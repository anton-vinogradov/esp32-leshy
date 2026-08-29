#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/auth/WifiAuthenticationCapture.h"

namespace leshy1::apps::auth {

enum class WifiAuthenticationCaptureView : std::uint8_t {
    Outcome,
    Actions,
    PeerDetail,
    EvidenceList,
    EvidenceDetail,
};

enum class WifiAuthenticationCaptureAction : std::uint8_t {
    Details,
    Save,
    Repeat,
};

enum class WifiAuthenticationCaptureLoadStatus : std::uint8_t {
    Ready,
    InvalidReport,
};

const char* wifiAuthenticationCaptureViewName(
    WifiAuthenticationCaptureView view);
const char* wifiAuthenticationCaptureActionName(
    WifiAuthenticationCaptureAction action);

// Allocation-free navigation over one immutable terminal report. The caller
// owns the report and must keep it unchanged until reset(). No captured packet
// bytes are copied or retained here.
class WifiAuthenticationCaptureController final {
public:
    static constexpr std::size_t kActionCapacity = 3U;

    WifiAuthenticationCaptureLoadStatus load(
        const services::auth::WifiAuthenticationCaptureReport& report,
        bool saveAvailable = true);
    void reset();

    bool next();
    bool previous();
    bool openSelected();
    bool back();

    WifiAuthenticationCaptureView view() const { return view_; }
    WifiAuthenticationCaptureLoadStatus loadStatus() const {
        return loadStatus_;
    }
    bool ready() const {
        return loadStatus_ == WifiAuthenticationCaptureLoadStatus::Ready &&
            report_ != nullptr;
    }
    bool hasDetails() const;
    bool saveAvailable() const;
    bool reportOpenable() const;

    std::size_t actionCount() const;
    std::size_t actionSelection() const { return actionSelection_; }
    WifiAuthenticationCaptureAction selectedAction() const;

    std::size_t peerSelection() const { return peerSelection_; }
    std::size_t selectedPeerPosition() const;
    std::size_t peerCount() const;
    std::size_t evidenceSelection() const { return evidenceSelection_; }
    const services::auth::WifiAuthenticationCaptureReport* report() const {
        return report_;
    }
    const services::auth::WifiAuthenticationPeer* selectedPeer() const;
    const services::auth::WifiAuthenticationEvidence* selectedEvidence()
        const;
    std::size_t evidenceCount() const;
    const services::auth::WifiAuthenticationEvidence* evidenceAt(
        std::size_t orderedIndex) const;
    std::size_t evidenceReportIndexAt(std::size_t orderedIndex) const;
    bool evidenceHasPmkid(std::size_t orderedIndex) const;
    std::size_t selectedEvidenceReportIndex() const;
    bool selectedEvidenceHasPmkid() const;
    std::size_t selectedPeerEvidenceCount() const;

private:
    bool validateReport(
        const services::auth::WifiAuthenticationCaptureReport& report) const;
    void buildEvidenceOrder();
    void selectMostUsefulPeer();
    bool peerUseful(std::size_t reportIndex) const;

    const services::auth::WifiAuthenticationCaptureReport* report_ = nullptr;
    std::array<std::uint8_t,
               services::auth::WifiAuthenticationCaptureReport::
                   kEvidenceCapacity>
        evidenceOrder_{};
    WifiAuthenticationCaptureView view_ =
        WifiAuthenticationCaptureView::Outcome;
    WifiAuthenticationCaptureLoadStatus loadStatus_ =
        WifiAuthenticationCaptureLoadStatus::InvalidReport;
    std::size_t actionSelection_ = 0U;
    std::size_t peerSelection_ = 0U;
    std::size_t evidenceSelection_ = 0U;
    bool saveAvailable_ = false;
};

}  // namespace leshy1::apps::auth
