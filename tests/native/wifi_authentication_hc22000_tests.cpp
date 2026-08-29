#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "apps/auth/WifiAuthenticationHc22000.h"
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

using namespace leshy1::apps::auth;
using namespace leshy1::domain::captures;
using namespace leshy1::services::auth;
using leshy1::storage::AuthenticationCaptureProvenance;
using leshy1::storage::AuthenticationCapturePurpose;

constexpr std::array<std::uint8_t, 6> kAccessPoint{
    0x64U, 0x66U, 0xb3U, 0x8eU, 0xc3U, 0xfcU};
constexpr std::array<std::uint8_t, 6> kStation{
    0x22U, 0x5eU, 0xdcU, 0x49U, 0xb7U, 0xaaU};
constexpr std::array<std::uint8_t, 32> kAuthenticatorNonce{
    0x10U, 0xe3U, 0xbeU, 0x3bU, 0x00U, 0x5aU, 0x62U, 0x9eU,
    0x89U, 0xdeU, 0x08U, 0x8dU, 0x6aU, 0x2fU, 0xdcU, 0x48U,
    0x9dU, 0xb8U, 0x3aU, 0xd4U, 0x76U, 0x4fU, 0x2dU, 0x18U,
    0x6bU, 0x9cU, 0xdeU, 0x15U, 0x44U, 0x6eU, 0x97U, 0x2eU};
constexpr std::array<std::uint8_t, 32> kStationNonce{
    0x48U, 0xceU, 0x2cU, 0xcbU, 0xa9U, 0xc1U, 0xfdU, 0xa1U,
    0x30U, 0xffU, 0x2fU, 0xbbU, 0xfbU, 0x4fU, 0xd3U, 0xb0U,
    0x63U, 0xd1U, 0xa9U, 0x39U, 0x20U, 0xb0U, 0xf7U, 0xdfU,
    0x54U, 0xa5U, 0xcbU, 0xf7U, 0x87U, 0xb1U, 0x61U, 0x71U};
constexpr std::array<std::uint8_t, 16> kMic{
    0x02U, 0x40U, 0x22U, 0x79U, 0x52U, 0x24U, 0xbfU, 0xfcU,
    0xa5U, 0x45U, 0x27U, 0x6cU, 0x37U, 0x62U, 0x68U, 0x6fU};
constexpr std::array<std::uint8_t, 16> kPmkid{
    0x4dU, 0x4fU, 0xe7U, 0xaaU, 0xc3U, 0xa2U, 0xceU, 0xcaU,
    0xb1U, 0x95U, 0x32U, 0x1cU, 0xebU, 0x99U, 0xa7U, 0xd0U};

struct FixtureFrame final {
    std::array<std::uint8_t, 256> bytes{};
    std::uint16_t length = 0U;
    std::uint64_t monotonicUs = 0U;
    std::int16_t rssiDbm = -42;
    bool readable = true;
};

class FixtureSource final : public WifiFrameSource {
public:
    FixtureFrame& add(bool fromAccessPoint,
                      const std::uint8_t* eapol,
                      std::size_t eapolLength,
                      std::uint64_t monotonicUs) {
        CHECK(count_ < frames_.size());
        CHECK(eapol != nullptr);
        CHECK(eapolLength + 32U <= frames_[count_].bytes.size());
        FixtureFrame& frame = frames_[count_++];
        frame = {};
        frame.monotonicUs = monotonicUs;
        frame.rssiDbm = -42;
        frame.bytes[0] = 0x08U;
        frame.bytes[1] = fromAccessPoint ? 0x02U : 0x01U;
        if (fromAccessPoint) {
            std::memcpy(frame.bytes.data() + 4U, kStation.data(),
                        kStation.size());
            std::memcpy(frame.bytes.data() + 10U, kAccessPoint.data(),
                        kAccessPoint.size());
        } else {
            std::memcpy(frame.bytes.data() + 4U, kAccessPoint.data(),
                        kAccessPoint.size());
            std::memcpy(frame.bytes.data() + 10U, kStation.data(),
                        kStation.size());
        }
        std::memcpy(frame.bytes.data() + 16U, kAccessPoint.data(),
                    kAccessPoint.size());
        constexpr std::array<std::uint8_t, 8> kLlc{
            0xaaU, 0xaaU, 0x03U, 0x00U, 0x00U, 0x00U, 0x88U, 0x8eU};
        std::memcpy(frame.bytes.data() + 24U, kLlc.data(), kLlc.size());
        std::memcpy(frame.bytes.data() + 32U, eapol, eapolLength);
        frame.length = static_cast<std::uint16_t>(32U + eapolLength);
        return frame;
    }

    std::size_t frameCount() const override { return count_; }
    std::uint16_t snapLength() const override { return 256U; }
    bool frameView(std::size_t index, WifiFrameView* output) const override {
        if (output == nullptr || index >= count_ || !frames_[index].readable) {
            return false;
        }
        const FixtureFrame& frame = frames_[index];
        output->monotonicUs = frame.monotonicUs;
        output->capturedLength = frame.length;
        output->originalLength = frame.length;
        output->rssiDbm = frame.rssiDbm;
        output->channel = 6U;
        output->kind = WifiFrameKind::Data;
        output->fcsIncluded = false;
        output->payload = frame.bytes.data();
        return true;
    }

    FixtureFrame& at(std::size_t index) {
        CHECK(index < count_);
        return frames_[index];
    }

private:
    std::array<FixtureFrame, 4> frames_{};
    std::size_t count_ = 0U;
};

std::array<std::uint8_t, 99> message1() {
    std::array<std::uint8_t, 99> eapol{};
    eapol[0] = 1U;
    eapol[1] = 3U;
    eapol[2] = 0U;
    eapol[3] = 95U;
    eapol[4] = 2U;
    eapol[5] = 0U;
    eapol[6] = 0x8aU;
    eapol[8] = 16U;
    eapol[16] = 1U;
    std::memcpy(eapol.data() + 17U, kAuthenticatorNonce.data(),
                kAuthenticatorNonce.size());
    return eapol;
}

std::array<std::uint8_t, 121> message2() {
    std::array<std::uint8_t, 121> eapol{};
    eapol[0] = 1U;
    eapol[1] = 3U;
    eapol[2] = 0U;
    eapol[3] = 117U;
    eapol[4] = 2U;
    eapol[5] = 0x01U;
    eapol[6] = 0x0aU;
    eapol[16] = 1U;
    std::memcpy(eapol.data() + 17U, kStationNonce.data(),
                kStationNonce.size());
    std::memcpy(eapol.data() + 81U, kMic.data(), kMic.size());
    eapol[97] = 0U;
    eapol[98] = 22U;
    constexpr std::array<std::uint8_t, 22> kRsnIe{
        0x30U, 0x14U, 0x01U, 0x00U, 0x00U, 0x0fU, 0xacU, 0x04U,
        0x01U, 0x00U, 0x00U, 0x0fU, 0xacU, 0x04U, 0x01U, 0x00U,
        0x00U, 0x0fU, 0xacU, 0x02U, 0x80U, 0x00U};
    std::memcpy(eapol.data() + 99U, kRsnIe.data(), kRsnIe.size());
    return eapol;
}

std::string hexString(const std::uint8_t* data, std::size_t size) {
    CHECK(data != nullptr || size == 0U);
    constexpr char kHex[] = "0123456789abcdef";
    std::string result;
    result.reserve(size * 2U);
    for (std::size_t index = 0U; index < size; ++index) {
        result.push_back(kHex[data[index] >> 4U]);
        result.push_back(kHex[data[index] & 0x0fU]);
    }
    return result;
}

std::array<std::uint8_t, 121> pmkidMessage1() {
    std::array<std::uint8_t, 121> eapol{};
    const auto basic = message1();
    std::copy(basic.begin(), basic.end(), eapol.begin());
    eapol[2] = 0U;
    eapol[3] = 117U;
    eapol[97] = 0U;
    eapol[98] = 22U;
    eapol[99] = 0xddU;
    eapol[100] = 20U;
    eapol[101] = 0x00U;
    eapol[102] = 0x0fU;
    eapol[103] = 0xacU;
    eapol[104] = 0x04U;
    std::memcpy(eapol.data() + 105U, kPmkid.data(), kPmkid.size());
    return eapol;
}

AuthenticationCaptureProvenance provenance(std::uint32_t frames) {
    AuthenticationCaptureProvenance value{};
    value.purpose = AuthenticationCapturePurpose::Authentication;
    value.targetBssid = kAccessPoint;
    constexpr char kSsid[] = "TP-LINK_HASHCAT_TEST";
    value.ssidLength = static_cast<std::uint8_t>(sizeof(kSsid) - 1U);
    value.ssidKnown = true;
    std::memcpy(value.ssid.data(), kSsid, sizeof(kSsid) - 1U);
    value.framesReported = frames;
    value.framesAccepted = frames;
    return value;
}

WifiAuthenticationCaptureReport analyze(const FixtureSource& source) {
    WifiAuthenticationCaptureInput input{};
    input.source = &source;
    input.captureComplete = true;
    input.framesReported = static_cast<std::uint32_t>(source.frameCount());
    input.framesAccepted = input.framesReported;
    WifiAuthenticationCaptureReport report{};
    CHECK(analyzeWifiAuthenticationCapture(input, &report));
    return report;
}

bool appendBytes(const std::uint8_t* data, std::size_t size, void* context) {
    if (data == nullptr || context == nullptr) return false;
    static_cast<std::string*>(context)->append(
        reinterpret_cast<const char*>(data), size);
    return true;
}

struct CountingSink final {
    std::size_t calls = 0U;
    std::size_t failAt = static_cast<std::size_t>(-1);
};

bool countCalls(const std::uint8_t*, std::size_t, void* context) {
    if (context == nullptr) return false;
    auto* state = static_cast<CountingSink*>(context);
    const bool accept = state->calls != state->failAt;
    ++state->calls;
    return accept;
}

void testCanonicalStrictM1M2RecordMatchesHashcatWireFormat() {
    FixtureSource source;
    const auto m1 = message1();
    const auto m2 = message2();
    source.add(true, m1.data(), m1.size(), 1000000ULL);
    source.add(false, m2.data(), m2.size(), 1100000ULL);
    const WifiAuthenticationCaptureReport report = analyze(source);
    CHECK(report.outcome == WifiAuthenticationCaptureOutcome::Incomplete);
    CHECK(report.peerCount == 1U);
    CHECK(report.peers[0].messageMask == 0x03U);

    std::string output;
    const AuthenticationCaptureProvenance facts = provenance(2U);
    const auto result = writeWifiAuthenticationHc22000(
        report, facts, source, appendBytes, &output);
    auto zeroMic = m2;
    std::fill(zeroMic.begin() + 81U, zeroMic.begin() + 97U, 0U);
    const std::string expected =
        std::string(
            "WPA*02*024022795224bffca545276c3762686f*6466b38ec3fc*"
            "225edc49b7aa*54502d4c494e4b5f484153484341545f54455354*"
            "10e3be3b005a629e89de088d6a2fdc489db83ad4764f2d186b9cde15446e972e*") +
        hexString(zeroMic.data(), zeroMic.size()) + "*00\n";
    CHECK(result.valid());
    CHECK(result.recordsWritten == 1U);
    CHECK(result.pmkidRecordsWritten == 0U);
    CHECK(result.eapolRecordsWritten == 1U);
    CHECK(result.bytesWritten == output.size());
    CHECK(output == expected);
    CHECK(wifiAuthenticationHc22000Size(report, facts, source) ==
          output.size());
}

void testCanonicalPmkidRecordAndBinarySafeSsid() {
    FixtureSource source;
    const auto m1 = pmkidMessage1();
    source.add(true, m1.data(), m1.size(), 2000000ULL);
    const WifiAuthenticationCaptureReport report = analyze(source);
    CHECK(report.pmkidCount == 1U);
    AuthenticationCaptureProvenance facts = provenance(1U);
    facts.ssidLength = 4U;
    facts.ssid[0] = 'A';
    facts.ssid[1] = 0U;
    facts.ssid[2] = 'P';
    facts.ssid[3] = '1';

    std::string output;
    const auto result = writeWifiAuthenticationHc22000(
        report, facts, source, appendBytes, &output);
    CHECK(result.valid());
    CHECK(result.pmkidRecordsWritten == 1U);
    CHECK(result.eapolRecordsWritten == 0U);
    CHECK(output ==
          "WPA*01*4d4fe7aac3a2cecab195321ceb99a7d0*6466b38ec3fc*"
          "225edc49b7aa*41005031***\n");
}

void testEvidenceMismatchFailsBeforeFirstSinkCall() {
    FixtureSource source;
    const auto m1 = message1();
    const auto m2 = message2();
    source.add(true, m1.data(), m1.size(), 3000000ULL);
    source.add(false, m2.data(), m2.size(), 3100000ULL);
    const WifiAuthenticationCaptureReport report = analyze(source);
    source.at(1U).bytes[32U + 17U] ^= 0x01U;
    CountingSink sink{};
    const auto result = writeWifiAuthenticationHc22000(
        report, provenance(2U), source, countCalls, &sink);
    CHECK(!result.valid());
    CHECK(result.status ==
          WifiAuthenticationHc22000Status::EvidenceMismatch);
    CHECK(result.bytesWritten == 0U);
    CHECK(result.recordsWritten == 0U);
    CHECK(sink.calls == 0U);
}

void testPolicyAndSinkFailuresAreExplicit() {
    FixtureSource source;
    const auto m1 = message1();
    const auto m2 = message2();
    source.add(true, m1.data(), m1.size(), 4000000ULL);
    source.add(false, m2.data(), m2.size(), 4100000ULL);
    const WifiAuthenticationCaptureReport report = analyze(source);

    AuthenticationCaptureProvenance wrong = provenance(2U);
    wrong.ssidKnown = false;
    CountingSink untouched{};
    auto result = writeWifiAuthenticationHc22000(
        report, wrong, source, countCalls, &untouched);
    CHECK(result.status == WifiAuthenticationHc22000Status::PolicyRejected);
    CHECK(untouched.calls == 0U);

    CountingSink failing{};
    failing.failAt = 2U;
    result = writeWifiAuthenticationHc22000(
        report, provenance(2U), source, countCalls, &failing);
    CHECK(result.status == WifiAuthenticationHc22000Status::OutputFailed);
    CHECK(!result.valid());
    CHECK(result.recordsWritten == 0U);
    CHECK(failing.calls == 3U);
    CHECK(std::strcmp(wifiAuthenticationHc22000StatusName(result.status),
                      "output_failed") == 0);
}

}  // namespace

int main() {
    testCanonicalStrictM1M2RecordMatchesHashcatWireFormat();
    testCanonicalPmkidRecordAndBinarySafeSsid();
    testEvidenceMismatchFailsBeforeFirstSinkCall();
    testPolicyAndSinkFailuresAreExplicit();
    std::puts("Wi-Fi authentication hc22000 tests passed");
    return 0;
}
