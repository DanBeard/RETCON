#!/usr/bin/env bash
#
# RETCON Image Builder
# Builds a customized Raspberry Pi image using rpi-image-gen
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

pathadd() {
    if [ -d "$1" ] && [[ ":$PATH:" != *":$1:"* ]]; then
        PATH="${PATH:+"$PATH:"}$1"
    fi
}

# =============================================================================
# ASCII Art Banner
# =============================================================================

cat << EOF

 000000ba   00000000b d000000P  a00000b.  .00000.  000000ba
 00    \`0b  00           00    d0'   \`00 d0'   \`0b 00    \`0b
a00aaaa0P' a00aaaa       00    00        00     00 00     00
 00   \`0b.  00           00    00        00     00 00     00
 00     00  00           00    Y0.   .00 Y0.   .0P 00     00
 dP     dP  00000000P    dP     Y00000P'  \`0000P'  dP     dP
ooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo

EOF

# =============================================================================
# Main Script
# =============================================================================

print_header "RETCON Image Builder"

log_info "This utility builds a customized RETCON Raspberry Pi image."
log_info "Target: Raspberry Pi 4/5 (ARM64)"
echo ""
log_warn "Ensure you have run ./install_prereqs.sh first!"
log_warn "This process may take 15-30 minutes depending on your hardware."
echo ""
log_info "The build uses rpi-image-gen and is Debian-dependent."
log_info "Recommended: Run on RPi4/RPi5 (x86 works with QEMU emulation)."

# -----------------------------------------------------------------------------
print_section "Configuration"
# -----------------------------------------------------------------------------

PROFILES_DIR="$SCRIPTPATH/retcon_profiles"
ACTIVE_FILE="$PROFILES_DIR/active"

# Get current active config name by comparing checksums
get_active_config_name() {
    if [ ! -f "$ACTIVE_FILE" ]; then
        echo ""
        return 1
    fi

    local active_sum=$(md5sum "$ACTIVE_FILE" | cut -d' ' -f1)
    for config in "$PROFILES_DIR"/*.config; do
        local config_sum=$(md5sum "$config" | cut -d' ' -f1)
        if [ "$active_sum" = "$config_sum" ]; then
            basename "$config"
            return 0
        fi
    done
    echo "custom"
    return 0
}

# Find available config files
CONFIG_FILES=()
CONFIG_NAMES=()
for config in "$PROFILES_DIR"/*.config; do
    if [ -f "$config" ]; then
        CONFIG_FILES+=("$config")
        CONFIG_NAMES+=("$(basename "$config")")
    fi
done

if [ ${#CONFIG_FILES[@]} -eq 0 ]; then
    log_error "No config files found in $PROFILES_DIR"
    log_info "Expected *.config files (e.g., default.config)"
    exit 1
fi

# Check if active file exists but is not writable (wrong permissions)
if [ -f "$ACTIVE_FILE" ] && [ ! -w "$ACTIVE_FILE" ]; then
    log_error "Config file has incorrect permissions: $ACTIVE_FILE"
    log_info "Fix with: sudo rm $ACTIVE_FILE"
    log_info "Then re-run this script to select a config."
    exit 1
fi

# Handle config selection
if [ -f "$ACTIVE_FILE" ]; then
    # Active config exists
    CURRENT_CONFIG=$(get_active_config_name)
    if [ "$CURRENT_CONFIG" = "custom" ]; then
        log_info "Current config: custom (modified)"
    else
        log_info "Current config: $CURRENT_CONFIG"
    fi

    echo ""
    echo "Available profiles:"
    log_warn "Selecting a new profile will OVERWRITE the active config."

    prompt_menu "true" "${CONFIG_NAMES[@]}"

    if [ $MENU_SELECTION -eq 0 ]; then
        log_success "Using current config"
    else
        SELECTED_INDEX=$((MENU_SELECTION - 1))
        SELECTED_FILE="${CONFIG_FILES[$SELECTED_INDEX]}"
        SELECTED_NAME="${CONFIG_NAMES[$SELECTED_INDEX]}"

        if cp "$SELECTED_FILE" "$ACTIVE_FILE"; then
            log_success "Activated config: $SELECTED_NAME"
        else
            log_error "Failed to copy config file"
            exit 1
        fi
    fi
else
    # No active config - must select one
    log_warn "No active config found. You must select one."

    echo ""
    echo "Available profiles:"

    prompt_menu "false" "${CONFIG_NAMES[@]}"

    SELECTED_INDEX=$((MENU_SELECTION - 1))
    SELECTED_FILE="${CONFIG_FILES[$SELECTED_INDEX]}"
    SELECTED_NAME="${CONFIG_NAMES[$SELECTED_INDEX]}"

    if cp "$SELECTED_FILE" "$ACTIVE_FILE"; then
        log_success "Activated config: $SELECTED_NAME"
    else
        log_error "Failed to copy config file"
        exit 1
    fi
fi

echo ""
prompt_confirm "Continue with build?" || exit 0

# Track completed steps for summary
COMPLETED_STEPS=()
TOTAL_STEPS=4

# Ensure /usr/sbin is in path (required for non-root users)
pathadd "/usr/sbin"
pathadd "/sbin"

# -----------------------------------------------------------------------------
print_section "Environment Setup"
# -----------------------------------------------------------------------------

log_step 1 $TOTAL_STEPS "Preparing build directory..."
sudo rm -rf "$HOME/.retcon-build" || true
if mkdir -p "$HOME/.retcon-build"; then
    log_success "Created ~/.retcon-build/"
    COMPLETED_STEPS+=("Build environment")
else
    log_error "Failed to create build directory"
    exit 1
fi

cd "$HOME/.retcon-build"

# -----------------------------------------------------------------------------
print_section "Cloning rpi-image-gen"
# -----------------------------------------------------------------------------

log_step 2 $TOTAL_STEPS "Cloning rpi-image-gen repository..."
spinner_start "Cloning from github.com/raspberrypi/rpi-image-gen"
if git clone --quiet https://github.com/raspberrypi/rpi-image-gen.git 2>/dev/null; then
    spinner_stop
    log_success "Repository cloned successfully"
    COMPLETED_STEPS+=("rpi-image-gen cloned")
else
    spinner_stop
    log_error "Failed to clone repository"
    log_info "Check your network connection"
    log_info "Manual: git clone https://github.com/raspberrypi/rpi-image-gen.git"
    exit 1
fi

cd rpi-image-gen

log_step 3 $TOTAL_STEPS "Checking out stable release v1.0.0..."
if git checkout v1.0.0 > /dev/null 2>&1; then
    log_success "Switched to tag v1.0.0"
    COMPLETED_STEPS+=("Version v1.0.0")
else
    log_error "Failed to checkout v1.0.0"
    exit 1
fi

# -----------------------------------------------------------------------------
print_section "Building Image"
# -----------------------------------------------------------------------------

log_step 4 $TOTAL_STEPS "Building RETCON image (this may take a while)..."
echo ""

if run_verbose "RETCON image build" ./build.sh -c retcon -D "$SCRIPTPATH/retcon_pi/" -o "$SCRIPTPATH/retcon_pi/retcon.options" -N retcon; then
    COMPLETED_STEPS+=("RETCON image built")
else
    print_failure_summary "Build Failed" "Image build process"
    log_error "The build process encountered an error."
    log_info "Check the output above for details."
    exit 1
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

print_summary "Build Complete!" "${COMPLETED_STEPS[@]}"

OUTPUT_PATH="$HOME/.retcon-build/rpi-image-gen/work/retcon/artefacts/retcon.img"
log_info "Output: $OUTPUT_PATH"
echo ""
log_info "Flash with: sudo dd if=$OUTPUT_PATH of=/dev/sdX bs=4M status=progress"
