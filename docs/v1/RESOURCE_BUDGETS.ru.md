# ESP32-Leshy 1.x — реестр ресурсных бюджетов

*Читать на: [English](RESOURCE_BUDGETS.md) · **Русский***

Статус документа: **принятый S1 baseline, активный S5 — product build/heap/storage,
cross-radio release endurance и controlled power-cut измерены; внешние измерения
shared-bus/power остаются открытыми**.

Реестр не позволяет смешивать измерения, плановые ограничения и legacy numbers. До
принятия ADR о partition/memory policy 1.x это источник истины по бюджетам.

## Классы evidence

- `measured` — воспроизведено именованной сборкой или physical HIL record;
- `reference` — полезное сравнение, не являющееся бюджетом 1.x;
- `guardrail` — временная граница, превышение которой требует явного review;
- `unknown` — обоснованного измерения пока нет.

## Текущие измерения

| ID | Класс | Величина | Результат | Scope и evidence |
|---|---|---|---|---|
| RB-M01 | measured | physical flash / PSRAM | 16 777 216 B Quad flash; PSRAM отсутствует | board-01 probe 0.1.1, `E-HIL-001` |
| RB-M02 | measured | текущие app/storage slots | app0/app1 по 3 342 336 B; filesystem 1 572 864 B | board-01 partition inventory; layout probe, не принятый layout 1.x |
| RB-M03 | measured | HIL probe build | 354 548 B linked flash, 23 872 B static RAM; app image 354 960 B; factory image 420 496 B | probe 0.1.1, `E-BUILD-002`; только evidence tool |
| RB-M04 | measured | HIL probe runtime heap | total 387 360 B; free 347 224 B; observed minimum 342 040 B | board-01 native-USB inventory после boot |
| RB-R01 | reference | build 0.x + feasibility prototype | 1 995 896 B linked flash; 98 748 B static RAM | `E-BUILD-001`; не clean target и не верхний product budget |
| RB-M05 | measured | physical flash path | 80 MHz; полный backup/restore 16 MiB hash-verified; native upload 460800, CP2102 надёжен на 230400 | `E-HIL-004` |
| RB-M06 | measured | independent clean target build | 320 952 B linked flash; 22 576 B static RAM; app image 321 360 B; factory image 386 896 B | pinned toolchain, без dependencies/legacy sources, `E-BUILD-003` |
| RB-M07 | measured | runtime clean target | heap total 389 680 B; free 349 660 B; observed minimum 344 512 B; runtime-ready milestone 7 224 µs | board-01 native USB, `E-HIL-006`; без display/input/source/storage |
| RB-M08 | measured | first interactive target | 391 719 B linked flash; 24 460 B static RAM; app/factory images 392 128/457 664 B; interactive-ready 362 960 µs; heap total/free/min 386 256/343 420/338 272 B | board-01 `0.2.0-interactive-measure`, `E-BUILD-004`/`E-HIL-007`; display + read-only input, без storage/source |
| RB-M09 | measured | automated UI target | 394 843 B linked flash; 26 388 B static RAM; app/factory images 395 248/460 784 B; interactive-ready 368 941 µs; heap total/free/min 384 328/341 492/336 344 B | board-01 `0.3.0-ui-automation-measure`, `E-BUILD-005`/`E-HIL-008`; actual TFT capture + probe Navigator, без storage/source |
| RB-M10 | measured | storage-contract target | 395 115 B linked flash; 26 388 B static RAM; app/factory images 395 520/461 056 B; interactive-ready 368 949 µs; heap total/free/min 384 328/341 492/336 344 B | board-01 `0.4.0-storage-contract-measure`, `E-BUILD-006`/`E-HIL-009`; host atomicity + read-only contract report, filesystem не mounted |
| RB-M11 | measured | storage-guard target | 395 627 B linked flash; 26 388 B static RAM; app/factory images 396 032/461 568 B; interactive-ready 368 955 µs; heap total/free/min 384 328/341 492/336 344 B | board-01 `0.5.0-storage-guard-measure`, `E-BUILD-007`/`E-HIL-010`; fail-closed write permit + read-only guard report, filesystem не mounted |
| RB-M12 | measured | capability-home target | 396 243 B linked flash; 26 436 B static RAM; app/factory images 396 640/462 176 B; interactive-ready 373 119 µs; heap total/free/min 384 280/341 444/336 296 B | board-01 `0.6.0-capability-home-measure`, `E-BUILD-008`/`E-HIL-011`; capability projection + disabled reasons + Diagnostics launch/Back |
| RB-M13 | measured | runtime-lease target | 396 887 B linked flash; 26 468 B static RAM; app/factory images 397 296/462 832 B; interactive-ready 373 130 µs; heap total/free/min 384 248/341 412/336 264 B | board-01 `0.7.0-runtime-leases-measure`, `E-BUILD-009`/`E-HIL-012`; 1 000 циклов Diagnostics open/Back, leaked leases и изменение heap отсутствуют; p99/max Back/release 98,801/99,345 мс |
| RB-M14 | measured | Survey-contract target | 397 571 B linked flash; 26 468 B static RAM; app/factory images 397 968/463 504 B; interactive-ready 373 112 µs; heap total/free/min 384 248/341 412/336 264 B | board-01 `0.8.0-survey-contract-measure`, `E-BUILD-010`/`E-HIL-013`; bounded model/passive ingress/golden controller, radio untouched |
| RB-M15 | measured | golden Survey UI target | 405 223 B linked flash; 31 156 B static RAM; app/factory images 405 632/471 168 B; interactive-ready 372 519 µs; heap total/free/min 379 560/336 724/331 576 B | board-01 `0.9.0-survey-golden-ui-measure`, `E-BUILD-011`/`E-HIL-014`; in-memory Session на 64 slots + rendered workflow из трёх records, RF off |
| RB-M16 | measured | Session-codec target | 416 175 B linked flash; 48 628 B static RAM; app/factory images 416 576/482 112 B; interactive-ready 372 497 µs; heap total/free/min 362 088/319 252/314 104 B | board-01 `0.10.0-session-codec-measure`, `E-BUILD-012`/`E-HIL-015`; bounded segment 12 288 B + manifest/reopen workspace, round-trip трёх records, без storage/RF |
| RB-M17 | measured | bounded SessionStore target | 458 847 B linked flash; 74 148 B static RAM; app/factory images 459 248/524 784 B; interactive-ready 372 545 µs; heap total/free/min 336 568/293 732/288 584 B | board-01 `0.11.0-session-store-measure`, `E-BUILD-013`/`E-HIL-016`; два maximum-size RAM generations, auto-publish/reopen/corrupt-new fallback, без persistent storage/RF |
| RB-M18 | measured | offline Library target | 465 563 B linked flash; 79 132 B static RAM; app/factory images 465 968/531 504 B; interactive-ready 393 829 µs; heap total/free/min 331 584/288 748/283 600 B | board-01 `0.12.0-library-offline-measure`, `E-BUILD-014`/`E-HIL-017`; bounded List/Detail над одной reopened RAM Session, только UI lease, volatile/RF-off provenance |
| RB-M19 | measured | bounded Library-export target | 467 247 B linked flash; 79 772 B static RAM; app/factory images 467 648/533 184 B; interactive-ready 393 850 µs; heap total/free/min 330 944/288 108/282 960 B | board-01 `0.13.0-library-export-measure`, `E-BUILD-015`/`E-HIL-018`; explicit Export Ready + deterministic serial NDJSON, без file/media write |
| RB-M20 | measured | read-only storage-discovery target | 469 199 B linked flash; 80 588 B static RAM; app/factory images 469 600/535 136 B; interactive-ready 393 904 µs; heap total/free/min 330 128/287 292/282 144 B | board-01 `0.14.0-storage-discovery-measure`, `E-BUILD-016`/`E-HIL-019`; GPIO38 sampled non-authoritatively, без mount/write |
| RB-M21 | measured | mount-policy target | 470 215 B linked flash; 80 588 B static RAM; app/factory images 470 624/536 160 B; interactive-ready 393 889 µs; heap total/free/min 330 128/287 292/282 144 B | board-01 `0.15.0-mount-policy-measure`, `E-BUILD-017`/`E-HIL-020`; SDFS refused из-за отсутствия RO guarantee; без SD/SPI execution |
| RB-M22 | measured | SD RO protocol-plan target | 471 099 B linked flash; 81 100 B static RAM; app/factory images 471 504/537 040 B; interactive-ready 393 887 µs; heap total/free/min 329 616/286 780/281 632 B | board-01 `0.16.0-sd-ro-protocol-measure`, `E-BUILD-018`/`E-HIL-021`; fixed identification-only commands, execution disabled |
| RB-M23 | measured | SD transcript-parser target | 472 987 B linked flash; 81 804 B static RAM; app/factory images 473 392/538 928 B; interactive-ready 393 906 µs; heap total/free/min 328 912/286 076/280 928 B | board-01 `0.17.0-sd-parser-measure`, `E-BUILD-019`/`E-HIL-022`; synthetic transcript, physical SPI disabled |
| RB-M24 | measured | fake SD transport target | 474 959 B linked flash; 82 316 B static RAM; app/factory images 475 360/540 896 B; interactive-ready 393 888 µs; heap total/free/min 328 400/285 564/280 416 B | board-01 `0.18.0-sd-transport-measure`, `E-BUILD-020`/`E-HIL-023`; 11 fake exchanges, physical transports rejected |
| RB-M25 | measured | SD SPI wire-codec target | 476 051 B linked flash; 82 828 B static RAM; app/factory images 476 448/541 984 B; interactive-ready 393 870 µs; heap total/free/min 327 888/285 052/279 904 B | board-01 `0.19.0-sd-wire-measure`, `E-BUILD-021`/`E-HIL-024`; только bounded byte framing, execution disabled |
| RB-M26 | measured | physical SD identification target | 479 659 B linked flash; 84 300 B static RAM; app/factory images 480 064/545 600 B; interactive-ready 393 896 µs; heap total/free/min 326 416/283 944/278 668 B | board-01 `0.20.0-sd-physical-id-measure`, `E-BUILD-022`/`E-HIL-025`; три stable guarded identity runs 400 kHz, без mount/write |
| RB-M27 | measured | physical SD LBA0 target | 483 319 B linked flash; 86 764 B static RAM; app/factory images 483 728/549 264 B; interactive-ready 393 909 µs; heap total/free/min 323 952/281 480/276 204 B | board-01 `0.21.0-sd-sector0-measure`, `E-BUILD-023`/`E-HIL-026`; один guarded CMD17, только MBR metadata/fingerprint, без mount/write |
| RB-M28 | measured | physical FAT32 boot-sector target | 487 071 B linked flash; 90 340 B static RAM; app/factory images 487 472/553 008 B; interactive-ready 393 881 µs; heap total/free/min 320 376/277 904/272 628 B | board-01 `0.22.0-sd-boot-inspect-measure`, `E-BUILD-024`/`E-HIL-027`; два guarded metadata blocks подтверждают FAT32 geometry, без mount/directory/file/write |
| RB-M29 | measured | metadata-only FAT32 root-sector target | 492 119 B linked flash; 95 620 B static RAM; app/factory images 492 528/558 064 B; interactive-ready 393 903 µs; heap total/free/min 315 096/272 516/267 208 B | board-01 `0.23.0-sd-root-metadata-measure`, `E-BUILD-025`/`E-HIL-028`; один derived directory sector, только counts/CRC, names omitted и buffer zeroed |
| RB-M30 | measured | metadata-only FAT32 root-cluster target | 492 743 B linked flash; 95 620 B static RAM; app/factory images 493 152/558 688 B; interactive-ready 393 904 µs; heap total/free/min 315 096/272 516/267 208 B | board-01 `0.24.0-sd-root-cluster-measure`, `E-BUILD-026`/`E-HIL-029`; end marker после двух bounded sectors, complete root metadata counts, без names/file data/mount/write |
| RB-M31 | measured | FAT32 FSInfo target + shared SD workspace | 493 799 B linked flash; 90 004 B static RAM; app/factory images 494 208/559 744 B; interactive-ready 393 919 µs; heap total/free/min 320 712/278 132/272 824 B | board-01 `0.25.0-sd-fsinfo-measure`, `E-BUILD-027`/`E-HIL-030`; только technical free/next hints, без FAT/name/file/mount/write; shared workspace возвращает 5 616 B static RAM относительно 0.24 |
| RB-M32 | measured | FAT32 reserved/root-entry cross-check | 500 007 B linked flash; 90 004 B static RAM; app/factory images 500 416/565 952 B; interactive-ready 393 901 µs; heap total/free/min 320 712/278 240/272 964 B | board-01 `0.27.0-sd-fat-reserved-measure`, `E-BUILD-029`/`E-HIL-032`; +6 208 B linked flash относительно 0.25, static RAM без роста; ровно FAT[0…2], без chain/name/file/mount/write |
| RB-M33 | measured | guarded physical FAT SessionStore | 572 655 B linked flash; 94 996 B static RAM; app/factory images 573 056/638 592 B; interactive-ready 391 564 µs; heap total/free/min 315 720/272 648/237 716 B | board-01 `0.28.0-sd-session-store-measure`, `E-BUILD-030`/`E-HIL-033`; FAT mount плюс два real generations, unmount/remount/read-only reopen; 440 logical B внутри guard 64 KiB; retry пишет 0 B |
| RB-M34 | measured | ESP-IDF SDSPI SessionStore throughput | 615 159 B linked flash; 99 932 B static RAM; app/factory images 615 568/681 104 B; interactive-ready 391 482 µs; heap total/free/min 309 504/266 460/233 464 B | board-01 `0.29.0-sd-session-throughput-measure`, `E-BUILD-031`/`E-HIL-034`; 32 commits на actual 4 MHz, p50/p95/p99 405 729/571 276/591 651 µs, generation 32 переживает remount; 7 040 logical B и 2 195 456 B physical delta внутри guard 4 MiB; retry пишет 0 B |
| RB-M35 | measured | software-reset harness и physical matrix | 626 155 B linked flash; 99 932 B static RAM; app/factory images 626 560/692 096 B; interactive-ready 391 524 µs; heap total/free/min 309 504/266 676/233 656 B | board-01 `0.30.0-sd-session-reset-measure`, `E-BUILD-032`/`E-HIL-035`; +10 996 B linked flash и zero static-RAM delta относительно 0.29; шесть boundaries восстанавливают 1/1/1/1/1/2 с unchanged prior hashes и zero recovery writes; boundary 4 потребовал один fail-closed read-only readiness retry |
| RB-M36 | measured | shared SessionStore validation/recovery workspace | 621 479 B linked flash; 95 260 B static RAM; app/factory images 621 888/687 424 B; interactive-ready 391 554 µs; heap total/free/min после boundary-6 HIL 314 176/271 348/238 460 B | board-01 `0.31.0-sd-session-ram-review`, `E-BUILD-033`/`E-HIL-036`; удалён один redundant `SurveySession` 4 672 B, вернув 3 044 B запаса ниже RB-03; guarded boundary 6 восстанавливает generation 2 с unchanged prior hashes и zero recovery writes |
| RB-M37 | measured | passive Wi-Fi source ingress | 1 016 688 B linked flash; 113 600 B static RAM; app/factory images 1 017 088/1 082 624 B; interactive-ready 391 729 µs; heap total/free/min после 32 scans 288 160/244 664/186 376 B | board-01 `0.32.0-wifi-passive-ingress-measure`, `E-BUILD-034`/`E-HIL-037`; 32/32 passive scans принимают 414 observations с zero drop/reject; p50/p95/p99 370/504/546 encoded B/s; RB-06 требует 2 184 B/s, а текущий fsync-per-generation SD workload даёт 536 B/s |
| RB-M38 | measured | fixed queue + batched SD service rate | 1 018 192 B linked flash; 114 200 B static RAM; app/factory images 1 018 592/1 084 128 B; interactive-ready 393 709 µs; heap total/free/min после HIL 287 560/244 324/211 328 B | board-01 `0.33.0-sd-session-batch-throughput-measure`, `E-BUILD-035`/`E-HIL-038`; fixed FIFO/policy добавляют 600 B static RAM; 32×64-observation commits дают 9 068 encoded B/s и проходят required 2 184 B/s в 4,15×; real source integration ещё открыта |
| RB-M39 | measured | real passive Wi-Fi→FIFO→persistent SessionStore | 1 027 804 B linked flash; 119 656 B static RAM; app/factory images 1 028 208/1 093 744 B; interactive-ready 393 741 µs; heap total/free/min после HIL 282 104/238 028/149 308 B | board-01 `0.34.0-wifi-passive-persist-measure`, `E-BUILD-036`/`E-HIL-039`; ring 64 занимает 4 672 B; 29 real observations, high-water 9, zero drops, latency batch, remount reopen; 6 921 encoded B/s проходит RB-06 в 3,17× |
| RB-M40 | measured | current-boot persistent Library admission/export | 1 029 116 B linked flash; 120 264 B static RAM; app/factory images 1 029 520/1 095 056 B; interactive-ready 393 726 µs; heap total/free/min после HIL 281 496/237 420/147 692 B | board-01 `0.35.0-persistent-library-admission-measure`, `E-BUILD-037`/`E-HIL-040`; 52 real observations, high-water 18/64, zero drops, size batch, remount reopen; 12 957 encoded B/s проходит RB-06 в 5,93×; ordinary Library List/Detail/Export использует persistent/real provenance и освобождает lease 5→0 |
| RB-M41 | measured | prerelease firmware build identity | 1 029 312 B linked flash; 120 328 B static RAM; app/factory images 1 029 712/1 095 248 B; interactive-ready 393 728 µs; heap total/free/min после device-smoke 281 432/238 768/233 372 B | board-01 `0.36.0-prerelease-build-identity-measure`, `E-BUILD-038`/`E-HIL-042`; +196 B linked flash/+64 B static RAM, full ELF SHA-256 из candidate/cold boot/metrics совпадает; Home/Diagnostics/Back сохраняют zero visual mismatch |
| RB-M42 | measured | prerelease HIL session envelope | 1 030 684 B linked flash; 120 368 B static RAM; app/factory images 1 031 088/1 096 624 B; interactive-ready 393 722 µs; heap total/free/min после device-smoke 281 392/238 728/233 332 B | board-01 `0.37.0-prerelease-test-session-measure`, `E-BUILD-039`/`E-HIL-043`; +1 372 B linked flash/+40 B static RAM; begin/end state связывает 128-bit run ID и app identity без hardware lease; три TFT comparisons остаются zero mismatch |
| RB-M43 | measured | product Survey workflow + extended prerelease HIL | 1 033 560 B linked flash; 120 400 B static RAM; app/factory images 1 033 968/1 099 504 B; interactive-ready 393 720 µs; heap total/free/min после полного workflow 281 360/238 696/233 300 B | board-01 `0.38.0-product-survey-workflow-measure`, `E-BUILD-040`/`E-HIL-046`; +2 876 B linked flash/+32 B static RAM; Setup→Running→Stop & Commit→Library→export, десять TFT comparisons zero mismatch, simulated/RAM/RF-off provenance |
| RB-M44 | measured | product source→FIFO pipeline + visible progress | 1 035 232 B linked flash; 120 488 B static RAM; app/factory images 1 035 632/1 101 168 B; interactive-ready 393 815 µs; heap total/free/min после workflow 281 272/238 608/233 212 B | board-01 `0.39.0-product-survey-pipeline-measure`, `E-BUILD-041`/`E-HIL-047`; +1 672 B linked flash/+88 B static RAM; существующий ring 64 переиспользован, pipeline 3 received/3 forwarded/high-water 3/drop 0, Stop trigger, десять visual mismatches 0 |
| RB-M45 | measured | fail-closed product source/store admission | 1 037 472 B linked flash; 120 488 B static RAM; app/factory images 1 037 872/1 103 408 B; interactive-ready 393 836 µs; heap total/free/min после workflow 281 272/238 608/233 212 B | board-01 `0.40.0-product-admission-policy-measure`, `E-BUILD-042`/`E-HIL-048`; +2 240 B linked flash/zero static-RAM delta; exact product root/read-only recovery/explicit bounded write/combined lease policy, revision-4 query и десять visual mismatches 0 без hardware I/O |
| RB-M46 | measured | background physical-keypad frontend | 1 039 304 B linked flash; 120 576 B static RAM; app/factory images 1 039 712/1 105 248 B; interactive-ready 394 001 µs; heap total/free/min после workflow 281 184/233 556/228 160 B | board-01 `0.41.0-keypad-frontend-measure`, `E-BUILD-043`/`E-HIL-049`; +1 832 B linked flash/+88 B static RAM и 5 052 B measured heap cost отдельной task/очереди 16; maximum physical sample gap сохраняется 5 ms во время полного HIL run |
| RB-M47 | measured | press-only/batched keypad attempt | 1 039 480 B linked flash; 120 584 B static RAM; app/factory images 1 039 888/1 105 424 B; interactive-ready 393 977 µs; heap total/free/min после workflow 281 176/233 548/228 152 B | board-01 `0.42.0-keypad-burst-measure`, `E-BUILD-044`/`E-HIL-051`; +176 B linked flash/+8 B static RAM vs 0.41; automatic HIL прошёл, physical burst переполнил press queue 16 |
| RB-M48 | measured | accepted lossless keypad burst buffer | 1 039 504 B linked flash; 120 584 B static RAM; app/factory images 1 039 904/1 105 440 B; interactive-ready 393 998 µs; heap total/free/min после workflow 281 176/233 140/227 744 B | board-01 `0.43.0-keypad-burst-buffer-measure`, `E-BUILD-045`/`E-HIL-052`; +24 B linked flash/zero static RAM и 408 B measured free/min-heap cost vs 0.42 для queue 64; physical high-water 6/64, 50/50 dispatched, zero drops, sample gap 5 ms |
| RB-M49 | measured | read-only product SD boot recovery | 1 053 188 B linked flash; 120 696 B static RAM; app image 1 053 600 B; generic interactive-ready 394 166 µs и heap total/free/min 281 064/232 984/227 516 B; enrolled cold-boot interactive-ready 564 144 µs и heap total/free/min 281 064/232 628/199 708 B | board-01 `0.44.0-sd-readonly-driver-measure`, `E-BUILD-046`/`E-HIL-053`; +13 684 B linked flash/+112 B static RAM относительно 0.43; exact-CID read-only boot допускает generation 1/17 observations с lease 12→0, zero write-blocker hits и zero SD write calls; O(media-size) FAT free-space scan отсутствует |
| RB-M50 | measured | interactive real passive product Survey + automatic product HIL | 1 059 264 B linked flash; 125 448 B static RAM; app image 1 059 664 B; enrolled cold-boot interactive-ready 592 104/598 613 µs до/после commit; heap total/free/min 276 312/227 876/194 956 B | board-01 `0.45.0-product-survey-measure`, `E-BUILD-047`/`E-HIL-054`; +6 076 B linked flash/+4 752 B static RAM vs 0.44; passive scan под lease 15 принимает/forward 15/15, generation 2→3, read-only reboot/export совпадают, final lease 0; cached FSInfo доказывает space без full FAT scan |
| RB-M51 | measured | bounded boot retry + endurance-runner smoke | 1 060 116 B linked flash; 125 448 B static RAM; app/factory images 1 060 528/1 126 064 B; шесть enrolled boot markers 750,446…761,734 ms; heap total/free/min 276 312/227 876/194 956 B с zero drift | board-01 `0.46.0-product-boot-retry-measure`, `E-BUILD-048`/`E-HIL-059`; +852 B linked flash/zero static-RAM delta vs 0.45; three-cycle smoke продвигает 12→15 с 51/51 forwarded и без drops, но все boots используют attempt 1 и результат не удовлетворял действовавшему тогда 8 h gate |
| RB-M52 | measured | Product Start raw-identity retry | 1 060 632 B linked flash; 125 448 B static RAM; app/factory images 1 061 040/1 126 576 B | board-01 `0.47.0-product-start-retry-measure`, `E-BUILD-049`/`E-HIL-060/061`; +516 B linked/app и zero static-RAM delta vs 0.46; два normal cycle проходят, а третий обнаруживает unbounded lower boot-recovery call |
| RB-M53 | measured | app-bound boot budget + lock-free recovery watchdog | 1 061 848 B linked flash; 125 456 B static RAM; app/factory images 1 062 256/1 127 792 B; RTC no-init 20 B; heap total/free/min 276 304/227 864/192 432 B; normal ready 812,973…820,884 ms и retry ready 2 660,702 ms | board-01 `0.48.0-product-boot-timeout-measure`, `E-BUILD-050`/`E-HIL-062…064`; +1 216 B linked/app и +8 B static RAM vs 0.47; injected timeout перезапускается без SD writes, затем три cycle продвигают 27→30 с 45/45 forwarded, zero drops и zero heap drift; это не удовлетворяло действовавшему тогда 8 h gate |
| RB-M54 | measured | lower-clock resilience Product Start | 1 061 852 B linked flash; 125 456 B static RAM; app/factory images 1 062 256/1 127 792 B; RTC no-init 20 B; heap total/free/min 276 304/227 864/192 432 B; normal ready 855,468…864,535 ms и retry ready 1 658,062 ms | board-01 `0.49.0-product-start-resilience-measure`, `E-BUILD-051`/`E-HIL-065…068`; +4 B linked flash/zero static-RAM или image delta vs 0.48; 100 kHz улучшает isolated valid raw identities с 13/32 до 24/32, exact three-cycle regression продвигает 35→38 с 46/46 forwarded, zero drops и zero heap drift; это не удовлетворяло действовавшему тогда 8 h gate |
| RB-M55 | measured | aligned resilience budget Product Start/boot | 1 061 852 B linked flash; 125 456 B static RAM; app/factory images 1 062 256/1 127 792 B; RTC no-init 20 B; heap total/free/min 276 304/227 864/192 432 B; normal ready 888,082…897,937 ms и retry ready 1 703,735 ms | board-01 `0.50.0-product-boot-resilience-measure`, `E-BUILD-052`/`E-HIL-069…071`; zero build/resource delta vs 0.49; boot attempts увеличены 3→8 после natural gate failure на трёх attempts и measured maximum raw failure streak четыре; three-cycle regression продвигает 44→47 с 39/39 forwarded, zero drops и zero heap drift; это не удовлетворяло действовавшему тогда 8 h gate |
| RB-M56 | measured | hardware-backed timeout recovery + shortened endurance | 1 062 900 B linked flash; 125 464 B static RAM; app/factory images 1 063 312/1 128 848 B; RTC no-init 20 B; software tier 4 000 ms плюс panic-enabled Task WDT tier 5 000 ms; runtime heap total/free/min 276 040/227 588/192 128 B; injected timeout ready 6 697,964 ms, normal maximum ready 961,019 ms | `0.51.0-hardware-boot-watchdog-measure`, `E-HIL-072…075`/`E-AUTO-019/020`/`E-BUILD-053`; physical Task WDT recovery и 12 последовательных product cycles за 11 330,816 s продвигают 51→63 с 144/144 forwarded, 24 cold boots, zero drops/retries/heap drift и final lease 0; shortened checkpoint не является release gate |
| RB-M57 | measured | semantic visual system + exact product regression | 1 063 092 B linked flash; 125 464 B static RAM; app/factory images 1 063 248/1 128 784 B; RTC no-init 20 B; runtime heap total/free/min 276 040/227 588/192 128 B | board-01 `0.52.0-visual-system-measure`, `E-BUILD-054`/`E-HIL-076`/`E-UX-003`; +192 B linked flash, zero static-RAM growth и app/factory images на 64 B меньше vs 0.51; exact run продвигает 64→65 с 9/9 forwarded, zero drops, шестью retained TFT frames и final lease 0; это принимает UX-03, но не S2 или release gate |
| RB-M58 | measured | встроенный Self-Test Quick + shared report workspace | 1 067 800 B linked flash; 128 720 B static RAM; app/factory images 1 068 208/1 133 744 B; RTC no-init 20 B; runtime heap total/free/min 272 784/224 332/188 872 B | board-01 `0.53.0-self-test-quick-measure`, `E-BUILD-055`/`E-HIL-077`/`E-AUTO-021`; +4 708 B linked flash, +3 256 B static RAM и +4 960 B images vs 0.52. Quick проходит 8/8 за 60 µs с zero side effects/final lease; Full остаётся blocked на incomplete coverage. Один shared static JSON workspace 3 KiB заменяет rejected loop-stack buffer |
| RB-M59 | measured | общая UI component geometry + renderer primitives | 1 068 048 B linked flash; 128 720 B static RAM; app/factory images 1 068 192/1 133 728 B; RTC no-init 20 B; runtime heap total/free/min 272 784/224 332/188 872 B | board-01 `0.54.0-ui-components-measure`, `E-BUILD-056`/`E-HIL-078`/`E-UX-004`; +248 B linked flash, zero static-RAM growth и images на 16 B меньше vs 0.53. Четыре retained TFT frame подтверждают общие Home/Self-Test components; Quick остаётся 8/8, final lease 0 |
| RB-M60 | measured | полный каталог EN/RU + сгенерированные GFX-шрифты PT Sans Narrow + persistent Language controller | 1 104 448 B linked flash; 128 744 B static RAM; app/factory images 1 104 592/1 170 128 B; RTC no-init 20 B; runtime heap total/free/min 272 760/224 280/188 792 B | board-01 `0.55.0-ui-language-measure`, `E-BUILD-057`/`E-HIL-079`/`E-UX-005`; +36 400 B linked flash, +24 B static RAM и +36 400 B images vs 0.54. Каталог 111-ID/222-string и сгенерированные Cyrillic faces 16/12 px не добавляют runtime font heap; exact TFT HIL подтверждает persistence, fit, Quick 8/8, zero input drops и final lease 0 |
| RB-M61 | measured | non-color focus outline/chevron + accessibility contract пяти кнопок | 1 105 748 B linked flash; 128 744 B static RAM; app/factory images 1 105 904/1 171 440 B; RTC no-init 20 B; runtime heap total/free/min 272 760/224 280/188 792 B | board-01 `0.56.0-ui-accessibility-measure`, `E-BUILD-058`/`E-HIL-080`/`E-UX-006`; +1 300 B linked flash, zero static-RAM growth и +1 312 B images vs 0.55. Exact TFT actions подтверждают geometric focus на Home/Library/Self-Test, Quick 8/8, zero current input errors/drops, buzzer LOW и final lease 0; retained physical evidence подтверждает 50/50/50 key events |
| RB-M62 | measured | renderer common states Full/Guided + evidence plan 2 | 1 107 448 B linked flash; 128 744 B static RAM; app/factory images 1 107 600/1 173 136 B; RTC no-init 20 B; runtime heap total/free/min 272 760/224 280/188 792 B | board-01 `0.57.0-ui-state-evidence-measure`, `E-BUILD-059`/`E-HIL-081`/`E-UX-007`; +1 700 B linked flash, zero static-RAM growth и +1 696 B images vs 0.56. Девять exact TFT frames покрывают modes/preflight/пять common states/result/cleanup; plan 2 даёт 9 pass/0 fail/1 честный blocker с zero side effects, input drops и final leases |
| RB-M63 | measured | exact воспроизводимый DEMO-S2 | 1 107 612 B linked flash; 128 744 B static RAM; app/factory images 1 107 760/1 173 296 B; RTC no-init 20 B; runtime heap total/free/min 272 760/224 280/188 792 B | board-01 `0.58.0-stage-demo-s2-measure`, `E-BUILD-060`/`E-HIL-082`/`E-GATE-002`; +164 B linked flash, zero static-RAM growth и +160 B images vs 0.57. Exact demo из 29 steps совпадает с девятью TFT frames, проходит Quick 8/8 и закрывает S2 с zero final leases; release gate остаётся false |
| RB-M64 | measured | persistent asynchronous Product Survey worker | 1 111 148 B linked flash; 128 800 B static RAM; app/factory images 1 111 296/1 176 832 B; RTC no-init 20 B; runtime heap total/free/min 272 704/208 928/188 736 B | board-01 `0.59.0-product-survey-worker-measure`, `E-BUILD-061`/`E-AUTO-024`/`E-HIL-084`; +3 536 B linked flash, +56 B static RAM и +3 536 B images vs 0.58. Core-0 task и fixed queues 8/64 выдерживают два continuous scan cycles, high-water 10/64, 27/27 forwarded, zero drops/heap drift, callbacks Start/Stop 13/10 us и final lease 0; gates S3/release остаются false |
| RB-M65 | measured | UI-acknowledged ownership terminal Product Survey | 1 111 128 B linked flash; 128 800 B static RAM; app/factory images 1 111 280/1 176 816 B; RTC no-init 20 B; runtime heap total/free/min 272 704/208 928/188 736 B | board-01 `0.60.0-product-survey-terminal-ack-measure`, `E-BUILD-062`/`E-AUTO-025`/`E-HIL-085`; linked flash меньше на 20 B, zero static-RAM delta и images меньше на 16 B vs 0.59. Только UI выставляет terminal `Idle` после cleanup/commit; exact regression выдерживает два scans, high-water 9/64, 25/25 forwarded, zero drops/heap drift, callbacks Start/Stop 12/8 us и final lease 0; gates S3/release остаются false |
| RB-M66 | measured | observable physical active-scan cancel + bounded PCF8574 boot probe | 1 111 564 B linked flash; 128 816 B static RAM; app/factory images 1 111 712/1 177 248 B; RTC no-init 20 B; runtime heap total/free/min 272 688/208 912/188 720 B | board-01 `0.62.0-input-probe-resilience-measure`, `E-BUILD-063`/`E-AUTO-026`/`E-HIL-086`; +132 B linked flash, +16 B static RAM и +128 B images vs failed 0.61. Exact HIL отменяет active scan за 86,762 ms при callback 9 us, сохраняет generation 68/25, zero SD writes/heap drift и final lease 0. Retained failure one-shot input probe 0.61 привёл к bounded accounting 1…8 попыток/35 ms extra; оба boot 0.62 обнаруживают input с первой попытки; deliberate first-read injection остаётся дополнительным evidence |
| RB-M67 | measured | замена typography на Roboto Condensed Medium 16/12 + TFT regression 18 states | 1 111 932 B linked flash; 128 816 B static RAM; app/factory images 1 112 336/1 177 872 B; RTC no-init 20 B; runtime heap total/free/min 272 688/208 912/188 720 B | board-01 `0.63.0-roboto-condensed-ui-measure`, `E-BUILD-064`/`E-AUTO-027`/`E-HIL-087`/`E-UX-008`; +368 B linked flash, zero static-RAM growth и +624 B images vs 0.62. Vendored OFL source weight 500 создаёт body/meta bitmaps 2 153/1 275 B, все 127 ID/254 варианта помещаются после восьми безопасных сокращений, 18 exact TFT frames охватывают EN/RU и Full/Guided states, Quick 8/8, Full 9/10 с одним honest blocker, side effects/input drops/heap drift равны нулю, final lease 0 |
| RB-M68 | measured | трёхъячеечная пространственная навигация 40 px + exact TFT/action regression | 1 111 100 B linked flash; 128 816 B static RAM; app/factory images 1 111 504/1 177 040 B; RTC no-init 20 B; runtime heap total/free/min 272 688/208 912/188 720 B | board-01 `0.64.0-spatial-navigation-measure`, `E-BUILD-065`/`E-AUTO-028`/`E-HIL-088`/`E-UX-009`; −832 B linked/app/factory и zero static-RAM growth vs 0.63 после замены 19 prose footers на 15 компактных actions. Девять exact TFT frames и 15 transitions доказывают Left Back, Right/OK Enter, Up/Down Select, nested Library parity, zero input errors/drops, buzzer LOW, invariant heap и final lease 0 |
| RB-M69 | measured | компактный footer 26 px + changed-row-only инкрементальная отрисовка | 1 112 256 B linked flash; 128 856 B static RAM; app/factory images 1 112 656/1 178 192 B; RTC no-init 20 B; runtime heap total/free/min 272 648/208 872/188 680 B | board-01 `0.65.0-compact-incremental-ui-measure`, `E-BUILD-066`/`E-AUTO-029`/`E-HIL-089`/`E-UX-010`; +1 156 B linked flash, +40 B static RAM и +1 152 B images vs 0.64. Восемь exact incremental transitions перерисовывают только old/new rows за 19,901–28,981 ms при ceiling 40 ms вместо замеченных 63,615 ms whole-page redraw; девять frames/21 transition сохраняют navigation, zero input errors/drops, invariant heap, buzzer LOW и final lease 0 |
| RB-M70 | measured | упорядоченный input dispatch как в 0.x + incremental repaint без footer | 1 112 172 B linked flash; 128 856 B static RAM; app/factory images 1 112 576/1 178 112 B; RTC no-init 20 B; runtime heap total/free/min 272 648/208 872/188 680 B | board-01 `0.66.0-ordered-key-repaint-measure`, `E-BUILD-067`/`E-AUTO-030`/`E-HIL-090`/`E-UX-011`; −84 B linked flash, zero static-RAM delta и −80 B images vs 0.65. Одно queued physical press отрисовывается до извлечения следующего, поэтому быстрые selections не схлопываются; selection repaint не трогает footer/input strip. Восемь exact transitions занимают 13,927–23,043 ms при девяти frames/21 transition, zero input errors/drops, invariant heap, buzzer LOW и final lease 0 |
| RB-M71 | measured | non-blocking physical-key hot path + on-demand end-to-end telemetry | 1 112 568 B linked flash; 128 896 B static RAM; app/factory images 1 112 976/1 178 512 B; RTC no-init 20 B; runtime heap total/free/min 272 608/208 320/188 140 B | board-01 `0.67.0-nonblocking-keypath-measure`, `E-BUILD-068`/`E-AUTO-031`/`E-HIL-091`/`E-UX-012`; +396 B linked flash, +40 B static RAM, +400 B images и runtime queue на 512 B больше vs 0.66, потому что каждое из 64 событий теперь несёт microsecond timestamp. Удаление post-render USB/UART writes снижает замеченный пользователем queue high-water с 5 на 10 нажатиях до 1 на 75 подтверждённых; max queue latency 1,256 ms, last focus end-to-end 16,703 ms, zero errors/drops/serial writes; восемь TFT transitions остаются 13,972–23,058 ms |
| RB-M72 | measured | localized missing-source terminal UI + one-shot source-boundary HIL telemetry | 1 114 184 B linked flash; 128 920 B static RAM; app/factory images 1 114 592/1 180 128 B; RTC no-init 20 B; runtime heap total/free/min 272 584/208 168/188 116 B | board-01 `0.68.0-missing-source-tft-measure`, `E-BUILD-069`/`E-AUTO-032`/`E-HIL-092`/`E-SURVEY-007`; +1 616 B linked flash, +24 B static RAM и +1 616 B images vs 0.67. One-shot failure потребляется до source/store start; RU unavailable state 240×320 виден после lease 15→0, writes/observations остаются 0, hidden retry blocked, cold reboot сохраняет generation 68/25, heap invariant и final lease 0 |
| RB-M73 | measured | isolated normal/remount parity LittleFS на inactive OTA1 | 1 153 228 B linked flash; 130 216 B static RAM; app/factory images 1 153 632/1 219 168 B; RTC no-init 20 B; parity heap free before/after/min 206 424/206 088/186 820 B | board-01 `0.69.0-littlefs-parity-measure`, `E-BUILD-070`/`E-AUTO-033`/`E-HIL-093`/`E-STORAGE-024`; +39 044 B linked flash, +1 296 B static RAM и +39 040 B images vs 0.68. Common SessionStore завершает 32/32 generations с 96+96 barriers и RO-remount recovery 32/64; 18 586 B/s превышает target 2 184 B/s в 8,51 раза. Inactive OTA1 и partition table восстанавливают exact hashes, product 68/25 неизменен, final lease 0 |
| RB-M74 | measured | isolated six-boundary software-reset matrix LittleFS на inactive OTA1 | 1 165 916 B linked flash; 134 888 B static RAM; app/factory images 1 166 320/1 231 856 B; RTC no-init 60 B; product heap total/free/min 266 616/202 200/182 148 B | board-01 `0.70.0-littlefs-reset-matrix`, `E-BUILD-071`/`E-AUTO-034`/`E-HIL-094`/`E-STORAGE-025`; +12 688 B linked flash, +4 672 B static RAM, +12 688 B images и +40 B RTC no-init vs 0.69. Шесть software-reset boundaries восстанавливают generations 1/1/1/1/1/2 read-only с zero writes/syncs, exact continuity и cleanup. Одна OTA1 restore write плюс independent read-only verification сохраняют exact target/table hashes и unchanged product 68/25 |
| RB-M75 | measured | первый пользовательский срез S4: выбираемый план источников Survey | 1 169 012 B linked flash; 134 928 B static RAM; app/factory images 1 169 424/1 234 960 B; RTC no-init 60 B; product heap total/free/min 266 576/202 160/182 108 B | board-01 `0.71.0-survey-source-plan`, `E-BUILD-072`/`E-AUTO-036`/`E-HIL-096`/`E-SURVEY-009`; +3 096 B linked flash, +40 B static RAM и +3 104 B images vs 0.70. Exact physical HIL покрывает выбираемый Wi-Fi, видимо недоступный BLE, отказ Start для пустого плана и восстановление Wi-Fi через 11 transitions/пять TFT frames; max incremental render 31 818 us, zero input errors/drops, invariant heap, buzzer inactive и final lease 0 |
| RB-M76 | measured | runtime общей source timeline S4 и видимый Wi-Fi duty | 1 174 456 B linked flash; 136 880 B static RAM; app/factory images 1 174 864/1 240 400 B; RTC no-init 60 B; product heap total/free/min 264 624/199 952/180 156 B | board-01 `0.72.0-source-timeline-runtime`, `E-BUILD-073`/`E-AUTO-037`/`E-HIL-097`/`E-SURVEY-010`; +5 444 B linked flash, +1 952 B static RAM и +5 440 B images vs 0.71. Exact HIL учитывает два real scans как 34/34 observations и 4→5 windows с zero drops/overflow, показывает 74% Wi-Fi duty, commits generation 71→72, cold-recovers exact CID, сохраняет heap invariant и заканчивает lease 0. Timeline persistence/export и durable drain FIFO остаются открыты |
| RB-M77 | measured | durable persistence, cold reopen и export общей source timeline S4 | 1 184 052 B linked flash; 145 184 B static RAM; app/factory images 1 184 208/1 249 744 B; RTC no-init 60 B; product heap total/free/min 256 320/191 648/171 852 B | board-01 `0.73.0-source-timeline-persistence`, `E-BUILD-074`/`E-AUTO-038`/`E-HIL-098`/`E-SURVEY-011`; +9 596 B linked flash, +8 304 B static RAM и +9 344 B images vs 0.72 за timeline records schema v2, bounded retained windows, summaries и export workspace. Exact HIL дренирует FIFO до 0/high-water 1, учитывает 21/21 observations, commits generation 73→74, cold-reopens и экспортирует пять ordered windows с exact duration equality, zero drops/overflow, invariant heap и final lease 0 |
| RB-M78 | measured | bounded passive BLE и durable dual-source Survey S4 | 1 419 892 B linked flash; 147 360 B static RAM; app/factory images 1 420 304/1 485 840 B; RTC no-init 60 B; product heap total/free/min 234 348/169 728/150 208 B | board-01 `0.74.0-passive-ble`, `E-BUILD-075`/`E-AUTO-039`/`E-HIL-099`/`E-SURVEY-012`; +235 840 B linked flash, +2 176 B static RAM и +236 096 B images vs 0.73, главным образом из-за Arduino BLE stack. Exact HIL потоково принимает и сразу удаляет advertisements, учитывает Wi-Fi 6 + BLE 34 = 40 observations, дренирует FIFO до 0/high-water 2, commits generation 76→77 с шестью retained/exported windows, zero drops/overflow, invariant cold-boot heap и final lease 0 |
| RB-M79 | measured | compatible runtime source degradation S4 | 1 421 832 B linked flash; 147 360 B static RAM; app/factory images 1 422 240/1 487 776 B; RTC no-init 60 B; product heap total/free/min 234 348/169 728/150 208 B | board-01 `0.75.0-runtime-degradation`, `E-BUILD-076`/`E-AUTO-040`/`E-HIL-100`/`E-SURVEY-013`; +1 940 B linked flash, zero static-RAM growth и +1 936 B images vs 0.74. Exact HIL безопасно инъекционно делает BLE unavailable, продолжает два real Wi-Fi cycles с 28 observations, дренирует FIFO до 0/high-water 2, commits generation 77→78 с восемью retained/exported windows, включая 3 625 744 us `driver_unavailable`, zero drops/overflow, invariant cold-boot heap и final lease 0 |
| RB-M80 | measured | общий Observation browser S4, bounded RSSI history и RF-off snapshot | 1 426 252 B linked flash; 147 368 B static RAM; app/factory images 1 426 656/1 492 192 B; RTC no-init 60 B; product heap total/free/min 234 340/169 720/150 200 B | board-01 `0.76.0-observation-browser`, `E-BUILD-077`/`E-AUTO-041`/`E-HIL-101`/`E-SURVEY-014`; +4 420 B linked flash, +8 B static RAM и +4 416 B images vs 0.75. Exact HIL завершает один Wi-Fi+BLE cycle с 8+37 observations, замораживает RF и финализирует шесть windows до user browsing, доказывает counts Все/Wi-Fi/BLE 45/8/37 плюс оба RSSI Detail, commits generation 80→81, cold-reopens exact snapshot и заканчивает с zero drops/overflow и lease 0 |
| RB-M81 | measured | immutable Capture metadata S4, schema v3 и streaming observation CSV | 1 432 812 B linked flash; 147 688 B static RAM; app/factory images 1 433 216/1 498 752 B; RTC no-init 60 B; product heap total/free/min 234 020/169 400/149 880 B | board-01 `0.77.0-capture-export`, `E-BUILD-078`/`E-AUTO-042`/`E-HIL-102`/`E-SURVEY-015`; +6 560 B linked flash, +320 B static RAM и +6 560 B images vs 0.76. Exact HIL сохраняет generation 81→82 с 16 Wi-Fi + 31 BLE observations и immutable build/receive provenance, cold-reopens её, потоково выдаёт 47 canonical CSV rows/3 275 B без второго Session-sized buffer, честно сообщает недоступность PCAP без raw payload, сохраняет десять TFT frames, invariant heap и заканчивает с zero drops/overflow и lease 0 |
| RB-M82 | measured | bounded volatile Wi-Fi frame Capture и streaming radiotap PCAP S4 | 1 446 000 B linked flash; 152 376 B static RAM; app/factory images 1 446 400/1 511 936 B; RTC no-init 60 B; product heap total/free/min 229 332/164 712/145 192 B | board-01 `0.78.0-wifi-frame-capture`, `E-BUILD-079`/`E-AUTO-043`/`E-HIL-103`/`E-CAPTURE-001`; +13 188 B linked flash, +4 688 B static RAM и +13 184 B images vs 0.77. Exact HIL ограничивает payload до 16×256 B/4 096 B, учитывает 18 capacity drops без overwrite, потоково выдаёт 16 valid radiotap/802.11 records в PCAP 4 616 B, выполняет zero application connect/raw-TX/storage calls, не сохраняет raw payload в evidence, scrub-ит RAM на Back и заканчивает lease 0 |
| RB-M83 | measured | privacy-confirmed persistent Wi-Fi Capture, schema v4 и cold Library PCAP S4 | 1 454 428 B linked flash; 152 424 B static RAM; app/factory images 1 454 832/1 520 368 B; RTC no-init 60 B; product heap total/free/min 229 284/164 540/145 144 B | board-01 `0.79.0-persistent-frame-capture`, `E-BUILD-080`/`E-AUTO-044`/`E-HIL-104`/`E-CAPTURE-002`; +8 428 B linked flash, +48 B static RAM и +8 432 B images vs 0.78. Эти 48 B обслуживают persistent view/workspace metadata, а не duplicate payload store. Exact HIL после explicit privacy confirmation atomic продвигает generation 82→83, cold-reopens 16 frames/2 253 B, потоково выдаёт byte-exact Library PCAP 2 773 B, сохраняет heap через reboot, scrub-ит live RAM и заканчивает lease 0 |
| RB-M84 | measured | plan-v3 Self-Test registration завершённых workflows S3/S4 и no-extension dispositions | 1 456 012 B linked flash; 152 520 B static RAM; app/factory images 1 456 416/1 521 952 B; RTC no-init 60 B; product heap total/free/min 229 188/164 444/145 048 B | board-01 `0.80.0-self-test-coverage`, `E-BUILD-081`/`E-AUTO-045`/`E-HIL-105`/`E-SELFTEST-002`; +1 584 B linked flash, +96 B static RAM и +1 584 B images vs 0.79. Exact HIL доказывает Quick 8/8 и Full 15 pass/0 fail/2 blocked/3 N/A с десятью TFT frames, неизменной storage generation, zero side effects/input drops и final lease 0 |
| RB-M85 | measured | plan-v4 guarded read-only identity probe declared receivers RF shield | 1 459 232 B linked flash; 152 552 B static RAM; app/factory images 1 459 632/1 525 168 B; RTC no-init 60 B; product heap total/free/min 229 156/164 412/145 016 B | board-01 `0.81.0-shield-receiver-probe`, `E-BUILD-082`/`E-AUTO-046`/`E-HIL-106`/`E-SELFTEST-003`/`E-RADIO-001`; +3 220 B linked flash, +32 B static RAM и +3 216 B images vs 0.80. Exact HIL обнаруживает два nRF24 и один CC1101 через 20 SPI bytes при zero CE-high/strobe/TX events, доказывает Full 16 pass/0 fail/1 blocked/3 N/A, unchanged storage и final lease 0 |
| RB-M86 | measured | volatile пользовательская карта spectrum activity через два nRF24 | 1 466 356 B linked flash; 152 752 B static RAM; app/factory images 1 466 768/1 532 304 B; RTC no-init 60 B; product heap total/free/min 228 956/164 212/144 816 B | board-01 `0.82.0-nrf24-spectrum`, `E-BUILD-083`/`E-AUTO-047`/`E-HIL-107`/`E-RADIO-002`; +7 124 B linked flash, +200 B static RAM и +7 136 B images vs 0.81. Exact HIL завершает 21×83-channel sweeps через два receiver, проверяет pause/resume, 99 activity hits, zero TX/CC/storage side effects, unchanged heap/storage и final lease 0 |
| RB-M87 | measured | volatile пользовательская RSSI-карта spectrum CC1101 по четырём диапазонам | 1 473 780 B linked flash; 152 928 B static RAM; app/factory images 1 474 192/1 539 728 B; RTC no-init 60 B; product heap total/free/min 228 780/164 036/144 640 B | board-01 `0.83.0-cc1101-spectrum`, `E-BUILD-084`/`E-AUTO-048`/`E-HIL-108`/`E-RADIO-003`; +7 424 B linked flash, +176 B static RAM и +7 424 B images vs 0.82. Exact HIL завершает все четыре band plan по 64 bins, проверяет стабильную pause 400 ms и resume, выполняет 354 receive samples при zero TX/PATABLE/FIFO/storage side effects, unchanged heap/storage и final lease 0 |
| RB-M88 | measured | plan-v5 active receive-only RF checks в Full/Guided | 1 478 132 B linked flash; 153 064 B static RAM; app/factory images 1 478 544/1 544 080 B; RTC no-init 60 B; product heap total/free/min 228 644/163 900/144 504 B | board-01 `0.84.0-full-guided-rf`, `E-BUILD-085`/`E-AUTO-049`/`E-HIL-109`/`E-SELFTEST-004`/`E-RADIO-004`; +4 352 B linked flash, +136 B static RAM и +4 352 B images vs 0.83. Exact HIL сохраняет Quick read-only 8/8 и Full 18 pass/0 fail/1 blocker/3 N/A после полного sweep двух nRF24 и sweep CC1101 433 МГц по 64 bins, с zero TX/storage side effects, unchanged generation, 11 reviewed TFT states и final lease 0 |
| RB-M89 | measured | plan-v6 read-only checks сохранённых Session/Library/export в Full/Guided | 1 482 568 B linked flash; 153 712 B static RAM; app/factory images 1 482 976/1 548 512 B; RTC no-init 60 B; product heap total/free/min 227 996/163 252/130 252 B | board-01 `0.85.0-full-guided-artifacts`, `E-BUILD-086`/`E-AUTO-050`/`E-HIL-110`/`E-SELFTEST-005`/`E-STORAGE-026`/`E-CAPTURE-003`; +4 436 B linked flash, +648 B static RAM и +4 432 B images vs 0.84. Exact HIL сохраняет Quick 8/8 и переводит Full на 21 pass/0 fail/1 blocker/3 N/A, read-only восстанавливает unchanged generation 83, staged-проверяет Library JSON/CSV и потоково выдаёт 16 frames/2 773 B radiotap PCAP, с zero storage writes/TX events, 12 reviewed TFT states и final lease 0. Наблюдаемое снижение heap minimum на 13 604 B сохранено и должно быть покрыто endurance, а не списано |
| RB-M90 | measured | plan-v7 exact-CID disposable Session commit/remount/export/cleanup в Full/Guided | 1 491 132 B linked flash; 154 472 B static RAM; app/factory images 1 491 536/1 557 072 B; RTC no-init 60 B; product heap total/free/min 227 236/162 492/129 276 B | board-01 `0.86.0-full-guided-disposable`, `E-BUILD-087`/`E-AUTO-051`/`E-HIL-111`/`E-SELFTEST-006`/`E-STORAGE-027`; +8 564 B linked flash, +760 B static RAM и +8 560 B images vs 0.85. Exact HIL сохраняет Quick 8/8 и переводит Full на 25 pass/0 fail/1 blocker/3 N/A, commit-ит только disposable generation 1 через три writes/504 B и шесть durability barriers, read-only remount-ит/экспортирует её, удаляет три files/scratch, сохраняет product 83/0, zero TX/product writes и final lease 0. Minimum 129 276 B на 1 796 B ниже floor RB-04 128 KiB и сохраняется как обязательная проблема endurance/heap budget, а не отменяется functional pass |
| RB-M91 | measured | final-facts heap enforcement и общий serial workspace diagnostics/storage | 1 491 172 B linked flash; 149 864 B static RAM; app/factory images 1 491 584/1 557 120 B; RTC no-init 60 B; product heap total/boot-free/final-free/min 231 844/167 100/166 884/133 884 B | board-01 `0.87.0-full-guided-heap-budget`, `E-BUILD-088`/`E-AUTO-052`/`E-HIL-112`/`E-SELFTEST-007`; +40 B linked flash, −4 608 B static RAM и +48 B images vs 0.86. Два serial-only workspace 4 608/5 120 B теперь используют один buffer 5 120 B; Quick перестраивается по final facts Full/Guided, поэтому native regression ниже floor даёт fail. Exact physical plan v7 остаётся 25/0/1/3 и теперь проходит floor 131 072 B с minimum 133 884 B/margin 2 812 B, exact disposable cleanup, product 83/0 и final lease 0. Endurance всё ещё должен доказать отсутствие monotonic degradation |
| RB-M92 | measured | calibrated touch input XPT2046, persistent calibration, shared hit targets и check plan-v8 Quick | 1 497 056 B linked flash; 149 936 B static RAM; app/factory images 1 497 456/1 562 992 B; RTC no-init 60 B; short touch HIL heap total/free/min 231 772/167 028/147 632 B | board-01 `0.88.0-touch-input`, `E-BUILD-089`/`E-AUTO-053`/`E-HIL-113`/`E-UX-013`/`E-SELFTEST-008`; +5 884 B linked flash, +72 B static RAM и +5 872 B images vs 0.87. Один real calibrated point открывает нужную строку; Quick проходит 9/9, сохранены четыре TFT states и explicit chrome misses, heap одинаков до/после, drops zero и final lease 0. Этот short focused run не заменяет endurance |
| RB-M93 | measured | cross-radio product release endurance с непересекающимися lifecycles SD/radio | 1 498 576 B linked flash; 149 936 B static RAM; app/factory images 1 498 832/1 564 512 B; exact release heap total/free/min 231 772/166 812/147 460 B | board-01 `0.89.0-touch-storage-dma`, `E-BUILD-090`/`E-AUTO-054`/`E-HIL-114`/`E-SURVEY-016`/`E-GATE-004`; +1 520 B linked flash и zero static-RAM growth против 0.88. Восемь полных Wi-Fi+BLE cycles за 2 799,845 s продвигают generation 86→94, передают 111+256=367 observations через 16 cold boots с zero drops/timeouts/heap drift и final lease 0; один bounded boot retry успешен. Это закрывает RB-04/release endurance, но не controlled physical power-cut recovery |
| RB-M94 | measured | product-first Home и вложенное сервисное меню Устройство | 1 500 384 B linked flash; 149 936 B static RAM; app/factory images 1 500 784/1 566 320 B; exact menu HIL heap total/free/min 231 772/166 812/147 460 B | board-01 `0.90.0-product-menu`, `E-BUILD-091`/`E-AUTO-055`/`E-HIL-115`/`E-UX-014`; +1 808 B linked flash, zero static-RAM growth и +1 952/+1 808 B app/factory images против 0.89. Восемь TFT states доказывают Home из шести доменов, submenu Устройство из четырёх пунктов, touch/key navigation и final lease 0; Цели/Лаборатория остаются disabled, controlled physical power cut открыт |
| RB-M95 | measured | компактный честный header SD/RF и product viewport из четырёх строк | 1 500 508 B linked flash; 149 936 B static RAM; app/factory images 1 500 912/1 566 448 B; exact menu/RF HIL heap total/free/min 231 772/166 812/147 460 B | board-01 `0.91.0-clean-status`, `E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015`; +124 B linked flash, zero static-RAM growth и +128/+128 B images против 0.90. Четыре строки 216×46 px помещаются над footer divider y=282; exact framebuffer crops доказывают idle `RF --` и real receive `RF RX`, SD остаётся `SD OK`, generation 95/0, final lease 0. Battery status и instrumented RF-silence не заявляются |
| RB-M96 | measured | full-width viewport Спектр/Водопад и bounded RF history | 1 504 500 B linked flash; 159 832 B static RAM; app/factory images 1 504 912/1 570 448 B; RTC no-init 60 B; exact dual-radio HIL heap total/free/min 221 876/156 916/137 564 B | board-01 `0.92.0-spectrum-views`, `E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/`E-RADIO-005`; +3 992 B linked flash, +9 896 B static RAM и +4 000/+4 000 B images против 0.91. Fixed history 112×83 bytes и малая metadata расходуют static delta без runtime allocation; сохранены 32 строки nRF24, 16 строк CC1101, четыре CC bands, 22 TFT states, invariant heap/storage и final lease 0 |
| RB-M97 | measured | Home из семи реализованных задач плюс host-side connected-candidate automation | 1 505 972 B linked flash; 159 856 B static RAM; app/factory images 1 506 384/1 571 920 B; RTC no-init 60 B; exact product-home HIL heap total/free/min 221 852/156 892/137 540 B | board-01 `0.93.0-product-menu`, `E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/`E-RADIO-006`; +1 472 B linked flash, +24 B static RAM и +1 472/+1 472 B images против 0.92. Firmware delta — catalog из семи пунктов, source scopes Wi-Fi/BLE и прямые receiver routes; orchestration build/flash/HIL/screenshots/verification остаётся на host и не расходует RAM устройства. Exact run сохраняет 13 TFT states, 16/8 nRF24/CC rows, unchanged heap/storage и final lease 0 |
| RB-M98 | measured | локализованный root-only Home и видимый build-derived SemVer | 1 506 228 B linked flash; 159 856 B static RAM; app/factory images 1 506 640/1 572 176 B; RTC no-init 60 B; exact bilingual Home HIL heap total/free/min 221 852/156 892/137 540 B | board-01 `0.94.0-home-identity`, `E-BUILD-095`/`E-AUTO-059`/`E-HIL-119`/`E-UX-018`; +256 B linked flash, zero static-RAM growth и +256/+256 B images против 0.93. Bounded stack buffer 24 bytes выводит `v0.94.0` из полного build ID без retained heap. Exact HIL снимает `LESHY` и `Леший`, восстанавливает русский, сохраняет 14 TFT states, unchanged heap/storage и final lease 0 |
| RB-M99 | measured | строчное представление подсказок физических клавиш на основе геометрии 0.x | 1 506 428 B linked flash; 159 856 B static RAM; app/factory images 1 506 832/1 572 368 B; RTC no-init 60 B; exact physical HIL heap total/free/min 221 852/156 892/137 540 B | board-01 `0.95.0-inline-key-hints`, `E-BUILD-096`/`E-AUTO-060`/`E-HIL-120`/`E-UX-019`; +200 B linked flash, zero static-RAM growth и +192/+192 B images против 0.94. Footer не использует retained buffer или heap allocation. Exact HIL сохраняет 14 EN/RU Home/menu/RF TFT states, unchanged storage/heap и final lease 0 |
| RB-M100 | measured | компактный contextual header/navigation на четыре строки и независимый от приёмника трёхсекундный cadence водопада | 1 507 264 B linked flash; 159 888 B static RAM; app/factory images 1 507 408/1 572 944 B; RTC no-init 60 B; exact stabilized HIL heap total/free/min 221 820/156 712/137 360 B | board-01 `0.96.0-compact-ui-waterfall`, `E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/`E-RADIO-007`; +836 B linked flash, +32 B static RAM и +576/+576 B images против 0.95. Static timing state и allocation-free cadence 26 785 мкс переиспользуют существующий ring на 112 строк; второй history не выделяется. Одна exact прошивка сохраняет 14 EN/RU Home/menu/RF states и измеряет полное host fill 2,905…2,927 s на nRF24 и CC315/433/868/915 при invariant stabilized heap, unchanged storage, zero TX/storage/input drops и final lease 0 |
| RB-M103 | measured | receiver-paced exact-pixel RF raster, Wi-Fi modes Сигнал/Трафик, приём всеми доступными nRF и non-blocking idle touch | 1 510 960 B linked flash; 205 296 B static RAM; app/factory images 1 511 360/1 576 896 B; exact stabilized HIL heap total/free/min 176 412/111 372/92 020 B | board-01 `0.99.0-wifi-spectrum-modes`, `E-BUILD-100`/`E-AUTO-064`/`E-HIL-124`/`E-UX-023`/`E-RADIO-010`; +3 696 B linked flash, +45 408 B static RAM и +3 952/+3 952 B images против 0.96. Fixed history теперь равен physical eight-bit raster 240×224 (53 760 B) без runtime allocation. Один полный sweep создаёт одну строку, поэтому full-history time ограничен приёмником, а не display timer: host 2,344/2,373 s для nRF Сигнал/Трафик и 32,793/22,857/31,438/31,595 s для CC315/433/868/915. Все paths имеют zero skipped measurements, exact run не использует recovery, сохраняет generation 95/0 и завершает lease 0. Short-run minimum 92 020 B ниже исторического Survey floor RB-04 128 KiB; поэтому focused display/RF checkpoint не заменяет принятый endurance 0.89, а большой raster требует нового mixed-workload budget review, если будет присутствовать в таком workload |
| RB-M104 | measured | source-bin history водопада с display expansion при render | 1 510 900 B linked flash; 170 128 B static RAM; app/factory images 1 511 312/1 576 848 B; exact stabilized HIL heap total/free/min 211 580/146 472/127 120 B | board-01 `0.100.0-spectrum-source-history`, `E-BUILD-101`/`E-AUTO-065`/`E-HIL-125`/`E-UX-024`/`E-RADIO-011`; −60 B linked flash, −35 168 B static RAM и −48/−48 B images против 0.99. Ring на 224 строки хранит максимум 83 однобайтовых receiver bins на строку (18 592 B); renderer отображает source bins в display scanline 240 px без interpolation. Exact HIL сохраняет один полный sweep на физическую строку, шесть paths с zero skipped, все три nRF slot и zero retry/recovery CC; host fill равен 2,083/2,346 s для nRF Сигнал/Трафик и 32,977/22,488/31,699/31,874 s для CC315/433/868/915, максимальный измеренный render строки — 611 us. Short focused minimum восстанавливается на 35 100 B до 127 120 B, что на 3 952 B ниже исторического Survey floor 128 KiB; для mixed workload остаётся авторитетным принятый endurance 0.89, а будущие изменения mixed workload всё ещё требуют budget review |
| RB-M105 | measured | изолированный six-boundary physical power-cut protocol и exact-device runner | 1 512 700 B linked flash; 170 128 B static RAM; app/factory images 1 512 848/1 578 384 B; exact product HIL heap total/free/min 211 580/146 472/127 120 B | board-01 `0.101.0-power-cut-harness`, `E-BUILD-102`/`E-AUTO-066`/`E-HIL-126`/`E-STORAGE-028`/`E-GATE-005`; +1 800 B linked flash, zero static-RAM growth и +1 536/+1 536 B images против 0.100. Шесть реальных отключений на 5,216…6,589 s read-only восстанавливают generations 1/1/1/1/1/2 с zero recovery writes/syncs, unchanged product 95/0 и final lease 0; exact source/candidate/CID/USB identity связаны. Это закрывает power-cut evidence RB-06 для общего SessionStore на одной паре board/card, а не совместимость всех носителей |
| RB-M106 | measured | main-loop safety supervisor, retained Safe Mode и destructive exact-device watchdog runner | 1 534 668 B linked flash; 171 496 B static RAM; app/factory images 1 535 072/1 600 608 B; normal HIL heap total/free/min 209 956/144 688/125 496 B; Safe Mode heap 209 956/161 296/160 256 B; RTC no-init 108 B | board-01 `0.103.0-safety-supervisor`, `E-BUILD-104`/`E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001`; +6 832 B linked flash, +96 B static RAM и +6 980/+7 236 B images против 0.102. Настоящий Task-WDT сбрасывает через 5 810,775 ms, retained Safe Mode переживает software restart, exact catalog 95/0 неизменен, final lease 0. Dedicated IRAM region 16 384 B занят на 100% без запаса; любой дальнейший рост IRAM сначала требует освободить или явно перебюджетировать место |
| RB-M107 | measured | passive infrared RAW/NEC Capture, SessionStore v6/CSV и declarative HIL scenario engine | 1 549 056 B linked flash; 172 760 B static RAM; app/factory images 1 549 456/1 614 992 B; exact HIL heap total/free/min 208 692/143 256/124 160 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.104.0-infrared-capture`, `E-BUILD-105`/`E-AUTO-069`/`E-HIL-129`/`E-RADIO-013`/`E-STORAGE-030`; +14 388 B linked flash, +1 264 B static RAM и +14 384/+14 384 B images против 0.103. Exact no-signal path выполняет 345 272 samples GPIO21 за 10 000 018 us с zero transitions, TX и writes, удерживает GPIO14 и все nRF CE LOW, сохраняет catalog 95/0 и heap, фиксирует семь TFT states и заканчивает Home с lease 0. Successful physical-signal decode/persistence остаётся открыт до fixture на второй плате |
| RB-M108 | measured | outcome-first product copy, presentation результата и retained multi-flow visual gate | 1 551 752 B linked flash; 172 760 B static RAM; app/factory images 1 552 008/1 617 696 B; exact HIL heap total/free/min 208 692/143 256/124 160 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.106.0-product-content`, `E-BUILD-106`/`E-AUTO-070`/`E-HIL-130`/`E-UX-025`; +2 696 B linked flash, zero static-RAM growth и +2 552/+2 704 B images против 0.104. Одна fresh flash и три exact-hash reuse runs сохраняют 37 TFT states по product routes; supplementary visual Wi-Fi Capture run не экспортирует PCAP и пишет zero SD bytes. Exact CID/catalog/heap и final lease 0 не меняются; у IRAM нет запаса роста |
| RB-M109 | measured | bounded catalog «Сети рядом» и финальные Wi-Fi menu/list/detail | 1 558 808 B linked flash; 175 168 B static RAM; app/factory images 1 558 552/1 624 240 B; post-warm exact HIL heap total/free/min 206 284/140 032/76 084 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.107.0-wifi-networks`, `E-BUILD-107`/`E-AUTO-071`/`E-HIL-131`/`E-UX-026`; +7 056 B linked flash, +2 408 B static RAM и +6 544/+6 544 B images против 0.106. Allocation-free BSSID catalog на 32 записи имеет stable insertion order и bounded replacement. Fresh boot показывает одноразовую warm allocation ESP-IDF Wi-Fi 816 B; три независимых post-warm endpoint и обе границы полного lifecycle byte-identical. Два физических lifecycle находят 13, затем 20 уникальных сетей с zero drops/writes и final lease 0; запаса IRAM по-прежнему нет |
| RB-M110 | measured | passive Wi-Fi client decoder, bounded catalog «Устройства» и list/detail | 1 566 368 B linked flash; 178 360 B static RAM; app/factory images 1 566 512/1 632 048 B; post-warm exact HIL heap total/free/min 203 092/137 032/75 112 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.108.0-wifi-devices`, `E-BUILD-108`/`E-AUTO-072`/`E-HIL-132`/`E-UX-027`; +7 560 B linked flash, +3 192 B static RAM и +7 960/+7 808 B images против 0.107. Fixed storage добавляет ingress queue на 64 frames и catalog на 32 clients; runtime monitoring остаётся volatile/NVS-disabled и allocation-free в app path. Два физических lifecycle имеют byte-identical post-warm heap, видят реальные clients на всех 13 каналах при zero drops/writes, не меняют static chrome/detail и завершаются lease 0; запаса IRAM по-прежнему нет |
| RB-M111 | measured | passive Wi-Fi airtime aggregation и график «Каналы» | 1 570 480 B linked flash; 179 680 B static RAM; app/factory images 1 570 880/1 636 416 B; post-warm exact HIL heap total/free 201 772/135 712 B, minimum floor 73 776 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.109.0-wifi-channels`, `E-BUILD-109`/`E-AUTO-073`/`E-HIL-133`/`E-UX-028`; +4 112 B linked flash, +1 320 B static RAM и +4 368/+4 368 B images против 0.108. Delta включает bounded state на 13 bins и 1 KiB дополнительной shared diagnostic capacity. Два физических lifecycle измеряют все каналы со стабильными post-warm total/free heap, zero writes, inactive buzzer и final lease 0; IRAM остаётся заполненной |
| RB-M112 | measured | прямой route записи пакетов Wi-Fi и changed-metric-only live UI | 1 571 740 B linked flash; 179 680 B static RAM; app/factory images 1 572 144/1 637 680 B; post-warm exact HIL heap total/free 201 772/135 712 B, minimum floor 73 824 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.110.0-wifi-capture`, `E-BUILD-110`/`E-AUTO-074`/`E-HIL-134`/`E-UX-029`/`E-CAPTURE-004`; +1 260 B linked flash, zero static RAM и +1 264/+1 264 B images против 0.109. Product route переиспользует существующий bounded Capture 16×256 B и single-workspace PCAP/persistence path, не добавляя payload buffer. Два физических lifecycle имеют byte-identical post-warm heap, меняют только live metric rows, privacy cancel выполняет zero writes, final lease — 0; IRAM остаётся заполненной |
| RB-M113 | measured | bounded passive BLE-catalog «Устройства рядом» и прямой list/detail UI | 1 579 464 B linked flash; 182 080 B static RAM; app/factory images 1 579 872/1 645 408 B; post-warm exact HIL heap total/free/min 199 372/133 652/60 324 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.111.0-ble-nearby`, `E-BUILD-111`/`E-AUTO-075`/`E-HIL-135`/`E-UX-030`; +7 724 B linked flash, +2 400 B static RAM и +7 728/+7 728 B images против 0.110. Allocation-free catalog хранит максимум 32 адреса и обновляет только изменившиеся строки. Два physical lifecycle byte-identical после warm-up, принимают 30, затем 32 уникальных устройства при zero drops, не трогают static chrome и открытый detail, выполняют zero writes и заканчивают с lease 0; IRAM остаётся заполненной |
| RB-M114 | measured | allocation-free порядок по убыванию сигнала для каждого живого списка radio objects | 1 578 308 B linked flash; 182 080 B static RAM; app/factory images 1 578 720/1 644 256 B; exact HIL heap total/free/min 199 372/133 652/61 208 B для BLE и 199 372/133 088/61 208 B для обеих Wi-Fi-задач; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.112.0-signal-order`, `E-BUILD-112`/`E-AUTO-076`/`E-HIL-136`/`E-UX-031`; −1 156 B linked flash, zero static RAM и −1 152/−1 152 B images против 0.111. Stable insertion sort работает в существующих fixed arrays на 32 записи; sort buffer или heap allocation не добавлены. Один fresh и два same-hash reuse run доказывают strongest-first для всех трёх каталогов, zero drops, byte-stable post-warm heap, data-only live redraw и final lease 0; IRAM остаётся заполненной |
| RB-M115 | measured | компактные факты radio objects и общая qualitative/numeric шкала сигнала | 1 578 716 B linked flash; 182 080 B static RAM; app/factory images 1 579 120/1 644 656 B; exact HIL heap total/free/min 199 372/133 652/61 292 B для BLE и 199 372/133 088/61 292 B для обеих Wi-Fi-задач; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.113.0-dense-details`, `E-BUILD-113`/`E-AUTO-077`/`E-HIL-137`/`E-UX-032`; +408 B linked flash, zero static RAM и +400/+400 B images против 0.112. Один shared renderer и девять localized strings заменяют три технических счётчика без dynamic allocation. Один fresh и два same-hash reuse run сохраняют 17 TFT states, byte-stable post-warm heap, zero detail/chrome changes, zero radio drops/writes и final lease 0; IRAM остаётся заполненной |
| RB-M116 | measured | identity-stable navigation «Сети рядом» при live RSSI updates | 1 579 500 B linked flash; 182 312 B static RAM; app/factory images 1 579 904/1 645 440 B; exact Wi-Fi HIL heap total/free/min 199 140/132 888/69 084 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.114.0-stable-network-nav`, `E-BUILD-114`/`E-AUTO-078`/`E-HIL-138`/`E-UX-033`; +784 B linked flash, +232 B static RAM и +784/+784 B images против 0.113. Fixed snapshot 32×BSSID не использует allocation. Один fresh run фиксирует 23 строки, выдерживает восемь actions, ещё два scan и 28 catalog revisions с byte-stable post-warm heap, неизменными order/selection identity, zero chrome/detail changes/writes и final lease 0; IRAM остаётся заполненной |
| RB-M117 | measured | пассивный Wi-Fi device fingerprint, полная IEEE MA-L lookup и selected-channel live radar | 2 874 880 B linked flash; 198 568 B static RAM; app/factory images 2 875 280/2 940 816 B; exact Wi-Fi HIL heap total/free/min 182 884/116 892/55 004 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.115.0-wifi-device-intelligence`, `E-BUILD-115`/`E-AUTO-079`/`E-HIL-139`/`E-UX-034`; +1 295 380 B linked flash, +16 256 B static RAM и +1 295 376/+1 295 376 B images против 0.114. Закреплённая таблица IEEE MA-L 1 279 488 B находится во flash и binary-searched без heap; catalog на 32 устройства хранит bounded WPS/SSID/rate/generation/range facts. Один fresh run находит 2→3 клиента, фиксирует identity/channel 4, принимает update выбранного клиента, сохраняет passport/chrome, выполняет zero writes и заканчивает lease 0. Minimum free heap на 14 080 B ниже 0.114 и существенно ниже исторического Survey floor 128 KiB, поэтому авторитетом остаётся mixed-workload release endurance, а будущие identity fields не должны добавлять unbounded memory; IRAM остаётся заполненной |
| RB-M118 | measured | session mean канала, gray/current overlay и выбор свободного канала по среднему | 2 874 896 B linked flash; 198 800 B static RAM; app/factory images 2 875 296/2 940 832 B; exact Wi-Fi HIL heap total/free/min 182 652/116 660/54 724 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.116.0-wifi-channel-average`, `E-BUILD-116`/`E-AUTO-080`/`E-HIL-140`/`E-UX-035`; +16 B linked flash, +232 B static RAM и +16/+16 B images против 0.115. Тринадцать 64-bit sums с bounded dwell counts и тринадцать rendered averages fixed и allocation-free. Fresh run доказывает 2→3 полных sweep, видимые серые средние, выбор 1/6/11 по среднему, 509 dynamic/zero static changed pixels, byte-identical post-warm total/free heap, zero writes и final lease 0. Focused minimum на 280 B ниже 0.115, поэтому accepted mixed-workload release endurance остаётся авторитетным; IRAM остаётся заполненной |
| RB-M119 | measured | integrated identity Wi-Fi-устройства и live signal выбранного канала | 2 875 204 B linked flash; 198 800 B static RAM; app/factory images 2 875 360/2 940 896 B; exact Wi-Fi HIL heap total/free/min 182 652/116 660/54 724 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.117.0-wifi-device-live-detail`, `E-BUILD-117`/`E-AUTO-081`/`E-HIL-141`/`E-UX-036`; +308 B linked flash, zero static RAM и +64/+64 B images против 0.116. Удаление отдельного radar state не добавляет buffer или heap allocation. Fresh HIL принимает два update выбранного клиента на locked channel 12, меняет 2 120 live и zero identity/chrome pixels, сохраняет exact post-warm total/free heap, пишет zero bytes и заканчивает lease 0. Focused minimum 54 724 B остаётся существенно ниже исторического Survey floor 128 KiB, поэтому mixed-workload release endurance остаётся авторитетным; IRAM остаётся заполненной |
| RB-M120 | measured | пассивный паспорт Wi-Fi-сети, vendor lookup и монотонное раскрытие hidden SSID | 2 890 164 B linked flash; 209 200 B static RAM; app/factory images 2 890 320/2 955 856 B; exact Wi-Fi HIL heap total/free/min 172 252/104 532/41 148 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.118.0-wifi-network-intelligence`, `E-BUILD-118`/`E-AUTO-082`/`E-HIL-142`/`E-UX-037`; +14 960 B linked flash, +10 400 B static RAM и +14 960/+14 960 B images против 0.117. Fixed facts observation/scan/catalog несут auth/ciphers/channel width/PHY/WPS/FTM/antenna/country metadata и переиспользуют flash-resident MA-L table на 39 984 записи; fail-closed diagnostic capacity увеличена на 1 KiB после сохранённого `state_overflow`. Fresh HIL находит 15→19 сетей, проверяет паспорт Hewlett Packard, byte-stable post-warm total/free heap, zero writes и final lease 0. Hidden→known SSID по BSSID native-tested; ambient run увидел zero resolutions. Focused minimum 41 148 B на 13 576 B ниже 0.117 и не заменяет mixed-workload release endurance; IRAM остаётся заполненной |
| RB-M121 | measured | встроенный BSSID-bound live-радар Wi-Fi-сети | 2 891 428 B linked flash; 209 464 B static RAM; app/factory images 2 891 840/2 957 376 B; exact Wi-Fi HIL heap total/free/min 171 988/104 256/40 540 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.119.0-wifi-network-live-radar`, `E-BUILD-119`/`E-AUTO-083`/`E-HIL-143`/`E-UX-038`; +1 264 B linked flash, +264 B static RAM и +1 520/+1 520 B images против 0.118. Главный RAM delta — 32 fixed signal-stat records, перемещающиеся вместе со своими BSSID slots; sample count, min/max и последний trend allocation-free и сбрасываются при входе. Fresh HIL продвигает реальную Keenetic record 4→5 samples и −71→−70 dBm, меняет 86 radar/zero outside pixels, сохраняет byte-identical post-warm total/free heap, пишет zero bytes и заканчивает lease 0. Focused minimum на 608 B ниже 0.118 и не заменяет mixed-workload release endurance; IRAM остаётся заполненной |
| RB-M122 | measured | all-channel рекомендация Wi-Fi по видимому среднему и highlight выбранной подписи оси | 2 891 648 B linked flash; 209 464 B static RAM; app/factory images 2 892 048/2 957 584 B; exact Wi-Fi HIL heap total/free/min 171 988/104 460/40 464 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.120.0-wifi-channel-choice`, `E-BUILD-120`/`E-AUTO-084`/`E-HIL-144`/`E-UX-039`; +220 B linked flash, zero static RAM и +208/+208 B images против 0.119. Ranking переиспользует 13 существующих fixed средних, считает давление соседей на stack и не хранит новый state. Fresh HIL измеряет все каналы, рекомендует/подсвечивает 13 после 2 и 3 sweep, меняет 1 195 dynamic/zero посторонних static pixels, сохраняет byte-identical post-warm total/free heap, пишет zero bytes и заканчивает lease 0. Focused minimum на 76 B ниже 0.119 и не заменяет mixed-workload release endurance; IRAM остаётся заполненной |
| RB-M123 | measured | channel-neutral palette текущей загрузки Wi-Fi | 2 891 644 B linked flash; 209 464 B static RAM; app/factory images 2 892 048/2 957 584 B; exact Wi-Fi HIL heap total/free/min 171 988/104 460/34 996 B; RTC no-init 108 B; IRAM 16 384/16 384 B | board-01 `0.121.0-wifi-channel-neutral-bars`, `E-BUILD-121`/`E-AUTO-085`/`E-HIL-145`/`E-UX-040`; −4 B linked flash, zero роста static RAM/images против 0.120. Удаление identity канала из функции цвета не добавляет state или allocation. Fresh HIL измеряет все 13 каналов, рекомендует 13 после 2 и 3 sweep, меняет 998 live/zero static pixels, сохраняет byte-identical post-warm total/free heap, пишет zero bytes и заканчивает lease 0. Focused minimum не заменяет mixed-workload release endurance; IRAM остаётся заполненной |
| RB-M124 | measured | passive BLE advertisement intelligence, company lookup и встроенный radar | 3 049 684 B linked flash; 228 688 B static RAM; app/factory images 3 050 096/3 115 632 B; exact BLE HIL heap total/free/min 152 764/82 248/9 760 B; dedicated DIRAM 309 456/341 760 B (90,55%, остаётся 32 304 B) | board-01 `0.122.2-ble-device-intelligence`, `E-BUILD-122`/`E-AUTO-086`/`E-HIL-146`/`E-UX-041`; +158 040 B linked flash, +19 224 B static RAM и +158 048/+158 048 B images против 0.121. Flash asset 128 384 B хранит 4 012 assigned companies; bounded advertisement facts расширяют shared Observation/queue/session/catalog state. Два physical lifecycle имеют byte-identical post-warm heap, zero drops/writes и final lease 0, но historical minimum 9 760 B намного ниже RB-04. Этот focused functional checkpoint явно не заменяет accepted endurance 0.89; после изменения baseline feature set обязательны mixed-workload memory consolidation и новый release-budget run |
| RB-M125 | measured | пассивный all-receiver finder сигнала nRF24 | 3 055 192 B linked flash; 229 448 B static RAM; app/factory images 3 055 600/3 121 136 B; exact nRF24 HIL heap total/free/min 152 004/81 772/67 540 B; dedicated DIRAM 310 216/341 760 B (90,77%, остаётся 31 544 B) | board-01 `0.123.0-nrf24-signal-finder`, `E-BUILD-123`/`E-AUTO-087`/`E-HIL-147`/`E-UX-042`; +5 508 B linked flash, +760 B static RAM и +5 504/+5 504 B images против 0.122.2. Fixed state baseline/response на 83 bin, product route, diagnostics и HIL surface остаются allocation-free. Focused physical minimum ниже RB-04 и не заменяет mixed-workload release endurance |
| RB-M126 | measured | passive wide-span finder частоты CC1101 с robust ambient rejection | 3 060 648 B linked flash; 233 288 B static RAM; app/factory images 3 061 056/3 126 592 B; exact CC1101 HIL heap total/free/min 148 164/77 932/63 700 B; dedicated DIRAM 314 056/341 760 B (91,89%, остаётся 27 704 B) | board-01 `0.124.1-cc1101-frequency-finder`, `E-BUILD-124`/`E-AUTO-088`/`E-HIL-148`/`E-UX-043`; +5 456 B linked flash, +3 840 B static RAM и +5 456/+5 456 B images против 0.123. Три fixed arrays по 1 099 bins (baseline, raw rise и held response), projection 240 columns и diagnostics остаются allocation-free. Два ambient run сохраняют heap, отвергают retained false peaks predecessor и заканчивают lease 0. Focused minimum ниже RB-04 и не заменяет mixed-workload release endurance |
| RB-M127 | measured build / physical open | product IR Library metadata плюс отдельный two-board NEC fixture foundation | product 3 061 504 B linked flash; 233 288 B static RAM; app/factory images 3 061 904/3 127 440 B; dedicated DIRAM неизменна: 314 056/341 760 B (91,89%, остаётся 27 704 B). Отдельный fixture: 322 215 B linked flash; 22 724 B static RAM; app/factory 322 624/388 160 B; DIRAM 74 519/341 760 B | непрошитый source `0.125.0-ir-fixture-foundation` / fixture `0.1.0-ir-nec`, `E-BUILD-125`/`E-AUTO-089`, source `f1b3394`; product delta против 0.124.1 равен +856 B linked flash, zero static RAM и +848/+848 B images. Бюджет отдельного fixture никогда не входит в product image. Physical heap и two-board result ещё отсутствуют, поэтому RB-04 и accepted endurance 0.89 не заменяются |
| RB-M128 | measured build + physical positive | pre-app safety guard, physical IR envelope tolerance и closed-loop NEC двух плат | product 3 062 560 B linked flash; 233 288 B static RAM; app/factory images 3 062 960/3 128 496 B; RTC no-init 128 B; physical heap total/free/min 148 164/77 932/63 700 B. Fixture остаётся 322 215 B linked flash и 22 724 B static RAM | board-01/02 `0.129.0-pre-app-watchdog`, `E-BUILD-129`/`E-AUTO-093`/`E-HIL-150`/`E-RADIO-014`/`E-STORAGE-031`; +1 056 B linked flash, zero static-RAM growth и +1 056/+1 056 B images против 0.125. Physical run сохраняет heap invariant через NEC receive/save/cold reopen, но focused minimum 63 700 B ниже RB-04 и не заменяет mixed-workload endurance |
| RB-M129 | measured diagnostic build + physical localization | isolated-main characterization shared MISO со всеми подавленными receiver operations | product-derived diagnostic 3 063 436 B linked flash; 233 288 B static RAM; app/factory images 3 063 840/3 129 376 B; dedicated DIRAM 314 056/341 760 B (91,89%, остаётся 27 704 B); isolated physical heap total/free/min 148 164/78 440/78 440 B | board-02 `0.131.0-isolated-main-miso`; +876 B linked flash, zero static RAM и +880/+880 B images против exact product 0.129. Retained run samples только GPIO13, clocks zero SPI bytes, выполняет zero receiver/TX operations и заканчивает Home/lease 0. Его более высокий focused heap minimum относится только к diagnostic и не продвигает product, не заменяет RB-04 или mixed-workload release endurance |
| RB-M130 | measured build + focused physical safety | allocation-free deadline state и первый trip/restart/clear Wi-Fi worker Product Survey | 3 066 128 B linked flash; 233 360 B static RAM; app image 3 066 528 B; boot-before exact HIL heap total/free/min 148 092/77 860/63 628 B | board-01 `0.133.0-worker-deadline-supervision`, `E-BUILD-133`/`E-AUTO-094`/`E-HIL-154`/`E-SAFETY-002`; +3 568 B linked flash и +72 B static RAM против exact product 0.129. Один arm Wi-Fi worker/два heartbeat/один trip чисто снимают lease и переживают restart. Этот fault-focused run не выполняет normal mixed Survey workload и не заменяет RB-04/release endurance |
| RB-M131 | measured build + normal/fault-focused physical safety | BLE-calibrated дедлайн Product Survey с normal cycle плюс trip/restart/clear | 3 066 124 B linked flash; 233 360 B static RAM; app image 3 066 528 B; boot-before exact HIL heap total/free/min 148 092/77 860/63 628 B | board-01 `0.134.0-ble-worker-deadline`, `E-BUILD-134`/`E-AUTO-095`/`E-HIL-155`/`E-SAFETY-003`; −4 B linked flash и zero delta static RAM/image против 0.133. Один normal BLE cycle принимает 34/34 с zero drops/retries и без ложного trip при bound 6,1 s ниже дедлайна 8 s; второй lifecycle срабатывает через 8 001 ms и чисто снимает lease. Этот focused run не выполняет normal mixed Survey workload и не заменяет RB-04/release endurance |

| RB-M132 | measured build + normal/fault-focused physical safety | deadline preparation/admission Product Survey до calibrated boundary workers Wi-Fi+BLE | 3 067 656 B linked flash; 233 360 B static RAM; app image 3 068 064 B; boot-before exact HIL heap total/free/min 148 092/77 860/63 628 B | board-01 `0.135.0-survey-preparation-deadline`, `E-BUILD-135`/`E-AUTO-096`/`E-HIL-156`/`E-SAFETY-004`; +1 532 B linked flash, +1 536 B image и zero static-RAM delta против 0.134. Normal BLE lifecycle взводит preparation, затем worker, принимает 30/30 с zero scan drops/retries и без ложного trip; pre-hardware stall 10 s срабатывает на preparation через 8 001 ms и чисто снимает lease. Этот focused run не выполняет normal mixed Survey workload и не заменяет RB-04/release endurance |
| RB-M133 | measured build + normal/fault-focused physical safety | deadline worker Wi-Fi Capture Store плюс консолидация workspaces без PSRAM | 3 059 360 B linked flash; 207 928 B static RAM; app image 3 059 760 B; boot-before exact HIL heap total/free/min 173 524/103 248/89 060 B | board-01 `0.136.0-capture-store-deadline`, `E-BUILD-136`/`E-AUTO-097`/`E-HIL-157`/`E-SAFETY-005`; −8 296 B linked flash, −25 432 B static RAM и −8 304 B image против 0.135. Lifecycle-exclusive workspaces Session/FatFs используются совместно. Normal Capture Store монтирует при 93 544 B free heap, largest block 32 756 B и error zero, сохраняет 2 frames/433 B и продвигает generation 98→99; pre-storage stall 10 s срабатывает через 8 001 ms с zero writes и чисто снимает lease. Этот focused run не выполняет normal mixed workload и не заменяет RB-04/release endurance |
| RB-M135 | measured build + normal/fault-focused physical safety | deadline worker IR Capture Store плюс no-OS restart Safe Mode | 3 061 508 B linked flash; 207 960 B static RAM; app/factory images 3 061 920/3 127 456 B; normal pre-mount heap free/largest 94 136/51 188 B | board-01 `0.138.0-safety-restart-noos`, `E-BUILD-138`/`E-AUTO-099`/`E-HIL-159`/`E-SAFETY-006`; +12 B linked flash, zero static RAM и +16/+16 B image против 0.137. Normal NEC Save продвигает generation 106→107; pre-storage stall 10 s срабатывает через 8 001 ms с zero writes, no-OS restart возвращается за 947,445 ms, final lease равен нулю. Этот focused run не выполняет normal mixed workload и не заменяет RB-04/release endurance |

`heap_min_free` probe относится только к короткой diagnostic run. Он не предсказывает
буферы Wi-Fi/BLE, display caches, Session queues, storage transactions или Survey
gate ≥45 минут/≥8 циклов. Размер 0.x включает legacy functionality и feasibility
contracts, поэтому не задаёт форму clean platform.

## Временные guardrails 1.x

Это причины для review, а не evidence выполнения продуктом NFR.

| ID | Guardrail | Обоснование / закрытие |
|---|---|---|
| RB-01 | Ни один обязательный путь не зависит от PSRAM | board-01/BOM задают N16/no-PSRAM; память N16R8 board-02 конфликтует с display pins и доказывает, что одной ROM capacity недостаточно для расширения portable envelope |
| RB-02 | Сохранить два bootable app slots и не менее 12,5% свободного места в выбранном slot | сохраняет OTA/rollback и рост; финальные значения задаст partition ADR |
| RB-03 | Clean S2 platform: static RAM ≤ 96 KiB и free internal heap ≥ 240 KiB после interactive boot | оставляет место первому radio/storage slice; измеряется на independent target |
| RB-04 | S3 passive Survey steady state: free internal heap ≥ 160 KiB и minimum ≥ 128 KiB без нисходящего тренда за ≥45 минут и ≥8 полных release cycles | резерв для bounded workers/parsers/export; закрывается в часовом endurance budget через heap time series и queue high-water marks |
| RB-05 | Interactive UI ≤ 2 с после cold boot; UI callbacks ≤ 10 мс; Back/release lease ≤ 150 мс | существующие NFR-001…003; закрывается device timestamps и внешним HIL timing |
| RB-06 | Sustained storage throughput ≥ 4× measured p99 ingress выбранного source set; commit/power-cut сохраняет все ранее committed records | вместо произвольной SD-only цифры; source rate, SD и LittleFS измеряются отдельно |
| RB-07 | 10 000 переходов radio→storage→radio дают ноль bus errors, inactive non-owner CS и ноль leaked leases | transaction policy закрывается только HW-T03/HW-T05 trace evidence |
| RB-08 | Unmeasured receiver combination не включается по умолчанию; принятые combinations проходят endurance без brownout/reset внутри measured regulator/thermal limits | power numbers требуют HW-T10; отсутствие прибора сужает scope, а не создаёт вымышленную capacity |

## Матрица закрытия измерений

| Область | Текущее состояние | Следующее воспроизводимое измерение | Влияние на gate |
|---|---|---|---|
| Flash/static RAM | platform/runtime до exact 0.104, Survey UI, codec, SessionStore v6 с RAW/IR pulses, persistent Library/export, SD metadata, guarded FAT persistence/reset/power-cut, Wi-Fi/BLE, receiver views, safety supervisor и passive IR capture измерены; exact 0.104 использует 172 760 B static RAM и 1 549 056 B linked flash внутри app slot 4 MiB, но dedicated IRAM region 16 384 B не имеет свободных bytes | освободить или явно перебюджетировать IRAM до добавления следующего ISR-resident кода; сохранять exact size/map deltas при добавлении полных module workflows S5 без перемещения product partition | lower bound S1; S2–S4 приняты; S5 отслеживается с critical constraint по IRAM headroom |
| Runtime heap/queues | lease lifecycle измерен на 1 000 UI cycles; exact 0.89 проходит 8 полных Wi-Fi+BLE→SD→Library cycles за 2 799,845 s с 367 forwarded observations, zero drops и invariant heap 231 772/166 812/147 460 B | сохранять exact-candidate check в каждом release workflow и расширять его только когда новый enabled source меняет workload | RB-04 и endurance gate S4 приняты |
| Boot/UI latency | capability-built home interactive-ready 0,373 с и TFT capture measured | измерить внешний cold power-on и поздние product services, не только device milestone | блокирует final verification NFR-001, не bootstrap S2 |
| Storage throughput/atomicity | bounded SessionStore matrices, guarded FAT/remount/reset, isolated LittleFS recovery, endurance exact 0.89 и six-boundary physical power-cut exact 0.101 измерены; exact 0.102 host-tests покрывают commit/reopen/corrupt rejection RAW pulses schema v5, а physical no-save path сохраняет product 95/0 при zero writes | доказать known physical RAW burst через explicit atomic save и cold Library CSV, затем повторять common recovery evidence только при изменении общего store/media policy | slice PR-005/RB-06 S4 принят для одной board/card; persistence CAP-030 и recovery evidence release candidate S8 остаются открыты |
| Shared bus | только identity reads | 10 000 transitions с logic trace, error counters и post-test identities | блокирует RB-07 и принятие coexistence ADR |
| Power/thermal | unknown, прибора нет | idle/backlight/SD/каждый passive receiver/combined rail min-avg-peak и temperature | ограничивает combinations по RB-08; не блокирует Wi-Fi-first platform work |

## Доступные решения

- Clean target 1.x конфигурируется без PSRAM, а profile mismatch становится fault.
- Passive Wi-Fi остаётся кандидатом первого Survey source: он проверяет end-to-end
  workflow без unresolved shield bus и external assemblies.
- Числа HIL probe и 0.x ограничивают поле текущего evidence, но не являются target
  budget.
- Automated probe UI проходит RB-03: 26 388 B static RAM и 341 492 B free heap;
  storage/runtime и Survey должны сохранить guardrail через measured deltas.
- Первый runtime lease path проходит RB-05 для acknowledgement Back/release на
  1 000 циклах и возвращается к точным значениям free/minimum heap до прогона.
- Bounded Session-codec target остаётся внутри RB-03/RB-04: 48 628 B static RAM и
  319 252 B free heap; delta 17 472 B — fixed self-check workspace, а не evidence
  filesystem transaction cost или endurance.
- Two-generation RAM SessionStore target остаётся внутри RB-03/RB-04: 74 148 B
  static RAM и 293 732 B free heap. Дополнительные 25 520 B намеренно удерживают
  второй maximum-size diagnostic generation; physical adapter измерит свой cache.
- Offline Library target остаётся внутри RB-03/RB-04: 79 132 B static RAM и
  288 748 B free heap. Delta 4 984 B добавляет bounded controller и caller-owned
  reopen result; первая реализация со stack copy была отклонена.
- Bounded export target остаётся внутри RB-03/RB-04: 79 772 B static RAM и
  288 108 B free heap. Delta 640 B — static serial artifact buffer; стоимость
  filesystem cache или persistence здесь не представлена.
- Read-only discovery target остаётся внутри RB-03/RB-04: 80 588 B static RAM и
  287 292 B free heap. Delta 816 B покрывает record/formatter и board adapter;
  стоимость SD driver, filesystem cache или persistence здесь не представлена.
- Mount policy добавляет 1 016 B linked flash без delta static RAM/heap. Неизменная
  memory подтверждает, что SD driver или filesystem cache не запускались.
- RO protocol plan добавляет 884 B linked flash и 512 B static RAM для report;
  SPI/SD driver или filesystem cache всё ещё не запускаются.
- Guarded FAT SessionStore остаётся ровно внутри RB-03 с 94 996 B static RAM и
  272 648 B free heap после boot. Delta относительно 0.27 — 72 648 B linked flash и
  4 992 B static RAM — включает SDFS/FatFs и physical adapter; observed minimum
  237 716 B короткого postflight ниже guardrail RB-03 по free heap и требует review
  до S2, а не считается endurance result.
- ESP-IDF SDSPI images 0.29/0.30 использовали 99 932 B static RAM — на 1 628 B выше
  временного ceiling RB-03. Map review нашёл redundant physical-recovery
  `SurveySession` 4 672 B; 0.31 переиспользует существующий caller-owned validation
  session и снижается до 95 260 B, на 3 044 B ниже RB-03. Guarded boundary-6
  reset/recovery проходит на shared workspace. FatFs workspace остаётся caller-owned,
  а не скрывается в loop stack.
- Linking первого passive Wi-Fi source со storage measurement image добавляет
  18 340 B static RAM и 395 209 B linked flash. Version 0.32 — S3 source slice, а не
  clean S2 platform: она превышает RB-03, но post-run minimum heap 186 376 B остаётся
  выше floor RB-04 128 KiB. p99 ingress 32 scans требует 2 184 B/s по RB-06, показывая
  необходимость bounded batching вместо sync после каждого scan.
- Fixed queue/policy добавляет 600 B static RAM к combined source/storage image.
  Synthetic 64-observation batching даёт 9 068 encoded B/s и закрывает RB-06 с
  запасом 4,15×; это service-rate evidence, не замена real Wi-Fi→queue→SD HIL.
- Real fixed ring в 0.34 добавляет 4 672 B static RAM; postflight minimum heap
  149 308 B остаётся выше floor RB-04 128 KiB, но headroom всего 18 236 B. До
  product UI/background workers нужен map/heap review и отказ от дублирования full
  Session buffers.
- Current-boot persistent Library admission/export в 0.35 добавляет 608 B static RAM
  и 1 312 B linked flash. Minimum heap 147 692 B остаётся выше RB-04 floor на
  16 620 B; entry переиспользует caller-owned `librarySession`, но boot catalog и
  concurrent workers требуют отдельного map/release-endurance review; extended
  qualification 8 h необязательна после крупных storage/runtime/radio changes.
- Storage, power и shared-bus limits остаются явными unknown; зависимые от них
  возможности нельзя перевести из `unknown` в `available` одной документацией.

Последний build delta `RB-M133`: exact 0.136 использует 3 059 360 B linked flash и
207 928 B static RAM; app image равен 3 059 760 B. Это −8 296 B linked flash,
−25 432 B static RAM и −8 304 B image против 0.135. Сокращение объединяет только
workspaces взаимоисключающих lifecycle: Survey/diagnostic Session и
product/diagnostic FatFs. Boot-before heap растёт до 173 524/103 248/89 060 B.
Normal Capture Store доходит до mount с 93 544 B free и largest block 32 756 B,
сообщает mount error zero, сохраняет 2 frames/433 B и продвигает generation 98→99.
Injected pre-storage path срабатывает через 8 001 ms до любого physical write. Run
не выполняет normal mixed workload. Exact 0.129 остаётся physical functional
baseline, а RB-04 плюс mixed-workload release endurance — resource/release baseline.

Source-bound diagnostic fixture `0.2.4` использует 332 135 B program flash и 22 844 B
static RAM. Delta +9 920/+120 B против fixed-NEC fixture добавляет read-only identity
telemetry всех nRF chip select, обеих orientation data pins и CC1101 на shared bus;
он не входит и не меняет exact product image. Физическая диагностика 2/2 выполняет
zero emissions и не заявляет runtime heap; отрицательный receiver inventory сохранён
в [evidence board-02](../../tests/hil/evidence/board-02-rf-shield-inventory-0.2.4.json).

Последний candidate delta `RB-M134`: exact 0.137 использует 3 061 496 B linked
flash, 207 960 B static RAM и app image 3 061 904 B. Это +2 136/+32/+2 144 B
против 0.136 за общий path deadline, cancel и telemetry Store IR/Sub-GHz. Fixture
0.2.5 использует 332 247 B linked flash, 22 844 B static RAM и image 332 656 B.
Её delta +112 B linked flash против 0.2.4 оставляет у физически общего pad GPIO14
IR/CE3 единственного LEDC-safe owner и добавляет source guard. Это только build facts:
текущий physical gate ИК-стенда остаётся fail-closed.

Последний принятый delta `RB-M135`: exact 0.138 использует 3 061 508 B linked
flash, 207 960 B static RAM и app/factory images 3 061 920/3 127 456 B. Это
+12/0/+16/+16 B против 0.137 за замену обоих software restart Safe Mode на no-OS
primitive. Normal IR Save достигает storage boundary при 94 136 B free heap и
largest block 51 188 B; injected path пишет zero bytes и не заявляет mount
allocation. Это physical safety evidence, а не mixed-workload resource или release
endurance.

Последний принятый delta `RB-M136`: exact 0.139 использует 3 078 272 B linked
flash, 208 304 B static RAM и app/factory images 3 078 768/3 144 304 B. Это
+16 764/+344/+16 848/+16 848 B против 0.138 за power safety policy, explicit
assembly profile, реальный light-sleep/resume reporting, truthful Power UI и bounded
HIL-only RX fixture. Fresh runtime gate board-01 стартует с heap
total/free/minimum 171 012/100 736/86 548 B; light sleep 300 ms сохраняет free и
minimum byte-exact. Разрешённый Store Sub-GHz достигает mount при 91 656 B free и
largest block 49 140 B и продвигает catalog 109→110. Low-voltage path не открывает
filesystem и выполняет zero writes. Это focused runtime checkpoint, а не
mixed-workload/release endurance, и он не добавляет physical positive-RF claim.

Последний принятый delta `RB-M137`: exact 0.140 использует 3 084 428 B linked
flash, 210 984 B static RAM и app/factory images 3 084 592/3 150 128 B. Это
+6 156 B linked flash, +2 680 B static RAM и +5 824/+5 824 B images против
0.139 за chooser OOK/FSK, bounded capture state GDO0 на 512 events, asynchronous
receive registers CC1101 и diagnostics. Dedicated DIRAM равна
294 164/341 760 B (86,07%, свободно 47 596 B); dedicated IRAM остаётся ровно
16 384/16 384 B без запаса. One-flash delta board-01 byte-exact сохраняет heap
total/free/minimum 168 076/97 800/83 612 B в lifecycle no-signal FSK и соседнего
OOK с zero storage/TX side effects. Это не physical positive-RF и не
mixed-workload release budget. Compact retention сокращает checked HIL bundle с
45 818 642 B до менее 1 MiB, сохраняя run, PNG и identities source/artifacts.

Последний принятый delta `RB-M138`: exact 0.144 использует 3 087 248 B linked
flash, 211 208 B static RAM и app/factory images 3 087 744/3 153 280 B. Это
+2 820 B linked flash, +224 B static RAM и +3 152/+3 152 B images против 0.140
за plan-v10 execution receivers/artifacts Full/Guided, раздельные gates heap для
current free и boot-lifetime minimum и applicability-aware audit PCAP. Dedicated
DIRAM равна 294 388/341 760 B (86,14%, свободно 47 372 B); dedicated IRAM остаётся
ровно 16 384/16 384 B без запаса. Принятая delta board-01 стартует с 167 852 B
total heap и завершает Full с 96 880 B free и boot-lifetime minimum 63 848 B,
оставляя 14 960 B над gate current-free 80 КиБ и 14 696 B над gate minimum
48 КиБ. Она выполняет bounded receive на трёх nRF24, CC1101, OOK, FSK и IR плюс
read-only product/disposable artifact audits; product generation 110/zero
observations остаётся неизменной, product writes и radio TX равны нулю, scratch
505 B удалён. Эта focused delta не является mixed-workload release budget и не
заменяет stage-end matrix или квалифицированный physical RF-positive gate.

Последний принятый delta `RB-M139`: exact 0.145 использует 3 089 868 B linked
flash, 211 224 B static RAM и app/factory images 3 090 368/3 155 904 B. Это
+2 620 B linked flash, +16 B static RAM и +2 624/+2 624 B images против 0.144
за сохраняемые язык EN/RU, пять уровней яркости, runtime semantic palette
Лесная/Контрастная и fail-closed строку недоступного Звука. Dedicated DIRAM
равна 294 404/341 760 B (86,14%, свободно 47 356 B); dedicated IRAM остаётся
ровно 16 384/16 384 B без запаса. One-flash HIL board-01 и два физических hard
reset доказывают, что изменённые настройки переживают reboot, а восстановленные
RU/100%/Лесная снова сохраняются. Run выполняет zero radio TX, удерживает баззер
и nRF CE inactive, сообщает zero input errors/drops и заканчивается
Home/none/lease 0. Эта focused interface delta не заменяет stage-end matrix или
квалифицированный physical RF-positive gate.

Test-only измерение fixture `RB-M140`: fixture `0.3.0-subghz-safe` на source
`4f97b3a751b96c7573c056d4ac7562ef410c06cc` использует 335 955 B linked flash,
22 876 B static RAM и app/factory images 336 352/401 888 B. Dedicated DIRAM
равна 74 687/341 760 B, IRAM — ровно 16 384/16 384 B. Hashes firmware,
factory, ELF и map:
`32f3619f66beeacbd3e05b1148699494cc808a24b4779f4ded2d131c0f2ffb9c`,
`98b712c4f1979506e010c37e748b4f7d4aba4fc2a7ebfb04874479483e4b6586`,
`72dd88393fe1cbe9c3ef3f50e31f353ce6ffd883cd922429ed956b85d91c5798` и
`bd4d6582339441c9818525713467b64c85cb5997755157c351718d7d3ce65b35`.
Этот отдельный test image не меняет product budget, а его успешная сборка не
является physical RF evidence.

Host/build измерение фундамента Target `RB-M141`: `E-TARGET-002` использует
3 090 668 B linked flash, 211 224 B static RAM и app/factory images
3 091 168/3 156 704 B. Это +800 B linked flash, zero static-RAM growth и
+800/+800 B images против exact 0.145 за deterministic Target CBOR/manifest,
exact admission Observation и reusable two-head journal Target. Dedicated DIRAM
остаётся 294 404/341 760 B (86,14%, свободно 47 356 B); dedicated IRAM остаётся
ровно 16 384/16 384 B. `TargetCatalog` ≤16 KiB, codec workspace 16 KiB и explicit
recovery scratch являются lifecycle-owned objects и ещё не instantiated как
permanent product globals; product integration S6.4 обязана измерить их live
heap/static placement. Это host/build evidence, а не HIL.

Host/build измерение explainable correlation `RB-M142`: `E-CORR-001` использует
3 090 892 B linked flash, 211 224 B static RAM и app/factory images
3 091 392/3 156 928 B. Это +224 B linked flash, zero static-RAM growth и
+224/+224 B images против `E-TARGET-002`; код correlation скомпилирован, но его
bounded service/log ещё не являются permanent product globals. Dedicated DIRAM
остаётся 294 404/341 760 B (86,14%, свободно 47 356 B), dedicated IRAM — ровно
16 384/16 384 B. `CorrelationDecisionLog` host-ограничен ≤16 КиБ и содержит не
более 32 immutable решений; persistence S6.2 и runtime integration S6.4 должны
измерить его retained-storage и live placement costs. Это host/build evidence,
а не HIL.

Host/build измерение atomic Target state `RB-M143`: `E-CORR-002` использует
3 091 340 B linked flash, 211 224 B static RAM и app/factory images
3 091 840/3 157 376 B. Это +448 B linked flash, zero static-RAM growth и
+448/+448 B images против `E-CORR-001` за deterministic encoding schema v2
графа Target и полной истории решений вместе с отдельным six-boundary
dual-head journal. Dedicated DIRAM остаётся 294 404/341 760 B (86,14%,
свободно 47 356 B), dedicated IRAM — ровно 16 384/16 384 B. Workspace
`TargetStateStoreWorkspace` размером 32 КиБ, каталог и recovery scratch журнала
решений остаются explicit lifecycle-owned objects, а не permanent product
globals; runtime integration S6.4 обязана измерить их live placement и цену
migration. Это host/build evidence, а не HIL.

Host/build измерение reversible Target `RB-M144`: `E-CORR-003` использует
3 091 516 B linked flash, 211 224 B static RAM и app/factory images
3 092 016/3 157 552 B. Это +176 B linked flash, zero static-RAM growth и
+176/+176 B images против `E-CORR-002` за Actions merge/split schema v1,
bounded восстановление graph и atomic persistence merge history schema v3.
Dedicated DIRAM остаётся 294 404/341 760 B (86,14%, свободно 47 356 B),
dedicated IRAM — ровно 16 384/16 384 B. `TargetMergeHistory` занимает 11 528 B
и ограничена восемью полными snapshots пар Targets; она, state workspace 32 КиБ,
catalog и decision log остаются lifecycle-owned, а не permanent product globals.
Runtime integration S6.4 обязана измерить их live placement и цену migration.
Это host/build evidence, а не HIL.

Host/build измерение comparison Targets `RB-M145`: `E-CORR-004` использует
3 091 760 B linked flash, 211 224 B static RAM и app/factory images
3 092 256/3 157 792 B. Это +244 B linked flash, zero static-RAM growth и
+240/+240 B images против `E-CORR-003` за read-only Action `target.compare`
schema v1, exact lookup двух Sessions и bounded classification. Dedicated DIRAM
остаётся 294 404/341 760 B (86,14%, свободно 47 356 B), dedicated IRAM — ровно
16 384/16 384 B. `TargetComparisonResult` занимает 7 736 B и хранит не более
16 строк с четырьмя exact evidence references на каждой стороне; он остаётся
lifecycle-owned, а не permanent product global. S6.4 обязана измерить совместное
live placement Target state, двух recovered Sessions и view model Compare. Это
host/build evidence, а не HIL.

Измерение on-device «Цели» `RB-M146`: exact production
`0.146.0-targets` использует 3 108 996 B linked flash, 211 296 B static RAM и
app/factory images 3 109 152/3 174 688 B. Против exact принятой 0.145 это
+19 128 B linked flash, +72 B static RAM и +18 784/+18 784 B images за
read-only recovery пары, bounded admission и product route List/Compare/Detail.
Dedicated DIRAM равна 294 476/341 760 B (86,16%, свободно 47 284 B), dedicated
IRAM остаётся ровно 16 384/16 384 B. Steady foreground workspace занимает
22 544 B: 19 008 B Target/view state плюс controller 3 536 B. Он переиспользует
уже lifecycle-owned buffers Session Survey/Library, а scratch catalog 11 272 B
существует только во время atomic admission и освобождается до rendering.
SHA-256 firmware/factory/ELF/map:
`f115f46b0e5e587ac1e1a4c83745c9f6d53818fd0c468de2adecf0bc99e1211c`/
`db8a396cf272e67662d31eb0ad13ddd890d36d85ed72e1402ad5e13ab32494c9`/
`d8d364734661e0c0b18c700cce1e16600a8e51ca318cf20f1053cec4f206ab0a`/
`b134c373147f553ba5aac2a8a511a726454c502a48ff82175bb9ecaf7fbba7ff`.
Соответствующий physical reject сохранён как
[E-HIL-164](../../tests/hil/evidence/board-01-targets-stack-failure-0.146.json);
эти размеры остаются host/build evidence, а не acceptance claim.

Исправление stack safety «Целей» `RB-M147`: exact production
`0.147.0-targets-stack-safe` использует 3 107 636 B linked flash, 211 296 B
static RAM и app/factory images 3 108 144/3 173 680 B. Dedicated DIRAM остаётся
294 476/341 760 B (86,16%, свободно 47 284 B), dedicated IRAM —
16 384/16 384 B. Result 7 736 B теперь остаётся в foreground workspace; два
снимка сторон сравнения используют 1 616 B проверяемого transient heap с
автоматическим освобождением. Native `-fstack-usage` измеряет 112 B у
`compareTargetSessionsInto`, 1 088 B у `buildSide` и 496 B у вызывающего
`TargetsController::loadBindings`. Удаление дублирующего PCAP route из меню
Wi-Fi и добавление публичного persistent route «Записать визит» не меняет
static RAM и уменьшает linked flash на 1 360 B против failed precursor 0.146.
SHA-256 firmware/factory/ELF/map:
`57b5fea451ed957a68c67f98a2d7964dfcf64007261d3bc580f8ba71b6808164`/
`2716812e80c6a728b85c813f911aa9a6c25ce173eb4fec482bb61bf041441b31`/
`f7a87222d5720109b5149623b95f6a7c4f6070a1dedb66de163f9768f9e89aaf`/
`9873506a75583169c08de1ddd9ac3f8c401de6d0f33f51e4cf5048c15626cf9d`.
Это host/build evidence до focused regression stack canary.

Исправление порядка storage «Целей» `RB-M148`: production
`0.148.0-targets-storage-order` использует 3 107 844 B linked flash,
211 296 B static RAM и images app/factory 3 108 352/3 173 888 B. Dedicated
DIRAM и IRAM остаются 294 476/341 760 B и 16 384/16 384 B. SHA-256
firmware/factory/ELF/map:
`6847673339df14538ddce4eb57f044088df825a20645f06f273e765187de066a`/
`65b0711a5940a9a863870efe7c5b37578f9af89728c52ed96873c24051096222`/
`57785567646cb45a2c885fbd71ca365b05e08084c34f56e4189ec4b1875f252f`/
`393cffd5859ed61845192464484a031f37e3e49874e3f13efa7961f1572d7397`.
Physical precursor 0.147 сначала доказал исправление stack, затем отказал на
read-only mount после выделения workspace; отдельный результат сохранён
fail-closed в
[E-HIL-165](../../tests/hil/evidence/board-01-targets-readonly-mount-failure-0.147.json).
Путь 0.148 восстанавливает exact-CID пару Sessions и закрывает FAT/SPI до
выделения неизменного workspace Targets 22 544 B. Это host/build evidence до
gated короткой physical regression mount.

Исправление in-place reset «Целей» `RB-M149`: production
`0.149.0-targets-inplace-reset` использует 3 107 472 B linked flash,
211 296 B static RAM и images app/factory 3 107 968/3 173 504 B. Dedicated
DIRAM и IRAM остаются 294 476/341 760 B и 16 384/16 384 B. SHA-256
firmware/factory/ELF/map:
`743f31614df8891667293fdf755c7e53b9b4fc6ce105bc48d8a84a76d1e9c653`/
`9eeca0ecd29c7fdefe2315428f2fd3f01d5f232829af5926250d9a4aab0e9a37`/
`3293c8328bf946843c0035df7516fa47b8363d207acface51416967d51be62e9`/
`8fef982fadc2253d7a64ae01d272965d8bd29c701654d95b128c552f8c202051`.
Exact linked disassembly доказывает stack frames 256 B у controller reset,
416 B у load bindings, 32 B у in-place result reset, 80 B у comparison и
1 104 B у deepest evidence builder. Оба physical runner выполняют этот ELF
check до прошивки. Source contract отклоняет aggregate reset result 7 736 B.
Physical acceptance exact 0.149 затем сохраняет 97 488/97 488 B до/после
workspace короткой regression и 96 452/96 452 B до/после workspace full delta;
оба завершаются с lease zero в `E-HIL-167`.

Checkpoint row-evidence «Целей» `RB-M150`: production
`0.150.0-targets-evidence` использует 3 112 664 B linked flash, неизменные
211 296 B static RAM и images app/factory 3 113 168/3 178 704 B. Это +5 192 B
linked flash и +5 200/+5 200 B images против 0.149 при zero growth static RAM за
class/signal order, selectable строки сравнения, exact evidence detail,
UTF-8-safe pixel fitting и incremental cleanup list band. SHA-256
firmware/factory/ELF/map:
`bbb200a5a9ca4b8c1cd60dcdd665ec64eea70ecb2a4d0244ff642df240268e65`/
`37da3aaf7fe3a7101ab772e29020e901e619990154cbba40016edd8ec9b53dce`/
`e91cad765c55c08dc317e4099e173423a18af4aeba323f824b1759e3b8caae56`/
`5599e1d0835f81458d1647b31ed3a40d0fe5e67d55bab7d47f95a50a0516ae9c`.
Linked disassembly дополнительно ограничивает load comparison side 272 B,
row ordering 32 B и row comparison 480 B; прежние frames 256/416/32/80/1 104 B
остаются внутри gates. Exact one-flash physical acceptance сохраняет workspace
22 544 B lifecycle-owned, удерживает 97 488/97 488 B до/после release и завершает
run с lease zero в `E-HIL-168`.

Checkpoint Favorite «Целей» `RB-M151`: exact production
`0.151.2-targets-favorite-compact` использует 3 128 500 B linked flash,
211 512 B static RAM и app/factory images 3 129 008/3 194 544 B. Это
+15 836 B linked flash, +216 B static RAM и +15 840/+15 840 B images против
0.150 за view «Действия», typed mutation service, persistence catalog schema v3
и supervised storage worker с deadline 8 s. Dedicated DIRAM равна
294 692/341 760 B (86,23%, свободно 47 068 B); dedicated IRAM остаётся
16 384/16 384 B. Существующий foreground workspace Targets 22 544 B остаётся
lifecycle-owned. Mutation до mount FAT выделяет отдельный catalog-only workspace
16 384 B; на реальной плате без PSRAM он видит 76 152 B free и largest block
34 804 B, после выхода heap возвращается к 97 012 B. Exact HIL фиксирует UI
acknowledgement 148 µs, worker 2 689 541 µs, 1 688 logical bytes, три writes,
три file syncs и три directory syncs, generation 1→2 и cold reopen.
SHA-256 firmware/ELF/map:
`62a300adeb76514719a93de58757a78537a14766243140024920ebcd01d9dfee`/
`bab922a10e4dd6d1ddf0215f0ec9cb97c85379da37cdebe61941884378ada0e5`/
`7a7c598338633c0e6dae8ac7736be35021e6ecf6df36271e0510879583744c49`.
Две предшествующие попытки allocation 32 КиБ отказывают до любой записи и
сохранены вместе с accepted run в `E-HIL-169`.

Checkpoint имени Target `RB-M152`: exact production
`0.152.0-targets-name-edit` использует 3 131 792 B linked flash, 211 624 B
static RAM и app/factory images 3 132 288/3 197 824 B. Это +3 292 B linked
flash, +112 B static RAM и +3 280/+3 280 B images против 0.151.2 за bounded
редактор имени, его touch/key rows, строки и state probe. Dedicated DIRAM равна
294 804/341 760 B (86,26%, свободно 46 956 B); dedicated IRAM остаётся
16 384/16 384 B. Foreground workspace Targets 22 544 B и отдельный
catalog-only mutation workspace 16 384 B сохраняют существующий lifecycle.
Exact HIL видит 75 992 B free и largest block 34 804 B до mount, возвращает
heap с 85 072 B к 96 852 B после release и фиксирует UI acknowledgement
155 µs, worker 2 824 907 µs, 1 689 logical bytes, три writes, три file syncs
и три directory syncs. Generation продвигается ровно 2→3, а physical cold
reopen сохраняет bytes имени `41` на том же Target ID. SHA-256
firmware/ELF/map:
`0599cb880921ec5cb11d39a681e64a324acc84f048f7dedfacae4ff200703506`/
`075a137a5b0cbe0dba1428e30f9fc223e59c940da87d3ca971406ea5f53941dd`/
`c52778fcfd8619a5847de5fb04ceddfeeccb5fcd1ff546a75a00792f4817198f`.
Exact one-flash delta и пять просмотренных TFT states сохранены в `E-HIL-170`;
cadence продвигается до 7/15 без полной physical matrix.

Checkpoint тегов Target `RB-M153`: exact production
`0.153.0-targets-tags-edit` использует 3 135 372 B linked flash, 211 624 B
static RAM и app/factory images 3 135 872/3 201 408 B. Это +3 580 B linked
flash, zero static RAM и +3 584/+3 584 B images против 0.152 за bounded список
и редактор тегов, Actions add/remove, строки, state probe и delta runner.
Dedicated DIRAM остаётся 294 804/341 760 B (86,26%, свободно 46 956 B),
dedicated IRAM — 16 384/16 384 B. Foreground workspace Targets 22 544 B и
отдельный catalog-only mutation workspace 16 384 B сохраняют существующий
lifecycle; state probe переиспользует static diagnostic JSON buffer вместо нового
workspace на loop stack. Exact HIL видит 75 992 B free и largest block 34 804 B
до обоих mount, возвращает heap с 85 072 B к 96 852 B и фиксирует времена
UI/worker 158/2 914 830 µs для add и 141/2 918 739 µs для remove. Обе mutations
используют три writes, три file syncs и три directory syncs; поколения продвигаются
3→4→5 с physical cold reopen после каждого перехода. SHA-256 firmware/ELF/map:
`b9a49fe887baf595da01ea798eb1efa8dada57c5ac20af090f467fcb7b688651`/
`49d9c7cbb058158bda4ef19c88e6cfbf56c05f38b4a055e616841cb4091a0d56`/
`0cdaa2ec9f4874991d5c9738f876f7f87fe6e4f96064dd42f3c0685273a3adde`.
One-flash delta и семь просмотренных TFT states сохранены в `E-HIL-171`;
cadence продвигается до 8/15 без полной physical matrix.

Checkpoint заметок Target `RB-M154`: exact production
`0.154.0-targets-notes-edit` использует 3 138 180 B linked flash, 211 848 B
static RAM и app/factory images 3 138 688/3 204 224 B. Это +2 808 B linked
flash, +224 B static RAM и +2 816/+2 816 B images против 0.153 за четвёртую
строку Actions, bounded редактор заметок, typed set/clear path, строки, state
probe и delta runner. Dedicated DIRAM равна 295 028/341 760 B (86,33%,
свободно 46 732 B), dedicated IRAM остаётся 16 384/16 384 B. Текущий
foreground allocation Targets равен 23 152 B: 19 008 B Target/view state плюс
controller 4 144 B со всеми bounded editors. Отдельный catalog-only mutation
workspace остаётся 16 384 B; в существующем static diagnostic JSON buffer
hex-кодируется только prefix заметки 24 bytes. Exact HIL видит 75 656 B free
и largest block 34 804 B до обоих mount, возвращает heap с 84 736 B к
96 516 B и фиксирует времена UI/worker 153/2 942 650 µs для set и
153/2 964 667 µs для clear. Обе mutations используют три writes, три file
syncs и три directory syncs; поколения продвигаются 5→6→7 с physical cold
reopen после каждого перехода. SHA-256 firmware/ELF/map:
`f2d151dcfc955260a4cd0bee67de1887a46af9bab53b18477bb6633ae99dd095`/
`9eaf3896cd681932f397f87cdb4cc07a087b9ef6914f2693c485bc40330a6ebd`/
`4888aa7c2b1ef182121364a2e72e1e1f2a19eee769f4820613ac377574309ed7`.
One-flash delta и семь просмотренных TFT states сохранены в `E-HIL-172`;
cadence продвигается до 9/15 без полной physical matrix.

Checkpoint Correlation Target `RB-M155`: exact production
`0.155.7-targets-shared-codec` использует 3 157 569 B linked flash, 214 165 B
static RAM и app/factory images 3 135 296/3 200 832 B. Dedicated DIRAM равна
297 365/341 760 B (87,01%, свободно 44 395 B). Union
`TargetsStoreCodecWorkspace` размером 24 800 B заменяет прежний постоянный
workspace codec Session 22 824 B, поэтому persistence полного graph/history
Target добавляет только 1 976 B permanent RAM вместо второй одновременной
allocation. Lifetime переключается placement construction только после writable
mount FAT, а codec Session восстанавливается до release worker. Linked stack
preflight фиксирует 416 B для `CorrelationService::propose`, 816 B для
`buildSessionCorrelationReview`, 432 B для `TargetsController::loadBindings` и
1 104 B для `buildSide`. Соседняя exact regression mutation проходит при
61 468 B free/29 684 B largest pre-mount heap, записывает 2 079 logical bytes
тремя writes, тремя file syncs и тремя directory syncs и завершается за
3 320 152 µs после UI callback 212 µs. Затем exact Accept продвигает state 8→9,
decision count 0→1 и Target revision 3→4; отдельный zero-flash physical reset
открывает то же состояние с invariant source identities 69. SHA-256
firmware/ELF/map:
`57cd9a4b2f84fbdd2ce7421f902497b1b57ea0a441adf64c20a6f37df93cdf2e`/
`47f483e9a65ede473fa4c9b5a3541267fdf6ea6e04dd9fb66efe29e6772cb89a`/
`17cdfbbfbe042a57c5b50eb31991015ca5a9b93ea72c49626c49132fe0020627`.
Шесть просмотренных TFT states и два rejected precursor с zero writes сохранены
в `E-HIL-173`; cadence продвигается до 10/15 без полной physical matrix.

Checkpoint Reject rebuild Target `RB-M156`: exact production
`0.156.0-targets-reject-rebuild` использует 214 168 B static RAM, 3 135 096 B
app partition из 4 194 304 B и firmware image 3 135 600 B. Mutation worker
больше не дублирует полный catalog 11 272 B и decision log 11 272 B, пока его
завершившийся stack FreeRTOS 8 КиБ ожидает cleanup idle task: после atomic write
и проверенного reopen runtime принимает эти две allocation worker на месте. На
жёстком пределе каталога 16/16 physical Reject проходит с 69 632 B free до mount
mutation, 60 552/32 756 B free/largest перед записью и полностью освобождает heap
до измеренных terminal 94 108 B после reset. Времена UI/worker —
231/3 960 944 µs; 2 878 logical bytes используют три writes, три file syncs и
три directory syncs. Target state продвигается 10→11, decision log 2→3, а
revision Target 5, visible ownership count 4 и catalog count 16 не меняются.
SHA-256 firmware/ELF/map:
`68c809d0a529c76b629c2723c5f918c5288413fe7791d68e98b67dcab74c98b9`/
`e0bffd74505ed266cb6a48d9646fdf47c0290b462c9fb5234b5a4b010c8a50a7`/
`37e6fa1e70d3fe210324b13b3deb302741ec29ff36a2aff8b78a66c47ee50750`.
Семь просмотренных TFT states и fail-closed precursor duplicate rebuild сохранены
в `E-HIL-174`; cadence продвигается до 11/15 без полной matrix.

Checkpoint load-memory Targets `RB-M157`: exact production
`0.160.0-targets-load-memory` использует 214 272 B static RAM, 3 147 108 B
app partition из 4 194 304 B и firmware image 3 147 616 B. Retained wire
workspace target-state 24 КиБ теперь перекрывается только с финальными catalog
11 272 B, decision log 11 272 B и merge history 11 528 B; он удаляется до фазы
comparison 7 736 B, proposals 2 704 B и controller/runtime 4 240 B. На exact
post-Survey boundary, где отказал 0.159, foreground load начинается с 67 436 B
free, завершается с 40 496 B free и освобождается до 93 040 B. Полная persistence
call chain проверяется production ELF gate; `loadTargetsProduct` использует 784 B,
а вложенные decode frames — 32…752 B. SHA-256 firmware/ELF/map:
`a54d1509c01b1e6d77afed25e5cac74eb8d290221942391b45f65b44a50633cd`/
`af75ba520082f1491bee06dd741e77d2d17613e8edb1324d5ad58ff7c98d87d9`/
`5cf29818ec00b96e6d2e04d590b193d592d86dde55c7bda39fc1881b5d7455d8`.
Три просмотренных TFT state и exact no-flash/no-scan regression сохранены в
`E-HIL-175`; cadence продвигается до 12/15 без полной matrix.

Checkpoint merge/split Targets `RB-M158`: exact production
`0.165.0-targets-fixture-reopen` использует 214 285 B static DRAM, 3 159 796 B
linked flash и app/factory images 3 160 304/3 225 840 B. Он добавляет bounded path
continuity fixture и полную on-device interaction merge/split без allocation второго
graph: linked frames merge/split равны 2 224/1 472 B, helpers replacement — 768/64 B,
а оба physical reset records сохраняют minimum stack worker 8 040 B. Isolated fixture
двух Targets открывается при 67 896 B free, освобождается до 93 500 B и удерживает
lease 13 только пока Targets владеет UI+Storage+RadioSPI. Две atomic mutations
используют по три writes, три file syncs и три directory syncs. SHA-256
firmware/ELF/map:
`40af5486e8525998e86aa3c864e0cb0e21e3aace0d3dc40c8dd4eb1923f01d4b`/
`20968cb44e847c7e3b9338c462991b6710a2c23c1654e9b3692879c9f91a81ec`/
`7acc6be8c106566de2d877acae572171e790983a421bd226b9c2070a2a7063f1`.
Exact `E-HIL-176` byte-for-byte восстанавливает inactive OTA1 4 MiB и исходную
partition table, удаляет private backups после проверки, read-only открывает product
generation 161 и заканчивает Home/none/lease 0. Cadence продвигается до 13/15 без
учёта disposable fixture или недоступной PSRAM как product capacity.

Checkpoint contract companion `RB-M159`: exact production
`0.166.0-companion-contract` на source
`d34135677e984b710ef061ca6886d7f08cd264be` использует 214 288 B static RAM,
3 159 808 B linked flash и app/factory images 3 160 304/3 225 840 B. Это
+3 B static RAM, +12 B linked flash и +0/+0 B images против exact 0.165;
dedicated DIRAM равна 297 504/341 760 B (свободно 44 256 B), dedicated IRAM
остаётся 16 384/16 384 B. `CompanionConnectRequest` и `CompanionConnection`
compile-time ограничены 48 B каждый. Parse frames имеют максимум 512 B; staging
response использует 513 B только на stack caller и не публикует partial bytes.
Translation unit protocol компилируется и проходит native tests, но ещё не связан с
product runtime, поэтому linker GC сохраняет прежнюю длину app/factory; этот budget
не заявляет работающий USB adapter. SHA-256 firmware/factory/ELF/map/partitions:
`200bf8f5c04f5815821503748aac549aadc422eb6268b3c700356fd3227cd9af`/
`3f3729e6a71d539bb38d981213b895f0494e579bbb90cfd7fcb5cc8f00bd61c9`/
`c86a2b60a9264f456b8d6d3f07c5e33b437f3f8ffec247de8f47c0465e00e6a7`/
`e7416f269ad17c44324e9d0225fdfe23d7f4e82a20ea21795890538b18a14622`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Physical cadence delta не расходуется.

Checkpoint read companion по USB `RB-M160`: exact production
`0.170.0-companion-usb-rx` на source
`b58fbc054522cecfca5dd4afcd6ea61098cb05c0` использует 214 664 B static RAM,
3 172 080 B linked flash и app/factory images 3 172 576/3 238 112 B. Это
+376 B static RAM и +12 272/+12 272/+12 272 B linked/app/factory против exact
0.166. Native adapter владеет одним workspace command/response 513 bytes, сохраняет
protocol bound 512 bytes и настраивает hardware CDC RX queue 576 bytes; последнее
необходимо, потому что valid compare request превышал default queue core 256 bytes до
прихода newline. Physical Targets имеет 92 972 B free heap до и после release;
минимальный sampled free heap во время bounded load равен 15 008 B. Exact SHA-256
firmware/factory/ELF/map/partitions:
`6275e94fd34cf28018cb761dc877717a668e2fedb8b5f4d9de6a213dfe0583ad`/
`8f0a7a1696069225a96984480e88d66f9beacb7530399e28291e8ffde1b66528`/
`6c4da4273bfa0d11fc5b022125a320f61f45342ac34cc0ac870a3178fc0832cf`/
`c18e76d32054cb0be139be73f3b55d085f55179858ae828dad8c68950b48adef`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
`E-HIL-177` принимает exact boundary 512 bytes, полную read pagination, invariant
released heap и zero storage writes, TX, drops или leaked lease. Cadence продвигается
до 14/15; следующая принятая physical delta запускает установленный full-matrix gate.

Checkpoint status LED каждой антенны и cadence-full `RB-M161`: exact production
`0.171.0-antenna-status-leds` на source
`c2413c9e31b89efd646a0ca15d2eb2b574d90fe5` использует 214 696 B static RAM,
3 175 040 B linked flash и app/factory images 3 175 536/3 241 072 B. Это
+32 B static RAM и +2 960/+2 960/+2 960 B linked/app/factory против exact 0.170.
Фиксированный controller четырёх пикселей GPIO1 не добавляет framebuffer, heap
allocation или timing loop: запись выполняется только при смене состояния приёмника
или persisted raw preference 0/2/3/5/8/12. Exact SHA-256
firmware/factory/ELF/map/partitions:
`77d14d9ac10f64cb60fb97f2f3b6b3986d2cdac71085b454d6d25267794e0784`/
`04bb4a4fb78cd4de7e12e5a2c4b43311e8e1af097c8e5181173a0bc08500a0fe`/
`e5189daa424da4e2ca04e5e94390f19e9ef3d483c894b10a62c8da9da08d247c`/
`04e897a24e7bb68e1933bb95d19b9c30a546ae56a8a598f9138256ad9ac1a8b4`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Периодическая physical matrix возвращает heap total/free к 164 108/91 068 B после
Home, RF, Targets и companion, сохраняет generation 161/59 observations и не добавляет
flash сверх одной прошивки LED-delta. `E-HIL-178` расходует delta 15/15;
`E-HIL-179` завершает немедленно обязательный full checkpoint и сбрасывает cadence
anchor до 0/15.

Checkpoint mutation Target через companion `RB-M162`: exact production
`0.172.0-companion-target-mutate` на firmware source
`6ec3a198562c2cffc998b18bbd5e0738dcae3428` использует 214 992 B static RAM,
3 183 044 B linked flash и app/factory images 3 183 200/3 248 736 B. Это
+296 B static RAM, +8 004 B linked flash и +7 664/+7 664 B images против exact
0.171. Bounded mutation adapter не добавляет второй catalog или storage path: его
fixed record preview/status хранит ненулевой token 128 bit, exact optimistic revision
и одно pending value, затем передаёт confirmation уже supervised worker Target.
Physical round trip Favorite публикует два поколения; каждый commit фиксирует три
writes, три file syncs и три directory syncs. Cold reset открывает generation 17
Target-state и revision 12 с исходным false. Heap total/free возвращается к
163 812/91 068 B; post-reset sampled minimum равен 17 344 B после полной bounded
загрузки Targets. Exact SHA-256 firmware/factory/ELF/map/partitions:
`7038ac9bd5995cea7b1dd203342e38514ced0b5b678fb625ef506c093b104e1c`/
`edf50e23cf071428c29c3031a1ecee7510e605bdd6c96aa0d9f9a4f0cb1f6658`/
`36ae2320517acf5625904aa5989d9253cce53c895ca6453ece39f81864df8da7`/
`8abb1b91b2273838171604ac427bedb22a16144cd23f3d483d249a4e1d926210`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
`E-HIL-180` переиспользует одну exact installation, сохраняет оба rejected precursor
harness и принимает reconnect-aware cold reopen с zero TX, input drops, port discovery,
Cardputer opens и leaked lease. Verification source
`48d296537a8eb358663420918b19151e2aa19c09` меняет только host reset transport. Cadence
продвигается до 1/15.

Checkpoint presentation local Web `RB-M163`: exact production
`0.173.0-companion-local-web` на source
`9ae7ee5a6013f219cb0cdf406ef5cf1ce57934e3` использует 214 992 B static RAM,
3 183 140 B linked flash и app/factory images 3 183 296/3 248 832 B. Это zero роста
static RAM и +96/+96/+96 B linked/app/factory против exact 0.172. Translation unit
Web и его self-contained page компилируются и проходят native tests, но ещё не связаны
с product runtime, поэтому linker GC удаляет payload presentation; оставшийся delta —
build identity. Request view compile-time ограничен 32 B, общий body остаётся не больше
512 B, ошибки transport используют staging не больше 192 B, offline page host-gated
ниже 16 КиБ. Exact SHA-256 firmware/factory/ELF/map/partitions:
`392d7e34f5625dee1762b28be6d75c164376b882bbd75f0f746ef2d891afbc78`/
`187b0a17c3072312e3f3ca56f380fcd1eced78c050a867ed32885a0ecbdb4bd2`/
`a45bc9fe70622a5d910902606609428a70a28fc555d19f53a0e8c5fdd53d1652`/
`086cf6da062bf2b6c23807ed3f19377669e47138e58e72468d6f04ec5c65d330`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Две последовательные сборки из workspace-local core PlatformIO дают те же exact
hashes и изолированы от посторонних проектов. Physical cadence delta не расходуется;
memory runtime listener/connectivity ещё не допущена и не заявляется.

Physical checkpoint lifecycle local Web `RB-M164`: exact production
`0.181.0-companion-web-deferred-worker-restore` на source
`6e0f2be76240e38d12805cfd654a7d70c61ae3d8` использует 222 800 B static RAM,
3 359 608 B linked flash и app/factory images 3 360 112/3 425 648 B. Против exact
0.173 это +7 808 B static RAM, +176 468 B linked flash и +176 816/+176 816 B images,
потому что runtime ESP-IDF Wi-Fi/AP и HTTP теперь reachable, а не удалён linker GC.
Portable board всё ещё имеет zero usable PSRAM. Ready Targets оставляет 32 660 B free;
release тяжёлых foreground objects поднимает значение до 39 924 B, а idle worker/queues
Survey — до 60 788 B. Непосредственно перед `esp_wifi_start` free/largest heap равны
54 764/23 540 B, после старта — 16 868 B. Stop возвращает 53 424 B при восстановленных
Targets и ещё deferred worker Survey; выход из Targets восстанавливает worker, а final
boot metric равен 75 972 B free при total 156 004 B и sampled minimum 14 088 B.
Admission фиксирован: один client, два static RX buffers, по одному dynamic RX/TX,
один management buffer, шесть short management buffers, один cached TX buffer,
600 s idle и 1 800 s absolute lifetime. Exact SHA-256
firmware/factory/ELF/map/built-partitions:
`7491f450026c864f228df3164155afd1c388d1faa0b8a60bf9a9ef652933cd9d`/
`b1a391215039621da8f7acc3d8cba5311d3d19bae10100b8ead1748d5ab98abb3`/
`eb42e6f9002a708329cb2498b0b37dc7be4d26f74bd40676e331ca599a56c31e`/
`585c0b9ec83193e1d8d239119359a934e111b1b3d7ce15b75a2f499004f92c84`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Installed partition preflight отдельно совпадает с `339bda68…ba2`; partition flash не
выполняется. `E-HIL-181` принимает только lifecycle и cleanup, двигает cadence до 2/15
и явно оставляет actual HTTP traffic следующему physical gate.

Pending checkpoint HTTP parity `RB-M165`: production candidate
`0.182.0-companion-web-http-parity` использует 222 816 B static RAM, 3 360 828 B
linked flash и app/factory images 3 361 328/3 426 864 B. Против exact 0.181 это
+16 B static RAM, +1 220 B linked flash и +1 216/+1 216 B images. Firmware delta —
один one-shot buffer entropy HIL 16 bytes и exact guards parse/scrub/scope; обычный
product start сохраняет credentials от hardware RNG. Host-only pagination, сравнение
native USB, HTTP и state machine восстановления Wi-Fi macOS не входят в firmware
budget. Exact SHA-256 firmware/factory/ELF/map/built-partitions:
`b7a1eea19c73c2d4fbd2be6487564b5a92e0e5cabff12bbe4ac92f6618692c5c`/
`bee589ee217579f3371c1ea2417ed78298ee0b716b2adfcb79e3e8baf5ad8a69`/
`e7452bf96285200b315b27e1532e8607cf1edfaa6c72e985a1969f831ff1bbee`/
`a2f8eb2aa6e5a3e3ac72cb894cf3be18fcbbb94a4f802aa13d12ab2edbbb95d2`/
`325d90a7000bdb14af736b3fdb08cfa17406889abf8a135c4cfe00cd33f7abb3`.
Это только host/build evidence: board не прошивалась, состояние Wi-Fi host не
менялось, runtime heap повторно не заявляется, physical cadence остаётся 2/15.

Offline checkpoint companion `RB-M166`: exact установленная
`0.195.0-companion-web-gzip-index` использует 223 112 B static RAM, 3 359 896 B
linked flash и app image 3 360 400 B; no-flash USB-only gate не добавляет firmware
memory. Host-owned canonical snapshot занимает 11 521 B и не расходует RAM/storage
устройства. После чистого reset Targets/export начинает и завершает работу с
82 892 B free heap и освобождает runtime до того же значения. Retained precursor
стартовал только с 60 584 B после прежнего Local Web и получил fail read-only mount
`ESP_ERR_NO_MEM` (257); reset вернул 82 892 B и immediate readiness Targets. Это
фиксирует открытый на тот момент firmware defect lifecycle/reclamation, а не принятый
сниженный memory budget; `RB-M167` ниже закрывает его.
Exact `E-HIL-182` принимает только deterministic offline USB snapshot/search, двигает
cadence до 3/15 и доказывает zero network tools/использования активного Wi-Fi Mac.

Checkpoint post-Web continuity `RB-M167`: exact
`0.196.2-companion-post-web-shared-scratch` использует 223 112 B static RAM,
3 360 064 B linked flash и app image 3 360 560 B: +0 B static RAM, +168 B linked
flash и +160 B app против exact 0.195. Wire codec Session (22 856 B), wire codec
Target (24 808 B) и admission scratch Target (11 272 B) mutually exclusive и
переиспользуют один существующий static union. Pinned ESP-IDF не умеет
деинициализировать `esp_netif`, поэтому его network core явно считается
process-lifetime allocation, а не ложно заявленным reclaimed heap. После Web
приостановка idle Survey worker поднимает free heap до 96 624 B перед Targets;
освобождение Targets и восстановление worker заканчивается на 75 760 B против
clean-boot start 82 892 B. Эта принятая разница является retained network core, тогда
как AP, server, authorization, credential и leases удалены. Exact `E-HIL-183`
запускает/останавливает SoftAP устройства с zero clients, повторно открывает 16 Targets
и 7 comparison items, воспроизводит принятый snapshot 11 521 byte, заканчивает
Home/none/lease 0 и продвигает cadence до 4/15. Fail-closed 0.196/0.196.1 сохраняют
boundaries duplicate codec и dynamic scratch allocation. Host network tools и активный
Wi-Fi Mac не используются.

Correction bounded BLE `RB-M168`: отклонённый exact 0.207 использует 225 680 B
static RAM и достигает interactive ready лишь с 29 576 B free после запуска NimBLE
при boot. Независимая read-only identity доказывает enrolled SD объёмом
62 534 975 488 byte и exact CID, тогда как FAT mount возвращает `ESP_ERR_NO_MEM`
(257). Это не missing media и не принятый сниженный heap budget. Candidate
`1.0.0-dev.208` использует 225 688 B static RAM, 3 318 064 B linked flash и
3 318 224/3 383 760 B app/factory: +8 B static RAM при переносе той же обязательной
allocation NimBLE за пределы boot/storage lifetimes. Host обязан остановиться,
завершить task и деинициализироваться перед mount FAT для commit; physical recovery
free heap остаётся следующим delta gate. Hashes firmware/app:
`1b72d9cc05353ba5f36b815a21af1e5d91224ccae451174508915dbb8858380f`/
`598dc7e8de07ac2dd8509a7e3e1d2fac154de98c20b27241cb449cd174e1fb09`.

Correction непересекающихся radio `RB-M169`: физически отклонённый exact
`1.0.0-dev.208` загружается с 153 116 B free heap, largest block 80 316 B и
minimum 66 632 B, но сохраняет NimBLE resident во время initialization Wi-Fi.
Поэтому Wi-Fi возвращает `ESP_ERR_NO_MEM` (257) с zero завершённых cycles Wi-Fi,
тогда как BLE завершает шесть окон и публикует 205 accepted reports. Bounded timeline
сохраняет 64 и отбрасывает 171 report по заявленной queue policy; это не drops driver
или storage. Degraded run не доказывает terminal commit и позже latch-ит Safe Mode
`runtime_watchdog` с owner none, lease zero и quiesced outputs. Candidate
`1.0.0-dev.209` делает lifecycle каждого radio непересекающимся и использует
225 688 B static RAM, 3 317 692 B linked flash и 3 318 192/3 383 728 B app/factory.
SHA-256 firmware/factory/ELF/map:
`63f55328d23082943945659fb63d55a771d388b427f5eca29dcecd2178aa3bab`/
`4ed3bdd0cb6f1b4f8990dd89406bc0147b06b27d373f4b25b9fde8fefdbd51db`/
`38d3cf0242707a13407c3123a207ab0c8e942242336ec396b31ccfc89083d868`/
`8a8e616323c176c702939813f35f3804a0ae67105f7ced4376f25c1ff51a4198`.
Exact `E-HIL-188` физически принимает этот budget: boot heap invariant
153 116/80 316/66 632 B до и после, Wi-Fi принимает 12 и BLE 35 observations с
zero errors/drops, generation 162→163 commit-ит 3 801 B, cold reopen/export
восстанавливает все 47 observations, final state — Home/none/lease 0 с safety armed.
Первый exact-flash run и принятый no-flash rerun образуют один one-flash lineage;
cadence двигается до 5/15.

Acceptance integrated demo `E-HIL-189` переиспользует тот же exact установленный
candidate и уже принятую no-flash pair Survey, поэтому добавляет zero application
flash и не меняет RAM/linked-flash/image-size. Targets открывает каждый из пяти
evidence views сравнения и освобождает heap invariant 80 316→80 316 B. Canonical
snapshot 11 882 byte является host-side output с двумя Sessions, 16 Targets и пятью
comparisons; он не расходует firmware storage budget и не разрешает device write.
Поскольку это selective reuse того же принятого candidate, а не новый delta,
cadence остаётся 5/15.

Foundation Защиты эфира `RB-M170`: exact `1.0.0-dev.210` добавляет только fixed
stack/caller-owned detector state, без resident task, radio owner или static buffer.
Поэтому static RAM остаётся 225 688 B; linked flash равен 3 317 732 B, а размеры
app/factory — 3 318 240/3 383 776 B. SHA-256 firmware/factory/ELF:
`835beabb6f47c5dcb51ceb3524a0a47a0d21596132f83230169b682863dd58c6`/
`fb52489d182af4c2111a8eafb1e25b2aa0a54cddf73befa39ac9e201f48c897d`/
`44d1106b24dc5e17d09ca442e1df3cb67e9dbcced1e7c2f2cd288a7afd97c8a4`.
Это только source/build evidence; изменение physical heap budget или cadence HIL не
заявляется.

Workflow Защиты эфира `RB-M171`: exact `1.0.0-dev.211` добавляет caller-owned
controller над bounded report. Поскольку production runtime им ещё не владеет, link
garbage collection сохраняет те же 225 688 B static RAM, 3 317 732 B linked flash и
3 318 240/3 383 776 B app/factory. SHA-256 firmware/factory/ELF:
`8b8953c54f8da2fa6564c3f093c26803775946d575ed9f8a0d979e069b522cdf`/
`8ace219821ac93fbcde5e5c158c89df0d49085e2bfae39f47669d1f9324cb34f`/
`fd84dac3a3b5e40e19cf5c0532f3306336d73c082841565d42b3bfa1ab28c447`.
Live wiring обязано заново измерить lifetime controller/report, а не наследовать
этот zero-growth source/build result.

Presentation Защиты эфира `RB-M172`: exact `1.0.0-dev.212` добавляет 27 bounded
записей каталога EN/RU и caller-owned состояние presentation на четыре строки.
Static RAM остаётся 225 688 B; linked flash равен 3 319 744 B, а размеры app/factory
— 3 319 904/3 385 440 B: +2 012 B linked flash и +1 664/+1 664 B images к dev.211,
полностью внутри source/build delta presentation. SHA-256 firmware/factory/ELF:
`300c8b748d7640bfa21cc54fc8cefd6164d980514f4ea433050e3052dfefbe56`/
`565494baab59a5004e9951d49efa84bd0ed7d00c553f38b8383a10cf1ef893fa`/
`8054fc7b82242721948379e53a5f2d725b8ea0241e3c892153373e10c7435dbc`.
Размеры app/factory/ELF — 3 319 904/3 385 440/22 332 172 B. Live capture и TFT
wiring всё ещё обязаны заново измерить foreground/report lifetime; zero роста
resident RAM здесь не является physical runtime budget claim.

TFT integration Защиты эфира `RB-M173`: exact `1.0.0-dev.213` даёт production
runtime один bounded instance controller/report и линкует adapter Navigator/TFT.
Static RAM равна 227 696 B, linked flash — 3 326 584 B: +2 008 B RAM и +6 840 B
linked flash к dev.212. Размеры app/factory/ELF —
3 326 752/3 392 288/22 385 524 B. SHA-256 firmware/factory/ELF:
`8e01268b7c640bee4a9bf36132947b50b74327346a0dab29e610f4737a45b805`/
`6bb1ab8745c4641a5ff7cdf75b170e4882452aa76405dec3fe2dd1a997c53a7d`/
`a42ac823d58a5fad3eab452887089270c649281e545b23a8747357cfadbef27f`.
Live capture buffer, task или radio owner не добавлены; physical heap остаётся
неизмеренным до готовности live adapter и одного delta HIL.

Bounded live capture Защиты эфира `RB-M174`: exact `1.0.0-dev.214` переиспользует
единственный resident `BoardWifiPassiveCapture`, его fixed buffer на 16 frames и
существующий lifecycle Wi-Fi driver; второй buffer capture или task не добавляется.
Monitor/report state увеличивает static RAM на 64 B до 227 760 B. Linked flash равен
3 330 584 B (+4 000 B); размеры app/factory/ELF —
3 331 088/3 396 624/22 410 600 B (+4 336/+4 336/+25 076 B).
SHA-256 firmware/factory/ELF:
`cc97e4ef5236105df17dc8a52c14e9bf72b08ebe28dc6e26afc27ce8cedc53ba`/
`91bff6744cf1c32cc2b0942eb909e02dd85d0ee6685053b5ce489b462ee195e5`/
`6e34eafe189f37cccb1c54abc5c35c32a103e3c3af85df0c7750a4af83957e1f`.
Это source/build evidence; live recovery heap и cleanup driver остаются physical
delta measurement, а не inferred budget claim.

Wi-Fi identity detector Защиты эфира `RB-M175`: exact `1.0.0-dev.215` расширяет
существующий bounded report и каталог EN/RU без task, radio owner или второго
capture buffer. Static RAM равна 228 080 B (+320 B), linked flash — 3 334 152 B
(+3 568 B). Размеры app/factory/ELF —
3 334 656/3 400 192/22 447 288 B (+3 568/+3 568/+36 688 B).
SHA-256 firmware/factory/ELF:
`f0363d45d50603a1cbf2881a85b78d6eb6e5bcf61f25791b6801548711d07b5f`/
`7b8d1126502341f14e7cd01ade8b07e80766ce464363f25d31b19030c4aa0e4c`/
`f70492ea627c4499d5b217e52063e6737058c395afa067423c2630da1427412f`.
Оптимизированный host compiler показывает 2 640 B static stack use для полного
вызова detector после разделения lifetime scratch disconnect/identity и замены
identity pass на bounded rereads. Это review aid, а не Xtensa HIL proof. В этом
checkpoint identity detector выключен на его incomplete live-retention path, поэтому
build не добавляет claim по live heap или physical radio.

Bounded live retention identity Защиты эфира `RB-M176`: exact
`1.0.0-dev.216` переиспользует тот же capture на 16 frames и добавляет только восемь
fixed exact identity keys; второго frame buffer, task или radio owner по-прежнему
нет. Static RAM равна 228 432 B (+352 B), linked flash — 3 335 404 B (+1 252 B).
Размеры app/factory/ELF — 3 335 904/3 401 440/22 429 812 B
(+1 248/+1 248/−17 476 B). SHA-256 firmware/factory/ELF:
`2c9eecfef8f65067f5e1104189a6de1d8f34ce1c7365b926a5cfd58dc751d081`/
`abb1cfd2aca3d48fb647b518535082cbd7a89476b3b82c36284278846ad9e276`/
`49eb21f5c3be4e15bd3a4512bb5cf8025aea7624d4fa3bd0e5251c4084401813`.
Оптимизированный host stack report показывает 2 592 B для `inspectWifi`, 176 B для
identity decode и 144 B для ingress key helper. Live heap/cleanup не заявляются до
physical HIL; incomplete identity retention выключает detector и учитывается как
source loss, а не clean result.

Детектор быстрой смены identity Защиты эфира `RB-M177`: exact
`1.0.0-dev.217` переиспользует complete bounded identity evidence и существующий
путь report/UI; он не добавляет task, radio owner, второй capture buffer или
static-RAM allocation. Static RAM остаётся 228 432 B, linked flash равен
3 336 748 B (+1 344 B). Размеры app/factory/ELF —
3 337 248/3 402 784/22 471 948 B (+1 344/+1 344/+42 136 B).
SHA-256 firmware/factory/ELF:
`d89ec463004b1c325af2655bac717bb699fc1da7ba3d15a6bba574f0840bee08`/
`5f19d2112b8ce7ebe61b18d2270ec205daf1ff9a85e1aae178a4643c8f091564`/
`bc9bdba79c75ed9b1c8be84ab2eeefdb105d8a9784d5065b33e55e79bebc0838`.
Оптимизированный host stack report показывает 2 656 B для `inspectWifi` (+64 B),
176 B для identity decode и 144 B для ingress key helper. Live heap и поведение
physical radio не заявляются до HIL; при incomplete identity retention detector
выключен.

Фундамент BLE tracker-compatible presence Защиты эфира `RB-M178`: exact
`1.0.0-dev.218` добавляет bounded detector нормализованных observations, но не
добавляет live adapter, task, radio owner, capture buffer, presentation path или
automatic response. Static RAM остаётся 228 432 B, linked flash равен 3 336 848 B
(+100 B). Размеры app/factory/ELF — 3 337 344/3 402 880/22 488 644 B
(+96/+96/+16 696 B). SHA-256 firmware/factory/ELF:
`bddb74d5a43b7cd565189163321369a130895558b61ee319c8c74591a69cd38b`/
`db3e444fc6c262c0064c6ddcf4c845cb1d1dcee366a21d04b8ab8a5e55cc56f0`/
`7e1bb82c00f233f19a3e10962b6e138aa0774fe23a01b4ea228be71ab3135171`.
Optimized host stack report показывает 2 320 B для `inspectBle`, меньше текущих
2 416 B `inspectWifi`. Это review aid, а не Xtensa HIL proof; поскольку live adapter
и product presentation намеренно отсутствуют, claim по live heap, radio, TFT или
cleanup не возникает.

Channel-free BLE presentation Защиты эфира `RB-M179`: exact
`1.0.0-dev.219` добавляет kind-aware controller validation и десять entries catalog
EN/RU, но не добавляет live adapter, task, radio owner или capture buffer. Static RAM
остаётся 228 432 B, linked flash равен 3 337 992 B (+1 144 B). Размеры
app/factory/ELF — 3 338 496/3 404 032/22 491 624 B (+1 152/+1 152/+2 980 B).
SHA-256 firmware/factory/ELF:
`2307faece5b5cb9c2061f79bd7acfffdccceecde507149f2053708e6147c523b`/
`7b119e5f3ee5f11b489a4b3205562b3fe3f58e7df19ff59e178400010e88d949`/
`c1211e966c67ff72498a3f9febeb79e1b01b50ba7402cfff2d55a03cecddeb0c`.
Claim по live heap, radio, TFT или cleanup не возникает до bounded BLE
retention/handoff и physical evidence.

Фундамент bounded BLE retention Защиты эфира `RB-M180`: exact
`1.0.0-dev.220` добавляет один fixed retention object на 32 observations и учёт raw
reports, но не новый task, stack или radio owner. Product Survey сохраняет default
address deduplication; только будущий request Защиты эфира сохраняет повторные reports.
Static RAM остаётся 228 432 B, linked flash равен 3 338 104 B (+112 B).
Размеры app/factory/ELF — 3 338 608/3 404 144/22 504 576 B
(+112/+112/+12 952 B). SHA-256 firmware/factory/ELF:
`fa864011d49d1db7ccf1f3a4dcb62cd6f24a9ec5eb3bbeebecfe3cb4314406b1`/
`79c2ea1011edfc5dac0e356945d93e7950c0ea982ab97b897539f52b23428617`/
`02c2a0c653990e03bf262c90dd8e46009c9968fa7363d26f570ff487e2128bdc`.
Полный tracked host suite и production build проходят. Live worker stack/heap,
radio cleanup и TFT behavior не заявляются до runtime wiring и HIL.

Supervised BLE runtime handoff Защиты эфира `RB-M181`: exact
`1.0.0-dev.221` переиспользует существующие task, stack Product Survey worker и
lifecycle NimBLE. Он добавляет один fixed workspace Защиты эфира на 32 observations
и одну single-result queue, а не второй task, BLE stack или radio owner. Static RAM
равна 235 424 B (+6 992 B), linked flash — 3 352 048 B (+13 944 B). Linker
оставляет 23 124 B internal DIRAM и сообщает 71,8% static RAM. Размеры
app/factory/ELF — 3 352 544/3 418 080/22 544 696 B
(+13 936/+13 936/+40 120 B). SHA-256 firmware/factory/ELF:
`88b0134205b5882c19db3caf7b1494b32de8bd49a1d88a4f90f300a14f202e8e`/
`109b92a2ec01ea48f2cfa0bf6f24c75bc1ddc717997737557c9edf1ffea4cdf2`/
`21d12b39c81812b5fa4d2558a55e2e827381f9636316e8c8371558a5a09f00c7`.
Полный tracked host suite и production build проходят. Runtime heap/stack, radio
cleanup и timing TFT не заявляются до physical HIL.

Bounded индикатор Wi-Fi noise Защиты эфира `RB-M182`: exact
`1.0.0-dev.222` добавляет восемь fixed normalized samples receive noise и их
fail-closed accounting; новый task, radio owner, TX path или dynamic allocation не
добавляются. Static RAM равна 235 680 B (+256 B), linked flash — 3 356 404 B
(+4 356 B). Размеры app/factory/ELF — 3 356 912/3 422 448/22 567 052 B
(+4 368/+4 368/+22 356 B). SHA-256 firmware/factory/ELF:
`7a75b5db714eabf1eb730c50e64e34670a5cbad82905c4c50ebac38b2c2756b6`/
`1341dd90ad7b7a7512cf963fabdacfa2c2b069cdfb68279e301d854fcab81024`/
`b1103ab3499d684f553e41fcf146dd72a740b6d849cb6fe625cc60e9d9760b5d`.
Полный tracked host suite и production build проходят. Runtime heap/stack, radio
cleanup и timing TFT не заявляются до physical HIL.

Foundation parser захвата аутентификации CAP-049 `RB-M183`: exact
`1.0.0-dev.242` добавляет allocation-free host parser с жёсткими bounds: 64
просмотренных immutable Wi-Fi frames, 16 exact evidence references, четыре peers,
четыре PMKID и report 1 536 B. Malformed, truncated, unread, capacity-lost и
unsupported input fail closed до publication. `E-BUILD-172`/`E-AUTO-146` принимают
эти host bounds; claim allocation для live driver, radio/lease, storage, UI или export
ещё нет. Combined production build использует 244 696 B static RAM и 3 372 276 B
linked flash, оставляя 13 852 B internal DIRAM. SHA-256 firmware:
`2b4a9fbdfa294bc3e632a6f707b37b3dcbc9151888320dc0ceda607794f21f5e`, embedded
app identity: `02b27bc09cbb507a621e6a69ae42b41090e50e371ec3c4f4d85c3de1e2116d5d`.

Полный physical acceptance «Защиты эфира» `RB-M184`: `E-BUILD-173`/`E-AUTO-147`/
`E-HIL-190` связывают те же exact bytes dev.242 и доказывают, что complete baseline
и deterministic capacity-loss lifecycles не оставляют утечку warmed working set.
Свободный heap начинается/восстанавливается на 60 540 B, после release queue растёт
до 72 324 B и сохраняет largest block 25 588 B. Baseline удерживает 54 BLE records
с zero drops; injection удерживает 1 и теряет ровно 904 из 905 observed, остаётся
incomplete/inconclusive и завершает Home/none/lease 0. SHA-256 retained run/index:
`3c2b372956563009893c060b4ea5fab365b7b6cad057527bb29af6c63e469956`/
`b728e5430b2de6ba73cccbe12c02b37497b17cdda9e37efea85537717498d766`.
Это measured runtime bound board-01 для CAP-048, а не claim ресурсов всё ещё
host-only интеграции CAP-049.

Acceptance повторного FAT/VFS mount CAP-049 `RB-M185`: exact `1.0.0-dev.246` на
source `54cf455810c15753220fb2bd0f497381dfabde48` использует application image
3 395 568 B внутри slot 4 194 304 B, оставляя 798 736 B, и оставляет 11 640 B
internal DIRAM. SHA-256 firmware/app identity равны
`8cdd2c01b9e3c8423d665e39b7a0581d0f5039ae4e96fa617fee934dc7ea3b6e`/
`3c4643e014262722c3ef3ce640e2d9964f0df1431ee49cd897d331291927a221`.
Fail-closed diagnostic dev.245 доказал, что hardware, initialization SPI и drive
FatFs всё ещё доступны на втором mount в том же boot: bus error равен нулю, но
largest internal block 17 396 B не вмещает contiguous VFS workspace IDF 5.5.4
размером 29 512 B для неиспользуемого `max_files=5`, возвращая error 257 после трёх
попыток. Продукт использует direct FatFs и ровно один сериализованный `FIL`, поэтому
dev.246 закрепляет `max_files=1` и уменьшает требуемый workspace до 12 968 B без
изменения storage schema или concurrency policy. Physical `E-HIL-191` затем завершает
первый mount при largest block 31 732 B и второй при 17 396 B с первой попытки/error
zero, доступным drive, final cleanup и lease 0. Retained workflow CAP-049 остаётся
receive-only и не наблюдает authentication evidence, поэтому это focused bound
mount headroom, а не завершение CAP-049, proof terminal commit Product Survey или
budget mixed-workload release/endurance.

Foundation navigation результата и provenance authentication CAP-049 `RB-M186`:
exact host/build `1.0.0-dev.247` на source
`ccb4a3a5351d065e312ca29cf689d3acd9e6d93b` использует 247 016 B static RAM и
linked image 3 403 120 B (PlatformIO Flash used сообщает 3 402 780 B). Application
3 403 280 B оставляет 791 024 B в OTA slot,
остаток internal DIRAM равен 11 528 B. SHA-256 application/factory:
`b3bb3e3a787ef36aa306d0711a40c0b5b730a02f69fc1d72e4a59315b0435ed1`/
`186c24fbd831db40dc5b936c6bbd91bee7908cefc38c9aa651fbfd8676c09ff1`;
identity ELF/app:
`954a5a80064a951bac6a3f278cdd5e06292d7589871ab132f5cd680e36e9dba4`,
SHA-256 map:
`2fd0300e65fb4b4d4c4b2bc0a1f01bb97627e19a65eb7d1f51503b9b82f79ccf`.
Bounded controller/presenter результата и foundation provenance
schema-8/segment-8/wire-5 не добавляют dynamic allocation, task, radio owner или TX
dependency. Full host suite прошёл до того, как независимое review нашло P1 с
полностью нулевым Key MIC; на этом exact post-fix source проходят focused
capture/policy ASan+UBSan tests, focused review, production build и budget. Это
исторический host/build bound: device не прошивался, поэтому принятым physical
runtime/heap baseline был dev.246 `RB-M185`, cadence была 11/15; physical bound ниже
заменён `RB-M187`. Product persistence и
export не подключены, standard artifact serializer ещё не существует,
`exportEligibility` остаётся `NotEvaluated`.

Physical navigation CAP-049 и regression product-entry `RB-M187`: exact
`1.0.0-dev.248` на source `e62599c1827e249845105405797cb75aedaa5226`
использует 229 960 B static RAM и linked image 3 413 764 B. Размеры exact прошитых
application/factory — 3 414 272/3 479 808 B с SHA-256
`15ab98ef95a85afae840b913ddeef60f0883bccf99a03e4f74ed50f1235ac40c`/
`d75ff42bfbd343d87e29022e4b16c1816db244c48705d769af679a290b3fffc0`;
identity ELF/app —
`1c908d29de25e84dba3423657464bedb0ced245115e7a18e93c9a3996c7bb5f1`,
SHA-256 map —
`c5484b781e923ef0d247aa274aa834832a29072e71b858420a0858cc908710a8`.
На оригинальном DIV два lifecycle Bluetooth сохраняют одинаковый free heap 75 380 B,
zero driver drops и exact bounded retention accounting. Верхнее меню и paths
CAP-049 navigation/Повтор/replay-negative возвращаются в Home/none/lease 0 с
content-only repaint. Это принимает physical runtime/navigation bound и двигает
cadence до 12/15; всё ещё отсутствующие standard serializer, product
persistence/export, полезный EAPOL/PMKID evidence и cold recovery Product Survey не
заявляются.

Foundation standard artifact persistence/export CAP-049 `RB-M188`: exact host/build
`1.0.0-dev.249` на product source
`d47b2ee5e1636981474398246c5e0c49d88db2ea` использует 230 000 B static RAM и
3 425 112 B linked flash. Размеры app/factory — 3 425 616/3 491 152 B с
SHA-256
`2af18b4ea99c5128282077963537ec4bd5e4fd0877895bc0d038e2b195174a9b`/
`29013dda59a75d4c66d9c4b5c0067ee2c49ad4290ff1caa7b9675302a9dbac78`;
identity ELF/app —
`fb521cbe0e7c8e3fee2dbaf3765c3d101c236a9f3c0bc8cb7341f16ee63f1414`,
SHA-256 map —
`b5bb81217479e73a8962a98a9b9fe04480263f1881ea996ecf675d59ab2a8a0b`.
Против `RB-M187` static RAM растёт на 40 B, linked flash — на 11 348 B, а оба
image — на 11 344 B. Build сохраняет 28 544 B остатка internal DIRAM,
заполняет IRAM до 16 384/16 384 B и оставляет 768 688 B внутри 4 MiB app-slot OTA,
выше обязательного резерва 524 288 B. Новый bounded serializer, states controller и
обобщённый background store worker не добавляют dynamic artifact-sized buffer и
потоково экспортируют exact reopened generation. Это только host/build bound:
dev.248 остаётся принятым physical baseline heap/cadence до проверки Save, commit SD,
cold reopen и полезного export artifact на оригинальном DIV.

Physical bound bounded repaint Bluetooth `RB-M189`: exact `1.0.0-dev.250` на source
`bfe646e4d9408b4cd0ec1dc58c7c4e9c38a4ac0d` использует 230 400 B static RAM и
3 426 528 B linked flash. Размеры app/factory — 3 427 024/3 492 560 B с SHA-256
`4c82162eab199532fba475df8341c520d43bce8bf4ab04bc31f930bf5f310bce`/
`0b6c24cdc3ac4a90e7e2725be18bb62ca6d9a30c5eabb5f490f112782006a923`;
identity ELF/app —
`3c401f5b1a7ffb9e15298b6716506ec9475e7d4c980aa5adc0ddbd756d08b750`,
SHA-256 map —
`614a52bc07636efd0279ab4f100e7dfc78cd58c292a11de41c4a68cb05142e3f`.
Против `RB-M188` visual cache четырёх строк Bluetooth, delta-state signal-card и
instrumentation добавляют 400 B static RAM, 1 416 B linked flash и 1 408 B в каждый
image; внутри app-slot OTA 4 MiB остаётся 767 280 B. Physical HIL продвигает catalog,
перерисовывая ровно две видимые строки, выполняет один detail delta repaint без full
content clear и возвращается Home/none/lease 0 при zero BLE driver drops. Это принимает
focused physical repaint/runtime bound и двигает cadence до 13/15, но не принимает
унаследованный path persistence/export CAP-049.

Physical bound atomic-card Bluetooth `RB-M190`: exact `1.0.0-dev.251` на source
`d84f8259c6781dcbe90ae00fba00f0c6f4379c32` использует 230 728 B static RAM и
3 434 756 B linked flash. Размеры app/factory — 3 435 264/3 500 800 B с SHA-256
`66b9f27a32159292d0ec168dce7bafe5871aadf2759541960fc2ab7edd9e4781`/
`e793b1a322a989824aeefc049fa1346e83a50e2b690067b599c5aa9de4845772`;
identity ELF/app —
`698c7a8ef19388762845ec7d95219a09ae132b3a6155bcf351af8486bb04202c`,
SHA-256 map —
`7f3e77e78a45f5516b812a0e617890aef1eb7f4799c687318c123366c9bc2c75`.
Против `RB-M189` объект reusable sprite и instrumentation atomic rows добавляют
328 B static RAM, 8 228 B linked flash и 8 240 B в каждый image; в app-slot OTA
4 MiB остаётся 759 040 B. Реальный live-buffer без PSRAM — один переиспользуемый
sprite 216×24 1-bpp, 648 B, а не full-card framebuffer RGB565. Physical HIL
наблюдает три atomic push строк с zero failures allocation и zero direct fallback,
один delta repaint радара без нового full repaint/content clear, invariant
post-cleanup heap 73 936 B и final Home/none/lease 0. Это принимает оставшийся
runtime bound мерцания Bluetooth-card и двигает cadence до 14/15; persistence/export
CAP-049 остаётся открыта на этом anchor dev.252.

Physical bound persistence/export authentication `RB-M192`: exact
`1.0.0-dev.255` на source `e6d3243104a5849d750176962b083949df792b82`
сохраняет app image 3 445 824 B с SHA-256
`b03e61c0b954a686fe9c7478c9c55ab36eb78c23a5ddd4a4e3d996c597ddbf16`
и embedded app identity
`dee3deef1c7467a355e4b83abc7de13c4d66d74f38de7a3809d4e289de90f2bb`.
Deterministic fixture ограничен двумя raw frames/284 bytes при snap length
256 bytes, одним peer/двумя evidence references, radiotap PCAP 370 bytes/два
records и одной canonical записью `WPA*02` 408 bytes. Boot heap invariant до и
после cold recovery: total/free/min 143 180/70 012/69 740 B; admission analyzer
фиксирует 63 316 B free и largest block 31 732 B. HIL runner не сохраняет raw
artifacts в Git и доказывает zero radio/connect/TX calls, generation 169→170,
read-only recovery с zero writes и final Home/none/lease 0. Это принимает runtime/
storage/export bound CAP-049 и двигает focused cadence до 1/15.

Physical bound стабильной scan-card Bluetooth `RB-M191`: exact
`1.0.0-dev.252` на source `30530812efe045aadd112d8b1b0961a48a48b89b`
использует 231 056 B static RAM и 3 435 604 B linked flash. Размеры app/factory —
3 436 112/3 501 648 B с SHA-256
`7cab8fd8a85b9fb437d21cdbc6d81e4a24aa050a814a9714337697d5cdb100a1`/
`b581fff7b8911250b549e20414a409f797fd133086782139fee599fd2ce4bd45`;
identity ELF/app —
`19f2667f3b3a1a755417dce602f29977f04cc977541c04b33045bd8f4e3bf101`,
SHA-256 map —
`f46bdc1d538014a3c8f4cb5b053354d279cb543d1da8a083d9fc65c045da1d34`.
Против `RB-M190` второй reusable sprite metadata 216×19 1-bpp/513 B,
state coalescing 4 Hz и counters добавляют 328 B static RAM, 848 B linked
flash, 848 B в app image и 848 B в factory image; в app-slot OTA 4 MiB остаётся
758 192 B. Physical HIL держит одну реальную карточку открытой два полных scan
cycle/2 633 ms, выполняет 6 refreshes, объединяет 19 лишних events, применяет
последнее pending state и фиксирует zero full/content clears, failures sprite и
direct fallbacks. Затем тот же image проходит periodic matrix
Home/RF/Targets/companion с invariant heap 147 748/73 608 B и zero writes/TX,
что принимает runtime/build bound и сбрасывает cadence до 0/15. Persistence/export
CAP-049 остаётся открыта.

Host/build bound Offline Field Survey `RB-M193`: exact `1.0.0-dev.256` на source
`dab7394b0c2fbd36857fc1088e5454da3c48cbe5` добавляет один allocation-free catalog
5 656 B не более чем на 64 компактные записи по 88 B. Catalog не владеет второй
Session-sized buffer, heap allocation или raw packet payload; он хранит только exact
identity из шести bytes, bounded label, first/latest/strongest evidence и факты
Wi-Fi/BLE для comparison/export. Потерянная source record, capacity loss, malformed
identity/radio или out-of-order update снимает признак complete input. Serializer
WiGLE использует fixed caller storage и честно оставляет location/time пустыми.
Static RAM/linked flash — 235 624/3 445 368 B. Размеры app/factory/ELF —
3 445 872/3 511 408/23 151 372 B, SHA-256 —
`1e2095e50e12630648cdd488702f2aeb17943a658510d27cd70fee7392411e25`/
`d405706c45cc7dc79f708bac125a9b2fbeac1d5cddb7e1f793a7907bcd64f1d2`/
`b693220dc351d16000159abe4eac56fbdcbb8ed3b4df1e09dd2c13eeeec5eff1`.
В app-slot OTA 4 MiB остаётся 748 432 B при обязательном floor 524 288 B. Это только
host/build bound; runtime heap, storage routing и physical cleanup остаются открыты
до product workflow.

Product-tracker bound Offline Field Survey `RB-M194`: exact host/build
`1.0.0-dev.257` на source `c5634400dc7a0dea23358ef4f21ff3255ccbc59a`
добавляет один allocation-free tracker 6 200 B. Он включает существующий current
catalog 5 656 B и только 64 компактные записи kind/identity предыдущего визита;
поэтому прирост против `RB-M193` составляет 6 192 B global RAM, а не второй catalog
или Session. Baseline допускается только по exact session id и complete input;
bounded comparison O(64²) выполняется только после Stop/commit, не использует heap
и не запускает radio или storage. Static RAM/linked flash — 241 816/3 454 652 B.
Размеры app/factory/ELF — 3 455 152/3 520 688/23 394 676 B, SHA-256 —
`1ab506fe080244c56d2886ad1c9bcbd625acf3230735f41b89377e57e22f6ed6`/
`ae7d24e0393f741f4c6ac20dcd19326b26343e49f269afb2db23d8315c2002ca`/
`5753bf949b1237d4c3325ea953acdb61d275b2445f65f4317824af0ccc865d71`.
В app-slot OTA 4 MiB остаётся 739 152 B при floor 524 288 B. Runtime heap и
physical cleanup остаются открыты до focused board HIL.

Regression bound старта BLE Field Survey `RB-M195`: exact physical
`1.0.0-dev.261` на source `b38464f93cdb7807734a24b1e1a08f03d4bbae24`
выносит 4 560 B raw capture CAP-049, нужного только HIL, из resident RAM продукта.
Он создаётся через `nothrow` только после допуска exact authenticated fixture и
освобождается на каждом path clear/rejection. Static RAM — 231 624 B, ровно на
4 560 B меньше dev.260 и на 10 192 B меньше product-slice build dev.257; отдельное
изменение terminal workspace dev.260 и это allocation change нельзя суммировать по
размерам source objects, потому что менялись также code и alignment. Размеры linked
image/app/factory/ELF — 3 447 556/3 447 712/3 513 248/23 392 412 B. SHA-256
app/factory/ELF/map —
`e5322abf49c43f8c7b561306bb811afc1c597a523a3b8d7ae8cb42fd3c26ca1e`/
`14db7f5b3418c665cfda8388f569a7fe7062ee9754faa1fd0d1b171c1dbdb59b`/
`fa7edeb12c95d14301702ff68e2c0a5d245ba8783bccda362b54ee724d42eb51`/
`0f422482266575d790e350d6fe9abce58bde6595986da3b40819a8368c1c8b36`.
В app-slot OTA 4 MiB остаётся 746 592 B при обязательном floor 524 288 B.
На оригинальном board-01 boot heap равен 74 012 B; BLE достигает `ready` из
73 360 B free/28 660 B largest block и завершает один real cycle 12 Wi-Fi/33 BLE,
45 forwarded, zero drops, zero writes и exact cleanup. Compact
[evidence preflight](../../tests/hil/evidence/board-01-field-survey-preflight-1.0.0-dev.261.json)
является только regression, а не capability gate first/revisit CAP-050. `RB-M196`
закрывает accumulation repeated cycles и runtime boundary committed visits; routing
native/WiGLE, station capture и trusted GPS/UTC остаются открыты.

Bound one-pass/commit/recovery Offline Field Survey `RB-M196`: exact physical
`1.0.0-dev.262` на source `99aacd01336a065e18b52035ec243e2eb47abd92`
не добавляет измеримой static RAM против `RB-M195`: 231 624 B. Field Visit теперь
учитывает один внешний проход selected sources и запрашивает Pause только когда
Wi-Fi и BLE каждый либо завершились, либо объявлены unavailable; generic monitoring
остаётся continuous. Размеры app/factory — 3 447 824/3 513 360 B с SHA-256
`8e21225c6041126a7ff11b0fe50b64d2dd3e64705e9b592cc33d3820aa551ae1`/
`a60df4249a7005c9671dab14eeeea160cee553de199aa2055d16da1b4c0994ec`;
SHA-256 ELF/map —
`deeccd42afe1112da6b47c29eb5269ce6b9da332819aef2d0bd735b6321b91a6`/
`3aaeb56afed302d81003bf8e5494346db65b21b970e2c6a2261e4ac4140f77a2`.
В app-slot OTA 4 MiB остаётся 746 480 B при обязательном floor 524 288 B.
Preflight, first visit и revisit завершают ровно по 1/1 cycles Wi-Fi/BLE с zero
source/pipeline drops. Committed visits содержат 46 и 52 bounded records, записывают
3 737 и 7 890 B, сохраняют по шесть timeline windows и двигают generation
170→171→172. Deterministic incomplete-input query не затрагивает radio или storage.
Финальный cold delta не сканирует и не пишет, а на attempt 1 восстанавливает exact
generation 172/52 read-only с zero physical/blocked writes и owner/lease none/0.
Исходный full runner ошибочно помечал себя eligible без post-commit cold reopen;
retained acceptance явно объединяет этот run с recovery-only delta, а исправленный
runner теперь требует integrated cold evidence для eligibility будущего full run.
Compact [evidence визитов](../../tests/hil/evidence/board-01-field-survey-visits-1.0.0-dev.262.json)
принимает lifecycle визита, но не native/WiGLE export, live station capture или
trusted GPS/UTC.

Bound export Offline Field Survey `RB-M197`: exact physical `1.0.0-dev.263` на
product source `0f46b4db840bf38e3beac6424623c33fca8e749e` сохраняет static RAM
231 624 B. Formatting native CSV Field Survey allocation-free и использует bounded
caller storage; serial path Library потоково выдаёт native или WiGLE без
запуска receivers и mutation storage. Linked flash — 3 455 384 B. Размеры
app/factory — 3 455 888/3 521 424 B с SHA-256
`be9a5061a59db614e804e36bf1f08b325dff31da93075c92a1eace4b2f3a8d35`/
`82d4a023769178714aeaecd243a05a01e101bdbce5d40cb21e7fe3c7e05c13d5`;
SHA-256 ELF/map —
`9906543f7f541778f7ba5969a7b74e2de81f83b66a30ff1caebc0f509fd0571f`/
`47edfc75a3d18222b6ea68e4c2f0b59b3d5b21a1d47ba2fab5b20d9f6645239b`.
В app-slot OTA 4 MiB остаётся 738 416 B при обязательном floor 524 288 B.
Physical HIL read-only открывает exact generation 172/52 с attempt 1 и выдаёт
52 native rows/4 650 B плюс 52 WiGLE rows/3 573 B. Он выполняет zero scans,
commits, physical/blocked writes, не пишет raw CSV в host evidence и завершается
Home/none/lease 0. WiGLE остаётся `untimed_unlocated` и not upload-ready. Compact
[evidence export](../../tests/hil/evidence/board-01-field-survey-export-1.0.0-dev.263.json)
принимает routing/truthfulness, но не live station capture или trusted GPS/UTC.

Bound stations Offline Field Survey `RB-M198`: exact physical `1.0.0-dev.266` на
source `ffd8f8f23cd3153a5de415049fc2665544af66c1` сохраняет static RAM 231 624 B.
Receive-only observer stations не добавляет persistent heap allocation и ограничен
тремя complete sweep 1–13, после чего удаляет promiscuous callback и освобождает
Wi-Fi для BLE. Linked flash — 3 458 056 B. Размеры app/factory —
3 458 560/3 524 096 B с SHA-256
`c3638e1c0266eacf88cef69e275152bf6589e5f5cfcecb941501b82709026447`/
`cf2f69d5482bd5da5c966af8518156a96548462b6bf44d3b56d33791718bc27e`;
SHA-256 ELF/map —
`1066d57bcc0cb4fd4dce311a6db6e72a87be83e1513c93be26f2c434da4112aa`/
`376a659a1da05132e50e4fd8671e5e50c42c719ca49ff6ec3cb25887cf1730ab`.
В app-slot OTA 4 MiB остаётся 735 744 B — на 211 456 B выше обязательного floor.
Physical first/revisit сохраняют по 51 bounded record с 2 stations и zero drops,
затем cold-recover-ят exact generation 175/51 read-only. No-reflash export delta
сохраняет обе station rows в 51 native rows/4 593 B и исключает ровно их из
49 WiGLE rows/3 362 B с zero scans/commits/writes и final Home/none/lease 0. Compact
[evidence stations](../../tests/hil/evidence/board-01-field-survey-stations-1.0.0-dev.266.json)
принимает live station capture и его export boundary, но не trusted GPS/UTC.

Bound trusted context Offline Field Survey `RB-M199`: exact physical
`1.0.0-dev.267` на source `eb23d614785420a10588a4ae5a8d3e351021702b` использует
231 736 B static RAM, на 112 B больше `RB-M198`. Schema 9 добавляет один fixed
64-byte checksummed `LTGC` record на segment и продолжает читать schemas 1…8;
dynamic allocation или resident raw-GPS buffer не добавляются. Linked flash —
3 459 768 B. Размеры app/factory — 3 460 272/3 525 808 B с SHA-256
`8d6982923dafdca1d7522e197eb7119cf69cbcb7045087bb193a58d2313cca55`/
`b3ba37cb6201e73682dc4f1aed5ed3cd999567382cc4f76e8e44b967de7ad63c`;
SHA-256 ELF/map —
`c33fed0f41e7a5594342aa3f3bc58787048793460bf39b7de2cd0d6d1945f3a1`/
`5f6f24f36d1ea80bf7d1b2545b45addfe62cc52bd418c7ec19c42b1f6d1c7a46`.
В app-slot OTA 4 MiB остаётся 734 032 B, на 209 744 B выше обязательного floor.
Fresh-flash focused HIL cold-recover-ит generation 175/51 read-only и экспортирует
51 native rows/4 593 B плюс 49 WiGLE rows/3 362 B с zero scans/commits/physical
writes. Поскольку stock hardware не имеет GPS source, оно честно сообщает
`trusted_source=none`, `untimed_unlocated`, `upload_ready=false`; отдельно
профилированный GPS fixture всё ещё нужен для physical located/timed acceptance.
Compact [evidence trusted context](../../tests/hil/evidence/board-01-field-survey-trusted-context-1.0.0-dev.267.json)
принимает bounded software/persistence slice и stock absence path.

Bound foundation BLE Inspector `RB-M200`: exact host/build `1.0.0-dev.268` на
source `52b2d1655b486ae029ce2402317c2f270bf88c0c` сохраняет static RAM 231 736 B.
Raw capture — caller-owned object 1 856 B с 32 fixed records по 56 B; GATT controller
— caller-owned object 2 136 B с 16 fixed service facts и 48 fixed characteristic
facts по 32 B. В этом slice они не являются resident product globals. Linked flash
растёт только на 508 B до 3 460 276 B. Размеры app/factory —
3 460 784/3 526 320 B с SHA-256
`af6b6a2d67308c39c469461b1b866786d5b9b892504d292c99ac891176bd5b66`/
`a7b7eac59a4415a399a2fb7a8bade1d58552c505c2856b96bea331f293d913fe`;
SHA-256 ELF/map —
`502fee63a64cebac3373be98cbccdff05ac928b8de0dbff191800d7972f52b69`/
`7f14b592d9712dbe005e2445b41176549da5e393bb5bcf702d99292d4ba346a7`.
В OTA slot 4 MiB остаётся 733 520 B, на 209 232 B выше mandatory floor. Product
integration обязан выбрать для bounded objects явный non-stack lifetime и повторно
измерить live NimBLE heap до physical admission.

Board-02 добавляет physical-variant fact, а не доступный memory budget. ROM сообщает
16 777 216 B flash и 8 388 608 B встроенной Octal PSRAM на модуле N16R8, тогда как
exact compatibility product возвращает `psramFound=false`. GPIO35/36/37 уже заняты
stock display bus, а OPI-enabled experiment не достигает стабильного product boot.
Поэтому portable ledger остаётся 16 MiB flash / zero PSRAM; кажущиеся 8 MiB нельзя
использовать для buffers, caches или admission функций. Source-bound details
сохранены в [variant evidence](../../tests/hil/evidence/board-02-hardware-variant-20260823.json).
