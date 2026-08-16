#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::storage {

constexpr std::uint16_t kHeadSchemaVersion = 1;
constexpr std::size_t kHeadWireSize = 24;

struct HeadRecord final {
    std::uint32_t generation = 0;
    std::uint32_t manifestLength = 0;
    std::uint32_t manifestCrc32c = 0;
};

enum class HeadDecodeStatus : std::uint8_t {
    Valid,
    TooShort,
    MagicMismatch,
    UnsupportedSchema,
    InvalidFlags,
    ChecksumMismatch,
};

std::uint32_t crc32c(const std::uint8_t* data, std::size_t size);
bool encodeHead(const HeadRecord& record, std::uint8_t* output, std::size_t size);
HeadDecodeStatus decodeHead(const std::uint8_t* wire, std::size_t size, HeadRecord* output);

struct ManifestEvidence final {
    bool present = false;
    std::uint32_t length = 0;
    std::uint32_t crc32c = 0;
};

enum class CandidateStatus : std::uint8_t {
    Valid,
    InvalidHead,
    MissingManifest,
    ManifestMismatch,
    InvalidPayload,
};

struct HeadCandidate final {
    const std::uint8_t* wire = nullptr;
    std::size_t wireSize = 0;
    ManifestEvidence manifest = {};
    bool payloadValid = true;
};

enum class RecoveryChoice : std::uint8_t {
    None,
    A,
    B,
    Conflict,
};

struct RecoveryResult final {
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    HeadRecord selected = {};
};

RecoveryResult recoverHead(const HeadCandidate& a, const HeadCandidate& b);

enum class CommitStage : std::uint8_t {
    WritePayloads,
    SyncPayloads,
    WriteManifest,
    SyncManifest,
    WriteHead,
    SyncHead,
    Complete,
};

class CommitBackend {
public:
    virtual ~CommitBackend() = default;
    virtual bool writePayloads() = 0;
    virtual bool syncPayloads() = 0;
    virtual bool writeManifest() = 0;
    virtual bool syncManifest() = 0;
    virtual bool writeOlderHead(const std::uint8_t* wire, std::size_t size) = 0;
    virtual bool syncHead() = 0;
};

struct CommitResult final {
    bool complete = false;
    CommitStage stage = CommitStage::WritePayloads;
};

CommitResult commitGeneration(CommitBackend& backend, const HeadRecord& next);

}  // namespace leshy1::storage
