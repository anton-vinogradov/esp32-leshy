# ADR-008: просмотр эфира без SD

*Read in: [English](ADR-008-live-radio-without-sd.md) · **Русский***

- Status: **accepted**, владелец подтвердил 13 сентября 2026.
- Requirements: PR-003/004/005, CAP-009/010/011; stage S6.5.
- Context: живые списки Wi-Fi/BLE использовали разрешение durable Survey,
  поэтому на новом устройстве с незарегистрированной SD приём не запускался.
- Decision: просмотр сетей/устройств/графиков — явный volatile RX-only режим.
  Он использует тот же worker, ограниченные очереди, таймлайн, Stop и watchdog,
  но не читает CID, не монтирует SD и не получает разрешение на запись.
  Его данные исчезают при выходе/перезагрузке; никаких обещаний сохранения.
  Только явное сохранение/Field Visit требует готового exact-CID хранилища,
  действующих ключей и существующей atomic commit policy. Persistent-запрос
  никогда не понижается автоматически до RAM из-за ошибки карты.
- Alternatives: требовать карту даже для просмотра — лишняя зависимость;
  подделывать writable permit — нарушение storage boundary, запрещено;
  отдельный дублирующий scanner — риск расхождения watchdog/cleanup/UX.
- Consequences: новые форматы, перенос ключей, регистрация/форматирование SD
  не нужны. Ключевые, radio ownership, coexistence, RF TX и Stop ограничения
  сохраняются. PIN-policy ADR-007 не расширяется.
- Verification: host admission проверяет live/persistent плюс отрицательные
  resource/source/passive/commit случаи; product HIL проверяет живые данные,
  нулевые SD identity/mount/write, отсутствие TX, Back и повторный вход.
  Приёмка отдельного реального сигнала/антенны и записей остаётся отдельной.
