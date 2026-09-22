# Go-live readiness assessment, 2026-09-22

This page records what was verified about the release state on 2026-09-22,
what blocks the first live release, what the readiness pull request changed,
and what only the owner can do. The ordered procedure is in
[GO_LIVE_RUNBOOK.md](GO_LIVE_RUNBOOK.md). The contract is unchanged:
[`DEPLOYMENT.md`](../DEPLOYMENT.md).

The assessment was assembled from twelve read-only research passes over the
code, the workflows, the release scripts and their tests, the product and
execution documents, the session log, the live public site, the GitHub
repository state, the Firebase CLI's view of the project, and current
platform documentation. Every claim below was checked against a file, a
command result or a cited source; where a fact could not be verified it says
so.

## 1. Verified state

**Hosting.** Live at `da339757150de2ff6b75f8f451a6f26b0526d111` (PR #65).
The public `/deployment.json` reports that commit with run `35373097691`,
attempt 1, and the CI/CD run for it shows all six jobs green including the
Hosting deploy. The site renders the magic-link sign-in for fieldmuseum.org
addresses. A signed-in administrator is shown "Collection connection
required", because the client was built with no API origin.

**Client configuration.** The repository has no variables. The main build
forwards `SPECIMEN_API_BASE_URL`, `SPECIMEN_RECAPTCHA_SITE_KEY`,
`SPECIMEN_ADMIN_CONTACT` and `SPECIMEN_PILOT_SCOPE`; the first two are
validated as a pair and the build fails if only one is set. The web App Check
provider is reCAPTCHA Enterprise; the Enterprise key was registered to the web
app on 2026-09-09 per the release plan.

**Data.** The Data Connect service `specimen-digitization-service` exists in
`us-east4` with a schema last updated on 2026-09-08 and no deployed
connector. `firebase dataconnect:sql:diff` lists the entire application
schema (27 tables) as missing, so the Cloud SQL database exists and is
reachable but has never been migrated. The `data-production` environment
still holds an envelope minted for PR #21's merge commit, so the protected
data workflow fails at admission on every push to `main`, which is correct
fail-closed behaviour.

**Runtime.** Nothing exists: no images in a registry, no Cloud Run services
or job, no runtime secrets. The `runtime-production` and
`runtime-build-production` environments are empty, so the protected runtime
workflow fails at its first input check on every push.

**Repository protection.** At the start of the day `main` reported
`protected: false` and the protection and rulesets APIs answered "upgrade to
GitHub Pro or make this repository public". The 2026-09-09 data run passed
admission, which requires `GITHUB_REF_PROTECTED=true`, so protection existed
then and had lapsed with the plan. The owner made the repository public the
same day; the dormant rule reactivated with exactly the contract's settings
and `main` now reports `protected: true`. Only the owner has push access. No
environment has required reviewers, which is now available and is proposed
as a follow-up.

**Cloud inventory.** `gcloud` on the coordinating workstation started the
day signed out and pointed at a different project. After the owner signed in,
a read-only inventory (list, describe and get-policy calls only) established
the state recorded in the runbook's Phase 2 table. In short: every workload
identity provider, every service account and every workload-identity binding
the planes need already exists with exact conditions; the registry exists
with immutable tags; the Cloud SQL instance has automated backups and
point-in-time recovery on; the IAM SQL users exist; the Hugging Face secret
exists with version 2 live and no accessor yet. What is missing: nine of the
eleven data-plane role bindings expired on 2026-09-13 and need their
timestamps renewed, the bootstrap role approved on 2026-09-14 was never
created, the worker Logfire secret does not exist, the runtime identities
hold no resource permissions, and public access prevention is not enforced
on the bucket. The Data Connect schema's update time moved to 2026-09-22
15:13Z during the inventory agent's schema diff, which performs a
validate-only upsert; its source stayed empty and no table was created.

**Private artifacts.** The frozen pilot manifest, the authorization record,
the cost review and the independent review report were lost with the
workstation's temporary folder on 2026-09-14. The version 2 shared ledger
survives under the owner's rollout state. The version 3 ledger required by
the USD 12 ceiling was never created. The ten pilot subjects are recorded in
[SOURCE_BROWSE_AND_RUN.md](SOURCE_BROWSE_AND_RUN.md) as
`subject_105526321` to `subject_105526330`.

## 2. What blocks the first live release

In the order they must be cleared.

1. Branch protection on `main`, because both protected planes require it
   at admission. Cleared on 2026-09-22: the owner made the repository public
   and the documented rule is active again.
2. The missing cloud preconditions from the runbook's Phase 2 table, now
   known exactly: renewing the nine expired data-plane bindings and creating
   the bootstrap role in the approved ten-minute window, creating the worker
   Logfire secret or leaving tracing out of the first plan, granting the
   runtime identities their resource permissions once the connector exists,
   and enforcing public access prevention on the bucket. The workflows verify
   these and refuse to create them.
3. The private artifacts in Phase 3, including a version 3 ledger with
   reserved rows and a manifest re-frozen from the owner's ordered catalog.
4. Fresh envelopes per environment, bound to the merged readiness commit and
   the failed run they will re-run.

## 3. Defects found and fixed in the readiness pull request

None of these weakens a gate. Each is a correctness or hygiene defect on the
release path, with a test.

| Area | Defect | Fix |
|---|---|---|
| Minting | `mint_release_packet.py` printed four variables; runtime activation also requires `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256`, and the deploy only proved plan and variable agree, never that either was an approved scope | A required scope-file option for the runtime plane whose digest must be one of the two approved scopes, a fifth printed variable, and `RELEASING.md` updated |
| Minting | Default window of 1,800 s is shorter than the approved worker timing needs at activation | Plane-aware default (7,200 s for the runtime plane) and a mint-time refusal below the approved cleanup bound |
| Candidate CI | `check_release_readiness.py` was never executed | Wired into `runtime-ci.yml` as its own contract describes: "Not run" on ordinary pull requests, strict on `main` when a generated candidate packet exists |
| Runtime deploy | The API's public invocation binding was assumed and never verified; the activation smoke cannot pass without it | Read-only verification before the first smoke that `allUsers` is the only, unconditional invoker; documented as an owner bootstrap precondition in `RELEASE_RUNTIME.md` |
| Runtime deploy | The SAM audience literal looked like an assumption | Judged not a defect: Cloud Run's deterministic URL form is a documented contract since 2024 and activation re-checks it against the live service; a comment cites the documentation |
| Worker | Data Connect target hard-coded while the API reads it from the environment | The worker reads the same three variables, all or none; the deploy pins them onto the job from the API plan |
| API boot | Observability configured with no explicit send setting and no token in the deployed environment | The API never sends telemetry in either mode; the worker's bounded path is unchanged |
| Hosting deploy | `npx firebase-tools` ran dependency lifecycle scripts with the deploy credential present | The pinned CLI is installed with `--ignore-scripts` into a private temporary prefix and its own binary is invoked, as the data plane already does |
| Data deploy | Literal table count of 27 beside a derived table set | Derived from the schema (still 27) |
| Hosting headers | No security headers | Content type, referrer, framing, CSP frame-ancestors and a deny-all permissions policy on every route; the route smoke applies the declared headers and fails without them |
| Web bundle | `firebase_storage` and `firebase_data_connect` declared and never imported | Removed with the lockfile; a new test requires every declared dependency to be imported; the release bundle builds without them |
| Public settings | `SPECIMEN_PILOT_SCOPE` unvalidated | Trimmed, at most 80 printable characters, with tests |
| Plans | No typed plan existed anywhere | Eight templates under `infra/release/`, each proven against the deploy scripts' own validators by a drift test, with 81 owner placeholders documented in `OWNER_INPUTS.md` |
| Documents | Stale status pages, a checklist still calling the USD 12 decision pending, the wrong App Check provider name, a superseded human-review digest, a "not wired" finding already resolved, and a contract that assumed protection | Dated corrections in place; this page and the runbook added |

## 4. Design points recorded, not changed

- The restore rehearsal is one-shot by contract: one held Storage claim with
  a create-only precondition and one clone name. A crashed rehearsal needs a
  new owner decision. The runbook says so; the contract is untouched.
- Runtime activation requires a completed data release's attested artifacts,
  and the data plane refuses to run once runtime services exist. The order in
  the runbook follows from this.
- The production session endpoint reports two permanent blockers and no
  production ingest can finalize a record. Both are intended for the
  human-review release, which does not finalize.
- The source-browse import surface is not wired in the production app
  factory. The pilot imports the ten through the ordinary upload flow, as the
  contract specifies, so this is a follow-up for the 1,000-image scope, not a
  go-live blocker.
- The API has no per-principal rate limit and accepts large decodes inside a
  1 GiB container. Acceptable for one administrator behind App Check and a
  domain allowlist; a follow-up before any wider audience.
- The independent review is a session id that differs from the
  coordinator's, not a GitHub review. A follow-up could bind it to an
  approving review from a different login.
- The runtime-build envelope keeps the 1,800-second default window while an
  image build may take up to 3,600 seconds and the publication budget is
  capped by the packet expiry. Widening a default is a deliberate loosening,
  so it is left for the owner to set explicitly at mint time with
  `--window-seconds`; the admission cap of 7,200 seconds still applies.
- The worker's non-timing production path still leaves the telemetry send
  setting unspecified; the bounded path the approval covers is unaffected.
- No `runtime-build` plan version exists in the deploy script: the build
  envelope carries a `runtime-prepare/v1` plan in its API-only form, which
  is what the template provides.
- The live-resources record names two runtime identities while the deploy
  assigns a third to the SAM service; its validator pins the count, so the
  record is corrected together with the validator in a later change.
- The Cloud SQL instance has a public IP address and no private address.
  Access is IAM-authenticated and Data Connect reaches it through Google's
  connector, so this is not a go-live blocker, but restricting it to private
  connectivity is a hardening follow-up for the owner.
- The raw inventory log stays outside the repository: it names the instance
  address, the billing account and the organization id, none of which
  belongs in a public repository.

## 5. External facts that change earlier assumptions

Checked against platform documentation current in 2026.

- Cloud SQL automated backups and point-in-time recovery are not tier-gated
  and work on the existing shared-core instance for a few dollars a month.
  On-demand backup and restore into a new instance also work on that tier.
  The instance remains outside the Cloud SQL service level agreement.
- Cloud Run Jobs allow tasks up to seven days. The 3,500-second bound is an
  approval limit, not a platform limit.
- Firebase Hosting rewrites to Cloud Run support `us-east4`, so a same-origin
  API path is available if wanted later. The current direct-origin design
  with exact origin checks is valid as is.
- reCAPTCHA's free quota is now 10,000 assessments a month across the whole
  Cloud organization. App Check refreshes tokens about hourly per active
  client, so a paid tier is a small but real budget line.
- Hugging Face Inference Providers still support provider-pinned routes. The
  runtime token should be a fine-grained token scoped to inference calls.
  `facebook/sam3` remains gated.
- On a public repository, branch protection, rulesets and required reviewers
  on environments are all available on the free plan.

## 6. Owner decisions recorded on 2026-09-22

- Make the repository public to restore branch protection.
- Release by the book, with defect fixes only; no contract simplification.
- Scope is the first-ten human-review pilot, web only, one administrator.
- The coordinator runs the read-only cloud inventory after the owner signs
  in.

## 7. Still open for the owner

- The administrator's fieldmuseum.org account, and the organization and
  collection names to freeze.
- The independent reviewer session.
- The current location of the SAM 3 checkpoint and the ordered catalog the
  manifest is frozen from.
- Enabling automated backups and point-in-time recovery on the instance.
- Rotating the Hugging Face token, and confirming data-processing approval
  for paid calls on real museum images.
- The ongoing budget after the pilot, and whether Logfire stays in
  metadata-only mode.
