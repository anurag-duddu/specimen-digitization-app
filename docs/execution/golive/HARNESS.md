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
the unresolved differences, and G19 then decides the route.

**Model and budget.** The profile's `first_pass_route`, pinned in
`run.dependencies` like the reader routes, provider pinned (no automatic
routing); a route that is not registered is not pinned, so the call blocks. A
call is budgeted like a reading: two requests (the answer and one output
retry), 16000 tokens, and the stage cost reservation `first_pass`, one key for
every region. Its circuit is the first-pass route's provider.

**Output**, validated before it is used: the selected reader or none; for every
numbered difference exactly one verdict (a reader, `neither`, or `uncertain`)
and whether it is material (more than capitalization); a rationale; one note per
reader. The first pass never writes text: the decided transcript is the selected
reading's literal text, verbatim. No merging, no rewriting. The call's own
provenance is an `Observation` (route, model, provider, prompt version, digest
of the crop and request, raw responses, tokens, latency, finish state) whose
`literal_text` is empty.

**Failures** (G6, QUE-005, PRD section 15). A rate limit or another provider
error, HTTP 402 included, is retried with backoff through the workflow's
existing retry, then blocks as operational; an authentication or authorization
error blocks at once. A timeout or a server error may follow an accepted,
billable call, so, as for the readers, it is `external_outcome_unknown` and
waits for the operator. A response that still fails validation after Pydantic
AI's one output retry is `model_malformed_response`, a known operational block
that accepts retry; this applies to the readers' calls too. A missing pinned
route or prompt blocks as `pinned_model_route_unavailable` or
`pinned_prompt_unavailable`. None of these produces a queue disposition.

**Tracing.** The agent carries no instrumentation override; it inherits the
lane's global setting (content on, binary off in approved-content mode, S3 T5).

## 4. The first pass in the workflow, and what each region records

**When.** A region whose readings are all identical keeps today's behaviour
(the `adjudicate` step in `workflow.py`) and is recorded with `decision_kind`
`identical_readings`, the first reading as the decided transcript when the
region resolves. Every other region with at least two stored readings (TRN-001,
TRN-008) gets one external, billable step `first_pass:{region_id}` (section 3)
after its transcribe steps and before `adjudicate`; a run that already passed
`adjudicate` is never given one. A decision for another region, or one naming a
reading the region does not have, blocks as `first_pass_contract_invalid`.

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

## 5. The Hugging Face routes for the first pass and the harness (T1)

G7 runs the first pass and the harness on Hugging Face models through the
existing gateway. Two routes are registered, pinned like the readers' (model
and provider; routed inference exposes no model revision, and the preflight
checks each route is live with the capabilities it needs), and approved by the
coordinator on 2026-09-23:

| Route | Model | Provider | Input | Use |
|---|---|---|---|---|
| `first-pass-glm` | `zai-org/GLM-5.3-Flash` | `deepinfra` | text, image | the first pass (sections 3 and 4) |
| `harness-deepseek` | `deepseek-ai/DeepSeek-V4.1-Flash` | `deepinfra` | text | the harness; provisional until the acceptance lab re-measures it with the real harness |

Both use DeepInfra, which the `handwriting-muse` reader already uses, so no
new provider enters the data-policy review; neither shares a model family
with a reader.
They are a separate stage route set: the reader routes stay the gateway's
initial set, which the pilot launch, its stage list and the release check
compare a profile's readers against; the gateway resolves either set.

**How they were chosen.** The ten pilot slides, cropped by hand to their left
label, were read by both readers (19 of 20 readings; 9 labels disagree). Each
candidate ran the first pass as section 3 specifies (the managed prompt
unchanged, readers shown as A and B with the order alternating). Its verdicts
were scored against a full-resolution reading of the crops: 11 material
disagreements, 1 ambiguous span, 2 fluent traps (the label's "Chimaltenago",
which one reader corrected to "Chimaltenango") and 7 capitalization-only
differences. Candidates were ranked, as the coordinator set, by the fewest
confidently wrong verdicts, then the fewest failed traps, then the most
correct. The top three ran twice, the second time with the reader order
flipped.

| First-pass candidate (DeepInfra) | Valid answers | Confidently wrong | Traps failed | Correct | Abstained | Median seconds | USD per call |
|---|---|---|---|---|---|---|---|
| GLM-5.3-Flash | 16 of 16 | 2 and 2 | 0 and 0 | 6 and 6 | 3 and 3 | 11 | 0.0003 |
| Qwen3.5-397B-A17B | 6 of 8 (2 timed out at the router's 120 s) | 2 | 0 of 1 | 5 | 1 | 45 | 0.0058 |
| DeepSeek-V4.1-Flash | 16 of 16 | 3 and 4 | 2 and 1 | 6 and 5 | 2 and 2 | 10 | 0.0004 |
| MiniMax-M3 | 8 of 8 | 3 | 0 | 4 | 4 | 29 | 0.002 |
| Qwen3-VL-235B-A22B | 8 of 8 | 6 | 1 | 3 | 2 | 16 | 0.0004 |

Gemma-4-31B produced valid output once in eight calls; Kimi-K2.6 and Inkling
timed out at the router's 120 s limit on every call, which production would
record as an unknown outcome. GLM's two confident errors ("la" for "1a" and
"a" for "2") are in slide-preparation codes, not in fields.

The harness candidates ran four real scenarios with typed tools (live GBIF, a
geography tool answering `authentication_error`, a date parser and a catalog
validator), one of them the decided taxon "Epipocous" with "Epipsocus" as the
raw fallback. DeepSeek-V4.1-Flash completed all four, got all 9 key field
literals right, never looped, and took 16 s and USD 0.0017 per run; its misses
(three literals joined across label lines, one slide code taken as a date) are
the kinds the harness's deterministic checks turn into unresolved fields
(HAR-019). GLM-5.3-Flash took slide codes as dates three times; Qwen3-VL-235B
was slowest (71 s) and looped once; DeepSeek-V4-Flash-0731 looped to the
request limit once; Gemma-4-31B failed every run.

The measurement spent USD 0.106 of the program's USD 25 (G9): readers 0.016,
first pass 0.068, harness probe 0.021.

## 6. The harness's tools, and the taxonomy tool (stage 7, part 1)

HAR-007, HAR-008, HAR-009, HAR-010; owner decisions G23, G25, G28. A profile
maps each field to tool ids (S3's `CollectionProfile.field_tools`); the slide
pilot maps `taxon` to `taxonomy_verifier`, the five locality fields to
`geography_lookup`, `fmnh_ins_number` to `catalog_number_validator` and the
three date fields to `date_parser`. Every other field is transcribed as seen.

**Every tool** answers with a `ToolResult` (`application/harness_tools.py`):
exactly one HAR-008 outcome, the candidates behind it, and one `SourceCall` per
provider request with the query, the retrieval time, the outcome, the attempt,
the stored response and its digest, and on failure `retry_after` and a
sanitized error. The harness records one S5 `ToolCall` row per source call. A
rate limit, a timeout or a provider error is retried inside the tool with
backoff and jitter, never sooner than the provider's `Retry-After` and at most
three attempts, every attempt recorded (HAR-009); a `Retry-After` longer than a
step may wait ends the retries at once. No tool writes a field.

**`taxonomy_verifier`** (`application/taxonomy_tool.py`). The query is the
scientific name the literal writes: its first capitalized word and the
lower-case epithets after it, ending at a qualifier ("Epipsocus sp. 1" asks
for "Epipsocus"); a literal without one ("Sp. 30") is `no_match` with no
request. GBIF species match v2 against the pinned COL XR checklist decides the
outcome (G23), as GBIF.md 118-130 sets it:

- `success` (row 1): an exact match whose usage is accepted, has a key, sits in
  class Insecta, has the rank the label's name gives (a genus alone is genus
  rank, G25; a binomial is a species; a trinomial a subspecies), and has no
  plausible alternative.
- A *plausible alternative* (row 4) is another exact match of the same name
  whose status is accepted, provisionally accepted or doubtful and whose name
  with authorship differs: a live homonym. Synonym records of the same name,
  duplicates of the same name and authorship, and variant or fuzzy names stay
  in the evidence but are not plausible alternatives.
- `ambiguous`: an exact synonym (row 2: the label's name is kept and the
  accepted usage is proposed separately), a fuzzy or variant match (rows 3, 4),
  a higher-rank match (row 5), a plausible alternative, or a usage outside
  Insecta. `no_match`: GBIF matched nothing. A matchType GBIF documents, VARIANT
  included, is never `malformed_response`.

Global Names Verifier (Catalogue of Life and GBIF sources) and the Catalogue of
Life match API are asked as well, each its own source call. They never change
the outcome. When one of them answers differently from GBIF (success against
anything else) the result carries the warning
`taxonomy_source_disagreement:{source}`; when one is unavailable after its
retries, `taxonomy_support_unavailable:{source}`. BugGuide is not called. GBIF's
names may be stored (G28).

## 7. The geography tool on Google (stage 7, part 2)

G10, G12, G26, G29. `geography_lookup` (`application/geography_tool.py`) is the
first version of the geography tool behind the interface of section 6; an
accepted S8 plan replaces this module, not the interface.

**One call per reading** carries every locality literal of that reading. The
address is the reading's unassigned locality text when there is any, otherwise
its assigned literals from the most to the least precise field. The key comes
from `SPECIMEN_GOOGLE_MAPS_API_KEY`; a missing or rejected key is
`authentication_error`, an operational block (QUE-005). Retries follow section
6; an HTTP 401 or 403 is final at once.

**The mapping from Google's response to our outcomes is one function**,
`map_geocoding_response`, so that a pending owner decision changes only it. One
result without `partial_match` is `success`; a partial match or several results
is `ambiguous`; `ZERO_RESULTS` is `no_match`. Per field, a success needs every
literal of the field to equal, after folding (case, accents, punctuation and
label notations such as "Prov.", G29), the name of an address component at one
of the field's levels, or a name the profile's aliases give for it ("P.I." as
the Philippines); otherwise that field is `no_match`. `precise_location` is
never replaced and is not compared: it holds only when at least one sibling
field matched and none contradicted the result; otherwise it is `ambiguous`, so
a result in the wrong place (Denali for a Mindanao label) never vouches for it.

**What is kept** (G26, Google's terms): per request only the place ID, our
outcome and the sha256 of the full response. Google's names, address components
and coordinates are read in memory to compute the outcomes and are never
returned to the agent, stored, traced or logged. The key travels as a URL
parameter, the only form the Geocoding API accepts (a header key is refused,
checked 2026-09-23); a filter redacts it from the `httpx` log, and the lane must
not record raw request URLs in traces.
