# Remaining P0 Flutter workflows

Status: implementation in progress, 2026-09-08. Branch
`codex/flutter-workflow-completion` starts at exact first-repair integration
`290a2a7`; `codex/flutter-audit-history` remains intact. Own
`apps/specimen_digitization/**` and this report. Read the full PRD v0.6,
NEXT_WAVE, repository AGENTS/DEPLOYMENT and shared coordination PLAN.

## Scope and sequencing

1. Add measured pre-submission image feedback with explicit limits, camera
   interruption recovery, server quality and classification/profile review.
2. Complete region geometry/coverage interactions while keeping original pixels
   immutable and accounting for source orientation/region rotation.
3. Expose typed candidate alternatives, authority identity/evidence, phase
   applicability, raw response details, disagreements and review-risk components.
4. Add operational budget/retry/outcome-unknown recovery explanation/actions and
   server-paged queue search across agreed filter dimensions.

Backend reliability owner is the single API composition point. Additive fields
and review actions must come from its executable fixture before wiring; no
invented endpoints, arbitrary raw-blob reads or disabled placeholder features.
History retains the first-repair fixed revision boundary and digest verification.
Current access and current CAS snapshots remain authoritative for every edit.

## Acceptance evidence

Pending implementation. Each workflow requires meaningful widget/wire tests,
actual local HTTP execution and rendered-browser verification. Canonical verify
and integrated independent QA remain required; module mocks are not full product
acceptance. No paid inference, cloud configuration, provisioning or deployment.

## External limitations

Institutional profile/field/authority policy and expert quality calibration are
unapproved. No device acceptance or production readiness is inferred. Existing
local iOS build limitation is the missing iOS platform component; canonical CI
native builds are independent evidence. Exact new API contracts and runnable
fixture paths have been requested from the backend owner.

## Implemented checkpoint

- Local pre-submission preview samples at most 256 pixels per axis for descriptive
  brightness/contrast/detail statistics. These are uncalibrated, never an
  automatic quality pass. Full originals remain unchanged. Files above the
  existing byte/pixel limits receive an explicit rejection. Choosing another
  image revokes manual quality confirmation. Android interrupted-camera recovery
  is scoped to the initiating user and collection and never uploads automatically.
- Explicit server-preflight action transmits the selected original only on click,
  verifies returned contract/digest/size, distinguishes review/blocked/rejected,
  exposes codec capabilities and unmeasured criteria. Memory-enforcement failure
  gives a runtime-specific remedy; it does not suggest changing PNG resolves it.
- Server quality diagnostics, classification candidates/provenance, pinned profile
  dependencies and publication/policy state are visible. Classification selection
  uses returned logical nodes, preserves the authorized storage collection UUID,
  requires a reason and starts a new run with historical evidence retained.
- Region correction exposes original-coordinate bounds, add/remove/order/merge,
  coverage controls and clockwise quarter-turn crop rotation. A digest-verified
  pixel-only server derivative is inversely transformed into the original pixel
  plane before overlays/crops, separating EXIF orientation from saved ROI rotation.
  Legacy sources without verified derivative provenance explicitly restrict
  geometry correction/overlays instead of assuming a client decoder orientation.
- Phase proposals/findings, review-risk components and unmeasured signals,
  qualified authority alternatives/context, language/script declarations and exact
  Unicode comparison spans are accessible. Each artifact read pins the selected
  specimen revision and reauthenticates; field_key disambiguates authority tools.
  Raw responses are displayed as text only after a matching digest and a 1 MiB
  response bound. Oversize, unavailable and tampered responses never display a
  partial body as complete. Character highlighting is limited to short readings;
  longer retained text uses one text node and the bounded server alignment.
- Authority selection sends the exact retained identifier/tool/field with current
  CAS and a required reason. Literal evidence is preserved. Final approval is a
  separate action. Leases, retry/dead-letter/outcome-unknown explanations, actual
  and reserved usage/cost and explicit run actions are visible; an active lease
  disables retry/resume/reprocess. Missing measurements never display as zero.
- Queue retrieval uses one bounded page and explicit Load more. Named filters
  include specimen/asset/run/batch/uploader, state/disposition/stage, profile,
  issue/blocker, UTC date bounds and risk bounds. No local postfilter discards
  server matches. Cursors reset on filter/scope changes; late responses from a
  prior filter are discarded. Cursor faults require explicit refresh.

## Concrete verification

- Frozen additive fixture copied byte-for-byte from backend composition:
  `test/fixtures/backend-next-wire-examples.json`, SHA-256
  `6d1bf6bf4eab1b47defdafcc8c99c10dd51dc15dc28f46a18c65782b3dfbb07f`.
  First-wave fixture is unchanged. Scanner dependency `bbf536a` was cherry-picked
  as `c50a68a`; integration already owns that dependency and must not duplicate it.
- Tests cover same-owner camera recovery/no automatic upload, quality bounds,
  required classification reason/storage scope separation, original ROI bounds,
  all four saved ROI rotations, all eight EXIF inverse-affine mappings, retained
  multilingual/astral/CRLF UTF-16 span semantics and policy-blocked comparisons,
  exact qualified candidate decisions, active leases, bounded raw evidence,
  current revision/CAS wiring, explicit queue paging and stale filter isolation.
- Real local HTTP fixture ran against isolated immutable backend
  `026d0b9e4f00cf24ab34f2fd151b6802adfceb6d` in
  `/tmp/specimen-flutter-backend-026d0b9`, SQLite plus actual local TCP mock Parties.
  No paid or institutional service calls. API port 8014, web 3000 leased from QA.
  `test/live_next_workflow_test.dart` passed: upload, default blocked preflight,
  metadata-free derivative, typed phase/authority/raw/reading evidence, exact
  candidate selection preserving literal, separate approval, stale-CAS rejection,
  pinned prior artifact retrieval and named search. Retained synthetic specimen
  `64a4f4fb-9bc4-5136-be18-cdcc294672f3`: initial revision 24, selected 25, cleared 26.
- Actual Chrome keyboard-accessible workflow then confirmed classification into
  a new run (revision 50), selected qualified local Parties identity (51) and
  separately approved (52, Cleared). Earlier run remains in immutable history.
  Local screenshot/AX artifacts: `/tmp/flutter-p0-evidence/wide-review.png` and
  `/tmp/flutter-p0-evidence/review-ax.txt`. Narrow check/final gates recorded below.

## Still open, not acceptance claims

- Actual approved HEIC intake/worker and declared RAW families await backend codec
  composition. Preflight is not their end-to-end acceptance. This checkpoint still
  requires locally decodable dimensions for normal createIntake; the future codec
  contract must replace that constraint with verified server dimensions.
- Backend active-graph large-evidence handling, storage streaming bounds,
  language/script provider propagation, workflow deadline/circuit refinements are
  later checkpoints. Existing unknown/unmeasured/typed failure states remain honest.
- Browser file-chooser extension permission was unavailable in the earlier repair;
  no browser setting was changed. This wave uses actual Flutter repository upload
  over HTTP plus injected picker/recovery widget tests; camera device acceptance
  and real HEIC-device capture are not inferred.
- Independent integration/QA of an immutable combined candidate remains required.
  No production deployment, cloud configuration, real quality calibration or
  museum policy approval is part of this checkpoint.

Final checkpoint gates: `scripts/ci/verify.sh` passed (81 Python tests, 3 optional
skips; 47 Flutter tests, 3 separately gated live tests skipped; fatal-info analysis,
secret scanners, web release build and Wasm dry run). Log:
`/tmp/flutter-p0-final-canonical.log`. The separate immutable-backend real HTTP
workflow passed in `/tmp/flutter-live-next-pinned.log`.

Chrome 390 × 844 inspection confirmed source containment/aspect ratio, responsive
navigation and scrollable region correction with retained original coordinates.
Additional screenshot `/tmp/flutter-p0-evidence/narrow-review.png`. A browser
region edit selected clockwise 90 degrees with a required reason and saved through
the real API, preserving original bounds. These are local synthetic checks;
independent QA and device/codec acceptance remain open.

### Viewer state and explicit-consent follow-up

A new active run or removed region now clears an obsolete crop selection and
resets view rotation/zoom, restoring the current overlays. Added regressions for
this transition and explicit preflight transmission: file selection sends nothing,
preflight creates no intake, and manual quality confirmation remains unchecked.
A display projection generated by `align_readings` from immutable backend
`026d0b9` covers combining Latin, emoji, CRLF, Japanese and Arabic in one reading:
codepoint 25 / UTF-8 byte 43 / UTF-16 unit 26 points to the retained Arabic numeral.
The UI rejects a reported span that does not match its retained source text.
Fatal-info analysis and all 50 Flutter tests passed (3 gated live tests skipped).
This follow-up does not change the frozen fixtures or claim HEIC intake acceptance.

### Verified server-codec intake follow-up

This supersedes the earlier local-decoder dimension gate. Paired width/height
claims are optional under the frozen codec contract; partial pairs are rejected.
HEIC/HEIF and approved DNG uploads omit both claims even if a local preview can be
decoded, because the server establishes the HEIF primary-image or RAW active-area
coordinate basis. JPEG/PNG/TIFF retain available paired local dimension claims
for server verification. No fabricated dimensions or preflight quality pass is
used. Upload completion redecodes the hash-verified original on the server.

The viewer and region editor disclose the recorded pixel basis, decoder version,
conversion and original-file retention. HEIF coordinates refer to the primary
image after container orientation; encoded-grid mapping is explicitly unavailable.
Decoded-preview quality measurements are distinguished from the codec itself.
An `image_codec_*` completion block retains the upload handle and gives a codec,
profile/runtime configuration remedy. It never marks the upload Accepted.

Frozen codec fixture:
`test/fixtures/backend-codec-wire-examples.json`, SHA-256
`8dc736071fc530260097279cee0a09fab35a7c67420ef2b3dcf7271fee673e7d`.
Generated synthetic HEIC and its exact retained PNG derivative are committed as
`synthetic-orientation6.heic` and `synthetic-heic-derived.png`. They contain no
museum record data. Scanner dependency `5868705` was cherry-picked as `cd745f0`;
integration already owns this dependency and must not duplicate it.

Actual Flutter HTTP proof used immutable backend
`d6be7a083d3198ebd7e9e1b52170828dfd300c13`, owned by backend at port 8016,
with explicit synthetic codec/profile enablement and the documented local-test
memory-enforcement exception. This is not production runtime approval. Source
`874a1af9-ed96-51d1-8f88-0b1eea373cfa` uploaded without client dimensions,
completed to Review at revision 20, established 64 × 96
`decoded_heif_primary_pixel_edges`, returned original bytes byte-for-byte, and
returned a digest-verified PNG preview. A fresh authenticated repository reopened
identical retained source metadata and pixels. Saving clockwise quarter-turn 1
kept the original-basis rectangle and source hash unchanged; later processing
settled at revision 36. The browser exposed the recorded basis/conversion and
performed a separate review approval, reaching revision 37 Cleared.

`test/live_codec_test.dart` passed against that actual HTTP service. New tests
cover omitted/partial dimension claims, source/derivative digest mismatch,
coordinate disclosure and blocked-codec upload retention. All 54 Flutter tests
passed (4 gated live tests skipped in the ordinary suite). This proves the local
HEIC path under the explicit test policy. Arbitrary RAW/device support, production
codec approval, camera-device acceptance and independent combined QA remain open.

Codec checkpoint canonical verification passed: 81 Python tests (3 optional skips),
54 Flutter tests (4 gated live skips), fatal-info analysis, both secret scanners,
web release build and Wasm dry run. Log `/tmp/flutter-codec-gates.log`; real HEIC
HTTP log `/tmp/flutter-codec-live.log`. Final browser artifacts:
`/tmp/flutter-codec-evidence/heic-review.png` and `heic-review-ax.txt` (Cleared
revision 37, explicit decoded-source accessible label and coordinate limitations).
The local web 3002 lease is released after verification; API 8016 remains owned
by backend and is released by notification, not by killing another task's process.
