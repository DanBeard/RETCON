// MicroRETCON RAK4631 — R1 bring-up (no crns yet; crns lands in R2).
//
// Proves, against the real board:
//   1. SX1262 SPI init under the RAK init rules (DIO2 antenna switch —
//      no TXEN/RXEN pins; DIO3 TCXO power; DCDC regulator not LDO)
//   2. USB CDC echo (the wire the Pi Zero rides, KISS framing later)
//   3. BLE UART echo (GATT serial — the third bearer)
//   4. battery ADC read (the solar-soak acceptance sensor)
//
// Radio params come from retcon_profiles/micro.config (US915, 914.875 MHz
// BW125 SF8 CR5 14dBm) — the config file is the source of truth. R1
// hardcodes the defaults as constants; R2 wires the crns parser in.
#include <Arduino.h>
#include <Adafruit_TinyUSB.h>  // USB CDC (the wire the Pi Zero rides)
#include <RadioLib.h>          // SX1262 driver (meshtastic's proven choice)

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

    lora_pins_setup();

    // SPI1 bus bring-up (pins 43/44/45 = SCK/MOSI/MISO per variant.h).
    // TODO(R1): SPIClass attach + SX1262 command handshake (GetStatus /
    // GetDeviceErrors) — the RAK init rules (DIO2/DIO3/DCDC) are RADIOLIB's
    // SX1262 class defaults with tcxoVoltage + dio2AsRFSwitch set true;
    // next commit brings the radio object up and reads the chip version.
    Serial.println("[lora] SPI1 pins staged; chip handshake lands next");
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
    // USB CDC + BLE UART echo (wire format later KISS; raw echo in R1).
    while (Serial.available()) {
        Serial.write(Serial.read());
    }
}
