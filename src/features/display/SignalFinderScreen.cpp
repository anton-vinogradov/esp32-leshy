#include "SignalFinderScreen.h"

#include "Display.h"

#include <stdio.h>

void SignalFinderScreen::pickerRows(ScanEngine& e, int sel) {
    const uint16_t bg    = uiBg();
    const uint16_t selbg = tft.color565(0x24, 0x40, 0x2c);
    const uint16_t white = tft.color565(0xe8, 0xe8, 0xe0);
    const uint16_t gold  = tft.color565(0xff, 0xe6, 0xa8);

    TFT_eSprite& row = uiRow();
    int n = e.wifiCount();
    int off = pickerOffset(sel);

    for (int i = 0; i < UI_VISIBLE; i++) {
        int idx = off + i;
        int y = UI_LIST_TOP + i * UI_ROW_H;
        bool s = (idx == sel);
        uint16_t rb = s ? selbg : bg;
        row.fillSprite(rb);
        WifiRow r;
        if (idx < n && e.wifiRow(idx, r)) {
            uint16_t col = uiRssiColor(r.rssi);
            uiSignalBars(row, 6, 5, r.rssi, col);
            String ss = r.ssid.length() ? r.ssid : String("<hidden>");
            if (ss.length() > 16) ss = ss.substring(0, 15) + "~";
            row.setTextDatum(ML_DATUM);
            row.setTextColor(s ? gold : white, rb);
            row.drawString(ss, 34, 12, 2);
            char b[8];
            sprintf(b, "%d", r.rssi);
            row.setTextDatum(MR_DATUM);
            row.setTextColor(col, rb);
            row.drawString(b, 232, 12, 2);
        }
        row.pushSprite(0, y);
    }
}

void SignalFinderScreen::drawPicker(ScanEngine& e, int sel) {
    uiHeader("Pick target", "");
    pickerRows(e, sel);
    uiFooter("SEL/tap: pick   LEFT: menu");
}

bool SignalFinderScreen::ssidAt(ScanEngine& e, int idx, String& out) {
    WifiRow r;
    if (e.wifiRow(idx, r) && r.ssid.length()) { out = r.ssid; return true; }
    return false;   // hidden / empty SSID can't be targeted by name
}

bool SignalFinderScreen::startTrack(const String& ssid) {
    target_ = ssid;
    lastRssi_ = -999;
    lastTrend_ = -999;
    SignalFinderConfig cfg;
    cfg.targetSsid = ssid;
    return finder_.begin(cfg);
}

void SignalFinderScreen::drawTrackChrome() {
    uiHeader("Signal Finder", "");
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(tft.color565(0xe7, 0xcf, 0x8f), uiBg());
    String t = target_.length() > 18 ? target_.substring(0, 17) + "~" : target_;
    tft.drawString(t, 120, 58, 4);
    uiFooter("LEFT: back");
    drawMeter(finder_.reading(), finder_.trend());
}

void SignalFinderScreen::drawMeter(int rssi, int trend) {
    const uint16_t bg = uiBg();
    uint16_t col = (rssi <= -127) ? tft.color565(0x8f, 0xa9, 0x8f) : uiRssiColor(rssi);

    // big RSSI number
    tft.fillRect(0, 104, 240, 78, bg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(col, bg);
    if (rssi <= -127) {
        tft.drawString("--", 120, 140, 6);
    } else {
        char b[8];
        sprintf(b, "%d", rssi);
        tft.drawString(b, 120, 138, 6);
        tft.setTextColor(tft.color565(0x9a, 0xac, 0x9a), bg);
        tft.drawString("dBm", 120, 176, 2);
    }

    // strength bar (-90 far .. -40 near)
    const int bx = 20, by = 208, bw = 200, bh = 26;
    tft.drawRect(bx - 1, by - 1, bw + 2, bh + 2, tft.color565(0x50, 0x60, 0x50));
    tft.fillRect(bx, by, bw, bh, bg);
    if (rssi > -127) {
        int pct = constrain((int)map(rssi, -90, -40, 0, bw), 0, bw);
        tft.fillRect(bx, by, pct, bh, col);
    }

    // trend
    tft.fillRect(0, 250, 240, 42, bg);
    tft.setTextDatum(MC_DATUM);
    if (rssi <= -127) {
        tft.setTextColor(tft.color565(0x8f, 0xa9, 0x8f), bg);
        tft.drawString("searching...", 120, 268, 4);
    } else if (trend > 1) {
        tft.setTextColor(tft.color565(0x4c, 0xd1, 0x64), bg);
        tft.drawString("WARMER", 120, 268, 4);
    } else if (trend < -1) {
        tft.setTextColor(tft.color565(0xd1, 0x4c, 0x4c), bg);
        tft.drawString("colder", 120, 268, 4);
    } else {
        tft.setTextColor(tft.color565(0x9a, 0xac, 0x9a), bg);
        tft.drawString("steady", 120, 268, 4);
    }
}

void SignalFinderScreen::updateTrack() {
    finder_.loop();
    int r = finder_.reading();
    int tr = finder_.trend();
    if (r != lastRssi_ || tr != lastTrend_) {
        lastRssi_ = r;
        lastTrend_ = tr;
        drawMeter(r, tr);
    }
}

void SignalFinderScreen::stopTrack() {
    finder_.stop();
}
