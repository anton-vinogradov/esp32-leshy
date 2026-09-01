#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::protocol {

enum class ProtocolAnnotationKind : std::uint8_t {
    Header = 0,
    Address,
    Command,
    Data,
    Checksum,
    Gap,
};

const char* protocolAnnotationKindName(ProtocolAnnotationKind kind);

struct ProtocolAnnotationSource final {
    std::uint32_t captureGeneration = 0U;
    std::uint64_t captureFingerprint = 0U;
    std::uint16_t pulseCount = 0U;

    bool valid() const {
        return captureGeneration != 0U && captureFingerprint != 0U &&
            pulseCount >= 2U;
    }
};

bool sameProtocolAnnotationSource(const ProtocolAnnotationSource& left,
                                  const ProtocolAnnotationSource& right);

struct ProtocolAnnotation final {
    ProtocolAnnotationKind kind = ProtocolAnnotationKind::Data;
    std::uint16_t firstPulse = 0U;
    std::uint16_t lastPulse = 0U;
};

enum class ProtocolAnnotationStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SourceMismatch,
    RangeInvalid,
    Overlap,
    CapacityExceeded,
    NotFound,
};

const char* protocolAnnotationStatusName(ProtocolAnnotationStatus status);

// A small, deterministic derived record. It owns no raw pulse data and can
// only be used with the exact Capture generation/fingerprint it was bound to.
class ProtocolAnnotationSet final {
public:
    static constexpr std::size_t kCapacity = 12U;

    ProtocolAnnotationStatus bind(const ProtocolAnnotationSource& source);
    void clear();
    ProtocolAnnotationStatus add(const ProtocolAnnotationSource& source,
                                 const ProtocolAnnotation& annotation);
    ProtocolAnnotationStatus remove(const ProtocolAnnotationSource& source,
                                    std::size_t index);

    bool bound() const { return source_.valid(); }
    const ProtocolAnnotationSource& source() const { return source_; }
    std::size_t size() const { return size_; }
    const ProtocolAnnotation* get(std::size_t index) const;
    const ProtocolAnnotation* findAtPulse(std::uint16_t pulse) const;

private:
    ProtocolAnnotationSource source_{};
    std::array<ProtocolAnnotation, kCapacity> annotations_{};
    std::size_t size_ = 0U;
};

}  // namespace leshy1::apps::protocol
