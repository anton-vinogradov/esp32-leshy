# ESP32-Leshy 1.x — текущий статус

*Читать на: [English](STATUS.md) · **Русский***

Последнее обновление: **17 августа 2026 года**.

Это единственный документ с живым состоянием проекта. Границы этапов находятся в
[DELIVERY_PLAN.ru.md](DELIVERY_PLAN.ru.md), а правила обновления — в
[GOVERNANCE.ru.md](GOVERNANCE.ru.md).

## Сейчас

- **Активный этап:** `S1 — Evidence baseline`.
- **Последний закрытый этап:** `S0 — Governance и граница поколений`.
- **Рабочая база репозитория:** `8e4bd92` плюс текущий невыпущенный slice 0.46 с
  bounded boot recovery и endurance runner.
- **Релизный статус:** 0.x — замороженный PoC; пользовательского бинарника 1.x ещё
  нет.
- **Главная цель текущего этапа:** подтвердить ограничения ESP32-DIV и перевести PRD
  1.0.0 из draft в принятый baseline.

## Состояние этапов

| Этап | Статус | Подтверждённый результат | Что отделяет от gate |
|---|---|---|---|
| S0 | `done` | архив 0.x, governance, delivery plan, status, traceability, маркировка installer 0.x | — |
| S1 | `active` | vision, конкурентный срез, draft PRD 0.2, product-reviewed `CAP-001…047`, UX-01/02 и Stage Demo contracts, workflows, constrained hardware unknowns, partial HIL/budgets, risk register и пять ADR; automatic device-smoke v6 плюс physical UI-HIL-A8 проверяют keypad path, а board-01 проходит exact-CID real passive Survey→persistent SD→cold-boot Library/export | остальные physical evidence и review baseline PRD |
| S2 | `planned` | существуют capability-built home, unified input/TFT capture, atomic-head/media-guard contracts, guarded product FAT lifecycle, первый complete product Survey workflow и lease path AppRuntime/ResourceBroker | formal S1/S2 gate и review production policy |
| S3 | `planned` | bounded Survey/UI, deterministic codec, auto-publishing SessionStore, guarded FAT persistence/reopen/throughput/software-reset recovery, generation fallback и interactive real passive Wi-Fi→FIFO→persistent product SessionStore→cold-boot Library/export работают на board-01 с RB-06 margin; bounded FSInfo не делает full FAT scan, abort сохраняет prior generation | открыты physical power-cut, endurance и LittleFS parity; требуется gate S2 |
| S4 | `planned` | целевая cross-radio модель описана | требуется gate S3 |
| S5 | `planned` | список штатного hardware scope определён | требуется gate S4 |
| S6 | `planned` | Targets/compare/companion определены концептуально | требуется gate S5 |
| S7 | `planned` | Lab/SDK boundaries описаны концептуально | требуется gate S6 |
| S8 | `planned` | release gates определены | требуется gate S7 |

## S1 — выполнено

- 0.x отделена от линии 1.x;
- проанализированы ESP32-DIV original, GhostESP, Bruce, Marauder, Flipper Zero и
  вторичные ориентиры;
- сформулированы `J-01…J-06`, `PR-001…PR-019`, `NFR-001…NFR-010`;
- первый вертикальный результат определён как сохраняемая Survey Session;
- создан двуязычный [`HARDWARE_ENVELOPE`](HARDWARE_ENVELOPE.ru.md) по v2
  schematic/BOM, original firmware и vendor datasheets;
- зафиксированы физические bus/resource domains, safe probe order, `HW-T01…HW-T11`
  и открытые вопросы `HW-U01…HW-U10`;
- PR-001/003/014 и архитектура уточнены с учётом detachable RF shield, внешних
  GPS/PN532 assembly и multi-state capability inventory.
- создана отдельная non-transmitting diagnostic image и операторская процедура для
  HW-T01/T04/T06/T07/T11; NRF #3 fail-closed оставлен `unknown` до HW-T08.
- на board-01 подтверждены ESP32-S3 rev 0.2, 16 MB Quad flash и отсутствие PSRAM;
  read-only I²C отвечает на `0x20` и `0x75`, CP2102 backup/upload/console работает;
- до flash сохранён private full-flash backup 16 MB с SHA-256; raw HIL logs сохранены
  без редактирования.
- после operator confirmation прочитаны identity NRF #1/#2 и CC1101 без TX opcodes;
  NRF #3 оставлен `unknown`, отсутствие физического RF event пока не измерено.
- описаны эталонные сценарии `WF-01…WF-05`, покрывающие J-01…J-06: у каждого есть
  happy/error/cancel path, измеримые acceptance IDs и план evidence.
- создан реестр ресурсных бюджетов: измеренные flash/heap evidence, no-PSRAM и OTA
  guardrails, а также явные unknowns storage/power/shared bus.
- создан risk register R-001…R-017 с controls, closure owners, stage gates и явным
  critical physical-stop risk для любого active action.
- полный пользовательский scope 1.0 разложен на `CAP-001…CAP-047`; UX управляется
  через S1 direction и S2 real-TFT baseline `UX-01…UX-08`, а каждый этап S2…S8
  закрывается воспроизводимым `DEMO-S*`, не ожиданием финальной прошивки.
- product review закрыл шесть скрытых scope gaps: Wi-Fi packet/PCAP Capture,
  screenshot evidence, offline enrichment, safe feedback service, scoped connectivity
  и data backup/restore; каталог принят как полная рабочая граница 1.0.
- UX-01 зафиксировал six-task Home, 28 screen contexts, typed Actions и physical
  Back/Panic mapping; UX-02 определил unavailable/loading/running/degraded/error/
  confirm/success и cleanup для всех WF-01…WF-05 screen families.
- приняты ADR-001…ADR-005: pinned clean toolchain, fail-closed resource policy,
  atomic versioned storage, единая typed Action boundary и hybrid prerelease HIL.
- для HW-U01…HW-U10 заданы binding fail-closed dispositions: у каждого physical
  unknown теперь есть safe default 1.x и named closure evidence.
- independent no-legacy target 1.x собран и запущен на board-01; измерены display,
  пять active-low входов keypad и sub-second interactive-ready milestone;
- добавлены единый physical/diagnostic UI action path и tiled capture реального TFT
  GRAM; board-01 намеренно оставлена на diagnostic target 1.x, а её hash-identified
  полный backup 0.x сохранён.
- реализован dual-head wire/recovery contract ADR-003 и внедрены отказы на каждой
  commit boundary без записи на неизвестный physical media.
- реализованы exact-fingerprint disposable-media authorization, bounded scratch
  namespace/size и negative tests; board diagnostics остаются read-only.
- static probe menu заменён на `AppCatalog`, projected из capability states;
  недоступные Survey/Library объясняются до launch.
- clean target интегрирован с `AppRuntime` и all-or-none `ResourceBroker`; board-01
  прошла 1 000 циклов launch/Back без leaked leases и изменения heap, а p99
  acknowledgement Back/release остался ниже 99 мс.
- добавлены первая bounded модель SurveySession/Observation и passive-only Wi-Fi
  ingress contract; measurement image статически запрещает Wi-Fi API и не трогает
  radio до появления physical no-TX evidence.
- добавлен golden Wi-Fi trace из трёх observations через первый List/Detail
  controller; Back сохраняет running Session, explicit Stop идемпотентен.
- golden workflow отрисован на board-01 с однозначным `SIMULATED / RF OFF`; actual
  TFT traces доказывают, что Back сохраняет Session, а explicit Stop предшествует
  Home/release lease.
- реализован bounded Session codec schema 1: canonical CBOR manifest/records,
  per-record и segment CRC32C, footer validation, offline reopen и deterministic JSON
  summary; exhaustive corruption/truncation tests fail closed.
- stopped golden Session прошла encode → AtomicHead selection → reopen → JSON на
  board-01; все три observations восстановлены, radio/storage не затронуты, Home
  release вернул zero leases.
- тот же commit contract выполнен на реальных temporary host files за валидным
  permit `StorageGuard`: семь isolated scenarios используют file/directory `fsync`;
  все шесть injected failures открывают generation 1, complete commit — generation 2,
  prior bytes остаются неизменными.
- выделен bounded hardware-independent `SessionStore`: он владеет fixed paths, codec
  workspace, automatic generation/older-head publication, rollover, полной payload
  validation и fallback; empty store инициализируется, corrupt/ambiguous heads
  fail closed без writes.
- commit child реально убит `SIGKILL` после каждой из шести boundaries, recovery в
  parent использует только files; результат всегда prior generation или полностью
  materialized new one, открывает 3 observations и сохраняет prior bytes.
- common `SessionStore` запущен на board-01 через bounded two-generation RAM adapter:
  automatic publication 1/A→2/B, reopen generation 2, deliberate corruption нового
  segment, classification `invalid_payload` и fallback на generation 1 проходят.
- добавлен bounded offline Library controller над metadata открытой Session; board-01
  проходит List→Detail→Back→Home с явным
  `SIMULATED RAM | VOLATILE | RF OFF`, удерживая только UI lease.
- первый Library build отклонён после stack canary: reopen создавал полную временную
  `SurveySession`; теперь decode идёт прямо в caller-owned bounded storage, а
  исправленный image проходит host tests и HIL.
- добавлены explicit action Detail→Export Ready и bounded deterministic Library JSON
  artifact; board-01 выдаёт его только после подтверждения, сохраняет provenance и
  fail closed отвечает `not_requested` после возврата Home.
- добавлена typed boundary read-only media adapter/discovery; board-01 читает GPIO38
  без перенастройки, но оставляет SD `unknown`, поскольку непроверенная polarity не
  может доказывать наличие или отсутствие карты. Mount/write не выполняются.
- добавлен mount-authorization gate: explicit target selection, proven read-only
  driver, format disabled и exclusive ownership Storage+RadioSpi; stock Arduino SDFS
  path отклоняется как `driver_not_read_only` без execution.
- добавлен fixed identification-only SD protocol plan вне SDFS: bounded
  CMD0/8/55/ACMD41/58/10/9, только CID/CSD reads; mutating commands и board execution
  статически отклоняются.
- добавлен bounded parser SD transcript с validation response/echo/OCR/CID/CSD и
  capacity; 256 one-bit faults CID/CSD fail closed, а board запускает только
  synthetic fixture без SPI.
- добавлен executable identification state machine над deterministic fake transport;
  каждый exchange failure, timeout 100 attempts, sequence drift и physical transport
  fail closed отклоняются до hardware I/O.
- добавлен allocation-free SD SPI wire framing: known CRC7 command frames, bounded
  R1/data-token polling, exact R3/R7 reads и CRC16 validation; board публикует
  contract с zero commands и disabled physical execution.
- одна explicit selected disposable microSD идентифицирована через guarded physical
  SPI 400 kHz в трёх read-only runs; CID/CSD/capacity стабильны, каждый cleanup
  освобождает Storage+RadioSpi, mount/data-block read/write/radio commands отсутствуют.
- ровно LBA0 прочитан одним bounded CMD17; сохранены только fingerprint и valid MBR
  geometry: FAT32-LBA partition type `0x0C`, first LBA 2 048 и 122 136 512 sectors;
  raw sector не сохранён.
- ровно partition boot sector, полученный из validated MBR, прочитан и подтвердил
  coherent FAT32 geometry: 512 B/sector, 64 sectors/cluster, root cluster 2 и total,
  совпадающий с partition; mount, directory и file reads не выполнялись.
- явно одобренная privacy policy `counts_hash_only` применена к одному derived FAT32
  root-directory sector; сохранены только counts типов entries и CRC32C, raw buffer
  обнулён, имена не retained, file data не читались.
- та же policy последовательно применена ко всему bounded root cluster; во втором
  sector найден end marker, поэтому получен complete metadata inventory 26 entries
  для текущего состояния карты без FAT-chain, names или file-content reads.
- ровно boot-declared FAT32 FSInfo sector прочитан; все три signatures и bounded
  free/next hints валидны, сохранены только technical counts/CRC32C, buffer обнулён,
  а static RAM уменьшена через один shared SD evidence workspace.
- один дополнительный exact first-FAT sector cross-check читает только FAT[0…2]:
  media `0xF8` совпадает, volume clean/no-error, root cluster 2 имеет EOC; FSInfo
  hints совместимы, FAT-chain/name/file data не читаются, оба raw buffers обнулены.
- добавлен guarded Arduino FAT backend общего `SessionStore`: один run на явно
  disposable card с exact CID создал только новый bounded scratch namespace,
  committed generations 1/A и 2/B с шестью file и шестью directory sync, затем
  пережил настоящий unmount/remount и read-only reopen generation 2/трёх observations.
- та же команда повторена с уже существующим run ID: `StorageGuard` отказал с
  `scratch_already_exists`, zero logical bytes written и без deletion; reset injection,
  power-cut и LittleFS parity были открыты на том evidence point.
- intermittent Arduino SD sector transport заменён guarded ESP-IDF SDSPI; один
  exact-CID run из 32 commits завершил 96 file и 96 directory barriers, дал
  p50/p95/p99 405 729/571 276/591 651 us и восстановил generation 32 до и после
  remount; exact retry отказал existing namespace с zero writes.
- реализован six-boundary logical-reset harness:
  host-tested wrapper `SessionStoreIo` останавливается только после успешной
  write или durability boundary; board arm/recovery commands требуют exact CID,
  уникальные bounded namespaces, software-reset reason, read-only reopen, allowed
  generation и неизменные hashes prior payload. Matrix runner отказывается без
  explicit acknowledgement `--execute-reset-matrix`.
- все шесть software-reset boundaries прошли на board-01/disposable SD:
  boundaries 1…4 восстановили generation 1, boundary 5 — allowed generation 1,
  а fully synced boundary 6 — generation 2; каждый read-only recovery сохранил
  prior hashes и записал/синхронизировал zero bytes. Boundary 4 выявил один
  transient immediate SD re-identification failure; bounded read-only retry и final
  six-namespace audit прошли.
- превышение RB-03 на 1 628 B static RAM закрыто без ослабления guardrail:
  map review удалил redundant physical-recovery `SurveySession` 4 672 B,
  переиспользовал существующий caller-owned validation workspace и измерил
  95 260 B static RAM; новый exact-CID boundary-6 run восстановил generation 2 с
  zero recovery writes.
- первый physical source измерен через explicit passive-only Wi-Fi adapter: 32/32
  scans приняли 414 normalized Observations с zero drop/reject и p99 encoded ingress
  546 B/s; heap вернулся к baseline, RF/storage leases очищены. Physical no-TX без
  RF instrument остаётся unverified.
- source сравнен с SD по RB-06: требуется 2 184 B/s, а текущий workload с fsync после
  каждого generation даёт 536 B/s. Следующий storage design обязан использовать
  bounded queueing и batching без ослабления atomic publication.
- fixed FIFO 64 observations и publish policy 2 KiB/5 s/Stop/safe-shutdown покрыты
  host tests; physical 64-observation workload даёт 9 068 encoded B/s, в 4,15 раза
  выше RB-06, и после 32 commits/remount открывает generation 32 без изменения
  atomic dual-head contract.
- real passive Wi-Fi, fixed FIFO, batch policy и guarded SessionStore соединены в
  одном board run: 29 observations из четырёх scans записаны без drop, latency trigger
  публикует generation 1, а remount/read-only reopen возвращает все 29; effective
  payload rate 6 921 B/s проходит RB-06 в 3,17×, combined lease 14→0.
- следующий board run принимает recovered generation в штатную Library вместо
  восстановления simulated fixture: 52 observations, FIFO high-water 18/64, zero
  drops, encoded payload 12 957 B/s; Home/List/Detail/Export показывают READY,
  PERSISTENT/REAL, generation 1/valid и PERSISTED YES, а serial artifact содержит
  `persistent=true`, `simulated=false`; Back возвращает lease mask 5→0.
- добавлены allocation-free `SurveyWorkflow` и `SessionCatalog`: первый задаёт
  Setup/Running/Committing/Result/Error, выполняет Stop & Commit только один раз,
  восстанавливает опубликованную generation до замены Library и сохраняет прежнюю
  Library при любой ошибке; второй fail-closed принимает latest valid generation из
  одного validated store root и явно отмечает fallback.
- первый продуктовый Survey-срез работает на board-01 от Setup через simulated
  three-observation source до Stop & Commit, открывает ту же generation 2 в Library
  и выдаёт bounded JSON export. `device-smoke` revision 2 автоматически проверяет
  idempotent Stop, десять real-TFT goldens, export record, resource cleanup и GPIO2
  LOW; RF и physical storage намеренно не задействованы.
- version 0.45 заменяет fixture только после boot admission enrolled exact card:
  AppCatalog запрашивает lease 15, explicit Select проверяет cached FSInfo capacity и
  fixed product root, выполняет credential-free passive scan, drain FIFO 64, а Right
  атомарно публикует следующую generation. Automatic board run принял 15/15 records
  с zero reject/drop, committed generation 2→3, cold boot read-only восстановил ту же
  Session 3/15, export persistent/non-simulated, final lease 0. Back из Running отдельно
  доказан без записи с retention generation 2; четыре TFT readback нашли и закрыли
  overflow реального списка.
- `SurveyPipeline` теперь отделяет source callback от Session через существующий
  fixed FIFO 64, считает received/forwarded/drop/depth/high-water, применяет Stop
  batch trigger и не допускает более 64 in-flight+forwarded observations. UI и
  diagnostic state показывают эти значения; host capacity case фиксирует 65-й
  record как drop, а board golden case показывает 3→3, high-water 3 и zero drop.
- добавлены `ProductStorePolicy` и `ProductSurveyAdmission`: boot catalog допускается
  только с exact enrolled fingerprint, существующим `/leshy/sessions/v1`, read-only
  driver и lease Storage+RadioSpi; initialize/commit дополнительно требуют explicit
  selection, writable driver и byte budget. Real Survey требует valid passive plan,
  writable commit permit и combined EspRf+Storage+RadioSpi lease; simulated/RAM
  fallback всегда false. Device-smoke проверяет отказ до hardware/radio/storage I/O.
- принят ADR-005 и реализован первый manifest-driven prerelease device-smoke:
  runner дважды прошил exact app candidate, после отдельного golden bootstrap
  прошёл cold boot→Home→Diagnostics→Back с real TFT RGB565 comparisons, zero pixel
  mismatch, owner/lease `none`/`0`, heap выше 128 KiB и GPIO2 LOW; независимый
  verifier проверяет bundle/candidate hashes и fail-closed отклоняет unsigned local
  result как самостоятельное release evidence.
- candidate 0.36 добавил полный firmware-reported ESP app ELF SHA-256; runner
  независимо извлекает тот же digest из app descriptor до flash и требует exact
  equality в cold-boot и повторном metrics record. Два промежуточных прогона
  fail-closed обнаружили truncated runtime digest и слишком малый bounded JSON
  envelope; исправленный physical run прошёл с тремя одинаковыми identity bindings.
- candidate 0.37 добавил allocation-free HIL session envelope: один random 128-bit
  run ID связывает candidate manifest, firmware begin/end, run и local result;
  firmware отказывает nested/malformed/identity-mismatch sessions. Runner сначала
  сохраняет candidate в bundle и прошивает именно эту immutable копию, поэтому
  verifier повторно проверяет self-contained evidence без внешнего build path.
- Исторический Ed25519 prototype через OpenSSL дал `release_eligible=true` на копии
  physical bundle, но product decision от 2026-08-17 отверг постоянный station key.
  Production trust перенесён в keyless GitHub OIDC/Sigstore attestation candidate и
  evidence archive; локальный signing code path удалён.
- найдено авторское upstream evidence причины ложного buzzer на GPIO2 и проверенный
  0.x LOW fix; clean 1.x теперь до console/display устанавливает OUTPUT LOW через
  отдельный BoardSafeOutputs, запрещает прямое управление из apps/drivers и публикует
  boot/runtime diagnostic state.

## S1 — приоритетная очередь

Недоступные платы или приборы ограничивают physical evidence, но не останавливают
следующий безопасный пункт документации или прототипирования.

1. Дополнить partial `HW-T01/T04/T07`: module marking, вторая v2 board и exact
   power-manager marking; отдельные GPS/PN532 assembly проверять только при наличии.
2. Выполнить manual `HW-T02/T03/T05/T08/T09/T10`; `HW-T06` запускать только после
   подтверждения отсутствия GPS/PN532 и с RF detector/logic analyzer.
3. Продолжить productization доказанного source→queue→store→Library/export path:
   UI/RAM slice с bounded FIFO и visible progress/drop/storage state автоматизирован;
   fail-closed real/persistent admission и точный product namespace уже закреплены;
   теперь реализовать adapter lifecycle, который удовлетворяет read-only boot
   recovery и explicit bounded commit, затем подключить к нему real passive source,
   общий pipeline и catalog той же persistent Session. Проверить reset-readiness retry при следующем natural
   transient. LittleFS требует отдельно доказанный disposable image, physical
   power-cut — controller.
4. Измерить power/shared-bus/no-TX stability при появлении приборов.
5. Обновить PRD/traceability по результатам измерений и только затем закрыть gate S1.

## Evidence на текущей базе

| ID | Проверка | Результат | Ограничение |
|---|---|---|---|
| E-DOC-001 | Все локальные Markdown links | pass, 2026-08-16 | проверяет навигацию, не содержание |
| E-DOC-002 | `docs/manifest.json` через `jq` | pass, 2026-08-16 | installer всё ещё устанавливает 0.x |
| E-TEST-001 | `tools/test.sh` | pass, 2026-08-16 | host contracts; physical storage/power failures требуют HIL |
| E-BUILD-001 | `tools/build.sh`, ESP32-S3 | pass: RAM 98,748 B (30.1%), flash 1,995,896 B (59.7%) | это сборка 0.x + prototype, не target 1.x |
| E-HW-DESIGN-001 | v2 main/shield schematic + BOM + original pin map + vendor datasheets | hardware envelope создан, 2026-08-16 | design evidence; не заменяет `HW-T01…HW-T11` |
| E-BUILD-002 | `tools/build_hil_probe.sh`, probe 0.1.1 | pass: RAM 23,872 B (7.3%), flash 354,548 B (10.6%); board-01 flash hash verified | evidence tool, не product target 1.x |
| E-TEST-002 | HIL probe logic tests + static no-TX guard | pass, 2026-08-16 | физическую тишину подтверждает только HW-T06 detector trace |
| E-HIL-001 | board-01 HW-T01 runtime | partial: ESP32-S3 rev 0.2, flash 16 MB Quad, PSRAM 0 | нет module photo и второй платы |
| E-HIL-002 | board-01 HW-T04 read-only I²C | partial/pass: `0x20`, `0x75`, writes 0 | exact IP5306 variant не установлен |
| E-HIL-003 | board-01 HW-T07 GPS RX-only 10 s | inconclusive: 0 bytes/NMEA | отсутствие GPS не доказано; PN532 не проверен |
| E-HIL-004 | board-01 HW-T11 | pass: оба USB path, reset, download, console, полный 16 MB restore hash-verified и визуально подтверждённый исходный UI 0.x | CP2102 460800 unstable; verified ceiling 230400 |
| E-HIL-005 | board-01 guarded HW-T06 | partial: NRF #1/#2 detected; CC PARTNUM `0x00`, VERSION `0x14`; CE-high/TX commands 0 | у оператора нет logic/RF detector; NRF #3 gated HW-T08 |
| E-BUDGET-001 | build + board-01 ledger в `RESOURCE_BUDGETS` | partial: physical flash/PSRAM, slots, clean/probe/legacy/interactive sizes, runtime heap, interactive-ready, upload/recovery | открыты product-home boot, storage, power и shared-bus measurements |
| E-RISK-001 | review `RISK_REGISTER` | R-001…R-017 имеют treatment, owner, closure evidence и gate controls | risks остаются open до появления named evidence |
| E-ADR-001 | ADR-001…ADR-004 + traceability review | accepted: toolchain, resource policy, storage schema/atomicity и Action boundary | implementation/verification начинаются в указанных gates S2+ |
| E-BUILD-003 | `tools/build_1x_measure.sh`, clean target 0.1.0-measure | pass: RAM 22 576 B (6,9%), flash 320 952 B (7,7% app slot 4 MiB); без dependencies/legacy sources | только bootstrap; нет display/input/storage/source |
| E-HIL-006 | clean target на board-01/native USB | profile match; runtime-ready 7 224 µs; heap total/free/min 389 680/349 660/344 512 B; полный restore 0.x hash-verified | runtime milestone не является interactive UI boot evidence |
| E-BUILD-004 | `0.2.0-interactive-measure` | pass: RAM 24 460 B, flash 391 719 B; app/factory 392 128/457 664 B | только probe screen; без storage/source |
| E-HIL-007 | interactive target на board-01 | display видим; PCF8574 detected; idle `0xFF` и пять отдельных active-low inputs; interactive-ready 0,363 с; heap free/min 343 420/338 272 B | semantic key labels наследуют известную карту v2; не final product UI |
| E-BUILD-005 | `0.3.0-ui-automation-measure` | pass: RAM 26 388 B, flash 394 843 B; app/factory 395 248/460 784 B; все host/isolation checks проходят | diagnostic shell, не user firmware |
| E-HIL-008 | board-01 UI action/capture trace | serial и physical input используют один `UiController`; stateful navigation получила 240×320/153 600 B TFT GRAM; post-capture revision совпала; passive serial reconnect сохранил state без reset | подтверждает transport/probe pages, но не workflow UI или физическую яркость |
| E-STORAGE-001 | host fault matrix ADR-003 `AtomicHead` | pass: fixed 24 B encoding; CRC32C/bounds; 192 one-bit corruptions; missing/mismatched manifest; conflict/rollover; failures на шести write/sync boundaries сохраняют prior generation | пока нет filesystem backend, throughput, reset или physical power-cut evidence |
| E-BUILD-006 | `0.4.0-storage-contract-measure` | pass: RAM 26 388 B, flash 395 115 B; app/factory 395 520/461 056 B | atomic head host-tested; filesystem backend отсутствует |
| E-HIL-009 | board-01 storage contract report + UI capture | pass: head 24 B/schema 1/six boundaries/`write_enabled=false`; interactive-ready 0,369 с; TFT/post-state revision совпадают | read-only; не проверяет media, throughput, reset или power-cut |
| E-STORAGE-002 | negative matrix `StorageGuard` | pass: обязательны exact fingerprint + explicit disposable + safe new run namespace + bounded size/reserve; любое invalid condition отклоняет permit | только policy; media не mounted и не записывался |
| E-BUILD-007 | `0.5.0-storage-guard-measure` | pass: RAM 26 388 B, flash 395 627 B; app/factory 396 032/461 568 B | filesystem backend отсутствует |
| E-HIL-010 | board-01 guard policy + UI capture | pass: scratch `/leshy-hil/`, exact/disposable/refuse-existing; mount/format/write false; interactive-ready 0,369 с | read-only policy evidence |
| E-CAPABILITY-001 | host tests `AppCatalog` + dynamic `UiController` | pass: available projection, disabled reasons, blocked launch, enabled launch/Back | только три S2 entries; product workflow отсутствует |
| E-BUILD-008 | `0.6.0-capability-home-measure` | pass: RAM 26 436 B, flash 396 243 B; app/factory 396 640/462 176 B | measurement target |
| E-HIL-011 | board-01 capability-home scenarios | pass: Diagnostics ready/open/back; Survey/Library disabled с reasons; actual TFT + revision traces; interactive-ready 0,373 с | не проверяет full apps или external cold-boot timing |
| E-RUNTIME-001 | host tests `AppRuntime` + `ResourceBroker` | pass: all-or-none acquisition, busy/disabled/invalid rejection, idempotent launch, stop/release | single-threaded S2 slice; physical shared-bus arbitration остаётся открытым |
| E-BUILD-009 | `0.7.0-runtime-leases-measure` | pass: RAM 26 468 B, flash 396 887 B; app/factory 397 296/462 832 B | measurement target; Diagnostics всё ещё shell |
| E-HIL-012 | runtime leases board-01 + 1 000 open/Back cycles | pass: disabled app не получает lease; Diagnostics start/stop получает/освобождает display; leaked leases и изменение heap отсутствуют; p99/max Back/release 98,801/99,345 мс | host acknowledgement timing, не external cold-boot или RF/storage bus evidence |
| E-SURVEY-001 | tests SurveySession/Observation/Wi-Fi/controller | pass: passive-only validation, normalization/bounds, monotonic sequence, idempotent stop, capacity 64/overflow и golden trace List→Detail→Back | только simulated contract; нет Wi-Fi driver, rendered product UI или persisted Session |
| E-BUILD-010 | `0.8.0-survey-contract-measure` | pass: RAM 26 468 B, flash 397 571 B; app/factory 397 968/463 504 B; clean-target guard запрещает Wi-Fi API | нет running source или rendered Survey workflow |
| E-HIL-013 | no-RF Survey contract на board-01 | pass: текущий hash flashed; passive-only/plan valid; active probe, directed SSID, driver start и radio touch false; capacity 64; Home TFT/state captured | только contract evidence; physical RF silence всё ещё требует detector |
| E-BUILD-011 | `0.9.0-survey-golden-ui-measure` | pass: RAM 31 156 B, flash 405 223 B; app/factory 405 632/471 168 B | in-memory golden data; нет hardware source/storage |
| E-HIL-014 | golden Survey UI на board-01 | pass: simulated Home→List→Detail→Back сохраняет running/lease; explicit Stop и затем Home освобождают owner/lease; final TFT review чистый | нет persistence/reopen/export и physical RF evidence |
| E-STORAGE-003 | host golden/fault matrix `SessionCodec` | pass: canonical CBOR schema 1; framed records + footer CRC32C; exact golden manifest/segment 41/155 B; reopen + deterministic JSON; отклонены каждый bit manifest, все truncations segment и по одному bit в каждом segment byte | нет filesystem backend или physical media |
| E-BUILD-012 | `0.10.0-session-codec-measure` | pass: RAM 48 628 B, flash 416 175 B; app/factory 416 576/482 112 B | bounded in-memory codec workspace; нет filesystem backend |
| E-HIL-015 | Session codec round-trip на board-01 | pass: explicit Stop → encode → head select → reopen 3 observations → JSON; storage/radio false; final Home owner none/lease 0; heap total/free/min 362 088/319 252/314 104 B | in-memory self-check, не evidence persistence/reset/power-cut |
| E-STORAGE-004 | guarded host real-filesystem commit fixture | pass: valid exact-fingerprint/1 MiB permit; семь isolated real-file scenarios; 30 file + 16 directory fsync calls; шесть failures восстанавливают generation 1, complete — generation 2; обе открывают 3 observations; prior bytes unchanged; fixture cleaned | modeled call failures, не process kill, ESP reset, removable media или power cut |
| E-STORAGE-005 | bounded `SessionStore` + host recovery после `SIGKILL` | pass: automatic empty→generation 1/A→generation 2/B, uint32 rollover, corrupt-new fallback, corrupt-store refusal; шесть children убиты после разных boundaries; recovery с files возвращает generation 1 до head и generation 2 после head, всегда открывает 3 observations и сохраняет prior bytes | process death на host, не kernel crash, ESP reset, removable media или power cut |
| E-BUILD-013 | `0.11.0-session-store-measure` | pass: RAM 74 148 B, flash 458 847 B; app/factory 459 248/524 784 B | два maximum-size RAM generations только diagnostic; persistent backend отсутствует |
| E-HIL-016 | bounded RAM SessionStore на board-01 | pass: stopped Session auto-commits 1/A→2/B; generation 2 открывает 3 observations; corrupt-new `invalid_payload` делает fallback на generation 1/3 observations; modeled шесть file + шесть directory sync calls; radio/physical storage false; Home owner none/lease 0 | RAM-backed target orchestration, не evidence persistence/reset/power-cut |
| E-LIBRARY-001 | host tests bounded offline Library controller | pass: admission stopped/valid, rejection running/invalid/duplicate, capacity 4, List→Detail→Back, provenance; reopen декодирует в caller-owned workspace | только RAM/simulated data; нет export transport или physical persistence |
| E-BUILD-014 | `0.12.0-library-offline-measure` | pass: RAM 79 132 B, flash 465 563 B; app/factory 465 968/531 504 B | bounded RAM Library; persistent backend отсутствует |
| E-HIL-017 | offline Library workflow на board-01 | pass: Home→List→Detail→Back→Home; generation 1/3 observations/valid; виден volatile/RF-off provenance; удерживается только UI lease; `radio_touched=false`; heap total/free/min 331 584/288 748/283 600 B | simulated RAM fixture, не evidence persistence/reset/power-cut |
| E-EXPORT-001 | host tests bounded Library export | pass: explicit transition Export Ready, exact deterministic JSON, provenance, refusal short buffer/missing Session, трёхуровневый Back | только serial NDJSON; нет file или companion delivery |
| E-BUILD-015 | `0.13.0-library-export-measure` | pass: RAM 79 772 B, flash 467 247 B; app/factory 467 648/533 184 B | export — bounded serial output, не persistence |
| E-HIL-018 | explicit Library export на board-01 | pass: Detail→Right→Export Ready; TFT показывает JSON/serial/not persisted/RF off; valid artifact содержит generation/integrity/session; Export→Detail→List→Home освобождает UI lease; command на Home возвращает `not_requested`; heap total/free/min 330 944/288 108/282 960 B | нет physical media или companion transport |
| E-STORAGE-006 | tests read-only media-adapter/discovery contract | pass: non-authoritative detect не может заявить present/absent; detected требует RO mount/filesystem/fingerprint/capacity; invalid metadata/mount state/write-enabled fail closed; bounded JSON | нет SD protocol или filesystem operation |
| E-BUILD-016 | `0.14.0-storage-discovery-measure` | pass: RAM 80 588 B, flash 469 199 B; app/factory 469 600/535 136 B | только GPIO sample + contract; mount отсутствует |
| E-HIL-019 | SD discovery на board-01 | pass: GPIO38 прочитан как 0 без перенастройки; validation valid, но status `unknown`, detect non-authoritative; mount false, fingerprint/filesystem/capacity unknown, write false, guard required; Home owner none/lease 0; heap total/free/min 330 128/287 292/282 144 B | не доказывает polarity, наличие карты, FAT, CID, shared SPI или persistence |
| E-STORAGE-007 | tests read-only mount authorization | pass: invalid discovery/slot/repeat/selection/driver/format/resources/conflict отклоняются; только complete request permitted; required mask Storage+RadioSpi | только authorization; нет SD command или mount |
| E-BUILD-017 | `0.15.0-mount-policy-measure` | pass: RAM 80 588 B, flash 470 215 B; app/factory 470 624/536 160 B | только policy report; driver execution отсутствует |
| E-HIL-020 | mount policy на board-01 | pass: actual `explicit_target_required`; hypothetical selection `driver_not_read_only`; Arduino SDFS RO guarantee false; required/owned resources 12/0; format/mount/execution/write false; Home lease 0; heap total/free/min 330 128/287 292/282 144 B | stock driver rejected; нет SD/SPI/filesystem evidence |
| E-STORAGE-008 | tests SD identification plan | pass: exact order CMD0/8/55/41/58/10/9, init bound 1…100; отклонены eleven mutating command classes, sequence drift и execution-enabled; invalid plan не форматирует evidence | только plan; нет response parser или SPI transport |
| E-BUILD-018 | `0.16.0-sd-ro-protocol-measure` | pass: RAM 81 100 B, flash 471 099 B; app/factory 471 504/537 040 B | только protocol contract; execution disabled |
| E-HIL-021 | SD RO protocol report на board-01 | pass: identification-only plan valid; CID/CSD true, data reads/write/erase/format false; max init 100; execution false; mount permit и disposable card required; Home lease 0; heap total/free/min 329 616/286 780/281 632 B | нет SD command, response, CID/CSD или bus evidence |
| E-STORAGE-009 | fault matrix parser SD transcript | pass: validation response/echo/init/OCR/CID/CSD/CSD-v2/capacity; CRC16 check vector; отклонены все 256 one-bit mutations CID/CSD | только synthetic transcript; нет command transport или physical SPI |
| E-BUILD-019 | `0.17.0-sd-parser-measure` | pass: RAM 81 804 B, flash 472 987 B; app/factory 473 392/538 928 B | только parser fixture; physical SPI false, commands 0 |
| E-HIL-022 | SD parser fixture на board-01 | pass: synthetic high-capacity identity 16 MiB, init 3, CID/CSD CRC valid; fake transport, commands 0, physical SPI/write/radio false; Home lease 0; heap total/free/min 328 912/286 076/280 928 B | interpretation transcript, не physical identity или framing |
| E-STORAGE-010 | tests fake SD transport state machine | pass: exact command/argument sequence, 11 exchange-boundary failures, timeout 100 attempts/202 exchanges, sequence violation, invalid plan zero calls, physical transport zero calls | только deterministic fake; нет bus acquisition или SPI framing |
| E-BUILD-020 | `0.18.0-sd-transport-measure` | pass: RAM 82 316 B, flash 474 959 B; app/factory 475 360/540 896 B | только fake transport; physical adapter rejected |
| E-HIL-023 | fake SD transport на board-01 | pass: 11/11 exchanges, init 3, parsed 16 MiB; fake transport, physical SPI/write/radio false; Home owner none/lease 0; heap total/free/min 328 400/285 564/280 416 B | execution state machine, не physical SD/SPI/no-TX evidence |
| E-STORAGE-011 | tests SD SPI wire codec | pass: known CMD0/CMD8 CRC7 frames; exact allowed arguments; eleven mutating classes refused; bounds R1 1…16 и data token 1…8; timeout/invalid/truncated/CRC16 faults rejected | только byte fixtures; нет CS, clocks, bus или physical transport |
| E-BUILD-021 | `0.19.0-sd-wire-measure` | pass: RAM 82 828 B, flash 476 051 B; app/factory 476 448/541 984 B | только wire contract; execution disabled, commands 0 |
| E-HIL-024 | SD wire report на board-01 | pass: known CMD0/CMD8 frames, CRC7/CRC16 и poll bounds; execution/physical SPI/commands/write/radio false; Home owner none/lease 0; heap total/free/min 327 888/285 052/279 904 B | framing contract, не physical SD identity/shared-bus/no-TX evidence |
| E-STORAGE-012 | safety tests physical SD permit/adapter | pass: physical transport получает zero calls без selection, identification-only contract, exact ownership Storage+RadioSpi и no conflict; GPIO изолирован в одном checked adapter без filesystem/write APIs | software/static evidence не доказывает RF silence или electrical timing |
| E-BUILD-022 | `0.20.0-sd-physical-id-measure` | pass: RAM 84 300 B, flash 479 659 B; app/factory 480 064/545 600 B | только guarded physical identification |
| E-HIL-025 | physical SD identity на board-01 | pass: три read-only 400 kHz runs возвращают stable CID `FE343253440000002000000055019CB7`, CSD и capacity 62 534 975 488 B; cold/warm init 8/2/2; resource 12→0, GPIO21 stable HIGH, cleanup complete; no mount/data block/write/radio command; Home lease 0; heap total/free/min 326 416/283 944/278 668 B | одна disposable card/board; нет logic/RF trace, filesystem, data-block, radio recovery, endurance или persistence evidence |
| E-STORAGE-013 | tests bounded CMD17/LBA0 authorization, wire и parser | pass: разрешён только high-capacity LBA0/count 1 с exact selection/read-only/ownership Storage+RadioSpi; покрыты 512-byte CRC16, truncation/corruption, MBR/GPT/FAT/exFAT hints и partition bounds | parser сохраняет только structural metadata/CRC32C; filesystem traversal отсутствует |
| E-BUILD-023 | `0.21.0-sd-sector0-measure` | pass: RAM 86 764 B, flash 483 319 B; app/factory 483 728/549 264 B | только guarded single-sector metadata read |
| E-HIL-026 | physical SD LBA0 на board-01 | pass: ровно один CMD17 читает valid MBR с partition type `0x0C`, first LBA 2 048, length 122 136 512 sectors; CRC32C 1 784 529 910 и wire CRC16 5 391; resource 12→0, cleanup complete; raw sector/mount/filesystem API/write/radio false; heap total/free/min 323 952/281 480/276 204 B | только partition map; нет boot sector, FAT, directory, allocation или file evidence |
| E-STORAGE-014 | tests partition-boot authorization и bounded FAT/exFAT parser | pass: boot LBA обязан совпадать с first partition LBA из valid LBA0; покрыты exact count 1, signature, capacity, FAT32/exFAT geometry, label sanitization и invalid forms | только metadata parser; нет mount, FAT traversal, directory или file read |
| E-BUILD-024 | `0.22.0-sd-boot-inspect-measure` | pass: RAM 90 340 B, flash 487 071 B; app/factory 487 472/553 008 B | ровно LBA0 плюс metadata его derived boot sector |
| E-HIL-027 | physical FAT32 boot sector на board-01 | pass: два metadata blocks подтверждают FAT32, 512 B/sector, 64 sectors/cluster, 14 906 sectors/FAT, root cluster 2 и 122 136 512 total sectors; boot CRC32C/wire CRC16 3 945 425 518/9 849; resource 12→0, cleanup complete; raw sectors/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 320 376/277 904/272 628 B | одна card/board; directory entries, allocation chains, files, instrumented RF silence, radio recovery, endurance и persistence открыты |
| E-STORAGE-015 | tests root-directory LBA permit и metadata-only privacy | pass: разрешён только count 1 на FAT32 root LBA из valid MBR/boot geometry; overflow/bounds/resource faults отклоняются; fixtures с short/LFN names выводят только counts/CRC32C без имён | one-sector parser временно видит raw bytes в RAM, затем board buffer обнуляется; нет persistence или content semantics |
| E-BUILD-025 | `0.23.0-sd-root-metadata-measure` | pass: RAM 95 620 B, flash 492 119 B; app/factory 492 528/558 064 B | один root-directory sector под policy `counts_hash_only` |
| E-HIL-028 | physical root-directory sector на board-01 | pass: derived LBA 32 768; ровно три total blocks; первый root sector содержит 16 active slots (8 LFN, 2 directory, 5 file, 1 volume label), CRC32C/wire CRC16 1 846 458 358/834; names/end marker не retained, buffer zeroed, resource 12→0, cleanup complete; mount/filesystem API/file data/write/radio false; heap total/free/min 315 096/272 516/267 208 B | только один sector; end marker отсутствует, поэтому inventory на этом evidence point неполный |
| E-STORAGE-016 | tests bounded sequential root-cluster authorization/aggregation | pass: каждый offset обязан быть sequential и внутри sectors/cluster; aggregate CRC32C/counts останавливаются на первом end marker, append-after-end rejected, имена никогда не форматируются | только первый cluster; FAT-chain traversal намеренно disabled |
| E-BUILD-026 | `0.24.0-sd-root-cluster-measure` | pass: RAM 95 620 B, flash 492 743 B; app/factory 493 152/558 688 B | bounded metadata-only root-cluster scan |
| E-HIL-029 | physical FAT32 root cluster на board-01 | pass: два из max 64 root sectors достигают end marker; examined 29 slots, active/deleted 26/2, из них 12 LFN, 6 directory, 7 file, 1 volume-label, invalid 0; aggregate CRC32C 1 849 301 523; четыре total blocks, resource 12→0, cleanup complete; names/raw/file data/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 315 096/272 516/267 208 B | complete root metadata только для текущего card state; file/FAT chains, free space, instrumented RF silence, radio recovery, endurance и persistence открыты |
| E-STORAGE-017 | tests boot-declared FAT32 FSInfo permit/parser | pass: разрешён только exact partition LBA + nonzero in-reserved FSInfo offset/count 1; покрыты lead/structure/trail signatures, unknown hints, cluster bounds, CRC32C и malformed forms | FSInfo values — hints; нет FAT allocation scan или VFS |
| E-BUILD-027 | `0.25.0-sd-fsinfo-measure` | pass: RAM 90 004 B, flash 493 799 B; app/factory 494 208/559 744 B | shared SD evidence workspace плюс один technical FSInfo sector |
| E-HIL-030 | physical FAT32 FSInfo на board-01 | pass: declared sector 1/LBA 2 049 имеет valid signatures и hints: 1 907 095 free из 1 907 903 data clusters, next-free 888, CRC32C/wire CRC16 1 661 032 487/49 708; ровно три blocks, buffer zeroed, resource 12→0, cleanup complete; names/file data/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 320 712/278 132/272 824 B | один card state; hints не cross-checked с FAT, нет instrumented RF silence, radio recovery, endurance или persistence evidence |
| E-DOC-003 | product-reviewed paired scope/UX/demo contracts | pass: `CAP-001…047`, `PR-001…019`, `UX-01…08`, `UX-S01…S28`, `CRV-01…06`, `DEMO-S2…S8` совпадают EN/RU; links/status discipline проходят `check_docs.py` | PRD остаётся draft до полного technical baseline gate; visual baseline UX-03…07 создаётся в S2 |
| E-BUZZER-001 | upstream issue #117 + 0.x commit `04fd290` + clean-target static/host checks | pass: GPIO2 active HIGH, проверенный fix — boot hold LOW; apps/drivers не могут напрямую вызвать `pinMode/digitalWrite/tone/ledc` для buzzer | software evidence; ADC/electrical coupling остаётся HW-T09 |
| E-BUILD-028 | `0.26.0-buzzer-safe-measure` | pass: RAM 90 004 B, flash 494 507 B; factory 560 448 B, SHA-256 `50d4510f…c7158f9` | measurement image; sound service намеренно отсутствует |
| E-HIL-031 | buzzer-safe boot/runtime + TFT на board-01 | pass: GPIO2 configured OUTPUT LOW до console/display; boot и 4/4 final runtime samples за 90 с дают `buzzer_inactive=true`; interactive ready 393 871 µs, Home capture чистый, lease 0 | pad-level software evidence без microphone/scope; физическая тишина требует audible observation, долгий endurance остаётся S4/S8 |
| E-STORAGE-018 | tests exact first-FAT-sector permit и FAT[0…2]/FSInfo cross-check parser | pass: разрешён только first FAT LBA из valid MBR/boot geometry и count 1; media descriptor, FAT[1] clean/error polarity, root free/data/self/reserved/bad/EOC/out-of-range и incompatible FSInfo hints покрыты | root cluster должен быть 2 для этого bounded slice; ни одна chain не follow |
| E-BUILD-029 | `0.27.0-sd-fat-reserved-measure` | pass: RAM 90 004 B, flash 500 007 B; app/factory 500 416/565 952 B, SHA-256 `a934e5c2…70e27524` | один дополнительный FAT sector; parser ограничен тремя entries |
| E-HIL-032 | physical FAT32 reserved/root cross-check на board-01 | pass: 4/4 blocks; first FAT LBA 2 956; FAT[0] media `0xF8` valid, FAT[1] clean/no-hard-error, FAT[2] root EOC; FSInfo free/next hints compatible; buffers zeroed, resource 12→0, cleanup complete; names/file data/chain/mount/write/radio false; Home lease 0, GPIO2 LOW; heap total/free/min 320 712/278 240/272 964 B | только минимальная проверка трёх entries текущего card state, не полный allocation recount/VFS/persistence; нет instrumented RF silence |
| E-STORAGE-019 | guarded Arduino FAT adapter `SessionStoreIo` и clean-target checks | pass: boot не mount/write; physical invocation требует exact CID, explicit disposable selection, новый bounded run ID, permit 64 KiB, lease Storage+RadioSpi, format false, confinement path, verified directory creation, file/directory sync и refuse-existing semantics | FatFs `f_sync` — durability boundary adapter; host/static evidence само по себе не доказывает reset или power-cut |
| E-BUILD-030 | `0.28.0-sd-session-store-measure` | pass: RAM 94 996 B, flash 572 655 B; app/factory 573 056/638 592 B, factory SHA-256 `d6808679…ac726ca7` | measurement image содержит explicit guarded writable HIL command, не product auto-mount policy |
| E-HIL-033 | guarded physical FAT SessionStore на board-01 | pass: exact-CID permit; новый `/leshy-hil/s1-session-store-20260816-d`; generations 1/A и 2/B committed за 165 474/184 572 us с 6 file + 6 directory sync; настоящий unmount/remount/read-only reopen возвращает generation 2/3 observations; 440 logical B внутри limit 65 536 B; resource 12→0, cleanup complete, без format/delete/read user names/data/radio TX; точный retry отказывает existing scratch и пишет 0 B; Home lease 0, GPIO2 LOW; heap total/free/min 315 720/272 648/237 716 B | один normal-remount card run, не evidence reset-boundary, throughput distribution, power-cut, endurance, user workflow или LittleFS |
| E-STORAGE-020 | guarded direct-FatFs `SessionStoreIo`, ESP-IDF SDSPI transport, timing summary и clean-target checks | pass: caller-owned FatFs workspace публикует exact open/write/sync/close `FRESULT`; format false; SPI2 exclusive; 32 samples используют physical guard 4 MiB и fixed nearest-rank p50/p95/p99; stack allocation и opaque Arduino sector failures устранены | implementation/static evidence; power-cut, endurance, source-rate comparison и LittleFS parity остаются physical work |
| E-BUILD-031 | `0.29.0-sd-session-throughput-measure` | pass: RAM 99 932 B, flash 615 159 B; app/factory 615 568/681 104 B, factory SHA-256 `fe30f079…b1d649` | static RAM превышала временный RB-03 на 1 628 B; review закрыт E-BUILD-033; explicit writable HIL image, не product auto-mount |
| E-HIL-034 | guarded SD SessionStore throughput на board-01 | pass: ESP-IDF SDSPI на actual 4 MHz; exact CID; новый `/leshy-hil/s1-throughput-20260816-n`; 32/32 commits, 96+96 barriers, min/p50/p95/p99/max 166 348/405 729/571 276/591 651/591 651 us; generation 32 и 3 observations recovered до и после remount; 7 040 logical B, physical delta 2 195 456 B внутри guard 4 MiB; exact retry пишет 0 B; resources 12→0, Home lease 0, GPIO2 LOW; heap total/free/min 309 504/266 460/233 464 B | одна card/run и SessionStore workload; этот run не injected reset, software reset позже покрыт E-HIL-035; нет power-cut/endurance, source-rate comparison, product workflow, shared-bus cycling или LittleFS evidence |
| E-STORAGE-021 | six-boundary `SessionStoreBoundaryIo`, exact existing-scratch read permit, guarded board arm/recovery commands и matrix runner | pass: host tests останавливаются после каждой успешной payload/manifest/head write или sync boundary; write arm требует exact CID/new run ID/guard 64 KiB; recovery требует exact CID/existing namespace и публикует zero-write read-only IO, software-reset reason, allowed generation, размеры+CRC32C prior manifest/segment, cleanup и exact `FRESULT`; host runner требует `--execute-reset-matrix`, checkpoints каждой completed boundary и делает не более трёх retry только для exact zero-write readiness signature `missing_media`; follow-up read-only policy audit прошёл все шесть namespaces с первой попытки | implementation плюс physical reset evidence E-HIL-035; retry branch ждёт natural transient exercise; `esp_restart` не является power-cut evidence |
| E-BUILD-032 | `0.30.0-sd-session-reset-measure` | pass: RAM 99 932 B, flash 626 155 B; app/factory 626 560/692 096 B, factory SHA-256 `8b15ae09…77fa83b` | +10 996 B linked flash и zero static-RAM delta относительно 0.29; guarded reset commands diagnostic, а не product recovery policy |
| E-HIL-035 | guarded six-boundary SD software-reset matrix на board-01 | pass: exact CID и шесть новых `/leshy-hil/s1-reset-20260816-r-b1…b6` namespaces; recovered generations 1/1/1/1/1/2 соответствуют boundary oracle; все reopen 3 observations и сохраняют segment 155 B/CRC32C 1 782 718 116 плюс manifest 41 B/CRC32C 1 687 843 120; каждый recovery пишет/синхронизирует 0 B, возвращает `FR_OK`, resources 12→0, cleanup complete; postflight Home lease 0, GPIO2 LOW, heap total/free/min 309 504/266 676/233 656 B; read-only audit hardened runner SHA-256 `7806a327…157f4` повторил все шесть с первой попытки | одна card/board/software-reset matrix; boundary 4 изначально потребовал one read-only retry после transient immediate `missing_media`; retry branch host-tested, но не был естественно повторно вызван; нет physical power-cut, endurance, LittleFS, source-rate или shared-bus evidence |
| E-BUILD-033 | `0.31.0-sd-session-ram-review` | pass: RAM 95 260 B, flash 621 479 B; app/factory 621 888/687 424 B, factory SHA-256 `2f6999cf…2774d3` | map-driven удаление одного redundant `SurveySession` 4 672 B; 3 044 B static-RAM headroom ниже RB-03 без изменения guardrail |
| E-HIL-036 | shared recovery workspace + guarded boundary 6 на board-01 | pass: exact 0.31 preflight heap total/free/min 314 176/271 704/266 428 B; новый `/leshy-hil/s1-ram-review-20260816-a-b6` достигает `sync_head`, software-reset recovery выбирает required generation 2/3 observations, сохраняет prior hashes, пишет/синхронизирует 0 B, возвращает `FR_OK`, resources 12→0, cleanup complete с первой попытки; postflight Home lease 0 и GPIO2 LOW; evidence SHA-256 `d42044a7…282a3` | одна board/card/boundary; transient HIL minimum 238 460 B не является interactive-boot значением RB-03; нет endurance, source, LittleFS или power-cut evidence |
| E-SURVEY-002 | explicit passive Wi-Fi board adapter, ingress rate summary, privacy scrubbing и safety guard | pass: host tests покрывают bounded nearest-rank rates и scrubbing Session reset; static checks требуют passive scan/null filters/RAM config/NVS off и запрещают active scan/connect/set-config/raw-TX/AP/promiscuous APIs вне adapter; command требует `passive-only` и ownership EspRf | software path имеет zero application TX APIs, но physical no-TX нельзя verify без RF instrumentation |
| E-BUILD-034 | `0.32.0-wifi-passive-ingress-measure` | pass: RAM 113 600 B, flash 1 016 688 B; app/factory 1 017 088/1 082 624 B, factory SHA-256 `5795c798…2c868` | Wi-Fi source slice добавляет 18 340 B static RAM и 395 209 B linked flash относительно 0.31; combined S3 diagnostic image превышает RB-03 и оценивается по RB-04 |
| E-HIL-037 | passive Wi-Fi ingress и RB-06 comparison на board-01 | pass: 32/32 passive scans за 54 419 229 us report/read 414/414 AP records, accept/reject/drop 414/0/0, encode 20 268 B; min/p50/p95/p99/max 214/370/504/546/546 B/s; heap before/after/min 244 664/244 664/186 376 B; resources 2→0, cleanup complete, Home unchanged, GPIO2 LOW, storage writes 0, identifiers emitted/retained false; evidence SHA-256 `c81da232…31422c` | RB-06 требует 2 184 B/s, текущий SD workload 536 B/s и не проходит margin примерно в 4,1×; одна environment, нет instrumented RF no-TX, product queue/workflow, 8 h endurance, BLE/NRF/CC ingress или concurrent storage evidence |
| E-STORAGE-022 | fixed `ObservationQueue`, batch policy и rate-bound tests | pass: host tests покрывают capacity 64, FIFO wrap-around, drop/high-water/push/pop counters, scrubbing reset, policy 2 048 B/5 s/capacity/Stop/safe-shutdown, trigger precedence и overflow-safe minimum batch; measured inputs дают minimum 1 293 B | implementation contract; real source→queue→store integration остаётся следующим slice |
| E-BUILD-035 | `0.33.0-sd-session-batch-throughput-measure` | pass: RAM 114 200 B, flash 1 018 192 B; app/factory 1 018 592/1 084 128 B, factory SHA-256 `27fbd7e1…3739e1` | +600 B static RAM и +1 504 B linked flash относительно combined 0.32 image; оценивается по RB-04 |
| E-HIL-038 | guarded batched SessionStore throughput на board-01 | pass: exact CID/new `/leshy-hil/s1-batch-throughput-20260816-a`; 32/32 commits по 64 observations/4 609 B, 96+96 barriers; min/p50/p95/p99/max 201 234/518 527/652 362/664 421/664 421 us; generation 32/64 observations recovered до и после remount; encoded payload 9 068 B/s против required 2 184 B/s, target pass 4,15×; 149 568 logical B; `FR_OK`, resources 12→0, cleanup complete, GPIO2 LOW, fixture restored; evidence SHA-256 `372d2d34…135f4` | synthetic fixed batch доказывает storage service rate, но ещё не concurrent/real Wi-Fi queue, product workflow, power-cut, LittleFS или endurance evidence |
| E-SURVEY-003 | guarded passive Wi-Fi→FIFO→SessionStore integration path | pass: exact-CID command получает combined EspRf+Storage+RadioSpi lease, passive scanner пишет normalized observations только в fixed FIFO, policy выбирает size/latency/capacity/Stop boundary, stopped snapshot atomарно committed и reopened после remount; output публикует только counts/rates, identifiers остаются в isolated scratch | diagnostic command, не product UI; physical no-TX не instrumented |
| E-BUILD-036 | `0.34.0-wifi-passive-persist-measure` | pass: RAM 119 656 B, flash 1 027 804 B; app/factory 1 028 208/1 093 744 B, factory SHA-256 `308a9869…7c3818` | real fixed ring +4 672 B и evidence buffer/code; combined S3 image оценивается по RB-04 |
| E-HIL-039 | real passive Wi-Fi→persistent SessionStore на board-01 | pass: exact CID/new `/leshy-hil/s3-wifi-persist-20260816-a`; 4 scans read/accept/reject/drop 29/29/0/0; FIFO high-water 9/64, push/pop/drop 29/29/0; latency trigger; generation 1 с 29 observations/1 334 B committed за 192 729 us и reopened до/после remount; encoded payload 6 921 B/s против required 2 184 B/s, pass 3,17×; `FR_OK`, resources 14→0, cleanup complete, Home lease 0, GPIO2 LOW; evidence SHA-256 `1dcb2e44…6cd77f` | первый real-source persistent technical path; product Start/Stop/Library/reboot/export, instrumented no-TX, power-cut, LittleFS и endurance остаются open |
| E-LIBRARY-002 | persistent Session admission contracts | pass: runtime capability `library.persistent_session` имеет приоритет над simulated fixture, включает штатную Library со Storage lease; state/export provenance берётся из активной entry, а не из hardcoded RAM flags | boot-time media discovery/catalog ещё не реализованы; entry содержит caller-owned RAM copy уже проверенной persistent Session |
| E-BUILD-037 | `0.35.0-persistent-library-admission-measure` | pass: RAM 120 264 B, flash 1 029 116 B; app/factory 1 029 520/1 095 056 B, factory SHA-256 `eb7a69a8…a967f9` | +608 B static RAM и +1 312 B linked flash относительно 0.34; diagnostic admission после explicit HIL command, не boot policy |
| E-HIL-040 | current-boot persistent Library и export на board-01 | pass: exact CID/new `/leshy-hil/s3-wifi-library-20260816-a`; 4 scans read/accept/drop 52/52/0, FIFO high-water 18/64, size trigger; generation 1/52 observations/2 499 B committed за 192 867 us и reopened после real remount; 12 957 B/s против 2 184 B/s, pass 5,93×; `fixture_restored=false`, persistent admission true; actual TFT Home→List→Detail→Export показывает READY/PERSISTENT REAL/generation 1 valid/PERSISTED YES; serial export `persistent=true`, `simulated=false`, Wi-Fi 52; Back освобождает lease 5→0, postflight heap total/free/min 281 496/237 420/147 692 B, GPIO2 LOW; run SHA-256 `cecbc574…f7f53b`, export `2e9c371f…655a3` | current-boot admission после explicit diagnostic path; reboot снова начинает с simulated Library, пока не реализованы безопасный boot mount/catalog/recovery; product Start/Stop, instrumented no-TX, power-cut, LittleFS и endurance открыты |
| E-AUTO-001 | ADR-005 prerelease runner/suite/bundle verifier host tests | pass: manifest/action/assertion/mask bounds, missing-only golden bootstrap, refusal to overwrite, exact/masked pixel mismatch, artifact/candidate tamper, safe internal/escaping tar links и unsigned-default rejection покрыты; full `tools/test.sh` зелёный | queue/quarantine и camera/power остаются открыты; live GitHub HIL закрыт E-AUTO-005/E-HIL-044…045 |
| E-HIL-041 | board-01 automatic `device-smoke` | pass: exact app candidate SHA-256 `e95d7ede…04441b` прошит и verified дважды; второй run ready за 501,72 ms, Home/Back exact и Diagnostics masked-exact дают zero mismatched pixels; acknowledgements 84,204/95,963 ms, final owner none/lease 0, heap total/free/min 281 496/238 832/233 436 B, GPIO2 LOW; runner pass/gate-eligible; `run.json` SHA-256 `16136f08…780f17`, artifact index `9240caee…4ae75` | development bundle локальный: verifier с explicit dev flag pass, default release check fail; exact release build identity, GitHub attestation run, EN/RU matrix, power-cycle/camera и CI publish gate открыты |
| E-BUILD-038 | `0.36.0-prerelease-build-identity-measure` | pass: RAM 120 328 B, flash 1 029 312 B; app/factory 1 029 712/1 095 248 B, app SHA-256 `47bd62ad…66cecd5`, factory `9aec9999…55da75` | +64 B static RAM и +196 B linked flash относительно 0.35; bounded boot evidence добавляет полный app ELF SHA-256 `2e5dfcc2…274e6` |
| E-AUTO-002 | ESP app identity parser, runner/verifier binding и negative host tests | pass: parser валидирует image/app-descriptor magic и читает full 32-byte ELF digest; malformed image, missing identity, firmware/candidate/run/manifest/local-result mismatch fail closed; full `tools/test.sh` зелёный | test-session envelope позже закрыт E-AUTO-004; live GitHub provenance остаётся E-AUTO-005 |
| E-HIL-042 | board-01 build-identity `device-smoke` | pass: exact app SHA-256 `47bd62ad…66cecd5` прошит с verify; candidate descriptor, cold boot и повторный metrics совпали по ELF SHA-256 `2e5dfcc2…274e6`; ready 505,962 ms, Actions 85,338/94,918 ms, три visual comparisons 0 mismatched pixels, final owner none/lease 0, heap total/free/min 281 432/238 768/233 372 B, GPIO2 LOW; `run.json` `d011e052…60dbf8`, artifact index `c021993e…4f318` | два предшествующих failed bundles сохраняют fail-closed truncated-digest и bounded-envelope diagnostics; successful result остаётся local development evidence, поэтому GitHub provenance/promotion/camera открыты |
| E-AUTO-003 | исторический canonical Ed25519 station-attestation prototype | experiment pass: ephemeral-key host test подписал копию candidate/bundle и поймал post-sign tamper | superseded 2026-08-17: persistent station key отвергнут, production code path удалён; не является release evidence |
| E-AUTO-004 | HIL session v2 и self-contained candidate host contracts | pass: 128-bit lower-hex ID и full app identity обязательны; nested begin, wrong end, stale/mixed session и rehashed mixed bundle отклоняются; runner копирует candidate, сверяет copy, прошивает её и индексирует внутри bundle; verifier может не принимать внешний candidate path | runner crash quarantine/power relay и remote immutable artifact download остаются station work |
| E-AUTO-005 | GitHub-native build-once/HIL/promotion trust workflow | live pass: `hil-production` разрешает только `main`; run `31975573475` доказал end-to-end контур, а hardened run `31976152593` на `714ac83` повторил его с exact pinned Node.js 24 Actions без compatibility fallback; candidate provenance проверен до flash, evidence attested, все artifacts/same bytes повторно проверены; unique-label one-job runner удалил credentials/registration и exit 0, repository runners 0; preceding run `31975374875` безопасно cancelled до registration/flash на overly-strict archive-link check; `publish` допускает только stable 1.x и rebuild отсутствует | measurement `0.37…` корректно завершает validation как non-publishable; queue/quarantine, camera/power и полный release-candidate suite остаются открыты |
| E-BUILD-039 | `0.37.0-prerelease-test-session-measure` | pass: RAM 120 368 B, flash 1 030 684 B; app/factory 1 031 088/1 096 624 B, app SHA-256 `25f1bacb…cd83c6`, factory `6fc9a66c…c41eca` | +40 B static RAM и +1 372 B linked flash относительно 0.36; session state не получает hardware/resource lease и сбрасывается reboot |
| E-HIL-043 | board-01 session-bound self-contained `device-smoke` | pass: bundled exact app SHA-256 `25f1bacb…cd83c6` прошит с verify; ELF SHA-256 `0c5277bb…ef7ed8`; run ID `803dd8cfbd28657240fd64af50019588` совпал в manifest/begin/end/run/legacy attestation, UI revision 0→2 и session active true→false; ready 502,245 ms, Actions 84,116/95,379 ms, три visual mismatch 0, final owner none/lease 0, heap total/free/min 281 392/238 728/233 332 B, GPIO2 LOW; self-contained verifier pass; `run.json` `8466fe45…d76948`, index `2f3cb367…4be3e7` | retained run локальный и предшествует GitHub-native E-AUTO-005; CI promotion-proof закрыт E-HIL-044, camera/power открыты |
| E-HIL-044 | board-01 GitHub-native `device-smoke` | pass: Actions run `31975573475`, commit `97e7145`; exact app `ef08797c…9d63a`, factory `87457cc7…280af`, ELF `e2d5b32c…edb94`, evidence archive `d395d913…162d`; build/physical/promotion 2:26/0:59/0:31; run ID `abbcd74e55aa5c05cfbb4f11a6492902`; ready 502,053 ms, Actions 85,164/95,840 ms, three TFT comparisons zero mismatch, final owner none/lease 0, heap total/free/min 281 392/238 728/233 332 B, GPIO2 LOW; candidate/evidence attestations и inner same-byte verifier pass | measurement version non-publishable; stable release, camera/power, extended suite и queue/quarantine остаются открыты |
| E-HIL-045 | board-01 hardened GitHub-native `device-smoke` | pass: Actions run `31976152593`, commit `714ac83`; exact app `16ab071a…7799a`, factory `05013e92…f3f9`, ELF `70ee2b5d…da1`, map `e2761e95…56f1`, evidence archive `1799719f…5bd`; build/physical/promotion 2:30/0:56/0:28; run ID `1585357a5c3b4f5bf70dec0e3b5fe317`; ready 501,840 ms, Actions 85,126/95,192 ms, three TFT comparisons zero mismatch, final owner none/lease 0, heap total/free/min 281 392/238 728/233 332 B, GPIO2 LOW; pinned Node.js 24 Actions, candidate/evidence attestations и inner same-byte verifier pass; runner credentials/registration удалены, repository runners 0 | measurement version получает `VALIDATION PASSED — NON-PUBLISHABLE VERSION`, stable release не создан; stable publish, camera/power, extended suite и queue/quarantine остаются открыты |

| E-SURVEY-004 | `SurveyWorkflow` product orchestration host tests | pass: cancel пишет/sync 0; Start принимает три observations; Detail/Back сохраняет Running; Stop публикует и восстанавливает generation ровно один раз; повторный Stop не пишет; failed third commit сохраняет прежнюю Library generation 2 | текущий product source simulated, backend bounded RAM; real FIFO/persistent adapter и progress/drop UI остаются следующей частью slice |
| E-LIBRARY-003 | `SessionCatalog` validated-root admission tests | pass: empty, valid latest, corrupt-new fallback, idempotent rebuild и direct duplicate-admission rejection; recovery staged в caller-owned workspace, result заменяется только после полной validation; physical diagnostic admission использует тот же bridge | это каталог latest Session одного уже validated root, не boot media discovery/mount или multi-root policy |
| E-BUILD-040 | `0.38.0-product-survey-workflow-measure` | pass: RAM 120 400 B, flash 1 033 560 B; app/factory 1 033 968/1 099 504 B, app SHA-256 `9240cccc…c3e370`, factory `71b2d168…5216a3`, ELF `de5598e1…df9aa` | +32 B static RAM и +2 876 B linked flash относительно 0.37; product vertical slice использует simulated source и bounded RAM store |
| E-AUTO-006 | `device-smoke` revision 2 + bounded query step | pass: suite добавила Survey→commit→Library→export, host validation запрещает action/query ambiguity, newline/non-ASCII/oversized command и capture-after-query; single-scenario golden bootstrap никогда не gate-eligible | historical revision-2 evidence superseded текущей revision 3; GitHub-native run revision 2 не выполнялся |
| E-HIL-046 | board-01 product-workflow `device-smoke` revision 2 | pass/gate-eligible local evidence: exact app `9240cccc…c3e370`, ELF `de5598e1…df9aa`, run ID `ddf0203694d3011788f1762cec64ff11`; ready 502,731 ms; 17 Actions, idempotent Stop `changed=false`; десять TFT comparisons zero mismatch; export generation 2/3 observations/0 dropped, simulated/RAM/RF-off; final owner none/lease 0, heap total/free/min 281 360/238 696/233 300 B, GPIO2 LOW; `run.json` `af5d493f…c2a7`, index `c73f08d1…6376d` | local development evidence без GitHub attestation; real RF/FIFO/SD, boot mount/catalog, camera/power и endurance не проверялись |
| E-SURVEY-005 | allocation-free `SurveyPipeline` host tests | pass: source→FIFO enqueue/drain сохраняет order; progress 3 received/queued/forwarded, partial drain и zero-depth; Stop выбирает batch trigger `stop` и commits once; 65-й record bounded case даёт exactly one drop, high-water 64, forwards/commits 64 без reject | simulated source/RAM store; background cadence, real driver callback и persistent errors ещё не product-connected |
| E-BUILD-041 | `0.39.0-product-survey-pipeline-measure` | pass: RAM 120 488 B, flash 1 035 232 B; app/factory 1 035 632/1 101 168 B, app SHA-256 `3f3b487b…d3fb19`, factory `6e406e8b…8ded77`, ELF `c442c637…ed6d8b` | +88 B static RAM и +1 672 B linked flash относительно 0.38; переиспользован существующий FIFO 64, без второго 4 672 B ring |
| E-AUTO-007 | `device-smoke` revision 3 pipeline assertions/goldens | pass: suite требует ready→drained→committed, received/forwarded 3/3, depth 0, high-water 3, drop 0 и trigger none→stop; семь goldens 0.38 сохранены с suffix, семь 0.39 сняты заново и visual-reviewed | GitHub-native revision-3 run ещё не выполнен; external camera/power и destructive lanes остаются S8 |
| E-HIL-047 | board-01 product-pipeline `device-smoke` revision 3 | pass/gate-eligible local evidence: exact app `3f3b487b…d3fb19`, ELF `c442c637…ed6d8b`, run ID `dc64d3b8d0438567a737f9a97d1cf078`; ready 502,915 ms, 17 Actions max 98,594 ms; pipeline running 3 received/3 forwarded/depth 0/high-water 3/drop 0, commit trigger Stop; десять TFT comparisons zero mismatch; final owner none/lease 0, heap total/free/min 281 272/238 608/233 212 B, GPIO2 LOW; `run.json` `9716a080…074a8f`, index `27da0a1c…cd2b6` | local development evidence без GitHub attestation; source remains simulated, store RAM-only, RF/SD/boot recovery/endurance не выполнялись |
| E-STORAGE-023 | `ProductStorePolicy` negative host matrix | pass: recovery разрешён без повторного prompt только для exact enrolled fingerprint, exact `/leshy/sessions/v1`, existing root, read-only non-writable driver и lease 12; initialize/commit требуют explicit selection, writable driver, правильную root existence семантику, bounded size/reserve и тот же lease; mismatch/root/format/mode/space/resource/conflict fail closed | policy не mount и не filesystem adapter; enrollment/config persistence и реальный read-only driver ещё не реализованы |
| E-SURVEY-006 | `ProductSurveyAdmission` host matrix + board policy query | pass: real start требует explicit Start, available source, valid passive-only plan, writable product commit permit и combined lease 14; permit всегда `persistent=true`, `simulated=false`; device query без authority отвечает `explicit_start_required`/`missing_media` и подтверждает hardware/radio/mount/write false | admission не запускает workers; product UI пока продолжает явный simulated/RAM workflow |
| E-BUILD-042 | `0.40.0-product-admission-policy-measure` | pass: RAM 120 488 B, flash 1 037 472 B; app/factory 1 037 872/1 103 408 B, app SHA-256 `83cac871…4d25844`, factory `6f7cc93e…9a9e29a`, ELF `dadad5b7…503713` | zero static-RAM delta и +2 240 B linked flash относительно 0.39; только contract/query, реальные source/store не стартуют |
| E-AUTO-008 | `device-smoke` revision 4 product admission assertion | pass: bounded query требует exact root, resources 14, persistent/passive true, simulated fallback false и zero hardware/radio/storage effects; прежние workflow/pipeline/visual assertions сохранены | GitHub-native revision-4 attestation ещё не выполнялась; destructive lane остаётся S8 |
| E-HIL-048 | board-01 product-admission `device-smoke` revision 4 | pass/gate-eligible local evidence: exact app `83cac871…4d25844`, ELF `dadad5b7…503713`, run ID `51a294577b902dd2bd1ed53908e86597`; fail-closed query прошла до I/O; ready 507,234 ms, 17 Actions max 99,066 ms; десять TFT comparisons zero mismatch; final owner none/lease 0, heap total/free/min 281 272/238 608/233 212 B, GPIO2 LOW; `run.json` `6361d40e…deafaa`, index `e3796ec3…9608f1` | local unsigned development evidence; реальный product RF/SD lifecycle и boot recovery не выполнялись |
| E-BUILD-043 | `0.41.0-keypad-frontend-measure` | pass: RAM 120 576 B, flash 1 039 304 B; app/factory 1 039 712/1 105 248 B, app SHA-256 `03dc165c…70c05c5`, factory `712a864e…2d6178`, ELF `21f31ab2…ae8958` | +88 B static RAM и +1 832 B linked flash относительно 0.40; task stack и queue — boot-time FreeRTOS allocations, видимые в heap, а не static totals |
| E-AUTO-009 | debounced bounded physical-keypad frontend + `device-smoke` revision 5 | host/static/automatic pass: покрыты short pulse, invalid I2C read, held key без duplicate, stable release, пять mappings, ambiguous chord, wrap `millis()`, 5 ms task и transition queue 16 | physical E-HIL-050 позже опроверг достаточность queue; automatic zero-input state был необходим, но недостаточен |
| E-HIL-049 | board-01 keypad-aware `device-smoke` revision 5 | automatic pass/gate-eligible local evidence: exact app `03dc165c…70c05c5`, ELF `21f31ab2…ae8958`, run ID `490608019ef55ae5c230ed1254a82fad`; ready 503,916 ms; 930 valid/0 erroneous samples, maximum gap 5 ms, queue 0/16 с 0 drops; прежний workflow и десять TFT comparisons zero mismatch; final owner none/lease 0, heap total/free/min 281 184/233 556/228 160 B, GPIO2 LOW | physical stress позже failed; evidence подтверждает idle deployment, но не burst delivery |
| E-HIL-050 | board-01 0.41 chaotic physical keypad stress | fail as designed: frontend поймал 43 presses/43 releases, 86 stable transitions, пять mapped counters, 0 I2C errors/ambiguity, maximum gap 5 ms; transition queue закончила depth 2 и дала 46 drops | sampling/debounce исправлены, но queuing press/release за synchronous UI output не был lossless |
| E-BUILD-044 | `0.42.0-keypad-burst-measure` | pass: RAM 120 584 B, flash 1 039 480 B; app/factory 1 039 888/1 105 424 B, app SHA-256 `674a2ca8…4dc4d6`, factory `268dd022…00b72`, ELF `9c60a9e4…aa8803` | press-only queue и batch state application; capacity осталась 16, per-action diagnostic output остался в drain path |
| E-HIL-051 | board-01 0.42 automatic + structured physical keypad | automatic revision-5 pass: exact app `674a2ca8…4dc4d6`, ELF `9c60a9e4…aa8803`, run ID `e81b13afbf510fc726cc4758c54effca`, ready 505,777 ms, десять zero-mismatch frames; physical fail: поймано 48 presses/48 releases (10/8/10/10/10), dispatched 27, press drops 21, 0 I2C errors/ambiguity, gap 5 ms | press-only filtering недостаточен при undersized consumer queue/output |
| E-BUILD-045 | `0.43.0-keypad-burst-buffer-measure` | pass: RAM 120 584 B, flash 1 039 504 B; app/factory 1 039 904/1 105 440 B, app SHA-256 `cf0adf5a…befbab0`, factory `bd8a1dec…2f60ad`, ELF `8114a78b…eec75e` | +24 B linked flash/zero static-RAM delta vs 0.42; boot heap включает enlarged queue 64 |
| E-AUTO-010 | press-only queue 64, bounded batch drain, single batch diagnostic и retained physical artifact checker | pass: static checks требуют producer/consumer/batch/high-water path; revision 6 требует capacity 64/empty/zero-drop baseline; `check_keypad_acceptance.py` связывает exact version/suite/candidate/run и fail closed без per-key 10, total/release/dispatched/UI-revision 50, transitions 100, high-water ниже capacity и всех failure counters 0 | physical artifact — local operator-generated evidence; GitHub-native revision-6 attestation открыт |
| E-HIL-052 | board-01 0.43 `device-smoke` revision 6 + UI-HIL-A8 | pass: automatic exact app `cf0adf5a…befbab0`, ELF `8114a78b…eec75e`, run ID `d28fac6bd45fc9713d7e5e1f114af86c`; ready 503,657 ms, десять zero-mismatch frames, final owner none/lease 0, heap total/free/min 281 176/233 140/227 744 B, GPIO2 LOW; bound physical run: каждая кнопка 10, presses/releases/dispatched 50/50/50, UI revision 17→67, transitions 100, maximum gap 5 ms, queue high-water 6/64, final depth/drops/errors/ambiguity 0; SHA-256 сохранённого artifact `c7b8af2e…7523dbdc` | local unsigned evidence; real product RF/SD lifecycle, boot recovery, GitHub-native revision 6 и endurance открыты |
| E-BUILD-046 | `0.44.0-sd-readonly-driver-measure` | pass: RAM 120 696 B, linked flash 1 053 188 B; app image 1 053 600 B SHA-256 `b997a1ff…a4451`, ELF `24615f86…c6d97` | +13 684 B linked flash/+112 B static RAM относительно 0.43 за ESP-IDF FAT mount/diskio write blocker, product-root IO, NVS enrollment, boot recovery и diagnostics |
| E-AUTO-011 | bounded product boot guard + retained acceptance checker | pass: static checks требуют read-only diskio status/write rejection и проверяют boot recovery body на запрещённые `freeBytes()`/`filesystemCapacityBytes()`; `check_product_boot_acceptance.py` связывает exact candidate/media, generic device-smoke v6, read-only enrollment/cold boot, persistent export, zero SD writes и lease cleanup | local physical evidence не является GitHub attestation; power-cut/endurance остаются отдельными destructive lanes |
| E-HIL-053 | board-01 0.44 isolated generic HIL + product SD boot | pass: exact candidate в un-enrolled состоянии прошёл `device-smoke`, run `47a59b27d36589fdf9c88273fb2a57af`, ready 506,198 ms, десять zero-mismatch captures, final lease 0; read-only re-enrollment допускает CID `FE343253…019CB7`, generation 1/17 observations, затем cold boot ready 680,261 ms (firmware interactive 564 144 µs), heap total/free/min 281 064/232 628/199 708 B, write blocker 0 hits, SD physical writes 0, lease 12→0; persistent Library export valid/non-simulated/RF-off, Back освобождает 5→0; сохранён [artifact](../../tests/hil/evidence/board-01-product-boot-0.44.json) | одна board/card и local unsigned run; seed bootstrap сделал одну explicit product write 895 B, re-enrollment и каждый accepted boot были read-only; real product Survey worker, physical power-cut и endurance открыты |
| E-BUILD-047 | `0.45.0-product-survey-measure` | pass: RAM 125 448 B, linked flash 1 059 264 B; app image 1 059 664 B SHA-256 `b0925272…70fe2`, ELF `dd33383b…7b904` | +6 076 B linked flash/+4 752 B static RAM vs 0.44 за dynamic SessionStore routing, product runtime state, второй FatFs workspace, Wi-Fi event loop и extended telemetry |
| E-AUTO-012 | exact-candidate product-Survey runner + retained checker | pass: `run_1x_product_survey_hil.py` прошивает candidate, делает два cold boot, query exact-CID recovery, fail-before-commit при inconsistent scan/space accounting, снимает четыре TFT frame, проверяет generation+Library export+lease cleanup; host tests и `check_product_survey_acceptance.py` проходят | standalone local evidence unsigned и для release gate заменено E-AUTO-013; dynamic visual golden comparison остаётся открытым |
| E-HIL-054 | board-01 0.45 real product Survey | локальный прогон `b7c534132b8157c617ae2c07f4b9b8a6` прошёл и пригоден для gate: точный CID, lease 15, ограниченная по времени проверка свободного места 62 483 857 408 B, пассивный scan 15/15 accepted/forwarded без reject/drop/event errors, generation 2→3 и полный cleanup; read-only перезагрузка допускает 3/15 без записей на SD, Library export валиден, постоянен и не симулирован; четыре проверенных TFT-кадра без переполнения viewport; изолированный generic-прогон точного кандидата `fe10902e25066e58f9e188afc991ee3f` также проходит десять эталонных кадров, после чего read-only re-enrollment возвращает устройство в 3/15 и lease 0; сохранён [артефакт](../../tests/hil/evidence/board-01-product-survey-0.45.json) | одна плата/карта и локальные неподписанные прогоны; нет RF detector, физического power-cut, endurance и проверки плотного окружения >64 сетей |
| E-AUTO-013 | однокомандный combined release HIL | pass: `run_1x_release_hil.py` выполняет product HIL точного кандидата, безопасный NVS-only unenroll, generic `device-smoke` revision 6, exact-CID read-only re-enroll и финальный cold boot; `verify_1x_release_hil_bundle.py` независимо связывает оба дочерних run, каждый внутренний hash, candidate/app identity, state isolation и final lease 0; workflow и `publish` используют combined verifier; E-HIL-056 доказывает GitHub-native путь | stable 1.x publish намеренно ещё не выполнялся; camera/power и destructive lanes остаются отдельными |
| E-HIL-055 | board-01 0.45 combined release HIL | локальный product run `408bad8f085d7012fbc85fa57bdd363d` прошёл/gate-eligible, продвинул generation 4→5 с passive 20/20 accepted/forwarded, четырьмя TFT captures и полным cleanup; изолированный generic run `9c81c9f3d0f9cb0bdb69ebc8d002e8ce` проходит десять goldens без mismatch; unenroll не обращается и не пишет на SD, re-enroll и финальный boot восстанавливают точный CID generation 5/20 read-only без blocked/physical writes, с persistent Library, owner none и lease 0; независимая проверка проходит, deterministic 64-file archive — `760fad19…6abad`; сохранён [артефакт](../../tests/hil/evidence/board-01-release-hil-0.45.json) | local unsigned evidence на одной плате/карте; GitHub OIDC attestation, RF detector, physical power-cut, endurance и dense >64-network acceptance открыты |
| E-HIL-056 | board-01 GitHub-native combined release HIL | pass: Actions run [`31987498533`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31987498533), commit `b878b95`; exact app `05865dc1…18d1a9`, factory `672e3f0c…676d0e`, ELF `a43fdbc6…e33a21`, map `c34384c0…f24b7`, evidence archive `fcc1e5fe…5992`; build/physical/promotion 2:32/1:39/0:30; product run `7476ff6b2c0d96a5332e01079302662d` продвигает 5→6 с passive 16/16 и четырьмя TFT captures; generic run `a15e136702f65bb29cb811e74d29c330` проходит десять goldens, финальный re-enrolled boot допускает 6/16 read-only с zero SD writes, owner none/lease 0; candidate/evidence attestations и inner combined verifier проходят; ephemeral runners после run 0; сохранён [артефакт](../../tests/hil/evidence/board-01-release-hil-0.45.json) | measurement version корректно заканчивает `VALIDATION PASSED — NON-PUBLISHABLE VERSION`; stable publish, RF detector, physical power-cut, endurance, dense >64-network acceptance и external camera открыты |
| E-AUTO-014 | foreground external-camera subset foundation | host pass: portable stdlib verifier требует exact `setup/running/committed/export`, station/camera identity, фиксированный frame и калиброванный TL/TR/BR/BL quad; сохраняет SHA-256 camera+GRAM и optical metrics; synthetic matrix принимает совпадающие physical views и fail-closed отклоняет rotation, blank panel, weak policy, unsafe path и неполный stage set; one-shot AVFoundation provider компилируется во временный каталог, исполняет `list` и не создаёт service | на текущем Mac camera devices не обнаружены; real board-01 calibration, пороги, четыре physical capture и включение результата в combined GitHub release gate остаются следующей частью этого slice |
| E-HIL-057 | board-01 short product repeatability | local pass: exact local 0.45 candidate `b0925272…70fe2`/ELF `dd33383b…b904` прошит/verified один раз, затем тот же app повторён без flash; два product Survey цикла непрерывно продвинули generation 6→7→8, приняли/forwarded 23/23 + 21/21 с zero drops, четыре cold boots read-only восстановили exact CID, восемь TFT captures сохранены, heap total/free/min во всех точках точно 276 312/227 876/194 956 B, maximum ready 742,609 ms, final owner none/lease 0; retained [artifact](../../tests/hil/evidence/board-01-product-repeatability-0.45.json) проходит отдельный checker | это двухцикловый short probe и local unsigned evidence, не требуемый 8-hour endurance; external camera, physical power-cut и другое RF environment не проверялись |
| E-AUTO-015 | bounded foreground product endurance orchestrator | pass: `run_1x_product_endurance_hil.py` повторяет exact-candidate product lane, сохраняет checkpoint после каждого цикла, связывает firmware/app/CID/continuity generation, требует четыре capture, zero drops, invariant heap и final lease 0, выдаёт foreground heartbeat каждые 30 s и fail-closed завершает interruption или missing child evidence; release policy нельзя ослабить ниже explicit `--release-endurance`, verified flash, 28 800 s и 32 cycles; четыре host tests покрывают continuity, identity/heap drift, drop/leak/latency и release floor | это одноразовая foreground-команда, не daemon; external camera и physical power-cut — отдельные inputs, GitHub integration полного 8-hour результата открыта |
| E-HIL-058 | отклонённый same-boot SD readiness retry | negative physical evidence: промежуточный image 0.46 повторно входил в raw identification/mount stack внутри того же boot; два цикла продвинули 9→10→11, но после третьего commit 11→12 post-commit cold boot выдал только ROM loader, а USB endpoint не отвечал до полного снятия питания; candidate `c3be20e0…73f9ff`/ELF `7ee60a45…28c8c` отклонён | доказывает, что cleanup flags недостаточно для безопасного same-boot re-entry SDSPI/FatFs; эта реализация не сохранена в source и не является positive recovery evidence |
| E-BUILD-048 | `0.46.0-product-boot-retry-measure` | pass: RAM 125 448 B, linked flash 1 060 116 B; app/factory images 1 060 528/1 126 064 B, app SHA-256 `df4a012a…dc22e`, factory `27725ef6…e39c`, ELF `bf461a9a…513a7`; два RTC no-init words сохраняют между software restart только retry magic/count | +852 B linked flash/+864 B app image и zero static-RAM delta vs 0.45; measurement image, не stable release |
| E-HIL-059 | board-01 0.46 three-cycle endurance-runner smoke | local pass: после полного снятия питания exact candidate прошит/verified один раз, ещё два цикла использовали тот же app; три product Survey cycles продвинули 12→13→14→15 с 20+17+14 = 51/51 accepted/forwarded, zero drops, шестью exact-CID read-only boots, 12 TFT captures, invariant heap 276 312/227 876/194 956 B, maximum ready 761,734 ms и final owner/lease none/0; каждый boot завершился с attempt 1 и zero transient retries; retained [artifact](../../tests/hil/evidence/board-01-product-endurance-smoke-0.46.json) machine-checked и явно `gate_eligible=false` | 60,694 s/три цикла — smoke оркестратора, не обязательный release lane 8 h/32 cycles; natural transient не повторился, поэтому reset-between-attempts имеет host policy coverage, но ещё не positive physical retry event; нет camera, physical power-cut, RF detector и второго dense RF environment |

## Известные неопределённости и риски

- Board-01 дала partial evidence для `HW-T01/T04/T07/T11`; остальные physical tests
  не выполнены, и ни один составной HW-T test ещё не закрыт целиком.
- BOM указывает ESP32-S3-WROOM-1U-N16 (16 MB, без PSRAM), а original build guide —
  OPI PSRAM; `HW-U01` физически открыт, но constrained до N16/no-PSRAM.
- TFT RESET на schematic и `TFT_RST=0` в legacy flags противоречат друг другу;
  GPIO0 запрещён как display reset до `HW-T02`.
- В worktree есть runtime/navigation prototype, интегрированный в 0.x. Он не считается
  реализацией S2 и не должен определять структуру чистой target автоматически.
- Flash/RAM/heap probe UI — platform lower bound 1.x, не бюджет Survey S3 или final
  release.
- PRD имеет статус `draft 0.2 after product review`; P0 requirements ещё не
  accepted/verified до полного technical baseline gate.
- Один экземпляр доступен, но `HW-T01` требует второй v2 board; continuity, logic/RF,
  storage и power evidence всё ещё отсутствуют.
- Для buzzer нет microphone/scope evidence: exact boot/runtime pad state подтверждён,
  но отсутствие слышимого фона остаётся операторским наблюдением и HW-T09.

## Blockers

Весь S1 не заблокирован. Для полного HIL нужны второй экземпляр, мультиметр,
logic analyzer/RF detector и power measurement; отсутствие этих приборов фиксируется
как ограничение evidence и не останавливает budgets/risk register/ADR.
