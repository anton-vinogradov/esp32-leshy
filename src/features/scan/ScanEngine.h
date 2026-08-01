#pragma once

#include <Arduino.h>

#include "../wifi_scanner/WifiScanner.h"
#include "../ble_scanner/BleScanner.h"

// Render-ready snapshot rows (decoupled from the scanner internals).
struct WifiRow { String ssid; int8_t rssi; uint8_t auth; uint8_t bssid[6]; };
struct BleRow  { String label; int rssi; bool tracker; };

// ScanEngine runs Wi-Fi and BLE scans in a background FreeRTOS task (pinned to
// the other core) and publishes results under a mutex. The UI thread reads
// snapshots and never blocks on a scan — so navigation stays smooth.
class ScanEngine {
public:
    enum ScanMode { SCAN_BOTH, SCAN_WIFI, SCAN_BLE };

    void begin();                        // start the background scan task
    void pause();                        // stop scanning and release the radio (blocks until idle)
    void resume();                       // resume background scanning
    void setMode(ScanMode m) { mode_ = m; }   // WIFI = refresh Wi-Fi fast (skip BLE)

    int  wifiCount();
    bool wifiRow(int i, WifiRow& out);
    int  bleCount();
    bool bleRow(int i, BleRow& out);

    uint32_t wifiGen() const { return wifiGen_; }   // bumped on each new Wi-Fi snapshot
    uint32_t bleGen()  const { return bleGen_; }

    void taskLoop();                     // internal (runs in the task)

private:
    static const int MAX = 48;
    WifiRow wifi_[MAX]; int wifiN_ = 0;
    BleRow  ble_[MAX];  int bleN_  = 0;
    volatile uint32_t wifiGen_ = 0, bleGen_ = 0;
    volatile bool paused_ = true;        // start idle — scanning begins only on a scan screen
    volatile bool idle_ = false;         // true when the task is paused and not scanning
    volatile ScanMode mode_ = SCAN_BOTH;
    SemaphoreHandle_t mtx_ = nullptr;
    WifiScanner ws_;
    BleScanner  bs_;
};
