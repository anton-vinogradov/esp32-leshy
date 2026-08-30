#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/targets/Target.h"

namespace leshy1::apps::targets {

enum class TargetRadarStatus : std::uint8_t {
    Idle,
    Waiting,
    Tracking,
    Partial,
    SourceLost,
    Stopped,
    Failed,
};

const char* targetRadarStatusName(TargetRadarStatus status);

enum class TargetRadarIngestStatus : std::uint8_t {
    InvalidArgument,
    Unmatched,
    Stale,
    Matched,
};

const char* targetRadarIngestStatusName(TargetRadarIngestStatus status);

struct TargetRadarSignal final {
    domain::targets::TargetIdentity identity{};
    domain::observations::RadioKind radio =
        domain::observations::RadioKind::Wifi;
    std::uint32_t samples = 0;
    std::int16_t rssiDbm = 0;
    std::int16_t previousRssiDbm = 0;
    std::int16_t minimumRssiDbm = 0;
    std::int16_t maximumRssiDbm = 0;
    std::int16_t trendDb = 0;
    std::uint16_t channel = 0;
    std::uint64_t firstSeenUs = 0;
    std::uint64_t lastSeenUs = 0;
    bool supported = false;
};

struct TargetRadarSnapshot final {
    TargetRadarStatus status = TargetRadarStatus::Idle;
    std::array<TargetRadarSignal,
               domain::targets::TargetRecord::kIdentityCapacity>
        signals{};
    std::uint8_t identityCount = 0;
    std::uint8_t supportedIdentityCount = 0;
    std::uint8_t matchedIdentityIndex = 0xffU;
    std::uint32_t samples = 0;
    std::uint32_t wifiSamples = 0;
    std::uint32_t bleSamples = 0;
    std::uint32_t unmatched = 0;
    std::uint32_t stale = 0;
    std::uint32_t revision = 0;
    bool passiveOnly = true;
    bool wifiStationSupported = false;
};

// Allocation-free signal tracker for one persisted Target. It never estimates
// distance: RSSI is environment dependent, so the UI exposes only the measured
// value, observed range and direction of change.
class TargetRadar final {
public:
    bool begin(const domain::targets::TargetRecord& target,
               bool wifiStationSupported);
    TargetRadarIngestStatus ingest(
        const domain::observations::Observation& observation);
    void sourceLost();
    void stop();
    void fail();
    void reset();

    const TargetRadarSnapshot& snapshot() const { return snapshot_; }

private:
    std::size_t findIdentity(
        const domain::observations::Observation& observation) const;
    void setTerminal(TargetRadarStatus status);

    TargetRadarSnapshot snapshot_{};
};

}  // namespace leshy1::apps::targets
