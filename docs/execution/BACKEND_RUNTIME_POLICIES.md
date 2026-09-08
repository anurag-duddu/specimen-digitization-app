# Backend runtime policy and deadline checkpoint

Owner: backend, worktree `3782`, branch `codex/backend-reliability`.
Base: `6b4b654`. No push, cloud provisioning, paid inference, merge or deployment.

## Dependencies and scope

Original commits in integration order: `64c5420` (bounded adjudication and actual
observation telemetry), `51fb6f65b7934366d60c9c536ebc48ba1625bdac` (risk policy
resolver), `c892e0e3c10a2ca5ad1d24a99571cfa3a7906acd` (published profile rules),
`fd72c33a2db1b082a6569a28c259f08942d08c04` (HF collection classifier), then this
runtime wiring. Local carries of the last three are `91701cb`, `6b75170`,
`e0ac0d6`; integration should carry originals only once.

Published profile selection resolves and retains exact language handling,
scoring policy reference/full resolution, and supported SAM settings. Subsequent
risk calculation validates the retained profile/rules/policy match. Missing or
unknown policy pins block rather than silently choosing a current default.
Historical deserialization remains compatible; historical runs do not acquire
invented policy pins. Selected profile variants change actual SAM request prompts,
language handling, and measured risk contributions; old run history remains exact.

Risk output contains specimen, label and field assessments with exact policy
references and measured components. Image quality, segmentation quality and
field agreement remain explicitly unmeasured, making incomplete composite scores
null. These values are triage evidence, never accuracy or clearance approval.
No automatic image detector, calibrated threshold, named risk-band taxonomy or
institutional policy was invented.

The configured HF classifier uses explicit server configuration, route/provider,
spending/data approval and sensitive-source approval. Model construction, source
retrieval/decoding and provenance persistence run inside a hard child-process
boundary. Missing configuration has no fallback to a different model/provider.

Transcription and extraction now use the same hard boundary around construction,
authentication, source loading, model calls and raw provenance persistence.
Transcription IPC carries only asset, its region, approved profile and pinned
configuration; no peer observations, prior runs, audit or authority results.
Extraction carries resolved transcripts and current fields, returning only typed
fields, new source-supported evidence and token usage. Parent state changes only
after completed, reaped child output. A killed/failed child leaves durable unknown
outcome and lease, without automatic replay. Local kill cannot cancel a request
already accepted by a remote provider. Cooperative SDK timeouts remain an inner
error translator, not the whole-effect deadline guarantee.

Default GBIF and authority HTTP reads bound raw response bytes and whole
construction/header/body time in child processes. Slow headers and drips are
terminated and reaped; oversized or encoded bodies do not become valid JSON
results. Explicit injected HTTP clients remain test transports. Parent-side
GBIF/authority blob persistence and SQL operations retain their separate existing
I/O limits; this checkpoint does not claim every storage operation has a hard
process deadline. SAM, classifier and model child factories include their own
scoped source/sink operations.

Provider exception bodies are sanitized before agent instrumentation, and model
content/binary/parameters instrumentation is explicitly disabled. Explicit HF
Secret Manager tokens now also reach the Pydantic provider constructor without
requiring environment mutation.

## Evidence

- Fresh isolated SQL Connect `127.0.0.1:9609` / PostgreSQL `5659`, plus SQLite:
  `tests/test_model_runtime.py tests/test_profile_runtime.py`: **10 passed**,
  37.33 seconds; `/tmp/specimen-model-boundary-tests.log`.
- Real child construction/model/sink stalls for both transcription and extraction:
  bounded completion, PID reaped, no late output, retained unknown lease, no replay.
- Actual SQL and SQLite workflow: two independent observations, raw response/crop
  lineage, source-supported extraction, durable intent inspected inside child,
  reopened application returns identical run.
- `scripts/ci/verify.sh`: **passed**. All pre-commit checks, Python **351 passed / 26 explicitly gated skips**, Flutter analysis, the local widget test and release web build passed. Log: `/tmp/specimen-final-runtime-canonical.log`. SQL opt-in tests are independently reported above; skipped live integrations are not inferred passes.

## Frozen additive wire evidence

`backend-runtime-wire-examples.json`, 410255 bytes, SHA-256
`7e44c24bb0d0858aafd69cee665606e9ee6ec739cac023191ab753440a4aaaaf`.
All earlier fixture files remain unchanged.

Three actual synthetic HTTP groups: `profile_variants`, `configured_classifier`,
`observation_telemetry`. The final group uses the hard transcription/extraction
factory, not an in-process substitute. Model responses are local FunctionModel
fixtures; SAM response masks are actual grayscale PNGs from a local test service.
These tests do not claim live model quality, live SAM serving or institutional
acceptance. `generate_runtime_fixture.py NEW_OUTPUT` refuses an existing target.

Retained SQLite/blob root:
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-runtime-wire-l44e4zzr`.
Subdirectories: `policies`, `classifier`, `telemetry`. Each has `state.db` and
`blobs`. These files are synthetic test evidence, not production data.

For a review API, use an immutable code worktree at the final checkpoint, construct
`create_app(mode="synthetic", repository=SQLiteRepository(root / "state.db"),
blobs=LocalBlobs(root / "blobs"), adapters=SyntheticAdapters(...), token=...)`,
and bind only a separately coordinated loopback port. GET existing specimen
workspaces reproduces the frozen state. Do not reprocess historical fixture runs
with a different adapter configuration; generate a new fixture for new execution.

## External gates

Published institutional registry/policy approval, approved inference/sensitive
source policy and budget, real endpoint credentials/configuration, representative
quality assessment, cloud IAM/restore/runtime rollout and release evidence remain
separate gates. Synthetic policy factories are explicit test data. No release is
claimed by this checkpoint.

## Integrated SQL follow-up

Integration's broader SQL suite exposed one stale assertion in
`test_sql_authority_review_and_search_metadata`: it expected an unmeasured/null
risk score to match numeric range 0 through 100 after human approval. The runtime
correctly excluded NULL. The test now verifies unfiltered discovery retains NULL,
then verifies the numeric range excludes that record. No runtime or filter logic
changed, and no frozen fixture bytes changed. Fresh isolated SQL `9609` / PG
`5659`, entire `tests/test_authority_runtime.py`: **5 passed**, 5.16 seconds;
`/tmp/specimen-null-risk-sql-tests.log`. This supplements canonical verification
above rather than claiming the earlier skipped SQL assertion had passed.
