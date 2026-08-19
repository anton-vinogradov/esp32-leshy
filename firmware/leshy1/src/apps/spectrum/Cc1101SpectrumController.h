#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "drivers/radio/Cc1101PassiveSpectrum.h"

namespace leshy1::apps::spectrum {

enum class Cc1101SpectrumViewState : std::uint8_t {
    Idle,
    Running,
    Paused,
    Fault,
};

const char* cc1101SpectrumViewStateName(Cc1101SpectrumViewState state);

class Cc1101SpectrumController final {
public:
    static constexpr std::size_t kBinCount =
        drivers::radio::Cc1101PassiveSpectrumPlan::kBinCount;

    void reset();
    bool start(std::uint64_t monotonicUs);
    bool start(drivers::radio::Cc1101SpectrumBand band,
               std::uint64_t monotonicUs);
    bool ingest(const drivers::radio::Cc1101PassiveSample& sample);
    bool togglePause();
    bool nextBand();
    bool previousBand();
    bool fail();
    bool stop();

    Cc1101SpectrumViewState state() const { return state_; }
    drivers::radio::Cc1101SpectrumBand band() const { return band_; }
    drivers::radio::Cc1101PassiveSpectrumPlan plan() const {
        return drivers::radio::cc1101PassiveSpectrumPlan(band_);
    }
    std::uint8_t nextBin() const { return nextBin_; }
    std::uint32_t sweeps() const { return sweeps_; }
    std::uint64_t samples() const { return samples_; }
    std::uint32_t peakKHz() const { return peakKHz_; }
    std::int16_t peakRssiDbm() const { return peakRssiDbm_; }
    std::int16_t latestRssiDbm() const { return latestRssiDbm_; }
    std::uint8_t intensity(std::size_t index) const;
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t updatedUs() const { return updatedUs_; }

private:
    bool changeBand(int direction);
    void clearBandData();

    std::array<std::uint8_t, kBinCount> intensity_{};
    Cc1101SpectrumViewState state_ = Cc1101SpectrumViewState::Idle;
    drivers::radio::Cc1101SpectrumBand band_ =
        drivers::radio::Cc1101SpectrumBand::Band433;
    std::uint8_t nextBin_ = 0;
    std::uint32_t sweeps_ = 0;
    std::uint64_t samples_ = 0;
    std::uint32_t peakKHz_ = 433920;
    std::int16_t peakRssiDbm_ = -128;
    std::int16_t latestRssiDbm_ = -128;
    std::uint64_t startedUs_ = 0;
    std::uint64_t updatedUs_ = 0;
};

}  // namespace leshy1::apps::spectrum
