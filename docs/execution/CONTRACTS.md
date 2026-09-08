# Application contracts v0.1

Status: preliminary integration contract, 2026-09-07; baseline `82fd60e`.
Owner: architecture task. Backend owns executable schemas and API; data owns SQL
mapping; Flutter consumes the wire contract. Changes to names or semantics must
be sent to the coordinator before dependent implementation. This document is a
specification, not evidence that endpoints or cloud resources exist.

## Common wire rules

Use JSON with snake_case keys, UTF-8, UTC RFC3339 timestamps, opaque UUID string
IDs and integer `revision` values. `/v1` is the application API prefix. All
resource IDs are tenant-scoped; the server derives identity from a verified
Firebase ID token and checks current organization and collection membership on
every operation. Never trust role, actor, organization or collection supplied
by a client without authorization. Production verifies issuer, audience, expiry,
signature and configured App Check policy. Emulator identity is permitted only
in an explicit local mode, never as a fallback for failed production auth.

Requests use `Authorization: Bearer <Firebase ID token>`. Mutating requests use
`Idempotency-Key`; editing existing resources also supplies `expected_revision`.
Persist idempotency scope `(organization_id, actor_id, operation, key)`, canonical
request digest and response. Same key/same payload returns the original result;
same key/different payload returns 409. Concurrent writes compare-and-swap the
revision in the same transaction as their append-only decision and audit event.
A stale revision returns 409 with current revision and no partial mutation.

Errors: `{error: {code, category, message, retryable, request_id, details}}`.
Categories: `input`, `authorization`, `conflict`, `operational`, `policy`.
Use 400 malformed input, 401 invalid identity, 403 prohibited action, 404 missing
or intentionally concealed resource, 409 conflict, 413 size, 415 format, 422
semantic validation, 429 throttling, 503 missing runtime/provider availability.
Details must contain no secrets, private cross-tenant identifiers or signed URLs.
Paginated reads use `{items, next_cursor}`; cursors bind authorized scope and
filters. Clients ignore additive optional fields, but unknown disposition or
policy values render as unsupported and cannot enable a decision action.

## Client API surface

The organization prefix below is `/v1/organizations/{organization_id}`. All
collection IDs are validated under that organization. Reads return `revision`
where a later write uses optimistic concurrency.

| Method and relative path | Input | Result and authorization |
|---|---|---|
| GET `/v1/session` | verified identity | user ID, authorized organizations/collections and permissions; `mode` (`synthetic`, `emulator`, `production`) and runtime readiness blockers |
| GET `/collections` | optional parent ID | configurable collection nodes and eligible published profiles; viewer |
| POST `/batches` | collection_id, display_name, acquisition_method, sensitive (strict boolean, default true) | batch_id and item manifest; operator; sensitive permission when true |
| POST `/batches/{batch_id}/items` | client_item_id, filename, declared MIME/bytes/dimensions, sha256, sensitive (strict boolean, default true; must match batch) | stable specimen_id, asset_id, upload_id, manifest state and duplicate reference if authorized; operator |
| GET `/batches/{batch_id}` | cursor | itemized manifest and accepted/duplicate/invalid/uploading/failed states |
| GET `/uploads/{upload_id}` | none | authoritative upload offset, revision and expiry; owner/scoped operator |
| PUT `/uploads/{upload_id}/content` | binary bytes and `Upload-Offset` header | updated offset/revision; authenticated scoped operator; backend-mediated transport |
| POST `/uploads/{upload_id}/resume` | expected_revision | refreshed scoped resumable upload instructions; stable asset/specimen IDs |
| POST `/uploads/{upload_id}/complete` | expected_revision, storage generation | server verifies actual bytes/hash/type/dimensions and commits immutable asset; idempotent ingestion enqueue |
| GET `/specimens` | collection_id, batch_id, state, disposition, date bounds, uploader, score band, issue, profile_version, cursor | authorized specimen summaries |
| GET `/specimens/{specimen_id}` | none | current summary plus pinned active/latest run, record version and available actions |
| GET `/specimens/{specimen_id}/workspace` | optional run_id | regions, independent observations, transcription versions, candidates, evidence, validations, decisions, disposition and audit timeline; large raw payloads remain references |
| GET `/assets/{asset_id}/access` | purpose | authenticated API read URL and immutable asset metadata; current scoped membership, plus sensitive-image permission for sensitive or legacy-unknown assets |
| POST `/specimens/{specimen_id}/classification` | expected_revision, collection_id, reason | new pinned run and superseded downstream references; reviewer or permitted operator |
| POST `/specimens/{specimen_id}/regions` | expected_revision, base_run_id, region edits, reason | new region-set version plus invalidation summary; reviewer |
| POST `/specimens/{specimen_id}/decisions` | expected_revision, base_record_version_id, kind, target_id, before, after, reason, evidence_ids | append-only decision, new revision and dependent revalidation state; reviewer |
| POST `/runs/{run_id}/actions` | expected_revision, action (`retry`, `resume`, `pause`, `cancel`, `reprocess`), reason | authorized transition and current status; operator/admin per action |
| GET `/runs/{run_id}/events` | after_sequence, limit | ordered persisted timeline, next retry and actionable blocker; polling is sufficient for first implementation |

The API must not accept a client-supplied final disposition as authoritative.
A review decision can request re-evaluation; only the deterministic policy
commits a final outcome. Export and EMu write endpoints are out of scope.
Backend and Flutter agreed on authenticated binary PUT to the content route with
`Upload-Offset`; GET reports authoritative offset and completion supplies
`expected_revision`. Direct Storage client writes are denied. Persist the session
and verified offset so a restarted client can resume the same IDs. Duplicate
chunks must either return verified progress or a conflict requiring GET; never
append repeated bytes. Backend must publish exact chunk response and error
examples before Flutter completes wiring. Never put permanent download tokens
in persisted evidence or telemetry.

### Explicit intake sensitivity

New batch and item requests accept `sensitive: true` or `sensitive: false` only.
Omission defaults to true; numbers, strings and null are invalid. The client
defaults to Sensitive and submits the user's selection on both creation requests.
An item must match its retained batch, and resume/retry never reclassifies an
existing upload. A non-sensitive member must explicitly select false before
creation; membership never supplies that declaration automatically.

The upload carries the declaration into `asset.sensitive`. Missing legacy
values always mean sensitive. True is omitted from canonical payloads to retain
old request and snapshot digests; false is explicit in payloads and responses.
Source classification may be promoted to sensitive by an authorized writer,
but sensitive or unknown history cannot be downgraded. There is no public
reclassification endpoint in this change.

Workspace, source/view pixels, history, active graphs and retained artifacts
recheck current scope membership and sensitivity. A historical snapshot's own
sensitive/unknown classification still denies its content even when the current
record says false. Membership revocation never grants access through a saved
URL, cached list result, revision, upload handle or idempotency receipt. These
rules do not grant institutional approval, human approval or clearance.

The SQL repository uses `GetDocumentV2`, `ListDocumentPageV2`,
`CreateDocumentV2` and `SaveDocumentV2`. Writes include required boolean
`sensitive`; list pages include `includeSensitive` from fresh scoped membership.
Returned column and payload classifications must match (missing legacy payload
field means true). The connector retains active scope, role, CAS and creator-only
protections for `pilot_launch` and `worker_cursor`, disallows listing control
documents, and atomically rejects a sensitivity downgrade. Older operations
cannot bypass these protections. V3 specimen writes bind the actual asset
classification to the persisted column.

`PilotLaunch.sensitive` likewise defaults to true and is omitted in that case
to preserve existing launch digests. An explicitly false launch can bind only
records whose assets are explicitly false; it creates a non-sensitive control
ledger. A changed launch declaration cannot reset or downgrade an existing
ledger. Actual source classification must be verified before materializing this
private launch; the runtime does not infer that the frozen ten are non-sensitive.

## Domain records

Every owned record carries organization_id, collection_id (when applicable),
created_at and immutable identifier. References must remain within authorized
scope; source references are IDs plus content digests, not transient URLs.

| Record | Required content |
|---|---|
| SourceAsset | asset_id, specimen_id, original_asset_id for derivatives, storage bucket/key/generation, sha256, verified MIME, byte_count, width, height, acquisition_method, uploader_id, acquired_at, received_at, derivative transform/version |
| Specimen | specimen_id, batch_id, source_asset_id, classification candidates and selection, active_run_id, latest_record_version_id, revision, sensitivity policy |
| PipelineRun | run_id, specimen_id, predecessor_run_id, status, stage, pinned profile/schema/prompt/model/provider/code/adapter/policy versions, input_digest, budgets, checkpoint revision, blocker, timestamps |
| LabelRegion | region_id, region_set_version, run_id, source_asset_id, label type/order, geometry, mask/crop asset IDs, segmentation model revision/parameters, provenance, supersedes_region_id |
| ModelObservation | observation_id, run_id, region_id, independence_group, route/model/provider/revision, prompt resolved version/digest, parameters, input asset IDs/digests, raw_response_asset_id/digest, parsed literal output, start/end times, latency, usage, finish state/error |
| TranscriptionVersion | transcription_id, run_id, region_id, verbatim_text, lines, spans with source geometry and observation/span references, alternatives, unresolved spans, adjudicator provenance |
| FieldCandidate | candidate_id, field_key, typed value, value_state, derivation (`literal`, `parsed`, `normalized`, `lookup`, `human`), source transcription/span IDs, parent candidate IDs, evidence IDs, transform/version, uncertainty |
| EvidenceItem | evidence_id, lookup_id or source observation, source/adapter/version, exact query digest and retained query reference, retrieved_at, source release/checklist, response asset/digest, locator/excerpt, matched identifiers, license/usage policy, support or contradiction |
| RecordVersion | record_version_id, run_id, predecessor ID, field states and selected candidate IDs, validation snapshot, immutable disposition decision if final |
| ReviewDecision | decision_id, actor_id from server, action/target, before/after, reason, source/evidence references, base revision, resulting revision, timestamp |
| ValidationFinding | finding_id, rule_id/version, severity (`hard`, `warning`, `info`), outcome (`pass`, `fail`, `unresolved`, `not_applicable`), field/region references, reason_code, evidence IDs |
| DispositionDecision | disposition, policy_version, reason_codes, summary, passed/failed gates, outstanding issues, evidence IDs, attempts and retry_eligibility for Deferred, actor/required approval evidence |

Geometry uses the unmodified original raster's pixel space: origin top-left,
x rightward, y downward, bbox `[x_min,y_min,x_max,y_max]` with exclusive upper
bounds. Coordinates must lie within original dimensions. Polygons and masks
record the same reference dimensions. EXIF orientation, crop rotation and preview
transforms are stored explicitly with invertible source-to-view mapping; no
implicit coordinate switch after orientation correction. Correction appends a
new region set; deletes are tombstones, not erasure of historical geometry.

Existing `LiteralTranscription` (`verbatim_text`, `lines`, `unreadable_spans`)
remains supported. Wrap it in immutable observation provenance; do not replace
its exact line-reconstruction invariant. Extend span evidence additively.
Persist raw provider envelopes as well as parsed Pydantic output; existing
`LiteralTranscriptionRun` alone is insufficient raw-response preservation.

## States, mandatory values and clearance

Run status: `pending`, `running`, `waiting_for_review`, `retry_scheduled`,
`paused`, `cancelled`, `processing_blocked`, `completed`, `superseded`.
Stage: `ingest`, `quality_check`, `classify`, `segment`, `transcribe`,
`adjudicate`, `parse`, `plan`, `lookup`, `resolve`, `normalize`, `validate`,
`finalize`. Waiting for classification or segmentation is a processing state;
a final `needs_human_review` requires configured attempts and validations to
have finished or been explicitly deemed inapplicable by policy.

Exactly three final wire values: `cleared`, `needs_human_review`, `deferred`.
An unfinished run has `disposition: null`. Historical completed runs retain their
outcomes when a new run starts. One active run per specimen is enforced in storage.

Field value_state: `supported`, `unknown`, `unreadable`, `not_present`,
`not_applicable`, `ambiguous`, `unresolved`. Only `supported` with a non-empty,
well-typed, evidenced value can satisfy an Insects mandatory field. Null and
placeholder strings never satisfy it. Operational lookup failures are stored as
execution outcomes, not disguised field absence. Unknown semantics fail the
relevant policy gate even if literal characters can be transcribed.

The 20 Insects keys are `fmnh_ins_number`, `collection_code`, `country`,
`province_state`, `county`, `city`, `precise_location`, `elevation_from_m`,
`elevation_to_m`, `elevation_from_ft`, `elevation_to_ft`, `habitat`,
`collection_method`, `date_visited_from`, `date_visited_to`, `collectors`,
`verbatim_dts`, `taxon`, `identified_by_irn`, `date_identified`.
These are internal PRD-derived keys, not approved EMu export mappings.
Preserve partial-date precision and literal units; do not invent missing dates,
endpoints or converted elevations pending policy. Identified-by identity is
`{source_system, tenant, environment, module: "eparties", irn}` with confirmed
authority evidence. A catalogue IRN or person-name search snippet is insufficient.

Clearance requires label coverage, two independent configured observations per
required label, completed adjudication, resolved critical disagreements, all
mandatory values, valid schema, full provenance, no unresolved hard findings,
approved semantics/policy and any required human approval. Risk scores cannot
override these gates. Deferred requires documented capability limitation,
exhausted viable approved attempts and retry eligibility. Missing configuration,
429, timeout, invalid credentials, outage, budget exhaustion and code error are
operational blocks. No reviewer action may simply waive missing evidence.

## Application-owned processing interfaces

`HarnessRunner.run_phase(snapshot, profile, phase, transcript_refs, tool_registry,
budget, prior_checkpoint) -> PhaseResult` returns candidates, evidence references,
validation findings, unresolved issues, typed tool outcomes, trace reference,
checkpoint and proposed disposition. Input is an immutable authorized snapshot.
Only named versioned modules and allow-listed tools run; no arbitrary code or
network tools arrive from model output. Phases are parse, plan, lookup, resolve,
normalize, validate, finalize; skips need a persisted applicability decision.

`LookupAdapter.execute(request, context) -> LookupResult` has outcome:
`success`, `no_match`, `ambiguous`, `empty_response`, `rate_limited`,
`timeout`, `authentication_error`, `authorization_error`, `provider_error`,
`malformed_response`, `policy_blocked`. Include candidates, evidence reference,
attempt, retry_after and sanitized error. Cache key includes provider, operation,
complete normalized query, checklist/release and adapter version. Empty, ambiguous
and error entries must not collapse into success/no-match.

`CheckpointStore.commit_step(run_id, expected_revision, step_key, input_digest,
output_refs, state, outbox_events) -> Checkpoint` atomically records logical result,
status and dispatch intent. Unique `(run_id, step_key, input_digest)` prevents
duplicate logical observations/tool results. Worker claims use leases and fencing
revisions; an expired worker cannot overwrite a newer result. Persist intent
before external effects and result afterward. If a provider cannot deduplicate
an ambiguous lost response, record outcome-unknown and reconcile or explicitly
retry with duplicate-cost risk; do not claim universal exactly-once external calls.

`WorkflowEngine.start/signal/cancel/query/replay` passes run IDs and compact
references. A signal carries decision_id and expected checkpoint revision;
duplicate or stale signals do not repeat effects. A local checkpoint runner can
prove application behavior but does not select Temporal or Google Workflows.
Both must pass the same comparative spike before production selection.

`EvidenceStore.put_immutable(payload, metadata) -> AssetRef` verifies the digest
and immutable object generation before a relational reference is committed.
Object write and SQL commit are not one transaction: stage object, verify, then
commit reference/outbox; reconcile orphan objects under retention policy. Never
delete retained evidence to compensate a failed SQL write.

## Persistence and compatibility handoff

SQL Connect/Cloud SQL owns memberships, collection/profile versions, manifests,
specimens/runs, observations, evidence references, decisions and audit history.
Cloud Storage owns bytes and large raw envelopes. Backend coordinates privileged
multi-entity mutations through reviewed server operations; direct client SQL
writes to final state, raw observations or audit records are forbidden. Data
owner must validate actual connector transaction, authorization and constraint
capabilities; do not assume an in-memory repository proves SQL behavior.

Required transactional boundaries: upload completion plus enqueue; claim/fenced
checkpoint plus result/outbox; correction plus successor version/invalidation;
final gate evaluation against revision plus record/disposition/audit commit.
Auth changes and review edits must be rechecked at commit, not only on fetch.

Version 0.1 is an early stable proposal. Owners must send concrete deviations to
the coordinator and document the agreed implementation wire shape here before
integration. No production resource or institutional approval is implied.

## Integration decision ledger

| Decision | Status and owner |
|---|---|
| Snake-case wire, organization-scoped API, optimistic revision and idempotency | Architecture proposal sent to backend/Flutter; exact executable serializer fixture pending backend |
| Idempotency-Key header; expected_revision request body; raw single-resource JSON and paged items/next_cursor | Proposed exact convention; backend confirmation pending |
| Backend-only SQL operations, membership checks inside CAS, normalized references plus immutable snapshots | Accepted architecture/data boundary; operation names/schema compilation and runtime tests owned by data/backend |
| Direct Storage client access denied; scoped backend upload/download | Accepted by data and Flutter; no direct SDK writes |
| Resumable binary transport | Backend proposed and Flutter accepted authenticated PUT `/uploads/{id}/content`, `Upload-Offset` plus raw bytes; GET offset, completion expected_revision; exact response serializer fixture remains backend-owned |
| Hosting remains static-only; no implicit runtime/data delivery | Release/integration owner acknowledged contract; no wire deviations |

For each pending row, the owner must publish an exact response example/schema
and the matching operation/test reference. A planned convention is not evidence
of a working serializer. Compatibility aliases, if needed, must be explicit and
tested; never let Flutter silently guess both shapes.


Data owner confirmed operation names `GetSpecimen`, `GetSnapshot`,
`ListSpecimens`, `Memberships`, `GetReceipt`, `CreateSpecimen`, `SaveSpecimen` in
`dataconnect/connector/operations.gql`. Architect inspected that in-progress source
read-only; compilation success is reported by the data owner, not independently
reproduced here. SQL operation variables are camelCase while HTTP remains
snake_case; the backend adapter owns explicit translation. `snapshot: Any` holds
backend-validated domain JSON with a proposed 256 KiB maximum, version and SHA-256;
raw payloads remain object references. Aggregate revision fences checkpoint
writes. Separate batch/upload document CAS operations are still data-owned work.

Idempotency persistence may further scope receipts by collection. The backend
must enforce the documented request scope consistently and avoid cross-collection
response replay. Membership lists must intersect active organization membership
with collection membership; a collection grant alone cannot retain access after
organization revocation. Backend enforces action-specific role permissions in
addition to connector membership/CAS checks. Snapshot bounds and operation names
must be exercised through the actual adapter before integration acceptance.


### In-progress serializer reconciliation

An early read-only review of backend `application/domain.py` identified the
following compact internal representation. These are not yet a frozen HTTP
fixture. Backend and Flutter were notified together before integration.

| Conceptual contract | Backend internal shape | Required wire resolution |
|---|---|---|
| specimen_id, revision, organization/collection, active run | `id`, `version`, `scope`, `run` | Explicit serializer maps HTTP revision to aggregate version; publish exact session/workspace fixture |
| asset_id, immutable storage reference, byte_count | `id`, `blob_ref`, `size_bytes` | Document compact aliases or translate once in backend; immutable digest/reference rules unchanged |
| original-pixel bbox min/max | `x`, `y`, `width`, `height` | Equivalent bbox is `[x,y,x+width,y+height]`; do not interpret width as x_max |
| lookup ambiguous match | `status: ambiguous` | Adopt `ambiguous` as canonical wire spelling, consistent with existing GBIF.md; conceptual meaning unchanged |
| unresolved field | no distinct unresolved enum in early model | `unknown`/`ambiguous` with explicit reason may represent unresolved processing; never satisfy supported mandatory value |
| valid empty lookup result | early OPERATIONAL set includes empty_response | Backend notified to distinguish valid empty response from malformed provider output; PRD §15 remains authoritative |

Conceptual table names above describe evidence obligations, not an instruction
to duplicate Python types or invent unsupported fields in Flutter. Final wire
examples must derive from the executable backend schema and be tested through
both serializers. Unimplemented provenance obligations remain acceptance gaps,
not waived by compact serialization. The data-owner snapshot bound is provisional
until the adapter enforces it. No later contract delta may weaken clearance or
turn institutional unknowns into approved values.

## Canonical wire freeze: v0.1 integration amendment

This section supersedes the pending serializer choices above. The architect
inspected backend `application/api.py`'s `summary`, `workspace`, request models
and route functions and adopts those explicit HTTP serializers. Do not expose
the compact internal Specimen object directly or have Flutter guess aliases.
Backend must retain a shared generated fixture and Flutter must test that same
fixture before integration acceptance. Source inspection is not HTTP execution
proof; the backend implementation is still in progress.

| Surface | Canonical shape |
|---|---|
| Session | `user_id`, `mode`, `memberships: [{organization_id, collection_id, role, can_view_sensitive}]`, `runtime_blockers: [string]`, `synthetic_token_required: boolean` |
| Summary | `specimen_id`, `asset_id`, `organization_id`, `collection_id`, `revision`, `batch_id`, `filename`, `created_at`, `active_run_id`, `record_version_id`, `status`, `stage`, `disposition`, `reason_codes`, `blocker`, `profile_id`, `profile_version`, `synthetic`, `available_actions` |
| Workspace | Summary fields plus singular `asset`, `run`, `regions`, `observations`, `transcriptions`, keyed-object `fields`, `evidence`, `validations`, `decisions`, `events` |
| Region | Internal `id`, `asset_id`, `x`, `y`, `width`, `height`, `order`, `method`, `version`, crop/mask references, plus wire `region_id` and `[x,y,x+width,y+height]` `bbox` |
| Observation | Internal provenance fields plus wire `observation_id` and `verbatim_text`; literal_text is an internal-compatible alias |
| Field | Fields object keyed by mandatory key; each value has `value_state`, `literal`, `parsed`, `normalized`, `authority_id`, `evidence_ids`, `reason`; internal-compatible `state` may also appear |
| Evidence | Evidence object plus `evidence_id`; image and raw references remain immutable IDs/digests |
| Validation | `validations` array, not validation_findings; each has rule_id, severity, outcome, reason_code |
| Timeline | `events` with monotonic sequence; decisions is the review-event subset; no audit_events alias |
| Batch create input | `collection_id`, `display_name`, `acquisition_method` (default files), `sensitive` (strict boolean, default true) |
| Item create input | `client_item_id`, `filename`, `media_type`, `size_bytes`, `width`, `height`, `sha256`, `sensitive` (strict boolean, default true; matches retained batch) |
| Item/upload result | Input metadata plus upload_id, asset_id, specimen_id, batch_id, collection_id, revision, state, offset, upload_url, upload_method; duplicate_specimen_id only for authorized duplicates |
| Upload content | Authenticated PUT with Upload-Offset and up to 4 MiB binary bytes; returns upload result with new offset/revision. Same retained offset/hash replay returns current result; otherwise 409 and GET to reconcile |
| Complete | `{expected_revision, reason}` plus Idempotency-Key; returns Summary. Storage generation is server-owned in this transport, not client input |
| Review request | expected_revision, base_record_version_id, kind, target_id, before, after, reason, evidence_ids; field/transcription/approve/coverage kinds; returns Workspace |
| Region replacement request | expected_revision, base_run_id, regions array, reason; returns Workspace with successor run |
| Asset access | `{url, requires_authorization: true, asset}`; relative URL is authenticated API content route; Flutter fetches bytes with bearer credentials, not unauthenticated Image.network |

`revision` explicitly maps internal `Specimen.version`. `record_version_id` is
currently the opaque token `<run_id>:<revision>`; clients preserve it unchanged.
Source asset uses `id`, `media_type`, `size_bytes`, `blob_ref`, hash/dimensions and
uploader metadata inside the singular `asset` field. Do not infer an assets array.
Lookup ambiguity is `ambiguous`. Scope IDs stay UUID strings; backend must
normalize SQL's hyphenless UUID responses before comparison/HTTP serialization.

Authenticated content endpoints are an accepted private-image alternative to
short-lived signed URLs. Authorization is rechecked per read, with no-store
responses; Flutter must fetch bytes without leaking bearer headers to unrelated
origins. The backend's current diagnostic generic errors need custom handlers
for validation/401 to satisfy the common error envelope; test all paths rather
than assuming the generic exception handler wraps framework-generated errors.

Current code acceptance gaps remain separate: not every requested search filter
is implemented; classification cannot yet select a different published profile;
profile and runtime readiness are not fully configurable; raw schema does not
supply every provenance obligation; history growth needs pagination; all supplied
available_actions must be filtered by actual actor permission. These are concrete
backend/QA obligations, not wire aliases or newly waived requirements.

Backend owner subsequently confirmed the outer projection above as canonical and
published `docs/execution/backend-openapi.json` and
`docs/execution/backend-wire-examples.json` in its implementation worktree. The
architect read the latter: it contains a synthetic session example and generated
item/decision request schemas; workspace/upload are still descriptive notes.
Backend must add actual generated response fixtures from the HTTP journey for
Flutter's identical-fixture test. That test requirement remains open; the wire
naming decision is settled. Backend also confirmed adding `unresolved` as a field
state, correcting valid-empty lookup semantics and adopting the 256 KiB snapshot
bound. Independent QA must verify these changes on the committed implementation.

Current implementation fixture locations (read-only cross-task references):
`/Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app/docs/execution/backend-openapi.json`
and
`/Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app/docs/execution/backend-wire-examples.json`.
Integration retains the files under repository-relative docs/execution paths so
the contract survives removal of temporary worktrees.

### Response-fixture milestone

Backend subsequently generated actual TestClient HTTP journey fixtures in
`backend-wire-examples.json`: session, batch_response, item_request, item_response,
upload_response, complete_response, workspace_response, decision_request and
decision_response. Architecture independently parsed the updated JSON and verified
all nine objects and canonical workspace keys. The backend reports a synthetic
Cleared journey without direct database edits; architecture did not independently
rerun that journey. Missing response-fixture generation is resolved. Flutter's
identical-fixture decode test and independent integrated HTTP/SQL acceptance
remain required, with exact candidate SHA and test evidence in their reports.

## Assembly fixture audit milestone

Architecture read BACKEND_ASSEMBLY.md and the frozen
backend-next-wire-examples.json in backend worktree 3782, independently recomputed
its SHA-256 and matched the digest supplied in the backend handoff. Inspected
current API source for phase, authority, raw observation, reading metadata and
disagreement readers. This is a bounded source/fixture audit during the final
gate, not independent HTTP execution or whole-product acceptance.

Canonical outer workspace fields remain compatible. Seven phase entries,
authority result metadata, risk/unmeasured structure and search persistence/domain
timestamps are present. Authority selection uses kind authority_resolution,
target_id equal to after.field_key, and after.tool_id/identifier naming one
retained candidate. Artifact readers take optional exact revision, authorize via
current specimen history access and resolve only retained artifact references.
No wire-format blocker was found in the inspected surfaces.

New artifact paths below are under the existing scoped specimen path:
`/phases/{phase}`, `/authority-results/{tool_id}` and its `/raw` suffix with
field_key when needed, `/observations/{observation_id}/raw`,
`/observations/{observation_id}/metadata`, `/disagreements/{region_id}`.
Clients preserve explicit Unicode offset conventions and current historical
revision. Raw text is not executable HTML. New fixture standalone Unicode and
bounded examples remain labelled separately from actual application responses.

Limits relayed to owners: the 1 MiB raw response check follows blob retrieval, so
it is not a read-memory limit. Default PNG server preflight can report
memory_limit_unavailable; changing image format does not repair that runtime
condition, and preflight refusal must not be confused with the independent
validated JPEG/PNG/TIFF intake capability. Optional codecs still are not full
intake/worker support. Current model adapters supply no language/script declaration;
unknown metadata is honest but does not complete TRN-006. Shared circuits,
SAM3/auth deadline proof, oversized active evidence graph and duplicate precheck
scale remain explicitly open in BACKEND_ASSEMBLY.md. Flutter fixture parity and
independent integrated SQL/HTTP acceptance are still required.
