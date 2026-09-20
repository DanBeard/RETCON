# MicroRETCON firmware

ESP-IDF 5.3 firmware for the MicroRETCON device: a Seeed **XIAO ESP32S3**
running the **crns** host loop, with LoRa (Wio-SX1262 kit over SPI) and
ESP-NOW as mesh interfaces, USB-C as both console (CDC) and the browser
UI (the SPA served from flash). See `../../docs/MICRORETCON-DESIGN.md`.

**Board note (2026-09-20):** primary target is the XIAO ESP32S3 +
Wio-SX1262 kit — *not* the T-Deck Plus (that board lives in its own
self-contained repo). The design docs' board table is updated; the
brainstorm's T-Deck mentions are historical.

## Build

```
idf.py set-target esp32s3
idf.py build
```

ESP-IDF 5.3.2 (the version rWatch pins — same toolchain, one install
serves both). No menuconfig required: everything lives in
`sdkconfig.defaults`.

## Layout

- `main/` — crns host loop wiring, `[micro]` config consumption, the
  mode (transport/client) toggle
- `components/micro_pal/esp32/espnow/` — `EspNowRadio : IEspNowRadio`
- `components/micro_pal/esp32/sx1262/` — SX1262 SPI driver
  (structure mirrors rWatch's proven 514-LOC driver, retargeted to the
  XIAO kit pin map)
- `components/micro_usb/` — TinyUSB composite (CDC + MSC)
- `partitions.csv` — FAT region for the SPA + config, NVS for identity

## Status (M2 scaffold)

- Seams written, implementations pending: `IEspNowRadio` (espnow_radio.hpp,
  open/broadcast/online, v2 MTU 1470), `SX1262` radio profile +
  pin-map-stubbed seam (sx1262_radio.hpp — pins TO VERIFY against the
  Seeed schematic; PirateBot no-invented-pins rule), USB composite
  posture enum (usb_composite.hpp).
- `main/micro_main.{hpp,cpp}` — the BoardPlan consumption shape: config
  off FAT → crns parse (with [micro] via crns M1) → shared-channel rule
  (AP wins over espnow_channel) → mode→profile pick lives HERE (crns M1
  pinned decision 5), default Node.
- POSIX CI: `scripts/host_checks.sh` — seam compile-check with host g++
  -Werror + the `scripts/footprint_budget.sh` gate (vacuous until the
  first real link map; budgets then only tighten, never loosen).
- crns M1 config parser is in the crns tree (sprint/micro-m1-config-r1,
  committed e71e9db); the template this firmware reads is
  `retcon_profiles/micro.config`.
