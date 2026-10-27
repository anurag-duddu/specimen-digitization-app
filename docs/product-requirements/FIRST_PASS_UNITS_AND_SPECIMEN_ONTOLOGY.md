# The first pass's reading units and the specimen ontology

Status: the owner's design of 2026-10-26, written from his typed words of that day and revised on
2026-10-27 after the second reviews of pull request #418. The owner set the substance. The
structure and the rules under his words are the engineer's (section 6). Nothing here is built.
Every sentence about today names the file and line that shows it (paths under
`src/specimen_digitization/` unless another root is given) or the recorded run under
`~/specimen-golive/runs/`. Section 7 is the build order; it is the same list as the plan's section
3 (`docs/execution/units/PLAN.md`).

## 1. The pipeline, in the owner's words

Each quotation is one message, copied as typed; his line breaks are kept.

> "N transcriptions per label
> Raw output
> LLM with its system prompt should have context it passes on the label about the specimen and the raw transcripts and its own final version of the transcriptions possible words numbers char whatnot 1:1
>
> Harnesses take all these run with them and do their lookups. We have specialized harnesses settling different fields."

> "The LLM is looking at words and deciding possible words. It can even say possible fields
>
> So it should be raw transcript potentially means x, r1,r2,r3. Literally an array of sorts
>
> Take an example label it has to do for each word or number or something like that not at a character level at a logical point break
>
> Bigger reason is data could be on two different labels but belong to the same field to settle like taxa
>
> Finally first pass never settles, it has to go to harness(QR is a straight pass, ignore that, I’m talking about specimens data)"

> "[LLM 1st pass, reader 1, reader 2,….n]-potential fields, repeat for each word then send to harness
>
> Yep it has to connect dots. Simple is location, it can’t be Philippines and cook county Chicago"

> "Some are derived from the data and lookups some are as written. You sometimes connect different dots and derive data because you doing it in the lookups. Derivation is not simple unit conversion. It’s essential has a concept model and understanding of how specimens work and how their data is connected and works"

> "Think ontologically for conceptual model"

On the shape of the first pass's output, three messages: "It’s not an array." Then: "I’m using and
example. It could be what best fits this structure." Then: "You decide. I’m not the engineer you
are".

## 2. The reading units

The first pass reads every label of the specimen with its image. For each label it cuts the text
at logical breaks (a word, a number, a code, a date, a phrase that belongs together) and gives one
record per unit. It settles nothing. The harness weighs its image judgement as one backing among
others (section 3).

### The shape

Decided by the engineer: a list of unit records, grouped by label and ordered by line, as JSON (a
Pydantic model `ReadingUnit`). The first pass already answers in structured JSON (`FirstPassOutput`,
`application/first_pass.py:290-301`) and the experts receive one JSON document
(`field_research/experts.py:281-327`), so the units travel in it.

The units are a new record on the run. The run's existing records refuse unknown keys (`Record`,
`application/domain.py:23-24`); the normalized projection publishes a fixed list of transcript
fields (`application/projection.py:448-464`, `AppendTranscriptionVersionV2`); the app checks the
research thread against an embedded copy of the server's schema
(`apps/specimen_digitization/lib/src/research/research_models.dart`;
`tests/research_harness/test_thread_embedded_schema.py:31-44`). So the units get their own record
type, their own Data Connect operation and projection field, and their own reader in the app,
shipped together, the data release before the runtime release (plan WP 1.1). The existing records,
the `layer` values and the app's enums do not change.

### Who cuts the units

The first pass, for every label, agreed labels included. Today it runs only for a label whose
readers' texts differ (`application/workflow.py:2068-2076`) and refuses fewer than two readings
(`first_pass.py:404`). The code's alignment (`reading_differences_among`) outputs differences only
and drops a difference of spacing alone ("Davao Prov." against "DavaoProv."); it supplies candidate
breaks and does not decide the units.

Code checks every answer:

- Tiling: every character of every reading belongs to exactly one unit, in order; only whitespace
  lies between units.
- Range: a unit never ends between two numbers or two dates joined by a range joiner (a hyphen, an
  en dash, "to", "bis", "au", "a"). A hyphen inside a name made of letters is not a range. This is
  the experts' standing rule (`field_research/prompts/common.txt:22`, "A date or an elevation is
  never one end of a range").
- An empty unit list is refused.
- An answer that fails is sent back once; the retry text names the failed check. An answer that
  fails twice is given up on, as today (`first_pass_given_up`, `first_pass.py:638-660`). A given-up
  label still gets units: code cuts them from the alignment, every unit's `image` is `uncertain`,
  and the label keeps the given-up marker, so it goes to review however its fields settle
  (`field_research/step.py:3735-3754`). Today an agreed label has no first pass and cannot be given
  up; under this spec it can, so the plan counts and bounds it (WP 1.2).

A label whose transcript a person decided has one reader, the person. The unit pass runs on that
text alone, and `image` is that text. Today a person's edit updates the transcript and resumes the
run at `parse` (`application/api.py:2176-2199`); it schedules no first pass. Under this spec the
edit also drops that label's units and runs the one-reader unit pass before `parse`; a second edit
does it again. A person's abstention (null text, `api.py:2168-2169`) keeps the machine units and
sets every unit's `image` to `uncertain`, so nothing on that label clears on agreement alone.

### What each unit holds

| Key | What it holds |
|---|---|
| `id` | `<label>:<n>`, n counting from 1 in reading order |
| `label`, `lines` | the label, and the first and last line the unit covers; a unit may cross a line ("E Slope Mt. / McKinley") |
| `readers` | for each reader, the text it wrote here and where: `{"A": {"text": "Elev.6400", "start": 60, "end": 69}, ...}`; `start` and `end` are Python string indices into that reader's text (code points); the app converts them to UTF-16 before slicing (`apps/specimen_digitization/lib/src/reading_alignment.dart:11-27`); a reader that wrote nothing here has `""` |
| `image` | what the first pass sees in the image at this unit: one reader's text, `uncertain`, or `not visible`. It is a judgement of the image, never a vote among readers: when the image is clear it names the text that matches it, even if one reader alone wrote it; `uncertain` only when the image itself is unclear here. Never a text no reader wrote |
| `means` | the first pass's own interpretation, which may be text no reader wrote: an expansion ("P.I." -> "Philippine Islands"), a normal form ("6-Sept-1946" -> 1946-09-06), a role ("leg." -> collected by). May be empty. Never a literal |
| `fields` | the fields this unit could belong to, most likely first. Advice only: every expert receives every unit (section 3). May be empty |
| `note` | one short sentence when something matters (a mark only one reader saw) |

The units go to the harness together with the raw readings, which stay available whole.

### The same label today and under this spec

Readings of pilot label e98a924c-L2 (a 1946 Field Museum slide label from the Philippines; slide
105526322 of `tests/fixtures/field_model_pilot_rows.json`):

- A: `CNHM. E Slope Mt. / McKinley, Davao Prov. / Mindanao, P.I. / 6-Sept-1946, Elev.6400 / H. Hoogstraal leg. / Shrubs, mostly forest / wings 4 head / Sp.30 ♀`
- B: the same with `Elev.6400'`, `Forest`, `Wings`, and an extra line `P-95-81-16`
- C: the same with `DavaoProv.`, `Mostly forst`, `Wings & head`, `♂`, no extra line

What the first pass answered on this label with three readers, over 12 recorded runs
(`three-readers-20261025/fp_three_reps*.jsonl`): preferred reader none in 9, A in 3. The foot mark:
"A, no mark in the image" in 7, `uncertain` in 4, `neither` in 1. The extra line `P-95-81-16`:
`uncertain` in 7, A in 3, `neither` in 2. `4` not `&`, `♀` not `♂` and `forest` not `forst`: 12 of
12. So on the two marks that matter, the one image judgement the harness gets changes from run to
run.

What the harness then did, per arm and repeat (`free-harness-20261025/results/<repeat>/<arm>.jsonl`;
the code reason replayed with this tree's `agreement.labels` and `agreement.refusal` on the
recorded organiser candidates):

- Two readers, repeats 1 and 2: country, province, locality, elevation, collector and date all
  `resolved`. The elevation: the organiser gave "6400" for 1A and 1B; the expert named 1B only;
  `labels()` settles the label on "6400" with basis `readers_agree` (every reader writes the
  number) and `refusal()` is None. The foot mark comes from the named reading alone:
  `_unit_refusal` reads the named readings (`field_research/agreement.py:789-826`); naming 1A and 1B
  gives `NO_UNIT` instead. The elevation check is no source: `SOURCE_IDS` holds the gazetteers and
  GBIF (`agreement.py:247`), and `elevation_from_ft`'s only tool is `elevation_parser`
  (`field_research/contracts.py:44`). So the pair arm settled feet because the expert chose to name
  the one reader that wrote the mark. The strict scorer reads the country from its parsed value, so
  "P.I." counts wrong there and right under the lenient rule (`score_full.md`).
- Three readers, repeat 1: the country's research ran out of time (`field_research_timeout:country`;
  the rig does not retry). The province expert resolved "Davao Prov." (Wikidata Q15095071), but the
  field stayed unresolved: no country was settled. Locality: `sources_cannot_resolve`. Elevation:
  `several_possibilities` with both texts. The organiser had filed 1A's and 1C's "6400" under
  `elevation_from_m` and only 1B's under `elevation_from_ft`; replayed with the answer naming 1B,
  the label does not settle (1A and 1C unread: "The readings differ, and no approved source confirms
  one of them."). Collector `resolved` as "H. Hoogstraal leg." (scored wrong: the marker is in the
  literal); date `resolved`.
- Three readers, repeat 2: country `sources_cannot_resolve`; province resolved, the field
  unresolved for want of a country; locality `several_possibilities` (1C's "DavaoProv.");
  elevation `sources_cannot_resolve`, literal "6400", 1A, 1B and 1C named, "a unit is never guessed
  from magnitude or place". Replayed, the label settles on "6400" by `readers_agree` and `refusal()`
  is `NO_UNIT`; naming 1B alone would have settled it. Collector and date as in repeat 1.
- Getty TGN answered `provider_error` in every run of this label (6 or 7 lookups each) and NGA timed
  out in repeat 1 (6 lookups each); Wikidata answered, so the pair arm still settled its places
  (`score_full.md`, degraded lookups).

Under this spec the first pass gives, among others (fields are the profile's; where today's
experts put a unit is noted):

| unit | readers | image | means | fields |
|---|---|---|---|---|
| CNHM. | A, B, C same | CNHM. | Chicago Natural History Museum, the Field Museum's name 1943-1966 | collection_code today (4 of 5 runs); the ontology's rule says whether an institution name is a code (WP 1.0) |
| E Slope Mt. McKinley (lines 1-2) | A, B, C same | same | east slope of Mount McKinley, a locality | precise_location |
| Mindanao | same | same | the island | context for precise_location; no field of its own |
| P.I. | same | same | Philippine Islands | country |
| 6-Sept-1946 | same | same | 1946-09-06 | date_visited_from |
| Elev.6400 / Elev.6400' | A "Elev.6400", B "Elev.6400'", C "Elev.6400" | "Elev.6400" or uncertain (the 12 recorded runs judged the mark absent in 7 and uncertain in 4) | elevation 6400, unit not certain from the image | elevation_from_ft |
| H. Hoogstraal leg. | same | same | collected by H. Hoogstraal | collectors |
| Shrubs, mostly forest | A "forest", B "Forest", C "forst" | forest | habitat note | habitat |
| wings 4 head / Wings & head | A, B "4", C "&" | 4 | a preparation note | none: `verbatim_dts` holds non-standard collecting-event date and time expressions (`PRD.md` section 22, question 3, the answer of 2026-10-07); the brief's sentence calling the field's meaning open (`field_research/prompts/verbatim_dts.txt:1,3`) is stale and is corrected in plan WP 1.7 |
| Sp.30 ♀ / ♂ | A, B "♀", C "♂" | ♀ | species number 30, female | taxon today (5 of 5 runs); the ontology's rule says where a species number and a sex go (WP 1.0) |
| P-95-81-16 | B only | uncertain | a code | collection_code, doubtful; the ontology's rule says what it is (WP 1.0) |

What the settlement rule (section 3) and the unit rule (below) do with it:

- Elevation. Two candidates at the unit: "Elev.6400" (1A, 1C) and "Elev.6400'" (1B). "Elev.6400"
  has two backings in the 7 recorded judgements that name it (two readers wrote it; the image names
  it) and one in the other 5 (the image uncertain or "neither"). "Elev.6400'" has none. One
  candidate backed: it settles on the number, 6400, cleared with the image and marked without it.
  The text writes no unit. The unit rule infers feet: B wrote the mark, 6,400 m is above the
  Philippines' highest point, 6,400 ft (1,951 m) is possible. An inferred unit is always marked for
  a person. So both arms give 6,400 ft, basis `inferred`, marked, instead of today's pair-arm clear
  and three-reader review. A misread such as "640.0 m" written as "6400" reaches the person the same
  way.
- Country. One candidate, "P.I."; backings: three readers, the image, and Wikidata (Q928 for the
  expansion "Philippine Islands"): cleared, value Philippines, literal "P.I.". Province, at the
  next level: "Davao Prov." and "DavaoProv." are one text (`agreement_key`, `agreement.py:1200-1206`
  ignores spacing); Wikidata confirms Davao: cleared. Locality: "E Slope Mt. McKinley", every reader
  and the image: cleared as written; no gazetteer holds it.
- Collector. "H. Hoogstraal leg.", every reader and the image: cleared. The unit's `means` and the
  ontology's notation ("leg." marks the collector) give the value H. Hoogstraal; the literal stays
  as written (`PRD.md:671`, "The original wording is always kept next to every interpreted value").

### The elevation unit: one ontology rule

A unit the cleared text does not write is inferred as feet only when all three hold:

- (a) at least one reader wrote the foot mark or "ft" at this unit;
- (b) the number read as metres is impossible for the settled country: above its highest point (for
  the Philippines, Mount Apo, 2,954 m, from the table in the ontology file);
- (c) the number read as feet is possible for it.

The country used must itself be cleared, not marked. The value is recorded with basis `inferred`
and the rule named, and it is always marked for a person: an inferred value is never cleared
(`PRD.md:668-670`). Without (a) the field is unresolved: magnitude alone never decides, so an
"Elev.16000" that no reader wrote a mark for is unresolved, and so is a number impossible in both
units (16,000 ft is 4,877 m, also above 2,954 m). Where the cleared text writes the unit, nothing is
inferred and the value's basis is `label`.

Today a unit is never guessed (`GEOREFERENCING.md` section 3, Parse row; `agreement.py:302`,
`NO_UNIT`; `:822-825`, "A unit is never guessed from the magnitude, the place or a map"), and the
pair arm settled feet from one reader's mark when the expert named that reader alone (above). The
rule extends that: it names the evidence a mark needs, and it marks the result. It takes effect
only after the owner and the curators have read it, with the other rules, in plan WP 2.1. Terrain
takes no part: Copernicus GLO-30 (D11) is approved for a missing elevation over a georeferenced
place (`golive/PLAN.md` section 4.8), and D5 is held, so a terrain check records its measurement
and changes no outcome (`GEOREFERENCING.md` section 3, Measurements row). No owner ask is made on D5
now. No gazetteer holds this Mount McKinley (`GEOREFERENCING.md`, the Mount Talomo crosswalk).

## 3. The harness

The field experts stay as they are in shape: one per field, with lookups. Two exceptions exist
today and stay: `identified_by_irn` gets no model call (`step.py:426-430`, `NO_APPROVED_AUTHORITY`),
and five fields have no lookup at all (collectors, collection code, habitat, collection method,
verbatim D/T/S: `contracts.py:47-51`), so they clear on the image, on readers that agree or on
another label, never on a source. What changes is what the experts receive, in what order they
run, and what settles a field.

### What an expert receives

- Every reading unit of every label (`id`, `lines`, `readers`, `image`, `means`, `fields`).
  `fields` is advice: an expert reads every unit, as today every expert reads every reading
  (`experts.py:281-327`), and may recover a field the organiser missed (`common.txt:22`).
- Every raw reading, whole, as today.
- The ontology (section 4), rendered into its instructions.
- Every value cleared at an earlier level (below).

### Levels

Today every expert runs at once, with one copy of the other fields taken before any expert answers
(`step.py:333-339`, `:437-439`). Under this spec the experts run in levels, in the dependency order
the ontology file writes: level 1, every field with no dependency; then the province (needs the
country), the elevation unit (needs the country), and the end date and the determination date (need
the start date); then the county (needs the province); then the city (needs the county). Four levels
at most. Each field still runs once, so the cost is today's; the latency grows with the levels. A
level's context holds every value settled at earlier levels, and a parent never changes after its
level. The run records the last completed level; a retry resumes at the next one. The order is
acyclic; a cycle fails the loader (a test).

### What settles a field: one rule

The rule follows PRD v2 (`PRD.md:667-670`): "A value is `unresolved` only when nothing supports
even an inference"; "On a conflict or a doubt, the harness fills in the best-supported value and
marks that part for a person"; and its risk row (`:1204`), "never clear on agreement alone". It is
written here once and the code follows it.

For each field, on each label that writes it:

1. The candidates are the texts the readers wrote at the unit. Texts a source confirms as one
   authority (the same place: "Yepocapa," and "Yepocapa", today `BY_SAME_PLACE`,
   `agreement.py:1530-1533`) are one candidate.
2. A candidate's backings: a person decided the label's transcript (binding: that text settles,
   unmarked, and the rule ends; today `BY_FIRST_PASS` with `person_decided`, `:1401-1408`); a
   source confirms it exactly, by its own name or expansion, and rules the others out (today
   `BY_SOURCE`); the image names it (new); it is a near spelling of a source's one candidate (today
   `BY_NEAR_SPELLING`); two or more readers of this label wrote it (today `BY_AGREEMENT`); another
   label of the specimen, read by two or more readers who agree, writes it (today `BY_OTHER_LABEL`,
   `MIN_BACKING_READERS = 2`, `:1228`).
3. Exactly one candidate has backing: it settles. It is cleared when it has two independent
   backings, or one backing that is a source or the image. With readers' agreement alone, or
   another label alone, it settles but is marked for a person (A and B both wrote "P-93", the
   image is uncertain).
4. Two or more candidates have backing: a conflict. The field takes the best-backed candidate
   (rank: source, image, same place or near spelling, readers agree, another label) and is marked
   for a person, with the others listed. Today a conflict settles nothing (`Label(texts,
   preference=CONFLICT)`, `:1526` and `:1547`; `several_possibilities`, `:1611-1618`).
5. No candidate has backing: an ontology rule may infer one (marked for a person, basis
   `inferred`); otherwise the field is unresolved, with the candidates as options.

In phase 1, "marked for a person" is today's `ambiguous` state with the options, best first; PRD
v2's per-part marks come with the four-group schema, not here. A cleared value records its backings
by name; a marked value records why: one backing, inferred, or conflict.

What the rule gives: for a given set of image judgements, adding a reader can add a candidate or a
conflict, so it can turn a cleared value into a marked one, but never into a different cleared
value. A changed value always comes from a conflict, and a conflict is always marked. The judge's
own run-to-run stability is a separate measured number with its own gate (plan, criterion 2 and WP
1.5).

The finding codes `first_pass_followed`, `first_pass_overridden`, `first_pass_absent` and
`first_pass_conflict` (`step.py:2385-2460`) are replaced by `cleared:<field>:<label>` and
`marked:<field>:<label>:<why>`. `first_pass_given_up` stays (section 2).

### The basis of a value

Every settled value carries its basis, in the PRD's three words (`PRD.md:612-622`): `label` (as
written), `derived` (from the label's own values by a rule or a lookup: feet to metres), `inferred`
("a reasoned conclusion that is probable but not certain", `:622`). Phase 1 records the basis on
the field, with the rule named in its reason; the per-part basis waits for PRD v2's schema. The
existing `layer` (`verbatim`, `settled`, `derived`; `domain.py:288`) and the app's enum for it do
not change. The literal is still text a reader wrote. A value may differ from its literal only
through a lookup or a named ontology rule.

### Putting units together: parts

One field may be put together from several units, on one label or across labels. The owner: "data
could be on two different labels but belong to the same field to settle like taxa". The expert's
answer gains `parts`: each part has a role, a literal and the readings that write it, and each part
is checked exactly as today's one literal is (`experts.py:523-531`: copied character for character
from every named reading). The value is composed by the ontology's rule for the field: a taxon from
genus + species [+ author]; a date from day + month + year; the place chain from its levels. Which
parts may combine is the ontology's rule: one determination's parts come from one determination
label or from the same label; two candidates for one role (two genera) are a conflict under rule 4.
Today the answer holds one literal (`contracts.py:229-232`), and only `precise_location` may cross
lines (`ACROSS_LINES`, `agreement.py:490`).

## 4. The conceptual model, as an ontology

The owner, 2026-10-26, three messages: "It’s not about location at all specimen level there is a
conceptual model that all models need to be aware of". "This is the ontological model that needs to
be baked in. So harness can connect the dots". "It may not exist the ontological conceptual model.
Needs to be built and baked in".

Two parts, one adopted and one built. Darwin Core publishes a conceptual model of specimen data
(dwc.tdwg.org/cm, version 2026-10-13): the things, Event, Location, Material entity,
Identification, Agent, Taxon, and the relationships among them. We adopt it as the frame, so our
things and fields carry names others already use. What does not exist is the model of THIS
collection's labels: which things each label type carries, what cannot be true together, what may
be derived or inferred and by which rule, the institution's and era's conventions. A seed exists in
the code: the `Notation` table of `application/harness_knowledge/insects.py:27-89` maps written
forms ("P.I.", "Prov.", "leg.", "ca.", Roman months) to their readings and fields, and the experts'
brief carries the label notations (`common.txt`, "Label notations"). The table has no production
caller today: `instructions_for` and `PLACE_ALIASES` are read by `tests/test_harness_knowledge.py`
only. It is the seed of the ontology file, not the file. That file we build, as one file in the
repository, readable by people and by code, and bake into every model in the pipeline: the readers'
instructions, the first pass, the organiser while it stays, and every field expert. The rules that
code can check are checked by code. Location is only the first example of a rule. The rules are the
collection's; the owner and its curators read them once, in plan WP 2.1.

### Things

| Thing | Examples on labels | Darwin Core |
|---|---|---|
| Specimen | the slide, its catalogue number, the institution that holds it | MaterialEntity; catalogNumber, institutionCode |
| Collecting event | one act of collecting: where, when, how, in what habitat | Event: eventDate, samplingProtocol, habitat; the collectors as recordedBy |
| Locality | the place of the event: a named site, inside a city or county, inside a province, inside a country; with an elevation | dcterms:Location: locality, municipality, county, stateProvince, country, minimumElevationInMeters |
| Agent | a collector, an identifier | Agent; recordedBy, identifiedBy |
| Determination | a taxon name given to the specimen by a person on a date | Identification: identifiedBy, dateIdentified; the name as Taxon: scientificName |
| Taxon | the name, its rank, its accepted name | Taxon |
| Code | a slide or preparation code, a species number | ours: no Darwin Core term fits them |
| Label | a physical label; it carries attributes of the things above and has a type (locality label, determination label, code label) | ours |

### Relations and what cannot be true together

- A specimen has one collecting event; the event has one locality, one date or date range, one or
  more collectors. Two labels that write different localities or dates for the same event are a
  conflict (section 3, rule 4): the best-backed value, marked, with the other listed.
- A locality sits inside one chain: country > province > county > city. A unit cannot settle at
  one level outside the chain settled at a higher one ("Cook County" under "Philippines"). Built in
  part today: `agreement.parents_refusal` (`agreement.py:2030-2096`) checks a candidate against the
  settled country, and a county or city against the settled province, but checks a city against a
  settled county only for a near spelling, not for an exact match (settled Coles County, then an
  exact "Chicago" under Illinois, passes). Plan WP 2.3 completes the check at every level and for
  exact candidates, with a fail-first test for that case.
- An elevation belongs to the locality and must be possible for it. The unit rule is in section 2.
  The highest points are a static table in the ontology file, taken from Wikidata, each row with
  its item id and the date it was read. Terrain is not used while D5 is held.
- A collecting date is on or before the determination date; the same day is allowed. Dates of
  different precision compare on the parts both have ("1946" and "1946-09-06" agree; `domain.py:293`
  records precision as day, month or year). A date still ambiguous between day and month is not
  excluded by this rule: it is a conflict with both readings, as today's `day_month_order_ambiguous`
  sends it to review. The institution's name dates the label: "CNHM" means 1943-1966. A collector's
  active years bound the date once a people source is approved (section 6).
- A taxon's occurrence in the settled region is not a rule. D4 (GBIF occurrence lookups) is held
  and off, and even once lifted, absence from an authority is not impossibility: a correctly
  identified specimen can be a new regional record, and the PRD names incomplete authorities as a
  cause of false no-match (`PRD.md:1207`). If D4 is lifted, an occurrence check may mark a value for
  the reviewer; it never unsettles a field by itself.
- Slide or preparation codes are never dates, nor any part of them (the standing rule; t1-329
  writes code "IV-29-68-4" beside the collecting date "IV-23-48"). The ontology says what a code is
  and which field it goes to. Whether "CNHM." is a code, where "Sp.30 ♀" goes and what "P-95-81-16"
  is are rules WP 1.0 writes; the seed table does not say.
- A label type routes units; it never excludes a field. A determination label's units go first to
  the taxon and identifier experts and a locality label's to the place, date and collector experts;
  a determination label that also prints the locality still feeds the locality expert, and every
  expert receives every unit in any case (section 3).
- Dependencies between fields, for the levels (section 3): province after country; elevation unit
  after country; end date and determination date after start date; county after province; city
  after county. Written in the file; acyclic; four levels at most.

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
  `Notation` table and `common.txt`'s label notations.
- The owner and the collection's curators: the rules above are theirs to confirm and extend, in one
  reading (plan section 6).

## 5. What exists today and what changes

| Piece | Today | Under this spec |
|---|---|---|
| Reader alignment | aligns readers span by span (`reading_differences_among`), outputs the differences only, drops spacing-only differences | supplies candidate breaks; the first pass cuts the units; code checks that they tile every reading |
| First pass output | one preferred reader or none, a verdict per difference, notes (`FirstPassOutput`, `first_pass.py:290-301`) | the units, behind the switch `SPECIMEN_FIRST_PASS_UNITS` (off by default) and a new prompt variable; with the switch off nothing changes; with it on the pinned `FirstPassDecision` names no reading and its differences carry verdict `uncertain` (today's path for an answer that never came, `first_pass.py:487-490`); the old path, prompt and switch are deleted in plan WP 1.8 |
| Transport | the first pass runs in a child process that returns `{"decision": ...}`; the parent validates `FirstPassDecision` (`application/model_runtime.py:90-99`, `:276-284`) | the child returns `{"decision": ..., "units": ...}`; the parent validates `ReadingUnits` and stores them on the run; `FirstPassDecision` is untouched |
| Scheduling | a first pass only for a label whose readers differ (`workflow.py:2068-2076`); refused below two readings (`first_pass.py:404`) | every label, one reading or more, when the switch is on |
| A person's edit | updates the transcript and resumes at `parse` (`api.py:2176-2199`); no first pass | drops the label's units and runs the one-reader unit pass before `parse`; an abstention keeps the machine units with `image` uncertain |
| Organiser | proposes field candidates quoted from whole readings and stores each as an evidence row with offsets (`application/harness.py:123-166`, `apply_candidates`) | stays through phase 1; the units' `fields` are measured against its candidates (plan WP 1.5); its future is decided in plan WP 2.5 |
| Field experts | all readings, organiser proposals, first-pass advice, lookups; one round (`experts.py`, `step.py:333-339`) | the units, the readings, the ontology, lookups; levels |
| What settles a field | readers agree; a source confirms; a near spelling; readers one source confirms as one place; another label whose two or more readers agree; the preferred reader's text; a person's text (`agreement.labels`, `:1366-1557`) | the rule in section 3: candidates, backings, cleared or marked; a conflict gives the best-backed value, marked |
| The image guard | a near spelling or another label never overrides a text the first pass confirmed in the image; the conflict settles nothing and goes to review (`confirmed_against_image`, `:1303`; `CONFLICT`, `:1526`, `:1547`) | the image is one backing; two backed candidates are a conflict: the best-backed value, marked, the others listed (rule 4) |
| Assembly | one literal per answer (`contracts.py:229-232`); `precise_location` alone across lines (`ACROSS_LINES`, `agreement.py:490`) | `parts`, each checked like the literal; composed by the ontology's rule (section 3) |
| Derivation | feet/metres, end date = start date, parent place from the gazetteer (`field_research/derive.py:68-91`) | the ontology's rules, each value recorded with its rule and its basis (`derived` or `inferred`); an inferred value is always marked |
| Review | several possibilities, or sources cannot resolve | marked (best value first, the others listed) or unresolved (the candidates as options) |

## 6. Decisions taken by the engineer

1. `image` never names a text no reader wrote: it is one reader's text, `uncertain` or
   `not visible`. It is a judgement of the image, never a vote among readers. `means` is the
   judge's interpretation and is never a literal.
2. Every value carries its basis in the PRD's words, `label`, `derived` or `inferred`; in phase 1
   on the field, later per part; no new `layer` value; the app's enum untouched. A value a rule
   decides is recorded with the rule named and shown so to the reviewer (the owner's decision of
   2026-10-08: derived and inferred values are tracked by their basis and reviewed per part).
3. Darwin Core's conceptual model is the frame; the collection's rules, label types and conventions
   are ours, seeded from the code's `Notation` table.
4. People lookups need a source the owner approves first; none is approved today. The ask goes to
   him with the first phase's measurement, not before.
5. One settlement rule (section 3), written once and followed by the code. A conflict gives the
   best-backed value and a mark, never a silent clear and never an empty field.
6. An elevation unit the cleared text does not write is inferred only with a reader's mark, a metre
   reading impossible for the cleared country and a foot reading possible for it; it is always
   marked; it takes effect after the owner's reading in WP 2.1. Terrain is not used while D5 is
   held, and no owner ask on D5 is made now.
7. Experts run in levels, in the dependency order the ontology file writes; each field runs once.
8. Units are put together through parts, on one label or across labels, by the ontology's rule for
   the field; two candidates for one role are a conflict.
9. A taxon's regional occurrence is not a rule.
10. The units path ships behind `SPECIMEN_FIRST_PASS_UNITS`, off by default, with its own prompt
    variable; a run keeps the prompt and path it started with; the old path is deleted only after
    the phase-1 gate and the production switch-on.
11. Codex gpt-6.1-sol reviews every work package as the adversarial reviewer. That is the
    engineer's choice; the owner said "Use codex as needed for adversarial reviews and checks if
    needed. They have sol 6.1".

## 7. Build order

One list, in the spec's section 7 and the plan's section 3, one lane at a time. A gate is met or the
phase stops.

Phase 0: WP 0, the reference set, its truth, the scorer and the baseline.

Phase 1, the ontology's first version and the reading units: 1.0 ontology v1 (things, fields, label
types, conventions, the code rules for the pilot's units) -> 1.1 unit record, storage, Data Connect
operation, projection field and app reader (data release before runtime) -> 1.2 first pass v2
behind `SPECIMEN_FIRST_PASS_UNITS` (units for every label, the tiling and range checks, the new
prompt variable, the transport, the ontology v1 in its prompt) -> 1.3 experts take units when the
switch is on (the settlement rule of the spec's section 3, given-up labels, a person's edits, the
ontology v1 in their instructions) -> 1.4 organiser kept and measured -> 1.5 measurement (gate:
criteria 1 and 2 met) -> 1.6 app shows the units -> 1.7 docs -> 1.8 switch on in production, then
delete the old first pass, its prompt variable, the switch, the unused field-harness prompt and the
dead `harness_knowledge` module.

Phase 2, the ontology's second version: 2.1 relations and rules (the owner's and curators' one
reading) -> 2.2 the rules baked into every model's instructions, readers included -> 2.3 code-checked
rules (the complete place chain, the elevation unit, date order, label types), the levels, the
`basis` field with its app reader -> 2.4 parts -> 2.5 organiser decision -> 2.6 measurement (gate:
criteria 1 to 3 met) -> 2.7 docs.

Phase 3, people and conventions: 3.1 people lookups, only if the owner approves a source -> 3.2 the
remaining knowledge tables -> 3.3 steady-state run (all four criteria met).

One lane runs at a time, in this order; a phase starts when the one before it has closed. Inside a
lane, two work packages that touch different files may run in parallel sessions in their own
worktrees (1.6 and 1.7; 2.1 and nothing else, since 2.2 to 2.5 read its file). The
`research_harness` package is out of this program's scope: it is kept as is, and a separate cleanup
program takes its inventory (the plan's section 5).
