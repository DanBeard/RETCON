# Sprint plan — MicroRETCON (mode A)

**Date:** 2026-09-19
**Design:** `docs/MICRORETCON-DESIGN.md`
**Repo layout:** RETCON hosts the device repo at `microretcon/` (ESP-IDF
project + board code). crns-side slices land as crns sprint branches
(`sprint/<n>-<name>-r1` in worktrees, per crns AGENTS.md). POSIX-first is
the standing rule: nothing here needs a device until the milestone that
is explicitly a device milestone.

## Sprint order, dependencies, and what each locks

| # | Sprint | Layer | Depends on | New-protocol risk |
|---|---|---|---|---|
| M1 | `[micro]` config section + profile mapping | crns + RETCON config | — | none (parser-only) |
| M2 | transport node (ESP-NOW + LoRa + forwarding) | device repo | M1 | SX1262 codec — the one real radio task |
| M3 | USB MSC volume + START_HERE | device repo | M2 (firmware base) | none |
| M4 | HTTP server + captive DNS + JSON API | device repo | M2 | none (lwIP httpd) |
| M5 | inbox FAT ring + identity NVS | device repo | M2 | file-format only |
| M6 | SPA console | RETCON `microretcon/ui/` | M4, M5 | none |
| M7 | transport→client toggle + PSRAM-aware profile pick | device repo | M2, M4 | none |

Sprints M1-M2 are the mesh-existence milestone; M3-M6 are the
hand-to-a-person milestone. M2 is the long pole and the only sprint with
genuinely new radio code — everything else is glue around seams crns
already drew.

## M1 — `[micro]` config section + profile selection (POSIX)

**crns side (sprint worktree):**
- `host/config.cpp`: parse the `[micro]` section
  (`lora_iface`, `espnow_channel`, `usb_mode`) into a
  `crns::host::MicroConfig` struct carried beside the existing parse
  result. Unknown keys stay tolerant (same rule as today).
- `Config::router()` / `Config::node()` unchanged; the mapping mode →
  profile lives in the *device* main, not the parser (the Pi builds never
  select `router()` because of it).
- tests: `[micro]` parses, `[micro]` absent = defaults, Pi-side ignore
  documented.

**RETCN side (this repo):**
- `retcon_profiles/micro.config` — the shared template with `[micro]`
  defaults and the same `[[wifi]]`/`[interfaces]` sections.
- `docs/MICRORETCON-DESIGN.md` §3 is the acceptance spec.

**Acceptance:** a config with `[micro]` parses on the Pi (ignored there)
and in the crns test suite (asserted there). Same values in
`[[[rnode]]]` survive a copy Pi↔ESP32.

## M2 — transport node (the long pole)

**Device repo `microretcon/`**:

```
microretcon/
  main/            # crns host loop wiring + [micro] consumption
  components/
    espnow_radio/  # IEspNowRadio concrete
    sx1262_radio/  # SPI radio + core/lora framer glue
    usb_cdc/       # UsbCdcSerial (IByteStream) + TinyUSB init
  sdkconfig.defaults
  partitions.csv   # NVS + FAT + firmware
```

- `espnow_radio`: the sketched `esp_wifi_*`/`esp_now_*` sequence from the
  research doc, now verified against the pinned ESP-IDF headers; recv
  callback → FreeRTOS queue → `on_bytes()` from main task (the §3.1
  boundary).
- `sx1262_radio`: SPI setup + TCXO/regulation + the framer's two
  callbacks. Reuses `core/lora`'s air framer byte-exact (508 B MTU,
  FLAG_SPLIT).
- `usb_cdc`: HDLC-framed `IByteStream` for the serial RNS iface; the
  same `KissInterface(FullCommandByte)` parity the Pi's serial RNode uses.
- Profile: `router()` when `mode = transport` (PSRAM probe may allow
  `router()` on S3; classic ESP32 uses `router()`-tables minus the fat
  caches — measured in CI, not guessed).

**Acceptance:**
- two boards: announces heard over ESP-NOW both directions, transport
  forwarding on, a Pi (over a TCP iface) routes through an ESP32 to
  another Pi.
- board ↔ Pi over USB-serial: LXMF round-trip with the Pi's crns binding.
- `make menuconfig`-free build: `idf.py build` from a clean clone with
  `idf.py set-target esp32s3`.

## M3 — USB MSC + START_HERE

- TinyUSB MSC exposing a read-mostly FAT region carved from flash
  (partition: `storage`), containing: `START_HERE.html`, `config`
  (the live config file), `retcon-docs/`.
- Config-on-the-drive is the *same file* the firmware reads. v1 rule:
  **rw config on the drive; the API (M4) writes the same file** — one
  source of truth, two windows (same rule as the Pi's release drive).
  Sync hazard (drive mounted while firmware writes) is handled by: mount
  rw only on a button-held-at-boot or `usb_mode`-triggered "config
  window", otherwise read-only. *Decision pinned here: v1 ships the
  read-only drive + API-writes; rw config window is a v2 nicety.*
- *Acceptance: plug into a laptop → drive appears with START_HERE.html;
  unplug-replug after an API config write shows the new file.*

## M4 — HTTP server + captive DNS + JSON API

- `esp_http_server` for the API + static `/files/*` (same FAT region as
  MSC, read-only).
- Captive DNS: a 53/udp responder answering `A retcon.local → gadget IP`,
  ~100 lines, wired when NCM is up.
- Endpoints exactly as §6 of the design doc (status/peers/inbox/send/
  config/announce). `identity_location:"device"` literal in status.
- *Acceptance: from an attached laptop browser — status, peers, inbox,
  send (DirectSend poll), config edit; every response JSON; no TLS
  prompt.*

## M5 — inbox FAT ring + identity NVS

- Fixed-region FAT ring for received LXMF (oldest-first eviction,
  documented), sized per PSRAM/SRAM variant (config key `inbox_kb`).
- Identity in NVS (or a fixed FAT file) in the same 64-byte format
  `register_destination(identity_file=...)` writes on the Pi — so
  identities move Pi↔ESP32.
- *Acceptance: identity written by the Pi's console reads on the device
  (same hash), and vice versa; inbox survives reboot; ring eviction
  documented and testable.*

## M6 — SPA console

- `microretcon/ui/` — vanilla JS + HTML, no build step. Pages: status,
  peers, inbox, compose, config. Same information architecture as the
  Pi's client web UI, minus Flask.
- `START_HERE.html` is the entry point from MSC; the SPA also lives at
  `/files/` over HTTP.
- *Acceptance: from a browser, complete flow — see peers, send a
  message, watch status go DELIVERED, read it on the peer, edit config
  (name, espnow_channel) and see it apply.*

## M7 — transport→client toggle + PSRAM-aware profile

- `mode = transport|client` switches `router()`/`node()` + USB posture,
  same semantics as the Pi's mode switch, applied via `/api/config` or
  the config file (M3's rule).
- PSRAM probe: S3 with PSRAM keeps `router()`; classic 520 KB SRAM runs
  the transport-thin router only if the footprint budget CI says so.
- *Acceptance: toggle mode in the browser, device reboots into the new
  posture, USB posture changes with it (gadget↔serial).*

## Standing rules across all sprints

- **POSIX-first:** every non-radio surface (config bridge, API handlers,
  inbox ring semantics, identity file IO) is built and tested on the Pi
  with the existing crns binding before the ESP-IDF port line exists.
- **Radio seams get fake-radio tests** in-tree, the same way
  `tests/test_espnow_interface.cpp` does; real-radio verification is
  hardware-blocked and stated plainly.
- **Footprint budgets are CI**, via `footprint_budget_bytes` — a sprint
  that regresses RAM is a red build, not a note.
- **Identity stays on-device.** No identity data ever ships to the
  browser (it's not needed for any endpoint); the
  `identity_location:"device"` field exists so a future posture is a
  value change, not a schema change.
- **No new wire bytes** in M1/M3-M7; M2's LoRa path reuses `core/lora`
  + `core/kiss` framing as-is (same bytes as an RNode would produce).

## Cross-sprint risk register

| Risk | Mitigation |
|---|---|
| SX1262 over SPI is the only genuinely new codec | start M2's radio bring-up on a POSIX-attached dev board (T-Deck as a USB peripheral to a Pi) before firmware integration |
| shared-channel conflict (ESP-NOW + AP) | config-pinned channel + documented AP-wins rule; revisit when a dual-purpose consumer exists (same call the research doc made) |
| 520 KB SRAM transport on classic ESP32 | footprint CI + PSRAM-first board choice (S3 primary) |
| TinyUSB composite class interactions (CDC+MSC+NCM) | pin an Espressif examples-verified combo; if NCM+MSC fights, ship CDC+MSC first and NCM as its own sprint |
| browser-inbox race (drive rw while serving) | v1 rule: drive is read-only; API writes the file — no concurrent mount writes |