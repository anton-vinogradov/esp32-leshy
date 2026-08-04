#include "BleScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"
#include "../ble_scanner/BleScanner.h"

#include <stdio.h>

void BleScreen::rows(ScanEngine& e, int offset, int sel) {
    const uint16_t bg    = uiBg();
    const uint16_t selbg = tft.color565(0x22, 0x33, 0x22);   // highlighted row
    const uint16_t white = tft.color565(0xff, 0xff, 0xf2);   // brighter list text
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t cyan  = tft.color565(0x5a, 0xd0, 0xff);   // device-type tag
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);   // "pub" address flag

    TFT_eSprite& row = uiRow();
    int n = e.bleCount();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        uint16_t rbg = (idx == sel) ? selbg : bg;
        row.fillSprite(rbg);
        BleRow d;
        if (idx < n && e.bleRow(idx, d)) {
            uint16_t col = uiRssiColor(d.rssi);
            int x = 6;                                       // signal bars removed — the RSSI number on the right already shows strength
            const char* tag = "";                            // subtype (AirPods/iBeacon…) → category → brand; trackers use the amber label instead
            if (!d.tracker) {
                if (d.subtype.length()) tag = d.subtype.c_str();
                else { tag = bleKindLabel((BleKind)d.kind, i18n::isRu()); if (!tag[0] && d.vendor.length()) tag = d.vendor.c_str(); }
            }
            if (tag[0]) {                                    // guessed device type/brand, in cyan, using the freed-up left slot
                row.setTextDatum(ML_DATUM);
                row.setTextColor(cyan, rbg);
                row.drawString(tag, x, 12);
                x += row.textWidth(tag) + 8;
            }
            int rssiX = 232;
            if (d.pub) {                                     // public = fixed, trackable MAC — flag it (random/privacy shows nothing)
                row.setTextDatum(MR_DATUM);
                row.setTextColor(dim, rbg);
                row.drawString(i18n::tr("fixed", "фикс"), 204, 12);
                rssiX = 204;                                 // (kept for clarity; RSSI stays at 232)
            }
            String label = (d.tracker && d.label == "Find My") ? i18n::tr("Apple Find My", "Apple Локатор") : d.label;
            bool trunc = false;
            int maxw = (d.pub ? 178 : 206) - x;              // keep clear of the "фикс" flag / RSSI at the right
            while (label.length() > 3 && row.textWidth(label) > maxw) { label = label.substring(0, label.length() - 1); trunc = true; }
            if (trunc) label += "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(d.tracker ? amber : white, rbg);
            row.drawString(label, x, 12);
            char b[8];
            sprintf(b, "%d", d.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, rbg);
            row.drawString(b, 232, 12);
        }
        row.pushSprite(0, y);
    }
}

void BleScreen::draw(ScanEngine& e, int offset, int sel) {
    int n = e.bleCount();
    char right[24];
    if (n > 0) sprintf(right, "%d %s", n, i18n::tr("dev", "устр"));
    else       sprintf(right, "%s", i18n::tr("scanning", "скан"));
    uiHeaderRu("BLE", right);
    rows(e, offset, sel);
    uiFooterRu(i18n::isRu() ? "◀ меню" : "◀ menu", i18n::tr("OK radar", "OK радар"));
    fontOff();
}
