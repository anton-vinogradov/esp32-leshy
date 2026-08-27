#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/guard/AirspaceGuard.h"

namespace leshy1::apps::guard {

enum class AirspaceGuardView : std::uint8_t {
    Outcome,
    Finding,
    EvidenceList,
    EvidenceDetail,
};

enum class AirspaceGuardLoadStatus : std::uint8_t {
    Ready,
    InvalidReport,
};

const char* airspaceGuardViewName(AirspaceGuardView view);
const char* airspaceGuardLoadStatusName(AirspaceGuardLoadStatus status);

// User-facing navigation over one immutable detector report. The controller owns
// no capture, radio, Action or response path. It orders findings once on load so
// live signal changes cannot move the selection under the user's cursor.
class AirspaceGuardController final {
public:
    AirspaceGuardLoadStatus load(
        const services::guard::AirspaceGuardReport& report);
    void reset();

    bool next();
    bool previous();
    bool openSelected();
    bool back();

    AirspaceGuardView view() const { return view_; }
    AirspaceGuardLoadStatus loadStatus() const { return loadStatus_; }
    services::guard::AirspaceGuardStatus outcome() const {
        return report_.status;
    }
    bool hasFinding() const { return report_.findingCount != 0U; }
    bool evidenceIncomplete() const;
    std::size_t findingCount() const { return report_.findingCount; }
    std::size_t findingSelection() const { return findingSelection_; }
    std::size_t evidenceSelection() const { return evidenceSelection_; }
    std::size_t framesAvailable() const { return report_.framesAvailable; }
    std::size_t framesInspected() const { return report_.framesInspected; }
    std::size_t malformedFrames() const { return report_.malformedFrames; }
    std::size_t sourceReadFailures() const {
        return report_.sourceReadFailures;
    }
    std::size_t findingsDropped() const { return report_.findingsDropped; }
    bool inspectionTruncated() const { return report_.inspectionTruncated; }

    const services::guard::AirspaceFinding* finding(
        std::size_t orderedIndex) const;
    const services::guard::AirspaceFinding* selectedFinding() const;
    const services::guard::AirspaceEvidenceRef* selectedEvidence() const;

private:
    bool validateReport(
        const services::guard::AirspaceGuardReport& report) const;
    void buildFindingOrder();

    services::guard::AirspaceGuardReport report_{};
    std::array<std::size_t,
               services::guard::AirspaceGuardReport::kFindingCapacity>
        findingOrder_{};
    AirspaceGuardView view_ = AirspaceGuardView::Outcome;
    AirspaceGuardLoadStatus loadStatus_ =
        AirspaceGuardLoadStatus::InvalidReport;
    std::size_t findingSelection_ = 0;
    std::size_t evidenceSelection_ = 0;
};

}  // namespace leshy1::apps::guard
