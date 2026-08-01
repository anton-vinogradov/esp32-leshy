#include "WifiScanner.h"

#include "../../core/i18n.h"

#include <WiFi.h>
#include <string.h>

int WifiScanner::scan(bool showHidden) {
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);          // drop association only; don't tear down the driver
    int n = WiFi.scanNetworks(false, showHidden);
    count_ = 0;
    for (int i = 0; i < n && count_ < MAX; i++) {
        WifiAp& a = aps_[count_];
        a.ssid = WiFi.SSID(i);
        memcpy(a.bssid, WiFi.BSSID(i), 6);
        a.rssi = WiFi.RSSI(i);
        a.channel = WiFi.channel(i);
        a.auth = (uint8_t)WiFi.encryptionType(i);
        count_++;
    }
    WiFi.scanDelete();
    return count_;
}

const char* WifiScanner::authName(uint8_t auth) {
    switch ((wifi_auth_mode_t)auth) {
        case WIFI_AUTH_OPEN:           return i18n::tr("open", "открыта");
        case WIFI_AUTH_WEP:            return "WEP";
        case WIFI_AUTH_WPA_PSK:        return "WPA";
        case WIFI_AUTH_WPA2_PSK:       return "WPA2";
        case WIFI_AUTH_WPA_WPA2_PSK:   return "WPA/2";
        case WIFI_AUTH_WPA3_PSK:       return "WPA3";
        case WIFI_AUTH_WPA2_WPA3_PSK:  return "WPA2/3";
        default:                       return "?";
    }
}
