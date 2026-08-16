# ESP32-Leshy 1.x clean measurement target

*Read in: **English** · [Русский](README.ru.md)*

This is the first independent 1.x build tree. It is an S1/S2 bootstrap and resource
measurement target, not a user firmware or a completed stage.

- compiles no 0.x source;
- pins the accepted ADR-001 toolchain and a 16 MiB no-PSRAM profile;
- initializes only the display/backlight and read-only PCF8574 input path; it starts
  no radio, storage, buzzer, IR, or contested GPIO;
- emits bounded NDJSON boot/resource evidence over native USB and UART0;
- implements the fixed-capacity multi-state HardwareInventory contract;
- routes physical and diagnostic keys through one `UiController` and exposes tiled
  TFT GRAM capture for reproducible PNG evidence;
- compiles the dual-head atomicity contract and fail-closed disposable-media guard;
  boot leaves mount/format/write disabled, while one explicit exact-CID HIL command
  can run the common `SessionStore` only inside a fresh bounded disposable-card path;
- projects its home menu from `HardwareInventory`: Diagnostics is available while
  Survey/Library are disabled with a reason until their capabilities are available;
- launches enabled entries through the clean-tree `AppRuntime` and atomically
  releases all foreground `ResourceBroker` leases on Back;
- defines the first bounded Survey/Observation model and a passive-only Wi-Fi ingress
  contract; the measurement image renders a clearly simulated golden List/Detail/Stop
  workflow but does not start or touch the radio;
- encodes the stopped golden Session as deterministic CBOR plus a framed CRC32C
  segment, validates it through an in-memory atomic head, reopens it with radios off,
  and formats a bounded JSON summary; the guarded HIL path additionally commits two
  generations to FAT, unmounts/remounts, and reopens the newest generation read-only;
- measures the production-candidate ESP-IDF SDSPI/FatFs path at actual 4 MHz over
  32 commits, reporting exact `FRESULT`, fixed p50/p95/p99 timing, sync counts,
  allocation delta, heap, and generation-32 recovery after a real remount;
- implements, but does not run automatically, a six-boundary software-reset HIL
  path: exact-CID/new-namespace arm, `esp_restart` after the selected successful
  operation, then exact-CID read-only recovery with prior-hash and zero-write checks;
  board-01 passed all six boundaries with recovered generations `1/1/1/1/1/2`, and
  the runner now checkpoints each boundary and bounds fail-closed media-readiness retries;
- shares the caller-owned SessionStore validation/recovery workspace; 0.31 removes
  one redundant 4,672-byte Session buffer, returns static RAM below RB-03, and passes
  a guarded physical boundary-6 regression;
- provides an explicit measurement-only passive Wi-Fi source in 0.32: NVS and
  credentials off, no active/connect/config/raw-TX API, EspRf lease, scrubbed
  identifier-free aggregate evidence, and fixed p50/p95/p99 encoded ingress rates;
- adds a fixed 64-observation FIFO and 2 KiB/5 s/Stop/safe-shutdown policy in 0.33;
  a guarded physical 32×64 batch run delivers 9,068 encoded B/s against the RB-06
  requirement of 2,184 B/s and recovers generation 32 after remount;
- joins real passive Wi-Fi→FIFO→guarded SessionStore in 0.34: 29 observations,
  high-water 9/64, zero drops, latency commit, and read-only reopen after remount;
- admits the recovered physical Session to ordinary Library in 0.35 without
  restoring the simulated fixture: Home/List/Detail/Export show persistent/real
  provenance and serial export carries `persistent=true`, `simulated=false`;
  boot-time catalog remains the next separate step;
- in 0.36 reports the full ESP app ELF SHA-256 from the descriptor of the running
  image; the pre-release runner independently extracts that digest from the
  candidate and requires exact equality at cold boot and in a repeated metrics
  record;
- in 0.37 accepts a bounded `hil.begin/end` envelope: one 128-bit run ID and exact
  app identity bind device execution to manifest/run/attestation without bypassing
  UI, permissions, or resource leases;
- uses a provisional dual-OTA/LittleFS partition layout governed by ADR-003/RB-02.

Build without flashing:

```sh
tools/build_1x_measure.sh
```

Host contracts and isolation checks run through `tools/test.sh`. Physical flashing is
an evidence operation and requires a verified full backup and the same restoration
procedure as `HIL_PROBE`.

The reset matrix runner has an additional deliberate acknowledgement and must only
target an explicitly selected disposable card:

```sh
"$HOME/.platformio/penv/bin/python" tools/run_1x_sd_reset_matrix.py \
  --port /dev/cu.usbmodem2101 --cid <CID32> --run-prefix <new-prefix> \
  --output reset-matrix.json --execute-reset-matrix
```

The evidence and remaining scope are maintained in
[`docs/v1/STORAGE_HIL.md`](../../docs/v1/STORAGE_HIL.md).

Drive and capture the probe UI without resetting it:

```sh
"$HOME/.platformio/penv/bin/python" tools/capture_1x_ui.py \
  --port /dev/cu.usbmodem2101 --keys down,down,select --output ui.png
```

The report separates runtime-, display-, input-, and first-render-ready milestones.
TFT GRAM capture replaces routine screen photography; physical brightness/panel
checks and external boot timing are still required for final NFR-001 evidence.
