#include "ui/TouchInput.h"

namespace leshy1::ui {

void TouchInput::reset(std::uint32_t nowMs) {
    metrics_ = {};
    releaseCandidateSinceMs_ = nowMs;
    pressed_ = false;
    releaseCandidate_ = false;
}

bool TouchInput::sample(bool touched, std::uint16_t x, std::uint16_t y,
                        std::uint32_t nowMs, TouchPoint* press) {
    ++metrics_.samples;
    if (touched) {
        releaseCandidate_ = false;
        ++metrics_.touchedSamples;
        if (x >= kScreenWidth || y >= kScreenHeight) {
            ++metrics_.rejectedCoordinates;
            return false;
        }
        metrics_.lastX = x;
        metrics_.lastY = y;
        if (pressed_) return false;
        pressed_ = true;
        ++metrics_.pressEvents;
        if (press != nullptr) *press = {x, y};
        return true;
    }

    if (!pressed_) return false;
    if (!releaseCandidate_) {
        releaseCandidate_ = true;
        releaseCandidateSinceMs_ = nowMs;
        return false;
    }
    if (nowMs - releaseCandidateSinceMs_ < kReleaseDebounceMs) return false;
    releaseCandidate_ = false;
    pressed_ = false;
    ++metrics_.releaseEvents;
    return false;
}

}  // namespace leshy1::ui
