# Independent live rollout QA

> 2026-09-23: The owner's decisions in [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the
> decision. [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that
> still enforces a superseded clause until a later go-live pull request
> changes it.

Status: **Blocked for final live acceptance; local harness implemented.**
Owner: task `01a08219-3527-7523-8365-7c3a85c3ca67`.
Coordinator: `01a07f48-a57c-71b0-9642-c9430886049c`.
Worktree: `/Users/anuragduddu/.codex/worktrees/73c3/specimen-digitization-app`.
Branch: `codex/live-acceptance`.
Product baseline: `a53f855e963b457c3ee2065f387609a193bb6f32`.
QA source identity: exact final head and CI are recorded in the PR body and
coordinator handoff to avoid recursive report commits.
PR / CI: submitting after the passed canonical gate. No merge or deployment
authorized in this phase.

## Objective, authority and limits

Independently verify the functioning combined stack: real verified Firebase
user and App Check, assigned collection, exactly the authorized ten existing
cloud specimens, retained actual provider results, review/correction/history
and durable reconstruction. Own QA report, evidence directory and harness
only. Product fixes go to their owners; no production configuration changed.

Read AGENTS.md, full docs/DEPLOYMENT.md, PRD section 19, and shared live plan and
status in coordinator worktree 80e6. The latest user restriction supersedes
older generic sample language: only the first ten existing cloud specimens;
no expansion until the user reviews and approves end-to-end results. Locally
authored rasters are harness fixtures, never pilot records or quality evidence.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2. Specimens are processed one at a time, on demand, including new uploads,
> "instead of doing batch 10" (G2's words); in S2's reading, a new upload no
> longer waits on the user's end-to-end review of the ten. The ten pilot
> specimens remain the acceptance cohort, processed in order, and only they
> count toward it. The rest of the paragraph stands, including that locally
> authored rasters are harness fixtures, never pilot records or quality
> evidence.

Initial admin supplied privately to the coordinator; no email/UID committed.
Budget remains unavailable. Read-only metadata is allowed but the data owner
reports expired cloud reauthentication and no ADC; exact source ordering,
inventory and ready manifest are **Not confirmed**. Do not download or infer
on any cloud specimen until the data owner freezes the approved object set and
the coordinator supplies concrete execution authorization. No paid calls,
cloud mutation, hand deploy, main edits or interference with ports 3000/8000.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2, G9, G11 and G30. No manifest is frozen and there is no approved object set
> to freeze: each run is authorized on its own instead of per frozen manifest
> (PLAN section 4.1 stage 2), and the ten remain the acceptance cohort,
> processed in order. The concrete execution authorization is no longer an
> artifact: authorization artifacts retire (G11). Downloading an existing cloud
> specimen and running inference on it happen only inside PLAN section 8's
> per-specimen loop: S7's local run with real models (step 1) and production
> processing through the app (step 2); a new upload is processed on demand in
> production (G2). The budget is no longer unavailable; there are two bounds:
> G9's USD 25 ceiling, cumulative, infrastructure and models together, and
> within it G30's USD 5 production model allowance, which the pipeline enforces
> across every paid step and COST-BOUNDS tests (PLAN 4.3). G30's per-call
> reservations stand (PLAN 4.3; the coordinator's ruling on the mechanism). The
> rest of the paragraph stands, including that this harness makes no paid call,
> cloud mutation or hand deploy.

## Evidence states and verdict

- **Confirmed:** independently executed behavior, bound to candidate and mode.
- **Failed:** executed behavior contradicts the criterion, with a reproduction.
- **Not confirmed:** owner report or static inference awaiting independent proof.
- **Blocked:** named missing environment, authorization or policy prerequisite.
- **Not run:** not executed; never count as passing.

Report mode separately: fixture, real emulator, owner report, live cloud. A
SQLite or in-process restart is not SQL durability or worker process recovery;
injected identity is not Firebase verification; native compile is not a device
test; actual model invocation is not institutional quality approval.

Final verdict remains **not accepted**. The offline checker can only mark an
evidence packet ready for independent review. All 20 PRD criteria remain in the
mapping even where policy or representative quality approval is unavailable.
Ten pilot results do not establish an institutionally approved representative
gold set, `Verbatim D/T/S` semantics, Parties authority or automatic clearance.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1, G2, G9, G11 and G30. Automated clearance is in scope for this program: a
> record the harness resolves is cleared without a human (G1). In S2's reading,
> G11 retires the independent-review reports, not the checker's evidence: final
> acceptance still belongs to the evidence-based acceptance harness and the
> coordinator
> ([`PROTECTED_RELEASE_HARNESS.md`](PROTECTED_RELEASE_HARNESS.md#sequence-without-circular-readiness-prerequisites)
> step 8, and the coordinator's acceptance sign-off in [PLAN section
> 6](golive/PLAN.md#6-sessions-ownership-and-branches)), on the checker's
> evidence and through PLAN section 8's per-specimen loop, and DoD-6, the
> owner's own new record run end to end with no intervention, needs the owner's
> own confirmation ([PLAN section
> 1](golive/PLAN.md#1-goal-and-definition-of-done)). The rest of the paragraph
> stands, including that all 20 PRD criteria remain in the mapping even where
> policy or representative quality approval is unavailable, and that ten pilot
> results establish no institutionally approved representative gold set,
> `Verbatim D/T/S` semantics or Parties authority. Within G9's USD 25 ceiling,
> G30's USD 5 production model allowance is the bound the pipeline enforces
> across every paid step and COST-BOUNDS tests (PLAN 4.3). The rest of
> acceptance stands too, including every UI and live case the human-review
> checker (`scripts/qa/live/human_review.py`) requires: the ten UI cases of
> [`RELEASE_ACCEPTANCE.md`](RELEASE_ACCEPTANCE.md) (UI-SIGN-IN, UI-INTAKE,
> UI-PROCESSING, UI-IMAGE-REGIONS, UI-LITERAL-UNCERTAINTY, UI-SAVE-REOPEN,
> UI-SEARCH-QUEUE, UI-PROVENANCE-HISTORY, UI-DENIAL-RECOVERY and
> UI-NO-SYNTHETIC-FALLBACK) and the fifteen live cases of
> [`LIVE_QA.md`](LIVE_QA.md) (AUTH-IDENTITY, AUTH-APPCHECK, AUTH-MEMBERSHIP,
> AUTH-REVOKE, AUTH-CROSS-SCOPE, DATA-TEN, DATA-GENERATION, DATA-RESTORE,
> PROVIDER-ACTUAL, COST-BOUNDS, RETRY-UNKNOWN, WORKER-RESTART, API-RESTART,
> DEPLOY-IDENTITY and BROWSER-E2E), with UI-SIGN-IN's unverified and no-role
> denial, UI-DENIAL-RECOVERY's unauthenticated, cross-organization or
> cross-collection, viewer-write and revoked-access denials, in which stale
> responses cannot restore access, and UI-SAVE-REOPEN's stale concurrent save,
> and with the ten, in order and beside new uploads, in place of a frozen
> manifest (G2), G9's USD 25 ceiling in place of the cohort budget, and the
> release packet and the cohort ledger retired (G11). G30's per-call
> reservations stand (PLAN 4.3; the coordinator's ruling on the mechanism). In
> S2's reading of G11 and PLAN 4.6, DEPLOY-IDENTITY compares the deployed API
> and worker SHAs and image digests with the candidate's own runtime release
> run, and the SQL and rules revisions with the data release run that deployed
> them, which is the candidate's own or a main run at or before the candidate
> with those inputs unchanged between the two, in place of the packet; the rest
> of DEPLOY-IDENTITY stands.

## Contracts and ownership

Data owner supplies private `specimen-pilot/v1` with `status=ready`, exact ten
canonical specimen UUIDs in established source order, one authorized scope,
each original bucket/object/generation/SHA-256/size and application-source
binding. Selection includes the inventory digest and authorization reference.
Metadata-only manifests are rejected. Multiple original objects per specimen
are retained; no failed specimen leaves the denominator. Exact file SHA-256 is
supplied separately by coordinator. QA independently validates this shared
schema; it does not derive authorization from a self-declared manifest field.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2 and G11. No `specimen-pilot/v1` manifest is frozen, and no authorization
> reference or ready status authorizes use: each run is authorized on its own
> instead of per frozen manifest (PLAN section 4.1 stage 2), and authorization
> artifacts retire (G11). The selection's inventory digest and the rejection of
> metadata-only manifests retire with it. The checker reads the ten from their
> private record instead, `specimen-pilot-reference/v1` (the coordinator's
> ruling in its message to S2 of 2026-09-24, 01:15Z on 09-25): the ordinal, the
> specimen UUIDs in established source order, the one scope, and each original's
> bucket, object, generation, SHA-256 and size and its application-source
> binding. S7 writes it after PLAN section 8 step 2 imports the ten, and the
> coordinator verifies it against DoD-4's subject ids. Its SHA-256, supplied
> separately, still pins it on the checker's command line, and the checker reads
> it as it read the manifest: outside Git, no symlink, a regular file its reader
> owns with mode 600, at most 1 MiB, and exactly the pinned bytes. The checker's
> checks are re-anchored to it
> ([`golive/RELEASE.md`](golive/RELEASE.md#21-code-that-still-enforces-a-superseded-clause)
> section 2.1, whose `manifest_ids` row lists what retires). The rest of the
> paragraph stands, including that multiple original objects per specimen are
> retained, that no failed specimen leaves the denominator, and that QA derives
> no authorization from a self-declared field.

Integration supplies full immutable combined commit, owner PRs, image digests,
connector/rules revisions, clean-tree status, supported start/stop commands,
disposable state paths and explicitly assigned ports. Runtime contract from
API owner is `/health/live`, `/health/ready`, `/version`, PORT binding and
revoked-token/App Check/app-ID validation. No port claimed by this harness.
Worker owner supplies approved pinned routes, independent raw output contract,
cost reservation and unknown-effect/restart injection points. Delivery supplies
reviewed migration/runtime workflows, rollback and exact deployment identities.

Actual authenticated browser verification starts only against the supplied
target, through supported UI and APIs. Capture authorized user scope privately,
record sanitized response status and provenance, verify server changes survive
refresh, and inspect network path plus session mode. No direct DB repair is
allowed in the end-to-end acceptance flow. Destructive denial/failure tests use
disposable authorized fixtures/resources and require coordinator authorization.

## Threat and operational acceptance matrix

Every row is **Not run live**. Evidence must include positive controls, observed
negative behavior, timestamps, sanitized request/response, candidate/manifest
digests, IDs privately, and before/after retained-state counts when applicable.

| ID | Required independent test and expected result | Owner / live gate |
|---|---|---|
| AUTH-IDENTITY | Verified assigned user succeeds. Missing/malformed/expired/wrong-project/revoked/disabled/unverified identity fails without metadata disclosure. Record verified-email policy explicitly. | API + client / real Firebase |
| AUTH-APPCHECK | Valid allowed app succeeds; missing/invalid/expired/wrong-project/disallowed-app tokens fail. Browser attestation and server check must agree. | API + client / real attestation configuration |
| AUTH-MEMBERSHIP | Assigned collection visible. No membership shows no records; viewer cannot mutate, operator cannot review/approve, unapproved role cannot gain access. | Data + API / private admin bootstrap |
| AUTH-REVOKE | Remove collection grant and revoke identity separately; next session, workspace, original, crop, audit and mutation requests deny with retained data unchanged. Restore test grant through supported admin route. | Data + API / authorized disposable identity |
| AUTH-CROSS-SCOPE | Substitute org/collection/specimen/asset/run IDs and cursor across scopes; server denies. Sensitive views redact consistently. Direct Storage/SQL paths also deny. | Data + API / two authorized test scopes |
| DATA-TEN | Independently reconcile frozen inventory/order and all ten specimen/object bindings; eleventh, duplicate, reordered, unknown or changed-generation source cannot enter launch work. Failed records stay counted. | Data + worker / ready manifest |
| DATA-GENERATION | Fetch only approved pinned source generations, independently hash bytes and compare metadata/application binding. Attempt mismatched completion and overwrite through supported disposable control; originals stay immutable. | Data / approved object access |
| DATA-RESTORE | Capture snapshot counts/checksums, restore into isolated destination, reconstruct originals/history/membership and compare independently. Prove backup exists before valuable new writes. | Data + delivery / reviewed restore target |
| PROVIDER-ACTUAL | All ten retain real SAM 3 revision/regions, two independent model raw responses per required label, input/output hashes, route/model/provider/prompt versions, usage and completion states. No synthetic fallback or peer-output contamination. | Worker / paid-call and data-processing approval |
| COST-BOUNDS | Validate positive bounded reservation, failed-closed missing budget, call/token/time/retry/concurrency limits and emergency stop; unknown outcomes keep reservation. Reconcile receipts against actual billing visibility. | Worker + delivery / concrete approved budget |
| RETRY-UNKNOWN | Inject 429/timeouts and kill after intent/response/checkpoint. Known safe retries are bounded; ambiguous external effect blocks reconciliation, never silent replay or duplicate accepted result. | Worker / authorized failure controls |
| WORKER-RESTART | Restart actual worker process/container with same data; observe fencing, lease expiry, duplicate delivery, persisted state and one accepted effect. Old worker cannot overwrite newer state. | Worker + data / durable runtime |
| API-RESTART | Save supported correction, revalidation and history, restart API revision, reopen exact persisted state and verify originals/raw observations remain unchanged. | API + data / actual runtime restart |
| DEPLOY-IDENTITY | All five exact-head PR checks, green main workflow/deploy job, public Hosting marker and application smoke; API/worker SHA+image digest, SQL/rules revisions match release packet. Wrong/stale marker fails. | Delivery / later authorized merge |
| BROWSER-E2E | Real sign-in/App Check, assigned collection, authorized intake/processing, evidence view, correction/history, refresh and recovery across the full frozen ten. Keyboard/accessibility and error states; no hidden repair. | Client + QA / integrated target |

> 2026-09-23: The DATA-TEN, COST-BOUNDS, DEPLOY-IDENTITY and BROWSER-E2E rows are superseded in part for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2, G9, G11 and G30. The matrix's evidence binds the candidate and the ten,
> not a frozen manifest's digest (G2). DATA-TEN reconciles the ten, in order, as
> the acceptance cohort, with no frozen inventory; an eleventh or a
> changed-generation source still cannot enter it, but a new upload may now
> enter on-demand processing outside it (G2). DATA-TEN's live gate is the ten's
> private record, `specimen-pilot-reference/v1`, not a ready manifest (the
> coordinator's ruling in its message to S2 of 2026-09-24, 01:15Z on 09-25).
> COST-BOUNDS' concrete approved budget is G30's USD 5 production model
> allowance, which the pipeline enforces across every paid step, within G9's
> USD 25 ceiling, cumulative, infrastructure and models together (PLAN 4.3); the
> acceptance lab's USD 5 share is separate. G30's per-call reservations stand
> (PLAN 4.3; the coordinator's ruling on the mechanism). COST-BOUNDS tests them:
> each paid call reserves its worst-case cost before it starts, an unknown
> outcome stays reserved in full, the spend is cumulative and never reset, and
> once the allowance is spent paid steps block as `program_allowance_exhausted`
> (QUE-005). In S2's reading of G11 and PLAN 4.6, DEPLOY-IDENTITY compares the
> deployed API and worker SHAs and image digests with the candidate's own
> runtime release run, and the SQL and rules revisions with the data release run
> that deployed them, which is the candidate's own or a main run at or before
> the candidate with those inputs unchanged between the two, in place of the
> packet; the rest of DEPLOY-IDENTITY stands. BROWSER-E2E's full frozen ten is
> the ten pilot specimens processed one at a time, in order, beside new uploads
> (G2). The rest of each row stands.

## All 20 PRD section 19 criteria retained

All rows are **Not run on the combined live candidate**. Local evidence below
supports only its stated scope. Earlier QA.md remains historical procedure,
not proof of the current rollout or institutional acceptance.

| Case | Observable procedure and expected result | Linked cases / remaining limit |
|---|---|---|
| PRD-01 | Upload valid authorized image; interrupt transfer, reopen and resume from retained server offset; replay completion keeps one specimen/job. | DATA-TEN, BROWSER-E2E; native camera/device separate |
| PRD-02 | Independently hash approved original generation, reject overwrite/hash substitution and retain provenance. | DATA-GENERATION |
| PRD-03 | Inspect ranked classification provenance; correct collection/profile; new pinned run supersedes dependent outputs while old history remains. Reject unauthorized target/stale revision. | AUTH-CROSS-SCOPE, BROWSER-E2E |
| PRD-04 | Actual pinned SAM 3 gives reproducible regions at documented tolerance. Add/delete/resize/rotate/merge/reorder and verify original-space transforms/crop hashes, including missed labels. | PROVIDER-ACTUAL; synthetic regions never qualify |
| PRD-05 | At least two required independent initial route calls per label, no peer context, complete immutable raw provenance. Pause after first and resume safely. | PROVIDER-ACTUAL, RETRY-UNKNOWN |
| PRD-06 | Known disagreement remains visible alongside source and original readings before/after adjudication. Minority reading persists. | BROWSER-E2E |
| PRD-07 | Trace literal, structured and normalized values separately; correction preserves literal evidence and derivation links. | API-RESTART |
| PRD-08 | Actual adapter fault controls exercise success/no-match/ambiguity/429/timeout/auth failure/malformed responses with typed states, Retry-After and retained evidence. | RETRY-UNKNOWN; controlled faults labeled separately |
| PRD-09 | Bounded temporary failure resumes checkpoint without duplicate observations/effects/records; crash at ambiguity blocks reconciliation. | RETRY-UNKNOWN, WORKER-RESTART |
| PRD-10 | Remove each critical gate independently; direct clear/approve request cannot bypass coverage/evidence/approval/semantics. | AUTH-MEMBERSHIP; institution policy unresolved |
| PRD-11 | Every mandatory Insects field varied null/empty/unreadable/unknown/unsupported; cannot clear, explicit reason retained. | DATA-TEN; exact institutional semantics unresolved |
| PRD-12 | Demand completion despite absent pixels/evidence; preserve explicit abstention, no placeholder or coerced value. | PROVIDER-ACTUAL; quality review required |
| PRD-13 | Provider 429/broken route/credential failure stays operationally blocked/retryable, never Deferred. | COST-BOUNDS, RETRY-UNKNOWN |
| PRD-14 | Capability exhaustion enters Deferred only with supported attempts, reason and retry eligibility; operational error cannot masquerade as limitation. | PROVIDER-ACTUAL |
| PRD-15 | Reviewer correction updates dependent validation/disposition; replay/stale conflict and unauthorized write controls pass. | AUTH-MEMBERSHIP, API-RESTART |
| PRD-16 | Each final field resolves to original pixels, crop transform, raw observation, lookup and policy/human decision; missing/tampered evidence fails closed. | DATA-GENERATION, PROVIDER-ACTUAL |
| PRD-17 | Reopen supported final queue states solely from stored versions/audit after runtime restart and isolated restore; no hidden memory state. | API-RESTART, WORKER-RESTART, DATA-RESTORE |
| PRD-18 | Unauthorized/revoked/cross-scope access to original/crop/record/audit/credential evidence denied through API and direct data endpoints. | All AUTH cases |
| PRD-19 | Keyboard/focus/screen-reader/error recovery/security/quality criteria pass with explicit approved thresholds. Web launch target; Android/iOS build evidence separate from device/signing. | BROWSER-E2E; quality/semantics approval not supplied |
| PRD-20 | Production-like full ten completes via UI/API with real runtime/data/providers; retain outcomes including review/blocked cases, no DB edits or hidden repair. | All live cases; launch pending |

> 2026-09-23: The PRD-03 and PRD-10 rows are superseded in part for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1 and G14. PRD-03: there is no classification stage to rank, since the
> profile comes from the collection a specimen was uploaded or imported into,
> resolved down the collection tree (G14). The rest of that row stands,
> including that a reviewer can correct the collection/profile through the
> existing classification endpoint, that a new pinned run supersedes dependent
> outputs while old history remains, and that an unauthorized target or a stale
> revision is rejected. PRD-10: PLAN section 4.1 stage 8 removes the approval
> and semantics gates for runs whose profile names `harness_route` (the
> coordinator's reading of G1, #158), so those runs have no such gate to bypass.
> The rest of that row stands, including removing each remaining critical gate
> independently, and that no direct clear or approve request bypasses coverage
> or evidence.

## Executed evidence and commands

| Command / inspection | Outcome | Evidence / limit |
|---|---|---|
| `git rev-parse HEAD` | Confirmed exact a53f855 baseline | Product source unchanged |
| `uv sync --frozen` | Exit 0 | Locked local environment; Python 3.11.16 (CI uses 3.12) |
| `uv run pytest -q scripts/qa/live` | Exit 0, 57 passed after the third-runtime provenance update | Authored adversarial gate and probe failure/provenance tests; no live claim |
| `uv run python scripts/qa/live/local_probe.py --output docs/execution/qa-evidence/live-rollout/baseline-local.json` | Exit 0, 24 checks passed | ASGI/SQLite/injected membership only; initial failed timing assertion preserved in experiments.md |
| Production `cli.py` identity inspection | Not confirmed live: no `email_verified` requirement in baseline | Repro: inspect verify closure after SDK success; returns claims uid regardless of verification field. API owner notified. No product patch by QA. |
| `scripts/ci/verify.sh` | Exit 0 after all independent harness fixes | Repository/scanners, locked Python, Flutter analysis/tests/release web build passed; no deployment |

Confirmed local checks include interrupted/resumed/replayed upload; settled
correction and original readings survive app recreation; immutable source hash;
decision replay/conflict; history; missing bearer; viewer write and cross-org
denial; next-request revoked membership denies workspace/source/history; CORS
does not allow unknown origin. No real Firebase token or App Check exercised.

## Launch blockers and next owner actions

| Gate | State / next owner |
|---|---|
| Ready exact-ten manifest and verified first-ten source order | Blocked: data owner needs cloud reauthentication/inventory, generation+SHA-256 and import binding |
| Cloud spending, model data policy, provider routing and shutdown bounds | Blocked: coordinator/user concrete budget and approved execution packet |
| Real auth/App Check/membership and runtime wiring | Not confirmed: API/client/data PRs plus configured authorized environment |
| Durable SQL/Storage integrity and isolated backup restore | Not confirmed: data/delivery evidence; local fixture cannot substitute |
| Actual SAM 3 and independent provider outputs | Not run: worker integration and approved resources/calls |
| SQL Connect 3.2.0 restart removes four supplemental indexes | Blocked: coordinator/data report; verify data repair DDL after repeated startup and writer fencing during the whole schema/index window |
| Combined candidate, deploy target and restart controls | Not supplied: delivery freezes candidate after scoped PRs; no self-merge |
| Institutional clearance, field semantics, representative quality approval | Not supplied: retain explicit blockers; never infer institutional sign-off |

> 2026-09-23: The "Ready exact-ten manifest...", "Cloud spending..." and "Institutional clearance..." rows are superseded in part for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1, G2, G9, G11 and G30. No manifest is frozen: each run is authorized on its
> own instead of per frozen manifest (PLAN section 4.1 stage 2), and the ten are
> the acceptance cohort, processed in order (G2), so the first row no longer
> waits on a ready manifest; the verified first-ten source order and each
> original's generation, SHA-256 and import binding still apply (DATA-TEN,
> DATA-GENERATION). Cloud spending has two bounds: G9's USD 25 ceiling,
> cumulative, infrastructure and models together, and within it G30's USD 5
> production model allowance, which the pipeline enforces across every paid step
> and COST-BOUNDS tests (PLAN 4.3), and the release envelope and its execution
> packet retire (G11), so the second row's blocker is answered rather than
> pending; model data policy, provider routing and shutdown bounds stand. G30's
> per-call reservations stand (PLAN 4.3; the coordinator's ruling on the
> mechanism). A record the harness resolves is cleared without a human (G1), and
> PLAN section 4.1 stage 8 removes the lane's institutional-approval, semantics
> and human-approval gates for runs whose profile names `harness_route`, so
> clearance no longer waits on institutional clearance there. The rest of the
> third row stands: field semantics and representative quality approval are not
> supplied, and nothing infers institutional sign-off.

Next QA action: finish canonical local gate, submit scoped PR and watch all five
checks. Then independently reproduce the frozen combined candidate and browser
flow when coordinator supplies prerequisites. Re-run evidence on the final
merged SHA; owner PR or generic HTTP 200 never completes release acceptance.

## Evidence-only pilot scope under review

Coordinator authorized worker implementation of a narrowly scoped intermediate
milestone: exact ten manifest, positive spending reservation and pinned source,
model, prompt and configuration; real SAM 3 plus two blind readings; draft and
risk-blocked profile stays draft; terminal `processing_blocked` with
`pilot_evidence_review_required` and disposition null. No parsing, authority
lookup, finalization or clearance. Normal production policy remains unchanged.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1, G2 and G30. The pipeline of PLAN section 1 is now the scope: parsing,
> authority lookup, finalization and clearance run, and a record the harness
> resolves is cleared without a human (G1), in place of this narrowly scoped
> milestone's terminal `processing_blocked` with
> `pilot_evidence_review_required` and a null disposition. Production policy
> follows PLAN section 4.1 stage 8, which removes the gates that contradict G1
> for runs whose profile names `harness_route`. No exact-ten manifest is frozen:
> each run is authorized on its own instead of per frozen manifest (PLAN section
> 4.1 stage 2) (G2). The rest of the milestone stands, including the positive
> spending reservation, now G30's per-call reservation against its USD 5
> production model allowance within G9's USD 25 ceiling (PLAN 4.3), the pinned
> source, model, prompt and configuration, and real SAM 3 plus two blind
> readings. G30's per-call reservations stand (PLAN 4.3; the coordinator's
> ruling on the mechanism).

QA will independently attempt outside-ten and changed-binding entry, absent
approval/budget, budget reset through run/profile/config changes, repeated
delivery and stop/restart, and all approve/finalize routes. Evidence correction
and history must not turn into risk approval or resume an unapproved normal
pipeline. This milestone cannot satisfy PRD-07/08/10/11/14/15/17/19/20 as a full
production pipeline; omitted stages and institutional quality remain blocked.
Request sent to worker for a frozen candidate and failure-injection commands.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1 and G30. The normal pipeline is the scope now (G1): its stages run, and the
> approve and finalize routes behave as PLAN section 4.1 specifies instead of
> staying blocked. The rest of the paragraph stands, including the outside-ten
> and changed-binding entry attempts, an absent budget failing closed, a budget
> reset through run, profile or configuration changes, repeated delivery and
> stop/restart, and that evidence correction and history never turn into risk
> approval. G30's per-call reservations stand (PLAN 4.3; the coordinator's
> ruling on the mechanism).

The data index repair requires a separate frozen candidate: compare exact
index definitions before startup, after schema restart, after DDL, and after
repeated restart/reapplication. Static inspection confirms the four indexes in
`dataconnect/sql/paging-indexes.sql` and `search-indexes.sql` are nonunique query
indexes; their absence alone does not establish uniqueness or data-loss risk.
Independently verify the schema-managed `specimen_scope_checksum` unique
constraint survives every phase, exact query results remain correct and the
reviewed API/worker/inflight-transaction quiescence ordering is effective. The
reported 27-table/16,251-row dump/restore is owner evidence only and cannot
replace this launch gate.

Additional API target: verify the actual Firebase Admin 7.5 App Check JWT
audience contract using signed-token validation with distinct numeric project
number and textual Auth project ID. Mocked SDK success is insufficient; review
the owner's pinned `SPECIMEN_FIREBASE_PROJECT_NUMBER` and application-ID
allowlist tests. Real production-token acceptance remains Not run.

Independent QA-tool review found and repaired three harness issues: preserve
failed probe evidence instead of deleting it, reject malformed/extra manifest
fields consistently with data owner's strict schema, and reject dirty or
changing product source so old commit identities cannot label changed code.
Regression tests and a fresh 24-check fixture probe pass. The original baseline
artifact remains historical and is not relabeled as the hardened harness run.

## Frozen owner review findings

Client PR 5 at `5ec7b6e17046d8b2bc6a1a9941c2786b840ba489`: independent
static source/test review found P2 authorization propagation gaps. Preview
fetch converts credential errors or HTTP 401/403 into a local preview error;
raw evidence, history and large-record children catch denials locally, and
intake can continue after denial. These paths bypass parent access clearing
and leave retained record/actions visible. No backend authorization bypass
was demonstrated. Sent exact files/lines and record-success-then-revocation
reproduction to client and coordinator. Fixed candidate needs independent
HTTP/widget recheck; old head is not accepted. UID binding, email refresh,
App Check requirement and server-action pilot controls had no other concrete
static finding. No Flutter/browser/live Firebase tests executed by this review.

Delivery PR 6 at `a26c0cc3f5786c74440bfe280eee505ede76f036`: 68 bounded
tests independently passed from an exact git-archive snapshot. No Hosting
identity/permission/deploy-guard regression found. Two P2 readiness gaps:
runtime CI validates an incomplete example with exit 0 even on main/integration;
packet validation compares internal source fields without a trusted expected
candidate SHA, permitting a self-consistent stale packet. API embedded source
is compared with an exact-commit build context; worker embedded provenance was
pending. No unauthorized deploy path was found: output explicitly denies
deployment authorization/live verification. Sent findings to delivery and
coordinator. No actual container build, cloud call or deployment executed by QA.

## Third-runtime evidence contract

The combined implementation now requires a separate SAM runtime. Offline
preflight therefore requires its image digest, matching source commit, pinned
model revision, checkpoint aggregate and serving-configuration digest alongside
API and worker identities. All three images require immutable SHA-256 digest
syntax. Twelve regression cases keep preflight incomplete for absent, stale or
unpinned runtime evidence. This change does not grant approval or establish real
SAM serving; complete live case evidence and independent review are still
required. Subsequent exact owner-review closures and CI results are retained in
the PR body so historical candidate observations are not silently relabeled.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2, G9, G11 and G30. In S2's reading, G11 retires the independent-review
> reports, not the evidence: complete live case evidence is still required, and
> final acceptance still belongs to the evidence-based acceptance harness and
> the coordinator
> ([`PROTECTED_RELEASE_HARNESS.md`](PROTECTED_RELEASE_HARNESS.md#sequence-without-circular-readiness-prerequisites)
> step 8, and the coordinator's acceptance sign-off in [PLAN section
> 6](golive/PLAN.md#6-sessions-ownership-and-branches)), on the checker's
> evidence and through PLAN section 8's per-specimen loop, and DoD-6, the
> owner's own new record run end to end with no intervention, needs the owner's
> own confirmation ([PLAN section
> 1](golive/PLAN.md#1-goal-and-definition-of-done)). SAM 3 stays bound to the
> candidate: its source commit is the candidate itself or, once T2 reuses an
> unchanged SAM 3 image, a commit on main at or before the candidate with SAM
> 3's inputs unchanged between the two (T2's reuse rule), and in both cases the
> candidate's own release run deployed the image built from that commit;
> [`golive/RELEASE.md`](golive/RELEASE.md#21-code-that-still-enforces-a-superseded-clause)
> section 2.1 lists the checker's line (`acceptance.py` 497). The rest of the
> paragraph stands, including that this change alone grants no approval and
> establishes no real SAM serving. Within G9's USD 25 ceiling, G30's USD 5
> production model allowance is the bound the pipeline enforces across every
> paid step and COST-BOUNDS tests (PLAN 4.3). The rest of acceptance stands too,
> including every UI and live case the human-review checker
> (`scripts/qa/live/human_review.py`) requires: the ten UI cases of
> [`RELEASE_ACCEPTANCE.md`](RELEASE_ACCEPTANCE.md) (UI-SIGN-IN, UI-INTAKE,
> UI-PROCESSING, UI-IMAGE-REGIONS, UI-LITERAL-UNCERTAINTY, UI-SAVE-REOPEN,
> UI-SEARCH-QUEUE, UI-PROVENANCE-HISTORY, UI-DENIAL-RECOVERY and
> UI-NO-SYNTHETIC-FALLBACK) and the fifteen live cases of
> [`LIVE_QA.md`](LIVE_QA.md) (AUTH-IDENTITY, AUTH-APPCHECK, AUTH-MEMBERSHIP,
> AUTH-REVOKE, AUTH-CROSS-SCOPE, DATA-TEN, DATA-GENERATION, DATA-RESTORE,
> PROVIDER-ACTUAL, COST-BOUNDS, RETRY-UNKNOWN, WORKER-RESTART, API-RESTART,
> DEPLOY-IDENTITY and BROWSER-E2E), with UI-SIGN-IN's unverified and no-role
> denial, UI-DENIAL-RECOVERY's unauthenticated, cross-organization or
> cross-collection, viewer-write and revoked-access denials, in which stale
> responses cannot restore access, and UI-SAVE-REOPEN's stale concurrent save,
> and with the ten, in order and beside new uploads, in place of a frozen
> manifest (G2), G9's USD 25 ceiling in place of the cohort budget, and the
> release packet and the cohort ledger retired (G11). G30's per-call
> reservations stand (PLAN 4.3; the coordinator's ruling on the mechanism). In
> S2's reading of G11 and PLAN 4.6, DEPLOY-IDENTITY compares the deployed API
> and worker SHAs and image digests with the candidate's own runtime release
> run, and the SQL and rules revisions with the data release run that deployed
> them, which is the candidate's own or a main run at or before the candidate
> with those inputs unchanged between the two, in place of the packet; the rest
> of DEPLOY-IDENTITY stands.

## Recovery and rollback

Harness creates only new evidence files and temporary local test data; remove
only its own disposable directory if interrupted. Preserve failed evidence.
Fix product defects in owner branches through reviewed PRs. If combined live
checks fail, stop further rollout, retain failed source/runtime/schema identities
and report the exact gate. Delivery owns reviewed runtime/data rollback and
restore. Hosting rollback/deployment follows DEPLOYMENT.md exclusively; this
QA task never runs a deployment or repairs production state directly.
