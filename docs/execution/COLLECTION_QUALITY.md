# Collection, classification and image quality handoff

Worktree `/Users/anuragduddu/.codex/worktrees/23ec/specimen-digitization-app`;
branch `codex/collection-quality`; base `034d806c30b21e2b1d031ac6c84b6c80637088e8`.
Implementation commit is supplied in the coordinator message (this report is part
of that commit). Only the three assigned application modules, their three test
files and this report change. No dependencies or shared modules changed. No push,
production merge, provisioning, private images or paid inference occurred.

## Runnable contracts

- `CollectionProfileRegistry.resolve(collection_id, profile_version=None)` returns
  `ProfileResolution(status=selected|review, reason, profile)`. IDs are opaque;
  no collection name, UUID prefix or tenant identity implies a mapping. Missing,
  duplicate, mismatched, inactive, revoked and stale-version mappings fail closed.
  Nodes form an explicitly validated acyclic hierarchy. Profiles and nested values
  are frozen, versioned and JSON round-trippable; `profile.digest` hashes canonical
  model JSON. Persist this digest beside the full profile snapshot. Duplicate
  `(id,version)` definitions are rejected. Changing definitions requires building
  a new registry snapshot; storage publication and historical uniqueness across
  registry snapshots remain the backend/configuration owner's responsibility.
- `insects_registry()` is a **draft**, with institutional/semantics approval false.
  `insects_registry(synthetic=True)` is explicitly synthetic and active only for
  local fixtures. The unconfirmed parent taxonomy path is omitted. Required fields
  reuse the existing 20-field domain tuple. Input formats default to JPEG/PNG;
  TIFF needs explicit profile configuration. Profile definitions reference prompt,
  model, segmentation, validators, sources, scoring and clearance policy versions.
- `classify(ClassificationRequest, ClassifierAdapter)` validates input digest,
  allowed collection candidates and top-k. `ClassificationResult` retains ranked
  scores, reason codes, adapter/route/model/prompt/raw response provenance and
  calibration reference; NaN, infinity, duplicates and misordered ranks fail.
  `UnconfiguredClassifier` produces `blocked/approved_classifier_route_missing`.
  There is no invented production classifier. Approved route discovery, immutable
  prompt resolution, actual provider execution and raw-response storage must be
  supplied through this boundary by the backend owner after approval.
- `select_profile(result, registry, SelectionPolicy, ManualSelection=None)` defaults
  to human confirmation. Automatic selection requires matching nonempty calibration
  versions, score/margin thresholds and no tie. A profile confirmation requirement cannot be waived by call policy.
  Synthetic inference/profiles require
  explicit policy opt-in. A manual choice has actor and reason; it is retained
  separately from model predictions and cannot bypass a missing mapping.
- `correction_invalidation(kind)` reports dependent stages, whether a new run is
  needed, preservation of originals/observations and no training authorization.
  Classification invalidates profile-dependent quality and all downstream stages;
  segmentation invalidates transcription onward; transcription invalidates extraction
  onward; field correction invalidates validation/finalization. Backend must persist
  superseded versions, authenticate both scopes for any actual transfer, apply CAS
  and idempotency and restart these stages. These pure functions never transfer
  tenancy or grant permission. A selection alone is not evidence a new run executed.
- `diagnose_image(bytes, ImageLimits)` returns serializable `ImageDiagnostics` with
  valid/rejected status, checksum, dimensions, format, bounded metrics, issues and
  all-eight-orientation pixel-edge transform. Full pixel decoding plus format
  verification catches corrupt input. Bounds default to existing backend ceilings:
  25 MB, 20,000 per axis, 40 MP; configuration may tighten these, not exceed them.
  Analysis thumbnail is bounded to at most 512 square pixels. Single-frame only.
- `orientation_view(bytes, limits)` creates a separate metadata-free RGB PNG plus
  original/derivative checksums and the exact affine transform. Pixel-edge coordinates
  use exclusive upper bounds; pixel centers use x+0.5/y+0.5. All eight orientations
  are tested against actual image pixels and inverse geometry, including mirrored
  forms. This creates a full oriented view, not an inference crop or SAM mask.
- `check_regions(width,height,regions,digest,coverage=None)` reports zero regions,
  out-of-bounds geometry and strict positive-area overlap (touching is not overlap).
  It bounds region count to 1,000. `CoverageAdapter` and `CoverageObservation` allow
  independent full-image checks with digest/raw provenance and missing candidates.
  Missing coverage stays unmeasured. A reported complete result still requires
  reviewer confirmation and is not proof all labels were found.

All handlers use Pydantic models and `model_dump(mode="json")` / `model_dump_json()`.
Executable fixture builders are in the matching test files. Backend alone composes
these outputs into domain/workflow/API; evidence HarnessSpec can bind by profile
ID/version and must respect the profile tool allowlist. Shared HTTP fixture updates
belong to backend and Flutter. No shared wire schema was independently modified.

## Quality measurement limits and format capabilities

| Capability | Implemented behavior | Acceptance limit |
|---|---|---|
| JPEG/PNG | Bounded verification and decoding | Synthetic fixtures; museum/device corpus not validated |
| TIFF | Explicit format opt-in; rejects multiple frames | No RAW TIFF variants promised |
| HEIC/RAW | Unavailable decoder; rejected explicitly | ING-001 remains incomplete |
| Orientation | All EXIF 1–8 affine/pixel round trips | EXIF is untrusted; invalid orientation rejects |
| Exposure | Luminance mean, dark <=5 and bright >=250 fractions | Pixel measures, not institution-approved exposure thresholds |
| Blur/contrast | Mean neighbor gradient and luminance standard deviation | Controlled synthetic blur lowers both; content/scale dependent |
| Glare/focus/framing/occlusion | Explicit unmeasured limitation | Bright fraction cannot prove glare or missing labels |
| Geometry | Bounds, overlap, zero/missing regions | Full-image detector and SAM calibration absent |

Metrics are versioned and uncalibrated, never accuracy or clearance. Uniform
luminance emits a diagnostic issue but a valid decode is not a quality acceptance.
No inferred quality threshold changes a final queue. Production image decode should
run in an isolated unprivileged resource-limited process; these in-process limits
bound normal decoded size but are not a codec sandbox or CPU deadline. Derivative
conversion currently makes RGB and strips ICC as well as metadata; color-managed
museum fidelity and transparent-background policy need representative review.

HEIC/RAW next work must be a separately approved decoder proposal through backend:
check runtime support and licenses of the exact pinned codec builds, bound decode
in isolation, add lawful synthetic/public malformed and orientation fixtures, test
real device samples and update the capability matrix. No dependency is proposed as
already validated. No native camera feedback or actual device behavior is claimed.

## Verification and acceptance mapping

`uv run pytest tests/test_collection_profiles.py tests/test_classification.py
 tests/test_image_quality.py -q`: **28 passed**. Tests cover malformed/truncated
images, exact byte/pixel/axis boundaries, TIFF approval/multiple frames, all EXIF
pixel and geometry transforms, metadata stripping, invalid orientation, bounded
sampling, controlled blur/exposure, zero/overlap/bounds/missed regions, missing and
ambiguous profiles, frozen versions, opaque IDs, malformed classifier scores,
ranking/digest mismatch/ties, synthetic gates and two distinct synthetic profile
corrections. The first PNG tests caught EXIF access consuming the verification
stream; verification now opens its own stream before full decoding.

PRD executable coverage: CLS-001/003/005, PRF-001/002 contracts, ING-006/007
handler behavior, SEG-003/005 geometry, and correction invalidation for CLS-004 /
REV-007. P0-03 and PRF-003 still require backend HTTP/persisted integration and
real classifier acceptance. ING-005 and CLS-002 are partial until real device
feedback and calibrated classifier evaluation. P0-04 requires approved SAM 3 and
representative coverage evidence. Canonical gate result is recorded below after
verification of the staged candidate; no release or production acceptance claimed.

Final staged-code `scripts/ci/verify.sh` **passed**: repository/secret checks,
**82 Python tests passed, 2 opt-in SQL emulator tests skipped**, Flutter analysis,
widget test and release web build. The skipped SQL tests belong to backend/data
integration; this task did not start or borrow their emulators. Ruff undefined/
unused checks and staged `git diff --check` passed. Canonical log was retained
locally at `/tmp/collection-quality-final-verify.log`. The only Python warnings
were existing AnyIO/Logfire notices. The report's final verification paragraph is
a documentation-only addition after the staged-code gate, checked by commit hooks.
