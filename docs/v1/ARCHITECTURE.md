# ESP32-Leshy 1.x target architecture

*Read in: **English** · [Русский](ARCHITECTURE.ru.md)*

Document status: draft architecture for the clean 1.x line. Firmware 0.x is frozen as a
separate PoC and a source of validated hardware knowledge. Version 1.x does not
depend on its `main.cpp`, menu tree, or global state. A low-level fragment may be
reused only after it is isolated behind a 1.x contract and tested independently.

Binding choices that refine this draft live in the
[accepted ADR index](adr/README.md). In a conflict, an accepted ADR takes precedence
over this general architecture text.

## Why change

At the audit baseline, `main.cpp` has 3,181 lines and owns navigation, global screen
state, rendering, driver lifecycle, radio coexistence, and serial QA. Lifecycle logic
is repeated across `launch()`, `back()`, serial commands, and the main `loop()`.

That makes features expensive and teardown unsafe. Physical pin conflicts are known
to individual drivers, not to the system, and most behavior is testable only on the
device. Existing non-blocking scans, OTA/rollback, and driver code remain useful as
evidence and implementation references. They are not linked into 1.x until they
satisfy a new driver contract and its tests.

## Layers

```text
apps/       Survey · Targets · Wi-Fi · BLE · Sub-GHz · IR · NFC · GPS · Lab
sdk/        Application · events · views · capture API · safety API
services/   observations · sessions · library · settings · OTA · diagnostics
kernel/     AppRuntime · Navigator · ResourceBroker · scheduler · event bus
drivers/    Wi-Fi/BLE · NRF24 · CC1101 · PN532 · GPS · IR · SD · display/input
boards/     pin map · electrical conflicts · build flags · capability probes
platform/   Arduino-ESP32 / FreeRTOS adapters
```

Dependencies point down. Drivers never open screens, apps never manipulate another
app's driver or global state, and services do not know about the TFT.

## Board profile and capabilities

The normative design-time source is
[`HARDWARE_ENVELOPE.md`](HARDWARE_ENVELOPE.md): evidence, the physical pin map,
assembly variants, safe probing, and unresolved facts. `BoardProfile.h` is a
versioned implementation of its accepted subset, not an independent source of facts.

`HardwareInventory` records `declared`, `detected`, `available`, `conflicted`,
`fault`, or `unknown` plus evidence and reason. It distinguishes the main board, the
detachable RF shield, removable media, and explicit external GPS/PN532 assemblies.
The app registry consumes only the compatible `available` projection.

Important v2 conflicts are explicit:

- TFT and touch share physical SPI GPIO 35/36/37 and require serialized transactions;
- NRF24, CC1101, and SD share radio SPI 12/13/11; PN532 reverses the data direction on 11/13;
- CC1101/PN532 and GPS overlap GPIO 5/6, so ambiguous auto-probing is forbidden;
- NRF24 slot 3 and IR overlap GPIO 21/14;
- GPIO2 couples the buzzer actuator and battery divider;
- the schematic connects TFT reset to RESET/EN while legacy flags use BOOT GPIO0;
- BOM module N16 has no PSRAM, while display GPIO35–37 conflict with Octal-PSRAM variants.

Detected hardware drives the app registry and menu. An unavailable app explains the
missing module in Diagnostics instead of failing after its screen opens.

The first broker domains are `spi_display`, `spi_radio`, `mux_5_6`,
`mux_nrf3_ir`, `gpio2_battery_buzzer`, `i2c_control`, `storage`, and `esp_rf`.
Radio SPI begins with exclusive operation leases; transaction-level sharing requires
HIL and endurance evidence. GPS/PN532 require explicit assembly profiles.

## Application runtime

Every app declares a stable ID, capabilities, exclusive resource domains, and one of
`Passive`, `Connected`, `Transmit`, or `Disruptive`. It implements `onStart`,
`onEvent`, `onTick`, and `onStop`.

`AppRuntime` validates capabilities, atomically acquires leases, and always releases
them after stop or failed start. `Navigator` owns the fixed-size screen stack and each
level's selection. Back becomes a system event instead of a branch repeated by screens.

Physical buttons, touch, and local diagnostic control produce the same normalized
Actions and enter that Navigator path. The diagnostic client reads actual TFT GRAM
and records state/revision evidence; it never owns a second navigation model. The
binding transport and acceptance rules are in
[`UI_AUTOMATION.md`](UI_AUTOMATION.md).

## Concurrency and memory

- Core 1 owns UI/navigation; callbacks should not block for more than 10 ms.
- Core 0 runs bounded radio/storage workers that publish immutable snapshots or events.
- ISRs only enqueue timestamped edges into preallocated queues.
- Long work has cancellation and progress; all queues are bounded and count drops.
- Steady state avoids repeated heap allocation; large buffers belong to reusable services.
- No mandatory path relies on PSRAM until `HW-U01` is resolved. Boot diagnostics
  records actual flash, partition table, package/revision, and PSRAM presence.

Source ingress never waits on filesystem durability barriers. Each receiver publishes
normalized Observations into a fixed-capacity ring owned by the Survey service; the
storage worker drains a bounded batch into the current segment and publishes a new
atomic head only on explicit stop, size/time threshold, or safe-shutdown request.
Queue depth, high-water mark, and drops are Session evidence. E-HIL-037 measures
passive Wi-Fi p99 at 546 encoded B/s and therefore sets the first RB-06 storage target
at 2,184 B/s. E-HIL-038's fixed batch delivers 9,068 B/s and E-HIL-039's real
Wi-Fi→FIFO→SessionStore path delivers 6,921 B/s with high-water 9/64 and zero drops.
E-HIL-040 repeats that path through ordinary Library/export at 12,957 B/s,
high-water 18/64, zero drops, recovered generation 1/52 observations, and
persistent/real provenance in List/Detail/Export. The latter remains a sequential
diagnostic command; it proves service rate, data path, and current-boot admission,
not the product worker invariant that receiver ingress never waits on a durability
barrier or boot-time catalog/recovery.

Product activation is a separate fail-closed boundary. `ProductStorePolicy` fixes
the only current product root at `/leshy/sessions/v1`: automatic catalog recovery
requires an already enrolled exact media fingerprint, an existing root, a guaranteed
read-only non-writable driver, and Storage+RadioSpi ownership. Initialization and
commit additionally require an explicit user selection, writable driver, and bounded
size/reserve. `ProductSurveyAdmission` then requires explicit Start, a validated
passive plan, a writable commit permit, and combined EspRf+Storage+RadioSpi ownership.
It never silently replaces a requested real/persistent Session with simulated/RAM.
These policies authorize no I/O themselves; the board adapter lifecycle remains the
next implementation boundary.

## Data model

Raw observation is separate from interpretation:

```text
Observation { session, time, location?, radio, frequency, RSSI, identity?, payload ref, annotations[] }
Target      { local id, identities[], first/last seen, tags, notes }
Capture     { immutable source blob, metadata, derived decodes[] }
Session     { device/build/calibration, start/end, track, observations[] }
```

Versioned CBOR metadata and immutable payloads live under `/leshy` on SD, with
LittleFS fallback. PCAP, CSV, JSON, and radio-specific formats are import/export
formats, not the internal source of truth.

## Safety and release integrity

TX apps require a Lab context with visible frequency, power, timeout, indication, and
immediate stop. A shared regulatory policy blocks disallowed bands. Firmware and its
manifest should be signed; SHA-256 verifies integrity but not origin. File and network
parsers are host-fuzzed, and credentials never enter session exports.

## 1.x implementation sequence

1. Freeze the board capability/conflict map and reference workflows.
2. Create an independent 1.x build target with the board profile, runtime, broker,
   and Navigator; treat the existing contract prototype as an experiment, not an
   extension of 0.x.
3. Bring up display, input, storage, and HardwareProbe without the legacy menu.
4. Build the first end-to-end Survey Session slice: one passive source → Observation
   → List/Detail → persisted Session → reopen.
5. Add receivers through new driver contracts and recorded traces; port only
   validated hardware operations, not 0.x screens or global state.
6. Grow Survey into cross-radio operation, then implement Targets and a reboot-backed Library catalog.

All new 1.x code must sit behind 1.x contracts, build independently from 0.x, and
have host/HIL verification. The 0.x archive is not changed to make new development
easier.
