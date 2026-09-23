# S5 brief: data model and thread API

Session title: **Build the pipeline data model and thread API**. Recommended
model Opus 5.5 at high effort.

## Mission

Every artifact of every run is in SQL, linked to the specimen, the original
image and the run, and the app reads a record's whole thread through one
endpoint.

## Read first

1. `docs/execution/golive/PLAN.md`, especially sections 4.4 and 4.7.
2. `~/specimen-golive/research/03-data-model-and-persistence.md` (all),
   `01-backend-pipeline-stages.md` stage 4, and `05-flutter-client.md` sections
   2 and 4.
3. `dataconnect/`, `application/storage.py`, `application/production.py` 80-534,
   `application/active_graph.py`, `docs/execution/DATA.md`, `DATA_CHECKSUM.md`,
   `DATA_PAGING.md`, `CONTRACTS.md`.

## Constraints

- Additive only, as PLAN section 4.4 defines it: expand-only. Dropping NOT NULL
  is allowed only on columns your contract names with a reason, never on
  provenance or idempotency keys (`ModelObservation.runId`, `regionId`,
  `provider`, `modelVersion`, `stepKey`). Every new connector operation is
  `@auth(level: NO_ACCESS)` with the membership `@check`s (`DATA.md` 73).
  Never destructive.
- Key everything per region: a specimen can carry several labels, and five
  pilot slides carry two (PLAN section 3).
- `Run.field_groups` is new, and you decide its shape. No Google Maps coordinates
  are stored anywhere (the platform terms allow caching them for 30 days at
  most); the place ID, matched names and components are.
- Versioned operations follow the existing pattern (new V-numbered operations
  with old and new adapter tests, `DATA_CHECKSUM.md` 64-84).
- Every new table updates `scripts/ci/release_sql_catalog.sql` and the table
  count test (`scripts/ci/test_data_release.py` 253-261) in the same PR. That
  test file is S2's; change only the count and tell S2.
- The first data release may go out before your schema; your schema then lands
  as an additive apply while the runtime runs (the release workstream, S2,
  builds that path).

## Pull requests, in order

**T1. The data contract, first and small.** Write
`docs/execution/golive/DATA_CONTRACT.md` and the exact additive GraphQL for what
the owner's requirements need and the schema cannot hold today (research 03
section 4): the disagreement score per region; the transcription's region
(required by `CONTRACTS.md` 185), the first pass's decision and what each reader
handed to the harness; the harness's tool calls (tool, arguments, typed outcome,
result, attempt, primary or fallback input); each field's group (mandatory or
optional) and source (decided transcript or raw reading); the automatic
coverage check's result and evidence (G15); the run's trace id;
`LabelRegion.cropAssetId` nullable if the domain needs it. Add connector
mutations (the existing `Append*` plus new ones) with the existing `@check`
authorization pattern, and emulator tests. S3 and S4 code against this PR, so
send it to both for comment before you mark it ready.

**T2. The projection writer.** `SqlConnectRepository` writes the normalized
rows for every run step in production, idempotently (keys from domain ids), in
the same transaction as `SaveSpecimenV3` where possible; `SourceAsset` and
`ProfileVersion` are written; `ReviewDecision` gets an append mutation for human
decisions. Emulator-backed tests (`--persistence sql-emulator`). Give the
acceptance lab (S7) a way to see the same rows locally: the emulator, or SQLite
parity.

**T3. The thread API.** `GET /specimens/{id}/thread` in a new module, reading
the normalized rows (and the snapshot for anything not yet normalized),
returning everything PLAN section 4.7 lists, with the trace id, a typed response
model, and the same authorization as the workspace route.

**T4. Contract snapshots.** Regenerate `docs/execution/backend-openapi.json` and
the wire examples from a non-production app (production disables
`/openapi.json`, `api.py` 458-461), and update the client's contract-test
amendments together with the UI workstream (S6).

## Coordination

S3 supplies the run fields and the trace id; S4 supplies the shapes of the
first-pass decision and the tool calls (agree them in T1); S6 consumes the
thread API; S2's data plane applies your schema. In `production.py` you own
`SqlConnectRepository` (80-534); the adapters (535-910) are S3's. `domain.py`
has no single owner; where S3 and S4 need the same shape, you decide it. Where
the specification is silent or contradictory, stop and ask the coordinator; do
not decide (G5).

## Done

For a processed specimen, SQL holds every artifact of section 4.1 keyed to the
specimen, image and run, and the thread API returns it.
