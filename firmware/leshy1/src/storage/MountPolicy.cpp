#include "MountPolicy.h"

namespace leshy1::storage {

const char* readOnlyMountStatusName(ReadOnlyMountStatus status) {
    switch (status) {
        case ReadOnlyMountStatus::Permitted: return "permitted";
        case ReadOnlyMountStatus::InvalidDiscovery: return "invalid_discovery";
        case ReadOnlyMountStatus::SlotUnavailable: return "slot_unavailable";
        case ReadOnlyMountStatus::AlreadyAttempted: return "already_attempted";
        case ReadOnlyMountStatus::ExplicitTargetRequired: return "explicit_target_required";
        case ReadOnlyMountStatus::DriverNotReadOnly: return "driver_not_read_only";
        case ReadOnlyMountStatus::FormatForbidden: return "format_forbidden";
        case ReadOnlyMountStatus::ResourcesMissing: return "resources_missing";
        case ReadOnlyMountStatus::ResourceConflict: return "resource_conflict";
    }
    return "invalid_discovery";
}

ReadOnlyMountPermit authorizeReadOnlyMountAttempt(const MediaDiscovery& discovery,
                                                  const ReadOnlyMountRequest& request) {
    const kernel::runtime::ResourceMask required =
        kernel::runtime::resourceMask(kernel::runtime::Resource::Storage) |
        kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi);
    ReadOnlyMountPermit permit{ReadOnlyMountStatus::InvalidDiscovery, required};
    if (validateMediaDiscovery(discovery) != MediaDiscoveryValidation::Valid) return permit;
    if (!discovery.slotDeclared || discovery.kind != MediaKind::Sd ||
        discovery.status == MediaDiscoveryStatus::Absent ||
        discovery.status == MediaDiscoveryStatus::Fault) {
        permit.status = ReadOnlyMountStatus::SlotUnavailable;
        return permit;
    }
    if (discovery.mountAttempted) {
        permit.status = ReadOnlyMountStatus::AlreadyAttempted;
        return permit;
    }
    if (!request.explicitlySelected) {
        permit.status = ReadOnlyMountStatus::ExplicitTargetRequired;
        return permit;
    }
    if (!request.driverReadOnlyGuaranteed) {
        permit.status = ReadOnlyMountStatus::DriverNotReadOnly;
        return permit;
    }
    if (request.formatRequested) {
        permit.status = ReadOnlyMountStatus::FormatForbidden;
        return permit;
    }
    if ((request.ownedResources & required) != required) {
        permit.status = ReadOnlyMountStatus::ResourcesMissing;
        return permit;
    }
    if (request.conflictingOwner) {
        permit.status = ReadOnlyMountStatus::ResourceConflict;
        return permit;
    }
    permit.status = ReadOnlyMountStatus::Permitted;
    return permit;
}

}  // namespace leshy1::storage
