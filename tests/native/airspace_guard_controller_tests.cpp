#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "apps/guard/AirspaceGuardController.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::apps::guard;
using namespace leshy1::services::guard;

constexpr std::array<std::uint8_t, 6> kSourceA{
    0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
constexpr std::array<std::uint8_t, 6> kSourceB{
    0x04, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};
constexpr std::array<std::uint8_t, 6> kSourceC{
    0x06, 0x10, 0x20, 0x30, 0x40, 0x50};

AirspaceFinding makeFinding(
    const std::array<std::uint8_t, 6>& source,
    AirspaceConfidence confidence, std::uint16_t observed,
    std::uint16_t threshold, std::uint64_t firstUs,
    std::uint64_t lastUs) {
    CHECK(observed >= threshold);
    AirspaceFinding finding{};
    finding.confidence = confidence;
    finding.detectorVersion = AirspaceFinding::kDetectorVersion;
    finding.threshold = threshold;
    finding.observed = observed;
    finding.deauthenticationFrames = observed;
    finding.transmitter = source;
    finding.firstUs = firstUs;
    finding.lastUs = lastUs;
    finding.evidenceCount = observed < finding.evidence.size()
        ? observed : finding.evidence.size();
    for (std::size_t index = 0; index < finding.evidenceCount; ++index) {
        AirspaceEvidenceRef& evidence = finding.evidence[index];
        evidence.frameIndex = index + 10U;
        evidence.monotonicUs = firstUs +
            ((lastUs - firstUs) * index) /
                (finding.evidenceCount > 1U
                    ? finding.evidenceCount - 1U : 1U);
        evidence.channel = static_cast<std::uint8_t>(1U + index);
        evidence.rssiDbm = static_cast<std::int16_t>(-40 - index);
    }
    return finding;
}

void testStrongestFindingOpensFirstAndOrderIsStable() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 3;
    report.findings[0] = makeFinding(
        kSourceA, AirspaceConfidence::Medium, 4, 4, 1000000, 1300000);
    report.findings[1] = makeFinding(
        kSourceB, AirspaceConfidence::High, 4, 4, 2000000, 2300000);
    report.findings[2] = makeFinding(
        kSourceC, AirspaceConfidence::High, 6, 4, 3000000, 3500000);

    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.view() == AirspaceGuardView::Finding);
    CHECK(controller.findingCount() == 3);
    CHECK(controller.selectedFinding() != nullptr);
    CHECK(controller.selectedFinding()->transmitter == kSourceC);
    CHECK(controller.next());
    CHECK(controller.selectedFinding()->transmitter == kSourceB);
    CHECK(controller.next());
    CHECK(controller.selectedFinding()->transmitter == kSourceA);
    CHECK(!controller.next());
    CHECK(controller.previous());
    CHECK(controller.selectedFinding()->transmitter == kSourceB);
}

void testEvidenceDrilldownUsesExactSourceReference() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1;
    report.findings[0] = makeFinding(
        kSourceA, AirspaceConfidence::Medium, 4, 4, 1000000, 1600000);

    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.openSelected());
    CHECK(controller.view() == AirspaceGuardView::EvidenceList);
    CHECK(controller.next());
    CHECK(controller.selectedEvidence() != nullptr);
    CHECK(controller.selectedEvidence()->frameIndex == 11);
    CHECK(controller.selectedEvidence()->channel == 2);
    CHECK(controller.selectedEvidence()->rssiDbm == -41);
    CHECK(controller.openSelected());
    CHECK(controller.view() == AirspaceGuardView::EvidenceDetail);
    CHECK(!controller.next());
    CHECK(controller.back());
    CHECK(controller.view() == AirspaceGuardView::EvidenceList);
    CHECK(controller.evidenceSelection() == 1);
    CHECK(controller.back());
    CHECK(controller.view() == AirspaceGuardView::Finding);
    CHECK(!controller.back());
}

void testIncompleteEvidenceRemainsVisibleUncertainty() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1;
    report.findings[0] = makeFinding(
        kSourceA, AirspaceConfidence::Medium, 4, 4, 1000000, 1400000);
    report.sourceReadFailures = 1;
    report.inspectionTruncated = true;

    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.evidenceIncomplete());
    CHECK(controller.outcome() == AirspaceGuardStatus::Finding);
}

void testClearAndInconclusiveStayOutcomeOnly() {
    AirspaceGuardController controller;
    AirspaceGuardReport clear{};
    clear.status = AirspaceGuardStatus::Clear;
    CHECK(controller.load(clear) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.view() == AirspaceGuardView::Outcome);
    CHECK(controller.outcome() == AirspaceGuardStatus::Clear);
    CHECK(!controller.openSelected());

    AirspaceGuardReport inconclusive{};
    inconclusive.status = AirspaceGuardStatus::Inconclusive;
    inconclusive.sourceReadFailures = 1;
    CHECK(controller.load(inconclusive) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.outcome() == AirspaceGuardStatus::Inconclusive);
    CHECK(controller.evidenceIncomplete());
}

void testMalformedReportsFailClosed() {
    AirspaceGuardController controller;
    AirspaceGuardReport mismatch{};
    mismatch.status = AirspaceGuardStatus::Finding;
    CHECK(controller.load(mismatch) == AirspaceGuardLoadStatus::InvalidReport);

    AirspaceGuardReport malformed{};
    malformed.status = AirspaceGuardStatus::Finding;
    malformed.findingCount = 1;
    malformed.findings[0] = makeFinding(
        kSourceA, AirspaceConfidence::Medium, 4, 4, 1000000, 1300000);
    malformed.findings[0].evidence[0].channel = 0;
    CHECK(controller.load(malformed) ==
          AirspaceGuardLoadStatus::InvalidReport);
    CHECK(controller.view() == AirspaceGuardView::Outcome);
    CHECK(!controller.hasFinding());
}

void testStableNames() {
    CHECK(std::strcmp(airspaceGuardViewName(AirspaceGuardView::Finding),
                      "finding") == 0);
    CHECK(std::strcmp(airspaceGuardLoadStatusName(
                          AirspaceGuardLoadStatus::InvalidReport),
                      "invalid_report") == 0);
}

}  // namespace

int main() {
    testStrongestFindingOpensFirstAndOrderIsStable();
    testEvidenceDrilldownUsesExactSourceReference();
    testIncompleteEvidenceRemainsVisibleUncertainty();
    testClearAndInconclusiveStayOutcomeOnly();
    testMalformedReportsFailClosed();
    testStableNames();
    std::puts("Airspace Guard controller tests passed");
    return 0;
}
