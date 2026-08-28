#include "AirspaceGuardController.h"

#include <cstring>

namespace leshy1::apps::guard {

namespace {

using services::guard::AirspaceBleTrackerProtocol;
using services::guard::AirspaceConfidence;
using services::guard::AirspaceFinding;
using services::guard::AirspaceFindingKind;
using services::guard::AirspaceGuardReport;
using services::guard::AirspaceGuardStatus;
using services::guard::AirspaceWifiSecurity;

std::uint8_t confidenceRank(AirspaceConfidence confidence) {
    switch (confidence) {
        case AirspaceConfidence::High: return 3;
        case AirspaceConfidence::Medium: return 2;
        case AirspaceConfidence::Low: return 1;
    }
    return 0;
}

bool validIdentity(const std::array<std::uint8_t, 6>& address) {
    bool any = false;
    bool allOnes = true;
    for (const std::uint8_t byte : address) {
        any = any || byte != 0U;
        allOnes = allOnes && byte == 0xffU;
    }
    return any && !allOnes;
}

bool validTransmitter(const std::array<std::uint8_t, 6>& address) {
    return (address[0] & 0x01U) == 0U && validIdentity(address);
}

bool emptyTransmitter(const std::array<std::uint8_t, 6>& address) {
    for (const std::uint8_t byte : address) {
        if (byte != 0U) return false;
    }
    return true;
}

bool validConfidence(AirspaceConfidence confidence) {
    switch (confidence) {
        case AirspaceConfidence::Low:
        case AirspaceConfidence::Medium:
        case AirspaceConfidence::High:
            return true;
    }
    return false;
}

bool validSecurity(AirspaceWifiSecurity security) {
    switch (security) {
        case AirspaceWifiSecurity::Open:
        case AirspaceWifiSecurity::LegacyPrivacy:
        case AirspaceWifiSecurity::Wpa:
        case AirspaceWifiSecurity::Rsn:
            return true;
        case AirspaceWifiSecurity::Unknown:
            return false;
    }
    return false;
}

bool validBleTrackerProtocol(AirspaceBleTrackerProtocol protocol) {
    switch (protocol) {
        case AirspaceBleTrackerProtocol::FindMy:
        case AirspaceBleTrackerProtocol::SmartTag:
        case AirspaceBleTrackerProtocol::Tile:
            return true;
        case AirspaceBleTrackerProtocol::None:
            return false;
    }
    return false;
}

bool sameNetworkName(const AirspaceFinding& left,
                     const AirspaceFinding& right) {
    return left.networkNameLength == right.networkNameLength &&
        left.networkNameLength != 0U &&
        std::memcmp(left.networkName.data(), right.networkName.data(),
                    left.networkNameLength) == 0;
}

bool duplicateFinding(const AirspaceFinding& left,
                      const AirspaceFinding& right) {
    if (left.kind != right.kind) return false;
    switch (left.kind) {
        case AirspaceFindingKind::WifiDisconnectBurst:
            return left.transmitter == right.transmitter;
        case AirspaceFindingKind::WifiSsidSecurityConflict:
            return sameNetworkName(left, right);
        case AirspaceFindingKind::WifiSsidChurn:
            return left.transmitter == right.transmitter;
        case AirspaceFindingKind::WifiElevatedNoise:
            return left.evidenceCount != 0U && right.evidenceCount != 0U &&
                left.evidence[0].channel == right.evidence[0].channel;
        case AirspaceFindingKind::BleTrackerPresence:
            return left.transmitter == right.transmitter &&
                left.bleTrackerProtocol == right.bleTrackerProtocol &&
                left.bleAddressType == right.bleAddressType;
    }
    return true;
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
    const std::size_t sourceInspectionCapacity =
        services::guard::AirspaceGuard::kFrameInspectionCapacity;
    // A product result can contain two independently bounded detector
    // reports. A single-source truncated report still has at most 64 attempted
    // records, while a merged Wi-Fi + BLE report can legitimately contain up
    // to 128. Derive that distinction from the already-accounted attempted
    // count instead of rejecting a dense but complete merged observation.
    const bool mergedInspectionBudget =
        report.framesInspected > sourceInspectionCapacity ||
        (report.framesInspected <= sourceInspectionCapacity &&
         report.sourceReadFailures >
             sourceInspectionCapacity - report.framesInspected);
    const std::size_t inspectionCapacity = mergedInspectionBudget
        ? services::guard::AirspaceGuard::kMergedFrameInspectionCapacity
        : sourceInspectionCapacity;
    const std::size_t attempted = report.framesAvailable < inspectionCapacity
        ? report.framesAvailable : inspectionCapacity;
    if (report.findingCount > report.findings.size()) return false;
    if (report.status == AirspaceGuardStatus::InvalidPolicy) {
        return report.findingCount == 0U && report.framesAvailable == 0U &&
            report.sourceFramesObserved == 0U &&
            report.framesInspected == 0U && report.disconnectFrames == 0U &&
            report.identityAdvertisementFrames == 0U &&
            report.bleAdvertisementRecords == 0U &&
            report.wifiNoiseSamplesObserved == 0U &&
            report.wifiNoiseSamplesAvailable == 0U &&
            report.wifiNoiseSamplesInspected == 0U &&
            report.wifiNoiseSamplesDropped == 0U &&
            report.wifiNoiseSamplesMalformed == 0U &&
            report.malformedFrames == 0U &&
            report.sourceReadFailures == 0U &&
            report.sourceFramesDropped == 0U &&
            report.findingsDropped == 0U && !report.inspectionTruncated;
    }
    if (report.sourceFramesObserved < report.framesAvailable ||
        report.sourceFramesDropped > report.sourceFramesObserved ||
        report.framesInspected > attempted ||
        report.sourceReadFailures > attempted ||
        report.framesInspected + report.sourceReadFailures != attempted ||
        report.disconnectFrames > report.framesInspected ||
        report.identityAdvertisementFrames > report.framesInspected ||
        report.bleAdvertisementRecords > report.framesInspected ||
        report.wifiNoiseSamplesAvailable >
            services::guard::kWifiNoiseFloorLiveRetentionCapacity ||
        report.wifiNoiseSamplesObserved <
            report.wifiNoiseSamplesAvailable +
                report.wifiNoiseSamplesDropped ||
        report.wifiNoiseSamplesDropped >
            report.wifiNoiseSamplesObserved ||
        report.wifiNoiseSamplesInspected +
                report.wifiNoiseSamplesMalformed !=
            report.wifiNoiseSamplesAvailable ||
        report.malformedFrames > report.framesInspected ||
        report.disconnectFrames + report.identityAdvertisementFrames +
                report.bleAdvertisementRecords + report.malformedFrames >
            report.framesInspected ||
        report.findingsDropped >
            report.framesInspected + report.wifiNoiseSamplesInspected ||
        (report.findingCount == 0U && report.findingsDropped != 0U) ||
        report.inspectionTruncated !=
            (report.framesAvailable > inspectionCapacity)) {
        return false;
    }
    const AirspaceGuardStatus expectedStatus = report.findingCount != 0U
        ? AirspaceGuardStatus::Finding
        : (report.sourceFramesObserved == 0U ||
                   report.framesAvailable == 0U ||
                   report.framesInspected == 0U ||
                   report.sourceReadFailures != 0U ||
                   report.sourceFramesDropped != 0U ||
                   report.malformedFrames != 0U ||
                   report.wifiNoiseSamplesDropped != 0U ||
                   report.wifiNoiseSamplesMalformed != 0U ||
                   report.inspectionTruncated
               ? AirspaceGuardStatus::Inconclusive
               : AirspaceGuardStatus::Clear);
    if (report.status != expectedStatus) return false;
    std::size_t reportedDisconnectFrames = 0U;
    // Identity findings may intentionally reference the same source frames:
    // each detector validates against the retained identity population rather
    // than inventing mutually exclusive ownership of immutable evidence.
    for (std::size_t index = 0; index < report.findingCount; ++index) {
        const AirspaceFinding& finding = report.findings[index];
        for (std::size_t previous = 0; previous < index; ++previous) {
            if (duplicateFinding(finding, report.findings[previous])) {
                return false;
            }
        }
        if (!validConfidence(finding.confidence) ||
            finding.detectorVersion == 0U || finding.threshold < 2U ||
            finding.threshold > AirspaceFinding::kEvidenceCapacity ||
            finding.observed < finding.threshold ||
            finding.observed > sourceInspectionCapacity ||
            finding.evidenceCount == 0U ||
            finding.evidenceCount > finding.evidence.size() ||
            finding.evidenceCount > finding.observed ||
            finding.firstUs == 0U || finding.lastUs < finding.firstUs ||
            (finding.kind == AirspaceFindingKind::BleTrackerPresence
                 ? !validIdentity(finding.transmitter)
                 : (finding.kind == AirspaceFindingKind::WifiElevatedNoise
                        ? !emptyTransmitter(finding.transmitter)
                        : !validTransmitter(finding.transmitter)))) {
            return false;
        }
        if (finding.kind != AirspaceFindingKind::WifiElevatedNoise &&
            finding.noiseFloorThresholdDbm != -127) {
            return false;
        }
        switch (finding.kind) {
            case AirspaceFindingKind::WifiDisconnectBurst:
                if (finding.detectorVersion !=
                        AirspaceFinding::kWifiDisconnectDetectorVersion ||
                    finding.lastUs - finding.firstUs > 10000000ULL ||
                    !emptyTransmitter(finding.relatedTransmitter) ||
                    finding.networkNameLength != 0U ||
                    finding.primarySecurity != AirspaceWifiSecurity::Unknown ||
                    finding.relatedSecurity != AirspaceWifiSecurity::Unknown ||
                    finding.bleTrackerProtocol !=
                        services::guard::AirspaceBleTrackerProtocol::None ||
                    finding.bleAddressType != 0xffU ||
                    static_cast<std::size_t>(
                        finding.deauthenticationFrames) +
                            finding.disassociationFrames !=
                        finding.observed) {
                    return false;
                }
                reportedDisconnectFrames += finding.observed;
                if (reportedDisconnectFrames > report.disconnectFrames) {
                    return false;
                }
                break;
            case AirspaceFindingKind::WifiSsidSecurityConflict:
                if (finding.detectorVersion !=
                        AirspaceFinding::kWifiIdentityDetectorVersion ||
                    finding.lastUs - finding.firstUs > 10000000ULL ||
                    finding.confidence != AirspaceConfidence::Medium ||
                    finding.threshold != 2U || finding.observed != 2U ||
                    finding.evidenceCount != 2U ||
                    finding.deauthenticationFrames != 0U ||
                    finding.disassociationFrames != 0U ||
                    !validTransmitter(finding.relatedTransmitter) ||
                    finding.transmitter == finding.relatedTransmitter ||
                    finding.networkNameLength == 0U ||
                    finding.networkNameLength > finding.networkName.size() ||
                    !validSecurity(finding.primarySecurity) ||
                    !validSecurity(finding.relatedSecurity) ||
                    finding.bleTrackerProtocol !=
                        services::guard::AirspaceBleTrackerProtocol::None ||
                    finding.bleAddressType != 0xffU ||
                    finding.primarySecurity == finding.relatedSecurity) {
                    return false;
                }
                if (finding.observed > report.identityAdvertisementFrames) {
                    return false;
                }
                break;
            case AirspaceFindingKind::WifiSsidChurn:
                if (finding.detectorVersion !=
                        AirspaceFinding::kWifiSsidChurnDetectorVersion ||
                    finding.lastUs - finding.firstUs > 10000000ULL ||
                    finding.confidence == AirspaceConfidence::Low ||
                    finding.threshold < 3U ||
                    finding.evidenceCount != finding.observed ||
                    finding.deauthenticationFrames != 0U ||
                    finding.disassociationFrames != 0U ||
                    !emptyTransmitter(finding.relatedTransmitter) ||
                    finding.networkNameLength != 0U ||
                    finding.primarySecurity != AirspaceWifiSecurity::Unknown ||
                    finding.relatedSecurity != AirspaceWifiSecurity::Unknown ||
                    finding.bleTrackerProtocol !=
                        services::guard::AirspaceBleTrackerProtocol::None ||
                    finding.bleAddressType != 0xffU ||
                    finding.observed > report.identityAdvertisementFrames) {
                    return false;
                }
                break;
            case AirspaceFindingKind::WifiElevatedNoise:
                if (finding.detectorVersion !=
                        AirspaceFinding::kWifiElevatedNoiseDetectorVersion ||
                    finding.lastUs - finding.firstUs > 10000000ULL ||
                    finding.confidence != AirspaceConfidence::Low ||
                    finding.noiseFloorThresholdDbm < -100 ||
                    finding.noiseFloorThresholdDbm > -30 ||
                    finding.deauthenticationFrames != 0U ||
                    finding.disassociationFrames != 0U ||
                    !emptyTransmitter(finding.relatedTransmitter) ||
                    finding.networkNameLength != 0U ||
                    finding.primarySecurity != AirspaceWifiSecurity::Unknown ||
                    finding.relatedSecurity != AirspaceWifiSecurity::Unknown ||
                    finding.bleTrackerProtocol !=
                        services::guard::AirspaceBleTrackerProtocol::None ||
                    finding.bleAddressType != 0xffU ||
                    finding.evidenceCount !=
                        (finding.observed < finding.evidence.size()
                             ? finding.observed : finding.evidence.size()) ||
                    finding.observed > report.wifiNoiseSamplesInspected) {
                    return false;
                }
                break;
            case AirspaceFindingKind::BleTrackerPresence:
                if (finding.detectorVersion !=
                        AirspaceFinding::kBleTrackerPresenceDetectorVersion ||
                    finding.lastUs - finding.firstUs > 60000000ULL ||
                    finding.confidence == AirspaceConfidence::Low ||
                    finding.deauthenticationFrames != 0U ||
                    finding.disassociationFrames != 0U ||
                    !emptyTransmitter(finding.relatedTransmitter) ||
                    finding.networkNameLength != 0U ||
                    finding.primarySecurity != AirspaceWifiSecurity::Unknown ||
                    finding.relatedSecurity != AirspaceWifiSecurity::Unknown ||
                    !validBleTrackerProtocol(finding.bleTrackerProtocol) ||
                    finding.bleAddressType > 3U ||
                    finding.evidenceCount !=
                        (finding.observed < finding.evidence.size()
                             ? finding.observed : finding.evidence.size()) ||
                    finding.observed > report.bleAdvertisementRecords) {
                    return false;
                }
                break;
            default:
                return false;
        }
        for (std::size_t evidenceIndex = 0;
             evidenceIndex < finding.evidenceCount; ++evidenceIndex) {
            const services::guard::AirspaceEvidenceRef& evidence =
                finding.evidence[evidenceIndex];
            if (evidence.monotonicUs < finding.firstUs ||
                evidence.monotonicUs > finding.lastUs ||
                (finding.kind == AirspaceFindingKind::WifiElevatedNoise
                     ? evidence.frameIndex >= report.sourceFramesObserved
                     : evidence.frameIndex >= attempted) ||
                (finding.kind == AirspaceFindingKind::BleTrackerPresence
                     ? evidence.channel != 0U
                     : (evidence.channel == 0U || evidence.channel > 14U)) ||
                evidence.rssiDbm < -127 || evidence.rssiDbm > 0 ||
                (finding.kind == AirspaceFindingKind::WifiElevatedNoise
                     ? !services::guard::isWifiNoiseFloorCandidate(
                           evidence.noiseFloorDbm)
                     : evidence.noiseFloorDbm != -127)) {
                return false;
            }
            if (finding.kind == AirspaceFindingKind::WifiElevatedNoise &&
                evidence.noiseFloorDbm <
                    finding.noiseFloorThresholdDbm) {
                return false;
            }
            for (std::size_t previousEvidence = 0;
                 previousEvidence < evidenceIndex; ++previousEvidence) {
                if (finding.evidence[previousEvidence].frameIndex ==
                    evidence.frameIndex) {
                    return false;
                }
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
    return report_.sourceFramesObserved == 0U ||
        report_.framesAvailable == 0U || report_.framesInspected == 0U ||
        report_.sourceReadFailures != 0U ||
        report_.sourceFramesDropped != 0U ||
        report_.malformedFrames != 0U ||
        report_.wifiNoiseSamplesDropped != 0U ||
        report_.wifiNoiseSamplesMalformed != 0U ||
        report_.findingsDropped != 0U ||
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
