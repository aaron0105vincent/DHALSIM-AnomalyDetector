#!/bin/bash

cwd=$(pwd)
version=$(lsb_release -rs )

doc=false
test=false

# Setting up test and doc parameters
while getopts ":dt" opt; do
  case $opt in
    d)
      printf "Installing with documentation dependencies.\n"
      doc=true
      ;;
    t)
      printf "Installing with testing dependencies.\n"
      test=true
      ;;
    \?)
      printf "Unknown option. Proceeding without installing documentation and testing dependencies.\n"
      ;;
  esac
done

echo "Starting DHALSIM installation..."
sleep 1

# ============================================================================
# System Update and Base Dependencies
# ============================================================================
echo "Updating system packages..."
sudo apt update

echo "Installing base dependencies..."
sudo apt install -y git python3 python3-pip curl

echo "Installing cpppo..."
sudo python3 -m pip install cpppo

# ============================================================================
# Install Mininet
# ============================================================================
echo "Installing Mininet..."
cd ~
git clone --depth 1 -b 2.3.1b4 https://github.com/mininet/mininet.git || git -C mininet pull
cd mininet
sudo PYTHON=python3 ./util/install.sh -fnv

# ============================================================================
# Install MiniCPS
# ============================================================================
echo "Installing MiniCPS..."
cd ~
git clone https://github.com/scy-phy/minicps.git
cd minicps
git checkout 94145cecaa692955db299238794d0d8c5637273a
sudo python3 -m pip install .
if [ $? -ne 0 ]; then
    echo "ERROR: MiniCPS installation failed!" >&2
    exit 1
fi

# ============================================================================
# Install epynet - An EPANET Python wrapper for WNTR
# ============================================================================
echo "Installing epynet..."
cd ~
if [ ! -d "DHALSIM-epynet" ]; then
    git clone --depth 1 https://github.com/afmurillo/DHALSIM-epynet
else
    echo "DHALSIM-epynet directory exists, updating..."
    git -C DHALSIM-epynet pull
fi
cd DHALSIM-epynet/
sudo python3 -m pip install .


# ============================================================================
# Install Optional Testing Dependencies
# ============================================================================
if [ "$TEST" = true ]; then
    echo "Installing testing dependencies..."
    sudo python3 -m pip install pytest-timeout pytest-cov pytest-mock
fi

# ============================================================================
# Install NetfilterQueue for DoS Attacks
# ============================================================================
echo "Installing netfilterqueue for DoS attack support..."
sudo apt install -y libnfnetlink-dev libnetfilter-queue-dev
sudo python3 -m pip install -U git+https://github.com/kti/python-netfilterqueue

# ============================================================================
# Install DHALSIM
cd "${cwd}" || { printf "Failure: Could not find DHALSIM directory\n"; exit 1; }

# Install without doc and test
if [ "$test" = false ] && [ "$doc" = false ]
then
  sudo python3 -m pip install -e .

  printf "\nInstallation finished. You can now run DHALSIM by using \n\t<sudo dhalsim your_config.yaml>.\n"
  exit 0;
fi

# Install doc
if [ "$test" = false ]
then
  sudo python3 -m pip install -e .[doc]

  printf "\nInstallation finished. You can now run DHALSIM by using \n\t<sudo dhalsim your_config.yaml>.\n"
  exit 0;
fi

# Install test
if [ "$doc" = false ]
then
  sudo python3 -m pip install -e .[test]

  printf "\nInstallation finished. You can now run DHALSIM by using \n\t<sudo dhalsim your_config.yaml>.\n"
  exit 0;
fi

# Install test and doc
sudo python3 -m pip install -e .[test,doc]

printf "\nInstallation finished. You can now run DHALSIM by using \n\t<sudo dhalsim your_config.yaml>.\n"
exit 0;
