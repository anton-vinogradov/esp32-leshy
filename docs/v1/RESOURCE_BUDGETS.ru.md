# ESP32-Leshy 1.x — реестр ресурсных бюджетов

*Читать на: [English](RESOURCE_BUDGETS.md) · **Русский***

Статус документа: **S1 draft — bootstrap, probe UI и один guarded FAT persistence
run измерены; product boot, storage endurance, power и shared bus остаются открытыми**.

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

`heap_min_free` probe относится только к короткой diagnostic run. Он не предсказывает
буферы Wi-Fi/BLE, display caches, Session queues, storage transactions или
восьмичасовой Survey. Размер 0.x включает legacy functionality и feasibility
contracts, поэтому не задаёт форму clean platform.

## Временные guardrails 1.x

Это причины для review, а не evidence выполнения продуктом NFR.

| ID | Guardrail | Обоснование / закрытие |
|---|---|---|
| RB-01 | Ни один обязательный путь не зависит от PSRAM | board-01 и BOM задают envelope N16/no-PSRAM; расширить его может только новое HW-T01 evidence |
| RB-02 | Сохранить два bootable app slots и не менее 12,5% свободного места в выбранном slot | сохраняет OTA/rollback и рост; финальные значения задаст partition ADR |
| RB-03 | Clean S2 platform: static RAM ≤ 96 KiB и free internal heap ≥ 240 KiB после interactive boot | оставляет место первому radio/storage slice; измеряется на independent target |
| RB-04 | S3 passive Survey steady state: free internal heap ≥ 160 KiB и minimum ≥ 128 KiB без нисходящего тренда за 8 ч | резерв для bounded workers/parsers/export; закрывается heap time series и queue high-water marks |
| RB-05 | Interactive UI ≤ 2 с после cold boot; UI callbacks ≤ 10 мс; Back/release lease ≤ 150 мс | существующие NFR-001…003; закрывается device timestamps и внешним HIL timing |
| RB-06 | Sustained storage throughput ≥ 4× measured p99 ingress выбранного source set; commit/power-cut сохраняет все ранее committed records | вместо произвольной SD-only цифры; source rate, SD и LittleFS измеряются отдельно |
| RB-07 | 10 000 переходов radio→storage→radio дают ноль bus errors, inactive non-owner CS и ноль leaked leases | transaction policy закрывается только HW-T03/HW-T05 trace evidence |
| RB-08 | Unmeasured receiver combination не включается по умолчанию; принятые combinations проходят endurance без brownout/reset внутри measured regulator/thermal limits | power numbers требуют HW-T10; отсутствие прибора сужает scope, а не создаёт вымышленную capacity |

## Матрица закрытия измерений

| Область | Текущее состояние | Следующее воспроизводимое измерение | Влияние на gate |
|---|---|---|---|
| Flash/static RAM | platform/runtime, Survey UI, codec, SessionStore, persistent Library/export, SD metadata, guarded FAT persistence, SD throughput, software-reset matrix и Wi-Fi source slice measured; shared recovery workspace возвращает 3 044 B ниже RB-03; LittleFS slice открыт | реализовать product workers и отдельно disposable LittleFS adapter; сохранять size/map deltas против RB-02/03/04 | lower bound S1, gate S2/S3 |
| Runtime heap/queues | lease lifecycle измерен на 1 000 UI cycles; fixed FIFO 64 прошёл real Wi-Fi→SD→Library path с high-water 18 и zero drops; short-run minimum 147 692 B выше floor RB-04 | отделить concurrent receiver/storage workers, затем снять steady/min heap, queue high-water и trend за 8 ч | lower bound S1, endurance S3/S4 |
| Boot/UI latency | capability-built home interactive-ready 0,373 с и TFT capture measured | измерить внешний cold power-on и поздние product services, не только device milestone | блокирует final verification NFR-001, не bootstrap S2 |
| Storage throughput/atomicity | bounded SessionStore matrices, guarded FAT/remount/reset evidence и passive Wi-Fi ingress измерены; real FIFO/batch path даёт 12 957 encoded B/s против required 2 184 B/s и reopens после remount | перенести path в product workers/Stop, проверить boot catalog, readiness retry при natural transient, затем отдельно LittleFS/power-cut/endurance | блокирует полную verification PR-005 и RB-06 |
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
  concurrent workers требуют отдельного map/8 h review.
- Storage, power и shared-bus limits остаются явными unknown; зависимые от них
  возможности нельзя перевести из `unknown` в `available` одной документацией.
