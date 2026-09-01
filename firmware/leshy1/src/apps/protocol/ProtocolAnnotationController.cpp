#include "ProtocolAnnotationController.h"

namespace leshy1::apps::protocol {
namespace {

constexpr std::uint8_t kKindCount =
    static_cast<std::uint8_t>(ProtocolAnnotationKind::Gap) + 1U;

}  // namespace

ProtocolAnnotationStatus ProtocolAnnotationController::enter(
    const ProtocolAnnotationSource& source) {
    view_ = ProtocolAnnotationView::Waveform;
    outcome_ = ProtocolAnnotationOutcome::None;
    pulseSelection_ = 0U;
    actionSelection_ = 0U;
    kindSelection_ = ProtocolAnnotationKind::Header;
    draftFirstPulse_ = 0U;
    draftLastPulse_ = 0U;
    storeGeneration_ = 0U;
    dirty_ = false;
    return annotations_.bind(source);
}

ProtocolAnnotationStatus ProtocolAnnotationController::restore(
    const ProtocolAnnotationSet& annotations, std::uint32_t storeGeneration) {
    if (!annotations.bound() || storeGeneration == 0U ||
        !annotations_.bound() ||
        !sameProtocolAnnotationSource(annotations_.source(),
                                      annotations.source())) {
        return ProtocolAnnotationStatus::SourceMismatch;
    }
    annotations_ = annotations;
    storeGeneration_ = storeGeneration;
    dirty_ = false;
    outcome_ = ProtocolAnnotationOutcome::None;
    return ProtocolAnnotationStatus::Valid;
}

std::size_t ProtocolAnnotationController::currentAnnotationIndex() const {
    for (std::size_t index = 0U; index < annotations_.size(); ++index) {
        const ProtocolAnnotation* annotation = annotations_.get(index);
        if (annotation != nullptr &&
            annotation->firstPulse <= pulseSelection_ &&
            pulseSelection_ <= annotation->lastPulse) {
            return index;
        }
    }
    return annotations_.size();
}

bool ProtocolAnnotationController::hasCurrentAnnotation() const {
    return currentAnnotationIndex() < annotations_.size();
}

std::size_t ProtocolAnnotationController::actionCount() const {
    return 1U + (hasCurrentAnnotation() ? 1U : 0U) + (dirty_ ? 1U : 0U);
}

ProtocolAnnotationController::Action ProtocolAnnotationController::actionAt(
    std::size_t index) const {
    if (index == 0U) return Action::Mark;
    if (hasCurrentAnnotation()) {
        if (index == 1U) return Action::Remove;
        return Action::Save;
    }
    return Action::Save;
}

void ProtocolAnnotationController::clampActionSelection() {
    const std::size_t count = actionCount();
    if (count == 0U) {
        actionSelection_ = 0U;
    } else if (actionSelection_ >= count) {
        actionSelection_ = count - 1U;
    }
}

bool ProtocolAnnotationController::previous() {
    outcome_ = ProtocolAnnotationOutcome::None;
    if (view_ == ProtocolAnnotationView::Waveform ||
        view_ == ProtocolAnnotationView::ChooseStart ||
        view_ == ProtocolAnnotationView::ChooseEnd) {
        if (pulseSelection_ == 0U) return false;
        --pulseSelection_;
        return true;
    }
    if (view_ == ProtocolAnnotationView::Actions) {
        if (actionSelection_ == 0U) return false;
        --actionSelection_;
        return true;
    }
    if (view_ == ProtocolAnnotationView::ChooseKind) {
        const std::uint8_t selected =
            static_cast<std::uint8_t>(kindSelection_);
        if (selected == 0U) return false;
        kindSelection_ = static_cast<ProtocolAnnotationKind>(selected - 1U);
        return true;
    }
    return false;
}

bool ProtocolAnnotationController::next() {
    outcome_ = ProtocolAnnotationOutcome::None;
    if (view_ == ProtocolAnnotationView::Waveform ||
        view_ == ProtocolAnnotationView::ChooseStart ||
        view_ == ProtocolAnnotationView::ChooseEnd) {
        if (!annotations_.bound() ||
            pulseSelection_ + 1U >= annotations_.source().pulseCount) {
            return false;
        }
        ++pulseSelection_;
        return true;
    }
    if (view_ == ProtocolAnnotationView::Actions) {
        if (actionSelection_ + 1U >= actionCount()) return false;
        ++actionSelection_;
        return true;
    }
    if (view_ == ProtocolAnnotationView::ChooseKind) {
        const std::uint8_t selected =
            static_cast<std::uint8_t>(kindSelection_);
        if (selected + 1U >= kKindCount) return false;
        kindSelection_ = static_cast<ProtocolAnnotationKind>(selected + 1U);
        return true;
    }
    return false;
}

ProtocolAnnotationActivation ProtocolAnnotationController::activate() {
    outcome_ = ProtocolAnnotationOutcome::None;
    if (view_ == ProtocolAnnotationView::Waveform) {
        actionSelection_ = 0U;
        view_ = ProtocolAnnotationView::Actions;
        return ProtocolAnnotationActivation::Changed;
    }
    if (view_ == ProtocolAnnotationView::Actions) {
        clampActionSelection();
        const Action action = actionAt(actionSelection_);
        if (action == Action::Mark) {
            draftFirstPulse_ = static_cast<std::uint16_t>(pulseSelection_);
            draftLastPulse_ = draftFirstPulse_;
            kindSelection_ = ProtocolAnnotationKind::Header;
            view_ = ProtocolAnnotationView::ChooseStart;
            return ProtocolAnnotationActivation::Changed;
        }
        if (action == Action::Remove) {
            const std::size_t index = currentAnnotationIndex();
            const ProtocolAnnotationStatus removed = annotations_.remove(
                annotations_.source(), index);
            if (removed != ProtocolAnnotationStatus::Valid) {
                outcome_ = ProtocolAnnotationOutcome::Failed;
                view_ = ProtocolAnnotationView::Result;
                return ProtocolAnnotationActivation::Changed;
            }
            dirty_ = true;
            outcome_ = ProtocolAnnotationOutcome::Removed;
            view_ = ProtocolAnnotationView::Result;
            return ProtocolAnnotationActivation::Changed;
        }
        if (action == Action::Save && dirty_) {
            return ProtocolAnnotationActivation::SaveRequested;
        }
        return ProtocolAnnotationActivation::None;
    }
    if (view_ == ProtocolAnnotationView::ChooseStart) {
        draftFirstPulse_ = static_cast<std::uint16_t>(pulseSelection_);
        draftLastPulse_ = draftFirstPulse_;
        view_ = ProtocolAnnotationView::ChooseEnd;
        return ProtocolAnnotationActivation::Changed;
    }
    if (view_ == ProtocolAnnotationView::ChooseEnd) {
        draftLastPulse_ = static_cast<std::uint16_t>(pulseSelection_);
        if (draftLastPulse_ < draftFirstPulse_) {
            const std::uint16_t first = draftFirstPulse_;
            draftFirstPulse_ = draftLastPulse_;
            draftLastPulse_ = first;
        }
        view_ = ProtocolAnnotationView::ChooseKind;
        return ProtocolAnnotationActivation::Changed;
    }
    if (view_ == ProtocolAnnotationView::ChooseKind) {
        const ProtocolAnnotation annotation{
            kindSelection_, draftFirstPulse_, draftLastPulse_};
        const ProtocolAnnotationStatus added = annotations_.add(
            annotations_.source(), annotation);
        outcome_ = added == ProtocolAnnotationStatus::Valid
            ? ProtocolAnnotationOutcome::Marked
            : ProtocolAnnotationOutcome::Failed;
        if (added == ProtocolAnnotationStatus::Valid) dirty_ = true;
        view_ = ProtocolAnnotationView::Result;
        return ProtocolAnnotationActivation::Changed;
    }
    if (view_ == ProtocolAnnotationView::Result) {
        view_ = ProtocolAnnotationView::Waveform;
        outcome_ = ProtocolAnnotationOutcome::None;
        return ProtocolAnnotationActivation::Changed;
    }
    return ProtocolAnnotationActivation::None;
}

bool ProtocolAnnotationController::back() {
    outcome_ = ProtocolAnnotationOutcome::None;
    if (view_ == ProtocolAnnotationView::Waveform) return false;
    if (view_ == ProtocolAnnotationView::Actions) {
        view_ = ProtocolAnnotationView::Waveform;
    } else if (view_ == ProtocolAnnotationView::ChooseStart) {
        view_ = ProtocolAnnotationView::Actions;
        clampActionSelection();
    } else if (view_ == ProtocolAnnotationView::ChooseEnd) {
        view_ = ProtocolAnnotationView::ChooseStart;
    } else if (view_ == ProtocolAnnotationView::ChooseKind) {
        view_ = ProtocolAnnotationView::ChooseEnd;
    } else {
        view_ = ProtocolAnnotationView::Waveform;
    }
    return true;
}

void ProtocolAnnotationController::noteSaved(std::uint32_t storeGeneration) {
    if (storeGeneration == 0U) {
        noteSaveFailed();
        return;
    }
    storeGeneration_ = storeGeneration;
    dirty_ = false;
    outcome_ = ProtocolAnnotationOutcome::Saved;
    view_ = ProtocolAnnotationView::Result;
}

void ProtocolAnnotationController::noteSaveFailed() {
    outcome_ = ProtocolAnnotationOutcome::Failed;
    view_ = ProtocolAnnotationView::Result;
}

}  // namespace leshy1::apps::protocol
