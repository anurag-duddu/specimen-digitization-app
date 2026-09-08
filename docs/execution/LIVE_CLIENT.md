# Live client workstream

## Objective and ownership

Connect the web login/upload/review path to verified Firebase identity and server
collection roles. Preserve native compilation and isolated local synthetic mode.
Owner task: `01a08219-3044-7c91-9907-5c3bc7d95548`.
Scope: `apps/specimen_digitization/` and this report only.
Branch: `codex/live-client`.
Worktree: `/Users/anuragduddu/.codex/worktrees/ac08/specimen-digitization-app`.
Baseline: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Candidate SHA/PR/CI: pending initial verification and commit below.

## Decisions and contracts

Confirmed: live builds consume `SPECIMEN_API_BASE_URL` (HTTPS origin/base path,
no credentials, query or fragment) and `SPECIMEN_RECAPTCHA_SITE_KEY` (public
reCAPTCHA v3 site key). Existing generated Firebase options remain ignored and
restored through the approved delivery workflow only. Neither setting supplies
an administrative credential. Delivery owner confirmed both names; no new
Hosting identity, secret or permission was requested.

Missing API or web App Check configuration presents a connection-required screen.
Credential-free CI builds retain their explicit placeholder setup screen. Live
builds reject authentication emulator routing. `SPECIMEN_LOCAL_SYNTHETIC=true`
remains restricted to local API hosts with entered fixture tokens and a visible
synthetic banner. No production failure falls back to fixtures.

Confirmed API contract: every protected JSON, upload, artifact and source-image
request uses `Authorization: Bearer` and `X-Firebase-AppCheck`; missing/failed
credentials abort locally. `/v1/session` must return `mode=production`, nonempty
`user_id` matching the current Firebase UID, and a list of memberships with
nonempty organization/collection/role fields. Malformed or duplicate scopes are
rejected, rather than silently treated as no access. The API remains authoritative
for permissions on every request. Client state is cleared after 401/403.

Confirmed with API owner: email_verified must be true in verified claims;
unverified identity returns 403 `email_verification_required`. Client email
verification gate prevents mounting the workspace until email verification and
forced token refresh complete. Sending a verification email requires a user click.
Account creation and role assignment remain administrator operations outside the
client. The approved initial identity remains private and is not committed here.

Account onboarding explains how to obtain an account and collection role.
Password-reset feedback is distinct from sign-in and preserves non-enumerating
success text. API-denied or unavailable collection access is not described as a
successful role assignment. Retry rechecks server membership.

SDK decisions checked against official Firebase documentation:
[Flutter App Check providers](https://firebase.google.com/docs/app-check/flutter/default-providers)
and [password authentication](https://firebase.google.com/docs/auth/flutter/password-auth).
The existing dependencies/providers were retained; no dependency upgrade.

## Verification and evidence

Confirmed: `flutter analyze --fatal-infos` passes; full `flutter test` passes after
initial implementation. `/tmp/live-client-flutter.log` contains that run.
New live_connection_http_test binds an ephemeral loopback HTTP server: checks
headers, UID mismatch, malformed membership, environment mismatch, missing or
throwing App Check providers, and configuration isolation. These are actual HTTP
transport tests using synthetic tokens, not real Firebase attestation.
New email_verification_test verifies no workspace before verification/refresh and
no automatic verification email. access_recovery_test exercises revocation and
membership retry through the widget.

Initial targeted run failed because a command used the repository-relative path
from the Flutter directory; corrected without changing environment. A subsequent
run caught the intentionally changed no-role copy in synthetic_auth_test; its
expectation was updated. Those failures are not counted as successful runs.

Confirmed: `scripts/ci/verify.sh` passed (exit 0). Python: 355 passed,
26 skipped, 7 warnings in 120.26 seconds. Flutter: 82 passed, 7 skipped; analysis
clean; release web build succeeded in 23 seconds. Skipped live/emulator tests are
not live acceptance evidence. Canonical log: `/tmp/live-client-verify.log`.
New files were staged and repository hooks rerun successfully after fixing a
scanner-detected synthetic basic-auth URL by using a username-only userinfo test;
no scanner rules or allowlists changed. Hook log: `/tmp/live-client-hooks.log`.
PR and all five remote platform jobs: pending.
No persistent fixture port reserved; HTTP tests bind ephemeral loopback ports.
Existing ports 3000/8000 were not changed or restarted.

## Gaps and release gates

Not run: authenticated production browser flow, actual cloud upload, retained
review persistence, real Firebase/App Check attestation, physical mobile devices.
Coordinator must provide the approved combined target and access. Data owner must
freeze the exact first 10 existing cloud specimen objects with immutable metadata
before sample use. No specimen bytes were downloaded or inferred in this task.
Budget authorization, production runtime/data rollout and approved build values
remain separate launch gates. No paid calls or cloud mutations performed.

## Recovery and next action

Before merge, withdraw or revise this scoped PR; no production state changed.
After authorized release, roll back through a reviewed revert PR and the normal
main CI/Hosting workflow. Never hand-deploy. User access recovery uses explicit
verification, sign-out/sign-in and server role recheck; no cached-role fallback.
Client owner next runs canonical local verification, opens PR, watches all five
checks, and reports exact commit/run links. Coordinator owns integrated browser
acceptance and any later merge authorization.

## Pending frontend design backlog

Separate real-model diagnostic feedback, relayed by the integration owner: on one
SAM SVG, detections 2/3 appeared plausible; 1/4 were uncertain or overly granular.
These are observations, not validated ground truth or confirmed defects; the
single image remains separate from the authorized frozen ten.

Pending UX review: transient hover preview, persistent click/tap region selection
linked to model-level readings for that label, and explicit enlarged whole-image
or region view with pan/zoom, touch pinch and keyboard/button equivalents. Evidence
must remain accessible without hover and return state must be predictable.
Existing zoom and selected-region reading linkage need design review. This is
captured only; it is outside this connection PR and is not final UX approval.
