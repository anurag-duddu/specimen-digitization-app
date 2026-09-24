# S2 brief: release planes

Session title: **Release data and runtime planes on merge**. Recommended model
Opus 5.5 at extra-high effort.

## Mission

Make the data and runtime planes deploy automatically on merge (owner decision
G11), get the database migrated and the backend running in production, connect
the web client, and keep every deploy healthy for the rest of the program. No
security gate is weakened: branch protection, the required checks, main-only
environments, keyless identities, pinned action SHAs and "never deploy from a
workstation or an agent shell" all stay.

## Read first

1. `docs/execution/golive/PLAN.md`, all of it.
2. `AGENTS.md`, `docs/DEPLOYMENT.md` (all), `docs/execution/RELEASING.md`,
   `RELEASE_RUNTIME.md`, `RELEASE_DATA.md`, `DATABASE_INITIALIZATION.md`,
   `RUNTIME_PROPOSAL.md`, `infra/release/OWNER_INPUTS.md`.
3. `~/specimen-golive/research/02-release-and-deploy-planes.md` (sections 1, 2
   and 7 especially) and `03-data-model-and-persistence.md` section 5.

## Facts you should not have to rediscover

- Cloud state on 2026-09-23 is in PLAN section 3. Always pass
  `--project specimen-digitization`; the `gcloud` credential is the owner's and
  expires often (ask the coordinator to have the owner run `gcloud auth login`).
- The runbook records the Data Connect placeholder schema as strictly
  validated, while `release_initialize.py` 72-78 and 88-89 require
  `schemaValidation: NONE` and `ephemeral`. Establish the real state with
  read-only REST GETs. Do not run `firebase dataconnect:sql:diff`: it performs a
  validate-only upsert that moves the live schema's update time.
- The database `specimen-digitization-database` exists and is empty, while the
  initialization code expects it absent (`release_initialize.py` 382, 445).
- Unmerged branch `codex/initialize-firebase-placeholder` (one commit,
  `2c0880f7`, "initialize from an empty Firebase onboarding schema") may already
  solve part of this. Read it before writing your own.
- Private artifacts live in `~/specimen-release-private/` (mode 700): the minted
  `hierarchy-request.json` (18 identifiers; never re-mint), the
  `hierarchy-bootstrap.artifact.json`, the filled `data-bootstrap.plan.json` and
  the administrator's auth record. Never commit them, print identities from
  them, or paste them into messages.
- The auto-mode classifier blocks IAM writes, branch protection changes and
  repository visibility changes from agent shells. Prepare the exact commands for
  the owner instead. Branch protection and repository visibility stay as they
  are (`DEPLOYMENT.md` 581-586).

## Pull requests, in order

**T1. Contract amendments (documents only, first, small).** Record the owner
decisions of PLAN section 2.1 with dated entries in every document that section
names as superseded, without rewriting history: add a dated "Superseded for the
go-live program by `docs/execution/golive/PLAN.md` section 2.1 G#" note beside
each clause. In `AGENTS.md`'s deployment paragraph, change only what G11
retires: the envelope and its inputs, the independent-review report and the
authorization artifacts, with the PR steward's review in place of the
independent review. Carry every other safeguard over: a separate main-only
environment and keyless identity per plane; the isolated Hosting identity; all
five required checks successful on the exact merged commit; immutable attested
provenance; verified readiness; failing closed on missing evidence. Add the
additive-only schema gate (PLAN section 4.4). Keep "never deploy from a
workstation or an agent shell" and the list of things never to weaken, word for
word. `APPROVED_LOGFIRE_TRACING.md`
gets G3's content scope (system prompts, text inputs and outputs, SAM 3
parameters, tool calls with arguments and results; no images; identities and
secrets scrubbed), narrowed by G26: the geocoding tool's result is only the
place ID, the outcome and the fingerprint, and no span, log line, exception
text, stored error or tool-call result records the Geocoding request URL, which
carries the key. `APPROVED_RELEASE_BUDGET.md` gets USD 25 (G9).

**T2. Runtime plane, automatic on merge.** `runtime-release.yml` and
`scripts/ci/deploy_runtime.py` (and the admission modules as needed): on a push
to `main`, verify `GITHUB_REF_PROTECTED=true` and that the five required checks
succeeded on the exact merged commit; build the three images (rebuild SAM 3 only
when its inputs changed, otherwise reuse the last attested SAM image digest);
push with immutable tags; attest; deploy `specimen-api`, the `specimen-worker`
job definition without starting an execution (the API starts executions, G2),
and `specimen-sam` as a persistent service that scales to zero and that only the
worker may invoke (the server code changes are the processing-lane workstream's,
S3; agree the shape with it). Wire environment and secrets: the Hugging Face
token, the Logfire write token for the worker, the API and SAM 3, the Google
Maps key for the worker, the first-pass and harness model routes (S4), the Data
Connect target and the bucket. Retire the envelope admission for this plane
(inputs secret and variables, packet, ledger, independent review,
authorization, the exactly-ten cohort). After deploy: `/version` reports the
merged commit, `/health/ready` passes, an anonymous `/v1/session` is refused.
Tests for every validator you change.

**T3. Data plane, automatic on merge.** `data-release.yml` and
`scripts/ci/deploy_data.py` and the initialization modules: a first
initialization that matches the real state (database exists and is empty); then,
on every push to `main` that changes `dataconnect/`, an additive-only check (PLAN
section 4.4's expand-only definition, including its NOT NULL rule, its one
closed unique-constraint exception and its `NO_ACCESS` rule; refuse anything
else) and a `COMPATIBLE`
apply, the
supplemental indexes, the connector and the Storage rules, working while the
runtime runs (the `no_runtime_exists` gate becomes the additive-only gate); before step two of the one unique
exception, the release reads the live database itself and runs S5's fixed drop
statement only if `source_asset_specimen_object` is in place, since the gate
compares committed text only; a
one-time, idempotent hierarchy bootstrap from the private artifacts, followed in
the same window (T3e) by the worker's membership from S5's reviewed document
(#96), applied once by the protected data release, never from an agent shell:
an active organization membership and one collection membership on the pilot
collection only, resolved from the committed key `insects` against the approved
hierarchy artifact, whose approval hash the owner holds and supplies apart from
the artifact, never computed from it (#96's `WORKER_MEMBERSHIP.md`; the
hierarchy bootstrap follows the same rule), role `operator`,
`canViewSensitive: false`, with the UID
from the temporary environment secret `DATA_WORKER_ACTOR_UID`, which the owner
sets for that run and deletes afterwards. First a read-only account lookup that
refuses unless the account exists, is disabled, and has no email, password,
phone or sign-in provider (coordinator ruling, from #96's security review);
then write, read back, skip if identical, fail if different. Never the admin membership document of
`scripts/data/bootstrap_admin.py`, which hard-codes role `admin`. Retire the
envelope admission for this plane, but keep the checks that live inside it:
`GITHUB_REF_PROTECTED=true` and the five required checks successful on the
exact merged commit, as in T2. Take a backup with a verified restore path
before any apply. Keep bootstrap identities and other private values out of
Actions logs and artifacts, which are public in this repository. Tests.

**T4. The owner's IAM and secret list.** A read-only script, in the style of
`scripts/ci/data_setup_window.py plan`, that reads the live policies and prints
the exact grants T2 and T3 need. Standing grants: the data release identity's
roles for automatic applies, each named and justified against that path (the
other "ordinary access" roles of `data_setup_window.py` 55-65 stay
time-bounded); the runtime build and release identities
(Artifact Registry push, Cloud Run deploy, act-as on the runtime identities,
attestations); the runtime identities (connector impersonation; object create
and read on the application prefix and read on `microscopic-slides/`; secret
access per identity and per secret, each with a reason: the worker reads the
Hugging Face, Logfire and Maps secrets, its actor uid and the collection
bindings, SAM 3 the Logfire token, the API the Logfire token, the source
registry and the collection bindings; SAM 3 invoker for the
worker only; `run.invoker` for the API on the worker job
only, since running a job needs no act-as; Firebase user lookup for the API);
`allUsers` invoker on the API. The one-time roles get no standing grant: the
initializer, `specimenDataOwnerBootstrap` and `specimenDataInitializerDisposal`
stay one-time and time-bounded through the existing setup-window path
(`data_setup_window.py`) and are revoked after use; `DEPLOYMENT.md` 889-895
caps the initializer's privilege window after native parity at ten minutes. The
setup-window path requires every binding to stay time-bound
(`data_setup_window.py` 126-138): run the window first or adapt the path, never
fall back to a grant without a time condition, and list the revocation
commands. Also list the
secrets (already stored, version 1 each: the Logfire token, the Maps key,
`specimen-source-registry`, `specimen-collection-bindings` and
`specimen-worker-actor-uid`; the existing Hugging Face version is reused,
since the owner withdrew the rotation),
public access prevention on the bucket, and the Budget API with a USD 25 budget
alert. Bind every grant to a named resource with a one-line reason; never Owner
or Editor. Write the commands into `~/specimen-golive/OWNER_ACTIONS.md` and
message the coordinator. Never run IAM writes yourself.

**T5. First releases.** After T2 to T4 are merged and the owner has run T4's
list: watch the data release (initialization, schema, connector, rules,
bootstrap) and then the runtime deploy, and check them against DoD-2 and DoD-3.
Write the repository variables `SPECIMEN_API_BASE_URL`,
`SPECIMEN_RECAPTCHA_SITE_KEY`, `SPECIMEN_ADMIN_CONTACT` and
`SPECIMEN_PILOT_SCOPE` into `~/specimen-golive/OWNER_ACTIONS.md` as exact
`gh variable set` commands for the owner to run. Leave private values such as
the administrator contact for the owner to fill in, and never put them in a
message. `SPECIMEN_ADMIN_CONTACT` is compiled into the public web client, so the
entry says its value becomes public and recommends a role address rather than a
person's. The next merge rebuilds
Hosting; then check DoD-1 (sign-in resolves the collection).

**T6. Deploy health.** For the rest of the program, fix any failed deploy the
PR steward reports.

## Coordination

- S3 changes the SAM 3 server and worker code; you change how they are built
  and deployed. Agree the service shape before T2.
- S5 owns the schema; your data plane applies it.
- The owner's actions come from your T4 list; the coordinator relays them.
- Your spec deltas go in `docs/execution/golive/RELEASE.md`.
- Where the specification is silent or contradictory, stop and ask the
  coordinator; do not decide (G5).

## Done

DoD-1, DoD-2 and DoD-3 hold with evidence, every merge deploys automatically,
and the contract documents say so.
