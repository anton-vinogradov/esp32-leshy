#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "apps/protocol/ProtocolAnnotations.h"
#include "apps/protocol/ProtocolAnnotationController.h"
#include "apps/protocol/ProtocolComparison.h"
#include "apps/protocol/ProtocolDerivedDecode.h"
#include "apps/protocol/ProtocolWorkbench.h"
#include "storage/ProtocolAnnotationCodec.h"
#include "storage/ProtocolAnnotationStore.h"
#include "storage/ProtocolDerivedDecodeCodec.h"
#include "storage/ProtocolDerivedDecodeStore.h"

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

class MemoryStoreIo final : public leshy1::storage::SessionStoreIo {
public:
    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override {
        if (path == nullptr || data == nullptr || size == 0U) return false;
        files_[path] = std::vector<std::uint8_t>(data, data + size);
        pending_ = path;
        return true;
    }

    ReadStatus readFile(const char* path, std::uint8_t* output,
                        std::size_t capacity,
                        std::size_t* outputSize) override {
        if (path == nullptr || output == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        const auto found = files_.find(path);
        if (found == files_.end()) return ReadStatus::NotFound;
        if (found->second.size() > capacity) return ReadStatus::TooLarge;
        std::memcpy(output, found->second.data(), found->second.size());
        *outputSize = found->second.size();
        return ReadStatus::Ok;
    }

    bool syncFile(const char* path) override {
        if (path == nullptr || pending_ != path) return false;
        if (!failSyncPath_.empty() && failSyncPath_ == path) {
            failSyncPath_.clear();
            return false;
        }
        pending_.clear();
        return true;
    }

    bool syncDirectory() override { return true; }

    void failNextSync(const char* path) { failSyncPath_ = path; }

    void flip(const char* path, std::size_t offset) {
        auto& bytes = files_.at(path);
        assert(offset < bytes.size());
        bytes[offset] ^= 0x5aU;
    }

private:
    std::map<std::string, std::vector<std::uint8_t>> files_{};
    std::string pending_{};
    std::string failSyncPath_{};
};

void testProtocolAnnotationsModelAndCodec() {
    using namespace leshy1::apps::protocol;
    using namespace leshy1::storage;

    const ProtocolAnnotationSource source{8U, 0x8FF146182DB0BEA0ULL, 67U};
    ProtocolAnnotationSet annotations;
    assert(annotations.bind(source) == ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Command, 35U,
                                    66U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Header, 0U, 1U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Address, 2U, 17U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.size() == 3U);
    assert(annotations.get(0U)->kind == ProtocolAnnotationKind::Header);
    assert(annotations.findAtPulse(10U)->kind ==
           ProtocolAnnotationKind::Address);
    assert(annotations.findAtPulse(30U) == nullptr);
    assert(annotations.add(source, {ProtocolAnnotationKind::Data, 16U, 20U}) ==
           ProtocolAnnotationStatus::Overlap);
    assert(annotations.add({9U, source.captureFingerprint, source.pulseCount},
                           {ProtocolAnnotationKind::Gap, 18U, 18U}) ==
           ProtocolAnnotationStatus::SourceMismatch);
    assert(annotations.add(source, {ProtocolAnnotationKind::Gap, 67U, 67U}) ==
           ProtocolAnnotationStatus::RangeInvalid);

    std::array<std::uint8_t, kProtocolAnnotationWireMaxBytes> wire{};
    std::size_t wireSize = 0U;
    assert(encodeProtocolAnnotations(annotations, wire.data(), wire.size(),
                                     &wireSize) ==
           ProtocolAnnotationCodecStatus::Valid);
    ProtocolAnnotationSet decoded;
    assert(decodeProtocolAnnotations(wire.data(), wireSize, &decoded) ==
           ProtocolAnnotationCodecStatus::Valid);
    assert(sameProtocolAnnotationSource(decoded.source(), source));
    assert(decoded.size() == annotations.size());
    assert(decoded.get(2U)->firstPulse == 35U);
    wire[25U] ^= 1U;
    assert(decodeProtocolAnnotations(wire.data(), wireSize, &decoded) ==
           ProtocolAnnotationCodecStatus::ChecksumMismatch);
    assert(!decoded.bound());
}

void testProtocolAnnotationAtomicStore() {
    using namespace leshy1::apps::protocol;
    using namespace leshy1::storage;

    const ProtocolAnnotationSource source{8U, 0x8FF146182DB0BEA0ULL, 67U};
    ProtocolAnnotationSet annotations;
    assert(annotations.bind(source) == ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Header, 0U, 1U}) ==
           ProtocolAnnotationStatus::Valid);

    MemoryStoreIo io;
    ProtocolAnnotationStoreWorkspace workspace;
    ProtocolAnnotationSet scratch;
    auto committed = commitNextProtocolAnnotations(
        io, workspace, annotations, scratch);
    assert(committed.complete());
    assert(committed.storeGeneration == 1U);
    assert(committed.publishedSlot == HeadSlot::A);

    ProtocolAnnotationSet recovered;
    auto recovery = recoverProtocolAnnotations(
        io, workspace, source, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 1U);
    assert(recovery.annotations == 1U);

    assert(annotations.add(source, {ProtocolAnnotationKind::Address, 2U, 17U}) ==
           ProtocolAnnotationStatus::Valid);
    committed = commitNextProtocolAnnotations(
        io, workspace, annotations, scratch);
    assert(committed.complete());
    assert(committed.storeGeneration == 2U);
    assert(committed.publishedSlot == HeadSlot::B);
    recovery = recoverProtocolAnnotations(io, workspace, source, &recovered);
    assert(recovery.valid());
    assert(recovered.size() == 2U);

    // A torn third generation cannot displace the fully synced second head.
    assert(annotations.add(source, {ProtocolAnnotationKind::Command, 18U, 33U}) ==
           ProtocolAnnotationStatus::Valid);
    io.failNextSync("protocol-annotations-00000008-00000003.manifest");
    committed = commitNextProtocolAnnotations(
        io, workspace, annotations, scratch);
    assert(!committed.complete());
    assert(committed.stage == CommitStage::SyncManifest);
    recovery = recoverProtocolAnnotations(io, workspace, source, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 2U);
    assert(recovered.size() == 2U);

    // Corrupting the newest payload falls back to generation one.
    io.flip("protocol-annotations-00000008-00000002.bin", 30U);
    recovery = recoverProtocolAnnotations(io, workspace, source, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 1U);
    assert(recovered.size() == 1U);

    // A different source fingerprint can never borrow these annotations.
    const ProtocolAnnotationSource other{
        source.captureGeneration, source.captureFingerprint + 1U,
        source.pulseCount};
    recovery = recoverProtocolAnnotations(io, workspace, other, &recovered);
    assert(!recovery.valid());
    assert(!recovered.bound());
}

void testProtocolAnnotationTaskFlow() {
    using namespace leshy1::apps::protocol;

    const ProtocolAnnotationSource source{8U, 0x8FF146182DB0BEA0ULL, 67U};
    ProtocolAnnotationController controller;
    assert(controller.enter(source) == ProtocolAnnotationStatus::Valid);
    assert(controller.view() == ProtocolAnnotationView::Waveform);
    assert(!controller.dirty());

    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::Actions);
    assert(controller.actionCount() == 1U);
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::ChooseStart);
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::ChooseEnd);
    assert(controller.next());
    assert(controller.next());
    assert(controller.next());
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::ChooseKind);
    assert(controller.next());
    assert(controller.kindSelection() == ProtocolAnnotationKind::Address);
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::Result);
    assert(controller.outcome() == ProtocolAnnotationOutcome::Marked);
    assert(controller.annotations().size() == 1U);
    assert(controller.annotations().get(0U)->firstPulse == 0U);
    assert(controller.annotations().get(0U)->lastPulse == 3U);
    assert(controller.dirty());

    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.view() == ProtocolAnnotationView::Waveform);
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.actionCount() == 3U);
    assert(controller.next());
    assert(controller.next());
    assert(controller.activate() ==
           ProtocolAnnotationActivation::SaveRequested);
    controller.noteSaved(4U);
    assert(controller.outcome() == ProtocolAnnotationOutcome::Saved);
    assert(controller.storeGeneration() == 4U);
    assert(!controller.dirty());

    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.actionCount() == 2U);
    assert(controller.next());
    assert(controller.activate() == ProtocolAnnotationActivation::Changed);
    assert(controller.outcome() == ProtocolAnnotationOutcome::Removed);
    assert(controller.annotations().size() == 0U);
    assert(controller.dirty());

    ProtocolAnnotationSet foreign;
    assert(foreign.bind({9U, source.captureFingerprint, source.pulseCount}) ==
           ProtocolAnnotationStatus::Valid);
    assert(controller.restore(foreign, 1U) ==
           ProtocolAnnotationStatus::SourceMismatch);
}

void testProtocolComparison() {
    using namespace leshy1::apps::protocol;

    FixtureSource left = necFixture();
    FixtureSource right = left;
    ProtocolWorkbenchWorkspace leftWorkspace;
    ProtocolWorkbenchWorkspace rightWorkspace;
    ProtocolWorkbenchAnalysis leftAnalysis;
    ProtocolWorkbenchAnalysis rightAnalysis;
    assert(analyzeInfraredCapture(left, leftWorkspace, &leftAnalysis) ==
           ProtocolWorkbenchStatus::Valid);
    assert(analyzeInfraredCapture(right, rightWorkspace, &rightAnalysis) ==
           ProtocolWorkbenchStatus::Valid);
    const ProtocolAnnotationSource leftIdentity{
        8U, leftAnalysis.sourceFingerprint,
        static_cast<std::uint16_t>(leftAnalysis.pulseCount)};
    ProtocolAnnotationSource rightIdentity{
        9U, rightAnalysis.sourceFingerprint,
        static_cast<std::uint16_t>(rightAnalysis.pulseCount)};
    ProtocolComparisonResult result;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, false, &result) ==
           ProtocolComparisonStatus::Valid);
    assert(result.outcome == ProtocolComparisonOutcome::Identical);
    assert(result.exactChangedPulses == 0U);
    assert(result.valueChangedPulses == 0U);
    assert(result.regionCount == 0U);
    assert(result.left.captureGeneration == 8U);
    assert(result.right.captureGeneration == 9U);

    // Receiver jitter changes exact evidence but not the decoded symbol family.
    right.pulses[2U] = static_cast<std::uint16_t>(right.pulses[2U] + 10U);
    assert(analyzeInfraredCapture(right, rightWorkspace, &rightAnalysis) ==
           ProtocolWorkbenchStatus::Valid);
    rightIdentity.captureFingerprint = rightAnalysis.sourceFingerprint;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, false, &result) ==
           ProtocolComparisonStatus::Valid);
    assert(result.outcome == ProtocolComparisonOutcome::TimingVariation);
    assert(result.exactChangedPulses == 1U);
    assert(result.valueChangedPulses == 0U);

    // A short/long symbol-family transition is useful payload change, with an
    // exact bounded pulse region rather than a copy of either raw Capture.
    right = left;
    right.pulses[5U] = 1680U;
    assert(analyzeInfraredCapture(right, rightWorkspace, &rightAnalysis) ==
           ProtocolWorkbenchStatus::Valid);
    rightIdentity.captureFingerprint = rightAnalysis.sourceFingerprint;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, false, &result) ==
           ProtocolComparisonStatus::Valid);
    assert(result.outcome == ProtocolComparisonOutcome::ValueChanged);
    assert(result.valueChangedPulses == 1U);
    assert(result.regionCount == 1U);
    assert(result.regions[0U].firstPulse == 5U);
    assert(result.regions[0U].lastPulse == 5U);

    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, true, &result) ==
           ProtocolComparisonStatus::Valid);
    assert(result.outcome == ProtocolComparisonOutcome::StructureChanged);

    // The summary counts omitted regions, not every pulse after capacity.
    right = left;
    for (std::size_t index = 2U; index <= 34U; index += 2U) {
        right.pulses[index] = 1680U;
    }
    assert(analyzeInfraredCapture(right, rightWorkspace, &rightAnalysis) ==
           ProtocolWorkbenchStatus::Valid);
    rightIdentity.captureFingerprint = rightAnalysis.sourceFingerprint;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, false, &result) ==
           ProtocolComparisonStatus::Valid);
    assert(result.regionCount == ProtocolComparisonResult::kMaximumRegions);
    assert(result.omittedRegions == 1U);

    ProtocolAnnotationSource foreign = rightIdentity;
    ++foreign.captureFingerprint;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, foreign, false, &result) ==
           ProtocolComparisonStatus::SourceMismatch);
    right.failedIndex = 4U;
    assert(compareInfraredCaptures(
               left, leftAnalysis, leftIdentity, false,
               right, rightAnalysis, rightIdentity, false, &result) ==
           ProtocolComparisonStatus::SourceReadFailed);
}

void testProtocolDerivedDecode() {
    using namespace leshy1::apps::protocol;

    FixtureSource source = necFixture();
    ProtocolWorkbenchWorkspace workspace;
    ProtocolWorkbenchAnalysis analysis;
    assert(analyzeInfraredCapture(source, workspace, &analysis) ==
           ProtocolWorkbenchStatus::Valid);
    const ProtocolAnnotationSource identity{
        8U, analysis.sourceFingerprint,
        static_cast<std::uint16_t>(analysis.pulseCount)};
    ProtocolAnnotationSet annotations;
    assert(annotations.bind(identity) == ProtocolAnnotationStatus::Valid);
    assert(annotations.add(identity, {ProtocolAnnotationKind::Header, 0U, 1U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.add(identity, {ProtocolAnnotationKind::Address, 2U, 17U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.add(identity, {ProtocolAnnotationKind::Command, 18U, 33U}) ==
           ProtocolAnnotationStatus::Valid);
    ProtocolDerivedDecode decode;
    ProtocolAnnotationSet empty;
    assert(empty.bind(identity) == ProtocolAnnotationStatus::Valid);
    assert(deriveProtocolDecode(source, analysis, false, empty, 1U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::InvalidArgument);
    assert(deriveProtocolDecode(source, analysis, false, annotations, 2U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::Valid);
    assert(decode.outcome == ProtocolDerivedDecodeOutcome::Complete);
    assert(decode.fieldCount == 3U);
    assert(decode.observedBitFields == 2U);
    assert(decode.inconclusiveFields == 0U);
    assert(decode.fields[0U].status ==
           ProtocolDerivedFieldStatus::DurationOnly);
    assert(decode.fields[1U].status ==
           ProtocolDerivedFieldStatus::BitsObserved);
    assert(decode.fields[1U].bitCount == 8U);
    assert(decode.fields[1U].observedBits == 0x49U);
    assert(decode.fields[2U].observedBits == 0x92U);
    assert(decode.source.captureFingerprint == analysis.sourceFingerprint);
    assert(decode.annotationStoreGeneration == 2U);
    assert(decode.decoderVersion == 1U);

    ProtocolAnnotationSet partial;
    assert(partial.bind(identity) == ProtocolAnnotationStatus::Valid);
    assert(partial.add(identity, {ProtocolAnnotationKind::Data, 34U, 34U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(deriveProtocolDecode(source, analysis, false, partial, 3U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::Valid);
    assert(decode.outcome == ProtocolDerivedDecodeOutcome::Partial);
    assert(decode.fields[0U].status ==
           ProtocolDerivedFieldStatus::Inconclusive);
    assert(decode.inconclusiveFields == 1U);

    ProtocolAnnotationSet foreign;
    assert(foreign.bind({9U, analysis.sourceFingerprint + 1U,
                         identity.pulseCount}) ==
           ProtocolAnnotationStatus::Valid);
    assert(foreign.add(foreign.source(),
                       {ProtocolAnnotationKind::Header, 0U, 1U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(deriveProtocolDecode(source, analysis, false, foreign, 1U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::SourceMismatch);
    source.failedIndex = 5U;
    assert(deriveProtocolDecode(source, analysis, false, annotations, 2U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::SourceReadFailed);
}

void testProtocolDerivedDecodeAtomicStore() {
    using namespace leshy1::apps::protocol;
    using namespace leshy1::storage;

    FixtureSource pulseSource = necFixture();
    ProtocolWorkbenchWorkspace analysisWorkspace;
    ProtocolWorkbenchAnalysis analysis;
    assert(analyzeInfraredCapture(pulseSource, analysisWorkspace, &analysis) ==
           ProtocolWorkbenchStatus::Valid);
    const ProtocolAnnotationSource source{
        8U, analysis.sourceFingerprint,
        static_cast<std::uint16_t>(analysis.pulseCount)};
    ProtocolAnnotationSet annotations;
    assert(annotations.bind(source) == ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Header, 0U, 1U}) ==
           ProtocolAnnotationStatus::Valid);
    assert(annotations.add(source, {ProtocolAnnotationKind::Address, 2U, 17U}) ==
           ProtocolAnnotationStatus::Valid);
    ProtocolDerivedDecode decode;
    assert(deriveProtocolDecode(pulseSource, analysis, false, annotations, 2U,
                                &decode) ==
           ProtocolDerivedDecodeStatus::Valid);

    std::array<std::uint8_t, kProtocolDerivedDecodeWireMaxBytes> wire{};
    std::size_t wireSize = 0U;
    assert(encodeProtocolDerivedDecode(decode, wire.data(), wire.size(),
                                       &wireSize) ==
           ProtocolDerivedDecodeCodecStatus::Valid);
    ProtocolDerivedDecode decoded;
    assert(decodeProtocolDerivedDecode(wire.data(), wireSize, &decoded) ==
           ProtocolDerivedDecodeCodecStatus::Valid);
    assert(decoded.source.captureFingerprint == source.captureFingerprint);
    assert(decoded.annotationStoreGeneration == 2U);
    assert(decoded.fieldCount == 2U);
    assert(decoded.fields[1U].observedBits == 0x49U);
    wire[40U] ^= 1U;
    assert(decodeProtocolDerivedDecode(wire.data(), wireSize, &decoded) ==
           ProtocolDerivedDecodeCodecStatus::ChecksumMismatch);
    assert(!decoded.valid());

    MemoryStoreIo io;
    ProtocolDerivedDecodeStoreWorkspace workspace;
    ProtocolDerivedDecode scratch;
    auto committed = commitNextProtocolDerivedDecode(
        io, workspace, decode, scratch);
    assert(committed.complete());
    assert(committed.storeGeneration == 1U);
    assert(committed.publishedSlot == HeadSlot::A);

    ProtocolDerivedDecode recovered;
    auto recovery = recoverProtocolDerivedDecode(
        io, workspace, source, 2U, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 1U);
    assert(recovery.fields == 2U);

    ++decode.fields[0U].durationUs;
    committed = commitNextProtocolDerivedDecode(
        io, workspace, decode, scratch);
    assert(committed.complete());
    assert(committed.storeGeneration == 2U);
    assert(committed.publishedSlot == HeadSlot::B);

    // A torn third derived generation cannot displace the durable second one.
    ++decode.fields[0U].durationUs;
    io.failNextSync("protocol-derived-00000008-00000002-00000003.manifest");
    committed = commitNextProtocolDerivedDecode(
        io, workspace, decode, scratch);
    assert(!committed.complete());
    assert(committed.stage == CommitStage::SyncManifest);
    recovery = recoverProtocolDerivedDecode(
        io, workspace, source, 2U, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 2U);

    // Corrupt newest payload: the first exact-source generation survives.
    io.flip("protocol-derived-00000008-00000002-00000002.bin", 40U);
    recovery = recoverProtocolDerivedDecode(
        io, workspace, source, 2U, &recovered);
    assert(recovery.valid());
    assert(recovery.storeGeneration == 1U);

    // Another annotation generation has an independent namespace and cannot
    // silently reuse this derived interpretation.
    recovery = recoverProtocolDerivedDecode(
        io, workspace, source, 3U, &recovered);
    assert(recovery.status == ProtocolDerivedDecodeStoreStatus::Empty);
    assert(!recovered.valid());

    ProtocolAnnotationSource foreign = source;
    ++foreign.captureFingerprint;
    recovery = recoverProtocolDerivedDecode(
        io, workspace, foreign, 2U, &recovered);
    assert(!recovery.valid());
    assert(!recovered.valid());
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

    testProtocolAnnotationsModelAndCodec();
    testProtocolAnnotationAtomicStore();
    testProtocolAnnotationTaskFlow();
    testProtocolComparison();
    testProtocolDerivedDecode();
    testProtocolDerivedDecodeAtomicStore();

    std::cout << "protocol workbench tests passed\n";
    return 0;
}
