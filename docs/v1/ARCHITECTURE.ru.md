# ESP32-Leshy 1.x — целевая архитектура

*Read in: [English](ARCHITECTURE.md) · **Русский***

Статус документа: черновик целевой архитектуры чистой линии 1.x. Прошивка 0.x заморожена как
отдельный PoC и источник проверенного аппаратного знания. 1.x не зависит от её
`main.cpp`, дерева меню и глобального состояния. Низкоуровневый фрагмент может быть
переиспользован только после выделения в контракт 1.x и отдельного теста.

Обязательные уточнения этого draft находятся в
[индексе accepted ADR](adr/README.ru.md). При конфликте accepted ADR имеет приоритет
над общим текстом architecture.

## 1. Почему меняем

На исходной точке `main.cpp` содержит 3181 строку и одновременно отвечает за дерево
меню, глобальные состояния, отрисовку экранов, запуск/остановку драйверов, radio
coexistence и serial QA. Модули сканирования уже отделены лучше, но их жизненный цикл
вручную дублируется в `launch()`, `back()`, serial-командах и основном `loop()`.

Это создаёт четыре системных риска:

- новый экран требует изменений в нескольких больших `switch`;
- пропущенный `stop()` оставляет radio/TX/portal активным;
- физические конфликты пинов известны отдельным драйверам, но не системе;
- почти всю логику можно проверить только сборкой или на реальном устройстве.

При этом используем рабочие достижения 0.x — неблокирующий UI, background scan, OTA
с rollback и аппаратные операции — как reference implementation и тестовые
свидетельства. В 1.x переносится только минимальный низкоуровневый код после
выделения в новый контракт и проверки; legacy screens и lifecycle не оборачиваются.

## 2. Слои

```text
apps/              Survey · Targets · Wi-Fi · BLE · Sub-GHz · IR · NFC · GPS · Lab
sdk/               Application · events · views · capture API · safety API
services/          observations · sessions · library · settings · OTA · diagnostics
kernel/            SafetySupervisor · AppRuntime · Navigator · ResourceBroker · scheduler
drivers/           Wi-Fi/BLE · NRF24 · CC1101 · PN532 · GPS · IR · SD · display/input
boards/             pin map · electrical conflicts · build flags · capability probes
platform/           Arduino-ESP32 / FreeRTOS adapters
```

Зависимости направлены вниз. Драйвер не открывает экран, приложение не вызывает
чужой драйвер и не меняет глобальное состояние, сервис не знает о TFT.

## 3. Профиль платы и capabilities

Нормативный design-time источник —
[`HARDWARE_ENVELOPE.ru.md`](HARDWARE_ENVELOPE.ru.md). Он содержит evidence,
физическую GPIO-карту, варианты комплектации, безопасный probe и открытые вопросы.
`src/boards/esp32_div_v2/BoardProfile.h` — версионируемая реализация принятой части
этой карты, а не независимый источник фактов.

`HardwareInventory` хранит для каждой возможности состояние `declared`, `detected`,
`available`, `conflicted`, `fault` или `unknown`, а также evidence и причину. Он
разделяет:

- main-board устройства: ESP Wi-Fi/BLE, display/touch, keypad, LEDs, buzzer и SD slot;
- съёмный RF shield: три NRF24, CC1101 и IR;
- внешние взаимоисключающие assembly: GPS и PN532, отсутствующие в v2 schematic/BOM;
- результат безопасного probe на этой конкретной загрузке.

Совместимая маска `available` вычисляется из inventory только после resource policy.
Реестр не запускает недоступное приложение; Diagnostics показывает ожидаемую
комплектацию, probe evidence, конфликт или fault. Неидентифицируемое цифровым probe
устройство не становится `detected` только потому, что оно нарисовано на схеме.

### Важные конфликты ESP32-DIV v2

| Домен | Общие линии |
|---|---|
| display SPI | TFT и touch физически делят GPIO 35/36/37; CS 17/18, транзакции сериализуются |
| radio/storage SPI | SCK 12, MISO 13, MOSI 11: NRF24, CC1101, SD; PN532 разворачивает data direction на 11/13 |
| CC1101 / GPS / PN532 | GPIO 5/6 имеют разные направления; автоперебор output modes запрещён |
| NRF24 slot 3 / IR | GPIO 21/14 используются как NRF CSN/CE и IR RX/TX |
| buzzer / battery | GPIO2 одновременно управляет buzzer transistor и является серединой VBAT divider |
| TFT reset / BOOT | schematic ведёт TFT RESET к RESET/EN, legacy flags задают GPIO0; до HIL reset считается внешним |
| memory / display | GPIO35–37 display несовместимы с Octal-PSRAM variants; BOM указывает N16 без PSRAM |

Наличие обоих модулей не означает, что они могут работать одновременно. Это
описывается ресурсами, а не случайным порядком `begin()`/`end()`.

## 4. Runtime приложений

Каждое приложение реализует один контракт:

```cpp
struct AppDescriptor {
    OwnerId id;
    const char* key;                 // стабильный: "subghz.spectrum"
    CapabilitySet requiredCapabilities;
    ResourceSet requiredResources;
    SafetyLevel safety;
};

class Application {
public:
    virtual bool onStart() = 0;
    virtual void onEvent(const AppEvent&) = 0;
    virtual void onTick(uint32_t nowMs) = 0;
    virtual void onStop() = 0;
};
```

`AppRuntime` проверяет capabilities, атомарно получает ресурсы, запускает приложение
и гарантированно освобождает lease после `onStop()` или неудачного `onStart()`.
Приложение не может «забыть» сообщить меню, как остановить его радио.

`Navigator` хранит стек экранов и выбор на каждом уровне. Back — системное событие,
а не ветка в каждом экране. Модальные диалоги и дочерние views добавятся поверх того
же стека.

Touch adapter загружает versioned calibration из NVS и умеет read-only импортировать
legacy-запись 0.x `leshy/tcal`. Allocation-free frontend выдаёт событие по edge и
использует release debounce 35 ms. Общий geometry mapper принимает только видимые
rectangles Home/choice и превращает hit в bounded перемещение selection плюс
`Select`; header/footer ничего не dispatch-ят, а touch не может синтезировать Back.

### Safety Supervisor

`SafetySupervisor` — kernel boundary ниже apps, UI, drivers и product recovery.
Panic-enabled Task WDT следит за каждым завершённым оборотом main loop. Его IRAM
handler может только опустить известные pads buzzer/nRF CE и опубликовать exact-app,
torn-write-resistant RTC record; он не пишет log, не выделяет память, не ждёт и не
трогает SPI. Watchdog reset входит в защёлкнутый Safe Mode, пропускающий product
workers и normal Actions. Второй reset сохраняет уже подтверждённую защёлку. Снять
её можно только явным двухшаговым user clear с restart. Exact 0.133 впервые добавляет
allocation-free дедлайн реальному worker Product Survey после подготовки scanners.
Exact 0.134 калибрует его до 8 s и compile-time assertion удерживает его выше
текущего bounded worst case BLE adapter 6,1 s для двух attempts и одного retry.
Main-loop evaluation идёт до обычного worker service; expiry отменяет оба scanner,
снимает application lease, глушит software outputs и входит в тот же retained Safe
Mode с reason `worker_deadline`. Публичные пути Wi-Fi «Сети рядом» и BLE «Устройства
рядом» приняты физически. Exact 0.135 добавляет отдельную boundary 8 s через identity
Product Survey, read-only проверки storage/store, startup scanners и admission с
bounded heartbeat и physical fault injection до hardware preparation. Остальные
workers и physical rail/radio shutdown остаются открыты. Обязательный
контракт — [`SAFETY_SUPERVISOR.ru.md`](SAFETY_SUPERVISOR.ru.md).

## 5. Ресурсы и coexistence

`ResourceBroker` не аллоцирует память и выдаёт набор ресурсов атомарно. Имена и
границы hardware domains берутся из `HARDWARE_ENVELOPE`. Первая версия использует:

- `spi_display` для TFT/touch и `spi_radio` для SD/NRF/CC;
- `mux_5_6`, `mux_nrf3_ir` и `gpio2_battery_buzzer`;
- `i2c_control`, `storage`, `console` и `esp_rf`;
- device-level leases NRF24 array, CC1101, NFC, GPS UART и IR;
- network stack, filesystem и ограниченные buffer pools.

Сначала `spi_radio` выдаётся как эксклюзивная operation lease. Более тонкое
transaction sharing разрешается только после HIL и endurance evidence. GPS/PN532
доступны лишь в явном assembly profile; неоднозначность GPIO5/6 делает все три
варианта недоступными, а не запускает экспериментальный probe.

Следующий шаг добавит управляемые сервисы поверх broker: например Wi-Fi STA может
жить фоном, пока foreground-приложение просит совместимый scan slot. Это будет явная
таблица режимов, а не предположение приложения.

TX-lease получает deadline. По таймауту, panic/back или watchdog kernel сначала
вызывает аппаратный `stopTransmit()`, и только потом закрывает UI.

## 6. События и задачи

- Core 1: UI, Navigator, `Application::onEvent/onTick`; ни один callback не блокирует
  более чем на 10 мс.
- Core 0: ограниченные radio/storage workers. Они публикуют immutable snapshots или
  bounded events; TFT из worker не вызывается.
- ISR: только timestamp/edge в заранее выделенную очередь.
- Долгая операция получает cancel token и публикует progress.

Очереди имеют фиксированный размер и счётчик dropped events. После boot steady-state
код не должен полагаться на частые `String`/heap allocations; большие буферы принадлежат
сервисам и повторно используются.

До закрытия `HW-U01` обязательный бюджет не предполагает PSRAM. Boot diagnostics
фиксирует chip/package/revision, фактический flash, partition table и результат
`psramFound()`; отличие от assembly profile является fault, а не поводом молча
поменять memory policy.

Объединять большие workspaces разрешено только тогда, когда resource broker делает
их owning lifecycle взаимоисключающими. Exact 0.136 совместно использует состояние
Survey/diagnostic Session и workspaces product/diagnostic FatFs под существующими
exclusive lifecycle и ownership Storage+RadioSpi; публичный Capture Store обязан
публиковать free heap, largest block и точную ошибку mount до работы с накопителем.
`E-HIL-157` доказывает, что это возвращает no-PSRAM headroom mount и не позволяет
fault-injected worker выполнить write.

Source ingress никогда не ждёт filesystem durability barriers. Каждый receiver
публикует normalized Observations в fixed-capacity ring, которым владеет Survey
service; storage worker забирает bounded batch в текущий segment и публикует новый
atomic head только по explicit Stop, threshold размера/времени или safe-shutdown
request. Queue depth, high-water mark и drops входят в Session evidence. E-HIL-037
измеряет passive Wi-Fi p99 546 encoded B/s и поэтому задаёт первую цель RB-06 storage
2 184 B/s. Fixed batch E-HIL-038 даёт 9 068 B/s, а real
Wi-Fi→FIFO→SessionStore path E-HIL-039 — 6 921 B/s при high-water 9/64 и zero drops.
E-HIL-040 повторяет этот path до обычной Library/export: 12 957 B/s, high-water
18/64, zero drops, recovered generation 1/52 observations и persistent/real
provenance в List/Detail/Export. Этот результат был sequential diagnostic command.
Version 0.59 закрывает gap product-worker integration: одна persistent task на Core 0
владеет source/storage work за bounded очередями events/observations (8/64), а Core 1
владеет и drain `SurveyPipeline`. UI callbacks Start и Stop только ставят intent в
очередь и возвращаются; измеренные callbacks занимают 13/10 us. Source остаётся
активным в List и Detail, а E-HIL-084 фиксирует progress с 14 observations/одного scan
до 27/двух scans при открытом Detail, high-water 10/64 и zero drops. Durability work
начинается только после остановки source; boot-time catalog recovery остаётся
отдельным read-only path.

Саморевью затем нашло одну race terminal state: worker выставлял `Idle` сразу после
enqueue Failed/Cancelled/Stopped, до обработки terminal event на Core 1. Version 0.60
делает UI единственным terminal acknowledger. Worker сохраняет non-idle control state,
пока Core 1 не завершит cancellation cleanup или commit cleanup; только после этого
разрешён следующий Start. Static contract отклоняет worker-side transition в `Idle`,
а E-HIL-085 повторяет exact physical normal path через generation 67→68 с 25/25
forwarded, zero drops, read-only reboot/export и final lease zero.
Version 0.62 делает интервал blocking scan worker наблюдаемым и snapshot этого state
при запросе Back/cancel. E-HIL-086 ждёт реальный active passive scan, затем доказывает
переход request в `cancelling`, закрытие source/backend, отсутствие новой generation и
cold reopen неизменной Library 68/25 с zero writes/leases. Предыдущий run 0.61 сохранён
как failed: второй cold boot потерял единственный read PCF8574. Boot теперь делает не
более восьми reads с интервалом 5 ms и публикует attempts/retries; deliberate injection
первого failed read остаётся дополнительным evidence.

Product activation выделена в отдельную fail-closed boundary. `ProductStorePolicy`
фиксирует единственный текущий product root `/leshy/sessions/v1`: automatic catalog
recovery требует уже enrolled exact media fingerprint, existing root, гарантированно
read-only non-writable driver и ownership Storage+RadioSpi. Initialize/commit
дополнительно требуют explicit user selection, writable driver и bounded size/reserve.
Затем `ProductSurveyAdmission` требует explicit Start, validated passive plan,
writable commit permit и combined ownership EspRf+Storage+RadioSpi. Запрошенная
real/persistent Session никогда молча не заменяется simulated/RAM. Сами политики не
выполняют I/O. В board lifecycle 0.44 NVS хранит только exact 32-character CID;
под lease 12 card идентифицируется, FAT монтируется с disabled format, diskio write и
trim callbacks заменяются на `RES_WRPRT`, открывается только fixed product root,
последняя valid generation staged в Library, затем mount и все resources освобождаются.
Recovery намеренно проверяет raw card capacity без `f_getfree` и filesystem-capacity
query: boot не требует free space, а scan большой FAT сделал бы latency зависимой от
размера media. Enrollment сохраняется только после такого же read-only recovery;
unenrollment удаляет только CID из NVS и вообще не обращается к SD. Initialize/commit
остаются explicit writable operations.

Version 0.45 впервые соединила admission с interactive product Survey, не меняя
un-enrolled simulated fixture. AppCatalog предпочитает
`survey.persistent_passive` только после
boot recovery exact media и атомарно запрашивает UI+EspRf+Storage+RadioSpi (lease 15).
Explicit Start заново идентифицирует CID, монтирует writable с disabled format,
использует только cached FAT/FSInfo free-cluster hint, допускает commit 64 KiB с reserve
1 MiB и направляет allocation-free workflow в product store. Credential-free Wi-Fi
adapter в 0.59 выполняет только passive scans в persistent bounded worker, умеет
останавливать активный scan и не вызывает connect/configuration/raw-TX API. Stop
сначала запрашивает остановку worker/source, затем публикует и reopens ровно следующую
generation до замены Library; каждый exit закрывает store/mount и возвращает workflow
на RAM. Back из Running cancels без commit и сохраняет prior Library. Нормальный path
Start→live List/Detail→Stop→commit→read-only reboot/export и финальный zero-lease
cleanup физически принят в E-HIL-084. Version 0.60 дополнительно удерживает ownership
control worker до UI terminal acknowledgement, не позволяя новому Start обогнать
старый terminal event; E-HIL-085 подтверждает неизменный normal hardware path.
E-HIL-086 теперь закрывает physical cancel во время active scan без commit/leak.
Version 0.68 добавляет one-shot release-test fault на реальной границе source.
E-HIL-092 доказывает, что недоступный passive source показывается как локализованный
terminal TFT state только после cleanup и release lease: source start и store open
равны false, создано zero bytes/observations, Select не делает скрытый retry, Back
возвращает Home, а cold read-only recovery сохраняет generation 68 и 25 observations.
На этой точке evidence physical power-cut, endurance, LittleFS parity и independent
demo goldens оставались открыты; normal/remount slice LittleFS принимается 0.69 ниже.

Version 0.69 добавляет HIL-only backend LittleFS без изменения product partition map.
Он принимает только inactive OTA1 `app1` по `0x410000`/4 MiB, доказывает, что running
и boot apps находятся в другом месте, а product `spiffs` не пересекается с target,
затем требует exact host-provided SHA-256 всего partition до format. Common
`SessionStore` использует confined POSIX adapter под
`/hil-lfs/leshy-hil/<run-id>`; file `fsync` служит durability barrier metadata/directory
LittleFS. E-HIL-093 доказывает 32 commits, read-only remount recovery и throughput,
а host — two-read backup, exact restore OTA1/table и unchanged product Library.
Version 0.70/E-HIL-094 затем закрывает все шесть software-reset boundaries LittleFS
с typed read-only recovery и one-write exact restore. `E-HIL-095`/`E-GATE-003`
закрывает S3 на том же exact candidate 0.70: generation 69→70, 29/29 observations,
cold reopen/export и пять independent TFT matches. S4 теперь активен; physical
power-cut и multi-source endurance остаются его explicit gates.

Первый пользовательский slice S4 — exact `0.71.0-survey-source-plan`
(`E-HIL-096`/`E-SURVEY-009`). Allocation-free `SurveySourceController` проецирует
boot inventory в draft plan UX-S02 отдельно от исполнения drivers: выбрать можно
только source со state `available`, пустой real plan не запускается, declared BLE
остаётся видимым с причиной unavailable. Навигация Plan/Sources использует общие
Actions и incremental renderer; выход из Setup освобождает foreground lease. Это
стабильная UI/domain граница для следующих shared timeline и passive BLE, а не claim
готовности BLE driver или `DEMO-S4`.

Exact checkpoint `0.72.0-source-timeline-runtime` добавляет первую общую модель
radio time и подключает её к selected plan и real product worker. `SourceTimeline`
владеет двумя fixed source slots и потоково отдаёт завершённые окна scheduled,
active, unavailable и fault через FIFO на 16 записей. Для каждого source сохраняются
64-bit accepted/drop counters и накопленные durations, duty cycle выдаётся в
permille, out-of-order transitions и неверные пары state/reason отклоняются. При
полной FIFO текущее состояние не меняется, а overflow явно считается. Host contracts
покрывают overlapping Wi-Fi/BLE windows, временную недоступность BLE driver,
observation drops, terminal accounting, FIFO drain/retry и overflow-safe stop.
Worker events ScanStarted/Scan/terminal теперь управляют Wi-Fi windows, каждое
accepted/dropped observation обновляет тот же monotonic ledger, а Running UI показывает
текущее состояние Wi-Fi и долю duty. Exact `E-HIL-097` подтверждает два real scan
cycles, 34/34 accepted/forwarded observations, 4→5 completed windows, zero
drops/overflow, terminal close, generation 71→72, exact-CID cold recovery и final
lease 0. Приняты только runtime integration и visibility: persistence schema v1 всё
ещё хранит observations без timeline windows, поэтому FIFO пока не дренируется durable,
а полная queue остаётся намеренным fail-closed short-run bound.

Exact `0.73.0-source-timeline-persistence` закрывает эту persistence boundary без
поломки существующих sessions. SessionCodec schema v2 добавляет CRC-bound timeline
record, а schema v1 остаётся byte-for-byte читаемой. Product worker немедленно
дренирует каждое завершённое runtime window в bounded ring `SurveySession` на 16
окон с явными total/evicted counters и per-source summaries; incomplete или invalid
timeline блокирует commit. Stop завершает timeline до публикации generation 73→74.
После cold Library reopen экспортирует `leshy.session.summary.v2` и retained ordered
`timeline_windows` с source/state/reason, точными monotonic bounds и accepted/drop
counters. Exact `E-HIL-098` доказывает 21/21 observations, пять windows, zero FIFO
backlog/overflow/drops, cold reopen и final lease 0. Управляемый power-cut schema v2
и длительный multi-source endurance остаются отдельными gates `DEMO-S4`.

Exact `0.74.0-passive-ble` добавляет второй real source без ослабления этих
boundaries. Bounded Arduino BLE scan потоково передаёт каждое advertisement прямо в
общий Observation pipeline и сразу удаляет его из library map, поэтому высокая RF
плотность не создаёт неограниченно растущую таблицу retained devices. Wi-Fi и BLE
scans остаются serialized в product worker; binary start gate заставляет worker
опубликовать, а UI task — принять timeline boundary `ScanStarted` до того, как driver
сможет передать observation, сохраняя cross-queue monotonic ordering. SessionCodec v2
принимает BLE observations с нулевыми channel/frequency, сохраняя exact decode schema
v1, а Library summary экспортирует явные per-source counts. Exact `E-HIL-099`
доказывает один real Wi-Fi и один real BLE cycle, 6+34 observations, generation
76→77, шесть ordered persisted/exported windows, zero drops/overflow, exact-CID cold
recovery и final lease 0. Следующий exact slice принимает injected
unavailable/fault recovery.

Exact `0.75.0-runtime-degradation` закрывает этот срез pure decision boundary между
driver results и product state. Unavailable или faulted source удаляется из active
mask и получает явные timeline state/reason; Session продолжается только пока остаётся
другой compatible selected source. Последующие успешные scans не могут стереть
`running_degraded`. Diagnostic one-shot может подменить следующий driver result только
в Home/idle и сообщает, что не коснулся hardware или storage. Exact `E-HIL-100`
инъекционно делает BLE unavailable, затем доказывает, что два real Wi-Fi cycles всё
ещё дают 28 observations, сохраняет восемь windows, включая 3 625 744 us BLE
`driver_unavailable`, cold-reopens/экспортирует их при zero fault time, zero drops и
final lease 0.

Exact `0.76.0-observation-browser` добавляет общий allocation-free Survey browser
поверх retained Observation records. Фильтры Все/Wi-Fi/BLE отображают visible rows
обратно в ту же bounded session без копирования records; List открывает radio-neutral
Detail и историю RSSI до 12 samples. Перевод focus к просмотру запрашивает snapshot,
которым владеет worker: активный RF source останавливается, timeline финализируется,
а storage backend остаётся под ownership до Save или Cancel. Так ожидание пользователя
не переполняет Session на 64 observations, а browser остаётся read-only. `E-HIL-101`
доказывает полный real Wi-Fi+BLE cycle, 8+37 observations, точные filter counts,
RF-off pause, commit generation 80→81, cold reopen/export, девять TFT captures, zero
drops/overflow и final lease 0.

Exact `0.77.0-capture-export` переводит atomic Session format на schema v3, сохраняя
byte-compatible v1 и readable v2. Fixed CRC-covered Capture record записывается перед
observation и timeline records. Он связывает producing app ELF, selected source mask и
точные passive Wi-Fi/BLE receive plans; отсутствие location и raw-frame payload
представляется явно, а не выводится косвенно. Library показывает этот immutable
provenance, сохраняет контракт JSON summary v2 и потоково выдаёт canonical CRLF CSV по
одной bounded row. Bytes identity и label кодируются lower-case hex, поэтому export
детерминирован и binary-safe без второй Session-sized allocation. Текущие scan drivers
сохраняют normalized observations, а не raw 802.11/BLE frames, поэтому PCAP возвращает
typed результат `unavailable_no_frame_payload`, не фабрикуя packets. `E-HIL-102`
доказывает generation 81→82, 16+31 observations, exact metadata, CSV на 47 rows, cold
recovery, десять TFT captures, invariant heap, zero drops/overflow и final lease 0.

Exact `0.78.0-wifi-frame-capture` добавляет отдельный packet path, не меняя модель
Observation. `WifiFrameCapture` владеет fixed store на 16 frames с snap bound 256 B;
Arduino adapter входит в STA promiscuous receive без NVS persistence, application
connect или raw TX и проходит явный план каналов 2,4 GHz. Stop сначала отключает
driver и освобождает Radio, затем замораживает bounded frames для streaming PCAP 2.4
writer. Каждая record содержит 15-byte radiotap header с flags, channel и RSSI, за
которым идут захваченные 802.11 bytes; writer не создаёт второй payload buffer.
Capture по умолчанию volatile, не пишет storage, а Back обнуляет store до release UI.
`E-HIL-103` доказывает 34 reported/16 retained real frames, payload 4 096 B, 18
учтённых capacity drops, разобранный PCAP 16 records/4 616 B, пять TFT states,
read-only prior Session, scrubbed RAM и final lease 0.

Exact `0.79.0-persistent-frame-capture` продолжает тот же bounded source через один
atomic storage path. Session schema v4 добавляет CRC-covered fixed frame block `LWFC`
и Capture metadata v2, сохраняя decoding v1–v3. Save — отдельное действие пользователя
с явным privacy confirmation для raw identities. Background worker проверяет exact
enrolled CID, владеет Storage+RadioSpi только во время commit, публикует одну новую
generation, fail-closed открывает её снова и освобождает ресурсы до подтверждения UI.
`PersistedWifiFrameCaptureView` читает существующий SessionStore workspace 12 KiB
напрямую, поэтому Library PCAP не создаёт второй frame-payload buffer. Back scrub-ит
volatile capture RAM, но не удаляет явно сохранённый artifact. `E-HIL-104` доказывает
generation 82→83, 16 records/2 253 payload bytes, равенство live/cold PCAP 2 773 B,
read-only recovery, invariant heap, девять TFT states и final lease 0.

Exact `0.80.0-self-test-coverage` превращает capability registration в явную
architecture boundary вместо вывода о здоровье из доступности меню. Boot inventory
facts проецируются в plan-v3 `SelfTestFacts`; один deterministic engine выдаёт ordered
checks readiness/persistence завершённых S3/S4, optional assembly declarations
становятся `not_applicable`, незавершённые receiver contracts — `blocked`. Один report
управляет TFT и independent HIL oracle, фиксирует zero side effects и удерживает только
UI lease. `E-HIL-105` доказывает 15 pass/0 fail/2 blocked/3 N/A и final lease 0.

Exact `0.81.0-shield-receiver-probe` добавляет узкий hardware adapter под этим pure
plan engine. Он вызывается только из подтверждённого пользователем Full/Guided, пока
foreground owner владеет `RadioSpi`; boot и Quick его не вызывают. Adapter удерживает
nRF CE LOW, читает только четыре identity/config register у slots 1/2, никогда не
выбирает slot 3/GPIO21 и читает у CC1101 только status PARTNUM/VERSION. Pure contract
отклоняет floating/partial identities, конфликты profile/resource, любое CE-high/
strobe/TX event или incomplete cleanup. `E-HIL-106` связывает exact 8 nRF reads,
2 CC reads, 20 SPI bytes, три detected receivers и final lease 0. Это identity
boundary, а не passive observation pipeline или physical RF-silence measurement.
Эти workflows, active Full/Guided execution, controlled physical power-cut и
endurance gate ≥45 минут/≥8 циклов в часовом операционном бюджете остаётся работой
`DEMO-S4`.

Exact `0.82.0-nrf24-spectrum` строит первую полезную workflow shield поверх этого
identity boundary, не связывая UI rendering со SPI. Pure
`Nrf24SpectrumController` владеет plan на 83 bins и состояниями pause/resume/stop;
только Arduino adapter владеет register sequence двух receivers, dwell 200 us и
safe cleanup. `SurveySourceController` лишь отображает typed Actions и проецирует
volatile snapshot в localized live chart, обновления которого ограничены областью
графика. `E-HIL-107` доказывает 21 полный sweep 2 402…2 484 МГц, стабильный paused
counter, exact accounting receive windows, zero TX/CC/storage side effects, invariant
heap/storage и final lease 0. RPD bins показывают threshold activity, а не calibrated
power; physical RF silence не измерен.

Exact `0.83.0-cc1101-spectrum` применяет то же разделение к Sub-GHz RSSI, не копируя
wire model nRF. Pure `Cc1101SpectrumController` владеет четырьмя band plan по 64 bins
и состоянием interaction. `BoardCc1101PassiveSpectrum` выполняет только один bounded
sample за проход main loop, разрешает strobes reset/RX/idle, ждёт RX ready не больше
3 000 us, наблюдает 500 us и возвращается в IDLE; операций TX, PATABLE или FIFO у него
нет. UI перерисовывается только после полного sweep. `E-HIL-108` доказывает все четыре
диапазона, стабильную pause 400 ms, exact wire accounting, zero TX/storage side
effects, invariant heap/storage и final lease 0. Значения — некалиброванный RSSI,
physical RF silence не измерен.

Принятый display contract `0.99.0-wifi-spectrum-modes` использует clock завершённых
измерений, а не wall-clock UI timer. Active pure controller публикует монотонный
counter законченных sweep; Arduino layer потребляет каждое новое значение один раз и
сохраняет текущий полный spectrum как одну физическую строку fixed eight-bit raster
240×224. Jump counter больше единицы сохраняется как failure skipped measurement,
поэтому renderer не может незаметно повторить stale/partial snapshot ради визуальной
скорости. Raster имеет разрешение экрана, а не приёмника: 83 bin nRF и 64 bin CC
попадают в соседние columns без interpolation вымышленных измерений. Поэтому time
axis определяется возможностями приёмника. По умолчанию выбраны все найденные nRF
slot; header показывает активный receive set, а Сигнал и Трафик остаются отдельными
display metrics. После начального chrome render обновляется только новая строка
графика. `E-HIL-124` связывает source/candidate, шесть full-history paths с zero
skipped, 17 TFT states, unchanged storage и final lease 0. Это по-прежнему software
receive-only evidence, не calibrated RF и не instrumented physical-silence evidence.

Принятый refinement `0.100.0-spectrum-source-history` разделяет физическое
разрешение display и сохраняемое разрешение приёмника, не меняя timing contract.
Каждая из 224 строк history теперь занимает 83 bytes — максимальную реальную ширину
source — вместо 240 уже развёрнутых display bytes. nRF хранит все 83 bin, CC — свои
64 bin и очищенный хвост; `intensity(row, column)` выбирает ближайший реальный source
bin только при render scanline 240 px. Горизонтальной interpolation, averaging или
дополнительного измерения нет, а физический результат остаётся одним законченным
sweep на строку 1 px. Fixed history уменьшается с 53 760 до 18 592 bytes, static RAM
— с 205 296 до 170 128 bytes. `E-HIL-125` связывает шесть paths с zero skipped,
максимальный render строки 611 us, все три nRF slot, zero retry/recovery CC,
stabilized heap 211 580/146 472/127 120 B, unchanged storage и final lease 0.

Exact `0.84.0-full-guided-rf` делает эти два receiver contract исполняемыми из
plan-v5 Full/Guided, не превращая boot или Quick в active. Orchestration показывает
cancellable boundary 500 ms, один раз получает `RadioSpi`, завершает bounded sweep
двух nRF24, затем продвигает CC1101 по одному bin за проход main loop до release и
итогового report. Stable active-check IDs и `leshy.self_test.active_rf.v1` отделяют
device progress от independent host oracle. `E-HIL-109` доказывает Quick 8/8, Full
18 pass/0 fail/1 blocked/3 N/A, exact wire accounting, zero TX/storage side effects,
11 real TFT states и final lease 0. Первый mismatch equation runner сохранён fail
closed. Physical RF silence и active execution остальных Survey/Library/Capture
workflows остаются открыты.

Exact `0.85.0-full-guided-artifacts` переводит Full/Guided на plan v6, сохраняя
Quick read-only и строго последовательное владение radio/storage. После cleanup
RF-adapters и release `RadioSpi` отдельная cancellable data boundary 500 ms получает
`Storage|RadioSpi`, заново идентифицирует enrolled CID, монтирует его read-only и
повторно использует boot recovery path для последней atomic Session. Staged discard
sinks затем проверяют Library JSON, capture metadata, по одной CSV record за проход
main loop и, когда сохранённые raw frames существуют, streaming radiotap PCAP без
создания или замены пользовательских данных. Stable check IDs и
`leshy.self_test.active_artifact.v1` публикуют recovery, bytes/records/hash exporters
и final cleanup независимому oracle. `E-HIL-110` доказывает Quick 8/8 и Full 21
pass/0 fail/1 blocked/3 N/A, unchanged generation 83, PCAP 16 records/2 773 B,
zero storage writes/TX events и final lease 0. Первый run с обрезанным расширенным
`ui.state` сохранён fail closed; bounded diagnostics workspace затем увеличен до
4 608 bytes, а исправленный exact candidate прогнан заново. Создание новой
disposable Survey/Capture, controlled physical power-cut и endurance остаются
открыты.

Exact `0.86.0-full-guided-disposable` переводит эту boundary в plan v7. После
read-only artifact audit отдельные short-lived leases `Storage|RadioSpi`
идентифицируют тот же enrolled CID, разрешают только
`/leshy-hil/full-guided-v7`, commit-ят deterministic Session из трёх observations с
finalized capture timeline, освобождают ресурсы, read-only remount-ят и экспортируют
её, затем снова получают ресурсы для typed exact cleanup. Финальный read-only
product recovery подтверждает неизменную generation 83/0. Failed candidate без
timeline и исправленный pass сохранены; только второй записывает три files/504 bytes
и затем удаляет их. Controlled physical power-cut и endurance в пределах часа
остаются открыты.

Exact `0.87.0-full-guided-heap-budget` закрывает defect достоверности/budget
diagnostics, обнаруженный 0.86. Storage line 4 608 bytes и diagnostic JSON buffer
5 120 bytes никогда не выполняются одновременно в single main-loop command path,
поэтому теперь используют один workspace 5 120 bytes. Full/Guided также очищает и
перестраивает ordered report из final facts; падение heap к концу run больше не может
сохранить healthy result preflight. Native injection ниже floor даёт fail, board-01
проходит с 133 884 B против 131 072 B.

Exact `0.101.0-power-cut-harness` закрывает последнюю durability boundary S4
отдельным protocol, а не скрытым boot behavior. `power-cut disposable-write`
готовит только typed exact-CID scratch Session, достигает одной из тех же шести
boundaries SessionStore, выдаёт flushed arm record и ждёт, подкармливая watchdog.
`esp_restart` не вызывается. Host доказывает реальное исчезновение USB минимум на
три секунды, отслеживает те же serial/VID/PID через re-enumeration и затем вызывает
отдельный `power-cut-recover disposable-read-only`. Firmware допускает этот path
только для `ESP_RST_POWERON`; recovery не может писать, форматировать, перечислять
product names или читать product data. Board-01 проходит все шесть boundaries как
generations 1/1/1/1/1/2 с unchanged prior CRC, zero recovery writes/syncs и lease 0.
Fixture переиспользует отдельный diagnostic Session workspace, поэтому static RAM
остаётся 170 128 B, product generation 95/0 не меняется. Вместе с endurance exact
0.89 это закрывает S4; теперь S5 расширяет те же broker/storage/observation contracts
на каждый штатный модуль.

Exact `0.115.0-wifi-device-intelligence` сохраняет path «Устройства Wi-Fi» пассивным
и bounded, разделяя raw evidence, inferred facts и presentation. Promiscuous adapter
принимает в существующую fixed queue только client Probe Request,
Association/Reassociation Request и to-DS Data frames. `WifiDeviceCatalog` объединяет
directed SSID, BSSID/state/channel, supported rates, поколение HT/VHT/HE и WPS
device/manufacturer/model в 32 fixed records; поздние sparse frames не стирают более
богатое раннее evidence. `WifiOuiDatabase` binary-searches закреплённый при сборке
официальный snapshot IEEE MA-L из 39 984 fixed records по 32 B прямо во flash.
Multicast и locally administered MAC пропускают OUI attribution, optional fields
остаются unknown, пока клиент их не объявил. `WifiDeviceNavigationOrder` фиксирует
MAC identity при первом пользовательском взаимодействии. Passport — frozen
presentation; следующий radar закрепляет приёмник на наблюдавшемся канале выбранного
устройства и перерисовывает только live RSSI/range/trend content. Ни один экран не
посылает probe, не associate/decrypt и не сохраняет persistent identity. Exact HIL
связывает source/OUI provenance, восемь TFT states, два стабильных lifecycle, zero
drops/writes/chrome repaint и final lease 0.

Exact `0.116.0-wifi-channel-average` сохраняет aggregation Wi-Fi «Каналов» bounded и
разделяет два масштаба времени. Каждый завершённый dwell 120 мс публикует прежнюю
текущую нижнюю оценку airtime permille и добавляет её в 64-bit cumulative sum канала
с bounded dwell count. Snapshot публикует арифметическое среднее; reset при входе в
задачу очищает оба значения. `bestPrimaryChannel()` сравнивает только средние
1/6/11. Renderer рисует широкий серый столбец среднего за узким цветным столбцом
текущего уровня и очищает только прежнюю область этого канала, поэтому axis, legend,
header и footer не мерцают. Native regression намеренно разводит мгновенного и
среднего победителей; physical HIL ждёт минимум два измерения каждого канала и
проверяет точные серые TFT pixels, data-only redraw, два чистых lifecycle и final
lease 0.

Более поздний exact `0.120.0-wifi-channel-choice` заменяет последнее правило выбора без изменения
storage. `bestPrimaryChannel()` ждёт полный 13-bit measured mask, затем сравнивает
`averageBusyPermille` каналов 1…13. Строго меньшее среднее всегда побеждает. Только
при равенстве allocation-free сумма давления соседей берёт центры ±3 каналов с
весами 3/2/1 как bounded-приближение убывающего перекрытия 20 МГц. Renderer вместе
с bounded-областью рекомендации перерисовывает старую/новую подпись оси, поэтому
выделен ровно один кандидат и full-screen refresh не добавлен.

Саморевью exact `0.121.0-wifi-channel-neutral-bars` приводит rendering к той же
channel-neutral модели. `wifiChannelBarTone()` принимает только `busyPermille`;
пороги warning/danger общие для всех каналов, а низкая загрузка всегда получает
один positive tone. Host guard запрещает возвращать прежнюю ветку 1/6/11.

Exact `0.122.2-ble-device-intelligence` сохраняет BLE discovery receive-only и
проводит bounded advertisement facts через существующий observation pipeline.
Adapter явно отключает active scan, deduplicates controller results и нормализует
address/advertisement type, legacy/connectable/scannable, TX power, appearance,
company ID, known service mask/counts и bounded payload lengths. `BleDeviceCatalog`
монотонно объединяет sparse advertisements для 32 identities, переносит fixed signal
statistics вместе со stable strongest-first sort и snapshot-ит identity order после
начала взаимодействия. Flash asset 128 384 B содержит 4 012 Bluetooth SIG company
records и ищется бинарно, не копируясь в heap. Full detail рисует stable facts один
раз, incremental refresh ограничен прямоугольником радара. Один scan cycle допускает
не более двух attempts и повторяет только scanner-unavailable/scan-timeout; второй
failure остаётся terminal, cleanup освобождает все leases. Advertisement enrichment
остаётся volatile и не кодируется текущей Session schema. Focused HIL minimum heap
9 760 B ниже RB-04, поэтому функциональный checkpoint не заменяет mixed-workload
release resource/endurance evidence.

Exact `0.117.0-wifi-device-live-detail` удаляет `DeviceRadar` как отдельное UI- и
runtime-state. Open в «Устройствах» копирует выбранную fixed record, фиксирует
passive adapter на её наблюдавшемся канале и входит в `DeviceDetail`; Left выполняет
парный unlock перед возвратом к списку. Full render один раз рисует стабильную
identity. Catalog revision вызывает только `renderWifiDeviceDetailLiveData()`, чья
bounded нижняя область содержит состояние наблюдения и прежние signal card/range/
trend. HIL oracle отдельно считает identity, live и chrome pixels и допускает
неизменный frame, если новый принятый пакет не изменил ни одного показанного значения.

Exact `0.118.0-wifi-network-intelligence` обогащает scan path, не делая его active.
`BoardWifiPassiveScanner` по-прежнему использует passive scan ESP-IDF с
`show_hidden=true`; возвращённые auth/cipher, channel-width/secondary, PHY, WPS/FTM,
RX-antenna, country, BSS-color и VHT-center fields нормализуются в fixed
`WifiNetworkFacts`. `WifiNetworkCatalog` остаётся bounded на 32 BSSID и монотонно
сливает sparse records: пустой SSID становится известным, когда поздний beacon или
probe response несёт тот же BSSID, а следующая пустая record уже не может стереть
имя или прежние факты. Vendor lookup переиспользует flash-resident IEEE MA-L table.
Navigation по-прежнему snapshot-ит BSSID identities, поэтому enrichment меняет
content на месте, а не позицию курсора. Detail renderer отдельно сравнивает static
facts и RSSI; обычные updates затрагивают только signal line. Directed probe,
association, decryption или persistent identity write не добавлены.

Exact `0.119.0-wifi-network-live-radar` добавляет allocation-free
`WifiNetworkSignalStats` рядом с каждым из 32 fixed BSSID slots каталога. Insertion
sort переносит observation и statistics вместе; update увеличивает saturating sample
count и поддерживает minimum, maximum и последний RSSI delta. Один sample count не
продвигает UI revision. Видимое изменение RSSI/range/trend продвигает его, а
`renderSelectionDelta()` перерисовывает только bounded radar card выбранной сети.
Shared survey service поэтому обновляет NetworkDetail, но по-прежнему замораживает
BLE detail. HIL связывает telemetry, exact BSSID facts и framebuffer pixels. Источник
остаётся обычным all-channel passive scan ESP-IDF: channel lock, active probe,
association, calibrated distance или persistent signal history не добавлены.

## 7. Модель данных

Наблюдение отделено от интерпретации:

```text
Observation { session, monotonic time, UTC?, location?, radio, channel/frequency,
              RSSI, identity?, payload reference, decoder annotations[] }
Target      { stable local id, identities[], first/last seen, tags, notes }
Capture     { immutable source blob, metadata, derived decodes[] }
Session     { device/build/calibration, start/end, location track, observations[] }
```

Хранилище на SD (fallback LittleFS):

```text
/leshy/
  sessions/<uuid>/manifest.cbor
  sessions/<uuid>/observations.cborseq
  captures/<uuid>/manifest.cbor
  captures/<uuid>/payload.bin
  profiles/<kind>/<slug>.cbor
  config/settings.cbor
```

У каждого формата есть `schema`, миграция и checksum. Исходный `payload.bin` не
перезаписывается декодером или редактором. PCAP/CSV/JSON/SubGhz RAW являются форматами
импорта/экспорта, а не внутренним источником истины.

## 8. UI

UI использует общие компоненты: `ListView`, `DetailView`, `RadarView`, `Chart`,
`Waterfall`, `Dialog`, `Keyboard`, `Progress`. Компонент получает state и генерирует
actions; он не управляет радио.

Input нормализуется в `Up/Down/Back/Open/Context/LongPress/Touch`. Кнопки, touch и
serial remote идут по одной трассе. Это исключает текущие расхождения, когда отдельная
serial-команда повторяет teardown вручную.

Diagnostic client проходит через тот же Navigator и читает реальный TFT GRAM, а не
держит отдельную тестовую модель экранов. Transport, evidence format и обязательные
критерии определяет [`UI_AUTOMATION.ru.md`](UI_AUTOMATION.ru.md).

Companion S6 является отдельным local presentation adapter, а не вторым product API.
Его [общий envelope USB/Web](COMPANION_PROTOCOL.ru.md) согласовывает явные scopes не
шире текущей device session, рекламирует только доступные capabilities, а затем
связывает requests с теми же read projections и typed Actions. Bounded parser и
encoder не владеют storage, driver, radio или secrets; USB NDJSON и local Web JSON
сохраняют одинаковые schema и denial semantics.
Первый Web presentation состоит из self-contained offline page и validator metadata
HTTP: exact routes, method, media type, авторизованная device session и общий bound
body 512 bytes проверяются до входа в неизменный companion parser. Network listener,
lifecycle Wi-Fi и credentials остаются за пределами adapter и образуют следующую
boundary S6.5.

## 9. Безопасность и обновления

### Пассивный поиск сигнала 2.4 ГГц

Exact `0.123.0-nrf24-signal-finder` переиспользует guarded adapter
`BoardNrf24PassiveSpectrum` и его receive-only plan всех обнаруженных slots; второй
hardware driver и TX operations не добавляются. Allocation-free
`Nrf24SignalFinder` объединяет 48 полных sweep по 83 bin в одно окно. Два окна
калибровки сохраняют минимум каждого bin как ambient floor. Поиск вычитает этот фон
и общий mean delta, затем применяет bounded hold-decay на два count, чтобы локальный
transient оставался виден, а широкая смена окружения не становилась ложной целью.
Detection начинается при local rise восемь.

UI state отделён от lifetime приёмника: direct app `spectrum24` удерживает
`UiForeground|RadioSpi` в двухстрочном menu, запускает adapter только внутри
Overview/Finder и возвращается в menu до финального release app. Finder один раз
рисует static chrome и затем обновляет только result state и изменившиеся columns
графика. Read-only `hardware.nrf24.finder` отдаёт calibration, mapping, receiver
mask, side-effect counters и leases для HIL; на TFT этих counters нет. Physical
acceptance покрывает реальный ambient receive/search/restart/cleanup; для physical
found-state нужен известный source на board-02.

### Пассивный поиск частоты Sub-GHz

Exact `0.124.1-cc1101-frequency-finder` переиспользует guarded receive-only adapter
CC1101 и удерживает `UiForeground|RadioSpi` только пока Overview/Finder/Capture нужен
приёмник. `Cc1101SignalFinder` проходит fixed plan 275 000…949 500 кГц с шагом
250 кГц: по 1 099 signed baseline bins, raw-rise bins и held-response bins размещены
статически. Три полных calibration sweep образуют per-bin median; search вычитает
common-wideband drift, отвергает окрестности в пределах 500 кГц от гармоник
тактовых частот платы 26/40 МГц и требует local rise 18 dB. Прежняя calibration
minimum-of-two превращала невоспроизводимые ambient minima в пики; оба failed run
0.124.0 сохранены, исправленный candidate дважды их отвергает.

Board adapter программирует по одному bounded receive observation CC1101 и допускает
только reset/RX/idle strobes. Product renderer один раз рисует static header,
инструкции, axis и footer, затем меняет только result state и 240-column projection
отклика. Read-only `hardware.cc1101.finder` отдаёт calibration sweeps, frequency
mapping, response, side effects и lease state для HIL. Finder path не содержит TX,
PATABLE, FIFO или storage operations. Принятый evidence board-01 покрывает реальный
ambient receive/search/restart/cleanup; controlled source board-02 всё ещё нужен для
physical found-state и любых заявлений calibrated accuracy.

### Пассивный фундамент Защиты эфира

Exact `1.0.0-dev.210` начинает CAP-048 allocation-free детектором только над
receive evidence существующего `WifiFrameSource`; он не владеет radio, resource
lease, Action или response path. Первый detector группирует management frames
deauthentication/disassociation по valid unicast transmitter и сообщает bounded
burst, когда не менее четырёх matching frames попадают в окно две секунды. Policy
явна и валидируется, просматривается не более 64 source frames, а каждая находка
сохраняет detector version, threshold, confidence, counts, transmitter, time span и
до восьми exact references frame/time/channel/RSSI.

Пустой, unreadable, malformed или truncated evidence даёт `inconclusive`, а не
clear. Native golden/negative tests и source guard фиксируют эти semantics и
отвергают любую dependency на driver/platform/TX. Это только host/build foundation:
live wiring Survey, BLE и evil-twin/loss indicators, пользовательские explanation/
evidence views и physical DEMO-S7 остаются открыты.

Exact `1.0.0-dev.211` добавляет следующую UI-independent boundary над immutable
report. `AirspaceGuardController` валидирует полный report до publication, один раз
сортирует находки по confidence, отношению evidence к threshold, recency и stable
identity transmitter и первым открывает самый доказательный результат. Поэтому
Up/Down не меняют порядок под курсором. Bounded path: Finding → Evidence list →
exact Evidence detail; Back возвращает на один уровень. Partial reads, malformed
frames, dropped findings или truncated inspection остаются видимым uncertainty
flag. Outcome-only состояния clear/inconclusive не открывают выдуманное evidence, а
malformed reports fail closed. TFT screen и live capture этим ещё не подключены.

Exact `1.0.0-dev.212` добавляет над этим controller allocation-free и независимую
от renderer продуктовую модель EN/RU. Четыре стабильные строки показывают только
полезные пользователю факты: MAC источника, позицию находки, confidence с версией
detector, число событий с threshold, exact evidence frame/channel/RSSI и временной
offset. Неполные данные явно описаны текстом, а не только цветом; при нехватке места
число пропущенных находок заменяет менее важную смесь subtype. До presentation
controller теперь также проверяет согласованность detector status и bounded counters,
exact inspection coverage, границы evidence frame, правдоподобный RSSI и максимальное
окно detector; любое противоречие отклоняет весь report. Модель всё ещё не подключена
к live capture или TFT renderer, поэтому user-visible или physical claim пока нет.

- descriptor помечает приложение `Passive`, `Connected`, `Transmit` или `Disruptive`;
- TX требует отдельного Lab context, видимой частоты/мощности/таймера и подтверждения;
- запрещённый регионом диапазон блокируется общей regulatory policy;
- manifest и firmware подписываются; SHA-256 проверяет целостность, но сам по себе не
  доказывает происхождение;
- capture/file/network parsers fuzz-тестируются на host;
- секреты Wi-Fi не попадают в логи и экспорт сессии.

## 10. Тестирование

1. Host unit tests: Navigator, ResourceBroker, runtime, parsеры, протоколы, миграции.
2. Firmware build: зафиксированный Arduino core и библиотеки.
3. Simulated drivers: записанные radio traces воспроизводят сценарии без эфира.
4. HIL: boot, input, probe, TFT GRAM capture + navigation trace, begin/stop каждого
   модуля, OTA rollback.
5. Endurance: release run ≥45 минут/≥8 циклов с бюджетом ≤1 час, power loss во
   время записи, 1000 переходов apps; более длинная qualification необязательна.

`tools/test.sh` уже запускает первый слой без PlatformIO; CI проверяет и host tests,
и полную прошивку.

## 11. Путь реализации 1.x

1. Зафиксировать карту возможностей/конфликтов платы и эталонные сценарии.
2. Создать независимую build target 1.x с board profile, runtime, broker и Navigator;
   существующий прототип этих контрактов считать экспериментом, а не продолжением
   0.x.
3. Поднять display, input, storage и HardwareProbe без подключения legacy menu.
4. Реализовать первый сквозной срез Survey Session: минимальный пассивный источник →
   Observation → List/Detail → сохранённая Session → повторное открытие.
5. Подключать остальные приёмники через новые driver contracts и recorded traces;
   переносить только проверенные аппаратные операции, не экраны и глобальное
   состояние 0.x.
6. Расширить Survey до cross-radio, затем реализовать Targets и reboot-backed Library catalog.

Правило реализации: любой новый код 1.x находится за контрактами 1.x, собирается
независимо от 0.x и получает host/HIL-проверку. Архив 0.x не меняется ради удобства
новой разработки.
