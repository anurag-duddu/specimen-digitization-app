# S4 brief: LLM first pass and agentic harness

Session title: **Build the LLM first pass and agentic harness**. Recommended
model Opus 5.5 at high effort.

## Mission

Build stages 6, 7 and 8 exactly as the owner specified: the LLM first pass on a
Hugging Face model, a fully functional agentic harness with graceful failures,
and the queue decision. A strong harness comes later; a fully functional one
comes first (G6).

## Read first

1. `docs/execution/golive/PLAN.md`: sections 1, 2 and 4.1 rows 6 to 8.
2. `~/specimen-golive/research/06-product-spec-and-approvals.md` sections 1 and
   4, and `01-backend-pipeline-stages.md` stages 5 to 8.
3. `docs/product-requirements/PRD.md` HAR-001 to HAR-019 (322-340), QUE-001 to
   QUE-005 (386-390), section 12.4 (484-564) and the failure table (673-685);
   `docs/execution/CONTRACTS.md` 210-260; `docs/GBIF.md`;
   `docs/product-requirements/HUGGINGFACE_MODEL_ROUTING.md` and
   `HARNESS_OPTIONS.md`.
4. Code: `prompts.py`, `application/harness.py`, `evidence_harness.py`,
   `lookup.py`, `parties.py`, `geography.py`, `policy.py`, `workflow.py`
   353-719, `model_gateway.py`.

## The owner's rules, verbatim where possible; do not reinterpret them

- "LLM does first pass at which final RAW transcript should run against (it
  should also give at a VLM level what was returned to the harness)." The first
  pass decides which of the readers' raw transcripts the harness runs against,
  and records, per reader, the reading and what was handed to the harness. Use
  the existing managed prompt `transcription-disagreement-adjudication`
  (`prompts.py` 63-72). Keep the existing behaviour when all readings are
  identical (`workflow.py` 353-375) and record it the same way. Do not build a
  merging or rewriting adjudicator.
- "agentic harness takes the finally decided raw transcript runs lookups (can
  rely on raw for a final check if LLM decided transcript output fails, if both
  fail send to relevant queue) with databases identified, (function call tool
  call etc this can be dependent on collection/subcollection, mandatory vs
  optional)".
- "When I say something that harness was able to resolve is cleared it is
  cleared." "mandatory fields if cleared then cleared, and once harness returns
  decide queue (human, deferred, cleared)". Which non-cleared queue is relevant
  follows the specification: needs human review per QUE-003, deferred only for
  the model-capability limits of QUE-004.
- "graceful failures are important. no data found, an error occurred, retry and
  so on. I am aware there is not always available data and thats when it goes to
  the need a human queue." No data found sends the record to the human queue with
  the reason. An error is retried with backoff; when retries are exhausted it is
  an operational block with retry (QUE-005), shown as blocked, never a crash.
  Every outcome is typed (HAR-008) and recorded.
- Never invent values (HAR-019). Every literal comes from the decided transcript
  or a raw reading, with provenance.
- G5: when the specification is silent or contradictory, ask the coordinator.

## Pull requests, in order

Each starts with its spec delta in `docs/execution/golive/HARNESS.md` and
failing tests (fakes for Hugging Face and HTTP; recorded real responses as
fixtures), then the implementation.

**T1. Hugging Face routes (G7).** The first pass sees the label crop, so it
needs a vision model; the harness needs reliable tool calling or structured
output. Choose provider-pinned models available through Hugging Face Inference
Providers, measure them on real crops (the acceptance lab has crops;
`specimen-huggingface-preflight` makes paid preflight calls; a local Hugging
Face token exists, never print it), and register them in `model_gateway.py` like
the existing routes. Report the choice and the measurements to the coordinator
before building on them.

**T2. The first pass (stage 6).** Persist the decision and the per-reader
records into S5's contract.

**T3. The harness (stage 7).** A Pydantic AI agent over typed tools from the
profile's registry: GBIF Species Match v2 (the existing adapter, `lookup.py`),
Global Names Verifier and Catalogue of Life for taxonomy; Google Maps geocoding
for geography (G10; the key comes from Secret Manager, and until the owner
creates it the tool returns the typed `unavailable` outcome and the field goes
to review); the deterministic validators for catalog numbers and dates; parties
returns `unavailable` because EMu Parties is not provisioned, and person names
are transcribed as seen. Phases as the specification lists them; the raw-reading
fallback; retries with backoff; a budget check per paid call; every tool call
recorded for S5 and traced with Pydantic AI instrumentation, content on (G3;
coordinate with S3's tracing topic).

Geography is being researched separately (owner decision G12, session S8,
`briefs/S8-georeferencing-research.md`): historical toponyms, tiered
resolution and uncertainty. Build geography as one typed tool behind the same
interface as the others, with the Google Maps implementation of G10 as the
initial version, so that an accepted S8 plan replaces the tool without touching
the harness. Share the tool interface with S8 when it exists.

**T4. The queue decision (stage 8).** The policy applies G1. For the lane,
remove the gates that contradict it: `policy.py` 31-34 (institutional approval
and semantics) and 138-139 (`human_approval_required`), and `worker.py` 318-323
(`pilot_clearance_forbidden`). Human deferral in `api.py` 1940-1967 stays for
people; the harness may also defer under QUE-004. Tests cover every path: all
mandatory fields resolved, cleared; no data, needs human review with the reason;
capability limit, deferred; transient error, retried, then an operational block.

## Coordination

S3 supplies the profile, the tools per field, the optional fields and the
tracing mode. S5 supplies the tables for the first-pass decisions, the tool calls
and the fields; agree the shapes in S5's first PR. S2 supplies the secrets and
environment. S7 supplies real crops and recorded responses.

## Done

On a real specimen run locally, the first pass and the harness run with a typed
outcome for every lookup, fall back to the raw readings when needed, and the
queue decision follows G1, with every artifact persisted and traced.
