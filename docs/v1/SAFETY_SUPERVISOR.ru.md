# ESP32-Leshy 1.x — программный Safety Supervisor

*Читать на: [English](SAFETY_SUPERVISOR.md) · **Русский***

Статус документа: **обязательный software-safety contract S5**. Текущая реализация
не является сертифицированной системой безопасности и не заменяет отсутствующие
power-cut, temperature, voltage и current-monitoring hardware.

## Назначение и граница

Safety Supervisor — общесистемный fail-closed слой ниже приложений. Наблюдаемый
фатальный software fault должен приводить к bounded reset и защёлкнутому Safe Mode,
а не к тихой перезагрузке обратно в обычный режим. Supervisor не принадлежит ни
одной пользовательской функции и не выводит безопасность из работающего UI.

ESP32-DIV v2 позволяет использовать panic-enabled Task WDT ESP32-S3 и принудительно
опускать известный active-high buzzer и все объявленные nRF CE. Подтверждённая схема
не позволяет разорвать rails 3,3/5 В, независимо reset/power-gate CC1101, измерить
температуру cell/rail или доказать физическую остановку радио после смерти MCU.
Недоступные controls всегда остаются явными `false` в diagnostics.

## Машина состояний

```text
startup ── WDT и outputs исправны ──> armed
   │                                    │
   └── WDT/invariant fault ─────────────┤
                                        ↓
                       fatal fault ──> latched Safe Mode
                                        │
                                 OK / вправо один раз
                                        ↓
                                   clear pending
                                 │               │
                         влево отменяет   OK / вправо подтверждает
                                 │               │
                                 └── latched     ↓
                                            clear RTC + restart
```

- У `latched` нет timeout или автоматического снятия.
- Console clear требует точную команду `safety.clear confirm`.
- Обычный UI использует тот же Action path, что physical keys: первое OK/вправо
  запрашивает разблокировку, второе подтверждает; влево только отменяет pending.
- Последующий software/EN/USB reset не очищает принятую exact fault record.
- Полное снятие питания удаляет RTC latch и поэтому является physical intervention.
  Durable журнал incident в NVS переживает снятие питания, но это диагностическая
  история: она не восстанавливает и не заменяет живую safety latch.

## Runtime watchdog

1. Boot устанавливает buzzer LOW и nRF CE LOW до console/display.
2. Узкий watchdog восстановления SD работает под отдельным существующим arm flag.
3. После boot recovery main loop task постоянно подписывается на panic-enabled
   Task WDT с timeout 5 с.
4. Каждый завершённый оборот main loop кормит watchdog. Намеренный тест может
   прекратить feed только на Home без owner/lease.
5. ISR Task WDT отличает arm восстановления SD от runtime arm. При runtime trip он
   прямыми write-one-to-clear регистрами ESP32-S3 опускает GPIO2/14/15/47 и затем
   пишет exact-app retained record.
6. Record публикуется magic-last и содержит value/complement для app identity,
   reason, trip count, quiesce count и latch confirmation. Torn и foreign-app records
   отклоняются.
7. Panic path перезагружает MCU. Свежая runtime record принимается только при
   watchdog-class reset, затем в task context отмечается confirmed. Последующие
   resets сохраняют этот Safe Mode; unconfirmed stale record его не создаёт.
8. Safe Mode пропускает product SD recovery, radio/capture workers и обычные
   Actions. Разрешены diagnostics, TFT capture, evidence-session commands,
   двухшаговый UI clear и exact console clear.

## Durable журнал incident

- ISR не трогает flash или filesystem. Он только quiesce-ит outputs и публикует
  bounded exact-app RTC record, описанную выше.
- На первом безопасном task-context boot валидный watchdog-class RTC incident один
  раз пишется во внутреннюю NVS и проверяется чтением. Маркер sequence не позволяет
  следующим reset дублировать тот же incident.
- Для текущего device profile NVS обязательна. Её verified record сохраняет reset
  reason, triggered CPU mask, firmware identity, page, stage и активный Wi-Fi view,
  даже если SD отсутствует, недоступна, чужая, заполнена или не принимает запись.
- Safe Mode никогда не mount-ит и не пишет карту. Только после явного two-step clear
  и нормального admission exact-CID storage тот же retained incident может быть
  зеркалирован в `/leshy/diagnostics/v1/watchdog-%08lx.json`.
- Зеркало SD выполняется по возможности и атомарно: temporary file записывается,
  sync-ится, закрывается, точно сверяется чтением, rename-ится, снова sync-ится и
  проверяется. Ошибка оставляет NVS record целой и показывает reasoned status; она
  не скрывает исходную причину.
- File и verification buffers FatFS делят один nothrow heap workspace. Ошибка
  allocation сообщает `workspace_unavailable`; unbounded retry отсутствует.

## Контракт outputs

| Output/domain | Действие ISR | Evidence при boot/Safe Mode | Текущая гарантия |
|---|---|---|---|
| buzzer GPIO2 | direct LOW | pad читается LOW | software sound path неактивен |
| nRF CE GPIO14/15/47 | direct LOW | все pads читаются LOW | все объявленные nRF transmit enable неактивны |
| CC1101 | ISR не вызывает scheduler/SPI | в текущем firmware нет TX path; boot возвращает receive/idle adapters только после clear | независимого hard stop нет; будущий TX запрещён без hardware/physical-stop evidence |
| SD/product data | ISR не трогает filesystem | Safe Mode не запускает catalog/mount workers; после explicit clear/restart обычный admission exact-CID разрешает одно atomic зеркало диагностики | safety trip ничего не пишет и не мутирует recovery; NVS остаётся authoritative при недоступной SD |
| power rails | нет действия | `physical_rail_kill_available=false` | rails остаются под питанием |
| thermal/voltage/current | нет действия | availability остаётся false | нет claim over-temperature/undervoltage |

ISR не пишет log, не flush-ит, не выделяет память, не берёт mutex, не вызывает
Arduino adapter и не выполняет SPI/filesystem cleanup. Task-context quiesce
идемпотентен, но ISR от него не зависит.

## Наблюдаемые schemas и автоматический HIL

- `safety.state` выдаёт `leshy.safety.v1`: state/reason, arm/latch/clear, watchdog
  timeout, retained counters, reset reason, pads, owner/lease и явные hardware limits.
- `hardware.safe-outputs` совместимо расширен facts для всех nRF CE и software
  quiesce.
- `safety.watchdog-test confirm` — bounded destructive diagnostic. Он разрешён
  только из нормального `armed` Home без runtime owner/lease и при inactive pads,
  выдаёт flushed arm record и намеренно прекращает feed main-loop WDT.
- `safety.restart-test confirm` разрешён только из защёлкнутого и quiescent Safe
  Mode; он выдаёт flushed proof record и выполняет software reset, не очищая
  retained latch. Это автоматическая проверка persistence, а не пользовательский
  clear path.
- `tools/run_1x_safety_watchdog_hil.py` прошивает один exact candidate, проверяет
  normal arm, вызывает настоящий Task-WDT reset, проверяет retained Safe Mode и
  inactive pads, делает явный output-quiesced software restart и требует сохранения
  latch, снимает оба TFT state, очищает latch через публичный Right/OK Action path и
  доказывает continuity exact CID/catalog плюс final Home lease zero.

Это не simulation: reset transcript обязателен. Отсутствующий reset, invalid record,
automatic recovery, запись storage, неожиданный owner или недоступный final Home —
terminal failure.

Принятый checkpoint board-01: exact `0.103.0-safety-supervisor`, source/runner commit
`2863090`, `E-BUILD-104`/`E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001`. Настоящий panic
Task-WDT reset произошёл через 5 810,775 ms с reason 6; один retained trip/quiesce
пережил software restart с reason 3, сняты три TFT states, catalog 95/0 и exact CID
не изменились, explicit clear завершился на Home с lease zero. В
[machine-checked artifact](../../tests/hil/evidence/board-01-safety-watchdog-0.103.json)
также связаны все negative hardware claims ниже.

Exact physical `1.0.0-dev.376`, `E-BUILD-245`/`E-AUTO-224`/`E-HIL-241`/
`E-SAFETY-089`/`RB-M258`, принимает расширение durable journal. Сохранённый
отклонённый run dev.375 доказывает first-boot persistence NVS и dedup после restart,
затем честно сохраняет отказ stack-canary loopTask в SD path. Dev.376 переносит
workspace FatFS со стека loopTask (`writeSd` 4 496 → 384 B), записывает один incident
reset-reason-6 как sequence 2, откладывает SD в Safe Mode, сохраняет sequence без
второй записи NVS после restart и atomically проверяет одно зеркало на
зарегистрированной exact-CID карте после explicit clear. Run завершается в
Home/armed/none/lease 0. Incident и исправление source-bound в
[privacy-minimal machine-checked artifact](../../tests/hil/evidence/board-01-runtime-watchdog-journal-1.0.0-dev.376.json).

## Принятый калиброванный checkpoint дедлайна Wi-Fi+BLE worker Product Survey

Версия `0.133.0-worker-deadline-supervision` добавила первую supervised worker
границу без изменения layout retained record. Версия
`0.134.0-ble-worker-deadline` калибрует дедлайн реальной Core-0 task Product Survey
до 8 s. BLE adapter публикует exact worst-case двух attempts и одного retry: 6 100 ms
для текущего плана. Compile-time assertion требует, чтобы дедлайн Product Survey
оставался больше этого bound. Task по-прежнему включает дедлайн только после
admission и подготовки scanners. Heartbeat стоит вокруг UI start gate, каждого
blocking Wi-Fi/BLE scan и bounded inter-scan wait; disarm происходит только после
cleanup scanner/filesystem.

Main loop оценивает это независимое состояние до обычных worker events. Expiry
запрашивает cancel обоих scanners, снимает foreground application lease, удерживает
software-controlled outputs inactive и защёлкивает `worker_deadline` в том же
exact-app RTC record, что использует main-loop watchdog. Test-only команда
`safety.worker-deadline-test confirm` лишь взводит одноразовую задержку 10 s;
реальный worker запускается обычным public Survey Start.

Exact 0.133 HIL board-01 принимает fault path **Wi-Fi → Сети рядом**. Exact 0.134
теперь принимает normal и fault paths **Bluetooth → Устройства рядом**. Normal
lifecycle завершает один BLE cycle/attempt, принимает 34/34 observations, фиксирует
zero drops/transient retries и не срабатывает, затем очищается до owner/lease
`none`/`0`. Второй lifecycle взводит тот же worker, внедряет stall 10 s и срабатывает
один раз на возрасте 8 001 ms при дедлайне 8 000 ms; cumulative arm/heartbeat/trip
равны 2/8/1. Cancel/cleanup завершается, buzzer и nRF CE остаются inactive, а
retained latch `worker_deadline` переживает software restart с reason 3. Safe Mode
переходит `latched` → `clear_pending` только после первой публичной Action Right/OK,
очищается и перезапускается только после второй и возвращается на Home с
неизменными exact CID, catalog 98/0 и zero physical storage writes. Три TFT state
240×320 и exact hashes source/image/runner/transcript связаны в
[machine-checked artifact](../../tests/hil/evidence/board-01-worker-deadline-0.134.json).

Exact `0.135.0-survey-preparation-deadline` добавляет отдельный supervisor 8 s от
public Start transition через card identity, read-only filesystem/store checks,
scanner startup и admission. Heartbeat обрамляет каждый bounded retry/wait и каждую
hardware boundary; calibrated worker взводится только после disarm preparation.
Test-only `safety.worker-preparation-deadline-test confirm` внедряет одну задержку
10 s до любой hardware operation подготовки. Normal BLE lifecycle сначала взводит
preparation, затем worker и принимает 30/30 observations за одну attempt с zero scan
drops/retries. Injected lifecycle срабатывает на preparation через 8 001 ms с
cumulative arm/heartbeat/trip 3/18/1 и сохраняет тот же quiesce, retained latch,
two-action clear, exact CID/catalog и final Home/lease-zero contract. Exact
source/image/runner/transcripts и три TFT state сохранены в
[machine-checked artifact](../../tests/hil/evidence/board-01-worker-preparation-deadline-0.135.json).

Checkpoint не покрывает остальные long-lived workers, будущие transmit leases,
retained state при полном снятии питания или physical rail/radio kill.

## Открытая safety-работа

- расширить принятый Product Survey slice на каждый другой long-lived worker и
  будущие transmit leases;
- направлять driver invariant, brownout/thermal и storage safe-shutdown faults в ту
  же reasoned latch только после появления надёжных sensors;
- для любого будущего active-radio profile добавить внешний rail/PA kill либо load
  switch и reset/power gate CC1101;
- измерить GPIO reset/pull и physical RF stop независимыми приборами;
- включить destructive watchdog check в Full/Guided Self-Test и final S8 release
  manifest, сохранив Quick read-only.
