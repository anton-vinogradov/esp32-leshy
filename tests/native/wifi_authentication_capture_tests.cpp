#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "services/auth/WifiAuthenticationCapture.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using leshy1::domain::captures::WifiFrameKind;
using leshy1::domain::captures::WifiFrameSource;
using leshy1::domain::captures::WifiFrameView;
using namespace leshy1::services::auth;

constexpr std::array<std::uint8_t, 6> kAccessPoint{
    0x02U, 0x11U, 0x22U, 0x33U, 0x44U, 0x55U};
constexpr std::array<std::uint8_t, 6> kStation{
    0x06U, 0xaaU, 0xbbU, 0xccU, 0xddU, 0xeeU};
constexpr std::array<std::uint8_t, 6> kOtherStation{
    0x0aU, 0xaaU, 0xbbU, 0xccU, 0xddU, 0xefU};
constexpr std::array<std::uint8_t, 6> kOtherAccessPoint{
    0x0eU, 0x11U, 0x22U, 0x33U, 0x44U, 0x66U};
constexpr std::array<std::uint8_t, 16> kPmkid{
    0x00U, 0x01U, 0x02U, 0x03U, 0x04U, 0x05U, 0x06U, 0x07U,
    0x08U, 0x09U, 0x0aU, 0x0bU, 0x0cU, 0x0dU, 0x0eU, 0x0fU};

struct FixtureFrame final {
    std::array<std::uint8_t, 256> payload{};
    std::uint16_t capturedLength = 0;
    std::uint16_t originalLength = 0;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = -52;
    std::uint8_t channel = 6;
    WifiFrameKind kind = WifiFrameKind::Data;
    bool readable = true;
    bool fcsIncluded = false;
};

class FixtureSource final : public WifiFrameSource {
public:
    static constexpr std::size_t kCapacity = 68;

    FixtureFrame& addEapolKey(
        WifiEapolKeyMessage message, std::uint64_t replayCounter,
        const std::array<std::uint8_t, 6>& accessPoint = kAccessPoint,
        const std::array<std::uint8_t, 6>& station = kStation,
        const std::array<std::uint8_t, 16>* pmkid = nullptr,
        std::uint8_t eapolVersion = 2U,
        std::uint8_t descriptorType = 2U,
        std::uint8_t descriptorVersion = 2U) {
        CHECK(size_ < frames_.size());
        FixtureFrame& frame = frames_[size_++];
        frame = {};
        frame.kind = WifiFrameKind::Data;
        frame.monotonicUs = 1000000ULL + size_ * 1000ULL;
        frame.rssiDbm = -52;
        frame.channel = 6;

        const bool fromAccessPoint =
            message == WifiEapolKeyMessage::Message1 ||
            message == WifiEapolKeyMessage::Message3;
        frame.payload[0] = 0x08U;
        frame.payload[1] = fromAccessPoint ? 0x02U : 0x01U;
        if (fromAccessPoint) {
            std::memcpy(frame.payload.data() + 4U, station.data(),
                        station.size());
            std::memcpy(frame.payload.data() + 10U, accessPoint.data(),
                        accessPoint.size());
        } else {
            std::memcpy(frame.payload.data() + 4U, accessPoint.data(),
                        accessPoint.size());
            std::memcpy(frame.payload.data() + 10U, station.data(),
                        station.size());
        }
        std::memcpy(frame.payload.data() + 16U, accessPoint.data(),
                    accessPoint.size());

        std::size_t offset = 24U;
        const std::array<std::uint8_t, 8> llc{
            0xaaU, 0xaaU, 0x03U, 0x00U, 0x00U, 0x00U, 0x88U, 0x8eU};
        std::memcpy(frame.payload.data() + offset, llc.data(), llc.size());
        offset += llc.size();
        const std::size_t eapolOffset = offset;
        frame.payload[offset++] = eapolVersion;
        frame.payload[offset++] = 3U;
        const std::size_t eapolLengthOffset = offset;
        offset += 2U;
        const std::size_t keyOffset = offset;
        frame.payload[offset++] = descriptorType;
        std::uint16_t keyInfo = static_cast<std::uint16_t>(
            (1U << 3U) | descriptorVersion);
        switch (message) {
            case WifiEapolKeyMessage::Message1:
                keyInfo |= 1U << 7U;
                break;
            case WifiEapolKeyMessage::Message2:
                keyInfo |= 1U << 8U;
                break;
            case WifiEapolKeyMessage::Message3:
                keyInfo |= (1U << 6U) | (1U << 7U) | (1U << 8U) |
                           (1U << 9U);
                break;
            case WifiEapolKeyMessage::Message4:
                keyInfo |= (1U << 8U) | (1U << 9U);
                break;
            case WifiEapolKeyMessage::Unknown:
                keyInfo = 2U;
                break;
        }
        frame.payload[offset++] = static_cast<std::uint8_t>(keyInfo >> 8U);
        frame.payload[offset++] = static_cast<std::uint8_t>(keyInfo);
        frame.payload[offset++] = 0U;
        frame.payload[offset++] = 16U;
        for (int shift = 56; shift >= 0; shift -= 8) {
            frame.payload[offset++] = static_cast<std::uint8_t>(
                replayCounter >> static_cast<unsigned>(shift));
        }
        if (message == WifiEapolKeyMessage::Message1 ||
            message == WifiEapolKeyMessage::Message3) {
            for (std::size_t index = 0; index < 32U; ++index) {
                frame.payload[keyOffset + 13U + index] =
                    static_cast<std::uint8_t>(0xa0U + index);
            }
        } else if (message == WifiEapolKeyMessage::Message2) {
            for (std::size_t index = 0; index < 32U; ++index) {
                frame.payload[keyOffset + 13U + index] =
                    static_cast<std::uint8_t>(0x40U + index);
            }
        }
        if (message == WifiEapolKeyMessage::Message2 ||
            message == WifiEapolKeyMessage::Message3 ||
            message == WifiEapolKeyMessage::Message4) {
            frame.payload[keyOffset + 77U] = 0x5aU;
        }
        offset = keyOffset + 93U;
        const std::size_t keyDataLength = pmkid == nullptr ? 0U : 22U;
        frame.payload[offset++] = static_cast<std::uint8_t>(
            keyDataLength >> 8U);
        frame.payload[offset++] = static_cast<std::uint8_t>(keyDataLength);
        if (pmkid != nullptr) {
            frame.payload[offset++] = 0xddU;
            frame.payload[offset++] = 20U;
            frame.payload[offset++] = 0x00U;
            frame.payload[offset++] = 0x0fU;
            frame.payload[offset++] = 0xacU;
            frame.payload[offset++] = 0x04U;
            std::memcpy(frame.payload.data() + offset, pmkid->data(),
                        pmkid->size());
            offset += pmkid->size();
        }
        const std::size_t eapolBodyLength = offset - keyOffset;
        frame.payload[eapolLengthOffset] = static_cast<std::uint8_t>(
            eapolBodyLength >> 8U);
        frame.payload[eapolLengthOffset + 1U] =
            static_cast<std::uint8_t>(eapolBodyLength);
        frame.capturedLength = static_cast<std::uint16_t>(offset);
        frame.originalLength = frame.capturedLength;
        CHECK(eapolOffset + 4U + eapolBodyLength == offset);
        return frame;
    }

    FixtureFrame& addOrdinaryFrame(WifiFrameKind kind) {
        CHECK(size_ < frames_.size());
        FixtureFrame& frame = frames_[size_++];
        frame = {};
        frame.kind = kind;
        frame.monotonicUs = 2000000ULL + size_ * 1000ULL;
        frame.channel = 11;
        frame.rssiDbm = -70;
        frame.capturedLength = 32;
        frame.originalLength = 32;
        frame.payload[0] = kind == WifiFrameKind::Data ? 0x08U : 0x80U;
        return frame;
    }

    FixtureFrame& mutableAt(std::size_t index) {
        CHECK(index < size_);
        return frames_[index];
    }

    void addQosHeader(FixtureFrame& frame) {
        CHECK(frame.capturedLength + 2U <= frame.payload.size());
        std::memmove(frame.payload.data() + 26U, frame.payload.data() + 24U,
                     frame.capturedLength - 24U);
        frame.payload[0] = static_cast<std::uint8_t>(frame.payload[0] | 0x80U);
        frame.payload[24] = 0U;
        frame.payload[25] = 0U;
        frame.capturedLength = static_cast<std::uint16_t>(
            frame.capturedLength + 2U);
        frame.originalLength = frame.capturedLength;
    }

    void appendFcs(FixtureFrame& frame) {
        CHECK(frame.capturedLength + 4U <= frame.payload.size());
        for (std::size_t index = 0; index < 4U; ++index) {
            frame.payload[frame.capturedLength + index] =
                static_cast<std::uint8_t>(0xf0U + index);
        }
        frame.capturedLength = static_cast<std::uint16_t>(
            frame.capturedLength + 4U);
        frame.originalLength = frame.capturedLength;
        frame.fcsIncluded = true;
    }

    std::size_t frameCount() const override { return size_; }
    std::uint16_t snapLength() const override { return 256; }
    bool frameView(std::size_t index, WifiFrameView* output) const override {
        if (output == nullptr || index >= size_ || !frames_[index].readable) {
            return false;
        }
        const FixtureFrame& frame = frames_[index];
        output->monotonicUs = frame.monotonicUs;
        output->capturedLength = frame.capturedLength;
        output->originalLength = frame.originalLength;
        output->rssiDbm = frame.rssiDbm;
        output->channel = frame.channel;
        output->kind = frame.kind;
        output->fcsIncluded = frame.fcsIncluded;
        output->payload = frame.payload.data();
        return true;
    }

private:
    std::array<FixtureFrame, kCapacity> frames_{};
    std::size_t size_ = 0;
};

WifiAuthenticationCaptureInput completeInput(const FixtureSource& source) {
    WifiAuthenticationCaptureInput input{};
    input.source = &source;
    input.captureComplete = true;
    input.framesReported = static_cast<std::uint32_t>(source.frameCount());
    input.framesAccepted = input.framesReported;
    return input;
}

WifiFrameView viewOf(const FixtureFrame& frame) {
    WifiFrameView view{};
    view.monotonicUs = frame.monotonicUs;
    view.capturedLength = frame.capturedLength;
    view.originalLength = frame.originalLength;
    view.rssiDbm = frame.rssiDbm;
    view.channel = frame.channel;
    view.kind = frame.kind;
    view.fcsIncluded = frame.fcsIncluded;
    view.payload = frame.payload.data();
    return view;
}

bool hasUncertainty(const WifiAuthenticationCaptureReport& report,
                    WifiAuthenticationUncertainty uncertainty) {
    return (report.uncertainty & static_cast<std::uint16_t>(uncertainty)) != 0U;
}

bool hasNonzero(const std::array<std::uint8_t, 32>& value) {
    for (std::uint8_t octet : value) {
        if (octet != 0U) return true;
    }
    return false;
}

void testSharedDecoderPreservesNonQosQosFcsAndTargetIdentity() {
    FixtureSource source;
    FixtureFrame& nonQos = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 5U, kAccessPoint, kStation, &kPmkid);
    WifiAuthenticationDecodedKeyFrame decoded{};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(nonQos), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::ClassifiedKey);
    CHECK(decoded.message == WifiEapolKeyMessage::Message1);
    CHECK(decoded.accessPoint == kAccessPoint);
    CHECK(decoded.station == kStation);
    CHECK(decoded.replayCounter == 5U);
    CHECK(decoded.descriptorType == 2U);
    CHECK(decoded.descriptorVersion == 2U);
    CHECK(decoded.fromAccessPoint);
    CHECK(decoded.hasPmkid);
    CHECK(decoded.pmkid == kPmkid);
    CHECK(classifyWifiAuthenticationIngress(viewOf(nonQos),
                                             kOtherAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& qos = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 5U);
    source.addQosHeader(qos);
    decoded = {};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(qos), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::ClassifiedKey);
    CHECK(decoded.message == WifiEapolKeyMessage::Message2);
    CHECK(decoded.keyMicNonzero);
    CHECK(decoded.accessPoint == kAccessPoint);
    CHECK(decoded.station == kStation);
    CHECK(!decoded.fromAccessPoint);

    FixtureFrame& fcs = source.addEapolKey(
        WifiEapolKeyMessage::Message3, 6U);
    source.addQosHeader(fcs);
    source.appendFcs(fcs);
    decoded = {};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(fcs), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::ClassifiedKey);
    CHECK(decoded.message == WifiEapolKeyMessage::Message3);
    CHECK(decoded.replayCounter == 6U);
}

void testSharedDecoderPreservesMalformedAndTruncatedBoundaries() {
    FixtureSource malformed;
    FixtureFrame& badVersion = malformed.addEapolKey(
        WifiEapolKeyMessage::Message1, 10U);
    badVersion.payload[32U] = 0U;
    WifiAuthenticationDecodedKeyFrame decoded{};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(badVersion), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::Malformed);

    FixtureSource truncated;
    FixtureFrame& shortFrame = truncated.addEapolKey(
        WifiEapolKeyMessage::Message1, 11U);
    shortFrame.capturedLength = 70U;
    CHECK(shortFrame.originalLength > shortFrame.capturedLength);
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(shortFrame), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::Truncated);

    FixtureSource ignored;
    FixtureFrame& management = ignored.addOrdinaryFrame(
        WifiFrameKind::Management);
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(management), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::Ignored);
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(management), nullptr) ==
          WifiAuthenticationFrameDecodeStatus::Malformed);
}

void testSharedDecoderPreservesDescriptorAndProfileClassification() {
    FixtureSource unsupportedType;
    FixtureFrame& legacy = unsupportedType.addEapolKey(
        WifiEapolKeyMessage::Message1, 20U, kAccessPoint, kStation, nullptr,
        2U, 1U, 2U);
    WifiAuthenticationDecodedKeyFrame decoded{};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(legacy), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::UnsupportedKey);
    CHECK(decoded.descriptorType == 1U);

    FixtureSource unsupportedVersion;
    FixtureFrame& versionOne = unsupportedVersion.addEapolKey(
        WifiEapolKeyMessage::Message1, 21U, kAccessPoint, kStation, nullptr,
        2U, 2U, 1U);
    decoded = {};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(versionOne), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::UnsupportedKey);
    CHECK(decoded.descriptorType == 2U);
    CHECK(decoded.descriptorVersion == 1U);

    FixtureSource unclassified;
    FixtureFrame& smk = unclassified.addEapolKey(
        WifiEapolKeyMessage::Message1, 22U);
    smk.payload[37U] = static_cast<std::uint8_t>(
        smk.payload[37U] | 0x20U);
    decoded = {};
    CHECK(decodeWifiAuthenticationKeyFrame(viewOf(smk), &decoded) ==
          WifiAuthenticationFrameDecodeStatus::UnclassifiedKey);
    CHECK(decoded.message == WifiEapolKeyMessage::Unknown);
}

void testClassifiedMicBearingMessagesRequireNonzeroKeyMic() {
    constexpr std::array<WifiEapolKeyMessage, 3> kMicBearingMessages{
        WifiEapolKeyMessage::Message2,
        WifiEapolKeyMessage::Message3,
        WifiEapolKeyMessage::Message4};
    constexpr std::size_t kNonQosKeyMicOffset = 24U + 8U + 4U + 77U;
    for (std::size_t index = 0U; index < kMicBearingMessages.size(); ++index) {
        FixtureSource source;
        FixtureFrame& frame = source.addEapolKey(
            kMicBearingMessages[index], 23U + index);
        WifiAuthenticationDecodedKeyFrame decoded{};
        CHECK(decodeWifiAuthenticationKeyFrame(viewOf(frame), &decoded) ==
              WifiAuthenticationFrameDecodeStatus::ClassifiedKey);
        CHECK(decoded.keyMicNonzero);

        frame.payload[kNonQosKeyMicOffset] = 0U;
        CHECK(decodeWifiAuthenticationKeyFrame(viewOf(frame), &decoded) ==
              WifiAuthenticationFrameDecodeStatus::Malformed);
        CHECK(!decoded.keyMicNonzero);

        WifiAuthenticationCaptureReport report{};
        CHECK(analyzeWifiAuthenticationCapture(completeInput(source),
                                               &report));
        CHECK(report.outcome ==
              WifiAuthenticationCaptureOutcome::Inconclusive);
        CHECK(report.counters.malformedFrames == 1U);
        CHECK(report.evidenceCount == 0U);
        CHECK(hasUncertainty(report,
                             WifiAuthenticationUncertaintyMalformed));
    }
}

void testIngressRetainsTargetNonQosQosAndFcs() {
    FixtureSource source;
    FixtureFrame& nonQos = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 1U);
    CHECK(classifyWifiAuthenticationIngress(viewOf(nonQos), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& qos = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 1U);
    source.addQosHeader(qos);
    CHECK(classifyWifiAuthenticationIngress(viewOf(qos), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& fcs = source.addEapolKey(
        WifiEapolKeyMessage::Message3, 2U);
    source.appendFcs(fcs);
    CHECK(classifyWifiAuthenticationIngress(viewOf(fcs), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& qosFcs = source.addEapolKey(
        WifiEapolKeyMessage::Message4, 2U);
    source.addQosHeader(qosFcs);
    source.appendFcs(qosFcs);
    CHECK(classifyWifiAuthenticationIngress(viewOf(qosFcs), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);
}

void testIngressIgnoresWrongBssidAndNonEapol() {
    FixtureSource source;
    FixtureFrame& wrongTarget = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 3U);
    CHECK(classifyWifiAuthenticationIngress(viewOf(wrongTarget),
                                             kOtherAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& nonEapol = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 3U);
    nonEapol.payload[31U] = 0x00U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(nonEapol), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& protectedFrame = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 4U);
    protectedFrame.payload[1U] = static_cast<std::uint8_t>(
        protectedFrame.payload[1U] | 0x40U);
    CHECK(classifyWifiAuthenticationIngress(viewOf(protectedFrame),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& management = source.addOrdinaryFrame(
        WifiFrameKind::Management);
    CHECK(classifyWifiAuthenticationIngress(viewOf(management), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);
}

void testIngressIgnoresCompleteNullDataButRetainsTruncation() {
    FixtureSource source;

    FixtureFrame& completeNull = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 5U);
    completeNull.payload[0U] = 0x48U;
    completeNull.capturedLength = 24U;
    completeNull.originalLength = completeNull.capturedLength;
    CHECK(classifyWifiAuthenticationIngress(viewOf(completeNull),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& completeQosNull = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 5U);
    source.addQosHeader(completeQosNull);
    completeQosNull.payload[0U] = 0xc8U;
    completeQosNull.capturedLength = 26U;
    completeQosNull.originalLength = completeQosNull.capturedLength;
    CHECK(classifyWifiAuthenticationIngress(viewOf(completeQosNull),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& completeNullWithFcs = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 6U);
    completeNullWithFcs.payload[0U] = 0x48U;
    completeNullWithFcs.capturedLength = 24U;
    completeNullWithFcs.originalLength = completeNullWithFcs.capturedLength;
    source.appendFcs(completeNullWithFcs);
    CHECK(classifyWifiAuthenticationIngress(viewOf(completeNullWithFcs),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& truncatedNull = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 7U);
    truncatedNull.payload[0U] = 0x48U;
    truncatedNull.capturedLength = 24U;
    CHECK(truncatedNull.originalLength > truncatedNull.capturedLength);
    CHECK(classifyWifiAuthenticationIngress(viewOf(truncatedNull),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& truncatedQosNull = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 7U);
    source.addQosHeader(truncatedQosNull);
    truncatedQosNull.payload[0U] = 0xc8U;
    truncatedQosNull.capturedLength = 25U;
    CHECK(truncatedQosNull.originalLength > truncatedQosNull.capturedLength);
    CHECK(classifyWifiAuthenticationIngress(viewOf(truncatedQosNull),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& malformedCompleteQosNull = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 8U);
    malformedCompleteQosNull.payload[0U] = 0xc8U;
    malformedCompleteQosNull.capturedLength = 24U;
    malformedCompleteQosNull.originalLength =
        malformedCompleteQosNull.capturedLength;
    CHECK(classifyWifiAuthenticationIngress(viewOf(malformedCompleteQosNull),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& completeHeaderOnlyData = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 9U);
    completeHeaderOnlyData.capturedLength = 24U;
    completeHeaderOnlyData.originalLength =
        completeHeaderOnlyData.capturedLength;
    CHECK(classifyWifiAuthenticationIngress(viewOf(completeHeaderOnlyData),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);
}

void testIngressRetainsProvableTargetFailuresFailClosed() {
    FixtureSource source;
    FixtureFrame& truncated = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 5U);
    truncated.capturedLength = 28U;
    CHECK(truncated.originalLength > truncated.capturedLength);
    CHECK(classifyWifiAuthenticationIngress(viewOf(truncated), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& headerOnly = source.addEapolKey(
        WifiEapolKeyMessage::Message2, 5U);
    headerOnly.capturedLength = 24U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(headerOnly), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& malformedMetadata = source.addEapolKey(
        WifiEapolKeyMessage::Message3, 6U);
    malformedMetadata.originalLength = 0U;
    malformedMetadata.monotonicUs = 0U;
    malformedMetadata.channel = 0U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(malformedMetadata),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& malformedStation = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 7U);
    malformedStation.payload[4U] = 0x01U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(malformedStation),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& malformedEapol = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 8U);
    malformedEapol.payload[32U] = 0U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(malformedEapol),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);

    FixtureFrame& unsupportedDescriptor = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 9U, kAccessPoint, kStation, nullptr,
        2U, 0xfeU, 2U);
    CHECK(classifyWifiAuthenticationIngress(viewOf(unsupportedDescriptor),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Retain);
}

void testIngressRejectsUnidentifiableMalformedFrames() {
    FixtureSource source;
    FixtureFrame& shortFrame = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 10U);
    shortFrame.capturedLength = 20U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(shortFrame), kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Invalid);

    FixtureFrame& wrongFrameControl = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 11U);
    wrongFrameControl.payload[0U] = 0x00U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(wrongFrameControl),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Invalid);

    FixtureFrame& ambiguousDirection = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 12U);
    ambiguousDirection.payload[1U] = 0x00U;
    CHECK(classifyWifiAuthenticationIngress(viewOf(ambiguousDirection),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Ignore);

    FixtureFrame& malformedFcs = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 13U);
    malformedFcs.capturedLength = 3U;
    malformedFcs.originalLength = 3U;
    malformedFcs.fcsIncluded = true;
    CHECK(classifyWifiAuthenticationIngress(viewOf(malformedFcs),
                                             kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Invalid);

    WifiFrameView nullFrame{};
    CHECK(classifyWifiAuthenticationIngress(nullFrame, kAccessPoint) ==
          WifiAuthenticationIngressDisposition::Invalid);
    constexpr std::array<std::uint8_t, 6> kInvalidTarget{};
    CHECK(classifyWifiAuthenticationIngress(viewOf(shortFrame),
                                             kInvalidTarget) ==
          WifiAuthenticationIngressDisposition::Invalid);
}

void testCompleteHandshakeAndPmkidRetainExactEvidence() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 7U, kAccessPoint,
                       kStation, &kPmkid);
    source.addEapolKey(WifiEapolKeyMessage::Message2, 7U);
    source.addEapolKey(WifiEapolKeyMessage::Message3, 8U);
    source.addEapolKey(WifiEapolKeyMessage::Message4, 8U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Complete);
    CHECK(report.uncertainty == WifiAuthenticationUncertaintyNone);
    CHECK(report.counters.framesRead == 4U);
    CHECK(report.counters.eapolFrames == 4U);
    CHECK(report.counters.classifiedKeyFrames == 4U);
    CHECK(report.evidenceCount == 4U);
    CHECK(report.peerCount == 1U);
    CHECK(report.peers[0].messageMask == 0x0fU);
    CHECK(report.peers[0].replayCountersConsistent);
    CHECK(report.peers[0].keyMaterialConsistent);
    CHECK(report.peers[0].complete);
    CHECK(report.peers[0].accessPoint == kAccessPoint);
    CHECK(report.peers[0].station == kStation);
    for (std::size_t index = 0; index < 4U; ++index) {
        CHECK(report.evidence[index].sourceFrameIndex == index);
        CHECK(report.evidence[index].message ==
              static_cast<WifiEapolKeyMessage>(index + 1U));
        CHECK(report.peers[0].evidenceIndices[index] == index);
    }
    CHECK(report.pmkidCount == 1U);
    CHECK(report.pmkids[0].sourceFrameIndex == 0U);
    CHECK(report.pmkids[0].accessPoint == kAccessPoint);
    CHECK(report.pmkids[0].station == kStation);
    CHECK(report.pmkids[0].pmkid == kPmkid);
    CHECK(std::strcmp(wifiAuthenticationCaptureOutcomeName(report.outcome),
                      "complete") == 0);
    CHECK(std::strcmp(wifiEapolKeyMessageName(
                          WifiEapolKeyMessage::Message3),
                      "message_3") == 0);
}

void testIncompleteHandshakeIsExplicitAndPeersNeverMerge() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 11U);
    source.addEapolKey(WifiEapolKeyMessage::Message2, 11U, kAccessPoint,
                       kOtherStation);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(report.uncertainty == WifiAuthenticationUncertaintyNone);
    CHECK(report.peerCount == 2U);
    CHECK(report.peers[0].messageMask == 0x01U);
    CHECK(report.peers[1].messageMask == 0x00U);
    CHECK(report.counters.sequenceRejected == 1U);
    CHECK(!report.peers[0].complete);
    CHECK(!report.peers[1].complete);
}

void testReplayMismatchCannotBecomeComplete() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 20U);
    source.addEapolKey(WifiEapolKeyMessage::Message2, 21U);
    source.addEapolKey(WifiEapolKeyMessage::Message3, 22U);
    source.addEapolKey(WifiEapolKeyMessage::Message4, 22U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(report.peers[0].messageMask == 0x01U);
    CHECK(!report.peers[0].replayCountersConsistent);
    CHECK(report.counters.sequenceRejected == 3U);
    CHECK(!report.peers[0].complete);
}

void testMismatchedAuthenticatorNonceCannotBecomeComplete() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 24U);
    source.addEapolKey(WifiEapolKeyMessage::Message2, 24U);
    FixtureFrame& message3 = source.addEapolKey(
        WifiEapolKeyMessage::Message3, 25U);
    message3.payload[49U] ^= 0x55U;
    source.addEapolKey(WifiEapolKeyMessage::Message4, 25U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(report.peers[0].messageMask == 0x03U);
    CHECK(report.peers[0].authenticatorNonceMismatch);
    CHECK(report.counters.sequenceRejected == 2U);
    CHECK(!report.peers[0].keyMaterialConsistent);
    CHECK(!report.peers[0].complete);
}

void testNoAuthenticationEvidenceStaysInconclusive() {
    FixtureSource source;
    source.addOrdinaryFrame(WifiFrameKind::Management);
    source.addOrdinaryFrame(WifiFrameKind::Data);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(report, WifiAuthenticationUncertaintyNoEvidence));
    CHECK(report.counters.framesIgnored == 2U);
    CHECK(report.counters.classifiedKeyFrames == 0U);
}

void testTruncatedEapolFailsClosed() {
    FixtureSource source;
    FixtureFrame& frame = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 30U);
    frame.originalLength = frame.capturedLength;
    frame.capturedLength = 70U;

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(report.counters.truncatedFrames == 1U);
    CHECK(hasUncertainty(report, WifiAuthenticationUncertaintyTruncated));
}

void testMalformedKeyAndPmkidElementFailClosed() {
    FixtureSource malformedLength;
    FixtureFrame& shortKey = malformedLength.addEapolKey(
        WifiEapolKeyMessage::Message1, 40U);
    shortKey.payload[34U] = 0U;
    shortKey.payload[35U] = 12U;
    WifiAuthenticationCaptureReport shortReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(malformedLength),
                                           &shortReport));
    CHECK(shortReport.counters.malformedFrames == 1U);
    CHECK(hasUncertainty(shortReport,
                         WifiAuthenticationUncertaintyMalformed));

    FixtureSource malformedKde;
    FixtureFrame& badKde = malformedKde.addEapolKey(
        WifiEapolKeyMessage::Message1, 41U, kAccessPoint, kStation, &kPmkid);
    badKde.payload[132U] = 21U;
    WifiAuthenticationCaptureReport kdeReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(malformedKde),
                                           &kdeReport));
    CHECK(kdeReport.outcome ==
          WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(kdeReport.counters.malformedFrames == 1U);
    CHECK(kdeReport.pmkidCount == 0U);
}

void testOnlySupportedRsnProfilesCanComplete() {
    constexpr std::array<std::uint8_t, 2> kEapolVersions{1U, 3U};
    for (std::uint8_t eapolVersion : kEapolVersions) {
        FixtureSource source;
        source.addEapolKey(WifiEapolKeyMessage::Message1, 70U,
                           kAccessPoint, kStation, nullptr, eapolVersion, 2U,
                           3U);
        source.addEapolKey(WifiEapolKeyMessage::Message2, 70U,
                           kAccessPoint, kStation, nullptr, eapolVersion, 2U,
                           3U);
        source.addEapolKey(WifiEapolKeyMessage::Message3, 71U,
                           kAccessPoint, kStation, nullptr, eapolVersion, 2U,
                           3U);
        source.addEapolKey(WifiEapolKeyMessage::Message4, 71U,
                           kAccessPoint, kStation, nullptr, eapolVersion, 2U,
                           3U);
        WifiAuthenticationCaptureReport report{};
        CHECK(analyzeWifiAuthenticationCapture(completeInput(source),
                                               &report));
        CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Complete);
        CHECK(report.peers[0].descriptorType == 2U);
        CHECK(report.peers[0].descriptorVersions[0] == 3U);
        CHECK(report.evidence[0].eapolVersion == eapolVersion);
        CHECK(report.evidence[0].profile ==
              WifiAuthenticationKeyProfile::RsnWpa2);
    }
}

void testUnsupportedDescriptorsAreRetainedAndNeverComplete() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 80U,
                       kAccessPoint, kStation, nullptr, 2U, 1U, 2U);
    source.addEapolKey(WifiEapolKeyMessage::Message1, 81U,
                       kAccessPoint, kStation, nullptr, 2U, 0xfeU, 2U);
    source.addEapolKey(WifiEapolKeyMessage::Message1, 82U,
                       kAccessPoint, kStation, nullptr, 2U, 2U, 0U);
    source.addEapolKey(WifiEapolKeyMessage::Message1, 83U,
                       kAccessPoint, kStation, nullptr, 2U, 2U, 1U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(report,
                         WifiAuthenticationUncertaintyUnsupported));
    CHECK(report.counters.unsupportedKeyFrames == 4U);
    CHECK(report.evidenceCount == 4U);
    CHECK(report.peerCount == 0U);
    CHECK(report.evidence[0].descriptorType == 1U);
    CHECK(report.evidence[1].descriptorType == 0xfeU);
    CHECK(report.evidence[2].descriptorVersion == 0U);
    CHECK(report.evidence[3].descriptorVersion == 1U);
    for (std::size_t index = 0; index < report.evidenceCount; ++index) {
        CHECK(report.evidence[index].sourceFrameIndex == index);
        CHECK(report.evidence[index].profile ==
              WifiAuthenticationKeyProfile::Unsupported);
    }
}

void testUnsupportedKeyInfoIsRetainedAndInconclusive() {
    FixtureSource source;
    FixtureFrame& smkMessage = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 84U);
    // Set the SMK-message flag in Key Information. This is an authentic RSN
    // descriptor layout, but not a supported four-way-handshake message.
    smkMessage.payload[37U] = static_cast<std::uint8_t>(
        smkMessage.payload[37U] | 0x20U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(report,
                         WifiAuthenticationUncertaintyUnsupported));
    CHECK(report.counters.unclassifiedKeyFrames == 1U);
    CHECK(report.counters.classifiedKeyFrames == 0U);
    CHECK(report.peerCount == 0U);
    CHECK(report.evidenceCount == 1U);
    CHECK(report.evidence[0].sourceFrameIndex == 0U);
    CHECK(report.evidence[0].profile ==
          WifiAuthenticationKeyProfile::Unsupported);
}

void testAttemptOrderDirectionNonceAndDescriptorConsistencyFailClosed() {
    FixtureSource zeroNonce;
    FixtureFrame& zeroM1 = zeroNonce.addEapolKey(
        WifiEapolKeyMessage::Message1, 90U);
    std::memset(zeroM1.payload.data() + 49U, 0, 32U);
    zeroNonce.addEapolKey(WifiEapolKeyMessage::Message2, 90U);
    FixtureFrame& zeroM3 = zeroNonce.addEapolKey(
        WifiEapolKeyMessage::Message3, 91U);
    std::memset(zeroM3.payload.data() + 49U, 0, 32U);
    zeroNonce.addEapolKey(WifiEapolKeyMessage::Message4, 91U);
    WifiAuthenticationCaptureReport zeroReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(zeroNonce),
                                           &zeroReport));
    CHECK(zeroReport.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(zeroReport.counters.sequenceRejected >= 1U);
    CHECK(!hasNonzero(zeroReport.peers[0].authenticatorNonce));

    FixtureSource outOfOrder;
    outOfOrder.addEapolKey(WifiEapolKeyMessage::Message4, 101U);
    outOfOrder.addEapolKey(WifiEapolKeyMessage::Message3, 101U);
    outOfOrder.addEapolKey(WifiEapolKeyMessage::Message2, 100U);
    outOfOrder.addEapolKey(WifiEapolKeyMessage::Message1, 100U);
    WifiAuthenticationCaptureReport orderReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(outOfOrder),
                                           &orderReport));
    CHECK(orderReport.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(orderReport.peers[0].messageMask == 0x01U);
    CHECK(orderReport.counters.sequenceRejected == 3U);

    FixtureSource nonMonotonic;
    FixtureFrame& timedM1 = nonMonotonic.addEapolKey(
        WifiEapolKeyMessage::Message1, 105U);
    FixtureFrame& timedM2 = nonMonotonic.addEapolKey(
        WifiEapolKeyMessage::Message2, 105U);
    timedM2.monotonicUs = timedM1.monotonicUs;
    nonMonotonic.addEapolKey(WifiEapolKeyMessage::Message3, 106U);
    nonMonotonic.addEapolKey(WifiEapolKeyMessage::Message4, 106U);
    WifiAuthenticationCaptureReport timeReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(nonMonotonic),
                                           &timeReport));
    CHECK(timeReport.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(timeReport.peers[0].messageMask == 0x01U);
    CHECK(timeReport.counters.sequenceRejected == 3U);

    FixtureSource wrongDirection;
    FixtureFrame& reversedM1 = wrongDirection.addEapolKey(
        WifiEapolKeyMessage::Message1, 110U);
    reversedM1.payload[1] = 0x01U;
    std::memcpy(reversedM1.payload.data() + 4U, kAccessPoint.data(),
                kAccessPoint.size());
    std::memcpy(reversedM1.payload.data() + 10U, kStation.data(),
                kStation.size());
    wrongDirection.addEapolKey(WifiEapolKeyMessage::Message2, 110U);
    wrongDirection.addEapolKey(WifiEapolKeyMessage::Message3, 111U);
    wrongDirection.addEapolKey(WifiEapolKeyMessage::Message4, 111U);
    WifiAuthenticationCaptureReport directionReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(wrongDirection),
                                           &directionReport));
    CHECK(directionReport.outcome ==
          WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(directionReport.counters.sequenceRejected == 4U);

    FixtureSource mixedVersion;
    mixedVersion.addEapolKey(WifiEapolKeyMessage::Message1, 120U);
    mixedVersion.addEapolKey(WifiEapolKeyMessage::Message2, 120U,
                             kAccessPoint, kStation, nullptr, 2U, 2U, 3U);
    mixedVersion.addEapolKey(WifiEapolKeyMessage::Message3, 121U,
                             kAccessPoint, kStation, nullptr, 2U, 2U, 3U);
    mixedVersion.addEapolKey(WifiEapolKeyMessage::Message4, 121U,
                             kAccessPoint, kStation, nullptr, 2U, 2U, 3U);
    WifiAuthenticationCaptureReport versionReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(mixedVersion),
                                           &versionReport));
    CHECK(versionReport.outcome ==
          WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(versionReport.peers[0].messageMask == 0x01U);

    FixtureSource equalReplay;
    equalReplay.addEapolKey(WifiEapolKeyMessage::Message1, 130U);
    equalReplay.addEapolKey(WifiEapolKeyMessage::Message2, 130U);
    equalReplay.addEapolKey(WifiEapolKeyMessage::Message3, 130U);
    equalReplay.addEapolKey(WifiEapolKeyMessage::Message4, 130U);
    WifiAuthenticationCaptureReport replayReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(equalReplay),
                                           &replayReport));
    CHECK(replayReport.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(replayReport.peers[0].messageMask == 0x03U);
}

void testCompletedAttemptSurvivesANewerIncompleteAttempt() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 135U);
    source.addEapolKey(WifiEapolKeyMessage::Message2, 135U);
    source.addEapolKey(WifiEapolKeyMessage::Message3, 136U);
    source.addEapolKey(WifiEapolKeyMessage::Message4, 136U);
    source.addEapolKey(WifiEapolKeyMessage::Message1, 137U);

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Complete);
    CHECK(report.peerCount == 2U);
    CHECK(report.peers[0].complete);
    CHECK(report.peers[0].messageMask == 0x0fU);
    CHECK(!report.peers[1].complete);
    CHECK(report.peers[1].messageMask == 0x01U);
}

void testExactLengthsQosAndFcs() {
    FixtureSource exactMismatch;
    FixtureFrame& extraKeyByte = exactMismatch.addEapolKey(
        WifiEapolKeyMessage::Message1, 140U);
    extraKeyByte.payload[35U] = static_cast<std::uint8_t>(
        extraKeyByte.payload[35U] + 1U);
    extraKeyByte.payload[extraKeyByte.capturedLength] = 0x5aU;
    ++extraKeyByte.capturedLength;
    extraKeyByte.originalLength = extraKeyByte.capturedLength;
    WifiAuthenticationCaptureReport keyLengthReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(exactMismatch),
                                           &keyLengthReport));
    CHECK(keyLengthReport.counters.malformedFrames == 1U);

    FixtureSource trailing;
    FixtureFrame& trailingByte = trailing.addEapolKey(
        WifiEapolKeyMessage::Message1, 141U);
    trailingByte.payload[trailingByte.capturedLength] = 0x6bU;
    ++trailingByte.capturedLength;
    trailingByte.originalLength = trailingByte.capturedLength;
    WifiAuthenticationCaptureReport trailingReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(trailing),
                                           &trailingReport));
    CHECK(trailingReport.counters.malformedFrames == 1U);

    FixtureSource qosFcs;
    FixtureFrame& m1 = qosFcs.addEapolKey(
        WifiEapolKeyMessage::Message1, 150U);
    qosFcs.addQosHeader(m1);
    FixtureFrame& m2 = qosFcs.addEapolKey(
        WifiEapolKeyMessage::Message2, 150U);
    qosFcs.appendFcs(m2);
    FixtureFrame& m3 = qosFcs.addEapolKey(
        WifiEapolKeyMessage::Message3, 151U);
    qosFcs.addQosHeader(m3);
    qosFcs.appendFcs(m3);
    qosFcs.addEapolKey(WifiEapolKeyMessage::Message4, 151U);
    WifiAuthenticationCaptureReport qosFcsReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(qosFcs),
                                           &qosFcsReport));
    CHECK(qosFcsReport.outcome == WifiAuthenticationCaptureOutcome::Complete);

    FixtureSource badFcs;
    FixtureFrame& tooShort = badFcs.addOrdinaryFrame(WifiFrameKind::Data);
    tooShort.capturedLength = 3U;
    tooShort.originalLength = 3U;
    tooShort.fcsIncluded = true;
    WifiAuthenticationCaptureReport badFcsReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(badFcs),
                                           &badFcsReport));
    CHECK(badFcsReport.counters.malformedFrames == 1U);
}

void testConflictingPmkidKdesFailClosed() {
    constexpr std::array<std::uint8_t, 16> kConflictingPmkid{
        0xf0U, 0xe1U, 0xd2U, 0xc3U, 0xb4U, 0xa5U, 0x96U, 0x87U,
        0x78U, 0x69U, 0x5aU, 0x4bU, 0x3cU, 0x2dU, 0x1eU, 0x0fU};
    FixtureSource source;
    FixtureFrame& frame = source.addEapolKey(
        WifiEapolKeyMessage::Message1, 160U, kAccessPoint, kStation, &kPmkid);
    std::size_t offset = frame.capturedLength;
    frame.payload[offset++] = 0xddU;
    frame.payload[offset++] = 20U;
    frame.payload[offset++] = 0x00U;
    frame.payload[offset++] = 0x0fU;
    frame.payload[offset++] = 0xacU;
    frame.payload[offset++] = 0x04U;
    std::memcpy(frame.payload.data() + offset, kConflictingPmkid.data(),
                kConflictingPmkid.size());
    offset += kConflictingPmkid.size();
    frame.payload[129U] = 0U;
    frame.payload[130U] = 44U;
    frame.payload[34U] = 0U;
    frame.payload[35U] = 139U;
    frame.capturedLength = static_cast<std::uint16_t>(offset);
    frame.originalLength = frame.capturedLength;

    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(report.counters.malformedFrames == 1U);
    CHECK(report.pmkidCount == 0U);
}

void testCaptureDropsAndUnreadableSourceFailClosed() {
    FixtureSource dropped;
    dropped.addEapolKey(WifiEapolKeyMessage::Message1, 50U);
    WifiAuthenticationCaptureInput droppedInput = completeInput(dropped);
    droppedInput.framesReported = 2U;
    droppedInput.framesDroppedCapacity = 1U;
    WifiAuthenticationCaptureReport droppedReport{};
    CHECK(analyzeWifiAuthenticationCapture(droppedInput, &droppedReport));
    CHECK(droppedReport.outcome ==
          WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(droppedReport,
                         WifiAuthenticationUncertaintyCaptureLoss));
    CHECK(droppedReport.counters.captureFramesDroppedCapacity == 1U);

    FixtureSource unreadable;
    unreadable.addEapolKey(WifiEapolKeyMessage::Message1, 51U);
    unreadable.mutableAt(0).readable = false;
    WifiAuthenticationCaptureReport unreadableReport{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(unreadable),
                                           &unreadableReport));
    CHECK(unreadableReport.outcome ==
          WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(unreadableReport.counters.sourceReadFailures == 1U);
    CHECK(hasUncertainty(unreadableReport,
                         WifiAuthenticationUncertaintySourceRead));
}

void testInspectionAndReportCapacityAreBounded() {
    FixtureSource source;
    for (std::size_t index = 0; index < FixtureSource::kCapacity; ++index) {
        source.addEapolKey(WifiEapolKeyMessage::Message1,
                           static_cast<std::uint64_t>(100U + index));
    }
    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(completeInput(source), &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(report.counters.framesRead ==
          WifiAuthenticationCaptureReport::kSourceFrameInspectionCapacity);
    CHECK(report.evidenceCount ==
          WifiAuthenticationCaptureReport::kEvidenceCapacity);
    CHECK(report.counters.evidenceDropped > 0U);
    CHECK(hasUncertainty(report, WifiAuthenticationUncertaintyCapacity));
}

void testInvalidAccountingAndNullInputFailClosed() {
    FixtureSource source;
    source.addEapolKey(WifiEapolKeyMessage::Message1, 60U);
    WifiAuthenticationCaptureInput invalid = completeInput(source);
    invalid.framesAccepted = 0U;
    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(invalid, &report));
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(report, WifiAuthenticationUncertaintyInvalidInput));

    WifiAuthenticationCaptureInput nullInput{};
    WifiAuthenticationCaptureReport nullReport{};
    CHECK(analyzeWifiAuthenticationCapture(nullInput, &nullReport));
    CHECK(nullReport.outcome ==
          WifiAuthenticationCaptureOutcome::Inconclusive);
    CHECK(hasUncertainty(nullReport,
                         WifiAuthenticationUncertaintyInvalidInput));
    CHECK(!analyzeWifiAuthenticationCapture(invalid, nullptr));
}

}  // namespace

int main() {
    testSharedDecoderPreservesNonQosQosFcsAndTargetIdentity();
    testSharedDecoderPreservesMalformedAndTruncatedBoundaries();
    testSharedDecoderPreservesDescriptorAndProfileClassification();
    testClassifiedMicBearingMessagesRequireNonzeroKeyMic();
    testIngressRetainsTargetNonQosQosAndFcs();
    testIngressIgnoresWrongBssidAndNonEapol();
    testIngressIgnoresCompleteNullDataButRetainsTruncation();
    testIngressRetainsProvableTargetFailuresFailClosed();
    testIngressRejectsUnidentifiableMalformedFrames();
    testCompleteHandshakeAndPmkidRetainExactEvidence();
    testIncompleteHandshakeIsExplicitAndPeersNeverMerge();
    testReplayMismatchCannotBecomeComplete();
    testMismatchedAuthenticatorNonceCannotBecomeComplete();
    testNoAuthenticationEvidenceStaysInconclusive();
    testTruncatedEapolFailsClosed();
    testMalformedKeyAndPmkidElementFailClosed();
    testOnlySupportedRsnProfilesCanComplete();
    testUnsupportedDescriptorsAreRetainedAndNeverComplete();
    testUnsupportedKeyInfoIsRetainedAndInconclusive();
    testAttemptOrderDirectionNonceAndDescriptorConsistencyFailClosed();
    testCompletedAttemptSurvivesANewerIncompleteAttempt();
    testExactLengthsQosAndFcs();
    testConflictingPmkidKdesFailClosed();
    testCaptureDropsAndUnreadableSourceFailClosed();
    testInspectionAndReportCapacityAreBounded();
    testInvalidAccountingAndNullInputFailClosed();
    std::puts("wifi authentication capture tests passed");
    return 0;
}
