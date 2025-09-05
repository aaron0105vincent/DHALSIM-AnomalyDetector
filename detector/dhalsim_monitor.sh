#!/usr/bin/env bash

SESSION="dhalsim"
# CONFIG_YAML="$1"
CONFIG_YAML="$1"
BASE_DIR="$(pwd)"
current_time=$(date +"%Y-%m-%d-%H-%M-%S")
LOG_DIR="$BASE_DIR/logs/logs_$current_time"
OUTPUT_DIR="$BASE_DIR/output/output_$current_time"
CONFIG_DIR="$BASE_DIR/zeek_config/local.zeek"

# Get the actual user (not root when using sudo)
if [ -n "$SUDO_USER" ]; then
    CURR_USER="$SUDO_USER"
else
    CURR_USER="$(whoami)"
fi



# Load detector configuration from YAML file
DETECTOR_CONFIG_FILE="$BASE_DIR/detector_config.yaml"

if [ ! -f "$DETECTOR_CONFIG_FILE" ]; then
    echo "Error: Detector configuration file not found: $DETECTOR_CONFIG_FILE"
    exit 1
fi

# Extract detector information using Python helper
DETECTOR_INFO=$(python3 "$BASE_DIR/detector_config_parser.py" "$DETECTOR_CONFIG_FILE")

# Parse the detector information into arrays
declare -a INTERFACES
declare -a DETECTORS
declare -a LOG_TYPES
declare -a SCRIPTS

while IFS='|' read -r interface detector_id log_type script; do
    [ -z "$interface" ] && continue
    INTERFACES+=("$interface")
    DETECTORS+=("$detector_id")
    LOG_TYPES+=("$log_type")
    SCRIPTS+=("$script")
done <<< "$DETECTOR_INFO"

echo "[*] Loaded configuration: ${#INTERFACES[@]} detectors"
for i in "${!INTERFACES[@]}"; do
    echo "    ${DETECTORS[$i]} (${LOG_TYPES[$i]}) -> ${INTERFACES[$i]} (${SCRIPTS[$i]})"
done

if [ -d "$OUTPUT_DIR" ]; then
    echo "[*] Removing existing OUTPUT_DIR..."
    sudo rm -rf "$OUTPUT_DIR"
fi

if [ -z "$CONFIG_YAML" ]; then
  echo "Usage: $0 <path_to_config.yaml>"
  exit 1
fi

# Start MongoDB (needs sudo)
echo "[*] Starting MongoDB..."
sudo systemctl start mongod

# Ensure LOG_DIR exists
mkdir -p "$LOG_DIR"
mkdir -p "$OUTPUT_DIR"

# Fix permissions on logs
sudo chown -R $CURR_USER:$CURR_USER $BASE_DIR
sudo chown -R $CURR_USER:$CURR_USER $OUTPUT_DIR
sudo chown -R $CURR_USER:$CURR_USER $LOG_DIR
# Ensure LOG_DIR exists

# Create (or truncate) log files
: > "$LOG_DIR/dhalsim.log"
: > "$LOG_DIR/copydb.log"
: > "$LOG_DIR/monitor.log"
: > "$LOG_DIR/dash_viewer.log"
: > "$LOG_DIR/save_alerts.log"



# Kill old session and remove old db data
sudo rm -rf /tmp/dhalsim_* 2>/dev/null
sudo rm -rf /tmp/monitor_copy.* 2>/dev/null
tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"

echo "[*] Launching new tmux session '$SESSION'..."

# Pane 0: DHALSIM (as root)
tmux new-session -d -s "$SESSION" \
  "cd $BASE_DIR && \
   sudo dhalsim -o /tmp '$CONFIG_YAML' 2>&1 | tee '$LOG_DIR/dhalsim.log'; \
   echo; echo '=== DHALSIM exited (see dhalsim.log) ==='; \
   python3 extract_mongodb.py; \
   echo '=== Saving alerts from MongoDB ==='; \
   python3 save_alerts.py --output-dir '$OUTPUT_DIR' 2>&1 | tee -a '$LOG_DIR/save_alerts.log'; \
   echo '=== Alert saving completed ==='; \
   sleep 5; \
   sudo find "$BASE_DIR" -maxdepth 1 -name "en[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]" -type f -delete 2>/dev/null; \
   sudo pkill -f "automatic_router.py"; \
   sudo pkill -f "automatic_plc.py"; \
   sudo pkill -f "automatic_scada.py"; \
   sudo pkill -f "local.zeek"; \
   sudo pkill -f "intermediate.yaml"; \
   tmux kill-server"

echo "[*] Launching new db_copy and monitoring session '$SESSION'..."
# Pane 1: copydb + monitor (as user)
tmux split-window -h -t "$SESSION" \
  "cd $BASE_DIR && \
   python3 copydb.py > '$LOG_DIR/copydb.log' 2>&1 & \
   python3 -u realtime_general_mongo.py 2>&1 | tee '$LOG_DIR/monitor.log'; \
   echo; echo '=== Monitor exited (see monitor.log) ===';"




echo "[*] Launching new dash session '$SESSION'..."
# Pane 2: DashViewer (as user)
tmux split-window -h -t "$SESSION" \
  "cd $BASE_DIR && \
   python3 dash_merge.py --output-dir '$OUTPUT_DIR' 2>&1 | tee '$LOG_DIR/dash_viewer.log'; \
   echo; echo '=== Dash exited (see dash_viewer.log) ===';"


# Pane 3: Zeek live capture for each interface
for interface in "${INTERFACES[@]}"; do
    sudo rm -r "$OUTPUT_DIR/$interface" 2>/dev/null
    sudo rm -r "/tmp/dhalsim_*" 2>/dev/null
    mkdir -p "$OUTPUT_DIR/$interface"
done

# Evenly space
tmux select-layout -t "$SESSION" even-horizontal

tmux new-window -t "$SESSION":1 -n zeek

# Counter for tmux pane management
pane_counter=0

# Create unique list of interfaces for Zeek
declare -A unique_interfaces
for interface in "${INTERFACES[@]}"; do
    unique_interfaces["$interface"]=1
done

# Launch Zeek for each unique interface
interface_counter=0
for interface in "${!unique_interfaces[@]}"; do
    if [ $interface_counter -eq 0 ]; then
        # Split the first window horizontally for Zeek
        tmux split-window -h -t "$SESSION":1 \
          "sleep 5 && \
          cd '$OUTPUT_DIR/$interface' && sudo /opt/zeek/bin/zeek -i $interface -C '$CONFIG_DIR'"
    else
        # Split subsequent windows horizontally for Zeek
        tmux split-window -h -t "$SESSION":1 \
          "sleep 5 && \
          cd '$OUTPUT_DIR/$interface' && sudo /opt/zeek/bin/zeek -i $interface -C '$CONFIG_DIR'"
    fi
    ((interface_counter++))
done

# Launch detectors using smart split pane layout
# Create dedicated windows for different detector groups
conn_detectors=()
arp_detectors=()

# Group detectors by log type
for i in "${!INTERFACES[@]}"; do
    interface="${INTERFACES[$i]}"
    detector_id="${DETECTORS[$i]}"
    log_type="${LOG_TYPES[$i]}"
    script="${SCRIPTS[$i]}"
    
    if [ "$log_type" = "conn" ]; then
        conn_detectors+=("$i")
    elif [ "$log_type" = "arp" ]; then
        arp_detectors+=("$i")
    fi
done

# Function to launch detectors in a tmux window
launch_detector_group() {
    local window_num=$1
    local window_name=$2
    local -n detector_array=$3
    
    if [ ${#detector_array[@]} -gt 0 ]; then
        tmux new-window -t "$SESSION":$window_num -n "$window_name"
        
        for j in "${!detector_array[@]}"; do
            i="${detector_array[$j]}"
            interface="${INTERFACES[$i]}"
            detector_id="${DETECTORS[$i]}"
            log_type="${LOG_TYPES[$i]}"
            script="${SCRIPTS[$i]}"
            
            echo "[*] Launching $script for $interface monitoring $log_type logs..."
            
            local cmd="cd $BASE_DIR && sudo python3 -u $script '$CONFIG_YAML' '$interface' '$detector_id' '$OUTPUT_DIR/$interface' 2>&1 | tee '$LOG_DIR/${script}_${interface}_${log_type}.log'; echo; echo '=== $script for $interface ($log_type) exited ==='; bash"
            
            if [ $j -eq 0 ]; then
                # First detector in main pane
                tmux send-keys -t "$SESSION":$window_num "$cmd" Enter
            elif [ $j -eq 1 ]; then
                # Second detector - split horizontally
                tmux split-window -h -t "$SESSION":$window_num "$cmd"
            elif [ $j -eq 2 ]; then
                # Third detector - split vertically from first pane
                tmux split-window -v -t "$SESSION":$window_num.0 "$cmd"
            fi
        done
        tmux select-layout -t "$SESSION":$window_num main-horizontal
    fi
}

# Launch detector groups
launch_detector_group 2 "conn_detectors" conn_detectors
launch_detector_group 3 "arp_detectors" arp_detectors

echo "[*] Launching Python log processors..."

# Evenly space all panes
tmux select-layout -t "$SESSION" tiled

# Rename main panes
tmux select-pane -t "$SESSION":0 -T "DHALSIM and Detectors"
tmux select-pane -t "$SESSION":1 -T "Zeek"

# Attach to the tmux session
echo "[*] Attached to tmux session. Use Ctrl+b d to detach."
# Evenly spacing
tmux select-layout -t "$SESSION":0 even-horizontal

tmux attach-session -t "$SESSION":0
