#include "WifiScreen.h"

#include "Display.h"

#include <stdio.h>

void WifiScreen::scanCue() {
    uiHeader("Wi-Fi", "scanning");
}

int WifiScreen::scan() {
    return scanner_.scan();
}

void WifiScreen::rows(int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);

    TFT_eSprite& row = uiRow();
    int n = scanner_.count();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        row.fillSprite(bg);
        if (idx < n) {
            const WifiAp& a = scanner_.at(idx);
            uint16_t col = uiRssiColor(a.rssi);
            uiSignalBars(row, 6, 5, a.rssi, col);
            if (a.auth != 0) {
                row.setTextDatum(ML_DATUM);
                row.setTextColor(dim, bg);
                row.drawString("#", 24, 12, 2);
            }
            String ss = a.ssid.length() ? a.ssid : String("<hidden>");
            if (ss.length() > 16) ss = ss.substring(0, 15) + "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(white, bg);
            row.drawString(ss, 34, 12, 2);
            char r[8];
            sprintf(r, "%d", a.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, bg);
            row.drawString(r, 232, 12, 2);
        }
        row.pushSprite(0, y);
    }
}

void WifiScreen::draw(int offset) {
    char right[16];
    sprintf(right, "%d nets", scanner_.count());
    uiHeader("Wi-Fi", right);
    rows(offset);
    uiFooter("SEL: BLE   UP/DN: scroll");
}
