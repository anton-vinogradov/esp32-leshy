#include "StationSniffer.h"

#include <WiFi.h>
#include <string.h>

static StationSniffer* s_inst = nullptr;
static portMUX_TYPE     s_mux = portMUX_INITIALIZER_UNLOCKED;

// Pull the station address out of a frame. Data frames carry BSSID + STA in a position
// set by the To/From-DS bits; a probe request's addr2 is a station hunting for networks.
static void staCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_DATA && type != WIFI_PKT_MGMT) return;
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    if (pkt->rx_ctrl.sig_len < 24) return;              // need addr1..addr3
    const uint8_t* p = pkt->payload;
    uint8_t ftype  = (p[0] >> 2) & 0x03;
    uint8_t tods   =  p[1]       & 0x01;
    uint8_t fromds = (p[1] >> 1) & 0x01;
    uint8_t sta[6], bssid[6];
    bool have = false, assoc = false;
    if (ftype == 2) {                                   // DATA
        if (tods && !fromds)      { memcpy(bssid, p + 4, 6); memcpy(sta, p + 10, 6); have = true; assoc = true; }   // STA→AP: a1=BSSID, a2=STA
        else if (!tods && fromds) { memcpy(sta, p + 4, 6); memcpy(bssid, p + 10, 6); have = true; assoc = true; }   // AP→STA: a1=STA,  a2=BSSID
    } else if (ftype == 0 && (p[0] & 0xF0) == 0x40) {   // MGMT probe request
        memcpy(sta, p + 10, 6); memset(bssid, 0, 6); have = true; assoc = false;
    }
    if (!have || (sta[0] & 0x01)) return;               // need a station, skip multicast/broadcast
    portENTER_CRITICAL(&s_mux);
    if (s_inst) s_inst->seen(sta, bssid, assoc, pkt->rx_ctrl.rssi);
    portEXIT_CRITICAL(&s_mux);
}

void StationSniffer::seen(const uint8_t sta[6], const uint8_t bssid[6], bool assoc, int8_t rssi) {
    for (int i = 0; i < n_; i++) {
        if (memcmp(tbl_[i].mac, sta, 6) == 0) {
            tbl_[i].rssi = rssi; tbl_[i].last = millis(); tbl_[i].pkts++;
            if (assoc) { memcpy(tbl_[i].bssid, bssid, 6); tbl_[i].assoc = true; }
            return;
        }
    }
    if (n_ < CAP) {
        StaRow& r = tbl_[n_++];
        memcpy(r.mac, sta, 6); memcpy(r.bssid, bssid, 6);
        r.rssi = rssi; r.last = millis(); r.pkts = 1; r.assoc = assoc;
    }
}

int StationSniffer::count() {
    portENTER_CRITICAL(&s_mux);
    int n = n_;
    portEXIT_CRITICAL(&s_mux);
    return n;
}

bool StationSniffer::row(int i, StaRow& out) {
    static StaRow tmp[CAP];                              // UI thread only
    portENTER_CRITICAL(&s_mux);
    int n = n_;
    memcpy(tmp, tbl_, sizeof(StaRow) * n);
    portEXIT_CRITICAL(&s_mux);
    for (int a = 1; a < n; a++) {                        // strongest RSSI first
        StaRow k = tmp[a]; int b = a - 1;
        while (b >= 0 && tmp[b].rssi < k.rssi) { tmp[b + 1] = tmp[b]; b--; }
        tmp[b + 1] = k;
    }
    if (i < 0 || i >= n) return false;
    out = tmp[i];
    return true;
}

bool StationSniffer::begin() {
    s_inst = this;
    n_ = 0;
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);          // keep the driver started (promiscuous needs it)
    delay(100);
    if (esp_wifi_set_promiscuous(true) != ESP_OK) { s_inst = nullptr; return false; }
    wifi_promiscuous_filter_t filt;
    filt.filter_mask = WIFI_PROMIS_FILTER_MASK_DATA | WIFI_PROMIS_FILTER_MASK_MGMT;
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&staCb);
    curChannel_ = 1;
    esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE);
    nextHop_ = millis() + 300;
    running_ = true;
    return true;
}

void StationSniffer::loop() {
    if (!running_) return;
    if (millis() >= nextHop_) {
        nextHop_ = millis() + 300;
        curChannel_ = curChannel_ >= 13 ? 1 : curChannel_ + 1;
        esp_wifi_set_channel(curChannel_, WIFI_SECOND_CHAN_NONE);
    }
}

void StationSniffer::stop() {
    portENTER_CRITICAL(&s_mux);
    s_inst = nullptr;                // the callback can no longer touch us
    portEXIT_CRITICAL(&s_mux);
    esp_wifi_set_promiscuous(false);
    running_ = false;
}
