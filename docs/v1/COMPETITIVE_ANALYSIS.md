# ESP32-Leshy 1.x competitive analysis

Market snapshot: **15 August 2026**.

This is a product-direction document, not a firmware leaderboard. Projects are
compared by how well they support an end-to-end workflow:

> discover → identify → locate → capture → compare → safely reproduce in an
> owned lab → preserve or export the result.

A larger collection of isolated features is not, by itself, a product advantage.

## Method

The review uses the projects' official repositories and documentation. It is a
qualitative review of documented capabilities, not a controlled hardware
benchmark. The main dimensions are ESP32-DIV hardware depth, passive discovery,
capture and export, common action semantics across front ends, extensibility,
field UX, portability, release safety, testability, and shared-resource safety.

## Strategic comparison set

### ESP32-DIV original

The [original ESP32-DIV firmware](https://github.com/CiferTech/ESP32-DIV) is the
hardware and feature-coverage baseline. It demonstrates the device's breadth
across Wi-Fi, BLE, NRF24, Sub-GHz, IR, NFC, GPS, and system utilities. Leshy should
retain that hardware depth while replacing isolated screens with connected
workflows and durable artifacts.

### GhostESP

[GhostESP](https://github.com/GhostESP-Revival/GhostESP) is the closest strategic
reference for firmware as a platform. Its documented direction includes an
ESP-IDF-native core, shared commands across several front ends, portable capture
formats, multi-ESP operation, Lua and native applications, permissions, and
scoped storage.

Leshy should match the unified action and data pipeline, then differentiate with
deep ESP32-DIV integration, deterministic handling of conflicting pins/buses, a
strict Observation/Target/Session model, and a complete offline-first workflow.

### Bruce

[Bruce](https://github.com/BruceDevices/firmware) is a benchmark for feature
breadth, board portability, community contribution, scripting, and accessible
installation. Leshy should adopt clear board adapters and an easy contribution
path, but should not expand its board matrix before the core data, resource, and
workflow contracts are stable on ESP32-DIV.

### ESP32 Marauder

[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) is a mature,
focused benchmark for Wi-Fi/BLE field workflows, PCAP/SD capture, hardware
variants, and releases. Leshy should match dependable capture and export, then go
beyond the single-radio view with cross-radio sessions, comparison, source
location, and a shared observation library.

### Flipper Zero firmware

The [official Flipper Zero firmware](https://github.com/flipperdevices/flipperzero-firmware)
targets different hardware but is a benchmark for product cohesion: stable
applications, an SDK boundary, portable file formats, system/user application
separation, predictable navigation, and an extension ecosystem.

Leshy should use similarly durable application and file contracts while joining
Wi-Fi/BLE and external radios in a single session and using ESP32 networking for
a local companion interface.

## Secondary references

- [NEMO](https://github.com/n0xa/m5stick-nemo) is useful for predictable
  button-driven navigation and clear positioning, but is not the Leshy
  architecture target.
- [CapibaraZero](https://github.com/CapibaraZero/fw) is archived and directs users
  to Bruce. It is a useful warning that platform sustainability matters more than
  an ambitious feature inventory.

## Qualitative matrix

The labels describe documented product emphasis, not the presence or absence of
an individual feature.

| Project | ESP32-DIV / multi-radio | Wi-Fi capture | Data and export | Extensions | Multiple front ends | Cohesive UX |
|---|---|---|---|---|---|---|
| ESP32-DIV original | strong | present | limited | limited | limited | limited |
| GhostESP | present | strong | strong | strong | strong | strong |
| Bruce | broad board support | present | present | present | present | present |
| ESP32 Marauder | limited | strong | strong | limited | present | strong in its niche |
| Flipper Zero | different hardware | limited | strong | strong | ecosystem strength | strong |
| Leshy 1.x target | deep support | strong | strong | strong after 1.0 | strong | unified cross-radio UX |

## What 1.x must match

- reliable browser installation, OTA, and recovery;
- full probing of the standard ESP32-DIV modules and honest unavailable states;
- stable list, detail, signal/radar, and timeline views;
- session recording to SD and export in common formats;
- a library of saved signals, devices, and sessions;
- 0.x hardware parity for IR, NFC, GPS, NRF24, and CC1101 before 1.0;
- versioned configuration formats and migrations.

## Where 1.x should lead

1. A common Observation/Target/Session domain model across radios.
2. One cross-radio survey that safely schedules mutually exclusive hardware.
3. Explicit leases for SPI, radio modes, GPIO, memory, storage, and display.
4. Durable, timestamped data as the default output of discovery.
5. One action semantic for buttons, CLI, local Web UI, and automation.
6. Clear separation and confirmation of passive and active lab workflows.
7. Complete offline operation; a companion interface enhances rather than
   unlocks the product.
8. Host-tested workflows, hardware-in-the-loop drivers, verified manifests, and
   a known rollback path.
9. A single bilingual string contract plus contrast, scale, and button-only
   accessibility.

## What we deliberately do not copy

- feature-count competition and giant menus;
- separate implementations of the same action per front end;
- dozens of boards before the platform contract is stable;
- plugins with unrestricted hardware or filesystem access;
- proprietary formats where a portable format exists;
- indistinguishable passive monitoring and active lab functions.

## Derived requirements

| ID | Requirement | Priority |
|---|---|---|
| CR-001 | One Action/Command API for UI, CLI, Web UI, and automation | P0 |
| CR-002 | Sessions and capture files are first-class objects | P0 |
| CR-003 | Application descriptors, capabilities, permissions, and scoped storage | P1 |
| CR-004 | Menus and actions reflect detected hardware | P0 |
| CR-005 | PCAP and compatible IR/NFC/Sub-GHz formats where feasible | P0/P1 |
| CR-006 | Contrast, text scale, button navigation, and no color-only state | P1 |
| CR-007 | A useful offline local Web/USB companion | P1 |
| CR-008 | Stable/beta channels, signed manifest, verification, and rollback | P0 |
| CR-009 | Resource leases and safe degradation under hardware conflicts | P0 |
| CR-010 | Scenario- and result-oriented navigation | P0 |

These feed the [product requirements](PRODUCT_REQUIREMENTS.md) and must trace to
an architecture decision, test, and acceptance criterion.

## Decision

1.x starts from three foundations: this competitive snapshot, a map of actual
ESP32-DIV capabilities and conflicts, and the target user jobs/workflows. The 1.0
requirements and architecture boundary are frozen only after those foundations.

The first implementation slice is a complete **Survey Session**, not an isolated
driver: probe available hardware, collect passive observations, show a unified
list and details, and persist the session.
