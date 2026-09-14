#include "BoardWifiTestNetwork.h"
#include <Arduino.h>
#include <esp_event.h>
#include <esp_random.h>
#include <esp_wifi.h>
#include <cstdio>
#include <cstring>
#include "ArduinoWifiOwnIdentity.h"
#include "apps/self_test/WifiTestNetwork.h"

namespace leshy1::platform::arduino {
bool BoardWifiTestNetwork::configure(bool hidden) {
    wifi_config_t config{};
    const auto length = std::strlen(ssid_.data());
    std::memcpy(config.ap.ssid, ssid_.data(), length);
    config.ap.ssid_len = static_cast<std::uint8_t>(length);
    std::memcpy(config.ap.password, password_.data(), password_.size());
    config.ap.channel = apps::self_test::WifiTestNetwork::kChannel;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    config.ap.pairwise_cipher = WIFI_CIPHER_TYPE_CCMP;
    config.ap.ssid_hidden = hidden;
    config.ap.max_connection = 1;
    config.ap.beacon_interval = 100;
    error_ = esp_wifi_set_config(WIFI_IF_AP, &config);
    return error_ == ESP_OK;
}

bool BoardWifiTestNetwork::begin(bool hidden) {
    if (initialized_ || started_ || !cleanupComplete_) return false;
    pinMode(0, INPUT_PULLUP);
    if (digitalRead(0) == LOW) { error_ = ESP_ERR_INVALID_STATE; return false; }
    cleanupComplete_ = false;
    error_ = esp_event_loop_create_default();
    eventLoopOwned_ = error_ == ESP_OK;
    if (error_ != ESP_OK && error_ != ESP_ERR_INVALID_STATE) {
        cleanupComplete_ = true;
        return false;
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    init.static_rx_buf_num = 4;
    init.dynamic_rx_buf_num = 8;
    init.tx_buf_type = 1;
    init.static_tx_buf_num = 0;
    init.dynamic_tx_buf_num = 4;
    init.ampdu_rx_enable = 0;
    init.ampdu_tx_enable = 0;
    init.amsdu_tx_enable = 0;
    init.rx_ba_win = 0;
    init.mgmt_sbuf_num = 6;
    error_ = esp_wifi_init(&init);
    if (error_ != ESP_OK) { stop(); return false; }
    initialized_ = true;
    error_ = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error_ == ESP_OK) error_ = esp_wifi_set_mode(WIFI_MODE_AP);
    if (error_ == ESP_OK && !wifiOwnIdentity().apply(WIFI_IF_AP))
        error_ = wifiOwnIdentity().diagnostics().lastError;
    if (error_ == ESP_OK) error_ = esp_wifi_get_mac(WIFI_IF_AP, bssid_.data());
    if (error_ != ESP_OK) { stop(); return false; }
    // An unmistakable own test SSID, never a nearby network's identity.
    std::snprintf(ssid_.data(), ssid_.size(), "LESHY-TEST-%02X%02X",
                  static_cast<unsigned>(bssid_[4]), static_cast<unsigned>(bssid_[5]));
    std::array<std::uint8_t, 8> entropy{};
    esp_fill_random(entropy.data(), entropy.size());
    for (std::size_t i = 0; i < entropy.size(); ++i)
        std::snprintf(password_.data() + 2U * i, 3, "%02x", entropy[i]);
    volatile std::uint8_t* bytes = entropy.data();
    for (std::size_t i = 0; i < entropy.size(); ++i) bytes[i] = 0;
    if (!configure(hidden)) { stop(); return false; }
    error_ = esp_wifi_start();
    if (error_ != ESP_OK) { stop(); return false; }
    started_ = true;
    // SDK accepts the limit only after start; startup uses the PHY default.
    // Readback is configured power, not a measured antenna output.
    error_ = esp_wifi_set_max_tx_power(8);
    if (error_ == ESP_OK) error_ = esp_wifi_get_max_tx_power(&power_);
    if (error_ != ESP_OK || power_ != 8) { stop(); return false; }
    return true;
}

bool BoardWifiTestNetwork::setHidden(bool hidden) {
    return started_ && configure(hidden);
}

bool BoardWifiTestNetwork::stop() {
    bool complete = true;
    if (started_) {
        const auto error = esp_wifi_stop();
        if (error == ESP_OK) started_ = false;
        else { error_ = error; complete = false; }
    }
    if (initialized_ && !started_) {
        const auto error = esp_wifi_deinit();
        if (error == ESP_OK) initialized_ = false;
        else { error_ = error; complete = false; }
    }
    if (eventLoopOwned_ && !initialized_) {
        const auto error = esp_event_loop_delete_default();
        if (error == ESP_OK) eventLoopOwned_ = false;
        else { error_ = error; complete = false; }
    }
    volatile char* password = password_.data();
    for (std::size_t i = 0; i < password_.size(); ++i) password[i] = 0;
    if (!started_) power_ = 0;
    cleanupComplete_ = complete && !started_ && !initialized_ && !eventLoopOwned_;
    return cleanupComplete_;
}
}  // namespace leshy1::platform::arduino
