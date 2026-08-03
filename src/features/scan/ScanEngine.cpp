#include "ScanEngine.h"

#include <string.h>

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
    paused_ = true;      // task finishes any in-flight scan then idles (non-blocking)
}

// Anything that reconfigures the radio (promiscuous, TLS/OTA) must wait for the
// scan task to actually leave scanNetworks()/reveal — otherwise two cores drive
// esp_wifi at once. A scan sweep plus reveal dwell can take a few seconds.
bool ScanEngine::pauseAndWait(uint32_t timeoutMs) {
    paused_ = true;
    uint32_t t0 = millis();
    while (!idle_ && (millis() - t0) < timeoutMs) vTaskDelay(pdMS_TO_TICKS(20));
    return idle_;
}

void ScanEngine::resume() {
    idle_ = false;
    paused_ = false;
}

// Safe only once the scan task is idle (pauseAndWait returned true) — otherwise
// we'd tear the BLE stack down from under bs_.scan(). The OTA path guarantees
// this by pausing the engine before it calls here.
bool ScanEngine::releaseBleForOta() { return bs_.releaseForOta(); }

void ScanEngine::taskLoop() {
    for (;;) {
        if (paused_) { idle_ = true; vTaskDelay(pdMS_TO_TICKS(50)); continue; }
        idle_ = false;
        ScanMode m = mode_;

        if (m == SCAN_BLE_RADAR) { bs_.radarScan(1); continue; }   // lock one MAC, live RSSI; no snapshot/list

        if (m != SCAN_BLE) {
            int n = ws_.scan();
            xSemaphoreTake(mtx_, portMAX_DELAY);
            wifiN_ = n < MAX ? n : MAX;
            for (int i = 0; i < wifiN_; i++) {
                const WifiAp& a = ws_.at(i);
                wifi_[i].hidden  = a.ssid.isEmpty();
                wifi_[i].ssid    = a.ssid;
                wifi_[i].rssi    = a.rssi;
                wifi_[i].auth    = a.auth;
                wifi_[i].channel = a.channel;
                memcpy(wifi_[i].bssid, a.bssid, 6);
                String name;                                   // fill hidden names we already know
                if (wifi_[i].hidden && rev_ && rev_->lookup(a.bssid, name)) wifi_[i].ssid = name;
                pushSpark(a.bssid, a.rssi);                     // per-AP RSSI history (mtx held)
            }
            wifiGen_ = wifiGen_ + 1;      // (avoid ++ on volatile — deprecated in C++20)
            xSemaphoreGive(mtx_);
        }

        if (m == SCAN_WIFI) {
            revealHidden();                                    // passive sniff on hidden channels
            vTaskDelay(pdMS_TO_TICKS(60));
            continue;                                          // Wi-Fi only: loop fast
        }

        if (m != SCAN_WIFI) {
            int mm = bs_.scan(4);
            xSemaphoreTake(mtx_, portMAX_DELAY);
            bleN_ = mm < MAX ? mm : MAX;
            for (int i = 0; i < bleN_; i++) {
                const BleDev& d = bs_.at(i);
                ble_[i].label   = d.tracker.length() ? d.tracker
                                : d.name.length()    ? d.name
                                                     : d.mac;
                ble_[i].rssi    = d.rssi;
                ble_[i].tracker = d.tracker.length() > 0;
                ble_[i].kind    = (uint8_t)d.kind;
                ble_[i].vendor  = d.vendor;
                ble_[i].mac     = d.mac;
                ble_[i].pub     = d.pub;
            }
            bleGen_ = bleGen_ + 1;
            xSemaphoreGive(mtx_);
        }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

// After a Wi-Fi sweep, briefly listen on the channel of each still-unnamed hidden
// AP. Names arrive only if there's traffic (a client probing / (re)associating),
// so this is a passive best-effort — no dwell at all when nothing is hidden.
void ScanEngine::revealHidden() {
    if (!rev_) return;
    uint8_t tgts[24][6]; int nt = 0;                // hidden BSSIDs still needing a name
    uint8_t chans[8];    int nc = 0;                // distinct channels to dwell on
    int n = ws_.count();
    for (int i = 0; i < n; i++) {
        const WifiAp& a = ws_.at(i);
        if (!a.ssid.isEmpty()) continue;            // only hidden APs
        String name;
        if (rev_->lookup(a.bssid, name)) continue;  // already revealed
        if (nt < 24) memcpy(tgts[nt++], a.bssid, 6);
        uint8_t ch = a.channel;
        if (ch < 1 || ch > 14) continue;
        bool dup = false;
        for (int k = 0; k < nc; k++) if (chans[k] == ch) dup = true;
        if (!dup && nc < 8) chans[nc++] = ch;
    }
    if (nt == 0) return;                            // nothing hidden to reveal → no promiscuous dwell
    rev_->setTargets(tgts, nt);                     // only these BSSIDs will be stored
    for (int k = 0; k < nc; k++) rev_->listen(chans[k], 450);
}

void ScanEngine::pushSpark(const uint8_t b[6], int8_t rssi) {
    for (int i = 0; i < sparkN_; i++) {
        if (memcmp(spark_[i].bssid, b, 6) == 0) {
            Spark& s = spark_[i];
            if (s.n < SPARK_N) s.v[s.n++] = rssi;
            else { for (int k = 0; k < SPARK_N - 1; k++) s.v[k] = s.v[k + 1]; s.v[SPARK_N - 1] = rssi; }
            return;
        }
    }
    if (sparkN_ < MAX) { Spark& s = spark_[sparkN_++]; memcpy(s.bssid, b, 6); s.v[0] = rssi; s.n = 1; }
}

void ScanEngine::clearSparks() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    sparkN_ = 0;
    xSemaphoreGive(mtx_);
}

int ScanEngine::sparkOf(const uint8_t b[6], int8_t* out) {
    int r = 0;
    xSemaphoreTake(mtx_, portMAX_DELAY);
    for (int i = 0; i < sparkN_; i++)
        if (memcmp(spark_[i].bssid, b, 6) == 0) { r = spark_[i].n; for (int k = 0; k < r; k++) out[k] = spark_[i].v[k]; break; }
    xSemaphoreGive(mtx_);
    return r;
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
