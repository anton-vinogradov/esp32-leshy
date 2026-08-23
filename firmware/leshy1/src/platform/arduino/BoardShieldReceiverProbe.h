#pragma once

#include "drivers/radio/ShieldReceiverIdentity.h"

namespace leshy1::platform::arduino {

// Guarded identity-only probe for the explicitly declared RF-shield assembly.
// It never raises an nRF CE pin, sends a CC1101 command strobe, or selects slot 3.
class BoardShieldReceiverProbe final {
public:
    bool run(bool radioSpiOwned,
             drivers::radio::ShieldReceiverProbeReport* report);

private:
    std::uint8_t transfer(std::uint8_t value);
    std::uint8_t readNrfRegister(int chipSelect, std::uint8_t reg,
                                 std::uint8_t* status);
    drivers::radio::NrfReceiverIdentity readNrf(int chipSelect);
    bool readCcStatus(std::uint8_t address, std::uint8_t* status,
                      std::uint8_t* value);
    std::uint8_t sampleMisoHigh(int inputMode);
    std::uint8_t readNrfNopBitBang(int chipSelect, int inputMode);
    void characterizeBusLine();
    bool gpio21Safe() const;
    void holdTransmitPathsInactive();
    void cleanup();

    drivers::radio::ShieldReceiverProbeReport* report_ = nullptr;
    bool spiStarted_ = false;
    bool transactionOpen_ = false;
};

}  // namespace leshy1::platform::arduino
