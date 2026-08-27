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
- **Verified checkpoint:** exact `0.196.2-companion-post-web-shared-scratch` at firmware source `7272d237ebb65e4b700ad8c64a32b48fc779ad75` is physically accepted for the **device-only Local Web → Targets → offline USB** continuity boundary in `E-BUILD-153`/`E-AUTO-125`/`E-HIL-183`/`E-COMPANION-007`. One exact application flash starts and stops the DIV SoftAP with zero associated stations, leaves the ESP-IDF network core explicitly process-lifetime, reopens 16 read-only Targets with 7 comparison items, reproduces the accepted 11,521-byte offline snapshot byte-for-byte and restores the Survey worker at Home/none/lease 0. The 24,808-byte state codec and 11,272-byte admission scratch reuse one existing static union, adding zero static RAM. No host network tool runs and active Mac Wi-Fi is untouched.
- **Next gate:** flash exact `1.0.0-dev.208` once on original board-01, then require successful exact-CID boot catalog admission, one contiguous real Wi-Fi+BLE Survey cycle, save after bounded NimBLE teardown, reboot, reopen the result and finish at Home/none/lease 0. The active laptop Wi-Fi and Cardputer remain prohibited. Physical HTTP parity remains deferred to a dedicated idle adapter or external client, and the physical S5 gate remains postponed, not waived, until the replacement DIV arrives and passes its read-only profile.

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
| Home with firmware identity, task-first final menu and full-area pages | S2 | ✅ complete |
| Five-key and touch navigation, stable selection, EN/RU UI and accessible common components | S2 | ✅ complete |
| Device settings: language, brightness, theme, power/sleep and per-antenna status LEDs | S2 + S5.5 | ✅ complete |
| Device service hub: Quick/Full Self-Test, Diagnostics, recovery state and About | S2 + S5.6 | ✅ complete |
| Selectable passive multi-radio Survey, durable timeline and reusable Sessions | S3 + S6.6 | 🟡 in progress |
| Wi-Fi nearby networks: stable list, SSID/security/channel/vendor facts, hidden-name enrichment and live radar | S4 | ✅ complete |
| Wi-Fi devices: passive client discovery, vendor/type/model/generation facts, directed SSID and live radar | S4 | ✅ complete |
| Wi-Fi channels 1–13: current and mean load, channel boundaries and explainable free-channel recommendation | S4 | ✅ complete |
| Bounded Wi-Fi packet recording, privacy confirmation, PCAP save, cold reopen and export | S4 | ✅ complete |
| Bluetooth nearby devices: strongest-first list, company/service identity details and live radar | S4 | ✅ complete |
| 2.4 GHz nRF24 all-receiver spectrum and receiver-paced one-pixel waterfall | S5.3 | 🔴 blocked |
| 2.4 GHz nRF24 signal finder with background calibration, exact frequency and nearest Wi-Fi channel | S5.3 | 🔴 blocked |
| Sub-GHz spectrum and receiver-paced one-pixel waterfalls for 315/433/868/915 MHz | S5.4 | 🔴 blocked |
| Sub-GHz calibrated frequency finder plus bounded OOK/FSK receive, save, cold reopen and export | S5.4 | 🔴 blocked |
| Infrared receive, NEC decode, save, cold Library reopen and CSV export | S5.2 | ✅ complete |
| Library browsing for Sessions and Captures with offline reopen and integrity status | S4 + S5 | ✅ complete |
| CSV/PCAP/offline snapshot export with exact source-evidence provenance | S4–S6.5 | ✅ complete |
| Targets: stable identity, favorite/name/tags/notes and drill-down to immutable evidence | S6.1 + S6.4 | ✅ complete |
| Explainable cross-radio correlation with review, accept/reject and reversible merge/split | S6.2 + S6.4 | ✅ complete |
| Baseline comparison: new, disappeared and changed Targets with evidence for every conclusion | S6.3 + S6.4 | ✅ complete |
| Scoped local USB companion: browse/search Sessions, Targets and comparisons and export offline | S6.5 | 🟡 in progress |
| Scoped device-hosted Web companion over the same read-only schemas and Actions | S6.5 | 🟡 in progress |
| Authorized Lab: bounded transmit/replay, visible TX state, immutable source capture and panic stop | S7 | ⬜ later |
| Permissioned extensions and optional GPS/NFC hardware profiles | S7 | ⬜ later |
| Device → Update: signed stable/beta OTA, rollback and recovery | S8 | ⬜ later |
| Browser install plus encrypted backup/restore of settings and user data | S8 | ⬜ later |
| Automated real-device screenshots, delta/full HIL and one-hour release qualification | S8 | ⬜ later |

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
