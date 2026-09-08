# Live data and platform report

Status: **local implementation verified; live data scope and release blocked**.
Date: 2026-09-08. Coordinator: `01a07f48-a57c-71b0-9642-c9430886049c`.
Branch: `codex/live-data-platform`.
Worktree: `/Users/anuragduddu/.codex/worktrees/0cf0/specimen-digitization-app`.
Baseline: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Candidate SHA, PR and CI links are recorded in the coordinator/task handoff after push.
This report is committed with the implementation; a commit cannot contain its own hash.
During verification origin/main advanced to
`1d297db520a6e31021e7bfa5e5f81b77e90cf618`; this branch and local evidence remain
based on `a53f855`. Latest-main assembly and corrective client changes belong to integration.

## Objective, scope and decisions

Prepare the data release for exactly the first ten existing cloud specimens,
including all associated source objects. Do not expand the pilot, substitute
failed specimens, infer ordering from image appearance, or claim a private
manifest exists before the metadata establishes source grouping and order.
The supplied administrator email remains in the coordinator's private decision
artifact; no user identity or specimen material is committed here.

Owned: SQL Connect, Storage rules/tests, data scripts, data/IAM proposal and new
pure `application/pilot_manifest.py`. API/processing ownership was coordinated;
no shared `production.py`/`storage.py`, provider, lockfile or Hosting edits.
Read AGENTS and DEPLOYMENT completely. No cloud write, deployment, IAM change,
secret value access, paid inference, or original image download occurred.
Existing user services on ports 3000/8000 were left running and untouched.

## Current cloud inventory: Blocked

All seven initial explicit-project gcloud queries failed before usable metadata:
bucket list, SQL instance list, project IAM, service accounts, secret metadata,
objects and backups. Error: `Reauthentication failed. cannot prompt during
non-interactive execution.` Existing ADC fallback failed `DefaultCredentialsError`.
Stopped retries and reported the gate to coordinator. Interactive reauthentication
with the existing authorized account is required; no global account/project was changed.

Private errors are retained outside Git, mode 0600, beneath
`/Users/anuragduddu/.codex/private/live-rollout/data-20260908/` (directory 0700).
An empty/failed query is **not** an empty bucket or database observation.
Historical `DATA.md` observations are not current proof of backup configuration,
connector deployment, SQL version, bucket layout, service accounts or secret versions.

After authentication, `uv run python scripts/data/inventory_cloud.py --output-dir
NEW_PRIVATE_DIRECTORY` saves read-only resource/IAM/Storage/SQL Connect metadata
privately, emits only counts/status, and stops on a failed query. No secret
versions are accessed, APIs enabled, SQL executed or object bytes downloaded.
Secret version enabled-state and effective runtime IAM still require separately
captured metadata/denial checks before launch.

**Exact-ten result: Not confirmed.** Selected specimens: none frozen. Source order,
grouping, generations, hashes, byte count, application import and original-source
readiness reference all remain unknown. User authorization permits reading only
the selected ten after generations are frozen; there is no arbitrary image fallback.

## Private pilot authority contract

Worker and QA accepted `specimen-pilot/v1` directly. Required fields:

- `schema_version`, `status: ready`, `project_id: specimen-digitization`,
  `authorization_reference`, `selection: {order: explicit_source_order,
  source_inventory_sha256}`.
- Exactly ten `specimens`, with consecutive `ordinal` 1..10, distinct canonical
  `specimen_id`, and one explicit UUID `organization_id`/`collection_id` scope.
- Every `source_objects` entry binds `bucket`, `object_name`, decimal-string
  `generation`, `sha256`, positive `size_bytes`; optional `crc32c`/`md5_hash`.
- `application_source` binds `blob_ref` (`sha256:generation`), `sha256`,
  `size_bytes`, `source_object_index`. Hash/size must match the selected original.
  Original multi-object associations remain intact even when the application uses
  one primary source. Application generations may differ from original generations.

`load_ready_manifest(path, expected_sha256)` requires an independently supplied
hash of the exact private file bytes. It rejects an absent hash, modified bytes,
wrong count/order/scope/binding, extra fields, incomplete metadata, symlinks,
nonregular files including FIFOs, wrong owner/mode and files inside Git.
The bounded loader is local only; it does not prove cloud reads/imports occurred.
Worker launch policy must independently bind authorized spending, identity, expiry
and the same manifest hash. A structurally valid document is not live evidence.

`scripts/data/pilot_manifest.py freeze-metadata` selects only the first ten rows
of a privately supplied ordered catalog with explicit grouping/ordering evidence.
It records immutable generations and available checksums as `metadata_frozen`
under the separate `specimen-pilot-source/v1` schema. Unknown SHA256 stays null;
CRC32C/MD5 never becomes SHA256. The runtime rejects this preliminary stage.
After authorized generation-pinned reads and independently verified application
imports, the approved ready artifact is checked with `validate-ready --manifest
PRIVATE_FILE --sha256 EXTERNAL_PIN`. Outputs are exclusively created 0600 outside Git.

## Runtime and first-admin contracts

`dataconnect/connector/readiness.gql` adds bounded, server-only `Readiness`.
API calls named `impersonateQuery`, discards returned IDs, and uses a three-second
timeout. Anonymous and authenticated client access is denied in emulator tests.
Storage readiness uses exact private object/generation `objects.get`, requiring
neither `buckets.get` nor `objects.list` grants. No actual readiness object is guessed.

`infra/live/data-resources.json` is a validated **proposal, not applied IAM**.
Candidate identities are `specimen-api-runtime` and `specimen-worker-runtime` in
the pinned project; existence and effective permissions are not confirmed.
Runtime connector permissions contain only named query/mutation impersonation.
Storage grants contain only object get/create, conditionally restricted to
`application/sha256/`. No runtime object delete/update/list, bucket metadata,
schema/connector administration, arbitrary GraphQL or SQL access is proposed.
API receives no provider secrets; worker secret grants belong to separately
approved exact-secret processing policy. Neither receives Hosting release identity.
The lowest supported connector IAM binding/condition and actual denied operations
must be tested live; a proposed permission list is not effective-IAM evidence.
The current application hash prefix is shared across collection scopes; SQL/API
membership checks remain the trusted collection boundary, not per-collection GCS IAM.

`scripts/data/bootstrap_admin.py` accepts explicit private request and exported
Firebase Admin record files. Email and UID must match exactly; verified must be
true and disabled false. Sensitive access defaults false. It prepares a new 0600
maintenance artifact only; there is no production apply command or bootstrap
operation in the runtime connector. The transaction locks the organization,
checks exact collection scope/no existing admin/no existing target membership,
then inserts both memberships atomically. It never upserts, reactivates or upgrades
an existing membership. Concurrent first-admin attempts yield one winner.
Before a later authorized application: fresh Auth lookup in pinned project,
explicit scope/permission review, approved artifact hash and real backup/restore
evidence are required. No live UID or account verification has been obtained yet.

## Migration and restore evidence

`schemaValidation: COMPATIBLE` is explicit. Official Firebase documentation
recommends compatible migrations for existing data; it is not a substitute for
reviewing actual SQL or testing old/new connector compatibility.
[Configuration reference](https://firebase.google.com/docs/sql-connect/configuration-reference)
and [migration guide](https://firebase.google.com/docs/sql-connect/manage-schemas-and-connectors).

Real local PostgreSQL 18.6 + SQL Connect emulator artifact 3.2.0 passed:

- Full `pg_dump` custom backup, restore to a distinct disposable database, and
  equality of all 27 tables / 26,315 synthetic rows (22,139 specimens), schema,
  sequence state, representative membership/source/run/observation/receipt/audit
  data and four supplemental index definitions/validity.
- Two restored connector restarts, immutable prior/current connector reads,
  four complete fingerprint comparisons after explicit index repair/repeated DDL.
- Scoped `specimen_scope_checksum` remains unique and valid at every inventoried
  stage; exact checksum query chooses that index after restored `ANALYZE`.

**Observed issue:** emulator 3.2.0 removes all four nonunique supplemental indexes
on startup even in COMPATIBLE mode. Source and restored databases reproduce this.
The test explicitly reapplies `dataconnect/sql/paging-indexes.sql` and
`dataconnect/sql/search-indexes.sql` after schema reconciliation. Repeated DDL
must leave catalog/records unchanged. `IF NOT EXISTS` alone does not repair an
invalid or mismatched existing index; compare definition and validity first.
No automatic-preservation or Cloud SQL backup claim is made.

Release ordering in the public proposal requires quiescing API writes, worker
dispatch and in-flight transactions before migration. Keep writers quiesced through
schema/connector changes, unique-constraint checks, supplemental-index repair,
restored planner-statistics refresh and full validation. Only then resume verified
runtime revisions. This local harness has no writers during those phases; actual
production fencing and denial require delivery/QA evidence before migration.

Restore rollback must use a separately approved isolated Cloud SQL instance and
preserve the original instance. Record successful backup ID, recovery point,
instance/connector revisions, restore counts/hashes and application smoke. An
application rollback retains compatible schema and immutable evidence; do not
drop tables, erase receipts, roll back valuable writes by blindly restoring over
production, or delete orphan originals as transaction compensation. Any destructive
schema reversal needs its own reviewed recovery decision.
[Cloud SQL restore guidance](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restore).

## Commands, outcomes and artifacts

| Check | Outcome |
|---|---|
| New pilot/metadata/bootstrap/proposal Python tests | Confirmed: 73 passed |
| `uv run python scripts/data/validate_live_plan.py` | Confirmed: offline scope/IAM/migration proposal gate passed |
| `SPECIMEN_TEST_PG_PORT=5569 SPECIMEN_TEST_DC_PORT=9519 scripts/data/test-postgres.sh` | Confirmed: full real local PostgreSQL/connector/bootstrap/backup/restore suite passed |
| Java21, `SPECIMEN_TEST_STORAGE_PORT=9539 scripts/data/test-storage.sh` | Confirmed: anonymous/authenticated read/list/create/overwrite/delete denied; admin bypass and unchanged original demonstrated |
| `scripts/ci/verify.sh` | Confirmed: repository gates, Python 428 passed / 26 skipped; Flutter analysis, 76 passed / 7 skipped, release web build passed |
| Actual Cloud SQL backup/restore, data migration, IAM denial, private import, admin bootstrap | Not run; live gates remain |

Final local data log: `/tmp/specimen-data-rehearsal-final2-20260908.log`.
Final proof directory:
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.QyrfUm/`.
Contains `backup-restore-proof.json`, full synthetic dump, before/after catalogs,
per-table row hashes/counts, source reconciliation and connector logs.
Dump SHA256: `85a8f1c0764574151d17650740f8ad00917d3abf3143e3ede1c2304f79c29690`.
Emulator binary SHA256: `408c52c857af86df7bcf71b9ab7d9e1eeb29a12f042d79c76000e85f22a2e975`.
Storage log: `/tmp/specimen-live-storage-20260908.log`.
Canonical log: `/tmp/specimen-live-data-verify-final3-20260908.log`.
Skipped Python/Flutter cases are not passes or live proof; real PostgreSQL and
Storage cases were exercised separately by the commands above.

Failed experiments remain outside Git: `specimen-data-test.J6lFqe` captured
checksum audit output overflow and index-loss investigation; `pBDxMx` captured
restored planner-statistics failure. Fixed the audit harness's 1MiB output ceiling
to 16MiB for the combined >10k fixture and added `ANALYZE` after restore. Local
fixture counts are synthetic test coverage and never the authorized live denominator.
Independent review fixed omitted external hash pin, FIFO blocking, incomplete
migration sequence validation and scope/provider policy bypasses; regression tests pass.
Read-only gcloud subprocesses disable API-enable/auth prompts and inherit no stdin;
fixture scripts explicitly reject ports 3000/8000 without relying on Bash errexit
behavior for compound tests.

## Minimal resource/cost proposal and outstanding inputs

Reuse the existing proposed SQL instance/SQL Connect service/bucket; propose **zero
new persistent SQL instances** and **one temporary isolated restore clone** for the
required recovery rehearsal. Do not provision until budget and exact configuration
are approved. The current instance tier, storage size, backup size and backup/PITR
settings cannot be priced from failed metadata queries. Do not reuse older rates.

Incremental data cost inputs: restore-clone tier hourly rate × approved clone hours;
retained backup GiB × storage duration/rate; ten-authorized-object bytes × download
egress rate; object operation counts and new immutable application/derivative bytes.
Use current region/edition pricing after metadata is available and add delivery's
API/worker and processing's bounded inference estimates. `cost_inputs` keeps each
unknown and the user's missing dollar cap null. A budget alert is not a hard cap;
worker launch bounds, expiry and shutdown authorization must separately enforce
the approved pilot spend. No dollar estimate or zero-cost claim is fabricated.
[Cloud SQL pricing](https://cloud.google.com/sql/pricing),
[Cloud Storage pricing](https://cloud.google.com/storage/pricing),
[Storage permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions).

Next owners: coordinator obtains authentication and budget; data inventories,
establishes exact source order/grouping and freezes ten generations before source
reads; data/API resolve explicit account UID and collection scope; delivery/QA
stage approved migration/IAM/runtime fencing and real recovery/denial evidence.
Each ready-manifest hash and runtime/schema/connector version must appear in the
consolidated packet. This scoped PR must remain unmerged until coordinator review.

## PR and CI handoff

Canonical local gate passed before the scoped push. Exact candidate SHA, PR and
all-five-check CI run are provided in the final coordinator/task handoff without
extra commits solely to self-record a CI URL. No merge or deployment is authorized
for this owner task. Hosting proof remains separate from runtime/data acceptance.
