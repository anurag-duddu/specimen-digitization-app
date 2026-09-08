# Independent live rollout QA

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

Initial admin supplied privately to the coordinator; no email/UID committed.
Budget remains unavailable. Read-only metadata is allowed but the data owner
reports expired cloud reauthentication and no ADC; exact source ordering,
inventory and ready manifest are **Not confirmed**. Do not download or infer
on any cloud specimen until the data owner freezes the approved object set and
the coordinator supplies concrete execution authorization. No paid calls,
cloud mutation, hand deploy, main edits or interference with ports 3000/8000.

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

## Contracts and ownership

Data owner supplies private `specimen-pilot/v1` with `status=ready`, exact ten
canonical specimen UUIDs in established source order, one authorized scope,
each original bucket/object/generation/SHA-256/size and application-source
binding. Selection includes the inventory digest and authorization reference.
Metadata-only manifests are rejected. Multiple original objects per specimen
are retained; no failed specimen leaves the denominator. Exact file SHA-256 is
supplied separately by coordinator. QA independently validates this shared
schema; it does not derive authorization from a self-declared manifest field.

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

QA will independently attempt outside-ten and changed-binding entry, absent
approval/budget, budget reset through run/profile/config changes, repeated
delivery and stop/restart, and all approve/finalize routes. Evidence correction
and history must not turn into risk approval or resume an unapproved normal
pipeline. This milestone cannot satisfy PRD-07/08/10/11/14/15/17/19/20 as a full
production pipeline; omitted stages and institutional quality remain blocked.
Request sent to worker for a frozen candidate and failure-injection commands.

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

## Recovery and rollback

Harness creates only new evidence files and temporary local test data; remove
only its own disposable directory if interrupted. Preserve failed evidence.
Fix product defects in owner branches through reviewed PRs. If combined live
checks fail, stop further rollout, retain failed source/runtime/schema identities
and report the exact gate. Delivery owns reviewed runtime/data rollback and
restore. Hosting rollback/deployment follows DEPLOYMENT.md exclusively; this
QA task never runs a deployment or repairs production state directly.
