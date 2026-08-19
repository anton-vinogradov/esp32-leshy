#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::domain::captures {

enum class SubGhzRawModulation : std::uint8_t {
    OokEnvelope = 0,
    FskAsync = 1,
};

struct SubGhzRawPulseView final {
    std::uint16_t durationUs = 0;
};

// A bounded, read-only pulse stream shared by the live receiver and a
// validated persisted segment. Transmission is intentionally absent.
class SubGhzRawSource {
public:
    virtual ~SubGhzRawSource() = default;
    virtual std::size_t pulseCount() const = 0;
    virtual bool pulseView(std::size_t index,
                           SubGhzRawPulseView* output) const = 0;
};

}  // namespace leshy1::domain::captures
