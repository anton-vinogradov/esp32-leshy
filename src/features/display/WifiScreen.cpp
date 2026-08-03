#include "WifiScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"

#include <stdio.h>

void WifiScreen::rows(ScanEngine& e, int offset, int sel) {
    const uint16_t bg     = uiBg();
    const uint16_t selbg  = tft.color565(0x22, 0x33, 0x22);   // selected row highlight
    const uint16_t bright = tft.color565(0xff, 0xff, 0xf2);
    const uint16_t grey   = tft.color565(0x66, 0x70, 0x66);   // hidden network (revealed name or not)
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
            String mine;
            bool isMine = net_ && net_->isMine(r.bssid, mine);
            bool named = r.ssid.length() > 0;
            bool hiddenNet = r.hidden && !isMine;     // hidden AP (revealed name or not) → grey, so it stands out
            String ss = named ? r.ssid : (isMine ? mine : String(i18n::tr("revealing", "раскрываю")));
            if (isMine) ss = "*" + ss;
            bool trunc = false;                       // name column: left edge .. ~x=86 (clear gap to graph)
            while (ss.length() > 3 && row.textWidth(ss) > 80) { ss = ss.substring(0, ss.length() - 1); trunc = true; }
            if (trunc) ss += "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(isMine ? gold : (hiddenNet ? grey : bright), rbg);
            row.drawString(ss, 6, 12);
            if (r.channel >= 1) {                     // channel — right after the name
                row.setTextDatum(MR_DATUM);
                row.setTextColor(dim, rbg);
                row.drawString("c" + String(r.channel), 118, 12);
            }
            // signal graph — this AP's RSSI over recent scans, sitting next to the RSSI number
            int8_t sp[ScanEngine::SPARK_N];
            int sc = e.sparkOf(r.bssid, sp);
            const int sx = 126, sw = 70, base = 19;   // continuous filled area, no gaps
            const uint16_t fillc = tft.color565(0x2a, 0x53, 0x48);
            if (sc >= 1) {
                for (int px = 0; px < sw; px++) {
                    float f = (sc <= 1) ? 0.0f : (float)px * (sc - 1) / (sw - 1);
                    int i0 = (int)f, i1 = (i0 + 1 < sc) ? i0 + 1 : i0;
                    int v = sp[i0] + (int)((sp[i1] - sp[i0]) * (f - i0));
                    int hh = map(constrain(v, -92, -40), -92, -40, 1, 14);
                    row.drawFastVLine(sx + px, base - hh, hh, fillc);
                    row.drawPixel(sx + px, base - hh, uiRssiColor(v));
                }
            }
            char b[8]; sprintf(b, "%d", r.rssi);      // signal, at the right edge
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, rbg);
            row.drawString(b, 238, 12);
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
