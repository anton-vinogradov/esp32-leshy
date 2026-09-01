#pragma once

#include <cstddef>
#include <cstdint>

#include "WifiFrameCapture.h"

namespace leshy1::apps::capture {

using PcapByteSink = bool (*)(const std::uint8_t* data, std::size_t size,
                              void* context);

struct PcapExportResult final {
    bool valid = false;
    std::size_t bytesWritten = 0;
    std::size_t framesWritten = 0;
};

constexpr std::size_t kRadiotapPcapChunkCapacity = 80;

// One immutable-size view over a possibly growing capture. The function
// snapshots frameCount once, validates every visible frame, and returns the
// requested PCAP byte window without allocating the complete file. This lets
// read-only USB clients follow a live capture while preserving exact offsets.
struct PcapStreamChunk final {
    bool valid = false;
    std::size_t offset = 0;
    std::size_t availableBytes = 0;
    std::size_t bytesRead = 0;
    std::size_t frameCount = 0;
};

PcapStreamChunk readRadiotapPcapChunk(
    const domain::captures::WifiFrameSource& source, std::size_t offset,
    std::uint8_t* output, std::size_t capacity);

std::size_t radiotapPcapSize(const domain::captures::WifiFrameSource& source);
PcapExportResult writeRadiotapPcap(
    const domain::captures::WifiFrameSource& source,
    PcapByteSink sink, void* context);
std::size_t radiotapPcapSize(const WifiFrameCapture& capture);
PcapExportResult writeRadiotapPcap(const WifiFrameCapture& capture,
                                   PcapByteSink sink, void* context);

}  // namespace leshy1::apps::capture
