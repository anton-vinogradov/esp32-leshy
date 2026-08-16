#pragma once

#include "storage/MediaDiscovery.h"

namespace leshy1::platform::arduino {

class BoardStorageAdapter final : public storage::ReadOnlyMediaAdapter {
public:
    // Arduino SDFS::begin has no read-only mount parameter and exposes raw writes.
    // It cannot satisfy the 1.x read-only discovery gate.
    static constexpr bool kDriverReadOnlyGuaranteed = false;

    storage::MediaDiscovery discoverReadOnly() override;
};

}  // namespace leshy1::platform::arduino
