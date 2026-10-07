# Taxonomy harness domain plan — 2026-10-07

Task/chat: Taxonomy harness; isolated branch `codex/harness-taxonomy`, worktree
`/Users/anuragduddu/.codex/worktrees/2e67/specimen-digitization-app`.
Baseline: `7890de551c75fe3b06836c7fb224f85dd2a2423a`, confirmed remote main at start.

1. Reproduce the G20 gap: a captured GBIF match for one reader plus an honest
   captured no-match for another reader on the same label must be eligible to
   settle. Missing evidence, a source failure, a tie, or another label that has
   not settled must remain unresolved. Retain each raw and adjudicated reading.
2. Preserve G23 authority precedence and G25 rank: GBIF COL XR decides; Global
   Names Verifier and Catalogue of Life support. Verify genus-only notation,
   synonyms, conflicting genera, exact captured provenance, and input lineage.
3. Improve taxonomy research input and stop guidance within existing source
   capture and budgets. Use only evidenced taxonomy context. Never invent a
   lineage or let an unsupported alternate name become deciding evidence.
4. Add focused offline regressions for validator, provider, captured-effect
   recovery, and automatic native publication where existing seams permit.
   Record fixture evidence separately from provider or live acceptance.
5. Append closeout evidence to `docs/SESSION_LEARNINGS.md` and make a local
   reviewable commit if focused checks pass. Integration, full verification,
   push, merge, paid canaries, and releases remain with Lane P.

Shared browser/code/memory/message-history recovery is owned by the geography
lane. This lane will describe precise taxonomy adapter requirements and will
not duplicate the shared runtime. Reusable procedures must preserve reviewed
authority and corrections; memory is not model training.

Dosu: no knowledge MCP tools are listed in this chat. CLI 0.66.1 reports expired
authentication and cannot save refreshed credentials in the sandbox. The
coordinator also reported monthly credit exhaustion; no knowledge retry or
billing/authentication mutation is part of this lane.

## Implemented domain slice

- `taxonomy.py` supplies pure GBIF query context, exact captured negative
  admission, supporting research stop checks, and detection of an available
  fully validated settlement. It creates no checkpoint or model authority.
- G20 alternatives are grouped by the aligned printed assertion and original
  reader, not just the label. Two names printed by one reader are independent
  assertions. G32 requires a positive settlement for each printed assertion
  across labels; a competing negative cannot erase it.
- A no-match must retain a completed same-scope/field GBIF semantic receipt,
  exact query digest, qualification and evidence. Source failure/refusal, a
  tie, missing capture or another accepted identity cannot replace it.
  Both values of the unused regional flag preserve valid taxonomy capture
  binding; specimen joins are never inferred into a negative name search.
  A second accepted identity for the same assertion cannot be silently dropped.
- GBIF receives only unanimous explicit whole-line `order:` / `family:`
  context from the same label. A rank substring in a locality line is excluded.
  Species/genus/synonym/homonym acceptance rules remain the existing GBIF rules.
- A policy stop cannot skip an explicit named assertion, captured same-line
  reader alternatives, GNV/COL research or a fully valid deciding settlement.
  Unkeyed labels still depend on organiser/reader assertion qualification;
  arbitrary capitalized words are not inferred to be taxa.
- Taxonomy source outages are tracked per exact query digest. Completed lookup
  B cannot recover failed lookup A. Completed captures replay without resending;
  an interrupted unknown send remains held for shared recovery.
- New jobs use taxonomy prompt v7; v1-v6 files remain unchanged. Acceptance v4
  fingerprints `evidence.py` and `taxonomy.py` together. Historical v1-v3 proof
  pairs remain readable; new historical-tagged captures remain refused. This
  lane does not rewrite frozen jobs, clear holds or migrate production pins.

| Evidence and stop | Taxon outcome |
| --- | --- |
| Accepted GBIF usage at the written rank, each assertion reconciled | Resolved; native publication is automatic |
| One reader confirmed, another captured no-match of the same assertion | Eligible to resolve under G20 |
| Independent printed assertion has no positive settlement, conflicting identities, unresolved tie | Structured unresolved result after scoped supporting research; existing missing policy routes Needs Human |
| No genus evidenced, including bare `sp.30` | No provider query; pinned unresolved missing-policy result |
| Source/capture failure or unknown send | Operational source/recovery state; no false no-match or new queue |
| Supporting source disagrees with valid GBIF | Retain disagreement as context/warning; GBIF decides |

## Exact shared-file integration hunks

- `evidence.py`: `_taxon_assertions`, `_validate_taxon_inputs`, and the taxonomy
  call from `validate_resolution`; no other domain's resolution semantics change.
- `sources.py`: GBIF parameter construction calls the domain helper; GBIF
  `NONE` never exposes a successful candidate.
- `agents.py`: taxonomy query identity in `masked_outages`; taxonomy-only
  unresolved output feedback. No new engine, scheduler or journal.
- `prompts/__init__.py`: taxonomy v7 constant and role mapping only; related
  existing prompt-table tests reflect that pin.
- `accepted_output.py`: v4 composite validator fingerprint, preserving v1-v3
  pairs. The integrator must recompute the v4 composite constant and Literal
  after composing any other lane's changes to `evidence.py` or `taxonomy.py`.

## Shared capabilities still required

Installed package source was inspected: Pydantic AI 2.51.0 and harness 0.36.0.
Current agent construction has instrumentation, persistence and delegation;
BrowserUse, Shell, CodeMode, Skills and Memory remain unconnected. This lane
did not install optional browser or Monty dependencies or configure a runtime.

- Browser: the shared adapter must admit GBIF/GNV/COL domains, use explicitly
  scoped models/budgets, and capture URLs, original inputs and raw responses.
  Browser summaries are research context until an approved source adapter
  validates them. `BrowserUse` has `allowed_domains`, `max_steps`,
  `session_scope` and `aclose()`; its implicit hosted model must not bypass the
  existing paid-effect reservation or identity policy.
- Code: expose domain-safe parsers/comparisons through shared `CodeMode` with
  bounded calls/resources. Keep `lookup_source` sequential and captured.
  Sandbox calculations never substitute for a deciding authority. `Shell`
  command allowlists alone are not an OS/network/secret sandbox.
- Procedures/memory: `Skills` may load a reviewed taxonomy procedure;
  `Memory` requires a persistent store and tenant/profile/domain namespace.
  Only reviewed general procedures, corrections and verified source lessons
  should be reusable. Model guesses and specimen identity are not authority.
  The default in-memory store does not provide durable recovery.
- Recovery: restore model messages plus captured per-query source outcomes;
  preserve original request/prompt, field revisions, effect holds and budgets.
  Completed capture replay is verified here; restored model-history wiring and
  invalid sibling-output salvage remain shared work. Taxonomy owns one field.
- Dependencies: related fields must arrive through verified assertions and
  settled dependency pins. General cross-label dependency population remains
  with the organiser/shared integration; this lane adds no inferred lineage.

Local fixture and composed publication evidence is recorded in the session
closeout. Live provider behavior, production release and scientific acceptance
are **Not confirmed**. Lane P retains integration, full verification, protected
review/merge, paid canaries and release ownership.
