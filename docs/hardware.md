# Hardware / Железо

ESP32-Leshy targets the **ESP32-DIV v2** platform by [CiferTech](https://github.com/cifertech/ESP32-DIV). We do not make or sell hardware — get the board there (or build a compatible DIY version).

Целевая платформа — **ESP32-DIV v2**. Железо мы не делаем и не продаём; плату берите у CiferTech или собирайте совместимую.

## Modules / Модули

| Part | Bus | Role |
|------|-----|------|
| ESP32-S3 | — | main MCU, Wi-Fi + BLE built in |
| ILI9341 2.8" TFT | SPI | display |
| XPT2046 | SPI | resistive touch |
| 3× NRF24L01(+) | SPI | 2.4 GHz sweep / spectrum / TX |
| CC1101 | SPI | Sub-GHz (300–928 MHz) RX/replay |
| PN532 | SPI | RFID / NFC (13.56 MHz) |
| NEO-6M GPS | UART | wardriving, time |
| IR TX/RX | GPIO | remotes |
| microSD | SPI | logs, profiles, PCAP |
| IP5306 (I2C variant) | I²C | battery / charge |
| PCF8574 | I²C | button expander (v2.x) |
| WS2812 ×4 | GPIO1 | status LEDs |
| CP2102 | USB | flashing / serial |

## Known hardware gotchas / Аппаратные грабли

- **Shared SPI bus** between touch, radios and SD is the #1 source of bugs (touch freezes after RF). Leshy splits touch onto a second SPI bus. The ESP32-S3 has two hardware SPI peripherals — use them.
- **Battery gauge**: the board uses the **IP5306-I2C** variant and the ADC divider pin may not be wired — read charge over I²C registers, not analog voltage.
- **GPIO1 = UART0 TX** also drives the NeoPixels — logging over UART0 conflicts; log over USB-CDC or disable it.
- **GPIO14** may be shared between the IR TX and an NRF24 on some revisions — plan pin usage before enabling both.
- **NRF24 PA/LNA** modules draw pulsed current — add a 10–100 µF cap on 3.3 V or the ESP32 browns out.

> Exact pin map will be committed once verified on real hardware. If your build differs, pins will live in a single board-config header.
>
> Точную распиновку зафиксируем после проверки на живой плате; она будет в одном board-config заголовке.
