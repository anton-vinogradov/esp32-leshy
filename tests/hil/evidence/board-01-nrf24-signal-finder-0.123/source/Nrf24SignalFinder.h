#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "drivers/radio/Nrf24PassiveSpectrum.h"

namespace leshy1::apps::spectrum {

enum class Nrf24SignalFinderState : std::uint8_t {
    Idle,
    Calibrating,
    Searching,
    Fault,
};

const char* nrf24SignalFinderStateName(Nrf24SignalFinderState state);

// Passive, allocation-free 2.4 GHz signal finder. It learns two short ambient
// windows and then reports only a local rise above that baseline. This avoids
// presenting a permanently busy Wi-Fi channel as the user's pressed remote/tag.
class Nrf24SignalFinder final {
public:
    static constexpr std::size_t kChannelCount =
        drivers::radio::Nrf24PassiveSpectrumPlan::kChannelCount;
    static constexpr std::uint8_t kSweepsPerWindow = 48;
    static constexpr std::uint8_t kCalibrationWindows = 2;
    static constexpr std::uint8_t kDetectionRise = 8;
    static constexpr std::uint8_t kGraphFullScale = 36;

    void reset();
    bool start(std::uint8_t modules, std::uint64_t monotonicUs);
    bool ingest(const drivers::radio::Nrf24PassiveSweep& sweep);
    bool restart(std::uint64_t monotonicUs);
    bool fail();
    bool stop();

    Nrf24SignalFinderState state() const { return state_; }
    bool calibrated() const {
        return state_ == Nrf24SignalFinderState::Searching;
    }
    bool found() const { return calibrated() && strongestRise_ >= kDetectionRise; }
    std::uint8_t modules() const { return modules_; }
    std::uint8_t calibrationWindows() const { return calibrationWindows_; }
    std::uint8_t sweepsInWindow() const { return sweepsInWindow_; }
    std::uint8_t strongestRise() const { return strongestRise_; }
    std::uint8_t strongestChannel() const { return strongestChannel_; }
    std::uint16_t strongestFrequencyMhz() const {
        return static_cast<std::uint16_t>(2400U + strongestChannel_);
    }
    std::uint8_t nearestWifiChannel() const;
    std::uint8_t strength(std::size_t index) const;
    std::uint32_t windows() const { return windows_; }
    std::uint32_t revision() const { return revision_; }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t updatedUs() const { return updatedUs_; }

private:
    void clearMeasurement();
    void finishWindow();

    std::array<std::uint8_t, kChannelCount> accumulated_{};
    std::array<std::uint8_t, kChannelCount> baseline_{};
    std::array<std::uint8_t, kChannelCount> heldRise_{};
    Nrf24SignalFinderState state_ = Nrf24SignalFinderState::Idle;
    std::uint8_t modules_ = 0;
    std::uint8_t calibrationWindows_ = 0;
    std::uint8_t sweepsInWindow_ = 0;
    std::uint8_t strongestRise_ = 0;
    std::uint8_t strongestChannel_ =
        drivers::radio::Nrf24PassiveSpectrumPlan::kFirstChannel;
    std::uint32_t windows_ = 0;
    std::uint32_t revision_ = 0;
    std::uint64_t startedUs_ = 0;
    std::uint64_t updatedUs_ = 0;
};

}  // namespace leshy1::apps::spectrum
