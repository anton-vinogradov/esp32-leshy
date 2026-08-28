#include "AirspaceGuard.h"

#include <cstring>

namespace leshy1::services::guard {

namespace {

using domain::captures::WifiFrameKind;
using domain::captures::WifiFrameView;
using domain::observations::BleAdvertisementFacts;
using domain::observations::Observation;
using domain::observations::RadioKind;

enum class DisconnectSubtype : std::uint8_t {
    Deauthentication,
    Disassociation,
};

enum class DisconnectDecode : std::uint8_t {
    NotDisconnect,
    Disconnect,
    Malformed,
};

enum class IdentityDecode : std::uint8_t {
    NotAdvertisement,
    IgnoredAdvertisement,
    Advertisement,
    Malformed,
};

struct DisconnectEvent final {
    std::size_t frameIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = 0;
    std::uint8_t channel = 0;
    DisconnectSubtype subtype = DisconnectSubtype::Deauthentication;
    std::array<std::uint8_t, 6> transmitter{};
};

struct IdentityAdvertisement final {
    std::size_t frameIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = 0;
    std::uint8_t channel = 0;
    std::array<std::uint8_t, 6> transmitter{};
    std::array<std::uint8_t, AirspaceFinding::kNetworkNameCapacity>
        networkName{};
    std::uint8_t networkNameLength = 0;
    AirspaceWifiSecurity security = AirspaceWifiSecurity::Unknown;
};

enum class BleObservationDecode : std::uint8_t {
    Advertisement,
    TrackerAdvertisement,
    Malformed,
};

struct BleTrackerEvent final {
    std::size_t observationIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = 0;
    std::array<std::uint8_t, 6> identity{};
    AirspaceBleTrackerProtocol protocol = AirspaceBleTrackerProtocol::None;
    std::uint8_t addressType = 0xffU;
};

bool sameTransmitter(const std::array<std::uint8_t, 6>& left,
                     const std::array<std::uint8_t, 6>& right) {
    return std::memcmp(left.data(), right.data(), left.size()) == 0;
}

bool sameNetworkName(
    const std::array<std::uint8_t,
                     AirspaceFinding::kNetworkNameCapacity>& left,
    std::uint8_t leftLength,
    const std::array<std::uint8_t,
                     AirspaceFinding::kNetworkNameCapacity>& right,
    std::uint8_t rightLength) {
    return leftLength == rightLength && leftLength != 0U &&
        std::memcmp(left.data(), right.data(), leftLength) == 0;
}

bool validTransmitter(const std::uint8_t* address) {
    if (address == nullptr || (address[0] & 0x01U) != 0U) return false;
    bool any = false;
    bool allOnes = true;
    for (std::size_t index = 0; index < 6U; ++index) {
        any = any || address[index] != 0U;
        allOnes = allOnes && address[index] == 0xffU;
    }
    return any && !allOnes;
}

bool validBleIdentity(const Observation& observation) {
    if (observation.identityLength != observation.identity.size()) {
        return false;
    }
    bool any = false;
    bool allOnes = true;
    for (const std::uint8_t byte : observation.identity) {
        any = any || byte != 0U;
        allOnes = allOnes && byte == 0xffU;
    }
    return any && !allOnes;
}

BleObservationDecode decodeBleObservation(
    const Observation& observation, BleTrackerEvent* output,
    std::size_t observationIndex) {
    if (output == nullptr || observation.radio != RadioKind::Ble ||
        observation.monotonicUs == 0U || observation.rssiDbm < -127 ||
        observation.rssiDbm > 20 || !validBleIdentity(observation) ||
        !observation.bleAdvertisement.present ||
        observation.bleAdvertisement.addressType > 3U) {
        return BleObservationDecode::Malformed;
    }

    const BleAdvertisementFacts& facts = observation.bleAdvertisement;
    const bool findMy = facts.companyKnown && facts.companyId == 0x004cU &&
        facts.appleContinuityType == 0x12U;
    const bool smartTag =
        (facts.knownServiceMask & BleAdvertisementFacts::kServiceSmartTag) !=
        0U;
    const bool tile =
        (facts.knownServiceMask & BleAdvertisementFacts::kServiceTile) != 0U;
    const std::uint8_t markerCount = static_cast<std::uint8_t>(findMy) +
        static_cast<std::uint8_t>(smartTag) +
        static_cast<std::uint8_t>(tile);
    if (markerCount == 0U) return BleObservationDecode::Advertisement;
    if (markerCount != 1U || facts.payloadLength == 0U) {
        return BleObservationDecode::Malformed;
    }

    *output = {};
    output->observationIndex = observationIndex;
    output->monotonicUs = observation.monotonicUs;
    output->rssiDbm = observation.rssiDbm;
    output->identity = observation.identity;
    output->addressType = facts.addressType;
    output->protocol = findMy
        ? AirspaceBleTrackerProtocol::FindMy
        : smartTag ? AirspaceBleTrackerProtocol::SmartTag
                   : AirspaceBleTrackerProtocol::Tile;
    return BleObservationDecode::TrackerAdvertisement;
}

bool sameBleTracker(const BleTrackerEvent& left,
                    const BleTrackerEvent& right) {
    return left.protocol == right.protocol &&
        left.addressType == right.addressType &&
        left.identity == right.identity;
}

DisconnectDecode decodeDisconnect(const WifiFrameView& frame,
                                  DisconnectEvent* output,
                                  std::size_t frameIndex) {
    if (output == nullptr || frame.payload == nullptr ||
        frame.capturedLength < 2U || frame.monotonicUs == 0U ||
        frame.channel == 0U || frame.channel > 14U) {
        return DisconnectDecode::Malformed;
    }
    if (frame.kind != WifiFrameKind::Management) {
        return DisconnectDecode::NotDisconnect;
    }
    const std::uint16_t frameControl = static_cast<std::uint16_t>(
        frame.payload[0] | (static_cast<std::uint16_t>(frame.payload[1]) << 8U));
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    if (type != 0U || (subtype != 10U && subtype != 12U)) {
        return DisconnectDecode::NotDisconnect;
    }
    if (frame.capturedLength < 24U ||
        !validTransmitter(frame.payload + 10U)) {
        return DisconnectDecode::Malformed;
    }

    *output = {};
    output->frameIndex = frameIndex;
    output->monotonicUs = frame.monotonicUs;
    output->rssiDbm = frame.rssiDbm;
    output->channel = frame.channel;
    output->subtype = subtype == 12U
        ? DisconnectSubtype::Deauthentication
        : DisconnectSubtype::Disassociation;
    std::memcpy(output->transmitter.data(), frame.payload + 10U,
                output->transmitter.size());
    return DisconnectDecode::Disconnect;
}

IdentityDecode decodeIdentityAdvertisement(
    const WifiFrameView& frame, IdentityAdvertisement* output,
    std::size_t frameIndex) {
    if (output == nullptr || frame.payload == nullptr ||
        frame.capturedLength < 2U || frame.monotonicUs == 0U ||
        frame.channel == 0U || frame.channel > 14U) {
        return IdentityDecode::Malformed;
    }
    if (frame.kind != WifiFrameKind::Management) {
        return IdentityDecode::NotAdvertisement;
    }
    const std::uint16_t frameControl = static_cast<std::uint16_t>(
        frame.payload[0] | (static_cast<std::uint16_t>(frame.payload[1]) << 8U));
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    if (type != 0U || (subtype != 5U && subtype != 8U)) {
        return IdentityDecode::NotAdvertisement;
    }
    std::size_t payloadLength = frame.capturedLength;
    if (frame.fcsIncluded) {
        if (payloadLength < 4U) return IdentityDecode::Malformed;
        payloadLength -= 4U;
    }
    if (payloadLength < 36U ||
        !validTransmitter(frame.payload + 10U) ||
        std::memcmp(frame.payload + 10U, frame.payload + 16U, 6U) != 0) {
        return IdentityDecode::Malformed;
    }

    IdentityAdvertisement decoded{};
    decoded.frameIndex = frameIndex;
    decoded.monotonicUs = frame.monotonicUs;
    decoded.rssiDbm = frame.rssiDbm;
    decoded.channel = frame.channel;
    std::memcpy(decoded.transmitter.data(), frame.payload + 10U,
                decoded.transmitter.size());

    const std::uint16_t capability = static_cast<std::uint16_t>(
        frame.payload[34] |
        (static_cast<std::uint16_t>(frame.payload[35]) << 8U));
    const bool privacy = (capability & 0x0010U) != 0U;
    bool ssidSeen = false;
    bool rsnSeen = false;
    bool wpaSeen = false;
    std::size_t offset = 36U;
    while (offset < payloadLength) {
        if (payloadLength - offset < 2U) {
            return IdentityDecode::Malformed;
        }
        const std::uint8_t id = frame.payload[offset++];
        const std::uint8_t length = frame.payload[offset++];
        if (payloadLength - offset < length) {
            return IdentityDecode::Malformed;
        }
        const std::uint8_t* value = frame.payload + offset;
        if (id == 0U) {
            if (ssidSeen || length > decoded.networkName.size()) {
                return IdentityDecode::Malformed;
            }
            ssidSeen = true;
            decoded.networkNameLength = length;
            if (length != 0U) {
                std::memcpy(decoded.networkName.data(), value, length);
            }
        } else if (id == 48U) {
            if (length < 2U) return IdentityDecode::Malformed;
            rsnSeen = true;
        } else if (id == 221U && length >= 4U && value[0] == 0x00U &&
                   value[1] == 0x50U && value[2] == 0xf2U &&
                   value[3] == 0x01U) {
            wpaSeen = true;
        }
        offset += length;
    }
    bool named = false;
    for (std::size_t index = 0U; index < decoded.networkNameLength; ++index) {
        named = named || decoded.networkName[index] != 0U;
    }
    if (!ssidSeen || !named) {
        return IdentityDecode::IgnoredAdvertisement;
    }
    decoded.security = rsnSeen
        ? AirspaceWifiSecurity::Rsn
        : wpaSeen
            ? AirspaceWifiSecurity::Wpa
            : privacy
                ? AirspaceWifiSecurity::LegacyPrivacy
                : AirspaceWifiSecurity::Open;
    *output = decoded;
    return IdentityDecode::Advertisement;
}

void retainEvidence(AirspaceFinding& finding,
                    const IdentityAdvertisement& event) {
    if (finding.evidenceCount >= finding.evidence.size()) return;
    AirspaceEvidenceRef& evidence =
        finding.evidence[finding.evidenceCount++];
    evidence.frameIndex = event.frameIndex;
    evidence.monotonicUs = event.monotonicUs;
    evidence.channel = event.channel;
    evidence.rssiDbm = event.rssiDbm;
}

AirspaceConfidence confidenceFor(std::size_t observed,
                                 std::size_t threshold) {
    return observed >= threshold * 2U
        ? AirspaceConfidence::High : AirspaceConfidence::Medium;
}

}  // namespace

BleTrackerIngressStatus bleTrackerIngressStatus(
    const Observation& observation) {
    BleTrackerEvent ignored{};
    switch (decodeBleObservation(observation, &ignored, 0U)) {
        case BleObservationDecode::Advertisement:
            return BleTrackerIngressStatus::CoverageAdvertisement;
        case BleObservationDecode::TrackerAdvertisement:
            return BleTrackerIngressStatus::TrackerAdvertisement;
        case BleObservationDecode::Malformed:
            return BleTrackerIngressStatus::MalformedAdvertisement;
    }
    return BleTrackerIngressStatus::MalformedAdvertisement;
}

void AirspaceGuardBleRetention::reset() {
    records_.fill(Observation{});
    stats_ = {};
    size_ = 0U;
}

BleLiveRetentionDisposition AirspaceGuardBleRetention::accept(
    const Observation& observation) {
    ++stats_.recordsObserved;
    const BleTrackerIngressStatus ingress =
        bleTrackerIngressStatus(observation);
    if (ingress == BleTrackerIngressStatus::MalformedAdvertisement) {
        ++stats_.malformedRecords;
        return BleLiveRetentionDisposition::Malformed;
    }

    ++stats_.validAdvertisements;
    if (ingress == BleTrackerIngressStatus::CoverageAdvertisement) {
        if (size_ == 0U) {
            records_[0] = observation;
            size_ = 1U;
            stats_.recordsRetained = 1U;
            stats_.coverageOnly = true;
            return BleLiveRetentionDisposition::Retained;
        }
        ++stats_.advertisementsIgnored;
        return BleLiveRetentionDisposition::Ignored;
    }

    ++stats_.trackerAdvertisements;
    if (stats_.coverageOnly) {
        records_[0] = observation;
        stats_.coverageOnly = false;
        stats_.trackerAdvertisements = 1U;
        return BleLiveRetentionDisposition::Retained;
    }
    if (size_ >= records_.size()) {
        ++stats_.capacityDrops;
        return BleLiveRetentionDisposition::Full;
    }
    records_[size_++] = observation;
    stats_.recordsRetained = size_;
    return BleLiveRetentionDisposition::Retained;
}

bool AirspaceGuardBleRetention::observationAt(
    std::size_t index, Observation* output) const {
    if (output == nullptr || index >= size_) return false;
    *output = records_[index];
    return true;
}

bool mergeAirspaceGuardReports(const AirspaceGuardReport& wifi,
                               const AirspaceGuardReport& ble,
                               AirspaceGuardReport* output) {
    if (output == nullptr ||
        wifi.status == AirspaceGuardStatus::InvalidPolicy ||
        ble.status == AirspaceGuardStatus::InvalidPolicy ||
        wifi.bleAdvertisementRecords != 0U || ble.disconnectFrames != 0U ||
        ble.identityAdvertisementFrames != 0U ||
        ble.wifiNoiseSamplesObserved != 0U ||
        ble.wifiNoiseSamplesAvailable != 0U ||
        ble.wifiNoiseSamplesInspected != 0U ||
        ble.wifiNoiseSamplesDropped != 0U ||
        ble.wifiNoiseSamplesMalformed != 0U ||
        wifi.findingCount > wifi.findings.size() ||
        ble.findingCount > ble.findings.size() ||
        wifi.inspectionTruncated || ble.inspectionTruncated ||
        wifi.framesAvailable > AirspaceGuard::kFrameInspectionCapacity ||
        ble.framesAvailable > AirspaceGuard::kFrameInspectionCapacity ||
        wifi.framesAvailable + ble.framesAvailable >
            AirspaceGuard::kFrameInspectionCapacity) {
        return false;
    }
    for (std::size_t index = 0U; index < wifi.findingCount; ++index) {
        if (wifi.findings[index].kind ==
            AirspaceFindingKind::BleTrackerPresence) {
            return false;
        }
    }
    for (std::size_t index = 0U; index < ble.findingCount; ++index) {
        if (ble.findings[index].kind !=
            AirspaceFindingKind::BleTrackerPresence) {
            return false;
        }
    }

    AirspaceGuardReport merged{};
    merged.sourceFramesObserved =
        wifi.sourceFramesObserved + ble.sourceFramesObserved;
    merged.framesAvailable = wifi.framesAvailable + ble.framesAvailable;
    merged.framesInspected = wifi.framesInspected + ble.framesInspected;
    merged.disconnectFrames = wifi.disconnectFrames;
    merged.identityAdvertisementFrames = wifi.identityAdvertisementFrames;
    merged.bleAdvertisementRecords = ble.bleAdvertisementRecords;
    merged.wifiNoiseSamplesObserved = wifi.wifiNoiseSamplesObserved;
    merged.wifiNoiseSamplesAvailable = wifi.wifiNoiseSamplesAvailable;
    merged.wifiNoiseSamplesInspected = wifi.wifiNoiseSamplesInspected;
    merged.wifiNoiseSamplesDropped = wifi.wifiNoiseSamplesDropped;
    merged.wifiNoiseSamplesMalformed = wifi.wifiNoiseSamplesMalformed;
    merged.malformedFrames = wifi.malformedFrames + ble.malformedFrames;
    merged.sourceReadFailures =
        wifi.sourceReadFailures + ble.sourceReadFailures;
    merged.sourceFramesDropped =
        wifi.sourceFramesDropped + ble.sourceFramesDropped;
    merged.findingsDropped = wifi.findingsDropped + ble.findingsDropped;

    const auto append = [&](const AirspaceGuardReport& source) {
        for (std::size_t index = 0U; index < source.findingCount; ++index) {
            if (merged.findingCount < merged.findings.size()) {
                merged.findings[merged.findingCount++] =
                    source.findings[index];
            } else {
                ++merged.findingsDropped;
            }
        }
    };
    append(wifi);
    append(ble);

    if (merged.sourceFramesObserved < merged.framesAvailable ||
        merged.framesInspected + merged.sourceReadFailures !=
            merged.framesAvailable ||
        merged.sourceFramesDropped > merged.sourceFramesObserved ||
        merged.findingsDropped >
            merged.framesInspected + merged.wifiNoiseSamplesInspected) {
        return false;
    }
    merged.status = merged.findingCount != 0U
        ? AirspaceGuardStatus::Finding
        : (merged.sourceFramesObserved == 0U ||
                   merged.framesAvailable == 0U ||
                   merged.framesInspected == 0U ||
                   merged.sourceReadFailures != 0U ||
                   merged.sourceFramesDropped != 0U ||
                   merged.malformedFrames != 0U ||
                   merged.wifiNoiseSamplesDropped != 0U ||
                   merged.wifiNoiseSamplesMalformed != 0U
               ? AirspaceGuardStatus::Inconclusive
               : AirspaceGuardStatus::Clear);
    *output = merged;
    return true;
}

const char* airspaceGuardStatusName(AirspaceGuardStatus status) {
    switch (status) {
        case AirspaceGuardStatus::Clear: return "clear";
        case AirspaceGuardStatus::Finding: return "finding";
        case AirspaceGuardStatus::Inconclusive: return "inconclusive";
        case AirspaceGuardStatus::InvalidPolicy: return "invalid_policy";
    }
    return "unknown";
}

const char* airspaceFindingKindName(AirspaceFindingKind kind) {
    switch (kind) {
        case AirspaceFindingKind::WifiDisconnectBurst:
            return "wifi_disconnect_burst";
        case AirspaceFindingKind::WifiSsidSecurityConflict:
            return "wifi_ssid_security_conflict";
        case AirspaceFindingKind::WifiSsidChurn:
            return "wifi_ssid_churn";
        case AirspaceFindingKind::WifiElevatedNoise:
            return "wifi_elevated_noise";
        case AirspaceFindingKind::BleTrackerPresence:
            return "ble_tracker_presence";
    }
    return "unknown";
}

const char* airspaceWifiSecurityName(AirspaceWifiSecurity security) {
    switch (security) {
        case AirspaceWifiSecurity::Unknown: return "unknown";
        case AirspaceWifiSecurity::Open: return "open";
        case AirspaceWifiSecurity::LegacyPrivacy: return "legacy_privacy";
        case AirspaceWifiSecurity::Wpa: return "wpa";
        case AirspaceWifiSecurity::Rsn: return "rsn";
    }
    return "unknown";
}

const char* airspaceBleTrackerProtocolName(
    AirspaceBleTrackerProtocol protocol) {
    switch (protocol) {
        case AirspaceBleTrackerProtocol::FindMy: return "find_my";
        case AirspaceBleTrackerProtocol::SmartTag: return "smart_tag";
        case AirspaceBleTrackerProtocol::Tile: return "tile";
        case AirspaceBleTrackerProtocol::None: return "none";
    }
    return "unknown";
}

const char* airspaceConfidenceName(AirspaceConfidence confidence) {
    switch (confidence) {
        case AirspaceConfidence::Low: return "low";
        case AirspaceConfidence::Medium: return "medium";
        case AirspaceConfidence::High: return "high";
    }
    return "unknown";
}

bool validateAirspaceGuardPolicy(const AirspaceGuardPolicy& policy) {
    return policy.disconnectBurstThreshold >= 2U &&
        policy.disconnectBurstThreshold <=
            AirspaceFinding::kEvidenceCapacity &&
        policy.disconnectWindowUs >= 100000ULL &&
        policy.disconnectWindowUs <= 10000000ULL &&
        policy.ssidSecurityConflictWindowUs >= 100000ULL &&
        policy.ssidSecurityConflictWindowUs <= 10000000ULL &&
        policy.ssidChurnThreshold >= 3U &&
        policy.ssidChurnThreshold <= AirspaceFinding::kEvidenceCapacity &&
        policy.ssidChurnWindowUs >= 100000ULL &&
        policy.ssidChurnWindowUs <= 10000000ULL &&
        policy.elevatedNoiseFloorDbm >= -100 &&
        policy.elevatedNoiseFloorDbm <= -30 &&
        policy.elevatedNoiseThreshold >= 2U &&
        policy.elevatedNoiseThreshold <=
            AirspaceFinding::kEvidenceCapacity &&
        policy.elevatedNoiseWindowUs >= 100000ULL &&
        policy.elevatedNoiseWindowUs <= 10000000ULL &&
        policy.bleTrackerPresenceThreshold >= 2U &&
        policy.bleTrackerPresenceThreshold <=
            AirspaceFinding::kEvidenceCapacity &&
        policy.bleTrackerPresenceWindowUs >= 100000ULL &&
        policy.bleTrackerPresenceWindowUs <= 60000000ULL;
}

bool isWifiDisconnectFrameCandidate(const std::uint8_t* payload,
                                    std::size_t length) {
    if (payload == nullptr || length < 2U) return false;
    const std::uint8_t frameControl = payload[0];
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    return type == 0U && (subtype == 10U || subtype == 12U);
}

bool isWifiIdentityAdvertisementCandidate(const std::uint8_t* payload,
                                          std::size_t length) {
    if (payload == nullptr || length < 2U) return false;
    const std::uint8_t frameControl = payload[0];
    const std::uint8_t type = static_cast<std::uint8_t>(
        (frameControl >> 2U) & 0x03U);
    const std::uint8_t subtype = static_cast<std::uint8_t>(
        (frameControl >> 4U) & 0x0fU);
    return type == 0U && (subtype == 5U || subtype == 8U);
}

WifiIdentityIngressStatus wifiIdentityRetentionKey(
    const std::uint8_t* payload, std::size_t length, bool fcsIncluded,
    WifiIdentityRetentionKey* output) {
    if (output == nullptr) {
        return WifiIdentityIngressStatus::MalformedAdvertisement;
    }
    *output = {};
    if (!isWifiIdentityAdvertisementCandidate(payload, length)) {
        return WifiIdentityIngressStatus::NotAdvertisement;
    }
    if (length > 0xffffU) {
        return WifiIdentityIngressStatus::MalformedAdvertisement;
    }
    WifiFrameView frame{};
    frame.monotonicUs = 1U;
    frame.capturedLength = static_cast<std::uint16_t>(length);
    frame.originalLength = frame.capturedLength;
    frame.channel = 1U;
    frame.kind = WifiFrameKind::Management;
    frame.fcsIncluded = fcsIncluded;
    frame.payload = payload;
    IdentityAdvertisement advertisement{};
    switch (decodeIdentityAdvertisement(frame, &advertisement, 0U)) {
        case IdentityDecode::NotAdvertisement:
            return WifiIdentityIngressStatus::NotAdvertisement;
        case IdentityDecode::IgnoredAdvertisement:
            return WifiIdentityIngressStatus::IgnoredAdvertisement;
        case IdentityDecode::Malformed:
            return WifiIdentityIngressStatus::MalformedAdvertisement;
        case IdentityDecode::Advertisement:
            output->transmitter = advertisement.transmitter;
            output->networkName = advertisement.networkName;
            output->networkNameLength = advertisement.networkNameLength;
            output->security = advertisement.security;
            return WifiIdentityIngressStatus::RetainableAdvertisement;
    }
    return WifiIdentityIngressStatus::MalformedAdvertisement;
}

bool sameWifiIdentityRetentionKey(const WifiIdentityRetentionKey& left,
                                  const WifiIdentityRetentionKey& right) {
    return left.transmitter == right.transmitter &&
        left.networkNameLength == right.networkNameLength &&
        left.security == right.security && left.networkNameLength != 0U &&
        std::memcmp(left.networkName.data(), right.networkName.data(),
                    left.networkNameLength) == 0;
}

bool wifiDisconnectRetentionSlotAvailable(std::size_t totalCapacity,
                                          std::size_t retainedFrames,
                                          std::size_t disconnectFrames) {
    return disconnectFrames < kWifiDisconnectLiveRetentionCapacity &&
        retainedFrames < totalCapacity;
}

bool wifiIdentityRetentionSlotAvailable(std::size_t totalCapacity,
                                        std::size_t retainedFrames,
                                        std::size_t disconnectFrames,
                                        std::size_t identityProfiles) {
    if (disconnectFrames > kWifiDisconnectLiveRetentionCapacity ||
        identityProfiles >= kWifiIdentityLiveRetentionCapacity ||
        retainedFrames > totalCapacity) {
        return false;
    }
    const std::size_t disconnectReservation =
        kWifiDisconnectLiveRetentionCapacity - disconnectFrames;
    return disconnectReservation <= totalCapacity &&
        retainedFrames < totalCapacity - disconnectReservation;
}

AirspaceGuardReport AirspaceGuard::inspectWifi(
    const domain::captures::WifiFrameSource& source,
    const AirspaceGuardPolicy& policy,
    std::size_t sourceFramesDropped,
    std::size_t sourceFramesObserved,
    const WifiNoiseFloorSample* noiseSamples,
    std::size_t noiseSampleCount,
    std::size_t noiseSamplesDropped,
    std::size_t noiseSamplesObserved) const {
    AirspaceGuardReport report{};
    if (!validateAirspaceGuardPolicy(policy)) {
        report.status = AirspaceGuardStatus::InvalidPolicy;
        return report;
    }

    report.sourceFramesDropped = sourceFramesDropped;

    report.framesAvailable = source.frameCount();
    report.sourceFramesObserved = sourceFramesObserved == 0U
        ? report.framesAvailable + sourceFramesDropped : sourceFramesObserved;
    report.wifiNoiseSamplesAvailable = noiseSampleCount;
    report.wifiNoiseSamplesDropped = noiseSamplesDropped;
    report.wifiNoiseSamplesObserved = noiseSamplesObserved == 0U
        ? noiseSampleCount + noiseSamplesDropped : noiseSamplesObserved;
    if (noiseSampleCount != 0U && noiseSamples == nullptr) {
        report.wifiNoiseSamplesMalformed = noiseSampleCount;
    }
    const std::size_t inspectionCount =
        report.framesAvailable < kFrameInspectionCapacity
            ? report.framesAvailable : kFrameInspectionCapacity;
    report.inspectionTruncated = report.framesAvailable > inspectionCount;

    std::uint64_t inspectedFrameMask = 0U;
    {
        std::array<DisconnectEvent, kFrameInspectionCapacity> events{};
        std::size_t eventCount = 0;
        for (std::size_t index = 0; index < inspectionCount; ++index) {
            WifiFrameView frame{};
            if (!source.frameView(index, &frame)) {
                ++report.sourceReadFailures;
                continue;
            }
            ++report.framesInspected;
            inspectedFrameMask |= 1ULL << index;
            if (frame.payload == nullptr || frame.capturedLength < 2U ||
                frame.monotonicUs == 0U || frame.channel == 0U ||
                frame.channel > 14U) {
                ++report.malformedFrames;
                continue;
            }
            DisconnectEvent event{};
            const DisconnectDecode decoded =
                decodeDisconnect(frame, &event, index);
            if (decoded == DisconnectDecode::Disconnect) {
                events[eventCount++] = event;
                ++report.disconnectFrames;
            } else if (decoded == DisconnectDecode::Malformed) {
                ++report.malformedFrames;
                continue;
            }
        }

        for (std::size_t candidate = 0; candidate < eventCount; ++candidate) {
            bool alreadyReported = false;
            for (std::size_t findingIndex = 0;
                 findingIndex < report.findingCount; ++findingIndex) {
                if (sameTransmitter(report.findings[findingIndex].transmitter,
                                    events[candidate].transmitter)) {
                    alreadyReported = true;
                    break;
                }
            }
            if (alreadyReported) continue;

            std::size_t bestStart = candidate;
            std::size_t bestCount = 0;
            for (std::size_t start = 0; start < eventCount; ++start) {
                if (!sameTransmitter(events[start].transmitter,
                                     events[candidate].transmitter)) {
                    continue;
                }
                std::size_t count = 0;
                for (std::size_t index = 0; index < eventCount; ++index) {
                    if (!sameTransmitter(events[index].transmitter,
                                         events[candidate].transmitter) ||
                        events[index].monotonicUs <
                            events[start].monotonicUs) {
                        continue;
                    }
                    const std::uint64_t elapsed = events[index].monotonicUs -
                        events[start].monotonicUs;
                    if (elapsed <= policy.disconnectWindowUs) ++count;
                }
                if (count > bestCount) {
                    bestCount = count;
                    bestStart = start;
                }
            }
            if (bestCount < policy.disconnectBurstThreshold) continue;
            if (report.findingCount >= report.findings.size()) {
                ++report.findingsDropped;
                continue;
            }

            AirspaceFinding& finding =
                report.findings[report.findingCount++];
            finding = {};
            finding.kind = AirspaceFindingKind::WifiDisconnectBurst;
            finding.confidence = confidenceFor(
                bestCount, policy.disconnectBurstThreshold);
            finding.detectorVersion = AirspaceFinding::kDetectorVersion;
            finding.threshold = policy.disconnectBurstThreshold;
            finding.observed = static_cast<std::uint16_t>(bestCount);
            finding.transmitter = events[candidate].transmitter;
            finding.firstUs = events[bestStart].monotonicUs;
            finding.lastUs = finding.firstUs;
            for (std::size_t index = 0; index < eventCount; ++index) {
                const DisconnectEvent& event = events[index];
                if (!sameTransmitter(event.transmitter,
                                     finding.transmitter) ||
                    event.monotonicUs < finding.firstUs ||
                    event.monotonicUs - finding.firstUs >
                        policy.disconnectWindowUs) {
                    continue;
                }
                if (event.subtype == DisconnectSubtype::Deauthentication) {
                    ++finding.deauthenticationFrames;
                } else {
                    ++finding.disassociationFrames;
                }
                if (event.monotonicUs > finding.lastUs) {
                    finding.lastUs = event.monotonicUs;
                }
                if (finding.evidenceCount < finding.evidence.size()) {
                    AirspaceEvidenceRef& evidence =
                        finding.evidence[finding.evidenceCount++];
                    evidence.frameIndex = event.frameIndex;
                    evidence.monotonicUs = event.monotonicUs;
                    evidence.channel = event.channel;
                    evidence.rssiDbm = event.rssiDbm;
                }
            }
        }
    }

    // Disconnect bursts keep first claim on the bounded finding array; a
    // lower-confidence identity indicator must never evict them.
    if (policy.ssidSecurityConflictEnabled || policy.ssidChurnEnabled) {
        std::uint64_t rereadFailureMask = 0U;
        const auto readIdentity = [&](std::size_t index,
                                      IdentityAdvertisement* output) {
            const std::uint64_t bit = 1ULL << index;
            if ((inspectedFrameMask & bit) == 0U) {
                return IdentityDecode::NotAdvertisement;
            }
            WifiFrameView frame{};
            if (!source.frameView(index, &frame)) {
                if ((rereadFailureMask & bit) == 0U &&
                    report.sourceFramesDropped <
                        report.sourceFramesObserved) {
                    ++report.sourceFramesDropped;
                }
                rereadFailureMask |= bit;
                return IdentityDecode::NotAdvertisement;
            }
            if (frame.payload == nullptr || frame.capturedLength < 2U ||
                frame.monotonicUs == 0U || frame.channel == 0U ||
                frame.channel > 14U) {
                // The first pass already counted this malformed source once.
                return IdentityDecode::NotAdvertisement;
            }
            return decodeIdentityAdvertisement(frame, output, index);
        };

        for (std::size_t leftIndex = 0U;
             leftIndex < inspectionCount; ++leftIndex) {
            IdentityAdvertisement left{};
            const IdentityDecode leftDecoded =
                readIdentity(leftIndex, &left);
            if (leftDecoded == IdentityDecode::Advertisement) {
                ++report.identityAdvertisementFrames;
            } else if (leftDecoded == IdentityDecode::Malformed) {
                ++report.malformedFrames;
                continue;
            } else {
                continue;
            }
            if (!policy.ssidSecurityConflictEnabled) continue;
            bool networkAlreadyReported = false;
            for (std::size_t findingIndex = 0;
                 findingIndex < report.findingCount; ++findingIndex) {
                const AirspaceFinding& existing =
                    report.findings[findingIndex];
                if (existing.kind ==
                        AirspaceFindingKind::WifiSsidSecurityConflict &&
                    sameNetworkName(existing.networkName,
                                    existing.networkNameLength,
                                    left.networkName,
                                    left.networkNameLength)) {
                    networkAlreadyReported = true;
                    break;
                }
            }
            if (networkAlreadyReported) continue;

            for (std::size_t rightIndex = leftIndex + 1U;
                 rightIndex < inspectionCount; ++rightIndex) {
                IdentityAdvertisement right{};
                if (readIdentity(rightIndex, &right) !=
                    IdentityDecode::Advertisement) {
                    continue;
                }
                if (!sameNetworkName(left.networkName,
                                     left.networkNameLength,
                                     right.networkName,
                                     right.networkNameLength) ||
                    sameTransmitter(left.transmitter, right.transmitter) ||
                    left.security == right.security) {
                    continue;
                }
                const std::uint64_t firstUs =
                    left.monotonicUs < right.monotonicUs
                        ? left.monotonicUs : right.monotonicUs;
                const std::uint64_t lastUs =
                    left.monotonicUs > right.monotonicUs
                        ? left.monotonicUs : right.monotonicUs;
                if (lastUs - firstUs >
                    policy.ssidSecurityConflictWindowUs) {
                    continue;
                }
                if (report.findingCount >= report.findings.size()) {
                    ++report.findingsDropped;
                    break;
                }

                AirspaceFinding& finding =
                    report.findings[report.findingCount++];
                finding = {};
                finding.kind =
                    AirspaceFindingKind::WifiSsidSecurityConflict;
                // Mixed security for one visible identity is an investigation
                // indicator, not proof of an impersonating access point.
                finding.confidence = AirspaceConfidence::Medium;
                finding.detectorVersion =
                    AirspaceFinding::kWifiIdentityDetectorVersion;
                finding.threshold = 2U;
                finding.observed = 2U;
                finding.transmitter = left.transmitter;
                finding.relatedTransmitter = right.transmitter;
                finding.networkName = left.networkName;
                finding.networkNameLength = left.networkNameLength;
                finding.primarySecurity = left.security;
                finding.relatedSecurity = right.security;
                finding.firstUs = firstUs;
                finding.lastUs = lastUs;
                retainEvidence(finding, left);
                retainEvidence(finding, right);
                break;
            }
        }

        if (policy.ssidChurnEnabled) {
            for (std::size_t startIndex = 0U;
                 startIndex < inspectionCount; ++startIndex) {
                IdentityAdvertisement start{};
                if (readIdentity(startIndex, &start) !=
                    IdentityDecode::Advertisement) {
                    continue;
                }
                bool transmitterAlreadyReported = false;
                for (std::size_t findingIndex = 0U;
                     findingIndex < report.findingCount; ++findingIndex) {
                    const AirspaceFinding& existing =
                        report.findings[findingIndex];
                    if (existing.kind == AirspaceFindingKind::WifiSsidChurn &&
                        sameTransmitter(existing.transmitter,
                                        start.transmitter)) {
                        transmitterAlreadyReported = true;
                        break;
                    }
                }
                if (transmitterAlreadyReported) continue;

                std::array<IdentityAdvertisement,
                           AirspaceFinding::kEvidenceCapacity> unique{};
                std::size_t uniqueCount = 0U;
                std::uint64_t lastUs = start.monotonicUs;
                for (std::size_t eventIndex = 0U;
                     eventIndex < inspectionCount; ++eventIndex) {
                    IdentityAdvertisement event{};
                    if (readIdentity(eventIndex, &event) !=
                            IdentityDecode::Advertisement ||
                        !sameTransmitter(event.transmitter,
                                         start.transmitter) ||
                        event.monotonicUs < start.monotonicUs ||
                        event.monotonicUs - start.monotonicUs >
                            policy.ssidChurnWindowUs) {
                        continue;
                    }
                    bool duplicateName = false;
                    for (std::size_t index = 0U; index < uniqueCount;
                         ++index) {
                        if (sameNetworkName(
                                unique[index].networkName,
                                unique[index].networkNameLength,
                                event.networkName,
                                event.networkNameLength)) {
                            duplicateName = true;
                            break;
                        }
                    }
                    if (duplicateName) continue;
                    if (uniqueCount < unique.size()) {
                        unique[uniqueCount++] = event;
                        if (event.monotonicUs > lastUs) {
                            lastUs = event.monotonicUs;
                        }
                    }
                }
                if (uniqueCount < policy.ssidChurnThreshold) continue;
                if (report.findingCount >= report.findings.size()) {
                    ++report.findingsDropped;
                    continue;
                }

                AirspaceFinding& finding =
                    report.findings[report.findingCount++];
                finding = {};
                finding.kind = AirspaceFindingKind::WifiSsidChurn;
                // Rapid identity churn is a review indicator, not proof that
                // the transmitter is PineAP or otherwise malicious.
                finding.confidence = confidenceFor(
                    uniqueCount, policy.ssidChurnThreshold);
                finding.detectorVersion =
                    AirspaceFinding::kWifiSsidChurnDetectorVersion;
                finding.threshold = policy.ssidChurnThreshold;
                finding.observed = static_cast<std::uint16_t>(uniqueCount);
                finding.transmitter = start.transmitter;
                finding.firstUs = start.monotonicUs;
                finding.lastUs = lastUs;
                for (std::size_t index = 0U; index < uniqueCount; ++index) {
                    retainEvidence(finding, unique[index]);
                }
            }
        }
    }

    const auto validNoiseSample = [&](const WifiNoiseFloorSample& sample) {
        return sample.observationIndex < report.sourceFramesObserved &&
            sample.monotonicUs != 0U && sample.channel >= 1U &&
            sample.channel <= 14U && sample.rssiDbm >= -127 &&
            sample.rssiDbm <= 0 &&
            isWifiNoiseFloorCandidate(sample.noiseFloorDbm);
    };
    if (noiseSamples != nullptr) {
        for (std::size_t index = 0U; index < noiseSampleCount; ++index) {
            if (validNoiseSample(noiseSamples[index])) {
                ++report.wifiNoiseSamplesInspected;
            } else {
                ++report.wifiNoiseSamplesMalformed;
            }
        }
    }

    if (policy.elevatedNoiseEnabled && noiseSamples != nullptr) {
        for (std::size_t candidate = 0U; candidate < noiseSampleCount;
             ++candidate) {
            const WifiNoiseFloorSample& first = noiseSamples[candidate];
            if (!validNoiseSample(first)) continue;
            if (first.noiseFloorDbm < policy.elevatedNoiseFloorDbm) {
                continue;
            }

            bool channelAlreadyReported = false;
            for (std::size_t findingIndex = 0U;
                 findingIndex < report.findingCount; ++findingIndex) {
                const AirspaceFinding& existing =
                    report.findings[findingIndex];
                if (existing.kind == AirspaceFindingKind::WifiElevatedNoise &&
                    existing.evidenceCount != 0U &&
                    existing.evidence[0].channel == first.channel) {
                    channelAlreadyReported = true;
                    break;
                }
            }
            if (channelAlreadyReported) continue;

            std::size_t bestStart = candidate;
            std::size_t bestCount = 0U;
            for (std::size_t start = 0U; start < noiseSampleCount; ++start) {
                const WifiNoiseFloorSample& startSample = noiseSamples[start];
                if (!validNoiseSample(startSample) ||
                    startSample.channel != first.channel ||
                    startSample.noiseFloorDbm <
                        policy.elevatedNoiseFloorDbm) {
                    continue;
                }
                std::size_t count = 0U;
                for (std::size_t index = 0U; index < noiseSampleCount;
                     ++index) {
                    const WifiNoiseFloorSample& sample = noiseSamples[index];
                    if (!validNoiseSample(sample) ||
                        sample.channel != first.channel ||
                        sample.noiseFloorDbm <
                            policy.elevatedNoiseFloorDbm ||
                        sample.monotonicUs < startSample.monotonicUs ||
                        sample.monotonicUs - startSample.monotonicUs >
                            policy.elevatedNoiseWindowUs) {
                        continue;
                    }
                    ++count;
                }
                if (count > bestCount) {
                    bestCount = count;
                    bestStart = start;
                }
            }
            if (bestCount < policy.elevatedNoiseThreshold) continue;
            if (report.findingCount >= report.findings.size()) {
                ++report.findingsDropped;
                continue;
            }

            const WifiNoiseFloorSample& start = noiseSamples[bestStart];
            AirspaceFinding& finding =
                report.findings[report.findingCount++];
            finding = {};
            finding.kind = AirspaceFindingKind::WifiElevatedNoise;
            // Noise-floor elevation cannot identify its cause. Keep confidence
            // low regardless of sample count and never call this jamming proof.
            finding.confidence = AirspaceConfidence::Low;
            finding.detectorVersion =
                AirspaceFinding::kWifiElevatedNoiseDetectorVersion;
            finding.threshold = policy.elevatedNoiseThreshold;
            finding.observed = static_cast<std::uint16_t>(bestCount);
            finding.noiseFloorThresholdDbm =
                policy.elevatedNoiseFloorDbm;
            finding.firstUs = start.monotonicUs;
            finding.lastUs = finding.firstUs;
            for (std::size_t index = 0U; index < noiseSampleCount; ++index) {
                const WifiNoiseFloorSample& sample = noiseSamples[index];
                if (!validNoiseSample(sample) ||
                    sample.channel != first.channel ||
                    sample.noiseFloorDbm < policy.elevatedNoiseFloorDbm ||
                    sample.monotonicUs < finding.firstUs ||
                    sample.monotonicUs - finding.firstUs >
                        policy.elevatedNoiseWindowUs) {
                    continue;
                }
                if (sample.monotonicUs > finding.lastUs) {
                    finding.lastUs = sample.monotonicUs;
                }
                if (finding.evidenceCount < finding.evidence.size()) {
                    AirspaceEvidenceRef& evidence =
                        finding.evidence[finding.evidenceCount++];
                    evidence.frameIndex = sample.observationIndex;
                    evidence.monotonicUs = sample.monotonicUs;
                    evidence.channel = sample.channel;
                    evidence.rssiDbm = sample.rssiDbm;
                    evidence.noiseFloorDbm = sample.noiseFloorDbm;
                }
            }
        }
    }

    if (report.findingCount != 0U) {
        report.status = AirspaceGuardStatus::Finding;
    } else if (report.sourceFramesObserved == 0U ||
               report.framesAvailable == 0U ||
               report.framesInspected == 0U ||
               report.sourceReadFailures != 0U ||
               report.sourceFramesDropped != 0U ||
               report.malformedFrames != 0U ||
               report.wifiNoiseSamplesDropped != 0U ||
               report.wifiNoiseSamplesMalformed != 0U ||
               report.inspectionTruncated) {
        report.status = AirspaceGuardStatus::Inconclusive;
    } else {
        report.status = AirspaceGuardStatus::Clear;
    }
    return report;
}

AirspaceGuardReport AirspaceGuard::inspectBle(
    const BleObservationSource& source, const AirspaceGuardPolicy& policy,
    std::size_t sourceRecordsDropped,
    std::size_t sourceRecordsObserved) const {
    AirspaceGuardReport report{};
    if (!validateAirspaceGuardPolicy(policy)) {
        report.status = AirspaceGuardStatus::InvalidPolicy;
        return report;
    }

    report.sourceFramesDropped = sourceRecordsDropped;
    report.framesAvailable = source.observationCount();
    report.sourceFramesObserved = sourceRecordsObserved == 0U
        ? report.framesAvailable + sourceRecordsDropped
        : sourceRecordsObserved;
    const std::size_t inspectionCount =
        report.framesAvailable < kFrameInspectionCapacity
            ? report.framesAvailable : kFrameInspectionCapacity;
    report.inspectionTruncated = report.framesAvailable > inspectionCount;

    std::array<BleTrackerEvent, kFrameInspectionCapacity> trackerEvents{};
    std::size_t trackerEventCount = 0U;
    for (std::size_t index = 0U; index < inspectionCount; ++index) {
        Observation observation{};
        if (!source.observationAt(index, &observation)) {
            ++report.sourceReadFailures;
            continue;
        }
        ++report.framesInspected;
        BleTrackerEvent event{};
        const BleObservationDecode decoded =
            decodeBleObservation(observation, &event, index);
        if (decoded == BleObservationDecode::Malformed) {
            ++report.malformedFrames;
            continue;
        }
        ++report.bleAdvertisementRecords;
        if (decoded == BleObservationDecode::TrackerAdvertisement) {
            trackerEvents[trackerEventCount++] = event;
        }
    }

    if (policy.bleTrackerPresenceEnabled) {
        for (std::size_t candidate = 0U; candidate < trackerEventCount;
             ++candidate) {
            bool alreadyReported = false;
            for (std::size_t findingIndex = 0U;
                 findingIndex < report.findingCount; ++findingIndex) {
                const AirspaceFinding& existing =
                    report.findings[findingIndex];
                if (existing.kind == AirspaceFindingKind::BleTrackerPresence &&
                    existing.transmitter == trackerEvents[candidate].identity &&
                    existing.bleTrackerProtocol ==
                        trackerEvents[candidate].protocol &&
                    existing.bleAddressType ==
                        trackerEvents[candidate].addressType) {
                    alreadyReported = true;
                    break;
                }
            }
            if (alreadyReported) continue;

            std::size_t bestStart = candidate;
            std::size_t bestCount = 0U;
            for (std::size_t start = 0U; start < trackerEventCount; ++start) {
                if (!sameBleTracker(trackerEvents[start],
                                    trackerEvents[candidate])) {
                    continue;
                }
                std::size_t count = 0U;
                for (std::size_t index = 0U; index < trackerEventCount;
                     ++index) {
                    if (!sameBleTracker(trackerEvents[index],
                                        trackerEvents[candidate]) ||
                        trackerEvents[index].monotonicUs <
                            trackerEvents[start].monotonicUs) {
                        continue;
                    }
                    const std::uint64_t elapsed =
                        trackerEvents[index].monotonicUs -
                        trackerEvents[start].monotonicUs;
                    if (elapsed <= policy.bleTrackerPresenceWindowUs) {
                        ++count;
                    }
                }
                if (count > bestCount) {
                    bestCount = count;
                    bestStart = start;
                }
            }
            if (bestCount < policy.bleTrackerPresenceThreshold) continue;
            if (report.findingCount >= report.findings.size()) {
                ++report.findingsDropped;
                continue;
            }

            AirspaceFinding& finding = report.findings[report.findingCount++];
            finding = {};
            finding.kind = AirspaceFindingKind::BleTrackerPresence;
            // Confidence describes repeated protocol-compatible presence. It
            // does not identify the owner or prove unwanted tracking.
            finding.confidence = confidenceFor(
                bestCount, policy.bleTrackerPresenceThreshold);
            finding.detectorVersion =
                AirspaceFinding::kBleTrackerPresenceDetectorVersion;
            finding.threshold = policy.bleTrackerPresenceThreshold;
            finding.observed = static_cast<std::uint16_t>(bestCount);
            finding.transmitter = trackerEvents[candidate].identity;
            finding.bleTrackerProtocol = trackerEvents[candidate].protocol;
            finding.bleAddressType = trackerEvents[candidate].addressType;
            finding.firstUs = trackerEvents[bestStart].monotonicUs;
            finding.lastUs = finding.firstUs;
            for (std::size_t index = 0U; index < trackerEventCount; ++index) {
                const BleTrackerEvent& event = trackerEvents[index];
                if (!sameBleTracker(event, trackerEvents[candidate]) ||
                    event.monotonicUs < finding.firstUs ||
                    event.monotonicUs - finding.firstUs >
                        policy.bleTrackerPresenceWindowUs) {
                    continue;
                }
                if (event.monotonicUs > finding.lastUs) {
                    finding.lastUs = event.monotonicUs;
                }
                if (finding.evidenceCount < finding.evidence.size()) {
                    AirspaceEvidenceRef& evidence =
                        finding.evidence[finding.evidenceCount++];
                    evidence.frameIndex = event.observationIndex;
                    evidence.monotonicUs = event.monotonicUs;
                    // The current passive host stack does not expose which
                    // advertising channel (37/38/39) received the record.
                    evidence.channel = 0U;
                    evidence.rssiDbm = event.rssiDbm;
                }
            }
        }
    }

    if (report.findingCount != 0U) {
        report.status = AirspaceGuardStatus::Finding;
    } else if (report.sourceFramesObserved == 0U ||
               report.framesAvailable == 0U ||
               report.framesInspected == 0U ||
               report.sourceReadFailures != 0U ||
               report.sourceFramesDropped != 0U ||
               report.malformedFrames != 0U ||
               report.inspectionTruncated) {
        report.status = AirspaceGuardStatus::Inconclusive;
    } else {
        report.status = AirspaceGuardStatus::Clear;
    }
    return report;
}

}  // namespace leshy1::services::guard
