#pragma once

#include <Arduino.h>

// NetManager — join YOUR OWN Wi-Fi without a keyboard: provision credentials
// from a phone (SoftAP + captive portal), store them in NVS, and connect.
// On connect it learns the AP's BSSID and saves it, so the scanner can tag that
// network (even a hidden one) as "yours" (★). Own-network use only.
class NetManager {
public:
    void   begin();                       // load saved creds/own-BSSID from NVS
    bool   hasCreds();
    String savedSsid();

    bool   connect(uint32_t timeoutMs = 12000);  // connect with saved creds; learns & saves own BSSID
    bool   connected();
    String ip();
    void   disconnect();                  // drop the link, keep saved creds
    void   forget();                      // drop the link and erase saved creds

    // provisioning via phone captive portal
    void   startProvision();              // raise "ESP32-Leshy-setup" AP + portal
    void   loopProvision();               // service DNS/web (call each loop while provisioning)
    bool   pendingConnect();              // true once the user submitted creds
    void   stopProvision();

    // scan tagging
    bool   isMine(const uint8_t bssid[6], String& ssidOut);

    // Lab captive-portal AP name (set from the same phone provisioning form, saved to NVS)
    String labApName();

    static const char* apName() { return "ESP32-Leshy-setup"; }
};
