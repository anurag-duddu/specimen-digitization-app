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
   field is cleared. The owner's decisions of 2026-10-09 clear two such
   cases: listed fields the label does not state, and a taxon with no genus
   (see "Fields the label does not state" below).
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
     whitespace collapse only, so "E. slope" and "E.slope" differ. An answer
     that takes a piece of a reading's candidate ("Danaus plexippus" where
     the candidate is "Danaus plexippus megalippe", "Sept. '46" where it is
     "3 Sept. '46", "San Pedro" where it is "San Pedro Sacatepequez") is
     refused, and a field with no candidate is never resolved: it goes to
     review. A candidate can itself be a piece of its reading, since the
     organiser's candidate need only lie inside its quote; for the taxon,
     the scientific-name parser reads the candidate's quote from the literal
     on (`checks.longer_name`), and a candidate whose quote writes a longer
     name there ("Danaus plexippus" quoting "Danaus plexippus megalippe")
     never settles the taxon: it goes to review ("The label writes a longer
     scientific name than this value."). A keyed line's "taxon:", an author
     and year, a sex sign or "sp. 1" are no longer name. Other fields'
     candidates are not checked against their quotes.
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
     never asked about is not a no-match. For a place field (country,
     province or state, county, city) such a label also settles when every
     text its readers write is confirmed and one authority_id confirms them
     all: the readers name that place ("Yepocapa," and "Yepocapa", both
     confirmed by one GEOLocate answer as the same town). That rests on the
     source's evidence, and each reader's text must match the candidate's
     name by the place comparison key (case, accents, punctuation, unit
     words), so texts that differ in those settle together ("Yepocapa," and
     "Yepocapa", "Chimaltenango Dept." and "Chimaltenango"); readers confirmed as
     different places, or not all confirmed, still go to review, and every
     other field keeps the one-confirmed rule. The answer then gives one
     reader's text as its literal with that authority_id and cites the
     answer that confirms it, and each reader's text stays in the value's
     lineage. An answer confirms a text as
     GBIF's decided candidate for the whole name it writes (a success
     answer), as the one candidate at a place field's level when it has that
     name (a success or ambiguous answer; see Places), or, for precise
     location, as a success answer's candidate of that name; a place source
     was asked about a text when the text is the query's first
     comma-separated part: the only name a gazetteer searches (the part
     before the first comma) and the place GEOLocate looks for. The rest of
     the query is larger units, so "San Pedro, Sacatepequez" asks about
     "San Pedro", never about "San Pedro Sacatepequez". A place query or
     candidate name is compared
     with a reader's text by the place tool's comparison key
     (`application/georef_locality.py` `comparison_key`: casefolded, accents
     and marks dropped, anything but letters and digits a single space, "Mt."
     read as "mount", unit words such as "Prov." or "Dept." dropped), so
     "Yepocapa," and "chimaltenango," were asked about by the queries
     "Yepocapa" and "Chimaltenango"; the literal itself stays as written, and
     a near spelling is never the same name here. The field settles
     when every label settles on the same literal, which is then the answer's literal
     (citing the confirming answer when a source settled a label), or, for
     labels (or a place's readers, above) that settle on different literals,
     when a source confirms each of those literals as the answer's
     authority_id (the same place ID or GBIF usage), the answer's literal is
     one of them and it cites the answer confirming it. Anything else goes
     to review, with each reader's candidate row still cited. So a field with no approved source (collectors,
     habitat, collection method, collection code, verbatim D/T/S), or only
     deterministic checks, goes to review when the readers of a label with no
     decided transcript differ. This follows the native harness's G20 and G32
     rules (`research_harness/evidence.py`); it is stricter than
     `application/field_resolution.py`, which clears readers that differ when
     every success names one value, unless they are a place's readers whose
     texts one candidate confirms (above).
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
     ("A.PCL..."; "A.ADM1"; "A.ADM2"; "P...."). GEOLocate settles only a
     city, with all its candidates at a city's level: for a country, a
     province or state, or a county its candidate is a part of the query
     itself (its country, its state or county part, or else its place part),
     which it only repeats, so it confirms nothing there (asked "Yepocapa,
     Chimaltenango, Guatemala" for a province
     "Yepocapa", its candidate is "Chimaltenango", a province inferred from a
     locality). So TGN's ambiguous
     answer for "Philippines" (the nation, a Dutch village, a sea) settles
     the country "P.I." as Philippines, and its answer for "Chimaltenango"
     (the department and its town) settles the province as the department
     and a city only as the town. Precise location stays the verbatim text.
   - **The label's own text (P3).** The answer that decides a place value
     was asked the label's own text: the query's first comma-separated part,
     the name the source searches, has the literal's comparison key (as
     above, case, accents, punctuation and notations such as "Prov." aside).
     For GEOLocate that part is the city it settles. There are two
     exceptions. A place notation (P4): when the literal is a notation
     of the table in `field_research/notations.py` for this field (compared
     by the same key, so "P. I." is "P.I."), the query may be the expansion
     the table gives it; the step then writes one evidence row of kind
     "rule" naming the table entry (locator `notation:<field>:<notation>`, no
     stored record, so it is never projected), and the value cites it as
     support. The table holds G29's notations as the briefs state them:
     "P.I." (country) is looked up as "Philippine Islands", "Guat." (country)
     as "Guatemala"; the shared brief's notation line is rendered from the
     same table. A near spelling: the query is the chosen candidate's own
     name, and that name is one letter from the literal
     (`georef_locality.one_letter_apart`: both full names, their comparison
     keys one insertion, deletion or substitution apart). That is the
     one-letter half of G34; the value settles only when the rest of G34
     holds too (below), and the step then records a `near_spelling:<field>`
     warning finding beside the record, naming the deciding answer, which
     never routes it. Any other lookup settles nothing, for decided and contested labels
     alike, in the expert's check and in the step: "Escuintla" asked for a
     label's "Chimaltenago", "Philippines" for "P.I." (a lookup of the modern
     name is context only), a notation the table does not hold, or a name
     two letters away ("Chimaltenango" for "Chimaltango"). So "P.I." settles
     its country on Getty TGN's answer to "Philippine Islands", whose one
     nation is the Philippines; TGN and NGA have no match for "P.I." itself
     (the coordinator's lookup of 2026-10-09).
   - **The label's other place fields (B3, N1).** A place below the
     country settles only when its source names, among the places it lies
     in, the country (and province) settled from the reading the answer
     names. This is a check by name and by record on those readings, not
     proof that the place lies inside the label's country and province
     (limits below). Only the step checks this (the brief tells
     the expert): it does so once every field's
     outcome is in, the country first, then the province, county and city,
     since the experts run at once and the country must be known
     (`step._misfit`, `agreement.parents_refusal`). Each source names the
     places a candidate lies in (`SourceCandidate.parents`): Getty TGN and
     Wikidata name each parent by its own record, so TGN's "Pilipinas" is
     the record tgn:1000135 it calls "Philippines" when searched; NGA names a
     first-order unit and a two-letter country code ("GT"), which a
     country's name does not match; a GEOLocate match lies in its admin unit (the
     first-level unit outside the USA, the county inside it), the queried
     state inside the USA, and the queried country, the only one GEOLocate
     searches. For each reading the answer names (its label's decided
     reading, on a label with one), another place field is written by the
     reading when the reading has text for it, and settled for it when its
     value is supported, the step has done with it, and the reading writes
     its literal (compared as place names). A parent is that field when it
     is the field's settled record (its authority_id), or when its name has
     the comparison key of one of the field's texts, of the notation table's
     expansion of one, or of the value the field settled on. Then:
     - a province, county or city settles only when its candidate has
       parents and one is the country settled for the reading, and, for a
       county or a city, one is also the province settled for it when one
       is. With no country settled for the reading, no parents, or none
       that is that country or province, the field goes to review with the
       reason ("The place found is not in the country the label gives.").
       So a Philippine label (P.I. settled as the Philippines, Davao, Mati)
       never settles its province on TGN's department of Guatemala, and
       Wikidata's one department for "San Pedro", in Paraguay, never settles
       a Guatemalan province. A country needs no parent. A place that waits
       for a country whose research failed is researched again with it on
       the retry;
     - a near spelling, of any place field, settles only on G34's whole
       condition: every other place field the reading writes, all of them
       and at least one, is one of the candidate's parents. In Getty TGN a
       province's parents are its country, so a near-spelled province with
       a county or a city on its reading goes to review, unless that county
       or city has the country's name. A country can settle: `sources._place` adds a
       place's country to its parents, so Getty TGN's nation lists itself,
       and a near-spelled country settles when every other place field on
       its reading has the nation's name or record ("Guatamala" beside the
       province "Guatemala" alone). Beside a county, a city or a province of
       another name it goes to review.

     The check's limits (the fourth review's NB1): a parent counts by name
     even when it is another place of that name. Getty TGN names a US
     county without "County" (its live answers of 2026-10-09), so a
     Graniteville in Nevada County, California, lies "in Nevada" and
     settles on a label whose state is Nevada, and a town in the US state
     of Georgia settles under the nation Georgia. Only the readings the
     answer names are read, so a province that only another reader of the
     label writes is not checked. A city is checked against the country and
     the province, never the county.
   - **105526330's province.** The decided reading writes "Chimaltenago" and
     Getty TGN knows only "Chimaltenango". An answer that takes the other
     reader's "Chimaltenango" as its literal is refused (G19). An answer that
     keeps "Chimaltenago" as the literal, as written (G27), and takes TGN's
     department Chimaltenango, one letter from it, as the value, passes the
     expert's check; but the reading also writes the city Yepocapa, which is
     not one of the department's parents, so the step leaves the province
     for review (G34's whole condition).
   - **The taxon.** A taxon is GBIF's decision for the whole name its
     candidate literal writes: the cited success answer's query is the
     scientific-name parser's query for that literal (the genus, any
     subgenus, the species epithet and any infraspecific epithet with its
     marker, as written, with or without the author and year written), or the
     genus alone for a "sp." identification (G25). A query for part of the
     name or for another name on the line grounds nothing, and a label with no
     genus ("sp. 30") has no groundable query: such a taxon clears as
     written, unmatched, on the owner's decision B (see "Fields the label
     does not state" below). The value and identifier are
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
   the check's number. Then the listed fields the label does not state are
   marked so (see "Fields the label does not state" below).
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

## Fields the label does not state (owner, 2026-10-09)

The owner decided two cases in the schema session on 2026-10-09. On whether
a required field the label doesn't state should keep going to review or
clear as "not on the label": "clearing as not on the label is fine" (A). On
whether a taxon with no genus should clear as written, marked "unmatched":
"ok" (B). The list below is the schema session's engineering reading of A
(`~/specimen-golive/status/schema-harness-plan.md`, H6 item 5); the owner
may narrow it.

**The list (A).** It is kept in `field_research/contracts.py`
(`NOT_ON_LABEL`), keyed by the collection profile's id and version
(`zoology_insects_slides` 1.0.0), and the step reads it through the run's
own pinned profile. A Retry keeps the run's profile snapshot, so a key added
to the published profile would never reach it; the published profile, its
digest and its byte pins are unchanged. Another profile, or a new version of
this one, gets its own entry.
- On the list: county, city, collection code, collection method, date
  identified, habitat, the four elevations and precise location.
- Never on it, whatever a profile lists, because their absence usually
  means a reading failed: catalogue number, country, the two collecting
  dates and collectors; and the taxon, which follows B. Province or state,
  verbatim D/T/S and identified-by IRN keep today's behaviour.

**When a listed field clears as not on the label.** Only when all of these
hold (`step.mark_not_on_label`, after the derived values, so a derivable
elevation is derived first, and only for a field a person has not decided):
1. Its expert searched and answered that no reading states it
   (label_lacks_value), with no failure. A field finalized without a model
   call, or a fallback answer (sources_cannot_resolve), never qualifies.
2. Its value is still not present.
3. Label coverage is confirmed, every label has two or more readings, and
   every reading has text.
4. No part of any label is unreadable: no reader's unreadable span or
   "[unreadable]" text, and no transcript marked unreadable.
5. The organiser found no text for it: no candidate, no literal, no
   reader's verbatim. For a county, a city or a precise location, a text
   counts as absent only when it sits inside the literal of another settled
   place field (both case folded, whitespace collapsed): the organiser's
   "Mt. McKinley" as a city, inside the settled precise location "E. slope
   Mt. McKinley", or the town "Yepocapa" as a precise location beside the
   settled city "Yepocapa".
6. For an elevation, no reading writes an elevation, as the place tool
   reads one (`georef_locality.read_locality`, on each reading's whole text
   and on each of its lines).
7. For a precise location, a city or a county is settled: the readings
   then carry nothing finer than the places settled (the town-only labels
   of 105526328 to 105526330).

The value keeps the state "not present", which the app shows as "This field
is not present on the label", and its reason starts "Not on the label:". It
cites one check row (kind "derived", locator `check:not_on_label`) whose
excerpt and stored record name every reading of the run, by name and
observation. The row lists no observation ids itself: one evidence row may
cite readings of one label only (`integrity.verify_evidence`). The clearance
rules (`step.not_on_label`) then skip mandatory_unresolved for the field,
only while the value cites that row, the row names the run's current
readings, and, for a precise location, a city or county is still settled.
So catalogue number, country, the collecting dates and collectors still go
to review when the label lacks them, as does any listed field a reading
writes, a label with an unreadable part, and a label whose coverage is not
confirmed.

**A taxon with no genus (B).** A taxon whose label writes only a morphocode
with no genus ("sp. 30" with a sex sign) clears as written, marked
unmatched (`step._unmatched_taxon`), when its expert found that GBIF cannot
resolve it (sources_cannot_resolve) and:
- the organiser's literal names no genus (`checks.names_no_genus`: the
  scientific-name parser reads no name in it, it has no whole-name GBIF
  query, and it is "sp.", a number or a short code, and optional sex signs);
- every taxon candidate is the same morphocode (`checks.morphocode`: the
  same number or code, case, spacing, punctuation and sex signs aside, so a
  reader's "Sp.30" beside "sp. 30", never "sp. 39");
- the readers settle on the literal by the rule for readers that disagree
  (step 5 above): with no successful lookup, that is a label's decided
  transcript, its other readers evidence only, or readers of a label with
  none that each write exactly that text.

The value is supported, with the literal as written, no authority, the
settled layer and the reason "Unmatched: the label names no genus, so GBIF
has nothing to match". It cites one check row (locator
`check:taxon_no_genus`) naming the literal and GBIF's no-match, which the
run keeps among its lookups (`lookup.no_name_lookup`: no match, and no
request made; the step adds it when the expert never asked GBIF that
literal). The clearance rules do not give such a taxon taxonomy_unresolved
(`step.taxon_unmatched`). A taxon with a genus that GBIF cannot decide, such
as 105526328's "Epipsocus", still goes to review.

**Known limitation.** The canonical projection skips a field with no literal
(`application/projection.py`, `_fields`), so the record in Data Connect does
not link a not-on-the-label value to its check row; the row itself is kept
with the run's evidence.

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

A field cleared as not on the label, or a taxon cleared as unmatched, is
reopened like any other field with Correct value: the reviewer's value is
kept as made and the record waits for that reviewer's approval. Every later
pass checks a not-on-the-label value again: it clears only while it cites
its check row and that row names the run's current readings. A not-present
value with no such row, as every record researched before 2026-10-09 has,
never clears on a re-check; only new research writes the row.

A field research run that failed (an outage, a model error, a timeout) is
retried, and the retry researches only the fields that did not settle (a
province, county or city that waited for a country that did not settle
is among them). A field marked not on the label is not settled, so the
retry researches it again, and it then cites only the row the retry writes.

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
