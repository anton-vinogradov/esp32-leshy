#include <cstdlib>
#include <cstring>
#include <iostream>

#include "domain/targets/TargetComparison.h"
#include "services/targets/SurveySessionTargetEvidenceLookup.h"
#include "services/targets/TargetComparisonService.h"

using namespace leshy1::domain::observations;
using namespace leshy1::domain::targets;
using namespace leshy1::services::survey;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            std::cerr << __FILE__ << ':' << __LINE__                            \
                      << ": check failed: " #expression << '\n';               \
            ++failures;                                                         \
        }                                                                       \
    } while (false)

TargetId targetId(std::uint8_t suffix) {
    TargetId id{};
    id.bytes[0] = 0x54;
    id.bytes.back() = suffix;
    return id;
}

SourceId sourceId(std::uint8_t suffix) {
    SourceId id{};
    id.bytes[0] = 0x53;
    id.bytes.back() = suffix;
    return id;
}

TargetComparisonSource source(std::uint8_t suffix,
                              std::uint32_t generation) {
    return {sourceId(suffix), generation};
}

TargetIdentity wifiIdentity(std::uint8_t suffix) {
    TargetIdentity identity{};
    identity.kind = TargetIdentityKind::WifiBssid;
    identity.value = {0x02, 0x10, 0x20, 0x30, 0x40, suffix};
    identity.length = identity.value.size();
    return identity;
}

TargetIdentity bleIdentity(std::uint8_t suffix, std::uint8_t addressType = 1) {
    TargetIdentity identity{};
    identity.kind = TargetIdentityKind::BleAddress;
    identity.value = {0xc0, 0x10, 0x20, 0x30, 0x40, suffix};
    identity.length = identity.value.size();
    identity.discriminator = addressType;
    return identity;
}

TargetEvidenceRef evidence(const TargetComparisonSource& source,
                           std::uint64_t sequence,
                           std::uint64_t monotonicUs) {
    return {source.id, source.generation, sequence, monotonicUs};
}

Observation wifiObservation(const TargetIdentity& identity,
                            std::uint64_t sequence,
                            std::uint64_t monotonicUs, std::int16_t rssi,
                            std::uint16_t channel, const char* label) {
    Observation observation{};
    observation.sequence = sequence;
    observation.monotonicUs = monotonicUs;
    observation.radio = RadioKind::Wifi;
    observation.channel = channel;
    observation.frequencyKhz =
        static_cast<std::uint32_t>(2407000U + channel * 5000U);
    observation.rssiDbm = rssi;
    observation.identity = identity.value;
    observation.identityLength = identity.length;
    observation.labelLength = static_cast<std::uint8_t>(std::strlen(label));
    std::memcpy(observation.label.data(), label, observation.labelLength);
    observation.wifiNetwork.present = true;
    observation.wifiNetwork.authentication = WifiAuthentication::Wpa2Psk;
    observation.wifiNetwork.pairwiseCipher = WifiCipher::Ccmp;
    observation.wifiNetwork.groupCipher = WifiCipher::Ccmp;
    observation.wifiNetwork.channelWidth = WifiChannelWidth::Mhz20;
    return observation;
}

Observation bleObservation(const TargetIdentity& identity,
                           std::uint64_t sequence,
                           std::uint64_t monotonicUs, std::int16_t rssi,
                           const char* label) {
    Observation observation{};
    observation.sequence = sequence;
    observation.monotonicUs = monotonicUs;
    observation.radio = RadioKind::Ble;
    observation.rssiDbm = rssi;
    observation.identity = identity.value;
    observation.identityLength = identity.length;
    observation.labelLength = static_cast<std::uint8_t>(std::strlen(label));
    std::memcpy(observation.label.data(), label, observation.labelLength);
    observation.bleAdvertisement.present = true;
    observation.bleAdvertisement.addressType = identity.discriminator;
    observation.bleAdvertisement.legacy = true;
    observation.bleAdvertisement.scannable = true;
    return observation;
}

class FakeEvidenceLookup final : public TargetComparisonEvidenceLookup {
public:
    static constexpr std::size_t kCapacity = 48;

    bool add(const TargetEvidenceRef& reference,
             const Observation& observation) {
        if (size_ >= values_.size()) return false;
        const TargetComparisonSource source{
            reference.sourceId, reference.sourceGeneration};
        bool knownSource = false;
        for (std::size_t index = 0; index < sourceSize_; ++index) {
            if (targetComparisonSourceEqual(sources_[index], source)) {
                knownSource = true;
                break;
            }
        }
        if (!knownSource) {
            if (sourceSize_ >= sources_.size()) return false;
            sources_[sourceSize_++] = source;
        }
        values_[size_++] = {reference, observation};
        return true;
    }

    bool sourceAvailable(
        const TargetComparisonSource& source) const override {
        for (std::size_t index = 0; index < sourceSize_; ++index) {
            if (targetComparisonSourceEqual(sources_[index], source)) {
                return true;
            }
        }
        return false;
    }

    void remove(const TargetEvidenceRef& reference) {
        for (std::size_t index = 0; index < size_; ++index) {
            if (targetEvidenceEqual(values_[index].reference, reference)) {
                for (std::size_t move = index + 1; move < size_; ++move) {
                    values_[move - 1] = values_[move];
                }
                values_[--size_] = {};
                return;
            }
        }
    }

    bool loadExact(const TargetEvidenceRef& reference,
                   Observation* output) const override {
        if (output == nullptr) return false;
        for (std::size_t index = 0; index < size_; ++index) {
            if (targetEvidenceEqual(values_[index].reference, reference)) {
                *output = values_[index].observation;
                return true;
            }
        }
        return false;
    }

private:
    struct Value final {
        TargetEvidenceRef reference{};
        Observation observation{};
    };
    std::array<Value, kCapacity> values_{};
    std::size_t size_ = 0;
    std::array<TargetComparisonSource, 8> sources_{};
    std::size_t sourceSize_ = 0;
};

const TargetComparisonItem* findItem(const TargetComparisonResult& result,
                                     const TargetId& id) {
    for (std::size_t index = 0; index < result.size; ++index) {
        const TargetComparisonItem* item = result.get(index);
        if (item != nullptr && targetIdEqual(item->targetId, id)) return item;
    }
    return nullptr;
}

void addEvidence(TargetCatalog* catalog, FakeEvidenceLookup* lookup,
                 const TargetId& target, const TargetIdentity& identity,
                 const TargetEvidenceRef& reference,
                 const Observation& observation, bool create = false) {
    CHECK(lookup->add(reference, observation));
    const TargetMutationStatus status = create
        ? catalog->create(target, identity, reference)
        : catalog->attachEvidence(target, identity, reference);
    CHECK(status == (create ? TargetMutationStatus::Created
                            : TargetMutationStatus::Applied));
}

void checkGoldenComparison() {
    const TargetComparisonSource baseline = source(1, 7);
    const TargetComparisonSource current = source(2, 9);
    TargetCatalog catalog;
    FakeEvidenceLookup lookup;

    const TargetIdentity stableWifi = wifiIdentity(1);
    const TargetEvidenceRef stableBase = evidence(baseline, 1, 1000);
    const TargetEvidenceRef stableNow = evidence(current, 1, 2000);
    addEvidence(&catalog, &lookup, targetId(1), stableWifi, stableBase,
                wifiObservation(stableWifi, 1, 1000, -60, 6, "office"), true);
    addEvidence(&catalog, &lookup, targetId(1), stableWifi, stableNow,
                wifiObservation(stableWifi, 1, 2000, -55, 6, "office"));

    const TargetIdentity changedWifi = wifiIdentity(2);
    const TargetEvidenceRef changedBase = evidence(baseline, 2, 1100);
    const TargetEvidenceRef changedNow = evidence(current, 2, 2100);
    addEvidence(&catalog, &lookup, targetId(2), changedWifi, changedBase,
                wifiObservation(changedWifi, 2, 1100, -51, 1, ""), true);
    Observation enriched =
        wifiObservation(changedWifi, 2, 2100, -57, 11, "camera");
    enriched.wifiNetwork.wps = true;
    addEvidence(&catalog, &lookup, targetId(2), changedWifi, changedNow,
                enriched);

    const TargetIdentity removedBle = bleIdentity(3);
    const TargetEvidenceRef removedBase = evidence(baseline, 3, 1200);
    addEvidence(&catalog, &lookup, targetId(3), removedBle, removedBase,
                bleObservation(removedBle, 3, 1200, -70, "tag"), true);

    const TargetIdentity addedBle = bleIdentity(4);
    const TargetEvidenceRef addedNow = evidence(current, 4, 2200);
    addEvidence(&catalog, &lookup, targetId(4), addedBle, addedNow,
                bleObservation(addedBle, 4, 2200, -48, "watch"), true);

    const TargetCatalog before = catalog;
    TargetComparisonService service(catalog, lookup);
    TargetComparisonAction action{};
    action.baseline = baseline;
    action.current = current;
    const TargetComparisonResult result = service.execute(action);
    CHECK(result.compared());
    CHECK(result.size == 4);
    CHECK(result.added == 1);
    CHECK(result.removed == 1);
    CHECK(result.changed == 1);
    CHECK(result.unchanged == 1);
    CHECK(targetComparisonSourceEqual(result.baseline, baseline));
    CHECK(targetComparisonSourceEqual(result.current, current));

    const TargetComparisonItem* stable = findItem(result, targetId(1));
    CHECK(stable != nullptr);
    CHECK(stable->classification == TargetComparisonClass::Unchanged);
    CHECK(stable->changes == 0);
    CHECK(stable->baselineEvidenceCount == 1);
    CHECK(stable->currentEvidenceCount == 1);
    CHECK(targetEvidenceEqual(stable->baselineEvidence[0].reference,
                              stableBase));
    CHECK(targetEvidenceEqual(stable->currentEvidence[0].reference,
                              stableNow));

    const TargetComparisonItem* changed = findItem(result, targetId(2));
    CHECK(changed != nullptr);
    CHECK(changed->classification == TargetComparisonClass::Changed);
    CHECK((changed->changes & targetChangeMask(TargetChangeKind::Signal)) != 0);
    CHECK((changed->changes & targetChangeMask(TargetChangeKind::Frequency)) != 0);
    CHECK((changed->changes & targetChangeMask(TargetChangeKind::Channel)) != 0);
    CHECK((changed->changes & targetChangeMask(TargetChangeKind::Label)) != 0);
    CHECK((changed->changes & targetChangeMask(TargetChangeKind::WifiFacts)) != 0);
    CHECK(changed->baselineEvidenceCount == 1);
    CHECK(changed->currentEvidenceCount == 1);

    const TargetComparisonItem* removed = findItem(result, targetId(3));
    CHECK(removed != nullptr);
    CHECK(removed->classification == TargetComparisonClass::Removed);
    CHECK(removed->baselineEvidenceCount == 1);
    CHECK(removed->currentEvidenceCount == 0);
    CHECK(targetEvidenceEqual(removed->baselineEvidence[0].reference,
                              removedBase));

    const TargetComparisonItem* added = findItem(result, targetId(4));
    CHECK(added != nullptr);
    CHECK(added->classification == TargetComparisonClass::Added);
    CHECK(added->baselineEvidenceCount == 0);
    CHECK(added->currentEvidenceCount == 1);
    CHECK(targetEvidenceEqual(added->currentEvidence[0].reference, addedNow));

    CHECK(catalog.size() == before.size());
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        CHECK(targetRecordGraphEqual(*catalog.get(index), *before.get(index)));
        CHECK(catalog.get(index)->revision == before.get(index)->revision);
    }

    const TargetComparisonActionDescriptor& descriptor =
        targetComparisonActionDescriptor();
    CHECK(std::strcmp(descriptor.id, "target.compare") == 0);
    CHECK(descriptor.requestSchemaVersion == 1);
    CHECK(descriptor.resultSchemaVersion == 1);
    CHECK(descriptor.requiredResources != 0);
    CHECK(!descriptor.cancellable);
    CHECK(sizeof(TargetComparisonResult) <= 12U * 1024U);
}

void checkLatestEvidenceAndIdentitySet() {
    const TargetComparisonSource baseline = source(3, 1);
    const TargetComparisonSource current = source(4, 1);
    const TargetIdentity wifi = wifiIdentity(5);
    const TargetIdentity ble = bleIdentity(5);
    TargetCatalog catalog;
    FakeEvidenceLookup lookup;
    const TargetEvidenceRef oldBaseline = evidence(baseline, 1, 1000);
    const TargetEvidenceRef latestBaseline = evidence(baseline, 2, 1100);
    const TargetEvidenceRef currentWifi = evidence(current, 1, 2000);
    const TargetEvidenceRef currentBle = evidence(current, 2, 2100);
    addEvidence(&catalog, &lookup, targetId(5), wifi, oldBaseline,
                wifiObservation(wifi, 1, 1000, -80, 6, "node"), true);
    addEvidence(&catalog, &lookup, targetId(5), wifi, latestBaseline,
                wifiObservation(wifi, 2, 1100, -60, 6, "node"));
    addEvidence(&catalog, &lookup, targetId(5), wifi, currentWifi,
                wifiObservation(wifi, 1, 2000, -60, 6, "node"));
    addEvidence(&catalog, &lookup, targetId(5), ble, currentBle,
                bleObservation(ble, 2, 2100, -55, "node"));

    const TargetComparisonResult result = compareTargetSessions(
        catalog, baseline, current, lookup);
    CHECK(result.compared());
    CHECK(result.changed == 1);
    const TargetComparisonItem* item = result.get(0);
    CHECK(item != nullptr);
    CHECK(item->classification == TargetComparisonClass::Changed);
    CHECK(item->changes == targetChangeMask(TargetChangeKind::IdentitySet));
    CHECK(item->baselineEvidenceCount == 1);
    CHECK(item->currentEvidenceCount == 2);
    CHECK(targetEvidenceEqual(item->baselineEvidence[0].reference,
                              latestBaseline));
    CHECK(targetIdentityEqual(item->currentEvidence[0].identity, wifi));
    CHECK(targetIdentityEqual(item->currentEvidence[1].identity, ble));
}

void checkFailureIsAllOrNothing() {
    const TargetComparisonSource baseline = source(5, 1);
    const TargetComparisonSource current = source(6, 1);
    const TargetIdentity wifi = wifiIdentity(6);
    const TargetEvidenceRef before = evidence(baseline, 1, 1000);
    const TargetEvidenceRef after = evidence(current, 1, 2000);
    TargetCatalog catalog;
    FakeEvidenceLookup lookup;
    addEvidence(&catalog, &lookup, targetId(6), wifi, before,
                wifiObservation(wifi, 1, 1000, -60, 6, "node"), true);
    addEvidence(&catalog, &lookup, targetId(6), wifi, after,
                wifiObservation(wifi, 1, 2000, -60, 6, "node"));

    lookup.remove(after);
    TargetComparisonResult result = compareTargetSessions(
        catalog, baseline, current, lookup);
    CHECK(result.status == TargetComparisonStatus::EvidenceUnavailable);
    CHECK(result.size == 0);
    CHECK(result.added == 0 && result.removed == 0 && result.changed == 0 &&
          result.unchanged == 0);

    CHECK(lookup.add(after,
                     wifiObservation(wifi, 99, 2000, -60, 6, "node")));
    result = compareTargetSessions(catalog, baseline, current, lookup);
    CHECK(result.status == TargetComparisonStatus::EvidenceMismatch);
    CHECK(result.size == 0);

    TargetComparisonAction action{};
    action.schemaVersion = 2;
    action.baseline = baseline;
    action.current = current;
    TargetComparisonService service(catalog, lookup);
    CHECK(service.execute(action).status ==
          TargetComparisonStatus::InvalidArgument);
    CHECK(compareTargetSessions(catalog, baseline, baseline, lookup).status ==
          TargetComparisonStatus::InvalidArgument);
}

void checkMalformedObservationFailsClosed() {
    const TargetComparisonSource baseline = source(7, 1);
    const TargetComparisonSource current = source(8, 1);
    const TargetIdentity wifi = wifiIdentity(7);
    const TargetEvidenceRef before = evidence(baseline, 1, 1000);
    const TargetEvidenceRef after = evidence(current, 1, 2000);
    TargetCatalog catalog;
    FakeEvidenceLookup lookup;
    addEvidence(&catalog, &lookup, targetId(7), wifi, before,
                wifiObservation(wifi, 1, 1000, -60, 6, "node"), true);
    Observation malformed = wifiObservation(wifi, 1, 2000, -60, 6, "node");
    malformed.labelLength =
        static_cast<std::uint8_t>(Observation::kLabelCapacity + 1U);
    addEvidence(&catalog, &lookup, targetId(7), wifi, after, malformed);
    const TargetComparisonResult result = compareTargetSessions(
        catalog, baseline, current, lookup);
    CHECK(result.status == TargetComparisonStatus::EvidenceMismatch);
    CHECK(result.size == 0);
}

void checkRealSurveySessionLookup() {
    const TargetComparisonSource baselineSource = source(9, 3);
    const TargetComparisonSource currentSource = source(10, 4);
    const TargetIdentity wifi = wifiIdentity(9);
    SurveySession baselineSession;
    SurveySession currentSession;
    CHECK(baselineSession.start("baseline", 900) == SessionStatus::Started);
    CHECK(baselineSession.append(
              wifiObservation(wifi, 88, 1000, -60, 6, "node")) ==
          SessionStatus::Appended);
    CHECK(baselineSession.stop(1100) == SessionStatus::Stopped);
    CHECK(currentSession.start("current", 1900) == SessionStatus::Started);
    CHECK(currentSession.append(
              wifiObservation(wifi, 77, 2000, -54, 6, "node")) ==
          SessionStatus::Appended);
    CHECK(currentSession.stop(2100) == SessionStatus::Stopped);
    const TargetEvidenceRef baselineEvidence =
        evidence(baselineSource, 1, 1000);
    const TargetEvidenceRef currentEvidence =
        evidence(currentSource, 1, 2000);
    TargetCatalog catalog;
    CHECK(catalog.create(targetId(9), wifi, baselineEvidence) ==
          TargetMutationStatus::Created);
    CHECK(catalog.attachEvidence(targetId(9), wifi, currentEvidence) ==
          TargetMutationStatus::Applied);

    SurveySessionTargetEvidenceLookup lookup(
        {baselineSource, &baselineSession},
        {currentSource, &currentSession});
    TargetComparisonService service(catalog, lookup);
    TargetComparisonAction action{};
    action.baseline = baselineSource;
    action.current = currentSource;
    const TargetComparisonResult result = service.execute(action);
    CHECK(result.compared());
    CHECK(result.size == 1);
    CHECK(result.changed == 1);
    CHECK(result.get(0)->changes ==
          targetChangeMask(TargetChangeKind::Signal));

    SurveySession running;
    CHECK(running.start("running", 3000) == SessionStatus::Started);
    SurveySessionTargetEvidenceLookup unavailable(
        {baselineSource, &running}, {currentSource, &currentSession});
    CHECK(compareTargetSessions(catalog, baselineSource, currentSource,
                                unavailable).status ==
          TargetComparisonStatus::SourceUnavailable);
    SurveySessionTargetEvidenceLookup sameSession(
        {baselineSource, &baselineSession},
        {currentSource, &baselineSession});
    CHECK(compareTargetSessions(catalog, baselineSource, currentSource,
                                sameSession).status ==
          TargetComparisonStatus::SourceUnavailable);
}

}  // namespace

int main() {
    checkGoldenComparison();
    checkLatestEvidenceAndIdentitySet();
    checkFailureIsAllOrNothing();
    checkMalformedObservationFailsClosed();
    checkRealSurveySessionLookup();
    if (failures != 0) {
        std::cerr << failures << " target comparison test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "S6 evidence-backed Target comparison tests passed; result_bytes="
              << sizeof(TargetComparisonResult) << '\n';
    return EXIT_SUCCESS;
}
