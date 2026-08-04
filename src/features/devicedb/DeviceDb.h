#pragma once

#include <Arduino.h>

// DeviceDb — optional on-device maker lookup from reference blobs on LittleFS:
//   /btco.bin  BLE SIG company IDs   (works on any advertiser, incl. random-MAC)
//   /oui.bin   IEEE MA-L OUIs        (MAC prefix — WiFi APs/clients + public BLE)
// Fully OPTIONAL: if a blob isn't flashed (data/ not uploaded), the matching
// lookup returns "" and callers fall back to the built-in short vendor list. The
// firmware binary is complete and works without any of this.
namespace DeviceDb {
    void   begin();                          // note which blobs are present (LittleFS must be mounted)
    bool   present();                        // any blob available
    String companyName(uint16_t code);       // BLE company ID  -> maker, "" if unknown / no blob
    String ouiName(const uint8_t mac[6]);    // MAC OUI (bytes 0..2) -> maker, "" if unknown / no blob
}
