# ESP32-Leshy 1.x — 1.0 capability catalog

*Read in: **English** · [Русский](CAPABILITY_CATALOG.ru.md)*

Document status: **product-reviewed 1.0 scope baseline**, expanded 27 August 2026.

This catalog is the user-facing view of the 1.0 boundary. Normative acceptance
criteria remain in [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md), while current
implementation state lives only in [STATUS.md](STATUS.md). A row is not done merely
because it exists: it becomes `verified` only through linked evidence.

## How to read the catalog

- **P0** — 1.0.0 cannot ship without it;
- **P1** — part of agreed 1.0 completeness and frozen no later than S7;
- **conditional** — required for 1.0 when the corresponding stock or explicitly
  selected optional assembly is declared and detected;
- **S2…S7** — the stage that delivers the complete user path;
- **S8** verifies the release and does not add major capabilities.

Wording and priority can be refined until S1 is accepted. A new row after S1 needs a
`J-*`, `PR/NFR-*`, stage, and test link; after the S7 feature freeze it requires an
explicit release-boundary change.

## Platform and device

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-001 | Boot probe identifies board, main/RF assembly, and capability states with evidence | P0 | PR-001, PR-014 | S2/S5 |
| CAP-002 | Home is projected from available capabilities and explains disabled/conflicted/fault before launch | P0 | PR-002 | S2 |
| CAP-003 | Diagnostics performs a safe no-TX self-test and exports a report | P0 | PR-009 | S2/S5 |
| CAP-004 | TFT, buttons, and touch use common Actions, calibration, and an accessible Back path | P0 | PR-002, NFR-002, NFR-010 | S2 |
| CAP-005 | EN/RU language, brightness, theme, sound, and screen behavior settings persist locally | P1 | PR-011, NFR-010 | S2/S5 |
| CAP-006 | Power, charging, low-voltage safe writes, sleep/resume, and reset reasons are visible and testable | P0 | PR-009, NFR-004 | S5 |
| CAP-007 | Browser install, stable/beta update, signatures, rollback, and recovery image | P0 | PR-010 | S8 |
| CAP-008 | Local logs, crash journal, and diagnostic bundle work without cloud services | P1 | PR-009, PR-012 | S6/S8 |

## Survey and observations

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-009 | Start/Stop creates a bounded Survey Session with explicit configuration and provenance | P0 | PR-003 | S3 |
| CAP-010 | Passive Wi-Fi scan publishes normalized Observations | P0 | PR-003 | S3 |
| CAP-011 | Passive BLE scan/sniff publishes normalized Observations | P0 | PR-003 | S4 |
| CAP-012 | Three nRF24 receivers provide passive 2.4 GHz activity without hidden TX | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-013 | CC1101 provides passive Sub-GHz spectrum/activity and RSSI/frequency evidence | P0, conditional RF shield | PR-003, PR-014 | S4/S5 |
| CAP-014 | GPS adds fix, satellites, time, and track to a Session when an explicit assembly is selected | conditional | PR-003, PR-014 | S4/S5 |
| CAP-015 | A common timeline shows sources, duty cycle, temporary unavailability, and dropped events | P0 | PR-003, NFR-004, NFR-005 | S4 |
| CAP-016 | Common List/Detail/filter behavior is consistent across supported radios | P0 | PR-004 | S3/S4 |
| CAP-017 | Radar/localize shows RSSI history and honest proximity limits | P1 | PR-004 | S4/S6 |
| CAP-042 | Passive Wi-Fi channel/packet monitor creates a bounded Capture and compatible PCAP with drop counters and no hidden TX | P0 | PR-003, PR-007, PR-015 | S4 |

Implementation checkpoint: exact `0.115.0-wifi-device-intelligence` deepens the
current CAP-016 Wi-Fi Devices detail with passive management/data-frame facts, a
pinned 39,984-entry IEEE MA-L lookup, explicit private-MAC handling and a
selected-channel current-signal radar. This is the first useful slice of CAP-017 and
CAP-044, but it does not close either: retained RSSI history, localization semantics,
BLE/services/protocol profiles, Target correlation and persistent identity history
remain owned by S6.

Exact `0.116.0-wifi-channel-average` refines the CAP-042 Channels presentation and
decision rule. It keeps the latest passive airtime dwell visible as a narrow colored
bar, adds a wide gray arithmetic mean since task entry for every channel 1…13, and
chooses the least-busy primary among 1/6/11 from those means. The mean is bounded,
allocation-free and volatile; it is neither calibrated CCA utilization nor a
persistent site survey.

Later exact `0.120.0-wifi-channel-choice` corrects the hidden 1/6/11 restriction.
Every measured channel 1…13 is now eligible, and the same gray session mean visible
on the graph is the primary comparison value. Equal means are resolved by a bounded
3/2/1 adjacent-channel overlap-pressure estimate; this cannot overrule a lower
visible mean. The recommended channel alone is highlighted on the axis. This remains
a received-frame airtime estimate, not calibrated RF energy/CCA or a regulatory
router-configuration oracle.

Exact `0.121.0-wifi-channel-neutral-bars` removes the last visual remnant of that
obsolete restriction. Current-load bar tone is a function of measured load only;
channels 1/6/11 no longer receive a preferred low-load color. The one cyan axis
label remains the recommendation. No measurement or ranking semantics change.

Exact `0.122.2-ble-device-intelligence` deepens CAP-011/016/017 for Bluetooth
Nearby Devices. The fixed catalog now monotonically combines passive advertisement
facts, a pinned 4,012-record Bluetooth SIG assigned-company lookup, available
device/subtype/tracker/service classifications and volatile signal statistics.
Strongest-first rows remain identity-stable after interaction, while detail presents
vendor, address/type, connectable/scannable state, TX power/appearance/service when
present and an integrated current/range/trend radar. It sends no scan request,
pairing or active probe and persists no enriched device passport. One bounded retry
is permitted only for a transient scan-start/completion failure; the accepted
physical run needed none, so recovery of that branch remains source-contract rather
than injected HIL evidence.

Exact `0.123.0-nrf24-signal-finder` deepens CAP-012 with a second user job beside
the accepted Spectrum/Waterfall: Find a signal from a remote, tag or sensor. It
uses every detected nRF24 receiver, learns two short ambient windows and reports
only a local response above that floor, with exact frequency and nearest Wi-Fi
channel where meaningful. It is allocation-free, volatile and RX-only. The physical
ambient/waiting path and non-flickering graph pass; deterministic host injection
proves the found mapping. A controlled board-02 source is still required before a
physical found result or calibrated power/distance claim can be accepted.

Exact `0.124.1-cc1101-frequency-finder` deepens CAP-013 with the corresponding
Sub-GHz job beside Air overview and RAW Capture. It passively covers 275…950 MHz
in 1,099 receiver bins at 250 kHz spacing, builds a median-of-three ambient floor,
rejects common drift and board-clock harmonic neighborhoods, and reports exact kHz
plus the nearest 315/433/868/915 MHz band hint. Two independent ambient runs reject
the non-repeatable peaks falsely accepted by 0.124.0; that failed predecessor is
retained with the corrected evidence. Deterministic host injection proves a real
local response at 433,250 kHz. Physical positive detection and calibrated frequency,
power or distance remain open for a controlled board-02 source.

Exact `0.117.0-wifi-device-live-detail` refines the CAP-016/017 presentation:
opening a Wi-Fi client now locks its observed channel and presents identity facts
plus the live RSSI meter/range/trend on one screen. Left unlocks the channel and
returns directly to the stable list. This removes a navigation-only intermediate
state; it does not add active probing, calibrated distance or retained history.

Exact `0.118.0-wifi-network-intelligence` deepens CAP-010/016 for Nearby Networks.
Each BSSID may expose its IEEE MA-L vendor and every normalized fact available from
the passive ESP-IDF scan record: auth/ciphers, channel/frequency/width, PHY,
WPS/FTM/RX antenna and country/channel constraints. Empty SSIDs stay visibly hidden
until a later passively received beacon or probe response for that BSSID supplies a
name; enrichment is monotonic and keeps navigation identity fixed. This is passive
discovery only, not directed probing, association, decryption, device-type certainty
or persistent network tracking.

Exact `0.119.0-wifi-network-live-radar` completes the baseline CAP-010/016 network
detail presentation with current RSSI, qualitative strength, a meter, volatile
minimum/maximum and latest trend for the selected fixed BSSID on the same screen.
The samples come from continued all-channel passive discovery and reset on task
entry. This is useful relative proximity feedback, not a selected-channel direct
receiver, calibrated range, historical Target tracking or proof of packet traffic.

## Targets and comparison

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-018 | Target retains identities and source Observation history | P1 | PR-008 | S6 |
| CAP-019 | Users add Target tags, notes, name, and favorite state | P1 | PR-008 | S6 |
| CAP-020 | Correlation explains signals/confidence; merge/split are reversible | P1 | PR-008 | S6 |
| CAP-021 | Baseline/diff compares visits and shows new, missing, and changed targets | P1 | J-04, PR-008 | S6 |
| CAP-022 | Every compare/correlation conclusion opens its source evidence | P1 | PR-008, NFR-008 | S6 |

## Capture, library, and data portability

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-023 | Capture is immutable and stores time, source, frequency/channel, RSSI, coordinates, and receive settings | P0 | PR-005, NFR-008 | S3/S4 |
| CAP-024 | Session/Capture writes are atomic and recover after reset or power loss | P0 | PR-005, NFR-009 | S3/S5 |
| CAP-025 | Library opens saved Session/Capture data offline with list/detail/search/filter | P0 | PR-006 | S3/S6 |
| CAP-026 | Export provides JSON/CSV summary, PCAP for compatible frames, and portable radio formats | P0/P1 | PR-007 | S3/S5 |
| CAP-027 | SD, USB, and local companion import/export use versioned schemas and fail-closed parsers | P0 | PR-007, NFR-007, NFR-009 | S5/S6 |
| CAP-028 | SD and LittleFS expose identity, capacity, recovery, integrity, and degraded behavior | P0 | PR-005, PR-006, PR-009 | S3/S5 |
| CAP-029 | IR capture/decode/library preserves the original and derived results | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-030 | Sub-GHz RAW/decode/library preserves pulses, radio parameters, and derived results | P0, conditional RF shield | PR-007, PR-014 | S5 |
| CAP-031 | PN532 reads tag/NDEF info and versioned dumps under an explicit non-conflicting assembly | conditional | PR-007, PR-014 | S5 |
| CAP-043 | A user saves a real-TFT screenshot with build/state/time provenance and opens it in Library/export | P1 | J-03, PR-015 | S2/S5 |

## Authorized Lab

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-032 | Lab context is separate from passive work and shows scope, frequency, power, time, and TX state | P0 for any TX | PR-013 | S7 |
| CAP-033 | Back, timeout, panic, and fault physically stop every enabled TX path | P0 for any TX | PR-013, NFR-002, NFR-006 | S7 |
| CAP-034 | IR replay is available only for a selected saved Capture in an authorized context | conditional | PR-013, PR-014 | S5/S7 |
| CAP-035 | Sub-GHz replay/TX uses ResourceBroker, bounds, explicit confirmation, and an immutable source Capture | conditional | PR-013, PR-014 | S5/S7 |
| CAP-036 | NFC write/restore runs only for a supported owned tag with preview and verify | conditional | PR-013, PR-014 | S5/S7 |
| CAP-037 | Protocol workbench compares pulses/waveforms, annotates fields, and creates derived decodes | P1 | J-06, NFR-008 | S7 |

## Companion and extensibility

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-038 | Local Web/USB companion views, searches, compares, and exports through the same Actions/schema | P1 | PR-012 | S6 |
| CAP-039 | App descriptor declares capabilities, resources, permissions, safety, and strings before launch | P1 | PR-002, PR-013 | S7 |
| CAP-040 | Decoder/profile packages have version compatibility, integrity/signature, and scoped storage | P1 | PR-010, PR-012 | S7/S8 |
| CAP-041 | SDK includes a sample extension, simulator trace kit, and checks that cannot bypass leases/policy | P1 | PR-012, PR-013, NFR-006 | S7 |

## Identification and device maintenance

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-044 | Offline OUI/BLE company/services/protocol profiles enrich facts with version and provenance without replacing source evidence | P1 | PR-008, PR-019 | S6 |
| CAP-045 | One feedback service owns WS2812 and buzzer: quiet mode, idle GPIO2 LOW, bounded tones, and non-color-only capture/proximity/fault cues | P1, conditional HW-T09 for sound | PR-009, PR-011, PR-016, NFR-010 | S5/S6 |
| CAP-046 | Local Wi-Fi/USB connectivity setup keeps secrets separate, never exports them, and never makes networking a Survey/Library prerequisite | P0 for PR-010/012 | PR-010, PR-012, PR-017 | S2/S6/S8 |
| CAP-047 | Versioned backup/restore and factory reset show scope/preview/checksum and never overwrite raw Capture without explicit confirmation | P1 | PR-005, PR-010, PR-018, NFR-008/009 | S5/S8 |

## Competitive completeness, device security, and automation

| ID | 1.0 capability | Commitment | Requirements | Ready stage |
|---|---|---|---|---|
| CAP-048 | Airspace Guard passively detects and explains suspicious Wi-Fi/BLE conditions: disconnect bursts, identity conflicts/churn, sustained elevated Wi-Fi noise and tracker-compatible BLE presence; every conclusion opens its source evidence and uncertainty | P1 | J-07, PR-020 | S7 |
| CAP-049 | Focused Wi-Fi authentication Capture identifies EAPOL/PMKID and complete/incomplete handshakes, then exports immutable PCAP and `hc22000` evidence | P1 | J-03, J-07, PR-015, PR-021 | S7 |
| CAP-050 | Offline Field Survey joins Wi-Fi AP/station and BLE observations with optional GPS track, deduplication, revisit comparison, and WiGLE-compatible local export | P1, GPS conditional | J-01, J-07, PR-022 | S7 |
| CAP-051 | BLE Inspector preserves compatible raw packets and offers an explicit permissioned connected-GATT mode with deterministic disconnect and provenance | P1 | J-02, J-07, PR-023 | S7 |
| CAP-052 | [Device Lock](DEVICE_LOCK.md) provides local PIN setup, bounded retry/recovery, and protects secrets/evidence without blocking safe cleanup or recovery | P0 before sensitive data ships | J-05, J-08, PR-017, PR-024 | S7 |
| CAP-053 | Device → Serial Console provides a bounded UART bridge and shared Actions CLI under explicit configuration, permissions, leases, and cleanup | P1 | J-05, J-08, PR-012, PR-025 | S7 |
| CAP-054 | Automation/HID runs signed permissioned scripts with preview, ceilings, finite runtime and scoped USB/BLE HID; defensive BadUSB inspection is passive by default | P1 | J-08, PR-013, PR-026 | S7 |
| CAP-055 | Authorized wireless Lab contains only named, individually accepted Wi-Fi/BLE/nRF fixture recipes with bounded region/power/channel/time and physical stop | P0 for any shipped wireless TX | J-06, J-08, PR-013, PR-027 | S7 |

## Explicitly after 1.0

Authenticated DIV-to-DIV Peer Link, cloud accounts and default telemetry, a public
executable-app marketplace, broad support for unrelated ESP32 boards,
hidden/disruptive actions, and attack count as a parity metric are not 1.0
commitments. A post-1.0 candidate gets its own user job, risk review, and stage
proposal; it is not inserted retroactively.

## Completeness gates

- **S1 scope gate:** every `CAP-*` has a requirement, priority, and stage; the
  catalog and explicit exclusions pass product review.
- **S2 UX gate:** every section has a navigation/state baseline on the real TFT,
  including disabled/error/empty/running/confirm states.
- **S7 feature-complete gate:** every P0/P1 and applicable conditional capability
  has a complete path or an explicitly accepted `deferred/rejected` requirement.
- **S8 release-complete gate:** every P0 is verified, no P0/P1 defects remain open,
  and applicable P1 capabilities pass the release matrix.
