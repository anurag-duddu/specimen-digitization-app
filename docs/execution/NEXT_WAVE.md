# Next implementation wave after the first integrated slice

Status: dispatch-ready planning, 2026-09-08 America/Chicago; no code or cloud
change. Architecture worktree `969e`, branch `codex/architecture-contracts`.
Baseline reviewed: backend implementation `80b432eab35e97c04b6776373563a3128bf4b702`
via immutable Git reads, its current BACKEND.md handoff in worktree `3782`, and
integration RUNTIME_PROPOSAL.md in `80e6`. The latter is a proposal, not deployed
infrastructure evidence. Flutter's current FLUTTER.md in `6b01` was consulted for
remaining client dependencies. Full PRD v0.6 and the prior architecture/acceptance
contract govern this comparison. Shared PLAN.md was reread for this pass.

The first integrated candidate is an independent QA baseline. It is not the
finished product. Continue three bounded workstreams while QA tests that candidate;
keep QA fixes separate from new-feature integration so evidence names an exact SHA.

## Immediate recommendation

1. Keep the existing backend owner on reliability and shared integration. Fix
   concrete scanner/lease/retry/budget gaps; preserve the working checkpoint path.
2. Start a collection-profile, image-quality and classification module task.
3. Start an authority/evidence-phase and explainable-risk module task.

The existing data owner supplies named paginated queries and history/projection
operations. The existing Flutter owner consumes additive contracts after the
module fixtures land. Backend alone changes shared workflow/domain/API files.
No new broker, workflow engine selection or paid service is needed to implement
these improvements locally. Deployment, real-model evaluation and institutional
approval remain separate gates; code that can be built now is not externally
blocked merely because final acceptance needs those gates.

## What the existing reliability implementation actually covers

| Concern | Evidence at backend 80b432e | Remaining work, without overstating absence |
|---|---|---|
| API exits after intake or review | `worker.py` scans retained specimens and calls one workflow step; SQL/SQLite snapshots retain next stage | Supervise a separate process in eventual runtime. Do not depend on API BackgroundTasks or request-billed background CPU |
| Duplicate logical work | `workflow.py` commits intent before external stage, records completed steps, uses aggregate revision CAS for result | Preserve this; test all crash/race boundaries through actual SQL, not only concurrent final writes |
| Concurrent provider calls | A persisted five-minute lease makes another worker return while work is in flight | No heartbeat/duration policy. Define maximum call duration below lease, or renewal with fencing; test expiry and slow provider explicitly |
| Crash after possibly executed external effect | Expired intent becomes processing_blocked/external_outcome_unknown; explicit retry required | Correct conservative behavior. Do not introduce automatic repeat of unknown paid effects or claim exactly-once billing |
| Known taxonomy transient failures | 429/timeout/provider-error schedule persisted retry time and block after three attempts | Generalize typed behavior to other adapters, honor Retry-After safely, add jitter/circuit and run-level budgets |
| Scanner completeness | `SqlConnectRepository.list` loops offset pages of 100 only to 10,000, reconstructing every full snapshot; worker repeats each second | Due-work summary/keyset paging, no silent truncation, fairness across scopes, bounded requests; mutable offset order is not a stable work cursor |
| Worker resilience | Worker catches Conflict, refreshes production memberships each loop | Storage/membership/unhandled step errors can terminate loop; isolate records/scopes, bounded control-plane backoff, health/stop semantics and supervised restart |
| Cancel/retry while old worker runs | Revision changes reject old logical commit | Current retry/resume clears blocker without checking active lease. Prevent overlapping retry of still-running effect; cancellation fences results but cannot promise remote request cancellation |
| Atomic dispatch | Data operations persist outbox with snapshots; worker discovers state by scanning | Outbox consumer is not necessary to recover jobs while correct scanning exists. Consume/prune outbox only when it provides measured dispatch/audit value; do not add a second authoritative scheduler |
| Long history | Immutable snapshot reconstruction and 256 KiB rejection already work | Repeated previous_runs/audit copies can exceed bound; paginated immutable history/projections needed for sustained review, never truncate old evidence |
| Runtime deployment | API/worker local commands and production adapters exist | Container binding/PORT, supervision, identities, transport readiness and approved delivery absent. A successfully built API container alone cannot host the complete processing plane |

Evidence of passing SQL/TCP restart, raw-request independence and 54 Python tests
is reported by BACKEND.md; this planning pass inspected source and reports, and
did not rerun those tests. Polling/leases are real application reliability
mechanisms. They do not satisfy the mandatory Temporal versus Google Workflows
comparison or establish production service availability. The runtime proposal's
phrase “implement durable worker dispatch/lease behavior” should be narrowed to
hardening/validating existing dispatch and leases plus selecting their hosting,
not interpreted as a requirement to replace working code with an unproven engine.

## Prioritized gap map against the full PRD

| Priority | Implementable gap | PRD / acceptance | Owner path |
|---|---|---|---|
| First | Scanner loss/starvation, active-effect retry races, worker exception isolation, bounded budgets/retries | HAR-009, OPS-001/002/003, §16.1; P0-09/13/17/20 | Task 1 with data support |
| First | Immutable run dependency resolution; current production transcriber resolves managed prompt on each call | PRF-002/003, TRN-005, §10.2/14.4; P0-05/16/17 | Task 1 integrates Task 2 profile contract |
| First | Configurable taxonomy/profile selection and real ranked classifier adapter; classify currently marks intake selection only | CLS-001/002/003/005; P0-03 | Task 2 modules, Task 1 wiring |
| First | Executable image quality feedback, orientation transforms, missed/overlap/zero-region checks | ING-005/007, SEG-002/003/005; P0-01/04 | Task 2 modules, Flutter later |
| First | Phase implementations/applicability evidence; plan/resolve/normalize/validate currently advance labels, while actual validators run in finalize | HAR-001..010/019; P0-07/08/10/12/16 | Task 3 modules, Task 1 wiring |
| First | Qualified Parties identity and evidence rules; draft semantics flags currently prevent real clearance but are not a complete authority contract | §12.4, QUE-002; P0-10/11/16 | Task 3; institutional approval remains separate |
| Next within wave | Explicit field candidates/alternatives and supported geographic transformations; no automatic institutional source precedence | HAR-004/005/010, REV-003; P0-07/08/16 | Task 3 |
| Next within wave | Span/line/field disagreement and language/script metadata, explainable label/specimen risk | TRN-006/007/009, SCR-001..004; P0-05/06 | Task 3; quality components from Task 2 |
| Next within wave | Normalized projections, bounded current snapshot, paginated history and all search dimensions | EXP-001, §14/16; P0-16/17/20 | Task 1 + data, Flutter later |
| Client follow-through | Region rotation/polygon/mask interactions, raw response retrieval, date/uploader/risk filters and automated capture feedback | SEG-004, REV-001..007, EXP-001; P0-01/04/06/15/19 | Existing Flutter owner, backend endpoints from Task 1 |
| Client/decoder follow-through | HEIC and profile-approved RAW/TIFF decode, lost-camera-result recovery, real device permission/resume behavior | ING-001/005, §16.4; P0-01/19 | Flutter + Task 2 decoder proposal; actual devices/format rights separately checked |

Do not silently reclassify P0 work as future production hardening. Some recovery
and correction features labelled P1 in section 11 are explicitly required by
section 19 and stay acceptance requirements. Conversely folder/cloud-URL intake,
advanced historical reasoning, BYOK administration and EMu export are not reasons
to delay these P0 fixes. Keep later-phase features on a separate backlog.

## Task 1 — harden persisted execution and bounded product history

Suggested branch `codex/runtime-recovery-next`; existing backend owner. Start from
the coordinator's clean integrated candidate including first-wave QA repairs.

Exclusive shared ownership: `application/worker.py`, `workflow.py`, `storage.py`,
`production.py`, `api.py`, `domain.py`, existing `harness.py`, `policy.py`, `lookup.py`,
Python dependency files and existing backend tests. Own new
`tests/test_worker_recovery.py`, `tests/test_history_paging.py` and
`docs/execution/RELIABILITY_NEXT.md`. This owner is the sole composition point for
Tasks 2/3. Data owner alone changes `dataconnect/` and its tests; send reviewed
operation contracts before changing the adapter. No parallel edits to shared files.

Bounded deliverables:

- Replace all-record/full-snapshot scan with bounded eligible-run summary pages.
  Publish `list_due_runs(scope, now, cursor, limit)` returning stable run/specimen
  IDs, expected revision, due time and next_cursor; fetch snapshot only for work
  attempted. Cursor scope/filters and deterministic tie-break order are explicit.
  Re-scan safely so changes cannot permanently strand work; no fixed silent cap.
- Isolate record/scope failures and back off on SQL/auth outages without hot loops.
  Preserve revoked membership denial and stop new effects for affected scope.
  Expose safe worker health, oldest due item, attempts and blocker counters.
- Define lease policy and guarded retry/resume. A still-valid lease cannot be
  cleared into a concurrent provider request. Late results after correction or
  cancellation fail CAS. Either constrain external timeout below lease with margin
  or implement fenced renewal; choose one from measured adapters, not both by
  default. Keep outcome-unknown reconciliation explicit.
- Persist run time/tool/request/token and approved cost budget state; reserve/check
  before effect and record actual usage after. Existing extractor's two-request,
  16,000-token cap is a useful local bound, not a whole-run budget. Unknown cost
  availability is not zero cost. Add typed safe retries/jitter/circuit with tests;
  no real paid call needed. Never set an institutional spending limit implicitly.
- Pin resolved prompts/profile/adapter dependencies before eligible effects so
  resume does not resolve a new managed label silently. Coordinate Task 2 output.
- Move historical graph/audit growth behind immutable referenced versions with
  paginated reads and bounded current summary, using existing data tables where
  practical. Keep old snapshot readers/migration compatibility and digest checks.
  Data supplies indexes/operations for due-work, history and search projections.
  Do not populate unused tables merely to claim normalization; project the fields
  needed by work discovery, retained history and PRD search.

Acceptance: multi-process SQL races, interruption before/after intent/result/ack,
active-lease retry rejection, expired unknown outcome without extra provider call,
late completion rejection, one poisoned record among healthy work, temporary SQL
failure and recovery, due work beyond 10,000 without omission, bounded query counts,
correct retry time/budget exhaustion, and history exceeding former aggregate bound
without evidence loss. Run same scenario through actual HTTP and SQL emulator;
freeze shared response fixture changes. No broker is an acceptance requirement.

## Task 2 — collection profiles, classification and image quality

Suggested branch `codex/collection-quality-next`; new independent worktree task.
Own NEW modules `application/collection_profiles.py`, `classification.py`,
`image_quality.py`; matching new `test_collection_profiles.py`,
`test_classification.py`, `test_image_quality.py`; report COLLECTION_QUALITY.md.
Read shared modules but do not edit them, Flutter, SQL, dependencies or workflow.
Request dependency changes through Task 1; pure existing-library implementations
are preferred where sufficient.

Publish first: immutable `ProfileDefinition`, `ClassificationResult` and
`ImageQualityResult` models in owned modules. Profile includes taxonomy node,
version/digest, field requirements/semantics status, approved route/prompt/rule
references, input policy and applicability. Classification includes ranked
candidates, evidence/provenance, selected/missing mapping and required review.
Quality includes original dimensions/orientation, algorithm version, measurements,
reason codes and diagnostics with unknown/unmeasured states. Task 1 maps these
additively into the API and invokes named handlers.

Implement configurable immutable published-profile resolution and two distinct
synthetic profile fixtures to prove correction/invalidation, without inventing a
second museum collection or moving a specimen across permission scopes. Separate
classification node selection from storage tenancy; if transfer changes collection
scope it needs explicit source/destination authorization and preserved history.
Real prediction uses an application-owned adapter plus replay fixtures; a fixed
Insects default or manual choice cannot be labelled a model prediction.

Implement deterministic bounded blur/exposure/resolution and geometry/overlap
checks, orientation-corrected derivative transforms and a format capability matrix.
Glare/focus/framing indicators require stated measurement limits; return unmeasured
rather than pretend a heuristic verifies all label coverage. Define full-image
coverage-check adapter and reviewer interaction; validate offline fixtures now,
real SAM 3/quality calibration later. Propose HEIC/RAW decoder work with actual
license/runtime/fixture checks before dependencies are added.

Acceptance: missing/ambiguous mappings fail closed, immutable version edits are
rejected, profile change invalidates dependencies, no cross-scope escalation,
rotated source-to-crop round trip, out-of-bounds/missed/overlapping/zero regions,
small corrupt files and bounded decode limits, quality signals respond to
controlled synthetic degradations and expose unmeasured components. A handler
exists for real classification without making paid calls; calibration and real
prediction quality remain explicitly unaccepted. Task 1 wires these into the
running application; Flutter exposes results and correction after fixture freeze.

## Task 3 — typed evidence phases and authoritative candidates

Suggested branch `codex/evidence-authorities-next`; new independent worktree task.
Own NEW modules `application/evidence_harness.py`, `authority_registry.py`,
`parties.py`, `geography.py`, `review_risk.py` and matching new tests; report
EVIDENCE_NEXT.md. Do not modify existing workflow/domain/policy/harness/lookup/API,
SQL or Flutter. Task 1 reconciles integration with existing GBIF and extraction;
no duplicate model gateway or second clearance policy.

Publish first: typed phase input/result (`phase/version`, candidates, evidence,
findings, tool outcomes, applicability and budget usage), authority request/result,
qualified Parties identity and versioned risk components. Use shared disposition
semantics; a phase only proposes, the existing deterministic policy commits.
Preserve candidates separately from selected values and preserve temporal/literal
geography and unsupported alternatives.

Implement explicit parse/plan/lookup/resolve/normalize/validate/finalize handlers
or justified non-applicable results; do not mark a no-op label as a completed
validation. Reuse current exact-source extraction and GBIF result evidence.
Add typed allow-listed registry for adapters with all PRD failure outcomes and
captured query/source/version/digest/rights metadata. Build Parties matching over
a clearly synthetic or approved read-only export adapter; confirmed identity must
include system, tenant, environment, eparties module and IRN. No catalogue IRN or
name-only match can satisfy that gate. Geography adapter contracts and local
fixtures can preserve conflicting/historical/modern candidates now, while live
Google/Mapcarta access, terms and precedence remain gated.

Add line/span/field disagreement evidence and language/script candidate metadata,
plus versioned explainable label/specimen review-risk components. Uncalibrated
risk is triage, never accuracy or clearance authority. External lookups enrich
separate candidates without replacing literals. Unknown date/elevation/Parties
semantics remain failed gates, even when the code can represent them.

Acceptance: candidate alternatives preserved, provenance traversable to pixels,
phase applicability persisted, wrong-module IRN rejected, ambiguous person not
selected, unknown semantics cannot clear, geography conflict retained, no-match
versus 429/auth/malformed distinguished, source snippet insufficient, exact replay
without external calls, budget exhaustion abstains, minority numeral and script
uncertainty visible, component scores cannot override hard gates. Include actual
local HTTP adapter harness tests with injected responses rather than assertions
only on constructed enums. Live institution/provider acceptance stays separate.

## Cross-task merge contract

Tasks 2 and 3 may work concurrently because they add separate modules/tests and
publish serializable handler models. They do not edit shared state or product API.
Task 1 integrates handlers in small reviewed commits; data owns query contracts
and schema changes, Flutter owns client integration. If domain schema extension
is required, send Task 1 an exact field/schema/example proposal first. Do not copy
a shared file into both branches and hope final merge resolves semantic conflicts.

Keep v0.1 canonical response names; additive versioned quality/classification/
candidates/risk/history fields get executable fixtures generated by the backend.
Flutter tests the identical file. Breaking history/persistence schema changes
need explicit compatibility readers and migrations, locally tested without
production schema writes. Existing QA regression failures take priority over new
capabilities; tests retain the candidate that failed and the commit that fixes it.

Every owner reads shared PLAN/AGENTS/DEPLOYMENT, uses an isolated codex branch,
reports actual paths, commits only owned files and runs canonical verification
before any push. Coordinator dispatches the user-visible tasks. This architecture
pass does not spawn or execute them.

## External gates and bounded work possible now

| Gate | Concrete work now | Evidence/authority still needed |
|---|---|---|
| Real SAM 3 and HF runs | Validate adapter requests, masks/transforms, route allowlists, synthetic/replay/failure cases | Approved license/model/serving/region/budget and representative data; real quality/latency results |
| Parties/geography institutional policy | Typed adapters, synthetic authority fixtures, qualified identity and abstention | Field IT read-only authority/export and permitted fields; collection matching/source precedence/date/elevation/DTS policy |
| Durable engine choice | Prepare one deterministic failure scenario consuming existing step/checkpoint interfaces; local Temporal trial if assigned | Same scenario in Google Workflows under approved resources/spend, compare recovery/versioning/effort; do not select via document or polling success |
| API/worker containers and runtime | Build proposal and local container/PORT/readiness/auth tests in later release-owned scope | Separate reviewed delivery contract, Cloud Run/registry/API enablement, identities/ingress/budget and supervised worker hosting |
| Data launch | Emulator migration compatibility, history queries, restore procedure on disposable local DB | Approved connector/rules publication, actual IAM tests, backups/PITR and restore objectives/proof; no inferred paid HA requirement |
| Quality/accessibility/device acceptance | Frozen synthetic regressions, semantics/keyboard tests and explicit device matrix | Approved expert cohort/thresholds, staff review, screen reader/device camera/App Check evidence |
| Production | Local integration and PR/CI evidence | Authorized merge and full Hosting SHA/deploy/public smoke plus separate runtime/connector proof |

The engine comparison remains required before final production engine selection,
but does not block independent application P0 work above. Outbox consumption and
normalization must be justified by concrete access patterns; no new broker,
Firestore, AWS, warehouse, arbitrary browser agent or EMu write path is proposed.

## Planning verification

This pass read exact backend source for workflow, scanner, SQL persistence,
production adapters, action endpoints, extraction, policy and test inventory,
plus the handoff/runtime/client reports. Source locators: `Workflow._step` and
`next_step`; `worker.main`; `SqlConnectRepository.list/_commit`; API `action`;
`ProductionAdapters.transcribe`; `extract_with_agent`. Findings are static
implementation observations, not newly reproduced defects or production claims.
Only this planning document changes. No inference, cloud mutation, code edit or
deployment. `git diff --check` and document commit hooks are the applicable checks;
canonical verification remains mandatory before any later push.

## Urgent first-candidate repair: B04 audit amplification

Reviewed frozen QA candidate `25e8358` and the backend reliability worktree after
QA reported eleven ordinary review actions yielding 223,585 audit bytes in a
244,139-byte snapshot; the twelfth action returned 413. Those measurements are
QA-reported, not rerun in this architecture pass. Static cause is confirmed:
`api.py:811` captures `s.run.model_dump(mode="json")`, then lines 953–958 embed
that entire run in every review AuditEvent. `Run` does not contain `audit`, so
this is repeated full-run payload duplication, not recursive nesting of events.
The current repair worktree retained the same pattern at inspection.

Recommended minimal design, sent directly to backend:

- Retain event ID, sequence, actor, timestamp, action, reason, target and source
  context. Store a small server-computed changed-target delta where bounded;
  never trust the client's `before` as authoritative audit evidence.
- Persist full before/after payloads with the existing immutable BlobStore. A
  versioned reference includes kind, specimen/run ID, base/result revision,
  immutable blob reference and SHA-256. Avoid unbounded arbitrary client `after`
  dictionaries; validate by decision type and offload retained payloads as needed.
- Add an authorized event-detail read resolving only a reference reached through
  the authorized specimen/event. Recheck current organization/collection and
  sensitive permission, verify digest, and return complete retained values.
  No arbitrary blob-reference read endpoint or permanent public URL. Existing
  inline events remain readable; this is an additive reference representation.
- Before size validation on a successful next write, compact existing legacy
  inline audit payloads in memory into verified references, preserving original
  event IDs/order/content. Thus a near-cap existing record can make progress;
  fixing only newly appended events is insufficient. Leave old immutable SQL
  snapshots and idempotency receipts unchanged.
- Write/verify blobs before the existing snapshot+CAS+receipt transaction.
  Failed CAS may leave an unreferenced immutable object; it must not create an
  audit event or receipt or overwrite retained evidence. No separate SQL schema
  or database mutation outside the application is needed.

Payload offloading removes the immediate amplification. An indefinitely growing
inline event array still eventually reaches the cap: use bounded immutable audit
pages with a digest-linked predecessor and a bounded current tail when needed,
reachable from the same snapshot reference. Persist global sequence/count and
paginate events without flattening all pages into the aggregate. This can use
existing blob storage without a new relational schema. Every archived event must
remain retrievable, including after process restart. Do not describe an inline
array with smaller entries as unbounded-history support. Previous-runs graph
amplification is a related next-wave issue; do not silently truncate it as part
of the first-candidate repair.

Alternative: references to already-retained scoped immutable record revisions
(SQLite versions / SQL GetSnapshot) can reconstruct full before/after state if
backend adds a consistent authorized get_version interface. Prefer whichever
backend can prove with fewer changes; do not implement two competing archives.
Do not make first-candidate recovery depend on the second-wave schema rollout.

Acceptance for the minimal repair: repeat QA's exact HTTP approval/integrity-
restore sequence beyond its former failure; recover a legacy near-cap snapshot
through ordinary authorized API writes; retrieve and compare every event's full
before/after bytes or canonical digest; verify event IDs/order/reasons and raw
observation hashes survive restart; stale CAS and duplicate keys leave exactly
one decision; cross-scope/event/reference substitution denied; missing/corrupt
blob fails explicitly; 256 KiB gate remains enforced. If audit paging is included,
force page rollover under a small test threshold and verify all event pages.
No direct SQL repair, raised cap, missing history or mutation of old snapshots
can count as B04 resolved. Architecture advice is not implementation/test proof.

### B04 selected repair: existing retained snapshots

Coordinator/backend selected the retained-revision alternative above. This
supersedes the blob-archive recommendation for this first-candidate repair; do
not implement a parallel archive. Backend proposes audit.before references to
exact immutable revision plus run digest, compaction of exact already-retained
audit/previous-run prefixes at 128 KiB, an explicit history-through marker and
bounded fixed-revision GetSnapshot retrieval. Architecture accepts this subject
to these invariants and executable proof:

- Reference scoped specimen ID, exact older revision, run ID and canonical run
  digest. Verify stored snapshot integrity and selected run digest; never resolve
  against the mutable current run. References must strictly decrease revision.
- Remove only a canonically identical prefix proven retained in that older
  snapshot, not an arbitrary slice or run-ID-only match. Preserve global event
  sequence/count, event IDs, history-through revision and bounded current tail.
  Reconstruct without omission/duplication. Previous-run content must match the
  complete retained version before replacing it with a reference.
- History pagination fixes its revision boundary, authenticates current scope and
  sensitivity, bounds traversal, and rejects malformed/cyclic references. Old
  snapshots and idempotency receipts remain immutable; no schema rollout needed.
- Compact legacy near-cap state before adding/checking the next event, while the
  resulting state still commits through the unchanged CAS/receipt transaction.
  A failed/stale write cannot publish a new history marker or partial event.
- Prove at least 100 ordinary HTTP review actions, recovery of the QA legacy
  near-cap shape, complete before/after and prior-run retrieval after restart,
  stable sequence/order/digests, duplicate receipt behavior and authorization.
  The 128 KiB threshold is a compaction trigger, not a higher acceptance cap.

Flutter's older-history UI is part of the chosen retrieval path; backend-only
retention cannot substitute for accessible complete review history. Architecture
has sent these conditions directly to backend. B04 remains unresolved until
independent QA verifies the chosen implementation on its repaired candidate.
