#include <array>
#include <cstdint>
#include <iostream>

#include "ui/LiveListRenderCache.h"

namespace {

int failures = 0;

#define CHECK(expression)                                                    \
    do {                                                                     \
        if (!(expression)) {                                                 \
            std::cerr << __FILE__ << ':' << __LINE__                         \
                      << ": check failed: " #expression << '\n';            \
            ++failures;                                                      \
        }                                                                    \
    } while (false)

struct Row final {
    bool present = false;
    bool selected = false;
    std::uint8_t identity = 0;
    std::uint8_t channel = 0;
    std::int16_t rssi = 0;

    bool operator==(const Row& other) const {
        return present == other.present && selected == other.selected &&
            identity == other.identity && channel == other.channel &&
            rssi == other.rssi;
    }

    bool sameIdentity(const Row& other) const {
        return present && other.present && identity == other.identity;
    }

    bool staticFieldsEqual(const Row& other) const {
        return present == other.present && selected == other.selected &&
            identity == other.identity && channel == other.channel;
    }
};

void testRetainedRowClassification() {
    using leshy1::ui::LiveListRenderCache;
    using leshy1::ui::LiveListRowChange;
    LiveListRenderCache<Row, 4> cache;

    const Row first{true, false, 7, 6, -60};
    CHECK(cache.classify(0, first) == LiveListRowChange::Replace);
    cache.publish(0, first);
    CHECK(cache.classify(0, first) == LiveListRowChange::None);

    Row signal = first;
    signal.rssi = -62;
    CHECK(cache.classify(0, signal) == LiveListRowChange::DynamicFields);

    Row selected = signal;
    selected.selected = true;
    CHECK(cache.classify(0, selected) == LiveListRowChange::Replace);

    Row reordered = signal;
    reordered.identity = 9;
    CHECK(cache.classify(0, reordered) == LiveListRowChange::Replace);

    const Row absent{};
    CHECK(cache.classify(0, absent) == LiveListRowChange::Clear);
    CHECK(cache.classify(1, absent) == LiveListRowChange::None);
}

void testSceneStateIsExplicitAndResettable() {
    using leshy1::ui::LiveListRenderCache;
    using leshy1::ui::LiveListSceneState;
    LiveListRenderCache<Row, 4> cache;
    CHECK(cache.state() == LiveListSceneState::Unknown);
    cache.setState(LiveListSceneState::Rows);
    CHECK(cache.state() == LiveListSceneState::Rows);
    cache.reset();
    CHECK(cache.state() == LiveListSceneState::Unknown);
    CHECK(!cache.valid(0));
}

}  // namespace

int main() {
    testRetainedRowClassification();
    testSceneStateIsExplicitAndResettable();
    if (failures != 0) return 1;
    std::cout << "live-list retained rendering tests passed\n";
    return 0;
}
