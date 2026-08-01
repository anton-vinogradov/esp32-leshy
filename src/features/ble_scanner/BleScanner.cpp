#include "BleScanner.h"

// Built-in Bluedroid BLE (part of the Arduino-ESP32 core) — chosen over
// NimBLE-Arduino, whose 1.4.x line boot-loops on core 3.x / IDF 5.x.
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
        BLEDevice::init("");
        inited_ = true;
    }
    return true;
}

int BleScanner::scan(uint32_t seconds) {
    begin();
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
    return count_;
}
