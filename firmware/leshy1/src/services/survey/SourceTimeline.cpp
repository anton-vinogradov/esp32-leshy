#include "SourceTimeline.h"

#include <limits>

namespace leshy1::services::survey {
namespace {

using domain::observations::RadioKind;

std::size_t sourceIndex(RadioKind source) {
    switch (source) {
        case RadioKind::Wifi: return 0;
        case RadioKind::Ble: return 1;
    }
    return SourceTimeline::kSourceCount;
}

template <typename Value>
void saturatingIncrement(Value* value) {
    if (*value != std::numeric_limits<Value>::max()) ++(*value);
}

void saturatingAdd(std::uint64_t* value, std::uint64_t increment) {
    const std::uint64_t available =
        std::numeric_limits<std::uint64_t>::max() - *value;
    *value += increment > available ? available : increment;
}

bool transitionState(SourceWindowState state) {
    return state == SourceWindowState::Scheduled ||
           state == SourceWindowState::Active ||
           state == SourceWindowState::Unavailable ||
           state == SourceWindowState::Fault;
}

bool validReason(SourceWindowState state, SourceWindowReason reason) {
    switch (state) {
        case SourceWindowState::Scheduled:
            return reason == SourceWindowReason::DutyCycle;
        case SourceWindowState::Active:
            return reason == SourceWindowReason::None;
        case SourceWindowState::Unavailable:
            return reason == SourceWindowReason::DriverUnavailable ||
                   reason == SourceWindowReason::RadioConflict;
        case SourceWindowState::Fault:
            return reason == SourceWindowReason::DriverFault;
        case SourceWindowState::Unselected:
        case SourceWindowState::Stopped:
            return false;
    }
    return false;
}

}  // namespace

const char* sourceWindowStateName(SourceWindowState state) {
    switch (state) {
        case SourceWindowState::Unselected: return "unselected";
        case SourceWindowState::Scheduled: return "scheduled";
        case SourceWindowState::Active: return "active";
        case SourceWindowState::Unavailable: return "unavailable";
        case SourceWindowState::Fault: return "fault";
        case SourceWindowState::Stopped: return "stopped";
    }
    return "unknown";
}

const char* sourceWindowReasonName(SourceWindowReason reason) {
    switch (reason) {
        case SourceWindowReason::None: return "none";
        case SourceWindowReason::DutyCycle: return "duty_cycle";
        case SourceWindowReason::DriverUnavailable:
            return "driver_unavailable";
        case SourceWindowReason::RadioConflict: return "radio_conflict";
        case SourceWindowReason::DriverFault: return "driver_fault";
    }
    return "unknown";
}

const char* sourceTimelineStateName(SourceTimelineState state) {
    switch (state) {
        case SourceTimelineState::Idle: return "idle";
        case SourceTimelineState::Running: return "running";
        case SourceTimelineState::Stopped: return "stopped";
        case SourceTimelineState::Cancelled: return "cancelled";
    }
    return "unknown";
}

const char* sourceTimelineStatusName(SourceTimelineStatus status) {
    switch (status) {
        case SourceTimelineStatus::Started: return "started";
        case SourceTimelineStatus::Transitioned: return "transitioned";
        case SourceTimelineStatus::ObservationRecorded:
            return "observation_recorded";
        case SourceTimelineStatus::WindowDequeued: return "window_dequeued";
        case SourceTimelineStatus::Stopped: return "stopped";
        case SourceTimelineStatus::Cancelled: return "cancelled";
        case SourceTimelineStatus::InvalidMask: return "invalid_mask";
        case SourceTimelineStatus::InvalidSource: return "invalid_source";
        case SourceTimelineStatus::InvalidReason: return "invalid_reason";
        case SourceTimelineStatus::InvalidState: return "invalid_state";
        case SourceTimelineStatus::OutOfOrder: return "out_of_order";
        case SourceTimelineStatus::SameState: return "same_state";
        case SourceTimelineStatus::Full: return "full";
        case SourceTimelineStatus::Empty: return "empty";
    }
    return "unknown";
}

void SourceTimeline::reset() {
    sources_.fill(SourceSlot{});
    windows_.fill(SourceWindow{});
    state_ = SourceTimelineState::Idle;
    selectedMask_ = 0;
    startedUs_ = 0;
    endedUs_ = 0;
    latestUs_ = 0;
    windowHead_ = 0;
    windowSize_ = 0;
    windowHighWater_ = 0;
    overflowEvents_ = 0;
}

SourceTimeline::SourceSlot* SourceTimeline::slot(RadioKind source) {
    const std::size_t index = sourceIndex(source);
    return index < sources_.size() ? &sources_[index] : nullptr;
}

const SourceTimeline::SourceSlot* SourceTimeline::slot(
    RadioKind source) const {
    const std::size_t index = sourceIndex(source);
    return index < sources_.size() ? &sources_[index] : nullptr;
}

SourceTimelineStatus SourceTimeline::start(std::uint8_t selectedMask,
                                           std::uint64_t monotonicUs) {
    if (state_ != SourceTimelineState::Idle) {
        return SourceTimelineStatus::InvalidState;
    }
    if (monotonicUs == 0 || selectedMask == 0 ||
        (selectedMask & static_cast<std::uint8_t>(~kSupportedSourceMask)) != 0) {
        return SourceTimelineStatus::InvalidMask;
    }
    reset();
    selectedMask_ = selectedMask;
    startedUs_ = monotonicUs;
    latestUs_ = monotonicUs;
    for (std::size_t index = 0; index < sources_.size(); ++index) {
        const RadioKind source = index == 0 ? RadioKind::Wifi : RadioKind::Ble;
        SourceSlot& target = sources_[index];
        if ((selectedMask & sourceMask(source)) == 0) continue;
        target.summary.selected = true;
        target.summary.state = SourceWindowState::Scheduled;
        target.current = {source, SourceWindowState::Scheduled,
                          SourceWindowReason::DutyCycle, monotonicUs, 0, 0, 0};
    }
    state_ = SourceTimelineState::Running;
    return SourceTimelineStatus::Started;
}

bool SourceTimeline::closeAndQueue(SourceSlot& source,
                                   std::uint64_t monotonicUs) {
    if (windowSize_ >= windows_.size()) return false;
    SourceWindow completed = source.current;
    completed.endedUs = monotonicUs;
    const std::size_t tail = (windowHead_ + windowSize_) % windows_.size();
    windows_[tail] = completed;
    ++windowSize_;
    if (windowSize_ > windowHighWater_) windowHighWater_ = windowSize_;

    const std::uint64_t duration = completed.endedUs - completed.startedUs;
    switch (completed.state) {
        case SourceWindowState::Scheduled:
            saturatingAdd(&source.summary.scheduledUs, duration);
            break;
        case SourceWindowState::Active:
            saturatingAdd(&source.summary.activeUs, duration);
            break;
        case SourceWindowState::Unavailable:
            saturatingAdd(&source.summary.unavailableUs, duration);
            break;
        case SourceWindowState::Fault:
            saturatingAdd(&source.summary.faultUs, duration);
            break;
        case SourceWindowState::Unselected:
        case SourceWindowState::Stopped:
            break;
    }
    saturatingIncrement(&source.summary.windows);
    return true;
}

SourceTimelineStatus SourceTimeline::transition(
    RadioKind source, SourceWindowState state, SourceWindowReason reason,
    std::uint64_t monotonicUs) {
    SourceSlot* target = slot(source);
    if (target == nullptr) return SourceTimelineStatus::InvalidSource;
    if (state_ != SourceTimelineState::Running || !target->summary.selected ||
        !transitionState(state)) {
        return SourceTimelineStatus::InvalidState;
    }
    if (!validReason(state, reason)) {
        return SourceTimelineStatus::InvalidReason;
    }
    if (monotonicUs < latestUs_ || monotonicUs < target->current.startedUs) {
        return SourceTimelineStatus::OutOfOrder;
    }
    if (target->summary.state == state) return SourceTimelineStatus::SameState;
    if (windowSize_ >= windows_.size()) {
        saturatingIncrement(&overflowEvents_);
        return SourceTimelineStatus::Full;
    }
    closeAndQueue(*target, monotonicUs);
    target->current = {source, state, reason, monotonicUs, 0, 0, 0};
    target->summary.state = state;
    saturatingIncrement(&target->summary.transitions);
    latestUs_ = monotonicUs;
    return SourceTimelineStatus::Transitioned;
}

SourceTimelineStatus SourceTimeline::recordObservation(
    RadioKind source, bool accepted, std::uint64_t monotonicUs) {
    SourceSlot* target = slot(source);
    if (target == nullptr) return SourceTimelineStatus::InvalidSource;
    if (state_ != SourceTimelineState::Running || !target->summary.selected ||
        target->summary.state != SourceWindowState::Active) {
        return SourceTimelineStatus::InvalidState;
    }
    if (monotonicUs < latestUs_ || monotonicUs < target->current.startedUs) {
        return SourceTimelineStatus::OutOfOrder;
    }
    if (accepted) {
        saturatingIncrement(&target->current.accepted);
        saturatingIncrement(&target->summary.accepted);
    } else {
        saturatingIncrement(&target->current.dropped);
        saturatingIncrement(&target->summary.dropped);
    }
    latestUs_ = monotonicUs;
    return SourceTimelineStatus::ObservationRecorded;
}

SourceTimelineStatus SourceTimeline::finish(
    std::uint64_t monotonicUs, SourceTimelineState terminalState) {
    if (state_ != SourceTimelineState::Running) {
        return SourceTimelineStatus::InvalidState;
    }
    if (monotonicUs < latestUs_) return SourceTimelineStatus::OutOfOrder;
    std::size_t needed = 0;
    for (const SourceSlot& source : sources_) {
        if (source.summary.selected) ++needed;
    }
    if (windows_.size() - windowSize_ < needed) {
        saturatingIncrement(&overflowEvents_);
        return SourceTimelineStatus::Full;
    }
    for (SourceSlot& source : sources_) {
        if (!source.summary.selected) continue;
        closeAndQueue(source, monotonicUs);
        source.summary.state = SourceWindowState::Stopped;
    }
    endedUs_ = monotonicUs;
    latestUs_ = monotonicUs;
    state_ = terminalState;
    return terminalState == SourceTimelineState::Stopped
        ? SourceTimelineStatus::Stopped : SourceTimelineStatus::Cancelled;
}

SourceTimelineStatus SourceTimeline::stop(std::uint64_t monotonicUs) {
    return finish(monotonicUs, SourceTimelineState::Stopped);
}

SourceTimelineStatus SourceTimeline::cancel(std::uint64_t monotonicUs) {
    return finish(monotonicUs, SourceTimelineState::Cancelled);
}

SourceTimelineStatus SourceTimeline::pop(SourceWindow* output) {
    if (output == nullptr) return SourceTimelineStatus::InvalidState;
    if (windowSize_ == 0) return SourceTimelineStatus::Empty;
    *output = windows_[windowHead_];
    windows_[windowHead_] = {};
    windowHead_ = (windowHead_ + 1U) % windows_.size();
    --windowSize_;
    return SourceTimelineStatus::WindowDequeued;
}

const SourceRuntimeSummary* SourceTimeline::source(RadioKind source) const {
    const SourceSlot* found = slot(source);
    return found == nullptr ? nullptr : &found->summary;
}

std::uint16_t SourceTimeline::dutyPermille(RadioKind source,
                                           std::uint64_t asOfUs) const {
    const SourceSlot* found = slot(source);
    if (found == nullptr || !found->summary.selected ||
        asOfUs < startedUs_ || state_ == SourceTimelineState::Idle) {
        return 0;
    }
    if (state_ != SourceTimelineState::Running && asOfUs < endedUs_) return 0;
    const std::uint64_t effectiveEnd =
        state_ == SourceTimelineState::Running ? asOfUs : endedUs_;
    if (effectiveEnd <= startedUs_ || effectiveEnd < latestUs_) return 0;
    std::uint64_t activeUs = found->summary.activeUs;
    if (state_ == SourceTimelineState::Running &&
        found->summary.state == SourceWindowState::Active &&
        effectiveEnd >= found->current.startedUs) {
        saturatingAdd(&activeUs, effectiveEnd - found->current.startedUs);
    }
    const std::uint64_t elapsedUs = effectiveEnd - startedUs_;
    if (activeUs >= elapsedUs) return 1000;
    return static_cast<std::uint16_t>((activeUs * 1000U) / elapsedUs);
}

}  // namespace leshy1::services::survey
