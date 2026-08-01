#include "WifiScreen.h"

#include "Display.h"

#include <stdio.h>

void WifiScreen::drawBars(int x, int y, int rssi, uint16_t color) {
    int bars = rssi > -55 ? 4 : rssi > -67 ? 3 : rssi > -78 ? 2 : rssi > -88 ? 1 : 0;
    uint16_t off = tft.color565(0x33, 0x3a, 0x33);
    for (int b = 0; b < 4; b++) {
        int h = 4 + b * 3;
        tft.fillRect(x + b * 5, y + 13 - h, 3, h, b < bars ? color : off);
    }
}

void WifiScreen::refresh() {
    const uint16_t bg    = tft.color565(0x10, 0x18, 0x12);
    const uint16_t hdr   = tft.color565(0x1e, 0x3a, 0x28);
    const uint16_t gold  = tft.color565(0xe7, 0xcf, 0x8f);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t green = tft.color565(0x4c, 0xd1, 0x64);
    const uint16_t yellow= tft.color565(0xf0, 0xc4, 0x3a);
    const uint16_t red   = tft.color565(0xd1, 0x4c, 0x4c);

    // header + "scanning" cue (shown during the ~2 s blocking scan)
    tft.fillRect(0, 0, 240, 28, hdr);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(gold, hdr);
    tft.drawString("Wi-Fi", 6, 14, 4);
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(dim, hdr);
    tft.drawString("scanning", 234, 14, 2);

    int n = scanner_.scan();

    // replace the cue with the network count
    tft.fillRect(150, 2, 88, 24, hdr);
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(gold, hdr);
    char cnt[16];
    sprintf(cnt, "%d nets", n);
    tft.drawString(cnt, 234, 14, 2);

    // list
    tft.fillRect(0, 28, 240, 320 - 28, bg);
    int rows = n < 13 ? n : 13;
    for (int i = 0; i < rows; i++) {
        const WifiAp& a = scanner_.at(i);
        int y = 34 + i * 22;
        uint16_t col = a.rssi > -60 ? green : a.rssi > -75 ? yellow : red;

        drawBars(6, y, a.rssi, col);

        String ssid = a.ssid.length() ? a.ssid : String("<hidden>");
        if (ssid.length() > 17) ssid = ssid.substring(0, 16) + "~";
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(white, bg);
        tft.drawString(ssid, 30, y + 8, 2);

        char r[8];
        sprintf(r, "%d", a.rssi);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(col, bg);
        tft.drawString(r, 232, y + 8, 2);

        if (a.auth != 0) {                       // encrypted → lock marker
            tft.setTextColor(dim, bg);
            tft.setTextDatum(ML_DATUM);
            tft.drawString("#", 22, y + 8, 2);
        }
    }
}
