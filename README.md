# ESP32-Leshy 1.x

Read this in: **English** · [Русский](README.ru.md)

ESP32-Leshy 1.x is a from-scratch redesign of the firmware for the
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV) wireless multitool.

<!-- LESHY-ROADMAP:START -->
## Development status and roadmap

> **Now: S6 — Product differentiation: Targets, comparison, companion**
>
> Stage gates complete: 5 of 9.

This front-page snapshot is generated from the authoritative 1.x documentation; CI rejects it if it drifts. The checklist is complete for the accepted 55-capability 1.x baseline; the audit accepted eight additions and explicitly defers Peer Link until after 1.0 in the [feature-level audit](docs/v1/COMPETITIVE_ANALYSIS.md#feature-level-parity-audit).

- **Current phase:** `S6.5 — local USB/Web companion over shared Actions and schemas`.
- **Verified checkpoint:** `E-BUILD-204`/`E-AUTO-179`/`E-HIL-213`/`E-SAFETY-008`/`E-STORAGE-038`/`E-SURVEY-019`/`RB-M215` accept exact physical `1.0.0-dev.301` at source `d34a9b0c6f61d43b462b1a638ce1c7781fe77947`. The existing supervised Product Survey worker now owns exact-media reopen, atomic terminal commit and cleanup, so the UI task remains responsive to its Task WDT. Two consecutive mixed Wi-Fi+BLE passes commit generations 7 and 8 with 54 observations each, zero Wi-Fi/BLE/pipeline drops, exact CID and final Home/none/lease 0. Worker supervision ends armed with 2,263 heartbeats and zero expiry/trip. Exact dev.299 and dev.300 remain retained fail-closed evidence for synchronous UI-task commit and for interstage feeds that could not make one long SD primitive safe.
- **Next gate:** the 15th accepted focused delta makes the periodic full current-capability checkpoint mandatory. After it resets cadence, physically exercise a bounded malformed/unsigned `.lhau` file through the nested Automation Inspector and retain stable EN/RU summary frames with zero Action/HID/resource output. The real P-256 trust store and every execution path remain later independent gates. Positive Serial Console traffic still waits for an explicitly reviewed no-RF `mux56-3v3` fixture; optional GPS, physical HTTP parity and the deferred S5 RF carrier gate remain externally blocked.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S6.1 | Target foundation: stable Target IDs, exact radio identities, editable name/tags/notes/favorite and immutable source-evidence references, all bounded and host-verified | ✅ complete |
| S6.2 | Explainable correlation proposes links with features/confidence; accept/reject and reversible merge/split never destroy source evidence | ✅ complete |
| S6.3 | Baseline/diff compares two Sessions and classifies new, disappeared and changed Targets with every conclusion opening its evidence | ✅ complete |
| S6.4 | On-device Targets and Compare workflows expose the useful result first, stable navigation and full-area detail views | ✅ complete |
| S6.5 | Local USB/Web companion uses the same Actions and versioned schemas with scoped connectivity and secrets | 🟡 in progress |
| S6.6 | Integrated DEMO-S6 device/offline path is physically accepted; final phase completion waits for the deferred S5 physical predecessor gate before S6 acceptance | 🔴 blocked |

### User functionality in implementation order

| Functionality | Delivery stage | Status |
|---|---|---|
| Boot probe identifies the board profile, main/RF assembly and every capability state with evidence | S2 + S5 | 🟡 in progress |
| Capability-driven Home exposes only available jobs and explains disabled/conflicted/fault before launch | S2 | ✅ complete |
| Device → Self-Test/Diagnostics safely checks applicable hardware without TX and exports a report | S2 + S5 | ✅ complete |
| TFT, five keys and touch share Actions, calibration, stable selection and an accessible Back path | S2 | ✅ complete |
| Locally persisted EN/RU language, brightness, theme, quiet/sound and screen behavior | S2 + S5 | ✅ complete |
| Explicit Start/Stop creates a bounded multi-radio Survey Session with configuration and provenance | S3 + S6.6 | ✅ complete |
| Passive Wi-Fi scan: networks, hidden-name enrichment, security/channel/vendor facts and normalized Observations | S3 + S4 | ✅ complete |
| Shared stable List/Detail/filter behavior for Wi-Fi, BLE and other radios with all useful facts | S3 + S4 | ✅ complete |
| Immutable Capture preserves raw source, time, frequency/channel, RSSI, coordinates and receive settings | S3 + S4 | ✅ complete |
| Session/Capture commits are atomic and recover after reset and controlled power loss | S3 + S5 | 🔴 blocked |
| Library opens Sessions/Captures offline with list/detail/search/filter and visible integrity state | S3 + S6 | ✅ complete |
| Export provides JSON/CSV summaries, PCAP and portable radio formats with exact provenance | S3 + S5 | 🟡 in progress |
| SD/LittleFS exposes identity, capacity, recovery, integrity and degraded behavior | S3 + S5 | ✅ complete |
| Passive BLE scan: strongest-first devices, company/service facts and normalized Observations without active probes | S4 | ✅ complete |
| Three nRF24 receivers: RX-only spectrum, receiver-paced one-pixel waterfall and background-calibrated 2.4 GHz signal finder | S4 + S5.3 | 🔴 blocked |
| CC1101: RX-only Sub-GHz spectrum/activity, one-pixel waterfalls and frequency/RSSI finder for 315/433/868/915 MHz | S4 + S5.4 | 🔴 blocked |
| GPS adds fix, satellites, time and track to a Session only for an explicit compatible assembly | S4 + S5 | ⬜ later |
| Shared timeline exposes sources, duty cycle, temporary unavailability, degradation and dropped events | S4 + S6.6 | ✅ complete |
| Network/device Radar/localize: RSSI history, trend/range and honest proximity limits | S4 + S6 | 🟡 in progress |
| Wi-Fi channel/packet monitor: current/mean load for 1–13, explainable free channel and bounded PCAP with drop counters | S4 | ✅ complete |
| Visible power/charge/reset reason, low-voltage safe write and verifiable sleep/resume | S5 | 🔴 blocked |
| SD, USB and local-companion import/export uses versioned schemas and a fail-closed parser | S5 + S6 | 🟡 in progress |
| IR receive/decode preserves original and derived data, cold-reopens in Library and exports CSV | S5.2 | ✅ complete |
| Sub-GHz RAW/OOK/FSK Capture preserves pulses, radio parameters and derived decodes | S5.4 | 🔴 blocked |
| PN532 reads tag/NDEF facts and a versioned dump only for an explicit non-conflicting assembly | S5 | 🔴 blocked |
| User saves a real-TFT screenshot with build/state/time provenance and opens it in Library/export | S5 | ⬜ later |
| One feedback service owns antenna LEDs and buzzer: default 2/255, quiet mode, bounded tones and non-color-only cues | S5 + S6 | ✅ complete |
| Local logs, crash journal and exportable diagnostic bundle without a cloud dependency | S6 + S8 | 🟡 in progress |
| A Target preserves stable identities, Observation history and links to immutable source evidence | S6.1 + S6.4 | ✅ complete |
| Target name, tags, notes and favorite are bounded edits that survive cold reopen | S6.1 + S6.4 | ✅ complete |
| Explainable correlation shows features/confidence; review, accept/reject and merge/split are reversible | S6.2 + S6.4 | ✅ complete |
| Session baseline/diff shows new, disappeared and changed Targets | S6.3 + S6.4 | ✅ complete |
| Every compare/correlation conclusion opens its exact source evidence | S6.3 + S6.4 | ✅ complete |
| Scoped local USB/Web companion browses, searches, compares and exports through shared Actions/schemas | S6.5 | 🟡 in progress |
| Offline OUI/BLE company/service/protocol profiles enrich facts with version/provenance without replacing raw evidence | S6 | ✅ complete |
| Scoped Wi-Fi/USB setup isolates secrets, never exports them and never makes networking a Survey/Library prerequisite | S6 + S8 | 🟡 in progress |
| Separate Lab exposes authorized scope, source, frequency, power, duration and permanently visible TX state | S7 | ⬜ later |
| Back, timeout, panic, fault or loss of control/telemetry physically stops every TX path | S7 | ⬜ later |
| IR replay is available only from a selected immutable Capture after preview and explicit confirmation | S7 | ⬜ later |
| Sub-GHz replay/TX from an immutable Capture passes ResourceBroker, bounds, confirmation, countdown and stop result | S7 | ⬜ later |
| NFC write/restore of a supported owned tag exposes preview, verify and the original recovery dump | S7, conditional hardware | ⬜ later |
| Protocol Workbench compares pulses/waveforms, annotates fields and stores a derived decode without changing raw source | S7 | ⬜ later |
| Permissioned app descriptor declares capabilities, resources, permissions, safety policy and UI strings before launch | S7 | ⬜ later |
| Versioned decoder/profile packages have a compatibility gate, integrity/signature and scoped storage | S7 + S8 | ⬜ later |
| SDK, sample extension and simulator trace kit cannot bypass ResourceBroker, permissions or Safety Supervisor | S7 | ⬜ later |
| Airspace Guard passively detects/explains suspicious Wi-Fi/BLE conditions and opens exact evidence/uncertainty for every finding | S7 | ✅ complete |
| Focused Wi-Fi authentication Capture reports EAPOL/PMKID and complete/incomplete handshakes, then exports PCAP and `hc22000` | S7 | ✅ complete |
| Offline Field Survey joins Wi-Fi AP/station and BLE observations with optional GPS track, revisit comparison and WiGLE-compatible export | S7 | 🟡 in progress |
| BLE Inspector preserves raw compatible packets and enters connected GATT only after explicit target/permission/lease confirmation | S7 | ✅ complete |
| Device Lock protects secrets/evidence with local PIN, bounded retry and tested recovery without blocking Stop/panic/recovery | S7 | ✅ complete |
| Device → Serial Console provides a bounded UART bridge and shared Actions CLI under explicit target/configuration/lease | S7 | 🟡 in progress |
| Permissioned signed Automation/HID has preview, ceilings, finite runtime, scoped target and passive-by-default BadUSB inspection | S7 | 🟡 in progress |
| Authorized wireless Lab ships only named, individually accepted Wi-Fi/BLE/nRF fixture recipes with bounded power/channel/time and physical stop | S7 | ⬜ later |
| Browser install and Device → Update: signed stable/beta OTA, rollback and recovery image | S8 | ⬜ later |
| Versioned backup/restore and factory reset show scope/preview/checksum and never overwrite raw Capture without confirmation | S8 | ⬜ later |

### Roadmap

- ✅ **S0 — Governance and generation boundary** · complete
- ✅ **S1 — Evidence baseline: users, competitors, and hardware** · complete
- ✅ **S2 — Clean 1.x platform** · complete
- ✅ **S3 — First vertical slice: Survey Session** · complete
- ✅ **S4 — Cross-radio passive platform** · complete
- 🔴 **S5 — Complete ESP32-DIV hardware** · blocked
- 🟡 **S6 — Product differentiation: Targets, comparison, companion** · in progress
- ⬜ **S7 — Competitive completeness, Safe Lab, and extensibility** · later
- ⬜ **S8 — Release hardening and 1.0.0** · later

[live status and next evidence gate](docs/v1/STATUS.md) · [stage outcomes and exit gates](docs/v1/DELIVERY_PLAN.md) · [complete functionality map](docs/v1/DELIVERY_PLAN.md#product-functionality-map)
<!-- LESHY-ROADMAP:END -->

## Security audit and authorized Lab

Leshy does not hide security capabilities behind the generic word “multitool.” The
table below names the accepted user outcome, its operating boundary, and its honest
current status. The complete scope and requirement provenance live in the
[feature-level competitor
audit](docs/v1/COMPETITIVE_ANALYSIS.md#feature-level-parity-audit), [product
requirements](docs/v1/PRODUCT_REQUIREMENTS.md), and [live status](docs/v1/STATUS.md).

| Mode | User outcome | 1.x status |
|---|---|---|
| **Passive audit** | **Airspace Guard (CF-001):** RX-only warnings for disconnect bursts, conflicting-twin/PineAP-like behavior, suspicious BLE tracker/skimmer/drone identifiers, and sustained elevated noise; every finding opens its source evidence and uncertainty | ✅ physically accepted in exact `1.0.0-dev.242`; DEMO-S7 remains open for the other S7 capabilities |
| **Passive audit** | **Wi-Fi authentication Capture (CF-002):** distinguishes EAPOL/PMKID and complete/incomplete handshakes, preserves a focused Capture, and exports PCAP/`hc22000` | ✅ physically accepted in exact `1.0.0-dev.255`: explicit atomic Save, cold exact-CID recovery, two-frame radiotap PCAP and one canonical `WPA*02` export pass without retained private/raw evidence |
| **Passive audit** | **Field Survey (CF-003):** Wi-Fi AP/station and BLE observations with deduplication, revisit comparison, an optional GPS track, and local WiGLE-compatible export | 🟡 active, S7: exact dev.263 physically accepts first/revisit recovery and bounded native plus truthful untimed/unlocated WiGLE export; live station capture and optional trusted GPS/UTC remain open |
| **Passive audit** | **BLE Inspector, receive path (CF-004):** preserves compatible raw advertising records with provenance; this is not a promise of arbitrary BLE link-layer sniffing | ✅ physically accepted in exact `1.0.0-dev.270`: selected-device Raw packets, bounded capture/freeze, incremental TFT and versioned local export pass with clean receive-only teardown |
| **Passive audit** | **BadUSB inspection (CF-008):** parses a signed Automation/HID script and previews its target, permissions, actions, and bounds without executing it | 🟡 exact host/build dev.286 accepts the bounded zero-output parser and admission foundation; compact product Inspector UI is next, while real trust and execution remain disconnected |
| **Safe Lab** | **Named wireless fixtures (CF-009):** individually accepted Wi-Fi/BLE/nRF recipes for an owned test fixture with selected source/target, channel, power/rate, duration, lease, and a verifiable Stop | ⬜ planned, S7; every recipe has its own safety acceptance |
| **Safe Lab** | **Owned signals and tags:** IR replay only from an immutable Capture; NFC write/restore with preview, verification, and a recovery dump; Sub-GHz replay only after a physical Stop has been proven | ⬜ planned; NFC requires PN532, and CC1101 TX is currently blocked |
| **Active-confirmed** | **BLE Inspector, GATT path (CF-004):** connects only to an explicitly selected device and enumerates services/characteristics under separate permission and lease | ✅ exact `1.0.0-dev.276`: explicit permission and second confirmation, live bounded enumeration, wrong-peer/timeout/resource/disconnect-failure cleanup and positive recovery are physically accepted with zero pair/read/write/subscribe operations |
| **Active-confirmed** | **Device Lock (CF-006):** local PIN, bounded retry/recovery, and protection for secrets/evidence without blocking Stop, panic, or recovery | ✅ exact dev.283 physically accepts authenticated encrypted product storage and exact-CID read-only cold reopen after dev.281 accepted recovery/admission; CAP-052 is complete, S7 |
| **Active-confirmed** | **Serial Console (CF-007):** bounded UART monitor/bridge for a selected external device and the shared Actions CLI without bypassing policy/leases | 🟡 exact dev.285 accepts the product UI/CLI and stock RF-shield fail-closed path; positive UART traffic still requires a reviewed no-RF fixture; arbitrary raw GPIO control is outside the product |
| **Active-confirmed** | **Automation/HID execution (CF-008):** runs only a signed, permissioned script after previewing the target, actions, ceilings, and finite duration | ⬜ planned, S7; dev.286 deliberately provides no HID/Action output path |

**Hardware and safety boundary:** the portable baseline is 16 MB flash and 0 usable
PSRAM; the RF shield, GPS, and PN532 are always established by probe/profile rather
than a board name. The three nRF paths can be physically disabled through `CE`, but
ESP32-DIV cannot independently reset or power-gate the CC1101, so its TX/replay path
remains forbidden until separate physical-stop evidence exists. The stock assembly
has proven useful CC1101 RF behavior at 433 MHz; software tuning to 315/868/915 MHz
does not prove physical RF efficiency. See the [hardware
envelope](docs/v1/HARDWARE_ENVELOPE.md) and [Safety
Supervisor](docs/v1/SAFETY_SUPERVISOR.md).

**Explicitly outside 1.0:** `CF-005 Peer Link` between two DIVs is deferred until
after 1.0. Jamming, indiscriminate flood/spam, crash, credential harvesting, and
disruptive clone workflows are not Leshy goals. The comparison used only official
primary sources: [ESP32-DIV](https://github.com/CiferTech/ESP32-DIV),
[GhostESP](https://github.com/GhostESP-Revival/GhostESP),
[Bruce](https://github.com/brucedevices/firmware), [ESP32
Marauder](https://github.com/justcallmekoko/ESP32Marauder), and [Flipper
Zero](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/ReadMe.md).

Released 0.x remains a frozen proof-of-concept line; no user-facing 1.x binary has
been released yet.

## Version lines

- **0.x — archived PoC:** existing menu firmware, feature list, hardware notes, and
  development guide are preserved in the [0.x archive](docs/archive/v0.x/README.md).
  The [web installer](https://anton-vinogradov.github.io/esp32-leshy/) currently flashes
  this line.
- **1.x — active redesign:** product discovery, architecture, and the new
  capability/resource-aware application runtime live under [docs/v1](docs/v1/README.md).

Existing redesign checkpoints through `0.207` keep their immutable evidence names.
The next source-bearing build is `1.0.0-dev.208`; phase-complete candidates use
`1.0.0-rc.N`, and the first stable redesign release is `1.0.0`.

## What 1.x is building

Leshy is becoming a field instrument organized around a complete workflow:

> discover → identify → locate → capture → compare → reproduce safely in your own lab
> → preserve and export the evidence.

The product is organized around Survey, Targets, Capture, Lab, Library, and Device
rather than a growing list of unrelated radio screens. Wi-Fi, BLE, NRF24, CC1101,
IR, NFC, GPS, and storage become capabilities shared by those workflows.

## Start here

- [Documentation index](docs/README.md)
- [Current status](docs/v1/STATUS.md)
- [Documentation governance](docs/v1/GOVERNANCE.md)
- [Stages to 1.0.0](docs/v1/DELIVERY_PLAN.md)
- [Goal traceability](docs/v1/TRACEABILITY.md)
- [Product vision](docs/v1/VISION.md)
- [Competitive analysis](docs/v1/COMPETITIVE_ANALYSIS.md)
- [Product requirements](docs/v1/PRODUCT_REQUIREMENTS.md)
- [Hardware envelope and conflicts](docs/v1/HARDWARE_ENVELOPE.md)
- [Target architecture](docs/v1/ARCHITECTURE.md)
- [0.x documentation archive](docs/archive/v0.x/README.md)

## Development

Documentation defines the 1.x scope and gates. Current code, prototype, and
verification state lives only in [STATUS](docs/v1/STATUS.md). The front-page roadmap
is generated from that status and the delivery plan, keeping this README from becoming
a competing source of truth.

```bash
python3 tools/readme_roadmap.py --write
python3 tools/check_docs.py
tools/test.sh
tools/build.sh
```

## Responsible use

Use Leshy only with equipment you own or are explicitly authorized in writing to test.
Passive observation is the default. Transmit and replay workflows belong to an explicit
Lab context with visible state, bounded duration, and immediate stop. Full terms:
[DISCLAIMER.md](DISCLAIMER.md).

## License and credit

[MIT](LICENSE). Hardware and the original firmware are by
[CiferTech](https://github.com/CiferTech/ESP32-DIV). Leshy is independent and unofficial.
