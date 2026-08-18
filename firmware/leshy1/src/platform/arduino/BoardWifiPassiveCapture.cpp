#include "BoardWifiPassiveCapture.h"

#include <esp_event.h>
#include <esp_timer.h>
#include <esp_wifi.h>

namespace leshy1::platform::arduino {

using apps::capture::WifiFrameCaptureState;
using apps::capture::WifiFrameKind;

BoardWifiPassiveCapture* BoardWifiPassiveCapture::active_ = nullptr;

bool BoardWifiPassiveCapture::begin(
    const apps::capture::WifiFrameCapturePlan& plan,
    std::uint64_t startedUs) {
    if (initialized_ || started_ || promiscuous_ || active_ != nullptr ||
        !apps::capture::validateWifiFrameCapturePlan(plan)) {
        return false;
    }
    capture_.reset();
    if (!capture_.begin(plan, startedUs)) return false;
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
    filter.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT |
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
    nextChannelUs_ = startedUs +
        static_cast<std::uint64_t>(plan.channelDwellMs) * 1000ULL;
    return true;
}

bool BoardWifiPassiveCapture::service(std::uint64_t nowUs) {
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
        return changeChannel(next, nowUs);
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
    return endWifi() && complete;
}

void BoardWifiPassiveCapture::reset() {
    stop(0);
    portENTER_CRITICAL(&mux_);
    capture_.reset();
    portEXIT_CRITICAL(&mux_);
    currentChannel_ = 0;
    nextChannelUs_ = 0;
    lastError_ = 0;
}

apps::capture::WifiFrameCaptureStats BoardWifiPassiveCapture::stats() const {
    portENTER_CRITICAL(&mux_);
    const apps::capture::WifiFrameCaptureStats result = capture_.stats();
    portEXIT_CRITICAL(&mux_);
    return result;
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
        portENTER_CRITICAL(&mux_);
        capture_.fail(error, nowUs);
        portEXIT_CRITICAL(&mux_);
        stop(nowUs);
        return true;
    }
    currentChannel_ = channel;
    nextChannelUs_ = nowUs +
        static_cast<std::uint64_t>(capture_.plan().channelDwellMs) * 1000ULL;
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
