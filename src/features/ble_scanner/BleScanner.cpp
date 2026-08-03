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
            if (company == 0x004C && (uint8_t)m[2] == 0x12) return "Find My";   // AirTag / offline Apple device (localized "Локатор" at display)
            // Samsung SmartTag is matched by its 0xFD5A service below; a bare
            // company-id 0x0075 match would flag every Galaxy phone/buds/watch.
        }
    }
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFEED))) return "Tile";
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFD5A))) return "SmartTag";
    return "";
}

// Guess the device category from advertising data. Order = most reliable first:
// the standard GAP Appearance code, then well-known service UUIDs, then name text.
static BleKind classifyKind(BLEAdvertisedDevice& d) {
    if (d.haveAppearance()) {
        uint16_t a = d.getAppearance();
        switch (a >> 6) {                                  // upper 10 bits = category
            case 0x01: return BK_PHONE;                    // 0x0040 Phone
            case 0x02: return BK_PC;                       // 0x0080 Computer
            case 0x03: return BK_WATCH;                    // 0x00C0 Watch
            case 0x05: return BK_TV;                       // 0x0140 Display
            case 0x08: return BK_TAG;                      // 0x0200 Tag
            case 0x0C: return BK_THERMO;                   // 0x0300 Thermometer
            case 0x0D: return BK_HEART;                    // 0x0340 Heart Rate
            case 0x0F: switch (a & 0x3F) { case 1: return BK_KBD; case 2: return BK_MOUSE; default: return BK_HID; }  // 0x03C0 HID
            case 0x11: case 0x12: return BK_FITNESS;       // 0x0440 Running/Walking, 0x0480 Cycling
            case 0x25: return BK_AUDIO;                    // 0x0940 Audio (earbuds/headset)
        }
    }
    if (d.isAdvertisingService(BLEUUID((uint16_t)0x1812))) return BK_HID;      // Human Interface Device
    if (d.isAdvertisingService(BLEUUID((uint16_t)0x180D))) return BK_HEART;    // Heart Rate
    if (d.isAdvertisingService(BLEUUID((uint16_t)0x1809))) return BK_THERMO;   // Health Thermometer
    if (d.isAdvertisingService(BLEUUID((uint16_t)0x1826))) return BK_FITNESS;  // Fitness Machine
    if (d.haveName()) {
        String n = d.getName(); n.toLowerCase();
        if (n.indexOf("airpod") >= 0 || n.indexOf("buds") >= 0 || n.indexOf("headphone") >= 0 || n.indexOf("headset") >= 0
            || n.indexOf("wf-") >= 0 || n.indexOf("wh-") >= 0 || n.indexOf("jbl") >= 0 || n.indexOf("beats") >= 0) return BK_AUDIO;
        if (n.indexOf("watch") >= 0 || n.indexOf("band") >= 0 || n.indexOf("amazfit") >= 0 || n.indexOf("fitbit") >= 0
            || n.indexOf("gtr") >= 0 || n.indexOf("gts") >= 0 || n.indexOf("versa") >= 0) return BK_WATCH;
        if (n.indexOf("keyboard") >= 0) return BK_KBD;
        if (n.indexOf("mouse")    >= 0) return BK_MOUSE;
        if (n.indexOf("tv") >= 0 || n.indexOf("bravia") >= 0) return BK_TV;
        if (n.indexOf("lywsd") >= 0 || n.indexOf("atc_") >= 0 || n.indexOf("thermo") >= 0) return BK_THERMO;   // Xiaomi Mijia sensors
        if (n.indexOf("iphone") >= 0 || n.indexOf("galaxy") >= 0 || n.indexOf("phone") >= 0
            || n.indexOf("pixel") >= 0 || n.indexOf("redmi") >= 0 || n.indexOf("poco") >= 0) return BK_PHONE;
    }
    return BK_NONE;
}

// Brand from the manufacturer company-ID (advertised even by privacy-random-MAC
// phones) or a vendor-specific service UUID. A weaker hint than kind, so it's only
// shown when the category is unknown — but it lights up the anonymous MAC list.
static String classifyVendor(BLEAdvertisedDevice& d) {
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFE95))) return "Xiaomi";   // MiBeacon
    if (d.haveManufacturerData()) {
        String m = d.getManufacturerData();
        if (m.length() >= 2) {
            uint16_t c = (uint8_t)m[0] | ((uint16_t)(uint8_t)m[1] << 8);
            switch (c) {
                case 0x004C: return "Apple";
                case 0x0075: return "Samsung";
                case 0x0006: return "Microsoft";
                case 0x00E0: return "Google";
                case 0x009E: return "Bose";
                case 0x0087: return "Garmin";
                case 0x012D: return "Sony";
                case 0x038F: return "Xiaomi";
                case 0x0157: return "Amazfit";
                case 0x02E5: return "Espressif";
                case 0x0059: return "Nordic";
            }
        }
    }
    return "";
}

// A more specific decode than the vendor: Apple Continuity message type tells AirPods
// from an AirTag from an iBeacon; Eddystone is a service-data beacon. Proper nouns, not
// localized.
static String classifySubtype(BLEAdvertisedDevice& d) {
    if (d.haveManufacturerData()) {
        String m = d.getManufacturerData();
        if (m.length() >= 3 && (uint8_t)m[0] == 0x4C && (uint8_t)m[1] == 0x00) {
            switch ((uint8_t)m[2]) {                 // Apple Continuity message type
                case 0x02: return "iBeacon";
                case 0x05: return "AirDrop";
                case 0x07: return "AirPods";
                case 0x09: case 0x0A: return "AirPlay";
                case 0x0C: return "Handoff";
                case 0x0D: case 0x0E: return "Hotspot";
                case 0x12: return "Find My";
            }
        }
    }
    if (d.isAdvertisingService(BLEUUID((uint16_t)0xFEAA))) return "Eddystone";
    return "";
}

// First advertised service, decoded to a friendly name (else its raw 0xUUID).
static String svcName(BLEAdvertisedDevice& d) {
    if (!d.haveServiceUUID()) return "";
    static const struct { uint16_t id; const char* n; } known[] = {
        {0x1812, "HID"}, {0x180F, "Battery"}, {0x180D, "Heart Rate"}, {0x1809, "Thermometer"},
        {0x1826, "Fitness"}, {0xFEAA, "Eddystone"}, {0xFE95, "Xiaomi"}, {0xFD5A, "SmartTag"},
        {0xFEED, "Tile"}, {0xFE9F, "Fast Pair"}, {0xFD6F, "Exposure Ntf"},
    };
    for (auto& k : known) if (d.isAdvertisingService(BLEUUID(k.id))) return k.n;
    String s = d.getServiceUUID().toString();
    return s.length() > 10 ? String("0x") + s.substring(4, 8) : s;   // 128-bit → the 16-bit slice
}

const char* bleKindLabel(BleKind k, bool ru) {
    switch (k) {
        case BK_PHONE:   return ru ? "телефон" : "phone";
        case BK_PC:      return ru ? "комп"    : "pc";
        case BK_WATCH:   return ru ? "часы"    : "watch";
        case BK_AUDIO:   return ru ? "аудио"   : "audio";
        case BK_KBD:     return ru ? "клава"   : "kbd";
        case BK_MOUSE:   return ru ? "мышь"    : "mouse";
        case BK_HID:     return ru ? "ввод"    : "hid";
        case BK_HEART:   return ru ? "пульс"   : "heart";
        case BK_THERMO:  return ru ? "термо"   : "thermo";
        case BK_TAG:     return ru ? "метка"   : "tag";
        case BK_TV:      return ru ? "экран"   : "display";
        case BK_FITNESS: return ru ? "фитнес"  : "fitness";
        default:         return "";
    }
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
    scan->setAdvertisedDeviceCallbacks(nullptr);   // drop any radar callback so a normal list scan isn't affected
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
        b.kind    = classifyKind(d);
        b.vendor  = classifyVendor(d);
        b.pub     = (d.getAddressType() == BLE_ADDR_PUBLIC);
        b.subtype = classifySubtype(d);
        b.appearance = d.haveAppearance() ? d.getAppearance() : 0;
        b.txpwr   = d.haveTXPower() ? (int)(int8_t)d.getTXPower() : 127;
        b.svc     = svcName(d);
        { String mm = d.haveManufacturerData() ? d.getManufacturerData() : String();
          b.company = mm.length() >= 2 ? ((uint8_t)mm[0] | ((uint16_t)(uint8_t)mm[1] << 8)) : 0; }
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

void BleScanner::radarOnAd(BLEAdvertisedDevice& d) {
    if (radarMac_.length() && d.getAddress().toString() == radarMac_) {
        radarRssi_   = d.getRSSI();
        radarSeenMs_ = millis();
    }
}

// Live single-target window: duplicates ON so the target's RSSI updates on every ad,
// not just once. The callback runs during scan->start() and pokes radarOnAd().
class RadarCB : public BLEAdvertisedDeviceCallbacks {
    BleScanner* s_;
public:
    explicit RadarCB(BleScanner* s) : s_(s) {}
    void onResult(BLEAdvertisedDevice d) override { s_->radarOnAd(d); }
};

void BleScanner::radarScan(uint32_t seconds) {
    if (!begin()) return;
    static RadarCB cb(this);
    BLEScan* scan = BLEDevice::getScan();
    scan->setActiveScan(true);
    scan->setInterval(60);
    scan->setWindow(50);
    scan->setAdvertisedDeviceCallbacks(&cb, true);   // wantDuplicates = live RSSI
    scan->start(seconds, false);
    scan->clearResults();
}
