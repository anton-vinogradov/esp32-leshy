#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::spectrum {

enum class Cc1101SignalFinderState : std::uint8_t {
    Idle,
    Calibrating,
    Searching,
    Fault,
};

const char* cc1101SignalFinderStateName(Cc1101SignalFinderState state);

// Passive, allocation-free frequency finder for the complete tunable CC1101
// receive envelope. Three ambient passes learn a median room floor per bin;
// this rejects both a single accidental button press and the low-biased noise
// floor that a minimum would create. Search results are the local RSSI rise
// above that floor after subtracting common whole-sweep drift. Known local
// crystal harmonics are never eligible as signal candidates.
class Cc1101SignalFinder final {
public:
    static constexpr std::uint32_t kStepKHz = 250;
    static constexpr std::size_t kBinCount = 1099;
    static constexpr std::uint8_t kCalibrationPasses = 3;
    static constexpr std::uint8_t kDetectionRiseDb = 18;
    static constexpr std::uint8_t kGraphFullScaleDb = 45;

    void reset();
    bool start(std::uint64_t monotonicUs);
    bool ingest(std::uint32_t frequencyKHz, std::int16_t rssiDbm,
                std::uint64_t startedUs, std::uint64_t endedUs);
    bool restart(std::uint64_t monotonicUs);
    bool fail();
    bool stop();

    Cc1101SignalFinderState state() const { return state_; }
    bool calibrated() const {
        return state_ == Cc1101SignalFinderState::Searching;
    }
    bool found() const {
        return calibrated() && strongestRiseDb_ >= kDetectionRiseDb;
    }
    std::size_t nextBin() const { return nextBin_; }
    std::uint32_t nextFrequencyKHz() const {
        return frequencyKHz(nextBin_);
    }
    std::uint8_t calibrationPasses() const { return calibrationPasses_; }
    std::uint8_t strongestRiseDb() const { return strongestRiseDb_; }
    std::size_t strongestBin() const { return strongestBin_; }
    std::uint32_t strongestFrequencyKHz() const {
        return frequencyKHz(strongestBin_);
    }
    std::uint8_t strength(std::size_t index) const {
        return index < heldRise_.size() ? heldRise_[index] : 0;
    }
    std::uint32_t sweeps() const { return sweeps_; }
    std::uint32_t revision() const { return revision_; }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t updatedUs() const { return updatedUs_; }
    const char* bandHint() const;

    static std::uint32_t frequencyKHz(std::size_t index);
    static bool tunableFrequency(std::uint32_t frequencyKHz);

private:
    void finishSweep();

    std::array<std::int8_t, kBinCount> baseline_{};
    std::array<std::int8_t, kBinCount> rawRise_{};
    std::array<std::uint8_t, kBinCount> heldRise_{};
    Cc1101SignalFinderState state_ = Cc1101SignalFinderState::Idle;
    std::size_t nextBin_ = 0;
    std::size_t strongestBin_ = 0;
    std::uint8_t calibrationPasses_ = 0;
    std::uint8_t strongestRiseDb_ = 0;
    std::uint32_t sweeps_ = 0;
    std::uint32_t revision_ = 0;
    std::uint64_t startedUs_ = 0;
    std::uint64_t updatedUs_ = 0;
};

}  // namespace leshy1::apps::spectrum
