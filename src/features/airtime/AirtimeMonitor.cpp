#include "AirtimeMonitor.h"

#include <WiFi.h>
#include <string.h>

static AirtimeMonitor* s_instance = nullptr;
static portMUX_TYPE    s_mux = portMUX_INITIALIZER_UNLOCKED;

// Rough on-air time of one PPDU, in microseconds. Exact airtime needs the full
// PHY parameters (guard interval, aggregation, coding); we approximate from the
// length and a coarse rate so the RELATIVE busyness of channels is truthful. It
// underestimates, which is why the UI calls the result a lower bound.
static uint32_t frameAirtimeUs(const wifi_pkt_rx_ctrl_t& c) {
    uint32_t bytes = c.sig_len;                 // whole received PPDU incl. FCS
    if (bytes < 14) bytes = 14;
    if (c.sig_mode == 1) {                      // HT (802.11n)
        static const uint16_t htMbps10[8] = { 65, 130, 195, 260, 390, 520, 585, 650 };  // MCS0..7, HT20 long-GI, x10
        uint16_t r = htMbps10[c.mcs & 7];
        return 40 + (uint32_t)((uint64_t)bytes * 8 * 10 / r);   // ~40us HT preamble + SIG
    }
    // Legacy 11b/g: we can't cleanly map the rate index here, so assume a modest
    // 12 Mbps — a deliberate middle estimate. Preamble+headers ~30us.
    return 30 + (uint32_t)((uint64_t)bytes * 8 / 12);
}

static void airtimeCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type == WIFI_PKT_MISC) return;          // zero-length payload, no useful length
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    uint8_t ch = pkt->rx_ctrl.channel;          // bucket by the frame's own channel
    if (ch < 1 || ch > 13) return;
    uint32_t us = frameAirtimeUs(pkt->rx_ctrl);
    portENTER_CRITICAL(&s_mux);
    if (s_instance) s_instance->addBusyLocked(ch, us);
    portEXIT_CRITICAL(&s_mux);
}

void AirtimeMonitor::addBusyLocked(uint8_t ch, uint32_t us) {
    busyUs_[ch] += us;
}

bool AirtimeMonitor::begin(uint32_t dwellMs) {
    dwellMs_ = dwellMs;
    memset((void*)busyUs_, 0, sizeof(busyUs_));
    memset((void*)obsUs_,  0, sizeof(obsUs_));
    memset((void*)last_,   0, sizeof(last_));
    s_instance = this;

    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);      // keep the driver started — promiscuous needs it
    delay(100);

    if (esp_wifi_set_promiscuous(true) != ESP_OK) { s_instance = nullptr; return false; }
    wifi_promiscuous_filter_t filt;
    filt.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA | WIFI_PROMIS_FILTER_MASK_CTRL;
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&airtimeCb);

    curChannel_ = 1;
    if (esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE) != ESP_OK) {
        esp_wifi_set_promiscuous(false);
        s_instance = nullptr;
        return false;
    }
    landedAt_ = millis();
    hopAt_    = landedAt_ + dwellMs_;
    running_  = true;
    return true;
}

// Fold the just-finished dwell on `ch` into its held busy-permille and reset its
// accumulators for the next visit. Caller holds s_mux.
void AirtimeMonitor::finalizeLocked(uint8_t ch, uint32_t now) {
    obsUs_[ch] += (now - landedAt_) * 1000;
    uint32_t obs = obsUs_[ch], busy = busyUs_[ch];
    if (obs) {
        uint32_t pm = (uint32_t)((uint64_t)busy * 1000 / obs);
        last_[ch] = pm > 1000 ? 1000 : (uint16_t)pm;
    }
    busyUs_[ch] = 0;
    obsUs_[ch]  = 0;
}

void AirtimeMonitor::loop() {
    if (!running_) return;
    if ((int32_t)(millis() - hopAt_) < 0) return;
    uint32_t now = millis();
    portENTER_CRITICAL(&s_mux);
    finalizeLocked(curChannel_, now);
    portEXIT_CRITICAL(&s_mux);
    curChannel_ = (curChannel_ % MAXCH) + 1;
    esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE);
    landedAt_ = now;
    hopAt_    = now + dwellMs_;
}

void AirtimeMonitor::read(uint16_t out[14]) {
    portENTER_CRITICAL(&s_mux);
    for (int ch = 1; ch <= MAXCH; ch++) out[ch] = last_[ch];
    portEXIT_CRITICAL(&s_mux);
}

void AirtimeMonitor::stop() {
    if (!running_) return;
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    esp_wifi_set_promiscuous(false);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    portENTER_CRITICAL(&s_mux);
    s_instance = nullptr;
    portEXIT_CRITICAL(&s_mux);
}
