// POSIX compile-check for the firmware seams (DESIGN §9: everything above
// the radio seam is POSIX-first). Hosts the seam headers into a plain C++
// build and asserts the shapes — no ESP-IDF needed. Runs in CI on the
// firmware repo without any toolchain beyond host g++.
//
// M2 replaces the TODOs with the real seam implementations; the fake-radio
// unit tests (crns tests/test_espnow_interface.cpp pattern) then run the
// REAL test bodies here on POSIX, with hardware bringing the same bodies
// onto real radios.
#include "espnow_radio.hpp"
#include "sx1262_radio.hpp"
#include "usb_composite.hpp"

#include <cstdint>

// TODO M2: FakeEspNowRadio (records sends, replays recorded frames) —
// the unit-test vehicle for the host loop, mirroring crns's
// tests/test_espnow_interface.cpp. Lives here so it compiles on POSIX.

int main() {
    using namespace micro::pal::esp32;
    using micro::usb::UsbMode;
    // The seams exist and the default profile is the config's values.
    static_assert(sx1262::RadioProfile{}.frequency_hz == 914'875'000);
    static_assert(sx1262::RadioProfile{}.spreading_factor == 8);
    static_assert(espnow::ESPNOW_MTU == 1470);
    static_cast<void>(UsbMode::Gadget);
    return 0;
}