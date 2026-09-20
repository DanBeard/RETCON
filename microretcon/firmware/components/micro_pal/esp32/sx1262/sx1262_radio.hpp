#pragma once
// SX1262 SPI radio seam — the "big one" (DESIGN §4). Two callbacks +
// chip config, same shape rWatch's Sx1262Interface claims: drive the
// chip over SPI, feed crns's core/lora framer.
//
// PIN MAP: TO VERIFY against Seeed's Wio-SX1262 kit schematic (user is
// fetching the item number) + Meshtastic's variant file for the XIAO
// ESP32S3. Do NOT invent pins (PirateBot rule: static profile table,
// pin conflicts refused at mode-set).
//
// UNWRITTEN — seam header only.

#include <cstdint>

namespace micro::pal::esp32::sx1262 {

// Radio profile fixed to the Meshtastic-915 EU/US-default used by
// RETCON's RNode blocks: 914.875 MHz, BW 125 kHz, SF8, CR 4:5 — the same
// numbers retcon_profiles/micro.config carries, so the config values are
// the single source of truth and this struct is filled from it (never
// hardcoded past the defaults).
struct RadioProfile {
    uint32_t frequency_hz = 914'875'000;
    uint32_t bandwidth_hz = 125'000;
    uint8_t txpower_dbm = 14;
    uint8_t spreading_factor = 8;
    uint8_t coding_rate = 5;
};

}  // namespace micro::pal::esp32::sx1262