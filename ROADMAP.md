# Roadmap / План

Prioritized plan for ESP32-Leshy. `effort` is a rough estimate; ⭐ marks the tastiest / highest-value features. This is a living document.

Приоритизированный план. «Effort» — грубая оценка сложности; ⭐ — самые сочные/ценные фичи.

> 🛑 Всё ниже — **только для своего оборудования и авторизованного тестирования**. Обязательно прочтите [DISCLAIMER.md](DISCLAIMER.md): никогда не применяйте это к чужому. / Everything below is **for your own equipment and authorized testing only** — see [DISCLAIMER.md](DISCLAIMER.md).

## Two headline tracks / Две главные ветки

1. **Wi-Fi lab** — attack & analyze **your own** networks, plus a universal signal finder (Phase 1).
2. **The Ether Recorder** — Sub-GHz record → classify → replay **your own** gear (Phase 2).

Everything sits on a **Foundation** (Phase 0), and a **Trickster & extras** grab-bag rounds it out (Phase 3). Vertical slices can ship headless before the full UI is done (as PolitePortal already did).

---

## Phase 0 — Foundation / Фундамент

The boring-but-critical base. Most ESP32-DIV pain comes from here.

- [ ] **Split SPI buses** (touch / radio / SD) — root cause of the "touch dies after RF" bug. `effort: high` ⭐⭐⭐⭐⭐
- [ ] Display + touch driver (TFT_eSPI, XPT2046 calibration). `effort: medium`
- [ ] Cooperative task model — radio scans never freeze input or drawing. `effort: medium` ⭐⭐⭐⭐⭐
- [ ] Input layer + debounce (PCF8574 auto-detect for v2.0/v2.1). `effort: medium`
- [ ] Menu framework + settings (brightness via LEDC, screen sleep). `effort: medium`
- [ ] On-screen keyboard with the **full** WPA character set. `effort: low` ⭐⭐⭐⭐
- [ ] Battery gauge over I²C (IP5306-I2C, not ADC). `effort: medium`
- [ ] SD layer with buffered writes (CSV / JSON / PCAP). `effort: low`

## Phase 1 — Wi-Fi lab / Wi-Fi лаба  (priority #1)

Attack & analyze your own networks. Deauth *as an attack on others* is out (see below); deauth against your own net for handshake capture / resilience testing is fine.

- [ ] **Deauth detector** — passive, fully legal ("who's attacking me"). `effort: low` ⭐⭐⭐⭐⭐
- [ ] Wi-Fi scanner (SSID / channel / RSSI / auth + OUI vendor). `effort: low`
- [ ] **WPA/WPA2 handshake capture** (+ deauth assist on your own net) → crack offline on a PC with hashcat. `effort: medium` ⭐⭐⭐⭐⭐
- [ ] **PMKID capture** (clientless) → hashcat. `effort: medium` ⭐⭐⭐⭐
- [ ] WPS PIN (Pixie Dust / brute) — feasibility to be confirmed on ESP32. `effort: high`
- [ ] Wi-Fi sniffer (promiscuous) + PCAP to SD (Wireshark). `effort: medium` ⭐⭐⭐⭐
- [x] **Polite Portal** — captive portal, **no credential logging**: asks to lower Wi-Fi TX power, verifies the drop via beacon RSSI, self-shuts-down. *(first cut landed — `src/features/polite_portal/`)* ⭐⭐⭐⭐
- [ ] Evil-twin + captive-portal delivery (same SSID + deauth of your own AP) — own-network/lab only. `effort: medium`
- [ ] ⭐ **Signal Finder ("hot / cold")** — universal RSSI direction-finder for ANY source (Wi-Fi AP, BLE device, 2.4 GHz, Sub-GHz). Big needle + buzzer/NeoPixel "warmer/colder". Foxhunt / find-that-AP-at-the-door. `effort: medium` ⭐⭐⭐⭐⭐

## Phase 2 — The Ether Recorder / Sub-GHz  (priority #2)

Record the airwaves, classify what's there, replay **your own** devices.

- [ ] CC1101 RX + raw OOK/ASK capture (timing via GDO0). `effort: high` ⭐⭐⭐⭐
- [ ] **Record-all + auto-classify** — rtl_433-style protocol ID (weather sensors, TPMS, doorbells, static remotes). `effort: high` ⭐⭐⭐⭐⭐
- [ ] **Signal library on SD** — browse / name / organize captures (+ Flipper `.sub` compatibility). `effort: medium` ⭐⭐⭐⭐
- [ ] **Replay your own devices** — static-code gates, 433 MHz sockets, etc. `effort: medium` ⭐⭐⭐⭐
- [ ] **"Record now"** — grab a specific signal on demand from a source you hold. `effort: low` ⭐⭐⭐⭐
- Reality check surfaced in the UI: rolling codes (KeeLoq, modern cars, real alarms) **do not** replay; CC1101 hears a narrow slice at a time (a full-spectrum sweep needs an SDR).

## Phase 3 — Trickster & extras / Пакости и экстра

The fun grab-bag + high-value extras from the hardware. Mostly legal; anything transmitting stays own-gear/demo.

- [ ] ⭐ **Surveillance Sweep** — hunt hidden cameras / bugs / trackers: BLE (AirTag/Tile/Find My) + Wi-Fi cameras + RF patterns. `effort: medium` ⭐⭐⭐⭐
- [ ] ⭐ **BLE tracker detector + "find my thing"** — spot foreign trackers near you; and home in on *your own* lost tag by RSSI. `effort: low` ⭐⭐⭐⭐
- [ ] **IR universal remote + TV-B-Gone** — record/replay your remotes; the classic "turn any TV off" prank. `effort: low` ⭐⭐⭐
- [ ] **2.4 GHz spectrum waterfall** (NRF24 RPD, 3 modules parallel). `effort: medium` ⭐⭐⭐⭐
- [ ] **Own RFID/NFC wallet** — read / store / emulate **your own** cards (PN532). `effort: high`
- [ ] **GPS wardriving → WiGLE CSV** (TinyGPS++, 2nd UART). `effort: medium` ⭐⭐⭐
- [ ] **BLE notification spam (Sour-Apple style)** — pop-up prank on your own devices / demo. `effort: medium`
- [ ] **RF sonification / visualizer** — turn the ether into sound/graphics. `effort: low`
- [ ] NeoPixel status / mood effects (mind GPIO1 = UART0 TX). `effort: low`
- [ ] Web / OTA firmware update. `effort: medium`

## Explicitly out (for now) / Сознательно не берём

Loud, illegal-outside-a-lab, or broken by modern SDKs — low value, high risk:

- Active Wi-Fi deauth **as an attack on networks you don't own** (illegal; also blocked by recent ESP-IDF sanity checks).
- NRF/BLE/CC1101 jammers ("Proto Kill", constant-carrier) — illegal RF interference; radiating a jammer over the air is illegal even against your own devices.
- Probe-request flood.
- Replaying someone else's alarm / security / car signals (illegal, and rolling codes won't replay anyway).

If any TX-heavy feature is added for lab use, it stays behind a clear warning and default-off.

## Key gotchas / Ключевые грабли

- NRF24 "spectrum" = 1-bit RPD occupancy detector (threshold −64 dBm), **not** a dBm level meter. Average many sweeps per channel.
- ESP32 hears **one channel at a time** — sniffer/detector need channel hopping (and then miss other channels; pin the channel for defense).
- Promiscuous RX callback runs in the Wi-Fi task — **no SD I/O inside it**, only push to a queue.
- TX power can't be read over the air — infer it from beacon RSSI, and only while the device stays put (PolitePortal caveat).
- Sub-GHz replay does **not** work against rolling codes (KeeLoq, modern cars).
- NRF24 PA/LNA modules need a 10–100 µF cap on 3.3 V or the ESP32 browns out.
- Single radio: to sniff a target's beacons while running a SoftAP, the AP must be on the target's channel.
