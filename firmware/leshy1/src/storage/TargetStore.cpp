#include "TargetStore.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

const char* targetHeadPath(HeadSlot slot) {
    return slot == HeadSlot::A ? "target-head-a.bin"
                               : "target-head-b.bin";
}

class TargetCommitBackend final : public CommitBackend {
public:
    TargetCommitBackend(SessionStoreIo& io, TargetStoreWorkspace& workspace,
                        std::size_t catalogSize, std::size_t manifestSize,
                        std::uint32_t generation, HeadSlot slot)
        : io_(io), workspace_(workspace), catalogSize_(catalogSize),
          manifestSize_(manifestSize), generation_(generation), slot_(slot) {}

    bool pathsReady() {
        return formatTargetStorePath(TargetStoreFileKind::Catalog, generation_,
                                     catalogPath_, sizeof(catalogPath_)) &&
            formatTargetStorePath(TargetStoreFileKind::Manifest, generation_,
                                  manifestPath_, sizeof(manifestPath_));
    }

    bool writePayloads() override {
        return io_.writeFile(catalogPath_, workspace_.catalog.data(),
                             catalogSize_);
    }
    bool syncPayloads() override {
        return io_.syncFile(catalogPath_) && io_.syncDirectory();
    }
    bool writeManifest() override {
        return io_.writeFile(manifestPath_, workspace_.manifest.data(),
                             manifestSize_);
    }
    bool syncManifest() override {
        return io_.syncFile(manifestPath_) && io_.syncDirectory();
    }
    bool writeOlderHead(const std::uint8_t* wire, std::size_t size) override {
        return io_.writeFile(targetHeadPath(slot_), wire, size);
    }
    bool syncHead() override {
        return io_.syncFile(targetHeadPath(slot_)) && io_.syncDirectory();
    }

private:
    SessionStoreIo& io_;
    TargetStoreWorkspace& workspace_;
    std::size_t catalogSize_ = 0;
    std::size_t manifestSize_ = 0;
    std::uint32_t generation_ = 0;
    HeadSlot slot_ = HeadSlot::A;
    char catalogPath_[kTargetStorePathMax] = {};
    char manifestPath_[kTargetStorePathMax] = {};
};

TargetStoreStatus commitFailureStatus(CommitStage stage) {
    switch (stage) {
        case CommitStage::SyncPayloads:
        case CommitStage::SyncManifest:
        case CommitStage::SyncHead: return TargetStoreStatus::SyncError;
        default: return TargetStoreStatus::IoError;
    }
}

struct CandidateLoad final {
    HeadCandidate candidate{};
    HeadRecord record{};
    SessionStoreIo::ReadStatus headRead = SessionStoreIo::ReadStatus::NotFound;
};

CandidateLoad loadCandidate(SessionStoreIo& io,
                            TargetStoreWorkspace& workspace, HeadSlot slot,
                            domain::targets::TargetCatalog* validationScratch) {
    CandidateLoad loaded;
    std::array<std::uint8_t, kHeadWireSize>& wire =
        slot == HeadSlot::A ? workspace.headA : workspace.headB;
    std::size_t wireSize = 0;
    loaded.headRead = io.readFile(targetHeadPath(slot), wire.data(), wire.size(),
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

    char manifestPath[kTargetStorePathMax] = {};
    if (!formatTargetStorePath(TargetStoreFileKind::Manifest,
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

    TargetManifest manifest{};
    if (decodeTargetManifest(workspace.manifest.data(), manifestSize,
                             &manifest) != TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    char catalogPath[kTargetStorePathMax] = {};
    if (!formatTargetStorePath(TargetStoreFileKind::Catalog,
                               loaded.record.generation, catalogPath,
                               sizeof(catalogPath))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t catalogSize = 0;
    if (io.readFile(catalogPath, workspace.catalog.data(),
                    workspace.catalog.size(), &catalogSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        reopenTargetCatalog(workspace.manifest.data(), manifestSize,
                            workspace.catalog.data(), catalogSize,
                            validationScratch) != TargetCodecStatus::Valid) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

TargetStoreStatus reopenSelected(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    std::uint32_t generation, domain::targets::TargetCatalog* output) {
    output->clear();
    char manifestPath[kTargetStorePathMax] = {};
    char catalogPath[kTargetStorePathMax] = {};
    if (!formatTargetStorePath(TargetStoreFileKind::Manifest, generation,
                               manifestPath, sizeof(manifestPath)) ||
        !formatTargetStorePath(TargetStoreFileKind::Catalog, generation,
                               catalogPath, sizeof(catalogPath))) {
        return TargetStoreStatus::PathError;
    }
    std::size_t manifestSize = 0;
    std::size_t catalogSize = 0;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(catalogPath, workspace.catalog.data(),
                    workspace.catalog.size(), &catalogSize) !=
            SessionStoreIo::ReadStatus::Ok) {
        return TargetStoreStatus::IoError;
    }
    const bool valid = reopenTargetCatalog(
        workspace.manifest.data(), manifestSize, workspace.catalog.data(),
        catalogSize, output) == TargetCodecStatus::Valid;
    workspace.manifestSize = valid ? manifestSize : 0;
    workspace.catalogSize = valid ? catalogSize : 0;
    return valid ? TargetStoreStatus::Valid
                 : TargetStoreStatus::CorruptGeneration;
}

}  // namespace

bool formatTargetStorePath(TargetStoreFileKind kind,
                           std::uint32_t generation, char* output,
                           std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    int written = -1;
    switch (kind) {
        case TargetStoreFileKind::Catalog:
            written = std::snprintf(output, capacity,
                                    "target-catalog-%08lu.bin",
                                    static_cast<unsigned long>(generation));
            break;
        case TargetStoreFileKind::Manifest:
            written = std::snprintf(output, capacity,
                                    "target-manifest-%08lu.bin",
                                    static_cast<unsigned long>(generation));
            break;
        case TargetStoreFileKind::HeadA:
            written = std::snprintf(output, capacity, "target-head-a.bin");
            break;
        case TargetStoreFileKind::HeadB:
            written = std::snprintf(output, capacity, "target-head-b.bin");
            break;
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

const char* targetStoreStatusName(TargetStoreStatus status) {
    switch (status) {
        case TargetStoreStatus::Valid: return "valid";
        case TargetStoreStatus::InvalidArgument: return "invalid_argument";
        case TargetStoreStatus::EncodeFailed: return "encode_failed";
        case TargetStoreStatus::PathError: return "path_error";
        case TargetStoreStatus::IoError: return "io_error";
        case TargetStoreStatus::SyncError: return "sync_error";
        case TargetStoreStatus::Empty: return "empty";
        case TargetStoreStatus::NoGeneration: return "no_generation";
        case TargetStoreStatus::Conflict: return "conflict";
        case TargetStoreStatus::CorruptGeneration: return "corrupt_generation";
    }
    return "unknown";
}

TargetStoreCommitResult commitTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog, std::uint32_t generation,
    HeadSlot publishSlot) {
    TargetStoreCommitResult result;
    result.generation = generation;
    result.publishedSlot = publishSlot;
    if (generation == 0 || catalog.size() == 0) {
        result.status = TargetStoreStatus::InvalidArgument;
        return result;
    }
    std::size_t catalogSize = 0;
    std::size_t manifestSize = 0;
    if (encodeTargetCatalog(catalog, workspace.catalog.data(),
                            workspace.catalog.size(), &catalogSize) !=
            TargetCodecStatus::Valid ||
        encodeTargetManifest(catalog, workspace.catalog.data(), catalogSize,
                             workspace.manifest.data(),
                             workspace.manifest.size(), &manifestSize) !=
            TargetCodecStatus::Valid) {
        result.status = TargetStoreStatus::EncodeFailed;
        return result;
    }
    workspace.catalogSize = catalogSize;
    workspace.manifestSize = manifestSize;
    TargetCommitBackend backend(io, workspace, catalogSize, manifestSize,
                                generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = TargetStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        generation, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? TargetStoreStatus::Valid : commitFailureStatus(committed.stage);
    if (result.complete()) workspace.generation = generation;
    return result;
}

TargetStoreCommitResult commitNextTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    const domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& recoveryScratch) {
    TargetStoreCommitResult result;
    if (&catalog == &recoveryScratch || catalog.size() == 0) {
        result.status = TargetStoreStatus::InvalidArgument;
        return result;
    }
    const TargetStoreRecoveryResult current =
        recoverTargetCatalog(io, workspace, &recoveryScratch);
    if (current.status == TargetStoreStatus::Empty) {
        return commitTargetCatalog(io, workspace, catalog, 1, HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    if (current.generation == UINT32_MAX) {
        result.status = TargetStoreStatus::Conflict;
        return result;
    }
    const HeadSlot publish =
        current.choice == RecoveryChoice::A ? HeadSlot::B : HeadSlot::A;
    return commitTargetCatalog(io, workspace, catalog,
                               current.generation + 1U, publish);
}

TargetStoreRecoveryResult recoverTargetCatalog(
    SessionStoreIo& io, TargetStoreWorkspace& workspace,
    domain::targets::TargetCatalog* output) {
    TargetStoreRecoveryResult result;
    if (output == nullptr) {
        result.status = TargetStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCandidate(io, workspace, HeadSlot::A, output);
    CandidateLoad b = loadCandidate(io, workspace, HeadSlot::B, output);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        output->clear();
        result.status = TargetStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        output->clear();
        result.status = TargetStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        output->clear();
        result.status = TargetStoreStatus::NoGeneration;
        return result;
    }
    result.generation = recovered.selected.generation;
    result.status = reopenSelected(io, workspace, result.generation, output);
    if (result.status == TargetStoreStatus::Valid) {
        result.targets = output->size();
        workspace.generation = result.generation;
    }
    return result;
}

}  // namespace leshy1::storage
