# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S6 — Продуктовые отличия: Targets, compare и companion**
>
> Закрыто этапов: 5 из 9.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон.

- **Текущая фаза:** `S6.4 — on-device workflows Targets и Compare`.
- **Проверенный checkpoint:** exact `0.153.0-targets-tags-edit` на source `042b120e85766d6d3762a7d07f8bf3c183f83cc5` физически принят в `E-AUTO-111`/`E-HIL-171`/`E-UX-048`. «Цель»→«Действия»→«Теги» открывает bounded добавление/удаление: добавляет ASCII-тег `A`, атомарно публикует catalog-only schema-v3 generation 3→4 и cold-reopen-ит его, затем удаляет тег, публикует generation 4→5 и cold-reopen-ит пустой список. Обе mutations повторно идентифицируют exact CID и выполняют 3 writes/3 file syncs/3 directory syncs. UI acknowledgement занимает 158/141 µs, supervised workers — 2,915/2,919 s; pre-mount workspace 16 КиБ помещается в largest block 34 804 B, heap освобождается с 85 072 до 96 852 B, финал — Home/none/lease 0. Отложенный RF-positive gate S5 открыт.
- **Следующий gate:** добавить bounded notes на том же exact-CID atomic path с сохранением выбранного Target. Далее идут correlation accept/reject; merge/split остаётся за явным confirmation с preview изменения ownership и сохранением reversal. Physical gate S5 остаётся отложенным до приезда replacement DIV и его read-only profile.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S6.1 | Фундамент Target: стабильные Target ID, точные radio identities, изменяемые name/tags/notes/favorite и неизменяемые ссылки на source evidence; всё bounded и host-verified | ✅ готово |
| S6.2 | Объяснимая correlation предлагает связи с features/confidence; accept/reject и обратимые merge/split никогда не уничтожают source evidence | ✅ готово |
| S6.3 | Baseline/diff сравнивает две Session и классифицирует новые, исчезнувшие и изменившиеся Targets; каждый вывод открывает своё evidence | ✅ готово |
| S6.4 | On-device workflows Targets и Compare сначала показывают полезный результат, сохраняют стабильную навигацию и полноэкранные detail views | 🟡 в работе |
| S6.5 | Local companion USB/Web использует те же Actions и versioned schemas с ограниченными connectivity и secrets | ⬜ дальше |
| S6.6 | Интегральный DEMO-S6: записать и сравнить две survey, открыть каждый вывод на устройстве или локально и offline-export; перед принятием S6 вернуться к отложенному physical predecessor gate S5 и закрыть его | ⬜ дальше |

### Роадмап

- ✅ **S0 — Governance и граница поколений** · готово
- ✅ **S1 — Evidence baseline: пользователи, конкуренты и железо** · готово
- ✅ **S2 — Чистая платформа 1.x** · готово
- ✅ **S3 — Первый вертикальный срез: Survey Session** · готово
- ✅ **S4 — Cross-radio passive platform** · готово
- 🔴 **S5 — Полнота железа ESP32-DIV** · заблокировано
- 🟡 **S6 — Продуктовые отличия: Targets, compare и companion** · в работе
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
