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

// Headless demo selector until the real menu (Phase 0) lands. Edit DEMO to switch.
#define DEMO_WIFI_SCANNER    1
#define DEMO_DEAUTH_DETECTOR 2
#define DEMO_BLE_SCANNER     3
#define DEMO_SIGNAL_FINDER   4
#define DEMO_POLITE_PORTAL   5
#define DEMO_DISPLAY         6
#define DEMO_DASHBOARD       7
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

WifiScreen wifiScreen;

void setup() {
    Serial.begin(115200);
    delay(200);
    i18n::set(UI_LANG);
    displayInit();
    BootScreen().show();
    delay(1800);
}

void loop() {
    wifiScreen.refresh();
    delay(4000);
}

#endif
