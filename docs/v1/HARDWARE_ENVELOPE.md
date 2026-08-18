# ESP32-Leshy 1.x — ESP32-DIV v2 hardware envelope

*Read in: **English** · [Русский](HARDWARE_ENVELOPE.ru.md)*

Document status: **accepted constrained S1 baseline — design evidence and safe
board-01 HIL are sufficient for S2; conditional physical evidence remains S4/S5/S8**.

The reproducible procedure and isolated read-only image are documented in
[`HIL_PROBE.md`](HIL_PROBE.md); having the tool is not physical evidence by itself.

This is the normative design-time hardware map for 1.x. It separates confirmed
connections from original-firmware assumptions and per-device facts. `BoardProfile`
implements this map and may not silently override it.

## Scope and sources

The analysis uses upstream snapshot `9d4d82f` dated 7 August 2026:

- [v2 main schematic](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/Main-Schematic.jpg),
  [shield schematic](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/Shield-Schematic.jpg),
  [main BOM](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/main-BOM.xls), and
  [shield BOM](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/shield-BOM.xlsx);
- [original pin definitions](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/ESP32-DIV/shared.h),
  [TFT setup](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Libraries/User_Setup%20v2.h), and
  [build settings](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/CONTRIBUTING.md#arduino-ide-settings);
- [Espressif WROOM-1/1U datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf),
  [ESP32-S3 GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/release-v5.0/esp32s3/api-reference/peripherals/gpio.html), and
  [TI PCF8574 datasheet](https://www.ti.com/lit/ds/symlink/pcf8574.pdf).

Evidence tags are `S` schematic, `B` BOM, `O` original code, `L` Leshy prototype,
`D` vendor datasheet, and `H` physical HIL. No `H` evidence is present yet.

## Physical assembly layers

| Layer | Contents | 1.x treatment |
|---|---|---|
| v2 main board | ESP32-S3, TFT/touch, SD slot, PCF8574/buttons, WS2812, buzzer, backlight, IP5306, LF33, CP2102, two USB paths | declared by board profile, then functionally checked |
| v2 RF shield | 3× NRF24L01, CC1101, IR RX/TX, antenna routing | detachable/optional; identity probes never transmit |
| External modules | NEO-6M GPS and PN532 | absent from v2 main/shield schematic and BOM; explicit assembly profile plus probe |
| Media/power | microSD and Li-ion cell | slot/charger exist; card/cell may not |

`Gps`, `Nfc`, and even the detachable RF shield cannot be inferred from the board name.

## MCU, flash, and PSRAM conflict

The schematic and main BOM specify **ESP32-S3-WROOM-1U-N16**. Espressif identifies
that ordering code as 16 MB Quad SPI flash with **no PSRAM**. That is compatible with
using GPIO35/36/37 for display/touch; Octal-PSRAM variants reserve those lines.

| Source | Flash | PSRAM | Assessment |
|---|---:|---:|---|
| v2 schematic + BOM | 16 MB | none (`N16`) | design-confirmed for repository artifacts |
| original CONTRIBUTING settings | 16 MB | OPI PSRAM | conflicts with ordering code and display pins |
| Leshy prototype `platformio.ini` | 8 MB partitions | no-PSRAM board | not BOM-accurate; current compatibility build only |

At boot, 1.x reads actual flash, `psramFound()`, chip/package/revision, and partition
layout. Until HIL, design budgets assume **8 MB flash / no PSRAM**; a confirmed N16
release profile should expose 16 MB without requiring PSRAM.

## Normative GPIO map

| GPIO | v2 connection | Resource/capability | Evidence | Constraint |
|---:|---|---|---|---|
| 0 | BOOT button with pull-up | boot strap | S,D | never use as TFT reset/runtime output |
| 1 | 4× WS2812 data chain | status LEDs | S,B,L | 5 V LEDs; presence is HIL-only |
| 2 | buzzer transistor base and VBAT divider midpoint | buzzer/battery | S,O,0.x,U | active HIGH; clean 1.x holds output LOW from the first setup instruction as a silent safety invariant; battery ADC is disabled |
| 3 | CC1101 GDO2 | CC receive/data | S,O,D | S3 strap pin; do not reconfigure before strap sampling |
| 4 | NRF #1 CSN | radio SPI CS | S,O | idle HIGH |
| 5 | CC CSN / PN532 SS / GPS TX→ESP RX | `mux_5_6` | S/O | keep input until GPS excluded; assemblies are exclusive |
| 6 | CC GDO0 / ESP TX→GPS RX | `mux_5_6` | S/O | direction depends on assembly/mode |
| 7 | TFT backlight gate | display | S,O,L | PWM output |
| 8 | I²C SDA | control I²C | S,L | PCF8574 and IP5306 share bus |
| 9 | I²C SCL | control I²C | S,L | PCF8574 and IP5306 share bus |
| 10 | microSD CS | radio/storage SPI | S,O | idle HIGH |
| 11 | SD/NRF/CC MOSI; PN532 MISO | `spi_radio` | S,O | PN532 reverses data direction |
| 12 | SD/NRF/CC/PN532 SCK | `spi_radio` | S,O | common physical clock |
| 13 | SD/NRF/CC MISO; PN532 MOSI | `spi_radio` | S,O | PN532 requires full exclusivity |
| 14 | NRF #3 CE / IR TX | `mux_nrf3_ir` | S,B,O | idle LOW; simultaneous use forbidden |
| 15 | NRF #1 CE | NRF #1 | S,O | idle LOW |
| 16 | TFT D/C | display | S,O,L | dedicated output |
| 17 | TFT CS | `spi_display` | S,O,L | idle HIGH |
| 18 | XPT2046 CS | `spi_display` | S,O,L | idle HIGH; IRQ unconnected |
| 19 | native USB D− | native USB | S,D | unavailable as GPIO while USB is active |
| 20 | native USB D+ | native USB | S,D | unavailable as GPIO while USB is active |
| 21 | NRF #3 CSN / IR RX | `mux_nrf3_ir` | S,B,O | CS output versus IR input mode |
| 35 | TFT/touch MOSI | `spi_display` | S,O,L,D | conflicts with Octal-PSRAM variants |
| 36 | TFT/touch SCK | `spi_display` | S,O,L,D | conflicts with Octal-PSRAM variants |
| 37 | TFT/touch MISO | `spi_display` | S,O,L,D | conflicts with Octal-PSRAM variants |
| 38 | microSD card-detect candidate | media presence | S/O | code assumes active-low; HIL required |
| 43 | UART0 TX → CP2102 RX | console | S,D | unrelated to GPIO1 NeoPixel |
| 44 | UART0 RX ← CP2102 TX | console | S,D | CP2102 DTR/RTS drives reset circuitry |
| 47 | NRF #2 CE | NRF #2 | S,O | idle LOW |
| 48 | NRF #2 CSN | NRF #2 | S,O | idle HIGH |

TFT and touch physically share 35/36/37 even if legacy code creates separate
`SPIClass` instances; transactions must be serialized. The schematic connects TFT
reset to system `RESET/EN`, while original and Leshy build flags say `TFT_RST=0`.
GPIO0 is BOOT. Until continuity/HIL evidence, 1.x treats TFT reset as external (`-1`)
and never toggles GPIO0 for the display.

## Bus/resource domains

| Domain | Devices | Initial policy |
|---|---|---|
| `spi_display` | 35/36/37; TFT CS17, touch CS18, D/C16 | transaction mutex; other CS HIGH |
| `spi_radio` | 11/12/13; SD CS10, NRF CS4/48/21, CC CS5 | one owner per driver operation; other CS HIGH, CE LOW |
| `spi_pn532_bitbang` | clock12, input11, output13, SS5 | exclusive `spi_radio` + `mux_5_6` lease |
| `mux_5_6` | CC1101, GPS, PN532 SS | assembly-level exclusivity; ambiguity disables all |
| `mux_nrf3_ir` | GPIO14/21 | NRF #3 or IR after full stop/tri-state |
| `gpio2_battery_buzzer` | GPIO2 ADC/output | buzzer or diagnostic ADC; ADC disabled until HIL |
| `i2c_control` | SDA8/SCL9; PCF8574/IP5306 candidate | shared mutex; read-only probe |
| `storage` | SD filesystem + radio SPI | atomic service; writes use explicit bus windows |
| `esp_rf` | built-in Wi-Fi/BLE | coexistence scheduler |
| `console` | CP2102 UART0/native USB | explicit logging and recovery path |

SD, NRF, and CC are electrically addressable by separate CS lines, but original code
repeatedly reclaims/remounts the bus because of pinmux, clock, and library state.
Version 1.x begins with exclusive operation leases; finer sharing requires HIL/soak
evidence.

## Power envelope

Confirmed topology: IP5306 handles the Li-ion/power-bank path; LF33 creates 3.3 V from
the 5 V rail; ESP/TFT logic/touch/PCF/SD/radios use 3.3 V; WS2812, IR LED, and buzzer
circuitry use 5 V. The shield has 10 µF per NRF but peak-current and rail margins are
unknown. GPIO2 is not an independent battery ADC because it also drives the buzzer.

Unknown until HIL: LF33 exact current/thermal limit, IP5306 I²C variant/registers,
rail peak current, USB+cell behavior, multi-radio brownout margin, and useful VBAT
accuracy with the buzzer circuit attached. Simultaneous TX stress modes remain out of
scope before these measurements.

## Capability states and safe probes

Capabilities use `declared`, `detected`, `available`, `conflicted`, `fault`, or
`unknown`, not a single boolean.

| Capability | Safe boot evidence | Initial outcome |
|---|---|---|
| MCU/flash/PSRAM | runtime chip/flash/PSRAM APIs | detected |
| TFT/backlight | init without GPIO0 reset; visible HIL later | declared |
| Touch | isolated read-only sample | declared, then functional |
| Keypad | expected PCF8574 0x20 ACK + port read | detected |
| Power manager | known-address/register read only | unknown on no response |
| LEDs/buzzer | LEDs have no automatic identity; buzzer is output LOW from the first setup instruction and Diagnostics checks pad level; no sound is generated | buzzer silent invariant available/fault; sound capability not declared |
| SD | card-detect read, then read-only mount last | slot declared, media detected |
| NRF #1/#2/#3 | CE LOW; #1/#2 stable register/status read; #3 only after GPIO21/IR contention is characterized | #1/#2 independently detected; #3 unknown until HW-T08 |
| CC1101 | only after GPS exclusion; reset→IDLE, PARTNUM/VERSION read | detected/conflicted |
| GPS | GPIO5 high-Z; passively observe valid 9600-baud NMEA first | detected |
| PN532 | explicit NFC assembly only; firmware-version command, no RF field | detected |
| IR | no digital identity; infer from confirmed shield, verify HIL | declared/unknown |

Safe order: read MCU memory first; leave GPIO0/3 and contested GPIO5/6/14/21
untouched; as the only exception, preload GPIO2 LOW and set OUTPUT immediately to
prevent the false stock low-battery buzzer, never sampling it as ADC; probe I²C
read-only; passively listen for GPS on GPIO5 before driving it; only then set
CS4/48/10/5 HIGH and all NRF CE LOW while keeping GPIO21 input; read NRF #1/#2, then
CC without command strobes. NRF #3 remains gated by HW-T08. Probe PN532 only under an
explicit exclusive assembly; mount SD read-only last; initialize display/touch
without GPIO0; never exercise LEDs, activate the buzzer, IR TX, or RF TX during boot
probe. Holding the buzzer LOW is a safety invariant, not an actuator probe.

Ambiguous GPIO5/6 or 14/21 yields `conflicted`, never trial-and-error output modes.

The product does not currently execute that optional radio sequence at boot. Exact
`0.81.0-shield-receiver-probe` runs the permitted subset only after the user confirms
Full/Guided and `RadioSpi` is acquired: nRF #1/#2 and CC1101 are detected with exact
read bounds 8/2/20, nRF #3 remains gated, GPIO21 remains HIGH, and all CE-high,
strobe and TX counters remain zero (`E-HIL-106`/`E-RADIO-001`). This is software and
register-identity evidence only. HW-T06 remains partial because no RF detector was
available to prove physical silence.

Exact `0.82.0-nrf24-spectrum` adds an explicit user-started receive path, never a
boot probe. It acquires the same exclusive `RadioSpi` domain, verifies both declared
receivers, powers each into `PRIM_RX`, and raises CE only for bounded 200 us receive
windows while sweeping 83 channels. Final exact counts are 1,743 CE receive windows,
1,753 reads, 1,755 writes and 7,016 SPI bytes; TX-mode/payload commands, CC strobes
and storage writes remain zero. Stop powers both nRF devices down, restores safe pins,
keeps slot 3/GPIO21 gated/high and releases the lease (`E-HIL-107`/`E-RADIO-002`).
Without an RF detector this proves the guarded software path, not physical RF silence.

Exact `0.83.0-cc1101-spectrum` adds the corresponding explicit user-started CC1101
receive path. GPIO5 is admitted only by the no-GPS/no-PN532 board-01 profile;
`RadioSpi` remains exclusive, nRF slot 3/GPIO21 stays gated/high, and every one of
the 354 samples uses only the whitelisted RX/IDLE sequence after one reset. Final
wire counts are 1 reset, 354 RX and 713 IDLE strobes, 11,443 reads, 1,078 writes and
26,110 SPI bytes; TX, rejected strobe, PATABLE, FIFO and storage-write counters are
zero. Stop leaves CC1101 IDLE and releases the lease (`E-HIL-108`/`E-RADIO-003`).
Without an RF detector or calibrated source this proves neither physical RF silence
nor calibrated RSSI/frequency accuracy.

Exact `0.84.0-full-guided-rf` reuses those guarded receive adapters only after the
Full/Guided preflight. Plan v5 acquires `RadioSpi`, completes one 83-channel sweep on
both nRF24 receivers and one 64-bin CC1101 433 MHz sweep, then returns both adapters
to safe state before release. The accepted run accounts 83 RX CE windows and
1 reset/64 RX/129 IDLE CC1101 strobes with zero TX-mode/payload/TX-strobe/PATABLE/
FIFO/storage counters (`E-HIL-109`/`E-RADIO-004`). This remains software-counter
evidence; HW-T06 is still partial without an RF detector.

Exact `0.85.0-full-guided-artifacts` releases that RF phase before acquiring the
declared `Storage|RadioSpi` set for its persisted-artifact phase. It re-identifies
CID `FE343253440000002000000055019CB7`, mounts the SD card read-only, recovers the
latest atomic Session through the same guarded path used at boot, streams its
Library/export artifacts only to discard sinks, then unmounts and releases both
resources. `E-HIL-110` observes generation 83/observation 0 continuity, zero blocked
or attempted storage writes, a byte-counted 16-frame PCAP and final lease 0. This is
read-only workflow evidence, not the separate controlled power-cut test.

Exact `0.86.0-full-guided-disposable` then uses the same exclusive resource set in
three non-overlapping phases: exact-CID writable scratch commit, read-only remount and
export, and exact typed cleanup. `E-HIL-111` observes three writes/504 bytes only in
`/leshy-hil/full-guided-v7`, zero product writes, removal of all three scratch files,
unchanged product generation 83/0 and final lease 0. It does not replace physical
power-cut or instrumented RF-silence evidence.

GPIO2 software evidence: the author's root-cause description and one-line LOW fix in
[upstream issue #117](https://github.com/cifertech/ESP32-DIV/issues/117#issuecomment-5178973211)
links the verified
[0.x commit `04fd290`](https://github.com/anton-vinogradov/esp32-leshy/blob/04fd290019dc2d80a53d8c86599b4380fd74ac47/src/main.cpp#L2883).

## HIL plan

| Test ID | Procedure | Evidence |
|---|---|---|
| HW-T01 | Record module marking and runtime chip/flash/PSRAM on at least two v2 boards | photo + diagnostic bundle |
| HW-T02 | Continuity GPIO0/TFT RESET and RESET-EN/TFT RESET | resistance/logic trace |
| HW-T03 | Logic-analyze display/touch and radio SPI | CS idle levels, modes, verified clocks |
| HW-T04 | Read-only I²C scan/read of PCF8574 and IP5306 | addresses/register behavior |
| HW-T05 | SD CD, read-only mount, radio↔SD recovery, power-cut write | trace + recovered filesystem |
| HW-T06 | Read identities of NRF #1/#2 and CC with no RF event | register log + RF detector silence |
| HW-T07 | Test separate GPS and PN532 assemblies | NMEA/version log, no contention |
| HW-T08 | Characterize GPIO21 contention, then NRF3 identity/switch, directions, and physical stop | logic trace + NRF register log + IR test |
| HW-T09 | Characterize GPIO2 buzzer/VBAT coupling | scope/ADC series |
| HW-T10 | Measure rails for idle, display, SD, passive radios, combined Survey | min/avg/peak, temperature, margin |
| HW-T11 | Verify native USB and CP2102 reset/download/recovery | port IDs + recovery transcript |

## Hardware uncertainties and binding dispositions

`constrained` resolves the software/scope ambiguity without claiming the physical
unknown was measured. The safe default remains binding until the named closure
evidence exists; a constrained device cannot be promoted to `available` by a build
flag or a successful unrelated probe.

| ID | Evidence state | Binding safe default for 1.x | Physical closure |
|---|---|---|---|
| HW-U01 | partial: board-01 is S3 rev 0.2, 16 MiB Quad, no PSRAM; batch range unknown | baseline profile is N16/no-PSRAM; any flash/PSRAM/profile mismatch is `fault`/unsupported | HW-T01 on second v2 unit + assembly IDs |
| HW-U02 | unmeasured: schematic and legacy flag conflict | TFT reset is external/unassigned; GPIO0 remains BOOT-only and is never driven as display reset | HW-T02 continuity/logic trace |
| HW-U03 | partial: read-only I²C responds at `0x75`; exact power-manager identity/map unknown | expose only generic presence/evidence; battery percentage and write/control operations are unavailable | exact marking/datasheet + HW-T04 |
| HW-U04 | design-only LF33 evidence; current/thermal headroom unknown | no default combined shield load; each new combination remains unavailable under RB-08 | marking + HW-T10 rail/thermal matrix |
| HW-U05 | operator reports no GPS/PN532 assembly on board-01; no standard connector contract proven | default profile declares both absent; either requires its own explicit assembly profile, never output-mode autodetect | assembly photo/spec + HW-T07 |
| HW-U06 | partial: GPIO38 reads LOW with one inserted/identified card; polarity/batch consistency remain unmeasured | GPIO38 is not authoritative in S2; storage state comes from a bounded explicit operation and remains fault/absent on failure | HW-T05 across media and board batch |
| HW-U07 | partial: three guarded SD identity runs and the exact 0.81 sequential receiver probe complete with exclusive RadioSpi, GPIO21 HIGH, stable CID/CSD/generation and cleanup; instrumented coexistence remains unmeasured | `spi_radio` is an exclusive operation lease; SD and shield receivers never overlap | HW-T03/HW-T05 + radio→SD→radio recovery + RB-07 endurance |
| HW-U08 | electrical/ADC behavior is unmeasured; the false-sound software root cause is confirmed by 0.x and upstream issue #117 | battery percentage is unavailable; GPIO2 is never ADC-sampled and is held OUTPUT LOW from the first setup instruction; HIGH belongs only to a future bounded sound service | HW-T09 for ADC/sound characterization; silent invariant closes through boot/runtime state plus audible observation |
| HW-U09 | no safe passive digital identity | IR is available only from an explicit RF-shield profile; no autodetect; IR TX additionally requires Lab/ADR-002 evidence | assembly manifest/detector + HW-T08 |
| HW-U10 | no rail peak/thermal measurement | first slice is Wi-Fi-only; shield operations are one receiver at a time after per-module HIL; combined modes unavailable | HW-T10 and RB-08 endurance |

## Architecture consequences

- This document is design-time pin/resource truth; `BoardProfile` references its
  revision and does not contain untraceable “verified” claims.
- HardwareProbe returns state plus evidence, not a capability bitmask alone.
- GPS and PN532 require explicit assembly profiles; autodetect may not trial contested
  outputs.
- ResourceBroker adds `spi_display`, `spi_radio`, `mux_5_6`, `mux_nrf3_ir`,
  `gpio2_battery_buzzer`, `i2c_control`, `storage`, and `esp_rf`.
- BoardSafeOutputs establishes GPIO2 OUTPUT LOW before console/display, and a static
  check prevents apps/drivers from changing the buzzer pin directly.
- 1.x has no OPI-PSRAM dependency until `HW-U01` proves a compatible variant that
  does not collide with the display pins.
- Passive Wi-Fi remains the provisional first Survey source because it bypasses all
  external mux conflicts while validating the Session pipeline.
