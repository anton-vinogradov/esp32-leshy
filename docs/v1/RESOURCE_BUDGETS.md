# ESP32-Leshy 1.x — resource budget ledger

*Read in: **English** · [Русский](RESOURCE_BUDGETS.ru.md)*

Document status: **accepted S1 baseline, active S5 — product build/heap/storage,
cross-radio release endurance and controlled power-cut are measured; externally
instrumented shared-bus/power measurements remain open**.

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
| RB-M43 | measured | product Survey workflow plus extended pre-release HIL | 1,033,560 B linked flash; 120,400 B static RAM; app/factory images 1,033,968/1,099,504 B; interactive-ready 393,720 µs; heap total/free/min after the full workflow 281,360/238,696/233,300 B | board-01 `0.38.0-product-survey-workflow-measure`, `E-BUILD-040`/`E-HIL-046`; +2,876 B linked flash/+32 B static RAM; Setup→Running→Stop & Commit→Library→export with ten zero-mismatch TFT comparisons and simulated/RAM/RF-off provenance |
| RB-M44 | measured | product source→FIFO pipeline plus visible progress | 1,035,232 B linked flash; 120,488 B static RAM; app/factory images 1,035,632/1,101,168 B; interactive-ready 393,815 µs; heap total/free/min after the workflow 281,272/238,608/233,212 B | board-01 `0.39.0-product-survey-pipeline-measure`, `E-BUILD-041`/`E-HIL-047`; +1,672 B linked flash/+88 B static RAM; existing ring 64 is reused, pipeline reports 3 received/3 forwarded/high-water 3/drop 0 and Stop trigger, with ten visual mismatches 0 |
| RB-M45 | measured | fail-closed product source/store admission | 1,037,472 B linked flash; 120,488 B static RAM; app/factory images 1,037,872/1,103,408 B; interactive-ready 393,836 µs; heap total/free/min after the workflow 281,272/238,608/233,212 B | board-01 `0.40.0-product-admission-policy-measure`, `E-BUILD-042`/`E-HIL-048`; +2,240 B linked flash/zero static-RAM delta; exact product root/read-only recovery/explicit bounded write/combined lease policy, revision-4 query, and ten visual mismatches 0 without hardware I/O |
| RB-M46 | measured | background physical-keypad frontend | 1,039,304 B linked flash; 120,576 B static RAM; app/factory images 1,039,712/1,105,248 B; interactive-ready 394,001 µs; heap total/free/min after the workflow 281,184/233,556/228,160 B | board-01 `0.41.0-keypad-frontend-measure`, `E-BUILD-043`/`E-HIL-049`; +1,832 B linked flash/+88 B static RAM, plus 5,052 B measured heap cost for the dedicated task/16-entry queue; maximum physical sample gap remains 5 ms during the full HIL run |
| RB-M47 | measured | press-only/batched keypad attempt | 1,039,480 B linked flash; 120,584 B static RAM; app/factory images 1,039,888/1,105,424 B; interactive-ready 393,977 µs; heap total/free/min after the workflow 281,176/233,548/228,152 B | board-01 `0.42.0-keypad-burst-measure`, `E-BUILD-044`/`E-HIL-051`; +176 B linked flash/+8 B static RAM vs 0.41; automatic HIL passed but the physical burst overflowed the 16-entry press queue |
| RB-M48 | measured | accepted lossless keypad burst buffer | 1,039,504 B linked flash; 120,584 B static RAM; app/factory images 1,039,904/1,105,440 B; interactive-ready 393,998 µs; heap total/free/min after the workflow 281,176/233,140/227,744 B | board-01 `0.43.0-keypad-burst-buffer-measure`, `E-BUILD-045`/`E-HIL-052`; +24 B linked flash/zero static RAM and 408 B measured free/min-heap cost vs 0.42 for queue 64; physical high-water 6/64, 50/50 dispatched, zero drops, sample gap 5 ms |
| RB-M49 | measured | read-only product SD boot recovery | 1,053,188 B linked flash; 120,696 B static RAM; app image 1,053,600 B; generic interactive-ready 394,166 µs and heap total/free/min 281,064/232,984/227,516 B; enrolled cold-boot interactive-ready 564,144 µs and heap total/free/min 281,064/232,628/199,708 B | board-01 `0.44.0-sd-readonly-driver-measure`, `E-BUILD-046`/`E-HIL-053`; +13,684 B linked flash/+112 B static RAM vs 0.43; exact-CID read-only boot admits generation 1/17 observations with lease 12→0, zero write-blocker hits and zero SD write calls; no O(media-size) FAT free-space scan |
| RB-M50 | measured | interactive real passive product Survey + automatic product HIL | 1,059,264 B linked flash; 125,448 B static RAM; app image 1,059,664 B; enrolled cold-boot interactive-ready 592,104/598,613 µs before/after commit; heap total/free/min 276,312/227,876/194,956 B | board-01 `0.45.0-product-survey-measure`, `E-BUILD-047`/`E-HIL-054`; +6,076 B linked flash/+4,752 B static RAM vs 0.44; lease 15 passive scan accepts/forwards 15/15, generation 2→3, read-only reboot/export match and final lease 0; cached FSInfo proves space without full FAT scan |
| RB-M51 | measured | bounded boot retry + endurance-runner smoke | 1,060,116 B linked flash; 125,448 B static RAM; app/factory images 1,060,528/1,126,064 B; six enrolled boot markers 750.446…761.734 ms; heap total/free/min 276,312/227,876/194,956 B with zero drift | board-01 `0.46.0-product-boot-retry-measure`, `E-BUILD-048`/`E-HIL-059`; +852 B linked flash/zero static-RAM delta vs 0.45; three-cycle smoke advances 12→15 with 51/51 forwarded and no drops, but all boots use attempt 1 and the result did not meet the then-current 8 h gate |
| RB-M52 | measured | Product Start raw-identity retry | 1,060,632 B linked flash; 125,448 B static RAM; app/factory images 1,061,040/1,126,576 B | board-01 `0.47.0-product-start-retry-measure`, `E-BUILD-049`/`E-HIL-060/061`; +516 B linked/app and zero static-RAM delta vs 0.46; two normal cycles pass, while the third exposes an unbounded lower boot-recovery call |
| RB-M53 | measured | app-bound boot budget + lock-free recovery watchdog | 1,061,848 B linked flash; 125,456 B static RAM; app/factory images 1,062,256/1,127,792 B; RTC no-init 20 B; heap total/free/min 276,304/227,864/192,432 B; normal ready 812.973…820.884 ms and retry ready 2,660.702 ms | board-01 `0.48.0-product-boot-timeout-measure`, `E-BUILD-050`/`E-HIL-062…064`; +1,216 B linked/app and +8 B static RAM vs 0.47; injected timeout restarts without SD writes, then three cycles advance 27→30 with 45/45 forwarded, zero drops, and zero heap drift; did not meet the then-current 8 h gate |
| RB-M54 | measured | lower-clock Product Start resilience | 1,061,852 B linked flash; 125,456 B static RAM; app/factory images 1,062,256/1,127,792 B; RTC no-init 20 B; heap total/free/min 276,304/227,864/192,432 B; normal ready 855.468…864.535 ms and retry ready 1,658.062 ms | board-01 `0.49.0-product-start-resilience-measure`, `E-BUILD-051`/`E-HIL-065…068`; +4 B linked flash/zero static-RAM or image delta vs 0.48; 100 kHz improves isolated valid raw identities from 13/32 to 24/32 and the three-cycle exact regression advances 35→38 with 46/46 forwarded, zero drops and zero heap drift; did not meet the then-current 8 h gate |
| RB-M55 | measured | aligned Product Start/boot resilience budget | 1,061,852 B linked flash; 125,456 B static RAM; app/factory images 1,062,256/1,127,792 B; RTC no-init 20 B; heap total/free/min 276,304/227,864/192,432 B; normal ready 888.082…897.937 ms and retry ready 1,703.735 ms | board-01 `0.50.0-product-boot-resilience-measure`, `E-BUILD-052`/`E-HIL-069…071`; zero build/resource delta vs 0.49; boot attempts increase 3→8 after a natural three-attempt gate failure and a measured maximum raw failure streak of four; three-cycle regression advances 44→47 with 39/39 forwarded, zero drops and zero heap drift; did not meet the then-current 8 h gate |
| RB-M56 | measured | hardware-backed timeout recovery + shortened endurance | 1,062,900 B linked flash; 125,464 B static RAM; app/factory images 1,063,312/1,128,848 B; RTC no-init 20 B; 4,000 ms software tier plus 5,000 ms panic-enabled Task WDT tier; runtime heap total/free/min 276,040/227,588/192,128 B; injected timeout ready 6,697.964 ms, normal maximum ready 961.019 ms | `0.51.0-hardware-boot-watchdog-measure`, `E-HIL-072…075`/`E-AUTO-019/020`/`E-BUILD-053`; physical Task WDT recovery and 12 consecutive product cycles over 11,330.816 s advance 51→63 with 144/144 forwarded, 24 cold boots, zero drops/retries/heap drift, and final lease 0; shortened checkpoint is not a release gate |
| RB-M57 | measured | semantic visual system + exact product regression | 1,063,092 B linked flash; 125,464 B static RAM; app/factory images 1,063,248/1,128,784 B; RTC no-init 20 B; runtime heap total/free/min 276,040/227,588/192,128 B | board-01 `0.52.0-visual-system-measure`, `E-BUILD-054`/`E-HIL-076`/`E-UX-003`; +192 B linked flash, zero static-RAM growth, and 64 B smaller app/factory images vs 0.51; exact run advances 64→65 with 9/9 forwarded, zero drops, six retained TFT frames, and final lease 0; this accepts UX-03, not the S2 or release gate |
| RB-M58 | measured | on-device Self-Test Quick + shared report workspace | 1,067,800 B linked flash; 128,720 B static RAM; app/factory images 1,068,208/1,133,744 B; RTC no-init 20 B; runtime heap total/free/min 272,784/224,332/188,872 B | board-01 `0.53.0-self-test-quick-measure`, `E-BUILD-055`/`E-HIL-077`/`E-AUTO-021`; +4,708 B linked flash, +3,256 B static RAM, and +4,960 B images vs 0.52. Quick passes 8/8 in 60 µs with zero side effects/final lease; Full remains blocked on incomplete coverage. One shared static 3 KiB JSON workspace replaces the rejected loop-stack buffer |
| RB-M59 | measured | shared UI component geometry + renderer primitives | 1,068,048 B linked flash; 128,720 B static RAM; app/factory images 1,068,192/1,133,728 B; RTC no-init 20 B; runtime heap total/free/min 272,784/224,332/188,872 B | board-01 `0.54.0-ui-components-measure`, `E-BUILD-056`/`E-HIL-078`/`E-UX-004`; +248 B linked flash, zero static-RAM growth, and 16 B smaller images vs 0.53. Four retained TFT frames prove shared Home/Self-Test components; Quick remains 8/8 and final lease 0 |
| RB-M60 | measured | complete EN/RU catalog + generated PT Sans Narrow GFX fonts + persistent Language controller | 1,104,448 B linked flash; 128,744 B static RAM; app/factory images 1,104,592/1,170,128 B; RTC no-init 20 B; runtime heap total/free/min 272,760/224,280/188,792 B | board-01 `0.55.0-ui-language-measure`, `E-BUILD-057`/`E-HIL-079`/`E-UX-005`; +36,400 B linked flash, +24 B static RAM, and +36,400 B images vs 0.54. The 111-ID/222-string catalog and generated 16/12 px Cyrillic faces add no runtime font heap; exact TFT HIL proves persistence, fit, Quick 8/8, zero input drops, and final lease 0 |
| RB-M61 | measured | non-color focus outline/chevron + five-key accessibility contract | 1,105,748 B linked flash; 128,744 B static RAM; app/factory images 1,105,904/1,171,440 B; RTC no-init 20 B; runtime heap total/free/min 272,760/224,280/188,792 B | board-01 `0.56.0-ui-accessibility-measure`, `E-BUILD-058`/`E-HIL-080`/`E-UX-006`; +1,300 B linked flash, zero static-RAM growth, and +1,312 B images vs 0.55. Exact TFT actions prove geometric focus across Home/Library/Self-Test, Quick 8/8, zero current input errors/drops, buzzer LOW, and final lease 0; retained physical evidence proves 50/50/50 key events |
| RB-M62 | measured | Full/Guided common-state renderer + plan-2 evidence | 1,107,448 B linked flash; 128,744 B static RAM; app/factory images 1,107,600/1,173,136 B; RTC no-init 20 B; runtime heap total/free/min 272,760/224,280/188,792 B | board-01 `0.57.0-ui-state-evidence-measure`, `E-BUILD-059`/`E-HIL-081`/`E-UX-007`; +1,700 B linked flash, zero static-RAM growth, and +1,696 B images vs 0.56. Nine exact TFT frames cover modes/preflight/five common states/result/cleanup; plan 2 is 9 pass/0 fail/1 honest blocker, with zero side effects, input drops, or final leases |
| RB-M63 | measured | exact reproducible DEMO-S2 | 1,107,612 B linked flash; 128,744 B static RAM; app/factory images 1,107,760/1,173,296 B; RTC no-init 20 B; runtime heap total/free/min 272,760/224,280/188,792 B | board-01 `0.58.0-stage-demo-s2-measure`, `E-BUILD-060`/`E-HIL-082`/`E-GATE-002`; +164 B linked flash, zero static-RAM growth, and +160 B images vs 0.57. Exact 29-step demo matches nine TFT frames, passes Quick 8/8, and closes S2 with zero final leases; release gate remains false |
| RB-M64 | measured | persistent asynchronous Product Survey worker | 1,111,148 B linked flash; 128,800 B static RAM; app/factory images 1,111,296/1,176,832 B; RTC no-init 20 B; runtime heap total/free/min 272,704/208,928/188,736 B | board-01 `0.59.0-product-survey-worker-measure`, `E-BUILD-061`/`E-AUTO-024`/`E-HIL-084`; +3,536 B linked flash, +56 B static RAM, and +3,536 B images vs 0.58. Core-0 task and fixed queues 8/64 sustain two continuous scan cycles, high-water 10/64, 27/27 forwarded, zero drops/heap drift, 13/10 us Start/Stop callbacks, and final lease 0; S3/release gates remain false |
| RB-M65 | measured | UI-acknowledged Product Survey terminal ownership | 1,111,128 B linked flash; 128,800 B static RAM; app/factory images 1,111,280/1,176,816 B; RTC no-init 20 B; runtime heap total/free/min 272,704/208,928/188,736 B | board-01 `0.60.0-product-survey-terminal-ack-measure`, `E-BUILD-062`/`E-AUTO-025`/`E-HIL-085`; 20 B less linked flash, zero static-RAM delta, and 16 B smaller images vs 0.59. UI alone exposes terminal `Idle` after cleanup/commit; exact regression sustains two scans, high-water 9/64, 25/25 forwarded, zero drops/heap drift, 12/8 us Start/Stop callbacks, and final lease 0; S3/release gates remain false |
| RB-M66 | measured | observable physical active-scan cancel + bounded PCF8574 boot probe | 1,111,564 B linked flash; 128,816 B static RAM; app/factory images 1,111,712/1,177,248 B; RTC no-init 20 B; runtime heap total/free/min 272,688/208,912/188,720 B | board-01 `0.62.0-input-probe-resilience-measure`, `E-BUILD-063`/`E-AUTO-026`/`E-HIL-086`; +132 B linked flash, +16 B static RAM, and +128 B images vs failed 0.61. Exact HIL cancels during an active scan in 86.762 ms with a 9 us callback, unchanged generation 68/25, zero SD writes/heap drift, and final lease 0. The retained 0.61 one-shot input-probe failure led to bounded 1…8-attempt/35 ms-extra boot accounting; both 0.62 boots detect input on attempt 1; deliberate first-read injection remains additional evidence |
| RB-M67 | measured | Roboto Condensed Medium 16/12 typography replacement + 18-state TFT regression | 1,111,932 B linked flash; 128,816 B static RAM; app/factory images 1,112,336/1,177,872 B; RTC no-init 20 B; runtime heap total/free/min 272,688/208,912/188,720 B | board-01 `0.63.0-roboto-condensed-ui-measure`, `E-BUILD-064`/`E-AUTO-027`/`E-HIL-087`/`E-UX-008`; +368 B linked flash, zero static-RAM growth, and +624 B images vs 0.62. Vendored OFL source weight 500 produces 2,153/1,275 B body/meta bitmaps, all 127 IDs/254 variants fit after eight safe shortenings, 18 exact TFT frames cover EN/RU and Full/Guided states, Quick is 8/8, Full is 9/10 with one honest blocker, side effects/input drops/heap drift are zero, and final lease is 0 |
| RB-M68 | measured | 40 px three-cell spatial navigation + exact TFT/action regression | 1,111,100 B linked flash; 128,816 B static RAM; app/factory images 1,111,504/1,177,040 B; RTC no-init 20 B; runtime heap total/free/min 272,688/208,912/188,720 B | board-01 `0.64.0-spatial-navigation-measure`, `E-BUILD-065`/`E-AUTO-028`/`E-HIL-088`/`E-UX-009`; −832 B linked/app/factory and zero static-RAM growth vs 0.63 after replacing 19 prose footers with 15 compact actions. Nine exact TFT frames and 15 transitions prove Left Back, Right/OK Enter, Up/Down Select, nested Library parity, zero input errors/drops, buzzer LOW, invariant heap, and final lease 0 |
| RB-M69 | measured | 26 px compact footer + changed-row-only incremental rendering | 1,112,256 B linked flash; 128,856 B static RAM; app/factory images 1,112,656/1,178,192 B; RTC no-init 20 B; runtime heap total/free/min 272,648/208,872/188,680 B | board-01 `0.65.0-compact-incremental-ui-measure`, `E-BUILD-066`/`E-AUTO-029`/`E-HIL-089`/`E-UX-010`; +1,156 B linked flash, +40 B static RAM and +1,152 B images vs 0.64. Eight exact incremental transitions repaint only old/new rows in 19.901–28.981 ms under a 40 ms ceiling, compared with the observed 63.615 ms whole-page redraw; nine frames/21 transitions retain navigation, zero input errors/drops, invariant heap, buzzer LOW and final lease 0 |
| RB-M70 | measured | 0.x-style ordered input dispatch + footer-free incremental repaint | 1,112,172 B linked flash; 128,856 B static RAM; app/factory images 1,112,576/1,178,112 B; RTC no-init 20 B; runtime heap total/free/min 272,648/208,872/188,680 B | board-01 `0.66.0-ordered-key-repaint-measure`, `E-BUILD-067`/`E-AUTO-030`/`E-HIL-090`/`E-UX-011`; −84 B linked flash, zero static-RAM delta, and −80 B images vs 0.65. One queued physical press is rendered before the next is dequeued, so rapid selections cannot coalesce; selection repaint skips the footer/input strip. Eight exact transitions take 13.927–23.043 ms, with nine frames/21 transitions, zero input errors/drops, invariant heap, buzzer LOW and final lease 0 |
| RB-M71 | measured | non-blocking physical-key hot path + on-demand end-to-end telemetry | 1,112,568 B linked flash; 128,896 B static RAM; app/factory images 1,112,976/1,178,512 B; RTC no-init 20 B; runtime heap total/free/min 272,608/208,320/188,140 B | board-01 `0.67.0-nonblocking-keypath-measure`, `E-BUILD-068`/`E-AUTO-031`/`E-HIL-091`/`E-UX-012`; +396 B linked flash, +40 B static RAM, +400 B images and a 512 B larger 64-slot runtime queue vs 0.66 because each event now carries a microsecond timestamp. Removing post-render USB/UART writes reduces the user-observed 10-press queue high-water 5 to 1 across 75 confirmed presses; max queue latency 1.256 ms, last focus end-to-end 16.703 ms, zero errors/drops/serial writes; eight TFT transitions remain 13.972–23.058 ms |
| RB-M72 | measured | localized missing-source terminal UI + one-shot source-boundary HIL telemetry | 1,114,184 B linked flash; 128,920 B static RAM; app/factory images 1,114,592/1,180,128 B; RTC no-init 20 B; runtime heap total/free/min 272,584/208,168/188,116 B | board-01 `0.68.0-missing-source-tft-measure`, `E-BUILD-069`/`E-AUTO-032`/`E-HIL-092`/`E-SURVEY-007`; +1,616 B linked flash, +24 B static RAM and +1,616 B images vs 0.67. One-shot failure is consumed before source/store start; the RU 240×320 unavailable state is visible after lease 15→0, writes/observations stay 0, hidden retry is blocked, cold reboot preserves generation 68/25, heap is invariant and final lease is 0 |
| RB-M73 | measured | isolated inactive-OTA1 LittleFS normal/remount parity | 1,153,228 B linked flash; 130,216 B static RAM; app/factory images 1,153,632/1,219,168 B; RTC no-init 20 B; parity heap free before/after/min 206,424/206,088/186,820 B | board-01 `0.69.0-littlefs-parity-measure`, `E-BUILD-070`/`E-AUTO-033`/`E-HIL-093`/`E-STORAGE-024`; +39,044 B linked flash, +1,296 B static RAM and +39,040 B images vs 0.68. Common SessionStore completes 32/32 generations with 96+96 barriers and RO-remount recovery 32/64; 18,586 B/s exceeds the 2,184 B/s target by 8.51×. Inactive OTA1 and partition table restore exact hashes, product 68/25 is unchanged, and final lease is 0 |
| RB-M74 | measured | isolated inactive-OTA1 LittleFS six-boundary software-reset matrix | 1,165,916 B linked flash; 134,888 B static RAM; app/factory images 1,166,320/1,231,856 B; RTC no-init 60 B; product heap total/free/min 266,616/202,200/182,148 B | board-01 `0.70.0-littlefs-reset-matrix`, `E-BUILD-071`/`E-AUTO-034`/`E-HIL-094`/`E-STORAGE-025`; +12,688 B linked flash, +4,672 B static RAM, +12,688 B images and +40 B RTC no-init vs 0.69. Six software-reset boundaries recover generations 1/1/1/1/1/2 read-only with zero writes/syncs, exact continuity and cleanup. One OTA1 restore write plus independent read-only verification preserves exact target/table hashes and unchanged product 68/25 |
| RB-M75 | measured | first S4 user slice: selectable Survey source plan | 1,169,012 B linked flash; 134,928 B static RAM; app/factory images 1,169,424/1,234,960 B; RTC no-init 60 B; product heap total/free/min 266,576/202,160/182,108 B | board-01 `0.71.0-survey-source-plan`, `E-BUILD-072`/`E-AUTO-036`/`E-HIL-096`/`E-SURVEY-009`; +3,096 B linked flash, +40 B static RAM and +3,104 B images vs 0.70. Exact physical HIL covers selectable Wi-Fi, visibly unavailable BLE, empty-plan Start rejection and Wi-Fi restoration through 11 transitions/five TFT frames; max incremental render 31,818 us, zero input errors/drops, invariant heap, buzzer inactive and final lease 0 |
| RB-M76 | measured | S4 shared source-timeline runtime and visible Wi-Fi duty | 1,174,456 B linked flash; 136,880 B static RAM; app/factory images 1,174,864/1,240,400 B; RTC no-init 60 B; product heap total/free/min 264,624/199,952/180,156 B | board-01 `0.72.0-source-timeline-runtime`, `E-BUILD-073`/`E-AUTO-037`/`E-HIL-097`/`E-SURVEY-010`; +5,444 B linked flash, +1,952 B static RAM and +5,440 B images vs 0.71. Exact HIL accounts two real scans as 34/34 observations and 4→5 windows with zero drops/overflow, displays 74% Wi-Fi duty, commits generation 71→72, cold-recovers exact CID, keeps heap invariant and ends with lease 0. Timeline persistence/export and durable FIFO drain remain open |
| RB-M77 | measured | S4 durable source-timeline persistence, cold reopen and export | 1,184,052 B linked flash; 145,184 B static RAM; app/factory images 1,184,208/1,249,744 B; RTC no-init 60 B; product heap total/free/min 256,320/191,648/171,852 B | board-01 `0.73.0-source-timeline-persistence`, `E-BUILD-074`/`E-AUTO-038`/`E-HIL-098`/`E-SURVEY-011`; +9,596 B linked flash, +8,304 B static RAM and +9,344 B images vs 0.72 for schema-v2 timeline records, bounded retained windows, summaries and export workspace. Exact HIL drains FIFO to 0/high-water 1, accounts 21/21 observations, commits generation 73→74, cold-reopens and exports five ordered windows with exact duration equality, zero drops/overflow, invariant heap and final lease 0 |
| RB-M78 | measured | S4 bounded passive BLE and durable dual-source Survey | 1,419,892 B linked flash; 147,360 B static RAM; app/factory images 1,420,304/1,485,840 B; RTC no-init 60 B; product heap total/free/min 234,348/169,728/150,208 B | board-01 `0.74.0-passive-ble`, `E-BUILD-075`/`E-AUTO-039`/`E-HIL-099`/`E-SURVEY-012`; +235,840 B linked flash, +2,176 B static RAM and +236,096 B images vs 0.73, primarily for the Arduino BLE stack. Exact HIL streams and immediately erases advertisements, accounts Wi-Fi 6 + BLE 34 = 40 observations, drains FIFO to 0/high-water 2, commits generation 76→77 with six retained/exported windows, zero drops/overflow, invariant cold-boot heap and final lease 0 |
| RB-M79 | measured | S4 compatible runtime source degradation | 1,421,832 B linked flash; 147,360 B static RAM; app/factory images 1,422,240/1,487,776 B; RTC no-init 60 B; product heap total/free/min 234,348/169,728/150,208 B | board-01 `0.75.0-runtime-degradation`, `E-BUILD-076`/`E-AUTO-040`/`E-HIL-100`/`E-SURVEY-013`; +1,940 B linked flash, zero static-RAM growth and +1,936 B images vs 0.74. Exact HIL safely injects BLE unavailability, continues two real Wi-Fi cycles for 28 observations, drains FIFO to 0/high-water 2, commits generation 77→78 with eight retained/exported windows including 3,625,744 us `driver_unavailable`, zero drops/overflow, invariant cold-boot heap and final lease 0 |
| RB-M80 | measured | S4 common Observation browser, bounded RSSI history and RF-off snapshot | 1,426,252 B linked flash; 147,368 B static RAM; app/factory images 1,426,656/1,492,192 B; RTC no-init 60 B; product heap total/free/min 234,340/169,720/150,200 B | board-01 `0.76.0-observation-browser`, `E-BUILD-077`/`E-AUTO-041`/`E-HIL-101`/`E-SURVEY-014`; +4,420 B linked flash, +8 B static RAM and +4,416 B images vs 0.75. Exact HIL completes one Wi-Fi+BLE cycle with 8+37 observations, freezes RF and finalizes six windows before user browsing, proves All/Wi-Fi/BLE counts 45/8/37 plus both RSSI Detail views, commits generation 80→81, cold-reopens the exact snapshot, and ends with zero drops/overflow and lease 0 |
| RB-M81 | measured | S4 immutable Capture metadata, schema v3 and streaming observation CSV | 1,432,812 B linked flash; 147,688 B static RAM; app/factory images 1,433,216/1,498,752 B; RTC no-init 60 B; product heap total/free/min 234,020/169,400/149,880 B | board-01 `0.77.0-capture-export`, `E-BUILD-078`/`E-AUTO-042`/`E-HIL-102`/`E-SURVEY-015`; +6,560 B linked flash, +320 B static RAM and +6,560 B images vs 0.76. Exact HIL persists generation 81→82 with 16 Wi-Fi + 31 BLE observations and immutable build/receive provenance, cold-reopens it, streams 47 canonical CSV rows/3,275 B with no second Session-sized buffer, reports PCAP honestly unavailable without raw payload, retains ten TFT frames, preserves heap and ends with zero drops/overflow and lease 0 |
| RB-M82 | measured | S4 bounded volatile Wi-Fi frame Capture and streaming radiotap PCAP | 1,446,000 B linked flash; 152,376 B static RAM; app/factory images 1,446,400/1,511,936 B; RTC no-init 60 B; product heap total/free/min 229,332/164,712/145,192 B | board-01 `0.78.0-wifi-frame-capture`, `E-BUILD-079`/`E-AUTO-043`/`E-HIL-103`/`E-CAPTURE-001`; +13,188 B linked flash, +4,688 B static RAM and +13,184 B images vs 0.77. Exact HIL bounds payload to 16×256 B/4,096 B, counts 18 capacity drops without overwrite, streams 16 valid radiotap/802.11 records in a 4,616 B PCAP, performs zero application connect/raw-TX/storage calls, retains no raw payload in evidence, scrubs RAM on Back and ends at lease 0 |
| RB-M83 | measured | S4 privacy-confirmed persistent Wi-Fi Capture, schema v4 and cold Library PCAP | 1,454,428 B linked flash; 152,424 B static RAM; app/factory images 1,454,832/1,520,368 B; RTC no-init 60 B; product heap total/free/min 229,284/164,540/145,144 B | board-01 `0.79.0-persistent-frame-capture`, `E-BUILD-080`/`E-AUTO-044`/`E-HIL-104`/`E-CAPTURE-002`; +8,428 B linked flash, +48 B static RAM and +8,432 B images vs 0.78. The 48 B covers persistent-view/workspace metadata, not a duplicate payload store. Exact HIL atomically advances generation 82→83 after explicit privacy confirmation, cold-reopens 16 frames/2,253 B, streams a byte-exact 2,773 B Library PCAP, preserves heap across reboot, scrubs live RAM and ends at lease 0 |
| RB-M84 | measured | plan-v3 Self-Test registration for completed S3/S4 workflows and no-extension dispositions | 1,456,012 B linked flash; 152,520 B static RAM; app/factory images 1,456,416/1,521,952 B; RTC no-init 60 B; product heap total/free/min 229,188/164,444/145,048 B | board-01 `0.80.0-self-test-coverage`, `E-BUILD-081`/`E-AUTO-045`/`E-HIL-105`/`E-SELFTEST-002`; +1,584 B linked flash, +96 B static RAM and +1,584 B images vs 0.79. Exact HIL proves Quick 8/8 and Full 15 pass/0 fail/2 blocked/3 N/A with ten TFT frames, unchanged storage generation, zero side effects/input drops and final lease 0 |
| RB-M85 | measured | plan-v4 guarded read-only identity probe for declared RF-shield receivers | 1,459,232 B linked flash; 152,552 B static RAM; app/factory images 1,459,632/1,525,168 B; RTC no-init 60 B; product heap total/free/min 229,156/164,412/145,016 B | board-01 `0.81.0-shield-receiver-probe`, `E-BUILD-082`/`E-AUTO-046`/`E-HIL-106`/`E-SELFTEST-003`/`E-RADIO-001`; +3,220 B linked flash, +32 B static RAM and +3,216 B images vs 0.80. Exact HIL detects two nRF24 and one CC1101 through 20 SPI bytes with zero CE-high/strobe/TX events, proves Full 16 pass/0 fail/1 blocked/3 N/A, unchanged storage and final lease 0 |
| RB-M86 | measured | volatile user-facing dual-nRF24 spectrum activity map | 1,466,356 B linked flash; 152,752 B static RAM; app/factory images 1,466,768/1,532,304 B; RTC no-init 60 B; product heap total/free/min 228,956/164,212/144,816 B | board-01 `0.82.0-nrf24-spectrum`, `E-BUILD-083`/`E-AUTO-047`/`E-HIL-107`/`E-RADIO-002`; +7,124 B linked flash, +200 B static RAM and +7,136 B images vs 0.81. Exact HIL completes 21×83-channel sweeps through two receivers, verifies pause/resume, 99 activity hits, zero TX/CC/storage side effects, unchanged heap/storage and final lease 0 |
| RB-M87 | measured | volatile user-facing four-band CC1101 RSSI spectrum map | 1,473,780 B linked flash; 152,928 B static RAM; app/factory images 1,474,192/1,539,728 B; RTC no-init 60 B; product heap total/free/min 228,780/164,036/144,640 B | board-01 `0.83.0-cc1101-spectrum`, `E-BUILD-084`/`E-AUTO-048`/`E-HIL-108`/`E-RADIO-003`; +7,424 B linked flash, +176 B static RAM and +7,424 B images vs 0.82. Exact HIL completes all four 64-bin band plans, verifies a stable 400 ms pause and resume, records 354 receive samples with zero TX/PATABLE/FIFO/storage side effects, unchanged heap/storage and final lease 0 |
| RB-M88 | measured | plan-v5 active receive-only RF checks in Full/Guided | 1,478,132 B linked flash; 153,064 B static RAM; app/factory images 1,478,544/1,544,080 B; RTC no-init 60 B; product heap total/free/min 228,644/163,900/144,504 B | board-01 `0.84.0-full-guided-rf`, `E-BUILD-085`/`E-AUTO-049`/`E-HIL-109`/`E-SELFTEST-004`/`E-RADIO-004`; +4,352 B linked flash, +136 B static RAM and +4,352 B images vs 0.83. Exact HIL keeps Quick at read-only 8/8 and Full at 18 pass/0 fail/1 blocker/3 N/A after one complete dual-nRF24 sweep and one 64-bin CC1101 433 MHz sweep, with zero TX/storage side effects, unchanged generation, 11 reviewed TFT states and final lease 0 |
| RB-M89 | measured | plan-v6 read-only persisted Session/Library/export checks in Full/Guided | 1,482,568 B linked flash; 153,712 B static RAM; app/factory images 1,482,976/1,548,512 B; RTC no-init 60 B; product heap total/free/min 227,996/163,252/130,252 B | board-01 `0.85.0-full-guided-artifacts`, `E-BUILD-086`/`E-AUTO-050`/`E-HIL-110`/`E-SELFTEST-005`/`E-STORAGE-026`/`E-CAPTURE-003`; +4,436 B linked flash, +648 B static RAM and +4,432 B images vs 0.84. Exact HIL keeps Quick at 8/8 and advances Full to 21 pass/0 fail/1 blocker/3 N/A, recovers unchanged generation 83 read-only, stages Library JSON/CSV and streams 16 frames/2,773 B of radiotap PCAP, with zero storage writes/TX events, 12 reviewed TFT states and final lease 0. The 13,604 B lower observed heap minimum is retained and must be covered by endurance, not explained away |
| RB-M90 | measured | plan-v7 exact-CID disposable Session commit/remount/export/cleanup in Full/Guided | 1,491,132 B linked flash; 154,472 B static RAM; app/factory images 1,491,536/1,557,072 B; RTC no-init 60 B; product heap total/free/min 227,236/162,492/129,276 B | board-01 `0.86.0-full-guided-disposable`, `E-BUILD-087`/`E-AUTO-051`/`E-HIL-111`/`E-SELFTEST-006`/`E-STORAGE-027`; +8,564 B linked flash, +760 B static RAM and +8,560 B images vs 0.85. Exact HIL keeps Quick 8/8 and advances Full to 25 pass/0 fail/1 blocker/3 N/A, commits only disposable generation 1 through three writes/504 B and six durability barriers, read-only remounts/exports it, removes three files/scratch, preserves product 83/0, zero TX/product writes and final lease 0. The 129,276 B minimum is 1,796 B below the 128 KiB RB-04 floor and is retained as a required endurance/heap-budget issue, not waived by this functional pass |
| RB-M91 | measured | final-facts heap enforcement and shared serial diagnostics/storage workspace | 1,491,172 B linked flash; 149,864 B static RAM; app/factory images 1,491,584/1,557,120 B; RTC no-init 60 B; product heap total/boot-free/final-free/min 231,844/167,100/166,884/133,884 B | board-01 `0.87.0-full-guided-heap-budget`, `E-BUILD-088`/`E-AUTO-052`/`E-HIL-112`/`E-SELFTEST-007`; +40 B linked flash, −4,608 B static RAM and +48 B images vs 0.86. The two serial-only 4,608/5,120 B workspaces now share one 5,120 B buffer; final Full/Guided facts rebuild Quick so a native below-floor regression fails. Exact physical plan v7 remains 25/0/1/3 and now passes the 131,072 B floor with minimum 133,884 B/margin 2,812 B, exact disposable cleanup, product 83/0 and final lease 0. Endurance must still prove no monotonic degradation |
| RB-M92 | measured | calibrated XPT2046 touch input, persistent calibration, shared hit targets and plan-v8 Quick check | 1,497,056 B linked flash; 149,936 B static RAM; app/factory images 1,497,456/1,562,992 B; RTC no-init 60 B; short touch HIL heap total/free/min 231,772/167,028/147,632 B | board-01 `0.88.0-touch-input`, `E-BUILD-089`/`E-AUTO-053`/`E-HIL-113`/`E-UX-013`/`E-SELFTEST-008`; +5,884 B linked flash, +72 B static RAM and +5,872 B images vs 0.87. One real calibrated point opens the intended row; Quick passes 9/9, four TFT states and explicit chrome misses are retained, heap is identical before/after, drops are zero and final lease is 0. This short focused run does not replace endurance |
| RB-M93 | measured | cross-radio product release endurance with non-overlapping SD/radio lifecycles | 1,498,576 B linked flash; 149,936 B static RAM; app/factory images 1,498,832/1,564,512 B; exact release heap total/free/min 231,772/166,812/147,460 B | board-01 `0.89.0-touch-storage-dma`, `E-BUILD-090`/`E-AUTO-054`/`E-HIL-114`/`E-SURVEY-016`/`E-GATE-004`; +1,520 B linked flash and zero static-RAM growth vs 0.88. Eight complete Wi-Fi+BLE cycles over 2,799.845 s advance generation 86→94, forward 111+256=367 observations through 16 cold boots with zero drops/timeouts/heap drift and final lease 0; one bounded boot retry succeeds. This closes RB-04/release endurance, not controlled physical power-cut recovery |
| RB-M94 | measured | product-first Home and nested Device service menu | 1,500,384 B linked flash; 149,936 B static RAM; app/factory images 1,500,784/1,566,320 B; exact menu HIL heap total/free/min 231,772/166,812/147,460 B | board-01 `0.90.0-product-menu`, `E-BUILD-091`/`E-AUTO-055`/`E-HIL-115`/`E-UX-014`; +1,808 B linked flash, zero static-RAM growth and +1,952/+1,808 B app/factory images vs 0.89. Eight TFT states prove the six-domain Home, four-item Device submenu, touch/key navigation and final lease 0; Targets/Lab remain disabled and controlled physical power cut remains open |
| RB-M95 | measured | compact truthful SD/RF header and four-row product viewport | 1,500,508 B linked flash; 149,936 B static RAM; app/factory images 1,500,912/1,566,448 B; exact menu/RF HIL heap total/free/min 231,772/166,812/147,460 B | board-01 `0.91.0-clean-status`, `E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015`; +124 B linked flash, zero static-RAM growth and +128/+128 B images vs 0.90. Four 216×46 px rows fit above the y=282 footer divider; exact framebuffer crops prove idle `RF --` versus real receive `RF RX`, while SD remains `SD OK`, generation 95/0 and final lease 0. No battery or instrumented RF-silence claim is added |
| RB-M96 | measured | full-width Spectrum/Waterfall viewport and bounded RF history | 1,504,500 B linked flash; 159,832 B static RAM; app/factory images 1,504,912/1,570,448 B; RTC no-init 60 B; exact dual-radio HIL heap total/free/min 221,876/156,916/137,564 B | board-01 `0.92.0-spectrum-views`, `E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/`E-RADIO-005`; +3,992 B linked flash, +9,896 B static RAM and +4,000/+4,000 B images vs 0.91. The fixed 112×83-byte history plus small metadata consumes the static delta without runtime allocation; 32 nRF24 and 16 CC1101 rows, four CC bands, 22 TFT states, invariant heap/storage and final lease 0 are retained |
| RB-M97 | measured | implemented-only seven-job Home plus host-side connected-candidate automation | 1,505,972 B linked flash; 159,856 B static RAM; app/factory images 1,506,384/1,571,920 B; RTC no-init 60 B; exact product-home HIL heap total/free/min 221,852/156,892/137,540 B | board-01 `0.93.0-product-menu`, `E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/`E-RADIO-006`; +1,472 B linked flash, +24 B static RAM and +1,472/+1,472 B images vs 0.92. The firmware delta is the seven-entry catalog, Wi-Fi/BLE source scopes and direct receiver routes; build/flash/HIL/screenshots/verification orchestration stays host-side and consumes no device RAM. One exact run retains 13 TFT states, 16/8 nRF24/CC rows, unchanged heap/storage and final lease 0 |
| RB-M98 | measured | localized root-only Home identity and visible build-derived SemVer | 1,506,228 B linked flash; 159,856 B static RAM; app/factory images 1,506,640/1,572,176 B; RTC no-init 60 B; exact bilingual Home HIL heap total/free/min 221,852/156,892/137,540 B | board-01 `0.94.0-home-identity`, `E-BUILD-095`/`E-AUTO-059`/`E-HIL-119`/`E-UX-018`; +256 B linked flash, zero static-RAM growth and +256/+256 B images vs 0.93. A bounded 24-byte stack buffer derives `v0.94.0` from the full build ID; it creates no retained heap. Exact HIL captures `LESHY` and `Леший`, restores Russian, retains 14 TFT states, unchanged heap/storage and final lease 0 |
| RB-M99 | measured | inline physical-key hint presentation derived from 0.x geometry | 1,506,428 B linked flash; 159,856 B static RAM; app/factory images 1,506,832/1,572,368 B; RTC no-init 60 B; exact physical HIL heap total/free/min 221,852/156,892/137,540 B | board-01 `0.95.0-inline-key-hints`, `E-BUILD-096`/`E-AUTO-060`/`E-HIL-120`/`E-UX-019`; +200 B linked flash, zero static-RAM growth and +192/+192 B images vs 0.94. The footer uses no retained buffer or heap allocation. Exact HIL retains 14 EN/RU Home/menu/RF TFT states, unchanged storage/heap and final lease 0 |
| RB-M100 | measured | compact contextual header/four-row navigation and receiver-independent three-second waterfall cadence | 1,507,264 B linked flash; 159,888 B static RAM; app/factory images 1,507,408/1,572,944 B; RTC no-init 60 B; exact stabilized HIL heap total/free/min 221,820/156,712/137,360 B | board-01 `0.96.0-compact-ui-waterfall`, `E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/`E-RADIO-007`; +836 B linked flash, +32 B static RAM and +576/+576 B images vs 0.95. The static timing state and allocation-free 26,785 us cadence reuse the existing 112-row ring; no second history is allocated. One exact flash retains 14 EN/RU Home/menu/RF states and measures full-area host fill in 2.905…2.927 s across nRF24 plus CC315/433/868/915, with invariant stabilized heap, unchanged storage, zero TX/storage/input drops and final lease 0 |
| RB-M103 | measured | receiver-paced exact-pixel RF raster, Wi-Fi Signal/Traffic modes, all-available nRF reception and non-blocking idle touch | 1,510,960 B linked flash; 205,296 B static RAM; app/factory images 1,511,360/1,576,896 B; exact stabilized HIL heap total/free/min 176,412/111,372/92,020 B | board-01 `0.99.0-wifi-spectrum-modes`, `E-BUILD-100`/`E-AUTO-064`/`E-HIL-124`/`E-UX-023`/`E-RADIO-010`; +3,696 B linked flash, +45,408 B static RAM and +3,952/+3,952 B images vs 0.96. The fixed history is now the physical 240×224 eight-bit raster (53,760 B); it adds no runtime allocation. One complete sweep emits one row, so full-history time is receiver-limited rather than display-timer-limited: host 2.344/2.373 s for nRF Signal/Traffic and 32.793/22.857/31.438/31.595 s for CC315/433/868/915. All paths skip zero measurements, use zero recovery in the exact run, preserve generation 95/0 and finish with lease 0. The 92,020 B short-run minimum is below the historical 128 KiB RB-04 Survey floor; this focused display/RF checkpoint therefore does not supersede accepted 0.89 endurance and requires a future mixed-workload budget review if the larger raster is present there |
| RB-M104 | measured | source-bin waterfall history with render-time display expansion | 1,510,900 B linked flash; 170,128 B static RAM; app/factory images 1,511,312/1,576,848 B; exact stabilized HIL heap total/free/min 211,580/146,472/127,120 B | board-01 `0.100.0-spectrum-source-history`, `E-BUILD-101`/`E-AUTO-065`/`E-HIL-125`/`E-UX-024`/`E-RADIO-011`; −60 B linked flash, −35,168 B static RAM and −48/−48 B images vs 0.99. The 224-row ring stores at most 83 one-byte receiver bins per row (18,592 B); the renderer maps those source bins to the 240-pixel display scanline without interpolation. Exact HIL preserves one complete sweep per physical row, six zero-skip paths, all three nRF slots and zero CC retry/recovery; host fill is 2.083/2.346 s for nRF Signal/Traffic and 32.977/22.488/31.699/31.874 s for CC315/433/868/915, with a maximum measured 611 us row render. The short focused minimum recovers by 35,100 B to 127,120 B, 3,952 B below the historical 128 KiB Survey floor; accepted 0.89 endurance remains authoritative for the mixed workload and future mixed-workload changes still require budget review |
| RB-M105 | measured | isolated six-boundary physical power-cut protocol and exact-device runner | 1,512,700 B linked flash; 170,128 B static RAM; app/factory images 1,512,848/1,578,384 B; exact product HIL heap total/free/min 211,580/146,472/127,120 B | board-01 `0.101.0-power-cut-harness`, `E-BUILD-102`/`E-AUTO-066`/`E-HIL-126`/`E-STORAGE-028`/`E-GATE-005`; +1,800 B linked flash, zero static-RAM growth and +1,536/+1,536 B images vs 0.100. Six real 5.216…6.589 s cuts recover generations 1/1/1/1/1/2 read-only with zero recovery writes/syncs, unchanged product 95/0 and final lease 0; exact source/candidate/CID/USB identity are bound. This closes RB-06 power-cut evidence for the common SessionStore on one board/card pair, not broad media compatibility |
| RB-M106 | measured | main-loop safety supervisor, retained Safe Mode and destructive exact-device watchdog runner | 1,534,668 B linked flash; 171,496 B static RAM; app/factory images 1,535,072/1,600,608 B; normal HIL heap total/free/min 209,956/144,688/125,496 B; Safe Mode heap 209,956/161,296/160,256 B; RTC no-init 108 B | board-01 `0.103.0-safety-supervisor`, `E-BUILD-104`/`E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001`; +6,832 B linked flash, +96 B static RAM and +6,980/+7,236 B images vs 0.102. The real Task-WDT resets in 5,810.775 ms, retained Safe Mode survives a software restart, exact catalog 95/0 is unchanged and final lease is 0. The dedicated 16,384 B IRAM region is 100% occupied with zero margin; any further IRAM growth must first recover or rebudget space |
| RB-M107 | measured | passive infrared RAW/NEC Capture, SessionStore v6/CSV and declarative HIL scenario engine | 1,549,056 B linked flash; 172,760 B static RAM; app/factory images 1,549,456/1,614,992 B; exact HIL heap total/free/min 208,692/143,256/124,160 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.104.0-infrared-capture`, `E-BUILD-105`/`E-AUTO-069`/`E-HIL-129`/`E-RADIO-013`/`E-STORAGE-030`; +14,388 B linked flash, +1,264 B static RAM and +14,384/+14,384 B images vs 0.103. The exact no-signal path performs 345,272 GPIO21 samples in 10,000,018 us with zero transitions, TX or writes, keeps GPIO14 and all nRF CE lines LOW, preserves catalog 95/0 and heap, captures seven TFT states, and finishes Home with lease 0. Successful physical-signal decode/persistence remains open for the second-board fixture |
| RB-M108 | measured | outcome-first product copy, result presentation and retained multi-flow visual gate | 1,551,752 B linked flash; 172,760 B static RAM; app/factory images 1,552,008/1,617,696 B; exact HIL heap total/free/min 208,692/143,256/124,160 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.106.0-product-content`, `E-BUILD-106`/`E-AUTO-070`/`E-HIL-130`/`E-UX-025`; +2,696 B linked flash, zero static-RAM growth and +2,552/+2,704 B images vs 0.104. One fresh flash plus three exact-hash reuse runs retain 37 TFT states across product routes; the supplementary visual Wi-Fi Capture run exports no PCAP and writes zero SD bytes. Exact CID/catalog/heap and final lease 0 remain unchanged; IRAM has zero growth margin |
| RB-M109 | measured | bounded Nearby Networks catalog plus final Wi-Fi menu/list/detail | 1,558,808 B linked flash; 175,168 B static RAM; app/factory images 1,558,552/1,624,240 B; post-warm exact HIL heap total/free/min 206,284/140,032/76,084 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.107.0-wifi-networks`, `E-BUILD-107`/`E-AUTO-071`/`E-HIL-131`/`E-UX-026`; +7,056 B linked flash, +2,408 B static RAM and +6,544/+6,544 B images vs 0.106. The allocation-free 32-record BSSID catalog has stable insertion order and bounded replacement. A fresh boot exposes a one-time 816 B ESP-IDF Wi-Fi warm allocation; three independent post-warm endpoints and both full lifecycle endpoints are byte-identical. Two physical lifecycles find 13 then 20 unique networks with zero drops/writes and final lease 0; IRAM still has zero growth margin |
| RB-M110 | measured | passive Wi-Fi client decoder, bounded Devices catalog and list/detail | 1,566,368 B linked flash; 178,360 B static RAM; app/factory images 1,566,512/1,632,048 B; post-warm exact HIL heap total/free/min 203,092/137,032/75,112 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.108.0-wifi-devices`, `E-BUILD-108`/`E-AUTO-072`/`E-HIL-132`/`E-UX-027`; +7,560 B linked flash, +3,192 B static RAM and +7,960/+7,808 B images vs 0.107. Fixed storage adds a 64-frame ingress queue and 32-client catalog; runtime monitoring is volatile/NVS-disabled and allocation-free in the app path. Two physical lifecycles have byte-identical post-warm heap, observe real clients over all 13 channels with zero drops/writes, keep static chrome/detail unchanged and finish with lease 0; IRAM still has zero growth margin |
| RB-M111 | measured | passive Wi-Fi airtime aggregation and Channels graph | 1,570,480 B linked flash; 179,680 B static RAM; app/factory images 1,570,880/1,636,416 B; post-warm exact HIL heap total/free 201,772/135,712 B, minimum floor 73,776 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.109.0-wifi-channels`, `E-BUILD-109`/`E-AUTO-073`/`E-HIL-133`/`E-UX-028`; +4,112 B linked flash, +1,320 B static RAM and +4,368/+4,368 B images vs 0.108. The delta includes bounded 13-bin airtime state and 1 KiB extra shared diagnostic capacity. Two physical lifecycles measure all channels with stable post-warm total/free heap, zero writes, inactive buzzer and final lease 0; IRAM remains full |
| RB-M112 | measured | direct Wi-Fi packet recorder route and changed-metric-only live UI | 1,571,740 B linked flash; 179,680 B static RAM; app/factory images 1,572,144/1,637,680 B; post-warm exact HIL heap total/free 201,772/135,712 B, minimum floor 73,824 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.110.0-wifi-capture`, `E-BUILD-110`/`E-AUTO-074`/`E-HIL-134`/`E-UX-029`/`E-CAPTURE-004`; +1,260 B linked flash, zero static RAM and +1,264/+1,264 B images vs 0.109. The product route reuses the existing bounded 16×256 B capture and single-workspace PCAP/persistence path; it adds no payload buffer. Two physical lifecycles have byte-identical post-warm heap, only live metric rows change, privacy cancel performs zero writes and final lease is 0; IRAM remains full |
| RB-M113 | measured | bounded passive BLE Nearby catalog and direct list/detail UI | 1,579,464 B linked flash; 182,080 B static RAM; app/factory images 1,579,872/1,645,408 B; post-warm exact HIL heap total/free/min 199,372/133,652/60,324 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.111.0-ble-nearby`, `E-BUILD-111`/`E-AUTO-075`/`E-HIL-135`/`E-UX-030`; +7,724 B linked flash, +2,400 B static RAM and +7,728/+7,728 B images vs 0.110. The allocation-free catalog holds at most 32 addresses and updates only changed rows. Two physical lifecycles are byte-identical after warm-up, receive 30 then 32 unique devices with zero drops, keep static chrome and open detail untouched, perform zero writes and finish with lease 0; IRAM remains full |
| RB-M114 | measured | allocation-free descending-signal order for every live radio-object list | 1,578,308 B linked flash; 182,080 B static RAM; app/factory images 1,578,720/1,644,256 B; exact HIL heap total/free/min 199,372/133,652/61,208 B for BLE and 199,372/133,088/61,208 B for both Wi-Fi jobs; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.112.0-signal-order`, `E-BUILD-112`/`E-AUTO-076`/`E-HIL-136`/`E-UX-031`; −1,156 B linked flash, zero static RAM and −1,152/−1,152 B images vs 0.111. Stable insertion sort works in the existing fixed 32-entry arrays; no sort buffer or heap allocation is added. One fresh and two same-hash reuse runs prove all three catalogs strongest-first, zero drops, byte-stable post-warm heap, data-only live redraw and final lease 0; IRAM remains full |
| RB-M115 | measured | compact radio-object facts and shared qualitative/numeric signal meter | 1,578,716 B linked flash; 182,080 B static RAM; app/factory images 1,579,120/1,644,656 B; exact HIL heap total/free/min 199,372/133,652/61,292 B for BLE and 199,372/133,088/61,292 B for both Wi-Fi jobs; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.113.0-dense-details`, `E-BUILD-113`/`E-AUTO-077`/`E-HIL-137`/`E-UX-032`; +408 B linked flash, zero static RAM and +400/+400 B images vs 0.112. One shared renderer and nine localized strings replace three technical counters without dynamic allocation. One fresh and two same-hash reuse runs retain 17 TFT states, byte-stable post-warm heap, zero detail/chrome changes, zero radio drops/writes and final lease 0; IRAM remains full |
| RB-M116 | measured | identity-stable Nearby Networks navigation during live RSSI updates | 1,579,500 B linked flash; 182,312 B static RAM; app/factory images 1,579,904/1,645,440 B; exact Wi-Fi HIL heap total/free/min 199,140/132,888/69,084 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.114.0-stable-network-nav`, `E-BUILD-114`/`E-AUTO-078`/`E-HIL-138`/`E-UX-033`; +784 B linked flash, +232 B static RAM and +784/+784 B images vs 0.113. The fixed 32×BSSID navigation snapshot is allocation-free. One fresh run locks 23 rows, survives eight actions, two more scans and 28 catalog revisions with byte-stable post-warm heap, unchanged order/selection identity, zero chrome/detail changes/writes and final lease 0; IRAM remains full |
| RB-M117 | measured | passive Wi-Fi device fingerprint, full IEEE MA-L lookup and selected-channel live radar | 2,874,880 B linked flash; 198,568 B static RAM; app/factory images 2,875,280/2,940,816 B; exact Wi-Fi HIL heap total/free/min 182,884/116,892/55,004 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.115.0-wifi-device-intelligence`, `E-BUILD-115`/`E-AUTO-079`/`E-HIL-139`/`E-UX-034`; +1,295,380 B linked flash, +16,256 B static RAM and +1,295,376/+1,295,376 B images vs 0.114. The 1,279,488 B pinned IEEE MA-L table is flash-resident and binary-searched without heap; the 32-device catalog retains bounded WPS/SSID/rate/generation/range facts. One fresh run finds 2→3 clients, locks identity/channel 4, receives a selected-client update, keeps passport/chrome stable, performs zero writes and ends lease 0. Minimum free heap is 14,080 B below 0.114 and far below the historical 128 KiB Survey floor, so mixed-workload release endurance remains the authority and future identity fields must not add unbounded memory; IRAM remains full |
| RB-M118 | measured | per-channel session mean, gray/current overlay and mean-based free-channel choice | 2,874,896 B linked flash; 198,800 B static RAM; app/factory images 2,875,296/2,940,832 B; exact Wi-Fi HIL heap total/free/min 182,652/116,660/54,724 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.116.0-wifi-channel-average`, `E-BUILD-116`/`E-AUTO-080`/`E-HIL-140`/`E-UX-035`; +16 B linked flash, +232 B static RAM and +16/+16 B images vs 0.115. Thirteen 64-bit sums with bounded dwell counts and thirteen rendered averages are fixed and allocation-free. A fresh run proves 2→3 complete sweeps, visible gray means, mean-based 1/6/11 recommendation, 509 dynamic/zero static changed pixels, byte-identical post-warm total/free heap, zero writes and final lease 0. The focused minimum is 280 B below 0.115, so accepted mixed-workload release endurance remains authoritative; IRAM remains full |
| RB-M119 | measured | integrated Wi-Fi device identity and selected-channel live signal detail | 2,875,204 B linked flash; 198,800 B static RAM; app/factory images 2,875,360/2,940,896 B; exact Wi-Fi HIL heap total/free/min 182,652/116,660/54,724 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.117.0-wifi-device-live-detail`, `E-BUILD-117`/`E-AUTO-081`/`E-HIL-141`/`E-UX-036`; +308 B linked flash, zero static RAM and +64/+64 B images vs 0.116. Removing the extra radar state adds no buffer or heap allocation. Fresh HIL accepts two selected-client updates on locked channel 12, changes 2,120 live and zero identity/chrome pixels, preserves exact post-warm total/free heap, writes zero bytes and ends lease 0. The 54,724 B focused minimum remains far below the historical 128 KiB Survey floor, so mixed-workload release endurance remains authoritative; IRAM remains full |
| RB-M120 | measured | passive Wi-Fi network passport, vendor lookup and monotonic hidden-SSID enrichment | 2,890,164 B linked flash; 209,200 B static RAM; app/factory images 2,890,320/2,955,856 B; exact Wi-Fi HIL heap total/free/min 172,252/104,532/41,148 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.118.0-wifi-network-intelligence`, `E-BUILD-118`/`E-AUTO-082`/`E-HIL-142`/`E-UX-037`; +14,960 B linked flash, +10,400 B static RAM and +14,960/+14,960 B images vs 0.117. Fixed observation/scan/catalog facts carry auth/ciphers/channel width/PHY/WPS/FTM/antenna/country metadata and reuse the flash-resident 39,984-record MA-L table; fail-closed diagnostic capacity grows by 1 KiB after a retained `state_overflow`. Fresh HIL finds 15→19 networks, validates a Hewlett Packard passport, byte-stable post-warm total/free heap, zero writes and final lease 0. Hidden→known SSID by BSSID is native-tested; the ambient run observed zero resolutions. The 41,148 B focused minimum is 13,576 B below 0.117 and does not supersede mixed-workload release endurance; IRAM remains full |
| RB-M121 | measured | integrated BSSID-bound Wi-Fi network live radar | 2,891,428 B linked flash; 209,464 B static RAM; app/factory images 2,891,840/2,957,376 B; exact Wi-Fi HIL heap total/free/min 171,988/104,256/40,540 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.119.0-wifi-network-live-radar`, `E-BUILD-119`/`E-AUTO-083`/`E-HIL-143`/`E-UX-038`; +1,264 B linked flash, +264 B static RAM and +1,520/+1,520 B images vs 0.118. The dominant RAM delta is 32 fixed signal-stat records that move with their BSSID slots; sample count, min/max and latest trend are allocation-free and reset on task entry. Fresh HIL advances a real Keenetic record 4→5 samples and −71→−70 dBm, changes 86 radar/zero outside pixels, preserves byte-identical post-warm total/free heap, writes zero bytes and ends lease 0. The focused minimum is 608 B below 0.118 and does not supersede mixed-workload release endurance; IRAM remains full |
| RB-M122 | measured | all-channel visible-mean Wi-Fi recommendation and selected-axis highlight | 2,891,648 B linked flash; 209,464 B static RAM; app/factory images 2,892,048/2,957,584 B; exact Wi-Fi HIL heap total/free/min 171,988/104,460/40,464 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.120.0-wifi-channel-choice`, `E-BUILD-120`/`E-AUTO-084`/`E-HIL-144`/`E-UX-039`; +220 B linked flash, zero static RAM and +208/+208 B images vs 0.119. Ranking reuses the existing 13 fixed means, computes adjacent pressure on the stack and stores no new state. Fresh HIL measures all channels, recommends/highlights 13 after 2 and 3 sweeps, changes 1,195 dynamic/zero unrelated static pixels, preserves byte-identical post-warm total/free heap, writes zero bytes and ends lease 0. The focused minimum is 76 B below 0.119 and does not supersede mixed-workload release endurance; IRAM remains full |
| RB-M123 | measured | channel-neutral Wi-Fi current-load bar palette | 2,891,644 B linked flash; 209,464 B static RAM; app/factory images 2,892,048/2,957,584 B; exact Wi-Fi HIL heap total/free/min 171,988/104,460/34,996 B; RTC no-init 108 B; IRAM 16,384/16,384 B | board-01 `0.121.0-wifi-channel-neutral-bars`, `E-BUILD-121`/`E-AUTO-085`/`E-HIL-145`/`E-UX-040`; −4 B linked flash, zero static RAM/image growth vs 0.120. Removing channel identity from the color function adds no state or allocation. Fresh HIL measures all 13 channels, recommends 13 after 2 and 3 sweeps, changes 998 live/zero static pixels, preserves byte-identical post-warm total/free heap, writes zero bytes and ends lease 0. Focused minimum does not supersede mixed-workload release endurance; IRAM remains full |
| RB-M124 | measured | passive BLE advertisement intelligence, company lookup and integrated radar | 3,049,684 B linked flash; 228,688 B static RAM; app/factory images 3,050,096/3,115,632 B; exact BLE HIL heap total/free/min 152,764/82,248/9,760 B; dedicated DIRAM 309,456/341,760 B (90.55%, 32,304 B remaining) | board-01 `0.122.2-ble-device-intelligence`, `E-BUILD-122`/`E-AUTO-086`/`E-HIL-146`/`E-UX-041`; +158,040 B linked flash, +19,224 B static RAM and +158,048/+158,048 B images vs 0.121. A 128,384 B flash asset holds 4,012 assigned companies; bounded advertisement facts widen shared Observation/queue/session/catalog state. Two physical lifecycles have byte-identical post-warm heap, zero drops/writes and final lease 0, but the 9,760 B historical minimum is far below RB-04. This focused functional checkpoint explicitly does not supersede accepted 0.89 endurance; mixed-workload memory consolidation and a new release-budget run are required after the baseline feature set changes |
| RB-M125 | measured | passive all-receiver nRF24 signal finder | 3,055,192 B linked flash; 229,448 B static RAM; app/factory images 3,055,600/3,121,136 B; exact nRF24 HIL heap total/free/min 152,004/81,772/67,540 B; dedicated DIRAM 310,216/341,760 B (90.77%, 31,544 B remaining) | board-01 `0.123.0-nrf24-signal-finder`, `E-BUILD-123`/`E-AUTO-087`/`E-HIL-147`/`E-UX-042`; +5,508 B linked flash, +760 B static RAM and +5,504/+5,504 B images vs 0.122.2. Fixed 83-bin baseline/response state, product route, diagnostics and HIL surface remain allocation-free. Focused physical minimum stays below RB-04 and does not supersede mixed-workload release endurance |
| RB-M126 | measured | passive wide-span CC1101 frequency finder with robust ambient rejection | 3,060,648 B linked flash; 233,288 B static RAM; app/factory images 3,061,056/3,126,592 B; exact CC1101 HIL heap total/free/min 148,164/77,932/63,700 B; dedicated DIRAM 314,056/341,760 B (91.89%, 27,704 B remaining) | board-01 `0.124.1-cc1101-frequency-finder`, `E-BUILD-124`/`E-AUTO-088`/`E-HIL-148`/`E-UX-043`; +5,456 B linked flash, +3,840 B static RAM and +5,456/+5,456 B images vs 0.123. Three fixed 1,099-bin arrays (baseline, raw rise and held response), 240-column projection and diagnostics are allocation-free. Two ambient runs preserve heap, reject retained predecessor false peaks and end lease 0. Focused minimum stays below RB-04 and does not supersede mixed-workload release endurance |
| RB-M127 | measured build / physical open | product IR Library metadata plus separate two-board NEC fixture foundation | product 3,061,504 B linked flash; 233,288 B static RAM; app/factory images 3,061,904/3,127,440 B; dedicated DIRAM unchanged at 314,056/341,760 B (91.89%, 27,704 B remaining). Separate fixture: 322,215 B linked flash; 22,724 B static RAM; app/factory 322,624/388,160 B; DIRAM 74,519/341,760 B | unflashed source `0.125.0-ir-fixture-foundation` / fixture `0.1.0-ir-nec`, `E-BUILD-125`/`E-AUTO-089`, source `f1b3394`; product delta vs 0.124.1 is +856 B linked flash, zero static RAM and +848/+848 B images. The separate fixture budget never enters the product image. No physical heap or two-board result exists yet, so RB-04 and accepted 0.89 endurance are not superseded |
| RB-M128 | measured build + physical positive | pre-app safety guard, physical IR envelope tolerance and closed-loop two-board NEC | product 3,062,560 B linked flash; 233,288 B static RAM; app/factory images 3,062,960/3,128,496 B; RTC no-init 128 B; physical heap total/free/min 148,164/77,932/63,700 B. Fixture remains 322,215 B linked flash and 22,724 B static RAM | board-01/02 `0.129.0-pre-app-watchdog`, `E-BUILD-129`/`E-AUTO-093`/`E-HIL-150`/`E-RADIO-014`/`E-STORAGE-031`; +1,056 B linked flash, zero static-RAM growth and +1,056/+1,056 B images vs 0.125. The physical run keeps heap invariant across NEC receive/save/cold reopen, but its 63,700 B focused minimum is below RB-04 and does not replace mixed-workload endurance |
| RB-M129 | measured diagnostic build + physical localization | isolated-main shared-MISO characterization with all receiver operations suppressed | product-derived diagnostic 3,063,436 B linked flash; 233,288 B static RAM; app/factory images 3,063,840/3,129,376 B; dedicated DIRAM 314,056/341,760 B (91.89%, 27,704 B remaining); isolated physical heap total/free/min 148,164/78,440/78,440 B | board-02 `0.131.0-isolated-main-miso`; +876 B linked flash, zero static RAM and +880/+880 B images vs exact product 0.129. The retained run samples GPIO13 only, clocks zero SPI bytes, performs zero receiver/TX operations and ends Home/lease 0. Its higher focused heap minimum is diagnostic-only and does not promote the product or supersede RB-04/mixed-workload release endurance |
| RB-M130 | measured build + focused physical safety | allocation-free deadline state and first Product Survey Wi-Fi worker trip/restart/clear | 3,066,128 B linked flash; 233,360 B static RAM; app image 3,066,528 B; boot-before exact HIL heap total/free/min 148,092/77,860/63,628 B | board-01 `0.133.0-worker-deadline-supervision`, `E-BUILD-133`/`E-AUTO-094`/`E-HIL-154`/`E-SAFETY-002`; +3,568 B linked flash and +72 B static RAM versus exact product 0.129. One Wi-Fi worker arm/two heartbeats/one trip cleanly releases lease and survives restart. This fault-focused run neither exercises a normal mixed Survey workload nor supersedes RB-04/release endurance |
| RB-M131 | measured build + normal/fault-focused physical safety | BLE-calibrated Product Survey deadline with normal cycle plus trip/restart/clear | 3,066,124 B linked flash; 233,360 B static RAM; app image 3,066,528 B; boot-before exact HIL heap total/free/min 148,092/77,860/63,628 B | board-01 `0.134.0-ble-worker-deadline`, `E-BUILD-134`/`E-AUTO-095`/`E-HIL-155`/`E-SAFETY-003`; −4 B linked flash and zero static-RAM/image delta versus 0.133. One normal BLE cycle accepts 34/34 with zero drops/retries and no false trip under a 6.1 s bound below the 8 s deadline; the second lifecycle trips at 8,001 ms and cleanly releases lease. This focused run does not exercise a normal mixed Survey workload or supersede RB-04/release endurance |

| RB-M132 | measured build + normal/fault-focused physical safety | Product Survey preparation/admission deadline before the calibrated Wi-Fi+BLE worker boundary | 3,067,656 B linked flash; 233,360 B static RAM; app image 3,068,064 B; boot-before exact HIL heap total/free/min 148,092/77,860/63,628 B | board-01 `0.135.0-survey-preparation-deadline`, `E-BUILD-135`/`E-AUTO-096`/`E-HIL-156`/`E-SAFETY-004`; +1,532 B linked flash, +1,536 B image and zero static-RAM delta versus 0.134. A normal BLE lifecycle arms preparation then worker, accepts 30/30 with zero scan drops/retries and no false trip; a pre-hardware 10 s stall trips preparation at 8,001 ms and cleanly releases lease. This focused run does not exercise a normal mixed Survey workload or supersede RB-04/release endurance |
| RB-M133 | measured build + normal/fault-focused physical safety | Wi-Fi Capture Store worker deadline plus no-PSRAM workspace consolidation | 3,059,360 B linked flash; 207,928 B static RAM; app image 3,059,760 B; boot-before exact HIL heap total/free/min 173,524/103,248/89,060 B | board-01 `0.136.0-capture-store-deadline`, `E-BUILD-136`/`E-AUTO-097`/`E-HIL-157`/`E-SAFETY-005`; −8,296 B linked flash, −25,432 B static RAM and −8,304 B image versus 0.135. Lifecycle-exclusive Session/FatFs workspaces are shared. Normal Capture Store mounts with 93,544 B free heap, 32,756 B largest block and error zero, saves 2 frames/433 B and advances generation 98→99; a pre-storage 10 s stall trips at 8,001 ms with zero writes and cleanly releases lease. This focused run does not exercise a normal mixed workload or supersede RB-04/release endurance |
| RB-M135 | measured build + normal/fault-focused physical safety | IR Capture Store worker deadline plus no-OS Safe Mode restart | 3,061,508 B linked flash; 207,960 B static RAM; app/factory images 3,061,920/3,127,456 B; normal pre-mount heap free/largest 94,136/51,188 B | board-01 `0.138.0-safety-restart-noos`, `E-BUILD-138`/`E-AUTO-099`/`E-HIL-159`/`E-SAFETY-006`; +12 B linked flash, zero static RAM and +16/+16 B image versus 0.137. Normal NEC Save advances generation 106→107; a pre-storage 10 s stall trips at 8,001 ms with zero writes, no-OS restart returns in 947.445 ms and final lease is zero. This focused run does not exercise a normal mixed workload or supersede RB-04/release endurance |

The probe's `heap_min_free` covers only its short diagnostic run. It does not predict
Wi-Fi/BLE buffers, display caches, Session queues, storage transactions, or the
≥45-minute/≥8-cycle Survey gate. The 0.x figure includes legacy functionality and feasibility
contracts, so it cannot define the clean platform shape.

## Provisional 1.x guardrails

These limits are review triggers, not evidence that the product meets its NFRs.

| ID | Guardrail | Rationale / closure |
|---|---|---|
| RB-01 | No required path may depend on PSRAM | board-01/BOM define N16/no-PSRAM; board-02 N16R8 memory collides with display pins and therefore confirms that ROM capacity alone cannot expand the portable envelope |
| RB-02 | Keep two bootable app slots and at least 12.5% free space in either selected slot | preserves OTA/rollback and growth; final values require the partition ADR |
| RB-03 | Clean S2 platform: static RAM ≤ 96 KiB and free internal heap ≥ 240 KiB after interactive boot | leaves room for the first radio/storage slice; measure on the independent target |
| RB-04 | S3 passive Survey steady state: free internal heap ≥ 160 KiB and minimum ≥ 128 KiB with no downward trend across ≥45 minutes and ≥8 complete release cycles | reserves bounded worker/parse/export headroom; close within the one-hour endurance budget using heap time series and queue high-water marks |
| RB-05 | Interactive UI ≤ 2 s after cold boot; UI callbacks ≤ 10 ms; Back/lease release ≤ 150 ms | existing NFR-001…003; close with device timestamps and external HIL timing |
| RB-06 | Sustained storage throughput ≥ 4× measured p99 ingress of the selected source set; commit/power-cut must preserve all prior committed records | avoids an arbitrary SD-only number; measure source rate, SD and LittleFS separately |
| RB-07 | A 10,000-transition radio→storage→radio test has zero bus errors, all non-owner CS lines inactive, and zero leaked leases | closes transaction policy only with HW-T03/HW-T05 trace evidence |
| RB-08 | No unmeasured receiver combination is enabled by default; accepted combinations must complete endurance without brownout/reset and stay inside measured regulator/thermal limits | power numbers require HW-T10; unavailable equipment narrows scope rather than inventing capacity |

## Measurement closure matrix

| Area | Current state | Next reproducible measurement | Gate impact |
|---|---|---|---|
| Flash/static RAM | platform/runtime through exact 0.104, Survey UI, codec, SessionStore v6 including RAW/IR pulses, persistent Library/export, SD metadata, guarded FAT persistence/reset/power-cut, Wi-Fi/BLE, receiver views, safety supervisor and passive IR capture are measured; exact 0.104 uses 172,760 B static RAM and 1,549,056 B linked flash inside the 4 MiB app slot, but the dedicated 16,384 B IRAM region has zero remaining bytes | recover or explicitly rebudget IRAM before any further ISR-resident code; retain exact size/map deltas as S5 adds complete module workflows without moving the product partition | S1 lower bound; S2–S4 accepted; S5 tracked with a critical IRAM headroom constraint |
| Runtime heap/queues | lease lifecycle is measured over 1,000 UI cycles; exact 0.89 passes 8 complete Wi-Fi+BLE→SD→Library cycles in 2,799.845 s with 367 forwarded observations, zero drops and invariant heap 231,772/166,812/147,460 B | keep the exact-candidate check in every release workflow and extend it only when a newly enabled source changes the workload | RB-04 and the S4 endurance gate are accepted |
| Boot/UI latency | capability-built home interactive-ready 0.373 s and TFT capture measured | measure external cold power-on and later product services, not only device milestone | blocks final NFR-001 verification, not S2 bootstrap |
| Storage throughput/atomicity | bounded SessionStore matrices, guarded FAT/remount/reset, isolated LittleFS recovery, exact 0.89 endurance and exact 0.101 six-boundary physical power-cut are measured; exact 0.102 host-tests schema-v5 RAW pulse commit/reopen/corrupt rejection and its physical no-save path leaves product 95/0 unchanged with zero writes | prove a known physical RAW burst through explicit atomic save and cold Library CSV, then repeat common recovery evidence only when the shared store/media policy changes | PR-005/RB-06 S4 slice is accepted for one board/card; CAP-030 persistence and S8 release-candidate recovery remain open |
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
  concurrent workers require a separate map/release-endurance review; an extended
  8 h qualification is optional after major storage/runtime/radio changes.
- Storage, power, and shared-bus limits remain explicit unknowns; features depending
  on them cannot be promoted from `unknown` to `available` by documentation alone.

Latest build delta `RB-M133`: exact 0.136 uses 3,059,360 B linked flash and 207,928 B
static RAM; its app image is 3,059,760 B. This is −8,296 B linked flash, −25,432 B
static RAM and −8,304 B image versus 0.135. The reduction aliases only workspaces
whose owning lifecycles are mutually exclusive: Survey/diagnostic Session and
product/diagnostic FatFs. Boot-before heap rises to 173,524/103,248/89,060 B. The
normal Capture Store reaches mount with 93,544 B free and a 32,756 B largest block,
reports mount error zero, persists 2 frames/433 B and advances generation 98→99.
The injected pre-storage path trips at 8,001 ms before any physical write. It does
not execute a normal mixed workload. Exact 0.129 remains the physical functional
baseline; RB-04 plus mixed-workload release endurance remain the resource/release
baseline.

The source-bound `0.2.4` diagnostic fixture uses 332,135 B program flash and 22,844 B
static RAM. Its +9,920/+120 B delta over the fixed-NEC fixture adds read-only identity
telemetry for all nRF chip selects, both data-pin orientations and shared-bus CC1101;
it does not enter or change the exact product image. The physical 2/2-step diagnostic
performs zero emissions and retains no runtime-heap claim; its negative receiver
inventory is recorded in
[board-02 evidence](../../tests/hil/evidence/board-02-rf-shield-inventory-0.2.4.json).

Latest candidate delta `RB-M134`: exact 0.137 uses 3,061,496 B linked flash,
207,960 B static RAM and a 3,061,904 B app image. This is +2,136/+32/+2,144 B
versus 0.136 for the shared IR/Sub-GHz Store deadline, cancel and telemetry path.
Fixture 0.2.5 uses 332,247 B linked flash, 22,844 B static RAM and a 332,656 B
image. Its +112 B linked-flash delta over 0.2.4 gives the physically shared GPIO14
IR/CE3 pad one LEDC-safe owner and adds a source guard. These are build facts only:
the current physical IR station gate remains fail-closed.

Latest accepted delta `RB-M135`: exact 0.138 uses 3,061,508 B linked flash,
207,960 B static RAM and app/factory images 3,061,920/3,127,456 B. This is
+12/0/+16/+16 B versus 0.137 for replacing both Safe Mode software restarts with
the no-OS primitive. The normal IR Save reaches the storage boundary with
94,136 B free heap and a 51,188 B largest block; the injected path writes zero
bytes and does not claim a mount allocation. This is physical safety evidence,
not mixed-workload resource or release endurance.

Latest accepted delta `RB-M136`: exact 0.139 uses 3,078,272 B linked flash,
208,304 B static RAM and app/factory images 3,078,768/3,144,304 B. This is
+16,764/+344/+16,848/+16,848 B versus 0.138 for the power safety policy, explicit
assembly profile, real light-sleep/resume reporting, truthful Power UI and bounded
HIL-only RX fixture. The fresh board-01 runtime gate starts at heap
total/free/minimum 171,012/100,736/86,548 B; 300 ms light sleep preserves both
free/minimum values exactly. The authorized Sub-GHz Store reaches mount with
91,656 B free and a 49,140 B largest block and advances catalog 109→110. The
low-voltage path opens no filesystem and performs zero writes. This is a focused
runtime checkpoint, not mixed-workload or release endurance, and it does not add a
physical positive-RF claim.

Latest accepted delta `RB-M137`: exact 0.140 uses 3,084,428 B linked flash,
210,984 B static RAM and app/factory images 3,084,592/3,150,128 B. This is
+6,156 B linked flash, +2,680 B static RAM and +5,824/+5,824 B images versus
0.139 for the OOK/FSK chooser, bounded 512-event GDO0 capture state, CC1101
asynchronous receive registers and diagnostics. Dedicated DIRAM is
294,164/341,760 B (86.07%, 47,596 B remaining); the dedicated IRAM region remains
exactly 16,384/16,384 B with no headroom. The one-flash board-01 delta preserves
heap total/free/minimum exactly at 168,076/97,800/83,612 B across FSK and adjacent
OOK no-signal lifecycles, with zero storage/TX side effects. It is not a physical
positive-RF or mixed-workload release budget. Compact retention reduces the checked
HIL bundle from 45,818,642 B to less than 1 MiB without discarding run, PNG or
source/artifact identities.

Latest accepted delta `RB-M138`: exact 0.144 uses 3,087,248 B linked flash,
211,208 B static RAM and app/factory images 3,087,744/3,153,280 B. This is
+2,820 B linked flash, +224 B static RAM and +3,152/+3,152 B images versus
0.140 for the plan-v10 Full/Guided receiver and artifact execution, split
current-free/boot-lifetime-minimum heap gates and applicability-aware PCAP audit.
Dedicated DIRAM is 294,388/341,760 B (86.14%, 47,372 B remaining); dedicated
IRAM remains exactly 16,384/16,384 B with no headroom. The accepted board-01
delta starts with 167,852 B total heap and finishes Full with 96,880 B free and
a 63,848 B boot-lifetime minimum, leaving 14,960 B above the 80 KiB current-free
gate and 14,696 B above the 48 KiB minimum gate. It runs bounded receive work on
three nRF24 modules, CC1101, OOK, FSK and IR plus read-only product and disposable
artifact audits; product generation 110/zero observations remains unchanged,
product writes and radio TX remain zero, and the 505 B scratch is removed. This
focused delta is not a mixed-workload release budget and does not replace the
stage-end matrix or a qualified physical RF-positive gate.

Latest accepted delta `RB-M139`: exact 0.145 uses 3,089,868 B linked flash,
211,224 B static RAM and app/factory images 3,090,368/3,155,904 B. This is
+2,620 B linked flash, +16 B static RAM and +2,624/+2,624 B images versus
0.144 for persistent EN/RU language, five brightness levels, the runtime
Forest/High Contrast semantic palette and a fail-closed unavailable Sound row.
Dedicated DIRAM is 294,404/341,760 B (86.14%, 47,356 B remaining); dedicated
IRAM remains exactly 16,384/16,384 B with no headroom. One-flash board-01 HIL
and two physical hard resets prove changed preferences survive reboot and the
restored RU/100%/Forest values persist again. The run issues zero radio TX,
keeps buzzer and nRF CE inactive, reports zero input errors/drops and finishes
Home/none/lease 0. This focused interface delta does not replace the stage-end
matrix or qualified physical RF-positive gate.

Test-only fixture measurement `RB-M140`: fixture `0.3.0-subghz-safe` at source
`4f97b3a751b96c7573c056d4ac7562ef410c06cc` uses 335,955 B linked flash,
22,876 B static RAM and app/factory images 336,352/401,888 B. Dedicated
DIRAM is 74,687/341,760 B and IRAM is exactly 16,384/16,384 B. Firmware,
factory, ELF and map hashes are
`32f3619f66beeacbd3e05b1148699494cc808a24b4779f4ded2d131c0f2ffb9c`,
`98b712c4f1979506e010c37e748b4f7d4aba4fc2a7ebfb04874479483e4b6586`,
`72dd88393fe1cbe9c3ef3f50e31f353ce6ffd883cd922429ed956b85d91c5798` and
`bd4d6582339441c9818525713467b64c85cb5997755157c351718d7d3ce65b35`.
This separate test image does not change the product budget and its passing build
does not constitute physical RF evidence.

Host/build Target-foundation measurement `RB-M141`: `E-TARGET-002` uses
3,090,668 B linked flash, 211,224 B static RAM and app/factory images
3,091,168/3,156,704 B. This is +800 B linked flash, zero static-RAM growth and
+800/+800 B images versus exact 0.145 for deterministic Target CBOR/manifest,
exact Observation admission and the reusable two-head Target journal. Dedicated
DIRAM remains 294,404/341,760 B (86.14%, 47,356 B remaining); dedicated IRAM
remains exactly 16,384/16,384 B. The ≤16 KiB `TargetCatalog`, 16 KiB codec
workspace and explicit recovery scratch are lifecycle-owned objects and are not
yet instantiated as permanent product globals; S6.4 product integration must
measure their live heap/static placement. This is host/build evidence, not HIL.

Host/build explainable-correlation measurement `RB-M142`: `E-CORR-001` uses
3,090,892 B linked flash, 211,224 B static RAM and app/factory images
3,091,392/3,156,928 B. This is +224 B linked flash, zero static-RAM growth and
+224/+224 B images versus `E-TARGET-002`; the correlation code is compiled but
its bounded service/log are not yet permanent product globals. Dedicated DIRAM
remains 294,404/341,760 B (86.14%, 47,356 B remaining), and dedicated IRAM
remains exactly 16,384/16,384 B. `CorrelationDecisionLog` is host-guarded at
≤16 KiB and contains at most 32 immutable decisions; S6.2 persistence and S6.4
runtime integration must measure its retained-storage and live placement costs.
This is host/build evidence, not HIL.

Host/build atomic Target-state measurement `RB-M143`: `E-CORR-002` uses
3,091,340 B linked flash, 211,224 B static RAM and app/factory images
3,091,840/3,157,376 B. This is +448 B linked flash, zero static-RAM growth and
+448/+448 B images versus `E-CORR-001` for deterministic schema-v2 encoding of
the Target graph and full decision history plus a dedicated six-boundary
dual-head journal. Dedicated DIRAM remains 294,404/341,760 B (86.14%, 47,356 B
remaining), and dedicated IRAM remains exactly 16,384/16,384 B. The 32 KiB
`TargetStateStoreWorkspace`, catalog and decision-log recovery scratch remain
explicit lifecycle-owned objects rather than permanent product globals; S6.4
runtime integration must measure their live placement and migration cost. This
is host/build evidence, not HIL.

Host/build reversible-Target measurement `RB-M144`: `E-CORR-003` uses
3,091,516 B linked flash, 211,224 B static RAM and app/factory images
3,092,016/3,157,552 B. This is +176 B linked flash, zero static-RAM growth and
+176/+176 B images versus `E-CORR-002` for schema-v1 merge/split Actions,
bounded graph restoration and schema-v3 atomic merge-history persistence.
Dedicated DIRAM remains 294,404/341,760 B (86.14%, 47,356 B remaining), and
dedicated IRAM remains exactly 16,384/16,384 B. `TargetMergeHistory` is 11,528 B
and bounded to eight complete two-Target snapshots; it, the 32 KiB state
workspace, catalog and decision log remain lifecycle-owned rather than permanent
product globals. S6.4 runtime integration must measure their live placement and
migration cost. This is host/build evidence, not HIL.

Host/build Target-comparison measurement `RB-M145`: `E-CORR-004` uses
3,091,760 B linked flash, 211,224 B static RAM and app/factory images
3,092,256/3,157,792 B. This is +244 B linked flash, zero static-RAM growth and
+240/+240 B images versus `E-CORR-003` for the read-only schema-v1
`target.compare` Action, exact two-Session lookup and bounded classification.
Dedicated DIRAM remains 294,404/341,760 B (86.14%, 47,356 B remaining), and
dedicated IRAM remains exactly 16,384/16,384 B. `TargetComparisonResult` is
7,736 B and holds at most 16 rows with four exact evidence references per side;
it remains lifecycle-owned and is not a permanent product global. S6.4 must
measure the combined live placement of Target state, two recovered Sessions and
the Compare view model. This is host/build evidence, not HIL.

On-device Targets measurement `RB-M146`: exact production
`0.146.0-targets` uses 3,108,996 B linked flash, 211,296 B static RAM and
app/factory images 3,109,152/3,174,688 B. Against exact accepted 0.145 this is
+19,128 B linked flash, +72 B static RAM and +18,784/+18,784 B images for
read-only pair recovery, bounded admission and the List/Compare/Detail product
route. Dedicated DIRAM is 294,476/341,760 B (86.16%, 47,284 B remaining), and
dedicated IRAM remains exactly 16,384/16,384 B. The foreground workspace is
22,544 B steady: 19,008 B of target/view state plus the 3,536 B controller. It
reuses the already lifecycle-owned Survey/Library Session buffers, while an
11,272 B scratch catalog exists only during atomic admission and is released
before rendering. Firmware/factory/ELF/map SHA-256 are
`f115f46b0e5e587ac1e1a4c83745c9f6d53818fd0c468de2adecf0bc99e1211c`/
`db8a396cf272e67662d31eb0ad13ddd890d36d85ed72e1402ad5e13ab32494c9`/
`d8d364734661e0c0b18c700cce1e16600a8e51ca318cf20f1053cec4f206ab0a`/
`b134c373147f553ba5aac2a8a511a726454c502a48ff82175bb9ecaf7fbba7ff`.
The corresponding physical rejection is retained as
[E-HIL-164](../../tests/hil/evidence/board-01-targets-stack-failure-0.146.json);
these size figures remain host/build evidence rather than an acceptance claim.

Targets stack-safety correction `RB-M147`: exact production
`0.147.0-targets-stack-safe` uses 3,107,636 B linked flash, 211,296 B static
RAM and app/factory images 3,108,144/3,173,680 B. Dedicated DIRAM remains
294,476/341,760 B (86.16%, 47,284 B remaining), and dedicated IRAM remains
16,384/16,384 B. The 7,736 B result now stays in the foreground workspace;
two comparison-side snapshots use 1,616 B of checked transient heap and
automatic release.
Native `-fstack-usage` measures 112 B at `compareTargetSessionsInto`, 1,088 B
at `buildSide`, and 496 B at the calling `TargetsController::loadBindings`.
Removing the duplicate Wi-Fi-menu PCAP route and adding the public persistent
Record visit route leaves static RAM unchanged and reduces linked flash by
1,360 B versus the failed 0.146 precursor. Firmware/factory/ELF/map SHA-256 are
`57b5fea451ed957a68c67f98a2d7964dfcf64007261d3bc580f8ba71b6808164`/
`2716812e80c6a728b85c813f911aa9a6c25ce173eb4fec482bb61bf041441b31`/
`f7a87222d5720109b5149623b95f6a7c4f6070a1dedb66de163f9768f9e89aaf`/
`9873506a75583169c08de1ddd9ac3f8c401de6d0f33f51e4cf5048c15626cf9d`.
This is host/build evidence pending the focused stack-canary regression.

Targets storage-order correction `RB-M148`: production
`0.148.0-targets-storage-order` uses 3,107,844 B linked flash, 211,296 B
static RAM and 3,108,352/3,173,888 B app/factory images. Dedicated DIRAM and
IRAM remain 294,476/341,760 B and 16,384/16,384 B. Firmware/factory/ELF/map
SHA-256 are
`6847673339df14538ddce4eb57f044088df825a20645f06f273e765187de066a`/
`65b0711a5940a9a863870efe7c5b37578f9af89728c52ed96873c24051096222`/
`57785567646cb45a2c885fbd71ca365b05e08084c34f56e4189ec4b1875f252f`/
`393cffd5859ed61845192464484a031f37e3e49874e3f13efa7961f1572d7397`.
The physical 0.147 precursor first proved the stack correction, then failed
read-only mount after workspace allocation; that distinct result is retained
fail-closed in
[E-HIL-165](../../tests/hil/evidence/board-01-targets-readonly-mount-failure-0.147.json).
The 0.148 path now recovers the exact-CID Session pair and closes FAT/SPI before
allocating the unchanged 22,544 B Targets workspace. This is host/build
evidence pending the gated short physical mount regression.

Targets in-place reset correction `RB-M149`: production
`0.149.0-targets-inplace-reset` uses 3,107,472 B linked flash, 211,296 B
static RAM and 3,107,968/3,173,504 B app/factory images. Dedicated DIRAM and
IRAM remain 294,476/341,760 B and 16,384/16,384 B. Firmware/factory/ELF/map
SHA-256 are
`743f31614df8891667293fdf755c7e53b9b4fc6ce105bc48d8a84a76d1e9c653`/
`9eeca0ecd29c7fdefe2315428f2fd3f01d5f232829af5926250d9a4aab0e9a37`/
`3293c8328bf946843c0035df7516fa47b8363d207acface51416967d51be62e9`/
`8fef982fadc2253d7a64ae01d272965d8bd29c701654d95b128c552f8c202051`.
Exact linked disassembly proves stack frames of 256 B for controller reset,
416 B for load bindings, 32 B for in-place result reset, 80 B for comparison
and 1,104 B for the deepest evidence builder. Both physical runners perform
this ELF check before flashing. The source contract rejects aggregate reset of
the 7,736 B result. Exact 0.149 physical acceptance then preserves
97,488/97,488 B before/after the short workspace and 96,452/96,452 B before/after
the full-delta workspace; both finish with lease zero in `E-HIL-167`.

Targets row-evidence checkpoint `RB-M150`: production
`0.150.0-targets-evidence` uses 3,112,664 B linked flash, unchanged 211,296 B
static RAM and 3,113,168/3,178,704 B app/factory images. This is +5,192 B linked
flash and +5,200/+5,200 B images versus 0.149, with zero static-RAM growth, for
class/signal order, selectable comparison rows, exact evidence detail, UTF-8-safe
pixel fitting and list-band incremental cleanup. Firmware/factory/ELF/map SHA-256
are
`bbb200a5a9ca4b8c1cd60dcdd665ec64eea70ecb2a4d0244ff642df240268e65`/
`37da3aaf7fe3a7101ab772e29020e901e619990154cbba40016edd8ec9b53dce`/
`e91cad765c55c08dc317e4099e173423a18af4aeba323f824b1759e3b8caae56`/
`5599e1d0835f81458d1647b31ed3a40d0fe5e67d55bab7d47f95a50a0516ae9c`.
Linked disassembly additionally bounds comparison-side loading at 272 B,
row ordering at 32 B and row comparison at 480 B; the prior 256/416/32/80/1,104 B
frames remain within their gates. Exact one-flash physical acceptance keeps the
22,544 B workspace lifecycle-owned, preserves 97,488/97,488 B before/after release
and ends at lease zero in `E-HIL-168`.

Targets Favorite checkpoint `RB-M151`: exact production
`0.151.2-targets-favorite-compact` uses 3,128,500 B linked flash, 211,512 B
static RAM and 3,129,008/3,194,544 B app/factory images. This is +15,836 B
linked flash, +216 B static RAM and +15,840/+15,840 B images versus 0.150 for
the Actions view, typed mutation service, schema-v3 catalog persistence and an
8 s supervised storage worker. Dedicated DIRAM is 294,692/341,760 B (86.23%,
47,068 B remaining); dedicated IRAM remains 16,384/16,384 B. The existing
22,544 B foreground Targets workspace remains lifecycle-owned. The mutation
allocates a separate 16,384 B catalog-only workspace before FAT mount; on the
real no-PSRAM board it sees 76,152 B free and a 34,804 B largest block, then
returns heap to 97,012 B after exit. Exact HIL records 148 µs UI acknowledgement,
2,689,541 µs worker time, 1,688 logical bytes, three writes plus three file and
three directory syncs, generation 1→2 and cold reopen. Firmware/ELF/map SHA-256
are `62a300adeb76514719a93de58757a78537a14766243140024920ebcd01d9dfee`/
`bab922a10e4dd6d1ddf0215f0ec9cb97c85379da37cdebe61941884378ada0e5`/
`7a7c598338633c0e6dae8ac7736be35021e6ecf6df36271e0510879583744c49`.
Two preceding 32 KiB allocation attempts fail before any write and are retained
with the accepted run in `E-HIL-169`.

Targets Name checkpoint `RB-M152`: exact production
`0.152.0-targets-name-edit` uses 3,131,792 B linked flash, 211,624 B static RAM
and 3,132,288/3,197,824 B app/factory images. This is +3,292 B linked flash,
+112 B static RAM and +3,280/+3,280 B images versus 0.151.2 for the bounded
name editor, its touch/key rows, strings and state probe. Dedicated DIRAM is
294,804/341,760 B (86.26%, 46,956 B remaining); dedicated IRAM remains
16,384/16,384 B. Both the 22,544 B foreground Targets workspace and separate
16,384 B catalog-only mutation workspace retain their existing lifecycle.
Exact HIL sees 75,992 B free and a 34,804 B largest block before mount, returns
heap from 85,072 B to 96,852 B after release, and records 155 µs UI
acknowledgement, 2,824,907 µs worker time, 1,689 logical bytes, three writes,
three file syncs and three directory syncs. Generation advances exactly 2→3
and physical cold reopen preserves name bytes `41` on the same Target ID.
Firmware/ELF/map SHA-256 are
`0599cb880921ec5cb11d39a681e64a324acc84f048f7dedfacae4ff200703506`/
`075a137a5b0cbe0dba1428e30f9fc223e59c940da87d3ca971406ea5f53941dd`/
`c52778fcfd8619a5847de5fb04ceddfeeccb5fcd1ff546a75a00792f4817198f`.
The exact one-flash delta and five reviewed TFT states are retained in
`E-HIL-170`; the cadence advances to 7/15 without a full physical matrix.

Targets Tags checkpoint `RB-M153`: exact production
`0.153.0-targets-tags-edit` uses 3,135,372 B linked flash, 211,624 B static RAM
and 3,135,872/3,201,408 B app/factory images. This is +3,580 B linked flash,
zero static RAM and +3,584/+3,584 B images versus 0.152 for the bounded tag
list/editor, add/remove Actions, strings, state probe and delta runner. Dedicated
DIRAM remains 294,804/341,760 B (86.26%, 46,956 B remaining); dedicated IRAM
remains 16,384/16,384 B. The 22,544 B foreground Targets workspace and separate
16,384 B catalog-only mutation workspace retain their existing lifecycle; the
state probe reuses the existing static diagnostic JSON buffer rather than adding
a loop-stack workspace. Exact HIL sees 75,992 B free and a 34,804 B largest block
before both mounts, returns heap from 85,072 B to 96,852 B, and records UI/worker
times of 158/2,914,830 µs for add and 141/2,918,739 µs for remove. Both mutations
use three writes, three file syncs and three directory syncs; generations advance
3→4→5, with a physical cold reopen after each transition. Firmware/ELF/map
SHA-256 are
`b9a49fe887baf595da01ea798eb1efa8dada57c5ac20af090f467fcb7b688651`/
`49d9c7cbb058158bda4ef19c88e6cfbf56c05f38b4a055e616841cb4091a0d56`/
`0cdaa2ec9f4874991d5c9738f876f7f87fe6e4f96064dd42f3c0685273a3adde`.
The one-flash delta and seven reviewed TFT states are retained in `E-HIL-171`;
the cadence advances to 8/15 without a full physical matrix.

Targets Notes checkpoint `RB-M154`: exact production
`0.154.0-targets-notes-edit` uses 3,138,180 B linked flash, 211,848 B static
RAM and 3,138,688/3,204,224 B app/factory images. This is +2,808 B linked
flash, +224 B static RAM and +2,816/+2,816 B images versus 0.153 for the
fourth Actions row, bounded notes editor, typed set/clear path, strings, state
probe and delta runner. Dedicated DIRAM is 295,028/341,760 B (86.33%, 46,732 B
remaining); dedicated IRAM remains 16,384/16,384 B. The current foreground
Targets allocation is 23,152 B: 19,008 B of Target/view state plus the 4,144 B
controller including its bounded editors. The separate catalog-only mutation
workspace remains 16,384 B; only a 24-byte notes prefix is hex-encoded in the
existing static diagnostic JSON buffer. Exact HIL sees 75,656 B free and a
34,804 B largest block before both mounts, returns heap from 84,736 B to
96,516 B, and records UI/worker times of 153/2,942,650 µs for set and
153/2,964,667 µs for clear. Both mutations use three writes, three file syncs
and three directory syncs; generations advance 5→6→7, with a physical cold
reopen after each transition. Firmware/ELF/map SHA-256 are
`f2d151dcfc955260a4cd0bee67de1887a46af9bab53b18477bb6633ae99dd095`/
`9eaf3896cd681932f397f87cdb4cc07a087b9ef6914f2693c485bc40330a6ebd`/
`4888aa7c2b1ef182121364a2e72e1e1f2a19eee769f4820613ac377574309ed7`.
The one-flash delta and seven reviewed TFT states are retained in `E-HIL-172`;
the cadence advances to 9/15 without a full physical matrix.

Targets Correlation checkpoint `RB-M155`: exact production
`0.155.7-targets-shared-codec` uses 3,157,569 B linked flash, 214,165 B static
RAM and 3,135,296/3,200,832 B app/factory images. Dedicated DIRAM is
297,365/341,760 B (87.01%, 44,395 B remaining). The 24,800 B
`TargetsStoreCodecWorkspace` union replaces the former permanent 22,824 B
Session codec workspace, so full Target graph/history persistence costs only
1,976 B additional permanent RAM rather than a second simultaneous allocation.
It switches lifetime with placement construction only after writable FAT mount
and restores the Session codec before releasing the worker. Linked stack
preflight records 416 B for `CorrelationService::propose`, 816 B for
`buildSessionCorrelationReview`, 432 B for `TargetsController::loadBindings`
and 1,104 B for `buildSide`. The adjacent exact mutation regression succeeds at
61,468 B free/29,684 B largest pre-mount heap, writes 2,079 logical bytes with
three writes, three file syncs and three directory syncs, and completes in
3,320,152 µs after a 212 µs UI callback. Exact Accept then advances state 8→9,
decision count 0→1 and Target revision 3→4; a separate zero-flash physical reset
reopens the same state with source identities invariant at 69. Firmware/ELF/map
SHA-256 are
`57cd9a4b2f84fbdd2ce7421f902497b1b57ea0a441adf64c20a6f37df93cdf2e`/
`47f483e9a65ede473fa4c9b5a3541267fdf6ea6e04dd9fb66efe29e6772cb89a`/
`17cdfbbfbe042a57c5b50eb31991015ca5a9b93ea72c49626c49132fe0020627`.
Six reviewed TFT states and the two zero-write rejected precursors are retained
in `E-HIL-173`; cadence advances to 10/15 without a full physical matrix.

Targets Reject rebuild checkpoint `RB-M156`: exact production
`0.156.0-targets-reject-rebuild` uses 214,168 B static RAM, 3,135,096 B of the
4,194,304 B app partition and a 3,135,600 B firmware image. The mutation worker
no longer duplicates the full 11,272 B catalog plus 11,272 B decision log while
its just-exited 8 KiB FreeRTOS stack awaits idle-task cleanup: after the atomic
write and verified reopen, runtime adopts those two worker allocations in place.
At the hard catalog bound 16/16 the physical Reject succeeds with 69,632 B free
before mutation mount, 60,552/32,756 B free/largest before the write, and fully
releases to the measured post-reset 94,108 B terminal heap. UI/worker times are
231/3,960,944 µs; 2,878 logical bytes use three writes, three file syncs and
three directory syncs. Target state advances 10→11 and the decision log 2→3,
while Target revision 5, visible ownership count 4 and catalog count 16 remain
unchanged. Firmware/ELF/map SHA-256 are
`68c809d0a529c76b629c2723c5f918c5288413fe7791d68e98b67dcab74c98b9`/
`e0bffd74505ed266cb6a48d9646fdf47c0290b462c9fb5234b5a4b010c8a50a7`/
`37e6fa1e70d3fe210324b13b3deb302741ec29ff36a2aff8b78a66c47ee50750`.
Seven reviewed TFT states and the fail-closed duplicate-rebuild precursor are
retained in `E-HIL-174`; cadence advances to 11/15 without a full matrix.

Targets load-memory checkpoint `RB-M157`: exact production
`0.160.0-targets-load-memory` uses 214,272 B static RAM, 3,147,108 B of the
4,194,304 B app partition and a 3,147,616 B firmware image. The retained
24 KiB target-state wire workspace now overlaps only the final 11,272 B
catalog, 11,272 B decision log and 11,528 B merge history; it is deleted before
the 7,736 B comparison, 2,704 B proposals and 4,240 B controller/runtime phase.
Under the exact post-Survey boundary that failed in 0.159, foreground load starts
with 67,436 B free, completes with 40,496 B free and releases to 93,040 B. The
complete persistence call chain is production-ELF-gated; `loadTargetsProduct`
uses 784 B and the nested decode frames use 32…752 B. Firmware/ELF/map SHA-256
are `a54d1509c01b1e6d77afed25e5cac74eb8d290221942391b45f65b44a50633cd`/
`af75ba520082f1491bee06dd741e77d2d17613e8edb1324d5ad58ff7c98d87d9`/
`5cf29818ec00b96e6d2e04d590b193d592d86dde55c7bda39fc1881b5d7455d8`.
Three reviewed TFT states and the exact no-flash/no-scan regression are retained
in `E-HIL-175`; cadence advances to 12/15 without a full matrix.

Targets merge/split checkpoint `RB-M158`: exact production
`0.165.0-targets-fixture-reopen` uses 214,285 B static DRAM, 3,159,796 B linked
flash and 3,160,304/3,225,840 B app/factory images. It adds the bounded fixture
continuity path and complete on-device merge/split interaction without allocating a
second graph: merge/split linked frames are 2,224/1,472 B, replacement helpers are
768/64 B, and both physical reset records retain 8,040 B minimum worker stack. The
isolated two-Target fixture opens with 67,896 B free, releases to 93,500 B and keeps
lease 13 only while Targets owns UI+Storage+RadioSPI. Two atomic mutations each use
three writes, three file syncs and three directory syncs. Firmware/ELF/map SHA-256
are `40af5486e8525998e86aa3c864e0cb0e21e3aace0d3dc40c8dd4eb1923f01d4b`/
`20968cb44e847c7e3b9338c462991b6710a2c23c1654e9b3692879c9f91a81ec`/
`7acc6be8c106566de2d877acae572171e790983a421bd226b9c2070a2a7063f1`.
Exact `E-HIL-176` restores the 4 MiB inactive OTA1 and original partition table
byte-for-byte, deletes private backups after verification, reopens product generation
161 read-only and ends Home/none/lease 0. Cadence advances to 13/15 without treating
the disposable fixture or unavailable PSRAM as product capacity.

Companion-contract checkpoint `RB-M159`: exact production
`0.166.0-companion-contract` at source
`d34135677e984b710ef061ca6886d7f08cd264be` uses 214,288 B static RAM,
3,159,808 B linked flash and 3,160,304/3,225,840 B app/factory images. This is
+3 B static RAM, +12 B linked flash and +0/+0 B images versus exact 0.165; dedicated
DIRAM is 297,504/341,760 B (44,256 B remaining) and dedicated IRAM remains
16,384/16,384 B. `CompanionConnectRequest` and `CompanionConnection` are each
compile-time bounded to at most 48 B. Parse frames are at most 512 B; response staging
uses 513 B only on the invoking stack and publishes no partial bytes. The protocol
translation unit is compiled and native-tested but is not yet referenced by product
runtime, so linker GC keeps the app/factory length unchanged; this budget does not
claim a running USB adapter. Firmware/factory/ELF/map/partitions SHA-256 are
`200bf8f5c04f5815821503748aac549aadc422eb6268b3c700356fd3227cd9af`/
`3f3729e6a71d539bb38d981213b895f0494e579bbb90cfd7fcb5cc8f00bd61c9`/
`c86a2b60a9264f456b8d6d3f07c5e33b437f3f8ffec247de8f47c0465e00e6a7`/
`e7416f269ad17c44324e9d0225fdfe23d7f4e82a20ea21795890538b18a14622`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
No physical cadence delta is consumed.

Companion-USB read checkpoint `RB-M160`: exact production
`0.170.0-companion-usb-rx` at source
`b58fbc054522cecfca5dd4afcd6ea61098cb05c0` uses 214,664 B static RAM,
3,172,080 B linked flash and 3,172,576/3,238,112 B app/factory images. This is
+376 B static RAM and +12,272/+12,272/+12,272 B linked/app/factory versus exact
0.166. The native adapter owns one 513-byte command/response workspace, keeps the
protocol frame bound at 512 bytes and configures a 576-byte hardware CDC RX queue;
the latter is required because the valid compare request exceeded the core's default
256-byte queue before its newline arrived. Physical Targets opens with 92,972 B free
heap before and after release; the minimum sampled free heap is 15,008 B during the
bounded load. Exact firmware/factory/ELF/map/partitions SHA-256 are
`6275e94fd34cf28018cb761dc877717a668e2fedb8b5f4d9de6a213dfe0583ad`/
`8f0a7a1696069225a96984480e88d66f9beacb7530399e28291e8ffde1b66528`/
`6c4da4273bfa0d11fc5b022125a320f61f45342ac34cc0ac870a3178fc0832cf`/
`c18e76d32054cb0be139be73f3b55d085f55179858ae828dad8c68950b48adef`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
`E-HIL-177` accepts the exact 512-byte boundary, full read pagination, invariant
released heap and zero storage writes, TX, drops or leaked lease. Cadence advances to
14/15; the next accepted physical delta triggers the established full-matrix gate.

Per-antenna LED and cadence-full checkpoint `RB-M161`: exact production
`0.171.0-antenna-status-leds` at source
`c2413c9e31b89efd646a0ca15d2eb2b574d90fe5` uses 214,696 B static RAM,
3,175,040 B linked flash and 3,175,536/3,241,072 B app/factory images. This is
+32 B static RAM and +2,960/+2,960/+2,960 B linked/app/factory versus exact 0.170.
The fixed four-pixel GPIO1 controller adds no frame buffer, heap allocation or timing
loop: it writes only when receiver state or the persisted raw 0/2/3/5/8/12 preference
changes. Exact firmware/factory/ELF/map/partitions SHA-256 are
`77d14d9ac10f64cb60fb97f2f3b6b3986d2cdac71085b454d6d25267794e0784`/
`04bb4a4fb78cd4de7e12e5a2c4b43311e8e1af097c8e5181173a0bc08500a0fe`/
`e5189daa424da4e2ca04e5e94390f19e9ef3d483c894b10a62c8da9da08d247c`/
`04e897a24e7bb68e1933bb95d19b9c30a546ae56a8a598f9138256ad9ac1a8b4`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
The periodic physical matrix returns heap total/free to 164,108/91,068 B after Home,
RF, Targets and companion, preserves generation 161/59 observations, and adds zero
flashes beyond the one already spent by the LED delta. `E-HIL-178` consumes delta
15/15; `E-HIL-179` completes the immediately required full checkpoint and resets the
cadence anchor to 0/15.

Companion Target-mutation checkpoint `RB-M162`: exact production
`0.172.0-companion-target-mutate` at firmware source
`6ec3a198562c2cffc998b18bbd5e0738dcae3428` uses 214,992 B static RAM,
3,183,044 B linked flash and 3,183,200/3,248,736 B app/factory images. This is
+296 B static RAM, +8,004 B linked flash and +7,664/+7,664 B images versus exact
0.171. The bounded mutation adapter adds no second catalog or storage path: its fixed
preview/status record carries a nonzero 128-bit token, exact optimistic revision and
one pending value, then delegates confirmation to the already supervised Target worker.
The physical Favorite round trip publishes two generations; every commit records three
writes, three file syncs and three directory syncs. Cold reset reopens Target-state
generation 17 and revision 12 with the original false value. Heap total/free returns to
163,812/91,068 B; the post-reset sampled minimum is 17,344 B after the full bounded
Targets load. Exact firmware/factory/ELF/map/partitions SHA-256 are
`7038ac9bd5995cea7b1dd203342e38514ced0b5b678fb625ef506c093b104e1c`/
`edf50e23cf071428c29c3031a1ecee7510e605bdd6c96aa0d9f9a4f0cb1f6658`/
`36ae2320517acf5625904aa5989d9253cce53c895ca6453ece39f81864df8da7`/
`8abb1b91b2273838171604ac427bedb22a16144cd23f3d483d249a4e1d926210`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
`E-HIL-180` reuses the one exact installation, preserves both rejected harness
precursors and accepts reconnect-aware cold reopen with zero TX, input drops, port
discovery, Cardputer opens or leaked lease. Verification source
`48d296537a8eb358663420918b19151e2aa19c09` changes host reset transport only. Cadence
advances to 1/15.

Local Web presentation checkpoint `RB-M163`: exact production
`0.173.0-companion-local-web` at source
`9ae7ee5a6013f219cb0cdf406ef5cf1ce57934e3` uses 214,992 B static RAM,
3,183,140 B linked flash and 3,183,296/3,248,832 B app/factory images. This is zero
static-RAM growth and +96/+96/+96 B linked/app/factory versus exact 0.172. The Web
translation unit and its self-contained page are compiled and native-tested but not
yet referenced by product runtime, so linker GC removes the presentation payload; the
remaining delta is build identity. Its request view is compile-time bounded to 32 B,
the shared body remains at most 512 B, transport errors stage at most 192 B and the
offline page is host-gated below 16 KiB. Exact firmware/factory/ELF/map/partitions
SHA-256 are
`392d7e34f5625dee1762b28be6d75c164376b882bbd75f0f746ef2d891afbc78`/
`187b0a17c3072312e3f3ca56f380fcd1eced78c050a867ed32885a0ecbdb4bd2`/
`a45bc9fe70622a5d910902606609428a70a28fc555d19f53a0e8c5fdd53d1652`/
`086cf6da062bf2b6c23807ed3f19377669e47138e58e72468d6f04ec5c65d330`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Two consecutive builds from the workspace-local PlatformIO core produce those exact
hashes while remaining isolated from unrelated projects. No physical cadence delta is
consumed; runtime listener/connection memory is not yet admitted or claimed.

Physical local-Web lifecycle checkpoint `RB-M164`: exact production
`0.181.0-companion-web-deferred-worker-restore` at source
`6e0f2be76240e38d12805cfd654a7d70c61ae3d8` uses 222,800 B static RAM,
3,359,608 B linked flash and 3,360,112/3,425,648 B app/factory images. Versus exact
0.173 this is +7,808 B static RAM, +176,468 B linked flash and +176,816/+176,816 B
images because the ESP-IDF Wi-Fi/AP and HTTP runtime are now reachable instead of
linker-collected. The portable board still has zero usable PSRAM. Ready Targets has
32,660 B free; releasing its heavy foreground objects raises this to 39,924 B and
releasing the idle Survey worker/queues raises it to 60,788 B. Immediately before
`esp_wifi_start`, free/largest heap is 54,764/23,540 B and after start it is 16,868 B.
Stop returns 53,424 B while Targets is restored and the Survey worker remains deferred;
leaving Targets restores that worker, and the final boot metric is 75,972 B free with
156,004 B total and 14,088 B sampled minimum. Admission is fixed at one client, two
static RX buffers, one dynamic RX, one dynamic TX, one management buffer, six short
management buffers, one cached TX buffer, 600 s idle and 1,800 s absolute lifetime.
Exact firmware/factory/ELF/map/built-partitions SHA-256 are
`7491f450026c864f228df3164155afd1c388d1faa0b8a60bf9a9ef652933cd9d`/
`b1a391215039621da8f7acc3d8cba5311d3d19bae10100b8ead1748d5ab98abb3`/
`eb42e6f9002a708329cb2498b0b37dc7be4d26f74bd40676e331ca599a56c31e`/
`585c0b9ec83193e1d8d239119359a934e111b1b3d7ce15b75a2f499004f92c84`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Installed partition preflight independently matches `339bda68…ba2`; no partition
flash occurs. `E-HIL-181` accepts lifecycle and cleanup only, advances cadence to 2/15
and explicitly leaves actual HTTP traffic for the next physical gate.

Pending HTTP-parity checkpoint `RB-M165`: production candidate
`0.182.0-companion-web-http-parity` uses 222,816 B static RAM, 3,360,828 B linked
flash and 3,361,328/3,426,864 B app/factory images. Versus exact 0.181 this is
+16 B static RAM, +1,220 B linked flash and +1,216/+1,216 B images. The firmware
delta is one 16-byte one-shot HIL entropy buffer plus exact parse/scrub/scope guards;
normal product starts retain hardware-RNG credentials. Host-only pagination, native
USB comparison, HTTP and macOS Wi-Fi restoration state live outside the firmware
budget. Exact firmware/factory/ELF/map/built-partitions SHA-256 are
`b7a1eea19c73c2d4fbd2be6487564b5a92e0e5cabff12bbe4ac92f6618692c5c`/
`bee589ee217579f3371c1ea2417ed78298ee0b716b2adfcb79e3e8baf5ad8a69`/
`e7452bf96285200b315b27e1532e8607cf1edfaa6c72e985a1969f831ff1bbee`/
`a2f8eb2aa6e5a3e3ac72cb894cf3be18fcbbb94a4f802aa13d12ab2edbbb95d2`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
This is host/build evidence only: no board was flashed, no host Wi-Fi state changed,
runtime heap is not re-claimed and physical cadence remains 2/15.

Offline companion checkpoint `RB-M166`: exact installed
`0.195.0-companion-web-gzip-index` uses 223,112 B static RAM, 3,359,896 B linked
flash and a 3,360,400 B app image; the no-flash USB-only gate adds no firmware
memory. The host-owned canonical snapshot is 11,521 B and does not consume device
RAM or storage. After a clean reset, Targets/export starts and finishes with 82,892 B
free heap and releases back to the same value. A retained precursor began from only
60,584 B after an earlier Local Web run and failed the read-only mount with
`ESP_ERR_NO_MEM` (257); reset restored 82,892 B and immediate Targets readiness.
This records the then-open firmware lifecycle/reclamation defect, not an accepted
lower memory budget; `RB-M167` below closes it. Exact `E-HIL-182` accepts only deterministic offline USB snapshot/search,
advances cadence to 3/15 and proves zero network-tool or active-Mac-Wi-Fi use.

Post-Web continuity checkpoint `RB-M167`: exact
`0.196.2-companion-post-web-shared-scratch` uses 223,112 B static RAM,
3,360,064 B linked flash and a 3,360,560 B app image: +0 B static RAM,
+168 B linked flash and +160 B app versus exact 0.195. Session wire codec
(22,856 B), Target wire codec (24,808 B) and Target admission scratch
(11,272 B) are mutually exclusive and reuse one existing static union. The pinned
ESP-IDF cannot deinitialize `esp_netif`, so its network core is an explicit
process-lifetime allocation rather than falsely reported reclaimed heap. After Web,
suspending the idle Survey worker raises free heap to 96,624 B before Targets;
releasing Targets and restoring the worker ends at 75,760 B versus the 82,892 B
clean-boot start. This accepted difference is the retained network core, while the AP,
server, authorization, credential and leases are gone. Exact `E-HIL-183` starts/stops
the device SoftAP with zero clients, reopens 16 Targets and 7 comparison items,
reproduces the accepted 11,521-byte snapshot, ends Home/none/lease 0 and advances
cadence to 4/15. Fail-closed 0.196/0.196.1 preserve the duplicate-codec and
dynamic-scratch allocation boundaries. No host network tool or active Mac Wi-Fi is
used.

Bounded-BLE correction `RB-M168`: rejected exact 0.207 uses 225,680 B static RAM
and reaches interactive ready with only 29,576 B free after starting NimBLE at boot.
Independent read-only identity proves the 62,534,975,488-byte enrolled SD and exact
CID, while FAT mount returns `ESP_ERR_NO_MEM` (257). This is not missing media and
is not an accepted lower heap budget. Candidate `1.0.0-dev.208` uses 225,688 B static
RAM, 3,318,064 B linked flash and 3,318,224/3,383,760 B app/factory: +8 B static RAM
while moving the same required NimBLE allocation out of boot/storage lifetimes. The
host must stop, exit and deinitialize before commit FAT can mount; physical free-heap
recovery remains the next delta gate. Firmware/app hashes are
`1b72d9cc05353ba5f36b815a21af1e5d91224ccae451174508915dbb8858380f`/
`598dc7e8de07ac2dd8509a7e3e1d2fac154de98c20b27241cb449cd174e1fb09`.

Disjoint-radio correction `RB-M169`: physically rejected exact
`1.0.0-dev.208` boots with 153,116 B free heap, 80,316 B largest block and
66,632 B minimum, but keeps NimBLE resident while Wi-Fi attempts initialization.
Wi-Fi therefore returns `ESP_ERR_NO_MEM` (257) with zero completed Wi-Fi cycles,
while BLE completes six windows and publishes 205 accepted reports. The bounded
timeline retains 64 and drops 171 reports by declared queue policy; these are not
driver or storage drops. The degraded run does not prove terminal commit and later
latches `runtime_watchdog` Safe Mode with owner none, lease zero and outputs
quiesced. Candidate `1.0.0-dev.209` makes each radio lifecycle disjoint and uses
225,688 B static RAM, 3,317,692 B linked flash and 3,318,192/3,383,728 B
app/factory. Firmware/factory/ELF/map SHA-256 are
`63f55328d23082943945659fb63d55a771d388b427f5eca29dcecd2178aa3bab`/
`4ed3bdd0cb6f1b4f8990dd89406bc0147b06b27d373f4b25b9fde8fefdbd51db`/
`38d3cf0242707a13407c3123a207ab0c8e942242336ec396b31ccfc89083d868`/
`8a8e616323c176c702939813f35f3804a0ae67105f7ced4376f25c1ff51a4198`.
Exact `E-HIL-188` physically accepts this budget: boot heap is invariant at
153,116/80,316/66,632 B before and after, Wi-Fi accepts 12 and BLE 35 observations
with zero errors/drops, generation 162→163 commits 3,801 B, cold reopen/export
recovers all 47 observations and final state is Home/none/lease 0 with safety armed.
The first exact-flash run and accepted no-flash rerun form one one-flash lineage;
cadence advances to 5/15.

Integrated-demo acceptance `E-HIL-189` reuses that exact installed candidate and
the already accepted no-flash Survey pair, so it adds zero application flashes and
no RAM/linked-flash/image-size delta. Targets opens every one of five comparison
evidence views and releases heap invariant at 80,316→80,316 B. The 11,882-byte
canonical snapshot is host-side output containing two Sessions, 16 Targets and five
comparisons; it does not consume firmware storage budget or authorize a device write.
Because this is selective reuse of the same accepted candidate rather than a new
delta, cadence remains 5/15.

Airspace Guard foundation `RB-M170`: exact `1.0.0-dev.210` adds only fixed stack/
caller-owned detector state and does not add a resident task, radio owner or static
buffer. Static RAM therefore remains 225,688 B; linked flash is 3,317,732 B and
app/factory sizes are 3,318,240/3,383,776 B. Firmware/factory/ELF SHA-256 are
`835beabb6f47c5dcb51ceb3524a0a47a0d21596132f83230169b682863dd58c6`/
`fb52489d182af4c2111a8eafb1e25b2aa0a54cddf73befa39ac9e201f48c897d`/
`44d1106b24dc5e17d09ca442e1df3cb67e9dbcced1e7c2f2cd288a7afd97c8a4`.
This is source/build evidence only; no physical heap budget or HIL cadence change is
claimed.

Airspace Guard workflow `RB-M171`: exact `1.0.0-dev.211` adds a caller-owned
controller over the bounded report. Because no production runtime owns it yet, link
garbage collection preserves the same 225,688 B static RAM, 3,317,732 B linked flash
and 3,318,240/3,383,776 B app/factory sizes. Firmware/factory/ELF SHA-256 are
`8b8953c54f8da2fa6564c3f093c26803775946d575ed9f8a0d979e069b522cdf`/
`8ace219821ac93fbcde5e5c158c89df0d49085e2bfae39f47669d1f9324cb34f`/
`fd84dac3a3b5e40e19cf5c0532f3306336d73c082841565d42b3bfa1ab28c447`.
Live wiring must remeasure the controller/report lifetime rather than inheriting this
zero-growth source/build result.

Airspace Guard presentation `RB-M172`: exact `1.0.0-dev.212` adds 27 bounded EN/RU
catalog entries and caller-owned four-row presentation state. Static RAM remains
225,688 B; linked flash is 3,319,744 B and app/factory sizes are
3,319,904/3,385,440 B: +2,012 B linked flash and +1,664/+1,664 B images versus
dev.211, entirely within the source/build presentation delta. Firmware/factory/ELF
SHA-256 are
`300c8b748d7640bfa21cc54fc8cefd6164d980514f4ea433050e3052dfefbe56`/
`565494baab59a5004e9951d49efa84bd0ed7d00c553f38b8383a10cf1ef893fa`/
`8054fc7b82242721948379e53a5f2d725b8ea0241e3c892153373e10c7435dbc`.
The app/factory/ELF sizes are 3,319,904/3,385,440/22,332,172 B. Live capture and
TFT wiring must still remeasure foreground/report lifetime; zero resident-RAM growth
here is not a physical runtime budget claim.

Airspace Guard TFT integration `RB-M173`: exact `1.0.0-dev.213` gives the production
runtime one bounded controller/report instance and links the Navigator/TFT adapter.
Static RAM is 227,696 B and linked flash is 3,326,584 B: +2,008 B RAM and +6,840 B
linked flash versus dev.212. App/factory/ELF sizes are
3,326,752/3,392,288/22,385,524 B. Firmware/factory/ELF SHA-256 are
`8e01268b7c640bee4a9bf36132947b50b74327346a0dab29e610f4737a45b805`/
`6bb1ab8745c4641a5ff7cdf75b170e4882452aa76405dec3fe2dd1a997c53a7d`/
`a42ac823d58a5fad3eab452887089270c649281e545b23a8747357cfadbef27f`.
No live capture buffer, task or radio owner is added; physical heap remains
unmeasured until the live adapter and one delta HIL are ready.

Airspace Guard bounded live capture `RB-M174`: exact `1.0.0-dev.214` reuses the one
resident `BoardWifiPassiveCapture`, its fixed 16-frame buffer and the existing Wi-Fi
driver lifecycle; no second capture buffer or task is introduced. Added monitor/report
state raises static RAM by 64 B to 227,760 B. Linked flash is 3,330,584 B (+4,000 B);
app/factory/ELF sizes are 3,331,088/3,396,624/22,410,600 B
(+4,336/+4,336/+25,076 B). Firmware/factory/ELF SHA-256 are
`cc97e4ef5236105df17dc8a52c14e9bf72b08ebe28dc6e26afc27ce8cedc53ba`/
`91bff6744cf1c32cc2b0942eb909e02dd85d0ee6685053b5ce489b462ee195e5`/
`6e34eafe189f37cccb1c54abc5c35c32a103e3c3af85df0c7750a4af83957e1f`.
This is source/build evidence; live heap recovery and driver cleanup remain a physical
delta measurement rather than an inferred budget claim.

Airspace Guard Wi-Fi identity detector `RB-M175`: exact `1.0.0-dev.215` extends the
existing bounded report and EN/RU catalog without a task, radio owner or second
capture buffer. Static RAM is 228,080 B (+320 B) and linked flash is 3,334,152 B
(+3,568 B). App/factory/ELF sizes are
3,334,656/3,400,192/22,447,288 B (+3,568/+3,568/+36,688 B).
Firmware/factory/ELF SHA-256 are
`f0363d45d50603a1cbf2881a85b78d6eb6e5bcf61f25791b6801548711d07b5f`/
`7b8d1126502341f14e7cd01ade8b07e80766ce464363f25d31b19030c4aa0e4c`/
`f70492ea627c4499d5b217e52063e6737058c395afa067423c2630da1427412f`.
The optimized host compiler reports 2,640 B static stack use for the complete
detector call after disconnect and identity scratch lifetimes were separated and
the identity pass was changed to bounded rereads. This is a review aid rather than
Xtensa HIL proof. At this checkpoint the identity detector is disabled on its
incomplete live-retention path, so this build makes no new live-heap or physical-radio
claim.

Airspace Guard bounded live identity retention `RB-M176`: exact
`1.0.0-dev.216` reuses the same 16-frame capture and adds only eight fixed exact
identity keys; there is still no second frame buffer, task or radio owner. Static RAM
is 228,432 B (+352 B) and linked flash is 3,335,404 B (+1,252 B).
App/factory/ELF sizes are 3,335,904/3,401,440/22,429,812 B
(+1,248/+1,248/−17,476 B). Firmware/factory/ELF SHA-256 are
`2c9eecfef8f65067f5e1104189a6de1d8f34ce1c7365b926a5cfd58dc751d081`/
`abb1cfd2aca3d48fb647b518535082cbd7a89476b3b82c36284278846ad9e276`/
`49eb21f5c3be4e15bd3a4512bb5cf8025aea7624d4fa3bd0e5251c4084401813`.
The optimized host stack report is 2,592 B for `inspectWifi`, 176 B for identity
decode and 144 B for the ingress key helper. Live heap/cleanup remains unclaimed
until physical HIL; incomplete identity retention disables the detector and is
reported as source loss rather than a clear result.

Airspace Guard rapid identity-churn detector `RB-M177`: exact
`1.0.0-dev.217` reuses the complete bounded identity evidence and the existing
report/UI path; it adds no task, radio owner, second capture buffer or static-RAM
allocation. Static RAM remains 228,432 B and linked flash is 3,336,748 B
(+1,344 B). App/factory/ELF sizes are
3,337,248/3,402,784/22,471,948 B (+1,344/+1,344/+42,136 B).
Firmware/factory/ELF SHA-256 are
`d89ec463004b1c325af2655bac717bb699fc1da7ba3d15a6bba574f0840bee08`/
`5f19d2112b8ce7ebe61b18d2270ec205daf1ff9a85e1aae178a4643c8f091564`/
`bc9bdba79c75ed9b1c8be84ab2eeefdb105d8a9784d5065b33e55e79bebc0838`.
The optimized host stack report is 2,656 B for `inspectWifi` (+64 B), 176 B for
identity decode and 144 B for the ingress key helper. Live heap and physical-radio
behavior remain unclaimed until HIL; the detector is disabled when identity
retention is incomplete.

Airspace Guard BLE tracker-compatible presence foundation `RB-M178`: exact
`1.0.0-dev.218` adds a bounded normalized-observation detector but no live adapter,
task, radio owner, capture buffer, presentation path or automatic response. Static
RAM remains 228,432 B and linked flash is 3,336,848 B (+100 B). App/factory/ELF
sizes are 3,337,344/3,402,880/22,488,644 B (+96/+96/+16,696 B).
Firmware/factory/ELF SHA-256 are
`bddb74d5a43b7cd565189163321369a130895558b61ee319c8c74591a69cd38b`/
`db3e444fc6c262c0064c6ddcf4c845cb1d1dcee366a21d04b8ab8a5e55cc56f0`/
`7e1bb82c00f233f19a3e10962b6e138aa0774fe23a01b4ea228be71ab3135171`.
The optimized host stack report is 2,320 B for `inspectBle`, below the current
2,416 B `inspectWifi`. This is a review aid, not Xtensa HIL proof; because the live
adapter and product presentation are intentionally absent, no live heap, radio,
TFT or cleanup claim follows.

Airspace Guard channel-free BLE presentation `RB-M179`: exact
`1.0.0-dev.219` adds kind-aware controller validation and ten EN/RU catalog entries,
but no live adapter, task, radio owner or capture buffer. Static RAM remains 228,432 B
and linked flash is 3,337,992 B (+1,144 B). App/factory/ELF sizes are
3,338,496/3,404,032/22,491,624 B (+1,152/+1,152/+2,980 B).
Firmware/factory/ELF SHA-256 are
`2307faece5b5cb9c2061f79bd7acfffdccceecde507149f2053708e6147c523b`/
`7b119e5f3ee5f11b489a4b3205562b3fe3f58e7df19ff59e178400010e88d949`/
`c1211e966c67ff72498a3f9febeb79e1b01b50ba7402cfff2d55a03cecddeb0c`.
No live heap, radio, TFT or cleanup claim follows until bounded BLE retention/handoff
and physical evidence exist.

Airspace Guard bounded BLE retention foundation `RB-M180`: exact
`1.0.0-dev.220` adds one fixed 32-observation retention object and raw-report
accounting, but no new task, stack or radio owner. Product Survey keeps its default
address deduplication; only the future guard request preserves repeated reports.
Static RAM remains 228,432 B and linked flash is 3,338,104 B (+112 B).
App/factory/ELF sizes are 3,338,608/3,404,144/22,504,576 B
(+112/+112/+12,952 B). Firmware/factory/ELF SHA-256 are
`fa864011d49d1db7ccf1f3a4dcb62cd6f24a9ec5eb3bbeebecfe3cb4314406b1`/
`79c2ea1011edfc5dac0e356945d93e7950c0ea982ab97b897539f52b23428617`/
`02c2a0c653990e03bf262c90dd8e46009c9968fa7363d26f570ff487e2128bdc`.
The full tracked host suite and production build pass. Live worker stack/heap,
radio cleanup and TFT behavior remain unclaimed until runtime wiring and HIL.

Airspace Guard supervised BLE runtime handoff `RB-M181`: exact
`1.0.0-dev.221` reuses the existing Product Survey worker task, stack and NimBLE
lifecycle. It adds one fixed 32-observation Airspace Guard workspace and one
single-result queue, not a second task, BLE stack or radio owner. Static RAM is
235,424 B (+6,992 B) and linked flash is 3,352,048 B (+13,944 B). The linker
retains 23,124 B internal DIRAM and reports 71.8% static RAM use. App/factory/ELF
sizes are 3,352,544/3,418,080/22,544,696 B (+13,936/+13,936/+40,120 B).
Firmware/factory/ELF SHA-256 are
`88b0134205b5882c19db3caf7b1494b32de8bd49a1d88a4f90f300a14f202e8e`/
`109b92a2ec01ea48f2cfa0bf6f24c75bc1ddc717997737557c9edf1ffea4cdf2`/
`21d12b39c81812b5fa4d2558a55e2e827381f9636316e8c8371558a5a09f00c7`.
The complete tracked host suite and production build pass. Runtime heap/stack,
radio cleanup and TFT timing remain unclaimed until physical HIL.

Airspace Guard bounded Wi-Fi noise indicator `RB-M182`: exact
`1.0.0-dev.222` adds eight fixed normalized receive-noise samples and their
fail-closed accounting; it adds no task, radio owner, TX path or dynamic allocation.
Static RAM is 235,680 B (+256 B) and linked flash is 3,356,404 B (+4,356 B).
App/factory/ELF sizes are 3,356,912/3,422,448/22,567,052 B
(+4,368/+4,368/+22,356 B). Firmware/factory/ELF SHA-256 are
`7a75b5db714eabf1eb730c50e64e34670a5cbad82905c4c50ebac38b2c2756b6`/
`1341dd90ad7b7a7512cf963fabdacfa2c2b069cdfb68279e301d854fcab81024`/
`b1103ab3499d684f553e41fcf146dd72a740b6d849cb6fe625cc60e9d9760b5d`.
The complete tracked host suite and production build pass. Runtime heap/stack,
radio cleanup and TFT timing remain unclaimed until physical HIL.

CAP-049 authentication-capture parser foundation `RB-M183`: exact
`1.0.0-dev.242` adds an allocation-free host parser with hard bounds of 64 inspected
immutable Wi-Fi frames, 16 exact evidence references, four peers, four PMKIDs and a
1,536 B report. Malformed, truncated, unread, capacity-lost and unsupported input
fails closed before publication. `E-BUILD-172`/`E-AUTO-146` accept these host bounds;
there is no live driver, radio/lease, storage, UI or export allocation claim yet.
The combined production build uses 244,696 B static RAM and 3,372,276 B linked flash,
leaving 13,852 B internal DIRAM. Firmware SHA-256 is
`2b4a9fbdfa294bc3e632a6f707b37b3dcbc9151888320dc0ceda607794f21f5e` and the
embedded app identity is
`02b27bc09cbb507a621e6a69ae42b41090e50e371ec3c4f4d85c3de1e2116d5d`.

Airspace Guard full physical acceptance `RB-M184`: `E-BUILD-173`/`E-AUTO-147`/
`E-HIL-190` bind the same exact dev.242 bytes and prove that the complete baseline
and deterministic capacity-loss lifecycles do not leak their warmed working set.
Free heap starts/restores at 60,540 B, rises to 72,324 B after queue release and keeps
25,588 B largest block. The baseline retains 54 BLE records with zero drops; injection
retains 1 and drops exactly 904 of 905 observed, stays incomplete/inconclusive, and
finishes Home/none/lease 0. The retained run/index SHA-256 are
`3c2b372956563009893c060b4ea5fab365b7b6cad057527bb29af6c63e469956`/
`b728e5430b2de6ba73cccbe12c02b37497b17cdda9e37efea85537717498d766`.
This is a measured board-01 runtime bound for CAP-048, not a resource claim for the
still host-only CAP-049 integration.

Board-02 adds a physical-variant fact, not usable memory budget. Its ROM reports
16,777,216 B flash and 8,388,608 B embedded Octal PSRAM on an N16R8 module, while
the exact compatibility product reports `psramFound=false`. GPIO35/36/37 are already
the stock display bus and the OPI-enabled experiment does not reach a stable product
boot. Therefore the portable ledger remains 16 MiB flash / zero PSRAM; the apparent
8 MiB must not fund buffers, caches or feature admission. The source-bound details are
retained in [variant evidence](../../tests/hil/evidence/board-02-hardware-variant-20260823.json).
