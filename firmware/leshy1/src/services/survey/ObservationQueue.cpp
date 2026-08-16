#include "ObservationQueue.h"

namespace leshy1::services::survey {

bool ObservationQueue::push(
    const domain::observations::Observation& observation) {
    if (full()) {
        ++dropped_;
        return false;
    }
    entries_[tail_] = observation;
    tail_ = (tail_ + 1U) % entries_.size();
    ++size_;
    ++pushed_;
    if (size_ > highWater_) highWater_ = size_;
    return true;
}

bool ObservationQueue::pop(domain::observations::Observation* output) {
    if (output == nullptr || empty()) return false;
    *output = entries_[head_];
    entries_[head_] = domain::observations::Observation{};
    head_ = (head_ + 1U) % entries_.size();
    --size_;
    ++popped_;
    return true;
}

void ObservationQueue::reset() {
    entries_.fill(domain::observations::Observation{});
    head_ = 0;
    tail_ = 0;
    size_ = 0;
    highWater_ = 0;
    pushed_ = 0;
    popped_ = 0;
    dropped_ = 0;
}

}  // namespace leshy1::services::survey
