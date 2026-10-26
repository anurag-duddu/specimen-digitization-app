# The first pass's reading units and the specimen ontology

Status: the owner's design, 2026-10-26, written from his words of 2026-10-25 and 2026-10-26, and
revised the same day after two reviews of pull request #418. The owner set the substance; the
structure and the rules below his words are the engineer's decisions (section 6). Nothing here is
built. Sections 2 to 5 say what exists today, naming the file that shows it, and what changes.
Section 7 is the build order; it is the same list as the plan's section 3
(`docs/execution/units/PLAN.md`).

## 1. The pipeline, in the owner's words

> "N transcriptions per label. Raw output. LLM with its system prompt should have context it passes
> on the label about the specimen and the raw transcripts and its own final version of the
> transcriptions possible words numbers char whatnot 1:1. Harnesses take all these run with them and
> do their lookups. We have specialized harnesses settling different fields."

> "The LLM is looking at words and deciding possible words. It can even say possible fields. So it
> should be raw transcript potentially means x, r1, r2, r3. Literally an array of sorts. [...] for each
> word or number [...] at a logical point break. [...] data could be on two different labels but
> belong to the same field to settle like taxa. [...] first pass never settles, it has to go to
> harness."

> "[LLM 1st pass, reader 1, reader 2, ... n] - potential fields, repeat for each word then send to
> harness. Yep it has to connect dots. Simple is location, it can't be Philippines and Cook County
> Chicago."

> "Derivation is not simple unit conversion. It's essential has a concept model and understanding of
> how specimens work and how their data is connected and works." "Think ontologically for conceptual
> model."

On the shape of the first pass's output: "It's not an array. I'm using an example. It could be what
best fits this structure. You decide. I'm not the engineer you are."

## 2. The reading units

The first pass reads every label of the specimen with the image. For each label it cuts the text at
logical breaks (a word, a number, a code, a date, a phrase that belongs together) and gives one
record per unit.

### The shape

Structure, decided by the engineer: a list of unit records, grouped by label and ordered by line, as
JSON (a Pydantic model `ReadingUnit`). Reasons: the first pass already answers in structured JSON
(`FirstPassOutput`, `application/first_pass.py`), and the experts receive one JSON document
(`field_research/experts.py`), so the units travel in it.

The units are a new record on the run. They do not fit the run's existing records: those refuse
unknown keys (`Record`, `application/domain.py`); the normalized projection publishes a fixed list
of transcript fields (`application/projection.py`, `AppendTranscriptionVersionV2`); and the app
checks the research thread against an embedded copy of the server's schema
(`apps/.../research/research_models.dart`). So the units get their own record type, their own
projection field and their own reader in the app, shipped together (plan WP 1.1). The run's existing
records, the `layer` values and the app's enums do not change.

### Who cuts the units

The first pass does, for every label, including labels whose readers agree. Today the first pass
runs only for a label whose readers' texts differ (`application/workflow.py`, "Differing readings
get the LLM first pass"), so this is one more call per agreed label; the plan costs it before the
change is accepted (WP 1.2). The code's alignment (`reading_differences_among`) does not decide the
units: it supplies candidate breaks. Today that alignment outputs differences only, drops a
difference of spacing alone ("Davao Prov." against "DavaoProv."), and has no units for agreed text.
The check below covers all three.

The check, run by code on every answer:

- The units of a label tile each reading's text: every character of every reading belongs to
  exactly one unit, in order; only whitespace may lie between units.
- A unit never ends inside a range: a hyphen, "to", "bis", "au" or a dash between two dates or two
  numbers keeps both ends in one unit (the experts' standing rule, `prompts/common.txt`, "A date or
  an elevation is never one end of a range").
- An empty unit list is refused.
- An answer that fails is sent back once, and the retry text names the check it failed. An answer
  that fails twice is given up on, as today (`first_pass_given_up`, `first_pass.py`).

A label whose transcript a person decided has one reader, the person. The first pass runs with that
one reading; its units are cut from the person's text alone, and `image` is that text. Today the
first pass refuses fewer than two readings (`first_pass_direct`); under this spec it refuses fewer
than one. The person's text binds the label (section 3, order 1).

### What each unit holds

| Key | What it holds |
|---|---|
| `label`, `line` | Which label and which line of it |
| `readers` | What each reader wrote for this unit: `{"A": "...", "B": "...", "C": "..."}`; empty when a reader wrote nothing here |
| `image` | What the first pass sees in the image at this unit: one of the readers' texts, `uncertain`, or `not visible`. It is a judgement of the image, never a vote among readers: when the image is clear it gives the text that matches it, even if only one reader wrote it and every other reader differs; `uncertain` only when the image itself is unclear at this unit. Never a text no reader wrote |
| `means` | The first pass's own interpretation of the unit, which may be text no reader wrote: an expansion ("P.I." -> "Philippine Islands"), a normal form ("6-Sept-1946" -> 1946-09-06), a role ("leg." -> collected by). May be empty. Never a literal |
| `fields` | The fields this unit could belong to, most likely first. Advice only: every expert receives every unit (section 3). May be empty |
| `note` | One short sentence when something matters (a mark only one reader saw) |

The first pass never settles anything. It lists. The units go to the harness together with the
raw readings, which stay available whole.

### The same label today and under this spec

Readings of pilot label e98a924c-L2 (a 1946 Field Museum slide label from the Philippines):

- A: `CNHM. E Slope Mt. / McKinley, Davao Prov. / Mindanao, P.I. / 6-Sept-1946, Elev.6400 / H. Hoogstraal leg. / Shrubs, mostly forest / wings 4 head / Sp.30 ♀`
- B: the same with `Elev.6400'`, `Forest`, `Wings`, and an extra line `P-95-81-16`
- C: the same with `DavaoProv.`, `Mostly forst`, `Wings & head`, `♂`, no extra line

What the first pass answered on this label with three readers, over 12 recorded runs
(`~/specimen-golive/runs/three-readers-20261025/fp_three_reps*.jsonl`): preferred reader none in 9,
A in 3. The foot mark: "A, no mark in the image" in 7, `uncertain` in 4, `neither` in 1. The extra
line `P-95-81-16`: `uncertain` in 7, A in 3, `neither` in 2. `4` not `&`, `♀` not `♂` and `forest`
not `forst`: 12 of 12. So on the two marks that matter, the one image judgement the harness gets
changes from run to run.

What the harness then did (`~/specimen-golive/runs/free-harness-20261025/`): with two readers,
collector, date, country, province, locality and the elevation all settled; the elevation settled at
6,400 ft because the elevation check read B's "Elev.6400'" as feet and A's "Elev.6400" as no unit,
so one reader's text was confirmed and the other ruled out. With three readers, collector and date
settled; the elevation went to review in both repeats (A and C write no unit, B writes the mark,
and the expert put both texts up as options); country, province and locality did not settle in
either repeat (a gazetteer timeout in the first, unresolved in the second). The difference between
the arms on the elevation is not the verdicts: it is that with a third reader writing no mark, the
expert treated the two texts as open possibilities instead of settling on the confirmed one.

Under this spec the first pass gives, among others (fields are the profile's; where today's
experts put a unit is noted):

| unit | readers | image | means | fields |
|---|---|---|---|---|
| CNHM. | A, B, C same | CNHM. | Chicago Natural History Museum, the Field Museum's name 1943-1966 | collection_code today (4 of 5 runs); the ontology decides whether an institution name is a code |
| E Slope Mt. McKinley | A, B, C same | same | east slope of Mount McKinley, a locality | precise_location |
| Mindanao | same | same | the island | context for precise_location; no field of its own |
| P.I. | same | same | Philippine Islands | country |
| 6-Sept-1946 | same | same | 1946-09-06 | date_visited_from |
| Elev.6400 / Elev.6400' | A "Elev.6400", B "Elev.6400'", C "Elev.6400" | "Elev.6400" or uncertain (the 12 recorded runs judged the mark absent in 7 and uncertain in 4) | elevation 6400, unit not certain from the image | elevation_from_ft |
| H. Hoogstraal leg. | same | same | collected by H. Hoogstraal | collectors |
| Shrubs, mostly forest | A "forest", B "Forest", C "forst" | forest | habitat note | habitat |
| wings 4 head / Wings & head | A, B "4", C "&" | 4 | a preparation note | none: `verbatim_dts` holds non-standard collecting-event date and time expressions ("Summer 1914", "am"), as `PRD.md` section 22, question 3, records the answer of 2026-10-07; a preparation note is not one. The brief's sentence calling the field's meaning open is stale and is corrected in plan WP 1.7 |
| Sp.30 ♀ / ♂ | A, B "♀", C "♂" | ♀ | species number 30, female | taxon today (5 of 5 runs); the ontology decides where a species number and a sex go |
| P-95-81-16 | B only | uncertain | a code | collection_code, doubtful |

The harness then settles the elevation. The number, 6400, is in every reader's text; only the unit
is open, and the image does not settle it (7 runs name the text without the mark, 4 are
uncertain). The ontology's rule decides the unit, and only with positive evidence. A unit the label
does not write is inferred as feet when all three hold:

- (a) at least one reader wrote the foot mark or "ft" at this unit;
- (b) the number read as metres is impossible for the settled country: above its highest point
  (for the Philippines, Mount Apo, 2,954 m, from the table in the ontology file);
- (c) the number read as feet is possible for it.

Here (a) B wrote `Elev.6400'`; (b) 6,400 m is above 2,954 m; (c) 6,400 ft is 1,951 m. The value is
6,400 ft, basis `inferred`, the rule named, shown so to the reviewer; the literal stays a reader's
text as written. Without (a) the field goes to review: magnitude alone never decides, so an
"Elev.16000" that no reader wrote a mark for goes to review, and so does a number impossible in
both units (16,000 ft is 4,877 m, also above 2,954 m). The rule needs the country settled first
(section 3, round 2). This reverses, deliberately and only through this named rule, the standing
rule that a unit is never guessed (`GEOREFERENCING.md` section 3, Parse row; `FIELD_RESEARCH.md`;
the elevation briefs; `agreement.py`'s `NO_UNIT` refusal: "A unit is never guessed from the
magnitude, the place or a map"). Terrain data takes no part: Copernicus GLO-30 (D11) is approved
for a missing elevation over a georeferenced place (`golive/PLAN.md` section 4.8), and D5 is held,
so while it is held a terrain check records its measurement and changes no outcome
(`GEOREFERENCING.md` section 3, Measurements row). No owner ask is made on D5 now. No gazetteer
holds this Mount McKinley (`GEOREFERENCING.md`, the Mount Talomo crosswalk), so the locality itself
stays what it is today.

## 3. The harness

The field experts stay as they are in shape: one per field, with lookups. Two exceptions exist today
and stay: `identified_by_irn` gets no model call (`field_research/step.py`, `NO_APPROVED_AUTHORITY`),
and five fields have no lookup at all (collectors, collection code, habitat, collection method,
verbatim D/T/S: `field_research/contracts.py`, `FIELD_TOOLS`), so they settle on the image, on
readers that agree or on another label only, never on a source. What changes is what the experts
receive, in what order they run, and what may settle a field.

### What an expert receives

- Every reading unit of every label, with its `readers`, `image`, `means` and `fields`. `fields` is
  advice: an expert reads every unit, as today every expert reads every reading (`experts.py`) and
  may recover a field the organiser missed (`prompts/common.txt`, "The literal").
- Every raw reading, whole, as today.
- The ontology (section 4), rendered into its instructions.
- In the second round, the fields the first round settled that its rules name (below).

### Two rounds

Today every expert runs at once with one copy of the other fields, taken before any expert answers
(`step.py`, `build_tasks`), and the brief calls those fields "context only" (`common.txt`). Under
this spec the experts run in two rounds. Round 1: every field, independently, as today. Round 2:
only the fields whose ontology rules name a field settled in round 1: province after country;
county and city after province; the elevation unit after country; the end date after the start
date. The dependency order is written in the ontology file, is acyclic (a test checks it), and two
rounds are the maximum. A round-2 value records the round-1 value it used as one of its inputs,
with the rule, so the record shows what it rests on.

### What settles a field: one order

A field on one label settles on the first reason in this list that applies, with the one exception
stated after it. The order is written here once and the code follows it.

1. A person decided the label's transcript: the person's text binds, whatever the sources say.
   Reason `BY_PERSON` (today this travels as `BY_FIRST_PASS` with `person_decided`, `agreement.py`;
   the behaviour is kept under the new name).
2. A source confirms exactly one reader's text by its own name or expansion, and every other
   reader's text is ruled out. Reason `BY_SOURCE` (today's).
3. The image names one reader's text at the unit. Reason `BY_IMAGE` (new).
4. For a place: one reader's text is a near spelling of a source's one candidate, every other text
   is ruled out, and the image names that reader or is uncertain. Reason `BY_NEAR_SPELLING`
   (today's).
5. Every reader of the label writes the same text, letter case and spacing aside. Reason
   `BY_AGREEMENT` (today's; it stays as one reason and is no longer the gate for everything).
6. Another label of the specimen, read by two or more readers who agree, writes the text. Reason
   `BY_OTHER_LABEL` (today's, with `MIN_BACKING_READERS = 2`).
7. Otherwise the field goes to review with each standing text as an option
   (`several_possibilities`, as today).

The exception: a conflict between 2 and 3 does not settle. When a source confirms B's text and the
image names A's, the field goes to review with both, finding `image_source_conflict`. This keeps
the guard `confirmed_against_image` gives today (a near spelling or another label never overrides a
text the first pass found in the image; `agreement.py`), under the new name `image_names`; a source
is added to what the guard holds against.

Each settled value's finding names its reason (`settled_<reason>:<field>:<label>`), replacing
today's `first_pass_followed`, `first_pass_overridden`, `first_pass_absent` and
`first_pass_conflict` (`step.py`). `first_pass_given_up` is not one of these and does not change: a
label whose first pass was given up on still goes to review however its fields settle
(`step.py`, `given_up_regions`).

### Adding a reader

`image` is a judgement of the image, never a vote (section 2). So adding a reader changes a
settlement only where the image judges the unit uncertain. The design's own test, counted per unit
in every measurement (plan section 1, criterion 2): an added reader never turns a right settlement
into a wrong one, and settled-right falls only at units the image judges uncertain.

### The basis of a value

Every settled value carries its basis, in the PRD's three words (`PRD.md`, "How every value is
recorded"): `label` (as written), `derived` (from the label's own values by a rule: feet to metres),
`inferred` (a rule supplies what the label does not write: an elevation's unit). The basis is a new
optional field on each value part, as PRD v2 says; the existing `layer` (`verbatim`, `settled`,
`derived`; `domain.py`) and the app's enum for it do not change, because a new layer value would
break every reader of the layer (`PRD.md`, the same section). The reason above says how the literal
was chosen; the basis says how the value relates to the label. The literal is still text a reader
wrote; nothing is invented. A value may differ from the literal only through a lookup or an
ontology rule, both named.

### Putting units together

One field may be put together from several units when the ontology says they belong together,
within these limits. On one label: genus and species on the same label make one taxon; day, month
and year on the same label make one date. Across labels: only the place chain and the date, and
only where one label writes the whole value and another writes a part of the same value
("6-Sept-1946" on one label and "1946" on another agree; "6 Sept" on one and "1946" on another are
two parts and go to review). A taxon name is never put together across labels: two labels with
different taxon parts go to review with both. Two labels that write different values for one field
contradict each other and go to review with both, as today.

## 4. The conceptual model, as an ontology

The owner, 2026-10-26: "It's not about location at all. At specimen level there is a conceptual
model that all models need to be aware of. This is the ontological model that needs to be baked in,
so the harness can connect the dots."

The owner, same day: "It may not exist, the ontological conceptual model. Needs to be built and
baked in."

Two parts, one adopted and one built. Darwin Core publishes a conceptual model of specimen data
(dwc.tdwg.org/cm, version 2026-10-13): the things, Event, Location, Material entity, Identification,
Agent, Taxon, and the relationships and cardinalities among them. We adopt it as the frame, so our
things and fields carry names others already use. What does not exist yet is the model of THIS
collection's labels: which things each label type carries, what cannot be true together on these
labels, what may be derived or inferred and by which rule, the institution's and era's conventions.
A part of it exists in the code: the `Notation` table of `application/harness_knowledge/insects.py`
maps written forms ("P.I.", "Prov.", "leg.", "ca.", Roman months) to their readings and fields, and
the experts' brief carries the label notations (`prompts/common.txt`, "Label notations"). They are
the seed of the ontology file, not the file. That file we build, as one file in the repository,
readable by people and by code, and bake into every model in the pipeline: the readers'
instructions, the first pass, the organiser while it stays, and every field expert carry it, so
each one knows what a unit can be and what it can connect to; the rules that code can check are
checked by code. Location is only the first example of a rule. The rules are the collection's; when
the owner and its curators read them is in the plan, section 6.

### Things

| Thing | Examples on labels | Darwin Core |
|---|---|---|
| Specimen | the slide, its catalogue number, the institution that holds it | MaterialEntity; catalogNumber, institutionCode |
| Collecting event | one act of collecting: where, when, how, in what habitat | Event: eventDate, samplingProtocol, habitat; the collectors as recordedBy (listed under Occurrence) |
| Locality | the place of the event: a named site, inside a city or county, inside a province, inside a country; with an elevation | dcterms:Location: locality, municipality, county, stateProvince, country, minimumElevationInMeters |
| Agent | a collector, an identifier | Agent; recordedBy, identifiedBy |
| Determination | a taxon name given to the specimen by a person on a date | Identification: identifiedBy, dateIdentified; the name as Taxon: scientificName |
| Taxon | the name, its rank, its accepted name | Taxon |
| Code | a slide or preparation code, a species number | ours: no Darwin Core term fits them |
| Label | a physical label; it carries attributes of the things above and has a type (locality label, determination label, code label) | ours |

### Relations and what cannot be true together

- A specimen has one collecting event; the event has one locality, one date or date range, one or
  more collectors. Two labels that write different localities or dates for the same event
  contradict each other; the harness settles neither and says why.
- A locality sits inside one chain: country > province > county > city. A unit cannot settle at one
  level outside the chain settled at a higher one ("Cook County" under "Philippines"). Built in part
  today: `agreement.parents_refusal` checks a candidate against the settled country, and a county or
  city against the settled province, but checks a city against a settled county only for a near
  spelling, not for an exact match (settled Coles County, then an exact "Chicago" under Illinois,
  passes). Plan WP 2.3 completes the check at every level and for exact candidates, with a
  fail-first test for that case.
- An elevation belongs to the locality and must be possible for it. The unit rule is in section 2:
  inferred as feet only with a reader's mark and a metre reading above the settled country's
  highest point, and only when the foot reading is possible; otherwise review. The highest points
  are a static table in the ontology file, taken from Wikidata, each row with its item id and the
  date it was read. Terrain is not used while D5 is held.
- A collecting date is on or before the determination date; the same day is allowed. Dates of
  different precision compare on the parts both have ("1946" and "1946-09-06" agree; `domain.py`
  records precision as day, month or year). A date that is still ambiguous (day against month) is
  not excluded by this rule: it goes to review with both readings, as today
  (`day_month_order_ambiguous`). The institution's name dates the label: "CNHM" means 1943-1966. A
  collector's active years bound the date once a people source is approved (section 6).
- A taxon's occurrence in the settled region is not a rule. D4 (GBIF occurrence lookups) is held and
  off, and even once lifted, absence from an authority is not impossibility: a correctly identified
  specimen can be a new regional record, and the PRD names incomplete authorities as a cause of
  false no-match (`PRD.md` section 21). If D4 is lifted, an occurrence check may flag a value for the
  reviewer; it never sends a field to review by itself.
- Slide or preparation codes are never dates, nor any part of them (the standing rule; t1-329
  writes code "IV-29-68-4" beside the collecting date "IV-23-48"). The ontology says what a code is
  and which field it goes to, never a date.
- A label type routes units; it never excludes a field. A determination label's units go first to
  the taxon and identifier experts and a locality label's to the place, date and collector experts;
  a determination label that also prints the locality still feeds the locality expert, and every
  expert receives every unit in any case (section 3).
- Dependencies between fields, for round 2 (section 3): province after country; county and city
  after province; the elevation unit after country; the end date after the start date. Written in
  the file; acyclic; two rounds at most.

### Where each rule gets its knowledge

- Gazetteers, approved for places today (Getty TGN, Wikidata, NGA, GEOLocate; `contracts.py`,
  `FIELD_TOOLS`): the place chain and coordinates.
- Copernicus GLO-30 (D11): approved in the sources table for a missing elevation over the
  uncertainty circle of a georeferenced place (`golive/PLAN.md` section 4.8). No rule here uses it
  while D5 is held.
- GBIF, Catalogue of Life, Global Names: taxon names, ranks, accepted names. Occurrences by region:
  D4 is held; no rule uses them.
- People: no approved source today. A collector-name query is an owner exception (`golive/PLAN.md`
  section 4.8 and its D4 row; `GEOREFERENCING.md`, D4); a people source (Wikidata persons, then
  Bionomia if needed) is put to the owner before use, with phase 1's measurement.
- The highest point of each country: a static table in the ontology file, from Wikidata, cited per
  row.
- Institution and label conventions: a short written table in the ontology file (institution names
  and dates, unit conventions by era and country, slide-code formats), seeded from `insects.py`'s
  `Notation` table.
- The owner and the collection's curators: the rules above are theirs to confirm and extend, in one
  reading (plan section 6).

## 5. What exists today and what changes

| Piece | Today | Under this spec |
|---|---|---|
| Reader alignment | aligns readers span by span (`reading_differences_among`), outputs the differences only, drops spacing-only differences | supplies candidate breaks; the first pass cuts the units; code checks that they tile every reading |
| First pass output | one preferred reader or none, a verdict per difference, notes (`FirstPassOutput`) | the units; during phase 1 the code also derives the old preferred reader and verdicts from them, until the experts and the app read units (plan WP 1.2 and 1.8) |
| Scheduling | a first pass only for a label whose readers differ (`workflow.py`); refused below two readings (`first_pass.py`) | every label, one reading or more |
| Organiser | proposes field candidates quoted from whole readings and stores each as an evidence row with offsets (`harness.py`, `apply_candidates`) | stays through phase 1; the units' `fields` are measured against its candidates (plan WP 1.5); its future is decided in plan WP 2.5 |
| Field experts | all readings, organiser proposals, first-pass advice, lookups; one round (`experts.py`, `step.py`) | the units, the readings, the ontology, lookups; two rounds |
| What settles a field | readers agree; a source confirms; a near spelling; another label whose two or more readers agree; the preferred reader's text; a person's text (`agreement.labels`) | the order in section 3: person, source, image, near spelling, agreement, other label; else review |
| Image guard | a near spelling or another label never overrides a text the first pass confirmed in the image; the conflict goes to review (`confirmed_against_image`) | the same guard as `image_names`; a source against the image goes to review too (`image_source_conflict`) |
| Derivation | feet/metres, end date = start date, parent place from the gazetteer (`derive.py`) | the ontology's rules, each value recorded with its rule and its basis (`derived` or `inferred`) |
| Review | several possibilities, or sources cannot resolve | the same, with the units as the options |

## 6. Decisions taken by the engineer

1. `image` never names a text no reader wrote: it is one reader's text, `uncertain` or
   `not visible`. It is a judgement of the image, never a vote among readers. A reader can be added;
   the judge cannot become a reader. `means` is the judge's interpretation and is never a literal.
2. Every value carries its basis in the PRD's words, `label`, `derived` or `inferred`, as an
   optional field on each part; no new `layer` value is added, and the app's enum is untouched. A
   value a rule decides is recorded with the rule named and shown so to the reviewer. This follows
   the owner's decision of 2026-10-08 that derived and inferred values are tracked by their basis
   and reviewed per part.
3. Darwin Core's conceptual model is the frame; the collection's rules, label types and conventions
   are ours, seeded from the code's `Notation` table.
4. People lookups need a source the owner approves first; none is approved today. The ask goes to
   him with the first phase's measurement, not before.
5. One settlement order (section 3), written once and followed by the code. A source that confirms
   one reader's text against an image that names another's does not settle; the field goes to
   review with both.
6. An elevation unit the label does not write is inferred only with positive evidence: a reader's
   mark, a metre reading impossible for the settled country, a foot reading possible for it.
   Terrain is not used while D5 is held, and no owner ask on D5 is made now.
7. Experts run in two rounds; the dependency order is written in the ontology file and is acyclic.
8. Units are put together across labels only for the place chain and the date, and only where one
   label writes the whole and another a part of the same value; never for a taxon name.
9. A taxon's regional occurrence is not a rule.

## 7. Build order

The same list as the plan's section 3, one lane at a time. A gate is met or the phase stops.

Phase 0: WP 0, the reference set and its baseline.

Phase 1, the ontology's first version and the reading units: 1.0 ontology v1 (things, fields, label
types, conventions) -> 1.1 unit record, storage, projection field and app reader -> 1.2 first pass
v2 (units for every label, the tiling check, the old preferred reader and verdicts derived from the
units for the time being, the ontology v1 in its prompt) -> 1.3 experts take units (the settlement
order of the spec's section 3, `BY_IMAGE`, `BY_PERSON`, the finding codes, the ontology v1 in their
instructions) -> 1.4 organiser kept and measured -> 1.5 measurement (gate: criteria 1 and 2 met) ->
1.6 app shows the units -> 1.7 docs -> 1.8 remove the derived preferred reader and verdicts and the
unused field-harness prompt.

Phase 2, the ontology's second version: 2.1 relations and rules (the owner's and curators' one
reading) -> 2.2 the rules baked into every model's instructions, readers included -> 2.3 code-checked
rules (the complete place chain, the elevation unit, date order, label types), the two rounds, the
`basis` field with its app reader -> 2.4 units put together within the limits of the spec's section
3 -> 2.5 organiser decision -> 2.6 measurement (gate: criteria 1 to 3 met) -> 2.7 docs.

Phase 3, people and conventions: 3.1 people lookups, only if the owner approves a source -> 3.2 the
remaining knowledge tables -> 3.3 steady-state run (all four criteria met) -> 3.4 research_harness
retirement, a separate pull request.

One lane runs at a time, in this order; a phase starts when the one before it has closed. Inside a
lane, two work packages that touch different files may run in parallel sessions in their own
worktrees (1.6 and 1.7; 2.1 and nothing else, since 2.2 to 2.5 read its file).
