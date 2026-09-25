# Go-live harness workstream (S4): spec deltas

Stages 6 to 8 of the go-live program ([PLAN.md](PLAN.md) section 4.1): the LLM
first pass, the agentic harness and the queue decision. Each pull request adds
its section here before its tests and implementation.

## 1. Tool calls keep their arguments when the conversation is replayed

The first pass and the harness are Pydantic AI agents on Hugging Face models
(G7), and their structured output and lookups are tool calls. Every model the
gateway returns must resend each earlier tool call with the exact arguments the
model produced, on every later turn: after a tool result, and on a retry after
invalid output (HAR-009). With pydantic-ai 2.40 and huggingface_hub 1.18 the
arguments were dropped, so DeepInfra rejected the second turn with HTTP 422 and
Novita passed an argument-less call to the model (observed 2026-09-23).

## 2. A step that fails after its external effect settled is a known block

Issue #80, G6 and QUE-005. A failure during a step's model or lookup call can
leave the call's outcome unknown. Once the call has returned,
a later deterministic failure in the same step, such as the phase check
`execute_phase` raising `EvidenceIntegrityError` after the extraction call in
`parse`, is a known operational block: the run records the failure's code
(`evidence_integrity_failure`, as `finalize` already does) or
`stage_failed_inspect_private_worker_logs`, releases the lease, does not charge
the provider's circuit, and accepts retry and reprocess. It is never
`external_outcome_unknown`, which retry and reprocess refuse. The exception's
class name is logged to the trace; its message is not, because it may carry
provider headers or label text.

## 3. The LLM first-pass call (stage 6)

The owner's rule (PLAN 2.1): "LLM does first pass at which final RAW transcript
should run against (it should also give at a VLM level what was returned to the
harness)". G7 runs it on a Hugging Face model; G19 and G20 decide what follows.
This section is the call; section 4 schedules it and records its decision.

**Input.** The crop the readers saw, each reading's raw transcript verbatim, and
the numbered differences between the readings from a deterministic token
alignment; a difference in whitespace alone is not listed. Readers appear as
Reader A, B, … in the profile's route order, never by model or route name.
Instructions are the pinned managed prompt
`transcription-disagreement-adjudication`, unchanged: its "route material
ambiguity to human review" is expressed by returning no reading and recording
the unresolved differences, and G19 then decides the route. The request states
that rule in the model's terms (**G19 in code**, below).

**Input binding** (the steward's review of #97, 2026-09-25). The readings must
be the region's own: each names the region and, when it records an input asset,
the run's asset; no reading appears twice; and they come in the profile's route
order. Otherwise the call blocks as `first_pass_contract_invalid` before any
request.

**Model and budget.** The profile's `first_pass_route`, pinned in
`run.dependencies` like the reader routes, provider pinned (no automatic
routing); a route that is not registered is not pinned, so the call blocks. A
call is budgeted like a reading: two requests (the answer and one output
retry), 16000 tokens, and the stage cost reservation `first_pass`, one key for
every region. Its circuit is the first-pass route's provider.

**A cap hit.** A first pass stopped by a G30 cap selects no reading: its token
total, or an answer cut off at its output cap (see **Failures**). G30 makes a
cap hit the raw fallback, and G19 then decides from the readings. The decision
records every difference as uncertain. Its call keeps the provider's usage up
to the stop and the responses kept before it (`completion_state`
`usage_limit`); Pydantic AI counts a response past the token total but does not
keep it.

**Output**, validated before it is used: the selected reader or none; for every
numbered difference exactly one verdict (a reader, `neither`, or `uncertain`); a
rationale; one note per reader. The first pass never writes text: the decided
transcript is the selected reading's literal text, verbatim. No merging, no
rewriting. The call's own provenance is an `Observation` (route, model,
provider, prompt version, the crop's digest as `input_sha256` like every
observation's, the text request's digest as `request_sha256`, raw responses,
tokens, latency, finish state) whose `literal_text` is empty.

**G19 in code** (the coordinator's reading of the prompt and G19, 12:31Z on
2026-09-25). A difference is material unless it is capitalization alone, and the
code decides it: a difference whose spans are equal once case-folded is not
material. The model is not asked. A pick stands only when every material
difference's verdict supports the picked reader, which is the prompt's "Resolve
a value only when the visual evidence supports it" with no merging. A material
difference left `neither` or `uncertain`, or supported by another reader, means
no reading, and every reading becomes a `raw_reading` handoff (G19). That is
neither a retry nor a block: the model's pick stays in the call's raw response
and its rationale.

**Failures** (G6, QUE-005, PRD section 15). A rate limit or another provider
error, HTTP 402 included, is retried with backoff through the workflow's
existing retry, then blocks as operational; an authentication or authorization
error blocks at once. A timeout or a server error may follow an accepted,
billable call, so, as for the readers, it is `external_outcome_unknown` and
waits for the operator. A response that still fails validation after Pydantic
AI's one output retry is `model_malformed_response`, a known operational block
that accepts retry; this applies to the readers' calls too. A missing pinned
route or prompt blocks as `pinned_model_route_unavailable` or
`pinned_prompt_unavailable`. None of these blocks produces a queue disposition.

An answer cut off at its output cap is not malformed but a cap hit (above): an
incomplete tool call, or a last response whose finish reason is `length`, raises
Pydantic AI's own `UsageLimitExceeded`, as the run's token and request limits do
(agreed with S3, 2026-09-25). The readers' calls share this split: PLAN 4.3
makes a reader stopped by its token cap a failed reading, which S3's #153
builds.

**Tracing.** The agent carries no instrumentation override; it inherits the
lane's global setting (content on, binary off in approved-content mode, S3 T5).

## 4. The first pass in the workflow, and what each region records

**When.** A region whose readings are all identical keeps today's behaviour
(the `adjudicate` step in `workflow.py`) and is recorded with `decision_kind`
`identical_readings`, the first reading as the decided transcript when the
region resolves. Every other region with at least two stored readings (TRN-001,
TRN-008) gets one external, billable step `first_pass:{region_id}` (section 3)
after its transcribe steps and before `adjudicate`; a run that already passed
`adjudicate` is never given one. A decision for another region, one naming a
reading the region does not have in its pick or a verdict, one whose `material`
flags differ from its spans, or one whose pick a material difference does not
support (G19) blocks as `first_pass_contract_invalid`.

**Recorded** on the region's `Transcript` (DATA_CONTRACT 4.2): `decision_kind`
`first_pass`, `selected_observation_id`, `text` (the selected reading verbatim,
or none), `first_pass_call` (the call's provenance), `reason` (the rationale),
`differences` (every verdict with each reading's span), and `handoffs`, one per
reading: the selected reading as `decided_transcript`, the others as
`raw_reading` (the harness's fallback); with no selection every reading is a
`raw_reading` (G19). `resolved` is true exactly when a reading was selected; a
difference left `neither` or `uncertain` stays on the record for the harness and
the queue decision (G19, G20). The disagreement score and the alignment fields
of stage 5 are unchanged. The run keeps each region's decision in
`first_pass_decisions`. Synthetic runs use a fixture that selects no reading.
