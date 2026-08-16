# ESP32-Leshy 1.x documentation

Read this in: **English** · [Русский](README.ru.md)

1.x is a product and architecture reset. Documents here describe intended behavior;
they are not claims about the currently released 0.x binary.

## Start here

1. [Current status](STATUS.md) — active stage, evidence, risks, and next actions.
2. [Documentation governance](GOVERNANCE.md) — normative sources and scope changes.
3. [Stages to 1.0.0](DELIVERY_PLAN.md) — outcomes and S0…S8 exit gates.
4. [Complete 1.0 capability catalog](CAPABILITY_CATALOG.md) — what feature-complete
   1.0 must include.
5. [UX/UI baseline](UX_UI_BASELINE.md) — when workflows and appearance are agreed.
6. [Stage Demo protocol](STAGE_DEMO.md) — how each intermediate stage is verified.
7. [Goal traceability](TRACEABILITY.md) — goals to requirements, components, and tests.

Only `STATUS` contains live state. Other documents change when product boundaries or
accepted decisions change.

## Product definition

- [Product vision](VISION.md)
- [Competitive analysis](COMPETITIVE_ANALYSIS.md) — market snapshot and derived
  requirements
- [Product requirements and acceptance metrics](PRODUCT_REQUIREMENTS.md) — draft
  baseline
- [1.0 catalog product review](CAPABILITY_REVIEW.md) — completeness, overlap, and
  six closed scope-gap findings
- [Reference workflows](REFERENCE_WORKFLOWS.md) — happy/error/cancel paths and
  measurable acceptance
- [Resource budget ledger](RESOURCE_BUDGETS.md) — measured evidence, provisional
  guardrails, and open measurements
- [Risk register](RISK_REGISTER.md) — durable risks, controls, owners, and closure
  evidence
- [Hardware capability envelope](HARDWARE_ENVELOPE.md) — design evidence, resource
  domains, safe probes, HIL plan, and explicit unknowns
- [HIL probe operator protocol](HIL_PROBE.md) — safe diagnostic image, commands, and
  physical-evidence retention rules
- [UI automation and visual evidence](UI_AUTOMATION.md) — one input path, real TFT
  capture, and operator-free menu traversal
- [Automated pre-release HIL](PRE_RELEASE_HIL.md) — proposed build-once,
  physical-test, promote-same-bytes pipeline with screenshots and attestation
- [Storage atomicity HIL](STORAGE_HIL.md) — dual-head recovery, fault boundaries,
  and disposable-media safety

## Design and delivery

- [Target architecture](ARCHITECTURE.md)
- [UX-01: screen and Action map](UX_SCREEN_MAP.md)
- [UX-02: state matrix](UX_STATE_MATRIX.md)
- [Architecture Decision Records](adr/README.md) — binding toolchain, resource,
  storage, and Action-boundary decisions
- [Former Roadmap link](ROADMAP.md) — redirect only

## Working rule

We do not promote a competitor's menu item directly into the backlog. Every candidate
must map to an authorized user job, fit the ESP32-DIV capability/resource envelope,
and have measurable completion and safety criteria.
