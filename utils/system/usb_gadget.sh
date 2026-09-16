#!/bin/bash
# RETCON USB gadget: the Zero's power/data cable becomes a USB ethernet NIC
# on the host (laptop). RNDIS for Windows/Android hosts, ECM for macOS and
# modern Linux/Windows — both bound as one device with two configs.
#
# Runs from retcon-usb-gadget.service (systemd, ConditionPathExists on the
# dwc2 overlay being active). Idempotent: re-running rebinds cleanly.
#
# Host-side experience: plug the Zero into a laptop's USB port → NIC appears
# → DHCP → browse retcon.local (meshchat + admin web UI) or ssh retcon@retcon.local.
#
# NOTE: only the middle USB port (the OTG/data port) carries data. A Zero
# powered through the PWR IN port will NOT enumerate as a gadget.
set -euo pipefail

GADGET=/sys/kernel/config/usb_gadget/retcon

modprobe libcomposite 2>/dev/null || true

if [ ! -d /sys/kernel/config/usb_gadget ]; then
    echo "configfs usb_gadget not available; is the dwc2 overlay loaded?" >&2
    exit 1
fi

# Tear down any previous binding
if [ -d "$GADGET" ]; then
    echo "" > "$GADGET/UDC" 2>/dev/null || true
    rm -rf "$GADGET"
fi

mkdir -p "$GADGET"
cd "$GADGET"

# Device descriptors (retcon's vendor-ish IDs: use a locally administered
# combination; VID 0x1d6b = Linux Foundation, PID 0x0104 = composite)
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x02   > bcdUSB
echo 0xEF   > bDeviceClass      # misc composite
echo 0x02   > bDeviceSubClass
echo 0x01   > bDeviceProtocol

mkdir -p strings/0x409
echo "retcon"          > strings/0x409/serialnumber
echo "RETCON"          > strings/0x409/manufacturer
echo "RETCON USB Link" > strings/0x409/product

# Function 1: RNDIS (Windows XP+ / Android built-in driver)
mkdir -p functions/rndis.usb0
# Function 2: ECM (macOS / Linux / Win10+ CDC ethernet)
mkdir -p functions/ecm.usb0

# Config 1: RNDIS-first (Windows picks this)
mkdir -p configs/c.1/strings/0x409
echo "RETCON RNDIS" > configs/c.1/strings/0x409/configuration
ln -sf functions/rndis.usb0 configs/c.1/

# Config 2: ECM-first (macOS/Linux pick this)
mkdir -p configs/c.2/strings/0x409
echo "RETCON ECM" > configs/c.2/strings/0x409/configuration
ln -sf functions/ecm.usb0 configs/c.2/

# MS OS descriptor so Windows auto-installs the RNDIS driver without a .inf
echo 1 > os_desc/use
echo 0xcd > os_desc/b_vendor_code
echo "MSFT100" > os_desc/qw_sign
mkdir -p functions/rndis.usb0/os_desc/interface.rndis
echo "RNDIS" > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
echo "5162001" > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id
ln -sf configs/c.1 os_desc/c.1

# Bind to the UDC (the dwc2 OTG controller)
UDC=$(ls /sys/class/udc 2>/dev/null | head -1 || true)
if [ -z "$UDC" ]; then
    echo "no UDC available (powered through PWR IN?); gadget not bound" >&2
    exit 0
fi
echo "$UDC" > "$GADGET/UDC"

echo "retcon usb gadget bound to $UDC (rndis + ecm)"