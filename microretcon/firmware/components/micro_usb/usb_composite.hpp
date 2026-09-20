#pragma once
// USB postures (DESIGN §5) — TinyUSB composite. usb_mode picks:
//   transport: CDC-serial is a Reticulum interface (IByteStream → KISS
//              framing, parity with the Pi's serial RNode path)
//   gadget:    NCM/RNDIS ethernet + captive portal ("the cable is the
//              console") + CDC console for headless ops
//   serial:    plain CDC console only
// MSC drive (config + START_HERE.html + static UI) exists in ALL THREE —
// TinyUSB composite, read-only in v1 (the API writes the config file, no
// concurrent-mount hazard).
//
// UNWRITTEN — seam header only (M3/M4).

namespace micro::usb {

// Composite descriptor sets per posture; M3 fills these in.
enum class UsbMode : uint8_t { Gadget, Transport, Serial };

}  // namespace micro::usb