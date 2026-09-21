// MicroRETCON device main — crns host loop wiring.
//
// Status: SCAFFOLD. The host loop, config bridge ([micro] section), and
// interface registration land with sprint M2
// (../../docs/MICRORETCON-SPRINTS.md). The POSIX-side proof of every
// flow this will run lives in ../ui/mock_server.py (contract) and the
// crns binding tests (mechanics).
#include <cstdint>
extern "C" void app_main(void) {
    // M2: init NVS, mount FAT, parse config, bring up interfaces
    // (espnow + sx1262 + usb cdc), start the crns host loop, serve /api.
    for (;;) {}
}
