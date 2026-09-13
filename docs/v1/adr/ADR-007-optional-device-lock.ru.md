# ADR-007: добровольный Device Lock с первого запуска

*Язык: [English](ADR-007-optional-device-lock.md) · **Русский***

- Статус: **accepted** владельцем 13 сентября 2026.
- Требования: PR-024, CAP-052; этап: S6.5 functional-first UX / S7 security.
- Контекст: общий ProtectedUi gate блокировал Wi-Fi и спектр на новом устройстве
  до создания PIN, даже если владелец собирался его отключить. Durable store уже
  отличает virgin от missing-expected credential и создаёт случайный data key
  до настройки PIN.
- Решение: initialized virgin устройство работает без PIN; enrollment остаётся
  добровольным действием Устройство → Блокировка. Состояния unconfigured/disabled
  и форматы записей/файлов сохраняются. Доступ требует успешно восстановленного
  локального ключа, а не только начального enum. Locked, retry, recovery-only,
  corrupt, missing-expected и unavailable-store остаются закрыты; обновление
  не отключает существующий PIN. Работа без PIN не является authenticated session.
- Альтернативы: обязательная настройка с последующим отключением не защищает
  владельца, выбравшего отсутствие PIN; исключения для отдельных радио создают
  несогласованные UI/export policies; автоматический сброс credential был бы
  обходом защиты и отвергнут.
- Последствия: без PIN нет PIN-защиты данных от человека с доступом к устройству.
  Файлы остаются зашифрованными прежним ключом; включение PIN оборачивает этот
  ключ, отключение сохраняет его. Миграция, enrollment SD и стирание не входят
  в изменение. Независимые strong-auth, RF admission, watchdog, Stop, target
  и storage rules не меняются. Lock без PIN ничего не делает, но по-прежнему
  отзывает authenticated session. Отмена reset не стирает no-PIN volatile key.
- Проверка: host tests проверяют отказ до restore, все общие operation classes,
  bootstrap failures, cold restore/key continuity, optional enrollment/locked
  restore/retry/recovery и cancel. Focused board run использует настоящий
  product state без fixture unlock, открывает passive menus, сохраняет credentials
  и SD, связывает exact firmware identity и освобождает leases. Полная исправность
  платы этим не принимается. Историческое setup-required evidence сохраняется.
