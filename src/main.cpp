#include <Arduino.h>
#include <string.h>
#include <WiFi.h>

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
#include "features/ble_scanner/BleScanner.h"
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
#include "features/subghz/SubCfg.h"
#include "features/subghz/RecStore.h"

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
PolitePortal   portal;          // Lab captive-portal demo (own-named AP, consent button)
SubCfg         subcfg;          // Sub-GHz settings captive portal

static void drawNetBadge();      // small "connected" mark in the header (defined below)
static void gotoWifi();          // (re)enter the live Wi-Fi scan
static void ensureWifiVisible(); // keep the selected scan row on screen
static int  drawWrapped(const char* s, int x, int y, int maxw, int lh, int maxlines);  // word-wrap (defined below)
static void openNetOptions();    // RIGHT on a scan row -> per-network options
static void radarStartWifi(const WifiRow& w);   // lock an AP by BSSID → radar finder
static void drawNetDetails();    // details screen for the selected network

// ---- menu tree ----
enum { M_ROOT, M_WIFI, M_BLE, M_SUBGHZ, M_SETTINGS, M_LANG, M_WIFI_ADV, M_LAB, M_DEVICE, M_PORTAL, M_GEN, M_REC };
enum { F_WIFI_SCAN, F_CONN, F_HIDDEN, F_DEAUTH, F_CHANNELS, F_SPECTRUM, F_BLE_SCAN, F_SUBSPECTRUM, F_SUBGHZ_SOON, F_RECAL, F_ABOUT, F_OTA, F_LEGAL, F_LEDS, F_BACKLIGHT, F_TXPOWER, F_NOISEGEN, F_TXMODE, F_PORTAL_CFG, F_POLITE, F_SUBTX, F_SUBPOWER, F_SUBREC, F_SUBCFG, F_REC_PLAY, F_SUBHUNT, F_HUNT24, F_LANG_EN, F_LANG_RU };
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
    {"Freq finder 2.4", "Which 2.4 channel a signal is on", "Частотомер 2.4", "Канал 2.4-сигнала", K_FEAT, F_HUNT24},
    {"Laboratory",    "Experimental — transmits", "Лаборатория", "Эксперименты — эфир",   K_SUB,  M_LAB},
    {"Advanced",      "Deeper Wi-Fi tools",    "Продвинутое",   "Инструменты поглубже",  K_SUB,  M_WIFI_ADV},
};
static const MenuItem WADV_I[] = {
    {"Hidden names",   "Revealed hidden SSIDs",  "Скрытые сети",  "Раскрытые имена",       K_FEAT, F_HIDDEN},
    {"Deauth monitor", "Alarm on deauth bursts", "Детектор атак", "Тревога на отключения", K_FEAT, F_DEAUTH},
    {"TX power",       "TX radiation power", "Мощность TX", "Мощность излучения", K_FEAT, F_TXPOWER},
};
static const MenuItem BLE_I[] = {
    {"BLE Scan", "Devices & trackers nearby", "Скан BLE", "Устройства и трекеры рядом", K_FEAT, F_BLE_SCAN},
};
static const MenuItem SUB_I[] = {
    {"Spectrum", "Sub-GHz waterfall (CC1101)", "Спектр", "Водопад Sub-GHz (CC1101)", K_FEAT, F_SUBSPECTRUM},
    {"Test TX",  "Transmit a test signal",     "Тест-передача", "Тестовый сигнал в эфир", K_FEAT, F_SUBTX},
    {"Rec + replay", "Record + replay your own", "Запись-повтор", "Запись/повтор своего", K_SUB, M_REC},
    {"Freq finder", "Find your signal's freq", "Частотомер", "Найти частоту сигнала", K_FEAT, F_SUBHUNT},
    {"TX power", "Sub-GHz radiation power",    "Мощность TX",   "Мощность излучения",     K_FEAT, F_SUBPOWER},
};
static const MenuItem SET_I[] = {
    {"Wi-Fi connect",   "Status, join, exit",      "Wi-Fi подключение", "Статус, вход, выход",   K_FEAT, F_CONN},
    {"Update",          "Update from GitHub",      "Обновление",        "Обновить с GitHub",     K_FEAT, F_OTA},
    {"Language",        "Interface language",      "Язык",        "Язык интерфейса",       K_SUB,  M_LANG},
    {"Device",          "LEDs, screen, touch",     "Устройство",  "LED, экран, калибровка", K_SUB,  M_DEVICE},
    {"About",           "About ESP32-Leshy",       "О девайсе",   "Об ESP32-Leshy",        K_FEAT, F_ABOUT},
    {"Responsible use", "Legal terms — read it",   "Ответственность", "Правила — прочти",  K_FEAT, F_LEGAL},
};
// Device settings — hardware knobs, split out of the main Settings list.
static const MenuItem DEV_I[] = {
    {"Status LEDs",     "Brightness / off",        "Светодиоды",  "Яркость / выкл",        K_FEAT, F_LEDS},
    {"Screen light",    "Screen brightness",       "Яркость экрана", "Подсветка дисплея",   K_FEAT, F_BACKLIGHT},
    {"Calibrate touch", "Redo screen calibration", "Калибровка",  "Перекалибровать экран", K_FEAT, F_RECAL},
};
// Laboratory — experimental tools that TRANSMIT. Under Wi-Fi (it's a 2.4 GHz lab).
static const MenuItem LAB_I[] = {
    {"Generator",       "Run + TX mode",              "Генератор",          "Запуск и режим",         K_SUB,  M_GEN},
    {"Portal",          "Setup + raise",              "Портал",             "Настроить и поднять",    K_SUB,  M_PORTAL},
};
static const MenuItem GEN_I[] = {
    {"Run",             "Transmit into channels",     "Запуск",             "Передача в каналы",      K_FEAT, F_NOISEGEN},
    {"TX mode",         "Verify / Maximum",           "Режим передачи",     "Проверка / Максимум",    K_FEAT, F_TXMODE},
};
static const MenuItem PORTAL_I[] = {
    {"Setup",           "Name the portal AP",         "Настроить",          "Задать имя точки",       K_FEAT, F_PORTAL_CFG},
    {"Raise",           "Raise it + consent page",    "Поднять",            "Поднять точку + согласие", K_FEAT, F_POLITE},
};
// Rec/Replay umbrella (Sub-GHz): capture-and-name, the saved library, and the tuning portal.
static const MenuItem REC_I[] = {
    {"Record",          "Capture, name, save",        "Запись",             "Захват, имя, сохранить", K_FEAT, F_SUBREC},
    {"Playback",        "Saved captures",             "Воспроизведение",    "Сохранённые записи",     K_FEAT, F_REC_PLAY},
    {"Settings",        "Wait, freq, threshold",      "Настройки",          "Ожидание, частота, порог", K_FEAT, F_SUBCFG},
};
static const MenuItem LANG_I[] = {
    {"English", "", "English", "", K_FEAT, F_LANG_EN},
    {"Русский", "", "Русский", "", K_FEAT, F_LANG_RU},
};
static const Menu MENUS[] = {
    {"ESP32-Leshy", "ESP32-Leshy", ROOT_I, 4},
    {"Wi-Fi",       "Wi-Fi",       WIFI_I, 6},
    {"BLE",         "BLE",         BLE_I,  1},
    {"Sub-GHz",     "Sub-GHz",     SUB_I,  5},
    {"Settings",    "Настройки",   SET_I,  6},
    {"Language",    "Язык",        LANG_I, 2},
    {"Advanced",    "Продвинутое", WADV_I, 3},
    {"Laboratory",  "Лаборатория", LAB_I,  2},
    {"Device",      "Устройство",  DEV_I,  3},
    {"Portal",      "Портал",      PORTAL_I, 2},
    {"Generator",   "Генератор",   GEN_I,  2},
    {"Rec/Replay",  "Запись-повтор", REC_I, 3},
};

// ---- navigation state ----
enum State { ST_MENU, ST_WIFI, ST_BLE, ST_INFO, ST_PROVISION, ST_CONN, ST_HIDDEN, ST_CONFIRM, ST_OPTIONS, ST_OTA, ST_DEAUTH, ST_CHANNELS, ST_SPECTRUM, ST_SUBSPECTRUM, ST_NETINFO, ST_LEGAL, ST_LANGPICK, ST_POLITE, ST_SUBTX, ST_SUBREC, ST_SUBCFG, ST_KEYBOARD, ST_REC_PLAY, ST_SUBHUNT, ST_HUNT24, ST_BLE_RADAR, ST_BLE_INFO, ST_WIFI_RADAR };
static State    st = ST_MENU;
static int      menuStack[6] = { M_ROOT };   // path of open menus (for back)
static int      selStack[6]  = { 0 };        // selection per level
static int      depth = 0;
static int      off = 0;
static int      wifiSel = 0;     // selected row in the Wi-Fi scan
static int      bleSel = 0;      // selected row in the BLE scan (SELECT → radar)
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
    else               { if (full) bleScreen.draw(engine, off, bleSel);  else bleScreen.rows(engine, off, bleSel); }
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
    infoNote  = i18n::tr("Transmit power for the Generator test. Max = loudest, but can wash out the whole waterfall — lower it for a cleaner picture.",
                         "Мощность передачи в тесте Генератора. Максимум — громче, но может засветить весь водопад — снизь для чистой картинки.");
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
    infoNote  = self ? i18n::tr("One antenna keeps listening — you see the injected signal on the waterfall. Best for checking it works.",
                                "Одна антенна слушает — свой сигнал виден на водопаде. Для проверки, что всё работает.")
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

// Lab captive-portal demo: our own named AP asks a visitor to lower their TX power;
// a tap on the page registers here and drops the AP. Own-equipment demo — no
// credentials asked or stored (see PolitePortal).
static int  politePhase = 0;                       // last drawn phase: 0 waiting · 1 done · 2 stopped
static bool portalSetup = false;                   // true = setup (name form) screen; false = raise (consent) screen
static bool portalSaved = false;                   // setup: the name was saved

static void drawPoliteScreen() {
    const uint16_t bg = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xe7, 0xcf, 0x8f);
    const uint16_t green = tft.color565(0x3f, 0xe0, 0x7a);
    uiHeaderRu(portalSetup ? i18n::tr("Portal setup", "Настройка портала")
                           : i18n::tr("Captive portal", "Captive-портал"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("1. Join this Wi-Fi:", "1. Подключись к сети:"), 10, 46);
    tft.setTextColor(gold, bg);
    tft.drawString(portal.ssid(), 10, 70);
    tft.setTextColor(white, bg);
    tft.drawString(portalSetup ? i18n::tr("2. Type the name, save.", "2. Впиши имя точки, сохрани.")
                               : i18n::tr("2. A page opens on the phone.", "2. На телефоне откроется страница."), 10, 104);
    fontBig();
    if (!portal.isRunning()) {                     // auto-stopped after the action (or begin failed)
        tft.setTextColor(green, bg);
        tft.drawString(i18n::tr("Done - AP is off.", "Готово — точка выкл."), 10, 150);
        fontSmall(); tft.setTextColor(white, bg);
        tft.drawString(i18n::tr("Press back.", "Нажми назад."), 10, 186);
    } else if (portalSetup ? portalSaved : portal.consented()) {
        tft.setTextColor(green, bg);
        tft.drawString(portalSetup ? i18n::tr("Name saved!", "Имя сохранено!") : i18n::tr("Consent got!", "Согласие!"), 10, 150);
        fontSmall(); tft.setTextColor(white, bg);
        tft.drawString(i18n::tr("Shutting down...", "Закрываюсь…"), 10, 186);
    } else {
        tft.setTextColor(gold, bg);
        tft.drawString(portalSetup ? i18n::tr("Awaiting name...", "Жду имя…") : i18n::tr("Waiting...", "Ждём гостя…"), 10, 150);
        fontSmall(); tft.setTextColor(white, bg);
        tft.drawString(portalSetup ? i18n::tr("Fill the form on the phone.", "Заполни форму на телефоне.")
                                   : i18n::tr("Tap the button on the page.", "Жми кнопку на странице."), 10, 186);
    }
    uiFooterRu(i18n::tr("◀ back", "◀ назад"));
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
enum OptId { OPT_DEL_HIDDEN, OPT_NET_DETAILS, OPT_NET_RADAR };
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
        case OPT_NET_RADAR:   radarStartWifi(netSel); break;
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
// Beacon TX modes: short RIGHT = static (fixed channels) / follow-caret live; long RIGHT = auto-sweep.
static bool     spSweep   = false;                             // auto-sweep: one carrier marches across the channels
static int      spSweepCh = 1;                                 // current sweep Wi-Fi channel (1..13)
static uint32_t spSweepAt = 0;                                 // sweep step timer
static const int SP_SWEEP_MS = 350;                            // dwell per channel while sweeping
static bool     spRightPending = false, spRightLong = false;   // RIGHT long-press tracking (Lab screen)
static uint32_t spRightAt = 0;
static int      spRightRel = 0;                                // consecutive "released" reads (debounce I2C 0xFF glitches)
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

static void spectrumStop() { spTxOn = false; spSweep = false; spRightPending = false; spRightRel = 0; nrf.end(); }

// Effective TX target: nothing when off; the sweep channel while sweeping; the fixed set
// if any is armed; else the caret channel live (follow-cursor "real-time" mode).
static uint16_t spEffMask() {
    if (!spTxOn) return 0;
    if (spSweep)  return (uint16_t)(1 << spSweepCh);
    if (spTxMask) return spTxMask;
    return (uint16_t)(1 << spCursor);
}
static void spApplyTx() { nrf.setTxWifiMask(spEffMask()); }

// Generator header badge (right side): what channel the noise is actually going into
// right now — the follow caret, the fixed set, or the marching sweep. Amber while
// emitting, grey when off. Redrawn from spDrawAxis(), so it tracks every change.
static void spDrawTxBadge() {
    if (!spLab) return;
    const uint16_t hdr = tft.color565(0x1e, 0x3a, 0x28);
    const uint16_t col = spTxOn ? tft.color565(0xff, 0x9a, 0x3a) : tft.color565(0x8f, 0xa9, 0x8f);
    char b[24];
    if (!spTxOn)        snprintf(b, sizeof(b), "%s", i18n::tr("off", "выкл"));
    else if (spSweep)   snprintf(b, sizeof(b), "%s%d", i18n::tr("sweep ch", "свип к"), spSweepCh);
    else if (spTxMask) {
        int n = 0;
        for (int w = 1; w <= 13; w++) if (spTxMask & (1 << w)) n++;
        if (n <= 4) {
            int p = snprintf(b, sizeof(b), "%s", i18n::tr("ch", "к"));
            bool comma = false;
            for (int w = 1; w <= 13; w++) if (spTxMask & (1 << w)) { p += snprintf(b + p, sizeof(b) - p, "%s%d", comma ? "," : "", w); comma = true; }
        } else snprintf(b, sizeof(b), "%s x%d", i18n::tr("ch", "к"), n);
    }
    else                snprintf(b, sizeof(b), "%s%d", i18n::tr("ch", "к"), spCursor);
    tft.fillRect(150, 2, 88, 24, hdr);          // clear only the badge area, right of the "Генератор" title
    fontSmall();
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(col, hdr);
    tft.drawString(b, 234, 14);
    fontOff();
}

// The channel axis below the plot: a tick + number per Wi-Fi channel (armed ones in
// orange-red), plus the selection caret. Redrawn on any change; touches only the strip
// under the plot, never the live waterfall above it.
static void spDrawAxis() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f), gold = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t armed = tft.color565(0xff, 0x5a, 0x32);
    const uint16_t caret = spTxOn ? armed : tft.color565(0x46, 0xd6, 0xff);   // cyan idle → red while emitting
    const int B = SP_Y + SP_H;                                               // strip top = plot bottom (y=266); footer at y=301
    tft.fillRect(0, B + 1, 240, 34, bg);                                     // clear the whole label strip
    fontOff();                                                               // channel numbers use the built-in font (arg 1); a loaded VLW would override it
    tft.setTextDatum(MC_DATUM);
    for (int w = 1; w <= 13; w++) {
        int sx = spNrfToX(Nrf24Spectrum::wifiCenterNrfCh(w));
        if (sx < 0 || sx >= SP_W) continue;
        int x = SP_X + sx;
        bool major   = (w == 1 || w == 6 || w == 11);
        bool isArmed = spLab && !spSweep && (spTxMask & (1 << w));            // armed set is meaningless during a sweep — hide it there
        uint16_t col = isArmed ? armed : (major ? gold : dim);
        if (spLab && w == spCursor) tft.fillTriangle(x - 3, B + 1, x + 3, B + 1, x, B + 7, caret);   // cursor: caret drops from the plot
        tft.drawFastVLine(x, B + 8, 3, col);
        String s = String(w);
        int ny = B + (w & 1 ? 15 : 24);                                      // odd row higher, even lower
        tft.setTextColor(col, bg);
        tft.drawString(s, x, ny, 1);
        if (isArmed) {
            tft.setTextColor(col);                                          // transparent overstrike, +1px = fake-bold
            tft.drawString(s, x + 1, ny, 1);
            tft.fillTriangle(x - 3, B + 34, x + 3, B + 34, x, B + 29, armed);   // armed: arrow points UP at the channel from below
        }
    }
    spDrawTxBadge();               // keep the header's TX-channel badge in sync with the caret/armed/sweep state
}

static void spDrawFooter() {
    // Passive Spectrum just shows a legend; the Lab generator shows the TX controls.
    // Only glyphs present in the tiny VLW subset (letters, space, ◀ ▶ ▼): ▲▼ move the
    // caret, the middle key (OK) arms the channel, ▶ starts/stops the noise.
    if (!spLab) { uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
                             spTraffic ? i18n::tr("traffic ▶", "трафик ▶") : i18n::tr("occupancy ▶", "занятость ▶")); return; }
    const char* right = spSweep ? (i18n::isRu() ? "СВИП  ▶ стоп"      : "SWEEP  ▶ stop")
                      : spTxOn   ? (i18n::isRu() ? "стоп ▶  держ=свип" : "stop ▶  hold=sweep")
                                 : (i18n::isRu() ? "OK канал  ▶ старт" : "OK chan  ▶ start");
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", right);
}

// SELECT fixes/unfixes the caret channel (a static beacon target). Leaves sweep mode.
static void spToggleArm() {
    spSweep = false;
    spTxMask ^= (uint16_t)(1 << spCursor);
    spApplyTx();
    spDrawAxis();
    spDrawFooter();
}

// Short RIGHT: start/stop the static/follow beacon. With channels fixed it hits those; with
// none fixed the carrier follows the caret live (move ▲▼ and it tracks you — real-time).
static void spToggleTx() {
    spSweep = false;
    spTxOn = !spTxOn;
    spApplyTx();
    spDrawAxis();
    spDrawFooter();
}

// Long RIGHT: start/stop the auto-sweep — one carrier marching across every channel.
static void spSweepToggle() {
    spSweep = !spSweep;
    spTxOn = spSweep;
    if (spSweep) { spSweepCh = 1; spCursor = 1; spSweepAt = millis(); }
    spApplyTx();
    spDrawAxis();
    spDrawFooter();
}

static void drawSpectrumScreen() {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f);
    if (spLab)   // Generator: title only here — spDrawAxis()→spDrawTxBadge() fills the right slot with the live TX channel
        uiHeaderRu(i18n::tr("Generator", "Генератор"), nullptr);
    else         // passive Spectrum: title only — the module count was cryptic and collided with the title
        uiHeaderRu(i18n::tr("2.4GHz Spectrum", "Спектр 2.4ГГц"), nullptr);
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
    if (spSweep && spTxOn && millis() - spSweepAt >= SP_SWEEP_MS) {   // auto-sweep: march the carrier one channel on
        spSweepAt = millis();
        spSweepCh = spSweepCh >= 13 ? 1 : spSweepCh + 1;
        spCursor = spSweepCh;
        spApplyTx();
        spDrawAxis();
    }
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

// ---- Sub-GHz test transmitter (CC1101) ----
// One CC1101 → pure TX, so it can't watch its own signal — verify on an external RX.
// RIGHT cycles the band, the middle key toggles TX; the sub-GHz antenna LED goes yellow.
static const uint8_t CC_PA[]     = { 0xC0, 0x84, 0x60, 0x34, 0x1D };   // PATABLE presets, max→min
static const int8_t  CC_PA_DBM[] = {   10,    5,    0,   -6,  -15 };   // approx dBm (433 MHz)
static const int     CC_PA_N     = sizeof(CC_PA) / sizeof(CC_PA[0]);
static int  subPwrIdx = 0;                          // 0 = max
static bool subTxOn   = false;

static void saveSubPower(int idx) { Preferences p; p.begin("leshy", false); p.putUChar("cc_pwr_i", (uint8_t)idx); p.end(); }
static int  loadSubPower() { Preferences p; p.begin("leshy", true); int v = p.getUChar("cc_pwr_i", 0); p.end(); return (v >= 0 && v < CC_PA_N) ? v : 0; }

// Sub-GHz settings (set via the SubCfg phone portal, saved to NVS, applied by loadSubCfg).
static uint32_t recWaitMs  = 30000;                 // recorder signal-wait timeout
static uint32_t subFreqKHz = 0;                     // exact TX/capture freq override (0 = band centre)
static int      recRepeats = 3;                     // replay repeat count
static int      subCfgPhase = 0;                    // settings-portal screen phase: 0 waiting · 1 saved · 2 stopped

static bool cc1101FreqOk(uint32_t f) {              // the chip only tunes these sub-bands
    return (f >= 300000 && f <= 348000) || (f >= 387000 && f <= 464000) || (f >= 779000 && f <= 928000);
}

// TX/capture frequency: the exact override if set & tunable, else the band centre, else
// 433.92 (the "full 300-928" centre is 614 MHz, inside a CC1101 gap).
static uint32_t subTxFreqKHz() {
    if (subFreqKHz && cc1101FreqOk(subFreqKHz)) return subFreqKHz;
    uint32_t f = Cc1101Spectrum::bandCenterKHz(cc.bandInfo());
    return cc1101FreqOk(f) ? f : 433920;
}

static void loadSubCfg() {                          // read all Sub-GHz settings from NVS and apply
    Preferences p; p.begin("leshy", true);
    recWaitMs  = p.getUInt("rec_wait", 30000);
    subFreqKHz = p.getUInt("sub_freq", 0);
    recRepeats = p.getUChar("rep_n", 3);
    int  thr   = p.getInt("cap_thr", -72);
    bool fsk   = p.getUChar("sub_mod", 0) != 0;
    bool inv   = p.getBool("sub_inv", false);
    p.end();
    if (recWaitMs < 3000 || recWaitMs > 300000) recWaitMs = 30000;   // guard corrupt/legacy NVS
    if (recRepeats < 1 || recRepeats > 20) recRepeats = 3;
    if (thr < -110 || thr > -30) thr = -72;
    cc.setCaptureThreshold(thr);
    cc.setModulation(fsk);
    cc.setInvert(inv);
}

static void subTxApply() {                          // (re)tune TX to a valid frequency at the set power
    cc.setTxPower(CC_PA[subPwrIdx]);
    cc.beginTx(subTxFreqKHz());
}

static void drawSubTxScreen() {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f), red = tft.color565(0xff, 0x5a, 0x32);
    const Cc1101Spectrum::Band& b = cc.bandInfo();
    uint32_t fk = subTxFreqKHz();                   // actual TX freq (band centre, or 433.92 for the "full" band)
    uiHeaderRu(i18n::tr("Sub-GHz TX", "Тест-передача"), "CC1101");
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall();
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Band:", "Диапазон:"), 10, 50);
    tft.setTextColor(gold, bg);  tft.drawString(i18n::isRu() ? b.ru : b.en, 96, 50);
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Freq:", "Частота:"), 10, 80);
    char fs[24]; snprintf(fs, sizeof(fs), "%lu.%02lu MHz", (unsigned long)(fk / 1000), (unsigned long)((fk % 1000) / 10));
    tft.setTextColor(gold, bg);  tft.drawString(fs, 96, 80);
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Power:", "Мощность:"), 10, 110);
    char ps[16]; snprintf(ps, sizeof(ps), "%d dBm", CC_PA_DBM[subPwrIdx]);
    tft.setTextColor(gold, bg);  tft.drawString(ps, 96, 110);
    fontBig();
    if (subTxOn) { tft.setTextColor(red, bg);  tft.drawString(i18n::tr("TRANSMITTING", "ПЕРЕДАЮ"), 10, 152); }
    else         { tft.setTextColor(gold, bg); tft.drawString(i18n::tr("Ready", "Готов"), 10, 152); }
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("Verify on external RX.", "Проверяй внешним RX."), 10, 194);
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
               subTxOn ? (i18n::isRu() ? "OK стоп  ▶ бэнд" : "OK stop  ▶ band")
                       : (i18n::isRu() ? "OK старт  ▶ бэнд" : "OK start  ▶ band"));
    fontOff();
}

static uint8_t subPowerCycle() {                    // max → … → min → wrap; persists; applied to the chip
    subPwrIdx = (subPwrIdx + 1) % CC_PA_N;
    cc.setTxPower(CC_PA[subPwrIdx]);
    saveSubPower(subPwrIdx);
    return CC_PA[subPwrIdx];
}

static void drawSubPowerInfo() {
    infoTitle = i18n::tr("Sub-GHz TX power", "Мощность Sub-GHz");
    infoBody  = String((int)CC_PA_DBM[subPwrIdx]) + i18n::tr(" dBm", " дБм") + (subPwrIdx == 0 ? i18n::tr(" (max)", " (макс)") : "");
    infoNote  = i18n::tr("Approx power of the Sub-GHz test signal (CC1101, ~10 mW max). Own equipment only.",
                         "Примерная мощность тестового сигнала Sub-GHz (CC1101, макс ~10 мВт). Только своё железо.");
    infoAction = F_SUBPOWER; st = ST_INFO; drawInfo();
}

// ---- Sub-GHz RAW recorder (CC1101) — own-equipment record + replay ----
static uint16_t recBuf[512];                        // captured OOK pulse durations (us)
static int      recN = 0;                            // pulses in the last capture (0 = empty)
static uint32_t recFreqKHz = 0;                      // frequency it was captured on (replay uses it)

static void drawSubRecScreen(const char* status = nullptr) {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f), green = tft.color565(0x3f, 0xe0, 0x7a);
    const Cc1101Spectrum::Band& b = cc.bandInfo();
    uint32_t fk = subTxFreqKHz();
    uiHeaderRu(i18n::tr("Rec/Replay", "Запись-повтор"), "CC1101");
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall();
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Band:", "Диапазон:"), 10, 50);
    tft.setTextColor(gold, bg);  tft.drawString(i18n::isRu() ? b.ru : b.en, 96, 50);
    tft.setTextColor(white, bg); tft.drawString(i18n::tr("Freq:", "Частота:"), 10, 78);
    char fs[24]; snprintf(fs, sizeof(fs), "%lu.%02lu MHz", (unsigned long)(fk / 1000), (unsigned long)((fk % 1000) / 10));
    tft.setTextColor(gold, bg);  tft.drawString(fs, 96, 78);
    fontBig();
    if (status) { tft.setTextColor(gold, bg); tft.drawString(status, 10, 118); }
    else if (recN > 0) { char cs[28]; snprintf(cs, sizeof(cs), "%s%d", i18n::tr("Saved: ", "Записано: "), recN); tft.setTextColor(green, bg); tft.drawString(cs, 10, 118); }
    else { tft.setTextColor(white, bg); tft.drawString(i18n::tr("Empty", "Пусто"), 10, 118); }
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("Own equipment only.", "Только своё железо."), 10, 152);
    tft.drawString(i18n::tr("OK record", "OK запись"), 10, 174);
    tft.drawString(i18n::tr("up replay", "вверх повтор"), 10, 196);
    tft.drawString(i18n::tr("down band", "вниз бэнд"), 10, 218);
    if (recN > 0) tft.drawString(i18n::tr("right save", "вправо сохранить"), 10, 240);   // only when there's a capture to save
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", recN > 0 ? (i18n::isRu() ? "▶ сохранить" : "▶ save") : nullptr);
    fontOff();
}

static void subRecord() {
    loadSubCfg();                                       // apply current settings — playback may have changed cc's modulation
    char msg[24]; snprintf(msg, sizeof(msg), "%s%lus", i18n::tr("Listening ", "Слушаю "), (unsigned long)(recWaitMs / 1000));
    drawSubRecScreen(msg);
    recFreqKHz = subTxFreqKHz();
    cc.beginCapture(recFreqKHz);
    recN = cc.captureRaw(recBuf, 512, recWaitMs);
    drawSubRecScreen();
}

static void subReplay() {
    if (recN <= 0) return;
    drawSubRecScreen(i18n::tr("Replaying...", "Повтор…"));
    cc.setTxPower(CC_PA[subPwrIdx]);
    for (int r = 0; r < recRepeats; r++) {          // remotes send the frame repeated — replay N times
        cc.replayRaw(recBuf, recN, recFreqKHz);
        delay(20);
    }
    drawSubRecScreen();
}

// ---- on-screen keyboard: name a capture before saving it to flash ----
// The VLW fonts carry the full printable ASCII, so a plain alphanumeric grid renders fine.
static const char* KB_ROWS[] = { "ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ0123", "456789-_.," };
static const char* KB_SPEC[] = { "SPC", "DEL", "OK", "ESC" };
static const int KB_NROW = 4, KB_NCOL = 10, KB_NSPEC = 4;
static const int KB_X0 = 6, KB_CW = 23, KB_CH = 30, KB_Y0 = 80, KB_RSTEP = 34;
static const int KB_SY = KB_Y0 + KB_NROW * KB_RSTEP, KB_SX = 6, KB_SW = 56, KB_SSTEP = 58;

static char  kbBuf[RecStore::NAME_LEN + 1] = {0};
static int   kbLen = 0, kbRow = 0, kbCol = 0;

static int kbRowCols(int row) { return row < KB_NROW ? KB_NCOL : KB_NSPEC; }

static void kbCellRect(int row, int col, int& x, int& y, int& w, int& h) {
    if (row < KB_NROW) { x = KB_X0 + col * KB_CW;   y = KB_Y0 + row * KB_RSTEP; w = KB_CW - 2; h = KB_CH; }
    else               { x = KB_SX + col * KB_SSTEP; y = KB_SY;                 w = KB_SW;     h = KB_CH; }
}

// Assumes a smooth font is already loaded (caller manages fontSmall/fontOff).
static void drawKbCell(int row, int col, bool sel) {
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f);
    int x, y, w, h; kbCellRect(row, col, x, y, w, h);
    uint16_t box = sel ? tft.color565(0x2c, 0x5a, 0x2c) : tft.color565(0x1b, 0x27, 0x1b);
    tft.fillRoundRect(x, y, w, h, 5, box);
    char lbl[4];
    if (row < KB_NROW) { lbl[0] = KB_ROWS[row][col]; lbl[1] = 0; }
    else               { strncpy(lbl, KB_SPEC[col], sizeof(lbl) - 1); lbl[sizeof(lbl) - 1] = 0; }
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(sel ? gold : white, box);
    tft.drawString(lbl, x + w / 2, y + h / 2);
}

static void drawKbName() {
    const uint16_t bg = uiBg(), gold = tft.color565(0xe7, 0xcf, 0x8f);
    tft.fillRect(0, 44, 240, 30, bg);
    fontBig();
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(gold, bg);
    char shown[RecStore::NAME_LEN + 2];
    snprintf(shown, sizeof(shown), "%s_", kbBuf);       // trailing caret
    tft.drawString(shown, 10, 48);
    fontOff();
}

static void drawKeyboard(bool full) {
    if (full) { uiHeaderRu(i18n::tr("Name", "Имя записи")); tft.fillRect(0, 28, 240, 320 - 28, uiBg()); }
    drawKbName();
    fontSmall();
    for (int r = 0; r <= KB_NROW; r++)
        for (int c = 0; c < kbRowCols(r); c++) drawKbCell(r, c, r == kbRow && c == kbCol);
    fontOff();
    uiFooterRu(i18n::isRu() ? "◀▶▼▲ выбор" : "◀▶▼▲ move", i18n::isRu() ? "OK ввод" : "OK pick");
}

static void kbRepaintCursor(int pr, int pc) {
    if (pr == kbRow && pc == kbCol) return;
    fontSmall(); drawKbCell(pr, pc, false); drawKbCell(kbRow, kbCol, true); fontOff();
}

static void kbCommit() {
    if (kbLen == 0) return;                             // a name is required
    if (!RecStore::exists(kbBuf) && RecStore::count() >= RecStore::MAX_RECS) {
        st = ST_SUBREC; drawSubRecScreen(i18n::tr("Full (64 max)", "Заполнено (64)")); return;
    }
    bool ok = RecStore::save(kbBuf, recBuf, recN, recFreqKHz, cc.modulation(), cc.inverted(), cc.startLevel());
    st = ST_SUBREC;
    if (ok) { char m[RecStore::NAME_LEN + 24]; snprintf(m, sizeof(m), "%s%s", i18n::tr("Saved: ", "Сохранено: "), kbBuf); drawSubRecScreen(m); }
    else    drawSubRecScreen(i18n::tr("Save error", "Ошибка ФС"));
}

static void kbSelect() {
    if (kbRow < KB_NROW) {                              // a character key
        if (kbLen < RecStore::NAME_LEN) { kbBuf[kbLen++] = KB_ROWS[kbRow][kbCol]; kbBuf[kbLen] = 0; drawKbName(); }
        return;
    }
    switch (kbCol) {                                    // special row
        case 0: if (kbLen < RecStore::NAME_LEN) { kbBuf[kbLen++] = ' '; kbBuf[kbLen] = 0; drawKbName(); } break;  // SPC
        case 1: if (kbLen > 0) { kbBuf[--kbLen] = 0; drawKbName(); } break;                                       // DEL
        case 2: kbCommit(); break;                                                                                // OK
        case 3: st = ST_SUBREC; drawSubRecScreen(); break;                                                        // ESC (discard)
    }
}

// ---- playback: browse + replay + delete the saved library ----
static const int RP_TOP = 42, RP_ROW_H = 30, RP_VISIBLE = 8;
static String recNames[RecStore::MAX_RECS];
static int    recCount = 0, recSel = 0, recOff = 0;
static bool   recDelArm = false;                        // delete confirmation armed

static void clampRecList() {
    if (recSel < recOff) recOff = recSel;
    if (recSel >= recOff + RP_VISIBLE) recOff = recSel - RP_VISIBLE + 1;
    if (recOff > recCount - RP_VISIBLE) recOff = recCount - RP_VISIBLE;   // pull the window up when the list shrank
    if (recOff < 0) recOff = 0;
}

static void drawRecPlayRow(int slot) {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f);
    int idx = recOff + slot, y = RP_TOP + slot * RP_ROW_H;
    tft.fillRect(0, y, 240, RP_ROW_H, bg);
    if (idx >= recCount) return;
    bool sel = (idx == recSel);
    uint16_t rowbg = sel ? tft.color565(0x22, 0x33, 0x22) : bg;
    if (sel) tft.fillRoundRect(6, y, 228, RP_ROW_H - 4, 6, rowbg);
    fontSmall();
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(sel ? gold : white, rowbg);
    tft.drawString(recNames[idx], 14, y + 8);
    fontOff();
}

static void drawRecList() { for (int s = 0; s < RP_VISIBLE; s++) drawRecPlayRow(s); }

static void drawRecPlayScreen(const char* status = nullptr) {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f);
    uiHeaderRu(i18n::tr("Playback", "Воспроизведение"), "CC1101");
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    if (recCount == 0) {
        fontBig(); tft.setTextDatum(TL_DATUM); tft.setTextColor(white, bg);
        tft.drawString(i18n::tr("Empty", "Пусто"), 10, 60);
        fontSmall(); tft.drawString(i18n::tr("Record a signal first", "Сначала запиши сигнал"), 10, 100);
        fontOff();
    } else {
        drawRecList();
    }
    if (status) { fontSmall(); tft.setTextDatum(TL_DATUM); tft.setTextColor(gold, bg); tft.drawString(status, 10, 286); fontOff(); }
    if (recDelArm) uiFooterRu(i18n::isRu() ? "◀ отмена"  : "◀ cancel", i18n::isRu() ? "OK удалить" : "OK delete");
    else           uiFooterRu(i18n::isRu() ? "◀ назад"   : "◀ back",   i18n::isRu() ? "OK повтор ▶ уд" : "OK play ▶ del");
}

static void recPlaySelected() {
    if (recSel < 0 || recSel >= recCount) return;
    int n, sl; uint32_t fk; bool fsk, inv;
    if (!RecStore::load(recNames[recSel].c_str(), recBuf, 512, n, fk, fsk, inv, sl)) { drawRecPlayScreen(i18n::tr("Load error", "Ошибка чтения")); return; }
    recN = n; recFreqKHz = fk;
    cc.setModulation(fsk); cc.setInvert(inv); cc.setStartLevel(sl);   // reproduce this slot's exact settings
    cc.setTxPower(CC_PA[subPwrIdx]);
    drawRecPlayScreen(i18n::tr("Replaying...", "Повтор…"));
    for (int r = 0; r < recRepeats; r++) { cc.replayRaw(recBuf, recN, recFreqKHz); delay(20); }
    loadSubCfg();                                       // restore the user's live settings for the next capture
    drawRecPlayScreen(i18n::tr("Done", "Готово"));
}

static void recDeleteSelected() {
    recDelArm = false;
    if (recSel >= 0 && recSel < recCount) RecStore::remove(recNames[recSel].c_str());
    recCount = RecStore::list(recNames, RecStore::MAX_RECS);
    if (recSel >= recCount) recSel = recCount > 0 ? recCount - 1 : 0;
    clampRecList();
    drawRecPlayScreen(i18n::tr("Deleted", "Удалено"));
}

// ---- Sub-GHz frequency hunter: find the frequency of your own tag/remote (pure RX) ----
struct HuntWin { uint32_t lo, hi; };
static const HuntWin HUNT_WINS[] = { {300000, 348000}, {387000, 464000}, {779000, 928000} };   // CC1101 tunable windows
static const int      HUNT_NWIN = sizeof(HUNT_WINS) / sizeof(HUNT_WINS[0]);
static const uint32_t HUNT_STEP = 250;              // kHz coarse grid (RX bandwidth ~200 kHz)
static const int      HUNT_RISE = 18;               // dB a bin must rise above its calibrated baseline to count
static const int      HUNT_MAXBINS = 1200;          // baseline array cap (actual ~1099)
static const int      HUNT_CALIB_PASSES = 2;        // baseline = per-bin MIN over N passes → a stray press can't poison it

// The hunter draws a live bar graph of how far each frequency RISES above a calibrated baseline.
// CALIB records the baseline (ambient + the chip's own crystal-harmonic birdies, e.g. 26 MHz*12 =
// 312 MHz) as the per-bin MIN over two passes; HUNT then max-holds the rise per bin, so a pressed
// tag builds a visible spike while constant spurs stay flat. You read the frequency off the peak —
// far more honest than an auto-pick that flip-flops on overload spurs and receiver harmonics.
enum HuntPhase { HP_CALIB, HP_HUNT };
static HuntPhase huntPhase = HP_CALIB;
static int8_t   huntBase[HUNT_MAXBINS];             // per-bin baseline RSSI (dBm)
static int8_t   huntRaw[HUNT_MAXBINS];              // this pass's raw rise above baseline (dB)
static int8_t   huntHold[HUNT_MAXBINS];             // per-bin max-held DRIFT-CORRECTED rise (dB), slow decay
static int      huntN = 0;                          // active bin count
static int      huntBin = 0;                        // sweep cursor (flat bin index)
static int      huntCalibPass = 0;                  // which baseline pass we're on
static bool     huntCalibrated = false;
static bool     huntLowGain = false;                // -18 dB input attenuation (near-field, anti-overload)
static uint32_t huntLastDraw = 0;

static int huntBinCount() {
    int n = 0;
    for (int w = 0; w < HUNT_NWIN; w++) n += (int)((HUNT_WINS[w].hi - HUNT_WINS[w].lo) / HUNT_STEP) + 1;
    return n;
}
static uint32_t huntBinFreq(int idx) {
    for (int w = 0; w < HUNT_NWIN; w++) {
        int n = (int)((HUNT_WINS[w].hi - HUNT_WINS[w].lo) / HUNT_STEP) + 1;
        if (idx < n) return HUNT_WINS[w].lo + (uint32_t)idx * HUNT_STEP;
        idx -= n;
    }
    return HUNT_WINS[HUNT_NWIN - 1].hi;
}
static int huntFreqBin(uint32_t f) {                // flat bin index nearest a frequency (-1 if in a gap)
    int base = 0;
    for (int w = 0; w < HUNT_NWIN; w++) {
        int n = (int)((HUNT_WINS[w].hi - HUNT_WINS[w].lo) / HUNT_STEP) + 1;
        if (f >= HUNT_WINS[w].lo && f <= HUNT_WINS[w].hi) return base + (int)((f - HUNT_WINS[w].lo + HUNT_STEP / 2) / HUNT_STEP);
        base += n;
    }
    return -1;
}

static const char* huntGuess(uint32_t k) {          // ISM/SRD band a real remote/tag would use (range-based)
    if (k >= 314000 && k <= 316000) return "315";
    if (k >= 386000 && k <= 392000) return "390";
    if (k >= 417000 && k <= 419000) return "418";
    if (k >= 433050 && k <= 434790) return "433 ISM";
    if (k >= 863000 && k <= 870000) return "868 ISM";
    if (k >= 902000 && k <= 928000) return "915 ISM";
    return "";
}

static bool huntIsSpur(uint32_t f) {                // near a crystal harmonic: 26 MHz (CC1101) or 40 MHz (ESP32)
    const uint32_t FX[] = { 26000, 40000 };
    for (uint32_t fx : FX) {
        uint32_t n = (f + fx / 2) / fx;
        uint32_t d = f > n * fx ? f - n * fx : n * fx - f;
        if (d <= 500) return true;
    }
    return false;
}

static void huntReset() {                           // (re)start with a fresh baseline calibration
    huntN = huntBinCount(); if (huntN > HUNT_MAXBINS) huntN = HUNT_MAXBINS;
    huntPhase = HP_CALIB; huntBin = 0; huntCalibPass = 0; huntCalibrated = false;
    for (int b = 0; b < huntN; b++) huntHold[b] = 0;
}

static void drawHuntChrome() {
    uiHeaderRu(i18n::tr("Freq finder", "Частотомер"), "CC1101");
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::isRu() ? "▶ калибровать" : "▶ recal");
}

// Live readout (peak) + a rise-vs-frequency bar graph. You read the answer off the tall clean spike.
static const int HG_TOP = 120, HG_BOT = 250, HG_FS = 45;   // graph box (px) + full-scale dB
static void drawHuntGraph() {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f),
                   green = tft.color565(0x3f, 0xe0, 0x7a), grayc = tft.color565(0x80, 0x88, 0x80),
                   dim = tft.color565(0x2c, 0x40, 0x30), axis = tft.color565(0x40, 0x50, 0x44);
    int peakBin = -1, peakRise = 0;                 // tallest held bin
    for (int b = 0; b < huntN; b++) if (huntHold[b] > peakRise) { peakRise = huntHold[b]; peakBin = b; }
    uint32_t peakKHz = peakBin >= 0 ? huntBinFreq(peakBin) : 0;

    // ---- readout ----
    tft.fillRect(0, 40, 240, HG_TOP - 44, bg);
    tft.setTextDatum(TL_DATUM);
    fontBig();
    if (!huntCalibrated) {
        tft.setTextColor(grayc, bg); tft.drawString(i18n::tr("calibrating...", "калибровка…"), 10, 46);
    } else if (peakRise >= HUNT_RISE && peakKHz) {
        char fs[16]; snprintf(fs, sizeof(fs), "%lu.%02lu", (unsigned long)(peakKHz / 1000), (unsigned long)((peakKHz % 1000) / 10));
        tft.setTextColor(green, bg); tft.drawString(fs, 10, 46);
        fontSmall(); tft.setTextColor(white, bg); tft.drawString(i18n::tr("MHz", "МГц"), 150, 62);
        const char* g = huntGuess(peakKHz);
        if (*g) { tft.setTextColor(gold, bg); tft.drawString(g, 182, 62); }
    } else {
        tft.setTextColor(grayc, bg); tft.drawString(i18n::tr("press the tag", "жми метку"), 10, 46);
    }
    fontSmall(); tft.setTextColor(white, bg);
    char l1[48];
    if (!huntCalibrated)            snprintf(l1, sizeof(l1), "%s", i18n::tr("don't press - measuring floor", "не жми — меряю фон"));
    else if (peakRise >= HUNT_RISE) snprintf(l1, sizeof(l1), "%s+%d dB", i18n::tr("peak rise ", "подъём пика "), peakRise);
    else                            snprintf(l1, sizeof(l1), "%s", i18n::tr("hold near antenna, press", "держи у антенны, жми"));
    tft.drawString(l1, 10, 96);
    if (huntLowGain) { tft.setTextColor(gold, bg); tft.drawString("-18 dB", 150, 46); }   // near-field attenuation on (OK toggles)
    fontOff();

    // ---- graph ----
    tft.fillRect(0, HG_TOP, 240, HG_BOT - HG_TOP + 14, bg);
    tft.drawFastHLine(0, HG_BOT, 240, axis);
    fontTiny(); tft.setTextDatum(TC_DATUM); tft.setTextColor(grayc, bg);   // ISM band ticks
    struct Tk { uint32_t f; const char* n; };
    static const Tk TKS[] = { {315000, "315"}, {433920, "433"}, {868350, "868"}, {915000, "915"} };
    for (const Tk& t : TKS) {
        int b = huntFreqBin(t.f); if (b < 0 || b >= huntN) continue;
        int x = b * 240 / huntN;
        tft.drawFastVLine(x, HG_BOT + 1, 3, axis);
        tft.drawString(t.n, x, HG_BOT + 4);
    }
    fontOff();
    for (int x = 0; x < 240; x++) {                 // bars: one column per screen x, max over its bins
        int b0 = x * huntN / 240, b1 = (x + 1) * huntN / 240; if (b1 <= b0) b1 = b0 + 1;
        int h = 0;
        for (int b = b0; b < b1 && b < huntN; b++) if (huntHold[b] > h) h = huntHold[b];
        int px = h * (HG_BOT - HG_TOP) / HG_FS; if (px > HG_BOT - HG_TOP) px = HG_BOT - HG_TOP;
        if (px > 0) tft.drawFastVLine(x, HG_BOT - px, px,
                        (peakBin >= b0 && peakBin < b1) ? gold : (h >= HUNT_RISE ? green : dim));
    }
}

static void huntTick() {
    const int BATCH = 16;                               // bounded work per loop() so buttons stay responsive
    if (huntPhase == HP_CALIB) {
        for (int i = 0; i < BATCH && huntBin < huntN; i++) {
            int dbm = cc.rssiAt(huntBinFreq(huntBin));
            int8_t v = (int8_t)(dbm < -128 ? -128 : (dbm > 0 ? 0 : dbm));
            huntBase[huntBin] = (huntCalibPass == 0 || v < huntBase[huntBin]) ? v : huntBase[huntBin];   // per-bin MIN across passes
            huntBin++;
        }
        if (huntBin >= huntN) {
            if (++huntCalibPass < HUNT_CALIB_PASSES) huntBin = 0;       // one more baseline pass (min rejects a stray press)
            else { huntCalibrated = true; huntPhase = HP_HUNT; huntBin = 0; }
        }
    } else {                                            // HP_HUNT — sweep raw rise, then drift-correct + max-hold
        for (int i = 0; i < BATCH && huntBin < huntN; i++) {
            uint32_t f = huntBinFreq(huntBin);
            if (huntIsSpur(f)) { huntRaw[huntBin] = 0; huntBin++; continue; }   // skip the chip's own crystal harmonics
            int rise = cc.rssiAt(f) - huntBase[huntBin];
            huntRaw[huntBin] = (int8_t)(rise < -120 ? -120 : (rise > 120 ? 120 : rise));
            huntBin++;
        }
        if (huntBin >= huntN) {                         // pass complete
            long sum = 0;                               // pass mean = global AGC/thermal drift; subtract it so only LOCAL peaks survive
            for (int b = 0; b < huntN; b++) sum += huntRaw[b];
            int mean = huntN ? (int)(sum / huntN) : 0;
            for (int b = 0; b < huntN; b++) {
                int adj = huntRaw[b] - mean; if (adj < 0) adj = 0;               // this bin's excess over the typical bin
                int dec = huntHold[b] - 3; if (dec < 0) dec = 0;                 // decay old spikes
                huntHold[b] = (int8_t)(adj > dec ? (adj > 120 ? 120 : adj) : dec);
            }
            huntBin = 0;
        }
    }
    if (millis() - huntLastDraw > 250) { huntLastDraw = millis(); drawHuntGraph(); }
}

// ---- 2.4 GHz frequency finder — same idea on the NRF24 (which channel lights up) ----
// The NRF24 gives only a 1-bit RPD per channel, so the "level" is a HIT-RATE: accumulate
// the RPD over H24_K sweeps → 0..K per channel. Baseline (min over 2 passes) captures the
// constant Wi-Fi/BT floor; a pressed tag/remote raises its channel's hit-rate above it.
static const int H24_N    = Nrf24Spectrum::CHANNELS;   // 126 channels, 2400 + ch MHz
static const int H24_K    = 48;                        // sweeps accumulated per pass
static const int H24_RISE = 8;                         // hit-rate rise above baseline to count as a signal
static const int H24_FS   = 36;                        // graph full-scale
enum Hunt24Phase { H24_CALIB, H24_HUNT };
static Hunt24Phase h24Phase = H24_CALIB;
static int8_t   h24Base[H24_N], h24Raw[H24_N], h24Hold[H24_N];
static int      h24Acc[H24_N];                         // this pass's per-channel hit accumulator
static int      h24Sweeps = 0, h24CalibPass = 0;
static bool     h24Calibrated = false;
static uint32_t h24LastDraw = 0;

static const char* hunt24Guess(int ch) {               // nearest Wi-Fi channel a peak overlaps
    static char buf[12];
    int w = (ch - 12 + 2) / 5 + 1;                     // Wi-Fi centres at nRF 12,17,22,... = 12+(w-1)*5
    if (w >= 1 && w <= 13 && abs(ch - (12 + (w - 1) * 5)) <= 6) { snprintf(buf, sizeof(buf), "Wi-Fi %d", w); return buf; }
    return "";
}

static void hunt24Reset() {
    h24Phase = H24_CALIB; h24CalibPass = 0; h24Calibrated = false; h24Sweeps = 0;
    for (int c = 0; c < H24_N; c++) { h24Acc[c] = 0; h24Hold[c] = 0; }
}

static void drawHunt24Chrome() {
    uiHeaderRu(i18n::tr("2.4 finder", "Частотомер 2.4"), "nRF24");
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::isRu() ? "▶ калибровать" : "▶ recal");
}

static void drawHunt24Graph() {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f),
                   green = tft.color565(0x3f, 0xe0, 0x7a), grayc = tft.color565(0x80, 0x88, 0x80),
                   dim = tft.color565(0x2c, 0x40, 0x30), axis = tft.color565(0x40, 0x50, 0x44);
    int peakCh = -1, peakRise = 0;
    for (int c = 0; c < H24_N; c++) if (h24Hold[c] > peakRise) { peakRise = h24Hold[c]; peakCh = c; }

    tft.fillRect(0, 40, 240, HG_TOP - 44, bg);          // reuse the sub-GHz graph box geometry (HG_TOP/HG_BOT)
    tft.setTextDatum(TL_DATUM);
    fontBig();
    if (!h24Calibrated) {
        tft.setTextColor(grayc, bg); tft.drawString(i18n::tr("calibrating...", "калибровка…"), 10, 46);
    } else if (peakRise >= H24_RISE && peakCh >= 0) {
        char fs[16]; snprintf(fs, sizeof(fs), "%d", 2400 + peakCh);
        tft.setTextColor(green, bg); tft.drawString(fs, 10, 46);
        fontSmall(); tft.setTextColor(white, bg); tft.drawString(i18n::tr("MHz", "МГц"), 120, 62);
        const char* g = hunt24Guess(peakCh);
        if (*g) { tft.setTextColor(gold, bg); tft.drawString(g, 160, 62); }
    } else {
        tft.setTextColor(grayc, bg); tft.drawString(i18n::tr("press the tag", "жми метку"), 10, 46);
    }
    fontSmall(); tft.setTextColor(white, bg);
    char l1[48];
    if (!h24Calibrated)            snprintf(l1, sizeof(l1), "%s", i18n::tr("don't press - measuring floor", "не жми — меряю фон"));
    else if (peakRise >= H24_RISE) snprintf(l1, sizeof(l1), "%s+%d", i18n::tr("peak rise ", "подъём пика "), peakRise);
    else                           snprintf(l1, sizeof(l1), "%s", i18n::tr("hold near antennas, press", "держи у антенн, жми"));
    tft.drawString(l1, 10, 96);
    fontOff();

    tft.fillRect(0, HG_TOP, 240, HG_BOT - HG_TOP + 14, bg);
    tft.drawFastHLine(0, HG_BOT, 240, axis);
    fontTiny(); tft.setTextDatum(TC_DATUM); tft.setTextColor(grayc, bg);   // Wi-Fi 1/6/11 landmarks
    const int WCH[] = { 1, 6, 11 };
    for (int wi = 0; wi < 3; wi++) {
        int ch = 12 + (WCH[wi] - 1) * 5, x = ch * 240 / H24_N;
        tft.drawFastVLine(x, HG_BOT + 1, 3, axis);
        char b[4]; snprintf(b, sizeof(b), "%d", WCH[wi]); tft.drawString(b, x, HG_BOT + 4);
    }
    fontOff();
    for (int c = 0; c < H24_N; c++) {                   // one bar per channel
        int x0 = c * 240 / H24_N, x1 = (c + 1) * 240 / H24_N; if (x1 <= x0) x1 = x0 + 1;
        int px = h24Hold[c] * (HG_BOT - HG_TOP) / H24_FS; if (px > HG_BOT - HG_TOP) px = HG_BOT - HG_TOP;
        if (px > 0) tft.fillRect(x0, HG_BOT - px, x1 - x0, px, c == peakCh ? gold : (h24Hold[c] >= H24_RISE ? green : dim));
    }
}

static void hunt24Tick() {
    uint8_t sw[H24_N];
    for (int s = 0; s < 2 && h24Sweeps < H24_K; s++) {  // accumulate a couple of RPD sweeps per loop
        nrf.sweep(sw);
        for (int c = 0; c < H24_N; c++) h24Acc[c] += (sw[c] & 1);
        h24Sweeps++;
    }
    if (h24Sweeps >= H24_K) {                           // pass complete → h24Acc[c] = hit-rate 0..K
        if (h24Phase == H24_CALIB) {
            for (int c = 0; c < H24_N; c++) {
                int8_t v = (int8_t)h24Acc[c];
                h24Base[c] = (h24CalibPass == 0 || v < h24Base[c]) ? v : h24Base[c];   // per-channel MIN
            }
            if (++h24CalibPass >= HUNT_CALIB_PASSES) { h24Calibrated = true; h24Phase = H24_HUNT; }
        } else {
            long sum = 0;
            for (int c = 0; c < H24_N; c++) { h24Raw[c] = (int8_t)(h24Acc[c] - h24Base[c]); sum += h24Raw[c]; }
            int mean = (int)(sum / H24_N);              // subtract the pass mean (drift/overall-busy) → local peaks survive
            for (int c = 0; c < H24_N; c++) {
                int adj = h24Raw[c] - mean; if (adj < 0) adj = 0;
                int dec = h24Hold[c] - 2; if (dec < 0) dec = 0;
                h24Hold[c] = (int8_t)(adj > dec ? adj : dec);
            }
        }
        for (int c = 0; c < H24_N; c++) h24Acc[c] = 0;
        h24Sweeps = 0;
    }
    if (millis() - h24LastDraw > 250) { h24LastDraw = millis(); drawHunt24Graph(); }
}

static void drawSubCfgScreen() {
    const uint16_t bg = uiBg(), white = tft.color565(0xe8, 0xe8, 0xe0), gold = tft.color565(0xe7, 0xcf, 0x8f);
    uiHeaderRu(i18n::tr("Sub-GHz setup", "Настройки Sub-GHz"));
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    tft.setTextDatum(TL_DATUM);
    fontSmall(); tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("1. Join this Wi-Fi:", "1. Подключись к сети:"), 10, 50);
    tft.setTextColor(gold, bg);  tft.drawString(SubCfg::apName(), 10, 74);
    tft.setTextColor(white, bg);
    tft.drawString(i18n::tr("2. Set the fields, save.", "2. Задай поля, сохрани."), 10, 108);
    fontBig();
    if (!subcfg.isRunning()) { tft.setTextColor(tft.color565(0x3f, 0xe0, 0x7a), bg); tft.drawString(i18n::tr("Saved.", "Сохранено."), 10, 150); }
    else if (subcfg.saved()) { tft.setTextColor(tft.color565(0x3f, 0xe0, 0x7a), bg); tft.drawString(i18n::tr("Got it!", "Принял!"), 10, 150); }
    else { tft.setTextColor(gold, bg); tft.drawString(i18n::tr("Waiting...", "Жду…"), 10, 150); }
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back");
    fontOff();
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

static void ensureBleVisible() {
    int n = engine.bleCount();
    if (bleSel > n - 1) bleSel = n - 1;
    if (bleSel < 0) bleSel = 0;
    if (bleSel < off) off = bleSel;
    if (bleSel >= off + UI_VISIBLE) off = bleSel - UI_VISIBLE + 1;
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
    optLabels[optN] = i18n::tr("Radar", "Радар");       optIds[optN] = OPT_NET_RADAR;   optN++;
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
        case ST_HUNT24:    nrf.end(); showMenu();                          return;
        case ST_SUBSPECTRUM: subStop(); showMenu();                        return;
        case ST_SUBTX:     subTxOn = false; cc.end(); showMenu();          return;
        case ST_SUBREC:    cc.end(); showMenu();                           return;
        case ST_KEYBOARD:  st = ST_SUBREC; drawSubRecScreen();             return;   // naming is part of the record flow — keep CC1101 (touch-on-header path)
        case ST_REC_PLAY:  cc.end(); showMenu();                           return;
        case ST_SUBHUNT:   cc.end(); showMenu();                           return;
        case ST_SUBCFG:    subcfg.stop(); showMenu();                      return;
        case ST_POLITE:    portal.stop(); showMenu();                      return;
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
    if (st == ST_HUNT24)    nrf.end();             // release NRF24
    if (st == ST_SUBSPECTRUM) subStop();           // release CC1101
    if (st == ST_SUBTX)     { subTxOn = false; cc.end(); }   // stop TX + release CC1101
    if (st == ST_SUBREC)    cc.end();              // release CC1101
    if (st == ST_KEYBOARD)  cc.end();              // naming screen was reached with CC1101 up
    if (st == ST_REC_PLAY)  cc.end();              // release CC1101
    if (st == ST_SUBHUNT)   cc.end();              // release CC1101
    if (st == ST_SUBCFG)    subcfg.stop();         // drop the settings SoftAP
    if (st == ST_POLITE)    portal.stop();         // drop the captive-portal SoftAP
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
                            spLab = false; spTxOn = false; spTxMask = 0; spSweep = false; spRightPending = false;   // passive viewer — never transmits
                            if (nrf.begin()) { st = ST_SPECTRUM; drawSpectrumScreen(); }
                            else { infoTitle = i18n::tr("2.4GHz Spectrum", "Спектр 2.4ГГц"); infoBody = i18n::tr("NRF24 not found", "NRF24 не найден");
                                   infoNote = i18n::tr("This build expects an NRF24 module in slot 2.", "Нужен модуль NRF24 в слоте 2."); st = ST_INFO; drawInfo(); }
                            break;
        case F_HUNT24:      engine.pause();                 // 2.4 GHz frequency finder — pure RX (RPD hit-rate)
                            if (nrf.begin()) { nrf.setTxWifiMask(0); hunt24Reset(); st = ST_HUNT24; drawHunt24Chrome(); drawHunt24Graph(); }
                            else { infoTitle = i18n::tr("2.4 finder", "Частотомер 2.4"); infoBody = i18n::tr("NRF24 not found", "NRF24 не найден");
                                   infoNote = i18n::tr("This build expects an NRF24 module in slot 2.", "Нужен модуль NRF24 в слоте 2."); st = ST_INFO; drawInfo(); }
                            break;
        case F_NOISEGEN:    engine.pause();
                            spLab = true; spTxOn = false; spCursor = 6; spSweep = false; spRightPending = false;
                            spTxMask = (1 << 1) | (1 << 6) | (1 << 11);    // preset the non-overlapping channels, ready to fire
                            if (nrf.begin()) { st = ST_SPECTRUM; drawSpectrumScreen(); }
                            else { infoTitle = i18n::tr("Generator", "Генератор"); infoBody = i18n::tr("NRF24 not found", "NRF24 не найден");
                                   infoNote = i18n::tr("This build expects an NRF24 module in slot 2.", "Нужен модуль NRF24 в слоте 2."); st = ST_INFO; drawInfo(); }
                            break;
        case F_TXMODE:      drawTxModeInfo(); break;
        case F_PORTAL_CFG:{ engine.pauseAndWait();                 // setup network to name the portal AP
                            PolitePortalConfig cfg;
                            cfg.setup        = true;
                            cfg.portalSsid   = "Leshy-portal-setup";   // the setup network's own name
                            cfg.setupCurrent = net.labApName();        // prefill the form with the saved name
                            cfg.channel      = 6;
                            if (portal.begin(cfg)) { portalSetup = true; portalSaved = false; politePhase = 0; st = ST_POLITE; drawPoliteScreen(); }
                            else { infoTitle = i18n::tr("Portal setup", "Настройка портала"); infoBody = i18n::tr("Failed to start", "Не удалось запустить"); infoNote = ""; st = ST_INFO; drawInfo(); }
                            break; }
        case F_POLITE:    { engine.pauseAndWait();                 // raise our own named AP with the consent page
                            PolitePortalConfig cfg;
                            cfg.targetSsid = "";                   // consent mode — stop on the button
                            cfg.portalSsid = net.labApName();
                            cfg.channel    = 6;
                            if (portal.begin(cfg)) { portalSetup = false; portalSaved = false; politePhase = 0; st = ST_POLITE; drawPoliteScreen(); }
                            else { infoTitle = i18n::tr("Captive portal", "Captive-портал"); infoBody = i18n::tr("Failed to start", "Не удалось запустить"); infoNote = ""; st = ST_INFO; drawInfo(); }
                            break; }
        case F_SUBSPECTRUM: engine.pause();
                            if (cc.begin()) { cc.setBand(0); st = ST_SUBSPECTRUM; drawSubScreen(); }
                            else { infoTitle = i18n::tr("Sub-GHz Spectrum", "Спектр Sub-GHz"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_SUBTX:       engine.pause(); subTxOn = false;
                            if (cc.begin()) { cc.setBand(2); st = ST_SUBTX; drawSubTxScreen(); }   // default to the 433 band
                            else { infoTitle = i18n::tr("Sub-GHz TX", "Тест-передача"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_SUBPOWER:    drawSubPowerInfo(); break;
        case F_SUBREC:      engine.pause(); recN = 0;
                            if (cc.begin()) { cc.setBand(2); st = ST_SUBREC; drawSubRecScreen(); }   // default 433
                            else { infoTitle = i18n::tr("Sub-GHz Rec", "Запись Sub-GHz"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_SUBCFG:      engine.pauseAndWait();                 // settings portal owns the radio (SoftAP)
                            if (subcfg.begin()) { subCfgPhase = 0; st = ST_SUBCFG; drawSubCfgScreen(); }
                            else { infoTitle = i18n::tr("Sub-GHz setup", "Настройки Sub-GHz"); infoBody = i18n::tr("Failed to start", "Не удалось запустить"); infoNote = ""; st = ST_INFO; drawInfo(); }
                            break;
        case F_SUBHUNT:     engine.pause();                        // frequency hunter — pure RX sweep
                            if (cc.begin()) { cc.setRxGain(huntLowGain); huntReset(); st = ST_SUBHUNT; drawHuntChrome(); drawHuntGraph(); }
                            else { infoTitle = i18n::tr("Freq finder", "Частотомер"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_REC_PLAY:    engine.pause();                        // browse + replay the saved library (CC1101 for TX)
                            if (cc.begin()) { recCount = RecStore::list(recNames, RecStore::MAX_RECS); recSel = 0; recOff = 0; recDelArm = false; st = ST_REC_PLAY; drawRecPlayScreen(); }
                            else { infoTitle = i18n::tr("Playback", "Воспроизведение"); infoBody = i18n::tr("CC1101 not found", "CC1101 не найден");
                                   infoNote = i18n::tr("This build expects a CC1101 sub-GHz module.", "Нужен модуль CC1101."); st = ST_INFO; drawInfo(); }
                            break;
        case F_BLE_SCAN:    engine.setMode(ScanEngine::SCAN_BLE);  engine.resume(); st = ST_BLE;  off = 0; bleSel = 0; seenBleGen  = engine.bleGen();
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
// ---- BLE radar: lock one device and track its RSSI live to walk it down ----
static String   radarMac, radarLabel, radarVendor, radarSub;
static uint8_t  radarKind = 0;
static BleRow   bleInfo;   // frozen snapshot of the device shown on the details screen
static bool     radarWifi = false;          // false = BLE target, true = WiFi AP target
static uint8_t  radarBssid[6];
static int      radarChan = 0, radarWifiRssi = -100;
static uint32_t radarWifiSeen = 0;
static bool     radarPub = false, radarBeepOn = false;
static int      radarEma = -100, radarSlow = -100;
static uint32_t radarDrawAt = 0, radarBeepAt = 0, radarBeepOff = 0;

static void radarFooter() {
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back",
               radarBeepOn ? (i18n::isRu() ? "OK: писк вкл" : "OK: beep on")
                           : (i18n::isRu() ? "OK: писк выкл" : "OK: beep off"));
}

static void drawRadarChrome() {
    const uint16_t bg = uiBg();
    char chbuf[12];
    const char* rt;
    if (radarWifi) { snprintf(chbuf, sizeof(chbuf), "ch %d", radarChan); rt = chbuf; }   // WiFi: show the channel
    else           { rt = radarPub ? i18n::tr("fixed", "фикс") : nullptr; }               // BLE: fixed-address flag
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    uiHeaderRu(i18n::tr("Radar", "Радар"), rt);
    fontSmall();
    tft.setTextDatum(MC_DATUM);
    const char* kl = bleKindLabel((BleKind)radarKind, i18n::isRu());
    const char* tag = radarSub.length() ? radarSub.c_str() : kl[0] ? kl : radarVendor.c_str();   // subtype > category > brand
    String t = tag[0] ? String(tag) + "  " + radarLabel : radarLabel;
    while (t.length() > 4 && tft.textWidth(t) > 232) t = t.substring(0, t.length() - 1);
    tft.setTextColor(tft.color565(0x5a, 0xd0, 0xff), bg);
    tft.drawString(t, 120, 44);
    fontOff();
    radarFooter();
}

// Concentric rings that bloom outward with proximity (more rings lit = closer), a live
// RSSI read-out, a rough distance, and a closer/farther trend. RSSI is jumpy → smoothed.
static void drawRadarGauge(bool lost) {
    const uint16_t bg = uiBg();
    const uint16_t green = tft.color565(0x3f, 0xe0, 0x7a), dimr = tft.color565(0x24, 0x3a, 0x2c);
    const uint16_t red = tft.color565(0xff, 0x5a, 0x32), white = tft.color565(0xf0, 0xf0, 0xe6), dim = tft.color565(0x8f, 0xa9, 0x8f);
    const int cx = 120, cy = 138, R[4] = {20, 42, 64, 85};
    float p = (radarEma + 95) / 55.0f; if (p < 0) p = 0; if (p > 1) p = 1;
    int L = lost ? 0 : (int)(p * 4 + 0.5f);
    for (int r = 0; r < 4; r++) {
        uint16_t c = (r < L) ? green : dimr;
        tft.drawCircle(cx, cy, R[r], c);
        tft.drawCircle(cx, cy, R[r] - 1, c);
    }
    tft.fillCircle(cx, cy, 4, lost ? red : green);
    tft.fillRect(0, 230, 240, 69, bg);
    tft.setTextDatum(MC_DATUM);
    fontBig();
    if (lost) {
        tft.setTextColor(red, bg);
        tft.drawString(i18n::tr("LOST", "ПОТЕРЯН"), 120, 252);
    } else {
        char b[16];
        snprintf(b, sizeof(b), "%d dBm", radarEma);
        tft.setTextColor(white, bg);
        tft.drawString(b, 120, 250);
        fontSmall();
        float dist = powf(10.0f, (-59 - radarEma) / 20.0f);
        int tr = radarEma - radarSlow;
        const char* arr = tr > 2 ? i18n::tr("closer", "ближе") : tr < -2 ? i18n::tr("farther", "дальше") : i18n::tr("steady", "ровно");
        char db[32];
        snprintf(db, sizeof(db), "~%.1f %s   %s", dist, i18n::tr("m", "м"), arr);
        tft.setTextColor(dim, bg);
        tft.drawString(db, 120, 283);
    }
    fontOff();
}

static void radarStart(const BleRow& d) {
    radarWifi = false;
    radarMac = d.mac; radarVendor = d.vendor; radarSub = d.subtype; radarKind = d.kind; radarPub = d.pub;
    radarLabel = (d.tracker && d.label == "Find My") ? i18n::tr("Find My", "Локатор") : d.label;
    radarEma = d.rssi ? d.rssi : -100; radarSlow = radarEma;
    radarBeepOn = false; radarBeepOff = 0; radarDrawAt = 0;
    engine.setRadarTarget(radarMac);
    engine.setMode(ScanEngine::SCAN_BLE_RADAR);
    engine.resume();
    st = ST_BLE_RADAR;
    drawRadarChrome();
    drawRadarGauge(true);
}

static void radarStartWifi(const WifiRow& w) {
    radarWifi = true; memcpy(radarBssid, w.bssid, 6); radarChan = w.channel;
    radarLabel = w.ssid.length() ? w.ssid : String(i18n::tr("<hidden>", "<скрытая>"));
    radarVendor = ""; radarSub = ""; radarKind = 0; radarPub = false;
    radarWifiRssi = w.rssi; radarWifiSeen = millis();
    radarEma = w.rssi; radarSlow = w.rssi;
    radarBeepOn = false; radarBeepOff = 0; radarDrawAt = 0;
    engine.setMode(ScanEngine::SCAN_WIFI);      // fast WiFi-only loop for responsive RSSI
    engine.resume();
    st = ST_WIFI_RADAR;
    drawRadarChrome();
    drawRadarGauge(false);
}

static void radarStop() {
    digitalWrite(2, LOW);                       // buzzer silent
    if (!radarWifi) engine.setMode(ScanEngine::SCAN_BLE);   // BLE: back to list scanning (WiFi list already SCAN_WIFI)
}

static void radarTick() {
    uint32_t t = millis();
    int rssi; uint32_t seen;
    if (radarWifi) {
        int r = engine.wifiRssiOf(radarBssid);
        if (r > -128) { radarWifiRssi = r; radarWifiSeen = t; }
        rssi = radarWifiRssi; seen = radarWifiSeen;
    } else { rssi = engine.radarRssi(); seen = engine.radarLastSeen(); }
    bool lost = (seen == 0) || (t - seen > (radarWifi ? 5000u : 3000u));   // WiFi sweeps slower
    if (!lost && rssi != 0) { radarEma += (rssi - radarEma) / 4; radarSlow += (radarEma - radarSlow) / 12; }
    if (radarBeepOn && !lost) {                 // Geiger-style: faster clicks as you close in
        float p = (radarEma + 95) / 55.0f; if (p < 0) p = 0; if (p > 1) p = 1;
        uint32_t iv = 90 + (uint32_t)((1 - p) * 520);
        if (t - radarBeepAt >= iv) { radarBeepAt = t; digitalWrite(2, HIGH); radarBeepOff = t + 18; }
        if (radarBeepOff && t >= radarBeepOff) { digitalWrite(2, LOW); radarBeepOff = 0; }
    } else if (radarBeepOff) { digitalWrite(2, LOW); radarBeepOff = 0; }
    if (t - radarDrawAt >= 120) { radarDrawAt = t; drawRadarGauge(lost); }
}

// ---- BLE device details: everything extractable from the advertisement ----
static void infoLine(int& y, const char* k, const String& v, uint16_t vcol) {
    const uint16_t bg = uiBg(), dim = tft.color565(0x8f, 0xa9, 0x8f);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(dim, bg);  tft.drawString(k, 8, y);
    tft.setTextColor(vcol, bg); tft.drawString(v, 96, y);
    y += 26;
}

static void drawBleInfo() {
    const uint16_t bg = uiBg(), white = tft.color565(0xf0, 0xf0, 0xe6), cyan = tft.color565(0x5a, 0xd0, 0xff);
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    uiHeaderRu(i18n::tr("Details", "Детали"), bleInfo.pub ? i18n::tr("fixed", "фикс") : nullptr);
    fontSmall();
    int y = 46;
    const char* kl = bleKindLabel((BleKind)bleInfo.kind, i18n::isRu());
    String typ = bleInfo.subtype.length() ? bleInfo.subtype
               : kl[0]                    ? String(kl)
               : bleInfo.tracker          ? String(i18n::tr("Find My", "Локатор"))
               : bleInfo.vendor.length()  ? bleInfo.vendor : String("—");
    infoLine(y, i18n::tr("Type", "Тип"), typ, cyan);
    if (!bleInfo.tracker && bleInfo.label.length() && bleInfo.label != bleInfo.mac)
        infoLine(y, i18n::tr("Name", "Имя"), bleInfo.label, white);
    infoLine(y, i18n::tr("Addr", "Адрес"), bleInfo.mac, white);
    infoLine(y, i18n::tr("Addr type", "Тип адр"), bleInfo.pub ? i18n::tr("public", "публичн") : i18n::tr("random", "случайн"), white);
    { float dist = powf(10.0f, (-59 - bleInfo.rssi) / 20.0f);
      char b[36]; snprintf(b, sizeof(b), "%d dBm  ~%.1f %s", bleInfo.rssi, dist, i18n::tr("m", "м"));
      infoLine(y, i18n::tr("Signal", "Сигнал"), b, white); }
    if (bleInfo.txpwr != 127)   { char b[16]; snprintf(b, sizeof(b), "%d dBm", bleInfo.txpwr);      infoLine(y, "TX", b, white); }
    if (bleInfo.appearance)     { char b[16]; snprintf(b, sizeof(b), "0x%04X", bleInfo.appearance); infoLine(y, "Appearance", b, white); }
    if (bleInfo.svc.length())   infoLine(y, i18n::tr("Service", "Сервис"), bleInfo.svc, white);
    if (bleInfo.vendor.length())      infoLine(y, i18n::tr("Vendor", "Вендор"), bleInfo.vendor, white);
    else if (bleInfo.company)   { char b[16]; snprintf(b, sizeof(b), "0x%04X", bleInfo.company);    infoLine(y, i18n::tr("Vendor", "Вендор"), b, white); }
    fontOff();
    uiFooterRu(i18n::isRu() ? "◀ назад" : "◀ back", i18n::tr("OK radar", "OK радар"));
}

static void onKey(int ev) {
    switch (ev) {
        case Buttons::UP:
            if (st == ST_MENU) { if (curSel() > 0) { int p = curSel(); curSel()--; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI)    { if (wifiSel > 0) { wifiSel--; ensureWifiVisible(); drawList(false); } }
            else if (st == ST_BLE)     { if (bleSel > 0) { bleSel--; ensureBleVisible(); drawList(false); } }
            else if (st == ST_CONN)    { if (connSel > 0) { int p = connSel; connSel--; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel > 0)  { int p = optSel;  optSel--;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel > 0)  { int p = hidSel; hidSel--; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            else if (st == ST_LEGAL)   { if (legOff > 0) { legOff -= 4; if (legOff < 0) legOff = 0; drawLegalScreen(); } }
            else if (st == ST_LANGPICK){ if (langPickSel > 0) { langPickSel--; drawLangPick(); } }
            else if (st == ST_SPECTRUM && spLab){ if (!spSweep && spCursor > 1)  { spCursor--; if (spTxOn && !spTxMask) spApplyTx(); spDrawAxis(); } }   // move caret (carrier follows it live only in follow mode; sweep owns the caret)
            else if (st == ST_SUBREC) subReplay();   // up = replay the captured signal
            else if (st == ST_KEYBOARD) { int pr = kbRow, pc = kbCol; if (kbRow > 0) kbRow--; if (kbCol >= kbRowCols(kbRow)) kbCol = kbRowCols(kbRow) - 1; kbRepaintCursor(pr, pc); }
            else if (st == ST_REC_PLAY) { if (recDelArm) { recDelArm = false; drawRecPlayScreen(); } else if (recSel > 0) { int p = recSel; recSel--; tft.fillRect(0, 283, 240, 18, uiBg()); int oo = recOff; clampRecList(); if (recOff != oo) drawRecList(); else { drawRecPlayRow(p - recOff); drawRecPlayRow(recSel - recOff); } } }
            break;
        case Buttons::DOWN:
            if (st == ST_MENU) { if (curSel() < MENUS[curMenu()].n - 1) { int p = curSel(); curSel()++; menuScreen.repaint(p, curSel()); } }
            else if (st == ST_WIFI)    { if (wifiSel < engine.wifiCount() - 1) { wifiSel++; ensureWifiVisible(); drawList(false); } }
            else if (st == ST_BLE)     { if (bleSel < engine.bleCount() - 1) { bleSel++; ensureBleVisible(); drawList(false); } }
            else if (st == ST_CONN)    { if (connSel < connActN - 1) { int p = connSel; connSel++; drawActionBtn(connActY[p], connLabel(connActs[p]), false); drawActionBtn(connActY[connSel], connLabel(connActs[connSel]), true); } }
            else if (st == ST_OPTIONS) { if (optSel < optN - 1)      { int p = optSel;  optSel++;  drawActionBtn(optY[p], optLabels[p], false); drawActionBtn(optY[optSel], optLabels[optSel], true); } }
            else if (st == ST_HIDDEN)  { if (hidSel < revealer.count() - 1) { int p = hidSel; hidSel++; int oo = hidOff; clampHidden(); if (hidOff != oo) drawHiddenRowsOnly(); else { drawHiddenRow(p - hidOff); drawHiddenRow(hidSel - hidOff); } } }
            else if (st == ST_LEGAL)   { int m = legN - LEG_LINES; if (m < 0) m = 0; if (legOff < m) { legOff += 4; if (legOff > m) legOff = m; drawLegalScreen(); } }
            else if (st == ST_LANGPICK){ if (langPickSel < 1) { langPickSel++; drawLangPick(); } }
            else if (st == ST_SPECTRUM && spLab){ if (!spSweep && spCursor < 13) { spCursor++; if (spTxOn && !spTxMask) spApplyTx(); spDrawAxis(); } }   // move caret (carrier follows it live only in follow mode; sweep owns the caret)
            else if (st == ST_SUBREC) { cc.setBand(cc.band() + 1); recN = 0; drawSubRecScreen(); }   // down = cycle band (drops the capture)
            else if (st == ST_KEYBOARD) { int pr = kbRow, pc = kbCol; if (kbRow < KB_NROW) kbRow++; if (kbCol >= kbRowCols(kbRow)) kbCol = kbRowCols(kbRow) - 1; kbRepaintCursor(pr, pc); }
            else if (st == ST_REC_PLAY) { if (recDelArm) { recDelArm = false; drawRecPlayScreen(); } else if (recSel < recCount - 1) { int p = recSel; recSel++; tft.fillRect(0, 283, 240, 18, uiBg()); int oo = recOff; clampRecList(); if (recOff != oo) drawRecList(); else { drawRecPlayRow(p - recOff); drawRecPlayRow(recSel - recOff); } } }
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
            else if (st == ST_BLE) { BleRow r; if (engine.bleRow(bleSel, r) && r.mac.length()) radarStart(r); }   // lock the device → radar finder
            else if (st == ST_BLE_RADAR) { radarBeepOn = !radarBeepOn; if (!radarBeepOn) digitalWrite(2, LOW); radarFooter(); }   // toggle the proximity beep
            else if (st == ST_BLE_INFO) radarStart(bleInfo);   // OK from details → radar finder
            else if (st == ST_SPECTRUM && spLab) spToggleArm();   // arm/disarm the caret channel for TX noise
            else if (st == ST_SUBTX) { subTxOn = !subTxOn; if (subTxOn) subTxApply(); else cc.endTx(); drawSubTxScreen(); }
            else if (st == ST_SUBREC) subRecord();       // OK = capture the next signal
            else if (st == ST_KEYBOARD) kbSelect();
            else if (st == ST_REC_PLAY) { if (recDelArm) recDeleteSelected(); else recPlaySelected(); }
            else if (st == ST_SUBHUNT) { huntLowGain = !huntLowGain; cc.setRxGain(huntLowGain); huntReset(); drawHuntGraph(); }   // OK = toggle -18 dB near-field gain
            else if (st == ST_HUNT24) { hunt24Reset(); drawHunt24Graph(); }   // OK = recalibrate
            else if (st == ST_INFO && infoAction == F_LEDS)      { leds.cycleBrightness(); drawLedsInfo(); }
            else if (st == ST_INFO && infoAction == F_BACKLIGHT) { uiBacklightCycle();     drawBacklightInfo(); }
            else if (st == ST_INFO && infoAction == F_TXPOWER)   { txPowerCycle();         drawTxPowerInfo(); }
            else if (st == ST_INFO && infoAction == F_TXMODE)    { txModeCycle();          drawTxModeInfo(); }
            else if (st == ST_INFO && infoAction == F_SUBPOWER)  { subPowerCycle();        drawSubPowerInfo(); }
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
            else if (st == ST_BLE) { if (engine.bleRow(bleSel, bleInfo)) { st = ST_BLE_INFO; drawBleInfo(); } }   // right = full advertisement details
            else if (st == ST_SUBSPECTRUM) { cc.setBand(cc.band() + 1); drawSubScreen(); }   // cycle the displayed band
            else if (st == ST_SUBTX) { cc.setBand(cc.band() + 1); if (subTxOn) subTxApply(); drawSubTxScreen(); }   // cycle the TX band
            else if (st == ST_SUBREC) { if (recN > 0) { kbBuf[0] = 0; kbLen = 0; kbRow = 0; kbCol = 0; st = ST_KEYBOARD; drawKeyboard(true); } }   // right = name + save the capture
            else if (st == ST_KEYBOARD) { int pc = kbCol; if (kbCol < kbRowCols(kbRow) - 1) kbCol++; kbRepaintCursor(kbRow, pc); }
            else if (st == ST_REC_PLAY) { if (recCount > 0 && !recDelArm) { recDelArm = true; drawRecPlayScreen(); } }   // right = arm delete
            else if (st == ST_SUBHUNT) { huntReset(); drawHuntGraph(); }   // right = reset the peak hold
            else if (st == ST_HUNT24) { hunt24Reset(); drawHunt24Graph(); }   // right = recalibrate
            else if (st == ST_SPECTRUM && spLab) { spRightPending = true; spRightLong = false; spRightAt = millis(); spRightRel = 0; }   // short=static/follow, long=sweep (timed in loop)
            else if (st == ST_SPECTRUM)          spToggleView();  // passive: flip occupancy <-> traffic view
            else if (st == ST_INFO && infoAction == F_LEDS)      { leds.cycleBrightness(); drawLedsInfo(); }
            else if (st == ST_INFO && infoAction == F_BACKLIGHT) { uiBacklightCycle();     drawBacklightInfo(); }
            else if (st == ST_INFO && infoAction == F_TXPOWER)   { txPowerCycle();         drawTxPowerInfo(); }
            else if (st == ST_INFO && infoAction == F_TXMODE)    { txModeCycle();          drawTxModeInfo(); }
            else if (st == ST_INFO && infoAction == F_SUBPOWER)  { subPowerCycle();        drawSubPowerInfo(); }
            break;
        case Buttons::LEFT:
            if (st == ST_KEYBOARD) { int pc = kbCol; if (kbCol > 0) kbCol--; kbRepaintCursor(kbRow, pc); }   // cursor left — never falls through to back()
            else if (st == ST_REC_PLAY && recDelArm) { recDelArm = false; drawRecPlayScreen(); }              // cancel the delete confirm
            else if (st == ST_BLE_RADAR) { radarStop(); st = ST_BLE; seenBleGen = engine.bleGen(); tft.fillRect(0, 28, 240, 320 - 28, uiBg()); drawList(true); }   // back to the device list
            else if (st == ST_BLE_INFO)  { st = ST_BLE; seenBleGen = engine.bleGen(); tft.fillRect(0, 28, 240, 320 - 28, uiBg()); drawList(true); }   // details → back to the list
            else if (st == ST_WIFI_RADAR) { radarStop(); gotoWifi(); }   // WiFi radar → back to the network list
            else back();
            break;
        default:
            break;
    }
}

// Serial remote (headless testing over USB): u/d/l/r/o = keys; scan/ble/hidden/conn/menu = jump.
// QA: dump the framebuffer over serial as hex rows (ILI9341 supports read; TFT_MISO=37).
// Host decodes to PNG. "shot" captures whatever screen is currently shown.
static void screenshotDump() {
    static uint16_t row[240];
    static char line[240 * 4 + 2];
    const char* H = "0123456789ABCDEF";
    Serial.println();
    Serial.println("SHOT 240 320");
    for (int y = 0; y < 320; y++) {
        tft.readRect(0, y, 240, 1, row);
        char* p = line;
        for (int x = 0; x < 240; x++) {
            uint16_t v = row[x];
            *p++ = H[(v >> 12) & 0xF]; *p++ = H[(v >> 8) & 0xF]; *p++ = H[(v >> 4) & 0xF]; *p++ = H[v & 0xF];
        }
        *p = 0;
        Serial.println(line);
    }
    Serial.println("SHOT END");
}

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
            else if (!strcmp(buf, "spec"))    launch(F_SPECTRUM);      // QA jumps for screenshots
            else if (!strcmp(buf, "subspec")) launch(F_SUBSPECTRUM);
            else if (!strcmp(buf, "hunt"))    launch(F_SUBHUNT);
            else if (!strcmp(buf, "hunt24"))  launch(F_HUNT24);
            else if (!strcmp(buf, "subtx"))   launch(F_SUBTX);
            else if (!strcmp(buf, "gen"))     launch(F_NOISEGEN);
            else if (!strcmp(buf, "rec"))     launch(F_SUBREC);
            else if (!strcmp(buf, "legal"))  launch(F_LEGAL);
            else if (!strcmp(buf, "legalreset")) { Preferences p; p.begin("leshy", false); p.remove("legal_ok"); p.end(); Serial.println("[cmd] legal flag cleared — reboot to see the gate"); }
            else if (!strcmp(buf, "shot"))  { screenshotDump(); continue; }                      // QA: framebuffer -> serial (host makes a PNG)
            else if (!strcmp(buf, "wifi"))  {                                                    // QA: is the board's own ESP32 radio associated, and on which channel?
                Serial.printf("[wifi] status=%d mode=%d ch=%d rssi=%d ssid=\"%s\" ip=%s\n",
                    (int)WiFi.status(), (int)WiFi.getMode(), WiFi.channel(), (int)WiFi.RSSI(),
                    WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
                continue;
            }
            else if (!strcmp(buf, "occ"))   {                                                    // QA: live all-module occupancy (0..255 per NRF ch, 2400+ch MHz)
                Serial.print("[occ]");
                for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) Serial.printf(" %d", spEma[c]);
                Serial.println(); continue;
            }
            else if (!strcmp(buf, "occ1"))  {                                                    // QA: same, but ONE module with siblings powered down — isolates external air from inter-module crosstalk
                static uint8_t pass[Nrf24Spectrum::CHANNELS]; uint16_t sum[Nrf24Spectrum::CHANNELS] = {0};
                const int N = 16;
                for (int p = 0; p < N; p++) { nrf.sweepSolo(pass); for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) sum[c] += pass[c]; }
                Serial.print("[occ1]");
                for (int c = 0; c < Nrf24Spectrum::CHANNELS; c++) Serial.printf(" %d", sum[c] * 255 / N);
                Serial.println(); continue;
            }
            else if (!strcmp(buf, "en"))    { i18n::set(Lang::EN); saveLang(Lang::EN); depth = 0; showMenu(); continue; }   // QA: language for screenshots
            else if (!strcmp(buf, "ru"))    { i18n::set(Lang::RU); saveLang(Lang::RU); depth = 0; showMenu(); continue; }
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
            else if (!strcmp(buf, "ccrssi")) {   // QA: live RSSI on the sub-GHz capture freq → pick the threshold
                engine.pauseAndWait();
                if (cc.begin()) cc.diagRssi(subTxFreqKHz());
                else Serial.println("[ccrssi] chip not present");
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
                if (st == ST_HUNT24)      nrf.end();
                if (st == ST_SUBSPECTRUM) subStop();
                if (st == ST_SUBTX)     { subTxOn = false; cc.end(); }
                if (st == ST_SUBREC || st == ST_KEYBOARD || st == ST_REC_PLAY || st == ST_SUBHUNT) cc.end();
                if (st == ST_SUBCFG)      subcfg.stop();
                if (st == ST_POLITE)      portal.stop();
                if (st == ST_PROVISION)   net.stopProvision();
                engine.pause();
                st = ST_OTA; seenOtaGen = ota.gen(); seenOtaPhase = (int)ota.phase(); drawOtaScreen();
            }
            else if (!strcmp(buf, "menu"))   { if (ota.busy()) continue;
                                               if (st == ST_DEAUTH) detector.stop();
                                               if (st == ST_CHANNELS) airtime.stop();
                                               if (st == ST_SPECTRUM) spectrumStop();
                                               if (st == ST_HUNT24) nrf.end();
                                               if (st == ST_SUBSPECTRUM) subStop();
                                               if (st == ST_SUBTX) { subTxOn = false; cc.end(); }
                                               if (st == ST_SUBREC || st == ST_KEYBOARD || st == ST_REC_PLAY || st == ST_SUBHUNT) cc.end();
                                               if (st == ST_SUBCFG) subcfg.stop();
                                               if (st == ST_POLITE) portal.stop();
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
    pinMode(2, OUTPUT); digitalWrite(2, LOW);   // hold the on-board buzzer (IO2) silent — it's the stock low-battery alarm, we don't use it
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
    subPwrIdx = loadSubPower(); cc.setTxPower(CC_PA[subPwrIdx]);   // saved Sub-GHz TX power (default max)
    loadSubCfg();                      // saved Sub-GHz recorder settings (wait/freq/threshold/repeats/mod/invert)
    if (!RecStore::begin()) Serial.println("[rec] LittleFS mount failed — saved captures unavailable");
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
           : (st == ST_PROVISION || (st == ST_POLITE && portal.isRunning()) || st == ST_SUBCFG) ? StatusLeds::PORTAL
           : st == ST_DEAUTH                       ? StatusLeds::PROMISC
           : (st == ST_WIFI || st == ST_CHANNELS || st == ST_SPECTRUM || st == ST_HUNT24 || st == ST_WIFI_RADAR) ? StatusLeds::WIFI_SCAN
           : st == ST_SUBSPECTRUM                  ? StatusLeds::PROMISC
           : (st == ST_BLE || st == ST_BLE_RADAR || st == ST_BLE_INFO) ? StatusLeds::BLE_SCAN
           : (st == ST_OTA && ota.phase() == OtaManager::FAILED) ? StatusLeds::ERR
                                                   : StatusLeds::IDLE);
    // An antenna emitting noise (spectrum TX) lights its own LED yellow: NRF slot i sits
    // under LED i+1 (LED 0 is the sub-GHz antenna), so shift the slot mask up by one.
    uint8_t txLeds = (st == ST_SPECTRUM && nrf.txActive()) ? (uint8_t)(nrf.txSlotMask() << 1)
                   : (st == ST_SUBTX && subTxOn)           ? (uint8_t)0x01     // sub-GHz antenna = LED 0
                                                           : 0;
    leds.setTx(txLeds);
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
        ensureBleVisible();       // keep the cursor valid as the device list grows/shrinks
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
    if (st == ST_POLITE) {
        portal.loop();
        if (portalSetup && portal.nameSubmitted() && !portalSaved) {
            net.saveLabApName(portal.submittedName());   // persist the name typed in the setup form
            portalSaved = true;
        }
        int ph = !portal.isRunning() ? 2 : (portalSetup ? portalSaved : portal.consented()) ? 1 : 0;
        if (ph != politePhase) { politePhase = ph; drawPoliteScreen(); }
    }
    if (st == ST_SPECTRUM && spLab && spRightPending) {          // RIGHT: short = static/follow, hold ≥500 ms = auto-sweep
        if (buttons.held(Buttons::RIGHT)) {                     // still down — a lone I2C 0xFF read must not count as release
            spRightRel = 0;
            if (!spRightLong && millis() - spRightAt >= 500) { spRightLong = true; spSweepToggle(); }
        } else if (++spRightRel >= 3) {                         // 3 consecutive "up" reads = a real release (glitch-proof)
            if (!spRightLong) spToggleTx();
            spRightPending = false; spRightLong = false; spRightRel = 0;
        }
    }
    if (st == ST_SPECTRUM) spectrumTick();
    if (st == ST_HUNT24) hunt24Tick();
    if (st == ST_BLE_RADAR || st == ST_WIFI_RADAR) radarTick();
    // Sub-GHz spectrum waterfall
    if (st == ST_SUBSPECTRUM) subTick();
    // Sub-GHz frequency hunter: keep sweeping + peak-holding while shown.
    if (st == ST_SUBHUNT) huntTick();
    // Sub-GHz test transmitter: blast a packet each loop while armed.
    if (st == ST_SUBTX && subTxOn) cc.txBurst();
    // Sub-GHz settings portal: service it; apply the saved settings on submit.
    if (st == ST_SUBCFG) {
        subcfg.loop();
        int ph = !subcfg.isRunning() ? 2 : subcfg.saved() ? 1 : 0;
        if (ph != subCfgPhase) { if (ph >= 1) loadSubCfg(); subCfgPhase = ph; drawSubCfgScreen(); }
    }

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
