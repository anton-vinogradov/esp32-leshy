#include <cstdlib>
#include <iostream>

#include "apps/targets/TargetRadar.h"

using leshy1::apps::targets::TargetRadar;
using leshy1::apps::targets::TargetRadarIngestStatus;
using leshy1::apps::targets::TargetRadarStatus;
using leshy1::domain::observations::Observation;
using leshy1::domain::observations::RadioKind;
using leshy1::domain::observations::WifiObservationKind;
using leshy1::domain::targets::TargetIdentityKind;
using leshy1::domain::targets::TargetRecord;

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::cerr << "CHECK failed at " << __FILE__ << ':' << __LINE__  \
                      << ": " #condition << '\n';                           \
            std::exit(1);                                                    \
        }                                                                    \
    } while (false)

TargetRecord target() {
    TargetRecord value{};
    value.id.bytes[0] = 1U;
    value.revision = 1U;
    value.identityCount = 3U;
    value.identities[0].kind = TargetIdentityKind::WifiBssid;
    value.identities[0].length = 6U;
    value.identities[0].value = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60};
    value.identities[1].kind = TargetIdentityKind::BleAddress;
    value.identities[1].length = 6U;
    value.identities[1].discriminator = 1U;
    value.identities[1].value = {1, 2, 3, 4, 5, 6};
    value.identities[2].kind = TargetIdentityKind::WifiStation;
    value.identities[2].length = 6U;
    value.identities[2].value = {6, 5, 4, 3, 2, 1};
    return value;
}

Observation wifi(std::uint64_t at, std::int16_t rssi) {
    Observation value{};
    value.monotonicUs = at;
    value.radio = RadioKind::Wifi;
    value.wifiKind = WifiObservationKind::AccessPoint;
    value.channel = 6U;
    value.rssiDbm = rssi;
    value.identityLength = 6U;
    value.identity = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60};
    return value;
}

Observation ble(std::uint64_t at, std::int16_t rssi,
                std::uint8_t addressType = 1U) {
    Observation value{};
    value.monotonicUs = at;
    value.radio = RadioKind::Ble;
    value.rssiDbm = rssi;
    value.identityLength = 6U;
    value.identity = {1, 2, 3, 4, 5, 6};
    value.bleAdvertisement.present = true;
    value.bleAdvertisement.addressType = addressType;
    return value;
}

int main() {
    TargetRadar radar;
    CHECK(radar.begin(target(), false));
    CHECK(radar.snapshot().status == TargetRadarStatus::Partial);
    CHECK(radar.snapshot().identityCount == 3U);
    CHECK(radar.snapshot().supportedIdentityCount == 2U);
    CHECK(!radar.snapshot().wifiStationSupported);

    CHECK(radar.ingest(wifi(100U, -70)) ==
          TargetRadarIngestStatus::Matched);
    CHECK(radar.ingest(wifi(200U, -61)) ==
          TargetRadarIngestStatus::Matched);
    const auto& wifiSignal = radar.snapshot().signals[0];
    CHECK(wifiSignal.samples == 2U);
    CHECK(wifiSignal.rssiDbm == -61);
    CHECK(wifiSignal.minimumRssiDbm == -70);
    CHECK(wifiSignal.maximumRssiDbm == -61);
    CHECK(wifiSignal.trendDb == 9);
    CHECK(wifiSignal.channel == 6U);

    CHECK(radar.ingest(wifi(200U, -20)) == TargetRadarIngestStatus::Stale);
    CHECK(radar.snapshot().signals[0].rssiDbm == -61);
    CHECK(radar.snapshot().stale == 1U);

    CHECK(radar.ingest(ble(300U, -55, 0U)) ==
          TargetRadarIngestStatus::Unmatched);
    CHECK(radar.ingest(ble(400U, -54)) ==
          TargetRadarIngestStatus::Matched);
    CHECK(radar.snapshot().samples == 3U);
    CHECK(radar.snapshot().wifiSamples == 2U);
    CHECK(radar.snapshot().bleSamples == 1U);
    CHECK(radar.snapshot().matchedIdentityIndex == 1U);

    Observation station{};
    station.monotonicUs = 500U;
    station.radio = RadioKind::Wifi;
    station.wifiKind = WifiObservationKind::Station;
    station.channel = 11U;
    station.rssiDbm = -40;
    station.identityLength = 6U;
    station.identity = {6, 5, 4, 3, 2, 1};
    CHECK(radar.ingest(station) == TargetRadarIngestStatus::Unmatched);

    radar.stop();
    CHECK(radar.snapshot().status == TargetRadarStatus::Stopped);
    CHECK(radar.ingest(wifi(600U, -50)) ==
          TargetRadarIngestStatus::InvalidArgument);

    CHECK(radar.begin(target(), true));
    CHECK(radar.snapshot().status == TargetRadarStatus::Waiting);
    CHECK(radar.ingest(station) == TargetRadarIngestStatus::Matched);
    CHECK(radar.snapshot().status == TargetRadarStatus::Tracking);

    TargetRecord invalid{};
    CHECK(!radar.begin(invalid, false));
    CHECK(radar.snapshot().status == TargetRadarStatus::Idle);

    std::cout << "target_radar_tests: ok\n";
    return 0;
}
