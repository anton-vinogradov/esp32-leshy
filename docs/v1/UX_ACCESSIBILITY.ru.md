# ESP32-Leshy 1.x — UX-06: карта input и accessibility

*Читать на: [English](UX_ACCESSIBILITY.md) · **Русский***

Статус: **UX-06 принят; упорядоченная и неблокирующая навигация физическими клавишами измерена exact TFT evidence 0.67**.

UX-06 требует, чтобы каждая текущая primary operation была доступна пятью
физическими кнопками, а любое состояние и focus различались без цвета. Diagnostic
automation входит в ту же boundary нормализованных Actions и не заменяет физический
control.

## Физические и нормализованные controls

| Физическая кнопка | Вход PCF8574 | Normalized Action | Стабильное значение |
|---|---:|---|---|
| Вверх | P7, active low | `Up` | предыдущий enabled или visible choice |
| Вниз | P5, active low | `Down` | следующий enabled или visible choice |
| Влево | P3, active low | `Left` | Back/Cancel; safety-first Stop во время TX |
| Вправо | P4, active low | `Right` | войти/открыть; то же направление внутрь, что Select |
| Выбор | P6, active low | `Select` | войти/открыть выбранный item; context action в конечном destination |
| только diagnostic | — | `Back` | та же boundary возврата, что physical Left |

Input task читает входы каждые 5 ms, использует debounce 12 ms, выдаёт одно action
на stable press, требует release перед повтором и отклоняет одновременные edges как
ambiguous. Retained физический тест 50 нажатий подтверждает по 10 нажатий каждой
кнопки, 50/50 press/release/dispatched events, zero errors/ambiguity/drops и maximum
sample gap 5 ms.

## Touch дополняет кнопки, а не создаёт вторую навигацию

Панель XPT2046 выдаёт одно событие на откалиброванное нажатие и требует debounced
release перед следующим. Касание активирует только видимую строку или явный control
под пальцем. Home показывает четыре строки 216×46 px с gap 5 px; общие choices — до
трёх строк 216×46 px с gap 6 px. Поэтому каждый текущий touch target имеет высоту
не менее 44 px.

Header, строка технического input-status и footer 26 px никогда не являются touch
targets. Footer остаётся подсказкой физических клавиш, а не экранными кнопками.
Touch намеренно не имеет Back-жеста или Back-target: стабильный Back/Cancel —
физическая клавиша Влево. Касание строки проходит через тот же bounded путь
Up/Down плюс Select, что keypad, поэтому экран не получает отдельное состояние
hit-test-навигации.

## Карта actions экранов

| Контекст | Up/Down | Select | Right | Left/Back |
|---|---|---|---|---|
| Home | переместить focus | открыть enabled item | открыть enabled item | без скрытой mutation |
| Язык | выбрать EN/RU | применить и сохранить | применить и сохранить | Home |
| Режимы Self-Test | выбрать Quick/Full | run/open preflight | run/open preflight | Home |
| Self-Test preflight/result | — | запустить доступные checks | запустить доступные checks | к режимам |
| Survey setup | — | Start | Start | cancel/Home |
| Survey running list | переместить focus observation | Detail | Detail | cancel без commit |
| Survey detail во время running | — | Stop/save | Stop/save | list |
| Survey result/error | — | — | — | Home без скрытого retry |
| Library list | переместить focus Session | Detail | Detail | Home |
| Library detail | — | Export | Export | list |
| Export ready | — | — | — | detail |
| Diagnostics | — | — | — | Home |

Footer — пространственная карта controls, а не предложение: Left занимает левую
ячейку, Up/Down — среднюю, Right+OK — правую. У каждой активной ячейки есть
нарисованный direction icon/key legend и одна локализованная action label 12 px в
footer высотой 26 px.
Техническое состояние RF/storage остаётся в body экрана. Недоступный Home item не
открывается и показывает причину, а не полагается на muted color.

## Контракт состояния без цвета

- Focus показан постоянным outline и заполненным chevron; palette contrast — только
  дополнительное evidence.
- Running, committed, error, pass, fail, blocked, persistent/volatile, simulated,
  passive RX-only и unavailable написаны на экране явно.
- Warning, positive и danger colors никогда не несут единственный signal state.
- У каждого вложенного экрана есть physical Left path; позже TX добавит постоянное
  safety-first правило Stop без смены этой кнопки.

`tools/check_ui_accessibility_contract.py` связывает эту карту с source, geometry,
localized state strings, native tests и retained physical-key evidence. Затем exact
candidate `0.56.0-ui-accessibility-measure` через public Actions перемещает focus по
всем пяти Home rows, Survey, Library, Language и обоим choices Self-Test на actual
TFT. Pixel audit находит outline 210 px и минимум 67 пикселей chevron в каждой
focused row; Quick остаётся 8/8, final owner/lease — `none`/`0`.
`E-BUILD-058`/`E-HIL-080`/`E-UX-006` поэтому принимают UX-06, но не UX-07,
`DEMO-S2` или release gate.

Exact candidate `0.64.0-spatial-navigation-measure` возвращает проверенную в 0.x
пространственную модель и удаляет prose footer. `E-AUTO-028` проводит Right и
Select по одинаковым inward paths, Left и diagnostic Back — по одинаковым return
paths, Up/Down — по bounded selection. Девять exact EN/RU TFT frames проверяют
40-px трёхъячеечный component на Home, Diagnostics, Survey setup, Library
list/detail, Language и Self-Test. Survey Stop/save теперь находится внутри Detail,
поэтому Right больше не противоречит своему стабильному значению «внутрь».
`E-BUILD-065`/`E-HIL-088`/`E-UX-009` уточняют принятый UX-06 без promotion S3 или
release.

Exact candidate `0.65.0-compact-incremental-ui-measure` сохраняет эту mapping и
уменьшает footer с 40 до 26 px. Одновременно возвращено правило repaint из 0.x:
Up/Down перерисовывает только старую и новую непрозрачные строки; полный переход
очищает лишь content ниже уже нарисованного header, а interactive path больше не
вызывает `fillScreen`. Восемь selection transitions Home/Language/Self-Test занимают
19,901–28,981 ms на реальной панели при fail-closed ceiling 40 ms вместо замеченных
63,615 ms whole-page redraw. Девять exact frames, 21 transition, неизменный heap и
чистые input/buzzer/lease связаны `E-BUILD-066`/`E-AUTO-029`/`E-HIL-089`/`E-UX-010`.

Exact candidate `0.66.0-ordered-key-repaint-measure` перенёс правило порядка из
0.x, но user acceptance всё ещё failed. Render-only lane показал 13,927–23,043 ms,
однако не учитывал синхронную USB/UART telemetry после repaint; десять физических
нажатий дали queue high-water 5/64 и тот же отложенный перескок, который заметил
пользователь.

Exact candidate `0.67.0-nonblocking-keypath-measure` удаляет все serial writes из
physical hot path и публикует queue/end-to-end timing только по запросу
`input.state`. Пользователь подтвердил исчезновение lag после 75 физических
нажатий; retained run фиксирует 75/75/75 press/release/dispatched events, queue
high-water 1, maximum queue latency 1,256 ms, zero errors/drops/serial writes и
16,703 ms end-to-end для последнего изменившего focus нажатия. Девять TFT frames/21
transition остаются exact, восемь incremental renders занимают 13,972–23,058 ms
(`E-BUILD-068`/`E-AUTO-031`/`E-HIL-091`/`E-UX-012`).
