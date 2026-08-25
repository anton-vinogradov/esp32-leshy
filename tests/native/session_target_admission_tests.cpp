#include <cstring>
#include <iostream>

#include "domain/observations/Observation.h"
#include "domain/targets/TargetCatalog.h"
#include "services/survey/SurveySession.h"
#include "services/targets/SessionTargetAdmission.h"

using namespace leshy1::domain::observations;
using namespace leshy1::domain::targets;
using namespace leshy1::services::survey;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__ << ": CHECK("          \
                      << #condition << ") failed\n";                         \
            ++failures;                                                      \
        }                                                                    \
    } while (false)

Observation wifi(std::uint64_t sequence, std::uint64_t us,
                 std::uint8_t suffix, std::int16_t rssi) {
    Observation value{};
    value.sequence = sequence;
    value.monotonicUs = us;
    value.radio = RadioKind::Wifi;
    value.frequencyKhz = 2412000;
    value.channel = 1;
    value.rssiDbm = rssi;
    value.identity = {0x02, 0, 0, 0, 0, suffix};
    value.identityLength = 6;
    value.wifiNetwork.present = true;
    return value;
}

Observation ble(std::uint64_t sequence, std::uint64_t us,
                std::uint8_t suffix) {
    Observation value = wifi(sequence, us, suffix, -70);
    value.radio = RadioKind::Ble;
    value.frequencyKhz = 2426000;
    value.channel = 38;
    value.bleAdvertisement.present = true;
    value.bleAdvertisement.addressType = 1;
    return value;
}

SurveySession stoppedSession(const char* id, std::uint8_t wifiSuffix,
                             std::uint8_t bleSuffix) {
    SurveySession session;
    CHECK(session.start(id, 100) == SessionStatus::Started);
    CHECK(session.append(wifi(1, 110, wifiSuffix, -80)) ==
          SessionStatus::Appended);
    CHECK(session.append(ble(2, 120, bleSuffix)) == SessionStatus::Appended);
    CHECK(session.append(wifi(3, 130, wifiSuffix, -42)) ==
          SessionStatus::Appended);
    CHECK(session.stop(140) == SessionStatus::Stopped);
    return session;
}

void stableIdsAndLatestEvidence() {
    SurveySession session = stoppedSession("baseline", 1, 2);
    SourceId first{};
    SourceId second{};
    CHECK(sourceIdForSession(session, &first));
    CHECK(sourceIdForSession(session, &second));
    CHECK(first.bytes == second.bytes);

    TargetCatalog catalog;
    TargetCatalog scratch;
    const auto admitted = admitSessionTargets(session, 7, catalog, scratch);
    CHECK(admitted.valid());
    CHECK(admitted.observations == 3);
    CHECK(admitted.identities == 2);
    CHECK(admitted.created == 2);
    CHECK(admitted.evidenceAttached == 0);
    CHECK(catalog.size() == 2);

    TargetIdentity wifiIdentity{};
    wifiIdentity.kind = TargetIdentityKind::WifiBssid;
    wifiIdentity.value = {0x02, 0, 0, 0, 0, 1};
    wifiIdentity.length = 6;
    const TargetRecord* target = catalog.findByIdentity(wifiIdentity);
    CHECK(target != nullptr);
    CHECK(target->evidenceCount == 1);
    CHECK(target->evidence[0].observationSequence == 3);
    CHECK(target->evidence[0].observedMonotonicUs == 130);
    CHECK(target->evidence[0].sourceGeneration == 7);

    const TargetCatalog before = catalog;
    const auto replay = admitSessionTargets(session, 7, catalog, scratch);
    CHECK(replay.valid());
    CHECK(replay.created == 0);
    CHECK(replay.evidenceAttached == 0);
    CHECK(replay.unchanged == 2);
    CHECK(catalog.size() == before.size());
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        CHECK(targetRecordGraphEqual(*catalog.get(index), *before.get(index)));
        CHECK(targetIdEqual(catalog.get(index)->id, before.get(index)->id));
    }
}

void repeatedIdentityAcrossSessionsAttachesEvidence() {
    SurveySession baseline = stoppedSession("baseline", 3, 4);
    SurveySession current = stoppedSession("current", 3, 5);
    TargetCatalog catalog;
    TargetCatalog scratch;
    CHECK(admitSessionTargets(baseline, 1, catalog, scratch).valid());
    const auto result = admitSessionTargets(current, 2, catalog, scratch);
    CHECK(result.valid());
    CHECK(result.created == 1);
    CHECK(result.evidenceAttached == 1);
    CHECK(catalog.size() == 3);

    TargetIdentity shared{};
    shared.kind = TargetIdentityKind::WifiBssid;
    shared.value = {0x02, 0, 0, 0, 0, 3};
    shared.length = 6;
    const TargetRecord* target = catalog.findByIdentity(shared);
    CHECK(target != nullptr);
    CHECK(target->evidenceCount == 2);
    CHECK(target->evidence[0].sourceGeneration == 1);
    CHECK(target->evidence[1].sourceGeneration == 2);
}

void failuresAreAtomic() {
    SurveySession baseline = stoppedSession("baseline", 6, 7);
    TargetCatalog catalog;
    TargetCatalog scratch;
    CHECK(admitSessionTargets(baseline, 1, catalog, scratch).valid());
    const TargetCatalog before = catalog;

    SurveySession malformed;
    CHECK(malformed.start("broken", 200) == SessionStatus::Started);
    Observation invalid = wifi(1, 210, 8, -50);
    invalid.identityLength = 0;
    CHECK(malformed.append(invalid) == SessionStatus::Appended);
    CHECK(malformed.stop(220) == SessionStatus::Stopped);
    const auto rejected = admitSessionTargets(malformed, 2, catalog, scratch);
    CHECK(rejected.status ==
          SessionTargetAdmissionStatus::ObservationRejected);
    CHECK(catalog.size() == before.size());
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        CHECK(targetRecordGraphEqual(*catalog.get(index), *before.get(index)));
    }

    SurveySession running;
    CHECK(running.start("running", 300) == SessionStatus::Started);
    CHECK(admitSessionTargets(running, 3, catalog, scratch).status ==
          SessionTargetAdmissionStatus::SessionUnavailable);
    CHECK(admitSessionTargets(baseline, 0, catalog, scratch).status ==
          SessionTargetAdmissionStatus::InvalidArgument);
    CHECK(admitSessionTargets(baseline, 1, catalog, catalog).status ==
          SessionTargetAdmissionStatus::InvalidArgument);
}

}  // namespace

int main() {
    stableIdsAndLatestEvidence();
    repeatedIdentityAcrossSessionsAttachesEvidence();
    failuresAreAtomic();
    if (failures != 0) {
        std::cerr << failures << " session target admission test(s) failed\n";
        return 1;
    }
    std::cout << "session target admission tests passed\n";
    return 0;
}
