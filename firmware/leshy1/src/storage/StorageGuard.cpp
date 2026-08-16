#include "StorageGuard.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

bool boundedToken(const char* value, std::size_t maxLength, bool runId) {
    if (value == nullptr || value[0] == '\0') return false;
    for (std::size_t i = 0; i <= maxLength; ++i) {
        const char current = value[i];
        if (current == '\0') return true;
        if (i == maxLength) return false;
        const bool alphaNumeric =
            (current >= 'a' && current <= 'z') || (current >= 'A' && current <= 'Z') ||
            (current >= '0' && current <= '9');
        if (runId) {
            if (!alphaNumeric && current != '-' && current != '_') return false;
        } else if (!alphaNumeric && current != '-' && current != '_' && current != ':') {
            return false;
        }
    }
    return false;
}

bool boundedEqual(const char* left, const char* right, std::size_t maxLength) {
    if (left == nullptr || right == nullptr) return false;
    for (std::size_t i = 0; i <= maxLength; ++i) {
        if (left[i] != right[i]) return false;
        if (left[i] == '\0') return true;
    }
    return false;
}

}  // namespace

const char* permitStatusName(PermitStatus status) {
    switch (status) {
        case PermitStatus::Permitted: return "permitted";
        case PermitStatus::MissingMedia: return "missing_media";
        case PermitStatus::ExplicitAuthorizationRequired: return "explicit_authorization_required";
        case PermitStatus::InvalidFingerprint: return "invalid_fingerprint";
        case PermitStatus::FingerprintMismatch: return "fingerprint_mismatch";
        case PermitStatus::InvalidRunId: return "invalid_run_id";
        case PermitStatus::ScratchAlreadyExists: return "scratch_already_exists";
        case PermitStatus::InvalidSize: return "invalid_size";
        case PermitStatus::InsufficientSpace: return "insufficient_space";
    }
    return "invalid_status";
}

WritePermit authorizeScratchWrite(const MediaIdentity& media, const WriteRequest& request) {
    WritePermit permit;
    if (!media.present) return permit;
    if (!request.explicitlyDisposable) {
        permit.status = PermitStatus::ExplicitAuthorizationRequired;
        return permit;
    }
    if (!boundedToken(media.fingerprint, kFingerprintMax, false) ||
        !boundedToken(request.expectedFingerprint, kFingerprintMax, false)) {
        permit.status = PermitStatus::InvalidFingerprint;
        return permit;
    }
    if (!boundedEqual(media.fingerprint, request.expectedFingerprint, kFingerprintMax)) {
        permit.status = PermitStatus::FingerprintMismatch;
        return permit;
    }
    if (!boundedToken(request.runId, kRunIdMax, true)) {
        permit.status = PermitStatus::InvalidRunId;
        return permit;
    }
    if (request.scratchExists) {
        permit.status = PermitStatus::ScratchAlreadyExists;
        return permit;
    }
    if (request.requiredBytes == 0 || request.reserveBytes > UINT64_MAX - request.requiredBytes) {
        permit.status = PermitStatus::InvalidSize;
        return permit;
    }
    if (media.freeBytes < request.requiredBytes + request.reserveBytes ||
        media.capacityBytes < media.freeBytes) {
        permit.status = PermitStatus::InsufficientSpace;
        return permit;
    }
    const int written = std::snprintf(permit.scratchPath, sizeof(permit.scratchPath), "%s%s",
                                      kScratchRoot, request.runId);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(permit.scratchPath)) {
        permit.status = PermitStatus::InvalidRunId;
        permit.scratchPath[0] = '\0';
        return permit;
    }
    permit.status = PermitStatus::Permitted;
    permit.byteLimit = request.requiredBytes;
    return permit;
}

const char* readPermitStatusName(ReadPermitStatus status) {
    switch (status) {
        case ReadPermitStatus::Permitted: return "permitted";
        case ReadPermitStatus::MissingMedia: return "missing_media";
        case ReadPermitStatus::ExplicitAuthorizationRequired:
            return "explicit_authorization_required";
        case ReadPermitStatus::InvalidFingerprint: return "invalid_fingerprint";
        case ReadPermitStatus::FingerprintMismatch: return "fingerprint_mismatch";
        case ReadPermitStatus::InvalidRunId: return "invalid_run_id";
        case ReadPermitStatus::ScratchMissing: return "scratch_missing";
    }
    return "invalid_status";
}

ReadPermit authorizeExistingScratchRead(
    const MediaIdentity& media, const ExistingScratchReadRequest& request) {
    ReadPermit permit;
    if (!media.present) return permit;
    if (!request.explicitlySelected) {
        permit.status = ReadPermitStatus::ExplicitAuthorizationRequired;
        return permit;
    }
    if (!boundedToken(media.fingerprint, kFingerprintMax, false) ||
        !boundedToken(request.expectedFingerprint, kFingerprintMax, false)) {
        permit.status = ReadPermitStatus::InvalidFingerprint;
        return permit;
    }
    if (!boundedEqual(media.fingerprint, request.expectedFingerprint,
                      kFingerprintMax)) {
        permit.status = ReadPermitStatus::FingerprintMismatch;
        return permit;
    }
    if (!boundedToken(request.runId, kRunIdMax, true)) {
        permit.status = ReadPermitStatus::InvalidRunId;
        return permit;
    }
    if (!request.scratchExists) {
        permit.status = ReadPermitStatus::ScratchMissing;
        return permit;
    }
    const int written = std::snprintf(permit.scratchPath,
                                      sizeof(permit.scratchPath), "%s%s",
                                      kScratchRoot, request.runId);
    if (written <= 0 || static_cast<std::size_t>(written) >=
                            sizeof(permit.scratchPath)) {
        permit.status = ReadPermitStatus::InvalidRunId;
        permit.scratchPath[0] = '\0';
        return permit;
    }
    permit.status = ReadPermitStatus::Permitted;
    return permit;
}

}  // namespace leshy1::storage
