# Batman-adv mesh plugin for RETCON
import asyncio
import subprocess
import hashlib
import netifaces as ni
from jinja2 import Template
from .base_plugin import RetconPlugin
import logging

logger = logging.getLogger("retcon")

# AutoInterface template for bat0 - stable interface, no TCP backbone needed
auto_iface_template = """
[[Batman Mesh AutoInterface]]
  type = AutoInterface
  interface_enabled = True
  mode = full
  devices = bat0

"""


class BatmanMeshPlugin(RetconPlugin):
    """
    batman-adv based mesh networking plugin.

    Creates a true Layer 2 mesh using ad-hoc WiFi and batman-adv.
    Optionally maintains an AP interface for non-mesh-aware clients.
    """

    PLUGIN_NAME = "batman_mesh"

    DEFAULT_MTU = 1532  # batman-adv overhead requires larger MTU on mesh interface

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mesh_running = False

    def get_config(self) -> dict:
        """Return Reticulum interface configuration for bat0."""
        interface_str = Template(auto_iface_template).render()
        return {
            "plugin_interfaces": interface_str
        }

    def init(self):
        """Initialize batman-adv mesh on startup."""
        logger.info("Initializing batman-adv mesh plugin")

        wifi = self.retcon_config["retcon"]["wifi"]
        mesh_config = self.config  # batman_mesh section from config

        # Get configuration
        mesh_iface = wifi.get("mesh_iface", wifi.get("client_iface", "wlan0"))
        ap_iface = wifi.get("ap_iface", "uap0") if self.retcon_config["retcon"]["mode"] == "transport" else None

        # ESSID: use config override or generate from prefix
        essid = mesh_config.get("essid", wifi.get("prefix", "RETCON") + "-MESH")
        channel = self._freq_to_channel(int(wifi.get("freq", 2462)))
        cell_id = self._generate_cell_id(essid)

        logger.info(f"Batman mesh config: iface={mesh_iface}, essid={essid}, channel={channel}, cell_id={cell_id}")

        # Bring up batman-adv mesh
        self._setup_batman_mesh(mesh_iface, essid, channel, cell_id)

        # If transport mode, set up dnsmasq redirects for client AP
        if ap_iface:
            self._transport_update_dnsmasq(ap_iface)

        self._mesh_running = True

    def _setup_batman_mesh(self, iface: str, essid: str, channel: int, cell_id: str):
        """Configure ad-hoc WiFi and batman-adv."""
        logger.info(f"Setting up batman-adv mesh on {iface}")

        freq = self._channel_to_freq(channel)

        commands = [
            # Take down any existing connections on this interface
            f"nmcli device disconnect {iface} 2>/dev/null || true",

            # Ensure batman-adv module is loaded
            "modprobe batman-adv",

            # Set interface down for configuration
            f"ip link set {iface} down",

            # Configure ad-hoc mode
            f"iw {iface} set type ibss",
            f"ip link set {iface} mtu {self.DEFAULT_MTU}",
            f"ip link set {iface} up",

            # Join the ad-hoc cell
            f"iw {iface} ibss join {essid} {freq} fixed-freq {cell_id}",

            # Add interface to batman-adv
            f"batctl if add {iface}",

            # Bring up bat0
            "ip link set bat0 up",

            # Set originator interval (ms) - lower = faster route updates
            "batctl orig_interval 1000",

            # Enable bridge loop avoidance
            "batctl bridge_loop_avoidance 1",

            # Enable distributed ARP table
            "batctl distributed_arp_table 1",
        ]

        for cmd in commands:
            logger.debug(f"Running: {cmd}")
            result = subprocess.run(cmd, shell=True, capture_output=True)
            if result.returncode != 0 and "2>/dev/null" not in cmd:
                stderr = result.stderr.decode() if result.stderr else ""
                if stderr:
                    logger.warning(f"Command '{cmd}' returned {result.returncode}: {stderr}")

        # Assign IP to bat0 based on node MAC
        self._assign_mesh_ip()

    def _transport_update_dnsmasq(self, ap_iface: str):
        """Update DNS masquerade file so retcon domains point to this node (transport only)."""
        try:
            ip = ni.ifaddresses(ap_iface)[ni.AF_INET][0]["addr"]
            urls = ["retcon.gateway", "retcon.local", "retcon.radio", "retcon.com", "retcon"]
            redirect_str = "\n".join(f"address=/{x}/{ip}" for x in urls)
            config_path = "/etc/NetworkManager/dnsmasq-shared.d/retcon_redirect.conf"
            with open(config_path, "w") as fout:
                fout.write(redirect_str)
            logger.info(f"Updated dnsmasq redirects to {ip}")
        except Exception as e:
            logger.warning(f"Could not update dnsmasq config: {e}")

    def _assign_mesh_ip(self):
        """Assign a unique IP to bat0 based on MAC address."""
        try:
            # Get bat0 MAC address
            addrs = ni.ifaddresses("bat0")
            if ni.AF_LINK not in addrs:
                logger.warning("bat0 has no MAC address yet")
                return

            mac = addrs[ni.AF_LINK][0]["addr"]
            # Use last 2 bytes of MAC for IP (10.99.X.Y/16)
            mac_bytes = bytes.fromhex(mac.replace(":", ""))
            ip = f"10.99.{mac_bytes[-2]}.{mac_bytes[-1]}/16"

            # Check if IP already assigned
            result = subprocess.run(f"ip addr show bat0 | grep -q '{ip.split('/')[0]}'",
                                    shell=True, capture_output=True)
            if result.returncode == 0:
                logger.info(f"IP {ip} already assigned to bat0")
                return

            subprocess.run(f"ip addr add {ip} dev bat0", shell=True, capture_output=True)
            logger.info(f"Assigned {ip} to bat0")
        except Exception as e:
            logger.error(f"Failed to assign IP to bat0: {e}")

    def _generate_cell_id(self, essid: str) -> str:
        """Generate a consistent cell ID (BSSID) from the ESSID."""
        # Hash the ESSID to get a consistent cell ID
        h = hashlib.sha256(essid.encode()).digest()
        # Format as MAC address with locally administered bit set (02:xx:xx:xx:xx:xx)
        cell_id = f"02:{h[0]:02x}:{h[1]:02x}:{h[2]:02x}:{h[3]:02x}:{h[4]:02x}"
        return cell_id

    def _freq_to_channel(self, freq: int) -> int:
        """Convert WiFi frequency to channel number."""
        channel_map = {
            2412: 1, 2417: 2, 2422: 3, 2427: 4, 2432: 5,
            2437: 6, 2442: 7, 2447: 8, 2452: 9, 2457: 10,
            2462: 11, 2467: 12, 2472: 13, 2484: 14
        }
        return channel_map.get(freq, 11)

    def _channel_to_freq(self, channel: int) -> int:
        """Convert WiFi channel to frequency."""
        freq_map = {
            1: 2412, 2: 2417, 3: 2422, 4: 2427, 5: 2432,
            6: 2437, 7: 2442, 8: 2447, 9: 2452, 10: 2457,
            11: 2462, 12: 2467, 13: 2472, 14: 2484
        }
        return freq_map.get(channel, 2462)

    async def loop(self):
        """Periodic maintenance loop."""
        if not self._mesh_running:
            return

        # Log mesh status periodically
        try:
            result = subprocess.run("batctl o 2>/dev/null", shell=True, capture_output=True)
            originators = result.stdout.decode().strip()
            if originators:
                lines = originators.split('\n')
                # Subtract header lines to get actual peer count
                peer_count = max(0, len(lines) - 2)
                if peer_count > 0:
                    logger.info(f"Batman-adv mesh peers: {peer_count}")
        except Exception as e:
            logger.debug(f"Could not get mesh status: {e}")
