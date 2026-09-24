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
retry), each capped at 1,024 output tokens so that its worst case can be
reserved (G30; T1's first passes used at most 406), 16000 tokens, and the stage
cost reservation `first_pass`, one key for every region. Its circuit is the first-pass route's provider.

**A cap hit.** A first pass stopped by a G30 cap selects no reading: its token
total, or the pre-send check of section 15. G30 makes a cap hit the raw
fallback, and G19 then decides from the readings. The decision records every
difference as uncertain. Its call keeps the provider's usage up to the stop
(`completion_state` `usage_limit`) for the lane's cost record.

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
6; an HTTP 401 or 403 is final at once. Every call's source is exactly
`google-maps-geocoding`, the string the data contract pins for Google (#88,
rule 1.6).

**The mapping from Google's response to our outcomes is one function**,
`map_geocoding_response`, so that a pending owner decision changes only it. One
result without `partial_match` is `success`; a partial match or several results
is `ambiguous`; `ZERO_RESULTS` is `no_match`. Per field, a success needs every
literal of the field to equal, after folding (case, accents, punctuation and
label notations such as "Prov."), the name of an address component at one of
the field's levels, or a name the profile's aliases give for it ("P.I." as the
Philippines); otherwise that field is `no_match`. The folding and the aliases
are G29 applied to places: PLAN's G29 row makes it the harness's principle to
work through every reading a notation allows, "for dates and for every other
field", from the harness knowledge each subcollection's profile carries.

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
nothing it returns can settle or replace it; where such a phrase actually is
waits for the owner's ruling on S8's D3 (coordinator, 2026-09-23). A result for
the wrong place settles no field either, because each admin-level field is
checked against its own literal: Google puts "E. slope Mt. McKinley" at Denali,
Alaska, where no component is named "Davao" or "P.I.".

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

HAR-006; owner decisions G24 and G29 and the date rules the coordinator
approved on 2026-09-23. Both tools are deterministic (`application/
field_validators.py`), call no provider and never change the literal; each
answers only for a literal that occurs in the reading it was copied from
(otherwise `policy_blocked`, `literal_not_in_source`).

**`date_parser`** returns every reading a date's notation allows, and the
harness settles which one the evidence supports (G29):

- Notations: a Roman-numeral month (I to XII, only when the profile's
  `date_rules.roman_numeral_months` is on; lowercase only between a day and a
  year joined by `.` or `-`, so `12 x 46` stays a possible measurement) with day
  and year, with day only, or with a four-digit year; day, Roman month, year
  (`12.VI.1946`); day, month name, year (`3 sept. '46`, `6-Sept-1946`); month
  name, day, year (`Sept. 3, 1946`); month name and year; a year alone; and a
  numeric date, which gives both the month-day and the day-month reading unless
  a component over 12 fixes the order.
- A two-digit year becomes 19xx only under the profile's
  `date_rules.two_digit_year_century` (G24; `century_rule` records it); without
  the rule the year is missing. A bare number after a month is its day, or under
  the century rule also its year (`IV-25`: April 25, or April 1925).
- Readings outside the calendar or outside 1750 to the current year are
  dropped (`invalid_calendar_date`, `implausible_year`); identical readings are
  one.
- A slide-preparation code (`IV-29-68-4`, `10-6-78-1a`, four or more
  hyphen-joined parts whose first three are date-shaped), or a date-shaped part
  of one, is never a date (`slide_code`); any other part of a hyphen-joined
  token is not read either (`part_of_hyphenated_token`).
- Outcome: `success` for exactly one reading with a year, at the precision
  written (day, month or year; month and year is enough, G24); `ambiguous` for
  several readings (`several_readings`) or one without a year (`year_missing`,
  `century_unresolved`); `no_match` otherwise. Each reading records the profile
  rules it used.

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
any other literal is refused. A field no reading has stays unknown, and
nothing is called for it.

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
  Names Verifier and Catalogue of Life `support` or `contradict`, and Google
  `supports` (G23). Only a success's evidence is linked.
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
geocoder result (PRD 515). Where such a phrase actually is waits for the
owner's ruling on S8's D3.

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

**Records.** Each source-call attempt is one `ToolCallRecord` in
`Run.tool_calls`. A validator's call is one attempt with no source.

- Phase `lookup` for taxonomy and geography, `validate` for the validators
  (HAR-003).
- Call key `{phase}:{tool}:{source or "-"}:{input_source}:{region_id or
  "-"}:{observation_id or "-"}:{first 16 hex of the SHA-256 of the arguments'
  canonical JSON}:{attempt}`, so GBIF, Global Names Verifier and Catalogue of
  Life calls of one request never collide.
- A call on the decided transcript names no reading; its region identifies the
  decision. A call on a raw reading names its observation.
- `field_keys` are the fields the request serves: one geography request serves
  every locality field of its reading.
- `result` is bounded: the sanitized error and Retry-After for a source call;
  GBIF's candidates (G28 allows its names); for Google, place IDs only (G26); a
  validator's verdict and warnings.

**Evidence.** Each source's final call is one `Evidence` item, linked from its
record, and earlier attempts link none.

- Kind `lookup` for a source call and `validation` for a validator.
- A lookup's `locator` is set exactly when it succeeded: `place/{place id}`
  for Google, `usage/{key}` for GBIF, `name/{name}` for the supporting sources.
  Otherwise it is empty. A validator's evidence keeps its region.
- No Google name, component or coordinate reaches evidence, a record or a
  result: only the place ID, our outcome and the stored fingerprint (G26).
- GBIF's lookup is also kept for the queue decision's taxonomy gate.

**What a field sees** (`Called`, section 9). A field's outcome is its own
outcome in the result when the tool reports one, otherwise the call's.
Only a success names a value:

- Taxonomy: GBIF's usage key and name, with GBIF's evidence `decides`. Global
  Names Verifier's and Catalogue of Life's evidence `supports` unless that source
  disagreed with GBIF (G23), and a disagreement or an unavailable source is a
  warning finding with that source's evidence.
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
call on the same literals are one request.

**Deciding.** After the agent answers, every field is resolved by section 9 from
the ledger's records, and any tool call the agent did not make on its final
literals is made then, once.
- A field with no tool is transcribed as written, and so is
  `precise_location`, which no geocoder settles (PRD 515).
- Every date literal of every reading is parsed first, so the order the dates
  fix can settle an ambiguous numeric date (G33). The date then cites one
  `date_order` evidence item naming the dates that fixed it.
- Each literal's evidence stores its record through the run's blob store.

**Budget (G30).** Each request reserves its worst case, and S3 sizes the `parse`
reservation from these caps together, so they change together:
- 8 requests per run, each at most 2,048 output tokens;
- 60,000 input tokens per run, checked after each response;
- a prompt of at most 12,000 bytes, instructions, readings and tool definitions
  together;
- at most 12 tool calls by the agent;
- at most 4 geocoding requests per run, the agent's and the final ones
  together, each with at most 3 attempts.

A tool call past its cap returns a refusal and makes no lookup. A final
geocoding request past the cap is refused as `policy_blocked`, which blocks the
run. T1's probe used 3 requests and 1,285 output tokens.

**Failures** (G6, QUE-005):
- A harness failure decides no field and sends the record to review:
  - a prompt over its cap, before any call (`harness_input_too_large`);
  - a run that reaches a usage cap (`harness_usage_limit`);
  - an answer still invalid after its retries (`harness_malformed_output`).

  Either way the run reports the provider's usage up to the stop, since the
  agent's usage is counted in place.
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
  gazetteer names. The harness applies whatever a run's geography results
  carry. The Google tool carries none, so until S8's tool lands those fields go
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
  - an elevation literal must state exactly one number, and nothing is derived
    while any elevation the label states is unsettled.

**Applying derivations** (`apply_derivations`), whoever emitted them:
- A field the label states is never replaced; its verbatim stays as written.
- A derivation applies only when each input field is settled to the value the
  derivation names: a derived value's own value, otherwise the field's
  authority id, else its parsed, normalized or literal value. So a derivation
  from a lookup that did not settle never applies. A value derived earlier in
  the same list counts as an input, so S8's feet follow its metres.
- Two derivations of one field that disagree fill it with neither, and it waits
  for review.
- A filled value is `supported`, with layer `derived`, `parsed` the value,
  `authority_id` the authority's record id, and `derived_from` its inputs.
- Its evidence is one `derivation` item, which `decides`: its source is the
  authority's name, its locator `derivation:{method}`, and its stored record the
  derivation itself with the evidence ids of the tool call that returned it. The
  input fields' evidence `supports` it, and so does that call's evidence, which
  links its `ToolCallRecord`. A derived value thus names its settled inputs,
  the authority with its version, and the tool call (#124, PLAN 4.8).

## 14. The harness in the `parse` step (stage 7, part 9)

The owner's pipeline runs the harness after the first pass. G40 is the harness's
job, G30 its budget, QUE-005 and G6 its failures, and PLAN 4.8 the outward text
rule. `application/harness_runtime.py` wires the harness (sections 9 to 13) into
the workflow's existing `parse` step.

**When it runs.** In `parse`, after the deterministic `key: value` parser, when
the adapter has a harness and the run's profile names a `harness_route`.
- The route is a new `domain.Profile.harness_route`, pinned in
  `run.dependencies` like `first_pass_route`. A route that is not registered
  stays unpinned, and the step blocks.
- Without a harness route, today's extraction runs, as before. S3's profile
  wiring carries both stage routes from the published profile at classify:
  `first-pass-glm` and `harness-deepseek`.
- The step stays external and billable, with the stage reservation `parse`
  (S3 sizes it from section 11's caps). Its circuit is the harness route's.

**What the isolated model child receives** (`harness_payload`):
- G40: every reading handed to the harness, from each region's handoffs
  (section 4) with the first pass's notes. A region decided before the first
  pass contributes its resolved transcript as its decided reading.
- The field plan: the mandatory fields, the profile's optional fields, and
  each field's tool from the profile's `field_tools`.
- The profile's `date_rules` and its `harness_knowledge`, by id and version.

Outward requests carry place text only: one reading's locality literals to
geography, a scientific name to taxonomy (PLAN 4.8).

**What the child does** (`harness_direct`):
- It requires approved inference, the pinned harness route, the pinned prompt
  `field-harness` and the named knowledge; otherwise it blocks with a fixed
  code.
- It runs the harness (section 11) with the production tools through the
  ledger. The geography tool gets the knowledge's place aliases, and the date
  tool the profile's date rules.
- It returns the fields, evidence, findings, tool calls, GBIF lookups, any
  block, any harness failure, and the reported token usage.

**What the parent keeps** (`merge_harness`):
- The fields replace `run.fields`, and must be exactly the plan's; anything
  else is `external_outcome_unknown`.
- The evidence, findings, tool calls and lookups are appended to the run, and
  the tokens are counted.
- The model call is kept as a `HarnessCall` in `Run.harness_calls`, one for
  each attempt of the step whose child returned. It holds:
  - the attempt, route, model and provider;
  - the requests, and the input and output tokens (None when the provider
    reported no usage);
  - the attempt's Google geocoding requests.

  S3's `record_step` prices the step from it: the model's tokens on its route,
  reserved when they're unknown, and the geocoding requests at the
  `google-maps-geocoding` price. A child that returned nothing leaves no call,
  so the step stays reserved.
- A harness failure is kept as `run.harness_failure`; the queue decision sends
  it to review (T4).
- A harness tool's operational outcome, such as GBIF rate-limited after its
  retries, is returned to the workflow. The workflow blocks the run with that
  code only after the model call has settled, so the harness route's circuit is
  not charged for a lookup source's failure. The tool calls already made stay on
  the run for their costs.

**The `lookup` step** makes no GBIF call of its own once the harness verified the
taxon: its GBIF lookup is already on the run for the queue decision.

## 15. Bounded retries (G30)

The coordinator's ruling of 2026-09-24 on G30: a call's later request goes only
if it cannot cross the call's reservation. It applies to every call through
`run_agent_bounded`: the readers, the first pass, the harness and the old
extraction agent. S3 writes it here, with S4's sign-off, because it changes the
shared agent setup.

- **Bounded feedback.** A later request carries pydantic-ai's validation
  feedback, which lists every error with the input it rejected. An answer with
  thousands of wrong-typed list items would carry thousands of errors.
  `PrivateProviderModel` sends every feedback within
  `RETRY_FEEDBACK_MAX_BYTES` (8,192), measured as the provider receives it:
  - a list of errors keeps the first `RETRY_FEEDBACK_MAX_ERRORS` (20), each
    `input` and `msg` shortened, and one more entry counting the rest;
  - a text feedback, such as a `ModelRetry` message, is cut to fit.

  The answer being corrected is already in the conversation, so a shortened
  echo of it loses nothing the model needs.
- **A budget.** `run_agent_bounded(..., budget=None)` takes a `CallBudget`: the
  call's reservation and its route's prices. Before each request after the
  first, the next request's input is bounded by the last answer's reported
  input and output tokens, the new parts in bytes (a token is never shorter
  than a byte) and 256 tokens of framing. If what was spent, plus that input
  and the request's output cap at the route's prices, could cross the
  reservation, the request is not sent. pydantic-ai's `UsageLimitExceeded` is
  raised before it, so each caller keeps its own mapping (section 11, the
  first pass's cap hit). A later request after an answer that reported no
  usage, or one that carries an image, cannot be bounded and is not sent
  either.
  - The first request is not checked here. The lane sizes the call's
    reservation for it from the crop (LANE.md T2d).
  - With no budget, nothing changes.
- **A reading stopped by its limits** fails as `model_usage_limit`, a known
  operational block with no automatic retry (G6), where it used to end as
  `external_outcome_unknown`. The limits are its token limits or its
  reservation. The provider answered, and what it billed is known.

## 16. The queue decision (stage 8)

G1 is the owner's rule: "When I say something that harness was able to resolve
is cleared it is cleared." G6 sends what the harness could not resolve to
needs human review with its reasons, QUE-004 defers a documented capability
limit, and QUE-005 keeps an operational failure a block.
`application/policy.py` decides each run once its steps are done. The lane's
profile names these rules `insects-clearance-v2`.

**The harness's runs (G1).** A run whose fields the harness decided, because
its profile names `harness_route` (section 14), no longer needs institutional
approval, confirmed semantics or a reviewer's approval to clear:
`institutional_policy_unapproved`, `mandatory_semantics_unconfirmed` and
`human_approval_required`. So G1 turns on with the harness, by the same profile
setting. Every other run keeps those gates: synthetic-mode demos, and
production runs before the switch. Everything else is as before. G15's
automatic coverage check still gates through `label_coverage_unconfirmed`, and
a failed check sends the record to review.

**Mandatory and optional.** Every field in the profile's `mandatory_fields`
must resolve. An optional field never blocks: the published Insects profile
makes `identified_by_irn` optional, which is G16's reading of G42.

**How a harness field is read.** A field whose `layer` is set came from the
harness, and it is read as the harness wrote it. A field from the older
extraction path is read as before.
- **Its value.** The verbatim, when one was chosen. When the first pass picked
  no reading, or the field is on several labels, none is chosen, and the value
  is the settled one: the authority id, the parsed value or the settled text
  (G27, G28, G32).
- **A derived value** counts only with its derivation record: its `derivation`
  evidence decides it, and the record is stored (G37, G41, #124). A value
  without one, such as a value the model asserted, doesn't count, so the field
  is unresolved.
- **Grounding.** Each reading the value rests on must be in its own literal
  evidence: the verbatim, or each reader's when none was chosen (G19, G27).
- **A settled value** rests on a success among the field's evidence:
  - an authority id on the lookup whose place ID or usage key it is;
  - a parsed value on the date parser's success, or on the specimen's date
    order (G33);
  - a settled name on its lookup's success, or on the one text every label
    read (G32).

**A label the first pass left open** (G19, G20) no longer blocks by itself
(`unresolved_transcription`). It passes when the harness drew fields from its
readings and every mandatory one resolved, on its own evidence or through a
lookup that settled the disagreement. A mandatory field still left with
conflicting readings sends the record to review.

**Elevations.** Each elevation's number is the one number its label's literal
states, or a derived value with its record (G41). Both ends and both units are
then checked as before.

**Dates.** The gate reads each date as parsed, at the precision written (G24):
a year or a month is the span of its days, and the order checks compare spans.
A Roman month is that month (G29). A date written as uncertain, with a "?",
keeps the date gate (`date_precision_requires_review`).

**The taxonomy gate** reads the GBIF lookup the taxon rests on, not simply
the run's last lookup.
- After the harness, it is the latest lookup of the literal whose call decides
  the field, or else of any of the taxon's readings. Never a lookup the agent
  made on another literal.
- Without the harness, it is the lookup step's, as before.

The operational check reads the same lookup, so a later lookup of the same
request recovers an earlier failure (QUE-005).

**A harness failure** sends the record to review with
`harness_failure:{code}` (G6, section 11).

**Findings never route a record.** G23's source flag and the readers' spelling
difference (G27) stay findings.

**The summary** (QUE-006, S5's data contract): `Run.disposition_summary` is
one sentence built from the rule version and the reason codes, without their
details:
- "Cleared under insects-clearance-v2.";
- "Needs human review under insects-clearance-v2: mandatory_unresolved,
  date_order.";
- "Deferred under insects-clearance-v2: unsupported_script."

A blocked run has no disposition and no summary. The evidence phase gate has
the last word on the disposition, so the summary is written again after it.

**Reason codes.** `harness_failure` is new. S3's `REASON_CODES` catalog (#136)
lists the codes in the rules' order.
