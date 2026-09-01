#include "ProtocolAnnotations.h"

namespace leshy1::apps::protocol {
namespace {

bool validKind(ProtocolAnnotationKind kind) {
    return static_cast<std::uint8_t>(kind) <=
        static_cast<std::uint8_t>(ProtocolAnnotationKind::Gap);
}

bool overlaps(const ProtocolAnnotation& left,
              const ProtocolAnnotation& right) {
    return left.firstPulse <= right.lastPulse &&
        right.firstPulse <= left.lastPulse;
}

}  // namespace

const char* protocolAnnotationKindName(ProtocolAnnotationKind kind) {
    switch (kind) {
        case ProtocolAnnotationKind::Header: return "header";
        case ProtocolAnnotationKind::Address: return "address";
        case ProtocolAnnotationKind::Command: return "command";
        case ProtocolAnnotationKind::Data: return "data";
        case ProtocolAnnotationKind::Checksum: return "checksum";
        case ProtocolAnnotationKind::Gap: return "gap";
    }
    return "invalid";
}

bool sameProtocolAnnotationSource(const ProtocolAnnotationSource& left,
                                  const ProtocolAnnotationSource& right) {
    return left.captureGeneration == right.captureGeneration &&
        left.captureFingerprint == right.captureFingerprint &&
        left.pulseCount == right.pulseCount;
}

const char* protocolAnnotationStatusName(ProtocolAnnotationStatus status) {
    switch (status) {
        case ProtocolAnnotationStatus::Valid: return "valid";
        case ProtocolAnnotationStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolAnnotationStatus::SourceMismatch:
            return "source_mismatch";
        case ProtocolAnnotationStatus::RangeInvalid: return "range_invalid";
        case ProtocolAnnotationStatus::Overlap: return "overlap";
        case ProtocolAnnotationStatus::CapacityExceeded:
            return "capacity_exceeded";
        case ProtocolAnnotationStatus::NotFound: return "not_found";
    }
    return "invalid_argument";
}

ProtocolAnnotationStatus ProtocolAnnotationSet::bind(
    const ProtocolAnnotationSource& source) {
    if (!source.valid()) return ProtocolAnnotationStatus::InvalidArgument;
    clear();
    source_ = source;
    return ProtocolAnnotationStatus::Valid;
}

void ProtocolAnnotationSet::clear() {
    source_ = {};
    annotations_.fill({});
    size_ = 0U;
}

ProtocolAnnotationStatus ProtocolAnnotationSet::add(
    const ProtocolAnnotationSource& source,
    const ProtocolAnnotation& annotation) {
    if (!source.valid() || !validKind(annotation.kind)) {
        return ProtocolAnnotationStatus::InvalidArgument;
    }
    if (!bound() || !sameProtocolAnnotationSource(source_, source)) {
        return ProtocolAnnotationStatus::SourceMismatch;
    }
    if (annotation.firstPulse > annotation.lastPulse ||
        annotation.lastPulse >= source_.pulseCount) {
        return ProtocolAnnotationStatus::RangeInvalid;
    }
    if (size_ >= annotations_.size()) {
        return ProtocolAnnotationStatus::CapacityExceeded;
    }
    std::size_t insertion = size_;
    for (std::size_t index = 0U; index < size_; ++index) {
        if (overlaps(annotations_[index], annotation)) {
            return ProtocolAnnotationStatus::Overlap;
        }
        if (insertion == size_ &&
            annotation.firstPulse < annotations_[index].firstPulse) {
            insertion = index;
        }
    }
    for (std::size_t index = size_; index > insertion; --index) {
        annotations_[index] = annotations_[index - 1U];
    }
    annotations_[insertion] = annotation;
    ++size_;
    return ProtocolAnnotationStatus::Valid;
}

ProtocolAnnotationStatus ProtocolAnnotationSet::remove(
    const ProtocolAnnotationSource& source, std::size_t index) {
    if (!bound() || !sameProtocolAnnotationSource(source_, source)) {
        return ProtocolAnnotationStatus::SourceMismatch;
    }
    if (index >= size_) return ProtocolAnnotationStatus::NotFound;
    for (std::size_t cursor = index; cursor + 1U < size_; ++cursor) {
        annotations_[cursor] = annotations_[cursor + 1U];
    }
    --size_;
    annotations_[size_] = {};
    return ProtocolAnnotationStatus::Valid;
}

const ProtocolAnnotation* ProtocolAnnotationSet::get(
    std::size_t index) const {
    return index < size_ ? &annotations_[index] : nullptr;
}

const ProtocolAnnotation* ProtocolAnnotationSet::findAtPulse(
    std::uint16_t pulse) const {
    if (pulse >= source_.pulseCount) return nullptr;
    for (std::size_t index = 0U; index < size_; ++index) {
        if (annotations_[index].firstPulse <= pulse &&
            pulse <= annotations_[index].lastPulse) {
            return &annotations_[index];
        }
    }
    return nullptr;
}

}  // namespace leshy1::apps::protocol
