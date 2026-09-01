#pragma once

#include <cstdint>

#include <esp_err.h>
#include <esp_wifi.h>

#include "services/privacy/WifiOwnIdentityPolicy.h"

namespace leshy1::platform::arduino {

struct ArduinoWifiOwnIdentityDiagnostics final {
    services::privacy::WifiOwnIdentityMode mode =
        services::privacy::WifiOwnIdentityMode::PrivatePerSession;
    std::uint32_t generation = 0U;
    std::uint32_t stationApplications = 0U;
    std::uint32_t accessPointApplications = 0U;
    std::uint32_t failures = 0U;
    esp_err_t lastError = ESP_OK;
    bool lastLocalAdmin = false;
    bool lastUnicast = false;
    bool lastDiffersFromHardware = false;
    bool rawAddressRetained = false;
};

class ArduinoWifiOwnIdentity final {
public:
    void restore(services::privacy::WifiOwnIdentityMode mode);
    void setMode(services::privacy::WifiOwnIdentityMode mode);
    bool apply(wifi_interface_t interface);

    services::privacy::WifiOwnIdentityMode mode() const { return mode_; }
    ArduinoWifiOwnIdentityDiagnostics diagnostics() const;

private:
    services::privacy::WifiOwnIdentityMode mode_ =
        services::privacy::WifiOwnIdentityMode::PrivatePerSession;
    std::uint32_t generation_ = 0U;
    std::uint32_t stationApplications_ = 0U;
    std::uint32_t accessPointApplications_ = 0U;
    std::uint32_t failures_ = 0U;
    esp_err_t lastError_ = ESP_OK;
    bool lastLocalAdmin_ = false;
    bool lastUnicast_ = false;
    bool lastDiffersFromHardware_ = false;
};

ArduinoWifiOwnIdentity& wifiOwnIdentity();

}  // namespace leshy1::platform::arduino
