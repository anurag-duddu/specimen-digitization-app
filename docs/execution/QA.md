# Independent acceptance procedure and evidence

Status: first-wave local assessment executed; P0 not accepted. See latest ledger below.
Date: 2026-09-07 America/Chicago.
Owner: independent QA task, coordinator `01a07f44-7d89-7052-b968-5e96753493ad`.
Worktree: `/Users/anuragduddu/.codex/worktrees/14dd/specimen-digitization-app`.
Branch: `codex/independent-acceptance-review`.
Inspected product baseline: `82fd60eff90684d2c630a37c59e1250604ad1cae`.
Integration task: `01a07f48-a57c-71b0-9642-c9430886049c`.

## Authority and limits

Read repository AGENTS.md, full DEPLOYMENT.md, full PRD v0.6 and architect
CONTRACTS.md v0.1 in worktree `969e`. Read the shared coordination PLAN.md before
planning and again before defining the acceptance procedure. The contract is a
specification, not implemented endpoint evidence. This report owns QA only;
implementation defects go through the coordinator to their owners.

No cloud mutation, deployment, production merge, paid inference or restricted
museum data is authorized. A reported existing Cloud SQL instance is not proof
of a deployed connector or functioning application transport. Connector deployment
remains unauthorized. No substitute SAM 3 fixture earns model acceptance.

Use these result states independently for each environment and criterion:

- **Passed:** the stated observable behavior was independently reproduced on the
  recorded commit and transport; includes evidence and limits.
- **Failed:** an executed check contradicted its expected result, or static
  inspection establishes a missing required implementation; cite reproduction.
- **Not tested:** executable proof has not been attempted or completed.
- **Externally blocked:** a named authorization, approved resource, dataset,
  institutional decision or device is required. A local missing implementation
  is a product gap, not an external blocker.

Never collapse unit, local synthetic HTTP, Firebase emulator, deployed SQL
Connect, live provider and representative museum acceptance into one result.
An emulator can establish local authorization behavior, not production IAM.
SQLite persistence can establish local restart behavior, not SQL Connect
transactions, grants, constraints or durability. A build is not a device test.

## Integration handoff required to execute

Integration must provide an immutable full SHA, clean status, merged contract
version, canonical verification result, supported mode/transport matrix, exact
API/worker/Flutter/emulator commands, ports, disposable local data paths,
synthetic fixture provenance, and supported failure-injection controls. It must
identify any fixture-only endpoint and every unimplemented capability.

Preserve this QA commit before incorporating the reviewed candidate in this
worktree. Verify the commit exists with `git show --no-patch FULL_SHA`; inspect
its diff and ancestry; merge the agreed candidate into this QA branch only
when clean and safe. Do not read uncommitted implementation files as the tested
candidate. Record candidate SHA separately from the QA documentation commit.

Run from this worktree, capturing exit code and sanitized output:

```bash
git status --short --branch
git rev-parse HEAD
scripts/ci/verify.sh
```

Run integration's documented local startup commands only after verifying they
use disposable local storage, explicit synthetic/emulator mode and no provider
credentials. Obtain test identities through the supported local auth setup;
never invent a production token or place bearer tokens in evidence. Open Flutter
against the actual local API. Check the browser network path/session mode and
that changing the server record is reflected by refresh. A demo repository
injected into a widget does not prove HTTP wiring.

## Frozen synthetic cohort and evidence protocol

Create a manifest before execution with case ID, fixture provenance/license,
SHA-256, byte length, real decoded dimensions and MIME, expected outcomes and
approved mode. Use authored synthetic labels and controlled local responses;
never use museum images or copy real Parties identities. Label synthetic
authority IDs and policy approvals explicitly. A test-only approved profile
may exercise a positive clearance control but cannot approve the Insects policy.
Keep failed and excluded cases in the denominator with reasons.

Cases: valid one-label PNG/JPEG; two labels with a deliberately missed region;
rotated label; competing numeral/date readings; unreadable and absent mandatory
values; all-supported test-only profile; exhausted capability limitation;
429/timeout/authentication failure; and malicious/corrupted uploads. For every
mandatory key vary null, empty/whitespace, placeholder, unknown, unreadable,
not-present, not-applicable, ambiguous and unsupported asserted value. Include
partial dates, elevation bounds and a catalogue IRN incorrectly offered as an
eparties identifier. Never infer missing field semantics to complete a case.

For each executed case retain: tested SHA; UTC start/end; command and exit;
mode and actual backend/storage transport; fixture digest; synthetic actor role
and scope; request method/path and redacted payload; response status/body;
specimen/run/asset/decision IDs; persisted counts and digests before/after;
expected/actual result; screenshots or accessible-state observations; result
state; defect ID. Retain raw evidence under a unique QA output directory and
commit only reviewed sanitized summaries or small synthetic evidence artifacts.
Do not store secrets, signed URLs or private content in Git.

## All 20 section 19 acceptance criteria

All rows below are **Not tested on an integrated candidate**. Each procedure has
a positive control and a negative/failure observation; all applicable rows must
also run on the approved representative dataset before P0 acceptance.

| P0 | Procedure and expected observable result | Evidence and limits |
|---|---|---|
| 01 Capture/upload and interruption | Upload valid files through Flutter. Interrupt binary transfer, close/reopen client, resume from server progress. Retry create/complete with same key; change payload under same key. Expect stable IDs, one accepted manifest entry/job, 409 for changed payload. Exercise camera on Android/iOS devices separately. | Manifest, actual byte digest, progress, job counts, browser/device record. A picker mock or retrying a whole POST is not proof of resumable binary transfer. |
| 02 Immutable original | Fetch authorized original and independently hash bytes; compare declared and verified metadata. Try overwrite/delete, mismatched hash/generation, derivative overwrite and cross-scope asset substitution through supported interfaces. Original remains identical; invalid completion cannot enqueue. | Storage rule/API results and immutable generation/digests before/after. Read the actual stored object, not echoed metadata. |
| 03 Classification/profile | Observe ranked candidates and provenance; correct to a different configured collection/profile. Verify new pinned run, successor links and supersession of dependent outputs; old history still opens. Submit stale correction and an unauthorized target collection. | Both workspace versions, profile digests, conflict/authorization responses, unchanged unaffected evidence. A selected label in UI alone is insufficient. |
| 04 SAM 3/region correction | With authorized serving available, submit fixed source/settings/revision; reproduce geometries and crop transforms within an explicitly recorded tolerance. Add/delete/reorder/resize/rotate/merge regions through review; verify coordinates in original raster space and retained old crops. Exercise zero/missed/overlapping/out-of-bounds regions. | Real SAM 3 call and model revision, mask/crop hashes, overlay screenshots and invalidation. Synthetic region fixtures test contracts only; actual SAM 3 currently externally blocked. |
| 05 Independent observations | For every required label inspect initial model requests and stored raw envelopes. Confirm two distinct configured routes, no peer output in either initial context, pinned versions, input digests and usage/errors. Interrupt after first observation and resume. | Provider-boundary request captures in synthetic mode plus immutable raw bytes. Route-name assertions alone do not prove independence or live model capability. |
| 06 Disagreement/adjudication | Use a known numeral/date disagreement and unreadable span. Inspect side-by-side alternatives before and after adjudication; retain minority reading and source-span links. Attempt adjudication before all required observations persist. | UI/accessibility observations, raw hashes unchanged, adjudication ordering and unresolved reasons. Consensus-only display fails. |
| 07 Separate layers | Follow a historical spelling and literal elevation/date through parse and normalization. Correct resolved value; literal text and original observation stay unchanged. | Distinct record IDs, derivation/evidence links and before/after payloads. Equal copied strings in unrelated columns are insufficient lineage. |
| 08 Typed lookup outcomes | Drive a controlled local HTTP authority through success, no-match, ambiguity, empty, 429 with Retry-After, timeout, 401, 403, malformed response and provider error. Verify typed outcomes, complete query/version/digest evidence, bounded attempts, no invented candidate. | Actual adapter HTTP captures, retry timestamps and stored lookup rows. A constructed result enum alone is insufficient. Live authority behavior remains separate. |
| 09 Checkpoint/retry | Kill worker after dispatch intent, after external response but before checkpoint, and after checkpoint before acknowledgment. Restart new process against same persistence. Deliver duplicate jobs; expire lease and race stale/new worker. | Before/after counts of observations/results/outbox, checkpoint/fencing revisions. Unknown external effect must be recorded/reconciled, not falsely called exactly-once. Repeat against actual SQL transport when authorized. |
| 10 Critical gates | Starting from a synthetic positive control, remove one critical gate at a time: coverage, independent passes, adjudication, evidence, schema, hard finding, approval, semantics. Set highest agreement/completeness score and request clearance directly. | Policy findings and API refusal/no-cleared snapshot; each mutation independently named. Test all gates, not only one boolean. |
| 11 Mandatory fields | Parameterize all 20 Insects keys over empty and unresolved states. Complete configured attempts; expect explicit field reason and review, or operational block when the attempt could not execute. | Full case count and field-to-reason map. No unknown/not-applicable/zero-as-placeholder or coerced value satisfies a mandatory field. |
| 12 Abstention under pressure | Submit instructions demanding every field be filled despite missing evidence; supply plausible unsupported Parties/catalogue ID, search snippet, unknown D/T/S semantics and inferred missing units/dates. | Persisted abstention, untouched literal layer and denied clearance. Test fixture text and caller assertions must not authorize policy or create evidence. |
| 13 Operational != Deferred | Inject 429, credentials failure, timeout, outage, malformed response, code error and exhausted temporary budget; exhaust retry limit and invoke replay. | Null final disposition while blocked, actionable reason/next action, bounded retry/dead-letter/replay timeline. An error string with a final Deferred value fails. |
| 14 Legitimate Deferred | Exhaust all approved viable alternatives for a synthetic unsupported capability; include attempts, capability reason and future retry predicate. Try premature deferral and one available unattempted approved fallback. | Versioned decision and attempts; negatives cannot defer. Test capability outcome is not evidence of actual model limitations. |
| 15 Review/revalidation | Two independent reviewer sessions load same revision. Save a reasoned correction in A; observe dependent revalidation and updated disposition. Save stale B, retry A with same key, then alter A payload under same key. | One decision/audit/version effect, 409 conflicts, actor from verified identity, refreshed UI. Old observations survive; unaffected stages do not rerun. |
| 16 Field traceability | For every selected field traverse source asset/region/span, independent or human observation, candidate parents, transformations, lookup capture and policy decision. Remove/substitute/cross-scope one reference and rerun finalization. | Independently fetched bytes/digests and graph traversal result. Nonempty evidence IDs or self-reported provenance-complete flag are insufficient. |
| 17 Persistent reconstruction | Produce all three outcomes using synthetic-approved controls. Stop API/workers/browser; start fresh processes and a fresh client using only documented persistence. Reopen historical versions and reconstruct fields/timeline/crops. | Before/after semantic snapshots and byte hashes. No reseeding or manual DB repair. SQLite and SQL Connect get separate results. |
| 18 Authorization/isolation | Run the threat matrix below against API, direct object transport and actual connector operations. Test logged-out, wrong tenant/collection, wrong role, revoked member, invalid/expired token and client-forged actor/scope. | Denial with no data/side effect; success control in same transport. A frontend-hidden button, synthetic principal or schema directive is not production auth proof. |
| 19 Accessibility/security/recovery/quality | Execute keyboard, screen-reader/semantics, touch, viewport/text scale and non-color disagreement checks; run threat/restart suites. Apply approved quality protocol only when supplied. | Per-platform results, screenshots, defects and expert dataset metrics. WCAG 2.2 AA and institutional quality cannot be declared passed from a widget test or absent Phase 0 thresholds. |
| 20 Complete journey | In one recorded session intake through classification, real segmentation, independent transcription, adjudication, lookup, validation, review and persisted final reopening. Close client during processing. Use only product UI/API actions. | Correlated IDs/timeline plus durable records and transport identity, no DB edits or reseeding. Local fixture journey is synthetic integration evidence; production-like/model and representative acceptance remain separate gates. |

## Threat and corruption matrix

### Mandatory candidate checks from architecture amendment

Coordinator supplied architecture HEAD `6a19fa9`; reviewed the canonical wire
freeze and delta ledger in CONTRACTS.md. The following owner-reported fixes are
**Not tested**, not acceptance evidence:

1. Capture actual local HTTP session, item/create, upload PUT/resume/complete and
   workspace responses from a synthetic journey. Feed those exact sanitized
   response bytes to Flutter parsing tests and the rendered API repository.
   Compare IDs, revision, offsets, singular asset, keyed fields, regions/bbox,
   observations, validations and events. Generated request schemas and handwritten
   expected examples cannot replace response fixtures. Confirm the same fixture
   digest is consumed on both sides and include a stale upload/review 409 path.
   Verify authenticated image fetches, relative URL handling, no-store and no
   bearer forwarding to an unrelated origin.
2. Send a valid authority envelope containing zero results through the adapter;
   distinguish it from empty bytes or a malformed envelope. The valid no-match
   outcome may leave an unsupported field needing review after required attempts;
   malformed provider output remains operationally blocked. Neither may become
   a supported candidate or Cleared. Retain raw HTTP bytes and persisted outcomes.
3. Persist and serialize a field with explicit `unresolved` state, then parse it
   in Flutter and reopen after process restart. Show the reason and abstention;
   do not silently coerce to supported or discard the field. Exercise each of
   the 20 mandatory keys, plus an unknown future enum to verify safe UI behavior.
4. Determine the exact serializer used for the 256 KiB snapshot limit. Exercise
   payloads of 262143, 262144 and 262145 serialized UTF-8 bytes through the actual
   persistence adapter; include multibyte text and JSON escaping to catch
   character-count errors. At/under limit may persist if otherwise valid; over
   limit must fail with a clear bounded error and no partial revision, decision,
   disposition or idempotency receipt. Reopen accepted data and retry rejected
   writes; no silent truncation. Record SQLite and SQL Connect results separately.

Repeat framework-generated 401/validation-error envelopes and available-action
role filtering against the amended serializer. Inspect committed code before
calling any architect-observed gap fixed. No candidate tests have run yet.

### SQL-backed HTTP and institutional semantics checkpoint

Coordinator reports initial real Python SQL Connect adapter execution against a
PostgreSQL 18 emulator, with the full workflow still in progress. This is owner
reported and **Not tested by QA**. Require an immutable candidate and isolated
launch handoff before execution. The independent SQL run must perform HTTP intake,
chunk resume/completion, worker processing, review and final reopening using the
actual connector transport. Record the explicit SQL adapter configuration and
persisted identifiers through a read-only connector query. Stop API and worker,
start fresh processes without seed/repair, and compare versions, evidence,
disposition and idempotency behavior. An emulator adapter unit test or a SQLite
HTTP journey does not substitute. Keep the PostgreSQL emulator state during this
process-restart check; database backup/restore is a separate procedure.

In that candidate, run the actual production Insects profile locally with
unresolved D/T/S semantics and Parties authority policy, even when all other
synthetic fields/evidence and scores appear complete. Request clearance through
normal review actions and repeat after restart. Expect an explicit unresolved
semantics/policy gate, no Cleared record, and no invented institutional approval.
Compare with an explicitly synthetic approved-profile positive control; verify
the latter cannot enable approval in the production profile by changing client
mode, submitted policy fields or retained idempotency key. This is local
production-profile policy verification, not production execution or museum
quality approval. No live provider calls or cloud mutation are authorized.

Cross-checked architect ACCEPTANCE.md after initial plan completion: the 20-row
coverage and synthetic/live limits agree. Section 11 P0 requirements remain
binding even where section 19 summarizes them. In addition to the matrix:

- P0-01: exercise HEIC and profile-approved RAW/TIFF with actual bounded decode,
  not just an accepted extension; camera quality feedback needs device evidence.
- P0-03/10/17: test configurable hierarchy, missing/ambiguous profile mapping,
  immutable published profiles, pinned versions and correction racing finalize.
- P0-05/06: test mixed scripts/languages, span/line/field/label disagreement,
  versioned risk components/reasons and no unsupported accuracy claim.
- P0-08/20: inspect persisted parse, plan, lookup, resolve, normalize, validate
  and finalize phases; a skipped phase requires an applicability decision.
- P0-15/19/20: test every specified search/filter dimension with positive and
  empty results, retry/dead-letter replay, authorized cancellation and human-wait
  restart. A visible filter that does not affect the API result fails.
- P0-17/19: backup/restore, retention and recovery targets require their own
  approved protocol; ordinary process restart is not a restore drill.

Use at least organizations A/B, collections A1/A2/B1, and operator, reviewer,
viewer, revoked and anonymous identities. A reviewer in A1 must not acquire A2
permissions by changing a URL, body, pagination cursor, referenced evidence ID,
upload ID, run ID or asset path. Check every read/write endpoint, list counts,
filters, events, audit and asset access; include a positive authorized control.

Try expired/wrong-audience/wrong-issuer/invalid-signature tokens and explicit
production mode with emulator credentials. Verify no fallback to synthetic
identity on auth failure. Revoke membership between read and commit. Confirm
role and actor come from verified server identity; idempotency keys bind actor,
organization and operation and cannot replay another user's response.

Check Storage and SQL Connect directly using their actual supported local client
transport. Attempt direct creation of cleared records, overwrite of raw evidence,
cross-scope reads and audit edits. Check the backend service-account path
separately because privileged SDK access may bypass client rules. Verify signed
URL scope/expiry locally if implemented; do not promise immediate revocation of
already issued URLs unless the architecture enforces it. Inspect redacted logs
and Flutter build artifacts for synthetic canary secret values only.

Upload negatives: MIME/extension mismatch, truncated image, empty file, changed
bytes after checksum declaration, false dimensions, over-limit byte count,
decompression-bomb metadata, invalid path/traversal filename, duplicate and
cross-tenant duplicate checksum. Use bounded tiny synthetic malformed fixtures;
do not allocate huge images. No invalid image may become accepted or produce a
processing job. Error details and duplicate references must not disclose another
tenant's specimen. If URL intake is exposed, test a local harness for redirect,
loopback/link-local and content-size policy; never probe real metadata services.

## Flutter usability procedure

Verify actual API mode and sign-in/sign-out/error recovery first. Through the
rendered application, upload, inspect per-file failures, navigate queue filters,
open original/crops, zoom/pan/rotate, compare readings, inspect field evidence,
record correction/reason, recover stale revision and confirm new disposition.
Refresh and reopen the result from a new session.

Run at desktop, tablet and narrow mobile viewport; repeat core actions at 200%
text scaling. Use keyboard only for focus order, dialogs, field edits, save and
error recovery; verify visible focus and no trap. Inspect assistive semantics
for controls, images/crops, status changes and errors. Confirm non-color labels
for differences, readable contrast and reduced-motion behavior. Record what was
actually observed with screen reader versus semantics inspection. Android/iOS
camera permissions, denial/retry, capture quality feedback, rotation, interrupted
network and background/resume require separately recorded device/emulator runs.

## Baseline independent test inspection and false-positive risks

The baseline has eight Python test files and one Flutter widget test. It has no
application API, persistence/review journey or Storage authorization test in the
inspected test inventory. These are baseline gaps, not findings against unseen
integration changes.

| Existing test | What it establishes | What it cannot establish |
|---|---|---|
| `test_transcription.py` | Line reconstruction validation and stable agent name | Pixel reading, two independent calls, raw persistence, adjudication |
| `test_model_gateway.py` | Explicit route config and mocked constructor arguments | Paid route availability, request isolation or valid output |
| `test_huggingface_preflight.py` | Handwritten catalog parsing and mocked CLI orchestration | Live SAM 3, actual credentials/transport or model execution |
| `test_evaluation.py` | Metric mechanics and two contract cases execute | Gold-set quality: candidate equals expected and task returns candidate; case count does not assert an acceptance threshold |
| `test_prompts.py` | Fake prompt resolver retains version metadata | Immutable published profile or persisted request provenance |
| `test_observability.py`, `test_tracing.py` | Synthetic metadata spans and selected content exclusions | Complete redaction under malicious errors or production telemetry/audit durability |
| `test_deployment_policy.py` | Required text fragments and bounded command scanning | Live branch protection/IAM, executable fail-closed behavior or a deployed matching artifact |
| Flutter `widget_test.dart` | App title and configured-platform text render | Auth, file intake, API wiring, evidence/review, accessible workflows or device behavior |

Reject additional false positives in candidate tests: reopening the same in-memory
object as a restart; sequential writes described as CAS races; assertions only
against response echoes; seeded dispositions bypassing policy; fake HTTP clients
described as integration; SQL text inspection described as executed transaction
proof; automatic retries hiding a lost external effect; and tests disabling
semantics/evidence gates without preserving an explicit synthetic-only boundary.

## Execution ledger and next dependency

### Pre-commit Flutter source review, 2026-09-08

Flutter owner explicitly requested read-only review before commit. Inspected
current files in `6b01` (auth, intake, models, HTTP repository, workspace and
review dialog) and the corresponding transcription handler in `3782`. These
are uncommitted source findings, not immutable candidate/browser reproductions.
No other worktree was modified. Shared all findings with Flutter and coordinator;
sent the transcription contract mismatch to backend as well.

| Defect | Severity and observed source behavior | Required regression / status |
|---|---|---|
| QA-F01 | P2: `workbench.dart` permits transcription unknown/unreadable selection, then emits null value. `api_repository.dart` sends only `after.text`, discarding state. Backend `api.py` transcription handler requires nonempty string and sets resolved true. The permitted UI absence action cannot save. | Region adjudication with absence state and reason must either persist typed abstention under an agreed contract or explicitly show unsupported action; never coerce absent text into supported transcription. Open, owner repair pending. |
| QA-F02 | P2: Field correction passes arbitrary server field state as dropdown initialValue; fixed dropdown items contain seven values. Unknown future state can trigger invalid dropdown selection/assertion instead of safe unsupported state. | Actual workspace fixture with unknown future field enum must render safely, preserve raw state and disable unsafe decision. Open, owner repair pending. |
| QA-F03 | P2 usability: Workspace carries `available_actions`, but review controls in inspected workbench do not consume it; busy state controls edit/approve availability. Viewer/operator can be shown prohibited reviewer controls. This is not evidence of backend authorization bypass. | Compare real viewer/operator/reviewer workspace responses; controls follow server actions and direct forbidden writes remain denied. Open, owner repair pending. |

Reported SQL HTTP restart, Flutter browser clearance and duplicate retention
remain owner-reported results pending immutable integration execution. Data owner
candidate is `790a9f936299de9770d66dc79563fb530625f9cf`; QA's planned isolated
PostgreSQL/SQL Connect ports are 5569/9519. Do not interrupt backend's leased
5549/9499. Worker claims to verify: five-minute persisted external-call lease,
revision fencing, three safe lookup retries/dead-letter, expired unfinished call
outcome-unknown, and snapshot polling recovery rather than an outbox consumer.

Initial independent commands: test/source inventory and full document reads.
No integrated or live journey has run.

| Check on baseline above | Independently observed result |
|---|---|
| `uv sync --frozen && uv run pytest -q` | Exit 0; 33 passed in 1.47 seconds, Python 3.11.16 local environment |
| `scripts/ci/verify.sh` | Exit 0; repository hooks/secret scans/actionlint/shellcheck passed, 33 Python tests passed, Flutter analyze found no issues, 1 widget test passed, release web build succeeded |
| Flutter build scope | Credential-free CI configuration, web release and Wasm dry run; no Android/iOS device test or production connection |
| Independent source inspection | Baseline lacks application API and end-to-end intake/review/persistence coverage; evaluation smoke is an identity task, not a quality benchmark |
| Integration handoff state | Integration confirmed baseline `82fd60e`, no runnable API, awaiting owner commits |

Canonical verification is baseline regression evidence only. All integrated P0
criteria remain not tested and overall P0 is **not accepted**. No files were
changed outside QA documentation; no push or deployment was performed.

Next dependency: integration's immutable candidate SHA and local startup/fixture
handoff. Send this plan to integration and coordinator now. After candidate
handoff, run canonical verification, independently reproduce applicable rows,
send concrete defects with severity/owner through coordinator, and update this
report with passed/failed/not-tested/externally-blocked evidence. Keep model
serving, approved authority access, deployed SQL transport and Phase 0 quality
acceptance blocked until their respective requirements are satisfied.


## Independent first-wave execution — 4c71e13, 2026-09-08

This section supersedes the initial not-tested ledger above. Frozen candidate
`4c71e133acc9f99c2dae068f4199c806bde8ff5f` was merged into the QA branch;
`git diff 4c71e13 --exit-code` confirmed an identical tracked tree before execution.
Evidence lives in `qa-evidence/4c71e13/`. Reproducer scripts record the actual
local harness and require the private temporary token/path; tokens are excluded.
These are synthetic correctness tests, not a representative quality evaluation.

| Independent execution | Result and limit |
|---|---|
| Canonical `scripts/ci/verify.sh` | Passed: 62 Python, 2 SQL opt-in skips; Flutter analyze, 16 offline tests plus 1 live skip, web release/Wasm dry run. |
| SQL HTTP process restart | Passed: 2 opt-in tests; API process termination/restart preserves full workspace and exact source bytes over SQL Connect9519/PostgreSQL5569. Synthetic cleared revision18, 2 observations, 28497 source bytes. |
| `scripts/data/test-postgres.sh` on5570/9520 | Passed executed CAS race, receipt/audit rollback, cross-scope and sensitive denial, revocation, normalized foreign keys and connector restart. Normalized schema tests do not prove runtime normalization. |
| Java21 `scripts/data/test-storage.sh` | Passed anonymous/authenticated read/list/create/overwrite/delete denial; original unchanged. Admin bypass remains explicit. |
| Flutter `live_api_test.dart` against TCP8124/SQL9519 | Passed real repository HTTP prefix100-byte resume, source access, unknown field correction, stale409, unreadable transcription persistence, observation retention and reopen. |
| Independent TCP negative intake | Auth/scope denial, chunk resume/replay, source digest/no-store and no-record corrupt-input cases passed; upload completion receipt and truncated PNG handling failed (B01/B02 below). |
| Exact UTF-8 aggregate bounds | SQLite and SQL both accept262143/262144 bytes and reject262145. Includes multibyte/escaped content; rejected save leaves prior record intact and rejected create retains no success receipt. |
| Policy absence probes | All260 probes across20 mandatory fields, six absence states and seven blank/placeholder literals prevent clearance. Default institutional policy and semantics remain unapproved. |
| SQL-backed roles, actual local HTTP | Viewer/operator approve denied403; available_actions follows role. Sensitive-denied workspace denied409; revoked membership prevents write404 and removes session scope. QA injected identity verifier; no Firebase signature/AppCheck validation claim. |
| Production-profile semantics, local fixture models | Emulator HTTP approval retains needs_human_review with institutional_policy_unapproved and mandatory_semantics_unconfirmed. QA explicitly injected fixture segmentation to avoid synthetic adapter's intentional production-profile rejection; no live model proof. |
| Authority boundary, controlled local HTTP | Distinguishes exact/no_match/malformed/ambiguous/429/401 and retains raw digest. Fixed authority URL routed to QA loopback server; no live GBIF acceptance. |
| Chrome GUI against actual SQL API | Persistent synthetic banner; source/regions, zoom/rotate/reset, separate reading panes, literal-versus-parsed field view. Empty review reason prevented save. Reasoned synthetic approval showed clearedrev18. Unreadable transcription saved and refresh showed reviewrev27 with explicit unresolved reasons. |
| Browser upload/device/accessibility | Extension file setter denied by browser permission; GUI upload not tested. Native fallback identified an unrelated foreground Chrome window and did not interact. Narrow390x844 screenshot retained; source geometry/accessibility need follow-up. Android/iOS devices, assistive technology and signed distribution not tested. |

The shared API fixture SHA256 independently matches both implementations:
`9cc65c46bf6c2bdeff42b6186b2949197b1cba8f8b6b2869823470ed04364616`.
Browser detail requires explicit Refresh evidence to show completed asynchronous
revalidation. Screenshots show synthetic fixtures only. Large boundary snapshots
are artificial adapter fixtures without image blobs and are excluded from GUI
journeys, not counted as product ingestion success.

| Defect | Independent result on frozen candidate |
|---|---|
| QA-F01 | Closed for local scope: typed unreadable survives real Flutter HTTP test and GUI save, preserves original observations and prevents clearance. |
| QA-F02 | Closed for widget regression scope: future enum guard tested; no live backend future-enum response injected. |
| QA-F03 | Closed for server/action-gating scope: Flutter regressions/source plus SQL-backed viewer/operator denial; no role-specific GUI screenshot. |
| QA-B01 P2 | Open: completion with same key and changed reason returns200; exact replay returns later snapshot rather than original receipt. Actual TCP/SQL reproduced. |
| QA-B02 P2 | Open: truncated60-byte valid PNG header returns503 retryable runtime_unavailable and resets the next keepalive request. No specimen created; expected422 with usable connection. Actual TCP/SQL reproduced. |
| QA-B03 P1 | Open: moving a retained raw response out of owned temporary blob storage before normal approval still returns200 cleared with no reasons. Exact HTTP/TestClient/SQLite repro; copied policy also ignores wrong digest/ref/asset lineage. Baseline SQL/TCP corruption variant not executed. |

Overall P0 remains **not accepted**. Across the20 criteria, local intake,
provenance, policy, review and persistence portions above have bounded positive
proof; B03 blocks trusted clearance. Real SAM3/classifier/two-model quality,
approved authorities and Parties/geography semantics, representative frozen
quality cohort, institutional policy approval, production authentication/IAM,
deployed SQL/storage, backup/restore, worker failure coverage at live external
boundaries, publishing and physical-device accessibility remain unproven or
unimplemented. No synthetic test changes those acceptance states. CI mobile
builds were reported green by integration on this candidate but not independently
inspected here; build success cannot establish device behavior.

Repair candidate `25e83589031cf4d751a7059d07d252287ef2783e` is pending independent
reproduction. Owner tests alone do not close B01–B03. No production deployment,
cloud mutation, paid inference, museum data or product code changes by QA.


## Independent repair verification — 25e8358

Product tree matches `25e83589031cf4d751a7059d07d252287ef2783e`; only owned QA
artifacts differ. Restarted owned API against unchanged SQL9519/PG5569 and
retained local storage. Independently reran the original TCP upload reproducer
and added fresh API-created synthetic records for each storage/graph fault.
`qa-evidence/25e8358/` retains the results and exact harness. All faults are
injected only into QA-owned storage/records and restored in finally blocks.

- **B01 closed locally:** changed completion payload under same key returns409;
  identical replay preserves the original response despite later processing.
- **B02 closed locally:** truncated PNG returns422, no specimen, and subsequent
  request on the same HTTP client succeeds. Other corrupt metadata cases stay422.
- **B03 closed locally:** 48 actual TCP+SQL assertions pass. Missing/corrupt
  source, observation and lookup bytes persist processing_blocked with null
  disposition and evidence_integrity_failure. Restoring bytes and approving a
  new version recovers synthetic clearance; replay keeps the old blocked receipt.
  Persisted wrong digest, wrong raw reference, foreign asset association, wrong
  input digest, wrong region asset and wrong evidence reference also block and
  recover after graph restoration. No real Firebase or model-call claim.
- Additional committed regressions independently pass:14 tests in
  `test_evidence_integrity.py` and `test_upload_completion_http.py` (3.91s).

An initial harness reused one record for every fault and reached the documented
256KiB aggregate cap during the sixth restore (HTTP413). Bytes were restored;
that fixture remains blocked until record-size handling. This is retained as a
capacity limitation, not concealed as a test pass. Fresh records per independent
fault completed all48 integrity assertions. No cap or policy was relaxed.
The verifier's positive production-extraction compatibility follow-up remains
pending on the next immutable integrated SHA; live providers remain untested.

### P0 criterion dispositions after local repairs

No row is accepted in full; these are bounded executed portions and remaining
work, mapped one-to-one to the20 procedures above.

| P0 | Independently passed local portion | Remaining acceptance gap |
|---|---|---|
|01|TCP resumed chunks, Flutter repository resume, duplicate receipt/conflict|GUI chooser and device camera/interruption not tested|
|02|Fetched source hash/no-store, metadata rejection, Storage rules denial, corrupt source blocks|Cloud immutable generations/derivatives not tested|
|03|Canonical synthetic/profile contract regressions|Real classification and full correction/supersession journey not tested|
|04|Displayed synthetic regions and source controls|Real SAM3 serving blocked; full region-edit geometry not tested|
|05|Two retained synthetic observations; raw digest integrity|Live independent routes/request isolation and interrupted first pass not tested|
|06|GUI separate readings and unreadable adjudication preserve observations|Real disagreements/peer isolation; assistive reading text needs verification|
|07|GUI literal-versus-parsed fields and repository correction|Full transformation lineage under historical/date/elevation cases not tested|
|08|Controlled HTTP exact/no-match/ambiguous/empty/429/401 typed and raw-retained|Full retry timing/403/timeout matrix and live authorities not tested|
|09|Actual API process restart using SQL and committed worker regressions|Three external-call crash boundaries and concurrent worker race not independently exercised|
|10|Unresolved semantics, mandatory absences and missing/corrupt evidence prevent clearance|All critical gates with real provider outputs/approved policy not tested|
|11|260 missing/unresolved/placeholder probes across20 mandatory fields|Institutional D/T/S/Parties semantics and approved attempt budgets unavailable|
|12|Default policy/semantics fail closed; unreadable remains explicit|Adversarial live-model pressure and unsupported authority identity cases not tested|
|13|Evidence outage operational block/null; restore/replay|Full provider failure/retry/dead-letter matrix not independently executed|
|14|Canonical synthetic deferral policy regressions|Independent viable-alternatives exhaustion and real capability limits not tested|
|15|GUI reason validation/approval/unreadable; real Flutter stale409|Full two-GUI-session race and all invalidation paths not tested|
|16|Actual stored-byte hashes plus wrong graph associations rejected|Complete field-by-field production lineage traversal and scope-bound cloud objects not tested|
|17|Actual SQL API kill/restart preserves workspace and exact original|All three outcomes/historical crops plus browser restart and backup restore not tested|
|18|TCP token/scope/role/revocation denials, SQL and Storage emulator isolation|Firebase crypto/AppCheck, productionIAM and exhaustive threat cases not tested|
|19|Browser/narrow screenshots; canonical analyzers/builds/tests|WCAG/device/text-scale review and approved quality cohort blocked or not tested|
|20|Synthetic local API/Flutter review-to-persisted-results portions|One complete GUI intake journey, real model chain and representative acceptance not tested|

Overall P0 remains **not accepted**; closing three defects is not a release or
scientific-quality acceptance. No production merge/deployment was performed.


## Additive extraction verification and B04 — 76da660

Exact product candidate `76da6606542201265101193ca831731efd52b319` incorporated
only the extraction checksum follow-up after25e8358; QA artifacts differ.
Independently executed all15 upload/integrity regressions (3.58s, passed), then
called the actual `extract_with_agent` through a real PydanticAI Agent configured
with its explicit local TestModel. This exercised response serialization, blob
retention, checksum generation and source-supported candidate application rather
than manually supplying the digest. Set profile.synthetic=false and computed
actual crop-input hashes for retained fixture observations. The901-byte response
matched the generated evidence digest; positive integrity passed, replacing that
response with corrupt bytes failed, and restoring it passed. This is a controlled
model boundary, not live inference, museum policy or production-cloud proof.
Results and harness: `qa-evidence/76da660/extraction-*`.

**QA-B04 P2 open: repeated normal review makes records uneditable.** Independently
created a fresh synthetic specimen through actual TCP8124/SQL9519 on76da660 and
sent ordinary reasoned approve decisions with fresh idempotency keys and current
revisions, with no corruption or graph injection. Eleven succeeded; the12th
returned413. Persisted snapshot grew from43561 bytes after first approval to
243821 after eleven. Audit accounted for223316 bytes,24 entries; previous_runs
remained empty. Each additional successful review added20026 bytes. Thus normal
short-reason review history reaches the256KiB cap after a low action count.
The12th failure safely preserves prior state but prevents later review/recovery.
Separate earlier fault fixture remained blocked despite restored bytes because
its recovery approval could not fit. This is not closed by fresh test records.
Growth series, specimen ID and exact harness are retained in
`qa-evidence/76da660/capacity-*`; backend and coordinator received the finding.

Required repair acceptance: preserve every historical revision/audit/evidence
and stable idempotency receipt, paginate bounded historical reads, keep current
snapshots bounded, and permit continued review/recovery well beyond11 actions.
Do not increase the limit or delete evidence to pass. Verify existing oversized
history fixtures recover through the supported migration/compaction path and
that old snapshots remain exactly reconstructable. Owner implementation is not
independent acceptance evidence. B01–B03 remain closed for tested local scope;
B04 remains open, overall20-criterion P0 remains not accepted, PR must stay draft.

### Visual follow-up QA-F04 P2

The retained390x844 Chrome screenshot shows the1000x520 original squeezed into
an approximately307x380 image box, visibly changing character proportions.
Flutter source remains unchanged through76da660: fixed380-height source container,
constrained AspectRatio/expanded Stack and Image.memory(BoxFit.fill). Reported
to Flutter and coordinator for intrinsic ratio preservation with aligned overlays
at narrow/wide widths and every rotation. Open; source pixel integrity on disk
does not establish faithful display geometry. Independent readings' text was
visually present but absent from the captured accessibility tree; this remains
an accessibility follow-up pending deeper semantics verification, not a confirmed
screen-reader defect. Browser viewport override was reset after QA.


## B04 backend reproduction — 95215d9

Exact candidate `95215d9ad6270052a644c12e4b822da399f0c487`, identical tracked tree
before execution. Original SQL9519/PG5569 state retained from the failing builds;
no reseed or manual repair of either near-cap record. Preserved all28 raw snapshot
rows per record before starting the new API. Evidence/harness in
`qa-evidence/95215d9/`; full prior snapshots and restart checkpoints retained in
the private QA temporary directory rather than duplicating large synthetic data.

| Independent actual TCP/SQL check | Result |
|---|---|
| Original blocked record98b3eac6… | First approval recovers;211 new decisions succeed: recovery,100 ordinary approvals,110 missing/restored approvals. Maximum current snapshot130668 bytes; final52134. |
| Original ordinary-cap record7aced055… | First approval recovers;101 new ordinary decisions succeed. Maximum/final current snapshot88283 bytes. |
| Full historical reconstruction | First record239 revisions/19 pages/235 unique audit events; second129 revisions/10 pages/125 unique events. Every global sequence is contiguous; duplicate appearances agree exactly. Every historical model digest matches its page entry. All56 pre-repair raw snapshot rows remain exactly equal, including stored payload/hash. |
| Compaction/reference/retry | New current snapshots stay below128KiB through rollover; previous run references resolve and their run digests match. First successful repair-decision receipt replays identically after all later decisions. Stale new writes and wrong run IDs/digests return409; excessive page limit returns422. |
| Authorization and stored tampering | Actual HTTP with SQL memberships and injected QA token verifier: viewer reads history; anonymous401, wrong organization404, revocation404. Sensitive permission removal denies409 (conflict envelope limitation); restoration200. Altered checksum of one QA-owned SQL snapshot causes409 for exact-version and page reads; restoring original checksum restores200 and exact original row. No Firebase crypto claim. |
| Process restart | Terminated actual API process4855 and started a fresh API5575. New HTTP client obtains exact current workspace, bounded page and original revision28 workspace for both records; six equality checks pass. SQL connector/database were not restarted in this check. |
| Bound unchanged | Independent SQLite and SQL262143/262144-byte acceptance,262145 rejection, rejected-save atomicity and no success receipt on rejected create all pass. No limit increase. |
| Affected committed regressions |18 passed,1 opt-in SQL test skipped in5.18s; own tests above independently exercise actual TCP/SQL rather than treating the skip as evidence. |

Backend capacity/recovery behavior passes the independent reproduction. Full B04
closure awaits the client history read-only flow on the assembled candidate.
A provenance wire clarification is pending: page item.sha256 on a legacy revision
differs from its original stored snapshot.sha256 because the API hashes the parsed
model with new default fields. Original stored bytes/hash are independently
verified and unchanged; the page hash must be labelled as reconstructed-model
hash or return the original retained hash so reviewers can distinguish them.
This is not evidence of lost history; it is a precise hash-meaning limitation.
F04 responsive source geometry remains open until browser verification. Overall
P0 remains not accepted; all live-provider/institutional/production limits above
still apply.


## Original stored hashes and Flutter HTTP history — 75f2953

Exact candidate `75f295385da27919d2f87000ba8aaa4febbe6f7b` includes the retained-hash
fix and Flutter history client; only prior owned QA artifacts differ. Independent
actual HTTP comparisons now match all56 original raw snapshot hashes captured
before repair. All56 raw-run references resolve with the original stored run
hash. Fixed-bound history pages remain exactly stable across new current review
writes; new review-before links resolve. The earlier hash-meaning limitation is
closed locally. Metadata now denotes the original retained digest.

Repeated actual SQL membership/revocation and stored-checksum fault checks pass
on this candidate, including409 for a tampered exact version and metadata page,
and200 after restoration. No stored history was rewritten to obtain the match.
Evidence: `qa-evidence/75f2953/`.

Independently ran Flutter `test/live_history_test.dart` against API8124/SQL9519
with original recovered compacted record98b3eac6…: one passed in3s. It paginates
all bounded revisions, loads historical evidence into a read-only client model,
validates reference mismatch409, retains current CAS for review, and denies a
stale review. This is real Flutter repository HTTP behavior, not a GUI result.
History Python regressions:4 passed,1 SQL opt-in skip in2.30s, supplemented by the
actual SQL checks above. Backend B04 proof remains passed; final B04 GUI closure
and F04 geometry still await the assembled browser candidate. Overall P0 remains
not accepted; no production/cloud/model deployment occurred.


## Final combined local repair assessment — 290a2a7

Exact candidate `290a2a7c6c713d39b1fefc9b88298bbe7b5f86bc`; tracked tree identical
before execution. Independently reran canonical verification: exit0,81 Python
passed/3 SQL opt-in skips,26 Flutter passed/2 live opt-in skips, analysis clean,
web release and Wasm dry run passed. Prior independent TCP/SQL evidence above
covers the opt-in boundaries; skipped tests are not counted as new passes.
Fresh owned API and Flutter processes served this candidate against the preserved
QA SQL database. No production connection or deployment.

**B04 closed for tested local backend and browser scope.** Chrome opened the
original recovered near-cap specimen98b3eac6… at current revision241. Browsed three
pages of retained revisions1–30 and opened original revision28: explicitly
read-only, historical processing_blocked status retained, original observations
and24 audit events available. Current review remains revision241. Opened current
review event237 and followed its retained run/hash reference to revision240,
again read-only with current241 unchanged. Independent HTTP confirms persisted
current revision241 after all GUI history browsing. The earlier312-decision,
full-sequence, exact56-row preservation, stored-hash, permission, tamper, receipt,
CAS and restart evidence remains applicable; no backend code changed afterward.

**F04 and the observed reading-text accessibility defect closed locally.** Chrome
at390x844 and1440x1000 displayed all four rotations. Screenshots retain the full
source and full-image region border; independent raster bounds measure310x161
and198x380 at narrow width,608x316 and198x380 at wide width, within2 pixels of
1000:520 or520:1000. Source character proportions remain faithful. Non-full-region
overlay coordinate offsets are additionally exercised by the canonical geometry
widget tests; the live browser fixture has a full-image region. Both model groups
now expose their complete independent literal text in the accessibility tree.
This is not a complete screen-reader/device/WCAG acceptance claim.

Evidence: `qa-evidence/290a2a7/` includes eight rotation screenshots, historical
read-only screenshot, accessible-text captures, raster measurements and result
manifest. Text captures abbreviate raw digests to avoid redundant full hashes;
original retained hash comparisons are independently recorded in75f2953 evidence.
Viewport testing initially changed device pixel ratio; reloaded at fixed DPR1
before final captures. Clipped accessibility rectangles were unsuitable for
rotation measurement, so the final checks use fully visible screenshot pixels.

GUI file selection remains **not tested**. The extension file setter is blocked
by file-URL permission. A bounded native fallback inspected the connected Chrome
window/tab list, but the agent QA tab was not exposed there; no safe native picker
could be operated. No browser permissions were changed and no user file uploaded.
The original native window was restored, viewport override reset and QA tab closed.
HTTP/Flutter repository upload proof remains valid and distinct from GUI upload.

All reported B01–B04 and F01–F04 defects are closed within their stated local
scopes. Overall20-criterion P0 remains **not accepted**: real provider/SAM3 behavior,
representative quality thresholds/cohort, institutional policy and field semantics,
full production security/deployment, device/accessibility and the untested portions
of the criterion matrix remain open. This is a local repair verification result,
not production or scientific acceptance. No PR merge/deployment was performed.

## 2026-09-08 — second-wave frozen backend checkpoint e963811

**No new defect found in the tested backend checkpoint; not overall P0 acceptance.**
Application `e963811aad17d8a958c948df0c11c13321a69b34`, documentation
`e2cd07627717a5ee4111dafd895dac4e849141c5`. QA merged the frozen tree into its own
branch and verified no tracked difference before execution. First-wave repair
results remain recorded above. The newer Flutter implementation is excluded here.

Independently ran canonical checks:206 Python passed/13 explicit optional skips,
26 Flutter passed/2 opt-in live skips, analysis and web release build passed.
Fresh QA-owned PostgreSQL/SQL Connect on5569/9519: designated authority, worker,
history, upload, persistence and process-restart suite26 passed. Skips are not
counted as live evidence. No institutional connection, paid inference, cloud
mutation, release or deployment.

Additional QA-authored probes in `qa-evidence/e963811/`:

- 63 assertions through actual loopback HTTP. The authority workflow used actual
SQL Connect/PostgreSQL and a local TCP Parties response. Its observer queried the
exact specimen before the network effect and found the retained intent. All seven
phase endpoints returned evidence. Bad tenant, absent candidate and mismatched
field selections returned422 with no revision or extra request. Valid selection
remained needs_human_review; a separate approval cleared. Corrupt raw retained
bytes returned503 `authority_artifact_integrity_failure`, then restored bytes
matched exactly. Source correction issued one new receipt/request, invalidated
clearance, and preserved the complete old workspace and all seven phase artifacts.
SQL metadata timestamps/revisions, terminal keyset page, changed-filter cursor,
invalid/duplicate filter and timestamp rejection passed.
- Actual HTTP preflight exercised valid PNG, MIME mismatch, corrupt PNG, disabled
HEIC, empty/oversized body, missing identity and wrong scope. Every database table
count and blob directory stayed unchanged. Successful decoder execution used an
explicit QA-only memory-enforcement opt-out and2048-byte limit on macOS; this does
not establish production memory isolation or optional-codec intake support.
- Four actual HTTP reading cases cover supplementary Unicode, combining marks,
CRLF, Bengali/Arabic, full-width numerals, insertion/deletion and9000-character
opposing readings. Returned half-open spans slice exactly in codepoints, UTF-8
and UTF-16. Raw bytes match retained digests; text hashes preserve originals.
Long comparison is policy_blocked with null distance/no alternatives and
unmeasured disagreement. Language/script remain unknown. A separate deterministic
300-case full-matrix distance oracle and span-reconstruction check passed.
- Actual HTTP with explicitly injected emulator identities/membership policy and
SQLite verifies current and pinned raw/metadata/disagreement access revocation,
restoration, and actor/permission cursor binding. This tests application checks,
not Firebase identity validation or production IAM.
- A separate persisted SQLite worker discovery exercise covers13 scopes/39 rows,
38 healthy rows exactly once with one poison row isolated, eight-scope/two-step
budgets, restart, later eligibility sorting behind the cursor recovered on wrap,
and membership outage/backoff recovery. Workflow effects in this fairness probe
are controlled callbacks; real workflow budget, lease, crash and SQL execution
boundaries are additionally exercised by the canonical/designated suites.

No product fixes were made. Harness setup mistakes (missing text argument,
incorrect workflow method name, overly specific expected403 vs404 and422 vs503)
were corrected before the final successful run; they were not product findings.
Repeated attempts used distinct synthetic source metadata to avoid duplicate
fixture interference. Raw response allocation, active graph growth, shared
circuits, SAM3/auth total deadlines, SQL V3 checksum wiring, optional codec intake
and language/script propagation remain the explicitly known pending work. No
claim is made about representative scientific accuracy, approved authority policy,
production security, real model behavior or complete PRD acceptance.

## 2026-09-08 — combined second-wave GUI checkpoint a398583

**No new defect found in the observed combined flows. Overall P0 is not accepted.**
Frozen application `a3985830c75fc9242a241ad9f621387e00612b75`; backend source,
tests, SQL and scripts remain identical to the independently tested e963811.
Imported into the QA branch after committing backend report `e371a7c` and verified
application-tree parity. Later owner followups are excluded from this checkpoint.

Independent canonical rerun passed206 Python/13 optional skips,47 Flutter/3 opt-in
live skips, analysis, scanners and release web build. The opt-in Flutter
`live_next_workflow_test.dart` separately passed through actual HTTP against a
fresh local API, SQLite and TCP mock Parties: synthetic specimen64a3b4b0…
revision24→26. Logs: `/tmp/specimen-qa-a398583-canonical.log` and
`/tmp/specimen-qa-a398583-live.log`. These are local synthetic results.

**GUI PNG intake is now tested in the Codex in-app browser.** Its supported file
chooser selected only repository synthetic fixtures; no browser permission was
changed. Local preview showed uncalibrated brightness/contrast/detail and explicit
limits. The server received preflight only after clicking its action. It reported
the macOS memory-enforcement block with the correct runtime remedy and retained
manual review guidance. All database counts remained1 record/26 versions/26
receipts/2 documents. Adding a second image reset the checked manual-quality
confirmation. Explicit upload reconciled `synthetic-wide-label.png` as a duplicate
and accepted the new27240-byte800×600 `synthetic-label.png`. This resolves the prior
picker gap for this browser. Final disk verification matched both retained source
blobs byte-for-byte to their selected repository fixtures. Chrome-extension and physical camera/device behavior
are separate, untested boundaries.

Browser-uploaded specimen `68cb3d4f-d8a1-5094-a3e9-d243ec3f74dd`:

- Classification rejected an empty reason, then accepted the returned published
  synthetic profile. Revision24→48 created a different run while independent HTTP
  verified the same authorized collection and immutable source.
- Opened lookup-phase proposals, the retained authority candidate and its
  identity/context, and118-byte raw authority text. Selected qualified
  `emu:/fmnh/eparties/7`: revision49 remained needs_human_review. A separate review
  approval produced cleared revision50. HTTP confirms the original literal and
  full system/connection/tenant/environment/module/IRN identity were preserved.
- Reading metadata explicitly displayed language/script unknown. Opened the
  retained comparison. Browsed three history pages and opened original completed
  revision24, explicitly read only with current review still50.
- At390×844, the scrollable region dialog retained original800×600 dimensions.
  Required reason validation prevented an empty save. A clockwise quarter-turn
  was saved with bounds0,0,800,600 unchanged. Independent HTTP verifies
  rotation_quarter_turns1, unchanged source digest, revision70 and renewed review.
- Named asset filtering returned one record; AND Cleared returned an honest empty
  state; clearing filters restored two records. Desktop1440×1000 and narrow390×844
  screenshots show source containment and readable responsive controls. No
  captured browser error logs were present.

Evidence: `qa-evidence/a398583/` contains screenshots, accessible UI captures and
independent HTTP summaries. Full unabridged captures remain in
`/tmp/specimen-qa-a398583-browser-evidence`; committed text abbreviates digests.
Some Flutter semantic `fill` calls did not visibly update narrow text fields;
verified focused keyboard input before saving. These tooling attempts were not
reported as product defects. No product source or scanner rule was changed.

The long-reading blocked state, nontrivial Unicode spans, queue multi-page UI and
all EXIF transformations were not additionally exercised in this GUI session;
backend/Flutter tests above are the evidence for those boundaries. The owner’s
known stale-selected-ROI followup `1e18d14` is not in frozen a398583 and is not
closed by this result. Known SQL V3, graph/streaming, circuit/deadline, codec and
language/script propagation work and institutional/scientific/production gates
remain open. No new release approval is implied.

QA signed out, reset the viewport and closed its browser tab. Owned web3000,
API8124, SQL9519 and PostgreSQL5569 services were stopped. SQLite/blob evidence is
retained at `/tmp/specimen-qa-a398583-authority`; the fresh SQL cluster is retained
under the temporary `specimen-data-serve.qVpvwg` directory. No push, PR merge,
production connection or deployment was performed.

## 2026-09-08 — frozen hardening checkpoint906e134, atomic repair pending

Candidate `906e1348e71a0e800bfb260fa1125d67239b0e0e`, exact backendd6be7a0 and
Flutterf10eb79. Independent canonical243 Python passed/23 optional skips,
54 Flutter passed/4 live skips, analysis/scanners/web passed. Fresh SQL suite
**29 passed,1 failed**: same-source concurrent completion returned409 Immutable
blob content mismatch and200, rather than200/200 acceptance/duplicate.

**H01 open: LocalBlobs publishes an incomplete final pathname.** A deterministic
QA-only scheduling hook pauses the first writer after exclusive create, before
writing. Its final hash-named path is visible at size0. A second actual put of
identical bytes falsely raises Immutable blob content mismatch. The first write
then completes and reads correctly. This reproduces the spontaneous SQL/HTTP
failure and is not excused by a later retry. A process crash in this window can
also retain an incomplete hash-named file. Backend and integration received the
reproducer immediately. No product edit was made to this frozen tree.

Other independent checks passed:

- Four actual HTTP completions synchronized before real CreateSpecimenV3 writes:
  four distinct IDs/keys, one committed specimen, three authorized duplicates,
  exact same-key receipts, changed-key409 as intentionally bound by contract.
  Invalid checksum SaveSpecimenV3 left revision1; valid save reached2. No legacy
  create/save operation was used. This proves SQL uniqueness, not local blob
  publication correctness.
- Real patterned HEIC120×80 with orientation6, explicit null dimensions, actual
  HTTP intake and codec child: verified80×120 decoded primary basis, byte-exact
  original, canonical pixels matching an independent decoder, partial crop
  5,7,40,50 and clockwise rotations1/3 matching NumPy pixel oracles. Restart with
  codec disabled and decode calls forbidden still processes retained pixels.
  Optional owner suite9 tests also passed; no arbitrary RAW/device claim.
- SAM child fixtures: slow authentication and drip TCP completed deadline handling
  in3.03/3.01 seconds for a3-second budget. Oversize output and401 fail closed.
  Children were reaped, private IPC cleaned, unknown outcomes retained, and three
  fresh workflow/repository calls after lease expiry issued no additional request.
- Actual local TCP through GCS streaming adapter: eight exact/oversize/header/
  digest/redirect/missing cases.257-byte cap consumed258 application bytes on
  overflow; oversized declared length consumed0. All responses closed, generation
  pinned, no redirects followed. GCS auth/stream wall-clock bounds remain excluded.
- Four fresh Python interpreters synchronized their initial SQL circuit read:
  exactly one half-open permit and three busy responses. Restart state, expired
  probe reopening, late-result fencing, successful closure and600-second provider
  minimum were verified through actual SQL Connect worker_cursor CAS.

Evidence and reproducible scripts: `qa-evidence/906e134/`; full private synthetic
captures resolve via `/tmp/specimen-qa-hardening-path`. Canonical and optional
logs are `/tmp/specimen-qa-906e134-{canonical,codecs}.log`. Actual Flutter HEIC
HTTP test independently passed. GUI selected/uploaded a fresh patterned HEIC
without local dimensions and showed honest80×120 decoded source provenance.
GUI crop/approval completion is **not yet established**: one post-resize click
sequence saved an empty region list; server refused clearance. Stable-viewport
keyboard rotation retained a region but the temporary browser tab closed before
that edit was saved. This is unresolved automation-versus-UI evidence, not a
confirmed second product defect. No crop-GUI pass is inferred.

Preserving this failed checkpoint before the separately reviewed minimal atomic
repair38fa32f+c8001bb. Graph/TRN are excluded. No production work or full P0
acceptance is implied.

## 2026-09-08 — minimal atomic repair verified, H01 closed locally

Exact approved application sequence906e134 +
`38fa32f07a77e28a9731a57b11334af7c7949eaf` +
`c8001bbe5f29cf1d679e7b982ecc079c868ca4a8`; verified empty application diff against
c8001bb. Only storage.py and the publication test differ from the frozen app.
No graph or TRN source was included. Original failure evidence remains in8e421b1.

**H01 closed for tested local immutable publication and SQL intake.** The QA
reproducer was adapted to stop the real writer both before writing its private
temporary file and immediately before linking the completed file. In both cases
the final digest pathname is absent. A second identical put succeeds and reads
byte-exact; releasing the first writer reconciles without replacing the existing
inode. Both leave no owned temporary file. First/replayed empty publication works;
corrupting its bytes then replaying fails closed without overwriting corruption.

Independent focused publication/stream/SQLite+SQL HTTP duplicate/shared circuit
suite:11 passed in3.34s, including the formerly failing SQL race and40 repeated
multiprocess publications with concurrent readers and crash recovery. Five further
QA-authored four-way barrier races through actual HTTP and SQL V3 produced five
unique winners and15 authorized duplicates from20 distinct proposed IDs/keys.
All20 same-key completion replays were exact; changed keys rejected; invalid
checksum saves left revision unchanged and valid V3 saves succeeded. No legacy
writer calls were observed. Evidence: `qa-evidence/c8001bb/`; focused log
`/tmp/specimen-qa-atomic-repair-focused.log`.

This bounded repair result was sent to parent/integration before broader GUI
completion. It does not close the incomplete HEIC crop GUI case or imply graph,
production, GCS wall-clock, codec memory-isolation or complete P0 acceptance.

## 2026-09-08 — frozen graph independent checkpoint

Frozen target `745127a1a326473a1aa93794bc7ae07f58591ba3`, exact product tree
verified after importing onto QA atomic closure. Canonical independent run:
259 Python passed,24 optional skips;58 Flutter passed,5 gated live skips;
analysis, scanners and web build passed. Fresh isolated PostgreSQL/SQL Connect
suite:49 passed. TRN changes are excluded from this checkpoint.

QA constructed a synthetic storage fixture with20 observations, including a
4,320,000-character marked reading. Complete artifact4,828,563 bytes; workspace
returns413 with retrieval metadata. Actual HTTP verified complete artifact size,
SHA header and scope/specimen/revision identity; missing authentication and wrong
organization were denied. This oversized synthetic fixture proves storage and UI
behavior, not transcription accuracy or scientific clearance.

In the actual Flutter browser, complete-artifact verification succeeded. QA
visited **all377 observation pages** using the Next control, captured every full
rendered text node, concatenated4,515,728 characters and parsed JSON. It equals
all20 observations in the independently retrieved original artifact exactly;
there is no missing page or truncation in this tested section.

Actual Flutter HTTP test passed coverage57→58 with committed receipt, exact
historical57 retrieval, stale CAS rejection and current cancel58→59. Browser
then applied pause59→60 and cancel60→61. Both displayed the explicit saved
revision and do-not-repeat acknowledgment. Current snapshot stayed12,897 bytes.
Historical57 artifact remained byte-exact after those mutations and a separate
server-process restart. Current artifact corruption returned409, restoration
recovered exact bytes and revision stayed61. No product changes were made.

Evidence scripts/results: `qa-evidence/745127a/`. Full browser page capture,
receipt/cancel snapshots, screenshots and original artifact are retained at
`/tmp/specimen-qa-745127a-graph`. Logs:
`/tmp/specimen-qa-745127a-{canonical,sql,live}.log`.
This closes the tested >4MiB local graph/UI path. It does not promote production,
scientific quality, cloud/provider limits or all20 P0 requirements to accepted.
