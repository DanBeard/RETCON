#pragma once
// EspNowRadio : crns::pal::IEspNowRadio — M2.
// ~150 LOC per docs/MICRORETCON-DESIGN.md §4: esp_wifi_init +
// esp_now_init + broadcast send. Pins itself to WiFi STA mode NONE
// (ESP-NOW does not need an AP) and channel from [micro] espnow_channel.
// UNWRITTEN — scaffold stub.
#include <cstdint>
namespace micro::pal::esp32::espnow {
struct PinConfig {};  // ESP-NOW needs no pins; placeholder for symmetry
}
