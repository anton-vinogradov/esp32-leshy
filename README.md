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

- **Current phase:** `S5.3 — controlled nRF24 positive-signal gate (hardware-blocked)`.
- **Verified checkpoint:** exact `0.139.0-s5-runtime-complete` closes the executable S5.5 runtime slice on no-PSRAM board-01. The stock assembly is identified truthfully as `stock-rf-no-gps-no-pn532`: I²C `0x75` ACKs but its type/voltage are not guessed, voltage remains unavailable because GPIO2 belongs to the buzzer, and GPS/PN532 are explicitly not applicable. Three injected low-voltage samples prohibit Store before filesystem open with zero writes and unchanged generation 109. Real 300 ms ESP32 light sleep wakes by timer with heap/generation invariant; the public Power action sleeps for 1 s and restores UI/input. An RX-only Sub-GHz software fixture then follows the public Capture Store path at 433.920 MHz, saves three pulses atomically, advances exact-CID generation 109→110, issues zero TX/PATABLE/FIFO commands and returns Home/none/lease 0. The HIL session is explicitly ended and three TFT frames are retained. This checkpoint does not claim a physical Sub-GHz signal or close S5.
- **Next gate:** use a qualified second RF carrier/source to close the physical S5.3 nRF24 positive result, then S5.4 physical Sub-GHz frequency→OOK capture→save→cold export and declared FSK/GDO0 path. The faulty clone is restored to stock for return and is not an authorized transmitter; without a replacement source those physical/two-board gates remain fail-closed.

### Current stage phases

| Phase | Outcome / exit gate | Status |
|---|---|---|
| S5.1 | Stock-radio passive product slices: all-antenna nRF24 overview/finder, robust CC1101 finder, bounded RAW/IR capture foundations | ✅ complete |
| S5.2 | First physical two-board loop: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ complete |
| S5.3 | Known nRF24 signal: source-bound 2,442 MHz minimum-power fixture → three-receiver finder result → safe cleanup; blocked until a repaired/replacement RF carrier is available | 🟡 in progress |
| S5.4 | Known Sub-GHz signal: frequency find plus OOK capture/save/cold export; declare and verify the FSK/GDO0 path | ⬜ later |
| S5.5 | Runtime completeness: exact 0.139 accepts Product Survey/worker safety inherited from 0.138 plus truthful stock assembly applicability, debounced low-voltage Store refusal, real light-sleep/resume and a public RX-only Sub-GHz software-fixture Store path; physical positive RF remains owned by S5.3/S5.4 | ✅ complete |
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
