#include "platform/arduino/BoardTouchInput.h"

#include <Preferences.h>

#include "ui/VisualTheme.h"

namespace leshy1::platform::arduino {

const char* touchCalibrationSourceName(TouchCalibrationSource source) {
    switch (source) {
        case TouchCalibrationSource::Leshy1: return "leshy1";
        case TouchCalibrationSource::Legacy0x: return "legacy_0x";
        case TouchCalibrationSource::DefaultProfile: return "default_profile";
        case TouchCalibrationSource::None: return "none";
    }
    return "none";
}

bool BoardTouchInput::validCalibration(const std::uint16_t* calibration) {
    if (calibration == nullptr || calibration[4] > 7U) return false;
    for (std::uint8_t index = 0; index < 4; ++index) {
        if (calibration[index] == 0 || calibration[index] > 4095U) return false;
    }
    return calibration[1] >= 256U && calibration[3] >= 256U;
}

bool BoardTouchInput::load(const char* name, const char* key,
                           TouchCalibrationSource source) {
    Preferences preferences;
    if (!preferences.begin(name, true)) return false;
    const std::size_t bytes = preferences.getBytes(
        key, calibration_, sizeof(calibration_));
    preferences.end();
    if (bytes != sizeof(calibration_) || !validCalibration(calibration_)) {
        return false;
    }
    display_->setTouch(calibration_);
    source_ = source;
    calibrated_ = true;
    return true;
}

bool BoardTouchInput::begin(TFT_eSPI& display, std::uint32_t nowMs) {
    display_ = &display;
    input_.reset(nowMs);
    source_ = TouchCalibrationSource::None;
    calibrated_ = false;
    if (load(kPreferencesNamespace, kCalibrationKey,
             TouchCalibrationSource::Leshy1) ||
        load(kLegacyNamespace, kLegacyCalibrationKey,
             TouchCalibrationSource::Legacy0x)) {
        return true;
    }
    for (std::uint8_t index = 0; index < 5; ++index) {
        calibration_[index] = kDefaultCalibration[index];
    }
    display_->setTouch(calibration_);
    source_ = TouchCalibrationSource::DefaultProfile;
    calibrated_ = true;
    return true;
}

bool BoardTouchInput::poll(std::uint32_t nowMs, ui::TouchPoint* press) {
    if (!ready()) return false;
    std::uint16_t x = 0;
    std::uint16_t y = 0;
    // TFT_eSPI::getTouch() performs five validated samples and delays after
    // every pressure read, even while the panel is untouched.  On this board
    // that stalls the foreground loop for about 13 ms, which is longer than
    // one pixel-row period of the live waterfall.  A single raw-Z transaction
    // is enough to reject the overwhelmingly common idle case.  Keep the
    // library's full validation for every plausible press. A new contact can
    // ramp through 20..80 between loop iterations, so the cheap candidate
    // gate must be lower than the acceptance gate. Coordinates still require
    // the original 80 threshold; only a validated ongoing press uses the
    // library's 20 continuation threshold.
    const std::uint16_t validationThreshold = input_.pressed()
        ? kCandidatePressureThreshold : kPressureThreshold;
    const bool pressurePresent =
        display_->getTouchRawZ() > kCandidatePressureThreshold;
    const bool touched = pressurePresent &&
        display_->getTouch(&x, &y, validationThreshold) != 0;
    return input_.sample(touched, x, y, nowMs, press);
}

bool BoardTouchInput::calibrateAndSave(std::uint32_t nowMs) {
    if (display_ == nullptr) return false;
    display_->calibrateTouch(calibration_, ui::visual::Palette::TextPrimary,
                             ui::visual::Palette::Canvas, 18);
    if (!validCalibration(calibration_)) return false;
    Preferences preferences;
    if (!preferences.begin(kPreferencesNamespace, false)) return false;
    const std::size_t written = preferences.putBytes(
        kCalibrationKey, calibration_, sizeof(calibration_));
    preferences.end();
    if (written != sizeof(calibration_)) return false;
    display_->setTouch(calibration_);
    source_ = TouchCalibrationSource::Leshy1;
    calibrated_ = true;
    input_.reset(nowMs);
    return true;
}

std::uint16_t BoardTouchInput::rawPressure() {
    return display_ == nullptr ? 0 : display_->getTouchRawZ();
}

}  // namespace leshy1::platform::arduino
