#pragma once

#include <cstdint>

namespace leshy1::platform::arduino {

enum class WifiPassiveTeardownStep : std::uint8_t {
    CloseAdmission,
    DisablePromiscuous,
    AwaitCallbacks,
    StopWifi,
    DeinitWifi,
    DeleteEventLoop,
    RetryRequired,
    Complete,
};

struct WifiPassiveTeardownState final {
    bool callbackOwnerHeld = false;
    bool callbackAdmissionOpen = false;
    bool callbackGenerationInvalidated = false;
    std::uint32_t callbacksInFlight = 0U;
    bool logicalModeHeld = false;
    bool promiscuous = false;
    bool started = false;
    bool initialized = false;
    bool eventLoopOwned = false;
    bool nvsDisabled = false;
    bool volatileStorageOnly = false;
    bool failureObserved = false;
    int lastError = 0;
};

struct WifiPassiveTeardownAttempt final {
    bool promiscuousDisableAttempted = false;
    bool failed = false;
};

struct WifiAuthenticationSurveyTeardownState final {
    bool timelineTerminal = false;
    bool timelineHealthy = false;
    bool identityCleanupComplete = false;
    bool scannerCleanupComplete = false;
    bool sourceActive = true;
    bool scanActive = true;
    bool workerArmed = true;
};

// Closing the survey backend is a later teardown stage. It may touch the
// store/filesystem only after the producing worker and both scan ingress paths
// are terminal; otherwise a safety retry must retain ownership and wait.
constexpr bool wifiAuthenticationSurveyBackendClosePermitted(
    const WifiAuthenticationSurveyTeardownState& state) {
    return state.timelineTerminal && state.timelineHealthy &&
        state.identityCleanupComplete && state.scannerCleanupComplete &&
        !state.sourceActive && !state.scanActive && !state.workerArmed;
}

constexpr bool wifiPassiveCleanupProven(
    const WifiPassiveTeardownState& state) {
    return !state.callbackAdmissionOpen &&
        state.callbackGenerationInvalidated &&
        state.callbacksInFlight == 0U && !state.promiscuous &&
        !state.started && !state.initialized && !state.eventLoopOwned;
}

constexpr WifiPassiveTeardownStep nextWifiPassiveTeardownStep(
    const WifiPassiveTeardownState& state,
    const WifiPassiveTeardownAttempt& attempt) {
    if (attempt.failed) return WifiPassiveTeardownStep::RetryRequired;
    if (state.callbackAdmissionOpen ||
        !state.callbackGenerationInvalidated) {
        return WifiPassiveTeardownStep::CloseAdmission;
    }
    if (state.promiscuous && !attempt.promiscuousDisableAttempted) {
        return WifiPassiveTeardownStep::DisablePromiscuous;
    }
    if (state.callbacksInFlight != 0U) {
        return WifiPassiveTeardownStep::AwaitCallbacks;
    }
    if (state.started) return WifiPassiveTeardownStep::StopWifi;
    if (state.initialized) return WifiPassiveTeardownStep::DeinitWifi;
    if (state.eventLoopOwned) {
        return WifiPassiveTeardownStep::DeleteEventLoop;
    }
    return WifiPassiveTeardownStep::Complete;
}

constexpr void applyWifiPassiveTeardownFailure(
    WifiPassiveTeardownState* state, WifiPassiveTeardownAttempt* attempt,
    WifiPassiveTeardownStep step, int error) {
    if (state == nullptr || attempt == nullptr) return;
    state->failureObserved = true;
    state->lastError = error;
    attempt->failed = true;
    if (step == WifiPassiveTeardownStep::DisablePromiscuous) {
        attempt->promiscuousDisableAttempted = true;
    }
}

constexpr void applyWifiPassiveTeardownSuccess(
    WifiPassiveTeardownState* state, WifiPassiveTeardownAttempt* attempt,
    WifiPassiveTeardownStep step) {
    if (state == nullptr || attempt == nullptr) return;
    switch (step) {
        case WifiPassiveTeardownStep::CloseAdmission:
            state->callbackAdmissionOpen = false;
            state->callbackGenerationInvalidated = true;
            break;
        case WifiPassiveTeardownStep::DisablePromiscuous:
            attempt->promiscuousDisableAttempted = true;
            state->promiscuous = false;
            break;
        case WifiPassiveTeardownStep::AwaitCallbacks:
            state->callbacksInFlight = 0U;
            break;
        case WifiPassiveTeardownStep::StopWifi:
            state->started = false;
            state->promiscuous = false;
            break;
        case WifiPassiveTeardownStep::DeinitWifi:
            state->initialized = false;
            state->nvsDisabled = false;
            state->volatileStorageOnly = false;
            break;
        case WifiPassiveTeardownStep::DeleteEventLoop:
            state->eventLoopOwned = false;
            break;
        case WifiPassiveTeardownStep::Complete:
        case WifiPassiveTeardownStep::RetryRequired:
            break;
    }
}

constexpr bool wifiPassiveCaptureCompletionPermitted(
    const WifiPassiveTeardownState& state) {
    return !state.failureObserved && wifiPassiveCleanupProven(state);
}

constexpr bool wifiPassiveCallbackOwnerReleasePermitted(
    const WifiPassiveTeardownState& state) {
    return state.callbackOwnerHeld && state.logicalModeHeld &&
        wifiPassiveCleanupProven(state);
}

constexpr bool releaseWifiPassiveCallbackOwner(
    WifiPassiveTeardownState* state) {
    if (state == nullptr ||
        !wifiPassiveCallbackOwnerReleasePermitted(*state)) {
        return false;
    }
    state->logicalModeHeld = false;
    state->callbackOwnerHeld = false;
    return true;
}

constexpr bool wifiPassiveRfLeaseReleasePermitted(
    const WifiPassiveTeardownState& state) {
    return wifiPassiveCleanupProven(state) &&
        !state.callbackOwnerHeld && !state.logicalModeHeld;
}

}  // namespace leshy1::platform::arduino
