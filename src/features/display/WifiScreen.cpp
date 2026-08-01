#include "WifiScreen.h"

#include "Display.h"

#include <stdio.h>

void WifiScreen::rows(ScanEngine& e, int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);

    TFT_eSprite& row = uiRow();
    int n = e.wifiCount();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        row.fillSprite(bg);
        WifiRow r;
        if (idx < n && e.wifiRow(idx, r)) {
            uint16_t col = uiRssiColor(r.rssi);
            uiSignalBars(row, 6, 5, r.rssi, col);
            if (r.auth != 0) {
                row.setTextDatum(ML_DATUM);
                row.setTextColor(dim, bg);
                row.drawString("#", 24, 12, 2);
            }
            String mine;
            bool isMine = net_ && net_->isMine(r.bssid, mine);
            bool named  = r.ssid.length() > 0;       // real name (broadcast or revealed)
            String ss = named ? r.ssid : (isMine ? mine : String("<hidden>"));
            if (ss.length() > 14) ss = ss.substring(0, 13) + "~";
            if (isMine) ss = "*" + ss;              // your own network
            row.setTextDatum(ML_DATUM);
            row.setTextColor(isMine ? tft.color565(0xff, 0xcf, 0x3f) : white, bg);
            row.drawString(ss, 34, 12, 2);
            if (r.hidden && (named || isMine)) {    // known name, but still a hidden SSID
                int hx = 34 + row.textWidth(ss, 2) + 5;
                if (hx < 206) {
                    row.setTextColor(tft.color565(0xff, 0xa5, 0x2a), bg);
                    row.drawString("H", hx, 12, 2);
                }
            }
            char b[8];
            sprintf(b, "%d", r.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, bg);
            row.drawString(b, 232, 12, 2);
        }
        row.pushSprite(0, y);
    }
}

void WifiScreen::draw(ScanEngine& e, int offset) {
    int n = e.wifiCount();
    char right[16];
    if (n > 0) sprintf(right, "%d nets", n); else sprintf(right, "scanning");
    uiHeader("Wi-Fi", right);
    rows(e, offset);
    uiFooter("LEFT: menu   UP/DN: scroll");
}
