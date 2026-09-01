#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/protocol/ProtocolDerivedDecode.h"

namespace leshy1::storage {

constexpr std::uint16_t kProtocolDerivedDecodeSchemaVersion = 1U;
constexpr std::size_t kProtocolDerivedDecodeWireMaxBytes = 228U;

enum class ProtocolDerivedDecodeCodecStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
    Malformed,
    UnsupportedSchema,
    BoundsExceeded,
    ChecksumMismatch,
    TrailingData,
};

const char* protocolDerivedDecodeCodecStatusName(
    ProtocolDerivedDecodeCodecStatus status);

ProtocolDerivedDecodeCodecStatus encodeProtocolDerivedDecode(
    const apps::protocol::ProtocolDerivedDecode& decode,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);

ProtocolDerivedDecodeCodecStatus decodeProtocolDerivedDecode(
    const std::uint8_t* input, std::size_t size,
    apps::protocol::ProtocolDerivedDecode* output);

}  // namespace leshy1::storage
