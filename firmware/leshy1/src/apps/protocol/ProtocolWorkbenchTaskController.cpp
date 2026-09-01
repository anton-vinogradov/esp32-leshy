#include "ProtocolWorkbenchTaskController.h"

namespace leshy1::apps::protocol {

const char* protocolWorkbenchTaskViewName(
    ProtocolWorkbenchTaskView view) {
    switch (view) {
        case ProtocolWorkbenchTaskView::Tasks: return "tasks";
        case ProtocolWorkbenchTaskView::Waveform: return "waveform";
        case ProtocolWorkbenchTaskView::Explain: return "explain";
        case ProtocolWorkbenchTaskView::Annotate: return "annotate";
        case ProtocolWorkbenchTaskView::Comparison: return "comparison";
        case ProtocolWorkbenchTaskView::Decode: return "decode";
    }
    return "unknown";
}

void ProtocolWorkbenchTaskController::enter() {
    view_ = ProtocolWorkbenchTaskView::Tasks;
    selection_ = 0U;
    resultCount_ = 0U;
}

std::size_t ProtocolWorkbenchTaskController::navigationCount() const {
    if (view_ == ProtocolWorkbenchTaskView::Tasks) return kTaskCount;
    if (view_ == ProtocolWorkbenchTaskView::Explain) {
        return kExplainTaskCount;
    }
    if (view_ == ProtocolWorkbenchTaskView::Comparison ||
        view_ == ProtocolWorkbenchTaskView::Decode) {
        return resultCount_;
    }
    return 0U;
}

bool ProtocolWorkbenchTaskController::previous() {
    if (selection_ == 0U || navigationCount() == 0U) return false;
    --selection_;
    return true;
}

bool ProtocolWorkbenchTaskController::next() {
    const std::size_t count = navigationCount();
    if (count == 0U || selection_ + 1U >= count) return false;
    ++selection_;
    return true;
}

ProtocolWorkbenchTaskActivation
ProtocolWorkbenchTaskController::activate() {
    if (view_ == ProtocolWorkbenchTaskView::Tasks) {
        if (selection_ == 0U) {
            view_ = ProtocolWorkbenchTaskView::Waveform;
        } else if (selection_ == 1U) {
            view_ = ProtocolWorkbenchTaskView::Explain;
            selection_ = 0U;
        } else if (selection_ == 2U) {
            return ProtocolWorkbenchTaskActivation::CompareRequested;
        } else {
            return ProtocolWorkbenchTaskActivation::None;
        }
        return ProtocolWorkbenchTaskActivation::Changed;
    }
    if (view_ == ProtocolWorkbenchTaskView::Waveform) {
        view_ = ProtocolWorkbenchTaskView::Explain;
        selection_ = 0U;
        return ProtocolWorkbenchTaskActivation::Changed;
    }
    if (view_ == ProtocolWorkbenchTaskView::Explain) {
        if (selection_ == 0U) {
            view_ = ProtocolWorkbenchTaskView::Annotate;
            selection_ = 0U;
            return ProtocolWorkbenchTaskActivation::Changed;
        }
        if (selection_ == 1U) {
            return ProtocolWorkbenchTaskActivation::DecodeRequested;
        }
    }
    return ProtocolWorkbenchTaskActivation::None;
}

bool ProtocolWorkbenchTaskController::back() {
    if (view_ == ProtocolWorkbenchTaskView::Tasks) return false;
    if (view_ == ProtocolWorkbenchTaskView::Explain ||
        view_ == ProtocolWorkbenchTaskView::Waveform ||
        view_ == ProtocolWorkbenchTaskView::Comparison) {
        view_ = ProtocolWorkbenchTaskView::Tasks;
    } else if (view_ == ProtocolWorkbenchTaskView::Annotate ||
               view_ == ProtocolWorkbenchTaskView::Decode) {
        view_ = ProtocolWorkbenchTaskView::Explain;
    }
    selection_ = 0U;
    resultCount_ = 0U;
    return true;
}

void ProtocolWorkbenchTaskController::noteComparison(
    std::size_t regionCount) {
    view_ = ProtocolWorkbenchTaskView::Comparison;
    selection_ = 0U;
    resultCount_ = regionCount;
}

void ProtocolWorkbenchTaskController::noteDecode(std::size_t fieldCount) {
    view_ = ProtocolWorkbenchTaskView::Decode;
    selection_ = 0U;
    resultCount_ = fieldCount;
}

}  // namespace leshy1::apps::protocol
