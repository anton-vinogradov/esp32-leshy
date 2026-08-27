#include "AirspaceGuard.h"

#include <cstring>

namespace leshy1::services::guard {

namespace {

using domain::captures::WifiFrameKind;
using domain::captures::WifiFrameView;

enum class DisconnectSubtype : std::uint8_t {
    Deauthentication,
    Disassociation,
};

enum class DisconnectDecode : std::uint8_t {
    NotDisconnect,
    Disconnect,
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

bool sameTransmitter(const std::array<std::uint8_t, 6>& left,
                     const std::array<std::uint8_t, 6>& right) {
    return std::memcmp(left.data(), right.data(), left.size()) == 0;
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

AirspaceConfidence confidenceFor(std::size_t observed,
                                 std::size_t threshold) {
    return observed >= threshold * 2U
        ? AirspaceConfidence::High : AirspaceConfidence::Medium;
}

}  // namespace

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
        policy.disconnectWindowUs <= 10000000ULL;
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

AirspaceGuardReport AirspaceGuard::inspectWifi(
    const domain::captures::WifiFrameSource& source,
    const AirspaceGuardPolicy& policy,
    std::size_t sourceFramesDropped,
    std::size_t sourceFramesObserved) const {
    AirspaceGuardReport report{};
    if (!validateAirspaceGuardPolicy(policy)) {
        report.status = AirspaceGuardStatus::InvalidPolicy;
        return report;
    }

    report.sourceFramesDropped = sourceFramesDropped;

    report.framesAvailable = source.frameCount();
    report.sourceFramesObserved = sourceFramesObserved == 0U
        ? report.framesAvailable + sourceFramesDropped : sourceFramesObserved;
    const std::size_t inspectionCount =
        report.framesAvailable < kFrameInspectionCapacity
            ? report.framesAvailable : kFrameInspectionCapacity;
    report.inspectionTruncated = report.framesAvailable > inspectionCount;

    std::array<DisconnectEvent, kFrameInspectionCapacity> events{};
    std::size_t eventCount = 0;
    for (std::size_t index = 0; index < inspectionCount; ++index) {
        WifiFrameView frame{};
        if (!source.frameView(index, &frame)) {
            ++report.sourceReadFailures;
            continue;
        }
        ++report.framesInspected;
        if (frame.payload == nullptr || frame.capturedLength < 2U ||
            frame.monotonicUs == 0U || frame.channel == 0U ||
            frame.channel > 14U) {
            ++report.malformedFrames;
            continue;
        }
        DisconnectEvent event{};
        const DisconnectDecode decoded = decodeDisconnect(frame, &event, index);
        if (decoded == DisconnectDecode::Disconnect) {
            events[eventCount++] = event;
            ++report.disconnectFrames;
        } else if (decoded == DisconnectDecode::Malformed) {
            ++report.malformedFrames;
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
                    events[index].monotonicUs < events[start].monotonicUs) {
                    continue;
                }
                const std::uint64_t elapsed =
                    events[index].monotonicUs - events[start].monotonicUs;
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

        AirspaceFinding& finding = report.findings[report.findingCount++];
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
            if (!sameTransmitter(event.transmitter, finding.transmitter) ||
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
