#include <Arduino.h>

#include "features/polite_portal/PolitePortal.h"

// TEMPORARY demo entry point for the PolitePortal feature. It will be replaced
// by the real menu/UI once the Phase 0 foundation lands.
//
// Point TARGET_SSID at YOUR OWN access point. Educational / own-equipment use
// only — see DISCLAIMER.md.
static const char* TARGET_SSID = "MyOwnAP";

PolitePortal portal;

void setup() {
    Serial.begin(115200);
    delay(300);

    PolitePortalConfig cfg;
    cfg.targetSsid = TARGET_SSID;
    cfg.portalSsid = "lower-your-wifi-power";
    cfg.rssiDropDb = 6;

    Serial.printf("[PolitePortal] measuring baseline for '%s'...\n", TARGET_SSID);
    if (!portal.begin(cfg)) {
        Serial.printf("[PolitePortal] target '%s' not found — check the SSID.\n", TARGET_SSID);
        return;
    }
    Serial.printf("[PolitePortal] up on the target's channel. baseline = %d dBm. "
                  "Join Wi-Fi '%s' and the page pops up.\n",
                  portal.baselineRssi(), cfg.portalSsid.c_str());
}

void loop() {
    portal.loop();
}
