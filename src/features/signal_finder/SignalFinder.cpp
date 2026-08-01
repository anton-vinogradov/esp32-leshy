#include "SignalFinder.h"

#include <WiFi.h>
#include <string.h>
#include <algorithm>

// Single active instance, reached from the C-style promiscuous callback.
static SignalFinder* s_instance = nullptr;
static uint8_t       s_targetBssid[6] = {0};
static portMUX_TYPE  s_mux = portMUX_INITIALIZER_UNLOCKED;

static void finderSnifferCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    SignalFinder* inst = s_instance;                    // snapshot: stop() may null it concurrently
    if (type != WIFI_PKT_MGMT || !inst) return;
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    if (pkt->rx_ctrl.sig_len < 22) return;              // need pl[0] + addr3 (pl[16..21])
    const uint8_t* pl = pkt->payload;
    if (pl[0] != 0x80) return;                          // beacon subtype only
    if (memcmp(pl + 16, s_targetBssid, 6) != 0) return; // addr3 == target BSSID
    inst->pushSample(pkt->rx_ctrl.rssi);
}

void SignalFinder::pushSample(int8_t rssi) {
    uint32_t t = millis();                              // keep the critical section tiny
    portENTER_CRITICAL(&s_mux);
    ring_[head_ % CAP] = { t, rssi };
    head_++;
    portEXIT_CRITICAL(&s_mux);
}

int SignalFinder::medianWithin(uint32_t windowMs, int* countOut) {
    int8_t   tmp[CAP];
    int      n = 0;
    uint32_t now = millis();

    portENTER_CRITICAL(&s_mux);
    size_t total = head_ < CAP ? head_ : CAP;
    for (size_t i = 0; i < total; i++) {
        if (now - ring_[i].t <= windowMs) tmp[n++] = ring_[i].rssi;
    }
    portEXIT_CRITICAL(&s_mux);

    if (countOut) *countOut = n;
    if (n == 0) return -127;
    std::sort(tmp, tmp + n);
    return tmp[n / 2];
}

int SignalFinder::rssi() { int c; return medianWithin(cfg_.windowMs, &c); }

bool SignalFinder::begin(const SignalFinderConfig& cfg) {
    cfg_ = cfg;
    s_instance = this;

    // Find the target AP's BSSID + channel.
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(true, true);
    delay(100);
    int found = -1, n = WiFi.scanNetworks(false, true);
    for (int i = 0; i < n; i++) {
        if (WiFi.SSID(i) == cfg_.targetSsid) { found = i; break; }
    }
    if (found < 0) { WiFi.scanDelete(); s_instance = nullptr; return false; }
    memcpy(targetBssid_, WiFi.BSSID(found), 6);
    memcpy(s_targetBssid, targetBssid_, 6);
    channel_ = WiFi.channel(found);
    WiFi.scanDelete();

    // Sniff that AP's beacons on its channel (single radio → fixed channel).
    esp_wifi_set_promiscuous(true);
    wifi_promiscuous_filter_t filt;
    filt.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&finderSnifferCb);
    esp_wifi_set_channel(channel_, WIFI_SECOND_CHAN_NONE);

    nextUpdate_ = millis() + cfg_.updateMs;
    running_ = true;
    return true;
}

void SignalFinder::loop() {
    if (!running_) return;
    if ((int32_t)(millis() - nextUpdate_) < 0) return;
    nextUpdate_ = millis() + cfg_.updateMs;

    int c = 0, cur = medianWithin(cfg_.windowMs, &c);
    if (c < cfg_.minSamples) {                          // lost the beacon this window
        hasReading_ = false;
        trend_ = 0;
        return;
    }
    trend_ = hasReading_ ? (cur - last_) : 0;           // no false jump across a gap
    last_ = cur;
    hasReading_ = true;
}

void SignalFinder::stop() {
    if (!running_) return;
    esp_wifi_set_promiscuous(false);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    s_instance = nullptr;
}
