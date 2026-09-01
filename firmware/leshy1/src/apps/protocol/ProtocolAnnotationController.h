#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolAnnotations.h"

namespace leshy1::apps::protocol {

enum class ProtocolAnnotationView : std::uint8_t {
    Waveform,
    Actions,
    ChooseStart,
    ChooseEnd,
    ChooseKind,
    Result,
};

enum class ProtocolAnnotationOutcome : std::uint8_t {
    None,
    Marked,
    Removed,
    Saved,
    Failed,
};

enum class ProtocolAnnotationActivation : std::uint8_t {
    None,
    Changed,
    SaveRequested,
};

// Allocation-free task-first editor for a derived annotation record. The
// controller owns only the small annotation set and cursor state; it never owns
// or changes raw Capture pulses.
class ProtocolAnnotationController final {
public:
    ProtocolAnnotationStatus enter(const ProtocolAnnotationSource& source);
    ProtocolAnnotationStatus restore(const ProtocolAnnotationSet& annotations,
                                     std::uint32_t storeGeneration);

    bool previous();
    bool next();
    ProtocolAnnotationActivation activate();
    bool back();

    void noteSaved(std::uint32_t storeGeneration);
    void noteSaveFailed();

    ProtocolAnnotationView view() const { return view_; }
    ProtocolAnnotationOutcome outcome() const { return outcome_; }
    const ProtocolAnnotationSource& source() const {
        return annotations_.source();
    }
    const ProtocolAnnotationSet& annotations() const { return annotations_; }
    ProtocolAnnotationSet& annotations() { return annotations_; }
    std::size_t pulseSelection() const { return pulseSelection_; }
    std::size_t actionSelection() const { return actionSelection_; }
    ProtocolAnnotationKind kindSelection() const { return kindSelection_; }
    std::uint16_t draftFirstPulse() const { return draftFirstPulse_; }
    std::uint16_t draftLastPulse() const { return draftLastPulse_; }
    std::uint32_t storeGeneration() const { return storeGeneration_; }
    bool dirty() const { return dirty_; }
    bool hasCurrentAnnotation() const;
    std::size_t actionCount() const;

private:
    enum class Action : std::uint8_t { Mark, Remove, Save };

    Action actionAt(std::size_t index) const;
    std::size_t currentAnnotationIndex() const;
    void clampActionSelection();

    ProtocolAnnotationSet annotations_{};
    ProtocolAnnotationView view_ = ProtocolAnnotationView::Waveform;
    ProtocolAnnotationOutcome outcome_ = ProtocolAnnotationOutcome::None;
    std::size_t pulseSelection_ = 0U;
    std::size_t actionSelection_ = 0U;
    ProtocolAnnotationKind kindSelection_ = ProtocolAnnotationKind::Header;
    std::uint16_t draftFirstPulse_ = 0U;
    std::uint16_t draftLastPulse_ = 0U;
    std::uint32_t storeGeneration_ = 0U;
    bool dirty_ = false;
};

}  // namespace leshy1::apps::protocol
