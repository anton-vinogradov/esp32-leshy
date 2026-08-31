#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>

#include "apps/protocol/ProtocolWorkbench.h"

namespace {

class FixtureSource final
    : public leshy1::domain::captures::InfraredRawSource {
public:
    std::array<std::uint16_t, 68U> pulses{};
    std::size_t count = 0U;
    std::size_t failedIndex = pulses.size();

    std::size_t pulseCount() const override { return count; }

    bool pulseView(
        std::size_t index,
        leshy1::domain::captures::InfraredRawPulseView* output) const override {
        if (output == nullptr || index >= count || index == failedIndex) {
            return false;
        }
        output->durationUs = pulses[index];
        return true;
    }
};

FixtureSource necFixture() {
    FixtureSource source;
    source.pulses[source.count++] = 9000U;
    source.pulses[source.count++] = 4500U;
    for (std::size_t bit = 0U; bit < 32U; ++bit) {
        source.pulses[source.count++] = static_cast<std::uint16_t>(
            540U + (bit % 5U) * 10U);
        source.pulses[source.count++] = static_cast<std::uint16_t>(
            bit % 3U == 0U ? 1680U + (bit % 4U) * 10U
                            : 550U + (bit % 3U) * 10U);
    }
    source.pulses[source.count++] = 560U;
    return source;
}

}  // namespace

int main() {
    using namespace leshy1::apps::protocol;

    FixtureSource source = necFixture();
    ProtocolWorkbenchWorkspace workspace;
    ProtocolWorkbenchAnalysis analysis;
    assert(analyzeInfraredCapture(source, workspace, &analysis) ==
           ProtocolWorkbenchStatus::Valid);
    assert(analysis.valid());
    assert(analysis.pulseCount == source.count);
    assert(analysis.bandCount == 4U);
    assert(analysis.baseUnitUs >= 540U && analysis.baseUnitUs <= 580U);
    assert(analysis.bands[0].samples > analysis.bands[1].samples);
    assert(analysis.bands[1].centerUs >= 1650U &&
           analysis.bands[1].centerUs <= 1750U);
    assert(analysis.bands[2].centerUs == 4500U);
    assert(analysis.bands[3].centerUs == 9000U);
    assert(protocolTimingBandFor(analysis, 1690U) == 1U);
    assert(protocolNormalizedUnits(analysis, 1690U) == 3U);

    const std::uint64_t fingerprint = analysis.sourceFingerprint;
    ProtocolWorkbenchAnalysis repeated;
    assert(analyzeInfraredCapture(source, workspace, &repeated) ==
           ProtocolWorkbenchStatus::Valid);
    assert(repeated.sourceFingerprint == fingerprint);
    source.pulses[10] = static_cast<std::uint16_t>(source.pulses[10] + 1U);
    assert(analyzeInfraredCapture(source, workspace, &repeated) ==
           ProtocolWorkbenchStatus::Valid);
    assert(repeated.sourceFingerprint != fingerprint);

    FixtureSource shortSource;
    shortSource.pulses[0] = 560U;
    shortSource.count = 1U;
    assert(analyzeInfraredCapture(shortSource, workspace, &repeated) ==
           ProtocolWorkbenchStatus::TooFewPulses);

    source = necFixture();
    source.failedIndex = 5U;
    assert(analyzeInfraredCapture(source, workspace, &repeated) ==
           ProtocolWorkbenchStatus::SourceReadFailed);

    std::cout << "protocol workbench tests passed\n";
    return 0;
}
