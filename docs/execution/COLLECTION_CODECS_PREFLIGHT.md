# Optional image codecs and pre-submission preflight

Worktree `/Users/anuragduddu/.codex/worktrees/23ec/specimen-digitization-app`;
branch `codex/collection-codecs-preflight`, base
`5023f235304b4fe819f899ceb8afd9334b4a006d`. The first handoff remains on
`codex/collection-quality`. This extension adds only `image_codecs.py`,
`image_preflight.py`, their two test files and this report. No shared modules,
dependencies, Flutter, production or another worktree were changed. Implementation
SHA is supplied to coordinator/backend with the handoff.

## Before-submission contract

`preflight_image(data: bytes, declared_media_type: str, policy: CodecPolicy)`
returns frozen, JSON-serializable `PreflightResult`:

- `contract_version: image-preflight-v1`, `origin: server_preflight`;
- `status: review | blocked | rejected` (no implication of museum-quality readiness);
- original `input_sha256`, `size_bytes`, `declared_media_type` and decoded
  `actual_format` (null until successfully decoded; a hint is not proof of format);
- `decode` with explicit status/reason, original digest, decoder family and
  immutable derivative provenance; `diagnostics` with the matching existing metric
  names `mean_luminance`, `contrast_stddev`, `dark_fraction`, `bright_fraction`,
  `mean_neighbor_gradient`, `sample_width`, `sample_height`;
- codec `capabilities`, machine `issues`, `action_hints`, and `unmeasured` focus,
  glare, framing, label coverage and museum-quality acceptance;
- `source_transmitted: true`, `specimen_created: false`, `external_provider_used:
  false`, `original_preserved: true`.

The Python function is the server analysis boundary, not a camera/device check or
an endpoint. It writes no specimen/upload records and invokes no model/provider.
Flutter's explicitly requested server-check action must precede any transmission;
the UI must say that it sends bytes for analysis without creating a specimen.
Client-local thumbnail measurements remain a separate `client_local` UI capability
owned by Flutter; no local HEIC/RAW or device success is implied by these results.
No automatic server check occurs just because a file was selected. Backend owns
authenticated, size-limited preflight HTTP wiring and the frozen HTTP fixture;
actual submission must recheck original digest/size and validation, never trust a
client's old preflight. A different digest invalidates the prior preflight. A
post-upload diagnostic is not represented as a pre-submission test.

`diagnostics.input_sha256` describes the analyzed PNG derivative; the result's
root `input_sha256` and `decode.provenance.original_sha256` describe the unchanged
source. This distinction is deliberate. The derivative transform/digest are
available under `decode.provenance`; do not attach derivative coordinates directly
to sensor/encoded-grid coordinates without their declared mapping.

## Executable decode boundary

`decode_image(data, format_hint="", policy=CodecPolicy())` returns
`(DecodeResult, png_bytes_or_none)`. Optional capabilities are disabled by default.
The exact enabled package version must match policy, otherwise decoding blocks
with `codec_missing`, `codec_disabled`, or `codec_version_mismatch`. Import/native
runtime failure blocks as `codec_runtime_unavailable`. A default policy requires
an enforceable process address-space limit; unavailable enforcement produces
`memory_limit_unavailable` before decoding. The explicit test policy sets
`require_memory_limit=False` solely for bounded synthetic tests on this macOS host.
It is surfaced as `memory_limit_not_enforced_local_test_only` in preflight.

Each accepted decode uses a new Python process, avoiding inherited native thread
pools. It gets only bounded request configuration, a temporary source file and a
restricted environment containing runtime path/locale settings, not provider or
cloud credentials. The private temporary directory is removed on success, error or
timeout. stdout/stderr are discarded so native errors cannot expose source metadata.
No Pillow plugin is registered globally. This is resource separation, **not** an
OS filesystem/network sandbox; a production unprivileged container must additionally
restrict network/filesystem access and enforce its own memory budget.

Limits are explicit: existing 25 MB input / 20,000-axis / 40 MP ceiling (policy can
tighten), wall time <=30 seconds (default 15), CPU <=20 seconds (default 10),
address space <=2 GB (default 1.5 GB), output <=25 MB, structured output <=32 KB,
no core dumps and one OpenMP thread. Parent timeout kills and waits for its child.
OS CPU termination is tested with an actual busy child. Input dimensions are checked
before raster loading / HEIF pixel access / RAW unpack, then output dimensions and
bytes are checked. libheif's own security limits remain enabled. On macOS,
RLIMIT_AS returned ValueError; default decoding consequently blocks there. Test
mode enforces CPU/wall/byte/pixel/output limits but claims no hard memory bound.
Linux enforcement and container behavior need their own runtime validation.

## Tested capabilities and provenance

| Family | Actual implementation | Limits / gaps |
|---|---|---|
| JPEG/PNG/TIFF | Existing verified orientation view in child | TIFF remains profile opt-in; source checksum retained |
| HEIC | Optional pillow-heif standalone decoder; single primary image | HEIF MIME/container checked, AVIF excluded, multi-image rejected; real synthetic HEVC tested |
| DNG | Optional rawpy/LibRaw; TIFF DNGVersion tag checked before RAW open, dimension check before unpack | Only DNG enabled; no claim for CR2/CR3/NEF/ARW/RAF/ORF/RW2/headerless RAW |
| Other RAW | Explicit `raw_family_not_approved` | New family needs camera/container/geometry fixtures and policy approval |

DNG detection checks the actual bounded TIFF directory regardless of a misleading
TIFF hint, so a RAW file cannot bypass its family approval by changing extension.
A DNG hint on an ordinary PNG fails `dng_signature_missing`. File extension never
establishes validity. DNG demosaics with no auto-brightness or auto/camera white
balance, produces sRGB 8-bit and records conversion choices, LibRaw version,
active-area sensor crop and orientation. Non-square pixels, unsupported native
flips or unexpected active-area dimensions reject rather than invent a transform.
LibRaw flip 0/3/5/6 maps to EXIF 1/3/8/6; original active-area edges map to the
view through the existing tested affine transform. Raw sensor crop offset must
be applied separately when converting to full-sensor coordinates.

HEIF container transforms are applied by libheif; EXIF is not applied a second
time. The coordinate space is explicitly `decoded_heif_primary_pixel_edges`,
with identity mapping from that primary raster to output. Encoded grid/tile
mapping is unavailable and recorded as a conversion limitation; do not claim
an affine map from every encoded item. The synthetic fixture initially used
`from_pillow`, whose encoding transforms interfered with the intended orientation
case; it now encodes original bytes with orientation in the HEIF container.
Quarter-turn output dimensions and the real decoder are verified. Both optional
formats create a fresh RGB PNG with all EXIF/ICC/metadata stripped. Neither
HDR/color fidelity nor actual museum device processing is accepted by this test.

## Exact optional-dependency proposal and license evidence

No package was added to pyproject/lock. The isolated test environment used:

| Package | Tested version | Package/bundled notices inspected |
|---|---|---|
| pillow-heif | 1.7.0 | Wrapper BSD-3-Clause; wheel `LICENSES_bundled.txt` identifies binary wheel as GPLv2, libheif 1.23.3/libde265 1.1.2 LGPLv3, x265 encoder GPLv2 |
| rawpy | 0.27.1 | Wrapper MIT; bundled LibRaw 0.22.1 has LGPL-2.1 notice |
| tifffile (fixtures only) | 2026.3.3 | BSD-3-Clause; generates our own uncompressed synthetic CFA DNG |

Backend received exact pins and notices and owns the optional-extras decision.
These notices are recorded facts, not legal or institutional deployment approval.
Production distribution review must evaluate the actual bundled builds, including
pillow-heif's encoder even though the application only decodes. Codecs remain
opt-in; no global decoder installation or production activation occurred.

Primary implementation references checked during this work:
[pillow-heif public API](https://pillow-heif.readthedocs.io/en/latest/reference/API.html),
[HEIF orientation behavior](https://pillow-heif.readthedocs.io/en/latest/workaround-orientation.html),
[LibRaw geometry](https://www.libraw.org/node/31),
[rawpy API/build notes](https://github.com/letmaik/rawpy), and
[libheif security limits](https://github.com/strukturag/libheif/blob/master/SECURITY.md).
Installed Python API/source and bundled license files were independently inspected.

## Reproduction and verification

Baseline tests (missing optional codecs are explicit skips):

```bash
uv run pytest tests/test_image_codecs.py tests/test_image_preflight.py -q
```

Real optional codecs in an isolated uv overlay, without changing the lock:

```bash
uv run --with pillow-heif==1.7.0 --with rawpy==0.27.1 \
  --with tifffile==2026.3.3 \
  pytest tests/test_image_codecs.py tests/test_image_preflight.py -q
```

Every image is generated by tests from synthetic pixels. No downloaded/private
image, codec-paid service, inference, cloud resource or data policy approval is
needed to reproduce these local tests. Tests cover actual decode, HEIC/DNG 1/3/6/8
orientations, derivatives/digests/metadata, missing/disabled/mismatched codecs,
misleading MIME/RAW hints, malformed files, dimension/output/byte limits, actual
wall and CPU termination, memory-enforcement fail-closed state, explicit server
preflight semantics and round-trippable result JSON. Exact final counts and the
canonical gate are appended below after staged verification.

This advances ING-001/005/007 and P0-01 handler behavior. Production codec build
approval, Linux/container bounds, RAW camera-family expansion, representative
quality/color fidelity, browser/device capture and the real preflight HTTP/UI
journey remain separately unverified. Backend/Flutter own integration; this module
handoff alone does not close P0 pre-submission acceptance.

Final verification: optional real-codec suite **17 passed** in 11.15 seconds;
ordinary environment **9 new tests passed, 8 optional codec tests skipped**.
`scripts/ci/verify.sh` passed all staged implementation files: repository/secret
checks, **91 Python tests passed, 10 skipped** (8 codec + 2 opt-in SQL), Flutter
analysis/widget tests and release web build. Ruff F checks and staged diff checks
passed. Logs: `/tmp/collection-codecs-optional-tests.log` and
`/tmp/collection-codecs-verify.log`. This final report paragraph is a documentation
addition after the staged-code gate and is checked by commit hooks. No push,
merge, deployment, provisioning or paid inference was performed.
