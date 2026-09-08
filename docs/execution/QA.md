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
