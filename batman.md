# Plan: Replace wifi_mesh Plugin with batman-adv Mesh

## Summary

Replace the current `wifi_mesh` plugin (TCP backbone over AP/client WiFi) with a new `batman_mesh` plugin using batman-adv for true Layer 2 ad-hoc mesh networking on Raspberry Pis.

**User decisions:**
- Keep AP interface (uap0) for non-mesh-aware client devices
- Remove wifi_mesh plugin entirely (no fallback)
- Use auto-generated IPs from MAC (10.99.X.Y/16)

---

## Why batman-adv?

Current `wifi_mesh` problems:
- Hierarchical topology (client connects to one AP at a time)
- Single point of failure per link
- Complex scanning/reconnection logic
- TCP BackboneInterface overhead

batman-adv benefits:
- True mesh topology with multiple paths
- Automatic route optimization and self-healing
- Layer 2 mesh - all nodes appear on same Ethernet segment
- Reticulum AutoInterface works reliably on stable bat0

---

## Files to Modify/Create

### New Files
| File | Purpose |
|------|---------|
| `plugins/batman_mesh.py` | New batman-adv mesh plugin |
| `retcon_pi/retcon/meta/batman-mesh.yaml` | Pi image package config |
| `retcon_pi/retcon/setup-batman-mesh` | Pi image setup script |

### Files to Modify
| File | Changes |
|------|---------|
| `retcon_profiles/default.config` | Replace `[[wifi_mesh]]` with `[[batman_mesh]]` |
| `retcon_pi/profile/retcon` | Replace `wifi-mesh` with `batman-mesh` layer |
| `install_prereqs.sh` | Add `batctl` package |

### Files to Delete
| File | Reason |
|------|--------|
| `plugins/wifi_mesh.py` | Replaced by batman_mesh |
| `retcon_pi/retcon/meta/wifi-mesh.yaml` | Replaced by batman-mesh.yaml |
| `retcon_pi/retcon/setup-wifi-mesh` | Replaced by setup-batman-mesh |

---

## Implementation Steps

### Step 1: Create `plugins/batman_mesh.py`

New plugin implementing `RetconPlugin`:

```python
class BatmanMeshPlugin(RetconPlugin):
    PLUGIN_NAME = "batman_mesh"
```

Key functionality:
1. **`get_config()`** - Return Reticulum AutoInterface config for bat0
2. **`init()`** - Set up batman-adv mesh:
   - Load batman-adv kernel module
   - Configure wlan0 in ad-hoc (IBSS) mode
   - Join ad-hoc cell with fixed ESSID/cell-id from config
   - Add wlan0 to batman-adv (`batctl if add wlan0`)
   - Bring up bat0 interface
   - Assign IP from MAC (10.99.X.Y/16)
3. **`loop()`** - Log mesh status periodically (`batctl o`)

Reticulum interface (simple AutoInterface on bat0):
```
[[Batman Mesh AutoInterface]]
  type = AutoInterface
  interface_enabled = True
  mode = full
  devices = bat0
```

### Step 2: Create `retcon_pi/retcon/meta/batman-mesh.yaml`

Package list for Pi image:
```yaml
packages:
  - batctl              # batman-adv CLI utility
  - batman-adv-dkms     # kernel module
  - bridge-utils        # optional bridging
  - iw                  # WiFi config
  - wireless-tools
  - wireless-regdb
  - wpasupplicant
  - firmware-brcm80211
  - firmware-atheros
  - polkitd-pkla
  - policykit-1
  - dnsmasq-base
```

### Step 3: Create `retcon_pi/retcon/setup-batman-mesh`

Setup script run during image build:
1. Add `batman-adv` to `/etc/modules` for auto-load at boot
2. Keep udev rule for creating uap0 virtual AP interface
3. Set up polkit rules for NetworkManager control
4. Enable IP forwarding (`net.ipv4.ip_forward=1`)

### Step 4: Update `retcon_profiles/default.config`

Remove `[[wifi_mesh]]`, add:
```ini
[retcon_plugins]
  [[batman_mesh]]
    essid = "RETCON-MESH"    # Fixed ESSID for mesh (optional override)
    # Channel/freq inherited from [retcon][wifi][freq]
```

### Step 5: Update `retcon_pi/profile/retcon`

Change layer from `wifi-mesh` to `batman-mesh`.

### Step 6: Update `install_prereqs.sh`

Add batman-adv packages for local development:
```bash
apt-get install -y batctl
```

### Step 7: Delete old wifi_mesh files

- `plugins/wifi_mesh.py`
- `retcon_pi/retcon/meta/wifi-mesh.yaml`
- `retcon_pi/retcon/setup-wifi-mesh`

---

## Architecture After Implementation

```
     RETCON Transport A                RETCON Transport B
    ┌─────────────────┐               ┌─────────────────┐
    │   Reticulum     │               │   Reticulum     │
    │  (AutoInterface)│               │  (AutoInterface)│
    │       ↓         │               │       ↓         │
    │     bat0        │←── mesh ────→ │     bat0        │
    │  10.99.X.Y/16   │               │  10.99.X.Y/16   │
    │       ↓         │               │       ↓         │
    │  wlan0 (IBSS)   │               │  wlan0 (IBSS)   │
    └────────┬────────┘               └────────┬────────┘
             │                                  │
    ┌────────┴────────┐               ┌────────┴────────┐
    │   uap0 (AP)     │               │   uap0 (AP)     │
    │  10.42.0.1/24   │               │  10.42.0.1/24   │
    └────────┬────────┘               └────────┬────────┘
             │                                  │
      Client devices                     Client devices
      (phones, laptops)                  (phones, laptops)
```

---

## Key Technical Details

### Ad-hoc WiFi Setup Commands
```bash
modprobe batman-adv
ip link set wlan0 down
iw wlan0 set type ibss
ip link set wlan0 up
iw wlan0 ibss join RETCON-MESH 2462 fixed-freq 02:XX:XX:XX:XX:XX
batctl if add wlan0
ip link set bat0 up
ip addr add 10.99.X.Y/16 dev bat0
```

### Cell ID Generation
Generate consistent cell ID (BSSID) from ESSID hash so all nodes join same IBSS cell:
```python
cell_id = "02:" + sha256(essid)[:5].hex(":")
```

### IP Address Assignment
Derive from bat0 MAC address:
```python
mac_bytes = get_mac("bat0")
ip = f"10.99.{mac_bytes[-2]}.{mac_bytes[-1]}/16"
```

---

## Potential Challenges

1. **Simultaneous IBSS + AP**: Some WiFi drivers may not support both modes. Pi Zero 2W's Broadcom chip should work but needs testing.

2. **Ad-hoc mode support**: IBSS support varies by driver. Fallback: consider using batman-adv over WiFi in managed mode with WDS.

3. **MTU**: batman-adv adds ~32 bytes overhead. May need to adjust MTU on mesh interface.

---

## Testing Checklist

- [ ] Single node: bat0 interface comes up with IP
- [ ] Two nodes: `batctl o` shows peer originator
- [ ] Two nodes: Reticulum AutoInterface discovers peer
- [ ] Client device connects to uap0 AP
- [ ] Meshchat accessible from client device
- [ ] Node removal: mesh self-heals
- [ ] Reticulum traffic routes across mesh
