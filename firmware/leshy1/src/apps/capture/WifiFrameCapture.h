#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"

namespace leshy1::apps::capture {

using WifiFrameKind = domain::captures::WifiFrameKind;

const char* wifiFrameKindName(WifiFrameKind kind);

enum class WifiFrameCaptureState : std::uint8_t {
    Idle,
    Running,
    Complete,
    Failed,
};

const char* wifiFrameCaptureStateName(WifiFrameCaptureState state);

struct WifiFrameCapturePlan final {
    // Channel zero means bounded passive hopping across channels 1..13.
    std::uint8_t channel = 0;
    std::uint32_t durationMs = 10000;
    std::uint16_t channelDwellMs = 120;
    std::uint16_t snapLength = 256;
    std::uint16_t maximumFrames = 16;
};

bool validateWifiFrameCapturePlan(const WifiFrameCapturePlan& plan);

struct WifiFrame final {
    static constexpr std::size_t kPayloadCapacity = 256;

    std::uint64_t monotonicUs = 0;
    std::uint16_t capturedLength = 0;
    std::uint16_t originalLength = 0;
    std::int16_t rssiDbm = 0;
    std::uint8_t channel = 0;
    WifiFrameKind kind = WifiFrameKind::Management;
    bool fcsIncluded = false;
    std::array<std::uint8_t, kPayloadCapacity> payload{};
};

struct WifiFrameCaptureStats final {
    WifiFrameCaptureState state = WifiFrameCaptureState::Idle;
    std::uint64_t startedUs = 0;
    std::uint64_t endedUs = 0;
    std::uint32_t framesReported = 0;
    std::uint32_t framesAccepted = 0;
    std::uint32_t framesDroppedCapacity = 0;
    std::uint32_t framesDroppedInvalid = 0;
    std::uint32_t payloadBytes = 0;
    std::int32_t driverError = 0;
};

class WifiFrameCapture final : public domain::captures::WifiFrameSource {
public:
    static constexpr std::size_t kFrameCapacity = 16;

    bool begin(const WifiFrameCapturePlan& plan, std::uint64_t startedUs);
    bool append(const std::uint8_t* payload, std::uint16_t originalLength,
                std::uint64_t monotonicUs, std::int16_t rssiDbm,
                std::uint8_t channel, WifiFrameKind kind, bool fcsIncluded);
    bool complete(std::uint64_t endedUs);
    bool fail(std::int32_t driverError, std::uint64_t endedUs);
    void reset();

    const WifiFrameCapturePlan& plan() const { return plan_; }
    const WifiFrameCaptureStats& stats() const { return stats_; }
    const WifiFrame* frame(std::size_t index) const;
    std::size_t size() const { return size_; }
    std::size_t frameCount() const override { return size_; }
    std::uint16_t snapLength() const override { return plan_.snapLength; }
    bool frameView(std::size_t index,
                   domain::captures::WifiFrameView* output) const override;

private:
    WifiFrameCapturePlan plan_{};
    WifiFrameCaptureStats stats_{};
    std::array<WifiFrame, kFrameCapacity> frames_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::apps::capture
