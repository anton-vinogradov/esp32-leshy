#include "SessionStore.h"

#include <cstdio>
#include <cstring>

namespace leshy1::storage {
namespace {

const char* headPath(HeadSlot slot) { return slot == HeadSlot::A ? "head-a.bin" : "head-b.bin"; }

class StoreCommitBackend final : public CommitBackend {
public:
    StoreCommitBackend(SessionStoreIo& io, SessionStoreWorkspace& workspace,
                       std::size_t segmentSize, std::size_t manifestSize,
                       std::uint32_t generation, HeadSlot slot)
        : io_(io), workspace_(workspace), segmentSize_(segmentSize),
          manifestSize_(manifestSize), generation_(generation), slot_(slot) {}

    bool pathsReady() {
        return formatSessionStorePath(StoreFileKind::Segment, generation_, segmentPath_,
                                      sizeof(segmentPath_)) &&
               formatSessionStorePath(StoreFileKind::Manifest, generation_, manifestPath_,
                                      sizeof(manifestPath_));
    }

    bool writePayloads() override {
        return io_.writeFile(segmentPath_, workspace_.segment.data(), segmentSize_);
    }
    bool syncPayloads() override {
        return io_.syncFile(segmentPath_) && io_.syncDirectory();
    }
    bool writeManifest() override {
        return io_.writeFile(manifestPath_, workspace_.manifest.data(), manifestSize_);
    }
    bool syncManifest() override {
        return io_.syncFile(manifestPath_) && io_.syncDirectory();
    }
    bool writeOlderHead(const std::uint8_t* wire, std::size_t size) override {
        return io_.writeFile(headPath(slot_), wire, size);
    }
    bool syncHead() override {
        return io_.syncFile(headPath(slot_)) && io_.syncDirectory();
    }

private:
    SessionStoreIo& io_;
    SessionStoreWorkspace& workspace_;
    std::size_t segmentSize_ = 0;
    std::size_t manifestSize_ = 0;
    std::uint32_t generation_ = 0;
    HeadSlot slot_ = HeadSlot::A;
    char segmentPath_[kSessionStorePathMax] = {};
    char manifestPath_[kSessionStorePathMax] = {};
};

SessionStoreStatus commitFailureStatus(CommitStage stage) {
    switch (stage) {
        case CommitStage::SyncPayloads:
        case CommitStage::SyncManifest:
        case CommitStage::SyncHead: return SessionStoreStatus::SyncError;
        default: return SessionStoreStatus::IoError;
    }
}

struct CandidateLoad final {
    HeadCandidate candidate{};
    HeadRecord record{};
    SessionStoreIo::ReadStatus headRead = SessionStoreIo::ReadStatus::NotFound;
};

CandidateLoad loadCandidate(SessionStoreIo& io, SessionStoreWorkspace& workspace,
                            HeadSlot slot) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(headPath(slot), wire.data(), wire.size(), &wireSize);
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate = {wire.data(), 0, {}, false};
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) != HeadDecodeStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }

    char manifestPath[kSessionStorePathMax] = {};
    if (!formatSessionStorePath(StoreFileKind::Manifest, loaded.record.generation,
                                manifestPath, sizeof(manifestPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(), workspace.manifest.size(),
                    &manifestSize) != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {true, static_cast<std::uint32_t>(manifestSize),
                                 crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c != loaded.record.manifestCrc32c) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }

    SessionManifest manifest;
    if (decodeSessionManifest(workspace.manifest.data(), manifestSize, &manifest) !=
        SessionCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char segmentPath[kSessionStorePathMax] = {};
    if (!formatSessionStorePath(StoreFileKind::Segment, loaded.record.generation, segmentPath,
                                sizeof(segmentPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t segmentSize = 0;
    if (io.readFile(segmentPath, workspace.segment.data(), workspace.segment.size(),
                    &segmentSize) != SessionStoreIo::ReadStatus::Ok ||
        reopenSession(workspace.manifest.data(), manifestSize, workspace.segment.data(),
                      segmentSize, &workspace.validationSession) != SessionCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

SessionStoreStatus reopenSelected(SessionStoreIo& io, SessionStoreWorkspace& workspace,
                                  std::uint32_t generation,
                                  services::survey::SurveySession* output) {
    char manifestPath[kSessionStorePathMax] = {};
    char segmentPath[kSessionStorePathMax] = {};
    if (!formatSessionStorePath(StoreFileKind::Manifest, generation, manifestPath,
                                sizeof(manifestPath)) ||
        !formatSessionStorePath(StoreFileKind::Segment, generation, segmentPath,
                                sizeof(segmentPath))) {
        return SessionStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t segmentSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(), workspace.manifest.size(),
                    &manifestSize) != SessionStoreIo::ReadStatus::Ok ||
        io.readFile(segmentPath, workspace.segment.data(), workspace.segment.size(),
                    &segmentSize) != SessionStoreIo::ReadStatus::Ok) {
        return SessionStoreStatus::IoError;
    }
    const bool valid = reopenSession(
        workspace.manifest.data(), manifestSize, workspace.segment.data(),
        segmentSize, output) == SessionCodecStatus::Valid;
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.segmentSize = valid ? segmentSize : 0;
    return valid ? SessionStoreStatus::Valid
                 : SessionStoreStatus::CorruptGeneration;
}

}  // namespace

bool formatSessionStorePath(StoreFileKind kind, std::uint32_t generation, char* output,
                            std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    int written = -1;
    switch (kind) {
        case StoreFileKind::Segment:
            written = std::snprintf(output, capacity, "segment-%08lu.bin",
                                    static_cast<unsigned long>(generation));
            break;
        case StoreFileKind::Manifest:
            written = std::snprintf(output, capacity, "manifest-%08lu.bin",
                                    static_cast<unsigned long>(generation));
            break;
        case StoreFileKind::HeadA: written = std::snprintf(output, capacity, "head-a.bin"); break;
        case StoreFileKind::HeadB: written = std::snprintf(output, capacity, "head-b.bin"); break;
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

const char* sessionStoreStatusName(SessionStoreStatus status) {
    switch (status) {
        case SessionStoreStatus::Valid: return "valid";
        case SessionStoreStatus::InvalidArgument: return "invalid_argument";
        case SessionStoreStatus::SessionNotStopped: return "session_not_stopped";
        case SessionStoreStatus::EncodeFailed: return "encode_failed";
        case SessionStoreStatus::PathError: return "path_error";
        case SessionStoreStatus::IoError: return "io_error";
        case SessionStoreStatus::SyncError: return "sync_error";
        case SessionStoreStatus::Empty: return "empty";
        case SessionStoreStatus::NoGeneration: return "no_generation";
        case SessionStoreStatus::Conflict: return "conflict";
        case SessionStoreStatus::CorruptGeneration: return "corrupt_generation";
    }
    return "unknown";
}

SessionStoreCommitResult commitSession(SessionStoreIo& io, SessionStoreWorkspace& workspace,
                                       const services::survey::SurveySession& session,
                                       std::uint32_t generation, HeadSlot publishSlot) {
    SessionStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    if (encodeObservationSegment(session, workspace.segment.data(), workspace.segment.size(),
                                 &segmentSize) != SessionCodecStatus::Valid ||
        encodeSessionManifest(session, workspace.segment.data(), segmentSize,
                              workspace.manifest.data(), workspace.manifest.size(),
                              &manifestSize) != SessionCodecStatus::Valid) {
        result.status = SessionStoreStatus::EncodeFailed;
        return result;
    }
    workspace.segmentSize = segmentSize;
    workspace.manifestSize = manifestSize;
    StoreCommitBackend backend(io, workspace, segmentSize, manifestSize, generation,
                               publishSlot);
    if (!backend.pathsReady()) {
        result.status = SessionStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{generation, static_cast<std::uint32_t>(manifestSize),
                          crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete ? SessionStoreStatus::Valid
                                       : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

SessionStoreCommitResult commitWifiFrameCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames,
    std::uint32_t generation, HeadSlot publishSlot) {
    SessionStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    if (encodeWifiFrameCaptureSegment(
            session, frames, workspace.segment.data(), workspace.segment.size(),
            &segmentSize) != SessionCodecStatus::Valid ||
        encodeSessionManifest(
            session, workspace.segment.data(), segmentSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != SessionCodecStatus::Valid) {
        result.status = SessionStoreStatus::EncodeFailed;
        return result;
    }
    workspace.segmentSize = segmentSize;
    workspace.manifestSize = manifestSize;
    StoreCommitBackend backend(io, workspace, segmentSize, manifestSize,
                               generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = SessionStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{generation, static_cast<std::uint32_t>(manifestSize),
                          crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete ? SessionStoreStatus::Valid
                                       : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

SessionStoreCommitResult commitSubGhzRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses,
    std::uint32_t generation, HeadSlot publishSlot) {
    SessionStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    if (encodeSubGhzRawCaptureSegment(
            session, pulses, workspace.segment.data(), workspace.segment.size(),
            &segmentSize) != SessionCodecStatus::Valid ||
        encodeSessionManifest(
            session, workspace.segment.data(), segmentSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != SessionCodecStatus::Valid) {
        result.status = SessionStoreStatus::EncodeFailed;
        return result;
    }
    workspace.segmentSize = segmentSize;
    workspace.manifestSize = manifestSize;
    StoreCommitBackend backend(io, workspace, segmentSize, manifestSize,
                               generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = SessionStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{generation, static_cast<std::uint32_t>(manifestSize),
                          crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete ? SessionStoreStatus::Valid
                                       : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

SessionStoreCommitResult commitInfraredRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses,
    std::uint32_t generation, HeadSlot publishSlot) {
    SessionStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    if (encodeInfraredRawCaptureSegment(
            session, pulses, workspace.segment.data(), workspace.segment.size(),
            &segmentSize) != SessionCodecStatus::Valid ||
        encodeSessionManifest(
            session, workspace.segment.data(), segmentSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != SessionCodecStatus::Valid) {
        result.status = SessionStoreStatus::EncodeFailed;
        return result;
    }
    workspace.segmentSize = segmentSize;
    workspace.manifestSize = manifestSize;
    StoreCommitBackend backend(io, workspace, segmentSize, manifestSize,
                               generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = SessionStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{generation, static_cast<std::uint32_t>(manifestSize),
                          crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete ? SessionStoreStatus::Valid
                                       : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

SessionStoreCommitResult commitNextSession(SessionStoreIo& io,
                                           SessionStoreWorkspace& workspace,
                                           const services::survey::SurveySession& session) {
    SessionStoreCommitResult result;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    const SessionStoreRecoveryResult current =
        recoverSession(io, workspace, &workspace.validationSession);
    if (current.status == SessionStoreStatus::Empty) {
        return commitSession(io, workspace, session, 1, HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitSession(io, workspace, session, current.generation + 1U, publish);
}

SessionStoreCommitResult commitNextWifiFrameCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames) {
    SessionStoreCommitResult result;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    const SessionStoreRecoveryResult current =
        recoverSession(io, workspace, &workspace.validationSession);
    if (current.status == SessionStoreStatus::Empty) {
        return commitWifiFrameCapture(io, workspace, session, frames, 1,
                                      HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitWifiFrameCapture(io, workspace, session, frames,
                                  current.generation + 1U, publish);
}

SessionStoreCommitResult commitNextSubGhzRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses) {
    SessionStoreCommitResult result;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    const SessionStoreRecoveryResult current =
        recoverSession(io, workspace, &workspace.validationSession);
    if (current.status == SessionStoreStatus::Empty) {
        return commitSubGhzRawCapture(io, workspace, session, pulses, 1,
                                     HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitSubGhzRawCapture(io, workspace, session, pulses,
                                 current.generation + 1U, publish);
}

SessionStoreCommitResult commitNextInfraredRawCapture(
    SessionStoreIo& io, SessionStoreWorkspace& workspace,
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses) {
    SessionStoreCommitResult result;
    if (session.state() != services::survey::SessionState::Stopped) {
        result.status = SessionStoreStatus::SessionNotStopped;
        return result;
    }
    const SessionStoreRecoveryResult current =
        recoverSession(io, workspace, &workspace.validationSession);
    if (current.status == SessionStoreStatus::Empty) {
        return commitInfraredRawCapture(io, workspace, session, pulses, 1,
                                        HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitInfraredRawCapture(io, workspace, session, pulses,
                                    current.generation + 1U, publish);
}

SessionStoreRecoveryResult recoverSession(SessionStoreIo& io,
                                          SessionStoreWorkspace& workspace,
                                          services::survey::SurveySession* output) {
    SessionStoreRecoveryResult result;
    if (output == nullptr) {
        result.status = SessionStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCandidate(io, workspace, HeadSlot::A);
    CandidateLoad b = loadCandidate(io, workspace, HeadSlot::B);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        result.status = SessionStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        result.status = SessionStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A && recovered.choice != RecoveryChoice::B) {
        result.status = SessionStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    result.status = reopenSelected(io, workspace, result.generation, output);
    if (result.status == SessionStoreStatus::Valid) {
        result.observations = output->size();
        workspace.generation = result.generation;
    }
    return result;
}

}  // namespace leshy1::storage
