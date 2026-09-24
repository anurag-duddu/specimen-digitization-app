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
- G25, a confirmed, accepted genus satisfies the taxon field of a label that
  identifies only to genus;
- G26, only the place id from Google;
- G27 and G28, a place or taxon field keeps both its verbatim and its settled
  value;
- G30, paid model calls spend at most USD 5, each reserving its worst-case cost
  before it starts;
- G31, the ten pilot slides are not sensitive;
- G32, a field found on two labels is settled per label on its own evidence, and
  clears when both labels settle to the same value.

This page fixes what SQL holds for every run, which domain fields each row comes
from, and the exact schema and connector additions. The lane (S3) and the first
pass and harness (S4) put their results into the domain `Run`; the projection
writer (S5 T2) is the only code that writes these tables. The thread API (S5 T3)
reads them.

## 1. Rules

1. The snapshot stays the workflow's source of truth. The normalized rows are a
   projection of it, written by `SqlConnectRepository` after each successful
   `SaveSpecimenV3`, and caught up on the next save if a write was lost, and
   after a run's final save by the lane's bounded re-projection (section 11).
2. Additive only: three new tables, new nullable columns, four dropped `NOT
   NULL` constraints, `SourceAsset`'s object uniqueness made per specimen in the
   two applies of section 3.3, new operations. The second apply drops
   `specimen_unique_1`, the ruled exception; nothing else is dropped, renamed or
   retyped, and no existing operation changes. The emulator migrates a database holding `main`'s schema to this
   one in place with its rows intact.
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
   - A region row belongs to one run. A domain region id can recur across runs:
     a region correction resends the ids it keeps, a region a person adds is
     `new-{microseconds}`, and the lab's segmenter derives ids without the run
     (`sam3_server.py` 390; production's seeds them with the run id, #105). So
     the row's id is derived from the run and the domain id (section 5), and
     `domainRegionId` keeps the domain id.
   - A segmentation correction starts a new run (`classification.py` 180). The
     new run's `supersedesRunId` names the run it replaces, and its regions are
     new rows. `supersedesRegionId` links regions within one run only.
6. From Google geocoding only the place id, our own outcome and a digest of the
   response are kept (G26; Google Maps Platform Service Specific Terms 6.3.1).
   - No Google name, address component or coordinate is stored anywhere: not in
     a column, a `result`, an evidence row, a stored blob, the snapshot or a
     trace.
   - The stored record behind a Google `EvidenceItem` is an `evidence_record`
     asset. It holds only those values: the place id when Google returned
     exactly one place (outcome `success`), the place ids and nothing else when
     it returned several (`ambiguous`), none for `no_match`. A call that got no
     response (a timeout, for example) has no stored record and no
     `EvidenceItem`; its `ToolCall` records the outcome. `responseSha256` is the
     digest of Google's full response.
   - A Google `EvidenceItem`'s `locator` is `place/{place id}` when set: always
     for `success` and for `recorded` evidence, never for any other outcome. The
     source string is exactly `google-maps-geocoding`, on evidence and on tool
     calls.
   - A field Google confirmed keeps its derivation from the label (`literal`,
     `parsed` or `normalized`) with Google as supporting evidence; Google never
     decides. Its `authorityId` is at most the place id in that evidence's
     locator, and its `normalizedValue` is at most a reader's exactly matching
     literal, never a Google name.
   - GBIF's accepted names may be stored (G28).
7. A place or taxon field keeps both its verbatim, as written on the label, and
   its settled value, as the harness settled it (G27, G28). When the first pass
   selected no reading, the verbatim is one value per reader, each attributed to
   its reading.

## 2. What SQL holds, stage by stage

| PLAN 4.1 stage | Domain source | SQL rows |
|---|---|---|
| 1 Image | `Specimen.asset` | `SourceAsset`, kind `original` |
| 2 Segmentation | `Run.regions[]`; `Run.segmentation` (model revision, settings) | `LabelRegion` per region of the run, with the domain's region id in `domainRegionId`, geometry in the original's pixels with `rotation_quarter_turns`; the settings and revision in `PipelineRun.pinnedVersions.segmentation` |
| 2 Coverage (G15) | `Run.coverage_check` (S3, section 4.1) | `EvidenceItem` with `source` `label-coverage-check`, outcome `recorded` and its own locator; a failed check also reaches the queue's reason codes and a hard `ValidationFinding` |
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
  independent readings of the region. `leftObservationId` is the one whose id
  sorts first as lowercase hex without dashes. The score is symmetric, so the
  order carries no meaning, and one fixed order lets the unique constraint
  refuse the reversed pair without a race.
- `algorithm`: `bounded-levenshtein-fraction-v1`, the only value today; the
  column is free text.
- `ratio: Float`: null when the pair was not measured.
- `editDistance` and `lengthBasis`: the ratio is `editDistance / lengthBasis`,
  and `lengthBasis` is the longer reading's length, at least 1.
- `status`: the alignment status, verbatim.
- `reasons: [String!]!`.
- Unique per run, region and pair.
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
  `{phase}:{tool}:{source or "-"}:{input_source}:{region_id or "-"}:{observation_id or "-"}:{first 16 hex of the SHA-256 of the arguments' canonical JSON}:{attempt}`
  (agreed with S4). The source keeps one tool's calls to several databases
  apart, and the region identical calls on two regions.
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
| `LabelRegion` | `domainRegionId` (the domain's region id: SAM's, a corrected one, or `new-{microseconds}` for a region a person added; the row's own id is per run, section 5) |
| `ModelObservation` | `routeId`, `unreadableSpans: [String!]` |
| `TranscriptionVersion` | `regionId` (CONTRACTS.md 185), `decisionKind` (`identical_readings`, `first_pass` or `human`), `selectedObservationId` (the reading whose raw transcript the harness runs against; null only when no reading was selected), `firstPassObservationId` (the first pass's model call), `rationale`. `unresolved` follows the one rule in section 4.2 |
| `FieldCandidate` | `inputSource` (`decided_transcript` or `raw_reading`), `sourceTranscriptionId`, `sourceObservationId` |
| `ResolvedField` | `fieldGroup` (`mandatory` or `optional`) |
| `ValidationFinding` | `evidenceIds: [UUID!]` (the evidence behind the finding, all of the record version's run) |

### 3.3 Relaxed constraints

Each relaxation only admits rows the old constraint refused; every existing row
satisfies the new one. PLAN 4.4 (as amended by #104, merged as 129c47e) allows a
dropped `NOT NULL` named here with its reason, and one closed exception
(coordinator ruling on #88, worded in #124's PLAN 4.4): `SourceAsset`'s object
uniqueness becomes per specimen, in two applies. S2's schema gate reads the same
list, with these reasons.

| Constraint | Change | Why |
|---|---|---|
| `SourceAsset.width`, `SourceAsset.height` | drop `NOT NULL` | Raw provider responses and check evidence are assets without pixels, and `ModelObservation.rawAssetId` and `EvidenceItem.rawAssetId` point at them. The operation still requires both, positive, for image kinds (`original`, `crop`, `mask`). |
| `LabelRegion.cropAssetId` | drop `NOT NULL` | SAM regions carry no crop (`Region.crop_ref` is always null from SAM), so a region is written as soon as segmentation finishes. The crop each reader saw is identified by `ModelObservation.inputSha256`. |
| `EvidenceItem.locator` | drop `NOT NULL` | A lookup that found no single match (`no_match`, `ambiguous`, an error) has nothing to locate, and G26 allows no Google value but a place id (rule 1.6). The operation keeps the locator set on every `recorded` row, and on a lookup exactly when its outcome is `success`, so it is optional nowhere else. |
| `SourceAsset` unique `specimen_unique_1` on (`bucket`, `objectName`, `generation`) | replaced by `source_asset_specimen_object` on (`organizationId`, `collectionId`, `specimenId`, `bucket`, `objectName`, `generation`), in two applies: #88 added the new constraint beside the old one, and T2a, the writer that needs it, drops `specimen_unique_1` once the first apply is live. The second step is one fixed, reviewed statement, `dataconnect/sql/drop-specimen-unique-1.sql`, a `DROP INDEX` of exactly that index, since S2's migration allowlist admits no drop, whatever Data Connect's diff carries. The data release runs it before it computes that diff, and only after its own read-back of the live database at apply time shows `source_asset_specimen_object` in place, over its six columns and valid, since S2's gate compares committed text only (PLAN 4.4 in #124). The local runners apply it behind the same read-back, `scripts/data/source-asset-read-back.sh` | The blob store is content-addressed and create-only (`GcsBlobs.put`), so byte-identical assets of different specimens are one stored object: the same GBIF answer for the same name, the same model response, or one image in two collections. Each specimen still records a stored object once. Nothing looks an asset up by its object: the key stays (`organizationId`, `collectionId`, `id`), and the only other write inserts by id. Every column the new constraint adds (`organizationId`, `collectionId`, `specimenId`) is `NOT NULL`, as the exception requires. Two applies, so that a unique constraint governs the table at every moment while writers run: the first adds the new constraint beside the old, which keeps governing, and cannot fail on existing rows, since it is weaker; the second drops the old only once the new one is read back in place, over its six columns and valid. |

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
"raw_reading"]`, `handed_text: str`, `note: str | None`. With a selected
reading, that reading is the `decided_transcript` handoff and every other
reading a `raw_reading` handoff with the first pass's note on it (null for
identical readings), so what each reader returned to the harness is recorded
(PLAN 4.1 stage 6). With none, every reading is a `raw_reading` handoff (G19).
The operation refuses a `raw_reading` handoff of the selected reading and a
`decided_transcript` handoff of any other (agreed with S4, #98).

The writer maps `TranscriptionVersion.spans` from `differences`, and
`alternatives` from the material differences whose verdict is `neither` or
`uncertain`.

**The unresolved rule** is the one definition of unresolved used everywhere. A
region's decision is unresolved when no reading was selected (G19: material
ambiguity means no pick; the harness then runs on each raw reading, and every
reading is a `raw_reading` handoff). A selected reading with a material
difference still `neither` or `uncertain` is resolved, and that difference is
stored in `alternatives`. For decisions other than a reviewer's, unresolved is exactly the negation
of the domain's `resolved` flag, which means a reading was selected (S4, #98).
For a reviewer's decision, unresolved means the reviewer left it unresolved.

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
  literal traces to the decided transcript or to the raw reading it came from
  (G20, G27; agreed with S4):
  - If the first pass picked a reading, the verbatim is that reading. `literal`
    and `input_source` stay on the decided transcript even when the harness
    falls back to the raw readings and a lookup confirms one of them. The
    confirmed reading appears only as the settled value's provenance: the
    `ToolCall` that ran on it (`input_source` `raw_reading`, its observation),
    that call's evidence, and `normalized`, which is then that reading's exact
    literal.
  - If the first pass picked none, the field uses the verbatim map below.
- `verbatim_by_observation: dict[str, str]`, `input_source_by_observation:
  dict[str, Literal["decided_transcript", "raw_reading"]]` and
  `settled_observation_ids: list[str]` (G27, G28, G32; agreed with S4). The
  three are set together, in two cases:
  - A field found on more than one label (G32: the harness settles each label
    separately, and the field clears when every label settles to the same
    value; PLAN in #124, 18958e0). There is one entry per label's source reading,
    even when the texts are identical, so every label keeps its own candidate: a
    label with a decided transcript contributes its selected reading
    (`decided_transcript`), and a no-pick label its readers (`raw_reading`).
  - A single-label field whose first pass selected no reading (G19): one entry
    per reader, each `raw_reading`.
  - Whenever the map is set, `literal`, `input_source`, `source_region_id` and
    `source_observation_id` are None. Single-label fields with a decided
    transcript stay as above, the G20 fallback included.
  - `settled_observation_ids` names the entries whose own verbatim settled to
    the field's value: one per label when the field cleared across labels (its
    decided reading, or the reader a lookup confirmed in a no-pick label), the
    confirmed reader in the single-label no-pick case, and none when the field
    is in review (labels or readings conflict).
  - The writer emits one `FieldCandidate` per entry with that entry's
    `inputSource`: a decided-transcript entry names its region's decision in
    `sourceTranscriptionId`, and a raw-reading entry its reading in
    `sourceObservationId`. Only the settled entries' candidates carry
    `normalizedValue`, `authorityId`, `parsedValue` and evidence links, each
    linking the evidence whose tool call ran on its own source (its reading, or
    its region's decided transcript); evidence from no tool call links to every
    settled candidate. The other candidates carry their literal and the field's
    state. `ResolvedField.candidateId` points at the first settled candidate in
    verbatim order, and is null when none settled.
  - The pointer selects the settled value only, never a verbatim: every label's
    and reader's verbatim stays on its own candidate. A field that clears across
    labels with differing spellings also gets the warning
    `spelling_disagreement` (S4's G32 rule, #131's `HARNESS.md`). Place and
    taxon fields are treated alike.
- The settled value stays on the field: `authority_id` (Google's place id, or
  GBIF's usage key) and `normalized` (rule 1.6 for Google; GBIF's accepted name
  for GBIF). Both are set only from a call whose outcome is `success`. A field
  without a lookup that clears across labels on identical texts has that common
  text in `normalized`, since `literal` is None there (G32).
  - GBIF's `success` (S4's T3a, under the coordinator's GBIF.md ruling and G25)
    is an `EXACT` match of an `ACCEPTED` usage with a key, in class Insecta, at
    the rank the label's name gives (a genus alone `GENUS`, a binomial
    `SPECIES`, a trinomial `SUBSPECIES`), with no live homonym.
  - `FUZZY`, `VARIANT`, `HIGHERRANK` and an exact synonym are `ambiguous`
    (GBIF.md 127-128). The label name stays the verbatim with no settled value;
    the reason codes the queue then records are S4's policy. For a synonym,
    S4 appends GBIF's `acceptedUsage` to that lookup's `candidates`, where
    the reviewer's `taxonomy_resolution` decision can select it: the
    accepted usage is proposed separately and never replaces the verbatim.
- `evidence_relations: dict[str, Literal["decides", "supports", "contradicts"]]`
  (G23). It has exactly one entry per id in `evidence_ids`, with no default, and
  maps each to that source's relation to the value: GBIF `decides`; Global Names
  Verifier and Catalogue of Life `support` or `contradict`; Google `supports`
  (rule 1.6). Only a `success` call's evidence, or recorded evidence that is not
  a lookup, is in `evidence_ids`. A call with any other outcome stays a
  `ToolCall` row with its `EvidenceItem` and is never support. A Global Names
  Verifier or Catalogue of Life answer that differs from GBIF's (a success
  against anything else) becomes the warning
  `taxonomy_source_disagreement:{source}`, and one unavailable after its retries
  `taxonomy_support_unavailable:{source}` (#109, `taxonomy_tool.py` 230-236).
  The writer stores the relation on `CandidateEvidence` and writes no link
  without one.
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
  `evidence_ids`. They carry the taxonomy tool's warnings under G23
  (`taxonomy_source_disagreement:{source}` and
  `taxonomy_support_unavailable:{source}`, #109) and `spelling_disagreement`,
  the readers' spelling difference under G27 that PLAN 4.1 stage 8 records as a
  finding (the code and its trigger are S4's, #131's `HARNESS.md`, after S8's
  #94 section 3.3). The writer stores each as a `ValidationFinding` with that
  severity and its recorded `evidence_ids`, each once, in `evidenceIds`, beside
  the hard finding it writes per reason code. Every finding the writer writes
  records a rule that did not pass, so its `outcome` is `fail`; `pass`,
  `unresolved` and `not_applicable` stay available to checks that record passing
  results, which none does today.
- The queue decision's summary (QUE-006) is `Run.disposition_summary`, a
  deterministic sentence built from the rule version and the reason codes. It
  maps to `RecordVersion.summary`.

## 5. Identifiers

Rows with a domain id use it: specimen, run, observation, the original asset,
evidence, and a review decision (its audit event's id). A region's domain id
repeats across runs (rule 1.5), so a region row's id is derived like the rest.
Every other row gets a UUIDv5 under one namespace fixed in the writer, from a
key that includes a content digest wherever a row can have several versions.
`{region}` is the domain region id, and `{left}` and `{right}` are in the
comparison's fixed order (section 3.1):

| Row | Key |
|---|---|
| `SourceAsset` other than the original | `asset/{specimen}/{bucket}/{object}/{generation}` |
| `LabelRegion` | `region/{run}/{region}` |
| `ProfileVersion` | `profile/{collection}/{profile key}/{version}/{config sha256}` |
| `TranscriptionVersion` | `transcription/{run}/{region}/{digest of decision}` |
| `HarnessInput` | `handoff/{transcription version}/{observation}` |
| `ReadingComparison` | `comparison/{run}/{region}/{left}/{right}` |
| `ToolCall` | `tool-call/{run}/{call_key}` |
| `FieldCandidate` | `candidate/{run}/{field key}/{observation or "-"}/{digest of value}` |
| `RecordVersion` | `record/{run}/{digest of disposition, reasons, summary, findings, field states and each field's resolved candidate}` |
| `ResolvedField` | `{record version}/field/{field key}` |
| `CandidateEvidence` | `candidate-evidence/{candidate}/{evidence}` |
| `ValidationFinding` | `{record version}/finding/{severity}/{rule id}/{field key or "-"}/{reason code}/{digest of its evidence ids}` |
| `Checkpoint` | `checkpoint/{run}/{step}/{attempt}` |

`CandidateEvidence` and `ReviewDecision` have no natural-key unique constraint,
and adding one over existing columns would not be additive, so the derived or
domain id is their only replay guard: every writer uses these keys.

Data Connect returns UUID key fields as 32 hex characters without dashes; the
views (`SpecimenListing`) return them with dashes. Readers normalize. Inside a
`@check`, a UUID variable is already lowercase hex without dashes, whatever
form the caller sent.

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
  A reading or decision a row names is also of the row's region, where the row
  names one: another region of the same run is refused too.
- **Closed vocabularies.** Asset `kind` (`original`, `crop`, `mask`,
  `raw_response`, `lookup_response`, `evidence_record`); decision
  `decisionKind` (`identical_readings`, `first_pass`, `human`); handoff `role`;
  `inputSource`; tool-call `phase` (HAR-003) and `outcome` (HAR-008);
  `CandidateEvidence.relation`; finding `severity` (`hard`, `warning`, `info`)
  and `outcome` (`pass`, `fail`, `unresolved`, `not_applicable`); evidence
  `outcome` (the 11 HAR-008 values and `recorded`); `fieldGroup`; record
  `disposition`.
- **Free text.** `ReadingComparison.algorithm`, alignment `status`, `tool` and
  `source`, except that a source naming Google in any letter case must be
  exactly `google-maps-geocoding`, on evidence and on tool calls.
- **Consistency.**
  - An original asset's `sha256` is its specimen's source checksum. Image
    assets have positive dimensions. A region's source asset is its
    specimen's original.
  - A decision other than a reviewer's is unresolved exactly when it names no
    selected reading (section 4.2). A `first_pass` decision names its model
    call, and no other kind names one. An `identical_readings` decision has no
    rationale, and its handoffs no note.
  - A `decided_transcript` handoff is of its decision's selected reading, and a
    `raw_reading` handoff of any other reading (section 4.2).
  - A call on the decided transcript names no reading, and a call on a raw
    reading names no decision.
  - A reading pair is recorded in its fixed order (section 3.1). The score's
    parts are in bounds. The trace id is well formed.
  - `EvidenceItem.locator` is always set on `recorded` evidence, and on a
    lookup exactly when its outcome is `success`.
- **Human decisions.** A `human` `TranscriptionVersion` needs `reviewer`,
  `manager` or `admin`, and so does `AppendReviewDecisionV1`, as the API's
  decision route does. The reviewer's own save writes them, and a worker's
  projection pass skips them. A review decision's resulting revision is after
  its base revision and no later than the specimen's current revision.
  - Catch-up (rule 1.1): a human decision lost from its reviewer's pass is
    written by the next save of a reviewer, manager or admin on that specimen.
    Until then a worker's pass stops, logged, at the first row that names it (a
    tool call or field candidate). Nothing is lost, because every pass resends
    each row its process has not recorded.
- **Google (G26, rule 1.6).**
  - An `EvidenceItem` from `google-maps-geocoding` has, when its locator is
    set, `place/{place id}` in place-id characters (`^place/[A-Za-z0-9_-]+$`);
    a 64-hex `responseSha256`; and an `evidence_record` asset for its stored
    record.
  - A `CandidateEvidence` link to Google evidence never `decides`, and the
    candidate's `authorityId` is null or the place id in that locator.
  - A Google call's `ToolCall.result` holds place ids only. CEL has no working
    `all()` here, so no operation can check each element; T2's writer tests are
    the gate for it.
- **Candidate evidence.** Only evidence with outcome `success`, or `recorded`
  evidence that is not a lookup, is linked to a candidate (section 4.3).
- **Findings.** `AppendValidationFindingV2` takes the run id. The record version
  and every one of the finding's `evidenceIds` must be of that run, each named
  once, at most 64.
- **Approval claims** (coordinator ruling on #88). `AppendProfileVersionV2`
  admits operators, because the worker writes the profile snapshot each run
  used. A non-null `approvedBy` is an approval claim and needs `main`'s rule: a
  reviewer or above with sensitive access, claiming for themselves (`approvedBy`
  is the caller). The worker writes null. The published profile's approval stays
  where it happened: the PR review and the release's `collection_profile_bytes`
  and `evidence_profile_sha256`. No client-facing API path passes user input
  into `approvedBy`.

## 7. Operations

The projection writes are in `dataconnect/connector/projection.gql`, all
`@auth(level: NO_ACCESS)`, one `@transaction` each, callable only through
`:impersonateMutation`. The existing operations stay unchanged.

| Operation | Writes or reads |
|---|---|
| `AppendSourceAssetV2` | `SourceAsset`; dimensions required and positive for image kinds; an original's `sha256` is the specimen's source checksum |
| `AppendProfileVersionV2` | `ProfileVersion`; an approval claim needs a sensitive-capable reviewer |
| `AppendPipelineRunV2` | `PipelineRun`, with an optional trace id |
| `RecordRunTraceV1` | `PipelineRun.traceId`, once, by a conditional update: the same id again is a no-op, and of two concurrent ids exactly one wins |
| `AppendLabelRegionV2` | `LabelRegion` with its `domainRegionId` (required), crop optional; supersedes only a region of its own run |
| `AppendModelObservationV2` | `ModelObservation` (readings and first-pass calls) |
| `AppendReadingComparisonV1` | `ReadingComparison`, in its fixed order |
| `AppendTranscriptionVersionV2` | `TranscriptionVersion` with the section 3.2 columns; `human` needs a reviewer or above |
| `AppendHarnessInputV1` | `HarnessInput`, its role matching the decision's selection |
| `AppendEvidenceItemV2` | `EvidenceItem`, locator optional; Google's rules in section 6 |
| `AppendToolCallV1` | `ToolCall` |
| `AppendFieldCandidateV2` | `FieldCandidate` with its input source |
| `AppendCandidateEvidenceV2` | `CandidateEvidence` with its relation, for `success` or `recorded` evidence only |
| `AppendRecordVersionV2` | `RecordVersion` |
| `AppendResolvedFieldV2` | `ResolvedField` with its group |
| `AppendValidationFindingV2` | `ValidationFinding` of any severity, with its evidence ids, all of the given run |
| `AppendCheckpointV2` | `Checkpoint` |
| `AppendReviewDecisionV1` | `ReviewDecision`; reviewer or above, revisions within the specimen's |
| `ListDueWorkV2` (in `paging.gql`) | due work for the lane's worker, oldest due time first: rows due at or before the cutoff in `(workAvailableAt, id)` order, paged by the cursor `(afterAt, afterId)`, starting from `1970-01-01T00:00:00Z` and `''`. A row without a due time is not listed; `storage.py` 69-84 never writes a null due time for a runnable stage. `includeSensitive` must be false for members who cannot view sensitive records, and then only non-sensitive rows are listed |

## 8. Thread API response (S5 T3, agreed with S6 on #88)

`GET /v1/organizations/{organization_id}/specimens/{specimen_id}/thread`, same
authorization as the workspace route, for the active run unless `run_id` is
given. A `run_id` whose run belongs to another specimen is refused as not found:
`Specimen.activeRunId` has no foreign key, and a non-sensitive specimen's thread
must never serve a sensitive specimen's run. Values in `…` are elided:

```json
{
  "specimen_id": "…", "revision": 12,
  "run": {"run_id": "…", "status": "processing_blocked", "stage": "lookup",
    "blocker": "provider_error", "next_retry_at": "…",
    "profile": {"key": "zoology_insects_slides", "version": "1.0.0"},
    "allowance": {"allowance_micros": 5000000, "reserved_total_micros": 0,
      "remaining_micros": 5000000, "at": "…"},
    "paid_calls": [{"step": "…", "attempt": 1, "kind": "model", "route_id": "…",
      "reserved_micros": 0, "usage": {"input_tokens": 0, "output_tokens": 0},
      "outcome": "completed", "cost_micros": 0, "cost_basis": "computed",
      "price_list": {"version": "…", "as_of": "…"}, "at": "…"}],
    "actual_cost_micros": 0},
  "trace": {"trace_id": "0af7…", "url": "https://…"},
  "image": {"asset_id": "…", "sha256": "…", "width": 4000, "height": 3000,
    "pixel_basis": "original_pixel_edges"},
  "segmentation": {"model_revision": "…", "settings": {"concept_prompt": "label"}},
  "coverage_check": {"status": "passed", "checks": [
    {"name": "region_count", "passed": true,
     "detail": {"found": 1, "min": 1, "max": 2, "reason_codes": []}},
    {"name": "full_image", "passed": true,
     "detail": {"counted": 1, "outside": 0, "threshold": 0.5, "min_inside_fraction": 0.8,
                "reason_codes": []}}],
    "evidence_id": "…", "checked_at": "…"},
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
    "normalized": null, "authority_id": "…", "settled_observation_ids": [],
    "evidence": [{"evidence_id": "…", "relation": "supports", "source": "google-maps-geocoding",
      "locator": "place/…", "outcome": "success"}]}],
  "decision": {"disposition": "needs_human_review", "policy_version": "…",
    "reason_codes": ["…"], "summary": "…",
    "findings": [{"rule_id": "…", "rule_version": "…", "severity": "warning", "outcome": "fail",
      "field_key": "taxon", "reason_code": "…", "evidence_ids": ["…"]}]}
}
```

- `run.status` uses the summary's `status` vocabulary; `decision` is null until
  the queue decides.
- `run.allowance`, `run.paid_calls` and `run.actual_cost_micros` come from the
  snapshot's `Run.program_allowance`, `Run.paid_calls` and
  `Run.usage.actual_cost_micros` (S3, G30: the program's USD 5 allowance and
  what remains of it). Cost stays out of SQL. A run with no paid call yet has an
  empty `paid_calls`.
  - A paid call's `cost_basis` is `computed` (the provider's reported usage times
    the pinned price list), `billed` (a billed amount the provider returned), or
    `reserved`, when the call's outcome is unknown (a timeout, a transport error,
    a 5xx, or a response without usage). A reserved call costs its full
    reservation, which is never released. Only `computed` or `billed` settles a
    call, and a settled cost above its reservation counts in full (coordinator
    ruling under G30; PLAN 4.3 and S5's brief in #124, 18958e0).
  - Each entry is passed through as S3 records it on the run (LANE.md T2c):
    `step`, `attempt`, `kind` and its target, `reserved_micros`, `usage`,
    `outcome`, `cost_micros`, `cost_basis`, `price_list {version, as_of}` and
    `at`.
    - The target is `route_id` for kind `model`, `service` for kind `service`
      (`sam3`), and `tool_id` for kind `tool`.
    - `usage` is `{input_tokens, output_tokens}`, `{seconds, vcpus,
      memory_gib}` or `{requests}`, and null for a reserved call.
    - `outcome` is `completed`, `failed` or `unknown`.
    - Keys S3 adds later reach the client unchanged.
- `region_id` throughout is the domain region id (`LabelRegion.domainRegionId`),
  the id the app and the snapshot use.
- `coverage_check.status` is `passed`, `failed` or `not_run` (G15). A failed
  check's reason code, `label_coverage_unconfirmed` today (`policy.py` 35-36),
  is also in `decision.reason_codes`.
  - `region_count`'s detail is `{found, min, max, reason_codes}`: the merged
    region count, and the profile's allowed range, null when the check did not
    record it. Its codes come from `zero_regions`, `region_out_of_bounds` and
    `label_region_count_out_of_range`.
  - `full_image`'s detail is `{counted, outside, threshold,
    min_inside_fraction, reason_codes}`: the label-like detections at or above
    the threshold, and how many of them lie outside the label regions. Its code
    is `cross_check_detection_outside_labels`, or none.
  - A check's `passed` is true exactly when its `reason_codes` is empty. The
    values come from S3's `Run.coverage_check` (#111), agreed with S6.
- `first_pass` is null for a region with no recorded decision; the run's
  `stage` and `blocker` say why. Its `unresolved` follows the rule in section
  4.2.
- Each field's `verbatim` has one entry, the decided transcript's literal; one
  entry per reader when the first pass selected no reading (G27, G28); or one
  entry per label's source reading when the field was found on more than one
  label (G32), each with its own `input_source`. The
  settled value is `normalized` and `authority_id` (rule 1.6), and `evidence`
  gives each linked source's G23 relation: `success` or `recorded` evidence
  only, while every other outcome is in `tool_calls`.
- `settled_observation_ids` lists, in verbatim order, the readings whose own
  literal settled the field's value (G20, G32):
  - with a verbatim map (several labels, or a no-pick label), the settled
    entries' readings, one per label when the field cleared across labels;
  - with a single decided transcript, the raw reading a fallback lookup
    confirmed;
  - otherwise it is empty.
  `parsed` stays a string; `precision` and `century_rule` sit beside it and are
  null for non-dates (G24).
- `decision.findings` lists the hard, warning and info findings, each with its
  evidence ids. Warnings and info never change the disposition.
- `geometry` is in the original raster's pixels (CONTRACTS.md geometry rules).
- `trace.url` is built on the server from a configured Logfire base and is null
  when that is unset.

## 9. Questions settled while this was in review

- **Sensitive uploads and due work** (coordinator ruling, 2026-09-23). Uploads
  default to sensitive, and a non-sensitive declaration must be explicit
  (CONTRACTS.md "Explicit intake sensitivity"). Sensitive data never goes to an
  unapproved provider (PRD 66, 715), and the worker's membership is
  nonsensitive (OWNER_INPUTS.md 288). So only uploads declared not sensitive run
  automatically, and G2 and DoD-6 hold for those. The ten pilot slides are not
  sensitive on the owner's verified classification (G31). `ListDueWorkV2` does not
  change.
- **Due time.** It is the request time only for work that has not started. A
  scheduled retry is due at its `next_retry_at`, and sorts there.
  - Before the worker switches to `ListDueWorkV2`, count the rows in `pending`,
    `running` or `retry_scheduled` with a null due time. V1 and V2 saves can
    write one, and `ListDueWorkV2` never lists such a row.
  - The due-work index is (`organizationId`, `collectionId`, `state`,
    `workAvailableAt`, `id`). No index matches the (`workAvailableAt`, `id`)
    order across the three states, so PostgreSQL merges or sorts the three
    ranges. A matching index is a separate reviewed change if staging's plans
    need one.

## 10. Tests

`scripts/data/projection-test.mjs` runs from `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator. It checks:

- the whole chain for one run;
- a worker is allowed on a non-sensitive specimen and refused on a sensitive
  one, where the same write then succeeds for a sensitive-capable reviewer;
- every parent of another run or specimen is refused, sensitive ones included,
  and so is a reading or decision of another region of the same run;
- cross-collection references are refused;
- a replayed row is refused with a primary-key conflict, and a natural-key
  duplicate by its unique constraint;
- the `SourceAsset` swap's step 2: two specimens each record one stored object,
  one specimen cannot record it twice, and only `source_asset_specimen_object`
  remains (read from PostgreSQL);
- a second run of the same specimen writes its own row for a region id the
  first run used, and a new run superseding the first is accepted;
- the writes the pipeline makes are accepted:
  - a picked decision's `raw_reading` handoffs of the other readings, and a G19
    no-pick `first_pass` decision with its `raw_reading` handoffs;
  - a G27 per-reader `raw_reading` candidate;
  - `identical_readings` and reviewer `human` decisions;
  - a crop with its parent asset, and a region with its crop;
  - a region superseding another of its run;
  - a Google `no_match` with no locator, recorded evidence linked to a
    candidate, and a finding with its evidence;
- the trace is recorded once, and of two concurrent ids exactly one wins;
- only a sensitive-capable reviewer may claim a profile approval, only for
  themselves, and only a reviewer may write a `human` decision;
- the closed vocabularies, the consistency rules, the fixed pair order, image
  dimensions, the original's checksum, a region's original, the handoff roles,
  identical readings' rationale and notes, the review revisions, the locator
  rule, the 64 evidence ids, and the Google rules of section 6 on evidence and
  tool calls are enforced;
- `ListDueWorkV2` lists the oldest due time first, with ties by id, pages one
  row at a time across a tie at a microsecond stamp, hides sensitive rows from
  the worker, and skips finished and undated runs; a stuck cursor fails the
  test instead of hanging it.

`scripts/ci/test_data_release.py` pins the table count at 30. CI does not start
the emulator. It does not compile the GraphQL, run the `@check`s, test replays,
cursors or the migration from `main`. Those run locally, and each PR records
the result.

For the writer: `tests/test_projection.py` (the mapping) and
`tests/test_projection_writer.py` (order, scope and actor, primary-key
conflicts, stop-and-resume on any other failure, a save that survives the
projection, sizes read once) run in CI; `tests/test_sqlconnect_projection.py`
runs against the emulator (`SPECIMEN_TEST_SQL_EMULATOR=true` with
`scripts/data/serve-local.sh`): stage 1 to 5 rows land once, and a fresh process
replays without duplicates or warnings.

## 11. Projection writer (S5 T2)

`application/projection.py` maps a specimen to the section 7 writes, in
foreign-key order, with the section 5 ids. It is pure: the repository supplies
the scope, the actor, a function that locates a blob by its ref and one that
measures it. Cloud Storage refs (`sha256:generation`) locate to the bucket,
`application/sha256/{sha256}` and the generation; local refs (a bare digest) to
bucket `local`, the digest and generation `0`. A size is read once per blob
per process, and only for raw responses: the original's size is on its asset.
`SqlConnectRepository.write_projection` runs after every successful
`CreateSpecimenV3` or `SaveSpecimenV3`, and after a replayed save.

- A write whose primary key already exists counts as written. Any other error
  stops the projection for that save, because later rows may depend on the
  failed one; it is logged with the specimen, run and operation, and the next
  save retries. The projection never fails a save: the snapshot is committed
  first.
- Each pass returns a `ProjectionResult`: `complete`, or the step it
  `stopped_at` (a connector operation, or `not_computed` when the rows could not
  be computed), never row data. After a run's final save, S3's lane calls
  `write_projection` again with bounded retries and backoff until a pass is
  complete. If none completes, the lane logs an error-level event with the
  specimen and run ids and leaves the disposition unchanged, and the next save
  catches up (coordinator ruling, 2026-09-24; DoD-4). S7's lab checks that SQL
  holds every artifact of each run. `SQLiteRepository` writes no normalized
  rows, so its passes are complete.
- The repository remembers the rows it wrote in this process, so a save sends
  only rows it has not sent. A new process sends each row once more, and the
  primary keys absorb the repeats.
- T2a writes stages 1 to 5: the original image, the profile version and the run
  (the trace id is recorded once when it appears), the regions, each reading
  with its raw response asset, and the reading comparisons. T2b adds the first
  pass, the harness, the queue decision and review decisions on S4's domain
  fields.
- `Checkpoint` rows are not written: the domain keeps no input digest per
  attempt. Attempts stay in the snapshot, and the harness's attempts are
  `ToolCall` rows.
- Without a blob store the pass is skipped and logged; the workflow supplies
  the store before its first save, and the next save catches up.
- The acceptance lab runs the same writer against the emulator
  (`--persistence sql-emulator`), so it sees the same rows as production.
  `SQLiteRepository` writes no normalized rows.

T2a mapping:

| Row | Mapping |
|---|---|
| `SourceAsset` original | id `Asset.id`; object from `Asset.blob_ref`; `mimeType`, `byteSize`, `width`, `height` from the asset; `acquisitionMethod` `intake`; `uploaderUid` `Asset.uploader` |
| `ProfileVersion` | `Run.profile.id` and `.version`; `configObject` the canonical JSON of `Run.profile_snapshot`; `configSha256` `Run.dependencies["profile_snapshot_sha256"]` |
| `PipelineRun` | id `Run.id`; `supersedesRunId` the previous run's id; `pinnedVersions` the profile's key, version, registry version and digest, its routes, schema and policy versions, its segmentation settings, and `Run.dependencies`; `inputSha256` the original's SHA-256; `traceId` `Run.trace_id` |
| `LabelRegion` | id `region/{run}/{Region.id}` (section 5); `domainRegionId` `Region.id`; `sourceAssetId` the original; `geometry` `{x, y, width, height, rotation_quarter_turns, pixel_basis}`; `ordinal` `Region.order`; `regionType` `label`; `segmentationVersion` `{method}:{version}` |
| `SourceAsset` raw response | id `asset/{specimen}/{bucket}/{object}/{generation}`, so byte-identical responses of two specimens are two rows of one stored object; kind `raw_response`, `application/json`, no dimensions, `acquisitionMethod` `model_response`, `uploaderUid` the writing actor |
| `ModelObservation` reading | id `Observation.id`; `regionId` the region row's id, while `stepKey` keeps the domain region id; `modelVersion` `model_id`; `parameters` `{model_settings, provider_model_id, input_tokens, output_tokens, latency_seconds, latency_basis}`; `outcome` `completion_state`, else `finish_state`; `independent` true; `routeId`; `unreadableSpans` |
| `ReadingComparison` | for a region's transcript with exactly two readings and an alignment algorithm; `regionId` the region row's id; readings in the fixed id order (section 3.1); `lengthBasis` the longer literal's length, at least 1; `editDistance` `ratio × lengthBasis`, rounded |
