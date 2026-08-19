#pragma once

#include <cstddef>
#include <cstdint>

#include "drivers/radio/Cc1101PassiveSpectrum.h"

namespace leshy1::platform::arduino {

// Explicit user-started receive-only CC1101 spectrum adapter. Only SRES, SRX and
// SIDLE command strobes are representable; PA-table, FIFO and TX paths are absent.
class BoardCc1101PassiveSpectrum final {
public:
    ~BoardCc1101PassiveSpectrum() { end(); }

    bool begin(
        bool radioSpiOwned,
        drivers::radio::Cc1101PassiveSpectrumReport* report);
    bool sample(
        const drivers::radio::Cc1101PassiveSpectrumPlan& plan,
        std::size_t bin,
        drivers::radio::Cc1101PassiveSample* output);
    // Lock the same receive-only adapter to one tunable frequency and expose
    // bounded RSSI envelope samples. No FIFO, PA table or TX strobe exists.
    bool lockReceive(std::uint32_t frequencyKHz);
    bool sampleRssi(std::int16_t* rssiDbm, std::uint64_t* monotonicUs);
    bool idle();
    bool end();

    bool active() const { return active_; }

private:
    enum class ReceiveWaitResult : std::uint8_t {
        Ready,
        Timeout,
        Fault,
    };

    std::uint8_t transfer(std::uint8_t value);
    bool selectCc();
    void deselectCc();
    bool command(std::uint8_t value);
    bool writeRegister(std::uint8_t address, std::uint8_t value);
    bool readStatus(std::uint8_t address, std::uint8_t* value);
    bool resetReceiver();
    bool configureReceive();
    bool tune(std::uint32_t frequencyKHz);
    bool sampleAtFrequency(
        const drivers::radio::Cc1101PassiveSpectrumPlan& plan,
        std::uint32_t frequencyKHz, std::uint8_t* rawRssi);
    bool recoverReceive();
    ReceiveWaitResult waitForReceive(std::uint16_t timeoutUs);
    bool gpio21Safe() const;
    void holdTransmitPathsInactive();
    void cleanupPinsAndSpi();

    drivers::radio::Cc1101PassiveSpectrumReport* report_ = nullptr;
    bool spiStarted_ = false;
    bool transactionOpen_ = false;
    bool active_ = false;
};

}  // namespace leshy1::platform::arduino
