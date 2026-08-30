#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::automation {

constexpr std::size_t kAutomationHeaderBytes = 64U;
constexpr std::size_t kAutomationSignatureBytes = 64U;
constexpr std::size_t kAutomationPackageIdBytes = 16U;
constexpr std::size_t kAutomationKeyIdBytes = 8U;
constexpr std::size_t kAutomationTargetFingerprintBytes = 16U;
constexpr std::size_t kAutomationMaximumPackageBytes = 4096U;
constexpr std::uint16_t kAutomationMaximumSteps = 32U;
constexpr std::uint16_t kAutomationMaximumEvents = 128U;
constexpr std::uint16_t kAutomationMaximumOutputBytes = 1024U;
constexpr std::uint32_t kAutomationMinimumRuntimeMs = 1000U;
constexpr std::uint32_t kAutomationMaximumRuntimeMs = 300000U;

enum class AutomationPackageKind : std::uint8_t {
    ActionScript = 1U,
    UsbHid = 2U,
    BleHid = 3U,
};

enum class AutomationTargetClass : std::uint8_t {
    Device = 1U,
    UsbHost = 2U,
    BlePeer = 3U,
};

enum class AutomationSignatureAlgorithm : std::uint8_t {
    EcdsaP256Sha256 = 1U,
};

using AutomationPermissionMask = std::uint32_t;

enum class AutomationPermission : AutomationPermissionMask {
    InvokeAction = 1U << 0U,
    UsbKeyboard = 1U << 1U,
    UsbPointer = 1U << 2U,
    BleKeyboard = 1U << 3U,
    BlePointer = 1U << 4U,
};

constexpr AutomationPermissionMask automationPermission(
    AutomationPermission permission) {
    return static_cast<AutomationPermissionMask>(permission);
}

constexpr AutomationPermissionMask kKnownAutomationPermissions =
    automationPermission(AutomationPermission::InvokeAction) |
    automationPermission(AutomationPermission::UsbKeyboard) |
    automationPermission(AutomationPermission::UsbPointer) |
    automationPermission(AutomationPermission::BleKeyboard) |
    automationPermission(AutomationPermission::BlePointer);

enum class AutomationOpcode : std::uint8_t {
    Delay = 1U,
    InvokeAction = 2U,
    Keyboard = 3U,
    Pointer = 4U,
};

enum class AutomationParseStatus : std::uint8_t {
    Parsed,
    InvalidArgument,
    TooSmall,
    TooLarge,
    InvalidMagic,
    UnsupportedWireVersion,
    UnsupportedSignatureAlgorithm,
    InvalidHeader,
    LengthMismatch,
    InvalidIdentity,
    InvalidStep,
};

enum class AutomationPolicyStatus : std::uint8_t {
    Ready,
    IncompatibleApi,
    InvalidKindTarget,
    UnknownPermission,
    InvalidRuntime,
    InvalidEventCeiling,
    InvalidOutputCeiling,
    InvalidStepCount,
    StepKindMismatch,
    InvalidActionId,
    InvalidStepPayload,
    PermissionMismatch,
    RuntimeExceeded,
};

enum class AutomationTrustStatus : std::uint8_t {
    VerifiedTrusted,
    MissingSignature,
    UnknownSigner,
    InvalidSignature,
    VerifierUnavailable,
};

const char* automationParseStatusName(AutomationParseStatus status);
const char* automationPolicyStatusName(AutomationPolicyStatus status);
const char* automationTrustStatusName(AutomationTrustStatus status);
const char* automationPackageKindName(AutomationPackageKind kind);
const char* automationTargetClassName(AutomationTargetClass target);

class AutomationSignatureVerifier {
public:
    virtual ~AutomationSignatureVerifier() = default;
    virtual AutomationTrustStatus verify(
        const std::uint8_t* signedBytes, std::size_t signedSize,
        const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId,
        const std::array<std::uint8_t, kAutomationSignatureBytes>& signature) = 0;
};

struct AutomationInspection final {
    AutomationParseStatus parseStatus = AutomationParseStatus::InvalidArgument;
    AutomationPolicyStatus policyStatus = AutomationPolicyStatus::InvalidStepCount;
    AutomationTrustStatus trustStatus = AutomationTrustStatus::VerifierUnavailable;
    AutomationPackageKind kind = AutomationPackageKind::ActionScript;
    AutomationTargetClass targetClass = AutomationTargetClass::Device;
    AutomationPermissionMask requestedPermissions = 0U;
    AutomationPermissionMask impliedPermissions = 0U;
    std::uint16_t scriptVersion = 0U;
    std::uint16_t minimumActionApiVersion = 0U;
    std::uint32_t runtimeCeilingMs = 0U;
    std::uint32_t aggregateDurationMs = 0U;
    std::uint16_t eventCeiling = 0U;
    std::uint16_t outputCeilingBytes = 0U;
    std::uint16_t declaredSteps = 0U;
    std::uint16_t observedSteps = 0U;
    std::uint16_t delaySteps = 0U;
    std::uint16_t actionSteps = 0U;
    std::uint16_t keyboardSteps = 0U;
    std::uint16_t pointerSteps = 0U;
    std::uint16_t activeEvents = 0U;
    std::array<std::uint8_t, kAutomationPackageIdBytes> packageId{};
    std::array<std::uint8_t, kAutomationKeyIdBytes> keyId{};
    bool executionEligible = false;
    std::uint32_t actionsInvoked = 0U;
    std::uint32_t hidReportsEmitted = 0U;
    std::uint32_t resourcesAcquired = 0U;
};

AutomationInspection inspectAutomationPackage(
    const std::uint8_t* bytes, std::size_t size,
    std::uint16_t currentActionApiVersion,
    AutomationSignatureVerifier* verifier);

enum class AutomationAdmissionStatus : std::uint8_t {
    Ready,
    PackageInvalid,
    PolicyRejected,
    SignatureRequired,
    AuthenticationRequired,
    PermissionDenied,
    TargetRequired,
    TargetMismatch,
    ConfirmationRequired,
    ConfirmationMismatch,
};

const char* automationAdmissionStatusName(AutomationAdmissionStatus status);

struct AutomationExecutionContext final {
    AutomationPermissionMask grantedPermissions = 0U;
    AutomationTargetClass selectedTargetClass = AutomationTargetClass::Device;
    std::array<std::uint8_t, kAutomationTargetFingerprintBytes>
        selectedTargetFingerprint{};
    std::array<std::uint8_t, kAutomationTargetFingerprintBytes>
        confirmedTargetFingerprint{};
    bool authenticated = false;
    bool targetSelected = false;
    bool confirmationFresh = false;
};

AutomationAdmissionStatus admitAutomationExecution(
    const AutomationInspection& inspection,
    const AutomationExecutionContext& context);

}  // namespace leshy1::apps::automation

