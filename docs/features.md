# ESP32-Leshy — Features

*Read this in: **English** · [Русский](features.ru.md)*

What the firmware does today, on real ESP32-DIV hardware, in a touch- and keypad-driven menu. Everything here is **passive / defensive / own-equipment** — see [DISCLAIMER.md](../DISCLAIMER.md).

## Menu map

```
ESP32-Leshy
├─ Wi-Fi
│  ├─ Wi-Fi Scan        signal · channel · security · ★your net · hidden; select a row, ▶ = per-network options
│  ├─ Channels 2.4G     scrolling per-channel airtime graphs (1/6/11 highlighted)
│  └─ Advanced
│     ├─ Hidden names   revealed hidden SSIDs (saved to flash, deletable)
│     └─ Deauth monitor passive alarm on deauth/disassoc bursts
├─ BLE
│  └─ BLE Scan          nearby devices + tracker detector
├─ Sub-GHz
│  └─ Recorder          315/433/868 MHz (coming, needs CC1101)
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
A live, scrolling **area graph per channel (1–13)** built from the scan — a cardiograph of how busy each channel is, so you can see at a glance where it is empty and where it is crowded. The non-overlapping channels **1 / 6 / 11** are highlighted.

### Advanced → Hidden names
Hidden networks broadcast an empty SSID, but the name still travels in cleartext inside **Probe-Response** and **(Re)Association** frames. While scanning, the device passively recovers those names **only for the BSSIDs the scan actually sees as hidden**, saves them to flash (they survive a reboot), and lists them here with delete. It is passive — a name appears only when there is real traffic to that network (a client probing or connecting).

### Advanced → Deauth monitor
A passive, receive-only alarm: it watches the air (hopping channels) and flags bursts of **deauthentication / disassociation** frames — the signature of a deauth attack against a nearby network. Shows the count in a window, the total, the current channel and the last source MAC. Defensive only.

## BLE

### BLE Scan
Lists nearby Bluetooth-LE devices and flags known **trackers** (Apple Find My / Tile / Samsung SmartTag).

## Sub-GHz

### Recorder
Record / replay 315–868 MHz — **coming**, needs the CC1101 module.

## Settings

### Wi-Fi connect
Join **your own** Wi-Fi without a keyboard: the device raises an `ESP32-Leshy-setup` access point with a captive portal; you enter the SSID and password from your **phone**. Credentials are saved; the connection status (SSID / IP) is shown. This is also how the device gets online for updates.

### Update (OTA)
In-app firmware update straight from **GitHub releases**: it checks the latest release, and if newer, downloads the firmware over TLS into the spare OTA slot, verifies its **SHA-256**, and reboots into it. Time is synced by SNTP first (TLS needs a valid clock), the certificate chain is validated against the built-in Mozilla CA bundle, and the bootloader's anti-rollback reverts automatically if a bad image fails to boot. The device also **auto-checks for updates when it connects to Wi-Fi** and shows an amber arrow in the header when one is available.

### Language / Calibrate touch / About
Interface language (EN / RU), touch-screen re-calibration, and device info (hardware, firmware version, author).
