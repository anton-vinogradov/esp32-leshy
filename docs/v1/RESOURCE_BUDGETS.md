# ESP32-Leshy 1.x — resource budget ledger

*Read in: **English** · [Русский](RESOURCE_BUDGETS.ru.md)*

Document status: **S1 draft — bootstrap, probe UI, and one guarded FAT persistence
run are measured; product boot, storage endurance, power, and shared-bus measurements
remain open**.

This ledger prevents measurements, planning limits, and legacy numbers from being
treated as the same thing. It is the budget source of truth until an accepted ADR
defines the 1.x partition and memory policy.

## Evidence classes

- `measured` — reproduced from a named build or physical HIL record;
- `reference` — useful comparison that is not a 1.x budget;
- `guardrail` — a provisional limit that new work must respect or explicitly review;
- `unknown` — no defensible measurement exists yet.

## Current measurements

| ID | Class | Quantity | Result | Scope and evidence |
|---|---|---|---|---|
| RB-M01 | measured | physical flash / PSRAM | 16,777,216 B Quad flash; PSRAM absent | board-01 probe 0.1.1, `E-HIL-001` |
| RB-M02 | measured | current app/storage slots | app0/app1 3,342,336 B each; filesystem 1,572,864 B | board-01 partition inventory; current probe layout, not accepted 1.x layout |
| RB-M03 | measured | HIL probe build | 354,548 B linked flash, 23,872 B static RAM; app image 354,960 B; factory image 420,496 B | probe 0.1.1, `E-BUILD-002`; evidence tool only |
| RB-M04 | measured | HIL probe runtime heap | total 387,360 B; free 347,224 B; minimum observed 342,040 B | board-01 native-USB inventory after boot |
| RB-R01 | reference | 0.x + feasibility prototype build | 1,995,896 B linked flash; 98,748 B static RAM | `E-BUILD-001`; neither a clean target nor an upper product budget |
| RB-M05 | measured | physical flash path | 80 MHz; full 16 MiB backup/restore hash-verified; native upload 460800, CP2102 reliable at 230400 | `E-HIL-004` |
| RB-M06 | measured | independent clean target build | 320,952 B linked flash; 22,576 B static RAM; app image 321,360 B; factory image 386,896 B | pinned toolchain, no dependencies/legacy sources, `E-BUILD-003` |
| RB-M07 | measured | clean target runtime | heap total 389,680 B; free 349,660 B; minimum observed 344,512 B; runtime-ready milestone 7,224 µs | board-01 native USB, `E-HIL-006`; no display/input/source/storage |
| RB-M08 | measured | first interactive target | 391,719 B linked flash; 24,460 B static RAM; app/factory images 392,128/457,664 B; interactive-ready 362,960 µs; heap total/free/min 386,256/343,420/338,272 B | board-01 `0.2.0-interactive-measure`, `E-BUILD-004`/`E-HIL-007`; display + read-only input, no storage/source |
| RB-M09 | measured | automated UI target | 394,843 B linked flash; 26,388 B static RAM; app/factory images 395,248/460,784 B; interactive-ready 368,941 µs; heap total/free/min 384,328/341,492/336,344 B | board-01 `0.3.0-ui-automation-measure`, `E-BUILD-005`/`E-HIL-008`; actual TFT capture + probe Navigator, no storage/source |
| RB-M10 | measured | storage-contract target | 395,115 B linked flash; 26,388 B static RAM; app/factory images 395,520/461,056 B; interactive-ready 368,949 µs; heap total/free/min 384,328/341,492/336,344 B | board-01 `0.4.0-storage-contract-measure`, `E-BUILD-006`/`E-HIL-009`; host atomicity + read-only contract report, filesystem not mounted |
| RB-M11 | measured | storage-guard target | 395,627 B linked flash; 26,388 B static RAM; app/factory images 396,032/461,568 B; interactive-ready 368,955 µs; heap total/free/min 384,328/341,492/336,344 B | board-01 `0.5.0-storage-guard-measure`, `E-BUILD-007`/`E-HIL-010`; fail-closed write permit + read-only guard report, filesystem not mounted |
| RB-M12 | measured | capability-home target | 396,243 B linked flash; 26,436 B static RAM; app/factory images 396,640/462,176 B; interactive-ready 373,119 µs; heap total/free/min 384,280/341,444/336,296 B | board-01 `0.6.0-capability-home-measure`, `E-BUILD-008`/`E-HIL-011`; capability projection + disabled reasons + Diagnostics launch/Back |
| RB-M13 | measured | runtime-lease target | 396,887 B linked flash; 26,468 B static RAM; app/factory images 397,296/462,832 B; interactive-ready 373,130 µs; heap total/free/min 384,248/341,412/336,264 B | board-01 `0.7.0-runtime-leases-measure`, `E-BUILD-009`/`E-HIL-012`; 1,000 Diagnostics open/Back cycles, zero leaked leases or heap change; Back/release p99/max 98.801/99.345 ms |
| RB-M14 | measured | Survey-contract target | 397,571 B linked flash; 26,468 B static RAM; app/factory images 397,968/463,504 B; interactive-ready 373,112 µs; heap total/free/min 384,248/341,412/336,264 B | board-01 `0.8.0-survey-contract-measure`, `E-BUILD-010`/`E-HIL-013`; bounded model/passive ingress/golden controller, radio untouched |
| RB-M15 | measured | golden Survey UI target | 405,223 B linked flash; 31,156 B static RAM; app/factory images 405,632/471,168 B; interactive-ready 372,519 µs; heap total/free/min 379,560/336,724/331,576 B | board-01 `0.9.0-survey-golden-ui-measure`, `E-BUILD-011`/`E-HIL-014`; 64-slot in-memory Session + rendered three-record workflow, RF off |
| RB-M16 | measured | Session-codec target | 416,175 B linked flash; 48,628 B static RAM; app/factory images 416,576/482,112 B; interactive-ready 372,497 µs; heap total/free/min 362,088/319,252/314,104 B | board-01 `0.10.0-session-codec-measure`, `E-BUILD-012`/`E-HIL-015`; bounded 12,288 B segment + manifest/reopen workspace, three-record round-trip, no storage/RF |
| RB-M17 | measured | bounded SessionStore target | 458,847 B linked flash; 74,148 B static RAM; app/factory images 459,248/524,784 B; interactive-ready 372,545 µs; heap total/free/min 336,568/293,732/288,584 B | board-01 `0.11.0-session-store-measure`, `E-BUILD-013`/`E-HIL-016`; two maximum-size RAM generations, auto-publish/reopen/corrupt-new fallback, no persistent storage/RF |
| RB-M18 | measured | offline Library target | 465,563 B linked flash; 79,132 B static RAM; app/factory images 465,968/531,504 B; interactive-ready 393,829 µs; heap total/free/min 331,584/288,748/283,600 B | board-01 `0.12.0-library-offline-measure`, `E-BUILD-014`/`E-HIL-017`; bounded List/Detail over one reopened RAM Session, UI lease only, volatile/RF-off provenance |
| RB-M19 | measured | bounded Library-export target | 467,247 B linked flash; 79,772 B static RAM; app/factory images 467,648/533,184 B; interactive-ready 393,850 µs; heap total/free/min 330,944/288,108/282,960 B | board-01 `0.13.0-library-export-measure`, `E-BUILD-015`/`E-HIL-018`; explicit Export Ready + deterministic serial NDJSON, no file/media write |
| RB-M20 | measured | read-only storage-discovery target | 469,199 B linked flash; 80,588 B static RAM; app/factory images 469,600/535,136 B; interactive-ready 393,904 µs; heap total/free/min 330,128/287,292/282,144 B | board-01 `0.14.0-storage-discovery-measure`, `E-BUILD-016`/`E-HIL-019`; GPIO38 sampled non-authoritatively, no mount/write |
| RB-M21 | measured | mount-policy target | 470,215 B linked flash; 80,588 B static RAM; app/factory images 470,624/536,160 B; interactive-ready 393,889 µs; heap total/free/min 330,128/287,292/282,144 B | board-01 `0.15.0-mount-policy-measure`, `E-BUILD-017`/`E-HIL-020`; SDFS refused for no RO guarantee; no SD/SPI execution |
| RB-M22 | measured | SD RO protocol-plan target | 471,099 B linked flash; 81,100 B static RAM; app/factory images 471,504/537,040 B; interactive-ready 393,887 µs; heap total/free/min 329,616/286,780/281,632 B | board-01 `0.16.0-sd-ro-protocol-measure`, `E-BUILD-018`/`E-HIL-021`; fixed identification-only commands, execution disabled |
| RB-M23 | measured | SD transcript-parser target | 472,987 B linked flash; 81,804 B static RAM; app/factory images 473,392/538,928 B; interactive-ready 393,906 µs; heap total/free/min 328,912/286,076/280,928 B | board-01 `0.17.0-sd-parser-measure`, `E-BUILD-019`/`E-HIL-022`; synthetic transcript, physical SPI disabled |
| RB-M24 | measured | fake SD transport target | 474,959 B linked flash; 82,316 B static RAM; app/factory images 475,360/540,896 B; interactive-ready 393,888 µs; heap total/free/min 328,400/285,564/280,416 B | board-01 `0.18.0-sd-transport-measure`, `E-BUILD-020`/`E-HIL-023`; 11 fake exchanges, physical transports rejected |
| RB-M25 | measured | SD SPI wire-codec target | 476,051 B linked flash; 82,828 B static RAM; app/factory images 476,448/541,984 B; interactive-ready 393,870 µs; heap total/free/min 327,888/285,052/279,904 B | board-01 `0.19.0-sd-wire-measure`, `E-BUILD-021`/`E-HIL-024`; bounded byte framing only, execution disabled |
| RB-M26 | measured | physical SD identification target | 479,659 B linked flash; 84,300 B static RAM; app/factory images 480,064/545,600 B; interactive-ready 393,896 µs; heap total/free/min 326,416/283,944/278,668 B | board-01 `0.20.0-sd-physical-id-measure`, `E-BUILD-022`/`E-HIL-025`; three stable guarded 400 kHz identity runs, no mount/write |
| RB-M27 | measured | physical SD LBA0 target | 483,319 B linked flash; 86,764 B static RAM; app/factory images 483,728/549,264 B; interactive-ready 393,909 µs; heap total/free/min 323,952/281,480/276,204 B | board-01 `0.21.0-sd-sector0-measure`, `E-BUILD-023`/`E-HIL-026`; one guarded CMD17, MBR metadata/fingerprint only, no mount/write |
| RB-M28 | measured | physical FAT32 boot-sector target | 487,071 B linked flash; 90,340 B static RAM; app/factory images 487,472/553,008 B; interactive-ready 393,881 µs; heap total/free/min 320,376/277,904/272,628 B | board-01 `0.22.0-sd-boot-inspect-measure`, `E-BUILD-024`/`E-HIL-027`; two guarded metadata blocks confirm FAT32 geometry, no mount/directory/file/write |
| RB-M29 | measured | metadata-only FAT32 root-sector target | 492,119 B linked flash; 95,620 B static RAM; app/factory images 492,528/558,064 B; interactive-ready 393,903 µs; heap total/free/min 315,096/272,516/267,208 B | board-01 `0.23.0-sd-root-metadata-measure`, `E-BUILD-025`/`E-HIL-028`; one derived directory sector, counts/CRC only, names omitted and buffer zeroed |
| RB-M30 | measured | metadata-only FAT32 root-cluster target | 492,743 B linked flash; 95,620 B static RAM; app/factory images 493,152/558,688 B; interactive-ready 393,904 µs; heap total/free/min 315,096/272,516/267,208 B | board-01 `0.24.0-sd-root-cluster-measure`, `E-BUILD-026`/`E-HIL-029`; end marker after two bounded sectors, complete root metadata counts, no names/file data/mount/write |
| RB-M31 | measured | FAT32 FSInfo target + shared SD workspace | 493,799 B linked flash; 90,004 B static RAM; app/factory images 494,208/559,744 B; interactive-ready 393,919 µs; heap total/free/min 320,712/278,132/272,824 B | board-01 `0.25.0-sd-fsinfo-measure`, `E-BUILD-027`/`E-HIL-030`; technical free/next hints only, no FAT/name/file/mount/write; shared workspace recovers 5,616 B static RAM vs 0.24 |
| RB-M32 | measured | FAT32 reserved/root-entry cross-check | 500,007 B linked flash; 90,004 B static RAM; app/factory images 500,416/565,952 B; interactive-ready 393,901 µs; heap total/free/min 320,712/278,240/272,964 B | board-01 `0.27.0-sd-fat-reserved-measure`, `E-BUILD-029`/`E-HIL-032`; +6,208 B linked flash vs 0.25 with no static-RAM growth; exactly FAT[0…2], no chain/name/file/mount/write |
| RB-M33 | measured | guarded physical FAT SessionStore | 572,655 B linked flash; 94,996 B static RAM; app/factory images 573,056/638,592 B; interactive-ready 391,564 µs; heap total/free/min 315,720/272,648/237,716 B | board-01 `0.28.0-sd-session-store-measure`, `E-BUILD-030`/`E-HIL-033`; FAT mount plus two real generations, unmount/remount/read-only reopen; 440 logical B written inside a 64 KiB guard; retry writes 0 B |
| RB-M34 | measured | ESP-IDF SDSPI SessionStore throughput | 615,159 B linked flash; 99,932 B static RAM; app/factory images 615,568/681,104 B; interactive-ready 391,482 µs; heap total/free/min 309,504/266,460/233,464 B | board-01 `0.29.0-sd-session-throughput-measure`, `E-BUILD-031`/`E-HIL-034`; 32 commits at actual 4 MHz, p50/p95/p99 405,729/571,276/591,651 µs, generation 32 survives remount; 7,040 logical B and 2,195,456 B physical delta inside 4 MiB guard; retry writes 0 B |
| RB-M35 | measured | software-reset harness and physical matrix | 626,155 B linked flash; 99,932 B static RAM; app/factory images 626,560/692,096 B; interactive-ready 391,524 µs; heap total/free/min 309,504/266,676/233,656 B | board-01 `0.30.0-sd-session-reset-measure`, `E-BUILD-032`/`E-HIL-035`; +10,996 B linked flash and zero static-RAM delta vs 0.29; six boundaries recover 1/1/1/1/1/2 with unchanged prior hashes and zero recovery writes; boundary 4 required one fail-closed read-only readiness retry |
| RB-M36 | measured | shared SessionStore validation/recovery workspace | 621,479 B linked flash; 95,260 B static RAM; app/factory images 621,888/687,424 B; interactive-ready 391,554 µs; heap total/free/min after boundary-6 HIL 314,176/271,348/238,460 B | board-01 `0.31.0-sd-session-ram-review`, `E-BUILD-033`/`E-HIL-036`; one redundant 4,672 B `SurveySession` removed, restoring 3,044 B headroom below RB-03; guarded boundary 6 recovers generation 2 with unchanged prior hashes and zero recovery writes |
| RB-M37 | measured | passive Wi-Fi source ingress | 1,016,688 B linked flash; 113,600 B static RAM; app/factory images 1,017,088/1,082,624 B; interactive-ready 391,729 µs; heap total/free/min after 32 scans 288,160/244,664/186,376 B | board-01 `0.32.0-wifi-passive-ingress-measure`, `E-BUILD-034`/`E-HIL-037`; 32/32 passive scans accept 414 observations with zero drop/reject; p50/p95/p99 370/504/546 encoded B/s; RB-06 requires 2,184 B/s, while current fsync-per-generation SD workload provides 536 B/s |
| RB-M38 | measured | fixed queue + batched SD service rate | 1,018,192 B linked flash; 114,200 B static RAM; app/factory images 1,018,592/1,084,128 B; interactive-ready 393,709 µs; heap total/free/min after HIL 287,560/244,324/211,328 B | board-01 `0.33.0-sd-session-batch-throughput-measure`, `E-BUILD-035`/`E-HIL-038`; fixed FIFO/policy add 600 B static RAM; 32×64-observation commits deliver 9,068 encoded B/s and pass the 2,184 B/s requirement by 4.15x; real-source integration remains open |
| RB-M39 | measured | real passive Wi-Fi→FIFO→persistent SessionStore | 1,027,804 B linked flash; 119,656 B static RAM; app/factory images 1,028,208/1,093,744 B; interactive-ready 393,741 µs; heap total/free/min after HIL 282,104/238,028/149,308 B | board-01 `0.34.0-wifi-passive-persist-measure`, `E-BUILD-036`/`E-HIL-039`; the 64-entry ring uses 4,672 B; 29 real observations, high-water 9, zero drops, latency batch, remount reopen; 6,921 encoded B/s passes RB-06 by 3.17x |
| RB-M40 | measured | current-boot persistent Library admission/export | 1,029,116 B linked flash; 120,264 B static RAM; app/factory images 1,029,520/1,095,056 B; interactive-ready 393,726 µs; heap total/free/min after HIL 281,496/237,420/147,692 B | board-01 `0.35.0-persistent-library-admission-measure`, `E-BUILD-037`/`E-HIL-040`; 52 real observations, high-water 18/64, zero drops, size batch, remount reopen; 12,957 encoded B/s passes RB-06 by 5.93x; ordinary Library List/Detail/Export uses persistent/real provenance and releases lease 5→0 |
| RB-M41 | measured | pre-release firmware build identity | 1,029,312 B linked flash; 120,328 B static RAM; app/factory images 1,029,712/1,095,248 B; interactive-ready 393,728 µs; heap total/free/min after device-smoke 281,432/238,768/233,372 B | board-01 `0.36.0-prerelease-build-identity-measure`, `E-BUILD-038`/`E-HIL-042`; +196 B linked flash/+64 B static RAM, full ELF SHA-256 agrees across candidate/cold boot/metrics; Home/Diagnostics/Back retain zero visual mismatch |
| RB-M42 | measured | pre-release HIL session envelope | 1,030,684 B linked flash; 120,368 B static RAM; app/factory images 1,031,088/1,096,624 B; interactive-ready 393,722 µs; heap total/free/min after device-smoke 281,392/238,728/233,332 B | board-01 `0.37.0-prerelease-test-session-measure`, `E-BUILD-039`/`E-HIL-043`; +1,372 B linked flash/+40 B static RAM; begin/end state binds the 128-bit run ID and app identity without a hardware lease; all three TFT comparisons retain zero mismatch |

The probe's `heap_min_free` covers only its short diagnostic run. It does not predict
Wi-Fi/BLE buffers, display caches, Session queues, storage transactions, or an
eight-hour Survey. The 0.x figure includes legacy functionality and feasibility
contracts, so it cannot define the clean platform shape.

## Provisional 1.x guardrails

These limits are review triggers, not evidence that the product meets its NFRs.

| ID | Guardrail | Rationale / closure |
|---|---|---|
| RB-01 | No required path may depend on PSRAM | board-01 and BOM identify the N16/no-PSRAM envelope; only new HW-T01 evidence may expand it |
| RB-02 | Keep two bootable app slots and at least 12.5% free space in either selected slot | preserves OTA/rollback and growth; final values require the partition ADR |
| RB-03 | Clean S2 platform: static RAM ≤ 96 KiB and free internal heap ≥ 240 KiB after interactive boot | leaves room for the first radio/storage slice; measure on the independent target |
| RB-04 | S3 passive Survey steady state: free internal heap ≥ 160 KiB and minimum ≥ 128 KiB with no downward trend over 8 h | reserves bounded worker/parse/export headroom; close with heap time series and queue high-water marks |
| RB-05 | Interactive UI ≤ 2 s after cold boot; UI callbacks ≤ 10 ms; Back/lease release ≤ 150 ms | existing NFR-001…003; close with device timestamps and external HIL timing |
| RB-06 | Sustained storage throughput ≥ 4× measured p99 ingress of the selected source set; commit/power-cut must preserve all prior committed records | avoids an arbitrary SD-only number; measure source rate, SD and LittleFS separately |
| RB-07 | A 10,000-transition radio→storage→radio test has zero bus errors, all non-owner CS lines inactive, and zero leaked leases | closes transaction policy only with HW-T03/HW-T05 trace evidence |
| RB-08 | No unmeasured receiver combination is enabled by default; accepted combinations must complete endurance without brownout/reset and stay inside measured regulator/thermal limits | power numbers require HW-T10; unavailable equipment narrows scope rather than inventing capacity |

## Measurement closure matrix

| Area | Current state | Next reproducible measurement | Gate impact |
|---|---|---|---|
| Flash/static RAM | platform/runtime, Survey UI, codec, SessionStore, persistent Library/export, SD metadata, guarded FAT persistence, SD throughput, software-reset matrix, and Wi-Fi source slice measured; shared recovery workspace restores 3,044 B below RB-03; LittleFS slice remains open | implement product workers and a separately disposable LittleFS adapter; archive size/map deltas against RB-02/03/04 | S1 lower bound, S2/S3 gate |
| Runtime heap/queues | lease lifecycle measured over 1,000 UI cycles; the fixed 64-entry FIFO passed the real Wi-Fi→SD→Library path with high-water 18 and zero drops; short-run minimum 147,692 B is above the RB-04 floor | separate concurrent receiver/storage workers, then capture steady/min heap, queue high-water, and an 8 h trend | S1 lower bound, S3/S4 endurance |
| Boot/UI latency | capability-built home interactive-ready 0.373 s and TFT capture measured | measure external cold power-on and later product services, not only device milestone | blocks final NFR-001 verification, not S2 bootstrap |
| Storage throughput/atomicity | bounded SessionStore matrices, guarded FAT/remount/reset evidence, and passive Wi-Fi ingress are measured; the real FIFO/batch path delivers 12,957 encoded B/s against required 2,184 B/s and reopens after remount | move the path into product workers/Stop, verify boot catalog and readiness retry on a natural transient, then separately measure LittleFS/power-cut/endurance | blocks full verification of PR-005 and RB-06 |
| Shared bus | identity reads only | 10,000 transition loop with logic trace, error counters, and post-test identities | blocks RB-07 and coexistence ADR acceptance |
| Power/thermal | unknown, no instrument available | idle/backlight/SD/each passive receiver/combined rail min-avg-peak and temperature | limits combinations under RB-08; does not block Wi-Fi-first platform work |

## Decisions enabled now

- The clean 1.x target must be configured for no PSRAM and must report a profile
  mismatch as a fault.
- Passive Wi-Fi remains the first Survey-source candidate because it exercises the
  end-to-end workflow without relying on unresolved shield buses or external
  assemblies.
- HIL probe and 0.x numbers bracket current evidence but neither is a target budget.
- The automated probe UI passes RB-03 with 26,388 B static RAM and 341,492 B free
  heap; storage/runtime and Survey must preserve the guardrail through measured deltas.
- The first runtime lease path passes RB-05 for Back/release acknowledgement over
  1,000 cycles and returns to the exact pre-run free/minimum heap values.
- The bounded Session-codec target remains inside RB-03/RB-04 with 48,628 B static
  RAM and 319,252 B free heap; its 17,472 B delta is fixed self-check workspace, not
  evidence of filesystem transaction cost or endurance.
- The two-generation RAM SessionStore target remains inside RB-03/RB-04 at 74,148 B
  static RAM and 293,732 B free heap. Its extra 25,520 B deliberately retains a second
  maximum-size diagnostic generation; a physical adapter must measure its own cache.
- The offline Library target remains inside RB-03/RB-04 at 79,132 B static RAM and
  288,748 B free heap. Its 4,984 B static-RAM delta adds the bounded controller and
  caller-owned reopen result; the first stack-copy implementation was rejected.
- The bounded export target remains inside RB-03/RB-04 at 79,772 B static RAM and
  288,108 B free heap. Its 640 B delta is the static serial artifact buffer; no
  filesystem cache or persistence cost is represented.
- The read-only discovery target remains inside RB-03/RB-04 at 80,588 B static RAM
  and 287,292 B free heap. Its 816 B delta covers the record/formatter and board
  adapter; no SD driver, filesystem cache, or persistence cost is represented.
- Mount policy adds 1,016 B linked flash and no static-RAM/heap delta. The unchanged
  memory confirms that no SD driver or filesystem cache was started.
- The RO protocol plan adds 884 B linked flash and 512 B static RAM for its report;
  it still starts no SPI/SD driver or filesystem cache.
- The guarded FAT SessionStore remains just inside RB-03 at 94,996 B static RAM and
  272,648 B free heap after boot. Its 72,648 B linked-flash and 4,992 B static-RAM
  deltas over 0.27 include SDFS/FatFs plus the physical adapter; the 237,716 B observed
  minimum during the short postflight is below the RB-03 free-heap guardrail and must
  be reviewed before S2, not treated as an endurance result.
- The 0.29/0.30 ESP-IDF SDSPI images used 99,932 B static RAM, 1,628 B above the
  temporary RB-03 ceiling. Map review found a redundant 4,672 B physical-recovery
  `SurveySession`; 0.31 reuses the existing caller-owned validation session and drops
  to 95,260 B, 3,044 B below RB-03. A guarded boundary-6 reset/recovery passes on the
  shared workspace. The FatFs workspace remains caller-owned rather than hidden on
  the loop stack.
- Linking the first passive Wi-Fi source with the storage measurement image adds
  18,340 B static RAM and 395,209 B linked flash. Version 0.32 is an S3 source slice,
  not the clean S2 platform: it exceeds RB-03 but keeps post-run minimum heap at
  186,376 B, above RB-04's 128 KiB floor. The 32-scan p99 ingress requires 2,184 B/s
  under RB-06, exposing the need for bounded batching rather than per-scan sync.
- The fixed queue/policy adds 600 B static RAM to the combined source/storage image.
  Synthetic 64-observation batching delivers 9,068 encoded B/s and closes RB-06
  with 4.15x margin; this is service-rate evidence, not a substitute for real
  Wi-Fi→queue→SD HIL.
- The real fixed ring in 0.34 adds 4,672 B static RAM; postflight minimum heap of
  149,308 B remains above the 128 KiB RB-04 floor but leaves only 18,236 B headroom.
  Product UI/background workers require map/heap review and no duplicate full Session
  buffers.
- Current-boot persistent Library admission/export in 0.35 adds 608 B static RAM
  and 1,312 B linked flash. Minimum heap 147,692 B remains 16,620 B above the RB-04
  floor; the entry reuses caller-owned `librarySession`, while boot catalog and
  concurrent workers require a separate map/8 h review.
- Storage, power, and shared-bus limits remain explicit unknowns; features depending
  on them cannot be promoted from `unknown` to `available` by documentation alone.
