#pragma once

#include <stdint.h>

namespace leshy {
namespace runtime {

// Physical abilities of a board. A feature declares what it needs; the boot-time
// hardware probe narrows the board profile to what is actually present.
enum class Capability : uint8_t {
    Wifi = 0,
    Bluetooth,
    Nrf24,
    Cc1101,
    Nfc,
    Gps,
    Infrared,
    SdCard,
    Display,
    Touch,
    Keypad,
    StatusLeds,
    Buzzer,
    Count
};

using CapabilitySet = uint32_t;
static_assert(static_cast<uint8_t>(Capability::Count) < 32, "CapabilitySet is too small");

constexpr CapabilitySet capability(Capability value) {
    return CapabilitySet{1} << static_cast<uint8_t>(value);
}

constexpr CapabilitySet operator|(Capability left, Capability right) {
    return capability(left) | capability(right);
}

constexpr CapabilitySet allCapabilities() {
    return (CapabilitySet{1} << static_cast<uint8_t>(Capability::Count)) - 1;
}

constexpr bool isValidCapabilitySet(CapabilitySet value) {
    return (value & ~allCapabilities()) == 0;
}

constexpr bool hasAllCapabilities(CapabilitySet available, CapabilitySet required) {
    return (available & required) == required;
}

}  // namespace runtime
}  // namespace leshy
