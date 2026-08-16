# ESP32-Leshy 1.x — аппаратные возможности ESP32-DIV v2

*Читать на: [English](HARDWARE_ENVELOPE.md) · **Русский***

Статус документа: **S1 draft — design evidence собрано, board-01 HIL выполнен частично**.

Воспроизводимая процедура и отдельная read-only firmware описаны в
[`HIL_PROBE.ru.md`](HIL_PROBE.ru.md); наличие инструмента не считается физическим
evidence само по себе.

Документ является нормативной design-time картой железа для 1.x. Он отделяет
подтверждённые соединения от предположений исходного firmware и от фактов, которые
можно установить только на конкретной плате. `BoardProfile` реализует эту карту, но
не переопределяет её молча.

## Область и источники

Разобран ESP32-DIV v2 из upstream snapshot `9d4d82f` от 7 августа 2026 года:

- [v2 Main Schematic](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/Main-Schematic.jpg);
- [v2 Shield Schematic](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/Shield-Schematic.jpg);
- [main BOM](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/main-BOM.xls) и
  [shield BOM](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Schematic/v2/shield-BOM.xlsx);
- [board pin definitions](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/ESP32-DIV/shared.h) и
  [TFT setup](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/Libraries/User_Setup%20v2.h);
- [официальные build settings original](https://github.com/CiferTech/ESP32-DIV/blob/9d4d82fe7a12febf554b12e1eca6d434ebe79d39/CONTRIBUTING.md#arduino-ide-settings);
- [ESP32-S3-WROOM-1/1U datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf),
  [ESP32-S3 GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/release-v5.0/esp32s3/api-reference/peripherals/gpio.html) и
  [PCF8574 datasheet](https://www.ti.com/lit/ds/symlink/pcf8574.pdf).

Обозначения evidence:

- `S` — schematic connection;
- `B` — BOM/component identity;
- `O` — assumption или поведение original firmware;
- `L` — текущее предположение Leshy 0.x/prototype;
- `D` — vendor datasheet;
- `H` — измерено на реальной плате; сейчас таких свидетельств в workspace нет.

Уровни уверенности: **design-confirmed** (`S/B/D` согласованы), **code-only** (`O/L`),
**conflicted** (источники расходятся), **HIL-pending**.

## Физические уровни устройства

| Уровень | Состав | Статус в 1.x |
|---|---|---|
| Main board v2 | ESP32-S3, TFT/touch, SD slot, PCF8574 + кнопки, WS2812, buzzer, backlight, IP5306, LF33, CP2102, два USB path | declared by board profile; функциональность проверяется |
| RF shield v2 | 3× NRF24L01, CC1101, IR RX/TX, antenna routing | detachable/optional; radios пробуются без TX |
| External modules | GPS NEO-6M и PN532 | не присутствуют в v2 main/shield schematic или BOM; только explicit assembly profile + probe |
| Media/power | microSD и Li-ion cell | слот/charger существуют, но card/cell могут отсутствовать |

Следствие: capability `Gps` или `Nfc` нельзя выводить только из строки «ESP32-DIV v2».
Даже RF shield нельзя считать установленным без probe или явного assembly profile.

## MCU, flash и PSRAM

Схема и main BOM называют модуль **ESP32-S3-WROOM-1U-N16**. По таблице вариантов
Espressif это 16 MB Quad SPI flash и **без PSRAM**. Это согласуется с использованием
GPIO35/36/37 для display/touch: на вариантах с Octal PSRAM эти GPIO относятся к
дополнительным линиям памяти и не должны использоваться как обычный display SPI.

Однако источники расходятся:

| Источник | Flash | PSRAM | Оценка |
|---|---:|---:|---|
| v2 schematic + main BOM | 16 MB | нет (`N16`) | design-confirmed для файлов проекта |
| original CONTRIBUTING settings | 16 MB | OPI PSRAM | конфликтует с ordering code и GPIO35–37 |
| Leshy `platformio.ini` prototype | 8 MB partition target | no-PSRAM board definition | не соответствует BOM; пригодно только как текущая совместимая сборка |

1.x не hardcode-ит память из названия платы. Boot diagnostics обязан получить
фактический размер flash, результат `psramFound()`, chip/package/revision и выбранную
partition table. До HIL применяются минимальные бюджеты **8 MB flash / 0 PSRAM**, но
release profile для подтверждённого `N16` должен использовать всю 16 MB flash без
обязательной PSRAM.

## Нормативная GPIO-карта

| GPIO | Соединение v2 | Resource/capability | Evidence | Ограничение |
|---:|---|---|---|---|
| 0 | BOOT button с pull-up | boot strap | S,D | не использовать как TFT reset или runtime output |
| 1 | data chain 4× WS2812B-2020 | status LEDs | S,B,L | LEDs питаются от 5 V; presence только HIL |
| 2 | buzzer transistor base **и** VBAT divider midpoint | buzzer / battery sense | S,O,0.x,U | active HIGH; clean 1.x с первой инструкции держит output LOW как silent safety invariant; battery ADC запрещён |
| 3 | CC1101 GDO2 | CC1101 RX/data | S,O,D | ESP32-S3 strapping pin; не менять режим до завершения boot strap |
| 4 | NRF24 #1 CSN | radio SPI slave select | S,O | idle HIGH |
| 5 | CC1101 CSN / PN532 SS / GPS TX→ESP RX | `mux_5_6` | S/O | output запрещён, пока не исключён GPS; три assembly взаимоисключающие |
| 6 | CC1101 GDO0 / ESP TX→GPS RX | `mux_5_6` | S/O | направление зависит от выбранного assembly/mode |
| 7 | TFT backlight MOSFET gate | display/backlight | S,O,L | PWM output; boot default должен быть безопасным |
| 8 | I²C SDA | control I²C | S,L | PCF8574 и IP5306 share bus |
| 9 | I²C SCL | control I²C | S,L | PCF8574 и IP5306 share bus |
| 10 | microSD CS | radio/storage SPI | S,O | idle HIGH |
| 11 | SD/NRF/CC MOSI; PN532 software-SPI MISO | `spi_radio` | S,O | PN532 разворачивает направление относительно общей bus |
| 12 | SD/NRF/CC/PN532 SCK | `spi_radio` | S,O | одна физическая clock line |
| 13 | SD/NRF/CC MISO; PN532 software-SPI MOSI | `spi_radio` | S,O | PN532 mode требует полной эксклюзивности |
| 14 | NRF24 #3 CE / IR TX transistor | `mux_nrf3_ir` | S,B,O | оба output; idle LOW, одновременно запрещены |
| 15 | NRF24 #1 CE | NRF24 #1 | S,O | idle LOW |
| 16 | TFT D/C | display | S,O,L | dedicated output |
| 17 | TFT CS | `spi_display` | S,O,L | idle HIGH |
| 18 | XPT2046 touch CS | `spi_display` | S,O,L | idle HIGH; IRQ не подключён |
| 19 | ESP native USB D− | native USB | S,D | не GPIO при включённом USB |
| 20 | ESP native USB D+ | native USB | S,D | не GPIO при включённом USB |
| 21 | NRF24 #3 CSN / IR RX | `mux_nrf3_ir` | S,B,O | NRF output vs IR input mode; idle HIGH для NRF CSN |
| 35 | TFT/XPT2046 MOSI | `spi_display` | S,O,L,D | конфликтует с Octal PSRAM variants |
| 36 | TFT/XPT2046 SCK | `spi_display` | S,O,L,D | конфликтует с Octal PSRAM variants |
| 37 | TFT/XPT2046 MISO | `spi_display` | S,O,L,D | конфликтует с Octal PSRAM variants |
| 38 | microSD card-detect candidate | SD presence | S/O | code считает active-low; polarity требует HIL |
| 43 | UART0 TX → CP2102 RX | console/programming | S,D | не путать с GPIO1 NeoPixel |
| 44 | UART0 RX ← CP2102 TX | console/programming | S,D | CP2102 auto-reset использует DTR/RTS отдельно |
| 47 | NRF24 #2 CE | NRF24 #2 | S,O | idle LOW |
| 48 | NRF24 #2 CSN | NRF24 #2 | S,O | idle HIGH |

TFT и XPT2046 **физически используют одни линии 35/36/37**, несмотря на то что
legacy-код создаёт отдельный `SPIClass`. Их нельзя считать двумя независимыми bus;
транзакции должны сериализоваться. TFT reset на schematic подключён к системному net
`RESET/EN`, тогда как original и Leshy build flags задают `TFT_RST=0`. GPIO0 является
BOOT strap. До continuity/HIL-проверки 1.x обязан считать display reset внешним
(`-1`) и никогда не переключать GPIO0 для reset дисплея.

## Шины и resource domains

| Domain | Линии/устройства | Политика первой реализации |
|---|---|---|
| `spi_display` | 35/36/37; TFT CS17, touch CS18, TFT D/C16 | transaction mutex; CS второго устройства HIGH |
| `spi_radio` | 11/12/13; SD CS10, NRF CS4/48/21, CC CS5 | один owner на driver operation; все остальные CS HIGH, NRF CE LOW |
| `spi_pn532_bitbang` | SCK12, input11, output13, SS5 | exclusive lease всей `spi_radio` + `mux_5_6`; CC/SD/NRF отключены |
| `mux_5_6` | CC1101, GPS, PN532 SS | assembly-level exclusivity; ambiguity = all unavailable |
| `mux_nrf3_ir` | GPIO14/21 | NRF #3 или IR; runtime switch только после полного stop/tri-state |
| `gpio2_battery_buzzer` | GPIO2 ADC/output | buzzer или диагностическое ADC measurement; ADC disabled until HIL |
| `i2c_control` | SDA8/SCL9; PCF8574, IP5306 candidate | shared transaction mutex; read-only probe |
| `storage` | SD filesystem + `spi_radio` | atomic service; запись только в выделенное bus window |
| `esp_rf` | встроенные Wi-Fi/BLE и одна 2.4 GHz antenna | coexistence scheduler; capability не означает полный simultaneous scan |
| `console` | CP2102/UART0 и native USB | logging policy выбирает один устойчивый path |

SD, NRF24 и CC1101 электрически могут делить SPI с разными CS, но original code
показывает регулярный reset/remount bus из-за pinmux, clock и library state. Поэтому
1.x сначала выдаёт эксклюзивную operation lease; transaction-level sharing можно
разрешить только после HIL/soak evidence.

## Питание

Design-confirmed topology:

- Li-ion cell подключён к IP5306; IP5306 формирует power-bank/charge path;
- LF33 формирует 3.3 V из 5 V rail;
- ESP32-S3, TFT logic/touch, PCF8574, SD и RF modules используют 3.3 V;
- WS2812, IR LED и buzzer circuitry используют 5 V;
- RF shield имеет по 10 µF рядом с каждым NRF24, но допустимый peak current и
  стабильность rail не подтверждены;
- VBAT divider и buzzer делят GPIO2, поэтому firmware не получает независимый
  battery ADC channel.

Неизвестны: точная LF33 variant/current/thermal margin, IP5306 I²C register variant,
максимальный ток обеих rail, поведение при USB+cell, brownout при трёх NRF и точность
VBAT divider с подключённым buzzer transistor. До измерений запрещены одновременные
TX stress modes; они не нужны для S1–S6.

## Capability model

Capability имеет не `bool`, а состояние:

```text
declared    — ожидается assembly profile
detected    — безопасный probe получил identity/response
available   — detected и все resources совместимы
conflicted  — hardware найдено, но текущая assembly/resource policy запрещает запуск
fault       — ожидалось, но probe/self-test не прошёл
unknown     — universal safe probe невозможен
```

| Capability | Основание | Безопасный boot probe | Итог без HIL |
|---|---|---|---|
| MCU/flash/PSRAM | chip runtime APIs | read chip/revision/flash/PSRAM | `detected` |
| TFT/backlight | main-board profile | init without GPIO0 reset; visible HIL later | `declared` |
| Touch | main-board profile | read-only sample with CS isolation | `declared`, затем functional |
| Keypad | PCF8574 A0..A2=GND → expected 0x20 | I²C ACK + port read, no output writes | `detected` |
| Power manager | IP5306 pins wired to I²C | address/register probe only; expected address remains HIL-pending | `unknown` if no known response |
| Status LEDs | main-board profile | no automatic electrical identity | `declared` |
| Buzzer | main-board profile | output LOW с первой инструкции setup; pad level проверяется в Diagnostics, звук не генерируется | silent invariant `available` либо `fault`; sound capability отдельно не заявлена |
| SD slot/card | main board + removable media | card-detect read, then read-only mount last | slot `declared`, card `detected` |
| NRF24 #1/#2/#3 | RF shield | CE LOW; #1/#2 read stable register/status per CS; #3 только после characterizing GPIO21/IR contention | #1/#2 independently `detected`; #3 `unknown` до HW-T08 |
| CC1101 | RF shield/assembly | only after GPS exclusion; reset→IDLE, read PARTNUM/VERSION, no RX/TX | `detected` or `conflicted` |
| GPS | external assembly | GPIO5 high-Z input; passively observe valid 9600-baud NMEA before any CC/PN532 drive | `detected` |
| PN532 | external assembly | only explicit NFC assembly and CC/GPS absence; firmware-version command, no RF field | `detected` |
| IR RX/TX | RF shield | circuitry has no digital identity; infer from confirmed shield, validate by HIL | `declared/unknown` |

## Безопасный порядок boot probe

1. Прочитать chip, package/revision, flash, partitions и PSRAM без изменения GPIO.
2. Оставить strap GPIO0/3 и contested GPIO5/6/14/21 в reset/high-impedance state;
   GPIO2 — единственное исключение: сразу preload LOW и OUTPUT, чтобы исключить
   ложный stock low-battery buzzer. Не читать его как ADC.
3. Инициализировать I²C 8/9; прочитать только ожидаемые PCF8574/IP5306 addresses.
4. Пассивно слушать GPIO5 как GPS TX. Валидные NMEA frames выбирают GPS assembly и
   навсегда запрещают CC1101/PN532 на этой загрузке.
5. Если assembly разрешает RF shield: выставить NRF CE LOW, CS4/48 HIGH, SD CS10
   HIGH и CC CS5 HIGH. GPIO21 оставить input до HW-T08. Только затем инициализировать
   radio SPI.
6. Пробовать NRF #1/#2 по одному чтением registers, не поднимать CE. NRF #3 не
   выбирать до characterizing contention с output IR receiver на GPIO21.
7. Пробовать CC1101 только когда GPS не обнаружен и NFC assembly не заявлен; оставить
   его в IDLE.
8. PN532 пробовать только в явном NFC assembly с полной exclusive lease. Автопоиск
   через GPIO5 запрещён.
9. Card detect прочитать после radios; read-only SD mount выполнять последним и
   полностью восстановить bus state.
10. Display/touch запустить на отдельном physical domain, не переключая GPIO0.
11. WS2812, активация buzzer, IR TX и любые RF TX не участвуют в автоматическом
    boot probe; удержание buzzer LOW — safety invariant, а не actuator probe.

Любая неоднозначность GPIO5/6 или 14/21 заканчивается `conflicted`, а не перебором
output modes. Probe не должен передавать RF/IR, писать на SD/NFC или издавать звук.

Software evidence для GPIO2: авторское описание root cause и one-line LOW fix в
[upstream issue #117](https://github.com/cifertech/ESP32-DIV/issues/117#issuecomment-5178973211)
ссылается на проверенную реализацию
[0.x commit `04fd290`](https://github.com/anton-vinogradov/esp32-leshy/blob/04fd290019dc2d80a53d8c86599b4380fd74ac47/src/main.cpp#L2883).

## HIL-план закрытия S1

| Test ID | Процедура | Evidence |
|---|---|---|
| HW-T01 | Снять marking ESP module и runtime flash/PSRAM/chip info минимум с двух v2 boards | фото + diagnostic bundle |
| HW-T02 | Continuity GPIO0↔TFT RESET и RESET/EN↔TFT RESET | resistance/logic trace; закрывает `HW-U02` |
| HW-T03 | Logic analyzer display/touch 35/36/37 и radio bus 11/12/13 | CS idle levels, modes, max verified clock |
| HW-T04 | I²C scan/read PCF8574 и IP5306 без записи | addresses, IDs/register behavior |
| HW-T05 | SD CD polarity, read-only mount, radio→SD→radio recovery, power-cut write | trace + recovered filesystem |
| HW-T06 | Read-only identity NRF #1/#2 и CC; verify no CE/TX event | register log + RF detector silence |
| HW-T07 | Отдельно подключить GPS assembly и PN532 assembly; проверить safe selection | NMEA/PN532 version logs, no pin contention |
| HW-T08 | NRF3↔IR: characterize electrical contention GPIO21, затем identity/switch, pin directions, idle levels и physical stop | logic trace + NRF register log + IR receiver test |
| HW-T09 | GPIO2 buzzer/VBAT: voltage, ADC loading, silent boot | scope/ADC series; decision on battery capability |
| HW-T10 | Rail current/voltage: idle, full backlight, SD, each passive radio, combined Survey | min/avg/peak, brownout margin, temperature |
| HW-T11 | Native USB and CP2102 paths, reset/download/recovery | port IDs + recovery transcript |

## Аппаратные неопределённости и обязательные dispositions

`constrained` снимает неоднозначность software/scope, не объявляя физический вопрос
измеренным. Safe default обязателен до появления named closure evidence; build flag
или успешный несвязанный probe не переводит constrained device в `available`.

| ID | Состояние evidence | Обязательный safe default 1.x | Физическое закрытие |
|---|---|---|---|
| HW-U01 | partial: board-01 — S3 rev 0.2, 16 MiB Quad, без PSRAM; диапазон партий неизвестен | baseline profile N16/no-PSRAM; flash/PSRAM/profile mismatch — `fault`/unsupported | HW-T01 на второй v2 + assembly IDs |
| HW-U02 | unmeasured: schematic противоречит legacy flag | TFT reset внешний/unassigned; GPIO0 остаётся только BOOT и не управляет display reset | HW-T02 continuity/logic trace |
| HW-U03 | partial: read-only I²C отвечает на `0x75`; identity/map power manager неизвестны | показывать только generic presence/evidence; battery percentage и write/control operations unavailable | exact marking/datasheet + HW-T04 |
| HW-U04 | только design evidence LF33; current/thermal headroom неизвестен | никакой default combined shield load; новая combination unavailable по RB-08 | marking + HW-T10 rail/thermal matrix |
| HW-U05 | оператор подтвердил отсутствие GPS/PN532 assembly на board-01; standard connector contract не доказан | default profile объявляет оба absent; каждому нужен explicit assembly profile, output-mode autodetect запрещён | assembly photo/spec + HW-T07 |
| HW-U06 | partial: GPIO38 LOW с одной inserted/identified card; polarity и batch consistency не измерены | GPIO38 не authoritative в S2; storage state определяется bounded explicit operation и остаётся fault/absent при failure | HW-T05 на разных media/batch |
| HW-U07 | partial: три guarded SD identity runs завершаются с exclusive Storage+RadioSpi, GPIO21 HIGH, stable CID/CSD и cleanup; instrumented coexistence не измерен | `spi_radio` — exclusive operation lease; SD и shield receivers не пересекаются | HW-T03/HW-T05 + radio→SD→radio recovery + endurance RB-07 |
| HW-U08 | electrical/ADC behavior не измерен; software root cause ложного звука подтверждён 0.x и upstream issue #117 | battery percentage unavailable; GPIO2 никогда не sampled как ADC и с первой инструкции setup удерживается OUTPUT LOW; HIGH разрешён только будущему bounded sound service | HW-T09 для ADC/sound characterization; silent invariant закрывается boot/runtime state + audible observation |
| HW-U09 | нет безопасного passive digital identity | IR available только из explicit RF-shield profile; autodetect отсутствует; IR TX дополнительно требует Lab/ADR-002 evidence | assembly manifest/detector + HW-T08 |
| HW-U10 | нет rail peak/thermal measurements | первый slice только Wi-Fi; shield по одному receiver после per-module HIL; combined modes unavailable | HW-T10 и endurance RB-08 |

## Решения для архитектуры

- `HARDWARE_ENVELOPE` становится design-time источником pin/resource truth;
  `BoardProfile` должен ссылаться на его revision и не содержать неотслеживаемых
  «verified» комментариев.
- HardwareProbe возвращает state + evidence, а не одну capability mask.
- Assembly profile обязателен для `gps_external` и `pn532_external`; autodetect не
  имеет права перебирать конфликтующие output modes.
- ResourceBroker получает domains `spi_display`, `spi_radio`, `mux_5_6`,
  `mux_nrf3_ir`, `gpio2_battery_buzzer`, `i2c_control`, `storage` и `esp_rf`.
- BoardSafeOutputs устанавливает GPIO2 OUTPUT LOW до console/display и статическая
  проверка запрещает apps/drivers менять buzzer pin напрямую.
- Release 1.x не включает OPI-PSRAM dependency, пока `HW-U01` не доказал совместимый
  hardware variant, не конфликтующий с display pins.
- Первый Survey source остаётся предварительно Wi-Fi: он обходит все внешние mux и
  позволяет проверить Session pipeline до закрытия radio-shield HIL.
