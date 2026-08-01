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
#include "features/display/SignalFinderScreen.h"
#include "features/scan/ScanEngine.h"
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

ScanEngine engine;
WifiScreen wifiScreen;
BleScreen  bleScreen;
MenuScreen menuScreen;
SignalFinderScreen sfScreen;
Buttons    buttons;

// ---- menu tree ----
enum { M_ROOT, M_WIFI, M_BLE, M_SUBGHZ, M_SETTINGS, M_LANG };
enum { F_WIFI_SCAN, F_SIGNAL_FINDER, F_BLE_SCAN, F_SUBGHZ_SOON, F_RECAL, F_ABOUT, F_LANG_EN, F_LANG_RU };
static const uint8_t K_SUB = 0, K_FEAT = 1;

static const MenuItem ROOT_I[] = {
    {"Wi-Fi",    "Scan & locate networks",   K_SUB,  M_WIFI},
    {"BLE",      "Bluetooth devices & tags", K_SUB,  M_BLE},
    {"Sub-GHz",  "315/433/868 MHz radio",    K_SUB,  M_SUBGHZ},
    {"Settings", "Language, touch, about",   K_SUB,  M_SETTINGS},
};
static const MenuItem WIFI_I[] = {
    {"Wi-Fi Scan",    "Networks: signal, channel, lock", K_FEAT, F_WIFI_SCAN},
    {"Signal Finder", "Hot/cold locate an AP",           K_FEAT, F_SIGNAL_FINDER},
};
static const MenuItem BLE_I[] = {
    {"BLE Scan", "Devices & trackers nearby", K_FEAT, F_BLE_SCAN},
};
static const MenuItem SUB_I[] = {
    {"Recorder", "Record RF signals (soon)", K_FEAT, F_SUBGHZ_SOON},
};
static const MenuItem SET_I[] = {
    {"Language",        "Interface language",      K_SUB,  M_LANG},
    {"Calibrate touch", "Redo screen calibration", K_FEAT, F_RECAL},
    {"About",           "About ESP32-Leshy",       K_FEAT, F_ABOUT},
};
static const MenuItem LANG_I[] = {
    {"English", "", K_FEAT, F_LANG_EN},
    {"Russian", "", K_FEAT, F_LANG_RU},
};
static const Menu MENUS[] = {
    {"ESP32-Leshy", ROOT_I, 4},
    {"Wi-Fi",       WIFI_I, 2},
    {"BLE",         BLE_I,  1},
    {"Sub-GHz",     SUB_I,  1},
    {"Settings",    SET_I,  3},
    {"Language",    LANG_I, 2},
};

// ---- navigation state ----
enum State { ST_MENU, ST_WIFI, ST_BLE, ST_INFO, ST_SF_PICK, ST_SF_TRACK };
static State    st = ST_MENU;
static int      menuStack[6] = { M_ROOT };   // path of open menus (for back)
static int      selStack[6]  = { 0 };        // selection per level
static int      depth = 0;
static int      off = 0, sfSel = 0;
static uint32_t seenWifiGen = 0, seenBleGen = 0;
static bool     touchDown = false;
static const char* infoTitle = "";
static const char* infoBody  = "";
static const char* infoNote  = "";

static int  curMenu() { return menuStack[depth]; }
static int& curSel()  { return selStack[depth]; }
static void showMenu() { st = ST_MENU; menuScreen.show(&MENUS[curMenu()], curSel()); }

static void saveLang(Lang l) { Preferences p; p.begin("leshy", false); p.putUChar("lang", (uint8_t)l); p.end(); }
static Lang loadLang() { Preferences p; p.begin("leshy", true); uint8_t v = p.getUChar("lang", (uint8_t)UI_LANG); p.end(); return (Lang)v; }

static int  listCount() { return st == ST_WIFI ? engine.wifiCount() : engine.bleCount(); }
static void drawList(bool full) {
    if (st == ST_WIFI) { if (full) wifiScreen.draw(engine, off); else wifiScreen.rows(engine, off); }
    else               { if (full) bleScreen.draw(engine, off);  else bleScreen.rows(engine, off); }
}

static void drawInfo() {
    uiHeader(infoTitle, "");
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tft.color565(0xe8, 0xe8, 0xe0), uiBg());
    tft.drawString(infoBody, 10, 50, 2);
    tft.setTextColor(tft.color565(0xff, 0xcf, 0x3f), uiBg());
    tft.drawString(infoNote, 10, 78, 2);
    uiFooter("LEFT: back");
}

static void tryTrack() {
    String ssid;
    if (sfScreen.ssidAt(engine, sfSel, ssid) && sfScreen.startTrack(ssid)) {
        st = ST_SF_TRACK;
        sfScreen.drawTrackChrome();
    }
}

static void back() {
    if (st == ST_SF_PICK) engine.resume();
    if (st != ST_MENU) { showMenu(); return; }      // leaf -> its menu
    if (depth > 0) { depth--; showMenu(); }          // submenu -> parent
}

static void launch(int feat) {
    switch (feat) {
        case F_WIFI_SCAN:     st = ST_WIFI; off = 0; seenWifiGen = engine.wifiGen(); drawList(true); break;
        case F_BLE_SCAN:      st = ST_BLE;  off = 0; seenBleGen  = engine.bleGen();  drawList(true); break;
        case F_SIGNAL_FINDER: engine.pause(); st = ST_SF_PICK; sfSel = 0; sfScreen.drawPicker(engine, sfSel); break;
        case F_SUBGHZ_SOON:   infoTitle = "Sub-GHz Recorder"; infoBody = "Record / replay 315-868 MHz"; infoNote = "Coming soon (needs CC1101)"; st = ST_INFO; drawInfo(); break;
        case F_ABOUT:         infoTitle = "About"; infoBody = "ESP32-Leshy - open firmware"; infoNote = "anton-vinogradov/esp32-leshy"; st = ST_INFO; drawInfo(); break;
        case F_RECAL:         touchRecalibrate(); showMenu(); break;
        case F_LANG_EN:       i18n::set(Lang::EN); saveLang(Lang::EN); if (depth > 0) depth--; showMenu(); break;
        case F_LANG_RU:       i18n::set(Lang::RU); saveLang(Lang::RU); if (depth > 0) depth--; showMenu(); break;
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
            } else if (st == ST_SF_PICK) {
                if (ty < 28) back();
                else if (ty >= UI_LIST_TOP && ty < UI_LIST_TOP + UI_VISIBLE * UI_ROW_H) {
                    int idx = sfScreen.pickerOffset(sfSel) + (ty - UI_LIST_TOP) / UI_ROW_H;
                    if (idx < engine.wifiCount()) { sfSel = idx; sfScreen.pickerRows(engine, sfSel); tryTrack(); }
                }
            } else if (st == ST_SF_TRACK) {
                if (ty < 28) { sfScreen.stopTrack(); st = ST_SF_PICK; sfScreen.drawPicker(engine, sfSel); }
            } else if (ty < 28) {           // WIFI / BLE / INFO: tap header to go back
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
            else if (st == ST_SF_PICK) { if (sfSel > 0) { sfSel--; sfScreen.pickerRows(engine, sfSel); } }
            break;
        case Buttons::DOWN:
            if (st == ST_MENU) { if (curSel() < MENUS[curMenu()].n - 1) { int p = curSel(); curSel()++; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI || st == ST_BLE) { if (off < listCount() - 1) { off++; drawList(false); } }
            else if (st == ST_SF_PICK) { if (sfSel < engine.wifiCount() - 1) { sfSel++; sfScreen.pickerRows(engine, sfSel); } }
            break;
        case Buttons::SELECT:
        case Buttons::RIGHT:
            if (st == ST_MENU) activate();
            else if (st == ST_SF_PICK) tryTrack();
            break;
        case Buttons::LEFT:
            if (st == ST_SF_TRACK) { sfScreen.stopTrack(); st = ST_SF_PICK; sfScreen.drawPicker(engine, sfSel); }
            else back();
            break;
        default:
            break;
    }

    // ---- live updates ----
    if (st == ST_WIFI && engine.wifiGen() != seenWifiGen) {
        seenWifiGen = engine.wifiGen();
        if (off >= engine.wifiCount()) off = 0;
        drawList(true);
    } else if (st == ST_BLE && engine.bleGen() != seenBleGen) {
        seenBleGen = engine.bleGen();
        if (off >= engine.bleCount()) off = 0;
        drawList(true);
    } else if (st == ST_SF_TRACK) {
        sfScreen.updateTrack();
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
