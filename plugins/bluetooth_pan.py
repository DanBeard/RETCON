# Bluetooth PAN plugin for RETCON
# Enables phone/tablet connectivity via Bluetooth Personal Area Network

import subprocess
import time
from enum import Enum
from .base_plugin import RetconPlugin
import logging

logger = logging.getLogger("retcon")


class BluetoothState(Enum):
    """State machine states for Bluetooth PAN."""
    UNCONFIGURED = "unconfigured"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"


class BluetoothPANPlugin(RetconPlugin):
    """
    Bluetooth PAN (Personal Area Network) plugin.

    Enables phones/tablets to connect to RETCON nodes via Bluetooth
    and access web apps (Meshchat UI) plus Reticulum network.

    Features:
    - Creates Bluetooth NAP (Network Access Point)
    - Phones get IP via DHCP (192.168.4.x/24)
    - Browser access to Meshchat, RETCON admin
    - Sideband can connect via TCP over BT-PAN

    Limitations:
    - Range: ~10m (Bluetooth Class 2)
    - Throughput: ~2-3 Mbps
    - Max connections: 7 (Bluetooth piconet limit)
    """

    PLUGIN_NAME = "bluetooth_pan"

    # Network configuration
    PAN_INTERFACE = "pan0"
    PAN_IP = "192.168.4.1"
    PAN_SUBNET = "192.168.4.0/24"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = BluetoothState.UNCONFIGURED
        self._start_time = None
        self._bt_name = None

    def _run_cmd(self, cmd: str, critical: bool = False) -> bool:
        """Run a shell command and return success status."""
        logger.debug(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True)
        success = result.returncode == 0
        if not success:
            stderr = result.stderr.decode() if result.stderr else ""
            stdout = result.stdout.decode() if result.stdout else ""
            msg = f"Command '{cmd}' failed (rc={result.returncode}): {stderr or stdout}"
            if critical:
                raise RuntimeError(msg)
            if "|| true" not in cmd:
                logger.warning(msg)
        return success

    def _run_bluetoothctl(self, commands: list) -> bool:
        """Run multiple bluetoothctl commands."""
        cmd_str = "\n".join(commands + ["quit"])
        result = subprocess.run(
            ["bluetoothctl"],
            input=cmd_str.encode(),
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0

    def get_config(self) -> dict:
        """Return Reticulum interface configuration for BT-PAN clients."""
        # Only add TCP interface in client mode
        if self.retcon_config["retcon"]["mode"] != "client":
            return {"plugin_interfaces": ""}

        # Add TCP server interface so phones can connect Sideband via BT-PAN
        interface_str = f"""
[[Bluetooth PAN TCP Server]]
  type = TCPServerInterface
  interface_enabled = True
  listen_ip = {self.PAN_IP}
  listen_port = 4242

"""
        return {
            "plugin_interfaces": interface_str
        }

    def init(self):
        """Initialize Bluetooth PAN on startup."""
        # Only initialize in client mode - transport nodes don't need user connections
        if self.retcon_config["retcon"]["mode"] != "client":
            logger.info("Bluetooth PAN disabled in transport mode")
            self._state = BluetoothState.UNCONFIGURED
            return

        logger.info("Initializing Bluetooth PAN plugin")
        self._state = BluetoothState.INITIALIZING

        bt_config = self.config  # bluetooth_pan section from config
        wifi_config = self.retcon_config["retcon"]["wifi"]

        # Get Bluetooth name from config or derive from WiFi SSID prefix
        self._bt_name = bt_config.get(
            "name",
            wifi_config.get("prefix", "RETCON") + "-BT"
        )

        try:
            # Step 1: Ensure Bluetooth service is running
            self._run_cmd("systemctl is-active bluetooth || systemctl start bluetooth", critical=True)
            time.sleep(1)

            # Step 2: Configure Bluetooth name and discoverability
            self._configure_bluetooth()

            # Step 3: Ensure systemd-networkd is handling pan0
            self._setup_pan_network()

            # Step 4: Start bt-network NAP service
            self._start_nap_service()

            self._state = BluetoothState.RUNNING
            self._start_time = time.time()
            logger.info(f"Bluetooth PAN initialized successfully as '{self._bt_name}'")

        except Exception as e:
            logger.error(f"Failed to initialize Bluetooth PAN: {e}")
            self._state = BluetoothState.FAILED

    def _configure_bluetooth(self):
        """Configure Bluetooth adapter for PAN."""
        logger.info(f"Configuring Bluetooth as '{self._bt_name}'")

        # Set discoverable and pairable via bluetoothctl
        self._run_bluetoothctl([
            "power on",
            f"system-alias {self._bt_name}",
            "discoverable on",
            "pairable on",
            "agent NoInputNoOutput",
            "default-agent",
        ])

    def _setup_pan_network(self):
        """Ensure pan0 bridge network is configured."""
        logger.info("Setting up PAN network configuration")

        # Check if pan0 netdev config exists
        netdev_path = "/etc/systemd/network/pan0.netdev"
        network_path = "/etc/systemd/network/pan0.network"

        # Create netdev file if missing
        try:
            with open(netdev_path, 'r') as f:
                pass  # File exists
        except FileNotFoundError:
            logger.info(f"Creating {netdev_path}")
            netdev_content = """[NetDev]
Name=pan0
Kind=bridge
"""
            with open(netdev_path, 'w') as f:
                f.write(netdev_content)

        # Create network file if missing
        try:
            with open(network_path, 'r') as f:
                pass  # File exists
        except FileNotFoundError:
            logger.info(f"Creating {network_path}")
            network_content = f"""[Match]
Name=pan0

[Network]
Address={self.PAN_IP}/24
DHCPServer=yes

[DHCPServer]
PoolOffset=10
PoolSize=50
DNS={self.PAN_IP}
"""
            with open(network_path, 'w') as f:
                f.write(network_content)

        # Reload systemd-networkd
        self._run_cmd("systemctl daemon-reload")
        self._run_cmd("systemctl restart systemd-networkd || true")

    def _start_nap_service(self):
        """Start the Bluetooth NAP service."""
        logger.info("Starting Bluetooth NAP service")

        # Check if bt-network is available
        if not self._run_cmd("which bt-network"):
            logger.warning("bt-network not found, trying bluez-tools package")
            # bt-network comes from bluez-tools package

        # Create systemd service file if missing
        service_path = "/etc/systemd/system/bt-network.service"
        try:
            with open(service_path, 'r') as f:
                pass  # File exists
        except FileNotFoundError:
            logger.info(f"Creating {service_path}")
            service_content = """[Unit]
Description=Bluetooth Network Access Point
After=bluetooth.service
Requires=bluetooth.service

[Service]
Type=simple
ExecStart=/usr/bin/bt-network -s nap pan0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
            with open(service_path, 'w') as f:
                f.write(service_content)
            self._run_cmd("systemctl daemon-reload")

        # Enable and start the service
        self._run_cmd("systemctl enable bt-network")
        self._run_cmd("systemctl restart bt-network", critical=True)

    def _verify_health(self) -> bool:
        """Verify Bluetooth PAN is functioning."""
        # Check bluetooth service
        if not self._run_cmd("systemctl is-active bluetooth"):
            logger.warning("Bluetooth service not active")
            return False

        # Check bt-network service
        if not self._run_cmd("systemctl is-active bt-network"):
            logger.warning("bt-network service not active")
            return False

        # Check pan0 interface exists
        if not self._run_cmd(f"ip link show {self.PAN_INTERFACE} 2>/dev/null"):
            # pan0 only appears when a device connects, so this is not critical
            logger.debug("pan0 interface not present (no devices connected)")

        return True

    def get_status(self) -> dict:
        """Return Bluetooth PAN status for web UI and admin interface."""
        # Get connected devices count
        connected_count = 0
        try:
            result = subprocess.run(
                "bluetoothctl devices Connected",
                shell=True,
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                output = result.stdout.decode().strip()
                if output:
                    connected_count = len(output.split('\n'))
        except Exception:
            pass

        uptime = None
        if self._start_time:
            uptime = int(time.time() - self._start_time)

        return {
            "state": self._state.value,
            "bt_name": self._bt_name,
            "pan_ip": self.PAN_IP,
            "connected_devices": connected_count,
            "uptime_seconds": uptime,
        }

    async def loop(self):
        """Periodic maintenance loop."""
        if self._state == BluetoothState.FAILED:
            return

        if self._state == BluetoothState.UNCONFIGURED:
            return

        # Health check
        if not self._verify_health():
            logger.warning("Bluetooth PAN health check failed")
            self._state = BluetoothState.DEGRADED
            # Try to restart services
            self._run_cmd("systemctl restart bluetooth")
            time.sleep(2)
            self._run_cmd("systemctl restart bt-network")
            return

        if self._state == BluetoothState.DEGRADED and self._verify_health():
            self._state = BluetoothState.RUNNING
            logger.info("Bluetooth PAN recovered")

        # Log status
        status = self.get_status()
        if status["connected_devices"] > 0:
            logger.info(f"Bluetooth PAN: {status['connected_devices']} device(s) connected")
