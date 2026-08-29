#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "apps/survey/FieldSurveyCatalog.h"
#include "apps/survey/FieldSurveyTracker.h"
#include "apps/survey/FieldSurveyWigleCsv.h"
#include "services/survey/SurveySession.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::apps::survey;
using namespace leshy1::domain::observations;
using namespace leshy1::services::survey;

Observation observation(
    RadioKind radio, std::array<std::uint8_t, 6> identity,
    std::uint64_t monotonicUs, std::int16_t rssiDbm, const char* label) {
    Observation value;
    value.radio = radio;
    value.identity = identity;
    value.identityLength = static_cast<std::uint8_t>(value.identity.size());
    value.monotonicUs = monotonicUs;
    value.rssiDbm = rssiDbm;
    if (label != nullptr) {
        const std::size_t length = std::strlen(label);
        CHECK(length <= Observation::kLabelCapacity);
        std::memcpy(value.label.data(), label, length);
        value.labelLength = static_cast<std::uint8_t>(length);
    }
    return value;
}

Observation accessPoint(std::array<std::uint8_t, 6> identity,
                        std::uint64_t monotonicUs, std::int16_t rssiDbm,
                        const char* label) {
    Observation value = observation(
        RadioKind::Wifi, identity, monotonicUs, rssiDbm, label);
    value.channel = 6U;
    value.frequencyKhz = 2437000U;
    value.wifiNetwork.present = true;
    value.wifiNetwork.authentication = WifiAuthentication::Wpa2Psk;
    value.wifiNetwork.pairwiseCipher = WifiCipher::Ccmp;
    value.wifiNetwork.groupCipher = WifiCipher::Ccmp;
    return value;
}

Observation bleDevice(std::array<std::uint8_t, 6> identity,
                      std::uint64_t monotonicUs, std::int16_t rssiDbm,
                      const char* label) {
    Observation value = observation(
        RadioKind::Ble, identity, monotonicUs, rssiDbm, label);
    value.bleAdvertisement.present = true;
    value.bleAdvertisement.companyKnown = true;
    value.bleAdvertisement.companyId = 0x004cU;
    return value;
}

void testCatalogDeduplicatesAndComparesVisits() {
    constexpr std::array<std::uint8_t, 6> kAp{
        0xa0U, 0xb1U, 0xc2U, 0xd3U, 0xe4U, 0xf5U};
    constexpr std::array<std::uint8_t, 6> kStation{
        0x10U, 0x11U, 0x12U, 0x13U, 0x14U, 0x15U};
    constexpr std::array<std::uint8_t, 6> kBle{
        0x20U, 0x21U, 0x22U, 0x23U, 0x24U, 0x25U};
    constexpr std::array<std::uint8_t, 6> kOldBle{
        0x30U, 0x31U, 0x32U, 0x33U, 0x34U, 0x35U};

    FieldSurveyCatalog current;
    Observation weak = accessPoint(kAp, 1100U, -70, "old-name");
    Observation strong = accessPoint(kAp, 1300U, -42, "Cafe,\"North\"");
    CHECK(current.ingest(weak, FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::Added);
    CHECK(current.ingest(strong, FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::Updated);
    CHECK(current.ingest(
              observation(RadioKind::Wifi, kStation, 1400U, -55, "client"),
              FieldSurveyEntityKind::WifiStation) ==
          FieldSurveyIngestStatus::Added);
    CHECK(current.ingest(bleDevice(kBle, 1500U, -61, "Tag"),
                         FieldSurveyEntityKind::BleDevice) ==
          FieldSurveyIngestStatus::Added);
    CHECK(current.size() == 3U);
    CHECK(current.complete());

    const FieldSurveyRecord* ap = current.get(0U);
    CHECK(ap != nullptr);
    CHECK(ap->firstSeenUs == 1100U);
    CHECK(ap->lastSeenUs == 1300U);
    CHECK(ap->observations == 2U);
    CHECK(ap->strongestRssiDbm == -42);
    CHECK(ap->latestRssiDbm == -42);
    CHECK(std::strcmp(ap->label.data(), "Cafe,\"North\"") == 0);
    CHECK(ap->wifiFactsPresent);
    CHECK(ap->wifiAuthentication == WifiAuthentication::Wpa2Psk);

    FieldSurveyCatalog baseline;
    CHECK(baseline.ingest(accessPoint(kAp, 100U, -60, "Cafe"),
                          FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::Added);
    CHECK(baseline.ingest(bleDevice(kOldBle, 200U, -80, "old-tag"),
                          FieldSurveyEntityKind::BleDevice) ==
          FieldSurveyIngestStatus::Added);
    const FieldSurveyComparison comparison = current.compare(baseline);
    CHECK(comparison.status == FieldSurveyComparisonStatus::Valid);
    CHECK(comparison.currentUnique == 3U);
    CHECK(comparison.baselineUnique == 2U);
    CHECK(comparison.seenAgain == 1U);
    CHECK(comparison.newThisVisit == 2U);
    CHECK(comparison.missingThisVisit == 1U);
    CHECK(comparison.wifiAccessPoints == 1U);
    CHECK(comparison.wifiStations == 1U);
    CHECK(comparison.bleDevices == 1U);
}

void testCatalogBuildFailsClosedOnDropsAndInvalidInput() {
    SurveySession running;
    CHECK(running.start("field", 100U) == SessionStatus::Started);
    FieldSurveyCatalog catalog;
    CHECK(catalog.build(running) == FieldSurveyBuildStatus::SessionNotStopped);
    CHECK(!catalog.complete());

    for (std::size_t index = 0U;
         index < SurveySession::kObservationCapacity; ++index) {
        std::array<std::uint8_t, 6> identity{};
        identity[0] = static_cast<std::uint8_t>(index + 1U);
        const Observation value = accessPoint(
            identity, 200U + index, -60, "bounded");
        CHECK(running.append(value) == SessionStatus::Appended);
    }
    Observation overflow = accessPoint(
        {0xffU, 1U, 2U, 3U, 4U, 5U}, 500U, -50, "overflow");
    CHECK(running.append(overflow) == SessionStatus::Full);
    CHECK(running.stop(600U) == SessionStatus::Stopped);
    CHECK(catalog.build(running) == FieldSurveyBuildStatus::CapacityExceeded);
    CHECK(!catalog.complete());
    CHECK(catalog.droppedCapacity() == 1U);
    CHECK(catalog.size() == SurveySession::kObservationCapacity);

    FieldSurveyCatalog invalid;
    Observation bad = accessPoint({1U, 2U, 3U, 4U, 5U, 6U},
                                  100U, -50, "bad");
    bad.radio = static_cast<RadioKind>(99U);
    CHECK(invalid.ingest(bad, FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::InvalidObservation);
    CHECK(!invalid.complete());

    FieldSurveyCatalog ordered;
    Observation first = accessPoint(
        {6U, 5U, 4U, 3U, 2U, 1U}, 200U, -70, "first");
    Observation older = first;
    older.monotonicUs = 199U;
    CHECK(ordered.ingest(first, FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::Added);
    CHECK(ordered.ingest(older, FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::OutOfOrder);
    CHECK(!ordered.complete());
    FieldSurveyCatalog complete;
    CHECK(complete.compare(ordered).status ==
          FieldSurveyComparisonStatus::IncompleteCatalog);
}

void testWigleExportIsExactAndTruthful() {
    constexpr std::array<std::uint8_t, 6> kAp{
        0xa0U, 0xb1U, 0xc2U, 0xd3U, 0xe4U, 0xf5U};
    FieldSurveyCatalog catalog;
    CHECK(catalog.ingest(accessPoint(kAp, 1300U, -42, "Cafe,\"North\""),
                         FieldSurveyEntityKind::WifiAccessPoint) ==
          FieldSurveyIngestStatus::Added);
    const FieldSurveyRecord* ap = catalog.get(0U);
    CHECK(ap != nullptr);
    std::array<char, 512> output{};

    FieldSurveyWigleResult formatted = formatFieldSurveyWigleMetadata(
        "1.0.0-dev.256", output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(!formatted.uploadReady);
    CHECK(std::strcmp(
              output.data(),
              "WigleWifi-1.6,appRelease=ESP32-Leshy-1.0.0-dev.256,"
              "model=ESP32-DIV,release=1.x,device=ESP32-DIV,"
              "display=ILI9341,board=esp32-div-v2\r\n") == 0);

    formatted = formatFieldSurveyWigleColumns(output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(std::strcmp(
              output.data(),
              "MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,"
              "CurrentLatitude,CurrentLongitude,AltitudeMeters,"
              "AccuracyMeters,RCOIs,MfgrId,Type\r\n") == 0);

    FieldSurveyWigleContext located;
    located.firstSeenUtc = "2026-08-29 12:34:56";
    located.location = {true, 557558260, 376173000, 12345, 678U};
    formatted = formatFieldSurveyWigleRow(
        *ap, located, output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(formatted.readiness == FieldSurveyWigleReadiness::Located);
    CHECK(formatted.uploadReady);
    CHECK(std::strcmp(
              output.data(),
              "A0:B1:C2:D3:E4:F5,\"Cafe,\"\"North\"\"\","
              "\"[WPA2-PSK-CCMP][ESS]\",2026-08-29 12:34:56,"
              "6,2437,-42,55.7558260,37.6173000,123.45,6.78,,,WIFI\r\n") ==
          0);

    FieldSurveyWigleContext unlocated;
    unlocated.firstSeenUtc = "2026-08-29 12:34:56";
    formatted = formatFieldSurveyWigleRow(
        *ap, unlocated, output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(formatted.readiness == FieldSurveyWigleReadiness::Unlocated);
    CHECK(!formatted.uploadReady);
    CHECK(std::strstr(output.data(), ",-42,,,,,,,WIFI\r\n") != nullptr);

    FieldSurveyWigleContext noTrustedMetadata;
    formatted = formatFieldSurveyWigleRow(
        *ap, noTrustedMetadata, output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(formatted.readiness ==
          FieldSurveyWigleReadiness::UntimedUnlocated);
    CHECK(!formatted.uploadReady);
    CHECK(std::strstr(output.data(), ",,6,2437,-42,,,,,,,WIFI\r\n") !=
          nullptr);

    FieldSurveyWigleContext untimedLocated;
    untimedLocated.location = {true, -338688000, 1512093000, 0, 250U};
    formatted = formatFieldSurveyWigleRow(
        *ap, untimedLocated, output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(formatted.readiness ==
          FieldSurveyWigleReadiness::UntimedLocated);
    CHECK(!formatted.uploadReady);
    CHECK(std::strstr(output.data(), ",-33.8688000,151.2093000,0.00,2.50,") !=
          nullptr);
}

void testWigleBleAndFailureBoundaries() {
    FieldSurveyCatalog catalog;
    CHECK(catalog.ingest(
              bleDevice({1U, 2U, 3U, 4U, 5U, 6U}, 100U, -61, "Tag"),
              FieldSurveyEntityKind::BleDevice) ==
          FieldSurveyIngestStatus::Added);
    const FieldSurveyRecord* ble = catalog.get(0U);
    CHECK(ble != nullptr);
    std::array<char, 256> output{};
    FieldSurveyWigleResult formatted = formatFieldSurveyWigleRow(
        *ble, {}, output.data(), output.size());
    CHECK(formatted.valid());
    CHECK(std::strcmp(
              output.data(),
              "01:02:03:04:05:06,\"Tag\",\"Misc [LE]\",,0,,-61,"
              ",,,,,0x004C,BLE\r\n") == 0);

    FieldSurveyCatalog stations;
    CHECK(stations.ingest(
              observation(RadioKind::Wifi,
                          {6U, 5U, 4U, 3U, 2U, 1U}, 100U, -50, "client"),
              FieldSurveyEntityKind::WifiStation) ==
          FieldSurveyIngestStatus::Added);
    const FieldSurveyRecord* station = stations.get(0U);
    CHECK(station != nullptr);
    formatted = formatFieldSurveyWigleRow(
        *station, {}, output.data(), output.size());
    CHECK(formatted.status == FieldSurveyWigleStatus::UnsupportedEntity);
    CHECK(output[0] == '\0');

    FieldSurveyWigleContext invalidTimestamp;
    invalidTimestamp.firstSeenUtc = "2026-08-29T12:34:56Z";
    formatted = formatFieldSurveyWigleRow(
        *ble, invalidTimestamp, output.data(), output.size());
    CHECK(formatted.status == FieldSurveyWigleStatus::InvalidTimestamp);

    FieldSurveyWigleContext invalidLocation;
    invalidLocation.location.latitudeE7 = 1;
    formatted = formatFieldSurveyWigleRow(
        *ble, invalidLocation, output.data(), output.size());
    CHECK(formatted.status == FieldSurveyWigleStatus::InvalidLocation);

    std::array<char, 8> tiny{};
    formatted = formatFieldSurveyWigleRow(
        *ble, {}, tiny.data(), tiny.size());
    CHECK(formatted.status == FieldSurveyWigleStatus::BufferTooSmall);
    CHECK(tiny[0] == '\0');
    CHECK(!formatFieldSurveyWigleMetadata(
               "bad version", output.data(), output.size()).valid());
}

SurveySession stoppedVisit(
    const char* id, const std::array<Observation, 3>& observations,
    std::size_t count) {
    SurveySession session;
    CHECK(session.start(id, 10U) == SessionStatus::Started);
    for (std::size_t index = 0; index < count; ++index) {
        CHECK(session.append(observations[index]) == SessionStatus::Appended);
    }
    CHECK(session.stop(10000U) == SessionStatus::Stopped);
    return session;
}

void testVisitTrackerUsesOnlyAnExplicitPreviousFieldVisit() {
    constexpr std::array<std::uint8_t, 6> kSame{
        1U, 2U, 3U, 4U, 5U, 6U};
    constexpr std::array<std::uint8_t, 6> kMissing{
        2U, 3U, 4U, 5U, 6U, 7U};
    constexpr std::array<std::uint8_t, 6> kNew{
        3U, 4U, 5U, 6U, 7U, 8U};
    constexpr std::array<std::uint8_t, 6> kBle{
        4U, 5U, 6U, 7U, 8U, 9U};

    const SurveySession unrelated = stoppedVisit(
        "product-passive-live",
        {accessPoint(kSame, 100U, -50, "same"), {}, {}}, 1U);
    FieldSurveyTracker tracker;
    FieldSurveyCatalog scratch;
    CHECK(!tracker.capturePrevious(unrelated, scratch));
    CHECK(!tracker.previousAvailable());
    CHECK(!tracker.toggleComparePrevious());

    const SurveySession previous = stoppedVisit(
        FieldSurveyTracker::kSessionId,
        {accessPoint(kSame, 100U, -50, "same"),
         bleDevice(kMissing, 200U, -70, "missing"), {}}, 2U);
    CHECK(tracker.capturePrevious(previous, scratch));
    CHECK(tracker.previousAvailable());
    CHECK(tracker.comparePrevious());

    const SurveySession current = stoppedVisit(
        FieldSurveyTracker::kSessionId,
        {accessPoint(kSame, 300U, -40, "same"),
         accessPoint(kNew, 400U, -60, "new"),
         bleDevice(kBle, 500U, -55, "tag")}, 3U);
    const FieldSurveyVisitResult& compared =
        tracker.completeVisit(current, scratch);
    CHECK(compared.status == FieldSurveyVisitStatus::Compared);
    CHECK(compared.complete());
    CHECK(compared.currentUnique == 3U);
    CHECK(compared.baselineUnique == 2U);
    CHECK(compared.seenAgain == 1U);
    CHECK(compared.newThisVisit == 2U);
    CHECK(compared.missingThisVisit == 1U);
    CHECK(compared.wifiAccessPoints == 2U);
    CHECK(compared.wifiStations == 0U);
    CHECK(compared.bleDevices == 1U);

    CHECK(tracker.toggleComparePrevious());
    CHECK(!tracker.comparePrevious());
    const FieldSurveyVisitResult& first = tracker.completeVisit(current, scratch);
    CHECK(first.status == FieldSurveyVisitStatus::FirstVisit);
    CHECK(first.newThisVisit == 3U);
    CHECK(first.seenAgain == 0U);
    CHECK(first.missingThisVisit == 0U);
}

void testVisitTrackerFailsClosedOnIncompleteCurrentVisit() {
    FieldSurveyTracker tracker;
    FieldSurveyCatalog scratch;
    SurveySession running;
    CHECK(running.start(FieldSurveyTracker::kSessionId, 1U) ==
          SessionStatus::Started);
    const FieldSurveyVisitResult& result = tracker.completeVisit(running, scratch);
    CHECK(result.status == FieldSurveyVisitStatus::Incomplete);
    CHECK(!result.complete());
    CHECK(result.buildStatus == FieldSurveyBuildStatus::SessionNotStopped);
}

}  // namespace

int main() {
    testCatalogDeduplicatesAndComparesVisits();
    testCatalogBuildFailsClosedOnDropsAndInvalidInput();
    testWigleExportIsExactAndTruthful();
    testWigleBleAndFailureBoundaries();
    testVisitTrackerUsesOnlyAnExplicitPreviousFieldVisit();
    testVisitTrackerFailsClosedOnIncompleteCurrentVisit();
    std::printf(
        "field survey tests passed (record=%zu B, catalog=%zu B, tracker=%zu B)\n",
        sizeof(FieldSurveyRecord), sizeof(FieldSurveyCatalog),
        sizeof(FieldSurveyTracker));
    return 0;
}
