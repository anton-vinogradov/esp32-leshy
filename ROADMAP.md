# Roadmap / План

Prioritized plan for ESP32-Leshy. Effort is a rough estimate; "interest" is how valuable/cool the feature is. This is a living document.

Приоритизированный план. «Effort» — грубая оценка сложности; «⭐» — насколько фича ценная/крутая.

## Phase 0 — Foundation / Фундамент

The boring-but-critical base. Most ESP32-DIV pain comes from here.

- [ ] **Split SPI buses** (touch / radio / SD) — root cause of the "touch dies after RF" bug. `effort: high` ⭐⭐⭐⭐⭐
- [ ] Display + touch driver (TFT_eSPI, XPT2046 calibration). `effort: medium`
- [ ] Cooperative task model — no `delay()` in scan loops; radio never blocks UI. `effort: medium` ⭐⭐⭐⭐⭐
- [ ] Button/input layer with proper debounce (PCF8574 auto-detect for v2.0/v2.1). `effort: medium`
- [ ] Menu framework + settings (brightness via LEDC, screen sleep). `effort: medium`
- [ ] Battery gauge over I²C (IP5306-I2C, not ADC). `effort: medium`
- [ ] SD layer with buffered writes (CSV / JSON / PCAP). `effort: low`
- [ ] On-screen keyboard with the **full** WPA character set. `effort: low` ⭐⭐⭐⭐

## Phase 1 — Analysis & defense / Анализ и защита

Legal, useful, high value-per-effort. Good first "real" features.

- [ ] **Wi-Fi deauth detector** — passive, fully legal. `effort: low` ⭐⭐⭐⭐⭐
- [ ] Wi-Fi scanner (SSID / channel / RSSI / auth, OUI vendor lookup). `effort: low`
- [ ] 2.4 GHz activity waterfall (NRF24 RPD sweep, 3 modules parallel). `effort: medium` ⭐⭐⭐⭐⭐
- [ ] Wi-Fi sniffer (promiscuous) + PCAP to SD. `effort: medium` ⭐⭐⭐⭐
- [ ] BLE scanner (NimBLE) + tracker / skimmer / hidden-camera detectors. `effort: low` ⭐⭐⭐⭐
- [ ] Beacon / probe-request analysis. `effort: medium`

## Phase 2 — Trickster toolkit / Пакости

The fun stuff. Framed for demos on your own gear; disruptive TX gated + off by default.

- [ ] Evil-twin AP + captive portal (Apple/Android detection handled). `effort: medium` ⭐⭐⭐⭐
- [ ] BLE notification spam (proximity pop-ups). `effort: medium` ⭐⭐⭐⭐
- [ ] Fake beacon / SSID flood. `effort: medium`
- [ ] "Lead astray" mode — playful redirects (DNS / captive). `effort: medium`

## Phase 3 — Radio & extras / Радио и прочее

- [ ] IR record / replay / universal remote (IRremoteESP8266). `effort: low` ⭐⭐⭐
- [ ] GPS wardriving → WiGLE CSV (TinyGPS++, 2nd UART). `effort: medium` ⭐⭐⭐⭐
- [ ] Sub-GHz RX / replay (CC1101, RadioLib) — static codes only; rolling-code will NOT replay. `effort: high` ⭐⭐⭐⭐
- [ ] RFID/NFC read/dump (PN532) — MIFARE Classic needs keys. `effort: high`
- [ ] NeoPixel status effects (mind GPIO1 = UART0 TX). `effort: low`
- [ ] Web / OTA firmware update. `effort: medium`

## Explicitly out (for now) / Сознательно не берём

Loud, illegal-outside-a-lab, or broken by modern SDKs — low value, high risk:

- Active Wi-Fi deauth attack (blocked by recent ESP-IDF sanity checks; illegal to jam).
- NRF/BLE/CC1101 jammers ("Proto Kill", constant-carrier) — illegal RF interference.
- Probe-request flood.

If added later, they stay behind a clear warning and default-off.

## Key gotchas / Ключевые грабли

- NRF24 "spectrum" = 1-bit RPD occupancy detector (threshold −64 dBm), **not** a dBm level meter. Average many sweeps for a bar height.
- ESP32 hears **one channel at a time** — sniffer/detector need channel hopping (and then miss attacks on other channels; pin the channel for defense).
- Promiscuous RX callback runs in the Wi-Fi task — **no SD I/O inside it**, only push to a queue.
- Sub-GHz replay does **not** work against rolling codes (KeeLoq, modern cars).
- NRF24 PA/LNA modules need a 10–100 µF cap on 3.3 V or the ESP32 browns out.
