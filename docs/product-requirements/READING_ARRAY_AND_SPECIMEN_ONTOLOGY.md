# The reading array and the specimen ontology

Status: DRAFT for the owner's sign-off, 2026-10-26. Written from the owner's words of 2026-10-25 and
2026-10-26. Nothing here is built. Every section says what exists today and what changes.

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

## 2. The reading array

The first pass reads every label of the specimen with the image. For each label it cuts the text at
logical breaks (a word, a number, a code, a date, a phrase that belongs together) and gives, for each
unit:

| Key | What it holds |
|---|---|
| `label`, `line` | Which label and which line of it |
| `readers` | What each reader wrote for this unit: `{"A": "...", "B": "...", "C": "..."}`; empty when a reader wrote nothing here |
| `image` | What the first pass sees in the image for this unit: one of the readers' texts, or `uncertain`, or `not visible`. Never a text no reader wrote |
| `means` | What the unit probably stands for: an expansion ("P.I." -> "Philippine Islands"), a normal form ("6-Sept-1946" -> 1946-09-06), a role ("leg." -> collected by). May be empty |
| `fields` | The fields this unit could belong to, most likely first. May be empty |
| `note` | One short sentence when something matters (a mark only one reader saw) |

The first pass never settles anything. It lists. The array goes to the harness together with the
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

- Input: the reading array (the units whose `fields` include this expert's field, from every label),
  the whole raw readings, the ontology (section 4), and the other fields as they settle.
- A field may settle on a unit whose `image` names a reader's text, or that a lookup confirms, or that
  the ontology makes the only consistent reading. The basis is recorded on the value, as now
  (as written, matched by a source, derived with the reason).
- One field may be assembled from units on different labels when the ontology says they belong
  together: a genus on one label and a species on another, a day on one and a year on another.
- The literal is still text a reader wrote; nothing is invented. A value may differ from the
  literal only through a lookup or an ontology rule, both named.
- When the array and the lookups leave two readings standing, the field goes to review with both,
  as now.
- Unanimity of readers is no longer required for anything.

## 4. The conceptual model, as an ontology

The model names the things a specimen label is about, how they relate, and what cannot be true
together. It is written down once and given to every expert; the rules that can be checked by code
are checked by code. It follows Darwin Core, the standard for specimen data, so every field here
maps to a term others already use.

### Things

| Thing | Examples on labels | Darwin Core |
|---|---|---|
| Specimen | the slide, its catalogue number, the institution that holds it | MaterialSample, catalogNumber, institutionCode |
| Collecting event | one act of collecting: who, where, when, how, in what habitat | Event: recordedBy, eventDate, samplingProtocol, habitat |
| Locality | the place of the event: a named site, inside a city or county, inside a province, inside a country; with an elevation | Location: locality, municipality, county, stateProvince, country, minimumElevationInMeters |
| Person | a collector, an identifier | recordedBy, identifiedBy |
| Determination | a taxon name given to the specimen by a person on a date | Identification: scientificName, identifiedBy, dateIdentified |
| Taxon | the name, its rank, its accepted name | Taxon |
| Code | a field number, a slide or preparation code, a species number | fieldNumber, otherCatalogNumbers |
| Label | a physical label; it carries attributes of the things above and has a type (locality label, determination label, code label) | not a Darwin Core thing; ours |

### Relations and what cannot be true together

- A specimen has one collecting event; the event has one locality, one date or date range, one or
  more collectors. Two labels that write different localities or dates for the same event contradict
  each other; the harness does not settle either and says why.
- A locality sits inside one chain: country > province > county > city. A unit cannot settle at one
  level outside the chain settled at a higher one ("Cook County" under "Philippines"). Built today for
  places; the spec keeps it and names it as the first instance of the rule.
- An elevation belongs to the locality and must be possible for it: the settled place's known
  elevation range (from the gazetteer or a terrain source) decides the unit when the label omits it.
- A collecting date lies within the collector's active years and before the determination date.
  The institution's name dates the label: "CNHM" means 1943-1966.
- A determination names a taxon that occurs in the settled region (GBIF occurrences), or the harness
  says it does not and sends it to review.
- A code that encodes a date (slide codes like "IV-23-48-2") must agree with the collecting date.
- A field that lives on a label type does not live on another: a determination label carries the
  taxon and the identifier, not the locality; the harness uses the label type to place units.

### Where each rule gets its knowledge

- Gazetteers (Getty TGN, Wikidata, NGA, GEOLocate): place chain, coordinates, elevation range.
- GBIF, Catalogue of Life, Global Names: taxon names, ranks, accepted names, occurrences by region.
- People: Wikidata and Bionomia for collectors' names and active years (new source).
- Institution and label conventions: a short written table kept in the repository (institution
  names and dates, unit conventions by era and country, slide-code formats).
- The owner and the collection's curators: the rules above are theirs to confirm and extend.

## 5. What exists today and what changes

| Piece | Today | Under this spec |
|---|---|---|
| Reader alignment | the code already aligns readers span by span (`reading_differences_among`) but outputs only the differences | the alignment becomes the units of the array |
| First pass output | one preferred reader or none, a verdict per difference, notes | the reading array; no preferred reader |
| Organiser | proposes field candidates from whole readings | folded into the array's `fields`; may stay as a check |
| Field experts | all readings, organiser proposals, first-pass advice, lookups | the array, the readings, the ontology, lookups |
| What may settle a field | all readers agree; a source confirms; another label agrees; the preferred reader's text | image names a reader's text; a source confirms; the ontology makes one reading the only consistent one; assembled across labels |
| Derivation | feet/metres, end date = start date, parent place from the gazetteer | the ontology's rules, each recorded as the value's basis |
| Review | several possibilities, or sources cannot resolve | the same, with the array's units as the options |

## 6. Questions for the owner

1. May the first pass ever propose a text that no reader wrote, when it reads the image itself? This
   draft says no: it may only choose among readers, say `uncertain`, or say `not visible`.
2. The ontology's rules decide values (an elevation unit, a date from a code). Should every such
   value be shown to the reviewer as derived, with the rule named, before it is accepted? This draft
   says yes.
3. Is Darwin Core acceptable as the frame for the ontology, with our own additions (label types,
   institution conventions)?
4. People sources (Wikidata, Bionomia) are new lookups: approve them as sources?

## 7. Not in this document

How the app shows the array, the measurement plan, cost and schedule. They follow the sign-off.
