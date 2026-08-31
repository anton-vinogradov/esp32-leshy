#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "AtomicHead.h"
#include "SessionStore.h"

namespace leshy1::storage {

constexpr std::uint16_t kScreenshotWidth = 240U;
constexpr std::uint16_t kScreenshotHeight = 320U;
constexpr std::uint32_t kScreenshotPixelBytes =
    static_cast<std::uint32_t>(kScreenshotWidth) * kScreenshotHeight * 2U;
constexpr std::size_t kScreenshotManifestBytes = 128U;
constexpr std::size_t kScreenshotBuildVersionBytes = 24U;

enum class ScreenshotPixelFormat : std::uint8_t {
    Rgb565BigEndian = 1U,
};

struct ScreenshotMetadata final {
    std::uint32_t generation = 0U;
    std::uint16_t width = kScreenshotWidth;
    std::uint16_t height = kScreenshotHeight;
    std::uint32_t pixelBytes = kScreenshotPixelBytes;
    std::uint32_t pixelCrc32c = 0U;
    std::uint64_t capturedUs = 0U;
    std::uint32_t uiRevision = 0U;
    std::uint8_t uiPage = 0U;
    ScreenshotPixelFormat format = ScreenshotPixelFormat::Rgb565BigEndian;
    std::array<char, kScreenshotBuildVersionBytes> buildVersion{};
    std::array<std::uint8_t, 32U> appElfSha256{};
};

enum class ScreenshotFileKind : std::uint8_t {
    Pixels,
    Manifest,
    HeadA,
    HeadB,
};

enum class ScreenshotStoreStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    EncodeFailed,
    PathError,
    IoError,
    SyncError,
    Empty,
    Conflict,
    CorruptGeneration,
};

const char* screenshotStoreStatusName(ScreenshotStoreStatus status);
bool formatScreenshotStorePath(ScreenshotFileKind kind,
                               std::uint32_t generation, char* output,
                               std::size_t capacity);
bool encodeScreenshotManifest(
    const ScreenshotMetadata& metadata,
    std::array<std::uint8_t, kScreenshotManifestBytes>* output);
bool decodeScreenshotManifest(const std::uint8_t* input, std::size_t size,
                              ScreenshotMetadata* output);
bool formatScreenshotJsonSummary(const ScreenshotMetadata& metadata,
                                 char* output, std::size_t capacity);

using ScreenshotSource = bool (*)(std::size_t offset, std::uint8_t* output,
                                  std::size_t size, void* context);
using ScreenshotSink = bool (*)(std::size_t offset, const std::uint8_t* input,
                                std::size_t size, void* context);

class ScreenshotStoreIo : public SessionStoreIo {
public:
    virtual bool writeStreamFile(const char* path, std::size_t size,
                                 ScreenshotSource source,
                                 void* context) = 0;
    virtual ReadStatus readStreamFile(const char* path, ScreenshotSink sink,
                                      void* context,
                                      std::size_t* outputSize) = 0;
};

struct ScreenshotStoreWorkspace final {
    std::array<std::uint8_t, kScreenshotManifestBytes> manifest{};
    std::array<std::uint8_t, kHeadWireSize> headA{};
    std::array<std::uint8_t, kHeadWireSize> headB{};
    ScreenshotMetadata metadata{};
};

struct ScreenshotStoreResult final {
    ScreenshotStoreStatus status = ScreenshotStoreStatus::InvalidArgument;
    CommitStage stage = CommitStage::WritePayloads;
    std::uint32_t generation = 0U;
    HeadSlot publishedSlot = HeadSlot::A;

    bool valid() const { return status == ScreenshotStoreStatus::Valid; }
};

ScreenshotStoreResult commitScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    const ScreenshotMetadata& metadata, ScreenshotSource source,
    void* sourceContext, std::uint32_t generation, HeadSlot publishSlot);
ScreenshotStoreResult commitNextScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    const ScreenshotMetadata& metadata, ScreenshotSource source,
    void* sourceContext);
ScreenshotStoreResult recoverScreenshot(
    ScreenshotStoreIo& io, ScreenshotStoreWorkspace& workspace,
    ScreenshotMetadata* output);
ScreenshotStoreResult streamScreenshotPixels(
    ScreenshotStoreIo& io, const ScreenshotMetadata& metadata,
    ScreenshotSink sink, void* sinkContext);

}  // namespace leshy1::storage
