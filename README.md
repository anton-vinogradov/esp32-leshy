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
- **Next gate:** recover board-01 from the rejected 0.204 boot loop into the ROM loader, flash host/build-verified `0.206.0-minimal-nimble-observer`, and run one exact delta HIL in which the real product Survey completes contiguous Wi-Fi+BLE cycles, saves, reboots, reopens the result and ends at Home/none/lease 0. The test remains USB-only: the active laptop Wi-Fi and Cardputer are prohibited. Physical HTTP parity remains deferred to a dedicated idle adapter or external client, and the physical S5 gate remains postponed, not waived, until the replacement DIV arrives and passes its read-only profile.

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
| Home, five keys, touch, EN/RU UI and accessible common components | S2 | ✅ complete |
| Device hub: Power, Settings, Self-Test, Diagnostics and About | S2 | ✅ complete |
| Persistent passive Survey and reusable Sessions | S3 + S6.6 | 🟡 in progress |
| Wi-Fi networks, devices, channels, details, radar and packet capture | S4 | ✅ complete |
| Bluetooth devices, identity/vendor details and radar | S4 | ✅ complete |
| 2.4 GHz nRF24 spectrum, one-pixel waterfall and signal finder | S5 | 🔴 blocked |
| Sub-GHz spectrum, one-pixel waterfall, finder and OOK/FSK capture | S5 | 🔴 blocked |
| Infrared receive, decode, save and Library export | S5 | ✅ complete |
| Library, offline reopen, CSV/PCAP export and evidence provenance | S4 + S5 | ✅ complete |
| Targets, comparison, evidence, metadata and reversible correlation | S6.1–S6.4 | ✅ complete |
| Scoped local USB/Web companion and offline search/export | S6.5 | 🟡 in progress |
| Authorized Lab: bounded transmit/replay with panic stop | S7 | ⬜ later |
| Permissioned extensions and optional GPS/NFC hardware profiles | S7 | ⬜ later |
| Device → Update: signed stable/beta OTA, rollback and recovery | S8 | ⬜ later |
| Browser install, backup/restore and automated one-hour release qualification | S8 | ⬜ later |

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
