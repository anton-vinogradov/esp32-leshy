#include <Arduino.h>

#include "core/i18n.h"
#include "features/wifi_scanner/WifiScanner.h"
#include "features/deauth_detector/DeauthDetector.h"
#include "features/ble_scanner/BleScanner.h"
#include "features/polite_portal/PolitePortal.h"
#include "features/signal_finder/SignalFinder.h"
#include "features/display/Display.h"
#include "features/display/BootScreen.h"
#include "features/display/WifiScreen.h"
#include "features/display/BleScreen.h"
#include "features/display/MenuScreen.h"
#include "features/display/Fonts.h"
#include "features/scan/ScanEngine.h"
#include "features/net/NetManager.h"
#include "features/input/Buttons.h"
#include "features/input/Touch.h"

// Headless demo selector until the real menu (Phase 0) lands. Edit DEMO to switch.
#define DEMO_WIFI_SCANNER    1
#define DEMO_DEAUTH_DETECTOR 2
#define DEMO_BLE_SCANNER     3
#define DEMO_SIGNAL_FINDER   4
#define DEMO_POLITE_PORTAL   5
#define DEMO_DISPLAY         6
#define DEMO_DASHBOARD       7
#define DEMO_BTNTEST         8
#define DEMO_TOUCHCAL        9
#ifndef DEMO                      // override at build time: pio run -DDEMO=3
#define DEMO DEMO_DASHBOARD
#endif

// The app is bilingual (EN/RU). Startup default; menu/portal switch at runtime.
static constexpr Lang UI_LANG = Lang::RU;

// Point this at YOUR OWN access point (Signal Finder / Polite Portal only).
// Educational / own-equipment use only — see DISCLAIMER.md.
static const char* TARGET_SSID = "MyOwnAP";

#if DEMO == DEMO_WIFI_SCANNER || DEMO == DEMO_DEAUTH_DETECTOR
static void macStr(const uint8_t* m, char* out) {
    sprintf(out, "%02X:%02X:%02X:%02X:%02X:%02X", m[0], m[1], m[2], m[3], m[4], m[5]);
}
#endif

#if DEMO == DEMO_WIFI_SCANNER

WifiScanner scanner;

void setup() {
    Serial.begin(115200);
    delay(300);
    i18n::set(UI_LANG);
    Serial.println(i18n::tr("[WifiScanner] scanning...", "[WifiScanner] сканирую..."));
}

void loop() {
    int n = scanner.scan();
    Serial.printf("\n%s: %d\n", i18n::tr("networks", "сетей"), n);
    for (int i = 0; i < n; i++) {
        const WifiAp& a = scanner.at(i);
        char bssid[18];
        macStr(a.bssid, bssid);
        Serial.printf("%2d  ch%-2d %4d dBm  %-7s  %s  %s\n", i + 1, a.channel, a.rssi,
                      WifiScanner::authName(a.auth), bssid,
                      a.ssid.length() ? a.ssid.c_str() : i18n::tr("<hidden>", "<скрытая>"));
    }
    delay(5000);
}

#elif DEMO == DEMO_DEAUTH_DETECTOR

DeauthDetector detector;

void setup() {
    Serial.begin(115200);
    delay(300);
    i18n::set(UI_LANG);
    if (!detector.begin()) {
        Serial.println(i18n::tr("[DeauthDetector] failed to start promiscuous monitor.",
                                "[DeauthDetector] не удалось запустить монитор."));
        return;
    }
    Serial.println(i18n::tr("[DeauthDetector] passive monitor, hopping channels...",
                            "[DeauthDetector] пассивный монитор, перебираю каналы..."));
}

void loop() {
    detector.loop();
    static uint32_t next = 0;
    if ((int32_t)(millis() - next) >= 0) {
        next = millis() + 2000;
        int recent = detector.recentCount();
        DeauthEvent e;
        if (detector.alerting() && detector.lastEvent(e)) {
            char src[18];
            macStr(e.src, src);
            Serial.printf("!! %s: %d/%lus  ch%d  %s %s\n",
                          i18n::tr("DEAUTH ALERT", "ТРЕВОГА DEAUTH"), recent,
                          (unsigned long)(detector.windowMs() / 1000), e.channel,
                          i18n::tr("from", "от"), src);
        } else {
            Serial.printf("%s: %lu  (ch%d, %d/%lus)\n",
                          i18n::tr("total deauth/disassoc", "всего deauth/disassoc"),
                          (unsigned long)detector.total(), detector.channel(), recent,
                          (unsigned long)(detector.windowMs() / 1000));
        }
    }
}

#elif DEMO == DEMO_BLE_SCANNER

BleScanner ble;

void setup() {
    Serial.begin(115200);
    delay(300);
    i18n::set(UI_LANG);
    ble.begin();
    Serial.println(i18n::tr("[BleScanner] scanning BLE...", "[BleScanner] сканирую BLE..."));
}

void loop() {
    int n = ble.scan(5);
    Serial.printf("\n%s: %d\n", i18n::tr("BLE devices", "BLE-устройств"), n);
    for (int i = 0; i < n; i++) {
        const BleDev& d = ble.at(i);
        String flag = d.tracker.length() ? (String("<< ") + d.tracker) : String("");
        Serial.printf("%2d  %4d dBm  %-18s  %-16s %s\n", i + 1, d.rssi, d.mac.c_str(),
                      d.name.length() ? d.name.c_str() : "-", flag.c_str());
    }
    delay(2000);
}

#elif DEMO == DEMO_SIGNAL_FINDER

SignalFinder finder;

static String needleBar(int r, int farRssi, int nearRssi, int width) {
    if (r <= -127) return String(i18n::tr("searching...", "поиск..."));
    int filled = map(constrain(r, farRssi, nearRssi), farRssi, nearRssi, 0, width);
    String s;
    for (int i = 0; i < width; i++) s += (i < filled) ? '#' : '.';
    return s;
}

void setup() {
    Serial.begin(115200);
    delay(300);
    i18n::set(UI_LANG);

    SignalFinderConfig cfg;
    cfg.targetSsid = TARGET_SSID;
    Serial.printf("[SignalFinder] %s '%s'...\n", i18n::tr("looking for", "ищу"), TARGET_SSID);
    if (!finder.begin(cfg)) {
        Serial.printf("[SignalFinder] '%s' %s\n", TARGET_SSID,
                      i18n::tr("not found - check the SSID.", "не найдена - проверь SSID."));
        return;
    }
    Serial.println(i18n::tr("[SignalFinder] locked on target. Walk around - warmer = closer.",
                            "[SignalFinder] цель захвачена. Ходи вокруг - теплее = ближе."));
}

void loop() {
    finder.loop();
    static uint32_t nextPrint = 0;
    if ((int32_t)(millis() - nextPrint) >= 0) {
        nextPrint = millis() + 300;
        int r = finder.reading(), t = finder.trend();
        const char* arrow = (r <= -127) ? ""
                          : (t > 1 ? i18n::tr("  ^ warmer", "  ^ теплее")
                          : (t < -1 ? i18n::tr("  v colder", "  v холоднее")
                                    : i18n::tr("  = steady", "  = ровно")));
        Serial.printf("%5d dBm [%s]%s\n", r, needleBar(r, -90, -40, 20).c_str(), arrow);
    }
}

#elif DEMO == DEMO_POLITE_PORTAL

PolitePortal portal;

void setup() {
    Serial.begin(115200);
    delay(300);
    i18n::set(UI_LANG);

    PolitePortalConfig cfg;
    cfg.targetSsid = TARGET_SSID;
    if (!portal.begin(cfg)) {
        Serial.printf("[PolitePortal] '%s' %s\n", TARGET_SSID,
                      i18n::tr("not found - check the SSID.", "не найдена - проверь SSID."));
        return;
    }
    Serial.printf("[PolitePortal] %s %d dBm. %s '%s'.\n",
                  i18n::tr("up. baseline =", "запущен. базовый уровень ="), portal.baselineRssi(),
                  i18n::tr("Join Wi-Fi", "Подключись к Wi-Fi"), cfg.portalSsid.c_str());
}

void loop() { portal.loop(); }

#elif DEMO == DEMO_DISPLAY

BootScreen bootScreen;

void setup() {
    Serial.begin(115200);
    delay(300);
    displayInit();
    bootScreen.show();
    Serial.println("[BootScreen] drawn — if the TFT is still white, the pin map is off.");
}

void loop() {}

#elif DEMO == DEMO_DASHBOARD

#include <Preferences.h>

#include "features/wifi_scanner/HiddenRevealer.h"

ScanEngine     engine;
WifiScreen     wifiScreen;
BleScreen      bleScreen;
MenuScreen     menuScreen;
Buttons        buttons;
NetManager     net;
HiddenRevealer revealer;

static void drawNetBadge();      // small "connected" mark in the header (defined below)

// ---- menu tree ----
enum { M_ROOT, M_WIFI, M_BLE, M_SUBGHZ, M_SETTINGS, M_LANG };
enum { F_WIFI_SCAN, F_CONN, F_HIDDEN, F_BLE_SCAN, F_SUBGHZ_SOON, F_RECAL, F_ABOUT, F_LANG_EN, F_LANG_RU };
static const uint8_t K_SUB = 0, K_FEAT = 1;

static const MenuItem ROOT_I[] = {
    {"Wi-Fi",    "Scan networks",            "Wi-Fi",     "Сканирование сетей",       K_SUB, M_WIFI},
    {"BLE",      "Bluetooth devices & tags", "BLE",       "Устройства и метки",       K_SUB, M_BLE},
    {"Sub-GHz",  "315/433/868 MHz radio",    "Sub-GHz",   "Радио 315/433/868 МГц",    K_SUB, M_SUBGHZ},
    {"Settings", "Language, touch, about",   "Настройки", "Язык, тач, о девайсе",     K_SUB, M_SETTINGS},
};
static const MenuItem WIFI_I[] = {
    {"Wi-Fi Scan",   "Signal, channel, lock", "Скан Wi-Fi",   "Сигнал, канал, шифр", K_FEAT, F_WIFI_SCAN},
    {"Connection",   "Status, join, exit",    "Подключение",  "Статус, вход, выход", K_FEAT, F_CONN},
    {"Hidden names", "Revealed hidden SSIDs", "Скрытые сети", "Раскрытые имена",     K_FEAT, F_HIDDEN},
};
static const MenuItem BLE_I[] = {
    {"BLE Scan", "Devices & trackers nearby", "Скан BLE", "Устройства и трекеры рядом", K_FEAT, F_BLE_SCAN},
};
static const MenuItem SUB_I[] = {
    {"Recorder", "Record RF signals (soon)", "Запись", "Запись сигналов (скоро)", K_FEAT, F_SUBGHZ_SOON},
};
static const MenuItem SET_I[] = {
    {"Language",        "Interface language",      "Язык",       "Язык интерфейса",       K_SUB,  M_LANG},
    {"Calibrate touch", "Redo screen calibration", "Калибровка", "Перекалибровать экран", K_FEAT, F_RECAL},
    {"About",           "About ESP32-Leshy",       "О девайсе",  "Об ESP32-Leshy",        K_FEAT, F_ABOUT},
};
static const MenuItem LANG_I[] = {
    {"English", "", "English", "", K_FEAT, F_LANG_EN},
    {"Русский", "", "Русский", "", K_FEAT, F_LANG_RU},
};
static const Menu MENUS[] = {
    {"ESP32-Leshy", "ESP32-Leshy", ROOT_I, 4},
    {"Wi-Fi",       "Wi-Fi",       WIFI_I, 3},
    {"BLE",         "BLE",         BLE_I,  1},
    {"Sub-GHz",     "Sub-GHz",     SUB_I,  1},
    {"Settings",    "Настройки",   SET_I,  3},
    {"Language",    "Язык",        LANG_I, 2},
};

// ---- navigation state ----
enum State { ST_MENU, ST_WIFI, ST_BLE, ST_INFO, ST_PROVISION, ST_CONN, ST_HIDDEN, ST_CONFIRM, ST_OPTIONS };
static State    st = ST_MENU;
static int      menuStack[6] = { M_ROOT };   // path of open menus (for back)
static int      selStack[6]  = { 0 };        // selection per level
static int      depth = 0;
static int      off = 0;
static uint32_t seenWifiGen = 0, seenBleGen = 0;
static bool     touchDown = false;
static String   infoTitle, infoBody, infoNote;

static int  curMenu() { return menuStack[depth]; }
static int& curSel()  { return selStack[depth]; }
// In a menu the radios are idle — scanning only runs on a scan screen.
static void showMenu() { engine.pause(); st = ST_MENU; menuScreen.show(&MENUS[curMenu()], curSel()); drawNetBadge(); }

static void saveLang(Lang l) { Preferences p; p.begin("leshy", false); p.putUChar("lang", (uint8_t)l); p.end(); }
static Lang loadLang() { Preferences p; p.begin("leshy", true); uint8_t v = p.getUChar("lang", (uint8_t)UI_LANG); p.end(); return (Lang)v; }

static int  listCount() { return st == ST_WIFI ? engine.wifiCount() : engine.bleCount(); }
static void drawList(bool full) {
    if (st == ST_WIFI) { if (full) wifiScreen.draw(engine, off); else wifiScreen.rows(engine, off); }
    else               { if (full) bleScreen.draw(engine, off);  else bleScreen.rows(engine, off); }
}

static void drawInfo() {
    uiHeaderRu(infoTitle.c_str());
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    fontSmall();
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tft.color565(0xe8, 0xe8, 0xe0), uiBg());
    tft.drawString(infoBody, 10, 50);
    tft.setTextColor(tft.color565(0xff, 0xcf, 0x3f), uiBg());
    tft.drawString(infoNote, 10, 80);
    uiFooterRu(i18n::isRu() ? "НАЗАД: LEFT" : "LEFT: back");
    fontOff();
    drawNetBadge();
}

static void drawProvisionScreen() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xe7, 0xcf, 0x8f);
    uiHeaderRu(i18n::tr("Wi-Fi setup", "Настройка Wi-Fi"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("1. Join Wi-Fi:", "1. Подключись к Wi-Fi:"), 10, 46);
    fontBig();   tft.setTextColor(gold, bg);
    tft.drawString(NetManager::apName(), 10, 68);
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("2. Open in browser:", "2. Открой в браузере:"), 10, 112);
    fontBig();   tft.setTextColor(gold, bg);
    tft.drawString("192.168.4.1", 10, 134);
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("3. Pick network + password", "3. Выбери сеть + пароль"), 10, 178);
    uiFooterRu(i18n::tr("LEFT: cancel", "LEFT: отмена"));
    fontOff();
}

// Small "connected" mark in the top-right of the header: three gold bars, drawn
// only while actually associated. Scanning drops the link, so it honestly
// disappears on the scan screens.
static void drawNetBadge() {
    if (!net.connected()) return;
    const uint16_t gold = tft.color565(0xff, 0xcf, 0x3f);
    int x = 210, base = 21;
    tft.fillRect(x,      base - 6,  4, 6,  gold);
    tft.fillRect(x + 6,  base - 10, 4, 10, gold);
    tft.fillRect(x + 12, base - 14, 4, 14, gold);
}

// ---- hidden (revealed) SSID list ----
static const int HID_TOP = 40, HID_ROW_H = 30, HID_VISIBLE = 8;
static int hidSel = 0, hidOff = 0, hidRowY[HID_VISIBLE];

// One list row, repainted in place (fills only its own rectangle — no full-screen clear).
static void drawHiddenRow(int slot) {
    fontOff();                    // rows use the built-in fonts (2/1); drop any smooth font first
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    int n   = revealer.count();
    int idx = hidOff + slot;
    int y   = HID_TOP + slot * HID_ROW_H;
    hidRowY[slot] = (idx < n) ? y : -1;
    tft.fillRect(0, y, 240, HID_ROW_H, bg);
    if (idx >= n) return;
    uint8_t b[6]; String ss;
    revealer.get(idx, b, ss);
    bool sel = (idx == hidSel);
    uint16_t rowbg = sel ? tft.color565(0x22, 0x33, 0x22) : bg;
    if (sel) tft.fillRoundRect(6, y, 228, HID_ROW_H - 4, 6, rowbg);
    if (ss.length() > 18) ss = ss.substring(0, 17) + "~";
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(sel ? gold : white, rowbg);
    tft.drawString(ss, 12, y + 1, 2);
    char mac[18];
    snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X", b[0], b[1], b[2], b[3], b[4], b[5]);
    tft.setTextColor(dim, rowbg);
    tft.drawString(mac, 12, y + 16, 1);
}

static void clampHidden() {
    int n = revealer.count();
    if (hidSel > n - 1) hidSel = n - 1;
    if (hidSel < 0) hidSel = 0;
    if (hidSel < hidOff) hidOff = hidSel;                      // stop when the screen would start to empty
    if (hidSel >= hidOff + HID_VISIBLE) hidOff = hidSel - HID_VISIBLE + 1;
    if (hidOff < 0) hidOff = 0;
}

static void drawHiddenRowsOnly() { for (int s = 0; s < HID_VISIBLE; s++) drawHiddenRow(s); }

static void drawHiddenScreen() {
    const uint16_t bg = uiBg();
    const uint16_t dim = tft.color565(0x8f, 0xa9, 0x8f);
    int n = revealer.count();
    uiHeaderRu(i18n::tr("Hidden names", "Скрытые сети"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    if (n == 0) {
        fontSmall();
        tft.setTextDatum(TL_DATUM); tft.setTextColor(dim, bg);
        tft.drawString(i18n::tr("Empty yet.", "Пока пусто."), 12, 70);
        tft.drawString(i18n::tr("Scan near a hidden", "Сканируй рядом со"), 12, 96);
        tft.drawString(i18n::tr("network to reveal.", "скрытой сетью."), 12, 118);
        uiFooterRu(i18n::isRu() ? "LEFT назад" : "LEFT back");
        fontOff(); drawNetBadge(); return;
    }
    clampHidden();
    drawHiddenRowsOnly();
    uiFooterRu(i18n::isRu() ? "LEFT назад  вправо опции" : "LEFT back  right options");
    drawNetBadge();
}

static void gotoHidden() { Serial.printf("[Hidden] screen opened: count=%d\n", revealer.count()); st = ST_HIDDEN; drawHiddenScreen(); }

// ---- connection screen (one menu item: full status + contextual actions) ----
enum ConnAct { CA_SETUP, CA_CONNECT, CA_DISCONNECT, CA_FORGET };
static ConnAct connActs[4];
static int     connActN = 0, connSel = 0, connActY[4];

static void buildConnActions() {
    connActN = 0;
    bool has = net.hasCreds(), on = net.connected();
    if (!has) { connActs[connActN++] = CA_SETUP; }
    else {
        connActs[connActN++] = on ? CA_DISCONNECT : CA_CONNECT;
        connActs[connActN++] = CA_SETUP;
        connActs[connActN++] = CA_FORGET;
    }
    if (connSel >= connActN) connSel = 0;
}

static const char* connLabel(ConnAct a) {
    switch (a) {
        case CA_SETUP:      return i18n::tr("Set up (phone)", "Настроить (телефон)");
        case CA_CONNECT:    return i18n::tr("Connect",        "Подключиться");
        case CA_DISCONNECT: return i18n::tr("Disconnect",     "Отключиться");
        case CA_FORGET:     return i18n::tr("Forget network", "Забыть сеть");
    }
    return "";
}

// Reusable action button, repainted in place (fills only its own rectangle).
static void drawActionBtn(int y, const char* label, bool sel) {
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    uint16_t box = sel ? tft.color565(0x2c, 0x5a, 0x2c) : tft.color565(0x1b, 0x27, 0x1b);
    tft.fillRoundRect(10, y, 220, 34, 8, box);
    fontSmall();
    tft.setTextColor(sel ? gold : white, box);
    tft.setTextDatum(ML_DATUM);
    tft.drawString(label, 22, y + 17);
    fontOff();
}

static void drawConnScreen() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    uiHeaderRu(i18n::tr("Connection", "Подключение"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall();
    int y = 44;
    bool has = net.hasCreds(), on = net.connected();
    if (on) {
        tft.setTextColor(gold, bg);  tft.drawString(i18n::tr("Connected:", "Подключено:"), 10, y); y += 24;
        tft.setTextColor(white, bg); tft.drawString(net.savedSsid(), 12, y); y += 22;
        tft.setTextColor(dim, bg);   tft.drawString("IP " + net.ip(), 12, y); y += 26;
    } else if (has) {
        tft.setTextColor(white, bg); tft.drawString(i18n::tr("Saved network:", "Сохранённая сеть:"), 10, y); y += 24;
        tft.setTextColor(gold, bg);  tft.drawString(net.savedSsid(), 12, y); y += 22;
        tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("not connected", "не подключено"), 12, y); y += 26;
    } else {
        tft.setTextColor(white, bg); tft.drawString(i18n::tr("Not set up", "Не настроено"), 10, y); y += 24;
        tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("add via phone below", "настрой с телефона ниже"), 12, y); y += 26;
    }
    y += 6;
    fontOff();
    for (int i = 0; i < connActN; i++) { connActY[i] = y; drawActionBtn(y, connLabel(connActs[i]), i == connSel); y += 42; }
    uiFooterRu(i18n::isRu() ? "LEFT назад  OK выбор" : "LEFT back  OK select");
    fontOff();
    drawNetBadge();
}

static void gotoConn() { buildConnActions(); st = ST_CONN; drawConnScreen(); }

// ---- confirm dialog (destructive actions) ----
enum PendKind { PK_NONE, PK_FORGET, PK_DEL_HIDDEN };
static PendKind pendKind = PK_NONE;
static int      pendIdx = 0;
static State    confirmReturn = ST_MENU;
static String   confirmMsg, confirmSub;
static const int okBtnY = 214, cancelBtnY = 262;

static void drawConfirm() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t okbg  = tft.color565(0x7a, 0x25, 0x25);
    const uint16_t cbg   = tft.color565(0x22, 0x2a, 0x22);
    uiHeaderRu(i18n::tr("Confirm", "Подтверждение"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall();
    tft.setTextColor(white, bg); tft.drawString(confirmMsg, 12, 74);
    tft.setTextColor(gold, bg);  tft.drawString(confirmSub, 12, 104);
    tft.fillRoundRect(10, okBtnY, 220, 40, 8, okbg);
    tft.setTextDatum(MC_DATUM); tft.setTextColor(white, okbg);
    tft.drawString(i18n::tr("OK (middle)", "OK (средняя)"), 120, okBtnY + 20);
    tft.fillRoundRect(10, cancelBtnY, 220, 40, 8, cbg);
    tft.setTextColor(white, cbg);
    tft.drawString(i18n::tr("Cancel (LEFT)", "Отмена (LEFT)"), 120, cancelBtnY + 20);
    fontOff();
}

static void askConfirm(PendKind kind, int idx, const char* msg, const String& sub, State ret) {
    pendKind = kind; pendIdx = idx; confirmMsg = msg; confirmSub = sub; confirmReturn = ret;
    st = ST_CONFIRM; drawConfirm();
}

static void doConfirm() {
    switch (pendKind) {
        case PK_FORGET:     net.forget();             break;
        case PK_DEL_HIDDEN: revealer.remove(pendIdx); break;
        default: break;
    }
    pendKind = PK_NONE;
    if (confirmReturn == ST_HIDDEN) gotoHidden(); else gotoConn();
}

static void cancelConfirm() {
    pendKind = PK_NONE;
    if (confirmReturn == ST_HIDDEN) gotoHidden(); else gotoConn();
}

static void connActivate() {
    switch (connActs[connSel]) {
        case CA_SETUP: net.startProvision(); st = ST_PROVISION; drawProvisionScreen(); break;
        case CA_CONNECT:
            infoTitle = i18n::tr("Connecting...", "Подключение..."); infoBody = net.savedSsid(); infoNote = "";
            st = ST_INFO; drawInfo();
            net.connect();
            gotoConn();
            break;
        case CA_DISCONNECT: net.disconnect(); connSel = 0; gotoConn(); break;
        case CA_FORGET:     askConfirm(PK_FORGET, 0, i18n::tr("Forget this network?", "Забыть эту сеть?"), net.savedSsid(), ST_CONN); break;
    }
}

// ---- options menu (RIGHT opens context actions for the selected item) ----
enum OptId { OPT_DEL_HIDDEN };
static OptId       optIds[4];
static const char* optLabels[4];
static int         optN = 0, optSel = 0, optY[4];
static State       optReturn = ST_MENU;
static String      optTitle;

static void drawOptionsScreen() {
    const uint16_t bg = uiBg();
    const uint16_t dim = tft.color565(0x8f, 0xa9, 0x8f);
    uiHeaderRu(i18n::tr("Options", "Опции"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    fontSmall();
    tft.setTextDatum(TL_DATUM); tft.setTextColor(dim, bg);
    String t = optTitle; if (t.length() > 24) t = t.substring(0, 23) + "~";
    tft.drawString(t, 12, 46);
    fontOff();
    int y = 84;
    for (int i = 0; i < optN; i++) { optY[i] = y; drawActionBtn(y, optLabels[i], i == optSel); y += 42; }
    uiFooterRu(i18n::isRu() ? "LEFT назад  OK выбор" : "LEFT back  OK select");
    drawNetBadge();
}

static void openHiddenOptions() {
    if (revealer.count() == 0) return;
    uint8_t b[6]; String ss;
    revealer.get(hidSel, b, ss);
    optTitle = ss;
    optN = 0;
    optLabels[optN] = i18n::tr("Delete name", "Удалить имя"); optIds[optN] = OPT_DEL_HIDDEN; optN++;
    optSel = 0; optReturn = ST_HIDDEN;
    st = ST_OPTIONS; drawOptionsScreen();
}

static void optActivate() {
    switch (optIds[optSel]) {
        case OPT_DEL_HIDDEN: revealer.remove(hidSel); gotoHidden(); break;
    }
}

static void back() {
    switch (st) {
        case ST_PROVISION: net.stopProvision(); gotoConn();               return;
        case ST_CONFIRM:   cancelConfirm();                               return;
        case ST_OPTIONS:   if (optReturn == ST_HIDDEN) gotoHidden(); else showMenu(); return;
        case ST_MENU:      if (depth > 0) { depth--; showMenu(); }        return;
        default:           showMenu();                                    return;  // WIFI/BLE/INFO/CONN/HIDDEN
    }
}

static void launch(int feat) {
    switch (feat) {
        case F_WIFI_SCAN:   engine.setMode(ScanEngine::SCAN_WIFI); engine.resume(); st = ST_WIFI; off = 0; seenWifiGen = engine.wifiGen(); drawList(true); break;
        case F_CONN:        connSel = 0; gotoConn(); break;
        case F_HIDDEN:      hidSel = 0; hidOff = 0; gotoHidden(); break;
        case F_BLE_SCAN:    engine.setMode(ScanEngine::SCAN_BLE);  engine.resume(); st = ST_BLE;  off = 0; seenBleGen  = engine.bleGen();  drawList(true); break;
        case F_SUBGHZ_SOON: infoTitle = i18n::tr("Sub-GHz Recorder", "Запись Sub-GHz"); infoBody = i18n::tr("Record / replay 315-868 MHz", "Запись/повтор 315-868 МГц"); infoNote = i18n::tr("Coming soon (needs CC1101)", "Скоро (нужен CC1101)"); st = ST_INFO; drawInfo(); break;
        case F_ABOUT:       infoTitle = i18n::tr("About", "О девайсе"); infoBody = i18n::tr("ESP32-Leshy - open firmware", "ESP32-Leshy - открытая прошивка"); infoNote = "anton-vinogradov/esp32-leshy"; st = ST_INFO; drawInfo(); break;
        case F_RECAL:       touchRecalibrate(); showMenu(); break;
        case F_LANG_EN:     i18n::set(Lang::EN); saveLang(Lang::EN); if (depth > 0) depth--; showMenu(); break;
        case F_LANG_RU:     i18n::set(Lang::RU); saveLang(Lang::RU); if (depth > 0) depth--; showMenu(); break;
    }
}

static void activate() {
    const MenuItem& it = MENUS[curMenu()].items[curSel()];
    if (it.kind == K_SUB) { depth++; menuStack[depth] = it.target; selStack[depth] = 0; showMenu(); }
    else launch(it.target);
}

void setup() {
    Serial.begin(115200);
    delay(200);
    displayInit();
    BootScreen().show();
    delay(1500);
    i18n::set(loadLang());
    buttons.begin();
    touchBegin();                    // loads NVS calibration, or calibrates once
    net.begin();
    revealer.begin();                // load saved revealed hidden-SSID names from NVS
    wifiScreen.attachNet(&net);      // so the scanner can mark your own network (*)
    engine.attachRevealer(&revealer);// passively reveal hidden SSIDs during Wi-Fi scans
    engine.begin();                  // background scan task
    showMenu();
}

void loop() {
    // ---- touch (edge-triggered) ----
    uint16_t tx, ty;
    if (touchGet(tx, ty)) {
        if (!touchDown) {
            touchDown = true;
            if (st == ST_MENU) {
                int hit = menuScreen.hitTest(tx, ty);
                if (hit >= 0) { int p = curSel(); curSel() = hit; menuScreen.repaint(p, hit); activate(); }
            } else if (st == ST_CONN) {
                if (ty < 28) back();
                else for (int i = 0; i < connActN; i++)
                    if (ty >= connActY[i] && ty < connActY[i] + 34) { connSel = i; connActivate(); break; }
            } else if (st == ST_HIDDEN) {
                if (ty < 28) back();
                else for (int i = 0; i < HID_VISIBLE; i++)
                    if (hidRowY[i] >= 0 && ty >= hidRowY[i] && ty < hidRowY[i] + HID_ROW_H) { hidSel = hidOff + i; openHiddenOptions(); break; }
            } else if (st == ST_OPTIONS) {
                if (ty < 28) back();
                else for (int i = 0; i < optN; i++)
                    if (ty >= optY[i] && ty < optY[i] + 34) { optSel = i; optActivate(); break; }
            } else if (st == ST_CONFIRM) {
                if (ty >= okBtnY && ty < okBtnY + 40) doConfirm();
                else if (ty >= cancelBtnY && ty < cancelBtnY + 40) cancelConfirm();
                else if (ty < 28) cancelConfirm();
            } else if (ty < 28) {           // WIFI / BLE / INFO / PROVISION: tap header to go back
                back();
            }
        }
    } else {
        touchDown = false;
    }

    // ---- keypad ----
    switch (buttons.poll()) {
        case Buttons::UP:
            if (st == ST_MENU) { if (curSel() > 0) { int p = curSel(); curSel()--; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI || st == ST_BLE) { if (off > 0) { off--; drawList(false); } }
            else if (st == ST_CONN)    { if (connSel > 0) { int p = connSel; connSel--; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel > 0)  { int p = optSel;  optSel--;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel > 0)  { int p = hidSel; hidSel--; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            break;
        case Buttons::DOWN:
            if (st == ST_MENU) { if (curSel() < MENUS[curMenu()].n - 1) { int p = curSel(); curSel()++; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI || st == ST_BLE) { int m = listCount() - UI_VISIBLE; if (m < 0) m = 0; if (off < m) { off++; drawList(false); } }
            else if (st == ST_CONN)    { if (connSel < connActN - 1) { int p = connSel; connSel++; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel < optN - 1)      { int p = optSel;  optSel++;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel < revealer.count() - 1) { int p = hidSel; hidSel++; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            break;
        case Buttons::SELECT:                    // middle = enter / confirm
            if (st == ST_MENU) activate();
            else if (st == ST_CONN) connActivate();
            else if (st == ST_OPTIONS) optActivate();
            else if (st == ST_CONFIRM) doConfirm();
            break;
        case Buttons::RIGHT:                      // right = options / action
            if (st == ST_MENU) activate();
            else if (st == ST_CONN) connActivate();
            else if (st == ST_OPTIONS) optActivate();
            else if (st == ST_CONFIRM) doConfirm();
            else if (st == ST_HIDDEN) openHiddenOptions();
            break;
        case Buttons::LEFT:
            back();
            break;
        default:
            break;
    }

    // ---- provisioning portal ----
    if (st == ST_PROVISION) {
        net.loopProvision();
        if (net.pendingConnect()) {
            net.stopProvision();     // saves creds + switches to STA (AP drops)
            infoTitle = i18n::tr("Connecting...", "Подключение..."); infoBody = net.savedSsid(); infoNote = "";
            st = ST_INFO; drawInfo();
            net.connect();
            gotoConn();              // land on the connection screen with the fresh status
        }
    }

    // ---- live updates ----
    if (st == ST_WIFI && engine.wifiGen() != seenWifiGen) {
        seenWifiGen = engine.wifiGen();
        int m = engine.wifiCount() - UI_VISIBLE; if (m < 0) m = 0; if (off > m) off = m;
        drawList(true);
    } else if (st == ST_BLE && engine.bleGen() != seenBleGen) {
        seenBleGen = engine.bleGen();
        int m = engine.bleCount() - UI_VISIBLE; if (m < 0) m = 0; if (off > m) off = m;
        drawList(true);
    }

    delay(10);
}

#elif DEMO == DEMO_BTNTEST

Buttons buttons;

void setup() {
    Serial.begin(115200);
    delay(300);
    if (!buttons.begin()) {
        Serial.println("[BtnTest] PCF8574 not found on I2C (0x20-0x27).");
        return;
    }
    Serial.printf("[BtnTest] PCF8574 @ 0x%02X. Press one button at a time; I'll print its bit.\n",
                  buttons.addr());
}

void loop() {
    static uint8_t last = 0xFF;
    uint8_t v = buttons.readRaw();
    uint8_t edge = last & ~v;                    // released -> pressed
    for (int b = 0; b < 8; b++) {
        if (edge & (1 << b)) Serial.printf("pressed bit %d  (raw=0x%02X)\n", b, v);
    }
    last = v;
    delay(30);
}

#elif DEMO == DEMO_TOUCHCAL

void setup() {
    Serial.begin(115200);
    delay(300);
    displayInit();
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("Touch the arrows", 120, 160, 2);

    uint16_t cal[5];
    tft.calibrateTouch(cal, TFT_WHITE, TFT_BLACK, 18);
    Serial.printf("TOUCH_CAL = { %u, %u, %u, %u, %u };\n",
                  cal[0], cal[1], cal[2], cal[3], cal[4]);

    tft.fillScreen(TFT_BLACK);
    tft.drawString("Done — tap to test", 120, 160, 2);
}

void loop() {
    uint16_t x, y;
    if (tft.getTouch(&x, &y)) {
        tft.fillCircle(x, y, 3, TFT_GREEN);
        Serial.printf("touch %u,%u\n", x, y);
    }
}

#endif
