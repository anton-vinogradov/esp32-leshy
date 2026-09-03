#include "BoardWifiPassiveCapture.h"

#include <esp_event.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <esp_wifi.h>
#include <freertos/task.h>

#include "platform/arduino/ArduinoWifiOwnIdentity.h"
#include "services/guard/AirspaceGuard.h"

namespace leshy1::platform::arduino {

namespace {

constexpr std::uint32_t kCallbackQuiescenceTimeoutMs = 100U;

std::uint32_t estimatedFrameAirtimeUs(const wifi_pkt_rx_ctrl_t& control) {
    std::uint32_t bytes = control.sig_len;
    if (bytes < 14U) bytes = 14U;
    if (control.sig_mode == 1U) {
        constexpr std::uint16_t htMbps10[8] = {
            65, 130, 195, 260, 390, 520, 585, 650,
        };
        const std::uint16_t rate = htMbps10[control.mcs & 7U];
        return 40U + static_cast<std::uint32_t>(
            static_cast<std::uint64_t>(bytes) * 8ULL * 10ULL / rate);
    }
    return 30U + bytes * 8U / 12U;
}

}  // namespace

using apps::capture::WifiFrameCaptureState;
using apps::capture::WifiFrameKind;

const char* boardWifiPassiveBeginFailureStageName(
    BoardWifiPassiveBeginFailureStage stage) {
    switch (stage) {
        case BoardWifiPassiveBeginFailureStage::None: return "none";
        case BoardWifiPassiveBeginFailureStage::Admission: return "admission";
        case BoardWifiPassiveBeginFailureStage::CaptureBegin:
            return "capture_begin";
        case BoardWifiPassiveBeginFailureStage::EventLoopCreate:
            return "event_loop_create";
        case BoardWifiPassiveBeginFailureStage::WifiInit: return "wifi_init";
        case BoardWifiPassiveBeginFailureStage::SetStorage:
            return "set_storage";
        case BoardWifiPassiveBeginFailureStage::SetMode: return "set_mode";
        case BoardWifiPassiveBeginFailureStage::SetIdentity:
            return "set_identity";
        case BoardWifiPassiveBeginFailureStage::WifiStart: return "wifi_start";
        case BoardWifiPassiveBeginFailureStage::SetChannel:
            return "set_channel";
        case BoardWifiPassiveBeginFailureStage::SetFilter: return "set_filter";
        case BoardWifiPassiveBeginFailureStage::SetCallback:
            return "set_callback";
        case BoardWifiPassiveBeginFailureStage::EnablePromiscuous:
            return "enable_promiscuous";
    }
    return "unknown";
}

BoardWifiPassiveCapture* BoardWifiPassiveCapture::active_ = nullptr;
portMUX_TYPE BoardWifiPassiveCapture::callbackMux_ =
    portMUX_INITIALIZER_UNLOCKED;
std::uint32_t BoardWifiPassiveCapture::callbacksInFlight_ = 0U;

void BoardWifiPassiveCapture::resetBeginDiagnostics() {
    beginDriverError_ = 0;
    beginFailureStage_ = BoardWifiPassiveBeginFailureStage::None;
    heapFreeBeforeInit_ = 0;
    heapLargestBeforeInit_ = 0;
}

void BoardWifiPassiveCapture::recordBeginFailure(
    BoardWifiPassiveBeginFailureStage stage, int error) {
    beginFailureStage_ = stage;
    beginDriverError_ = error;
    lastError_ = error;
}

void BoardWifiPassiveCapture::snapshotHeapBeforeInit() {
    heapFreeBeforeInit_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_8BIT));
    heapLargestBeforeInit_ = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
}

bool BoardWifiPassiveCapture::reserveCallbackOwner() {
    bool reserved = false;
    portENTER_CRITICAL(&callbackMux_);
    if (active_ == nullptr && !callbackAdmissionOpen_ &&
        callbacksInFlight_ == 0U) {
        active_ = this;
        ++callbackGeneration_;
        if (callbackGeneration_ == 0U) ++callbackGeneration_;
        reserved = true;
    }
    portEXIT_CRITICAL(&callbackMux_);
    return reserved;
}

void BoardWifiPassiveCapture::releaseCallbackOwner() {
    portENTER_CRITICAL(&callbackMux_);
    callbackAdmissionOpen_ = false;
    if (active_ == this) active_ = nullptr;
    portEXIT_CRITICAL(&callbackMux_);
}

void BoardWifiPassiveCapture::openCallbackAdmission() {
    portENTER_CRITICAL(&callbackMux_);
    if (active_ == this && callbacksInFlight_ == 0U) {
        callbackAdmissionOpen_ = true;
    }
    portEXIT_CRITICAL(&callbackMux_);
}

void BoardWifiPassiveCapture::closeCallbackAdmission() {
    portENTER_CRITICAL(&callbackMux_);
    callbackAdmissionOpen_ = false;
    ++callbackGeneration_;
    if (callbackGeneration_ == 0U) ++callbackGeneration_;
    portEXIT_CRITICAL(&callbackMux_);
}

bool BoardWifiPassiveCapture::callbacksQuiescent() const {
    portENTER_CRITICAL(&callbackMux_);
    const bool quiescent = callbacksInFlight_ == 0U;
    portEXIT_CRITICAL(&callbackMux_);
    return quiescent;
}

bool BoardWifiPassiveCapture::waitForCallbackQuiescence() {
    const std::uint64_t deadlineUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) +
        static_cast<std::uint64_t>(kCallbackQuiescenceTimeoutMs) * 1000ULL;
    while (!callbacksQuiescent()) {
        if (static_cast<std::uint64_t>(esp_timer_get_time()) >= deadlineUs) {
            return false;
        }
        vTaskDelay(1U);
    }
    return true;
}

WifiPassiveTeardownState BoardWifiPassiveCapture::teardownState(
    bool callbacksAreQuiescent) const {
    WifiPassiveTeardownState state{};
    portENTER_CRITICAL(&callbackMux_);
    state.callbackOwnerHeld = active_ == this;
    state.callbackAdmissionOpen = callbackAdmissionOpen_;
    state.callbackGenerationInvalidated = !callbackAdmissionOpen_;
    state.callbacksInFlight = callbacksAreQuiescent
        ? 0U : callbacksInFlight_;
    portEXIT_CRITICAL(&callbackMux_);
    state.logicalModeHeld = deviceMonitor_ || channelMonitor_ ||
        airspaceGuardMonitor_ || authenticationCapture_ ||
        state.callbackOwnerHeld;
    state.promiscuous = promiscuous_;
    state.started = started_;
    state.initialized = initialized_;
    state.eventLoopOwned = eventLoopOwned_;
    state.nvsDisabled = nvsDisabled_;
    state.volatileStorageOnly = volatileStorageOnly_;
    state.failureObserved = lastError_ != 0;
    state.lastError = lastError_;
    return state;
}

void BoardWifiPassiveCapture::applyTeardownState(
    const WifiPassiveTeardownState& state) {
    promiscuous_ = state.promiscuous;
    started_ = state.started;
    initialized_ = state.initialized;
    eventLoopOwned_ = state.eventLoopOwned;
    nvsDisabled_ = state.nvsDisabled;
    volatileStorageOnly_ = state.volatileStorageOnly;
    cleanupComplete_ = wifiPassiveCleanupProven(state);
    lastError_ = state.lastError;
}

void BoardWifiPassiveCapture::releaseFailedBegin() {
    closeCallbackAdmission();
    portENTER_CRITICAL(&mux_);
    if (deviceMonitor_) {
        deviceStats_.active = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
    }
    if (channelMonitor_) {
        channelStats_.active = false;
        channelStats_.cleanupComplete = cleanupComplete_;
    }
    if (airspaceGuardMonitor_) {
        airspaceGuardStats_.active = false;
        airspaceGuardStats_.cleanupComplete = cleanupComplete_;
    }
    if (authenticationCapture_) {
        authenticationStats_.active = false;
        authenticationStats_.cleanupComplete = cleanupComplete_;
    }
    portEXIT_CRITICAL(&mux_);
    // A failed ESP-IDF teardown still owns the callback singleton and the
    // logical monitor admission. Retain both until stop() can retry every
    // outstanding teardown stage and prove exact quiescence.
    WifiPassiveTeardownState teardown = teardownState(true);
    if (!cleanupComplete_ ||
        !wifiPassiveCallbackOwnerReleasePermitted(teardown)) {
        return;
    }
    deviceMonitor_ = false;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    authenticationCapture_ = false;
    releaseCallbackOwner();
    releaseWifiPassiveCallbackOwner(&teardown);
}

bool BoardWifiPassiveCapture::begin(
    const apps::capture::WifiFrameCapturePlan& plan,
    std::uint64_t startedUs) {
    return beginCapture(plan, startedUs, false, false, nullptr);
}

bool BoardWifiPassiveCapture::beginAirspaceGuardMonitor(
    std::uint64_t startedUs, std::uint32_t durationMs,
    std::uint16_t channelDwellMs) {
    apps::capture::WifiFrameCapturePlan plan{};
    plan.durationMs = durationMs;
    plan.channelDwellMs = channelDwellMs;
    plan.maximumFrames = static_cast<std::uint16_t>(
        apps::capture::WifiFrameCapture::kFrameCapacity);
    return beginCapture(plan, startedUs, true, false, nullptr);
}

bool BoardWifiPassiveCapture::beginAuthenticationCapture(
    const apps::capture::WifiFrameCapturePlan& plan,
    const std::array<std::uint8_t, 6>& targetAccessPoint,
    std::uint64_t startedUs) {
    bool any = false;
    bool allOnes = true;
    for (const std::uint8_t octet : targetAccessPoint) {
        any = any || octet != 0U;
        allOnes = allOnes && octet == 0xffU;
    }
    if (!any || allOnes || (targetAccessPoint[0] & 1U) != 0U) return false;
    return beginCapture(plan, startedUs, false, true, &targetAccessPoint);
}

bool BoardWifiPassiveCapture::beginCapture(
    const apps::capture::WifiFrameCapturePlan& plan,
    std::uint64_t startedUs, bool airspaceGuardMonitor,
    bool authenticationCapture,
    const std::array<std::uint8_t, 6>* authenticationTarget) {
    if (initialized_ || started_ || promiscuous_) {
        return false;
    }
    resetBeginDiagnostics();
    if (!apps::capture::validateWifiFrameCapturePlan(plan) ||
        (authenticationCapture && authenticationTarget == nullptr)) {
        recordBeginFailure(BoardWifiPassiveBeginFailureStage::Admission,
                           ESP_ERR_INVALID_ARG);
        return false;
    }
    if (!reserveCallbackOwner()) {
        recordBeginFailure(BoardWifiPassiveBeginFailureStage::Admission,
                           ESP_ERR_INVALID_STATE);
        return false;
    }
    capture_.reset();
    if (!capture_.begin(plan, startedUs)) {
        recordBeginFailure(BoardWifiPassiveBeginFailureStage::CaptureBegin,
                           ESP_ERR_INVALID_ARG);
        releaseFailedBegin();
        return false;
    }
    deviceMonitor_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = airspaceGuardMonitor;
    authenticationCapture_ = authenticationCapture;
    if (authenticationCapture) authenticationTarget_ = *authenticationTarget;
    airspaceGuardStats_ = {};
    authenticationStats_ = {};
    airspaceGuardIdentityRetention_.reset();
    airspaceGuardStats_.cleanupComplete = !airspaceGuardMonitor;
    authenticationStats_.cleanupComplete = !authenticationCapture;
    cleanupComplete_ = false;
    lastError_ = 0;

    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
    } else if (error != ESP_ERR_INVALID_STATE) {
        recordBeginFailure(
            BoardWifiPassiveBeginFailureStage::EventLoopCreate, error);
        capture_.fail(error, startedUs);
        cleanupComplete_ = true;
        releaseFailedBegin();
        return false;
    }

    snapshotHeapBeforeInit();
    wifi_init_config_t init = makeBoardWifiPassiveOnlyInitConfig();
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        recordBeginFailure(BoardWifiPassiveBeginFailureStage::WifiInit, error);
        capture_.fail(error, startedUs);
        endWifi();
        releaseFailedBegin();
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) {
        volatileStorageOnly_ = true;
        error = esp_wifi_set_mode(WIFI_MODE_STA);
        if (error != ESP_OK) {
            recordBeginFailure(
                BoardWifiPassiveBeginFailureStage::SetMode, error);
        }
        if (error == ESP_OK && !wifiOwnIdentity().apply(WIFI_IF_STA)) {
            error = wifiOwnIdentity().diagnostics().lastError;
            recordBeginFailure(
                BoardWifiPassiveBeginFailureStage::SetIdentity, error);
        }
    } else {
        recordBeginFailure(
            BoardWifiPassiveBeginFailureStage::SetStorage, error);
    }
    if (error == ESP_OK) {
        error = esp_wifi_start();
        if (error != ESP_OK) {
            recordBeginFailure(
                BoardWifiPassiveBeginFailureStage::WifiStart, error);
        }
    }
    if (error != ESP_OK) {
        capture_.fail(error, startedUs);
        endWifi();
        releaseFailedBegin();
        return false;
    }
    started_ = true;

    currentChannel_ = plan.channel == 0U ? 1U : plan.channel;
    error = esp_wifi_set_channel(currentChannel_, WIFI_SECOND_CHAN_NONE);
    if (error != ESP_OK) {
        recordBeginFailure(
            BoardWifiPassiveBeginFailureStage::SetChannel, error);
    }
    wifi_promiscuous_filter_t filter{};
    filter.filter_mask = authenticationCapture_
        ? WIFI_PROMIS_FILTER_MASK_DATA
        : (airspaceGuardMonitor_
               ? WIFI_PROMIS_FILTER_MASK_MGMT
               : WIFI_PROMIS_FILTER_MASK_MGMT |
                     WIFI_PROMIS_FILTER_MASK_CTRL |
                     WIFI_PROMIS_FILTER_MASK_DATA);
    if (error == ESP_OK) {
        error = esp_wifi_set_promiscuous_filter(&filter);
        if (error != ESP_OK) {
            recordBeginFailure(
                BoardWifiPassiveBeginFailureStage::SetFilter, error);
        }
    }
    if (error == ESP_OK) {
        error = esp_wifi_set_promiscuous_rx_cb(&receive);
        if (error != ESP_OK) {
            recordBeginFailure(
                BoardWifiPassiveBeginFailureStage::SetCallback, error);
        }
    }
    if (error != ESP_OK) {
        capture_.fail(error, startedUs);
        endWifi();
        releaseFailedBegin();
        return false;
    }

    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        recordBeginFailure(
            BoardWifiPassiveBeginFailureStage::EnablePromiscuous, error);
        portENTER_CRITICAL(&mux_);
        capture_.fail(error, startedUs);
        portEXIT_CRITICAL(&mux_);
        endWifi();
        releaseFailedBegin();
        return false;
    }
    promiscuous_ = true;
    portENTER_CRITICAL(&mux_);
    if (airspaceGuardMonitor_) airspaceGuardStats_.active = true;
    if (authenticationCapture_) authenticationStats_.active = true;
    portEXIT_CRITICAL(&mux_);
    channelDwellMs_ = plan.channelDwellMs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(plan.channelDwellMs) * 1000ULL;
    openCallbackAdmission();
    return true;
}

bool BoardWifiPassiveCapture::beginDeviceMonitor(
    std::uint64_t startedUs, std::uint16_t channelDwellMs) {
    if (initialized_ || started_ || promiscuous_ ||
        startedUs == 0U || channelDwellMs < 50U || channelDwellMs > 1000U) {
        return false;
    }
    if (!reserveCallbackOwner()) return false;
    capture_.reset();
    deviceQueue_.fill(apps::wifi::WifiDeviceObservation{});
    deviceQueueHead_ = 0;
    deviceQueueTail_ = 0;
    deviceQueueSize_ = 0;
    deviceStats_ = {};
    nextDeviceDataInspectUs_ = startedUs;
    deviceStats_.cleanupComplete = false;
    deviceMonitor_ = true;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    authenticationCapture_ = false;
    cleanupComplete_ = false;
    lastError_ = 0;

    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
    } else if (error != ESP_ERR_INVALID_STATE) {
        lastError_ = error;
        cleanupComplete_ = true;
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = true;
        releaseFailedBegin();
        return false;
    }

    wifi_init_config_t init = makeBoardWifiPassiveOnlyInitConfig();
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK && !wifiOwnIdentity().apply(WIFI_IF_STA)) {
        error = wifiOwnIdentity().diagnostics().lastError;
    }
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    started_ = true;

    currentChannel_ = 1U;
    error = esp_wifi_set_channel(currentChannel_, WIFI_SECOND_CHAN_NONE);
    wifi_promiscuous_filter_t filter{};
    filter.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT |
                         WIFI_PROMIS_FILTER_MASK_DATA;
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_filter(&filter);
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_rx_cb(&receive);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }

    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    promiscuous_ = true;
    channelDwellMs_ = channelDwellMs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(channelDwellMs_) * 1000ULL;
    channelLandedUs_ = startedUs;
    portENTER_CRITICAL(&mux_);
    deviceStats_.active = true;
    portEXIT_CRITICAL(&mux_);
    openCallbackAdmission();
    return true;
}

bool BoardWifiPassiveCapture::beginChannelMonitor(
    std::uint64_t startedUs, std::uint16_t channelDwellMs) {
    if (initialized_ || started_ || promiscuous_ ||
        startedUs == 0U || channelDwellMs < 50U || channelDwellMs > 1000U) {
        return false;
    }
    if (!reserveCallbackOwner()) return false;
    capture_.reset();
    channelLoad_.reset();
    channelStats_ = {};
    channelStats_.cleanupComplete = false;
    deviceMonitor_ = false;
    channelMonitor_ = true;
    airspaceGuardMonitor_ = false;
    authenticationCapture_ = false;
    cleanupComplete_ = false;
    lastError_ = 0;

    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
    } else if (error != ESP_ERR_INVALID_STATE) {
        lastError_ = error;
        cleanupComplete_ = true;
        channelMonitor_ = false;
        channelStats_.cleanupComplete = true;
        releaseFailedBegin();
        return false;
    }
    wifi_init_config_t init = makeBoardWifiPassiveOnlyInitConfig();
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK && !wifiOwnIdentity().apply(WIFI_IF_STA)) {
        error = wifiOwnIdentity().diagnostics().lastError;
    }
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    started_ = true;
    currentChannel_ = 1U;
    error = esp_wifi_set_channel(currentChannel_, WIFI_SECOND_CHAN_NONE);
    wifi_promiscuous_filter_t filter{};
    filter.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT |
                         WIFI_PROMIS_FILTER_MASK_CTRL |
                         WIFI_PROMIS_FILTER_MASK_DATA;
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_filter(&filter);
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_rx_cb(&receive);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        releaseFailedBegin();
        return false;
    }
    promiscuous_ = true;
    channelDwellMs_ = channelDwellMs;
    channelLandedUs_ = startedUs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(channelDwellMs_) * 1000ULL;
    portENTER_CRITICAL(&mux_);
    channelStats_.active = true;
    portEXIT_CRITICAL(&mux_);
    openCallbackAdmission();
    return true;
}

bool BoardWifiPassiveCapture::service(std::uint64_t nowUs) {
    if (deviceMonitor_ || channelMonitor_) {
        if (!promiscuous_) return false;
        if (deviceMonitor_ && deviceChannelLocked_) return false;
        if (nowUs >= nextChannelUs_) {
            if (channelMonitor_) {
                const std::uint64_t elapsed = nowUs - channelLandedUs_;
                portENTER_CRITICAL(&mux_);
                channelLoad_.completeDwell(
                    currentChannel_, static_cast<std::uint32_t>(
                        elapsed > UINT32_MAX ? UINT32_MAX : elapsed));
                portEXIT_CRITICAL(&mux_);
            }
            const std::uint8_t next = currentChannel_ >= 13U
                ? 1U : static_cast<std::uint8_t>(currentChannel_ + 1U);
            const bool changed = changeChannel(next, nowUs);
            if (changed) {
                portENTER_CRITICAL(&mux_);
                if (deviceMonitor_) ++deviceStats_.channelHops;
                if (channelMonitor_) ++channelStats_.channelHops;
                if (airspaceGuardMonitor_) {
                    ++airspaceGuardStats_.channelHops;
                }
                portEXIT_CRITICAL(&mux_);
            }
            channelLandedUs_ = nowUs;
            return changed;
        }
        return false;
    }
    const apps::capture::WifiFrameCaptureStats current = stats();
    if (current.state != WifiFrameCaptureState::Running) return false;
    if (nowUs >= current.startedUs +
                     static_cast<std::uint64_t>(capture_.plan().durationMs) *
                         1000ULL) {
        return stop(nowUs);
    }
    if (capture_.plan().channel == 0U && nowUs >= nextChannelUs_) {
        const std::uint8_t next = currentChannel_ >= 13U
                                      ? 1U
                                      : static_cast<std::uint8_t>(
                                            currentChannel_ + 1U);
        const bool changed = changeChannel(next, nowUs);
        if (changed && airspaceGuardMonitor_) {
            portENTER_CRITICAL(&mux_);
            ++airspaceGuardStats_.channelHops;
            portEXIT_CRITICAL(&mux_);
        }
        return changed;
    }
    return false;
}

bool BoardWifiPassiveCapture::stop(std::uint64_t endedUs) {
    const apps::capture::WifiFrameCaptureStats current = stats();
    portENTER_CRITICAL(&callbackMux_);
    const bool ownsCallbackLifecycle = active_ == this;
    portEXIT_CRITICAL(&callbackMux_);
    const bool terminalCapture =
        current.state == WifiFrameCaptureState::Complete ||
        current.state == WifiFrameCaptureState::Failed ||
        current.state == WifiFrameCaptureState::Idle;
    if (!initialized_ && !started_ && !promiscuous_ &&
        !eventLoopOwned_ && !ownsCallbackLifecycle &&
        !deviceMonitor_ && !channelMonitor_ &&
        !airspaceGuardMonitor_ && !authenticationCapture_) {
        return cleanupComplete_ && terminalCapture;
    }
    closeCallbackAdmission();
    WifiPassiveTeardownState teardown = teardownState(false);
    WifiPassiveTeardownAttempt teardownAttempt{};
    const bool wasDeviceMonitor = deviceMonitor_;
    const bool wasChannelMonitor = channelMonitor_;
    const bool wasAirspaceGuardMonitor = airspaceGuardMonitor_;
    const bool wasAuthenticationCapture = authenticationCapture_;
    if (promiscuous_) {
        const esp_err_t error = esp_wifi_set_promiscuous(false);
        if (error != ESP_OK) {
            applyWifiPassiveTeardownFailure(
                &teardown, &teardownAttempt,
                WifiPassiveTeardownStep::DisablePromiscuous, error);
            applyTeardownState(teardown);
            return false;
        } else {
            applyWifiPassiveTeardownSuccess(
                &teardown, &teardownAttempt,
                WifiPassiveTeardownStep::DisablePromiscuous);
        }
        applyTeardownState(teardown);
    }
    if (!waitForCallbackQuiescence()) {
        applyWifiPassiveTeardownFailure(
            &teardown, &teardownAttempt,
            WifiPassiveTeardownStep::AwaitCallbacks, ESP_ERR_TIMEOUT);
        applyTeardownState(teardown);
        return false;
    }
    applyWifiPassiveTeardownSuccess(
        &teardown, &teardownAttempt,
        WifiPassiveTeardownStep::AwaitCallbacks);
    applyTeardownState(teardown);
    if (endedUs == 0U) endedUs = current.startedUs;
    const bool wifiCleanup = endWifi(&teardown);
    if (!wifiCleanup) {
        // A physical teardown failure is part of the capture outcome. Record
        // it while the raw capture is still Running; Complete is irreversible
        // and must never be published ahead of stop/deinit/event-loop proof.
        portENTER_CRITICAL(&mux_);
        if (capture_.stats().state == WifiFrameCaptureState::Running) {
            capture_.fail(lastError_, endedUs);
        }
        portEXIT_CRITICAL(&mux_);
        if (wasDeviceMonitor) {
            portENTER_CRITICAL(&mux_);
            deviceStats_.active = promiscuous_;
            deviceStats_.cleanupComplete = false;
            portEXIT_CRITICAL(&mux_);
        }
        if (wasChannelMonitor) {
            portENTER_CRITICAL(&mux_);
            channelStats_.active = promiscuous_;
            channelStats_.cleanupComplete = false;
            portEXIT_CRITICAL(&mux_);
        }
        if (wasAirspaceGuardMonitor) {
            portENTER_CRITICAL(&mux_);
            airspaceGuardStats_.active = promiscuous_;
            airspaceGuardStats_.cleanupComplete = false;
            portEXIT_CRITICAL(&mux_);
        }
        if (wasAuthenticationCapture) {
            portENTER_CRITICAL(&mux_);
            authenticationStats_.active = promiscuous_;
            authenticationStats_.cleanupComplete = false;
            portEXIT_CRITICAL(&mux_);
        }
        return false;
    }
    if (!wifiPassiveCallbackOwnerReleasePermitted(teardown)) {
        cleanupComplete_ = false;
        portENTER_CRITICAL(&mux_);
        if (capture_.stats().state == WifiFrameCaptureState::Running) {
            capture_.fail(lastError_, endedUs);
        }
        portEXIT_CRITICAL(&mux_);
        return false;
    }
    // Raw terminal evidence is committed only after exact physical cleanup,
    // but still while the callback and logical-mode owner remain held.
    portENTER_CRITICAL(&mux_);
    if (capture_.stats().state == WifiFrameCaptureState::Running) {
        if (wifiPassiveCaptureCompletionPermitted(teardown)) {
            if (wasAirspaceGuardMonitor &&
                airspaceGuardStats_.framesReported != 0U &&
                capture_.size() == 0U &&
                airspaceGuardIdentityRetention_.size() == 0U) {
                std::array<std::uint8_t, 24> coverageProjection{};
                coverageProjection[0] = 0x40U;
                capture_.append(
                    coverageProjection.data(), coverageProjection.size(),
                    endedUs, -127,
                    currentChannel_ >= 1U && currentChannel_ <= 13U
                        ? currentChannel_ : 1U,
                    WifiFrameKind::Management, false);
            }
            capture_.complete(endedUs);
        } else {
            capture_.fail(lastError_, endedUs);
        }
    }
    portEXIT_CRITICAL(&mux_);
    deviceMonitor_ = false;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    authenticationCapture_ = false;
    // Exact physical teardown is global to the one Wi-Fi adapter. Mark every
    // view clean so a failed begin whose mode flag was already folded down can
    // also be recovered by a later stop() retry.
    portENTER_CRITICAL(&mux_);
    deviceStats_.active = false;
    deviceStats_.cleanupComplete = true;
    channelStats_.active = false;
    channelStats_.cleanupComplete = true;
    airspaceGuardStats_.active = false;
    airspaceGuardStats_.cleanupComplete = true;
    authenticationStats_.active = false;
    authenticationStats_.cleanupComplete = true;
    portEXIT_CRITICAL(&mux_);
    releaseCallbackOwner();
    releaseWifiPassiveCallbackOwner(&teardown);
    return true;
}

void BoardWifiPassiveCapture::reset() {
    if (!stop(0)) return;
    portENTER_CRITICAL(&mux_);
    capture_.reset();
    deviceQueue_.fill(apps::wifi::WifiDeviceObservation{});
    deviceQueueHead_ = 0;
    deviceQueueTail_ = 0;
    deviceQueueSize_ = 0;
    deviceStats_ = {};
    channelStats_ = {};
    airspaceGuardStats_ = {};
    authenticationStats_ = {};
    authenticationTarget_ = {};
    airspaceGuardIdentityRetention_.reset();
    channelLoad_.reset();
    portEXIT_CRITICAL(&mux_);
    deviceMonitor_ = false;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    authenticationCapture_ = false;
    currentChannel_ = 0;
    nextChannelUs_ = 0;
    channelLandedUs_ = 0;
    nextDeviceDataInspectUs_ = 0;
    channelDwellMs_ = 0;
    lastError_ = 0;
    resetBeginDiagnostics();
}

apps::capture::WifiFrameCaptureStats BoardWifiPassiveCapture::stats() const {
    portENTER_CRITICAL(&mux_);
    const apps::capture::WifiFrameCaptureStats result = capture_.stats();
    portEXIT_CRITICAL(&mux_);
    return result;
}

BoardWifiPassiveCapture::DeviceMonitorStats
BoardWifiPassiveCapture::deviceMonitorStats() const {
    portENTER_CRITICAL(&mux_);
    DeviceMonitorStats result = deviceStats_;
    result.active = deviceMonitor_ && promiscuous_;
    result.cleanupComplete = cleanupComplete_;
    portEXIT_CRITICAL(&mux_);
    return result;
}

BoardWifiPassiveCapture::ChannelMonitorStats
BoardWifiPassiveCapture::channelMonitorStats() const {
    portENTER_CRITICAL(&mux_);
    ChannelMonitorStats result = channelStats_;
    result.active = channelMonitor_ && promiscuous_;
    result.cleanupComplete = cleanupComplete_;
    portEXIT_CRITICAL(&mux_);
    return result;
}

BoardWifiPassiveCapture::AirspaceGuardMonitorStats
BoardWifiPassiveCapture::airspaceGuardMonitorStats() const {
    portENTER_CRITICAL(&mux_);
    AirspaceGuardMonitorStats result = airspaceGuardStats_;
    result.active = airspaceGuardMonitor_ && promiscuous_;
    result.framesRetained = capture_.stats().framesAccepted +
        airspaceGuardIdentityRetention_.size();
    result.cleanupComplete = airspaceGuardMonitor_
        ? cleanupComplete_ : airspaceGuardStats_.cleanupComplete;
    result.identityRetentionComplete = !result.active &&
        result.cleanupComplete && result.identityProfilesDropped == 0U &&
        result.invalidFrames == 0U;
    result.noiseRetentionComplete = !result.active &&
        result.cleanupComplete && result.noiseSamplesDropped == 0U &&
        result.invalidFrames == 0U;
    portEXIT_CRITICAL(&mux_);
    return result;
}

BoardWifiPassiveCapture::AuthenticationCaptureStats
BoardWifiPassiveCapture::authenticationCaptureStats() const {
    portENTER_CRITICAL(&mux_);
    AuthenticationCaptureStats result = authenticationStats_;
    result.active = authenticationCapture_ && promiscuous_;
    result.cleanupComplete = authenticationCapture_
        ? cleanupComplete_ : authenticationStats_.cleanupComplete;
    portEXIT_CRITICAL(&mux_);
    return result;
}

apps::wifi::WifiChannelLoadSnapshot
BoardWifiPassiveCapture::channelLoadSnapshot() const {
    portENTER_CRITICAL(&mux_);
    const auto result = channelLoad_.snapshot();
    portEXIT_CRITICAL(&mux_);
    return result;
}

std::uint8_t BoardWifiPassiveCapture::bestPrimaryChannel() const {
    portENTER_CRITICAL(&mux_);
    const std::uint8_t result = channelLoad_.bestPrimaryChannel();
    portEXIT_CRITICAL(&mux_);
    return result;
}

bool BoardWifiPassiveCapture::pollDevice(
    apps::wifi::WifiDeviceObservation* output) {
    if (output == nullptr) return false;
    portENTER_CRITICAL(&mux_);
    if (deviceQueueSize_ == 0U) {
        portEXIT_CRITICAL(&mux_);
        return false;
    }
    *output = deviceQueue_[deviceQueueTail_];
    deviceQueue_[deviceQueueTail_] = {};
    deviceQueueTail_ = (deviceQueueTail_ + 1U) % deviceQueue_.size();
    --deviceQueueSize_;
    portEXIT_CRITICAL(&mux_);
    return true;
}

bool BoardWifiPassiveCapture::lockDeviceChannel(std::uint8_t channel,
                                                std::uint64_t nowUs) {
    if (!deviceMonitor_ || !promiscuous_ || channel < 1U || channel > 13U ||
        nowUs == 0U) {
        return false;
    }
    if (currentChannel_ != channel && !changeChannel(channel, nowUs)) {
        return false;
    }
    deviceChannelLocked_ = true;
    return true;
}

void BoardWifiPassiveCapture::unlockDeviceChannel(std::uint64_t nowUs) {
    if (!deviceMonitor_ || !promiscuous_) return;
    deviceChannelLocked_ = false;
    nextChannelUs_ = nowUs == 0U ? 1U : nowUs;
}

void BoardWifiPassiveCapture::receive(void* buffer,
                                      wifi_promiscuous_pkt_type_t type) {
    BoardWifiPassiveCapture* instance = nullptr;
    std::uint32_t generation = 0U;
    portENTER_CRITICAL(&callbackMux_);
    if (active_ != nullptr && active_->callbackAdmissionOpen_) {
        instance = active_;
        generation = instance->callbackGeneration_;
        ++callbacksInFlight_;
    }
    portEXIT_CRITICAL(&callbackMux_);
    if (instance == nullptr) return;

    instance->accept(buffer, type, generation);

    portENTER_CRITICAL(&callbackMux_);
    if (callbacksInFlight_ != 0U) --callbacksInFlight_;
    portEXIT_CRITICAL(&callbackMux_);
}

void BoardWifiPassiveCapture::accept(void* buffer,
                                     wifi_promiscuous_pkt_type_t type,
                                     std::uint32_t generation) {
    portENTER_CRITICAL(&callbackMux_);
    const bool currentGeneration = callbackGeneration_ == generation;
    portEXIT_CRITICAL(&callbackMux_);
    if (!currentGeneration) return;
    if (buffer == nullptr) return;
    const auto* packet = static_cast<const wifi_promiscuous_pkt_t*>(buffer);
    WifiFrameKind kind = WifiFrameKind::Management;
    if (type == WIFI_PKT_CTRL) {
        kind = WifiFrameKind::Control;
    } else if (type == WIFI_PKT_DATA) {
        kind = WifiFrameKind::Data;
    } else if (type != WIFI_PKT_MGMT) {
        return;
    }
    const bool receiveValid = packet->rx_ctrl.rx_state == 0U;
    if (authenticationCapture_) {
        std::uint64_t receivedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (receivedUs == 0U) receivedUs = 1U;
        auto disposition = leshy1::services::auth::
            WifiAuthenticationIngressDisposition::Invalid;
        if (receiveValid && type == WIFI_PKT_DATA &&
            packet->rx_ctrl.channel >= 1U && packet->rx_ctrl.channel <= 13U &&
            packet->rx_ctrl.sig_len != 0U) {
            leshy1::domain::captures::WifiFrameView frame{};
            frame.monotonicUs = receivedUs;
            frame.capturedLength = packet->rx_ctrl.sig_len;
            frame.originalLength = packet->rx_ctrl.sig_len;
            frame.rssiDbm = packet->rx_ctrl.rssi;
            frame.channel = packet->rx_ctrl.channel;
            frame.kind = WifiFrameKind::Data;
            frame.fcsIncluded = true;
            frame.payload = packet->payload;
            disposition = leshy1::services::auth::
                classifyWifiAuthenticationIngress(
                    frame, authenticationTarget_);
        }
        portENTER_CRITICAL(&mux_);
        ++authenticationStats_.framesObserved;
        if (disposition == leshy1::services::auth::
                WifiAuthenticationIngressDisposition::Ignore) {
            ++authenticationStats_.framesIgnored;
        } else if (disposition == leshy1::services::auth::
                       WifiAuthenticationIngressDisposition::Invalid) {
            ++authenticationStats_.framesInvalid;
        } else {
            ++authenticationStats_.candidates;
            const bool retainedFrameIncludesFcs =
                packet->rx_ctrl.sig_len <= capture_.plan().snapLength;
            const bool retained = capture_.append(
                packet->payload, packet->rx_ctrl.sig_len, receivedUs,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                WifiFrameKind::Data, retainedFrameIncludesFcs);
            if (retained) {
                ++authenticationStats_.candidatesAccepted;
            } else {
                ++authenticationStats_.candidatesDropped;
            }
        }
        portEXIT_CRITICAL(&mux_);
        return;
    }
    if (channelMonitor_) {
        portENTER_CRITICAL(&mux_);
        ++channelStats_.framesReported;
        if (!receiveValid || packet->rx_ctrl.channel < 1U ||
            packet->rx_ctrl.channel > 13U) {
            ++channelStats_.invalidFrames;
        } else {
            channelLoad_.observe(packet->rx_ctrl.channel,
                                 estimatedFrameAirtimeUs(packet->rx_ctrl),
                                 packet->rx_ctrl.rssi);
        }
        portEXIT_CRITICAL(&mux_);
        return;
    }
    if (deviceMonitor_) {
        std::uint64_t receivedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (receivedUs == 0U) receivedUs = 1U;
        // Management advertisements are sparse and carry the richest device
        // identity, so inspect every one. Dense data traffic can otherwise
        // keep the ESP-IDF Wi-Fi task continuously busy and starve IDLE0 long
        // enough to trip the hardware Task WDT; sample that class at a fixed
        // 1 kHz ceiling instead.
        if (type == WIFI_PKT_DATA && receivedUs < nextDeviceDataInspectUs_) {
            portENTER_CRITICAL(&mux_);
            ++deviceStats_.framesReported;
            ++deviceStats_.dataFramesThrottled;
            portEXIT_CRITICAL(&mux_);
            return;
        }
        if (type == WIFI_PKT_DATA) {
            nextDeviceDataInspectUs_ =
                receivedUs + kDeviceDataInspectIntervalUs;
        }
        apps::wifi::WifiDeviceObservation observation{};
        const bool decoded = receiveValid &&
            apps::wifi::decodeWifiClientFrame(
                packet->payload, packet->rx_ctrl.sig_len,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                receivedUs,
                &observation);
        portENTER_CRITICAL(&mux_);
        ++deviceStats_.framesReported;
        if (!decoded) {
            ++deviceStats_.ignoredFrames;
        } else if (deviceQueueSize_ >= deviceQueue_.size()) {
            ++deviceStats_.clientsDropped;
        } else {
            deviceQueue_[deviceQueueHead_] = observation;
            deviceQueueHead_ = (deviceQueueHead_ + 1U) % deviceQueue_.size();
            ++deviceQueueSize_;
            ++deviceStats_.clientsAccepted;
        }
        portEXIT_CRITICAL(&mux_);
        return;
    }
    if (airspaceGuardMonitor_) {
        const bool disconnectCandidate = receiveValid &&
            leshy1::services::guard::isWifiDisconnectFrameCandidate(
                packet->payload, packet->rx_ctrl.sig_len);
        leshy1::services::guard::WifiIdentityRetentionKey identityKey{};
        const auto identityStatus = receiveValid
            ? leshy1::services::guard::wifiIdentityRetentionKey(
                  packet->payload, packet->rx_ctrl.sig_len, true,
                  &identityKey)
            : leshy1::services::guard::
                  WifiIdentityIngressStatus::NotAdvertisement;
        std::uint64_t receivedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (receivedUs == 0U) receivedUs = 1U;
        portENTER_CRITICAL(&mux_);
        ++airspaceGuardStats_.framesReported;
        if (receiveValid && packet->rx_ctrl.channel >= 1U &&
            packet->rx_ctrl.channel <= 13U &&
            packet->rx_ctrl.rssi >= -127 && packet->rx_ctrl.rssi <= 0 &&
            leshy1::services::guard::isWifiNoiseFloorCandidate(
                packet->rx_ctrl.noise_floor)) {
            ++airspaceGuardStats_.noiseSamplesObserved;
            if (airspaceGuardStats_.noiseSamplesRetained <
                airspaceGuardStats_.noiseSamples.size()) {
                auto& sample = airspaceGuardStats_.noiseSamples[
                    airspaceGuardStats_.noiseSamplesRetained++];
                sample.observationIndex =
                    static_cast<std::size_t>(
                        airspaceGuardStats_.framesReported - 1U);
                sample.monotonicUs = receivedUs;
                sample.channel = packet->rx_ctrl.channel;
                sample.rssiDbm = packet->rx_ctrl.rssi;
                sample.noiseFloorDbm = packet->rx_ctrl.noise_floor;
            } else {
                ++airspaceGuardStats_.noiseSamplesDropped;
            }
        }
        if (!receiveValid || packet->rx_ctrl.channel < 1U ||
            packet->rx_ctrl.channel > 13U || packet->rx_ctrl.sig_len < 2U) {
            ++airspaceGuardStats_.invalidFrames;
            ++airspaceGuardStats_.receiveInvalidFrames;
        } else if (disconnectCandidate) {
            if (!leshy1::services::guard::
                    wifiDisconnectRetentionSlotAvailable(
                        apps::capture::WifiFrameCapture::kFrameCapacity,
                        capture_.size(),
                        airspaceGuardStats_.disconnectFramesRetained)) {
                ++airspaceGuardStats_.disconnectFramesDropped;
                portEXIT_CRITICAL(&mux_);
                return;
            }
            const bool retainedFrameIncludesFcs =
                packet->rx_ctrl.sig_len <= capture_.plan().snapLength;
            const bool retained = capture_.append(
                packet->payload, packet->rx_ctrl.sig_len,
                receivedUs,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                WifiFrameKind::Management, retainedFrameIncludesFcs);
            if (retained) {
                ++airspaceGuardStats_.disconnectFramesRetained;
            } else {
                ++airspaceGuardStats_.disconnectFramesDropped;
            }
        } else if (identityStatus == leshy1::services::guard::
                       WifiIdentityIngressStatus::RetainableAdvertisement) {
            ++airspaceGuardStats_.identityAdvertisementsObserved;
            const auto disposition =
                airspaceGuardIdentityRetention_.accept(
                    identityKey, receivedUs, packet->rx_ctrl.rssi,
                    packet->rx_ctrl.channel);
            if (disposition == leshy1::services::guard::
                    WifiIdentityLiveRetentionDisposition::Retained) {
                ++airspaceGuardStats_.identityProfilesRetained;
                ++airspaceGuardStats_.identityProfilesProjected;
            } else if (disposition == leshy1::services::guard::
                           WifiIdentityLiveRetentionDisposition::Duplicate) {
                ++airspaceGuardStats_.identityProfilesDeduplicated;
            } else {
                ++airspaceGuardStats_.identityProfilesDropped;
            }
        } else if (leshy1::services::guard::wifiIdentityIngressMalformed(
                       identityStatus)) {
            ++airspaceGuardStats_.invalidFrames;
            if (identityStatus == leshy1::services::guard::
                    WifiIdentityIngressStatus::MalformedEnvelope) {
                ++airspaceGuardStats_.identityMalformedEnvelope;
            } else if (identityStatus == leshy1::services::guard::
                           WifiIdentityIngressStatus::MalformedAddressing) {
                ++airspaceGuardStats_.identityMalformedAddressing;
            } else {
                ++airspaceGuardStats_.identityMalformedElements;
            }
        } else {
            ++airspaceGuardStats_.ignoredFrames;
        }
        portEXIT_CRITICAL(&mux_);
        return;
    }
    portENTER_CRITICAL(&mux_);
    const bool retainedFrameIncludesFcs =
        packet->rx_ctrl.sig_len <= capture_.plan().snapLength;
    capture_.append(receiveValid ? packet->payload : nullptr,
                    packet->rx_ctrl.sig_len,
                    static_cast<std::uint64_t>(esp_timer_get_time()),
                    packet->rx_ctrl.rssi, packet->rx_ctrl.channel, kind,
                    retainedFrameIncludesFcs);
    portEXIT_CRITICAL(&mux_);
}

bool BoardWifiPassiveCapture::changeChannel(std::uint8_t channel,
                                            std::uint64_t nowUs) {
    const esp_err_t error =
        esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);
    if (error != ESP_OK) {
        lastError_ = error;
        if (!deviceMonitor_ && !channelMonitor_) {
            portENTER_CRITICAL(&mux_);
            capture_.fail(error, nowUs);
            portEXIT_CRITICAL(&mux_);
        }
        stop(nowUs);
        return true;
    }
    currentChannel_ = channel;
    nextChannelUs_ = nowUs +
        static_cast<std::uint64_t>(channelDwellMs_) * 1000ULL;
    return true;
}

bool BoardWifiPassiveCapture::endWifi(
    WifiPassiveTeardownState* teardown) {
    WifiPassiveTeardownState local = teardown == nullptr
        ? teardownState(callbacksQuiescent()) : *teardown;
    WifiPassiveTeardownAttempt attempt{};
    if (started_) {
        const esp_err_t error = esp_wifi_stop();
        if (error != ESP_OK) {
            applyWifiPassiveTeardownFailure(
                &local, &attempt, WifiPassiveTeardownStep::StopWifi, error);
            applyTeardownState(local);
            if (teardown != nullptr) *teardown = local;
            return false;
        }
        applyWifiPassiveTeardownSuccess(
            &local, &attempt, WifiPassiveTeardownStep::StopWifi);
        applyTeardownState(local);
    }
    if (initialized_) {
        const esp_err_t error = esp_wifi_deinit();
        if (error != ESP_OK) {
            applyWifiPassiveTeardownFailure(
                &local, &attempt, WifiPassiveTeardownStep::DeinitWifi, error);
            applyTeardownState(local);
            if (teardown != nullptr) *teardown = local;
            return false;
        }
        applyWifiPassiveTeardownSuccess(
            &local, &attempt, WifiPassiveTeardownStep::DeinitWifi);
        applyTeardownState(local);
    }
    if (eventLoopOwned_) {
        const esp_err_t error = esp_event_loop_delete_default();
        if (error != ESP_OK) {
            applyWifiPassiveTeardownFailure(
                &local, &attempt,
                WifiPassiveTeardownStep::DeleteEventLoop, error);
            applyTeardownState(local);
            if (teardown != nullptr) *teardown = local;
            return false;
        }
        applyWifiPassiveTeardownSuccess(
            &local, &attempt, WifiPassiveTeardownStep::DeleteEventLoop);
        applyTeardownState(local);
    }
    if (teardown != nullptr) *teardown = local;
    cleanupComplete_ = wifiPassiveCleanupProven(local);
    return cleanupComplete_;
}

}  // namespace leshy1::platform::arduino
