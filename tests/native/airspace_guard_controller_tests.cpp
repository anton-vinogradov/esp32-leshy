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

void setCompleteCounters(AirspaceGuardReport& report,
                         std::size_t frames,
                         std::size_t disconnectFrames) {
    report.framesAvailable = frames;
    report.framesInspected = frames;
    report.disconnectFrames = disconnectFrames;
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
    setCompleteCounters(report, 24, 14);

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
    setCompleteCounters(report, 16, 4);

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
    report.framesAvailable = 65;
    report.framesInspected = 63;
    report.disconnectFrames = 4;
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
    clear.framesAvailable = 1;
    clear.framesInspected = 1;
    CHECK(controller.load(clear) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.view() == AirspaceGuardView::Outcome);
    CHECK(controller.outcome() == AirspaceGuardStatus::Clear);
    CHECK(!controller.openSelected());

    AirspaceGuardReport inconclusive{};
    inconclusive.status = AirspaceGuardStatus::Inconclusive;
    inconclusive.framesAvailable = 1;
    inconclusive.sourceReadFailures = 1;
    CHECK(controller.load(inconclusive) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.outcome() == AirspaceGuardStatus::Inconclusive);
    CHECK(controller.evidenceIncomplete());

    AirspaceGuardReport empty{};
    empty.status = AirspaceGuardStatus::Inconclusive;
    CHECK(controller.load(empty) == AirspaceGuardLoadStatus::Ready);
    CHECK(controller.evidenceIncomplete());
}

void testOutcomeStatusMismatchFailsClosed() {
    AirspaceGuardController controller;
    AirspaceGuardReport emptyClear{};
    emptyClear.status = AirspaceGuardStatus::Clear;
    CHECK(controller.load(emptyClear) ==
          AirspaceGuardLoadStatus::InvalidReport);

    AirspaceGuardReport falseInconclusive{};
    falseInconclusive.status = AirspaceGuardStatus::Inconclusive;
    falseInconclusive.framesAvailable = 1;
    falseInconclusive.framesInspected = 1;
    CHECK(controller.load(falseInconclusive) ==
          AirspaceGuardLoadStatus::InvalidReport);

    AirspaceGuardReport invalidPolicyWithEvidence{};
    invalidPolicyWithEvidence.status = AirspaceGuardStatus::InvalidPolicy;
    invalidPolicyWithEvidence.framesAvailable = 1;
    invalidPolicyWithEvidence.framesInspected = 1;
    CHECK(controller.load(invalidPolicyWithEvidence) ==
          AirspaceGuardLoadStatus::InvalidReport);

    AirspaceGuardReport omittedWithoutFinding{};
    omittedWithoutFinding.status = AirspaceGuardStatus::Clear;
    omittedWithoutFinding.framesAvailable = 1;
    omittedWithoutFinding.framesInspected = 1;
    omittedWithoutFinding.disconnectFrames = 1;
    omittedWithoutFinding.findingsDropped = 1;
    CHECK(controller.load(omittedWithoutFinding) ==
          AirspaceGuardLoadStatus::InvalidReport);
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
    setCompleteCounters(malformed, 16, 4);
    malformed.findings[0].evidence[0].channel = 0;
    CHECK(controller.load(malformed) ==
          AirspaceGuardLoadStatus::InvalidReport);
    CHECK(controller.view() == AirspaceGuardView::Outcome);
    CHECK(!controller.hasFinding());
}

void testOutOfBoundsEvidenceFailsClosed() {
    AirspaceGuardController controller;
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1;
    report.findings[0] = makeFinding(
        kSourceA, AirspaceConfidence::Medium, 4, 4, 1000000, 1300000);
    setCompleteCounters(report, 16, 4);

    report.findings[0].evidence[0].frameIndex = 16;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);

    report.findings[0].evidence[0].frameIndex = 10;
    report.findings[0].lastUs = 11000001ULL;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);

    report.findings[0].lastUs = 1300000ULL;
    report.findings[0].evidence[0].rssiDbm = 1;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);

    report.findings[0].evidence[0].rssiDbm = -40;
    report.framesInspected = 15;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);

    report.framesInspected = 16;
    report.findingCount = 2;
    report.findings[1] = report.findings[0];
    report.disconnectFrames = 8;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);
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
    testOutcomeStatusMismatchFailsClosed();
    testMalformedReportsFailClosed();
    testOutOfBoundsEvidenceFailsClosed();
    testStableNames();
    std::puts("Airspace Guard controller tests passed");
    return 0;
}
