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

Эта host foundation не завершает `FUNC-61`: открыты пользовательская интеграция с
companion, WPA3/key-version 3, physical evidence цепочки export→verification и
остальные типы собственного evidence.

## Безопасный сценарий

1. На DIV выбрать **Wi-Fi → Проверить мою сеть → Захват аутентификации** для своей
   сети или сети с явным разрешением, затем экспортировать проверенный `hc22000`.
2. Подготовить локальный проверенный corpus и не добавлять его в репозиторий.
3. Проверить входы без оценки candidates:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --preview-only
   ```

4. Запустить с явным подтверждением владения, конечными budgets и durable checkpoint:

   ```sh
   python3 tools/owned_wifi_evidence_verifier.py \
     --evidence owned.hc22000 --corpus common.txt \
     --corpus-id curated-common --corpus-version 2026.09 \
     --corpus-class common --max-candidates 10000 --max-seconds 30 \
     --checkpoint verification.checkpoint.json \
     --owned-evidence-confirmed --report verification.report.json
   ```

5. Для результата `paused` повторить ту же команду с `--resume`. Изменение evidence,
   corpus или metadata corpus делает checkpoint недействительным.

`weak_password_match` означает только то, что один candidate corpus воспроизводит
все переданные records. Report намеренно его не раскрывает. Пароль следует изменить
штатным интерфейсом роутера и повторным capture подтвердить исправление.

## Приёмка

Focused delta — `tools/test.sh --only owned-wifi-evidence`. Она проверяет canonical
export Leshy, официальный reference-вектор PMKID Hashcat mode 22000, positive/negative
WPA*01 и WPA*02, strict parser, privacy-safe report, bounded checkpoint/resume и
source-contract без network/device/radio операций.
