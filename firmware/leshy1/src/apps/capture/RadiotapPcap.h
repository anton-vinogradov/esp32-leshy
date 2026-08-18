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

std::size_t radiotapPcapSize(const WifiFrameCapture& capture);
PcapExportResult writeRadiotapPcap(const WifiFrameCapture& capture,
                                   PcapByteSink sink, void* context);

}  // namespace leshy1::apps::capture
