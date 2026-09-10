# Production release: data readiness

Date: 2026-09-08. Owner task: `01a082b4-a9bc-7413-a3c5-505b61c2f4db`.
Coordinator: `01a082b2-c2c3-70d2-be90-7bfb622c9102`.
Branch: `codex/release-data-verification`; worktree:
`/Users/anuragduddu/.codex/worktrees/4a25/specimen-digitization-app`.
Baseline: `61d82aed64816802cd6ac00ac11e307a30c2bd8e`.
Actual coding model: `gpt-6-astra`, reasoning `xhigh`, as independently confirmed
by the coordinator from this task's turn context.

**Local data candidate verified; live data readiness Not confirmed.** No cloud
change, private image read, paid model call, push, merge or deployment was
performed by this owner. Read `AGENTS.md` and all of `docs/DEPLOYMENT.md` before
work. The coordinator owns the separate runtime/data delivery amendment.

## Reconciliation and private evidence

GitHub freshly confirms [PR #8](https://github.com/anurag-duddu/specimen-digitization-app/pull/8)
merged at `61ea1e5f2ee0e7988bcd84b7e02e1dff49f16f2f`. Its owner commit
`3d60a1b87027c7321d409be8617a73401cc82b3b` is an ancestor of this baseline;
GitHub main matched the baseline. The preserved `0cf0` worktree is clean.
`LIVE_DATA.md` and the old private receipt describe their historical checkpoint;
their open/unmerged instructions and missing-budget status are superseded by
current Git evidence and the coordinator's USD 5 decision.

The approved administrator email and instruction to select the deterministic
first ten are recorded privately in
`/Users/anuragduddu/.codex/rollout-state/specimen-live/decisions.json` (0600).
Observed file SHA256:
`e9e49cac4ad9789ae6c7454b2a15b9ba870f37f4722563415e7ded0cf2d8fc5a`.
This hash identifies the inspected version; the coordinator may append decisions.
The file contains no verified Firebase UID, explicit collection UUIDs, ordered
source catalog or selected specimen manifest. Its budget now fixes USD 5 total
incremental test spend, shared across sessions, retries and days, with no reset.
The same USD 5 daily maximum applies; existing SQL baseline spend is separate.

Later in this session the coordinator reported the user's submitted approval of
both the protected runtime/data workflow amendment and bounded Google setup.
That approval includes removal only of newly created restore target
`specimen-digitization-restore-20260908-r1` by its two-hour expiry after retaining
proof, and keeps initial administrator sensitive access disabled. These decisions
are no longer pending. Coordinator implementation of the release contract and
the verified resource/cost/identity packet still precede any cloud change.
The actual 0600 approval artifact was independently read and its external
decision-file pin matched:
`/Users/anuragduddu/.codex/rollout-state/specimen-live/release-authorization-v1.json`,
SHA256 `88d757ce9a5fd3474d092c803390c4e799bd2689a561d6ffe15403914486bd63`.
The updated decisions-file SHA256 is
`c8d2832623fd4fc9196917378399030cbcf3d20cb1bf34c51f5cbdfdf1ebe37a`.

The preserved data handoff is
`/Users/anuragduddu/.codex/private/live-rollout/data-20260908/final-3d60a1b-handoff.json`
(0600), SHA256
`07342884dfc3dbc5ff800f8e5313cab6d8334f8ce14cfc71c51031476d1027bd`.
Its ready-manifest hash is null and it records no cloud mutation. All seven
listed data source fingerprints matched the baseline before this task's edits.
Its local restore-proof hash still matches the retained file:
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.QyrfUm/backup-restore-proof.json`,
SHA256 `eb5cd641144342014d7ff529cf8eac6165cca68369e1e1d7e722aad2e927d6e7`.

A targeted inventory of the preserved data and rollout-state JSON artifacts
found historical handoffs and synthetic QA evidence, but no actual metadata
freeze, ready-ten manifest, verified admin export, prepared admin transaction,
cloud import receipt or cloud restore proof. This is a statement about those
inspected locations, not a claim that every private directory was searched.
Keep all preserved worktrees and ignored evidence until coordinator reconciliation.

## Current cloud facts

The coordinator's fresh existing-account probe requires interactive Google
reauthentication; the owner is completing that flow in its terminal. This task's
single attempted project metadata probe failed on sandbox-local gcloud access,
so it does not independently establish an authentication or cloud-resource fact.
Its private error is `/tmp/specimen-release-data-auth-20260908.json` (0600),
SHA256 `499fb9091e647b3b3acc7b07931f6a1fec06c6104618628807ad5b31f6444490`.
No competing login, account switch or repeated unchanged cloud probe followed.

**Not confirmed:** actual object/specimen count, first-ten order/grouping, all
source generations and bytes; bucket region, retention/versioning/soft-delete,
uniform access and public-access prevention; SQL engine/edition/tier/disk,
backups/PITR/latest successful recovery point; published connector/schema;
runtime identities, inherited/conditional effective IAM and denial behavior;
live admin UID, verified/enabled state and collection membership.
Failed access is not evidence of an empty bucket or absent resources.

After the coordinator confirms authentication, run the read-only
`scripts/data/inventory_cloud.py` into a new private directory outside Git.
It captures project/bucket IAM, recursive live/noncurrent object metadata,
instance/backups/databases, service-account and secret metadata, and paginated
SQL Connect service/schema/connector metadata. It disables authentication/API
enablement prompts and stops at the first failed query. It reads no image or
secret-version bytes. Effective IAM still requires target-identity checks;
inventory under an administrator cannot prove runtime access or denial.

## Repairs and TDD evidence

The initial 73 focused data tests passed. Fifteen added regressions then failed
for the intended reasons, with 41 existing tests still passing:
`/tmp/specimen-release-data-red-20260908.log`.

- `inventory_cloud.py` used a bare bucket URL. The installed Google CLI converts
  it to `bucket/*`, omitting nested originals. The fix uses `bucket/**`; the
  regression retains two generations of a nested original and checks sanitized
  output. The CLI already includes live and noncurrent generations by default;
  no unsupported all-versions flag was added. Soft-deleted-only enumeration is
  a separate case and must not silently substitute a source.
  [Google CLI reference](https://docs.cloud.google.com/sdk/gcloud/reference/storage/objects/list).
- `bootstrap_admin.py` read input files with unrestricted `read_text`. It now
  uses the existing bounded private-file loader for both request and Auth export:
  owned regular 0600 files outside Git, no final-component symlink, nonblocking
  file open and 1 MiB bound. Regressions reject public/symlink/in-Git inputs;
  a positive private-file CLI case confirms preparation still works.
- `validate_live_plan.py` accepted a different SQL instance/database, additional
  persistent/restore instances and budget expansion/reset. It now pins the
  intended SQL resources, zero new persistent instances, one proposed isolated
  restore and the shared USD 5 total/daily ceiling. `data-resources.json` records
  supplied budget, two-hour restore authority and proposed allocations without
  claiming a quote, verified inventory or executed cloud change.

Independent coordinator review found eight additional proposal bypasses: inflated
approved/proposed restore hours, backup allocation/ordinary reserve, negative
contingency, another restore target, another Storage rules file, and removal of
the separate maintenance identity. The added suite first failed all eight with
20 existing passes. The validator now pins these reviewed limits/resources;
all 97 focused data tests pass. Logs:
`/tmp/specimen-release-data-review-red-20260908.log` and
`/tmp/specimen-release-data-review-green-20260908.log`.

The green focused suite and broader gates are recorded in the final validation
section. No production schema, connector operation, Storage rule, runtime API,
provider route, Hosting workflow or global tool identity was changed.

## Exact resource and authority packet

The bounded footprint has user approval; each exact mutation remains gated on
fresh inventory, verified cost/identity and coordinator execution coordination.
No resource is presumed missing or in need of recreation.

| Target in project `specimen-digitization` | Proposed action and boundary |
|---|---|
| SQL Connect `us-east4/specimen-digitization-service`, connector `specimen-server` | Compare exact published schema/connector hashes with candidate; apply only reviewed COMPATIBLE changes through separately approved data delivery. Never use the Hosting identity. |
| Cloud SQL `specimen-digitization-instance`, database `specimen-digitization-database` | Reuse current capacity. Capture fresh successful backup/recovery evidence; no upgrade, replacement, destructive restore or additional persistent instance. |
| Temporary `specimen-digitization-restore-20260908-r1`, `us-east4` | At most one new isolated restore target, only after uniqueness, compatible sizing and price are confirmed. User approved removal of this new target after proof retention by the maximum two hours from creation request; no extension/recreation/retry budget reset. |
| Bucket `specimen-digitization.firebasestorage.app` | Preserve all approved original generations. Compare actual bucket/rules/IAM controls before any approved correction; exact needed changes depend on inventory. |
| `application/sha256/` inside that bucket | Immutable application objects; create only with generation-match zero, read only explicit generation, reconcile duplicate creates by exact digest/size. No overwrite/delete/list privilege for runtime. |
| `application/release-control/first-production-restore.json` | One fixed-key held claim before any backup/clone liability, using only the reviewed ordinary data identity's exact-object create permission. No read/adoption/retry/reset or runtime access. Full original issuance baseline, native IAM/hold qualification and continuing storage cost admission are required by [the claim contract](CLONE_ALLOWANCE.md). |
| `specimen-api-runtime` and `specimen-worker-runtime` service accounts | Only the two connector query/mutation impersonation permissions at the narrowest supported connector scope; bucket-conditioned object get/create on the application prefix. Verify actual grants and denied operations. API receives no provider secret; worker receives only separately approved named secret versions. |
| Separate reviewed data-maintenance identity | Time-limited, exact-resource backup/restore/schema/index/bootstrap permissions. Split Auth lookup from bootstrap and release if needed; no Owner/Editor, service-account key or Hosting-identity expansion. Final permission grants require current resource/IAM evidence. |

Direct client Storage rules remain deny-all. IAM-authenticated privileged access
bypasses Firebase rules; rule-emulator success cannot prove privileged IAM safety.
Object get/create permissions do not authorize changing bucket configuration.
[Storage permission reference](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions).
Collection scope remains enforced by verified API identity and SQL membership;
the shared content-addressed object prefix is not per-collection IAM isolation.

## Freeze, bootstrap and import sequence

1. Capture one private complete metadata inventory. Establish specimen grouping
   and deterministic preexisting order from authoritative metadata, preserving
   all associated objects/generations. If grouping, order or a primary source is
   ambiguous, leave the cohort unfrozen and resolve that fact; do not choose by
   image appearance, drop failed records or advance to specimen eleven.
2. Produce the private ordered catalog with authority/grouping/order references.
   `pilot_manifest.py freeze-metadata` freezes exactly records 1–10 and their
   generations under `specimen-pilot-source/v1`. Externally pin its bytes and the
   input inventory hash. Report only count, associated-object count, aggregate
   source bytes and hashes. Unknown SHA256 stays null, never an MD5/CRC substitute.
3. Before any image read, coordinator reviews that frozen authority, exact byte
   bound, source transport/region price, and approved whole-test reservation.
   A changed/missing generation blocks its original specimen; no fallback to latest.
4. After authorized data delivery and successful recovery rehearsal, lookup only
   the approved email in Firebase Auth for this project. Privately export UID,
   email, emailVerified and disabled; require exact verified/enabled identity and
   explicit existing organization/collection UUIDs. Prepare a hashed first-admin
   transaction with `bootstrap_admin.py`, default sensitive permission false.
   Immediately before approved apply, relookup and compare Auth. The transaction
   locks the organization, denies any previous admin or target membership, and
   inserts both memberships atomically. No upsert, upgrade or reactivation.
5. Generation-pinned authorized source reads compute actual SHA256, CRC/MD5 and
   byte counts, preserving original bytes and all associations privately. Do not
   fabricate missing metadata/digests or place specimens in Git/console output.
6. Use the authenticated API's existing intake/upload/complete flow with stable
   idempotency keys, verified App Check/identity and exact collection scope;
   primary-source choice must match source authority. Retain upload receipts,
   application generation/digest/size, canonical specimen IDs, all original
   associations and current revision. SQL checksum conflict requires explicit
   reconciliation; it cannot silently reduce the denominator or substitute data.
7. Independently read back all ten records and every relevant exact-generation
   source binding. Prepare `specimen-pilot/v1` only after actual import proof;
   every `application_source.source_object_index` binds the approved original.
   Freeze and externally pin ready-manifest bytes. Pass the same hash, UID/scope
   and readiness reference to API, worker launch policy, SAM and QA.
8. Verify denial for anonymous/unverified/wrong-collection identities and
   restart/reload persistence. Preserve the original denominator of ten even
   if a specimen needs review or is blocked. Structural manifest validation
   alone never establishes imports, processing, quality clearance or acceptance.

No cloud bootstrap apply command or source-import CLI is currently implemented
in this data owner scope. Existing bootstrap produces reviewable artifacts only;
the API intake path and separately approved protected data delivery must be
materialized with the runtime/coordinator before real application. If a specimen
has multiple originals, retaining those associations is mandatory; a single
primary application source must not be reported as processing every original.

## Cheapest safe restore and cost admission

Reuse an already successful, sufficiently fresh native backup when it covers
the quiesced source checkpoint. Otherwise price and approve one new backup.
Restore only to the uniquely named disposable target above; never over production.
Choose the smallest compatible target compute after inspecting actual edition,
engine, source extensions and restore requirements. Google permits target
cores/memory to differ but sets disk to at least the larger configured/backup
disk size. Flags and restored backup configuration require explicit comparison.
[Cloud SQL restore behavior](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restore).

Writers/worker dispatch stay quiesced through backup, isolated restore, schema
review/application, unique-index checks, the exact supplemental SQL files,
connector reconciliation, row/catalog comparisons and `ANALYZE`. Verify all
27 expected schema tables as actually deployed, full scope/row hashes, sequence
state, source/run/receipt provenance and repeated connector restarts. Compare
supplemental index definitions/validity; `IF NOT EXISTS` does not repair a
wrong or invalid index. Resume only the verified runtime revision. Preserve
recovery proof before removal of the temporary target; cleanup of this new
target alone now has user authority, without source deletion or retention changes.

The current planning allocation is **USD 1 for incremental backup/restore**
inside the shared USD 5 ceiling; ordinary reservations target USD 4 and leave
USD 1 contingency. Two hours is the approved maximum; the price still needs
verification. Before admitting the action, conservatively reserve:

`restore compute hourly rate × 2h + full allocated restore-disk cost × retained
time + incremental backup-retention cost + priced operations/transfers`.

Reserve through the authorized cleanup deadline, including startup/restore time.
The separate USD 0.75 storage/build/transfer envelope must include all selected
original bytes, application copies, derivatives, image pulls and network paths;
the same transfer must not be omitted or counted as free merely because it is
read-only. Use current region/edition SKUs and recorded bytes, rounding upward;
do not assume free-tier credit. [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
and [Storage pricing](https://cloud.google.com/storage/pricing).

There is no verified dollar quote yet: tier/disk/backup/object metadata remains
unavailable. A local logical dump/restore is useful low-cost preliminary proof
but does not replace the required native cloud recovery rehearsal. If minimum
safe recovery plus actual processing reservations cannot fit USD 5, keep the
release blocked at that exact cost gate; do not weaken backup or substitute
synthetic specimens. Budget alerts and a document TTL are not hard cost caps.

## Validation and remaining handoff

- Existing focused suite: 73 passed. New red suite: 15 failed / 41 passed.
  Initial green focused suite: 88 passed; the additional positive-input case
  also passes in canonical validation. Offline `validate_live_plan.py` passed.
  Green focused log: `/tmp/specimen-release-data-green-20260908.log`.
- Final canonical `scripts/ci/verify.sh`: exit 0, 805 Python passed / 26 skipped,
  120 Flutter passed / 7 skipped, Flutter analysis, release web build and
  repository/security gates passed. Log:
  `/tmp/specimen-release-data-final-verify-20260908.log`. The earlier gate before
  the eight review regressions passed 797 Python tests. Skips remain explicit;
  this local build does not deploy. The new report and closeout log receive
  an additional scoped repository/security check before commit.
- Independent coordinator re-review passed: 65 scoped tests and all 28 tested
  unsafe resource/cost/policy mutations rejected; no remaining code blocker in
  the reviewed diff. The owner's complete focused data suite passed 97 tests.
- Storage emulator on port 9559, preserved Java 21 runtime: exit 0. Denied
  anonymous/authenticated read/list/create/overwrite/delete and verified unchanged
  original bytes plus explicit privileged bypass. Log:
  `/tmp/specimen-release-data-storage-20260908.log`, SHA256
  `3c4c2cf9ee3f8f7fb212f86a51f0699c5323563621bd501caee704a58865b19f`.
  Own emulator shut down; synthetic configuration remains in
  `/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-storage-test.fTqkEG/`.
- Coordinator executed unchanged-baseline real local PostgreSQL/SQL Connect on
  ports 5579/9549, exit 0. Log:
  `/tmp/specimen-release-data-postgres-coordinator-20260908.log`.
  Fresh proof:
  `/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.CwKNiR/backup-restore-proof.json`,
  SHA256 `9b47e4a39e40f2a935a72dd50448f5e1e4aea4c3b15f7b5d4c056840c425ccd5`.
  Dump SHA256 `fe70258281a87ff060417740c4c972929f340b39c61d8554e4a261755c1d7ed8`.
  This task reread the log and proof: complete schema/data/index equality,
  two restored connector restarts and four post-repair equality checks passed.
  This is synthetic local evidence, not actual ten-specimen or Cloud SQL proof.
- Initial local listener attempt failed EPERM; approved retry overlapped the
  coordinator's run and stopped on EADDRINUSE before creating its test cluster.
  No process was killed to take the port. Coordinator cleanup stopped its own
  fixtures. User services on 3000/8000 were untouched.

Remaining sequence: coordinator completes authentication and materializes the
approved release contract; data finalizes actual metadata/cost packet; runtime and
data agree exact intake/manifest bindings; protected delivery applies approved
changes; independent QA verifies real recovery/import/identity and public product
acceptance. Budget and prior PR merge are resolved decisions, not missing inputs.

## Subsequent actual connector integration and metadata checkpoint

The coordinator assigned an actual local SQL Connect stage-cost/launch-ledger
round trip after runtime source `24e6550` and trusted protobuf snapshot repair
`d859ac6dfa9c64d7fb68037da03283b823303736`. The new opt-in
`tests/test_sqlconnect_stage_cost_roundtrip.py` persists only synthetic metadata;
it constructs no image bytes, blob adapter, model or cloud session.

The real REST connector returns integral JSON numbers. Snapshot get/save/history
and strict external cost validation passed even before the protobuf repair;
that test is independent persistence evidence, not a reproduction of the
protobuf Struct float defect. The runtime owner's separate real-Struct test
establishes the latter. The actual launch-ledger case failed because
`CreateDocument`/`SaveDocument` omitted the runtime's `pilot_launch` kind.

The authorized connector correction permits that exact control-document kind
and applies the existing `worker_cursor` creator restrictions to its read,
history and save paths. Active org/collection membership, writer role,
sensitivity, CAS and deny-all direct client checks remain. Both control kinds
remain excluded from ordinary offset/keyset document lists. The new
`scripts/data/pilot-ledger-test.mjs` runs in the existing PostgreSQL harness.

Actual connector red: `/tmp/specimen-release-pilot-ledger-red-20260908.log` and
`/tmp/specimen-release-stage-map-connector-isolated-red-20260908.log` (one snapshot
pass, one ledger failure). Green:
`/tmp/specimen-release-pilot-ledger-green-20260908.log` and
`/tmp/specimen-release-stage-map-connector-green-20260908.log` (two Python cases).
Checks prove same policy/launch digest and unchanged admission ledger after
fresh repository reconstruction, immutable history, rejected changed launch/map,
and rejected external fractional/boolean/string/float costs. The JS suite proves
creator/client/cross-scope/role/sensitivity denial, stale-CAS rejection and both
control-list denials. Independent coordinator reviewer found no blocking issue.
Canonical gate: `/tmp/specimen-release-pilot-ledger-verify-20260908.log`, exit 0,
805 Python passed / 28 skipped, 120 Flutter passed / 7 skipped, analysis,
repository/security and release web build. The two new opt-in tests actually ran
against runtime `d859ac6` separately; they skip on this data-only source checkout.

Fixture uses PostgreSQL 5589 / SQL Connect 9569, retained for the subsequently
assigned sensitivity contract, so do not stop it from another task. Exact-source
runtime archives are `/tmp/specimen-stage-map-runtime-red-24e6550/src` and
`/tmp/specimen-stage-map-runtime-green-d859ac6/src`. Recheck with
`FIREBASE_DATACONNECT_EMULATOR_HOST=127.0.0.1:9569 node scripts/data/pilot-ledger-test.mjs`
and `SPECIMEN_TEST_SQL_EMULATOR=true SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:9569
PYTHONPATH=/tmp/specimen-stage-map-runtime-green-d859ac6/src .venv/bin/python -m
pytest -q -s tests/test_sqlconnect_stage_cost_roundtrip.py`.

Cloud metadata is now available: the coordinator successfully reused the same
existing Firebase CLI account for read-only inventory without changing account
defaults or printing credentials. Private directory:
`/Users/anuragduddu/.codex/rollout-state/specimen-live/inventory-20260908-firebase`.
This supersedes the earlier authentication blocker. Independently read: one
bucket, 1,000 JPEG records plus one non-image marker, zero backup records, one
SQL database, two service accounts and one secret metadata record. SQL is
PostgreSQL 18, Enterprise, db-f1-micro, zonal, 10 GB SSD in us-east4, running;
backups are disabled. Bucket location is us-east1, uniform access true, inherited
public-access prevention and seven-day soft deletion. No public member appears
in the inventoried project or bucket bindings; inherited effective denial and
native restore remain unproven. No image bytes or cloud writes occurred.

Raw acquisition `subjects_1000.json` remains at
`/Users/anuragduddu/Documents/Codex/2026-08-13/fin/work/field_museum_fleas_api/subjects_1000.json`,
SHA256 `631095098ae2785891dddf97ef7b44b66f978a46080d0ed4fcaeda6cc4481c44`.
Its subject-derived filenames match all 1,000 cloud JPEG basenames exactly;
every record has exactly one original location and every cloud name one observed
generation. First ten match preserved page-one order and total 3,018,274 bytes.
The old CSV is absent; an earlier chat statement overclaimed its presence and
was corrected after direct filesystem verification. The raw JSON and original
script provide the surviving source-order evidence. Metadata freeze and current
cost packet are being prepared; no actual source sensitivity classification is
established merely by public acquisition provenance.

The user now requires a complete ten-specimen human-review journey, deferring
automated classification and clearance. Initial administrator sensitive access
remains false. A separate scoped contract is in progress for explicit new
non-sensitive intake while retaining default-sensitive legacy evidence,
creator-only control documents and no downgrade. This ledger correction does
not relax any sensitivity check or classify actual images.

## Explicit classification connector follow-up

The separate sensitivity candidate adds an auxiliary-document column with a true
default and seven named V2 operations for explicitly classified metadata. New
ordinary records require literal false in both the column and payload. Scoped
membership is checked on every read, history, receipt, list and write; historical
access follows the current parent classification. Controls remain creator-only
and cannot appear in ordinary lists. Promotion needs sensitive capability, and
no operation permits downgrade. Legacy auxiliary writes also bind the payload
to the protected column. All specimen create/save versions bind the snapshot
asset classification to the column, treating omission as sensitive.

This supports the runtime owner's separately committed strict domain/API path
without changing the initial administrator capability. It makes no classification
decision about actual source images. The repository's protected separate data
delivery still owns migration and publication; no local deployment occurred.

Validation: initial real connector tests failed on missing V2 operation and on
an older specimen create accepting unknown classification as non-sensitive.
Version-specific test variables were corrected before final validation; denial
assertions now reject INVALID_ARGUMENT false positives. Final real connector
suite passes legacy/default, explicit false, malformed classification, writer,
scope, client, creator, CAS, no-downgrade, both membership revocations and history
after promotion. Logs: `/tmp/specimen-release-sensitivity-red-20260908.log`,
`/tmp/specimen-release-sensitivity-specimen-red-20260908.log`, and
`/tmp/specimen-release-sensitivity-complete-green-20260908.log`.

Full PostgreSQL 18.6 / connector 3.2.0 suite passed on owned ports 5599/9579,
including 27 tables and 26,512 synthetic rows (22,151 specimens), two restored
restarts and four schema/data/index equality comparisons. Log:
`/tmp/specimen-release-sensitivity-postgres-20260908.log`. Proof:
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.Qyo5Fj/backup-restore-proof.json`,
SHA256 `5292c664181d331d21d3603e2613443dd22b9961bb193a1876517e3407aeb70b`.
That harness stopped its own processes after completing.

The stage-map/launch-ledger opt-in test now covers four actual round trips:
snapshot and ledger, each with legacy sensitive and explicitly ordinary metadata.
The ordinary cases use separate synthetic scopes with canViewSensitive=false.
All four pass against runtime source `e7f4985064c5b6a778b556852c0e4d0d247f456d`;
log `/tmp/specimen-release-sensitivity-runtime-roundtrip-20260908.log`.
REST still returns integer costs; no protobuf-float reproduction is claimed.
Canonical `scripts/ci/verify.sh` exit 0: 805 Python passed / 30 skipped, 120
Flutter passed / 7 skipped, analysis, web build and repository/security checks;
log `/tmp/specimen-release-sensitivity-verify-20260908.log`. The four opt-in
tests skipped on this data-only checkout and actually ran separately as above.

Independent runtime-owner review passed with no blocking finding. It reran the
suite and added 217 separate result/denial checks, including malformed legacy/V2
saves, CAS rollback, receipt/history after promotion and sensitivity revocation,
privileged-peer controls and keyset membership revocation. Reviewed source hashes
were unchanged; logs `/tmp/specimen-runtime-data-sensitivity-independent-20260908.log`
and `/tmp/specimen-runtime-data-extra-review-20260908.log`. A final four-case
runtime repeat against immutable archive `86e8eec37fd72cbdd94d69c91e57edc2fb6aeb03`
also passed in `/tmp/specimen-release-sensitivity-runtime-pinned-20260908.log`;
that revision additionally fixes supplied-session authentication reuse.
Preserve the owned 5589/9569 fixture until the reviewer finishes its remaining
runtime repeat. Native Cloud SQL recovery, effective IAM, current
cohort classification and production acceptance remain separate live gates.

## Frozen metadata, regional costs and database access checkpoint

Sensitivity source commit is `0fb70aa5e26e421e68e64a7f550a20d77e65e30a`.
The independent reviewer reconciled the reviewed file hashes to that commit and
reran all four runtime cases successfully; log
`/tmp/specimen-runtime-data-roundtrip-independent-20260908.log`. Its fixture
access is released. This later checkpoint changes observations and documentation,
not the reviewed sensitivity implementation or actual cohort classification.

Metadata-only freeze is complete and has been delivered privately to coordinator.
The surviving raw acquisition JSON/script/page-one order reconciles all 1,000
cloud JPEG basenames; the first ten have one original/generation each and total
3,018,274 bytes. The original CSV remains absent. All three private output files
are 0600 under `/tmp/specimen-first-ten-metadata-20260908/`:

| Artifact | SHA256 |
| --- | --- |
| ordered-catalog.json | `f2b472d8b005ebd6c23743cdfcb3c005bfe87be58b2672e90f83f4fb4d2893f1` |
| metadata-frozen.json | `5865f62c4b3d869ac2b516d78c23ceb0701f796cbf6c7f054c5e22ce79037e2b` |
| reconciliation.json | `56b4d7f9b17155643ac8864352a37676dac27ae85e28c470cd0fa576576c4fcd` |

These are source metadata and grouping evidence, not `specimen-pilot/v1` runtime
readiness. No image bytes have been read; source SHA256 values, verified imports,
admin UID/scope and actual classification remain pending coordinator execution.
The coordinator must retain the files in its durable private evidence location.

The plan now reflects pinned inventory observations: backups disabled, bucket
uniform access true, source order confirmed, and existing SQL tier/disk known.
It remains `proposal_not_applied`, with no ready-manifest hash or native restore
proof. The current SQL Connect service uses this Google Cloud SQL PostgreSQL
database; these are API and storage layers of the same configured application.
[Firebase SQL Connect CLI reference](https://firebase.google.com/docs/sql-connect/cli-reference#cloud-sql-management-commands).

On 2026-09-08, the rendered official pricing page was inspected after selecting
Northern Virginia (us-east4). Published USD rates are db-f1-micro $0.0112/hour,
SSD $0.000249178/GiB-hour, and standard backup used storage $0.00011726/GiB-hour.
Two hours of a 10 GiB zonal restore target therefore costs $0.02738356 for compute
and disk. An illustrative 10 GiB backup retained seven days adds $0.1969968;
30 days adds $0.844272. These are component estimates, excluding transfer,
operations and extra copies. Actual backup size and retention must be admitted
to the shared USD 5 ledger. No retention schedule or deletion beyond the approved
new clone was authorized here. [Cloud SQL pricing](https://cloud.google.com/sql/pricing).

The region selector updates the storage and instance tables together. The
generic $0.0105 rate belongs to the Iowa default; $0.018 in search results was
extended-support pricing. Neither establishes this PostgreSQL 18 restore rate.
Browser content export was unsupported, so the observed selected-region table
is retained in task tool evidence; no exported raw-price artifact is claimed.

IAM access remains a distinct prerequisite. Existing IAM authentication does not
grant database privileges; newly registered IAM users initially have none.
Use only the exact approved maintenance service account's database identity,
`specimen-data-release@specimen-digitization.iam`, with scoped Cloud SQL login
and connector permissions. [Cloud SQL IAM logins](https://docs.cloud.google.com/sql/docs/postgres/iam-logins).
Inventory/dump requires CONNECT on the named database, public-schema USAGE and
SELECT on relevant tables/sequences. MAINTAIN supports ANALYZE/REINDEX but does
not grant new-index creation. Exact supplemental DDL needs verified table-owner
rights, supplied through a separately reviewed existing owner or narrow owner
membership; do not infer those rights from project IAM.
[PostgreSQL privileges](https://www.postgresql.org/docs/18/ddl-priv.html).

Installed Firebase CLI 15.8.0 source establishes that `dataconnect:sql:setup` and
`dataconnect:sql:grant` can create/update passworded `firebasesuperuser`, create
additional IAM database users, and transfer ownership. These helpers must not
be substituted for the approved narrow bootstrap. The provider's ordinary setup
flow is broader than this release's authorized maintenance boundary. The live
login-user listing does not expose every internal NOLOGIN role, and ephemeral
schema metadata does not prove an empty database.

Read-only catalog packet `/tmp/specimen-data-iam-catalog-20260908.sql`, SHA256
`879c20f058f44e462c92f41c40fbe608d48af9d169fda3dae8dbddb241db039a`, was delivered
to root. It uses a read-only transaction, exact database guard and bounded
timeouts, then reads schema/table owners and relevant role grants/capabilities.
It passed syntax validation on local PostgreSQL 18; it has not run against live
SQL. Capture future owner/role output privately. Root owns the prerequisite IAM
database registration and any subsequent exact grants; DATA made no cloud writes.

After reviewer release and coordinator notice, the owned 5589/9569 fixture was
stopped and both listener ports verified unused. The observation-only plan update
passed the offline validator and all 28 plan regressions; implementation remains
the independently reviewed sensitivity commit. The user's empty Firebase console
observation is recorded for the initial-setup assessment, pending actual catalog
proof. No other local service, cloud resource or source image was changed.
