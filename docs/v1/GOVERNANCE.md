# ESP32-Leshy 1.x — documentation as the source of truth

*Read in: **English** · [Русский](GOVERNANCE.ru.md)*

Document status: **binding project rule**.

The 1.x documentation defines the product before implementation and records evidence
after it. Code, an issue, a verbal agreement, or a 0.x menu item cannot independently
change the 1.x scope.

## Canonical structure

| Question | Single normative document |
|---|---|
| Where is the project now? | [STATUS.md](STATUS.md) |
| Why does the product exist and for whom? | [VISION.md](VISION.md) |
| What must 1.0.0 deliver? | [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) |
| What is the complete user-facing 1.0 scope? | [CAPABILITY_CATALOG.md](CAPABILITY_CATALOG.md) |
| Why is the catalog considered complete? | [CAPABILITY_REVIEW.md](CAPABILITY_REVIEW.md) |
| How must core user paths behave? | [REFERENCE_WORKFLOWS.md](REFERENCE_WORKFLOWS.md) |
| When are UX and visual appearance agreed? | [UX_UI_BASELINE.md](UX_UI_BASELINE.md), [UX-01](UX_SCREEN_MAP.md), and [UX-02](UX_STATE_MATRIX.md) |
| What resource limits are measured or provisional? | [RESOURCE_BUDGETS.md](RESOURCE_BUDGETS.md) |
| Which durable risks constrain delivery? | [RISK_REGISTER.md](RISK_REGISTER.md) |
| What can the board physically do, and which modes conflict? | [HARDWARE_ENVELOPE.md](HARDWARE_ENVELOPE.md) |
| Through which stages is 1.0.0 delivered? | [DELIVERY_PLAN.md](DELIVERY_PLAN.md) |
| How do requirements map to implementation and tests? | [TRACEABILITY.md](TRACEABILITY.md) |
| How is the system structured? | [ARCHITECTURE.md](ARCHITECTURE.md) and the [accepted ADR index](adr/README.md) |
| How is UI driven and captured without routine operator work? | [UI_AUTOMATION.md](UI_AUTOMATION.md) |
| How is a release candidate automatically verified on real hardware before publication? | [PRE_RELEASE_HIL.md](PRE_RELEASE_HIL.md) and accepted [ADR-005](adr/ADR-005-pre-release-hil.md) |
| How is atomic storage verified without risking unknown media? | [STORAGE_HIL.md](STORAGE_HIL.md) |
| How is each stage's intermediate result verified? | [STAGE_DEMO.md](STAGE_DEMO.md) |
| Why was a priority introduced? | Research such as [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) |

README files are navigation only. Research explains decisions but does not directly
set scope. The former `ROADMAP` remains as a redirect for external links and carries
no live status.

## Conflict precedence

1. Safety, licensing, and legal constraints.
2. An accepted `PR-*` or `NFR-*` requirement.
3. The `CAP-*` catalog as a view of accepted scope without weakening requirements.
4. An accepted ADR for a specific technical decision.
5. The `S*` stage gate, UX baseline, and Stage Demo contract.
6. Architecture narrative and research.
7. The 1.x implementation.

A conflict is never resolved silently by choosing the newer-looking document. Work
stops on the affected area, the inconsistency is recorded in `STATUS`, and all
normative documents are updated in one change before code follows the decision.

## Change lifecycle

Every 1.x behavior change follows one path:

1. **Intent:** identify a `J-*` user job, `PR/NFR-*` requirement, and `S*` stage. If
   they do not exist, change the documentation first.
2. **Decision:** accept an ADR for a significant or hard-to-reverse choice. A proposed
   ADR cannot make implementation complete.
3. **Implementation:** code stays within the requirement acceptance criteria and the
   active stage.
4. **Verification:** add an automated or HIL check and store a link or reproducible
   command as evidence.
5. **Synchronization:** update traceability and current status in the same change.
6. **Gate review:** mark a stage `done` only when every exit criterion has evidence.

## Status vocabulary

Stages use `planned`, `active`, `blocked`, `done`, or `reopened`. Only one stage may
be `active`. Requirements use `draft`, `accepted`, `implemented`, `verified`,
`deferred`, or `rejected`. Implemented without evidence is not verified.

## Definition of Done

Work is complete only when:

- a requirement and measurable acceptance criterion exist;
- implementation belongs to the clean 1.x target and adds no 0.x monolith dependency;
- unit/integration/HIL verification matches the risk;
- negative flow, cancel/back, and resource release are covered;
- EN/RU user copy and normative documents are synchronized;
- traceability and `STATUS` are updated;
- local links, host tests, and applicable firmware builds pass.

## Maintenance rules

- Update `STATUS` whenever the active stage, a gate, a blocker, or verified evidence
  changes; its date is the project freshness date.
- Change `DELIVERY_PLAN` only when stage boundaries or order change, not for daily
  progress.
- Do not delete requirements: mark them `rejected` or `deferred`.
- Put consequential technical decisions in ADRs, not only commit messages.
- Manual evidence names the board, procedure, build, and observable result.
- Update translations together. A mismatched ID or acceptance criterion is undefined
  until both versions agree.

## Minimum ADR fields

```text
ADR-NNN: title
status: proposed | accepted | superseded | rejected
date:
requirements:
stage:
context:
decision:
alternatives:
consequences:
verification:
```

An ADR is required for storage formats, resource/coexistence policy, framework and
toolchain, security boundaries, public SDK/API, and any choice whose replacement
would migrate data or rewrite several layers.
