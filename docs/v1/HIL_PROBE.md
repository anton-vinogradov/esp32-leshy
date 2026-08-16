# ESP32-Leshy 1.x — S1 HIL probe operator protocol

*Read in: **English** · [Русский](HIL_PROBE.ru.md)*

Document status: **evidence-collection procedure; no physical-board results exist
yet**.

This procedure serves the tests in
[`HARDWARE_ENVELOPE.md`](HARDWARE_ENVELOPE.md). The hardware map remains normative;
the diagnostic image only collects reproducible evidence and is neither the 1.x
target nor user firmware.

## Artifact and safety boundary

The isolated PlatformIO project is under `diagnostics/hil_probe`. It links no 0.x
code, Wi-Fi/BLE, RF24, or RadioLib and emits JSON Lines to both native USB and
UART0/CP2102 at 115200 baud.

Image invariants:

- NRF CE15/47/14 is driven LOW before consoles start and is never raised;
- Wi-Fi, BLE, RF/IR TX, buzzer, LEDs, display, touch, and SD never start;
- GPIO0/2/3/5/6/21 and radio SPI remain inputs until a selected read-only procedure;
- I²C uses only `requestFrom`, with zero register/config writes;
- GPS uses GPIO5 as UART RX only, with the TX pin disabled;
- CC1101 receives only status-register reads `0xF0/0xF1`, with no command strobes;
- NRF #1/#2 receive only `R_REGISTER`; slot #3 is not selected before `HW-T08`;
- radio reads require an exact operator phrase confirming GPS and PN532 are absent.

The static check establishes that the source has no known TX path. Physical silence
still requires the logic-analyzer/RF-detector evidence in `HW-T06`.

## Build

```bash
tools/build_hil_probe.sh
shasum -a 256 diagnostics/hil_probe/.pio/build/esp32-div-hil-probe/firmware.factory.bin
```

Expected artifact:
`diagnostics/hil_probe/.pio/build/esp32-div-hil-probe/firmware.factory.bin`.
Record its SHA-256, commit/worktree state, probe version, and board identity with the
captured JSONL.

Flashing changes device contents. Preserve any needed 0.x data and record the
recovery path first. Upload only to an explicit port:

```bash
pio run -d diagnostics/hil_probe -t upload --upload-port /dev/cu.EXPLICIT_PORT
pio device monitor --port /dev/cu.EXPLICIT_PORT --baud 115200
tools/capture_hil_serial.py --port /dev/cu.EXPLICIT_PORT \
  --output evidence.log --command inventory --command i2c-read
tools/capture_hil_serial.py --port /dev/cu.EXPLICIT_PORT \
  --output rf-evidence.log --rf-read-confirmed
```

Codex does not flash the board or claim HIL pass without an operator, an identified
port, and saved observable results.

## Commands

| Command | Test | Action | Preconditions |
|---|---|---|---|
| `inventory` | HW-T01, HW-T11 | chip/revision/eFuse MAC, physical flash ID/size, PSRAM, heap, partitions, reset/toolchain | automatic at boot; no GPIO changes |
| `i2c-read` | HW-T04 | read-only 0x08…0x77 sweep on GPIO8/9, retaining the first read byte | standard main board only |
| `gps-listen` | HW-T07 | listen on GPIO5 RX/9600 for 10 seconds and count valid-checksum NMEA without printing coordinates | CC/PN532 remain inactive |
| `rf-read shield-no-gps-no-pn532` | HW-T06 | after a 2.2-second GPS preflight, read NRF #1/#2 and CC1101 identity at 1 MHz SPI | operator physically removed GPS and PN532 and installed the RF shield |
| `help` | — | print protocol and safety warning | always |

The capture-tool flag `--rf-read-confirmed` is allowed only after the operator
physically excludes GPS/PN532; it sends the exact long command. This is an accidental
invocation guard, not a security boundary.

The RF command is intentionally long. It prevents accidental invocation but is not
a security boundary. Valid NMEA aborts before GPIO5 changes. No NMEA does not prove
GPS absence, so operator confirmation remains mandatory.

NRF #3 reports `unknown`: GPIO21 is both its CSN and the IR-receiver output. `HW-T08`
must characterize idle levels and contention before any output probe is added.

## One HIL session

1. Assign a stable `board-id`; photograph both sides, ESP module marking, RF shield,
   and connected external modules.
2. With USB and battery fully disconnected, run `HW-T02` continuity separately for
   GPIO0↔TFT RESET and RESET/EN↔TFT RESET; retain meter/range/resistance.
3. Restore power and flash the hash-identified HIL image through an explicit port.
4. Capture boot JSONL through CP2102 and run `inventory`; repeat connection and the
   command through native USB. This covers the console portion of `HW-T11`.
5. Run `i2c-read`. Preserve PCF8574 address/value; do not infer an IP5306 variant
   from an ACK alone.
6. Test external GPS as a separate assembly using `gps-listen`, without RF-shield
   reads. This image does not probe PN532 until `HW-U05` confirms connector/wiring.
7. Remove GPS and PN532 completely, install the RF shield, remove IR sources, and
   attach a logic analyzer/RF detector. Only then enter the exact RF command.
8. Verify CE15/47/14 remains LOW and the detector sees no transmission. Register
   values without this trace do not close `HW-T06`.
9. Run manual HW-T03/HW-T05/HW-T08…HW-T11 procedures from the hardware envelope.
10. Preserve raw JSONL/traces/photos and add a manifest with board-id, image hash,
    wiring, instruments, operator, timestamp, and verdict for each test ID.

## Verdict rule

- `pass`: procedure and observation meet acceptance, with raw evidence attached;
- `fail`: a reproducible incompatible result exists;
- `inconclusive`: measurement ran but cannot distinguish the variants;
- `not-run`: no evidence exists.

JSONL `detected` is not HIL `pass`; it only classifies read bytes. A floating bus or
unexpected module stays `unknown/fail` and is not “fixed” by broadening accepted
values without new evidence.
