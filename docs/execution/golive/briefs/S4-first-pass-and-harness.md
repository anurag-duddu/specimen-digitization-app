# S4 brief: LLM first pass and agentic harness

Session title: **Build the LLM first pass and agentic harness**. Recommended
model Opus 5.5 at high effort.

## Mission

Build stages 6, 7 and 8 exactly as the owner specified: the LLM first pass on a
Hugging Face model, a fully functional agentic harness with graceful failures,
and the queue decision. Stage 5's scores also live in your steps: keep the
disagreement ratio in `adjudicate` (`workflow.py` 390-395) and the risk refresh
in `finalize` (534) when you change them. A strong harness comes later; a fully
functional one comes first (G6).

## Read first

1. `docs/execution/golive/PLAN.md`: sections 1, 2, 4.1 rows 5 to 8, and 6 (your
   row).
2. `~/specimen-golive/research/06-product-spec-and-approvals.md` sections 1 and
   4, and `01-backend-pipeline-stages.md` stages 5 to 8.
3. `docs/product-requirements/PRD.md` HAR-001 to HAR-019 (323-341), QUE-001 to
   QUE-005 (387-391), section 12.4 (487-567) and the failure table (676-688);
   `docs/execution/CONTRACTS.md` 210-270; `docs/GBIF.md`;
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
  the need a human queue." No data found for a mandatory field sends the record
  to the human queue with the reason; an optional field with no data is recorded
  as such and does not block clearance (G1: "mandatory fields if cleared then
  cleared"). An error is retried with backoff; when retries are exhausted it is
  an operational block with retry (QUE-005), shown as blocked, never a crash.
  Every outcome is typed (HAR-008) and recorded.
- Never invent values (HAR-019). Every literal comes from the decided transcript
  or a raw reading, with provenance.
- G19: when the first pass picks no reading for a label, the harness runs its
  lookups on each reader's raw reading; fields that resolve clear on their own
  evidence, and a field still left with conflicting readings goes to needs human
  review. G20: when the readers disagree and a lookup confirms exactly one
  reader's literal, that settles the disagreement, with its provenance, and the
  field can clear; it counts as a resolved critical disagreement for QUE-002.
  For places and taxon names that literal does not become the verbatim (G27,
  G28, below).
- G27 and G28: for places and taxon names the verbatim keeps the text as written
  and the final value is what the lookup settled; both are stored. When the
  first pass picked no reading and the readers' literals differ, each reader's
  reading is kept as captured, none is chosen, and the field clears on the
  settled value with a success outcome. S5's contract has the shape. For a
  place, the final value's name (`FieldValue.normalized`) is only a reader's
  literal the lookup matched exactly; otherwise the final value is the place ID
  and the outcome with no name (G26). Where no reader's literal matches even
  after folding or through an alias, the field clears only as G34 decides D15
  for the Google tool (below), and otherwise goes to review. For a taxon it is
  GBIF's settled name.
- G29: a Roman numeral I to XII in the month position is that month. The
  harness works through every reading a notation allows, for dates (month
  names, Roman numerals, both day and month orders, two-digit years under G24)
  and for every other field, and settles the one the evidence supports; what
  it cannot settle goes to needs human review with the candidates. You write
  the notations, and every reading each allows, as the Insects harness
  knowledge in a module you own, with an id and a version, and render it into
  the Insects harness's system prompt; S3's profile names it, so each
  subcollection gets its own, and carries G24's and G29's date rules for your
  date tool (PLAN section 4.2).
- G32: a field on two labels is settled per label on its own evidence and
  clears when every label settles to the same value: the same place ID or GBIF
  usage, or, for a field without a lookup, the same text. Otherwise it goes to
  review with each label's reading kept.
- G33: the numeric dates of every reading, the decided transcript's and the raw
  readings', are the evidence for an all-numeric date's day and month order;
  any disagreement among them fixes no order, and the date goes to review with
  its readings.
- G34 (D15 for the Google tool): a place field whose literal matches no
  component by fold or alias clears with the place ID and no name only when
  the long name of Google's component at the field's levels, never a short
  name or code, is within one edit of the folded literal, is the only such
  component, and every other admin field of
  the reading, at least one, matches by fold or alias; it carries a
  `near_spelling` warning finding that never routes the record. Otherwise it
  goes to review with the candidate. S8 builds the retrospective
  georeferencing tool behind your T3a interface (G34).
- G22, revised by G37 and G41: the four elevation fields stay mandatory. A
  single stated value fills From and To, and the other unit is converted
  exactly (G41; both ways, coordinator reading), each marked as derived with
  evidence; an elevation the label doesn't state is derived by S8's tool from
  the settled location (G37).
- G35 to G40 (PLAN section 2.1): the place tool's three tiers and open-source
  coordinates (G35, S8's build behind your interface); no conclusion without
  evidence, and curator-confirmed places (G36); fill in what the label leaves
  out, with authority and evidence, harness-wide (G37); every value records
  its layer, and `derive_rest` serves review's "fill the rest" (G38); the
  georeference stays in the tool result (G39); the agent reads everything
  transcribed and keeps looking things up (G40), stated in its system prompt.
  S8 builds the geographic derivations; you build those that need no outside
  data (coordinator ruling).
- G5: when the specification is silent or contradictory, ask the coordinator.

## Pull requests, in order

Each starts with its spec delta in `docs/execution/golive/HARNESS.md` and
failing tests (fakes for Hugging Face and HTTP; recorded real responses as
fixtures, a Google geocoding response first reduced to the place ID, the
outcome and the fingerprint, and no recorded request keeping its URL, which
carries the key, G26), then the implementation.

**T1. Hugging Face routes (G7).** The first pass sees the label crop, so it
needs a vision model; the harness needs reliable tool calling or structured
output. Choose provider-pinned models available through Hugging Face Inference
Providers, measure them on real crops (the acceptance lab has crops;
`specimen-huggingface-preflight` makes paid preflight calls; a local Hugging
Face token exists, never print it), and register them in `model_gateway.py` like
the existing routes. Report the choice and the measurements to the coordinator
before building on them. Approved 2026-09-23: `first-pass-glm`
(zai-org/GLM-5.3-Flash on deepinfra, text and image) and, provisionally until
the lab re-measures it with the real harness and G29's prompt,
`harness-deepseek` (deepseek-ai/DeepSeek-V4.1-Flash on deepinfra, text only).

**T2. The first pass (stage 6).** Persist the decision and the per-reader
records into S5's contract.

**T3. The harness (stage 7).** A Pydantic AI agent over typed tools from the
profile's registry: GBIF Species Match v2 (the existing adapter, `lookup.py`),
Global Names Verifier and Catalogue of Life for taxonomy (G23: GBIF species
match v2 against the pinned COL XR checklist decides, the other two are
recorded as supporting evidence, a disagreement is a warning finding, and
BugGuide is not called; a match succeeds as `GBIF.md` 126-130 defines, exact and
accepted at the expected rank, which for a genus-only label is the genus (G25);
synonym, fuzzy, variant and higher-rank matches are `ambiguous`, which changes
today's adapter: `lookup.py` 105-118 returns `success` for an exact synonym and
`malformed_response` for VARIANT); Google Maps geocoding
for geography (G10; the key comes from Secret Manager as
`specimen-google-maps-key`, and a missing or rejected key is
`authentication_error`, an operational block: `CONTRACTS.md` 244-246,
`PRD.md` 682; keep only the place ID, the outcome and the response digest,
everywhere including traces, fixtures and lab folders, and drop Google's names,
address parts and coordinates (G26); the tool hands the agent only those, and no
span, log line, exception text, stored error or tool-call result records the
request URL, which carries the key); the deterministic validators for catalog numbers and dates
(a Roman numeral I to XII in the month position is the month (G29); the date
tool returns every reading a literal's notation allows, both day and month
orders for an all-numeric date, and the harness settles the one the evidence
supports or sends the field to needs human review with the candidates (G29);
a date clears at the precision written, and a two-digit year reads as 19xx for
Insects, recorded as the profile's rule (G24); an uncertain date (a written
"?") is outside G24 and keeps the existing date gate; date-shaped
slide-preparation codes on the pilot slides are not collection dates, PLAN
section 3). No Parties tool: `identified_by_irn` is optional for the
slide pilot (G16), and the other fields outside taxonomy and geography are
transcribed as seen. Every outcome is one of HAR-008's, as `LookupStatus`
encodes them (`domain.py` 43-54); add none. Phases as the specification lists
them; the raw-reading fallback; retries with backoff; a worst-case reservation
before every model request (G30, PLAN section 4.3), which needs a cap on output
tokens per request and on the agent's model requests per run, set from the
lab's measured runs, a run reaching the cap being a harness failure under G6;
every tool call recorded for S5 and traced with Pydantic AI
instrumentation, content on and binary content off (G3; `include_binary_content`
defaults to on, and the first pass sends the crop; coordinate with S3's tracing
topic).

Geography is being researched separately (owner decision G12, session S8,
`briefs/S8-georeferencing-research.md`): historical toponyms, tiered
resolution and uncertainty. Build geography as one typed tool behind the same
interface as the others, with the Google Maps implementation of G10 as the
initial version, so that an accepted S8 plan replaces the tool without touching
the harness. Share the tool interface with S8 when it exists. The pilot's
localities are in the Philippines (1946) and Guatemala (1948); assume no
country.

**T4. The queue decision (stage 8).** The policy applies G1. For the lane,
remove the gates that contradict it: `policy.py` 31-34 (institutional approval
and semantics) and 138-139 (`human_approval_required`). Keep
`label_coverage_unconfirmed` (35-36): the lane's automatic coverage check (S3,
G15) satisfies it, and a failed check sends the record to needs human review.
`pilot_clearance_forbidden` (`worker.py` 318-323) is in the evidence-only
`PilotWorker`, off the lane's path; leave it. The reviewer's `capability_defer`
action in `api.py` 1940-1967 stays; the queue decision may also return deferred
under QUE-004. Validate the separately parsed date, not the verbatim text
(`policy.py` 119-126 parses the literal today): a date clears at the precision
written, a two-digit year reads as 19xx for Insects (G24), and a Roman numeral
in the month position is that month (G29). Keep the
elevation gate (99-106), which accepts elevation values filled with authority
and evidence (G37 and G41, revising G22). `unresolved_transcription` (46-48) yields to G19 and G20: a
region whose first pass picked no reading passes when every field drawn from it
resolved, on its own evidence or through a lookup that settled the
disagreement; a field still left with conflicting readings sends the record to
needs human review. When the first pass picked no reading, the non-empty check
reads the settled value with a success outcome, since no verbatim was chosen
(G27, G28), and the grounding check (75, `field.literal in excerpt`, which
raises on that None literal) tests each reader's reading against its own
evidence. The taxonomy
gate (140-157) and finalize's operational check (163) read only
`run.lookups[-1]`, which is arbitrary once G19 and G20 add a lookup per reader:
the taxonomy gate reads the lookup that settled the taxon field, and the
operational check catches an operational failure, not recovered by a retry, in
any lookup the decision depends on. G23's flag and the readers' spelling
difference under G27 are findings, never reasons for review. Tests cover every
path: the G19 and G20 paths with several lookups per run; all mandatory fields
resolved, cleared;
no data for a mandatory field, needs human review with the reason; no data for
an optional field, still cleared; a failed coverage check, needs human review;
capability limit, deferred; transient error, retried, then an operational block.

## Coordination

S3 supplies the profile, the tools per field, the optional fields (as
`Run.field_groups`, a new field whose shape S5 decides), the coverage check and the tracing mode. S5 supplies the
tables for the first-pass decisions, the tool calls and the fields; agree the
shapes in S5's first PR. `domain.py` has no single owner: add to it additively,
list your additions in the pull request body, and let S5 decide any shape that
S3 also needs. S2 supplies the secrets and
environment. S7 supplies real crops and recorded responses.

## Done

On a real specimen run locally, the first pass and the harness run with a typed
outcome for every lookup, fall back to the raw readings when needed, and the
queue decision follows G1, with every artifact persisted and traced.
