# ESP32-Leshy 1.x — UX/UI baseline

*Read in: [English](UX_UI_BASELINE.md) · **Русский***

Статус: **обязательная контрольная точка S1/S2**; low-fidelity UX-01/UX-02
зафиксированы, visual baseline UX-03…UX-07 остаётся S2.

Документ определяет, когда обсуждается опыт пользователя и когда внешний вид
становится ограничением реализации. Он не подменяет
[эталонные сценарии](REFERENCE_WORKFLOWS.ru.md) и не хранит текущее состояние.

## Два последовательных решения

### S1 — product UX direction

До закрытия S1 согласуются:

- информационная архитектура `Обзор / Цели / Захват / Лаборатория / Библиотека /
  Устройство`;
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

## Gate

**S1 UX direction accepted:** готовы UX-01/UX-02 в low-fidelity форме, все разделы
каталога имеют место в IA, открытые product choices записаны до реализации.

**S2 UX/UI baseline accepted:** UX-01…UX-07 подтверждены на реальном TFT; WF-01 и
platform-путь WF-02 проходят через те же Actions кнопками и diagnostic automation;
состояния не зависят от 0.x UI. UX-08 повторяется на каждом следующем Stage Demo.
