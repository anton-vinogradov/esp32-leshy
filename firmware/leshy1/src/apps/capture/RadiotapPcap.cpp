#include "RadiotapPcap.h"

#include <array>

namespace leshy1::apps::capture {
namespace {

constexpr std::size_t kGlobalHeaderBytes = 24;
constexpr std::size_t kRecordHeaderBytes = 16;
constexpr std::size_t kRadiotapHeaderBytes = 15;
constexpr std::uint32_t kRadiotapLinkType = 127;

void put16(std::uint8_t* output, std::uint16_t value) {
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
}

void put32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value);
    output[1] = static_cast<std::uint8_t>(value >> 8U);
    output[2] = static_cast<std::uint8_t>(value >> 16U);
    output[3] = static_cast<std::uint8_t>(value >> 24U);
}

std::uint16_t channelFrequencyMhz(std::uint8_t channel) {
    if (channel == 14U) return 2484U;
    return static_cast<std::uint16_t>(2407U + 5U * channel);
}

bool emit(PcapByteSink sink, void* context, const std::uint8_t* data,
          std::size_t size, PcapExportResult* result) {
    if (!sink(data, size, context)) return false;
    result->bytesWritten += size;
    return true;
}

}  // namespace

std::size_t radiotapPcapSize(const WifiFrameCapture& capture) {
    if (capture.stats().state != WifiFrameCaptureState::Complete) return 0;
    std::size_t bytes = kGlobalHeaderBytes;
    for (std::size_t index = 0; index < capture.size(); ++index) {
        const WifiFrame* frame = capture.frame(index);
        if (frame == nullptr) return 0;
        bytes += kRecordHeaderBytes + kRadiotapHeaderBytes +
                 frame->capturedLength;
    }
    return bytes;
}

PcapExportResult writeRadiotapPcap(const WifiFrameCapture& capture,
                                   PcapByteSink sink, void* context) {
    PcapExportResult result;
    if (sink == nullptr ||
        capture.stats().state != WifiFrameCaptureState::Complete) {
        return result;
    }

    std::array<std::uint8_t, kGlobalHeaderBytes> global{};
    put32(global.data(), 0xA1B2C3D4U);
    put16(global.data() + 4, 2U);
    put16(global.data() + 6, 4U);
    put32(global.data() + 16, static_cast<std::uint32_t>(
        kRadiotapHeaderBytes + capture.plan().snapLength));
    put32(global.data() + 20, kRadiotapLinkType);
    if (!emit(sink, context, global.data(), global.size(), &result)) {
        return result;
    }

    for (std::size_t index = 0; index < capture.size(); ++index) {
        const WifiFrame* frame = capture.frame(index);
        if (frame == nullptr) return result;
        const std::uint32_t capturedLength = static_cast<std::uint32_t>(
            kRadiotapHeaderBytes + frame->capturedLength);
        const std::uint32_t originalLength = static_cast<std::uint32_t>(
            kRadiotapHeaderBytes + frame->originalLength);

        std::array<std::uint8_t, kRecordHeaderBytes> record{};
        put32(record.data(), static_cast<std::uint32_t>(frame->monotonicUs /
                                                        1000000ULL));
        put32(record.data() + 4, static_cast<std::uint32_t>(
            frame->monotonicUs % 1000000ULL));
        put32(record.data() + 8, capturedLength);
        put32(record.data() + 12, originalLength);
        if (!emit(sink, context, record.data(), record.size(), &result)) {
            return result;
        }

        std::array<std::uint8_t, kRadiotapHeaderBytes> radiotap{};
        put16(radiotap.data() + 2, kRadiotapHeaderBytes);
        // FLAGS + CHANNEL + DBM_ANTSIGNAL. Channel begins at an aligned offset.
        put32(radiotap.data() + 4, (1U << 1U) | (1U << 3U) | (1U << 5U));
        radiotap[8] = frame->fcsIncluded ? 0x10U : 0U;
        put16(radiotap.data() + 10, channelFrequencyMhz(frame->channel));
        put16(radiotap.data() + 12, 0x0080U);  // 2 GHz channel.
        radiotap[14] = static_cast<std::uint8_t>(frame->rssiDbm);
        if (!emit(sink, context, radiotap.data(), radiotap.size(), &result) ||
            !emit(sink, context, frame->payload.data(), frame->capturedLength,
                  &result)) {
            return result;
        }
        ++result.framesWritten;
    }
    result.valid = result.framesWritten == capture.size() &&
                   result.bytesWritten == radiotapPcapSize(capture);
    return result;
}

}  // namespace leshy1::apps::capture
