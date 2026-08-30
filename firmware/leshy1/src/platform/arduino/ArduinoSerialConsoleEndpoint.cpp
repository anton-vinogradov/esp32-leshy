#include "ArduinoSerialConsoleEndpoint.h"

#include <algorithm>

namespace leshy1::platform::arduino {

services::serial::SerialConsolePreflightStatus
ArduinoSerialConsoleEndpoint::configure(
    const services::serial::SerialConsoleConfig& config,
    const services::serial::SerialConsoleHardware& hardware) {
    if (active_) {
        return services::serial::SerialConsolePreflightStatus::MuxConflict;
    }
    const auto status = services::serial::validateSerialConsoleConfig(
        config, hardware);
    if (status != services::serial::SerialConsolePreflightStatus::Ready) {
        configured_ = false;
        config_ = {};
        buffer_.reset();
        return status;
    }
    config_ = config;
    configured_ = true;
    cleanupComplete_ = true;
    buffer_.reset();
    bytesReceived_ = 0U;
    bytesTransmitted_ = 0U;
    return status;
}

bool ArduinoSerialConsoleEndpoint::start(std::uint32_t nowMs) {
    static_cast<void>(nowMs);
    if (!configured_ || active_) return false;
    cleanupComplete_ = false;
    buffer_.reset();
    bytesReceived_ = 0U;
    bytesTransmitted_ = 0U;
    serial_.setRxBufferSize(services::serial::SerialConsoleBuffer::kCapacity);
    const int8_t txPin = config_.mode ==
            services::serial::SerialConsoleMode::Bridge
        ? 6 : -1;
    serial_.begin(config_.baud, arduinoFraming(config_.framing), 5, txPin);
    active_ = true;
    return true;
}

services::actions::ActionEndpointState
ArduinoSerialConsoleEndpoint::tick(std::uint32_t nowMs) {
    static_cast<void>(nowMs);
    if (!active_) return services::actions::ActionEndpointState::Failed;
    constexpr std::size_t kMaximumBytesPerTick = 64U;
    std::size_t consumed = 0U;
    while (consumed < kMaximumBytesPerTick && serial_.available() > 0) {
        const int value = serial_.read();
        if (value < 0) break;
        ++bytesReceived_;
        ++consumed;
        if (!buffer_.push(static_cast<std::uint8_t>(value))) {
            // Do not let a later lease owner inherit either the UART or a
            // truncated transcript after bounded capacity is exceeded.
            stop();
            return services::actions::ActionEndpointState::Failed;
        }
    }
    return services::actions::ActionEndpointState::Running;
}

void ArduinoSerialConsoleEndpoint::cancel() { stop(); }

bool ArduinoSerialConsoleEndpoint::pop(std::uint8_t* output) {
    return buffer_.pop(output);
}

std::size_t ArduinoSerialConsoleEndpoint::write(
    const std::uint8_t* data, std::size_t length) {
    if (!active_ || config_.mode !=
            services::serial::SerialConsoleMode::Bridge ||
        data == nullptr || length == 0U) {
        return 0U;
    }
    constexpr std::size_t kMaximumWrite = 64U;
    const std::size_t bounded = std::min(length, kMaximumWrite);
    const std::size_t written = serial_.write(data, bounded);
    bytesTransmitted_ += static_cast<std::uint32_t>(written);
    return written;
}

ArduinoSerialConsoleStats ArduinoSerialConsoleEndpoint::stats() const {
    return {
        configured_, active_, cleanupComplete_, bytesReceived_,
        bytesTransmitted_, buffer_.dropped(), buffer_.size(),
        buffer_.highWater(),
    };
}

std::uint32_t ArduinoSerialConsoleEndpoint::arduinoFraming(
    services::serial::SerialConsoleFraming framing) {
    switch (framing) {
        case services::serial::SerialConsoleFraming::Data8None1:
            return SERIAL_8N1;
        case services::serial::SerialConsoleFraming::Data8Even1:
            return SERIAL_8E1;
        case services::serial::SerialConsoleFraming::Data8Odd1:
            return SERIAL_8O1;
        case services::serial::SerialConsoleFraming::Data8None2:
            return SERIAL_8N2;
    }
    return SERIAL_8N1;
}

void ArduinoSerialConsoleEndpoint::stop() {
    if (active_) serial_.end();
    active_ = false;
    configured_ = false;
    cleanupComplete_ = true;
    config_ = {};
    buffer_.scrub();
}

}  // namespace leshy1::platform::arduino
