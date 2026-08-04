#include "WpsProbe.h"

#include <WiFi.h>
#include <esp_wifi.h>
#include <string.h>

namespace {
    volatile bool s_done = false;
    uint8_t s_target[6];
    char    s_manuf[34], s_model[34];

    // WPS data elements are big-endian {u16 id, u16 len, value}. Pull Manufacturer
    // (0x1021) and Model Name (0x1023).
    void parseWps(const uint8_t* p, int len) {
        int i = 0;
        while (i + 4 <= len) {
            uint16_t id = ((uint16_t)p[i] << 8) | p[i + 1];
            uint16_t l  = ((uint16_t)p[i + 2] << 8) | p[i + 3];
            i += 4;
            if (i + l > len) break;
            if (id == 0x1021 && !s_manuf[0]) { int n = l < 33 ? l : 33; memcpy(s_manuf, p + i, n); s_manuf[n] = 0; }
            if (id == 0x1023 && !s_model[0]) { int n = l < 33 ? l : 33; memcpy(s_model, p + i, n); s_model[n] = 0; }
            i += l;
        }
    }

    void cb(void* buf, wifi_promiscuous_pkt_type_t type) {
        if (s_done || type != WIFI_PKT_MGMT) return;
        auto* pkt = (wifi_promiscuous_pkt_t*)buf;
        int total = pkt->rx_ctrl.sig_len;
        if (total < 40) return;
        const uint8_t* p = pkt->payload;
        if ((p[0] & 0xF0) != 0x80) return;                    // beacon subtype
        if (memcmp(p + 10, s_target, 6) != 0) return;         // addr2 = BSSID
        int i = 36, end = total - 4;                          // IEs start after 24B hdr + 12B fixed; drop FCS
        while (i + 2 <= end) {
            uint8_t tag = p[i], tl = p[i + 1];
            i += 2;
            if (i + tl > end) break;
            if (tag == 0xDD && tl >= 4 && p[i] == 0x00 && p[i + 1] == 0x50 && p[i + 2] == 0xF2 && p[i + 3] == 0x04) {
                parseWps(p + i + 4, tl - 4);                  // vendor-specific, WPS (00:50:F2 / type 04)
                s_done = true;
            }
            i += tl;
        }
    }
}

bool WpsProbe::probe(const uint8_t bssid[6], uint8_t channel, uint32_t ms, String& manuf, String& model) {
    memcpy(s_target, bssid, 6);
    s_manuf[0] = s_model[0] = 0;
    s_done = false;
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);                                   // keep the driver started
    delay(50);
    if (esp_wifi_set_promiscuous(true) != ESP_OK) return false;
    wifi_promiscuous_filter_t f;
    f.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
    esp_wifi_set_promiscuous_filter(&f);
    esp_wifi_set_promiscuous_rx_cb(&cb);
    esp_wifi_set_channel(channel >= 1 && channel <= 14 ? channel : 1, WIFI_SECOND_CHAN_NONE);
    uint32_t t0 = millis();
    while (!s_done && millis() - t0 < ms) delay(20);
    esp_wifi_set_promiscuous_rx_cb(nullptr);
    esp_wifi_set_promiscuous(false);
    manuf = s_manuf;
    model = s_model;
    return s_model[0] || s_manuf[0];
}
