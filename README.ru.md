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

- **Текущая фаза:** `S5.3 — проверка известного сигнала nRF24`.
- **Проверенный checkpoint:** exact `0.129.0-pre-app-watchdog` завершает физическую цепочку двух плат NEC receive → save → cold Library CSV за 33/33 шага. Exact `0.130.0`/`0.131.0` меняют shared MISO/GPIO13 board-02 из LOW с подключённым RF carrier в HIGH при снятом carrier. Exact `0.132.0-carrier-csn-characterization` снова подключает carrier и наблюдает все четыре receiver select в HIGH на 32/32 samples (nRF GPIO4/48/21 и CC1101 GPIO5), а MISO возвращается в LOW: 0/32 HIGH samples под обоими pull. Run выполняет zero SPI bytes, receiver reads, CE-high events, strobes и TX commands и возвращает Home/none/lease 0. Это отвергает случайно выбранный receiver и локализует fault до carrier module или общей MISO-сети carrier; один модуль не определён, antenna/U.FL fault не доказан. Exact `0.136.0-capture-store-deadline` расширяет принятый safety slice S5.5 на публичный worker Wi-Fi Capture Store no-PSRAM board-01: normal save сохраняет 2 frames/433 payload bytes и продвигает generation 98→99 при 93 544 B free heap, largest block 32 756 B и mount error zero. Второй save внедряет stall 10 s до storage hardware; worker deadline 8 000 ms срабатывает через 8 001 ms с zero physical writes, глушит outputs/освобождает lease, Safe Mode переживает restart, блокирует recovery writes, требует двухшаговый clear и возвращает exact CID/catalog 99/0, Home и lease 0.
- **Следующий gate:** отремонтировать, вернуть или заменить RF carrier/device board-02, затем потребовать plausible identities nRF и CC1101 тем же exact read-only probe до любой bounded known-signal emission. Изоляция отдельных modules теперь требует физического разрыва MISO или power, потому что carrier не имеет software-controlled power modules. Cross-swap и RF emission остаются закрыты.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S5.1 | Пассивные product slices штатных радио: all-antenna overview/finder nRF24, robust finder CC1101, основы bounded RAW/IR capture | ✅ готово |
| S5.2 | Первый physical loop двух плат: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ готово |
| S5.3 | Известный nRF24 signal: source-bound fixture 2 442 МГц на минимальной мощности → результат finder трёх приёмников → safe cleanup | 🟡 в работе |
| S5.4 | Известный Sub-GHz signal: поиск частоты плюс OOK capture/save/cold export; объявленный и проверенный FSK/GDO0 path | ⬜ дальше |
| S5.5 | Полнота runtime: exact 0.136 принимает preparation/admission Product Survey, калиброванные workers Wi-Fi+BLE и heartbeat/deadline slice worker Wi-Fi Capture Store; workers store Sub-GHz/IR, low-voltage safe-write, sleep/resume и применимые явные assembly profiles GPS/PN532 остаются | ⬜ дальше |
| S5.6 | Интегральный hardware gate S5: on-device Full check плюс автоматический two-board regression без утечки leases/outputs | ⬜ дальше |

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
