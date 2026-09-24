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
  `modelVersion`, `stepKey`), the gate reading a checked-in list of the
  allowed columns; new indexes, unique constraints and foreign keys
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
  results are permitted, except that geocoding keeps only the place ID, the
  pipeline's outcome and a response fingerprint. Images are never captured.
  Secrets and the identities of the app's users never enter prompts or tool
  arguments, and scrubbing is only the backstop. The worker, SAM 3 and the API
  hold standing read access to the writer secret.
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
| `scripts/ci/data_setup_window.py` 55-65, 126-138 | Renews the standing roles and the time-bounded ones alike as 120-minute bindings, and refuses any untimed binding | G11 | S2 T4 (narrows the renewals to the time-bounded roles) |

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
offline. It parses only the SDL this repository uses. It accepts:

- new `@table` types, whatever their fields;
- new nullable fields on existing tables, including a new foreign key that
  covers at least one new field. Scoped foreign keys always include the
  existing `organizationId` and `collectionId`, and PostgreSQL does not
  enforce a foreign key on rows whose new, nullable column is null;
- removing `!` only from a field on the gate's checked-in list, each named
  with its reason from the data contract (`SourceAsset.width`,
  `SourceAsset.height`, `LabelRegion.cropAssetId`). A relation field whose
  `@ref(fields:)` covers a listed column may follow it, since they are the
  same SQL column. The gate never removes `!` from a key field, a `@unique`
  field, or a provenance or idempotency key (`ModelObservation` `runId`,
  `regionId`, `provider`, `modelVersion`, `stepKey`);
- a new type-level `@unique` or `@index` whose fields are all new;
- new connector operations whose header carries `@auth(level: NO_ACCESS)` and
  whose body checks `organizationMember(key: {organizationId: $organizationId,
  uid: $actorUid})` with `@check`.

It refuses everything else, and names each refusal without values:
- a removed or renamed table or field;
- a changed `@table` key or name, field type, default or reference;
- an added `!`, or a new non-null field on an existing table;
- a new `@unique` or `@index` over an existing field, or a removed or changed
  type-level constraint;
- a changed or removed `@view`;
- a removed or changed operation, compared with whitespace normalized;
- a new operation at another auth level or without the membership check.

When the live schema is the empty placeholder there is nothing to compare, and
the release initializes instead (4.3).

### 4.2 The data gate and its phases (T3b)

T3b lands in two pull requests: T3b1 adds the code and T3b2 switches the
workflow.

- The data jobs use the gate of section 3.1 for the `data` and
  `data-initialization` planes, with their fixed providers
  (`specimen-data-release`, `specimen-data-initialize`). A data job does not
  wait for a data release, because it is one; only the runtime planes carry
  the data run in their record (D3).
- `deploy_data.py --deploy` with a gate record reads the live state without
  changing it: the Data Connect schema and connector, the Storage rules
  release, the SQL instance and the application database. It then chooses the
  phase:
  - `initialize`: the schema is the empty placeholder and no connector exists.
    The job writes `phase=initialize`, and the initialization jobs (T3c)
    continue.
  - `verify`: the live schema, connector and Storage rules equal the merged
    files. The job checks the persistent, reconciled schema and the connector,
    and succeeds. The SQL catalog and the supplemental indexes need SQL access,
    which arrives with T3d. From then on verify also checks them, and a
    missing supplemental index makes the phase `apply`.
  - `apply`: anything else, if the gate of section 4.1 finds no refusal. The
    apply itself arrives with T3d; until then this phase fails closed. Any
    refusal fails and is named without values.
  - Any other combination (a schema without a connector, or the reverse)
    fails, asking to reconcile.
- Once a data gate record is admitted, every exit writes a `data-released/v1`
  receipt holding the phase and public resource facts only (names, etags,
  the schema's update time). The workflow uploads it on every exit and
  attests it on success.
- The reads need `firebasedataconnect.schemas.get` and `connectors.get`,
  `firebaserules.releases.get` and `rulesets.get`, and
  `cloudsql.instances.get` and `databases.get` for `specimen-data-release`.
  T4's list of the owner's standing grants names the role that grants each.
- The workflow's admission job has no credentials. It runs the gate and waits
  for CI. The release job re-admits, authenticates with the fixed provider and
  deploys. It reads no `RELEASE_INPUTS_B64` secret and no `RELEASE_*`
  variable. The envelope-era jobs and phases leave the workflow. Their code
  stays until a later clean-up removes it with its tests. Until T3c lands, the
  `initialize` route fails closed, so the runtime's wait (D3) never passes
  over an uninitialized database.
- The runtime gate waits for the same commit's data release to succeed (D3).
- The data admission waits up to 3,300 seconds for CI/CD, the gate's limit
  on this branch. When T2c raises the limit to 5,400 seconds, the data wait
  rises with it, since the CI/CD run can take about an hour.

### 4.3 First initialization (T3c)

The application database already exists. Data Connect's service agent
created it on 2026-09-22 (a Cloud SQL `CREATE_DATABASE` operation). So the
first release initializes an existing, empty database. It never creates or
drops a database, and it skips the clone rehearsal: the database holds
nothing to restore, and backups with point-in-time recovery are on.

1. **Read first.** As `specimen-data-release`, the release reads the
   database's catalog. It stops unless no schema other than the system
   schemas holds a user relation, view, routine, type or extension. It also
   reads whether Data Connect's three roles for `public` exist
   (`firebaseowner`, `firebasewriter` and `firebasereader` for
   `specimen-digitization-database`), and prints a summary without values.
2. **Roles.** If the three roles are absent, the one-time initializer
   (`specimen-data-initialize`, with `specimenDataInitializeTemporary` open in
   the owner's setup window) runs `initialize_database.sql` and its
   postconditions in one transaction on the existing database. It is then
   disposed of as before. The roles follow Data Connect's standard setup:
   `firebaseowner` owns `public` and is granted to `specimen-data-release`,
   and `firebasewriter` goes to Data Connect's service agent.
   - **Extension.** Right after its guard, in the same transaction, the
     initializer creates the one extension the schema needs:
     `CREATE EXTENSION "uuid-ossp" SCHEMA public`. The reason is that
     `@default(expr: "uuidV4()")` compiles to `uuid_generate_v4()`. The
     postconditions pin the extensions to exactly `plpgsql` and that one.
   - **Existing roles.** The release never adopts roles it did not create.
     A re-run of the same workflow run may continue past this step only with
     the attested receipt of that run's own initializer, after re-checking
     the postconditions exactly. Otherwise, if any of the three roles or
     `uuid-ossp` already exists, the release stops and prints the catalog
     summary for the coordinator; adopting them needs its own ruling.
   - **Timing.** The owner opens the window before this run and closes it
     after.
3. **Migration, client-side,** as `firebase-tools` 15.8 does for an existing
   instance:
   - A validate-only schema update with `schemaValidation: COMPATIBLE`
     returns Data Connect's SQL diff.
   - Every statement must be non-destructive and of an allowed kind: create
     table or view, add column, create index or unique constraint, add
     foreign key, or drop NOT NULL on a column the gate of section 4.1
     permits (never a key, unique or provenance column). `CREATE EXTENSION`
     and every drop are refused.
   - Python reads each statement, and then Node reads it again the same way
     before it connects. The log names a refused statement by its kind and a
     fixed reason, never its text.
   - The release identity runs them after `SET ROLE` to the owner role, in
     one transaction that sets `lock_timeout` and `statement_timeout` as the
     initializer does. A timeout rolls the transaction back and fails the
     run, which can be re-run. The tables are then owned by `firebaseowner`,
     and the service agent keeps writer only.
   - The schema is then applied with `schemaValidation: COMPATIBLE`,
     conditional on the live etag.

   Server-side `schemaMigration: MIGRATE_COMPATIBLE` is not used.
   `firebase-tools` sends it only while an instance is still being created,
   and it would run the DDL as the service agent.
4. **Then:** the supplemental indexes (`CREATE INDEX CONCURRENTLY IF NOT
   EXISTS`, as the owner role), the connector and the Storage rules.
5. **Catalog check.** The catalog must list exactly the tables the merged
   schema declares and the views it persists, and one extension besides the
   built-in `plpgsql`: `uuid-ossp`. The tables and views must be owned by
   `firebaseowner`, with the writer and reader privileges the postconditions
   define. A `@view` with `sql` persists nothing, because Data Connect plans
   its SQL inline in each query, so today's schema persists no view. That is
   the coordinator's ruling of 2026-09-24 on S2's reading of the migration
   engine: the emulator that `firebase-tools` 15.8 pins generates no
   `CREATE VIEW`. The first catalog read confirms it. Any view the schema does
   not persist fails the check, and the receipt records the view count.

**Jobs.** T3c lands in stacked pull requests. T3c1 adds steps 1 and 2 (#147),
and T3c1b their jobs (#148). T3c2 adds steps 3 to 5 in two pull requests, the
SQL half and then the migrate step. T3c2b replaces the fail-closed `migrate`
placeholder with the job. Each job re-admits through the gate before it
authenticates.

| Job | Environment and identity | Does |
|---|---|---|
| `release` | `data-production`, `specimen-data-release` | On `initialize`, runs step 1 and outputs `init_step`: `initialize` (a new, empty database), `migrate` (this run's own attested initializer receipt exists) or a stop. |
| `initialize` | `data-initialization-production`, `specimen-data-initialize` (gate plane `data-initialization`) | Only when `init_step` is `initialize`. Creates its own Cloud SQL IAM user with `cloudsqlsuperuser`, runs `initialize_database.sql` and the postconditions in one transaction on the existing database, then uploads and attests the initializer receipt, which names this run. |
| `dispose-initializer` | `data-production`, `specimen-data-release` | Always after `initialize`. Revokes and deletes the initializer's SQL user after proving this run created it, as before. |
| `migrate` | `data-production`, `specimen-data-release` | After a successful `dispose-initializer`, or when `init_step` is `migrate`. Verifies the attested receipt, re-checks the postconditions exactly, read-only, and requires the initializer's SQL principal gone. Then it runs steps 3 to 5 under the shared mutation lock. It uploads a `data-initialized/v1` receipt on every exit and attests it on success. |

A run that fails after `initialize` is re-run with "Re-run failed jobs".
`migrate` then consumes the earlier attempt's receipt. The owner's window
must still be open for any job that needs a time-bounded role.

### 4.4 Apply while the runtime runs (T3d)

The coordinator's rulings of 2026-09-24 settle the backup's retention, the
first apply's claim and the rollback guard's record.

1. Before every apply, an on-demand backup must reach `SUCCESSFUL`, and
   point-in-time recovery must be on. On the first apply after the plane goes
   live, that backup is also restored into a short-lived clone; the clone's
   catalog is checked and the clone is deleted (D1).
   - **Retention.** The backup expires 7 days after it is sent; Cloud SQL's
     readback may differ from the request by at most a minute. Its size is
     read back once it exists, and must not exceed the source disk. Its cost
     falls under G9's USD 25 and the billing alert; no release reserves it.
     The daily automated backups and point-in-time recovery stay as they are.
   - **The first apply** is the one whose live schema carries no
     `source-sha` label (item 2). Its clone is
     `specimen-digitization-restore-20260908-r1`. The clone's catalog is
     checked as item 5 checks the source's, but against the live schema: the
     backup comes before the migration, so it holds the tables this apply
     starts from.
   - **The claim.** Before it creates the clone, the apply claims the
     single-use restore allowance of `CLONE_ALLOWANCE.md` itself. It writes
     `application/release-control/first-production-restore.json`
     create-only (`ifGenerationMatch=0`). The claim binds the gate record's
     commit, the run id and attempt, the backup id, the clone name, the
     source instance, and a window of at most two hours inside the gate
     record's deadline. `baseline_sha256` and `iam_sha256` retire with the
     coordinator's issuance (G11).
   - **Single use** rests on three things:
     - the fixed key;
     - the data identity having no permission to delete or update the claim;
     - the time-bounded `specimenDataRestoreAllowanceClaim` role, which the
       owner opens for that run.

     If a claim already exists, the apply stops and the coordinator decides,
     because deleting a claim never refunds the allowance. There is one
     exception, below.
   - **A re-run after a spent claim** (the coordinator's ruling of
     2026-09-24). The claim is unreadable to the data identity, so the
     evidence is an earlier attempt of this run, for this commit, whose
     attested receipt records `first_restore: "checked"`. That attempt made
     D1's one restore proof. The apply then continues without a second claim
     or clone, and records `first_restore: "proven"`.
     - An earlier attempt that recorded only `claimed` stops the apply before
       any effect.
     - Anything else stops for the coordinator: a different commit, a missing
       or unattested receipt, or any other value.

     The release job therefore attests its receipt on every exit, not only
     on success.
2. The gate of section 4.1 must pass, and the merged commit must be the one
   the plane last applied or a descendant of it, checked like the runtime's
   rollback guard against a commit the apply records. A manual re-run of an
   older run could otherwise roll the Storage rules back; the gate already
   refuses a stale schema's apparent removals.
   - **The record** is a `source-sha` label on the Data Connect schema,
     holding the merged commit. The apply sets it in the same PATCH that
     applies the schema.
   - **The check.** Before any effect, the apply reads the label. GitHub's
     compare API must report the merged commit `identical` to it or `ahead`
     of it, as the runtime's guard does (#100).
   - A schema without the label is the first apply after T3c.
3. The schema is migrated client-side, exactly as in 4.3 step 3, and applied
   with `schemaValidation: COMPATIBLE`, conditional on the live etag. Before a
   change that drops `specimen_unique_1` (step two of the exception in 4.1),
   the release reads the live catalog. It proceeds only if
   `source_asset_specimen_object` is in place, so a failed or superseded
   step one can never turn step two into a one-step swap. A COMPATIBLE diff
   lists no drops, so step two's drop is one fixed, reviewed statement for
   exactly `specimen_unique_1`, kept with the supplemental index files, and
   run only after that read-back. The diff's allowlist stays free of drops.
4. The supplemental indexes are created concurrently, then the connector and
   the Storage rules are applied.
5. The catalog must list exactly the declared tables.

No writer is quiesced and no row hash is compared, because the runtime keeps
running.

**Verify.** With SQL access, the `verify` phase of section 4.2 also reads, as
`specimen-data-release` and read-only:
- the catalog, as item 5 does: the postconditions, exactly the declared
  tables, one owner, and `plpgsql` and `uuid-ossp`;
- the supplemental index inventory.

A missing or changed supplemental index makes the phase `apply`.

**Pull requests.** T3d lands in stacked pull requests:
1. the apply without a clone or a drop: items 1 to 5, the rollback guard, and
   verify's SQL checks;
2. the first apply's clone and claim (D1);
3. step two's drop, which waits for S5's #146 and the PR steward's word.

Until the second pull request lands, a first apply stops before any effect.

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
  `specimenDataInitializerDisposal`) and for the clone and claim roles.
- T5, first releases: the first data and runtime releases; the repository
  variables as an owner action whose private values the owner fills in;
  Hosting rebuilt and connected (DoD-1 to DoD-3).
- T6, deploy health: any failed deploy fixed through a pull request.
