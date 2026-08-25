#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/targets/Correlation.h"
#include "domain/targets/TargetCatalog.h"
#include "domain/targets/TargetComparison.h"
#include "services/survey/SurveySession.h"
#include "services/targets/SessionCorrelationReview.h"
#include "services/targets/SessionTargetAdmission.h"

namespace leshy1::apps::targets {

enum class TargetsView : std::uint8_t {
    List,
    Detail,
    Actions,
    NameEdit,
    TagList,
    TagEdit,
    NotesEdit,
    CorrelationList,
    CorrelationReview,
    CorrelationEvidence,
    Compare,
    CompareDetail,
};

enum class TargetActionItem : std::uint8_t {
    Favorite,
    Name,
    Tags,
    Notes,
    Correlations,
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
    domain::targets::TargetCatalog& catalog;
    domain::targets::CorrelationDecisionLog& decisions;
    services::targets::SessionCorrelationProposalSet& correlations;
    domain::targets::TargetComparisonResult& comparison;

    TargetsWorkspace(
        domain::targets::TargetCatalog& catalogValue,
        domain::targets::CorrelationDecisionLog& decisionsValue,
        services::targets::SessionCorrelationProposalSet& correlationsValue,
        domain::targets::TargetComparisonResult& comparisonValue)
        : catalog(catalogValue), decisions(decisionsValue),
          correlations(correlationsValue), comparison(comparisonValue) {}
};

class TargetsController final {
public:
    static constexpr std::size_t kActionCount = 5;
    static constexpr std::size_t kCorrelationReviewControlCount = 4;
    static constexpr std::size_t kNameEditControlCount = 4;
    static constexpr std::size_t kTagEditControlCount = 4;
    static constexpr std::size_t kNotesEditControlCount = 4;

    explicit TargetsController(TargetsWorkspace& workspace)
        : workspace_(workspace) {}

    void reset();
    TargetsLoadStatus load(const TargetProductBinding& current);
    TargetsLoadStatus load(
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted);
    TargetsLoadStatus load(
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted,
        const domain::targets::CorrelationDecisionLog& decisions);
    TargetsLoadStatus load(const TargetProductBinding& baseline,
                           const TargetProductBinding& current);
    TargetsLoadStatus load(
        const TargetProductBinding& baseline,
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted);
    TargetsLoadStatus load(
        const TargetProductBinding& baseline,
        const TargetProductBinding& current,
        const domain::targets::TargetCatalog& persisted,
        const domain::targets::CorrelationDecisionLog& decisions);
    bool next();
    bool previous();
    bool openSelected();
    bool openNameEditor();
    bool openTagList();
    bool openTagEditor();
    bool openNotesEditor();
    bool openCorrelationList();
    bool openCompare();
    bool back();
    bool selectTarget(const domain::targets::TargetId& id);
    bool cycleNameEditorGlyph();
    bool appendNameEditorGlyph();
    bool eraseNameEditorGlyph();
    bool cycleTagEditorGlyph();
    bool appendTagEditorGlyph();
    bool eraseTagEditorGlyph();
    bool cycleNotesEditorGlyph();
    bool appendNotesEditorGlyph();
    bool eraseNotesEditorGlyph();

    TargetsView view() const { return view_; }
    TargetsLoadStatus status() const { return status_; }
    std::size_t size() const { return rowCount_; }
    std::size_t entryCount() const {
        return rowCount_ + (comparisonAvailable_ ? 1U : 0U);
    }
    std::size_t selection() const { return selection_; }
    std::size_t comparisonSelection() const { return comparisonSelection_; }
    std::size_t actionSelection() const { return actionSelection_; }
    std::size_t nameEditorSelection() const { return nameEditorSelection_; }
    std::size_t tagSelection() const { return tagSelection_; }
    std::size_t tagEditorSelection() const { return tagEditorSelection_; }
    std::size_t notesEditorSelection() const { return notesEditorSelection_; }
    std::size_t correlationSelection() const { return correlationSelection_; }
    std::size_t correlationReviewSelection() const {
        return correlationReviewSelection_;
    }
    TargetActionItem selectedAction() const;
    const char* nameEditorText() const { return nameEditorText_.data(); }
    std::size_t nameEditorLength() const { return nameEditorLength_; }
    char nameEditorGlyph() const;
    bool nameEditorDirty() const;
    bool nameEditorCanAppend() const {
        return nameEditorLength_ < domain::targets::TargetRecord::kNameCapacity;
    }
    std::size_t tagEntryCount() const;
    bool selectedTagIsAdd() const;
    const char* selectedTagText() const;
    std::size_t selectedTagLength() const;
    const char* tagEditorText() const { return tagEditorText_.data(); }
    std::size_t tagEditorLength() const { return tagEditorLength_; }
    char tagEditorGlyph() const;
    bool tagEditorCanAppend() const {
        return tagEditorLength_ < domain::targets::TargetRecord::kTagCapacity;
    }
    bool tagEditorCanSave() const {
        return view_ == TargetsView::TagEdit && tagEditorLength_ != 0;
    }
    const char* notesEditorText() const { return notesEditorText_.data(); }
    std::size_t notesEditorLength() const { return notesEditorLength_; }
    char notesEditorGlyph() const;
    bool notesEditorDirty() const;
    bool notesEditorCanAppend() const {
        return notesEditorLength_ < domain::targets::TargetRecord::kNotesCapacity;
    }
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
    std::size_t selectedCorrelationCount() const;
    const domain::targets::CorrelationProposal* selectedCorrelationProposal(
        std::size_t index) const;
    const domain::targets::CorrelationProposal* reviewedCorrelationProposal()
        const;
    bool correlationEvidence(bool candidate,
                             domain::observations::Observation* output) const;
    bool correlationEvidenceIsCandidate() const {
        return correlationEvidenceCandidate_;
    }
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
    const domain::targets::CorrelationDecisionLog& decisions() const {
        return workspace_.decisions;
    }
    const services::targets::SessionTargetAdmissionResult& lastAdmission()
        const { return lastAdmission_; }
    const char* lastAdmissionStage() const { return lastAdmissionStage_; }

private:
    void resetTransient(bool clearPersistentState);
    TargetsLoadStatus loadBindings(const TargetProductBinding& baseline,
                                   const TargetProductBinding& current,
                                   bool compare,
                                   const domain::targets::TargetCatalog*
                                       persisted = nullptr,
                                   const domain::targets::CorrelationDecisionLog*
                                       decisions = nullptr);
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
    std::size_t actionSelection_ = 0;
    std::size_t nameEditorSelection_ = 0;
    std::array<char, domain::targets::TargetRecord::kNameCapacity + 1>
        nameEditorText_{};
    std::size_t nameEditorLength_ = 0;
    std::array<char, domain::targets::TargetRecord::kNameCapacity + 1>
        originalName_{};
    std::size_t originalNameLength_ = 0;
    std::size_t nameEditorGlyphSelection_ = 0;
    std::size_t tagSelection_ = 0;
    std::size_t tagEditorSelection_ = 0;
    std::array<char, domain::targets::TargetRecord::kTagCapacity + 1>
        tagEditorText_{};
    std::size_t tagEditorLength_ = 0;
    std::size_t tagEditorGlyphSelection_ = 0;
    std::size_t notesEditorSelection_ = 0;
    std::array<char, domain::targets::TargetRecord::kNotesCapacity + 1>
        notesEditorText_{};
    std::size_t notesEditorLength_ = 0;
    std::array<char, domain::targets::TargetRecord::kNotesCapacity + 1>
        originalNotes_{};
    std::size_t originalNotesLength_ = 0;
    std::size_t notesEditorGlyphSelection_ = 0;
    std::size_t correlationSelection_ = 0;
    std::size_t correlationReviewSelection_ = 0;
    bool correlationEvidenceCandidate_ = false;
    TargetsView view_ = TargetsView::List;
    TargetsLoadStatus status_ = TargetsLoadStatus::SessionUnavailable;
    bool comparisonAvailable_ = false;
    std::size_t sourceIdentityCount_ = 0;
    bool truncated_ = false;
    services::targets::SessionTargetAdmissionResult lastAdmission_{};
    const char* lastAdmissionStage_ = "none";
};

}  // namespace leshy1::apps::targets
