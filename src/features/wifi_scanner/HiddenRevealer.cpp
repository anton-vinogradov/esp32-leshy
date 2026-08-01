#include "HiddenRevealer.h"

#include <string.h>
#include <Preferences.h>
#include "esp_wifi.h"
#include "freertos/task.h"

HiddenRevealer* HiddenRevealer::active = nullptr;

static void promiscCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_MGMT || !HiddenRevealer::active) return;
    const wifi_promiscuous_pkt_t* p = (const wifi_promiscuous_pkt_t*)buf;
    HiddenRevealer::active->onFrame(p->payload, p->rx_ctrl.sig_len);
}

void HiddenRevealer::begin() {
    if (!mtx_) mtx_ = xSemaphoreCreateMutex();
    { Preferences p; p.begin("leshy_hid", false); p.end(); }   // create namespace so the read-only load won't log NOT_FOUND
    load();
}

// Parse a management frame; if it carries a non-empty SSID, cache BSSID -> name.
// Frames that expose a hidden name in cleartext: Probe Response / Beacon
// (SSID after a 12-byte fixed field) and (Re)Association Request (4 / 10 bytes).
void HiddenRevealer::onFrame(const uint8_t* f, uint16_t len) {
    if (len < 24) return;
    if ((f[0] & 0x0C) != 0x00) return;              // type must be management
    uint8_t subtype = (f[0] & 0xF0) >> 4;
    int fixed;
    switch (subtype) {
        case 0x5: case 0x8: fixed = 12; break;      // Probe Response / Beacon
        case 0x0:           fixed = 4;  break;       // Association Request
        case 0x2:           fixed = 10; break;       // Reassociation Request
        default: return;
    }
    const uint8_t* bssid = f + 16;                   // addr3 = BSSID (the AP)
    const uint8_t* body  = f + 24 + fixed;
    int blen = (int)len - 24 - fixed;
    int i = 0;
    while (i + 2 <= blen) {                          // walk tagged parameters
        uint8_t tag = body[i], tlen = body[i + 1];
        if (i + 2 + tlen > blen) break;
        if (tag == 0) {                              // SSID element
            if (tlen > 0 && tlen <= 32 && body[i + 2] != 0) {
                if (xSemaphoreTake(mtx_, 0) == pdTRUE) {   // never block the Wi-Fi task
                    storeLocked(bssid, (const char*)(body + i + 2), tlen);
                    xSemaphoreGive(mtx_);
                }
            }
            return;                                  // SSID is always the first tag
        }
        i += 2 + tlen;
    }
}

void HiddenRevealer::storeLocked(const uint8_t bssid[6], const char* ssid, uint8_t slen) {
    bool bcast = true;
    for (int k = 0; k < 6; k++) if (bssid[k] != 0xFF) bcast = false;
    if (bcast) return;
    for (int k = 0; k < n_; k++)
        if (memcmp(ent_[k].bssid, bssid, 6) == 0) return;   // already known
    if (n_ >= MAX) return;
    memcpy(ent_[n_].bssid, bssid, 6);
    memcpy(ent_[n_].ssid, ssid, slen);
    ent_[n_].ssid[slen] = 0;
    n_++;
    dirty_ = true;
}

void HiddenRevealer::listen(uint8_t channel, uint32_t ms) {
    active = this;
    esp_wifi_set_promiscuous(false);
    wifi_promiscuous_filter_t filt = { .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT };
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&promiscCb);
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);
    vTaskDelay(pdMS_TO_TICKS(ms));
    esp_wifi_set_promiscuous(false);
    active = nullptr;
    if (dirty_) persist();
}

bool HiddenRevealer::lookup(const uint8_t bssid[6], String& out) {
    bool ok = false;
    xSemaphoreTake(mtx_, portMAX_DELAY);
    for (int k = 0; k < n_; k++)
        if (memcmp(ent_[k].bssid, bssid, 6) == 0) { out = ent_[k].ssid; ok = true; break; }
    xSemaphoreGive(mtx_);
    return ok;
}

int HiddenRevealer::count() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    int n = n_;
    xSemaphoreGive(mtx_);
    return n;
}

bool HiddenRevealer::get(int i, uint8_t bssidOut[6], String& ssidOut) {
    bool ok = false;
    xSemaphoreTake(mtx_, portMAX_DELAY);
    if (i >= 0 && i < n_) { memcpy(bssidOut, ent_[i].bssid, 6); ssidOut = ent_[i].ssid; ok = true; }
    xSemaphoreGive(mtx_);
    return ok;
}

void HiddenRevealer::remove(int i) {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    if (i >= 0 && i < n_) {
        for (int k = i; k < n_ - 1; k++) ent_[k] = ent_[k + 1];
        n_--;
        dirty_ = true;
    }
    xSemaphoreGive(mtx_);
    if (dirty_) persist();
}

void HiddenRevealer::clear() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    n_ = 0; dirty_ = true;
    xSemaphoreGive(mtx_);
    persist();
}

void HiddenRevealer::persist() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    Preferences p; p.begin("leshy_hid", false);
    p.clear();
    p.putInt("cnt", n_);
    char k[8];
    for (int i = 0; i < n_; i++) {
        snprintf(k, sizeof(k), "b%d", i); p.putBytes(k, ent_[i].bssid, 6);
        snprintf(k, sizeof(k), "s%d", i); p.putString(k, ent_[i].ssid);
    }
    p.end();
    dirty_ = false;
    xSemaphoreGive(mtx_);
}

void HiddenRevealer::load() {
    xSemaphoreTake(mtx_, portMAX_DELAY);
    Preferences p; p.begin("leshy_hid", true);
    int c = p.getInt("cnt", 0);
    n_ = 0;
    char k[8];
    for (int i = 0; i < c && i < MAX; i++) {
        snprintf(k, sizeof(k), "b%d", i);
        if (p.getBytes(k, ent_[n_].bssid, 6) != 6) continue;
        snprintf(k, sizeof(k), "s%d", i);
        String s = p.getString(k, "");
        if (s.isEmpty()) continue;
        strncpy(ent_[n_].ssid, s.c_str(), 32);
        ent_[n_].ssid[32] = 0;
        n_++;
    }
    p.end();
    xSemaphoreGive(mtx_);
}
