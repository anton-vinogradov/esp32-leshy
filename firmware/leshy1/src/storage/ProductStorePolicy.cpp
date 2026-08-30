#include "ProductStorePolicy.h"

#include <cstring>

namespace leshy1::storage {
namespace {

constexpr kernel::runtime::ResourceMask kProductStoreResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage) |
    kernel::runtime::resourceMask(kernel::runtime::Resource::RadioSpi);

bool validFingerprint(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    for (std::size_t index = 0; index <= kFingerprintMax; ++index) {
        const char current = value[index];
        if (current == '\0') return true;
        if (index == kFingerprintMax) return false;
        const bool alphaNumeric =
            (current >= 'a' && current <= 'z') ||
            (current >= 'A' && current <= 'Z') ||
            (current >= '0' && current <= '9');
        if (!alphaNumeric && current != '-' && current != '_' && current != ':') {
            return false;
        }
    }
    return false;
}

bool exactRoot(const char* value) {
    if (value == nullptr) return false;
    constexpr std::size_t expectedLength = 18;
    static_assert(sizeof("/leshy/sessions/v1") - 1U == expectedLength,
                  "product root length changed");
    return std::strncmp(value, kProductSessionStoreRoot, expectedLength) == 0 &&
           value[expectedLength] == '\0';
}

ProductStorePermit rejected(ProductStoreAccessStatus status,
                            const ProductStoreRequest& request) {
    return {status, request.operation, kProductStoreResources,
            kProductSessionStoreRoot, 0, false, false};
}

}  // namespace

const char* productStoreOperationName(ProductStoreOperation operation) {
    switch (operation) {
        case ProductStoreOperation::RecoverCatalog: return "recover_catalog";
        case ProductStoreOperation::InitializeStore: return "initialize_store";
        case ProductStoreOperation::CommitSession: return "commit_session";
    }
    return "recover_catalog";
}

const char* productStoreAccessStatusName(ProductStoreAccessStatus status) {
    switch (status) {
        case ProductStoreAccessStatus::Permitted: return "permitted";
        case ProductStoreAccessStatus::MissingMedia: return "missing_media";
        case ProductStoreAccessStatus::InvalidMediaGeometry:
            return "invalid_media_geometry";
        case ProductStoreAccessStatus::ExplicitSelectionRequired:
            return "explicit_selection_required";
        case ProductStoreAccessStatus::InvalidFingerprint:
            return "invalid_fingerprint";
        case ProductStoreAccessStatus::FingerprintMismatch:
            return "fingerprint_mismatch";
        case ProductStoreAccessStatus::InvalidRoot: return "invalid_root";
        case ProductStoreAccessStatus::RootMissing: return "root_missing";
        case ProductStoreAccessStatus::RootAlreadyExists:
            return "root_already_exists";
        case ProductStoreAccessStatus::ReadOnlyDriverRequired:
            return "read_only_driver_required";
        case ProductStoreAccessStatus::WritableDriverRequired:
            return "writable_driver_required";
        case ProductStoreAccessStatus::FormatForbidden: return "format_forbidden";
        case ProductStoreAccessStatus::InvalidSize: return "invalid_size";
        case ProductStoreAccessStatus::InsufficientSpace:
            return "insufficient_space";
        case ProductStoreAccessStatus::ResourcesMissing:
            return "resources_missing";
        case ProductStoreAccessStatus::ResourceConflict:
            return "resource_conflict";
        case ProductStoreAccessStatus::PowerUnsafe:
            return "power_unsafe";
    }
    return "missing_media";
}

ProductStorePermit authorizeProductStore(const MediaIdentity& media,
                                         const ProductStoreRequest& request) {
    if (!media.present) {
        return rejected(ProductStoreAccessStatus::MissingMedia, request);
    }
    if (media.capacityBytes == 0 || media.freeBytes > media.capacityBytes) {
        return rejected(ProductStoreAccessStatus::InvalidMediaGeometry, request);
    }
    if (request.operation != ProductStoreOperation::RecoverCatalog &&
        !request.explicitlySelected) {
        return rejected(ProductStoreAccessStatus::ExplicitSelectionRequired,
                        request);
    }
    if (!validFingerprint(media.fingerprint) ||
        !validFingerprint(request.expectedFingerprint)) {
        return rejected(ProductStoreAccessStatus::InvalidFingerprint, request);
    }
    if (std::strncmp(media.fingerprint, request.expectedFingerprint,
                     kFingerprintMax + 1U) != 0) {
        return rejected(ProductStoreAccessStatus::FingerprintMismatch, request);
    }
    if (!exactRoot(request.rootPath)) {
        return rejected(ProductStoreAccessStatus::InvalidRoot, request);
    }
    if (request.formatRequested) {
        return rejected(ProductStoreAccessStatus::FormatForbidden, request);
    }

    const bool recovery =
        request.operation == ProductStoreOperation::RecoverCatalog;
    const bool initialize =
        request.operation == ProductStoreOperation::InitializeStore;
    if (initialize ? request.rootExists : !request.rootExists) {
        return rejected(initialize
                            ? ProductStoreAccessStatus::RootAlreadyExists
                            : ProductStoreAccessStatus::RootMissing,
                        request);
    }
    if (recovery &&
        (!request.driverReadOnlyGuaranteed || request.driverWriteEnabled)) {
        return rejected(ProductStoreAccessStatus::ReadOnlyDriverRequired,
                        request);
    }
    if (!recovery &&
        (request.driverReadOnlyGuaranteed || !request.driverWriteEnabled)) {
        return rejected(ProductStoreAccessStatus::WritableDriverRequired,
                        request);
    }
    if (!recovery &&
        (request.requiredBytes == 0 ||
         request.reserveBytes > UINT64_MAX - request.requiredBytes)) {
        return rejected(ProductStoreAccessStatus::InvalidSize, request);
    }
    if (!recovery &&
        (media.capacityBytes < media.freeBytes ||
         media.freeBytes < request.requiredBytes + request.reserveBytes)) {
        return rejected(ProductStoreAccessStatus::InsufficientSpace, request);
    }
    if ((request.ownedResources & kProductStoreResources) !=
        kProductStoreResources) {
        return rejected(ProductStoreAccessStatus::ResourcesMissing, request);
    }
    if (request.conflictingOwner) {
        return rejected(ProductStoreAccessStatus::ResourceConflict, request);
    }
    if (!recovery && request.power ==
            services::power::PowerWriteDisposition::ProhibitedLowVoltage) {
        return rejected(ProductStoreAccessStatus::PowerUnsafe, request);
    }
    return {ProductStoreAccessStatus::Permitted, request.operation,
            kProductStoreResources, kProductSessionStoreRoot,
            recovery ? 0 : request.requiredBytes, request.rootExists,
            !recovery};
}

}  // namespace leshy1::storage
