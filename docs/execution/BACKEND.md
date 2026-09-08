# Backend implementation handoff

Branch `codex/insects-backend`; worktree
`/Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app`.
Base `82fd60e`. Implementation and handoff commit IDs are reported to the coordinator
with this document. No push, merge, cloud provisioning, deployment or paid inference
was performed by this task.

The backend now runs a persisted Insects journey through the application HTTP API.
A synthetic image can be uploaded in resumable chunks, processed into independently
retained observations, reviewed, cleared under an explicitly synthetic policy and
reopened after the API process is terminated. The same journey has passed against
SQL Connect backed by real local PostgreSQL 18, with local immutable image storage.
This proves application behavior; it does not establish museum quality or production
readiness.

## Reproduction

From the integrated repository, install the locked environment with `uv sync --frozen`.
Set a local secret without displaying it (the shell variable below is not committed):

```bash
export SPECIMEN_SYNTHETIC_TOKEN="$(openssl rand -hex 24)"
uv run specimen-api --mode synthetic --state-dir /tmp/specimen-local --port 8000
```

In another terminal with the same environment token:

```bash
uv run specimen-demo --url http://127.0.0.1:8000
```

The demo renders its own conspicuously synthetic label image, sends actual HTTP
intake/chunk/complete/review requests and reports the persisted result. The API
binds loopback only. Flutter uses local port 3000 and the bearer entered by the
operator; source images require an authenticated byte fetch. Tokens are neither
returned in session JSON nor persisted. No model receives a live request.

Completion schedules a local background worker. To resume work after an API crash,
run the independent polling worker against the **same** state directory:

```bash
uv run specimen-worker --mode synthetic --state-dir /tmp/specimen-local
```

`--once` executes at most one pending step per specimen. A worker process may be
stopped and restarted; the next stage comes from persistence. A lost external-call
response is not blindly retried: after the five-minute lease expires it becomes
`external_outcome_unknown`, requiring an explicit retry action and reason.

For SQL-backed testing, follow `docs/execution/DATA.md` to start the owned local
PostgreSQL process on 5549 and SQL Connect on 9499. Run the loopback-only
`scripts/data/seed-integration.mjs` fixture seed. It creates the synthetic memberships
used by these tests, not production users. Use a fresh state directory:

```bash
uv run specimen-api --mode synthetic --persistence sql-emulator \
  --state-dir /tmp/specimen-sql-local --port 8000
uv run specimen-worker --mode synthetic --persistence sql-emulator \
  --state-dir /tmp/specimen-sql-local
```

The selector uses `SqlConnectRepository` at the fixed isolated project
`demo-specimen-data`, service `specimen-digitization-service`, connector
`specimen-server`, location `us-east4`; it cannot target a cloud emulator address.
Originals and raw responses still use local immutable blobs in this test mode.
The session identifies `mode: synthetic` and `persistence: sql_connect`.

Run the actual network/process tests after the data fixture is seeded:

```bash
SPECIMEN_TEST_SQL_EMULATOR=true uv run pytest \
  tests/test_sqlconnect_application.py tests/test_http_process_restart.py -q
```

The TCP test owns port 8102, starts an API subprocess, drives the complete journey,
terminates and restarts that subprocess, compares the entire workspace and original
bytes, and stops its process. It does not reseed, repair or edit SQL rows.
`backend-sql-http-evidence.json` records the verified specimen/revision from this run.

## HTTP contract and ownership

`backend-openapi.json` is generated from the executable FastAPI application.
`backend-wire-examples.json` contains **actual HTTP responses**, including session,
batch, item, upload, completion, workspace and decision. Flutter adopted the same
fixture. `api.py` owns the final serializer, as agreed with architecture.

- `/v1/session` returns user, mode, persistence, scoped memberships and runtime blockers.
- Scoped paths are `/v1/organizations/{organization_id}/...` from `CONTRACTS.md`.
- Outer wire names use `specimen_id`, `revision`, `record_version_id`; internal stored
  snapshots use `id`, `version`, `scope`, `run`. The mapping is explicit.
- Workspace has singular `asset`, `regions`, `observations`, `transcriptions`, a
  20-key `fields` map, `evidence`, `validations`, `decisions`, `events`, and full `run`.
- Region aliases include `region_id` and original-pixel exclusive-upper-bound `bbox`.
- Upload: authenticated raw `PUT .../uploads/{id}/content`, `Upload-Offset`, at most
  4 MiB per chunk. GET returns authoritative offset/revision; completion verifies
  length, SHA-256, image format and dimensions before committing immutable originals.
- Supported decoding is JPEG, PNG and TIFF. HEIC/RAW need approved decoders; they
  fail explicitly. Limits are 25 MB, 20,000 per axis and 40 megapixels.
- Mutations use `Idempotency-Key`; review uses `expected_revision`, base record ID
  and reason. Domain conflicts return 409 without breaking HTTP keep-alive.
- Decisions: `field`, `transcription`, `approve`, `coverage`, and narrowly gated
  `capability_defer`. Deferral requires retained unreadable observations, exhausted
  independent passes, an allowed capability reason and retry eligibility. No client
  writes a final disposition directly.
- Runs support retry/resume/pause/cancel/reprocess. Region changes preserve the prior
  run and invalidate transcription/interpretation. Transcript and taxon corrections
  rerun dependent stages; raw observations remain in immutable snapshots.
- Synthetic-only `/specimens/{id}/process` is a bounded fixture driver. Production
  inference is dispatched by the separate worker, not this endpoint.

## Evidence and recovery implementation

`domain.py` defines application-owned records and the twenty mandatory keys.
`policy.py` requires supported non-placeholder values, source-pixel lineage, evidence
that contains the literal value, two distinct routes/models per region, resolved
transcripts, coverage, taxonomy support, numeric/date consistency, approved semantics
and human approval. Confidence never overrides a gate. The real draft profile has
institutional approval and semantics flags **false**; HTTP cannot enable them.

`workflow.py` persists every step and each independent reading before adjudication.
First-pass production agents receive only their own image and prompt, proven using
an actual Pydantic AI FunctionModel test through the production adapter. No peer
output enters their requests. All provider response messages, including retries, are
retained as immutable SDK response envelopes; provider HTTP bytes unavailable from
the SDK are not claimed as retained. Literal, parsed, normalized and authority values
remain distinct. The typed Pydantic AI extractor accepts only exact source-supported
candidates; unsupported suggestions are discarded rather than coerced.

SQLite atomically commits snapshot, revision and idempotency receipt. SQL Connect
uses the data owner's transaction operations to commit snapshot, receipt, audit and
outbox together, checks memberships at commit, and fences concurrent revisions.
SQL UUIDs and numeric JSON are normalized at the boundary. Snapshot digests survive
PostgreSQL/protobuf numeric serialization. Snapshots over 256 KiB are rejected
without truncating history. Blob writes are content-addressed create-only operations;
GCS additionally pins object generations and verifies downloaded hashes.

The polling runner uses five-minute persisted leases plus revision fencing around
external work. Completed logical steps are not repeated. An expired unfinished
intent is outcome-unknown, because a remote provider may already have charged or
executed; universal exactly-once network effects are not promised. Retryable taxonomy
429/timeout/provider failures schedule bounded retries and persist the next retry;
after three attempts they enter a recoverable dead-letter block. Auth/configuration
failures remain processing blocks. Final queues remain exactly three.

## Production adapters and required configuration

The explicit `--mode production` path uses:

- Firebase Admin ID-token verification with revocation checks and mandatory App Check;
  emulator-auth environment configuration is rejected.
- ADC authenticated SQL Connect named `impersonateQuery`/`impersonateMutation` calls,
  with verified actor UID variables. The official Admin SDK uses these admin paths;
  public execute endpoints respect `NO_ACCESS` and are inappropriate here.
- Current scoped organization/collection memberships; all source records are treated
  as sensitive and source bytes require the sensitive permission.
- GCS bucket `specimen-digitization.firebasestorage.app` with create-only generations.
- Existing HF gateway routes and Pydantic AI, metadata-only Logfire instrumentation.
- GBIF v2 matching with explicit COL XR checklist, metadata capture, raw references,
  distinct no-match/ambiguity/empty/malformed/429/timeout/auth errors. A high confidence
  with NONE/HIGHERRANK never becomes success.
- A pinned SAM3 Cloud Run HTTP adapter requiring service identity, model/revision/mask
  provenance and validated original-pixel geometry. No model download or GPU service
  is created, and a rectangle fixture is never labeled SAM3.

The existing production SQL service and Storage bucket were independently inventoried
by the data owner. The reviewed connector still needs its separately authorized
publication; resource existence is not connector readiness. Runtime identity needs
least-privilege SQL/GCS/Secret Manager/IAM-token permissions. The worker requires
`SPECIMEN_WORKER_ACTOR_UID` for an authorized scoped service/operator membership.
HF credentials must be injected server-side from the existing Secret Manager secret;
no secret value was read or stored by this task. `SPECIMEN_APPROVED_INFERENCE=true`
is an explicit runtime gate, not institutional or spending approval by itself.
`SPECIMEN_SAM3_ENDPOINT` must be an approved HTTPS Cloud Run endpoint. Neither was
activated or tested live. Production frontend origin is allowlisted separately.

Official implementation references: [Firebase token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens),
[SQL Connect REST](https://firebase.google.com/docs/reference/sql-connect/rest/v1/projects.locations.services.connectors),
[Firebase Admin transport](https://github.com/firebase/firebase-admin-node/blob/master/src/data-connect/data-connect-api-client-internal.ts),
[Pydantic AI message history](https://pydantic.dev/docs/ai/core-concepts/message-history/),
and [GBIF species API](https://techdocs.gbif.org/en/openapi/v1/species).

## Validation and honest remaining gates

The scoped tests cover HTTP chunk interruption/replay, original byte preservation,
all mandatory fields and unsupported values, missing evidence, unknown semantics,
independent requests/raw output, disagreement abstention, typed lookup failures,
retry recovery with unchanged observation IDs, capability deferral boundaries,
unauthorized scope, concurrent CAS, idempotency payload conflicts, snapshot bounds,
and SQL-backed HTTP process restart/reconstruction. The canonical gate additionally
runs all baseline Python tests, repository/secret checks and the existing Flutter
analyze/test/web build. Flutter product changes belong to the parallel owner and
must pass integration checks after cherry-picking.

Remaining production/P0 acceptance gates are explicit:

1. Representative expert-reviewed museum dataset, quality thresholds, approved
   Verbatim D/T/S and Parties semantics, collection policy and provider data-use rules.
2. Live SAM3 service deployment/license/performance validation and paid HF image
   inference authorization. Production adapters are executable but untested live.
3. Automated collection prediction is not implemented; intake explicitly selects the
   Insects profile. The correction endpoint can restart that supported profile;
   cross-collection transfers require another published mapping and authorization.
4. Automatic image-quality scoring and full-image missing-label verification are not
   implemented; original bytes and reviewer-confirmed region coverage are preserved.
5. Parties and geography access/matching policy remain unresolved. GBIF is the
   implemented authority; no unapproved person IRN or geocoder value is invented.
6. Temporal versus Google Workflows failure-injection comparison remains mandatory
   before engine selection. This local polling runner is not that comparison.
7. SQL normalized child tables and outbox are supplied by data; this adapter persists
   bounded aggregate snapshots. Normalized projections, outbox dispatcher, paginated
   historical graph and long-history scaling are a further production workstream.
8. Partial dates conservatively require review. API filtering currently implements
   scope/batch/state/disposition and pagination; broader PRD search filters remain.
9. Cloud runtime/connector delivery, IAM/stewardship review, backup/restore, actual
   storage IAM authorization and App Check device configuration need separate gates.
10. No production release claim: there is no merged PR, deployment or public marker
    proof from this task. Hosting does not deploy this Python runtime or SQL schemas.

### Final integration fixes

Independent QA identified typed transcription abstention and role projection gaps.
The API now accepts `after: {state: "unknown" | "unreadable" | "unresolved" |
"ambiguous" | "not_present", text: null}` and retains the typed state without
changing either independent reading. Supported text remains explicitly required
for `state: supported`. Real HTTP regression tests prove downstream abstention.
`available_actions` now reflects current caller role; viewers receive no mutation
actions, operators receive run controls and reviewers receive the named review
operations. The server independently rejects unauthorized decisions.

`taxonomy_resolution` is also implemented: a reviewer selects a retained candidate
by `after.authority_id` and supplies a reason. The original ambiguous lookup remains
unchanged; a separate authority-selection evidence record supports the normalized
value. A live, unpaid public GBIF lookup of `Danaus plexippus` returned an exact match
with three candidates and metadata; the adapter conservatively returned ambiguous.
No museum data or model inference was involved in that read.

The frozen shared wire example predates these additive action/state fields and is
retained byte-for-byte for backend/Flutter fixture parity. Their behavior is covered
by newer real HTTP tests. The release owner's reviewed scanner-baseline dependency
was cherry-picked as `74b9278` (source commit `30d6f99`); it permits only the exact
reviewed synthetic digest values, retaining both scanners and their default rules.

### Reviewed implementation commit and final checks

Implementation commit: `80b432eab35e97c04b6776373563a3128bf4b702`.
Scanner dependency: `74b9278` (equivalent to integration owner's `30d6f99`).
Data dependency for SQL mode: `790a9f936299de9770d66dc79563fb530625f9cf`.

On the final implementation candidate, `scripts/ci/verify.sh` passed all repository
and secret checks, **54 Python tests** (two explicit emulator tests skipped in the
ordinary suite), Flutter analysis, widget test and release web build. The two
emulator tests were separately enabled and **both passed**, including real TCP
SQL-backed HTTP intake/review and full API process restart. Ruff undefined/unused
checks and `git diff --check` passed. The only warnings were the installed Starlette
AnyIO deprecation and unconfigured Logfire in unit tests; executable API/worker
entry points configure metadata-only instrumentation.

Review-triggered work now schedules automatically in synthetic mode as well as
initial upload work. The abstention HTTP regression checks the subsequent GET
without invoking the synthetic `/process` driver, proving that dependent validation
runs automatically. Production remains on the independent polling worker.

Cherry-pick the implementation commit and this documentation follow-up into the
integration branch after its scanner dependency. Do not copy unrelated worktree
state or deploy runtime/data resources through Hosting. Full product acceptance
remains constrained by the numbered production gates above.

### Isolated QA ports

Local SQL API and worker modes now honor `SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:PORT`.
Only that loopback address and TCP ports 1–65535 are accepted, always with the
`demo-specimen-data` project. Production rejects the emulator environment variable
rather than silently selecting a test backend. The default remains 9499 for the
simple local commands above.

The real TCP subprocess test accepts `SPECIMEN_TEST_HTTP_PORT`; when omitted it
allocates a free loopback port instead of reserving 8102. It terminates only its own
API subprocess. Start a separately seeded data runtime on an independently owned
port before running the opt-in SQL tests; do not attach to another task's runtime.
Eight focused configuration tests cover rejected hosts/ports and production-mode
rejection. This follow-up changes runtime selection only; fixture bytes are unchanged.
