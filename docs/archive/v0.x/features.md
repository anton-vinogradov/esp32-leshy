# ESP32-Leshy — Features

> **Archived 0.x documentation.** This describes the proof-of-concept firmware line
> and is kept for users of existing 0.x builds. See [the 1.x documentation](../../README.md).

*Read this in: **English** · [Русский](features.ru.md)*

What the 0.x firmware does on real ESP32-DIV hardware, in a touch- and keypad-driven menu. Everything here is **passive / defensive / own-equipment** — see [DISCLAIMER.md](../../../DISCLAIMER.md).

## Menu map

```
ESP32-Leshy
├─ Wi-Fi
│  ├─ Wi-Fi Scan        signal · channel · security · vendor · ★your net · hidden
│  │  └─ ▶ on a network  Details (BSSID · channel · RSSI · security · vendor · WPS model) · Radar
│  ├─ Channels 2.4G     scrolling real per-channel airtime graphs (promiscuous; 1/6/11)
│  ├─ Spectrum 2.4G     raw band waterfall over 2400-2525 MHz (NRF24 carrier detect)
│  ├─ Freq finder 2.4   which channel a 2.4 GHz signal is on (NRF24 hit-rate vs baseline)
│  ├─ Laboratory        (transmits — own gear)
│  │  ├─ Generator      Run (carrier/noise into channels + sweep beacon) · TX mode (Verify / Maximum)
│  │  └─ Portal         own-named AP with a "lower your power" consent page (Setup · Raise)
│  └─ Advanced
│     ├─ Hidden names   revealed hidden SSIDs (saved to flash, deletable)
│     ├─ Deauth monitor passive alarm on deauth/disassoc bursts
│     ├─ Clients        client devices (stations) on the air · OK = radar
│     └─ TX power       2.4 GHz radiation power (0 … -18 dBm)
├─ BLE
│  └─ BLE Scan          nearby devices · type/brand tags · trackers · OK = radar · ▶ = details
├─ Sub-GHz
│  ├─ Spectrum          sub-GHz waterfall, RIGHT cycles bands (CC1101 RSSI)
│  ├─ Test TX           transmit a test signal (own gear)
│  ├─ Rec + replay      Record (→ name → save) · Playback library · Settings
│  ├─ Freq finder       find your own remote's frequency (rise-vs-freq graph)
│  └─ TX power          sub-GHz radiation power
└─ Settings
   ├─ Wi-Fi connect     set up from your phone (captive portal) · status
   ├─ Update            OTA from GitHub releases
   ├─ Language          English / Русский
   ├─ Device            Status LEDs · Screen light · Calibrate touch
   ├─ About
   └─ Responsible use   the legal notice (read to accept)
```

Navigation: **▲▼** move, **middle** = enter/confirm, **▶** = options for the selected item, **◀** = back. Touch works too.

## Wi-Fi

### Wi-Fi Scan
Live list of nearby access points. Each row shows the name, a small **sparkline of that AP's signal over recent scans** (its footprint over time), the **channel**, and the **RSSI**. Your own network is marked **★** (matched by BSSID — even when it is hidden). Select a row and press **▶** for **per-network options**: **Details** and **Radar**. Details shows BSSID, channel, RSSI, security and hidden/own, plus the **maker** (from the MAC's OUI — see *Device database*) and, when the access point advertises **WPS**, its actual **model** read live from the beacon (e.g. `MikroTik C53UiG+5H`, or *no WPS* if it doesn't advertise it). Radar walks you to the access point by signal — see *Finding things: Radar*.

### Channels 2.4G
A live, scrolling **area graph per channel (1–13)** — a cardiograph of how busy each channel really is. It listens in **promiscuous mode** and sums the on-air time of the frames it hears (management + data + control), sweeping the channels one at a time, so a channel with one busy access point outranks a channel crowded with idle ones. This is **actual airtime, not access-point count**. The value is a **lower bound** (only frames the radio decodes are counted, and the rate is estimated), so quiet air shows a small baseline and a genuine download or stream clearly rises above it. The non-overlapping channels **1 / 6 / 11** are highlighted. Uses the radio exclusively, so the background scan pauses while this screen is open.

### Spectrum 2.4G
A live **waterfall of the whole 2.4 GHz band** (2400–2525 MHz), painted with a separate **NRF24** radio while the ESP32's own Wi-Fi stays free. The NRF24 has no spectrum analyzer, but its carrier detector (RPD) latches on any signal above ~-64 dBm; sweeping all 126 one-MHz channels and colouring each by how often it fires builds a heat map — newest scan on top, flowing down. It sees **more than Wi-Fi**: Bluetooth, wireless video, drones, microwaves — anything radiating in the band shows up. Wi-Fi channels **1 / 6 / 11** are marked on the frequency axis. Needs an NRF24 module fitted (slot 2 on the ESP32-DIV v2).

### Freq finder 2.4
Point it at a 2.4 GHz gadget of **your own** — a remote, a tag, a drone controller — and it tells you **which channel** the signal is on. It sweeps all 126 NRF24 channels measuring a per-channel **hit-rate**, then subtracts a calibrated **baseline** (the constant Wi-Fi/Bluetooth floor) so only a channel that *rises* when your device transmits survives — drawn as a live bar graph with Wi-Fi **1 / 6 / 11** marked and the peak read out as `2400 + channel` MHz. Calibrate first (a couple of seconds, don't transmit), then press your device's button. Receive-only.

### Laboratory → Generator
An **own-equipment** 2.4 GHz test transmitter on the NRF24 modules. Pick a Wi-Fi channel with **▲▼** (the carrier follows the caret live), arm one or more channels with **OK**, and start/stop a static carrier with a short **▶**. A long **▶** starts an **auto-sweep** — one carrier marching across channels 1–13 — a low-power test beacon to prove reception on your own second device. Armed channels get an up-arrow and the header shows the live TX channel. Low power (a −18 dBm carrier), own-equipment bench use — **not a jammer** (no max-power all-channel blast). Under Generator, **Run** is that screen and **TX mode** picks *Verify* (one NRF24 keeps receiving so the waterfall stays live) or *Maximum* (all radios transmit); the radiated level is set by **Advanced → TX power** (0 … -18 dBm).

### Laboratory → Portal
A **polite** captive portal: an access point you name yourself, serving a single consent page that asks people to turn their Wi-Fi power down — **no password fields, no cloning of anyone else's SSID**. **Setup** names the point from your phone, **Raise** brings it up with the consent page. Own-named point only, one AP/portal at a time.

### Advanced → Clients
Lists Wi-Fi **client devices (stations)** — the phones, laptops and gadgets talking to access points — which a normal scan never shows. It sniffs raw 802.11 in **promiscuous mode**, pulls the station address out of data frames and probe requests, hops channels 1–13, and lists each station's MAC, the access point it's on (or *searching* for an unassociated one), its **maker** (from the OUI), and RSSI, strongest first. Press **OK** on a station for the **radar**. Receive-only, passive observation.

### Advanced → Hidden names
Hidden networks broadcast an empty SSID, but the name still travels in cleartext inside **Probe-Response** and **(Re)Association** frames. While scanning, the device passively recovers those names **only for the BSSIDs the scan actually sees as hidden**, saves them to flash (they survive a reboot), and lists them here with delete. It is passive — a name appears only when there is real traffic to that network (a client probing or connecting).

### Advanced → Deauth monitor
A passive, receive-only alarm: it watches the air (hopping channels) and flags bursts of **deauthentication / disassociation** frames — the signature of a deauth attack against a nearby network. Shows the count in a window, the total, the current channel and the last source MAC. Defensive only.

## Finding things: Radar

A shared "hotter / colder" finder that walks you toward a specific transmitter by its **live signal**. Concentric rings bloom outward as you close in, with the smoothed RSSI, a rough distance and a closer/farther trend; **OK** toggles an optional **Geiger-style proximity beep** on the buzzer (faster as you approach). Reached from three places — **BLE Scan → OK** (a tag, earbuds, a phone), **Wi-Fi network options → Radar** (an access point / router), and **Clients → OK** (a Wi-Fi client). Caveats: privacy-random MACs (phones, AirTags) rotate every ~15 min, so a lock is good for one hunt, not forever; a Wi-Fi client is only audible while it transmits, so a busy one (a speaker, a streaming phone) tracks smoothly and an idle one sits in a *searching* state.

## BLE

### BLE Scan
Lists nearby Bluetooth-LE devices, **sorted by signal (nearest first)**. Each row leads with a cyan **tag guessing what the device is**: from the standard BLE *Appearance* code and service UUIDs it tells apart AirPods / iBeacon / watch / keyboard / mouse / thermometer, and otherwise falls back to the **maker** (Apple, Samsung, Xiaomi…, from the advertised company ID — see *Device database*). Known **trackers** are flagged in amber — **Apple Локатор** (Find My), Tile, SmartTag — the anti-stalking case: a stray tag riding along with you shows up here. A small **фикс** marks a device on a fixed, public (trackable) MAC, as opposed to a privacy-rotating one.

Press **OK** on a device for the **radar** (*Finding things: Radar*), or **▶** for **Details**.

### Details (▶)
The full advertisement, laid out: address + address type (public / random), signal + distance + advertised TX power, name, guessed type, GAP appearance, first service, and maker. **OK** from here jumps to the radar.

## Sub-GHz

### Spectrum
A live waterfall of the sub-GHz band on the **CC1101**, which reports a real RSSI per frequency (true signal strength, not just presence). **RIGHT cycles the display window**: the whole 300–928 MHz span, then aimed technical bands — **315** (car fobs / garage remotes / TPMS), **433** (alarms, remotes, sensors), **868** (EU LoRa / Meshtastic), **915** (US LoRa / Meshtastic), and a tight **433 zoom**. Same flicker-free rendering as the 2.4 GHz screen, with the quiet→busy colour legend. Receive-only. Needs a CC1101 module fitted.

### Test TX
Transmit a **test signal** on the CC1101 to prove your own receiver / spectrum end-to-end. Own-equipment only; the radiated level is set by **Sub-GHz → TX power**.

### Freq finder
Find the frequency of **your own** sub-GHz remote or sensor. Hold it by the antenna and press its button; the CC1101 sweeps its tunable windows (300–348 / 387–464 / 779–928 MHz) and — after a two-pass **baseline calibration** that captures the ambient floor and the chip's own crystal spurs — shows the frequency of whatever *rises* above that baseline, refined to ~50 kHz with an `868 ISM`-style band hint. It's a live **rise-vs-frequency bar graph** (drift-corrected, crystal harmonics skipped), so a real button-press is a clean spike while spurs stay flat. **OK** toggles an 18 dB near-field attenuation so a tag held right at the antenna can't overload the front-end. Receive-only.

### Rec / Replay
Record and replay **your own** OOK/FSK devices — remotes, sensors — across 300–928 MHz. **Record** captures the on/off pulse train (an RSSI envelope for OOK, the GDO0 demodulator for FSK), then you name it on an **on-screen keyboard** and save it. **Playback** browses the saved library — which survives a reboot (stored on the flash filesystem) — replays a capture or deletes it. **Settings** (a phone captive portal) tune the listen time, exact frequency, capture threshold, replay repeats, modulation and polarity. Own-equipment only — no rolling-code capture and no replaying third-party signals.

## Device database (offline maker lookup)

The vendor and type names come from small reference tables the device carries on its flash: **Bluetooth SIG company IDs** (~4000) and **IEEE OUIs** (~40000). They let it name the maker of almost anything it sees — **offline**, no phone, no internet — including privacy-random BLE devices (via the advertised company ID) and Wi-Fi access points and clients (via the MAC OUI). The database is **optional**: the **web installer flashes it alongside the firmware**, and the plain `firmware.bin` runs fine without it, falling back to a short built-in vendor list. (An OTA update refreshes only the firmware, not the database.)

## Settings

### Wi-Fi connect
Join **your own** Wi-Fi without a keyboard: the device raises an `ESP32-Leshy-setup` access point with a captive portal; you enter the SSID and password from your **phone**. Credentials are saved; the connection status (SSID / IP) is shown. This is also how the device gets online for updates.

### Update (OTA)
In-app firmware update straight from **GitHub releases**: it checks the latest release, and if newer, downloads the firmware over TLS into the spare OTA slot, verifies its **SHA-256**, and reboots into it. Time is synced by SNTP first (TLS needs a valid clock), the certificate chain is validated against the built-in Mozilla CA bundle, and the bootloader's anti-rollback reverts automatically if a bad image fails to boot. The device also **auto-checks for updates when it connects to Wi-Fi** and shows an amber arrow in the header when one is available.

### Language / Device / About / Responsible use
**Language** — interface language (English / Русский). **Device** — the hardware knobs: Status-LED brightness, screen backlight, and touch re-calibration. **About** — hardware, firmware version, author. **Responsible use** — the legal notice accepted on first boot (readable again any time).
