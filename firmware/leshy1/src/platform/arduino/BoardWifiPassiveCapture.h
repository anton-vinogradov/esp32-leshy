#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>

#include "apps/capture/WifiFrameCapture.h"
#include "apps/wifi/WifiChannelLoad.h"
#include "apps/wifi/WifiDeviceCatalog.h"
#include "platform/arduino/BoardWifiPassiveInitConfig.h"
#include "platform/arduino/WifiPassiveCaptureTeardownPolicy.h"
#include "services/auth/WifiAuthenticationCapture.h"
#include "services/guard/AirspaceGuard.h"

namespace leshy1::platform::arduino {

enum class BoardWifiPassiveBeginFailureStage : std::uint8_t {
    None,
    Admission,
    CaptureBegin,
    EventLoopCreate,
    WifiInit,
    SetStorage,
    SetMode,
    SetIdentity,
    WifiStart,
    SetChannel,
    SetFilter,
    SetCallback,
    EnablePromiscuous,
};

const char* boardWifiPassiveBeginFailureStageName(
    BoardWifiPassiveBeginFailureStage stage);

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

    struct AirspaceGuardMonitorStats final {
        static constexpr std::size_t kDisconnectRetentionCapacity =
            services::guard::kWifiDisconnectLiveRetentionCapacity;
        static constexpr std::size_t kIdentityRetentionCapacity =
            services::guard::kWifiIdentityLiveRetentionCapacity;
        static constexpr std::size_t kNoiseRetentionCapacity =
            services::guard::kWifiNoiseFloorLiveRetentionCapacity;

        std::uint32_t framesReported = 0;
        std::uint32_t framesRetained = 0;
        std::uint32_t disconnectFramesRetained = 0;
        std::uint32_t disconnectFramesDropped = 0;
        std::uint32_t identityAdvertisementsObserved = 0;
        std::uint32_t identityProfilesRetained = 0;
        std::uint32_t identityProfilesProjected = 0;
        std::uint32_t identityProfilesDeduplicated = 0;
        std::uint32_t identityProfilesDropped = 0;
        std::uint32_t identityMalformedEnvelope = 0;
        std::uint32_t identityMalformedAddressing = 0;
        std::uint32_t identityMalformedElements = 0;
        std::array<services::guard::WifiNoiseFloorSample,
                   kNoiseRetentionCapacity> noiseSamples{};
        std::uint32_t noiseSamplesObserved = 0;
        std::uint32_t noiseSamplesRetained = 0;
        std::uint32_t noiseSamplesDropped = 0;
        std::uint32_t invalidFrames = 0;
        std::uint32_t receiveInvalidFrames = 0;
        std::uint32_t ignoredFrames = 0;
        std::uint32_t channelHops = 0;
        bool active = false;
        bool cleanupComplete = true;
        bool identityRetentionComplete = false;
        bool noiseRetentionComplete = false;
    };

    struct AuthenticationCaptureStats final {
        std::uint32_t framesObserved = 0;
        std::uint32_t framesIgnored = 0;
        std::uint32_t framesInvalid = 0;
        std::uint32_t candidates = 0;
        std::uint32_t candidatesAccepted = 0;
        std::uint32_t candidatesDropped = 0;
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
    bool beginAirspaceGuardMonitor(std::uint64_t startedUs,
                                   std::uint32_t durationMs = 10000U,
                                   std::uint16_t channelDwellMs = 120U);
    bool beginAuthenticationCapture(
        const apps::capture::WifiFrameCapturePlan& plan,
        const std::array<std::uint8_t, 6>& targetAccessPoint,
        std::uint64_t startedUs);
    bool service(std::uint64_t nowUs);
    bool stop(std::uint64_t endedUs);
    void reset();

    apps::capture::WifiFrameCaptureStats stats() const;
    DeviceMonitorStats deviceMonitorStats() const;
    ChannelMonitorStats channelMonitorStats() const;
    AirspaceGuardMonitorStats airspaceGuardMonitorStats() const;
    AuthenticationCaptureStats authenticationCaptureStats() const;
    apps::wifi::WifiChannelLoadSnapshot channelLoadSnapshot() const;
    std::uint8_t bestPrimaryChannel() const;
    bool pollDevice(apps::wifi::WifiDeviceObservation* output);
    bool lockDeviceChannel(std::uint8_t channel, std::uint64_t nowUs);
    void unlockDeviceChannel(std::uint64_t nowUs);
    bool deviceChannelLocked() const { return deviceChannelLocked_; }
    const apps::capture::WifiFrameCapture& capture() const { return capture_; }
    const services::guard::WifiIdentityProjectionRetention&
    airspaceGuardIdentitySource() const {
        return airspaceGuardIdentityRetention_;
    }
    std::uint8_t currentChannel() const { return currentChannel_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    bool nvsDisabled() const { return nvsDisabled_; }
    bool volatileStorageOnly() const { return volatileStorageOnly_; }
    int lastError() const { return lastError_; }
    int beginDriverError() const { return beginDriverError_; }
    BoardWifiPassiveBeginFailureStage beginFailureStage() const {
        return beginFailureStage_;
    }
    std::uint32_t heapFreeBeforeInit() const {
        return heapFreeBeforeInit_;
    }
    std::uint32_t heapLargestBeforeInit() const {
        return heapLargestBeforeInit_;
    }

private:
    bool beginCapture(const apps::capture::WifiFrameCapturePlan& plan,
                      std::uint64_t startedUs, bool airspaceGuardMonitor,
                      bool authenticationCapture = false,
                      const std::array<std::uint8_t, 6>*
                          authenticationTarget = nullptr);
    static void receive(void* buffer, wifi_promiscuous_pkt_type_t type);
    void accept(void* buffer, wifi_promiscuous_pkt_type_t type,
                std::uint32_t generation);
    bool reserveCallbackOwner();
    void releaseCallbackOwner();
    void openCallbackAdmission();
    void closeCallbackAdmission();
    bool waitForCallbackQuiescence();
    bool callbacksQuiescent() const;
    void releaseFailedBegin();
    bool changeChannel(std::uint8_t channel, std::uint64_t nowUs);
    WifiPassiveTeardownState teardownState(bool callbacksAreQuiescent) const;
    void applyTeardownState(const WifiPassiveTeardownState& state);
    bool endWifi(WifiPassiveTeardownState* teardown = nullptr);
    void resetBeginDiagnostics();
    void recordBeginFailure(BoardWifiPassiveBeginFailureStage stage,
                            int error);
    void snapshotHeapBeforeInit();

    static BoardWifiPassiveCapture* active_;
    static portMUX_TYPE callbackMux_;
    static std::uint32_t callbacksInFlight_;
    mutable portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
    apps::capture::WifiFrameCapture capture_{};
    static constexpr std::size_t kDeviceQueueCapacity = 64;
    std::array<apps::wifi::WifiDeviceObservation,
               kDeviceQueueCapacity> deviceQueue_{};
    DeviceMonitorStats deviceStats_{};
    ChannelMonitorStats channelStats_{};
    AirspaceGuardMonitorStats airspaceGuardStats_{};
    AuthenticationCaptureStats authenticationStats_{};
    std::array<std::uint8_t, 6> authenticationTarget_{};
    services::guard::WifiIdentityProjectionRetention
        airspaceGuardIdentityRetention_{};
    apps::wifi::WifiChannelLoad channelLoad_{};
    std::size_t deviceQueueHead_ = 0;
    std::size_t deviceQueueTail_ = 0;
    std::size_t deviceQueueSize_ = 0;
    bool deviceMonitor_ = false;
    bool deviceChannelLocked_ = false;
    bool channelMonitor_ = false;
    bool airspaceGuardMonitor_ = false;
    bool authenticationCapture_ = false;
    bool initialized_ = false;
    bool started_ = false;
    bool promiscuous_ = false;
    bool eventLoopOwned_ = false;
    bool cleanupComplete_ = true;
    bool nvsDisabled_ = false;
    bool volatileStorageOnly_ = false;
    std::uint32_t callbackGeneration_ = 0;
    bool callbackAdmissionOpen_ = false;
    std::uint8_t currentChannel_ = 0;
    std::uint64_t nextChannelUs_ = 0;
    std::uint64_t channelLandedUs_ = 0;
    std::uint16_t channelDwellMs_ = 0;
    int lastError_ = 0;
    int beginDriverError_ = 0;
    BoardWifiPassiveBeginFailureStage beginFailureStage_ =
        BoardWifiPassiveBeginFailureStage::None;
    std::uint32_t heapFreeBeforeInit_ = 0;
    std::uint32_t heapLargestBeforeInit_ = 0;
};

}  // namespace leshy1::platform::arduino
