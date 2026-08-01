#include "PolitePortal.h"

#include <WiFi.h>
#include <string.h>
#include <algorithm>

// The promiscuous RX callback is a plain C function pointer, so route it to the
// single active instance through file-static state. Only one PolitePortal may
// run at a time.
static PolitePortal* s_instance = nullptr;
static uint8_t       s_targetBssid[6] = {0};
static portMUX_TYPE  s_mux = portMUX_INITIALIZER_UNLOCKED;

static void snifferCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_MGMT || !s_instance) return;
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    const uint8_t* pl = pkt->payload;
    if (pl[0] != 0x80) return;                          // beacon subtype only
    if (memcmp(pl + 16, s_targetBssid, 6) != 0) return; // addr3 == target BSSID
    s_instance->pushSample(pkt->rx_ctrl.rssi);
}

void PolitePortal::pushSample(int8_t rssi) {
    portENTER_CRITICAL(&s_mux);
    ring_[head_ % CAP] = { millis(), rssi };
    head_++;
    portEXIT_CRITICAL(&s_mux);
}

int PolitePortal::medianWithin(uint32_t windowMs, int* countOut) {
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

int PolitePortal::currentRssi() { int c; return medianWithin(cfg_.windowMs, &c); }
int PolitePortal::sampleCount() { int c; medianWithin(cfg_.windowMs, &c); return c; }

bool PolitePortal::begin(const PolitePortalConfig& cfg) {
    cfg_ = cfg;
    s_instance = this;

    // 1) Locate the target AP (BSSID + channel). It must be one you own.
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(true, true);
    delay(100);
    int found = -1, scanRssi = -127, n = WiFi.scanNetworks(false, true);
    for (int i = 0; i < n; i++) {
        if (WiFi.SSID(i) == cfg_.targetSsid) { found = i; break; }
    }
    if (found < 0) { WiFi.scanDelete(); s_instance = nullptr; return false; }
    memcpy(targetBssid_, WiFi.BSSID(found), 6);
    memcpy(s_targetBssid, targetBssid_, 6);
    channel_ = WiFi.channel(found);
    scanRssi = WiFi.RSSI(found);
    WiFi.scanDelete();

    // 2) SoftAP on the target's channel — a single radio must share the channel
    //    to hear the target's beacons while also serving the portal.
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(apIp_, apIp_, IPAddress(255, 255, 255, 0));
    WiFi.softAP(cfg_.portalSsid.c_str(), nullptr, channel_);

    // 3) Sniff beacons on that channel.
    esp_wifi_set_promiscuous(true);
    wifi_promiscuous_filter_t filt;
    filt.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT;
    esp_wifi_set_promiscuous_filter(&filt);
    esp_wifi_set_promiscuous_rx_cb(&snifferCb);
    esp_wifi_set_channel(channel_, WIFI_SECOND_CHAN_NONE);

    // 4) Baseline RSSI while the AP is (presumably) at full power.
    uint32_t t0 = millis();
    while (millis() - t0 < cfg_.baselineMs) delay(50);
    int c = 0, med = medianWithin(cfg_.baselineMs, &c);
    baseline_ = (c >= cfg_.minSamples) ? med : scanRssi;   // scan RSSI is a rough fallback

    // 5) Captive portal: wildcard DNS + web routes.
    dns_.start(53, "*", apIp_);
    web_.on("/", [this] { handleRoot(); });
    web_.on("/reduced", [this] { handleReduced(); });
    web_.on("/result", [this] { handleResult(); });
    web_.onNotFound([this] { redirectToPortal(); });      // pull OS captive checks to the page
    web_.begin();

    running_ = true;
    return true;
}

void PolitePortal::loop() {
    if (!running_) return;
    dns_.processNextRequest();
    web_.handleClient();
    if (shutdownArmed_ && (int32_t)(millis() - shutdownAt_) >= 0) stop();
}

void PolitePortal::stop() {
    if (!running_) return;
    web_.stop();
    dns_.stop();
    esp_wifi_set_promiscuous(false);
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    shutdownArmed_ = false;
    s_instance = nullptr;
}

void PolitePortal::redirectToPortal() {
    web_.sendHeader("Location", String("http://") + apIp_.toString() + "/", true);
    web_.send(302, "text/plain", "");
}

static const char* PAGE_CSS =
    "body{font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;"
    "margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}"
    ".card{max-width:440px;text-align:center}.big{font-size:52px;line-height:1}"
    "h1{margin:14px 0 8px}p{color:#cfcfcf;line-height:1.5}"
    "a.btn{display:inline-block;margin-top:22px;padding:16px 26px;background:#2ecc71;color:#04240f;"
    "font-weight:700;text-decoration:none;border-radius:12px}"
    "code{color:#8fd4ff}small{color:#888;display:block;margin-top:26px;line-height:1.5}";

void PolitePortal::sendPage(const String& body, int refreshSec, const char* refreshUrl) {
    String html = "<!doctype html><html><head><meta charset=utf-8>"
                  "<meta name=viewport content=\"width=device-width,initial-scale=1\">";
    if (refreshSec >= 0 && refreshUrl) {
        html += "<meta http-equiv=refresh content=\"" + String(refreshSec) + ";url=" + refreshUrl + "\">";
    }
    html += "<title>ESP32-Leshy</title><style>";
    html += PAGE_CSS;
    html += "</style></head><body><div class=card>" + body + "</div></body></html>";
    web_.send(200, "text/html; charset=utf-8", html);
}

void PolitePortal::handleRoot() {
    sendPage(
        "<div class=big>&#127794;&#128122;&#128246;</div>"
        "<h1>Привет, сосед!</h1>"
        "<p>Твой Wi-Fi добивает ко мне на полной мощности и глушит мой. Будь другом — "
        "зайди в настройки роутера и снизь мощность передатчика (Tx Power) на пару делений.</p>"
        "<p>Как снизишь — жми кнопку. Я проверю по уровню сигнала и сразу отстану. &#128591;</p>"
        "<a class=btn href=\"/reduced\">Я снизил мощность</a>"
        "<small>Демо-стенд ESP32-Leshy. Паролей тут не спрашивают и ничего не сохраняют.</small>");
}

void PolitePortal::handleReduced() {
    int wait = (int)(cfg_.windowMs / 1000) + 1;
    sendPage(
        "<div class=big>&#9203;</div>"
        "<h1>Проверяю…</h1>"
        "<p>Слушаю эфир несколько секунд и сравниваю с исходным уровнем. "
        "Не двигай устройства и не закрывай страницу.</p>",
        wait, "/result");
}

void PolitePortal::handleResult() {
    int cnt = 0;
    int cur = medianWithin(cfg_.windowMs, &cnt);
    int drop = baseline_ - cur;
    bool ok = (cnt >= cfg_.minSamples) && (drop >= cfg_.rssiDropDb);

    if (ok) {
        shutdownArmed_ = true;
        shutdownAt_ = millis() + 5000;         // let the client read the message first
        sendPage(
            "<div class=big>&#9989;&#127794;</div>"
            "<h1>Спасибо!</h1>"
            "<p>Вижу, сигнал упал на <code>" + String(drop) + " dB</code> "
            "(было " + String(baseline_) + ", стало " + String(cur) + " dBm). "
            "Договорились — выключаюсь. Эта сеть сейчас пропадёт. &#128075;</p>");
    } else {
        sendPage(
            "<div class=big>&#129300;</div>"
            "<h1>Пока не вижу снижения</h1>"
            "<p>Замерил всего <code>" + String(drop) + " dB</code> разницы "
            "(нужно ≥ <code>" + String(cfg_.rssiDropDb) + " dB</code>, образцов: " + String(cnt) + "). "
            "Точно снизил мощность? Убедись и попробуй ещё раз — и не двигай роутер/устройство.</p>"
            "<a class=btn href=\"/reduced\">Проверить снова</a>");
    }
}
