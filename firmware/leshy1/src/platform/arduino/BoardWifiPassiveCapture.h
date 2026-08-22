#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>

#include "apps/capture/WifiFrameCapture.h"
#include "apps/wifi/WifiChannelLoad.h"
#include "apps/wifi/WifiDeviceCatalog.h"

namespace leshy1::platform::arduino {

class BoardWifiPassiveCapture final {
public:
    struct DeviceMonitorStats final {
        std::uint32_t framesReported = 0;
        std::uint32_t clientsAccepted = 0;
        std::uint32_t clientsDropped = 0;
        std::uint32_t ignoredFrames = 0;
        std::uint32_t channelHops = 0;
        bool active = false;
        bool cleanupComplete = true;
    };

    struct ChannelMonitorStats final {
        std::uint32_t framesReported = 0;
        std::uint32_t invalidFrames = 0;
        std::uint32_t channelHops = 0;
        bool active = false;
        bool cleanupComplete = true;
    };

    ~BoardWifiPassiveCapture() { stop(0); }

    bool begin(const apps::capture::WifiFrameCapturePlan& plan,
               std::uint64_t startedUs);
    bool beginDeviceMonitor(std::uint64_t startedUs,
                            std::uint16_t channelDwellMs = 120U);
    bool beginChannelMonitor(std::uint64_t startedUs,
                             std::uint16_t channelDwellMs = 120U);
    bool service(std::uint64_t nowUs);
    bool stop(std::uint64_t endedUs);
    void reset();

    apps::capture::WifiFrameCaptureStats stats() const;
    DeviceMonitorStats deviceMonitorStats() const;
    ChannelMonitorStats channelMonitorStats() const;
    apps::wifi::WifiChannelLoadSnapshot channelLoadSnapshot() const;
    std::uint8_t bestPrimaryChannel() const;
    bool pollDevice(apps::wifi::WifiDeviceObservation* output);
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
    static constexpr std::size_t kDeviceQueueCapacity = 64;
    std::array<apps::wifi::WifiDeviceObservation,
               kDeviceQueueCapacity> deviceQueue_{};
    DeviceMonitorStats deviceStats_{};
    ChannelMonitorStats channelStats_{};
    apps::wifi::WifiChannelLoad channelLoad_{};
    std::size_t deviceQueueHead_ = 0;
    std::size_t deviceQueueTail_ = 0;
    std::size_t deviceQueueSize_ = 0;
    bool deviceMonitor_ = false;
    bool channelMonitor_ = false;
    bool initialized_ = false;
    bool started_ = false;
    bool promiscuous_ = false;
    bool eventLoopOwned_ = false;
    bool cleanupComplete_ = true;
    bool nvsDisabled_ = false;
    bool volatileStorageOnly_ = false;
    std::uint8_t currentChannel_ = 0;
    std::uint64_t nextChannelUs_ = 0;
    std::uint64_t channelLandedUs_ = 0;
    std::uint16_t channelDwellMs_ = 0;
    int lastError_ = 0;
};

}  // namespace leshy1::platform::arduino
