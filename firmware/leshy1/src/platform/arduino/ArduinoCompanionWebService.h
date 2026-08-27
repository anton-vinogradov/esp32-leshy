#pragma once

#include <Arduino.h>
#include <NetworkClient.h>
#include <NetworkServer.h>

#include <esp_err.h>
#include <esp_netif.h>

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/companion/CompanionConnectivity.h"
#include "services/companion/CompanionProtocol.h"

namespace leshy1::platform::arduino {

using CompanionWebFrameHandler = bool (*)(
    char* request, std::size_t requestLength, char* response,
    std::size_t responseCapacity, std::size_t* responseLength,
    void* context);

class ArduinoCompanionWebService final {
public:
    static constexpr std::size_t kMaximumHeaderBytes = 768;
    static constexpr std::size_t kRequestCapacity =
        kMaximumHeaderBytes + services::companion::kCompanionMaxFrameBytes;
    static constexpr std::uint64_t kClientDeadlineUs = 3000000ULL;
    static constexpr int kStaticRxBuffers = 2;
    static constexpr int kDynamicRxBuffers = 1;
    // The pinned ESP-IDF libraries are compiled for static TX buffers. Six
    // buffers cover the bounded 6.6 KiB index response without stalling the
    // supervised main loop while the single local client acknowledges it.
    static constexpr int kStaticTxBuffers = 6;
    static constexpr int kDynamicTxBuffers = 0;
    static constexpr int kRxManagementBuffers = 1;
    static constexpr int kCacheTxBuffers = 1;
    // ESP-IDF rejects values below six during driver initialization.
    static constexpr int kManagementShortBuffers = 6;
    static constexpr std::uint32_t kApReadyTimeoutMs = 2000;
    static constexpr std::uint32_t kApReadyPollMs = 10;

    enum class BeginStage : std::uint8_t {
        Idle,
        NetworkCore,
        EventLoop,
        Netif,
        WifiHandlers,
        WifiInit,
        RamStorage,
        ApMode,
        ApConfig,
        WifiStart,
        Dhcp,
        Server,
        Ready,
    };

    ArduinoCompanionWebService() : server_(80, 1) {}

    bool prepareNetworkCore();
    bool begin(
        const services::companion::CompanionLocalCredentials& credentials);
    bool stop();
    bool poll(std::uint64_t nowUs, bool deviceSessionAuthorized,
              CompanionWebFrameHandler handler, void* context);

    bool active() const { return active_; }
    std::uint32_t requestsHandled() const { return requestsHandled_; }
    std::uint32_t requestsRejected() const { return requestsRejected_; }
    bool networkCoreReady() const { return networkCoreReady_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    BeginStage beginStage() const { return beginStage_; }
    esp_err_t lastError() const { return lastError_; }
    std::uint32_t heapFreeBeforeBegin() const { return heapFreeBeforeBegin_; }
    std::uint32_t heapLargestBeforeBegin() const {
        return heapLargestBeforeBegin_;
    }
    std::uint32_t heapFreeAfterBegin() const { return heapFreeAfterBegin_; }
    std::uint32_t heapFreeAfterStop() const { return heapFreeAfterStop_; }
    bool apIpv4Ready() const;
    bool dhcpServerStarted() const;
    std::uint16_t associatedStations() const;

    static const char* beginStageName(BeginStage stage);

private:
    void resetClient();
    void sendResponse(std::uint16_t status, const char* contentType,
                      const char* body, std::size_t bodyLength);
    bool processRequest(bool deviceSessionAuthorized,
                        CompanionWebFrameHandler handler, void* context);
    bool cleanupRuntime();
    bool failBegin(BeginStage stage, esp_err_t error);

    NetworkServer server_;
    NetworkClient client_;
    std::array<char, kRequestCapacity + 1U> request_{};
    std::array<char, kMaximumHeaderBytes + 1U> header_{};
    std::array<char, services::companion::kCompanionMaxFrameBytes + 1U>
        response_{};
    std::size_t requestLength_ = 0;
    std::uint64_t clientStartedUs_ = 0;
    std::uint32_t requestsHandled_ = 0;
    std::uint32_t requestsRejected_ = 0;
    esp_netif_t* apNetif_ = nullptr;
    esp_err_t lastError_ = ESP_OK;
    BeginStage beginStage_ = BeginStage::Idle;
    std::uint32_t heapFreeBeforeBegin_ = 0;
    std::uint32_t heapLargestBeforeBegin_ = 0;
    std::uint32_t heapFreeAfterBegin_ = 0;
    std::uint32_t heapFreeAfterStop_ = 0;
    bool networkCoreReady_ = false;
    bool eventLoopOwned_ = false;
    bool wifiNetifAttached_ = false;
    bool wifiInitialized_ = false;
    bool wifiStarted_ = false;
    bool cleanupComplete_ = true;
    bool active_ = false;
};

}  // namespace leshy1::platform::arduino
