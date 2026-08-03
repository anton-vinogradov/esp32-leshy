#include "BleScanner.h"

// Core's built-in BLE library (BLEDevice.h) — chosen over the external
// NimBLE-Arduino, whose 1.4.x line boot-loops on core 3.x / IDF 5.x. In this
// arduino-esp32 build the library is compiled on the NimBLE host (the core ships
// no Bluedroid variant), so all teardown goes through the backend-agnostic
// BLEDevice::deinit() rather than raw esp_bluedroid_*/esp_bt_* calls.
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>

// Recognize a few common trackers from advertising data. Heuristic — meant to
// surface "there is a tracker near you", not to be authoritative.
static String detectTracker(BLEAdvertisedDevice& d) {
    if (d.haveManufacturerData()) {
        String m = d.getManufacturerData();
        if (m.length() >= 3) {
            uint16_t company = (uint8_t)m[0] | ((uint16_t)(uint8_t)m[1] << 8);
            if (company == 0x004C && (uint8_t)m[2] == 0x12) return "Apple Find My";
            // Samsung SmartTag is matched by its 0xFD5A service below; a bare
            // company-id 0x0075 match would flag every Galaxy phone/buds/watch.
        }
    }
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFEED))) return "Tile";
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFD5A))) return "SmartTag";
    return "";
}

bool BleScanner::begin() {
    if (!inited_) {
        if (!BLEDevice::init("")) return false;   // e.g. RAM was handed to OTA — a reboot is needed before BLE works again
        inited_ = true;
    }
    return true;
}

// Hand the BLE stack (NimBLE host + BT controller) RAM back to the system heap so
// a memory-hungry job can get a large contiguous block. One-way: BLEDevice::deinit(true)
// calls btMemRelease(), so BLE can't be brought back up without a reboot — which is
// exactly the OTA download path (it always ends in ESP.restart()). Must be called
// only when the scan task is idle (nobody inside scan()).
bool BleScanner::releaseForOta() {
    if (!inited_) return false;      // BLE never came up this session → nothing to free
    BLEDevice::deinit(true);         // stop host + controller, release BT memory
    inited_ = false;
    return true;
}

int BleScanner::scan(uint32_t seconds) {
    if (!begin()) { count_ = 0; return 0; }   // BLE unavailable (released for OTA) — no devices, no crash
    BLEScan* scan = BLEDevice::getScan();
    scan->setActiveScan(true);
    scan->setInterval(100);
    scan->setWindow(99);

    BLEScanResults* results = scan->start(seconds, false);
    count_ = 0;
    int n = results ? results->getCount() : 0;
    for (int i = 0; i < n && count_ < MAX; i++) {
        BLEAdvertisedDevice d = results->getDevice(i);
        BleDev& b = devs_[count_];
        b.mac     = d.getAddress().toString();
        b.name    = d.haveName() ? d.getName() : String("");
        b.rssi    = d.getRSSI();
        b.tracker = detectTracker(d);
        count_++;
    }
    scan->clearResults();
    for (int i = 1; i < count_; i++) {          // strongest RSSI first (nearest device on top)
        BleDev key = devs_[i];
        int j = i - 1;
        while (j >= 0 && devs_[j].rssi < key.rssi) { devs_[j + 1] = devs_[j]; j--; }
        devs_[j + 1] = key;
    }
    return count_;
}
