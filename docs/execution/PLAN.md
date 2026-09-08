# Product execution plan

Coordinator: Codex task `01a07f44-7d89-7052-b968-5e96753493ad`.
Baseline: `82fd60e`, inspected 2026-09-07 America/Chicago.
Shared live plan: `/Users/anuragduddu/code-projects/fieldmuseum/specimen-digitization-coordination/docs/execution/PLAN.md`.
This coordination worktree is deliberately separate from implementation worktrees.

## Objective and authority

Build the PRD's complete Insects pilot vertical slice and an extensible cross-platform product. The parent task plans, delegates, coordinates, and reviews; implementation occurs in separate user-visible tasks and worktrees. The user explicitly requested parallel tasks, branches, worktrees, and GPT-6 astra medium for complex work. Use that model/effort for these initial complex workstreams. Do not interpret this plan as institutional approval of quality thresholds or provider data policy.

Authoritative inputs: repository AGENTS.md; docs/DEPLOYMENT.md; the entire docs/product-requirements/PRD.md; HARNESS_OPTIONS.md; HUGGINGFACE_MODEL_ROUTING.md; OBSERVABILITY_AND_EVALUATION.md; GBIF.md; internal research. Read applicable documents completely before making related decisions. Verify live SDK details from official primary documentation. Existing source and tests are the baseline, not evidence of an already complete application.

## Observed baseline

- Existing targets: Flutter web, Android, iOS. Provisional first-release targets are those three plus desktop browsers, pending user response.
- Python provides typed transcription, HF gateway, pinned hub assets, prompt registry, Logfire instrumentation, and evaluation foundations.
- No implemented SQL Connect schema, application API, complete intake/review UI, or durable processing vertical slice was found in the initial inventory.
- Latest main CI/CD run 34185255766 succeeded. Current pipeline deploys Hosting only. Cloud data/runtime readiness is unverified.
- Repository was clean on main; no open PRs at inspection.

## Ownership and sequence

1. **Architecture and contracts**: audit entire codebase and local/Git plans; map all PRD P0 criteria; publish versioned API/domain contracts and dependency decisions promptly. Own docs/execution/ARCHITECTURE.md, CONTRACTS.md, ACCEPTANCE.md. No product implementation. Resolve cross-team contracts before dependent integration.
2. **Backend and evidence workflow**: typed application service, Insects profile, evidence graph, authoritative lookup adapters, deterministic clearance, operational recovery, review transitions, API/auth boundaries, worker orchestration. Own Python application modules/tests and Python dependencies. Preserve existing HF/Pydantic/Logfire foundation. Coordinate persistence interfaces with data task and UI contract with architect.
3. **Flutter product**: responsive accessible intake, authentication, manifests, queues, status, specimen/review workspace, evidence/disagreement display, corrections and recovery. Own apps/specimen_digitization only. Real API wiring required; isolated synthetic demo mode may assist testing but must be explicitly labeled and never imply live processing.
4. **Data and platform**: SQL Connect schema/operations, storage rules and immutable asset contracts, Google Secret Manager runtime binding design, emulator tooling and data authorization tests. Own dataconnect/, storage configuration, platform docs, infrastructure proposals. Inspect existing Google resources read-only. Coordinate Firebase configuration with release task. No production schema changes/provisioning without authorization.
5. **CI/CD and release**: audit existing required checks and public baseline; platform build matrix; preserve protections; own .github/, scripts/ci/, deployment documentation and root Firebase configuration. Establish safe separately reviewed runtime/data delivery proposal, without bypassing current Hosting-only contract. Own integration branch later, reconcile commits, run canonical verification, create PRs, watch CI, and record exact release evidence if authorized.
6. **Independent acceptance review** (second wave): inspect integrated implementation against every P0 criterion, threat boundaries, reliability and accessibility. Independently reproduce an end-to-end synthetic fixture and failure cases. Report pass/fail/blocked with evidence, no fabricated institutional approval. Own QA reports, not implementation; send concrete defects to owners.

First wave starts architecture, backend, Flutter, data, and release tasks concurrently. Architecture publishes contracts early; teams can inventory/test baseline while contracts settle. Each task changes only its worktree. Communicate breaking interface proposals through coordinator before implementation. Second wave integrates and reviews; owners repair discovered defects. Do not call disconnected components a working product.

## Shared documentation protocol

Each task reads this absolute shared plan and writes its own report under its own worktree docs/execution/<WORKSTREAM>.md. Report branch, worktree, HEAD, scope, files, commands/results, requirements covered, known gaps, decisions and exact blockers. Send coordinator task messages with contract milestones and handoff locations. Coordinator alone updates this shared PLAN.md and STATUS.md. Architect publishes shared contracts in its own worktree and tells coordinator the absolute paths; coordinator distributes paths to all tasks. Integration copies reviewed documentation into the final branch so Git retains the durable plan, decisions, test evidence, and runbook. Never include credentials or restricted museum data.

## Integration contract requirements

- Organization/collection scoped identity and server authorization, not client-only controls.
- Stable specimen/asset/run IDs; checksums and immutable original references; bounded upload metadata; resumability and deduplication.
- Versioned profile, models/providers/prompts and observations; independent readings remain immutable.
- Literal, candidate, resolved and authoritative evidence remain distinct.
- Exactly three final dispositions; retryable operational problems remain processing/blocked states.
- Corrections supersede affected results and rerun dependent validation; optimistic concurrency and idempotency required.
- Source regions, unresolved disagreements, required-field semantics and external-authority limitations must remain visible.
- Emulator/synthetic mode and real production configuration must be unmistakably distinguishable. Missing runtime/provider configuration produces actionable blocked state, not fabricated success.

## Verification and definition of done

Map all 20 PRD section 19 requirements to concrete tests and manual evidence. Include upload interruption, duplicate requests, process restart, independent observations, missing mandatory fields, unknown semantics, unauthorized access, stale review writes, lookup ambiguity/429/timeout/auth failures, and reconstruction from persistence. Test meaningful behavior, not mock-only assertions that mirror implementation. Build/analyze/test available Flutter targets and explicitly identify unsigned/unrun device builds. Representative museum quality acceptance remains blocked until approved data, thresholds and reviewers exist.

Before any push, run scripts/ci/verify.sh in that worktree. Do not bypass hooks/checks or commit secrets. Integration must pass canonical gates with all components combined. Production release requires merged PR, all required checks, green main run and deploy job, matching public deployment.json SHA, and public app smoke; report all evidence. No workstation deployment, no broadened Hosting deployment, no AWS. Never weaken protections or WIF.

## Pending user input and safe defaults

- Requested overnight spending cap and permission for production merges/cloud provisioning. Until answered: local/emulator implementation, read-only cloud inspection, tests and draft PRs; no paid inference, new billable resources, secret rotation, or production merges.
- Requested launch platforms; proceed with web/Android/iOS existing targets while awaiting answer.
- Unknown institutional semantics, authority access and clearance policy: require explicit review and fail closed. No guessed Verbatim D/T/S, Parties IRNs, mandatory values, quality thresholds, or museum approval.
- SAM 3 serving and durable-engine selection require existing bounded validation gates. Implement honest adapters and failure tests; do not label a fixture or bounding-box placeholder SAM 3 inference.

## Morning handoff

Provide what is runnable and exact commands/URLs, integrated SHA/PR/CI status, tested platforms, verified user journeys, synthetic vs live distinctions, unresolved blockers with owner/action, and next work. The full product is incomplete while mandatory workflow or release evidence is missing.
