# Specimen Digitization — Product Requirements Document

| Document field | Value |
|---|---|
| Status | Draft for product review |
| Version | 0.6 |
| Date | 2026-09-07 |
| Working product name | Specimen Digitization |
| Product owner | TBD |
| Technical owner | TBD |

## 1. Executive summary

Specimen Digitization will turn photographs of natural-history museum specimens and their labels into traceable, reviewable digital records. It will support botany, zoology, geology, and anthropology, with collection- and subcollection-specific processing profiles.

The product will use a responsive Flutter client for capture, upload, monitoring, and review. Firebase Authentication, Firebase SQL Connect backed by Cloud SQL for PostgreSQL, and Cloud Storage will provide the initial application platform. Long-running image, model, and agent workflows will run in a separate backend processing plane so jobs can be checkpointed, retried, audited, and resumed without depending on an open client session.

The first pilot will use the Field Museum Insects subcollection. Its initial profile, mandatory record fields, and collection-manager source policy are defined in section 12.4.

The first build ends at a persisted, reviewable final queue disposition inside this application. EMu projection, versioned EMu export snapshots, and writes to EMu are explicitly deferred until after the application works end-to-end and the production pilot has validated record quality and workflow usability.

For each submitted photograph, the platform will:

1. Create a specimen-centered processing record and preserve the original image.
2. Predict the relevant collection and subcollection, while allowing a user to correct the prediction.
3. Select a versioned collection profile containing the right prompts, schemas, models, tools, reference sources, validation rules, and clearance policy.
4. Use SAM 3 to identify and segment labels and other relevant regions.
5. Ask multiple vision models to independently transcribe every detected label.
6. Preserve each model's raw output, measure disagreement, and produce an adjudicated transcription without concealing uncertainty.
7. Run a modular agentic harness to extract fields, perform authoritative lookups, reason over historical and contextual information, normalize values, and validate the candidate record.
8. Route the specimen to exactly one final queue: **Cleared**, **Needs human review**, or **Deferred**. Operationally failed or interrupted work remains in a recoverable processing state and is not misclassified as a completed outcome.

The system must never treat a confidence score as proof of correctness. A record is cleared only when its profile-specific evidence, coverage, validation, provenance, and disagreement-resolution gates have all passed.

## 2. Product vision

Enable museums to digitize heterogeneous specimen collections at scale while preserving the evidentiary relationship between the source image, literal label text, interpreted fields, external authority data, model decisions, and human review.

The platform should automate routine work aggressively, abstain when it cannot support a conclusion, and make difficult cases efficient for a domain expert to resolve.

## 3. Problem statement

Natural-history labels vary by discipline, era, language, handwriting, layout, preservation condition, and institutional convention. A single general-purpose OCR or vision prompt is not sufficient. Correct interpretation may require collection-specific schemas and reference sources, along with temporal reasoning about people, taxonomy, geography, political boundaries, historical spellings, and collecting practices.

Existing digitization workflows often lose one or more of the following:

- the exact wording and layout of a label;
- alternative model readings and the disagreement between them;
- the distinction between transcription and interpretation;
- evidence for an enriched or normalized value;
- a durable record of automated and human decisions;
- clear handling of source failures, rate limits, and unresolved ambiguity.

This product addresses those gaps through a configurable, specimen-centered pipeline with explicit evidence and review states.

## 4. Product principles

1. **Source first.** Preserve the original image and literal transcription. Normalization must never overwrite source text.
2. **One specimen, one traceable history.** Every crop, model result, lookup, transformation, retry, decision, and review action must link back to the specimen and pipeline run.
3. **Independent observations before consensus.** Vision models must produce their initial readings without seeing one another's outputs.
4. **Abstention is valid.** Unknown, unreadable, ambiguous, not applicable, no match, and operational failure are distinct states.
5. **Configuration over hard-coding.** Collection-specific behavior belongs in versioned profiles and harness modules.
6. **Human authority is explicit.** Users may correct classification, segmentation, transcription, and resolved fields; the system records who changed what and why.
7. **Scores support triage, not truth.** Agreement and quality scores prioritize work but do not independently clear a specimen.
8. **Durable execution.** Every processing step is idempotent, checkpointed, retryable where safe, and observable.
9. **Privacy and stewardship by default.** Sensitive locality, cultural, personal, and collection information is access-controlled and is not sent to an unapproved provider.
10. **Evaluation before scale.** New models, prompts, profiles, and rules are tested against versioned, representative evaluation sets before promotion.

## 5. Goals

### 5.1 Product goals

- Support image intake from device storage, folder-based batches, cloud URLs, and mobile/tablet camera capture.
- Classify a specimen into a configurable collection hierarchy and allow correction at any appropriate point.
- Select and version the correct processing profile for the chosen subcollection.
- Segment all visible labels and preserve their coordinates, masks, crops, and relationship to the original image.
- Generate multiple independent, span-aware label transcriptions and retain every raw response.
- Quantify and explain disagreement at the label, field, and specimen levels.
- Transform raw transcriptions into structured candidate records without erasing ambiguity or provenance.
- Enrich and validate records through modular data-source adapters and collection-specific reasoning tools.
- Give reviewers a single workspace in which source pixels, readings, evidence, proposed values, and validation issues are visible together.
- Route every fully attempted specimen to a clear final queue using versioned, inspectable rules.
- Support museum-funded provider access through bring-your-own-key (BYOK) for approved provider adapters, as well as a platform-managed default set of models.
- Produce schema-valid internal digital records and a complete audit package; downstream collection-system projection and export are later integrations.

### 5.2 Success outcomes

- Higher verified records per reviewer hour than the museum's current baseline.
- A lower critical-field error rate than a single-model transcription workflow.
- Complete provenance for every cleared field.
- No specimen enters Cleared with unresolved critical disagreements or validation failures.
- Operational failures are visible, recoverable, and never silently converted into data conclusions.
- Adding a new subcollection does not require changing the core workflow engine.

## 6. Non-goals for the initial product

- Replacing a museum's collection management system or becoming the authoritative accession ledger.
- Publishing specimen data directly to the public internet without a separate, approved release workflow.
- Automatically modifying an external system of record without explicit integration configuration, validation, and authorization.
- Training foundation models on museum data by default.
- Guaranteeing that every image can be cleared without human review.
- Treating multiple specimens in one photograph as a standard v1 workflow. The v1 default is one specimen digitization record per photograph; a user can reject or split exceptional images.
- Running large segmentation or vision models entirely on the capture device. On-device quality checks may be added, but authoritative processing is initially server-side.
- Using a single global schema, prompt, confidence threshold, or enrichment strategy for every collection.

## 7. Users and permissions

### 7.1 Primary users

**Digitization operator**

- Captures or uploads images.
- Supplies batch metadata.
- Confirms obvious classification suggestions.
- Monitors upload and processing problems.

**Collection reviewer / domain expert**

- Reviews label segmentation, competing readings, extracted fields, evidence, and validation issues.
- Resolves ambiguity and records a reason for consequential decisions.
- Clears records when authorized by policy.

**Collection manager**

- Defines required fields and review policy.
- Approves collection profiles and evaluation sets.
- Monitors quality, throughput, queue aging, and recurring failure patterns.

**System administrator**

- Manages organizations, users, roles, provider connections, data retention, and platform-level settings.
- Can disable compromised provider credentials and pause affected jobs.

**Profile developer / data steward**

- Creates and tests schemas, prompts, lookup adapters, validators, crosswalks, and clearance policies in a non-production environment.
- Promotes signed profile versions after evaluation and approval.

### 7.2 Access model

The system must support organization and collection scopes. A user may have different roles in different collections. Permissions must be enforced by backend rules, not only hidden in the interface.

At minimum, permissions cover:

- view source images and sensitive fields;
- upload and cancel jobs;
- correct classification and segmentation;
- edit transcription and structured values;
- make final review decisions;
- export records;
- configure profiles and data sources;
- manage users, credentials, retention, and audit access.

## 8. Core concepts and terminology

| Term | Definition |
|---|---|
| Specimen record | The primary unit of processing and review, normally anchored to one submitted photograph in v1. |
| Source asset | An immutable original image plus its checksum, acquisition metadata, and storage pointer. |
| Collection taxonomy | The configurable hierarchy of collection, subcollection, and optional deeper specialization. |
| Collection profile | A versioned bundle of schema, prompts, model policy, segmentation settings, tools, sources, validators, scoring policy, and clearance gates. |
| Pipeline run | One immutable-version attempt to process a specimen with a specific profile and dependency set. |
| Label region | A SAM 3 mask/bounding geometry and derived crop representing a label or other configured region. |
| Model observation | One model's immutable raw transcription or classification output, including model and prompt provenance. |
| Literal transcription | The best-supported reading of visible text, retaining line breaks, spelling, abbreviations, and unreadable spans. |
| Field candidate | A possible structured value derived from text, context, a lookup, or a human action. |
| Resolved value | The currently selected field value, linked to its source candidates, evidence, rule or actor, and confidence state. |
| Evidence item | A source locator and captured support for a claim, including source, query, time, response digest, and relevant excerpt or identifiers. |
| Harness | A collection-specific, tool-using workflow that parses, looks up, reasons, normalizes, validates, and proposes a final record. |
| Queue disposition | Cleared, Needs human review, or Deferred, assigned only after the configured attempts and validation steps finish. |

## 9. Scope and key user journeys

### 9.1 Capture and batch upload

1. An operator chooses camera, files, folder, or cloud URL.
2. The client performs basic file, image, and quality checks.
3. The backend creates stable specimen and asset identifiers before processing.
4. Uploads survive intermittent connectivity and can resume without creating duplicate jobs.
5. The operator sees an itemized manifest with accepted, duplicate, invalid, uploading, and failed items.
6. Each accepted photograph becomes a specimen record and an asynchronous processing job.

### 9.2 Automated processing

1. The platform evaluates image quality and predicts collection/subcollection candidates.
2. It selects a profile or pauses for classification review when policy requires.
3. It segments relevant regions and transcribes all label regions independently with the configured models.
4. It calculates disagreements and performs adjudication.
5. The harness extracts fields, performs lookups, proposes normalized values, and executes deterministic validations.
6. The clearance policy selects a final queue or identifies an operational block that must be recovered first.

### 9.3 Human review

1. A reviewer opens a specimen from a prioritized queue.
2. The workbench shows the original image, label overlays/crops, model readings, differences, field candidates, lookup evidence, and validation messages.
3. The reviewer corrects or confirms values, adds missing regions if needed, and records decisions.
4. Relevant downstream stages rerun without discarding prior versions.
5. The specimen is re-evaluated against the same versioned clearance policy.

### 9.4 Deferred reprocessing

1. A deferred record contains a precise machine-capability reason and the model/profile versions already attempted.
2. An administrator or scheduled campaign selects records eligible for a newer model or profile.
3. The platform starts a new pipeline run while preserving the previous result.
4. The new run is compared with the former run and routed normally.

### 9.5 Later-phase external integration

External-system projection is not part of the initial end-to-end application milestone. After the production pilot validates the internal record and queue workflow, an authorized user may select cleared records for an approved target schema. That later integration must validate the exact export set, create a manifest, preserve provenance and warnings, and remain deterministic and idempotent.

## 10. End-to-end lifecycle

### 10.1 Processing states

```text
Draft / Capturing
  -> Uploading
  -> Ingested
  -> Quality check
  -> Classifying
  -> [Classification review when required]
  -> Segmenting
  -> [Segmentation review when required]
  -> Transcribing
  -> Adjudicating
  -> Extracting and enriching
  -> Validating
  -> Finalizing
  -> Cleared | Needs human review | Deferred
```

Any processing stage may enter `Retry scheduled`, `Paused`, `Cancelled`, or `Processing blocked`. Those are operational states, not final data-quality queues. Once the cause is resolved, the run resumes from a durable checkpoint.

### 10.2 Lifecycle invariants

- A specimen has no more than one active pipeline run at a time.
- A run pins the exact profile, prompt, schema, model policy, code, and data-source adapter versions used.
- Raw source assets and raw model observations are immutable. Corrections create new versions.
- User classification changes invalidate all downstream results whose behavior depended on the former profile.
- A retry of the same step and inputs is idempotent.
- Every final disposition includes machine-readable reason codes and a human-readable explanation.
- A record cannot be Deferred for a temporary operational failure such as a rate limit, invalid credential, timeout, or platform outage.
- A record cannot be Cleared solely because its composite score crosses a threshold.
- Reopening or reprocessing a cleared record preserves the earlier cleared version. Later export integrations must also preserve export history.

## 11. Functional requirements

Priority uses `P0` for the initial usable vertical slice, `P1` for the production pilot, and `P2` for later expansion.

### 11.1 Intake and image management

| ID | Priority | Requirement |
|---|---:|---|
| ING-001 | P0 | Accept JPEG, PNG, HEIC, and profile-approved RAW/TIFF inputs, subject to configurable size and resolution limits. |
| ING-002 | P0 | Support single- and multi-file upload from supported Flutter targets. |
| ING-003 | P1 | Support folder-based batch selection where the operating system permits it, with a visible per-file manifest. |
| ING-004 | P1 | Support server-side retrieval from HTTPS cloud URLs after validation against SSRF, redirect, content-type, size, and malware policies. |
| ING-005 | P0 | Support camera capture on mobile/tablet with focus, glare, blur, exposure, framing, and resolution feedback before submission. |
| ING-006 | P0 | Preserve the unmodified original in object storage and store its cryptographic checksum, MIME type, dimensions, size, acquisition method, timestamps, and uploader. |
| ING-007 | P0 | Generate derivatives without overwriting the original, including display previews, orientation-corrected views, and model-safe crops. |
| ING-008 | P0 | Make create/upload operations idempotent and warn on likely checksum duplicates within the configured scope. |
| ING-009 | P1 | Resume interrupted client uploads and backend ingestion without duplicating specimen records. |
| ING-010 | P1 | Let an authorized user reject an out-of-scope image or manually split an image that contains multiple specimens. |
| ING-011 | P1 | Treat embedded metadata as untrusted; preserve only policy-approved EXIF and remove sensitive EXIF from derivatives and exports when configured. |

### 11.2 Collection classification and profile selection

| ID | Priority | Requirement |
|---|---:|---|
| CLS-001 | P0 | Store the collection hierarchy as configurable data rather than hard-coded Flutter values. |
| CLS-002 | P0 | Produce ranked classification candidates with calibrated scores, the selected candidate, model provenance, and machine-readable reasons. |
| CLS-003 | P0 | Allow a user to select or correct collection/subcollection before processing continues when confidence or policy requires review. |
| CLS-004 | P1 | Allow an authorized user to correct classification later; create a new run and explicitly invalidate profile-dependent downstream results. |
| CLS-005 | P0 | Map a selected classification to one active, versioned collection profile. Missing or ambiguous mappings must fail closed to review. |
| CLS-006 | P1 | Support profile-specific classification thresholds, top-k behavior, and mandatory human confirmation. |
| CLS-007 | P1 | Capture confirmed user corrections as evaluation data; do not automatically use them for model training without an approved policy. |

### 11.3 Segmentation

| ID | Priority | Requirement |
|---|---:|---|
| SEG-001 | P0 | Invoke SAM 3 through a versioned service adapter using settings supplied by the active collection profile. |
| SEG-002 | P0 | Detect every visible label region required by the profile and store masks, bounding boxes/polygons, ordering, confidence, model version, parameters, and derived crops. |
| SEG-003 | P0 | Retain coordinates in the original image's coordinate space so crops and overlays remain reproducible. |
| SEG-004 | P0 | Let reviewers add, delete, reorder, resize, rotate, or merge label regions without modifying the source asset. |
| SEG-005 | P0 | Route missing-label, overlapping-region, low-quality, or zero-region cases according to profile rules. |
| SEG-006 | P1 | Optionally identify other profile-defined regions such as specimen, barcode, color target, scale bar, annotation, packet, or container. |
| SEG-007 | P1 | When segmentation changes, rerun only dependent steps and preserve the superseded crops and observations. |

### 11.4 Multi-model transcription

| ID | Priority | Requirement |
|---|---:|---|
| TRN-001 | P0 | Run at least two independently configured vision-model observations per required label in the pilot profile. |
| TRN-002 | P0 | Keep first-pass models isolated from peer outputs. Each receives only the approved image context, profile prompt, schema, and tool permissions. |
| TRN-003 | P0 | Ask models to preserve visible spelling, capitalization, punctuation, line breaks, abbreviations, and explicit unreadable/uncertain spans. |
| TRN-004 | P0 | Separate literal transcription from structured field extraction and later normalization. |
| TRN-005 | P0 | Store the full raw provider response and a parsed observation with provider, model identifier/version, prompt version, parameters, input asset/crop IDs, timestamps, latency, token/compute usage, finish state, and errors. Large raw payloads belong in object storage with an immutable relational reference. |
| TRN-006 | P0 | Support label-level language/script candidates and profile-defined handling for mixed-language labels. |
| TRN-007 | P0 | Calculate character/span, line, field, and label disagreements without discarding minority readings. |
| TRN-008 | P0 | Run a separate adjudication step only after all required independent observations are durably stored. |
| TRN-009 | P0 | Link every adjudicated span to the contributing observations and source crop; unresolved alternatives remain explicit. |
| TRN-010 | P1 | Allow the profile to require additional models for particular scripts, handwriting classes, label types, or disagreement patterns. |
| TRN-011 | P1 | Detect prompt refusal, empty output, truncated output, schema violation, and likely unsupported modality as distinct outcomes. |
| TRN-012 | P1 | Enable reviewers to compare raw responses and visual diffs, not only the consensus text. |

### 11.5 Disagreement and triage scoring

| ID | Priority | Requirement |
|---|---:|---|
| SCR-001 | P0 | Produce label- and specimen-level triage scores with versioned algorithms and profile-specific weights. |
| SCR-002 | P0 | Include explainable component measures such as image quality, segmentation quality, transcription agreement, field agreement, validation status, lookup support, and unresolved uncertainty. |
| SCR-003 | P0 | Display component values and reason codes; do not expose only an unexplained composite number. |
| SCR-004 | P0 | Name the score as a risk, review-priority, or evidence-completeness score until it is calibrated against expert ground truth; do not label it “accuracy.” |
| SCR-005 | P1 | Calibrate thresholds using a versioned, representative, expert-reviewed dataset for each profile and report performance across relevant difficulty slices. |
| SCR-006 | P1 | Prevent a high score from overriding missing required labels, unresolved critical fields, provenance gaps, or hard validation failures. |

### 11.6 Structured extraction, enrichment, and reasoning harness

| ID | Priority | Requirement |
|---|---:|---|
| HAR-001 | P0 | Provide a stable harness contract that accepts a specimen snapshot, active profile, resolved label transcript, tool registry, execution budget, and prior checkpoints. |
| HAR-002 | P0 | Return typed field candidates, evidence items, validation results, unresolved issues, tool outcomes, execution trace, and a proposed disposition. |
| HAR-003 | P0 | Execute versioned phases: parse, plan, lookup, resolve, normalize, validate, and finalize. A profile may skip only explicitly non-applicable phases. |
| HAR-004 | P0 | Keep the literal source value, parsed value, normalized value, and external identifier as separate linked properties. |
| HAR-005 | P0 | Require evidence for externally resolved or normalized claims and allow the harness to abstain when support is insufficient. |
| HAR-006 | P0 | Support deterministic validators before and after agent reasoning, including schema, type, format, range, cross-field, identifier, and profile-specific rules. |
| HAR-007 | P0 | Expose data sources through typed, allow-listed adapters rather than unrestricted arbitrary code or network access. |
| HAR-008 | P0 | Represent lookup outcomes distinctly: success, no match, ambiguous match, empty response, rate limited, timeout, authentication error, authorization error, provider error, malformed response, and policy blocked. |
| HAR-009 | P0 | Apply bounded retries with backoff and jitter only where safe, honor provider retry instructions, use circuit breakers, and resume from checkpoints. |
| HAR-010 | P0 | Capture query parameters, source/provider, retrieval time, adapter version, response digest, matched identifiers, relevant support, licensing/usage metadata when needed, and the candidate values derived from each lookup. |
| HAR-011 | P1 | Support controlled tools for domain-specific browser, terminal, function, API, ontology, geocoding, taxonomy, people-authority, and institutional-catalog workflows. |
| HAR-012 | P1 | Enforce per-run time, cost, token, tool-call, loop, and concurrency budgets. Budget exhaustion produces an explicit issue, never an invented value. |
| HAR-013 | P1 | Support historical reasoning over collector identity, date ranges, spelling variants, taxonomic synonyms, and historical geography while preserving alternatives and temporal context. |
| HAR-014 | P1 | Store historical locality as written separately from interpreted historical jurisdiction, modern jurisdiction, and geospatial candidates. |
| HAR-015 | P1 | Treat verbatim notes and descriptions separately from interpretations or controlled-vocabulary mappings. |
| HAR-016 | P1 | Permit multiple specialized agents where a profile benefits from them, but require explicit responsibilities, typed handoffs, bounded execution, and a final verifier that can abstain. |
| HAR-017 | P1 | Cache source responses where policy permits while retaining retrieval date and supporting forced refresh. |
| HAR-018 | P1 | Provide a sandbox and test fixtures so a profile and its adapters can be evaluated without touching production records or paid services. |
| HAR-019 | P0 | Never invent, guess, or coerce a value to satisfy completeness. When source evidence is insufficient, the harness must abstain, preserve the unresolved state and attempts, and fail the affected clearance gate. |

### 11.7 Collection profile management

| ID | Priority | Requirement |
|---|---:|---|
| PRF-001 | P0 | A profile declares its collection taxonomy node, record schema, required/optional/not-applicable fields, prompt set, model policy, segmentation policy, tools, data sources, validators, scoring weights, and queue rules. |
| PRF-002 | P0 | Profiles are immutable once published. Edits create a new draft version. |
| PRF-003 | P0 | Every pipeline run pins a published profile version. |
| PRF-004 | P1 | Promotion requires schema validation, static policy checks, adapter contract tests, representative evaluation results, and authorized approval. |
| PRF-005 | P1 | The system supports draft, testing, approved, active, deprecated, and revoked profile states. |
| PRF-006 | P1 | Revoking a profile or provider prevents new runs and visibly identifies affected in-flight or completed records; it does not erase history. |
| PRF-007 | P1 | A new subcollection can be added through a profile and adapters without editing the core state machine. |

### 11.8 BYOK and model-provider management

| ID | Priority | Requirement |
|---|---:|---|
| BYO-001 | P1 | Support organization- or collection-scoped provider connections for approved provider adapters and the platform-managed default model pool without coupling the application architecture to any provider's cloud. |
| BYO-002 | P1 | Keep provider secrets server-side in an approved secret manager; SQL Connect/Cloud SQL stores only encrypted connection metadata and secret references, never plaintext keys. |
| BYO-003 | P1 | Let an authorized administrator test a connection, see permitted models/regions, set budgets, rotate credentials, and disable a connection. |
| BYO-004 | P1 | A profile's provider-routing policy states which data classifications may be sent to which providers and regions. |
| BYO-005 | P1 | Before execution, resolve a logical capability such as `handwriting_transcriber` to an approved provider/model and record the exact resolution. |
| BYO-006 | P1 | If BYOK is unavailable, apply the configured fallback policy: pause, use an approved platform model, or require human review. Never switch providers silently. |
| BYO-007 | P1 | Record per-provider latency, usage, estimated cost, error class, and fallback behavior without exposing credentials. |
| BYO-008 | P2 | Support additional provider adapters without changing collection profiles that reference logical capabilities. |

### 11.9 Review workbench

| ID | Priority | Requirement |
|---|---:|---|
| REV-001 | P0 | Present the original image with pan, zoom, rotation, label overlays, and quick navigation among crops. |
| REV-002 | P0 | Show independent readings side by side with character/span differences and uncertainty markers. |
| REV-003 | P0 | Show literal transcription, parsed fields, normalized candidates, authority identifiers, evidence, validation issues, and decision history as distinct layers. |
| REV-004 | P0 | Permit keyboard-efficient confirmation and correction while remaining fully usable by touch and assistive technology. |
| REV-005 | P0 | Require a reason for overrides that change a critical field, dismiss a hard validation finding, or change a final disposition. |
| REV-006 | P0 | Save edits as versioned decisions with actor, timestamp, before/after values, reason, and source context. |
| REV-007 | P0 | Re-evaluate dependent fields and queue eligibility after a correction, without recomputing unaffected stages. |
| REV-008 | P1 | Support assignment, claim/release, comments, saved filters, bulk non-destructive actions, and conflict detection for concurrent reviewers. |
| REV-009 | P1 | Prioritize queue items using explicit filters such as collection, reason, risk, age, batch, source, script, or failed rule. |
| REV-010 | P1 | Let reviewers mark a source span unreadable or unknown without forcing a guessed value. |

### 11.10 Final queues and disposition policy

| ID | Priority | Requirement |
|---|---:|---|
| QUE-001 | P0 | After all required attempts complete, assign exactly one disposition: Cleared, Needs human review, or Deferred. |
| QUE-002 | P0 | Cleared requires complete required-label coverage, completed independent passes, resolved critical disagreements, schema-valid output, a supported non-empty value for every profile-specific mandatory field, complete provenance, zero unresolved hard validation errors, and any required human approval. |
| QUE-003 | P0 | Needs human review covers cases a person can reasonably resolve now: classification ambiguity, segmentation correction, transcription disagreement, missing/ambiguous field, conflicting evidence, policy exception, or reviewer-required rule. |
| QUE-004 | P0 | Deferred is limited to documented model-capability limitations after all configured viable attempts, such as unsupported script, exceptionally complex handwriting, severe occlusion/damage, or an unavailable required capability with no current approved substitute. |
| QUE-005 | P0 | Rate limits, timeouts, provider outages, invalid credentials, code errors, and exhausted temporary capacity remain operational blocks and cannot produce Deferred. |
| QUE-006 | P0 | Every disposition includes rule version, reason codes, summary, outstanding issues, and the evidence used. |
| QUE-007 | P1 | Deferred records include retry eligibility predicates, such as a newer model family, capability tag, profile version, or manual campaign. |
| QUE-008 | P1 | A reprocessed record retains prior dispositions and shows why the latest disposition changed. |

### 11.11 Search, reporting, and export

| ID | Priority | Requirement |
|---|---:|---|
| EXP-001 | P0 | Search and filter specimens by stable ID, batch, collection, state, queue, date, uploader, score band, issue, and profile version. |
| EXP-002 | P1 | Provide dashboards for throughput, clearance rate, human-review rate, deferred reasons, operational failures, queue age, cost, latency, and reviewer effort. |
| EXP-003 | P1 | Report quality measures against reviewed ground truth by profile, field, model, prompt, language/script, image-quality band, and difficulty slice. |
| EXP-004 | P2 | Export only authorized record versions to versioned target schemas with an immutable manifest, checksums, warnings, and provenance references. |
| EXP-005 | P2 | Support CSV and JSON/JSON Lines when export work begins; collection-system-specific adapters are separate versioned integrations. |
| EXP-006 | P2 | Prevent duplicate downstream creation through stable source IDs and idempotency keys. |
| EXP-007 | P2 | Never include restricted fields or source images in an export unless the target and user are explicitly authorized. |
| EXP-008 | P2 | Defer EMu projection, EMu export snapshots, and EMu writes until the internal end-to-end application and production pilot exit criteria pass. |

### 11.12 Notifications and operational recovery

| ID | Priority | Requirement |
|---|---:|---|
| OPS-001 | P0 | Display clear, actionable messages for user input errors, operational errors, data ambiguity, and model limitations; these categories must not be conflated. |
| OPS-002 | P0 | Provide a per-specimen timeline of stage, progress, attempts, next retry, and current blocker. |
| OPS-003 | P0 | Use dead-letter handling for jobs that exceed automated retry policy and provide an authorized replay action. |
| OPS-004 | P1 | Alert administrators to credential failures, sustained provider errors, queue stalls, and budget thresholds. |
| OPS-005 | P1 | Pause affected workflows when a provider, model, profile, or adapter is revoked, while leaving unrelated work running. |
| OPS-006 | P1 | Support maintenance-mode and incident messages that identify affected features without hiding already completed records. |

## 12. Collection-profile and harness contract

The collection profile is the main extension point. It should be declarative where possible and reference tested code modules only where reasoning or integration requires them.

The accepted architecture boundary separates a durable outer workflow from the typed inner agent harness. Pydantic AI is the first harness candidate; Temporal is the production-reference workflow candidate and Google Cloud Workflows is the required Firebase/GCP-native comparator. The final workflow engine is not selected until both run the same Insects failure-injection spike. Do not provision Temporal Cloud before that bounded comparison passes. See [Durable Workflow and Agent Harness Decision](./HARNESS_OPTIONS.md).

### 12.1 Minimum profile contents

```yaml
profile_id: zoology_insects
version: 1.0.0
collection_path: [zoology, insects]
record_schema: fmnh_insects_record_v1
label_types: [collection, determination, annotation, barcode]
segmentation:
  adapter: sam3
  policy_version: 1
transcription:
  minimum_independent_observations: 2
  logical_model_capabilities: [printed_text, handwriting]
  prompt_set: fmnh_insects_transcription_v1
harness:
  phases: [parse, plan, lookup, resolve, normalize, validate, finalize]
  tools: [taxonomy_verifier, geography_lookup, parties_lookup]
  budgets: {max_tool_calls: TBD, max_elapsed_minutes: TBD, max_cost: TBD}
validation:
  ruleset: fmnh_insects_rules_v1
scoring:
  policy: fmnh_insects_review_risk_v1
disposition:
  clearance_policy: fmnh_insects_clearance_v1
data_policy:
  classification: internal
  approved_provider_routes: [huggingface_qwen_novita, huggingface_muse_deepinfra]
```

This is illustrative, not a locked file format.

### 12.2 Harness execution rules

- Plans and tool calls are bounded and persist after each step.
- Tools accept and return typed payloads with stable error taxonomies.
- The harness may propose values but cannot erase raw observations or human decisions.
- Deterministic validation wraps agent reasoning; agents cannot waive a hard rule without an authorized, recorded policy exception.
- Tool results are treated as untrusted input and are validated before use.
- Browser or terminal tools, when enabled, run in a restricted environment with allow-listed destinations, scoped credentials, sanitized logs, and no access to unrelated tenants.
- The final verifier receives the full evidence graph and returns passed gates, failed gates, unresolved issues, and an explicit disposition recommendation.
- Final queue assignment is made by the versioned policy engine, not by free-form model text.

### 12.3 Reasoning requirements

The harness must be able to represent and test multiple hypotheses rather than collapse ambiguity prematurely. Examples include:

- a collector known under initials, full name, married name, alternate transliteration, or misspelling;
- a place whose label name, jurisdiction, country, or boundaries changed over time;
- a scientific name that was valid at collection time but is now a synonym;
- a date inferred from collector activity that conflicts with a literal reading;
- ditto marks or label layout that inherit context from another line;
- notes that contain habitat, preparation, cultural, or expedition context but should not be forced into a controlled field;
- multiple authority records that remain plausible after lookup.

For every such case, the record must retain the literal text, candidates considered, temporal constraints, supporting or conflicting evidence, chosen interpretation if any, confidence state, and decision source.

### 12.4 Field Museum Insects pilot profile

#### Confirmed pilot decisions

- The first pilot subcollection is **Insects**.
- The following fields are mandatory members of the entomological record schema.
- **Cleared requires a supported, non-empty value for every mandatory field.** A placeholder or processing state such as `unknown`, `unreadable`, `not present`, or `not applicable` does not satisfy this requirement.
- No agent, model, validator, or reviewer workflow may invent or pressure-generate a value merely to make a record complete. Insufficient evidence produces an explicit abstention and blocks Cleared.
- Taxonomy work begins with Global Names Verifier, Catalogue of Life, GBIF, and BugGuide for North American material.
- Geography work begins with Mapcarta and Google Maps.
- Parties/person research uses the taxonomy sources or an approved Google search workflow to find species authors.
- Fields other than the explicit taxonomy, geography, and parties-resolution work are transcribed as seen on the labels.
- **Corrected after technical verification:** the official Axiell expansion of `IRN` is **Internal Record Number**, not “Internal Reference Number.”

Every record version must still retain a typed state for each mandatory field so omissions are visible and queryable. Absence states are legitimate processing outcomes, but they do not become data values and cannot pass the Insects clearance gate. A missing or ambiguous value after all required attempts complete routes the specimen to **Needs human review**; it may enter **Deferred** only when the separate, narrowly defined model-capability policy in `QUE-004` applies. If a required lookup could not execute because of credentials, authorization, service availability, or another operational condition, the job remains operationally blocked under `QUE-005` rather than entering a final queue.

#### EMu Parties technical finding — checked 2026-09-07

Field Museum's currently published active Darwin Core mapping, together with its 2024 sample and 2019 historical schema evidence, indicates that `Identified by IRN` refers to an `eparties` record. The public collection search exposes catalogue IRNs and flattened person names, but no anonymous Parties resolver was confirmed. The exact production mapping and approved authority-access mechanism still require Field Museum confirmation; see the [dated EMu Parties/IRN research note](./EMU_PARTIES_IRN_RESEARCH.md).

#### Mandatory fields

| Display field | Proposed internal key | Initial data treatment |
|---|---|---|
| FMNH-INS# | `fmnh_ins_number` | Literal identifier plus a separately validated canonical form. |
| Collection Code | `collection_code` | Literal value plus a controlled-code candidate if a code list is supplied. |
| Country | `country` | Literal geographic value; normalized candidate and evidence stored separately. |
| Province/State | `province_state` | Literal geographic value; normalized candidate and evidence stored separately. |
| County | `county` | Literal geographic value; normalized candidate and evidence stored separately. |
| City | `city` | Literal geographic value; normalized candidate and evidence stored separately. |
| Precise Location | `precise_location` | Verbatim locality text; never replaced by a geocoder result. |
| Elevation From (m) | `elevation_from_m` | Literal numeric value/unit when present; derived conversion must be marked as derived. |
| Elevation To (m) | `elevation_to_m` | Literal numeric value/unit when present; derived conversion must be marked as derived. |
| Elevation From (ft) | `elevation_from_ft` | Literal numeric value/unit when present; derived conversion must be marked as derived. |
| Elevation To (ft) | `elevation_to_ft` | Literal numeric value/unit when present; derived conversion must be marked as derived. |
| Habitat | `habitat` | Transcribed as seen; controlled terms, if later required, are separate candidates. |
| Collection Method | `collection_method` | Transcribed as seen; controlled terms, if later required, are separate candidates. |
| Date Visited From | `date_visited_from` | Literal text plus a separately parsed date or partial date. |
| Date Visited To | `date_visited_to` | Literal text plus a separately parsed date or partial date. |
| Collectors | `collectors` | Verbatim names plus separate person/party candidates when resolution is required. |
| Verbatim D/T/S | `verbatim_dts` | Transcribed exactly; expansion and internal semantics require confirmation. |
| Taxon | `taxon` | Verbatim scientific name plus separately resolved name, authorship, status, rank, and source identifier. |
| Identified by IRN | `identified_by_irn` | Internal Record Number of the resolved `eparties` record. Qualify it with source system, tenant/environment, and module; the current production column, expected serialization, and approved lookup path require confirmation. |
| Date Identified | `date_identified` | Literal text plus a separately parsed date or partial date. |

The proposed internal keys are implementation candidates, not approved Field Museum mappings. They must be reconciled with the target collection-management schema before development.

#### Source registry and intended use

| Domain | Source | Intended pilot use | Automation status |
|---|---|---|---|
| Taxonomy | [Global Names Verifier](https://verifier.globalnames.org/) | Parse names, exact/fuzzy verification, and source-specific candidates. | REST API is documented; adapter spike required. |
| Taxonomy | [Catalogue of Life](https://www.catalogueoflife.org/) | Accepted names, synonyms, rank, authorship, and release-specific identifiers. | ChecklistBank API is documented; pin dataset/release in evidence. |
| Taxonomy | [GBIF](https://www.gbif.org/) | Name matching, taxonomic usage, synonymy, authorship, and identifiers. | Species API is documented; adapter spike required. |
| Taxonomy | [BugGuide](https://www.bugguide.net/node/view/15740) | North American insect context and candidate corroboration. | Treat as browser-assisted/manual until terms and a supported machine interface are approved. |
| Geography | [Mapcarta](https://mapcarta.com/) | Place discovery and corroboration. | Treat as browser-assisted/manual until terms and a supported machine interface are approved. |
| Geography | [Google Maps](https://www.google.com/maps) | Place discovery, modern geographic candidates, and coordinates. | Use an approved Google Maps Platform API for automation; browser use remains a separately governed tool. |
| Parties | Approved taxonomy sources and Google search | Find candidate species authors and supporting pages. | Search is discovery, not sufficient evidence by itself; capture and evaluate the underlying result page. |

Source adapters must preserve the exact query, result candidates, source release/version when available, retrieval time, stable identifier, response digest, and evidence used. A search-result snippet alone cannot support a cleared value.

#### Initial insects harness stages

1. Parse all literal fields from the adjudicated label transcript without normalizing away original wording.
2. Validate and canonicalize the FMNH-INS identifier while retaining the literal form.
3. Run taxonomy verification against the approved taxonomy adapters, retaining accepted, synonym, ambiguous, and no-match outcomes.
4. Use BugGuide only for North American context and only under the approved browser/terms policy.
5. Generate geography candidates from Mapcarta and/or Google Maps without overwriting verbatim locality fields.
6. Generate parties/person candidates for taxonomic authorship using taxonomy evidence and approved web discovery.
7. Run deterministic range and consistency checks, including elevation lower/upper order, metre/foot conversion tolerance where both are present, visited-date order, identified-date plausibility, and geographic containment as a warning rather than automatic truth.
8. Return typed candidates, evidence, disagreements, unresolved issues, and clearance-gate results to the policy engine.

#### Insects-specific items not yet confirmed

- The exact parent path and collection code for Insects in the application's configurable taxonomy.
- The expansion, format, and business meaning of `Verbatim D/T/S`.
- The current production column, serialization, and approved lookup path for the `eparties` record referenced by `Identified by IRN`; no anonymous public Parties resolver was confirmed in the 2026-09-07 check.
- Whether the collection manager confirms Parties resolution for every person-name field. Current Field Museum schema evidence supports collector, identifier, and taxonomy-author references, but the production requirement remains unapproved.
- Whether missing metric or imperial elevation values should be converted, left absent, or both; any conversion must remain visibly derived.
- Required date precision and formats for partial, uncertain, or range dates.
- Source precedence and conflict rules among Global Names Verifier, Catalogue of Life, GBIF, and BugGuide.
- The approved Google products, credentials, attribution, storage, and caching policy.
- Whether a Google-only or Mapcarta-only match can support clearance without human confirmation.

## 13. Scoring model requirements

The initial composite should be framed as **review risk**, where a higher score means greater need for review. The exact formula is a versioned policy and must be empirically calibrated.

Candidate components include:

- image-quality risk: blur, glare, clipping, resolution, perspective, occlusion;
- segmentation risk: missing-region indicators, overlap, small crops, uncertain boundaries;
- transcription disagreement: normalized edit differences, unresolved spans, line ordering, numeral/date disagreement;
- field disagreement: competing parses or mutually exclusive critical values;
- evidence risk: no match, weak source, ambiguous authority match, stale source, conflicting sources;
- validation risk: hard and soft rule findings;
- capability risk: unsupported script, handwriting complexity, damaged media, or provider refusal;
- coverage risk: required label types or fields not accounted for.

Every score must store:

- the algorithm and feature version;
- input feature values;
- profile-specific weights/thresholds;
- the resulting components and composite;
- reason codes;
- calibration dataset/version;
- creation time.

The product must report score calibration and correction rates. It must not optimize the percentage in Cleared without simultaneously monitoring expert-verified critical errors and queue composition.

## 14. Data architecture

### 14.1 Platform boundary

**Flutter client**

- Responsive UI for mobile, tablet, web, and selected desktop targets.
- Capture, resumable upload, queue navigation, review, settings, and status.
- No provider secrets and no authoritative long-running model execution.

**Firebase application services**

- Firebase Authentication for identity.
- Firebase SQL Connect backed by Cloud SQL for PostgreSQL for transactional application metadata, relational constraints, workflow summaries, permissions, and review state.
- Cloud Storage for originals, derivatives, crops, large raw responses, and audit artifacts; later export artifacts may use the same service.
- Firebase App Check and backend authorization enforcement for supported clients.
- Short event-handling functions where appropriate.

**Backend processing plane**

- Durable workflow orchestration with retries, timeouts, checkpoints, idempotency, cancellation, and human-wait states.
- Containerized services for quality analysis, classification, SAM 3 segmentation, model-provider adapters, transcription, adjudication, harness execution, and validation. Export services are added in a later integration phase.
- Queue/event transport for asynchronous work and backpressure.
- Secret manager and key-management service for BYOK.
- Central logs, traces, metrics, budgets, and alerting.

Firebase remains the identity, application-data, object-storage, and UI-state platform. A durable workflow engine is additive: it coordinates the multi-stage processing lifecycle and writes application-owned records and summaries through controlled interfaces; it does not replace Firebase or become the specimen system of record.

The implementation may use Google Cloud services that integrate naturally with Firebase, but the workflow and agent-framework selection is a technical-design decision. Temporal and Google Cloud Workflows must be compared with the same failure-injection scenario before the engine is selected. The chosen stack must satisfy the behavior in this PRD; an agent library, individual task queue, or event handler by itself is not a substitute for a durable workflow engine.

### 14.2 Logical relational model

The SQL Connect schema and PostgreSQL structure must be validated against access patterns, relational constraints, indexes, transaction boundaries, authorization directives, connection limits, and cost. A proposed starting point is:

| Table / entity | Purpose |
|---|---|
| `organizations` | Tenant policy, retention, provider-routing defaults. |
| `users` and `memberships` | Identity references and scoped roles. |
| `collectionNodes` | Configurable hierarchy and display metadata. |
| `collectionProfiles` | Version metadata, status, approval, immutable config pointer. |
| `batches` | Intake manifest, defaults, counts, source, uploader. |
| `specimens` | Current summary, selected classification, active run, latest disposition, sensitivity flags. |
| `sourceAssets` | Storage pointers, hashes, media metadata, derivatives, relationships. |
| `pipelineRuns` | Pinned versions, lifecycle, checkpoints, budgets, timestamps, active blockers. |
| `labelRegions` | Geometry, crop references, type/order, segmentation provenance, version. |
| `modelObservations` | Parsed output metadata and pointers to immutable raw responses. |
| `transcriptionVersions` | Adjudicated literal text, alternatives, span lineage, unresolved uncertainty. |
| `fieldCandidates` | Candidate values and derivation/evidence links. |
| `recordVersions` | Resolved structured record and validation snapshot. |
| `lookupExecutions` | Query/result metadata, typed outcome, evidence and raw-response pointer. |
| `validationFindings` | Rule version, severity, affected field, result, evidence. |
| `reviewDecisions` | Actor, before/after, reason, authority, timestamps. |
| `auditEvents` | Append-only security and material product actions. |
| `exports` (later phase) | Export set, target schema, manifest, checksums, status; do not build for the initial vertical slice. |
| `providerConnections` | Non-secret metadata and references to secret-manager entries. |

Image bytes, raw model payloads, large evidence captures, and complete trace bundles must not be embedded in relational rows. They belong in object storage with immutable references and hashes; repeated structured values belong in normalized child tables.

### 14.3 Record layers

The database must keep these layers distinct:

1. **Source layer:** original pixels and acquisition facts.
2. **Observation layer:** segmentation and independent model outputs.
3. **Transcription layer:** adjudicated literal readings and alternatives.
4. **Interpretation layer:** parsed and normalized candidates with evidence.
5. **Decision layer:** selected values, validation outcomes, human overrides, and disposition.
6. **Downstream projection layer (later phase):** immutable snapshots sent to downstream systems only after the internal app and pilot are proven.

### 14.4 Provenance minimum

Every material value must answer:

- Which specimen, source asset, and label region did it come from?
- Was it directly transcribed, deterministically parsed, inferred, looked up, normalized, or entered by a person?
- Which model, prompt, profile, code, adapter, rule, and external-source versions contributed?
- What alternatives existed and what evidence supported or contradicted them?
- Who or what selected the final value, when, and why?
- If later exported, which exact version was exported and where?

## 15. Provider and data-source failure behavior

| Outcome | Automatic behavior | User-visible behavior | Final-queue impact |
|---|---|---|---|
| Rate limited | Honor retry instructions, back off, checkpoint, and retry within budget. | Show provider, next retry, and affected stage. | Operational block if exhausted; never Deferred. |
| Timeout/transient provider error | Retry safely, then open circuit if systemic. | Show retry status and incident state. | Operational block if exhausted. |
| Authentication/authorization error | Stop calls for that connection and alert an administrator. | Explain that credentials or permissions require action without revealing secrets. | Operational block. |
| Empty result / no match | Record the query and valid empty outcome; optionally try approved alternate sources. | Show that sources were checked and returned no supported match. | Review or profile-approved unknown; not an operational error. |
| Ambiguous match | Preserve ranked candidates and evidence; do not pick without sufficient policy support. | Show alternatives and differences. | Usually Needs human review. |
| Malformed response/schema mismatch | Preserve raw response, retry only when safe, and flag adapter/provider defect. | Show a processing problem. | Operational block unless an alternate approved path completes. |
| Unsupported model capability | Try profile-approved alternate capabilities/models. | Explain what could not be read and what was attempted. | May be Deferred only after configured viable attempts are exhausted. |
| Budget exhausted | Checkpoint and stop new paid/tool work. | Show which budget was reached and available administrator action. | Operational/policy block, not automatically Deferred. |
| Policy blocked | Do not send data or invoke the tool. | Explain the policy restriction and permitted next action. | Review or operational block according to profile. |

## 16. Non-functional requirements

### 16.1 Reliability and recoverability

- Processing must continue independently of the client session.
- At-least-once message delivery must not create duplicate logical results.
- All externally visible mutations use idempotency keys.
- Each stage has explicit timeout, retry, cancellation, and compensation behavior.
- Jobs can resume after worker restart, deployment, provider outage, or temporary network loss.
- Backpressure prevents a batch from overwhelming providers or starving interactive review work.
- Backups, restore procedures, recovery objectives, and disaster-recovery exercises must be defined before production launch.

### 16.2 Performance and scale

- Upload acknowledgment and job creation should feel interactive; model processing is asynchronous and must show stage-level progress.
- The system must support batch concurrency limits by organization, profile, provider, and model resource.
- Original-image size, throughput, latency, and cost targets will be set after a representative pilot benchmark rather than guessed in this draft.
- The architecture must allow segmentation/model workers to scale independently from the Flutter/API tier.

### 16.3 Security, privacy, and stewardship

- Encrypt data in transit and at rest.
- Store BYOK secrets only in an approved secret manager and never in Flutter, logs, prompts, analytics, or SQL Connect/Cloud SQL plaintext.
- Enforce least-privilege service identities and collection-scoped user authorization.
- Use short-lived signed access for private images and exports.
- Maintain append-only audit events for authentication, authorization, configuration, review, export, credential, and deletion actions.
- Support configurable retention, legal hold, export, and verified deletion policies.
- Do not use museum images, labels, records, prompts, or corrections for provider or platform training without explicit institutional authorization.
- Treat precise localities, endangered species, cultural objects, human remains, donor restrictions, personally identifying label data, and repatriation-sensitive information as potentially restricted. Policy owners define handling and provider eligibility before a profile is activated.
- Validate all uploaded files and remote content; isolate image decoding and tool execution from privileged services.
- Redact secrets and sensitive content from telemetry while preserving useful trace identifiers.
- Complete a threat model and privacy review before the pilot accepts restricted collections.

### 16.4 Accessibility and responsive behavior

- Target WCAG 2.2 AA, or the museum's stricter applicable standard, for supported user workflows.
- Provide keyboard access, visible focus, semantic labels, adequate contrast, non-color-only status, scalable text, screen-reader-compatible forms/tables, and reduced-motion behavior.
- Make the review experience usable on tablet and desktop. Mobile supports capture and status; dense transcription review may recommend a larger display without blocking accessible access.
- Never encode transcript disagreement only through color; include text and symbols.

### 16.5 Observability and auditability

- Assign correlation IDs across specimen, run, stage, model call, tool call, lookup, review, and export.
- Record structured logs, distributed traces, metrics, and typed errors without logging secrets.
- Track stage latency, queue depth/age, retry counts, provider errors, model usage/cost, disposition reasons, and profile-version regressions.
- Make every cleared record reproducible from retained source assets and pinned dependencies, subject to provider reproducibility limits that must be disclosed.

### 16.6 Maintainability

- Publish versioned contracts for profiles, model adapters, data-source adapters, validators, workflow events, and exports.
- Validate backward compatibility and provide migrations for breaking schema changes.
- Use test fixtures with licensed or approved representative samples.
- Support feature flags and organization-scoped rollout of models, prompts, profiles, and UI behavior.

## 17. Evaluation and success metrics

### 17.1 Quality metrics

- Exact-match and character/word error rates for literal transcription on expert-reviewed labels, with explicit handling of unreadable ground truth.
- Precision, recall, and correction rate for critical structured fields.
- Classification accuracy and calibration by collection/subcollection.
- Label-detection coverage and region quality.
- False-clear rate, especially specimens with a critical error after expert audit.
- Provenance completeness rate for cleared fields and records.
- Disagreement score calibration: observed correction/error rate within each score band.
- Inter-reviewer agreement and adjudication rate.

### 17.2 Operational metrics

- Median and percentile time from ingestion to disposition by profile.
- Reviewer minutes per specimen and records cleared per reviewer hour.
- Percentage Cleared, Needs human review, Deferred, and operationally blocked, reported together.
- Queue age and oldest item by reason.
- Retry, dead-letter, provider-failure, and recovery rates.
- Cost per processed, reviewed, and cleared specimen by provider/profile.
- Duplicate ingestion and idempotency-violation counts.

### 17.3 Metric safeguards

- Never evaluate success from clearance percentage alone.
- Maintain a stable, representative evaluation set and disclose exclusions.
- Report results by difficulty, collection, script/language, image quality, label type, and provider where sample sizes permit.
- Human corrections are evaluation evidence; they are not automatically ground truth until approved under the evaluation protocol.
- Threshold changes require comparison against the previous policy, including regressions and changed queue composition.

## 18. MVP and phased delivery

Trying to activate all natural-history domains at once would make validation ambiguous. The product should establish one complete vertical slice, then prove the extension model with a meaningfully different second subcollection.

### Phase 0 — Discovery and technical validation

- Use Field Museum Insects as the first pilot subcollection and confirm the internal pilot record schema. The EMu target schema is not a Phase 0 blocker.
- Inventory representative image and label conditions, including difficult cases.
- Define gold-set creation, reviewer protocol, critical fields, evidence policy, and acceptable error thresholds.
- Validate Flutter capture/upload behavior on target devices.
- Validate SAM 3 licensing, deployment, hardware, throughput, crop quality, and adapter contract on museum samples.
- Benchmark candidate default and BYOK vision models using independent prompts.
- Select the durable workflow engine and the agent-harness framework against the requirements in this PRD.
- Complete initial threat model, provider data-use review, and cost model.

**Exit:** Approved pilot profile design, representative evaluation set, architecture decision record, and quantified go/no-go results for image/model processing.

### Phase 1 — P0 Insects vertical slice

- Flutter authentication, file/camera intake, upload manifest, specimen list, and processing status.
- SQL Connect/Cloud SQL and Cloud Storage foundation with a durable asynchronous workflow.
- One Field Museum Insects profile implementing the mandatory fields and source rules in section 12.4.
- Classification with manual correction.
- SAM 3 segmentation with region correction.
- Two independent vision transcriptions, raw-output preservation, disagreement display, and adjudication.
- Minimal parse/validate harness with at least one meaningful authoritative lookup.
- Review workbench and all three final queues.
- End-to-end audit trail, operational recovery, and pilot dashboard.

**Exit:** A representative pilot batch can move from image intake through classification, segmentation, independent transcription, adjudication, enrichment, validation, review, persistence, and final queue assignment without manual database edits, and the critical quality thresholds approved in Phase 0 are met.

### Phase 2 — Production pilot

- Full collection-specific enrichment and historical reasoning tools for the first profile.
- Provider-neutral BYOK plus approved platform-provider routing.
- Batch/folder and cloud-URL intake hardening.
- Role scopes, assignments, notifications, cost controls, and operational alerts.
- Profile authoring/test/promotion workflow.
- Security, accessibility, load, backup/restore, and incident-response validation.

**Exit:** Museum staff complete an agreed production-scale pilot with signed quality, security, accessibility, cost, and operational acceptance.

### Phase 3 — Multi-collection expansion

- Add a second, materially different subcollection without changing the core state machine.
- Generalize authority sources, tools, schemas, and review components proven by the second profile.
- Expand provider adapters, historical geography, taxonomic, people-authority, and notes reasoning.
- Add deferred reprocessing campaigns and model/profile comparison workflows.

**Exit:** Two distinct subcollections operate through versioned profiles and demonstrate that extension is modular rather than a fork of the application.

### Phase 4 — Portfolio scale

- Onboard additional botany, zoology, geology, and anthropology profiles under collection-governance approval.
- Introduce advanced workload scheduling, cross-institution tenancy if required, and additional downstream integrations.
- Design and implement the versioned EMu projection/export adapter only after the internal application and production pilot have passed their exit criteria.
- Evaluate active learning or institution-approved fine-tuning as a separate governed capability.

## 19. P0 release acceptance criteria

The first vertical slice is acceptable only when all of the following are demonstrated with an agreed representative dataset:

1. A user can capture or upload a valid image and can recover from an interrupted upload.
2. The original image remains immutable and its checksum and provenance are available.
3. Classification returns candidates; a user correction reliably causes the correct profile to run and supersedes affected downstream results.
4. SAM 3 produces reproducible label regions, and a reviewer can correct missed or inaccurate regions.
5. At least two model observations are generated independently for every required label, with complete raw provenance.
6. Disagreements remain visible and can be adjudicated without overwriting the independent readings.
7. Literal transcription is stored separately from structured and normalized values.
8. The harness performs typed lookup and validation steps and demonstrates success, no-match, ambiguity, rate-limit, timeout, and authentication-error behavior in tests.
9. A temporary provider failure resumes from a checkpoint and does not duplicate observations, tool effects, or records.
10. Cleared is impossible when any configured critical gate is unresolved.
11. An Insects specimen with any empty or unresolved mandatory field cannot enter Cleared and is routed with an explicit reason.
12. Tests that demand completion despite missing evidence produce an abstention rather than an invented, placeholder, or coerced value.
13. Rate-limited, broken, or credential-blocked jobs do not enter Deferred.
14. A legitimate model-capability limitation can enter Deferred only with attempts, reason, and retry eligibility recorded.
15. A reviewer can resolve a Needs human review case and see dependent validations and disposition update.
16. Every final field can be traced to source pixels, model/human observations, transformations, lookup evidence, and policy decisions.
17. A persisted Cleared, Needs human review, or Deferred result can be reopened and reconstructed from its stored versions and audit evidence without hidden state.
18. Unauthorized users cannot access restricted source images, records, credentials, or audit evidence.
19. Accessibility, security, recovery, and quality gates defined during Phase 0 pass.
20. A production-like end-to-end run completes without direct database edits or hidden manual repair.

## 20. Dependencies

- Museum-approved representative and evaluation datasets, including hard and negative cases.
- Domain experts to define schemas, critical fields, authority sources, and review decisions.
- Rights to store and process specimen images and send approved data to chosen providers.
- SAM 3 model access, acceptable license, serving infrastructure, and performance validation.
- Credentials and terms for authority sources, geocoders, taxonomy services, or other APIs.
- Credentials and account access for organizations using a supported BYOK provider adapter.
- Downstream collection-system schemas and identifiers are a later integration dependency, not a blocker for the initial end-to-end application.
- Security, privacy, cultural stewardship, legal, and accessibility review appropriate to each collection.

## 21. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| False confidence from model agreement | Multiple models repeat the same plausible error. | Use diverse models/prompts, validation and evidence gates, calibrated gold sets, and expert audits; never clear on agreement alone. |
| Poor or incomplete segmentation | Labels are missed before transcription begins. | Coverage rules, full-image cross-checks, region-count anomaly detection, reviewer overlay tools, and profile-specific label expectations. |
| Agentic workflow is non-deterministic or loops | High cost, inconsistent records, stalled jobs. | Durable checkpoints, bounded plans/tools, typed outputs, deterministic validators, budgets, idempotency, and replay tests. |
| External authorities are incomplete or historically inaccurate | Incorrect normalization or false no-match. | Preserve literal values, distinguish no match from unknown, use source/version/time provenance, support multiple sources, and abstain. |
| Provider outage, rate limit, or grant expiration | Processing stalls or unexpectedly changes models. | Typed failures, backoff/circuit breaking, budget alerts, explicit fallback policy, paused jobs, and resumable runs. |
| Sensitive data reaches an unapproved provider | Stewardship, privacy, contractual, or legal harm. | Data classification, provider-routing allowlists, server-side policy enforcement, redaction where approved, and audit logs. |
| Profile changes make records incomparable | Quality regressions and unclear provenance. | Immutable versioned profiles, pinned runs, evaluation gates, controlled promotion, and run-to-run comparisons. |
| SQL Connect/Cloud SQL becomes a connection, hot-table, or large-payload bottleneck | Cost, contention, latency, and scale limits. | Normalize relational state, index measured access paths, bound connection pools, keep assets/raw payloads in object storage, and design append-only events from measured workloads. |
| Flutter target differences disrupt folder/camera behavior | Inconsistent capture and batch workflows. | Define a supported-target matrix, prototype early, provide capability-specific UI, and test on actual museum devices. |
| Clearance-rate incentives cause cherry-picking | Easy items inflate progress while hard work accumulates. | Report all dispositions and queue aging, freeze evaluation cohorts, audit exclusions, and prioritize representative sampling. |
| Anthropology or sensitive collections need materially different governance | A generic workflow violates collection policy. | Make access, provider routing, evidence display, retention, and export profile/collection controlled; require stewardship approval before activation. |

## 22. Open decisions and clarifying questions

These questions do not prevent the initial PRD draft, but the starred items must be answered before Phase 0 can exit.

1. What downstream collection management system and exact target schema will eventually receive cleared Insects records? This is intentionally deferred and does not block the initial build.
2. **What does “cleared” mean institutionally?** ★ Must every pilot record receive human approval, or can a calibrated subset clear automatically after hard gates?
3. **What does `Verbatim D/T/S` mean in the target system, including its format and validation rules?** ★
4. **Can Field Museum confirm the current production column, serialization, authority-access method, and permitted fields for the `eparties` record referenced by `Identified by IRN`?** ★
5. **Can the collection manager confirm that Parties resolution is required for every person-name field, including species authors, Collectors, and identifiers?** ★
6. **What are the acceptable error targets, especially for critical fields, and who approves the gold set?** ★
7. **Which Flutter targets are launch requirements: iOS, Android, web, macOS, Windows, or all of them?** ★ Folder selection, camera behavior, offline support, and deployment differ by target.
8. Is offline capture with later synchronization required at launch, or is resumable online upload sufficient?
9. What batch sizes, image formats/resolutions, daily volume, concurrent operators, and turnaround expectations should the architecture support?
10. Can one specimen have multiple photographs or sides in the initial data model, even if one photograph remains the default processing unit?
11. Should operators confirm every collection classification during the pilot, or only low-confidence/policy-selected cases?
12. Which exact SAM 3 release/checkpoint, license, hosting environment, latency target, and hardware budget are approved? ★
13. Which platform-managed open vision models are candidates, and must “open” mean open weights, self-hosted, a particular license, or simply not BYOK? ★
14. Which BYOK providers, authentication methods, and regions must be supported first?
15. May any model provider retain inputs, and what zero-retention/data-residency requirements apply? ★
16. What terms, quotas, caching, attribution, and automation permissions apply to the named taxonomy and geography sources? ★
17. Under what conditions may a browser or terminal tool access the public web, and what evidence must be captured from it?
18. Which categories require restricted handling, redaction, embargo, or prohibition from external providers and exports? ★
19. How long must originals, crops, raw responses, tool traces, review history, and exports be retained?
20. Who can override a hard validation finding or move a specimen among queues, and is dual approval required for sensitive/critical records?
21. Which notification channels are needed for assignments and operational incidents?
22. Is there a required institutional identity provider, or is Firebase Authentication sufficient for the pilot?
23. Is deployment single-museum initially, or must true multi-institution tenancy be present from the first release?
24. Are labels expected to contain languages or scripts that require specialized models in the pilot?
25. Can reviewed corrections be used for evaluation only, or may they later support institution-approved training/fine-tuning?

## 23. Recommended immediate next step

Run a short Insects-profile workshop focused on questions 2–6, 12–13, 15–16, and 18. The output should confirm field semantics, critical-field rules, source conflict policy, approved providers, gold-set ownership, and the clearance standard. Downstream EMu projection is deliberately excluded. That brief will make the P0 Insects vertical slice estimable.

## 24. Approval

| Role | Name | Decision | Date | Notes |
|---|---|---|---|---|
| Product owner | TBD | Pending |  |  |
| Pilot collection owner | TBD | Pending |  |  |
| Digitization operations | TBD | Pending |  |  |
| Security/privacy/stewardship | TBD | Pending |  |  |
| Technical owner | TBD | Pending |  |  |
