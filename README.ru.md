# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S5 — Полнота железа ESP32-DIV**
>
> Закрыто этапов: 5 из 9.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон.

- **Текущая фаза:** `S5.4 — завершение Sub-GHz OOK/FSK (physical positive gate аппаратно заблокирован)`.
- **Проверенный checkpoint:** exact `0.144.0-full-guided-s5-rx` превращает публичный путь Устройство → Самопроверка → Полная в автономный passive hardware/artifact delta на board-01. Быстрая проходит 9/9; Полная сообщает 28 pass, zero fail, один честный blocker полноты capabilities и три N/A. Прогон упражняет все три receive path nRF24, sweep CC1101 на 64 bin, bounded окна OOK/FSK и вход IR; FSK фиксирует 72 edges в 32 окнах с zero overflow. Аудиты Recovery/Library/disposable сохраняют exact CID, generation 110 и zero product observations; PCAP корректно N/A для этой пустой принятой сессии, а изолированный scratch выполняет 3 записи/505 B и удаляется. Heap заканчивает с 96 880 B free и boot-lifetime minimum 63 848 B — на 14 960/14 696 B выше независимых gates 80/48 КиБ. Evidence `E-HIL-162` сохраняет 13 автоматических TFT frames, zero radio TX/input drops и финал Home/none/lease 0. Это принимает интегрированный passive delta Full/Guided, а не оставшийся physical RF-positive или S5 exit gate.
- **Следующий gate:** использовать квалифицированный собственный RF source, чтобы закрыть physical nRF24 result S5.3 и Sub-GHz frequency→OOK/FSK capture→save→cold export S5.4, затем выполнить integrated gate S5.6. Неисправный клон восстановлен в stock для возврата и не является разрешённым transmitter; без replacement source physical/two-board gates остаются fail-closed.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S5.1 | Пассивные product slices штатных радио: all-antenna overview/finder nRF24, robust finder CC1101, основы bounded RAW/IR capture | ✅ готово |
| S5.2 | Первый physical loop двух плат: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ готово |
| S5.3 | Известный nRF24 signal: source-bound fixture 2 442 МГц на минимальной мощности → результат finder трёх приёмников → safe cleanup; заблокирован до появления исправного/заменённого RF carrier | 🔴 заблокировано |
| S5.4 | Известный Sub-GHz signal: exact 0.140 принимает bounded OOK/FSK UI, реализацию receive GDO0 и one-flash no-signal delta; physical frequency→capture→save→cold export остаётся source-blocked | 🟡 в работе |
| S5.5 | Полнота runtime: exact 0.139 принимает унаследованную от 0.138 safety Product Survey/workers плюс truthful applicability stock assembly, debounced отказ Store при low voltage, реальный light-sleep/resume и public RX-only software-fixture path Store Sub-GHz; physical positive RF остаётся в S5.3/S5.4 | ✅ готово |
| S5.6 | Интегральный hardware gate S5: exact 0.144 уже принимает автономную on-device половину Full receivers/artifacts без утечки leases/outputs; выполнить two-board половину с qualified source после S5.3/S5.4 | ⬜ дальше |

### Роадмап

- ✅ **S0 — Governance и граница поколений** · готово
- ✅ **S1 — Evidence baseline: пользователи, конкуренты и железо** · готово
- ✅ **S2 — Чистая платформа 1.x** · готово
- ✅ **S3 — Первый вертикальный срез: Survey Session** · готово
- ✅ **S4 — Cross-radio passive platform** · готово
- 🟡 **S5 — Полнота железа ESP32-DIV** · в работе
- ⬜ **S6 — Продуктовые отличия: Targets, compare и companion** · дальше
- ⬜ **S7 — Безопасная Lab и расширяемость** · дальше
- ⬜ **S8 — Release hardening и 1.0.0** · дальше

[живой статус и ближайший evidence gate](docs/v1/STATUS.ru.md) · [результаты и exit gates этапов](docs/v1/DELIVERY_PLAN.ru.md) · [полная карта функциональности](docs/v1/DELIVERY_PLAN.ru.md#карта-функциональности-продукта)
<!-- LESHY-ROADMAP:END -->

Выпущенная 0.x остаётся замороженной PoC-линейкой; пользовательский бинарник 1.x
пока не выпускался.

## Линейки версий

- **0.x — архивный PoC:** существующая menu-прошивка, список функций, заметки по
  железу и руководство разработчика сохранены в [архиве 0.x](docs/archive/v0.x/README.ru.md).
  [Веб-установщик](https://anton-vinogradov.github.io/esp32-leshy/) пока прошивает эту
  линейку.
- **1.x — активный редизайн:** продуктовый анализ, архитектура и новое ядро приложений
  с capabilities/resources находятся в разделе [docs/v1](docs/v1/README.ru.md).

## Что строит 1.x

Leshy становится полевым инструментом с законченным сценарием:

> обнаружить → идентифицировать → локализовать → записать → сравнить → безопасно
> воспроизвести на своём стенде → сохранить и экспортировать результат.

Продукт строится вокруг Обзора, Целей, Захвата, Лаборатории, Библиотеки и Устройства,
а не постоянно растущего списка разрозненных радиоэкранов. Wi-Fi, BLE, NRF24, CC1101,
IR, NFC, GPS и хранилище становятся общими возможностями этих сценариев.

## С чего читать

- [Индекс документации](docs/README.ru.md)
- [Текущий статус](docs/v1/STATUS.ru.md)
- [Правила документации](docs/v1/GOVERNANCE.ru.md)
- [Этапы достижения 1.0.0](docs/v1/DELIVERY_PLAN.ru.md)
- [Трассировка целей](docs/v1/TRACEABILITY.ru.md)
- [Продуктовая концепция](docs/v1/VISION.ru.md)
- [Конкурентный анализ](docs/v1/COMPETITIVE_ANALYSIS.ru.md)
- [Требования продукта](docs/v1/PRODUCT_REQUIREMENTS.ru.md)
- [Аппаратные возможности и конфликты](docs/v1/HARDWARE_ENVELOPE.ru.md)
- [Целевая архитектура](docs/v1/ARCHITECTURE.ru.md)
- [Архив документации 0.x](docs/archive/v0.x/README.ru.md)

## Разработка

Документация определяет scope и gates 1.x. Текущее состояние кода, прототипов и
проверок фиксируется только в [STATUS](docs/v1/STATUS.ru.md). Роадмап на главной
генерируется из этого статуса и delivery plan, поэтому README не становится второй
конкурирующей точкой истины.

```bash
python3 tools/readme_roadmap.py --write
python3 tools/check_docs.py
tools/test.sh
tools/build.sh
```

## Ответственное использование

Используйте Leshy только со своим оборудованием или там, где есть явное письменное
разрешение. Наблюдение — режим по умолчанию. Передача и replay находятся в отдельной
Лаборатории с видимым состоянием, ограниченным временем и мгновенной остановкой.
Полные условия: [DISCLAIMER.ru.md](DISCLAIMER.ru.md).

## Лицензия и благодарности

[MIT](LICENSE). Железо и оригинальная прошивка —
[CiferTech](https://github.com/CiferTech/ESP32-DIV). Leshy — независимый неофициальный проект.
