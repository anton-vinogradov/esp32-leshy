#include "SurveySession.h"

#include <cstring>

namespace leshy1::services::survey {
namespace {

bool validSessionId(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    for (std::size_t index = 0; value[index] != '\0'; ++index) {
        const char character = value[index];
        const bool allowed = (character >= 'a' && character <= 'z') ||
                             (character >= 'A' && character <= 'Z') ||
                             (character >= '0' && character <= '9') || character == '-' ||
                             character == '_';
        if (!allowed || index >= SurveySession::kSessionIdCapacity) return false;
    }
    return true;
}

}  // namespace

const char* sessionStatusName(SessionStatus status) {
    switch (status) {
        case SessionStatus::Started: return "started";
        case SessionStatus::AlreadyStarted: return "already_started";
        case SessionStatus::InvalidSession: return "invalid_session";
        case SessionStatus::Appended: return "appended";
        case SessionStatus::NotRunning: return "not_running";
        case SessionStatus::OutOfOrder: return "out_of_order";
        case SessionStatus::Full: return "full";
        case SessionStatus::Stopped: return "stopped";
        case SessionStatus::AlreadyStopped: return "already_stopped";
        case SessionStatus::TimelineIncomplete: return "timeline_incomplete";
    }
    return "invalid_session";
}

const char* sessionTimelineStatusName(SessionTimelineStatus status) {
    switch (status) {
        case SessionTimelineStatus::Started: return "started";
        case SessionTimelineStatus::Appended: return "appended";
        case SessionTimelineStatus::Finalized: return "finalized";
        case SessionTimelineStatus::NotRunning: return "not_running";
        case SessionTimelineStatus::AlreadyStarted: return "already_started";
        case SessionTimelineStatus::NotStarted: return "not_started";
        case SessionTimelineStatus::AlreadyFinalized: return "already_finalized";
        case SessionTimelineStatus::InvalidMask: return "invalid_mask";
        case SessionTimelineStatus::InvalidWindow: return "invalid_window";
        case SessionTimelineStatus::OutOfOrder: return "out_of_order";
        case SessionTimelineStatus::InvalidSummary: return "invalid_summary";
    }
    return "invalid_summary";
}

const char* captureMetadataStatusName(CaptureMetadataStatus status) {
    switch (status) {
        case CaptureMetadataStatus::Configured: return "configured";
        case CaptureMetadataStatus::InvalidState: return "invalid_state";
        case CaptureMetadataStatus::InvalidMetadata: return "invalid_metadata";
        case CaptureMetadataStatus::AlreadyConfigured: return "already_configured";
    }
    return "invalid_metadata";
}

namespace {

bool validWindow(const SourceWindow& window, std::uint8_t selectedMask) {
    if ((selectedMask & sourceMask(window.source)) == 0 ||
        window.startedUs == 0 || window.endedUs < window.startedUs) {
        return false;
    }
    switch (window.state) {
        case SourceWindowState::Scheduled:
            return window.reason == SourceWindowReason::DutyCycle;
        case SourceWindowState::Active:
            return window.reason == SourceWindowReason::None;
        case SourceWindowState::Unavailable:
            return window.reason == SourceWindowReason::DriverUnavailable ||
                   window.reason == SourceWindowReason::RadioConflict;
        case SourceWindowState::Fault:
            return window.reason == SourceWindowReason::DriverFault;
        case SourceWindowState::Unselected:
        case SourceWindowState::Stopped:
            return false;
    }
    return false;
}

bool validSummary(const SourceRuntimeSummary& summary, bool selected) {
    if (summary.selected != selected) return false;
    if (!selected) {
        return summary.state == SourceWindowState::Unselected &&
               summary.scheduledUs == 0 && summary.activeUs == 0 &&
               summary.unavailableUs == 0 && summary.faultUs == 0 &&
               summary.accepted == 0 && summary.dropped == 0 &&
               summary.windows == 0 && summary.transitions == 0;
    }
    return summary.state == SourceWindowState::Stopped && summary.windows > 0 &&
           summary.transitions < UINT32_MAX &&
           summary.windows == summary.transitions + 1U;
}

bool exactDuration(const SourceRuntimeSummary& summary,
                   std::uint64_t elapsedUs) {
    if (!summary.selected) return true;
    if (summary.scheduledUs > elapsedUs) return false;
    std::uint64_t remaining = elapsedUs - summary.scheduledUs;
    if (summary.activeUs > remaining) return false;
    remaining -= summary.activeUs;
    if (summary.unavailableUs > remaining) return false;
    remaining -= summary.unavailableUs;
    return summary.faultUs == remaining;
}

}  // namespace

void SurveySession::reset() {
    sessionId_.fill('\0');
    observations_.fill(domain::observations::Observation{});
    state_ = SessionState::Idle;
    startedUs_ = 0;
    stoppedUs_ = 0;
    size_ = 0;
    dropped_ = 0;
    captureMetadata_ = {};
    timeline_ = {};
    timelineWindows_.fill(SourceWindow{});
    timelineWindowHead_ = 0;
    timelineWindowSize_ = 0;
    latestTimelineWindowEndUs_ = 0;
}

CaptureMetadataStatus SurveySession::configureCaptureMetadata(
    const CaptureMetadata& metadata) {
    if (state_ != SessionState::Running || size_ != 0) {
        return CaptureMetadataStatus::InvalidState;
    }
    if (captureMetadata_.present) {
        return CaptureMetadataStatus::AlreadyConfigured;
    }
    const bool wifiSelected =
        (metadata.selectedSourceMask & sourceMask(
            domain::observations::RadioKind::Wifi)) != 0;
    const bool bleSelected =
        (metadata.selectedSourceMask & sourceMask(
            domain::observations::RadioKind::Ble)) != 0;
    const bool validMask = metadata.selectedSourceMask != 0 &&
        (metadata.selectedSourceMask &
         static_cast<std::uint8_t>(~kSupportedSourceMask)) == 0;
    const bool validWifi = wifiSelected
        ? metadata.wifiMaxMsPerChannel >= 20 &&
              metadata.wifiMaxMsPerChannel <= 1000 &&
              metadata.wifiChannel <= 14
        : metadata.wifiMaxMsPerChannel == 0 && metadata.wifiChannel == 0 &&
              !metadata.wifiShowHidden;
    const bool validBle = bleSelected
        ? metadata.bleDurationMs > 0 && metadata.bleDurationMs <= 60000 &&
              metadata.bleIntervalMs > 0 &&
              metadata.bleWindowMs > 0 &&
              metadata.bleWindowMs <= metadata.bleIntervalMs &&
              metadata.bleMaximumRecords > 0 &&
              metadata.bleMaximumRecords <= kObservationCapacity
        : metadata.bleDurationMs == 0 && metadata.bleIntervalMs == 0 &&
              metadata.bleWindowMs == 0 && metadata.bleMaximumRecords == 0;
    if (!metadata.present || !metadata.passive || !validMask || !validWifi ||
        !validBle || metadata.locationPresent || metadata.framePayloadCaptured ||
        metadata.framePayloadBytes != 0 ||
        metadata.appIdentityLength != metadata.appIdentity.size()) {
        return CaptureMetadataStatus::InvalidMetadata;
    }
    bool identityPresent = false;
    for (const std::uint8_t byte : metadata.appIdentity) {
        identityPresent = identityPresent || byte != 0;
    }
    if (!identityPresent) return CaptureMetadataStatus::InvalidMetadata;
    if (timeline_.present &&
        timeline_.selectedMask != metadata.selectedSourceMask) {
        return CaptureMetadataStatus::InvalidMetadata;
    }
    captureMetadata_ = metadata;
    return CaptureMetadataStatus::Configured;
}

SessionStatus SurveySession::start(const char* sessionId, std::uint64_t monotonicUs) {
    if (state_ != SessionState::Idle) return SessionStatus::AlreadyStarted;
    if (!validSessionId(sessionId) || monotonicUs == 0) {
        return SessionStatus::InvalidSession;
    }
    const std::size_t length = std::strlen(sessionId);
    if (length > kSessionIdCapacity) return SessionStatus::InvalidSession;
    std::memcpy(sessionId_.data(), sessionId, length + 1);
    startedUs_ = monotonicUs;
    state_ = SessionState::Running;
    return SessionStatus::Started;
}

SessionStatus SurveySession::append(const domain::observations::Observation& observation) {
    if (state_ != SessionState::Running) return SessionStatus::NotRunning;
    const std::uint64_t previousUs = size_ == 0 ? startedUs_ : observations_[size_ - 1].monotonicUs;
    if (observation.monotonicUs < previousUs) return SessionStatus::OutOfOrder;
    if (size_ >= observations_.size()) {
        ++dropped_;
        return SessionStatus::Full;
    }
    observations_[size_] = observation;
    observations_[size_].sequence = static_cast<std::uint64_t>(size_ + 1);
    ++size_;
    return SessionStatus::Appended;
}

SessionStatus SurveySession::stop(std::uint64_t monotonicUs) {
    if (state_ == SessionState::Stopped) return SessionStatus::AlreadyStopped;
    if (state_ != SessionState::Running) return SessionStatus::NotRunning;
    if (timeline_.present && !timeline_.finalized) {
        return SessionStatus::TimelineIncomplete;
    }
    std::uint64_t lastUs = size_ == 0
        ? startedUs_ : observations_[size_ - 1].monotonicUs;
    if (timeline_.finalized && timeline_.stoppedUs > lastUs) {
        lastUs = timeline_.stoppedUs;
    }
    if (monotonicUs < lastUs) return SessionStatus::OutOfOrder;
    stoppedUs_ = monotonicUs;
    state_ = SessionState::Stopped;
    return SessionStatus::Stopped;
}

SessionTimelineStatus SurveySession::startTimeline(
    std::uint8_t selectedMask, std::uint64_t monotonicUs) {
    if (state_ != SessionState::Running) return SessionTimelineStatus::NotRunning;
    if (timeline_.present) return SessionTimelineStatus::AlreadyStarted;
    if (selectedMask == 0 ||
        (selectedMask & static_cast<std::uint8_t>(~kSupportedSourceMask)) != 0 ||
        monotonicUs < startedUs_) {
        return SessionTimelineStatus::InvalidMask;
    }
    timeline_ = {};
    timeline_.present = true;
    timeline_.selectedMask = selectedMask;
    timeline_.startedUs = monotonicUs;
    latestTimelineWindowEndUs_ = monotonicUs;
    return SessionTimelineStatus::Started;
}

SessionTimelineStatus SurveySession::appendTimelineWindow(
    const SourceWindow& window) {
    if (state_ != SessionState::Running) return SessionTimelineStatus::NotRunning;
    if (!timeline_.present) return SessionTimelineStatus::NotStarted;
    if (timeline_.finalized) return SessionTimelineStatus::AlreadyFinalized;
    if (!validWindow(window, timeline_.selectedMask) ||
        window.startedUs < timeline_.startedUs) {
        return SessionTimelineStatus::InvalidWindow;
    }
    if (window.endedUs < latestTimelineWindowEndUs_) {
        return SessionTimelineStatus::OutOfOrder;
    }
    if (timelineWindowSize_ < timelineWindows_.size()) {
        const std::size_t tail =
            (timelineWindowHead_ + timelineWindowSize_) % timelineWindows_.size();
        timelineWindows_[tail] = window;
        ++timelineWindowSize_;
    } else {
        timelineWindows_[timelineWindowHead_] = window;
        timelineWindowHead_ = (timelineWindowHead_ + 1U) % timelineWindows_.size();
        ++timeline_.evictedWindows;
    }
    ++timeline_.totalWindows;
    latestTimelineWindowEndUs_ = window.endedUs;
    return SessionTimelineStatus::Appended;
}

SessionTimelineStatus SurveySession::restoreTimelineEvictions(
    std::uint32_t evictedWindows) {
    if (state_ != SessionState::Running) return SessionTimelineStatus::NotRunning;
    if (!timeline_.present) return SessionTimelineStatus::NotStarted;
    if (timeline_.finalized) return SessionTimelineStatus::AlreadyFinalized;
    if (timelineWindowSize_ != 0 || timeline_.totalWindows != 0 ||
        timeline_.evictedWindows != 0) {
        return SessionTimelineStatus::InvalidSummary;
    }
    timeline_.totalWindows = evictedWindows;
    timeline_.evictedWindows = evictedWindows;
    return SessionTimelineStatus::Appended;
}

SessionTimelineStatus SurveySession::finalizeTimeline(
    std::uint64_t monotonicUs, const SourceRuntimeSummary& wifi,
    const SourceRuntimeSummary& ble, std::uint64_t overflowEvents) {
    if (state_ != SessionState::Running) return SessionTimelineStatus::NotRunning;
    if (!timeline_.present) return SessionTimelineStatus::NotStarted;
    if (timeline_.finalized) return SessionTimelineStatus::AlreadyFinalized;
    const std::uint64_t elapsedUs = monotonicUs >= timeline_.startedUs
        ? monotonicUs - timeline_.startedUs : 0;
    if (monotonicUs < latestTimelineWindowEndUs_ ||
        !validSummary(wifi, (timeline_.selectedMask & sourceMask(
            domain::observations::RadioKind::Wifi)) != 0) ||
        !validSummary(ble, (timeline_.selectedMask & sourceMask(
            domain::observations::RadioKind::Ble)) != 0) ||
        !exactDuration(wifi, elapsedUs) || !exactDuration(ble, elapsedUs) ||
        static_cast<std::uint64_t>(wifi.windows) + ble.windows !=
            timeline_.totalWindows ||
        timeline_.evictedWindows + timelineWindowSize_ !=
            timeline_.totalWindows) {
        return SessionTimelineStatus::InvalidSummary;
    }
    if (timeline_.evictedWindows == 0) {
        std::array<std::uint64_t, SourceTimeline::kSourceCount> accepted{};
        std::array<std::uint64_t, SourceTimeline::kSourceCount> dropped{};
        for (std::size_t index = 0; index < timelineWindowSize_; ++index) {
            const SourceWindow* window = timelineWindow(index);
            if (window == nullptr) return SessionTimelineStatus::InvalidSummary;
            const std::size_t sourceIndex =
                window->source == domain::observations::RadioKind::Wifi ? 0 : 1;
            if (UINT64_MAX - accepted[sourceIndex] < window->accepted ||
                UINT64_MAX - dropped[sourceIndex] < window->dropped) {
                return SessionTimelineStatus::InvalidSummary;
            }
            accepted[sourceIndex] += window->accepted;
            dropped[sourceIndex] += window->dropped;
        }
        if (accepted[0] != wifi.accepted || dropped[0] != wifi.dropped ||
            accepted[1] != ble.accepted || dropped[1] != ble.dropped) {
            return SessionTimelineStatus::InvalidSummary;
        }
    }
    timeline_.sources[0] = wifi;
    timeline_.sources[1] = ble;
    timeline_.overflowEvents = overflowEvents;
    timeline_.stoppedUs = monotonicUs;
    timeline_.finalized = true;
    return SessionTimelineStatus::Finalized;
}

const domain::observations::Observation* SurveySession::get(std::size_t index) const {
    return index < size_ ? &observations_[index] : nullptr;
}

const SourceWindow* SurveySession::timelineWindow(std::size_t index) const {
    if (index >= timelineWindowSize_) return nullptr;
    return &timelineWindows_[(timelineWindowHead_ + index) % timelineWindows_.size()];
}

}  // namespace leshy1::services::survey
