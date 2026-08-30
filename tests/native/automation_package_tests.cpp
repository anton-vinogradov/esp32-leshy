#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

#include "apps/automation/AutomationPackage.h"
#include "apps/automation/AutomationInspectorController.h"

using namespace leshy1::apps::automation;

namespace {

int failures = 0;

#define CHECK(expression)                                                     \
    do {                                                                      \
        if (!(expression)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__                         \
                      << ": check failed: " #expression << '\n';            \
            ++failures;                                                       \
        }                                                                     \
    } while (false)

void put16(std::vector<std::uint8_t>* bytes, std::size_t offset,
           std::uint16_t value) {
    (*bytes)[offset] = static_cast<std::uint8_t>(value & 0xffU);
    (*bytes)[offset + 1U] = static_cast<std::uint8_t>(value >> 8U);
}

void put32(std::vector<std::uint8_t>* bytes, std::size_t offset,
           std::uint32_t value) {
    (*bytes)[offset] = static_cast<std::uint8_t>(value & 0xffU);
    (*bytes)[offset + 1U] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    (*bytes)[offset + 2U] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
    (*bytes)[offset + 3U] = static_cast<std::uint8_t>(value >> 24U);
}

class PackageBuilder final {
public:
    PackageBuilder(AutomationPackageKind kind, AutomationTargetClass target,
                   AutomationPermissionMask permissions) {
        bytes.resize(kAutomationHeaderBytes, 0U);
        std::memcpy(bytes.data(), "LHAU", 4U);
        bytes[4] = 1U;
        bytes[5] = static_cast<std::uint8_t>(kind);
        bytes[6] = static_cast<std::uint8_t>(
            AutomationSignatureAlgorithm::EcdsaP256Sha256);
        bytes[7] = static_cast<std::uint8_t>(target);
        put16(&bytes, 12U, 1U);
        put16(&bytes, 14U, 1U);
        put32(&bytes, 16U, permissions);
        put32(&bytes, 20U, 2000U);
        put16(&bytes, 24U, 8U);
        put16(&bytes, 26U, 128U);
        for (std::size_t index = 0U; index < kAutomationPackageIdBytes; ++index) {
            bytes[32U + index] = static_cast<std::uint8_t>(index + 1U);
        }
        for (std::size_t index = 0U; index < kAutomationKeyIdBytes; ++index) {
            bytes[48U + index] = static_cast<std::uint8_t>(0xa0U + index);
        }
    }

    void addStep(AutomationOpcode opcode, std::uint32_t durationMs,
                 const std::uint8_t* payload = nullptr,
                 std::size_t payloadSize = 0U) {
        const std::size_t start = bytes.size();
        bytes.resize(start + 8U + payloadSize, 0U);
        bytes[start] = static_cast<std::uint8_t>(opcode);
        put16(&bytes, start + 2U,
              static_cast<std::uint16_t>(8U + payloadSize));
        put32(&bytes, start + 4U, durationMs);
        if (payloadSize != 0U) {
            std::memcpy(bytes.data() + start + 8U, payload, payloadSize);
        }
        ++steps;
    }

    void addAction(const char* id, std::uint32_t durationMs = 500U) {
        addStep(AutomationOpcode::InvokeAction, durationMs,
                reinterpret_cast<const std::uint8_t*>(id), std::strlen(id));
    }

    std::vector<std::uint8_t> finish(std::uint8_t signatureByte = 0x5aU) {
        const std::size_t signedBytes = bytes.size();
        bytes.resize(signedBytes + kAutomationSignatureBytes, signatureByte);
        put16(&bytes, 8U, static_cast<std::uint16_t>(bytes.size()));
        put16(&bytes, 10U, static_cast<std::uint16_t>(signedBytes));
        put16(&bytes, 28U, steps);
        return bytes;
    }

    std::vector<std::uint8_t> bytes;
    std::uint16_t steps = 0U;
};

class RecordingVerifier final : public AutomationSignatureVerifier {
public:
    explicit RecordingVerifier(const std::vector<std::uint8_t>& package) {
        const std::size_t signedBytes =
            static_cast<std::size_t>(package[10]) |
            (static_cast<std::size_t>(package[11]) << 8U);
        expectedSigned.assign(package.begin(), package.begin() +
                                                static_cast<std::ptrdiff_t>(signedBytes));
        std::memcpy(expectedKey.data(), package.data() + 48U,
                    expectedKey.size());
        std::memcpy(expectedSignature.data(), package.data() + signedBytes,
                    expectedSignature.size());
    }

    AutomationTrustStatus verify(
        const std::uint8_t* signedBytes, std::size_t signedSize,
        const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId,
        const std::array<std::uint8_t, kAutomationSignatureBytes>& signature)
        override {
        ++calls;
        if (signedSize != expectedSigned.size() ||
            std::memcmp(signedBytes, expectedSigned.data(), signedSize) != 0 ||
            keyId != expectedKey || signature != expectedSignature) {
            return AutomationTrustStatus::InvalidSignature;
        }
        return result;
    }

    AutomationTrustStatus result = AutomationTrustStatus::VerifiedTrusted;
    int calls = 0;
    std::vector<std::uint8_t> expectedSigned;
    std::array<std::uint8_t, kAutomationKeyIdBytes> expectedKey{};
    std::array<std::uint8_t, kAutomationSignatureBytes> expectedSignature{};
};

std::vector<std::uint8_t> validActionPackage() {
    PackageBuilder builder(
        AutomationPackageKind::ActionScript, AutomationTargetClass::Device,
        automationPermission(AutomationPermission::InvokeAction));
    builder.addStep(AutomationOpcode::Delay, 100U);
    builder.addAction("device.info", 500U);
    return builder.finish();
}

AutomationExecutionContext validContext(
    const AutomationInspection& inspection) {
    AutomationExecutionContext context{};
    context.authenticated = true;
    context.grantedPermissions = inspection.requestedPermissions;
    context.targetSelected = true;
    context.selectedTargetClass = inspection.targetClass;
    context.confirmationFresh = true;
    for (std::size_t index = 0U;
         index < context.selectedTargetFingerprint.size(); ++index) {
        context.selectedTargetFingerprint[index] =
            static_cast<std::uint8_t>(index + 7U);
    }
    context.confirmedTargetFingerprint = context.selectedTargetFingerprint;
    return context;
}

void testTrustedActionPackageIsInspectedWithoutExecution() {
    const std::vector<std::uint8_t> package = validActionPackage();
    RecordingVerifier verifier(package);
    const AutomationInspection inspected = inspectAutomationPackage(
        package.data(), package.size(), 1U, &verifier);
    CHECK(inspected.parseStatus == AutomationParseStatus::Parsed);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::Ready);
    CHECK(inspected.trustStatus == AutomationTrustStatus::VerifiedTrusted);
    CHECK(inspected.executionEligible);
    CHECK(inspected.kind == AutomationPackageKind::ActionScript);
    CHECK(inspected.targetClass == AutomationTargetClass::Device);
    CHECK(inspected.declaredSteps == 2U);
    CHECK(inspected.observedSteps == 2U);
    CHECK(inspected.delaySteps == 1U);
    CHECK(inspected.actionSteps == 1U);
    CHECK(inspected.keyboardSteps == 0U);
    CHECK(inspected.pointerSteps == 0U);
    CHECK(inspected.activeEvents == 1U);
    CHECK(inspected.aggregateDurationMs == 600U);
    CHECK(inspected.requestedPermissions == inspected.impliedPermissions);
    CHECK(inspected.actionsInvoked == 0U);
    CHECK(inspected.hidReportsEmitted == 0U);
    CHECK(inspected.resourcesAcquired == 0U);
    CHECK(verifier.calls == 1);
}

void testUsbAndBleKindsDeriveExactPermissions() {
    const std::uint8_t keyboard[] = {0x02U, 0x04U};
    const std::uint8_t pointer[] = {1U, 0xffU, 1U};
    PackageBuilder usb(
        AutomationPackageKind::UsbHid, AutomationTargetClass::UsbHost,
        automationPermission(AutomationPermission::UsbKeyboard) |
            automationPermission(AutomationPermission::UsbPointer));
    usb.addStep(AutomationOpcode::Keyboard, 20U, keyboard, sizeof(keyboard));
    usb.addStep(AutomationOpcode::Pointer, 20U, pointer, sizeof(pointer));
    std::vector<std::uint8_t> usbPackage = usb.finish();
    RecordingVerifier usbVerifier(usbPackage);
    AutomationInspection inspected = inspectAutomationPackage(
        usbPackage.data(), usbPackage.size(), 1U, &usbVerifier);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::Ready);
    CHECK(inspected.targetClass == AutomationTargetClass::UsbHost);
    CHECK(inspected.keyboardSteps == 1U);
    CHECK(inspected.pointerSteps == 1U);

    PackageBuilder ble(
        AutomationPackageKind::BleHid, AutomationTargetClass::BlePeer,
        automationPermission(AutomationPermission::BleKeyboard));
    ble.addStep(AutomationOpcode::Keyboard, 20U, keyboard, sizeof(keyboard));
    std::vector<std::uint8_t> blePackage = ble.finish();
    RecordingVerifier bleVerifier(blePackage);
    inspected = inspectAutomationPackage(
        blePackage.data(), blePackage.size(), 1U, &bleVerifier);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::Ready);
    CHECK(inspected.impliedPermissions ==
          automationPermission(AutomationPermission::BleKeyboard));
    CHECK(inspected.hidReportsEmitted == 0U);
}

void testSignatureStatesNeverBecomeExecutionAuthority() {
    std::vector<std::uint8_t> package = validActionPackage();
    RecordingVerifier verifier(package);
    verifier.result = AutomationTrustStatus::UnknownSigner;
    AutomationInspection inspected = inspectAutomationPackage(
        package.data(), package.size(), 1U, &verifier);
    CHECK(inspected.trustStatus == AutomationTrustStatus::UnknownSigner);
    CHECK(!inspected.executionEligible);

    inspected = inspectAutomationPackage(
        package.data(), package.size(), 1U, nullptr);
    CHECK(inspected.trustStatus == AutomationTrustStatus::VerifierUnavailable);
    CHECK(!inspected.executionEligible);

    const std::size_t signedBytes = package.size() - kAutomationSignatureBytes;
    std::memset(package.data() + signedBytes, 0, kAutomationSignatureBytes);
    RecordingVerifier missingVerifier(package);
    inspected = inspectAutomationPackage(
        package.data(), package.size(), 1U, &missingVerifier);
    CHECK(inspected.trustStatus == AutomationTrustStatus::MissingSignature);
    CHECK(missingVerifier.calls == 0);
    CHECK(!inspected.executionEligible);
}

void testMutationAndFramingFailClosed() {
    const std::vector<std::uint8_t> valid = validActionPackage();
    RecordingVerifier exactVerifier(valid);
    std::vector<std::uint8_t> changed = valid;
    changed[64U + 4U] ^= 1U;
    AutomationInspection inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, &exactVerifier);
    CHECK(inspected.trustStatus == AutomationTrustStatus::InvalidSignature);
    CHECK(!inspected.executionEligible);

    inspected = inspectAutomationPackage(nullptr, valid.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidArgument);
    inspected = inspectAutomationPackage(valid.data(), valid.size(), 0U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidArgument);
    inspected = inspectAutomationPackage(valid.data(), 12U, 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::TooSmall);

    changed = valid;
    changed[0] = 'X';
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidMagic);
    changed = valid;
    changed[4] = 2U;
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus ==
          AutomationParseStatus::UnsupportedWireVersion);
    changed = valid;
    changed[6] = 2U;
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus ==
          AutomationParseStatus::UnsupportedSignatureAlgorithm);
    changed = valid;
    changed[56] = 1U;
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidHeader);
    changed = valid;
    put16(&changed, 8U, static_cast<std::uint16_t>(changed.size() - 1U));
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::LengthMismatch);
    changed = valid;
    std::fill(changed.begin() + 32, changed.begin() + 48, 0U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidIdentity);
    changed = valid;
    changed[64] = 0xffU;
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::InvalidStep);

    RecordingVerifier mutationVerifier(valid);
    for (std::size_t index = 0U; index < valid.size(); ++index) {
        changed = valid;
        changed[index] ^= 1U;
        inspected = inspectAutomationPackage(
            changed.data(), changed.size(), 1U, &mutationVerifier);
        CHECK(!inspected.executionEligible);
    }
    for (std::size_t size = 0U; size < valid.size(); ++size) {
        inspected = inspectAutomationPackage(valid.data(), size, 1U, nullptr);
        CHECK(!inspected.executionEligible);
    }
    changed = valid;
    changed.push_back(0U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::LengthMismatch);
    changed.resize(kAutomationMaximumPackageBytes + 1U, 0U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.parseStatus == AutomationParseStatus::TooLarge);
}

void testPolicyRejectsPrivilegeKindAndBounds() {
    const std::vector<std::uint8_t> valid = validActionPackage();
    std::vector<std::uint8_t> changed = valid;
    put16(&changed, 14U, 2U);
    AutomationInspection inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::IncompatibleApi);

    changed = valid;
    changed[7] = static_cast<std::uint8_t>(AutomationTargetClass::UsbHost);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::InvalidKindTarget);
    changed = valid;
    put32(&changed, 16U, 1U << 30U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::UnknownPermission);
    changed = valid;
    put32(&changed, 16U,
          automationPermission(AutomationPermission::InvokeAction) |
              automationPermission(AutomationPermission::UsbKeyboard));
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::PermissionMismatch);
    changed = valid;
    put32(&changed, 20U, 999U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::InvalidRuntime);
    changed = valid;
    put16(&changed, 24U, 0U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::InvalidEventCeiling);
    changed = valid;
    put16(&changed, 26U, kAutomationMaximumOutputBytes + 1U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::InvalidOutputCeiling);
    changed = valid;
    put16(&changed, 28U, 3U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::InvalidStepCount);
    changed = valid;
    put32(&changed, 20U, 1000U);
    put32(&changed, 64U + 4U, 800U);
    put32(&changed, 72U + 4U, 800U);
    inspected = inspectAutomationPackage(
        changed.data(), changed.size(), 1U, nullptr);
    CHECK(inspected.policyStatus == AutomationPolicyStatus::RuntimeExceeded);
}

void testAdmissionOrderBindsAuthenticationPermissionAndTarget() {
    const std::vector<std::uint8_t> package = validActionPackage();
    RecordingVerifier verifier(package);
    const AutomationInspection inspected = inspectAutomationPackage(
        package.data(), package.size(), 1U, &verifier);
    AutomationExecutionContext context = validContext(inspected);
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::Ready);

    AutomationInspection invalid = inspected;
    invalid.parseStatus = AutomationParseStatus::InvalidStep;
    CHECK(admitAutomationExecution(invalid, context) ==
          AutomationAdmissionStatus::PackageInvalid);
    invalid = inspected;
    invalid.policyStatus = AutomationPolicyStatus::PermissionMismatch;
    CHECK(admitAutomationExecution(invalid, context) ==
          AutomationAdmissionStatus::PolicyRejected);
    invalid = inspected;
    invalid.trustStatus = AutomationTrustStatus::InvalidSignature;
    invalid.executionEligible = false;
    CHECK(admitAutomationExecution(invalid, context) ==
          AutomationAdmissionStatus::SignatureRequired);

    context = validContext(inspected);
    context.authenticated = false;
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::AuthenticationRequired);
    context = validContext(inspected);
    context.grantedPermissions |=
        automationPermission(AutomationPermission::UsbKeyboard);
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::PermissionDenied);
    context = validContext(inspected);
    context.targetSelected = false;
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::TargetRequired);
    context = validContext(inspected);
    context.selectedTargetClass = AutomationTargetClass::UsbHost;
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::TargetMismatch);
    context = validContext(inspected);
    context.confirmationFresh = false;
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::ConfirmationRequired);
    context = validContext(inspected);
    context.confirmedTargetFingerprint[4] ^= 1U;
    CHECK(admitAutomationExecution(inspected, context) ==
          AutomationAdmissionStatus::ConfirmationMismatch);
}

void testPassiveInspectorRetainsSummaryButNeverPackageBytes() {
    const std::vector<std::uint8_t> package = validActionPackage();
    AutomationInspectorController controller;
    CHECK(controller.inspect("owned-check.lhau",
                             static_cast<std::uint32_t>(package.size()),
                             package.data(), package.size(), 1U, nullptr));
    const AutomationInspectorModel& model = controller.model();
    CHECK(model.sourceStatus == AutomationInspectorSourceStatus::Inspected);
    CHECK(std::strcmp(model.sourceName.data(), "owned-check.lhau") == 0);
    CHECK(model.sourceSize == package.size());
    CHECK(model.inspection.parseStatus == AutomationParseStatus::Parsed);
    CHECK(model.inspection.policyStatus == AutomationPolicyStatus::Ready);
    CHECK(model.inspection.trustStatus ==
          AutomationTrustStatus::VerifierUnavailable);
    CHECK(!model.inspection.executionEligible);
    CHECK(model.inspection.actionsInvoked == 0U);
    CHECK(model.inspection.hidReportsEmitted == 0U);
    CHECK(model.inspection.resourcesAcquired == 0U);

    const std::uint32_t inspectedRevision = model.revision;
    controller.clear();
    CHECK(controller.model().sourceStatus ==
          AutomationInspectorSourceStatus::Empty);
    CHECK(controller.model().sourceName[0] == '\0');
    CHECK(controller.model().sourceSize == 0U);
    CHECK(controller.model().revision != inspectedRevision);
}

void testInspectorCatalogAndSourceFailuresAreBounded() {
    AutomationPackageCatalog catalog;
    CHECK(catalog.add("z-last.LHAU", 64U));
    CHECK(catalog.add("a-first.lhau", 128U));
    CHECK(!catalog.add("../escape.lhau", 128U));
    CHECK(!catalog.add("not-a-package.bin", 128U));
    CHECK(!catalog.add("a-first.lhau", 128U));
    CHECK(catalog.size() == 2U);
    CHECK(std::strcmp(catalog.get(0U)->name.data(), "a-first.lhau") == 0);
    CHECK(std::strcmp(catalog.get(1U)->name.data(), "z-last.LHAU") == 0);
    CHECK(catalog.selected() == catalog.get(0U));
    CHECK(catalog.next());
    CHECK(catalog.selected() == catalog.get(1U));
    CHECK(!catalog.next());
    CHECK(catalog.previous());
    CHECK(!catalog.previous());
    CHECK(catalog.add("b.lhau", 0U));
    CHECK(catalog.add("c.lhau", 1U));
    CHECK(catalog.add("d.lhau", 2U));
    CHECK(!catalog.add("z-omitted.lhau", 2U));
    CHECK(catalog.add("00-earliest.lhau", 3U));
    CHECK(catalog.size() == AutomationPackageCatalog::kCapacity);
    CHECK(std::strcmp(catalog.get(0U)->name.data(), "00-earliest.lhau") == 0);
    CHECK(std::strcmp(catalog.get(3U)->name.data(), "c.lhau") == 0);

    AutomationInspectorController controller;
    CHECK(controller.rejectSource(
        "large.lhau", kAutomationMaximumPackageBytes + 1U,
        AutomationInspectorSourceStatus::TooLarge));
    CHECK(controller.model().sourceStatus ==
          AutomationInspectorSourceStatus::TooLarge);
    CHECK(controller.model().inspection.parseStatus ==
          AutomationParseStatus::TooLarge);
    CHECK(!controller.model().inspection.executionEligible);
    CHECK(controller.rejectSource(
        "broken.lhau", 100U,
        AutomationInspectorSourceStatus::ReadFailed));
    CHECK(controller.model().sourceStatus ==
          AutomationInspectorSourceStatus::ReadFailed);
    CHECK(!controller.rejectSource(
        "empty.lhau", 0U, AutomationInspectorSourceStatus::Empty));
    CHECK(!controller.inspect("bad/name.lhau", 0U, nullptr, 0U, 1U,
                              nullptr));
}

}  // namespace

int main() {
    testTrustedActionPackageIsInspectedWithoutExecution();
    testUsbAndBleKindsDeriveExactPermissions();
    testSignatureStatesNeverBecomeExecutionAuthority();
    testMutationAndFramingFailClosed();
    testPolicyRejectsPrivilegeKindAndBounds();
    testAdmissionOrderBindsAuthenticationPermissionAndTarget();
    testPassiveInspectorRetainsSummaryButNeverPackageBytes();
    testInspectorCatalogAndSourceFailuresAreBounded();
    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "automation package inspection/admission tests passed\n";
    return EXIT_SUCCESS;
}
