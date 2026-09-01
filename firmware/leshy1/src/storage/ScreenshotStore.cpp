#include "ScreenshotStore.h"

#include <cstdio>
#include <cstring>

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kManifestMagic[4] = {'L', 'S', 'S', 'C'};
constexpr std::uint16_t kManifestSchema = 1U;
constexpr std::size_t kManifestCrcOffset = kScreenshotManifestBytes - 4U;

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

void put64(std::uint8_t* output, std::uint64_t value) {
    for (std::size_t index = 0; index < 8U; ++index) {
        output[index] = static_cast<std::uint8_t>(
            value >> static_cast<unsigned>((7U - index) * 8U));
    }
}

std::uint16_t get16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(input[0]) << 8U) | input[1]);
}

std::uint32_t get32(const std::uint8_t* input) {
    return (static_cast<std::uint32_t>(input[0]) << 24U) |
        (static_cast<std::uint32_t>(input[1]) << 16U) |
        (static_cast<std::uint32_t>(input[2]) << 8U) |
        static_cast<std::uint32_t>(input[3]);
}

std::uint64_t get64(const std::uint8_t* input) {
    std::uint64_t value = 0U;
    for (std::size_t index = 0; index < 8U; ++index) {
        value = (value << 8U) | input[index];
    }
    return value;
}

bool validBuildVersion(
    const std::array<char, kScreenshotBuildVersionBytes>& version) {
    return version[0] != '\0' &&
        std::memchr(version.data(), '\0', version.size()) != nullptr;
}

bool validMetadata(const ScreenshotMetadata& metadata) {
    return metadata.generation != 0U &&
        metadata.width == kScreenshotWidth &&
        metadata.height == kScreenshotHeight &&
        metadata.pixelBytes == kScreenshotPixelBytes &&
        metadata.capturedUs != 0U &&
        metadata.format == ScreenshotPixelFormat::Rgb565BigEndian &&
        validBuildVersion(metadata.buildVersion);
}

char hexDigit(std::uint8_t value) {
    return value < 10U ? static_cast<char>('0' + value)
                       : static_cast<char>('a' + value - 10U);
}

struct CrcSinkContext final {
    std::uint32_t crc = 0xffffffffU;
    std::size_t bytes = 0U;
};

bool crcSink(std::size_t offset, const std::uint8_t* input,
             std::size_t size, void* context) {
    if (context == nullptr || input == nullptr) return false;
    auto* state = static_cast<CrcSinkContext*>(context);
    if (offset != state->bytes) return false;
    for (std::size_t index = 0; index < size; ++index) {
        state->crc ^= input[index];
        for (std::uint8_t bit = 0; bit < 8U; ++bit) {
            const std::uint32_t mask = 0U - (state->crc & 1U);
            state->crc = (state->crc >> 1U) ^ (0x82F63B78U & mask);
        }
    }
    state->bytes += size;
    return true;
}

ScreenshotStoreStatus commitFailureStatus(CommitStage stage) {
    return stage == CommitStage::SyncPayloads ||
                   stage == CommitStage::SyncManifest ||
                   stage == CommitStage::SyncHead
        ? ScreenshotStoreStatus::SyncError
        : ScreenshotStoreStatus::IoError;
}

class ScreenshotCommitBackend final : public CommitBackend {
public:
    ScreenshotCommitBackend(
        ScreenshotStoreIo& io,
        const std::array<std::uint8_t, kScreenshotManifestBytes>& manifest,
        ScreenshotSource source, void* sourceContext,
        std::uint32_t generation, HeadSlot publishSlot)
        : io_(io), manifest_(manifest), source_(source),
          sourceContext_(sourceContext), generation_(generation),
          publishSlot_(publishSlot) {
        pathsReady_ = formatScreenshotStorePath(
                ScreenshotFileKind::Pixels, generation_, pixelsPath_,
                sizeof(pixelsPath_)) &&
            formatScreenshotStorePath(
                ScreenshotFileKind::Manifest, generation_, manifestPath_,
                sizeof(manifestPath_)) &&
            formatScreenshotStorePath(
                publishSlot_ == HeadSlot::A ? ScreenshotFileKind::HeadA
                                            : ScreenshotFileKind::HeadB,
                0U, headPath_, sizeof(headPath_));
    }

    bool pathsReady() const { return pathsReady_; }
    bool writePayloads() override {
        return pathsReady_ && io_.writeStreamFile(
            pixelsPath_, kScreenshotPixelBytes, source_, sourceContext_);
    }
    bool syncPayloads() override { return io_.syncFile(pixelsPath_); }
    bool writeManifest() override {
        return io_.writeFile(manifestPath_, manifest_.data(), manifest_.size());
    }
    bool syncManifest() override { return io_.syncFile(manifestPath_); }
    bool writeOlderHead(const std::uint8_t* wire,
                        std::size_t size) override {
        return io_.writeFile(headPath_, wire, size);
    }
    bool syncHead() override {
        return io_.syncFile(headPath_) && io_.syncDirectory();
    }

private:
    ScreenshotStoreIo& io_;
    const std::array<std::uint8_t, kScreenshotManifestBytes>& manifest_;
    ScreenshotSource source_ = nullptr;
    void* sourceContext_ = nullptr;
    std::uint32_t generation_ = 0U;
    HeadSlot publishSlot_ = HeadSlot::A;
    char pixelsPath_[kSessionStorePathMax] = {};
    char manifestPath_[kSessionStorePathMax] = {};
    char headPath_[kSessionStorePathMax] = {};
    bool pathsReady_ = false;
};

struct LoadedCandidate final {
    HeadCandidate candidate{};
    HeadRecord record{};
    ScreenshotMetadata metadata{};
};

LoadedCandidate loadCandidateEnvelope(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    HeadSlot slot) {
    LoadedCandidate loaded{};
    auto& wire = slot == HeadSlot::A ? workspace.headA : workspace.headB;
    char path[kSessionStorePathMax] = {};
    if (!formatScreenshotStorePath(
            slot == HeadSlot::A ? ScreenshotFileKind::HeadA
                                : ScreenshotFileKind::HeadB,
            0U, path, sizeof(path))) {
        return loaded;
    }
    std::size_t wireSize = 0U;
    if (io.readFile(path, wire.data(), wire.size(), &wireSize) !=
        SessionStoreIo::ReadStatus::Ok) {
        return loaded;
    }
    loaded.candidate.wire = wire.data();
    loaded.candidate.wireSize = wireSize;
    if (decodeHead(wire.data(), wireSize, &loaded.record) !=
        HeadDecodeStatus::Valid) {
        return loaded;
    }
    if (!formatScreenshotStorePath(
            ScreenshotFileKind::Manifest, loaded.record.generation, path,
            sizeof(path))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    std::size_t manifestSize = 0U;
    if (io.readFile(path, workspace.manifest.data(), workspace.manifest.size(),
                    &manifestSize) != SessionStoreIo::ReadStatus::Ok) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    loaded.candidate.manifest = {
        true, static_cast<std::uint32_t>(manifestSize),
        crc32c(workspace.manifest.data(), manifestSize)};
    if (manifestSize != loaded.record.manifestLength ||
        loaded.candidate.manifest.crc32c !=
            loaded.record.manifestCrc32c ||
        !decodeScreenshotManifest(workspace.manifest.data(), manifestSize,
                                  &loaded.metadata) ||
        loaded.metadata.generation != loaded.record.generation ||
        !formatScreenshotStorePath(
            ScreenshotFileKind::Pixels, loaded.record.generation, path,
            sizeof(path))) {
        loaded.candidate.payloadValid = false;
        return loaded;
    }
    // Pixel validation is intentionally deferred until recoverHead selects the
    // newest valid envelope.  Reading both full 240x320 RGB565 generations on
    // every boot can exceed the bounded boot-recovery watchdog.  If the newest
    // pixels fail validation, recovery marks only that candidate invalid and
    // validates the older generation as the atomic fallback.
    loaded.candidate.payloadValid = true;
    return loaded;
}

bool validateCandidatePixels(ScreenshotStoreIo& io,
                             const LoadedCandidate& loaded) {
    if (!loaded.candidate.payloadValid) return false;
    char path[kSessionStorePathMax] = {};
    if (!formatScreenshotStorePath(
            ScreenshotFileKind::Pixels, loaded.record.generation, path,
            sizeof(path))) {
        return false;
    }
    CrcSinkContext crc{};
    std::size_t pixels = 0U;
    return io.readStreamFile(path, crcSink, &crc, &pixels) ==
               SessionStoreIo::ReadStatus::Ok &&
        pixels == loaded.metadata.pixelBytes && crc.bytes == pixels &&
        ~crc.crc == loaded.metadata.pixelCrc32c;
}

}  // namespace

const char* screenshotStoreStatusName(ScreenshotStoreStatus status) {
    switch (status) {
        case ScreenshotStoreStatus::Valid: return "valid";
        case ScreenshotStoreStatus::InvalidArgument: return "invalid_argument";
        case ScreenshotStoreStatus::EncodeFailed: return "encode_failed";
        case ScreenshotStoreStatus::PathError: return "path_error";
        case ScreenshotStoreStatus::IoError: return "io_error";
        case ScreenshotStoreStatus::SyncError: return "sync_error";
        case ScreenshotStoreStatus::Empty: return "empty";
        case ScreenshotStoreStatus::Conflict: return "conflict";
        case ScreenshotStoreStatus::CorruptGeneration:
            return "corrupt_generation";
    }
    return "invalid_argument";
}

bool formatScreenshotStorePath(ScreenshotFileKind kind,
                               std::uint32_t generation, char* output,
                               std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return false;
    int written = -1;
    switch (kind) {
        case ScreenshotFileKind::Pixels:
            written = std::snprintf(output, capacity,
                                    "screenshot-%08lu.rgb565",
                                    static_cast<unsigned long>(generation));
            break;
        case ScreenshotFileKind::Manifest:
            written = std::snprintf(output, capacity,
                                    "screenshot-%08lu.bin",
                                    static_cast<unsigned long>(generation));
            break;
        case ScreenshotFileKind::HeadA:
            written = std::snprintf(output, capacity,
                                    "screenshot-head-a.bin");
            break;
        case ScreenshotFileKind::HeadB:
            written = std::snprintf(output, capacity,
                                    "screenshot-head-b.bin");
            break;
    }
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool encodeScreenshotManifest(
    const ScreenshotMetadata& metadata,
    std::array<std::uint8_t, kScreenshotManifestBytes>* output) {
    if (output == nullptr || !validMetadata(metadata)) return false;
    output->fill(0U);
    std::memcpy(output->data(), kManifestMagic, sizeof(kManifestMagic));
    put16(output->data() + 4U, kManifestSchema);
    put16(output->data() + 6U,
          static_cast<std::uint16_t>(kScreenshotManifestBytes));
    put32(output->data() + 8U, metadata.generation);
    put16(output->data() + 12U, metadata.width);
    put16(output->data() + 14U, metadata.height);
    put32(output->data() + 16U, metadata.pixelBytes);
    put32(output->data() + 20U, metadata.pixelCrc32c);
    put64(output->data() + 24U, metadata.capturedUs);
    put32(output->data() + 32U, metadata.uiRevision);
    (*output)[36U] = metadata.uiPage;
    (*output)[37U] = static_cast<std::uint8_t>(metadata.format);
    std::memcpy(output->data() + 40U, metadata.buildVersion.data(),
                metadata.buildVersion.size());
    std::memcpy(output->data() + 64U, metadata.appElfSha256.data(),
                metadata.appElfSha256.size());
    put32(output->data() + kManifestCrcOffset,
          crc32c(output->data(), kManifestCrcOffset));
    return true;
}

bool decodeScreenshotManifest(const std::uint8_t* input, std::size_t size,
                              ScreenshotMetadata* output) {
    if (input == nullptr || output == nullptr ||
        size != kScreenshotManifestBytes ||
        std::memcmp(input, kManifestMagic, sizeof(kManifestMagic)) != 0 ||
        get16(input + 4U) != kManifestSchema ||
        get16(input + 6U) != kScreenshotManifestBytes ||
        get32(input + kManifestCrcOffset) !=
            crc32c(input, kManifestCrcOffset)) {
        return false;
    }
    ScreenshotMetadata decoded{};
    decoded.generation = get32(input + 8U);
    decoded.width = get16(input + 12U);
    decoded.height = get16(input + 14U);
    decoded.pixelBytes = get32(input + 16U);
    decoded.pixelCrc32c = get32(input + 20U);
    decoded.capturedUs = get64(input + 24U);
    decoded.uiRevision = get32(input + 32U);
    decoded.uiPage = input[36U];
    decoded.format = static_cast<ScreenshotPixelFormat>(input[37U]);
    std::memcpy(decoded.buildVersion.data(), input + 40U,
                decoded.buildVersion.size());
    std::memcpy(decoded.appElfSha256.data(), input + 64U,
                decoded.appElfSha256.size());
    if (!validMetadata(decoded)) return false;
    *output = decoded;
    return true;
}

bool formatScreenshotJsonSummary(const ScreenshotMetadata& metadata,
                                 char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U || !validMetadata(metadata)) {
        return false;
    }
    char hash[65] = {};
    for (std::size_t index = 0; index < metadata.appElfSha256.size(); ++index) {
        hash[index * 2U] = hexDigit(metadata.appElfSha256[index] >> 4U);
        hash[index * 2U + 1U] =
            hexDigit(metadata.appElfSha256[index] & 0x0fU);
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.screenshot.v1\",\"generation\":%lu,"
        "\"width\":%u,\"height\":%u,\"format\":\"rgb565be\","
        "\"bytes\":%lu,\"pixel_crc32c\":\"%08lx\","
        "\"captured_us\":%llu,\"ui_page\":%u,\"ui_revision\":%lu,"
        "\"build_version\":\"%s\",\"app_elf_sha256\":\"%s\"}",
        static_cast<unsigned long>(metadata.generation), metadata.width,
        metadata.height, static_cast<unsigned long>(metadata.pixelBytes),
        static_cast<unsigned long>(metadata.pixelCrc32c),
        static_cast<unsigned long long>(metadata.capturedUs), metadata.uiPage,
        static_cast<unsigned long>(metadata.uiRevision),
        metadata.buildVersion.data(), hash);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

ScreenshotStoreResult commitScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    const ScreenshotMetadata& metadata, ScreenshotSource source,
    void* sourceContext, std::uint32_t generation, HeadSlot publishSlot) {
    ScreenshotStoreResult result{};
    result.generation = generation;
    result.publishedSlot = publishSlot;
    ScreenshotMetadata manifest = metadata;
    manifest.generation = generation;
    if (source == nullptr || !encodeScreenshotManifest(
            manifest, &workspace.manifest)) {
        result.status = ScreenshotStoreStatus::EncodeFailed;
        return result;
    }
    ScreenshotCommitBackend backend(io, workspace.manifest, source,
                                    sourceContext, generation, publishSlot);
    if (!backend.pathsReady()) {
        result.status = ScreenshotStoreStatus::PathError;
        return result;
    }
    const HeadRecord head{
        generation, static_cast<std::uint32_t>(workspace.manifest.size()),
        crc32c(workspace.manifest.data(), workspace.manifest.size())};
    const CommitResult committed = commitGeneration(backend, head);
    result.stage = committed.stage;
    result.status = committed.complete
        ? ScreenshotStoreStatus::Valid
        : commitFailureStatus(committed.stage);
    if (result.valid()) workspace.metadata = manifest;
    return result;
}

ScreenshotStoreResult recoverScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    ScreenshotMetadata* output) {
    ScreenshotStoreResult result{};
    if (output == nullptr) return result;
    LoadedCandidate a = loadCandidateEnvelope(io, workspace, HeadSlot::A);
    LoadedCandidate b = loadCandidateEnvelope(io, workspace, HeadSlot::B);
    for (std::uint8_t attempt = 0U; attempt < 2U; ++attempt) {
        const RecoveryResult recovered = recoverHead(
            a.candidate, b.candidate);
        if (recovered.choice == RecoveryChoice::None) {
            result.status = a.candidate.wireSize == 0U &&
                                    b.candidate.wireSize == 0U
                ? ScreenshotStoreStatus::Empty
                : ScreenshotStoreStatus::CorruptGeneration;
            return result;
        }
        if (recovered.choice == RecoveryChoice::Conflict) {
            result.status = ScreenshotStoreStatus::Conflict;
            return result;
        }
        LoadedCandidate& selected = recovered.choice == RecoveryChoice::A
            ? a : b;
        if (validateCandidatePixels(io, selected)) {
            result.status = ScreenshotStoreStatus::Valid;
            result.generation = selected.record.generation;
            result.publishedSlot = recovered.choice == RecoveryChoice::A
                ? HeadSlot::A : HeadSlot::B;
            result.stage = CommitStage::Complete;
            workspace.metadata = selected.metadata;
            *output = selected.metadata;
            return result;
        }
        selected.candidate.payloadValid = false;
    }
    result.status = ScreenshotStoreStatus::CorruptGeneration;
    return result;
}

ScreenshotStoreResult commitNextScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    const ScreenshotMetadata& metadata, ScreenshotSource source,
    void* sourceContext) {
    ScreenshotMetadata current{};
    const ScreenshotStoreResult recovered = recoverScreenshot(
        io, workspace, &current);
    if (recovered.status == ScreenshotStoreStatus::Empty) {
        return commitScreenshot(io, workspace, metadata, source,
                                sourceContext, 1U, HeadSlot::A);
    }
    if (!recovered.valid()) return recovered;
    const HeadSlot nextSlot = recovered.publishedSlot == HeadSlot::A
        ? HeadSlot::B : HeadSlot::A;
    return commitScreenshot(io, workspace, metadata, source,
                            sourceContext, recovered.generation + 1U,
                            nextSlot);
}

ScreenshotStoreResult streamScreenshotPixels(
    ScreenshotStoreIo& io, const ScreenshotMetadata& metadata,
    ScreenshotSink sink, void* sinkContext) {
    ScreenshotStoreResult result{};
    result.generation = metadata.generation;
    if (!validMetadata(metadata) || sink == nullptr) return result;
    char path[kSessionStorePathMax] = {};
    if (!formatScreenshotStorePath(ScreenshotFileKind::Pixels,
                                   metadata.generation, path,
                                   sizeof(path))) {
        result.status = ScreenshotStoreStatus::PathError;
        return result;
    }
    std::size_t size = 0U;
    result.status = io.readStreamFile(path, sink, sinkContext, &size) ==
                            SessionStoreIo::ReadStatus::Ok &&
                        size == metadata.pixelBytes
        ? ScreenshotStoreStatus::Valid
        : ScreenshotStoreStatus::IoError;
    result.stage = result.valid() ? CommitStage::Complete
                                  : CommitStage::WritePayloads;
    return result;
}

}  // namespace leshy1::storage
