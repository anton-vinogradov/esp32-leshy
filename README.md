# ESP32-Leshy 1.x

Read this in: **English** · [Русский](README.ru.md)

ESP32-Leshy 1.x is a from-scratch redesign of the firmware for the
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV) wireless multitool.

<!-- LESHY-ROADMAP:START -->
## Development status and roadmap

> **Now: S6 — Product differentiation: Targets, comparison, companion**
>
> Stage gates complete: 5 of 9.
>
> User functionality: **24/62 done** · 17 active · 6 blocked · 15 planned.

This front-page snapshot is generated from the authoritative 1.x documentation; CI rejects it if it drifts. The checklist is complete for the currently frozen 62-capability 1.x baseline. The 1 September competitor re-audit and product decision are complete: every valuable accepted outcome is inside this denominator, while deferred integrations and the three hard product boundaries remain explicit in the [feature-level audit](docs/v1/COMPETITIVE_ANALYSIS.md#feature-level-parity-audit).

- **Current phase:** `S6.5 — functional-first user slices over shared Actions, safety and schemas`; `FF-5` bounded IR replay is active.
- **Delivery mode:** `functional-first`: user-visible vertical slices precede additional invisible infrastructure; affected delta HIL runs per slice and the broad matrix runs at block/stage, RC, cross-cutting or cadence boundaries.
- **Verified checkpoint:** `E-BUILD-246`/`E-AUTO-225`/`E-HIL-242`/`E-UX-093`/`RB-M259` accept exact physical `1.0.0-dev.377`: Home now names the domain **Wi-Fi** and explains **Networks · Devices · Channels**, so its one-action transition to the Wi-Fi task menu is visible. From that menu, one `OK` or one `Right` action enters Nearby Networks. A later long-idle physical-key observation recorded both intentional tree actions with zero input errors, ambiguity or queue drops; it did not reproduce a swallowed first press. Two passive lifecycles retain strongest-first identity focus, zero chrome repaint, zero storage errors and final Home/none/lease 0. The fresh precursor remains honestly rejected by the obsolete 2 KiB cold-Wi-Fi heap oracle; its measured 7,344 B one-time initialization is bounded by the shared 8 KiB policy and both post-warm endpoints are exactly 59,320 B.
- **Next gate:** progress remains **24/62**, while the fixed Wi-Fi track is **17/21 done, 4/21 remaining**. Wi-Fi work resumes from `WF-18`; the second-board `FF-5` IR replay gate remains deferred until the replacement DIV arrives. `WF-18…WF-21` stay behind explicit isolated-fixture/second-board admission; RF TX remains forbidden.

### Functional-first delivery queue

| Priority | User-visible slice | State |
|---|---|---|
| FF-0 | Physical review build: traverse every available passive top-level workflow, retain stable screens/navigation and record only user-visible findings | ✅ complete |
| FF-1 | Wi-Fi/BLE and Targets Radar plus the coherent cross-radio interaction review for `FUNC-17` | ✅ complete |
| FF-2 | Deliver `FUNC-43` on-device screenshot → Library → export with build/state/time provenance | ✅ complete |
| FF-3 | Complete `FUNC-37` Protocol Workbench over immutable Captures; waveform, task-first marking, comparison and truthful derived-decode screens are physically accepted; protected commit/cold reopen is deferred by owner decision until the second working DIV arrives | ⏸️ safely parked |
| FF-4 | Finish `FUNC-38` local USB/Web browse, search, compare and export without making network access a device dependency; dev.361 completes bilingual task-first host/build presentation and local preview, and tooling source `0ca7181` prepares a no-network-configuration external-client verifier plus exact USB parity binder; the dedicated-client physical run is deferred by owner decision until the second working DIV arrives | ⏸️ safely parked |
| FF-5 | Deliver `FUNC-34` IR replay from one selected immutable Capture with preview, confirmation and proven Stop/timeout; host/build foundation is accepted on dev.373 and exact two-board physical acceptance is deferred until the replacement DIV arrives | 🟡 active |
| FF-6 | Resume signed-package classification/execution for `FUNC-54`, then individually admitted Safe Lab actions; Automation/HID remains zero-output until this row becomes active | ⏸️ safely parked |

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S6.1 | Target foundation: stable Target IDs, exact radio identities, editable name/tags/notes/favorite and immutable source-evidence references, all bounded and host-verified | ✅ complete |
| S6.2 | Explainable correlation proposes links with features/confidence; accept/reject and reversible merge/split never destroy source evidence | ✅ complete |
| S6.3 | Baseline/diff compares two Sessions and classifies new, disappeared and changed Targets with every conclusion opening its evidence | ✅ complete |
| S6.4 | On-device Targets and Compare workflows expose the useful result first, stable navigation and full-area detail views | ✅ complete |
| S6.5 | Functional-first product train reviews and completes user-visible vertical slices while the local USB/Web companion continues over shared Actions and versioned schemas | 🟡 in progress |
| S6.6 | Integrated DEMO-S6 device/offline path is physically accepted; final phase completion waits for the deferred S5 physical predecessor gate before S6 acceptance | 🔴 blocked |

### Complete user functionality catalog

| Functionality | Delivery stage | Status |
|---|---|---|
| Boot probe identifies the board profile, main/RF assembly and every capability state with evidence | S2 + S5 | 🟡 in progress |
| Capability-driven Home exposes only available jobs and explains disabled/conflicted/fault before launch | S2 | ✅ complete |
| Device → Self-Test/Diagnostics safely checks applicable hardware without TX and exports a report | S2 + S5 | ✅ complete |
| TFT, five keys and touch share Actions, calibration, stable selection and an accessible Back path | S2 | ✅ complete |
| Persisted EN/RU, brightness/theme/sound, font scale/contrast/reduced motion/input repeat, favorite/hidden apps, shortcuts and startup app | S2 + S5 + S7 | 🟡 in progress |
| Explicit Start/Stop creates a bounded multi-radio Survey Session with configuration and provenance | S3 + S6.6 | ✅ complete |
| Passive Wi-Fi scan: networks, hidden-name enrichment, security/channel/vendor facts and normalized Observations | S3 + S4 | ✅ complete |
| Shared stable List/Detail/filter behavior for Wi-Fi, BLE and other radios with all useful facts | S3 + S4 | ✅ complete |
| Immutable Capture preserves raw source, time, frequency/channel, RSSI, coordinates and receive settings | S3 + S4 | ✅ complete |
| Session/Capture commits are atomic and recover after reset and controlled power loss | S3 + S5 | 🔴 blocked |
| Library opens Sessions/Captures offline with list/detail/search/filter, integrity state and recoverable Trash/Undo | S3 + S6 + S7 | 🟡 in progress |
| Export provides JSON/CSV summaries, PCAP and portable radio formats with exact provenance | S3 + S5 | 🟡 in progress |
| SD/LittleFS exposes identity, capacity, recovery, integrity and degraded behavior | S3 + S5 | ✅ complete |
| Passive BLE scan: strongest-first devices, company/service facts and normalized Observations without active probes | S4 | ✅ complete |
| Three nRF24 receivers: RX-only spectrum, receiver-paced one-pixel waterfall and background-calibrated 2.4 GHz signal finder | S4 + S5.3 | 🔴 blocked |
| CC1101: RX-only Sub-GHz spectrum/activity, one-pixel waterfalls and frequency/RSSI finder for 315/433/868/915 MHz | S4 + S5.4 | 🔴 blocked |
| GPS adds fix, satellites, time and track to a Session only for an explicit compatible assembly | S4 + S5 | ⬜ later |
| Shared timeline exposes sources, duty cycle, temporary unavailability, degradation and dropped events | S4 + S6.6 | ✅ complete |
| Network/device Radar/localize: RSSI history, trend/range and honest proximity limits | S4 + S6 | ✅ complete |
| Wi-Fi channel/packet monitor: current/mean load for 1–13, explainable free channel and bounded PCAP with drop counters | S4 | ✅ complete |
| Visible power/charge/reset reason, low-voltage safe write and verifiable sleep/resume | S5 | 🔴 blocked |
| SD, USB and local-companion import/export uses versioned schemas and a fail-closed parser | S5 + S6 | 🟡 in progress |
| IR receive/decode preserves original and derived data, cold-reopens in Library and exports CSV | S5.2 | ✅ complete |
| Sub-GHz RAW/OOK/FSK Capture preserves pulses/parameters/decodes and exports Flipper-compatible `.sub` from a declared decoder inventory | S5.4 + S7 | 🔴 blocked |
| PN532 reads tag/NDEF facts and a versioned dump only for an explicit non-conflicting assembly | S5 | 🔴 blocked |
| User saves a real-TFT screenshot with build/state/time provenance and opens it in Library/export | S5 | ✅ complete |
| One feedback service owns antenna LEDs and buzzer: default 2/255, quiet mode, bounded tones and non-color-only cues | S5 + S6 | ✅ complete |
| Local logs, crash journal and exportable diagnostic bundle without a cloud dependency | S6 + S8 | 🟡 in progress |
| A Target preserves stable identities, Observation history and links to immutable source evidence | S6.1 + S6.4 | ✅ complete |
| Target name, tags, notes and favorite are bounded edits that survive cold reopen | S6.1 + S6.4 | ✅ complete |
| Explainable correlation shows features/confidence; review, accept/reject and merge/split are reversible | S6.2 + S6.4 | ✅ complete |
| Session baseline/diff shows new, disappeared and changed Targets | S6.3 + S6.4 | ✅ complete |
| Every compare/correlation conclusion opens its exact source evidence | S6.3 + S6.4 | ✅ complete |
| Scoped local USB/Web companion browses, searches, compares and exports through shared Actions/schemas | S6.5 | 🟡 in progress |
| Offline OUI/BLE company/service/protocol profiles enrich facts with version/provenance without replacing raw evidence | S6 | ✅ complete |
| Scoped Wi-Fi/USB setup isolates secrets, never exports them and never makes networking a Survey/Library prerequisite | S6 + S8 | ✅ complete |
| Separate Lab exposes authorized scope, source, frequency, power, duration and permanently visible TX state | S7 | ⬜ later |
| Back, timeout, panic, fault or loss of control/telemetry physically stops every TX path | S7 | ⬜ later |
| IR replay uses selected immutable Capture or a ready signed multi-button/favorite remote/TV profile after preview and explicit confirmation | S7 | 🟡 in progress |
| Sub-GHz replay/TX from an immutable Capture passes ResourceBroker, bounds, confirmation, countdown and stop result | S7 | ⬜ later |
| NFC write/restore of a supported owned tag exposes preview, verify and the original recovery dump | S7, conditional hardware | ⬜ later |
| Protocol Workbench compares pulses/waveforms, annotates fields and stores a derived decode without changing raw source | S7 | 🟡 in progress |
| Permissioned app descriptor declares capabilities, resources, permissions, safety policy and UI strings before launch | S7 | ⬜ later |
| Versioned decoder/profile packages have a compatibility gate, integrity/signature and scoped storage | S7 + S8 | ⬜ later |
| SDK, sample extension and simulator trace kit cannot bypass ResourceBroker, permissions or Safety Supervisor | S7 | ⬜ later |
| Named Airspace Guard profiles/sensitivity explain Wi-Fi/BLE/nRF/Sub-GHz conditions, WPA3/PMF/SAE and jamming indicators with exact evidence/uncertainty | S7 | 🟡 in progress |
| Focused Wi-Fi authentication Capture reports EAPOL/PMKID and complete/incomplete handshakes, then exports PCAP and `hc22000` | S7 | ✅ complete |
| Offline Field Survey joins Wi-Fi AP/station and BLE with optional GPS track/satellite diagnostics/POI/notes, revisit comparison and WiGLE export | S7 | 🟡 in progress |
| BLE Inspector preserves raw compatible packets and enters connected GATT only after explicit target/permission/lease confirmation | S7 | ✅ complete |
| Device Lock protects secrets/evidence with PIN/recovery and can continue an admitted Capture beneath a private lock overlay without blocking Stop | S7 | 🟡 in progress |
| Device → Serial Console provides a bounded UART bridge and shared Actions CLI under explicit target/configuration/lease | S7 | 🟡 in progress |
| Permissioned signed Automation/HID has preview, ceilings, finite runtime, scoped target and passive-by-default BadUSB inspection | S7 | 🟡 in progress |
| Owned Lab ships named Wi-Fi/BLE/nRF/IR recipes for targeted handshake assist, identity/iBeacon, MouseJack, robustness and IR-camera fixtures with containment and Stop | S7 | ⬜ later |
| nRF24 ESB Workbench captures/decodes compatible packets and passively detects MouseJack; injection is a separate owned-fixture recipe | S7 | ⬜ later |
| Read-only Live Companion streams compatible Wi-Fi/BLE evidence to USB Wireshark/extcap and mirrors TFT without changing the host network | S7 | 🟡 in progress |
| Conditional Advanced NFC/EMV provides NDEF/ISO14443-4 emulation, erase, owned-tag recovery and redacted protocol diagnostics | S7, conditional PN532 | ⬜ later |
| Privacy Identity randomizes Leshy STA/AP and offers ephemeral provenance-labeled synthetic lab identities from owned Captures | S7 | 🟡 in progress |
| Conditional USB Host Inspector enumerates device/class interfaces and bounded signed keyboard/HID behavior after VBUS/OTG qualification | S7, conditional hardware | ⬜ later |
| Owned Evidence Verification checks owned Wi-Fi/NFC/Sub-GHz/fixed-code Captures with budget, pause/stop/checkpoint and provenance | S7 | 🟡 in progress |
| Owned Network Lab gives read-only LAN inventory and bounded captive-portal/ARP/DHCP/MITM robustness tests on an isolated selected fixture | S7 | ⬜ later |
| Browser/SD install and Device → Update: signed stable/beta OTA/SD package, rollback and recovery image | S8 | ⬜ later |
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
| **Passive audit** | **BadUSB inspection (CF-008):** parses a signed Automation/HID script and previews its target, permissions, actions, and bounds without executing it | 🟡 exact physical dev.303 accepts malformed/unsigned packages and dev.308 accepts real public-only enrollment/cold restore/revocation with zero output and complete cleanup; trusted/unknown/invalid signed-package classification remains next, execution disconnected |
| **Safe Lab** | **Named wireless fixtures (CF-009):** individually accepted Wi-Fi/BLE/nRF recipes for an owned test fixture with selected source/target, channel, power/rate, duration, lease, and a verifiable Stop | ⬜ planned, S7; every recipe has its own safety acceptance |
| **Safe Lab** | **Owned signals and tags:** IR replay only from an immutable Capture; NFC write/restore with preview, verification, and a recovery dump; Sub-GHz replay only after a physical Stop has been proven | ⬜ planned; NFC requires PN532, and CC1101 TX is currently blocked |
| **Active-confirmed** | **BLE Inspector, GATT path (CF-004):** connects only to an explicitly selected device and enumerates services/characteristics under separate permission and lease | ✅ exact `1.0.0-dev.276`: explicit permission and second confirmation, live bounded enumeration, wrong-peer/timeout/resource/disconnect-failure cleanup and positive recovery are physically accepted with zero pair/read/write/subscribe operations |
| **Active-confirmed** | **Device Lock (CF-006):** local PIN, bounded retry/recovery, optional non-destructive PIN disable, and protection for secrets/evidence without blocking Stop, panic, or recovery | ✅ exact dev.331 physically accepts separately confirmed PIN disable and exact-CID protected cold reopen without data loss, on top of dev.283 encrypted storage and dev.281 recovery/admission; CAP-052 is complete, S7 |
| **Active-confirmed** | **Serial Console (CF-007):** bounded UART monitor/bridge for a selected external device and the shared Actions CLI without bypassing policy/leases | 🟡 exact dev.285 accepts the product UI/CLI and stock RF-shield fail-closed path; positive UART traffic still requires a reviewed no-RF fixture; arbitrary raw GPIO control is outside the product |
| **Active-confirmed** | **Automation/HID execution (CF-008):** runs only a signed, permissioned script after previewing the target, actions, ceilings, and finite duration | ⬜ planned, S7; accepted passive dev.308 deliberately still provides no HID/Action output path |

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
