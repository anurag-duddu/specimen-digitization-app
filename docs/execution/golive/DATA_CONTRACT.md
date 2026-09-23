# Go-live data contract

Status: draft for comment, 2026-09-23. Owner: the data workstream (S5, session
"Build the pipeline data model and thread API"). Authority: PLAN.md section 4.4
and the owner's requirement in PLAN.md section 1: "raw transcript back to sql
connect against original image with tracking back to which VLM gave what -
scoring for level of disagreement - LLM does first pass at which final RAW
transcript should run against (it should also give at a VLM level what was
returned to the harness) ... obviously everything should link back to the
specimen record/id". Owner decisions G15 (automatic coverage check) and G16
(`identified_by_irn` optional) are included.

This page fixes what SQL holds for every run, which domain fields each row comes
from, and the exact schema and connector additions. The lane (S3) and the first
pass and harness (S4) put their results into the domain `Run`; the projection
writer (S5 T2) is the only code that writes these tables. The thread API (S5 T3)
reads them.

## 1. Rules

1. The snapshot stays the workflow's source of truth. The normalized rows are a
   projection of it, written by `SqlConnectRepository` after each successful
   `SaveSpecimenV3`, and caught up on the next save if a write was lost.
2. Additive only: three new tables, new nullable columns, three dropped `NOT
   NULL` constraints (section 3.3), new operations. Nothing is dropped, renamed
   or retyped, and no existing operation changes. The emulator migrates a
   database holding `main`'s schema to this one with its rows intact.
3. One row per mutation. Data Connect rejects table input types as variables
   ("cannot use LabelRegion_Data as a variable"), so there is no batch write
   and no transaction spanning the snapshot and its rows.
4. Insert only, with deterministic ids (section 5). A primary-key conflict means
   the row is already written, so replays are safe. A conflict on any other
   unique constraint is a defect and fails the write.
5. Every row is keyed to its run, and through `PipelineRun.specimenId` to the
   specimen. Regions carry the original image as `sourceAssetId`. A specimen may
   have several regions (slides 324-328 have two labels); everything from the
   readings to the first pass is per region, and a field records the region
   and reading its literal came from.
6. No Google Geocoding latitude or longitude is stored anywhere (Google Maps
   Platform Service Specific Terms 6.3.1): not in a column, a `result`, an
   evidence row or a stored raw response. S4 redacts them before storage and
   keeps the full response's digest; SQL holds the place id, the matched name
   and components, and the outcome.

## 2. What SQL holds, stage by stage

| PLAN 4.1 stage | Domain source | SQL rows |
|---|---|---|
| 1 Image | `Specimen.asset` | `SourceAsset`, kind `original` |
| 2 Segmentation | `Run.regions[]`; `Run.segmentation` (model revision, settings) | `LabelRegion` per region, geometry in the original's pixels with `rotation_quarter_turns`; the settings and revision in `PipelineRun.pinnedVersions.segmentation` |
| 2 Coverage (G15) | `Run.coverage_check` (S3, section 4.1) | `EvidenceItem` with `source` `label-coverage-check`; a failed check also reaches the queue's reason codes and a `ValidationFinding` |
| 3, 4 Readings | `Run.observations[]`, raw envelope at `raw_ref` | `ModelObservation` per reading: `independent` true, `stepKey` `transcribe:{region_id}:{route_id}`, `routeId`, `unreadableSpans`; `SourceAsset` kind `raw_response` for the envelope |
| 5 Disagreement | `Transcript` alignment fields | `ReadingComparison` per pair of readings of a region, with the ratio and its components |
| 6 First pass | `Transcript` per region, extended by S4 (section 4.2) | `TranscriptionVersion` with region, decision kind, selected reading and rationale; the first pass's model call as a `ModelObservation` with `independent` false and `stepKey` `first_pass:{region_id}`; `HarnessInput` per reading |
| 7 Harness | S4's tool call records (section 4.3); `Run.lookups`; `Run.fields` | `ToolCall` per call attempt; `EvidenceItem` per lookup response; `FieldCandidate` with its input source; `CandidateEvidence` |
| 8 Queue | `Run.disposition`, `Run.reasons`, `Run.profile.policy_version`, `Run.fields`, `Run.field_groups` | `RecordVersion`, `ResolvedField` with `fieldGroup`, `ValidationFinding` per reason code; `Specimen.disposition` as today |
| 9 Linkage | ids throughout | every row carries `runId` or a parent that does |
| Trace | `Run.trace_id` (S3) | `PipelineRun.traceId` |
| Profile | `Run.profile`, `Run.profile_snapshot`, `Run.dependencies["profile_snapshot_sha256"]` | `ProfileVersion`, then `PipelineRun`, once `profile_snapshot` is non-empty |
| Attempts | `Run.attempts`, `Run.blocker`, `Run.next_retry_at` | `Checkpoint` per step attempt |
| Human decisions | `DecisionInput` handled in `api.py` | `ReviewDecision`; the real action in `AuditEvent` through `SaveSpecimenV3`'s `action` |

Kept in the snapshot only, because the requirement does not ask for them in SQL:
per-region SAM scores, cost and usage, risk scores, the alignment blob, and the
harness's model turns (those are in the Logfire trace, PLAN 4.5).

## 3. Schema changes

### 3.1 New tables

`ReadingComparison`: the disagreement score for one pair of readings of one
region. `runId`, `regionId`, `leftObservationId`, `rightObservationId` (readings
in the profile's route order), `algorithm` (`bounded-levenshtein-fraction-v1`),
`ratio: Float` (null when the pair was not measured), `editDistance` and
`lengthBasis` (the ratio is `editDistance / lengthBasis`; `lengthBasis` is the
longer reading's length, at least 1), `status` (the alignment status,
verbatim), `reasons: [String!]!`. Unique per run, region and pair. The score is
review priority and uncalibrated (SCR-004, SCR-005); the thread API says so.

`HarnessInput`: what the first pass handed to the harness from one reading.
`runId`, `transcriptionVersionId`, `observationId` (the reading), `role`
(`decided_transcript` or `raw_reading`), `handedText` (required: the reading's
literal text, verbatim, exactly as the harness received it), `note` (the first
pass's statement about this reader; null for identical readings). A row exists
only for a reading actually handed to the harness. Unique per transcription
version and reading.

`ToolCall`: one attempt of one harness tool call. `runId`, `callKey` (unique per
run, stable across replays; S4's format is
`{phase}:{tool}:{input_source}:{observation_id}:{first 16 hex of the SHA-256 of
the arguments' canonical JSON}:{attempt}`), `phase` (HAR-003 phases), `tool`,
`toolVersion`, `source` (the database the tool queried; null for local
validators), `fieldKeys: [String!]!` (the fields the call serves; one geography
call serves several), `inputSource` (`decided_transcript` or `raw_reading`),
`transcriptionVersionId` or `observationId` when the call's literal came from
one region's text (null when it spans regions), `attempt` (1 based),
`arguments: Any!`, `outcome` (exactly the 11 HAR-008 values, checked in the
operation), `result: Any` (bounded: `candidates`, `retry_after` and the
sanitized `error` of CONTRACTS.md's `LookupResult`; never the raw response),
`evidenceId` (the `EvidenceItem` the call produced), `startedAt`,
`completedAt`.

### 3.2 New nullable columns

| Table | Columns |
|---|---|
| `PipelineRun` | `traceId` (32 lowercase hex, recorded once) |
| `ModelObservation` | `routeId`, `unreadableSpans: [String!]` |
| `TranscriptionVersion` | `regionId` (CONTRACTS.md 185), `decisionKind` (`identical_readings`, `first_pass` or `human`), `selectedObservationId` (the reading whose raw transcript the harness runs against; null when unresolved), `firstPassObservationId` (the first pass's model call), `rationale` |
| `FieldCandidate` | `inputSource` (`decided_transcript` or `raw_reading`), `sourceTranscriptionId`, `sourceObservationId` |
| `ResolvedField` | `fieldGroup` (`mandatory` or `optional`) |

### 3.3 Dropped `NOT NULL`

| Column | Why |
|---|---|
| `SourceAsset.width`, `SourceAsset.height` | Raw provider responses and check evidence are assets without pixels, and `ModelObservation.rawAssetId` and `EvidenceItem.rawAssetId` point at them. The operation still requires both for image kinds (`original`, `crop`, `mask`). |
| `LabelRegion.cropAssetId` | SAM regions carry no crop (`Region.crop_ref` is always null from SAM), so a region is written as soon as segmentation finishes. The crop each reader saw is identified by `ModelObservation.inputSha256`. |

## 4. Domain fields the writer reads

Names are proposals until the owning session confirms them. The writer maps
whatever the owners settle on; the table columns above do not change.

### 4.1 From the lane (S3)

- `Run.trace_id: str | None`, the W3C trace id, 32 lowercase hex.
- `Run.field_groups: dict[str, Literal["mandatory", "optional"]]`, pinned from
  the profile at run creation, one entry for every key in `Run.fields`. For the
  slide pilot, `identified_by_irn` is `optional` (G16).
- `Run.segmentation` as today (`model_revision`, `settings`).
- `Run.coverage_check` (G15): the check's version, outcome, region count, the
  full-image cross-check's result, reason codes, the evidence blob's ref and
  digest, and when it ran.
- The profile identity after classify: `Run.profile.id`, `Run.profile.version`,
  `Run.profile_snapshot`, `Run.dependencies["profile_snapshot_sha256"]`.

### 4.2 From the first pass (S4), on each region's `Transcript`

| Field | Type | Meaning |
|---|---|---|
| `decision_kind` | `identical_readings`, `first_pass`, `human` | how the decided transcript was reached |
| `selected_observation_id` | `str \| None` | the reading chosen; `text` is its `literal_text`, verbatim |
| `first_pass_call` | `Observation \| None` | the model call's provenance, same model as the readers' observations; set only for `first_pass` |
| `reason` (exists) | `str \| None` | the first pass's rationale, or the reviewer's reason |
| `handoffs` | `list[ReaderHandoff]` | one per reading of the region |

`ReaderHandoff`: `observation_id: str`, `role: Literal["decided_transcript",
"raw_reading"]`, `handed_text: str`, `note: str | None`. For `first_pass`,
`spans` holds one verdict per aligned difference with every reading's text for
that span, `alternatives` the unresolved material differences, and `unresolved`
is true when any material difference is unresolved. The rationale and the notes
are null for `identical_readings`. A region with no recorded decision has no
`TranscriptionVersion`; the run's stage and blocker say why.

### 4.3 From the harness (S4), in `Run.tool_calls: list[ToolCallRecord]`

`ToolCallRecord`: `call_key`, `phase`, `tool`, `tool_version`, `source`,
`field_keys`, `input_source`, `region_id` and `observation_id` (when the call ran
on one region's text), `attempt`, `arguments: dict`, `outcome`,
`result: dict | None`, `evidence_id` (the `Evidence` or `Lookup` it produced),
`started_at`, `completed_at`. `outcome` takes exactly the `LookupStatus` values
(`success`, `no_match`, `ambiguous`, `empty_response`, `rate_limited`,
`timeout`, `authentication_error`, `authorization_error`, `provider_error`,
`malformed_response`, `policy_blocked`). A missing or rejected Maps key is
`authentication_error`; deterministic validators record `success` with their
verdict in `result`. A paid call's cost is in S3's per-call cost record on the
run, not in SQL. The queue decision's summary (QUE-006) is
`Run.disposition_summary`, a deterministic sentence from the rule version and
reason codes, mapped to `RecordVersion.summary`.

Each `FieldValue` in `Run.fields` gains `input_source`, `source_region_id` and
`source_observation_id`, so a field's literal traces to the decided transcript
or to the raw reading it came from.

## 5. Identifiers

Rows with a domain id use it: specimen, run, region, observation, asset,
evidence. Every other row gets a UUIDv5 under one namespace fixed in the writer,
from a key that includes a content digest wherever a row can have several
versions:

| Row | Key |
|---|---|
| `SourceAsset` other than the original | `asset/{bucket}/{object}/{generation}` |
| `ProfileVersion` | `profile/{collection}/{profile key}/{version}/{config sha256}` |
| `TranscriptionVersion` | `transcription/{run}/{region}/{digest of decision}` |
| `HarnessInput` | `handoff/{transcription version}/{observation}` |
| `ReadingComparison` | `comparison/{run}/{region}/{left}/{right}` |
| `ToolCall` | `tool-call/{run}/{call_key}` |
| `FieldCandidate` | `candidate/{run}/{field key}/{digest of value}` |
| `RecordVersion` | `record/{run}/{specimen revision}` |
| `ResolvedField`, `ValidationFinding` | `{record version}/{field key or reason code}` |
| `Checkpoint` | `checkpoint/{run}/{step}/{attempt}` |

Data Connect returns UUID key fields as 32 hex characters without dashes; the
views (`SpecimenListing`) return them with dashes. Readers normalize.

## 6. Authorization

The existing `Append*` operations and `ListDueWork` require `canViewSensitive`,
which the worker's release membership never has (`deploy_runtime.py` 459-461
requires `canViewSensitive == false`). Every operation in section 7 applies the
rule `SaveSpecimenV3` already applies to the same data in snapshot form: an
active organization member; an active collection member with role `operator`,
`reviewer`, `manager` or `admin`; and the row's specimen is not sensitive, or
the member can view sensitive records. The specimen is found through the row's
run, never taken from a variable. `AppendReviewDecisionV1` requires `reviewer`,
`manager` or `admin`, as the API's decision route does. Closed vocabularies,
the trace id format and the score's bounds are checked in the operation.

## 7. Operations

The projection writes are in `dataconnect/connector/projection.gql`, all
`@auth(level: NO_ACCESS)`, one `@transaction` each, callable only through
`:impersonateMutation`. The existing operations stay unchanged.

| Operation | Writes or reads |
|---|---|
| `AppendSourceAssetV2` | `SourceAsset`, dimensions optional for non-image kinds |
| `AppendProfileVersionV2` | `ProfileVersion` |
| `AppendPipelineRunV2` | `PipelineRun`, with an optional trace id |
| `RecordRunTraceV1` | `PipelineRun.traceId`, once; the same id again is a no-op |
| `AppendLabelRegionV2` | `LabelRegion`, crop optional |
| `AppendModelObservationV2` | `ModelObservation` (readings and first-pass calls) |
| `AppendReadingComparisonV1` | `ReadingComparison` |
| `AppendTranscriptionVersionV2` | `TranscriptionVersion` with the section 3.2 columns |
| `AppendHarnessInputV1` | `HarnessInput` |
| `AppendEvidenceItemV2` | `EvidenceItem` |
| `AppendToolCallV1` | `ToolCall` |
| `AppendFieldCandidateV2` | `FieldCandidate` with its input source |
| `AppendCandidateEvidenceV2` | `CandidateEvidence` |
| `AppendRecordVersionV2` | `RecordVersion` |
| `AppendResolvedFieldV2` | `ResolvedField` with its group |
| `AppendValidationFindingV2` | `ValidationFinding` |
| `AppendCheckpointV2` | `Checkpoint` |
| `AppendReviewDecisionV1` | `ReviewDecision` |
| `ListDueWorkV2` (in `paging.gql`) | due work for the lane's worker: `includeSensitive` must be false for members who cannot view sensitive records, and then only non-sensitive rows are listed |

## 8. Thread API response (S5 T3, draft agreed with S6)

`GET /specimens/{id}/thread`, same authorization as the workspace route, for the
active run unless `run_id` is given. Values in `…` are elided:

```json
{
  "specimen_id": "…", "revision": 12,
  "run": {"run_id": "…", "status": "processing_blocked", "stage": "lookup",
    "blocker": "provider_error", "next_retry_at": "…",
    "profile": {"key": "zoology_insects_slides", "version": "1.0.0"}},
  "trace": {"trace_id": "0af7…", "url": "https://…"},
  "image": {"asset_id": "…", "sha256": "…", "width": 4000, "height": 3000,
    "pixel_basis": "original_pixel_edges"},
  "segmentation": {"model_revision": "…", "settings": {"concept_prompt": "label"}},
  "coverage": {"outcome": "confirmed", "region_count": 2, "reason_codes": [], "evidence_id": "…"},
  "regions": [{
    "region_id": "…", "ordinal": 0, "rotation_quarter_turns": 0,
    "geometry": {"x": 10, "y": 20, "width": 390, "height": 160},
    "readings": [{"observation_id": "…", "route_id": "handwriting-qwen", "model": "…",
      "provider": "…", "prompt_version": "…", "literal_text": "…", "unreadable_spans": [],
      "outcome": "…", "raw_response": {"asset_id": "…", "sha256": "…"}}],
    "comparisons": [{"left_observation_id": "…", "right_observation_id": "…",
      "algorithm": "bounded-levenshtein-fraction-v1", "ratio": 0.077, "edit_distance": 1,
      "length_basis": 13, "status": "…", "reasons": [],
      "calibration": "uncalibrated review priority"}],
    "first_pass": {"decision_kind": "first_pass", "selected_observation_id": "…",
      "decided_text": "…", "unresolved": false, "rationale": "…",
      "model_call": {"observation_id": "…", "route_id": "…", "model": "…", "provider": "…",
        "prompt_version": "…", "outcome": "…", "raw_response": {"asset_id": "…", "sha256": "…"}},
      "handoffs": [{"observation_id": "…", "role": "decided_transcript", "handed_text": "…", "note": null}]}
  }],
  "tool_calls": [{"call_key": "…", "phase": "lookup", "tool": "geocode", "tool_version": "…",
    "source": "google-maps-geocoding", "field_keys": ["country", "province_state", "county", "city"],
    "input_source": "decided_transcript", "region_id": "…", "observation_id": null, "attempt": 1,
    "arguments": {}, "outcome": "success", "result": {"candidates": []}, "error": null,
    "retry_after": null, "evidence_id": "…",
    "started_at": "…", "completed_at": "…"}],
  "fields": [{"field_key": "city", "group": "mandatory", "state": "supported",
    "literal": "…", "parsed": "…", "normalized": "…", "authority_id": null,
    "input_source": "decided_transcript", "source_region_id": "…",
    "source_observation_id": null, "evidence_ids": ["…"]}],
  "decision": {"disposition": "needs_human_review", "policy_version": "…",
    "reason_codes": ["…"], "summary": "…"}
}
```

- `run.status` uses the summary's `status` vocabulary; `decision` is null until
  the queue decides.
- `first_pass` is null for a region with no recorded decision; the run's
  `stage` and `blocker` say why. `unresolved` is true when the first pass ran and
  chose no reading.
- `geometry` is in the original raster's pixels (CONTRACTS.md geometry rules).
- `trace.url` is built on the server from a configured Logfire base and is null
  when that is unset.

## 9. Open questions

None for the data contract. S4 and the coordinator are settling whether the
harness still runs on the raw readings when the first pass selects no reading;
either way the region has `raw_reading` rows or no `HarnessInput` rows, and the
columns hold.

## 10. Tests

`scripts/data/projection-test.mjs`, run by `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator: the whole chain for one
run; the worker allowed on a non-sensitive specimen and refused on a sensitive
one, where the same write then succeeds for a sensitive-capable reviewer;
cross-collection references refused; a replayed row refused with a primary-key
conflict and a natural-key duplicate refused by its unique constraint; the trace
recorded once; closed vocabularies (including the 11 outcomes), a required
handed text, score bounds and image dimensions enforced;
`ListDueWorkV2` hiding sensitive rows from the worker and never listing
finished runs. `scripts/ci/test_data_release.py` pins the table count at 30.
