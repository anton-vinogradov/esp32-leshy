#include "RadiotapPcap.h"

#include <algorithm>
#include <array>
#include <cstring>

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

bool appendWindow(const std::uint8_t* data, std::size_t size,
                  std::size_t requestedOffset, std::size_t requestedSize,
                  std::size_t* streamOffset, std::uint8_t* output,
                  std::size_t* outputSize) {
    if (data == nullptr || streamOffset == nullptr || output == nullptr ||
        outputSize == nullptr) {
        return false;
    }
    const std::size_t segmentStart = *streamOffset;
    const std::size_t segmentEnd = segmentStart + size;
    const std::size_t requestEnd = requestedOffset + requestedSize;
    if (segmentEnd > requestedOffset && segmentStart < requestEnd) {
        const std::size_t copyStart = std::max(segmentStart, requestedOffset);
        const std::size_t copyEnd = std::min(segmentEnd, requestEnd);
        const std::size_t sourceOffset = copyStart - segmentStart;
        const std::size_t copySize = copyEnd - copyStart;
        std::memcpy(output + *outputSize, data + sourceOffset, copySize);
        *outputSize += copySize;
    }
    *streamOffset = segmentEnd;
    return true;
}

void encodeGlobalHeader(std::uint16_t snapLength,
                        std::uint8_t* output) {
    std::memset(output, 0, kGlobalHeaderBytes);
    put32(output, 0xA1B2C3D4U);
    put16(output + 4, 2U);
    put16(output + 6, 4U);
    put32(output + 16, static_cast<std::uint32_t>(
        kRadiotapHeaderBytes + snapLength));
    put32(output + 20, kRadiotapLinkType);
}

void encodeFrameHeaders(const domain::captures::WifiFrameView& frame,
                        std::uint8_t* record, std::uint8_t* radiotap) {
    std::memset(record, 0, kRecordHeaderBytes);
    const std::uint32_t capturedLength = static_cast<std::uint32_t>(
        kRadiotapHeaderBytes + frame.capturedLength);
    const std::uint32_t originalLength = static_cast<std::uint32_t>(
        kRadiotapHeaderBytes + frame.originalLength);
    put32(record, static_cast<std::uint32_t>(frame.monotonicUs / 1000000ULL));
    put32(record + 4, static_cast<std::uint32_t>(
        frame.monotonicUs % 1000000ULL));
    put32(record + 8, capturedLength);
    put32(record + 12, originalLength);

    std::memset(radiotap, 0, kRadiotapHeaderBytes);
    put16(radiotap + 2, kRadiotapHeaderBytes);
    put32(radiotap + 4, (1U << 1U) | (1U << 3U) | (1U << 5U));
    radiotap[8] = frame.fcsIncluded ? 0x10U : 0U;
    put16(radiotap + 10, channelFrequencyMhz(frame.channel));
    put16(radiotap + 12, 0x0080U);
    radiotap[14] = static_cast<std::uint8_t>(frame.rssiDbm);
}

}  // namespace

PcapStreamChunk readRadiotapPcapChunk(
    const domain::captures::WifiFrameSource& source, std::size_t offset,
    std::uint8_t* output, std::size_t capacity) {
    PcapStreamChunk result{};
    result.offset = offset;
    if (output == nullptr || capacity == 0U ||
        capacity > kRadiotapPcapChunkCapacity || source.snapLength() == 0U) {
        return result;
    }
    const std::size_t frameCount = source.frameCount();
    result.frameCount = frameCount;
    result.availableBytes = kGlobalHeaderBytes;
    for (std::size_t index = 0; index < frameCount; ++index) {
        domain::captures::WifiFrameView frame{};
        if (!source.frameView(index, &frame) || frame.payload == nullptr ||
            frame.capturedLength > source.snapLength()) {
            return result;
        }
        result.availableBytes += kRecordHeaderBytes + kRadiotapHeaderBytes +
            frame.capturedLength;
    }
    if (offset > result.availableBytes) return result;

    const std::size_t requestedSize = std::min(
        capacity, result.availableBytes - offset);
    std::array<std::uint8_t, kRadiotapPcapChunkCapacity> scratch{};
    std::array<std::uint8_t, kGlobalHeaderBytes> global{};
    encodeGlobalHeader(source.snapLength(), global.data());
    std::size_t streamOffset = 0;
    std::size_t outputSize = 0;
    if (!appendWindow(global.data(), global.size(), offset, requestedSize,
                      &streamOffset, scratch.data(), &outputSize)) {
        return result;
    }
    for (std::size_t index = 0;
         index < frameCount && outputSize < requestedSize; ++index) {
        domain::captures::WifiFrameView frame{};
        if (!source.frameView(index, &frame) || frame.payload == nullptr) {
            return result;
        }
        std::array<std::uint8_t, kRecordHeaderBytes> record{};
        std::array<std::uint8_t, kRadiotapHeaderBytes> radiotap{};
        encodeFrameHeaders(frame, record.data(), radiotap.data());
        if (!appendWindow(record.data(), record.size(), offset, requestedSize,
                          &streamOffset, scratch.data(), &outputSize) ||
            !appendWindow(radiotap.data(), radiotap.size(), offset,
                          requestedSize, &streamOffset, scratch.data(),
                          &outputSize) ||
            !appendWindow(frame.payload, frame.capturedLength, offset,
                          requestedSize, &streamOffset, scratch.data(),
                          &outputSize)) {
            return result;
        }
    }
    if (outputSize != requestedSize) return result;
    if (outputSize != 0U) std::memcpy(output, scratch.data(), outputSize);
    result.bytesRead = outputSize;
    result.valid = true;
    return result;
}

std::size_t radiotapPcapSize(
    const domain::captures::WifiFrameSource& source) {
    std::size_t bytes = kGlobalHeaderBytes;
    for (std::size_t index = 0; index < source.frameCount(); ++index) {
        domain::captures::WifiFrameView frame;
        if (!source.frameView(index, &frame) || frame.payload == nullptr) return 0;
        bytes += kRecordHeaderBytes + kRadiotapHeaderBytes +
                 frame.capturedLength;
    }
    return bytes;
}

PcapExportResult writeRadiotapPcap(
    const domain::captures::WifiFrameSource& source,
    PcapByteSink sink, void* context) {
    PcapExportResult result;
    if (sink == nullptr || source.frameCount() == 0U ||
        source.snapLength() == 0U) return result;

    std::array<std::uint8_t, kGlobalHeaderBytes> global{};
    encodeGlobalHeader(source.snapLength(), global.data());
    if (!emit(sink, context, global.data(), global.size(), &result)) {
        return result;
    }

    for (std::size_t index = 0; index < source.frameCount(); ++index) {
        domain::captures::WifiFrameView frame;
        if (!source.frameView(index, &frame) || frame.payload == nullptr) {
            return result;
        }
        std::array<std::uint8_t, kRecordHeaderBytes> record{};
        std::array<std::uint8_t, kRadiotapHeaderBytes> radiotap{};
        encodeFrameHeaders(frame, record.data(), radiotap.data());
        if (!emit(sink, context, record.data(), record.size(), &result)) {
            return result;
        }
        if (!emit(sink, context, radiotap.data(), radiotap.size(), &result) ||
            !emit(sink, context, frame.payload, frame.capturedLength,
                  &result)) {
            return result;
        }
        ++result.framesWritten;
    }
    result.valid = result.framesWritten == source.frameCount() &&
                   result.bytesWritten == radiotapPcapSize(source);
    return result;
}

std::size_t radiotapPcapSize(const WifiFrameCapture& capture) {
    if (capture.stats().state != WifiFrameCaptureState::Complete) return 0;
    return radiotapPcapSize(
        static_cast<const domain::captures::WifiFrameSource&>(capture));
}

PcapExportResult writeRadiotapPcap(const WifiFrameCapture& capture,
                                   PcapByteSink sink, void* context) {
    if (capture.stats().state != WifiFrameCaptureState::Complete) return {};
    return writeRadiotapPcap(
        static_cast<const domain::captures::WifiFrameSource&>(capture),
        sink, context);
}

}  // namespace leshy1::apps::capture
