#include "BoardStorageAdapter.h"

#include <driver/gpio.h>

#include "boards/esp32_div_v2/BoardProfile.h"

namespace leshy1::platform::arduino {

storage::MediaDiscovery BoardStorageAdapter::discoverReadOnly() {
    storage::MediaDiscovery discovery;
    discovery.kind = storage::MediaKind::Sd;
    discovery.status = storage::MediaDiscoveryStatus::Unknown;
    discovery.slotDeclared = true;
    discovery.detectPin = boards::esp32_div_v2::BoardProfile::kSdDetectPin;
    discovery.detectSampled = true;
    discovery.detectLevel = static_cast<std::int8_t>(gpio_get_level(
        static_cast<gpio_num_t>(boards::esp32_div_v2::BoardProfile::kSdDetectPin)));
    discovery.detectAuthoritative = false;
    discovery.mountAttempted = false;
    discovery.mountedReadOnly = false;
    discovery.filesystem = storage::FilesystemKind::Unknown;
    discovery.fingerprint = nullptr;
    discovery.capacityBytes = 0;
    discovery.freeBytes = 0;
    discovery.writeEnabled = false;
    discovery.reason = "polarity_unverified_no_mount";
    return discovery;
}

}  // namespace leshy1::platform::arduino
