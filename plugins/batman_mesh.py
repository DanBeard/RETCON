# Batman-adv mesh plugin for RETCON
import asyncio
import subprocess
import hashlib
import time
import netifaces as ni
from enum import Enum
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


class MeshState(Enum):
    """State machine states for batman-adv mesh."""
    UNCONFIGURED = "unconfigured"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"


class BatmanMeshPlugin(RetconPlugin):
    """
    batman-adv based mesh networking plugin.

    Creates a true Layer 2 mesh using ad-hoc WiFi and batman-adv.
    Optionally maintains an AP interface for non-mesh-aware clients.

    Features:
    - State machine with health monitoring
    - Automatic recovery with configurable retry limit
    - Status reporting for web UI
    """

    PLUGIN_NAME = "batman_mesh"

    DEFAULT_MTU = 1532  # batman-adv overhead requires larger MTU on mesh interface
    MAX_RECOVERY_ATTEMPTS = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = MeshState.UNCONFIGURED
        self._recovery_attempts = 0
        self._start_time = None
        # Store config for recovery
        self._iface = None
        self._essid = None
        self._channel = None
        self._cell_id = None
        self._ap_iface = None

    def get_config(self) -> dict:
        """Return Reticulum interface configuration for bat0."""
        interface_str = Template(auto_iface_template).render()
        return {
            "plugin_interfaces": interface_str
        }

    def _run_cmd(self, cmd: str, critical: bool = False) -> bool:
        """
        Run a shell command and return success status.

        Args:
            cmd: Shell command to execute
            critical: If True, raise RuntimeError on failure

        Returns:
            True if command succeeded, False otherwise
        """
        logger.debug(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True)
        success = result.returncode == 0
        if not success:
            stderr = result.stderr.decode() if result.stderr else ""
            stdout = result.stdout.decode() if result.stdout else ""
            msg = f"Command '{cmd}' failed (rc={result.returncode}): {stderr or stdout}"
            if critical:
                raise RuntimeError(msg)
            # Don't warn for commands that are expected to fail sometimes
            if "2>/dev/null" not in cmd and "|| true" not in cmd:
                logger.warning(msg)
        return success

    def _cleanup_mesh(self, iface: str):
        """
        Reset interface to clean state for retry or shutdown.

        This undoes the batman-adv and IBSS setup, returning the interface
        to managed mode so it can be reconfigured.
        """
        logger.info(f"Cleaning up mesh interface {iface}")
        cleanup_commands = [
            f"batctl if del {iface} 2>/dev/null || true",
            "ip link set bat0 down 2>/dev/null || true",
            f"ip link set {iface} down 2>/dev/null || true",
            f"iw {iface} set type managed 2>/dev/null || true",
            f"ip link set {iface} up 2>/dev/null || true",
        ]
        for cmd in cleanup_commands:
            subprocess.run(cmd, shell=True, capture_output=True)

    def _verify_module_loaded(self) -> bool:
        """Check if batman-adv kernel module is loaded."""
        result = subprocess.run("lsmod | grep -q batman_adv", shell=True, capture_output=True)
        return result.returncode == 0

    def _verify_mesh_health(self) -> bool:
        """
        Check that mesh is properly configured and running.

        Returns:
            True if mesh is healthy, False otherwise
        """
        if self._iface is None:
            return False

        # Check bat0 exists and is up
        result = subprocess.run("ip link show bat0 2>/dev/null | grep -q 'state UP\\|state UNKNOWN'",
                               shell=True, capture_output=True)
        if result.returncode != 0:
            logger.warning("bat0 interface not UP")
            return False

        # Check interface is attached to batman-adv
        result = subprocess.run(f"batctl if | grep -q '{self._iface}'",
                               shell=True, capture_output=True)
        if result.returncode != 0:
            logger.warning(f"{self._iface} not attached to batman-adv")
            return False

        # Check interface is in IBSS mode
        result = subprocess.run(f"iw {self._iface} info 2>/dev/null | grep -q 'type IBSS'",
                               shell=True, capture_output=True)
        if result.returncode != 0:
            logger.warning(f"{self._iface} not in IBSS mode")
            return False

        return True

    def _attempt_recovery(self):
        """
        Attempt to recover mesh with retry limit.

        After MAX_RECOVERY_ATTEMPTS failures, transitions to FAILED state
        which requires manual intervention.
        """
        if self._recovery_attempts >= self.MAX_RECOVERY_ATTEMPTS:
            logger.error(f"Max recovery attempts ({self.MAX_RECOVERY_ATTEMPTS}) reached. Mesh FAILED.")
            self._state = MeshState.FAILED
            return

        self._recovery_attempts += 1
        logger.info(f"Recovery attempt {self._recovery_attempts}/{self.MAX_RECOVERY_ATTEMPTS}")

        # Clean up before retry
        if self._iface:
            self._cleanup_mesh(self._iface)
        time.sleep(2)

        try:
            self._setup_batman_mesh(self._iface, self._essid, self._channel, self._cell_id)
            self._state = MeshState.RUNNING
            self._recovery_attempts = 0  # Reset on success
            logger.info("Mesh recovery successful")
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            self._state = MeshState.DEGRADED

    def init(self):
        """Initialize batman-adv mesh on startup."""
        logger.info("Initializing batman-adv mesh plugin")
        self._state = MeshState.INITIALIZING

        wifi = self.retcon_config["retcon"]["wifi"]
        mesh_config = self.config  # batman_mesh section from config

        # Get configuration and store for recovery
        self._iface = wifi.get("mesh_iface", wifi.get("client_iface", "wlan0"))
        self._ap_iface = wifi.get("ap_iface", "uap0") if self.retcon_config["retcon"]["mode"] == "transport" else None

        # ESSID: use config override or generate from prefix
        self._essid = mesh_config.get("essid", wifi.get("prefix", "RETCON") + "-MESH")
        self._channel = self._freq_to_channel(int(wifi.get("freq", 2462)))
        self._cell_id = self._generate_cell_id(self._essid)

        logger.info(f"Batman mesh config: iface={self._iface}, essid={self._essid}, "
                   f"channel={self._channel}, cell_id={self._cell_id}")

        try:
            # Bring up batman-adv mesh
            self._setup_batman_mesh(self._iface, self._essid, self._channel, self._cell_id)

            # If transport mode, set up dnsmasq redirects for client AP
            if self._ap_iface:
                self._transport_update_dnsmasq(self._ap_iface)

            self._state = MeshState.RUNNING
            self._start_time = time.time()
            logger.info("Batman-adv mesh initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize mesh: {e}")
            self._state = MeshState.DEGRADED
            # Will attempt recovery in loop()

    def _setup_batman_mesh(self, iface: str, essid: str, channel: int, cell_id: str):
        """
        Configure ad-hoc WiFi and batman-adv.

        Raises:
            RuntimeError: If critical commands fail
        """
        logger.info(f"Setting up batman-adv mesh on {iface}")

        freq = self._channel_to_freq(channel)

        # Phase 1: Load batman-adv module (critical)
        self._run_cmd("modprobe batman-adv", critical=False)
        time.sleep(0.5)
        if not self._verify_module_loaded():
            raise RuntimeError("batman-adv kernel module failed to load")

        # Phase 2: Disconnect from NetworkManager and prepare interface
        self._run_cmd(f"nmcli device disconnect {iface} 2>/dev/null || true")
        time.sleep(0.5)

        # Phase 3: Configure interface for ad-hoc mode (critical steps)
        self._run_cmd(f"ip link set {iface} down", critical=True)
        self._run_cmd(f"iw {iface} set type ibss", critical=True)

        # MTU setting - try but don't fail if not supported
        if not self._run_cmd(f"ip link set {iface} mtu {self.DEFAULT_MTU}"):
            logger.warning(f"Could not set MTU to {self.DEFAULT_MTU}, using default")

        self._run_cmd(f"ip link set {iface} up", critical=True)

        # Phase 4: Join ad-hoc cell (critical)
        self._run_cmd(f"iw {iface} ibss join {essid} {freq} fixed-freq {cell_id}", critical=True)
        time.sleep(1)

        # Phase 5: Add to batman-adv (critical)
        self._run_cmd(f"batctl if add {iface}", critical=True)
        self._run_cmd("ip link set bat0 up", critical=True)

        # Phase 6: Configure batman-adv parameters (non-critical)
        self._run_cmd("batctl orig_interval 1000")
        self._run_cmd("batctl bridge_loop_avoidance 1")
        self._run_cmd("batctl distributed_arp_table 1")

        # Phase 7: Assign IP
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

    def _get_peer_count(self) -> int:
        """Get the number of batman-adv mesh peers."""
        try:
            result = subprocess.run("batctl o 2>/dev/null", shell=True, capture_output=True)
            if result.returncode == 0:
                lines = result.stdout.decode().strip().split('\n')
                # Subtract header lines to get actual peer count
                return max(0, len(lines) - 2)
        except Exception:
            pass
        return 0

    def _log_mesh_status(self):
        """Log current mesh status."""
        peer_count = self._get_peer_count()
        if peer_count > 0:
            logger.info(f"Batman-adv mesh peers: {peer_count}")

    def get_status(self) -> dict:
        """
        Return mesh status for web UI and admin interface.

        Returns:
            dict with state, peer_count, bat0_ip, recovery info, and uptime
        """
        peer_count = self._get_peer_count()

        bat0_ip = None
        try:
            addrs = ni.ifaddresses("bat0")
            if ni.AF_INET in addrs:
                bat0_ip = addrs[ni.AF_INET][0].get("addr")
        except Exception:
            pass

        uptime = None
        if self._start_time:
            uptime = int(time.time() - self._start_time)

        return {
            "state": self._state.value,
            "peer_count": peer_count,
            "bat0_ip": bat0_ip,
            "interface": self._iface,
            "essid": self._essid,
            "recovery_attempts": self._recovery_attempts,
            "max_recovery_attempts": self.MAX_RECOVERY_ATTEMPTS,
            "uptime_seconds": uptime,
        }

    def force_restart(self):
        """
        Force a mesh restart. Can be called from admin interface.

        Resets recovery counter and attempts to reinitialize.
        """
        logger.info("Forcing mesh restart")
        self._recovery_attempts = 0
        self._state = MeshState.DEGRADED
        self._attempt_recovery()

    async def loop(self):
        """
        Periodic maintenance loop with health monitoring.

        Called every 60 seconds by the main RETCON loop.
        Checks mesh health and attempts recovery if needed.
        """
        # Permanent failure - require manual restart
        if self._state == MeshState.FAILED:
            return

        # Not yet initialized
        if self._state == MeshState.UNCONFIGURED:
            return

        # Health check
        if self._state in (MeshState.RUNNING, MeshState.DEGRADED):
            if not self._verify_mesh_health():
                logger.warning("Mesh health check failed, attempting recovery...")
                self._state = MeshState.DEGRADED
                self._attempt_recovery()
                return

        # If we're healthy, reset recovery counter
        if self._state == MeshState.RUNNING and self._recovery_attempts > 0:
            logger.info("Mesh healthy, resetting recovery counter")
            self._recovery_attempts = 0

        # If we recovered from DEGRADED, update state
        if self._state == MeshState.DEGRADED and self._verify_mesh_health():
            self._state = MeshState.RUNNING
            logger.info("Mesh recovered, state now RUNNING")

        # Log status
        self._log_mesh_status()
