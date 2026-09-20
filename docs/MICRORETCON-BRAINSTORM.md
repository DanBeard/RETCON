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

---

## Round 2 — pushing logic OFF the device: the server is a pipe, not a brain

The design constraint that matters most: **the ESP32 must never be the
bottleneck for capability.** It runs crns (the mesh), a USB stack, and a
near-zero-thought HTTP pipe. Everything that needs "horsepower" — UI
rendering, message composition, maps, crypto-heavy bulk ops, storage,
*any* scripting — happens on the device the user already owns (laptop,
phone, tablet). The ESP32 is a smart radio dongle with a USB port.

### Three attachment modes, one contract

The gadget exposes the same small HTTP+JSON API regardless of which of
these the host machine picks:

| Attachment | What it is | Who it serves |
|---|---|---|
| **USB NCM/RNDIS gadget** (primary) | ESP32 appears as a USB ethernet NIC; HTTP+DNS captive portal at `retcon.local` | Any laptop/phone with a browser — zero install |
| **USB MSC (mass storage)** | ESP32 appears as a USB flash drive with `START_HERE.html` + files | Truly "off to the races": the UI literally opens from the drive, or a portable-HTML launcher |
| **USB CDC serial** (transport mode) | HDLC-framed RNS interface; also a JSON-over-serial console for headless ops | Debugging, transport nodes, future Web-Serial UI |

Composite TinyUSB makes CDC+MSC+(NCM) simultaneous on one port, so a single
plugged-in device can be *all three at once* — ethernet gadget AND a flash
drive with the launcher page AND a serial console. That's the "hand it to a
normy" story: **plug in the cable, a drive pops up, double-click
START_HERE.html, done.** No pip, no drivers on modern OSes (NCM/MSC/CDC are
class drivers).

### The client-side architecture (where the "logic" lives)

The HTTP server serves **static assets + a JSON API**; the intelligence is
in a browser app delivered from the device's flash (or the MSC volume):

```
ESP32 (dumb pipe)                    Laptop browser (smart client)
┌──────────────────────────┐         ┌────────────────────────────────┐
│ crns Node (mesh truth)   │  HTTP   │ SPA: rendering, message draft, │
│ /api/status  (json)      │ ←────── │ identity management, maps,     │
│ /api/peers, /api/announce│         │ bulk listing, caching          │
│ /api/msg (send/recv poll)│         │                                │
│ /api/config (read/write) │         │                                │
│ /files/* (static SPA)    │         │                                │
└──────────────────────────┘         └────────────────────────────────┘
```

- The SPA is a few KB of vanilla JS (or Preact-lite, ~10 KB) — no build
  step, no npm. It renders, drafts, and talks to the JSON API. It can be
  as fancy as the laptop can render, because it never touches the ESP32's
  CPU.
- **State lives in two places, by rule:** the mesh-side state (identity,
  LXMF inbox, paths) lives on the ESP32 in crns structures; UI-side state
  (drafts, UI prefs, cache) lives in the browser's localStorage. The API is
  stateless between requests — every page load re-syncs from the device.
- The **MSC volume is a bonus channel, not the app**: firmware-side it's a
  read-only FAT image served from flash (esp_vfs_fat + TinyUSB MSC — a
  static 256 KB-4 MB region), so the drive is literally a read-only window
  onto the same files the HTTP server serves. START_HERE.html explains and
  links to `http://retcon.local` (which the NCM interface serves
  simultaneously). No sync problem: one source of truth (flash), two
  windows onto it.

### On the "WASM reticulum in the browser" idea — why I'd split it the other way

The temptation: compile Reticulum to WASM so the browser is a real RNS
peer and the ESP32 is just a radio. Three reasons that inverts the right
split here:

1. **No RNS WASM port exists.** BearSSL (crns's crypto) would need an
   Emscripten port first (60-100 KB), then the whole crns core, then LXMF —
   and the crypto + transport state machine is exactly the part that must
   be *right* and is the hardest to keep in sync with the real stack.
2. **Identity splits in two.** If the browser runs RNS, your LXMF identity
   keys live in browser localStorage — cleared on "clear browsing data",
   per-browser, per-machine. The whole point of RETCON identity is that it
   lives on the device (the Pi already does `~/retcon/storage/identity`).
   A browser-side peer forks the identity model.
3. **The browser has no mesh attachment anyway.** Even with WASM RNS, the
   browser can't reach ESP-NOW or LoRa — it would still tunnel over USB to
   the ESP32. So the WASM peer adds a second, parallel RNS stack talking to
   the first, and the ESP32 is still the radio. All cost, no capability.

The design that preserves your actual goal ("logic lives away from the
ESP32") without a WASM port: **the ESP32 is a Reticulum node with a dumb
JSON API, and the browser does everything that isn't mesh protocol.**
Rendering, composition, search, history, maps, even end-to-end crypto for
*user-authored* payloads can be browser-side (WebCrypto ed25519 exists in
Chrome/Firefox/Safari 17+) — as long as the *Reticulum* identity and its
signing stay on-device. Where the line sits exactly (e.g. is LXMF envelope
crypto on-device, with only rendering remote?) is a real design decision
worth its own doc — the default here is: mesh crypto on-device, everything
else in the browser.

### The transport mode answer

In transport mode the same HTTP+JSON surface is available over **CDC serial**
using the **Web Serial API** (Chrome/Edge; a ~200-line serial-to-JSON
bridge in the browser) — so even a transport node with no NCM gadget is
configurable from a browser page served *from the MSC volume* (the drive
pops up, you open START_HERE.html, it talks JSON over serial with a user
gesture). No ethernet gadget needed for configuration; the mesh itself
still rides ESP-NOW + LoRa + the serial RNS iface.

### What the ESP32's HTTP server actually needs to be

- lwIP's bundled httpd (esp_http_server): handles GET/POST, ~20 KB flash,
  no TLS (gadget = direct USB attach, no network in between), serves the
  SPA + JSON routes. Captive-portal DNS: lwIP has no built-in DNS server,
  but a 53/udp responder that answers `A retcon.local → gadget IP` is
  ~100 lines.
- Endpoints, all JSON, all synchronous-ish (crns submit() shaped):
  - `GET /api/status` — identity hash, mode, ifaces, transport fwd status
  - `GET /api/peers` — heard announces + freshness + paths
  - `GET /api/inbox` — LXMF messages (paged; stored in a FAT ring)
  - `POST /api/send` — {dest, title, content} → DirectSend, returns handle
  - `GET /api/send/<id>` — poll a DirectSend's status
  - `GET/POST /api/config` — the [reticulum]/[micro] config, same keys as
    the Pi
  - `POST /api/announce` — announce now
- **No TLS.** The gadget is a direct USB attach (no network hop to
  intercept); the mesh provides its own crypto end-to-end. HTTPS on an
  ESP32 without a real CA cert buys a browser warning, not security.
- Rate/bulk: message bodies are capped by the same 0xFFFF packed bound;
  bulk file transfer (firmware updates, image pulls) rides MSC or the
  dashboard, not the JSON API.

### What this makes the ESP32's actual CPU cost

- crns Node + 2-3 ifaces: measured 268 KB RAM (node profile)
- TinyUSB composite: ~15-30 KB RAM
- lwIP + httpd + captive DNS: ~40-60 KB RAM
- FatFS ring for LXMF inbox: flash-side, RAM cost is the read buffer

Total ~350-400 KB of 520 KB — fits a classic ESP32 in client mode
(comfortably on an S3). The render/compose/script work is 0 bytes of it,
which is the entire point of the round-2 design.