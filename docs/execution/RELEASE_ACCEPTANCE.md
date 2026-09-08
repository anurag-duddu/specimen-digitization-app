# Production product acceptance

Owner: `01a082b4-a9bc-7413-a3c5-5077dd5c3a9f` (Flutter/acceptance).
Coordinator: `01a082b2-c2c3-70d2-be90-7bfb622c9102`.
Model: `gpt-6-astra`, `xhigh` (coordinator verified actual turn context).
Worktree: `/Users/anuragduddu/.codex/worktrees/ac0d/specimen-digitization-app`.
Branch: `codex/release-acceptance`. Starting product SHA:
`61d82aed64816802cd6ac00ac11e307a30c2bd8e`.

Status on 2026-09-08: **Not accepted live. Local acceptance harness verified.**
No cloud writes, specimen reads, paid calls, push, merge or deployment performed.
The existing client/API fixes are already in main; historical unmerged statements
in `LIVE_*` reports do not represent the current release state.

## Current public observation and remaining inputs

GitHub main independently matched the baseline. In the public browser at
<https://specimen-digitization.web.app>, enabling Flutter accessibility exposed
“Collection connection required” and the explanation that the API is not
configured. There is no sign-in form or collection workspace in this state.
This is a product setup blocker; the title/HTTP status/marker are not acceptance.
The coordinator separately verified all six baseline CI jobs and the public
marker, and confirmed API/App Check repository variables are empty.

Confirmed source contract: live client expects HTTPS configuration, Firebase
verified email and UID, App Check on protected requests, production session mode
and server-assigned membership. It rejects failed attestation, malformed session
scope and synthetic mode. Access denial invalidates the workspace and suppresses
following protected requests. Existing HTTP/widget regressions cover these paths.
No new Flutter behavioral defect was established during this bounded audit.

Required before live execution:

- The coordinator relayed the user's approval of the protected runtime/data
  amendment and bounded Google setup under the shared USD 5 ceiling. Implementation
  and actual release receipts, combined immutable SHA, public API/App Check
  configuration and exact resource/cost qualification remain required.
- Data owner provides the approved private ready first-ten manifest and its
  independently supplied SHA-256, authorized identity/scope, original generations,
  and approved local intake inputs. Keep all identity/object/receipt details private.
- Real sign-in, App Check, SQL/Storage readiness, deployed runtime/worker/SAM pins
  and restore/restart execution must be demonstrated. Google reauthentication is
  coordinator-owned; missing access is not proof that a cloud resource is absent.
- The user supplied **USD 5 total incremental spend**, shared across every session,
  provider, retry and day, with the same daily maximum. Budget approval is present;
  measured costs, hard execution reservations and complete reconciliation are not.

The prior local PostgreSQL/SQL Connect restore result is owner evidence supplied
by the coordinator: scoped paging/search/CAS/admin concurrency, restore and two
connector restarts with index repair. Log:
`/tmp/specimen-release-data-postgres-coordinator-20260908.log`.
It used local services and synthetic fixtures, not production data. It was not
rerun here or relabeled as independently observed by this acceptance session.

## Acceptance cases and executable procedure

Use `scripts/qa/live/acceptance.py` and its README for private ledger creation
and evaluation commands. The extended ledger retains all 20 PRD and 15 threat/
operational cases and adds ten explicit UI cases (45 total). Missing a case is
invalid. A blocked/not-run/non-live case is pending. Every passing case requires
retained bytes with their exact SHA-256, observer, time, command, expected/actual
behavior and successful exit status. The seven data journeys require all ten
manifest specimens; a failed specimen stays in the denominator.

The rows below specify execution through the public UI and supported API. Record
sanitized assertions in Git only; preserve screenshots, exact strings, source
hashes, response bodies and identities in the private evidence directory. Never
put a bearer, App Check token, signed URL or object path into a command/log.

| Required case | Execute and assert | Coverage / present evidence |
|---|---|---|
| UI-SIGN-IN | Sign in with the assigned verified identity; assert actual production session and collection role; unverified/no-role identities cannot mount workspace. | One authorized session plus denial controls; local auth/verification/HTTP widgets pass; **Not run live** |
| UI-INTAKE | Intake only approved original bytes through the normal UI, or inspect a previously imported approved record when duplicate detection applies. Match immutable original hash/size and server receipt. Replaying upload must not create a second specimen. | All ten; local resume/replay HTTP test; **Not run live** |
| UI-PROCESSING | Observe server job state and retained run, then bounded actual model results or explicit reasoned block. Exhausted output/cost limits must not become accepted truncated text. No client-invented completion. | All ten; local state/unknown-effect controls; **Not run live** |
| UI-IMAGE-REGIONS | Open original image, select each label region, inspect its crop/geometry and linked independent readings; verify original/crop digests and image coordinates. Use keyboard/touch controls where available. | All ten; local geometry/region/evidence tests; **Not run live** |
| UI-LITERAL-UNCERTAINTY | Compare displayed exact literal text with private retained reader output and source, preserving punctuation, line breaks and uncertainty. Unknown/unreadable values stay explicit; no inferred mandatory value or zero-risk score. | All ten; local alignment/risk/declaration tests; **Not run live** |
| UI-SAVE-REOPEN | Make an allowed evidence correction with reason, save, refresh and sign out/in, then reopen from server. Verify revision increment, exact correction and unchanged raw observations. A stale concurrent save must conflict without overwriting either version. | All ten; separate-process Flutter correction/reopen and local conflict probe; **Not run live** |
| UI-SEARCH-QUEUE | Search a retained known literal/corrected value, exercise queue filters and paging, open each intended specimen and verify scope/no duplicates. Include a no-result positive control. | All ten; local queue/paging/wire tests; **Not run live** |
| UI-PROVENANCE-HISTORY | Open saved history and historical record, verify original/run/model/prompt/crop lineage and correction reason. Reopen after authorized API/worker restart and verify raw bytes and history survive. | All ten; local audit/graph/history tests, app recreation only in local probe; **Not run live** |
| UI-DENIAL-RECOVERY | With separate authorized denial fixtures, demonstrate unauthenticated, cross-organization/collection, viewer-write and revoked access fail without content. Deny image/history/intake after successful session; stale responses cannot restore access. Reverify access explicitly. | Denial controls and authorized positive control; local HTTP/widget tests; **Not run live** |
| UI-NO-SYNTHETIC-FALLBACK | Interrupt the approved API connection or force a controlled provider failure. UI must show failure/blocked state with no fixture records, fabricated transcript, implicit retries of ambiguous effects, or false clearance. Restore connection and reopen retained server state. | Controlled authorized failure target; local config/mode and recovery tests; **Not run live** |

Use a disposable authorized failure target for denial/restart/fault injection.
Do not revoke a real user's role, stop production services, upload new sample
material or force paid retries merely because this checklist names a test.
Those actions require the coordinator's concrete execution plan. No direct SQL
repair is permitted inside a user journey to manufacture success.

The current evidence-only pilot can honestly remain `processing_blocked` with
`pilot_evidence_review_required`, unmeasured risk and null disposition after
allowed transcription/field/reading-metadata/coverage edits. It must retain raw
observations, prevent geometry-triggered inference and deny approval/clearance.
This is reviewable evidence, not institutional quality qualification. The broader
20 PRD criteria remain pending when those requirements have not been observed.

## Shared cost evidence contract

The ledger's `budget` uses `cohort-budget/v1`, USD, the same frozen manifest SHA,
private authorization reference and scope
`entire_first_ten_all_sessions_and_retries`. Total/daily limits are positive
integer micro-USD, at most `5000000`; daily cannot exceed total. There is no
per-session reset. `mode` separates fixture/emulator/owner_report/live evidence.

Require all eleven categories: provider, api, worker, sam, build, storage,
network, restore, identity (Authentication and App Check), secrets (Secret
Manager), telemetry (logging/monitoring). Each must have `reconciled: true` and
an artifact list with relative path plus SHA-256. Zero incremental cost also
needs retained supporting evidence; existing baseline costs must be distinguished
privately from attributable incremental test costs.

`entries` retains unique operation IDs across the entire cohort, each with
category, ISO UTC day, `settled`, `reserved` or `unknown` state, and nonnegative
integer `amount_microusd`. Settled entries carry actual cost; reserved/unknown
entries carry a conservative upper bound. Unknown effects require a positive
reservation. The checker sums every entry across all days, then checks each day.
Changing day or session cannot reset the cumulative total. Do not double-count a
settled operation as a second reservation or drop an unresolved effect. Retain
underlying event history privately so an independent reviewer can reconcile it.

This is an **offline evidence check**, not an account spending limiter. The runtime
owner must enforce reservations before real work; an independent reviewer must
check that all operations/categories are present and prices/receipts are real.
A fabricated but internally consistent ledger cannot establish observed behavior.
Every output therefore keeps `release_accepted: false`, including structurally
complete reports. Never use an empty/synthetic packet as release permission.

## Validation ledger

- Existing acceptance/probe tests: **57 passed**, baseline before changes.
- TDD first actual red: **31 failed** for missing journey cases/budget validation;
  `/tmp/specimen-ac0d-acceptance-red.log`. The earlier uv cache EPERM was an
  environment failure before test execution and is not counted as a red test.
- Green focused acceptance regression: **88 passed** after initial implementation.
  Added follow-up red for unknown-effect zero reservation; final totals below.
- Flutter analysis: no issues. Full widget/HTTP regression: **120 passed / 7 skipped**;
  `/tmp/specimen-ac0d-flutter-tests.log`. The opt-in skips are not live proof.
- Independent synthetic local HTTP/SQLite probe: **24 checks passed**;
  `/tmp/specimen-ac0d-local-probe-20260908.json`. App recreation in one process,
  not Cloud SQL durability or worker process restart. No external providers.
- Separate API process plus opt-in Flutter HTTP journey and canonical verification:
  final executed results are appended below before handoff.

Tools/environment failures: Git branch creation and uv/Flutter caches needed
approved access to shared paths; no denied action was worked around. Public tab
creation waited about 29 minutes before returning. A temporary HTTP evidence
parser initially rejected a JSON list event; the parser was repaired and the
journey rerun. None of these failures are product acceptance passes.

## Handoff and follow-ups

Coordinator independently reviews this scoped harness diff, integrates reviewed
commits, and owns PR/push/merge, runtime/data policy, actual cloud execution and
public final acceptance. No change here authorizes deployment or cohort expansion.
Preserve ignored evidence and historical reports. No worktree/branch was pruned.
A final combined SHA requires new evidence; do not relabel this baseline's local
results with the merged production identity. The offline checker remains
insufficient to declare the product live even when every local check is green.


## Final local verification and independent runtime review

Final acceptance suite: **92 passed** in
`/tmp/specimen-ac0d-acceptance-final.log`. Canonical `scripts/ci/verify.sh` exited
0 with **816 Python passed / 26 skipped**, **120 Flutter passed / 7 skipped**,
clean analysis, repository/security checks and release web build (22.9 seconds).
Log: `/tmp/specimen-ac0d-canonical-20260908.log`. Staged-file hooks were rerun
so newly added files were included in sensitive-file and secret checks.

The separate-process HTTP test executed **1 test, no skips**, passing the existing
Flutter intake, upload restart/resume, processing, evidence, correction, stale
conflict, unreadable transcript and reopen journey against a fresh local
synthetic API on an ephemeral loopback port. The temporary driver preserved
result and machine events under
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-ac0d-http-e5m8b4yt`.
The process was terminated after testing. It used zero cloud specimens/provider
calls and does not establish browser/Firebase/production acceptance.

Independent review requested by coordinator: runtime implementation
`87117c2067cef01c093fc6e99e2af670d7d93e7e`, report/closeout
`6a9420c80d185850a3665b2b4e27ccc0b181c3ab`, clean owner worktree 7471. Reviewed
SAM daemon expiry/cancel-on-exit fix and explicit parsed Hub offline flag.
Independently ran `tests/test_sam3_lifecycle.py tests/test_sam3_server.py`: **29
passed**, including actual process exit after startup failure/server return and
SIGTERM during a stuck handler. Log:
`/tmp/specimen-ac0d-runtime-review-20260908.log`. No actionable defect found in
this scoped diff. These tests inject model/cloud boundaries. The owner's real
local SAM result exceeded the 120-second serving deadline (132.388 seconds on
emulated AMD64); native target timing remains a launch gate. It has zero cohort
credit and was not rerun here. No mask-quality or production-serving claim is
inferred from lifecycle tests.

## Follow-up runtime budget and persistence review

Reviewed runtime stage-cost/offline candidate
`24e6550a10b6cc02d0dd319ada22c2bff9c54885`. Initial independent suite passed
86 tests; an additional direct old/new serializer comparison confirmed absent
stage maps preserve exact default/nondefault policy and concrete ten-source
launch JSON/digests. New mapped stage costs reserve before effects, retain full
known retries and unknown liabilities, and cannot reset the cohort ledger.
Offline SAM requires the approved checkpoint digest before loading model files.

A subsequent transport review found a blocker: genuine protobuf Struct changed
integer costs to `17.0`-style numbers. The production SQL snapshot reader accepted
the canonical digest and then rejected all three strict stage-cost values.
This was reproduced through `SqlConnectRepository._snapshot`; no real SQL/cloud
request was made. The initial candidate review pass was withdrawn pending repair.

Runtime correction `d859ac6dfa9c64d7fb68037da03283b823303736` normalizes only
positive exact safe integer-valued floats under explicit persisted-snapshot
validation context. Direct config still rejects floats, booleans, strings,
fractions and unsafe integers. It copies the cost map; it does not alter receipt
bytes or digest validation. Independently reviewed this correction and ran stage
costs, SAM lifecycle/server, worker launch, evidence pilot and active graph tests:
**103 passed / 1 opt-in skipped**, 3 existing warnings, exit 0 in 16.64 seconds.
Log: `/tmp/specimen-ac0d-runtime-persistence-review-20260908.log`.
No blocking scoped finding remains in these two commits. The skipped real SQL
integration is not proof of deployed connector behavior.

Delivery must provision the identical approved map in each retained run policy
and the launch; the worker deliberately rejects mismatches. It must supply
`SPECIMEN_SAM3_CHECKPOINT_SHA256` and the offline cache, enforce the shared full
USD 5 budget, and qualify native SAM timing. No real model, image, cloud or paid
call was made during this independent follow-up. Runtime owner canonical checks
and exact integrated release checks remain separate from this focused review.

## Approved human-review release projection

The user explicitly selected complete human review of all ten specimens, with
only automated classification and automated clearance deferred. The coordinator
approved the concrete mapping below. Authority is the private
`human-review-release-scope-v1.json`, SHA-256
`14f6b1140f7d45e46c022e4a1c4f60cd775bafbef73ca363a677f278e0eafd1a`.
This decision changes acceptance scope; it does not qualify any unexecuted PRD
criterion, expand infrastructure authority, raise the USD 5 cap, grant sensitive
access or change the ten-source denominator.

`scripts/qa/live/human_review.py` is a separate projection over the unchanged
45-case full gate. It requires **every existing ten UI and fifteen live case**,
plus these four manual subcriteria. Generic blocked/not-run/failed/non-live rows
remain pending. A row cannot declare itself deferred. Full-PRD rows and their
actual statuses remain present and are reported separately; no entire mixed PRD
row is silently treated as passed or deferred.

| Manual subcriterion | PRD relation and required evidence |
|---|---|
| HUMAN-LABEL-COVERAGE | PRD-04/05/12: review the whole original and all regions, compare two readings of every required label and explicitly confirm coverage. Missing/inaccurate or omitted label coverage keeps the human journey incomplete until addressed. No region/specimen may be removed to fit budget. |
| HUMAN-FIELD-SEPARATION | PRD-07/16: preserve literal output separately from human field corrections/normalized values and trace each claimed value to retained source/reading/review evidence. Missing authority/normalization remains explicit; no invented derivation chain. |
| HUMAN-NO-AUTOMATIC-CLEARANCE | PRD-10/11/14/15: correction/save does not enable automatic clearance, approve institutional semantics/risk, or mislabel an operational failure as Deferred. Exercise denial controls with unresolved mandatory values and verify review state/history survive. |
| HUMAN-ACCESSIBLE-REVIEW | Manual portion of PRD-19: execute keyboard/focus/error recovery, image/region navigation, text-based uncertainty and save/reopen in the actual public review UI. This does not claim institutional quality thresholds are approved. |

The existing UI/live cases cover intake/immutability, authentic sign-in and scope,
actual processing, literal comparisons/uncertainty, correction/save/readback,
search/queue, provenance/history, denial, recovery/restart/restore and budget.
Automated PRD-03 and the automated/institutional portions of mixed criteria stay
at their actual full-PRD status. In particular, PRD-04/07/08/10/11/14/15/16/17/19/20
are not wholesale waived. `full_prd_qualified` and `release_accepted` remain false
in every human-checker output. Only the coordinator's independent actual release
review may make a release decision for the approved human scope.

### Retained record evidence

The report retains the original 45 `results`, `deployment` and cumulative
`budget`, adding `scope_sha256`, four `human_results` with the same evidence-row
fields, and `human_records`. Empty records are pending; a partially supplied
record list cannot become complete. A complete list has exactly the frozen ten
unique specimen IDs, each with:

- `original`: artifact descriptor for the approved original bytes.
- `before_review`, `after_save`, `after_reload`: separate artifact descriptors
  for actual API workspace JSON, captured at the named milestones. Preserve
  the private original response, not a reconstructed summary or direct DB edit.
- `sam_receipt`: the retained SAM response JSON, including source generation,
  manifest/model/checkpoint pins, checkpoint file map, original regions and masks.
- `raw_observations`: map from each observation ID to its retained raw response
  artifact. `crops`: the corresponding map to exact reader input crop bytes.
- `masks`: map from each retained region ID to its mask-byte artifact.

All artifact descriptors use paths relative to the private evidence directory
plus SHA-256 over exact retained bytes. The checker verifies original/scope
bindings; SAM receipt and model config/checkpoint-file hashes; every retained
region/mask/crop; exact Qwen/Novita and Muse/DeepInfra route pairs; validated,
non-truncated literal outputs reconstructed from the retained final raw response;
exact uncertainty; unchanged raw readings/regions across edits; a new reasoned
review event, coverage confirmation, advanced revision/version and equal saved
versus reopened state. `sam_config_sha256` is the checkpoint's `config.json`
SHA-256; `sam_checkpoint_sha256` hashes its canonical file-name/hash map.
Both the deployment and every retained SAM region must use the existing approved
`SAM3_MODEL.revision`, with region method `sam3`; mutual agreement on a different
revision cannot qualify. JSON evidence is parsed from the same bounded bytes
whose SHA-256 was checked, so a file replacement between reads is rejected.

The current pilot intentionally retains `processing_blocked` with
`pilot_evidence_review_required`, false institutional/human approval flags and
null disposition. This is eligible for human evidence checking **only after**
actual SAM and both validated readers exist for every retained region and the
human review/save/reload checks pass. A cost/provider/output-limit failure, empty
result, incomplete reading pair or setup screen cannot qualify.

Raw response artifacts preserve provider responses without image-bearing request
messages. The independent PROVIDER-ACTUAL case must also verify the real blind
request path; hashes/declared route names alone cannot prove independence or that
an external call occurred. This checker establishes retained-byte consistency,
not authenticity, model quality, billing completeness or production availability.
All sensitive artifacts and receipts remain outside Git.

### Execution and evidence states

Use the explicit commands in `scripts/qa/live/README.md`. The scope file is owned
by the current user, mode 0600, outside Git and verified against the exact approved
hash. Template generation is explicitly `human_review_preflight: not_run` and
cannot count as execution. Checking exits 0 only for evidence ready for independent
review, 1 for pending requirements and 2 for invalid/tampered evidence. Both scope
verdicts remain visible. A merged candidate needs fresh candidate-bound evidence.

TDD: initial **35 failures / 6 passes** reproduced the full-gate-only gap;
follow-ups each reproduced two failures for scope/crop completeness, optional
uncertainty/template-state handling, and new review-event/run identity. These are
local authored fixtures, not actual first-ten outcomes. Logs:
`/tmp/specimen-ac0d-human-review-red.log`,
`/tmp/specimen-ac0d-human-artifacts-red.log`,
`/tmp/specimen-ac0d-human-defaults-red.log`,
`/tmp/specimen-ac0d-human-save-red.log`. Final scoped/canonical results are
recorded below before handoff. No model, route, cloud or Flutter behavior changed.

The independent coordinator review confirmed a JSON hash/parse race and requested
approved SAM revision binding. Both now have regressions: one byte-swap failure
and three unapproved revision/method failures, respectively, before fixes.
Logs `/tmp/specimen-ac0d-human-byte-race-red.log` and
`/tmp/specimen-ac0d-human-sam-pin-red.log`. A first canonical attempt stopped at
the secret scanner's classification of a public decision digest. The source now
derives the identical digest from the readable canonical approved decision; no
scanner rule or allowlist was changed. The next canonical passed 870 Python /
26 skips, 120 Flutter / 7 skips and release web build in 20.2 seconds; this was
before the final three SAM binding regressions. Final exact-source validation
follows below.

## Independent explicit-sensitivity runtime review

Reviewed runtime implementation `e7f4985064c5b6a778b556852c0e4d0d247f456d`,
owner documentation tip `61c525142f6f7b33c26ac0cfc26622074aeec360` in clean
worktree 7471. Batch/item flags are strict booleans defaulting to sensitive;
items must match the retained batch. Explicit false persists into the asset,
SQL mutation metadata and optional pilot ledger. Legacy omissions remain
sensitive without changing their canonical payloads/digests. Repository guards
reject downgrades, and current/historical/image/graph/artifact access checks the
selected asset's classification and current membership.

Independent focused execution: **109 passed**, 3 existing warnings, exit 0 in
7.47 seconds. Log `/tmp/specimen-ac0d-sensitivity-review-20260908.log`. Also
loaded the actual parent Git versions of Asset and PilotLaunch and compared
their serialized values and digests with the candidate on a concrete authored
ten-source launch; both matched. No blocking scoped source finding remains.
These checks use local SQLite/ASGI and injected SQL boundaries; deployed V2
connector behavior and actual first-ten sensitivity are **Not confirmed** by
this review. Initial admin sensitive permission remains false. No real images,
models, cloud resources or paid calls were used, and no deployment was made.

### Final local validation of the human projection

All **149 focused tests passed**, including the byte-swap and three SAM binding
regressions. Final canonical `scripts/ci/verify.sh` exited 0: **873 Python passed /
26 skipped**, **120 Flutter passed / 7 skipped**, static analysis, all repository
and security hooks, and release web build passed. Logs:
`/tmp/specimen-ac0d-human-final-focused-20260908.log` and
`/tmp/specimen-ac0d-human-final-canonical-20260908.log`.
The existing full-gate implementation and Flutter source are unchanged in this
commit. Coordinator confirmation of the final source-review repairs, integration
with runtime/data/client changes and actual candidate-bound live evidence remain
separate follow-ups. These local passes do not change either release verdict.

### Final coordinator-requested bounded-read and strict-JSON follow-up

After commit `3dbd834`, coordinator source review accepted the byte-integrity and
SAM pin repairs and requested two contract corrections. JSON artifacts now open
once with no-follow/nonblocking flags, require the opened descriptor to be a
regular file, and read at most 16 MiB plus one byte before rejecting oversize
input. The same consumed bytes are hashed and parsed. Shared descriptor/path
validation is factored without changing its existing restrictions. Shared JSON
parsing now rejects the non-JSON constants `NaN`, `Infinity` and `-Infinity` as
well as duplicate keys. Valid evidence and the full gate's case/status rules are
unchanged.

Five actual regressions failed before repairs; final focused suite **154 passed**
with one existing warning in 2.11 seconds. Logs:
`/tmp/specimen-ac0d-human-bounded-strict-red-20260908.log` and
`/tmp/specimen-ac0d-human-bounded-strict-green-20260908.log`.
An interim test wrapper instrumented the same stream twice through `os.fdopen`
and `io.open`, producing one false test failure; the instrument now wraps each
stream once. An early green message sent before inspecting that output was
immediately withdrawn and corrected. Final canonical results follow below.

Coordinator independently reviewed the final bounded descriptor, strict JSON,
same-byte parsing and approved SAM deployment/region checks and reported no
remaining source finding. Integration is to carry `3dbd834` and this follow-up
together. This source-review pass does not authenticate any live evidence.

Final required canonical validation exited 0: **878 Python passed / 26 skipped**,
**120 Flutter passed / 7 skipped**, static analysis, all repository/security
hooks and release web build (19.9 seconds) passed. Log:
`/tmp/specimen-ac0d-human-bounded-strict-canonical-20260908.log`.
No further source changes or repeat testing are required for this scoped handoff.
