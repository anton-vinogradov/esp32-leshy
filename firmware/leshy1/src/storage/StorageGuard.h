#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::storage {

constexpr std::size_t kFingerprintMax = 64;
constexpr std::size_t kRunIdMax = 32;
constexpr std::size_t kScratchPathMax = 64;
constexpr const char* kScratchRoot = "/leshy-hil/";

enum class MediaKind : std::uint8_t {
    Sd,
    LittleFs,
};

struct MediaIdentity final {
    bool present = false;
    MediaKind kind = MediaKind::Sd;
    const char* fingerprint = nullptr;
    std::uint64_t capacityBytes = 0;
    std::uint64_t freeBytes = 0;
};

struct WriteRequest final {
    bool explicitlyDisposable = false;
    const char* expectedFingerprint = nullptr;
    const char* runId = nullptr;
    bool scratchExists = false;
    std::uint64_t requiredBytes = 0;
    std::uint64_t reserveBytes = 0;
};

enum class PermitStatus : std::uint8_t {
    Permitted,
    MissingMedia,
    ExplicitAuthorizationRequired,
    InvalidFingerprint,
    FingerprintMismatch,
    InvalidRunId,
    ScratchAlreadyExists,
    InvalidSize,
    InsufficientSpace,
};

const char* permitStatusName(PermitStatus status);

struct WritePermit final {
    PermitStatus status = PermitStatus::MissingMedia;
    char scratchPath[kScratchPathMax] = {};
    std::uint64_t byteLimit = 0;

    bool allowed() const { return status == PermitStatus::Permitted; }
};

WritePermit authorizeScratchWrite(const MediaIdentity& media, const WriteRequest& request);

enum class ReadPermitStatus : std::uint8_t {
    Permitted,
    MissingMedia,
    ExplicitAuthorizationRequired,
    InvalidFingerprint,
    FingerprintMismatch,
    InvalidRunId,
    ScratchMissing,
};

const char* readPermitStatusName(ReadPermitStatus status);

struct ExistingScratchReadRequest final {
    bool explicitlySelected = false;
    const char* expectedFingerprint = nullptr;
    const char* runId = nullptr;
    bool scratchExists = false;
};

struct ReadPermit final {
    ReadPermitStatus status = ReadPermitStatus::MissingMedia;
    char scratchPath[kScratchPathMax] = {};

    bool allowed() const { return status == ReadPermitStatus::Permitted; }
};

ReadPermit authorizeExistingScratchRead(
    const MediaIdentity& media, const ExistingScratchReadRequest& request);

}  // namespace leshy1::storage
