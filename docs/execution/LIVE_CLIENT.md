# Live client workstream

This report preserves the earlier password-based implementation. Current web
sign-in uses [staff email links](../MAGIC_LINK_SIGN_IN.md); collection roles
remain server-authorized.

## Objective and ownership

Connect the web login/upload/review path to verified Firebase identity and server
collection roles. Preserve native compilation and isolated local synthetic mode.
Owner task: `01a08219-3044-7c91-9907-5c3bc7d95548`.
Scope: `apps/specimen_digitization/` and this report only.
Branch: `codex/live-client-auth-repair` (preserved from `codex/live-client`).
Worktree: `/Users/anuragduddu/.codex/worktrees/ac08/specimen-digitization-app`.
Baseline: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Implementation SHA: `ac6053b078bad85c2098e683973a074a78eccc52`.
PR: [5](https://github.com/anurag-duddu/specimen-digitization-app/pull/5).
Initial CI run: [34259362976](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34259362976).
This follow-up also clarifies the confirmed evidence-only pilot blocker. The
[PR checks](https://github.com/anurag-duddu/specimen-digitization-app/pull/5/checks)
are authoritative for the current head, including this report revision; do not
substitute checks from the initial implementation run for the final head.

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
PR 5 was open and unmerged at this checkpoint. Remote verification was queued when this report was
committed; the owner continues watching Repository checks, Python tests, Flutter
checks and web build, Flutter android build, and Flutter ios build on the exact
latest PR head. Final SHA/job outcomes will be sent to the coordinator; the
current head/run links remain available through PR checks above.
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


## Evidence-only pilot coordination

Coordinator described a separately gated first-ten evidence-only pilot with real
SAM and two blind readings retained, `processing_blocked`,
`pilot_evidence_review_required`, no disposition and blocked/unmeasured risk.
Processing owner confirmed the exact run blocker and evidence-pilot-v1 dependency
marker. The operational panel explains this blocker as evidence review needed,
unmeasured risk and blocked clearance; no new state is introduced. API owner confirmed pilot `available_actions`: field, transcription,
reading_metadata, coverage for authorized reviewers/managers/admins. Geometry,
classification, approval, defer and lifecycle actions are denied because geometry
currently starts new inference. Original blocker and null disposition persist
after retained-evidence corrections. Regions remain viewable, not editable. Existing workbench gates edits on server
`available_actions` and renders blocked/unmeasured risk without a numeric
composite. This pilot is not a completed or cleared production pipeline.

API owner is separately validating Firebase App Check numeric project audience;
client token issuer/provider configuration is unchanged. Live attestation remains
an acceptance gate, not inferred from successful token transport fixtures.

## Frozen follow-up verification

The second canonical gate passed: 355 Python passed/26 skipped; Flutter 83
passed/7 skipped; clean analysis; release web build succeeded in 25.6 seconds.
Log: `/tmp/live-client-final-verify.log`. After the coordinator requested an
explicit no-geometry/no-clearance case, the pilot widget tests passed 2/2,
including actual workbench disabled controls with permitted coverage review.
Log: `/tmp/live-client-pilot.log`. This supplementary test initially needed the
credential-free CI options file after canonical cleanup, then a button-subclass
finder correction; no product permission was changed to make it pass.
Retained raw model observations are untouched by this PR. Permitted human edits
cannot authorize model replay or unblock finalization. Final exact head/all-five
remote results are recorded in the PR body and coordinator handoff to avoid a
self-referential sequence of report-only commits.


## Corrective authorization boundary after PR 5 merge

Confirmed by coordinator and fetched origin/main: PR 5 was merged by the user at
2026-09-08T17:58:22Z as `1d297db520a6e31021e7bfa5e5f81b77e90cf618`, while
independent QA's P2 repair was in progress. The prior freeze is superseded.
Work was preserved on `codex/live-client-auth-repair`; the corrective PR targets
current main. No agent merge, reset or hand deployment occurred.

QA found that an authorized record followed by denied source-image access could
return editable data; child evidence/history/intake catches also hid denials from
the workspace. Repair introduces a repository access-denial signal and latch:
401/403 or failed App Check invalidates workspace regardless of child handling;
subsequent protected calls are suppressed. Intake stops its remaining file loop.
Image non-auth failures retain a local preview error and remain retryable.

Requests bind to access epoch and Firebase UID. Late responses from an older
verification or user neither restore access nor deny a new verified session.
A recheck does not clear the latch early: only a complete same-user/mode/session
and collection request sequence unlocks it; failed or partial checks stay locked.
Workspace generations also discard late initialization/mutation responses.
Already transmitted requests cannot be recalled; their stale responses are
rejected and no automatic mutation retry is introduced.

Confirmed local repair tests: 30 passed across protected_access_http_test,
access_generation_http_test, access_recovery_test and intake_recovery_test;
analysis clean. Actual HTTP tests cover record200 then image401/403/AppCheck
failure, historical/raw/complete-graph/history/intake denials despite local
catches, no following protected request, successful explicit recovery,
failed/partial/in-progress rechecks, late200/403 and changed Firebase UID.
Widget tests verify parent invalidation from child denial and no second upload
attempt after the first denied file. Logs: `/tmp/live-client-repair-tests.log`,
`/tmp/live-client-auth-analyze.log`. Canonical corrective gate and independent QA
are required before acceptance; final exact SHA/PR/CI goes to the coordinator and
PR body after the new head is frozen. Actual live Firebase/browser/ten-specimen
acceptance remains unperformed by this client task.


Repair validation expanded to broken-connection versus HTTP503 image recovery,
first-chunk upload denial after a successful offset read, and collection200
responses missing the assigned collection. The full Flutter suite and analysis
passed before the final canonical rerun. Earlier canonical runs caught the old
graph post-denial reuse expectation and then a test-matrix variable scoping error;
both were corrected in tests without weakening authorization or scanners.
Artifacts: `/tmp/live-client-repair-flutter.log`,
`/tmp/live-client-repair-analyze.log`, `/tmp/live-client-auth-repair-canonical.log`.

Independent follow-up QA found a composed fallback race: an old preview transport
failure, or summary fallback after an artifact receipt, could return an old
record after a successful newer access recheck. The corrective batch now checks
context after preview fallback and before summary/committed-receipt success;
summary 401/403/access_changed is rethrown. Historical receipt and retry/review
follow-ups retain their original context. New composite_access_http_test holds
preview and summary HTTP requests, rechecks access, then disconnects or denies
the old request and asserts the complete specimen future rejects without
invalidating the new session. Direct summary401/403 cannot become a receipt.
The existing committed-receipt recovery test uses non-auth503 so harmless
summary unavailability is still verified independently of authorization failure.
Full Flutter result after this fix: 120 passed, 7 skipped; analysis clean.
Logs: `/tmp/live-client-composite-flutter.log`,
`/tmp/live-client-composite-analyze.log`,
`/tmp/live-client-corrective-canonical.log` (final required rerun).
