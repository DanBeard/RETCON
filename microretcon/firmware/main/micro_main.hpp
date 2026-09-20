#pragma once
// MicroRETCON device main — board consumption of the shared config file.
//
// Reads the SAME config the Pi writes (crns parser, [micro] section via
// MicroConfig — crns M1). Picks the node profile + interface set from it,
// starts the crns host loop, serves the HTTP API. Sprint M2
// (RETCON docs/MICRORETCON-SPRINTS.md).
//
// Everything here is a THIN adapter: the mesh mechanics live in crns
// (vendored as a submodule), the UI lives in ../ui/static/, and this file
// wires the two together and nothing more.

#include "host/config.hpp"  // crns: RnsdConfig + MicroConfig ([micro])

namespace micro::main {

// What the device builds from the config file. Deliberately a plain
// struct — no allocation, filled once at boot, read-only after.
struct BoardPlan {
    // crns's parsed config (interfaces, transport flag) — passed straight
    // to the host loop.
    crns::host::RnsdConfig rns{};

    // [micro] section as parsed (present/lora_iface/espnow_channel/usb_mode).
    crns::host::MicroConfig micro{};

    // Effective WiFi channel for ESP-NOW: the AP's channel WINS over
    // [micro] espnow_channel when the device hosts/joins an AP (DESIGN §3
    // shared-channel rule). Equals micro.espnow_channel when no WiFi.
    uint8_t espnow_channel = 6;

    // Which crns node profile the firmware instantiates. The mapping
    // mode → profile lives HERE, not in the parser (crns M1 pinned
    // decision 5): client mode gets node() (smaller, UI-facing);
    // transport mode selects between node() and router() by PSRAM size —
    // 8 MB octal PSRAM on the XIAO ESP32S3 comfortably fits router()'s
    // ~480 KB static node, but the DEFAULT stays node() until measured
    // (footprint_budget_bytes gates the promotion).
    enum class Profile : uint8_t { Node, Router } profile = Profile::Node;
};

// Parse the config file off the FAT volume + produce the board plan.
// Fatally errors (and reboots with a readable console message) when the
// config is missing or malformed — a headless device with no config is
// not recoverable from the API, so it must be loud at boot.
BoardPlan load_board_plan(const char* config_path);

// Bring-up order (M2 implements, M3/M4 add):
//   1. NVS init, FAT mount (the MSC-visible volume)
//   2. load_board_plan()
//   3. interfaces: [micro] lora_iface → SX1262 (SPI), espnow_channel →
//      EspNowRadio, [interfaces] UDP/TCP entries → crns host ifaces
//   4. TinyUSB composite per usb_mode (M3)
//   5. crns host loop start, identity from NVS (M5)
//   6. esp_http_server + captive DNS serving ../ui/static + /api (M4)

}  // namespace micro::main