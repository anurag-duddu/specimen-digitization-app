# Production release plan and coordination

Owner: task `01a082b2-c2c3-70d2-be90-7bfb622c9102`, branch `codex/cohort-budget-admission`, canonical
checkout. Started 2026-09-08. Status: active implementation and qualification;
end-to-end production acceptance is **Not confirmed**.

The user requested a complete live product using actual data, test-driven
development, multiple sessions, and active orchestration through release. This
plan coordinates that work. Historical owner reports remain evidence of their
recorded commits; their old merge restrictions and statuses are not current Git
state. Existing deployment protections and the frozen ten-specimen limit remain.

## Outcome and scope

At <https://specimen-digitization.web.app>, the authorized administrator can
sign in, access the intended collection, inspect/import the approved originals,
start bounded real processing, inspect image regions and independent readings,
correct evidence, save, reload, search and reopen persisted review records with
their original images and versioned history. Restarting the API or worker must
preserve state and must not repeat an ambiguous external effect.

The first acceptance cohort is exactly the previously authorized first ten
existing cloud specimens, with every associated source object generation and
digest frozen privately before image reads. No substitutes or expansion. An
honest review-required or blocked quality disposition is valid; fabricated text,
synthetic production output, invented mandatory values and automatic clearance
without an approved profile are failures. The human-review first release is
explicitly approved in [HUMAN_REVIEW_RELEASE.md](HUMAN_REVIEW_RELEASE.md).
Automated classification and clearance are deferred; real processing, comparison,
corrections and persisted review for all ten remain required. Evidence must not
be reported as fully qualified automatic processing.
EMu writes, universal collection support, institutional quality approval, and
signed mobile distribution are outside this release's first-ten acceptance.

## Confirmed starting point

- Local `V0.1`, `main` and `origin/main` point at
  `61d82aed64816802cd6ac00ac11e307a30c2bd8e`; working tree was clean.
- GitHub reports no open pull requests. All six jobs, including Hosting, passed
  in [run 34272730878](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34272730878).
- The coordinator reran `scripts/ci/smoke_hosting.sh` against that SHA; the public
  page title and deployment marker passed. This proves static delivery only.
- Public API/App Check repository variables are absent. Production product
  acceptance and backend/data availability remain **Not confirmed**.
- Main has strict required checks, enforced administrators, required PRs and
  disabled force pushes/deletion. These protections will be retained.
- Prior private decisions contain the administrator and ten-specimen scope;
  the budget was not supplied at the starting checkpoint. The user subsequently
  supplied a USD 5 total ceiling, recorded below. No private values are reproduced
  here. The earlier rollout heartbeat is paused.
- Fresh noninteractive `gcloud projects describe specimen-digitization` failed
  because the current credentials require interactive reauthentication. No
  account/project switch, API enablement, resource write or image read occurred.
  This is an observed access gate, not evidence that cloud resources are absent.

## Sessions, agents, models and ownership

Use the Codex app's existing task/worktree harness. Each implementation session
has its own checkout and explicit owned files. Session creation inherits the
configured default, observed as `gpt-6-astra` with `xhigh` reasoning on this host;
no model override or separate API key was introduced. All three actual session
turn contexts confirm these settings. Do not confuse coding agents with product
inference models.

| Session | Agent responsibility | Owned work and TODOs | Completion evidence |
|---|---|---|---|
| This coordinator | Release lead and integrator | Reconcile prior work; maintain plan/decisions; resolve interfaces; review precise release amendment and resource plan; integrate reviewed commits; run complete gates; PR/merge/CI/public verification | Exact integrated SHA, PR/check/deploy URLs, independent acceptance verdict |
| Release: runtime and model processing | Backend and processing engineer | Audit API/auth/storage/worker path; reuse preserved real-model work; reproduce runtime blockers with failing tests; fix; qualify startup/health/version/drain and durable effects | Red/green logs, runtime/config contract, model provenance and real-vs-synthetic evidence in `RELEASE_RUNTIME.md` |
| Release: data and cloud readiness | Data/platform engineer | Revalidate Google access read-only; inventory exact resources; freeze first ten; prepare import/admin/backup/restore/IAM/cost plan; repair data defects with TDD | Manifest fingerprints, restore/integrity evidence, exact action list and `RELEASE_DATA.md` |
| Release: product journey and acceptance | Client engineer and acceptance lead | Audit public app; test sign-in/intake/processing/review/save/reopen/search; fix Flutter defects using TDD; extend executable acceptance and denial/recovery checks | Browser/HTTP evidence, genuine executed-vs-skipped counts and `RELEASE_ACCEPTANCE.md` |

Confirmed session registry (each starts at `61d82ae` in an isolated worktree):

| Owner | Task ID | Worktree |
|---|---|---|
| Runtime | `01a082b4-a9bd-7392-a73b-57ca45532fb7` | `/Users/anuragduddu/.codex/worktrees/7471/specimen-digitization-app` |
| Data | `01a082b4-a9bc-7413-a3c5-505b61c2f4db` | `/Users/anuragduddu/.codex/worktrees/4a25/specimen-digitization-app` |
| Acceptance | `01a082b4-a9bc-7413-a3c5-5077dd5c3a9f` | `/Users/anuragduddu/.codex/worktrees/ac0d/specimen-digitization-app` |

`list_threads` omitted these workstream tasks; explicit `read_thread` and
`wait_threads` confirmed their active state. Use those IDs for coordination.
Worktree isolation follows the [official Codex worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees).

The coordinator provides independent review of acceptance-code changes; the
acceptance session independently checks runtime/data/integrated outputs. A
session's own passing tests do not constitute independent final acceptance.
Use a further bounded reviewer only if these ownership boundaries cannot supply
an independent review. No uncontrolled recursive delegation.

## Orchestration protocol

1. Each owner sends an early gap report with task/worktree/model, confirmed
   findings, ordered TODOs, dependencies, and precise missing inputs.
2. Send interface changes to this coordinator before cross-owner edits. API and
   client agree payloads and auth headers; data and runtime agree frozen manifest,
   scope and storage references; delivery consumes exact configuration contracts.
3. Use statuses `Pending`, `In progress`, `Blocked`, `Ready for review`,
   `Verified`, and `Not confirmed`. Every verified statement names source SHA,
   command, environment and evidence location. A skipped test is never a pass.
4. Owner handoff includes failing-test evidence, fix commit, passing tests,
   remaining risks, and an append-only `docs/SESSION_LEARNINGS.md` entry.
5. Coordinator reviews diffs and dependencies before integration. Only the
   coordinator controls merge/deployment order. Do not overwrite user work,
   rebase a running owner's checkout, or archive/prune evidence dependencies.
6. Collect decisions here or in private decision artifacts as appropriate.
   Ask the user only for missing authority, budget, identity or unavailable
   domain facts. Continue independent authorized work while awaiting replies.
7. Check actual session status at handoffs; creation requests and green wrapper
   jobs do not establish implementation or release completion. Use event waits
   and substantive updates, not duplicate work or blind repeated polling.

## Test-driven development and harness

For every behavioral defect or new behavior: specify observable acceptance;
write/run a minimal regression that fails for the intended reason; implement the
smallest correct change; run it green; refactor if useful; run relevant boundary
and integration coverage. Record commands and red/green outcomes. Do not weaken
security assertions, skip failing tests, or invent tests for document edits.

| Layer | Harness | What must be proved |
|---|---|---|
| Domain/API/worker | Locked `uv`, pytest, process/HTTP failure injection | Scope/auth denial, original/hash binding, valid state changes, concurrency/CAS, provider error/timeout/unknown-effect handling |
| Data | Existing isolated PostgreSQL/SQL Connect and Storage emulator scripts | Persistence, membership bootstrap isolation, generations, migrations, supplemental indexes, backup/restore/reconstruction |
| Client | Flutter analysis, widget and HTTP integration suites, browser UI | Verified identity, actionable setup/errors, real requests, save/reopen/history, access revocation, no stale or synthetic fallback |
| Model evidence | Pydantic AI and strict schemas; immutable SAM model artifacts; existing pilot/launch/evidence harness | Two independent readings, literal transcript preservation, raw/crop/model/prompt provenance, uncertainty, durable bounded budgets |
| Release | Existing context/packet/readiness validators and protected GitHub CI | Exact source, immutable image/build provenance, complete independently verified inputs, correct workflow/environment identity |
| Live acceptance | `scripts/qa/live` plus actual authenticated public browser/API | Real Google tokens, first-ten manifest, real model calls, persisted readback/restart, denials and final user journey |

Retain the explicit HF routes Qwen/Novita and Muse/DeepInfra and pinned SAM model;
reverify route access, rates, artifact revisions and compatibility before paid
execution. The bounded SQL-checkpoint worker is the existing pilot candidate.
Do not provision Temporal or claim the incomplete Workflows comparison is passed.

## Release sequence and gates

| Gate | Required work and exit evidence | Current state |
|---|---|---|
| G0 Baseline | Live Git/GitHub/marker reconciliation and safe work ownership | Verified for starting SHA above |
| G1 Candidate | Owner audits, TDD repairs, independent review, exact interface/config contracts | PRs 15–19 reviewed and integrated. Catalog credential-mode compatibility and safe diagnostics passed TDD, independent review, full Python3.12/Flutter verification and all five protected platform checks. Actual managed-service qualification remains pending |
| G2 Access and scope | Working Google authentication, verified admin, generation-frozen ten-source manifest and allowed provider use | All ten local originals match frozen cloud size/MD5/CRC metadata; SHA256 and local review complete. Coordinator accepted non-sensitive intake for these ten only. Existing email/password Auth retained; verified admin remains pending |
| G3 Authority and cost | Reviewed release-policy amendment, precise resource/IAM/config plan, one cumulative budget and hard execution bounds | Infrastructure authority granted; USD 5 remains shared across all sessions/days/retries. Prior uncertainty and bounded metering are explicitly reserved; eight native aggregate reads are complete. Independent review supports the next bounded catalog read within the cumulative cap, pending truthful operator-ledger admission and source gates. Organization reCAPTCHA usage remains a later assessment gate |
| G4 Protected delivery implementation | Approved separate data/runtime workflows with negative policy tests, least-privilege keyless identities and immutable provenance | Separate workflows merged; backend environments verified main-only. All five providers and ten service accounts exist. Four exact immutable subject repairs and three matching WIF-to-account bindings are natively verified, preserving Hosting and unrelated policies. Scoped image/workload permissions, native SQL qualification and current admission inputs remain pending |
| G5 Protected source release | Integrated `scripts/ci/verify.sh`, runtime container CI, independent review and all five platform checks on exact PR head; merge through GitHub; green exact-main CI/Hosting | PR19 merged as `c2a5ce897e344cb5952cdfaf51aae0747dfe5dde`; main CI34334300400 all five checks and Hosting passed. Matching public marker, root smoke and fresh browser inspected; product acceptance remains pending |
| G6 Data readiness | Cloud backup and isolated restore, compatible schema/connector/rules, exact indexes, scoped admin/import and independent readback through the protected data workflow | Pending G2/G3/G5 |
| G7 Runtime readiness | Built-once API/worker/SAM digests, real model-loaded health, Google auth/App Check/denials, frozen inputs, safe stop/restart through the protected runtime workflow | Pending G6 and verified runtime admission |
| G8 Public acceptance | Green main deploy, exact public marker, matching runtime/data revisions, actual ten-source processing/review/save/reopen and recovery | Not accepted: fresh public browser shows Collection connection required and API not configured; real ten-source processing and review are pending |
| G9 Closeout | Record complete release receipt, limitations, stop/rollback instructions and append-only learnings; preserve evidence before pruning | Pending G8 |

Use local synthetic fixtures to develop tests, then real isolated data/services,
then the authorized first-ten live cohort. These are separate evidence levels.
Do not use private data or paid inference inside ordinary pull-request CI.

The source merge necessarily precedes data/runtime deployment; cloud readiness
must not be required to create the workflow that establishes it. Each effect
still requires its own verified admission. Once actual main-push run IDs and
attempts exist, bind reviewed private inputs to those identities and the shared
cumulative ledger. A rerun of that original main-push workflow may consume newly
verified inputs; it must reserve previous unknown or incurred costs and the new
attempt together. It must not introduce another trigger or silently replay an
effect. Data readiness precedes runtime activation. If verified API/App Check
public settings require a subsequent client build, use another protected PR and
main Hosting deployment, then reconcile the source and data/runtime compatibility
before public acceptance. A static Hosting deploy during this sequence is only
an intermediate milestone.

## Approved release-policy decision

The user submitted both decisions in release decision packet v1: protected
backend/data deployment workflows and the bounded Google Cloud setup. The
authoritative scope is now recorded in
[RELEASE_AUTHORIZATION.md](RELEASE_AUTHORIZATION.md), with a private copy and
digest alongside the execution decisions. These approvals are no longer missing.
`AGENTS.md` and `docs/DEPLOYMENT.md` are being amended through the release PR.

Approved replacement for the first deployment rule:

> Hosting production deployments MUST use `.github/workflows/ci-cd.yml` after
> a pull request is merged to `main`. Runtime and data production changes MUST
> use only `.github/workflows/runtime-release.yml` and
> `.github/workflows/data-release.yml`, respectively, after a pull request is
> merged to `main` and the reviewed LIVE_DELIVERY contract is met. Each uses a
> separate main-only environment and keyless identity, all required checks on
> the exact merged source, and independently verified release evidence. Missing
> authorization or evidence fails closed. Workstation/manual deployments and
> changes to the Hosting identity's privileges remain forbidden.

Review the matching runbook and negative tests with that change. Preserve pinned
actions, required checks, branch protection, environment restrictions and
Hosting isolation. The separately approved bounded resource/IAM scope allows
routine names/configuration to be resolved by the coordinator after live
inventory and independent review. Record the exact action packet before action;
do not expand scope or infer an unverified cost as zero.

The resource design being reconciled is the existing `LIVE_PILOT_COST.md`:
one scale-to-zero API, one bounded worker execution, one CPU SAM service, existing
SQL/Storage, three immutable images, and one temporary restore clone. Its compute
illustration is **not** a complete quote or enforceable account cost cap. Obtain
current metadata and conservative model reservations; fail closed if an approved
budget cannot be enforced. Keep the previous stable revisions for rollback;
quiesce workers and retain evidence on failure. No destructive database rollback.

## Decision log

- 2026-09-08: User requests complete production release, TDD and multiple
  coordinated sessions. Implementation and normal protected release are in scope.
- 2026-09-08: Reuse existing platform and ten-specimen cohort. Do not replace
  prior work or expand the sample to make acceptance easier.
- 2026-09-08: Three specialist sessions requested in isolated worktrees; model
  setting inherited from host default. Coordinator owns release integration.
- 2026-09-08: Total/daily pilot budget requested; no value supplied at this
  checkpoint. Runtime/data policy amendment awaits explicit resolution.
- 2026-09-08: Exact amendment requested for approval through the conversation;
  no policy change or additional deployment path has been applied.
- 2026-09-08: Old retained worktrees are dependencies until new owners reconcile
  their ignored evidence and unfinished work. Cleanup coordinator notified.
- 2026-09-08 later: User expects the entire first-ten app/pipeline/agents/harness
  test comfortably below USD 5. Treat USD 5 as the maximum total incremental
  test spend across all sessions/retries/days, with the same daily maximum and
  no reset. Target at most USD 4 ordinary reservations plus USD 1 contingency.
  Updated `LIVE_PILOT_COST.md` and private decisions; budget is no longer missing.
- 2026-09-08 later: Coordinator owns a narrow TDD repair in `reliability.py`
  after demonstrating that aggregate token checks did not set a provider output
  cap. Default per-request generation is now capped at 4,096 tokens, preserving
  stricter agent/usage limits; both initial and schema retry requests are covered.
  Existing production subprocess regression checks both transcription and
  extraction. Runtime owner notified to avoid overlapping edits. Independent
  review assigned to the bounded `budget_guard_review` subagent.
- 2026-09-08 later: Independent review reproduced underlying-model, dynamic
  settings and remaining-retry allowance defects in the first repair. Added
  failing regressions and corrected all three with a per-request settings
  resolver. Final independent review passed eight tests and an offline genuine
  Hugging Face transport check (caps 20 then 12 after eight output tokens).
- 2026-09-08 later: Started reauthentication for the existing Google account;
  the CLI is waiting for account-owner password entry in its terminal. No
  password is requested in chat, account switched or cloud resource changed.
- 2026-09-08 decision packet v1: User submitted both approvals. Recorded protected
  workflow and bounded setup authority in `RELEASE_AUTHORIZATION.md` and the
  private decision artifact. Stop requesting those approvals; discover identity,
  source, resource, price and readiness facts after authentication.
- 2026-09-08 after approval: Cancelled the idle terminal-password flow and opened
  a fresh browser authorization flow for the same existing Google account.
  Successful Google sign-in remains Not confirmed; the old terminal is no longer
  the action to complete.
- 2026-09-08 after approval: Added bounded helper agent
  `/root/protected_release_delivery` on coordinator branch `V0.1`, inheriting the
  coordinator model/effort. It owns the two workflows and their executable
  admission/build/apply tests while root owns policy, integration and reviews.
  It has no cloud-write, paid-call, GitHub-admin, push or deploy authority.
  Existing `/root/budget_guard_review` independently reviews data repairs.
- 2026-09-08 first-release scope: After discovery of missing institutional
  profile/clearance configuration, the user selected complete human review of
  all ten and explicitly deferred automated classification and clearance.
  [HUMAN_REVIEW_RELEASE.md](HUMAN_REVIEW_RELEASE.md) records the exact choice and
  private artifact digest. No infrastructure, cohort or spending limit changed.
  Acceptance preserves full-PRD status separately from the approved human-review
  release; actual processing and saved/reopened evidence are still mandatory.
- 2026-09-08 access update: Newly available Firebase MCP successfully read the
  correct live project. The existing same-account Firebase CLI credential then
  completed all twelve read-only metadata inventory queries using a temporary
  private short-lived access-token file and explicit per-command authentication.
  No global gcloud account/project changed; the token file was removed and the
  unused browser gcloud login cancelled. No further Google login is required for
  this observed metadata access. Effective release/runtime IAM remains unverified.
- 2026-09-08 identity update: Exact approved-email lookup returned no matching
  Firebase Auth user. No UID, account or membership was invented. The first
  administrator must sign into the configured application before verified
  bootstrap; this is distinct from the working cloud-administration connection.

## Validation and next checkpoint

- Coordinator targeted gate: `uv run pytest -q tests/test_deployment_policy.py
  scripts/ci/test_release_context.py scripts/ci/test_release_packet.py
  scripts/ci/test_release_readiness.py scripts/ci/test_public_settings.py`:
  **87 passed**. Existing policy remains unchanged.
- Full `scripts/ci/verify.sh` passed: **781 Python passed / 26 skipped**,
  **120 Flutter passed / 7 skipped**, Flutter analysis, repository/security
  checks and release web build. Log:
  `/tmp/specimen-release-plan-verify-20260908.log`. These are local baseline
  results, not real-data or public production acceptance. No test was weakened.
- Updated generation-cap candidate: red-first reproduction logs are
  `/tmp/specimen-five-dollar-generation-red.log`,
  `/tmp/specimen-five-dollar-stricter-cap-red.log`, and
  `/tmp/specimen-five-dollar-independent-findings-red.log`. Final focused
  runtime/recovery regression passed **41 tests / 3 opt-in SQL skips** in
  `/tmp/specimen-five-dollar-generation-regression-final.log`.
- Updated canonical `scripts/ci/verify.sh` passed **789 Python / 26 skipped**,
  **120 Flutter / 7 skipped**, analysis, repository/security checks and release
  web build; log `/tmp/specimen-five-dollar-verify-20260908.log`. This succeeds
  the earlier 781-test baseline for the candidate. No paid inference or cloud
  data test is implied.
- Candidate `2964e7b8288ab2e9baf195955519389e67e8b644` is published in draft
  [PR 15](https://github.com/anurag-duddu/specimen-digitization-app/pull/15).
  All five platform checks passed in
  [CI/CD 34277824497](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34277824497),
  as did all three runtime image builds and candidate structure validation in
  [runtime CI 34277824350](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34277824350).
  Hosting was correctly skipped on the pull request. This is not a merged or
  deployed release, and structure validation does not establish runtime readiness.
- All three specialist initial reports arrived. Runtime reproduced a SAM expiry
  timer lifecycle defect and is repairing it with process tests. Acceptance
  confirmed the public client says its application API is not configured and is
  adding separate journey and cohort-budget evidence requirements. Data is
  reviewing manifest completeness. Some local commands encountered sandbox
  restrictions; those failures are not application regressions or test passes.
- Coordinator executed the data owner's unchanged baseline harness with
  `SPECIMEN_TEST_PG_PORT=5579 SPECIMEN_TEST_DC_PORT=9549
  scripts/data/test-postgres.sh`: **passed, exit 0**. Actual local PostgreSQL and
  SQL Connect emulator checks covered scoped paging/search, concurrent CAS/admin
  bootstrap, isolated backup/restore, two restored connector restarts, and exact
  schema/data/index equality after explicit, idempotent post-schema index repair.
  Log: `/tmp/specimen-release-data-postgres-coordinator-20260908.log`; retained
  evidence: `/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.CwKNiR`.
  These used synthetic fixtures and local services; live restoration remains
  Not confirmed. The script stopped its own temporary services on completion.
- Data owner is reviewing the successful private inventory at
  `inventory-20260908-firebase` under the existing rollout-state directory and
  preparing the exact freeze/bootstrap/restore packet. Inventory found 1,001
  object records, one database and no recorded backups. This is object metadata,
  not specimen count or image reads. No API was enabled to make inventory pass.
- Policy/resource authority is granted within the recorded limits. Dependent
  cloud work still waits for the verified exact inventory/action
  packet, independent review and a conservative cost reservation within USD 5.
- Coordinator integrated the independently reviewed SAM lifecycle/cache repair
  as `e573458`, its owner report as `becd4f9`, the 45-case acceptance and shared
  budget harness as `db7a0b7`, and data guard repairs as `accbaed`. Each owner's
  closeout is preserved in the shared append-only log. No integrated full-suite
  pass is claimed until the protected workflow implementation is complete.
- Follow-up stage-specific reservations and credential-free SAM loading passed
  their scoped independent review at runtime commit `24e6550`. A subsequent
  real protobuf Struct probe found integer amounts become integral floats at
  the storage boundary. Integration is held for the runtime repair and an
  independent real SQL Connect emulator round trip; external launch validation
  remains strict. This is a local compatibility finding, not a live cloud result.
- Before pruning the old `codex/live-*` branches at the user's cleanup request,
  reconcile and preserve their ignored evidence, append owner closeouts, and
  confirm all source is reachable from main. The unfinished real-model worktree
  must remain until its four untracked source/report paths are integrated or
  explicitly preserved. No removal was authorized by this checkpoint.

## Verified checkpoint after PR 15 — 2026-09-08

This checkpoint supersedes the earlier in-progress source-release statuses above.
PR #15 merged reviewed source `2a787a9` as main
`cc3a412e933b201229121d2ca61f26ae14d6a66c`.
[CI/CD 34291763222](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34291763222)
passed all five checks and the Hosting deploy; runtime candidate CI
`34291763285` also passed. Root independently verified the public deployment
marker and Hosting smoke for the exact main SHA. The protected data and runtime
workflows stopped at credential-free admission because their private inputs were
incomplete. G5 is verified; G6–G8 remain incomplete.

Canonical local verification passed 1,167 Python tests (30 skipped), 129 Flutter
tests (7 skipped), Flutter analysis, repository checks and the web release build.
Skipped and synthetic tests do not count as live acceptance.

The next critical path is:

1. The reviewed keyless data identity and main-only environment setup is
   verified. The registered IAM SQL user has no database roles; native SQL login
   remains untested. Exact custom permissions avoid the broader predefined SQL
   login role. Hosting identity and existing protections were preserved.
2. Add the missing first-time application database and role initialization to
   the protected data workflow, with backup/restore evidence and an independently
   reviewed minimum privilege plan. The existing instance has only `postgres`;
   the application database is absent. No new persistent instance is planned.
3. Reconcile Authentication setup: one scoped setup request enabled email/password
   on the existing app, but the server returned `IDENTITY_PLATFORM` rather than
   the planned `FIREBASE_AUTH`. The helper stopped; app and billing attachment
   were unchanged, and no account/email was created. Do not replay or silently
   treat the failed subtype check as a pass.
4. Prepare the API and verified App Check configuration; establish the owner's
   verified account and scoped administrator membership.
5. Resolve the already-open specimen sensitivity, measured whole-cohort cost,
   new-backup retention and organization App Check allowance decisions. Complete
   the cumulative reservation before any billable cohort work.
6. Run real segmentation and both readers for every region of all ten originals,
   then pass the authenticated correction/save/reload/search/history and recovery
   journey on the public URL. Automated classification and clearance stay deferred.

Private setup regressions continue to use failing tests followed by narrow fixes
and independent review. Setup receipts, source checks and the Hosting checkpoint
are preparation evidence; the first-ten product release is **not yet accepted**.

## Initialization source candidate — 2026-09-09

The first-database implementation is integrated from runtime `1d24d64` with
all owner closeouts preserved. Independent SQL/native, cleanup/provenance and
privacy reviews passed after two reproduced defects were repaired. Canonical
verification passed **1,285 Python / 56 skipped** and **129 Flutter / 7 skipped**,
plus analysis, security/workflow checks and the web build. Source PR/CI remains
the next gate; these results do not establish managed Cloud SQL or live acceptance.
The detailed contract is [DATABASE_INITIALIZATION.md](DATABASE_INITIALIZATION.md).

The bounded prior-cost audit reconciled twelve setup effects and retained
response evidence, but did not establish the complete running balance. No
remaining balance of USD5 is assumed. The five existing owner decisions remain
pending, and no paid model call or native database/restore execution is admitted
by this source checkpoint.

## Verified source checkpoint after PR 16 — 2026-09-09

[PR16](https://github.com/anurag-duddu/specimen-digitization-app/pull/16) merged
reviewed source `04eb3277eb34b2495efa9019d1b812d2a0fd4efa` as main
`e0187b132519c4d4dd17c878ff05201a20d7a01e`; the trees are identical.
[Main CI/CD34307140346](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34307140346)
passed all five checks and Hosting deployment. Runtime candidate CI34307140526
also passed. Root verified the exact public deployment marker and Hosting smoke.

Fresh browser verification shows **Collection connection required** and an
unconfigured application API. Data34307140330 and runtime34307140332 stopped
at credential-free admission; their effect jobs were skipped. G5 is verified
for this source, while G6–G8 remain incomplete. This source checkpoint does not
admit a catalog connection, initializer privilege, restore clone or model call.

The five existing decisions remain pending. The cumulative USD5 balance is
Not confirmed; prior costs must be reconciled before the next billable action.
All ten real inputs, both readings for every retained region, human correction
and durable save/readback remain required. Classification and clearance stay
deferred under the approved human-review scope.

## Configuration continuation after user go-ahead — 2026-09-09

The user authorized continuation and asked what still needs their input. The
coordinator owns routine implementation choices: retain the observed
email/password Identity Platform configuration without reprovisioning; implement
the all-ten segmentation-first, full-cohort reader reservation barrier with TDD;
and preserve backups without assuming new deletion authority. These are explicit
coordinator choices within the existing release scope, not claims that the user
selected every earlier decision card.

Only two owner facts are pending in the replacement decision cards: sensitivity
and provider use for the exact frozen ten, and other organization reCAPTCHA/App
Check usage this month. Account password creation and email verification will be
a later owner action through the real sign-in flow. The existing private admin
identity does not need to be requested again.

Fresh Firebase connector reads verified the intended project/account and enabled
billing. SQL Connect's remote schema remains ephemeral with validation NONE;
this is not a durable database proof. GitHub has no repository variables and
only the existing FlutterFire configuration secret, confirming that public API
and App Check build settings are still absent. Hosting is verified; backend
configuration, native qualification, cumulative cost admission and authenticated
full-cohort acceptance remain our implementation work. No cloud effect or model
execution was performed during this check.

## Direct configuration investigation — 2026-09-09

At the user's request, the coordinator inspected the existing Infinative Chrome
Firebase tab and working authenticated connectors. The browser requires Google
reauthentication and the Mac subsequently locked; connected administrative reads
remain available. These are observed access states, not missing product decisions.
The previous sensitivity and organization-usage cards are superseded: sensitivity
for the exact frozen ten is resolved by local review, and the coordinator owns
investigation of organization usage before actual App Check assessments.

All ten existing local originals match the frozen Firebase generation metadata
(size, MD5 and CRC32C); independent full-image review and SHA256 recording are
complete. The coordinator accepted non-sensitive intake only for this private
human-review pilot. This does not grant automated institutional clearance or
validate the source collection's taxonomy. Preserve literal label readings and
all ten originals. No cloud image fetch or model call was needed for this review.

Fresh native reads confirm only `postgres` in the existing SQL instance, a
disabled Cloud Run API, and no App Check/reCAPTCHA registration. The existing
inference credential version is enabled and reusable. GitHub's backend release
environments lack required guards or private inputs. Hosting continues to serve
the verified PR16 source and the unconfigured-API setup screen.

Eight fixed, bounded Monitoring GET requests completed with native receipts.
Their conservative read cost is at most USD0.000017; the full USD0.001 allowance
and USD1 prior-uncertainty hold remain retained. This is not a settled invoice or
a claim that the rest of the budget is available for cohort work. Independent
review supports an additional USD0.02 catalog-only reservation, subject to source
and identity admission. The current production ledger requires workflow IDs for
all entries; a minimal additive contract is being tested to preserve actual
operator provenance and prior uncertainty without inventing workflow runs.

The all-ten reading barrier candidate `3bb8d17` is integrated locally for review.
Independent testing found that per-specimen time checks do not ensure all
remaining readings fit the launch and worker deadline. That regression must be
fixed and reviewed before the next source release. GitHub environment guard
setup is being prepared and tested separately; no guard effect is claimed here.

### Verified backend environment guards

The coordinator executed the independently reviewed six-action GitHub setup.
`runtime-production`, `runtime-build-production`, and
`data-initialization-production` now each have exactly one `main` branch policy.
Native full listings and individual policy readbacks verified all six effects;
`production`, `data-production`, and main branch protections were preserved.
No workflow, cloud resource, secret, input or deployment was changed by this
operation. The existing runtime environment identity was retained.

Further native inventory confirms Artifact Registry is disabled alongside Cloud
Run, and the separate runtime/initializer service accounts and WIF providers are
absent. Only the existing Hosting and ordinary data providers are present. The
coordinator is preparing the minimum already-authorized setup from those facts.

### Integrated cohort, transport and cumulative accounting fixes

The next candidate includes the all-ten segmentation-first reader barrier and
the independently repaired aggregate time admission. Every retained region and
both pinned readers remain required. Durable attempt claims retain uncertain
liability across restarts; launch and worker checks preserve the original
execution deadline, including malformed retained-window rejection.

Native SQL Connect numeric transport exposed a separate circuit-state defect:
integral JSON values can return as floating-point values. The repository adapter
now normalizes only validated persisted integer fields, preserves strict public
validation and compare-and-swap revision checks, and rejects unsafe writes.
Generated ten-specimen/two-region coverage verifies all forty reader attempts;
it does not count as actual specimen processing.

The additive `release-cost-ledger/v2` contract preserves the exact original
coordinator snapshot, real operator provenance and the positive prior-uncertainty
hold alongside exact workflow reservations. The cumulative USD5 cap cannot reset
between dates, sessions or retries. Independent accounting and source reviews
passed; actual catalog admission still requires its reviewed private packet.

Canonical `scripts/ci/verify.sh` passed: **1,478 Python tests / 56 skipped**,
**129 Flutter tests / 7 skipped**, repository checks, analysis and the web build.
The source PR, all five exact-head checks and protected main release remain the
next source gates. No native SQL catalog or paid model inference is claimed.

### Runtime API setup reconciled

One native request enabled the Cloud Run API. Its original operation completed;
fresh reads confirm that both Cloud Run and Artifact Registry APIs are now
enabled. Artifact Registry changed during that sequence, so the helper stopped
before a second intent or enable request. The coordinator and independent
reviewer retained that original blocked result and added a separate observed
closure; no replay or unverified causal claim was used.

Fresh regional inventory confirms the runtime registry is absent and there are
no Cloud Run services or worker jobs. Six separate service accounts have since
been created and read back; their runtime/initializer permissions, registry,
actual SQL initialization and runtime delivery remain necessary setup.
The connected cloud tools and in-app browser work while the native Mac is locked.
The earlier request to unlock and sign into the Firebase console is withdrawn.

### Verified source delivery and next native checks — 2026-09-09

PR17 is merged at `d34d27032b07c223a7556472535c8fe2ebd828ae` with reviewed
tree `4baa39a95c26dbff1ffb878a9b346cd80d70cd31`. All five main checks and the
Hosting job passed in run34316700169 attempt1. The public marker and smoke
match that source. The browser still reports that the application API is not
configured, so the complete product has not passed live acceptance.

The existing data provider now emits only its unchanged subject and unique
release-plane mapping. One PATCH was sent. An initially incomplete operation
response stopped the helper; separate read-only reconciliation subsequently
verified that original operation completed and all ten service accounts,
eleven project/account policies, other providers and Hosting were preserved.
No update was replayed.

The approved administrator Auth record is now created and verified by UID and
email readbacks, with email unverified and no password supplied. No email or
collection membership was created. Once the backend and login UI are ready,
the owner sets a password, verifies the email and tests signed-in human review.

The protected catalog attempt2 passed both source and budget admission checks,
then stopped during Google authentication before SQL. The pinned GitHub action
uses a full identity URL as its default audience; the provider was configured
with the shorter resource name. The provider now accepts the exact full identity URL. A separate source guard
also required correction to match the pinned action's generated credential.
That repair and Enterprise App Check selection are prepared together for PR18.
The next catalog must use the newly merged source and its actual main-push run;
the unissued old-source attempt3 draft must not execute. Attempt2's USD0.02
reservation remains held. The next-attempt draft retains another USD0.02 for
USD1.041 in proposed cumulative commitments; it has not been issued or started. These reservations are not a billing invoice
or a verified remaining balance. No SQL catalog, schema initialization, runtime
deployment or paid model inference has occurred yet.

The empty runtime registry is now created and verified as immutable and
unscanned. Google added its documented Artifact Registry service-agent role;
all prior project bindings and ten service-account policies were preserved.
The three additional WIF providers remain pending and will use the corrected
audience contract. Native operation, GET and LIST response differences were
reconciled through reads without replaying the registry create.

Direct App Check reads confirm default unconfigured records and zero project
keys. The web app's Enterprise provider correction passed its red-first tests,
full Flutter suite, Chrome provider tests, analysis and build. Independent
credential review used the actual pinned action bundle with synthetic inputs;
all four emitted fixtures fail on the old guard and pass on the correction.
The combined source gate passed in an isolated worktree: 1,501 Python tests
(56 skipped), 133 Flutter tests (7 skipped), repository checks, analysis and the
release web build. The pull request and protected main delivery remain next. These checks do
not establish a live App Check exchange or an authenticated product journey.

Bounded monthly assessment reads returned no assessments for nine accessible
organization projects. The tenth project's Monitoring read was denied, so
organization-wide allowance coverage remains incomplete. No permission was
expanded or assessment created. Metadata-only key registration may proceed;
assessment-cost headroom remains a gate before public browser activation.


### Verified PR18 source and provider checkpoint — 2026-09-09

PR18 is live at `bc2b5483dfa831c04bf83734c237f3ef3617f1db`, with reviewed
tree `28b55ddaa104b89fee268e35d6d47bab79411f9d`. All five main checks and Hosting
passed in run34323102079 attempt1. The public deployment marker, smoke test and
fresh browser check were independently inspected. The app still shows its
unconfigured API screen; this is a source checkpoint, not full acceptance.

All three remaining runtime/initializer WIF providers are now created. Root and
an independent reviewer reconciled 239 native responses and preserved the
existing two providers, ten service accounts, eleven policies and empty immutable
registry. Their exact service-account bindings are prepared offline; workload
grants and actual runtime delivery remain pending.

The new original data34323102081 attempt1 stopped before cloud credentials and
skipped every effect job. A fresh catalog-only attempt2 is being reviewed against
PR18. It carries the old attempted USD0.02 liability and reserves a new USD0.02
once, with proposed cumulative commitments of USD1.041. No native SQL catalog,
database initialization, runtime deployment, model inference or signed-in review
has yet passed. The original ten specimens and cumulative USD5 cap remain fixed.


### App Check registration verified; exact GitHub subject repair — 2026-09-09

The existing owned Enterprise key is now registered to the live web app. One
siteKey PATCH succeeded; root checked all58 native response hashes and the full
key/config/identity/policy readbacks. Existing token lifetime, score threshold
and enforcement settings were preserved. No browser assessment or public build
setting was enabled by this metadata operation.

New-main data run34323102081 attempt2 passed both source and budget admission
checks, then failed Google federation before SQL because its exact subject
condition used GitHub's older name-only subject. The repository's native OIDC
configuration reports an immutable owner/repository-ID prefix, matching the
current format for its September7 creation. Four backend/initializer providers
need only that exact subject value corrected; other restrictions and Hosting
remain fixed. No automatic workflow retry has been requested. Both actual
catalog attempts retain their USD0.02 uncertain liabilities; current admitted
commitments remain USD1.041. A later attempt3 draft would add USD0.02 once and
requires actual repair evidence and a new independent reservation review.

Fresh reads after App Check registration preserve all five providers, ten
service accounts, eleven policies, enabled APIs and empty immutable registry.
Three matching WIF service-account binding requests passed independent offline
review; their executor and narrow immutable-subject planner amendment are being
tested before any grant. Image-publication permissions are being prepared in
the existing runtime session. Actual catalog, database initialization, runtime
deployment, ten-specimen processing and signed-in save/reload are not yet
confirmed.

The older organization project's Monitoring and Admin Activity reads remain
denied. The owner has one selectable factual question about its September
reCAPTCHA usage; the USD5 cap remains in force while backend work continues.


2026-09-09 08:28 UTC checkpoint: all four existing data/runtime WIF immutable subjects now natively repaired with 240 verified response receipts and full state preservation. Next: independently reviewed original main data run34323102081 attempt3. Hosting PR18 remains live; runtime/API and full ten-specimen acceptance are not yet ready.

### Catalog and runtime access checkpoint — 2026-09-09 09:12 UTC

The three exact WIF-to-service-account bindings are now complete. Root and an
independent reviewer reconciled all202 native responses and the full eleven-field
baseline; only the three reviewed account bindings changed. Image publication
and workload grants have not started.

Original main data run34323102081 attempt3 passed source/budget admission and
Google authentication, then failed the reviewed catalog command with a sanitized
ValueError. Its complete native artifact listing is empty. Actual SQL connection
and the precise failing operation remain Not confirmed; absence of a file is not
proof of absence of a connection. No retry was issued. The additive accounting
draft retains all three actual USD0.02 attempt liabilities as unknown, preserving
USD1.061 in cumulative commitments; a next reservation has not been issued.

An independent offline test of the unchanged pinned authentication action
reproduced mode0640 under umask022, which the strict credential reader rejects.
The scoped source repair tightens only that owned credential descriptor to0600
before reading it and adds fixed safe failure stages. The general private-file
policy and successful catalog protocol remain unchanged. TDD and independent
review passed; full verification on Python3.12 is running in an isolated branch.
The next native catalog must bind the eventual merged source and its own actual
main-push run. The historical runner mode and failure cause remain unconfirmed.

Runtime publication preparation now includes successful native direct404 reads
for both proposed custom roles, a complete FULL/deleted role list showing neither,
and all four required registry permissions in the exact repository's native
permission catalog. The organization allow policy is readable; the tested project
deny and principal-boundary lists returned no entries. Organization deny listing
is denied and remains unknown. Independent review confirms this restricts certainty
about successful access, without increasing the proposed allow permissions; it
requires no new owner permission or denial-policy change. Final exact positive
grant review, fresh execution reads and protected publisher calls remain necessary.

The owner cost question for the older project's monthly reCAPTCHA usage remains
pending. No browser assessment, runtime image publication, native database
initialization, model inference or authenticated ten-specimen acceptance has been
claimed from these checkpoints.

### Current integrated release checkpoint — 2026-09-09 10:04 UTC

PR19 source repair merged normally as `c2a5ce897e344cb5952cdfaf51aae0747dfe5dde`; exact-head five platform checks and all six main CI/Hosting jobs in34334300400 passed. All four runtime candidate jobs in34334300467 passed. Public deployment marker and independent public smoke match the source. Browser still shows collection connection required/API unconfigured; full product acceptance remains Not confirmed. Root full verification passed1,548 Python tests and133 Flutter tests with explicitly recorded skips; public source verification lives in `catalog-pr19-source-release-20260909/ROOT_PUBLIC_VERIFICATION.json`.

Native source SQL settingsVersion is now5. Independent old/new full comparison established only metadata etag/selfLink/version differences, with every configuration field and full eleven-field runtime/IAM state unchanged. Later native selfLink alias variation was reconciled explicitly without following the link or changing configuration. Root and frontend retained all29 current nativeHTTP200 and ten GitHubHTTP200 preflight receipts; no SQL connection was inferred.

Root issued exactly one fresh source-bound catalog packet for original main data run34334300382 prospective attempt2 at1788948048, expiry1788951648. New20,000-micro reservation carries complete prior33 rows forward; total commitments1,081,000 micros under unchanged5,000,000 ceiling. Final bundle independent review precedes exact existing four-variable/one-secret installation and one original-push rerun. Runtime34334300352 remains original credential-free attempt1 failure with no effects.

The runtime workflow requires actual same-source data-ready proof and API configuration before full runtime preparation; there is no publication-only phase. Preserve this ordering through catalog, exact service-agent registration if absent, verified backup/owned restore, initializer qualification/disposal and compatible data apply. The root independently reviewed the additive no-role service-agent registration executor (37 mocked tests; actual metadata/source checked); actual catalog and eight fresh prerequisite observations are still required. The publication IAM executor is undergoing TDD correction for two independently reproduced deadline bugs, without cloud grants. Offline model cache preparation is complete; no model upload/inference or full-cohort processing has occurred.

The only pending owner cost fact remains older-project September reCAPTCHA usage. Backend work continues without browser assessments. Owner authentication handoff will be requested only once the backend and live UI are ready for it.

### 2026-09-09 10:35 UTC checkpoint

Protected catalog run `34334300382/2` succeeded on main `c2a5ce897e344cb5952cdfaf51aae0747dfe5dde`; signed artifact, actual workflow attempt/environment, encrypted catalog and private plaintext were independently reconciled. Application data and runtime remain uninitialized. Cumulative pilot commitments remain USD 1.081 of USD 5.

The actual native catalog revealed managed `cloudsqladmin` database and inert IAM authentication membership assumptions that the initializer must preserve. A combined red-first compatibility repair is being completed in isolated `codex/managed-cloudsql-catalog`; the initial database-only version passed full CI and independent review, but final combined bytes still require those gates.

The SQL Connect managed identity lookup now uses the documented exact service identity generation design, pending executable independent review and one root-owned bounded action. No role grant, SQL registration, clone, runtime publication or specimen processing has occurred in this checkpoint. Frontend separately reviews repaired publication IAM executor deadlines; root coordinates all native writes and PR sequencing. The existing reCAPTCHA prior-usage question is still pending and limits browser assessment activation only.

### 2026-09-09 10:56 UTC checkpoint

The exact SQL Connect primary managed identity is now verified by one successful Service Usage generation operation and full consumer-project before/after preservation. No SQL registration or schema initialization yet. Root native closure `a9595ea44d1031bd5eb9ba84af3061649d06e018fd0ca39a0ca8b471fcb285cb`; cost commitments unchanged at USD1.081.

Combined managed-database/IAM-marker repair `8a63bcdb10d356f872bec50d817436796d863b36` is open as PR20 with full local gates and independent review complete; exact platform/runtime CI is running. Root holds main c2 stable during the separately reviewed SQL-registration setup. Delivery prepares the next-source catalog issuer; Budget prepares complete phased resource/model cost accounting; Frontend independently verifies actual identity outcome; runtime session authors bounded registrationv3. Root owns native writes, actual packets, PR merge and public verification. No cohort result or end-to-end readiness is claimed.

### 2026-09-09 17:09 UTC resumption

PR20 all five platform checks and four runtime candidate jobs are now green on8a63; protected main remainsc2 while separately reviewed SQL registrationv3 is completed. The prior service identity generation succeeded and must never be replayed. Reconstituted bounded review, catalog and cost workers continue with root as sole native writer. The existing runtime task is active again. Public browser still displays API unconfigured; full app acceptance remains Not confirmed.

Eight SAM cache files were rehashed locally with fresh transfer checksums and unchanged aggregate; no upload/effect. Cost/time analysis now checks the common segmentation/reader timeout before committing the single30-minute worker run. USD1.081 cumulative holds and the frozen ten remain unchanged; no limits reset, old packet reuse or processing credit from local SAM qualification.

Correction at 2026-09-09 17:03 UTC: the preceding root resumption entry labeled17:09 UTC was written before17:03 UTC; the heading time was an operator transcription error. The reported GitHub/browser/local checksum facts and no-effect state are unchanged.

### 2026-09-09 19:02 UTC — integrated release checkpoint

The selected first release remains all ten frozen specimens through segmentation, both independent readings for every retained region, correction/save/reopen in human review. Classification and institutional clearance remain deferred. USD5 is one cumulative incremental pilot cap across all tasks and retries; retained commitments are USD1.081. No new catalog, backup, image upload, runtime or model execution reservation has been issued in this checkpoint.

SQL Connect registration completed exactly once at18:19:24UTC using the reviewed no-role request. Full93 original request/response triples and all16 before/after fields were independently verified: only the intended SQL user was added. Root closure da2e8d22 and independent outcome c68ee26f are retained privately. Native PostgreSQL privileges remain Not confirmed until the next protected catalog. The original generation and registration intents are permanent and must never be replayed.

PR20 merged as0547636b66b82a8666616a4c00306a79039af29a. All five main platform checks and all four runtime candidate jobs passed. Hosting upload succeeded, but its immediate public marker read was stale and the deploy job failed. Later root public marker and smoke match054763/run34389444933/attempt1. This is not a green source-release completion; a bounded, strict marker propagation retry is being developed through TDD before the next normal PR. Protected runtime/data admission failed with effect jobs skipped and no rerun.

The coordinator integrates reviewed source in isolated codex/pilot-release-completion based054763. Cohort v2 adds atomic all-ten SAM reservation and expansion from actual retained regions, plus consistent reader deadlines; 176 independent checks pass, including the originally failing near-expiry schedule. Finite backup expiry and maximum-byte proof pass653 CI-script and20 independent checks; the optional path preserves legacy behavior. Native backup response shape, expiry enforcement and restore success remain Not confirmed. Full combined verification and the next PR remain pending.

Current orchestration uses the same inherited coding-model configuration, with no model override or additional key. The bounded collaboration workers inherit the coordinator's model and reasoning settings; product inference remains the pinned SAM, Qwen/Novita and Muse/DeepInfra routes.

| Active owner | Current responsibility and next evidence |
|---|---|
| Root coordinator01a082b2-c2c3-70d2-be90-7bfb622c9102 | Sole native/cloud/GitHub writer; integrate exact reviewed bytes, full verify, PR/main release, cost/source packets, protected data/runtime and final live acceptance |
| complete_pilot_cost | Completed cost worksheet, cohort repair and independent backup audit; independently tests the strict Hosting verifier |
| identity_registration_review | Completed registration and cohort outcome reviews; independently reviews the concrete cache upload/cleanup executables |
| next_catalog_issuer | Authors bounded eight-file cache transfer and exact-generation cleanup with offline TDD; preserve original frozen catalog issuer and later refreeze it for actual final source and registration evidence |
| Existing runtime task01a082b4-a9bd-7392-a73b-57ca45532fb7 | Completed finite-backup repair; authors strict Hosting propagation verification in a separate worktree |
| Existing read-only release monitor01a08342-516e-7d53-a6ce-0f28cf63d1a3 | Tracks actual workflow completion/failure; root handles public access where monitor DNS is unavailable |

Next: finish the Hosting repair and independent review; run combined verification; use normal PR and exact-source checks. Issue one fresh final-source catalog after these changes, carrying all prior commitments. Then qualify backup/owned restore, initialize/dispose temporary privilege, publish compatible data, qualify runtime/cache/model access and run the one bounded ten-specimen worker. Verify authenticated human review/save/reopen on the live URL. The older-project reCAPTCHA usage question and verified owner authentication remain separate owner facts; backend preparation continues without inventing answers or overriding identity.
