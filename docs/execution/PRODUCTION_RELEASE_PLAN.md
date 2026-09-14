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


## Coordinator checkpoint — 2026-09-09T20:10:59.540540+00:00

PR21 source aa7cdc0613fb4887ba5265a5aab29ac9df7eb4d8 is publicly verified: all six main jobs green, exact deployment marker/run/attempt and strict public smoke pass. Fresh browser still shows API unconfigured. The next protected read-only catalog is being bound to original data34397935824 attempt2. Current cumulative commitments remain USD1.081; one next USD0.020 remains unissued. Actual34-read native state is unchanged from the independently closed registration. Historical observations retain their original age; refresh before issuance.

Current work assignments, preserving configured models and inherited reasoning settings:

| Task / agent | Current bounded work | Root acceptance gate |
|---|---|---|
| Root coordinator | Actual GitHub/public/native observations, reviewed packet issuance, all production effects | Exact source, current independent proof, cumulative budget and final live acceptance |
| next_catalog_issuer | Original-only issue/install controller source and offline TDD | Independently reviewed source; no author effects |
| identity_registration_review | Actual source/catalog/native proof review | v3 current-input review and exact final bundle review |
| complete_pilot_cost | Controller independent review; frozen complete cache cost/retention reconciliation | No duplicated allocations; original operation fences |
| Release: runtime and model processing | Local merged-source Linux amd64 image geometry and network-none smoke | Immutable source/image evidence before protected publication |
| Release: data and cloud readiness | Minimal initializer/disposal permissions and typed setup preparation | Actual next catalog and separately reviewed bounded action packet |
| Existing release monitor | Read-only exact-source workflows | Quiet on unchanged state; root owns mutations |

The execution harness remains protected main-push GitHub workflows plus fixed typed native action packets, original-operation journals, disjoint cumulative budget reservations and offline fault-injection tests. The application harness uses all10 segmentation reservations, then atomic allocation for both readers over every retained region and the fixed worker/reader deadlines. Human correction/save/reopen remains the chosen release; classification and automated clearance stay deferred.


## Coordinator checkpoint — 2026-09-09T20:35:53.227249+00:00

PR21 public source remains aa7cdc0/all6mainCIgreen. Original current catalog issued exactlyonce and installed; run34397935824/attempt2 admissionpassed, native catalogrunning. Current cumulative commitments USD1.101/55rows including the new20k hold; exactlyten unchanged. Root owns protected execution/attestation/decryption/native review. Identity reviewer is checking current local image qualification; next_catalog_issuer prepares offline outcome checks; complete_pilot_cost independently reviews minimal IAM draft. Existing data task prepares concrete bounded setup transport; runtime task has completed all3localimages/fiveCLIchecks; product journey task completed its offline149-test runbook. Actual data initialization, runtime publication, real all-ten model pipeline, browser correction/save/reopen and final release remain pending. No new tasks, model overrides, budget resets or specimen substitutions.


### 2026-09-09 21:15 UTC — root catalog closure, cache reservation and backend corrections

Task `01a082b2-c2c3-70d2-be90-7bfb622c9102`; canonical `codex/cohort-budget-admission` at `defbb1df1ca0417dfb89f203077ff16303d3affb`, preserved dirty shared logs and all other worktrees. Source PR21 merged `aa7cdc0613fb4887ba5265a5aab29ac9df7eb4d8`; all six main CI jobs, exact public deployment marker and strict smoke already verified. This is source delivery, not full product acceptance.

- Original data main-push run34397935824 attempt2 completed successful catalog with downstream mutation jobs skipped. Root verified exact artifact IDs10123780879/10123778884, ZIP digests, keyless attestation source/run and encrypted envelope before one private decryption. Actual catalog confirms application database absent and registered SQL Connect IAM role present. Independent159 checks25 files PASS, review4466ca89c9dfa71d02e547459341565708984bf22e656566c5fe5e68cefa8fb4. Native catalog SHAe7a2285e4c8bd50df2980bd6629a78903a1155501ecb244675ae8bbd87562a97. The historical verifier3f67 vs final49e source difference was reconciled using actual retained bytes and AST; no duplicate decryption or rerun.
- One cache upload/cleanup reservation140000micros was appended without changing prior55 workflow rows, operator hold or1M uncertainty. Current cumulative commitments1241000micros, ledgera53e2ba59e594321493385c7a9069807b95dcdc74e73b7bcd5bd58d51b46ab5a; independent187checks44files PASSc61dfbb2943e424b142ce7457e1508411252704bb182ebf1df0adc30dcb25d2e. Cache network120400/storage19600 are subsets of full650000/90000, never extra funding or a second cleanup hold. Same-second local snapshot validation failure was reconciled before saving ledger, without altering original snapshot/intent or issuing twice.
- Existing Firebase credentials normally refreshed at21:05:14; no new account/key. Fresh exact four cache metadata GETs were recorded. First prospective T21:09:32 was missed during coordinator compaction, with zero operative binding/fence/native upload. All original reviews/evidence remain immutable. Second prospective T21:17:07 has actual fresh four GETs, 223 independent checks, review62525bf072c3813f0751d8f883bf5c9b6a88bfe89e7882635ebc9ce847648f1d. Root activation wrapper6a2d17f725784a189c8a1e3a3029c6ac67e84e927db1ece3d01ec0fcc15a8531 passed independent static read. At this log instant upload remains Not started. Later exact eight-generation cleanup after SAM quiescence is still required; no automatic TTL claim.
- Concrete data IAM executor independent tests found a real Requests slow-drip total-deadline gap (3.156seconds return against2.1);31other tests+17subtests passed. Data task is repairing test-first, with no native grants yet. Runtime task found SAM original-read/old-claim-prefix mismatch; focused correction reads verified application copy and preserves provenance/idempotence, independent acceptance-task source review now active. Source successor and actual cache-mount least-privilege qualification remain required. No specimen or model execution has occurred.
- Google billing browser requires fresh private sign-in for existing anurag account. Owner question is pending; backend work continues. No password, MFA code, email or verification override requested/executed. API URL/sitekey remain unpublished until data/runtime/App Check admission. Entire ten-specimen human review/save/reopen acceptance remains Not confirmed.


## Coordinator checkpoint — 2026-09-09 22:16 UTC

**Production dispatch is blocked; end-to-end acceptance remains Not confirmed.** The existing accounts/tools work, and the sole reviewed IAM setup succeeded (eight exact custom roles, one additive project-policy write, all prior policy state preserved). Cloud SQL then returned403notAuthorized for the exact owned-clone operation-history read. This failed required readback stopped the sequence; the original phase issue window elapsed without a packet, data workflow rerun, database change, backup or restore clone. Full failure evidence and independent review are retained. The failure does not establish missing history or prove its permission cause.

Current public source is PR21/aa7cdc0613fb4887ba5265a5aab29ac9df7eb4d8; main CI/Hosting and earlier strict smoke are verified, latest22:05 public marker still matches. Original data34397935824 remains successful catalog attempt2 only. SAM application-copy/storage correction is draftPR22/e1666f6 with canonical verification and independent review; it remains unmerged. Runtime setup contract v2 fixes the independently reproduced mask-create permission gap; its source/design review passes, native runtime setup remains pending.

| Owner | Current concrete work / next gate | State |
|---|---|---|
| Root coordinator | Preserve exact native failure and finite authority; reconcile source/native path before any new protected release operation | Production stopped |
| Release: data and cloud readiness | Diagnose exact Cloud SQL clone-history403 using retained response, same-source code and primary documentation; TDD repair only if substantiated | In progress, no cloud effects |
| Release: runtime and model processing | Corrected least-permission runtime contract, managed-folder cache design and actual SAM mask path | Independent source/design PASS; native pending |
| Release: product journey and acceptance | Reviewed runtime grant correction; actual original-ten browser/auth/pipeline/correction/save/reopen/denial evidence remains pending | Offline harness ready; live Not confirmed |
| identity_registration_review | Native IAM outcome and stopped47-metadata-read sequence reconstructed independently; no phase admission | Verified outcome / blocked release |
| complete_pilot_cost | Reconcile actual metadata traffic while preserving full previous holds, no duplicated accounting | Current commitments USD1.256; billed cost Not confirmed |
| next_catalog_issuer | Two-plane controllers and truthful current43+7 input derivation qualified offline; no active phase packet | Source PASS; actual history gate failed |

Exactlytenexisting specimens/allretainedregions/bothreaders/fullhumanreview remain required. USD5 is cumulative across all tasks/days/retries; no reset or undocumented spending release. The cache's original8objects require owned-generation cleanup by Sep10 21:17:07UTC, with the existing140k upload+cleanuphold. Timestamprepair is independently verified; futurebucketIAMetag drift needs a distinct preservation correction before operationalcleanup. No cache TTL or finishedcleanup is claimed.

The only pending user interaction is privateGooglebillingreauth in the existing Chrome Release billing session, needed to verify App Check assessment cost. Do not request new keys or share passwords. Final owner sign-in/verification remains a private product step. No App Check assessment, specimen import, model processing or accepted human review has yet occurred. All existing task IDs, inherited coding models, TDD/independent-review and protected main-only deployment harness remain as listed above.


Update 2026-09-09 22:23:19 UTC: the data diagnosis is complete. Seven unchanged-source regression tests verify safe stopping in both precreation paths. No source patch is justified yet: optional-instance REST syntax is documented, while deleted-target history coverage and release-identity authorization remain unconfirmed. Root has the frozen diagnostic design for a later fresh read-only scope. The production stop, original expired window, USD1.256 reservations and pending private billing sign-in remain unchanged.

Update2026-09-09 22:48UTC: project-level SQL history diagnostic ran once and returned HTTP400 INVALID_ARGUMENT (285bytes); earlier absent-clone filtered request remains403. No retry or cloud mutation. Fourteen pure safety tests passed; a local private-file mode issue was corrected before the sole cloud request, preserving both attempts. Production remains stopped. DATA is evaluating a supported pre-creation correction preserving the one-clone/no-replay requirement; issuer agent audits cross-run evidence. Reservations remainUSD1.256; actual billing and live acceptance Not confirmed. Google billing sign-in remains pending.

Update 2026-09-09 23:32 UTC: complete captured GitHub data-workflow history now accounts for all seven runs/twelve attempts; none entered a clone-creation-capable phase. Independent baseline reconciliation a37900389a91b36e37f1acf951af2dc103be8dbb74244db59289a499e7a0282b closes the earlier PR15/PR20/enumeration gaps. DATA is finishing TDD repair for one shared recovery claim, no application resend, and hard native response deadlines. Root will integrate reviewed SAM commit e1666f6 with the frozen recovery candidate into one PR and run final gates. Acceptance task investigates the newly identified API-configuration/sign-in/bootstrap dependency cycle before any UI correction. Original403/400 failures, expired phase authority, USD1.256 commitments, private billing sign-in and cache cleanup deadline remain unchanged. No new production admission or full-app result is claimed.

Timestamp correction at 2026-09-09T23:30:28.669028+00:00: the preceding root checkpoint labelled 23:32 UTC was written at approximately 23:30 UTC. The heading was an incorrect manual timestamp; all linked native scope and result timestamps remain unchanged.


## Coordinator checkpoint — 2026-09-10T00:34:54.354167+00:00

PR23 is merged and the public sign-in release is verified at source f542604dc67ae12a6579b3dfe0d01d1e4b5b2e46: all five main checks, Hosting34420166543/1, matching public marker and strict smoke. Combined local validation1845 Python/149 Flutter passed with documented66/7 skips. Backend release remains pending; data34420166597/1 stopped at credential-free admission and all privileged jobs skipped.

| Owner | Current work | Next acceptance gate |
| --- | --- | --- |
| Root coordinator | Actual source/proof binding and cloud dispatch | Reviewed executable inputs, cumulative budget, one finite scope, exact native outcome |
| Release: data and cloud readiness | Successor evidence assembler, issuer and two-plane installer | Complete offline path and independent review; observed1 versus planned2 preserved |
| Release: runtime and model processing | Finite API setup, later public policy and owned cleanup | Offline TDD, independent source/cost review, then actual IAM evidence |
| identity_registration_review | Source/Hosting/baseline PASS; same-account refresh independent review | Additive corrected wrapper and later actual effective IAM review |
| complete_pilot_cost | Correct bounded refresh selection; preserve accounting | Frozen source and known additional public marker traffic within existing network hold |
| next_catalog_issuer | DATA executable independent review | Current catalog compatibility, budget preservation and no-replay installation |

Current ledger commitsUSD1.2684, retainingUSD1 prior uncertainty; this is not an invoice. Conditional full ten-specimen forecastUSD4.4434 assumes exactlyten total regions; all actual regions and both readers must fit before admission. No new IAM time window, token refresh, native held claim or SQL deployment has been issued. Existing models/tasks and protected main-only GitHub harness continue; no architecture expansion or specimen substitution.

User-only gates are now concrete: complete Google organization's password check on the prepared billing page, and use the live app reset/sign-in/email-verification flow for the approved owner. Backend work continues independently. Cache cleanup remains due2026-09-10T21:17:07Z with the existing budget hold and exact generations; no automatic TTL or full-product completion is claimed.


### Current coordination checkpoint — 2026-09-10T01:09:14.118962+00:00

Public Hosting remains verified PR23/f542604 with sign-in available. Data initialization, runtime publication/promotion and all-ten live human review remain pending. The configured Google account is present: a single sanitized local diagnostic found a helper schema mismatch between requested scopes and native granted scopes. The original refresh made zero HTTP requests; its failed operation is preserved while a separately reviewed correction is prepared. No user key or account recreation is needed for that local defect.

| Owner | Current work | Exit evidence |
|---|---|---|
| Root | Existing-account refresh correction, exact DATA setup and protected execution | Retained successful token receipt, fresh reviewed native inputs, protected workflow results |
| Release: data and cloud readiness | Frozen32-check phase tools; fresh20-request GitHub collector preparation | Reviewed current source/environment and full baseline observations |
| Release: runtime and model processing | API-first least-permission helper | Final source freeze and independent review, distinct bounded cost admission |
| identity_registration_review | Minimal granted-scope refresh successor | Preserved original failure plus meaningful TDD and frozen source |
| next_catalog_issuer | Independent refresh successor review | Exact source/transport/account/budget and no-replay checks |
| complete_pilot_cost | Runtime helper independent review and finite request-cost quote | No duplicate holds; current cumulative ledger preserved |

Current commitments remain USD1.2684 including the original USD1 uncertainty. The285000+20000 DATA phase is a proposal, not a reservation. New API-first control traffic is separate and must be reconciled. All ten frozen specimens, every actual region and both readings remain required; no full-pipeline cost guarantee or acceptance claim is made. Existing Browser Billing session requires private sign-in; product owner sign-in/email verification remains private. No new product choice, model override, task duplication or architecture expansion.


## Coordinator checkpoint — 2026-09-10T01:57:51.912041+00:00

Task `01a082b2-c2c3-70d2-be90-7bfb622c9102`, canonical `codex/cohort-budget-admission` at defbb1df. Public Hosting remains verified PR23/f542604: sign-in, all five exact-source checks, successful Hosting job, matching public marker and strict smoke. Full data/runtime and ten-specimen acceptance remain pending.

The configured Google account successfully refreshed once using its actual native granted scopes; safe RESULT241f2d46 and independent/root verification293acf56 are retained. No new account/key, credential-cache rewrite or original failed-operation replay. Browser Billing still requires the organization's private password check for anurag@infinative.com; root left the existing Chrome tab ready and asked only for completion there.

The first current GitHub collector stopped after eleven read-only requests because its protection predicate incorrectly expected five protected contexts. The actual policy matches DEPLOYMENT: three strict protected contexts, with all five successful CI jobs independently required. Additive v2 collector107be309 passed25 author tests and10 focused independent tests; existing GitHub protection was not changed. New scope1bbd32bd has its original300-second interval and separate source/cost reviews; its actual outcome will be appended. Old scope, eleven responses, STOP and both network holds are preserved. Current shared ledger80c69752 commits USD1.2724 including USD1 uncertainty, independently reviewed4ef1bf37. Current six-proof bundle d79bac9c has independent input reviewad93d2e5. Neither amount nor proof set establishes native billing or full-pilot affordability.

Read-only integration reviewad4b39c2 identifies remaining sequencing work: publisher setup is separate and its historical preservation baseline needs explicit reconciliation after DATA policy changes; API-first permissions cover reads, while imports/save and worker/SAM require additional reviewed setup; SAM must be prepared before its worker-only invoker is verified; a second full runtime prepare currently repeats three-image publication. These dependencies must be included in the complete cost before new DATA mutations.

| Owner | Bounded work | Required evidence |
| --- | --- | --- |
| Root | Actual read-only GitHub preflight, current coordination and private sign-in handoff | Fresh source/protection/environment/baseline outcome; no premature production dispatch |
| next_catalog_issuer | Exact scope and actual twenty-read outcome review | Independent current-source and baseline judgment |
| complete_pilot_cost | Collector scope review, complete-pilot sequencing cost, final API helper review | Current cumulative budget, required second build/setup accounted for |
| identity_registration_review | Prepared DATA comparator and current proof bundle | Actual effective IAM review only when a new scope is admitted |
| Release: product journey and acceptance | Publisher successor TDD against legitimate policy lineage | Preserve historical baseline and reject unrelated drift; no native action |
| Release: runtime and model processing | Minimum executable full-runtime sequence and cost dimensions | Imports/save grants, SAM preparation/policy and publication count |

The protected GitHub workflow harness, existing task/model assignments, exact ten frozen specimens, all regions and both readings remain unchanged. Human compare/correct/save/reopen is the release; automated classification and clearance remain deferred. DATA600-second setup, native recovery claim, SQL deployment, runtime publication and real inference remain unissued. Cache cleanup remains due2026-09-10T21:17:07Z against its original eight generations and existing reservation.


### 2026-09-10 — current integration handoff

See `CURRENT_RELEASE_CHECKLIST.md` for the current owners and exact review references. The publisher IAM source is qualified; the runtime setup additive repair, five-bundle control package and minimal publication cutoff correction remain in progress. Independent review found and preserved concrete account-policy method, dispatch/history freshness, raw-evidence and credential-contract gaps. Source qualification is separate from actual operation approval. Cost proposal aadeba67 corrects earlier metadata-fee attribution, with count-label addendum0fba1558; the original ledger remains USD1.2724 and full affordability is unqualified. Google Billing private sign-in, post-test retention, original cache cleanup deadline and exact-ten/all-regions/two-reader constraints remain unchanged. No new source release, native packet, IAM/database/secret/environment change, authentication refresh or cloud execution occurred in this handoff.


## 2026-09-10T04:45:03Z — runtime source repair qualified; remaining code fixes isolated

Root accepted the frozen runtime completion source review `b97caf38383a29e8c1ff5379afb8ef359a6d83122c6eeb80a466acc9dea3b906`: all 33 targeted independent tests pass, closing the two reproduced defects. The publication auth-cutoff design review `031a267ed82ba5591b510fa38dfe02f69dabcce040b52e3580650a9c3f2f2d1f` is frozen; the product task is implementing and testing the owned authentication/publication deadline and dedicated local cleanup entrypoint.

The runtime controls package `e4d164f8c660eedb224c8f92edfc5189c9f25664908915391c10ea21b11d90af` passed 109 author checks and is under independent review. Its retained complete-ledger fixture exposes a concrete transport size failure (65,888 bytes against 48,000). The DATA task now owns a separate minimal lossless transport correction, preserving the single secret, raw evidence hashes, all prior ledger rows and the current caps. Root will integrate reviewed source fixes before issuing any new-source operational inputs. No fresh scope, credential refresh, ledger hold, environment write or production action has occurred. Billing and storage-cost inputs remain pending; all-ten live acceptance and complete budget admission remain unconfirmed.

### 2026-09-10 05:40 UTC — root combined release-control regression checkpoint

- Coordinator task `01a082b2-c2c3-70d2-be90-7bfb622c9102`; canonical branch `codex/cohort-budget-admission` at `defbb1d` retains existing coordination edits. Isolated worktree `/private/tmp/specimen-release-controls-integration-20260910`, branch `codex/release-controls-integration`, base `f542604dc67ae12a6579b3dfe0d01d1e4b5b2e46`, contains 18 intended source/test/document files. Commit/PR: Not confirmed; none created at this checkpoint.
- Transport independent review `8f54725e111cd63605f9b43c320a31e9cda74ecd84749596d2ce82d84d3c18e8` passed 59 focused checks. The exact retained 65,888-byte complete fixture encodes to 7,076 bytes, while raw hashes and legacy small bundles remain unchanged. This is source qualification, not future-source or actual-input issuance.
- Publication first final-output repair `c6cc8fe1847d42eb0a9a292880099a4f2746d0f547820d62d010604593a42490` closes the original late-close defect; original probe plus preservation tests pass 20 cases. The additive independent review `c56d25b0825b9eaaf737c3205fc4fa93d234324da30b4909d584b59d48d3dc5c` found one new gap: checking the pathname before append does not bind the actual opened descriptor. Replacement file/symlink cases fail; seven controls pass.
- Root reproduced the exact new probe `2491ccd8596b35511b6e1af4558b67f1958bbfc213a4f90d0ea33f9c6218a44f` against the combined checkout: 2 failed / 7 passed. Durable RED log `/Users/anuragduddu/.codex/rollout-state/specimen-live/release-controls-integration-20260910/descriptor-red/RED.log`, SHA `a3d40d7eee145af6b333d3da47330fb56e0aa4af254e2c977d59e4ea47380f81`. Both observed substitute-byte files are retained separately from later GREEN evidence.
- Product task owns the minimal descriptor correction and regression-first verification; original and first-repair artifacts remain immutable. Mechanical `fileno()` delegation in file wrappers must have new test hashes while preserving injected faults, clocks and assertions. No production test-double bypass is acceptable. Source reviewer checks combined interfaces while root waits to run canonical verification on the corrected candidate.
- Read-only `git ls-remote` observed main still f542; GitHub repository metadata reports PUBLIC. These observations do not renew historical source/environment scopes. No new credential refresh, cost reservation, cloud/data mutation, publication, import or inference occurred. Billing private sign-in and image-retention answer are still pending; whole-release affordability and live acceptance remain Not confirmed.

### 2026-09-10 — PR24 final release-control source candidate

- Coordinator task `01a082b2-c2c3-70d2-be90-7bfb622c9102`; isolated branch/worktree `codex/release-controls-integration` / `/private/tmp/specimen-release-controls-integration-20260910`; committed candidate `a9639c4c782fdc20e7e2ad7323be0997c07455ba`, PR https://github.com/anurag-duddu/specimen-digitization-app/pull/24. Canonical `codex/cohort-budget-admission` retains append-only coordination files. No worktree or branch was removed.
- Final 20-file staged candidate passed `scripts/ci/verify.sh`: 1,919 Python passed / 80 skipped / 7 warnings; 149 Flutter passed / 7 skipped, clean analysis, release web build and every safety hook. All source hashes remained unchanged. Final log SHA `8834947b233e73e9409e2d0000a616e364f5951e82360ae9e877cd2a98c0600d`; earlier run `66c55b6a...` remains historical predecessor evidence. Real commit and pre-push hooks also passed.
- Independent exact-source reviews: transport `8f54725e111cd63605f9b43c320a31e9cda74ecd84749596d2ce82d84d3c18e8` (59 focused); final publication `c514e49c2e1690e2bb2c6663547efcb2574d98baaa3937c21a03751581516a5b` (31 focused); combined interfaces `da85edc47730c1da1b8add9456d34c514e42170feb247bd722d3851fc2cb9332`; exact public-revision scanner exception `30178978888fbd18bc3889c3f1abe1252ebed5e220f155aca656eca2bcc9bfc6` (10 directory/staged controls). Publication source4434f70a and consumerfb31b7a remain unchanged by the two scanner/doc additions.
- Initial real commit was correctly rejected by Gitleaks for public AUTH_SHA. It created no commit. A dependent push was mistakenly already issued and only created the remote branch at existing f542; no new source or production effect occurred. The exact public revision is freshly confirmed through GitHub’s public commit API. An initial anchored exception failed on staged fragments; pinned scanner source showed that its line slice retains the preceding LF. Final exception allows only that optional LF plus the exact declaration/path. Changed values, other paths and adjacent dummy credentials remain detected. Do not mistake `pre-commit --all-files` with an empty index for a staged candidate scan, and never issue dependent mutations before checking the preceding result.
- PR24 GitHub checks are running for the exact candidate. Root waits for all five expected checks before merge, then requires main CI, Hosting deploy, exact public marker and smoke. PR/commit alone does not complete a release. Native DATA/runtime admission remains paused: Billing identity confirmation, unresolved retention and whole-sequence cost/input qualification, plus future merged-source helper qualification are still outstanding. No model calls, specimen import, new Google refresh, ledger mutation or DATA/runtime deployment was performed in this checkpoint.

### 2026-09-10 — PR24 Linux launch-gate failure retained

- Root coordinator `01a082b2-c2c3-70d2-be90-7bfb622c9102`, branch `codex/release-controls-integration`, candidate `a9639c4c782fdc20e7e2ad7323be0997c07455ba`, PR24. CI/CD run `34443480373`, Python job `102763181777`, failed with 6 failed / 1,918 passed / 75 skipped / 7 warnings. All four other required checks and runtime candidate/image CI passed. Root did not merge or rerun this failed candidate.
- Durable log `/Users/anuragduddu/.codex/rollout-state/specimen-live/release-controls-integration-20260910/PR24_PYTHON_FAILED.log`, SHA `e89c670a7aebc52a8d9e03184df1bcb6bd36c1b27d19b79e7d00798d80176c01`. Two inherited-grandchild and four swallowed-soft-deadline tests fail because their marker files never appear. This is not evidence that the intended child work or cutoff behavior was exercised successfully.
- Product task owns deterministic diagnosis and an additive repair; identity reviewer investigates independently. Current hypothesis is Linux /bin/sh inherited-descriptor redirection above9, which narrow Linux runs with fewer open descriptors may not expose. Root requires actual reproduction, no deadline padding, skips or blind CI rerun. A normal offline Linux fixture is allowed; no privileged/network/native/credential/model effects are authorized for this source test.
- Current public f542 Hosting smoke was refreshed successfully before merge, observed at Unix1789020429.3417149, log SHA `4944bfe68eee274f0fec0ba83bb4f8d2ace899c3ec2122038a89c86e408bc102`. No main deployment occurred. Prior source reviews and local passes remain their recorded evidence; final Linux CI gate is open. Billing, retention, whole-sequence cost/input and ten-specimen live acceptance gates remain open.

### 2026-09-10 — PR24 gate successor validated and pushed

- Root coordinator `01a082b2-c2c3-70d2-be90-7bfb622c9102`; `codex/release-controls-integration` now commits `1df16bea090b1535c442c6fd543f25affc964374` on prior `a9639c4c782fdc20e7e2ad7323be0997c07455ba`, same PR24. Only the launch source, new regression file and append-only session entry changed; actual commit/pre-push hooks passed. No branch/worktree cleanup occurred.
- Fresh `scripts/ci/verify.sh` passed on the unchanged final staged successor: 1,924 Python / 80 skips / 7 warnings; 149 Flutter / 7 skips; clean analysis, release web build and safety hooks. Log SHA `ed024dc3cfd11dd823837b4956f75534a6ab9eb96880e52cfd5b31b84adee890`.
- Independent exact gate review `ff8b083015fa7570118d3d63ffd9abd7d78e222bfee83c36412692e01785c7c7` passed18 focused Linux cases with64 open descriptors, including all six original failures plus11 gate/isolation/boundary cases. It verifies pre-release startup isolation, durable-record/cancel/deadline failures, exact argument/environment/process identity, bounded EOF/token handling and descriptor closure. Only the gate segment differs in AST; no concrete concern warranted broad unrelated Node/Docker replay. Earlier Node/Docker runs remain predecessor evidence.
- Final source `ef089ea38e8c908d22a714b07e0558a30d6ad730c7d04d615a6755be08dadd31`; unchanged consumerfb31b7a and scanner configd55da329. Original CI failures and deterministic7-failure Linux RED remain intact. New GitHub checks run on the new exact source; no blind retry of the failed candidate or merge before checks. Native DATA/runtime, billing, retention, whole-cost and live-ten acceptance remain outstanding.

### 2026-09-10 — PR24 pre-merge checkpoint

- Coordinator `01a082b2-c2c3-70d2-be90-7bfb622c9102`, `codex/release-controls-integration`, PR24 candidate `1df16bea090b1535c442c6fd543f25affc964374`. Exact CI/CD pull-request run `34445501996` completed successfully; all five required jobs passed, Hosting correctly skipped on the PR. Full CI record SHA `b9885859c3ff5b2f734fa39bd028b99e5b108dda163e943c305722dea097f62e`; main freshly remains `f542604dc67ae12a6579b3dfe0d01d1e4b5b2e46`, PR merge state CLEAN.
- Local canonical1924Python/149Flutter and independent gate18-case review `ff8b083015fa7570118d3d63ffd9abd7d78e222bfee83c36412692e01785c7c7` are retained. Root may perform the normal exact-head merge; no branch deletion, force/admin merge, source bypass or direct deploy. Main CI, Hosting deploy and exact public marker/smoke remain required afterward. Native DATA/runtime and live-ten cost/access acceptance remain blocked separately.


## Coordinator Hosting delivery checkpoint — 2026-09-10T06:49:15Z

PR24 is merged as `6e6d5b814ee8103d109bd811d871957fe6a9c611`. Final candidate `1df16bea090b1535c442c6fd543f25affc964374` passed all five PR checks before normal merge. Main CI/CD `34446008176/1` passed all six jobs, including Hosting `102772591575`; runtime candidate `34446008215/1` passed all four jobs. The public marker matches source/run/attempt and strict root smoke passes. Public verification SHA `b1afc4ad7b38cccf6a0cb992fdef7b2f28d679f7697fdd90eb0090fadb82258e`; frozen delivery manifest `5a4a7909443b8ecac7940ca1df6dee4afc8f552f57e11fa5afd2b60fcd6abaef` under the private `release-controls-integration-20260910/gate-successor` evidence directory.

This is a verified Hosting/tooling release. DATA `34446008196/1` and runtime `34446008278/1` failed admission; all seven privileged follow-on jobs skipped with zero steps, independently verified in review `67ae21142859918402412afb089ad1dd91b9fda046bce86e16197c6e0ad2079a`. DATA still exposes the older aa7 source authorization; runtime release inputs are empty. The exact private first failing predicate is unprinted. Do not rerun these attempts or relabel old f542 source certificates; future reviewed input production must include these new actual history rows and explicitly qualify the new merged source.

Next engineering work remains: finish current-source operational helper and complete cost/input qualification, protected DATA/runtime preparation and activation, paired API/Hosting configuration, then all-ten authenticated import, all-region/two-reader processing and human compare/correct/save/reopen. Billing's private Google identity check and the pending post-test image-retention choice are unresolved user gates. The image-only proposal does not authorize secret retention or other unspecified liabilities. No new tool/key/account is requested. Current commitments remain USD1.2724, not an invoice; full USD5 eligibility and live product acceptance are Not confirmed. Cache cleanup remains due2026-09-10T21:17:07Z with the original exact generations and reservation.

Existing task/model assignments and protected workflow harness remain in place. Canonical coordination edits and all worktrees/branches are preserved; no archive, deletion or pruning. See `CURRENT_RELEASE_CHECKLIST.md` for current decisions and todos.

Additive final Hosting review `755a6fbd775cd531b6341b6e515998f4b75b08544287f5e786e39f4a3429eac4` passed the retained exact-source main/run/attempt/marker/smoke chain. Its scope is Hosting only; prior source/admission review and remaining gates are unchanged.


## 2026-09-10T15:06:21Z — resumed release with confirmed console access and retention approval

- Root task `01a082b2-c2c3-70d2-be90-7bfb622c9102`, canonical branch `codex/cohort-budget-admission`; coordination edits only. User said they are logged into GCP/Firebase and accepted the previously proposed additional USD1. In context this approves up toUSD1/month ongoing release-image retention; original USD5 cumulative test/all-ten/all-regions/two-reader scope remains. Do not ask this decision again or infer unlimited pay-as-you-go authority.
- Actual Firebase connector and native Chrome now confirm the configured operator, active production project716045864126, billing enabled and Blaze. The browser extension inventory exposed another Chrome profile; native Chrome reached the existing configured profile. Original open GCP tab used another project/account. Root verified the production project's linked Firebase Payment account before reading costs. No password, key or account recreation is required; no identity challenge remains on this access check.
- Actual Billing report has one project option, specimen-digitization, and Sep1–10 Cloud SQL usageUSD0.71/other savings-minusUSD0.71/rounded totalUSD0.00. The previous overview renderedUSD0.69 before the report loaded. These are actual displayed observations, not a settled invoice, complete provider bill or ledger refund. Original ledger80c69752/1.2724 remains unchanged. Existing Cloud SQL trial banner says87days remain and standard pricing beginsDec6; no trial/plan/resource modification performed.
- Live app still shows collection sign-in. Firebase owner account exists and is enabled but emailVerified remainsfalse. No password reset/verification message or app sign-in was submitted. Console authentication is resolved; future owner app sign-in/verification remains a distinct acceptance step.
- Private normalized actual observations `/private/tmp/specimen-login-billing-recheck-20260910/CHECK_RESULT.json` SHA `99468a8bedf87187208f00879148854bc588fae65edb54085c4791c59215cd29`. Root GitHub Git commit API confirms merge6e6d5b8 tree1709b781978dcd8f0ed35322059e87e7e08b2d72, identical to local1df16bea tree; parentsf542/1df retained in MERGE_TREE_OBSERVATION.json. This confirms source equality without renewing native packets or changing Git refs.
- Cost/source agents are performing bounded follow-ups for the now-approved image allowance and exact PR24 helper dependencies. Current finding: new release_google imports release_publication_deadline; prepared DATA/runtime source snapshots must include that module, and actual issuers must use the already-reviewed lossless encoding seam. Root owns native effects. No deployment, model processing, import, authentication-refresh command, ledger mutation, cloud permission change or pruning in this checkpoint. Full end-to-end acceptance remains Not confirmed. Original SAM cache cleanup remains due2026-09-10T21:17:07Z.


## 2026-09-13T00:56:50.632059+00:00 — Current live release and remaining admission gates

Magic-link sign-in shipped independently on `codex/magic-link-signin` through PR25 and was completed with the existing museum account. After PR27 Hosting deployed source `0875f15dd9e56e82d14a5b6a7bf90bc73719fba2`, a live browser reload retained that signed-in session. It still shows **Collection connection required**. The authenticated import, both-reader pipeline, correction/save/reopen journey is not accepted. Current source passed canonical2,050Python/205Flutter tests, all five exact-source checks, main Hosting103644198036, matching public marker and strict smoke. DATA34727278181/1 and runtime34727278145/1 stopped at admission with no privileged steps; no hand deployment substitutes for them.

The PR27 operational helper package is frozen at `/private/tmp/specimen-pr27-operational-helpers-20260912`, manifest979bd376e70f448c118c26c8245412857176abeb05a053f8f723209edd979c1d. Author83 focused tests and four import/constructor checks passed; independent review is active. Its descriptive current operator count12 is incorrect: actual prior11 plus five new cleanup rows equals16. Root preserved the package and appended correctiond63c673d41f44514ab807591bf8644c4adcfc60d6f467be7063d870e4c5d7cf9 at `/private/tmp/specimen-pr27-helper-accounting-correction-20260913/CORRECTION.json`. The reviewer is exercising the16-row synthetic constructor/codec case without touching the active ledger.

The reviewed locale successor completed one ordinary Firebase SDK refresh and four Storage metadata reads. Independent actual outcome501361181bdca6fd7e71a1d5fd717da356286cf290871b74d51ba1c0038d6546 verifies the original eight live cache generations, complete unchanged bucket/policy and no soft deletion. Five management reads then returned404SAMservice,404workerjob,200emptyexecutions,200two standard project sinks and403organization sink inventory. The helper stopped correctly at403. No model invocation or deletion occurred; the refresh fence is consumed while the cleanup fence remains absent. Organization destination-cost applicability remains unresolved; review8b61e4241b3b2a62fc00e7f1c48424859377041ffac84b85ea5611b40b26efb6 explains why another project-only read cannot close it. Nine of20 diagnostic GETs used.

The latest unchanged ledger0ce36a8bd10f2abec173772ed206d80059d53844948e847637efdd828f284c34 reservesUSD1.3224, including priorUSD1uncertainty. Exactly10 local originals produced25SAM regions; unchanged both-reader and SAM bounds already bring the incomplete subtotal toUSD5.5224 before other release costs. The user's USD5-versus-USD8 choice remains pending; current ceiling staysUSD5. Separate up-to-USD1/month image-retention approval remains in force. Neither Blaze nor an expired execution window increases this authority. Current-source native qualification, full-sequence cost/time fit, protected DATA/runtime and independent live acceptance remain required.

No branch, worktree, prior evidence, intent or ledger history was removed. Current checklist and shared closeout retain owner assignments and the precise remaining work.


### 2026-09-13T01:07:46.514778+00:00 — PR27 helper source review closed

Independent review `b04a3d9b5277a45b5cf4cdb0ca4bac608963c9cce19786ce1dc5eb767839cf5b` passes83focused cases, two fresh imports, two constructor replays and both16-operator synthetic integrations, including allfive runtime bundles and four liability/history negatives. All757predecessors and250author artifacts remain unchanged. The descriptive operator count is resolved by pinned additive correctiond63c673d; no executable finding or further source repair. Review manifestacbe8b8fc4e057305f335f017ef6f6f41907f307becf016e560037ccfc611398 is retained. Source-only work is complete; actual current inputs, budget decision/full-cost fit, protected DATA/runtime and ten-specimen live acceptance remain gated.


## 2026-09-13 — DATA initialization priority after PR29

Magic-link work remains isolated on `codex/magic-link-signin` (PR25); its recorded real-account sign-in and session persistence are accepted. The parallel DATA repair merged as PR29 `f9a445437efd59e0fe3b20c041b25811bf677a03`, with exact main CI34768186129/1, Hosting103753711665, public marker and canonical smoke verified by the DATA task. This establishes source/Hosting delivery, not a connected collection or full product acceptance.

The shortest active path is initialization, with later owner-bootstrap work prepared independently:

| Owner | Current bounded task | Completion gate |
| --- | --- | --- |
| Root coordinator | Exact operator/phase budget, bounded credential refresh/handoff, actual input assembly and protected execution | Current independent reviews, original immutable fences and finite source/run/attempt scope |
| `/root/cache_cleanup_reconcile` | Initialization helper v2 accepting only the complete observed SQL revision12 configuration | Author121 tests/134 subtests passed; independent review pending; author paused for priority |
| `/root/identity_registration_review` | Actual IAM/claim/input review, v2 compatibility and credential-wrapper adversarial review | Fresh49-value capture and literal exact action review before unchanged two-effect setup |
| `/root/complete_pilot_cost` | Exact candidate ledger/category/duration and one new refresh accounting | All historical rows/uncertainty preserved; cumulative total belowUSD5 |
| `/root/sam_results_cost` | Separate three-permission owner-bootstrap IAM helper | Core23 tests pass; native wrapper still unfinished; paused to free the initialization review slot |
| DATA task `01a082b4-a9bc-7413-a3c5-505b61c2f4db` | Source/CI coordination and current static proof package | Current source proof package delivered; bootstrap and product work remain separate |

Agents retain the existing task model settings and the recorded TDD/independent-review harness. Current read-only evidence confirms only the original empty temporary schema, no application database/connector, unchanged eight expired initializer-related IAM bindings, and empty current/versioned/soft-deleted release-claim lists. The sole historical preservation difference is the SQL etag/settings revision6→12. The new helper binds the entire actual revision12 body; it does not ignore etags or adopt future drift.

The numerical DATA-only engineering proposal isUSD4.016903 including the unchangedUSD1.3224 ledger, current diagnostics/shared artifacts, initialization, optional inventory/owner-bootstrap headroom, the newUSD0.0003 SDK-refresh allowance andUSD2.25 for the entire existing SQL lifetime through2026-09-14T18:00:00Z. This remains an uninstalled review candidate; it is not an invoice guarantee or a model-pilot budget. No historical uncertainty is refunded. The source horizon is fixed and does not authorize source shutdown/deletion. Later bootstrap IAM helper expenses still require their own finite mapping within remaining headroom.

A separate optional catalog inventory is not mandatory absent a concrete discrepancy: the protected initializer verifies actual source catalog/absence before acquiring the original restore claim or creating backup/clone liabilities. Once exact inputs qualify, use the original DATA34768186119 main-push run's next reviewed attempt; no manual dispatch or workstation deploy. Bootstrap follows persistent schema readiness, with exact original scope/identity and encrypted evidence. Runtime activation, ten real imports, all25 regions/two readers and human compare/correct/save/reopen are still outstanding; the paid model scope is not silently reduced.


### 2026-09-13 execution gate after successful actual metadata capture

Magic-link sign-in remains the independently branched and already released slice. PR29 source/Hosting and initializer-v2/source/cost checks are complete. The current live DATA setup reached actual49-read capture and independent exact two-action review. Automatic approval review then rejected the IAM execution twice before process creation, requiring explicit user approval for the persistent create-only claim role plus eight existing temporary DATA bindings. A single decision card is pending. Preserve original scope expiry1789319973, all captures, the consumed SDK-refresh fence, and every budget hold. No IAM/database/backup/claim/schema/environment/workflow mutation occurred. Hold fresh GitHub capture and bootstrap; after approval reconcile only expired actual inputs and any additional read cost, without resetting original evidence or bypassing protected workflows.


### 2026-09-13 explicit IAM approval received

The user replied “Approve these exact IAM changes” in root. The permission gate in the preceding entry is resolved; preserve the earlier rejection and expired-scope evidence. Current private approval is d389e138; current recorded cumulative ledger e37d1a59 totals3.7243, with proposed protected initialization4.0293 and total including optional allowances4.059303 under USD5. No new credential refresh is required: current cached identity and exact grants passed the unchanged exporter check.

Next: finish the two narrowly identified GitHub collector defects and private descriptor staging, open one fresh bounded setup scope, capture/review/apply the exact two IAM effects, verify readback, then derive/issue/install the reviewed DATA inputs and replay the original main-push run through its protected workflow. No fresh scope is opened while collector preparation is incomplete. Source PR29 f9a remains unchanged pending fresh source verification. End-to-end product acceptance remains outstanding.


### 2026-09-13T20:37Z — Approved IAM applied; final reconciliation pending

The explicit IAM approval was executed. Both requested native effects returned HTTP200; independent review af5590b5 confirms the exact role and all23 policy bindings. The original helper stopped on reordered bindings, leaving final readback unperformed. The effect fence is consumed and must never be replayed. Author, identity reviewer and cost reviewer are preparing a separately reserved read-only49+6 reconciliation that preserves this partial transcript.

The initializer requires3600 seconds remaining before its original21:40:15UTC expiry, so issuance closes20:40:15UTC. Original write scope ended20:35:15; no automatic renewal or reduced timing margin is allowed. Hold a new GitHub capture and protected initialization until the entire actual contract passes. Current ledgerUSD3.7243 retains every old reservation. No database, restore, schema, environment or workflow effect has been performed; the ten-specimen live journey remains outstanding.


### 2026-09-13T20:56:42Z — IAM verified; initialization start window closed

The user's exact IAM approval is complete: role creation and the conditional policy update succeeded, then55 independent read-only observations verified the entire resulting state. Independent actual review714e6dbe confirms all23 policy bindings and same native etag, the create-only role, original transcript preservation and no repeated IAM effects. Root final outcome is `/private/tmp/specimen-pr29-root-iam-final-readback-20260913/FINAL_OUTCOME.json`.

Initialization remains paused at its original3600-second remaining-validity gate, whose20:40:15UTC start cutoff passed during verifier repair/review. No database, schema, environment or workflow mutation ran. The distinct read-only68866299/a55ba43c receipts cannot substitute for original setup success. Original scopes/fences and unchanged controllers remain preserved; no new permission window has been issued. Current cumulative commitments areUSD3.7344, not an invoice; the full-ten model pilot and live compare/correct/save/reopen journey remain outstanding.


### 2026-09-13T21:38Z — Review-readiness work resumed before new clocks

The owner explicitly resumed completion in the DATA task; root verified the actual user record (b766d135). Prepare all source, consumer compatibility and input constructors before the next reviewed temporary permission window. Root owns native effects and ledger; author/reviewer/cost lanes work independently; DATA owns the comparison-screen regression and app acceptance audit. Any resulting source change must pass the normal PR/main/Hosting path before final operational source qualification.

Full cost fit is now an early dependency: current reservations3.7344 +readers3.70 +DATA0.305 +SAM0.50 =8.2394 before remaining work. Keep the unchanged5 ceiling until an explicit current decision; do not reuse the old8 suggestion as an adequate quote. Budget source gates require a reviewed source/authority change for any approved higher ceiling. No fresh credentials, clocks, IAM renewal or paid workflow starts while whole-path affordability is unresolved. The same ten specimens,25 regions,both readers and human compare/correct/save/reopen remain the acceptance scope.
