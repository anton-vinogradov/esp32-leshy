#include "ProtocolDerivedDecodeCodec.h"

#include <cstring>

#include "AtomicHead.h"

namespace leshy1::storage {
namespace {

constexpr std::uint8_t kMagic[4] = {'L', 'P', 'D', 'D'};
constexpr std::size_t kHeaderBytes = 32U;
constexpr std::size_t kRecordBytes = 16U;
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

bool isValueKind(apps::protocol::ProtocolAnnotationKind kind) {
    return kind == apps::protocol::ProtocolAnnotationKind::Address ||
        kind == apps::protocol::ProtocolAnnotationKind::Command ||
        kind == apps::protocol::ProtocolAnnotationKind::Data ||
        kind == apps::protocol::ProtocolAnnotationKind::Checksum;
}

bool fieldValid(const apps::protocol::ProtocolDerivedField& field,
                std::uint16_t pulseCount) {
    using apps::protocol::ProtocolDerivedFieldStatus;
    if (static_cast<std::uint8_t>(field.kind) >
            static_cast<std::uint8_t>(
                apps::protocol::ProtocolAnnotationKind::Gap) ||
        static_cast<std::uint8_t>(field.status) >
            static_cast<std::uint8_t>(ProtocolDerivedFieldStatus::Inconclusive) ||
        field.firstPulse > field.lastPulse || field.lastPulse >= pulseCount ||
        field.durationUs == 0U) {
        return false;
    }
    if (field.status == ProtocolDerivedFieldStatus::BitsObserved) {
        if (!isValueKind(field.kind) || field.bitCount == 0U ||
            field.bitCount > 32U) {
            return false;
        }
        return field.bitCount == 32U ||
            (field.observedBits >> field.bitCount) == 0U;
    }
    if (field.bitCount != 0U || field.observedBits != 0U) return false;
    return field.status == ProtocolDerivedFieldStatus::Inconclusive
        ? isValueKind(field.kind) : !isValueKind(field.kind);
}

bool decodeValid(const apps::protocol::ProtocolDerivedDecode& decode) {
    using apps::protocol::ProtocolDerivedDecodeOutcome;
    using apps::protocol::ProtocolDerivedDecodeStatus;
    using apps::protocol::ProtocolDerivedFieldStatus;
    if (decode.status != ProtocolDerivedDecodeStatus::Valid ||
        !decode.source.valid() || decode.annotationStoreGeneration == 0U ||
        decode.decoderVersion !=
            apps::protocol::ProtocolDerivedDecode::kDecoderVersion ||
        decode.fieldCount == 0U || decode.fieldCount > decode.fields.size() ||
        decode.source.pulseCount >
            apps::protocol::ProtocolWorkbenchWorkspace::kMaximumPulses) {
        return false;
    }
    std::uint16_t observed = 0U;
    std::uint16_t inconclusive = 0U;
    std::uint16_t previousLastPulse = 0U;
    for (std::size_t index = 0U; index < decode.fieldCount; ++index) {
        const auto& field = decode.fields[index];
        if (!fieldValid(field, decode.source.pulseCount) ||
            (index != 0U && field.firstPulse <= previousLastPulse)) {
            return false;
        }
        previousLastPulse = field.lastPulse;
        if (field.status == ProtocolDerivedFieldStatus::BitsObserved) {
            ++observed;
        } else if (field.status == ProtocolDerivedFieldStatus::Inconclusive) {
            ++inconclusive;
        }
    }
    const auto expectedOutcome = inconclusive == 0U
        ? ProtocolDerivedDecodeOutcome::Complete
        : ProtocolDerivedDecodeOutcome::Partial;
    return decode.observedBitFields == observed &&
        decode.inconclusiveFields == inconclusive &&
        decode.outcome == expectedOutcome;
}

}  // namespace

const char* protocolDerivedDecodeCodecStatusName(
    ProtocolDerivedDecodeCodecStatus status) {
    switch (status) {
        case ProtocolDerivedDecodeCodecStatus::Valid: return "valid";
        case ProtocolDerivedDecodeCodecStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolDerivedDecodeCodecStatus::BufferTooSmall:
            return "buffer_too_small";
        case ProtocolDerivedDecodeCodecStatus::Malformed: return "malformed";
        case ProtocolDerivedDecodeCodecStatus::UnsupportedSchema:
            return "unsupported_schema";
        case ProtocolDerivedDecodeCodecStatus::BoundsExceeded:
            return "bounds_exceeded";
        case ProtocolDerivedDecodeCodecStatus::ChecksumMismatch:
            return "checksum_mismatch";
        case ProtocolDerivedDecodeCodecStatus::TrailingData:
            return "trailing_data";
    }
    return "invalid_argument";
}

ProtocolDerivedDecodeCodecStatus encodeProtocolDerivedDecode(
    const apps::protocol::ProtocolDerivedDecode& decode,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (outputSize != nullptr) *outputSize = 0U;
    if (output == nullptr || outputSize == nullptr || !decodeValid(decode)) {
        return ProtocolDerivedDecodeCodecStatus::InvalidArgument;
    }
    const std::size_t required = kHeaderBytes +
        decode.fieldCount * kRecordBytes + kChecksumBytes;
    if (required > capacity || required > kProtocolDerivedDecodeWireMaxBytes) {
        return ProtocolDerivedDecodeCodecStatus::BufferTooSmall;
    }
    std::memset(output, 0, required);
    std::memcpy(output, kMagic, sizeof(kMagic));
    put16(output + 4U, kProtocolDerivedDecodeSchemaVersion);
    output[6U] = static_cast<std::uint8_t>(decode.fieldCount);
    output[7U] = static_cast<std::uint8_t>(decode.outcome);
    put32(output + 8U, decode.source.captureGeneration);
    put64(output + 12U, decode.source.captureFingerprint);
    put16(output + 20U, decode.source.pulseCount);
    put16(output + 22U, decode.decoderVersion);
    put32(output + 24U, decode.annotationStoreGeneration);
    put16(output + 28U, decode.observedBitFields);
    put16(output + 30U, decode.inconclusiveFields);
    std::size_t position = kHeaderBytes;
    for (std::size_t index = 0U; index < decode.fieldCount; ++index) {
        const auto& field = decode.fields[index];
        output[position] = static_cast<std::uint8_t>(field.kind);
        output[position + 1U] = static_cast<std::uint8_t>(field.status);
        put16(output + position + 2U, field.firstPulse);
        put16(output + position + 4U, field.lastPulse);
        put16(output + position + 6U, field.bitCount);
        put32(output + position + 8U, field.observedBits);
        put32(output + position + 12U, field.durationUs);
        position += kRecordBytes;
    }
    put32(output + position, crc32c(output, position));
    *outputSize = required;
    return ProtocolDerivedDecodeCodecStatus::Valid;
}

ProtocolDerivedDecodeCodecStatus decodeProtocolDerivedDecode(
    const std::uint8_t* input, std::size_t size,
    apps::protocol::ProtocolDerivedDecode* output) {
    if (input == nullptr || output == nullptr) {
        return ProtocolDerivedDecodeCodecStatus::InvalidArgument;
    }
    *output = {};
    if (size < kHeaderBytes + kChecksumBytes ||
        std::memcmp(input, kMagic, sizeof(kMagic)) != 0) {
        return ProtocolDerivedDecodeCodecStatus::Malformed;
    }
    if (get16(input + 4U) != kProtocolDerivedDecodeSchemaVersion) {
        return ProtocolDerivedDecodeCodecStatus::UnsupportedSchema;
    }
    const std::size_t count = input[6U];
    if (count > apps::protocol::ProtocolDerivedDecode::kMaximumFields) {
        return ProtocolDerivedDecodeCodecStatus::BoundsExceeded;
    }
    const std::size_t expected =
        kHeaderBytes + count * kRecordBytes + kChecksumBytes;
    if (size < expected) return ProtocolDerivedDecodeCodecStatus::Malformed;
    if (size > expected) return ProtocolDerivedDecodeCodecStatus::TrailingData;
    if (get32(input + expected - kChecksumBytes) !=
        crc32c(input, expected - kChecksumBytes)) {
        return ProtocolDerivedDecodeCodecStatus::ChecksumMismatch;
    }
    if (input[7U] > static_cast<std::uint8_t>(
                         apps::protocol::ProtocolDerivedDecodeOutcome::Partial)) {
        return ProtocolDerivedDecodeCodecStatus::Malformed;
    }
    output->status = apps::protocol::ProtocolDerivedDecodeStatus::Valid;
    output->outcome = static_cast<apps::protocol::ProtocolDerivedDecodeOutcome>(
        input[7U]);
    output->source = {get32(input + 8U), get64(input + 12U),
                      get16(input + 20U)};
    output->decoderVersion = get16(input + 22U);
    output->annotationStoreGeneration = get32(input + 24U);
    output->observedBitFields = get16(input + 28U);
    output->inconclusiveFields = get16(input + 30U);
    output->fieldCount = count;
    std::size_t position = kHeaderBytes;
    for (std::size_t index = 0U; index < count; ++index) {
        const std::uint8_t kind = input[position];
        const std::uint8_t status = input[position + 1U];
        if (kind > static_cast<std::uint8_t>(
                       apps::protocol::ProtocolAnnotationKind::Gap) ||
            status > static_cast<std::uint8_t>(
                         apps::protocol::ProtocolDerivedFieldStatus::Inconclusive)) {
            *output = {};
            return ProtocolDerivedDecodeCodecStatus::Malformed;
        }
        output->fields[index] = {
            static_cast<apps::protocol::ProtocolAnnotationKind>(kind),
            static_cast<apps::protocol::ProtocolDerivedFieldStatus>(status),
            get16(input + position + 2U), get16(input + position + 4U),
            get16(input + position + 6U), get32(input + position + 8U),
            get32(input + position + 12U)};
        position += kRecordBytes;
    }
    if (!decodeValid(*output)) {
        *output = {};
        return ProtocolDerivedDecodeCodecStatus::Malformed;
    }
    return ProtocolDerivedDecodeCodecStatus::Valid;
}

}  // namespace leshy1::storage
