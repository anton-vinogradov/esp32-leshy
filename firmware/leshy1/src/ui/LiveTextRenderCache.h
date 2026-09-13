#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace leshy1::ui {

// Cache the pixels' inputs, not the producer's revision. Publish only after a
// successful paint. A failed allocation must not make a missing row look valid.
template <std::size_t Rows, std::size_t Bytes = 96>
class LiveTextRenderCache final {
  public:
    void reset() { valid_.fill(false); }
    bool changed(std::size_t row, const char* text, std::uint16_t style) const {
        return row < Rows && (!valid_[row] || styles_[row] != style ||
            std::strcmp(texts_[row].data(), text) != 0);
    }
    void publish(std::size_t row, const char* text, std::uint16_t style) {
        if (row >= Rows || std::strlen(text) >= Bytes) return;
        std::strcpy(texts_[row].data(), text);
        styles_[row] = style;
        valid_[row] = true;
    }
  private:
    std::array<std::array<char, Bytes>, Rows> texts_{};
    std::array<std::uint16_t, Rows> styles_{};
    std::array<bool, Rows> valid_{};
};

}  // namespace leshy1::ui
