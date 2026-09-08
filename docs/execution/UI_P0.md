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

### Large-record recovery and committed-mutation receipts

The frozen additive `backend-graph-wire-examples.json` was copied unchanged
(SHA-256 `8e9238d5582fabc4eea8265740a6bb19df58e548c7eb834644199d9c8b779715`).
Scanner dependency `d77038b` is carried as `3f6fee4`; integration already owns it.
No multi-megabyte payload is committed as a fixture.

A typed `workspace_artifact_required` response retains its revision and record
version. The UI loads an independently authenticated, matching current summary
and switches to an explicit read-only complete-evidence view. Summary failure or
revision drift disables actions and requests a refresh. A mutation receipt with
`mutation_committed=true` returns the saved revision and a visible saved notice;
the workspace removes its pending mutation key instead of presenting the action
as failed or automatically repeating it. Field edits and approval are intentionally
unavailable in this fallback. Authorized current run controls and retained history
remain reachable. This is bounded recovery, not unlimited graph support or a
replacement for the ordinary field-review workspace.

Artifact URLs from responses are never followed. Retrieval constructs the scoped
specimen endpoint, pins revision, reauthenticates, caps the complete stream at
16 MiB and checks retained SHA-256, size, response digest/revision headers,
contract, organization, collection, specimen and run identity before display.
The complete verified graph is navigable by section and 12,000 UTF-16-unit text
pages, with surrogate-safe boundaries. A fixed-height selectable text area keeps
controls nearby and exposes each complete page to accessibility tools. No partial
or tampered payload is represented as complete. Historical artifact views retain
the requested revision and grant no current mutation actions.

Actual Flutter HTTP proof: immutable backend `e18570f`, fresh synthetic SQLite
state `/tmp/specimen-flutter-graph-state-e18570f`, loopback API 8018. The generated
multi-label record has a 2 MiB observation and a 2,605,715-byte complete artifact;
its projected workspace exceeds 4 MiB. Specimen
`748c44fa-b2f2-5c32-80cd-2cdb5269aa45`: GET fallback at revision 57, coverage
mutation committed via 413 at 58, explicit cancel at 59. The stale revision was
rejected, complete historical graph 57 remained identical, and no mutation was
replayed. Log `/tmp/flutter-graph-live.log`; gated reproducible client test
`test/live_graph_test.dart` requires an explicitly seeded large synthetic record.

Browser testing discovered that cross-origin reads need the verification headers
exposed. Backend owner supplied original `7dc87cc` (exact two exposed headers,
allowed origins unchanged), carried only in the detached backend test checkout
as `99509385764ee4f0c5829d6f98a78c9b32e24c4e`. After restarting the same persisted
state through canonical `create_app(origins=...)`, Chrome verified and opened the
complete graph using those headers. The initial test-only CORS wrapper was no
longer used. Integration must include the backend CORS dependency with this UI.
No deployed environment or institutional data was involved.

Four focused wire/widget tests cover exact captured receipts, summary access
failure after commit, authenticated constructed paths, digest/header/size/stream
bounds, historical pinning, explicit lazy retrieval, no approval action, bounded
text pages and complete page accessibility. Final canonical verification and
browser artifact paths are recorded below. Independent combined QA remains open;
TRN-006 human declaration mutations await their separate frozen HTTP fixture.

Final graph gates passed: 81 Python tests (3 optional skips), 58 Flutter tests
(5 separately gated live tests skipped), fatal-info analysis, both secret scanners,
web release build and Wasm dry run. Log `/tmp/flutter-graph-final-gates.log`.
The separate actual HTTP graph test passed in `/tmp/flutter-graph-live.log`.
Final Chrome evidence `/tmp/flutter-graph-evidence/graph-page.png` and
`graph-page-ax.txt` shows page 2 of 192, its complete 12,000-character text in AX,
and nearby run controls. `history-ax.txt` records reachable history pagination.
HTTP tests separately verify complete historical artifact retrieval and stale CAS.
No browser viewport override or QA-owned port was changed. Both temporary graph
API 8018 and Flutter web 3002 were stopped after verification; persisted synthetic
state and immutable backend checkout remain available for independent reproduction.

### Actual reading declarations and versioned language handling

The separate declaration checkpoint uses immutable backend
`6b4b654737d4d6bf7d26a749f431c15312c9a33b` (core `a6fd15c`, frozen fixture
`8439b6e`, and explicit action-capability repair `6b4b654`). The original frozen
433,475-byte `backend-declarations-wire-examples.json` is unchanged at SHA-256
`1afb38f43da024ab8e8f45d70d5b28bb564d2d8cb90618e1b41fb9bb1fdb6eed`.
A separate captured field projection, `backend-declaration-actions-wire-examples.json`
(SHA-256 `d6971acad82a319b17ac690e392ee208dd60f442faef831640e91146726a045b`),
records the added `reading_metadata` capability without rewriting the earlier
fixture. Scanner dependency original `d3cb125` is carried as `57405a1`; integration
already owns it. Backend code is not included in this Flutter checkpoint.

The readings view displays per-label language/script candidates, mixed declarations,
conflicting interpretations, unmeasured confidence, review requirements and the
exact versioned policy. Unknown declarations remain unknown; Unicode diagnostics
are not promoted into language or script classifications. A separate authenticated
provenance read pins revision and verifies run/observation/region/raw identity. It
shows retained model output, each human declaration, server-recorded actor/reason/
time and explicit supersession lineage.

Human editing requires both reviewer permission and the exact server-advertised
`reading_metadata` action. It never aliases another permission. The form uses one
opaque candidate per line, at most eight distinct candidates per language/script
list and at most 100 Unicode codepoints per candidate. Co-occurring or alternative
language relationships require two distinct languages. A reason is required;
empty lists explicitly record no declaration. The client supplies no actor,
confidence or provenance. Current CAS and record-version identity accompany the
existing decisions endpoint. Model/raw evidence remains immutable, prior human
entries remain in history, and approval is invalidated rather than inferred.

Six focused wire/widget tests pass: exact request/CAS, pinned authenticated
provenance and mismatch rejection, mixed/conflicting/unknown policy states,
model/human supersession separation, authoritative action plus reviewer gating,
and required reason/relationship validation. The canonical gate passes 81 Python
(3 optional skips), 64 Flutter (6 gated live tests skipped), fatal-info analysis,
both secret scanners, web release build and Wasm dry run. Log:
`/tmp/flutter-declarations-gates.log`.

Actual Flutter HTTP proof used the immutable backend with fresh mixed-declaration
SQLite state `/tmp/specimen-flutter-declarations-state-6b4b654b`, synthetic-only
API 8018. Specimen `748c44fa-b2f2-5c32-80cd-2cdb5269aa45` starts at revision 20;
separate approval reaches 21, French declaration 22 and superseding Italian 23.
Each declaration invalidates approval, preserves observations/raw bytes and the
immediately preceding phase/authority evidence, reconciles an identical-key replay
without another revision, and rejects stale CAS. Historical revision 20 retains
its original model declaration with no human entries. Log:
`/tmp/flutter-declarations-live.log`; reproducible gated client test requires a
fresh explicitly seeded synthetic record. An initial assertion compared phase
artifacts from before the separate approval action; it was corrected to isolate
the declaration mutation and rerun against fresh state.

After a real server restart, Chrome loaded the retained model and both human
entries, verified the required-reason form, and saved an explicit English/German
co-occurring declaration at revision 24. The policy now reports mixed=true,
conflicting=false, review_required=true and unmeasured confidence. A separate
HTTP read verified the exact saved candidates, three-entry supersession chain,
unchanged model/raw digest and `human_approved=false`. Browser evidence and proof:
`/tmp/flutter-declarations-evidence/declaration-form.png`, `saved-lineage.png`,
`saved-policy-ax.txt`, `saved-lineage-ax.txt`, `browser-save-http-proof.json`.
Both temporary API 8018 and Flutter web 3002 were stopped; QA ports and browser
viewport/settings were untouched. Independent combined QA, institutional policy
approval, real-language quality calibration and production acceptance remain open.
Later nullable disagreement/observation-measurement contracts are separate work.

### Scoped runtime risk, published policy pins and measured observation details

This additive UI checkpoint uses exact runtime fixture
`backend-runtime-wire-examples.json`, 410,255 bytes, SHA-256
`7e44c24bb0d0858aafd69cee665606e9ee6ec739cac023191ab753440a4aaaaf`.
Earlier fixtures remain unchanged. Scanner original
`42dd95a959f8f8d7ccc15808184aceba7f25a492` is carried as `3088165`; integration
already owns that dependency. Read the risk module's `PROFILE_LABEL_RISK.md`
contract and waited for the actual HTTP fixture and immutable backend before
verification. Backend source/fixture reference is full immutable
`b60d9f219b9a9cbc12bef2fc9bdeb186bd59d0d5`, core `a45643f`.
The later `25bac56` correction changes a backend SQL test/report, not this API.

The evidence view exposes specimen, label and field assessments with explicit
status, nullable composite, exact policy ID/version/digest, registry/feature
versions, resolution state, component counts/weights/contributions, reasons,
unmeasured dimensions and retained evidence details. Label/field details expand
individually and reset when their input digest changes. A blocked, unmeasured or
incomplete assessment never displays a composite, including a contradictory zero
in a negative presentation probe. Measured component contributions remain visible;
no local composite calculation or named risk bands are introduced. Prioritization
never becomes a clearance badge or overrides validation. Published policy
resolution/definition is inspectable; existing pinned-profile details retain the
language, scoring and segmentation settings supplied by the backend.

Observation details distinguish configured and reported model identities and show
actual retained latency/basis, finish/completion states, token counts and input
asset/crop lineage. Missing latency and parameters are explicitly unmeasured/not
reported, never fabricated zeros. Completion describes processing, not correctness.
The retained-transcription detail distinguishes measured disagreement fractions
from unavailable/policy-blocked comparison; agreement does not certify accuracy.
Separate semantic containers expose risk and telemetry text accessibly. No new API
routes, inference calls, profile defaults or classification thresholds were added.

Four focused tests pass for the two published synthetic policy variants (numeral
weight 20 versus 40, both composites null), scoped expansion/pins/unmeasured
dimensions, blocked/partial zero rejection, real captured versus absent telemetry,
and measured versus unavailable comparison. Final canonical verification passes
81 Python tests (3 optional skips), 68 Flutter tests (7 separately gated live tests
skipped), fatal-info analysis, both secret scanners, web release build and Wasm
dry run. Log `/tmp/flutter-runtime-final-gates.log`.

Actual Flutter HTTP readback passed against the immutable backend in
`/tmp/specimen-flutter-runtime-a45643f` checked out at full `b60d9f2`, using private
copies of the backend's captured `policies` and `telemetry` SQLite/blob states:
`/tmp/specimen-flutter-runtime-state-policies` and
`/tmp/specimen-flutter-runtime-state-telemetry`. API ports 8018/8019 were scoped to
loopback. No processing POST was made with the readback adapters; this verifies
current authenticated UI/repository retrieval of captured execution evidence,
not a fresh model execution. The backend owner separately verified hard-child,
SAM/classifier and SQL execution. The client read current profile revision 40 and
historical revision 20 with exact retained profile/risk pins, confirmed all label/
field/specimen composites and the queue risk remain null, and read telemetry
revision 21 matching the actual fixture. Log `/tmp/flutter-runtime-live.log`;
gated test `test/live_runtime_test.dart`.

Chrome on web 3002 confirmed queue Unmeasured, the policy-pinned weight-40 label
assessment with measured components and no composite, and both observations'
exact latency/token/crop lineage with missing parameters explicitly reported.
Final screenshot/AX evidence is `/tmp/flutter-runtime-evidence/risk.png`,
`risk-ax.txt`, `telemetry.png` and `telemetry-ax.txt`. The risk and telemetry blocks
are separately exposed in AX. Browser use was read-only. Both temporary APIs and
web server were stopped after verification; QA ports, viewport and browser
settings were untouched. Independent final combined QA and institutional policy/
calibration/production acceptance remain open.

### Narrow post-QA coordinate-message correction

Independent QA of product `ee4bec8` passed the final risk/telemetry and HEIC
crop/reopen checks, and reported one nonblocking stale local validation message.
That prior QA attribution is unchanged. Coordinator authorized this isolated
follow-up from clean Flutter `06f7616`; no API, layout or backend change is included.

Numeric parsing feedback is now derived from the current invalid-input set.
Both valid and invalid changes rebuild the message. Once every coordinate is
valid the parsing message disappears; another invalid field still blocks saving.
Other local validation errors remain separate, and workspace/server/CAS error
handling is untouched. Three targeted RegionEditor tests pass, including
valid-to-empty-to-valid replacement, another invalid field remaining, blocked
submission, exact saved bounds `[5, 7, 45, 57]` with quarter-turn 1, and preservation
of an unrelated required-reason error. All 70 Flutter tests pass (7 gated live
skips), and fatal-info analysis passes. Logs:
`/tmp/flutter-coordinate-validation-targeted.log`,
`/tmp/flutter-coordinate-validation-all.log`,
`/tmp/flutter-coordinate-validation-analyze.log`.
Integration/QA own the targeted final recheck before updating their frozen target.
