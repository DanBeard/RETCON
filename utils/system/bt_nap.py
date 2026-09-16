#!/bin/bash
# RETCON Bluetooth PAN (NAP) server — optional, opt-in via the LXMF admin
# console (`btpan on`) or by starting retcon-bt-nap.service once.
#
# Gives a wireless "console" experience when the node's wifi is an IBSS
# (no AP for phones to join): Android/Linux/macOS/Windows clients pair,
# join the PAN, get DHCP from dnsmasq on br-bt, and reach meshchat at
# retcon.local. NOTE: iPhones cannot join a Bluetooth PAN (Apple dropped
# PAN-client support) — they should use the USB cable instead.
#
# 10.56.0.1/24 on br-bt; USB gadget uses 10.55.0.1/24, AP shared uses
# 10.42.0.1 or 10.<mac-derived>.1 — no overlaps.
set -euo pipefail

BRIDGE=br-bt
SUBNET=10.56.0.1/24

# bridge for bnep devices
ip link add "$BRIDGE" type bridge 2>/dev/null || true
ip addr show "$BRIDGE" | grep -q "$SUBNET" || ip addr add "$SUBNET" dev "$BRIDGE"
ip link set "$BRIDGE" up

# NAP server via bluez dbus (NetworkServer1.Register("nap", bridge))
exec python3 - <<'PYEOF'
import dbus, dbus.service, GLib

BUS = dbus.SystemBus()

def register_nap():
    bluez = dbus.Interface(
        BUS.get_object("org.bluez", "/org/bluez"),
        "org.freedesktop.DBus.ObjectManager",
    )
    managed = bluez.GetManagedObjects()
    for path, ifaces in managed.items():
        if "org.bluez.NetworkServer1" in ifaces:
            server = dbus.Interface(
                BUS.get_object("org.bluez", path),
                "org.bluez.NetworkServer1",
            )
            server.Register("nap", "br-bt")
            print("NAP registered on br-bt")
            return True
    print("no NetworkServer1 found (bluetoothd running? adapter present?)")
    return False

if not register_nap():
    raise SystemExit(1)

loop = GLib.MainLoop()
# bluez keeps the NAP registration as long as our dbus connection holds it
try:
    loop.run()
except KeyboardInterrupt:
    pass
PYEOF