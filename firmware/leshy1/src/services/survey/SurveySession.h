#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
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
    SessionTimelineSummary timeline_{};
    std::array<SourceWindow, kTimelineWindowCapacity> timelineWindows_{};
    std::size_t timelineWindowHead_ = 0;
    std::size_t timelineWindowSize_ = 0;
    std::uint64_t latestTimelineWindowEndUs_ = 0;
};

}  // namespace leshy1::services::survey
