#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/targets/TargetCatalog.h"
#include "domain/targets/TargetComparison.h"
#include "services/survey/SurveySession.h"

namespace leshy1::apps::targets {

enum class TargetsView : std::uint8_t {
    List,
    Detail,
    Actions,
    Compare,
    CompareDetail,
};

enum class TargetsLoadStatus : std::uint8_t {
    Ready,
    InvalidArgument,
    SessionUnavailable,
    AdmissionRejected,
    EvidenceUnavailable,
    CompareRejected,
};

const char* targetsLoadStatusName(TargetsLoadStatus status);

struct TargetProductBinding final {
    const services::survey::SurveySession* session = nullptr;
    std::uint32_t generation = 0;
};

struct TargetListRow final {
    domain::targets::TargetId targetId{};
    domain::targets::TargetIdentity identity{};
    domain::targets::TargetEvidenceRef evidence{};
    domain::observations::Observation latest{};
};

struct TargetComparisonSide final {
    domain::targets::TargetIdentity identity{};
    domain::targets::TargetEvidenceRef evidence{};
    domain::observations::Observation observation{};
    bool present = false;
};

// Explicit heap/lifecycle working set. Arduino product code creates it only
// while Targets owns the foreground; no member becomes permanent static RAM.
struct TargetsWorkspace final {
    domain::targets::TargetCatalog catalog{};
    domain::targets::TargetComparisonResult comparison{};
};

class TargetsController final {
public:
    explicit TargetsController(TargetsWorkspace& workspace)
        : workspace_(workspace) {}

    void reset();
    TargetsLoadStatus load(const TargetProductBinding& current);
    TargetsLoadStatus load(
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted);
    TargetsLoadStatus load(const TargetProductBinding& baseline,
                           const TargetProductBinding& current);
    TargetsLoadStatus load(
        const TargetProductBinding& baseline,
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted);
    bool next();
    bool previous();
    bool openSelected();
    bool openCompare();
    bool back();
    bool selectTarget(const domain::targets::TargetId& id);

    TargetsView view() const { return view_; }
    TargetsLoadStatus status() const { return status_; }
    std::size_t size() const { return rowCount_; }
    std::size_t entryCount() const {
        return rowCount_ + (comparisonAvailable_ ? 1U : 0U);
    }
    std::size_t selection() const { return selection_; }
    std::size_t comparisonSelection() const { return comparisonSelection_; }
    std::size_t navigationSelection() const {
        return view_ == TargetsView::Compare ||
                view_ == TargetsView::CompareDetail
            ? comparisonSelection_ : selection_;
    }
    std::size_t navigationCount() const {
        return view_ == TargetsView::Compare ||
                view_ == TargetsView::CompareDetail
            ? comparisonSize() : entryCount();
    }
    std::size_t sourceIdentityCount() const { return sourceIdentityCount_; }
    bool truncated() const { return truncated_; }
    bool compareAvailable() const { return comparisonAvailable_; }
    bool selectedIsCompare() const {
        return view_ == TargetsView::List && comparisonAvailable_ &&
               selection_ == 0;
    }
    const TargetListRow* row(std::size_t index) const;
    const TargetListRow* selectedRow() const;
    const domain::targets::TargetRecord* selectedTarget() const;
    std::size_t comparisonSize() const {
        return comparisonAvailable_ ? workspace_.comparison.size : 0U;
    }
    const domain::targets::TargetComparisonItem* comparisonItem(
        std::size_t index) const;
    const domain::targets::TargetComparisonItem* selectedComparisonItem()
        const;
    const TargetListRow* comparisonTargetRow(std::size_t index) const;
    bool comparisonSide(std::size_t index, bool current,
                        TargetComparisonSide* output) const;
    const domain::targets::TargetComparisonResult& comparison() const {
        return workspace_.comparison;
    }
    const domain::targets::TargetCatalog& catalog() const {
        return workspace_.catalog;
    }

private:
    TargetsLoadStatus loadBindings(const TargetProductBinding& baseline,
                                   const TargetProductBinding& current,
                                   bool compare,
                                   const domain::targets::TargetCatalog*
                                       persisted = nullptr);
    bool rebuildRows();
    bool rebuildComparisonOrder();
    bool comparisonItemBefore(std::uint8_t left, std::uint8_t right) const;
    bool loadComparisonSide(
        const domain::targets::TargetComparisonItem& item, bool current,
        TargetComparisonSide* output) const;
    bool loadExact(const domain::targets::TargetEvidenceRef& evidence,
                   domain::observations::Observation* output) const;

    TargetsWorkspace& workspace_;
    std::array<TargetListRow, domain::targets::TargetCatalog::kCapacity> rows_{};
    TargetProductBinding baseline_{};
    TargetProductBinding current_{};
    std::size_t rowCount_ = 0;
    std::size_t selection_ = 0;
    std::array<std::uint8_t, domain::targets::TargetComparisonResult::kCapacity>
        comparisonOrder_{};
    std::size_t comparisonSelection_ = 0;
    TargetsView view_ = TargetsView::List;
    TargetsLoadStatus status_ = TargetsLoadStatus::SessionUnavailable;
    bool comparisonAvailable_ = false;
    std::size_t sourceIdentityCount_ = 0;
    bool truncated_ = false;
};

}  // namespace leshy1::apps::targets
