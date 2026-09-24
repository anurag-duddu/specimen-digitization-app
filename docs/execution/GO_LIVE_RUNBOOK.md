# Go-live runbook: the first-ten human-review release

> 2026-09-23: The owner's decisions in [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the
> decision. [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that
> still enforces a superseded clause until a later go-live pull request
> changes it.

This page is for the project owner. It puts the whole release in order, says
who does each step, and names the evidence to keep. It adds nothing to the
contract: [`DEPLOYMENT.md`](../DEPLOYMENT.md) remains the authority on every
gate, [`RELEASING.md`](RELEASING.md) on minting the release envelope, and
[`RELEASE_AUTHORIZATION.md`](RELEASE_AUTHORIZATION.md) on what is approved.
Nothing here deploys from a workstation. The read-only commands that obtain
each owner-supplied value are in
[`../../infra/release/OWNER_INPUTS.md`](../../infra/release/OWNER_INPUTS.md).

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. `DEPLOYMENT.md`'s gates, `RELEASING.md`'s release envelope and
> `RELEASE_AUTHORIZATION.md`'s approval are amended: once the required
> checks pass and the PR steward approves, a merge to `main` deploys runtime
> code and additive schema changes automatically. Branch protection, the
> required checks, keyless identities and main-only environments stay.
> Envelopes, cost ledgers, independent-review reports and authorization
> artifacts retire for this program. G30's per-call reservations stand (PLAN
> 4.3; the coordinator's ruling on the mechanism). The prohibition on
> deploying from a workstation or agent shell is unchanged.

## What "live" means for this release

The approved release is the human-review release of the first ten specimens
([`HUMAN_REVIEW_RELEASE.md`](HUMAN_REVIEW_RELEASE.md)): subjects
`subject_105526321` to `subject_105526330`, one administrator, the web client
only, one bounded worker execution that runs real SAM 3 and both handwriting
readers on every region, and then the administrator compares, corrects, saves
and reopens all ten on the public URL. Cost stays inside the USD 12 cumulative
ceiling ([`APPROVED_RELEASE_BUDGET.md`](APPROVED_RELEASE_BUDGET.md)).

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2 and G9. Specimens are processed one at a time, on demand, including new
> uploads, instead of one bounded worker execution over the whole cohort;
> the ten remain the acceptance cohort, processed in order. The spending
> ceiling is USD 25, cumulative, infrastructure and models together.

It is not full-pipeline acceptance and not institutional acceptance. EMu,
GBIF lookups, native apps, more than ten specimens, BYOK, Temporal, automated
classification and automated clearance are out of scope.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1 and G14. The full pipeline of PLAN section 1 is in scope, including the
> LLM first pass, the agentic harness's lookups (GBIF among them) and the
> queue decision; a record the harness resolves is cleared without a human.
> EMu, native apps, BYOK and Temporal stay out of scope, and so does
> automated classification: under G14 there is no classification stage, and
> the profile comes from the collection a specimen was uploaded or imported
> into. New uploads beyond the ten are processed on demand under G2.

## Where things stood on 2026-09-22

| Plane | State | Evidence |
|---|---|---|
| Hosting | Live at the current `main` commit; magic-link sign-in works; after sign-in the client reports "Collection connection required" | public `/deployment.json`, CI/CD run for that commit |
| Client configuration | All four public repository variables unset | `gh variable list` empty |
| Data | Never run live. Cloud SQL database exists but is unmigrated; the Data Connect connector has never been deployed | `firebase dataconnect:sql:diff` lists every application table as missing |
| Runtime | Never run live. No images, services, jobs or runtime secrets exist | `runtime-production` environment empty |
| Branch protection | Lapsed. `main` reports `protected: false`; the protected planes require `GITHUB_REF_PROTECTED=true` at admission | `gh api repos/anurag-duddu/specimen-digitization-app/branches/main` |

The order below is fixed by the code, not by preference: Hosting green, then
data, then runtime build, then runtime prepare, then client configuration and
the import of the ten, then runtime activation and the one worker execution,
then human review.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2. After the first release, the worker drains due work one specimen at a
> time, on demand, instead of one execution over the whole cohort; SAM 3
> serves any run the worker authorizes.

## Phase 0. Repository and credentials

Owner. Nothing else can start before this.

1. Confirm protection on `main`. The protected planes read GitHub's
   `GITHUB_REF_PROTECTED` flag, and GitHub sets it only when a protection
   rule or ruleset exists for the branch. Done on 2026-09-22: the owner made
   the repository public and the dormant rule reactivated with the settings
   `DEPLOYMENT.md` specifies (pull request required, the three required
   checks strict and up to date, conversations resolved, no force push, no
   deletion, administrators included). Re-verify before every release:

   ```bash
   gh api repos/anurag-duddu/specimen-digitization-app/branches/main --jq .protected
   ```

   The answer must be `true`.

2. Sign in to Google Cloud on the workstation that will run the read-only
   inventory, and point it at the right project:

   ```bash
   gcloud auth login
   ```

   ```bash
   gcloud config set project specimen-digitization
   ```

3. Run the read-only inventory and keep its log with the release evidence. It
   lists and describes only; it creates and changes nothing.

Evidence to keep: the `protected: true` answer, the inventory log.

## Phase 1. The readiness pull request

Coordinator, then owner merges.

The branch `claude/go-live-readiness` carries the defect fixes, the typed plan
templates under `infra/release/`, the owner inputs table and the corrected
documents. It passes `scripts/ci/verify.sh` locally and the required checks
on GitHub. Merge it through the pull request. The merge redeploys Hosting;
verify the public marker with the four-argument smoke from `DEPLOYMENT.md`
before going on. The merged commit is the source the first envelopes bind to.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. There are no first envelopes to bind to: once this pull request's
> required checks pass and the PR steward approves, merging it deploys data
> and runtime releases automatically.

## Phase 2. Cloud bootstrap

Owner, inside the approved action packets. Every item is a precondition the
protected workflows check and refuse to create. The read-only inventory of
2026-09-22 (run by the coordinator after the owner signed in) established
the state column; verify effective access again before acting, and create
only what is missing.

| Precondition | State on 2026-09-22 | Action |
|---|---|---|
| Workload Identity pool `github-actions` with providers `specimen-data-release`, `specimen-data-initialize`, `specimen-runtime-build`, `specimen-runtime-release` (and `specimen-digitization` for Hosting), each conditioned on this repository's numeric ids, `push`, `refs/heads/main`, its environment and its workflow | All five exist and are active with exactly those conditions | None |
| Workload identity user bindings on the five release service accounts | All five bound, each to its provider's release-plane attribute (Hosting to the repository id) | None |
| Service accounts: five release identities plus `specimen-api-runtime`, `specimen-worker-runtime`, `specimen-sam-runtime` | All exist, none disabled | None |
| The eleven data-plane custom roles bound to the DATA identities (`RELEASE_DATA.md`, `CLONE_ALLOWANCE.md`, `DATABASE_INITIALIZATION.md`) | All bound, but nine bindings carry time conditions that expired on 2026-09-13 between 21:40Z and 22:25Z (backup, clone create and control, restore claim, schema publish, Storage rules, runtime absence, initializer temporary and disposal). Only the two inventory roles remain effective | Coordinator records the exact packet with `scripts/ci/data_setup_window.py plan` (one read of the live policy; nothing changes); the owner approves the printed packet and runs `execute` inside the ten minutes. The renewed access lasts 75, 115 and 120 minutes, so this is the last step before Phase 4, taken only when Phase 3 is complete and both data envelopes are installed |
| Custom role `specimenDataOwnerBootstrap` and its two-hour conditional grant to the DATA identity | Not created | The same packet: `execute` creates the role and its two-hour grant before it renews the bindings, six requests in all, and refuses to run if the policy moved since planning |
| Cloud SQL instance `specimen-digitization-instance`, PostgreSQL 18, `us-east4`, `db-f1-micro`, 10 GB SSD | Exists and runnable. Automated backups are on (seven retained), point-in-time recovery is on with seven days of logs | None; the backup decision the docs left open is already made |
| Database `specimen-digitization-database`; IAM SQL users for `specimen-data-release@` and the Data Connect service agent | Both exist; both users registered as IAM service accounts | None (their in-database roles are checked by the initializer) |
| Data Connect service `specimen-digitization-service` with schema and connector | Service exists; schema `main` has no source files (the empty placeholder), strict validation, bound to the instance; no connector | Delivered by the data plane. The schema's update time moved on 2026-09-22 at 15:13Z because the read-only diff performs a validate-only upsert; source stayed empty |
| Artifact Registry repository `specimen-runtime` in `us-east4` with immutable tags | Exists, immutable tags on, empty | None |
| Secret `huggingface-runtime-token` | Exists; version 2 enabled, version 1 disabled; no accessor bindings | Owner: rotate to a fine-grained inference-only token as a new version if not already, pin that numeric version in the plans, and grant the accessor role to `specimen-worker-runtime` only |
| Secret `specimen-worker-logfire` (`APPROVED_LOGFIRE_TRACING.md`) | Does not exist | Owner decided on 2026-09-22 that bounded tracing is in the first plan. Owner mints a dedicated write token for the approved project in the Logfire console, saves it to an owner-only file outside the repository and runs `scripts/ci/worker_trace_setup.py store` (parent in `us-east4`, one version, readback compared byte for byte), then `identity` (the single approved identity request; prints `trace_project_id` and `trace_identity_receipt_sha256`). The accessor grant (`grant`) belongs to the runtime setup, bound to the runtime packet's expiration |
| Resource permissions for the three runtime identities: connector impersonation, bucket prefix get and create, secret access, SAM invocation | None exist; the runtime identities hold no project role, the bucket policy holds only legacy project roles, and the SAM service does not exist yet | Owner bootstrap after the connector exists and before runtime prepare (`RUNTIME_PROPOSAL.md`) |
| Public invocation of the API service (`allUsers` as the only invoker) | The service does not exist yet | Owner grants it as soon as runtime prepare creates the service and before activation; the release verifies it |
| Worker-only invocation of the SAM service | The service does not exist yet | Owner grants it after prepare; the release verifies and never changes it |
| SAM 3 checkpoint under the bucket's `application/sha256/<commit>/sam3-cache` prefix | The `application/sha256/` prefix holds 21 objects; their contents were not read | Owner populates the cache for the merged commit before activation |
| Bucket `specimen-digitization.firebasestorage.app` (`us-east1`) | Uniform bucket-level access on; no public members; soft delete seven days; 1,004 objects under `microscopic-slides/`. Public access prevention is inherited and the effective organization policy is empty, so it is not enforced | Owner: enforce public access prevention on the bucket (nothing public is intended) |
| Live Storage ruleset equal to `storage.rules` | Not visible from the CLI | Owner confirms in the console; the data plane publishes the deny-all rules |
| Cloud Run services and job | None in `us-east4` or `us-central1` | Created by the runtime plane |
| Required APIs (Cloud Run, Artifact Registry, Secret Manager, Cloud SQL Admin, Data Connect, reCAPTCHA Enterprise, Identity Toolkit, Storage for Firebase, IAM, STS) | All enabled. Billing is enabled on the "Firebase Payment" account; the Budget API is not enabled | None; a budget alert is optional |
| Firebase Authentication email-link sign-in and the authorized domain; App Check enforcement and a budget line for reCAPTCHA Enterprise assessments | Not visible from the CLI | Owner confirms in the console. The organization-wide free quota is now 10,000 assessments a month |

> 2026-09-23: The "Secret `specimen-worker-logfire`" row: Superseded for the
> go-live program by [`docs/execution/golive/PLAN.md` section
> 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G3. The scope to mint the writer secret for is no longer metadata-only:
> system prompts and text inputs and outputs at every VLM, LLM and SAM 3
> level, and the harness's tool calls, are recorded in Logfire and linked
> from the specimen record. The amended scope is in
> [APPROVED_LOGFIRE_TRACING.md](APPROVED_LOGFIRE_TRACING.md).

> 2026-09-23: The "eleven data-plane custom roles" row: Superseded for the
> go-live program by [`docs/execution/golive/PLAN.md` section
> 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. The "both data envelopes are installed" precondition no longer
> applies: once the required checks pass and the PR steward approves, a
> merge to `main` applies additive schema changes automatically.

Evidence to keep: the recorded action packet and its receipt, the writer
secret and identity receipts, the inventory log after the changes, and the
exact resource names and secret version numbers, which go into the plans.

Timing: the setup window's renewed access expires 120 minutes after it opens
(the initializer's after 75, disposal's after 115) and the bootstrap grant
with it, so the two data envelopes of Phase 4 must already be installed when
`execute` runs, and the failed protected run is re-run the moment the
receipt is written. The writer secret, its identity receipt, the bucket
setting and the token rotation are persistent and can be done any time
before.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. There are no data envelopes in Phase 4 to install. How the one-time,
> time-bounded initializer window lines up with the automatic data release
> is specified in the release workstream's data-plane pull request
> ([`golive/RELEASE.md`](golive/RELEASE.md)).

## Phase 3. Private artifacts

Owner and coordinator, before any envelope is minted.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. No envelope is minted: once the required checks pass and the PR
> steward approves, a merge to `main` deploys the release automatically.

| Artifact | How it comes to exist |
|---|---|
| Pilot manifest of the ten, frozen | `scripts/data/pilot_manifest.py freeze-metadata` over the reviewed ordered catalog the owner holds outside the repository. The earlier copy was lost with the workstation's temporary folder; regenerate it and record its digest |
| The organization name, the private collection identifiers for the reviewed tree, and the administrator's verified account | The tree's keys, names and parents are reviewed in `infra/reference/fieldmuseum-collection-tree.json`; `scripts/data/prepare_hierarchy_request.py` mints the identifiers once into a private request; the administrator's account already exists and is verified |
| Recipient keys for the catalog and evidence envelopes | Owner generates; the private half never enters CI |
| Authorization artifact for this source commit | Owner's private record of approval, bound to the merged commit |
| Cost review, and the shared ledger upgraded to `release-cost-ledger/v3` with `reserved` rows in all eleven categories for the exact run and attempt | Coordinator, from the surviving v2 ledger; reserving cost is a spending decision the mint refuses to make |
| Independent review report | A reviewer session that is not the coordinator's |

> 2026-09-23: The "Authorization artifact for this source commit," "Cost
> review... ledger," and "Independent review report" rows: Superseded for the
> go-live program by [`docs/execution/golive/PLAN.md` section
> 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G9 and G11. Release envelopes, the release and cohort cost ledgers,
> independent-review reports and authorization artifacts are retired for
> this program; the PR steward's fresh-swarm review of the pull request
> replaces the independent-review report. The spending ceiling is USD 25,
> cumulative, infrastructure and models together. G30's per-call
> reservations stand (PLAN 4.3; the coordinator's ruling on the mechanism):
> each paid model call reserves its worst-case cost before it starts, is
> settled once its outcome is known, and stays reserved while its outcome is
> unknown.
> The "Pilot manifest of the ten, frozen" row is superseded by G2: each run
> is authorized on its own instead of per frozen manifest (PLAN section 4.1
> stage 2), so no manifest is frozen or pinned into a release; the ten stay
> the acceptance cohort, processed in order.
> The "Recipient keys for the catalog and evidence envelopes" row stands:
> those are encryption envelopes for what the public workflow publishes
> (`catalog_recipient`, `evidence_recipient`), not release envelopes.

## Phase 4. Data initialization and apply

The first data release is the `data-initialize-missing/v1` phase, because the
database exists and is empty ([`DATABASE_INITIALIZATION.md`](DATABASE_INITIALIZATION.md)).

1. Take the run id of the `Protected data release` run that failed closed on
   the merged commit.
2. Mint two envelopes against that run with attempt 2, one per environment,
   exactly as `RELEASING.md` describes: `--plane data-initialization` for
   `data-initialization-production` and `--plane data` for `data-production`.
   Install the secret and the four variables in each environment.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. No envelope is minted and no `RELEASE_INPUTS_B64` secret or
   > `RELEASE_*` variables are installed: once the required checks pass and
   > the PR steward approves, a merge to `main` runs this data release
   > automatically.
3. Re-run all jobs of that run before the packet deadline. Never dispatch a
   new run and never re-run failed jobs only.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. There is no packet deadline or separate re-run step: the
   > automatic deploy on merge (see the note on step 2) runs the release
   > once, from the merged commit.
4. Watch it through: recovery proof, initializer window, disposal, compatible
   apply, connector publication, Storage ruleset, clone cleanup.
5. When the bootstrap plan is ready, mint and run the `data-bootstrap/v1`
   phase the same way. By the owner's decision of 2026-09-22 it uses the
   hierarchy mode: one transaction inserts the organization, every
   collection of the reviewed tree in parent-first order (the four
   departments and their sub-collections, with `Insects` beneath `Zoology`
   as the pilot's scope) and the administrator's two memberships, and the
   release verifies every row before it writes its receipt.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. The bootstrap phase deploys the same way as step 2's data
   > release: automatically, on merge, without minting an envelope. The
   > hierarchy-mode content it applies is unchanged.

Evidence to keep: the attested `data-ready` and `native-recovery` artifacts,
the receipts, the clone deletion time, and the encrypted bootstrap evidence.

## Phase 5. Runtime build and prepare

1. Mint the `runtime-build` envelope for `runtime-build-production` against
   the failed `Protected runtime release` run, install it, re-run all jobs.
   The three images are built from the exact merged source, attested and
   pushed with immutable tags.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. No envelope is minted: once the required checks pass and the PR
   > steward approves, a merge to `main` builds and deploys these images
   > automatically. They stay attested and immutable-tagged, built from the
   > merged commit.
2. Mint the `runtime` envelope for `runtime-production` for the prepare
   phase, install it together with `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256`
   (the digest of the version 2 human-review scope), re-run all jobs. The API
   and SAM services and the worker job are created from the attested images.
   A first creation serves the API at its URL immediately.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G1 and G11. `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256`, the deferred-
   > clearance authorization digest, no longer applies: a record the
   > agentic harness resolves is cleared without a human. No envelope is
   > minted or `RELEASE_*` variable installed; the merge itself deploys the
   > prepared services automatically once the required checks pass and the
   > PR steward approves.
3. Verify the API from outside: `/version` and `/health/ready` report
   production and the merged commit; an anonymous request to `/v1/session`
   is refused.

## Phase 6. Client configuration and the import of the ten

1. Set the repository variables. The first two must be set together or the
   main build fails: `SPECIMEN_API_BASE_URL` (the verified API origin) and
   `SPECIMEN_RECAPTCHA_SITE_KEY` (the reCAPTCHA Enterprise key registered for
   the web app). Also set `SPECIMEN_ADMIN_CONTACT` and, for this bounded
   pilot, `SPECIMEN_PILOT_SCOPE`.
2. Merge a pull request to `main` so Hosting rebuilds with them. Verify the
   marker, sign in as the administrator, and confirm the session resolves the
   collection.
3. Import the ten originals through the authenticated client's ordinary
   upload flow, and verify each object's generation and digest against the
   frozen manifest. The pilot does not use the source-browse path.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G2. No manifest is frozen (PLAN section 4.1 stage 2), so there is none to
   > verify against, and the ten are processed one at a time, in order. Source
   > import is in scope (PLAN section 4.1 stage 1), and it refuses an object
   > whose generation or digest changed.

## Phase 7. Activation and the one worker execution

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2 and G11. After the first release there is no single worker execution
> over the whole cohort and no envelope minted for it: the worker drains due
> work one specimen at a time, on demand, and SAM 3 serves any run the
> worker authorizes and scales to zero instead of expiring within an hour.

1. Populate the SAM checkpoint cache if not already done, and confirm the
   secret versions in the activation plan.
2. Mint the activation envelope for `runtime-production`, install it, re-run
   all jobs. Activation re-verifies images, data and API, promotes the API to
   full traffic, reads back all ten imported specimens, and dispatches exactly
   one worker execution keyed to the manifest digest. The worker runs SAM 3
   and both readers for every region inside the approved 3,500 seconds. The
   SAM service expires within one hour on its own.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G2 and G11 (see the note under this phase's heading). No envelope is
   > minted; the worker drains due work one specimen at a time instead of
   > dispatching one execution for all ten, and SAM 3 no longer expires
   > within an hour on its own.

Evidence to keep: the activation receipt, the worker dispatch intent, the
execution outcome, and the per-specimen receipts in Storage.

## Phase 8. Human review and acceptance

1. The administrator reviews all ten on the public URL: compares both
   readings for every region, corrects, saves, reopens, and confirms history,
   denial and stale-save behaviour.
2. Run the human-review checker over the unchanged 45-case ledger plus the
   four manual subcriteria ([`RELEASE_ACCEPTANCE.md`](RELEASE_ACCEPTANCE.md)).
   > 2026-09-23: Items 1 and 2 are superseded in part for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G1 and G2. The ten pilot specimens are processed one at a time, in order
   > (PLAN section 8), and a record the harness resolves is cleared without a
   > human, so the administrator reviews only what the queue sends to human
   > review. The rest of items 1 and 2 stands, including every UI and live case
   > the human-review checker (`scripts/qa/live/human_review.py`) requires: the
   > ten UI cases of [`RELEASE_ACCEPTANCE.md`](RELEASE_ACCEPTANCE.md)
   > (UI-SIGN-IN, UI-INTAKE, UI-PROCESSING, UI-IMAGE-REGIONS,
   > UI-LITERAL-UNCERTAINTY, UI-SAVE-REOPEN, UI-SEARCH-QUEUE,
   > UI-PROVENANCE-HISTORY, UI-DENIAL-RECOVERY and UI-NO-SYNTHETIC-FALLBACK) and
   > the fifteen live cases of [`LIVE_QA.md`](LIVE_QA.md) (AUTH-IDENTITY,
   > AUTH-APPCHECK, AUTH-MEMBERSHIP, AUTH-REVOKE, AUTH-CROSS-SCOPE, DATA-TEN,
   > DATA-GENERATION, DATA-RESTORE, PROVIDER-ACTUAL, COST-BOUNDS, RETRY-UNKNOWN,
   > WORKER-RESTART, API-RESTART, DEPLOY-IDENTITY and BROWSER-E2E), with
   > UI-SIGN-IN's unverified and no-role denial, UI-DENIAL-RECOVERY's
   > unauthenticated, cross-organization or cross-collection, viewer-write and
   > revoked-access denials, in which stale responses cannot restore access, and
   > UI-SAVE-REOPEN's stale concurrent save, and with the ten, in order and
   > beside new uploads, in place of a frozen manifest (G2), G9's USD 25 ceiling
   > in place of the cohort budget, and the release packet and the cohort ledger
   > retired (G11), so DEPLOY-IDENTITY compares the deployed image digests and
   > SQL and rules revisions with the merged commit's own release runs.
3. Reconcile cost: every reservation category closed with an artifact, the
   ledger appended, the cumulative total inside USD 12.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G9 and G11. The release cost ledgers and their reservation artifacts are
   > retired for this program. The spending ceiling is USD 25, cumulative,
   > infrastructure and models together, and G30's per-call reservations stand
   > (PLAN 4.3; the coordinator's ruling on the mechanism).
4. Independent reconciliation of deployed source, results and cleanup.
   > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
   > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. The reconciliation stays, and the separate independent reviewer's
   > report is retired. In S2's reading, the PR steward's post-merge deploy
   > check performs it; PLAN sections 6 and 8 split this work between S1, S2
   > and S7.
5. Append the closeout to `docs/SESSION_LEARNINGS.md` with the commit,
   pull request, run ids, marker and smoke results.

Only after step 5 is the release complete.

## If something fails

- A required check fails: fix on a branch, pull request, wait for the new
  head. Never alter a gate.
- Admission fails: read the named stage. The common causes are a stale
  source commit, a window that expired, a ledger without reserved rows, or a
  reviewer session equal to the coordinator's. Mint a fresh envelope against
  the current run; a packet is never edited.
  > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
  > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G11. There is no envelope, packet, release reservation ledger or
  > independent reviewer session to admit. Admission keeps only the checks
  > that stay, the protected branch and the five checks on the exact merged
  > commit; when one fails, the fix goes through a pull request and the next
  > merge deploys. G30's per-call reservations stand (PLAN 4.3; the
  > coordinator's ruling on the mechanism).
- The restore rehearsal crashes after claiming the held Storage object: the
  allowance is consumed by contract and no workflow can retry. This is a new
  authorization decision for the owner, recorded in `CLONE_ALLOWANCE.md`
  terms, before anything else is attempted.
- The worker's outcome is unknown: it exits without retrying by design.
  Read the execution log and the per-specimen receipts; a second execution
  is a new dispatch decision under the same budget.
  > 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
  > section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G2. There is no single execution over the whole cohort to redispatch:
  > the API starts a worker execution when work is due, and the worker
  > drains it one specimen at a time. Paid model calls stay within G30's USD 5
  > allowance, and G30's per-call reservations stand (PLAN 4.3; the
  > coordinator's ruling on the mechanism): each reserves its worst-case cost
  > before it starts and stays reserved while its outcome is unknown.
- The public site is broken: follow the emergency rollback rule in
  `DEPLOYMENT.md`, which covers Hosting only.
