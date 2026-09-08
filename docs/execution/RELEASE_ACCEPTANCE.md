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
