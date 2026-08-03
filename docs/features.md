# ESP32-Leshy — Features

*Read this in: **English** · [Русский](features.ru.md)*

What the firmware does today, on real ESP32-DIV hardware, in a touch- and keypad-driven menu. Everything here is **passive / defensive / own-equipment** — see [DISCLAIMER.md](../DISCLAIMER.md).

## Menu map

```
ESP32-Leshy
├─ Wi-Fi
│  ├─ Wi-Fi Scan        signal · channel · security · ★your net · hidden
│  │  └─ ▶ on a network  Details (SSID · BSSID · channel · RSSI · security)
│  ├─ Channels 2.4G     scrolling real per-channel airtime graphs (promiscuous; 1/6/11)
│  ├─ Spectrum 2.4G     raw band waterfall over 2400-2525 MHz (NRF24 carrier detect)
│  ├─ Freq finder 2.4   which channel a 2.4 GHz signal is on (NRF24 hit-rate vs baseline)
│  └─ Advanced
│     ├─ Hidden names   revealed hidden SSIDs (saved to flash, deletable)
│     └─ Deauth monitor passive alarm on deauth/disassoc bursts
├─ BLE
│  └─ BLE Scan          nearby devices + tracker detector
├─ Sub-GHz
│  ├─ Spectrum          sub-GHz waterfall, RIGHT cycles bands (CC1101 RSSI)
│  ├─ Freq finder       find your own remote's frequency (rise-vs-freq graph)
│  └─ Rec / Replay      record → name (on-screen keyboard) → save · playback library
└─ Settings
   ├─ Wi-Fi connect     set up from your phone (captive portal) · status
   ├─ Update            OTA from GitHub releases
   ├─ Language          EN / RU
   ├─ Calibrate touch
   └─ About
```

Navigation: **▲▼** move, **middle** = enter/confirm, **▶** = options for the selected item, **◀** = back. Touch works too.

## Wi-Fi

### Wi-Fi Scan
Live list of nearby access points. Each row shows the name, a small **sparkline of that AP's signal over recent scans** (its footprint over time), the **channel**, and the **RSSI**. Your own network is marked **★** (matched by BSSID — even when it is hidden). Select a row and press **▶** to open **per-network options** (currently *Details*: SSID, BSSID, channel, RSSI, security, hidden/own) — this is where per-network tools live, reached from the scan rather than the menu.

### Channels 2.4G
A live, scrolling **area graph per channel (1–13)** — a cardiograph of how busy each channel really is. It listens in **promiscuous mode** and sums the on-air time of the frames it hears (management + data + control), sweeping the channels one at a time, so a channel with one busy access point outranks a channel crowded with idle ones. This is **actual airtime, not access-point count**. The value is a **lower bound** (only frames the radio decodes are counted, and the rate is estimated), so quiet air shows a small baseline and a genuine download or stream clearly rises above it. The non-overlapping channels **1 / 6 / 11** are highlighted. Uses the radio exclusively, so the background scan pauses while this screen is open.

### Spectrum 2.4G
A live **waterfall of the whole 2.4 GHz band** (2400–2525 MHz), painted with a separate **NRF24** radio while the ESP32's own Wi-Fi stays free. The NRF24 has no spectrum analyzer, but its carrier detector (RPD) latches on any signal above ~-64 dBm; sweeping all 126 one-MHz channels and colouring each by how often it fires builds a heat map — newest scan on top, flowing down. It sees **more than Wi-Fi**: Bluetooth, wireless video, drones, microwaves — anything radiating in the band shows up. Wi-Fi channels **1 / 6 / 11** are marked on the frequency axis. Needs an NRF24 module fitted (slot 2 on the ESP32-DIV v2).

### Freq finder 2.4
Point it at a 2.4 GHz gadget of **your own** — a remote, a tag, a drone controller — and it tells you **which channel** the signal is on. It sweeps all 126 NRF24 channels measuring a per-channel **hit-rate**, then subtracts a calibrated **baseline** (the constant Wi-Fi/Bluetooth floor) so only a channel that *rises* when your device transmits survives — drawn as a live bar graph with Wi-Fi **1 / 6 / 11** marked and the peak read out as `2400 + channel` MHz. Calibrate first (a couple of seconds, don't transmit), then press your device's button. Receive-only.

### Advanced → Hidden names
Hidden networks broadcast an empty SSID, but the name still travels in cleartext inside **Probe-Response** and **(Re)Association** frames. While scanning, the device passively recovers those names **only for the BSSIDs the scan actually sees as hidden**, saves them to flash (they survive a reboot), and lists them here with delete. It is passive — a name appears only when there is real traffic to that network (a client probing or connecting).

### Advanced → Deauth monitor
A passive, receive-only alarm: it watches the air (hopping channels) and flags bursts of **deauthentication / disassociation** frames — the signature of a deauth attack against a nearby network. Shows the count in a window, the total, the current channel and the last source MAC. Defensive only.

## BLE

### BLE Scan
Lists nearby Bluetooth-LE devices, **sorted by signal (nearest first)**, and flags known **trackers** (Apple Find My / Tile / Samsung SmartTag).

## Sub-GHz

### Spectrum
A live waterfall of the sub-GHz band on the **CC1101**, which reports a real RSSI per frequency (true signal strength, not just presence). **RIGHT cycles the display window**: the whole 300–928 MHz span, then aimed technical bands — **315** (car fobs / garage remotes / TPMS), **433** (alarms, remotes, sensors), **868** (EU LoRa / Meshtastic), **915** (US LoRa / Meshtastic), and a tight **433 zoom**. Same flicker-free rendering as the 2.4 GHz screen, with the quiet→busy colour legend. Receive-only. Needs a CC1101 module fitted.

### Freq finder
Find the frequency of **your own** sub-GHz remote or sensor. Hold it by the antenna and press its button; the CC1101 sweeps its tunable windows (300–348 / 387–464 / 779–928 MHz) and — after a two-pass **baseline calibration** that captures the ambient floor and the chip's own crystal spurs — shows the frequency of whatever *rises* above that baseline, refined to ~50 kHz with an `868 ISM`-style band hint. It's a live **rise-vs-frequency bar graph** (drift-corrected, crystal harmonics skipped), so a real button-press is a clean spike while spurs stay flat. **OK** toggles an 18 dB near-field attenuation so a tag held right at the antenna can't overload the front-end. Receive-only.

### Rec / Replay
Record and replay **your own** OOK/FSK devices — remotes, sensors — across 300–928 MHz. **Record** captures the on/off pulse train (an RSSI envelope for OOK, the GDO0 demodulator for FSK), then you name it on an **on-screen keyboard** and save it. **Playback** browses the saved library — which survives a reboot (stored on the flash filesystem) — replays a capture or deletes it. **Settings** (a phone captive portal) tune the listen time, exact frequency, capture threshold, replay repeats, modulation and polarity. Own-equipment only — no rolling-code capture and no replaying third-party signals.

## Settings

### Wi-Fi connect
Join **your own** Wi-Fi without a keyboard: the device raises an `ESP32-Leshy-setup` access point with a captive portal; you enter the SSID and password from your **phone**. Credentials are saved; the connection status (SSID / IP) is shown. This is also how the device gets online for updates.

### Update (OTA)
In-app firmware update straight from **GitHub releases**: it checks the latest release, and if newer, downloads the firmware over TLS into the spare OTA slot, verifies its **SHA-256**, and reboots into it. Time is synced by SNTP first (TLS needs a valid clock), the certificate chain is validated against the built-in Mozilla CA bundle, and the bootloader's anti-rollback reverts automatically if a bad image fails to boot. The device also **auto-checks for updates when it connects to Wi-Fi** and shows an amber arrow in the header when one is available.

### Language / Calibrate touch / About
Interface language (EN / RU), touch-screen re-calibration, and device info (hardware, firmware version, author).
