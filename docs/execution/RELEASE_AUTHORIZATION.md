# Approved release authority — 2026-09-08

The September 14 approved amendment below supersedes only the original budget,
worker-duration and explicitly listed IAM setup limits. The original text remains
the authority for legacy artifacts and all unchanged release boundaries.

The user submitted both approvals in release decision packet v1 in task
`01a082b2-c2c3-70d2-be90-7bfb622c9102`. This records the actual submitted
decisions, superseding earlier statements that these two approvals were pending.
It is authority for the bounded actions below, not evidence that any resource,
credential, cost estimate, backup, deployment or acceptance test is ready.

> 2026-09-23: The owner's decisions in
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the decision.
> [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that still enforces a
> superseded clause until a later go-live pull request changes it.

## Protected backend and data releases

Amend `AGENTS.md` and `docs/DEPLOYMENT.md`. Hosting continues only through
`.github/workflows/ci-cd.yml`. Backend and data production deployments use only
`.github/workflows/runtime-release.yml` and
`.github/workflows/data-release.yml`, respectively, after a PR merges to `main`.
Each uses a separate main-only environment and keyless identity. Require all
five successful checks on the exact merged source, independent review,
immutable build provenance, verified data readiness and public end-to-end
verification. Preserve Hosting isolation and every existing protection.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. Independent review is replaced by the PR steward's review of every pull
> request. The required checks, keyless identities, main-only environments,
> immutable build provenance, verified data readiness, public end-to-end
> verification, Hosting isolation and every existing protection stay, and a
> merge to `main` now deploys runtime code and additive schema changes
> automatically.

Workstation deployments, manual dispatch, weaker branch protection, broader
Hosting permissions, service-account JSON keys and AWS resources remain forbidden.
Predeployment admission and postdeployment acceptance are distinct gates;
an incomplete example packet or a source-only test cannot satisfy live readiness.

## Bounded Google Cloud setup

Use only the existing `specimen-digitization` project; proposed region
`us-east4`. Current cloud resource existence must be discovered, not assumed.

| Component | Approved maximum |
|---|---|
| API | 1 CPU / 1 GiB; minimum 0, maximum 2 instances |
| Worker | One execution; 1 CPU / 1 GiB; 30 minutes; no platform retries |
| CPU SAM | 4 CPUs / 16 GiB; minimum 0, maximum 1 instance; absolute expiry within 1 hour including startup |
| SQL and Storage | Reuse existing services; no new persistent SQL instance or capacity upgrade |
| Restore rehearsal | One isolated clone, at most 2 hours; proposed `specimen-digitization-restore-20260908-r1`; smallest compatible target after checking backup/source requirements and complete cost |

> 2026-09-23: Two cells are superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2. In the "Worker" row, "One execution", "30 minutes" and "no platform
> retries": the API starts an execution whenever work is due, and each
> execution drains due work one
> specimen at a time within the task timeout the release sets. In the "CPU
> SAM" row, the absolute one-hour expiry: SAM 3 serves any run the worker
> authorizes and scales to zero. The CPU, memory and instance limits stand.

Remove only the newly created rehearsal clone by its expiry after preserving
verification evidence. Never delete the source instance or original data. Preserve
originals, object generations and history. Apply only independently reviewed,
compatible schema, connector, index and private Storage-rule changes through the
protected data workflow. Bootstrap only the previously supplied administrator
after verifying identity and collection scope; keep sensitive-data access disabled.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. "Independently reviewed" is superseded: the PR steward's review of each
> pull request replaces it, and the data plane applies additive schema changes
> automatically once the required checks pass and the steward approves. The
> rest of the paragraph stands:
> - only the rehearsal clone may be removed;
> - the source instance and original data are never deleted;
> - originals, generations and history are preserved;
> - compatible schema, connector, index and private Storage-rule changes go
>   only through the protected data workflow;
> - only the supplied administrator is bootstrapped, with sensitive access
>   off.

Create only missing APIs, image registry, secret versions and separate build,
release and runtime identities needed by these services. Permissions must be
scoped to named resources, approved connector operations and the application
object prefix. Only the worker runtime reads the pinned inference secret and
invokes SAM. No broad project Owner/Editor grants and no changes to the Hosting
identity. Verify effective access, rather than treating a role name as proof.

Configure the verified API URL and App Check registration/site key for the
existing live app. Verify authentication and denials before real data processing.
Publish public build settings only after their targets are verified.

## Execution and budget boundary

The coordinator may resolve routine resource names and configuration within
these limits after live inventory and independent review. Record an exact action
packet before execution. The user's prior scope remains exactly ten specimens
and **USD 5 total incremental test spending across all sessions and retries**,
without resets. The USD 4 ordinary-reservation target and USD 1 contingency are
planning allocations within that ceiling, not extra budget.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2, G9 and G11. Specimens are processed one at a time, on demand, instead of
> a single ten-specimen batch; the ten remain the acceptance cohort, processed
> in order. The cumulative spending ceiling is USD 25 across infrastructure
> and models. Independent review and the action packet are retired for releases
> and for the standing grants, and a merge to main deploys automatically once
> the required checks pass and the PR steward approves. The setup window keeps
> its action packet for the time-bounded roles.

Stop if the complete conservative reservation cannot fit the remaining budget
or a change falls outside these limits. Do not omit specimens or regions to make
cost or acceptance pass. Stop paid processing when the test completes or its
limit is reached. An evidence-only intermediate run is not full-pipeline release
acceptance.

Google authentication is a separate owner action. The decision submission does
not establish successful sign-in, a verified UID, a frozen manifest, a cloud
quote, native SAM timing or live production readiness. Those are facts to verify,
not approvals to request again. Retain the private authority artifact and its
digest with the private execution packet; no private identity or object path
belongs in this public record.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. The private authority artifact and execution packet are retired, so
> nothing is retained or matched against them. The rest stands: those findings
> are facts to verify rather than approvals, and no private identity or object
> path belongs in this public record.

## Approved combined amendment — 2026-09-14

The user explicitly approved the combined decision at 2026-09-14T02:03:08.382Z
in integration task `01a07f48-a57c-71b0-9642-c9430886049c` after presentation of
the exact budget, worker and Firebase IAM proposal. Its direct user-record digest
and additive evidence contracts are in [APPROVED_RELEASE_BUDGET.md](APPROVED_RELEASE_BUDGET.md).

- USD 12 cumulative and daily, preserving every previous cost and reservation.
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G9 and G11. The cumulative spending ceiling is USD 25, infrastructure and
  > models together, and cost ledgers and reservations retire for this
  > program.
- One worker execution, 1 CPU/1 GiB, one task, zero platform retries, at most
  3500 seconds from original dispatch. Useful work stops by 3485; cleanup by 3500.
  The original SAM one-hour expiry remains unchanged. See
  [APPROVED_WORKER_TIMING.md](APPROVED_WORKER_TIMING.md).
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G2. The worker drains due work one specimen at a time, on demand, instead
  > of one bounded execution of one task with zero platform retries, and SAM 3
  > scales to zero instead of expiring after an hour.
- One fresh ten-minute bounded Firebase setup window for exactly three effects:
  create persistent role `specimenDataOwnerBootstrap` with only
  `firebaseauth.users.get`, `firebasedataconnect.services.executeGraphql` and
  `firebasedataconnect.services.executeGraphqlRead`; grant it at project scope
  to the existing DATA release identity for at most two hours; renew only 18
  timestamps in nine existing DATA/restore-claim bindings, preserving all other
  permissions, members and resource predicates. Initializer/disposal/ordinary
  access expires after 75/115/120 minutes respectively. The role definition
  persists after the conditional grant expires. Reviewed bootstrap code binds
  the approved owner and service; sensitive access stays disabled.
  > 2026-09-23: The expiry of the ordinary DATA access in this item is
  > superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G11, but only for the roles automatic applies need, all from the release
  > workstream's reviewed list: `specimenDataSchemaPublish`,
  > `specimenDataStorageRules` and `specimenDataSourceBackup` become standing,
  > and `specimenDataInventorySqlConnect` and
  > `specimenDataInventoryProjectRead` stay standing with their conditions
  > unchanged. The rest of this item stands:
  > - the clone roles and `specimenDataRestoreAllowanceClaim` stay
  >   time-bounded and open only for the first apply's single restore check
  >   (the coordinator's ruling D1);
  > - `specimenDataRuntimeAbsence` stays time-bounded, unused by automatic
  >   applies;
  > - `specimenDataOwnerBootstrap`, the initializer role and
  >   `specimenDataInitializerDisposal` stay one-time and time-bounded through
  >   this setup window and are revoked after use.
  >
  > Until T4 adapts `data_setup_window.py`, the window still renews three of
  > the standing roles as well (`specimenDataSchemaPublish`,
  > `specimenDataSourceBackup` and `specimenDataStorageRules`).

This includes finishing, independently reviewing and using the bounded helpers
for those effects with at most 187 metadata/IAM requests. Prepare all source,
review, cost and private inputs before the single setup clock starts. Never
replay a completed effect or consumed fence. Protected merged-main workflows
still perform database/runtime deployments. This amendment does not itself
establish credential access, free service quotas, managed database capability,
trace delivery, actual complete region counts or live product acceptance.

## Owner decision — 2026-09-22: bootstrap the whole collection tree

The project owner decided on 2026-09-22, in the go-live session, that the
first data release must create the museum's complete collection hierarchy
rather than one flat collection, so that later phases never re-parent
records: "lets build it right. They can all be there we shouldn't have to
worry about jumping around everytime we update things." This is a new,
explicit architecture decision by the owner and amends only the shape of
the first-scope bootstrap.

- The four-insert `first-scope-owner-bootstrap/v1` mode remains as approved
  and unchanged; an additive `first-scope-hierarchy-bootstrap/v1` mode
  inserts one organization, the reviewed collection tree in parent-first
  order and the same two memberships in one transaction, verifying every
  row exactly as the four-insert mode does.
- The tree's keys, names and parents are reviewed in the repository at
  `infra/reference/fieldmuseum-collection-tree.json` and recorded in
  [`../product-requirements/COLLECTION_HIERARCHY.md`](../product-requirements/COLLECTION_HIERARCHY.md);
  the collection identifiers are minted privately once and never
  regenerated. The artifact binds the exact digest of the tree file at the
  release's source commit.
- The pilot's scope is the `Insects` collection beneath `Zoology`. The
  administrator's memberships, sensitive access (off), the ten specimens,
  the budget and every other boundary above are unchanged.
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G2 and G9. The ten specimens are now the acceptance cohort, processed one
  > at a time on demand alongside new uploads, and the budget this bullet points
  > back to is replaced by the cumulative USD 25 ceiling, infrastructure and
  > models together. The memberships and sensitive access (off) stand.

Everything else in this record, including the protected data lane, the
evidence recipient, the independent review and the private identity rule,
applies to the new mode without change.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. Independent review is replaced by the PR steward's review of every
> pull request. The protected data lane, the evidence recipient (bootstrap
> evidence stays encrypted in public artifacts) and the private identity rule
> stay.

## Owner decision — 2026-09-22: bounded tracing is in the first plan

The project owner decided on 2026-09-22, in the same session, that the
worker's bounded Logfire tracing runs in the first runtime plan rather than
being left out: "I want logfire to run, with tracing." This selects the
already approved contract of
[`APPROVED_LOGFIRE_TRACING.md`](APPROVED_LOGFIRE_TRACING.md) and changes
nothing in it: metadata only, the existing US project, one worker-only writer
secret with one version, one identity request, the accessor grant bound to
the exact version and the runtime expiration. Content capture (prompts,
label text, images, model responses) stays excluded and would need a new
approval and a privacy review.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G3. Tracing now also covers system prompts and text inputs and outputs at
> every VLM, LLM and SAM 3 level, SAM 3 parameters and the harness's tool
> calls with their arguments and results (a Google geocoding result keeps only
> what G26 allows), one trace per run linked from the specimen record; images
> stay excluded. Secrets and the identities of the app's users never enter
> prompts or tool arguments, and scrubbing is only the backstop. The accessor
> grant keeps its exact-version condition, and only the runtime expiration is
> superseded (G11). For this program, the PR steward's review replaces the
> privacy review under G11. The amended scope is in
> [APPROVED_LOGFIRE_TRACING.md](APPROVED_LOGFIRE_TRACING.md).

The owner also asked for the IAM setup to proceed and offered approval. The
bounded setup window of the 2026-09-14 amendment is unchanged; its exact
action packet is recorded by `scripts/ci/data_setup_window.py plan` and the
owner's approval attaches to that packet, not to a general statement. The
helper performs the three approved effects only, inside the 600-second
clock, and refuses if the live policy differs from the packet.

> 2026-09-23: This paragraph stands for every role that stays time-bounded.
> Under
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11, only the roles automatic applies need become or stay standing, from
> the release workstream's reviewed list. `specimenDataSchemaPublish`,
> `specimenDataStorageRules` and `specimenDataSourceBackup` become standing;
> `specimenDataInventorySqlConnect` and `specimenDataInventoryProjectRead`
> stay standing with their conditions unchanged. These stay inside this
> bounded window with its action packet, and their bindings expire when it
> closes: the clone roles, `specimenDataRestoreAllowanceClaim` and
> `specimenDataRuntimeAbsence`. The one-time roles,
> `specimenDataOwnerBootstrap`, the initializer role and
> `specimenDataInitializerDisposal`, are also revoked after use.
