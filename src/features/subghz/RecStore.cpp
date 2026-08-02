#include "RecStore.h"

#include <LittleFS.h>

namespace {
    // 16-byte header, then count × uint16 durations.
    struct Header {
        uint32_t magic;        // 'LSHR'
        uint16_t version;      // 1
        uint16_t count;        // number of uint16 durations that follow
        uint32_t freqKHz;      // capture/replay frequency (== recFreqKHz)
        uint8_t  fsk;          // modulation: 0 = OOK/ASK, 1 = 2-FSK   (== sub_mod)
        uint8_t  inv;          // replay polarity inverted              (== sub_inv)
        uint8_t  startLevel;   // captured start polarity (Cc1101 capStartLevel_)
        uint8_t  reserved;
    };
    const uint32_t MAGIC = 0x4C534852u;   // "LSHR"
    bool s_ready = false;

    // Build a safe path /rec/<clean>: strip separators / control chars, cap the length.
    void pathFor(const char* name, char* out, size_t cap) {
        char clean[RecStore::NAME_LEN + 1];
        int k = 0;
        for (const char* p = name; *p && k < RecStore::NAME_LEN; ++p) {
            char c = *p;
            if (c == '/' || c == '\\' || (uint8_t)c < 0x20) c = '_';
            clean[k++] = c;
        }
        clean[k] = 0;
        snprintf(out, cap, "/rec/%s", clean);
    }
}

bool RecStore::begin() {
    if (s_ready) return true;
    if (!LittleFS.begin(true)) return false;      // formatOnFail — formats the empty spiffs partition on first boot
    if (!LittleFS.exists("/rec")) LittleFS.mkdir("/rec");
    s_ready = true;
    return true;
}

bool RecStore::ready() { return s_ready; }

// Write via a temp file + atomic rename so a failure (full partition) never destroys the
// existing same-named capture. Refuses a brand-new name once the library is full, so every
// saved file stays visible in the (equally capped) playback list.
bool RecStore::save(const char* name, const uint16_t* dur, int n,
                    uint32_t freqKHz, bool fsk, bool inv, int startLevel) {
    if (!s_ready || !name || !*name || n < 1 || n > MAX_DUR) return false;
    char path[6 + RecStore::NAME_LEN + 1];
    pathFor(name, path, sizeof(path));
    if (!LittleFS.exists(path) && count() >= MAX_RECS) return false;   // library full — don't create an unlistable file
    const char* tmp = "/rec/.tmp";
    File f = LittleFS.open(tmp, "w");
    if (!f) return false;
    Header h{ MAGIC, 1, (uint16_t)n, freqKHz,
              (uint8_t)(fsk ? 1 : 0), (uint8_t)(inv ? 1 : 0), (uint8_t)(startLevel ? 1 : 0), 0 };
    size_t need = sizeof(uint16_t) * (size_t)n;
    bool ok = f.write((const uint8_t*)&h, sizeof(h)) == sizeof(h)
           && f.write((const uint8_t*)dur, need) == need;
    f.close();
    if (!ok) { LittleFS.remove(tmp); return false; }                  // the old file (if any) is untouched
    if (!LittleFS.rename(tmp, path)) { LittleFS.remove(tmp); return false; }   // atomic replace of the target
    return true;
}

int RecStore::list(String* out, int maxOut) {
    if (!s_ready || maxOut <= 0) return 0;
    File d = LittleFS.open("/rec");
    if (!d) return 0;
    int k = 0;
    for (File e = d.openNextFile(); e && k < maxOut; e = d.openNextFile()) {
        if (e.isDirectory()) continue;
        String nm = e.name();                     // some cores return a full path
        int slash = nm.lastIndexOf('/');
        if (slash >= 0) nm = nm.substring(slash + 1);
        if (!nm.length() || nm[0] == '.') continue;   // skip the ".tmp" scratch file / dotfiles
        out[k++] = nm;
    }
    d.close();
    return k;
}

int RecStore::count() {
    if (!s_ready) return 0;
    File d = LittleFS.open("/rec");
    if (!d) return 0;
    int k = 0;
    for (File e = d.openNextFile(); e; e = d.openNextFile()) {
        if (e.isDirectory()) continue;
        String nm = e.name();
        int slash = nm.lastIndexOf('/');
        if (slash >= 0) nm = nm.substring(slash + 1);
        if (nm.length() && nm[0] != '.') k++;
    }
    d.close();
    return k;
}

bool RecStore::load(const char* name, uint16_t* dur, int cap, int& n,
                    uint32_t& freqKHz, bool& fsk, bool& inv, int& startLevel) {
    if (!s_ready) return false;
    char path[6 + RecStore::NAME_LEN + 1];
    pathFor(name, path, sizeof(path));
    File f = LittleFS.open(path, "r");
    if (!f) return false;
    Header h;
    if (f.read((uint8_t*)&h, sizeof(h)) != sizeof(h) || h.magic != MAGIC) { f.close(); return false; }
    int cnt = h.count;
    if (cnt > cap) cnt = cap;
    int got = cnt > 0 ? f.read((uint8_t*)dur, sizeof(uint16_t) * cnt) / sizeof(uint16_t) : 0;
    f.close();
    n = got;
    freqKHz = h.freqKHz;
    fsk = h.fsk;
    inv = h.inv;
    startLevel = h.startLevel;
    return got > 0;
}

bool RecStore::remove(const char* name) {
    if (!s_ready) return false;
    char path[6 + RecStore::NAME_LEN + 1];
    pathFor(name, path, sizeof(path));
    return LittleFS.remove(path);
}

bool RecStore::exists(const char* name) {
    if (!s_ready) return false;
    char path[6 + RecStore::NAME_LEN + 1];
    pathFor(name, path, sizeof(path));
    return LittleFS.exists(path);
}
