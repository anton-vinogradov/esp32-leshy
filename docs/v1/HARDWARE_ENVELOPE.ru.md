# ESP32-Leshy 1.x — аппаратные возможности ESP32-DIV v2

*Читать на: [English](HARDWARE_ENVELOPE.md) · **Русский***

Статус документа: **принятый constrained baseline S1 — design evidence и безопасный
board-01 HIL достаточны для S2; conditional physical evidence остаётся S4/S5/S8**.

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
- `H` — измерено на реальной плате. Физические данные двух assembly сохранены в
  [`board-02-hardware-variant-20260823.json`](../../tests/hil/evidence/board-02-hardware-variant-20260823.json).

Уровни уверенности: **design-confirmed** (`S/B/D` согласованы), **code-only** (`O/L`),
**conflicted** (источники расходятся), **HIL-pending**.

## Физические уровни устройства

| Уровень | Состав | Статус в 1.x |
|---|---|---|
| Main board v2 | ESP32-S3, TFT/touch, SD slot, PCF8574 + кнопки, WS2812, optional-by-assembly buzzer, backlight, IP5306, LF33, USB bridge, два USB path | объявляется точным assembly profile; функциональность проверяется |
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
| Leshy product `platformio.ini` | физические 16 MB, bounded partitions | PSRAM выключена | консервативный совместимый profile для обеих наблюдаемых плат |
| board-01 ROM/фото | 16 MB | нет (`N16`) | known-positive original assembly |
| board-02 ROM/фото | 16 MB | встроенные 8 MB Octal (`N16R8`) | реальный вариант; PSRAM не допущена из-за конфликта с GPIO35/36/37 дисплея |

1.x не hardcode-ит память из названия платы. Boot diagnostics обязан получить
фактический размер flash, результат `psramFound()`, chip/package/revision и выбранную
partition table. Обязательный переносимый бюджет теперь равен **16 MB flash / 0
используемой PSRAM**. ROM board-02 сообщает встроенные 8 MB, но их включение привело
display build к boot loop; exact compatibility image работает с `psramFound=false`.
Ни одна функция не учитывает эту память, пока отдельный pin-compatible profile не
докажет одновременную работу дисплея и PSRAM.
Замена на N16R8 не перенумеровывает pads модуля и не remap-ит application GPIO;
она делает IO35/36/37 недоступными, потому что они внутренне подключены к Octal
PSRAM. Radio set v2 (GPIO3–6, 11–15, 21, 47 и 48) с ними не пересекается, поэтому
вариант processor/memory объясняет конфликт display/PSRAM, но не common-zero radio
identity.

## Наблюдаемые assembly profiles

| Profile | Main module и population | RF-результат | Допуск |
|---|---|---|---|
| `esp32-div-v2-n16` / board-01 | `ESP32-S3-WROOM-1U-N16`; BOM buzzer распаян | exact 0.81 читает две разрешённые nRF identity и CC1101 VERSION `0x14` | known-positive baseline |
| `esp-div-n16r8-dnp-unqualified` / board-02 | `ESP32-S3-WROOM-1U-N16R8`; buzzer отсутствует; population antenna interface CC1101 AS07 отличается от board-01, U.FL не используется | assembled exact 0.130 читает zero identities и MISO LOW 0/32 под обоими pull; isolated-main exact 0.131 читает тот же GPIO13 HIGH 32/32 под обоими pull после снятия detachable RF carrier | совместимы display/input; carrier-side RF в `fault`, fixture TX запрещён |

На обоих carriers стоят три nRF24-compatible module с внешними PA/LNA и один
CC1101. Shield BOM описывает последний как **433 МГц, 10 мВт**; 315/868/915 МГц —
software tuning choices, но не доказанные полезные диапазоны этого physical assembly.
Схема также показывает, что R2/R4 — альтернативные antenna links, а R3/R5 относятся
к IR TX: их population не объясняет отсутствие SPI identity. Все четыре receiver
получают прямые 3,3 В и общий SPI через connector 2×10. Сравнительные DC measurements
теперь показывают примерно 4,7/3,3 В на board-02 и 4,35/3,2 В на рабочей board-01,
поэтому отсутствие idle rail больше не поддерживается. Exact 0.130 удерживает все CE
в LOW, samples GPIO13 с обоими внутренними pull и выполняет четыре nRF NOP reads:
board-01 остаётся HIGH 32/32 со STATUS `0x0E`, board-02 остаётся LOW 0/32 со STATUS
`0x00` до и после reseat без питания. Powered-off resistance MISO→GND равно
23 кОм на board-02 против 32 кОм на board-01, что отвергает hard passive short.
Exact 0.131 затем samples isolated main hardware board-02 при снятом detachable RF
carrier и меняет тот же наблюдаемый GPIO13 на HIGH 32/32 под обоими pull, с zero SPI
clocks, receiver reads, CE-high events, command strobes и TX commands. GPIO13 также
является SD MISO main board, поэтому high-dominant isolated state не доказывает
повреждение ESP input. Зависящий от сборки LOW локализует powered/logic-dependent
clamp на RF carrier или его стороне connector. См.
[assembled characterization](../../tests/hil/evidence/board-02-rf-bus-characterization-0.130.json)
и [isolated-main characterization](../../tests/hil/evidence/board-02-isolated-main-miso-0.131.json).
Видимое отличие antenna interface не является результатом RF continuity и не может
объяснить отсутствие digital identity. Нельзя добавлять припой или считать U.FL
оборванным только по виду фото. Exact 0.132 снова подключает carrier и samples CSN
GPIO4, 48, 21 и 5 HIGH 32/32 каждый, пока MISO остаётся LOW 0/32 под обоими pull.
Он clocks zero SPI bytes и выполняет zero reads, CE-high events, strobes и TX commands.
Значит, line удерживает не выбранный receiver, а carrier module или shared-MISO net
carrier не переходит в high impedance. Общая direct power/MISO topology исключает
дальнейшую software-only изоляцию отдельных modules. См.
[carrier-CSN evidence](../../tests/hil/evidence/board-02-rf-carrier-csn-0.132.json).

Upstream community evidence имеет такую же форму отказа, но не доказывает root cause
этого экземпляра. [Issue #102](https://github.com/cifertech/ESP32-DIV/issues/102)
описывает одновременную потерю инициализации NRF24/CC1101 из-за cold joints или
окисления межплатных контактов и рекомендует проверить rails shield плюс CE/CSN.
Leshy принимает проверки rail/continuity, но не критерий CE HIGH из сообщения:
passive admission обязана удерживать CE LOW до plausible identity receiver.
[Discussion #90](https://github.com/cifertech/ESP32-DIV/discussions/90) также сообщает,
что неудачная инициализация nRF может испортить состояние shared bus для следующей
операции CC1101. Для нашего случая это более слабое объяснение: exact image Leshy
делает независимые bounded reads после clean boot и всё равно получает common-zero.
Сообщения о white screen в той discussion и issues
[#135](https://github.com/cifertech/ESP32-DIV/issues/135),
[#157](https://github.com/cifertech/ESP32-DIV/issues/157) и
[#158](https://github.com/cifertech/ESP32-DIV/issues/158) не называют N16R8 или
GPIO35/36/37 причиной и остаются только background evidence.

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
- RF shield имеет по 10 µF рядом с каждым NRF24 и получает прямые 3,3 В через
  pin 18 connector 2×10; pin 20 подаёт 5 В. User-observed idle DC values: 4,35/3,2 В на board-01
  и 4,7/3,3 В на board-02; meter accuracy, ripple, peak current и thermal margin
  не подтверждены;
- VBAT divider и buzzer делят GPIO2, поэтому firmware не получает независимый
  battery ADC channel.

Неизвестны: точная LF33 variant/current/thermal margin, IP5306 I²C register variant,
максимальный ток обеих rail, поведение при USB+cell, brownout при трёх NRF и точность
VBAT divider с подключённым buzzer transistor. До измерений запрещены одновременные
TX stress modes; они не нужны для S1–S6.

[Программный Safety Supervisor](SAFETY_SUPERVISOR.ru.md) может немедленно опустить
active-high buzzer и все объявленные nRF CE, а затем защёлкнуть exact firmware в
Safe Mode. На подтверждённой плате нет независимого rail kill, датчика
температуры/тока или reset/power gate CC1101, поэтому этот control не закрывает
`HW-U04`, `HW-U09`, `HW-U10`, `R-009` или `R-018` как physical-safety claim.

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
| NRF24 #1/#2/#3 | RF shield | CE LOW; stable register/status read на каждом выбранном CS; #3 только внутри exclusive nRF-стороны mux GPIO14/21 | все три independently `detected` в nRF mode; physical mux contention остаётся constrained по HW-T08 |
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

Product сейчас не выполняет optional radio sequence при boot. Exact
`0.81.0-shield-receiver-probe` запускает разрешённый subset только после подтверждения
Full/Guided пользователем и получения `RadioSpi`: nRF #1/#2 и CC1101 обнаружены с
exact read bounds 8/2/20, nRF #3 остаётся gated, GPIO21 остаётся HIGH, все counters
CE-high/strobe/TX равны нулю (`E-HIL-106`/`E-RADIO-001`). Это только software и
register-identity evidence. HW-T06 остаётся partial: RF detector для доказательства
physical silence недоступен.

Абзац boot policy выше описывает консервативный автоматический probe, а не текущий
результат explicit runtime. Exact 0.100 заменяет старое software gating 0.81 после
выбора nRF reception пользователем: все три независимо адресуемых nRF slot активны с
mask `7`. Exact 0.104 добавляет взаимоисключающую IR-сторону того же mux: nRF #3
полностью остановлен, GPIO14 и все CE остаются LOW, GPIO21 — только input во время
345 272 passive samples. nRF и IR никогда не активны одновременно. Это закрывает
software ownership/direction часть HW-T08; known physical IR stimulus и
instrumented electrical trace остаются открыты.

Exact `0.82.0-nrf24-spectrum` добавляет явный запускаемый пользователем receive path,
но не boot probe. Он получает тот же exclusive domain `RadioSpi`, проверяет оба
declared receiver, переводит каждый в `PRIM_RX` и поднимает CE только для bounded
receive windows 200 us при sweep по 83 каналам. Final exact counts — 1 743 CE receive
windows, 1 753 reads, 1 755 writes и 7 016 SPI bytes; TX-mode/payload commands,
CC strobes и storage writes остаются нулевыми. Stop выключает оба nRF, восстанавливает
safe pins, сохраняет slot 3/GPIO21 gated/high и освобождает lease
(`E-HIL-107`/`E-RADIO-002`). Без RF detector это доказывает guarded software path,
но не physical RF silence.

Exact `0.83.0-cc1101-spectrum` добавляет соответствующий явный пользовательский
receive path CC1101. GPIO5 разрешён только профилем board-01 без GPS/PN532;
`RadioSpi` остаётся exclusive, nRF slot 3/GPIO21 — gated/high, а каждый из 354
samples использует только разрешённую последовательность RX/IDLE после одного reset.
Final wire counts — 1 reset, 354 RX и 713 IDLE strobes, 11 443 reads, 1 078 writes и
26 110 SPI bytes; counters TX, rejected strobe, PATABLE, FIFO и storage write равны
нулю. Stop оставляет CC1101 в IDLE и освобождает lease
(`E-HIL-108`/`E-RADIO-003`). Без RF detector и calibrated source это не доказывает
ни physical RF silence, ни calibrated RSSI/frequency accuracy.

Exact `0.84.0-full-guided-rf` повторно использует эти guarded receive adapters только
после preflight Full/Guided. Plan v5 получает `RadioSpi`, завершает один sweep 83
каналов на обоих nRF24 и один sweep CC1101 433 МГц по 64 bins, затем возвращает оба
adapter в safe state до release. Принятый run учитывает 83 RX CE windows и
1 reset/64 RX/129 IDLE strobes CC1101 при zero TX-mode/payload/TX-strobe/PATABLE/
FIFO/storage counters (`E-HIL-109`/`E-RADIO-004`). Это по-прежнему software-counter
evidence; HW-T06 остаётся partial без RF detector.

Exact `0.85.0-full-guided-artifacts` освобождает эту RF phase до получения
объявленного набора `Storage|RadioSpi` для persisted-artifact phase. Он заново
идентифицирует CID `FE343253440000002000000055019CB7`, монтирует SD read-only,
восстанавливает последнюю atomic Session через тот же guarded path, что используется
при boot, потоково направляет Library/export artifacts только в discard sinks, затем
unmount-ит карту и освобождает оба ресурса. `E-HIL-110` наблюдает continuity
generation 83/observation 0, zero blocked или attempted storage writes, PCAP из 16
frames с точным byte count и final lease 0. Это evidence read-only workflow, а не
отдельный controlled power-cut test.

Exact `0.86.0-full-guided-disposable` затем использует тот же exclusive resource set
в трёх непересекающихся phases: exact-CID writable scratch commit, read-only remount
и export, exact typed cleanup. `E-HIL-111` наблюдает три writes/504 bytes только в
`/leshy-hil/full-guided-v7`, zero product writes, удаление всех трёх scratch files,
неизменную product generation 83/0 и final lease 0. Это не заменяет physical
power-cut или instrumented RF-silence evidence.

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
| HW-T08 | Partial: exact nRF mask 7 и exclusive IR switch/directions/stop доказаны software; осталось электрически охарактеризовать GPIO21 и подать known IR signal | logic trace + NRF register log + IR receiver test |
| HW-T09 | GPIO2 buzzer/VBAT: voltage, ADC loading, silent boot | scope/ADC series; decision on battery capability |
| HW-T10 | Rail current/voltage: idle, full backlight, SD, each passive radio, combined Survey | min/avg/peak, brownout margin, temperature |
| HW-T11 | Native USB and CP2102 paths, reset/download/recovery | port IDs + recovery transcript |

## Аппаратные неопределённости и обязательные dispositions

`constrained` снимает неоднозначность software/scope, не объявляя физический вопрос
измеренным. Safe default обязателен до появления named closure evidence; build flag
или успешный несвязанный probe не переводит constrained device в `available`.

| ID | Состояние evidence | Обязательный safe default 1.x | Физическое закрытие |
|---|---|---|---|
| HW-U01 | partial: board-01 — N16/no-PSRAM; board-02 — N16R8/DNP variant, чьи встроенные 8 MiB Octal PSRAM конфликтуют с display GPIO35/36/37 и не используются compatibility image | portable baseline — 16 MiB flash с отключённой PSRAM; N16R8 — отдельный unqualified profile, не dynamic budget expansion | дополнительные batch IDs и pin-compatible display/PSRAM profile, если он существует |
| HW-U02 | unmeasured: schematic противоречит legacy flag | TFT reset внешний/unassigned; GPIO0 остаётся только BOOT и не управляет display reset | HW-T02 continuity/logic trace |
| HW-U03 | partial: read-only I²C отвечает на `0x75`; identity/map power manager неизвестны | показывать только generic presence/evidence; battery percentage и write/control operations unavailable | exact marking/datasheet + HW-T04 |
| HW-U04 | partial: idle connector rails user-measured 4,35/3,2 В на рабочей board-01 и 4,7/3,3 В на board-02; ripple, peak и thermal margin не измерены | никакого active RF fixture board-02 и default combined shield load; новая combination unavailable по RB-08 | calibrated dynamic HW-T10 rail/thermal matrix |
| HW-U05 | оператор подтвердил отсутствие GPS/PN532 assembly на board-01; standard connector contract не доказан | default profile объявляет оба absent; каждому нужен explicit assembly profile, output-mode autodetect запрещён | assembly photo/spec + HW-T07 |
| HW-U06 | partial: GPIO38 LOW с одной inserted/identified card; polarity и batch consistency не измерены | GPIO38 не authoritative в S2; storage state определяется bounded explicit operation и остаётся fault/absent при failure | HW-T05 на разных media/batch |
| HW-U07 | partial: exact 0.130 читает valid receiver identities и MISO HIGH 32/32 на board-01, но assembled board-02 удерживает shared MISO LOW 0/32 под обоими pull до/после reseat несмотря на valid idle rails; powered-off MISO→GND 23 кОм против 32 кОм отвергает hard short; exact isolated-main 0.131 меняет GPIO13 на HIGH 32/32 без carrier; exact reassembled 0.132 доказывает каждый receiver CSN HIGH 32/32, пока MISO возвращается LOW 0/32 при zero bus/TX activity | `spi_radio` exclusive; carrier RF board-02 остаётся `fault`; cross-swap и emission запрещены; конкретный module или antenna/U.FL fault не заявляется | вернуть/заменить carrier/device либо физически изолировать MISO/power modules по одному; до bounded regression потребовать repaired plausible identities |
| HW-U08 | electrical/ADC behavior не измерен; software root cause ложного звука подтверждён 0.x и upstream issue #117 | battery percentage unavailable; GPIO2 никогда не sampled как ADC и с первой инструкции setup удерживается OUTPUT LOW; HIGH разрешён только будущему bounded sound service | HW-T09 для ADC/sound characterization; silent invariant закрывается boot/runtime state + audible observation |
| HW-U09 | partial: exact 0.129 доказывает один bounded physical NEC receive/save/cold-export path; GPIO21 остаётся exclusive с nRF #3 | IR RX available только из explicit RF-shield profile; autodetect отсутствует; product IR TX дополнительно требует Lab/ADR-002 evidence | расширить protocol vectors и instrument GPIO21 switching по HW-T08 |
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
- BoardSafeOutputs устанавливает GPIO2 и nRF CE GPIO14/15/47 OUTPUT LOW до
  console/display. ISR panic Task WDT повторно устанавливает эти уровни прямыми GPIO
  registers, а static checks запрещают apps/drivers обходить безопасный path.
- Release 1.x не включает OPI-PSRAM dependency, пока `HW-U01` не доказал совместимый
  hardware variant, не конфликтующий с display pins.
- Первый Survey source остаётся предварительно Wi-Fi: он обходит все внешние mux и
  позволяет проверить Session pipeline до закрытия radio-shield HIL.
