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
artifacts retire for this program." G30's per-call reservations stand
(PLAN 4.3; the coordinator's ruling on the mechanism).

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
  defines them:
  - new tables and new nullable columns;
  - dropping NOT NULL only on columns the data contract names with a reason.
    Never on a key column, a column of any unique constraint, or the
    provenance and idempotency keys: `ModelObservation.runId`, `regionId`,
    `provider`, `modelVersion` and `stepKey`, and TRN-005's `rawAssetId`,
    `promptVersion` and `inputSha256`. The gate refuses these even when the
    contract's list names them;
  - one closed exception, by coordinator ruling (#88): `SourceAsset`'s
    `specimen_unique_1` on (bucket, objectName, generation) gives way to
    `source_asset_specimen_object` on (organizationId, collectionId,
    specimenId, bucket, objectName, generation). Every added column is an
    existing NOT NULL column. It takes two applies, create before drop, and
    the drop comes only after a read-back of the live database shows the new
    constraint in place. The gate admits exactly these two steps from its
    checked-in list;
  - new indexes, unique constraints and foreign keys over new columns only;
  - new connector operations, each `@auth(level: NO_ACCESS)` with the
    membership `@check`s (`DATA.md` 73).

  The gate refuses everything else: dropped or renamed tables and columns,
  type changes, adding NOT NULL, key changes, new or changed uniqueness over
  existing columns other than that exception, changed or removed
  operations, and operations at any other auth level.
- Branch protection and the repository's visibility stay as they are
  ([DEPLOYMENT.md, branch and repository protection](../../DEPLOYMENT.md#branch-and-repository-protection)).
- IAM writes and secret creation are owner actions, taken from a reviewed list
  a read-only script prints (T4). No workflow and no agent creates IAM policy.
  Every grant names its resource and its reason; no identity receives Owner or
  Editor. Standing grants go only to three groups:
  - the runtime-build, runtime-release and runtime identities;
  - the data-release roles that automatic applies need:
    `specimenDataSchemaPublish`, `specimenDataStorageRules` and
    `specimenDataSourceBackup` become standing, and
    `specimenDataInventorySqlConnect` and `specimenDataInventoryProjectRead`,
    already standing, keep their conditions unchanged;
  - the `allUsers` invoker on the API.

  Every other data-release role stays time-bounded:
  - `specimenDataCloneCreate`, `specimenDataCloneControl` and
    `specimenDataRestoreAllowanceClaim` open only for the first apply's single
    restore check, whose claim is the single-use allowance of
    `CLONE_ALLOWANCE.md`. That check is D1, the coordinator's ruling for T3 of
    2026-09-23: a backup before every apply, and one clone restore proof.
  - `specimenDataRuntimeAbsence` stays time-bounded too, though no automatic
    apply uses it.
  - The one-time roles never get a standing grant: the initializer role
    (`specimenDataInitializeTemporary`), `specimenDataOwnerBootstrap` and
    `specimenDataInitializerDisposal` stay one-time and time-bounded through
    the existing setup-window path (`scripts/ci/data_setup_window.py`) and are
    revoked after use. That window grants the initializer role for 75 minutes;
    `docs/DEPLOYMENT.md` separately caps the initializer's privilege window
    after native parity at ten minutes.
- The setup-window path keeps every binding it manages time-bound. Run the
  window first or adapt the path, never fall back to a grant without a time
  condition, and list the revocation commands.
- Before every apply, an on-demand backup must succeed and point-in-time
  recovery must be on; the first apply also restores that backup once into a
  clone and checks it (D1). After every apply, the supplemental SQL indexes
  are re-created concurrently and each is checked by definition.
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
  G3's content scope with G26 applied. System prompts, text inputs and
  outputs, SAM 3 parameters and the harness's tool calls with arguments and
  results are permitted, except that a Google geocoding result keeps only the
  place ID, the pipeline's outcome and a response fingerprint. Images are
  never captured. Secrets and the identities of the app's users never enter
  prompts or tool arguments, and scrubbing is only the backstop. The worker,
  SAM 3 and the API hold standing read access to the writer secret, bound to
  its exact version.
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
| `scripts/ci/mint_release_packet.py` 61, `scripts/qa/live/human_review.py` 29 and 40 | The `human-review-release-scope` artifacts with `"automated_clearance": "deferred"` | G1, G11 | S2 T2 retires `mint_release_packet.py`'s scope binding; S2's checker pull request, after T3d, retires `human_review.py`'s (the scope row below) |
| `scripts/ci/deploy_runtime.py` 113, 544, 549 | SAM expiry within one hour, `LOGFIRE_CAPTURE_MODE=metadata`, one cohort execution by `runExecutionToken` | G2, G3, G11 | S2 T2 |
| `scripts/ci/deploy_data.py` 153, 462 | `writers: "no_runtime_exists"`; no data change once the runtime exists | G11 | S2 T3 (the additive-only gate) |
| `scripts/ci/release_initialize.py` | An absent application database and a `NONE`/`ephemeral` placeholder schema | PLAN section 3 (the database exists and is empty) | S2 T3 |
| `src/specimen_digitization/application/worker_launch.py` 42, `worker.py`, `worker_timing.py` | The `authorized-ten-v1` launch, the ten-specimen loop and the single timing clock | G2 | S3 |
| `src/specimen_digitization/application/sam3_server.py` 617-618 | The manifest binding and the self-shutdown within an hour | G2 | S3 |
| `src/specimen_digitization/observability.py`, `bounded_telemetry.py`, the worker's forced metadata mode | Metadata-only tracing | G3 | S3 |
| `src/specimen_digitization/application/policy.py` 31-34 and 138-139, for the lane | The institutional-approval and semantics gates, and the human-approval gate | G1 | S4 |
| `scripts/qa/live/human_review.py` 52 and 124 | `HUMAN-NO-AUTOMATIC-CLEARANCE`'s clause that correction and save never enable automatic clearance (`RELEASE_ACCEPTANCE.md`'s HUMAN-NO-AUTOMATIC-CLEARANCE row). The rest of the subcriterion stays: correction and save never approve institutional semantics or risk, which 194-195 enforce, no clearance with mandatory values unresolved, an operational failure never labelled Deferred (QUE-005), and review state and history surviving | G1 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 194-200 | Every run stopped at the review block, `processing_blocked` with `pilot_evidence_review_required` (198-200), which `evidence_pilot.py` 230-233 sets, with `human_approved` false and a null disposition (196). The profile's `institutional_policy_approved` and `semantics_confirmed` stay false (194-195): the check that a correction or save never approves institutional semantics or risk, since PLAN section 4.1 stage 8 removes the lane's gates but sets no institutional flag. The replacement keeps the rule that an operational block cannot qualify | G1 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 103 and 168 | The frozen manifest as the cohort's anchor: its digest on every human case (103) and its specimens (168). The cohort and the denominator stay ten, in order (G2), and the checks the manifest anchors stay, re-anchored to the ten: no duplicate or outside-cohort record (175), a record for every one of the ten (169, 290), the evidence fields (172-173), and the original-bytes and collection-scope checks (177-190, 235-237). Each of the ten the harness did not clear needs its complete human record. A specimen the harness clears keeps its original, SAM receipt, masks, raw readings and crops, with their checks (177-190, 218-289), and the lane's coverage confirmation (208, next row); only the other review checks (201-207, 209-217) drop out for it (G1) | G1, G2 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 51, 124 and 208 | HUMAN-LABEL-COVERAGE as a manual subcriterion (51, required at 124), and `coverage_confirmed` as a human's confirmation on each saved record (208). In the coordinator's reading of G15 (its message to S2 of 2026-09-24, 01:00Z on 09-25, answering #184's round-1 question), the lane's automatic coverage check is the confirmation for every record: the checker reads the lane's `coverage_confirmed`, which S3 sets from that check, for each of the ten, and a record whose check fails went to the human queue | G15 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 224, `scripts/qa/live/acceptance.py` 431 and 443 | Each SAM receipt, the report and every case row bound to the frozen manifest's digest | G2 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 298-304, `scripts/qa/live/acceptance.py` 348-420 and 512-517 | COHORT-BUDGET and the cohort ledger it reconciles, which retire with the other cost ledgers (G11): the ledger's version (300-301) and approval digest (303), the case pending while the ledger is missing or not live (`acceptance.py` 516-517, kept pending at 304), and `cohort_budget` (`acceptance.py` 348-420) whole, with its USD 5 or USD 12 cap (352, 375), manifest binding (366), authorization reference and scope (367-371), eleven reconciled categories (378-388), and entries and totals (389-420), together with the report's `budget_exposure_microusd` (527) and the `--budget-approval-sha256` argument (540, 544). The bound is G30's USD 5 production model allowance, which the pipeline enforces across every paid step and COST-BOUNDS tests, within G9's USD 25 ceiling, cumulative, infrastructure and models together (PLAN 4.3). G30's per-call reservations stand (PLAN 4.3; the coordinator's ruling on the mechanism): the COST-BOUNDS live case (`LIVE_QA.md`'s threat matrix) tests them, and two of the ledger's rules move there with them: an unknown effect keeps a positive reservation (400-403), which COST-BOUNDS already requires, and the sum is cumulative across days and sessions, never reset (368-371, 417-418), as G30's allowance is (PLAN 4.3). DEPLOYMENT-PROVENANCE, which 304 also keeps pending, stays, but for the SAM commit check in the next row | G9, G11, G30 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/acceptance.py` 497 | DEPLOYMENT-PROVENANCE's `sam_commit_sha` equal to the candidate. T2 rebuilds SAM 3 only when its inputs change (section 3), so once it reuses an image, the deployed SAM 3 can come from an earlier merged commit. The check keeps SAM 3 bound to the candidate: its commit is the candidate, or is on main at or before the candidate with SAM 3's inputs unchanged between the two (T2's reuse rule), and in both cases the candidate's own release run deployed the image built from that commit. A digest the candidate's own run did not deploy fails. The rest of DEPLOYMENT-PROVENANCE stays (480-511): the repository; the Hosting, API and worker commit SHAs equal to the candidate; the main workflow, deploy job and runtime workflow URLs; the connector and Storage-rules revisions; the SAM model id, revision, checkpoint and configuration digests; the three image digests; and the main workflow's and deploy job's success. The next row binds the revisions and digests to the candidate | G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/acceptance.py` 482-493 and 502-507 | DEPLOYMENT-PROVENANCE's deployment evidence taken at face value: the workflow URLs and the connector and Storage-rules revisions need only be non-empty (482-493), and the three image digests only well formed (502-507). In S2's reading of G11 and PLAN 4.6, as DEPLOY-IDENTITY reads, the checker binds them to the candidate, each from its release run's own evidence. The API and worker digests bind to the candidate's own runtime release run. The connector and Storage-rules revisions bind to the data release run that deployed them: the candidate's own, or a main run at or before it with those inputs unchanged between the two | G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 315 | The report's `deferred_capabilities`: `automated_clearance` is no longer deferred (G1), and there is no classification stage to defer (G14) | G1, G14 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 333-334, `scripts/qa/live/acceptance.py` 545-548 | The approved manifest's digest pinned on the command line (333; `acceptance.py` 545), and the manifest read under it (334; `acceptance.py` 547-548). The pin and the read stay, on the ten's private record, `specimen-pilot-reference/v1`, in place of the manifest (the coordinator's ruling in its message to S2 of 2026-09-24, 01:15Z on 09-25). S7 writes it after PLAN section 8 step 2 imports the ten, the coordinator verifies it against DoD-4's subject ids, and its SHA-256, supplied separately, pins it on the command line. The read keeps `private_manifest`'s checks (`acceptance.py` 116-133): outside Git, no symlink, a regular file its reader owns with mode 600, at most 1 MiB, and exactly the pinned bytes. The candidate-SHA pin on the same lines stays (333; `acceptance.py` 546) | G2, G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/acceptance.py` 136-268 (`manifest_ids`, called at 424 and 549, and by `human_review.py` 306 and 335) | The `specimen-pilot/v1` manifest as an authorization: its `ready` status (152-154), its authorization reference (156-163) and the frozen source inventory's digest (165, 169), and its schema name (150) and `project_id` (155), which `specimen-pilot-reference/v1` doesn't carry. The rest stays, on the ten's private record (the pin's row above), including exactly ten canonical specimen UUIDs in explicit source order, one collection scope, each original's bucket, object, generation, SHA-256 and size, each generation assigned once, and the application-source binding | G2, G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 105-108 and 123, `scripts/qa/live/acceptance.py` 449-452 and 476 | Coverage drawn from the manifest: each case's specimens inside it and without duplicates (105-108; `acceptance.py` 449-452), and full coverage of its ten (123, for every manual subcriterion but HUMAN-ACCESSIBLE-REVIEW, which 122 exempts; `acceptance.py` 476 for the full-cohort cases). They stay, re-anchored to the ten, and the cohort and the denominator stay ten (G2) | G2 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 61-69, 74, 295-297, 310, 324-325, 330-332 and 337 | The human-review scope: `validate_scope` (61-69), the skeleton's scope pin (74, 337), the scope decision validated and pinned in the report (295-296) with `amended` (297), the report's scope (310), and the scope arguments and authority checks (324-325, 330-332). The scope artifacts retire with the other authorization artifacts (G11), and so do the checker's scope definitions at 29 and 40, which this table's `mint_release_packet.py` row also names. What the scope never granted stays: no sensitive access and no infrastructure authority | G1, G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/qa/live/human_review.py` 311 and 314, `scripts/qa/live/acceptance.py` 525 | `ready_for_independent_review` as the passing preflight verdict. In S2's reading, G11 retires the independent-review reports, not the decision, so passing evidence goes to the acceptance decision of the evidence-based acceptance harness and the coordinator (`PROTECTED_RELEASE_HARNESS.md` step 8; the coordinator's acceptance sign-off, PLAN section 6), beside the owner's own DoD-6 confirmation | G11 | S2, after T3d (the coordinator's assignment of 2026-09-24) |
| `scripts/ci/worker_trace_setup.py` `grant` | A worker-only writer-secret binding that expires within 24 hours | G3, G11 | S2 T4 (standing grants per identity and secret) |
| `src/specimen_digitization/application/cli.py` 84-90 | The API never sends traces | G3 | S3 |
| `scripts/ci/data_setup_window.py` 55-65, 126-138 | Renews three of the standing roles (`specimenDataSchemaPublish`, `specimenDataSourceBackup`, `specimenDataStorageRules`) together with the time-bounded ones, for 120 minutes (the initializer role for 75, `specimenDataInitializerDisposal` for 115), and refuses any untimed binding | G11 | S2 T4c, PR #123 (narrows the renewals to the time-bounded roles) |

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
    three checks run on the service URL. Its invoker policy must be exactly
    `allUsers`, unconditionally.
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

1. Admission: no credentials. It runs the gate and waits for CI.
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

## 4. T3: data plane on merge

T3 retires the data plane's envelope in steps that each keep `main` green: T3a
the additive-only gate, T3b the data gate and automatic phases, T3c the first
initialization, T3d the apply while the runtime runs, and T3e the bootstrap.
The coordinator settled the three open choices on 2026-09-23 (D1 to D3 below).
Live state, read on 2026-09-23:
- The Data Connect schema is a `STRICT` placeholder with no source files, and
  no connector exists.
- The application database exists.
- Cloud SQL takes daily automated backups (seven retained) with
  point-in-time recovery on.

### 4.1 The additive-only gate (T3a)

`scripts/ci/schema_gate.py` compares the live schema and connector sources with
the merged `dataconnect/schema/*.gql` and `dataconnect/connector/*.gql`,
offline. It parses only the SDL this repository uses. It reads only the
top-level `*.gql` files of those two folders, the files the data release
sends. It fails closed on anything else firebase-tools would read there: a
nested folder, a `*.graphql` file, or an entry that is not a regular file. The
data release applies exactly those files through the Data Connect API. It
never applies them through `firebase deploy` or a `firebase dataconnect:`
command, which read `**/*.{gql,graphql}` and every `connectorDirs` entry. It
accepts:

- new `@table` types, whatever their fields, except a field whose `@default`
  carries SQL (below);
- new nullable fields on existing tables, including a new foreign key that
  covers at least one new field (S2's reading of PLAN 4.4's "foreign keys
  over new columns only"). Scoped foreign keys always include the existing
  `organizationId` and `collectionId`, and PostgreSQL does not enforce a
  foreign key on rows whose new, nullable column is null;
- removing `!` only from a field that section 3.3 of the data contract
  (`docs/execution/golive/DATA_CONTRACT.md`) lists with its reason. The gate
  reads that table strictly from the merged tree, and fails closed on a
  missing or malformed one. It reads the section as GitHub renders it, so
  the table a reviewer sees is the one it reads. Lines end only at LF, CRLF
  or CR. The section holds no HTML comment or block and no fenced or
  indented code. Its only whitespace character is the space. Today it lists
  `SourceAsset.width`, `SourceAsset.height`, `LabelRegion.cropAssetId` and
  `EvidenceItem.locator`. A row in the merged tree authorizes a drop in the
  same merge, so reviewers check every new row against PLAN 4.4 and the
  never-list below. A relation field whose `@ref(fields:)` covers a listed
  column may follow it, since they are the same SQL column. The gate never
  removes `!` from a key field, a `@unique` field, or a provenance or
  idempotency key. These are `ModelObservation`'s `runId`, `regionId`,
  `provider`, `modelVersion` and `stepKey`, and the TRN-005 provenance
  `rawAssetId`, `promptVersion` and `inputSha256` on every table that
  carries them, `EvidenceItem`, `PipelineRun` and `Checkpoint` included
  (PLAN 4.4). The gate refuses the drop even when the list names the field;
- one closed exception for a unique constraint (PLAN section 4.4,
  coordinator ruling on #88). `SourceAsset`'s `specimen_unique_1` on
  (bucket, objectName, generation) gives way to `source_asset_specimen_object`
  on (organizationId, collectionId, specimenId, bucket, objectName,
  generation), because the content-addressed blob store makes identical bytes
  one object across specimens. The swap takes two merges, so that a unique
  constraint governs the table at every moment while writers run. The gate
  admits exactly these two steps from its checked-in entry:
  1. adding exactly `source_asset_specimen_object`, with no argument but its
     `indexName` and its `fields` in the entry's order, while
     `specimen_unique_1` is still declared in both schemas, so the old
     constraint keeps governing. Every column it adds must be an existing
     NOT NULL column, since PostgreSQL treats NULLs as distinct;
  2. in a later merge, removing exactly `specimen_unique_1` from the schema,
     only when the live schema already has `source_asset_specimen_object`
     and no live or merged operation uses the old constraint (a lookup,
     upsert or `onConflict` on its fields). The migration admits no drop,
     whatever Data Connect's diff carries, so the data release drops the old
     constraint itself. It runs S5's one fixed, reviewed statement in
     `dataconnect/sql/` before it computes that diff, and only after its own
     read-back of the live database shows `source_asset_specimen_object` in
     place, over its six columns and valid (4.4). The gate compares
     committed text only, so it admits this step only when its caller says
     that read-back passed. No caller says so until T3d's drop step pins the
     statement's SHA-256 and reads the live database back. Until then, step 2
     is refused.

  Both steps in one merge, and any other change to a unique constraint, are
  refused. Neither constraint may be the table's key or hold a never-list key;
- a new type-level `@unique` or `@index` whose fields are all new;
- new connector operations that:
  - carry `@auth(level: NO_ACCESS)` as their own and only `@auth`;
  - declare `$actorUid: String!` without a default;
  - check `organizationMember(key: {organizationId: $organizationId, uid:
    $actorUid})` with exactly `@check(expr: "this.active")` or
    `@check(expr: "this.active == true")`, where a `message` may follow and
    `optional` may not;
  - use no `@skip`, `@include` or `all:` argument;
  - if a mutation, also carry `@transaction` and make that check before the
    first write.

The gate checks only those marks of an operation. Reviewers check the rest of
every new or changed operation, which the gate cannot (PLAN 4.4, `DATA.md`
73):
- every read and write is filtered to the checked `$organizationId` and
  `$collectionId`, never unfiltered and never another organization's;
- the `collectionMember` `@check`'s role expression fits the operation;
- sensitive fields are read only behind a `canViewSensitive` check;
- deletes and updates are bounded by the same filters.

The first initialization (4.3) has nothing live to compare, so the gate never
checks the connector it applies; those reviews are its only check.

It refuses everything else, and names each refusal without values:
- a removed or renamed table or field;
- a changed `@table` key or name, field type, default or reference;
- an added `!`, or a new non-null field on an existing table;
- a new `@unique` or `@index` over an existing field, or a removed or changed
  type-level constraint, other than the two steps above;
- a new, changed or removed `@view`, and a new field whose `@default` carries
  SQL. PLAN 4.4 admits only new tables and nullable columns, and both of
  these would run their own SQL text in the database;
- a removed or changed operation, compared with whitespace normalized;
- a new operation without the marks above.

When the live schema is the empty placeholder there is nothing to compare, and
the release initializes instead (4.3).

### 4.2 The data gate and its phases (T3b)

- The data jobs use the gate of section 3.1 for the `data` and
  `data-initialization` planes, with their fixed providers.
- The release job chooses the phase itself from live state read without
  changing it: `initialize` when the schema is the empty placeholder and no
  connector exists; `apply` when the merged schema, connector or Storage rules
  differ from the live ones; `verify` otherwise.
- The runtime gate waits for the same commit's data release to succeed (D3).

### 4.3 First initialization (T3c)

The one-time initializer creates the Data Connect roles and grants in one
transaction with postconditions, through the existing time-bounded window. It
skips the clone rehearsal: the database holds nothing to restore, and backups
with point-in-time recovery are on. The ordinary identity then:
1. applies the schema with `MIGRATE_COMPATIBLE`;
2. applies the supplemental indexes, the connector and the Storage rules;
3. checks that the catalog lists exactly the tables the merged schema
   declares.

### 4.4 Apply while the runtime runs (T3d)

1. Before every apply, an on-demand backup must reach `SUCCESSFUL`, and
   point-in-time recovery must be on. On the first apply after the plane goes
   live, that backup is also restored into a short-lived clone; the clone's
   catalog is checked and the clone is deleted (D1).
2. The gate of section 4.1 must pass. For step 2 of the unique swap, the
   release first reads the live database back and gives the gate the result.
   Once the gate passes, it runs S5's statement, checked against its pinned
   SHA-256, before validate-only. T3d's drop step adds this. Until it lands,
   the gate refuses step 2.
3. The schema is applied with `MIGRATE_COMPATIBLE`: validate-only first, then
   conditional on the live etag. The apply sends the merged sources unchanged
   and never builds a schema of its own. A change one migration would order
   unsafely, like the unique swap in 4.1, spans two merges instead.
4. The supplemental indexes are created concurrently, then the connector and
   the Storage rules are applied.
5. The catalog must list exactly the declared tables.

No writer is quiesced and no row hash is compared, because the runtime keeps
running.

### 4.5 Bootstrap (T3e)

The private artifact reaches the job only through the `data-production`
environment secret `DATA_BOOTSTRAP_ARTIFACT_B64`. The owner sets it for the
bootstrap run, with the one-time bootstrap window open, and deletes it
afterwards (D2).
- If the secret is absent, the job skips the bootstrap.
- If it is present and the rows already match exactly, the job verifies and
  skips.
- If it is present and the rows differ, the job fails.

Nothing prints a value from the artifact, and evidence stays encrypted as
today. The envelope phases stay until T3's last step removes them.

## 5. Next pull requests

Each adds its own section here, with failing tests first, as PLAN section 7.2
requires.

- T4, the owner's list: a read-only script that prints the exact standing IAM
  grants and secrets T2 and T3 need, each bound to a named resource with its
  reason. It also prints the time-bounded windows for the one-time roles (the
  initializer role, `specimenDataOwnerBootstrap`,
  `specimenDataInitializerDisposal`) and for the clone, claim and
  runtime-absence roles.
- T5, first releases: the first data and runtime releases; the repository
  variables as an owner action whose private values the owner fills in;
  Hosting rebuilt and connected (DoD-1 to DoD-3).
- T6, deploy health: any failed deploy fixed through a pull request.
