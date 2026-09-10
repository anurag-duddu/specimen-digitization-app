# Flutter product implementation and verification

This report preserves the original implementation. Current production web
authentication uses [staff email links](../MAGIC_LINK_SIGN_IN.md).

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

## B04 retained history repair (2026-09-08)

- Isolated branch `codex/flutter-audit-history` starts at integration commit
  `76da6606542201265101193ca831731efd52b319`. Requires backend B04
  `4bea6c9`; no backend, SQL schema, deployment or next-wave changes included.
- Added scoped, authenticated, read-only immutable revision browser, available
  whether or not audit compaction has occurred. Pages contain at most ten
  records and remain pinned to the current review revision. Missing records,
  malformed digests, repeated cursors and changed bounds are rejected.
- Compaction marker and global audit sequence offsets are visible. Legacy inline
  audit evidence stays readable. Prior-run references construct scoped API paths
  and forward run ID/digest verification; supplied URLs are never followed.
  Retry preserves the reference. Full retained workspace, source metadata, run,
  readings, fields, validation and audit evidence are expandable/selectable.
- Historical reads use current bearer/App Check authentication, suppress actions,
  and never fetch source bytes implicitly or replace the active CAS model.
  Scope/specimen/revision keys dispose prior history, including pending reads.
- Seven new offline tests cover paging bounds/gaps, authenticated requests,
  identity/access/digest failures, legacy evidence, read-only/current CAS,
  digest-preserving retry and late-response isolation. Existing wire fixture
  bytes remain unchanged (SHA-256
  `9cc65c46bf6c2bdeff42b6186b2949197b1cba8f8b6b2869823470ed04364616`).
- Actual TCP/SQL emulator verification used backend `4bea6c9` on an owned
  API port 8012/state directory and leased SQL port 9579. An independently
  unique synthetic upload completed 250 ordinary approve actions alternating
  missing/restored raw evidence via the backend's test helper. At revision 267,
  history was compacted through 177 with audit offset 173. The Flutter HTTP
  repository read all 267 revisions across bounded pages, loaded revision 1 and
  a digest-verified prior run, rejected a wrong digest, then successfully wrote
  using the unchanged current revision (268) and rejected stale reuse. A pinned
  history page remained bounded at 267 after that new write. Opt-in regression:
  `test/live_history_test.dart`; no persisted fixtures or credentials added.
- Canonical `scripts/ci/verify.sh` passed: scanners/hooks, 77 Python tests
  (two opt-in SQL tests skipped), Flutter analysis, 23 offline Flutter tests
  (two opt-in live tests skipped) and release web build. Actual live-history
  test separately passed against the newer B04 backend as described above.

## QA-F04 source geometry and confirmed reading semantics (2026-09-08)

- Separate follow-up to B04 commit `4d00421`. A centered loose layout now lets
  the source aspect ratio fit inside the 380-pixel viewer at every rotation.
  The original stays whole; region overlays use the same original-pixel
  coordinate transform. Existing explicit region-crop selection remains.
- Two geometry regressions use a generated 1000 x 520 synthetic PNG with a
  circular fiducial, corner text and an interior box. At 390 x 844 and
  1440 x 1000, every quarter turn asserts source aspect ratio, full containment
  within the viewer, overlay extent and original-coordinate origin alignment.
- Confirmed QA's independent-reading accessibility observation in Chrome:
  before repair, both independent observation groups exposed an empty disabled
  textbox while visible literal text existed. Replaced `SelectableText.rich`
  with `SelectionArea(Text.rich)`; selectable text and character differences
  remain. Widget semantics now include each complete distinct reading. The
  post-repair browser accessibility snapshot contains complete literals under
  both independent model groups.
- Actual Chrome inspection at 390 x 844 and 1440 x 1000 confirmed undistorted
  full source images, with a narrow 90-degree rotation check. Narrow original
  source bounds were 310 x 161.2 CSS pixels (1000:520 ratio); letterboxing is
  intentional. Temporary evidence: `/tmp/flutter-f04-evidence/narrow-0.png`,
  `narrow-90.png`, `wide-0.png`, and `readings-ax.txt`. These are local artifacts,
  not committed release evidence. QA will independently capture its candidate.
- Browser also fetched the bounded history index and opened historical revision
  1 read only while current review stayed at 17 (`history-ax.txt`). The fixture
  was accepted through authenticated local HTTP because Chrome extension file
  URL permission blocked file-chooser injection; no browser setting changed.
- Canonical `scripts/ci/verify.sh` passed with scanners/hooks, 77 Python tests
  (two opt-in SQL skips), Flutter analysis, 26 offline Flutter tests (two
  opt-in live skips) and release web build. The three new focused geometry and
  semantics tests also passed separately. No native behavior/platform changes;
  prior iOS platform-component limitation remains.
- Owned web port 3000 and API 8012 stopped; browser viewport overrides reset and
  own test tab closed. SQL emulator lease returned to backend. No deployment.
