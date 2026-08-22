#pragma once

#include <cstdint>

namespace leshy1::platform::arduino {

enum class InfraredReceiverStatus : std::uint8_t {
    NotStarted,
    Ready,
    RefusedProfile,
    Busy,
    Fault,
    CleanupFailed,
};

struct InfraredReceiverReport final {
    InfraredReceiverStatus status = InfraredReceiverStatus::NotStarted;
    bool profileDeclared = false;
    bool resourceOwned = false;
    bool rxOnly = true;
    bool txHeldLow = true;
    bool nrfCeHeldLow = true;
    bool gpio21Input = false;
    bool cleanupComplete = true;
    std::uint32_t samples = 0;
    std::uint32_t transitions = 0;
};

class BoardInfraredReceiver final {
public:
    ~BoardInfraredReceiver() { end(); }

    bool begin(bool radioSpiOwned, InfraredReceiverReport* report,
               bool* initialLevel, std::uint64_t* startedUs);
    bool sample(bool* level, std::uint64_t* sampledUs);
    bool end();
    bool active() const { return active_; }

private:
    bool safeLevels() const;

    InfraredReceiverReport* report_ = nullptr;
    bool active_ = false;
    bool lastLevel_ = true;
};

}  // namespace leshy1::platform::arduino
