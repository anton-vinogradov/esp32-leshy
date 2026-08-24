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

- **Current phase:** `S5.3 — controlled nRF24 known-signal proof`.
- **Verified checkpoint:** exact `0.129.0-pre-app-watchdog` completes the physical two-board NEC receive → save → cold Library CSV path in 33/33 steps. Exact `0.130.0`/`0.131.0` changes board-02 shared MISO/GPIO13 from LOW with its RF carrier attached to HIGH with the carrier absent. Exact `0.132.0-carrier-csn-characterization` then reattaches the carrier and observes all four receiver selects HIGH for 32/32 samples (nRF GPIO4/48/21 and CC1101 GPIO5) while MISO returns LOW for 0/32 HIGH samples under both pulls. It performs zero SPI bytes, receiver reads, CE-high events, strobes or TX commands and returns Home/none/lease 0. This rejects an accidentally selected receiver and localizes the fault to a carrier module or the carrier's shared-MISO net; it does not identify one module or prove an antenna/U.FL fault.
- **Next gate:** repair, return or replace the board-02 RF carrier/device, then require plausible nRF and CC1101 identities from the same exact read-only probe before any bounded known-signal emission. Per-module isolation now requires physical separation of MISO or power because the carrier has no software-controlled module power. Cross-swap and RF emission remain closed.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S5.1 | Stock-radio passive product slices: all-antenna nRF24 overview/finder, robust CC1101 finder, bounded RAW/IR capture foundations | ✅ complete |
| S5.2 | First physical two-board loop: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ complete |
| S5.3 | Known nRF24 signal: source-bound 2,442 MHz minimum-power fixture → three-receiver finder result → safe cleanup | 🟡 in progress |
| S5.4 | Known Sub-GHz signal: frequency find plus OOK capture/save/cold export; declare and verify the FSK/GDO0 path | ⬜ later |
| S5.5 | Runtime completeness: worker supervision, low-voltage safe-write, sleep/resume and applicable explicit GPS/PN532 assembly profiles | ⬜ later |
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
