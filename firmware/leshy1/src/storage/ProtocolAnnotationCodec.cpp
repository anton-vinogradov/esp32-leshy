#include "ProtocolAnnotationCodec.h"

#include <cstring>

#include "AtomicHead.h"

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kMagic[4] = {'L', 'P', 'A', 'N'};
constexpr std::size_t kHeaderBytes = 24U;
constexpr std::size_t kRecordBytes = 5U;
constexpr std::size_t kChecksumBytes = 4U;

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
    for (std::size_t index = 0U; index < 8U; ++index) {
        output[index] = static_cast<std::uint8_t>(
            value >> ((7U - index) * 8U));
    }
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

std::uint64_t get64(const std::uint8_t* input) {
    std::uint64_t value = 0U;
    for (std::size_t index = 0U; index < 8U; ++index) {
        value = (value << 8U) | input[index];
    }
    return value;
}

}  // namespace

const char* protocolAnnotationCodecStatusName(
    ProtocolAnnotationCodecStatus status) {
    switch (status) {
        case ProtocolAnnotationCodecStatus::Valid: return "valid";
        case ProtocolAnnotationCodecStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolAnnotationCodecStatus::BufferTooSmall:
            return "buffer_too_small";
        case ProtocolAnnotationCodecStatus::Malformed: return "malformed";
        case ProtocolAnnotationCodecStatus::UnsupportedSchema:
            return "unsupported_schema";
        case ProtocolAnnotationCodecStatus::BoundsExceeded:
            return "bounds_exceeded";
        case ProtocolAnnotationCodecStatus::ChecksumMismatch:
            return "checksum_mismatch";
        case ProtocolAnnotationCodecStatus::TrailingData:
            return "trailing_data";
    }
    return "invalid_argument";
}

ProtocolAnnotationCodecStatus encodeProtocolAnnotations(
    const apps::protocol::ProtocolAnnotationSet& annotations,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (outputSize != nullptr) *outputSize = 0U;
    if (!annotations.bound() || output == nullptr || outputSize == nullptr) {
        return ProtocolAnnotationCodecStatus::InvalidArgument;
    }
    const std::size_t required = kHeaderBytes +
        annotations.size() * kRecordBytes + kChecksumBytes;
    if (required > capacity || required > kProtocolAnnotationWireMaxBytes) {
        return ProtocolAnnotationCodecStatus::BufferTooSmall;
    }
    std::memset(output, 0, required);
    std::memcpy(output, kMagic, sizeof(kMagic));
    put16(output + 4U, kProtocolAnnotationSchemaVersion);
    output[6U] = static_cast<std::uint8_t>(annotations.size());
    put32(output + 8U, annotations.source().captureGeneration);
    put64(output + 12U, annotations.source().captureFingerprint);
    put16(output + 20U, annotations.source().pulseCount);
    std::size_t position = kHeaderBytes;
    for (std::size_t index = 0U; index < annotations.size(); ++index) {
        const auto* annotation = annotations.get(index);
        if (annotation == nullptr) {
            return ProtocolAnnotationCodecStatus::InvalidArgument;
        }
        output[position] = static_cast<std::uint8_t>(annotation->kind);
        put16(output + position + 1U, annotation->firstPulse);
        put16(output + position + 3U, annotation->lastPulse);
        position += kRecordBytes;
    }
    put32(output + position, crc32c(output, position));
    *outputSize = required;
    return ProtocolAnnotationCodecStatus::Valid;
}

ProtocolAnnotationCodecStatus decodeProtocolAnnotations(
    const std::uint8_t* input, std::size_t size,
    apps::protocol::ProtocolAnnotationSet* output) {
    if (input == nullptr || output == nullptr) {
        return ProtocolAnnotationCodecStatus::InvalidArgument;
    }
    output->clear();
    if (size < kHeaderBytes + kChecksumBytes) {
        return ProtocolAnnotationCodecStatus::Malformed;
    }
    if (std::memcmp(input, kMagic, sizeof(kMagic)) != 0) {
        return ProtocolAnnotationCodecStatus::Malformed;
    }
    if (get16(input + 4U) != kProtocolAnnotationSchemaVersion) {
        return ProtocolAnnotationCodecStatus::UnsupportedSchema;
    }
    if (input[7U] != 0U || get16(input + 22U) != 0U) {
        return ProtocolAnnotationCodecStatus::Malformed;
    }
    const std::size_t count = input[6U];
    if (count > apps::protocol::ProtocolAnnotationSet::kCapacity) {
        return ProtocolAnnotationCodecStatus::BoundsExceeded;
    }
    const std::size_t expected =
        kHeaderBytes + count * kRecordBytes + kChecksumBytes;
    if (size < expected) return ProtocolAnnotationCodecStatus::Malformed;
    if (size > expected) return ProtocolAnnotationCodecStatus::TrailingData;
    if (get32(input + expected - kChecksumBytes) !=
        crc32c(input, expected - kChecksumBytes)) {
        return ProtocolAnnotationCodecStatus::ChecksumMismatch;
    }

    const apps::protocol::ProtocolAnnotationSource source{
        get32(input + 8U), get64(input + 12U), get16(input + 20U)};
    if (output->bind(source) !=
        apps::protocol::ProtocolAnnotationStatus::Valid) {
        output->clear();
        return ProtocolAnnotationCodecStatus::Malformed;
    }
    std::size_t position = kHeaderBytes;
    for (std::size_t index = 0U; index < count; ++index) {
        const std::uint8_t kind = input[position];
        if (kind > static_cast<std::uint8_t>(
                       apps::protocol::ProtocolAnnotationKind::Gap)) {
            output->clear();
            return ProtocolAnnotationCodecStatus::Malformed;
        }
        const apps::protocol::ProtocolAnnotation annotation{
            static_cast<apps::protocol::ProtocolAnnotationKind>(kind),
            get16(input + position + 1U), get16(input + position + 3U)};
        if (output->add(source, annotation) !=
            apps::protocol::ProtocolAnnotationStatus::Valid) {
            output->clear();
            return ProtocolAnnotationCodecStatus::Malformed;
        }
        position += kRecordBytes;
    }
    return ProtocolAnnotationCodecStatus::Valid;
}

}  // namespace leshy1::storage
