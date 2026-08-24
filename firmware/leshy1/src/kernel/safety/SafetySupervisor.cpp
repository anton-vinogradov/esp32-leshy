#include "kernel/safety/SafetySupervisor.h"

namespace leshy1::kernel::safety {
namespace {

bool recognizedReason(std::uint32_t reason) {
    return reason >= static_cast<std::uint32_t>(SafetyReason::RuntimeWatchdog) &&
           reason <= static_cast<std::uint32_t>(SafetyReason::WorkerDeadline);
}

}  // namespace

SafetyRetainedRecord makeSafetyRetainedRecord(
    std::uint32_t appIdentity, SafetyReason reason, std::uint32_t tripCount,
    std::uint32_t quiesceCount, bool latchConfirmed) {
    const std::uint32_t encodedReason = static_cast<std::uint32_t>(reason);
    const std::uint32_t encodedConfirmation = latchConfirmed ? 1U : 0U;
    return {
        kSafetyRetainedMagic,
        kSafetyRetainedSchema,
        appIdentity,
        ~appIdentity,
        encodedReason,
        ~encodedReason,
        tripCount,
        ~tripCount,
        quiesceCount,
        ~quiesceCount,
        encodedConfirmation,
        ~1U,
    };
}

bool validateSafetyRetainedRecord(const SafetyRetainedRecord& record,
                                  std::uint32_t appIdentity) {
    return appIdentity != 0 && record.magic == kSafetyRetainedMagic &&
           record.schema == kSafetyRetainedSchema &&
           record.appIdentity == appIdentity &&
           record.appIdentityInverse == ~record.appIdentity &&
           record.reasonInverse == ~record.reason &&
           recognizedReason(record.reason) && record.tripCount != 0 &&
           record.tripCountInverse == ~record.tripCount &&
           record.quiesceCount != 0 &&
           record.quiesceCountInverse == ~record.quiesceCount &&
           record.latchConfirmed <= 1U &&
           record.latchConfirmedInverse == ~1U;
}

bool shouldLatchSafetyStop(const SafetyRetainedRecord& record,
                           std::uint32_t appIdentity,
                           bool watchdogReset) {
    if (!validateSafetyRetainedRecord(record, appIdentity)) return false;
    const auto reason = static_cast<SafetyReason>(record.reason);
    return reason != SafetyReason::RuntimeWatchdog || watchdogReset ||
           record.latchConfirmed == 1U;
}

const char* safetyReasonName(SafetyReason reason) {
    switch (reason) {
        case SafetyReason::RuntimeWatchdog:
            return "runtime_watchdog";
        case SafetyReason::SupervisorUnavailable:
            return "supervisor_unavailable";
        case SafetyReason::OutputInvariant:
            return "output_invariant";
        case SafetyReason::WorkerDeadline:
            return "worker_deadline";
        case SafetyReason::None:
        default:
            return "none";
    }
}

const char* safetyStateName(SafetyState state) {
    switch (state) {
        case SafetyState::Armed:
            return "armed";
        case SafetyState::Latched:
            return "latched";
        case SafetyState::ClearPending:
            return "clear_pending";
        case SafetyState::Startup:
        default:
            return "startup";
    }
}

void SafetySupervisor::restore(const SafetyRetainedRecord& record,
                               std::uint32_t appIdentity,
                               bool watchdogReset) {
    state_ = SafetyState::Startup;
    reason_ = SafetyReason::None;
    tripCount_ = 0;
    quiesceCount_ = 0;
    if (!shouldLatchSafetyStop(record, appIdentity, watchdogReset)) return;
    state_ = SafetyState::Latched;
    reason_ = static_cast<SafetyReason>(record.reason);
    tripCount_ = record.tripCount;
    quiesceCount_ = record.quiesceCount;
}

bool SafetySupervisor::arm() {
    if (state_ != SafetyState::Startup) return false;
    state_ = SafetyState::Armed;
    return true;
}

bool SafetySupervisor::latch(SafetyReason reason, std::uint32_t tripCount,
                             std::uint32_t quiesceCount) {
    if (reason == SafetyReason::None || tripCount == 0 || quiesceCount == 0) {
        return false;
    }
    const bool changed = !latched() || reason_ != reason ||
                         tripCount_ != tripCount ||
                         quiesceCount_ != quiesceCount;
    state_ = SafetyState::Latched;
    reason_ = reason;
    tripCount_ = tripCount;
    quiesceCount_ = quiesceCount;
    return changed;
}

bool SafetySupervisor::requestClear() {
    if (state_ != SafetyState::Latched) return false;
    state_ = SafetyState::ClearPending;
    return true;
}

bool SafetySupervisor::cancelClear() {
    if (state_ != SafetyState::ClearPending) return false;
    state_ = SafetyState::Latched;
    return true;
}

bool SafetySupervisor::confirmClear(bool explicitConfirmation) {
    if (!explicitConfirmation || state_ != SafetyState::ClearPending) {
        return false;
    }
    state_ = SafetyState::Startup;
    reason_ = SafetyReason::None;
    tripCount_ = 0;
    quiesceCount_ = 0;
    return true;
}

}  // namespace leshy1::kernel::safety
