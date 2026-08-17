# ESP32-Leshy 1.x — автоматизация UI и визуальные evidence

*Читать на: [English](UI_AUTOMATION.md) · **Русский***

Статус документа: **обязательный verification contract S2; transport подтверждён
на measurement target S1**.

Проверки UI не должны требовать, чтобы оператор постоянно фотографировал дисплей и
нажимал кнопки. Физический и диагностический input входят в один обработчик actions;
диагностический transport может наблюдать UI и управлять им, но не может напрямую
менять состояние экрана.

## Контракты

### Единый путь actions

Нормализованные actions: `up`, `down`, `left`, `right`, `select` и `back`. Frontend
PCF8574 каждые 5 ms читает active-low inputs в отдельной задаче, требует 12 ms
стабильного состояния и помещает нормализованные события в bounded-очередь из 64
элементов. UI loop и локальная serial-команда `ui.key <action>` вызывают один
allocation-free controller, поэтому перерисовка TFT больше не блокирует physical
sampling. Ответ содержит принятое action, признак изменения, текущую
страницу/selection и монотонно растущую revision UI.

`input.state` публикует valid/error samples, raw/stable transitions, счётчики каждой
кнопки, maximum sample gap, ambiguity, queue depth и queue drops. Неверное чтение
I2C не меняет debounced state; для следующего action той же кнопки обязателен
стабильный release. Одновременный front нескольких кнопок fail closed как ambiguous.

`ui.state` наблюдает то же публичное состояние UI, не меняя его. Автоматизация не
вызывает setter конкретного экрана, не обходит cleanup по Back и не создаёт отдельное
тестовое меню. Когда продуктовый Navigator заменит probe controller, transport
останется на границе нормализованных Actions.

`ui.language en|ru` выбирает язык через тот же persistent `LanguageController`,
который использует публичный экран Язык. Это automation-вход в product operation,
а не отдельный renderer override; `ui.state` сообщает active language и selection
экрана Язык.

### Захват реального дисплея

`ui.capture` читает GRAM ILI9341 тайлами по четыре строки и возвращает:

1. NDJSON-запись `frame_begin` с шириной, высотой, форматом, числом байт и revision;
2. ровно `width × height × 2` байт пикселей `rgb565be`;
3. NDJSON-запись `frame_end` с теми же числом байт и revision.

Target 240×320 передаёт 153 600 байт. Tile buffer занимает 1 920 B; захват не требует
PSRAM или постоянного framebuffer. Хост преобразует пиксели в PNG и сохраняет
SHA-256 исходных RGB565 и PNG.

Это подтверждает содержимое контроллера дисплея, ориентацию, rendering и состояние
навигации. Оно не доказывает яркость подсветки, углы обзора, повреждение панели,
touch alignment или физическую калибровку цвета — для них остаётся физический HIL.

## Воспроизводимый host path

Используется Python environment, где уже есть serial dependency PlatformIO:

```sh
"$HOME/.platformio/penv/bin/python" tools/capture_1x_ui.py \
  --port /dev/cu.usbmodem2101 \
  --keys down,down,select \
  --output ui-automation.png
```

Утилита открывает native USB без переходов DTR/RTS, выполняет actions, читает пиксели
TFT, проверяет доступность той же revision после capture и создаёт
`ui-automation.png` вместе с `ui-automation.png.json`. Сценарий держит одно
соединение, если нужны промежуточные кадры; подключение и отключение evidence client
не должны перезагружать плату.

## Приёмка

| ID | Обязательный результат | Evidence |
|---|---|---|
| UI-HIL-A1 | Каждому физическому navigation action соответствует то же диагностическое action | controller unit test + physical/serial traces |
| UI-HIL-A2 | Неверное action отклоняется без изменения state и reboot | negative protocol test |
| UI-HIL-A3 | Back проходит через публичный Navigator и сохраняет семантику release | state trace + resource ownership trace |
| UI-HIL-A4 | Byte count, dimensions, format и begin/end revision совпадают | host protocol check |
| UI-HIL-A5 | После capture state доступен и имеет captured revision | JSON evidence sidecar |
| UI-HIL-A6 | Golden/snapshot comparison не игнорирует критичный текст или selection | host visual test каждого screen/state |
| UI-HIL-A7 | Connect, capture и disconnect UI client не перезагружают плату | reset counter/revision continuity trace |
| UI-HIL-A8 | 10 обычных нажатий каждой physical кнопки дают ровно 50 presses и 50 releases, по 10 каждого normalized action, 50 dispatched public UI actions, без ambiguity, I2C error, duplicate и queue drop | guided physical burst + machine-checked [artifact до/после](../../tests/hil/evidence/board-01-keypad-0.43.json) |

Каждый reference workflow получает автоматизированный UI scenario по мере появления
его экранов. Участие оператора остаётся только для evidence, которое не может дать
контроллер дисплея, а не для обычного прохода по меню.

Встроенный [Self-Test](SELF_TEST.ru.md) использует ту же boundary normalized Action
и capture. Его Quick и Full/Guided plans не вводят screen setters или второй
test-only navigation path; release automation выбирает те же versioned check IDs и
независимо проверяет report, frames и final cleanup.

## Текущее evidence

Board-01 со сборкой `0.3.0-ui-automation-measure` приняла diagnostic actions через
тот же `UiController`, что и пять active-low входов PCF8574. Stateful trace перешёл
с home на Automation, получил 240×320 RGB565 и после capture вернул ту же revision.
Второе подключение сохранило revision/state, когда client подавил DTR/RTS. Это
подтверждает transport и probe navigation shell.

Первый manifest-driven `device-smoke` сборки `0.35.0-storage-product-measure` затем
автоматически перепрошил board-01 exact candidate, дождался готовности за 502 ms,
прошёл Home→Diagnostics→Back через публичные Actions и снял три real-TFT кадра.
Оба стабильных Home совпали с compressed RGB565 golden попиксельно; Diagnostics
совпал вне явно зафиксированной области динамических heap/timing значений. Bundle
содержит raw frames, PNG, state/serial traces, manifest и SHA-256 index; отдельный
fail-closed verifier подтвердил его как unsigned development evidence, но не как
release-eligible attestation. Это закрывает воспроизводимый automation path
UI-HIL-A3…A6 для текущих экранов, но ещё не финальные продуктовые экраны, внешний
вид физической панели или NFR-001/NFR-002/NFR-010 целиком.

Повторный `device-smoke` candidate 0.36 сохранил те же goldens и снова дал zero
pixel mismatch для Home/Diagnostics/Back, одновременно связав кадры с полным
firmware-reported ELF SHA-256 запущенного образа (`E-HIL-042`).

Candidate 0.37 повторил zero mismatch и дополнительно ограничил все Actions/captures
одним device-acknowledged run ID от UI revision 0 до 2 (`E-HIL-043`).

Candidate 0.38 расширил suite до product Survey→commit→Library→export: семь новых
real-TFT goldens и три прежних кадра совпали без единого пикселя; bounded serial
query проверил export generation 2/3 observations/0 drops, а финальный Back вернул
owner `none`/lease `0` (`E-HIL-046`). Теперь автоматизация проверяет первый
продуктовый вертикальный срез, хотя источник и store в этом UI-run остаются
simulated/RAM/RF-off.

Candidate 0.39 сделал состояние pipeline частью screen/state contract: Running
показывает FIFO depth/high-water/drop, Result сохраняет high-water/drop, а HIL
assertions требуют received/forwarded 3/3 и trigger none→stop. Семь прежних 0.38
goldens сохранены с version suffix; семь кадров 0.39 заново сняты с TFT, просмотрены
и затем дали zero mismatch в полном revision-3 run (`E-HIL-047`).

Candidate 0.40 не меняет визуальный contract: revision-4 добавляет перед
навигацией bounded product-admission query и повторно использует те же десять
reviewed TFT comparisons с zero mismatch. Query доказывает, что без explicit Start
и trusted persistent store нет скрытого hardware/radio/storage действия или
simulated fallback (`E-HIL-048`).

Candidate 0.41 заменил унаследованный 35 ms single-sample edge detector после
наблюдения оператора примерно одного принятого нажатия из десяти. Host tests покрыли
bounce, неверные чтения, held key, стабильный release, все пять mappings, ambiguous
chord и wrap `millis()`. Automatic run revision 5 прошёл, но первый physical stress
опроверг достаточность transition-очереди 16: frontend поймал 43 presses и 43
releases с maximum gap 5 ms, а очередь потеряла 46 transitions. Candidate 0.42
оставил в очереди только presses и batch-применял state до redraw; automatic run
прошёл, но structured physical attempt поймал 48 presses, доставил только 27 и
потерял 21 press. Эти failures сохранены как `E-HIL-050/051`, а не скрыты
serial-only тестом.

Candidate 0.43 рассчитывает ordered press queue на весь acceptance burst 50,
применяет накопившийся state до одной redraw и публикует одну diagnostic record на
batch. `device-smoke` revision 6 сохранил полный workflow и десять zero-mismatch TFT
frames. Затем UI-HIL-A8 прошёл на том же exact app: каждая кнопка дала 10,
presses/releases/dispatched — 50/50/50, UI revision выросла на 50, maximum sample
gap 5 ms, queue high-water всего 6/64, errors, ambiguity, queue depth и drops — нули
(`E-HIL-052`).

Candidate 0.52 добавляет semantic visual roles, не меняя Action/capture boundary.
Exact product-aware run сохранил setup/running/result/export и финальные Home/Library
frames, связал их с app `39fc2c92…43ace` и завершился с 9/9 forwarded, zero drops и
owner/lease `none`/`0` (`E-HIL-076`). Pixel audit также обнаружил и закрыл footer
overflow. Это принимает UX-03 и часть UX-07, но ещё не доказывает Self-Test screens
или оставшиеся dialog/error/degraded states.

Candidate 0.53 затем доходит до последнего пункта Home только через normalized
Actions, снимает mode/Quick result/Full preflight/blocked result/final Home и
связывает те же стабильные check IDs в `leshy.self_test.report.v1`. Первый capture
regression обнаружил и сохранил loop-task stack panic в расширенной state record;
перенос обоих больших records в один static bounded workspace исправил его. Exact
rerun проходит Quick 8/8 и возвращает owner/lease `none`/`0`; Full остаётся визуально
и machine-readably blocked на incomplete capability coverage (`E-HIL-077`).

Candidate 0.55 добавляет единый каталог EN/RU и persistent экран Язык, не меняя
Action/capture boundary. Exact run сохраняет русские Home, Diagnostics, Survey,
Library, Language, Self-Test и Quick result, а также английские Home/Language,
подтверждает сохранение русского после flash/reset и завершает Quick 8/8 с zero
input errors/drops, buzzer LOW и owner/lease `none`/`0`
(`E-HIL-079`/`E-UX-005`).

Candidate 0.56 добавляет outline и заполненный chevron каждой focused shared/menu/list
row. Двенадцать exact current TFT captures проходят Home, Survey, Library, Language,
оба choices Self-Test, Quick result и final cleanup только через normalized Actions.
Standard-library pixel audit проверяет cue независимо от цвета и объединяет его с
retained physical-key acceptance 50 events (`E-HIL-052/080`, `E-UX-006`).

Candidate 0.57 тем же путём выбирает последний пункт Home и Full/Guided, затем
снимает preflight, dialog/confirm, unavailable, degraded, error, running, blocked
result и финальный Home. Checker связывает все девять frames 240×320 с точными
revisions и identity candidate, доказывает geometric square cue каждой state card и
проверяет plan 2 как 9 pass/0 fail/1 blocked с zero side effects и final owner/lease
`none`/`0` (`E-HIL-081`/`E-UX-007`). Это принимает UX-07; combined `DEMO-S2`
остаётся stage gate.
