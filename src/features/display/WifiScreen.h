#pragma once

#include "../scan/ScanEngine.h"

// WifiScreen — renders the Wi-Fi snapshot from ScanEngine on the TFT. draw()
// paints header + rows + footer; rows() repaints just the list (via a sprite,
// flicker-free). No scanning here — the engine does that in the background.
class WifiScreen {
public:
    void draw(ScanEngine& e, int offset);
    void rows(ScanEngine& e, int offset);
};
