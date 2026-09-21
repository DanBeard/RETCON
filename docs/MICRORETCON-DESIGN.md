# MicroRETCON — design (mode A: HTTP pipe)

**Date:** 2026-09-19
**Status:** DESIGN — supersedes the round-2/3 brainstorm options where they
conflict. The WASM-peer-in-browser posture (round 3's shape B) is recorded
as a **future architecture option, deliberately not traded for** here; see
`docs/MICRORETCON-BRAINSTORM.md` round 3 for the side-by-side and
`docs/MICRORETCON-BRAINSTORM.md` "Round 3" for why A ships first.

## 1. What this document pins

MicroRETCON is the ESP32 build of RETCON: same config keys, same
transport/client mode split, same "the cable is the console" story, on a
board with no python. The user-facing contract:

- **Same config file** (rnsd-format, same keys as the Pi's
  `retcon_profiles/*.config`), parsed by crns's own parser
  (`host/config.cpp`) — not a new dialect.
- **Transport mode** (`mode = transport`): forwarding on, headless, USB
  exposes a *serial Reticulum interface* so a laptop is a peer.
- **Client mode** (`mode = client`): the USB port is an *ethernet gadget*;
  a laptop opens a browser at `http://retcon.local` and gets the console
  UI — the browser does all rendering, composition, and storage work. The
  ESP32 never runs more than crns + USB + a pipe.
- **Identity location is device flash.** Always. Explicit in the status
  payload (`identity_location: "device"`), never in a browser. (The
  browser-resident posture stays a possible future add-on, documented in
  the brainstorm round 3; it is out of scope here and must not fall out of
  any shortcut taken in this design.)

## 2. Board targets

| Board | Radios | USB | RAM/flash | Profile | Notes |
|---|---|---|---|---|---|
| **Seeed XIAO ESP32S3 + Wio-SX1262 kit** (primary client) | SX1262 LoRa (external module), WiFi, BLE | USB-C (S3 native) | 8 MB PSRAM / 16 MB flash | `node()` w/ PSRAM | the "hand to a person" device — tiny, cheap, Meshtastic-ecosystem kit; no screen (USB console IS the UI). Higher draw — NOT the solar 24/7 candidate |
| **RAK4630 on RAK19003** (transport node) | SX1262 LoRa (on-module), BLE 5 | USB-C CDC (nRF52840 native) | 1 MB flash / **256 KB RAM** | `minimal()` (20.3 KB measured) | 24/7 solar transport; LoRa+BLE+USB-serial only — no WiFi, no ESP-NOW, no JS. **This target has its own doc: `docs/MICRORETCON-RAK4630.md`** |
| **LILYGO T3-S3** | SX1262, WiFi, BLE | USB-OTG | 8 MB PSRAM variants | `router()` | transport-first board |
| **classic ESP32 + SX1276 hat** | LoRa via SPI, WiFi (no BLE5) | UART bridge (not OTG) | 520 KB SRAM / 4 MB flash | `router()` tight | cheapest transport node; no gadget UI |

Profile selection is by `mode` **plus a PSRAM probe**: `router()`'s
~480 KB budget fits 520 KB SRAM only with `transport`'s thin tables —
measured in CI via `footprint_budget_bytes`, not hoped.

## 3. The config file — same keys, one new section

The device reads the same `[retcon]`/`[[wifi]]`/`[interfaces]` file the Pi
uses. crns's parser owns `[reticulum]` + `[interfaces]` exactly as today;
a **`[micro]`** section is board-side settings the firmware consumes
directly and the Pi's tooling ignores:

```ini
[micro]
  # which [[interfaces]] section is the ON-BOARD SX1262 (driven over SPI,
  # not a serial RNode). The section still uses rnode keys (frequency,
  # bandwidth, txpower, spreadingfactor, codingrate) so the same values
  # survive a config copy between Pi and ESP32.
  lora_iface = rnode0

  # ESP-NOW bearer. Shared-channel rule: if the device is also a WiFi
  # STA/AP, the AP's channel WINS and ESP-NOW follows it. Standalone mesh
  # nodes use this channel.
  espnow_channel = 6

  # USB posture (see §5)
  usb_mode = transport | gadget | serial
```

Everything else — `[reticulum]` forwarding, `[[wifi]]` (prefix scan keys,
mesh_mode), `[interfaces]` — means what it means on the Pi, with two
documented deltas:

- `mesh_mode = tcp` on an ESP32 means **the ESP32 is a station joining
  APs + optionally hosting a SoftAP** (lwIP, not NetworkManager). Same
  keys, different plumbing — the deterministic SSID-prefix scan is the
  same algorithm.
- RNode **serial** interfaces in the config refer to *external* RNodes
  over the board's spare UART; the on-board radio is `lora_iface`'d.

## 4. Firmware architecture

```
ESP-IDF 5.x, C++20
├── main task (FreeRTOS, core 0): crns host loop — poll/tick/respond,
│     the §80 responder, dispatch_inbound_cb → inbox store
├── radio task: SX1262 SPI driver (interrupt → queue → on_bytes() from
│     main task; the §3.1 boundary from docs/design/02-pal.md)
├── wifi task (ESP-IDF owned): ESP-NOW recv → queue → on_bytes()
├── usb task: TinyUSB composite — see §5
└── nvscfg: identity in NVS, config in FAT (same file the Pi writes)
```

crns pieces used as-is: `core/` everything, `host/host.cpp` loop +
responder, `pal/espnow/espnow_interface.hpp`, `core/kiss` + `core/lora`
framer, `pal/bearssl`. New device-side code (the whole list):

| Piece | Size class | Notes |
|---|---|---|
| `EspNowRadio : IEspNowRadio` | ~150 LOC | `esp_wifi_init` + `esp_now_init` + broadcast send; the research doc's sketched calls, verified against real headers |
| `SX1262Radio` + air-framer glue | the big one | drive SX1262 over SPI, feed `core/lora` framer; same shape the "direct-attach watch" pattern claims — two callbacks + chip config |
| `UsbCdcSerial : IByteStream` | ~100 LOC | transport mode's serial RNS iface |
| TinyUSB MSC volume | FAT image in flash | read-only window: config + START_HERE.html + static UI |
| captive DNS + `esp_http_server` | ~200 LOC | `retcon.local`; endpoint list §6 |
| config bridge | thin | `[micro]` + the same file into crns parser |

**Sequencing rule from the brainstorm, kept:** everything above the radio
seam is built POSIX-first with the existing crns binding (the Pi runs the
same config parser + host loop today), so the config bridge, HTTP API, and
LXMF flows are tested before any ESP-IDF line exists.

## 5. USB: the two postures

`usb_mode` picks, and both are TinyUSB composite-capable so the
`START_HERE.html` drive exists in both:

- **`usb_mode = transport`** (default for transport nodes): CDC-serial is
  a Reticulum interface (HDLC framing, `IByteStream` → `KissInterface`
  parity with the Pi's serial RNode path) — a laptop becomes a mesh peer
  over USB. The MSC drive still pops up with config + docs.
- **`usb_mode = gadget`** (default for client nodes): NCM/RNDIS ethernet
  gadget + captive portal, exactly the Pi's "the cable is the console."
  CDC console still available for headless ops.

S3 OTG is full-speed (12 Mbps) — fine for mesh-chat-scale traffic, and
the mesh itself is the bottleneck long before USB is.

## 6. The HTTP API contract (v1)

Stateless request/response; mesh state lives on-device, UI state in the
browser's localStorage. All JSON; no TLS (direct USB attach; the mesh
provides end-to-end crypto).

```
GET  /api/status    → { node_name, identity_hash, identity_location:"device",
                        mode, transport_enabled, interfaces:[{name,type,online}],
                        firmware, config_hash }
GET  /api/peers     → [ {dest_hash, last_heard, hops, iface} ]
GET  /api/inbox     → paged LXMF messages (FAT ring; `?page=` cursor)
POST /api/send      → { dest, title, content } → { handle }   (DirectSend)
GET  /api/send/<id> → { status: delivered|failed|cancelled }
GET  /api/config    → current config (same file, rendered)
POST /api/config    → full-file replace (same semantics as the Pi's config_str setter)
POST /api/announce  → announce now
GET  /files/*       → static UI (SPA + START_HERE.html), served from the same
                      flash region the MSC volume exposes
```

Rules pinned here:

- **`identity_location` is always `"device"`** in this design — it exists
  in the payload *now* so a future browser-resident posture is a value
  change, not a schema change.
- **No TLS.** HTTPS without a trusted cert is a browser warning, not
  security; the mesh provides its own end-to-end crypto.
- **The inbox is device-resident and paged**: a FAT ring (fixed flash
  region) holds received LXMF; the browser never needs to hold the whole
  history for the device to keep working.
- **Bulk is not the API's job**: firmware updates and large pulls ride
  MSC; the API stays JSON-small.

## 7. The UI: server-rendered floor, SPA ceiling

`START_HERE.html` on the MSC drive is the entire install procedure: it
explains, and links to `http://retcon.local`. The served UI is a vanilla-JS
SPA (no build step, no npm; a few KB) — same page shell the Pi's
`client_web_ui` shape implies, minus Flask. NomadNet-analogue pages, JSON
API under it. JS-in-the-browser only ever renders what the device's API
serves; no on-device scripting runtime is shipped (mJS/QuickJS stay
documented as *possible later*, never assumed).

## 8. Sprint plan (each is a RETCON-side doc/sprint with the crns-side
slices noted)

**S1 — `[micro]` config bridge + profile selection (POSIX-testable now)**
crns: extend `host/config.cpp` with the `[micro]` section (parse, ignore on
Pi builds) and expose `mode` → profile mapping. RETCON: the shared config
template gains the `[micro]` section with defaults; tests assert the Pi
ignores it and the parser accepts it. *Acceptance: config with `[micro]`
parses on both; unknown-key rule (tolerant) documented.*

**S2 — transport node, no UI (the mesh-existence milestone)**
ESP-IDF repo skeleton + `EspNowRadio` concrete (real `esp_wifi_*`/`esp_now_*`)
+ SX1262 SPI driver + `core/lora` framer glue + `UsbCdcSerial` RNS iface +
FreeRTOS queue glue + `Node<router()>` forwarding. *Acceptance: two boards
exchange announces over ESP-NOW; a board and a Pi exchange LXMF over LoRa
and over USB-serial; forwarding works with `enable_transport = yes`.*

**S3 — USB MSC + START_HERE + config file flow** — read-only FAT volume
from flash; config replace via the API (S6) or by editing the file on the
drive (mount rw only when not serving HTTP? — decide: **rw config on the
drive is v1; the API writes the same file**). *Acceptance: plug into a
laptop, edit config on the drive, unplug-replug applies it.*

**S4 — HTTP server + captive DNS + JSON API** — `esp_http_server` + lwIP
DNS responder + the endpoint contract above, against the same handler
shapes the Pi's web UI implies. *Acceptance: a browser on an attached
laptop does status/peers/inbox/send/config with no other software.*

**S5 — the SPA** — vanilla JS, the same shell for both A (device identity)
and the future B. *Acceptance: full round-trip — announce, message send,
inbox read, config edit — from a browser with no install.*

**S6 — LXMF inbox FAT ring + identity NVS** — fixed-region storage with a
documented eviction policy (oldest-first), same file semantics as
`~/retcon/storage/identity` so identities move Pi↔ESP32. *Acceptance:
identity written by the Pi reads on the ESP32 and vice versa.*

**Deliberately out of scope, with reasons:**
- Browser-resident identity / WASM peer (round 3 shape B) — architecture
  stays A; revisit as its own design doc if wanted.
- No screen/keyboard on the XIAO kit — the USB-attached browser is the console;
  the e-ink screen is a later, optional surface.
- BLE interfaces — ESP-NOW + LoRa cover the mesh; BLE-serial is a later
  adapter on the same `IByteStream` seam.
- `rns-if-espnow` wire compatibility (non-goal in the research doc, same
  call).
- OTA firmware updates over the mesh — MSC/USB path first.

## 9. Verification posture (inherited from crns's own rules)

- The whole non-radio surface is POSIX-testable first (config bridge, API
  handlers, config semantics) — same pattern that made the Pi side work
  before any ESP-IDF line existed.
- Radio seams get fake-radio unit tests exactly like
  `tests/test_espnow_interface.cpp` does today; real-radio verification is
  hardware-blocked and said so plainly (same caveat shape the RNode doc
  uses).
- xtensa+QEMU harness (§109-§113) runs the real test bodies on the real
  ISA in CI; windowed ABI + no-heap rules already enforced.
- Footprint budgets: `node()`/`router()` + USB + lwIP measured against
  `footprint_budget_bytes` at build time — regression = red build.