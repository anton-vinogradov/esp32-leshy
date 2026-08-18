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
kernel/            AppRuntime · Navigator · ResourceBroker · scheduler · event bus
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

## 9. Безопасность и обновления

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
5. Endurance: 8-часовой survey, power loss во время записи, 1000 переходов apps.

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
