#pragma once

#include <stdint.h>

#include "../../core/runtime/Capabilities.h"

namespace leshy {
namespace board {
namespace esp32_div_v2 {

// Feasibility implementation of docs/v1/HARDWARE_ENVELOPE.md. The document is the
// design-time source of truth; this prototype must not silently override it. Some
// peripherals deliberately share pins and require matching conflict-domain leases.
namespace pins {
static constexpr int kStatusLed = 1;
// GPIO2 is also the midpoint of the VBAT divider. ADC use is disabled until HW-T09.
static constexpr int kBuzzer = 2;
static constexpr int kBacklight = 7;
static constexpr int kI2cSda = 8;
static constexpr int kI2cScl = 9;

static constexpr int kRadioSck = 12;
static constexpr int kRadioMiso = 13;
static constexpr int kRadioMosi = 11;

static constexpr int kNrfCe[3] = {15, 47, 14};
static constexpr int kNrfCsn[3] = {4, 48, 21};

static constexpr int kCc1101Cs = 5;
static constexpr int kCc1101Gdo0 = 6;
static constexpr int kCc1101Gdo2 = 3;

// SD is present on the main-board schematic. GPS and PN532 are code-only external
// assembly conventions: neither appears in the v2 schematic/BOM, and both conflict
// with CC1101 on GPIO5/6. PN532 reverses data direction on GPIO11/13.
static constexpr int kSdCs = 10;
static constexpr int kPn532Sck = 12;
static constexpr int kPn532Miso = 11;
static constexpr int kPn532Mosi = 13;
static constexpr int kPn532Cs = 5;
static constexpr int kGpsRx = 5;
static constexpr int kGpsTx = 6;
static constexpr int kIrRx = 21;
static constexpr int kIrTx = 14;
}  // namespace pins

// This bitset belongs to the feasibility runtime. Production 1.x uses a multi-state
// HardwareInventory; schematic presence alone does not imply functional detection.
static constexpr runtime::CapabilitySet kBuiltInCapabilities =
    runtime::capability(runtime::Capability::Wifi) |
    runtime::capability(runtime::Capability::Bluetooth) |
    runtime::capability(runtime::Capability::Display) |
    runtime::capability(runtime::Capability::Touch) |
    runtime::capability(runtime::Capability::Keypad) |
    runtime::capability(runtime::Capability::StatusLeds) |
    runtime::capability(runtime::Capability::Buzzer);

static constexpr runtime::CapabilitySet kProbeCapabilities =
    runtime::capability(runtime::Capability::Nrf24) |
    runtime::capability(runtime::Capability::Cc1101) |
    runtime::capability(runtime::Capability::Nfc) |
    runtime::capability(runtime::Capability::Gps) |
    runtime::capability(runtime::Capability::Infrared) |
    runtime::capability(runtime::Capability::SdCard);

}  // namespace esp32_div_v2
}  // namespace board
}  // namespace leshy
