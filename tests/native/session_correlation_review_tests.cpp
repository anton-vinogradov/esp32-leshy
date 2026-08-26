#include <cstring>
#include <iostream>

#include "services/targets/ObservationTargetAdapter.h"
#include "services/targets/SessionCorrelationReview.h"

using namespace leshy1::domain::observations;
using namespace leshy1::domain::targets;
using namespace leshy1::services::survey;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(expression)                                                     \
    do {                                                                      \
        if (!(expression)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__                         \
                      << ": check failed: " #expression << '\n';             \
            ++failures;                                                       \
        }                                                                     \
    } while (false)

SourceId source(std::uint8_t suffix) {
    SourceId result{};
    result.bytes[0] = 0x53;
    result.bytes.back() = suffix;
    return result;
}

TargetId target(std::uint8_t suffix) {
    TargetId result{};
    result.bytes[0] = 0x4c;
    result.bytes.back() = suffix;
    return result;
}

Observation observation(RadioKind radio, std::uint64_t sequence,
                        std::uint64_t monotonicUs, std::uint8_t suffix,
                        std::int16_t rssi, const char* label) {
    Observation result{};
    result.radio = radio;
    result.sequence = sequence;
    result.monotonicUs = monotonicUs;
    result.frequencyKhz = radio == RadioKind::Wifi ? 2412000U : 0U;
    result.channel = radio == RadioKind::Wifi ? 1U : 0U;
    result.rssiDbm = rssi;
    result.identity = {0x02, 0x11, 0x22, 0x33, 0x44, suffix};
    result.identityLength = result.identity.size();
    result.labelLength = static_cast<std::uint8_t>(std::strlen(label));
    std::memcpy(result.label.data(), label, result.labelLength);
    if (radio == RadioKind::Wifi) {
        result.wifiNetwork.present = true;
    } else {
        result.bleAdvertisement.present = true;
        result.bleAdvertisement.addressType = 1;
    }
    return result;
}

SurveySession stoppedSession(const char* id, std::uint64_t base,
                             std::initializer_list<Observation> values) {
    SurveySession result;
    CHECK(result.start(id, base) == SessionStatus::Started);
    for (const Observation& value : values) {
        CHECK(result.append(value) == SessionStatus::Appended);
    }
    CHECK(result.stop(base + 100U) == SessionStatus::Stopped);
    return result;
}

TargetComparisonSessionBinding binding(const SurveySession& session,
                                       std::uint8_t sourceSuffix,
                                       std::uint32_t generation) {
    return {{source(sourceSuffix), generation}, &session};
}

void createBaselineTarget(TargetCatalog* catalog, const TargetId& id,
                          const TargetComparisonSessionBinding& baseline,
                          std::size_t observationIndex = 0) {
    const Observation* value = baseline.session->get(observationIndex);
    CHECK(value != nullptr);
    const ObservationTargetAdmission admitted = admitObservationToTarget(
        baseline.source.id, baseline.source.generation, *value);
    CHECK(admitted.valid());
    CHECK(catalog->create(id, admitted.identity, admitted.evidence) ==
          TargetMutationStatus::Created);
}

void uniqueCrossRadioNameProducesExplainableProposal() {
    SurveySession baseline = stoppedSession(
        "old", 100, {observation(RadioKind::Wifi, 1, 110, 1, -52, "Beacon")});
    SurveySession current = stoppedSession(
        "new", 300, {observation(RadioKind::Ble, 1, 310, 2, -57, "Beacon")});
    const auto oldBinding = binding(baseline, 1, 10);
    const auto newBinding = binding(current, 2, 11);
    TargetCatalog catalog;
    CorrelationDecisionLog decisions;
    createBaselineTarget(&catalog, target(1), oldBinding);

    SessionCorrelationProposalSet proposals;
    proposals.size = proposals.values.size();
    proposals.truncated = true;
    CHECK(buildSessionCorrelationReview(oldBinding, newBinding, catalog,
                                        decisions, &proposals) ==
          SessionCorrelationReviewStatus::Ready);
    CHECK(proposals.size == 1);
    CHECK(!proposals.truncated);
    CHECK(proposals.values[0].confidence == CorrelationConfidence::Medium);
    CHECK(proposals.values[0].scorePermille == 452);
    CHECK(proposals.values[0].featureCount == 2);
    CHECK(proposals.values[0].features[0].kind ==
          CorrelationFeatureKind::AdvertisedNameMatch);
    CHECK(proposals.values[0].features[1].kind ==
          CorrelationFeatureKind::SignalTrendMatch);
    CHECK(sessionCorrelationCandidatePending(
        proposals, proposals.values[0].candidateIdentity));
    CHECK(catalog.size() == 1);
    CHECK(catalog.findByIdentity(proposals.values[0].candidateIdentity) ==
          nullptr);

    SurveySessionTargetEvidenceLookup lookup(oldBinding, newBinding);
    CorrelationService service(catalog, decisions, lookup);
    const std::uint32_t revision = catalog.find(target(1))->revision;
    CorrelationAction reject{};
    reject.kind = CorrelationActionKind::Reject;
    reject.proposal = proposals.values[0];
    reject.expectedTargetRevision = revision;
    CHECK(service.execute(reject).status == CorrelationDecisionStatus::Rejected);
    SessionCorrelationProposalSet rebuilt;
    CHECK(buildSessionCorrelationReview(oldBinding, newBinding, catalog,
                                        decisions, &rebuilt) ==
          SessionCorrelationReviewStatus::Ready);
    CHECK(rebuilt.size == 0);
}

void sameRadioAndAmbiguousLabelsStayIndependent() {
    SurveySession wifiBaseline = stoppedSession(
        "wifi-old", 1000,
        {observation(RadioKind::Wifi, 1, 1010, 1, -40, "Office")});
    SurveySession wifiCurrent = stoppedSession(
        "wifi-new", 1200,
        {observation(RadioKind::Wifi, 1, 1210, 2, -41, "Office")});
    const auto wifiOld = binding(wifiBaseline, 3, 20);
    const auto wifiNew = binding(wifiCurrent, 4, 21);
    TargetCatalog wifiCatalog;
    CorrelationDecisionLog decisions;
    createBaselineTarget(&wifiCatalog, target(2), wifiOld);
    SessionCorrelationProposalSet proposals;
    CHECK(buildSessionCorrelationReview(wifiOld, wifiNew, wifiCatalog,
                                        decisions, &proposals) ==
          SessionCorrelationReviewStatus::Ready);
    CHECK(proposals.size == 0);

    SurveySession baseline = stoppedSession(
        "amb-old", 2000,
        {observation(RadioKind::Wifi, 1, 2010, 3, -50, "Tag"),
         observation(RadioKind::Wifi, 2, 2020, 4, -55, "Tag")});
    SurveySession current = stoppedSession(
        "amb-new", 2200,
        {observation(RadioKind::Ble, 1, 2210, 5, -52, "Tag")});
    const auto oldBinding = binding(baseline, 5, 30);
    const auto newBinding = binding(current, 6, 31);
    TargetCatalog catalog;
    createBaselineTarget(&catalog, target(3), oldBinding, 0);
    createBaselineTarget(&catalog, target(4), oldBinding, 1);
    CHECK(buildSessionCorrelationReview(oldBinding, newBinding, catalog,
                                        decisions, &proposals) ==
          SessionCorrelationReviewStatus::Ready);
    CHECK(proposals.size == 0);
}

}  // namespace

int main() {
    uniqueCrossRadioNameProducesExplainableProposal();
    sameRadioAndAmbiguousLabelsStayIndependent();
    if (failures != 0) return 1;
    std::cout << "session correlation review tests passed\n";
    return 0;
}
