#include "ScanEngine.h"

static ScanEngine* s_engine = nullptr;

static void scanTaskEntry(void*) {
    if (s_engine) s_engine->taskLoop();
    vTaskDelete(nullptr);
}

void ScanEngine::begin() {
    mtx_ = xSemaphoreCreateMutex();
    s_engine = this;
    // Pin to core 0 (the radio core); the Arduino loop runs on core 1.
    xTaskCreatePinnedToCore(scanTaskEntry, "scan", 12288, nullptr, 1, nullptr, 0);
}

void ScanEngine::pause() {
    paused_ = true;
    uint32_t t = millis();
    while (!idle_ && (millis() - t) < 6000) delay(10);   // wait for the in-flight scan to finish
}

void ScanEngine::resume() {
    idle_ = false;
    paused_ = false;
}

void ScanEngine::taskLoop() {
    for (;;) {
        if (paused_) { idle_ = true; vTaskDelay(pdMS_TO_TICKS(50)); continue; }
        idle_ = false;

        int n = ws_.scan();
        xSemaphoreTake(mtx_, portMAX_DELAY);
        wifiN_ = n < MAX ? n : MAX;
        for (int i = 0; i < wifiN_; i++) {
            const WifiAp& a = ws_.at(i);
            wifi_[i].ssid = a.ssid;
            wifi_[i].rssi = a.rssi;
            wifi_[i].auth = a.auth;
        }
        wifiGen_ = wifiGen_ + 1;         // (avoid ++ on volatile — deprecated in C++20)
        xSemaphoreGive(mtx_);
        vTaskDelay(pdMS_TO_TICKS(300));

        if (paused_) continue;           // don't start the BLE scan if a pause was requested

        int m = bs_.scan(4);
        xSemaphoreTake(mtx_, portMAX_DELAY);
        bleN_ = m < MAX ? m : MAX;
        for (int i = 0; i < bleN_; i++) {
            const BleDev& d = bs_.at(i);
            ble_[i].label   = d.tracker.length() ? d.tracker
                            : d.name.length()    ? d.name
                                                 : d.mac;
            ble_[i].rssi    = d.rssi;
            ble_[i].tracker = d.tracker.length() > 0;
        }
        bleGen_ = bleGen_ + 1;
        xSemaphoreGive(mtx_);
        vTaskDelay(pdMS_TO_TICKS(300));
    }
}

int ScanEngine::wifiCount() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    int n = wifiN_;
    xSemaphoreGive(mtx_);
    return n;
}

bool ScanEngine::wifiRow(int i, WifiRow& out) {
    bool ok = false;
    xSemaphoreTake(mtx_, portMAX_DELAY);
    if (i >= 0 && i < wifiN_) { out = wifi_[i]; ok = true; }
    xSemaphoreGive(mtx_);
    return ok;
}

int ScanEngine::bleCount() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    int n = bleN_;
    xSemaphoreGive(mtx_);
    return n;
}

bool ScanEngine::bleRow(int i, BleRow& out) {
    bool ok = false;
    xSemaphoreTake(mtx_, portMAX_DELAY);
    if (i >= 0 && i < bleN_) { out = ble_[i]; ok = true; }
    xSemaphoreGive(mtx_);
    return ok;
}
