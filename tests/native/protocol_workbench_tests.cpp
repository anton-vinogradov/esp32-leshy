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
#include "apps/protocol/ProtocolWorkbench.h"
#include "storage/ProtocolAnnotationCodec.h"
#include "storage/ProtocolAnnotationStore.h"

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

    std::cout << "protocol workbench tests passed\n";
    return 0;
}
