#pragma once

#include <cstdint>

namespace leshy1::ui {

struct BarLayers final {
    std::int16_t current = 0;
    std::int16_t average = 0;
    std::uint16_t color = 0;
};

// Emit final-colour rectangles, never erase-then-paint. Three non-overlapping
// strips represent the wide mean and narrow live value. The supplied background
// restores grid lines too. No framebuffer, allocation, or float arithmetic.
template <typename Background, typename Paint>
void paintLayeredBarDelta(const BarLayers& old, const BarLayers& next,
                          std::int16_t width, std::int16_t currentWidth,
                          std::int16_t height, std::uint16_t averageColor,
                          Background background, Paint paint) {
    if (width <= 0 || currentWidth <= 0 || currentWidth > width || height <= 0)
        return;
    if (old.current == next.current && old.average == next.average &&
        old.color == next.color) return;
    const std::int16_t inset = (width - currentWidth) / 2;
    const std::int16_t edges[] = {0, inset,
        static_cast<std::int16_t>(inset + currentWidth), width};
    for (unsigned strip = 0; strip < 3; ++strip) {
        const std::int16_t span = edges[strip + 1U] - edges[strip];
        if (span == 0) continue;
        std::int16_t run = -1;
        std::uint16_t runColor = 0;
        for (std::int16_t y = 0; y <= height; ++y) {
            bool changed = false;
            std::uint16_t color = 0;
            if (y < height) {
                const auto pixel = [&](const BarLayers& bar) {
                    if (strip == 1U && y >= height - bar.current) return bar.color;
                    if (y >= height - bar.average) return averageColor;
                    return static_cast<std::uint16_t>(background(y));
                };
                color = pixel(next);
                changed = color != pixel(old);
            }
            if (run >= 0 && (!changed || color != runColor)) {
                paint(edges[strip], run, span,
                      static_cast<std::int16_t>(y - run), runColor);
                run = -1;
            }
            if (changed && run < 0) { run = y; runColor = color; }
        }
    }
}

}  // namespace leshy1::ui
