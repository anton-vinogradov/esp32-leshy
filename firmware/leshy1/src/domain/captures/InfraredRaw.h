#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::domain::captures {

enum class InfraredProtocol : std::uint8_t {
    Unknown = 0,
    Nec = 1,
    NecExtended = 2,
    NecRepeat = 3,
};

constexpr const char* infraredProtocolName(InfraredProtocol protocol) {
    switch (protocol) {
        case InfraredProtocol::Unknown: return "unknown";
        case InfraredProtocol::Nec: return "nec";
        case InfraredProtocol::NecExtended: return "nec_extended";
        case InfraredProtocol::NecRepeat: return "nec_repeat";
    }
    return "unknown";
}

struct InfraredRawPulseView final {
    std::uint16_t durationUs = 0;
};

// A bounded, read-only demodulated IR envelope. Transmission is deliberately
// absent: replay belongs to the separately authorized Lab path.
class InfraredRawSource {
public:
    virtual ~InfraredRawSource() = default;
    virtual std::size_t pulseCount() const = 0;
    virtual bool pulseView(std::size_t index,
                           InfraredRawPulseView* output) const = 0;
};

struct InfraredDecode final {
    InfraredProtocol protocol = InfraredProtocol::Unknown;
    std::uint32_t rawCode = 0;
    std::uint16_t address = 0;
    std::uint8_t command = 0;
    bool integrityValid = false;
};

}  // namespace leshy1::domain::captures
