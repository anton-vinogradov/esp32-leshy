#include <Arduino.h>
#include <string.h>

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
#include "features/leds/StatusLeds.h"
#include "features/airtime/AirtimeMonitor.h"
#include "features/spectrum/Nrf24Spectrum.h"
#include "features/spectrum/Cc1101Spectrum.h"

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
#include "features/ota/OtaManager.h"
#include "features/display/img_rider.h"
#include "features/display/font_ru_small.h"
#include "features/legal/LegalText.h"
#include "core/version.h"

ScanEngine     engine;
WifiScreen     wifiScreen;
BleScreen      bleScreen;
MenuScreen     menuScreen;
Buttons        buttons;
NetManager     net;
HiddenRevealer revealer;
OtaManager     ota;
DeauthDetector detector;
StatusLeds     leds;             // the four WS2812s under the antennas — shows what the radio is doing
AirtimeMonitor airtime;          // real per-channel airtime (promiscuous) for the Channels screen
Nrf24Spectrum  nrf;              // NRF24 raw 2.4GHz spectrum sniffer
Cc1101Spectrum cc;              // CC1101 sub-GHz spectrum sniffer

static void drawNetBadge();      // small "connected" mark in the header (defined below)
static void gotoWifi();          // (re)enter the live Wi-Fi scan
static void ensureWifiVisible(); // keep the selected scan row on screen
static int  drawWrapped(const char* s, int x, int y, int maxw, int lh, int maxlines);  // word-wrap (defined below)
static void openNetOptions();    // RIGHT on a scan row -> per-network options
static void drawNetDetails();    // details screen for the selected network

// ---- menu tree ----
enum { M_ROOT, M_WIFI, M_BLE, M_SUBGHZ, M_SETTINGS, M_LANG, M_WIFI_ADV, M_LAB };
enum { F_WIFI_SCAN, F_CONN, F_HIDDEN, F_DEAUTH, F_CHANNELS, F_SPECTRUM, F_BLE_SCAN, F_SUBSPECTRUM, F_SUBGHZ_SOON, F_RECAL, F_ABOUT, F_OTA, F_LEGAL, F_LEDS, F_BACKLIGHT, F_TXPOWER, F_NOISEGEN, F_TXMODE, F_LANG_EN, F_LANG_RU };
static const uint8_t K_SUB = 0, K_FEAT = 1;

static const MenuItem ROOT_I[] = {
    {"Wi-Fi",       "Scan networks",            "Wi-Fi",       "Сканирование сетей",       K_SUB, M_WIFI},
    {"BLE",         "Bluetooth devices & tags", "BLE",         "Устройства и метки",       K_SUB, M_BLE},
    {"Sub-GHz",     "315/433/868 MHz radio",    "Sub-GHz",     "Радио 315/433/868 МГц",    K_SUB, M_SUBGHZ},
    {"Settings",    "Language, touch, about",   "Настройки",   "Язык, тач, о девайсе",     K_SUB, M_SETTINGS},
};
static const MenuItem WIFI_I[] = {
    {"Wi-Fi Scan",    "Signal, channel, lock", "Скан Wi-Fi",    "Сигнал, канал, шифр",   K_FEAT, F_WIFI_SCAN},
    {"Channels 2.4G", "Airtime per channel",   "Каналы 2.4ГГц", "Занятость по каналам",  K_FEAT, F_CHANNELS},
    {"Spectrum 2.4G", "Raw band waterfall (NRF24)", "Спектр 2.4ГГц", "Водопад по спектру (NRF24)", K_FEAT, F_SPECTRUM},
    {"Advanced",      "Deeper Wi-Fi tools",    "Продвинутое",   "Инструменты поглубже",  K_SUB,  M_WIFI_ADV},
    {"Laboratory",    "Experimental — transmits", "Лаборатория", "Эксперименты — эфир",   K_SUB,  M_LAB},
};
static const MenuItem WADV_I[] = {
    {"Hidden names",   "Revealed hidden SSIDs",  "Скрытые сети",  "Раскрытые имена",       K_FEAT, F_HIDDEN},
    {"Deauth monitor", "Alarm on deauth bursts", "Детектор атак", "Тревога на отключения", K_FEAT, F_DEAUTH},
    {"TX power",       "Noise TX radiation power", "Мощность TX", "Мощность излучения шума", K_FEAT, F_TXPOWER},
};
static const MenuItem BLE_I[] = {
    {"BLE Scan", "Devices & trackers nearby", "Скан BLE", "Устройства и трекеры рядом", K_FEAT, F_BLE_SCAN},
};
static const MenuItem SUB_I[] = {
    {"Spectrum", "Sub-GHz waterfall (CC1101)", "Спектр", "Водопад Sub-GHz (CC1101)", K_FEAT, F_SUBSPECTRUM},
    {"Recorder", "Record RF signals (soon)",   "Запись", "Запись сигналов (скоро)",   K_FEAT, F_SUBGHZ_SOON},
};
static const MenuItem SET_I[] = {
    {"Wi-Fi connect",   "Status, join, exit",      "Wi-Fi подключение", "Статус, вход, выход",   K_FEAT, F_CONN},
    {"Update",          "Update from GitHub",      "Обновление",        "Обновить с GitHub",     K_FEAT, F_OTA},
    {"Language",        "Interface language",      "Язык",        "Язык интерфейса",       K_SUB,  M_LANG},
    {"Status LEDs",     "Brightness / off",        "Светодиоды",  "Яркость / выкл",        K_FEAT, F_LEDS},
    {"Screen light",    "Screen brightness",       "Яркость экрана", "Подсветка дисплея",   K_FEAT, F_BACKLIGHT},
    {"Calibrate touch", "Redo screen calibration", "Калибровка",  "Перекалибровать экран", K_FEAT, F_RECAL},
    {"About",           "About ESP32-Leshy",       "О девайсе",   "Об ESP32-Leshy",        K_FEAT, F_ABOUT},
    {"Responsible use", "Legal terms — read it",   "Ответственность", "Правила — прочти",  K_FEAT, F_LEGAL},
};
// Laboratory — experimental tools that TRANSMIT. Under Wi-Fi (it's a 2.4 GHz lab).
static const MenuItem LAB_I[] = {
    {"Noise gen 2.4G",  "Inject noise into channels", "Генератор шума 2.4", "Шум в выбранные каналы", K_FEAT, F_NOISEGEN},
    {"TX mode",         "Verify / Maximum",           "Режим передачи",     "Проверка / Максимум",    K_FEAT, F_TXMODE},
};
static const MenuItem LANG_I[] = {
    {"English", "", "English", "", K_FEAT, F_LANG_EN},
    {"Русский", "", "Русский", "", K_FEAT, F_LANG_RU},
};
static const Menu MENUS[] = {
    {"ESP32-Leshy", "ESP32-Leshy", ROOT_I, 4},
    {"Wi-Fi",       "Wi-Fi",       WIFI_I, 5},
    {"BLE",         "BLE",         BLE_I,  1},
    {"Sub-GHz",     "Sub-GHz",     SUB_I,  2},
    {"Settings",    "Настройки",   SET_I,  8},
    {"Language",    "Язык",        LANG_I, 2},
    {"Advanced",    "Продвинутое", WADV_I, 3},
    {"Laboratory",  "Лаборатория", LAB_I,  2},
};

// ---- navigation state ----
enum State { ST_MENU, ST_WIFI, ST_BLE, ST_INFO, ST_PROVISION, ST_CONN, ST_HIDDEN, ST_CONFIRM, ST_OPTIONS, ST_OTA, ST_DEAUTH, ST_CHANNELS, ST_SPECTRUM, ST_SUBSPECTRUM, ST_NETINFO, ST_LEGAL, ST_LANGPICK };
static State    st = ST_MENU;
static int      menuStack[6] = { M_ROOT };   // path of open menus (for back)
static int      selStack[6]  = { 0 };        // selection per level
static int      depth = 0;
static int      off = 0;
static int      wifiSel = 0;     // selected row in the Wi-Fi scan
static WifiRow  netSel;          // network the per-network options act on
static uint32_t seenWifiGen = 0, seenBleGen = 0;
static uint32_t scanPausedAt = 0;   // when the scan was paused (net options) — long gaps invalidate the RSSI graph
static bool     touchDown = false;
static String   infoTitle, infoBody, infoNote;
static int      infoAction = -1;   // F_LEDS / F_BACKLIGHT when the info screen is an adjustable setting (SELECT cycles it in place), else -1

static int  curMenu() { return menuStack[depth]; }
static int& curSel()  { return selStack[depth]; }
// In a menu the radios are idle — scanning only runs on a scan screen.
static void showMenu() { engine.pause(); st = ST_MENU; menuScreen.show(&MENUS[curMenu()], curSel(), depth > 0); drawNetBadge(); }

static void saveLang(Lang l) { Preferences p; p.begin("leshy", false); p.putUChar("lang", (uint8_t)l); p.end(); }
static Lang loadLang() { Preferences p; p.begin("leshy", true); uint8_t v = p.getUChar("lang", (uint8_t)UI_LANG); p.end(); return (Lang)v; }

static int  listCount() { return st == ST_WIFI ? engine.wifiCount() : engine.bleCount(); }
static void drawList(bool full) {
    if (st == ST_WIFI) { if (full) wifiScreen.draw(engine, off, wifiSel); else wifiScreen.rows(engine, off, wifiSel); }
    else               { if (full) bleScreen.draw(engine, off);  else bleScreen.rows(engine, off); }
}

static void drawInfo() {
    uiHeaderRu(infoTitle.c_str());
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    fontSmall();
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tft.color565(0xe8, 0xe8, 0xe0), uiBg());
    int y = drawWrapped(infoBody.c_str(), 10, 50, 220, 24, 3);   // word-wrap, no mid-word breaks
    if (infoNote.length()) {
        tft.setTextColor(tft.color565(0xff, 0xcf, 0x3f), uiBg());
        drawWrapped(infoNote.c_str(), 10, y + 14, 220, 24, 7);
    }
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
               infoAction >= 0 ? (i18n::isRu() ? "менять ▶" : "change ▶") : nullptr);
    fontOff();
    drawNetBadge();
}

// Adjustable-setting info screens: show the CURRENT value; SELECT/RIGHT cycles in place.
static void drawLedsInfo() {
    uint8_t b = leds.brightness();
    infoTitle = i18n::tr("Status LEDs", "Светодиоды");
    infoBody  = b ? String(i18n::tr("Brightness ", "Яркость ")) + b + "/255"
                  : String(i18n::tr("Off", "Выключены"));
    infoNote  = i18n::tr("Press ▶ to change. LEDs under the antennas show what the radio is doing.",
                         "Жми ▶ для смены. Светодиоды под антеннами показывают работу радио.");
    infoAction = F_LEDS; st = ST_INFO; drawInfo();
}
static void drawBacklightInfo() {
    uint8_t v = uiBacklightLevel();
    infoTitle = i18n::tr("Screen light", "Яркость экрана");
    infoBody  = String(v * 100 / 255) + "%";
    infoNote  = i18n::tr("Press ▶ to change the screen brightness.",
                         "Жми ▶ для смены яркости экрана.");
    infoAction = F_BACKLIGHT; st = ST_INFO; drawInfo();
}

// TX radiation power for the Spectrum noise self-test — persisted; applied to the NRF24.
static void saveTxPower(uint8_t bits) { Preferences p; p.begin("leshy", false); p.putUChar("tx_pwr", bits); p.end(); }
static uint8_t loadTxPower() { Preferences p; p.begin("leshy", true); uint8_t v = p.getUChar("tx_pwr", 0x06); p.end(); return v & 0x06; }

static uint8_t txPowerCycle() {              // 0 dBm (max) -> -6 -> -12 -> -18 -> wrap; persists; applied to radio
    uint8_t b = nrf.txPower();
    b = (b == 0) ? 0x06 : (uint8_t)(b - 2);
    nrf.setTxPower(b);
    saveTxPower(b);
    return b;
}

static void drawTxPowerInfo() {
    uint8_t b = nrf.txPower();
    int dbm = Nrf24Spectrum::txPowerDbm(b);
    infoTitle = i18n::tr("TX power", "Мощность TX");
    infoBody  = String(dbm) + i18n::tr(" dBm", " дБм") + (b == 0x06 ? i18n::tr(" (max)", " (макс)") : "");
    infoNote  = i18n::tr("Transmit power for the Spectrum noise test. Max = loudest, but can wash out the whole waterfall — lower it for a cleaner picture.",
                         "Мощность передачи шума в тесте Спектра. Максимум — громче, но может засветить весь водопад — снизь для чистой картинки.");
    infoAction = F_TXPOWER; st = ST_INFO; drawInfo();
}

// TX mode: Проверка (keep one antenna listening → live waterfall) vs Максимум (all antennas
// transmit → louder, waterfall goes dark). Persisted; applied to the NRF24.
static void saveTxMode(bool listenSelf) { Preferences p; p.begin("leshy", false); p.putBool("tx_self", listenSelf); p.end(); }
static bool loadTxMode() { Preferences p; p.begin("leshy", true); bool v = p.getBool("tx_self", true); p.end(); return v; }

static bool txModeCycle() {                  // toggle Проверка <-> Максимум; persists; applied to radio
    bool v = !nrf.txListenSelf();
    nrf.setTxListenSelf(v);
    saveTxMode(v);
    return v;
}

static void drawTxModeInfo() {
    bool self = nrf.txListenSelf();
    infoTitle = i18n::tr("TX mode", "Режим передачи");
    infoBody  = self ? i18n::tr("Verify", "Проверка") : i18n::tr("Maximum", "Максимум");
    infoNote  = self ? i18n::tr("One antenna keeps listening — you see the injected noise on the waterfall. Best for checking it works.",
                                "Одна антенна слушает — свой шум виден на водопаде. Для проверки, что всё работает.")
                     : i18n::tr("All antennas transmit — loudest output, but the waterfall goes dark (nothing is left to receive).",
                                "Все антенны в эфир — максимум мощности, но водопад гаснет (принимать нечем).");
    infoAction = F_TXMODE; st = ST_INFO; drawInfo();
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
    uiFooterRu(i18n::tr("◀ cancel", "◀ отмена"));
    fontOff();
}

// Small "connected" mark in the top-right of the header: three gold bars, drawn
// only while actually associated. Scanning drops the link, so it honestly
// disappears on the scan screens.
static void drawNetBadge() {
    bool conn = net.connected();
    bool upd  = (ota.phase() == OtaManager::AVAILABLE);
    if (!conn && !upd) return;
    if (upd) {                                   // amber up-arrow: an update is waiting
        const uint16_t amber = tft.color565(0xff, 0xa5, 0x2a);
        tft.fillTriangle(190, 8, 184, 20, 196, 20, amber);
        tft.fillRect(187, 18, 6, 4, amber);
    }
    if (conn) {                                  // gold signal bars: connected
        const uint16_t gold = tft.color565(0xff, 0xcf, 0x3f);
        int x = 210, base = 21;
        tft.fillRect(x,      base - 6,  4, 6,  gold);
        tft.fillRect(x + 6,  base - 10, 4, 10, gold);
        tft.fillRect(x + 12, base - 14, 4, 14, gold);
    }
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
        uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
        fontOff(); drawNetBadge(); return;
    }
    clampHidden();
    drawHiddenRowsOnly();
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::isRu() ? "опции ▶" : "options ▶");
    drawNetBadge();
}

static void gotoHidden() { st = ST_HIDDEN; drawHiddenScreen(); }

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
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
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
            infoTitle = i18n::tr("Connecting...", "Подключение..."); infoBody = net.savedSsid(); infoNote = ""; infoAction = -1;
            st = ST_INFO; drawInfo();
            net.connect();
            if (net.connected()) ota.startCheck();   // auto-check for updates on connect
            gotoConn();
            break;
        case CA_DISCONNECT: net.disconnect(); connSel = 0; gotoConn(); break;
        case CA_FORGET:     askConfirm(PK_FORGET, 0, i18n::tr("Forget this network?", "Забыть эту сеть?"), net.savedSsid(), ST_CONN); break;
    }
}

// ---- options menu (RIGHT opens context actions for the selected item) ----
enum OptId { OPT_DEL_HIDDEN, OPT_NET_DETAILS };
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
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
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
        case OPT_DEL_HIDDEN:  revealer.remove(hidSel); gotoHidden(); break;
        case OPT_NET_DETAILS: drawNetDetails(); st = ST_NETINFO; break;
    }
}

// ---- OTA update screen (full-bleed rider background + progress slider) ----
static uint32_t seenOtaGen = 0;
static int      seenOtaPhase = -1;

static const char* otaErrText(OtaManager::Err e) {
    switch (e) {
        case OtaManager::E_NONET:     return i18n::tr("No network",        "Нет сети");
        case OtaManager::E_TIME:      return i18n::tr("No clock (SNTP)",   "Нет времени");
        case OtaManager::E_API:       return i18n::tr("Server error",      "Ошибка сервера");
        case OtaManager::E_NORELEASE: return i18n::tr("No releases yet",   "Релизов пока нет");
        case OtaManager::E_RATELIMIT: return i18n::tr("Rate limited",      "Лимит запросов");
        case OtaManager::E_PARSE:     return i18n::tr("Bad response",      "Плохой ответ");
        case OtaManager::E_NOASSET:   return i18n::tr("No firmware.bin",   "Нет firmware.bin");
        case OtaManager::E_HTTP:      return i18n::tr("Download error",    "Ошибка загрузки");
        case OtaManager::E_BEGIN:     return i18n::tr("No OTA slot",       "Нет OTA-слота");
        case OtaManager::E_WRITE:     return i18n::tr("Flash error",       "Ошибка записи");
        case OtaManager::E_SHORT:     return i18n::tr("Interrupted",       "Прервано");
        case OtaManager::E_HASH:      return i18n::tr("Checksum mismatch", "Хеш не сошёлся");
        case OtaManager::E_END:       return i18n::tr("Bad image",         "Битый образ");
        case OtaManager::E_NOMEM:     return i18n::tr("Low memory",        "Мало памяти");
        default:                      return "";
    }
}

// A short "what to do" hint per error — the actionable half of a full-screen error.
static const char* otaHintText(OtaManager::Err e) {
    switch (e) {
        case OtaManager::E_NONET:     return i18n::tr("Join your Wi-Fi in Connection, then retry.", "Подключись к своему Wi-Fi в «Подключении» и повтори.");
        case OtaManager::E_TIME:      return i18n::tr("The clock needs internet. Wait a bit and retry.", "Часам нужен интернет. Подожди немного и повтори.");
        case OtaManager::E_API:       return i18n::tr("No answer from GitHub. Retry; if it persists, check the net.", "Нет ответа от GitHub. Повтори; если не поможет — проверь сеть.");
        case OtaManager::E_NORELEASE: return i18n::tr("No release has been published yet.", "Релиз ещё не опубликован.");
        case OtaManager::E_RATELIMIT: return i18n::tr("GitHub rate limit. Wait about an hour.", "Лимит запросов GitHub. Подожди примерно час.");
        case OtaManager::E_PARSE:     return i18n::tr("GitHub sent an unreadable reply. Retry.", "GitHub прислал нечитаемый ответ. Повтори.");
        case OtaManager::E_NOASSET:   return i18n::tr("The release has no firmware.bin file.", "В релизе нет файла firmware.bin.");
        case OtaManager::E_HTTP:      return i18n::tr("Download failed. Check the net and retry.", "Загрузка не удалась. Проверь сеть и повтори.");
        case OtaManager::E_BEGIN:     return i18n::tr("No room for the update image.", "Нет места под образ обновления.");
        case OtaManager::E_WRITE:     return i18n::tr("Flash write failed. Retry.", "Сбой записи во флеш-память. Повтори.");
        case OtaManager::E_SHORT:     return i18n::tr("The download was cut off. Retry.", "Загрузка оборвалась. Повтори.");
        case OtaManager::E_HASH:      return i18n::tr("Checksum mismatch — the file is corrupt. Retry.", "Хеш не сошёлся — файл повреждён. Повтори.");
        case OtaManager::E_END:       return i18n::tr("The image was rejected. Retry.", "Образ отвергнут системой. Повтори.");
        case OtaManager::E_NOMEM:     return i18n::tr("Not enough RAM. Reboot the device and retry.", "Не хватило памяти. Перезагрузи устройство и повтори.");
        default:                      return "";
    }
}

// Word-wrap a string at maxw px (font must already be loaded, datum TL, color set). Returns next y.
static int drawWrapped(const char* s, int x, int y, int maxw, int lh, int maxlines) {
    char line[160] = {0}; char word[80]; char trial[200];
    int lines = 0;
    const char* w = s;
    while (*w && lines < maxlines) {
        while (*w == ' ') w++;
        int wi = 0;
        while (*w && *w != ' ' && wi < (int)sizeof(word) - 1) word[wi++] = *w++;
        word[wi] = 0;
        if (!wi) break;
        if (line[0]) snprintf(trial, sizeof(trial), "%s %s", line, word);
        else         snprintf(trial, sizeof(trial), "%s", word);
        if (tft.textWidth(trial) <= maxw) {
            strncpy(line, trial, sizeof(line) - 1);
        } else {
            if (line[0]) { tft.drawString(line, x, y); y += lh; lines++; strncpy(line, word, sizeof(line) - 1); }
            else         { tft.drawString(word, x, y); y += lh; lines++; line[0] = 0; }
        }
    }
    if (line[0] && lines < maxlines) { tft.drawString(line, x, y); y += lh; }
    return y;
}

// Full-screen, photographable error — big reason, plain-language hint, and the exact
// technical facts (stage / HTTP code / detail) so a photo is enough to diagnose it.
static void drawOtaError() {
    const uint16_t bg    = tft.color565(0x1c, 0x0c, 0x0c);
    const uint16_t hdrbg = tft.color565(0x86, 0x22, 0x22);
    const uint16_t panel = tft.color565(0x2a, 0x16, 0x16);
    const uint16_t white = tft.color565(0xf4, 0xea, 0xea);
    const uint16_t dim   = tft.color565(0xcf, 0xa2, 0xa2);
    const uint16_t label = tft.color565(0x9a, 0x78, 0x78);
    const uint16_t gold  = tft.color565(0xff, 0xd0, 0x55);
    tft.fillScreen(bg);
    tft.fillRect(0, 0, 240, 28, hdrbg);
    fontBig(); tft.setTextDatum(ML_DATUM); tft.setTextColor(white, hdrbg);
    tft.drawString(i18n::tr("Update error", "Ошибка обновления"), 8, 15);

    fontBig(); tft.setTextDatum(TL_DATUM); tft.setTextColor(gold, bg);
    tft.drawString(otaErrText(ota.err()), 12, 40);

    fontSmall(); tft.setTextColor(white, bg);
    int y = drawWrapped(otaHintText(ota.err()), 12, 72, 216, 20, 3) + 8;

    tft.fillRoundRect(6, y, 228, 300 - y, 8, panel);
    int ty = y + 10, tx = 14;
    char buf[80];
    fontSmall();
    tft.setTextColor(label, panel); tft.drawString(i18n::tr("stage", "этап"), tx, ty);
    tft.setTextColor(white, panel);
    tft.drawString(ota.failPhase() == OtaManager::DOWNLOADING ? i18n::tr("download", "загрузка")
                                                              : i18n::tr("check", "проверка"), tx + 66, ty);
    ty += 22;
    if (ota.httpCode() != 0) {
        tft.setTextColor(label, panel); tft.drawString(i18n::tr("code", "код"), tx, ty);
        snprintf(buf, sizeof(buf), "%d", ota.httpCode());
        tft.setTextColor(white, panel); tft.drawString(buf, tx + 66, ty);
        ty += 22;
    }
    if (ota.detail()[0]) {
        tft.setTextColor(label, panel); tft.drawString(i18n::tr("detail", "детали"), tx, ty); ty += 18;
        fontTiny(); tft.setTextColor(dim, panel);
        ty = drawWrapped(ota.detail(), tx, ty, 208, 15, 3) + 4;
        fontSmall();
    }
    snprintf(buf, sizeof(buf), "%s%s", i18n::tr("installed v", "стоит v"), OtaManager::current());
    tft.setTextColor(label, panel); tft.drawString(buf, tx, ty);

    fontTiny(); tft.setTextColor(dim, bg);
    tft.setTextDatum(ML_DATUM); tft.drawString(i18n::tr("◀ back", "◀ назад"), 8, 309);
    tft.setTextDatum(MR_DATUM); tft.drawString(i18n::tr("retry ▶", "повтор ▶"), 232, 309);
    fontOff();
}

// The progress "slider" with the current step written on it (redrawn alone on % change).
static void otaBar() {
    const int x = 16, y = 268, w = 208, h = 26;
    const uint16_t barbg = tft.color565(0x14, 0x1a, 0x14);
    const uint16_t panel = tft.color565(0x0b, 0x11, 0x0b);
    static TFT_eSprite bar(&tft);
    static bool made = false;
    if (!made) { bar.createSprite(w, h); bar.loadFont(font_ru_small); made = true; }
    const char* label; int pct; uint16_t fill;
    switch (ota.phase()) {
        case OtaManager::CHECKING:    label = i18n::tr("Checking...", "Проверяю...");        pct = 12;  fill = tft.color565(0x7a, 0x6a, 0x2a); break;
        case OtaManager::UPTODATE:    label = i18n::tr("Latest version", "Последняя версия"); pct = 100; fill = tft.color565(0x2e, 0x6a, 0x3e); break;
        case OtaManager::AVAILABLE:   label = i18n::tr("OK: update", "OK: обновить");         pct = 0;   fill = tft.color565(0xff, 0xcf, 0x3f); break;
        case OtaManager::DOWNLOADING: { static char b[28]; snprintf(b, sizeof(b), "%s %d%%", i18n::tr("Downloading", "Загрузка"), ota.progress()); label = b; pct = ota.progress(); fill = tft.color565(0x2e, 0x8a, 0x3e); break; }
        case OtaManager::DONE:        label = i18n::tr("Done! reboot...", "Готово! рестарт..."); pct = 100; fill = tft.color565(0x2e, 0x8a, 0x3e); break;
        case OtaManager::FAILED:      label = otaErrText(ota.err());                          pct = 100; fill = tft.color565(0x8a, 0x2a, 0x2a); break;
        default:                      label = "";                                            pct = 0;   fill = barbg; break;
    }
    bar.fillSprite(panel);                    // compose off-screen, push once — no flicker
    bar.fillRoundRect(0, 0, w, h, 7, barbg);
    int fw = (w - 4) * pct / 100;
    if (fw > 0) bar.fillRoundRect(2, 2, fw < 6 ? 6 : fw, h - 4, 5, fill);
    bar.setTextDatum(MC_DATUM);
    bar.setTextColor(tft.color565(0xff, 0xff, 0xf2), barbg);
    bar.drawString(label, w / 2, h / 2);
    bar.pushSprite(x, y);
}

static void drawOtaScreen() {
    if (ota.phase() == OtaManager::FAILED) { drawOtaError(); return; }
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t dim   = tft.color565(0xbe, 0xc8, 0xb6);
    const uint16_t amber = tft.color565(0xff, 0xa5, 0x2a);
    const uint16_t panel = tft.color565(0x0b, 0x11, 0x0b);
    tft.setSwapBytes(true);
    tft.pushImage(0, 0, IMG_RIDER_W, IMG_RIDER_H, img_rider);   // rider = the whole background
    tft.setSwapBytes(false);
    tft.fillRoundRect(6, 196, 228, 118, 10, panel);             // dark panel for legible text
    fontBig(); tft.setTextDatum(TL_DATUM); tft.setTextColor(gold, panel);
    tft.drawString(i18n::tr("Update", "Обновление"), 16, 204);
    fontSmall(); tft.setTextColor(dim, panel);
    String line = (ota.phase() == OtaManager::AVAILABLE)
                    ? String(i18n::tr("Available: ", "Доступно: ")) + ota.latest()
                    : String(i18n::tr("Installed: v", "Установлено: v")) + OtaManager::current();
    tft.drawString(line, 16, 236);
    otaBar();
    if (ota.phase() == OtaManager::DOWNLOADING) {
        fontTiny(); tft.setTextDatum(MC_DATUM); tft.setTextColor(amber, panel);
        tft.drawString(i18n::tr("Do not power off", "Не выключай питание"), 120, 302);
    } else {
        fontTiny(); tft.setTextDatum(ML_DATUM); tft.setTextColor(dim, panel);
        tft.drawString(i18n::tr("◀ back", "◀ назад"), 16, 302);
        if (ota.phase() == OtaManager::AVAILABLE) {
            tft.setTextDatum(MR_DATUM);
            tft.drawString(i18n::tr("update ▶", "обновить ▶"), 224, 302);
        }
    }
    fontOff();
}

static void gotoOta() {
    // Reclaim BLE RAM up-front, before the version check — not just before the download.
    // A BLE session leaves the stack resident; freeing it hands the allocator ~70 KB more
    // room so the check's TLS can't fragment the heap below the two ~16 KB contiguous record
    // buffers the download then needs (measured: post-check largest block 31 KB without this,
    // 65 KB with it). The update flow ends in a reboot, so tearing BLE down here is safe;
    // no-op if BLE never ran. Pause the scan first so we don't free BLE mid-scan.
    engine.pauseAndWait();
    if (engine.releaseBleForOta())
        Serial.printf("[OTA] BLE freed before check: free=%u largest=%u\n",
                      (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    ota.startCheck(); seenOtaGen = ota.gen(); seenOtaPhase = -1; st = ST_OTA; drawOtaScreen();
}

static void otaActivate() {
    if (ota.phase() == OtaManager::AVAILABLE) ota.startUpdate();
    else if (ota.phase() == OtaManager::UPTODATE || ota.phase() == OtaManager::FAILED) ota.startCheck();
}

static void drawAboutScreen() {
    const uint16_t bg = uiBg();
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    uiHeaderRu(i18n::tr("About", "О девайсе"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall();
    int y = 46;
    tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("Hardware", "Железо"), 14, y); y += 22;
    tft.setTextColor(white, bg); tft.drawString("ESP32-DIV (ESP32-S3)", 22, y); y += 20;
    tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("by CiferTech", "от CiferTech"), 22, y); y += 32;
    tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("Firmware", "Прошивка"), 14, y); y += 22;
    tft.setTextColor(gold, bg);  tft.drawString("ESP32-Leshy", 22, y); y += 20;
    tft.setTextColor(white, bg); tft.drawString(String(i18n::tr("version v", "версия v")) + LESHY_FW_VERSION, 22, y); y += 20;
    tft.setTextColor(dim, bg);   tft.drawString(String(i18n::tr("released ", "выпуск ")) + LESHY_FW_DATE, 22, y); y += 30;
    tft.setTextColor(dim, bg);   tft.drawString(i18n::tr("Author", "Автор"), 14, y); y += 22;
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Anton Vinogradov", "Антон Виноградов"), 22, y); y += 30;
    tft.setTextColor(dim, bg);   tft.drawString("GitHub", 14, y); y += 20;
    fontTiny(); tft.setTextColor(white, bg);
    tft.drawString("anton-vinogradov/esp32-leshy", 22, y);
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
    fontOff();
    drawNetBadge();
}

// ---- Deauth monitor screen (passive/defensive) ----
// Repaints only what changed (rule: no full-screen redraw on refresh — it flickers).
static const int DA_BADGE_Y = 44, DA_ROW1 = 104, DA_ROW2 = 132, DA_ROW3 = 160, DA_SRC_Y = 214;
static int    daLastAlert = -1, daLastRecent = -1, daLastChan = -1;
static long   daLastTotal = -1;
static String daLastMac;

static void deauthValue(int y, const String& val, uint16_t col) {
    const uint16_t bg = uiBg();
    tft.fillRect(120, y - 2, 108, 22, bg);          // value column only
    fontSmall();
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(col, bg);
    tft.drawString(val, 226, y);
}

static void deauthBadge(bool alert) {
    const uint16_t bc = alert ? tft.color565(0xd1, 0x4c, 0x4c) : tft.color565(0x2f, 0x6a, 0x3e);
    tft.fillRoundRect(12, DA_BADGE_Y, 216, 42, 9, bc);
    fontBig(); tft.setTextDatum(MC_DATUM); tft.setTextColor(tft.color565(0xff, 0xff, 0xf2), bc);
    tft.drawString(alert ? i18n::tr("ALERT", "ТРЕВОГА") : i18n::tr("Clear", "Чисто"), 120, DA_BADGE_Y + 22);
}

static void deauthRefresh() {                        // called on a timer; touches only changed fields
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t red   = tft.color565(0xd1, 0x4c, 0x4c);
    bool alert  = detector.alerting();
    int  recent = detector.recentCount();
    long total  = (long)detector.total();
    int  chan   = detector.channel();
    if (alert != (bool)daLastAlert) { daLastAlert = alert; deauthBadge(alert); }
    if (recent != daLastRecent) { daLastRecent = recent; deauthValue(DA_ROW1, String(recent), alert ? red : white); }
    if (total  != daLastTotal)  { daLastTotal  = total;  deauthValue(DA_ROW2, String(total), white); }
    if (chan   != daLastChan)   { daLastChan   = chan;   deauthValue(DA_ROW3, String(chan), white); }
    DeauthEvent e;
    if (detector.lastEvent(e)) {
        char mac[18];
        snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X", e.src[0], e.src[1], e.src[2], e.src[3], e.src[4], e.src[5]);
        if (daLastMac != mac) {
            daLastMac = mac;
            tft.fillRect(14, DA_SRC_Y - 2, 212, 20, bg);
            fontOff(); tft.setTextDatum(TL_DATUM); tft.setTextColor(gold, bg);
            tft.drawString(mac, 20, DA_SRC_Y, 2);
        }
    }
    fontOff();
}

static void drawDeauthScreen() {                     // full paint: static chrome + labels, then values
    const uint16_t bg = uiBg();
    const uint16_t dim = tft.color565(0x8f, 0xa9, 0x8f);
    uiHeaderRu(i18n::tr("Deauth monitor", "Детектор атак"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    daLastAlert = -1; daLastRecent = -1; daLastTotal = -1; daLastChan = -1; daLastMac = "";
    fontSmall();
    tft.setTextDatum(TL_DATUM); tft.setTextColor(dim, bg);
    tft.drawString(i18n::tr("In window", "За окно"), 14, DA_ROW1);
    tft.drawString(i18n::tr("Total", "Всего"),      14, DA_ROW2);
    tft.drawString(i18n::tr("Channel", "Канал"),    14, DA_ROW3);
    tft.drawString(i18n::tr("Last source", "Источник"), 14, DA_SRC_Y - 26);
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
    fontOff();
    drawNetBadge();
    deauthRefresh();
}

// ---- Channel analyzer: per-channel scrolling area graphs (cardiograph style) ----
static const int CH_HIST = 212;                 // samples kept per channel (graph width)
static const int CH_ROWH = 20, CH_TOP = 34, CH_GX = 24, CH_GW = CH_HIST, CH_GH = 17;
static uint8_t chHist[14][CH_HIST];             // load history per channel (0..CH_GH)
static int     chHead = 0;                      // ring write position
static bool    chReady = false;

// Full graph height = this much real airtime. Decoded airtime is a lower bound (we
// miss frames and estimate the rate), and ambient air (beacons only) sits around
// 1%, so full-scale is set low: quiet channels show a small baseline, and genuine
// traffic (a nearby download/stream) clearly rises above it. Honest relative
// busyness, not a calibrated percentage — the footer says "est.".
static const int CH_FULLSCALE_PM = 80;          // permille (~8%) that fills a row

static void channelSample() {                   // push one column of real per-channel airtime
    uint16_t pm[14];
    airtime.read(pm);
    for (int ch = 1; ch <= 13; ch++) {
        int v = pm[ch] * CH_GH / CH_FULLSCALE_PM;
        chHist[ch][chHead] = (uint8_t)(v > CH_GH ? CH_GH : v);
    }
    chHead = (chHead + 1) % CH_HIST;
    chReady = true;
}

// Each graph row is composed off-screen and pushed in one go — fast and flicker-free.
static void channelGraphs() {
    const uint16_t grid = tft.color565(0x1b, 0x24, 0x1b);
    static TFT_eSprite g(&tft);
    static bool made = false;
    if (!made) { g.createSprite(CH_GW, CH_GH); made = true; }
    for (int ch = 1; ch <= 13; ch++) {
        int gy = CH_TOP + (ch - 1) * CH_ROWH;
        bool clean = (ch == 1 || ch == 6 || ch == 11);   // non-overlapping channels
        uint16_t line = clean ? tft.color565(0x5c, 0xe1, 0x74) : tft.color565(0x4a, 0x9a, 0xaa);
        uint16_t fill = clean ? tft.color565(0x1e, 0x4a, 0x28) : tft.color565(0x1b, 0x3a, 0x42);
        g.fillSprite(grid);
        for (int x = 0; x < CH_HIST; x++) {
            int v = chHist[ch][(chHead + x) % CH_HIST];   // oldest -> newest, left to right
            if (v > 0) {
                g.drawFastVLine(x, CH_GH - v, v, fill);   // filled volume
                g.drawPixel(x, CH_GH - v, line);          // the trace on top
            } else {
                g.drawPixel(x, CH_GH - 1, line);
            }
        }
        g.pushSprite(CH_GX, gy);
    }
}

static void channelLabels() {                    // static column of channel numbers
    const uint16_t bg   = uiBg();
    const uint16_t gold = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t dim  = tft.color565(0x8f, 0xa9, 0x8f);
    fontOff();
    for (int ch = 1; ch <= 13; ch++) {
        int gy = CH_TOP + (ch - 1) * CH_ROWH;
        bool clean = (ch == 1 || ch == 6 || ch == 11);
        tft.fillRect(0, gy, CH_GX, CH_ROWH, bg);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(clean ? gold : dim, bg);
        tft.drawString(String(ch), 21, gy + CH_GH / 2, 1);
    }
}

static void drawChannelScreen() {
    const uint16_t bg = uiBg();
    uiHeaderRu(i18n::tr("Channels 2.4G", "Каналы 2.4ГГц"), i18n::tr("airtime", "эфир"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    channelLabels();
    channelGraphs();
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::tr("busy, est.", "занятость ~"));
    drawNetBadge();
}

// ---- 2.4GHz spectrum waterfall (NRF24) ----
// Flicker-free by construction: instead of scrolling a full-screen sprite (a ~31ms
// blit per frame → visible tearing), we write ONE new row directly to the panel at
// a moving cursor and never move the existing pixels — a ring-buffer waterfall with
// a bright sweep line marking "now". Each update is a 228x1 push (~0.1ms). No big
// sprite either, so ~106 KB of heap stays free.
static const int SP_X = 6, SP_Y = 46, SP_W = 228, SP_H = 220;   // plot area (legend row above, 2 label rows below)
static int      spEma[Nrf24Spectrum::CHANNELS];                 // per-channel busy level 0..255 (smoothed) — gives a full colour gradient
static uint32_t spRowAt = 0;
static int      spWy = 0;                                       // current write row within the plot (ring)
static uint8_t  spGrid[SP_W];                                   // per-column WiFi-channel marker: 0 none, 1 minor, 2 major (1/6/11)
// TX self-test state: which Wi-Fi channels are armed for noise injection, where the
// selection caret sits, and whether we are actually emitting. Persist while on screen.
static uint16_t spTxMask = 0;                                   // armed Wi-Fi channels (bit 1..13)
static int      spCursor = 6;                                  // Wi-Fi channel under the caret (1..13)
static bool     spTxOn   = false;                              // master TX on/off
static bool     spLab    = false;                              // true = Lab noise generator (TX controls); false = passive Spectrum
// Traffic view: subtract a slow per-channel baseline so the constant floor (beacons, steady
// BT) fades and only activity ABOVE it stands out. RPD is 1-bit, so this shows changes in
// occupancy (bursts), not decoded traffic — a steady stream shows only when it starts.
// Traffic = a MEDIUM-smoothed occupancy minus the SLOW floor, noise-gated. The medium
// EMA averages out single beacon/BT hits (1-bit RPD is jumpy: one hit = +31), so only a
// sustained rise above the floor survives — the real bursts, not the beacon flicker.
static int      spCurF[Nrf24Spectrum::CHANNELS];               // medium EMA, fixed-point (value * 1024)
static int      spBaseF[Nrf24Spectrum::CHANNELS];              // slow floor,  fixed-point (value * 1024)
static bool     spTraffic = false;                             // false = occupancy heat; true = above-baseline traffic
static int      spBasePrime = 0;                               // >0: glue cur/base to spEma while the EMA settles (no cold-start flood)
static const int SP_CUR_TAU  = 32;                             // medium smoothing (~1 s) — kills single-hit flicker
static const int SP_BASE_TAU = 256;                            // slow floor (~9 s) — steady sources sink into it
static const int SP_TRAFFIC_GAIN = 3, SP_TRAFFIC_FLOOR = 12;   // burst amplification and the noise gate (ignore small jitter)
static const int SP_PRIME_N  = 40;                             // sweeps (~1.5 s) to seed the floor on screen entry
static const uint16_t SP_BG = 0x0862;                          // near-black plot background (RGB565)
// Only the used part of the band is shown, stretched to full width: NRF ch 2..84 =
// 2402..2484 MHz covers all Wi-Fi (1..14) and Bluetooth. The dead ISM edges
// (2400..2402, 2484..2525) are dropped so channels 1..13 spread across the screen.
static const int SP_CH_LO = 2, SP_CH_HI = 84;
static inline int spNrfToX(int nc) { return (nc - SP_CH_LO) * SP_W / (SP_CH_HI - SP_CH_LO); }
static inline int spXToNrf(int x)  { return SP_CH_LO + x * (SP_CH_HI - SP_CH_LO) / SP_W; }

// Energy → heat colour: blue → cyan → green → yellow → red.
static uint16_t spColor(int e, int maxN) {
    if (e <= 0 || maxN <= 0) return SP_BG;
    float f = (float)e / maxN; if (f > 1) f = 1;
    uint8_t r, g, b;
    if      (f < 0.25f) { r = 0;                                g = (uint8_t)(f / 0.25f * 160);         b = 210; }
    else if (f < 0.50f) { r = 0;                                g = 160 + (uint8_t)((f - 0.25f) / 0.25f * 95); b = (uint8_t)(210 - (f - 0.25f) / 0.25f * 210); }
    else if (f < 0.75f) { r = (uint8_t)((f - 0.50f) / 0.25f * 255); g = 255;                            b = 0; }
    else                { r = 255;                              g = (uint8_t)(255 - (f - 0.75f) / 0.25f * 255); b = 0; }
    return tft.color565(r, g, b);
}
static const uint16_t SP_GMAJ = 0x6AA2, SP_GMIN = 0x2164;       // channel dividers: dim gold (1/6/11), faint grey-green (others)

// Push one waterfall row at the ring cursor and advance it, leaving a bright sweep
// line just ahead of the newest data. Shared by the 2.4GHz (NRF) and Sub-GHz (CC1101)
// spectrum screens — one 228x1 blit, no pixels moved, so it never flickers.
static void wfPushRow(const uint16_t* row) {
    tft.setSwapBytes(false);
    tft.pushImage(SP_X, SP_Y + spWy, SP_W, 1, (uint16_t*)row);
    spWy = (spWy + 1) % SP_H;
    tft.drawFastHLine(SP_X, SP_Y + spWy, SP_W, tft.color565(0x6a, 0x80, 0x6a));
}

// The quiet→busy colour legend, shared by both spectrum screens. Cyrillic labels
// need the smooth VLW font (font1 is ASCII-only).
static void wfLegend(uint16_t bg, uint16_t dim, const char* lo = nullptr, const char* hi = nullptr) {
    const int by = 32, bh = 8, bw = 118, bx = SP_X + 46;
    for (int i = 0; i < bw; i++) tft.drawFastVLine(bx + i, by, bh, spColor(i * 255 / (bw - 1), 255));
    tft.drawRect(bx - 1, by - 1, bw + 2, bh + 2, tft.color565(0x2a, 0x3a, 0x2a));
    fontTiny();
    tft.setTextColor(dim, bg);
    tft.setTextDatum(MR_DATUM); tft.drawString(lo ? lo : i18n::tr("quiet", "тихо"), bx - 5, by + bh / 2);
    tft.setTextDatum(ML_DATUM); tft.drawString(hi ? hi : i18n::tr("busy", "занято"), bx + bw + 5, by + bh / 2);
    fontOff();
}

static void spectrumStop() { spTxOn = false; nrf.end(); }

// Push the armed set to the radio (empty when TX is off, so nothing is emitted).
static void spApplyTx() { nrf.setTxWifiMask(spTxOn ? spTxMask : 0); }

// The channel axis below the plot: a tick + number per Wi-Fi channel (armed ones in
// orange-red), plus the selection caret. Redrawn on any change; touches only the strip
// under the plot, never the live waterfall above it.
static void spDrawAxis() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f), gold = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t armed = tft.color565(0xff, 0x5a, 0x32);
    const uint16_t caret = spTxOn ? armed : tft.color565(0x46, 0xd6, 0xff);   // cyan idle → red while emitting
    tft.fillRect(0, SP_Y + SP_H + 1, 240, 34, bg);                           // clear the strip (footer starts at y=301)
    fontOff();                                                               // channel numbers use the built-in font (arg 1); a loaded VLW would override it
    tft.setTextDatum(MC_DATUM);
    for (int w = 1; w <= 13; w++) {
        int sx = spNrfToX(Nrf24Spectrum::wifiCenterNrfCh(w));
        if (sx < 0 || sx >= SP_W) continue;
        int x = SP_X + sx;
        bool major = (w == 1 || w == 6 || w == 11);
        uint16_t col = (spLab && (spTxMask & (1 << w))) ? armed : (major ? gold : dim);
        if (spLab && w == spCursor) tft.fillTriangle(x - 3, SP_Y + SP_H + 1, x + 3, SP_Y + SP_H + 1, x, SP_Y + SP_H + 7, caret);
        tft.drawFastVLine(x, SP_Y + SP_H + 8, 3, col);
        tft.setTextColor(col, bg);
        tft.drawString(String(w), x, SP_Y + SP_H + (w & 1 ? 16 : 26), 1);     // odd row higher, even lower
    }
}

static void spDrawFooter() {
    // Passive Spectrum just shows a legend; the Lab generator shows the TX controls.
    // Only glyphs present in the tiny VLW subset (letters, space, ◀ ▶ ▼): ▲▼ move the
    // caret, the middle key (OK) arms the channel, ▶ starts/stops the noise.
    if (!spLab) { uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
                             spTraffic ? i18n::tr("traffic ▶", "трафик ▶") : i18n::tr("occupancy ▶", "занятость ▶")); return; }
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
               spTxOn ? (i18n::isRu() ? "▶ стоп"           : "▶ stop")
                      : (i18n::isRu() ? "OK канал  ▶ шум"  : "OK chan  ▶ noise"));
}

// SELECT arms/disarms the channel under the caret; live if we're already emitting.
static void spToggleArm() {
    spTxMask ^= (uint16_t)(1 << spCursor);
    if (spTxMask == 0) spTxOn = false;              // nothing armed → nothing to emit
    spApplyTx();
    spDrawAxis();
    spDrawFooter();
}

// RIGHT starts/stops the noise. Pressing it with nothing armed arms the caret channel.
static void spToggleTx() {
    if (!spTxOn && spTxMask == 0) spTxMask |= (uint16_t)(1 << spCursor);
    spTxOn = !spTxOn && spTxMask != 0;
    spApplyTx();
    spDrawAxis();
    spDrawFooter();
}

static void drawSpectrumScreen() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f);
    char hr[20];
    if (spLab) {
        snprintf(hr, sizeof(hr), "x%d %s", nrf.modules(),
                 nrf.txListenSelf() ? i18n::tr("chk", "проба") : i18n::tr("max", "макс"));
        uiHeaderRu(i18n::tr("Noise 2.4", "Шум 2.4ГГц"), hr);
    } else {
        snprintf(hr, sizeof(hr), "NRF24 x%d", nrf.modules());
        uiHeaderRu(i18n::tr("2.4GHz Spectrum", "Спектр 2.4ГГц"), hr);
    }
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    wfLegend(bg, dim, (spTraffic && !spLab) ? i18n::tr("base", "фон") : nullptr,
                      (spTraffic && !spLab) ? i18n::tr("spike", "всплеск") : nullptr);
    tft.fillRect(SP_X, SP_Y, SP_W, SP_H, SP_BG);
    tft.drawRect(SP_X - 1, SP_Y - 1, SP_W + 2, SP_H + 2, tft.color565(0x2a, 0x3a, 0x2a));
    // Vertical divider column for every Wi-Fi channel 1..13 (1/6/11 stand out); pre-drawn
    // full height and overwritten by real energy as the waterfall fills. The tick+number
    // strip and the selection caret below the plot are drawn by spDrawAxis().
    memset(spGrid, 0, sizeof(spGrid));
    for (int w = 1; w <= 13; w++) {
        int sx = spNrfToX(Nrf24Spectrum::wifiCenterNrfCh(w));
        if (sx < 0 || sx >= SP_W) continue;
        spGrid[sx] = (w == 1 || w == 6 || w == 11) ? 2 : 1;
        tft.drawFastVLine(SP_X + sx, SP_Y, SP_H, spGrid[sx] == 2 ? SP_GMAJ : SP_GMIN);
    }
    spDrawAxis();
    spDrawFooter();
    drawNetBadge();
    memset(spEma, 0, sizeof(spEma)); spBasePrime = SP_PRIME_N; spRowAt = millis(); spWy = 0;   // baseline seeds from spEma over the first ~1 s (no cold-start flood)
}

// Spectrum view: occupancy heat vs traffic (above-baseline). Persisted; shared by the
// passive Spectrum and the Lab generator (the passive screen's ▶ flips it live).
static void saveSpView(bool traffic) { Preferences p; p.begin("leshy", false); p.putBool("sp_view", traffic); p.end(); }
static bool loadSpView() { Preferences p; p.begin("leshy", true); bool v = p.getBool("sp_view", false); p.end(); return v; }
// Repaint only the mode chrome (legend + footer) above/below the plot — keeps the
// waterfall and the learned baseline, so occupancy <-> traffic flips instantly.
static void spRepaintChrome() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f);
    tft.fillRect(0, 28, 240, SP_Y - 29, bg);     // legend band above the plot (does not touch the waterfall)
    wfLegend(bg, dim, (spTraffic && !spLab) ? i18n::tr("base", "фон") : nullptr,
                      (spTraffic && !spLab) ? i18n::tr("spike", "всплеск") : nullptr);
    spDrawFooter();
}
static void spToggleView() {
    spTraffic = !spTraffic;
    saveSpView(spTraffic);
    spRepaintChrome();
}

static void spectrumTick() {
    uint8_t sw[Nrf24Spectrum::CHANNELS];
    nrf.sweep(sw);                                       // ~25ms across 126 channels; RPD is 1-bit per channel
    for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) {
        spEma[c] += ((int)sw[c] * 255 - spEma[c]) / 8;  // fast occupancy (0..255) → occupancy view
        int e1024 = (int)spEma[c] << 10;
        if (spBasePrime) { spCurF[c] = e1024; spBaseF[c] = e1024; }        // seed both to the settling EMA — no cold-start flood
        else {
            spCurF[c]  += (e1024 - spCurF[c])  / SP_CUR_TAU;               // medium: averages out single beacon/BT hits
            spBaseF[c] += (e1024 - spBaseF[c]) / SP_BASE_TAU;              // slow floor: steady sources sink in
        }
    }
    if (spBasePrime) spBasePrime--;
    if (millis() - spRowAt < 37) return;                // one waterfall row every ~37ms (fast scroll)
    spRowAt = millis();
    static uint16_t row[SP_W];
    for (int x = 0; x < SP_W; x++) {
        int c = spXToNrf(x);
        if (c < 0) c = 0; else if (c >= Nrf24Spectrum::CHANNELS) c = Nrf24Spectrum::CHANNELS - 1;
        int v = spEma[c];
        if (spTraffic && !spLab) {                      // traffic (passive only): medium level above the slow floor, noise-gated
            int d = ((spCurF[c] - spBaseF[c]) >> 10) - SP_TRAFFIC_FLOOR;
            v = d > 0 ? d * SP_TRAFFIC_GAIN : 0;
            if (v > 255) v = 255;
        }
        if      (v > 8)            row[x] = spColor(v, 255);             // energy / burst → heat gradient
        else if (spGrid[x] == 2)   row[x] = SP_GMAJ;                      // channel divider shows through quiet air
        else if (spGrid[x] == 1)   row[x] = SP_GMIN;
        else                       row[x] = SP_BG;
    }
    wfPushRow(row);                                     // one row, direct — no pixels moved, no flicker
}

// ---- Sub-GHz spectrum waterfall (CC1101) ----
// Same flicker-free ring waterfall, but the CC1101 gives a real RSSI per frequency,
// so the heat is true signal strength. RIGHT cycles the display window: whole span,
// then aimed technical bands (315/433 remotes & alarms, 868/915 mesh & LoRa).
static const int SUB_NB = 40;                           // frequencies swept per row (fewer = ~3x faster scroll; mapped across the width)
static uint8_t   subE[SUB_NB];
static int       subBin = 0;                            // sweep progress (spread across loop iterations for button responsiveness)

static void subStop() { cc.end(); }

static void drawSubScreen() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f), gold = tft.color565(0xff, 0xcf, 0x3f);
    const Cc1101Spectrum::Band& b = cc.bandInfo();
    uiHeaderRu(i18n::tr("Sub-GHz Spectrum", "Спектр Sub-GHz"), "CC1101");
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    wfLegend(bg, dim);
    tft.fillRect(SP_X, SP_Y, SP_W, SP_H, SP_BG);
    tft.drawRect(SP_X - 1, SP_Y - 1, SP_W + 2, SP_H + 2, tft.color565(0x2a, 0x3a, 0x2a));
    // axis: localized band name (centre) on the VLW font + the MHz range at the ends
    fontTiny();
    tft.setTextColor(gold, bg); tft.setTextDatum(MC_DATUM);
    tft.drawString(i18n::isRu() ? b.ru : b.en, SP_X + SP_W / 2, SP_Y + SP_H + 13);
    tft.setTextColor(dim, bg);
    tft.setTextDatum(ML_DATUM); tft.drawString(String(b.loKHz / 1000), SP_X, SP_Y + SP_H + 13);
    tft.setTextDatum(MR_DATUM); tft.drawString(String(b.hiKHz / 1000) + (i18n::isRu() ? " МГц" : " MHz"), SP_X + SP_W, SP_Y + SP_H + 13);
    fontOff();
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::tr("band ▶", "диапазон ▶"));
    drawNetBadge();
    spWy = 0; subBin = 0;
}

static void subTick() {
    // Sweep only a few bins per loop iteration so buttons (band switch) stay snappy —
    // a full CC1101 sweep is ~150-250ms, too long to block the input poll.
    for (int k = 0; k < 10 && subBin < SUB_NB; k++, subBin++) subE[subBin] = cc.sampleBin(subBin, SUB_NB);
    if (subBin < SUB_NB) return;                        // sweep still in progress
    subBin = 0;
    static uint16_t row[SP_W];
    for (int x = 0; x < SP_W; x++) {
        int bin = x * SUB_NB / SP_W; if (bin >= SUB_NB) bin = SUB_NB - 1;
        int e = subE[bin];
        row[x] = (e > 12) ? spColor(e, 255) : SP_BG;    // above the noise floor → heat
    }
    wfPushRow(row);
}

// ---- Wi-Fi scan selection + per-network options ----
static void ensureWifiVisible() {
    int n = engine.wifiCount();
    if (wifiSel > n - 1) wifiSel = n - 1;
    if (wifiSel < 0) wifiSel = 0;
    if (wifiSel < off) off = wifiSel;
    if (wifiSel >= off + UI_VISIBLE) off = wifiSel - UI_VISIBLE + 1;
    if (off < 0) off = 0;
}

static void gotoWifi() {
    if (scanPausedAt && millis() - scanPausedAt > 5000) engine.clearSparks();  // long gap → the graph would splice two sessions into one line
    scanPausedAt = 0;
    engine.setMode(ScanEngine::SCAN_WIFI); engine.resume();
    st = ST_WIFI; seenWifiGen = engine.wifiGen();
    ensureWifiVisible();
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());   // clear the canvas once on entry; ticks repaint rows only
    drawList(true);
}

static void openNetOptions() {
    if (!engine.wifiRow(wifiSel, netSel)) return;
    engine.pause();                          // freeze the scan while the menu is open
    scanPausedAt = millis();                 // remember when, so a long detour resets the RSSI graph on return
    String mine; bool isMine = net.isMine(netSel.bssid, mine);
    optTitle = netSel.ssid.length() ? netSel.ssid : (isMine ? mine : String(i18n::tr("<hidden>", "<скрытая>")));
    optN = 0;
    optLabels[optN] = i18n::tr("Details", "Подробнее"); optIds[optN] = OPT_NET_DETAILS; optN++;
    optSel = 0; optReturn = ST_WIFI;
    st = ST_OPTIONS; drawOptionsScreen();
}

static void drawNetDetails() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    String mine; bool isMine = net.isMine(netSel.bssid, mine);
    bool named = netSel.ssid.length() > 0;
    String name = named ? netSel.ssid : (isMine ? mine : String(i18n::tr("<hidden>", "<скрытая>")));
    uiHeaderRu(i18n::tr("Network", "Сеть"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    fontSmall(); tft.setTextDatum(TL_DATUM);
    int y = 46;
    tft.setTextColor(dim, bg);  tft.drawString(i18n::tr("Name", "Имя"), 14, y); y += 22;
    tft.setTextColor(isMine ? gold : white, bg);
    tft.drawString((isMine ? String("* ") : String("")) + name, 22, y); y += 30;
    char mac[18];
    snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X", netSel.bssid[0], netSel.bssid[1], netSel.bssid[2], netSel.bssid[3], netSel.bssid[4], netSel.bssid[5]);
    tft.setTextColor(dim, bg); tft.drawString("BSSID", 14, y); y += 20;
    fontOff(); tft.setTextColor(white, bg); tft.drawString(mac, 22, y, 2); fontSmall(); y += 30;
    tft.setTextColor(dim, bg); tft.drawString(i18n::tr("Channel", "Канал"), 14, y);
    tft.setTextDatum(TR_DATUM); tft.setTextColor(white, bg); tft.drawString(String(netSel.channel), 226, y); tft.setTextDatum(TL_DATUM); y += 24;
    tft.setTextColor(dim, bg); tft.drawString("RSSI", 14, y);
    tft.setTextDatum(TR_DATUM); tft.setTextColor(white, bg); tft.drawString(String(netSel.rssi) + " dBm", 226, y); tft.setTextDatum(TL_DATUM); y += 24;
    tft.setTextColor(dim, bg); tft.drawString(i18n::tr("Security", "Шифр"), 14, y);
    tft.setTextDatum(TR_DATUM); tft.setTextColor(white, bg); tft.drawString(WifiScanner::authName(netSel.auth), 226, y); tft.setTextDatum(TL_DATUM); y += 26;
    if (netSel.hidden) { tft.setTextColor(tft.color565(0xff, 0xa5, 0x2a), bg); tft.drawString(i18n::tr("hidden network", "скрытая сеть"), 14, y); }
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
    fontOff();
    drawNetBadge();
}

// ---- Responsible-use notice: full text, scrollable, must be read to the end ----
static const int LEG_TOP = 34, LEG_LH = 15, LEG_LINES = 17;   // visible text lines
static String  legLines[220];                                  // wrapped lines
static int     legN = 0, legOff = 0;
static bool    legAccepted = false;      // read to the end in this viewing
static bool    legFirstRun = false;      // gate at boot (must accept once)

static bool legalSeen() { Preferences p; p.begin("leshy", true); bool v = p.getBool("legal_ok", false); p.end(); return v; }
static void legalMarkSeen() { Preferences p; p.begin("leshy", false); p.putBool("legal_ok", true); p.end(); }

static void legalWrap() {                 // wrap the doc into display lines (smooth font metrics)
    const LegalDoc& d = i18n::isRu() ? LEGAL_DOC_RU : LEGAL_DOC_EN;
    fontTiny();
    legN = 0; legOff = 0; legAccepted = false;
    for (int i = 0; i < d.n && legN < 218; i++) {
        String par = d.p[i];
        if (par.length() == 0) { legLines[legN++] = ""; continue; }
        bool head = par.startsWith("#");
        if (head) par = par.substring(2);
        String cur, word;
        for (int k = 0; k <= (int)par.length(); k++) {
            char c = (k < (int)par.length()) ? par[k] : ' ';
            if (c == ' ') {
                String test = cur.length() ? cur + " " + word : word;
                if (tft.textWidth(test) > 222 && cur.length()) { legLines[legN++] = (head ? "#" : "") + cur; cur = word; }
                else cur = test;
                word = "";
                if (legN >= 218) break;
            } else word += c;
        }
        if (cur.length() && legN < 218) legLines[legN++] = (head ? "#" : "") + cur;
    }
    fontOff();
}

static void drawLegalScreen() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    int maxOff = legN - LEG_LINES; if (maxOff < 0) maxOff = 0;
    if (legOff >= maxOff) legAccepted = true;         // scrolled to the end = read
    char pct[12]; snprintf(pct, sizeof(pct), "%d%%", maxOff ? (legOff * 100 / maxOff) : 100);
    uiHeaderRu(i18n::tr("Responsible use", "Ответственность"), pct);
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    fontTiny();
    tft.setTextDatum(TL_DATUM);
    for (int i = 0; i < LEG_LINES; i++) {
        int idx = legOff + i;
        if (idx >= legN) break;
        String ln = legLines[idx];
        bool head = ln.startsWith("#");
        if (head) ln = ln.substring(1);
        tft.setTextColor(head ? gold : white, bg);
        tft.drawString(ln, 9, LEG_TOP + i * LEG_LH);
    }
    if (legFirstRun)
        uiFooterRu(legAccepted ? (i18n::isRu() ? "OK — принимаю" : "OK — I accept")
                               : (i18n::isRu() ? "листай вниз" : "scroll down"),
                   legAccepted ? "" : (i18n::isRu() ? "до конца ▼" : "to the end ▼"));
    else
        uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::isRu() ? "листай ▼" : "scroll ▼");
    fontOff();
}

static void gotoLegal(bool firstRun) {
    legFirstRun = firstRun;
    legalWrap();
    st = ST_LEGAL;
    drawLegalScreen();
}

// First boot: pick the language, then the notice must be read before anything else.
static const char* const LANGPICK[] = { "English", "Русский" };
static int langPickSel = 1;

static void drawLangPick() {
    const uint16_t bg = uiBg();
    const uint16_t gold = tft.color565(0xff, 0xcf, 0x3f);
    uiHeaderRu("ESP32-Leshy");
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    fontSmall();
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(gold, bg);
    tft.drawString("Language / Язык", 120, 70);
    fontOff();
    for (int i = 0; i < 2; i++) drawActionBtn(120 + i * 48, LANGPICK[i], i == langPickSel);
    uiFooterRu("", "OK ▶");
}

static void back() {
    switch (st) {
        case ST_LANGPICK:  return;                                         // no way out before choosing
        case ST_LEGAL:     if (legFirstRun) return;                        // must accept on first run
                           showMenu();                                     return;
        case ST_DEAUTH:    detector.stop(); showMenu();                    return;
        case ST_CHANNELS:  airtime.stop(); showMenu();                     return;
        case ST_SPECTRUM:  spectrumStop(); showMenu();                     return;
        case ST_SUBSPECTRUM: subStop(); showMenu();                        return;
        case ST_NETINFO:   gotoWifi();                                     return;
        case ST_OTA:       if (ota.busy()) return;   // checking or downloading — stay put
                           showMenu();                                     return;
        case ST_PROVISION: net.stopProvision(); gotoConn();               return;
        case ST_CONFIRM:   cancelConfirm();                               return;
        case ST_OPTIONS:   if (optReturn == ST_HIDDEN) gotoHidden(); else if (optReturn == ST_WIFI) gotoWifi(); else showMenu(); return;
        case ST_MENU:      if (depth > 0) { depth--; showMenu(); }        return;
        default:           showMenu();                                    return;  // WIFI/BLE/INFO/CONN/HIDDEN
    }
}

static void launch(int feat) {
    // An OTA check/download owns the radio — never start a screen that touches it.
    if (ota.busy() && feat != F_OTA) return;
    if (st == ST_DEAUTH)    detector.stop();       // release promiscuous before anything else
    if (st == ST_CHANNELS)  airtime.stop();        // also promiscuous
    if (st == ST_SPECTRUM)  spectrumStop();        // release NRF24
    if (st == ST_SUBSPECTRUM) subStop();           // release CC1101
    if (st == ST_PROVISION) net.stopProvision();   // drop the SoftAP + portal
    engine.pause();                                // scanning is off unless the target feature turns it back on
    infoAction = -1;                               // most info screens aren't adjustable; the two that are set this
    switch (feat) {
        case F_WIFI_SCAN:   wifiSel = 0; off = 0; engine.clearSparks(); gotoWifi(); break;
        case F_CONN:        connSel = 0; gotoConn(); break;
        case F_HIDDEN:      hidSel = 0; hidOff = 0; gotoHidden(); break;
        case F_DEAUTH:      engine.pauseAndWait();     // promiscuous needs the radio to itself
                            if (detector.begin()) { st = ST_DEAUTH; drawDeauthScreen(); }
                            else { infoTitle = i18n::tr("Deauth monitor", "Детектор атак"); infoBody = i18n::tr("Radio busy", "Радио занято"); infoNote = ""; st = ST_INFO; drawInfo(); }
                            break;
        case F_CHANNELS:    engine.pauseAndWait();          // airtime needs the radio to itself (promiscuous)
                            if (airtime.begin()) { st = ST_CHANNELS; memset(chHist, 0, sizeof(chHist)); chHead = 0; drawChannelScreen(); }
                            else { infoTitle = i18n::tr("Channels 2.4G", "Каналы 2.4ГГц"); infoBody = i18n::tr("Radio busy", "Радио занято"); infoNote = ""; st = ST_INFO; drawInfo(); }
                            break;
        case F_SPECTRUM:    engine.pause();                 // NRF24 is a separate SPI radio; free the ESP radio's CPU load anyway
                            spLab = false; spTxOn = false; spTxMask = 0;   // passive viewer — never transmits
                            if (nrf.begin()) { st = ST_SPECTRUM; drawSpectrumScreen(); }
                            else { infoTitle = i18n::tr("2.4GHz Spectrum", "Спектр 2.4ГГц"); infoBody = i18n::tr("NRF24 not found", "NRF24 не найден");
                                   infoNote = i18n::tr("This build expects an NRF24 module in slot 2.", "Нужен модуль NRF24 в слоте 2."); st = ST_INFO; drawInfo(); }
                            break;
        case F_NOISEGEN:    engine.pause();
                            spLab = true; spTxOn = false; spCursor = 6;
                            spTxMask = (1 << 1) | (1 << 6) | (1 << 11);    // preset the non-overlapping channels, ready to fire
                            if (nrf.begin()) { st = ST_SPECTRUM; drawSpectrumScreen(); }
                            else { infoTitle = i18n::tr("Noise gen 2.4", "Генератор шума"); infoBody = i18n::tr("NRF24 not found", "NRF24 не найден");
                                   infoNote = i18n::tr("This build expects an NRF24 module in slot 2.", "Нужен модуль NRF24 в слоте 2."); st = ST_INFO; drawInfo(); }
                            break;
        case F_TXMODE:      drawTxModeInfo(); break;
        case F_SUBSPECTRUM: engine.pause();
                            if (cc.begin()) { cc.setBand(0); st = ST_SUBSPECTRUM; drawSubScreen(); }
                            else { infoTitle = i18n::tr("Sub-GHz Spectrum", "Спектр Sub-GHz"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_BLE_SCAN:    engine.setMode(ScanEngine::SCAN_BLE);  engine.resume(); st = ST_BLE;  off = 0; seenBleGen  = engine.bleGen();
                            tft.fillRect(0, 28, 240, 320 - 28, uiBg()); drawList(true); break;
        case F_SUBGHZ_SOON: infoTitle = i18n::tr("Sub-GHz Recorder", "Запись Sub-GHz"); infoBody = i18n::tr("Record / replay 315-868 MHz", "Запись/повтор 315-868 МГц"); infoNote = i18n::tr("Coming soon (needs CC1101)", "Скоро (нужен CC1101)"); st = ST_INFO; drawInfo(); break;
        case F_ABOUT:       st = ST_INFO; drawAboutScreen(); break;
        case F_LEGAL:       gotoLegal(false); break;
        case F_OTA:         gotoOta(); break;
        case F_LEDS:        drawLedsInfo(); break;         // shows current; SELECT/RIGHT cycles in place
        case F_BACKLIGHT:   drawBacklightInfo(); break;
        case F_TXPOWER:     drawTxPowerInfo(); break;
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

// One place that handles a navigation event, whether it came from the keypad or the serial remote.
static void onKey(int ev) {
    switch (ev) {
        case Buttons::UP:
            if (st == ST_MENU) { if (curSel() > 0) { int p = curSel(); curSel()--; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI)    { if (wifiSel > 0) { wifiSel--; ensureWifiVisible(); drawList(false); } }
            else if (st == ST_BLE)     { if (off > 0) { off--; drawList(false); } }
            else if (st == ST_CONN)    { if (connSel > 0) { int p = connSel; connSel--; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel > 0)  { int p = optSel;  optSel--;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel > 0)  { int p = hidSel; hidSel--; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            else if (st == ST_LEGAL)   { if (legOff > 0) { legOff -= 4; if (legOff < 0) legOff = 0; drawLegalScreen(); } }
            else if (st == ST_LANGPICK){ if (langPickSel > 0) { langPickSel--; drawLangPick(); } }
            else if (st == ST_SPECTRUM && spLab){ if (spCursor > 1)  { spCursor--; spDrawAxis(); } }   // move the TX channel caret
            break;
        case Buttons::DOWN:
            if (st == ST_MENU) { if (curSel() < MENUS[curMenu()].n - 1) { int p = curSel(); curSel()++; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI)    { if (wifiSel < engine.wifiCount() - 1) { wifiSel++; ensureWifiVisible(); drawList(false); } }
            else if (st == ST_BLE)     { int m = engine.bleCount() - UI_VISIBLE; if (m < 0) m = 0; if (off < m) { off++; drawList(false); } }
            else if (st == ST_CONN)    { if (connSel < connActN - 1) { int p = connSel; connSel++; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel < optN - 1)      { int p = optSel;  optSel++;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel < revealer.count() - 1) { int p = hidSel; hidSel++; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            else if (st == ST_LEGAL)   { int m = legN - LEG_LINES; if (m < 0) m = 0; if (legOff < m) { legOff += 4; if (legOff > m) legOff = m; drawLegalScreen(); } }
            else if (st == ST_LANGPICK){ if (langPickSel < 1) { langPickSel++; drawLangPick(); } }
            else if (st == ST_SPECTRUM && spLab){ if (spCursor < 13) { spCursor++; spDrawAxis(); } }   // move the TX channel caret
            break;
        case Buttons::SELECT:                    // middle = enter / confirm
            if (st == ST_LANGPICK) { Lang l = langPickSel ? Lang::RU : Lang::EN; i18n::set(l); saveLang(l); gotoLegal(true); }
            else if (st == ST_LEGAL) {
                if (!legFirstRun) { showMenu(); }
                else if (legAccepted) { legalMarkSeen(); legFirstRun = false; depth = 0; showMenu(); }
            }
            else if (st == ST_MENU) activate();
            else if (st == ST_CONN) connActivate();
            else if (st == ST_OPTIONS) optActivate();
            else if (st == ST_CONFIRM) doConfirm();
            else if (st == ST_OTA) otaActivate();
            else if (st == ST_WIFI) openNetOptions();
            else if (st == ST_SPECTRUM && spLab) spToggleArm();   // arm/disarm the caret channel for TX noise
            else if (st == ST_INFO && infoAction == F_LEDS)      { leds.cycleBrightness(); drawLedsInfo(); }
            else if (st == ST_INFO && infoAction == F_BACKLIGHT) { uiBacklightCycle();     drawBacklightInfo(); }
            else if (st == ST_INFO && infoAction == F_TXPOWER)   { txPowerCycle();         drawTxPowerInfo(); }
            else if (st == ST_INFO && infoAction == F_TXMODE)    { txModeCycle();          drawTxModeInfo(); }
            break;
        case Buttons::RIGHT:                      // right = options / action
            if (st == ST_LANGPICK) { Lang l = langPickSel ? Lang::RU : Lang::EN; i18n::set(l); saveLang(l); gotoLegal(true); }
            else if (st == ST_LEGAL) {
                if (!legFirstRun) { showMenu(); }
                else if (legAccepted) { legalMarkSeen(); legFirstRun = false; depth = 0; showMenu(); }
            }
            else if (st == ST_MENU) activate();
            else if (st == ST_CONN) connActivate();
            else if (st == ST_OPTIONS) optActivate();
            else if (st == ST_CONFIRM) doConfirm();
            else if (st == ST_OTA) otaActivate();
            else if (st == ST_HIDDEN) openHiddenOptions();
            else if (st == ST_WIFI) openNetOptions();
            else if (st == ST_SUBSPECTRUM) { cc.setBand(cc.band() + 1); drawSubScreen(); }   // cycle the displayed band
            else if (st == ST_SPECTRUM && spLab) spToggleTx();    // Lab: start/stop transmitting noise into the armed channels
            else if (st == ST_SPECTRUM)          spToggleView();  // passive: flip occupancy <-> traffic view
            else if (st == ST_INFO && infoAction == F_LEDS)      { leds.cycleBrightness(); drawLedsInfo(); }
            else if (st == ST_INFO && infoAction == F_BACKLIGHT) { uiBacklightCycle();     drawBacklightInfo(); }
            else if (st == ST_INFO && infoAction == F_TXPOWER)   { txPowerCycle();         drawTxPowerInfo(); }
            else if (st == ST_INFO && infoAction == F_TXMODE)    { txModeCycle();          drawTxModeInfo(); }
            break;
        case Buttons::LEFT:
            back();
            break;
        default:
            break;
    }
}

// Serial remote (headless testing over USB): u/d/l/r/o = keys; scan/ble/hidden/conn/menu = jump.
static void serialControl() {
    static char buf[24];
    static uint8_t len = 0;
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (!len) continue;
            buf[len] = 0; len = 0;
            // the first-run notice must not be bypassed — only nav keys work there
            if (st == ST_LANGPICK || (st == ST_LEGAL && legFirstRun)) {
                if      (!strcmp(buf, "u")) onKey(Buttons::UP);
                else if (!strcmp(buf, "d")) onKey(Buttons::DOWN);
                else if (!strcmp(buf, "o") || !strcmp(buf, "s") || !strcmp(buf, "r")) onKey(Buttons::SELECT);
                Serial.printf("[cmd] %s -> st=%d\n", buf, (int)st);
                continue;
            }
            if      (!strcmp(buf, "u")) onKey(Buttons::UP);
            else if (!strcmp(buf, "d")) onKey(Buttons::DOWN);
            else if (!strcmp(buf, "l")) onKey(Buttons::LEFT);
            else if (!strcmp(buf, "r")) onKey(Buttons::RIGHT);
            else if (!strcmp(buf, "o") || !strcmp(buf, "s")) onKey(Buttons::SELECT);
            else if (!strcmp(buf, "scan"))   launch(F_WIFI_SCAN);
            else if (!strcmp(buf, "ble"))    launch(F_BLE_SCAN);
            else if (!strcmp(buf, "hidden")) launch(F_HIDDEN);
            else if (!strcmp(buf, "conn"))   launch(F_CONN);
            else if (!strcmp(buf, "ota"))    launch(F_OTA);
            else if (!strcmp(buf, "deauth")) launch(F_DEAUTH);
            else if (!strcmp(buf, "chan"))   launch(F_CHANNELS);
            else if (!strcmp(buf, "legal"))  launch(F_LEGAL);
            else if (!strcmp(buf, "legalreset")) { Preferences p; p.begin("leshy", false); p.remove("legal_ok"); p.end(); Serial.println("[cmd] legal flag cleared — reboot to see the gate"); }
            else if (!strcmp(buf, "leds"))  { leds.selfTest(); continue; }                       // QA: all four pixels + their order
            else if (!strcmp(buf, "ledbr")) { Serial.printf("[leds] brightness -> %u/255\n", leds.cycleBrightness()); continue; }
            else if (!strcmp(buf, "bl"))    { Serial.printf("[bl] backlight -> %u/255\n", uiBacklightCycle()); continue; }
            else if (!strcmp(buf, "txpwr")) { Serial.printf("[txpwr] -> %d dBm\n", Nrf24Spectrum::txPowerDbm(txPowerCycle())); continue; }
            else if (!strcmp(buf, "txmode")){ Serial.printf("[txmode] -> %s\n", txModeCycle() ? "verify (listen)" : "maximum (all TX)"); continue; }
            else if (!strcmp(buf, "view"))  { spTraffic = !spTraffic; saveSpView(spTraffic); if (st == ST_SPECTRUM) spRepaintChrome(); Serial.printf("[view] -> %s\n", spTraffic ? "traffic" : "occupancy"); continue; }
            else if (!strcmp(buf, "air"))   { uint16_t pm[14]; airtime.read(pm); Serial.printf("[air] run=%d ch=%d busy‰:", (int)airtime.isRunning(), (int)airtime.channel());
                                              for (int ch = 1; ch <= 13; ch++) Serial.printf(" %d:%u", ch, pm[ch]); Serial.println(); continue; }
            else if (!strcmp(buf, "nrfdiag")) { engine.pauseAndWait(); nrf.diag(); continue; }
            else if (!strcmp(buf, "cc")) {   // QA: probe CC1101 + a quick RSSI sweep of the current band
                engine.pauseAndWait();
                bool ok = cc.begin();
                Serial.printf("[cc] present=%d version=0x%02X\n", (int)ok, cc.version());
                if (ok) {
                    static uint8_t e[64];
                    cc.sweep(e, 64);
                    Serial.printf("[cc] %s RSSI64:", cc.bandInfo().en);
                    for (int i = 0; i < 64; i++) Serial.printf(" %d", e[i]);
                    Serial.println();
                }
                cc.end();
                continue;
            }
            else if (!strcmp(buf, "nrf"))   {   // QA: probe the NRF24 spectrum sniffer on real hardware
                engine.pauseAndWait();
                bool ok = nrf.begin();
                Serial.printf("[nrf] present=%d modules=%d\n", (int)ok, nrf.modules());
                if (ok) {
                    static uint16_t acc[Nrf24Spectrum::CHANNELS];
                    memset(acc, 0, sizeof(acc));
                    uint8_t sw[Nrf24Spectrum::CHANNELS];
                    for (int p = 0; p < 300; p++) { nrf.sweep(sw); for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) acc[c] += sw[c]; }
                    Serial.print("[nrf] hits/300:");
                    for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) if (acc[c]) Serial.printf(" %d:%d", c, acc[c]);
                    Serial.println();
                    for (int w = 1; w <= 13; w++) { int nc = Nrf24Spectrum::wifiCenterNrfCh(w); Serial.printf("  wifi%d (nrf%d): %d\n", w, nc, acc[nc]); }
                }
                nrf.end();
                continue;
            }
            else if (!strcmp(buf, "stat")) { Serial.printf("[stat] st=%d wifiGen=%u bleGen=%u scanIdle=%d heap=%u largest=%u\n",
                                             (int)st, (unsigned)engine.wifiGen(), (unsigned)engine.bleGen(),
                                             (int)engine.isIdle(), (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap()); continue; }
            else if (!strncmp(buf, "otafail", 7)) {            // QA: render each full-screen OTA error without a real failure
                static const struct { OtaManager::Err e; int code; const char* d; OtaManager::Phase ph; } S[] = {
                    { OtaManager::E_NONET,     0,   "wifi not connected (wl=3)",              OtaManager::CHECKING },
                    { OtaManager::E_TIME,      0,   "no NTP time (epoch=42)",                 OtaManager::CHECKING },
                    { OtaManager::E_API,       -1,  "conn: connection refused",              OtaManager::CHECKING },
                    { OtaManager::E_PARSE,     200, "IncompleteInput: stream ended mid-object", OtaManager::CHECKING },
                    { OtaManager::E_RATELIMIT, 403, "",                                       OtaManager::CHECKING },
                    { OtaManager::E_HASH,      0,   "",                                       OtaManager::DOWNLOADING },
                    { OtaManager::E_HTTP,      404, "download HTTP 404",                      OtaManager::DOWNLOADING },
                    { OtaManager::E_NOMEM,     0,   "no RAM for OTA task",                    OtaManager::CHECKING },
                };
                int n = (buf[7] == ' ') ? atoi(buf + 8) : 0;
                if (n < 0 || n >= (int)(sizeof(S) / sizeof(S[0]))) n = 0;
                if (!ota.simulateFail(S[n].e, S[n].code, S[n].d, S[n].ph)) { Serial.println("[cmd] otafail ignored — OTA busy"); continue; }
                if (st == ST_DEAUTH)      detector.stop();     // same teardown launch() does — don't strand the radio
                if (st == ST_CHANNELS)    airtime.stop();
                if (st == ST_SPECTRUM)    spectrumStop();      // also stops any TX carrier
                if (st == ST_SUBSPECTRUM) subStop();
                if (st == ST_PROVISION)   net.stopProvision();
                engine.pause();
                st = ST_OTA; seenOtaGen = ota.gen(); seenOtaPhase = (int)ota.phase(); drawOtaScreen();
            }
            else if (!strcmp(buf, "menu"))   { if (ota.busy()) continue;
                                               if (st == ST_DEAUTH) detector.stop();
                                               if (st == ST_CHANNELS) airtime.stop();
                                               if (st == ST_SPECTRUM) spectrumStop();
                                               if (st == ST_SUBSPECTRUM) subStop();
                                               if (st == ST_PROVISION) net.stopProvision();
                                               depth = 0; showMenu(); }
            else { Serial.printf("[cmd] ? '%s'\n", buf); continue; }
            Serial.printf("[cmd] %s -> st=%d\n", buf, (int)st);
        } else if (len < sizeof(buf) - 1) {
            buf[len++] = c;
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    displayInit();
    uiBacklightBegin();              // apply saved screen brightness before anything is drawn
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
    ota.begin(&engine, &net);        // OTA needs the radio (pauses scan) and the connection
    leds.begin();                    // status LEDs under the antennas
    nrf.setTxPower(loadTxPower());    // apply the saved Spectrum TX power (default max)
    nrf.setTxListenSelf(loadTxMode()); // apply the saved TX mode (Verify keeps the waterfall live)
    spTraffic = loadSpView();          // apply the saved spectrum view (occupancy / traffic)
    if (!legalSeen()) { st = ST_LANGPICK; drawLangPick(); }   // first run: language, then the notice
    else showMenu();
}

void loop() {
    // ---- touch (edge-triggered) ----
    uint16_t tx, ty;
    if (touchGet(tx, ty)) {
        if (!touchDown) {
            touchDown = true;
            if (st == ST_LANGPICK) {
                for (int i = 0; i < 2; i++)
                    if (ty >= 120 + i * 48 && ty < 120 + i * 48 + 34) {
                        langPickSel = i; Lang l = i ? Lang::RU : Lang::EN;
                        i18n::set(l); saveLang(l); gotoLegal(true); break;
                    }
            } else if (st == ST_LEGAL) {
                if (ty > 260) { int m = legN - LEG_LINES; if (m < 0) m = 0;   // tap low = scroll on
                                if (legOff < m) { legOff += 4; if (legOff > m) legOff = m; drawLegalScreen(); }
                                else if (legFirstRun && legAccepted) { legalMarkSeen(); legFirstRun = false; depth = 0; showMenu(); }
                                else if (!legFirstRun) showMenu(); }
                else if (ty < 60 && legOff > 0) { legOff -= 4; if (legOff < 0) legOff = 0; drawLegalScreen(); }
            } else if (st == ST_MENU) {
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
            } else if (st == ST_WIFI) {
                if (ty < 28) back();
                else { int i = (ty - UI_LIST_TOP) / UI_ROW_H; int idx = off + i;
                       if (i >= 0 && i < UI_VISIBLE && idx < engine.wifiCount()) { wifiSel = idx; ensureWifiVisible(); openNetOptions(); } }
            } else if (st == ST_OTA) {
                if (ota.phase() == OtaManager::AVAILABLE) ota.startUpdate();
                else if (ota.phase() != OtaManager::DOWNLOADING && ty < 60) back();
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

    // ---- keypad + serial remote ----
    onKey(buttons.poll());
    serialControl();

    // ---- status LEDs: derive "what the radio is doing" from one place, so no
    //      screen transition can forget to update them ----
    leds.set(ota.busy()                            ? StatusLeds::OTA
           : st == ST_PROVISION                    ? StatusLeds::PORTAL
           : st == ST_DEAUTH                       ? StatusLeds::PROMISC
           : (st == ST_WIFI || st == ST_CHANNELS || st == ST_SPECTRUM) ? StatusLeds::WIFI_SCAN
           : st == ST_SUBSPECTRUM                  ? StatusLeds::PROMISC
           : st == ST_BLE                          ? StatusLeds::BLE_SCAN
           : (st == ST_OTA && ota.phase() == OtaManager::FAILED) ? StatusLeds::ERR
                                                   : StatusLeds::IDLE);
    // An antenna emitting noise (spectrum TX) lights its own LED yellow: NRF slot i sits
    // under LED i+1 (LED 0 is the sub-GHz antenna), so shift the slot mask up by one.
    leds.setTx((st == ST_SPECTRUM && nrf.txActive()) ? (uint8_t)(nrf.txSlotMask() << 1) : 0);
    leds.tick();

    // ---- deauth monitor: hop channels + refresh stats ----
    if (st == ST_DEAUTH) {
        detector.loop();
        static uint32_t nextDeauthDraw = 0;
        if (millis() - nextDeauthDraw > 400) { nextDeauthDraw = millis(); deauthRefresh(); }
    }

    // ---- provisioning portal ----
    if (st == ST_PROVISION) {
        net.loopProvision();
        if (net.pendingConnect()) {
            net.stopProvision();     // saves creds + switches to STA (AP drops)
            infoTitle = i18n::tr("Connecting...", "Подключение..."); infoBody = net.savedSsid(); infoNote = ""; infoAction = -1;
            st = ST_INFO; drawInfo();
            net.connect();
            if (net.connected()) ota.startCheck();   // auto-check for updates on connect
            gotoConn();              // land on the connection screen with the fresh status
        }
    }

    // ---- live updates ----
    if (st == ST_WIFI && engine.wifiGen() != seenWifiGen) {
        seenWifiGen = engine.wifiGen();
        ensureWifiVisible();
        drawList(true);
    } else if (st == ST_BLE && engine.bleGen() != seenBleGen) {
        seenBleGen = engine.bleGen();
        int m = engine.bleCount() - UI_VISIBLE; if (m < 0) m = 0; if (off > m) off = m;
        drawList(true);
    } else if (st == ST_OTA && ota.gen() != seenOtaGen) {
        seenOtaGen = ota.gen();
        if ((int)ota.phase() != seenOtaPhase) { seenOtaPhase = (int)ota.phase(); drawOtaScreen(); }
        else otaBar();                       // % change → repaint just the slider (no bg redraw)
    }

    // Channel graphs scroll on a steady tick (cardiograph feel) from real airtime.
    if (st == ST_CHANNELS) {
        airtime.loop();             // hop channels; each is refreshed as the sweep visits it
        static uint32_t nextCh = 0;
        if (millis() - nextCh > 120) {
            nextCh = millis();
            channelSample();
            channelGraphs();        // header/footer untouched — no flicker
        }
    }

    // 2.4GHz spectrum waterfall
    if (st == ST_SPECTRUM) spectrumTick();
    // Sub-GHz spectrum waterfall
    if (st == ST_SUBSPECTRUM) subTick();

    if (millis() > 8000) ota.markHealthy();  // once the UI has clearly been up, confirm this image

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
