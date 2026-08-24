#pragma once

#include <cstddef>
#include <cstdint>

#include "domain/captures/SubGhzRaw.h"
#include "drivers/radio/Cc1101PassiveSpectrum.h"

namespace leshy1::platform::arduino {

// Explicit user-started receive-only CC1101 spectrum adapter. Only SRES, SRX and
// SIDLE command strobes are representable; PA-table, FIFO and TX paths are absent.
class BoardCc1101PassiveSpectrum final {
public:
    struct AsyncEdge final {
        std::uint16_t durationUs = 0;
        bool newLevel = false;
        bool clipped = false;
    };

    ~BoardCc1101PassiveSpectrum() { end(); }

    bool begin(
        bool radioSpiOwned,
        drivers::radio::Cc1101PassiveSpectrumReport* report);
    bool sample(
        const drivers::radio::Cc1101PassiveSpectrumPlan& plan,
        std::size_t bin,
        drivers::radio::Cc1101PassiveSample* output);
    // Sample an exact point in any declared CC1101 tuning window. This is the
    // receive-only primitive used by the automatic frequency finder.
    bool sampleFrequency(std::uint32_t frequencyKHz, std::int16_t* rssiDbm,
                         std::uint64_t* startedUs,
                         std::uint64_t* endedUs);
    // Lock the same receive-only adapter to one tunable frequency and expose
    // bounded RSSI envelope samples. No FIFO, PA table or TX strobe exists.
    bool lockReceive(std::uint32_t frequencyKHz);
    bool lockReceive(
        std::uint32_t frequencyKHz,
        domain::captures::SubGhzRawModulation modulation);
    bool sampleRssi(std::int16_t* rssiDbm, std::uint64_t* monotonicUs);
    bool startAsyncEdgeCapture(bool* startLevel);
    bool stopAsyncEdgeCapture();
    bool popAsyncEdge(AsyncEdge* output);
    bool takeAsyncEdgeOverflow();
    bool asyncEdgeCaptureActive() const;
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
    bool configureReceive(
        domain::captures::SubGhzRawModulation modulation);
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
    domain::captures::SubGhzRawModulation modulation_ =
        domain::captures::SubGhzRawModulation::OokEnvelope;
};

}  // namespace leshy1::platform::arduino
