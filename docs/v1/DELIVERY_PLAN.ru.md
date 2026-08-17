# ESP32-Leshy 1.x — этапы достижения 1.0.0

*Читать на: [English](DELIVERY_PLAN.md) · **Русский***

Этот документ определяет устойчивые границы этапов. Текущее состояние, evidence и
следующие действия находятся только в [STATUS.ru.md](STATUS.ru.md).

Этап закрывается результатом, который можно проверить, а не объёмом написанного
кода. Каждый технический этап после S1 оставляет работоспособный вертикальный срез.

## Карта этапов

```text
S0 Правила и граница версий
 └─ S1 Доказательства и ограничения
     └─ S2 Чистая платформа 1.x
         └─ S3 Первая Survey Session
             └─ S4 Cross-radio passive platform
                 └─ S5 Полнота железа ESP32-DIV
                     └─ S6 Targets, compare и companion
                         └─ S7 Безопасная Lab и расширяемость
                             └─ S8 Надёжность, RC и 1.0.0
```

Предварительное соответствие релизам:

| Этап | Возможный артефакт | Главный результат |
|---|---|---|
| S0–S1 | без пользовательского релиза | зафиксирована правильная задача и реальные ограничения |
| S2 | `1.0.0-alpha.1` | независимая target загружается и диагностирует плату |
| S3 | `1.0.0-alpha.2` | первая сохраняемая Survey Session end-to-end |
| S4 | `1.0.0-alpha.3` | единая пассивная сессия нескольких радио |
| S5 | `1.0.0-alpha.4` | штатное железо ESP32-DIV имеет базовые сценарии |
| S6 | `1.0.0-beta.1` | появляются основные продуктовые отличия Leshy |
| S7 | `1.0.0-beta.2` | безопасные активные действия и контракт расширений |
| S8 | `1.0.0-rc.*` → `1.0.0` | подтверждённая полевая надёжность |

Номер версии не закрывает gate автоматически; он лишь маркирует артефакт.

## Сквозные контрольные точки

Три документа не создают новые этапы, а защищают их результат:

- [каталог возможностей](CAPABILITY_CATALOG.ru.md) фиксирует полный scope 1.0 на S1;
- [UX/UI baseline](UX_UI_BASELINE.ru.md) согласует product UX на S1 и visual/
  interaction system на реальном TFT в S2;
- [Stage Demo](STAGE_DEMO.ru.md) обязательно закрывает каждый этап S2…S8
  воспроизводимым сквозным проходом на плате.

S7 означает **feature-complete**: все принятые P0/P1 и применимые conditional
`CAP-*` реализованы. S8 означает **release-complete**: те же возможности выдержали
release matrix, endurance и recovery; крупный feature scope в S8 не добавляется.

## S0 — Governance и граница поколений

**Цель:** исключить смешивание PoC 0.x и нового продукта.

Результаты:

- 0.x явно заморожена и её документация архивирована;
- определена каноническая структура документов и порядок разрешения конфликтов;
- заведены IDs для jobs, requirements, stages и будущих ADR;
- есть единый `STATUS`, delivery plan и traceability;
- web installer честно маркирует устанавливаемую линию 0.x.

**Exit gate S0:** новый участник однозначно находит актуальный scope, текущий этап и
условия его закрытия; в активных документах нет живого checklist конкурирующего с
`STATUS`; внутренние ссылки проходят проверку.

## S1 — Evidence baseline: пользователи, конкуренты и железо

**Цель:** доказать, что строится правильный продукт в реальном resource envelope
ESP32-DIV, до фиксации реализации.

Входы: vision, первичный PRD, конкурентный срез, схема/исходники ESP32-DIV и плата v2.

Результаты:

- карта питания, GPIO, SPI/I2C/UART, памяти и конфликтующих режимов;
- capability matrix: built-in, optional, detected, mutually exclusive, degraded;
- 3–5 эталонных сценариев с happy/error/cancel flows;
- измеренные flash/RAM/storage/startup/power бюджеты минимального прототипа;
- risk register: hardware, safety, data integrity, dependencies, supply variants;
- PRD 1.0.0 переведён из `draft` в принятый baseline;
- полный `CAP-*` catalog и явные исключения 1.0 прошли product review;
- согласованы information architecture, common Actions и обязательные UX states;
- принят протокол промежуточных Stage Demo S2…S8;
- выбран первый Survey source на основе измерений, а не удобства кода;
- ADR-кандидаты для framework/toolchain, storage schema и resource policy.

**Exit gate S1:** для каждого P0 requirement понятны capability, ограничение,
архитектурный владелец и тип проверки; неизвестных pin/resource-конфликтов не осталось;
первый вертикальный срез помещается в измеренные бюджеты; scope catalog и S1 UX
direction приняты.

## S2 — Чистая платформа 1.x

**Цель:** получить минимальную независимую firmware, на которой безопасно строить
сценарии, не подключая монолит 0.x.

Результаты:

- отдельная build target и дерево `apps/sdk/services/kernel/drivers/boards/platform`;
- зафиксированные toolchain и зависимости;
- BoardProfile + HardwareProbe + Diagnostics;
- Navigator и единый input event path;
- AppRuntime, capability registry и атомарный ResourceBroker;
- базовые display, storage, logging, crash reason и системное время;
- visual/interaction baseline, проверенный на реальном TFT для EN/RU и common states;
- последний пункт Home Self-Test с Quick platform checks и skeleton versioned report;
- host CI и минимальный HIL boot/input/probe test.

**Exit gate S2:** clean build загружается без кода меню 0.x, показывает достоверную
диагностику конкретной платы, 1000 open/back циклов не теряют leases/heap, missing
hardware не мешает boot, повторяемые host и HIL проверки зелёные.
Дополнительно `DEMO-S2` и UX-01…UX-07 должны пройти по общему Stage Demo protocol.
Quick Self-Test доступен кнопками, read-only, bounded/cancellable и оставляет zero
ownership; registry Full/Guided растёт на каждом следующем этапе.

## S3 — Первый вертикальный срез: Survey Session

**Цель:** доказать продуктовую и архитектурную цепочку целиком на одном пассивном
источнике.

Результаты:

- Start/Stop Survey как Actions;
- один driver публикует нормализованные Observation;
- общие List и Detail, корректные Back/cancel/error states;
- Session manifest и атомарная запись observations;
- открытие сохранённой Session после reboot при выключенном радио;
- JSON summary export;
- recorded trace для воспроизводимого host integration test.

**Exit gate S3:** все девять критериев первого среза из PRD подтверждены evidence;
power loss не повреждает подтверждённую Session; UI, CLI/test harness используют одну
семантику Actions.

## S4 — Cross-radio passive platform

**Цель:** превратить единичный срез в общую пассивную систему наблюдения.

Результаты:

- Wi-Fi/BLE scan, NRF24/CC1101 spectrum и GPS через единые driver contracts;
- scheduler совместимых и mutually-exclusive ресурсов с видимым duty cycle;
- общая timeline, фильтры, List/Detail/Radar и capture metadata;
- PCAP для совместимых сетевых захватов и CSV/JSON export;
- bounded queues, dropped-event diagnostics и heap/latency instrumentation;
- 8-часовой passive endurance test.
- каждый завершённый passive source регистрирует применимый Full/Guided Self-Test
  check вместо release-only diagnostic path.

**Exit gate S4:** одна Session безопасно объединяет доступные пассивные источники,
объясняет временно недоступные ресурсы, переживает reboot и экспорт без утечки heap и
повреждения данных.

## S5 — Полнота железа ESP32-DIV

**Цель:** дать каждому штатному модулю законченный полезный сценарий и достичь
осмысленного паритета 0.x/original без переноса их структуры меню.

Результаты:

- IR capture/decode/library и SafetyPolicy-approved replay;
- PN532 probe, tag/NDEF info, versioned dump и разрешённые write/restore flows;
- GPS fix/satellite/track/time diagnostics;
- SD/LittleFS recovery, library browser и portable import/export;
- calibration для RSSI/frequency, power/sleep/resume и low-voltage safe write;
- passive smoke test и error flow каждого физического модуля.

**Exit gate S5:** `PR-014` verified; отсутствие любого optional module не ломает
загрузку или соседние сценарии; каждый модуль проходит цепочку
probe → observe/capture → library → inspect/export.

## S6 — Продуктовые отличия: Targets, compare и companion

**Цель:** превзойти набор отдельных инструментов связностью данных и анализа.

Результаты:

- Target history, identities, tags, notes и evidence-backed correlation;
- обратимые merge/split и объяснимый confidence;
- baseline/diff сессий и захватов;
- локализация, timeline и GPS track/map where available;
- локальный Web/USB companion над теми же Actions и schemas;
- офлайн просмотр, поиск и экспорт без аккаунта.

**Exit gate S6:** пользователь записывает окружение, сравнивает повторный проход,
видит новые/исчезнувшие/изменившиеся цели и открывает исходное доказательство каждого
вывода на устройстве или локальном companion.

## S7 — Безопасная Lab и расширяемость

**Цель:** разрешить развитие протоколов и контролируемое исследование своего
оборудования без обхода системных гарантий.

Результаты:

- общий Lab context, regulatory policy, TX indication/deadline/panic stop;
- application descriptor: capabilities, resources, permissions, safety, strings;
- scoped storage и ограниченный driver/action access;
- decoder/profile packages с проверкой версии и подписи;
- protocol workbench: waveform/pulses, compare, annotations, derived decode;
- sample app/decoder, SDK docs и simulator trace kit.

**Exit gate S7:** внешний разработчик создаёт sample extension без изменения kernel;
extension не может обойти leases/permissions; HIL подтверждает физическую остановку
каждого включённого TX path при timeout, Back, panic и fault; каталог 1.0
feature-complete и проходит `DEMO-S7`.

## S8 — Release hardening и 1.0.0

**Цель:** превратить beta в инструмент, которому можно доверить полевой день и данные.

Результаты:

- stable/beta channels, подписанные manifest/firmware, rollback и recovery image;
- HIL matrix display/input/radios/storage/power-cycle/update;
- fuzzing импортируемых форматов и сетевых ответов;
- crash journal и диагностический bundle;
- performance, storage и power budgets на чистом и заполненном устройстве;
- user/developer docs, schemas, threat model, support и compatibility policy;
- release checklist с воспроизводимыми binary hashes и provenance;
- единый полный Self-Test plan для on-device Full/Guided и независимо проверяющего
  release runner.

**Exit gate S8:** два последовательных RC без открытых P0/P1; 24-часовой mixed
workload без зависания, утечки или повреждения; успешное восстановление после
прерванных update и write; все P0 requirements имеют статус `verified`; `DEMO-S8`
проходит без добавления нового feature scope.

## После 1.0.0

Следующие board profiles, каталог расширений, новые языки и расширенная аналитика
начинаются только после отдельного 1.x requirement/stage proposal. Они не могут
ослабить gates 1.0.0 задним числом.
