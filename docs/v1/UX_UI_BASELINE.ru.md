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

- информационная архитектура `Обзор / Цели / Захват / Лаборатория / Библиотека /
  Устройство`, прямой доступ к `Язык` и постоянный utility-пункт `Self-Test` в
  самом низу Home;
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
Full/Guided используют обычные Actions и компоненты. Это не boot screen, не скрытое
service menu и не release-only serial path.

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

Geometry фиксирует 240×320, edge 12 px, content width 216 px, header 42 px,
row 40 px, gap 7 px, radius 4 px и отдельный footer ниже y=236. Footer не может
перекрывать product content; три list rows обязаны помещаться до него.

Exact candidate 0.52 принимает UX-03 как implementation evidence: шесть retained
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
| Header + title | brand anchor 240×42; title region 216 px | Home и все Self-Test views |
| Home row | 216×28; пять строк помещаются над footer, utility gap задан явно | capability Home, Язык и последний Self-Test item |
| Choice row | 216×48 с primary и metadata text | выбор Quick / Full-Guided |
| Metric row | пять result slots 216×28 | Full preflight и Quick/Full result |
| Footer divider | фиксирован на y=236 | каждый interactive screen |
| Input status + hint | отдельные непересекающиеся regions | каждый interactive screen и HIL |

Exact candidate `0.54.0-ui-components-measure` принимает UX-04 через
`E-BUILD-056`/`E-HIL-078`/`E-UX-004`: Home и Self-Test используют одинаковые
renderer primitives; четыре actual TFT frame проходят pixel/trace checker; Quick
проходит 8/8; input имеет zero errors/drops, buzzer остаётся LOW, Back возвращает
owner/lease в `none`/`0`. Тогда это приняло component system; UX-05…07 и `DEMO-S2`
ещё оставались открыты.

## UX-05 — размещение EN/RU

`ui/UiStrings.def` — единый allocation-free каталог всех текущих строк S2 renderer,
кроме неизменяемого бренда `LESHY 1.x`. Сейчас он задаёт 127 стабильных ID, варианты
EN и RU (всего 254 строки) и пиксельный budget каждого места использования. Exact
accepted candidate 0.55 содержал 111 ID/222 строки; 16 последующих ID добавляют
тексты guided states и product cancellation/progress.
`tools/generate_ui_gfx_font.py` воспроизводимо генерирует faces, а
`tools/check_ui_language_contract.py` измеряет их metrics, отклоняет отсутствующий
перевод или переполнение и проверяет, что renderers не возвращают локальные
user-facing literals.

Оба языка теперь используют официальный vendored variable source Roboto Condensed с
лицензией OFL и pinned SHA-256. Генератор выбирает named instance Medium (weight 500)
и создаёт body 16 px и metadata 12 px для нужного ASCII/Cyrillic range без
runtime-загрузки шрифта или heap allocation. `Язык` — предпоследний пункт Home,
выбор EN/RU применяется сразу и сохраняется в NVS namespace `leshy1-ui`, key
`lang.v1`; команда `ui.language en|ru` проходит через ту же controller boundary,
что и экран. Прежний source PT Sans Narrow и exact evidence 0.55 остаются historical
provenance, а не текущим face.

UX-05 принимает encoding coverage, persistence, geometric fit и выбранный face для
малого raster; physical-panel optics и особенности зрения остаются частью usability
walkthrough. Замена на Roboto потребовала восьми безопасных сокращений. После них
все 254 варианта помещаются в declared pixel budgets generated glyphs без overflow.

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

## Gate

**S1 UX direction accepted:** готовы UX-01/UX-02 в low-fidelity форме, все разделы
каталога имеют место в IA, открытые product choices записаны до реализации.

**S2 UX/UI baseline accepted:** UX-01…UX-07 подтверждены на реальном TFT; WF-01 и
platform-путь WF-02 проходят через те же Actions кнопками и diagnostic automation;
состояния не зависят от 0.x UI. Exact candidate 0.58 выполняет 29 steps, девять
zero-mismatch TFT comparisons, Quick 8/8 и zero final leases в `DEMO-S2`
(`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`). UX-08 повторяется на каждом следующем
Stage Demo.
