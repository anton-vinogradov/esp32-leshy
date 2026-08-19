#pragma once

namespace leshy1::platform::arduino {

// Establishes fail-safe levels for board outputs that must never float during
// normal runtime. This adapter is deliberately separate from feature code so
// static checks can prove that no app drives the buzzer directly.
class BoardSafeOutputs final {
public:
    static void establishBootInvariant();
    static void emergencyQuiesce();
    static bool buzzerHeldInactive();
    static bool radioTransmitPathsHeldInactive();
};

}  // namespace leshy1::platform::arduino
