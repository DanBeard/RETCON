# How RETCON Mesh Networking Works

This document explains how RETCON uses batman-adv to create mesh networks. It's written for people familiar with traditional networking but new to mesh networking concepts.

## TL;DR

batman-adv creates a **virtual Layer 2 switch** that spans multiple physical devices over WiFi. Every node on the mesh appears to be on the same Ethernet segment - they can ARP for each other, broadcast works, etc. It's like having a really long Ethernet cable connecting all your Raspberry Pis together, except it's wireless and self-healing.

---

## The Stack

```
┌─────────────────────────────────────────────────────────┐
│  Applications (Meshchat, Reticulum, etc.)               │
├─────────────────────────────────────────────────────────┤
│  IP Layer (10.99.x.x addresses on bat0)                 │
├─────────────────────────────────────────────────────────┤
│  bat0 - Virtual Ethernet interface created by batman-adv│
├─────────────────────────────────────────────────────────┤
│  batman-adv kernel module (Layer 2 mesh routing)        │
├─────────────────────────────────────────────────────────┤
│  wlan0 - Physical WiFi in ad-hoc (IBSS) mode            │
├─────────────────────────────────────────────────────────┤
│  802.11 Radio (2.4GHz)                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Step 1: Ad-hoc WiFi (IBSS Mode)

Traditional WiFi uses **infrastructure mode**: there's an Access Point (AP) and clients connect to it. The AP is a central coordinator.

**Ad-hoc mode (IBSS - Independent Basic Service Set)** is different:
- No central AP
- All nodes are peers
- Any node can talk directly to any other node in radio range
- Nodes form a "cell" identified by:
  - **ESSID**: Network name (e.g., "RETCON-MESH")
  - **BSSID/Cell ID**: A MAC address identifying the cell (e.g., "02:aa:bb:cc:dd:ee")
  - **Frequency**: The WiFi channel (e.g., 2462 MHz = channel 11)

When RETCON starts, it does:
```bash
# Switch WiFi to ad-hoc mode
iw wlan0 set type ibss

# Join (or create) the mesh cell
iw wlan0 ibss join RETCON-MESH 2462 fixed-freq 02:aa:bb:cc:dd:ee
```

**Important**: All nodes must use the exact same ESSID, frequency, and cell ID to see each other. This is configured in your RETCON profile via `prefix`, `psk`, and `freq`.

### What you get with just ad-hoc WiFi

At this point, nodes within radio range of each other can send frames directly. But:
- ❌ No multi-hop routing (Node A can't reach Node C through Node B)
- ❌ No automatic path selection
- ❌ No handling of topology changes

This is where batman-adv comes in.

---

## Step 2: batman-adv (Layer 2 Mesh Routing)

**batman-adv** (Better Approach To Mobile Ad-hoc Networking - Advanced) is a Linux kernel module that adds mesh routing capabilities at Layer 2.

### What it creates

When you add an interface to batman-adv:
```bash
batctl if add wlan0    # Add the ad-hoc WiFi interface
ip link set bat0 up    # Bring up the virtual interface
```

batman-adv creates a virtual interface called `bat0`. This interface behaves like a port on a **virtual Ethernet switch** that spans all mesh nodes.

```
                        Virtual Switch (bat0)
     ┌────────────────────────────────────────────────────┐
     │                                                    │
  ┌──┴──┐          ┌──┴──┐          ┌──┴──┐          ┌──┴──┐
  │Node1│          │Node2│          │Node3│          │Node4│
  │bat0 │          │bat0 │          │bat0 │          │bat0 │
  └──┬──┘          └──┬──┘          └──┬──┘          └──┬──┘
     │                │                │                │
  ┌──┴──┐          ┌──┴──┐          ┌──┴──┐          ┌──┴──┐
  │wlan0│~~~~~~~~~~~│wlan0│~~~~~~~~~~│wlan0│~~~~~~~~~~│wlan0│
  └─────┘  Radio    └─────┘  Radio   └─────┘  Radio   └─────┘
```

From the perspective of anything using `bat0`, all nodes appear to be on the same Layer 2 network segment. You can:
- Assign IP addresses and ping between nodes
- Run any Layer 2 protocol (ARP works!)
- Use broadcast/multicast (batman-adv handles it efficiently)

### How routing works: OGMs

batman-adv nodes discover each other using **OGMs (Originator Messages)**:

1. Each node periodically broadcasts an OGM announcing itself
2. Neighboring nodes receive the OGM and rebroadcast it (with decremented TTL)
3. Each node builds a table of "originators" (other mesh nodes) and the best "next hop" to reach them

```
Node A's Originator Table:
┌─────────────┬───────────────┬─────────────┐
│ Originator  │ Next Hop      │ TQ (quality)│
├─────────────┼───────────────┼─────────────┤
│ Node B      │ Node B        │ 255 (direct)│
│ Node C      │ Node B        │ 200 (1 hop) │
│ Node D      │ Node B        │ 150 (2 hops)│
└─────────────┴───────────────┴─────────────┘
```

**TQ (Transmission Quality)** is batman-adv's metric for path quality. It starts at 255 and degrades based on:
- Number of hops
- Packet loss
- Link quality

batman-adv automatically selects the best path and adapts when topology changes (nodes move, join, or leave).

### Multi-hop example

```
[Node A] ~~~~ [Node B] ~~~~ [Node C] ~~~~ [Node D]
   │                                          │
   └──────── Can communicate! ────────────────┘

Node A sends a frame to Node D:
1. A looks up D in originator table → next hop is B
2. A sends frame to B (over ad-hoc WiFi)
3. B looks up D → next hop is C
4. B forwards to C
5. C looks up D → next hop is D (direct)
6. C delivers to D
```

The beauty: **applications on Node A just see Node D as being on the same Ethernet**. They don't know or care about the mesh hops.

---

## Step 3: IP Addressing (Without DHCP)

Once `bat0` exists as a virtual Ethernet interface, you need IP addresses to do anything useful at Layer 3. But there's a problem: **no DHCP server**.

In a traditional network, you'd have:
- A DHCP server that hands out unique IPs
- Or static assignment by an administrator

In a decentralized mesh, neither works well:
- No guaranteed "always on" node to run DHCP
- Manual assignment doesn't scale and requires coordination

### RETCON's Solution: Derive IP from MAC Address

RETCON uses a simple deterministic algorithm - derive the IP from the node's MAC address:

```python
def _assign_mesh_ip(self):
    # Get bat0's MAC address (e.g., "aa:bb:cc:dd:e3:7f")
    mac = get_mac("bat0")
    mac_bytes = bytes.fromhex(mac.replace(":", ""))

    # Use last 2 bytes of MAC for the IP
    # 10.99.{second-to-last-byte}.{last-byte}/16
    ip = f"10.99.{mac_bytes[-2]}.{mac_bytes[-1]}/16"

    # e.g., MAC aa:bb:cc:dd:e3:7f → IP 10.99.227.127/16
```

**Example mappings:**
```
MAC Address          →  IP Address
─────────────────────────────────────
aa:bb:cc:dd:00:01    →  10.99.0.1
aa:bb:cc:dd:01:42    →  10.99.1.66
aa:bb:cc:dd:e3:7f    →  10.99.227.127
aa:bb:cc:dd:ff:fe    →  10.99.255.254
```

### Why This Works

1. **MAC addresses are (supposed to be) globally unique** - manufacturers assign them from allocated ranges, so no two devices should have the same MAC.

2. **Deterministic** - the same node always gets the same IP. This is helpful for:
   - Debugging ("Node 10.99.42.17 is having issues")
   - Logs that make sense across reboots
   - No "lease expired" issues

3. **Zero coordination** - each node independently calculates its own IP. No network traffic needed, works even if the node is temporarily isolated.

4. **Works offline** - no dependency on any other node being available.

### Trade-offs and Limitations

| Pros | Cons |
|------|------|
| ✅ Zero configuration | ⚠️ Small collision probability |
| ✅ Zero coordination | ⚠️ IPs aren't human-memorable |
| ✅ Works offline | ⚠️ Only 65,534 possible addresses |
| ✅ Deterministic/stable | ⚠️ Can't "reserve" specific IPs |

### Collision Probability

Since we're only using 2 bytes of the MAC (16 bits = 65,536 possibilities), there's a chance two nodes could end up with the same IP. This is the [birthday problem](https://en.wikipedia.org/wiki/Birthday_problem):

| Nodes | Collision Probability |
|-------|----------------------|
| 10    | ~0.08% |
| 50    | ~1.9% |
| 100   | ~7.4% |
| 500   | ~85% |

For RETCON's target use case (tens of nodes at an event), this is perfectly acceptable. If you're deploying hundreds of nodes, you'd want a different strategy:
- Run DHCP on a known-stable node
- Use a distributed consensus protocol
- Manually assign from different /24 ranges per deployment

### The /16 Subnet

All mesh nodes share the `10.99.0.0/16` subnet, which means:
- Any node can talk to any other node directly (same broadcast domain)
- ARP works normally
- 65,534 usable addresses (10.99.0.1 - 10.99.255.254)

---

## Comparison to Traditional Networking

| Concept | Traditional | batman-adv Mesh |
|---------|-------------|-----------------|
| **Switching** | Physical switch, CAM table | Virtual switch across nodes, originator table |
| **Routing** | IP-level, routers, BGP/OSPF | Layer 2, OGMs, TQ metric |
| **IP assignment** | DHCP server or static | Derived from MAC address (no coordination) |
| **Discovery** | ARP within subnet | OGMs for mesh, ARP still works on bat0 |
| **Failover** | STP, VRRP, routing protocols | Automatic via OGM path selection |
| **Broadcast domain** | Physical switch/VLAN | Entire mesh (bat0 is one L2 segment) |

### Why Layer 2?

batman-adv operates at Layer 2 (Ethernet frames) rather than Layer 3 (IP packets). Benefits:

1. **Protocol agnostic**: Works with IPv4, IPv6, or any protocol that runs over Ethernet
2. **Transparent**: Applications don't need mesh awareness
3. **Simple addressing**: Just Ethernet MACs, no IP routing configuration
4. **Broadcast works**: Critical for protocols like Reticulum's AutoInterface discovery

---

## How RETCON Uses This

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                    batman-adv Mesh (bat0)                       │
│                     10.99.0.0/16                                │
│                                                                 │
│  ┌─────────┐         ┌─────────┐         ┌─────────┐           │
│  │ Node 1  │ ~~~~~~~ │ Node 2  │ ~~~~~~~ │ Node 3  │           │
│  │10.99.1.1│   WiFi  │10.99.2.2│   WiFi  │10.99.3.3│           │
│  └────┬────┘         └────┬────┘         └────┬────┘           │
│       │                   │                   │                 │
└───────┼───────────────────┼───────────────────┼─────────────────┘
        │                   │                   │
   ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
   │Bluetooth│         │Bluetooth│         │Bluetooth│
   │  PAN    │         │  PAN    │         │  PAN    │
   │(pan0)   │         │(pan0)   │         │(pan0)   │
   │192.168. │         │192.168. │         │192.168. │
   │  4.1    │         │  4.1    │         │  4.1    │
   └────┬────┘         └────┬────┘         └────┬────┘
        │                   │                   │
   ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
   │  Phone  │         │ Tablet  │         │  Phone  │
   │192.168. │         │192.168. │         │192.168. │
   │  4.10   │         │  4.11   │         │  4.12   │
   └─────────┘         └─────────┘         └─────────┘
```

### Reticulum Integration

Reticulum runs on top of this with an **AutoInterface** on `bat0`:

```ini
[[Batman Mesh AutoInterface]]
  type = AutoInterface
  interface_enabled = True
  devices = bat0
```

AutoInterface uses broadcast discovery on the `bat0` interface. Since all mesh nodes share the same Layer 2 segment, they discover each other automatically - even across multiple hops!

### Data Flow Example

User on phone connected to Node 1 sends a message to user on Node 3:

1. **Phone → Node 1**: Via Bluetooth PAN (192.168.4.x)
2. **Node 1 Reticulum**: Receives message, determines destination is on mesh
3. **Node 1 → Node 2 → Node 3**: batman-adv routes the Ethernet frame across the mesh
4. **Node 3 Reticulum**: Receives message, delivers to local user or forwards to their phone
5. **Node 3 → Phone**: Via Bluetooth PAN

The mesh routing is completely transparent to Reticulum - it just sees `bat0` as an Ethernet interface.

---

## Useful Commands

### Check mesh status
```bash
# See attached interfaces
batctl if

# See originator table (other mesh nodes)
batctl o

# See neighbors (direct radio contact)
batctl n

# See routing table
batctl rt
```

### Check ad-hoc WiFi
```bash
# See interface mode and cell
iw wlan0 info

# See connected stations (neighbors)
iw wlan0 station dump
```

### Check bat0 interface
```bash
# See IP address
ip addr show bat0

# Ping another mesh node
ping 10.99.2.2
```

---

## Further Reading

- [batman-adv documentation](https://www.open-mesh.org/projects/batman-adv/wiki)
- [Freifunk community](https://freifunk.net/) - German community mesh networks using batman-adv
- [Wireless Battle Mesh](https://battlemesh.org/) - Annual mesh networking testing event
