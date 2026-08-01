#pragma once

#include "../scan/ScanEngine.h"
#include "../net/NetManager.h"

// WifiScreen — renders the Wi-Fi snapshot from ScanEngine on the TFT. draw()
// paints header + rows + footer; rows() repaints just the list (via a sprite,
// flicker-free). No scanning here — the engine does that in the background.
// If a NetManager is attached, the user's own network (by BSSID) is marked ★.
class WifiScreen {
public:
    void attachNet(NetManager* n) { net_ = n; }
    void draw(ScanEngine& e, int offset, int sel = -1);
    void rows(ScanEngine& e, int offset, int sel = -1);

private:
    NetManager* net_ = nullptr;
};
