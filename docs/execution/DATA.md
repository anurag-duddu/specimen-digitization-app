# Data and platform execution report

Status: tested local foundation; production data rollout and end-to-end acceptance
remain incomplete. No cloud writes, secret access, migrations, rules deployment,
provisioning or production merge was performed by this task.

Worktree: `/Users/anuragduddu/.codex/worktrees/39c2/specimen-digitization-app`.
Branch: `codex/data-platform-foundation`. Base: `82fd60e`.
Coordinator: `01a07f44-7d89-7052-b968-5e96753493ad`.
Final commit is recorded in the task handoff; this report is part of that commit.

Read the shared execution PLAN, repository AGENTS, DEPLOYMENT, PRD, harness,
model-routing, GBIF and observability requirements. Adopted architect CONTRACTS
v0.1. Backend owns all Python code/dependencies and the external snake_case API.
Data owns GraphQL/configuration, Storage rules, local tests and this report.
Root `firebase.json` remains owned by release. `firebase.data-emulator.json` is
an isolated local-only config, not a deployment target.

## Implemented boundary

`dataconnect/schema/schema.gql` defines organization/collection membership,
collection hierarchy, specimens, immutable aggregate snapshots and receipts,
profiles, assets, runs, regions, observations, transcription versions, candidates,
evidence links, resolved fields, record versions, validation findings, review
records, audit, checkpoints, outbox, provider references and auxiliary upload/batch
metadata. Composite keys and foreign keys prevent cross-scope references. Explicit
short constraint/index names avoid PostgreSQL identifier truncation.

`operations.gql` is the current backend persistence contract:

- `Memberships`: active organization and collection rows. Backend intersects the
  two lists; results are bounded at 1000 and must fail closed if truncated.
- `GetSpecimen`, `GetSnapshot`, `ListSpecimens`: scope and sensitive-image/record
  authorization. GetSpecimen checks matching summary/snapshot revision; retry a
  read if concurrent update produces a mismatch. Backend may read summary then
  request that exact immutable revision with GetSnapshot.
- `GetReceipt`: replay lookup under actor, operation, collection and organization;
  no receipt returns null. A present receipt rechecks sensitive permission.
- `CreateSpecimen`, `SaveSpecimen`: membership checks, expected-revision update,
  immutable snapshot, request receipt, append-only audit and outbox in one
  `@transaction`. Exactly one CAS writer commits. Save rejects a final disposition
  on an operational state and rejects unknown final dispositions. Backend policy
  still owns all clearance evidence and role/action semantics.

`auxiliary.gql` provides Create/Save/GetDocument, GetDocumentVersion,
GetDocumentReceipt and ListDocuments. Kinds are `upload` and `batch`; upload
payloads contain offsets/checksums/references, not bytes or bearer URLs. All
auxiliary operations conservatively require sensitive-data access. CAS/version
and idempotency receipts preserve resumable metadata. ListDocuments limit is
1..100, with nonnegative offset.

`artifacts.gql` provides append-only normalized profile/asset/run/region/model
observation/transcription/evidence/candidate/record/resolved-field/finding/checkpoint
operations. No published operation updates/deletes original assets, raw
observations, immutable versions or audit. Unique object-generation and logical
observation-step keys reject duplicate records. These append operations are
separate transactions: the integrated backend currently persists aggregate JSON
snapshots, and must not claim all normalized child tables are populated atomically
with an aggregate. The normalized tables and append operations are tested
foundation for that mapping, not an implemented full projection pipeline.

One active run is represented by the aggregate's single active-run pointer and
backend state machine. A standalone normalized SQL partial-unique active-run index
is not implemented. The checkpoint table stores append-only attempt history;
aggregate revision provides backend checkpoint fencing. Outbox dispatch/acknowledge
and leases are not implemented here; durable engine comparison remains pending.

## Runtime adapter contract

Project `specimen-digitization`, location `us-east4`, service
`specimen-digitization-service`, connector `specimen-server`. Backend validates
Firebase ID token first and binds `actorUid` itself; a client-provided UID is never
trusted. Every data operation is `@auth(level: NO_ACCESS)`. Admin access bypasses
that directive, so membership `@check` directives independently run inside writes.
No raw arbitrary GraphQL endpoint is exposed by the application.

The official Node Admin SDK implements named server execution using REST
`POST /v1/projects/{project}/locations/{location}/services/{service}/connectors/{connector}:impersonateQuery`
and `:impersonateMutation`, with JSON `{operationName, variables, extensions: {}}`.
These are different from the client `:executeQuery`/`:executeMutation` endpoints,
which reject NO_ACCESS. Use ADC bearer authentication in production. The backend
owns its Python REST adapter; no Python SQL Connect SDK was invented.

Operation variables are camelCase; application wire fields remain snake_case.
GraphQL UUID results are 32 hexadecimal characters without hyphens; normalize
using a UUID parser. Snapshot `Any` is PostgreSQL JSONB; backend validates the
opaque Pydantic domain. New revision is 1; save computes expectedRevision+1.
Backend enforces a 256KiB UTF-8 snapshot bound before sending. Large raw responses,
images and masks belong in Storage. Growing audit/previous_runs arrays will
require normalized paginated history before scale; overflow must fail explicitly,
never truncate retained evidence.

On retry: fetch receipt in the same scope, compare canonical request digest,
return the receipt's exact snapshot if equal; different digest is conflict. A
unique receipt race rolls back the entire mutation, then the caller rereads the
receipt. A stale revision must not be blindly retried as a new decision. Preserve
actor, request and operation through retries. Revocation is checked at commit;
service identities with arbitrary SQL/admin access remain privileged, and are not
constrained by end-user authorization directives.

## Original assets and Storage

`storage.rules` denies every direct Firebase client read/list/create/update/delete,
including authenticated users. SQL-backed membership cannot be queried from these
rules. Backend-mediated resumable chunks/session are therefore required; Flutter
must not use direct Firebase Storage SDK uploads under this policy.

The server checks active organization/collection membership and sensitive access
before every upload continuation/completion or image access. It validates actual
bytes, SHA256, file signature/type, size and decoded dimensions; filename and EXIF
are untrusted. Keep the original unchanged. Object keys include immutable IDs or
content digest under organization/collection scope; derivatives use distinct keys
and retain transform/version and original reference. Persist bucket, object name,
returned generation and verified digest, not a permanent download token.

Use GCS generation-match=0 when creating an original. If retried creation returns
412, verify the existing generation, size and digest rather than overwriting.
Read exact generations. Authorize short-lived access before issuing a signed URL;
URLs/session tokens are bearer credentials and cannot appear in SQL snapshots,
logs, browser analytics or audit payloads. Proxy access can provide tighter
revocation than a previously issued URL.

Storage rules do not govern Admin/GCS IAM requests; the Storage test explicitly
shows this bypass. Separate bucket-scoped object creator and reader identities;
no runtime delete permission on originals. Generation preconditions plus a
create-only identity prevent routine overwrite, but do not prove protection
against privileged deletion, retention-policy changes or project administrators.
Object retention/legal hold and verified deletion require institution-approved
policy and a separately authorized administrative identity. A failed SQL commit
can leave an orphan object; reconcile after retention grace, never delete retained
evidence as transaction compensation.

## Secret Manager and least privilege design

No secret values were read. Store only a provider connection ID and exact Secret
Manager version resource, enabled status, approved routes/data classes/regions in
SQL. Never store API keys, refresh tokens or signed upload URLs in JSON snapshots.
Server configuration binds logical connection to approved org/collection and exact
`projects/specimen-digitization/secrets/.../versions/N`; do not accept a secret
resource from request data or use mutable `latest` for a pinned run.

Backend runtime uses ADC/workload identity. Grant secretAccessor on the specific
secret only to the model runtime that needs it. API, Flutter and Hosting deploy
identity receive no provider-secret access. Runtime resolves the pinned version,
checks enabled connection/policy before each invocation, keeps value in memory,
redacts exceptions and traces, and fails to processing_blocked on disabled,
missing, denied or invalid credentials. Rotation is a new version plus approved
connection update; it does not rewrite historical run provenance. Credential
revocation must stop new calls and invalidate any runtime credential cache.

Before rollout, review a custom SQL Connect runtime role containing only required
connector impersonation execution permissions, not schema/connector administration
or arbitrary SQL migration privileges. Scope IAM to supported service/connector
resources and test actual denial behavior; effective IAM is not proven by these
local tests. Separate SQL migration identity, original writer/reader, worker and
secret accessor. Keep the Hosting deploy identity restricted as DEPLOYMENT.md
requires. No SQL credentials or service-account key files are introduced.

## Read-only cloud observations

Observed 2026-09-07 America/Chicago (UTC 2026-09-08); metadata only:

| Resource | Observation |
|---|---|
| SQL Connect | specimen-digitization-service, us-east4, no connector listed |
| Database | specimen-digitization-database on specimen-digitization-instance |
| Cloud SQL | PostgreSQL18, RUNNABLE, ZONAL; backups enabled=false |
| Network metadata | IPv4 enabled=true, requireSsl=false; these fields alone do not establish effective connector transport policy |
| Storage | specimen-digitization.firebasestorage.app, US-EAST1, uniform bucket access=true |
| Storage recovery | public-access prevention inherited; soft delete 604800 seconds; no retention policy returned |
| Secret metadata | huggingface-runtime-token version2 enabled, version1 disabled |

All gcloud requests explicitly specified project specimen-digitization; the
workstation default points elsewhere. `firebase dataconnect:services:list` checked
required API enablement as part of listing; services were already present. No
provisioning was requested. Metadata presence is not runtime readiness. Backups,
restore rehearsal, region/transfer policy, TLS/IAM, schema migration and storage
retention are explicit launch gates; no configuration was changed to resolve them.

## Tests and exact commands

`~/.cache/firebase/emulators/dataconnect-emulator-3.2.0 build -config_dir dataconnect`
passes. The binary can return exit0 with GraphQL errors, so the automated test
runner parses its JSON errors array instead of trusting exit status alone.

Run `scripts/data/test-postgres.sh` with PostgreSQL18 binaries and the SQL Connect
3.2.0 emulator. Defaults: PostgreSQL loopback5559, connector loopback9509; override
POSTGRES_BIN, DATACONNECT_EMULATOR_BIN, SPECIMEN_TEST_PG_PORT and
SPECIMEN_TEST_DC_PORT as needed. It creates a unique temporary cluster, starts no
system service, tests real named operations, restarts the connector and verifies
stored versions, then stops only its own processes. Logs/synthetic data remain in
the printed temporary directory for inspection; remove that exact directory after
review. It never contacts a cloud database. Local trust authentication is limited
to loopback and disposable synthetic test data.

Passed behaviors: create, absent receipt, exact historical snapshot, CAS/stale
rollback, outsider read/write denial, direct client NO_ACCESS, active membership
revocation, sensitive read/list denial, operational/final shape validation,
auxiliary upload offset/history CAS, concurrent writers (one commit), audit/outbox
counts, normalized asset/run/region/observation inserts, logical step/object
uniqueness, cross-collection FK rejection and connector restart reconstruction.

The Firebase15.8.0 bundled PGlite database passes sequential tests but **fails the
concurrent transaction regression**, reporting `unexpected transaction status idle
in transaction` and shutting down. The test remains enabled. Do not substitute
PGlite success for PostgreSQL concurrency validation.

Run Storage tests with a task-scoped Java21+ environment:

```bash
JAVA_HOME=/path/to/jdk21/Contents/Home \
PATH=/path/to/jdk21/Contents/Home/bin:"$PATH" scripts/data/test-storage.sh
```

Storage emulator tests pass: anonymous/authenticated read, list, new upload,
overwrite and delete all denied; original bytes remain unchanged; Admin bypass is
explicit. They do not prove production GCS preconditions, IAM, signed URL expiry,
resumable byte transport or retention.

Java17 from Android Studio was insufficient for Firebase15.8.0 (requires21+).
Temurin21.0.12.1+1 was downloaded into `/tmp/specimen-data-java21`, checked against
vendor SHA256 `3623232f33a9c3baadf304480b2535f9a3cba8a58d42ecbb438ba267315d9998`.
No global JAVA_HOME changed. Homebrew installed PostgreSQL18.6, krb5 and updated
its ca-certificates/OpenSSL dependencies; no PostgreSQL service was enabled. Its
new default cluster is unused; tests use unique temporary clusters. The initial
backend integration fixture uses `/tmp/specimen-data-pg39c2/cluster` on port5549
and connector9499; stop these only after backend releases its integration lease.

Canonical `scripts/ci/verify.sh` passed repository hooks, Python tests, Flutter
analysis/tests and release web build. Rerun after final staging so new data files
are included in all-file hooks. Data tests run separately and must be included by
the release owner in the reviewed data/runtime workflow; existing Hosting workflow
remains Hosting-only.

## Migration and acceptance gates

Do not deploy this schema or rules through Hosting CI. A separate reviewed data
rollout requires cloud owner authorization, database backup/PITR and restore
proof, staging diff review, effective runtime/migration IAM separation, validation
of generated cascade behavior, additive/backward-compatible schema sequencing,
connector compatibility, verification of old/new runtime behavior and a rollback
plan. No automated rollback may delete immutable data. Generated @ref defaults
include cascading parent deletes; prevent parent deletion through runtime IAM and
published operations, and review DB-level retention controls before production.

Acceptance contribution: PRD19 #2/#5/#6/#7/#9/#16/#17/#18 storage and provenance
foundation, #1 resumable metadata, #13 operational-disposition separation. This is
not full acceptance of these criteria: actual SAM3/model inference, cleared-field
policy, end-to-end upload bytes, provider access, approved museum quality data,
full normalized graph reconstruction, cloud restore/recovery and a live rollout
remain owned by the coordinated integration and approval gates.

Primary references: [SQL Connect directives](https://firebase.google.com/docs/reference/sql-connect/gql/directive),
[Admin SDK](https://firebase.google.com/docs/sql-connect/admin-sdk),
[official Admin REST implementation](https://github.com/firebase/firebase-admin-node/blob/master/src/data-connect/data-connect-api-client-internal.ts),
[GCS generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions),
[Secret Manager guidance](https://docs.cloud.google.com/secret-manager/docs/best-practices).

## Reusable integration server and CI installation boundary

`scripts/data/serve-local.sh` creates an isolated PostgreSQL cluster on5549 and
SQL Connect on9499, seeds only the canonical synthetic organization/collection
ending0001/0002 with UID `synthetic-reviewer`, and waits until interrupted. Ctrl-C
stops its own processes. The separate `seed-integration.mjs` can repeat local
fixture creation. Both accept only loopback emulator traffic; no real credentials
are needed. Override the port environment variables when another task holds the
default ports. Backend confirmed its Python production adapter against this local
service (membership, create/get/CAS/list and auxiliary create/get/list).

CI installation is release-owned: pin PostgreSQL18.6 (Ubuntu PostgreSQL binaries
or a reviewed image with immutable digest), Firebase CLI15.8.0 and downloaded
SQL Connect emulator3.2.0, Node supported by that CLI, and Temurin21.0.12.1+1.
Set POSTGRES_BIN/DATACONNECT_EMULATOR_BIN explicitly on Linux; the local scripts'
Homebrew defaults are conveniences, not portable CI paths. Install/download using
signed official repositories or verified vendor checksums; resolve and review
architecture-specific artifact digests in the CI PR. Do not add an unpinned
`latest` database image, paid services or data/rules deployment to Hosting CI.
Toolchain installation in CI has not been implemented or tested by this task.

Readiness classification: missing tested backup/restore is a hard launch gate.
Zonal availability and the SQL/Storage regional difference are architecture and
cost/residency tradeoffs for the owner to accept or change; they do not by
themselves mandate a migration. The requireSsl metadata needs effective transport
verification before any security conclusion. No unilateral remediation is proposed.

The initial leased integration processes can be stopped after backend/QA release:
terminate only the connector process launched by this task, then use
`/opt/homebrew/opt/postgresql@18/bin/pg_ctl -D /tmp/specimen-data-pg39c2/cluster -m fast stop`.
Do not stop other PostgreSQL clusters. An independent QA server can use
`SPECIMEN_TEST_PG_PORT=5569 SPECIMEN_TEST_DC_PORT=9519 scripts/data/serve-local.sh`.
Its Ctrl-C trap handles its own process cleanup and prints its unique data directory.

## Integration lease cleanup — 2026-09-08

After the backend released its lease and the coordinator confirmed QA/integration
use independent clusters, stopped the task-owned SQL Connect PID64810 on9499
and PostgreSQL PID64827 on5549. Verified each process command and PostgreSQL
postmaster file against `/tmp/specimen-data-pg39c2/cluster` before stopping.
Sent TERM to that connector only and used `pg_ctl -D` with the exact owned cluster
and fast shutdown. TCP checks confirmed both loopback ports closed. Preserved the
cluster, logs and repository evidence; no other service or cloud resource changed.
QA/integration should launch the documented isolated server from their immutable
candidate, choosing separate PostgreSQL and connector ports.
