# First-production recovery allowance

This source contract replaces the absent-clone CREATE-history admission check.
The filtered operations request returned HTTP 403; omitting the instance returned
HTTP 400. Neither result proves unused allowance. Existing-instance operation
history, native ownership, temporary-principal lifecycle and clone disposal checks
remain required. This contract does not issue authority or qualify native setup.

## Typed authority and baseline

Every `data-apply/v1` and `data-initialize-missing/v1` recovery plan now requires
`recovery.allowance` with exactly these fields:

| Field | Required value or binding |
|---|---|
| `version` | `first-production-restore/v1`, the stable allowance ID |
| `bucket` | `specimen-digitization.firebasestorage.app` |
| `object` | `application/release-control/first-production-restore.json` |
| `authority_sha256` | Original authority digest, equal to the admitted packet |
| `baseline_sha256` | Independently reviewed coordinator issuance/outcome baseline |
| `manifest_sha256` | Original ten-specimen manifest, equal to the packet |
| `iam_sha256` | Independently reviewed effective IAM and native bucket qualification |
| `issued_at_unix`, `expires_at_unix` | Original finite claim window, at most two hours |

The packet and recovery deadlines must fit within that original window. The
fixed object key never varies with date, source, run, attempt, manifest, clone
name or plan. An old plan without this contract cannot create recovery liability.
The exact admitted source tree binds the helper and workflow; existing data-only
fingerprints retain their schema/connector compatibility meaning.

Before issuing actual bytes, the coordinator must reconcile every prior
creation-capable packet, signed intent, outcome and in-flight operation since
the original approval. A missing file or a current native 404 cannot establish
that baseline. Inspect the exact claim namespace including historical/noncurrent
versions. Any prior or unknown claim/creation blocks issuance; deletion never
refunds allowance. A coordinator tombstone records no-refund issuance provenance;
it is not the atomic exclusion mechanism.

## Protected workflow and native request

The protected data workflow prepares `clone-allowance-intent.json` from the exact
packet and plan bytes, attests it at the merged source, and publishes it as
`clone-allowance-intent-SOURCE-ATTEMPT` in the current run. Before claiming, the
helper downloads this immutable artifact and verifies its signature, exact bytes,
source/workflow and source/run/attempt bindings. Publication or verification
failure prevents the claim and all backup/clone effects.

The ordinary data identity performs one request:

`POST https://storage.googleapis.com/upload/storage/v1/b/specimen-digitization.firebasestorage.app/o`

Query parameters are exactly `uploadType=multipart`, the fixed `name`,
`ifGenerationMatch=0`, and `projection=noAcl`. This is the JSON API's single
multipart/related upload, not resumable or XML multipart upload. Metadata contains
only the exact name, `contentType: application/json`, `temporaryHold: true`, and
the canonical payload's base64 MD5 integrity checksum. SHA256 binds the original
authority, baseline, manifest, IAM, source tree, packet, plan and signed intent.
No ACL, retention configuration, context or KMS override is supplied.

The canonical payload is at most 2 KiB, the complete multipart body 4 KiB, and
the decoded native response 16 KiB. Request/response bytes and exclusive send
intent are retained with private permissions and fsync. The locked transport
disables AuthorizedSession's automatic 401-refresh replay, adapter retries and
redirects. Credential refresh before sending is allowed; application requests
are never resubmitted. On the protected Ubuntu runner, a main-process POSIX timer
interrupts credential refresh, response headers and body reads within 30 seconds
or the remaining original authority, whichever is shorter. The same timer covers
capability-guarded SQL effects. It refuses nested timers; a slow/dripping response
cannot silently extend the request. The helper performs zero Storage reads.

Only a complete HTTP 200 from this invocation qualifies: exact object kind,
bucket, name, content type, payload length/checksum, positive generation, initial
metageneration and `temporaryHold=true`, all before the original deadline.
Failed retention, malformed/truncated response, non-200, timeout or unknown
outcome stops before backup/clone. No receipt or generation loaded from disk,
another job or a Storage read can reconstruct the in-memory winner.

Backup, clone create and restore run in that same process. Each stage has an
exclusive local journal and admits at most one native submission. The transport
rejects both legacy and finite backup creates, clone insertion and restore
without the live capability, including the verified numeric project alias.
Before backup/create, admission is rechecked along with source revision, actual
clone 404, runtime absence and original deadlines. A second runner with the same
packet must claim again and lose. A winner dying before backup leaves a spent
claim. Later signed initialization/schema continuation does not claim or recreate
the backup/clone. Cleanup never modifies the claim.

## Native setup and continuing costs

Root must independently qualify the existing bucket's actual location, class,
uniform access, defaults, lifecycle, encryption and effective inherited IAM.
Propose only `storage.objects.create` for the ordinary data identity, conditioned
on the exact `projects/_/buckets/BUCKET/objects/OBJECT` resource and a separately
reviewed finite request-time window. Prefer a project-level binding; a bucket
policy change would additionally need separately reviewed reconciliation with
SAM's original-policy cleanup. No actual IAM mutation is part of this change.

The data identity must lack claim get/list/update/delete/setRetention/setIamPolicy
capabilities; adding a create-only role does not remove inherited grants.
Initializer, runtime and Hosting identities receive no claim access. Keep runtime
object permissions inside `application/sha256/`. The held claim survives clone
deletion and lifecycle expiry; no workflow clears its hold or deletes it.
Administrators are trusted not to reset that namespace. Noncurrent versions alone
do not prevent a generation-match-zero insert, hence the baseline and live hold.

Cost admission must cover one insert per approved invocation, failed contenders,
bounded traffic, preflight/setup reads, audit/encryption charges and continuing
held-object storage at the verified bucket location. Reserve up to 8 KiB of
billable content/metadata over an explicit initial 365-day horizon and carry the
continuing liability beyond it. The accounting horizon is not a deletion date.
No new packet, window, ledger reservation or native claim is created by the
source implementation. The cumulative USD 5 cap and exact ten-specimen scope
remain unchanged. Provider behavior and effective grant success require root's
native qualification; offline fixtures alone cannot establish them.

Primary provider contracts:
[objects.insert](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/insert),
[preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions),
[atomic object operations](https://docs.cloud.google.com/storage/docs/consistency#atomic_operations),
[object holds](https://docs.cloud.google.com/storage/docs/object-holds),
[IAM conditions](https://docs.cloud.google.com/storage/docs/access-control/iam#conditions),
[JSON API permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-json?hl=en).
