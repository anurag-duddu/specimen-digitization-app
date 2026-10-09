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
   names them), the organiser's candidates and settled value for each field
   (a keyed line the parser read is a candidate of each reading that writes
   it), and the profile's field list.
2. **Accurate reads finalize.** A field with no approved source or check whose
   organiser value is supported is finalized as written, with no model call,
   on the readings that write it (of a label with a decided transcript, only
   the decided reading). The rules of step 5 apply to it.
3. **One expert per field.** Every other field gets its own Pydantic AI agent
   (`field_<key>`), its own instructions (shared rules plus the field's brief)
   and only its approved tools. All experts run at once.
4. **Sources.** GBIF (with Catalogue of Life and Global Names Verifier
   alongside), GEOLocate, Getty TGN, Wikidata and NGA, plus deterministic date,
   elevation and catalogue-number checks. One request per distinct query per
   record (shared cache), retries with backoff, GEOLocate spacing kept. Each
   source response is stored once as evidence.
5. **Checked answers.** The expert's answer check (an answer that breaks it
   is sent back for correction) and, again, the step before a resolved answer
   becomes a value apply these rules (`field_research/agreement.py`, on the
   source answers the field received):
   - The literal appears exactly in each reading the answer names.
   - **A whole candidate.** The literal is one of the field's candidate
     literals, whole, for each reading the answer names (on a label with a
     decided transcript, the decided reading's): the organiser's candidates,
     and each keyed line the parser read ("taxon: Danaus plexippus") on each
     reading that writes the line. Literals are compared after NFC and
     whitespace collapse only, so "E. slope" and "E.slope" differ. A piece of
     a reading ("Danaus plexippus" from "Danaus plexippus megalippe",
     "Sept. '46" from "3 Sept. '46", "San Pedro" from "San Pedro
     Sacatepequez") is never a literal, and a field with no candidate is never
     resolved: it goes to review.
   - A value that differs from the literal is a source candidate the expert
     was given, or a deterministic check's settled parse of that literal (an
     ambiguous check's readings are only options for a person). An elevation
     candidate that writes more than its number ("ca. 1200 m", "300-450 m")
     is the literal, and a number the elevation check returned for exactly
     that literal is the value (the briefs name which end).
   - **The decided transcript (G19).** On a label with a decided transcript,
     the decided reading's text contains the literal. The other reader's
     different text is kept as contradicting evidence and does not block.
   - **Readers and labels that disagree (G20, G27, G32).** Whatever state the
     organiser gave the field, each label that writes it settles on its own:
     a label with a decided transcript on its decided reading's one candidate
     literal (a label whose decided reading writes nothing for the field takes
     no part); a label whose readers each write the same one literal on that
     literal; any other label (readers that differ, or one that writes
     nothing) only when the expert asked the field's approved sources about
     every distinct text its readers write, exactly one is confirmed by an
     answer about it, and every other has a captured no_match answer
     about it and no success or ambiguous one. An error, a timeout or a text
     never asked about is not a no-match. An answer confirms a text as
     GBIF's decided candidate for the whole name it writes (a success
     answer), as the one candidate at a place field's level when it has that
     name (a success or ambiguous answer; see Places), or, for precise
     location, as a success answer's candidate of that name; a place source
     was asked about a text
     when the text is its whole query or the query's first comma-separated
     part (the name it searches). A place query or candidate name is compared
     with a reader's text by the place tool's comparison key
     (`application/georef_locality.py` `comparison_key`: casefolded, accents
     and marks dropped, anything but letters and digits a single space, "Mt."
     read as "mount", unit words such as "Prov." or "Dept." dropped), so
     "Yepocapa," and "chimaltenango," were asked about by the queries
     "Yepocapa" and "Chimaltenango"; the literal itself stays as written, and
     a near spelling is never the same name here. The field settles
     when every label settles on the same literal, which is then the answer's literal
     (citing the confirming answer when a source settled a label), or, for
     labels that settle on different literals, when a source confirms each
     label's literal as the answer's authority_id (the same place ID or GBIF
     usage). Anything else goes to review, with each reader's candidate row
     still cited. So a field with no approved source (collectors,
     habitat, collection method, collection code, verbatim D/T/S), or only
     deterministic checks, goes to review when the readers of a label with no
     decided transcript differ. This follows the native harness's G20 and G32
     rules (`research_harness/evidence.py`); it is stricter than
     `application/field_resolution.py`, which clears readers that differ when
     every success names one value.
   - **Places.** A place field (country, province or state, county, city)
     settles only on a cited success or ambiguous answer of a place source
     with exactly one candidate at the field's level, and that candidate is
     the value, with its authority_id; with none or several at the level the
     field goes to review. The levels are by each source's kinds, kept in
     `agreement.PLACE_LEVELS`: Getty TGN's place types ("nations"; "first
     level subdivisions (political entities)"; "second level subdivisions
     (political entities)" or "counties"; "inhabited places", "cities",
     "towns" or "villages"), Wikidata's instance-of labels ("country",
     "sovereign state"; "province", "former province", "department", "state";
     "county"; "city", "town", "village", "human settlement",
     "municipality", each also as "... of ..."), NGA's feature codes
     ("A.PCL..."; "A.ADM1"; "A.ADM2"; "P...."); GEOLocate is asked for the
     field's own level, so all its candidates are at it. So TGN's ambiguous
     answer for "Philippines" (the nation, a Dutch village, a sea) settles
     the country "P.I." as Philippines, and its answer for "Chimaltenango"
     (the department and its town) settles the province as the department
     and a city only as the town. Precise location stays the verbatim text.
   - **The label's own text (P3).** The answer that decides a place value
     was asked the label's own text: its query, or the query's first
     comma-separated part, has the literal's comparison key (as above, case,
     accents, punctuation and notations such as "Prov." aside). There are
     two exceptions. A place notation (P4): when the literal is a notation
     of the table in `field_research/notations.py` for this field (compared
     by the same key, so "P. I." is "P.I."), the query may be the expansion
     the table gives it; the step then writes one evidence row of kind
     "rule" naming the table entry (locator `notation:<field>:<notation>`, no
     stored record, so it is never projected), and the value cites it as
     support. The table holds G29's notations as the briefs state them:
     "P.I." (country) is looked up as "Philippine Islands", "Guat." (country)
     as "Guatemala"; the shared brief's notation line is rendered from the
     same table. G34's near-spelling bound: the query is the chosen
     candidate's own name, and that name is one letter from the literal
     (`georef_locality.one_letter_apart`: both full names, their comparison
     keys one insertion, deletion or substitution apart); the value then
     settles and the step records a `near_spelling:<field>` warning finding
     beside the record, naming the deciding answer, which never routes it.
     Any other lookup settles nothing, for decided and contested labels
     alike, in the expert's check and in the step: "Escuintla" asked for a
     label's "Chimaltenago", "Philippines" for "P.I." (a lookup of the modern
     name is context only), a notation the table does not hold, or a name
     two letters away ("Chimaltenango" for "Chimaltango"). So "P.I." settles
     its country on Getty TGN's answer to "Philippine Islands", whose one
     nation is the Philippines; TGN and NGA have no match for "P.I." itself
     (the coordinator's lookup of 2026-10-09).
   - **105526330's province.** The decided reading writes "Chimaltenago" and
     Getty TGN knows only "Chimaltenango". An answer that takes the other
     reader's "Chimaltenango" as its literal is refused (G19). The intended
     answer keeps "Chimaltenago" as the literal, as written (G27), and
     settles on TGN's department Chimaltenango, one letter from it, with the
     near_spelling finding.
   - **The taxon.** A taxon is GBIF's decision for the whole name its
     candidate literal writes: the cited success answer's query is the
     scientific-name parser's query for that literal (the genus, any
     subgenus, the species epithet and any infraspecific epithet with its
     marker, as written, with or without the author and year written), or the
     genus alone for a "sp." identification (G25). A query for part of the
     name or for another name on the line grounds nothing, and a label with no
     genus ("sp. 30") has no groundable query. The value and identifier are
     the candidate GBIF decided, never one of its alternatives. The clearance
     rules check the stored taxon the same way.

   An expert whose answer still fails the checks after its retries sends the
   field to review, never to a retry. At the step, an answer that breaks the
   rules is ambiguous (readers or labels disagree) or unresolved, never
   settled.
6. **Derived values** (G37, G41, G44) are filled deterministically afterwards
   from settled fields only: elevation copies and exact unit conversion, and
   the collection date's end from its start. An elevation settled on a
   candidate that writes more than its number is read as its parsed value,
   the check's number.
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
On a label with no decided transcript, a reviewer's field correction leaves
`unresolved_transcription:<region>` in place, even after approval (the
corrected value has no raw reading behind it): the way out is a transcription
decision, which reruns field research and pays for it again.

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
