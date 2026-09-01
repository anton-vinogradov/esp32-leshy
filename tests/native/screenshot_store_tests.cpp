#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "storage/ScreenshotStore.h"

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::cerr << "CHECK failed at " << __FILE__ << ':' << __LINE__  \
                      << ": " #condition << '\n';                          \
            std::exit(1);                                                    \
        }                                                                    \
    } while (false)

namespace {

using namespace leshy1::storage;

class MemoryScreenshotIo final : public ScreenshotStoreIo {
public:
    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override {
        if (path == nullptr || data == nullptr || size == 0U) return false;
        files_[path] = std::vector<std::uint8_t>(data, data + size);
        pending_ = path;
        return true;
    }

    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override {
        if (path == nullptr || output == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        const auto found = files_.find(path);
        if (found == files_.end()) return ReadStatus::NotFound;
        if (found->second.size() > capacity) return ReadStatus::TooLarge;
        std::memcpy(output, found->second.data(), found->second.size());
        *outputSize = found->second.size();
        return ReadStatus::Ok;
    }

    bool writeStreamFile(const char* path, std::size_t size,
                         ScreenshotSource source,
                         void* context) override {
        if (path == nullptr || source == nullptr || size == 0U) return false;
        std::vector<std::uint8_t> bytes(size);
        for (std::size_t offset = 0U; offset < size;) {
            const std::size_t chunk =
                size - offset < 256U ? size - offset : 256U;
            if (!source(offset, bytes.data() + offset, chunk, context)) {
                return false;
            }
            offset += chunk;
        }
        files_[path] = std::move(bytes);
        pending_ = path;
        return true;
    }

    ReadStatus readStreamFile(const char* path, ScreenshotSink sink,
                              void* context,
                              std::size_t* outputSize) override {
        if (path == nullptr || sink == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        const auto found = files_.find(path);
        if (found == files_.end()) return ReadStatus::NotFound;
        ++streamReadCalls_;
        streamReadBytes_ += found->second.size();
        for (std::size_t offset = 0U; offset < found->second.size();) {
            const std::size_t chunk = found->second.size() - offset < 256U
                ? found->second.size() - offset : 256U;
            if (!sink(offset, found->second.data() + offset, chunk, context)) {
                return ReadStatus::IoError;
            }
            offset += chunk;
        }
        *outputSize = found->second.size();
        return ReadStatus::Ok;
    }

    bool syncFile(const char* path) override {
        if (path == nullptr || pending_ != path) return false;
        if (!failSyncPath_.empty() && failSyncPath_ == path) {
            failSyncPath_.clear();
            return false;
        }
        pending_.clear();
        return true;
    }

    bool syncDirectory() override { return true; }

    void failNextSync(const char* path) { failSyncPath_ = path; }

    void resetStreamReadStats() {
        streamReadCalls_ = 0U;
        streamReadBytes_ = 0U;
    }

    std::size_t streamReadCalls() const { return streamReadCalls_; }
    std::size_t streamReadBytes() const { return streamReadBytes_; }

    void flip(const char* path, std::size_t offset) {
        auto& bytes = files_.at(path);
        CHECK(offset < bytes.size());
        bytes[offset] ^= 0x5aU;
    }

private:
    std::map<std::string, std::vector<std::uint8_t>> files_{};
    std::string pending_{};
    std::string failSyncPath_{};
    std::size_t streamReadCalls_ = 0U;
    std::size_t streamReadBytes_ = 0U;
};

bool vectorSource(std::size_t offset, std::uint8_t* output,
                  std::size_t size, void* context) {
    if (context == nullptr || output == nullptr) return false;
    const auto* bytes = static_cast<const std::vector<std::uint8_t>*>(context);
    if (offset > bytes->size() || size > bytes->size() - offset) return false;
    std::memcpy(output, bytes->data() + offset, size);
    return true;
}

bool vectorSink(std::size_t offset, const std::uint8_t* input,
                std::size_t size, void* context) {
    if (context == nullptr || input == nullptr) return false;
    auto* bytes = static_cast<std::vector<std::uint8_t>*>(context);
    if (offset != bytes->size()) return false;
    bytes->insert(bytes->end(), input, input + size);
    return true;
}

ScreenshotMetadata metadataFor(const std::vector<std::uint8_t>& pixels,
                               std::uint64_t capturedUs,
                               std::uint32_t revision) {
    ScreenshotMetadata metadata{};
    metadata.pixelCrc32c = crc32c(pixels.data(), pixels.size());
    metadata.capturedUs = capturedUs;
    metadata.uiRevision = revision;
    metadata.uiPage = 2U;
    std::snprintf(metadata.buildVersion.data(), metadata.buildVersion.size(),
                  "1.0.0-dev.329");
    for (std::size_t index = 0U; index < metadata.appElfSha256.size(); ++index) {
        metadata.appElfSha256[index] = static_cast<std::uint8_t>(index + 1U);
    }
    return metadata;
}

void testManifestRoundTrip() {
    std::vector<std::uint8_t> pixels(kScreenshotPixelBytes, 0x2aU);
    ScreenshotMetadata source = metadataFor(pixels, 1234567U, 42U);
    source.generation = 9U;
    std::array<std::uint8_t, kScreenshotManifestBytes> wire{};
    CHECK(encodeScreenshotManifest(source, &wire));
    ScreenshotMetadata decoded{};
    CHECK(decodeScreenshotManifest(wire.data(), wire.size(), &decoded));
    CHECK(decoded.generation == 9U);
    CHECK(decoded.pixelCrc32c == source.pixelCrc32c);
    CHECK(decoded.capturedUs == 1234567U);
    CHECK(decoded.uiRevision == 42U);
    CHECK(std::strcmp(decoded.buildVersion.data(), "1.0.0-dev.329") == 0);
    wire[70] ^= 1U;
    CHECK(!decodeScreenshotManifest(wire.data(), wire.size(), &decoded));
}

void testAtomicCommitRecoveryAndStreaming() {
    MemoryScreenshotIo io;
    ScreenshotStoreWorkspace workspace{};
    std::vector<std::uint8_t> first(kScreenshotPixelBytes);
    for (std::size_t index = 0U; index < first.size(); ++index) {
        first[index] = static_cast<std::uint8_t>(index * 17U + 3U);
    }
    const ScreenshotMetadata firstMetadata = metadataFor(first, 1000U, 3U);
    const ScreenshotStoreResult firstCommit = commitNextScreenshot(
        io, workspace, firstMetadata, vectorSource, &first);
    CHECK(firstCommit.valid());
    CHECK(firstCommit.generation == 1U);
    CHECK(firstCommit.publishedSlot == HeadSlot::A);

    ScreenshotMetadata recovered{};
    CHECK(recoverScreenshot(io, workspace, &recovered).valid());
    CHECK(recovered.generation == 1U);
    std::vector<std::uint8_t> exported;
    CHECK(streamScreenshotPixels(io, recovered, vectorSink, &exported).valid());
    CHECK(exported == first);

    char summary[384] = {};
    CHECK(formatScreenshotJsonSummary(recovered, summary, sizeof(summary)));
    CHECK(std::strstr(summary, "\"generation\":1") != nullptr);
    CHECK(std::strstr(summary, "\"format\":\"rgb565be\"") != nullptr);

    std::vector<std::uint8_t> second(kScreenshotPixelBytes, 0x7cU);
    const ScreenshotMetadata secondMetadata = metadataFor(second, 2000U, 8U);
    CHECK(commitNextScreenshot(io, workspace, secondMetadata,
                               vectorSource, &second).valid());
    io.resetStreamReadStats();
    CHECK(recoverScreenshot(io, workspace, &recovered).valid());
    CHECK(recovered.generation == 2U);
    CHECK(io.streamReadCalls() == 1U);
    CHECK(io.streamReadBytes() == kScreenshotPixelBytes);

    io.flip("screenshot-00000002.rgb565", 700U);
    io.resetStreamReadStats();
    const ScreenshotStoreResult fallback = recoverScreenshot(
        io, workspace, &recovered);
    CHECK(fallback.valid());
    CHECK(fallback.generation == 1U);
    CHECK(io.streamReadCalls() == 2U);
    CHECK(io.streamReadBytes() == kScreenshotPixelBytes * 2U);
}

void testPowerCutBeforeHeadPreservesPublishedGeneration() {
    MemoryScreenshotIo io;
    ScreenshotStoreWorkspace workspace{};
    std::vector<std::uint8_t> first(kScreenshotPixelBytes, 0x11U);
    const ScreenshotMetadata firstMetadata = metadataFor(first, 100U, 1U);
    CHECK(commitNextScreenshot(io, workspace, firstMetadata,
                               vectorSource, &first).valid());

    std::vector<std::uint8_t> second(kScreenshotPixelBytes, 0x22U);
    const ScreenshotMetadata secondMetadata = metadataFor(second, 200U, 2U);
    io.failNextSync("screenshot-00000002.bin");
    const ScreenshotStoreResult interrupted = commitNextScreenshot(
        io, workspace, secondMetadata, vectorSource, &second);
    CHECK(!interrupted.valid());
    CHECK(interrupted.stage == CommitStage::SyncManifest);

    ScreenshotMetadata recovered{};
    const ScreenshotStoreResult result = recoverScreenshot(
        io, workspace, &recovered);
    CHECK(result.valid());
    CHECK(recovered.generation == 1U);
}

}  // namespace

int main() {
    testManifestRoundTrip();
    testAtomicCommitRecoveryAndStreaming();
    testPowerCutBeforeHeadPreservesPublishedGeneration();
    std::cout << "screenshot store tests passed\n";
    return 0;
}
