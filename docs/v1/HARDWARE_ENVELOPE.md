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
`D` vendor datasheet, and `H` physical HIL. Physical evidence now covers two
assemblies and is retained in
[`board-02-hardware-variant-20260823.json`](../../tests/hil/evidence/board-02-hardware-variant-20260823.json).

## Physical assembly layers

| Layer | Contents | 1.x treatment |
|---|---|---|
| v2 main board | ESP32-S3, TFT/touch, SD slot, PCF8574/buttons, WS2812, optional-by-assembly buzzer, backlight, IP5306, LF33, USB bridge, two USB paths | declared by an exact assembly profile, then functionally checked |
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
| Leshy product `platformio.ini` | 16 MB physical flash, bounded partitions | PSRAM disabled | compatible conservative profile on both observed modules |
| board-01 ROM/photo | 16 MB | none (`N16`) | known-positive original assembly |
| board-02 ROM/photo | 16 MB | 8 MB embedded Octal (`N16R8`) | real variant; PSRAM is not admitted because it collides with display GPIO35/36/37 |

At boot, 1.x reads actual flash, `psramFound()`, chip/package/revision, and partition
layout. The binding portable budget is now **16 MB flash / no usable PSRAM**. The
board-02 ROM reports its embedded 8 MB, but enabling it boot-looped the display build;
the exact compatibility image runs with `psramFound=false`. No feature may count that
memory until a distinct pin-compatible board profile proves both display and PSRAM.
The N16R8 substitution does not renumber the module pads or remap application GPIOs;
it makes IO35/36/37 unavailable because they are internally connected to Octal PSRAM.
The v2 radio set (GPIO3–6, 11–15, 21, 47 and 48) does not intersect those pins, so
the processor-memory variant explains the display/PSRAM conflict but not the
common-zero radio identity.

## Observed assembly profiles

| Profile | Main module and population | RF result | Admission |
|---|---|---|---|
| `esp32-div-v2-n16` / board-01 | `ESP32-S3-WROOM-1U-N16`; BOM buzzer populated | exact 0.81 reads two permitted nRF identities and CC1101 VERSION `0x14` | known-positive baseline |
| `esp-div-n16r8-dnp-unqualified` / board-02 | `ESP32-S3-WROOM-1U-N16R8`; buzzer omitted; CC1101 AS07 antenna-interface population differs from board-01 and its U.FL is unused | assembled exact 0.130 reads zero identities and MISO LOW 0/32 under both pulls; isolated-main exact 0.131 reads the same GPIO13 HIGH 32/32 under both pulls after the detachable RF carrier is removed | display/input compatibility only; carrier-side RF `fault`, fixture TX forbidden |

Exact 0.139 applies the software assembly overlay `stock-rf-no-gps-no-pn532` to
board-01. This makes the observed stock RF carrier applicable while declaring GPS
and PN532 `not_applicable`; neither contested GPIO output nor speculative module
probe is used to infer their absence.

Both carriers contain three nRF24-compatible modules with external PA/LNA front ends
and one CC1101 module. The shield BOM specifies the latter as **433 MHz, 10 mW**;
315/868/915 MHz are therefore software tuning choices, not proven useful bands for
this physical assembly. The shield schematic also proves that R2/R4 are alternative
antenna links and R3/R5 belong to IR TX; their population cannot explain a missing
SPI identity. All four receivers share direct 3.3 V and SPI through the 2×10
connector. Comparative DC measurements now show board-02 at approximately 4.7/3.3 V
and the working board-01 at 4.35/3.2 V on the assembled connector, so an absent idle
rail is no longer a supported explanation. Exact 0.130 then holds every CE LOW,
samples GPIO13 under both internal pulls and performs four nRF NOP reads: board-01
stays HIGH 32/32 with NOP STATUS `0x0E`, while board-02 stays LOW 0/32 with STATUS
`0x00` before and after a powered-off reseat. Powered-off MISO-to-ground resistance is
23 kΩ on board-02 versus 32 kΩ on board-01, rejecting a hard passive short. Exact
0.131 then samples the isolated board-02 main hardware with the detachable RF carrier
absent and changes the same observed GPIO13 to HIGH 32/32 under both pulls, with zero
SPI clocks, receiver reads, CE-high events, command strobes or TX commands. GPIO13 is
also the main-board SD MISO line, so this high-dominant isolated state is not evidence
of a damaged ESP input. The assembly-dependent LOW localizes the powered/logic-dependent
clamp to the RF carrier or its connector side. See the
[assembled characterization](../../tests/hil/evidence/board-02-rf-bus-characterization-0.130.json)
and [isolated-main characterization](../../tests/hil/evidence/board-02-isolated-main-miso-0.131.json).
The visible antenna-interface difference is not an RF-continuity result and cannot
explain missing digital identity. Do not add solder or infer a broken U.FL path from
photo appearance alone. Exact 0.132 reattaches the carrier and samples CSN GPIO4, 48,
21 and 5 HIGH 32/32 each while MISO remains LOW 0/32 under both pulls. It clocks zero
SPI bytes and performs zero reads, CE-high events, strobes or TX commands. Thus a
selected receiver is not holding the line: a carrier module or the carrier shared-MISO
net fails to tri-state. The shared direct power/MISO topology prevents further
software-only per-module isolation. See the
[carrier-CSN evidence](../../tests/hil/evidence/board-02-rf-carrier-csn-0.132.json).

Upstream community evidence has the same failure shape but does not prove this unit's
root cause. [Issue #102](https://github.com/cifertech/ESP32-DIV/issues/102) reports
simultaneous NRF24/CC1101 initialization loss from interboard cold joints or oxidized
contacts and recommends checking shield rails plus CE/CSN. Leshy adopts the rail and
continuity checks, but not that report's CE-high criterion: passive admission requires
CE to remain LOW until a plausible receiver identity exists. [Discussion
#90](https://github.com/cifertech/ESP32-DIV/discussions/90) also reports a failed nRF
initialization poisoning later shared-bus operations. That is a weaker fit here because
the exact Leshy image performs independent bounded reads after a clean boot and still
gets common-zero identities. White-screen reports in that discussion and issues
[#135](https://github.com/cifertech/ESP32-DIV/issues/135),
[#157](https://github.com/cifertech/ESP32-DIV/issues/157), and
[#158](https://github.com/cifertech/ESP32-DIV/issues/158) do not identify N16R8 or
GPIO35/36/37 as their cause and therefore remain background only.

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
circuitry use 5 V. The shield has 10 µF per NRF and takes 3.3 V directly from pin 18
of the interboard connector; pin 20 supplies 5 V. User-observed idle DC values are 4.35/3.2 V on
board-01 and 4.7/3.3 V on board-02; meter accuracy, ripple, peak-current and thermal
margins remain unknown.
GPIO2 is not an independent battery ADC because it also drives the optional buzzer.
Exact 0.139 therefore keeps it OUTPUT LOW and reports voltage/battery percentage as
unavailable. I²C address `0x75` ACKs read-only, but the power-manager type and register
map remain unidentified; no charge-control or percentage claim follows from the ACK.

Unknown until HIL: LF33 exact current/thermal limit, IP5306 I²C variant/registers,
rail peak current, USB+cell behavior, multi-radio brownout margin, and useful VBAT
accuracy with the buzzer circuit attached. Simultaneous TX stress modes remain out of
scope before these measurements.

The [software Safety Supervisor](SAFETY_SUPERVISOR.md) can immediately force the
active-high buzzer and all declared nRF CE paths LOW, then latch the exact firmware
in Safe Mode. The confirmed board has no independent rail kill, temperature/current
sensor, or CC1101 reset/power gate, so this control does not close `HW-U04`,
`HW-U09`, `HW-U10`, `R-009`, or `R-018` as a physical-safety claim.

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
| NRF #1/#2/#3 | CE LOW; stable register/status read per selected CS; #3 only inside the exclusive nRF side of the GPIO14/21 mux | all three independently detected in nRF mode; physical mux contention remains constrained by HW-T08 |
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

The boot paragraph above is the conservative automatic-probe policy; it is not the
current explicit runtime result. Exact 0.100 supersedes the older 0.81 software
gating after the user selects nRF reception: all three independently addressed nRF
slots are active with mask `7`. Exact 0.104 adds the mutually exclusive IR side of
the same mux: nRF #3 is fully stopped, GPIO14 and every CE remain LOW, and GPIO21 is
input-only while 345,272 passive samples are taken. nRF and IR are never active
simultaneously. This closes the software ownership/direction part of HW-T08; a known
physical IR stimulus and instrumented electrical trace remain open.

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
| HW-T08 | Partial: exact nRF mask 7 plus exclusive IR switch/directions/stop are proven in software; characterize GPIO21 electrically and apply a known IR signal | logic trace + NRF register log + IR test |
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
| HW-U01 | partial: board-01 is N16/no-PSRAM; board-02 is an N16R8/DNP variant whose embedded 8 MiB Octal PSRAM conflicts with display GPIO35/36/37 and is unusable in the compatibility image | portable baseline is 16 MiB flash with PSRAM disabled; N16R8 is a distinct unqualified profile, never dynamic budget expansion | additional batch IDs plus a pin-compatible display/PSRAM profile if one exists |
| HW-U02 | unmeasured: schematic and legacy flag conflict | TFT reset is external/unassigned; GPIO0 remains BOOT-only and is never driven as display reset | HW-T02 continuity/logic trace |
| HW-U03 | partial: read-only I²C responds at `0x75`; exact 0.139 exposes the ACK while keeping power-manager identity/map and voltage unavailable | expose only generic presence/evidence; battery percentage and write/control operations are unavailable | exact marking/datasheet + HW-T04 |
| HW-U04 | partial: idle connector rails are user-measured at 4.35/3.2 V on working board-01 and 4.7/3.3 V on board-02; ripple, peak and thermal margin are unmeasured | no active board-02 RF fixture and no default combined shield load; each new combination remains unavailable under RB-08 | calibrated dynamic HW-T10 rail/thermal matrix |
| HW-U05 | exact 0.139 applies `stock-rf-no-gps-no-pn532` to board-01; no standard expansion connector contract is proven | stock profile reports both `not_applicable`; either module requires its own explicit assembly profile, never output-mode autodetect | future equipped assembly + HW-T07 |
| HW-U06 | partial: GPIO38 reads LOW with one inserted/identified card; polarity/batch consistency remain unmeasured | GPIO38 is not authoritative in S2; storage state comes from a bounded explicit operation and remains fault/absent on failure | HW-T05 across media and board batch |
| HW-U07 | partial: exact 0.130 reads valid receiver identities and MISO HIGH 32/32 on board-01, but assembled board-02 holds shared MISO LOW 0/32 under both pulls before/after reseat despite valid idle rails; powered-off MISO-to-ground is 23 kΩ versus 32 kΩ, rejecting a hard short; exact isolated-main 0.131 changes GPIO13 to HIGH 32/32 without the carrier; exact reassembled 0.132 proves every receiver CSN HIGH 32/32 while MISO returns LOW 0/32 with zero bus/TX activity | `spi_radio` is exclusive; board-02 carrier RF remains `fault`; no cross-swap or emission; no single module or antenna/U.FL fault is claimed | return/replace the carrier/device or physically isolate module MISO/power one at a time; require repaired plausible identities before bounded regression |
| HW-U08 | electrical/ADC behavior is unmeasured; the false-sound software root cause is confirmed by 0.x and upstream issue #117 | battery percentage is unavailable; GPIO2 is never ADC-sampled and is held OUTPUT LOW from the first setup instruction; HIGH belongs only to a future bounded sound service | HW-T09 for ADC/sound characterization; silent invariant closes through boot/runtime state plus audible observation |
| HW-U09 | partial: exact 0.129 proves one bounded physical NEC receive/save/cold-export path; GPIO21 remains exclusive with nRF #3 | IR RX is available only from the explicit RF-shield profile; no autodetect; product IR TX additionally requires Lab/ADR-002 evidence | broaden protocol vectors and instrument GPIO21 switching under HW-T08 |
| HW-U10 | no rail peak/thermal measurement | first slice is Wi-Fi-only; shield operations are one receiver at a time after per-module HIL; combined modes unavailable | HW-T10 and RB-08 endurance |

## Architecture consequences

- This document is design-time pin/resource truth; `BoardProfile` references its
  revision and does not contain untraceable “verified” claims.
- HardwareProbe returns state plus evidence, not a capability bitmask alone.
- GPS and PN532 require explicit assembly profiles; autodetect may not trial contested
  outputs.
- ResourceBroker adds `spi_display`, `spi_radio`, `mux_5_6`, `mux_nrf3_ir`,
  `gpio2_battery_buzzer`, `i2c_control`, `storage`, and `esp_rf`.
- BoardSafeOutputs establishes GPIO2 plus nRF CE GPIO14/15/47 OUTPUT LOW before
  console/display. The panic Task-WDT ISR reasserts those levels with direct GPIO
  registers, while static checks prevent apps/drivers from bypassing the safe path.
- 1.x has no OPI-PSRAM dependency until `HW-U01` proves a compatible variant that
  does not collide with the display pins.
- Passive Wi-Fi remains the provisional first Survey source because it bypasses all
  external mux conflicts while validating the Session pipeline.
