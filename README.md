# Enhancing DHALSIM Thesis (SUTD/TU Delft project)
A thesis project done on top of DHALSIM with the objective to enhance the functionality of DHALSIM. 

The repo contains features such as:
1. Physical-based anomaly detector and network-based anomaly detector
2. Dashboard to display merged alerts from both physical-based anomaly detector and network-based anomaly detector

Related Works:
[1] A. Murillo et al., ‘High-Fidelity Cyber and Physical Simulation of Water Distribution Systems. I: Models and Data’, Journal of Water Resources Planning and Management, vol. 149, no. 5, p. 04023009, May 2023, doi: 10.1061/JWRMD5.WRENG-5853.
[2] A. Murillo, R. Taormina, N. O. Tippenhauer, and S. Galelli, ‘High-Fidelity Cyber and Physical Simulation of Water Distribution Systems. II: Enabling Cyber-Physical Attack Localization’, Journal of Water Resources Planning and Management, vol. 149, no. 5, p. 04023010, May 2023, doi: 10.1061/JWRMD5.WRENG-5854.
[3] J.-P. Konijn, ‘Multi-domain Cyber-attack Detection in Industrial Control Systems’. Accessed: May 29, 2025. [Online]. Available: https://essay.utwente.nl/93236/


# Digital HydrAuLic SIMulator (DHALSIM)
_A Digital Twin for Water Distribution Systems. A work by the SUTD Critical Infrastructure Systems Lab, TU Delft Department of Water Management, CISPA, and iTrust_

DHALSIM uses the [WNTR](https://wntr.readthedocs.io/en/latest/index.html) EPANET wrapper to simulate the behaviour of water distribution systems. In addition, DHALSIM uses Mininet and MiniCPS to emulate the behavior of industrial control system controlling a water distribution system. This means that in addition to physical data, DHALSIM can also provide network captures of the PLCs, SCADA server, and other network and industrial devices present in the a water distribution system.

DHALSIM was presented in the ICSS Workshop in ACSAC'20, with the paper: [Co-Simulating Physical Processes and Network Data for High-Fidelity Cyber-Security Experiments](https://dl.acm.org/doi/abs/10.1145/3442144.3442147)

Two papers in the Journal of Water Resources Planning and Management explain in detail DHALSIM architecture, features, and capabilities: [High-fidelity cyber and physical simulation of water distribution systems. I: Models and Data](https://ascelibrary.org/doi/abs/10.1061/JWRMD5.WRENG-5853) and [High-fidelity cyber and physical simulation of water distribution systems. II: Enabling cyber-physical attack localization](https://ascelibrary.org/doi/abs/10.1061/JWRMD5.WRENG-5854)
 

## Installation

In order to offer a simple installation we have included an installation script which will install DHALSIM on an Ubuntu 20.04 and 22.04 machine. This script is located in the root of the repository and can be run with ```./install.sh```. Root privilege is required.

Detector installation script is separated in the detector folder and can be run with ```./detector_setup.sh```

## Running DHALSIM

DHALSIM can be run using the command ```sudo dhalsim path/to/config.yaml```.

Replacing the text between "< >" with the path to one example topology or your own configuration files. For example, for the anytown example, you'd use:
```sudo dhalsim <examples/anytown_topology/anytown_config.yaml>```

## Running DHALSIM with detector

DHALSIM with detector can be run using the command ```sudo ./dhalsim_monitor.sh path/to/config.yaml``` in detector folder which will run the script for running DHALSIM, Zeek logging, physical-based detector, network-based detector, and the dashboard.
