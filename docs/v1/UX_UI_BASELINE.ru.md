# ESP32-Leshy 1.x — UX/UI baseline

*Read in: [English](UX_UI_BASELINE.md) · **Русский***

Статус: **S1 product UX direction принят; S2 visual gate активен**. Low-fidelity
UX-01/UX-02 зафиксированы, UX-03/UX-04 приняты; UX-05…UX-07 — текущая работа S2.

Документ определяет, когда обсуждается опыт пользователя и когда внешний вид
становится ограничением реализации. Он не подменяет
[эталонные сценарии](REFERENCE_WORKFLOWS.ru.md) и не хранит текущее состояние.

## Два последовательных решения

### S1 — product UX direction

До закрытия S1 согласуются:

- информационная архитектура `Обзор / Цели / Захват / Лаборатория / Библиотека /
  Устройство` и постоянный utility-пункт `Self-Test` в самом низу Home;
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
| Home row | 216×32; gap последнего utility задан явно | capability Home и последний Self-Test item |
| Choice row | 216×48 с primary и metadata text | выбор Quick / Full-Guided |
| Metric row | пять result slots 216×28 | Full preflight и Quick/Full result |
| Footer divider | фиксирован на y=236 | каждый interactive screen |
| Input status + hint | отдельные непересекающиеся regions | каждый interactive screen и HIL |

Exact candidate `0.54.0-ui-components-measure` принимает UX-04 через
`E-BUILD-056`/`E-HIL-078`/`E-UX-004`: Home и Self-Test используют одинаковые
renderer primitives; четыре actual TFT frame проходят pixel/trace checker; Quick
проходит 8/8; input имеет zero errors/drops, buzzer остаётся LOW, Back возвращает
owner/lease в `none`/`0`. Это принимает component system, но не UX-05…07 или
`DEMO-S2`.

## Gate

**S1 UX direction accepted:** готовы UX-01/UX-02 в low-fidelity форме, все разделы
каталога имеют место в IA, открытые product choices записаны до реализации.

**S2 UX/UI baseline accepted:** UX-01…UX-07 подтверждены на реальном TFT; WF-01 и
platform-путь WF-02 проходят через те же Actions кнопками и diagnostic automation;
состояния не зависят от 0.x UI. UX-08 повторяется на каждом следующем Stage Demo.
