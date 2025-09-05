# Zeek-Configuration-Files
Zeek config used is a combination of config referenced from these repo/packages :
1. https://github.com/RabbITCybErSeC/Multi-domain-Cyber-attack-Detection-in-Industrial-Control-Systems-Resources/tree/main/zeek-config-ics
2. https://github.com/stratosphereips/zeek-package-ARP
3. https://github.com/cisagov/icsnpp-enip

For usage with static files:```/opt/zeek/bin/zeek -r <pcap> local.zeek ```
For live capture usage with interface:```/opt/zeek/bin/zeek -i <interface> -C local.zeek ```