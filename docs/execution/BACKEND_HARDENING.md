# Codec intake and reliability hardening checkpoint

Branch codex/backend-reliability after core assembly026d0b9. This checkpoint is for local integration and independent acceptance, not production activation. Active graph externalization and language/script declaration capture remain subsequent implementation work.

## Carried owner changes

Original data3daf6c7+5f15bc1 carried ase216f9c+92afd58; bounded effecte0dd0aa carried asf70e6fe; circuit19997c7+681d1e0 carried asc7e9fdb+08f2da9; explicit profile formatseffb708 carried asa156313; exact codec fixture scanner5868705 carried asa2a9b87. Only application bindings, Python dependencies/tests and this report are backend authored. Owner modules retain their reviewed source.

## Intake and source pixels

Batch item dimensions may be omitted/null together. Original SHA256, size and media remain required. Server completion rehashes and fully decodes original bytes, establishes actual dimensions before creating the specimen, and verifies any supplied dimension claims. Raster dimension limits are checked before full pixel allocation.

HEIC and explicitly approved DNG use the bounded optional decoder process. Both a configured codec policy and published profile format permission are required for processing. Optional extras `heic` (pillow-heif1.7.0) and `raw` (rawpy0.27.1) are pinned, not enabled by default. Runtime memory enforcement and distribution/licensing approval remain external gates. macOS local tests explicitly disable the unavailable memory enforcement check; this is not a production policy. JPEG/PNG/TIFF retain independent validation and do not require optional preflight success.

Original objects remain unchanged. Asset.processing_derivative retains canonical pixel SHA, original association, codec/version/conversion metadata and pixel_basis. HEIC uses decoded_heif_primary_pixel_edges because libheif has already applied container transforms; no encoded-grid mapping is fabricated. DNG uses raw_active_area_pixel_edges with explicit sensor crop. For DNG, the stored oriented view is inverted to the recorded active-area basis for canonical crop bytes. The separate view derivative preserves the original-to-view affine transform. Worker crops and integrity verification consume retained canonical pixels rather than re-running optional codecs on restart.

`backend-codec-wire-examples.json` is frozen at SHA2568dc736071fc530260097279cee0a09fab35a7c67420ef2b3dcf7271fee673e7d. It contains an actual captured nullable-dimension HEIC request and responses from an explicit synthetic profile. The generator refuses existing output paths. `serve_codec_fixture.py` is a loopback-only synthetic test server with an explicit memory-enforcement exception; it is not a production startup route. Earlier two wire fixtures are unchanged.

## Duplicate completion and bounded reads

Python uses BOTH CreateSpecimenV3 and SaveSpecimenV3. Server-verified checksum feeds the scoped unique field. FindSpecimenByChecksum and SQLite's existing checksum index replace full-list duplicate precheck. If concurrent completions race, the loser rechecks current authorized scope and returns the existing specimen summary with upload_state=duplicate and duplicate_specimen_id; the upload's original completion receipt remains replayable. A hidden or unrelated conflict never yields another scope's ID. Existing V1/V2 writers and null legacy rows require explicit retirement/audit/backfill before rollout; no production migration was applied.

Local and GCS get_bounded consume at most cap+1 application bytes. GCS requests generation-pinned media with streaming enabled, no redirect, no eager download_as_bytes, and closes responses on every exit. Header sizes are advisory for early rejection; stream overflow or digest mismatch fails instead of returning a partial blob. Original/canonical pixel cap25MiB, phase artifact cap4MiB, raw HTTP view cap1MiB. This bounds read allocation; it does not claim a total wall-clock deadline for GCS authentication or slow object streams.

## Shared circuit and isolated SAM effects

Workflow admission binds the persisted circuit to owner-scoped worker_cursor CAS before external intent/reservations. Provider/configuration and circuit policy fingerprints are stable across runs; no secrets are stored in keys. Three transient failures open the breaker; provider RetryAfter is honored. Fresh workers share persisted admission and only one leased half-open probe. Valid biological no-match/ambiguity counts as provider availability success, separate from disposition. Current SQL worker_cursor ownership requires workers sharing a circuit to use the same configured worker identity; no cross-user authorization was weakened. Circuit state never reconciles a workflow's unknown external result.

The entire trusted SAM helper, including Google identity acquisition, HTTP send, bounded body and JSON/region validation, runs in the isolated child under one deadline. Completed raw responses retain checksum/model/source provenance. Timeout/crash/oversize leaves the durable intent outcome unknown, never automatically repeats the effect, and preserves the lease fence. Local process termination cannot cancel a remotely accepted request. Process-start OS syscall interruption and child memory ceiling limitations remain as documented by the bounded-effect owner; the HTTP helper streams its own bounded body. No live SAM service or paid inference was called.

## Verification

Focused checks include9 actual HEIC/DNG tests over orientations1/3/6/8 through upload/worker/crop/read/restart/approval;3 real isolated SAM adapter tests for success, slow authentication and drip TCP body with retained unknown state/no retry; bounded local/GCS stream overshoot/hash/response cleanup; and4 actual SQLite/SQL Connect tests covering concurrent HTTP same-source completion/replay and fresh-worker shared circuit/single half-open admission. The shared circuit tests use real database CAS, not an in-memory breaker.

The earlier retry test now verifies that forcing a record's retry time cannot bypass the shared provider minimum, then advances the injected clock beyond cooldown. Canonical scripts/ci/verify.sh PASS:243 Python passed/23 explicit SQL and optional-codec skips, repository/secret scans, Flutter analysis,16 widget tests and release web build. Log /tmp/specimen-hardening-canonical.log. The optional codec run separately passed9 tests using both pinned extras and tifffile2026.3.3 as a test-only fixture generator. The exact core commit is supplied in the handoff. No push, merge, provisioning, production schema changes or deployment occurred.
