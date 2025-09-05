import os
import time
import sqlite3
from glob import glob

DEST_PATH = "/tmp/monitor_copy.sqlite"
COPY_INTERVAL = 1  # In seconds

# Wait for the SQLite database to appear
def wait_for_dhalsim_db(timeout=300, check_interval=2):
    print("Waiting for /tmp/dhalsim_*/dhalsim.sqlite to appear...")
    elapsed = 0
    while elapsed < timeout:
        matches = glob("/tmp/dhalsim_*/dhalsim.sqlite")
        if matches:
            matches.sort(key=os.path.getctime, reverse=True)
            print(f"Found DB: {matches[0]}")
            return matches[0]
        time.sleep(check_interval)
        elapsed += check_interval
    raise TimeoutError("Timed out waiting for dhalsim.sqlite to appear in /tmp")

# Copy loop
def copy_sqlite_live(source_path, dest_path=DEST_PATH, interval=COPY_INTERVAL):
    print(f"Starting live DB copy from: {source_path}")
    while True:
        try:
            if not os.path.exists(source_path):
                print("Source DB deleted. Stopping copy service.")
                break
            with sqlite3.connect(source_path) as src, sqlite3.connect(dest_path) as dst:
                src.backup(dst)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("Copy service interrupted by user. Exiting.")
            break
        except Exception as e:
            print(f"[COPY ERROR] {e}")
            time.sleep(interval)

if __name__ == "__main__":
    try:
        if os.path.exists(DEST_PATH):
            os.remove(DEST_PATH)
        source_path = wait_for_dhalsim_db()
        copy_sqlite_live(source_path)
    except KeyboardInterrupt:
        print("Exiting cleanly due to Ctrl+C.")
    except Exception as e:
        print(f"Unhandled error: {e}")
