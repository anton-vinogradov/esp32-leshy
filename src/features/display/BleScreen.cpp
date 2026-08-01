#include "BleScreen.h"

#include "Display.h"

#include <stdio.h>

void BleScreen::scanCue() {
    uiHeader("BLE", "scanning");
}

int BleScreen::scan() {
    return ble_.scan(4);
}

void BleScreen::rows(int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);

    TFT_eSprite& row = uiRow();
    int n = ble_.count();

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = offset + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        row.fillSprite(bg);
        if (idx < n) {
            const BleDev& d = ble_.at(idx);
            uint16_t col = uiRssiColor(d.rssi);
            uiSignalBars(row, 6, 5, d.rssi, col);

            String label = d.tracker.length() ? d.tracker
                         : d.name.length()    ? d.name
                                              : d.mac;
            uint16_t labelCol = d.tracker.length() ? amber : white;
            if (label.length() > 16) label = label.substring(0, 15) + "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(labelCol, bg);
            row.drawString(label, 34, 12, 2);

            char r[8];
            sprintf(r, "%d", d.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, bg);
            row.drawString(r, 232, 12, 2);
        }
        row.pushSprite(0, y);
    }
}

void BleScreen::draw(int offset) {
    char right[16];
    sprintf(right, "%d dev", ble_.count());
    uiHeader("BLE", right);
    rows(offset);
    uiFooter("SEL: Wi-Fi   UP/DN: scroll");
}
