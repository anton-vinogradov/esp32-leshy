#include "WifiAuthenticationCaptureController.h"

#include <limits>

namespace leshy1::apps::auth {
namespace {

using services::auth::WifiAuthenticationCaptureOutcome;
using services::auth::WifiAuthenticationCaptureReport;
using services::auth::WifiAuthenticationEvidence;
using services::auth::WifiAuthenticationPeer;

std::uint8_t messageCount(std::uint8_t mask) {
    mask = static_cast<std::uint8_t>(mask & 0x0fU);
    std::uint8_t count = 0U;
    while (mask != 0U) {
        count = static_cast<std::uint8_t>(count + (mask & 1U));
        mask = static_cast<std::uint8_t>(mask >> 1U);
    }
    return count;
}

bool evidenceBefore(const WifiAuthenticationEvidence& left,
                    const WifiAuthenticationEvidence& right) {
    if (left.sourceFrameIndex != right.sourceFrameIndex) {
        return left.sourceFrameIndex < right.sourceFrameIndex;
    }
    return left.monotonicUs < right.monotonicUs;
}

}  // namespace

const char* wifiAuthenticationCaptureViewName(
    WifiAuthenticationCaptureView view) {
    switch (view) {
        case WifiAuthenticationCaptureView::Outcome: return "outcome";
        case WifiAuthenticationCaptureView::Actions: return "actions";
        case WifiAuthenticationCaptureView::PeerDetail:
            return "peer_detail";
        case WifiAuthenticationCaptureView::EvidenceList:
            return "evidence_list";
        case WifiAuthenticationCaptureView::EvidenceDetail:
            return "evidence_detail";
    }
    return "outcome";
}

const char* wifiAuthenticationCaptureActionName(
    WifiAuthenticationCaptureAction action) {
    switch (action) {
        case WifiAuthenticationCaptureAction::Details: return "details";
        case WifiAuthenticationCaptureAction::Repeat: return "repeat";
    }
    return "repeat";
}

WifiAuthenticationCaptureLoadStatus
WifiAuthenticationCaptureController::load(
    const WifiAuthenticationCaptureReport& report) {
    reset();
    if (!validateReport(report)) return loadStatus_;
    report_ = &report;
    loadStatus_ = WifiAuthenticationCaptureLoadStatus::Ready;
    buildEvidenceOrder();
    selectMostUsefulPeer();
    return loadStatus_;
}

void WifiAuthenticationCaptureController::reset() {
    report_ = nullptr;
    evidenceOrder_.fill(0U);
    view_ = WifiAuthenticationCaptureView::Outcome;
    loadStatus_ = WifiAuthenticationCaptureLoadStatus::InvalidReport;
    actionSelection_ = 0U;
    peerSelection_ = 0U;
    evidenceSelection_ = 0U;
}

bool WifiAuthenticationCaptureController::next() {
    if (!ready()) return false;
    if (view_ == WifiAuthenticationCaptureView::Actions) {
        if (actionSelection_ + 1U >= actionCount()) return false;
        ++actionSelection_;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::PeerDetail) {
        for (std::size_t index = peerSelection_ + 1U;
             index < report_->peerCount; ++index) {
            if (!peerUseful(index)) continue;
            peerSelection_ = index;
            return true;
        }
        return false;
    }
    if (view_ == WifiAuthenticationCaptureView::EvidenceList) {
        if (evidenceSelection_ + 1U >= report_->evidenceCount) return false;
        ++evidenceSelection_;
        return true;
    }
    return false;
}

bool WifiAuthenticationCaptureController::previous() {
    if (!ready()) return false;
    if (view_ == WifiAuthenticationCaptureView::Actions) {
        if (actionSelection_ == 0U) return false;
        --actionSelection_;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::PeerDetail) {
        for (std::size_t index = peerSelection_; index > 0U; --index) {
            const std::size_t candidate = index - 1U;
            if (!peerUseful(candidate)) continue;
            peerSelection_ = candidate;
            return true;
        }
        return false;
    }
    if (view_ == WifiAuthenticationCaptureView::EvidenceList) {
        if (evidenceSelection_ == 0U) return false;
        --evidenceSelection_;
        return true;
    }
    return false;
}

bool WifiAuthenticationCaptureController::openSelected() {
    if (!ready()) return false;
    if (view_ == WifiAuthenticationCaptureView::Outcome) {
        view_ = WifiAuthenticationCaptureView::Actions;
        actionSelection_ = 0U;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::Actions) {
        if (selectedAction() != WifiAuthenticationCaptureAction::Details ||
            !hasDetails()) {
            return false;
        }
        view_ = selectedPeer() != nullptr
            ? WifiAuthenticationCaptureView::PeerDetail
            : WifiAuthenticationCaptureView::EvidenceList;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::PeerDetail) {
        if (report_->evidenceCount == 0U) return false;
        view_ = WifiAuthenticationCaptureView::EvidenceList;
        evidenceSelection_ = 0U;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::EvidenceList &&
        selectedEvidence() != nullptr) {
        view_ = WifiAuthenticationCaptureView::EvidenceDetail;
        return true;
    }
    return false;
}

bool WifiAuthenticationCaptureController::back() {
    if (!ready()) return false;
    if (view_ == WifiAuthenticationCaptureView::EvidenceDetail) {
        view_ = WifiAuthenticationCaptureView::EvidenceList;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::EvidenceList) {
        view_ = selectedPeer() != nullptr
            ? WifiAuthenticationCaptureView::PeerDetail
            : WifiAuthenticationCaptureView::Actions;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::PeerDetail) {
        view_ = WifiAuthenticationCaptureView::Actions;
        return true;
    }
    if (view_ == WifiAuthenticationCaptureView::Actions) {
        view_ = WifiAuthenticationCaptureView::Outcome;
        return true;
    }
    return false;
}

bool WifiAuthenticationCaptureController::hasDetails() const {
    return ready() &&
        (peerCount() != 0U || report_->evidenceCount != 0U);
}

bool WifiAuthenticationCaptureController::reportOpenable() const {
    return ready();
}

std::size_t WifiAuthenticationCaptureController::actionCount() const {
    return hasDetails() ? kActionCapacity : 1U;
}

WifiAuthenticationCaptureAction
WifiAuthenticationCaptureController::selectedAction() const {
    if (!hasDetails()) return WifiAuthenticationCaptureAction::Repeat;
    return actionSelection_ == 0U
        ? WifiAuthenticationCaptureAction::Details
        : WifiAuthenticationCaptureAction::Repeat;
}

const WifiAuthenticationPeer*
WifiAuthenticationCaptureController::selectedPeer() const {
    return ready() && peerUseful(peerSelection_)
        ? &report_->peers[peerSelection_] : nullptr;
}

std::size_t WifiAuthenticationCaptureController::selectedPeerPosition()
    const {
    if (selectedPeer() == nullptr) return 0U;
    std::size_t position = 0U;
    for (std::size_t index = 0U; index < peerSelection_; ++index) {
        if (peerUseful(index)) ++position;
    }
    return position;
}

std::size_t WifiAuthenticationCaptureController::peerCount() const {
    if (!ready()) return 0U;
    std::size_t count = 0U;
    for (std::size_t index = 0U; index < report_->peerCount; ++index) {
        if (peerUseful(index)) ++count;
    }
    return count;
}

const WifiAuthenticationEvidence*
WifiAuthenticationCaptureController::selectedEvidence() const {
    return evidenceAt(evidenceSelection_);
}

std::size_t WifiAuthenticationCaptureController::evidenceCount() const {
    return ready() ? report_->evidenceCount : 0U;
}

const WifiAuthenticationEvidence*
WifiAuthenticationCaptureController::evidenceAt(
    std::size_t orderedIndex) const {
    const std::size_t index = evidenceReportIndexAt(orderedIndex);
    return ready() && index < report_->evidenceCount
        ? &report_->evidence[index] : nullptr;
}

std::size_t WifiAuthenticationCaptureController::evidenceReportIndexAt(
    std::size_t orderedIndex) const {
    return ready() && orderedIndex < report_->evidenceCount
        ? evidenceOrder_[orderedIndex]
        : std::numeric_limits<std::size_t>::max();
}

bool WifiAuthenticationCaptureController::evidenceHasPmkid(
    std::size_t orderedIndex) const {
    if (!ready()) return false;
    const WifiAuthenticationEvidence* evidence = evidenceAt(orderedIndex);
    if (evidence == nullptr) return false;
    for (std::size_t index = 0U; index < report_->pmkidCount; ++index) {
        if (report_->pmkids[index].sourceFrameIndex ==
            evidence->sourceFrameIndex) {
            return true;
        }
    }
    return false;
}

std::size_t
WifiAuthenticationCaptureController::selectedEvidenceReportIndex() const {
    return evidenceReportIndexAt(evidenceSelection_);
}

bool WifiAuthenticationCaptureController::selectedEvidenceHasPmkid() const {
    return evidenceHasPmkid(evidenceSelection_);
}

std::size_t
WifiAuthenticationCaptureController::selectedPeerEvidenceCount() const {
    const WifiAuthenticationPeer* peer = selectedPeer();
    if (peer == nullptr) return 0U;
    std::size_t count = 0U;
    for (const std::uint8_t index : peer->evidenceIndices) {
        if (index != WifiAuthenticationPeer::kMissingEvidence) ++count;
    }
    return count;
}

bool WifiAuthenticationCaptureController::validateReport(
    const WifiAuthenticationCaptureReport& report) const {
    if (report.evidenceCount > report.evidence.size() ||
        report.peerCount > report.peers.size() ||
        report.pmkidCount > report.pmkids.size()) {
        return false;
    }
    std::size_t completePeers = 0U;
    for (std::size_t peerIndex = 0U; peerIndex < report.peerCount;
         ++peerIndex) {
        const WifiAuthenticationPeer& peer = report.peers[peerIndex];
        if ((peer.messageMask & 0xf0U) != 0U) return false;
        for (const std::uint8_t evidenceIndex : peer.evidenceIndices) {
            if (evidenceIndex != WifiAuthenticationPeer::kMissingEvidence &&
                evidenceIndex >= report.evidenceCount) {
                return false;
            }
        }
        if (peer.complete) {
            if (peer.messageMask != 0x0fU ||
                !peer.sequenceConsistent ||
                !peer.replayCountersConsistent ||
                !peer.keyMaterialConsistent) {
                return false;
            }
            ++completePeers;
        }
    }
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        const WifiAuthenticationEvidence& evidence = report.evidence[index];
        if (evidence.sourceFrameIndex >= report.counters.sourceFrames ||
            evidence.monotonicUs == 0U || evidence.channel < 1U ||
            evidence.channel > 14U) {
            return false;
        }
    }
    for (std::size_t index = 0U; index < report.pmkidCount; ++index) {
        const auto& pmkid = report.pmkids[index];
        if (pmkid.sourceFrameIndex >= report.counters.sourceFrames ||
            pmkid.monotonicUs == 0U) {
            return false;
        }
    }
    if (report.outcome == WifiAuthenticationCaptureOutcome::Complete) {
        return report.uncertainty == 0U && completePeers != 0U;
    }
    if (report.outcome == WifiAuthenticationCaptureOutcome::Incomplete) {
        return report.uncertainty == 0U && completePeers == 0U &&
            (report.evidenceCount != 0U || report.pmkidCount != 0U);
    }
    return report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive &&
        report.uncertainty != 0U;
}

void WifiAuthenticationCaptureController::buildEvidenceOrder() {
    if (!ready()) return;
    for (std::size_t index = 0U; index < report_->evidenceCount; ++index) {
        evidenceOrder_[index] = static_cast<std::uint8_t>(index);
    }
    for (std::size_t index = 1U; index < report_->evidenceCount; ++index) {
        const std::uint8_t candidate = evidenceOrder_[index];
        std::size_t insertion = index;
        while (insertion > 0U &&
               evidenceBefore(report_->evidence[candidate],
                              report_->evidence[evidenceOrder_[insertion - 1U]])) {
            evidenceOrder_[insertion] = evidenceOrder_[insertion - 1U];
            --insertion;
        }
        evidenceOrder_[insertion] = candidate;
    }
}

void WifiAuthenticationCaptureController::selectMostUsefulPeer() {
    if (!ready() || report_->peerCount == 0U) return;
    std::size_t best = report_->peerCount;
    for (std::size_t index = 0U; index < report_->peerCount; ++index) {
        if (!peerUseful(index)) continue;
        if (best == report_->peerCount) {
            best = index;
            continue;
        }
        const WifiAuthenticationPeer& candidate = report_->peers[index];
        const WifiAuthenticationPeer& retained = report_->peers[best];
        if ((!retained.complete && candidate.complete) ||
            (retained.complete == candidate.complete &&
             messageCount(candidate.messageMask) >
                 messageCount(retained.messageMask))) {
            best = index;
        }
    }
    if (best != report_->peerCount) peerSelection_ = best;
}

bool WifiAuthenticationCaptureController::peerUseful(
    std::size_t reportIndex) const {
    return ready() && reportIndex < report_->peerCount &&
        report_->peers[reportIndex].messageMask != 0U;
}

}  // namespace leshy1::apps::auth
