#pragma once

#include <cstdint>

#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>

#include "apps/capture/WifiFrameCapture.h"

namespace leshy1::platform::arduino {

class BoardWifiPassiveCapture final {
public:
    ~BoardWifiPassiveCapture() { stop(0); }

    bool begin(const apps::capture::WifiFrameCapturePlan& plan,
               std::uint64_t startedUs);
    bool service(std::uint64_t nowUs);
    bool stop(std::uint64_t endedUs);
    void reset();

    apps::capture::WifiFrameCaptureStats stats() const;
    const apps::capture::WifiFrameCapture& capture() const { return capture_; }
    std::uint8_t currentChannel() const { return currentChannel_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    bool nvsDisabled() const { return nvsDisabled_; }
    bool volatileStorageOnly() const { return volatileStorageOnly_; }
    int lastError() const { return lastError_; }

private:
    static void receive(void* buffer, wifi_promiscuous_pkt_type_t type);
    void accept(void* buffer, wifi_promiscuous_pkt_type_t type);
    bool changeChannel(std::uint8_t channel, std::uint64_t nowUs);
    bool endWifi();

    static BoardWifiPassiveCapture* active_;
    mutable portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
    apps::capture::WifiFrameCapture capture_{};
    bool initialized_ = false;
    bool started_ = false;
    bool promiscuous_ = false;
    bool eventLoopOwned_ = false;
    bool cleanupComplete_ = true;
    bool nvsDisabled_ = false;
    bool volatileStorageOnly_ = false;
    std::uint8_t currentChannel_ = 0;
    std::uint64_t nextChannelUs_ = 0;
    int lastError_ = 0;
};

}  // namespace leshy1::platform::arduino
