# RAK4630 transport node — MicroRETCON target B (solar, 24/7)

**Date:** 2026-09-20
**Status:** scoping — this doc splits the MicroRETCON design into its two
real hardware targets after a board-identity correction.
**Supersedes:** the single-target assumption in
`docs/MICRORETCON-DESIGN.md` §4–§5 for this board (the ESP32-S3 client
device keeps its design; this doc is the RAK's).
**Companion:** `retcon_profiles/micro.config` (the shared config file —
unchanged, it carries over verbatim).

## The board (what is actually true)

- **RAK4630** WisBlock module: **nRF52840** (Cortex-M4F, 1 MB flash,
  **256 KB RAM**) + **SX1262** LoRa + BLE 5, antennas on-module, fully
  assembled.
- **RAK19003** WisBlock Base Board 2 (the 4-slot base it's plugged into):
  USB-C, battery/PMIC path for solar+battery 24/7 operation.
- Measured (user, with a Pi Zero attached): draw barely above a bare
  ESP32-S3 with nothing attached — this is the low-power transport
  candidate, and the reason it exists.

**Authoritative pin/reference source:** Meshtastic firmware
`variants/rak4630/` (officially supported target) + RAK's RAK4630 /
RAK19003 docs. Verify every pin against those before firmware (PirateBot
no-invented-pins rule). NO pins invented in this repo until that lookup.

## Role split (the user's pinned decision, 2026-09-20)

| | **RAK4630 transport node** (this doc) | XIAO ESP32-S3 client device |
|---|---|---|
| Job | 24/7 LoRa+BLE+USB transport, solar+battery | the "hand to a person" console device |
| Power | ultra-low, solar-backed | higher draw, wall/solar-large |
| crns profile | `minimal()` (20.3 KB static, measured) | `node()` (269 KB) |
| Interfaces | LoRa (SX1262) + BLE + USB-CDC serial | LoRa + ESP-NOW + WiFi + USB gadget |
| JS/browser console | **no** — no WiFi, no RAM for it | yes — the SPA served over USB |
| Client pairing | Pi Zero (or similar) on the USB port is the user's client | self-contained |

The two targets are siblings, not forks: **same config file, same crns
core, same LXMF mesh.** The RAK is a *transport-only* Reticulum node its
paired host rides through.

## Why minimal() fits (measured, not hoped)

crns profiles (from the test suite's own printout, crns @ 2.2.0):

| profile | `sizeof(Node)` | fits 256 KB? |
|---|---|---|
| `minimal()` | **20,328 B** | easily |
| `node()` | 269,056 B | marginal-to-no (stacks+heap don't fit) |
| `router()` | 481,432 B | no |

`minimal()` gives: 1 interface, 16 path entries, 2 links, 4 pending
sends, no resources, no bz2. For a transport-only node whose job is
**forward frames + keep the path table warm**, this is exactly the
profile. Its budget is CI-asserted already (crns M1 tree, green).

Open item for the crns side: `minimal()` is likely tuned *below* what a
multi-interface transport needs (it models 1 interface; the RAK wants
LoRa + BLE + USB = 3). A `rak()`-style profile or a
`Config::transport_nrf52()` variant is a crns-side follow-up — measured
before committed, per the footprint-budget contract.

## Interfaces on the RAK (the three bearers)

1. **LoRa — SX1262 over SPI** (on-module). Same chip, same driver shape
   as the ESP32 plan (rWatch's 514-LOC `Sx1262Interface` is the crib),
   but the SPI/GPIO layer is **nRF52** (`nrfx_spim`), not ESP-IDF. Pins
   from the Meshtastic `rak4630` variant file at implementation time.
2. **BLE — GATT serial.** crns sprint/122 (BLE5 research/design) is the
   reference; the PirateBot prop firmware's "BLE+USB share a tiny frame
   layer" pattern is the second precedent. The paired host sees a
   BLE-serial Reticulum interface.
3. **USB-CDC serial** — nRF52840's native USB device controller (CDC
   only; no NCM/MSC composite question — it's a serial bridge, which is
   all the transport posture needs). This is the wire the Pi Zero rides.

Mode: **`transport`** in `[retcon]` terms — no UI, no meshchat, no auth,
pure forwarding. The client experience lives on the paired host.

## What does NOT apply here (honest deltas from the ESP32 design)

- **No `[micro] usb_mode = gadget`** — no ethernet gadget, no captive
  portal, no MSC drive. The RAK's USB is a plain serial Reticulum
  interface (KISS framing), the same shape as a serial RNode on the Pi.
- **No ESP-NOW** — no WiFi at all. The `IEspNowRadio` seam is
  ESP32-only; the RAK's second bearer is BLE instead.
- **No JS/browser console** — by design (256 KB RAM, no WiFi). The
  console for a RAK is the paired host's console.
- **No lwIP/httpd** — no IP stack needed for the transport posture.
- **Power is a design constraint, not an afterthought:** the point of
  this board is the measured draw. P4 ordering applies (prove function
  first, optimise power second) — but the acceptance metric includes the
  solar+battery 24/7 posture, not just "it forwards".

## Pin facts (VERIFIED 2026-09-20 — meshtastic/firmware
`variants/nrf52840/rak4631/{variant.h,variant.cpp,platformio.ini}`;
SKU: RAKwireless Mini Meshtastic Starter Kit US915, RAK19003 + RAK4631,
SKU 115093)

Kit region: **US915** — the rnode radio params in
`retcon_profiles/micro.config` (914.875 MHz / BW 125k / SF8 / CR5 / 14
dBm) are US915-compatible; Meshtastic's own US915 default is 906.875 MHz
SF11 for public LongFast, but a private transport can use the RETCON
rnode numbers. Config file stays the source of truth.

### SX1262 (on-module, SPI1 — P1.n pins, Arduino GPIO numbers)

| Signal | nRF52 pin | Arduino GPIO |
|---|---|---|
| NSS | P1.10 | 42 |
| SCK | P1.11 | 43 |
| MOSI | P1.12 | 44 |
| MISO | P1.13 | 45 |
| BUSY | P1.14 | 46 |
| DIO1 | P1.15 | 47 |
| NRESET | P1.06 | 38 |

**Init requirements from the variant header (load-bearing):**
- **DIO2 controls the antenna switch** — no TXEN/RXEN GPIOs (P1.07 is
  wired to the switch but MUST NOT be initialised; the header comment is
  emphatic: GPIO 39/TXEN may not be defined or the radio fails).
- **DIO3 controls the TCXO power**.
- Use the **DCDC regulator**, not the LDO.
- `SX126X_POWER_EN = GPIO 37` (P1.02?) powers the module rail.

### Other pins of record
- LED1 (green) = GPIO 35, LED2 (blue) = GPIO 36, active HIGH.
- Battery: ADC on A0 (VBAT via divider, 12-bit, ×1.73 multiplier,
  3.0 V ref) — the solar-soak acceptance needs this.
- nRF52 Arduino SPI pins 43/44/45 = SCK/MOSI/MISO (the primary SPI bus;
  SPI1 at 29/30/3 is the free one for expansion slots).

### Platform facts
- Meshtastic architecture: `nrf52840`, board `wiscore_rak4631`,
  actively supported, support-level 1.
- Toolchain: PlatformIO `nrf52840_base` env (Zephyr-less — Meshtastic's
  Nordic build is Arduino-core-on-nRF52, NOT NCS/Zephyr). This matters
  for R1's toolchain decision below.

## Firmware target (nRF52)

- Toolchain: **decision point, now informed by the variant lookup** —
  Meshtastic's `nrf52840_base` PlatformIO env is **Arduino-core on
  nRF52, not Zephyr/NCS** (board `wiscore_rak4631`, actively supported,
  support-level 1). The Arduino-nRF52 core gives USB CDC + BLE UART out
  of the box, which is 80% of R1. Recommendation: start Meshtastic-shaped
  (PlatformIO + Arduino-nRF52 core) for R1 bring-up, and only reach for
  Zephyr/NCS if a need appears that the Arduino core can't express.
  crns on nRF52 then needs a thin PAL over the Arduino-core primitives
  (same shape as the ESP32 PAL ports rWatch/piratebot did).
- crns on nRF52: the core is portable C++20 (no heap/threads/exceptions)
  and BearSSL is pure C — the **posix PAL is the mismatch** (sockets/
  threads/files). The seam pattern from `pal/espnow` (pure logic behind
  `IInterface`) plus a new `pal/nrf52` port is the shape; the ESP32 PAL
  ports (rWatch/piratebot precedent) are the template for the effort.
- Vendor: same crns pinned-submodule pattern as rWatch/piratebot.

## Sprint reshuffle (replacement for the single M2)

- **R1 — RAK4630 bring-up (the board in hand):** Zephyr/NCS project
  skeleton, SX1262 over SPI talking (verified against the variant pin
  map), USB CDC echo, BLE GATT serial echo. No crns yet. Output: a
  booting board + a written pin/fact record (S0-shaped, rWatch precedent).
- **R2 — crns on nRF52:** `pal/nrf52` (clock/RNG/crypto glue), minimal()
  profile, ONE LoRa interface forwarding. Two RAKs exchange traffic
  AP-less (they have no AP — LoRa direct).
- **R3 — the Pi Zero pairing:** USB CDC KISS interface on the Pi side
  (RETCON's serial-RNode path, already proven shape), Pi as the client.
  Solar 24/7 soak test begins.
- **R4 — BLE bearer** as the third interface (GATT serial, crns 122's
  design), transport profile at 3 interfaces (crns-side follow-up if
  `minimal()` needs widening).
- **M2 (ESP32 client device)** — parallel track, unchanged design, needs
  the XIAO kit hardware.

## Immediate next steps

1. Pin-verify from Meshtastic's `variants/rak4630/` + RAK docs (SX1262
   SPI wiring, LNA/BUSY/DIO1, LED/battery ADC) — before any pin is typed.
2. Decide Zephyr/NCS vs bare `nrfx` for R1 (recommendation: NCS, since
   USB CDC + BLE GATT both come from it and Meshtastic proves the
   platform).
3. Power-log the existing unit while idle (the user's measured data point
   deserves a recorded baseline for the 24/7 acceptance).