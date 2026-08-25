#include "TargetStateStore.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

const char* stateHeadPath(HeadSlot slot) {
    return slot == HeadSlot::A ? "target-state-head-a.bin"
                               : "target-state-head-b.bin";
}

template <typename Workspace>
class TargetStateCommitBackend final : public CommitBackend {
public:
    TargetStateCommitBackend(SessionStoreIo& io,
                             Workspace& workspace,
                             std::size_t stateSize,
                             std::size_t manifestSize,
                             std::uint32_t generation, HeadSlot slot)
        : io_(io), workspace_(workspace), stateSize_(stateSize),
          manifestSize_(manifestSize), generation_(generation), slot_(slot) {}

    bool pathsReady() {
        return formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                          generation_, statePath_,
                                          sizeof(statePath_)) &&
            formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                       generation_, manifestPath_,
                                       sizeof(manifestPath_));
    }

    bool writePayloads() override {
        return io_.writeFile(statePath_, workspace_.state.data(), stateSize_);
    }
    bool syncPayloads() override {
        return io_.syncFile(statePath_) && io_.syncDirectory();
    }
    bool writeManifest() override {
        return io_.writeFile(manifestPath_, workspace_.manifest.data(),
                             manifestSize_);
    }
    bool syncManifest() override {
        return io_.syncFile(manifestPath_) && io_.syncDirectory();
    }
    bool writeOlderHead(const std::uint8_t* wire, std::size_t size) override {
        return io_.writeFile(stateHeadPath(slot_), wire, size);
    }
    bool syncHead() override {
        return io_.syncFile(stateHeadPath(slot_)) && io_.syncDirectory();
    }

private:
    SessionStoreIo& io_;
    Workspace& workspace_;
    std::size_t stateSize_ = 0;
    std::size_t manifestSize_ = 0;
    std::uint32_t generation_ = 0;
    HeadSlot slot_ = HeadSlot::A;
    char statePath_[kTargetStateStorePathMax] = {};
    char manifestPath_[kTargetStateStorePathMax] = {};
};

TargetStateStoreStatus commitFailureStatus(CommitStage stage) {
    switch (stage) {
        case CommitStage::SyncPayloads:
        case CommitStage::SyncManifest:
        case CommitStage::SyncHead:
            return TargetStateStoreStatus::SyncError;
        default: return TargetStateStoreStatus::IoError;
    }
}

struct CandidateLoad final {
    HeadCandidate candidate{};
    HeadRecord record{};
    SessionStoreIo::ReadStatus headRead = SessionStoreIo::ReadStatus::NotFound;
};

CandidateLoad loadCandidate(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace, HeadSlot slot,
    domain::targets::TargetCatalog* validationCatalog,
    domain::targets::CorrelationDecisionLog* validationDecisions,
    domain::targets::TargetMergeHistory* validationMerges) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(stateHeadPath(slot), wire.data(), wire.size(),
                                  &wireSize);
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate = {wire.data(), 0, {}, false};
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) !=
            HeadDecodeStatus::Valid ||
        loaded.record.generation == 0) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }

    char manifestPath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    loaded.record.generation, manifestPath,
                                    sizeof(manifestPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c !=
            loaded.record.manifestCrc32c) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }

    TargetStateManifest manifest{};
    if (decodeTargetStateManifest(workspace.manifest.data(), manifestSize,
                                  &manifest) != TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    loaded.record.generation, statePath,
                                    sizeof(statePath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t stateSize = 0;
    if (io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok ||
        reopenTargetState(workspace.manifest.data(), manifestSize,
                          workspace.state.data(), stateSize,
                          validationCatalog, validationDecisions,
                          validationMerges) !=
            TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

CandidateLoad loadCatalogCandidate(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    HeadSlot slot,
    domain::targets::TargetCatalog* validationCatalog) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(stateHeadPath(slot), wire.data(), wire.size(),
                                  &wireSize);
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate = {wire.data(), 0, {}, false};
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) !=
            HeadDecodeStatus::Valid ||
        loaded.record.generation == 0) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char manifestPath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    loaded.record.generation, manifestPath,
                                    sizeof(manifestPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c != loaded.record.manifestCrc32c) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    TargetStateManifest manifest{};
    if (decodeTargetStateManifest(workspace.manifest.data(), manifestSize,
                                  &manifest) != TargetCodecStatus::Valid ||
        manifest.decisionCount != 0 || manifest.mergeCount != 0) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    loaded.record.generation, statePath,
                                    sizeof(statePath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t stateSize = 0;
    if (io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok ||
        reopenTargetCatalogState(
            workspace.manifest.data(), manifestSize, workspace.state.data(),
            stateSize, validationCatalog) != TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

CandidateLoad loadDecisionCandidate(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    HeadSlot slot, domain::targets::TargetCatalog* validationCatalog,
    domain::targets::CorrelationDecisionLog* validationDecisions) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(stateHeadPath(slot), wire.data(), wire.size(),
                                  &wireSize);
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate = {wire.data(), 0, {}, false};
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) !=
            HeadDecodeStatus::Valid ||
        loaded.record.generation == 0) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char manifestPath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    loaded.record.generation, manifestPath,
                                    sizeof(manifestPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c != loaded.record.manifestCrc32c) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    TargetStateManifest manifest{};
    if (decodeTargetStateManifest(workspace.manifest.data(), manifestSize,
                                  &manifest) != TargetCodecStatus::Valid ||
        manifest.mergeCount != 0 ||
        manifest.stateLength > workspace.state.size()) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    loaded.record.generation, statePath,
                                    sizeof(statePath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t stateSize = 0;
    if (io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok ||
        reopenTargetDecisionState(
            workspace.manifest.data(), manifestSize, workspace.state.data(),
            stateSize, validationCatalog, validationDecisions) !=
            TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

CandidateLoad loadDecisionWireCandidate(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    HeadSlot slot) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(stateHeadPath(slot), wire.data(), wire.size(),
                                  &wireSize);
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate = {wire.data(), 0, {}, false};
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) !=
            HeadDecodeStatus::Valid ||
        loaded.record.generation == 0) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char manifestPath[kTargetStateStorePathMax] = {};
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    loaded.record.generation, manifestPath,
                                    sizeof(manifestPath)) ||
        !formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    loaded.record.generation, statePath,
                                    sizeof(statePath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c !=
            loaded.record.manifestCrc32c) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    TargetStateManifest manifest{};
    if (decodeTargetStateManifest(workspace.manifest.data(), manifestSize,
                                  &manifest) != TargetCodecStatus::Valid ||
        manifest.mergeCount != 0 ||
        manifest.stateLength > workspace.state.size()) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t stateSize = 0;
    if (io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok ||
        manifest.stateLength != stateSize ||
        manifest.stateCrc32c != crc32c(workspace.state.data(), stateSize)) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

TargetStateStoreStatus reopenSelected(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    std::uint32_t generation, domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions,
    domain::targets::TargetMergeHistory* merges) {
    catalog->clear();
    decisions->clear();
    merges->clear();
    char manifestPath[kTargetStateStorePathMax] = {};
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    generation, manifestPath,
                                    sizeof(manifestPath)) ||
        !formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    generation, statePath,
                                    sizeof(statePath))) {
        return TargetStateStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t stateSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok) {
        return TargetStateStoreStatus::IoError;
    }
    const bool valid = reopenTargetState(
        workspace.manifest.data(), manifestSize, workspace.state.data(),
        stateSize, catalog, decisions, merges) == TargetCodecStatus::Valid;
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.stateSize = valid ? stateSize : 0;
    return valid ? TargetStateStoreStatus::Valid
                 : TargetStateStoreStatus::CorruptGeneration;
}

TargetStateStoreStatus reopenSelectedCatalog(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    std::uint32_t generation, domain::targets::TargetCatalog* catalog) {
    catalog->clear();
    char manifestPath[kTargetStateStorePathMax] = {};
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    generation, manifestPath,
                                    sizeof(manifestPath)) ||
        !formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    generation, statePath,
                                    sizeof(statePath))) {
        return TargetStateStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t stateSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok) {
        return TargetStateStoreStatus::IoError;
    }
    const bool valid = reopenTargetCatalogState(
        workspace.manifest.data(), manifestSize, workspace.state.data(),
        stateSize, catalog) == TargetCodecStatus::Valid;
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.stateSize = valid ? stateSize : 0;
    return valid ? TargetStateStoreStatus::Valid
                 : TargetStateStoreStatus::CorruptGeneration;
}

TargetStateStoreStatus reopenSelectedDecision(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    std::uint32_t generation, domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions) {
    catalog->clear();
    decisions->clear();
    char manifestPath[kTargetStateStorePathMax] = {};
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    generation, manifestPath,
                                    sizeof(manifestPath)) ||
        !formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    generation, statePath,
                                    sizeof(statePath))) {
        return TargetStateStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t stateSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok) {
        return TargetStateStoreStatus::IoError;
    }
    const bool valid = reopenTargetDecisionState(
        workspace.manifest.data(), manifestSize, workspace.state.data(),
        stateSize, catalog, decisions) == TargetCodecStatus::Valid;
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.stateSize = valid ? stateSize : 0;
    return valid ? TargetStateStoreStatus::Valid
                 : TargetStateStoreStatus::CorruptGeneration;
}

TargetStateStoreStatus reopenSelectedDecisionWire(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    std::uint32_t generation, TargetStateManifest* manifest) {
    if (manifest == nullptr) return TargetStateStoreStatus::InvalidArgument;
    char manifestPath[kTargetStateStorePathMax] = {};
    char statePath[kTargetStateStorePathMax] = {};
    if (!formatTargetStateStorePath(TargetStateStoreFileKind::Manifest,
                                    generation, manifestPath,
                                    sizeof(manifestPath)) ||
        !formatTargetStateStorePath(TargetStateStoreFileKind::State,
                                    generation, statePath,
                                    sizeof(statePath))) {
        return TargetStateStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t stateSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(statePath, workspace.state.data(), workspace.state.size(),
                    &stateSize) != SessionStoreIo::ReadStatus::Ok) {
        return TargetStateStoreStatus::IoError;
    }
    TargetStateManifest decoded{};
    const bool valid = decodeTargetStateManifest(
            workspace.manifest.data(), manifestSize, &decoded) ==
            TargetCodecStatus::Valid &&
        decoded.mergeCount == 0 &&
        decoded.stateLength == stateSize &&
        stateSize <= workspace.state.size() &&
        decoded.stateCrc32c == crc32c(workspace.state.data(), stateSize);
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.stateSize = valid ? stateSize : 0;
    if (valid) *manifest = decoded;
    return valid ? TargetStateStoreStatus::Valid
                 : TargetStateStoreStatus::CorruptGeneration;
}

}  // namespace

bool formatTargetStateStorePath(TargetStateStoreFileKind kind,
                                std::uint32_t generation, char* output,
                                std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    int written = -1;
    switch (kind) {
        case TargetStateStoreFileKind::State:
            written = std::snprintf(output, capacity,
                                    "target-state-%08lu.cbor",
                                    static_cast<unsigned long>(generation));
            break;
        case TargetStateStoreFileKind::Manifest:
            written = std::snprintf(output, capacity,
                                    "target-state-manifest-%08lu.cbor",
                                    static_cast<unsigned long>(generation));
            break;
        case TargetStateStoreFileKind::HeadA:
            written = std::snprintf(output, capacity,
                                    "target-state-head-a.bin");
            break;
        case TargetStateStoreFileKind::HeadB:
            written = std::snprintf(output, capacity,
                                    "target-state-head-b.bin");
            break;
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

const char* targetStateStoreStatusName(TargetStateStoreStatus status) {
    switch (status) {
        case TargetStateStoreStatus::Valid: return "valid";
        case TargetStateStoreStatus::InvalidArgument:
            return "invalid_argument";
        case TargetStateStoreStatus::EncodeFailed: return "encode_failed";
        case TargetStateStoreStatus::PathError: return "path_error";
        case TargetStateStoreStatus::IoError: return "io_error";
        case TargetStateStoreStatus::SyncError: return "sync_error";
        case TargetStateStoreStatus::Empty: return "empty";
        case TargetStateStoreStatus::NoGeneration: return "no_generation";
        case TargetStateStoreStatus::Conflict: return "conflict";
        case TargetStateStoreStatus::CorruptGeneration:
            return "corrupt_generation";
    }
    return "unknown";
}

TargetStateStoreCommitResult commitTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    std::uint32_t generation, HeadSlot publishSlot) {
    TargetStateStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (generation == 0 || catalog.size() == 0) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    if (encodeTargetState(catalog, decisions, merges, workspace.state.data(),
                          workspace.state.size(), &stateSize) !=
            TargetCodecStatus::Valid ||
        encodeTargetStateManifest(
            catalog, decisions, merges, workspace.state.data(), stateSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != TargetCodecStatus::Valid) {
        result.status = TargetStateStoreStatus::EncodeFailed;
        return result;
    }
    workspace.stateSize = stateSize;
    workspace.manifestSize = manifestSize;
    TargetStateCommitBackend<TargetStateStoreWorkspace> backend(
        io, workspace, stateSize, manifestSize, generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = TargetStateStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        generation, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? TargetStateStoreStatus::Valid
        : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

TargetStateStoreCommitResult commitNextTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    domain::targets::TargetCatalog& recoveryCatalogScratch,
    domain::targets::CorrelationDecisionLog& recoveryDecisionScratch,
    domain::targets::TargetMergeHistory& recoveryMergeScratch) {
    TargetStateStoreCommitResult result;
    if (&catalog == &recoveryCatalogScratch ||
        &decisions == &recoveryDecisionScratch ||
        &merges == &recoveryMergeScratch || catalog.size() == 0) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    const TargetStateStoreRecoveryResult current = recoverTargetState(
        io, workspace, &recoveryCatalogScratch, &recoveryDecisionScratch,
        &recoveryMergeScratch);
    if (current.status == TargetStateStoreStatus::Empty) {
        return commitTargetState(io, workspace, catalog, decisions, merges, 1,
                                 HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    if (current.generation == UINT32_MAX) {
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitTargetState(io, workspace, catalog, decisions, merges,
                             current.generation + 1U, publish);
}

TargetStateStoreRecoveryResult recoverTargetState(
    SessionStoreIo& io, TargetStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions,
    domain::targets::TargetMergeHistory* merges) {
    TargetStateStoreRecoveryResult result;
    if (catalog == nullptr || decisions == nullptr || merges == nullptr) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCandidate(io, workspace, HeadSlot::A,
                                    catalog, decisions, merges);
    CandidateLoad b = loadCandidate(io, workspace, HeadSlot::B,
                                    catalog, decisions, merges);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        catalog->clear();
        decisions->clear();
        merges->clear();
        result.status = TargetStateStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        catalog->clear();
        decisions->clear();
        merges->clear();
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        catalog->clear();
        decisions->clear();
        merges->clear();
        result.status = TargetStateStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    result.status = reopenSelected(io, workspace, result.generation,
                                   catalog, decisions, merges);
    if (result.status == TargetStateStoreStatus::Valid) {
        result.targets = catalog->size();
        result.decisions = decisions->size();
        result.merges = merges->size();
        workspace.generation = result.generation;
    }
    return result;
}

TargetStateStoreCommitResult commitTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    std::uint32_t generation, HeadSlot publishSlot) {
    TargetStateStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (generation == 0 || catalog.size() == 0) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    if (encodeTargetCatalogState(
            catalog, workspace.state.data(), workspace.state.size(),
            &stateSize) != TargetCodecStatus::Valid ||
        encodeTargetCatalogStateManifest(
            catalog, workspace.state.data(), stateSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != TargetCodecStatus::Valid) {
        result.status = TargetStateStoreStatus::EncodeFailed;
        return result;
    }
    workspace.stateSize = stateSize;
    workspace.manifestSize = manifestSize;
    TargetStateCommitBackend<TargetCatalogStateStoreWorkspace> backend(
        io, workspace, stateSize, manifestSize, generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = TargetStateStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        generation, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? TargetStateStoreStatus::Valid
        : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

TargetStateStoreCommitResult commitNextTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& recoveryCatalogScratch) {
    TargetStateStoreCommitResult result;
    if (&catalog == &recoveryCatalogScratch || catalog.size() == 0) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    const TargetStateStoreRecoveryResult current = recoverTargetCatalogState(
        io, workspace, &recoveryCatalogScratch);
    if (current.status == TargetStateStoreStatus::Empty) {
        return commitTargetCatalogState(io, workspace, catalog, 1,
                                        HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    if (current.generation == UINT32_MAX) {
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitTargetCatalogState(io, workspace, catalog,
                                    current.generation + 1U, publish);
}

TargetStateStoreRecoveryResult recoverTargetCatalogState(
    SessionStoreIo& io, TargetCatalogStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog) {
    TargetStateStoreRecoveryResult result;
    if (catalog == nullptr) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCatalogCandidate(io, workspace, HeadSlot::A, catalog);
    CandidateLoad b = loadCatalogCandidate(io, workspace, HeadSlot::B, catalog);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        catalog->clear();
        result.status = TargetStateStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        catalog->clear();
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        catalog->clear();
        result.status = TargetStateStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    result.status = reopenSelectedCatalog(
        io, workspace, result.generation, catalog);
    if (result.status == TargetStateStoreStatus::Valid) {
        workspace.generation = result.generation;
        result.targets = catalog->size();
    }
    return result;
}

TargetStateStoreCommitResult commitTargetDecisionState(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    std::uint32_t generation, HeadSlot publishSlot) {
    TargetStateStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (generation == 0 || catalog.size() == 0) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    std::size_t stateSize = 0;
    std::size_t manifestSize = 0;
    if (encodeTargetDecisionState(
            catalog, decisions, workspace.state.data(), workspace.state.size(),
            &stateSize) != TargetCodecStatus::Valid ||
        encodeTargetDecisionStateManifest(
            catalog, decisions, workspace.state.data(), stateSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &manifestSize) != TargetCodecStatus::Valid) {
        result.status = TargetStateStoreStatus::EncodeFailed;
        return result;
    }
    workspace.stateSize = stateSize;
    workspace.manifestSize = manifestSize;
    TargetStateCommitBackend<TargetDecisionStateStoreWorkspace> backend(
        io, workspace, stateSize, manifestSize, generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = TargetStateStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        generation, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? TargetStateStoreStatus::Valid
        : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

TargetStateStoreRecoveryResult recoverTargetDecisionState(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions) {
    TargetStateStoreRecoveryResult result;
    if (catalog == nullptr || decisions == nullptr) {
        result.status = TargetStateStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadDecisionCandidate(
        io, workspace, HeadSlot::A, catalog, decisions);
    CandidateLoad b = loadDecisionCandidate(
        io, workspace, HeadSlot::B, catalog, decisions);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        catalog->clear();
        decisions->clear();
        result.status = TargetStateStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        catalog->clear();
        decisions->clear();
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        catalog->clear();
        decisions->clear();
        result.status = TargetStateStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    result.status = reopenSelectedDecision(
        io, workspace, result.generation, catalog, decisions);
    if (result.status == TargetStateStoreStatus::Valid) {
        workspace.generation = result.generation;
        result.targets = catalog->size();
        result.decisions = decisions->size();
    }
    return result;
}

TargetStateStoreRecoveryResult recoverTargetDecisionStateWire(
    SessionStoreIo& io, TargetDecisionStateStoreWorkspace& workspace) {
    TargetStateStoreRecoveryResult result;
    CandidateLoad a = loadDecisionWireCandidate(io, workspace, HeadSlot::A);
    CandidateLoad b = loadDecisionWireCandidate(io, workspace, HeadSlot::B);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        result.status = TargetStateStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        result.status = TargetStateStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        result.status = TargetStateStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    TargetStateManifest manifest{};
    result.status = reopenSelectedDecisionWire(
        io, workspace, result.generation, &manifest);
    if (result.status == TargetStateStoreStatus::Valid) {
        workspace.generation = result.generation;
        result.targets = manifest.targetCount;
        result.decisions = manifest.decisionCount;
    }
    return result;
}

}  // namespace leshy1::storage
