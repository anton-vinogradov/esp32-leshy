#include "WifiScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"

#include <stdio.h>

void WifiScreen::rows(ScanEngine& e, int offset, int sel) {
    const uint16_t bg     = uiBg();
    const uint16_t selbg  = tft.color565(0x22, 0x33, 0x22);   // selected row highlight
    const uint16_t bright = tft.color565(0xff, 0xff, 0xf2);
    const uint16_t grey   = tft.color565(0x66, 0x70, 0x66);   // hidden, not yet revealed
    const uint16_t dim    = tft.color565(0x8f, 0xa9, 0x8f);
    const uint16_t gold   = tft.color565(0xff, 0xcf, 0x3f);

    TFT_eSprite& row = uiRow();
    int n = e.wifiCount();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        uint16_t rbg = (idx == sel) ? selbg : bg;
        row.fillSprite(rbg);
        WifiRow r;
        if (idx < n && e.wifiRow(idx, r)) {
            uint16_t col = uiRssiColor(r.rssi);
            uiSignalBars(row, 6, 5, r.rssi, col);
            String mine;
            bool isMine = net_ && net_->isMine(r.bssid, mine);
            bool named = r.ssid.length() > 0;
            bool unrev = r.hidden && !named && !isMine;
            String ss = named ? r.ssid : (isMine ? mine : String("раскрываю"));
            if (isMine) ss = "*" + ss;
            bool trunc = false;                      // name column ~ up to x=142, gap before channel
            while (ss.length() > 3 && row.textWidth(ss) > 112) { ss = ss.substring(0, ss.length() - 1); trunc = true; }
            if (trunc) ss += "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(isMine ? gold : (unrev ? grey : bright), rbg);
            row.drawString(ss, 30, 12);
            if (r.channel >= 1) {                     // channel
                row.setTextColor(dim, rbg);
                row.drawString("c" + String(r.channel), 160, 12);
            }
            if (r.auth != 0) {                        // encryption lock
                row.setTextColor(dim, rbg);
                row.drawString("#", 196, 12);
            }
            char b[8]; sprintf(b, "%d", r.rssi);      // rssi
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, rbg);
            row.drawString(b, 232, 12);
        }
        row.pushSprite(0, y);
    }
}

void WifiScreen::draw(ScanEngine& e, int offset, int sel) {
    int n = e.wifiCount();
    char right[24];
    if (n > 0) sprintf(right, "%d %s", n, i18n::tr("nets", "сетей"));
    else       sprintf(right, "%s", i18n::tr("scanning", "скан"));
    uiHeaderRu("Wi-Fi", right);
    rows(e, offset, sel);
    uiFooterRu(i18n::isRu() ? "◀ меню" : "◀ menu", i18n::isRu() ? "опции ▶" : "options ▶");
    fontOff();
}
