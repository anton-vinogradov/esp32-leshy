#pragma once

#include <cstddef>
#include <cstdint>

#include "domain/targets/Correlation.h"
#include "domain/targets/TargetCatalog.h"
#include "domain/targets/TargetMerge.h"

namespace leshy1::storage {

constexpr std::uint16_t kTargetCatalogSchemaVersion = 1;
constexpr std::size_t kTargetCatalogMaxBytes = 16384;
constexpr std::size_t kTargetManifestMaxBytes = 128;
constexpr std::uint16_t kTargetStatePreviousSchemaVersion = 2;
constexpr std::uint16_t kTargetStateSchemaVersion = 3;
constexpr std::size_t kTargetStateMaxBytes = 32768;
constexpr std::size_t kTargetStateManifestMaxBytes = 160;

struct TargetManifest final {
    std::uint16_t schemaVersion = 0;
    std::uint16_t targetCount = 0;
    std::uint32_t catalogLength = 0;
    std::uint32_t catalogCrc32c = 0;
};

struct TargetStateManifest final {
    std::uint16_t schemaVersion = 0;
    std::uint16_t targetCount = 0;
    std::uint16_t decisionCount = 0;
    std::uint16_t mergeCount = 0;
    std::uint32_t stateLength = 0;
    std::uint32_t stateCrc32c = 0;
};

enum class TargetCodecStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
    Malformed,
    UnsupportedSchema,
    BoundsExceeded,
    Conflict,
    ChecksumMismatch,
    TrailingData,
};

const char* targetCodecStatusName(TargetCodecStatus status);

TargetCodecStatus encodeTargetCatalog(
    const domain::targets::TargetCatalog& catalog,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
TargetCodecStatus decodeTargetCatalog(
    const std::uint8_t* input, std::size_t size,
    domain::targets::TargetCatalog* output);
TargetCodecStatus encodeTargetManifest(
    const domain::targets::TargetCatalog& catalog,
    const std::uint8_t* catalogBytes, std::size_t catalogSize,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
TargetCodecStatus decodeTargetManifest(
    const std::uint8_t* input, std::size_t size, TargetManifest* output);
TargetCodecStatus reopenTargetCatalog(
    const std::uint8_t* manifestBytes, std::size_t manifestSize,
    const std::uint8_t* catalogBytes, std::size_t catalogSize,
    domain::targets::TargetCatalog* output);

TargetCodecStatus encodeTargetState(
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
TargetCodecStatus decodeTargetState(
    const std::uint8_t* input, std::size_t size,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions,
    domain::targets::TargetMergeHistory* merges);
TargetCodecStatus encodeTargetStateManifest(
    const domain::targets::TargetCatalog& catalog,
    const domain::targets::CorrelationDecisionLog& decisions,
    const domain::targets::TargetMergeHistory& merges,
    const std::uint8_t* stateBytes, std::size_t stateSize,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
TargetCodecStatus decodeTargetStateManifest(
    const std::uint8_t* input, std::size_t size,
    TargetStateManifest* output);
TargetCodecStatus reopenTargetState(
    const std::uint8_t* manifestBytes, std::size_t manifestSize,
    const std::uint8_t* stateBytes, std::size_t stateSize,
    domain::targets::TargetCatalog* catalog,
    domain::targets::CorrelationDecisionLog* decisions,
    domain::targets::TargetMergeHistory* merges);

}  // namespace leshy1::storage
