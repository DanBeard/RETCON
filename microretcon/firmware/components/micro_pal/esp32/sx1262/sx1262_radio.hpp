#pragma once
// SX1262 over SPI for the Wio-SX1262 kit on XIAO ESP32S3 — M2.
//
// Driver SHAPE mirrors rWatch's Sx1262Interface (514 LOC, proven against
// the command set; rwatch_pal/esp32/sx1262) retargeted to this kit's pin
// map. rWatch's XL9555 expander RF-switch does NOT exist here — the
// Wio-SX1262 kit has no antenna-tuner expander.
//
// PIN MAP: TO VERIFY against Seeed's schematic before first flash. The
// kit mates with the XIAO expansion; Meshtastic's variant file for the
// Seeed XIAO S3 + Wio-SX1262 kit is the source of truth. Do NOT invent
// pins (PirateBot rule: static profile table, conflicts refused).
namespace micro::pal::esp32::sx1262 {
struct PinConfig {
    // int nss = ?; int dio1 = ?; int reset = ?; int busy = ?;
    // int mosi = ?; int miso = ?; int sck = ?;  // TO VERIFY at M2
};
}
