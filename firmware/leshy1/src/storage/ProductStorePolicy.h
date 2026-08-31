#pragma once

#include <cstdint>

#include "kernel/runtime/Resources.h"
#include "services/power/PowerSafetyPolicy.h"
#include "storage/StorageGuard.h"

namespace leshy1::storage {

constexpr const char* kProductSessionStoreRoot = "/leshy/sessions/v1";

enum class ProductStoreOperation : std::uint8_t {
    RecoverCatalog,
    InitializeStore,
    CommitSession,
    CommitEvidence,
};

const char* productStoreOperationName(ProductStoreOperation operation);

enum class ProductStoreAccessStatus : std::uint8_t {
    Permitted,
    MissingMedia,
    InvalidMediaGeometry,
    ExplicitSelectionRequired,
    InvalidFingerprint,
    FingerprintMismatch,
    InvalidRoot,
    RootMissing,
    RootAlreadyExists,
    ReadOnlyDriverRequired,
    WritableDriverRequired,
    FormatForbidden,
    InvalidSize,
    InsufficientSpace,
    ResourcesMissing,
    ResourceConflict,
    PowerUnsafe,
};

const char* productStoreAccessStatusName(ProductStoreAccessStatus status);

struct ProductStoreRequest final {
    ProductStoreOperation operation = ProductStoreOperation::RecoverCatalog;
    bool explicitlySelected = false;
    const char* expectedFingerprint = nullptr;
    const char* rootPath = nullptr;
    bool rootExists = false;
    bool driverReadOnlyGuaranteed = false;
    bool driverWriteEnabled = false;
    bool formatRequested = false;
    std::uint64_t requiredBytes = 0;
    std::uint64_t reserveBytes = 0;
    kernel::runtime::ResourceMask ownedResources = 0;
    bool conflictingOwner = false;
    services::power::PowerWriteDisposition power =
        services::power::PowerWriteDisposition::AtomicOnly;
};

struct ProductStorePermit final {
    ProductStoreAccessStatus status = ProductStoreAccessStatus::MissingMedia;
    ProductStoreOperation operation = ProductStoreOperation::RecoverCatalog;
    kernel::runtime::ResourceMask requiredResources = 0;
    const char* rootPath = nullptr;
    std::uint64_t byteLimit = 0;
    bool existingRootVerified = false;
    bool writable = false;

    bool allowed() const { return status == ProductStoreAccessStatus::Permitted; }
};

// Authorizes access only to the fixed product SessionStore root. Boot catalog
// recovery may be automatic for an already enrolled exact media fingerprint, but
// it must be read-only. Initialization and commits always require a fresh explicit
// user selection and a bounded byte budget. No operation permits formatting.
ProductStorePermit authorizeProductStore(const MediaIdentity& media,
                                         const ProductStoreRequest& request);

}  // namespace leshy1::storage
