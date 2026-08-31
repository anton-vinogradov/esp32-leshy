#include "DeviceLockController.h"

#include <cstring>

namespace leshy1::apps::device {

void DeviceLockSubmission::clear() {
    volatile char* cursor = pin.data();
    for (std::size_t index = 0; index < pin.size(); ++index) {
        cursor[index] = '\0';
    }
    pinLength = 0;
    intent = DeviceLockIntent::None;
}

void DeviceLockController::secureClear(char* bytes, std::size_t size) {
    volatile char* cursor = bytes;
    while (size-- != 0U) *cursor++ = '\0';
}

void DeviceLockController::resetEditor() {
    secureClear(pin_.data(), pin_.size());
    secureClear(firstPin_.data(), firstPin_.size());
    submission_.clear();
    for (std::size_t index = 0; index < kProductPinDigits; ++index) {
        pin_[index] = '0';
    }
    cursor_ = 0;
    submissionReady_ = false;
}

void DeviceLockController::enter(
    const services::security::DeviceLockAudit& audit) {
    resetEditor();
    audit_ = audit;
    view_ = DeviceLockView::Status;
    intent_ = DeviceLockIntent::None;
    outcome_ = DeviceLockUiOutcome::None;
    actionSelection_ = 0;
}

DeviceLockActivation DeviceLockController::activate() {
    if (view_ == DeviceLockView::ConfirmDisable) {
        return DeviceLockActivation::DisableRequested;
    }
    if (view_ != DeviceLockView::Status) return DeviceLockActivation::None;
    resetEditor();
    outcome_ = DeviceLockUiOutcome::None;
    if (audit_.state == services::security::DeviceLockState::Unconfigured ||
        audit_.state == services::security::DeviceLockState::Disabled) {
        intent_ = DeviceLockIntent::Configure;
        view_ = DeviceLockView::EnterPin;
        return DeviceLockActivation::EditorOpened;
    }
    if (audit_.state == services::security::DeviceLockState::Locked) {
        intent_ = DeviceLockIntent::Unlock;
        view_ = DeviceLockView::EnterPin;
        return DeviceLockActivation::EditorOpened;
    }
    if (audit_.state == services::security::DeviceLockState::Unlocked) {
        if (actionSelection_ == 0U) {
            return DeviceLockActivation::LockRequested;
        }
        view_ = DeviceLockView::ConfirmDisable;
        return DeviceLockActivation::DisableConfirmationOpened;
    }
    return DeviceLockActivation::None;
}

bool DeviceLockController::previousAction() {
    if (view_ != DeviceLockView::Status ||
        audit_.state != services::security::DeviceLockState::Unlocked ||
        actionSelection_ == 0U) {
        return false;
    }
    --actionSelection_;
    return true;
}

bool DeviceLockController::nextAction() {
    if (view_ != DeviceLockView::Status ||
        audit_.state != services::security::DeviceLockState::Unlocked ||
        actionSelection_ + 1U >= kUnlockedActionCount) {
        return false;
    }
    ++actionSelection_;
    return true;
}

bool DeviceLockController::previousDigit() {
    if (view_ != DeviceLockView::EnterPin &&
        view_ != DeviceLockView::ConfirmPin) return false;
    pin_[cursor_] = pin_[cursor_] == '0'
        ? '9' : static_cast<char>(pin_[cursor_] - 1);
    return true;
}

bool DeviceLockController::nextDigit() {
    if (view_ != DeviceLockView::EnterPin &&
        view_ != DeviceLockView::ConfirmPin) return false;
    pin_[cursor_] = pin_[cursor_] == '9'
        ? '0' : static_cast<char>(pin_[cursor_] + 1);
    return true;
}

bool DeviceLockController::finishEntry() {
    if (view_ == DeviceLockView::EnterPin &&
        intent_ == DeviceLockIntent::Configure) {
        if (services::security::DeviceLock::pinWeak(
                pin_.data(), kProductPinDigits)) {
            outcome_ = DeviceLockUiOutcome::WeakPin;
            resetEditor();
            view_ = DeviceLockView::Status;
            intent_ = DeviceLockIntent::None;
            return true;
        }
        std::memcpy(firstPin_.data(), pin_.data(), kProductPinDigits);
        secureClear(pin_.data(), pin_.size());
        for (std::size_t index = 0; index < kProductPinDigits; ++index) {
            pin_[index] = '0';
        }
        cursor_ = 0;
        view_ = DeviceLockView::ConfirmPin;
        return true;
    }

    if (view_ == DeviceLockView::ConfirmPin &&
        std::memcmp(firstPin_.data(), pin_.data(), kProductPinDigits) != 0) {
        outcome_ = DeviceLockUiOutcome::PinMismatch;
        resetEditor();
        view_ = DeviceLockView::Status;
        intent_ = DeviceLockIntent::None;
        return true;
    }

    submission_.clear();
    submission_.intent = intent_;
    submission_.pinLength = kProductPinDigits;
    const char* source = view_ == DeviceLockView::ConfirmPin
        ? firstPin_.data() : pin_.data();
    std::memcpy(submission_.pin.data(), source, kProductPinDigits);
    submission_.pin[kProductPinDigits] = '\0';
    secureClear(pin_.data(), pin_.size());
    secureClear(firstPin_.data(), firstPin_.size());
    submissionReady_ = true;
    cursor_ = 0;
    view_ = DeviceLockView::Working;
    return true;
}

bool DeviceLockController::advance() {
    if (view_ != DeviceLockView::EnterPin &&
        view_ != DeviceLockView::ConfirmPin) return false;
    if (cursor_ + 1U < kProductPinDigits) {
        ++cursor_;
        return true;
    }
    return finishEntry();
}

bool DeviceLockController::cancel() {
    if (view_ == DeviceLockView::Status ||
        view_ == DeviceLockView::Working) return false;
    resetEditor();
    intent_ = DeviceLockIntent::None;
    outcome_ = DeviceLockUiOutcome::None;
    view_ = DeviceLockView::Status;
    return true;
}

bool DeviceLockController::takeSubmission(DeviceLockSubmission* output) {
    if (output == nullptr || !submissionReady_ ||
        view_ != DeviceLockView::Working) return false;
    output->clear();
    output->intent = submission_.intent;
    output->pinLength = submission_.pinLength;
    std::memcpy(output->pin.data(), submission_.pin.data(),
                submission_.pinLength + 1U);
    submission_.clear();
    submissionReady_ = false;
    return true;
}

void DeviceLockController::complete(
    const services::security::DeviceLockAudit& audit, bool success) {
    resetEditor();
    audit_ = audit;
    if (success) {
        outcome_ = intent_ == DeviceLockIntent::Configure
            ? DeviceLockUiOutcome::Configured
            : DeviceLockUiOutcome::Unlocked;
    } else {
        outcome_ = DeviceLockUiOutcome::Failed;
    }
    intent_ = DeviceLockIntent::None;
    view_ = DeviceLockView::Status;
}

void DeviceLockController::noteLocked(
    const services::security::DeviceLockAudit& audit) {
    resetEditor();
    audit_ = audit;
    intent_ = DeviceLockIntent::None;
    outcome_ = DeviceLockUiOutcome::Locked;
    view_ = DeviceLockView::Status;
}

void DeviceLockController::noteDisabled(
    const services::security::DeviceLockAudit& audit, bool success) {
    resetEditor();
    audit_ = audit;
    intent_ = DeviceLockIntent::None;
    outcome_ = success ? DeviceLockUiOutcome::Disabled
                       : DeviceLockUiOutcome::Failed;
    view_ = DeviceLockView::Status;
    actionSelection_ = 0;
}

}  // namespace leshy1::apps::device
