#include "BleScreen.h"

#include "Display.h"

#include <stdio.h>

static const int VISIBLE = 12;

void BleScreen::scanCue() {
    uiHeader("BLE", "scanning");
}

int BleScreen::scan() {
    return ble_.scan(4);
}

void BleScreen::render(int offset) {
    const uint16_t bg    = uiBg();
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);

    char right[16];
    sprintf(right, "%d dev", ble_.count());
    uiHeader("BLE", right);
    tft.fillRect(0, 28, 240, 306 - 28, bg);

    int n = ble_.count();
    for (int i = 0; i < VISIBLE; i++) {
        int idx = offset + i;
        if (idx >= n) break;
        const BleDev& d = ble_.at(idx);
        int y = 32 + i * 23;
        uint16_t col = uiRssiColor(d.rssi);

        uiSignalBars(6, y, d.rssi, col);

        // name, or the tracker label (amber) if flagged, else the MAC
        String label;
        uint16_t labelCol = white;
        if (d.tracker.length()) { label = d.tracker; labelCol = amber; }
        else if (d.name.length()) { label = d.name; }
        else { label = d.mac; }
        if (label.length() > 16) label = label.substring(0, 15) + "~";
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(labelCol, bg);
        tft.drawString(label, 34, y + 8, 2);

        char r[8];
        sprintf(r, "%d", d.rssi);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(col, bg);
        tft.drawString(r, 232, y + 8, 2);
    }

    uiFooter("SEL: Wi-Fi   UP/DN: scroll");
}
