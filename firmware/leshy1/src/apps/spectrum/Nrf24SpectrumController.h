#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "drivers/radio/Nrf24PassiveSpectrum.h"

namespace leshy1::apps::spectrum {

enum class Nrf24SpectrumViewState : std::uint8_t {
    Idle,
    Running,
    Paused,
    Fault,
};

const char* nrf24SpectrumViewStateName(Nrf24SpectrumViewState state);

enum class Nrf24SpectrumMetric : std::uint8_t {
    Signal,
    Traffic,
};

const char* nrf24SpectrumMetricName(Nrf24SpectrumMetric metric);

class Nrf24SpectrumController final {
public:
    static constexpr std::size_t kChannelCount =
        drivers::radio::Nrf24PassiveSpectrumPlan::kChannelCount;

    void reset();
    bool start(std::uint8_t modules, std::uint64_t monotonicUs);
    bool ingest(const drivers::radio::Nrf24PassiveSweep& sweep);
    bool toggleMetric();
    bool togglePause();
    bool fail();
    bool stop();

    Nrf24SpectrumViewState state() const { return state_; }
    std::uint8_t modules() const { return modules_; }
    std::uint32_t sweeps() const { return sweeps_; }
    std::uint64_t totalHits() const { return totalHits_; }
    std::uint8_t activeBins() const { return activeBins_; }
    std::uint8_t hottestChannel() const { return hottestChannel_; }
    std::uint8_t intensity(std::size_t index) const;
    std::uint8_t displayIntensity(std::size_t index) const;
    Nrf24SpectrumMetric metric() const { return metric_; }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t updatedUs() const { return updatedUs_; }

private:
    std::array<std::uint8_t, kChannelCount> intensity_{};
    std::array<std::uint8_t, kChannelCount> trafficIntensity_{};
    std::array<std::int32_t, kChannelCount> currentFixed_{};
    std::array<std::int32_t, kChannelCount> baselineFixed_{};
    Nrf24SpectrumMetric metric_ = Nrf24SpectrumMetric::Signal;
    std::uint8_t trafficPrimeSweeps_ = 40;
    Nrf24SpectrumViewState state_ = Nrf24SpectrumViewState::Idle;
    std::uint8_t modules_ = 0;
    std::uint8_t activeBins_ = 0;
    std::uint8_t hottestChannel_ =
        drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel;
    std::uint32_t sweeps_ = 0;
    std::uint64_t totalHits_ = 0;
    std::uint64_t startedUs_ = 0;
    std::uint64_t updatedUs_ = 0;
};

}  // namespace leshy1::apps::spectrum
