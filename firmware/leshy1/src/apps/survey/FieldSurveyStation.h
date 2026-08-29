#pragma once

#include "apps/wifi/WifiDeviceCatalog.h"
#include "domain/observations/Observation.h"

namespace leshy1::apps::survey {

// Convert one already-passive 802.11 client observation into the common
// Survey record. No scan, association, probe or transmit action occurs here.
bool normalizeFieldSurveyStation(
    const apps::wifi::WifiDeviceObservation& station,
    domain::observations::Observation* output);

}  // namespace leshy1::apps::survey
