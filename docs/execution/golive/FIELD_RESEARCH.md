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
   and only its approved tools. All experts run at once. After the step has
   decided (steps 5 to 7), each field of the attempt is one
   `field_research.field` span inside the step's `field_research` span
   (`step.trace_fields`): the expert's outcome, its failure and fallback,
   the value's state and layer, the run's reason codes for the field, the
   check that refused a resolved answer and the rule that decided the field
   (rule A or B, a derivation, an unreachable source on the last attempt),
   and each lookup as source and status. These are codes; the literal,
   value, authority id and reason are added only when the worker captures
   approved content.
4. **Sources.** GBIF (with Catalogue of Life and Global Names Verifier
   alongside), GEOLocate, Getty TGN, Wikidata and NGA, plus deterministic date,
   elevation and catalogue-number checks. One request per distinct query per
   record (shared cache), retries with backoff (three attempts, a Retry-After
   of at most 10 s honoured, a redirect never followed), GEOLocate spacing
   kept, and at most two requests at a time to each of Getty TGN, Wikidata
   and NGA across the worker process (`sources.SOURCE_SLOTS`). Each source
   response is stored once as evidence. Each request a source leaves
   unanswered (a final status other than 200, or retries that ran out) is
   logged in one WARNING line with the source, the host, the HTTP status or
   the error's class, whether a Retry-After came back and the attempt it
   ended on, never the query; for GBIF, the status its verification ended on.

   **A source that cannot be reached** (a lookup whose last attempt was rate
   limited, timed out, was refused or redirected, failed on the server or
   came back unreadable; a refused query is not one) does not void the
   field when another of its expert's lookups answered. The expert's answer
   then stands and is checked under the rules of step 5 like any other, and
   the field's reason ends by naming the source ("Getty TGN could not be
   reached; settled from Wikidata."). A place settles on a cited answer of
   any place source, so no Getty TGN answer is needed. Only when every
   lookup the expert made failed, at least one because its source could not
   be reached, does an unresolved answer leave the field for a retry
   (`source_unavailable`; see step 7). The place briefs tell the expert to
   decide with the sources that answered and to say which did not.
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
     on, and, for a literal in which it reads no genus, with the word the
     quote writes immediately before the literal when that word may be a
     genus (`checks.longer_name`). A candidate whose quote writes a longer
     name there ("Danaus plexippus" quoting "Danaus plexippus megalippe",
     "sp. 1" quoting "Epipsocus sp. 1") never settles the taxon: it goes to
     review ("The label writes a longer scientific name than this value.").
     A keyed line's "taxon:", an author and year, a sex sign or "sp. 1" are
     no longer name. Other fields' candidates are not checked against their
     quotes.
   - **A doubtful genus (taxon only).** The literal never settles the taxon
     when the label marks its genus as doubtful (`checks.genus_in_doubt`,
     through `agreement._genus_in_doubt`): wherever the quote of a candidate
     of that literal, the text of a reading the answer names, or the text of
     its label's decided reading writes the literal:
     - a qualifier, read as the doubt signs read one (below, under B; a
       person's initials such as "C.F." are none), stands in the
       whitespace-separated part holding the literal's first word
       ("cfr.Epipsocus") or in the part just before it, across a line
       break too ("cfr. Epipsocus", "cf." ending the line above); or
     - a question mark ("?", the full-width one, U+FF1F, or the inverted
       one, U+00BF: `checks.QUESTION_MARKS`) is on that word itself ("Epipsocus?",
       "?Epipsocus", "Epipsocus(?)"), or stands alone, a part with no letter
       or digit, just before or just after it on its line ("? Epipsocus",
       "(?) Epipsocus", "Epipsocus ?", "Epipsocus ? sp. 1", "Epipsocus
       (?)").

     A question mark on or beside another word ("Davao? Epipsocus",
     "Epipsocus sp. 1 ?"), any on the line above ("1946?" above "Epipsocus
     sp. 1") or below ("?" under "Epipsocus"), and a qualifier after the
     genus ("Epipsocus cf. sp. 1", G25) are none. The value goes to review ("The label marks this
     name's genus as doubtful."): GBIF may decide the bare genus the taxon
     brief has the expert look up, and an expert that then resolves the
     taxon as that genus ("Epipsocus" quoting "cfr. Epipsocus", or quoting
     "Epipsocus" on a reading line that writes "Epipsocus?") is refused.
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
   sends the record to Needs human review with a plain reason. A field whose
   expert reached no source (step 4), a model failure and a field's timeout
   leave the record blocked with a retry, every settled field kept. The
   workflow allows the run's `max_attempts` attempts (its execution policy,
   3 by default). On
   the step's last attempt a field whose sources still could not be reached
   goes to Needs human review instead, unresolved, its reason naming them
   ("Getty TGN could not be reached after 3 attempts."), and the record
   finalizes with its other fields. A model failure or timeout on the last
   attempt still stops the automatic retries
   (`retry_budget_exhausted:<code>`). The app judges such a blocker by the
   cause after the colon, never by the word "budget" in the prefix, and never
   shows the code. The processing panel's "Blocked:" line names the cause and
   a two-sentence passage says what happened and what to do; the workbench
   issue list shows the same cause and next step; the queue row, the history,
   the blocker filter menu and the reason chips show the name alone:

   | Cause after the colon | Name | Sentences |
   | --- | --- | --- |
   | `lookup_operational_failure` | Approved source not reachable | An approved source could not be reached after repeated attempts. Retry later, or ask an administrator. |
   | `field_research_timeout` | Field research ran out of time | Field research ran out of time after repeated attempts. Retry later, or ask an administrator. |
   | `field_research_model_error` | No usable model answer | The model gave no usable answer after repeated attempts. Retry later, or ask an administrator. |
   | any other cause | Automatic retries stopped | Processing stopped after repeated attempts. Retry later, or ask an administrator. |

   A cause containing "budget" or "cost" is a cost limit and reads "Cost
   limit reached" with "Processing stopped at a cost limit." A blocker the
   app has no name for, whether or not it carries a colon, reads "Needs an
   operator check" with "Processing needs an operator check before it can
   continue. Ask an administrator to review it." The raw code stays in the
   workbench's "Technical review details" drawer (inside the closed "Review
   details" disclosure), which lists each issue's `reason_code`. The history's
   "Retained version data" drawer also holds a past version's raw record.
   No line, sentence, row or menu above shows it.
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
1. Its expert itself answered that no reading states it
   (label_lacks_value), with no failure, in this attempt. The field was not
   finalized without a model call, so the answer is the model's; no lookup
   is required, since a field such as the habitat has no source to search.
   The resolver's fallback, put in place of an answer the expert never gave
   (out of attempts, or answers that failed their checks), is
   sources_cannot_resolve, so it never qualifies.
2. Its value is still not present.
3. Label coverage is confirmed, every label has two or more readings, and
   every reading has text.
4. No part of any label is unreadable: no reader's unreadable span, no
   transcript marked unreadable, and no placeholder for an unread word
   anywhere in a reader's, a reading's or a transcript's text
   (`checks.shows_placeholder`, the one test rule B reads too). The
   placeholders are "[unreadable]" (the marker the reader prompt asks for
   in place of each unreadable span), "(unreadable)", "[illegible]",
   "(illegible)", "[illeg.]", "[illeg]", "(illeg.)", "[unclear]",
   "(unclear)", "[?]", "???", "...", "[...]" and the ellipsis character, in
   any case (`checks.DOUBT_PLACEHOLDERS`; "..." also inside "...."), and
   the words "illegible" and "unreadable" standing alone, in any case
   (`checks.PLACEHOLDER_WORDS`; never "illegibly").
5. The organiser found no text for it: no candidate, no literal, no
   reader's verbatim. For a county, a city or a precise location, a text
   counts as absent only when its whole words, compared by the place
   comparison key (case, accents and punctuation aside, "Mt." read as
   "mount"), are a run of the words of another settled place field's
   literal, and it writes no unit word of its own (County, Co., Prov.,
   Dept., Mun. and the others the place tool knows): the organiser's
   "Mt. McKinley" as a city, inside the settled precise location "E. slope
   Mt. McKinley", or the town "Yepocapa" as a precise location beside the
   settled city "Yepocapa". "Lee" beside the city "Leesburg", or "Cook
   County" inside the precise location "Cook County Forest Preserve", does
   not count.
6. For an elevation, no reading writes an elevation
   (`step._elevation_written`, on every reading's and every reader's text).
   That is, none of:
   - an elevation as the place tool reads one
     (`georef_locality.read_locality`, on each whole text and on each of its
     lines; the tool is unchanged);
   - a number in metres above sea level, however the unit is spaced or
     dotted: "msnm", "m snm", "m.s.n.m.", "masl", "m a.s.l." ("2000 msnm",
     "1200 masl", `step.SEA_LEVEL_METRES`);
   - a number, then one of the units "m", "mt", "mts", "mtr", "mtrs",
     "metro", "metros", "msm", "pies" or "p.s.n.m." (its letters dotted or
     not, spaced or not: "psnm", "p s n m"), with an optional final period
     and in any case ("1200 mts.", "1200 mts", "1200 metros", "1200 msm",
     "6400 pies", "6400 p.s.n.m.", "1200 m.", "1200 m",
     `step.NUMBER_AND_UNIT`). The number never follows a letter, a digit, a
     "-" or a "/", so it is never the end of a date or a code
     ("V-4-67-1"), and it may be a range ("1200-1500 mts."); the unit is a
     whole word on the number's line ("1200 mm" is none). "1200 m" and
     "1200 m." are read by the place tool too.
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

**A taxon with no genus (B).** A taxon whose label names no genus for its
morphocode ("sp. 30" with a sex sign, and no genus written beside it)
clears as written, marked unmatched (`step._unmatched_taxon`), only when
all of these hold:
- its expert itself answered that GBIF cannot resolve it
  (sources_cannot_resolve), with no failure, not finalized without a model
  call, and not as the resolver's fallback (`FieldOutcome.fallback`: an expert out of
  attempts, or whose answers kept failing their checks); its answer's
  literal is the code itself, compared with the organiser's literal as
  the GBIF query guard below compares a query (case, spaces, punctuation
  and sex signs aside), whether or not it asked GBIF, so an answer quoting
  "Epipsocus", the slide number, another code or nothing never qualifies;
  and it answered after a GBIF lookup attempt for the field, or quoting
  as its literal the morphocode a reading it names writes
  (`step._expert_found_no_genus`);
- no GBIF answer the expert received for the field shows a genus
  (`step._answer_found_a_genus`): none has candidates (105526328's
  "Epipsocus" homonym has two), none has the status success or ambiguous
  (a name the GBIF tool withholds unsent is ambiguous), and no query the
  expert asked GBIF names a genus (`checks.query_names_a_genus`). A query
  names a genus when the scientific-name parser reads a name in it as
  written ("Epipsocus", "Epipsocus sp. 1", "Epipsocus prob. sp. 1"), with
  the emphasis marks "*" and "_" dropped and its first letter a capital
  ("epipsocus", "*Epipsocus*", "epipsocus sp. 1"), or as its tokens (the
  label check's tokens, below) with the first letter a capital
  ("Epipsocus(?)"); or when, its morphocodes aside, any of its tokens may
  be a genus by the label check's test below ("EPIPSOCUS", "ep1psocus",
  "Epipsocu5", "(epipsocus)", "E. sp. 1", "E.?", an "Epipsocus" with an
  accented capital). The taxon brief has the
  expert look up the genus a label writes, so such a lookup is its own
  finding that the label writes one, wherever on the label the genus
  stands. The brief has it look up alone, before it answers for a
  morphocode, any genus any label writes anywhere (on another line or
  another label, with a qualifier or without), and a genus in doubt too:
  a genus, or a word that may be one, behind a qualifier of any spelling
  ("cf.", "cfr.", "c.f.", "aff.", "nr.", "conf.", "poss.", "prob.") or
  with "?" is looked up as the bare genus word, with no qualifier and no
  epithet, and the expert then answers sources_cannot_resolve whatever
  GBIF says (`prompts/taxon.txt`). GBIF's no-name answer for a morphocode (no match, no candidates,
  "sp. 30" asked) shows none, so the pilots' codes still clear with no
  GBIF lookup or after that answer;
- the expert asked GBIF, for the field, no query but the code itself
  (`step._gbif_asked_another_name`, `checks.query_is_the_code`): each
  query is compared with the organiser's literal once case, spaces,
  punctuation and sex signs are stripped from both. So "Sp.30" or "SP 30"
  asked for "sp. 30" qualifies, and any other query holds the taxon back:
  a misread genus the test above does not count ("Epipsocu55"), a slide
  number, another code, or an empty query. The taxon brief never has the
  expert send GBIF a name no reading prints. GBIF's no-name lookup that the
  step adds itself is no query;
- the organiser's literal is a morphocode (`checks.names_no_genus`: the
  scientific-name parser reads no name in it, it has no whole-name GBIF
  query, and it is "sp.", then a number with an optional letter, or a
  short lower-case code after a space or a period, then optional sex
  signs; "spp", "sp. nov.", "sp. n.", "sp. aff." and "sp. cf." are none);
- every taxon candidate is the same morphocode (`checks.morphocode`: the
  same number or code, case, spacing, punctuation and sex signs aside, so a
  reader's "Sp.30" beside "sp. 30", never "sp. 39"). This compares the
  organiser's candidates. Readers of a label with no decided transcript
  whose codes differ never settle (the readers' rule below). On a label
  with a decided transcript, the rule refuses another reader's different
  code only when the organiser gives that reader's text as a candidate;
  where it gives none, the decided transcript's code clears alone, as G19
  decides every field on a decided label (#284);
- the label names no genus for that code (`checks.label_names_no_genus`):
  this is judged on every reading's text, not on the organiser's literal.
  Wherever any reading writes the code, no token beside it may be a genus
  (`checks.genus_beside`). A token is a whitespace-separated word with
  "?", "*", "_", straight and curly quotes, backticks, brackets, ",", ";"
  and ":" shed at either end, and a qualifier of the doubt signs' list
  (below) with its final period shed at the start, or at the end with no
  letter right before it, written against the word or as a word of its
  own ("cf.Epipsocus", "c.f.Epipsocus" and "Conf.Epipsocus" are
  "Epipsocus"; a person's initials such as "C.F." keep their letters;
  `checks._token`); what then holds no letter or digit (a sex
  sign, a "+", a lone "?" or "cf.") is no token. Two tokens are read: the one
  written immediately before the code (the last before it on its line or,
  when its line has none there, the last of the nearest line above that
  has one), and the first after the code on its line. Either may be a
  genus (`checks.may_be_genus`), judged with its first letter made a
  capital, as the query check above judges a token: when it holds a letter
  and no digit ("Epipsocus", "epipsocus?", "E.?", "cf.Epipsocus",
  "R.D.mitchell", "legs", the reader's "[unreadable]"); when it is then a
  capital followed by letters and digits ending in a letter, with an
  optional final period ("Ep1psocus", "ep1psocus"); or when it holds three
  letters or more and one digit at most, a genus misread with a digit
  ("Epipsocu5", "3pipsocus"; with one digit, no date or number
  punctuation stands between digits). Any other token is none: "V-4-67-1",
  "6400'", "IX-14-46", "Epipsocu55". The token after the code is passed over
  when it is, as written, one of `checks.NOT_GENERA`, the one list of
  such words: legs, leg, wings, wing, head, terminalia, genitalia, slide,
  mount and the two sex signs. On the taxon's keyed line ("taxon: sp.
  30", as `Workflow.parse` reads key: value text) the key is no token;
  when the nearest line above with a token is itself a keyed line
  ("verbatim_dts: ..."), it is another field's, and no token before the
  code is read. So "Epipsocus sp. 1", "Epipsocus", "Epipsocus?" or
  "[unreadable]" with "sp. 1" on the next line (as on 105526328), "E.?
  sp. 1", "Epipsocu5 sp. 1" and "legs sp. 1" never clear as unmatched,
  whatever the organiser's candidate is; the pilot's 105526321 ("Mossy
  forest 6400'" above "sp. 30"), 105526326 ("Sp. 22" on a label of its
  own) and 105526327 ("V-4-67-1" above "sp 22", "legs" on the line below)
  clear;
- no part of a label that writes the code is unreadable
  (`step._code_label_unreadable`): rule A's test (no reader's unreadable
  span, no transcript marked unreadable, no placeholder of rule A's list
  in a reader's, a reading's or a transcript's text,
  `checks.shows_placeholder`), applied to each label any of whose texts
  writes the code. An unreadable word there may be the genus;
- no sign of a doubtful or unreadable name shows anywhere on the specimen
  (`step._doubt_on_the_labels`): none in any reading's, reader's or
  transcript's text of any label, whether or not that label writes the
  code. The signs are one list, `checks.DOUBT_SIGNS`:
  - a question mark ("?", the full-width one, U+FF1F, or the inverted
    one, U+00BF: `checks.QUESTION_MARKS`) in a whitespace-separated part
    that holds a letter ("Epipsocus?", "?Epipsocus", "Epipsocus(?)",
    "E.?"), or in the part just before or just after one, across a line
    break too ("Epipsocus ?", "(?) Epipsocus", "Epipsocus" with "?" on the
    next line);
  - a qualifier (`checks.DOUBT_QUALIFIERS`): cf, cfr, aff, affin,
    affinis, nr, near, prob, probably, poss, possibly, conf, vic or prope,
    each a whole word, in any case except vic, which counts in lower case
    only (`checks.LOWER_CASE_QUALIFIERS`: "vic." and "v.i.c.", never "Vic."
    or "VIC", Victoria), and with or without its periods (a period may
    follow each of its letters, so "c.f.", "Cf.", "CF." and "n.r." are
    "cf" and "nr"), with no letter right before or after it: apart or
    against a word ("cf. Epipsocus", "CF.Epipsocus", "(cf) Epipsocus",
    "cfr. Epipsocus", "Epipsocus nr", "possibly Epipsocus"), never inside a
    longer word ("Nearctic", "Staff", "Victoria", "Proper"). Two or more
    capitals each followed by a period are a person's initials, never a
    qualifier (`checks._initials`: "C.F." in "leg. C.F. Baker" or "Baker,
    C.F.", "N.R. Smith");
  - a placeholder for an unread word, by rule A's own test
    (`checks.shows_placeholder`): "[unreadable]", "(unreadable)",
    "[illegible]", "(illegible)", "[illeg.]", "[illeg]", "(illeg.)",
    "[unclear]", "(unclear)", "[?]", "???", "...", "[...]" or the ellipsis
    character anywhere in a text, in any case, or the words "illegible"
    and "unreadable" standing alone, in any case;
  - a reader's unreadable span, or a transcript marked unreadable, on any
    label.

  These sit on top of the label check, which reads only the two tokens
  beside the code. The taxon brief has the expert look a doubtful genus up
  alone, a query the GBIF guard above refuses; the signs hold the taxon
  back when the expert makes no such lookup. So "Epipsocus?" above
  "V-4-67-1" above the code, on the line after the code or on another
  label, and "cf. Epipsocus", "cfr. Epipsocus" or "c.f. Epipsocus"
  anywhere, a determination label of its own included, keep the taxon in
  review, as does a locality's "near" or "nr." and a "?" beside any
  word; a collector's "C.F. Baker" and a locality's "Melbourne, Vic." do
  not. No reading of 105526321, 105526326 or 105526327 shows a sign.
  105526324's unreadable label, whose readers list the span and write
  "[unreadable]", holds back the "sp 22" another of its labels writes;
- the readers settle on the literal by the rule for readers that disagree
  (step 5 above): with no successful lookup, that is a label's decided
  transcript, its other readers evidence only, or readers of a label with
  none that each write exactly that text;
- the value meets the agreement rules every resolved answer meets
  (`agreement.refusal`): among them, no candidate of it may quote a longer
  name around it, and no text may mark the literal's first word as a
  doubtful genus (step 5 above).

The value is supported, with the literal as written, no authority, the
settled layer and the reason "Unmatched: the label names no genus, so GBIF
has nothing to match". It cites one check row (locator
`check:taxon_no_genus`) naming the literal and GBIF's no-match, which the
run keeps among its lookups (`lookup.no_name_lookup`: no match, and no
request made; the step adds it when the expert never asked GBIF that
literal). The clearance rules do not give such a taxon taxonomy_unresolved
(`step.taxon_unmatched`) while it cites that row, the run's readings still
name no genus beside its code, no part of a label that writes the code is
unreadable, no sign of a doubtful or unreadable name shows on any label,
and no GBIF lookup the run stores shows a genus
(`step._lookup_found_a_genus`: the same test, on the query sent or asked
and the name GBIF could not read) or asked anything but the code itself
(`step._lookup_asked_another_name`, on the same texts; the step's own
no-name lookup aside). A taxon with a genus that GBIF cannot
decide, such as 105526328's "Epipsocus", still goes to review, whether the
organiser's candidate is "Epipsocus sp. 1" or only "sp. 1": when the label
writes the genus, or any word that may be one, as a token beside the code,
by the label check; when a label that writes the code has an unreadable
part; when any label shows a sign of a doubtful or unreadable name; and,
wherever the label writes the genus, when the expert asked GBIF anything
but the code; and when the expert's answer quotes anything but the code.
Two cases remain, each only when the expert makes no lookup of a genus
its brief has it look up (alone, any genus a label writes, doubtful or
not, before it answers for a morphocode):
- a genus written with no doubt sign where the label check does not count
  it (away from the code, as "Epipsocus" above "V-4-67-1" above the code,
  on the line after the code's or on another label; or misread beside it
  into a token the label check's test does not count, as "Epipsocu55"),
  when the expert makes no GBIF lookup but of the code itself;
- a genus marked doubtful in a way the doubt signs do not read (a doubt
  word outside the qualifier list, as "sim. Epipsocus" above "V-4-67-1"
  above the code), when the expert likewise makes no GBIF lookup but of
  the code itself.

Each still clears as unmatched. Where the expert does look the genus up,
as its brief says, the GBIF guard refuses rule B, since that query is not
the code (`step._gbif_asked_another_name`;
`test_the_real_resolver_looking_the_genus_up_as_its_brief_says_keeps_the_taxon_in_review`
for "sim. Epipsocus" and "Epipsocus" above "V-4-67-1").

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
its check row and that row names the run's current readings. An unmatched
taxon is checked again too: it clears only while it cites its check row,
the run's readings name no genus beside its code, no part of a label that
writes the code is unreadable, no label shows a sign of a doubtful or
unreadable name, and no GBIF lookup the run stores shows a genus or asked
anything but the code. A not-present
value with no such row, as every record researched before 2026-10-09 has,
never clears on a re-check; only new research writes the row.

A field research run that failed (a field whose expert reached no source, a
model error, a timeout) is retried until its last allowed attempt, on which
a source still unreachable sends its field to review (step 7 above), and
the retry researches only the fields that did not settle (a
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
