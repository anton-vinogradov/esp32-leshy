#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::services::survey {

enum class SourceWindowState : std::uint8_t {
    Unselected,
    Scheduled,
    Active,
    Unavailable,
    Fault,
    Stopped,
};

enum class SourceWindowReason : std::uint8_t {
    None,
    DutyCycle,
    DriverUnavailable,
    RadioConflict,
    DriverFault,
};

enum class SourceTimelineState : std::uint8_t {
    Idle,
    Running,
    Stopped,
    Cancelled,
};

enum class SourceTimelineStatus : std::uint8_t {
    Started,
    Transitioned,
    ObservationRecorded,
    WindowDequeued,
    Stopped,
    Cancelled,
    InvalidMask,
    InvalidSource,
    InvalidReason,
    InvalidState,
    OutOfOrder,
    SameState,
    Full,
    Empty,
};

const char* sourceWindowStateName(SourceWindowState state);
const char* sourceWindowReasonName(SourceWindowReason reason);
const char* sourceTimelineStateName(SourceTimelineState state);
const char* sourceTimelineStatusName(SourceTimelineStatus status);

constexpr std::uint8_t sourceMask(
    domain::observations::RadioKind source) {
    switch (source) {
        case domain::observations::RadioKind::Wifi: return 1U << 0U;
        case domain::observations::RadioKind::Ble: return 1U << 1U;
    }
    return 0;
}

constexpr std::uint8_t kSupportedSourceMask =
    sourceMask(domain::observations::RadioKind::Wifi) |
    sourceMask(domain::observations::RadioKind::Ble);

struct SourceWindow final {
    domain::observations::RadioKind source =
        domain::observations::RadioKind::Wifi;
    SourceWindowState state = SourceWindowState::Unselected;
    SourceWindowReason reason = SourceWindowReason::None;
    std::uint64_t startedUs = 0;
    std::uint64_t endedUs = 0;
    std::uint64_t accepted = 0;
    std::uint64_t dropped = 0;
};

struct SourceRuntimeSummary final {
    bool selected = false;
    SourceWindowState state = SourceWindowState::Unselected;
    std::uint64_t scheduledUs = 0;
    std::uint64_t activeUs = 0;
    std::uint64_t unavailableUs = 0;
    std::uint64_t faultUs = 0;
    std::uint64_t accepted = 0;
    std::uint64_t dropped = 0;
    std::uint32_t windows = 0;
    std::uint32_t transitions = 0;
};

// Allocation-free, streaming source-activity ledger. It retains aggregate duty
// and drop counters while completed windows leave through a bounded FIFO for
// durable storage. A full FIFO rejects the transition without changing the
// current source state, so an unrecorded transition cannot silently become fact.
class SourceTimeline final {
public:
    static constexpr std::size_t kSourceCount = 2;
    static constexpr std::size_t kWindowCapacity = 16;

    void reset();
    SourceTimelineStatus start(std::uint8_t selectedMask,
                               std::uint64_t monotonicUs);
    SourceTimelineStatus transition(
        domain::observations::RadioKind source, SourceWindowState state,
        SourceWindowReason reason, std::uint64_t monotonicUs);
    SourceTimelineStatus recordObservation(
        domain::observations::RadioKind source, bool accepted,
        std::uint64_t monotonicUs);
    SourceTimelineStatus stop(std::uint64_t monotonicUs);
    SourceTimelineStatus cancel(std::uint64_t monotonicUs);
    SourceTimelineStatus pop(SourceWindow* output);

    SourceTimelineState state() const { return state_; }
    std::uint8_t selectedMask() const { return selectedMask_; }
    std::uint64_t startedUs() const { return startedUs_; }
    std::uint64_t endedUs() const { return endedUs_; }
    std::size_t queuedWindows() const { return windowSize_; }
    std::size_t windowHighWater() const { return windowHighWater_; }
    std::uint64_t overflowEvents() const { return overflowEvents_; }
    const SourceRuntimeSummary* source(
        domain::observations::RadioKind source) const;
    std::uint16_t dutyPermille(domain::observations::RadioKind source,
                               std::uint64_t asOfUs) const;

private:
    struct SourceSlot final {
        SourceRuntimeSummary summary{};
        SourceWindow current{};
    };

    SourceTimelineStatus finish(std::uint64_t monotonicUs,
                                SourceTimelineState terminalState);
    SourceSlot* slot(domain::observations::RadioKind source);
    const SourceSlot* slot(domain::observations::RadioKind source) const;
    bool closeAndQueue(SourceSlot& source, std::uint64_t monotonicUs);

    std::array<SourceSlot, kSourceCount> sources_{};
    std::array<SourceWindow, kWindowCapacity> windows_{};
    SourceTimelineState state_ = SourceTimelineState::Idle;
    std::uint8_t selectedMask_ = 0;
    std::uint64_t startedUs_ = 0;
    std::uint64_t endedUs_ = 0;
    std::uint64_t latestUs_ = 0;
    std::size_t windowHead_ = 0;
    std::size_t windowSize_ = 0;
    std::size_t windowHighWater_ = 0;
    std::uint64_t overflowEvents_ = 0;
};

}  // namespace leshy1::services::survey
