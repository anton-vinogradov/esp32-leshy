#include <cassert>
#include <cstdio>
#include <vector>
#include "apps/wifi/WifiNetworkNameEvidence.h"

using namespace leshy1::apps::wifi;
using leshy1::domain::captures::WifiFrameView;
using leshy1::domain::captures::WifiFrameKind;
using Bytes = std::vector<std::uint8_t>;

const std::array<std::uint8_t, 6> ap{0x02, 1, 2, 3, 4, 5};
const std::array<std::uint8_t, 6> station{0x02, 6, 7, 8, 9, 10};

Bytes packet(std::uint8_t subtype, const Bytes& name) {
    const bool fromAp = subtype == 8 || subtype == 5;
    Bytes p(fromAp ? 36U : (subtype == 2 ? 34U : 28U), 0);
    p[0] = static_cast<std::uint8_t>(subtype << 4U);
    std::memcpy(p.data() + 4U, fromAp ? station.data() : ap.data(), 6U);
    std::memcpy(p.data() + 10U, fromAp ? ap.data() : station.data(), 6U);
    std::memcpy(p.data() + 16U, ap.data(), 6U);
    p.push_back(0);
    p.push_back(static_cast<std::uint8_t>(name.size()));
    p.insert(p.end(), name.begin(), name.end());
    return p;
}

WifiFrameView view(const Bytes& bytes) {
    return {100U, static_cast<std::uint16_t>(bytes.size()),
            static_cast<std::uint16_t>(bytes.size()), -20, 6,
            WifiFrameKind::Management, false, bytes.data()};
}

int main() {
    WifiNetworkNameEvidence name;
    const Bytes binary{0xd0, 0x9b, 0, 0xff};
    for (const auto subtype : {0U, 2U, 5U, 8U}) {
        auto bytes = packet(static_cast<std::uint8_t>(subtype), binary);
        assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Visible);
        assert(name.bssid == ap && name.length == binary.size());
        assert(std::memcmp(name.name.data(), binary.data(), binary.size()) == 0);
        assert(name.source == (subtype == 0U || subtype == 2U
            ? WifiNameSource::ClientConnection : WifiNameSource::AccessPoint));
        const auto complete = view(bytes);
        for (std::uint16_t n = 0; n < complete.capturedLength; ++n) {
            auto clipped = complete;
            clipped.capturedLength = n;
            assert(decodeWifiNetworkName(clipped, &name) == WifiNameDecode::Invalid);
            assert(name.length == 0U);
            clipped.originalLength = n;
            assert(decodeWifiNetworkName(clipped, &name) == WifiNameDecode::Invalid);
        }
        for (const auto bit : {1U, 2U, 4U, 64U, 128U}) {
            auto invalid = bytes;
            invalid[1] = static_cast<std::uint8_t>(bit);
            assert(decodeWifiNetworkName(view(invalid), &name) == WifiNameDecode::Invalid);
        }
        auto duplicate = bytes;
        duplicate.insert(duplicate.end(), {0, 1, 'X'});
        assert(decodeWifiNetworkName(view(duplicate), &name) == WifiNameDecode::Invalid);
        auto trailing = bytes;
        trailing.push_back(1); // No length: reject whole IE chain, even after a valid SSID.
        assert(decodeWifiNetworkName(view(trailing), &name) == WifiNameDecode::Invalid);
        bytes.insert(bytes.end(), {0xde, 0xad, 0xbe, 0xef});
        auto withFcs = view(bytes);
        withFcs.fcsIncluded = true;
        assert(decodeWifiNetworkName(withFcs, &name) == WifiNameDecode::Visible);
        assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Invalid);
    }
    for (const auto& hidden : {Bytes{}, Bytes(32, 0)}) {
        const auto bytes = packet(8, hidden);
        assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Hidden);
        assert(name.length == 0U);
    }
    auto bytes = packet(8, Bytes(32, 'a'));
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Visible);
    bytes = packet(8, Bytes(33, 'a'));
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Invalid);
    bytes = packet(4, {'N'});
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Ignored);
    bytes = packet(0, {'N'});
    bytes[4] ^= 2U; // Association destination must equal BSSID.
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Invalid);
    bytes = packet(8, {'N'});
    bytes[10] ^= 2U; // AP transmitter must equal BSSID.
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Invalid);

    WifiNetworkNameTracker tracker;
    assert(tracker.reset(ap, 6));
    bytes = packet(0, {'N'});
    assert(decodeWifiNetworkName(view(bytes), &name) == WifiNameDecode::Visible);
    assert(tracker.accept(name) && !tracker.apConfirmed());
    assert(!tracker.accept(name)); // Retransmissions do not repaint.
    auto wrong = name;
    wrong.bssid[5] ^= 2U;
    assert(!tracker.accept(wrong));
    wrong = name; wrong.channel = 1;
    assert(!tracker.accept(wrong));
    wrong = name; wrong.observedUs = 99;
    assert(!tracker.accept(wrong));
    name.source = WifiNameSource::AccessPoint;
    name.observedUs = 101;
    assert(tracker.accept(name) && tracker.apConfirmed());
    assert(tracker.primary().source == WifiNameSource::ClientConnection); // Preserve first evidence.
    name.name[0] = 'X'; name.observedUs = 102;
    assert(tracker.accept(name));
    assert(tracker.primary().name[0] == 'N' && tracker.conflict().name[0] == 'X');
    assert(!tracker.accept(name));
    name.name[0] = 'Y'; name.observedUs = 103;
    assert(tracker.accept(name) && tracker.additionalConflict());
    assert(tracker.conflict().name[0] == 'X');
    name.length = 0;
    assert(!tracker.accept(name) && tracker.primary().name[0] == 'N');
    assert(tracker.primaryLastSeenUs() == 101U); // Conflicting names do not freshen N.
    assert(tracker.apConfirmationUs() == 101U);
    assert(tracker.reset(tracker.primary().bssid, 6));
    assert(tracker.primary().length == 0U);
    assert(!tracker.reset({}, 6));
    assert(!tracker.accept(name) && tracker.primary().length == 0U);
    assert(!tracker.reset(ap, 14));
    std::puts("Wi-Fi name evidence: four frame types, exact bytes, address binding, conflicts, bounded state passed");
}
