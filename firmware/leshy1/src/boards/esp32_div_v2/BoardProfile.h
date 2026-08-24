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
    static constexpr int kIrTxPin = 14;
    static constexpr int kIrRxPin = 21;
    static constexpr int kCc1101CsPin = 5;
    static constexpr std::uint32_t kSdIdentificationSpiHz = 100000;

    // The measured board-01 assembly carries the stock RF shield, while external
    // GPS/PN532 modules are excluded. Receiver identity is still probed only from
    // explicit Full/Guided Self-Test, never automatically during boot.
    static constexpr bool kRfShieldDeclared = true;
    // Temporary read-only fault-localization candidate. Full/Guided Self-Test
    // samples each carrier CSN as an input under its weak pull-up, then exits
    // before generating any SPI clock. Remove this gate after board-02 has a
    // retained carrier diagnosis and the product receiver probe is restored.
    static constexpr bool kRfCarrierChipSelectCharacterizationOnly = false;

    // HW-U05: external assemblies are never autodetected. IR RX/TX belongs to
    // the declared stock RF shield and is time-multiplexed with nRF slot 3;
    // availability still requires a user-started HIL signal, never boot probing.
    static constexpr bool kGpsDeclared = false;
    static constexpr bool kPn532Declared = false;
    static constexpr bool kIrDeclared = true;
};

}  // namespace leshy1::boards::esp32_div_v2
