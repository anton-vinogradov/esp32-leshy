#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "SessionCodec.h"

namespace leshy1::storage {

constexpr std::size_t kSessionStorePathMax = 48;

enum class StoreFileKind : std::uint8_t {
    Segment,
    Manifest,
    HeadA,
    HeadB,
};

enum class HeadSlot : std::uint8_t {
    A,
    B,
};

bool formatSessionStorePath(StoreFileKind kind, std::uint32_t generation, char* output,
                            std::size_t capacity);

class SessionStoreIo {
public:
    virtual ~SessionStoreIo() = default;
    virtual bool writeFile(const char* path, const std::uint8_t* data, std::size_t size) = 0;
    enum class ReadStatus : std::uint8_t {
        Ok,
        NotFound,
        TooLarge,
        IoError,
    };
    virtual ReadStatus readFile(const char* path, std::uint8_t* output, std::size_t capacity,
                                std::size_t* outputSize) = 0;
    virtual bool syncFile(const char* path) = 0;
    virtual bool syncDirectory() = 0;
};

struct SessionStoreWorkspace final {
    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    services::survey::SurveySession validationSession{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    std::uint32_t generation = 0;
};

enum class SessionStoreStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SessionNotStopped,
    EncodeFailed,
    PathError,
    IoError,
    SyncError,
    Empty,
    NoGeneration,
    Conflict,
    CorruptGeneration,
};

const char* sessionStoreStatusName(SessionStoreStatus status);

struct SessionStoreCommitResult final {
    SessionStoreStatus status = SessionStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t generation = 0;
    HeadSlot publishedSlot = HeadSlot::A;

    bool complete() const { return status == SessionStoreStatus::Valid; }
};

SessionStoreCommitResult commitSession(SessionStoreIo& io, SessionStoreWorkspace& workspace,
                                       const services::survey::SurveySession& session,
                                       std::uint32_t generation, HeadSlot publishSlot);

SessionStoreCommitResult commitNextSession(SessionStoreIo& io,
                                           SessionStoreWorkspace& workspace,
                                           const services::survey::SurveySession& session);
SessionStoreCommitResult commitWifiFrameCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames,
    std::uint32_t generation, HeadSlot publishSlot);
SessionStoreCommitResult commitNextWifiFrameCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames);
SessionStoreCommitResult commitSubGhzRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses,
    std::uint32_t generation, HeadSlot publishSlot);
SessionStoreCommitResult commitNextSubGhzRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses);
SessionStoreCommitResult commitInfraredRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses,
    std::uint32_t generation, HeadSlot publishSlot);
SessionStoreCommitResult commitNextInfraredRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses);

struct SessionStoreRecoveryResult final {
    SessionStoreStatus status = SessionStoreStatus::NoGeneration;
    RecoveryChoice choice = RecoveryChoice::None;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t generation = 0;
    std::size_t observations = 0;

    bool valid() const { return status == SessionStoreStatus::Valid; }
};

SessionStoreRecoveryResult recoverSession(SessionStoreIo& io,
                                          SessionStoreWorkspace& workspace,
                                          services::survey::SurveySession* output);

struct SessionStorePairRecoveryResult final {
    SessionStoreStatus status = SessionStoreStatus::NoGeneration;
    CandidateStatus aStatus = CandidateStatus::InvalidHead;
    CandidateStatus bStatus = CandidateStatus::InvalidHead;
    std::uint32_t baselineGeneration = 0;
    std::uint32_t currentGeneration = 0;
    std::size_t baselineObservations = 0;
    std::size_t currentObservations = 0;

    bool valid() const { return status == SessionStoreStatus::Valid; }
};

// Recovers the two distinct durable generations currently named by the atomic
// heads. Orphan payloads from interrupted writes are never admitted. Results
// are chronological and all-or-nothing, ready for an exact Session compare.
SessionStorePairRecoveryResult recoverSessionPair(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    services::survey::SurveySession* baseline,
    services::survey::SurveySession* current);

}  // namespace leshy1::storage
