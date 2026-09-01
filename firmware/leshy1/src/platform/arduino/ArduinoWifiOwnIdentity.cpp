#include "platform/arduino/ArduinoWifiOwnIdentity.h"

#include <cstring>

#include <esp_random.h>

namespace leshy1::platform::arduino {

namespace {

void clearAddress(services::privacy::WifiMacAddress& address) {
    volatile std::uint8_t* bytes = address.data();
    for (std::size_t index = 0; index < address.size(); ++index) {
        bytes[index] = 0U;
    }
}

services::privacy::WifiOwnInterface ownInterface(
    wifi_interface_t interface) {
    return interface == WIFI_IF_AP
        ? services::privacy::WifiOwnInterface::AccessPoint
        : services::privacy::WifiOwnInterface::Station;
}

ArduinoWifiOwnIdentity singleton;

}  // namespace

void ArduinoWifiOwnIdentity::restore(
    services::privacy::WifiOwnIdentityMode mode) {
    mode_ = mode;
}

void ArduinoWifiOwnIdentity::setMode(
    services::privacy::WifiOwnIdentityMode mode) {
    mode_ = mode;
}

bool ArduinoWifiOwnIdentity::apply(wifi_interface_t interface) {
    using services::privacy::WifiMacAddress;
    lastError_ = ESP_OK;
    lastLocalAdmin_ = false;
    lastUnicast_ = false;
    lastDiffersFromHardware_ = false;

    WifiMacAddress hardware{};
    lastError_ = esp_wifi_get_mac(interface, hardware.data());
    if (lastError_ != ESP_OK) {
        ++failures_;
        clearAddress(hardware);
        return false;
    }
    if (mode_ == services::privacy::WifiOwnIdentityMode::Hardware) {
        if (interface == WIFI_IF_AP) {
            ++accessPointApplications_;
        } else {
            ++stationApplications_;
        }
        clearAddress(hardware);
        return true;
    }

    WifiMacAddress entropy{};
    esp_fill_random(entropy.data(), entropy.size());
    ++generation_;
    if (generation_ == 0U) ++generation_;
    auto generated = services::privacy::makePrivateWifiIdentity(
        entropy, hardware, ownInterface(interface), generation_);
    clearAddress(entropy);
    if (!generated.valid()) {
        ++failures_;
        lastError_ = ESP_ERR_INVALID_STATE;
        clearAddress(hardware);
        clearAddress(generated.address);
        return false;
    }

    lastError_ = esp_wifi_set_mac(interface, generated.address.data());
    WifiMacAddress observed{};
    if (lastError_ == ESP_OK) {
        lastError_ = esp_wifi_get_mac(interface, observed.data());
    }
    const bool exact = lastError_ == ESP_OK &&
        std::memcmp(observed.data(), generated.address.data(),
                    observed.size()) == 0;
    lastLocalAdmin_ = generated.localAdmin;
    lastUnicast_ = generated.unicast;
    lastDiffersFromHardware_ = generated.differsFromHardware;
    clearAddress(hardware);
    clearAddress(observed);
    clearAddress(generated.address);
    if (!exact) {
        ++failures_;
        if (lastError_ == ESP_OK) lastError_ = ESP_ERR_INVALID_STATE;
        return false;
    }
    if (interface == WIFI_IF_AP) {
        ++accessPointApplications_;
    } else {
        ++stationApplications_;
    }
    return true;
}

ArduinoWifiOwnIdentityDiagnostics ArduinoWifiOwnIdentity::diagnostics() const {
    return {
        mode_, generation_, stationApplications_, accessPointApplications_,
        failures_, lastError_, lastLocalAdmin_, lastUnicast_,
        lastDiffersFromHardware_, false,
    };
}

ArduinoWifiOwnIdentity& wifiOwnIdentity() { return singleton; }

}  // namespace leshy1::platform::arduino
