# Production release plan and coordination

Owner: task `01a082b2-c2c3-70d2-be90-7bfb622c9102`, branch `V0.1`, canonical
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
without an approved profile are failures. The evidence-only pilot must remain
clearly labeled and must not be reported as fully qualified automatic processing.
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
| G1 Candidate | Owner audits, TDD repairs, independent review, exact interface/config contracts | In progress |
| G2 Access and scope | Working Google authentication, verified admin, generation-frozen ten-source manifest and allowed provider use | Blocked: fresh Google credential refresh requires interactive reauthentication; remaining evidence Not confirmed |
| G3 Authority and cost | Reviewed release-policy amendment, precise resource/IAM/config plan, approved total/daily budget and hard execution bounds | USD 5 total budget supplied; current Hosting-only rule and exact action/cost verification remain gates |
| G4 Protected delivery implementation | Approved separate data/runtime workflows with negative policy tests, least-privilege keyless identities and immutable provenance | Pending G3; no executable alternate deploy path permitted yet |
| G5 Data readiness | Cloud backup and isolated restore, compatible schema/connector/rules, exact indexes, scoped admin/import and independent readback | Pending authorized cloud work |
| G6 Runtime readiness | Built-once API/worker/SAM digests, real model-loaded health, Google auth/App Check/denials, frozen inputs, safe stop/restart | Pending G4/G5 |
| G7 Integrated release | `scripts/ci/verify.sh`, runtime container CI, all five platform checks on exact PR head; merge through GitHub | Pending candidate and cloud readiness |
| G8 Public acceptance | Green main deploy, exact public marker, matching runtime/data revisions, actual ten-source processing/review/save/reopen and recovery | Not confirmed |
| G9 Closeout | Record complete release receipt, limitations, stop/rollback instructions and append-only learnings; preserve evidence before pruning | Pending G8 |

Use local synthetic fixtures to develop tests, then real isolated data/services,
then the authorized first-ten live cohort. These are separate evidence levels.
Do not use private data or paid inference inside ordinary pull-request CI.

## Concrete release-policy decision

`AGENTS.md` currently says production deployments **MUST** occur only through
`.github/workflows/ci-cd.yml`; it also forbids runtime/data deployment through
that Hosting workflow. `docs/DEPLOYMENT.md` requires an explicit reviewed
amendment before a separate runtime/data workflow exists. Therefore the current
contract cannot deliver the required backend. No active rule is changed by this
plan.

Proposed narrow replacement for the first deployment rule, for user review:

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
Hosting isolation. This policy decision authorizes no unspecified resource/IAM
change or spend. The concrete data/runtime action packet must be reviewed too.

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
- Specialist tasks are active but currently report `waitingOnApproval`: runtime
  and data at their initial coordinator handoff tool calls; acceptance at public
  browser inspection. Pending approval is not a test result or a rejection.
- After account-owner reauthentication, data owner performs one read-only refresh,
  then prepares the exact freeze/bootstrap/restore packet. Do not repeat failed
  credential probes or enable APIs simply to make inventory succeed.
- Next irreversible phase waits for the specific policy/resource/cost authority;
  locally authorized tests, fixes and review may continue meanwhile.
- Before pruning the old `codex/live-*` branches at the user's cleanup request,
  reconcile and preserve their ignored evidence, append owner closeouts, and
  confirm all source is reachable from main. The unfinished real-model worktree
  must remain until its four untracked source/report paths are integrated or
  explicitly preserved. No removal was authorized by this checkpoint.
