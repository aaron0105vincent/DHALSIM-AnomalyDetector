sudo pkill -f "automatic_router.py"; 
sudo pkill -f "automatic_plc.py"; 
sudo pkill -f "automatic_scada.py"; 
sudo pkill -f "local.zeek"; 
sudo pkill -f "intermediate.yaml";
tmux kill-server;