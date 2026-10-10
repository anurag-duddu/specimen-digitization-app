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

The owner's words (PLAN section 1): "LLM does first pass at which final RAW
transcript should run against (it should also give at a VLM level what was
returned to the harness)". G7 runs it on a Hugging Face model; G19 and G20
decide what follows. This section is the call; section 4 schedules it and
records its decision.

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
call is budgeted like a reading: two requests (the answer and one output retry),
16000 tokens, the stage cost reservation `first_pass`, one key for every region,
and, like every billable step, 16,000 of the run's tokens. Each region's
`first_pass` reservation is sized by PLAN 4.3 in S3's route wiring PR: each
request from the crop, with 20,000 micro-dollars as its floor, and the call
reserves the sum of its two requests. The same PR names the pilot's first-pass
route; until then no lane run has a first pass. Its circuit is the first-pass
route's provider.

**A cap hit.** A first pass stopped by its caps, its token total or an answer
cut off at its output cap (see **Failures**), returns no answer, so it selects
no reading. The owner's pipeline "can rely on raw for a final check if LLM
decided transcript output fails" (PLAN section 1), and G19 sends each reader's
raw reading to the harness. The decision records every difference as uncertain.
Its call keeps the provider's usage up to the stop and the responses kept before
it (`completion_state` `usage_limit`); Pydantic AI counts a response past the
token total but does not keep it.

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
code decides it: a difference whose spans are equal once lower-cased is not
material, so a spelling variant such as "Straße" against "Strasse" stays
material (the coordinator's ruling at 14:05Z, which reads 12:31Z's "case-folded"
as lower-cased). The model is not asked. A pick stands only when every material
difference's verdict supports the picked reader, which is the prompt's "Resolve
a value only when the visual evidence supports it" with no merging. A material
difference left `neither` or `uncertain`, or supported by another reader, means
no reading, and every reading becomes a `raw_reading` handoff (G19). That is
neither a retry nor a block (the coordinator's confirmation at 12:32Z): the
model's pick stays in the call's raw response and its rationale.

**Failures** (G6, QUE-005, PRD section 15). For the first pass, the organiser
and the legacy extraction call (a reader's are below): a rate limit or another
provider error, HTTP 402 included, is retried with backoff through the workflow's
existing retry, then blocks as operational; an authentication or authorization
error blocks at once, and so does a request the provider refuses as invalid
(HTTP 400, 404, 413 or 422), as `model_request_rejected`, since asking again
repeats it. A timeout or a server error may follow an accepted, billable call,
so it is `external_outcome_unknown` and waits for the operator. A response that
still fails validation after Pydantic AI's one output retry is
`model_malformed_response`, a known operational block that accepts retry; this
applies to the legacy extraction call in `parse` (`harness.py`) and the first
pass too. A missing pinned route or prompt blocks as
`pinned_model_route_unavailable` or `pinned_prompt_unavailable`. None of these
blocks produces a queue disposition.

An answer cut off at its output cap is not malformed but a cap hit (above): an
incomplete tool call, or a last response whose finish reason is `length`, raises
Pydantic AI's own `UsageLimitExceeded`, as the run's token and request limits do
(agreed with S3, 2026-09-25). The readers' calls and the legacy extraction call
share this split. PLAN 4.3 makes a reader stopped by its token cap a failed
reading: its step completes with no observation (`ReadingStopped`, from #153's
re-cut #232) and is not asked again; the legacy extraction call has no cap
handler, so a cap hit there, a length stop included, blocks as
`external_outcome_unknown`.

**A reader's failures** (G6, 2026-10-09). A reading is a pure read: the parent
saves its observation only after the call returns, so asking again cannot corrupt
data or duplicate an observation, and costs one more reservation. A reader whose
child ends as anything but an answer (a deadline, a kill, a transport error, an
exception the child does not map), or whose provider answers 429, a server error,
a timeout or a malformed answer (HTTP 402 included), is therefore a known
failure and never `external_outcome_unknown`. A reader that answers after its
effect timeout keeps its observation. The workflow retries the step through its
existing retry (`max_attempts`, backing off); each attempt reserves its cost
again, and an attempt whose outcome is unknown keeps its reservation in full
(PLAN 4.3). When the attempts are used up, the step completes with no
observation, as for a cap hit, and the queue decision sends the record to review
with `independent_observations_missing:{region}`; a region no reader could read
keeps a transcript with no text and no readings. Every reading that gave no
observation is recorded in `paid_calls` as `failed` with its `failure_code`, and
its reservation stays held in full (`cost_basis: reserved`). An authentication or
authorization error, and a request the provider refuses as invalid (HTTP 400,
404, 413, 422: `model_request_rejected`), still block at once and name their
cause, since asking again repeats them. A reviewer cannot record supported text
for a region no reader read (the decision is refused, 422, and the record is
unchanged: verification would refuse text with no reading to trace to); an
abstention still can be recorded.
The rule is `reliability.reader_failure_is_recoverable`; the first pass, the
organiser, field research and every effectful step keep their unknown outcome as
a block, and so does a reader of the evidence pilot, whose exact cohort
reservations and zero retries never replay a paid call (a pilot reader that is
stopped by its limits ends as `external_outcome_unknown` too). A run that was
already blocked as `external_outcome_unknown` stays so.

**Tracing.** The agent carries no instrumentation override; it inherits the
lane's global setting (content on, binary off in approved-content mode, S3 T5).
The pinned managed prompt reaches the call's span through Pydantic AI's
`include_model_request_parameters`: it is static text, and G3 asks for every LLM
level's system prompt to be visible in Logfire.

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
support (G19; the coordinator's 12:31Z reading) blocks as
`first_pass_contract_invalid`. A call that comes back naming another route or
another asset is refused as `external_outcome_unknown`, as a reading's is.

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
`first_pass_decisions`. Synthetic runs use a fixture that selects no reading;
its call names the input the readers saw.

**Checked at finalize** (the steward's reviews of #98). The evidence check
(`integrity.py`) verifies each first-pass call's raw responses, region and input
(the region's crop, and the bytes at `input_crop_ref`). A machine transcript,
one no reviewer's decision has changed, must have text that is none or one of
its region's readings, verbatim, and none when a machine kind selected nothing.
A machine-selected reading must be one of the region's readings, with `text` its
literal. A region the run holds a first-pass decision for is recorded as
`first_pass`, with the pick and call that decision records, and a pick G19
allows.

**The extraction call is the organiser** (owner, 2026-10-03, relayed by the
coordinator, replacing the earlier rule that this call received the decided text
alone): "maybe the LLM that looks at the raw transcript can organize the data into
field value pairs and share it with the harness along with the transcript.
Because if the data is kinda spread out on different labels it becomes a little
chaotic. taxa can be on multiple else. So the first agent LLM that interfaces with
raw VLM transcripts can do this. The reason raw transcript is important is
because LLM can make mistakes and invent stuff so evidence is always necessary."
The call (`harness.extract_with_agent`, still one text-only call per specimen on
the profile's first reader route) receives every non-empty reading of every
region, named 1A, 1B, 2A ... as the stage-7 harness names them
(`field_harness.labelled`): a resolved transcript's text as the decided
transcript, every other reading as a raw reading, and every reading of a region
with no decided transcript as a raw reading. It does not receive the first-pass
notes, differences or call. It returns candidates, several per field when the
labels or the readers differ or repeat, each naming the one reading it quotes with
a short quote and the literal. `harness.apply_candidates` keeps a candidate only
when the quote is an exact substring of that reading and the literal an exact
substring of the quote, runs the extraction guard on that reading's text, computes
every offset itself and stores one evidence row per candidate; the stored shape
is in `application/organiser.py`. A field's value is settled as
`field_resolution.Resolver` settles a field no tool checks (G19, G27, G32), whatever
the order of the model's answer: a label with a decided transcript has the decided
reading's literal (the other reader's differing literal does not contest it); a label
with no decided transcript has a value only when every one of its readings states the
same literal, so a reader that does not state the field, or readers that differ, leave
it AMBIGUOUS with no literal (none is chosen); labels that all have a value and agree
leave the field SUPPORTED, any other mix of labels AMBIGUOUS with no literal. Every
verified candidate's row stays cited by the field, in every state, for the harness to
check against the raw readings; a candidate quoted from the other reader's reading of
a decided label is evidence beside the value, never the value. The first version of
the organiser did not follow the Resolver on a label with no decided transcript (one
reader's literal was a value; readers that differed gave the first in the model's
order); `tests/test_organiser.py` now runs the Resolver and `apply_candidates` on every
combination of one and two labels and compares. A cut-off answer is still not handled
(the legacy extraction call has no cap handler: it blocks the run as
`external_outcome_unknown`, as section 3 says), and the answer grows with the readings:
about 185 output tokens per reading on average and 297 at most in the replay against the
4,096-token cap, so about seven labels (14 readings at the worst ratio, 22 at the average)
is where a cut-off becomes possible (INFERRED from the nine replayed specimens).

**Lane P hand-over and exact local settlement (source, 2026-10-04).** The
ordinary organiser's verified candidate rows retain a quote from each named
reader, including readers of labels the first pass did not decide. The research
request re-finds each candidate's unique literal span in that reading, presents
at most five candidates per field with an explicit truncation marker, and never
uses stored offsets to place a value. Its five simple literal fields may form
an assembly from a decided reading or unanimous raw readers. An explicit
collection-date or determination-date line may form a date assembly only when
every retained reader of one label quotes the same unambiguous date and no
competing event claim exists. A collection date may settle From and G44's
derived To; it never fills dateIdentified. An explicit Elevation/Elev./Altitude/Alt.
line may form one elevation assembly only for an exact single quantity with a
written metre or foot unit, unanimous readers and no competing measurement.
Ranges, unitless or approximate quantities, ambiguous date order, silent
readers, unreadable spans and collisions remain candidates for review. These
rules do not assign a field from the model's candidate alone.

The temporal and measurement specialists' v6 prompts call scoped local
`settle_temporal` and `settle_elevation` utilities on the accepted event and
assembly IDs. Those utilities return the exact validator-generated
`FieldResolution` objects, including G44/G41 derivations and native evidence
relations. Publication replays the utilities from the immutable request; a
changed relation, authority, value or assembly fails closed. They are local
computations, not outside source authority. Geography and taxonomy still need
their qualified lookups, and fields with no qualified assembly or source remain
unresolved under the pinned missing-policy rule.

## 5. The Hugging Face routes for the first pass and the harness (T1)

G7 runs the first pass and the harness on Hugging Face models through the
existing gateway. Two routes are registered. S4 recommended them in its T1
report to the coordinator at 22:48Z on 2026-09-23, and the coordinator approved
them on that report's figures (its message to S4 at 22:52:14Z;
coordinator.md:58). The first-pass table below recomputes those figures from the
same saved calls (2026-09-25): its seconds are medians, where the report's were
mostly means, and it adds MiniMax-M3's second run, which finished after the
report. Neither pick changes.

| Route | Model | Provider | Input | Use |
|---|---|---|---|---|
| `first-pass-glm` | `zai-org/GLM-5.3-Flash` | `deepinfra` | text, image | the first pass (sections 3 and 4) |
| `harness-deepseek` | `deepseek-ai/DeepSeek-V4.1-Flash` | `deepinfra` | text | the harness; provisional until the acceptance lab re-measures it with the real harness and G29's prompt |

Both use DeepInfra, which the `handwriting-muse` reader already uses, so no
new provider enters the data-policy review; neither shares a model family
with a reader.
They are a separate stage route set: the reader routes stay the gateway's
initial set, which the pilot launch, its stage list and the release check
compare a profile's readers against; the gateway resolves either set.

**Pinned by model id and provider**, as the readers are. The approval message
said "Pin both routes (provider and model revision) as the readers are pinned";
the coordinator's ruling at 19:21Z on 2026-09-25 (option (a),
coordinator.md:456) corrected "provider and model revision" to "model id and
provider", on S4's finding that Hugging Face routed inference exposes no model
revision. The router's `/v1/models` entries in S4's T1 catalog snapshots
(2026-09-23) give each model's id, owner, creation time and architecture and,
for each provider, its status, pricing, context length, latency, throughput and
tool and structured-output support, but no revision. A chat-completions
response, as `huggingface_hub` 1.18.0 parses it, has `id`, `created`, `model`,
`system_fingerprint`, `choices` and `usage`, and no revision either. Each reader
and first-pass call keeps its provider responses, and in them the response's
`model` (Pydantic AI's `model_name`), so a version string a provider puts there
is on the record without a new field. Pydantic AI 2.40 does not keep
`system_fingerprint`, and no field is added for it (the coordinator's ruling at
19:29Z, coordinator.md:458). The preflight checks each route is live with the
capabilities it needs.

**Each route in its role** (the steward's review of #107). A reader is pinned
from the initial reader set only, as on main, so a profile that names the
first-pass or the harness route as a reader fails the pin step. A reader call
blocks as `pinned_model_route_unavailable` unless its route is a
`handwriting_transcriber` with image input; `transcribe_label_image`, which has
no caller, raises `ModelGatewayConfigurationError` on any other route. The
first-pass route is pinned only when it is registered as
`transcription_first_pass` with image input, and the first-pass call checks the
same before its request: any other route, the harness's text-only one or a
reader's included, blocks the step as `pinned_model_route_unavailable`.

**The paid smoke test** (`specimen-huggingface-preflight --live-route`) runs one
synthetic prompt under a reading's caps: 4,096 output tokens a response, two
requests (the answer and one output retry), and a stop once the run passes
16,000 tokens in all (Pydantic AI checks the total after each response). A route
that takes images needs the `--image` fixture and is sent it; a text-only route
is sent a synthetic sentence, never an image, and refuses `--image`.

**How they were chosen.** The ten pilot slides, cropped by hand to their left
label, were read by both readers (19 of 20 readings; 9 labels disagree). Each
candidate ran the first pass as section 3 specifies (the managed prompt
unchanged, readers shown as A and B with the order alternating). Its verdicts
were scored against S4's full-resolution reading of the crops: 11 material
disagreements, 1 ambiguous span, 2 fluent traps (the label's "Chimaltenago",
which one reader corrected to "Chimaltenango") and 7 capitalization-only
differences. Candidates were ranked by the fewest confidently wrong verdicts
(S4's criterion, which the coordinator agreed), then by the coordinator's
tie-breaks (its message to S4 at 21:45:54Z on 2026-09-23): the fewest failed
traps, then the most correct. The table follows that order on each candidate's
first run. GLM, MiniMax and DeepSeek ran a second time, with the reader order
flipped. Median seconds are over a candidate's valid calls, leaving out calls
that waited on retries after an HTTP 402 (payment required), nine in the table,
seven of them in DeepSeek's first run; USD per call is the mean over its valid
calls.

| First-pass candidate (DeepInfra) | Valid answers | Confidently wrong | Traps failed | Correct | Abstained | Median seconds | USD per call |
|---|---|---|---|---|---|---|---|
| GLM-5.3-Flash | 16 of 16 | 2 and 2 | 0 and 0 | 6 and 6 | 3 and 3 | 11 | 0.00029 |
| Qwen3.5-397B-A17B | 6 of 8 (2 timed out at the router's 120 s) | 2 | 0 of 1 | 5 | 1 | 22 | 0.0057 |
| MiniMax-M3 | 16 of 16 | 3 and 6 | 0 and 2 | 4 and 4 | 4 and 1 | 25 | 0.0018 |
| DeepSeek-V4.1-Flash | 16 of 16 | 3 and 4 | 2 and 1 | 6 and 5 | 2 and 2 | 4 | 0.00040 |
| Qwen3-VL-235B-A22B | 8 of 8 | 6 | 1 | 3 | 2 | 8 | 0.00035 |

Gemma-4-31B produced valid output once in eight calls; Kimi-K2.6 and Inkling
timed out at the router's 120 s limit on every call, which production would
record as an unknown outcome. GLM's two confident errors ("la" for "1a" and
"a" for "2") are in slide-preparation codes, not in fields.

The harness candidates, each served by DeepInfra, ran four real scenarios with
typed tools (live GBIF, a geography tool answering `authentication_error`, a
date parser and a catalog validator), one of them the decided taxon "Epipocous"
with "Epipsocus" as the raw fallback. DeepSeek-V4.1-Flash completed all four,
got all 9 key field literals right, never looped, and took 16 s and USD 0.0017
per run; its misses (three literals joined across label lines, one slide code
taken as a date) are the kinds the harness's deterministic checks turn into
unresolved fields (HAR-019). GLM-5.3-Flash took slide codes as dates three
times; Qwen3-VL-235B was slowest (71 s) and looped once; DeepSeek-V4-Flash-0731
looped to the request limit once; Gemma-4-31B failed every run.

The measurement spent USD 0.106 of the program's USD 25 (G9): readers 0.016,
first pass 0.068, harness probe 0.021.

## 6. The harness's tools, and the taxonomy tool (stage 7, part 1)

HAR-007, HAR-008, HAR-009, HAR-010; owner decisions G23, G25, G26, G28 and G35.
A profile maps each field to tool ids (S3's `CollectionProfile.field_tools`);
the slide pilot maps `taxon` to `taxonomy_verifier`, the five locality fields to
`geography_lookup`, `fmnh_ins_number` to `catalog_number_validator` and the
three date fields to `date_parser`. Every other field is transcribed as seen.

**Every tool** answers with a `ToolResult` (`application/harness_tools.py`):
exactly one HAR-008 outcome, the candidates behind it, and one `SourceCall` per
provider request with the query, the retrieval time, the outcome, the attempt,
the source's licence, the stored response and its digest, and on failure
`retry_after` and a sanitized error. The harness records one S5 `ToolCall` row
per source call. A rate limit, a timeout or a provider error is retried inside
the tool with backoff and jitter, never sooner than the provider's
`Retry-After` (an HTTP-date is rounded up to the next second) and at most three
attempts, every attempt recorded (HAR-009); a `Retry-After` longer than a step
may wait ends the retries at once. No tool writes a field. The types keep G26:
a Google place candidate carries a place ID and no name or components, and a
georeference candidate names at least one source, none of them Google (G35's
openly licensed sources only). A Google source call's stored record is the
tool's own (place ID, outcome and response fingerprint), never Google's body:
that is S4's stated rule for the Google tool (#113), not a type check.

**`taxonomy_verifier`** (`application/taxonomy_tool.py`). The query is the
scientific name the literal writes, read from its leading words. The reader
fails closed (the steward's review of round 3): a word it does not take marks
the name read only in part. It sends only the words it reads as the name, and
each of its lists holds only the words it lists, so what syntax cannot settle
(below) bounds what it keeps out. This is S4's reading of PLAN 4.8 and
`GBIF.md` 109, as the steward's reviews of rounds 1 to 4 tightened it:
- **First** the text is normalized to NFC, and format characters (zero-width
  spaces, soft hyphens and the like) are dropped.
- **The name**: a title-case genus; optionally a parenthesized subgenus, written
  out or abbreviated ("(Pyrobombus)", "(P.)"); epithets in lower case, with any
  accents and inner hyphens ("impatiëns", "c-album"), or an old capitalized
  epithet with a patronym's or a place's ending ("Smithi", "Canadensis") that
  does not begin an author-year authorship ("Rossi, 1790" is an author); and a
  subspecies or variety marker with its epithet ("ssp.", "var."). Trailing
  punctuation is not part of a word. A word ending in a comma, a semicolon, a
  colon or a period is the name's last: only an authorship or a word that ends
  the name may follow it, and any other word marks the name read only in part
  ("Bombus impatiens, Davao").
- **Qualifiers** (the coordinator's reading of G25 and G28 at 01:11Z on
  2026-09-26, coordinator.md:504, with its confirmation of 03:31Z,
  coordinator.md:531). A qualifier right after the genus ("sp. 1", "cf.",
  "aff.", "nr.") makes a genus-level identification: the genus is asked and may
  clear, and the species is never asked. A qualifier before the genus, or a
  question mark on it, leaves the genus in doubt: nothing is sent, and the name
  goes to review as ambiguous ("cf. Bombus impatiens", "Near Davao 1946",
  "Bombus? impatiens").
- **Words that end the name**: nothing after them is read, and the name is not
  marked unless an epithet-shaped word follows (below). They are the words the
  reader lists, and no others:
  - person clauses, by the markers listed in English, Spanish, Latin, French
    and German, abbreviated or spelled out ("det.", "coll.", "determinado",
    "colectado", "determinavit", "lgt.", "vid.", "teste", "dét.", "Sammler"),
    which cut the literal where they stand;
  - the prepositions listed as ends ("in", "en", "por", "prope", "bei", "with"),
    and the particles of an author's name ("de", "van", "du", "la"), which may
    still begin one;
  - the sex, life-stage, type-status and nomenclatural words listed ("female",
    "fem.", "juv.", "imago", "paratype", "alotipo", "nov.");
  - the months listed, in full or abbreviated, in English and Spanish ("June",
    "Aug.", "julio"), and the Roman months I to XII but V and X;
  - a number or a written date ("1946", "13-5-48", "12.v.1948"), and sex signs
    ("♀").
- **An epithet-shaped word after an end word marks the name** (the steward's
  review of round 4), since it may be the name's own: "Coccinella 7 punctata",
  "Bombus ♀ impatiens" and "Xus yus de zus" go to review. A qualifier right
  after the genus is the exception above.
- **Words that change the taxon mark the name** (the steward's review of round
  4): a group, a complex or an aggregate ("group", "gr.", "grupo", "complex",
  "complejo", "agg."), a concept ("sensu", "auct."), and "et" joining two
  names. So "Formica rufa group", "Bombus impatiens auct. nec Cresson" and
  "Bombus impatiens et fervidus" go to review and never clear as the species.
  A "V" or "v." standing alone may be "var.", so it marks the name too
  ("Carabus auratus v. lotharingus").
- **Other listed words mark the name.** The reader also lists other
  prepositions, articles and conjunctions in those languages ("sur", "auf",
  "bajo", "sub", "the", "und"). It never reads one as an epithet, and the name
  does not end on one, so the name is read only in part and nothing after it is
  sent ("Epipsocus bajo corteza, Petén 1987").
- **Authorship**, only in the author-year form and bounded: one to four authors
  (title-case surnames, never a listed month or a Roman month, with particles
  such as "de" and initials such as "F."), joined by "&", "et" or a comma, then
  a year, in parentheses or not ("Linnaeus, 1758", "(de Geer, 1775)", "Smith &
  Jones, 1901"). A joiner needs an author after it, so "Smith & 1900" is no
  authorship (S4's grammar).
- **Place text is never sent** (PLAN 4.8: "The taxonomy tools send the taxon
  name, never place text"). The place text is the reading's place-field
  literals and unassigned locality text, compared as PLAN 4.8 folds them (case,
  diacritics and punctuation set aside), word by word and as whole literals.
  - **It leaves the authorship** (the coordinator's ruling of 02:07Z on
    2026-09-26, coordinator.md:515). Before a taxonomy request is built, every
    token of the authorship that shares a folded word with the place text is
    dropped, and the name is read again until its authorship holds none; what
    remains is sent or refused by the rules above. So "Epipsocus Davao,
    Mindanao 1946", with "Davao" and "Mindanao" in the place text, is asked as
    "Epipsocus", and "Epipsocus corteza, Petén 1987", with "Petén", as
    "Epipsocus corteza": neither pin's request carries a place word. A real
    author who shares a word with the place text loses it ("Xus yus Davao,
    1900" is asked as "Xus yus"): a weaker match, which the ruling accepts as
    failing safely. A drop that changes the genus, subgenus, epithets or rank
    marks the name, which is asked as first read without its authorship
    ("Carabus Smithi Lewis, 1900", with "Lewis County", is asked as "Carabus
    Smithi"; the steward's review of round 4).
  - **A name part equal to it is withheld** (the coordinator's ruling of 03:24Z
    on 2026-09-26, coordinator.md:527, word by word as confirmed at 03:31Z,
    coordinator.md:530). A genus, subgenus or epithet whose folded form equals
    a folded word of the place text, or a whole folded literal, is not sent:
    the name is asked only up to it, marked, and goes to review as ambiguous.
    So with "Davao" or "Davao City" in the place text, "Epipsocus davao 1946"
    and "Epipsocus (Davao) 1946" are asked as "Epipsocus", and "Davao" alone
    sends nothing. A Latinized epithet is still asked ("Epipsocus
    davaoensis"). The stated cost: a real name part equal to a place word of
    the same reading goes to review too.
  - The tool takes the place text from its caller, the harness, as a sequence
    of texts; a bare string is refused. The workflow's `lookup` step passes the
    literals of the run's place fields (`country`, `province_state`, `county`,
    `city`, `precise_location`); it holds no unassigned locality text, so there
    only those count.
- **Bounds**: only the first 40 words are read, a literal with a word over 64
  characters before any person clause writes no name, and authorship is at most
  four authors and 200 characters.
- **A name read only in part never succeeds.** Any other word after the name or
  its authorship marks it, and so do a hybrid sign ("×", "x", "X", "✕"), a
  marker the reader does not take ("ab.", "f.", "forma", "morph") and a marker
  without its epithet ("ssp. Zus"). The query is the name as far as it was
  read, without the rest, and the match can only be `ambiguous`: the result
  warns `taxonomy_name_partly_read`, and the lookup records why in
  `partly_read`: the word it could not read, "hybrid", or `place_word` for
  place text (a doubt on the genus records its qualifier or "?"). So
  "Coccinella 7-punctata", "Bombus impatiens?", "Bombus 'impatiens'", "Bombus
  impa-" at a line's end, "Bombus impatiens / fervidus", "Epipsocus Mt. Apo
  1946", "Apis mellifera L." (an author without a year) and "Epipsocus Hagen,
  1866 Davao" go to review, never clearing at genus or species.
- **What syntax cannot settle** (S4's reading): a word in a name's place reads
  as that part of the name, and a list holds only the words it lists.
  - A lone title-case word such as "Davao" or "Werner" reads as a genus. A
    lower-case word after the genus, such as "corteza", reads as an epithet
    unless a list holds it. A title-case word with a patronym's or a place's
    ending, such as "Hawaii" or "Suzuki", reads as a capitalized epithet, and
    "(Davao)" as a subgenus.
  - After a name, title-case words and a year in the author-year form read as
    authorship ("Genus Word Year": "Epipsocus Davao 1946", "Epipsocus Werner,
    1946", "Epipsocus Davao, Mindanao 1946").
  - A person-clause marker or a month the lists do not hold reads the same
    way. "Epipsocus collegit Werner 1946", "Epipsocus récolté Werner 1946",
    "Epipsocus recogido: Werner 1946", "Epipsocus bestimmt von Werner 1946" and
    "Epipsocus gesammelt von Werner 1946" read the marker as an epithet and the
    rest as authorship; "Epipsocus Juni 1946", "Juin", "Okt." and "Iunius" read
    as authorship.
  - Each is then sent as part of the name, except the reading's place text
    (above), so a place that text does not hold, or a person, can still go out.
    Nothing else is sent: the query holds only the name's parts, as far as they
    were read.

A literal that begins with no genus ("Sp. 30 ♀ Davao", "det. Mockford", "Coll.
F. G. Werner", "collected by Werner 1946") is `no_match` with no request. The
label's rank follows from the name: a genus alone is genus rank (G25), one
epithet a species, a subspecies or variety its own rank. The workflow's `lookup`
step goes through the same reading, so it sends no request for such text
either, and a species label never clears there at genus. A name with nothing it
may send (its genus in doubt, or place text) is `ambiguous` with no request; its
lookup stores a record of what was withheld and why, with its digest, so the
run's evidence check reads it like any other lookup and the name reaches review
(the steward's review of round 5).

GBIF species match v2 against the pinned COL XR checklist decides the outcome
(G23), under the coordinator's ruling that success is `GBIF.md` 126-130's (S4
brief 166-170; coordinator.md:19), as its rulings of 22:46Z on 2026-09-25
refine it for homonyms and correct it for exact synonyms, which the brief sent
to review (coordinator.md:476-478). GBIF is sent the name with its authorship
when written, `taxonRank`, kingdom Animalia and class Insecta from the profile,
and the checklist key (`GBIF.md` 107-114; PLAN 4.8).

- `success` (row 1, `GBIF.md` 126): an exact match whose usage is accepted, has
  a key, has the label's canonical name (`canonicalName`, compared exactly) at
  the label's rank, sits in class Insecta (the compatible classification, as
  the coordinator ruled at 22:46Z), and has no homonym conflict, for a name
  read in full.
- A *homonym conflict* (row 4, `GBIF.md` 129, as the coordinator ruled at
  22:46Z): another exact alternative with the same canonical name and other
  authorship, in class Insecta, whatever its status. Non-exact alternatives,
  alternatives outside the class, and a duplicate of the same name and
  authorship stay in the evidence but do not count. An exact alternative
  missing its class or its canonical name counts, and so does one whose
  authorship, like the usage's, is empty: nothing shows either is another name
  (the steward's review of round 2). The usage itself, by its key, never counts.
  The pilot's "Epipsocus sp. 1" goes to review under it: GBIF's answer lists
  "Epipsocus Badonnel, 1955" beside the accepted "Epipsocus Hagen, 1866".
- An *exact synonym* (row 2, `GBIF.md` 127, as the coordinator ruled at 22:46Z
  from G28 and G1) clears when its accepted usage passes row 1's test: the
  accepted usage GBIF returns, at the label's rank, in class Insecta, and no
  homonym conflict for the label's name (S4's reading of whose conflict
  counts). GBIF v2 gives the accepted usage no status, since it is the accepted
  name by definition, so a missing status counts as accepted and any other
  status sends the match to review (the coordinator's ruling of 23:58Z,
  coordinator.md:492). A pro parte synonym has several accepted usages, which
  `GBIF.md` 129 sends to review, so it never clears. The final value is the
  accepted name, the verbatim stays the label's spelling, and the synonym's
  status and the accepted usage are recorded. Otherwise it is `ambiguous`.
- `ambiguous`: a fuzzy or variant match (row 3), a higher-rank match (row 5), a
  homonym conflict, a usage that is not accepted, another canonical name or
  rank, a usage outside Insecta, an exact synonym that does not clear, and a
  name read only in part.
  `no_match`: GBIF matched nothing. A match type GBIF documents, VARIANT
  included, is never `malformed_response`.
- A body whose parts do not have the types GBIF documents is
  `malformed_response`, never an exception: a usage, an alternative or its
  diagnostics that is not an object; a usage without a name, or whose name is
  only whitespace; a name, canonical name or authorship over 500 characters,
  or with a control, format, surrogate, private-use, unassigned, line-separator
  or paragraph-separator character or a variation selector; a rank or status
  outside the values GBIF and ChecklistBank document; a key that is neither 1
  to 32 letters and digits nor an integer from 0 below 10^12; an alternative's
  match type outside GBIF's; a classification element that is not an object
  with such a name and rank; an object that gives a key twice; nesting deeper
  than 32 levels; or any string, key or value, that cannot be encoded, such as
  a lone surrogate. Each holds in the match body and in the index metadata the
  lookup stores, so every record the lookup keeps can be written (the
  steward's reviews of rounds 3 and 4).

Every GBIF candidate is a usage's documented fields alone (key, name,
canonical name, authorship, rank and status), with `scientificName` always
GBIF's own `name`, never a body's field or a usage nested inside one, so the
reviewer's existing `taxonomy_resolution` decision can select it and stores
GBIF's name. GBIF's usage,
accepted usage, classification and alternatives are kept as `GBIF.md` 134-160's
evidence contract lists them, the coordinator's reading of what may be stored;
G28 itself stores the label's spelling and GBIF's settled name. A lookup keeps
GBIF's usage, its accepted usage and at most its first 20 alternatives as
candidates, so the review step's proposals stay within their bound of 100; the
diagnostics keep every alternative (the steward's review of round 5).

Global Names Verifier (Catalogue of Life and GBIF Backbone sources) and the
Catalogue of Life match API are asked as well, each its own source call with its
licence (CC BY 4.0 for each source), and each is sent the canonical name only.
The Catalogue of Life is pinned to its release COL26.9 (dataset 316321, issued
2026-09-11), not the moving `3LR` alias (PRD 543). They never change the
outcome. When GBIF answered and one of them answers differently (success
against anything else) the result carries the warning
`taxonomy_source_disagreement:{source}`; when one is unavailable after its
retries, or answers a truncated or malformed body (which is not retried),
`taxonomy_support_unavailable:{source}`. An answer of a type its API does not
document is malformed, with the sanitized error `malformed_response`: GNV's
`matchType` outside its list, or a `bestResult` that is not an object or whose
`taxonomicStatus` is not a string; COL's `match` not a boolean, a `type` that
is not a string, or a `usage` that is not an object or whose `status` or
`name` is not a string. A body in an encoding the fetch cannot read is
malformed, with the sanitized error `unsupported_encoding`. Neither is
retried, and neither is a disagreement. BugGuide is not called.

**One deadline.** The tool has 60 seconds in all, half the default external
step timeout (S4's choice), and GBIF comes first: GBIF's attempts, and each
request's own timeout, fit inside it, and the supporting sources get only the
time left. A supporting source with less than 5 seconds left is not asked: its
source call records `timeout` with `tool_deadline`, and the result warns
`taxonomy_support_unavailable:{source}`.

## 7. The geography tool on Google (stage 7, part 2)

G10, G12, G26, G29. `geography_lookup` (`application/geography_tool.py`) is the
first version of the geography tool behind the interface of section 6; an
accepted S8 plan replaces this module, not the interface.

2026-10-03 (owner G-geo-1 to G-geo-3, quoted in PLAN 2.1): this section is
retired, and Google Maps leaves the harness permanently. The research harness's
geography specialist runs the historian prompt `specimen_geography-v2.txt`: it
interprets the label's verbatim locality with historical knowledge and asks the
GEOLocate validator (source `geolocate` in `research_harness/sources.py`) to
check each geography value it proposes. The validator sends one request per
lookup to GEOLocate's `glcwrap.aspx` (`fmt=json`, over HTTPS), with at least
3 s between GEOLocate request starts in one process, and captures the full
response as evidence (coordinator engineering calls of 2026-10-03). The matched point's coordinates are candidate metadata in
the tool result and the trace, not record fields (G39), and the research
thread card does not show them yet; no uncertainty radius is taken from
GEOLocate (D13). A GEOLocate candidate's `authority_id` is `geolocate:` and 16 hex digits of a digest of the match's name, admin unit and point (`sources.geolocate_authority_id`), so the id that `field_candidate.authorityId` and the record's fields carry holds no coordinates; the point stays in the tool result, in the candidate's evidence excerpt (which the public workspace's evidence list shows) and in the trace (coordinator ruling, 2026-10-03, applying G39). Whether the public evidence excerpt list may show the point is an open owner question. 2026-10-03 (coordinator engineering call, ruling 7, citing owner G6): a GEOLocate no_match or ambiguous outcome for a geography field is a scientific result, not an operational block; it reaches Needs human review with that field's GEOLocate receipts (`contracts.HumanQuestion`), the one exception to "human questions need exhausted sources". Every outage stays an operational block. `application/geography_tool.py` stays in the repository with
no production caller (only tests import it); the text below records it as
built.

**One call per reading** carries every locality literal of that reading. The
address is the reading's unassigned locality text when there is any, otherwise
its assigned literals from the most to the least precise field. The key comes
from `SPECIMEN_GOOGLE_MAPS_API_KEY`; a missing or rejected key is
`authentication_error`, an operational block (QUE-005). Retries follow section
6; an HTTP 401 or 403 is final at once. Every call's source is exactly
`google-maps-geocoding`, the string the data contract pins for Google (#88, rule
1.6). This address predates PLAN 4.8's single place filter, which #183 applies
to every request this tool builds; no profile names the harness route before
#183 merges (MERGE_ORDER 5e, confirmed by the coordinator on 2026-09-25).

**The mapping from Google's response to our outcomes is one function**,
`map_geocoding_response`, so that an owner decision changes only it. S8's D1 and
D14, pending when this was written, are decided since (G35 and G27;
GEOREFERENCING.md 555). One result without `partial_match` is `success`; a
partial match or several results is `ambiguous`; `ZERO_RESULTS` is `no_match`.
Per field, a success needs every literal of the field to equal, after folding
(case, accents, punctuation and label notations such as "Prov."), the name of an
address component at one of the field's levels, or a name the profile's aliases
give for it ("P.I." as the Philippines); otherwise that field is `no_match`. The
folding and the aliases are G29 applied to places: PLAN's G29 row makes it the
harness's principle to work through every reading a notation allows, "for dates
and for every other field", from the harness knowledge each subcollection's
profile carries.

**A near spelling** (G34, the owner's answer to S8's D15, 2026-09-24) can clear
a field no name matches, with the place ID and no name. It needs a single result
without `partial_match`, as any success does, and all three of G34's conditions:
(1) a component at the field's levels has a long name within one edit of the
folded literal, never a short name or code: "P.I." is not one letter off "PH",
and only the profile's alias confirms it; (2) it is the only such component; (3)
every other admin field of the reading, and at least one, matched by name or
alias. FMNH 105526330's "Chimaltenago" clears its department this way, because
Google's department is "Chimaltenango" and "GUAT." names its country. A live
check on 2026-09-24 found that Google answers that address with one result and
no partial match. The tool then warns `near_spelling:{field}`; the harness
records it as a warning finding, which never routes the record. The label's
spelling stays the verbatim (G27). Denali still clears nothing: no component
there is one edit from "Davao" or "P.I.".

**`precise_location` is verbatim locality text** (PRD 515). Its literal helps
form the address, but the tool reports no outcome and no place for it, so
nothing it returns can settle or replace it: the coordinator's ruling (b) at
00:08:24Z on 2026-09-24 took it out of the field outcomes, so that no stored
result can read as locality resolution. Where such a phrase actually is was
left to the owner's ruling on S8's D3 (the coordinator, 00:07Z on 2026-09-24).
G36 decided D3 for the places and itinerary entries S8 drafts, the places only
the museum's own records know: a curator confirms each one, and an unconfirmed
one never settles a field. A result for the wrong place settles no field either,
because each admin-level field is checked against its own literal, as ruling
(b) asked: Google puts "E. slope Mt. McKinley" at Denali, Alaska, where no
component is named "Davao" or "P.I.".

**What is kept** (G26, Google's terms): per request only the place ID, our
outcome and the sha256 of the full response. Google's names, address components
and coordinates are read in memory to compute the outcomes and are never
returned to the agent, stored, traced or logged. The key travels as a URL
parameter, the only form the Geocoding API accepts (a header key is refused,
checked 2026-09-23); a filter redacts it from the `httpx` log, and the lane must
not record raw request URLs in traces. An exception's text can quote the
request URL, and the key with it, so no exception leaves the request: a timeout
is `timeout`, any other `httpx` transport error is `provider_error`
(`geocoding_transport_error`), and every other failure, including the `httpx`
errors outside its `HTTPError` family such as `InvalidURL`, is `provider_error`
with the fixed code `geocoding_unexpected_error`.

## 8. The date and catalog-number validators (stage 7, part 3)

HAR-006; owner decisions G24 and G29, and the date rules the coordinator
approved at 21:49Z on 2026-09-23, which G24 revised for two-digit years at
22:07Z. Both tools are deterministic (`application/field_validators.py`), call
no provider and never change the literal; each answers only for a literal that
occurs in the reading it was copied from (otherwise `policy_blocked`,
`literal_not_in_source`).

**`date_parser`** returns every reading a date's notation allows, and the
harness settles which one the evidence supports (G29):

- Notations, a list S4 keeps and not a closed one (the owner's G29 answer: the
  harness works out "all possible cases"): a Roman-numeral month (I to XII,
  only when the profile's `date_rules.roman_numeral_months` is on; lowercase
  only between a day and a year joined by `.` or `-`, so `12 x 46` stays a
  possible measurement) with day and year, with day only, or with a year of
  four digits or of two after an apostrophe (`XI.'46`, pilot 327's date, is
  November 1946 under the century rule: G24 reads '46 as 1946, and G29 a Roman
  numeral in the month position as the month); day, Roman month, year
  (`12.VI.1946`); day, month name, year (`3 sept. '46`, `6-Sept-1946`); month
  name, day, year (`Sept. 3, 1946`); month name and year; a year alone; and a
  numeric date, which gives both the month-day and the day-month reading unless
  a component over 12 fixes the order.
  Added 2026-10-09 (tool version `date-parser-v2`; the rules are in
  FIELD_RESEARCH.md, "How dates are read"): month words of English, Spanish,
  French, German, Portuguese, Italian and Latin (`application/date_months.py`),
  ordinals (`3rd`, `1er`), a year written first (`1946.IX.14`, `1946-04-05`), a
  day and month with no year (`14.IX`), and ranges (`3-5.IX.1946`,
  `VIII-IX.46`, `3.IX-5.X.1946`), whose reading has the start in `iso` and the
  end in `end`. A reading's `order` names the notation rule that matched.
- A two-digit year becomes 19xx only under the profile's
  `date_rules.two_digit_year_century` (G24; `century_rule` records it); without
  the rule the year is missing. A bare number after a month is its day, or under
  the century rule also its year (`IV-25`: April 25, or April 1925). A year
  literal leaves both readings, which the six-specialist harness's pinned
  explicit-event rules (`research_harness/temporal_context.py`) still read, unless
  the caller passes `year_literal_decides` (field research does): `IV-25` beside
  `1948` is then April 25, 1948 only.
- Readings outside the calendar or outside 1750 to the current year are
  dropped (`invalid_calendar_date`, `implausible_year`); identical readings are
  one.
- A letter that matches a Roman numeral only under Unicode case rules, such as
  `İ` (U+0130), is no numeral, and the literal is no date (`no_match`).
- A slide-preparation code (`IV-29-68-4`, `10-6-78-1a`, four or more
  hyphen-joined parts whose first three are date-shaped), or a date-shaped part
  of one, is never a date (`slide_code`); any other part of a hyphen-joined
  token is not read either (`part_of_hyphenated_token`).
- Outcome: `success` for exactly one reading with a year, at the precision
  written (day, month or year; month and year is enough, G24); `ambiguous` for
  several readings (`several_readings`) or one without a year (`year_missing`,
  `century_unresolved`); `no_match` otherwise. A numeric date that leaves day
  against month open also says so (`day_month_order_ambiguous`, after
  `several_readings`). Each reading records the profile rules it used.

**`catalog_number_validator`**: an optional `FMNH INS` prefix (any spacing,
`-` or `#`, including a line break) and five to nine digits, nothing else; the
digits are the catalog number. Anything else is `no_match`.

## 9. Field resolution from recorded outcomes (stage 7, part 4)

G19, G20, G23, G24, G27, G28, G29, G32, G33; the data contract's section 4.3
(#88), with the multi-label shape agreed with S5.
`application/field_resolution.py` decides every field from the recorded
outcomes of its tool calls. The harness agent (the next part) proposes each
field's literal as each reading has it and makes the calls; it never decides a
field, and nothing here invents a value (HAR-019).

**What it reads.** Per region, the decided transcript (the reading the first
pass selected) and the raw readings: every reading when the first pass
selected none (G19), otherwise the unselected ones, for the fallback (G20). Per
field, each reading's literal, which must occur in that reading's text exactly;
any other literal is refused before anything is called, the raw readings' in
the fallback too. A field no reading has stays unknown, and nothing is called
for it.

**With a decided transcript,** its literal is the field's verbatim (G27).

- The field is looked up on that literal, and a `success` settles it.
- Otherwise each raw reading whose literal differs is looked up, one call per
  distinct literal. When the successes agree on one value, that value settles
  the field (G20): the verbatim stays the decided literal, and the confirmed
  reading appears only as the settled value's provenance, through its call, that
  call's evidence and the name the call settled (#88, 4.3).
- Raw successes that disagree leave the field `ambiguous` with
  `readings_conflict`. With no success, the field keeps the decided literal
  with the first lookup's state (`ambiguous`, or `unresolved` for any other
  outcome) and the reason `lookup_{outcome}`, and goes to review.

**Without one (G19),** literals identical in every reading are one lookup and
keep that literal, and every reading's literal is grounded as its own evidence,
so the provenance names each reader that agreed (#124, the single-label
agreement ruling). Differing literals are looked up once each. When the
successes agree on one value, the field clears with no single verbatim:
`verbatim_by_observation` keeps each reader's literal as captured, and
`settled_observation_ids` names the first confirmed reader (G27, G28).
Otherwise the field is `ambiguous` with `readings_conflict`, keeps every
literal and names no reader. Whenever `verbatim_by_observation` is set,
`literal`, `input_source` and the source ids stay empty, and
`input_source_by_observation` gives each reading's own input source.

**A field on several labels** (G32) is settled on each label separately, by
the rules above. It clears only when every label settled the same value: the
same place ID or GBIF usage, or for a field no tool checks the same text. It
then keeps each label's reading in `verbatim_by_observation`, even when the
texts are identical, and lists each label's settled reading in
`settled_observation_ids`: for a label its raw-reading fallback settled (G20),
the confirmed raw reading, while its decided verbatim stays in
`verbatim_by_observation`. Its `normalized` is the one text every label has
for a field no tool checks, and otherwise the first label's settled name.
Differing spellings of the one value record `spelling_disagreement`. Otherwise it is `ambiguous` with `labels_conflict` and
goes to review with each label's reading and only their literal evidence. A
label without the field does not count.

**Only `success` settles.** An operational outcome after retries (rate limit,
timeout, authentication, authorization, provider, malformed response, policy)
blocks the run as `harness_{tool}_{outcome}` (QUE-005). The field stays
`unresolved`, and no fallback call follows.

**The settled value** is `authority_id` (Google's place ID or GBIF's usage key),
`parsed` (a validator's verdict), `normalized`, and a date's `precision` and
`century_rule`. `normalized` is only the name the tool settled: GBIF's name for
a taxon; for a place, the reader's literal the lookup matched exactly, never a
Google name (G26, rule 1.6). Validators leave it empty. Two successes agree
when their `authority_id` and `parsed` are equal.

**Evidence and findings.**

- Every literal a field cites is recorded as `literal` evidence of its reading
  (source `field_harness`). Its record (the region, the reading and the
  excerpt) is stored, and the evidence carries its reference and SHA-256, so it
  projects like any other evidence (#88).
- `evidence_relations` has one entry per evidence id. Literals `support`; a
  success's evidence has the relation the tool reports: GBIF `decides`, Global
  Names Verifier and Catalogue of Life `support` or `contradict` (G23), and
  Google `supports` (rule 1.6). Only a success's evidence is linked.
- A tool's warnings (`taxonomy_source_disagreement:{source}`,
  `taxonomy_support_unavailable:{source}`) and `spelling_disagreement` go to
  `Run.findings` as warnings with their evidence, never to `Run.reasons`.
  `spelling_disagreement` is recorded when a value settles through the
  fallback (G20), or without a decided transcript when the readers' literals
  differ (S8's plan, #94 section 3.3); a decided literal that settles itself
  records none.

**Fields no tool checks** keep the decided literal, or the literal identical in
every reading, as transcribed (`supported`). Differing literals without a
decided transcript are `ambiguous` with `readings_conflict`. `precise_location`
is one of them: it stays verbatim locality text, never replaced or settled by a
geocoder result (PRD 515). Where such a phrase actually is was left to the
owner's ruling on S8's D3. G36 decided D3 for the places and itinerary entries
S8 drafts, the places only the museum's own records know: a curator confirms
each one, and an unconfirmed one never settles a field.

**A numeric date's order** (G29, G33) comes only from the dates in every
model's reading of the specimen, not only the decided transcript. A date with
exactly one reading and a day different from its month, such as 13-5-48, fixes
its order; 5-5-48 fixes none. When the specimen's dates fix exactly one order,
the reading of `4-5-48` in that order is the date. When they fix none, or
disagree, the date stays `ambiguous` with its readings as the candidates: a
misread can block a choice but never make one. A date that settles keeps the
precision its literal writes and the century rule it used (G24).

**Domain.** `FieldValue` gains `input_source`, `source_region_id`,
`source_observation_id`, `verbatim_by_observation`,
`input_source_by_observation`, `settled_observation_ids`, `evidence_relations`,
`precision` and `century_rule`; `Run` gains `findings: list[RunFinding]`, each
with `rule_id`, `rule_version`, `severity`, `field_key`, `reason_code` and
`evidence_ids`. All default to empty, so stored runs load unchanged.

## 10. The tool ledger: every harness request, recorded once (stage 7, part 5)

HAR-007, HAR-010; G23, G26; the data contract's sections 3.1, 4.3 and 4.4
(#88), with the call key agreed with S5. `application/harness_ledger.py` is the
only way the harness reaches a tool. It runs each distinct request once,
records it as the contract reads it, and turns its result into what one field
sees for section 9.

**Only the profile's four tools run.** They are `taxonomy_verifier`,
`geography_lookup`, `date_parser` and `catalog_number_validator`; any other
tool id is refused before anything is called (HAR-007). The implementations are
injected, so tests use fakes. A request is one tool, one reading and its
arguments; the same request again returns the recorded result and records
nothing new.

**A taxonomy request carries its reading's place text.** The caller gives the
reading's place text, and the ledger hands it to the taxonomy tool, which
sends none of it (PLAN 4.8, as the coordinator ruled at 02:07Z and 03:24Z on
2026-09-26). Keeping it in the request is S4's choice: the record's arguments
hold it, so a request with other place text is made anew, never answered from
the record of one made without it, and has its own call key. A bare text is
refused rather than split into letters. The final calls give each reading's
place-field literals; the agent's own check gives none yet.

**Records.** Each source-call attempt is one `ToolCallRecord` in
`Run.tool_calls`. A validator's call is one attempt with no source.

- Phase `lookup` for taxonomy and geography, `validate` for the validators
  (HAR-003).
- Call key `{phase}:{tool}:{source or "-"}:{input_source}:{region_id or
  "-"}:{observation_id or "-"}:{first 16 hex of the SHA-256 of the arguments'
  canonical JSON}:{attempt}`, so GBIF, Global Names Verifier and Catalogue of
  Life calls of one request never collide.
- No call key repeats. A ledger can start from the run's earlier records, as
  a same-run retry needs: they stay, and a repeated request numbers its
  attempts on from them. A tool answer whose attempts would repeat a key is
  refused whole.
- A call on the decided transcript names no reading; its region identifies the
  decision. A call on a raw reading names its observation.
- `field_keys` are the fields the request serves: one geography request serves
  every locality field of its reading.
- `result` is bounded: the sanitized error and Retry-After for a source call;
  GBIF's candidates (G28 allows its names); for Google, place IDs only (G26); a
  validator's verdict and warnings. Candidates and place IDs go only on the
  source's final attempt, the one that answered them.

**Evidence.** Each source's final call is one `Evidence` item, linked from its
record, and earlier attempts link none. A Google call that got no response (a
timeout, for example) has none; its record keeps the outcome (the data
contract's rule 1.6). A Google item's digest is the SHA-256 of Google's full
response, and its stored record keeps only the place ID, the outcome and
that SHA-256 (DATA_CONTRACT.md:79-81), so `verify_evidence` checks it through
the record: exactly those keys, naming the item's digest.

- Kind `lookup` for a source call and `validation` for a validator.
- A lookup's `locator` is set exactly when it succeeded: `place/{place id}`
  for Google, `usage/{key}` for GBIF, `name/{name}` for the supporting sources.
  Otherwise it is empty. A validator's evidence keeps its region, and stores
  its verdict as a record (the tool, the literal, the outcome, the parsed
  value and the warnings) with its reference and SHA-256, as literal evidence
  does, so that every evidence item has its stored record (agreed with S5 for
  #168).
- No Google name, component or coordinate reaches evidence, a record or a
  result: only the place ID, our outcome and the stored fingerprint (G26).
- GBIF's lookup is also kept for the queue decision's taxonomy gate.

**What a field sees** (`Called`, section 9). A field's outcome is its own
outcome in the result when the tool reports one, otherwise the call's.
Only a success names a value:

- Taxonomy: GBIF's usage key and name, with GBIF's evidence `decides`. Global
  Names Verifier's and Catalogue of Life's evidence `supports` unless that source
  disagreed with GBIF (G23), and a disagreement or an unavailable source is a
  warning finding with that source's evidence. A name read only in part
  (`taxonomy_name_partly_read`) names no source, so its warning cites the
  taxonomy tool's own record.
- Geography: the place ID, and as `normalized` the literal the lookup matched by
  name, with Google's evidence only `supporting` (rule 1.6). A near spelling
  (G34) gives the place ID alone, and its `near_spelling:{field}` warning
  becomes a finding with Google's evidence. The ledger refuses to settle a field
  the geography tool reports nothing for, `precise_location`.
- Dates: the single reading's date, precision and century rule (G24).
- Catalog number: its digits.

An operational outcome passes through unchanged, for section 9 to block on.
`Evidence.locator` becomes optional for the failed lookups.

## 11. The harness agent (stage 7, part 6)

G6, G7, G19, G20, G26, G30, G32, G33 and G40; HAR-007 and HAR-019. The owner's rule: "agentic harness takes the finally decided raw
transcript runs lookups (can rely on raw for a final check if LLM decided
transcript output fails, if both fail send to relevant queue)". G40 names the
job: "the harness is looking at everything transcribed for context, the system
prompt should factor in all possibilities and the agents search and try to
figure out what it could be". `application/field_harness.py` runs a Pydantic
AI agent on the profile's harness route (section 5). The agent proposes
literals and checks them with the tools. Field resolution (section 9) decides
every field from the ledger's records (section 10).

**What the agent reads** (G40): everything transcribed on the specimen, as
context for every field. That is each label's decided transcript and its raw
readings with the first pass's note on each (section 4), named by label and
reading (`1A`, `1B`, `2A`), never by model or route. It also reads the
profile's mandatory and optional fields, each with the tool it may use.

**Instructions** are given to the agent: the pinned managed prompt followed by
the harness knowledge the profile names (section 12).

**What it returns.** For every field, the literal exactly as each reading has
it, and for a date the year literal the same label states elsewhere. Code
validates the answer and returns one fault per problem for a retry: a field the
profile does not have, a reading it was not given, a literal that is not
character for character in its reading, or two literals for one field in one
reading.

**Tools.** Only the profile's tools, each run through the ledger:
- `verify_taxon`: GBIF's usage, name, rank and status (G28);
- `geocode`: a reading's locality literals together, returning the outcome and
  each field's outcome, never a Google name (G26);
- `parse_date`: every reading a date's notation allows;
- `check_catalog_number`.

Geography arguments are in field order, so the agent's check and the final
call on the same literals are one request. The agent's tool calls run one at a
time, even several in one response, so a repeated call is answered from the
ledger's record and the caps count exactly.

**Deciding.** After the agent answers, every field is resolved by section 9 from
the ledger's records, and any tool call the agent did not make on its final
literals is made then, once.
- A field with no tool is transcribed as written, and so is
  `precise_location`, which no geocoder settles (PRD 515).
- Every date literal of every reading is parsed first, so the order the dates
  fix can settle an ambiguous numeric date (G33). The date then cites one
  `date_order` evidence item naming the dates that fixed it.
- Each literal's evidence stores its record through the run's blob store.

**Budget (G30).** The `parse` step reserves the harness's worst case before it
starts, and S3 sizes that reservation from these caps together, so they change
together:
- 8 requests per run, each at most 2,048 output tokens;
- 60,000 input tokens per run, checked after each response;
- a prompt of at most 12,000 bytes, instructions, readings and tool definitions
  together;
- at most 12 tool calls by the agent;
- at most 4 geocoding requests per run, the agent's and the final ones
  together, each with at most 3 attempts.

A tool call past its cap returns a refusal and makes no lookup. A final
geocoding request past the cap is refused as `policy_blocked`, which blocks the
run. T1's probe used 3 requests and 1,285 output tokens. The input limit is
checked after each response, so a reservation sized to 60,000 input tokens does
not cover the request that crosses it; S3's profile pull request, which merges
after #183, adds #153's pre-send budget check to the harness call, so a request
the reservation can no longer cover is refused as `harness_usage_limit` (agreed
with S3 on 2026-09-25).

**Failures** (G6, QUE-005):
- A harness failure decides no field and sends the record to review:
  - a prompt over its cap, before any call (`harness_input_too_large`);
  - a run that reaches a usage cap (`harness_usage_limit`);
  - an answer still invalid after its retries (`harness_malformed_output`);
  - a tool that raises, or answers nothing, during the agent's run
    (`harness_tool_failed`);
  - a resolution that raises on its inputs (`harness_resolution_failed`).
- Nothing half-made is kept. The ledger appends a request's records and
  evidence only once all of them are built, and refuses arguments it could
  not store (deeper than 32 levels, or text that is not valid Unicode). A
  failed resolution keeps no field, literal evidence, finding or blocker,
  only the ledger's records of the calls it made.
- A provider error stays an operational block, as for every model call.
- An operational tool outcome blocks the run (section 9).

## 12. The harness's instructions: the managed prompt and the knowledge (stage 7, part 7)

G29, G36, G37 and G40; PLAN's G29 row makes each subcollection's harness
knowledge part of its profile. The harness agent's instructions (section 11)
are the pinned managed prompt `field-harness` followed by the harness knowledge
the profile names by id and version (`harness_knowledge.instructions_for`). A
knowledge id or version the code does not have is refused.

**The prompt** is a managed prompt like the other three: a Logfire template
variable with its default in code, pinned on the run. It states:
- G40: everything transcribed on the specimen is context for every field;
  keep looking things up and weighing the evidence until a field settles or is
  shown not to;
- G29: work through every reading a notation allows;
- G37: a field the label leaves out is filled only by derivation from settled
  fields, with authority and evidence;
- G36: no conclusion without evidence;
- the copy rule: never invent, complete, correct, expand or translate a literal.

**The Insects knowledge** (`harness_knowledge/insects.py`, id `insects`, version
`insects-harness-knowledge-v1`) is the pilot's. S3's profile names it. It lists
the label notations and every reading each allows, each with the fields it can
belong to:
- "P.I.", "Guat.", "Prov.", "Dept.", "Mt.", "Is.", "nr." and the directions
  that qualify a place;
- "leg." and "coll." marking collectors, and "det." marking who identified the
  specimen;
- a Roman or named month, both orders of a numeric date, and a two-digit year
  under the profile's century rule;
- "?" marking an uncertain value.

Reading a notation assigns what is written to the field it names. "m", "ft.",
"'", "alt." and "el." give the unit of the elevation written, and "ca." marks a
value as approximate. The knowledge never fills or converts a value; derived
values are section 13's.

Its place aliases, written as the geography tool folds them, are the only extra
names that tool accepts ("P.I." as the Philippines).

## 13. Layers and derived values (stage 7, part 8)

G37, G38 and G41 (the owner's answers of 2026-09-24; G41 revises G22 in full,
relayed by the coordinator), with the coordinator's readings recorded in #124,
the field names agreed with S5 and the derivation type agreed with S8.

**Every field value records its layer** (G38). The owner's order is image,
transcription, verbatim, the harness's settled answer, then derived, and a
later layer never erases an earlier one:
- `verbatim`: as written and not settled, whether transcribed as seen or a
  lookup that did not settle;
- `settled`: a lookup's success, or the one text every label has (G32);
- `derived`: a field the label leaves out, filled from others, with
  `derived_from` naming the fields it came from.

A reviewer's value is the review decision (S5), not a harness layer.

**A derivation** is a `Derivation` (`harness_tools.py`, section 6): the field, the
value and its unit, the method, the authority (a `SourceRef` whose version pins
the dataset), the settled input fields with their values, and its checks.
- S8's geographic tool emits the derivations that need outside data in the
  `geography_lookup` result (`ToolResult.derivations`): containment for county
  and city, the elevation model where the label states no elevation, and
  gazetteer names. The harness applies qualified derivations in a run's geography
  results. The Google tool carries none, so until S8's tool lands those fields go
  to review, which G37 allows.
- The harness emits G41's elevation rules (`application/derivations.py`). The
  owner chose "The label's own number fills both From and To, and the metre
  fields are converted from it exactly (1 ft = 0.3048 m)". In the coordinator's
  reading the conversion goes both ways, so:
  - a single stated elevation fills both ends of its unit
    (`stated_elevation`), while a stated range keeps its own ends;
  - the label's unit fills the other unit's fields by the exact factor, when
    the label states nothing in that unit (`unit_conversion`);
  - converted values are kept to hundredths, and copied values stay as stated;
  - a stated elevation must settle to exactly one number: its literal, or the
    agreed settled text when several labels retain separate verbatims (G32).
    A complete single quantity is required: unary `+`, `-` and Unicode `−`
    signs and leading decimals retain their magnitude and sign. A hyphen after
    a number separates range endpoints. Ambiguous signs, uncertainty markers
    and unmatched fragments supply no derivation. Nothing is derived while
    any stated elevation is unsettled;
  - a recognized unit suffix must match the field's unit before that quantity
    supplies a derivation. Metre words/`m` and foot words/`ft`/foot primes keep
    their stated unit. A contradictory suffix supplies no derived authority,
    and never remaps the stated field or overwrites its verbatim. A bare
    number, including a separately assigned range endpoint, uses its field's unit;
  - their authority is `apply_derivations` at the rules' version
    (`derivation-rules-v1`), so a G41 value names its stated field, its rule
    and `apply_derivations` (#124).

**Applying derivations** (`apply_derivations`), whoever emitted them:
- A field the label states is never replaced; its verbatim stays as written.
- An external derivation's authority needs a concrete, nonblank version before
  it can fill a field or conflict with a qualified derivation. Missing, empty
  or whitespace-only versions remain readable in the optional `SourceRef` DTO,
  but are not inferred from a tool version, a timestamp or another source.
- A derivation needs nonempty inputs, and applies only when each input field is
  settled to the value the derivation names: a derived value's own value, otherwise the field's
  authority id, else its parsed, normalized or literal value. So a derivation
  from a lookup that did not settle never applies. A value derived earlier in
  the same list counts as an input, so S8's feet follow its metres.
- External derivations need successful producing-call evidence from the result
  that returned them. Only final successful source attempts `support` a derived
  value; failed attempts and responses remain in the ledger and evidence history.
  When the authority's exact name is a recorded source ID, that source's final
  attempt must succeed and have evidence. No authority/source aliases are inferred.
  When it has no recorded source, the current field must succeed and the result
  must have successful producing-call evidence. A failed unrelated field or source
  does not erase a successful recorded producer. Only bare, internally generated
  G41 rules with authority `apply_derivations`, version `derivation-rules-v1` and
  method `stated_elevation` or `unit_conversion` need no outside tool call; an
  externally returned `Found` needs producing-call evidence even with those names.
- Two derivations of one field that disagree fill it with neither, and it waits
  for review.
- A filled value is `supported`, with layer `derived`, `parsed` the value,
  `authority_id` the authority's record id, and `derived_from` its inputs.
- Its evidence is one `derivation` item, which `decides`: its source is the
  authority's name, its locator `derivation:{method}`, and its stored record the
  derivation itself with the evidence ids of the tool call that returned it. The
  input fields' evidence `supports` it, and so does that call's evidence, which
  links its `ToolCallRecord`. A derived value thus names its settled inputs,
  the authority with its version, and the tool call or, for G41's rules,
  `apply_derivations` (#124, PLAN 4.8).
- A value counts as derived only with that record. The model can't assert
  one: the agent proposes only literals its readings contain, and a field the
  label leaves out is filled only by a derivation that applies.
