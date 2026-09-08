# Flutter product implementation and verification

Worktree: `/Users/anuragduddu/.codex/worktrees/6b01/specimen-digitization-app`.
Branch: `codex/flutter-product`. Base: `82fd60e`.
Verified implementation HEAD: `31120e7d88ce053c465e890718d5fc21fc898322`.
Subsequent documentation-only handoff commit records this tested implementation.
Scope: `apps/specimen_digitization/**` and this report only. No deployment,
production merge, cloud provisioning, model call, or other worktree edits.
Read shared PLAN, repository AGENTS, DEPLOYMENT, and complete PRD before work;
read PLAN again before integration decisions. This is an implementation handoff,
not institutional pilot acceptance or production readiness.

## Implemented product

- Firebase email/password sign-in, reset and sign-out; scoped session membership
  and collection names loaded from the real API. Firebase bearer and App Check
  headers accompany API and image requests. No provider/admin credentials.
- Separate HTTP repository and session adapters from Flutter presentation.
  Requests reject non-local HTTP, do not forward credentials through redirects,
  retain mutation keys across uncertain outcomes, and surface conflict responses.
- Responsive queue/search/disposition and operational-state filters, periodic
  queue polling, explicit no-access/empty/network/configuration states.
  Review snapshots do not auto-refresh under an open correction dialog.
- File selection and Android/iOS camera intake, original bytes and SHA-256,
  local dimensions/size validation, manual framing/readability checklist,
  resumable 1 MiB chunk uploads with server-authoritative offset, duplicate
  handling and server completion verification. Saved local handles contain only
  scoped opaque upload IDs and checksums. Reselect original bytes after restart.
- Source image fetched with authentication into memory, pan/zoom/view rotation,
  original-pixel overlays and region crop navigation. Region editor adds,
  deletes, reorders, resizes and merges bounds; server creates successor versions.
- Independent literal readings, underlined character-position disagreements,
  adjudicated transcription separately displayed, mandatory field state and
  validation reasons, literal/parsed/resolved/authority layers, evidence and
  lookup details, immutable observation/raw-response references and audit events.
- Reasoned field/transcription/classification correction, coverage confirmation,
  human review approval and checkpoint retry. No client clearance assignment.
  Unknown field states can abstain; server applies every clearance gate.
- Explicit local synthetic login requires a compile flag, loopback API, manually
  entered in-memory fixture bearer, and matching server synthetic mode. A
  persistent synthetic banner distinguishes fixture processing from live work.
  Missing real configuration never activates synthetic processing.

## Exact API contract

Adopts architect v0.1 plus executable backend serializers in
`application/api.py`. Wire top-level names: `specimen_id`, `revision`,
`record_version_id`, singular `asset`, `run`, `regions`, `observations`,
`transcriptions`, keyed `fields`, `evidence`, `validations`, `decisions`, `events`.
The adapter maps these to presentation models without changing evidence values.
Geometry `bbox` uses exclusive upper original-pixel bounds; review writes convert
back to backend integer x/y/width/height. Lookup status remains backend spelling.

Upload transport: scoped authenticated `PUT /uploads/{id}/content`, raw bytes,
`Upload-Offset`, then GET offset/revision and POST complete `expected_revision`.
No Firebase Storage client writes. Review kinds map to `field`, `transcription`,
`coverage`, `approve`; field writes contain FieldValue `state`, `literal`, reason,
and evidence IDs. Existing revision and base record ID travel with each decision.

Exact backend-generated response fixture copied without alteration into
`test/fixtures/backend-wire-examples.json`. SHA-256:
`9cc65c46bf6c2bdeff42b6186b2949197b1cba8f8b6b2869823470ed04364616`.
Verified equal to backend owner's file at time of testing. Contains nine actual
HTTP journey objects. `api_repository_test.dart` consumes the session and
workspace response, not hand-invented aliases.

## Run locally

First run the backend owner's explicit synthetic server (the assembled branch
must contain its Python implementation):

```bash
# Set SPECIMEN_SYNTHETIC_TOKEN locally; do not commit it or use a provider key.
uv run specimen-api --mode synthetic --state-dir /tmp/specimen-local --port 8000
```

Then from `apps/specimen_digitization`:

```bash
# For credential-free local verification only, when the generated file is absent:
cp lib/firebase_options.ci.dart lib/firebase_options.dart
flutter run -d web-server --web-port 3000 \
  --dart-define=SPECIMEN_API_BASE_URL=http://127.0.0.1:8000 \
  --dart-define=SPECIMEN_LOCAL_SYNTHETIC=true
```

Open localhost:3000, use any test email and the local server fixture token in the
password field. Upload `test/fixtures/synthetic-label.png`, which is generated
and conspicuously marked synthetic. No museum data is included. CORS must allow
the local web origin. The source image and all displayed model outputs in this
mode are fixtures; no live inference is demonstrated.

Production builds require generated Firebase client config,
`SPECIMEN_API_BASE_URL=https://approved-api`, and on web
`SPECIMEN_RECAPTCHA_SITE_KEY=<public reCAPTCHA v3 site key>`.
The client uses ReCaptchaV3Provider, not Enterprise. Missing configuration shows
an actionable setup screen. Mobile uses Firebase App Check default Play Integrity
and DeviceCheck providers; registration/device attestation is an external gate.
An optional `SPECIMEN_AUTH_EMULATOR_HOST` points Firebase Auth at port 9099;
production backend rejects emulator identities. No debug attestation fallback.

## Verification evidence

- `flutter analyze --fatal-infos`: passed during implementation.
- `flutter test`: 16 offline tests passed; real-server test intentionally skipped
  unless `SPECIMEN_LIVE_TEST=true`. Covers sign-in/evidence/sign-out, explicit
  setup and synthetic states, 390px narrow layout at 200% text scale, semantic
  control labels, reasoned abstention, exact wire decoding, chunk offset resume,
  version/idempotency body, separate literal/normalized/authority writes,
  original-pixel region serialization, 409 non-retry and redirect refusal.
- `SPECIMEN_LIVE_TEST=true SPECIMEN_SYNTHETIC_TOKEN=... flutter test
  test/live_api_test.dart`: passed against actual local HTTP server. Initial
  prefix-upload/reconstruction journey reached stale-write test and exposed a
  backend keep-alive defect. Backend registered domain exception handlers; after
  restart the complete test passed, including reopen after 409. A fresh-state
  final run is recorded below when complete.
- Browser inspection at localhost:3000: real synthetic sign-in, queue, source
  bytes, overlay, status and review controls rendered. Accessibility enable
  control exposes semantic navigation and form controls. Additional final
  browser checks and canonical/native builds are recorded below.

## Acceptance boundaries and remaining gaps

This client does not certify PRD section 19 or WCAG conformance. Institutional
thresholds, approved representative data, production Firebase/Auth/App Check,
SQL runtime, SAM 3 serving, and model/provider policy are external acceptance
gates. Integration owner observed no established API endpoint or App Check
registration; this report does not convert that into proof of any deployment.

Current bounded limitations: original region rotation/polygon/mask editing and
raw provider-response body retrieval are not exposed (references are visible);
classification transfer depends on server profile mapping (currently only the
existing collection); required-field presentation follows the pilot contract's
20 fields. Folder/cloud URL intake and offline image-byte persistence are not
implemented. HEIC/RAW and TIFF require a locally decodable original plus approved
server decoder; unsupported decode is an explicit blocked intake, never a
fabricated preview. Camera capture uses system controls with manual quality
review; automated focus/glare/blur scoring and Android lost-camera-result
recovery remain device-validation work. All native camera/permissions/signing
and real Firebase identity/attestation remain unverified on museum devices.

Search currently covers all paged authorized summaries by ID, filename, batch,
profile and reason; date/uploader/risk advanced filters await backend projection.
Source preview bytes live only in memory and are discarded on sign-out; local
upload handles are not an offline specimen cache. Large-scale paging/performance
and screen-reader/device audits still require representative workloads.

## Official SDK references checked

- Firebase Flutter password authentication:
  https://firebase.google.com/docs/auth/flutter/password-auth
- Firebase App Check default providers:
  https://firebase.google.com/docs/app-check/flutter/default-providers
- Flutter-maintained file selector and camera plugins:
  https://pub.dev/packages/file_selector and https://pub.dev/packages/image_picker

Dependency lock uses the repository Flutter 3.38.5 / Dart 3.10.4 toolchain and
retains the existing firebase_core_web compatibility override.

## Final verification additions

- Browser file-chooser upload of a new synthetic PNG reached Accepted, then
  Needs human review after automatic server processing. Reasoned review approval
  yielded server Cleared at revision 18. A duplicate source was retained without
  a second record. No database edits or hidden repair were used for this journey.
- Android debug APK: passed using release owner's temporary
  `scripts/ci/build_mobile.sh android`, JDK bundled with Android Studio.
  Synthetic config files were generated and cleaned by that script. APK is
  debug-signed and not a distribution/device/camera acceptance artifact.
- iOS unsigned release: CocoaPods resolved the added plugins and updated
  Podfile.lock; Xcode build blocked because the iOS 26.5 platform component is
  not installed (`generic platform:iOS` destination unavailable). No platform
  download, signing, or device installation attempted.
- Temporary native verification script copy removed; no release-owned file
  is included in this commit.
- Fresh-state real HTTP run: passed on localhost:8001 with a new SQLite state
  directory, exercising prefix upload, repository reconstruction/resume, auto
  processing, authenticated source bytes, mandatory-field abstention, stale 409,
  and reconstruction of the resulting record and unchanged observations.
- `flutter build web --release`: passed (21.4 seconds); Wasm dry-run also passed.
  The built artifact is credential-free setup UI, not a live configured release.

## Independent QA corrections

- QA-F01: agreed backend typed transcription abstention; client now sends
  both `after.text` and `after.state`, preserving unknown/unreadable/unresolved
  instead of silently dropping state. Unsupported not-applicable transcription
  option is excluded. Wire regression included; live HTTP regression follows.
- QA-F02: unknown future field states remain visible as unsupported, with
  unsafe correction disabled before dropdown construction. Widget regression.
- QA-F03: reviewer controls require server session reviewer scope and specific
  `available_actions` keys; run retry requires operator scope plus `retry`.
  Backend remains authoritative. Viewer and operator/action-list widget regressions included.
- Scanner dependency: release-owned commit `30d6f99` was cherry-picked as
  `4b135dc` before the scoped Flutter commit. It audits only exact confirmed
  digest findings; both scanners and their detection rules remain enabled.

- Canonical `scripts/ci/verify.sh`: passed after the audited scanner dependency,
  including both scanners, repository hooks, 33 baseline Python tests, Flutter
  analysis/tests and release web build. Final rerun includes all QA regressions.
  Backend application tests live in the backend owner branch and must also run
  after integration; this worktree's Python baseline is not integrated proof.
- Final canonical run passed with all 16 offline tests (one explicit live-server
  test skipped by default), 33 baseline Python tests, scanners, analysis and web
  release build. Fresh actual HTTP run separately passed typed unreadable
  transcription through automatic revalidation to Needs human review, with
  independent observations unchanged and stale writes rejected.
- Final Android debug rebuild after QA corrections passed in 7.4 seconds.
  Generated synthetic Firebase files and temporary native script were removed.
- Local demonstration services remain available for independent QA at web port
  3000 and API port 8000 using explicit synthetic configuration. They are local
  temporary processes, not a deployment, scheduled monitor or production service.
