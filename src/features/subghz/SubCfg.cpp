#include "SubCfg.h"

#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <Preferences.h>

static DNSServer s_dns;
static WebServer s_web(80);
static IPAddress s_ip(192, 168, 4, 1);
static SubCfg*   s_self = nullptr;

// Current saved values (defaults match main.cpp's loaders).
static uint32_t cfgWaitMs()  { Preferences p; p.begin("leshy", true); uint32_t v = p.getUInt("rec_wait", 30000); p.end(); return v; }
static uint32_t cfgFreqKHz() { Preferences p; p.begin("leshy", true); uint32_t v = p.getUInt("sub_freq", 0);     p.end(); return v; }
static int      cfgThr()     { Preferences p; p.begin("leshy", true); int v = p.getInt("cap_thr", -72);          p.end(); return v; }
static int      cfgRep()     { Preferences p; p.begin("leshy", true); int v = p.getUChar("rep_n", 3);            p.end(); return v; }
static bool     cfgFsk()     { Preferences p; p.begin("leshy", true); bool v = p.getUChar("sub_mod", 0) != 0;    p.end(); return v; }
static bool     cfgInv()     { Preferences p; p.begin("leshy", true); bool v = p.getBool("sub_inv", false);      p.end(); return v; }

static bool freqTunable(uint32_t k) {              // CC1101 tunes only these sub-bands
    return (k >= 300000 && k <= 348000) || (k >= 387000 && k <= 464000) || (k >= 779000 && k <= 928000);
}

static String freqField() {                        // MHz (3 decimals), or blank when "use band"
    uint32_t k = cfgFreqKHz();
    if (!k) return "";
    char b[16]; snprintf(b, sizeof(b), "%lu.%03lu", (unsigned long)(k / 1000), (unsigned long)(k % 1000));
    return String(b);
}

void SubCfg::handleRoot() {
    String h = "<!doctype html><html><head><meta charset=utf-8>"
               "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
               "<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:20px}"
               "label{display:block;margin:14px 0 4px;color:#9a9;font-size:14px}"
               "input,select{width:100%;box-sizing:border-box;padding:12px;font-size:16px;border-radius:8px;border:1px solid #444;background:#1c1c1c;color:#eee}"
               ".row{display:flex;align-items:center;gap:8px;margin-top:14px}.row input{width:auto}"
               "button{width:100%;padding:16px;margin-top:18px;background:#2ecc71;color:#04240f;font-weight:700;border:0;border-radius:12px;font-size:16px}</style>"
               "</head><body><h2>🌲 Sub-GHz</h2><form action=\"/save\" method=get>"
               "<label>Ожидание сигнала (сек)</label><input name=wait type=number min=3 max=300 value=" + String(cfgWaitMs() / 1000) + ">"
               "<label>Частота (МГц, пусто = центр бэнда)</label><input name=freq inputmode=decimal placeholder=433.92 value=\"" + freqField() + "\">"
               "<label>Порог захвата (dBm, ниже = чувствительнее)</label><input name=thr type=number min=-110 max=-30 value=" + String(cfgThr()) + ">"
               "<label>Повторов при воспроизведении</label><input name=rep type=number min=1 max=20 value=" + String(cfgRep()) + ">"
               "<label>Модуляция</label><select name=mod>"
               "<option value=ook" + String(cfgFsk() ? "" : " selected") + ">OOK (пульты)</option>"
               "<option value=fsk" + String(cfgFsk() ? " selected" : "") + ">2-FSK (датчики)</option></select>"
               "<div class=row><input type=checkbox name=inv id=inv " + String(cfgInv() ? "checked" : "") + "><label for=inv style='margin:0'>Инверсия полярности повтора</label></div>"
               "<button>Сохранить</button></form></body></html>";
    s_web.send(200, "text/html; charset=utf-8", h);
}

void SubCfg::handleSave() {
    Preferences p; p.begin("leshy", false);
    long wait = s_web.arg("wait").toInt(); if (wait < 3) wait = 3; if (wait > 300) wait = 300;
    p.putUInt("rec_wait", (uint32_t)wait * 1000);
    String f = s_web.arg("freq"); f.trim();
    uint32_t fk = f.length() ? (uint32_t)(f.toFloat() * 1000.0f + 0.5f) : 0;
    if (fk && !freqTunable(fk)) fk = 0;             // out of the CC1101's tunable sub-bands → fall back to band centre
    p.putUInt("sub_freq", fk);
    long thr = s_web.arg("thr").toInt(); if (thr < -110) thr = -110; if (thr > -30) thr = -30;
    p.putInt("cap_thr", (int)thr);
    long rep = s_web.arg("rep").toInt(); if (rep < 1) rep = 1; if (rep > 20) rep = 20;
    p.putUChar("rep_n", (uint8_t)rep);
    p.putUChar("sub_mod", s_web.arg("mod") == "fsk" ? 1 : 0);
    p.putBool("sub_inv", s_web.hasArg("inv"));
    p.end();
    saved_ = true;
    armed_ = true; at_ = millis() + 4000;          // show the confirmation, then drop the AP
    s_web.send(200, "text/html; charset=utf-8",
               "<!doctype html><meta charset=utf-8><body style='font-family:sans-serif;background:#111;color:#eee;padding:24px'>"
               "<h2>Сохранено ✅</h2><p>Настройки применены. Сеть закрывается — вернись к устройству.</p></body>");
}

void SubCfg::redirect() {
    s_web.sendHeader("Location", String("http://") + s_ip.toString() + "/", true);
    s_web.send(302, "text/plain", "");
}

bool SubCfg::begin() {
    s_self = this;
    saved_ = false; armed_ = false;
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(s_ip, s_ip, IPAddress(255, 255, 255, 0));
    if (!WiFi.softAP(apName())) { WiFi.mode(WIFI_OFF); s_self = nullptr; return false; }
    s_dns.start(53, "*", s_ip);
    if (!routes_) {                                // register once (WebServer::stop keeps handlers)
        s_web.on("/", []() { if (s_self) s_self->handleRoot(); });
        s_web.on("/save", []() { if (s_self) s_self->handleSave(); });
        s_web.onNotFound([]() { if (s_self) s_self->redirect(); });
        routes_ = true;
    }
    s_web.begin();
    running_ = true;
    return true;
}

void SubCfg::loop() {
    if (!running_) return;
    s_dns.processNextRequest();
    s_web.handleClient();
    if (armed_ && (int32_t)(millis() - at_) >= 0) stop();
}

void SubCfg::stop() {
    if (!running_) return;
    s_web.stop();
    s_dns.stop();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    running_ = false;
    armed_ = false;
}
