#include "BoardWifiPassiveScanner.h"

#include <cstring>

#include <esp_event.h>
#include <esp_timer.h>
#include <esp_wifi.h>

namespace leshy1::platform::arduino {

namespace {

domain::observations::WifiAuthentication normalizeAuthentication(
    wifi_auth_mode_t authentication) {
    using Authentication = domain::observations::WifiAuthentication;
    switch (authentication) {
        case WIFI_AUTH_OPEN: return Authentication::Open;
        case WIFI_AUTH_WEP: return Authentication::Wep;
        case WIFI_AUTH_WPA_PSK: return Authentication::WpaPsk;
        case WIFI_AUTH_WPA2_PSK: return Authentication::Wpa2Psk;
        case WIFI_AUTH_WPA_WPA2_PSK: return Authentication::WpaWpa2Psk;
        case WIFI_AUTH_WPA2_ENTERPRISE:
            return Authentication::Wpa2Enterprise;
        case WIFI_AUTH_WPA3_PSK:
        case WIFI_AUTH_WPA3_EXT_PSK: return Authentication::Wpa3Psk;
        case WIFI_AUTH_WPA2_WPA3_PSK:
        case WIFI_AUTH_WPA3_EXT_PSK_MIXED_MODE:
            return Authentication::Wpa2Wpa3Psk;
        case WIFI_AUTH_WAPI_PSK: return Authentication::WapiPsk;
        case WIFI_AUTH_OWE: return Authentication::Owe;
        case WIFI_AUTH_WPA3_ENT_192:
            return Authentication::Wpa3Enterprise192;
        case WIFI_AUTH_DPP: return Authentication::Dpp;
        case WIFI_AUTH_WPA3_ENTERPRISE:
            return Authentication::Wpa3Enterprise;
        case WIFI_AUTH_WPA2_WPA3_ENTERPRISE:
            return Authentication::Wpa2Wpa3Enterprise;
        case WIFI_AUTH_WPA_ENTERPRISE:
            return Authentication::WpaEnterprise;
        case WIFI_AUTH_MAX:
        default: return Authentication::Unknown;
    }
}

domain::observations::WifiCipher normalizeCipher(wifi_cipher_type_t cipher) {
    using Cipher = domain::observations::WifiCipher;
    switch (cipher) {
        case WIFI_CIPHER_TYPE_NONE: return Cipher::None;
        case WIFI_CIPHER_TYPE_WEP40: return Cipher::Wep40;
        case WIFI_CIPHER_TYPE_WEP104: return Cipher::Wep104;
        case WIFI_CIPHER_TYPE_TKIP: return Cipher::Tkip;
        case WIFI_CIPHER_TYPE_CCMP: return Cipher::Ccmp;
        case WIFI_CIPHER_TYPE_TKIP_CCMP: return Cipher::TkipCcmp;
        case WIFI_CIPHER_TYPE_AES_CMAC128: return Cipher::AesCmac128;
        case WIFI_CIPHER_TYPE_SMS4: return Cipher::Sms4;
        case WIFI_CIPHER_TYPE_GCMP: return Cipher::Gcmp;
        case WIFI_CIPHER_TYPE_GCMP256: return Cipher::Gcmp256;
        case WIFI_CIPHER_TYPE_AES_GMAC128: return Cipher::AesGmac128;
        case WIFI_CIPHER_TYPE_AES_GMAC256: return Cipher::AesGmac256;
        case WIFI_CIPHER_TYPE_UNKNOWN:
        default: return Cipher::Unknown;
    }
}

domain::observations::WifiChannelWidth normalizeWidth(
    wifi_bandwidth_t width) {
    using Width = domain::observations::WifiChannelWidth;
    switch (width) {
        case WIFI_BW_HT20: return Width::Mhz20;
        case WIFI_BW_HT40: return Width::Mhz40;
        case WIFI_BW80: return Width::Mhz80;
        case WIFI_BW160: return Width::Mhz160;
        case WIFI_BW80_BW80: return Width::Mhz80Plus80;
        default: return Width::Unknown;
    }
}

domain::observations::WifiNetworkFacts networkFacts(
    const wifi_ap_record_t& source) {
    using Facts = domain::observations::WifiNetworkFacts;
    Facts facts;
    facts.present = true;
    facts.authentication = normalizeAuthentication(source.authmode);
    facts.pairwiseCipher = normalizeCipher(source.pairwise_cipher);
    facts.groupCipher = normalizeCipher(source.group_cipher);
    facts.channelWidth = normalizeWidth(source.bandwidth);
    facts.secondaryChannelDirection =
        static_cast<std::uint8_t>(source.second);
    facts.receiveAntenna = source.ant == WIFI_ANT_ANT0
        ? 0U : (source.ant == WIFI_ANT_ANT1 ? 1U : 0xffU);
    facts.phyMask = static_cast<std::uint16_t>(
        (source.phy_11b ? Facts::kPhy11b : 0U) |
        (source.phy_11g ? Facts::kPhy11g : 0U) |
        (source.phy_11n ? Facts::kPhy11n : 0U) |
        (source.phy_lr ? Facts::kPhyLowRate : 0U) |
        (source.phy_11a ? Facts::kPhy11a : 0U) |
        (source.phy_11ac ? Facts::kPhy11ac : 0U) |
        (source.phy_11ax ? Facts::kPhy11ax : 0U));
    facts.wps = source.wps;
    facts.ftmResponder = source.ftm_responder;
    facts.ftmInitiator = source.ftm_initiator;
    std::memcpy(facts.countryCode.data(), source.country.cc,
                facts.countryCode.size());
    facts.countryStartChannel = source.country.schan;
    facts.countryChannelCount = source.country.nchan;
    facts.countryMaximumTxPowerDbm = source.country.max_tx_power;
    facts.bssColor = source.he_ap.bss_color;
    facts.bssColorKnown = source.phy_11ax && !source.he_ap.bss_color_disabled;
    facts.vhtCenterChannel1 = source.vht_ch_freq1;
    facts.vhtCenterChannel2 = source.vht_ch_freq2;
    return facts;
}

}  // namespace

const char* boardWifiScanStatusName(BoardWifiScanStatus status) {
    switch (status) {
        case BoardWifiScanStatus::Valid: return "valid";
        case BoardWifiScanStatus::NotStarted: return "not_started";
        case BoardWifiScanStatus::InvalidPlan: return "invalid_plan";
        case BoardWifiScanStatus::ScanFailed: return "scan_failed";
        case BoardWifiScanStatus::CountFailed: return "count_failed";
        case BoardWifiScanStatus::RecordFailed: return "record_failed";
    }
    return "unknown";
}

bool BoardWifiPassiveScanner::begin() {
    if (initialized_ || started_) return false;
    cleanupComplete_ = false;
    lastError_ = 0;
    esp_err_t error = esp_event_loop_create_default();
    if (error == ESP_OK) {
        eventLoopOwned_ = true;
        eventLoopReady_ = true;
    } else if (error == ESP_ERR_INVALID_STATE) {
        eventLoopReady_ = true;
    } else {
        lastError_ = error;
        cleanupComplete_ = true;
        return false;
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    error = esp_wifi_init(&init);
    if (error != ESP_OK) {
        lastError_ = error;
        cleanupComplete_ = true;
        return false;
    }
    initialized_ = true;
    nvsDisabled_ = true;

    error = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (error == ESP_OK) volatileStorageOnly_ = true;
    if (error == ESP_OK) error = esp_wifi_set_mode(WIFI_MODE_STA);
    if (error == ESP_OK) error = esp_wifi_start();
    if (error != ESP_OK) {
        lastError_ = error;
        end();
        return false;
    }
    started_ = true;
    return true;
}

BoardWifiPassiveScanResult BoardWifiPassiveScanner::scan(
    const drivers::wifi::WifiScanPlan& plan,
    WifiRecordVisitor visitor, void* context) {
    BoardWifiPassiveScanResult result;
    if (!started_) return result;
    if (!drivers::wifi::validatePassivePlan(plan) || visitor == nullptr) {
        result.status = BoardWifiScanStatus::InvalidPlan;
        return result;
    }

    wifi_scan_config_t config{};
    config.ssid = nullptr;
    config.bssid = nullptr;
    config.channel = plan.channel;
    config.show_hidden = plan.showHidden;
    config.scan_type = WIFI_SCAN_TYPE_PASSIVE;
    config.scan_time.passive = plan.maxMsPerChannel;
    config.home_chan_dwell_time = 30;

    const std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    esp_err_t error = esp_wifi_scan_start(&config, true);
    result.durationUs = static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
    if (error != ESP_OK) {
        result.status = BoardWifiScanStatus::ScanFailed;
        result.driverError = error;
        lastError_ = error;
        return result;
    }
    error = esp_wifi_scan_get_ap_num(&result.recordsReported);
    if (error != ESP_OK) {
        result.status = BoardWifiScanStatus::CountFailed;
        result.driverError = error;
        lastError_ = error;
        esp_wifi_clear_ap_list();
        return result;
    }

    const std::uint16_t recordsToRead =
        result.recordsReported < kMaximumRecordsVisited
            ? result.recordsReported : kMaximumRecordsVisited;
    for (std::uint16_t index = 0; index < recordsToRead; ++index) {
        wifi_ap_record_t source{};
        error = esp_wifi_scan_get_ap_record(&source);
        if (error != ESP_OK) {
            result.status = BoardWifiScanStatus::RecordFailed;
            result.driverError = error;
            lastError_ = error;
            esp_wifi_clear_ap_list();
            return result;
        }
        ++result.recordsRead;
        drivers::wifi::WifiScanRecord record;
        std::memcpy(record.bssid.data(), source.bssid, record.bssid.size());
        record.channel = source.primary;
        record.rssiDbm = source.rssi;
        record.ssid = reinterpret_cast<const char*>(source.ssid);
        record.ssidLength = 0;
        while (record.ssidLength < 32U && source.ssid[record.ssidLength] != 0) {
            ++record.ssidLength;
        }
        record.network = networkFacts(source);
        switch (visitor(record,
                        static_cast<std::uint64_t>(esp_timer_get_time()),
                        context)) {
            case WifiRecordDisposition::Accepted: ++result.accepted; break;
            case WifiRecordDisposition::Rejected: ++result.rejected; break;
            case WifiRecordDisposition::Dropped: ++result.dropped; break;
        }
    }
    if (result.recordsReported > result.recordsRead) {
        result.dropped = static_cast<std::uint16_t>(
            result.dropped + result.recordsReported - result.recordsRead);
    }
    esp_wifi_clear_ap_list();
    result.status = BoardWifiScanStatus::Valid;
    return result;
}

bool BoardWifiPassiveScanner::cancelActiveScan() {
    const esp_err_t error = esp_wifi_scan_stop();
    return error == ESP_OK || error == ESP_ERR_WIFI_NOT_STARTED ||
           error == ESP_ERR_WIFI_STATE;
}

bool BoardWifiPassiveScanner::end() {
    bool complete = true;
    if (started_) {
        const esp_err_t error = esp_wifi_stop();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    started_ = false;
    if (initialized_) {
        const esp_err_t error = esp_wifi_deinit();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    initialized_ = false;
    nvsDisabled_ = false;
    volatileStorageOnly_ = false;
    if (eventLoopOwned_) {
        const esp_err_t error = esp_event_loop_delete_default();
        if (error != ESP_OK) {
            lastError_ = error;
            complete = false;
        }
    }
    eventLoopOwned_ = false;
    eventLoopReady_ = false;
    cleanupComplete_ = complete;
    return complete;
}

}  // namespace leshy1::platform::arduino
