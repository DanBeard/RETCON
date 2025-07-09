# RETCON (Reticulum Embedded Turnkey Connection Operating Node) v0.0.5

Because complex networks shouldn't require complex setup.

## Overview

RETCON is a streamlined, deployment-focused solution for Reticulum mesh networking.  While Reticulum provides powerful customization options, RETCON packages these capabilities into a solution that is ready-to-deploy en masse.

RETCON enables quick creation of pre-configured Raspberry Pi images that automatically form resilient mesh networks once deployed. It is designed for scenarios where rapid consistent deployment matters more than configuration flexibility - e.g. conferences, maker camps, community events, emergency response situations, and other environments where you need reliable communication infrastructure quickly.

Note: This is currently alpha dev release. Use at your own risk and please give feedback on improvements or potenial PRs!

### Key Features

- **One-command image creation**: Create SD card images pre-configured with Reticulum settings
- **Auto-detection**: Automatically identifies and connects to USB attached RNodes and Meshtastic devices so users don't need to fiddle with config files
- **WiFi mesh capability**: Forms device-to-device mesh networks using raspi's built-in WiFi chip, no additional hardware required for small distance mesh hops
- **Dual operation modes**:
  - **Transport mode**: Headless operation focused solely on extending the mesh network
  - **Client mode**: Provides user-accessible access point with pre-configured Meshchat app for immediate communication


## Getting Started

### System Requirements

For running a RETCON image:

- Raspberry Pi 3/4/5 or Pi Zero 2W
- MicroSD card (8GB+ recommended)
- Optional: Compatible LoRa hardware (RNode, Meshtastic devices, etc.)

### Dev requirements
These are only needed for building a flashable RETCON image
- Debian 12+
- 8GB+ of RAM
- arm64 envorinment or qemu supported emulation of arm64 and armf

### Creating & Deploying a RETCON raspi Image


#### 1. Clone the RETCON Image Creator from source

```bash
# Clone from source
git clone https://github.com/DanBeard/RETCON.git
cd retcon

```

#### 2. Install prereqs and RETCON apps 
`sudo ./install_prereqs.sh`


#### 3. Configure active deployment
profile configuration is in retcon_profiles/active
Copy a default profile to 'active' and modify to meet your needs

Note: 'active' is gitignored. Other configs can be stored here and checked into git for easy copying e.g. dc33.config but be mindful of checking in config with passwords you'd rather not share publically. 


#### 4. Run the raspi image builder
`./build_retcon.sh`

Grab your favorite drink and relax because it will take a while. The last line printed will include the file location of the image. 

#### 5. Copy sd card

Use `dd` or raspi imager in "custom image" mode to flash the .img file to an sd card.

#### 6. Boot and use
For devices in client mode:
1. Connect to the RETCON access point (ssid is defined in the config file)
2. Open a web browser and navigate to `retcon.local` (or retcon.radio, or anything.retcon)
3. The Reticulum Meshchat interface will be available for immediate communication

## Operation Modes

### Transport Mode

In Transport mode, RETCON operates headlessly with no access point for end users. This mode is ideal for:
- Extending the physical range of your mesh network
- Deploying relay nodes in strategic locations

Transport nodes automatically connect to other RETCON nodes via WiFi when in range and will utilize any attached LoRa hardware for extended communication.

### Client Mode

Client mode provides both mesh networking capabilities and end-user access:
- Creates a separate access point for users to connect
- Pre-configures Meshchat for immediate communication
- Maintains mesh connectivity to other RETCON nodes
- Automatically bridges communications across the entire network

This mode is meant for user-facing nodes where people can access the mesh network.

## Administrating the Nodes
Each node comes with a text based administration console that can be used over LXMF. Look for the identity with the same name as the wifi mesh SSID.

### How to Contribute

Contributions are welcome and appreciated!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Planned Features

- [x] LXMF based configuration interface
- [x] Client mode where wifi AP password is different meshchat is launched automatically
- [x] Web based app in client mode to instruct users how to connect to meshchat and change wifi ap details
- [x] Captive portal in client mode directing to web app (retcon.local)
- [ ] Set Meshchat default config from RETCON config file. (e.g. default ident name/announce/etc)
- [x] Ability to change from client to transport mode via admin interfaces
- [x] Ability to change from client mode details from admin interface (like AP password)
- [ ] Configure rpi-image-gen from retcon config (for things like ssh, username and extra apt packages)
- [ ] Nomadnet/micron configuration interface for field adjustments
- [ ] 'microRetcon' for hardware platforms (ESP32, etc.)
- [ ] Integration with more transports (Bluetooth mesh, additional radio modules)


### Debugging, Dev and security Tips

SSH in enabled in the raspi build but disabled on first boot by RETCON. It can be temporarily turned on via the web interface. 
default username is `retcon` and password is `retcon`. If the node is somewhere people have easy phsyical access to it (or if SSH server is turned on) then this absolutely needs to be changed! 

### Troubleshooting

TODO 

## License

This project is licensed under the MIT License - see the LICENSE file for details.


---

