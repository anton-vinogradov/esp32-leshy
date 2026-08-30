#include "AutomationPackage.h"

#include <cstring>
#include <limits>

namespace leshy1::apps::automation {
namespace {

constexpr std::uint8_t kWireVersion = 1U;
constexpr std::size_t kMinimumStepBytes = 8U;
constexpr std::uint32_t kMaximumDelayMs = 30000U;
constexpr std::uint32_t kMaximumHidEventMs = 1000U;
constexpr std::size_t kMaximumActionIdBytes = 48U;

std::uint16_t read16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>(bytes[0]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(bytes[1]) << 8U);
}

std::uint32_t read32(const std::uint8_t* bytes) {
    return static_cast<std::uint32_t>(bytes[0]) |
        (static_cast<std::uint32_t>(bytes[1]) << 8U) |
        (static_cast<std::uint32_t>(bytes[2]) << 16U) |
        (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

bool anyNonZero(const std::uint8_t* bytes, std::size_t size) {
    std::uint8_t combined = 0U;
    for (std::size_t index = 0U; index < size; ++index) {
        combined = static_cast<std::uint8_t>(combined | bytes[index]);
    }
    return combined != 0U;
}

bool allZero(const std::uint8_t* bytes, std::size_t size) {
    return !anyNonZero(bytes, size);
}

bool supportedKind(AutomationPackageKind kind) {
    switch (kind) {
        case AutomationPackageKind::ActionScript:
        case AutomationPackageKind::UsbHid:
        case AutomationPackageKind::BleHid:
            return true;
    }
    return false;
}

bool supportedTarget(AutomationTargetClass target) {
    switch (target) {
        case AutomationTargetClass::Device:
        case AutomationTargetClass::UsbHost:
        case AutomationTargetClass::BlePeer:
            return true;
    }
    return false;
}

bool validActionId(const std::uint8_t* bytes, std::size_t size) {
    if (bytes == nullptr || size == 0U || size > kMaximumActionIdBytes) {
        return false;
    }
    for (std::size_t index = 0U; index < size; ++index) {
        const char value = static_cast<char>(bytes[index]);
        const bool valid = (value >= 'a' && value <= 'z') ||
            (value >= '0' && value <= '9') || value == '.' || value == '-' ||
            value == '_';
        if (!valid) return false;
    }
    return true;
}

AutomationTargetClass expectedTarget(AutomationPackageKind kind) {
    switch (kind) {
        case AutomationPackageKind::ActionScript:
            return AutomationTargetClass::Device;
        case AutomationPackageKind::UsbHid:
            return AutomationTargetClass::UsbHost;
        case AutomationPackageKind::BleHid:
            return AutomationTargetClass::BlePeer;
    }
    return AutomationTargetClass::Device;
}

bool constantTimeEqual(
    const std::array<std::uint8_t, kAutomationTargetFingerprintBytes>& left,
    const std::array<std::uint8_t, kAutomationTargetFingerprintBytes>& right) {
    std::uint8_t difference = 0U;
    for (std::size_t index = 0U; index < left.size(); ++index) {
        difference = static_cast<std::uint8_t>(
            difference | static_cast<std::uint8_t>(left[index] ^ right[index]));
    }
    return difference == 0U;
}

}  // namespace

const char* automationParseStatusName(AutomationParseStatus status) {
    switch (status) {
        case AutomationParseStatus::Parsed: return "parsed";
        case AutomationParseStatus::InvalidArgument: return "invalid_argument";
        case AutomationParseStatus::TooSmall: return "too_small";
        case AutomationParseStatus::TooLarge: return "too_large";
        case AutomationParseStatus::InvalidMagic: return "invalid_magic";
        case AutomationParseStatus::UnsupportedWireVersion:
            return "unsupported_wire_version";
        case AutomationParseStatus::UnsupportedSignatureAlgorithm:
            return "unsupported_signature_algorithm";
        case AutomationParseStatus::InvalidHeader: return "invalid_header";
        case AutomationParseStatus::LengthMismatch: return "length_mismatch";
        case AutomationParseStatus::InvalidIdentity: return "invalid_identity";
        case AutomationParseStatus::InvalidStep: return "invalid_step";
    }
    return "invalid_status";
}

const char* automationPolicyStatusName(AutomationPolicyStatus status) {
    switch (status) {
        case AutomationPolicyStatus::Ready: return "ready";
        case AutomationPolicyStatus::IncompatibleApi: return "incompatible_api";
        case AutomationPolicyStatus::InvalidKindTarget:
            return "invalid_kind_target";
        case AutomationPolicyStatus::UnknownPermission:
            return "unknown_permission";
        case AutomationPolicyStatus::InvalidRuntime: return "invalid_runtime";
        case AutomationPolicyStatus::InvalidEventCeiling:
            return "invalid_event_ceiling";
        case AutomationPolicyStatus::InvalidOutputCeiling:
            return "invalid_output_ceiling";
        case AutomationPolicyStatus::InvalidStepCount:
            return "invalid_step_count";
        case AutomationPolicyStatus::StepKindMismatch:
            return "step_kind_mismatch";
        case AutomationPolicyStatus::InvalidActionId:
            return "invalid_action_id";
        case AutomationPolicyStatus::InvalidStepPayload:
            return "invalid_step_payload";
        case AutomationPolicyStatus::PermissionMismatch:
            return "permission_mismatch";
        case AutomationPolicyStatus::RuntimeExceeded:
            return "runtime_exceeded";
    }
    return "invalid_status";
}

const char* automationTrustStatusName(AutomationTrustStatus status) {
    switch (status) {
        case AutomationTrustStatus::VerifiedTrusted: return "verified_trusted";
        case AutomationTrustStatus::MissingSignature: return "missing_signature";
        case AutomationTrustStatus::UnknownSigner: return "unknown_signer";
        case AutomationTrustStatus::InvalidSignature: return "invalid_signature";
        case AutomationTrustStatus::VerifierUnavailable:
            return "verifier_unavailable";
    }
    return "invalid_status";
}

const char* automationPackageKindName(AutomationPackageKind kind) {
    switch (kind) {
        case AutomationPackageKind::ActionScript: return "action_script";
        case AutomationPackageKind::UsbHid: return "usb_hid";
        case AutomationPackageKind::BleHid: return "ble_hid";
    }
    return "invalid";
}

const char* automationTargetClassName(AutomationTargetClass target) {
    switch (target) {
        case AutomationTargetClass::Device: return "device";
        case AutomationTargetClass::UsbHost: return "usb_host";
        case AutomationTargetClass::BlePeer: return "ble_peer";
    }
    return "invalid";
}

AutomationInspection inspectAutomationPackage(
    const std::uint8_t* bytes, std::size_t size,
    std::uint16_t currentActionApiVersion,
    AutomationSignatureVerifier* verifier) {
    AutomationInspection result{};
    if (bytes == nullptr || currentActionApiVersion == 0U) return result;
    if (size < kAutomationHeaderBytes + kMinimumStepBytes +
                   kAutomationSignatureBytes) {
        result.parseStatus = AutomationParseStatus::TooSmall;
        return result;
    }
    if (size > kAutomationMaximumPackageBytes) {
        result.parseStatus = AutomationParseStatus::TooLarge;
        return result;
    }
    if (std::memcmp(bytes, "LHAU", 4U) != 0) {
        result.parseStatus = AutomationParseStatus::InvalidMagic;
        return result;
    }
    if (bytes[4] != kWireVersion) {
        result.parseStatus = AutomationParseStatus::UnsupportedWireVersion;
        return result;
    }
    result.kind = static_cast<AutomationPackageKind>(bytes[5]);
    const auto signatureAlgorithm =
        static_cast<AutomationSignatureAlgorithm>(bytes[6]);
    result.targetClass = static_cast<AutomationTargetClass>(bytes[7]);
    if (signatureAlgorithm != AutomationSignatureAlgorithm::EcdsaP256Sha256) {
        result.parseStatus =
            AutomationParseStatus::UnsupportedSignatureAlgorithm;
        return result;
    }
    if (!supportedKind(result.kind) || !supportedTarget(result.targetClass) ||
        !allZero(bytes + 56U, 8U)) {
        result.parseStatus = AutomationParseStatus::InvalidHeader;
        return result;
    }

    const std::size_t totalBytes = read16(bytes + 8U);
    const std::size_t signedBytes = read16(bytes + 10U);
    if (totalBytes != size || signedBytes < kAutomationHeaderBytes +
                                              kMinimumStepBytes ||
        signedBytes + kAutomationSignatureBytes != totalBytes) {
        result.parseStatus = AutomationParseStatus::LengthMismatch;
        return result;
    }

    result.scriptVersion = read16(bytes + 12U);
    result.minimumActionApiVersion = read16(bytes + 14U);
    result.requestedPermissions = read32(bytes + 16U);
    result.runtimeCeilingMs = read32(bytes + 20U);
    result.eventCeiling = read16(bytes + 24U);
    result.outputCeilingBytes = read16(bytes + 26U);
    result.declaredSteps = read16(bytes + 28U);
    if (read16(bytes + 30U) != 0U) {
        result.parseStatus = AutomationParseStatus::InvalidHeader;
        return result;
    }
    std::memcpy(result.packageId.data(), bytes + 32U,
                result.packageId.size());
    std::memcpy(result.keyId.data(), bytes + 48U, result.keyId.size());
    if (!anyNonZero(result.packageId.data(), result.packageId.size()) ||
        !anyNonZero(result.keyId.data(), result.keyId.size())) {
        result.parseStatus = AutomationParseStatus::InvalidIdentity;
        return result;
    }

    AutomationPolicyStatus policy = AutomationPolicyStatus::Ready;
    std::size_t cursor = kAutomationHeaderBytes;
    std::uint64_t aggregateDuration = 0U;
    while (cursor < signedBytes) {
        if (signedBytes - cursor < kMinimumStepBytes) {
            result.parseStatus = AutomationParseStatus::InvalidStep;
            return result;
        }
        const auto opcode = static_cast<AutomationOpcode>(bytes[cursor]);
        const std::uint8_t flags = bytes[cursor + 1U];
        const std::size_t recordBytes = read16(bytes + cursor + 2U);
        const std::uint32_t durationMs = read32(bytes + cursor + 4U);
        if (flags != 0U || recordBytes < kMinimumStepBytes ||
            recordBytes > signedBytes - cursor) {
            result.parseStatus = AutomationParseStatus::InvalidStep;
            return result;
        }
        const std::uint8_t* payload = bytes + cursor + kMinimumStepBytes;
        const std::size_t payloadSize = recordBytes - kMinimumStepBytes;
        switch (opcode) {
            case AutomationOpcode::Delay:
                ++result.delaySteps;
                if (payloadSize != 0U || durationMs == 0U ||
                    durationMs > kMaximumDelayMs) {
                    if (policy == AutomationPolicyStatus::Ready) {
                        policy = AutomationPolicyStatus::InvalidStepPayload;
                    }
                }
                break;
            case AutomationOpcode::InvokeAction:
                ++result.actionSteps;
                ++result.activeEvents;
                result.impliedPermissions |=
                    automationPermission(AutomationPermission::InvokeAction);
                if (result.kind != AutomationPackageKind::ActionScript &&
                    policy == AutomationPolicyStatus::Ready) {
                    policy = AutomationPolicyStatus::StepKindMismatch;
                }
                if (!validActionId(payload, payloadSize) &&
                    policy == AutomationPolicyStatus::Ready) {
                    policy = AutomationPolicyStatus::InvalidActionId;
                }
                if (durationMs == 0U ||
                    durationMs > kAutomationMaximumRuntimeMs) {
                    if (policy == AutomationPolicyStatus::Ready) {
                        policy = AutomationPolicyStatus::InvalidStepPayload;
                    }
                }
                break;
            case AutomationOpcode::Keyboard:
                ++result.keyboardSteps;
                ++result.activeEvents;
                if (result.kind == AutomationPackageKind::UsbHid) {
                    result.impliedPermissions |= automationPermission(
                        AutomationPermission::UsbKeyboard);
                } else if (result.kind == AutomationPackageKind::BleHid) {
                    result.impliedPermissions |= automationPermission(
                        AutomationPermission::BleKeyboard);
                } else if (policy == AutomationPolicyStatus::Ready) {
                    policy = AutomationPolicyStatus::StepKindMismatch;
                }
                if (payloadSize != 2U || payload[1] == 0U ||
                    payload[1] > 0xe7U ||
                    durationMs == 0U || durationMs > kMaximumHidEventMs) {
                    if (policy == AutomationPolicyStatus::Ready) {
                        policy = AutomationPolicyStatus::InvalidStepPayload;
                    }
                }
                break;
            case AutomationOpcode::Pointer:
                ++result.pointerSteps;
                ++result.activeEvents;
                if (result.kind == AutomationPackageKind::UsbHid) {
                    result.impliedPermissions |= automationPermission(
                        AutomationPermission::UsbPointer);
                } else if (result.kind == AutomationPackageKind::BleHid) {
                    result.impliedPermissions |= automationPermission(
                        AutomationPermission::BlePointer);
                } else if (policy == AutomationPolicyStatus::Ready) {
                    policy = AutomationPolicyStatus::StepKindMismatch;
                }
                if (payloadSize != 3U || allZero(payload, payloadSize) ||
                    durationMs == 0U || durationMs > kMaximumHidEventMs) {
                    if (policy == AutomationPolicyStatus::Ready) {
                        policy = AutomationPolicyStatus::InvalidStepPayload;
                    }
                }
                break;
            default:
                result.parseStatus = AutomationParseStatus::InvalidStep;
                return result;
        }
        aggregateDuration += durationMs;
        ++result.observedSteps;
        cursor += recordBytes;
    }
    if (cursor != signedBytes) {
        result.parseStatus = AutomationParseStatus::InvalidStep;
        return result;
    }
    result.aggregateDurationMs = aggregateDuration >
            std::numeric_limits<std::uint32_t>::max()
        ? std::numeric_limits<std::uint32_t>::max()
        : static_cast<std::uint32_t>(aggregateDuration);
    result.parseStatus = AutomationParseStatus::Parsed;

    if (policy == AutomationPolicyStatus::Ready &&
        (result.scriptVersion == 0U || result.minimumActionApiVersion == 0U ||
         result.minimumActionApiVersion > currentActionApiVersion)) {
        policy = AutomationPolicyStatus::IncompatibleApi;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        result.targetClass != expectedTarget(result.kind)) {
        policy = AutomationPolicyStatus::InvalidKindTarget;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        (result.requestedPermissions & ~kKnownAutomationPermissions) != 0U) {
        policy = AutomationPolicyStatus::UnknownPermission;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        (result.runtimeCeilingMs < kAutomationMinimumRuntimeMs ||
         result.runtimeCeilingMs > kAutomationMaximumRuntimeMs)) {
        policy = AutomationPolicyStatus::InvalidRuntime;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        (result.eventCeiling == 0U ||
         result.eventCeiling > kAutomationMaximumEvents ||
         result.activeEvents > result.eventCeiling)) {
        policy = AutomationPolicyStatus::InvalidEventCeiling;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        result.outputCeilingBytes > kAutomationMaximumOutputBytes) {
        policy = AutomationPolicyStatus::InvalidOutputCeiling;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        (result.declaredSteps == 0U ||
         result.declaredSteps > kAutomationMaximumSteps ||
         result.observedSteps != result.declaredSteps)) {
        policy = AutomationPolicyStatus::InvalidStepCount;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        result.requestedPermissions != result.impliedPermissions) {
        policy = AutomationPolicyStatus::PermissionMismatch;
    }
    if (policy == AutomationPolicyStatus::Ready &&
        (aggregateDuration > result.runtimeCeilingMs ||
         aggregateDuration > std::numeric_limits<std::uint32_t>::max())) {
        policy = AutomationPolicyStatus::RuntimeExceeded;
    }
    result.policyStatus = policy;

    std::array<std::uint8_t, kAutomationSignatureBytes> signature{};
    std::memcpy(signature.data(), bytes + signedBytes, signature.size());
    if (allZero(signature.data(), signature.size())) {
        result.trustStatus = AutomationTrustStatus::MissingSignature;
    } else if (verifier == nullptr) {
        result.trustStatus = AutomationTrustStatus::VerifierUnavailable;
    } else {
        result.trustStatus = verifier->verify(
            bytes, signedBytes, result.keyId, signature);
        if (result.trustStatus == AutomationTrustStatus::MissingSignature ||
            result.trustStatus == AutomationTrustStatus::VerifierUnavailable) {
            result.trustStatus = AutomationTrustStatus::InvalidSignature;
        }
    }
    result.executionEligible =
        result.policyStatus == AutomationPolicyStatus::Ready &&
        result.trustStatus == AutomationTrustStatus::VerifiedTrusted;
    return result;
}

const char* automationAdmissionStatusName(AutomationAdmissionStatus status) {
    switch (status) {
        case AutomationAdmissionStatus::Ready: return "ready";
        case AutomationAdmissionStatus::PackageInvalid: return "package_invalid";
        case AutomationAdmissionStatus::PolicyRejected: return "policy_rejected";
        case AutomationAdmissionStatus::SignatureRequired:
            return "signature_required";
        case AutomationAdmissionStatus::AuthenticationRequired:
            return "authentication_required";
        case AutomationAdmissionStatus::PermissionDenied:
            return "permission_denied";
        case AutomationAdmissionStatus::TargetRequired: return "target_required";
        case AutomationAdmissionStatus::TargetMismatch: return "target_mismatch";
        case AutomationAdmissionStatus::ConfirmationRequired:
            return "confirmation_required";
        case AutomationAdmissionStatus::ConfirmationMismatch:
            return "confirmation_mismatch";
    }
    return "invalid_status";
}

AutomationAdmissionStatus admitAutomationExecution(
    const AutomationInspection& inspection,
    const AutomationExecutionContext& context) {
    if (inspection.parseStatus != AutomationParseStatus::Parsed) {
        return AutomationAdmissionStatus::PackageInvalid;
    }
    if (inspection.policyStatus != AutomationPolicyStatus::Ready) {
        return AutomationAdmissionStatus::PolicyRejected;
    }
    if (inspection.trustStatus != AutomationTrustStatus::VerifiedTrusted ||
        !inspection.executionEligible) {
        return AutomationAdmissionStatus::SignatureRequired;
    }
    if (!context.authenticated) {
        return AutomationAdmissionStatus::AuthenticationRequired;
    }
    if (context.grantedPermissions != inspection.requestedPermissions) {
        return AutomationAdmissionStatus::PermissionDenied;
    }
    if (!context.targetSelected ||
        !anyNonZero(context.selectedTargetFingerprint.data(),
                    context.selectedTargetFingerprint.size())) {
        return AutomationAdmissionStatus::TargetRequired;
    }
    if (context.selectedTargetClass != inspection.targetClass) {
        return AutomationAdmissionStatus::TargetMismatch;
    }
    if (!context.confirmationFresh) {
        return AutomationAdmissionStatus::ConfirmationRequired;
    }
    if (!anyNonZero(context.confirmedTargetFingerprint.data(),
                    context.confirmedTargetFingerprint.size()) ||
        !constantTimeEqual(context.selectedTargetFingerprint,
                           context.confirmedTargetFingerprint)) {
        return AutomationAdmissionStatus::ConfirmationMismatch;
    }
    return AutomationAdmissionStatus::Ready;
}

}  // namespace leshy1::apps::automation
