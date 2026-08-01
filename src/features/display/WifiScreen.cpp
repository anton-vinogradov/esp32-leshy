#include "WifiScreen.h"

#include "Display.h"

#include <stdio.h>

static const int VISIBLE = 12;

void WifiScreen::scanCue() {
    uiHeader("Wi-Fi", "scanning");
}

int WifiScreen::scan() {
    return scanner_.scan();
}

void WifiScreen::render(int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);

    char right[16];
    sprintf(right, "%d nets", scanner_.count());
    uiHeader("Wi-Fi", right);
    tft.fillRect(0, 28, 240, 306 - 28, bg);

    int n = scanner_.count();
    for (int i = 0; i < VISIBLE; i++) {
        int idx = offset + i;
        if (idx >= n) break;
        const WifiAp& a = scanner_.at(idx);
        int y = 32 + i * 23;
        uint16_t col = uiRssiColor(a.rssi);

        uiSignalBars(6, y, a.rssi, col);

        if (a.auth != 0) {                       // encrypted → lock marker
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(dim, bg);
            tft.drawString("#", 24, y + 8, 2);
        }
        String ss = a.ssid.length() ? a.ssid : String("<hidden>");
        if (ss.length() > 16) ss = ss.substring(0, 15) + "~";
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(white, bg);
        tft.drawString(ss, 34, y + 8, 2);

        char r[8];
        sprintf(r, "%d", a.rssi);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(col, bg);
        tft.drawString(r, 232, y + 8, 2);
    }

    uiFooter("SEL: BLE   UP/DN: scroll");
}
