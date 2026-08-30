#include "SerialConsoleBuffer.h"

namespace leshy1::services::serial {

bool SerialConsoleBuffer::push(std::uint8_t value) {
    if (size_ >= bytes_.size()) {
        ++dropped_;
        return false;
    }
    bytes_[tail_] = value;
    tail_ = (tail_ + 1U) % bytes_.size();
    ++size_;
    if (size_ > highWater_) highWater_ = size_;
    return true;
}

bool SerialConsoleBuffer::pop(std::uint8_t* output) {
    if (output == nullptr || size_ == 0U) return false;
    *output = bytes_[head_];
    bytes_[head_] = 0U;
    head_ = (head_ + 1U) % bytes_.size();
    --size_;
    return true;
}

void SerialConsoleBuffer::scrub() {
    volatile std::uint8_t* cursor = bytes_.data();
    for (std::size_t index = 0U; index < bytes_.size(); ++index) {
        cursor[index] = 0U;
    }
    head_ = 0U;
    tail_ = 0U;
    size_ = 0U;
}

void SerialConsoleBuffer::reset() {
    scrub();
    highWater_ = 0U;
    dropped_ = 0U;
}

}  // namespace leshy1::services::serial
