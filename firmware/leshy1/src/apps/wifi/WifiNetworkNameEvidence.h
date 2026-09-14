#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include "domain/captures/WifiFrame.h"

namespace leshy1::apps::wifi {

enum class WifiNameSource : std::uint8_t { None, AccessPoint, ClientConnection };
enum class WifiNameDecode : std::uint8_t { Ignored, Invalid, Hidden, Visible };

// Name provenance is separate from AP radio measurements. In particular, a
// client's RSSI cannot become the selected AP's RSSI, age or capabilities.
struct WifiNetworkNameEvidence final {
    std::array<std::uint8_t, 6> bssid{};
    std::array<std::uint8_t, 32> name{};
    std::uint64_t observedUs = 0;
    std::uint8_t length = 0;
    std::uint8_t channel = 0;
    WifiNameSource source = WifiNameSource::None;
};

inline bool wifiNameUnicast(const std::uint8_t* address) {
    if ((address[0] & 1U) != 0U) return false;
    std::uint8_t bits = 0;
    for (std::size_t i = 0; i < 6U; ++i) bits |= address[i];
    return bits != 0U;
}

// Complete immutable management frames only. FCS presence is explicit metadata;
// do not guess it from trailing bytes. The receiver/validated import owns FCS
// checking. A decoded name is an observation, never authenticated AP identity.
inline WifiNameDecode decodeWifiNetworkName(
    const domain::captures::WifiFrameView& frame,
    WifiNetworkNameEvidence* output) {
    using Result = WifiNameDecode;
    if (output == nullptr) return Result::Invalid;
    *output = {};
    if (frame.kind != domain::captures::WifiFrameKind::Management) return Result::Ignored;
    if (frame.payload == nullptr || frame.capturedLength != frame.originalLength ||
        frame.capturedLength < 24U || frame.capturedLength > 4096U ||
        frame.monotonicUs == 0U || frame.channel == 0U || frame.channel > 13U)
        return Result::Invalid;
    const auto* bytes = frame.payload;
    // Version/type must be management; no DS, fragment, protected or HT-control
    // variants. Retry is allowed: it does not change address/name semantics.
    if ((bytes[0] & 0x0fU) != 0U || (bytes[1] & 0xc7U) != 0U ||
        (bytes[22] & 0x0fU) != 0U) return Result::Invalid;
    const auto subtype = static_cast<std::uint8_t>(bytes[0] >> 4U);
    const bool ap = subtype == 8U || subtype == 5U;
    if (!ap && subtype != 0U && subtype != 2U) return Result::Ignored;
    const std::size_t end = frame.capturedLength - (frame.fcsIncluded ? 4U : 0U);
    const std::size_t elements = ap ? 36U : (subtype == 0U ? 28U : 34U);
    if (end < elements) return Result::Invalid;
    const auto* bssid = bytes + 16U;
    const auto* transmitter = bytes + 10U;
    if (!wifiNameUnicast(bssid) || !wifiNameUnicast(transmitter)) return Result::Invalid;
    if (ap) {
        if (std::memcmp(transmitter, bssid, 6U) != 0) return Result::Invalid;
    } else {
        // Only a connection explicitly addressed to this AP supplies its name.
        // A probe request searching for a name is deliberately never accepted.
        if (std::memcmp(bytes + 4U, bssid, 6U) != 0 ||
            std::memcmp(transmitter, bssid, 6U) == 0) return Result::Invalid;
    }
    const std::uint8_t* name = nullptr;
    std::uint8_t length = 0;
    for (std::size_t offset = elements; offset < end;) {
        if (end - offset < 2U) return Result::Invalid;
        const std::uint8_t id = bytes[offset++];
        const std::uint8_t size = bytes[offset++];
        if (size > end - offset) return Result::Invalid;
        if (id == 0U) {
            if (name != nullptr || size > 32U) return Result::Invalid;
            name = bytes + offset;
            length = size;
        }
        offset += size;
    }
    if (name == nullptr) return Result::Invalid;
    std::uint8_t nonzero = 0;
    for (std::uint8_t i = 0; i < length; ++i) nonzero |= name[i];
    if (nonzero == 0U) return Result::Hidden;
    std::memcpy(output->bssid.data(), bssid, 6U);
    std::memcpy(output->name.data(), name, length);
    output->length = length;
    output->channel = frame.channel;
    output->observedUs = frame.monotonicUs;
    output->source = ap ? WifiNameSource::AccessPoint : WifiNameSource::ClientConnection;
    return Result::Visible;
}

// Fixed selected-target state for a bounded listen window. The live
// adapter owns the deadline, receiver and schedule restore; this model does no
// I/O, scan, TX, allocation or catalog/RSSI mutation. First conflict is retained
// rather than silently replacing the displayed name. Reset starts a new window.
class WifiNetworkNameTracker final {
  public:
    bool reset(const std::array<std::uint8_t, 6>& bssid, std::uint8_t channel) {
        const auto target = bssid; // Permit resetting from a field of this tracker.
        *this = {};
        if (!wifiNameUnicast(target.data()) || channel == 0U || channel > 13U) return false;
        target_ = target;
        channel_ = channel;
        return true;
    }
    const WifiNetworkNameEvidence& primary() const { return primary_; }
    const WifiNetworkNameEvidence& conflict() const { return conflict_; }
    const WifiNetworkNameEvidence& firstClient() const { return firstClient_; }
    bool clientMatchesPrimary() const {
        return firstClient_.length != 0U && sameName(primary_, firstClient_);
    }
    bool apConfirmed() const { return confirmed_; }
    bool additionalConflict() const { return additionalConflict_; }
    std::uint64_t primaryLastSeenUs() const { return primaryLastSeenUs_; }
    std::uint64_t apConfirmationUs() const { return apConfirmationUs_; }
    // True means a presentation change; repeats update only the separate age.
    bool accept(const WifiNetworkNameEvidence& evidence) {
        if (channel_ == 0U || evidence.channel != channel_ || evidence.bssid != target_ ||
            evidence.length == 0U || evidence.length > evidence.name.size() ||
            evidence.observedUs == 0U || evidence.observedUs < lastEvidenceUs_ ||
            (evidence.source != WifiNameSource::AccessPoint &&
             evidence.source != WifiNameSource::ClientConnection)) return false;
        std::uint8_t nonzero = 0;
        for (std::uint8_t i = 0; i < evidence.length; ++i) nonzero |= evidence.name[i];
        if (nonzero == 0U) return false;
        lastEvidenceUs_ = evidence.observedUs;
        // A directed probe response may reveal the name before association.
        // Preserve that first source; independently retain the client frame.
        const bool firstClient = firstClient_.length == 0U &&
            evidence.source == WifiNameSource::ClientConnection;
        if (firstClient) firstClient_ = evidence;
        if (primary_.length == 0U) {
            primary_ = evidence;
            primaryLastSeenUs_ = evidence.observedUs;
            confirmed_ = evidence.source == WifiNameSource::AccessPoint;
            if (confirmed_) apConfirmationUs_ = evidence.observedUs;
            return true;
        }
        if (sameName(primary_, evidence)) {
            primaryLastSeenUs_ = evidence.observedUs;
            if (!confirmed_ && evidence.source == WifiNameSource::AccessPoint) {
                confirmed_ = true;
                apConfirmationUs_ = evidence.observedUs;
                return true;
            }
            return firstClient;
        }
        if (conflict_.length == 0U) { conflict_ = evidence; return true; }
        if (!sameName(conflict_, evidence) && !additionalConflict_) {
            additionalConflict_ = true;
            return true;
        }
        return firstClient;
    }
  private:
    static bool sameName(const WifiNetworkNameEvidence& a, const WifiNetworkNameEvidence& b) {
        return a.length == b.length && std::memcmp(a.name.data(), b.name.data(), a.length) == 0;
    }
    WifiNetworkNameEvidence primary_{}, conflict_{}, firstClient_{};
    std::array<std::uint8_t, 6> target_{};
    std::uint64_t lastEvidenceUs_ = 0;
    std::uint64_t primaryLastSeenUs_ = 0;
    std::uint64_t apConfirmationUs_ = 0;
    std::uint8_t channel_ = 0;
    bool confirmed_ = false;
    bool additionalConflict_ = false;
};

static_assert(sizeof(WifiNetworkNameTracker) <= 224U, "selected name evidence must stay bounded");
}  // namespace leshy1::apps::wifi
