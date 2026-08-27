#include "BoardWifiPassiveCapture.h"

#include <esp_event.h>
#include <esp_timer.h>
#include <esp_wifi.h>

#include "services/guard/AirspaceGuard.h"

namespace leshy1::platform::arduino {

namespace {

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

BoardWifiPassiveCapture* BoardWifiPassiveCapture::active_ = nullptr;

bool BoardWifiPassiveCapture::begin(
    const apps::capture::WifiFrameCapturePlan& plan,
    std::uint64_t startedUs) {
    return beginCapture(plan, startedUs, false);
}

bool BoardWifiPassiveCapture::beginAirspaceGuardMonitor(
    std::uint64_t startedUs, std::uint32_t durationMs,
    std::uint16_t channelDwellMs) {
    apps::capture::WifiFrameCapturePlan plan{};
    plan.durationMs = durationMs;
    plan.channelDwellMs = channelDwellMs;
    plan.maximumFrames = static_cast<std::uint16_t>(
        apps::capture::WifiFrameCapture::kFrameCapacity);
    const bool started = beginCapture(plan, startedUs, true);
    if (!started) {
        airspaceGuardMonitor_ = false;
        airspaceGuardStats_.active = false;
        airspaceGuardStats_.cleanupComplete = cleanupComplete_;
    }
    return started;
}

bool BoardWifiPassiveCapture::beginCapture(
    const apps::capture::WifiFrameCapturePlan& plan,
    std::uint64_t startedUs, bool airspaceGuardMonitor) {
    if (initialized_ || started_ || promiscuous_ || active_ != nullptr ||
        !apps::capture::validateWifiFrameCapturePlan(plan)) {
        return false;
    }
    capture_.reset();
    if (!capture_.begin(plan, startedUs)) return false;
    deviceMonitor_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = airspaceGuardMonitor;
    airspaceGuardStats_ = {};
    airspaceGuardIdentityKeys_.fill(
        services::guard::WifiIdentityRetentionKey{});
    airspaceGuardIdentityKeyCount_ = 0U;
    airspaceGuardStats_.cleanupComplete = !airspaceGuardMonitor;
    cleanupComplete_ = false;
    lastError_ = 0;

    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
    } else if (error != ESP_ERR_INVALID_STATE) {
        lastError_ = error;
        capture_.fail(error, startedUs);
        cleanupComplete_ = true;
        return false;
    }

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        capture_.fail(error, startedUs);
        endWifi();
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        capture_.fail(error, startedUs);
        endWifi();
        return false;
    }
    started_ = true;

    currentChannel_ = plan.channel == 0U ? 1U : plan.channel;
    error = esp_wifi_set_channel(currentChannel_, WIFI_SECOND_CHAN_NONE);
    wifi_promiscuous_filter_t filter{};
    filter.filter_mask = airspaceGuardMonitor_
        ? WIFI_PROMIS_FILTER_MASK_MGMT
        : WIFI_PROMIS_FILTER_MASK_MGMT |
              WIFI_PROMIS_FILTER_MASK_CTRL |
              WIFI_PROMIS_FILTER_MASK_DATA;
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_filter(&filter);
    if (error == ESP_OK) error = esp_wifi_set_promiscuous_rx_cb(&receive);
    if (error != ESP_OK) {
        lastError_ = error;
        capture_.fail(error, startedUs);
        endWifi();
        return false;
    }

    active_ = this;
    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        active_ = nullptr;
        lastError_ = error;
        portENTER_CRITICAL(&mux_);
        capture_.fail(error, startedUs);
        portEXIT_CRITICAL(&mux_);
        endWifi();
        return false;
    }
    promiscuous_ = true;
    if (airspaceGuardMonitor_) airspaceGuardStats_.active = true;
    channelDwellMs_ = plan.channelDwellMs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(plan.channelDwellMs) * 1000ULL;
    return true;
}

bool BoardWifiPassiveCapture::beginDeviceMonitor(
    std::uint64_t startedUs, std::uint16_t channelDwellMs) {
    if (initialized_ || started_ || promiscuous_ || active_ != nullptr ||
        startedUs == 0U || channelDwellMs < 50U || channelDwellMs > 1000U) {
        return false;
    }
    capture_.reset();
    deviceQueue_.fill(apps::wifi::WifiDeviceObservation{});
    deviceQueueHead_ = 0;
    deviceQueueTail_ = 0;
    deviceQueueSize_ = 0;
    deviceStats_ = {};
    deviceStats_.cleanupComplete = false;
    deviceMonitor_ = true;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
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
        return false;
    }

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
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
        return false;
    }

    active_ = this;
    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        active_ = nullptr;
        lastError_ = error;
        endWifi();
        deviceMonitor_ = false;
        deviceStats_.cleanupComplete = cleanupComplete_;
        return false;
    }
    promiscuous_ = true;
    channelDwellMs_ = channelDwellMs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(channelDwellMs_) * 1000ULL;
    channelLandedUs_ = startedUs;
    deviceStats_.active = true;
    return true;
}

bool BoardWifiPassiveCapture::beginChannelMonitor(
    std::uint64_t startedUs, std::uint16_t channelDwellMs) {
    if (initialized_ || started_ || promiscuous_ || active_ != nullptr ||
        startedUs == 0U || channelDwellMs < 50U || channelDwellMs > 1000U) {
        return false;
    }
    capture_.reset();
    channelLoad_.reset();
    channelStats_ = {};
    channelStats_.cleanupComplete = false;
    deviceMonitor_ = false;
    channelMonitor_ = true;
    airspaceGuardMonitor_ = false;
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
        return false;
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;
    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
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
        return false;
    }
    active_ = this;
    error = esp_wifi_set_promiscuous(true);
    if (error != ESP_OK) {
        active_ = nullptr;
        lastError_ = error;
        endWifi();
        channelMonitor_ = false;
        channelStats_.cleanupComplete = cleanupComplete_;
        return false;
    }
    promiscuous_ = true;
    channelDwellMs_ = channelDwellMs;
    channelLandedUs_ = startedUs;
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(channelDwellMs_) * 1000ULL;
    channelStats_.active = true;
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
    if (!initialized_ && !started_ && !promiscuous_) {
        return current.state == WifiFrameCaptureState::Complete ||
               current.state == WifiFrameCaptureState::Failed ||
               current.state == WifiFrameCaptureState::Idle;
    }
    active_ = nullptr;
    const bool wasDeviceMonitor = deviceMonitor_;
    const bool wasChannelMonitor = channelMonitor_;
    const bool wasAirspaceGuardMonitor = airspaceGuardMonitor_;
    bool complete = true;
    if (promiscuous_) {
        const esp_err_t error = esp_wifi_set_promiscuous(false);
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    promiscuous_ = false;
    if (endedUs == 0U) endedUs = current.startedUs;
    portENTER_CRITICAL(&mux_);
    if (capture_.stats().state == WifiFrameCaptureState::Running) {
        if (complete) {
            capture_.complete(endedUs);
        } else {
            capture_.fail(lastError_, endedUs);
        }
    }
    portEXIT_CRITICAL(&mux_);
    const bool wifiCleanup = endWifi();
    deviceMonitor_ = false;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    if (wasDeviceMonitor) {
        portENTER_CRITICAL(&mux_);
        deviceStats_.active = false;
        deviceStats_.cleanupComplete = wifiCleanup && complete;
        portEXIT_CRITICAL(&mux_);
    }
    if (wasChannelMonitor) {
        portENTER_CRITICAL(&mux_);
        channelStats_.active = false;
        channelStats_.cleanupComplete = wifiCleanup && complete;
        portEXIT_CRITICAL(&mux_);
    }
    if (wasAirspaceGuardMonitor) {
        portENTER_CRITICAL(&mux_);
        airspaceGuardStats_.active = false;
        airspaceGuardStats_.cleanupComplete = wifiCleanup && complete;
        portEXIT_CRITICAL(&mux_);
    }
    return wifiCleanup && complete;
}

void BoardWifiPassiveCapture::reset() {
    stop(0);
    portENTER_CRITICAL(&mux_);
    capture_.reset();
    deviceQueue_.fill(apps::wifi::WifiDeviceObservation{});
    deviceQueueHead_ = 0;
    deviceQueueTail_ = 0;
    deviceQueueSize_ = 0;
    deviceStats_ = {};
    channelStats_ = {};
    airspaceGuardStats_ = {};
    airspaceGuardIdentityKeys_.fill(
        services::guard::WifiIdentityRetentionKey{});
    airspaceGuardIdentityKeyCount_ = 0U;
    channelLoad_.reset();
    portEXIT_CRITICAL(&mux_);
    deviceMonitor_ = false;
    deviceChannelLocked_ = false;
    channelMonitor_ = false;
    airspaceGuardMonitor_ = false;
    currentChannel_ = 0;
    nextChannelUs_ = 0;
    channelLandedUs_ = 0;
    channelDwellMs_ = 0;
    lastError_ = 0;
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
    result.framesRetained = capture_.stats().framesAccepted;
    result.cleanupComplete = airspaceGuardMonitor_
        ? cleanupComplete_ : airspaceGuardStats_.cleanupComplete;
    result.identityRetentionComplete = !result.active &&
        result.cleanupComplete && result.identityProfilesDropped == 0U &&
        result.invalidFrames == 0U;
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
    BoardWifiPassiveCapture* instance = active_;
    if (instance != nullptr) instance->accept(buffer, type);
}

void BoardWifiPassiveCapture::accept(void* buffer,
                                     wifi_promiscuous_pkt_type_t type) {
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
        apps::wifi::WifiDeviceObservation observation{};
        const bool decoded = receiveValid &&
            apps::wifi::decodeWifiClientFrame(
                packet->payload, packet->rx_ctrl.sig_len,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                static_cast<std::uint64_t>(esp_timer_get_time()),
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
        if (!receiveValid || packet->rx_ctrl.channel < 1U ||
            packet->rx_ctrl.channel > 13U || packet->rx_ctrl.sig_len < 2U) {
            ++airspaceGuardStats_.invalidFrames;
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
            const bool retained = capture_.append(
                packet->payload, packet->rx_ctrl.sig_len,
                receivedUs,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                WifiFrameKind::Management, true);
            if (retained) {
                ++airspaceGuardStats_.disconnectFramesRetained;
            } else {
                ++airspaceGuardStats_.disconnectFramesDropped;
            }
        } else if (identityStatus == leshy1::services::guard::
                       WifiIdentityIngressStatus::RetainableAdvertisement) {
            ++airspaceGuardStats_.identityAdvertisementsObserved;
            if (packet->rx_ctrl.sig_len > capture_.plan().snapLength) {
                ++airspaceGuardStats_.identityProfilesDropped;
                portEXIT_CRITICAL(&mux_);
                return;
            }
            bool duplicate = false;
            for (std::size_t index = 0U;
                 index < airspaceGuardIdentityKeyCount_; ++index) {
                if (leshy1::services::guard::sameWifiIdentityRetentionKey(
                        airspaceGuardIdentityKeys_[index], identityKey)) {
                    duplicate = true;
                    break;
                }
            }
            if (duplicate) {
                ++airspaceGuardStats_.identityProfilesDeduplicated;
                portEXIT_CRITICAL(&mux_);
                return;
            }
            if (!leshy1::services::guard::wifiIdentityRetentionSlotAvailable(
                    apps::capture::WifiFrameCapture::kFrameCapacity,
                    capture_.size(),
                    airspaceGuardStats_.disconnectFramesRetained,
                    airspaceGuardIdentityKeyCount_)) {
                ++airspaceGuardStats_.identityProfilesDropped;
                portEXIT_CRITICAL(&mux_);
                return;
            }
            const bool retained = capture_.append(
                packet->payload, packet->rx_ctrl.sig_len, receivedUs,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                WifiFrameKind::Management, true);
            if (retained) {
                airspaceGuardIdentityKeys_[airspaceGuardIdentityKeyCount_++] =
                    identityKey;
                ++airspaceGuardStats_.identityProfilesRetained;
            } else {
                ++airspaceGuardStats_.identityProfilesDropped;
            }
        } else if (identityStatus == leshy1::services::guard::
                       WifiIdentityIngressStatus::MalformedAdvertisement) {
            ++airspaceGuardStats_.invalidFrames;
        } else if (capture_.size() == 0U) {
            const bool retained = capture_.append(
                packet->payload, packet->rx_ctrl.sig_len, receivedUs,
                packet->rx_ctrl.rssi, packet->rx_ctrl.channel,
                WifiFrameKind::Management, true);
            if (!retained) ++airspaceGuardStats_.invalidFrames;
        } else {
            ++airspaceGuardStats_.ignoredFrames;
        }
        portEXIT_CRITICAL(&mux_);
        return;
    }
    portENTER_CRITICAL(&mux_);
    capture_.append(receiveValid ? packet->payload : nullptr,
                    packet->rx_ctrl.sig_len,
                    static_cast<std::uint64_t>(esp_timer_get_time()),
                    packet->rx_ctrl.rssi, packet->rx_ctrl.channel, kind, true);
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

bool BoardWifiPassiveCapture::endWifi() {
    bool complete = true;
    if (started_) {
        const esp_err_t error = esp_wifi_stop();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    started_ = false;
    if (initialized_) {
        const esp_err_t error = esp_wifi_deinit();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    initialized_ = false;
    nvsDisabled_ = false;
    volatileStorageOnly_ = false;
    if (eventLoopOwned_) {
        const esp_err_t error = esp_event_loop_delete_default();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    eventLoopOwned_ = false;
    cleanupComplete_ = complete;
    return complete;
}

}  // namespace leshy1::platform::arduino
