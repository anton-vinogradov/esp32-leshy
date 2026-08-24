# ESP32-Leshy 1.x

Read this in: **English** · [Русский](README.ru.md)

ESP32-Leshy 1.x is a from-scratch redesign of the firmware for the
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV) wireless multitool.

<!-- LESHY-ROADMAP:START -->
## Development status and roadmap

> **Now: S5 — Complete ESP32-DIV hardware**
>
> Stage gates complete: 5 of 9.

This front-page snapshot is generated from the authoritative 1.x documentation; CI rejects it if it drifts.

- **Current phase:** `S5.5 — IR/Sub-GHz Capture Store deadline completion`.
- **Verified checkpoint:** exact `0.138.0-safety-restart-noos` closes the physical IR Capture Store deadline gate on no-PSRAM board-01 with fixture `0.2.5-shared-pin-safe`. One fixed NEC `0x10/0x34` emission is decoded and saved, advancing exact-CID catalog generation 106→107 with 94,136 B free heap, a 51,188 B largest block and mount error zero. A second bounded emission enters the same public Save path, stalls 10 s before storage hardware and trips the 8,000 ms deadline at 8,001 ms with zero physical writes. Outputs quiesce, lease reaches zero, Safe Mode survives a no-OS software restart, recovery stays read-only, two public Actions clear the latch and final state is Home with exact CID, catalog 107/0 and lease 0. Both fixture emissions are below 100 ms and finish inactive. The fresh exact two-board flash and all 26 product actions are retained as machine-checked evidence.
- **Next gate:** apply the accepted shared 8 s Store boundary to a positive physical Sub-GHz capture/save path when a receiver carrier with plausible read-only identities is available; in parallel, add low-voltage safe-write and sleep/resume coverage on board-01. The paused S5.3 nRF gate and S5.4 Sub-GHz gate must not use or transmit from the unqualified clone RF carrier.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S5.1 | Stock-radio passive product slices: all-antenna nRF24 overview/finder, robust CC1101 finder, bounded RAW/IR capture foundations | ✅ complete |
| S5.2 | First physical two-board loop: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ complete |
| S5.3 | Known nRF24 signal: source-bound 2,442 MHz minimum-power fixture → three-receiver finder result → safe cleanup; waiting for repaired/replacement board-02 RF carrier | ⬜ later |
| S5.4 | Known Sub-GHz signal: frequency find plus OOK capture/save/cold export; declare and verify the FSK/GDO0 path | ⬜ later |
| S5.5 | Runtime completeness: exact 0.138 accepts Product Survey preparation/admission, calibrated Wi-Fi+BLE workers and both Wi-Fi/IR Capture Store deadline/restart/clear paths; Sub-GHz positive Store, low-voltage safe-write, sleep/resume and applicable explicit GPS/PN532 assembly profiles remain | 🟡 in progress |
| S5.6 | Integrated S5 hardware gate: on-device Full check plus automated two-board regression with zero leaked leases/outputs | ⬜ later |

### Roadmap

- ✅ **S0 — Governance and generation boundary** · complete
- ✅ **S1 — Evidence baseline: users, competitors, and hardware** · complete
- ✅ **S2 — Clean 1.x platform** · complete
- ✅ **S3 — First vertical slice: Survey Session** · complete
- ✅ **S4 — Cross-radio passive platform** · complete
- 🟡 **S5 — Complete ESP32-DIV hardware** · in progress
- ⬜ **S6 — Product differentiation: Targets, comparison, companion** · later
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
