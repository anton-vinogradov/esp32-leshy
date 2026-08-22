#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/captures/InfraredRaw.h"
#include "domain/captures/SubGhzRaw.h"
#include "services/survey/SourceTimeline.h"

namespace leshy1::services::survey {

enum class SessionState : std::uint8_t {
    Idle,
    Running,
    Stopped,
};

enum class SessionStatus : std::uint8_t {
    Started,
    AlreadyStarted,
    InvalidSession,
    Appended,
    NotRunning,
    OutOfOrder,
    Full,
    Stopped,
    AlreadyStopped,
    TimelineIncomplete,
};

const char* sessionStatusName(SessionStatus status);

enum class SessionTimelineStatus : std::uint8_t {
    Started,
    Appended,
    Finalized,
    NotRunning,
    AlreadyStarted,
    NotStarted,
    AlreadyFinalized,
    InvalidMask,
    InvalidWindow,
    OutOfOrder,
    InvalidSummary,
};

const char* sessionTimelineStatusName(SessionTimelineStatus status);

enum class CaptureMetadataStatus : std::uint8_t {
    Configured,
    InvalidState,
    InvalidMetadata,
    AlreadyConfigured,
};

const char* captureMetadataStatusName(CaptureMetadataStatus status);

enum class FramePayloadFormat : std::uint8_t {
    None,
    Ieee80211,
};

// Immutable acquisition provenance for schema-v3+ Sessions. It records the exact
// passive receive plans and build identity that produced the normalized records.
// Frame payload and location flags are explicit so exports cannot invent PCAP or
// coordinates from observation-only scans.
struct CaptureMetadata final {
    static constexpr std::size_t kAppIdentityBytes = 32;

    bool present = false;
    bool passive = true;
    bool wifiShowHidden = false;
    bool locationPresent = false;
    bool framePayloadCaptured = false;
    bool subGhzRawCaptured = false;
    bool infraredRawCaptured = false;
    std::uint8_t selectedSourceMask = 0;
    std::uint32_t wifiMaxMsPerChannel = 0;
    std::uint8_t wifiChannel = 0;
    std::uint32_t bleDurationMs = 0;
    std::uint16_t bleIntervalMs = 0;
    std::uint16_t bleWindowMs = 0;
    std::uint16_t bleMaximumRecords = 0;
    std::uint64_t framePayloadBytes = 0;
    std::uint16_t framePayloadRecords = 0;
    std::uint16_t framePayloadSnapLength = 0;
    FramePayloadFormat framePayloadFormat = FramePayloadFormat::None;
    std::uint32_t subGhzFrequencyKHz = 0;
    std::int16_t subGhzThresholdDbm = 0;
    domain::captures::SubGhzRawModulation subGhzModulation =
        domain::captures::SubGhzRawModulation::OokEnvelope;
    bool subGhzStartLevel = true;
    bool subGhzTruncated = false;
    std::uint16_t subGhzPulseRecords = 0;
    std::uint32_t subGhzPulseBytes = 0;
    bool infraredStartLevel = false;
    bool infraredTruncated = false;
    std::uint16_t infraredPulseRecords = 0;
    std::uint32_t infraredPulseBytes = 0;
    domain::captures::InfraredDecode infraredDecode{};
    std::array<std::uint8_t, kAppIdentityBytes> appIdentity{};
    std::uint8_t appIdentityLength = 0;
};

struct SessionTimelineSummary final {
    bool present = false;
    bool finalized = false;
    std::uint8_t selectedMask = 0;
    std::uint64_t startedUs = 0;
    std::uint64_t stoppedUs = 0;
    std::uint32_t totalWindows = 0;
    std::uint32_t evictedWindows = 0;
    std::uint64_t overflowEvents = 0;
    std::array<SourceRuntimeSummary, SourceTimeline::kSourceCount> sources{};
};

class SurveySession final {
public:
    static constexpr std::size_t kSessionIdCapacity = 31;
    static constexpr std::size_t kObservationCapacity = 64;
    static constexpr std::size_t kTimelineWindowCapacity = 16;

    void reset();
    SessionStatus start(const char* sessionId, std::uint64_t monotonicUs);
    SessionStatus append(const domain::observations::Observation& observation);
    SessionStatus stop(std::uint64_t monotonicUs);
    CaptureMetadataStatus configureCaptureMetadata(
        const CaptureMetadata& metadata);
    SessionTimelineStatus startTimeline(std::uint8_t selectedMask,
                                        std::uint64_t monotonicUs);
    SessionTimelineStatus appendTimelineWindow(const SourceWindow& window);
    SessionTimelineStatus restoreTimelineEvictions(std::uint32_t evictedWindows);
    SessionTimelineStatus finalizeTimeline(
        std::uint64_t monotonicUs,
        const SourceRuntimeSummary& wifi,
        const SourceRuntimeSummary& ble,
        std::uint64_t overflowEvents);

    SessionState state() const { return state_; }
    const char* id() const { return sessionId_.data(); }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t stoppedUs() const { return stoppedUs_; }
    std::size_t size() const { return size_; }
    std::uint32_t dropped() const { return dropped_; }
    const CaptureMetadata& captureMetadata() const { return captureMetadata_; }
    const domain::observations::Observation* get(std::size_t index) const;
    const SessionTimelineSummary& timeline() const { return timeline_; }
    std::size_t timelineWindowCount() const { return timelineWindowSize_; }
    const SourceWindow* timelineWindow(std::size_t index) const;

private:
    std::array<char, kSessionIdCapacity + 1> sessionId_{};
    std::array<domain::observations::Observation, kObservationCapacity> observations_{};
    SessionState state_ = SessionState::Idle;
    std::uint64_t startedUs_ = 0;
    std::uint64_t stoppedUs_ = 0;
    std::size_t size_ = 0;
    std::uint32_t dropped_ = 0;
    CaptureMetadata captureMetadata_{};
    SessionTimelineSummary timeline_{};
    std::array<SourceWindow, kTimelineWindowCapacity> timelineWindows_{};
    std::size_t timelineWindowHead_ = 0;
    std::size_t timelineWindowSize_ = 0;
    std::uint64_t latestTimelineWindowEndUs_ = 0;
};

}  // namespace leshy1::services::survey
