#include "ProtocolAnnotationStore.h"

#include <cstdio>
#include <cstring>

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kManifestMagic[4] = {'L', 'P', 'A', 'M'};
constexpr std::uint16_t kManifestSchema = 1U;

void put16(std::uint8_t* output, std::uint16_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 8U);
    output[1] = static_cast<std::uint8_t>(value);
}

void put32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 24U);
    output[1] = static_cast<std::uint8_t>(value >> 16U);
    output[2] = static_cast<std::uint8_t>(value >> 8U);
    output[3] = static_cast<std::uint8_t>(value);
}

std::uint16_t get16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(input[0]) << 8U) |
        static_cast<std::uint16_t>(input[1]));
}

std::uint32_t get32(const std::uint8_t* input) {
    return (static_cast<std::uint32_t>(input[0]) << 24U) |
        (static_cast<std::uint32_t>(input[1]) << 16U) |
        (static_cast<std::uint32_t>(input[2]) << 8U) |
        static_cast<std::uint32_t>(input[3]);
}

bool encodeManifest(const std::uint8_t* payload, std::size_t payloadSize,
                    std::uint8_t* output, std::size_t capacity) {
    if (payload == nullptr || payloadSize == 0U || output == nullptr ||
        capacity < kProtocolAnnotationManifestBytes ||
        payloadSize > UINT32_MAX) {
        return false;
    }
    std::memset(output, 0, kProtocolAnnotationManifestBytes);
    std::memcpy(output, kManifestMagic, sizeof(kManifestMagic));
    put16(output + 4U, kManifestSchema);
    put32(output + 8U, static_cast<std::uint32_t>(payloadSize));
    put32(output + 12U, crc32c(payload, payloadSize));
    return true;
}

bool manifestMatches(const std::uint8_t* manifest, std::size_t manifestSize,
                     const std::uint8_t* payload, std::size_t payloadSize) {
    return manifest != nullptr && payload != nullptr &&
        manifestSize == kProtocolAnnotationManifestBytes &&
        std::memcmp(manifest, kManifestMagic, sizeof(kManifestMagic)) == 0 &&
        get16(manifest + 4U) == kManifestSchema &&
        get16(manifest + 6U) == 0U &&
        get32(manifest + 8U) == payloadSize &&
        get32(manifest + 12U) == crc32c(payload, payloadSize);
}

class AnnotationCommitBackend final : public CommitBackend {
public:
    AnnotationCommitBackend(SessionStoreIo& io,
                            ProtocolAnnotationStoreWorkspace& workspace,
                            std::uint32_t captureGeneration,
                            std::uint32_t storeGeneration, HeadSlot slot)
        : io_(io), workspace_(workspace),
          captureGeneration_(captureGeneration),
          storeGeneration_(storeGeneration), slot_(slot) {}

    bool pathsReady() {
        return formatProtocolAnnotationStorePath(
                   ProtocolAnnotationStoreFileKind::Payload,
                   captureGeneration_, storeGeneration_, payloadPath_,
                   sizeof(payloadPath_)) &&
            formatProtocolAnnotationStorePath(
                ProtocolAnnotationStoreFileKind::Manifest,
                captureGeneration_, storeGeneration_, manifestPath_,
                sizeof(manifestPath_)) &&
            formatProtocolAnnotationStorePath(
                slot_ == HeadSlot::A
                    ? ProtocolAnnotationStoreFileKind::HeadA
                    : ProtocolAnnotationStoreFileKind::HeadB,
                captureGeneration_, 0U, headPath_, sizeof(headPath_));
    }

    bool writePayloads() override {
        return io_.writeFile(payloadPath_, workspace_.payload.data(),
                             workspace_.payloadSize);
    }
    bool syncPayloads() override {
        return io_.syncFile(payloadPath_) && io_.syncDirectory();
    }
    bool writeManifest() override {
        return io_.writeFile(manifestPath_, workspace_.manifest.data(),
                             workspace_.manifest.size());
    }
    bool syncManifest() override {
        return io_.syncFile(manifestPath_) && io_.syncDirectory();
    }
    bool writeOlderHead(const std::uint8_t* wire,
                        std::size_t size) override {
        return io_.writeFile(headPath_, wire, size);
    }
    bool syncHead() override {
        return io_.syncFile(headPath_) && io_.syncDirectory();
    }

private:
    SessionStoreIo& io_;
    ProtocolAnnotationStoreWorkspace& workspace_;
    std::uint32_t captureGeneration_ = 0U;
    std::uint32_t storeGeneration_ = 0U;
    HeadSlot slot_ = HeadSlot::A;
    char payloadPath_[kProtocolAnnotationStorePathMax] = {};
    char manifestPath_[kProtocolAnnotationStorePathMax] = {};
    char headPath_[kProtocolAnnotationStorePathMax] = {};
};

ProtocolAnnotationStoreStatus failureStatus(CommitStage stage) {
    switch (stage) {
        case CommitStage::SyncPayloads:
        case CommitStage::SyncManifest:
        case CommitStage::SyncHead:
            return ProtocolAnnotationStoreStatus::SyncError;
        default: return ProtocolAnnotationStoreStatus::IoError;
    }
}

struct CandidateLoad final {
    HeadCandidate candidate{};
    HeadRecord record{};
    SessionStoreIo::ReadStatus headRead = SessionStoreIo::ReadStatus::NotFound;
};

CandidateLoad loadCandidate(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    HeadSlot slot, apps::protocol::ProtocolAnnotationSet* validationScratch) {
    CandidateLoad loaded;
    auto& wire = slot == HeadSlot::A ? workspace.headA : workspace.headB;
    char headPath[kProtocolAnnotationStorePathMax] = {};
    if (!formatProtocolAnnotationStorePath(
            slot == HeadSlot::A
                ? ProtocolAnnotationStoreFileKind::HeadA
                : ProtocolAnnotationStoreFileKind::HeadB,
            expectedSource.captureGeneration, 0U, headPath,
            sizeof(headPath))) {
        return loaded;
    }
    std::size_t headSize = 0U;
    loaded.headRead =
        io.readFile(headPath, wire.data(), wire.size(), &headSize);
    loaded.candidate = {wire.data(),
                        loaded.headRead == SessionStoreIo::ReadStatus::Ok
                            ? headSize : 0U,
                        {}, false};
    if (loaded.headRead != SessionStoreIo::ReadStatus::Ok ||
        decodeHead(wire.data(), headSize, &loaded.record) !=
            HeadDecodeStatus::Valid ||
        loaded.record.generation == 0U) {
        return loaded;
    }

    char manifestPath[kProtocolAnnotationStorePathMax] = {};
    char payloadPath[kProtocolAnnotationStorePathMax] = {};
    if (!formatProtocolAnnotationStorePath(
            ProtocolAnnotationStoreFileKind::Manifest,
            expectedSource.captureGeneration, loaded.record.generation,
            manifestPath, sizeof(manifestPath)) ||
        !formatProtocolAnnotationStorePath(
            ProtocolAnnotationStoreFileKind::Payload,
            expectedSource.captureGeneration, loaded.record.generation,
            payloadPath, sizeof(payloadPath))) {
        return loaded;
    }
    std::size_t manifestSize = 0U;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (loaded.record.manifestLength != manifestSize ||
        loaded.record.manifestCrc32c !=
            loaded.candidate.manifest.crc32c) {
        return loaded;
    }
    std::size_t payloadSize = 0U;
    if (io.readFile(payloadPath, workspace.payload.data(),
                    workspace.payload.size(), &payloadSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        !manifestMatches(workspace.manifest.data(), manifestSize,
                         workspace.payload.data(), payloadSize) ||
        decodeProtocolAnnotations(workspace.payload.data(), payloadSize,
                                  validationScratch) !=
            ProtocolAnnotationCodecStatus::Valid ||
        !sameProtocolAnnotationSource(validationScratch->source(),
                                      expectedSource)) {
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

ProtocolAnnotationStoreStatus reopenSelected(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    std::uint32_t storeGeneration,
    apps::protocol::ProtocolAnnotationSet* output) {
    char manifestPath[kProtocolAnnotationStorePathMax] = {};
    char payloadPath[kProtocolAnnotationStorePathMax] = {};
    if (!formatProtocolAnnotationStorePath(
            ProtocolAnnotationStoreFileKind::Manifest,
            expectedSource.captureGeneration, storeGeneration, manifestPath,
            sizeof(manifestPath)) ||
        !formatProtocolAnnotationStorePath(
            ProtocolAnnotationStoreFileKind::Payload,
            expectedSource.captureGeneration, storeGeneration, payloadPath,
            sizeof(payloadPath))) {
        return ProtocolAnnotationStoreStatus::PathError;
    }
    std::size_t manifestSize = 0U;
    std::size_t payloadSize = 0U;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(payloadPath, workspace.payload.data(),
                    workspace.payload.size(), &payloadSize) !=
            SessionStoreIo::ReadStatus::Ok) {
        return ProtocolAnnotationStoreStatus::IoError;
    }
    if (!manifestMatches(workspace.manifest.data(), manifestSize,
                         workspace.payload.data(), payloadSize) ||
        decodeProtocolAnnotations(workspace.payload.data(), payloadSize,
                                  output) !=
            ProtocolAnnotationCodecStatus::Valid) {
        output->clear();
        return ProtocolAnnotationStoreStatus::CorruptGeneration;
    }
    if (!sameProtocolAnnotationSource(output->source(), expectedSource)) {
        output->clear();
        return ProtocolAnnotationStoreStatus::SourceMismatch;
    }
    workspace.payloadSize = payloadSize;
    workspace.storeGeneration = storeGeneration;
    return ProtocolAnnotationStoreStatus::Valid;
}

}  // namespace

bool formatProtocolAnnotationStorePath(
    ProtocolAnnotationStoreFileKind kind, std::uint32_t captureGeneration,
    std::uint32_t storeGeneration, char* output, std::size_t capacity) {
    if (captureGeneration == 0U || output == nullptr || capacity == 0U) {
        return false;
    }
    int written = -1;
    switch (kind) {
        case ProtocolAnnotationStoreFileKind::Payload:
            if (storeGeneration == 0U) return false;
            written = std::snprintf(
                output, capacity, "protocol-annotations-%08lu-%08lu.bin",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(storeGeneration));
            break;
        case ProtocolAnnotationStoreFileKind::Manifest:
            if (storeGeneration == 0U) return false;
            written = std::snprintf(
                output, capacity,
                "protocol-annotations-%08lu-%08lu.manifest",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(storeGeneration));
            break;
        case ProtocolAnnotationStoreFileKind::HeadA:
            written = std::snprintf(
                output, capacity, "protocol-annotations-%08lu-head-a.bin",
                static_cast<unsigned long>(captureGeneration));
            break;
        case ProtocolAnnotationStoreFileKind::HeadB:
            written = std::snprintf(
                output, capacity, "protocol-annotations-%08lu-head-b.bin",
                static_cast<unsigned long>(captureGeneration));
            break;
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

const char* protocolAnnotationStoreStatusName(
    ProtocolAnnotationStoreStatus status) {
    switch (status) {
        case ProtocolAnnotationStoreStatus::Valid: return "valid";
        case ProtocolAnnotationStoreStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolAnnotationStoreStatus::EncodeFailed:
            return "encode_failed";
        case ProtocolAnnotationStoreStatus::PathError: return "path_error";
        case ProtocolAnnotationStoreStatus::IoError: return "io_error";
        case ProtocolAnnotationStoreStatus::SyncError: return "sync_error";
        case ProtocolAnnotationStoreStatus::Empty: return "empty";
        case ProtocolAnnotationStoreStatus::NoGeneration:
            return "no_generation";
        case ProtocolAnnotationStoreStatus::Conflict: return "conflict";
        case ProtocolAnnotationStoreStatus::CorruptGeneration:
            return "corrupt_generation";
        case ProtocolAnnotationStoreStatus::SourceMismatch:
            return "source_mismatch";
    }
    return "invalid_argument";
}

ProtocolAnnotationStoreCommitResult commitProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSet& annotations,
    std::uint32_t storeGeneration, HeadSlot publishSlot) {
    ProtocolAnnotationStoreCommitResult result;
    result.storeGeneration = storeGeneration;
    result.publishedSlot = publishSlot;
    if (!annotations.bound() || storeGeneration == 0U) {
        result.status = ProtocolAnnotationStoreStatus::InvalidArgument;
        return result;
    }
    if (encodeProtocolAnnotations(
            annotations, workspace.payload.data(), workspace.payload.size(),
            &workspace.payloadSize) !=
            ProtocolAnnotationCodecStatus::Valid ||
        !encodeManifest(workspace.payload.data(), workspace.payloadSize,
                        workspace.manifest.data(), workspace.manifest.size())) {
        result.status = ProtocolAnnotationStoreStatus::EncodeFailed;
        return result;
    }
    AnnotationCommitBackend backend(
        io, workspace, annotations.source().captureGeneration,
        storeGeneration, publishSlot);
    if (!backend.pathsReady()) {
        result.status = ProtocolAnnotationStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        storeGeneration,
        static_cast<std::uint32_t>(workspace.manifest.size()),
        crc32c(workspace.manifest.data(), workspace.manifest.size())};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? ProtocolAnnotationStoreStatus::Valid
        : failureStatus(committed.stage);
    if (result.complete()) workspace.storeGeneration = storeGeneration;
    return result;
}

ProtocolAnnotationStoreCommitResult commitNextProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSet& annotations,
    apps::protocol::ProtocolAnnotationSet& recoveryScratch) {
    ProtocolAnnotationStoreCommitResult result;
    if (!annotations.bound() || &annotations == &recoveryScratch) {
        result.status = ProtocolAnnotationStoreStatus::InvalidArgument;
        return result;
    }
    const auto current = recoverProtocolAnnotations(
        io, workspace, annotations.source(), &recoveryScratch);
    if (current.status == ProtocolAnnotationStoreStatus::Empty) {
        return commitProtocolAnnotations(io, workspace, annotations, 1U,
                                         HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    if (current.storeGeneration == UINT32_MAX) {
        result.status = ProtocolAnnotationStoreStatus::Conflict;
        return result;
    }
    const HeadSlot publish = current.choice == RecoveryChoice::A
        ? HeadSlot::B : HeadSlot::A;
    return commitProtocolAnnotations(
        io, workspace, annotations, current.storeGeneration + 1U, publish);
}

ProtocolAnnotationStoreRecoveryResult recoverProtocolAnnotations(
    SessionStoreIo& io, ProtocolAnnotationStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    apps::protocol::ProtocolAnnotationSet* output) {
    ProtocolAnnotationStoreRecoveryResult result;
    if (!expectedSource.valid() || output == nullptr) {
        result.status = ProtocolAnnotationStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCandidate(
        io, workspace, expectedSource, HeadSlot::A, output);
    CandidateLoad b = loadCandidate(
        io, workspace, expectedSource, HeadSlot::B, output);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        output->clear();
        result.status = ProtocolAnnotationStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        output->clear();
        result.status = ProtocolAnnotationStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        output->clear();
        result.status = ProtocolAnnotationStoreStatus::NoGeneration;
        return result;
    }
    result.storeGeneration = recovered.selected.generation;
    result.status = reopenSelected(io, workspace, expectedSource,
                                   result.storeGeneration, output);
    if (result.valid()) result.annotations = output->size();
    return result;
}

}  // namespace leshy1::storage
