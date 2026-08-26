#include <Arduino.h>
#include <BLEDevice.h>
#include <WiFi.h>

#include <cstring>

namespace {

constexpr const char* kSchema = "leshy.hil.correlation_fixture.v1";
constexpr int kWifiTxDbm = -1;
constexpr int kBleTxDbm = -12;
constexpr std::size_t kLabelCapacity = 20;

enum class Mode : std::uint8_t { Off, Wifi, Ble };

Mode mode = Mode::Off;
BLEAdvertising* advertising = nullptr;
bool bleInitialized = false;
char label[kLabelCapacity + 1U] = "LESHY-HIL-CORR";

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
        "\"label\":\"%s\",\"wifi_tx\":%s,\"ble_tx\":%s,"
        "\"wifi_tx_dbm\":%d,\"ble_tx_dbm\":%d}\n",
        kSchema, modeName(), label, mode == Mode::Wifi ? "true" : "false",
        mode == Mode::Ble ? "true" : "false", kWifiTxDbm, kBleTxDbm);
}

void stopWifi() {
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    // The next DUT scan must not retain a final AP beacon from the previous
    // fixture mode.  The extra bounded guard time is fixture-only and keeps
    // the two persisted Sessions unambiguous.
    delay(750);
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
    WiFi.setTxPower(WIFI_POWER_MINUS_1dBm);
    if (!WiFi.softAP(label, nullptr, 1, false, 1)) {
        setOff();
        return false;
    }
    mode = Mode::Wifi;
    return true;
}

bool setBle() {
    setOff();
    BLEDevice::init(label);
    bleInitialized = true;
    BLEDevice::setPower(ESP_PWR_LVL_N12, ESP_BLE_PWR_TYPE_ADV);
    advertising = BLEDevice::getAdvertising();
    if (advertising == nullptr) {
        setOff();
        return false;
    }
    BLEAdvertisementData data;
    // Keep the complete local name in the primary advertising PDU.  Leshy is
    // deliberately a passive observer and therefore never sends the active
    // scan request that would be needed to recover a scan-response-only name.
    data.setFlags(ESP_BLE_ADV_FLAG_GEN_DISC |
                  ESP_BLE_ADV_FLAG_BREDR_NOT_SPT);
    data.setName(label);
    advertising->setScanResponse(false);
    if (!advertising->setAdvertisementData(data)) {
        setOff();
        return false;
    }
    advertising->setMinInterval(160);
    advertising->setMaxInterval(240);
    if (!advertising->start()) {
        setOff();
        return false;
    }
    // A successful GAP start request precedes the first over-air PDU.  Do not
    // acknowledge the mode until several advertising intervals have elapsed.
    delay(750);
    mode = Mode::Ble;
    return true;
}

void reject(const char* reason) {
    Serial.printf(
        "{\"schema\":\"%s\",\"kind\":\"error\","
        "\"reason\":\"%s\"}\n", kSchema, reason);
}

bool setLabel(const char* hex) {
    if (mode != Mode::Off || hex == nullptr) return false;
    const std::size_t length = std::strlen(hex);
    if (length == 0U || (length % 2U) != 0U ||
        length > kLabelCapacity * 2U) {
        return false;
    }
    char decoded[kLabelCapacity + 1U] = {};
    const auto nibble = [](char value) -> int {
        if (value >= '0' && value <= '9') return value - '0';
        if (value >= 'A' && value <= 'F') return value - 'A' + 10;
        if (value >= 'a' && value <= 'f') return value - 'a' + 10;
        return -1;
    };
    for (std::size_t index = 0; index < length / 2U; ++index) {
        const int high = nibble(hex[index * 2U]);
        const int low = nibble(hex[index * 2U + 1U]);
        if (high < 0 || low < 0) return false;
        const char value = static_cast<char>((high << 4) | low);
        if (value < 0x20 || value > 0x7e || value == '"' || value == '\\') {
            return false;
        }
        decoded[index] = value;
    }
    std::strcpy(label, decoded);
    return true;
}

void handleLine(char* line) {
    if (std::strcmp(line, "state") == 0) {
        emitState();
        return;
    }
    if (std::strncmp(line, "label ", 6) == 0) {
        if (!setLabel(line + 6)) {
            reject("label_rejected");
            return;
        }
    } else if (std::strcmp(line, "mode off") == 0) {
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
    static char line[64] = {};
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
