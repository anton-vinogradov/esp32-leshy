#pragma once

#include "apps/wifi/WifiDeviceCatalog.h"
#include "domain/observations/Observation.h"

namespace leshy1::apps::survey {

// Convert one already-passive 802.11 client observation into the common
// Survey record. No scan, association, probe or transmit action occurs here.
bool normalizeFieldSurveyStation(
    const apps::wifi::WifiDeviceObservation& station,
    domain::observations::Observation* output);

// A monitor starting on channel 1 has covered all requested channels after
// at least channelCount - 1 successful hops. Extra hops are harmless: task
// scheduling can keep the bounded monitor alive long enough to start another
// sweep, and exact equality would falsely reject that valid coverage.
bool fieldSurveyStationSweepCovered(std::uint32_t channelHops,
                                    std::uint8_t channelCount,
                                    std::uint8_t sweepCount = 1U);

}  // namespace leshy1::apps::survey
