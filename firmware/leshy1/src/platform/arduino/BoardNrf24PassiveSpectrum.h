#pragma once

#include <cstdint>

#include "drivers/radio/Nrf24PassiveSpectrum.h"

namespace leshy1::platform::arduino {

// Explicit user-started receive-only nRF24 spectrum adapter. Slot 3 stays gated,
// every CE-high interval follows a verified PWR_UP|PRIM_RX configuration, and
// no payload/TX opcode is exposed by this type.
class BoardNrf24PassiveSpectrum final {
public:
    ~BoardNrf24PassiveSpectrum() { end(); }

    bool begin(
        bool radioSpiOwned,
        const drivers::radio::Nrf24PassiveSpectrumPlan& plan,
        drivers::radio::Nrf24PassiveSpectrumReport* report);
    bool sweep(drivers::radio::Nrf24PassiveSweep* output);
    bool end();

    bool active() const { return active_; }
    const drivers::radio::Nrf24PassiveSpectrumPlan& plan() const {
        return plan_;
    }

private:
    std::uint8_t transfer(std::uint8_t value);
    std::uint8_t readRegister(std::uint8_t module, std::uint8_t reg,
                              std::uint8_t* status = nullptr);
    void writeRegister(std::uint8_t module, std::uint8_t reg,
                       std::uint8_t value);
    bool gpio21Safe() const;
    void holdAllCeLow();
    bool configureReceive(std::uint8_t module);
    void cleanupPinsAndSpi();

    drivers::radio::Nrf24PassiveSpectrumPlan plan_{};
    drivers::radio::Nrf24PassiveSpectrumReport* report_ = nullptr;
    bool spiStarted_ = false;
    bool transactionOpen_ = false;
    bool active_ = false;
};

}  // namespace leshy1::platform::arduino
