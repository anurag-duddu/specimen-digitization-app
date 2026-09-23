# Go-live data contract

Status: in review (PR #88), 2026-09-23. Owner: the data workstream (S5, session
"Build the pipeline data model and thread API"). Authority: PLAN.md section 4.4
and the owner's requirement in PLAN.md section 1: "raw transcript back to sql
connect against original image with tracking back to which VLM gave what -
scoring for level of disagreement - LLM does first pass at which final RAW
transcript should run against (it should also give at a VLM level what was
returned to the harness) ... obviously everything should link back to the
specimen record/id". These owner decisions are included:

- G15, automatic coverage check;
- G16, `identified_by_irn` optional;
- G19, the harness runs on each raw reading when the first pass selects none;
- G20, a lookup confirming exactly one reader's literal resolves the disagreement;
- G23, GBIF decides a taxonomy outcome, and Global Names Verifier and Catalogue of
  Life support it, with a disagreement flagged but GBIF's result unchanged;
- G24, dates clear at the precision written;
- G26, only the place id from Google;
- G27 and G28, a place or taxon field keeps both its verbatim and its settled
  value.

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
4. Every write is an insert with a deterministic id (section 5), except
   `RecordRunTraceV1`'s set-once conditional update. A primary-key conflict means
   the row is already written, so replays are safe. A conflict on any other
   unique constraint is a defect and fails the write.
5. Every row is keyed to its run, and through `PipelineRun.specimenId` to the
   specimen. Regions carry the original image as `sourceAssetId`. Every parent a
   row names belongs to the row's run, or to its specimen for assets, and the
   operations enforce it (section 6). A specimen may have several regions
   (slides 324-328 have two labels). Everything from the readings to the first
   pass is per region, and a field records the region and reading its literal
   came from.
6. From Google geocoding only the place id, our own outcome and a digest of the
   response are kept (G26; Google Maps Platform Service Specific Terms 6.3.1).
   - No Google name, address component or coordinate is stored anywhere: not in
     a column, a `result`, an evidence row, a stored blob, the snapshot or a
     trace.
   - The stored record behind a Google `EvidenceItem` holds only those three
     values; its `responseSha256` is the digest of Google's full response, and
     its `locator` is `place/{place id}`.
   - A field Google confirmed keeps its derivation from the label (`literal`,
     `parsed` or `normalized`) with Google as supporting evidence. Its
     `authorityId` is at most the place id, and its `normalizedValue` is at most
     a reader's exactly matching literal, never a Google name.
   - GBIF's accepted names may be stored (G28).
7. A place or taxon field keeps both its verbatim, as written on the label, and
   its settled value, as the harness settled it (G27, G28). When the first pass
   selected no reading, the verbatim is one value per reader, each attributed to
   its reading.

## 2. What SQL holds, stage by stage

| PLAN 4.1 stage | Domain source | SQL rows |
|---|---|---|
| 1 Image | `Specimen.asset` | `SourceAsset`, kind `original` |
| 2 Segmentation | `Run.regions[]`; `Run.segmentation` (model revision, settings) | `LabelRegion` per region, geometry in the original's pixels with `rotation_quarter_turns`; the settings and revision in `PipelineRun.pinnedVersions.segmentation` |
| 2 Coverage (G15) | `Run.coverage_check` (S3, section 4.1) | `EvidenceItem` with `source` `label-coverage-check`; a failed check also reaches the queue's reason codes and a hard `ValidationFinding` |
| 3, 4 Readings | `Run.observations[]`, raw envelope at `raw_ref` | `ModelObservation` per reading: `independent` true, `stepKey` `transcribe:{region_id}:{route_id}`, `routeId`, `unreadableSpans`; `SourceAsset` kind `raw_response` for the envelope |
| 5 Disagreement | `Transcript` alignment fields | `ReadingComparison` per pair of readings of a region, with the ratio and its components |
| 6 First pass | `Transcript` per region, extended by S4 (section 4.2) | `TranscriptionVersion` with region, decision kind, selected reading and rationale; the first pass's model call as a `ModelObservation` with `independent` false and `stepKey` `first_pass:{region_id}`; `HarnessInput` per reading handed over |
| 7 Harness | S4's tool call records (section 4.3); `Run.lookups`; `Run.fields` | `ToolCall` per call attempt; `EvidenceItem` per lookup response; `FieldCandidate` per verbatim value, with its input source and the settled value; `CandidateEvidence` with its G23 relation |
| 8 Queue | `Run.disposition`, `Run.reasons`, `Run.findings`, `Run.profile.policy_version`, `Run.fields`, `Run.field_groups` | `RecordVersion`, `ResolvedField` with `fieldGroup`, a hard `ValidationFinding` per reason code and a warning or info one per `Run.findings` entry; `Specimen.disposition` as today |
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
region.
- `runId`, `regionId`, and `leftObservationId` and `rightObservationId`: two
  independent readings of the region, in the profile's route order.
- `algorithm`: `bounded-levenshtein-fraction-v1`, the only value today; the
  column is free text.
- `ratio: Float`: null when the pair was not measured.
- `editDistance` and `lengthBasis`: the ratio is `editDistance / lengthBasis`,
  and `lengthBasis` is the longer reading's length, at least 1.
- `status`: the alignment status, verbatim.
- `reasons: [String!]!`.
- Unique per run, region and pair, and recorded in one order only.
- The score is review priority and uncalibrated (SCR-004, SCR-005); the thread
  API says so.

`HarnessInput`: what the first pass handed to the harness from one reading.
- `runId`.
- `transcriptionVersionId`, and `observationId`: a reading of that decision's
  region.
- `role`: `decided_transcript` or `raw_reading`.
- `handedText`: required; the reading's literal text, verbatim, exactly as the
  harness received it.
- `note`: the first pass's statement about this reader; null for identical
  readings.
- A row exists only for a reading actually handed to the harness. Unique per
  transcription version and reading.

`ToolCall`: one attempt of one harness tool call.
- `runId`.
- `callKey`: unique per run and stable across replays, in the form
  `{phase}:{tool}:{input_source}:{region_id or "-"}:{observation_id or "-"}:{first 16 hex of the SHA-256 of the arguments' canonical JSON}:{attempt}`.
  The region keeps identical calls on two regions apart.
- `phase`: one of the HAR-003 phases.
- `tool` and `toolVersion`.
- `source`: the database the tool queried; null for local validators.
- `fieldKeys: [String!]!`: the fields the call serves; one geography call
  serves several.
- `inputSource`: `decided_transcript` or `raw_reading`.
- `transcriptionVersionId` for a call on the decided transcript, or
  `observationId` for a call on a raw reading, when the call's literal came from
  one region's text; null when it spans regions.
- `attempt`: 1 based.
- `arguments: Any!`.
- `outcome`: exactly the 11 HAR-008 values.
- `result: Any`: bounded; `candidates`, `retry_after` and the sanitized `error`
  of CONTRACTS.md's `LookupResult`, never the raw response. A Google geocoding
  candidate is its place id and nothing else.
- `evidenceId`: the `EvidenceItem` the call produced.
- `startedAt` and `completedAt`.

### 3.2 New nullable columns

| Table | Columns |
|---|---|
| `PipelineRun` | `traceId` (32 lowercase hex, recorded once) |
| `ModelObservation` | `routeId`, `unreadableSpans: [String!]` |
| `TranscriptionVersion` | `regionId` (CONTRACTS.md 185), `decisionKind` (`identical_readings`, `first_pass` or `human`), `selectedObservationId` (the reading whose raw transcript the harness runs against; null only when no reading was selected), `firstPassObservationId` (the first pass's model call), `rationale`. `unresolved` follows the one rule in section 4.2 |
| `FieldCandidate` | `inputSource` (`decided_transcript` or `raw_reading`), `sourceTranscriptionId`, `sourceObservationId` |
| `ResolvedField` | `fieldGroup` (`mandatory` or `optional`) |

### 3.3 Dropped `NOT NULL`

| Column | Why |
|---|---|
| `SourceAsset.width`, `SourceAsset.height` | Raw provider responses and check evidence are assets without pixels, and `ModelObservation.rawAssetId` and `EvidenceItem.rawAssetId` point at them. The operation still requires both, positive, for image kinds (`original`, `crop`, `mask`). |
| `LabelRegion.cropAssetId` | SAM regions carry no crop (`Region.crop_ref` is always null from SAM), so a region is written as soon as segmentation finishes. The crop each reader saw is identified by `ModelObservation.inputSha256`. |

## 4. Domain fields the writer reads

S3 and S4 have confirmed these names. The writer maps them; the table columns
above do not change.

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
| `first_pass_call` | `Observation \| None` | the model call's provenance, same model as the readers' observations, with `literal_text` empty and the structured answer at `raw_ref`; set only for `first_pass` |
| `differences` | `list[FirstPassDifference]` | one per aligned difference: `number`, `spans` (per observation, exact `start` and `end` offsets into that reading's `literal_text` and the `text`), `verdict` (an observation id, `neither` or `uncertain`) and `material` |
| `reason` (exists) | `str \| None` | the first pass's rationale, or the reviewer's reason |
| `handoffs` | `list[ReaderHandoff]` | one per reading handed to the harness |

`ReaderHandoff`: `observation_id: str`, `role: Literal["decided_transcript",
"raw_reading"]`, `handed_text: str`, `note: str | None`.

The writer maps `TranscriptionVersion.spans` from `differences`, and
`alternatives` from the material differences whose verdict is `neither` or
`uncertain`.

**The unresolved rule** is the one definition of unresolved used everywhere. A
region's decision is unresolved when:
- no reading was selected (G19: the harness then runs on each raw reading, and
  every reading is a `raw_reading` handoff); or
- a material difference is still `neither` or `uncertain`, even though a
  reading was selected.

For a reviewer's decision, unresolved means the reviewer left it unresolved.
The domain's `resolved` flag means only that a reading was selected, so the
writer does not copy it.

The rationale and the notes are null for `identical_readings`. That kind also
covers identical readings that stay unresolved, such as unreadable spans or an
unmeasured alignment: no reading is selected there. A region with fewer than two
readings, or with no recorded decision, has no `TranscriptionVersion`; the run's
stage and blocker say why.

### 4.3 From the harness (S4)

**Tool calls,** in `Run.tool_calls: list[ToolCallRecord]`. Each record has:
- `call_key`, in section 3.1's form;
- `phase`, `tool`, `tool_version`, `source` and `field_keys`;
- `input_source`, plus `region_id` and `observation_id` when the call ran on
  one region's text;
- `attempt`, `arguments: dict`, `outcome` and `result: dict | None`;
- `evidence_id`, the `Evidence` or `Lookup` the call produced;
- `started_at` and `completed_at`.

`outcome` takes exactly the `LookupStatus` values: `success`, `no_match`,
`ambiguous`, `empty_response`, `rate_limited`, `timeout`,
`authentication_error`, `authorization_error`, `provider_error`,
`malformed_response` and `policy_blocked`. A missing or rejected Maps key is
`authentication_error`. Deterministic validators record `success` with their
verdict in `result`. A paid call's cost is in S3's per-call cost record on the
run, not in SQL.

**Fields.** Each `FieldValue` in `Run.fields` gains these:
- `input_source`, `source_region_id` and `source_observation_id`. A field's
  literal traces to the decided transcript or to the raw reading it came from.
  When a lookup confirms exactly one reader's literal (G20), the field records
  `raw_reading` and that reading's observation.
- `verbatim_by_observation: dict[str, str]` (G27, G28). It maps an observation
  id to that reader's literal exactly as captured, and is set only when the
  first pass selected no reading; `literal` is None there. The writer emits
  one `FieldCandidate` per entry, with `inputSource` `raw_reading` and that
  `sourceObservationId`. Place and taxon fields are treated alike.
- The settled value stays on the field: `authority_id` (Google's place id, or
  GBIF's usage key) and `normalized` (rule 1.6 for Google; GBIF's accepted name
  for GBIF).
- `evidence_relations: dict[str, Literal["decides", "supports", "contradicts"]]`
  (G23). It maps an evidence id to that source's relation to the value: GBIF's
  evidence `decides`, and Global Names Verifier and Catalogue of Life `support`
  or `contradict`. An evidence id without an entry `supports`. The writer
  stores the relation on `CandidateEvidence`.
- `precision` and `century_rule` (G24). A parsed date carries its precision
  (`day`, `month` or `year`, exactly as written, never widened) and the rule
  that set its century: the pinned profile's rule version and value, for
  example `date-rules-v1:two_digit_year_century=1900`, and null for non-dates
  and four-digit years. The writer stores `parsedValue` as `{value, precision,
  century_rule}` whenever either is set, otherwise as the parsed value alone.

**Findings and summary.**
- Findings that never route the record to review are in `Run.findings:
  list[Finding]`, never in `Run.reasons`, because any reason means needs human
  review (`policy.py` 176). Each Finding has `rule_id`, `rule_version`,
  `severity` (`warning` or `info`), `field_key`, `reason_code` and
  `evidence_ids`. They carry G23's source disagreement (`taxonomy_source_disagreement`)
  and G27's `spelling_disagreement` check (S8, #94 section 3.3). The writer
  stores each as a `ValidationFinding` with that severity, beside the hard
  finding it writes per reason code.
- The queue decision's summary (QUE-006) is `Run.disposition_summary`, a
  deterministic sentence built from the rule version and the reason codes. It
  maps to `RecordVersion.summary`.

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
| `FieldCandidate` | `candidate/{run}/{field key}/{observation or "-"}/{digest of value}` |
| `RecordVersion` | `record/{run}/{digest of disposition, reasons, summary, findings and field states}` |
| `ResolvedField` | `{record version}/field/{field key}` |
| `ValidationFinding` | `{record version}/finding/{reason code}` |
| `Checkpoint` | `checkpoint/{run}/{step}/{attempt}` |

Data Connect returns UUID key fields as 32 hex characters without dashes; the
views (`SpecimenListing`) return them with dashes. Readers normalize.

## 6. Authorization and checks

The existing `Append*` operations and `ListDueWork` require `canViewSensitive`,
which the worker's release membership never has (`deploy_runtime.py` 459-461
requires `canViewSensitive == false`). Every operation in section 7 is
`@auth(level: NO_ACCESS)` with the organization and collection membership
checks (DATA.md 73). Each applies the rule `SaveSpecimenV3` already applies to
the same data in snapshot form:

- the caller is an active organization member;
- the caller is an active collection member with role `operator`, `reviewer`,
  `manager` or `admin`;
- the anchor's specimen is not sensitive, or the member can view sensitive
  records.

The anchor is the row's run, candidate or record version, or the specimen
itself for assets, runs and review decisions. It is read from the database.

On top of that rule:
- **Parents.** Every parent a row names must belong to the anchor's run: its
  region, readings, first-pass call, decision, evidence, candidate or
  predecessor. For assets, the parent must belong to the anchor's specimen.
  Otherwise the write is refused. A worker therefore cannot link another run's
  rows, or a sensitive specimen's, into its own.
- **Closed vocabularies.** Asset `kind`; decision `decisionKind`; handoff
  `role`; `inputSource`; tool-call `phase` (HAR-003) and `outcome` (HAR-008);
  `CandidateEvidence.relation`; finding `severity` (`hard`, `warning`, `info`)
  and `outcome` (`pass`, `fail`, `unresolved`, `not_applicable`); `fieldGroup`;
  record `disposition`.
- **Free text.** `ReadingComparison.algorithm`, alignment `status`, `tool` and
  `source`.
- **Consistency.** A first-pass decision names its model call. A resolved
  decision other than a reviewer's names its selected reading. A call on the
  decided transcript names no reading, and a call on a raw reading no decision.
  A reading pair is recorded in one order. Image assets have positive
  dimensions. The trace id is well formed. The score's parts are in bounds. A
  Google evidence locator is `place/{place id}`.
- **Review decisions.** `AppendReviewDecisionV1` requires `reviewer`, `manager`
  or `admin`, as the API's decision route does.
- **Approval claims.** `AppendProfileVersionV2` admits operators, because the
  worker writes the profile snapshot each run used. A non-null `approvedBy` is
  an approval claim and needs `main`'s rule: a reviewer or above with sensitive
  access. The worker writes null. The published profile's approval stays where
  it happened: the PR review and the release's `collection_profile_bytes` and
  `evidence_profile_sha256`. No client-facing API path passes user input into
  `approvedBy`.

## 7. Operations

The projection writes are in `dataconnect/connector/projection.gql`, all
`@auth(level: NO_ACCESS)`, one `@transaction` each, callable only through
`:impersonateMutation`. The existing operations stay unchanged.

| Operation | Writes or reads |
|---|---|
| `AppendSourceAssetV2` | `SourceAsset`; dimensions required and positive for image kinds |
| `AppendProfileVersionV2` | `ProfileVersion`; an approval claim needs a sensitive-capable reviewer |
| `AppendPipelineRunV2` | `PipelineRun`, with an optional trace id |
| `RecordRunTraceV1` | `PipelineRun.traceId`, once, by a conditional update: the same id again is a no-op, and of two concurrent ids exactly one wins |
| `AppendLabelRegionV2` | `LabelRegion`, crop optional |
| `AppendModelObservationV2` | `ModelObservation` (readings and first-pass calls) |
| `AppendReadingComparisonV1` | `ReadingComparison` |
| `AppendTranscriptionVersionV2` | `TranscriptionVersion` with the section 3.2 columns |
| `AppendHarnessInputV1` | `HarnessInput` |
| `AppendEvidenceItemV2` | `EvidenceItem` |
| `AppendToolCallV1` | `ToolCall` |
| `AppendFieldCandidateV2` | `FieldCandidate` with its input source |
| `AppendCandidateEvidenceV2` | `CandidateEvidence` with its relation |
| `AppendRecordVersionV2` | `RecordVersion` |
| `AppendResolvedFieldV2` | `ResolvedField` with its group |
| `AppendValidationFindingV2` | `ValidationFinding` of any severity |
| `AppendCheckpointV2` | `Checkpoint` |
| `AppendReviewDecisionV1` | `ReviewDecision` |
| `ListDueWorkV2` (in `paging.gql`) | due work for the lane's worker, oldest due time first: rows due at or before the cutoff in `(workAvailableAt, id)` order, paged by the cursor `(afterAt, afterId)`, starting from `1970-01-01T00:00:00Z` and `''`. A row without a due time is not listed; `storage.py` 69-84 never writes a null due time for a runnable stage. `includeSensitive` must be false for members who cannot view sensitive records, and then only non-sensitive rows are listed |

## 8. Thread API response (S5 T3, draft agreed with S6)

`GET /v1/organizations/{organization_id}/specimens/{specimen_id}/thread`, same
authorization as the workspace route, for the active run unless `run_id` is
given. Values in `…` are elided:

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
  "coverage_check": {"status": "passed", "checks": [{"name": "region_count", "passed": true,
    "detail": {}}, {"name": "full_image", "passed": true, "detail": {}}], "evidence_id": "…",
    "checked_at": "…"},
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
    "arguments": {}, "outcome": "success", "result": {"candidates": [{"place_id": "…"}]},
    "error": null, "retry_after": null, "evidence_id": "…",
    "started_at": "…", "completed_at": "…"}],
  "fields": [{"field_key": "city", "group": "mandatory", "state": "supported",
    "verbatim": [{"text": "…", "input_source": "decided_transcript", "region_id": "…",
      "observation_id": null}],
    "parsed": null, "precision": null, "century_rule": null,
    "normalized": null, "authority_id": "…",
    "evidence": [{"evidence_id": "…", "relation": "supports", "source": "google-maps-geocoding",
      "locator": "place/…", "outcome": "success"}]}],
  "decision": {"disposition": "needs_human_review", "policy_version": "…",
    "reason_codes": ["…"], "summary": "…",
    "findings": [{"rule_id": "…", "severity": "warning", "field_key": "taxon", "reason_code": "…"}]}
}
```

- `run.status` uses the summary's `status` vocabulary; `decision` is null until
  the queue decides.
- `coverage_check.status` is `passed`, `failed` or `not_run` (G15). A failed
  check's reason code, `label_coverage_unconfirmed` today (`policy.py` 35-36),
  is also in `decision.reason_codes`.
- `first_pass` is null for a region with no recorded decision; the run's
  `stage` and `blocker` say why. Its `unresolved` follows the rule in section
  4.2.
- Each field's `verbatim` has one entry, the decided transcript's literal, or one
  entry per reader when the first pass selected no reading (G27, G28). The
  settled value is `normalized` and `authority_id` (rule 1.6), and `evidence`
  gives each source's G23 relation. `parsed` stays a string; `precision` and
  `century_rule` sit beside it and are null for non-dates (G24).
- `decision.findings` lists the hard, warning and info findings. Warnings and
  info never change the disposition.
- `geometry` is in the original raster's pixels (CONTRACTS.md geometry rules).
- `trace.url` is built on the server from a configured Logfire base and is null
  when that is unset.

## 9. Questions settled while this was in review

- **Sensitive uploads and due work** (coordinator ruling, 2026-09-23). Uploads
  default to sensitive, and a non-sensitive declaration must be explicit
  (CONTRACTS.md "Explicit intake sensitivity"). Sensitive data never goes to an
  unapproved provider (PRD 66, 715), and the worker's membership is
  nonsensitive (OWNER_INPUTS.md 288). So only uploads declared not sensitive run
  automatically, and G2 and DoD-6 hold for those. `ListDueWorkV2` does not
  change. The client makes a sensitive record's waiting state explicit (S6).
- **Due time.** It is the request time only for work that has not started. A
  scheduled retry is due at its `next_retry_at`, and sorts there.

## 10. Tests

`scripts/data/projection-test.mjs` runs from `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator. It checks:

- the whole chain for one run;
- a worker is allowed on a non-sensitive specimen and refused on a sensitive
  one, where the same write then succeeds for a sensitive-capable reviewer;
- every parent of another run or specimen is refused, sensitive ones included;
- cross-collection references are refused;
- a replayed row is refused with a primary-key conflict, and a natural-key
  duplicate by its unique constraint;
- the trace is recorded once, and of two concurrent ids exactly one wins;
- only a sensitive-capable reviewer may claim a profile approval;
- the closed vocabularies, the consistency rules, one order per pair, image
  dimensions and the Google locator are enforced;
- `ListDueWorkV2` lists the oldest due time first, with ties by id, pages one
  row at a time across a tie at a microsecond stamp, hides sensitive rows from
  the worker, and skips finished and undated runs.

`scripts/ci/test_data_release.py` pins the table count at 30. CI does not start
the emulator. It does not compile the GraphQL, run the `@check`s, test replays,
cursors or the migration from `main`. Those run locally, and each PR records
the result.
