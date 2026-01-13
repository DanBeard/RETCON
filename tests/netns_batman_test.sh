#!/bin/bash
#
# Network namespace test for batman-adv mesh
#
# This script creates a virtual test environment using:
# - mac80211_hwsim kernel module for virtual WiFi interfaces
# - Network namespaces to isolate nodes
# - batman-adv for mesh networking
#
# Requirements:
# - Root privileges (sudo)
# - batman-adv kernel module
# - mac80211_hwsim kernel module
# - iw, batctl, ip utilities
#
# Usage: sudo ./tests/netns_batman_test.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test configuration
MESH_ESSID="RETCON-TEST-MESH"
MESH_FREQ=2412
MESH_CELL_ID="02:aa:bb:cc:dd:ee"

# Track created resources for cleanup
NETNS_CREATED=()
HWSIM_LOADED=false

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log_info "Cleaning up..."

    # Delete network namespaces
    for ns in "${NETNS_CREATED[@]}"; do
        ip netns del "$ns" 2>/dev/null || true
    done

    # Unload mac80211_hwsim if we loaded it
    if $HWSIM_LOADED; then
        modprobe -r mac80211_hwsim 2>/dev/null || true
    fi

    log_info "Cleanup complete"
}

trap cleanup EXIT

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_dependencies() {
    log_info "Checking dependencies..."

    local missing=()

    for cmd in ip iw batctl modprobe ping; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required commands: ${missing[*]}"
        exit 1
    fi

    # Check for required kernel modules
    if ! modprobe -n batman-adv 2>/dev/null; then
        log_error "batman-adv kernel module not available"
        exit 1
    fi

    if ! modprobe -n mac80211_hwsim 2>/dev/null; then
        log_error "mac80211_hwsim kernel module not available"
        log_warn "This module is needed for virtual WiFi testing"
        log_warn "Install with: apt-get install linux-modules-extra-\$(uname -r)"
        exit 1
    fi

    log_info "All dependencies satisfied"
}

setup_virtual_wifi() {
    log_info "Setting up virtual WiFi interfaces..."

    # Check if mac80211_hwsim is already loaded
    if lsmod | grep -q mac80211_hwsim; then
        log_warn "mac80211_hwsim already loaded, unloading first..."
        modprobe -r mac80211_hwsim || true
        sleep 1
    fi

    # Load mac80211_hwsim with 2 radios
    modprobe mac80211_hwsim radios=2
    HWSIM_LOADED=true

    # Wait for interfaces to appear
    sleep 2

    # Find the created interfaces
    WLAN0=$(iw dev | grep -A1 "phy#0" | grep Interface | awk '{print $2}' || echo "")
    WLAN1=$(iw dev | grep -A1 "phy#1" | grep Interface | awk '{print $2}' || echo "")

    if [ -z "$WLAN0" ] || [ -z "$WLAN1" ]; then
        log_error "Failed to create virtual WiFi interfaces"
        exit 1
    fi

    log_info "Created virtual interfaces: $WLAN0, $WLAN1"
}

create_netns() {
    local name=$1
    log_info "Creating network namespace: $name"

    ip netns add "$name"
    NETNS_CREATED+=("$name")
}

move_iface_to_netns() {
    local phy=$1
    local netns=$2

    log_info "Moving $phy to namespace $netns"
    iw phy "$phy" set netns name "$netns"
}

setup_batman_node() {
    local netns=$1
    local iface=$2
    local ip_addr=$3

    log_info "Configuring batman-adv node in $netns on $iface with IP $ip_addr"

    ip netns exec "$netns" bash -c "
        # Load batman-adv
        modprobe batman-adv

        # Configure interface for ad-hoc mode
        ip link set $iface down
        iw $iface set type ibss
        ip link set $iface up

        # Join the mesh cell
        iw $iface ibss join $MESH_ESSID $MESH_FREQ fixed-freq $MESH_CELL_ID

        # Add to batman-adv
        batctl if add $iface

        # Bring up bat0
        ip link set bat0 up

        # Assign IP
        ip addr add $ip_addr dev bat0
    "
}

run_tests() {
    log_info "Running tests..."

    echo ""
    echo "=== Node 1 Status ==="
    ip netns exec node1 bash -c "
        echo 'Interface info:'
        iw wlan0 info 2>/dev/null | head -5 || echo 'Could not get wlan0 info'
        echo ''
        echo 'Batman interfaces:'
        batctl if 2>/dev/null || echo 'No batman interfaces'
        echo ''
        echo 'bat0 IP:'
        ip addr show bat0 2>/dev/null | grep inet || echo 'No IP on bat0'
    "

    echo ""
    echo "=== Node 2 Status ==="
    ip netns exec node2 bash -c "
        echo 'Interface info:'
        iw wlan1 info 2>/dev/null | head -5 || echo 'Could not get wlan1 info'
        echo ''
        echo 'Batman interfaces:'
        batctl if 2>/dev/null || echo 'No batman interfaces'
        echo ''
        echo 'bat0 IP:'
        ip addr show bat0 2>/dev/null | grep inet || echo 'No IP on bat0'
    "

    echo ""
    log_info "Waiting for mesh to form (5 seconds)..."
    sleep 5

    echo ""
    echo "=== Node 1 Originators (Mesh Peers) ==="
    ip netns exec node1 batctl o 2>/dev/null || echo "No originators"

    echo ""
    echo "=== Node 2 Originators (Mesh Peers) ==="
    ip netns exec node2 batctl o 2>/dev/null || echo "No originators"

    echo ""
    echo "=== Connectivity Test: Node 1 -> Node 2 ==="
    if ip netns exec node1 ping -c 3 -W 2 10.99.0.2 >/dev/null 2>&1; then
        log_info "Ping test PASSED"
        PING_RESULT=0
    else
        log_error "Ping test FAILED"
        PING_RESULT=1
    fi

    echo ""
    echo "=== Connectivity Test: Node 2 -> Node 1 ==="
    if ip netns exec node2 ping -c 3 -W 2 10.99.0.1 >/dev/null 2>&1; then
        log_info "Reverse ping test PASSED"
        REVERSE_PING_RESULT=0
    else
        log_error "Reverse ping test FAILED"
        REVERSE_PING_RESULT=1
    fi

    return $((PING_RESULT + REVERSE_PING_RESULT))
}

main() {
    echo ""
    echo "=========================================="
    echo "  Batman-adv Network Namespace Test"
    echo "=========================================="
    echo ""

    check_root
    check_dependencies

    setup_virtual_wifi

    # Create network namespaces
    create_netns "node1"
    create_netns "node2"

    # Move WiFi interfaces to namespaces
    move_iface_to_netns "phy0" "node1"
    move_iface_to_netns "phy1" "node2"

    # Wait for interfaces to settle in new namespaces
    sleep 2

    # Find interface names within namespaces (they might have changed)
    IFACE1=$(ip netns exec node1 iw dev | grep Interface | awk '{print $2}' | head -1)
    IFACE2=$(ip netns exec node2 iw dev | grep Interface | awk '{print $2}' | head -1)

    log_info "Interfaces in namespaces: node1=$IFACE1, node2=$IFACE2"

    # Setup batman-adv on each node
    setup_batman_node "node1" "$IFACE1" "10.99.0.1/16"
    setup_batman_node "node2" "$IFACE2" "10.99.0.2/16"

    # Run the tests
    if run_tests; then
        echo ""
        echo -e "${GREEN}=========================================="
        echo "  ALL TESTS PASSED"
        echo -e "==========================================${NC}"
        exit 0
    else
        echo ""
        echo -e "${RED}=========================================="
        echo "  SOME TESTS FAILED"
        echo -e "==========================================${NC}"
        exit 1
    fi
}

main "$@"
