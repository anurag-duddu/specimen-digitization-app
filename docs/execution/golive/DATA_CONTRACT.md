# Go-live data contract

Status: draft for comment, 2026-09-23. Owner: the data workstream (S5, session
"Build the pipeline data model and thread API"). Authority: PLAN.md section 4.4
and the owner's requirement in PLAN.md section 1: "raw transcript back to sql
connect against original image with tracking back to which VLM gave what -
scoring for level of disagreement - LLM does first pass at which final RAW
transcript should run against (it should also give at a VLM level what was
returned to the harness) ... obviously everything should link back to the
specimen record/id".

This page fixes what SQL holds for every run, which domain fields each row comes
from, and the exact schema and connector additions. The lane (S3) and the first
pass and harness (S4) put their results into the domain `Run`; the projection
writer (S5 T2) is the only code that writes these tables. The thread API (S5 T3)
reads them.

## 1. Rules

1. The snapshot stays the workflow's source of truth. The normalized rows are a
   projection of it, written by `SqlConnectRepository` after each successful
   `SaveSpecimenV3`, and caught up on the next save if a write was lost.
2. Additive only. Three new tables, new nullable columns, and three `NOT NULL`
   relaxations (section 3.3). Nothing is dropped or renamed. The emulator
   migrates a database holding `main`'s schema to this one with rows intact.
3. One row per mutation. Data Connect rejects table input types as variables
   ("cannot use LabelRegion_Data as a variable"), so there is no batch or
   list write and no single transaction spanning the snapshot and its rows.
4. Insert only, with deterministic ids (section 5). A primary-key conflict means
   the row is already written, so replays are safe. A conflict on any other
   unique constraint is a defect and fails the write.
5. Every row is keyed to its run, and through `PipelineRun.specimenId` to the
   specimen. Regions carry the original image as `sourceAssetId`.

## 2. What SQL holds, stage by stage

| PLAN 4.1 stage | Domain source | SQL rows |
|---|---|---|
| 1 Image | `Specimen.asset` | `SourceAsset`, kind `original` |
| 2 Segmentation | `Run.regions[]`; `Run.segmentation` (model revision, settings) | `LabelRegion` per region; the settings and revision in `PipelineRun.pinnedVersions.segmentation` |
| 3, 4 Readings | `Run.observations[]`, raw envelope at `raw_ref` | `ModelObservation` per reading, `independent: true`, `stepKey` `transcribe:{region_id}:{route_id}`; `SourceAsset` kind `raw_response` for the envelope |
| 5 Disagreement | `Transcript` alignment fields (`disagreement_ratio`, `alignment_status`, `alignment_algorithm`, `alignment_reasons`, `observation_ids`) | `ReadingComparison`, one row per pair of readings of a region |
| 6 First pass | `Transcript` per region, extended by S4 (section 4.2) | `TranscriptionVersion` with region, decision kind, selected reading and rationale; the first pass's model call as a `ModelObservation` with `independent: false` and `stepKey` `first_pass:{region_id}`; `HarnessInput` per reading |
| 7 Harness | S4's tool call records (section 4.3); `Run.lookups`; `Run.fields` | `ToolCall` per call attempt; `EvidenceItem` for each lookup response; `FieldCandidate` with its input source; `CandidateEvidence` |
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
`ratio: Float` (null when the pair was not measured), `status` (the alignment
status, verbatim), `reasons: [String!]!`. Unique per run, region and pair.
The score is review priority and uncalibrated (SCR-004, SCR-005); the thread API
labels it so.

`HarnessInput`: what the first pass handed to the harness from one reading.
`runId`, `transcriptionVersionId`, `observationId` (the reading), `role`
(`decided_transcript` or `raw_reading`), `handedText` (exactly the text the
harness received from this reader), `note` (the first pass's statement about
this reader, when its output has one). Unique per transcription version and
reading.

`ToolCall`: one attempt of one harness tool call. `runId`, `callKey` (unique per
run, stable across replays), `phase` (HAR-003 phases), `tool`, `toolVersion`,
`fieldKey`, `inputSource` (`decided_transcript` or `raw_reading`),
`transcriptionVersionId` or `observationId` when the call ran on one region's
text, `attempt` (1 based), `arguments: Any!`, `outcome` (the typed outcome,
section 4.3), `result: Any` (bounded typed result, never the raw response),
`evidenceId` (the `EvidenceItem` the call produced), `startedAt`, `completedAt`.

### 3.2 New nullable columns

| Table | Columns |
|---|---|
| `PipelineRun` | `traceId` (32 lowercase hex, recorded once) |
| `TranscriptionVersion` | `regionId` (CONTRACTS.md 185), `decisionKind` (`identical_readings`, `first_pass` or `human`), `selectedObservationId` (the reading whose raw transcript the harness runs against; null when unresolved), `firstPassObservationId` (the first pass's model call), `rationale` |
| `FieldCandidate` | `inputSource` (`decided_transcript` or `raw_reading`), `sourceTranscriptionId`, `sourceObservationId` |
| `ResolvedField` | `fieldGroup` (`mandatory` or `optional`) |

### 3.3 Relaxed columns

| Column | Why |
|---|---|
| `SourceAsset.width`, `SourceAsset.height` | Raw provider responses are assets without pixels, and `ModelObservation.rawAssetId` and `EvidenceItem.rawAssetId` must point at them. The connector still requires both for image kinds (`original`, `crop`, `mask`). |
| `LabelRegion.cropAssetId` | `Region.crop_ref` is optional in the domain. |

The data plane (S2) must accept these three `DROP NOT NULL` changes as additive.

## 4. Domain fields the writer reads

Names are proposals until the owning session confirms them. The writer maps
whatever the owners settle on; the table columns above do not change.

### 4.1 From the lane (S3)

- `Run.trace_id: str | None`, the W3C trace id, 32 lowercase hex.
- `Run.field_groups: dict[str, Literal["mandatory", "optional"]]`, pinned from
  the profile at run creation, one entry for every key in `Run.fields`.
- `Run.segmentation` as today (`model_revision`, `settings`).
- The profile identity after classify: `Run.profile.id`, `Run.profile.version`,
  `Run.profile_snapshot`, `Run.dependencies["profile_snapshot_sha256"]`.

### 4.2 From the first pass (S4), on each region's `Transcript`

| Field | Type | Meaning |
|---|---|---|
| `decision_kind` | `identical_readings`, `first_pass`, `human` | how the decided transcript was reached |
| `selected_observation_id` | `str \| None` | the reading chosen; `text` is its `literal_text`, verbatim |
| `first_pass_call` | `Observation \| None` | the model call's provenance, same model as the readers' observations (route, model, provider, prompt version, input digest, raw response, tokens, latency, finish state); set only for `first_pass` |
| `reason` (exists) | `str \| None` | the first pass's rationale, or the reviewer's reason |
| `handoffs` | `list[ReaderHandoff]` | one per reading of the region |

`ReaderHandoff`: `observation_id: str`, `role: Literal["decided_transcript",
"raw_reading"]`, `handed_text: str | None`, `note: str | None`.

### 4.3 From the harness (S4), in `Run.tool_calls: list[ToolCallRecord]`

`ToolCallRecord`: `call_key`, `phase`, `tool`, `tool_version`, `field_key`,
`input_source`, `region_id` and `observation_id` (when the call ran on one
region's text), `attempt`, `arguments: dict`, `outcome`, `result: dict | None`,
`evidence_id` (the `Evidence` or `Lookup` it produced), `started_at`,
`completed_at`. `outcome` takes the `LookupStatus` values (`success`,
`no_match`, `ambiguous`, `empty_response`, `rate_limited`, `timeout`,
`authentication_error`, `authorization_error`, `provider_error`,
`malformed_response`, `policy_blocked`) plus any value S4 adds for a tool with
no configured source.

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
| `SourceAsset` (non-original) | `asset/{bucket}/{object}/{generation}` |
| `ProfileVersion` | `profile/{collection}/{profile key}/{version}/{config sha256}` |
| `TranscriptionVersion` | `transcription/{run}/{region}/{digest of decision}` |
| `HarnessInput` | `handoff/{transcription version}/{observation}` |
| `ReadingComparison` | `comparison/{run}/{region}/{left}/{right}` |
| `ToolCall` | `tool-call/{run}/{call_key}` |
| `FieldCandidate` | `candidate/{run}/{field key}/{digest of value}` |
| `RecordVersion` | `record/{run}/{specimen revision}` |
| `ResolvedField`, `ValidationFinding` | `{record version}/{field key or reason code}` |
| `Checkpoint` | `checkpoint/{run}/{step}/{attempt}` |

## 6. Authorization

The existing `Append*` operations require `canViewSensitive` and a reviewer
role, which the worker's release membership never has (`deploy_runtime.py`
459-461 requires `canViewSensitive == false`). Every operation in section 7
applies the rule `SaveSpecimenV3` already applies to the same data in snapshot
form: an active organization member; an active collection member with role
`operator`, `reviewer`, `manager` or `admin`; and the row's specimen is not
sensitive, or the member can view sensitive records. The specimen is found
through the row's run, never taken from a variable. `AppendReviewDecisionV1`
requires `reviewer`, `manager` or `admin`. Closed vocabularies (`role`,
`inputSource`, `decisionKind`, `fieldGroup`) and the trace id format are checked
in the operation.

## 7. Operations

All in `dataconnect/connector/projection.gql`, `@auth(level: NO_ACCESS)`, one
`@transaction` each, callable only through `:impersonateMutation`. The existing
`Append*` operations stay unchanged for compatibility.

| Operation | Writes |
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

## 8. Thread API response (S5 T3, draft for S6)

`GET /specimens/{id}/thread`, same authorization as the workspace route. One
object per request, for the active run unless `run_id` is given:

```json
{
  "specimen_id": "…", "revision": 12, "run_id": "…", "run_status": "completed",
  "profile": {"key": "zoology_insects_slides", "version": "1.0.0"},
  "trace": {"trace_id": "0af7651916cd43dd8448eb211c80319c", "url": "https://…"},
  "image": {"asset_id": "…", "sha256": "…", "width": 4000, "height": 3000},
  "regions": [{
    "region_id": "…", "ordinal": 0, "geometry": {"bbox": [10, 20, 400, 180]},
    "readings": [{"observation_id": "…", "route_id": "handwriting-qwen", "model": "…",
      "provider": "…", "prompt_version": "…", "literal_text": "…", "outcome": "…",
      "raw_response": {"asset_id": "…", "sha256": "…"}}],
    "comparisons": [{"left_observation_id": "…", "right_observation_id": "…",
      "algorithm": "bounded-levenshtein-fraction-v1", "ratio": 0.12, "status": "…",
      "calibration": "uncalibrated review priority"}],
    "first_pass": {"decision_kind": "first_pass", "selected_observation_id": "…",
      "decided_text": "…", "unresolved": false, "rationale": "…",
      "model_call": {"route_id": "…", "model": "…", "provider": "…", "prompt_version": "…"},
      "handoffs": [{"observation_id": "…", "role": "decided_transcript", "handed_text": "…", "note": null}]}
  }],
  "tool_calls": [{"call_key": "…", "phase": "lookup", "tool": "gbif_species_match",
    "tool_version": "…", "field_key": "taxon", "input_source": "decided_transcript",
    "attempt": 1, "arguments": {}, "outcome": "success", "result": {},
    "evidence_id": "…", "started_at": "…", "completed_at": "…"}],
  "fields": [{"field_key": "country", "group": "mandatory", "state": "supported",
    "literal": "…", "parsed": "…", "normalized": "…", "authority_id": null,
    "input_source": "decided_transcript", "evidence_ids": ["…"]}],
  "decision": {"disposition": "needs_human_review", "policy_version": "…",
    "reason_codes": ["…"], "summary": "…"}
}
```

`trace.url` is built on the server from a configured Logfire base and is null
when that is unset. S6 builds against a fixture of this shape until T3 lands.

## 9. Open questions

For S4: the first pass's structured output (does it give a rationale and a
per-reader note?), the `role` values, the `call_key` format, the outcome for a
tool with no configured source, and whether the queue decision produces a
summary for `RecordVersion.summary` (QUE-006); without one the writer stores the
reason codes joined.

## 10. Tests

`scripts/data/projection-test.mjs`, run by `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator: the whole chain for one
run; the worker allowed on a non-sensitive specimen and refused on a sensitive
one, where the same write then succeeds for a sensitive-capable reviewer;
cross-collection references refused; a replayed row refused with a primary-key
conflict and a natural-key duplicate refused by its unique constraint; the trace
recorded once; closed vocabularies and image dimensions enforced.
`scripts/ci/test_data_release.py` pins the table count at 30.
