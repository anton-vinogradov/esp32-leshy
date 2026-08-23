#include "apps/spectrum/Nrf24SignalFinder.h"

#include <limits>

namespace leshy1::apps::spectrum {

namespace {
constexpr std::uint8_t kHoldDecay = 2;
}

const char* nrf24SignalFinderStateName(Nrf24SignalFinderState state) {
    switch (state) {
        case Nrf24SignalFinderState::Idle: return "idle";
        case Nrf24SignalFinderState::Calibrating: return "calibrating";
        case Nrf24SignalFinderState::Searching: return "searching";
        case Nrf24SignalFinderState::Fault: return "fault";
    }
    return "unknown";
}

void Nrf24SignalFinder::reset() {
    accumulated_.fill(0);
    baseline_.fill(0);
    heldRise_.fill(0);
    state_ = Nrf24SignalFinderState::Idle;
    modules_ = 0;
    calibrationWindows_ = 0;
    sweepsInWindow_ = 0;
    strongestRise_ = 0;
    strongestChannel_ =
        drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel;
    windows_ = 0;
    revision_ = 0;
    startedUs_ = 0;
    updatedUs_ = 0;
}

bool Nrf24SignalFinder::start(std::uint8_t modules,
                              std::uint64_t monotonicUs) {
    if (state_ != Nrf24SignalFinderState::Idle || modules == 0 ||
        modules > 3 || monotonicUs == 0) {
        return false;
    }
    reset();
    modules_ = modules;
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    state_ = Nrf24SignalFinderState::Calibrating;
    return true;
}

void Nrf24SignalFinder::clearMeasurement() {
    accumulated_.fill(0);
    sweepsInWindow_ = 0;
}

void Nrf24SignalFinder::finishWindow() {
    if (state_ == Nrf24SignalFinderState::Calibrating) {
        for (std::size_t index = 0; index < kChannelCount; ++index) {
            if (calibrationWindows_ == 0 ||
                accumulated_[index] < baseline_[index]) {
                baseline_[index] = accumulated_[index];
            }
        }
        ++calibrationWindows_;
        heldRise_.fill(0);
        strongestRise_ = 0;
        if (calibrationWindows_ >= kCalibrationWindows) {
            state_ = Nrf24SignalFinderState::Searching;
        }
    } else {
        std::int32_t totalDelta = 0;
        for (std::size_t index = 0; index < kChannelCount; ++index) {
            totalDelta += static_cast<std::int16_t>(accumulated_[index]) -
                          static_cast<std::int16_t>(baseline_[index]);
        }
        const std::int16_t meanDelta = static_cast<std::int16_t>(
            totalDelta / static_cast<std::int32_t>(kChannelCount));
        strongestRise_ = 0;
        for (std::size_t index = 0; index < kChannelCount; ++index) {
            std::int16_t rise =
                static_cast<std::int16_t>(accumulated_[index]) -
                static_cast<std::int16_t>(baseline_[index]) - meanDelta;
            if (rise < 0) rise = 0;
            if (rise > std::numeric_limits<std::uint8_t>::max()) {
                rise = std::numeric_limits<std::uint8_t>::max();
            }
            const std::uint8_t decayed = heldRise_[index] > kHoldDecay
                ? static_cast<std::uint8_t>(heldRise_[index] - kHoldDecay)
                : 0;
            heldRise_[index] = rise > decayed
                ? static_cast<std::uint8_t>(rise) : decayed;
            if (heldRise_[index] > strongestRise_) {
                strongestRise_ = heldRise_[index];
                strongestChannel_ = static_cast<std::uint8_t>(
                    drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel +
                    index);
            }
        }
    }
    if (windows_ != std::numeric_limits<std::uint32_t>::max()) ++windows_;
    if (revision_ != std::numeric_limits<std::uint32_t>::max()) ++revision_;
    clearMeasurement();
}

bool Nrf24SignalFinder::ingest(
    const drivers::radio::Nrf24PassiveSweep& sweep) {
    if ((state_ != Nrf24SignalFinderState::Calibrating &&
         state_ != Nrf24SignalFinderState::Searching) || !sweep.valid ||
        sweep.modules != modules_ || sweep.startedUs < updatedUs_ ||
        sweep.endedUs < sweep.startedUs) {
        return false;
    }
    for (std::size_t index = 0; index < kChannelCount; ++index) {
        if (sweep.sampled[index] == 0 || sweep.hits[index] == 0 ||
            accumulated_[index] == std::numeric_limits<std::uint8_t>::max()) {
            continue;
        }
        ++accumulated_[index];
    }
    if (sweep.sweepComplete) {
        if (sweepsInWindow_ != std::numeric_limits<std::uint8_t>::max()) {
            ++sweepsInWindow_;
        }
        if (sweepsInWindow_ >= kSweepsPerWindow) finishWindow();
    }
    updatedUs_ = sweep.endedUs;
    return true;
}

bool Nrf24SignalFinder::restart(std::uint64_t monotonicUs) {
    if ((state_ != Nrf24SignalFinderState::Calibrating &&
         state_ != Nrf24SignalFinderState::Searching) || monotonicUs == 0) {
        return false;
    }
    const std::uint8_t modules = modules_;
    reset();
    modules_ = modules;
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    state_ = Nrf24SignalFinderState::Calibrating;
    return true;
}

bool Nrf24SignalFinder::fail() {
    if (state_ == Nrf24SignalFinderState::Fault) return false;
    state_ = Nrf24SignalFinderState::Fault;
    return true;
}

bool Nrf24SignalFinder::stop() {
    if (state_ == Nrf24SignalFinderState::Idle) return false;
    state_ = Nrf24SignalFinderState::Idle;
    return true;
}

std::uint8_t Nrf24SignalFinder::nearestWifiChannel() const {
    if (!found()) return 0;
    const std::int16_t frequency =
        static_cast<std::int16_t>(strongestFrequencyMhz());
    std::uint8_t best = 1;
    std::int16_t bestDistance = 32767;
    for (std::uint8_t channel = 1; channel <= 13; ++channel) {
        const std::int16_t center = static_cast<std::int16_t>(
            2412 + static_cast<std::int16_t>(channel - 1U) * 5);
        const std::int16_t distance = frequency > center
            ? frequency - center : center - frequency;
        if (distance < bestDistance) {
            best = channel;
            bestDistance = distance;
        }
    }
    return bestDistance <= 6 ? best : 0;
}

std::uint8_t Nrf24SignalFinder::strength(std::size_t index) const {
    return index < heldRise_.size() ? heldRise_[index] : 0;
}

}  // namespace leshy1::apps::spectrum
