# ESP32-Leshy 1.x — операторский протокол S1 HIL probe

*Читать на: [English](HIL_PROBE.md) · **Русский***

Статус документа: **процедура сбора evidence; результаты на реальной плате пока не
получены**.

Этот документ обслуживает тесты из
[`HARDWARE_ENVELOPE.ru.md`](HARDWARE_ENVELOPE.ru.md). Нормативная карта железа
остаётся там; diagnostic image лишь собирает воспроизводимое evidence и не является
target 1.x или пользовательской прошивкой.

## Артефакт и граница безопасности

Отдельный PlatformIO project находится в `diagnostics/hil_probe`. Он не линкует код
0.x, Wi-Fi/BLE, RF24 или RadioLib и выдаёт JSON Lines одновременно в native USB и
UART0/CP2102 на 115200 baud.

Инварианты image:

- NRF CE15/47/14 переводятся LOW до запуска consoles и никогда не поднимаются;
- Wi-Fi, BLE, RF/IR TX, buzzer, LEDs, display, touch и SD не запускаются;
- GPIO0/2/3/5/6/21 и radio SPI остаются input до выбранной read-only процедуры;
- I²C использует только `requestFrom`: zero register/config writes;
- GPIO5 для GPS используется только как UART RX, TX pin отключён;
- CC1101 получает только status-register read `0xF0/0xF1`, без command strobes;
- NRF #1/#2 получают только `R_REGISTER`; slot #3 не выбирается до `HW-T08`;
- RF read недоступен без точной операторской фразы, подтверждающей отсутствие GPS и
  PN532.

Статический check подтверждает отсутствие известных TX paths в source, но физическую
тишину доказывают logic analyzer/RF detector в `HW-T06`, а не утверждение кода.

## Сборка

```bash
tools/build_hil_probe.sh
shasum -a 256 diagnostics/hil_probe/.pio/build/esp32-div-hil-probe/firmware.factory.bin
```

Ожидаемый artifact:
`diagnostics/hil_probe/.pio/build/esp32-div-hil-probe/firmware.factory.bin`.
SHA-256, commit/worktree state, probe version и имя платы записываются рядом с
полученным JSONL.

Прошивка меняет содержимое flash. Перед выполнением сохранить нужные данные 0.x и
зафиксировать способ восстановления. Upload выполняется только с явным port:

```bash
pio run -d diagnostics/hil_probe -t upload --upload-port /dev/cu.EXPLICIT_PORT
pio device monitor --port /dev/cu.EXPLICIT_PORT --baud 115200
tools/capture_hil_serial.py --port /dev/cu.EXPLICIT_PORT \
  --output evidence.log --command inventory --command i2c-read
tools/capture_hil_serial.py --port /dev/cu.EXPLICIT_PORT \
  --output rf-evidence.log --rf-read-confirmed
```

Codex не прошивает плату и не объявляет HIL pass без присутствия оператора,
идентифицированного port и сохранённого наблюдаемого результата.

## Команды

| Команда | Тест | Действие | Условие |
|---|---|---|---|
| `inventory` | HW-T01, HW-T11 | chip/revision/eFuse MAC, physical flash ID/size, PSRAM, heap, partitions, reset/toolchain | автоматически при boot; GPIO не меняет |
| `i2c-read` | HW-T04 | read-only sweep 0x08…0x77 на GPIO8/9, сохраняет первый прочитанный byte | только штатная main board |
| `gps-listen` | HW-T07 | 10 секунд слушает GPIO5 RX/9600, считает NMEA с валидным checksum, координаты не печатает | CC/PN532 не активируются |
| `rf-read shield-no-gps-no-pn532` | HW-T06 | после 2,2 с GPS preflight читает NRF #1/#2 и CC1101 identity на 1 MHz SPI | оператор физически снял GPS и PN532, установил RF shield |
| `help` | — | печатает protocol и safety warning | всегда |

Флаг capture tool `--rf-read-confirmed` допустим только после физического исключения
GPS/PN532 оператором и отправляет точную длинную команду. Это не security boundary, а
защита от случайного запуска.

Команда RF intentionally длинная: это не security boundary, а защита от случайного
нажатия. Если preflight получает валидный NMEA, probe прекращается до изменения
GPIO5. Отсутствие NMEA не доказывает отсутствие GPS, поэтому подтверждение оператора
всё равно обязательно.

NRF #3 возвращается как `unknown`: GPIO21 одновременно является его CSN и выходом IR
receiver. Сначала `HW-T08` должен измерить idle levels/contention; добавлять output
probe только ради полноты отчёта запрещено.

## Порядок одной HIL-сессии

1. Присвоить плате устойчивый `board-id`; сфотографировать обе стороны, marking ESP
   module, RF shield и подключённые external modules.
2. При полностью отключённых USB и battery выполнить continuity `HW-T02`: отдельно
   GPIO0↔TFT RESET и RESET/EN↔TFT RESET; сохранить прибор, диапазон и сопротивления.
3. Восстановить питание, прошить hash-identified HIL image через явный port.
4. Сохранить boot JSONL через CP2102, выполнить `inventory`; повторить подключение и
   команду через native USB. Это console-часть `HW-T11`.
5. Выполнить `i2c-read`. Для expected PCF8574 сохранить address/value; неизвестный
   IP5306 не идентифицировать догадкой только по ACK.
6. External GPS проверять отдельной assembly командой `gps-listen`, без RF shield
   read. PN532 этим image не пробуется: его безопасный отдельный probe появится после
   подтверждения connector/wiring в `HW-U05`.
7. Полностью снять GPS и PN532, установить RF shield, убрать IR sources и подключить
   logic analyzer/RF detector. Только затем ввести точную RF-команду.
8. Проверить, что CE15/47/14 всё время LOW и detector не видит transmission. Наличие
   register values без этого trace не закрывает `HW-T06`.
9. Отдельно выполнить manual tests HW-T03/HW-T05/HW-T08…HW-T11 по hardware envelope.
10. Сохранить raw JSONL/logic traces/photos без редактирования и рядом создать краткий
    manifest: board-id, firmware hash, wiring, instruments, operator, timestamp и
    verdict каждого test ID.

## Правило verdict

- `pass` — процедура и наблюдаемый результат соответствуют acceptance, raw evidence
  приложено;
- `fail` — получен воспроизводимый несовместимый результат;
- `inconclusive` — измерение выполнено, но не различает варианты;
- `not-run` — evidence нет.

`detected` в JSONL не равно HIL `pass`: это классификация прочитанных bytes. Ошибка,
floating bus или неожиданный module variant фиксируются как `unknown/fail`, но не
«исправляются» расширением списка допустимых значений без нового evidence.
