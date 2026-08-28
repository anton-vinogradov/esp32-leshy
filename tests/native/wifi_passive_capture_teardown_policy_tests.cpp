#include <cstdlib>
#include <iostream>

#include "platform/arduino/WifiPassiveCaptureTeardownPolicy.h"

using namespace leshy1::platform::arduino;

namespace {

int failures = 0;

#define CHECK(expression)                                                    \
    do {                                                                     \
        if (!(expression)) {                                                 \
            std::cerr << __FILE__ << ':' << __LINE__                         \
                      << ": check failed: " #expression << '\n';            \
            ++failures;                                                      \
        }                                                                    \
    } while (false)

WifiPassiveTeardownState activeState() {
    WifiPassiveTeardownState state{};
    state.callbackOwnerHeld = true;
    state.callbackAdmissionOpen = true;
    state.callbacksInFlight = 1U;
    state.logicalModeHeld = true;
    state.promiscuous = true;
    state.started = true;
    state.initialized = true;
    state.eventLoopOwned = true;
    state.nvsDisabled = true;
    state.volatileStorageOnly = true;
    return state;
}

void closeAdmission(WifiPassiveTeardownState* state,
                    WifiPassiveTeardownAttempt* attempt) {
    CHECK(nextWifiPassiveTeardownStep(*state, *attempt) ==
          WifiPassiveTeardownStep::CloseAdmission);
    applyWifiPassiveTeardownSuccess(
        state, attempt, WifiPassiveTeardownStep::CloseAdmission);
}

void testTimeoutAndEveryIdfFailureRetainOwnershipUntilRetry() {
    WifiPassiveTeardownState state = activeState();
    WifiPassiveTeardownAttempt attempt{};
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    closeAdmission(&state, &attempt);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));

    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DisablePromiscuous);
    applyWifiPassiveTeardownFailure(
        &state, &attempt, WifiPassiveTeardownStep::DisablePromiscuous, 11);
    CHECK(state.promiscuous);
    CHECK(state.failureObserved);
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveRfLeaseReleasePermitted(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::RetryRequired);

    attempt = {};
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DisablePromiscuous);
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DisablePromiscuous);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::AwaitCallbacks);
    applyWifiPassiveTeardownFailure(
        &state, &attempt, WifiPassiveTeardownStep::AwaitCallbacks, 12);
    CHECK(state.callbacksInFlight == 1U);
    CHECK(state.started && state.initialized && state.eventLoopOwned);
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::RetryRequired);

    attempt = {};
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::AwaitCallbacks);
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::AwaitCallbacks);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::StopWifi);
    applyWifiPassiveTeardownFailure(
        &state, &attempt, WifiPassiveTeardownStep::StopWifi, 13);
    CHECK(state.started && !state.promiscuous);
    CHECK(state.initialized && state.eventLoopOwned);
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::RetryRequired);

    attempt = {};
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::StopWifi);
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::StopWifi);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(!state.started && !state.promiscuous);
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DeinitWifi);
    applyWifiPassiveTeardownFailure(
        &state, &attempt, WifiPassiveTeardownStep::DeinitWifi, 14);
    CHECK(state.initialized && state.eventLoopOwned);
    CHECK(state.nvsDisabled && state.volatileStorageOnly);
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::RetryRequired);

    attempt = {};
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DeinitWifi);
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DeinitWifi);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(!state.initialized);
    CHECK(!state.nvsDisabled && !state.volatileStorageOnly);
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DeleteEventLoop);
    applyWifiPassiveTeardownFailure(
        &state, &attempt, WifiPassiveTeardownStep::DeleteEventLoop, 15);
    CHECK(state.eventLoopOwned);
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::RetryRequired);

    attempt = {};
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::DeleteEventLoop);
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DeleteEventLoop);
    CHECK(nextWifiPassiveTeardownStep(state, attempt) ==
          WifiPassiveTeardownStep::Complete);
    CHECK(wifiPassiveCleanupProven(state));
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(wifiPassiveCallbackOwnerReleasePermitted(state));
    CHECK(!wifiPassiveRfLeaseReleasePermitted(state));
    CHECK(releaseWifiPassiveCallbackOwner(&state));
    CHECK(wifiPassiveRfLeaseReleasePermitted(state));
}

void testCleanPathAllowsCompletionOnlyAfterAllStages() {
    WifiPassiveTeardownState state = activeState();
    state.callbacksInFlight = 0U;
    WifiPassiveTeardownAttempt attempt{};
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    closeAdmission(&state, &attempt);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DisablePromiscuous);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::StopWifi);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DeinitWifi);
    CHECK(!wifiPassiveCaptureCompletionPermitted(state));
    CHECK(!wifiPassiveCallbackOwnerReleasePermitted(state));
    applyWifiPassiveTeardownSuccess(
        &state, &attempt, WifiPassiveTeardownStep::DeleteEventLoop);
    CHECK(wifiPassiveCleanupProven(state));
    CHECK(wifiPassiveCaptureCompletionPermitted(state));
    CHECK(releaseWifiPassiveCallbackOwner(&state));
    CHECK(wifiPassiveRfLeaseReleasePermitted(state));
}

void testSurveyBackendCloseRequiresProducerQuiescence() {
    WifiAuthenticationSurveyTeardownState state{};
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));

    state.timelineTerminal = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.timelineHealthy = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.identityCleanupComplete = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.scannerCleanupComplete = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.sourceActive = false;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.scanActive = false;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.workerArmed = false;
    CHECK(wifiAuthenticationSurveyBackendClosePermitted(state));

    state.workerArmed = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
    state.workerArmed = false;
    state.scanActive = true;
    CHECK(!wifiAuthenticationSurveyBackendClosePermitted(state));
}

}  // namespace

int main() {
    testTimeoutAndEveryIdfFailureRetainOwnershipUntilRetry();
    testCleanPathAllowsCompletionOnlyAfterAllStages();
    testSurveyBackendCloseRequiresProducerQuiescence();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "Wi-Fi passive teardown policy tests passed\n";
    return EXIT_SUCCESS;
}
