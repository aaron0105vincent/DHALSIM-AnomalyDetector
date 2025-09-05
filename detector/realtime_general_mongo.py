import os
import time
import sqlite3
import json
import re
from collections import deque
import numpy as np
import atexit
from modules.mongodb_config import get_alerts_collection, get_mongo_db

import functools
print = functools.partial(print, flush=True)

_first_alert = True

# Configuration
DB_PATH = "/tmp/monitor_copy.sqlite"
POLL_INTERVAL = 1.2  # Seconds, lower gives faster refresh rate, but higher computation

# CUSUM parameters
W = 144 # Window size
DECAY = 0.99 #Decay rate, how much the CUSUM statistics are decayed per time step
PERSISTENCE_THRESHOLD = 2 #Persistence threshold, how many time steps the CUSUM statistics must be above the threshold to trigger an alert
k_a_max = 0.3 # Sensitivity of the CUSUM
MIN_H = 0.8 #Minimum threshold, the minimum threshold for the CUSUM statistics
MAX_H = 10.0 #Maximum threshold, the maximum threshold for the CUSUM statistics
residual_mode = "median" # "mean" or "median"
threshold_mode = "mad" # "mean", "mad" or "flat". Changes the way the CUSUM threshold is precessed

# Invariant Parameters
INV_PERSIST = 2  # Persistence threshold, how many time steps the invariant must be violated to trigger an alert
DEAD_BAND = 0.10 # Prevents jitter in the invariant

# Drift Parameters
DRIFT_THRESHOLD = 0.6 # Drift threshold, the threshold for the drift detection


# Runtime state placeholders
k_attack = {}
tanks = []
pumps = []
cusum_state = {}
long_term_buffers = {}
last_block_mean = {}

# Database helpers
def safe_db_query(conn, query):
    while True:
        try:
            cur = conn.cursor()
            cur.execute(query)
            return cur.fetchall()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.1)
            else:
                raise

# Get iteration number
def get_master_time(conn):
    rows = safe_db_query(conn, "SELECT time FROM master_time WHERE id = 1")
    return int(float(rows[0][0])) if rows else None

# Get state tuple
def get_current_state(conn):
    rows = safe_db_query(conn, "SELECT name, value FROM plant")
    return {name: float(value) for name, value in rows} if rows else {}

# Detection functions
def compute_threshold_and_residual(buffer, x_t, tank):
    buf = list(buffer)
    estimate = np.median(buf) if residual_mode == "median" else np.mean(buf)
    residual = x_t - estimate
    if threshold_mode == "mad":
        mad = np.mean(np.abs(np.array(buf) - np.median(buf)))
        rolling_mad = max(1.4826 * mad, 1e-6)
        h_t = min(max(3.0 * rolling_mad, MIN_H), MAX_H)
        k_a = max(k_a_max, k_attack.get(tank, k_a_max) * rolling_mad)
    else:
        std = max(np.std(buf), 1e-6)
        h_t = min(max(3.0 * std, MIN_H), MAX_H)
        k_a = max(k_a_max, k_attack.get(tank, k_a_max) * std)
    return residual, h_t, k_a

# CUSUM algorithm
def check_cusum(state, current_time):
    alerts = []
    for tank in tanks:
        x_t = state.get(tank, 0.0)
        st  = cusum_state[tank]

        #Window collection for W samples
        if len(st["buffer"]) < W:
            st["buffer"].append(x_t)
            continue                

        residual, h_t, k_a = compute_threshold_and_residual(st["buffer"], x_t, tank)

        #Slide window forward 1 step
        st["buffer"].append(x_t)

        # CUSUM update
        st["h_t"]     = h_t
        st["C_plus"]  = max(0.0, DECAY * st["C_plus"]  + residual - k_a)
        st["C_minus"] = max(0.0, DECAY * st["C_minus"] - residual - k_a)

        #Persistence logic to prevent alarm sensitivity
        above = st["C_plus"] > h_t or st["C_minus"] > h_t
        st.setdefault("persist", 0)
        st["persist"] = min(st["persist"] + 1, PERSISTENCE_THRESHOLD) if above else 0

        if st["persist"] >= PERSISTENCE_THRESHOLD:
            alerts.append({
                "event":     "CUSUM_ALARM",
                "iteration": current_time,
                "tank":      tank,
                "C_plus":    st["C_plus"],
                "C_minus":   st["C_minus"],
                "persist":   st["persist"],
                "types":     ["CUSUM_ALARM"]
            })

    return alerts

# Invariant Algorithm
def check_invariants(state, current_time):
    alerts = []

    pump_on = any(state.get(p, 0) for p in pumps)     # True if any pump is running

    for tank in tanks:
        level  = state.get(tank, 0.0)

        # Retrieve previous level and consecutive-bad counter, defaulting to None / 0
        prev    = getattr(check_invariants, f"prev_{tank}", None)
        badcnt  = getattr(check_invariants, f"badcnt_{tank}", 0)

        # Save current level for the next loop
        setattr(check_invariants, f"prev_{tank}", level)

        # Skip check on very first sample
        if prev is None:
            continue

        # Determine whether invariant is violated this step
        delta    = level - prev
        violated = (pump_on and delta < -DEAD_BAND) or (not pump_on and delta > DEAD_BAND)

        # Update consecutive-bad counter
        badcnt = badcnt + 1 if violated else 0
        setattr(check_invariants, f"badcnt_{tank}", badcnt)

        # Fire alert only after INV_PERSIST consecutive violations
        if badcnt >= INV_PERSIST:
            alerts.append({
                "event":     "INVARIANT_VIOLATION",
                "iteration": current_time,
                "tank":      tank,
                "level":     level,
                "prev":      prev,
                "persist":   badcnt,
                "types":     ["INVARIANT_VIOLATION"]
            })
            setattr(check_invariants, f"badcnt_{tank}", 0)   # reset counter

        # Independent check for empty tank
        if level == 0.0:
            alerts.append({
                "event":     "TANK_EMPTY",
                "iteration": current_time,
                "tank":      tank,
                "types":     ["TANK_EMPTY"]
            })

    return alerts

#Mean drift Algorithm
def check_drift(state, current_time):
    alerts = []
    for tank in tanks:
        long_term_buffers[tank].append(state.get(tank, 0.0))
    if all(len(long_term_buffers[t]) >= W for t in tanks):
        for tank in tanks:
            cur_mean  = float(np.mean(long_term_buffers[tank]))
            prev_mean = last_block_mean[tank]
            if prev_mean is not None and abs(cur_mean - prev_mean) > DRIFT_THRESHOLD:
                alerts.append({
                    "iteration": current_time,
                    "tank":      tank,
                    "baseline":  prev_mean,
                    "current":   cur_mean,
                    "types":     ["MEAN_DRIFT"]
                })
            last_block_mean[tank] = cur_mean
        for t in tanks:
            long_term_buffers[t].clear()
    return alerts

# Main monitoring loop
def monitor():
    global tanks, pumps, cusum_state, long_term_buffers, last_block_mean
    print(f"Monitoring DB: {DB_PATH}")
    
    alerts_collection = get_alerts_collection()
    if alerts_collection is None:
        print("WARNING: MongoDB connection failed. Proceeding with JSON-only logging.")
    
    # Wait for SQLIte copy to be ready
    while not os.path.exists(DB_PATH):
        print("Waiting for DB copy to appear…")
        time.sleep(POLL_INTERVAL)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE;")

    while True:
        try:
            conn.execute("SELECT 1 FROM plant LIMIT 1")
            break
        except sqlite3.OperationalError:
            print("Waiting for table 'plant' to exist…")
            time.sleep(POLL_INTERVAL)

    # Dynamic topology discovery, auto detect number of tanks and pumps
    rows = safe_db_query(conn, "SELECT DISTINCT name FROM plant")
    names = [r[0] for r in rows]
    tanks = sorted(n for n in names if re.match(r'^[Tt]\d+', n))
    pumps = sorted(n for n in names if re.match(r'^[Pp][Uu]?\d+', n))
    for t in tanks:
        k_attack[t] = 1.35

    cusum_state       = {t: {"buffer": deque(maxlen=W), "C_plus":0.0, "C_minus":0.0} for t in tanks}
    long_term_buffers = {t: deque(maxlen=W) for t in tanks}
    last_block_mean   = {t: None for t in tanks}

    print("Discovered tanks:", tanks)
    print("Discovered pumps:", pumps)
    print(f"Initializing initial buffer of W = {W} samples... Start warm-up...")

    last_time = -1
    try:
        while True:
            try:
                current_time = get_master_time(conn)
                if current_time is None or current_time == last_time:
                    time.sleep(POLL_INTERVAL)
                    continue
                state = get_current_state(conn)

                # Warm-up: fill CUSUM buffer
                check_cusum(state, current_time)
                if any(len(cusum_state[t]["buffer"]) < W for t in tanks):
                    counts = {t: len(cusum_state[t]["buffer"]) for t in tanks}
                    print(f"Warming up… collected {counts} (need {W} samples)")
                    last_time = current_time
                    time.sleep(POLL_INTERVAL)
                    continue

                # Generate alerts each iteration
                for alert in check_cusum(state, current_time):
                    write_alert(alert)
                    print(json.dumps(alert, default=str))
                for alert in check_invariants(state, current_time):
                    write_alert(alert)
                    print(json.dumps(alert, default=str))
                for alert in check_drift(state, current_time):
                    write_alert(alert)
                    print(json.dumps(alert, default=str))

                # CLI summary
                summary = []
                for t in tanks:
                    summary.append(f"{t}: C+={cusum_state[t]['C_plus']:.2f}, C-={cusum_state[t]['C_minus']:.2f}, h_t={cusum_state[t]['h_t']:.2f}")
                print(f"ITERATION {current_time} " + ", ".join(summary))

                last_time = current_time
            except Exception as e:
                print(f"[ERROR] {e}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[INFO] Monitoring stopped by user")
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("[INFO] Database connection closed")

if __name__ == "__main__":
    monitor()
