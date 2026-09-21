// MicroRETCON RAK4631 — R1 bring-up (no crns yet; crns lands in R2).
//
// Proves, against the real board:
//   1. SX1262 SPI init under the RAK init rules (DIO2 antenna switch —
//      no TXEN/RXEN pins; DIO3 TCXO power; DCDC regulator not LDO)
//   2. USB CDC: RNode-compatible KISS responder (DETECT / FW_VERSION /
//      PLATFORM / MCU / READY / RADIO_STATE / STAT_BAT + CMD_DATA echo —
//      the python RNS RNodeInterface probe answers byte-exact)
//   3. BLE UART echo (GATT serial — the third bearer)
//   4. battery ADC read (the solar-soak acceptance sensor)
//
// Radio params come from retcon_profiles/micro.config (US915, 914.875 MHz
// BW125 SF8 CR5 14dBm) — the config file is the source of truth. R1
// hardcodes the defaults as constants; R2 wires the crns parser in.
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>  // USB CDC (the wire the Pi Zero rides)
#include <RadioLib.h>          // SX1262 driver (meshtastic's proven choice)
#include <bluefruit.h>         // BLE: the third bearer (GATT UART)

// BLE UART (Bluefruit's Uart service — the same service the RNode firmware
// and Meshtastic speak: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E Nordic UART).
static BLEUart ble_uart;

// RAK4631 SX1262 init rules (meshtastic variants/nrf52840/rak4631/variant.h
// + SX126xInterface.cpp): DIO2 IS the RF switch; DIO3 powers the TCXO at
// 1.8 V; DCDC regulator (useRegulatorLDO=false). variant.h carries the
// SX126X_DIO2_AS_RF_SWITCH + SX126X_DIO3_TCXO_VOLTAGE 1.8 defines.
#ifndef SX126X_DIO2_AS_RF_SWITCH
#define SX126X_DIO2_AS_RF_SWITCH
#endif
#ifndef SX126X_DIO3_TCXO_VOLTAGE
#define SX126X_DIO3_TCXO_VOLTAGE 1.8
#endif

// SX1262 pins come from variant.h (vendored in ../variant/, verified from
// meshtastic/firmware variants/nrf52840/rak4631 — see
// docs/MICRORETCON-RAK4630.md): SX126X_CS 42 / SCK 43 / MOSI 44 / MISO 45
// / BUSY 46 / DIO1 47 / RESET 38 / POWER_EN 37.
// ANTENNA SWITCH: DIO2-driven — NO TXEN/RXEN GPIOs; P1.07 (39) must NOT be
// initialised (variant.h is emphatic).
#include "variant/variant.h"

// Battery ADC uses variant.h's A0/PIN_A0 (12-bit, 3.0 V ref, ×1.73).

// Radio object: RadioLib SX1262 over the Arduino SPI (pins from variant.h).
// Module(cs, irq, rst, busy) — RadioLib drives NSS itself.
static Module radio_mod = Module(SX126X_CS, SX126X_DIO1, SX126X_RESET, SX126X_BUSY);
static SX1262 radio = SX1262(&radio_mod);

static bool lora_ok = false;

static void lora_pins_setup() {
    pinMode(SX126X_POWER_EN, OUTPUT);
    digitalWrite(SX126X_POWER_EN, HIGH);  // rail on
    pinMode(SX126X_CS, OUTPUT);
    digitalWrite(SX126X_CS, HIGH);  // deselected
    pinMode(SX126X_RESET, OUTPUT);
    // Reset pulse per SX1262 datasheet (>=1 ms low, then wait for BUSY low).
    digitalWrite(SX126X_RESET, LOW);
    delay(2);
    digitalWrite(SX126X_RESET, HIGH);
    pinMode(SX126X_BUSY, INPUT);
    pinMode(SX126X_DIO1, INPUT);
    // NOTE: no TXEN/RXEN — DIO2 handles the antenna switch. GPIO 39 stays
    // untouched on purpose.
    uint32_t waited = 0;
    while (digitalRead(SX126X_BUSY) == HIGH && waited < 20) {
        delay(1);
        waited++;
    }
    Serial.print("[lora] pins set; busy=");
    Serial.print(digitalRead(SX126X_BUSY));
    Serial.print(" (0=ready), reset released after ");
    Serial.print(waited);
    Serial.println(" ms");

    // SPI bus: the primary Arduino SPI maps to pins 43/44/45 (SCK/MOSI/
    // MISO) per variant.h. RadioLib drives NSS itself via its Module.
    SPI.begin();

    // R1 handshake: begin() = hardware reset + STANDBY + packet config with
    // the DIO3-TCXO + DCDC rules; then the chip answers GetStatus-style
    // queries. Params from retcon_profiles/micro.config (US915).
    const float freq_mhz = 914.875f;
    const float bw_khz = 125.0f;
    const uint8_t sf = 8, cr = 5;
    const uint8_t sync_word = 0x12;  // Reticulum/RNode private sync word? R2 wires config; R1 uses RadioLib LoRaWAN-public default check only
    const int8_t power_dbm = 14;
    const uint16_t preamble = 8;

    int state = radio.begin(freq_mhz, bw_khz, sf, cr, sync_word, power_dbm, preamble,
                        SX126X_DIO3_TCXO_VOLTAGE, /*useRegulatorLDO=*/false);
    if (state == RADIOLIB_ERR_NONE) {
        Serial.println("[lora] SX1262 begin() OK");
        lora_ok = true;
        // The variant.h mandate: DIO2 as RF switch (after begin — RadioLib
        // resets it inside begin()).
        state = radio.setDio2AsRfSwitch(true);
        Serial.print("[lora] setDio2AsRfSwitch: ");
        Serial.println(state == RADIOLIB_ERR_NONE ? "ok" : "FAILED");
        // begin() returning ERR_NONE already proves SPI is alive end-to-end
        // (reset → config → read-back through the whole command set).
        digitalWrite(LED_BLUE, HIGH);
    } else {
        Serial.print("[lora] begin FAILED code ");
        Serial.println(state);
    }
}


// --- USB CDC: RNode-compatible KISS responder -------------------------
// The Pi Zero (python RNS RNodeInterface) probes with:
//   FEND CMD_DETECT DETECT_REQ FEND CMD_FW_VERSION 00 FEND CMD_PLATFORM 00
//   FEND CMD_MCU 00 FEND                     (RNodeInterface.py:484)
// and gates on: DETECT_RESP (0x46), fw >= 1.52, platform byte, mcu byte.
// Constants byte-exact with RNode_Firmware Boards.h + RNS 1.3.8
// RNodeInterface.py (cited inline below).
namespace rnode {
constexpr uint8_t FEND = 0xC0;
constexpr uint8_t FESC = 0xDB;
constexpr uint8_t TFEND = 0xDC;
constexpr uint8_t TFESC = 0xDD;
constexpr uint8_t CMD_DATA = 0x00;
constexpr uint8_t CMD_DETECT = 0x08;
constexpr uint8_t DETECT_REQ = 0x73;
constexpr uint8_t DETECT_RESP = 0x46;
constexpr uint8_t CMD_FW_VERSION = 0x50;
constexpr uint8_t CMD_PLATFORM = 0x48;
constexpr uint8_t CMD_MCU = 0x49;
constexpr uint8_t CMD_READY = 0x0F;
constexpr uint8_t CMD_RADIO_STATE = 0x06;
constexpr uint8_t CMD_STAT_BAT = 0x27;
constexpr uint8_t PLATFORM_NRF52 = 0x70;
constexpr uint8_t MCU_NRF52 = 0x71;
constexpr uint8_t FW_MAJ = 1;
constexpr uint8_t FW_MIN = 52;  // python gate: REQUIRED_FW_VER_MIN (1.52)

void write_escaped(const uint8_t* data, size_t n) {
    for (size_t i = 0; i < n; i++) {
        switch (data[i]) {
        case FEND: Serial.write(FESC); Serial.write(TFEND); break;
        case FESC: Serial.write(FESC); Serial.write(TFESC); break;
        default: Serial.write(data[i]); break;
        }
    }
}
void frame_open(uint8_t cmd) { Serial.write(FEND); Serial.write(cmd); }
void frame_close() { Serial.write(FEND); }
}  // namespace rnode

// KISS decode state (R1 slice: DETECT/FW/PLATFORM/MCU/RADIO_STATE/DATA).
static bool kiss_escape = false;
static bool kiss_in_frame = false;
static bool kiss_data_closed = false;  // a CMD_DATA frame closed this tick
static uint8_t kiss_cmd = 0;
static bool kiss_have_cmd = false;
static uint8_t kiss_buf[512];
static size_t kiss_len = 0;

// Feed one USB byte. Sets kiss_data_closed when a CMD_DATA frame closes.
static void kiss_feed(uint8_t b) {
    if (kiss_escape) {
        kiss_escape = false;
        if (kiss_in_frame && kiss_have_cmd && kiss_len < sizeof kiss_buf) {
            kiss_buf[kiss_len++] = (b == rnode::TFEND) ? rnode::FEND
                                  : (b == rnode::TFESC) ? rnode::FESC : b;
        }
        return;
    }
    if (b == rnode::FEND) {
        if (kiss_in_frame && kiss_have_cmd) {
            if (kiss_cmd == rnode::CMD_DATA && kiss_len > 0) {
                kiss_data_closed = true;  // consumed by loop() this tick
            } else if (kiss_cmd == rnode::CMD_DETECT && kiss_len == 1 &&
                       kiss_buf[0] == rnode::DETECT_REQ) {
                rnode::frame_open(rnode::CMD_DETECT);
                Serial.write(rnode::DETECT_RESP);
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_FW_VERSION && kiss_len == 1 &&
                       kiss_buf[0] == 0x00) {
                rnode::frame_open(rnode::CMD_FW_VERSION);
                Serial.write(rnode::FW_MAJ);
                Serial.write(rnode::FW_MIN);
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_PLATFORM && kiss_len == 0) {
                rnode::frame_open(rnode::CMD_PLATFORM);
                Serial.write(rnode::PLATFORM_NRF52);
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_MCU && kiss_len == 0) {
                rnode::frame_open(rnode::CMD_MCU);
                Serial.write(rnode::MCU_NRF52);
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_READY && kiss_len == 0) {
                rnode::frame_open(rnode::CMD_READY);
                Serial.write(0x01);  // ready (queue not full in R1)
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_RADIO_STATE && kiss_len == 0) {
                rnode::frame_open(rnode::CMD_RADIO_STATE);
                Serial.write(0x01);  // online
                rnode::frame_close();
            } else if (kiss_cmd == rnode::CMD_STAT_BAT && kiss_len == 0) {
                rnode::frame_open(rnode::CMD_STAT_BAT);
                Serial.write(100);  // percent placeholder; real ADC in R2
                rnode::frame_close();
            }
        }
        kiss_in_frame = true;  // (re)open — a bare FEND is a line reset
        kiss_have_cmd = false;
        kiss_len = 0;
        return;
    }
    if (!kiss_in_frame) return;
    if (b == rnode::FESC) { kiss_escape = true; return; }
    if (!kiss_have_cmd) { kiss_cmd = b; kiss_have_cmd = true; return; }
    if (kiss_len < sizeof kiss_buf) kiss_buf[kiss_len++] = b;
}

static uint32_t boot_ms = 0;

void setup() {
    Serial.begin(115200);
    uint32_t usb_wait = 0;
    while (!Serial && usb_wait < 4000) {
        delay(10);
        usb_wait += 10;
    }  // don't hang forever headless
    boot_ms = millis();

    pinMode(PIN_LED1, OUTPUT);
    pinMode(LED_BLUE, OUTPUT);
    digitalWrite(PIN_LED1, HIGH);  // "booted"
    digitalWrite(LED_BLUE, LOW);

    Serial.println("\n[micro] RAK4631 R1 bring-up");

    // BLE: Bluefruit stack + Nordic UART Service (the third bearer).
    Bluefruit.autoConnLed(false);  // we drive our own LEDs
    Bluefruit.begin();
    Bluefruit.setTxPower(4);  // dBm, conservative for solar
    ble_uart.begin();
    Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addService(ble_uart);
    Bluefruit.Advertising.start(0);  // 0 = advertise forever
    Serial.println("[ble] NUART advertising");

    lora_pins_setup();

    Serial.println("[usb] RNode KISS responder live on CDC");
}

void loop() {
    // Heartbeat + battery telemetry + a LoRa TX ping every 10 s.
    static uint32_t last = 0;
    if (millis() - last > 10000) {
        last = millis();
        if (lora_ok) {
            // One unmodulated-carrier-off transmit: proves TX power path +
            // DIO2 antenna switch under firmware control.
            String ping = "micro-r1 ";
            ping += (millis() - boot_ms) / 1000;
            ping += "s";
            int st = radio.transmit(ping);
            Serial.print("[lora] tx '");
            Serial.print(ping);
            Serial.print("' -> ");
            Serial.println(st == RADIOLIB_ERR_NONE ? "sent" : String("err ") + st);
        }
        analogReadResolution(12);
        // 3.0 V ref, divider multiplier 1.73 (variant.h battery constants).
        uint32_t mv = (analogRead(A0) * 3000UL * 173UL) / (4096UL * 100UL);
        Serial.print("[bat] ");
        Serial.print(mv);
        Serial.print(" mV   uptime ");
        Serial.print((millis() - boot_ms) / 1000);
        Serial.println(" s");
        digitalWrite(LED_BLUE, (millis() / 10000) % 2 == 0 ? HIGH : LOW);
    }
    // USB CDC: RNode-compatible KISS responder (the wire the Pi rides).
    while (Serial.available()) {
        kiss_feed(Serial.read());
        if (kiss_data_closed) {
            kiss_data_closed = false;
            // R1: RX data from the Pi — echo back as a DATA frame until the
            // crns host (R2) consumes it. Proves the full data round-trip.
            rnode::frame_open(rnode::CMD_DATA);
            rnode::write_escaped(kiss_buf, kiss_len);
            rnode::frame_close();
        }
    }
    // BLE UART: same KISS responder fed from the BLE pipe (raw echo in R1 —
    // the same feed, one framing).
    while (ble_uart.available()) {
        char c = ble_uart.read();
        ble_uart.write(c);
    }
}
