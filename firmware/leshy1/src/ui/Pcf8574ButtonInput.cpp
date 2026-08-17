#include "ui/Pcf8574ButtonInput.h"

namespace leshy1::ui {

std::uint8_t Pcf8574ButtonInput::normalize(std::uint8_t raw) {
    return static_cast<std::uint8_t>((raw & kButtonMask) |
                                     static_cast<std::uint8_t>(~kButtonMask));
}

UiAction Pcf8574ButtonInput::actionForPressedMask(std::uint8_t pressed) {
    if (pressed == 0 || (pressed & static_cast<std::uint8_t>(pressed - 1U)) != 0) {
        return UiAction::Unknown;
    }
    if ((pressed & (1U << 6U)) != 0) return UiAction::Select;
    if ((pressed & (1U << 7U)) != 0) return UiAction::Up;
    if ((pressed & (1U << 5U)) != 0) return UiAction::Down;
    if ((pressed & (1U << 3U)) != 0) return UiAction::Left;
    if ((pressed & (1U << 4U)) != 0) return UiAction::Right;
    return UiAction::Unknown;
}

void Pcf8574ButtonInput::recordMappedPress(UiAction action) {
    switch (action) {
        case UiAction::Select: ++metrics_.selectPresses; break;
        case UiAction::Up: ++metrics_.upPresses; break;
        case UiAction::Down: ++metrics_.downPresses; break;
        case UiAction::Left: ++metrics_.leftPresses; break;
        case UiAction::Right: ++metrics_.rightPresses; break;
        default: break;
    }
}

void Pcf8574ButtonInput::reset(std::uint8_t initialRaw, std::uint32_t nowMs) {
    metrics_ = Pcf8574ButtonInputMetrics{};
    const std::uint8_t normalized = normalize(initialRaw);
    metrics_.latestRaw = initialRaw;
    metrics_.stableRaw = normalized;
    candidateRaw_ = normalized;
    candidateSinceMs_ = nowMs;
    lastSampleMs_ = nowMs;
    initialized_ = true;
    sampled_ = false;
}

UiAction Pcf8574ButtonInput::sample(bool valid, std::uint8_t raw,
                                    std::uint32_t nowMs) {
    if (sampled_) {
        const std::uint32_t gap = nowMs - lastSampleMs_;
        if (gap > metrics_.maximumSampleGapMs) metrics_.maximumSampleGapMs = gap;
    }
    lastSampleMs_ = nowMs;
    sampled_ = true;

    if (!valid) {
        ++metrics_.readErrors;
        return UiAction::Unknown;
    }
    ++metrics_.validSamples;
    metrics_.latestRaw = raw;

    const std::uint8_t normalized = normalize(raw);
    if (!initialized_) {
        metrics_.stableRaw = normalized;
        candidateRaw_ = normalized;
        candidateSinceMs_ = nowMs;
        initialized_ = true;
        return UiAction::Unknown;
    }
    if (normalized != candidateRaw_) {
        candidateRaw_ = normalized;
        candidateSinceMs_ = nowMs;
        ++metrics_.rawTransitions;
        return UiAction::Unknown;
    }
    if (candidateRaw_ == metrics_.stableRaw ||
        nowMs - candidateSinceMs_ < kDebounceMs) {
        return UiAction::Unknown;
    }

    const std::uint8_t previous = metrics_.stableRaw;
    metrics_.stableRaw = candidateRaw_;
    ++metrics_.stableTransitions;
    const std::uint8_t pressed = static_cast<std::uint8_t>(
        previous & static_cast<std::uint8_t>(~candidateRaw_) & kButtonMask);
    const std::uint8_t released = static_cast<std::uint8_t>(
        static_cast<std::uint8_t>(~previous) & candidateRaw_ & kButtonMask);
    if (released != 0) ++metrics_.releaseEvents;
    if (pressed == 0) return UiAction::Unknown;

    const UiAction action = actionForPressedMask(pressed);
    if (action == UiAction::Unknown) {
        ++metrics_.ambiguousPresses;
        return action;
    }
    ++metrics_.pressEvents;
    recordMappedPress(action);
    return action;
}

}  // namespace leshy1::ui
