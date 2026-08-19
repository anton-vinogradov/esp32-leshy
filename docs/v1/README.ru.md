# Документация ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

1.x — сброс продуктовых и архитектурных предположений. Документы этого раздела
описывают целевое поведение и не являются обещанием функций текущего бинарника 0.x.

## Начать здесь

1. [Текущий статус](STATUS.ru.md) — активный этап, evidence, риски и следующие
   действия.
2. [Правила документации](GOVERNANCE.ru.md) — что нормативно и как меняется scope.
3. [Этапы достижения 1.0.0](DELIVERY_PLAN.ru.md) — результаты и exit gates S0…S8.
4. [Полный каталог возможностей 1.0](CAPABILITY_CATALOG.ru.md) — что именно должно
   войти в feature-complete 1.0.
5. [UX/UI baseline](UX_UI_BASELINE.ru.md) — когда согласуются сценарии и внешний вид.
6. [Протокол Stage Demo](STAGE_DEMO.ru.md) — как проверяется каждый промежуточный этап.
7. [Трассировка целей](TRACEABILITY.ru.md) — связь целей, требований, компонентов и
   проверок.

Только `STATUS` содержит живое состояние. Остальные документы меняются, когда
меняются границы продукта или принятые решения.

## Определение продукта

- [Продуктовая концепция](VISION.ru.md)
- [Конкурентный анализ](COMPETITIVE_ANALYSIS.ru.md) — срез рынка и полученные
  требования
- [Продуктовые требования и измеримые критерии](PRODUCT_REQUIREMENTS.ru.md) —
  принятый baseline 1.0
- [Product review каталога 1.0](CAPABILITY_REVIEW.ru.md) — проверка полноты,
  пересечений и шести закрытых пробелов scope
- [Эталонные сценарии](REFERENCE_WORKFLOWS.ru.md) — happy/error/cancel paths и
  измеримая приёмка
- [Реестр ресурсных бюджетов](RESOURCE_BUDGETS.ru.md) — измеренное evidence,
  временные guardrails и открытые измерения
- [Реестр рисков](RISK_REGISTER.ru.md) — устойчивые risks, controls, owners и
  closure evidence
- [Карта возможностей и ограничений железа](HARDWARE_ENVELOPE.ru.md) — design
  evidence, resource domains, safe probes, HIL plan и явные unknowns
- [Операторский протокол HIL probe](HIL_PROBE.ru.md) — безопасная diagnostic image,
  команды и правила сохранения физического evidence
- [Автоматизация UI и визуальные evidence](UI_AUTOMATION.ru.md) — единый input path,
  захват реального TFT и проход по меню без оператора
- [Встроенный Self-Test](SELF_TEST.ru.md) — явные Quick и Full/Guided modes для
  пользователя и release HIL на одном test engine
- [Программный Safety Supervisor](SAFETY_SUPERVISOR.ru.md) — runtime watchdog,
  retained Safe Mode, emergency quiesce outputs и явные hardware limits
- [Автоматический предрелизный HIL](PRE_RELEASE_HIL.ru.md) — proposed build-once,
  physical-test и promote-same-bytes pipeline с screenshots и attestation
- [HIL атомарности storage](STORAGE_HIL.ru.md) — dual-head recovery, fault boundaries
  и безопасность disposable media

## Проектирование и реализация

- [Целевая архитектура](ARCHITECTURE.ru.md)
- [UX-01: карта экранов и Actions](UX_SCREEN_MAP.ru.md)
- [UX-02: матрица состояний](UX_STATE_MATRIX.ru.md)
- [UX-06: карта input и accessibility](UX_ACCESSIBILITY.ru.md)
- [Architecture Decision Records](adr/README.ru.md) — обязательные решения по
  toolchain, resources, storage и Action boundary
- [Старая ссылка Roadmap](ROADMAP.ru.md) — только перенаправление

## Рабочее правило

Пункт меню конкурента не попадает в backlog напрямую. Кандидат должен решать сценарий
разрешённого пользователя, помещаться в capability/resource envelope ESP32-DIV и
иметь измеримые критерии готовности и безопасности.
