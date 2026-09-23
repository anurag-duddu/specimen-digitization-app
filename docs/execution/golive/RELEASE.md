# Release workstream: data and runtime planes on merge

Status: active, started 2026-09-23. Owner: the go-live session "Release data
and runtime planes on merge" (S2), brief
[`briefs/S2-release-planes.md`](briefs/S2-release-planes.md). This page holds
the workstream's spec deltas, one section per pull request, under the
program's [master plan](PLAN.md).

## 1. Authority and invariants

The owner's decision G11 of 2026-09-23
([PLAN section 2.1](PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator))
governs this workstream: "Data and runtime releases deploy automatically on
merge, like Hosting: once the required checks pass and the PR steward approves,
a merge to `main` deploys runtime code and additive schema changes. Branch
protection, the required checks, keyless identities and main-only environments
stay. Envelopes, cost ledgers, independent-review reports and authorization
artifacts retire for this program."

These invariants hold for every pull request in this workstream and are never
traded for a passing release:

- Nobody deploys from a workstation or an agent shell. Only
  `.github/workflows/runtime-release.yml` and
  `.github/workflows/data-release.yml`, triggered by a push to `main`, deploy
  the runtime and data planes; Hosting stays on `.github/workflows/ci-cd.yml`
  with its own isolated identity.
- Branch protection, the five required checks, the main-only GitHub
  environments, pinned action SHAs and the Workload Identity Federation
  conditions are never weakened.
- Every plane verifies `GITHUB_REF_PROTECTED=true` and all five successful
  checks on the exact merged commit before it obtains a Google credential.
- Credentials are keyless and short-lived; no service-account key exists.
- Runtime images are immutable, attested and built from `main`; every deploy
  verifies readiness before it reports success; missing evidence fails closed.
- The data plane applies additive schema changes only, as PLAN section 4.4
  defines them: new tables; new nullable columns; dropping NOT NULL, but only
  on columns the data contract names with a reason and never on provenance or
  idempotency keys (`ModelObservation.runId`, `regionId`, `provider`,
  `modelVersion`, `stepKey`); new indexes, unique constraints and foreign keys
  over new columns only; and new connector operations, each
  `@auth(level: NO_ACCESS)` with the membership `@check`s (`DATA.md` 73). The
  gate refuses everything else: dropped or renamed tables and columns, type
  changes, adding NOT NULL, key changes, uniqueness over existing columns,
  changed or removed operations, and operations at any other auth level.
- Branch protection and the repository's visibility stay as they are
  ([DEPLOYMENT.md, branch and repository protection](../../DEPLOYMENT.md#branch-and-repository-protection)).
- IAM writes and secret creation are owner actions, taken from a reviewed list
  a read-only script prints (T4). No workflow and no agent creates IAM policy.
  Every grant names its resource and its reason; no identity receives Owner or
  Editor. Standing grants go only to the ordinary data-release, runtime-build,
  runtime-release and runtime identities, plus the `allUsers` invoker on the
  API. The one-time roles never get a standing grant: the initializer role,
  `specimenDataOwnerBootstrap` and `specimenDataInitializerDisposal` stay
  one-time and time-bounded through the existing setup-window path
  (`scripts/ci/data_setup_window.py`) and are revoked after use. That window
  grants the initializer role for 75 minutes; `docs/DEPLOYMENT.md` separately
  caps the initializer's privilege window after native parity at ten minutes.
- No private value (administrator or bootstrap identities, organization or
  collection ids, tokens) appears in a workflow log or artifact, because both
  are public in this repository.

## 2. T1: contract amendments (documents only)

T1 records the owner decisions in PLAN section 2.1 in every document that
section names as superseded, and in the other documents with a clause those
decisions contradict. It rewrites no history: each superseded clause keeps its original
text and gains a dated note, "Superseded for the go-live program by
`docs/execution/golive/PLAN.md` section 2.1 G#", followed by what now holds.
Each amended release and approval document also carries a dated banner under
its title; `PRD.md` and `CONTRACTS.md` carry notes only. Decisions made after
T1 began are recorded where they supersede a clause: G19 beside the harness
scope in `HUMAN_REVIEW_RELEASE.md`, and G14 and G16 in `PRD.md` (T1b).

T1 lands in two pull requests to stay under the program's size limit. T1a
amends `AGENTS.md`, `docs/DEPLOYMENT.md`, the approvals and the product
contracts the other workstreams code against. T1b annotates the runbooks and
release histories: `GO_LIVE_RUNBOOK.md`, `GO_LIVE_READINESS.md`,
`RELEASING.md`, `RELEASE_RUNTIME.md`, `RELEASE_DATA.md` and
`PROTECTED_RELEASE_HARNESS.md`.

Three documents gain more than notes:

- `AGENTS.md`: only the first deployment rule changes, to G11's release
  requirements. It keeps every safeguard G11 does not retire: a separate
  main-only environment and keyless identity per plane, the isolated Hosting
  identity, all five checks on the exact merged commit, immutable attested
  provenance, verified readiness and failing closed on missing evidence. It
  adds the additive-only schema gate, and the PR steward's review replaces the
  independent review. "Never run `firebase deploy`, a Hosting channel deploy,
  or a `gcloud ... deploy` command from a workstation or an agent shell" and
  the rule listing what is never weakened are unchanged, word for word.
- [`APPROVED_LOGFIRE_TRACING.md`](../APPROVED_LOGFIRE_TRACING.md#go-live-amendment-2026-09-23-g3):
  G3's content scope. System prompts, text inputs and outputs, SAM 3
  parameters and the harness's tool calls with arguments and results are
  permitted; images are never captured; secrets and the identities of the
  app's users are scrubbed; the worker, SAM 3 and the API hold standing read
  access to the writer secret.
- [`APPROVED_RELEASE_BUDGET.md`](../APPROVED_RELEASE_BUDGET.md#go-live-amendment-2026-09-23-g9):
  G9's USD 25 ceiling, cumulative, infrastructure and models together.

No document's bytes are pinned by code or tests, so every amendment is made in
place. `tests/test_deployment_policy.py` requires `AGENTS.md` and
`docs/DEPLOYMENT.md` to keep naming both release workflows and
`docs/DEPLOYMENT.md` to keep naming `RELEASE_AUTHORIZATION.md`; both still do.
The approval digest `3303d129…` in `release_budget.py` fingerprints the owner's
original 2026-09-14 message, not a document, and is unaffected.

### 2.1 Code that still enforces a superseded clause

The amendments change the contract; the code below still enforces the old
clause until the named pull request changes it. Until T2 and T3 merge, both
protected workflows keep failing closed at envelope admission, as they do
today, so no release runs under a contract the documents no longer state.
Line numbers are as of `709ae3c`.

| Code | Still enforces | Decision | Changed by |
|---|---|---|---|
| `scripts/ci/release_admission.py`, `release_context.py`, `validate_release_packet.py`, `mint_release_packet.py` | The release envelope: packet, evidence digests, independent review, authorization, reservation ledger, exactly ten specimens | G2, G11 | S2 T2 (runtime), T3 (data) |
| `src/specimen_digitization/release_budget.py` 14 | `APPROVED_LIMIT_MICROS = 12_000_000` and the v3 ledger checks | G9, G11 | S2 T2 and T3 retire it with the envelope |
| `scripts/ci/mint_release_packet.py` 61, `scripts/qa/live/human_review.py` 29 and 40 | The `human-review-release-scope` artifacts with `"automated_clearance": "deferred"` | G1, G11 | S2 T2 retires the scope binding |
| `scripts/ci/deploy_runtime.py` 113, 544, 549 | SAM expiry within one hour, `LOGFIRE_CAPTURE_MODE=metadata`, one cohort execution by `runExecutionToken` | G2, G3, G11 | S2 T2 |
| `scripts/ci/deploy_data.py` 153, 462 | `writers: "no_runtime_exists"`; no data change once the runtime exists | G11 | S2 T3 (the additive-only gate) |
| `scripts/ci/release_initialize.py` | An absent application database and a `NONE`/`ephemeral` placeholder schema | PLAN section 3 (the database exists and is empty) | S2 T3 |
| `src/specimen_digitization/application/worker_launch.py` 42, `worker.py`, `worker_timing.py` | The `authorized-ten-v1` launch, the ten-specimen loop and the single timing clock | G2 | S3 |
| `src/specimen_digitization/application/sam3_server.py` 617-618 | The manifest binding and the self-shutdown within an hour | G2 | S3 |
| `src/specimen_digitization/observability.py`, `bounded_telemetry.py`, the worker's forced metadata mode | Metadata-only tracing | G3 | S3 |
| `src/specimen_digitization/application/policy.py` 31-34 and 138-139, for the lane | The institutional-approval and semantics gates, and the human-approval gate | G1 | S4 |
| `scripts/ci/worker_trace_setup.py` `grant` | A worker-only writer-secret binding that expires within 24 hours | G3, G11 | S2 T4 (standing grants per identity and secret) |
| `src/specimen_digitization/application/cli.py` 84-90 | The API never sends traces | G3 | S3 |

## 3. T2: runtime plane on merge

T2 replaces the runtime plane's envelope with a gate that derives everything
from GitHub and fixed configuration, then deploys on every push to `main`.
It lands in steps that each keep `main` green: T2a the gate, T2b the deploy,
T2c the workflow, T2d the removal of the runtime plane's dead envelope code,
and T2e the reuse of an unchanged SAM 3 image.

### 3.1 The gate (T2a)

`scripts/ci/release_gate.py` admits a runtime job without cloud credentials.

- Context: `release_context.validate_context` with `envelope=False` checks
  every value the envelope checked except the retired owner-set
  `RELEASE_AUTHORIZED_SHA`: the repository and its numeric ids, the `push`
  event, `refs/heads/main`, `GITHUB_REF_PROTECTED=true`, the workflow ref, the
  commit, the environment, the project and the release identity.
- The commit is on `main`: `compare/<sha>...main` is `identical` or `ahead`.
- Exactly one merged pull request produced it: merged, its merge commit is this
  commit, its base is `main` of this repository, its head is in this
  repository, and its head's tree equals the commit's tree.
- Exactly one CI/CD push run exists for the commit, on `main`, from
  `.github/workflows/ci-cd.yml` in this repository. The gate waits for it,
  polling every 30 seconds up to a bounded `--wait-seconds`, because both
  workflows start on the same push. The run must succeed, and each of the five
  required checks must be exactly one successful job of that run's latest
  attempt, on the same commit.
- It writes a gate record, `protected-release-gate/v1`, owner-only, where the
  envelope packet used to be. The record holds the plane, the commit and its
  tree, the pull request, the CI run and attempt, this run and attempt, the
  issue time, an expiry one hour later, and the plane's fixed Workload
  Identity provider. It exports the record's digest as `RELEASE_PACKET_SHA256`
  for the job's later steps.
- `release_admission.admit` recognizes a gate record and re-admits it with
  `release_gate.readmit`. The digest, plane, run and attempt must match, the
  record must not be expired, the context must pass again, and the same facts
  are observed again without waiting. Envelope packets keep their existing
  path until T2d. The Google client calls `admit` before each mutation and
  needs no change. The publication supervisor needs two small ones, which T2b
  makes: it checks the context without the retired variable, and its
  admission step reads a gate record, which has no plan.
- The CI run's `path` (`.github/workflows/ci-cd.yml`) and the five job names
  the gate requires were checked against the live GitHub API on 2026-09-23.
- The gate does not require the commit to be the tip of `main`. The
  workflow's concurrency group runs one release at a time in push order, and
  the deploy's rollback guard refuses to replace a newer deployed commit.

### 3.2 The deploy (T2b)

`scripts/ci/deploy_runtime.py --deploy` with a gate record:

- Settings: `scripts/ci/runtime_settings.py` commits every non-secret value.
  That includes each secret's pinned version number and the API readiness
  object's name and generation, so a new secret version or marker is a
  reviewed pull request, and the release needs no permission to discover
  them. Private values (the worker's actor uid, and the source registry, which
  holds collection ids) and credentials arrive only as Secret Manager
  references.
- Pending settings: some values are not known yet. The worker's drain
  arguments and SAM 3's environment follow the processing lane's merged server
  code; the secret versions, the readiness marker and the SAM 3 checkpoint
  digest follow the owner's T4 actions. A role with a pending setting is not
  deployed. The receipt names the role and each missing setting, and the run
  still verifies every role it did deploy, so the API can go live before SAM 3
  and the worker.
- Images: the three receipts from this run's build job. Each image's
  attestation is verified: signer workflow `runtime-release.yml`, source and
  signer digest equal to the commit, ref `main`, no self-hosted runners.
- Rollback guard: before changing a resource, its `source-sha` label must be
  this commit or an ancestor of it.
- Order: SAM 3, then the worker job, then the API.
  - `specimen-sam`: zero to one instance, concurrency one, 4 CPU and 16 GiB,
    the checkpoint mounted read-only, Hugging Face offline, traffic to the
    latest ready revision. Its invoker policy must be exactly the worker
    identity.
  - `specimen-worker`: the job definition only. One task, parallelism one, no
    retries, 3,600 seconds, the drain arguments. The deploy never sets an
    execution token and never calls `:run`.
  - `specimen-api`: when a revision already serves, the new revision gets 0%
    traffic under the tag `candidate`. On the candidate URL, `/version`
    reports the merged commit, `/health/ready` passes and an anonymous
    `/v1/session` is refused. Only then does traffic move to 100%, and the same
    three checks run on the service URL. A candidate that fails any later
    check loses its tag, and the previous revision keeps all traffic. Its
    invoker policy must be exactly `allUsers`, unconditionally.
- IAM is verified, never changed. The invoker policies are checked after
  every deployable role is deployed and before the API is promoted, and all
  missing bindings are reported together. The first release creates the
  services, so its check fails with the owner actions it names; the owner
  grants both bindings from T4's list and re-runs the failed job once.
- The deploy writes a `runtime-deployed/v1` receipt without private values,
  attests it and uploads it.

### 3.3 The workflow (T2c)

`.github/workflows/runtime-release.yml` keeps its trigger (push to `main`
only), its read-only default permissions and its uncancelled concurrency
group. Its jobs are:

1. Admission: no credentials. It runs the gate and waits for CI, then for
   the same commit's data release to succeed. Runtime promotion follows data
   readiness (the coordinator's D3 of 2026-09-23). The wait is bounded at 90
   minutes, and the record carries the data run and attempt, so a later
   re-run of either fails re-admission.
2. Build: `runtime-build-production`; one job per image. It runs the gate,
   then the unchanged publication action, then attestation.
3. Release: `runtime-production`. It runs the gate, then authenticates with
   the fixed provider, then deploys.

It reads no `RELEASE_INPUTS_B64` secret and no `RELEASE_*` variable.

### 3.4 After the switch (T2d, T2e)

T2d deletes the runtime plane's envelope code and tests once no workflow
reaches them. The data plane keeps its envelope until T3. T2e reuses the last
attested SAM 3 image when its inputs (`containers/worker/sam3.Dockerfile`, its
lock file and `src/specimen_digitization`) are unchanged, and rebuilds it
otherwise.

## 4. Next pull requests

Each adds its own section here, with failing tests first, as PLAN section 7.2
requires.

- T3, data plane on merge: the protected-ref check and the five-checks check
  move out of the retired admission into the plane's own gate; a first
  initialization that matches the real state; then, on every change to
  `dataconnect/`, a backup with a verified restore path, an additive-only check
  and a compatible apply that works while the runtime runs; a one-time,
  idempotent hierarchy bootstrap whose identities never reach a log or
  artifact.
- T4, the owner's list: a read-only script that prints the exact standing IAM
  grants and secrets T2 and T3 need, each bound to a named resource with its
  reason, plus the initializer's one-time window.
- T5, first releases: the first data and runtime releases; the repository
  variables as an owner action whose private values the owner fills in;
  Hosting rebuilt and connected (DoD-1 to DoD-3).
- T6, deploy health: any failed deploy fixed through a pull request.
