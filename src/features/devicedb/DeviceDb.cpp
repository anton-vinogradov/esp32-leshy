#include "DeviceDb.h"

#include <LittleFS.h>
#include <string.h>

namespace {
    bool have_co = false, have_oui = false;
    const int REC = 32;                       // both blobs use 32-byte fixed records, sorted by key

    // Binary-search a sorted fixed-record blob for `key` (keyBytes at offset 0), return its name field.
    String lookup(const char* path, int keyBytes, bool littleEndian, uint32_t key, int nameOff, int nameLen) {
        File f = LittleFS.open(path, "r");
        if (!f) return "";
        long lo = 0, hi = (long)(f.size() / REC) - 1;
        uint8_t buf[REC];
        while (lo <= hi) {
            long mid = (lo + hi) / 2;
            if (!f.seek((uint32_t)mid * REC) || f.read(buf, REC) != REC) break;
            uint32_t k = 0;
            if (littleEndian) for (int i = keyBytes - 1; i >= 0; i--) k = (k << 8) | buf[i];
            else              for (int i = 0; i < keyBytes; i++)      k = (k << 8) | buf[i];
            if (k == key) {
                f.close();
                char nm[REC];
                memcpy(nm, buf + nameOff, nameLen); nm[nameLen] = 0;   // name is null-padded in the blob
                return String(nm);
            }
            if (k < key) lo = mid + 1; else hi = mid - 1;
        }
        f.close();
        return "";
    }
}

void DeviceDb::begin() {
    if (!LittleFS.begin(true)) return;        // ensure mounted (the recorder may already have)
    have_co  = LittleFS.exists("/btco.bin");
    have_oui = LittleFS.exists("/oui.bin");
}

bool DeviceDb::present() { return have_co || have_oui; }

String DeviceDb::companyName(uint16_t code) {
    if (!have_co) return "";
    return lookup("/btco.bin", 2, true, code, 2, 30);      // u16 LE key, char[30] name
}

String DeviceDb::ouiName(const uint8_t mac[6]) {
    if (!have_oui) return "";
    uint32_t key = ((uint32_t)mac[0] << 16) | ((uint32_t)mac[1] << 8) | mac[2];
    return lookup("/oui.bin", 3, false, key, 3, 29);       // u24 BE key, char[29] name
}
