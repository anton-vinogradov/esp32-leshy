#pragma once

#include <Arduino.h>

// RecStore — a persistent library of sub-GHz captures on the built-in flash. Uses the
// "spiffs" partition already carved in default_8MB.csv (1.5 MB, otherwise unused) via
// LittleFS, so nothing in the partition table changes and OTA is untouched. One capture =
// one file /rec/<name>: a small header + the on/off pulse durations (microseconds).
// Own-equipment recordings only; nothing here transmits.
namespace RecStore {
    static const int MAX_DUR  = 512;   // matches recBuf[] in main.cpp
    static const int NAME_LEN = 16;    // on-device name length
    static const int MAX_RECS = 64;    // library cap — save() refuses new names beyond this so nothing is unlistable

    bool begin();                      // mount LittleFS + ensure /rec (call once at boot)
    bool ready();
    int  count();                      // number of saved captures in /rec

    // Write one capture as /rec/<name> (overwrites a same-named file). false on FS error / bad args.
    bool save(const char* name, const uint16_t* dur, int n,
              uint32_t freqKHz, bool fsk, bool inv, int startLevel);

    // Fill out[] with up to maxOut file names from /rec; returns how many.
    int  list(String* out, int maxOut);

    // Read a capture back into dur[] (cap = buffer capacity). false if missing / corrupt.
    bool load(const char* name, uint16_t* dur, int cap, int& n,
              uint32_t& freqKHz, bool& fsk, bool& inv, int& startLevel);

    bool remove(const char* name);
    bool exists(const char* name);
}
