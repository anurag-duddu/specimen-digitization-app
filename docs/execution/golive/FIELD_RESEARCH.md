# Field research: one expert per field (takeover, 2026-10-08)

This note records why the six-specialist research harness could not finish a
specimen, what replaces its runtime path, and how the replacement meets the
owner's harness design of 2026-10-03. It is written for the owner first and
for engineers second.

## The owner's design (2026-10-03, the spec)

1. The harness never invents what the label does not say. Several image
   readers transcribe each label; one model (the organiser) reads every
   transcription and arranges the text into field-value pairs. The owner's
   correction in the schema session, 2026-10-08, refines this: deriving and
   inferring are the point, so the rule is "never a value without recorded
   support" (PRD.md section "Field model v2: four groups", its decision
   record and rules 1 to 3; in progress). This first version settles what the label states, what an
   approved source confirms (for example "P.I." settled as the Philippines
   from a cited place lookup) and the arithmetic derivations below. Supported
   inference beyond that is the next step: an engineering staging decision of
   the harness session, not an owner decision
   (`~/specimen-golive/status/harness-derivation-proposal.md`).
2. The harness receives those pairs together with every raw transcription,
   because a model can make mistakes and evidence is always needed.
3. It works field by field: one expert resolver per field, each with its own
   instructions, visible as its own agent in Logfire.
4. A field that is already an accurate read is simply finalized. A field with
   confusion is checked against the approved sources, and the expert keeps
   trying them until the field is settled or shown not to settle.
5. Unrelated work runs in parallel. Each record starts with fresh context.
6. What cannot be settled (the label lacks it, the sources cannot settle it,
   or several possibilities remain) goes to Needs human review. A settled
   field is cleared.
7. USD 1 per run is a hard ceiling, configurable per institution, and each
   run should cost as little as possible.
8. Failures are graceful: "no data found", "an error occurred, retry".

## What the code did on 2026-10-08 (main cb38a8be5)

| Spec point | Today | Gap |
|---|---|---|
| 1, 2 Pairs plus raw text | Met. The organiser call reads every reading of every label and stores quoted candidates; each specialist receives every reading. | None. |
| 3 One expert per field | Six topic specialists own the 20 fields (geography owns five, collection five, measurement four). | Real gap. |
| 4 Keep trying sources | Each specialist has a 240-second limit that its own record keeping uses up. Only geography is pushed to try more sources. | Real gap. |
| 5 Parallel | Two specialists at a time, in three windows one after another; tool calls one at a time. | Real gap. |
| 6 Unresolved to review | Several unresolved states block the record instead of sending it to review. | Real gap. |
| 7 USD 1 ceiling | Enforced per collection profile. Each request re-sends up to 500 KB. | Partly met. |
| 8 Graceful failures | Several failure reasons show no message in the app. | Real gap. |

## Why one specimen took so long and then failed

Every step of every specialist was saved by rewriting the whole run record,
which had grown to 873 KB against a 1.5 MB cap. Two specialists wrote that
same record at once, so their writes collided and were retried (93 rejected
writes in eight minutes of the live run). Counting the code paths, one
specimen made roughly 4,000 sequential database and storage round trips:
about 36 per model call, 9 per tool call, and about 140 to publish each field.
Offline, with an instant scripted model and an in-memory database, one
specimen still took 59 s of pure record keeping (59% publication, 25% the
whole-record store). The live traces (Logfire, 2026-10-08 22:08-22:20Z) add
the model side: the six specialists ran in three pairs one after another,
about 9 minutes before publication began; model calls, with the effect
record keeping wrapped around each, were 56% of specialist time, and one
taxonomy call took 99 s, because every request re-sent the whole research
input (taxonomy's first message alone was about 118 KB).

The live run on 2026-10-08 (specimen 105526321) failed four ways, all
confirmed from its recorded state, journal and worker log:

1. Taxonomy asked for a procedure by a prompt's version name; the tool refused
   it without a retry.
2. Geography spent 132.9 s on five calls of a tool that makes no outside
   request, almost all of it saving, and hit its 240 s limit.
3. Collectors and catalogue number: a helper built the complete answer with
   its lineage, the model dropped the lineage when retyping it, and the
   validator refused the answer.
4. Publishing `identified_by_irn` timed out twice reading the oversized record
   (30 s each), before anything was written.

## PR #282

Not merged. It fixes cause 1 at its root but works around causes 2 and 3
(one batched geography tool, longer prompts asking the model to copy text
exactly), does not speed up the read behind cause 4, removes a check on which
date reading is chosen, and makes one publication timeout stop the whole
queue. The record keeping that causes the failures stays.

## The replacement: field research

For a run whose profile names a harness route, the workflow hands over at the
`plan` step, as it does today. With `SPECIMEN_RESEARCH_HARNESS=fields` the
handover runs field research instead of the six specialists:

1. **Inputs.** Every reading of every label (named 1A, 1B, 2A as the organiser
   names them), the organiser's candidates and settled value for each field,
   and the profile's field list.
2. **Accurate reads finalize.** A field with no approved source or check whose
   organiser value is supported is finalized as written, with no model call.
3. **One expert per field.** Every other field gets its own Pydantic AI agent
   (`field_<key>`), its own instructions (shared rules plus the field's brief)
   and only its approved tools. All experts run at once.
4. **Sources.** GBIF (with Catalogue of Life and Global Names Verifier
   alongside), GEOLocate, Getty TGN, Wikidata and NGA, plus deterministic date,
   elevation and catalogue-number checks. One request per distinct query per
   record (shared cache), retries with backoff, GEOLocate spacing kept. Each
   source response is stored once as evidence.
5. **Checked answers.** An expert's literal must appear exactly in the
   readings it names; a value that differs from the literal must be a source
   candidate it was given, or a deterministic check's settled parse of that
   literal (an ambiguous check's readings are only options for a person).
   Readers that disagree, and places, follow `field_research/agreement.py`:
   - A field's readers disagree when the organiser left it ambiguous, or when
     its candidates across readers carry more than one literal. Literals are
     compared after NFC and whitespace collapse only, so "E. slope" and
     "E.slope" disagree.
   - A label with a decided transcript takes its text from that reading
     (G19): a resolved literal must be text the decided reading writes. The
     other reader's different text is kept as contradicting evidence and does
     not block.
   - Otherwise readers that disagree settle only when a success answer of the
     field's approved sources confirms exactly one reader's literal (G20):
     GBIF asked about exactly that name, or a place source returned a
     candidate of exactly that name. The answer must take that reader's
     literal and cite that answer, and each other reader's candidate text stays
     in the value's lineage, unsettled. A field whose only tools are deterministic
     checks, or that has no approved source (collectors, habitat, collection
     method, collection code, verbatim D/T/S), goes to review when its readers
     disagree.
   - A place field (country, province or state, county, city) settles only on
     a cited success answer of a place source whose candidate is the value,
     with that candidate's authority_id. Precise location stays the verbatim
     text and follows the decided-transcript rule.
   - A taxon is GBIF's decision for the whole name its literal writes: the
     cited success answer's query is the scientific-name parser's query for
     the literal (the genus, any subgenus, the species epithet and any
     infraspecific epithet with its marker, as written, with or without the
     author and year written), or the genus alone for a "sp." identification
     (G25). A query for part of the name ("Danaus plexippus" for "Danaus
     plexippus megalippe") or for another name on the line grounds nothing,
     and a label with no genus ("sp. 30") has no groundable query. The value
     and identifier are the candidate GBIF decided, never one of its
     alternatives.

   An answer that breaks a check is sent back for correction; an expert whose
   answer still fails the checks after its retries sends the field to review,
   never to a retry. The step applies the agreement rules again to every
   resolved answer before it becomes a value, on the source answers its field
   received, so an answer that breaks them is ambiguous (readers disagree) or
   unresolved, never settled. The clearance rules check the taxon the same way.
6. **Derived values** (G37, G41, G44) are filled deterministically afterwards
   from settled fields only: elevation copies and exact unit conversion, and
   the collection date's end from its start.
7. **One save.** Field values, evidence and reasons are written in one save
   at the end, through the existing record writer. Clearance uses the existing
   scientific rules without blanket human approval (G1). Anything unresolved
   sends the record to Needs human review with a plain reason; a source or
   model outage leaves the record blocked with retry.
8. **Budget.** Before every model call the step reserves that call's worst
   case (its input, the provider's chat template and the output cap) from
   what remains of the run's ceiling (the profile's `run_cost_limit_micros`,
   USD 1 for the pilot), and settles to the real usage after. A call that
   would cross the ceiling is not sent; that field goes to review. The step
   holds no more of the shared program allowance than it has left: when that
   is less than the run's headroom, the meter's cap is what is left, and a
   field that does not fit goes to review. Only when the program allowance
   cannot pay for one expert request is the record blocked, as before. A setup
   error before any request settles to nothing; research cut short by an
   error, or a step that overran its deadline, settles to what the meter spent.
9. **Time.** Research stops a minute before the step's deadline (210 s of the
   pilot's 270 s): a field still being researched becomes a timeout for the
   retry, and every settled field is kept. The work after research measured
   4.3 s on a slide-sized record with a 50 ms storage round trip per blob, most
   of it the integrity check, so the minute is more than three times it. The
   record's sources close when research ends, so a GBIF check still running
   cannot hold the step.

At the harness route's prices (USD 0.20 per million input tokens, USD 0.60
per million output), a typical record is expected to cost a few cents for
field research. The ceiling cannot be crossed.

## After field research: a reviewer's decisions

Field research runs once per run. When it has completed, a later pass (an
operator's retry or resume, or a reviewer's decision) researches nothing and
pays nothing: the clearance rules are applied again to the fields exactly as
they are. As on the native path, a reviewer's correction is kept exactly as
made and the record waits in review for that reviewer's approval; an approval
clears the record when the rules clear it, and a correction the rules refuse
stays in review. A taxon GBIF could not settle is cleared the way the ordinary
policy clears one: the reviewer chooses one of the candidates of the run's
last stored lookup (the taxonomy resolution decision reads only that one).
Field research therefore stores its GBIF lookups so that the last is the
last success or ambiguous one with candidates whose query is the whole name
the label writes, else the last such one with candidates; a lookup with none
(a failure, no match) is never last while one with candidates exists. Field research leaves such a taxon
ambiguous or unresolved, so a correction first records the name the label
writes. A name that lookup never returned cannot be chosen, and a value typed
in without that choice stays in review.
A corrected transcription is the one exception: its fields
are parsed again from the new text, and field research runs on them again.

A field research run that failed (an outage, a model error, a timeout) is
retried, and the retry researches only the fields that did not settle.

If `SPECIMEN_RESEARCH_HARNESS` is rolled back to "on", a run field research
left `retry_scheduled` (`field_research_timeout`, `field_research_model_error`,
`lookup_operational_failure`) is refused by native provisioning when its retry
comes due (`research_provision_run_unavailable`: native provisioning does
not accept a run at that stage), and each such run needs a manual Resume
(or Retry), which returns it to `plan`.

The worker check behind G38 derivation and the per-field research retry
(application.derivation_readiness) reports those native-only features as
unavailable when the worker runs with `SPECIMEN_RESEARCH_HARNESS=fields`. That
is intended: field research has neither.

The six-specialist code stays in the repository, unused by production, until
field research is proven live; a later pull request deletes it with its tests.
