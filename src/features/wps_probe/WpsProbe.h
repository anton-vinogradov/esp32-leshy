#pragma once

#include <Arduino.h>

// WpsProbe — read an access point's self-reported maker/model from the WPS
// Information Element in its beacon. WPS (when enabled) carries Manufacturer /
// Model Name / Model Number in cleartext; many home routers advertise it,
// hardened/enterprise APs strip it. Not a database — parsed live from the air.
//
// Blocking: briefly goes promiscuous on the AP's channel and listens for its
// beacon. The caller must own the radio (pause the scan engine first).
namespace WpsProbe {
    // Fills manuf/model from `bssid`'s WPS IE within `ms`. Either may stay empty.
    // Returns true if anything was found. Manages promiscuous itself.
    bool probe(const uint8_t bssid[6], uint8_t channel, uint32_t ms, String& manuf, String& model);
}
