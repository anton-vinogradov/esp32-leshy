#include "DeauthDetector.h"

#include <WiFi.h>
#include <string.h>

static DeauthDetector* s_instance = nullptr;
static portMUX_TYPE    s_mux = portMUX_INITIALIZER_UNLOCKED;

static void deauthCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_MGMT) return;
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    if (pkt->rx_ctrl.sig_len < 24) return;              // need addr1..addr3 (pl[4..21])
    const uint8_t* pl = pkt->payload;
    uint8_t subtype = pl[0] & 0xF0;
    if (subtype != 0xC0 && subtype != 0xA0) return;     // deauth (0xC0) / disassoc (0xA0)

    DeauthEvent e;
    e.t       = millis();
    e.subtype = subtype;
    e.rssi    = pkt->rx_ctrl.rssi;
    e.channel = pkt->rx_ctrl.channel;
    memcpy(e.dst, pl + 4, 6);                            // addr1 = destination
    memcpy(e.src, pl + 10, 6);                           // addr2 = source

    // Check the instance and write under the same lock so stop() can retire the
    // instance safely (it clears s_instance under s_mux).
    portENTER_CRITICAL(&s_mux);
    if (s_instance) s_instance->writeLocked(e);
    portEXIT_CRITICAL(&s_mux);
}

void DeauthDetector::writeLocked(const DeauthEvent& e) {
    ring_[head_ % CAP] = e;
    head_++;
    total_++;
}

uint32_t DeauthDetector::total() {
    portENTER_CRITICAL(&s_mux);
    uint32_t t = total_;
    portEXIT_CRITICAL(&s_mux);
    return t;
}

int DeauthDetector::recentCount() {
    uint32_t now = millis();
    int n = 0;
    portENTER_CRITICAL(&s_mux);
    size_t total = head_ < CAP ? (size_t)head_ : CAP;
    for (size_t i = 0; i < total; i++) {
        if (now - ring_[i].t <= cfg_.windowMs) n++;
    }
    portEXIT_CRITICAL(&s_mux);
    return n;
}

bool DeauthDetector::lastEvent(DeauthEvent& out) {
    bool ok = false;
    portENTER_CRITICAL(&s_mux);
    if (head_ > 0) { out = ring_[(head_ - 1) % CAP]; ok = true; }
    portEXIT_CRITICAL(&s_mux);
    return ok;
}

bool DeauthDetector::begin(const DeauthDetectorConfig& cfg) {
    cfg_ = cfg;
    s_instance = this;

    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);      // keep the driver init+started — promiscuous needs it (wifioff=true kills it)
    delay(100);

    if (esp_wifi_set_promiscuous(true) != ESP_OK) { s_instance = nullptr; return false; }
    wifi_promiscuous_filter_t filt;
    filt.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&deauthCb);

    curChannel_ = cfg_.fixedChannel ? cfg_.fixedChannel : 1;
    if (esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE) != ESP_OK) {
        esp_wifi_set_promiscuous(false);
        s_instance = nullptr;
        return false;
    }

    nextHop_ = millis() + cfg_.hopMs;
    running_ = true;
    return true;
}

void DeauthDetector::loop() {
    if (!running_ || cfg_.fixedChannel) return;         // fixed channel → nothing to hop
    if ((int32_t)(millis() - nextHop_) < 0) return;
    nextHop_ = millis() + cfg_.hopMs;
    curChannel_ = (curChannel_ % 13) + 1;
    esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE);
}

void DeauthDetector::stop() {
    if (!running_) return;
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    esp_wifi_set_promiscuous(false);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    portENTER_CRITICAL(&s_mux);          // retire the instance under the lock the callback uses
    s_instance = nullptr;
    portEXIT_CRITICAL(&s_mux);
}
