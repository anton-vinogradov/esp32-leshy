#pragma once

#include <Arduino.h>

// SubCfg — a phone captive portal to configure the Sub-GHz record / replay / TX from a
// browser (typing 433.92 or a dBm threshold on a 5-button pad is painful). Raises its own
// "Leshy-subghz" SoftAP, serves one form, saves the fields to NVS, then drops the AP.
// main.cpp reads the saved values back and applies them. Own-equipment settings only.
class SubCfg {
public:
    bool begin();                         // raise the SoftAP + form
    void loop();                          // service DNS/web (call each loop while running)
    void stop();
    bool isRunning() const { return running_; }
    bool saved() const { return saved_; }        // the form was submitted

    static const char* apName() { return "Leshy-subghz"; }

private:
    void handleRoot();
    void handleSave();
    void redirect();

    bool     running_ = false;
    bool     saved_ = false;
    bool     routes_ = false;             // web handlers registered once (stop() keeps them)
    bool     armed_ = false;              // shutdown armed after save
    uint32_t at_ = 0;
};
