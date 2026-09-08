# Proposed runtime, App Check and provider wiring

Status: review proposal only, 2026-09-08 UTC. No resource creation, IAM change,
API enablement, secret read/rotation, production merge or paid inference is
authorized or performed. This document contains no deployment commands.
Owner: release/integration task; coordinator approves scope and spending.
Read with DEPLOYMENT.md, ARCHITECTURE.md, CONTRACTS.md, DATA.md and QA.md.

## Decision to review

Use the existing `specimen-digitization` Google/Firebase project, SQL Connect
service/database and Storage bucket. Propose one Cloud Run API service and a
separate worker delivery design, with keyless identities. Keep the existing
Hosting workflow static-only. Do not deploy the polling worker as a background
thread in a request-billed API. Persisted scanning, revision CAS and five-minute
leases already exist. Local failure tests now cover publication races, shared
circuits, durable unknown outcomes and hard child-process deadlines. Validate
those mechanisms with production identities and storage, select supervised
worker hosting and complete the required engine comparison before production
processing; an outbox consumer is not required for correct scanner recovery.

The initial API resource is concretely proposed below; worker hosting cannot be
approved as a complete processing plane until the Temporal/Google Workflows
comparison and fencing/dispatch/restart gates pass. SAM 3 serving needs its own
approved GPU/model/license/data/cost assessment. This proposal does not select a
workflow engine or authorize a GPU resource.

## Observed configuration and proposed resources

| Resource | Existing evidence / exact proposal | Approval or verification needed |
|---|---|---|
| Project | Existing `specimen-digitization`, number `716045864126` | Use explicit project on every operation; workstation default differs |
| SQL | Existing `specimen-digitization-service`, database `specimen-digitization-database`, instance `specimen-digitization-instance`, `us-east4`; proposed named connector `specimen-server` | Reviewed schema/connector rollout; backup/PITR and restore proof before data launch |
| Storage | Existing `specimen-digitization.firebasestorage.app`, `US-EAST1` | Deny-all client rules rollout; IAM/preconditions/retention review; no region migration proposed |
| API | Proposed Cloud Run service `specimen-api` in `us-east4`; immutable image digest from proposed Artifact Registry Docker repository `specimen-runtime` in `us-east4` | Cloud Run and Artifact Registry APIs/resources need inspection/authorization before creation; runtime deployment must pass auth/data tests |
| API sizing | Proposed initial maximum 2 instances, minimum 0, 1 vCPU, 1 GiB RAM, concurrency 8, request timeout 60 seconds | Bounded upload/decode/load evidence must justify these trial limits; they are not a cost ceiling or production capacity claim |
| Worker | Reserved name `specimen-worker`, isolated identity below | Hosting mode/region/CPU/minimum count remain unapproved until engine comparison; a polling loop needs continuously allocated compute, not API request lifetime |
| SAM 3 | Reserved name `specimen-sam3` if Cloud Run is validated for the approved model | No GPU type, region, minimum count or image proposed as approved; actual adapter/mask/crop/model-revision proof required |
| Web App Check | Existing Firebase web app `1:716045864126:web:a193fa80c7a98bcac8e2ef`; proposed reCAPTCHA v3 registration consistent with Flutter | Config GET returns SERVICE_DISABLED; existing registration unknown. Confirm or register only after explicit API/config authorization |
| Provider secret | Data owner observed `projects/specimen-digitization/secrets/huggingface-runtime-token/versions/2` enabled | Reverify version metadata and approved route/data policy at authorization time; value never needed in review output |

Read-only 2026-09-08 evidence: GitHub repository and production-environment
variable lists are empty; repository secret names list only
`FIREBASE_OPTIONS_DART_B64`. App Check v3 and Enterprise configuration GETs return
403 PERMISSION_DENIED with reason SERVICE_DISABLED for
`firebaseappcheck.googleapis.com`. Cloud Run list returns SERVICE_DISABLED for
`run.googleapis.com`. An alternate runtime is not ruled out; no API was enabled
to turn an unknown into a claim of absence.

Data reports ZONAL SQL and disabled backups. Backup/restore is a launch gate.
High availability and the SQL/Storage region difference are explicit owner
availability/latency/transfer-cost tradeoffs; this proposal does not silently
require or perform a paid HA upgrade or data relocation.

## Least-privilege identities and binding review

All new identities below are proposed, not created. Use attached service
identities/ADC, never JSON keys. Keep the existing
`github-firebase-hosting@specimen-digitization.iam.gserviceaccount.com` unchanged.

| Proposed identity | Required access | Explicit exclusions |
|---|---|---|
| `specimen-api@specimen-digitization.iam.gserviceaccount.com` | Named SQL connector query/mutation; Firebase user lookup required by revoked-token checks; object create/get for authorized upload/access | No provider secret, object delete, schema/IAM administration, arbitrary SQL, model invocation or Hosting permissions |
| `specimen-worker@specimen-digitization.iam.gserviceaccount.com` | Named SQL connector query/mutation; original/raw/crop get/create; approved provider secret access; run.invoker only on approved SAM 3 service | No object delete, schema/IAM administration, arbitrary SQL or Hosting permissions |
| `specimen-sam3@specimen-digitization.iam.gserviceaccount.com` | Source get and derivative create restricted to approved bucket/prefix; only approved model asset access if needed | No SQL, provider token, object delete or public invocation |
| `specimen-runtime-release@specimen-digitization.iam.gserviceaccount.com` | Reviewed artifact push, existing runtime service update/read; actAs only API/worker identities when their release is approved | No provider secret value access, SQL migration, IAM administration or Hosting delivery |
| `specimen-data-release@specimen-digitization.iam.gserviceaccount.com` | Separately reviewed schema/connector/rules deployment permissions for named existing resources | No runtime image release, provider token or Hosting delivery; exact migration permissions require diff-specific review |

Propose custom runtime SQL role permissions
`firebasedataconnect.connectors.impersonateQuery` and
`firebasedataconnect.connectors.impersonateMutation`; exclude
`firebasedataconnect.services.executeGraphql`, executeGraphqlRead and schema
administration. Bind at the narrowest supported resource scope and prove effective
allow/deny with the exact REST calls. If only project-level binding is supported,
review a supported IAM condition and remaining blast radius explicitly. Do not
fall back to broad dataAdmin to make a test pass. The
[official permission catalog](https://docs.cloud.google.com/iam/docs/roles-permissions/firebasedataconnect)
lists these impersonation permissions; actual scope/custom-role support remains
an authorization-time test.

For Storage, combine objectCreator with a reviewed custom get-only permission on
the existing bucket and supported object-prefix conditions; avoid objectAdmin and
list permission where unnecessary. Runtime source currently uses
`application/sha256/` rather than tenant-scoped object prefixes, so application
authorization remains essential and per-tenant IAM isolation is not yet proven.
Generation-match zero and digest verification protect ordinary writes, while
retention and privileged deletion need separate policy. The API's revoked-token
check requires `firebaseauth.users.get`; propose a minimal custom permission
rather than authentication administration. Verify the exact SDK calls against
[Firebase Auth permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/firebaseauth).

## Client and API configuration contract

The Flutter build uses public, reviewed values:

- `SPECIMEN_API_BASE_URL`: the actual HTTPS API service URL obtained after its
  approved deployment; do not invent a run.app hostname or substitute localhost.
- `SPECIMEN_RECAPTCHA_SITE_KEY`: public v3 site key registered for
  `specimen-digitization.web.app`; add any additional origin only if actually
  supported and approved. The private reCAPTCHA secret belongs only in provider
  registration, never Dart, repository variables or logs.
- Production builds must omit/disable `SPECIMEN_LOCAL_SYNTHETIC` and omit
  `SPECIMEN_AUTH_EMULATOR_HOST`. PR/native checks retain synthetic configuration.

Store the two public values as repository variables once approved because the
web artifact build precedes the production deploy environment. Record their
reviewed change and build SHA. Environment-only variables are not automatically
available to that build job; do not copy secrets into PR jobs or move OIDC to the
build job. Production Flutter currently shows a connection/setup block when API
or App Check setup is absent, and synthetic mode requires an explicit local
build flag. Independently exercise those paths on the committed client before
acceptance; replace generic App Check setup errors with an actionable provider
configuration message if necessary.

The API remains internet reachable for browser/mobile requests; application
middleware must verify Firebase ID token (issuer/audience/expiry/signature and
revocation), App Check token and current SQL organization/collection membership
on every protected operation. Cloud Run IAM tokens cannot replace user Firebase
identity tokens. If public Cloud Run ingress/invocation is approved, the
unauthenticated surface is limited to CORS preflight and non-sensitive liveness;
all specimen/image data requires application auth. Review this deliberate ingress
boundary rather than assuming CORS is authorization. CORS allowlist starts with
`https://specimen-digitization.web.app` and required headers including
Authorization, X-Firebase-AppCheck, Idempotency-Key and Upload-Offset. Confirm the
client/backend exact App Check header name in integration tests.

Default Flutter providers are v3 for web, Play Integrity for Android and DeviceCheck
for Apple; their registration/signing/device gates are separate. Unsigned/debug
builds cannot establish production attestation. See
[Flutter App Check setup](https://firebase.google.com/docs/app-check/flutter/default-providers).
No debug attestation token belongs in a production build or policy fallback.

## Provider binding and startup gaps

The existing gateway reads `HF_TOKEN`. Proposed worker-only Cloud Run secret
binding maps that name to the exact approved secret version 2, with
secretAccessor on that secret only. No ordinary environment value or build ARG
contains the token. Cloud Run resolves secret environment values at instance
startup, so rotation requires a reviewed revision restart and old-revision drain;
revoking Secret Manager access alone does not erase an already cached token.
Connection revocation must stop new work and invalidate cached capability state.
Prefer explicit application version/resource checks per run where the approved
connection registry requires them. [Cloud Run secret guidance](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
recommends a pinned version for environment bindings.

`SPECIMEN_APPROVED_INFERENCE` remains false/unset until exact data/provider/spend
approval. `SPECIMEN_SAM3_ENDPOINT` remains unset until a reviewed authenticated
SAM 3 deployment exists. Missing/denied configuration yields processing_blocked,
never synthetic output or Deferred. Immutable runs retain provider/prompt/model
versions, source/raw digests and known external-effect ambiguity.

Implementation prerequisites before a container can be deployed: commit/review
an immutable container build; bind HTTP server to 0.0.0.0 and supplied PORT
(current local CLI binds loopback); verify production rejection of emulator transport
and synthetic profiles under real identities; validate the locally tested
scanning/lease/effect boundaries in the selected hosting model and complete the
engine/hosting decision; verify runtime readiness can represent unavailable components;
verify no secret access by API or frontend; exercise new-process SQL reconstruction
and production-profile semantics refusal. These gaps must be tested, not hidden
by a successful image build.

## Separate delivery sequence

1. Finish local integration and independent QA; create draft PR with exact passing
   candidate checks and honest P0 gaps. Existing Hosting workflow remains the
   only executable production delivery in this repository.
2. Obtain approval of resource names, ingress, region/sizing, budgets, identity
   bindings, data/provider policies and backup/restore plan. Perform required
   metadata verification without printing secret values.
3. Review a new data/runtime delivery contract in a separate PR. Only after that
   contract is explicitly approved may executable workflows be added. Proposed
   workflow names `data-release.yml` and `runtime-release.yml` use distinct
   `data-production`/`runtime-production` environments, main-only policy and
   separate keyless WIF conditions pinned to exact workflow refs. Do not broaden
   the existing Hosting WIF provider or grant its identity new roles.
4. Proposed data delivery stages backup/restore proof, migration diff, compatible
   schema/connector/rules revision, and application-version compatibility tests.
   Runtime delivery builds once, signs/attests digest, validates auth/readiness,
   and promotes that digest with revision/provenance checks. Each future workflow
   must independently preserve required checks and explicit production approval.
5. Set approved public client variables, release Flutter through the existing
   merged-PR CI/CD path, and match Hosting marker SHA plus authenticated product
   smoke to separately recorded runtime image and connector revisions. Test
   rollback compatibility before any traffic promotion. Data rollback never
   deletes immutable evidence to repair an application rollout.

## Cost and stop conditions

No spend cap has been supplied. Do not provision or infer paid approval from this
proposal. Before approval, estimate workload variables: upload/response GiB,
requests, active CPU-seconds and GiB-seconds, worker duty cycle, model tokens/GPU
seconds, active secret versions/access operations, retained object/DB/backup GiB,
SQL operations, build minutes and log volume. Record assumptions and approved
maximum daily/monthly spend alongside per-run provider caps. Maximum instances
and minimum zero constrain some compute behavior but do not cap egress, storage,
existing SQL or provider spend.

[Cloud Run pricing](https://cloud.google.com/run/pricing) distinguishes request-
and instance-based compute; an always-running worker has ongoing allocation cost.
[Secret Manager pricing](https://cloud.google.com/secret-manager/pricing) bills
active versions and access operations. Existing SQL runs independently of API
scale-to-zero; backup/PITR and retained evidence increase storage. Region
separation may add transfer cost. reCAPTCHA/provider quotas and paid tiers must
be checked against the approved traffic estimate. No monthly dollar total is
asserted without workload, billing-account and region-specific calculator inputs.

Required stop conditions: approval/budget missing; backup restore unproven; key or
runtime readiness absent; wrong source/image/connector revision; auth denial
regression; lost CAS/fencing or evidence; unknown institutional semantics; provider
policy/secret disabled. Preserve records and return explicit blocked status.
