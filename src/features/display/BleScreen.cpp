#include "BleScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"

#include <stdio.h>

void BleScreen::rows(ScanEngine& e, int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xff, 0xff, 0xf2);   // brighter list text
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);

    TFT_eSprite& row = uiRow();
    int n = e.bleCount();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        row.fillSprite(bg);
        BleRow d;
        if (idx < n && e.bleRow(idx, d)) {
            uint16_t col = uiRssiColor(d.rssi);
            uiSignalBars(row, 6, 5, d.rssi, col);
            String label = d.label;
            if (label.length() > 16) label = label.substring(0, 15) + "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(d.tracker ? amber : white, bg);
            row.drawString(label, 34, 12, 2);
            char b[8];
            sprintf(b, "%d", d.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, bg);
            row.drawString(b, 232, 12, 2);
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
    uiFooterRu(i18n::isRu() ? "Влево: меню, листать" : "LEFT: menu, scroll");
    fontOff();
}
