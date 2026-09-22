# Owner inputs for the release plan templates

The guarded planes refuse to run without a typed plan inside the release
envelope. The templates beside this file are those plans with every value the
repository can already prove filled in, and one `<OWNER:name>` placeholder for
every value only the project owner can supply.

Nothing here deploys, mints or authorizes anything. Filling a template in is a
preparation step. `docs/execution/RELEASING.md` describes the one command that
seals a filled plan into an envelope, and `docs/DEPLOYMENT.md` remains the
authority on what a release actually requires.

## How to use a template

1. Copy the template to a private file outside this repository, mode `600`.
2. Replace every `<OWNER:name>` string with the value from the table below. The
   placeholder is always the whole JSON value, never part of a longer string.
3. Keep the filled values' JSON types: a placeholder standing in for a number
   becomes a number, not a quoted string. The table says which.
4. Do not add, remove or rename any other key. Every plan validator uses an
   exact key set, so an extra field fails the release closed.
5. Pass the filled file to `scripts/ci/mint_release_packet.py --plan-path`.

`scripts/ci/test_release_plan_templates.py` runs each template through the same
validator the deploy script calls, so a template that drifts away from the
schema fails CI rather than a release run.

## The templates

| Template | Plan version | Envelope plane |
|---|---|---|
| `data-initialization-inventory.plan.template.json` | `data-initialization-inventory/v1` | `data` |
| `data-initialize-missing.plan.template.json` | `data-initialize-missing/v1` | `data` and `data-initialization` |
| `data-apply.plan.template.json` | `data-apply/v1` | `data` |
| `data-bootstrap.plan.template.json` | `data-bootstrap/v1` | `data` |
| `runtime-build.plan.template.json` | `runtime-prepare/v1` | `runtime-build` |
| `runtime-prepare.plan.template.json` | `runtime-prepare/v1` | `runtime` |
| `runtime-activate.plan.template.json` | `runtime-activate/v1` | `runtime` |
| `evidence-digests.template.json` | not a plan | `--evidence-digests` for the mint command |

Only `evidence-digests.template.json` carries a `_template` guidance block. The
mint command reads named keys from that file and ignores anything else. The plan
templates cannot carry one: their validators reject every unexpected key.

The `data-initialize-missing/v1` plan is minted twice, once into the
`data-production` envelope and once into `data-initialization-production`, with
the same plan bytes and a different plane. `runtime-build` and `runtime-prepare`
are likewise two envelopes of one release run.

## Sequence

Hosting first, then data, then runtime. Hosting needs nothing from this table:
it deploys from `.github/workflows/ci-cd.yml` on a merge to `main`.

1. `data-initialization-inventory/v1` reads the native catalog and encrypts it
   to the coordinator's key. It changes nothing.
2. `data-initialize-missing/v1` creates the missing application database and
   continues into the compatible schema, connector, index and rules apply.
3. `data-bootstrap/v1` inserts the first organization, collection and owner.
4. `runtime-build` publishes the three images; `runtime-prepare/v1` brings up
   the API in the same run. Leave `worker` and `sam` as `null` on that first
   preparation: the ready manifest does not exist until the cohort is imported
   through the running API.
5. `runtime-activate/v1` starts SAM and runs the one worker execution.

`data-apply/v1` is the ordinary later path, for a database that already exists.
It is not part of the first sequence but uses the same recovery contract.

## Conventions used by the commands

```bash
PROJECT=specimen-digitization
REPO=anurag-duddu/specimen-digitization-app
REGION=us-east4
token() { gcloud auth print-access-token; }
```

Every command below is read only. None creates, changes or deletes a resource,
and none prints a secret value: the Secret Manager commands list version
resource names only.

## Every envelope

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `source_sha` | The merged `main` commit this release is for, 40 hex characters. | every plan template | `gh api repos/$REPO/commits/main --jq .sha` |
| `authorization_sha256` | Digest of the private approval record for this release. Must equal the packet's `authorization_sha256`. | `data-initialize-missing`, `data-apply` | `shasum -a 256 <authorization file>` |
| `independent_review_sha256` | Digest of the reviewer's report against this exact source tree. Must equal the packet's review digest. | `data-initialize-missing` | `shasum -a 256 <review report file>` |
| `pilot_manifest_sha256` | The frozen cohort identity, that is `selection.source_inventory_sha256` in the frozen manifest. Ten specimens, `subject_105526321` to `subject_105526330`. | `data-initialize-missing`, `data-apply` | `jq -r .selection.source_inventory_sha256 <frozen manifest>` |
| `pool_id` | The workload identity pool that issues the release job credential. | `data-initialize-missing` | `gcloud iam workload-identity-pools list --location=global --project=$PROJECT --format='value(name)'` |

## Data: observed Cloud SQL and Firebase state

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `sql_settings_version` | The source instance's current `settings.settingsVersion`. The plan calls it `database_etag`. String. | all three data plans | `gcloud sql instances describe specimen-digitization-instance --project=$PROJECT --format='value(settings.settingsVersion)'` |
| `source_disk_gb` | The source instance's data disk size in GiB. Number, 1 to 10. | `data-initialize-missing`, `data-apply` | `gcloud sql instances describe specimen-digitization-instance --project=$PROJECT --format='value(settings.dataDiskSizeGb)'` |
| `source_database_version` | The source instance's PostgreSQL version, for the ordinary apply path only. Initialization is pinned to `POSTGRES_18`. | `data-apply` | `gcloud sql instances describe specimen-digitization-instance --project=$PROJECT --format='value(databaseVersion)'` |
| `restore_clone_tier` | Owner decision: the smallest tier the source can be restored onto. One of `db-f1-micro`, `db-g1-small`, `db-custom-1-3840`, `db-custom-2-7680`. | `data-initialize-missing`, `data-apply` | Owner decision, after reading the source tier: `gcloud sql instances describe specimen-digitization-instance --project=$PROJECT --format='value(settings.tier)'` |
| `storage_ruleset_name` | The ruleset name currently released for Storage, or `null` when no release exists. | `data-initialize-missing`, `data-apply` | `curl -s -H "Authorization: Bearer $(token)" "https://firebaserules.googleapis.com/v1/projects/$PROJECT/releases/firebase.storage/$PROJECT.firebasestorage.app" \| jq -r .rulesetName` |
| `catalog_recipient_public_key_pem` | The reviewed coordinator public key, SPKI PEM, RSA 3072 or larger, exponent 65537. The private key never enters CI. | all three data plans | Owner decision. The coordinator keeps the private half; paste the exact PEM text of the public half. |
| `catalog_recipient_public_key_sha256` | Digest of those exact PEM bytes. | all three data plans | `shasum -a 256 <public key PEM file>` |

## Data: the empty Firebase schema placeholder

Firebase can leave an empty onboarding `schemas/main` while the PostgreSQL
database is still absent. Read the resource once and copy the four observed
fields. If the resource is genuinely absent, delete the whole
`schema_placeholder` key and set `schema_etag` to `null` instead.

```bash
curl -s -H "Authorization: Bearer $(token)" \
  "https://firebasedataconnect.googleapis.com/v1/projects/$PROJECT/locations/$REGION/services/specimen-digitization-service/schemas/main"
```

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `schema_placeholder_etag` | The placeholder resource's `etag`. The same value fills the plan's `schema_etag`. | `data-initialize-missing` | `.etag` of the response above |
| `schema_placeholder_uid` | The placeholder's `uid`, a canonical UUID. | `data-initialize-missing` | `.uid` of the response above |
| `schema_placeholder_create_time` | The placeholder's `createTime`, with a timezone. | `data-initialize-missing` | `.createTime` of the response above |
| `schema_placeholder_update_time` | The placeholder's `updateTime`, with a timezone. | `data-initialize-missing` | `.updateTime` of the response above |
| `schema_etag` | The deployed schema's `etag` on the ordinary apply path. | `data-apply` | `.etag` of the response above |
| `connector_etag` | The deployed connector's `etag` on the ordinary apply path. | `data-apply` | `curl -s -H "Authorization: Bearer $(token)" ".../services/specimen-digitization-service/connectors/specimen-server" \| jq -r .etag` |

## Data: the one recovery window

These eight values describe one backup, one isolated clone and one held claim.
They must satisfy, in order: `clone_allowance_issued_at_unix` at or before the
packet's issue time, then now, then `recovery_expires_at_unix`, then the
packet's expiry, then `clone_allowance_expires_at_unix`, which may not exceed
the allowance issue time plus two hours. All five are numbers.

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `recovery_expires_at_unix` | Absolute deadline for the restore clone. At most two hours after now. | `data-initialize-missing`, `data-apply` | Owner decision inside the packet window: `date -u -v+100M +%s` |
| `clone_allowance_issued_at_unix` | When the one fixed-key clone allowance was issued. | `data-initialize-missing`, `data-apply` | `.issued_at_unix` of the issued allowance record |
| `clone_allowance_expires_at_unix` | When that allowance expires. | `data-initialize-missing`, `data-apply` | `.expires_at_unix` of the issued allowance record |
| `clone_allowance_baseline_sha256` | Digest of the reviewed issuance baseline for the allowance. | `data-initialize-missing`, `data-apply` | `shasum -a 256 <allowance baseline file>` |
| `clone_allowance_iam_sha256` | Digest of the reviewed exact-object create-only IAM evidence for the allowance. | `data-initialize-missing`, `data-apply` | `shasum -a 256 <allowance IAM evidence file>` |
| `backup_retention_expires_at_unix` | Finite expiry for the one new source backup. After the packet and clone expiry, and at most 172 hours after the packet was issued. Number. | `data-initialize-missing`, `data-apply` | Owner decision: `date -u -v+48H +%s` |
| `backup_max_chargeable_bytes` | Reserved ceiling for that backup, at least `source_disk_gb` times 1073741824 and at most 10737418240. Number. | `data-initialize-missing`, `data-apply` | Owner decision from the disk size read above |

See `docs/execution/CLONE_ALLOWANCE.md` and
`docs/execution/FINITE_RECOVERY_BACKUP.md` for what each record must contain.

## Data: the one-time initializer privilege

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `native_source_catalog_sha256` | The independently reviewed complete native source catalog hash from the inventory phase. | `data-initialize-missing` | `gh run download <inventory run id> --repo $REPO --name data-initialization-recovery-<sha>-<attempt>` then `jq -r .catalog_sha256`, recomputed from the decrypted envelope per `docs/execution/DATABASE_INITIALIZATION.md` |
| `data_initialize_wif_provider` | The separately pinned initializer provider, exactly `projects/716045864126/locations/global/workloadIdentityPools/<pool_id>/providers/specimen-data-initialize`. | `data-initialize-missing` | `gcloud iam workload-identity-pools providers list --workload-identity-pool=<pool_id> --location=global --project=$PROJECT --format='value(name)'` |
| `conditional_binding_sha256` | Digest of the reviewed conditional source and clone IAM binding evidence. | `data-initialize-missing` | `gcloud projects get-iam-policy $PROJECT --format=json > policy.json` then `shasum -a 256 <reviewed binding evidence file>` |
| `disposal_binding_sha256` | Digest of the separately reviewed disposal binding evidence. | `data-initialize-missing` | `shasum -a 256 <reviewed disposal binding evidence file>` |

`privilege_window_seconds` is already filled at 600, the approved maximum.
Lower it if the review bounds it further; anything outside 120 to 600 fails.

## Data: the first organization, collection and owner

The whole `bootstrap.payload` block is machine generated. Do not hand edit it.
Run the offline preparer, which makes no cloud calls and writes a private file:

```bash
uv run python scripts/data/bootstrap_admin.py --first-scope \
  --request <private request json> --auth-record <private admin record json> \
  --output <private artifact outside git>
```

Then copy that artifact into `bootstrap.payload` unchanged. The values below are
the ones you chose or that the preparer computed, listed so the plan can be
reviewed field by field.

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `data_ready_source_sha` | The commit the signed schema readiness receipt was produced on. It may be older than `source_sha`. | `data-bootstrap` | `jq -r .source_sha data-ready.json` from the downloaded receipt |
| `admin_uid` | The administrator's Firebase UID, verified and enabled. | `data-bootstrap` | `curl -s -H "Authorization: Bearer $(token)" -H "Content-Type: application/json" -d '{"email":["ADDRESS"]}' "https://identitytoolkit.googleapis.com/v1/projects/$PROJECT/accounts:lookup" \| jq -r .users[0].localId` |
| `admin_email` | That account's exact email address. | `data-bootstrap` | Owner decision, confirmed by the same lookup: `jq -r .users[0].email` |
| `org_uuid` | Owner decision: the organization's fixed UUID. It must not already exist. | `data-bootstrap` | Owner decision: `python3 -c 'import uuid; print(uuid.uuid4())'` |
| `collection_uuid` | Owner decision: the first collection's fixed UUID. | `data-bootstrap` | Owner decision: `python3 -c 'import uuid; print(uuid.uuid4())'` |
| `organization_name` | Owner decision: the organization's display name. Bounded text, at most 256 bytes. | `data-bootstrap` | Owner decision |
| `collection_name` | Owner decision: the first collection's display name. | `data-bootstrap` | Owner decision |
| `bootstrap_auth_record_sha256` | The preparer's digest of the four account fields. | `data-bootstrap` | `jq -r .auth_record_sha256 <prepared artifact>` |
| `bootstrap_artifact_sha256` | The preparer's digest of the whole artifact. It also fills `bootstrap.sha256` and the candidate's `approvals.bootstrap_sha256`. | `data-bootstrap`, `evidence-digests` | `jq -r .artifact_sha256 <prepared artifact>` |

## Runtime: the signed data readiness receipt

Every runtime plan binds the receipt the data release published. The runtime
plan's `data_receipt.source_sha` is `source_sha`, because runtime promotion
requires a data receipt for this same commit.

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `data_ready_receipt_sha256` | Digest of the exact `data-ready.json` bytes. It also fills the candidate's `data.compatibility_evidence_sha256`. | `data-bootstrap`, all three runtime plans, `evidence-digests` | `gh run download <data run id> --repo $REPO --name data-ready-<sha>-<attempt>` then `shasum -a 256 data-ready.json` |
| `data_ready_run_id` | The GitHub run id that published it. Number. | `data-bootstrap`, all three runtime plans | `jq -r .run_id data-ready.json` |
| `data_ready_run_attempt` | That run's attempt. Number. | `data-bootstrap`, all three runtime plans | `jq -r .run_attempt data-ready.json` |

## Runtime: the API environment

Eight of the ten API environment values are already filled: the project, project
number, the three Firebase app ids, the region, the SQL service and connector,
the bucket and the two approved CORS origins. Only the readiness object is
per-release.

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `readiness_object` | The frozen private readiness object's name inside the bucket, under `application/sha256/`. | all three runtime plans | `gcloud storage ls gs://$PROJECT.firebasestorage.app/application/sha256/` |
| `readiness_object_generation` | That object's exact generation, as a string of digits. | all three runtime plans | `gcloud storage objects describe gs://$PROJECT.firebasestorage.app/<object> --format='value(generation)'` |

## Runtime: worker, SAM and the ready cohort

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `worker_launch_secret_version` | Immutable resource name of the launch policy secret version. A numeric version, never `latest`. | `runtime-prepare`, `runtime-activate` | `gcloud secrets versions list <launch secret> --project=$PROJECT --format='value(name)'` then `projects/$PROJECT/secrets/<secret>/versions/<n>` |
| `pilot_manifest_secret_version` | Immutable resource name of the ready manifest secret version, shared by the worker and SAM. | `runtime-prepare`, `runtime-activate` | `gcloud secrets versions list <manifest secret> --project=$PROJECT --format='value(name)'` |
| `worker_launch_sha256` | Digest of the exact launch policy document bytes. | `runtime-prepare`, `runtime-activate` | `shasum -a 256 <launch policy json>` |
| `ready_manifest_sha256` | Digest of the exact ready manifest document bytes. The same value fills `sam.manifest_sha256`. | `runtime-prepare`, `runtime-activate` | `shasum -a 256 <ready manifest json>` |
| `sam_expires_at_unix` | Absolute SAM deadline. More than 125 seconds from now, at most one hour, and not past the packet expiry. Number. | `runtime-prepare`, `runtime-activate` | Owner decision inside the packet window: `date -u -v+55M +%s` |
| `sam_checkpoint_sha256` | Canonical digest of the offline SAM3 checkpoint file map. | `runtime-prepare`, `runtime-activate` | `jq -r .sam3_checkpoint_files <launch policy json>` then the canonical digest recorded with the cached checkpoint |
| `sam_checkpoint_prefix` | The content addressed cache prefix, exactly `application/sha256/<sam_checkpoint_sha256>/sam3-cache`. | `runtime-prepare`, `runtime-activate` | Derived from the value above |

The SAM revision `3c879f39826c281e95690f02c7821c4de09afae7` and the audience
`https://specimen-sam-716045864126.us-east4.run.app` are already filled. So is
`worker.timing_version`, which requires the USD 12 budget authority
`release-cost-ledger/v3`. Remove that one key to release under the legacy
authority, and expect the legacy USD 5 ceiling.

## Runtime activation

`api.expected_etag` and `api.previous_revision` are both filled with
placeholders here because activation always follows a preparation. On a first
preparation both are `null`, as the `runtime-build` and `runtime-prepare`
templates show, and the validator requires the two to agree.

```bash
curl -s -H "Authorization: Bearer $(token)" \
  "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/services/specimen-api"
```

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `api_service_etag` | The live API service's `etag`. | `runtime-activate` | `.etag` of the response above |
| `api_previous_revision` | The API revision currently serving, name only, matching `specimen-api-...`. | `runtime-activate` | `.latestReadyRevision` of the response above, last path segment |
| `prepared_receipt_run_id` | The run that published `runtime-receipt.json`. Number. | `runtime-activate` | `gh run list --repo $REPO --workflow runtime-release.yml` |
| `prepared_receipt_run_attempt` | That run's attempt. Number. | `runtime-activate` | `jq -r .run_attempt runtime-receipt.json` |
| `prepared_receipt_sha256` | Digest of the exact `runtime-receipt.json` bytes. | `runtime-activate` | `gh run download <run id> --repo $REPO --name runtime-receipt-<sha>-<attempt>` then `shasum -a 256 runtime-receipt.json` |
| `ready_manifest_bytes` | The ready manifest document itself, as one JSON string whose digest is `ready_manifest_sha256`. | `runtime-activate` | `jq -Rs . < <ready manifest json>` |
| `worker_launch_bytes` | The launch policy document itself, as one JSON string whose digest is `worker_launch_sha256`. | `runtime-activate` | `jq -Rs . < <launch policy json>` |
| `collection_profile_bytes` | The draft collection profile document, as one JSON string whose digest is the launch's `evidence_profile_sha256`. | `runtime-activate` | `jq -Rs . < <collection profile json>` |
| `collection_profile_secret_version` | Immutable resource name of the profile secret version. | `runtime-activate` | `gcloud secrets versions list <profile secret> --project=$PROJECT --format='value(name)'` |
| `hf_secret_version` | Immutable resource name of the inference token secret version. Only the worker runtime reads it. Must equal the launch policy's `hf_secret_resource`. | `runtime-activate` | `gcloud secrets versions list <inference secret> --project=$PROJECT --format='value(name)'` |
| `worker_actor_uid` | The verified Firebase UID the worker acts as. It needs a nonsensitive membership in the bootstrapped collection. | `runtime-activate` | The same Identity Toolkit lookup used for `admin_uid` |
| `trace_project_id` | The reviewed existing trace destination project identity. | `runtime-activate` | Owner decision, from the reviewed trace destination record |
| `worker_logfire_token_secret_version` | Immutable resource name under `projects/specimen-digitization/secrets/specimen-worker-logfire`, with a numeric version. | `runtime-activate` | `gcloud secrets versions list specimen-worker-logfire --project=$PROJECT --format='value(name)'` |
| `trace_identity_receipt_sha256` | Digest of the reviewed trace destination identity receipt. | `runtime-activate` | `shasum -a 256 <trace identity receipt file>` |

`activation.human_review_authorization_sha256` is already filled with the
approved `human-review-release-scope/v2` digest from
`docs/execution/APPROVED_RELEASE_BUDGET.md`. The `runtime-production`
environment variable `RELEASE_HUMAN_REVIEW_AUTHORIZATION_SHA256` must hold the
same value or admission fails. `worker_trace.approval_sha256` and
`worker_trace.service_name` are filled from the approved trace contract.

## The public readiness candidate

`evidence-digests.template.json` is not a plan. It feeds
`mint_release_packet.py --evidence-digests`, which turns it into the public
candidate that `validate_release_packet.py` and `check_release_readiness.py`
judge. Every value is a digest of release evidence the mint command cannot
observe. A `null` is reported as a named gap, not filled in.

| Input | What it is | Consumed by | How to get it |
|---|---|---|---|
| `api_image_reference` | The published API image by digest, never by tag. | `evidence-digests` | `gcloud artifacts docker images list us-east4-docker.pkg.dev/$PROJECT/specimen-runtime/api --include-tags --format=json`, or pass `--from-registry` and let the mint command read all three |
| `worker_image_reference` | The published worker image by digest. | `evidence-digests` | Same command for `.../specimen-runtime/worker` |
| `sam_image_reference` | The published SAM image by digest. | `evidence-digests` | Same command for `.../specimen-runtime/sam` |
| `api_image_provenance_sha256` | Digest of the API image's verified build provenance. | `evidence-digests` | `gh attestation verify oci://<reference> --repo $REPO --format json` then digest the retained result |
| `worker_image_provenance_sha256` | Digest of the worker image's verified provenance. | `evidence-digests` | Same command for the worker reference |
| `sam_image_provenance_sha256` | Digest of the SAM image's verified provenance. | `evidence-digests` | Same command for the SAM reference |
| `sam_artifacts_sha256` | Digest of the pinned SAM3 model artifacts at the pinned revision. | `evidence-digests` | From the retained offline checkpoint evidence for revision `3c879f39826c281e95690f02c7821c4de09afae7` |
| `sam_config_sha256` | Digest of that revision's model config. | `evidence-digests` | From the same retained checkpoint evidence |
| `deployed_schema_sha256` | Digest of the deployed SQL Connect schema evidence. | `evidence-digests` | From the signed data release receipt for the deployed schema resource |
| `deployed_connector_sha256` | Digest of the deployed connector evidence. | `evidence-digests` | From the same signed receipt |
| `deployed_storage_rules_sha256` | Digest of the released Storage ruleset evidence. | `evidence-digests` | From the same signed receipt |
| `backup_restore_evidence_sha256` | Digest of the retained `native-recovery.json` proving backup and verified isolated restore. | `evidence-digests` | `gh run download <data run id> --repo $REPO --name native-recovery-<sha>-<attempt>` then `shasum -a 256 native-recovery.json` |
| `contract_approval_sha256` | Digest of the approved release contract record. | `evidence-digests` | `shasum -a 256 <contract approval file>` |
| `budget_approval_sha256` | Digest of the approved budget record. Confirm it is the same record `src/specimen_digitization/release_budget.py` pins as `APPROVAL_SHA256`. | `evidence-digests` | `shasum -a 256 <budget approval file>` |
| `provider_data_approval_sha256` | Digest of the approved provider data handling record. | `evidence-digests` | `shasum -a 256 <provider data approval file>` |
| `public_config_sha256` | Digest of the published public build settings. | `evidence-digests` | `shasum -a 256 <public settings file>`, cross checked with `scripts/ci/validate_public_settings.py` |
| `rollback_sha256` | Digest of the reviewed rollback point for this release. | `evidence-digests` | `shasum -a 256 <rollback record file>` |

## What is not in this table

The mint command asks for five private files and three short answers of its
own: the authorization artifact, the review report, the budget ledger, the cost
review, the reviewer session id, the project number, the pool id and the pilot
manifest digest. Those go on the command line or at its prompts, not into a
plan. `docs/execution/RELEASING.md` covers them.
