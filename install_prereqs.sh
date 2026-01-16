#!/usr/bin/env bash
#
# RETCON Prerequisites Installer
# Installs dependencies required for building RETCON images
#

# Get script directory
SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
cd "$SCRIPTPATH"

# Source shared utilities
source "${SCRIPTPATH}/scripts/shell_utils.sh" || {
    echo "ERROR: Could not load shell utilities from ${SCRIPTPATH}/scripts/shell_utils.sh"
    exit 1
}

# =============================================================================
# Main Script
# =============================================================================

print_header "RETCON Prerequisites Installer"

log_info "This will install RETCON dependencies and configuration files."
echo ""
log_warn "This script is designed for Debian-based systems."
log_warn "Other Linux distributions may require manual adjustments."
echo ""
log_info "sudo is required for package installation."
log_info "Examine the script before running to ensure compatibility."
echo ""

prompt_confirm "Continue with installation?" || exit 0

# Check for root privileges
check_root

# Track completed steps for summary
COMPLETED_STEPS=()
TOTAL_STEPS=5

# -----------------------------------------------------------------------------
print_section "System Update"
# -----------------------------------------------------------------------------

log_step 1 $TOTAL_STEPS "Updating package lists..."
spinner_start "Running apt update"
if sudo apt update > /dev/null 2>&1; then
    spinner_stop
    log_success "Package lists updated"
    COMPLETED_STEPS+=("Package lists updated")
else
    spinner_stop
    log_error "Failed to update package lists"
    log_info "Check your network connection and /etc/apt/sources.list"
    exit 1
fi

log_step 2 $TOTAL_STEPS "Upgrading installed packages..."
spinner_start "Running apt upgrade"
if sudo apt upgrade -y > /dev/null 2>&1; then
    spinner_stop
    log_success "System packages upgraded"
    COMPLETED_STEPS+=("System packages upgraded")
else
    spinner_stop
    log_error "Failed to upgrade packages"
    exit 1
fi

# -----------------------------------------------------------------------------
print_section "Core Dependencies"
# -----------------------------------------------------------------------------

log_step 3 $TOTAL_STEPS "Installing Python and development tools..."
PYTHON_PACKAGES=(
    git
    python3-pip
    python3-venv
    curl
    dbus
    libdbus-glib-1-dev
    libdbus-1-dev
    jq
    batctl
)
spinner_start "Installing Python packages"
if apt_install "${PYTHON_PACKAGES[@]}" > /dev/null 2>&1; then
    spinner_stop
    log_success "Python and development tools installed"
    COMPLETED_STEPS+=("Python environment")
else
    spinner_stop
    log_error "Failed to install Python packages"
    exit 1
fi

log_step 4 $TOTAL_STEPS "Installing rpi-image-gen dependencies..."
BUILD_PACKAGES=(
    coreutils
    zip
    dosfstools
    e2fsprogs
    grep
    rsync
    genimage
    mtools
    mmdebstrap
    bdebstrap
    podman
    crudini
    zstd
    pv
    uidmap
    python-is-python3
    dbus-user-session
    btrfs-progs
    dctrl-tools
    uuid-runtime
)
spinner_start "Installing build dependencies"
if apt_install "${BUILD_PACKAGES[@]}" > /dev/null 2>&1; then
    spinner_stop
    log_success "Build dependencies installed"
    COMPLETED_STEPS+=("Build dependencies")
else
    spinner_stop
    log_error "Failed to install build dependencies"
    exit 1
fi

log_step 5 $TOTAL_STEPS "Installing QEMU emulation support..."
QEMU_PACKAGES=(
    qemu-user-static
    binfmt-support
)
spinner_start "Installing QEMU packages"
if apt_install "${QEMU_PACKAGES[@]}" > /dev/null 2>&1; then
    spinner_stop
    log_success "QEMU emulation support installed"
    COMPLETED_STEPS+=("QEMU emulation")
else
    spinner_stop
    log_error "Failed to install QEMU packages"
    exit 1
fi

# Clean up unnecessary packages
spinner_start "Cleaning up"
sudo apt autoremove -y > /dev/null 2>&1
spinner_stop

# -----------------------------------------------------------------------------
print_section "Configuration"
# -----------------------------------------------------------------------------

export ACTIVE_CONFIG="$SCRIPTPATH/retcon_profiles/active"
if [ -f "$ACTIVE_CONFIG" ]; then
    log_info "Active config detected - not overwriting"
else
    log_info "No active config found"
    if cp "$SCRIPTPATH/retcon_profiles/default.config" "$ACTIVE_CONFIG"; then
        log_success "Copied default.config to active"
        COMPLETED_STEPS+=("Configuration files")
    else
        log_error "Failed to copy default config"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

print_summary "Installation Complete" "${COMPLETED_STEPS[@]}"

log_info "Next step: Run ./build_retcon.sh to create your RETCON image"
