#pragma once
// The ESP-NOW radio seam — MicroRETCON's IByteStream-equivalent for the
// connectionless bearer. Mirrors crns's IEspNowRadio exactly (vendored
// crns pal/espnow/espnow_interface.hpp is the pure-logic reference; the
// piratebot + rWatch ESP32 PALs are the two proven ESP-IDF concretes to
// crib from).
//
// Open/broadcast/online: ESP-NOW v2 has no pairing, no framer, no AP.
// 1470-byte payload cap NEEDS ESP-IDF >= 5.4.2 (5.3.2 pins v1 at 250 B —
// sdkconfig.defaults records this; version decision at M2 start).
//
// UNWRITTEN — seam header only, so M2's implementation and the fake-radio
// unit tests (crns tests/test_espnow_interface.cpp pattern) can be built
// against the same shape on POSIX before real hardware.

#include <cstddef>
#include <cstdint>

namespace micro::pal::esp32::espnow {

// Broadcast MTU per ESP-NOW v2 (design: no framer). VERIFY against the
// pinned IDF's esp_now.h at M2 — the header constant is authoritative,
// not this comment.
inline constexpr size_t ESPNOW_MTU = 1470;

class IEspNowRadio {
public:
    virtual ~IEspNowRadio() = default;

    // Send a broadcast frame. Returns bytes sent or negative errno.
    virtual int send(const uint8_t* data, size_t len) = 0;

    // Delivered from the WiFi task: ESP-NOW recv → queue → on_bytes()
    // (DESIGN §4 architecture diagram). Implementations must not block.
    virtual void on_bytes(const uint8_t* data, size_t len) = 0;
};

}  // namespace micro::pal::esp32::espnow