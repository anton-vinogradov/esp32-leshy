#pragma once

#include <Arduino.h>
#include "../../core/version.h"

class ScanEngine;
class NetManager;

// In-app OTA from GitHub Releases. Two phases run in a background FreeRTOS task so
// the UI stays responsive; state is published for the screen to poll (gen() bumps
// on every change). Design: manual Update.h + HTTPClient + WiFiClientSecure with
// the Mozilla CA bundle (validates api.github.com AND the redirected download host),
// SNTP time first (TLS needs a valid clock), SHA-256 verified against the release
// asset's digest, and the bootloader's anti-rollback as the safety net.
// Own-equipment / educational firmware — see DISCLAIMER.
class OtaManager {
public:
    enum Phase { IDLE, CHECKING, UPTODATE, AVAILABLE, DOWNLOADING, DONE, FAILED };
    enum Err   { E_NONE, E_NONET, E_TIME, E_API, E_NORELEASE, E_RATELIMIT,
                 E_PARSE, E_NOASSET, E_HTTP, E_BEGIN, E_WRITE, E_SHORT, E_HASH, E_END };

    void begin(ScanEngine* eng, NetManager* net);
    void markHealthy();                 // confirm the running image (cancels pending rollback)

    void startCheck();                  // async: time + GET /releases/latest + compare
    void startUpdate();                 // async: download firmware.bin -> flash -> reboot (only when AVAILABLE)

    Phase       phase()    const { return phase_; }
    Err         err()      const { return err_; }
    int         progress() const { return pct_; }
    const char* latest()   const { return latest_; }
    uint32_t    gen()      const { return gen_; }
    bool        busy()     const { return busy_; }
    static const char* current() { return LESHY_FW_VERSION; }

private:
    volatile Phase    phase_ = IDLE;
    volatile Err      err_   = E_NONE;
    volatile int      pct_   = 0;
    volatile uint32_t gen_   = 0;
    volatile bool     busy_  = false;
    char   latest_[24] = {0};
    char   url_[320]   = {0};
    char   digest_[80] = {0};
    long   size_       = 0;
    bool   healthy_    = false;
    ScanEngine* eng_ = nullptr;
    NetManager* net_ = nullptr;

    void set(Phase p) { phase_ = p; gen_ = gen_ + 1; }
    void fail(Err e)  { err_ = e; phase_ = FAILED; gen_ = gen_ + 1; busy_ = false; Serial.printf("[OTA] fail err=%d\n", (int)e); }
    bool prep();
    bool syncTime();
    void doCheck();
    void doDownload();
    static void checkTask(void*);
    static void updTask(void*);
};
