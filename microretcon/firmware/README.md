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

## Status

Scaffold only — components are stubs. Sprint plan:
`../../docs/MICRORETCON-SPRINTS.md` (M2 = this repo's bring-up).
