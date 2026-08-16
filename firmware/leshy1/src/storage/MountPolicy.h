#pragma once

#include <cstdint>

#include "kernel/runtime/Resources.h"
#include "storage/MediaDiscovery.h"

namespace leshy1::storage {

struct ReadOnlyMountRequest final {
    bool explicitlySelected = false;
    bool driverReadOnlyGuaranteed = false;
    bool formatRequested = false;
    kernel::runtime::ResourceMask ownedResources = 0;
    bool conflictingOwner = false;
};

enum class ReadOnlyMountStatus : std::uint8_t {
    Permitted,
    InvalidDiscovery,
    SlotUnavailable,
    AlreadyAttempted,
    ExplicitTargetRequired,
    DriverNotReadOnly,
    FormatForbidden,
    ResourcesMissing,
    ResourceConflict,
};

const char* readOnlyMountStatusName(ReadOnlyMountStatus status);

struct ReadOnlyMountPermit final {
    ReadOnlyMountStatus status = ReadOnlyMountStatus::InvalidDiscovery;
    kernel::runtime::ResourceMask requiredResources = 0;

    bool allowed() const { return status == ReadOnlyMountStatus::Permitted; }
};

ReadOnlyMountPermit authorizeReadOnlyMountAttempt(const MediaDiscovery& discovery,
                                                  const ReadOnlyMountRequest& request);

}  // namespace leshy1::storage
