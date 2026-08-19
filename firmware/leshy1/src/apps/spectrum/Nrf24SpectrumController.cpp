#include "apps/spectrum/Nrf24SpectrumController.h"

#include <limits>

namespace leshy1::apps::spectrum {

const char* nrf24SpectrumViewStateName(Nrf24SpectrumViewState state) {
    switch (state) {
        case Nrf24SpectrumViewState::Idle: return "idle";
        case Nrf24SpectrumViewState::Running: return "running";
        case Nrf24SpectrumViewState::Paused: return "paused";
        case Nrf24SpectrumViewState::Fault: return "fault";
    }
    return "unknown";
}

const char* nrf24SpectrumMetricName(Nrf24SpectrumMetric metric) {
    switch (metric) {
        case Nrf24SpectrumMetric::Signal: return "signal";
        case Nrf24SpectrumMetric::Traffic: return "traffic";
    }
    return "unknown";
}

void Nrf24SpectrumController::reset() {
    intensity_.fill(0);
    trafficIntensity_.fill(0);
    currentFixed_.fill(0);
    baselineFixed_.fill(0);
    metric_ = Nrf24SpectrumMetric::Signal;
    trafficPrimeSweeps_ = 40;
    state_ = Nrf24SpectrumViewState::Idle;
    modules_ = 0;
    activeBins_ = 0;
    hottestChannel_ =
        drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel;
    sweeps_ = 0;
    totalHits_ = 0;
    startedUs_ = 0;
    updatedUs_ = 0;
}

bool Nrf24SpectrumController::start(std::uint8_t modules,
                                    std::uint64_t monotonicUs) {
    if (state_ != Nrf24SpectrumViewState::Idle || modules == 0 ||
        modules > 3 || monotonicUs == 0) {
        return false;
    }
    intensity_.fill(0);
    trafficIntensity_.fill(0);
    currentFixed_.fill(0);
    baselineFixed_.fill(0);
    trafficPrimeSweeps_ = 40;
    modules_ = modules;
    activeBins_ = 0;
    hottestChannel_ =
        drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel;
    sweeps_ = 0;
    totalHits_ = 0;
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    state_ = Nrf24SpectrumViewState::Running;
    return true;
}

bool Nrf24SpectrumController::ingest(
    const drivers::radio::Nrf24PassiveSweep& sweep) {
    if (state_ != Nrf24SpectrumViewState::Running || !sweep.valid ||
        sweep.modules != modules_ || sweep.startedUs < updatedUs_ ||
        sweep.endedUs < sweep.startedUs) {
        return false;
    }
    activeBins_ = 0;
    for (std::size_t index = 0; index < intensity_.size(); ++index) {
        if (sweep.sampled[index] == 0) continue;
        const bool hit = sweep.hits[index] != 0;
        if (hit && totalHits_ != std::numeric_limits<std::uint64_t>::max()) {
            ++totalHits_;
        }
        const std::int16_t target = hit ? 255 : 0;
        const std::int16_t current = intensity_[index];
        intensity_[index] = static_cast<std::uint8_t>(
            current + (target - current) / 8);
        const std::int32_t signalFixed =
            static_cast<std::int32_t>(intensity_[index]) << 10;
        if (trafficPrimeSweeps_ != 0) {
            currentFixed_[index] = signalFixed;
            baselineFixed_[index] = signalFixed;
            trafficIntensity_[index] = 0;
        } else {
            currentFixed_[index] +=
                (signalFixed - currentFixed_[index]) / 32;
            baselineFixed_[index] +=
                (signalFixed - baselineFixed_[index]) / 256;
            std::int32_t activity =
                ((currentFixed_[index] - baselineFixed_[index]) >> 10) - 12;
            if (activity < 0) activity = 0;
            activity *= 3;
            if (activity > 255) activity = 255;
            trafficIntensity_[index] =
                static_cast<std::uint8_t>(activity);
        }
    }
    std::uint8_t hottestIntensity = 0;
    for (std::size_t index = 0; index < intensity_.size(); ++index) {
        if (intensity_[index] >= 24U) ++activeBins_;
        if (intensity_[index] > hottestIntensity) {
            hottestIntensity = intensity_[index];
            hottestChannel_ = static_cast<std::uint8_t>(
                drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel +
                index);
        }
    }
    if (sweep.sweepComplete) {
        if (trafficPrimeSweeps_ != 0) --trafficPrimeSweeps_;
        if (sweeps_ != std::numeric_limits<std::uint32_t>::max()) ++sweeps_;
    }
    updatedUs_ = sweep.endedUs;
    return true;
}

bool Nrf24SpectrumController::toggleMetric() {
    if (state_ != Nrf24SpectrumViewState::Running &&
        state_ != Nrf24SpectrumViewState::Paused) {
        return false;
    }
    metric_ = metric_ == Nrf24SpectrumMetric::Signal
        ? Nrf24SpectrumMetric::Traffic
        : Nrf24SpectrumMetric::Signal;
    return true;
}

bool Nrf24SpectrumController::togglePause() {
    if (state_ == Nrf24SpectrumViewState::Running) {
        state_ = Nrf24SpectrumViewState::Paused;
        return true;
    }
    if (state_ == Nrf24SpectrumViewState::Paused) {
        state_ = Nrf24SpectrumViewState::Running;
        return true;
    }
    return false;
}

bool Nrf24SpectrumController::fail() {
    if (state_ == Nrf24SpectrumViewState::Fault) return false;
    state_ = Nrf24SpectrumViewState::Fault;
    return true;
}

bool Nrf24SpectrumController::stop() {
    if (state_ == Nrf24SpectrumViewState::Idle) return false;
    state_ = Nrf24SpectrumViewState::Idle;
    return true;
}

std::uint8_t Nrf24SpectrumController::intensity(std::size_t index) const {
    return index < intensity_.size() ? intensity_[index] : 0;
}

std::uint8_t Nrf24SpectrumController::displayIntensity(
    std::size_t index) const {
    if (index >= intensity_.size()) return 0;
    return metric_ == Nrf24SpectrumMetric::Traffic
        ? trafficIntensity_[index] : intensity_[index];
}

}  // namespace leshy1::apps::spectrum
