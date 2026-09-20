# RETCON on crns — integration notes

RETCON's mesh now runs on **crns** (`~/crns`), a clean-slate C++20
implementation of Reticulum/LXMF aimed at resource-constrained hardware.
This note documents the architecture of the swap, what changed in crns to
make it possible, and what is deliberately still python rns.

## Architecture

```
+----------------------------------------------------------+
| meshchat (python rns, unchanged app)                      |
|   joins over TCP loopback: 127.0.0.1:4243 (HDLC)          |
+---------------------------+------------------------------ ^
                            |                              |
+---------------------------v------------------------------+----------------+
| ONE crns host (python binding over libcrns.so)                            |
|  - owns every interface in ~/.reticulum/config (same file format!)        |
|  - transport forwarding (enable_transport from config)                    |
|  - LXMF admin console destination (utils/admin.py)                        |
+---------------------------------------------------------------------------+
| crnsd-compatible config parser + interface bring-up (libcrns_host)        |
|   UDP / TCPClient / TCPServer / RNodeInterface(serial) / IFAC             |
+---------------------------------------------------------------------------+
```

Why one process owns everything: crns deliberately has **no
shared-instance IPC** (PHILOSOPHY.md §67 — "one mesh attachment per app",
no IPC). RETCON's original design leaned on python rns's shared-instance
socket hand-off so that the transport, admin console and meshchat could all
share one `~/.reticulum`. On crns that knob doesn't exist, so the mesh is
one host process, and other local apps join it like remote peers do — over
a TCP interface. The wire format is the same HDLC-over-TCP framing python
rns speaks (`demo_rns_tcp_bidi` proves crns ↔ python rns interop live).

### Who runs what

| Component | Stack | Notes |
|---|---|---|
| mesh transport + interfaces | **crns** (`libcrns_host` loop thread, owned by the admin console process) | reads `~/.reticulum/config` unchanged; forwarding per `enable_transport` |
| RETCON LXMF admin console | **crns python binding** | `utils/admin.py`, identity persisted at `~/retcon/storage/identity` |
| meshchat | **python rns + lxmf** (unchanged) | own config dir `~/.meshchat-rns` with a single `TCPClientInterface` → `127.0.0.1:4243`; joins the mesh over the crns host's loopback listener |
| rnsd / rnstatus / rnsh | replaced | crnsd is built by the installer but not run by RETCON; `status` comes from the binding's path/announce feed inside the admin console; rnsh is not available on crns yet (no probe responder) |

## The crns branch: `retcon/posix-build-fixes`

crnsd reads rnsd configs, but RETCON's generated configs use keys that only
python rns understood. The branch (`ssh://git@192.168.0.2:2222/dbeard/crns.git`,
branch `retcon/posix-build-fixes`) adds, all in host glue (`host/`), no core
changes:

- **`port` key** — python rns maps BackboneInterface's `port` to
  `listen_port` (server) and `target_port` (client); same mapping here. A
  path-shaped value (`/dev/...`) binds to the RNode-serial meaning instead,
  mirroring how RNodeInterface spells the device path. Post-load validation
  re-checks the pairing.
- **`listen_on` key** — BackboneInterface's spelling of `listen_ip`.
- **`device` key** — for TCP servers, resolved at post-load to the kernel
  interface's first IPv4 address (getifaddrs), the host-side spelling of
  python's `TCPServerInterface.get_address_for_if`. Unresolvable device →
  hard error, same as python. Cleared once resolved.
- **`RNodeInterface` sections** — `port` (device path), `frequency`,
  `bandwidth`, `txpower`, `spreadingfactor`, `codingrate` →
  `SerialByteStream` (115200 8N1) + `init_radio` + KISS
  `FullCommandByte` framer (mtu 508). Removed from `HARD_REJECT_TYPES`.
- Tests: 663 doctest cases green (device resolution + failure,
  `listen_on`, `port` disambiguation, RNode parse/validate);
  `check-forbidden.sh` + pre-commit green.

## Data-path details RETCON now owns

- **LXMF announce app_data**: python LXMF rides the display name in the
  announce's app_data as msgpack peer_data
  `[display_name, stamp_cost, [SF_COMPRESSION]]`
  (`LXMRouter.get_announce_app_data`). crns's `announce()` takes raw
  app_data bytes, so RETCON packs that array itself
  (`utils/admin.py:pack_display_name_app_data`) using `msgpack`.
- **meshchat config isolation**: `~/.meshchat-rns/config` holds a single
  TCP client to the crns host's loopback listener (port 4243), created by
  `install_retcon_locally.sh`; `meshchat_handler.py` launches meshchat with
  `--reticulum-config-dir $HOME/.meshchat-rns`.
- **Identity**: the admin console identity persists via the binding's
  `register_destination("lxmf.delivery", identity_file=...)`, so the node's
  destination hash survives reboots (fleet trust preserved).
- **rnsd restart**: RETCON's `restart_rnsd()` now restarts the admin
  console process, which tears down and re-creates the whole crns host
  (interfaces included) — the closest analogue to the old shared-instance
  re-load, and enough for the wifi-mesh plugin's "config changed, reboot
  Reticulum" flow.

## Build + vendoring (`install_retcon_locally.sh`)

1. clone crns (repo/ref overridable with `CRNS_REPO` / `CRNS_REF`)
2. `cmake -DCRNS_BUILD_SHARED=ON -DCRNS_WITH_BEARSSL=ON` → `libcrns.so`
3. vendor `libcrns.so*` to `crns_lib/` and the pure-python
   `python/crns` package to `python_packages/crns`
4. sanity-import: `import crns; crns.abi_version()` — expect 2.2.0
   (W-series: store seam, browser profile; §102 auto-prove on
   register_destination — `prove_all` kwarg is gone, prove is the
   default with `set_proof_strategy` to override)

`CRNS_LIBRARY` is exported before anything imports `crns`, so the binding
dlopens the freshly built library.

## What is deliberately NOT swapped (yet)

- **meshchat stays python rns.** It is a third-party app; rewriting it
  against the crns binding is a separate project.
- **crnsd is built but not run.** RETCON's single-process host covers
  transport + application; crnsd (the standalone daemon) remains available
  for headless deployments, but RETCON doesn't launch it.
- **rnsh remote shell** — unavailable on crns (no probe responder). The
  `rnsh_admins` config key is still honoured but logs a notice.
- **Nomadnet** stays python rns (same shared-socket reasoning as meshchat;
  joins via the loopback listener when configured).

## POSIX build recipe (verified)

```bash
cmake -S . -B build -DCRNS_BUILD_SHARED=ON -DCRNS_WITH_BEARSSL=ON
cmake --build build -j
ctest --test-dir build          # 3 suites, 665 cases
```

Two fixes were needed on the crns branch to get there, both now on
`retcon/posix-build-fixes` (see git log there for details):

1. `api/libcrns_shared.cpp` asserted `CRNS_ABI_VERSION_MAJOR == 1` — stale
   after the §93 ABI bump to 2.x, so `CRNS_BUILD_SHARED=ON` failed a
   static_assert at build time. The assert now holds the invariant
   (major ≥ 1) instead of pinning a dead version; CMake derives
   VERSION/SOVERSION from `c_abi.h` either way.
2. Startup DNS failures on TCP-client interfaces (RETCON's client points
   at the dnsmasq name `retcon.gateway`, which only resolves once the AP
   is up) aborted host startup with `CRNS_HOST_ERR_INTERFACE_BRINGUP`.
   Now, with auto-reconnect armed (the default), the interface is
   registered in a deferred state and re-resolves the hostname on the
   reconnect backoff window (§100) — python rns's "retry the hostname
   forever" posture.

## Verified end-to-end (x86-64, sandbox)

- two crns hosts over a TCP loopback pair: announce → path learned →
  opportunistic LXMF `send` → `set_inbound_handler` receives decoded
  message → reply received by the peer.
- the full RETCON admin console (`utils/admin.py`): a peer host sends
  `status` over LXMF, the console replies with node identity +
  destination count.
- **cross-stack**: a crns host and python RNS 1.5.4 exchanging announces
  over one TCP interface (HDLC framing both sides) — the loopback bridge
  meshchat will use.
- full arm64 image build (`build_retcon.sh -- ARCH=arm64`): crns builds
  in-image (cmake from the suite packages), `import crns` works in the
  image's venv (binding + libcrns.so.2 staged in site-packages), and the
  generated `~/.meshchat-rns/config` is present with `share_instance =
  no`.
- **large messages (crns sprint 123, 2026-09-19)**: `send_direct()` —
  Link + rns-wire Resources, auto-chained across 32 KiB segments, up to
  the 0xFFFF packed-message bound. A 64000-byte (2-segment) round-trip
  verified byte-exact with `DirectSend.wait()` → DELIVERED. The console
  exposes it as `peers` + `sendfile <dest_hash> <path> [title]`
  (payloads ≤ 0xF000 bytes per message; the packed LXMF overhead eats
  the rest of 0xFFFF). Anything larger stays on the dashboard download
  path — one LXMF message is protocol-honestly capped, the same ceiling
  python RNS enforces.

## Open items

- crns path-table persistence across reboots (python rns writes path
  table state; crns keeps it in memory per config) — cold-start announce
  learning is slower on a fresh boot.
- IFAC on TCPServerInterface is not supported by crns v1 (RETCON doesn't
  use it; flagged here so nobody enables it silently).
- crns `AutoInterface`/`I2PInterface` remain unsupported — RETCON
  generates only TCP/RNode interfaces, which is exactly what crnsd
  accepts.