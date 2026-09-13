#include <cassert>
#include <cstdio>
#include "ui/LiveTextRenderCache.h"
#include "ui/WifiNetworkNavigation.h"
#include "ui/VisibleNetworkName.h"
#include "ui/LayeredBarDelta.h"

using namespace leshy1::ui;

int main() {
    // Every changed pixel is painted exactly once with its final colour;
    // unchanged pixels (including the grid) are never touched.
    constexpr std::int16_t h = 7;
    for (std::int16_t oldH = 0; oldH <= h; ++oldH)
    for (std::int16_t oldA = 0; oldA <= h; ++oldA)
    for (std::int16_t nextH = 0; nextH <= h; ++nextH)
    for (std::int16_t nextA = 0; nextA <= h; ++nextA)
    for (std::uint16_t tone = 3; tone <= 4; ++tone) {
        const BarLayers old{oldH, oldA, 3}, next{nextH, nextA, tone};
        const auto bg = [](std::int16_t y) -> std::uint16_t { return y == 3 ? 1 : 0; };
        const auto pixel = [&](BarLayers bar, int x, int y) -> std::uint16_t {
            if (x >= 1 && x < 4 && y >= h - bar.current) return bar.color;
            if (y >= h - bar.average) return 2;
            return bg(static_cast<std::int16_t>(y));
        };
        unsigned hits[7][5] = {};
        paintLayeredBarDelta(old, next, 5, 3, h, 2, bg,
            [&](int x, int y, int w, int height, std::uint16_t color) {
                for (int yy = y; yy < y + height; ++yy)
                for (int xx = x; xx < x + w; ++xx) {
                    assert(++hits[yy][xx] == 1);
                    assert(color == pixel(next, xx, yy));
                    assert(color != pixel(old, xx, yy));
                }
            });
        for (int y = 0; y < h; ++y)
        for (int x = 0; x < 5; ++x)
            assert(hits[y][x] == (pixel(old, x, y) != pixel(next, x, y) ? 1U : 0U));
    }
    char name[96] = {};
    formatVisibleNetworkName("A\0B", 3, "hidden", name, sizeof(name));
    assert(std::strcmp(name, "A\\x00B") == 0);
    formatVisibleNetworkName(u8"Леший", 10, "hidden", name, sizeof(name));
    assert(std::strcmp(name, u8"Леший") == 0);
    formatVisibleNetworkName(u8"Леший", 10, "hidden", name, 6);
    assert(std::strcmp(name, u8"Ле~") == 0);
    formatVisibleNetworkName("\xC0\xAF", 2, "hidden", name, sizeof(name));
    assert(std::strcmp(name, "\\xC0\\xAF") == 0);
    formatVisibleNetworkName("", 0, "hidden", name, sizeof(name));
    assert(std::strcmp(name, "hidden") == 0);
    LiveTextRenderCache<2, 16> cache;
    assert(cache.changed(0, "-61 dBm", 1));
    cache.publish(0, "-61 dBm", 1);
    assert(!cache.changed(0, "-61 dBm", 1));
    assert(cache.changed(0, "-61 dBm", 2));
    assert(cache.changed(0, "-60 dBm", 1));
    assert(!cache.changed(2, "ignored", 1));
    assert(cache.changed(1, "", 1));
    cache.publish(1, "", 1);
    assert(!cache.changed(1, "", 1));
    cache.publish(1, "this cannot fit in sixteen bytes", 1);
    assert(cache.changed(1, "this cannot fit in sixteen bytes", 1));
    cache.reset();
    assert(cache.changed(0, "-61 dBm", 1));

    WifiNetworkNavigation nav;
    using Key = WifiNetworkKey;
    using Page = WifiNetworkPage;
    using Intent = WifiNetworkIntent;
    assert(nav.handle(Key::Ok) == Intent::Changed);
    assert(nav.page() == Page::Radar);
    assert(nav.handle(Key::Left) == Intent::Changed);
    assert(nav.page() == Page::Summary);
    assert(nav.handle(Key::Right) == Intent::Changed);
    assert(nav.page() == Page::Actions);
    nav.handle(Key::Ok);
    assert(nav.page() == Page::Protection);
    nav.handle(Key::Left);
    assert(nav.page() == Page::Actions);
    nav.handle(Key::Down);
    assert(nav.handle(Key::Right) == Intent::Password);  // preflight only
    assert(nav.page() == Page::Actions);
    nav.handle(Key::Down);
    nav.handle(Key::Ok);
    assert(nav.page() == Page::Information && nav.rowCount() == 4);
    for (unsigned row = 0; row < 4; ++row) {
        nav.handle(Key::Right);
        assert(nav.rowCount() == 0);
        assert(nav.handle(Key::Ok) == Intent::None);
        nav.handle(Key::Left);
        assert(nav.page() == Page::Information);
        // Protection must return to its own info row, not the first row.
        assert(nav.selection() == row);
        nav.handle(Key::Down);
    }
    nav.reset();
    assert(nav.handle(Key::Left) == Intent::Exit);
    std::puts("Wi-Fi navigation and retained text tests passed");
}
