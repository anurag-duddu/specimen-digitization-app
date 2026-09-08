# Live API runtime owner report

Status: Implementation and local gates complete; PR/CI handoff follows below. No production deployment or authentication claim.
Owner task: 01a08219-2fc7-79e3-a2a9-bace605c5862.
Coordinator: 01a07f48-a57c-71b0-9642-c9430886049c.
Branch: `codex/live-api-runtime`.
Worktree: `/Users/anuragduddu/.codex/worktrees/2bfe/specimen-digitization-app`.
Baseline SHA: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Frozen implementation SHA: `fedfaaeefc4646251f6a287c0a6deb76649dbb47` (this report may have a later documentation-only commit).

## Scope and decisions

Own API/CLI, runtime configuration/auth/health modules, API container and API tests.
No worker, provider, repository adapter, dependency lock, CI or IAM modifications.
Preserve local ports 3000/8000. Tests use ephemeral ports and fixture state.
Only the data owner's frozen first 10 cloud specimens are authorized for later
cloud sample work. No sample bytes have been accessed by this workstream.
Budget and production resources remain coordinator gates.

The production API verifies Firebase ID tokens with `check_revoked=True`, requires
`email_verified` true and verifies App Check plus an exact app ID allowlist.
Invalid/revoked/disabled/App Check failures return 403 `access_denied`;
cryptographically verified but unverified-email identities return 403
`email_verification_required`. Missing bearer returns 401 `http_error`.
SDK tests with injected returns/exceptions are local contract tests, not real
Firebase production or emulator validation. Memberships remain authoritative
server repository rows; no self-assignment or administrator configuration.

Exact HTTPS origins are required. Browser requests with any other Origin fail
before route execution; native requests without Origin still need both tokens.
OpenAPI/docs are disabled in production and responses use no-store.

## Runtime and delivery contract

Build from repo root with `docker build -f containers/api/Dockerfile
--build-arg SOURCE_SHA=<40 lowercase hex commit> -t <local image> .`.
`SOURCE_SHA` is mandatory and becomes packaged `_build.json` and OCI revision.
Production refuses missing/invalid provenance. Delivery must bind that build arg
to the clean tested source SHA and deploy by digest; the build cannot independently
attest that the caller supplied the correct SHA. Base Python and uv are digest
pinned; `uv sync --frozen --no-dev --no-editable`; non-root runtime, exec entrypoint.
Docker-specific allowlist context excludes credentials, fixtures and local state.

Entrypoint: `specimen-api --mode production`. `PORT` defaults 8080, binding
`0.0.0.0`; production `--port` must agree with PORT. One Uvicorn process,
concurrency 64, keepalive 5s, graceful request shutdown 8s and hard process watchdog 9s, access logging off,
forwarded headers untrusted. The watchdog handles Python thread/network teardown that can outlive ASGI
request cancellation; delivery should retain a platform termination deadline.
No provider secrets should be mounted in this API; known HF/OpenAI/Anthropic
variables and inference approval are rejected. ADC must be the API service
identity with narrow repository/object access, never Hosting identity.

| Variable | Required value/meaning |
| --- | --- |
| SPECIMEN_FIREBASE_PROJECT | specimen-digitization |
| SPECIMEN_FIREBASE_PROJECT_NUMBER | Numeric project number; all allowed app IDs must match |
| SPECIMEN_SQL_LOCATION | Explicit SQL region; data owner confirms |
| SPECIMEN_SQL_SERVICE | Explicit SQL service ID |
| SPECIMEN_SQL_CONNECTOR | Explicit server connector ID |
| SPECIMEN_GCS_BUCKET | specimen-digitization.firebasestorage.app |
| SPECIMEN_FIREBASE_APP_IDS | Comma-delimited registered allowed Firebase app IDs |
| SPECIMEN_CORS_ORIGINS | Comma-delimited exact HTTPS origins, no slash or wildcard |
| SPECIMEN_READINESS_OBJECT | Exact frozen authorized object name, private runtime config |
| SPECIMEN_READINESS_GENERATION | Exact positive frozen generation |
| PORT | TCP port; default 8080 |

Public health endpoints never return object names, identities, credentials or errors:

- GET `/health/live`: 200 `{"status":"live"}`; process event handling only.
- GET `/health/ready`: 200 ready or 503 not_ready, mode and scope
  `sql_query_and_object_metadata`. Cached 15s, serialized probes. Named SQL
  `Readiness` impersonateQuery with empty variables (data-owner additive query),
  then generation-pinned GCS object metadata. Three-second network timeouts,
  storage retries disabled. No bucket permissions/image reads or writes.
- GET `/version`: `source_sha`, `contract_version=api-runtime-v1`, `mode`.

Readiness does not prove migrations, authenticated membership, image bytes,
worker progress, inference or successful writes. Those are independent QA gates.
A credential-free container smoke may override the entrypoint to
`specimen-api --mode synthetic --state-dir /tmp/api-smoke --port <port>` with
`SPECIMEN_SYNTHETIC_TOKEN`. This is explicitly local fixture validation and
binds loopback; execute HTTP smoke inside that container. Default entrypoint
with missing production config must exit nonzero. No production bypass mode.

## Evidence and next actions

Confirmed: clean branch from baseline; full deployment rules read; existing
Firebase SDK revocation path audited; Docker engine available; Python locked
sync passed. Pinned base digests resolved from registry manifest metadata.
Commands/tests, exact candidate SHA, PR and all five CI URLs: pending below.
Data handshake accepted Readiness query + exact-generation metadata probe.
No shared pyproject/uv edits required; no cloud mutations or paid calls.

Not run: live Firebase valid/revoked/disabled/App Check/wrong-project tests,
production ADC/IAM/readiness, authorized 10 upload/review/restart journey.
Blocked: live resource decisions, private manifest/bootstrap and coordinator
release authorization. No merges requested or performed.

Rollback: retain prior immutable API image/revision and config packet; use only
later reviewed runtime delivery contract to restore it. This PR contains no
schema or data mutation and does not authorize manual deployment.

Official references consulted 2026-09-08:
[Firebase App Check](https://firebase.google.com/docs/app-check/custom-resource-backend),
[Firebase revoked sessions](https://firebase.google.com/docs/auth/admin/manage-sessions),
[Uvicorn settings](https://www.uvicorn.org/settings/).


## Reviewed auth and pilot corrections

Installed `firebase-admin==7.5.0`, `firebase_admin/app_check.py` lines 59-67,
sets its expected audience to `projects/` + `app.project_id`. Official App Check
contract uses the project number. Confirmed local compatibility correction:
Auth app `specimen-api` retains textual project ID, separate App Check app
`specimen-api-app-check` uses the explicit numeric project number. Exact App
Check issuer is checked too (the installed SDK only checks its prefix).
Real SDK RSA tests use ephemeral local signing keys and intercepted certificate,
JWKS and user-record transports: numeric App Check audience succeeds, textual or
wrong audience/issuer/app, expired or wrong-key token fails; textual Auth project
succeeds and numeric/wrong issuer/audience, expiry, disabled and revoked user
records fail. This does not constitute a Google-issued token or live IAM test.

Independent reviewer identified blocking readiness lock starvation and project
identifier mismatch. Both corrected with regression tests. Readiness now returns
not_ready during concurrent refresh; cheap liveness/version run asynchronously.

Evidence pilot is server-authored retained metadata, never a client flag. Key
presence `run.dependencies.evidence_pilot` blocks lifecycle/process/classification/
geometry/approval/defer operations even when malformed. Human corrections require
version `evidence-pilot-v1`, four 64-hex hashes (`launch_sha256`,
`source_manifest_sha256`, `profile_sha256`, `runtime_pins_sha256`), processing_blocked stage and no lease. The runtime-pins hash must match retained
dependencies excluding the marker; rules remain empty, risk policy blocked,
profile approval/semantics false, human approval false and no disposition.
Allowed reviewer actions: field, transcription, reading_metadata, coverage.
Corrections preserve marker, raw model observations, blocked risk and original
blocker, human_approved false, disposition null. Metadata declarations are retained
without risk recomputation. Geometry is view-only: the old endpoint starts a new
run and must not erase the pilot boundary. Generic nonpilot retry/resume/reprocess
also rejects external_outcome_unknown pending operator reconciliation.

Candidate identity names are `specimen-api-runtime@specimen-digitization.iam.gserviceaccount.com`
and service `specimen-api`, pending separate approved creation/binding; no cloud
existence or grant is claimed here.


## Local validation ledger (before candidate commit)

- `uv run pytest -q tests/test_api_runtime.py`: 39 passed, including real local
  SDK RSA signature/claim/revocation logic, CORS, single-flight readiness,
  subprocess HTTP and stuck-thread SIGTERM, pilot restart/correction denials and
  altered raw/source/crop bytes. No fixture key is persisted or accepted in runtime.
- First full backend run: 386 passed, 26 skipped (before later pilot/auth tests).
  Skips are opt-in emulator/live integration cases, not live validation passes.
- Canonical verify initial pass: all local gates passed. Staged pass identified
  dummy basic-auth URL scanner match; fixture changed to username-only URL without
  exemptions. Final candidate verify will be recorded with PR evidence below.
- Development container build completed, nonroot UID65532, read-only filesystem,
  no network, local synthetic health/ready/version and SIGTERM smoke passed.
  Missing production settings exited nonzero. That exploratory build used the
  baseline SHA build argument on modified source and is not a release artifact;
  rebuild from the committed candidate is required for exact provenance.
- Independent read-only review: identified and resolved numeric App Check project
  audience, readiness thread starvation, complete worker pin marker and draft
  pilot metadata integrity. Final focused review found no additional actionable
  findings. Normal active-profile clearance verification remains unchanged.

Session `runtime_blockers` now reports `worker_readiness_not_verified` and
`institutional_policy_unapproved` outside synthetic mode. The API does not
pretend to know another process's SAM3 configuration; per-run blocker remains
retained processing truth. Worker readiness and clearance approval are separate
acceptance evidence.


Integration note: GitHub main advanced externally to
`1d297db520a6e31021e7bfa5e5f81b77e90cf618` while this coherent candidate retained
base `a53f855e963b457c3ee2065f387609a193bb6f32`. Local evidence here is API-branch
coverage, not the final combined assembly; delivery owns integration revalidation.
Pilot review exposes original-image bytes only, suppresses view-derivative metadata
in the workspace and rejects direct view=true. Processing derivatives are ineligible
for pilot corrections, aligned with the worker's frozen-original admission gate.


Final canonical gate: `scripts/ci/verify.sh` exited 0 on the frozen implementation.
Evidence log: `/tmp/specimen-live-api-verify-frozen.log`. Backend 394 passed,
26 explicit opt-in skips; Flutter analysis/tests/release web build and all
repository/secret checks passed. No scanner, check or policy exception added.
The 39 API-specific tests include pilot original-only asset response/direct-view
denial as well as the prior signed-token, shutdown and correction contracts.


## Pull request and container handoff

PR: <https://github.com/anurag-duddu/specimen-digitization-app/pull/10>.
Required checks for the latest head:
<https://github.com/anurag-duddu/specimen-digitization-app/pull/10/checks>.
Initial implementation run:
<https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34261175704>.
All five required jobs started on the frozen implementation; latest-head final
results and exact run URL are recorded in the task/coordinator handoff rather
than claimed in advance here. Do not merge this owner PR independently.

Exact-implementation container build passed with SOURCE_SHA
`fedfaaeefc4646251f6a287c0a6deb76649dbb47` and local image config digest
`sha256:4392861467042821c244a1a986cdfec9d99910cef011f79000f9325219f05432`.
This is a local image, not a published registry digest or deployable release proof.
`/version` returned that exact source SHA and mode synthetic in the nonroot,
network-none/read-only/tmpfs container smoke; liveness/readiness 200 and SIGTERM
exit within the deadline. Default production startup without required settings
exits nonzero. Logs: `/tmp/specimen-live-api-container-frozen.log`,
`/tmp/specimen-live-api-container-smoke.log`,
`/tmp/specimen-live-api-container-denial-final.log`.

Remaining owners: data publishes named Readiness query and frozen generation;
delivery integrates against current main and binds service identity/image/config;
QA validates real issued Firebase/App Check tokens, authorized first ten objects,
worker/review/restart flow and deployed provenance after coordinator authorization.
No production deployment, merge, provider call, secret value, cloud specimen read,
IAM mutation, schema migration or local port3000/8000 change occurred here.
