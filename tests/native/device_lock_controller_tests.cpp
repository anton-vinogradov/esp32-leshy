#include <cstdlib>
#include <cstring>
#include <iostream>

#include "apps/device/DeviceLockController.h"

namespace {

int failures = 0;

#define CHECK(expression)                                                     \
    do {                                                                      \
        if (!(expression)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__                          \
                      << ": check failed: " #expression << '\n';             \
            ++failures;                                                       \
        }                                                                     \
    } while (false)

using leshy1::apps::device::DeviceLockActivation;
using leshy1::apps::device::DeviceLockController;
using leshy1::apps::device::DeviceLockIntent;
using leshy1::apps::device::DeviceLockSubmission;
using leshy1::apps::device::DeviceLockUiOutcome;
using leshy1::apps::device::DeviceLockView;
using leshy1::services::security::DeviceLockAudit;
using leshy1::services::security::DeviceLockFailure;
using leshy1::services::security::DeviceLockState;

DeviceLockAudit audit(DeviceLockState state,
                      DeviceLockFailure failure = DeviceLockFailure::None) {
    DeviceLockAudit value{};
    value.state = state;
    value.lastFailure = failure;
    value.protectedAccessAllowed = state == DeviceLockState::Unlocked ||
        state == DeviceLockState::Disabled;
    return value;
}

void enterDigits(DeviceLockController& controller, const char* digits) {
    for (std::size_t index = 0;
         index < DeviceLockController::kProductPinDigits; ++index) {
        for (int value = 0; value < digits[index] - '0'; ++value) {
            CHECK(controller.nextDigit());
        }
        CHECK(controller.advance());
    }
}

void testConfigureRequiresStrongMatchingConfirmationAndClearsSubmission() {
    DeviceLockController controller;
    controller.enter(audit(DeviceLockState::Unconfigured));
    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    CHECK(controller.view() == DeviceLockView::EnterPin);
    CHECK(controller.intent() == DeviceLockIntent::Configure);

    enterDigits(controller, "120394");
    CHECK(controller.view() == DeviceLockView::ConfirmPin);
    enterDigits(controller, "120394");
    CHECK(controller.view() == DeviceLockView::Working);
    CHECK(controller.submissionReady());

    DeviceLockSubmission submission;
    CHECK(controller.takeSubmission(&submission));
    CHECK(submission.intent == DeviceLockIntent::Configure);
    CHECK(submission.pinLength == 6U);
    CHECK(std::strcmp(submission.pin.data(), "120394") == 0);
    CHECK(!controller.takeSubmission(&submission));
    submission.clear();

    controller.complete(audit(DeviceLockState::Unlocked), true);
    CHECK(controller.view() == DeviceLockView::Status);
    CHECK(controller.outcome() == DeviceLockUiOutcome::Configured);
    CHECK(controller.audit().protectedAccessAllowed);
}

void testWeakAndMismatchedPinNeverProduceSubmission() {
    DeviceLockController controller;
    controller.enter(audit(DeviceLockState::Unconfigured));
    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    enterDigits(controller, "000000");
    CHECK(controller.view() == DeviceLockView::Status);
    CHECK(controller.outcome() == DeviceLockUiOutcome::WeakPin);
    CHECK(!controller.submissionReady());

    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    enterDigits(controller, "120394");
    enterDigits(controller, "120395");
    CHECK(controller.view() == DeviceLockView::Status);
    CHECK(controller.outcome() == DeviceLockUiOutcome::PinMismatch);
    CHECK(!controller.submissionReady());
}

void testUnlockCancelRetryAndImmediateLockIntent() {
    DeviceLockController controller;
    controller.enter(audit(DeviceLockState::Locked));
    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    CHECK(controller.nextDigit());
    CHECK(controller.previousDigit());
    CHECK(controller.cancel());
    CHECK(controller.view() == DeviceLockView::Status);
    CHECK(!controller.submissionReady());

    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    enterDigits(controller, "120394");
    DeviceLockSubmission submission;
    CHECK(controller.takeSubmission(&submission));
    CHECK(submission.intent == DeviceLockIntent::Unlock);
    submission.clear();
    controller.complete(
        audit(DeviceLockState::RetryDelay, DeviceLockFailure::WrongPin), false);
    CHECK(controller.outcome() == DeviceLockUiOutcome::Failed);
    CHECK(controller.activate() == DeviceLockActivation::None);

    controller.enter(audit(DeviceLockState::Unlocked));
    CHECK(controller.activate() == DeviceLockActivation::LockRequested);
    controller.noteLocked(audit(DeviceLockState::Locked));
    CHECK(controller.outcome() == DeviceLockUiOutcome::Locked);
}

void testDisableRequiresSeparateSelectionAndConfirmation() {
    DeviceLockController controller;
    controller.enter(audit(DeviceLockState::Unlocked));
    CHECK(controller.actionSelection() == 0U);
    CHECK(!controller.previousAction());
    CHECK(controller.nextAction());
    CHECK(controller.actionSelection() == 1U);
    CHECK(!controller.nextAction());
    CHECK(controller.activate() ==
          DeviceLockActivation::DisableConfirmationOpened);
    CHECK(controller.view() == DeviceLockView::ConfirmDisable);
    CHECK(controller.cancel());
    CHECK(controller.view() == DeviceLockView::Status);

    CHECK(controller.actionSelection() == 1U);
    CHECK(controller.activate() ==
          DeviceLockActivation::DisableConfirmationOpened);
    CHECK(controller.activate() == DeviceLockActivation::DisableRequested);
    controller.noteDisabled(audit(DeviceLockState::Disabled), true);
    CHECK(controller.view() == DeviceLockView::Status);
    CHECK(controller.outcome() == DeviceLockUiOutcome::Disabled);

    CHECK(controller.activate() == DeviceLockActivation::EditorOpened);
    CHECK(controller.intent() == DeviceLockIntent::Configure);
}

}  // namespace

int main() {
    testConfigureRequiresStrongMatchingConfirmationAndClearsSubmission();
    testWeakAndMismatchedPinNeverProduceSubmission();
    testUnlockCancelRetryAndImmediateLockIntent();
    testDisableRequiresSeparateSelectionAndConfirmation();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "Device Lock UI controller tests passed\n";
    return EXIT_SUCCESS;
}
