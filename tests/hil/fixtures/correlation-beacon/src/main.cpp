#include <Arduino.h>
#include <BLEDevice.h>
#include <WiFi.h>

#include <cstring>

namespace {

constexpr const char* kSchema = "leshy.hil.correlation_fixture.v1";
constexpr const char* kLabel = "LESHY-HIL-CORR";

enum class Mode : std::uint8_t { Off, Wifi, Ble };

Mode mode = Mode::Off;
BLEAdvertising* advertising = nullptr;
bool bleInitialized = false;

const char* modeName() {
    switch (mode) {
        case Mode::Wifi: return "wifi";
        case Mode::Ble: return "ble";
        case Mode::Off: return "off";
    }
    return "off";
}

void emitState() {
    Serial.printf(
        "{\"schema\":\"%s\",\"kind\":\"state\",\"mode\":\"%s\","
        "\"label\":\"%s\",\"wifi_tx\":%s,\"ble_tx\":%s}\n",
        kSchema, modeName(), kLabel, mode == Mode::Wifi ? "true" : "false",
        mode == Mode::Ble ? "true" : "false");
}

void stopWifi() {
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(100);
}

void stopBle() {
    if (advertising != nullptr) advertising->stop();
    if (bleInitialized) BLEDevice::deinit(true);
    advertising = nullptr;
    bleInitialized = false;
    delay(100);
}

void setOff() {
    stopWifi();
    stopBle();
    mode = Mode::Off;
}

bool setWifi() {
    setOff();
    WiFi.mode(WIFI_AP);
    WiFi.setTxPower(WIFI_POWER_2dBm);
    if (!WiFi.softAP(kLabel, nullptr, 1, false, 1)) {
        setOff();
        return false;
    }
    mode = Mode::Wifi;
    return true;
}

bool setBle() {
    setOff();
    BLEDevice::init(kLabel);
    bleInitialized = true;
    BLEDevice::setPower(ESP_PWR_LVL_N0, ESP_BLE_PWR_TYPE_ADV);
    advertising = BLEDevice::getAdvertising();
    if (advertising == nullptr) {
        setOff();
        return false;
    }
    BLEAdvertisementData data;
    data.setName(kLabel);
    advertising->setAdvertisementData(data);
    advertising->setMinInterval(160);
    advertising->setMaxInterval(240);
    advertising->start();
    mode = Mode::Ble;
    return true;
}

void reject(const char* reason) {
    Serial.printf(
        "{\"schema\":\"%s\",\"kind\":\"error\","
        "\"reason\":\"%s\"}\n", kSchema, reason);
}

void handleLine(char* line) {
    if (std::strcmp(line, "state") == 0) {
        emitState();
        return;
    }
    if (std::strcmp(line, "mode off") == 0) {
        setOff();
    } else if (std::strcmp(line, "mode wifi") == 0) {
        if (!setWifi()) {
            reject("wifi_start_failed");
            return;
        }
    } else if (std::strcmp(line, "mode ble") == 0) {
        if (!setBle()) {
            reject("ble_start_failed");
            return;
        }
    } else {
        reject("unknown_command");
        return;
    }
    emitState();
}

}  // namespace

void setup() {
    Serial.begin(115200);
    setOff();
    emitState();
}

void loop() {
    static char line[32] = {};
    static std::size_t length = 0;
    while (Serial.available() > 0) {
        const char value = static_cast<char>(Serial.read());
        if (value == '\r') continue;
        if (value == '\n') {
            line[length] = '\0';
            if (length != 0) handleLine(line);
            length = 0;
        } else if (length + 1U < sizeof(line)) {
            line[length++] = value;
        } else {
            length = 0;
            reject("command_too_long");
        }
    }
    delay(5);
}
