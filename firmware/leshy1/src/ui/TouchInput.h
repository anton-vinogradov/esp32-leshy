#pragma once

#include <cstdint>

namespace leshy1::ui {

struct TouchPoint final {
    std::uint16_t x = 0;
    std::uint16_t y = 0;
};

struct TouchInputMetrics final {
    std::uint32_t samples = 0;
    std::uint32_t touchedSamples = 0;
    std::uint32_t pressEvents = 0;
    std::uint32_t releaseEvents = 0;
    std::uint32_t rejectedCoordinates = 0;
    std::uint16_t lastX = 0;
    std::uint16_t lastY = 0;
};

// Edge-triggered, allocation-free touch frontend. The hardware adapter supplies
// already calibrated screen coordinates; this class prevents a held or briefly
// noisy resistive panel from dispatching the same visible target repeatedly.
class TouchInput final {
public:
    static constexpr std::uint32_t kReleaseDebounceMs = 35;
    static constexpr std::uint16_t kScreenWidth = 240;
    static constexpr std::uint16_t kScreenHeight = 320;

    void reset(std::uint32_t nowMs);
    bool sample(bool touched, std::uint16_t x, std::uint16_t y,
                std::uint32_t nowMs, TouchPoint* press);

    bool pressed() const { return pressed_; }
    const TouchInputMetrics& metrics() const { return metrics_; }

private:
    TouchInputMetrics metrics_{};
    std::uint32_t releaseCandidateSinceMs_ = 0;
    bool pressed_ = false;
    bool releaseCandidate_ = false;
};

}  // namespace leshy1::ui
