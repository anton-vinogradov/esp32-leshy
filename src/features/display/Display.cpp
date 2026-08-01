#include "Display.h"

TFT_eSPI tft;

void displayInit() {
    tft.init();
    tft.setRotation(2);      // ESP32-DIV v2 panel is flipped vs rotation 0
}
