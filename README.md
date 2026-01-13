# RETCON (Reticulum Embedded Turnkey Connection Operating Node) v0.0.9

Because complex networks shouldn't require complex setup.

## Overview

RETCON is a streamlined, deployment-focused solution for Reticulum mesh networking.  While Reticulum provides powerful customization options, RETCON packages these capabilities into a solution that is ready-to-deploy en masse.

RETCON enables quick creation of pre-configured Raspberry Pi images that automatically form resilient mesh networks once deployed. It is designed for scenarios where rapid consistent deployment matters more than configuration flexibility - e.g. conferences, maker camps, community events, emergency response situations, and other environments where you need reliable communication infrastructure quickly.

Note: This is currently alpha dev release. Use at your own risk and please give feedback on improvements or potenial PRs!

### Key Features

- **One-command image creation**: Create SD card images pre-configured with Reticulum settings
- **Auto-detection**: Automatically identifies and connects to USB attached RNodes and Meshtastic devices so users don't need to fiddle with config files
- **batman-adv mesh networking**: Forms device-to-device Layer 2 mesh networks using WiFi ad-hoc mode, no additional hardware required ([learn more](docs/MESH_NETWORKING.md))
- **Bluetooth PAN connectivity**: Phones and tablets connect via Bluetooth Personal Area Network - no WiFi password needed
- **Dual operation modes**:
  - **Transport mode**: Headless relay operation, WiFi used exclusively for mesh networking
  - **Client mode**: User access via Bluetooth PAN with Meshchat web UI and Reticulum connectivity


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
- arm64 environment or qemu supported emulation of arm64 and armf

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

For devices in **client mode**, see the "Connecting to a RETCON Node" section below.

For devices in **transport mode**, the node will automatically join the mesh network and relay traffic.

## Connecting to a RETCON Node (Client Mode)

RETCON nodes in client mode use **Bluetooth PAN** (Personal Area Network) for user connections. This provides full IP networking over Bluetooth - no WiFi password needed!

### Quick Start

1. **Enable Bluetooth** on your phone/tablet
2. **Scan for devices** - look for the node name (e.g., "RETCON-BT" or configured name)
3. **Pair** with the device (one-time, no PIN required)
4. **Connect** to the paired Bluetooth device
5. **Open browser** and go to `http://192.168.4.1` or `http://retcon.local`
6. **Meshchat loads!** Start communicating on the mesh network

### Using the Sideband App

You can connect the Sideband Reticulum app to a RETCON node via Bluetooth PAN. Add this interface to your Sideband config:

```
[[RETCON BT-PAN]]
  type = TCPClientInterface
  enabled = yes
  target_host = 192.168.4.1
  target_port = 4242
```

### Bluetooth Limitations

- **Range**: ~10 meters (Bluetooth Class 2)
- **Max connections**: 7 devices simultaneously (Bluetooth piconet limit)
- **Throughput**: ~2-3 Mbps (sufficient for messaging)

## Operation Modes

### Transport Mode

In Transport mode, RETCON operates headlessly as a mesh relay. This mode is ideal for:
- Extending the physical range of your mesh network
- Deploying relay nodes in strategic locations

Transport nodes use WiFi exclusively for batman-adv mesh networking with other RETCON nodes. Bluetooth PAN is disabled. Any attached LoRa hardware (RNode, Meshtastic) will also be utilized.

### Client Mode

Client mode provides both mesh networking capabilities and end-user access:
- **Bluetooth PAN** for phone/tablet connections (no WiFi password needed)
- Pre-configured **Meshchat web UI** accessible at `http://192.168.4.1`
- **Reticulum TCP interface** for Sideband app connectivity
- Maintains mesh connectivity to other RETCON nodes via batman-adv
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
- [x] Client mode with Meshchat web UI
- [x] Web based app in client mode
- [x] Set Meshchat default config from RETCON config file
- [x] Ability to change from client to transport mode via admin interfaces
- [x] batman-adv Layer 2 mesh networking (replaced WiFi AP mesh)
- [x] Bluetooth PAN for phone/tablet connectivity (replaced WiFi AP for user access)
- [ ] Configure rpi-image-gen from retcon config (for things like ssh, username and extra apt packages)
- [ ] Nomadnet/micron configuration interface for field adjustments
- [ ] 'microRetcon' for hardware platforms (ESP32, etc.)
- [ ] Better error handling around meshchat crashes


### Debugging, Dev and security Tips

SSH in enabled in the raspi build but disabled on first boot by RETCON. It can be temporarily turned on via the web interface. 
default username is `retcon` and password is `retcon`. If the node is somewhere people have easy phsyical access to it (or if SSH server is turned on) then this absolutely needs to be changed! 

You can change or configure files on teh SD card without booting. All retcon files are in `/home/retcon/retcon/` 


### Troubleshooting

#### Can't find the RETCON node in Bluetooth scan
- Make sure the node is in **client mode** (transport mode disables Bluetooth PAN)
- The Bluetooth name defaults to the WiFi prefix + "-BT" (e.g., "RT-DEFAULT-BT")
- Ensure Bluetooth is enabled on your phone/tablet
- You may need to be within ~10 meters of the node

#### Can't access web UI after Bluetooth connection
- Make sure you're connected (not just paired) to the Bluetooth device
- Your device should get an IP address in the 192.168.4.x range via DHCP
- Try accessing `http://192.168.4.1` directly instead of `retcon.local`

#### Mesh nodes not seeing each other
All RETCON nodes must use the same WiFi configuration to mesh together:
- Same `prefix` (ESSID prefix for mesh network)
- Same `psk` (password)
- Same `freq` (WiFi frequency/channel)

For a deep dive on how the mesh works, see [docs/MESH_NETWORKING.md](docs/MESH_NETWORKING.md).

WiFi channel to frequency mapping (2.4 GHz):
```
wifi_channel_to_freq = {
    1: 2412,  6: 2437,  11: 2462,
    2: 2417,  7: 2442,  12: 2467,
    3: 2422,  8: 2447,  13: 2472,
    4: 2427,  9: 2452,  14: 2484,
    5: 2432,  10: 2457
}
``` 

## License

This project is licensed under the MIT License - see the LICENSE file for details.


---

