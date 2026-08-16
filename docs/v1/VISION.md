# ESP32-Leshy 1.x product vision

*Read in: **English** · [Русский](VISION.ru.md)*

## One sentence

Leshy should become a field instrument for researching signals and devices, not a
bag of radio-specific functions:

> discover → identify → locate → capture → compare → reproduce safely in your own
> lab → preserve and export the evidence.

A menu entry is not a product outcome. A complete, consistent workflow across Wi-Fi,
BLE, Sub-GHz, IR, and NFC is.

## Product structure

The future home screen is organized around jobs:

1. **Survey** — a resource-compatible Wi-Fi/BLE/2.4 GHz/Sub-GHz/GPS survey with one
   observation timeline.
2. **Targets** — durable AP, station, BLE device, tag, and remote identities with
   details, history, notes, correlations, and a shared radar action.
3. **Capture** — PCAP, raw Sub-GHz, IR, NFC dumps, location, and screenshots with a
   common metadata envelope.
4. **Lab** — authorized TX/replay workflows, visibly separated from passive tools and
   governed by a safety policy.
5. **Library** — observations, captures, decoded protocols, favorites, import/export.
6. **Device** — detected modules, diagnostics, power, connectivity, updates, settings.

Radios remain useful filters and expert views, but they are no longer the only way to
find a task.

## Competitive position

The review covered [ESP32-DIV](https://github.com/CiferTech/ESP32-DIV),
[Bruce](https://github.com/BruceDevices/firmware),
[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder), and the application
model of [Flipper Zero](https://github.com/flipperdevices/flipperzero-firmware).

| Project strength | Leshy response |
|---|---|
| ESP32-DIV uses the full board | Reach hardware parity without inheriting global state and multi-thousand-line modules. |
| Bruce supports many boards and scripts | Optimize one platform more deeply, with coherent workflows and explicit resources. |
| Marauder has mature Wi-Fi capture/monitor flows | Correlate Wi-Fi with BLE, external radios, GPS, and a common evidence library. |
| Flipper has apps, stable formats, SDK, and polished UX | Bring that discipline to ESP32-DIV while exploiting its color touch display, Wi-Fi, and multiple radios. |

Leshy's existing passive reconnaissance, bilingual UI, offline vendor database, web
installer, and rollback-capable OTA remain strengths. The differentiator is workflow
coherence, data quality, and reliability—not raw feature count.

## Principles

1. Observation and original evidence come first.
2. List/detail/radar/capture/library patterns are shared by every radio.
3. Detected hardware capabilities drive the UI.
4. Transmission is always visible, bounded, and immediately stoppable.
5. Core use is offline-first.
6. User data uses documented, versioned, exportable formats.
7. A stable SDK eventually lets apps and decoders ship without rebuilding the kernel.

## Success measures

- cold boot to an interactive home screen in at most 2 seconds;
- Back exits any app in at most 150 ms and releases every lease;
- no app touches a shared radio, SPI bus, or UART without a resource lease;
- an 8-hour survey has no heap growth, UI stall, or file corruption;
- capture parsers run in host tests and malformed input never reboots the device;
- every app declares capabilities, resources, and safety level;
- firmware plus standard apps pass build and smoke/HIL gates before release.

## Non-goals

- copying every offensive feature from competing firmware;
- supporting dozens of ESP32 boards before the ESP32-DIV architecture is stable;
- requiring a cloud account;
- covert transmission, credential collection, or use against equipment without explicit authorization.
