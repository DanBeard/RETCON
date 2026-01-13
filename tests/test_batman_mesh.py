"""
Unit tests for batman_mesh plugin.

These tests verify the logic of the batman_mesh plugin without requiring
actual hardware or root privileges. Hardware-specific functionality is
tested via the network namespace integration test.

Run with: pytest tests/test_batman_mesh.py -v
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.batman_mesh import BatmanMeshPlugin, MeshState


class TestMeshState:
    """Test the MeshState enum."""

    def test_all_states_exist(self):
        """Verify all expected states are defined."""
        assert MeshState.UNCONFIGURED.value == "unconfigured"
        assert MeshState.INITIALIZING.value == "initializing"
        assert MeshState.RUNNING.value == "running"
        assert MeshState.DEGRADED.value == "degraded"
        assert MeshState.FAILED.value == "failed"


class TestCellIdGeneration:
    """Test cell ID (BSSID) generation from ESSID."""

    @pytest.fixture
    def plugin(self):
        """Create a minimal plugin instance for testing."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        return plugin

    def test_cell_id_consistent(self, plugin):
        """Same ESSID should always produce same cell ID."""
        cell1 = plugin._generate_cell_id("RETCON-MESH")
        cell2 = plugin._generate_cell_id("RETCON-MESH")
        assert cell1 == cell2

    def test_cell_id_different_for_different_essid(self, plugin):
        """Different ESSIDs should produce different cell IDs."""
        cell1 = plugin._generate_cell_id("RETCON-MESH")
        cell2 = plugin._generate_cell_id("OTHER-MESH")
        assert cell1 != cell2

    def test_cell_id_locally_administered_bit(self, plugin):
        """Cell ID should have locally administered bit set (starts with 02:)."""
        cell_id = plugin._generate_cell_id("TEST-MESH")
        assert cell_id.startswith("02:")

    def test_cell_id_format(self, plugin):
        """Cell ID should be valid MAC address format."""
        cell_id = plugin._generate_cell_id("TEST-MESH")
        parts = cell_id.split(":")
        assert len(parts) == 6
        for part in parts:
            assert len(part) == 2
            int(part, 16)  # Should not raise


class TestFrequencyChannelConversion:
    """Test WiFi frequency/channel conversion."""

    @pytest.fixture
    def plugin(self):
        """Create a minimal plugin instance for testing."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        return plugin

    def test_freq_to_channel_known_values(self, plugin):
        """Test known frequency to channel mappings."""
        assert plugin._freq_to_channel(2412) == 1
        assert plugin._freq_to_channel(2437) == 6
        assert plugin._freq_to_channel(2462) == 11
        assert plugin._freq_to_channel(2484) == 14

    def test_channel_to_freq_known_values(self, plugin):
        """Test known channel to frequency mappings."""
        assert plugin._channel_to_freq(1) == 2412
        assert plugin._channel_to_freq(6) == 2437
        assert plugin._channel_to_freq(11) == 2462
        assert plugin._channel_to_freq(14) == 2484

    def test_freq_to_channel_unknown_defaults_to_11(self, plugin):
        """Unknown frequency should default to channel 11."""
        assert plugin._freq_to_channel(9999) == 11
        assert plugin._freq_to_channel(0) == 11

    def test_channel_to_freq_unknown_defaults_to_2462(self, plugin):
        """Unknown channel should default to 2462 (channel 11)."""
        assert plugin._channel_to_freq(99) == 2462
        assert plugin._channel_to_freq(0) == 2462

    def test_round_trip_conversion(self, plugin):
        """Converting freq->channel->freq should give original value."""
        for freq in [2412, 2437, 2462]:
            channel = plugin._freq_to_channel(freq)
            result = plugin._channel_to_freq(channel)
            assert result == freq


class TestStateManagement:
    """Test state machine transitions and recovery logic."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin with mocked config."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        plugin._state = MeshState.UNCONFIGURED
        plugin._recovery_attempts = 0
        plugin._start_time = None
        plugin._iface = "wlan0"
        plugin._essid = "TEST-MESH"
        plugin._channel = 11
        plugin._cell_id = "02:aa:bb:cc:dd:ee"
        plugin._ap_iface = None
        return plugin

    def test_initial_state(self, plugin):
        """Plugin should start in UNCONFIGURED state."""
        plugin._state = MeshState.UNCONFIGURED
        assert plugin._state == MeshState.UNCONFIGURED
        assert plugin._recovery_attempts == 0

    def test_max_recovery_attempts_defined(self, plugin):
        """MAX_RECOVERY_ATTEMPTS should be defined."""
        assert hasattr(BatmanMeshPlugin, 'MAX_RECOVERY_ATTEMPTS')
        assert BatmanMeshPlugin.MAX_RECOVERY_ATTEMPTS == 5

    def test_recovery_increments_counter(self, plugin):
        """Recovery attempt should increment counter."""
        plugin._recovery_attempts = 0
        plugin._state = MeshState.DEGRADED

        # Mock _cleanup_mesh and _setup_batman_mesh to avoid actual execution
        with patch.object(plugin, '_cleanup_mesh'):
            with patch.object(plugin, '_setup_batman_mesh', side_effect=RuntimeError("Test")):
                plugin._attempt_recovery()

        assert plugin._recovery_attempts == 1

    def test_recovery_fails_after_max_attempts(self, plugin):
        """After MAX_RECOVERY_ATTEMPTS, state should become FAILED."""
        plugin._recovery_attempts = BatmanMeshPlugin.MAX_RECOVERY_ATTEMPTS
        plugin._state = MeshState.DEGRADED

        plugin._attempt_recovery()

        assert plugin._state == MeshState.FAILED

    def test_successful_recovery_resets_counter(self, plugin):
        """Successful recovery should reset the counter."""
        plugin._recovery_attempts = 3
        plugin._state = MeshState.DEGRADED

        with patch.object(plugin, '_cleanup_mesh'):
            with patch.object(plugin, '_setup_batman_mesh'):  # Success
                plugin._attempt_recovery()

        assert plugin._state == MeshState.RUNNING
        assert plugin._recovery_attempts == 0


class TestGetStatus:
    """Test status reporting for web UI."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin with mocked config."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        plugin._state = MeshState.RUNNING
        plugin._recovery_attempts = 0
        plugin._start_time = 1000.0  # Mock start time
        plugin._iface = "wlan0"
        plugin._essid = "TEST-MESH"
        plugin._channel = 11
        plugin._cell_id = "02:aa:bb:cc:dd:ee"
        plugin._ap_iface = None
        return plugin

    @patch('plugins.batman_mesh.subprocess.run')
    @patch('plugins.batman_mesh.ni.ifaddresses')
    @patch('plugins.batman_mesh.time.time')
    def test_get_status_returns_dict(self, mock_time, mock_ifaddresses, mock_run, plugin):
        """get_status should return a dictionary with expected keys."""
        mock_time.return_value = 1060.0  # 60 seconds after start
        mock_run.return_value = MagicMock(returncode=1, stdout=b"")  # No peers
        mock_ifaddresses.side_effect = Exception("No interface")

        status = plugin.get_status()

        assert isinstance(status, dict)
        assert "state" in status
        assert "peer_count" in status
        assert "bat0_ip" in status
        assert "interface" in status
        assert "recovery_attempts" in status
        assert "max_recovery_attempts" in status
        assert "uptime_seconds" in status

    @patch('plugins.batman_mesh.subprocess.run')
    @patch('plugins.batman_mesh.ni.ifaddresses')
    @patch('plugins.batman_mesh.time.time')
    def test_get_status_state_value(self, mock_time, mock_ifaddresses, mock_run, plugin):
        """get_status should report correct state."""
        mock_time.return_value = 1060.0
        mock_run.return_value = MagicMock(returncode=1, stdout=b"")
        mock_ifaddresses.side_effect = Exception("No interface")

        plugin._state = MeshState.RUNNING
        status = plugin.get_status()
        assert status["state"] == "running"

        plugin._state = MeshState.FAILED
        status = plugin.get_status()
        assert status["state"] == "failed"

    @patch('plugins.batman_mesh.subprocess.run')
    @patch('plugins.batman_mesh.ni.ifaddresses')
    @patch('plugins.batman_mesh.time.time')
    def test_get_status_uptime(self, mock_time, mock_ifaddresses, mock_run, plugin):
        """get_status should calculate uptime correctly."""
        mock_time.return_value = 1060.0  # 60 seconds after start
        mock_run.return_value = MagicMock(returncode=1, stdout=b"")
        mock_ifaddresses.side_effect = Exception("No interface")

        status = plugin.get_status()
        assert status["uptime_seconds"] == 60


class TestRunCmd:
    """Test command execution helper."""

    @pytest.fixture
    def plugin(self):
        """Create a minimal plugin instance for testing."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        return plugin

    @patch('plugins.batman_mesh.subprocess.run')
    def test_run_cmd_success(self, mock_run, plugin):
        """Successful command should return True."""
        mock_run.return_value = MagicMock(returncode=0)

        result = plugin._run_cmd("echo test")
        assert result is True

    @patch('plugins.batman_mesh.subprocess.run')
    def test_run_cmd_failure(self, mock_run, plugin):
        """Failed command should return False."""
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error")

        result = plugin._run_cmd("false")
        assert result is False

    @patch('plugins.batman_mesh.subprocess.run')
    def test_run_cmd_critical_raises(self, mock_run, plugin):
        """Critical command failure should raise RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr=b"error", stdout=b"")

        with pytest.raises(RuntimeError):
            plugin._run_cmd("false", critical=True)


class TestForceRestart:
    """Test force_restart functionality."""

    @pytest.fixture
    def plugin(self):
        """Create a plugin with mocked config."""
        plugin = BatmanMeshPlugin.__new__(BatmanMeshPlugin)
        plugin._state = MeshState.FAILED
        plugin._recovery_attempts = 5
        plugin._iface = "wlan0"
        plugin._essid = "TEST-MESH"
        plugin._channel = 11
        plugin._cell_id = "02:aa:bb:cc:dd:ee"
        return plugin

    def test_force_restart_resets_counter(self, plugin):
        """force_restart should reset recovery counter."""
        with patch.object(plugin, '_attempt_recovery'):
            plugin.force_restart()

        assert plugin._recovery_attempts == 0

    def test_force_restart_sets_degraded_state(self, plugin):
        """force_restart should set state to DEGRADED before recovery."""
        with patch.object(plugin, '_attempt_recovery'):
            plugin.force_restart()

        # State was set to DEGRADED before _attempt_recovery was called
        # Since we mocked _attempt_recovery, state remains DEGRADED
        assert plugin._state == MeshState.DEGRADED
