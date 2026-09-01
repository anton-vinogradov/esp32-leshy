# Проверка собственного evidence

*Читать на: [English](OWNED_EVIDENCE_VERIFICATION.md) · **Русский***

Это offline-часть `CAP-061` на компьютере. Она отвечает на один ограниченный вопрос
пользователя: **совпадает ли authentication evidence моей Wi-Fi-сети с локальным
проверенным corpus распространённых или заводских паролей?** Это не универсальный
cracker: инструмент не работает с радио, не подключается к сети и не изменяет DIV.

## Текущая принятая граница

- вход — 1…16 строгих canonical records `hc22000`: PMKID `WPA*01` или EAPOL
  `WPA*02`;
- перед запуском пользователь явно подтверждает право проверять evidence;
- corpus локальный и связан с ID, version, class и SHA-256;
- один запуск ограничен 1 000 000 candidates, 3 600 секундами и corpus 64 MiB;
- у каждого реального запуска есть checkpoint, связанный с exact hashes evidence и
  corpus;
- report хранит только rank совпадения, class слабости, provenance corpus и hashes
  входов — без plaintext, raw evidence, SSID, BSSID и station ID;
- Leshy не поставляет corpus, особенно identity-linked базы утечек;
- поддерживаются EAPOL descriptor versions 1 и 2; остальные fail closed.

Поддерживаемый пользовательский путь WPA2 PMKID/EAPOL и его physical-цепочка
export→verification завершают `WF-11`. Более широкий `FUNC-61` остаётся active для
WPA3/key-version 3 и остальных типов собственного evidence.

## Безопасный сценарий

1. На DIV выбрать **Wi-Fi → Сети → своя сеть → Проверить пароль** для своей сети или
   сети с явным разрешением. Пройти объяснение, записать bounded authentication
   evidence, затем сохранить и экспортировать его из **Сохранённого**.
2. Подготовить локальный проверенный список распространённых или заводских паролей
   роутеров и не добавлять его в репозиторий.
3. Использовать основной task-first путь. Он объясняет границу разрешения, показывает
   точные limits, автоматически создаёт checkpoint и выдаёт понятный результат:

   ```sh
   python3 tools/check_my_wifi_password.py \
     --evidence owned.hc22000 --corpus common.txt \
     --list-kind common --max-candidates 10000 --max-seconds 30
   ```

   Если проверка остановилась по limit, повторить ту же команду с `--resume`.
   Изменение evidence или corpus инвалидирует checkpoint. `--preview-only` проверяет
   входы, не оценивая ни одного пароля.

4. Низкоуровневый verifier остаётся для автоматизации и расширенного использования:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --preview-only
   ```

5. Запустить его с явным подтверждением владения, конечными budgets и durable checkpoint:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --max-candidates 10000 --max-seconds 30 \
     --checkpoint verification.checkpoint.json \
     --owned-evidence-confirmed --report verification.report.json
   ```

6. Для результата `paused` повторить ту же команду с `--resume`. Изменение evidence,
   corpus или metadata corpus делает checkpoint недействительным.

`weak_password_match` означает только то, что один candidate corpus воспроизводит
все переданные records. Durable report намеренно его не раскрывает. Пароль следует
изменить штатным интерфейсом роутера и повторным capture подтвердить исправление.
`complete_no_match` не доказывает надёжность пароля: он исключает только точный
конечный локальный список, который был проверен.

## Приёмка

Focused delta — `tools/test.sh --only owned-wifi-evidence`. Она проверяет canonical
export Leshy, task-first journey, официальный reference-вектор PMKID Hashcat mode
22000, positive/negative WPA*01 и WPA*02, strict parser, privacy-safe report, bounded
checkpoint/resume и source-contract без network/device/radio операций. Сохранённая
[physical acceptance](../../tests/hil/evidence/board-01-owned-wifi-password-check-1.0.0-dev.369.json)
дополнительно связывает exact candidate hashes/CID, task-first device navigation,
atomic save, cold reopen, canonical export, physical negative control, public positive
control и final cleanup без сохранения raw evidence или identity сети.
