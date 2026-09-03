#pragma once

#include <Arduino.h>
#include <TFT_eSPI.h>

#include <cstdint>

#include "ui/TouchInput.h"

namespace leshy1::platform::arduino {

enum class TouchCalibrationSource : std::uint8_t {
    None,
    Leshy1,
    Legacy0x,
    DefaultProfile,
};

const char* touchCalibrationSourceName(TouchCalibrationSource source);

class BoardTouchInput final {
public:
    bool begin(TFT_eSPI& display, std::uint32_t nowMs);
    bool poll(std::uint32_t nowMs, ui::TouchPoint* press);
    bool calibrateAndSave(std::uint32_t nowMs);
    std::uint16_t rawPressure();

    bool ready() const { return display_ != nullptr && calibrated_; }
    bool pressed() const { return input_.pressed(); }
    static constexpr std::uint16_t pressureThreshold() {
        return kPressureThreshold;
    }
    static constexpr std::uint16_t candidatePressureThreshold() {
        return kCandidatePressureThreshold;
    }
    const std::uint16_t* calibration() const { return calibration_; }
    TouchCalibrationSource calibrationSource() const { return source_; }
    const ui::TouchInputMetrics& metrics() const { return input_.metrics(); }

private:
    static constexpr const char* kPreferencesNamespace = "leshy1-ui";
    static constexpr const char* kCalibrationKey = "touch.v1";
    static constexpr const char* kLegacyNamespace = "leshy";
    static constexpr const char* kLegacyCalibrationKey = "tcal";
    // Board-01 idle pressure is 3..14. Calibration uses 175 internally; 80
    // retains ample noise margin while accepting normal finger pressure.
    static constexpr std::uint16_t kPressureThreshold = 80;
    // A fresh resistive contact ramps through values below the validation
    // threshold. Use 20 only to start TFT_eSPI's bounded five-sample
    // validator; no coordinate or action is accepted below 80. This preserves
    // the idle fast path while preventing a light first tap after a long idle
    // from being discarded before validation has a chance to observe it.
    static constexpr std::uint16_t kCandidatePressureThreshold = 20;
    static constexpr std::uint16_t kDefaultCalibration[5] = {
        300, 3600, 300, 3600, 3,
    };

    static bool validCalibration(const std::uint16_t* calibration);
    bool load(const char* name, const char* key,
              TouchCalibrationSource source);

    TFT_eSPI* display_ = nullptr;
    ui::TouchInput input_{};
    std::uint16_t calibration_[5] = {};
    TouchCalibrationSource source_ = TouchCalibrationSource::None;
    bool calibrated_ = false;
};

}  // namespace leshy1::platform::arduino
