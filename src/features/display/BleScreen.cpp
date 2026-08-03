#include "BleScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"
#include "../ble_scanner/BleScanner.h"

#include <stdio.h>

void BleScreen::rows(ScanEngine& e, int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xff, 0xff, 0xf2);   // brighter list text
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t cyan  = tft.color565(0x5a, 0xd0, 0xff);   // device-type tag

    TFT_eSprite& row = uiRow();
    int n = e.bleCount();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        row.fillSprite(bg);
        BleRow d;
        if (idx < n && e.bleRow(idx, d)) {
            uint16_t col = uiRssiColor(d.rssi);
            int x = 6;                                       // signal bars removed — the RSSI number on the right already shows strength
            const char* tag = bleKindLabel((BleKind)d.kind, i18n::isRu());
            if (!tag[0] && !d.tracker && d.vendor.length()) tag = d.vendor.c_str();   // no category → fall back to the brand
            if (tag[0]) {                                    // guessed device type/brand, in cyan, using the freed-up left slot
                row.setTextDatum(ML_DATUM);
                row.setTextColor(cyan, bg);
                row.drawString(tag, x, 12);
                x += row.textWidth(tag) + 8;
            }
            String label = d.label;
            bool trunc = false;
            int maxw = 206 - x;                              // keep clear of the RSSI number at the right edge
            while (label.length() > 3 && row.textWidth(label) > maxw) { label = label.substring(0, label.length() - 1); trunc = true; }
            if (trunc) label += "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(d.tracker ? amber : white, bg);
            row.drawString(label, x, 12);
            char b[8];
            sprintf(b, "%d", d.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, bg);
            row.drawString(b, 232, 12);
        }
        row.pushSprite(0, y);
    }
}

void BleScreen::draw(ScanEngine& e, int offset) {
    int n = e.bleCount();
    char right[24];
    if (n > 0) sprintf(right, "%d %s", n, i18n::tr("dev", "устр"));
    else       sprintf(right, "%s", i18n::tr("scanning", "скан"));
    uiHeaderRu("BLE", right);
    rows(e, offset);
    uiFooterRu(i18n::isRu() ? "◀ меню" : "◀ menu");
    fontOff();
}
