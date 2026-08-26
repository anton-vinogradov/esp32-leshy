#pragma once

#include <Arduino.h>
#include <NetworkClient.h>
#include <NetworkServer.h>

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

    ArduinoCompanionWebService() : server_(80, 1) {}

    bool begin(
        const services::companion::CompanionLocalCredentials& credentials);
    void stop();
    bool poll(std::uint64_t nowUs, bool deviceSessionAuthorized,
              CompanionWebFrameHandler handler, void* context);

    bool active() const { return active_; }
    std::uint32_t requestsHandled() const { return requestsHandled_; }
    std::uint32_t requestsRejected() const { return requestsRejected_; }

private:
    void resetClient();
    void sendResponse(std::uint16_t status, const char* contentType,
                      const char* body, std::size_t bodyLength);
    bool processRequest(bool deviceSessionAuthorized,
                        CompanionWebFrameHandler handler, void* context);

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
    bool active_ = false;
};

}  // namespace leshy1::platform::arduino
