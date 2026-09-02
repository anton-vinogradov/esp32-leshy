#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/lab/InfraredReplay.h"

namespace leshy1::platform::arduino {

enum class InfraredTransmitterStatus : std::uint8_t {
    NotStarted,
    Running,
    Complete,
    RefusedProfile,
    RefusedOwnership,
    RefusedSafety,
    InvalidPlan,
    DriverFault,
    CleanupFailed,
};

struct InfraredTransmitterReport final {
    InfraredTransmitterStatus status = InfraredTransmitterStatus::NotStarted;
    bool profileDeclared = false;
    bool resourceOwned = false;
    bool safetyArmed = false;
    bool singleShot = true;
    bool outputInactive = true;
    bool cleanupComplete = true;
    std::uint32_t plannedDurationUs = 0U;
    std::uint32_t transmissions = 0U;
};

class BoardInfraredTransmitter final
    : public apps::lab::InfraredReplayOutput {
public:
    ~BoardInfraredTransmitter() override { stop(); }

    void admit(bool radioSpiOwned, bool safetyArmed,
               InfraredTransmitterReport* report);
    bool begin(const apps::lab::InfraredReplayPlan& plan,
               std::uint64_t startedUs) override;
    apps::lab::InfraredReplayOutputState service(
        std::uint64_t nowUs) override;
    bool stop() override;
    bool inactive() const override;

private:
    static constexpr std::size_t kSymbolCapacity = 34U;

    bool prepareSymbols(const apps::lab::InfraredReplayPlan& plan);
    bool cleanup();

    InfraredTransmitterReport* report_ = nullptr;
    void* channel_ = nullptr;
    void* encoder_ = nullptr;
    std::array<std::uint32_t, kSymbolCapacity> symbols_{};
    std::size_t symbolCount_ = 0U;
    bool admittedRadioSpi_ = false;
    bool admittedSafety_ = false;
    bool enabled_ = false;
    bool running_ = false;
};

}  // namespace leshy1::platform::arduino
