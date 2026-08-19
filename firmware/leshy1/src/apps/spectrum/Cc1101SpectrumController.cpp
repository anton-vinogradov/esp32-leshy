#include "apps/spectrum/Cc1101SpectrumController.h"

#include <limits>

namespace leshy1::apps::spectrum {

const char* cc1101SpectrumViewStateName(Cc1101SpectrumViewState state) {
    switch (state) {
        case Cc1101SpectrumViewState::Idle: return "idle";
        case Cc1101SpectrumViewState::Running: return "running";
        case Cc1101SpectrumViewState::Paused: return "paused";
        case Cc1101SpectrumViewState::Fault: return "fault";
    }
    return "unknown";
}

void Cc1101SpectrumController::clearBandData() {
    intensity_.fill(0);
    nextBin_ = 0;
    sweeps_ = 0;
    samples_ = 0;
    const auto currentPlan = plan();
    peakKHz_ = currentPlan.firstKHz +
        (currentPlan.lastKHz - currentPlan.firstKHz) / 2U;
    peakRssiDbm_ = -128;
    latestRssiDbm_ = -128;
}

void Cc1101SpectrumController::reset() {
    state_ = Cc1101SpectrumViewState::Idle;
    band_ = drivers::radio::Cc1101SpectrumBand::Band433;
    startedUs_ = 0;
    updatedUs_ = 0;
    clearBandData();
}

bool Cc1101SpectrumController::start(std::uint64_t monotonicUs) {
    return start(drivers::radio::Cc1101SpectrumBand::Band433, monotonicUs);
}

bool Cc1101SpectrumController::start(
    drivers::radio::Cc1101SpectrumBand band, std::uint64_t monotonicUs) {
    if (state_ != Cc1101SpectrumViewState::Idle || monotonicUs == 0 ||
        static_cast<std::uint8_t>(band) >= static_cast<std::uint8_t>(
            drivers::radio::Cc1101SpectrumBand::Count)) {
        return false;
    }
    band_ = band;
    clearBandData();
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    state_ = Cc1101SpectrumViewState::Running;
    return true;
}

bool Cc1101SpectrumController::ingest(
    const drivers::radio::Cc1101PassiveSample& sample) {
    const auto currentPlan = plan();
    if (state_ != Cc1101SpectrumViewState::Running || !sample.valid ||
        sample.band != band_ || sample.bin != nextBin_ ||
        sample.frequencyKHz != drivers::radio::cc1101SpectrumFrequencyKHz(
            currentPlan, nextBin_) || sample.rssiDbm < -128 ||
        sample.rssiDbm > 20 || sample.startedUs < updatedUs_ ||
        sample.endedUs < sample.startedUs) {
        return false;
    }
    latestRssiDbm_ = sample.rssiDbm;
    const int bounded = sample.rssiDbm < -110
        ? -110 : (sample.rssiDbm > -20 ? -20 : sample.rssiDbm);
    const std::uint8_t target = static_cast<std::uint8_t>(
        (bounded + 110) * 255 / 90);
    const std::uint16_t current = intensity_[nextBin_];
    intensity_[nextBin_] = static_cast<std::uint8_t>(
        target >= current ? current + (target - current + 1U) / 2U
                          : current - (current - target + 3U) / 4U);
    if (peakRssiDbm_ == -128 || sample.rssiDbm > peakRssiDbm_) {
        peakRssiDbm_ = sample.rssiDbm;
        peakKHz_ = sample.frequencyKHz;
    }
    if (samples_ != std::numeric_limits<std::uint64_t>::max()) ++samples_;
    updatedUs_ = sample.endedUs;
    ++nextBin_;
    if (nextBin_ == kBinCount) {
        nextBin_ = 0;
        if (sweeps_ != std::numeric_limits<std::uint32_t>::max()) ++sweeps_;
    }
    return true;
}

bool Cc1101SpectrumController::togglePause() {
    if (state_ == Cc1101SpectrumViewState::Running) {
        state_ = Cc1101SpectrumViewState::Paused;
        return true;
    }
    if (state_ == Cc1101SpectrumViewState::Paused) {
        state_ = Cc1101SpectrumViewState::Running;
        return true;
    }
    return false;
}

bool Cc1101SpectrumController::changeBand(int direction) {
    if (state_ != Cc1101SpectrumViewState::Running &&
        state_ != Cc1101SpectrumViewState::Paused) {
        return false;
    }
    const int count = static_cast<int>(
        drivers::radio::Cc1101SpectrumBand::Count);
    int next = static_cast<int>(band_) + direction;
    if (next < 0) next = count - 1;
    if (next >= count) next = 0;
    band_ = static_cast<drivers::radio::Cc1101SpectrumBand>(next);
    clearBandData();
    return true;
}

bool Cc1101SpectrumController::nextBand() { return changeBand(1); }
bool Cc1101SpectrumController::previousBand() { return changeBand(-1); }

bool Cc1101SpectrumController::fail() {
    if (state_ == Cc1101SpectrumViewState::Fault) return false;
    state_ = Cc1101SpectrumViewState::Fault;
    return true;
}

bool Cc1101SpectrumController::stop() {
    if (state_ == Cc1101SpectrumViewState::Idle) return false;
    state_ = Cc1101SpectrumViewState::Idle;
    return true;
}

std::uint8_t Cc1101SpectrumController::intensity(std::size_t index) const {
    return index < intensity_.size() ? intensity_[index] : 0;
}

}  // namespace leshy1::apps::spectrum
