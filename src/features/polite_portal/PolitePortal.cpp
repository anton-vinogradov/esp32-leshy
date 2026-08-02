#include "PolitePortal.h"

#include "../../core/i18n.h"

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
    PolitePortal* inst = s_instance;                    // snapshot: stop() may null it concurrently
    if (type != WIFI_PKT_MGMT || !inst) return;
    auto* pkt = (wifi_promiscuous_pkt_t*)buf;
    if (pkt->rx_ctrl.sig_len < 22) return;              // need pl[0] + addr3 (pl[16..21])
    const uint8_t* pl = pkt->payload;
    if (pl[0] != 0x80) return;                          // beacon subtype only
    if (memcmp(pl + 16, s_targetBssid, 6) != 0) return; // addr3 == target BSSID
    inst->pushSample(pkt->rx_ctrl.rssi);
}

void PolitePortal::pushSample(int8_t rssi) {
    uint32_t t = millis();                              // keep the critical section tiny
    portENTER_CRITICAL(&s_mux);
    ring_[head_ % CAP] = { t, rssi };
    head_++;
    portEXIT_CRITICAL(&s_mux);
}

int PolitePortal::medianWithin(uint32_t windowMs, int* countOut) {
    int8_t   tmp[CAP];
    int      n = 0;
    uint32_t now = millis();

    portENTER_CRITICAL(&s_mux);
    size_t total = head_ < CAP ? (size_t)head_ : CAP;
    for (size_t i = 0; i < total; i++) {
        if (now - ring_[i].t <= windowMs) tmp[n++] = ring_[i].rssi;
    }
    portEXIT_CRITICAL(&s_mux);

    if (countOut) *countOut = n;
    if (n == 0) return -127;
    std::sort(tmp, tmp + n);
    return tmp[n / 2];
}

bool PolitePortal::begin(const PolitePortalConfig& cfg) {
    cfg_ = cfg;
    s_instance = this;
    consented_ = false;
    shutdownArmed_ = false;
    setup_ = cfg_.setup;
    nameSubmitted_ = false;
    submittedName_ = "";

    // Consent mode (no target AP to watch): just raise the portal on our own named SoftAP
    // and stop when the visitor taps the button. No scan, no beacon sniffing, no RSSI.
    if (cfg_.targetSsid.isEmpty()) {
        WiFi.mode(WIFI_AP);
        WiFi.softAPConfig(apIp_, apIp_, IPAddress(255, 255, 255, 0));
        if (!WiFi.softAP(cfg_.portalSsid.c_str(), nullptr, cfg_.channel)) {
            WiFi.mode(WIFI_OFF); s_instance = nullptr; return false;
        }
        dns_.start(53, "*", apIp_);
        registerRoutes();
        web_.begin();
        running_ = true;
        baselineReady_ = true;                          // no baseline to wait for
        return true;
    }

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

    // 4) Bring the captive portal up first, so it answers even during baseline.
    dns_.start(53, "*", apIp_);
    registerRoutes();
    web_.begin();
    running_ = true;

    // 5) Baseline RSSI while the AP is (presumably) at full power. Serve the
    //    portal during the wait instead of dead-blocking the main thread.
    uint32_t t0 = millis();
    while ((int32_t)(millis() - (t0 + cfg_.baselineMs)) < 0) {
        dns_.processNextRequest();
        web_.handleClient();
        delay(5);
    }
    int c = 0, med = medianWithin(cfg_.baselineMs, &c);
    baseline_ = (c >= cfg_.minSamples) ? med : scanRssi;  // scan RSSI is a rough fallback
    if (c < cfg_.minSamples) {
        Serial.printf("[PolitePortal] warning: only %d baseline beacons - baseline is unreliable.\n", c);
    }
    baselineReady_ = true;
    return true;
}

void PolitePortal::loop() {
    if (!running_) return;
    dns_.processNextRequest();
    web_.handleClient();
    if (shutdownArmed_ && (int32_t)(millis() - shutdownAt_) >= 0) stop();
}

// Register the HTTP routes exactly once for this object's lifetime. WebServer::stop()
// closes the socket but does NOT drop the handler chain, so re-adding on every begin()
// would leak a std::function per route each time — register once, reuse across restarts.
void PolitePortal::registerRoutes() {
    if (routesRegistered_) return;
    web_.on("/", [this] { handleRoot(); });
    web_.on("/reduced", [this] { handleReduced(); });
    web_.on("/result", [this] { handleResult(); });
    web_.on("/savename", [this] { handleSaveName(); });   // setup mode form target
    web_.onNotFound([this] { redirectToPortal(); });   // pull OS captive checks to the page
    routesRegistered_ = true;
}

void PolitePortal::stop() {
    if (!running_) return;
    web_.stop();
    dns_.stop();
    esp_wifi_set_promiscuous(false);
    esp_wifi_set_promiscuous_rx_cb(nullptr);            // symmetry with airtime/deauth; don't leave our cb wired
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    baselineReady_ = false;
    shutdownArmed_ = false;                             // consented_ kept so the screen can show the final state; begin() resets it
    s_instance = nullptr;
}

void PolitePortal::redirectToPortal() {
    web_.sendHeader("Location", String("http://") + apIp_.toString() + "/", true);
    web_.send(302, "text/plain", "");
}

void PolitePortal::applyLangArg() {
    if (!web_.hasArg("lang")) return;
    String v = web_.arg("lang");
    if (v == "ru") i18n::set(Lang::RU);
    else if (v == "en") i18n::set(Lang::EN);
}

static const char* PAGE_CSS =
    "body{font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;"
    "margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}"
    ".card{max-width:440px;text-align:center}.big{font-size:52px;line-height:1}"
    "h1{margin:14px 0 8px}p{color:#cfcfcf;line-height:1.5}"
    "a.btn{display:inline-block;margin-top:22px;padding:16px 26px;background:#2ecc71;color:#04240f;"
    "font-weight:700;text-decoration:none;border-radius:12px}"
    "code{color:#8fd4ff}small{color:#888;display:block;margin-top:26px;line-height:1.5}"
    ".lang{margin-top:22px;font-size:13px;color:#666}.lang a{color:#8fd4ff;text-decoration:none;margin:0 5px}";

void PolitePortal::sendPage(const String& body, int refreshSec, const char* refreshUrl) {
    String html = String("<!doctype html><html lang=") + i18n::code() +
                  "><head><meta charset=utf-8>"
                  "<meta name=viewport content=\"width=device-width,initial-scale=1\">";
    if (refreshSec >= 0 && refreshUrl) {
        html += "<meta http-equiv=refresh content=\"" + String(refreshSec) + ";url=" + refreshUrl + "\">";
    }
    html += "<title>ESP32-Leshy</title><style>";
    html += PAGE_CSS;
    html += "</style></head><body><div class=card>" + body +
            "<div class=lang><a href=\"/?lang=en\">EN</a> &middot; <a href=\"/?lang=ru\">RU</a></div>"
            "</div></body></html>";
    web_.send(200, "text/html; charset=utf-8", html);
}

// Escape for a double-quoted HTML attribute value (the prefilled name).
static String attrEsc(const String& in) {
    String o;
    for (size_t i = 0; i < in.length(); i++) {
        char c = in[i];
        if      (c == '&') o += "&amp;";
        else if (c == '"') o += "&quot;";
        else if (c == '<') o += "&lt;";
        else if (c == '>') o += "&gt;";
        else o += c;
    }
    return o;
}

void PolitePortal::handleRoot() {
    applyLangArg();
    if (setup_) {                                   // setup mode: a form to name the portal AP
        String body =
            String("<div class=big>&#128295;</div><h1>") +
            i18n::tr("Portal AP name", "Имя точки портала") + "</h1><p>" +
            i18n::tr("Type the Wi-Fi name the Lab portal will broadcast, then save.",
                     "Впиши имя Wi-Fi, которое будет вещать портал Лаборатории, и сохрани.") +
            "</p><form action=\"/savename\" method=get style=\"margin-top:18px\">"
            "<input name=\"name\" value=\"" + attrEsc(cfg_.setupCurrent) + "\" autocapitalize=off autocorrect=off "
            "style=\"width:100%;box-sizing:border-box;padding:14px;font-size:16px;border-radius:10px;border:1px solid #444;background:#1c1c1c;color:#eee\">"
            "<button class=btn style=\"width:100%;margin-top:14px;border:0;cursor:pointer\">" +
            i18n::tr("Save", "Сохранить") + "</button></form>";
        sendPage(body);
        return;
    }
    String body =
        String("<div class=big>&#127794;&#128122;&#128246;</div><h1>") +
        i18n::tr("Hey, neighbor!", "Привет, сосед!") + "</h1><p>" +
        i18n::tr("Your Wi-Fi reaches me at full power and drowns out mine. Please open your "
                 "router settings and lower the transmit power (Tx Power) a notch or two.",
                 "Твой Wi-Fi добивает ко мне на полной мощности и глушит мой. Будь другом — зайди "
                 "в настройки роутера и снизь мощность передатчика (Tx Power) на пару делений.") +
        "</p><p>" +
        (cfg_.targetSsid.isEmpty()
            ? i18n::tr("When you have, tap the button and I'll leave you alone.",
                       "Как снизишь — жми кнопку, и я сразу отстану.")
            : i18n::tr("When you have, tap the button. I'll check the signal and leave you alone.",
                       "Как снизишь — жми кнопку. Я проверю по уровню сигнала и сразу отстану.")) +
        " &#128591;</p><a class=btn href=\"/reduced\">" +
        i18n::tr("I lowered the power", "Я снизил мощность") + "</a>";
    sendPage(body);
}

void PolitePortal::handleSaveName() {
    applyLangArg();
    if (!setup_) { redirectToPortal(); return; }        // only meaningful in setup mode
    String name = web_.arg("name");
    name.trim();
    if (!name.length()) {
        sendPage(String("<div class=big>&#9998;</div><h1>") +
                 i18n::tr("Empty name", "Пустое имя") + "</h1><p>" +
                 i18n::tr("Type a name, then save.", "Впиши имя и сохрани.") +
                 "</p><a class=btn href=\"/\">" + i18n::tr("Back", "Назад") + "</a>");
        return;
    }
    submittedName_ = name;
    nameSubmitted_ = true;
    shutdownArmed_ = true;
    shutdownAt_ = millis() + 4000;                      // show the confirmation, then drop the setup AP
    sendPage(String("<div class=big>&#9989;</div><h1>") +
             i18n::tr("Saved!", "Сохранено!") + "</h1><p>" +
             i18n::tr("The portal will broadcast this name. Setup network is closing now.",
                      "Портал будет вещать это имя. Настроечная сеть закрывается.") + "</p>");
}

void PolitePortal::handleReduced() {
    applyLangArg();
    if (setup_) { redirectToPortal(); return; }         // /reduced has no meaning in setup mode
    if (cfg_.targetSsid.isEmpty()) {                    // consent mode: the tap IS the result
        consented_ = true;
        shutdownArmed_ = true;
        shutdownAt_ = millis() + 6000;                  // let them read the thanks, then drop the AP
        sendPage(String("<div class=big>&#9989;&#127794;</div><h1>") +
                 i18n::tr("Thank you!", "Спасибо!") + "</h1><p>" +
                 i18n::tr("Deal - I'm shutting this network down now. Take care! ",
                          "Договорились — выключаю эту сеть. Бывай! ") + "&#128075;</p>");
        return;
    }
    if (!baselineReady_) {
        sendPage(String("<div class=big>&#9203;</div><h1>") +
                     i18n::tr("Calibrating...", "Калибруюсь…") + "</h1><p>" +
                     i18n::tr("Still taking the first reading. One moment.",
                              "Первичный замер эфира ещё идёт. Секунду.") + "</p>",
                 3, "/reduced");
        return;
    }
    int wait = (int)(cfg_.windowMs / 1000) + 1;
    sendPage(String("<div class=big>&#9203;</div><h1>") +
                 i18n::tr("Checking...", "Проверяю…") + "</h1><p>" +
                 i18n::tr("Listening for a few seconds and comparing to the baseline. "
                          "Don't move the devices or close the page.",
                          "Слушаю эфир несколько секунд и сравниваю с исходным уровнем. "
                          "Не двигай устройства и не закрывай страницу.") + "</p>",
             wait, "/result");
}

void PolitePortal::handleResult() {
    applyLangArg();
    if (!baselineReady_) { handleReduced(); return; }   // still calibrating

    int cnt = 0;
    int cur = medianWithin(cfg_.windowMs, &cnt);

    if (cnt < cfg_.minSamples) {                         // not enough beacons to judge — no bogus drop
        sendPage(String("<div class=big>&#128064;</div><h1>") +
                 i18n::tr("Not enough data yet", "Пока мало данных") + "</h1><p>" +
                 i18n::tr("Caught only ", "Поймал пока образцов: ") + String(cnt) +
                 i18n::tr(" beacons so far. Keep the device still and try again.",
                          " — держи устройство на месте и попробуй ещё раз.") + "</p>" +
                 "<a class=btn href=\"/reduced\">" + i18n::tr("Check again", "Проверить снова") + "</a>");
        return;
    }

    int drop = baseline_ - cur;
    if (drop >= cfg_.rssiDropDb) {
        shutdownArmed_ = true;
        shutdownAt_ = millis() + 5000;                  // let the client read the message first
        sendPage(String("<div class=big>&#9989;&#127794;</div><h1>") +
                 i18n::tr("Thank you!", "Спасибо!") + "</h1><p>" +
                 i18n::tr("The signal dropped by ", "Вижу, сигнал упал на ") + "<code>" + String(drop) +
                 i18n::tr(" dB</code> (from ", " dB</code> (было ") + String(baseline_) +
                 i18n::tr(" to ", ", стало ") + String(cur) +
                 i18n::tr(" dBm). Deal - shutting down. This network will disappear now. ",
                          " dBm). Договорились — выключаюсь. Эта сеть сейчас пропадёт. ") +
                 "&#128075;</p>");
    } else {
        sendPage(String("<div class=big>&#129300;</div><h1>") +
                 i18n::tr("No drop yet", "Пока не вижу снижения") + "</h1><p>" +
                 i18n::tr("Measured only ", "Замерил всего ") + "<code>" + String(drop) +
                 i18n::tr(" dB</code> (need &ge; ", " dB</code> (нужно ≥ ") + "<code>" + String(cfg_.rssiDropDb) +
                 i18n::tr(" dB</code>). Did you really lower it? Make sure, and don't move the router/device.",
                          " dB</code>). Точно снизил мощность? Убедись и не двигай роутер/устройство.") +
                 "</p><a class=btn href=\"/reduced\">" + i18n::tr("Check again", "Проверить снова") + "</a>");
    }
}
