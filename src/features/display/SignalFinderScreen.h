#pragma once

#include "Display.h"                       // UI_VISIBLE, UI_ROW_H, shared helpers
#include "../scan/ScanEngine.h"
#include "../signal_finder/SignalFinder.h"

// SignalFinderScreen — pick a Wi-Fi target from the last scan, then a big
// "hot / cold" meter (RSSI number + bar + warmer/colder trend) to home in on it.
// The caller pauses ScanEngine before tracking (SignalFinder owns the radio).
class SignalFinderScreen {
public:
    // target picker
    void drawPicker(ScanEngine& e, int sel);   // full (header + rows + footer)
    void pickerRows(ScanEngine& e, int sel);   // rows only (on nav) — flicker-free
    int  pickerOffset(int sel) { return sel < UI_VISIBLE ? 0 : sel - UI_VISIBLE + 1; }
    bool ssidAt(ScanEngine& e, int idx, String& out);

    // tracking
    bool startTrack(const String& ssid);
    void drawTrackChrome();
    void updateTrack();                        // call every loop
    void stopTrack();

private:
    SignalFinder finder_;
    String  target_;
    int     lastRssi_  = -999;
    int     lastTrend_ = -999;
    void drawMeter(int rssi, int trend);
};
