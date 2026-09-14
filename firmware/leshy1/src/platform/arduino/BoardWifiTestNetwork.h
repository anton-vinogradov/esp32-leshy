#pragma once
#include <array>
#include <cstdint>

namespace leshy1::platform::arduino {
// Ordinary Self-check radio adapter. RAM-only, no netif/DHCP/HTTP/SD/injection.
// The caller must hold EspRf and pass the product safety/admission gate.
class BoardWifiTestNetwork final {
public:
    bool begin(bool hidden);
    bool setHidden(bool hidden);
    bool stop();
    bool active() const { return started_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    int lastError() const { return error_; }
    const char* ssid() const { return ssid_.data(); }
    // Ephemeral credential for the local TFT only; never diagnostics or storage.
    const char* displayPassword() const { return started_ ? password_.data() : ""; }
    const std::array<std::uint8_t, 6>& bssid() const { return bssid_; }
    std::int8_t powerQuarterDbm() const { return power_; }
private:
    bool configure(bool hidden);
    std::array<char, 24> ssid_{};
    std::array<std::uint8_t, 6> bssid_{};
    std::array<char, 17> password_{};
    bool initialized_ = false, started_ = false, eventLoopOwned_ = false;
    bool cleanupComplete_ = true;
    int error_ = 0;
    std::int8_t power_ = 0;
};
}  // namespace leshy1::platform::arduino
