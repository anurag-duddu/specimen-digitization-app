# Protected first-ten release harness

Status: executable release paths and local tests are implemented. Production
readiness, real native restore, native SAM/reader results, and public human-review
acceptance are **Not confirmed**. This document describes the harness, not an
authorization packet or proof that a release happened. The coordinator retains
the private source, permission, cost, and user-decision evidence.

> 2026-09-23: The owner's decisions in
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the decision.
> [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that still enforces a
> superseded clause until a later go-live pull request changes it.

## Entry points and identities

Only original `push` events on protected `main`, after a merged PR and successful
`ci-cd.yml`, can enter the new workflows. There is no `workflow_dispatch`,
workstation deployment, or deployment through the Hosting identity.

| Workflow job | Environment | Keyless Google identity | Purpose |
| --- | --- | --- | --- |
| Data admission | `data-production` | None | Verify exact source, five checks, review, private input pins, cumulative budget |
| Data release | `data-production` | `specimen-data-release` | Apply the exact named data phase |
| Data cleanup | `data-production` | `specimen-data-release` | Independently dispose only this original run's owned restore clone |
| Runtime admission | `runtime-production` | None | Admit preparation or activation without Google credentials |
| Runtime build, three roles | `runtime-build-production` | `specimen-runtime-build` | Build/smoke committed source, publish immutable role images and keyless provenance |
| Runtime release | `runtime-production` | `specimen-runtime-release` | Verify signed receipts and prepare or activate named resources |

> 2026-09-23: The "Data admission" row is superseded for the go-live program
> by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. Admission now checks only the protected branch and the five required
> checks on the merged commit; the PR steward's review happens before the
> merge, not in admission. The private input pins and the cumulative budget
> it checked belong to the retired envelope.

The two entry scripts are `scripts/ci/deploy_data.py` and
`scripts/ci/deploy_runtime.py`. Their CLI guards deliberately reject workstation,
fork, PR, dispatch, wrong environment, wrong identity, unprotected ref, wrong
repository IDs, and unapproved source contexts. These software checks complement
the independently configured GitHub environment, branch, WIF, and resource IAM
protections; they do not replace those protections.

All full WIF provider strings come from the reviewed packet and observed numeric
project identity. Provider IDs are `specimen-data-release`,
`specimen-runtime-release`, and `specimen-runtime-build`. API/worker/SAM runtime
identities remain separate from all release identities. Build credentials cannot
deploy; the release paths never change IAM or database users/passwords.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. The reviewed packet is retired; the release workstream's runtime and
> data pull requests make these provider IDs fixed workflow configuration, as
> Hosting's already is, instead of values read from an envelope. Runtime
> identities stay separate from every release identity, build credentials
> still cannot deploy, and the release paths still never change IAM or
> database users or passwords.

## Sequence without circular readiness prerequisites

1. Review the candidate source independently; pass all five required PR checks;
   merge to `main`. Wait for successful exact-source main CI, including Hosting.
   A push-triggered backend workflow without its complete reviewed packet fails
   closed before OIDC. This initial failure is not a deployment attempt.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. Independent review and the complete reviewed packet are retired; a
   > merge deploys once the required checks pass and the PR steward
   > approves.
2. Observe actual workflow run IDs and next attempts. Assemble and independently
   review the private, source-bound data packet using real inventory and cost
   evidence. Supply it to the protected environment and rerun the **original
   main-push** workflow. Never substitute manual dispatch or a local command.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. The private, source-bound data packet and its independent review
   > are retired for this program; the protected environment still runs only
   > the original main-push workflow.
3. If the existing database's maintenance grants are unconfirmed, first run
   `data-inventory/v1` after the coordinator registers the approved IAM SQL user.
   This phase verifies the named instance revision and first executes the committed
   read-only catalog through `postgres`. It records whether the application
   database exists and opens that exact database only when present. A missing
   database is explicitly unobserved, never an empty or initialized schema.
   Its signed result contains expected-role and capability booleans, approved
   application table names, and counts. It neither grants
   privileges nor establishes schema readiness. The coordinator reviews the
   observed existing roles before assigning any app-scoped maintenance role.
   `data-apply/v1` then proves runtime writers absent, verifies the existing SQL target,
   performs the one native backup/restore rehearsal, compares rows and catalog,
   applies only compatible schema/connector changes and committed supplemental
   indexes, verifies Storage rules, and disposes the owned clone. Its signed
   receipt proves schema readiness and explicitly sets `data_ready: false`.
   Empty-schema initialization selects only `schemaMigration: MIGRATE_COMPATIBLE`;
   existing-schema validation selects only `schemaValidation: COMPATIBLE`, as the
   [SQL Connect API](https://firebase.google.com/docs/reference/sql-connect/rest/v1/projects.locations.services.schemas)
   makes these mutually exclusive. Both validate-only and apply use the same
   source-bound body. A missing application database and unproven initial schema
   ownership remain a separate gate; this harness does not create that database.
   > 2026-09-23: For additive applies, proving runtime writers absent is
   > superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11, as [`DEPLOYMENT.md`](../DEPLOYMENT.md)'s note on quiescing explains:
   > uniqueness is never absent during an additive apply, so writers keep
   > running.
4. Assemble separate build/runtime packets after those run IDs and receipt hashes
   are known. `runtime-prepare/v1` can prepare only the API with `sam: null` and
   `worker: null`; the three signed immutable images are retained for activation.
   An existing approved source object's real generation can serve as the API's
   readiness read. Preparation never executes the worker.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G11. Build and runtime packets are retired; the signed immutable images
   > and their attestation remain the readiness evidence.
5. Configure the public Hosting client through its normal protected main release,
   verify the exact public marker, and obtain actual Firebase sign-in. After the
   enabled/verified Auth identity exists, `data-bootstrap/v1` verifies the signed
   compatible schema/restore receipt and invokes the reviewed atomic bootstrap.
   This phase does not repeat backup/schema operations or require the API absent.
6. Import and verify the exact ten source specimens through the separately owned
   protected intake/application path. Retain original generations, ready manifest,
   existing scoped membership, immutable launch/profile versions, stage budgets,
   and the offline SAM file-map/cache pins. The data schema receipt alone does not
   assert that any of these steps occurred.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G2. Specimens are imported and processed one at a time, on demand,
   > including new uploads, instead of through a single batch intake of all
   > ten; the ten remain the acceptance cohort, processed in order.
7. `runtime-activate/v1` consumes the signed preparation receipt and exact images,
   current compatible data receipt, real imported-record readback, and bound
   private inputs. It verifies API source/readiness and anonymous denial, then
   observes the actual SAM revision/image/configuration and worker-only service
   invocation binding. It promotes the verified API and starts one bounded
   cohort execution. The existing worker orders quality, native SAM, then readers;
   failed or ambiguous SAM prevents reader continuation. No separate qualification
   worker execution is created by this harness.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G2 and G11. The worker drains due work one specimen at a time instead of
   > starting one bounded cohort execution, and SAM 3 scales to zero instead
   > of expiring after an hour; bound private inputs belong to the retired
   > envelope.
8. Independently verify retained native receipts and the public product for all
   ten: authenticated read, actual SAM and both readers, correction, save and
   reopen. Human review remains distinct from automated classification/clearance.
   A runtime receipt always has `release_accepted: false`; final acceptance belongs
   to the evidence-based acceptance harness and coordinator.
   > 2026-09-23: Superseded for the go-live program by
   > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
   > G1, G2 and G11. Each specimen is checked through the full pipeline as it
   > is processed, in order, by the per-specimen acceptance loop of PLAN
   > section 8, not as one verification pass for all ten; the authorization
   > artifacts are retired.

If a later Hosting-only main merge changes the source SHA, `data-verify/v1` can
publish a current-source compatibility receipt without replaying the rehearsal.
It verifies the previous signed schema/restore evidence, exact unchanged
committed data fingerprints, deployed schema/connector etags and Storage rules.
Runtime build/preparation still binds its images to the current approved source.
Any changed data fingerprint or runtime writer during `data-apply/v1` blocks that
path and requires a separately reviewed migration plan.

## Private input materialization and public receipts

Each environment supplies `RELEASE_AUTHORIZED_SHA`, `RELEASE_PACKET_SHA256`,
`RELEASE_INPUTS_SHA256`, and `RELEASE_INPUTS_B64`. The base64 value decodes to one
JSON object containing `packet`, `plan`, and `evidence`; each nested payload is
the exact original UTF-8 string, not a reserialized approximation. Evidence has
exactly `authorization`, `independent_review`, and `shared_budget_ledger`.
`RELEASE_BUDGET_LEDGER_SHA256` is the coordinator's shared ledger authority;
never replace it with a fresh per-plane ceiling. Human-review activation also
requires `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256`.

Materialization uses fixed filenames in a new runner-private directory, rejects
duplicate JSON keys/nonfinite constants, bounds bytes, and refuses overwrites.
Packet/evidence/plan reads use owned private regular files without following final
symlinks. Validation consumes the same bytes whose digests were checked. Private
source data, manifests, profile/launch contents, API error bodies and credentials
are never uploaded as public GitHub artifacts. Check the complete encoded bundle
against GitHub's per-secret size limit before configuring the environment.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. These `RELEASE_*` secrets and variables and the envelope they
> materialize are retired for this program; the public artifacts below are
> unaffected. Private source data, manifests, profile and launch contents, API
> error bodies and credentials are still never uploaded as public artifacts.

Public artifacts have immutable per-attempt names:

- `data-ready-{source_sha}-{run_attempt}` contains `data-ready.json`.
- `native-recovery-{source_sha}-{run_attempt}` contains sanitized native operation
  and owned-clone receipts; schema readiness pins the final recovery receipt hash.
- `runtime-image-{role}-{source_sha}-{run_attempt}` contains the role image receipt.
- `runtime-receipt-{source_sha}-{run_attempt}` contains the observed preparation or
  activation receipt, including explicitly pending acceptance state.

The data receipt binding is `{source_sha, run_id, run_attempt, sha256}`. Runtime
activation additionally pins its prior preparation receipt's run, attempt, and
SHA. Downloading a GitHub artifact is insufficient: the harness verifies its
digest and GitHub keyless attestation for the exact repository, workflow, main
ref, source/signer SHA, and hosted runner before trusting it. The verified
attestation's subject digest must match the exact in-memory bytes consumed;
verifying a mutable filename alone is insufficient. Current deployed resource
revisions are then read again.

## Cost, replay, and cleanup boundaries

The original frozen source-inventory SHA identifies the shared USD 5 allowance.
The ready application manifest preserves that selection SHA while adding real
post-intake IDs and generations. Every plane, day, build, failed attempt,
reservation, and unknown outcome remains in the same cumulative ledger. The
current run/attempt's category totals must exactly match its reviewed reserved
entries. Historical liabilities cannot be removed by a retry or a new date.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G9 and G11. The spending ceiling is USD 25, cumulative, infrastructure and
> models together, and this cumulative release ledger and its reserved
> entries are retired for this program. G30's per-call reservations stand
> (PLAN section 4.3).

The data and runtime workflows have separate non-cancelling run queues. Their
mutation jobs share `specimen-protected-mutation`; neither waits for the other
plane while holding that lock. Build jobs have separately reserved costs and a
build-only identity. The coordinator must reconcile outstanding reservations
before issuing another packet; admission itself is read-only and does not turn
an uncertain effect into a settled charge.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. Separately reserved build costs and reconciling reservations before
> issuing another packet are retired for this program.

Resource fences supplement that shared authority: expected etags and previous
revisions, immutable registry tags per source/run/attempt, one clone name with a
fixed-key held Storage claim before any recovery liability, a cohort-stable worker execution token, and refusal
to activate a job whose single execution was already used. SAM uses immutable
checkpoint files from a read-only cache, no provider credential, bounded requests
and an absolute deadline. API and SAM set and verify both total service and
revision caps, plus GEN2. These are configuration controls, not a claim that an
autoscaling limit alone is an exact billing hard stop.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2. The worker drains due work one specimen at a time instead of holding a
> cohort-stable single-execution token, and SAM 3 scales to zero instead of
> running to an absolute one-hour deadline. The other fences here stand:
> expected etags and previous revisions, immutable registry tags, the one
> clone name with its held Storage claim, SAM 3's immutable checkpoint files
> from a read-only cache with no provider credential, its bounded requests
> (its only time limit once it scales to zero), and the API and SAM 3 service
> and revision caps.

Both recovery entrypoints use `scripts/ci/release_clone.py`. The original intent
must be attested, published as this run's immutable artifact, downloaded and
verified before one conditional JSON multipart insert. Only the current
invocation's fully verified HTTP 200 response grants an in-memory capability for
one backup, clone create and restore sequence. A copied signed intent, generation,
receipt or local winner flag grants no capability. No claim read, retry, adoption,
delete, overwrite or hold release exists. Native ownership and complete operation
history checks on an existing clone still govern cleanup and initialization.
See [the exact claim contract](CLONE_ALLOWANCE.md) for baseline, IAM and cost gates.

Native cleanup has a separate always-run job and an in-job `finally` path. Its
public ownership permit is captured by the original credential-free admission,
so a later expired packet, failed CI, or changed authorization variable cannot
strand the owned clone. Before deletion it independently verifies the exact
native CREATE operation's principal, target, original run/attempt/source labels,
create time and authority window. It never deletes a preexisting or mismatched
resource. The permit preserves the earliest approved clone deadline even when
the local recovery receipt is missing. Late cleanup deletes immediately and
records the deadline violation;
it does not refuse disposal and leave a billable clone running. Network, IAM or
provider failures can still prevent confirmed deletion and must be reconciled
immediately. The cleanup exception authorizes no other mutation.

The on-demand backup mode has no automatic backup/PITR toggle and no automatic
backup deletion. A bounded retention/disposal decision and complete cost reserve
are required before a packet that creates a backup can be admitted operationally.
No wider cleanup authority is inferred from owned-clone disposal.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G9 and G11. Admission through a reviewed packet is retired for this
> program; a backup still needs a bounded retention/disposal decision and
> its cost tracked against the USD 25 ceiling.

## Remaining live inputs and gates

- Minimum named runtime/build/data identities, WIF conditions, registry and APIs;
  resource-level invocation, object, secret-version and SQL Connect permissions.
- Existing SQL IAM database user, signed metadata inventory, and independently
  reviewed app-scoped ownership/maintenance grants; the harness does not invent
  passwords or grant `cloudsqlsuperuser` to proceed.
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G11. Independent review is replaced by the PR steward's review of the
  > pull request that adds these grants to the owner's reviewed list; the owner
  > still makes every grant.
- Native backup retention/cost, restored full catalog/data proof and cleanup.
- Actual enabled Firebase identity, App Check/client settings, bootstrap artifact,
  source sensitivity decision, authenticated import, and immutable object hashes.
- Reviewed complete cumulative cost ledger, SAM cache staging and file hashes,
  strict per-stage/provider bounds, real native timings and actual reader evidence.
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G9 and G11. The reviewed cumulative cost ledger is retired; the spending
  > ceiling is USD 25, cumulative, infrastructure and models together.
- Successful exact-source protected workflows, matching public Hosting marker,
  application smoke, and independent all-ten human-review acceptance.
  > 2026-09-23: Superseded for the go-live program by
  > [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
  > G2 and G11. Acceptance is checked one specimen at a time as each is
  > processed, not as one independent all-ten human-review pass.

Local tests and a successful build do not satisfy any missing live observation.
