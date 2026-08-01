#pragma once

// BootScreen — the startup screen on the 2.8" ILI9341 TFT. Draws an on-brand
// splash (forest + Wi-Fi + title) so the device shows something instead of a
// blank white panel. First real use of the display on ESP32-DIV v2.
class BootScreen {
public:
    void show();
};
