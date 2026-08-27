# ESP32-Leshy 1.x

Read this in: **English** · [Русский](README.ru.md)

ESP32-Leshy 1.x is a from-scratch redesign of the firmware for the
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV) wireless multitool.

<!-- LESHY-ROADMAP:START -->
## Development status and roadmap

> **Now: S6 — Product differentiation: Targets, comparison, companion**
>
> Stage gates complete: 5 of 9.

This front-page snapshot is generated from the authoritative 1.x documentation; CI rejects it if it drifts.

- **Current phase:** `S6.5 — local USB/Web companion over shared Actions and schemas`.
- **Verified checkpoint:** exact `1.0.0-dev.209` at firmware source `e04d98dd3c5e5d494c615e12f2897dc3207272a9` is physically accepted for the **lifecycle-disjoint real Wi-Fi+BLE Product Survey** boundary in `E-BUILD-158`/`E-AUTO-131`/`E-HIL-188`/`E-SURVEY-017`. One exact application flash plus one no-flash rerun after a runner-only navigation correction proves exact-CID boot, one cycle per source, 12 Wi-Fi + 35 BLE observations with zero drops/errors, six persisted timeline windows, generation 162→163 commit, cold reopen/export of all 47 observations, invariant boot heap and final Home/none/lease 0 with safety armed. The first run already passed the product boundary and independently cleaned up; only its obsolete one-Back Home assertion was rejected. No host network tool runs and active Mac Wi-Fi/Cardputer are untouched.
- **Next gate:** run the prepared no-second-flash integrated DEMO-S6 continuity over the accepted Survey/Targets/Compare/offline-USB chain. Physical HTTP parity remains deferred to a dedicated idle adapter or external client, and the physical S5 gate remains postponed, not waived, until the replacement DIV arrives and passes its read-only profile.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S6.1 | Target foundation: stable Target IDs, exact radio identities, editable name/tags/notes/favorite and immutable source-evidence references, all bounded and host-verified | ✅ complete |
| S6.2 | Explainable correlation proposes links with features/confidence; accept/reject and reversible merge/split never destroy source evidence | ✅ complete |
| S6.3 | Baseline/diff compares two Sessions and classifies new, disappeared and changed Targets with every conclusion opening its evidence | ✅ complete |
| S6.4 | On-device Targets and Compare workflows expose the useful result first, stable navigation and full-area detail views | ✅ complete |
| S6.5 | Local USB/Web companion uses the same Actions and versioned schemas with scoped connectivity and secrets | 🟡 in progress |
| S6.6 | Integrated DEMO-S6: record and compare two surveys, inspect each conclusion on-device or locally, export offline, then return to and close the deferred S5 physical predecessor gate before S6 acceptance | ⬜ later |

### User functionality

| Functionality | Delivery stage | Status |
|---|---|---|
| Boot probe identifies the board profile, main/RF assembly and every capability state with evidence | S2 + S5 | 🟡 in progress |
| Capability-driven Home exposes only available jobs and explains disabled/conflicted/fault before launch | S2 | ✅ complete |
| Device → Self-Test/Diagnostics safely checks applicable hardware without TX and exports a report | S2 + S5 | ✅ complete |
| TFT, five keys and touch share Actions, calibration, stable selection and an accessible Back path | S2 | ✅ complete |
| Locally persisted EN/RU language, brightness, theme, quiet/sound and screen behavior | S2 + S5 | ✅ complete |
| Visible power/charge/reset reason, low-voltage safe write and verifiable sleep/resume | S5 | 🔴 blocked |
| Browser install and Device → Update: signed stable/beta OTA, rollback and recovery image | S8 | ⬜ later |
| Local logs, crash journal and exportable diagnostic bundle without a cloud dependency | S6 + S8 | 🟡 in progress |
| Explicit Start/Stop creates a bounded multi-radio Survey Session with configuration and provenance | S3 + S6.6 | 🟡 in progress |
| Passive Wi-Fi scan: networks, hidden-name enrichment, security/channel/vendor facts and normalized Observations | S3 + S4 | ✅ complete |
| Passive BLE scan: strongest-first devices, company/service facts and normalized Observations without active probes | S4 | ✅ complete |
| Three nRF24 receivers: RX-only spectrum, receiver-paced one-pixel waterfall and background-calibrated 2.4 GHz signal finder | S4 + S5.3 | 🔴 blocked |
| CC1101: RX-only Sub-GHz spectrum/activity, one-pixel waterfalls and frequency/RSSI finder for 315/433/868/915 MHz | S4 + S5.4 | 🔴 blocked |
| GPS adds fix, satellites, time and track to a Session only for an explicit compatible assembly | S4 + S5 | ⬜ later |
| Shared timeline exposes sources, duty cycle, temporary unavailability, degradation and dropped events | S4 + S6.6 | 🟡 in progress |
| Shared stable List/Detail/filter behavior for Wi-Fi, BLE and other radios with all useful facts | S3 + S4 | ✅ complete |
| Network/device Radar/localize: RSSI history, trend/range and honest proximity limits | S4 + S6 | 🟡 in progress |
| A Target preserves stable identities, Observation history and links to immutable source evidence | S6.1 + S6.4 | ✅ complete |
| Target name, tags, notes and favorite are bounded edits that survive cold reopen | S6.1 + S6.4 | ✅ complete |
| Explainable correlation shows features/confidence; review, accept/reject and merge/split are reversible | S6.2 + S6.4 | ✅ complete |
| Session baseline/diff shows new, disappeared and changed Targets | S6.3 + S6.4 | ✅ complete |
| Every compare/correlation conclusion opens its exact source evidence | S6.3 + S6.4 | ✅ complete |
| Immutable Capture preserves raw source, time, frequency/channel, RSSI, coordinates and receive settings | S3 + S4 | ✅ complete |
| Session/Capture commits are atomic and recover after reset and controlled power loss | S3 + S5 | 🔴 blocked |
| Library opens Sessions/Captures offline with list/detail/search/filter and visible integrity state | S3 + S6 | ✅ complete |
| Export provides JSON/CSV summaries, PCAP and portable radio formats with exact provenance | S3 + S5 | 🟡 in progress |
| SD, USB and local-companion import/export uses versioned schemas and a fail-closed parser | S5 + S6 | 🟡 in progress |
| SD/LittleFS exposes identity, capacity, recovery, integrity and degraded behavior | S3 + S5 | ✅ complete |
| IR receive/decode preserves original and derived data, cold-reopens in Library and exports CSV | S5.2 | ✅ complete |
| Sub-GHz RAW/OOK/FSK Capture preserves pulses, radio parameters and derived decodes | S5.4 | 🔴 blocked |
| PN532 reads tag/NDEF facts and a versioned dump only for an explicit non-conflicting assembly | S5 | 🔴 blocked |
| Separate Lab exposes authorized scope, source, frequency, power, duration and permanently visible TX state | S7 | ⬜ later |
| Back, timeout, panic, fault or loss of control/telemetry physically stops every TX path | S7 | ⬜ later |
| IR replay is available only from a selected immutable Capture after preview and explicit confirmation | S7 | ⬜ later |
| Sub-GHz replay/TX from an immutable Capture passes ResourceBroker, bounds, confirmation, countdown and stop result | S7 | ⬜ later |
| NFC write/restore of a supported owned tag exposes preview, verify and the original recovery dump | S7, conditional hardware | ⬜ later |
| Protocol Workbench compares pulses/waveforms, annotates fields and stores a derived decode without changing raw source | S7 | ⬜ later |
| Scoped local USB/Web companion browses, searches, compares and exports through shared Actions/schemas | S6.5 | 🟡 in progress |
| Permissioned app descriptor declares capabilities, resources, permissions, safety policy and UI strings before launch | S7 | ⬜ later |
| Versioned decoder/profile packages have a compatibility gate, integrity/signature and scoped storage | S7 + S8 | ⬜ later |
| SDK, sample extension and simulator trace kit cannot bypass ResourceBroker, permissions or Safety Supervisor | S7 | ⬜ later |
| Wi-Fi channel/packet monitor: current/mean load for 1–13, explainable free channel and bounded PCAP with drop counters | S4 | ✅ complete |
| User saves a real-TFT screenshot with build/state/time provenance and opens it in Library/export | S5 | ⬜ later |
| Offline OUI/BLE company/service/protocol profiles enrich facts with version/provenance without replacing raw evidence | S6 | ✅ complete |
| One feedback service owns antenna LEDs and buzzer: default 2/255, quiet mode, bounded tones and non-color-only cues | S5 + S6 | ✅ complete |
| Scoped Wi-Fi/USB setup isolates secrets, never exports them and never makes networking a Survey/Library prerequisite | S6 + S8 | 🟡 in progress |
| Versioned backup/restore and factory reset show scope/preview/checksum and never overwrite raw Capture without confirmation | S8 | ⬜ later |

### Roadmap

- ✅ **S0 — Governance and generation boundary** · complete
- ✅ **S1 — Evidence baseline: users, competitors, and hardware** · complete
- ✅ **S2 — Clean 1.x platform** · complete
- ✅ **S3 — First vertical slice: Survey Session** · complete
- ✅ **S4 — Cross-radio passive platform** · complete
- 🔴 **S5 — Complete ESP32-DIV hardware** · blocked
- 🟡 **S6 — Product differentiation: Targets, comparison, companion** · in progress
- ⬜ **S7 — Safe Lab and extensibility** · later
- ⬜ **S8 — Release hardening and 1.0.0** · later

[live status and next evidence gate](docs/v1/STATUS.md) · [stage outcomes and exit gates](docs/v1/DELIVERY_PLAN.md) · [complete functionality map](docs/v1/DELIVERY_PLAN.md#product-functionality-map)
<!-- LESHY-ROADMAP:END -->

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
