#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/SubGhzRaw.h"

namespace leshy1::apps::capture {

enum class SubGhzRawCaptureState : std::uint8_t {
    Idle,
    Waiting,
    Capturing,
    Complete,
    TimedOut,
    SignalTooLong,
    Cancelled,
    Failed,
};

const char* subGhzRawCaptureStateName(SubGhzRawCaptureState state);

struct SubGhzRawCapturePlan final {
    std::uint32_t frequencyKHz = 433920;
    std::int16_t thresholdDbm = -72;
    std::uint32_t waitTimeoutMs = 10000;
    std::uint32_t maximumCaptureMs = 5000;
    std::uint16_t debounceUs = 60;
    std::uint16_t minimumFskPulseUs = 4;
    std::uint16_t endGapUs = 20000;
    std::uint16_t maximumPulses = 512;
    domain::captures::SubGhzRawModulation modulation =
        domain::captures::SubGhzRawModulation::OokEnvelope;
};

bool validateSubGhzRawCapturePlan(const SubGhzRawCapturePlan& plan);

struct SubGhzRawRssiSample final {
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = 0;
};

struct SubGhzRawCaptureStats final {
    SubGhzRawCaptureState state = SubGhzRawCaptureState::Idle;
    std::uint64_t startedUs = 0;
    std::uint64_t signalStartedUs = 0;
    std::uint64_t endedUs = 0;
    std::uint32_t samples = 0;
    std::uint32_t invalidSamples = 0;
    std::uint32_t shortTransitionsRejected = 0;
    std::uint32_t pulsesAccepted = 0;
    bool startLevel = true;
    bool truncated = false;
    std::int32_t driverError = 0;
};

class SubGhzRawCapture final : public domain::captures::SubGhzRawSource {
public:
    static constexpr std::size_t kPulseCapacity = 512;

    bool begin(const SubGhzRawCapturePlan& plan, std::uint64_t startedUs);
    bool ingest(const SubGhzRawRssiSample& sample);
    // FSK is admitted by the debounced RSSI carrier above. Once admitted, the
    // platform records only GDO0 CHANGE durations into a bounded ISR transport
    // and drains them here from task context. No radio write or transmit API is
    // reachable through this capture object.
    bool armFskEdges(bool startLevel, std::uint64_t monotonicUs);
    bool ingestFskEdge(std::uint32_t durationUs, bool newLevel,
                       bool transportClipped, std::uint64_t monotonicUs);
    bool finishFskTransport(std::uint64_t monotonicUs, bool overflowed);
    bool service(std::uint64_t monotonicUs);
    bool cancel(std::uint64_t endedUs);
    bool fail(std::int32_t driverError, std::uint64_t endedUs);
    void reset();

    const SubGhzRawCapturePlan& plan() const { return plan_; }
    const SubGhzRawCaptureStats& stats() const { return stats_; }
    std::size_t pulseCount() const override { return size_; }
    bool pulseView(std::size_t index,
                   domain::captures::SubGhzRawPulseView* output) const override;

private:
    bool finish(std::uint64_t endedUs, bool truncated);
    bool acceptStableLevel(bool level, std::uint64_t monotonicUs);

    SubGhzRawCapturePlan plan_{};
    SubGhzRawCaptureStats stats_{};
    std::array<std::uint16_t, kPulseCapacity> pulses_{};
    std::size_t size_ = 0;
    bool candidateLevel_ = false;
    bool stableLevel_ = false;
    bool candidateValid_ = false;
    std::uint64_t candidateSinceUs_ = 0;
    std::uint64_t stableSinceUs_ = 0;
    std::uint64_t lastSampleUs_ = 0;
    bool fskLevel_ = false;
    bool fskLevelValid_ = false;
};

}  // namespace leshy1::apps::capture
