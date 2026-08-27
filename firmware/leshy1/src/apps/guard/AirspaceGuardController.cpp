#include "AirspaceGuardController.h"

#include <cstring>

namespace leshy1::apps::guard {

namespace {

using services::guard::AirspaceConfidence;
using services::guard::AirspaceFinding;
using services::guard::AirspaceGuardReport;
using services::guard::AirspaceGuardStatus;

std::uint8_t confidenceRank(AirspaceConfidence confidence) {
    switch (confidence) {
        case AirspaceConfidence::High: return 3;
        case AirspaceConfidence::Medium: return 2;
        case AirspaceConfidence::Low: return 1;
    }
    return 0;
}

bool validTransmitter(const std::array<std::uint8_t, 6>& address) {
    if ((address[0] & 0x01U) != 0U) return false;
    bool any = false;
    bool allOnes = true;
    for (const std::uint8_t byte : address) {
        any = any || byte != 0U;
        allOnes = allOnes && byte == 0xffU;
    }
    return any && !allOnes;
}

bool comesBefore(const AirspaceFinding& left,
                 const AirspaceFinding& right) {
    const std::uint8_t leftConfidence = confidenceRank(left.confidence);
    const std::uint8_t rightConfidence = confidenceRank(right.confidence);
    if (leftConfidence != rightConfidence) {
        return leftConfidence > rightConfidence;
    }

    const std::uint32_t leftStrength =
        static_cast<std::uint32_t>(left.observed) * right.threshold;
    const std::uint32_t rightStrength =
        static_cast<std::uint32_t>(right.observed) * left.threshold;
    if (leftStrength != rightStrength) return leftStrength > rightStrength;
    if (left.lastUs != right.lastUs) return left.lastUs > right.lastUs;
    return std::memcmp(left.transmitter.data(), right.transmitter.data(),
                       left.transmitter.size()) < 0;
}

}  // namespace

const char* airspaceGuardViewName(AirspaceGuardView view) {
    switch (view) {
        case AirspaceGuardView::Outcome: return "outcome";
        case AirspaceGuardView::Finding: return "finding";
        case AirspaceGuardView::EvidenceList: return "evidence_list";
        case AirspaceGuardView::EvidenceDetail: return "evidence_detail";
    }
    return "unknown";
}

const char* airspaceGuardLoadStatusName(AirspaceGuardLoadStatus status) {
    switch (status) {
        case AirspaceGuardLoadStatus::Ready: return "ready";
        case AirspaceGuardLoadStatus::InvalidReport: return "invalid_report";
    }
    return "unknown";
}

bool AirspaceGuardController::validateReport(
    const AirspaceGuardReport& report) const {
    if (report.findingCount > report.findings.size()) return false;
    if ((report.status == AirspaceGuardStatus::Finding) !=
        (report.findingCount != 0U)) {
        return false;
    }
    for (std::size_t index = 0; index < report.findingCount; ++index) {
        const AirspaceFinding& finding = report.findings[index];
        if (finding.detectorVersion == 0U || finding.threshold < 2U ||
            finding.threshold > AirspaceFinding::kEvidenceCapacity ||
            finding.observed < finding.threshold ||
            finding.evidenceCount == 0U ||
            finding.evidenceCount > finding.evidence.size() ||
            finding.evidenceCount > finding.observed ||
            finding.firstUs == 0U || finding.lastUs < finding.firstUs ||
            !validTransmitter(finding.transmitter) ||
            static_cast<std::size_t>(finding.deauthenticationFrames) +
                    finding.disassociationFrames !=
                finding.observed) {
            return false;
        }
        for (std::size_t evidenceIndex = 0;
             evidenceIndex < finding.evidenceCount; ++evidenceIndex) {
            const services::guard::AirspaceEvidenceRef& evidence =
                finding.evidence[evidenceIndex];
            if (evidence.monotonicUs < finding.firstUs ||
                evidence.monotonicUs > finding.lastUs ||
                evidence.channel == 0U || evidence.channel > 14U) {
                return false;
            }
        }
    }
    return true;
}

void AirspaceGuardController::buildFindingOrder() {
    for (std::size_t index = 0; index < report_.findingCount; ++index) {
        findingOrder_[index] = index;
    }
    for (std::size_t index = 1; index < report_.findingCount; ++index) {
        const std::size_t value = findingOrder_[index];
        std::size_t insertion = index;
        while (insertion > 0U &&
               comesBefore(report_.findings[value],
                           report_.findings[findingOrder_[insertion - 1U]])) {
            findingOrder_[insertion] = findingOrder_[insertion - 1U];
            --insertion;
        }
        findingOrder_[insertion] = value;
    }
}

AirspaceGuardLoadStatus AirspaceGuardController::load(
    const AirspaceGuardReport& report) {
    reset();
    if (!validateReport(report)) return loadStatus_;
    report_ = report;
    buildFindingOrder();
    loadStatus_ = AirspaceGuardLoadStatus::Ready;
    view_ = hasFinding() ? AirspaceGuardView::Finding
                         : AirspaceGuardView::Outcome;
    return loadStatus_;
}

void AirspaceGuardController::reset() {
    report_ = {};
    findingOrder_.fill(0U);
    view_ = AirspaceGuardView::Outcome;
    loadStatus_ = AirspaceGuardLoadStatus::InvalidReport;
    findingSelection_ = 0;
    evidenceSelection_ = 0;
}

bool AirspaceGuardController::next() {
    if (view_ == AirspaceGuardView::Finding &&
        findingSelection_ + 1U < findingCount()) {
        ++findingSelection_;
        evidenceSelection_ = 0;
        return true;
    }
    const AirspaceFinding* selected = selectedFinding();
    if (view_ == AirspaceGuardView::EvidenceList && selected != nullptr &&
        evidenceSelection_ + 1U < selected->evidenceCount) {
        ++evidenceSelection_;
        return true;
    }
    return false;
}

bool AirspaceGuardController::previous() {
    if (view_ == AirspaceGuardView::Finding && findingSelection_ > 0U) {
        --findingSelection_;
        evidenceSelection_ = 0;
        return true;
    }
    if (view_ == AirspaceGuardView::EvidenceList && evidenceSelection_ > 0U) {
        --evidenceSelection_;
        return true;
    }
    return false;
}

bool AirspaceGuardController::openSelected() {
    const AirspaceFinding* selected = selectedFinding();
    if (view_ == AirspaceGuardView::Finding && selected != nullptr &&
        selected->evidenceCount != 0U) {
        evidenceSelection_ = 0;
        view_ = AirspaceGuardView::EvidenceList;
        return true;
    }
    if (view_ == AirspaceGuardView::EvidenceList &&
        selectedEvidence() != nullptr) {
        view_ = AirspaceGuardView::EvidenceDetail;
        return true;
    }
    return false;
}

bool AirspaceGuardController::back() {
    if (view_ == AirspaceGuardView::EvidenceDetail) {
        view_ = AirspaceGuardView::EvidenceList;
        return true;
    }
    if (view_ == AirspaceGuardView::EvidenceList) {
        view_ = AirspaceGuardView::Finding;
        return true;
    }
    return false;
}

bool AirspaceGuardController::evidenceIncomplete() const {
    return report_.sourceReadFailures != 0U ||
        report_.malformedFrames != 0U || report_.findingsDropped != 0U ||
        report_.inspectionTruncated;
}

const AirspaceFinding* AirspaceGuardController::finding(
    std::size_t orderedIndex) const {
    if (orderedIndex >= report_.findingCount) return nullptr;
    return &report_.findings[findingOrder_[orderedIndex]];
}

const AirspaceFinding* AirspaceGuardController::selectedFinding() const {
    return finding(findingSelection_);
}

const services::guard::AirspaceEvidenceRef*
AirspaceGuardController::selectedEvidence() const {
    const AirspaceFinding* selected = selectedFinding();
    if (selected == nullptr || evidenceSelection_ >= selected->evidenceCount) {
        return nullptr;
    }
    return &selected->evidence[evidenceSelection_];
}

}  // namespace leshy1::apps::guard
