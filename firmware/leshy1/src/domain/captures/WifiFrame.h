#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::domain::captures {

enum class WifiFrameKind : std::uint8_t {
    Management,
    Control,
    Data,
};

struct WifiFrameView final {
    std::uint64_t monotonicUs = 0;
    std::uint16_t capturedLength = 0;
    std::uint16_t originalLength = 0;
    std::int16_t rssiDbm = 0;
    std::uint8_t channel = 0;
    WifiFrameKind kind = WifiFrameKind::Management;
    bool fcsIncluded = false;
    const std::uint8_t* payload = nullptr;
};

// A bounded, read-only frame stream. Live capture and a validated persisted
// segment implement the same interface, so PCAP export never needs a second
// payload-sized buffer.
class WifiFrameSource {
public:
    virtual ~WifiFrameSource() = default;
    virtual std::size_t frameCount() const = 0;
    virtual std::uint16_t snapLength() const = 0;
    virtual bool frameView(std::size_t index, WifiFrameView* output) const = 0;
};

}  // namespace leshy1::domain::captures
