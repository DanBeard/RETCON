# MicroRETCON — ESP32 target brainstorm (2026-09-19)

Status: brainstorm / design exploration. No code written for the device yet.

## What MicroRETCON is

The same *shape* as RETCON — same config keys, same transport/client split,
same USB-gadget console idea — shrunk onto an ESP32 (class target: LILYGO
T-Deck / T3-S3: ESP32-S3, SX1262 LoRa on board, WiFi + BLE, USB OTG).
crns already treats ESP32 as its primary embedded target (§104-§113: xtensa
+ QEMU test harness, freestanding crns_core builds, `EspNowInterface` landed
with an `IEspNowRadio` seam waiting for a board).

## The single load-bearing decision: crns core on the MCU, not a python host

On the Pi, RETCON is "python binding over libcrns.so". On an ESP32 there is
no python, so the stack is the C++ core directly:

```
MicroRETCON firmware (ESP-IDF, C++)
  ├─ main task: crns Node<Config> + host loop (poll/tick/respond)
  ├─ pal: EspNowInterface (landed in crns, needs IEspNowRadio glue)
  ├─ pal: RNodeInterface over SPI-direct SX1262 (the "watch" pattern:
  │        drive the radio chip directly, no KISS serial hop)
  ├─ pal: WiFi STA/AP + ESP-NOW channel policy from config
  ├─ USB: TinyUSB CDC/NCM gadget (client mode) or CDC-serial transport
  └─ UI: USB-CDC web console over a serial SLIP/HDLC bridge, or USB NCM
         ethernet gadget + tiny HTTP server (the NomadNet-ish page)
```

### The config file story (what "same config" means in practice)

The Pi already writes a plain rnsd-format config. MicroRETCON reads the
**same file** with the same parser semantics crns host/config.cpp already
implements. Two things differ and need config-side acknowledgement:

1. **New keys under a `[micro]` section** (board-specific, ignored by the Pi):
   - `espnow_channel = 6` (the shared-channel gotcha: a node that's also an
     AP is pinned to the AP's channel; document that the AP side wins)
   - `lora_iface = rnode0` (which `[interfaces]` section drives the
     on-board SX1262 instead of a serial RNode)
   - `usb_mode = transport | gadget | serial` — see below
2. **Profile**: `Config::node()` (leaf, ~268 KB) for client mode,
   `Config::router()` (~480 KB) for transport mode. ESP32 has 520 KB SRAM —
   transport on a classic ESP32 is tight but measured-in-budget; an S3 with
   PSRAM is comfortable. crns's footprint budgets make this a compile-time
   CI check, which is exactly the right shape.

## The two modes

### Transport node (`mode = transport`)

Same semantics as the Pi: transport forwarding on (`enable_transport = yes`
in the same `[reticulum]` section), interfaces from `[interfaces]`, no UI.
USB exposes a **CDC-serial Reticulum interface** (HDLC framing, the same
thing the Pi's loopback listener speaks) so a laptop can attach over USB and
become a Reticulum peer — that's the "transport server over USB/serial"
story. BLE could later join as a BLE-serial GATT service (python RNS speaks
BLE-serial RNodes already), but ESP-NOW + LoRa + USB-serial is the honest
first slice.

### Client mode: the USB gadget and the "NomadNet-ish" UI

The Pi's client mode is: USB NIC (RNDIS/ECM) + a web page at
`retcon.local`. On an ESP32-S3 with USB-OTG the equivalent is a **TinyUSB
NCM/RNDIS ethernet gadget**: the host laptop sees a USB ethernet NIC, the
ESP32 runs a tiny HTTP server on it. The UI options, honestly costed:

| Option | Flash | RAM | Verdict |
|---|---|---|---|
| mJS (cesanta) | ~30-50 KB | ~5-15 KB/script | real JS engine, but no DOM; you'd write a JS-driven JSON API and keep UI native |
| QuickJS-ng | 300-800 KB | 1-2 MB heap min | real JS, but eats PSRAM; only sane on S3 N16R8 |
| **Server-side HTML + forms, no JS** | ~10 KB | ~10 KB | the honest NomadNet analogue |

The NomadNet page model is the right analogy, not a JS runtime: NomadNet's
`.mu` pages are static text/markup fetched over LXMF with a minimal link
grammar. MicroRETCON's gadget UI should be the same thing: a tiny HTTP
server (or even a captive-portal DNS + HTTP pair like the Pi's
`retcon.local`) serving hand-rolled HTML forms that POST to a config API.
"Runs JS" is the wrong goal; "works with zero JS" is the constraint that
fits a 520 KB SRAM part and still feels like NomadNet. If real JS is
wanted later, QuickJS-on-PSRAM is the upgrade path, not the foundation.

So the UI slice, minimum viable:
- `GET /` — node status (identity hash, interfaces, heard peers, transport/client mode)
- `GET/POST /config` — the same settings the Pi's web UI edits (wifi ap prefix/psk, espnow channel, lora params, name)
- `GET /msg` — LXMF inbox (announces heard + messages), `POST /msg` to send
- captive DNS (dnsmasq-equivalent is ~100 lines on the ESP32's lwIP) so the
  gadget auto-opens like the Pi's portal does

## What's already landed in crns that MicroRETCON stands on

- `pal/espnow/espnow_interface.hpp` — full `IInterface` over an injected
  `IEspNowRadio` (open/broadcast/online, three methods), POSIX-tested with a
  fake radio. ESP-NOW facts from the research doc: no peer pairing
  (broadcast MAC, receiver needs zero calls), datagram-shaped (no framer),
  v2 1470 B payload, set `resource_segment_bytes` ≈ 1450 and the MTU guard
  does the rest.
- `core/kiss/kiss_framer.hpp` + `core/lora/` RNode air framer — for a
  LoRa iface the board drives SX1262 over SPI directly and crns owns L1/L2,
  same as the "direct-attach watch" shape.
- `Config::node()` / `Config::router()` — measured footprints (268 KB /
  480 KB) with CI budget checks, vs 520 KB SRAM on classic ESP32.
- `scripts/build-esp32-tests.sh` — the whole freestanding test harness on
  xtensa + QEMU (windowed ABI, no-heap discipline), already in-tree.

## The gap list (what MicroRETCON actually needs building)

1. **Downstream device repo** (`microretcon/` in RETCON, or its own repo):
   - concrete `IEspNowRadio` (esp_wifi + esp_now calls, pinned ESP-IDF)
   - SX1262 SPI radio implementing the RNode air-framer side directly
     (this is the biggest genuinely-new codec work; the framer doc claims
     it's "two callbacks + chip config")
   - TinyUSB CDC (serial transport) + NCM gadget (client mode) glue
   - FreeRTOS queue glue: recv callback → ring → `on_bytes()` in main task
2. **Config bridge**: parse the same `[reticulum]`/`[interfaces]` file with
   crns's own parser, plus a `[micro]` section the board reads
3. **UI**: the tiny HTTP server + pages (probably raw lwIP httpd, ~1-2 KB of
   handlers; forms POST → config update → same semantics as the Pi's web UI)
4. **Announce/display identity**: same LXMF announce app_data shape as the
   Pi's console so meshchat peers see the node properly
5. **The transport/client toggle**: same as the Pi's mode switch, but
   `transport_enabled` comes from `Config::router()` vs `Config::node()`

## Sizing the JS question (the "barebones JS UI" idea)

On an **S3 with PSRAM** (T-Deck: 8 MB PSRAM, 16 MB flash), QuickJS is
real: ~500 KB flash for the engine, 1-2 MB PSRAM heap per context. That's
the "actually run JS on the node" path. On classic ESP32 (no PSRAM), no JS
engine is honest — the UI should be server-rendered HTML (the NomadNet
model) and the "JS" part lives in the browser, not the node. Recommendation:
design the API as JSON-over-HTTP (mJS-friendly), ship the UI as plain HTML
first, and treat a QuickJS sandbox as a later add-on if on-device scripting
is ever actually needed.

## Sequencing (what I'd build first)

1. **POSIX-first, always**: the `IEspNowRadio` concrete implementation has
   to be built against real ESP-IDF, but everything above it (config bridge,
   HTTP UI, LXMF flows) is testable on the Pi first with the existing
   crns binding — same pattern that made the Pi side work.
2. Bring up the **transport node** first (ESP-NOW iface + LoRa iface +
   forwarding, no UI) — it's the thing that makes a *mesh* exist, and the
   thing you can verify from a Pi before any UI exists.
3. Then the USB CDC transport interface (laptop as RNS peer over serial) —
   small, and it unlocks debugging from a laptop with real rns tooling.
4. Then the NCM gadget + HTML UI.
5. ESP-NOW wire-compat with `rns-if-espnow` stays a non-goal (same call as
   the research doc made).