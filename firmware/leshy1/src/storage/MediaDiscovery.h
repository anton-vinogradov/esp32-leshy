#pragma once

#include <cstddef>
#include <cstdint>

#include "storage/StorageGuard.h"

namespace leshy1::storage {

enum class MediaDiscoveryStatus : std::uint8_t {
    Unknown,
    Declared,
    Absent,
    Detected,
    Fault,
};

enum class FilesystemKind : std::uint8_t {
    Unknown,
    Fat,
    LittleFs,
};

const char* mediaKindName(MediaKind kind);
const char* mediaDiscoveryStatusName(MediaDiscoveryStatus status);
const char* filesystemKindName(FilesystemKind filesystem);

struct MediaDiscovery final {
    MediaKind kind = MediaKind::Sd;
    MediaDiscoveryStatus status = MediaDiscoveryStatus::Unknown;
    bool slotDeclared = false;
    std::int16_t detectPin = -1;
    bool detectSampled = false;
    std::int8_t detectLevel = -1;
    bool detectAuthoritative = false;
    bool mountAttempted = false;
    bool mountedReadOnly = false;
    FilesystemKind filesystem = FilesystemKind::Unknown;
    const char* fingerprint = nullptr;
    std::uint64_t capacityBytes = 0;
    std::uint64_t freeBytes = 0;
    bool writeEnabled = false;
    const char* reason = nullptr;
};

enum class MediaDiscoveryValidation : std::uint8_t {
    Valid,
    InvalidReason,
    InvalidDetectSample,
    UnauthoritativePresenceClaim,
    MountStateInvalid,
    DetectedMetadataMissing,
    CapacityInvalid,
    WriteEnabled,
};

const char* mediaDiscoveryValidationName(MediaDiscoveryValidation status);
MediaDiscoveryValidation validateMediaDiscovery(const MediaDiscovery& discovery);
bool formatMediaDiscoveryJson(const MediaDiscovery& discovery, char* output,
                              std::size_t capacity);

class ReadOnlyMediaAdapter {
public:
    virtual ~ReadOnlyMediaAdapter() = default;
    virtual MediaDiscovery discoverReadOnly() = 0;
};

}  // namespace leshy1::storage
