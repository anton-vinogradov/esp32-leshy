#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/protocol/ProtocolAnnotations.h"

namespace leshy1::storage {

constexpr std::uint16_t kProtocolAnnotationSchemaVersion = 1U;
constexpr std::size_t kProtocolAnnotationWireMaxBytes = 88U;

enum class ProtocolAnnotationCodecStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
    Malformed,
    UnsupportedSchema,
    BoundsExceeded,
    ChecksumMismatch,
    TrailingData,
};

const char* protocolAnnotationCodecStatusName(
    ProtocolAnnotationCodecStatus status);

ProtocolAnnotationCodecStatus encodeProtocolAnnotations(
    const apps::protocol::ProtocolAnnotationSet& annotations,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);

ProtocolAnnotationCodecStatus decodeProtocolAnnotations(
    const std::uint8_t* input, std::size_t size,
    apps::protocol::ProtocolAnnotationSet* output);

}  // namespace leshy1::storage
