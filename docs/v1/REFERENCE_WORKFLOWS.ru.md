# ESP32-Leshy 1.x — эталонные сценарии

*Читать на: [English](REFERENCE_WORKFLOWS.md) · **Русский***

Статус документа: **кандидат baseline S1**. Сценарии уточняют границу приёмки уже
существующих `J-*`, `PR-*` и `NFR-*`; они не утверждают, что бинарник 1.x уже
существует. Сценарий считается проверенным только по указанному ниже evidence.

## Назначение и правила

Сценарии определяют продукт через наблюдаемый пользовательский результат, а не
структуру меню. У каждого есть happy path, error path, cancel/back path, измеримая
приёмка и план evidence.

- Тесты используют фиксированные inventory и Session fixtures, чтобы EN/RU видели
  одинаковые данные.
- `Back` — системное действие: обрабатывается не дольше 150 мс и освобождает
  foreground leases покидаемого контекста (`NFR-002`).
- Ошибка не подменяет молча receiver, assembly profile, storage target или active
  mode.
- Cancel не меняет уже подтверждённые исходные данные и не оставляет операцию или
  lease работающими.
- Критическое состояние и доступный Stop понятны без различения цвета.
- Reports/exports не содержат секреты, если формат явно не включает выбранные
  пользователем исходные данные.

## Индекс сценариев

| ID | Результат пользователя | Jobs | Основные requirements | Первый gate реализации |
|---|---|---|---|---|
| WF-01 | Понять, что устройство может делать безопасно | J-05 | PR-001, PR-002, PR-009, PR-014; NFR-001/002/006/010 | S2 |
| WF-02 | Записать одну полезную passive Survey Session | J-01, J-03 | PR-003…PR-005; NFR-002…006/010 | S3 |
| WF-03 | Открыть и экспортировать evidence offline | J-03 | PR-005…PR-007, PR-012; NFR-007…010 | S3 |
| WF-04 | Исследовать, локализовать и сравнить Target | J-02, J-04 | PR-004, PR-006, PR-008; NFR-002/008…010 | S6 |
| WF-05 | Запустить и физически остановить разрешённое Lab action | J-06 | PR-002, PR-009, PR-013; NFR-002/003/006/010 | S7 |
| WF-06 | Обнаружить и сохранить объяснённое wireless evidence в поле | J-03, J-07 | PR-020…PR-023; NFR-002/005…010 | S7 |
| WF-07 | Разблокировать устройство и безопасно работать с явным serial target | J-05, J-08 | PR-017, PR-024, PR-025; NFR-002/006/010 | S7 |
| WF-08 | Запустить permissioned automation или authorized wireless recipe | J-06, J-08 | PR-013, PR-026, PR-027; NFR-002/003/005…007/010 | S7 |

## WF-01 — загрузиться, диагностировать, решить

**Предусловие:** задан declared ESP32-DIV v2 assembly profile; external assembly не
выводится из legacy flags.

**Happy path**

1. Cold boot доходит до интерактивного главного экрана.
2. Diagnostics показывает board, firmware/build, storage и каждый declared module.
3. Каждая capability имеет `declared`, `detected`, `available`, `conflicted`, `fault`
   или `unknown`, evidence и причину.
4. Меню разрешает только совместимые действия; diagnostic report экспортируется.
5. Последний пункт Home открывает Устройство, затем Self-Test: Quick выполняет безопасный read-only
   plan, а Full/Guided до старта показывает applicable checks/fixtures/side effects.

**Error path:** неоднозначная GPIO5/6 или GPIO14/21 assembly остаётся `conflicted`
или `unknown`; Diagnostics объясняет ожидаемый profile и не пробует output modes.
Отсутствующий module считается `fault` только когда он declared профилем.
Отсутствующий по profile module получает `not_applicable`; missing fixture или
недоказуемый результат — `blocked/inconclusive`, но не молчаливый pass.

**Cancel/back path:** выход из Diagnostics возвращает на прошлый экран, не запуская
module и не удерживая foreground lease. Back во время Self-Test останавливает plan
на safe boundary, выполняет cleanup и сохраняет экспортируемый partial report.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-01-A1 | Исправная конфигурация даёт интерактивный UI не позже 2 с после cold boot | HIL timestamp/video trace |
| WF-01-A2 | Golden inventory fixtures одинаково показывают все states/evidence/reason в EN/RU | snapshot tests |
| WF-01-A3 | Недоступное action disabled/hidden до старта `Action` и до получения lease | Action/ResourceBroker integration trace |
| WF-01-A4 | Probe/report не даёт RF/IR TX command и не экспортирует сохранённые credentials | policy tests + HIL detector trace + report scan |
| WF-01-A5 | Back принят не позже 150 мс, ownership table покидаемого контекста пуста | input/resource trace |
| WF-01-A6 | User Quick/Full и release HIL вызывают одинаковые versioned check IDs; host отклоняет missing checks, wrong candidate identity, unexpected side effects или nonzero final ownership | Self-Test contract tests + physical HIL report verifier |

## WF-02 — создать и сохранить passive Survey Session

**Предусловие:** WF-01 выполнен; доступен хотя бы один passive source. Passive Wi-Fi
остаётся предварительным первым source, потому что не требует external assembly.

**Happy path**

1. Survey до запуска показывает available, unavailable и mutually exclusive sources.
2. Start создаёт ровно одну Session со stable ID, build/profile metadata и
   запрошенной source configuration.
3. Normalized Observations входят в одну monotonic timeline. List открывает Detail;
   Back возвращает в List, не останавливая Session.
4. Stop завершает source workers, атомарно подтверждает Session и сообщает место
   сохранения.
5. Сохранённая Session предлагается как следующее действие.

**Error path:** source, не запустившийся, показан с причиной. Остальные выбранные
sources продолжают работу только если preview объявил degraded mode; иначе весь
start завершается до commit Session. Ошибка storage не перезаписывает ранее
подтверждённую Session.

**Cancel/back path:** cancel во время start не оставляет committed Session и leases.
Back из child view не останавливает Survey неявно. Явный Stop идемпотентен: повторный
Stop не создаёт второй commit.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-02-A1 | Golden passive trace создаёт одну Session и ожидаемый ordered набор Observation | simulated-driver integration test |
| WF-02-A2 | Каждый source пишет фактические active windows/duty cycle; unavailable source не порождает вымышленных observations | Session schema assertions |
| WF-02-A3 | Detail/List сохраняют selection; Back укладывается в 150 мс, не теряет и не останавливает source lease случайно | navigation/resource trace |
| WF-02-A4 | Stop подтверждает данные один раз; reboot/power-cut injection не портит старые committed данные | storage fault matrix + HIL power-cut test |
| WF-02-A5 | Failed/cancelled start оставляет ноль workers, foreground leases и видимых committed Sessions | negative integration test |
| WF-02-A6 | Passive run не менее 45 минут/восьми циклов укладывается в часовой release budget без monotonic heap growth, зависания UI, drops, leaked leases или повреждения Session | endurance HIL |

## WF-03 — открыть и экспортировать offline

**Предусловие:** на SD или LittleFS существует хотя бы одна committed Session fixture.

**Happy path**

1. После reboot Library открывается при неактивных radio receivers.
2. Пользователь открывает Session List и Detail, включая исходные Captures и
   integrity state.
3. Export пишет versioned JSON summary; совместимые форматы показываются только для
   данных, которые они представляют без выдумывания.
4. Для готового файла показаны size, checksum, schema version и target.

**Error path:** отсутствующий media, нехватка места, checksum failure, malformed
input или будущая неподдерживаемая schema дают конкретное recovery action. Исходная
Session/Capture остаётся byte-identical.

**Cancel/back path:** cancel export удаляет или инвалидирует temporary output,
сохраняет committed source и освобождает storage. Выход из Library не запускает radio.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-03-A1 | Golden Session открывается после reboot с нулём radio leases и совпадающими counts/checksums | offline integration test + lease trace |
| WF-03-A2 | JSON export проходит declared schema и сохраняет source IDs/units/timestamps | schema and golden-file test |
| WF-03-A3 | Failure/cancel на каждой границе записи сохраняет source hash и не оставляет committed partial export | storage fault-injection matrix |
| WF-03-A4 | Malformed или newer-schema input отклоняется понятно, без reboot и изменения source | bounds/fuzz/migration tests |
| WF-03-A5 | Back укладывается в 150 мс; критические ошибки EN/RU помещаются и понятны без цвета | HIL input + UI snapshot tests |

## WF-04 — исследовать, локализовать и сравнить

**Предусловие:** две golden Sessions содержат повторяющиеся и уникальные identities;
live receiver нужен только для localization.

**Happy path**

1. Общий Observation List открывает Detail с едиными channel/frequency/RSSI units и
   provenance.
2. Пользователь создаёт или открывает Target. Suggested identity links показывают
   confidence и использованное evidence.
3. Radar/localization при поддержке показывает RSSI history и sample age, не выдавая
   их за физическое расстояние.
4. Compare показывает added, removed, changed и unchanged факты между Sessions.
5. Merge/split, notes и tags создают audit-able обратимую Target revision.

**Error path:** stale samples, недостаточное identity evidence, отсутствующий
receiver или несовместимые версии Session указаны явно. Они не создают уверенный
automatic merge или вымышленное расстояние.

**Cancel/back path:** cancel edit/merge/split сохраняет предыдущую Target revision.
Back из live localization останавливает worker и lease не позже 150 мс, не меняя
исходную Session.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-04-A1 | List/Detail/Radar fixtures используют единые units, filters, identity и provenance между radio types | shared-view contract tests |
| WF-04-A2 | Golden pair даёт точно ожидаемый added/removed/changed/unchanged diff | golden comparison test |
| WF-04-A3 | Merge с последующим split восстанавливает прежний identity graph и source references | Target property/round-trip test |
| WF-04-A4 | Low-confidence/stale fixtures помечены и не auto-merge/не показываются как distance | negative domain/UI tests |
| WF-04-A5 | Cancel не создаёт revision; Back из localization укладывается в 150 мс и не оставляет receiver lease | domain/resource HIL trace |

## WF-05 — ограниченное разрешённое Lab action

**Предусловие:** пользователь работает со своим/разрешённым оборудованием; action,
region, hardware stop path и assembly profile доступны. Если в release нет active
action, PR-013 остаётся обязательным инвариантом будущего включения, а не поводом
подделать capability.

**Happy path**

1. Пользователь явно входит в Lab context и выбирает available active action.
2. До подтверждения видны frequency/channel, power, duration, target/fixture,
   regulatory result и физический Stop.
3. Отдельное confirmation запускает TX lease с deadline. Active state различим без
   опоры только на цвет.
4. Stop или expiry сначала вызывает hardware stop path, подтверждает idle state,
   освобождает resources и пишет local audit result без секретов.

**Error path:** unsupported hardware, conflicting lease, invalid parameter, region
block, detector/self-test failure или отсутствие physical-stop evidence блокирует до
TX. Нет best-effort fallback на другой channel/power/module.

**Cancel/back path:** cancel до confirmation даёт ноль TX. Back/panic во время action
вызывает тот же physical stop path, что expiry; reboot не возобновляет active action.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-05-A1 | Любому TX start предшествуют Lab context, valid policy result, explicit confirmation и finite deadline | policy/Action audit test |
| WF-05-A2 | Cancel до confirmation не даёт CE/TX event | logic analyzer/RF detector HIL |
| WF-05-A3 | Back/panic принят не позже 150 мс; hardware idle независимо наблюдается до release lease | input + logic/RF HIL trace |
| WF-05-A4 | Expiry, driver error и watchdog используют один idempotent stop path; reboot не возобновляет TX | fault-injection + reboot HIL |
| WF-05-A5 | Blocked parameters/resource conflicts завершаются до hardware start с actionable EN/RU reason | policy/resource/UI tests |

## WF-06 — защитная полевая проверка

**Предусловие:** passive Wi-Fi/BLE reception доступен; GPS и connected BLE —
optional capabilities. Ни один alert не разрешает countermeasure или hidden connect.

**Happy path**

1. Защита эфира открывает сильнейшую текущую находку с detector version, threshold,
   confidence, uncertainty и exact source frames/observations.
2. Focused Wi-Fi authentication Capture показывает EAPOL/PMKID и complete/incomplete
   handshake state, затем сохраняет immutable PCAP/`hc22000` evidence.
3. Field Survey дедуплицирует Wi-Fi AP/station и BLE observations, добавляет GPS track
   при наличии, сравнивает повторный проход и экспортирует локальный
   WiGLE-compatible artifact.
4. BLE Inspector сохраняет compatible raw packets; connected GATT стартует только
   после выбора target, просмотра permissions и подтверждения mode transition.

**Error path:** недостаточное evidence остаётся inconclusive; отсутствие GPS даёт
явный result без location; unsupported capture/export или отказ GATT видимы. Нет
fallback, который запускает active Wi-Fi или connect/pair к другой BLE identity.

**Cancel/back path:** Back останавливает текущий receiver/connection, завершает только
явно сохранённый artifact, отключает GATT и оставляет ноль foreground leases.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-06-A1 | Каждый alert открывает exact source evidence и показывает detector version/threshold/confidence; insufficient fixture остаётся inconclusive | detector golden/negative tests |
| WF-06-A2 | Authentication fixtures дают точный complete/incomplete state и schema-valid PCAP/`hc22000` без active provocation | parser/export fixtures + no-TX trace |
| WF-06-A3 | Field Survey дедуплицирует golden revisit и экспортирует совпадающие Wi-Fi/BLE/location facts; no-GPS остаётся valid/explicit | golden route/export tests |
| WF-06-A4 | BLE connected mode требует explicit target/permission и всегда disconnect/release-ит lease по Back, timeout или error | Action/resource integration + HIL |
| WF-06-A5 | Все четыре пути сохраняют raw evidence, bounded queues/drop counters, stable navigation и смысл EN/RU errors | schema/UI/resource matrix |

## WF-07 — защищённое устройство и bounded serial console

**Предусловие:** owner настроил Device Lock или явно начинает настройку; внешний UART
target принадлежит пользователю/разрешён, его voltage/pins известны.

**Happy path**

1. Device Lock принимает local PIN setup или unlock с bounded retry policy.
2. Protected captures, secrets, exports и sensitive settings недоступны при lock;
   safe Stop/panic/cleanup и recovery entry сохраняются.
3. Устройство → Serial Console до UART lease показывает pins, voltage assumption,
   baud, framing, mode, target, permissions и resource conflicts.
4. Console и Actions CLI используют одни bounded Actions; exit освобождает UART и не
   сохраняет transcript без явного Save.

**Error path:** wrong PIN, unavailable recovery material, unsafe UART configuration,
conflict, overrun, disconnect или unsupported CLI Action завершается bounded с
remedy. Raw GPIO и policy-bypass fallback отсутствуют.

**Cancel/back path:** cancel не меняет lock state/target; Back закрывает console,
scrub-ит unsaved buffers и освобождает UART/input/storage ownership.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-07-A1 | Locked fixtures не раскрывают protected content через UI, logs, companion, backup или export; Stop/panic/recovery доступны | access-control matrix |
| WF-07-A2 | Retry/recovery bounded и auditable, не обходит update/recovery или safe cleanup | security negative tests |
| WF-07-A3 | Serial start требует reviewed pins/baud/target и exclusive lease; Back/error оставляет zero UART ownership | Action/resource HIL |
| WF-07-A4 | Actions CLI и on-device UI дают одинаковый authorization/result для golden и forbidden operations | shared-Action contract tests |

## WF-08 — permissioned automation и wireless Lab recipe

**Предусловие:** существует signed compatible package или отдельно принятый recipe;
любой active target/fixture принадлежит пользователю, physical stop path имеет evidence.

**Happy path**

1. Пользователь проверяет identity/signature/permissions package/recipe, target,
   resource ceilings, ожидаемые effects, duration и output artifact.
2. Automation выполняет только declared Actions; HID дополнительно требует explicit
   USB/BLE target и scope confirm. BadUSB inspection по умолчанию пассивен.
3. Wireless recipe входит в Lab и повторяет WF-05 policy/confirm/deadline/visible
   TX/physical-stop contract для точного Wi-Fi/BLE/nRF fixture.
4. Completion записывает bounded audit/evidence result и освобождает все resources.

**Error path:** unsigned/incompatible package, undeclared permission, exhausted
budget, missing target, region block, watchdog или detector failure останавливает до
или через тот же idempotent cleanup. Forbidden recipe classes нельзя загрузить.

**Cancel/back path:** cancel до confirm не создаёт HID/TX. Back/panic во время
execution сначала останавливает outputs, затем освобождает leases и сообщает причину.

| Acceptance ID | Наблюдаемый результат | Evidence |
|---|---|---|
| WF-08-A1 | Unsigned, over-permissioned, incompatible или over-budget automation отказывает до undeclared Action/resource | package/policy negative tests |
| WF-08-A2 | HID требует explicit target/scope; cancel-before-confirm ничего не отправляет, passive inspection не отправляет всегда | USB/BLE HIL trace |
| WF-08-A3 | Каждый wireless recipe связан с reviewed fixture/region/power/channel/time bounds и наследует WF-05-A1…A5 | recipe manifest tests + RF HIL |
| WF-08-A4 | Timeout, fault, watchdog, Back и panic сходятся в idempotent cleanup без resumed output после reboot | fault/reboot/physical-stop HIL |

## Результат review S1

Восемь сценариев покрывают `J-01…J-08`. Их acceptance IDs — цели спецификации, а не
текущее evidence. PRD можно принять в baseline S1 только после измерения prototype
budgets и измерения либо явного ограничения оставшихся hardware unknowns. Следующие
этапы добавляют test evidence, не ослабляя эти пути.
