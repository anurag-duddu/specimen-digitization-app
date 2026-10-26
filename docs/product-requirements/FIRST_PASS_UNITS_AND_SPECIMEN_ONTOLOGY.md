# The first pass's reading units and the specimen ontology

Status: the owner's design, 2026-10-26, written from his words of 2026-10-25 and 2026-10-26. The
owner set the substance; the structure is the engineer's decision (section 2). Nothing here is
built. Sections 2 to 5 say what exists today and what changes; sections 6 and 7 are decisions and
order.

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
logical breaks (a word, a number, a code, a date, a phrase that belongs together) and gives, for each
unit, one record.

Structure, decided by the engineer: a list of unit records, grouped by label and ordered by line, as
JSON (a Pydantic model `ReadingUnit`). Reasons: the first pass already answers in structured JSON;
the run record stores JSON, so the units are kept with the run and shown in the app as they are;
the experts receive JSON, so each expert takes the units whose `fields` name its field.

Who cuts the units: the first pass does, for every label, including labels whose readers agree.
Today the first pass runs only for labels whose readers differ, so this is one more call per
agreed label; the cost is measured before the change is accepted. The code's alignment
(`reading_differences_among`) does not decide the units: it supplies candidate breaks and the check
that every unit's reader texts are exact substrings of the readings at consistent positions. Today
that alignment drops differences of spacing only ("Davao Prov." against "DavaoProv.") and has no
units for agreed text; both are covered by the new check. A label whose transcript a person
decided has one reader, the person, and `image` is that text. Each unit holds:

| Key | What it holds |
|---|---|
| `label`, `line` | Which label and which line of it |
| `readers` | What each reader wrote for this unit: `{"A": "...", "B": "...", "C": "..."}`; empty when a reader wrote nothing here |
| `image` | What the first pass sees in the image for this unit: one of the readers' texts, or `uncertain`, or `not visible`. Never a text no reader wrote |
| `means` | The first pass's own interpretation of the unit, which may be text no reader wrote: an expansion ("P.I." -> "Philippine Islands"), a normal form ("6-Sept-1946" -> 1946-09-06), a role ("leg." -> collected by). May be empty. Never a literal |
| `fields` | The fields this unit could belong to, most likely first. May be empty |
| `note` | One short sentence when something matters (a mark only one reader saw) |

The first pass never settles anything. It lists. The units go to the harness together with the
raw readings, which stay available whole.

### The same label today and under this spec

Readings of pilot label e98a924c-L2 (a 1946 Field Museum slide label from the Philippines):

- A: `CNHM. E Slope Mt. / McKinley, Davao Prov. / Mindanao, P.I. / 6-Sept-1946, Elev.6400 / H. Hoogstraal leg. / Shrubs, mostly forest / wings 4 head / Sp.30 ♀`
- B: the same with `Elev.6400'`, `Forest`, `Wings`, and an extra line `P-95-81-16`
- C: the same with `DavaoProv.`, `Mostly forst`, `Wings & head`, `♂`, no extra line

Today the first pass answers: preferred reader none (no reader is right everywhere); verdicts: the
foot mark `uncertain` (it changes between runs), `4` not `&`, `♀` not `♂`, `forest` not `forst`,
`P-95-81-16` not visible. The harness then settles country, province, locality, collector and date,
and sends the elevation to review (unit unknown), because no rule lets it use the verdicts.

Under this spec the first pass gives, among others:

| unit | readers | image | means | fields |
|---|---|---|---|---|
| CNHM. | A, B, C same | CNHM. | Chicago Natural History Museum (the Field Museum, 1943-1966) | institution |
| E Slope Mt. McKinley | A, B, C same | same | east slope of Mount McKinley, a locality | precise_location |
| Davao Prov. / DavaoProv. | A "Davao Prov.", B "Davao Prov.", C "DavaoProv." | Davao Prov. | Davao Province | province_state |
| Mindanao | same | same | the island | precise_location (context), not a field of its own |
| P.I. | same | same | Philippine Islands | country |
| 6-Sept-1946 | same | same | 1946-09-06 | date_visited_from |
| Elev.6400 / Elev.6400' | A "Elev.6400", B "Elev.6400'", C "Elev.6400" | uncertain (the foot mark) | elevation 6400, unit not certain from the image | elevation_from_ft |
| H. Hoogstraal leg. | same | same | collected by H. Hoogstraal | collectors |
| Shrubs, mostly forest | A, B "forest", C "forst" | forest | habitat note | habitat |
| wings 4 head / Wings & head | A, B "4", C "&" | 4 | preparation note | verbatim_dts |
| Sp.30 ♀ / ♂ | A, B "♀", C "♂" | ♀ | species number 30, female | collection_code, sex |
| P-95-81-16 | B only | not visible | a code | collection_code (doubtful) |

The harness then settles the elevation: the ontology says a 1946 CNHM Philippine label writes
elevation in feet, Mount McKinley's slopes reach 6,400 ft and not 6,400 m, and one reader saw the
foot mark; so 6,400 ft, recorded as derived with that reason. Today that field goes to review.

## 3. The harness

The field experts stay as they are in shape: one per field, with lookups, running in parallel.
What changes is what they receive and what may settle a field.

- Input: the reading units (those whose `fields` include this expert's field, from every label),
  the whole raw readings, the ontology (section 4), and the other fields as they settle.
- A field may settle on a unit whose `image` names a reader's text, or that a lookup confirms, or that
  the ontology makes the only consistent reading. The basis is recorded on the value, as now
  (as written, matched by a source, derived with the reason).
- One field may be assembled from units on different labels when the ontology says they belong
  together: a genus on one label and a species on another, a day on one and a year on another.
- The literal is still text a reader wrote; nothing is invented. A value may differ from the
  literal only through a lookup or an ontology rule, both named. A value a rule decides where the
  label writes none (an elevation's unit) is inferred, the term PRD v2 uses beside derived; the
  code has no inferred layer today and gains one.
- When the units and the lookups leave two readings standing, the field goes to review with both,
  as now.
- Unanimity of readers is no longer required for anything.

## 4. The conceptual model, as an ontology

The owner, 2026-10-26: "It's not about location at all. At specimen level there is a conceptual
model that all models need to be aware of. This is the ontological model that needs to be baked in,
so the harness can connect the dots."

The owner, same day: "It may not exist, the ontological conceptual model. Needs to be built and
baked in."

Two parts, one adopted and one built. Darwin Core publishes a conceptual model of specimen data
(dwc.tdwg.org/cm, version 2026-10-13): the things, Event, Location, Material entity, Identification,
Agent, Taxon, and the relationships and cardinalities among them. We adopt it as the frame, so our
things and fields carry names others already use. What exists nowhere is the model of THIS
collection's labels: which things each label type carries, what cannot be true together on these
labels, what may be derived or inferred and by which rule, the institution's and era's conventions.
That part we build, as one file in the repository, readable by people and by code, and bake into
every model in the pipeline: the readers' instructions, the first pass, the organiser if it stays,
and every field expert carry it, so each one knows what a unit can be and what it can connect to;
the rules that code can check are checked by code. Location is only the first example of a rule.
The rules are the collection's, written with its curators.

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
  more collectors. Two labels that write different localities or dates for the same event contradict
  each other; the harness does not settle either and says why.
- A locality sits inside one chain: country > province > county > city. A unit cannot settle at one
  level outside the chain settled at a higher one ("Cook County" under "Philippines"). Built today for
  places (`agreement.parents_refusal`); the spec keeps it and names it as the first instance of the
  rule.
- An elevation belongs to the locality and must be possible for it: an elevation above the settled
  country's highest point in metres can only be feet; a terrain source (Copernicus GLO-30, D11, the
  approved elevation source) bounds it where the place is georeferenced. The value is inferred, by
  the named rule.
- A collecting date lies before the determination date. The institution's name dates the label:
  "CNHM" means 1943-1966. A collector's active years bound the date once a people source is
  approved (section 6).
- A determination names a taxon that occurs in the settled region: only if the owner lifts the hold
  on GBIF occurrence lookups (D4, held and off today).
- Slide or preparation codes are never dates, nor any part of them (the standing rule; t1-329
  writes code "IV-29-68-4" beside the collecting date "IV-23-48"). The ontology says what a code is
  and which field it goes to, never a date.
- A field that lives on a label type does not live on another: a determination label carries the
  taxon and the identifier, not the locality; the harness uses the label type to place units.

### Where each rule gets its knowledge

- Gazetteers, approved for places today (Getty TGN, Wikidata, NGA, GEOLocate): the place chain and
  coordinates.
- Copernicus GLO-30 (D11): terrain elevation for a georeferenced place.
- GBIF, Catalogue of Life, Global Names: taxon names, ranks, accepted names. Occurrences by region
  only if D4 is lifted.
- People: no approved source today. A collector-name query is an owner exception (`PLAN.md`
  section 4.8, `GEOREFERENCING.md`); a people source (Wikidata persons, then Bionomia if needed) is
  put to the owner before use.
- Institution and label conventions: a short written table in the ontology file (institution names
  and dates, unit conventions by era and country, slide-code formats).
- The owner and the collection's curators: the rules above are theirs to confirm and extend.

## 5. What exists today and what changes

| Piece | Today | Under this spec |
|---|---|---|
| Reader alignment | the code already aligns readers span by span (`reading_differences_among`) but outputs only the differences | the alignment becomes the units |
| First pass output | one preferred reader or none, a verdict per difference, notes | the reading units; no preferred reader |
| Organiser | proposes field candidates from whole readings | folded into the units' `fields`; may stay as a check |
| Field experts | all readings, organiser proposals, first-pass advice, lookups | the units, the readings, the ontology, lookups |
| What may settle a field | all readers agree; a source confirms; another label agrees; the preferred reader's text | image names a reader's text; a source confirms; the ontology makes one reading the only consistent one; assembled across labels |
| Derivation | feet/metres, end date = start date, parent place from the gazetteer | the ontology's rules, each recorded as the value's basis |
| Review | several possibilities, or sources cannot resolve | the same, with the units as the options |

## 6. Decisions taken by the engineer

1. `image` never names a text no reader wrote: it is one reader's text, `uncertain` or
   `not visible`. A reader can be added; the judge cannot become a reader. `means` is the judge's
   interpretation and is never a literal.
2. Every value an ontology rule decides is recorded with the rule named and shown so to the
   reviewer: derived when the label's own values give it (feet to metres), inferred when the rule
   supplies what the label does not write (an elevation's unit). This follows the owner's decision
   of 2026-10-08 that derived and inferred values are tracked by their basis and reviewed per part.
3. Darwin Core's conceptual model is the frame; the collection's rules, label types and conventions
   are ours.
4. People lookups need a source the owner approves first; none is approved today. The ask goes to
   him with the first phase's measurement, not before.

## 7. Build order

1. The ontology, first version: the things, the profile's fields and their Darwin Core names, the
   label types, and the conventions the units need (`means` and `fields` depend on it).
2. The reading units: first-pass schema and prompt, stored with the run; the ontology baked into
   the readers', the first pass's and the experts' instructions; the experts receive the units; a
   field settles on a unit the image names, with unanimity dropped. Measured with the first pass run
   live per repeat.
3. The ontology, second version: the code-checked rules (place chain, elevation, date order, label
   types), the inferred layer, cross-label assembly of one field. Measured on multi-label specimens.
4. People sources, if approved, and the remaining knowledge tables.

How the app shows the units, and cost and schedule, follow with each phase.
