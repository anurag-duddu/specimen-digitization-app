# Go-live runbook: the first-ten human-review release

This page is for the project owner. It puts the whole release in order, says
who does each step, and names the evidence to keep. It adds nothing to the
contract: [`DEPLOYMENT.md`](../DEPLOYMENT.md) remains the authority on every
gate, [`RELEASING.md`](RELEASING.md) on minting the release envelope, and
[`RELEASE_AUTHORIZATION.md`](RELEASE_AUTHORIZATION.md) on what is approved.
Nothing here deploys from a workstation. The read-only commands that obtain
each owner-supplied value are in
[`../../infra/release/OWNER_INPUTS.md`](../../infra/release/OWNER_INPUTS.md).

## What "live" means for this release

The approved release is the human-review release of the first ten specimens
([`HUMAN_REVIEW_RELEASE.md`](HUMAN_REVIEW_RELEASE.md)): subjects
`subject_105526321` to `subject_105526330`, one administrator, the web client
only, one bounded worker execution that runs real SAM 3 and both handwriting
readers on every region, and then the administrator compares, corrects, saves
and reopens all ten on the public URL. Cost stays inside the USD 12 cumulative
ceiling ([`APPROVED_RELEASE_BUDGET.md`](APPROVED_RELEASE_BUDGET.md)).

It is not full-pipeline acceptance and not institutional acceptance. EMu,
GBIF lookups, native apps, more than ten specimens, BYOK, Temporal, automated
classification and automated clearance are out of scope.

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

## Phase 0. Repository and credentials

Owner. Nothing else can start before this.

1. Make the repository public and restore protection on `main`. The
   protected planes read GitHub's `GITHUB_REF_PROTECTED` flag, and GitHub
   sets it only when a protection rule or ruleset exists for the branch.

   ```bash
   gh repo edit anurag-duddu/specimen-digitization-app --visibility public --accept-visibility-change-consequences
   ```

   Then apply the protection `DEPLOYMENT.md` specifies (pull request
   required, the three required checks strict and up to date, conversations
   resolved, no force push, no deletion, administrators included). A ready
   settings file is described in the readiness pull request; verify with:

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

## Phase 2. Cloud bootstrap

Owner, inside the approved action packets. Every item is a precondition the
protected workflows check and refuse to create. Discover first, create only
what is missing, and verify effective access rather than role names.

| Precondition | Defined in | Notes |
|---|---|---|
| Workload Identity providers `specimen-data-release`, `specimen-data-initialize`, `specimen-runtime-build`, `specimen-runtime-release` in one pool, each bound to this repository's numeric ids, `push`, `refs/heads/main` and its environment | `DEPLOYMENT.md` "Approved runtime/data release contract", `scripts/ci/release_admission.py` | Hosting keeps its own pool and provider unchanged |
| Service accounts `specimen-data-release`, `specimen-data-initialize`, `specimen-runtime-build`, `specimen-runtime-release`, `specimen-api-runtime`, `specimen-worker-runtime`, `specimen-sam-runtime` | `RUNTIME_PROPOSAL.md`, `RELEASE_DATA.md` | Least privilege, named resources only |
| Cloud SQL IAM users for the DATA release identity and the Data Connect service agent, with no roles | `DATABASE_INITIALIZATION.md` | The initializer refuses elevated registrations |
| Custom role `specimenDataOwnerBootstrap` and its two-hour conditional grant, applied in the one fresh ten-minute window | `RELEASE_AUTHORIZATION.md` amendment of 2026-09-14 | Prepare every input before the clock starts |
| Create-only permission on the single held Storage claim object | `CLONE_ALLOWANCE.md` | One restore rehearsal, ever; see "If something fails" |
| Artifact Registry repository `specimen-runtime` in `us-east4` with immutable tags | `scripts/ci/deploy_runtime.py` | Asserted, never created by the workflow |
| Secret Manager versions: the Hugging Face inference token (rotate to a fine-grained token scoped to inference calls first) and the worker-only Logfire writer | `HUGGINGFACE_MODEL_ROUTING.md`, `APPROVED_LOGFIRE_TRACING.md` | Pin numeric versions; `latest` is rejected |
| SAM 3 checkpoint pre-populated under the bucket's `sam3-cache` prefix for the exact source commit | `RELEASE_RUNTIME.md` | The SAM service runs offline and forbids a token |
| Public invocation of the API service at the Cloud Run layer (`allUsers` as the only `roles/run.invoker` member) | `RELEASE_RUNTIME.md` | The application enforces auth itself; browser preflights cannot carry IAM |
| Worker-only invocation of the SAM service | `scripts/ci/deploy_runtime.py` | Verified, never changed, by the release |
| Live Storage ruleset equal to `storage.rules`, uniform bucket access and public access prevention on | `DATA.md`, `storage.rules` | The bucket already holds 1,000 real images |
| Automated backups and point-in-time recovery on the existing instance | Owner decision | Not tier-gated; a few dollars a month; the release's own restore rehearsal still runs |
| Firebase Authentication email-link sign-in enabled and `specimen-digitization.web.app` in the authorized domains | `../MAGIC_LINK_SIGN_IN.md` | Console state, not in the repository |
| App Check enforcement for the registered web app, and a budget line for reCAPTCHA Enterprise assessments | `LIVE_API.md` | The organization-wide free quota is now 10,000 assessments a month |

Evidence to keep: the recorded action packet, the inventory log after the
changes, and the exact resource names and secret version numbers, which go
into the plans.

## Phase 3. Private artifacts

Owner and coordinator, before any envelope is minted.

| Artifact | How it comes to exist |
|---|---|
| Pilot manifest of the ten, frozen | `scripts/data/pilot_manifest.py freeze-metadata` over the reviewed ordered catalog the owner holds outside the repository. The earlier copy was lost with the workstation's temporary folder; regenerate it and record its digest |
| Organization and collection identifiers and names, and the administrator's verified account | Owner decision; the administrator signs in once on the live site so the account exists before bootstrap |
| Recipient keys for the catalog and evidence envelopes | Owner generates; the private half never enters CI |
| Authorization artifact for this source commit | Owner's private record of approval, bound to the merged commit |
| Cost review, and the shared ledger upgraded to `release-cost-ledger/v3` with `reserved` rows in all eleven categories for the exact run and attempt | Coordinator, from the surviving v2 ledger; reserving cost is a spending decision the mint refuses to make |
| Independent review report | A reviewer session that is not the coordinator's |

## Phase 4. Data initialization and apply

The first data release is the `data-initialize-missing/v1` phase, because the
database exists and is empty ([`DATABASE_INITIALIZATION.md`](DATABASE_INITIALIZATION.md)).

1. Take the run id of the `Protected data release` run that failed closed on
   the merged commit.
2. Mint two envelopes against that run with attempt 2, one per environment,
   exactly as `RELEASING.md` describes: `--plane data-initialization` for
   `data-initialization-production` and `--plane data` for `data-production`.
   Install the secret and the four variables in each environment.
3. Re-run all jobs of that run before the packet deadline. Never dispatch a
   new run and never re-run failed jobs only.
4. Watch it through: recovery proof, initializer window, disposal, compatible
   apply, connector publication, Storage ruleset, clone cleanup.
5. When the first-scope bootstrap plan is ready, mint and run the
   `data-bootstrap/v1` phase the same way to create the organization, the root
   collection and the administrator's two memberships in one transaction.

Evidence to keep: the attested `data-ready` and `native-recovery` artifacts,
the receipts, the clone deletion time, and the encrypted bootstrap evidence.

## Phase 5. Runtime build and prepare

1. Mint the `runtime-build` envelope for `runtime-build-production` against
   the failed `Protected runtime release` run, install it, re-run all jobs.
   The three images are built from the exact merged source, attested and
   pushed with immutable tags.
2. Mint the `runtime` envelope for `runtime-production` for the prepare
   phase, install it together with `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256`
   (the digest of the version 2 human-review scope), re-run all jobs. The API
   and SAM services and the worker job are created from the attested images.
   A first creation serves the API at its URL immediately.
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

## Phase 7. Activation and the one worker execution

1. Populate the SAM checkpoint cache if not already done, and confirm the
   secret versions in the activation plan.
2. Mint the activation envelope for `runtime-production`, install it, re-run
   all jobs. Activation re-verifies images, data and API, promotes the API to
   full traffic, reads back all ten imported specimens, and dispatches exactly
   one worker execution keyed to the manifest digest. The worker runs SAM 3
   and both readers for every region inside the approved 3,500 seconds. The
   SAM service expires within one hour on its own.

Evidence to keep: the activation receipt, the worker dispatch intent, the
execution outcome, and the per-specimen receipts in Storage.

## Phase 8. Human review and acceptance

1. The administrator reviews all ten on the public URL: compares both
   readings for every region, corrects, saves, reopens, and confirms history,
   denial and stale-save behaviour.
2. Run the human-review checker over the unchanged 45-case ledger plus the
   four manual subcriteria ([`RELEASE_ACCEPTANCE.md`](RELEASE_ACCEPTANCE.md)).
3. Reconcile cost: every reservation category closed with an artifact, the
   ledger appended, the cumulative total inside USD 12.
4. Independent reconciliation of deployed source, results and cleanup.
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
- The restore rehearsal crashes after claiming the held Storage object: the
  allowance is consumed by contract and no workflow can retry. This is a new
  authorization decision for the owner, recorded in `CLONE_ALLOWANCE.md`
  terms, before anything else is attempted.
- The worker's outcome is unknown: it exits without retrying by design.
  Read the execution log and the per-specimen receipts; a second execution
  is a new dispatch decision under the same budget.
- The public site is broken: follow the emergency rollback rule in
  `DEPLOYMENT.md`, which covers Hosting only.
