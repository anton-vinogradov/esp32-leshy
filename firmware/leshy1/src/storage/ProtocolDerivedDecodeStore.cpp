#include "ProtocolDerivedDecodeStore.h"

#include <cstdio>
#include <cstring>

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kManifestMagic[4] = {'L', 'P', 'D', 'M'};
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

bool sameSource(const apps::protocol::ProtocolAnnotationSource& left,
                const apps::protocol::ProtocolAnnotationSource& right) {
    return apps::protocol::sameProtocolAnnotationSource(left, right);
}

bool encodeManifest(const std::uint8_t* payload, std::size_t payloadSize,
                    std::uint8_t* output, std::size_t capacity) {
    if (payload == nullptr || payloadSize == 0U || output == nullptr ||
        capacity < kProtocolDerivedDecodeManifestBytes ||
        payloadSize > UINT32_MAX) {
        return false;
    }
    std::memset(output, 0, kProtocolDerivedDecodeManifestBytes);
    std::memcpy(output, kManifestMagic, sizeof(kManifestMagic));
    put16(output + 4U, kManifestSchema);
    put32(output + 8U, static_cast<std::uint32_t>(payloadSize));
    put32(output + 12U, crc32c(payload, payloadSize));
    return true;
}

bool manifestMatches(const std::uint8_t* manifest, std::size_t manifestSize,
                     const std::uint8_t* payload, std::size_t payloadSize) {
    return manifest != nullptr && payload != nullptr &&
        manifestSize == kProtocolDerivedDecodeManifestBytes &&
        std::memcmp(manifest, kManifestMagic, sizeof(kManifestMagic)) == 0 &&
        get16(manifest + 4U) == kManifestSchema &&
        get16(manifest + 6U) == 0U &&
        get32(manifest + 8U) == payloadSize &&
        get32(manifest + 12U) == crc32c(payload, payloadSize);
}

class DerivedCommitBackend final : public CommitBackend {
public:
    DerivedCommitBackend(SessionStoreIo& io,
                         ProtocolDerivedDecodeStoreWorkspace& workspace,
                         std::uint32_t captureGeneration,
                         std::uint32_t annotationGeneration,
                         std::uint32_t storeGeneration, HeadSlot slot)
        : io_(io), workspace_(workspace),
          captureGeneration_(captureGeneration),
          annotationGeneration_(annotationGeneration),
          storeGeneration_(storeGeneration), slot_(slot) {}

    bool pathsReady() {
        return formatProtocolDerivedDecodeStorePath(
                   ProtocolDerivedDecodeStoreFileKind::Payload,
                   captureGeneration_, annotationGeneration_, storeGeneration_,
                   payloadPath_, sizeof(payloadPath_)) &&
            formatProtocolDerivedDecodeStorePath(
                ProtocolDerivedDecodeStoreFileKind::Manifest,
                captureGeneration_, annotationGeneration_, storeGeneration_,
                manifestPath_, sizeof(manifestPath_)) &&
            formatProtocolDerivedDecodeStorePath(
                slot_ == HeadSlot::A
                    ? ProtocolDerivedDecodeStoreFileKind::HeadA
                    : ProtocolDerivedDecodeStoreFileKind::HeadB,
                captureGeneration_, annotationGeneration_, 0U,
                headPath_, sizeof(headPath_));
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
    ProtocolDerivedDecodeStoreWorkspace& workspace_;
    std::uint32_t captureGeneration_ = 0U;
    std::uint32_t annotationGeneration_ = 0U;
    std::uint32_t storeGeneration_ = 0U;
    HeadSlot slot_ = HeadSlot::A;
    char payloadPath_[kProtocolDerivedDecodeStorePathMax] = {};
    char manifestPath_[kProtocolDerivedDecodeStorePathMax] = {};
    char headPath_[kProtocolDerivedDecodeStorePathMax] = {};
};

ProtocolDerivedDecodeStoreStatus failureStatus(CommitStage stage) {
    switch (stage) {
        case CommitStage::SyncPayloads:
        case CommitStage::SyncManifest:
        case CommitStage::SyncHead:
            return ProtocolDerivedDecodeStoreStatus::SyncError;
        default: return ProtocolDerivedDecodeStoreStatus::IoError;
    }
}

struct CandidateLoad final {
    HeadCandidate candidate{};
    HeadRecord record{};
    SessionStoreIo::ReadStatus headRead = SessionStoreIo::ReadStatus::NotFound;
};

CandidateLoad loadCandidate(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    std::uint32_t expectedAnnotationGeneration, HeadSlot slot,
    apps::protocol::ProtocolDerivedDecode* validationScratch) {
    CandidateLoad loaded;
    auto& wire = slot == HeadSlot::A ? workspace.headA : workspace.headB;
    char headPath[kProtocolDerivedDecodeStorePathMax] = {};
    if (!formatProtocolDerivedDecodeStorePath(
            slot == HeadSlot::A
                ? ProtocolDerivedDecodeStoreFileKind::HeadA
                : ProtocolDerivedDecodeStoreFileKind::HeadB,
            expectedSource.captureGeneration, expectedAnnotationGeneration,
            0U, headPath, sizeof(headPath))) {
        return loaded;
    }
    std::size_t headSize = 0U;
    loaded.headRead = io.readFile(
        headPath, wire.data(), wire.size(), &headSize);
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
    char manifestPath[kProtocolDerivedDecodeStorePathMax] = {};
    char payloadPath[kProtocolDerivedDecodeStorePathMax] = {};
    if (!formatProtocolDerivedDecodeStorePath(
            ProtocolDerivedDecodeStoreFileKind::Manifest,
            expectedSource.captureGeneration, expectedAnnotationGeneration,
            loaded.record.generation, manifestPath, sizeof(manifestPath)) ||
        !formatProtocolDerivedDecodeStorePath(
            ProtocolDerivedDecodeStoreFileKind::Payload,
            expectedSource.captureGeneration, expectedAnnotationGeneration,
            loaded.record.generation, payloadPath, sizeof(payloadPath))) {
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
        loaded.record.manifestCrc32c != loaded.candidate.manifest.crc32c) {
        return loaded;
    }
    std::size_t payloadSize = 0U;
    if (io.readFile(payloadPath, workspace.payload.data(),
                    workspace.payload.size(), &payloadSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        !manifestMatches(workspace.manifest.data(), manifestSize,
                         workspace.payload.data(), payloadSize) ||
        decodeProtocolDerivedDecode(workspace.payload.data(), payloadSize,
                                    validationScratch) !=
            ProtocolDerivedDecodeCodecStatus::Valid ||
        !sameSource(validationScratch->source, expectedSource) ||
        validationScratch->annotationStoreGeneration !=
            expectedAnnotationGeneration) {
        return loaded;
    }
    loaded.candidate.payloadValid = true;
    return loaded;
}

ProtocolDerivedDecodeStoreStatus reopenSelected(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    std::uint32_t expectedAnnotationGeneration,
    std::uint32_t storeGeneration,
    apps::protocol::ProtocolDerivedDecode* output) {
    char manifestPath[kProtocolDerivedDecodeStorePathMax] = {};
    char payloadPath[kProtocolDerivedDecodeStorePathMax] = {};
    if (!formatProtocolDerivedDecodeStorePath(
            ProtocolDerivedDecodeStoreFileKind::Manifest,
            expectedSource.captureGeneration, expectedAnnotationGeneration,
            storeGeneration, manifestPath, sizeof(manifestPath)) ||
        !formatProtocolDerivedDecodeStorePath(
            ProtocolDerivedDecodeStoreFileKind::Payload,
            expectedSource.captureGeneration, expectedAnnotationGeneration,
            storeGeneration, payloadPath, sizeof(payloadPath))) {
        return ProtocolDerivedDecodeStoreStatus::PathError;
    }
    std::size_t manifestSize = 0U;
    std::size_t payloadSize = 0U;
    if (io.readFile(manifestPath, workspace.manifest.data(),
                    workspace.manifest.size(), &manifestSize) !=
            SessionStoreIo::ReadStatus::Ok ||
        io.readFile(payloadPath, workspace.payload.data(),
                    workspace.payload.size(), &payloadSize) !=
            SessionStoreIo::ReadStatus::Ok) {
        return ProtocolDerivedDecodeStoreStatus::IoError;
    }
    if (!manifestMatches(workspace.manifest.data(), manifestSize,
                         workspace.payload.data(), payloadSize) ||
        decodeProtocolDerivedDecode(workspace.payload.data(), payloadSize,
                                    output) !=
            ProtocolDerivedDecodeCodecStatus::Valid) {
        *output = {};
        return ProtocolDerivedDecodeStoreStatus::CorruptGeneration;
    }
    if (!sameSource(output->source, expectedSource)) {
        *output = {};
        return ProtocolDerivedDecodeStoreStatus::SourceMismatch;
    }
    if (output->annotationStoreGeneration != expectedAnnotationGeneration) {
        *output = {};
        return ProtocolDerivedDecodeStoreStatus::AnnotationMismatch;
    }
    workspace.payloadSize = payloadSize;
    workspace.storeGeneration = storeGeneration;
    return ProtocolDerivedDecodeStoreStatus::Valid;
}

}  // namespace

bool formatProtocolDerivedDecodeStorePath(
    ProtocolDerivedDecodeStoreFileKind kind,
    std::uint32_t captureGeneration,
    std::uint32_t annotationStoreGeneration,
    std::uint32_t derivedStoreGeneration,
    char* output, std::size_t capacity) {
    if (captureGeneration == 0U || annotationStoreGeneration == 0U ||
        output == nullptr || capacity == 0U) {
        return false;
    }
    int written = -1;
    switch (kind) {
        case ProtocolDerivedDecodeStoreFileKind::Payload:
            if (derivedStoreGeneration == 0U) return false;
            written = std::snprintf(
                output, capacity,
                "protocol-derived-%08lu-%08lu-%08lu.bin",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(annotationStoreGeneration),
                static_cast<unsigned long>(derivedStoreGeneration));
            break;
        case ProtocolDerivedDecodeStoreFileKind::Manifest:
            if (derivedStoreGeneration == 0U) return false;
            written = std::snprintf(
                output, capacity,
                "protocol-derived-%08lu-%08lu-%08lu.manifest",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(annotationStoreGeneration),
                static_cast<unsigned long>(derivedStoreGeneration));
            break;
        case ProtocolDerivedDecodeStoreFileKind::HeadA:
            written = std::snprintf(
                output, capacity,
                "protocol-derived-%08lu-%08lu-head-a.bin",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(annotationStoreGeneration));
            break;
        case ProtocolDerivedDecodeStoreFileKind::HeadB:
            written = std::snprintf(
                output, capacity,
                "protocol-derived-%08lu-%08lu-head-b.bin",
                static_cast<unsigned long>(captureGeneration),
                static_cast<unsigned long>(annotationStoreGeneration));
            break;
    }
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

const char* protocolDerivedDecodeStoreStatusName(
    ProtocolDerivedDecodeStoreStatus status) {
    switch (status) {
        case ProtocolDerivedDecodeStoreStatus::Valid: return "valid";
        case ProtocolDerivedDecodeStoreStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolDerivedDecodeStoreStatus::EncodeFailed:
            return "encode_failed";
        case ProtocolDerivedDecodeStoreStatus::PathError: return "path_error";
        case ProtocolDerivedDecodeStoreStatus::IoError: return "io_error";
        case ProtocolDerivedDecodeStoreStatus::SyncError: return "sync_error";
        case ProtocolDerivedDecodeStoreStatus::Empty: return "empty";
        case ProtocolDerivedDecodeStoreStatus::NoGeneration:
            return "no_generation";
        case ProtocolDerivedDecodeStoreStatus::Conflict: return "conflict";
        case ProtocolDerivedDecodeStoreStatus::CorruptGeneration:
            return "corrupt_generation";
        case ProtocolDerivedDecodeStoreStatus::SourceMismatch:
            return "source_mismatch";
        case ProtocolDerivedDecodeStoreStatus::AnnotationMismatch:
            return "annotation_mismatch";
    }
    return "invalid_argument";
}

ProtocolDerivedDecodeStoreCommitResult commitProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolDerivedDecode& decode,
    std::uint32_t storeGeneration, HeadSlot publishSlot) {
    ProtocolDerivedDecodeStoreCommitResult result;
    result.storeGeneration = storeGeneration;
    result.publishedSlot = publishSlot;
    if (!decode.valid() || storeGeneration == 0U) {
        result.status = ProtocolDerivedDecodeStoreStatus::InvalidArgument;
        return result;
    }
    if (encodeProtocolDerivedDecode(
            decode, workspace.payload.data(), workspace.payload.size(),
            &workspace.payloadSize) !=
            ProtocolDerivedDecodeCodecStatus::Valid ||
        !encodeManifest(workspace.payload.data(), workspace.payloadSize,
                        workspace.manifest.data(), workspace.manifest.size())) {
        result.status = ProtocolDerivedDecodeStoreStatus::EncodeFailed;
        return result;
    }
    DerivedCommitBackend backend(
        io, workspace, decode.source.captureGeneration,
        decode.annotationStoreGeneration, storeGeneration, publishSlot);
    if (!backend.pathsReady()) {
        result.status = ProtocolDerivedDecodeStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        storeGeneration,
        static_cast<std::uint32_t>(workspace.manifest.size()),
        crc32c(workspace.manifest.data(), workspace.manifest.size())};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? ProtocolDerivedDecodeStoreStatus::Valid
        : failureStatus(committed.stage);
    if (result.complete()) workspace.storeGeneration = storeGeneration;
    return result;
}

ProtocolDerivedDecodeStoreCommitResult commitNextProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolDerivedDecode& decode,
    apps::protocol::ProtocolDerivedDecode& recoveryScratch) {
    ProtocolDerivedDecodeStoreCommitResult result;
    if (!decode.valid() || &decode == &recoveryScratch) {
        result.status = ProtocolDerivedDecodeStoreStatus::InvalidArgument;
        return result;
    }
    const auto current = recoverProtocolDerivedDecode(
        io, workspace, decode.source, decode.annotationStoreGeneration,
        &recoveryScratch);
    if (current.status == ProtocolDerivedDecodeStoreStatus::Empty) {
        return commitProtocolDerivedDecode(io, workspace, decode, 1U,
                                           HeadSlot::A);
    }
    if (!current.valid()) {
        result.status = current.status;
        return result;
    }
    if (current.storeGeneration == UINT32_MAX) {
        result.status = ProtocolDerivedDecodeStoreStatus::Conflict;
        return result;
    }
    const HeadSlot publish = current.choice == RecoveryChoice::A
        ? HeadSlot::B : HeadSlot::A;
    return commitProtocolDerivedDecode(
        io, workspace, decode, current.storeGeneration + 1U, publish);
}

ProtocolDerivedDecodeStoreRecoveryResult recoverProtocolDerivedDecode(
    SessionStoreIo& io, ProtocolDerivedDecodeStoreWorkspace& workspace,
    const apps::protocol::ProtocolAnnotationSource& expectedSource,
    std::uint32_t expectedAnnotationStoreGeneration,
    apps::protocol::ProtocolDerivedDecode* output) {
    ProtocolDerivedDecodeStoreRecoveryResult result;
    if (!expectedSource.valid() || expectedAnnotationStoreGeneration == 0U ||
        output == nullptr) {
        result.status = ProtocolDerivedDecodeStoreStatus::InvalidArgument;
        return result;
    }
    CandidateLoad a = loadCandidate(
        io, workspace, expectedSource, expectedAnnotationStoreGeneration,
        HeadSlot::A, output);
    CandidateLoad b = loadCandidate(
        io, workspace, expectedSource, expectedAnnotationStoreGeneration,
        HeadSlot::B, output);
    if (a.headRead == SessionStoreIo::ReadStatus::NotFound &&
        b.headRead == SessionStoreIo::ReadStatus::NotFound) {
        *output = {};
        result.status = ProtocolDerivedDecodeStoreStatus::Empty;
        return result;
    }
    const RecoveryResult recovered = recoverHead(a.candidate, b.candidate);
    result.choice = recovered.choice;
    result.aStatus = recovered.aStatus;
    result.bStatus = recovered.bStatus;
    if (recovered.choice == RecoveryChoice::Conflict) {
        *output = {};
        result.status = ProtocolDerivedDecodeStoreStatus::Conflict;
        return result;
    }
    if (recovered.choice != RecoveryChoice::A &&
        recovered.choice != RecoveryChoice::B) {
        *output = {};
        result.status = ProtocolDerivedDecodeStoreStatus::NoGeneration;
        return result;
    }
    result.storeGeneration = recovered.selected.generation;
    result.status = reopenSelected(
        io, workspace, expectedSource, expectedAnnotationStoreGeneration,
        result.storeGeneration, output);
    if (result.valid()) result.fields = output->fieldCount;
    return result;
}

}  // namespace leshy1::storage
