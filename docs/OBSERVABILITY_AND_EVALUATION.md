# Observability, Prompts, and Evaluation

| Document field | Value |
|---|---|
| Status | Foundation implemented; external Logfire setup and gold dataset pending |
| Logfire project | `anuragduddu/specimen-digitization` |
| Trace format | OpenTelemetry through Logfire and Pydantic AI |
| Default capture | Metadata only; binary images always excluded |

## Decision

Use Logfire as the observability and evaluation plane for the complete specimen
processing system. Pydantic AI supplies nested agent, model, tool, retry, usage,
and error spans. Application-owned spans supply the deterministic processing
stages around those agents.

Logfire is not the specimen system of record. Cloud Storage remains the source
for images and immutable payloads; SQL Connect/Cloud SQL owns product state,
review state, and provenance. Every Logfire record uses stable identifiers to
link back to those systems without embedding image bytes.

The improvement loop is:

```text
trace -> evaluator or curator judgment -> dataset case -> experiment
      -> reviewed prompt/model promotion -> live monitoring
```

## Implemented foundation

| Capability | Current implementation |
|---|---|
| Trace capture policy | `metadata` and explicit `approved-content` modes |
| Pydantic AI traces | Stable agent names plus model, token, retry, and error spans |
| Application traces | Safe specimen-run and processing-stage span helpers |
| Distributed correlation | Explicit context serialization/attachment helpers for trusted worker hops |
| Prompt contracts | Typed managed-variable resolvers with code-owned fallback templates |
| Literal transcription | Evidence-preserving Pydantic output schema and named agent builder |
| Offline evaluation | Versioned Pydantic Evals dataset contract and deterministic scorers |
| Experiment smoke | Synthetic dataset exported by `specimen-eval-smoke` |

## Capture policy

`LOGFIRE_CAPTURE_MODE=metadata` is the default for every environment. It records
the trace tree, span attributes, model/provider, tokens, timing, errors, and
model request schema. It excludes prompts, completions, and tool payloads.

`LOGFIRE_CAPTURE_MODE=approved-content` additionally records prompt, completion,
and tool text. It is for synthetic data or a specifically approved evaluation
corpus. The integration always sets `include_binary_content=false`; images stay
in Cloud Storage regardless of capture mode.

Use separate `APP_ENV` values for `development`, `evaluation`, `staging`, and
`production`. Start with 100% trace sampling while volume is low. If sampling is
later required, preserve complete traces and retain all failures/slow runs at an
OpenTelemetry collector rather than applying process-local tail sampling across
distributed Temporal workers.

The production decision to store specimen-label text in Logfire remains open.
It requires confirmation of permitted collections, US-region retention,
project access, and deletion requirements. Regex scrubbing is not a substitute
for that approval because LLM message attributes are not reliably scrubbed.

## Trace structure

One active processing segment begins with `Process specimen run`. Its children
use `Run specimen processing stage` with a stable
`specimen.processing.stage` value:

```text
ingest -> segment -> transcribe -> extract -> reconcile
       -> validate -> persist -> review-route
```

Every applicable span carries:

- `specimen.run.id`
- `temporal.workflow.id`
- `specimen.subject.id`
- `specimen.batch.id`
- `specimen.collection_profile.id`
- `specimen.collection_profile.version`

Model spans additionally carry the application route ID, exact model ID,
upstream provider, requested prompt label, served prompt label, and prompt
version. Do not put GCS signed URLs, tokens, image bytes, transcripts, or
operator identities in span names.

Temporal workflow code must remain deterministic and replay-safe. Instrument
activities and active execution segments, not replayed workflow decisions. A
human pause can last days, so correlate resumed segments with workflow and run
IDs rather than holding one process span open for the entire pause.

## Managed prompts

The code declares these Logfire prompt variables:

| Prompt | Managed variable |
|---|---|
| Literal label transcription | `prompt__literal_label_transcription` |
| Structured field extraction | `prompt__structured_field_extraction` |
| Disagreement adjudication | `prompt__transcription_disagreement_adjudication` |

Each has a safe code fallback, typed inputs, and resolution evidence. Create the
matching prompts in Logfire, then use `development`, `candidate`, and
`production` labels. A promotion moves a label only after the candidate passes
the frozen offline dataset and review gate. Record the resolved version with
every run; a label by itself is not reproducible evidence.

Logfire Prompt Management currently requires an eligible plan and an enabled AI
Gateway for UI prompt tests. The gateway supports Hugging Face BYOK, but do not
route production specimen images through it until its data handling, region,
latency, and billing are approved. Direct Hugging Face inference remains the
production candidate in the meantime.

## Evaluation datasets and experiments

The checked-in synthetic dataset only proves that experiment reporting and the
scorer contract work. It is not a quality benchmark.

Create a frozen, expert-reviewed dataset for each collection profile and version
it by name, for example `insects/handwriting/gold/v1`. Each case should contain a
stable asset ID, expected literal transcript, line structure, explicit unreadable
spans, difficulty tags, and approved expected fields. Keep the image in Cloud
Storage; the evaluation runner retrieves it by ID.

The implemented literal-transcription scorers are:

- exact verbatim match;
- case- and punctuation-sensitive character accuracy;
- exact line structure; and
- exact preservation of unreadable spans.

Before production clearance, add structured-field exactness, evidence alignment,
unsupported inference, abstention, cross-model disagreement, latency, token,
cost-per-reviewed-record, and human-correction evaluators. LLM judges may help
with genuinely ambiguous cases but must be sampled and calibrated against expert
review; they are not clearance authority.

Every experiment records dataset version, prompt and fragment versions, route,
model/provider, schema version, collection-profile version, code commit, and data
classification. Compare a candidate experiment with the current production
baseline before moving a prompt label or model route.

## Live evaluation and human review

Run cheap deterministic online checks on every result: schema validity, required
evidence, unresolved ambiguity, route agreement, and queue disposition. Sample
expensive model-based checks. Alert on provider exceptions, validation retries,
latency, cost, disagreement, review rate, and queue age.

The installed Pydantic AI 2.40 package does not yet expose the documented
`OnlineEvaluation` capability, so this repository does not synthesize its
telemetry format. Add that capability only after upgrading to a verified release
and covering it with an end-to-end Logfire test.

Logfire annotations are supporting evaluation evidence, not the authoritative
review record. The application review queue remains the source of truth. Export
reviewed failures or sync them into a versioned dataset so each accepted failure
becomes a permanent regression case. Annotation queues are currently a beta or
design-partner capability and must not block the initial workflow.

## Commands

Metadata-only synthetic agent trace:

```bash
uv run specimen-logfire-smoke
```

Approved-content synthetic evaluation experiment:

```bash
uv run specimen-eval-smoke
```

Paid provider smoke with metadata only:

```bash
uv run --env-file .env specimen-huggingface-preflight \
  --live-route handwriting-qwen \
  --image /path/to/approved-fixture.png
```

Add `--approved-content` only when the prompt and output text may be retained in
the Logfire project. The image bytes remain excluded.

## External setup gates

The following require an explicit project-administration step rather than a
repository default:

1. Confirm Logfire plan access, project membership, US-region retention, and
   production data policy.
2. Create the three managed prompts and their labels in the Logfire UI.
3. Enable a development-only Logfire Gateway route if Prompt Playground tests
   against Hugging Face are approved.
4. Create the expert-reviewed dataset and assign its owner and freeze criteria.
5. Enable live evaluators after the supported SDK capability is verified.
6. Configure annotation queues if the beta feature is available to the project.
7. Create production dashboards and alerts only after the metric names and
   initial baselines are observed from the real workflow.
