# ADR-001 — clean toolchain 1.x и граница framework

*Читать на: [English](ADR-001-toolchain.md) · **Русский***

- **Статус:** accepted
- **Дата:** 2026-08-16
- **Requirements:** PR-001, PR-010, PR-014; NFR-001, NFR-006
- **Risks:** R-011, R-012, R-013
- **Этап:** решение S1; первая реализация в S2

## Контекст

0.x и feasibility contracts сейчас делят одну PlatformIO/Arduino build. Установленная
platform воспроизводима и уже даёт ESP-IDF 5.5.4/FreeRTOS API, но копирование legacy
tree сохранит lifecycle/dependency coupling. Немедленный native ESP-IDF rewrite
уберёт Arduino globals, но заставит поднимать display/input/libraries до проверки
первого product slice.

## Решение

1. Создать независимые environment и source tree 1.x, не компилирующие application
   или screen sources 0.x.
2. Зафиксировать pioarduino `55.03.39`, Arduino-ESP32 `3.3.9`, ESP-IDF `5.5.4` и
   точные версии direct libraries. Floating ranges в env 1.x запрещены.
3. В S2 Arduino-ESP32 — board-support/framework layer. Прямые Arduino, ESP-IDF и
   FreeRTOS calls живут только в `platform/` или hardware driver; domain/kernel/
   services остаются host-testable standard C++.
4. Использовать C++17; warnings нового кода 1.x становятся CI failures. CI собирает
   из empty dependency cache и сохраняет tool versions плюс image/map sizes.
5. Target — measured N16/no-PSRAM profile. Partition layout следует ADR-003/RB-02;
   обязательны два bootable slots и recovery.
6. Dependency допускается только с owner, pinned source/version, license review,
   bounded API wrapper и host/simulated alternative, где это практично.

## Альтернативы

- **Продолжить environment/tree 0.x:** rejected — нарушает generation boundary.
- **Сразу native ESP-IDF:** deferred, не навсегда rejected. До measurements S2/S3
  стоимость миграции не оправдана; platform adapters сохраняют путь.
- **Unpinned registry packages:** rejected — API drift уже ломал BLE build.

## Последствия

S2 использует проверенный board ecosystem, не превращая Arduino в domain
architecture. Риск доступности pioarduino снижается exact artifacts, clean-cache CI
и adapters. Для supersede нужны clean build, сравнение size/boot и работающий
display/input/storage smoke на board-01.

## Проверка

- clean target не содержит source paths 0.x;
- две clean-cache CI builds дают одинаковые version manifests и firmware hashes;
- host tests собираются без Arduino headers;
- build проходит RB-02/RB-03; HIL подтверждает boot, display, input, recovery.
