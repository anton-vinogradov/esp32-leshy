#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "ProtocolAnnotations.h"
#include "ProtocolWorkbench.h"

namespace leshy1::apps::protocol {

enum class ProtocolDerivedDecodeStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SourceMismatch,
    SourceReadFailed,
};

enum class ProtocolDerivedFieldStatus : std::uint8_t {
    DurationOnly,
    BitsObserved,
    Inconclusive,
};

enum class ProtocolDerivedDecodeOutcome : std::uint8_t {
    Complete,
    Partial,
};

const char* protocolDerivedDecodeStatusName(ProtocolDerivedDecodeStatus status);
const char* protocolDerivedFieldStatusName(ProtocolDerivedFieldStatus status);
const char* protocolDerivedDecodeOutcomeName(ProtocolDerivedDecodeOutcome outcome);

struct ProtocolDerivedField final {
    ProtocolAnnotationKind kind = ProtocolAnnotationKind::Data;
    ProtocolDerivedFieldStatus status =
        ProtocolDerivedFieldStatus::Inconclusive;
    std::uint16_t firstPulse = 0U;
    std::uint16_t lastPulse = 0U;
    std::uint16_t bitCount = 0U;
    // Bit zero is the first bit observed on air. No byte order is invented.
    std::uint32_t observedBits = 0U;
    std::uint32_t durationUs = 0U;
};

// Versioned, bounded interpretation derived from one exact immutable Capture
// and one exact annotation generation. No pulse bytes are owned here.
struct ProtocolDerivedDecode final {
    static constexpr std::uint16_t kDecoderVersion = 1U;
    static constexpr std::size_t kMaximumFields =
        ProtocolAnnotationSet::kCapacity;

    ProtocolDerivedDecodeStatus status =
        ProtocolDerivedDecodeStatus::InvalidArgument;
    ProtocolDerivedDecodeOutcome outcome =
        ProtocolDerivedDecodeOutcome::Partial;
    ProtocolAnnotationSource source{};
    std::uint32_t annotationStoreGeneration = 0U;
    std::uint16_t decoderVersion = kDecoderVersion;
    std::array<ProtocolDerivedField, kMaximumFields> fields{};
    std::size_t fieldCount = 0U;
    std::uint16_t observedBitFields = 0U;
    std::uint16_t inconclusiveFields = 0U;

    bool valid() const { return status == ProtocolDerivedDecodeStatus::Valid; }
};

ProtocolDerivedDecodeStatus deriveProtocolDecode(
    const domain::captures::InfraredRawSource& pulseSource,
    const ProtocolWorkbenchAnalysis& analysis, bool electricalStartLevel,
    const ProtocolAnnotationSet& annotations,
    std::uint32_t annotationStoreGeneration,
    ProtocolDerivedDecode* output);

}  // namespace leshy1::apps::protocol
