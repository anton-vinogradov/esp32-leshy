# ESP32-Leshy 1.x — трассировка целей

*Читать на: [English](TRACEABILITY.md) · **Русский***

Статус документа: начальная матрица S1. Здесь не повторяются критерии requirements; нормативный
текст находится в [PRODUCT_REQUIREMENTS.ru.md](PRODUCT_REQUIREMENTS.ru.md).

## Цели верхнего уровня

| Goal | Результат для пользователя | Jobs | Requirements | Этапы | Финальное evidence |
|---|---|---|---|---|---|
| G-001 | Одна автономная cross-radio сессия | J-01, J-03 | PR-001…PR-007, NFR-002…NFR-009 | S1–S4 | integration traces, storage fault tests, 8h HIL |
| G-002 | Идентификация, локализация и сравнение | J-02, J-04 | PR-004, PR-006…PR-008, NFR-008…NFR-010 | S3, S6 | reference workflow HIL + golden session diff |
| G-003 | Полезность всего штатного железа | J-03, J-05 | PR-001, PR-002, PR-009, PR-014 | S1, S2, S4, S5 | capability matrix + module HIL matrix |
| G-004 | Безопасная работа со своим оборудованием | J-05, J-06 | PR-009, PR-013, NFR-002, NFR-006, NFR-007 | S1, S2, S5, S7, S8 | safety policy tests + physical TX-stop HIL |
| G-005 | Надёжный offline-first полевой инструмент | J-01…J-05 | PR-005, PR-006, PR-010…PR-012, NFR-001…NFR-010 | S2–S8 | endurance, recovery, update rollback, accessibility matrix |
| G-006 | Расширяемость без нового монолита | J-03, J-06 | CR-001, CR-003, CR-009, PR-012, PR-013 | S2, S6, S7 | external sample extension + permission negative tests |

## Покрытие требований этапами

| Группа | Владелец реализации | Первый gate | Gate полной проверки |
|---|---|---|---|
| PR-001, PR-002, PR-009 | boards + diagnostics service | S2 | S5 |
| PR-003, PR-004 | survey app + observation service + shared views | S3 | S4 |
| PR-005…PR-007 | session/storage/export services | S3 | S5/S8 |
| PR-008 | target service | S6 | S8 |
| PR-010 | update/recovery service | S2 prototype | S8 |
| PR-011 | strings/input/view contracts | S2 | S8 |
| PR-012 | Action API + companion | S3 contract | S6/S8 |
| PR-013 | safety/regulatory/runtime | S2 invariants | S7/S8 |
| PR-014 | board/drivers/apps | S1 scope | S5 |
| PR-015 | capture service + Wi-Fi driver + TFT evidence | S2 screenshot contract/S4 packet capture | S5/S8 |
| PR-016 | feedback service + board safe outputs | S2 idle invariant | S5/S8 |
| PR-017 | connectivity/secrets service | S2 boundary | S6/S8 |
| PR-018 | storage maintenance + recovery | S3 atomic contract | S5/S8 |
| PR-019 | offline enrichment service | S6 | S8 |
| NFR-001…NFR-006 | kernel/runtime/services | S2 | S4/S8 |
| NFR-007…NFR-009 | parsers/storage/schema | S3 | S8 |
| NFR-010 | UI/input/strings | S2 | S8 |

## Каталог и контрольные evidence

| Scope | Requirements | Первый пользовательский gate | Полнота |
|---|---|---|---|
| CAP-001…CAP-008 | PR-001/002/009…011/014, NFR-001/002/004/010 | DEMO-S2 | S5/S8 |
| CAP-009…CAP-017 | PR-003/004/014, NFR-004…006 | DEMO-S3 | S4/S8 |
| CAP-018…CAP-022 | PR-008, NFR-008 | DEMO-S6 | S6/S8 |
| CAP-023…CAP-031 | PR-005…007/009/014, NFR-007…009 | DEMO-S3 | S5/S8 |
| CAP-032…CAP-037 | PR-013/014, NFR-002/006/008 | DEMO-S7 | S7/S8 |
| CAP-038…CAP-041 | PR-002/010/012/013, NFR-006 | DEMO-S6 | S7/S8 |
| CAP-042…CAP-047 | PR-005/007…012/015…019, NFR-005…010 | DEMO-S2/S4 | S5/S8 |

UX-01…UX-07 закрывают visual/interaction gate S2; UX-08 повторяется в каждом
`DEMO-S2…DEMO-S8`. Полный protocol и retention evidence задаёт
[STAGE_DEMO.ru.md](STAGE_DEMO.ru.md).

## Исследования → requirements

| Источник | Полученный вывод | Нормативное продолжение |
|---|---|---|
| Конкурентный анализ CR-001/002/010 | единые Actions, данные как продукт, scenario UX | PR-003…PR-008, PR-012 |
| Конкурентный анализ CR-004/009 | detected hardware и resource leases | PR-001, PR-002, PR-009, NFR-006 |
| Конкурентный анализ CR-005/007/008 | переносимость, offline companion, безопасный update | PR-007, PR-010, PR-012 |
| Vision safety principles | пассивное по умолчанию, заметный bounded TX | PR-013, NFR-002, NFR-006 |
| [Каталог возможностей](CAPABILITY_CATALOG.ru.md) + [product review](CAPABILITY_REVIEW.ru.md) + [UX/UI baseline](UX_UI_BASELINE.ru.md) + [Stage Demo](STAGE_DEMO.ru.md) | полный scope согласован в S1 как 47 capabilities; UX-01/02 фиксируют IA/states, visual system — в S2, feature-complete — в S7, release-complete — в S8 | `CAP-001…047`, `PR-001…019`, `UX-01…08`, `DEMO-S2…S8`; product/UX/test control points для всех PR/NFR |
| [Hardware envelope](HARDWARE_ENVELOPE.ru.md) + [HIL probe](HIL_PROBE.ru.md) | hardware — это main board, detachable RF shield и явные external assembly; capability имеет state/evidence; конфликтующие GPIO не пробуются output-перебором | уточняет PR-001/003/009/014; `E-HW-DESIGN-001`, tool build `E-BUILD-002`, physical HIL `HW-T01…HW-T11`; gates S1/S2/S4/S5 |
| [Эталонные сценарии](REFERENCE_WORKFLOWS.ru.md) | основные пути имеют явные happy/error/cancel behavior и acceptance IDs `WF-01-A1…WF-05-A5` | покрывает J-01…J-06 и PR-001…PR-009/012…014; test ownership распределён по S2/S3/S6/S7/S8 |
| [Реестр ресурсных бюджетов](RESOURCE_BUDGETS.ru.md) | no-PSRAM envelope, build/runtime measurements, временные limits и явные unknowns разделены | уточняет NFR-001…006 и ограничивает targets S2/S3; `E-BUDGET-001` |
| [Реестр рисков](RISK_REGISTER.ru.md) | hardware, integrity, safety, dependency, privacy и scope risks имеют controls и closure owners | пересекает PR-001…PR-019/NFR-001…010; review на каждом gate |
| Clean measurement target 1.x | independent pinned build реализует BoardProfile, projection HardwareInventory→AppCatalog, unified display/input, buzzer-safe boot output, storage/runtime contracts и interactive exact-CID real passive Wi-Fi→FIFO→persistent SessionStore→cold-boot Library/export path с fail-closed ProductStore/ProductSurvey admission, abort cleanup, bounded Survey/Observation model, Session codec/store и NDJSON evidence без legacy sources | `E-BUILD-003…047`, `E-HIL-006…054`; implementation evidence для PR-002 и slices PR-003…007/009/012/NFR-002/003/005…010 плюс lower bounds для PR-001/014, NFR-001/010, RB-02…06 |
| GPIO2 buzzer regression | upstream issue #117 и 0.x commit `04fd290` подтверждают active-HIGH control и boot LOW fix; 1.x выражает его отдельным safe-output invariant до console/display | `E-BUZZER-001`, `E-BUILD-028`, `E-HIL-031`; снижает R-004, HW-U08; audible/electrical HW-T09 остаётся открыт |
| [UI automation contract](UI_AUTOMATION.ru.md) | physical и diagnostic input используют normalized Actions; actual TFT GRAM становится воспроизводимым PNG/state evidence без рутинного участия оператора | `UI-HIL-A1…A7`, `E-HIL-008`; S2 owner для PR-002/011/012 и NFR-001/002/003/010 |
| [Автоматический предрелизный HIL](PRE_RELEASE_HIL.ru.md) | generic host-runner и enrolled product runner прошивают exact candidate, связывают app identity, проходят public Actions/query, снимают real TFT и создают hash-indexed evidence; product lane дополнительно делает два boot, bounded passive scan/commit, recovery/export и final lease checks без resident service; GitHub OIDC/Sigstore promotion повторно проверяет attested bytes без rebuild | `E-AUTO-001…012`, `E-HIL-041…054`, ADR-005; retained checkers связывают keypad, isolated boot и real product Survey; GitHub integration product lane, destructive lane, внешний camera subset и stable publish открыты |
| [HIL атомарности storage](STORAGE_HIL.ru.md) | fixed dual heads публикуют только после sync; exact-fingerprint guard запрещает unknown media; guarded FAT commit/remount/reopen, real-source batching, six-boundary recovery, exact-CID write-blocked boot и interactive product commit/abort проверены physical | `E-STORAGE-001…005/019…023`, `E-SURVEY-003`, `E-LIBRARY-002/003`, `E-HIL-033…040/053/054`, `ST-HIL-A01…A10`; product Survey commits 2→3 и read-only recovers 3/15; power-cut и LittleFS parity остаются S5/S8 |
| HIL leases AppRuntime/ResourceBroker | disabled apps ничего не получают; enabled launch атомарно получает весь requested resource set; Back освобождает ownership внутри UI budget | `E-RUNTIME-001`, `E-BUILD-009`, `E-HIL-012`; первое implementation evidence для ADR-002, PR-002/009 и NFR-003/006; physical bus arbitration остаётся evidence S5/S7 |
| Passive Wi-Fi Survey ingress | passive-only plans отклоняют active/directed operation; explicit adapter отключает NVS/credentials, owns/cleans event loop и не вызывает connect/config/raw-TX API; под lease 15 product path нормализует records в FIFO 64, commits одну authorized Session и передаёт reboot-validated Session в Library/export | `E-SURVEY-001…003`, `E-BUILD-010/034/036/037/046/047`, `E-HIL-013/037/039/040/053/054`, WF-02-A1/A5; product run принимает/forward 15/15 с zero software TX calls/event errors; instrumented physical no-TX и endurance открыты |
| Product Survey workflow | simulated capability остаётся explicit/RF-free без enrollment; после exact-card boot admission AppCatalog выбирает real/persistent provenance и lease 15. Explicit Start проверяет bounded cached space/root/CID, passive scan drain FIFO 64, Stop publishes/reopens ровно следующую product generation, reboot/export подтверждают её; Back из Running aborts без commit, failures сохраняют prior Library и clean mount/backend | `E-SURVEY-004…006`, `E-STORAGE-023`, `E-LIBRARY-003`, `E-BUILD-011/040…042/046/047`, `E-HIL-014/046…048/053/054`, WF-02-A1/A2/A4/A5; interactive real worker и automatic board lane реализованы для одной card; power-cut/dense RF/endurance открыты |
| Session codec и offline reopen | stopped bounded Session превращается в canonical CBOR manifest/framed records; bounded SessionStore атомарно publishes/rejects/falls back, переживает host process death, повторяет fallback на board RAM, открывается без radio и экспортирует deterministic JSON | `E-STORAGE-003…005`, `E-BUILD-012/013`, `E-HIL-015/016`, WF-02-A4/WF-03-A1/A3; первое implementation evidence для PR-005/006 и NFR-007…009; persistent target reset/power-cut открыты |
| Offline/persistent Library | bounded controller принимает только stopped/valid Sessions и показывает List/Detail с generation, integrity, simulated/persistent и RF provenance; `SessionCatalog` staged-recovers latest valid generation одного validated root, включая corrupt-new fallback; exact-CID cold boot теперь заменяет simulated fixture, а Back освобождает Storage+UI lease | `E-LIBRARY-001…003`, `E-BUILD-014/037/040/046`, `E-HIL-017/040/046/053`, WF-03-A1/A3; implementation evidence для PR-006 и NFR-002/003/008/010; generic discovery semantics и multi-root policy открыты |
| Explicit Library export | Detail→Export Ready разрешает bounded deterministic JSON artifact с Session summary и provenance; physical recovered Session экспортируется как `persistent=true`, `simulated=false`; command вне этого state возвращает `not_requested` | `E-EXPORT-001`, `E-BUILD-015/037`, `E-HIL-018/040`; implementation evidence для PR-007/012 и NFR-002/003/007…010; WF-03-A2 full IDs/units/timestamps и file/companion delivery открыты |
| Read-only media discovery | typed adapter record запрещает claims presence от non-authoritative card detect и требует RO mount/filesystem/fingerprint/capacity до `detected`; board-01 читает GPIO38 без mount/write | `E-STORAGE-006`, `E-BUILD-016`, `E-HIL-019`, contract slice ST-HIL-A01; implementation evidence для PR-001/005/009 и NFR-006/007; polarity, media identity и filesystem открыты |
| Mount authorization | любая попытка SD mount требует explicit target selection, proven RO-only driver behavior, format disabled и exclusive ownership Storage+RadioSpi; stock SDFS fail closed до execution | `E-STORAGE-007`, `E-BUILD-017`, `E-HIL-020`, contract slice ST-HIL-A02; implementation evidence для PR-005/009 и NFR-002/006/007; dedicated RO protocol и physical media открыты |
| SD identification-only plan и parser | fixed bounded command plan читает OCR/CID/CSD initialization metadata и явно отклоняет write/program/erase/lock/general commands; parser проверяет responses, CRC16, identity structure и capacity | `E-STORAGE-008/009`, `E-BUILD-018/019`, `E-HIL-021/022`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-005…007; physical SPI открыт |
| Fake SD identification transport | bounded state machine выполняет identification plan через exact command/argument fake, останавливается после 100 init attempts, отклоняет каждый injected exchange failure и отказывает physical transports до вызовов | `E-STORAGE-010`, `E-BUILD-020`, `E-HIL-023`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…007; resource-owned physical adapter открыт |
| SD SPI wire codec | allocation-free framing выдаёт known CRC7 command packets, а bounded parsers принимают только valid R1/R3/R7 и защищённые CRC16 16-byte identity data | `E-STORAGE-011`, `E-BUILD-021`, `E-HIL-024`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-005…007; chip-select, clocks, bus ownership и physical card открыты |
| Physical SD identity | exact confirmation плюс ownership Storage+RadioSpi разрешают один identification-only adapter 400 kHz; три board runs возвращают stable CID/CSD/capacity и complete cleanup CS/CE/resources | `E-STORAGE-012`, `E-BUILD-022`, `E-HIL-025`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…007; block/filesystem reads, instrumented RF silence, radio recovery и persistence открыты |
| Physical SD partition map | один отдельно authorized CMD17 читает только high-capacity LBA0; bounded CRC16/CRC32C и MBR geometry checks не сохраняют raw sector | `E-STORAGE-013`, `E-BUILD-023`, `E-HIL-026`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…007; partition boot, filesystem traversal, instrumented RF silence и persistence ещё открыты на этом evidence point |
| Physical FAT32 boot geometry | второй permit выводит единственный разрешённый LBA из valid MBR metadata; один block подтверждает FAT32 signature, bounds, layout и sanitized volume metadata без mount | `E-STORAGE-014`, `E-BUILD-024`, `E-HIL-027`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…009; directory names/data, allocation traversal, radio recovery и persistence открыты |
| Metadata-only FAT32 root directory | exact MBR/boot geometry выводит единственный разрешённый root LBA; approved parsing `counts_hash_only` публикует только entry classes/CRC32C, никогда names, и обнуляет raw buffer | `E-STORAGE-015/016`, `E-BUILD-025/026`, `E-HIL-028/029`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/006/009 и NFR-002/005…009; end marker во втором sector завершает root inventory текущего card state, а file/FAT chains, free space и persistence открыты |
| FAT32 FSInfo technical metadata | boot-declared in-reserved sector — единственный разрешённый LBA; signatures, free/next hints, cluster bounds и CRC32C проверяются до обнуления raw buffer | `E-STORAGE-017`, `E-BUILD-027`, `E-HIL-030`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…009; hints не являются FAT scan, VFS/persistence открыты |
| FAT32 reserved/root cross-check | exact first FAT LBA из MBR/boot geometry разрешает один sector; parser интерпретирует только FAT[0] media, FAT[1] health flags и FAT[2] root allocation, затем bounded-сверяет FSInfo и обнуляет buffer без chain traversal | `E-STORAGE-018`, `E-BUILD-029`, `E-HIL-032`, contract slice ST-HIL-A01/A02; implementation evidence для PR-001/005/009 и NFR-002/005…009; full allocation recount, VFS/persistence и instrumented RF silence открыты |
| Guarded physical FAT SessionStore | exact CID, explicit disposable selection и новый bounded namespace разрешают исторический SDFS path с disabled format; common `SessionStore` commits два generations, unmount/remount и read-only reopen generation 2; retry отказывает existing namespace с zero logical writes | `E-STORAGE-019`, `E-BUILD-030`, `E-HIL-033`, slices ST-HIL-A02/A03/A05/A06; implementation evidence для PR-005/006/009 и NFR-002/005…009; reset позднее измерен в E-HIL-035, а power-cut, product workflow и LittleFS parity открыты |
| Guarded SD SessionStore throughput | production-candidate ESP-IDF SDSPI path на actual 4 MHz commits через direct FatFs calls с exact `FRESULT` и real unmount/remount recovery; fixed FIFO/policy требует 2 KiB/5 s/capacity/Stop/safe-shutdown и теперь принимает real passive Wi-Fi | `E-STORAGE-020/022`, `E-SURVEY-003`, `E-BUILD-031/035/036`, `E-HIL-034/037…039`, slices ST-HIL-A02/A03/A05/A06; synthetic batching даёт 9 068 B/s, real path — 6 921 B/s против required 2 184 B/s; power-cut, product workflow и LittleFS parity открыты |
| Guarded software-reset recovery | host-tested wrapper наблюдает шесть неизменённых commit boundaries; exact-CID arm использует уникальный bounded namespace и `esp_restart`, а exact-CID recovery открывает existing scratch read-only и требует software-reset reason, allowed generation, неизменные prior hashes, zero writes/syncs и complete cleanup; runner сохраняет boundary checkpoints и повторяет только exact fail-closed readiness signature `missing_media` | `E-STORAGE-021`, `E-BUILD-032`, `E-HIL-035`, slices ST-HIL-A02/A03/A04/A06; шесть physical software-reset boundaries восстанавливают 1/1/1/1/1/2 на одной card/board; physical power-cut, endurance, source-rate, product workflow и LittleFS parity открыты |

## ADR coverage

| ADR | Requirements / risks | Owner реализации | Verification gates |
|---|---|---|---|
| [ADR-001](adr/ADR-001-toolchain.ru.md) | PR-001/010/014, NFR-001/006; R-011/012/013 | platform/build | clean target S2; reproducibility/recovery S8 |
| [ADR-002](adr/ADR-002-resource-policy.ru.md) | PR-001/002/009/013/014, NFR-002/006; R-003/004/005/008/009 | kernel/boards/drivers | invariants S2; physical HIL S5/S7 |
| [ADR-003](adr/ADR-003-storage-schema.ru.md) | PR-003/005…008/012, NFR-007…009; R-006/010/014/016 | storage/session/library | slice S3; fault/endurance S5/S8 |
| [ADR-004](adr/ADR-004-action-boundary.ru.md) | PR-002/009/012/013, NFR-002/003/006; R-008/009/014/016 | SDK/kernel/services | dispatcher S2; transports/safety S6/S7/S8 |
| [ADR-005](adr/ADR-005-pre-release-hil.ru.md) | PR-002/010/011/012/014/015, NFR-001…003/005/007/010; R-004/006/011/012/014/016 | platform/verification/firmware | device-smoke S1/S2; signed immutable release gate S8 |

Все пять решений — accepted design constraints; ни одно не переводит requirement
в implemented или verified.
