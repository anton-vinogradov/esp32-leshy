#include "MediaDiscovery.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

bool boundedReason(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    constexpr std::size_t kReasonMax = 64;
    for (std::size_t index = 0; index <= kReasonMax; ++index) {
        const char current = value[index];
        if (current == '\0') return true;
        if (index == kReasonMax) return false;
        const bool alphaNumeric =
            (current >= 'a' && current <= 'z') ||
            (current >= 'A' && current <= 'Z') ||
            (current >= '0' && current <= '9');
        if (!alphaNumeric && current != '-' && current != '_') return false;
    }
    return false;
}

bool boundedFingerprint(const char* value) {
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

}  // namespace

const char* mediaKindName(MediaKind kind) {
    switch (kind) {
        case MediaKind::Sd: return "sd";
        case MediaKind::LittleFs: return "littlefs";
    }
    return "unknown";
}

const char* mediaDiscoveryStatusName(MediaDiscoveryStatus status) {
    switch (status) {
        case MediaDiscoveryStatus::Unknown: return "unknown";
        case MediaDiscoveryStatus::Declared: return "declared";
        case MediaDiscoveryStatus::Absent: return "absent";
        case MediaDiscoveryStatus::Detected: return "detected";
        case MediaDiscoveryStatus::Fault: return "fault";
    }
    return "unknown";
}

const char* filesystemKindName(FilesystemKind filesystem) {
    switch (filesystem) {
        case FilesystemKind::Unknown: return "unknown";
        case FilesystemKind::Fat: return "fat";
        case FilesystemKind::LittleFs: return "littlefs";
    }
    return "unknown";
}

const char* mediaDiscoveryValidationName(MediaDiscoveryValidation status) {
    switch (status) {
        case MediaDiscoveryValidation::Valid: return "valid";
        case MediaDiscoveryValidation::InvalidReason: return "invalid_reason";
        case MediaDiscoveryValidation::InvalidDetectSample: return "invalid_detect_sample";
        case MediaDiscoveryValidation::UnauthoritativePresenceClaim:
            return "unauthoritative_presence_claim";
        case MediaDiscoveryValidation::MountStateInvalid: return "mount_state_invalid";
        case MediaDiscoveryValidation::DetectedMetadataMissing:
            return "detected_metadata_missing";
        case MediaDiscoveryValidation::CapacityInvalid: return "capacity_invalid";
        case MediaDiscoveryValidation::WriteEnabled: return "write_enabled";
    }
    return "invalid_reason";
}

MediaDiscoveryValidation validateMediaDiscovery(const MediaDiscovery& discovery) {
    if (!boundedReason(discovery.reason)) {
        return MediaDiscoveryValidation::InvalidReason;
    }
    if (discovery.writeEnabled) return MediaDiscoveryValidation::WriteEnabled;
    if ((!discovery.detectSampled && discovery.detectLevel != -1) ||
        (discovery.detectSampled && discovery.detectLevel != 0 &&
         discovery.detectLevel != 1)) {
        return MediaDiscoveryValidation::InvalidDetectSample;
    }
    if (!discovery.detectAuthoritative &&
        (discovery.status == MediaDiscoveryStatus::Absent ||
         discovery.status == MediaDiscoveryStatus::Detected)) {
        return MediaDiscoveryValidation::UnauthoritativePresenceClaim;
    }
    if (discovery.mountedReadOnly && !discovery.mountAttempted) {
        return MediaDiscoveryValidation::MountStateInvalid;
    }
    if (discovery.status == MediaDiscoveryStatus::Detected) {
        if (!discovery.mountAttempted || !discovery.mountedReadOnly ||
            discovery.filesystem == FilesystemKind::Unknown ||
            !boundedFingerprint(discovery.fingerprint)) {
            return MediaDiscoveryValidation::DetectedMetadataMissing;
        }
        if (discovery.capacityBytes == 0 ||
            discovery.freeBytes > discovery.capacityBytes) {
            return MediaDiscoveryValidation::CapacityInvalid;
        }
    } else if (discovery.capacityBytes != 0 || discovery.freeBytes != 0 ||
               discovery.filesystem != FilesystemKind::Unknown ||
               discovery.fingerprint != nullptr) {
        return MediaDiscoveryValidation::DetectedMetadataMissing;
    }
    return MediaDiscoveryValidation::Valid;
}

bool formatMediaDiscoveryJson(const MediaDiscovery& discovery, char* output,
                              std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const MediaDiscoveryValidation validation = validateMediaDiscovery(discovery);
    if (validation != MediaDiscoveryValidation::Valid) {
        output[0] = '\0';
        return false;
    }
    const char* fingerprint = discovery.fingerprint == nullptr ? "null" : discovery.fingerprint;
    const char* fingerprintPrefix = discovery.fingerprint == nullptr ? "" : "\"";
    const char* fingerprintSuffix = discovery.fingerprint == nullptr ? "" : "\"";
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.storage.discovery.v1\",\"kind\":\"report\","
        "\"validation\":\"%s\",\"media_kind\":\"%s\",\"status\":\"%s\","
        "\"slot_declared\":%s,\"detect_pin\":%d,\"detect_sampled\":%s,"
        "\"detect_level\":%d,\"detect_authoritative\":%s,"
        "\"mount_attempted\":%s,\"mounted_read_only\":%s,"
        "\"filesystem\":\"%s\",\"fingerprint\":%s%s%s,"
        "\"capacity_bytes\":%llu,\"free_bytes\":%llu,"
        "\"write_enabled\":%s,\"guard_required\":true,\"reason\":\"%s\"}",
        mediaDiscoveryValidationName(validation), mediaKindName(discovery.kind),
        mediaDiscoveryStatusName(discovery.status),
        discovery.slotDeclared ? "true" : "false", static_cast<int>(discovery.detectPin),
        discovery.detectSampled ? "true" : "false",
        static_cast<int>(discovery.detectLevel),
        discovery.detectAuthoritative ? "true" : "false",
        discovery.mountAttempted ? "true" : "false",
        discovery.mountedReadOnly ? "true" : "false",
        filesystemKindName(discovery.filesystem), fingerprintPrefix, fingerprint,
        fingerprintSuffix, static_cast<unsigned long long>(discovery.capacityBytes),
        static_cast<unsigned long long>(discovery.freeBytes),
        discovery.writeEnabled ? "true" : "false", discovery.reason);
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
