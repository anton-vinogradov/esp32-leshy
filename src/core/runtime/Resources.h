#pragma once

#include <stdint.h>

namespace leshy {
namespace runtime {

// Exclusive runtime resources. These are conflict domains, not merely chips:
// SharedRadioSpi prevents CC1101/NRF24/PN532/SD drivers from reconfiguring the
// same bus concurrently, while shared-pin domains model the ESP32-DIV v2 wiring.
enum class Resource : uint8_t {
    EspWifiRadio = 0,
    EspBluetoothRadio,
    BluetoothMemory,
    SharedRadioSpi,
    Nrf24Array,
    Cc1101,
    Nfc,
    GpsUart,
    Infrared,
    SdCard,
    SharedCcGpsPins,
    SharedNrfIrPins,
    NetworkStack,
    FileSystem,
    Count
};

using ResourceSet = uint32_t;
static_assert(static_cast<uint8_t>(Resource::Count) < 32, "ResourceSet is too small");

constexpr ResourceSet resource(Resource value) {
    return ResourceSet{1} << static_cast<uint8_t>(value);
}

constexpr ResourceSet operator|(Resource left, Resource right) {
    return resource(left) | resource(right);
}

constexpr ResourceSet allResources() {
    return (ResourceSet{1} << static_cast<uint8_t>(Resource::Count)) - 1;
}

constexpr bool isValidResourceSet(ResourceSet value) {
    return (value & ~allResources()) == 0;
}

}  // namespace runtime
}  // namespace leshy
