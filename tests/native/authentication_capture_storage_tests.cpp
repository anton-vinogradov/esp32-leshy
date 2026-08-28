#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "domain/observations/Observation.h"
#include "services/survey/SurveySession.h"
#include "storage/SessionCodec.h"
#include "storage/SessionStore.h"

namespace {

using leshy1::domain::captures::WifiFrameKind;
using leshy1::domain::captures::WifiFrameSource;
using leshy1::domain::captures::WifiFrameView;
using leshy1::services::survey::CaptureMetadata;
using leshy1::services::survey::CaptureMetadataStatus;
using leshy1::services::survey::FramePayloadFormat;
using leshy1::services::survey::SessionStatus;
using leshy1::services::survey::SurveySession;
using leshy1::storage::AuthenticationCaptureProvenance;
using leshy1::storage::AuthenticationCapturePurpose;
using leshy1::storage::HeadSlot;
using leshy1::storage::PersistedWifiFrameCaptureView;
using leshy1::storage::SessionCodecStatus;
using leshy1::storage::SessionManifest;
using leshy1::storage::SessionStoreIo;
using leshy1::storage::SessionStoreStatus;
using leshy1::storage::SessionStoreWorkspace;

static_assert(sizeof(AuthenticationCaptureProvenance) <= 64,
              "provenance must remain a small bounded value object");
static_assert(sizeof(PersistedWifiFrameCaptureView) <= 80,
              "persisted view must remain a small zero-copy object");
static_assert(sizeof(SessionStoreWorkspace) <= 24U * 1024U,
              "caller-owned storage workspace exceeded its host bound");

int failures = 0;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__,       \
                         __LINE__, #expression);                                \
            ++failures;                                                         \
        }                                                                       \
    } while (false)

class TwoFrameSource final : public WifiFrameSource {
public:
    TwoFrameSource() {
        for (std::size_t index = 0; index < first_.size(); ++index) {
            first_[index] = static_cast<std::uint8_t>(index);
            second_[index] = static_cast<std::uint8_t>(0xa0U + index);
        }
    }

    std::size_t frameCount() const override { return 2; }
    std::uint16_t snapLength() const override { return 64; }
    bool frameView(std::size_t index, WifiFrameView* output) const override {
        if (output == nullptr || index > 1) return false;
        output->monotonicUs = index == 0 ? 1100 : 1200;
        output->capturedLength = 32;
        output->originalLength = index == 0 ? 36 : 40;
        output->rssiDbm = index == 0 ? -42 : -51;
        output->channel = 6;
        output->kind = index == 0 ? WifiFrameKind::Management
                                  : WifiFrameKind::Data;
        output->fcsIncluded = index != 0;
        output->payload = index == 0 ? first_.data() : second_.data();
        return true;
    }

private:
    std::array<std::uint8_t, 32> first_{};
    std::array<std::uint8_t, 32> second_{};
};

SurveySession makeStoppedSession(const char* id) {
    SurveySession session;
    CHECK(session.start(id, 1000) == SessionStatus::Started);
    CaptureMetadata metadata;
    metadata.present = true;
    metadata.passive = true;
    metadata.selectedSourceMask = leshy1::services::survey::sourceMask(
        leshy1::domain::observations::RadioKind::Wifi);
    metadata.wifiMaxMsPerChannel = 120;
    metadata.wifiChannel = 6;
    metadata.framePayloadCaptured = true;
    metadata.framePayloadBytes = 64;
    metadata.framePayloadRecords = 2;
    metadata.framePayloadSnapLength = 64;
    metadata.framePayloadFormat = FramePayloadFormat::Ieee80211;
    for (std::size_t index = 0; index < metadata.appIdentity.size(); ++index) {
        metadata.appIdentity[index] = static_cast<std::uint8_t>(index + 1U);
    }
    metadata.appIdentityLength = metadata.appIdentity.size();
    CHECK(session.configureCaptureMetadata(metadata) ==
          CaptureMetadataStatus::Configured);
    CHECK(session.stop(2000) == SessionStatus::Stopped);
    return session;
}

AuthenticationCaptureProvenance makeProvenance() {
    AuthenticationCaptureProvenance provenance;
    provenance.purpose = AuthenticationCapturePurpose::Authentication;
    provenance.targetBssid = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    provenance.ssidKnown = true;
    provenance.ssidLength = 4;
    provenance.ssid[0] = 'A';
    provenance.ssid[1] = 0;
    provenance.ssid[2] = 'P';
    provenance.ssid[3] = '1';
    provenance.framesReported = 4;
    provenance.framesAccepted = 2;
    provenance.framesDroppedCapacity = 1;
    provenance.framesDroppedInvalid = 1;
    return provenance;
}

void put32(std::uint8_t* output, std::uint32_t value) {
    output[0] = static_cast<std::uint8_t>(value >> 24U);
    output[1] = static_cast<std::uint8_t>(value >> 16U);
    output[2] = static_cast<std::uint8_t>(value >> 8U);
    output[3] = static_cast<std::uint8_t>(value);
}

std::uint16_t get16(const std::uint8_t* input) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(input[0]) << 8U) |
        static_cast<std::uint16_t>(input[1]));
}

std::uint32_t get32(const std::uint8_t* input) {
    return (static_cast<std::uint32_t>(input[0]) << 24U) |
           (static_cast<std::uint32_t>(input[1]) << 16U) |
           (static_cast<std::uint32_t>(input[2]) << 8U) |
           static_cast<std::uint32_t>(input[3]);
}

void refreshSegmentChecksums(std::uint8_t* segment, std::size_t segmentSize) {
    CHECK(segment != nullptr);
    CHECK(segmentSize >= leshy1::storage::kSegmentFooterBytes + 8U);
    if (segment == nullptr ||
        segmentSize < leshy1::storage::kSegmentFooterBytes + 8U) {
        return;
    }
    const std::uint32_t captureLength = get32(segment);
    CHECK(captureLength <= segmentSize - 8U);
    if (captureLength > segmentSize - 8U) return;
    put32(segment + 4, leshy1::storage::crc32c(segment + 8, captureLength));
    const std::size_t bodySize =
        segmentSize - leshy1::storage::kSegmentFooterBytes;
    std::uint8_t* footer = segment + bodySize;
    put32(footer + 16, leshy1::storage::crc32c(segment, bodySize));
    put32(footer + 20, leshy1::storage::crc32c(footer, 20));
}

class MemorySessionStoreIo final : public SessionStoreIo {
public:
    bool writeFile(const char* path, const std::uint8_t* data,
                   std::size_t size) override {
        if (path == nullptr || (data == nullptr && size != 0)) return false;
        files_[path] = std::vector<std::uint8_t>(data, data + size);
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

    bool syncFile(const char*) override { return true; }
    bool syncDirectory() override { return true; }

    bool flip(const char* path, std::size_t offset) {
        const auto found = files_.find(path);
        if (found == files_.end() || offset >= found->second.size()) {
            return false;
        }
        found->second[offset] ^= 0x01U;
        return true;
    }

private:
    std::map<std::string, std::vector<std::uint8_t>> files_;
};

void testSchemaEightRoundTripAndGenericOpen() {
    const SurveySession session = makeStoppedSession("auth-roundtrip");
    const TwoFrameSource frames;
    const AuthenticationCaptureProvenance expected = makeProvenance();
    std::array<std::uint8_t, leshy1::storage::kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, leshy1::storage::kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, expected, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    CHECK(get32(segment.data()) == 132);
    CHECK(get32(segment.data() + 4) ==
          leshy1::storage::crc32c(segment.data() + 8, 132));
    CHECK(segment[8 + 4] == 5);
    CHECK(segment[8 + 72] == 1);
    CHECK(segment[8 + 73] == 1);
    CHECK(segment[8 + 74] == 4);
    CHECK(segment[8 + 75] == 0);
    CHECK(segment[8 + 130] == 0);
    CHECK(segment[8 + 131] == 0);
    const std::uint8_t* footer =
        segment.data() + segmentSize - leshy1::storage::kSegmentFooterBytes;
    CHECK(get16(footer + 4) ==
          leshy1::storage::kAuthenticationCaptureSegmentSchemaVersion);
    CHECK(get16(footer + 6) == 2);
    CHECK(get32(footer + 8) == 0);
    CHECK(get32(footer + 12) ==
          segmentSize - leshy1::storage::kSegmentFooterBytes);
    CHECK(get32(footer + 16) == leshy1::storage::crc32c(
              segment.data(), segmentSize -
                                  leshy1::storage::kSegmentFooterBytes));
    CHECK(get32(footer + 20) == leshy1::storage::crc32c(footer, 20));
    CHECK(leshy1::storage::encodeSessionManifest(
              session, segment.data(), segmentSize, manifest.data(),
              manifest.size(), &manifestSize) == SessionCodecStatus::Valid);
    SessionManifest decodedManifest;
    CHECK(leshy1::storage::decodeSessionManifest(
              manifest.data(), manifestSize, &decodedManifest) ==
          SessionCodecStatus::Valid);
    CHECK(decodedManifest.schemaVersion ==
          leshy1::storage::kAuthenticationCaptureSessionSchemaVersion);

    SurveySession reopened;
    CHECK(leshy1::storage::reopenSession(
              manifest.data(), manifestSize, segment.data(), segmentSize,
              &reopened) == SessionCodecStatus::Valid);
    PersistedWifiFrameCaptureView generic;
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              reopened, segment.data(), segmentSize, &generic) ==
          SessionCodecStatus::Valid);
    CHECK(generic.frameCount() == 2);

    AuthenticationCaptureProvenance actual;
    PersistedWifiFrameCaptureView authenticated;
    CHECK(leshy1::storage::openPersistedAuthenticationCapture(
              reopened, segment.data(), segmentSize, &actual,
              &authenticated) == SessionCodecStatus::Valid);
    CHECK(actual.purpose == expected.purpose);
    CHECK(actual.targetBssid == expected.targetBssid);
    CHECK(actual.ssid == expected.ssid);
    CHECK(actual.ssidLength == expected.ssidLength);
    CHECK(actual.ssidKnown == expected.ssidKnown);
    CHECK(actual.framesReported == expected.framesReported);
    CHECK(actual.framesAccepted == expected.framesAccepted);
    CHECK(actual.framesDroppedCapacity == expected.framesDroppedCapacity);
    CHECK(actual.framesDroppedInvalid == expected.framesDroppedInvalid);
}

void testSchemaFourRemainsReadable() {
    const SurveySession session = makeStoppedSession("schema-four");
    const TwoFrameSource frames;
    std::array<std::uint8_t, leshy1::storage::kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, leshy1::storage::kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(leshy1::storage::encodeWifiFrameCaptureSegment(
              session, frames, segment.data(), segment.size(), &segmentSize) ==
          SessionCodecStatus::Valid);
    CHECK(leshy1::storage::encodeSessionManifest(
              session, segment.data(), segmentSize, manifest.data(),
              manifest.size(), &manifestSize) == SessionCodecStatus::Valid);
    SessionManifest decodedManifest;
    CHECK(leshy1::storage::decodeSessionManifest(
              manifest.data(), manifestSize, &decodedManifest) ==
          SessionCodecStatus::Valid);
    CHECK(decodedManifest.schemaVersion ==
          leshy1::storage::kWifiFrameSessionSchemaVersion);
    SurveySession reopened;
    CHECK(leshy1::storage::reopenSession(
              manifest.data(), manifestSize, segment.data(), segmentSize,
              &reopened) == SessionCodecStatus::Valid);
    PersistedWifiFrameCaptureView generic;
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              reopened, segment.data(), segmentSize, &generic) ==
          SessionCodecStatus::Valid);
    AuthenticationCaptureProvenance provenance;
    CHECK(leshy1::storage::openPersistedAuthenticationCapture(
              reopened, segment.data(), segmentSize, &provenance, &generic) ==
          SessionCodecStatus::UnsupportedSchema);
}

void testSchemaEightGenericPurpose() {
    const SurveySession session = makeStoppedSession("generic-purpose");
    const TwoFrameSource frames;
    AuthenticationCaptureProvenance expected = makeProvenance();
    expected.purpose = AuthenticationCapturePurpose::Generic;
    expected.targetBssid.fill(0);
    expected.ssid.fill(0);
    expected.ssidLength = 0;
    expected.ssidKnown = false;
    std::array<std::uint8_t, leshy1::storage::kSessionSegmentMaxBytes> segment{};
    std::size_t segmentSize = 0;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, expected, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    AuthenticationCaptureProvenance actual;
    PersistedWifiFrameCaptureView view;
    CHECK(leshy1::storage::openPersistedAuthenticationCapture(
              session, segment.data(), segmentSize, &actual, &view) ==
          SessionCodecStatus::Valid);
    CHECK(actual.purpose == AuthenticationCapturePurpose::Generic);
    CHECK(actual.framesAccepted == 2);
}

void testInvalidProvenanceAndCorruptionFailClosed() {
    const SurveySession session = makeStoppedSession("auth-invalid");
    const TwoFrameSource frames;
    std::array<std::uint8_t, leshy1::storage::kSessionSegmentMaxBytes> segment{};
    std::size_t segmentSize = 0;

    AuthenticationCaptureProvenance invalidLength = makeProvenance();
    invalidLength.ssidLength = 33;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, invalidLength, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::CaptureInvalid);

    AuthenticationCaptureProvenance invalidAccounting = makeProvenance();
    ++invalidAccounting.framesReported;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, invalidAccounting, frames, segment.data(),
              segment.size(), &segmentSize) ==
          SessionCodecStatus::CaptureInvalid);

    AuthenticationCaptureProvenance invalidKnownEmpty = makeProvenance();
    invalidKnownEmpty.ssid.fill(0);
    invalidKnownEmpty.ssidLength = 0;
    invalidKnownEmpty.ssidKnown = true;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, invalidKnownEmpty, frames, segment.data(),
              segment.size(), &segmentSize) ==
          SessionCodecStatus::CaptureInvalid);

    AuthenticationCaptureProvenance unknownAuthentication = makeProvenance();
    unknownAuthentication.ssid.fill(0);
    unknownAuthentication.ssidLength = 0;
    unknownAuthentication.ssidKnown = false;
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, unknownAuthentication, frames, segment.data(),
              segment.size(), &segmentSize) == SessionCodecStatus::Valid);

    const AuthenticationCaptureProvenance valid = makeProvenance();
    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, valid, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    segment[8 + 82] ^= 0x01U;
    PersistedWifiFrameCaptureView view;
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              session, segment.data(), segmentSize, &view) ==
          SessionCodecStatus::ChecksumMismatch);

    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, valid, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    segment[8 + 74] = 33;
    refreshSegmentChecksums(segment.data(), segmentSize);
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              session, segment.data(), segmentSize, &view) ==
          SessionCodecStatus::CaptureInvalid);

    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, valid, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    segment[8 + 117] = 5;
    refreshSegmentChecksums(segment.data(), segmentSize);
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              session, segment.data(), segmentSize, &view) ==
          SessionCodecStatus::CaptureInvalid);

    CHECK(leshy1::storage::encodeAuthenticationCaptureSegment(
              session, valid, frames, segment.data(), segment.size(),
              &segmentSize) == SessionCodecStatus::Valid);
    segment[8 + 117] = 5;
    segment[8 + 121] = 3;
    refreshSegmentChecksums(segment.data(), segmentSize);
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              session, segment.data(), segmentSize, &view) ==
          SessionCodecStatus::CaptureInvalid);
}

void testAtomicBoundaryRecoveryFallsBackToSchemaFour() {
    MemorySessionStoreIo io;
    SessionStoreWorkspace workspace;
    const SurveySession session = makeStoppedSession("auth-store");
    const TwoFrameSource frames;
    const AuthenticationCaptureProvenance provenance = makeProvenance();

    CHECK(leshy1::storage::commitWifiFrameCapture(
              io, workspace, session, frames, 1, HeadSlot::A).status ==
          SessionStoreStatus::Valid);
    CHECK(leshy1::storage::commitAuthenticationCapture(
              io, workspace, session, provenance, frames, 2,
              HeadSlot::B).status == SessionStoreStatus::Valid);
    SurveySession recovered;
    auto recovery = leshy1::storage::recoverSession(io, workspace, &recovered);
    CHECK(recovery.status == SessionStoreStatus::Valid);
    CHECK(recovery.generation == 2);
    AuthenticationCaptureProvenance actual;
    PersistedWifiFrameCaptureView view;
    CHECK(leshy1::storage::openPersistedAuthenticationCapture(
              recovered, workspace.segment.data(), workspace.segmentSize,
              &actual, &view) == SessionCodecStatus::Valid);

    CHECK(io.flip("segment-00000002.bin", 8 + 114));
    recovery = leshy1::storage::recoverSession(io, workspace, &recovered);
    CHECK(recovery.status == SessionStoreStatus::Valid);
    CHECK(recovery.generation == 1);
    CHECK(leshy1::storage::openPersistedWifiFrameCapture(
              recovered, workspace.segment.data(), workspace.segmentSize,
              &view) == SessionCodecStatus::Valid);
}

}  // namespace

int main() {
    testSchemaEightRoundTripAndGenericOpen();
    testSchemaFourRemainsReadable();
    testSchemaEightGenericPurpose();
    testInvalidProvenanceAndCorruptionFailClosed();
    testAtomicBoundaryRecoveryFallsBackToSchemaFour();
    if (failures != 0) {
        std::fprintf(stderr, "%d authentication capture storage checks failed\n",
                     failures);
        return 1;
    }
    std::puts("authentication capture storage checks passed");
    return 0;
}
