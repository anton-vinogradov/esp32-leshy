# ESP32-Leshy 1.x — протокол промежуточных Stage Demo

*Read in: [English](STAGE_DEMO.md) · **Русский***

Статус: **обязательный delivery gate для S2…S8**.

Тестирование не откладывается до полной прошивки. Каждый вертикальный slice проходит
host tests и применимый HIL сразу, а этап S2…S8 закрывается только воспроизводимым
Stage Demo на реальной плате. Процент готовности и отдельные unit tests demo не
заменяют.

## Общий пакет demo

Для каждого `DEMO-S*` сохраняются:

1. firmware version, commit/worktree identity, board/profile и dependency lock;
2. сценарий из Home с happy path, error/degraded path и Back/cancel;
3. автоматический serial/action trace и real-TFT captures ключевых состояний;
4. применимые host/unit/integration результаты и firmware size/RAM budgets;
5. HIL результат boot/input/resource cleanup и затронутых физических модулей;
6. известные ограничения без формулировки «готово», если gate ещё открыт;
7. ссылки `CAP-* → PR/NFR-* → WF-* → evidence` в traceability/STATUS.

Оператор нужен только для физического наблюдения, которое нельзя получить с платы
или приборов автоматически. Обычный переход по меню и TFT evidence выполняет UI
automation.

## Demo по этапам

| ID | Что демонстрируется | Минимальный сквозной путь | Что это доказывает |
|---|---|---|---|
| DEMO-S2 | Независимая платформа и UX/UI baseline | boot → capability Home → Self-Test Quick → Diagnostics/disabled reason → report → Back | clean target, real hardware probe, единые Actions, базовый visual system, user-visible automation, zero leaked leases |
| DEMO-S3 | Первая сохраняемая Survey Session | Start passive Wi-Fi → List → Detail → Stop → reboot → Library → export | первый реальный end-to-end product workflow и atomic persistent storage |
| DEMO-S4 | Cross-radio passive Session | несколько совместимых receivers → timeline/radar → degradation → reopen/export | общая модель Observation, scheduler/duty cycle и passive stability ≥45 минут/≥8 циклов в часовом release budget |
| DEMO-S5 | Полнота штатного hardware | Full/Guided preflight → probe каждого present module → observe/capture → Library → inspect/export; approved replay отдельно | аппаратный паритет, optional/degraded behavior, честные N/A/blocked results и recovery/power safety |
| DEMO-S6 | Targets, compare и companion | baseline Session → повторный проход → diff/Target evidence → local companion export | главные продуктовые отличия и одна Action/schema boundary |
| DEMO-S7 | Конкурентная полнота, защищённые tools, Safe Lab и SDK | matrix Защита эфира/auth Capture/Field Survey/BLE Inspector → negative paths Lock/Serial → signed automation → admitted wireless recipe → timeout/panic; sample extension | feature-complete всех 55 принятых capabilities, privacy/permission boundaries, physical stop и расширяемость без обхода policy |
| DEMO-S8 | Release candidate | exact candidate → полный Self-Test plan → mixed field workflow → interrupted update/write → rollback/recovery | одинаковые on-device/release checks, independent oracle, release-complete binary, provenance, endurance и recovery |

`DEMO-S7` — stage matrix, а не один unsafe monolithic run. Он покрывает WF-06…WF-08,
negative cases R-020…R-023, exact evidence/cleanup для CAP-048…CAP-055 и independent
physical-stop contract WF-05 для каждого admitted active path. Passive detector,
capture, route и inspection results не подменяют active fixture proof, а unavailable
fixture остаётся blocker, не simulated pass.

`DEMO-S2` принят evidence `E-BUILD-060`/`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`.
Exact committed candidate 0.58 выполнил 29 public Action/query steps и совпал с
девятью отдельно записанными real-TFT goldens без расхождений; Quick прошёл 8/8,
safe outputs оставались неактивны, final resource lease равен нулю. Это stage gate
S2, а не release: полный capability coverage остаётся blocked, пока S3…S7 не
зарегистрируют свои checks.

S3 progress `E-AUTO-023`/`E-HIL-083` переиспользует тот же exact candidate 0.58 и
подтверждает real passive product path через live List→Detail→Back, commit generation
65→66, cold read-only reopen, Library и JSON export. Пять TFT states визуально
проверены, final ownership равен нулю. Normal-path evidence с тех пор продвинулся
через 0.60/0.62, а exact 0.68
`E-AUTO-032`/`E-HIL-092` закрывает missing-source real-TFT path без запуска source или
store, записи bytes, изменения прежней Library 68/25, утечки lease или скрытого retry
по Select. Это всё ещё намеренно не `DEMO-S3`: открыты независимо записанные final
demo goldens и воспроизводимый gate run. Exact 0.69 `E-AUTO-033`/`E-HIL-093`
принимает normal/remount throughput LittleFS, а exact 0.70
`E-AUTO-034`/`E-HIL-094` — все шесть software-reset boundaries с one-write restore
inactive OTA1. Управляемый physical power-cut — named gate `DEMO-S4`.

`DEMO-S3` теперь принят `E-AUTO-035`/`E-HIL-095`/`E-GATE-003`. Отдельный non-gate
recording run заморозил пять вручную проверенных TFT goldens до distinct gate run.
Exact 0.70 затем продвинул generation 69→70 с 29/29 passive observations, zero drops,
cold read-only reopen и valid Library export; все пять сравнений имеют zero unmasked
mismatch, heap invariant, final ownership нулевой. S3 закрыт, S4 активен; это не
promote release и не отменяет ни один gate `DEMO-S4`.

Progress S4 до exact 0.75 теперь покрывает selectable/durable real Wi-Fi/BLE и
compatible runtime degradation. `E-AUTO-040`/`E-HIL-100` безопасно инъекционно делает
BLE unavailable, продолжает два real Wi-Fi cycles и 28 observations, commits
generation 77→78, cold-reopens восемь ordered windows с точным unavailable interval
и заканчивает с zero drops/overflow и lease 0. Это slice checkpoint, не `DEMO-S4`:
exact 0.76 затем принимает общий read-only Observation browser — фильтры
Все/Wi-Fi/BLE, List/Detail, bounded RSSI history и frozen snapshot с выключенным RF
для 45 observations, generation 80→81, девяти exact TFT states, cold recovery и zero
drops/overflow. Exact 0.77 затем принимает immutable Capture provenance и canonical
observation CSV на 47 rows. Exact 0.78 принимает намеренно отдельный bounded Wi-Fi
packet Capture: 16 retained real frames, разобранный radiotap PCAP, aggregate-only
repository evidence, RAM scrub и final lease 0. Exact 0.79 затем принимает explicit
privacy-confirmed atomic persistence, generation 82→83, cold read-only reopen Library
и byte-exact PCAP без второго payload buffer. Exact 0.80 затем регистрирует
завершённые platform/S3/S4 checks в Self-Test. Exact 0.81 переводит его на plan v4:
16 checks проходят, три отсутствующие assembly дают N/A, identity check declared
nRF24 #1/#2 и CC1101 проходит под exact read-only wire bounds, blocked остаётся только
total future coverage. Полезные passive receiver workflows, active Full/Guided
execution, controlled physical power-cut и multi-source stability ≥45 минут/≥8 циклов
остаются обязательными.

Exact 0.82 принимает первую из этих полезных workflows shield: явный путь
Survey→RF spectrum→2.4 GHz/nRF24 рисует volatile карту активности по 83 каналам,
поддерживает измеренную pause/resume, завершает 21 sweep через два receiver с exact
receive-only wire accounting, сохраняет heap/storage invariant и возвращается Home
с lease 0. Retained contract не заявляет calibrated power или instrumented physical
RF silence. Active Full/Guided execution, controlled physical power-cut и endurance
всё ещё держат `DEMO-S4` открытым.

Exact 0.83 принимает вторую полезную workflow shield: Survey→RF spectrum→Sub-GHz/
CC1101 показывает plans 315/433/868/915 МГц, снимает один из 64 bins за проход main
loop и перерисовывает экран только после sweep. Board run завершает каждый диапазон,
удерживает ровно 351 sample во время pause 400 ms, возобновляет работу и чисто
останавливается после 354 samples при zero TX/PATABLE/FIFO/storage side effects,
invariant heap/storage и final lease 0. RSSI и frequency scale не калиброваны,
physical RF silence не измерен. Active Full/Guided execution, controlled physical
power-cut и endurance всё ещё держат `DEMO-S4` открытым.

Exact 0.84 принимает первый active execution slice Full/Guided. Plan v5 сохраняет
Quick read-only 8/8, затем активно выполняет один полный receive sweep двух nRF24 и
один receive sweep CC1101 433 МГц по 64 bins. Full возвращает 18 pass, zero fail,
один честный blocker future coverage и три N/A; все TX/storage counters остаются
нулевыми, storage generation — 83, 11 TFT states проходят review, final lease — zero.
Первый mismatch equation runner сохранён fail closed. Remaining
Survey/Library/Capture execution, controlled physical power-cut и endurance gate с
часовым бюджетом всё ещё держат `DEMO-S4` открытым.

Exact 0.85 принимает следующий slice Full/Guided. Plan v6 сначала выполняет RF
phase, освобождает её, затем через отдельную cancellable boundary переходит к
read-only audit сохранённых artifacts: recovery generation 83 по exact CID, Library
JSON и capture metadata, staged CSV и machine-parsed PCAP 16 records/2 773 B. Full
возвращает 21 pass, zero fail, один честный blocker future coverage и три N/A;
storage writes и TX events остаются нулевыми, 12 TFT states проходят review, final
lease — zero. Первый telemetry-truncation failure сохранён fail closed рядом с
исправленным run. Создание новой disposable Survey/Capture, controlled physical
power-cut и cross-radio endurance gate ≥45 минут/≥8 циклов всё ещё держат `DEMO-S4`
открытым.

Exact 0.86 принимает disposable slice Full/Guided. Plan v7 добавляет четыре checks,
которые создают Session из трёх observations только в scratch namespace exact CID,
commit-ят её тремя writes и durability barriers, восстанавливают/экспортируют после
read-only remount, затем удаляют каждый exact scratch file. Product generation 83/0
не меняется, counters TX/product-write остаются нулевыми, проходят 13 TFT states и
final lease 0. Первый candidate без timeline сохранён fail closed с zero writes;
исправленный candidate связывает capture metadata с finalized Wi-Fi timeline.
Controlled physical power-cut и endurance gate ≥45 минут/≥8 циклов в пределах часа
теперь являются двумя оставшимися gates `DEMO-S4`.

Exact 0.87 затем закрывает heap-budget defect, обнаруженный evidence 0.86. Final
facts теперь перестраивают Quick, native case ниже floor даёт fail, один общий serial
workspace возвращает 4 608 B static RAM. Тот же physical plan-v7 run проходит с
minimum 133 884 B против floor 131 072 B при неизменном functional/cleanup evidence.
Это закрывает heap issue, но не два оставшихся gate `DEMO-S4`.

Exact 0.88 принимает calibrated XPT2046 touch как второй неблокирующий input path
поверх того же Navigator и finger-sized rows. Exact 0.89 затем закрывает
release-endurance gate: 8/8 полных Wi-Fi+BLE product cycles за 2 799,845 s продвигают
generation 86→94, передают 367 observations через 16 cold boots, сохраняют heap и
exact CID, фиксируют zero drops/timeouts и завершают каждый цикл без owner/lease.
Lifecycles radio и SD не пересекаются. Controlled physical power-cut recovery теперь
единственный оставшийся gate `DEMO-S4`; сам этап ещё не завершён.

Exact 0.90 затем принимает финальную product-first иерархию меню без изменения
gate: Обзор/Захват/Библиотека — прямые рабочие entries, planned Цели/Лаборатория
fail closed, а Настройки/Самопроверка/Диагностика/О системе находятся в Устройстве.
Восемь real TFT states доказывают key/touch traversal и final zero ownership.
Controlled physical power-cut recovery остаётся единственным gate `DEMO-S4`.

`DEMO-S4` принят `E-AUTO-066`/`E-HIL-126`/`E-STORAGE-028`/`E-GATE-005`. Exact 0.101
сначала проходит автоматический product regression на 17 states с unchanged product
generation 95/0, затем выполняет все шесть boundaries SessionStore при реальном
снятии USB-питания. Host наблюдает каждый blackout длительностью 5,216…6,589 s;
возвращается та же USB identity с `ESP_RST_POWERON`; read-only recovery выбирает
generations 1/1/1/1/1/2 с тремя observations, неизменными prior CRC, zero recovery
writes/syncs, полным cleanup scratch и lease 0. Вместе с принятым endurance exact
0.89 на 2 799,845 s/восемь циклов это выполняет стабильный exit gate S4. S4 закрыт,
S5 активен. Результат покрывает одну пару board/card, не выпускает релиз и не
заявляет instrumented RF silence.

Прогресс S5 теперь принимает автономную половину `DEMO-S5` на board-01 через exact
0.144 `E-AUTO-102`/`E-HIL-162`/`E-RADIO-020`/`E-STORAGE-033`. Из публичного пути
Устройство→Самопроверка→Полная plan v10 запускает все три receive path nRF24,
CC1101, bounded OOK/FSK и вход IR, затем проверяет product Recovery/Library,
applicability-aware PCAP и disposable Session exact CID. Быстрая проходит 9/9;
Полная даёт 28 pass/0 fail/1 blocked/3 N/A с zero TX/product writes/input drops,
margins heap 14 960/14 696 B, полным cleanup scratch, 13 TFT captures и финалом
Home/none/lease 0. Blocker capability coverage намеренный: qualified positive source
nRF24/Sub-GHz OOK/FSK не участвовал. Поэтому это воспроизводимый delta checkpoint,
а не `DEMO-S5`; source-bound physical paths receive→save→cold export и интегральный
two-board exit run остаются обязательными.

Exact 0.145 `E-BUILD-145`/`E-HIL-163` дополнительно принимает исполнимый slice
настроек интерфейса для этой демонстрации. Устройство→Настройки показывает четыре
полноширинные строки; язык EN/RU, пять уровней яркости и темы Лесная/Контрастная
применяются сразу и сохраняются. Один exact flash и два физических hard reset
доказывают сохранение изменённых настроек после reset и повторное сохранение
восстановленных RU/100%/Лесная. Звук явно недоступен, баззер остаётся inactive,
сохранены три TFT state, run заканчивается Home/none/lease 0 с zero TX/input drops.
Это cadence-controlled delta, а не замена финальной matrix `DEMO-S5`.

`E-AUTO-126` принимает host/build orchestration contract для `DEMO-S6`. Одна команда
ограничена ровно одной application flash, записывает baseline Survey и одну contiguous
repeat Survey, открывает и закрывает evidence view каждого conclusion сравнения,
экспортирует ту же пару как canonical offline USB snapshot и доказывает чистый выход
Home/none/lease 0. Команда не запрашивает SoftAP или host network tool, поэтому
активный Wi-Fi Mac остаётся вне теста. Это подготовка, а не physical evidence:
one-command run на плате ожидается, physical HTTP parity всё ещё требует отдельный
client, а deferred predecessor gate S5 по-прежнему удерживает final acceptance S6.

## Ритм тестирования внутри этапа

- **При изменении:** быстрые host/static tests и связанные negative cases. Physical
  HIL по умолчанию **дельтовый**: выполняются только затронутый сценарий, соседний
  negative path и финальный cleanup. Candidate прошивается не более одного раза и
  вообще не перепрошивается, если hash бинарника не изменился.
- **Периодический checkpoint:** после 15 принятых delta HIL checkpoint выполняется
  применимая regression matrix текущих возможностей. Один exact candidate image
  прошивается один раз и используется всеми сценариями.
- **Немедленный полный trigger:** интервал не ждём после cross-cutting изменения
  safety, power, storage, resource ownership или board profile.
- **Перед gate этапа или RC:** выполняются полный применимый `DEMO-S*`, regression
  matrix текущих возможностей и review открытых рисков/бюджетов. Недоступные
  physical fixtures остаются явными blockers и не подменяются software evidence.
- **S8:** два последовательных RC проходят один и тот же release packet без
  изменения критериев после результата.

`tests/hil/hil-cadence.v1.json` — machine-readable policy. Перед physical работой
запускается `python3 tools/plan_hil_scope.py --base HEAD`; на границах добавляется
`--stage-end` или `--release-candidate`. Planner возвращает `none`, `delta` или
`full`, причину и flash policy. Интервал считает новые принятые retained HIL summary
после текущего anchor, а не попытки или нажатия клавиш.
Считается только root evidence с явным status `pass` или начинающимся с `pass_`;
сохранённые fail-closed attempts никогда не продвигают интервал. Завершённая periodic
matrix становится новым anchor и сбрасывает счётчик до нуля.
Additive backward-compatible изменение внутри cross-cutting файла допускает delta HIL
только с `--delta-review <manifest>`: manifest фиксирует точный SHA-256 каждого
проверенного cross-cutting файла и перечисляет обязательные host checks и соседние
physical scenarios. Устаревший или неполный review fail closed возвращает `full`;
триггеры stage-end, RC и interval отменить им нельзя.

Stage Demo не является маркетинговым роликом: он считается pass только если команды,
логи, бинарный hash и ожидаемые наблюдения позволяют повторить результат.
