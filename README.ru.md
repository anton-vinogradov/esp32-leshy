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
- **Проверенный checkpoint:** exact `0.129.0-pre-app-watchdog` завершает физическую цепочку двух плат NEC receive → save → cold Library CSV за 33/33 шага. Exact passive `0.130.0` удерживает shared MISO/GPIO13 собранной board-02 в LOW на 32/32 samples под обеими подтяжками и читает zero receiver identities; exact isolated-main `0.131.0` меняет тот же наблюдаемый input на HIGH на 32/32 samples под обеими подтяжками при снятом RF carrier. Второй run выполняет zero SPI clocks, receiver reads, CE-high events, strobes и TX commands и возвращает Home/lease 0. Зависящий от сборки LOW локализует fault на RF carrier или его стороне connector, а не на main-only stuck-low ESP input.
- **Следующий gate:** разметить CSN/MISO pads RF carrier и проверить HIGH на CSN каждого receiver под quiescent exact image. Если все deselected, а MISO остаётся LOW, по одному изолировать carrier modules и потребовать plausible identities после ремонта до любого known-signal emission. Cross-swap и RF emission остаются закрыты.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S5.1 | Пассивные product slices штатных радио: all-antenna overview/finder nRF24, robust finder CC1101, основы bounded RAW/IR capture | ✅ готово |
| S5.2 | Первый physical loop двух плат: fixed NEC receive → explicit save → cold Library byte-exact export → safe cleanup | ✅ готово |
| S5.3 | Известный nRF24 signal: source-bound fixture 2 442 МГц на минимальной мощности → результат finder трёх приёмников → safe cleanup | 🟡 в работе |
| S5.4 | Известный Sub-GHz signal: поиск частоты плюс OOK capture/save/cold export; объявленный и проверенный FSK/GDO0 path | ⬜ дальше |
| S5.5 | Полнота runtime: worker supervision, low-voltage safe-write, sleep/resume и применимые явные assembly profiles GPS/PN532 | ⬜ дальше |
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
