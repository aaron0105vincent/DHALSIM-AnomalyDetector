#!/bin/bash
set -e

# Function to check command success
check_status() {
    if [ $? -ne 0 ]; then
        echo "$1 failed!" >&2
        exit 1
    fi
}

# ============================================================================
# SYSTEM SETUP
# ============================================================================

# Update system and install basic dependencies
sudo apt update && sudo apt install -y python3-pip tmux git apt-utils gnupg curl
check_status "System package installation"

# ============================================================================
# ZEEK INSTALLATION
# ============================================================================

# Add Zeek repository
echo 'deb http://download.opensuse.org/repositories/security:/zeek/xUbuntu_22.04/ /' | sudo tee /etc/apt/sources.list.d/security:zeek.list
curl -fsSL https://download.opensuse.org/repositories/security:zeek/xUbuntu_22.04/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/security_zeek.gpg > /dev/null

# Install Zeek and its dependencies
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install -y --no-install-recommends zeek-7.0 libssl-dev cmake make g++ libpcap-dev python3-dev nano
check_status "Zeek and dependencies installation"

# Verify Zeek installation
if [ ! -f "/opt/zeek/bin/zkg" ]; then
    echo "Error: Zeek installation failed - zkg not found" >&2
    exit 1
fi

# Install Zeek plugin for CIP and ENIP
sudo /opt/zeek/bin/zkg refresh
echo "y" | sudo /opt/zeek/bin/zkg install icsnpp-enip
check_status "Zeek plugin installation"

# ============================================================================
# PYTHON PACKAGES
# ============================================================================

# Install Python packages for the detector
sudo pip install \
    salesforce-merlion \
    pymongo \
    "dash<3.0.0" \
    "dash-bootstrap-components<2.0.0" \
    typing-extensions==4.4.0
check_status "Python packages installation"

# ============================================================================
# MONGODB INSTALLATION
# ============================================================================

# Add MongoDB repository
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
    sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor

echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/8.0 multiverse" | \
    sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list

# Install MongoDB
sudo apt update
sudo apt install -y mongodb-org
check_status "MongoDB installation"

echo "Setup completed successfully!"