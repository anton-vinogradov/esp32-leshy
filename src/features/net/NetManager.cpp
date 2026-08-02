#include "NetManager.h"

#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <Preferences.h>
#include <string.h>

static DNSServer   s_dns;
static WebServer   s_web(80);
static IPAddress   s_apIp(192, 168, 4, 1);
static bool        s_pending = false;
static String      s_pendSsid, s_pendPass;
static String      s_scanHtml;

static const char* LAB_SSID_DEFAULT = "lower-your-wifi-power";

static String htmlEscape(const String& in) {       // for a single-quoted JS string (onclick handler)
    String o;
    for (size_t i = 0; i < in.length(); i++) {
        char c = in[i];
        if (c == '\'' || c == '\\') o += '\\';
        o += c;
    }
    return o;
}

void NetManager::begin() {
    // nothing to do eagerly; creds are read on demand (avoids radio use at boot)
}

bool NetManager::hasCreds() {
    Preferences p; p.begin("leshy", true);
    bool has = p.isKey("wifi_ssid");
    p.end();
    return has;
}

String NetManager::savedSsid() {
    Preferences p; p.begin("leshy", true);
    String s = p.getString("wifi_ssid", "");
    p.end();
    return s;
}

void NetManager::disconnect() {
    WiFi.disconnect(false);               // keep the driver up, just drop the association
}

void NetManager::forget() {
    WiFi.disconnect(false);
    Preferences p; p.begin("leshy", false);
    p.remove("wifi_ssid"); p.remove("wifi_pass");
    p.remove("my_ssid");   p.remove("my_bssid");
    p.end();
}

bool NetManager::connected() { return WiFi.status() == WL_CONNECTED; }
String NetManager::ip()      { return WiFi.localIP().toString(); }

bool NetManager::connect(uint32_t timeoutMs) {
    Preferences p; p.begin("leshy", true);
    String ssid = p.getString("wifi_ssid", "");
    String pass = p.getString("wifi_pass", "");
    p.end();
    if (ssid.isEmpty()) return false;

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid.c_str(), pass.c_str());
    uint32_t t = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - t) < timeoutMs) delay(100);
    if (WiFi.status() != WL_CONNECTED) { Serial.println("[Net] connect FAILED"); return false; }

    // learn & persist our own BSSID so the scanner can tag this network (★)
    uint8_t* b = WiFi.BSSID();
    Serial.printf("[Net] connected '%s' IP=%s BSSID=%02X:%02X:%02X:%02X:%02X:%02X\n",
                  ssid.c_str(), WiFi.localIP().toString().c_str(),
                  b ? b[0] : 0, b ? b[1] : 0, b ? b[2] : 0, b ? b[3] : 0, b ? b[4] : 0, b ? b[5] : 0);
    Preferences w; w.begin("leshy", false);
    w.putString("my_ssid", ssid);
    if (b) w.putBytes("my_bssid", b, 6);
    w.end();
    return true;
}

bool NetManager::isMine(const uint8_t bssid[6], String& ssidOut) {
    uint8_t mine[6];
    Preferences p; p.begin("leshy", true);
    size_t n = p.getBytes("my_bssid", mine, 6);
    String s = p.getString("my_ssid", "");
    p.end();
    if (n != 6) return false;
    if (memcmp(mine, bssid, 6) != 0) return false;
    ssidOut = s;
    return true;
}

// ---- provisioning ----

static void handleRoot() {
    String h = "<!doctype html><html><head><meta charset=utf-8>"
               "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
               "<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:20px}"
               "input{width:100%;box-sizing:border-box;padding:12px;margin:6px 0;font-size:16px;border-radius:8px;border:1px solid #444;background:#1c1c1c;color:#eee}"
               "button{width:100%;padding:14px;margin-top:10px;background:#2ecc71;color:#04240f;font-weight:700;border:0;border-radius:10px;font-size:16px}"
               "a{color:#8fd4ff;text-decoration:none} .net{display:block;padding:8px;border-bottom:1px solid #2a2a2a}</style></head><body>"
               "<h2>🌲 ESP32-Leshy — Wi-Fi</h2>"
               "<form action=\"/save\" method=\"get\">"
               "<input name=\"s\" id=\"s\" placeholder=\"Имя сети (SSID)\" autocapitalize=off autocorrect=off>"
               "<input name=\"p\" type=\"password\" placeholder=\"Пароль\">"
               "<button>Подключить</button></form>"
               "<p>Сети рядом — нажми, чтобы подставить имя (скрытую введи вручную):</p>";
    h += s_scanHtml;
    h += "</body></html>";
    s_web.send(200, "text/html; charset=utf-8", h);
}

static void handleSave() {
    s_pendSsid = s_web.arg("s");
    s_pendPass = s_web.arg("p");
    if (s_pendSsid.length()) s_pending = true;
    s_web.send(200, "text/html; charset=utf-8",
               "<!doctype html><meta charset=utf-8><body style='font-family:sans-serif;background:#111;color:#eee;padding:24px'>"
               "<h2>Сохранено ✅</h2><p>Отключаюсь от этой точки и подключаюсь к твоей сети — смотри на экран девайса.</p></body>");
}

static void handleNotFound() {
    s_web.sendHeader("Location", String("http://") + s_apIp.toString() + "/", true);
    s_web.send(302, "text/plain", "");
}

void NetManager::startProvision() {
    s_pending = false;
    // scan nearby networks first, build the clickable list
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);
    int n = WiFi.scanNetworks(false, true, false, 120);
    s_scanHtml = "";
    for (int i = 0; i < n && i < 20; i++) {
        String ss = WiFi.SSID(i);
        if (ss.isEmpty()) continue;
        s_scanHtml += "<a href=\"#\" class=net onclick=\"document.getElementById('s').value='" +
                      htmlEscape(ss) + "';return false\">" + ss + "  (" + String(WiFi.RSSI(i)) + ")</a>";
    }
    WiFi.scanDelete();

    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(s_apIp, s_apIp, IPAddress(255, 255, 255, 0));
    WiFi.softAP(apName());
    s_dns.start(53, "*", s_apIp);
    s_web.on("/", handleRoot);
    s_web.on("/save", handleSave);
    s_web.onNotFound(handleNotFound);
    s_web.begin();
    Serial.printf("[Net] provisioning AP '%s' up -> http://192.168.4.1 (%d networks listed)\n", apName(), n);
}

void NetManager::loopProvision() {
    s_dns.processNextRequest();
    s_web.handleClient();
}

bool NetManager::pendingConnect() { return s_pending; }

void NetManager::stopProvision() {
    s_web.stop();
    s_dns.stop();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_STA);
    // persist the submitted Wi-Fi creds (the Lab AP name is saved in handleSave already)
    if (s_pendSsid.length()) {
        Preferences p; p.begin("leshy", false);
        p.putString("wifi_ssid", s_pendSsid);
        p.putString("wifi_pass", s_pendPass);
        p.end();
    }
    s_pending = false;
}

String NetManager::labApName() {
    Preferences p; p.begin("leshy", true);
    String v = p.getString("lab_ssid", LAB_SSID_DEFAULT);
    p.end();
    return v;
}

void NetManager::saveLabApName(const String& name) {
    if (!name.length()) return;
    Preferences p; p.begin("leshy", false);
    p.putString("lab_ssid", name);
    p.end();
}
