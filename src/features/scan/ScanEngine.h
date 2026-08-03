#pragma once

#include <Arduino.h>

#include "../wifi_scanner/WifiScanner.h"
#include "../wifi_scanner/HiddenRevealer.h"
#include "../ble_scanner/BleScanner.h"

// Render-ready snapshot rows (decoupled from the scanner internals).
// hidden = the AP broadcast an empty SSID; ssid may still be filled from a
// revealed name (HiddenRevealer) or the user's own saved name.
struct WifiRow { String ssid; int8_t rssi; uint8_t auth; uint8_t channel; uint8_t bssid[6]; bool hidden; };
struct BleRow  { String label; int rssi; bool tracker; uint8_t kind; String vendor; String mac; bool pub; };   // kind = BleKind; vendor = brand; mac = radar target; pub = fixed/trackable address

// ScanEngine runs Wi-Fi and BLE scans in a background FreeRTOS task (pinned to
// the other core) and publishes results under a mutex. The UI thread reads
// snapshots and never blocks on a scan — so navigation stays smooth.
class ScanEngine {
public:
    enum ScanMode { SCAN_BOTH, SCAN_WIFI, SCAN_BLE, SCAN_BLE_RADAR };

    void begin();                        // start the background scan task
    void pause();                        // ask the task to stop scanning (returns immediately)
    bool pauseAndWait(uint32_t timeoutMs = 6000);  // pause AND wait until the radio is really free
    bool isIdle() const { return idle_; }
    void resume();                       // resume background scanning
    bool releaseBleForOta();             // free BLE RAM for the OTA download — call ONLY after pauseAndWait() (scan task idle)
    void setMode(ScanMode m) { mode_ = m; }   // WIFI = refresh Wi-Fi fast (skip BLE)
    void attachRevealer(HiddenRevealer* r) { rev_ = r; }   // passively reveal hidden SSIDs

    static const int SPARK_N = 20;       // per-AP RSSI history length (sparkline)
    int  wifiCount();
    bool wifiRow(int i, WifiRow& out);
    int  sparkOf(const uint8_t bssid[6], int8_t* out);   // fills out[0..n-1] oldest->newest, returns n
    void clearSparks();                  // drop per-AP RSSI history — a fresh scan session builds a live graph, not a stale one
    int  bleCount();
    bool bleRow(int i, BleRow& out);

    // Radar (find-one-device): set SCAN_BLE_RADAR mode + target, then poll the live RSSI.
    void     setRadarTarget(const String& mac) { bs_.radarSetTarget(mac); }
    int      radarRssi()     { return bs_.radarRssi(); }
    uint32_t radarLastSeen() { return bs_.radarLastSeen(); }

    uint32_t wifiGen() const { return wifiGen_; }   // bumped on each new Wi-Fi snapshot
    uint32_t bleGen()  const { return bleGen_; }

    void taskLoop();                     // internal (runs in the task)

private:
    void revealHidden();                 // sniff hidden-AP channels for their names
    void pushSpark(const uint8_t bssid[6], int8_t rssi);  // append to a BSSID's RSSI history (mtx held)
    struct Spark { uint8_t bssid[6]; int8_t v[SPARK_N]; uint8_t n; };
    static const int MAX = 48;
    WifiRow wifi_[MAX]; int wifiN_ = 0;
    BleRow  ble_[MAX];  int bleN_  = 0;
    Spark   spark_[MAX]; int sparkN_ = 0;
    volatile uint32_t wifiGen_ = 0, bleGen_ = 0;
    volatile bool paused_ = true;        // start idle — scanning begins only on a scan screen
    volatile bool idle_ = false;         // true when the task is paused and not scanning
    volatile ScanMode mode_ = SCAN_BOTH;
    SemaphoreHandle_t mtx_ = nullptr;
    WifiScanner    ws_;
    BleScanner     bs_;
    HiddenRevealer* rev_ = nullptr;
};
