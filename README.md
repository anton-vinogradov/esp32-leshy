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

- **Current phase:** `S6.2 — explainable correlation and reversible identity decisions`.
- **Verified checkpoint:** host/build checkpoint `E-CORR-001` establishes the first S6.2 slice. A bounded proposal joins one unowned exact radio identity/evidence reference to one Target, exposes fixed per-feature contributions and explicit `Low`/`Medium`/`High`/`Stale` confidence, and never mutates on proposal. Both candidate and explanation evidence must open exact retained Observations. Versioned `correlation.accept` and `correlation.reject` Actions require an explicit decision, recheck evidence and optimistic Target revision, and write an immutable bounded decision record; no automatic merge path exists. Native, ASan/UBSan and production builds pass. The decision log is not persistent yet and merge/split, compare and UI remain explicitly unclaimed. Exact `0.145.0-interface-settings` remains the latest physically accepted board-01 product baseline; the deferred S5 RF-positive gate remains open.
- **Next gate:** persist correlation decisions atomically with the Target catalog, then implement reversible merge/split history and prove merge→split restores the exact prior identity/evidence graph without editing source Observations. The physical S5 gate is postponed, not waived: when the ordered replacement DIV arrives, its read-only profile must pass before the retained one-command IR→nRF24→OOK→FSK matrix can close S5.3/S5.4/S5.6.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S6.1 | Target foundation: stable Target IDs, exact radio identities, editable name/tags/notes/favorite and immutable source-evidence references, all bounded and host-verified | ✅ complete |
| S6.2 | Explainable correlation proposes links with features/confidence; accept/reject and reversible merge/split never destroy source evidence | 🟡 in progress |
| S6.3 | Baseline/diff compares two Sessions and classifies new, disappeared and changed Targets with every conclusion opening its evidence | ⬜ later |
| S6.4 | On-device Targets and Compare workflows expose the useful result first, stable navigation and full-area detail views | ⬜ later |
| S6.5 | Local USB/Web companion uses the same Actions and versioned schemas with scoped connectivity and secrets | ⬜ later |
| S6.6 | Integrated DEMO-S6: record and compare two surveys, inspect each conclusion on-device or locally, export offline, then return to and close the deferred S5 physical predecessor gate before S6 acceptance | ⬜ later |

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
