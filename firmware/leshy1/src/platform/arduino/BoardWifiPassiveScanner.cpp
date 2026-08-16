#include "BoardWifiPassiveScanner.h"

#include <cstring>

#include <esp_timer.h>
#include <esp_wifi.h>

namespace leshy1::platform::arduino {

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
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    init.nvs_enable = 0;
    esp_err_t error = esp_wifi_init(&init);
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
    cleanupComplete_ = complete;
    return complete;
}

}  // namespace leshy1::platform::arduino
