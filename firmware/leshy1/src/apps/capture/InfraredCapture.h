#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/InfraredRaw.h"

namespace leshy1::apps::capture {

enum class InfraredCaptureState : std::uint8_t {
    Idle,
    Waiting,
    Capturing,
    Complete,
    TimedOut,
    SignalTooLong,
    Unreliable,
    Cancelled,
    Failed,
};

const char* infraredCaptureStateName(InfraredCaptureState state);

struct InfraredCapturePlan final {
    std::uint32_t waitTimeoutMs = 10000;
    std::uint32_t maximumCaptureMs = 1000;
    std::uint16_t minimumPulseUs = 80;
    std::uint16_t endGapUs = 20000;
    std::uint16_t maximumSampleGapUs = 250;
    std::uint16_t maximumPulses = 512;
    bool idleLevel = true;
};

bool validateInfraredCapturePlan(const InfraredCapturePlan& plan);

struct InfraredLevelSample final {
    std::uint64_t monotonicUs = 0;
    bool level = true;
};

struct InfraredCaptureStats final {
    InfraredCaptureState state = InfraredCaptureState::Idle;
    std::uint64_t startedUs = 0;
    std::uint64_t signalStartedUs = 0;
    std::uint64_t endedUs = 0;
    std::uint32_t samples = 0;
    std::uint32_t invalidSamples = 0;
    std::uint32_t shortPulsesRejected = 0;
    std::uint32_t pulsesAccepted = 0;
    std::uint32_t maximumObservedSampleGapUs = 0;
    bool startLevel = false;
    bool truncated = false;
    std::int32_t driverError = 0;
};

class InfraredCapture final : public domain::captures::InfraredRawSource {
public:
    static constexpr std::size_t kPulseCapacity = 512;

    bool begin(const InfraredCapturePlan& plan, std::uint64_t startedUs,
               bool initialLevel);
    bool ingest(const InfraredLevelSample& sample);
    bool service(std::uint64_t monotonicUs);
    bool cancel(std::uint64_t endedUs);
    bool fail(std::int32_t driverError, std::uint64_t endedUs);
    void reset();

    const InfraredCapturePlan& plan() const { return plan_; }
    const InfraredCaptureStats& stats() const { return stats_; }
    const domain::captures::InfraredDecode& decode() const { return decode_; }
    std::size_t pulseCount() const override { return size_; }
    bool pulseView(std::size_t index,
                   domain::captures::InfraredRawPulseView* output) const override;

private:
    bool acceptTransition(bool level, std::uint64_t monotonicUs);
    bool finish(std::uint64_t endedUs, bool truncated);
    void decodeCapturedSignal();

    InfraredCapturePlan plan_{};
    InfraredCaptureStats stats_{};
    domain::captures::InfraredDecode decode_{};
    std::array<std::uint16_t, kPulseCapacity> pulses_{};
    std::size_t size_ = 0;
    bool currentLevel_ = true;
    std::uint64_t currentLevelSinceUs_ = 0;
    std::uint64_t lastSampleUs_ = 0;
};

}  // namespace leshy1::apps::capture
