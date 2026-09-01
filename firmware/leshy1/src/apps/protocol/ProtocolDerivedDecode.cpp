#include "ProtocolDerivedDecode.h"

#include <limits>

namespace leshy1::apps::protocol {
namespace {

bool isValueField(ProtocolAnnotationKind kind) {
    return kind == ProtocolAnnotationKind::Address ||
        kind == ProtocolAnnotationKind::Command ||
        kind == ProtocolAnnotationKind::Data ||
        kind == ProtocolAnnotationKind::Checksum;
}

bool logicalMark(bool electricalStartLevel, std::uint16_t pulse) {
    const bool electrical = (pulse % 2U) == 0U
        ? electricalStartLevel : !electricalStartLevel;
    return !electrical;
}

}  // namespace

const char* protocolDerivedDecodeStatusName(ProtocolDerivedDecodeStatus status) {
    switch (status) {
        case ProtocolDerivedDecodeStatus::Valid: return "valid";
        case ProtocolDerivedDecodeStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolDerivedDecodeStatus::SourceMismatch:
            return "source_mismatch";
        case ProtocolDerivedDecodeStatus::SourceReadFailed:
            return "source_read_failed";
    }
    return "invalid_argument";
}

const char* protocolDerivedFieldStatusName(ProtocolDerivedFieldStatus status) {
    switch (status) {
        case ProtocolDerivedFieldStatus::DurationOnly:
            return "duration_only";
        case ProtocolDerivedFieldStatus::BitsObserved:
            return "bits_observed";
        case ProtocolDerivedFieldStatus::Inconclusive:
            return "inconclusive";
    }
    return "inconclusive";
}

const char* protocolDerivedDecodeOutcomeName(
    ProtocolDerivedDecodeOutcome outcome) {
    switch (outcome) {
        case ProtocolDerivedDecodeOutcome::Complete: return "complete";
        case ProtocolDerivedDecodeOutcome::Partial: return "partial";
    }
    return "partial";
}

ProtocolDerivedDecodeStatus deriveProtocolDecode(
    const domain::captures::InfraredRawSource& pulseSource,
    const ProtocolWorkbenchAnalysis& analysis, bool electricalStartLevel,
    const ProtocolAnnotationSet& annotations,
    std::uint32_t annotationStoreGeneration,
    ProtocolDerivedDecode* output) {
    if (output == nullptr) return ProtocolDerivedDecodeStatus::InvalidArgument;
    *output = {};
    if (!analysis.valid() || !annotations.bound() || annotations.size() == 0U ||
        annotationStoreGeneration == 0U ||
        pulseSource.pulseCount() > ProtocolWorkbenchWorkspace::kMaximumPulses) {
        output->status = ProtocolDerivedDecodeStatus::InvalidArgument;
        return output->status;
    }
    output->source = annotations.source();
    output->annotationStoreGeneration = annotationStoreGeneration;
    if (annotations.source().captureFingerprint != analysis.sourceFingerprint ||
        annotations.source().pulseCount != analysis.pulseCount ||
        pulseSource.pulseCount() != analysis.pulseCount) {
        output->status = ProtocolDerivedDecodeStatus::SourceMismatch;
        return output->status;
    }

    for (std::size_t index = 0U; index < annotations.size(); ++index) {
        const ProtocolAnnotation* annotation = annotations.get(index);
        if (annotation == nullptr ||
            output->fieldCount >= output->fields.size()) {
            *output = {};
            output->status = ProtocolDerivedDecodeStatus::InvalidArgument;
            return output->status;
        }
        ProtocolDerivedField& field = output->fields[output->fieldCount++];
        field.kind = annotation->kind;
        field.firstPulse = annotation->firstPulse;
        field.lastPulse = annotation->lastPulse;
        std::uint64_t duration = 0U;
        for (std::uint32_t pulse = annotation->firstPulse;
             pulse <= annotation->lastPulse; ++pulse) {
            domain::captures::InfraredRawPulseView value;
            if (!pulseSource.pulseView(pulse, &value)) {
                *output = {};
                output->source = annotations.source();
                output->annotationStoreGeneration = annotationStoreGeneration;
                output->status = ProtocolDerivedDecodeStatus::SourceReadFailed;
                return output->status;
            }
            duration += value.durationUs;
        }
        field.durationUs = duration > std::numeric_limits<std::uint32_t>::max()
            ? std::numeric_limits<std::uint32_t>::max()
            : static_cast<std::uint32_t>(duration);
        if (!isValueField(field.kind)) {
            field.status = ProtocolDerivedFieldStatus::DurationOnly;
            continue;
        }

        const std::uint32_t pulseCount =
            static_cast<std::uint32_t>(field.lastPulse) -
            field.firstPulse + 1U;
        const std::uint32_t bitCount = pulseCount / 2U;
        bool conclusive = pulseCount % 2U == 0U && bitCount != 0U &&
            bitCount <= 32U && logicalMark(electricalStartLevel,
                                           field.firstPulse);
        std::uint32_t bits = 0U;
        for (std::uint32_t bit = 0U; conclusive && bit < bitCount; ++bit) {
            const std::uint16_t markIndex = static_cast<std::uint16_t>(
                static_cast<std::uint32_t>(field.firstPulse) + bit * 2U);
            const std::uint16_t spaceIndex =
                static_cast<std::uint16_t>(markIndex + 1U);
            domain::captures::InfraredRawPulseView mark;
            domain::captures::InfraredRawPulseView space;
            if (!pulseSource.pulseView(markIndex, &mark) ||
                !pulseSource.pulseView(spaceIndex, &space)) {
                *output = {};
                output->source = annotations.source();
                output->annotationStoreGeneration = annotationStoreGeneration;
                output->status = ProtocolDerivedDecodeStatus::SourceReadFailed;
                return output->status;
            }
            const std::uint16_t markUnits = protocolNormalizedUnits(
                analysis, mark.durationUs);
            const std::uint16_t spaceUnits = protocolNormalizedUnits(
                analysis, space.durationUs);
            conclusive = logicalMark(electricalStartLevel, markIndex) &&
                !logicalMark(electricalStartLevel, spaceIndex) &&
                markUnits == 1U && spaceUnits != 0U;
            if (conclusive && spaceUnits > 1U) {
                bits |= (std::uint32_t{1U} << bit);
            }
        }
        if (conclusive) {
            field.status = ProtocolDerivedFieldStatus::BitsObserved;
            field.bitCount = static_cast<std::uint16_t>(bitCount);
            field.observedBits = bits;
            ++output->observedBitFields;
        } else {
            field.status = ProtocolDerivedFieldStatus::Inconclusive;
            ++output->inconclusiveFields;
        }
    }
    output->outcome = output->inconclusiveFields == 0U
        ? ProtocolDerivedDecodeOutcome::Complete
        : ProtocolDerivedDecodeOutcome::Partial;
    output->status = ProtocolDerivedDecodeStatus::Valid;
    return output->status;
}

}  // namespace leshy1::apps::protocol
