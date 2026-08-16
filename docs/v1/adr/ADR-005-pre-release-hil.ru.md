# ADR-005: hybrid host-orchestrated предрелизный HIL

*Читать на: [English](ADR-005-pre-release-hil.md) · **Русский***

- status: `accepted`
- date: 2026-08-16
- amended: 2026-08-17 — release trust перенесён на keyless GitHub Artifact
  Attestations; постоянный station key отвергнут; принят one-command on-demand
  ephemeral runner lifecycle без macOS service
- requirements: PR-010, PR-014, PR-015, NFR-001…003, NFR-005, NFR-010
- stages: S2…S8

## Context

Release 1.x должен проверяться на реальном устройстве автоматически, включая
навигацию, реальные TFT pixels, resource cleanup и физические workflows. Текущие
serial/action/capture/HIL scripts уже доказывают feasibility, но release workflow
публикует binaries без device attestation, а разрозненные команды не образуют
versioned suite.

Полный self-test внутри firmware создаёт self-validation risk. Отдельная test image
не доказывает exact release bytes. Только внешний robot дорог для каждого commit, а
только emulator не проверяет устройство.

## Proposed decision

Принять hybrid boundary:

1. Release binary предоставляет локальный USB evidence plane: identity, public
   state/metrics, normal typed Actions, real TFT GRAM capture и safe-output state.
2. Host-runner владеет manifest, expectations, golden images, comparison, retries и
   итогом pass/fail.
3. CI собирает candidate один раз и GitHub-attests exact artifact через OIDC/Sigstore;
   HIL station проверяет provenance, прошивает exact SHA и формирует evidence bundle.
   GitHub Actions attests упакованный bundle, а publish job проверяет обе attestations
   и продвигает те же bytes без rebuild.
4. Destructive HIL остаётся отдельной diagnostic image/external-equipment lane и не
   заменяет smoke exact release candidate.
5. Небольшой camera/power subset дополняет GRAM capture перед RC для физических
   свойств, невидимых контроллеру дисплея.
6. Оператор запускает `tools/release_1x.py check <version>` при подключённой плате.
   Команда сама dispatches workflow и поднимает временный `--ephemeral` runner только
   на один physical job. `publish <run-id>` продвигает только успешный stable 1.x run
   и никогда не пересобирает candidate.

Операционный контракт: [PRE_RELEASE_HIL.ru.md](../PRE_RELEASE_HIL.ru.md).

## Alternatives

- полный on-device self-test;
- отдельная test firmware как единственный gate;
- только camera/button/power robot;
- только emulator/host screenshots;
- публикация после ручного просмотра неподписанных logs.

Каждый вариант сохраняется как вспомогательный слой, но не заменяет рекомендуемый
контур целиком.

## Consequences

- Нужны versioned USB protocol, manifest schema, golden review и HIL station.
- Release artifact становится immutable между build, physical test и publish.
- Ни HIL station, ни repository не хранят долгоживущий signing private key; identity
  выводится из GitHub workflow, commit/ref и protected environment.
- Runner archive может кэшироваться после SHA-256 verification, но config, token и
  work directory одноразовые; unique per-run label запрещает runner принять другой
  queued job; persistent listener/`launchd` запрещены.
- Безопасный evidence plane остаётся в production binary; опасная instrumentation —
  нет.
- Release может ожидать свободную станцию; очередь и quarantine становятся частью
  deployment reliability.
- GRAM capture сокращает ручную работу, но не заменяет camera, RF/power/audio
  instruments там, где нужны физические измерения.

## Verification

- один manifest-driven runner проходит cold boot→Home→Diagnostics→Back, сохраняет
  raw/PNG/state и подтверждает lease 0/safe outputs;
- intentional golden/state/candidate-hash mismatch обязан fail closed;
- interrupted runner quarantines station или доказывает safe recovery;
- `gh attestation verify` проверяет candidate и evidence archive с pinned repository,
  signer workflow и `refs/heads/main`; внутренний verifier повторно связывает archive
  с exact published binary;
- `check` не печатает `RELEASE READY` при любом cloud/HIL/provenance failure, а
  `publish` отвергает non-main, другой HEAD, prerelease version и неожиданный artifact;
- два последовательных RC проходят неизменную release suite по DEMO-S8.
