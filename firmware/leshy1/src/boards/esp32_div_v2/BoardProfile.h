#pragma once

#include <cstdint>

namespace leshy1::boards::esp32_div_v2 {

// Implementation of the constrained HW-U dispositions. The normative source is
// docs/v1/HARDWARE_ENVELOPE.md; this profile never upgrades an unknown capability.
struct BoardProfile final {
    static constexpr const char* kId = "esp32-div-v2-n16";
    static constexpr const char* kEnvelopeRevision = "S1-2026-08-16";
    static constexpr std::uint32_t kExpectedFlashBytes = 16U * 1024U * 1024U;
    static constexpr bool kExpectedPsram = false;

    // HW-U02: GPIO0 is BOOT-only until continuity evidence exists.
    static constexpr int kDisplayResetPin = -1;
    static constexpr int kBacklightPin = 7;
    // The v2 buzzer transistor is active-high on GPIO2. The same node is tied
    // into the stock battery-divider circuit, so an unconfigured input can
    // produce an audible false low-battery alarm. Clean 1.x owns the pin from
    // the first setup instruction and keeps it output-low until an explicit,
    // safety-reviewed sound service exists.
    static constexpr int kBuzzerPin = 2;
    static constexpr int kI2cSdaPin = 8;
    static constexpr int kI2cSclPin = 9;
    static constexpr std::uint8_t kPcf8574Address = 0x20;

    // HW-U06: the signal is sampled without reconfiguration, but its polarity is
    // not authoritative until HW-T05. It cannot by itself claim card presence.
    static constexpr int kSdDetectPin = 38;
    static constexpr int kRadioMosiPin = 11;
    static constexpr int kRadioSckPin = 12;
    static constexpr int kRadioMisoPin = 13;
    static constexpr int kSdCsPin = 10;
    static constexpr int kNrfCePins[3] = {15, 47, 14};
    static constexpr int kNrfCsPins[3] = {4, 48, 21};
    static constexpr int kCc1101CsPin = 5;
    static constexpr std::uint32_t kSdIdentificationSpiHz = 400000;

    // HW-U05/U09: external assemblies and IR are never autodetected.
    static constexpr bool kGpsDeclared = false;
    static constexpr bool kPn532Declared = false;
    static constexpr bool kIrDeclared = false;
};

}  // namespace leshy1::boards::esp32_div_v2
