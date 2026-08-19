# ESP32-Leshy 1.x — UX/UI baseline

*Read in: [English](UX_UI_BASELINE.md) · **Русский***

Статус: **S1 product UX direction и S2 visual gate приняты**. Low-fidelity
UX-01/UX-02 зафиксированы, UX-03…UX-07 подтверждены evidence, а воспроизводимый
`DEMO-S2` проходит на exact candidate 0.58. UX-08 повторяется в каждом следующем
Stage Demo.

Документ определяет, когда обсуждается опыт пользователя и когда внешний вид
становится ограничением реализации. Он не подменяет
[эталонные сценарии](REFERENCE_WORKFLOWS.ru.md) и не хранит текущее состояние.

## Два последовательных решения

### S1 — product UX direction

До закрытия S1 согласуются:

- product-first архитектура `Обзор / Захват / Библиотека / Цели / Лаборатория /
  Устройство`; служебные функции находятся под последним пунктом `Устройство` как
  `Настройки / Самопроверка / Диагностика / О системе`, а не конкурируют на Home;
- основные пути J-01…J-06 и место каждого `CAP-*`;
- единая семантика Start/Stop, Select, Back, confirm, cancel и panic;
- обязательные состояния каждого пути: unavailable, empty, loading, running,
  partial/degraded, error, confirm, success;
- какие сведения должны помещаться на TFT, а какие доступны в Detail/companion;
- доступность без цвета, кнопочное управление, EN/RU и пределы touch.

Это обсуждение отвечает на вопрос «как человек решает задачу» и не фиксирует
пиксельные размеры раньше проверки реального дисплея.

### S2 — visual and interaction baseline

На независимой target и реальном TFT фиксируются:

- сетка 240×320, safe areas, вертикальный ритм и плотность списков;
- роли typography, иерархия заголовок/list/detail/metadata и обрезка EN/RU;
- palette и contrast для normal/selected/disabled/warning/error/TX без зависимости
  только от цвета;
- компоненты Home, status bar, list row, detail field, graph, dialog, progress и
  unavailable explanation;
- mapping кнопок/touch, focus, long press, debounce и постоянный путь Back;
- motion/update budgets, чтобы радио и storage никогда не блокировали UI;
- визуальный TX-индикатор, timeout и panic, даже если активные действия появятся в S7.

После gate изменение базового компонента или interaction pattern требует обновления
baseline, TFT evidence и затронутых acceptance tests.

Self-Test следует отдельному [product contract](SELF_TEST.ru.md): явные Quick и
Full/Guided используют обычные Actions и компоненты. Это второй видимый пункт внутри
`Устройство`, а не boot screen, скрытое service menu или release-only serial path.

## Обязательные артефакты baseline

| ID | Артефакт | Проверяемый результат |
|---|---|---|
| [UX-01](UX_SCREEN_MAP.ru.md) | Карта экранов и Actions | Каждый `CAP-*` имеет вход, success/error/cancel и путь назад |
| [UX-02](UX_STATE_MATRIX.ru.md) | State matrix | Для основных экранов определены empty/loading/running/degraded/error/confirm states |
| UX-03 | Design tokens | Зафиксированы роли цвета, текста, spacing, borders и focus, а не случайные hex по экранам |
| UX-04 | Component sheet | Общие элементы отрисованы на 240×320 и переиспользуются между радио |
| UX-05 | EN/RU content fit | Критические строки помещаются или имеют определённое безопасное сокращение |
| UX-06 | Input/accessibility map | Все основные действия доступны кнопками; состояние различимо без цвета |
| UX-07 | Real-TFT evidence | Home, List, Detail, dialog, error/degraded и running state сняты через UI automation |
| UX-08 | Usability walkthrough | WF-01…WF-05 пройдены на board без скрытых serial-only действий |

## UX-03 — visual tokens, кандидат S2

Первый implementation slice находится в `ui/VisualTheme.h`. Экраны используют
семантические роли, а не TFT-константы или локальные RGB. UX-03 принят как artifact;
полный visual baseline S2 всё ещё требует UX-04…07.

| Роль | RGB | Назначение |
|---|---|---|
| Canvas / Header | `#07100C` / `#1A3A28` | спокойный тёмный фон и устойчивый brand anchor |
| Surface / Focus | `#0D1611` / `#1A4E34` | строки и текущий keyboard focus |
| Primary / Secondary / Muted | `#E7CF8F` / `#C6D0C8` / `#68756B` | иерархия текста без зависимости от размера |
| Focus | `#F5C542` | выбранный объект или primary Action, не warning |
| Positive / Warning / Danger | `#55D98A` / `#F7A641` / `#F05D5E` | состояние всегда дублируется текстом/формой |

Текущая geometry фиксирует 240×320, edge 12 px, content width 216 px, компактный
information/navigation header 26 px, radius 4 px, четыре Home row 216×60 px с gap
5 px, divider y=293 и footer physical-key hints высотой 26 px. Footer не может
перекрывать product content; header/footer никогда не являются touch targets.

Exact candidate 0.52 принял historical geometry с header 42 px,
y=236 и input status как implementation evidence: шесть retained
TFT frames 240×320 связаны с candidate, а standard-library pixel audit проверяет
полную geometry brand/divider/input и пустые bottom guard rows. Audit обнаружил
wrapped Library footer за пределами его region; текст сокращён, image пересобран,
прошит и снят заново. UX-07 остаётся partial: ещё открыты dialog и
unavailable/degraded/error states, а также EN/RU matrix.

## UX-04 — общий component sheet

Allocation-free контракт `ui/UiComponents.h` — component sheet 240×320, который
используют product screens. Он владеет rectangles и tones компонентов; экраны —
content и state. Bounds и отсутствие overlap проверяются compile-time assertions и
native tests, поэтому экран не может незаметно залезть content в фиксированный footer.

| Компонент | Геометрия/роль | Текущее переиспользование |
|---|---|---|
| Header + title | information/status bar 240×26; на Home — локализованные brand/version, на вложенных экранах — название текущей страницы в той же панели | все product views |
| Home row | 216×60; четыре увеличенных touch target образуют прокручиваемое visible window над footer | Home из семи jobs и меню «Устройство» из четырёх пунктов |
| Choice row | 216×52; до трёх увеличенных choices помещаются над footer | Quick / Full-Guided, Язык, Survey plan/source/filter |
| Metric row | пять result slots 216×28 | Full preflight и Quick/Full result |
| Footer divider | фиксирован на y=293 | каждый interactive screen |
| Пространственная навигация | три action cell 70×26 для физических клавиш; visible raw-input diagnostic отсутствует | каждый interactive screen и HIL |

Exact candidate `0.54.0-ui-components-measure` принимает UX-04 через
`E-BUILD-056`/`E-HIL-078`/`E-UX-004`: Home и Self-Test используют одинаковые
renderer primitives; четыре actual TFT frame проходят pixel/trace checker; Quick
проходит 8/8; input имеет zero errors/drops, buzzer остаётся LOW, Back возвращает
owner/lease в `none`/`0`. Тогда это приняло component system; UX-05…07 и `DEMO-S2`
ещё оставались открыты.

Touch corrective 0.88 сохраняет принятый component vocabulary, но заменяет пять
Home rows 28 px на visible window из трёх строк 46 px и стандартизирует choice rows
на 46 px. Header/footer исключены из hit testing; footer остаётся только подсказкой
физических клавиш, а единственным Back control остаётся physical Влево.

## UX-05 — размещение EN/RU

`ui/UiStrings.def` — единый allocation-free каталог всех текущих строк S2 renderer,
кроме неизменяемого бренда `LESHY` и компактных protocol-status tokens. Сейчас он
задаёт 134 стабильных ID, варианты
EN и RU (всего 268 строк) и пиксельный budget каждого места использования. Exact
0.63 измерил прежний каталог prose-footer из 127 ID; 0.64 заменяет его 19 context
sentences на 15 компактных labels пространственных actions.
`tools/generate_ui_gfx_font.py` воспроизводимо генерирует faces, а
`tools/check_ui_language_contract.py` измеряет их metrics, отклоняет отсутствующий
перевод или переполнение и проверяет, что renderers не возвращают локальные
user-facing literals.

Оба языка теперь используют официальный vendored variable source Roboto Condensed с
лицензией OFL и pinned SHA-256. Генератор выбирает named instance Medium (weight 500)
и создаёт body 16 px и metadata 12 px для нужного ASCII/Cyrillic range без
runtime-загрузки шрифта или heap allocation. `Устройство → Настройки` открывает
`Язык`; выбор EN/RU применяется сразу и сохраняется в NVS namespace `leshy1-ui`, key
`lang.v1`; команда `ui.language en|ru` проходит через ту же controller boundary,
что и экран. Прежний source PT Sans Narrow и exact evidence 0.55 остаются historical
provenance, а не текущим face.

UX-05 принимает encoding coverage, persistence, geometric fit и выбранный face для
малого raster; physical-panel optics и особенности зрения остаются частью usability
walkthrough. Замена на Roboto потребовала восьми безопасных сокращений. После них
все текущие 246 вариантов помещаются в declared pixel budgets generated glyphs без
overflow; retained typography run 0.63 остаётся historical proof 254/254.

Exact candidate `0.55.0-ui-language-measure` принимает UX-05 через
`E-BUILD-057`/`E-HIL-079`/`E-UX-005`. Actual TFT captures 240×320 охватывают Home,
Diagnostics, Survey, Library, Language, Self-Test и Quick result на русском, а также
Home и Language на английском. Русский сохраняется после exact-candidate flash/reset;
Quick остаётся 8/8 с zero RF/storage/buzzer side effects, input errors и drops равны
нулю, buzzer остаётся LOW, final owner/lease — `none`/`0`. Retained artifact и
независимый checker связывают frames, каталог, source шрифта, hashes candidate,
state trace и final cleanup. На тот момент UX-06/UX-07 и `DEMO-S2` оставались
открыты.

Exact candidate `0.63.0-roboto-condensed-ui-measure` заменяет только typography layer
через `E-BUILD-064`/`E-AUTO-027`/`E-HIL-087`/`E-UX-008`; Stage gate не переоткрывается
и не продвигается. Идемпотентный device runner снимает 18 actual frames 240×320:
русские Home/Diagnostics/Survey/Library detail/Language/Self-Test, Full preflight,
все пять common states и оба result, английские Home/Language и pixel-identical
финальный русский Home. Quick проходит 8/8, Full остаётся честно 9/10 с одним blocked
capability-coverage check, radio/storage/buzzer side effects и input errors/drops
равны нулю, heap до и после остаётся 272 688/208 912/188 720 B, buzzer LOW, final
owner/lease `none`/`0`. Retained checker пересчитывает официальный TTF, OFL,
generated face, exact candidate, runner, каждый frame/trace и final cleanup.

## UX-06 — кнопки и доступность без цвета

Обязательная [карта input/accessibility](UX_ACCESSIBILITY.ru.md) связывает все пять
физических PCF8574 keys и diagnostic `Back` с normalized Actions каждого текущего
экрана. Выбранная row теперь имеет геометрические outline и заполненный chevron в
дополнение к palette contrast. Unavailable, running, committed, error, pass, fail,
blocked, persistent/volatile, simulated и passive states остаются явным текстом.

Exact candidate `0.56.0-ui-accessibility-measure` принимает UX-06 через
`E-BUILD-058`/`E-HIL-080`/`E-UX-006`. Retained physical evidence связывает по 10
нажатий каждой кнопки с 50/50/50 presses/releases/dispatched и zero errors,
ambiguity или drops. Exact TFT run через public Actions перемещает focus по всем
пяти Home rows, Survey, Library, Language и обоим choices Self-Test; pixel checker
доказывает outline/chevron независимо от цвета. Quick остаётся 8/8, input healthy,
buzzer LOW, final owner/lease — `none`/`0`. На той точке evidence UX-07 и
`DEMO-S2` оставались открыты.

Exact candidate `0.64.0-spatial-navigation-measure` уточняет UX-06 через
`E-BUILD-065`/`E-AUTO-028`/`E-HIL-088`/`E-UX-009`. Footer 40 px теперь содержит
три пространственные ячейки: Left/Back, Up+Down/Select и Right+OK/Enter. Direction
icons рисуются геометрически, action labels используют Roboto Condensed Medium 16,
а техническое RF/storage state остаётся в body и не конкурирует с controls. Right
и Select открывают одинаковые destinations Home и вложенной Library; Survey
Stop/save перенесён внутрь Detail, поэтому у стабильной navigation model больше нет
исключения на уровне списка. Девять exact TFT frames, 15 public transitions,
неизменный heap, healthy input, buzzer LOW и финальный русский Home с lease 0
проверяются независимо.

Exact candidate `0.65.0-compact-incremental-ui-measure` сохраняет ту же mapping трёх
ячеек, но использует labels 12 px в footer 26 px. Изменение selection теперь
перерисовывает только старую/новую rows, никогда не очищает весь экран и публикует
измеримые diagnostics `render_mode`/`render_us`. Exact TFT lane доказывает восемь
инкрементальных transitions за 19,901–28,981 ms, девять финальных frames, 21 public
transition и zero drift heap/input/resources (`E-BUILD-066`/`E-AUTO-029`/
`E-HIL-089`/`E-UX-010`).

Exact candidate `0.66.0-ordered-key-repaint-measure` восстановил правило «одно
событие — один кадр», но failed user acceptance: синхронная serial telemetry всё
ещё выполнялась после render timer. Десять нажатий достигли queue high-water 5/64 и
заметно тормозили.

Exact candidate `0.67.0-nonblocking-keypath-measure` удаляет эту USB/UART работу из
hot path. Пользователь подтвердил отзывчивую навигацию на 75 физических нажатиях;
high-water равен 1/64, maximum queue latency — 1,256 ms, последнее изменившее focus
нажатие — 16,703 ms end-to-end, serial writes/errors/drops равны нулю. Exact TFT
rendering остаётся 13,972–23,058 ms (`E-BUILD-068`/`E-AUTO-031`/`E-HIL-091`/
`E-UX-012`).

## UX-07 — evidence common states на реальном TFT

Exact candidate `0.57.0-ui-state-evidence-measure` принимает UX-07 через
`E-BUILD-059`/`E-HIL-081`/`E-UX-007`. Последний пункт Home открывает Self-Test без
boot detour, выбирает Full/Guided через обычные Actions и показывает preflight, а
затем явные карточки dialog/confirm, unavailable, degraded, error и running. Каждая
карточка сочетает текст, фиксированный квадратный outline и semantic tone;
machine-checker связывает девять actual TFT captures 240×320, разные framebuffer
hashes, точные Action/state revisions и geometry карточки.

Тот же run выполняет plan version 2. Восемь Quick platform checks и
`full.ui.common_states` проходят, а `full.capability.coverage` честно остаётся
blocked: 9 passed, 0 failed, 1 blocked. Radio TX, storage writes и buzzer activations
равны нулю; heap — 272 760/224 280/188 792 B, input errors/drops равны нулю, GPIO2
LOW, final owner/lease — `none`/`0`. Это закрывает real-TFT common-state artifact,
но не полный capability plan или release gate. Combined platform gate закрывает
последующее exact 0.58 evidence `DEMO-S2`.

## Уточнение product-first меню

Exact candidate `0.90.0-product-menu` реализует финальную верхнеуровневую
information architecture, не переоткрывая baseline S2. Home теперь содержит
`Обзор / Захват / Библиотека / Цели / Лаборатория / Устройство`; незавершённые
Цели и Лаборатория явно disabled, а Устройство содержит Настройки, Самопроверку,
Диагностику и О системе. Общие строки 216×46 px работают и с physical navigator,
и с touch. Footer 26 px остаётся легендой физических клавиш и не является touch
target; только Left возвращает child→Устройство→Home.

`E-BUILD-091`/`E-AUTO-055`/`E-HIL-115`/`E-UX-014` сохраняют восемь actual TFT
states 240×320, exact bytes candidate/runner, touch chrome misses, nested parent
state, heap 231 772/166 812/147 460 B и final owner/lease `none`/`0`. Первый HIL run
тоже сохранён как runner-only ошибка ожидания revision; для проходящего retry
candidate не перепрошивался.

## Компактный status и уточнение content

Exact candidate `0.91.0-clean-status` удаляет visible input diagnostic `RAW 0xFF`
из product shell. Освободившееся место меняет viewport Home с трёх на четыре строки
216×46 px и переносит footer divider на y=282; последние 26 px остаются только
пространственной легендой физических клавиш. Header 34 px сохраняет короткий anchor
`LESHY` и два текстовых состояния:

- `SD OK` означает, что enrolled medium совпал, read-only recovery гарантирован и
  cleanup завершён; `SD !` обозначает fault enrolled media, `SD --` — отсутствие
  заявления о готовом enrolled medium;
- `RF RX` означает, что реально работает receiver product Survey, Wi-Fi Capture,
  spectrum nRF24 или spectrum CC1101; `RF --` — receive path не активен.

Battery percentage или power state не показываются до появления надёжной measured
capability. `E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015` связывают восемь menu
и шесть RF TFT states. Exact framebuffer crops различают настоящий receive nRF24 и
pause/Home; тот же run доказывает zero TX/storage side effects, invariant heap и
final lease 0.

## Full-width RF views и контекстный header

Exact candidate `0.92.0-spectrum-views` заменяет повторяющийся brand из shell 0.91:
`LESHY` виден только на Home; на каждом вложенном экране левая часть header показывает
текущий раздел или задачу. Оба receiver workflow дают режимы Спектр и Водопад.
Up/Down меняет вид, Right/OK ставит на паузу или продолжает, Left останавливает и
возвращает. Live graph использует x=0…239 и y=62…277, компактный metrics overlay и
axis без декоративной рамки. Диапазон CC1101 выбирается обычным четырёхстрочным меню
315/433/868/915 МГц.

Waterfall — fixed allocation-free ring на 112 строк; во время acquisition добавляется
только новейшая экранная строка. `E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/
`E-RADIO-005` связывают 22 TFT states, 32 накопленные строки nRF24, 16 строк CC1101,
стабильные pause/resume, все CC bands, invariant heap/storage и final lease 0. Это
визуализация activity/RSSI, а не calibrated analyzer.

Candidate `0.96.0-compact-ui-waterfall` отделяет визуальную временную шкалу от
длительности hardware sweep конкретного приёмника. nRF24 и каждый диапазон CC1101
теперь делают snapshot последнего receive-only spectrum по единому cadence 26 785
мкс: 112 строк занимают не более 3 000 000 мкс и заполняют всю область graph. Exact
physical acceptance измеряет, а не выводит из констант, timing на nRF24 и
315/433/868/915 МГц: host-observed fill равен 2,905/2,927/2,918/2,916/2,924 s,
device telemetry остаётся в диапазоне 2,814…2,857 s. Все paths достигают 112 строк
с zero TX/storage side effects, unchanged storage, stabilized invariant heap и
final lease 0 (`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/`E-RADIO-007`).

## Home из реализованных задач и однокомандный physical checkpoint

Exact candidate `0.93.0-product-menu` заменяет executable-часть Home 0.90.
Показаны только реализованные задачи: Wi-Fi, Bluetooth, 2.4 ГГц, Sub-GHz,
Захват, Библиотека и Устройство. Будущие Цели/Лаборатория остаются в roadmap 1.0,
а не dead entries меню. Wi-Fi/BLE открывают свою one-source строку Start,
2.4 ГГц запускает live screen nRF24, Sub-GHz — chooser CC, а Устройство остаётся
последним service container.

Checkpoint на подключённой плате теперь запускается одной foreground-командой:

```sh
./tools/verify_connected_candidate.sh
```

Она требует clean committed candidate и ровно одну подключённую плату, затем выполняет
host tests, documentation checks, exact build, ровно одну прошивку, обычные public
Actions, автоматические TFT captures и independent verifier. Принятый run потребовал
zero ручных нажатий и сохранил 13 реальных кадров, все семь открываемых пунктов,
source masks Wi-Fi/BLE 1/2, наполненные водопады nRF24/CC1101, stable pause/resume,
unchanged generation 95/0, invariant heap и final owner/lease `none`/`0`
(`E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/`E-RADIO-006`).

## Локализованный Home и видимая версия

Exact `0.94.0-home-identity` делает identity корневого экрана явной и не
смешивает её с навигационным контекстом. Только Home показывает `LESHY` на
английском или `Леший` на русском. Ни About, ни строки вложенных экранов не
повторяют эти варианты бренда; вложенные headers по-прежнему называют текущий
раздел или задачу.

Тот же Home header высотой 34 px показывает прямо под локализованным названием
SemVer core, полученный из build identity (`v0.94.0`). Полный идентификатор
`0.94.0-home-identity` остаётся доступен в «О системе» и диагностике. Индикаторы
SD/RF остаются справа и не меняют семантику. Connected-candidate workflow обязан
автоматически снять английский и русский Home, восстановить русский язык и связать
кадры с exact flashed candidate без ручных нажатий. Принятый run сохраняет 14 real
TFT states, все семь jobs Home, оба наполненных водопада, unchanged generation 95/0
и heap, final owner/lease `none`/`0`
(`E-BUILD-095`/`E-AUTO-059`/`E-HIL-119`/`E-UX-018`).

Candidate `0.96.0-compact-ui-waterfall` сохраняет root-only identity contract и
показывает на Home `LESHY v0.96.0` или `Леший v0.96.0` в одну строку. Brand 16 px
и SemVer 12 px имеют общую baseline и fixed gap 5 px; measured text widths не
затрагивают right-aligned область SD/RF status. На вложенных экранах название
текущей страницы переносится в ту же information bar, поэтому отдельный body-title
исчезает; панель уменьшается с 34 до 26 px, а content начинается на y=32. Четыре
увеличенных menu target 216×60 заполняют доступный viewport. Interactive menu/list
rows используют единый horizontal inset 12 px и вертикально центрированный
двухстрочный текст. Exact bilingual physical acceptance сохраняет 14 Home/menu/RF
states после одной прошивки с zero ручных нажатий, exact CID, unchanged generation
95/0, stabilized invariant heap и final owner/lease `none`/`0`
(`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`).

## Строчная легенда физических клавиш

Candidate `0.95.0-inline-key-hints` возвращает удачную модель представления 0.x,
не возвращая его renderer. Footer высотой 26 px — одна спокойная строка, а не три
двухэтажные псевдокнопки. Roboto Condensed Medium 12 выводит действие рядом с
символом физической клавиши смешанным регистром и одним secondary-цветом:
`◀ Назад` привязан к левому краю, `▲▼ Выбор` центрирован, `Вход OK▶` привязан к
правому краю. Если действия нет, соответствующая зона остаётся пустой.

Символы сохраняют принятую семантику 1.x: Left — путь к parent/Stop, Up/Down меняет
selection или вид, Right либо OK входит внутрь или выполняет названное действие.
Внешние anchors по шесть пикселей и оптическая вертикальная центровка получены из
читаемой геометрии footer 0.x; подписи остаются текстом generated EN/RU font и не
становятся touch targets. Connected-candidate gate снимает Home, вложенные меню и
live RF views, проверяя compact legend во всех сочетаниях. Exact physical checkpoint
0.95 сохраняет 14 TFT states после одной прошивки и zero ручных нажатий при unchanged
heap/storage и final lease 0 (`E-BUILD-096`/`E-AUTO-060`/`E-HIL-120`/`E-UX-019`).

## Gate

**S1 UX direction accepted:** готовы UX-01/UX-02 в low-fidelity форме, все разделы
каталога имеют место в IA, открытые product choices записаны до реализации.

**S2 UX/UI baseline accepted:** UX-01…UX-07 подтверждены на реальном TFT; WF-01 и
platform-путь WF-02 проходят через те же Actions кнопками и diagnostic automation;
состояния не зависят от 0.x UI. Exact candidate 0.58 выполняет 29 steps, девять
zero-mismatch TFT comparisons, Quick 8/8 и zero final leases в `DEMO-S2`
(`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`). UX-08 повторяется на каждом следующем
Stage Demo.
