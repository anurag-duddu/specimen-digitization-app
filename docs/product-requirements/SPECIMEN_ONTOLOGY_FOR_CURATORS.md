# The specimen ontology, for curators

This page explains, in plain words, what the digitization system knows about a specimen and its
labels. That knowledge lives in one file, the specimen ontology, version 2.0
(`specimen.yaml:60` (`version: "2.0"`)). The models that read the labels receive parts of it in
their instructions (`ontology/__init__.py:17-22` (`gives the text a model's`)), and code checks its
rules (`specimen.yaml:696-701` (`The rules (version 2.0)`)).

The file is the source of truth. This page copies the file's words where it can and names the line
it copies. If the two ever disagree, the file is right. The test
`tests/test_ontology_curator_doc.py` fails when this page's tables, or the text of a line or range
of the file it cites, stop matching the file (see "Keeping this page right" at the end).

Short names on this page:

- `specimen.yaml` is `src/specimen_digitization/ontology/specimen.yaml`, the ontology itself.
- `ontology/__init__.py` is `src/specimen_digitization/ontology/__init__.py`, the code that loads
  and checks it.
- "The spec" is [`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md`](FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md),
  the design this page sits beside.

Several sections end with a line for engineers that names the tests. A citation names a file and a
line, and for `specimen.yaml` also the text that line holds, so every statement here can be
checked.

## Words this page uses

- **Ambiguous**: no value settles, and the field keeps its candidates as options
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:200` (`When none has (text against text)`)).
- **Basis**: what a value is settled on. It is written in the value's reason, such as
  "Basis: inferred, rule elevation_unit_feet"
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:233-234` (`In this program a value's basis is written in its`)).
- **Check stage**: after every expert has answered, one stage checks the settled values
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:53-56` (`After every expert has answered, one check stage runs`)).
- **Cleared and marked**: a settled value is either cleared, with no review item, or marked: the
  value is set, and the record carries a review item for a person
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:52` (`whether the value is cleared or marked for a person`);
  `FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:193-194` (`It is CLEARED when it has an IMAGE or a SOURCE`);
  `FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:221-222` (`Marked means`)).
- **Coordinator**: the program's coordinator, whose rulings the plan records, such as the change of
  the rules from questions to a notice to the owner
  (`docs/execution/units/PLAN.md:125` (`the coordinator changed the reading from questions to a notice`)).
  The owner gave the ruling quoted on this page in the coordinator's session
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:332` (`the owner, in the coordinator's session`)).
- **Darwin Core**: the published model and terms for specimen data that the file is built on. Each
  field names its Darwin Core term, such as catalogNumber
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:306-308` (`Darwin Core publishes a conceptual model`); `specimen.yaml:62-66` (`frame:`)).
- **Expert**: the system's researcher for one field, with its lookups. There is one per field, and
  each receives every unit
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:50-52` (`The field experts run in parallel`)).
- **Field research**: the stage in which the experts research the fields, one expert per field
  (`src/specimen_digitization/field_research/__init__.py:1` (`one expert resolver per field`)).
- **First pass**: the model that cuts every label's text into units. It settles nothing
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:48-49` (`The first pass cuts each label's text into units at logical`)).
- **GBIF**: the Global Biodiversity Information Facility, the source the taxon expert looks a name
  up in. It matches the name against the pinned Catalogue of Life checklist and decides
  (`src/specimen_digitization/field_research/prompts/taxon.txt:3` (`GBIF matches the name against the pinned Catalogue of Life checklist`)).
- **Getty TGN**: the Getty Thesaurus of Geographic Names, one of the system's three gazetteers, the
  sources of place records
  (`src/specimen_digitization/field_research/contracts.py:22` (`GAZETTEERS = ("tgn", "wikidata", "nga")`)).
- **ISO 3166-1**: the standard country codes, such as GE for Georgia and US for the United States
  (`specimen.yaml:738` (`ISO 3166-1 codes`); `specimen.yaml:741-742` (`settled on Wikidata's nation (GE)`)).
- **Label id**: a name such as e98a924c-L2 names one label. That one is a label of pilot slide
  105526322 (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:118` (`Pilot label e98a924c-L2`)).
- **Literal**: the exact text a value copies from a reading. The value itself may be a source's
  name: the literal "Chimaltenago" can carry the value "Chimaltenango"
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:173-178` (`The merged candidate's literal is the text the image`)).
- **Morphocode**: the file's word for a species number, written "sp." and a number. After a genus
  it is a genus-level identification (`specimen.yaml:623` (`a morphocode, a species number`)).
- **Organiser**: a model that proposes candidates for every field, quoted from the whole readings.
  Each expert receives them
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:362` (`proposes candidates quoted from whole readings`); `FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:151` (`the organiser's candidates`);
  `specimen.yaml:709` (`the organiser, which proposes every field`)).
- **Reader**: one of the models that transcribe each label. A pilot label's readers are named A, B
  and C (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:309-310` (`rendered into every model's instructions: the readers`);
  `FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:118-123` (`Pilot label e98a924c-L2`)).
- **Reading**: the word has two senses. A reader's transcription of a label is a reading
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:50-51` (`every raw`)). A notation's reading is one meaning the notation allows, such as
  "the Philippines" for "P.I."
  (`specimen.yaml:353` (`The label notations and every reading each allows`)).
- **Reference truth**: the expected values of the pilot specimens, ten rows in
  `tests/fixtures/field_model_pilot_rows.json`
  (`specimen.yaml:1102-1103` (`confirmed by the reference truth`)).
- **Refused**: code turns an answer down, and the field does not settle on it
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:209-212` (`No candidate has a backing`)).
- **Settle**: a field settles when one candidate value is accepted for it
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:193` (`Exactly one candidate has a backing: it settles`)).
- **Source record**: the record a lookup source, such as a gazetteer, gives for a place, naming the
  places it lies in, its parents
  (`specimen.yaml:735-736` (`settled on a source record that names`)).
- **Unit**: a piece of one label's text, cut at a logical break, such as "P.I.", "6-Sept-1946" or
  "H. Hoogstraal leg." (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:135-142` (`CNHM.`)).
- **Units path**: the way of reading a specimen in units. Every new run records it, and a run the
  old first pass processed is moved onto it when it is reopened
  (`src/specimen_digitization/application/reading_units.py:27-30` (`Every new run records UNITS`)).
  The experts research a run on the units path only
  (`src/specimen_digitization/field_research/step.py:211-213` (`The workflow`)). So this page leaves
  out the file's "on the units path": each rule below holds for every run the experts research. A
  completed run of the old path that a person decides a field on, with no new research, keeps that
  path's date order and precise location rules
  (`src/specimen_digitization/field_research/step.py:213-216` (`The clearance rules`)).
- **Unresolved**: "A value is `unresolved` only when nothing supports even an inference"
  (`docs/product-requirements/PRD.md:667` (`only when nothing supports even an inference`)).
- **Work package (WP)**: a numbered step of the program's plan, `docs/execution/units/PLAN.md`.
  WP 2.1 gave the file its version 2.0
  (`specimen.yaml:25` (`Version 2.0 (plan WP 2.1, 2026-11-14)`)).

## What the file is built on

- **Its frame** is Darwin Core's conceptual model of specimen data, version 2026-10-13
  (`specimen.yaml:62-66` (`frame:`)).
- **Every entry names its source.** The loader refuses an entry with no source
  (`ontology/__init__.py:440-446` (`def _source`)). It also refuses a key it does not know, a field
  that is not one of the profile's 20, and a file that leaves one of the 20 out
  (`ontology/__init__.py:414-425` (`def _entry`); `ontology/__init__.py:449-456` (`def _fields`);
  `ontology/__init__.py:542-545` (`keys = [entry.key`)).
- **Version 1.0 held no meaning the engineer invented.** Its notations were moved from the Insects
  harness knowledge and from the label notations of `field_research/prompts/common.txt`
  (`specimen.yaml:8-15` (`Version 1.0 held no meaning the engineer invented`)).
- **Version 2.0 resolved the meanings that 1.0 left open, from sources and without asking the
  owner.** The sources come in this order: the PRD and the field briefs first, then the reference truth's general
  conventions, then a public reference. A meaning no source settles stays an open question, and its
  unit carries no field
  (`specimen.yaml:34-35` (`Version 2.0 also resolves the meanings`);
  `specimen.yaml:39-42` (`Each resolved meaning is a notation or a rule`)).

For engineers: the loader's refusals are pinned by
`tests/test_ontology.py::test_the_loader_refuses_a_notation_with_no_source`,
`tests/test_ontology.py::test_every_other_entry_needs_a_source_too`,
`tests/test_ontology.py::test_the_loader_refuses_an_unknown_key`,
`tests/test_ontology.py::test_the_loader_refuses_a_field_not_among_the_profiles_20_keys` and
`tests/test_ontology.py::test_the_loader_refuses_a_file_that_leaves_out_one_of_the_20_fields`.

## The things on a label

The file names eight things. The examples and the Darwin Core terms are the file's words
(`specimen.yaml:68-108` (`things:`)).

| Thing | Examples on labels | Darwin Core |
|---|---|---|
| Specimen | the slide, its catalogue number, the institution that holds it | MaterialEntity; catalogNumber, institutionCode |
| Collecting event | one act of collecting: where, when, how, in what habitat | Event: eventDate, samplingProtocol, habitat; the collectors as recordedBy |
| Locality | the place of the event, in a chain country > province > county > city, with an elevation | dcterms:Location: locality, municipality, county, stateProvince, country, minimumElevationInMeters |
| Agent | a collector, an identifier | Agent; recordedBy, identifiedBy |
| Determination | a taxon name given to the specimen by a person on a date | Identification: identifiedBy, dateIdentified; the name as Taxon: scientificName |
| Taxon | the name, its rank, its accepted name | Taxon |
| Code | a slide or preparation code, a species number | no term fits them; the thing is this file's own |
| Label | a physical label; it carries attributes of the things above and has a type (locality, determination, code) | no term; the thing is this file's own |

### How the things relate

- **A specimen has one collecting event.** When two of its labels write two different collecting
  dates, or two place names that no source confirms as one place, an answer that settles the field
  on one label's text is refused
  (`specimen.yaml:711-717` (`id: one_collecting_event`)).
- **The collecting event happened at a locality**, whose places form one chain: country > province
  or state > county > city
  (`specimen.yaml:79-81` (`id: locality`); `specimen.yaml:787-789` (`id: place_chain`)).
- **Agents** are a collector or an identifier. Darwin Core records the collectors as
  recordedBy and the identifier as identifiedBy
  (`specimen.yaml:84-87` (`id: agent`)).
- **A determination is a taxon name given to the specimen by a person on a date.** The collecting
  date is on or before the determination date, and the same day is allowed
  (`specimen.yaml:89-92` (`id: determination`); `specimen.yaml:835-837` (`id: date_order`)).
- **The specimen's taxon is settled only inside the collection's higher taxon, class Insecta**
  (`specimen.yaml:1184-1188` (`id: taxon_in_collection_scope`)). A name written after a host
  marker names the host, never the specimen's taxon
  (`specimen.yaml:1221-1228` (`id: host_is_no_taxon`)).
- **A label carries attributes of the things above and has a type**: locality, determination or
  code (`specimen.yaml:104-106` (`id: label`)). Its type never keeps a field's expert from its
  units: a determination label that writes a locality reaches the locality expert
  (`specimen.yaml:906-912` (`id: label_type_routing`)).
- **A code is never a date, nor part of one.** A code is a slide or preparation code or a species
  number, and no Darwin Core term fits it
  (`specimen.yaml:99-102` (`id: code`); `specimen.yaml:869-872` (`id: code_is_no_date`)).

For engineers: most relations above are rules of the file; the rules section below lists them all.

## The 20 fields

These are the profile's 20 fields, in the profile's order. The display name is the PRD's. "What it
holds" is the first line of the field's brief, unless the file says otherwise
(`specimen.yaml:110-113` (`The profile's 20 fields`)). The last column names the rule by which the
system fills the field from other fields, where the file has one.

| Key | Display name | Darwin Core | What it holds | Filled from other fields |
|---|---|---|---|---|
| `fmnh_ins_number` | FMNH-INS# | `catalogNumber` | The Field Museum insect catalog number, often printed after "FMNH INS" or "FMNHINS", sometimes on a barcode label. | No |
| `collection_code` | Collection Code | `collectionCode` | A code the label writes for the collection or the collecting event, copied as written. | No |
| `country` | Country | `country` | The country where the specimen was collected, as the labels write it. | `place_parents_derived` |
| `province_state` | Province/State | `stateProvince` | The first-level administrative unit (province, state or department) where the specimen was collected, as the labels write it. | `place_parents_derived` |
| `county` | County | `county` | The country's second-level administrative unit where the specimen was collected, as the labels write it: a county, or whatever unit the country's local government holds at that level instead (a municipio, where that is the second level). | `place_parents_derived` |
| `city` | City | `municipality` | The city, town or municipality the labels name as the collecting place. | No |
| `precise_location` | Precise Location | `verbatimLocality` | The locality as the label writes it: the most specific place text, such as "E. slope Mt. `<Mountain>`, nr. `<Town>`". | No |
| `elevation_from_m` | Elevation From (m) | `minimumElevationInMeters` | The lower, or only, elevation the label writes in metres. | `elevation_conversion` |
| `elevation_to_m` | Elevation To (m) | `maximumElevationInMeters` | The upper end of an elevation range the label writes in metres. | `elevation_conversion` |
| `elevation_from_ft` | Elevation From (ft) | `verbatimElevation` | The lower, or only, elevation the label writes in feet. | `elevation_conversion`; also inferred by `elevation_unit_feet` |
| `elevation_to_ft` | Elevation To (ft) | `verbatimElevation` | The upper end of an elevation range the label writes in feet. | `elevation_conversion` |
| `habitat` | Habitat | `habitat` | The habitat, host or substrate the label writes, such as "under `<substrate>`", "on `<host>`" or "`<vegetation>` forest", copied as written. | No |
| `collection_method` | Collection Method | `samplingProtocol` | How the specimen was collected, as the label writes it, such as "Berlese", "light trap", "beating" or "sweeping". | No |
| `date_visited_from` | Date Visited From | `eventDate` | The date the specimen was collected, or the first date of a written collecting range, at the precision written. | No |
| `date_visited_to` | Date Visited To | `eventDate` | The last date of collecting, only when the label writes a range or an end date, at the precision written. | `end_date_from_one_date` |
| `collectors` | Collectors | `recordedBy` | The people who collected the specimen, exactly as the label writes them. | No |
| `verbatim_dts` | Verbatim D/T/S | `verbatimEventDate` | Text transcribed exactly as written: a non-standard collection-event date or time expression, such as "Avril 1917", "Summer 1914", "am", "pm", "sunrise" or "daylight". | No |
| `taxon` | Taxon | `scientificName` | The scientific name the labels give the specimen, at the rank written. | No |
| `identified_by_irn` | Identified by IRN | `identifiedBy` | The EMu Parties record number (IRN) of the person who identified the specimen. | No |
| `date_identified` | Date Identified | `dateIdentified` | The date the specimen was identified (determined), at the precision written. | No |

### What the file adds about some fields

- **Precise Location**: "Darwin Core's locality is its interpretation and may equal it."
  (`specimen.yaml:172` (`Darwin Core's locality is its interpretation and may equal it.`)).
- **The four elevation fields**: "The four elevation fields map to verbatimElevation, as written,
  and to minimumElevationInMeters and maximumElevationInMeters; an elevation in feet is the
  verbatimElevation ("4800 ft.")."
  (`specimen.yaml:190-197` (`key: elevation_from_ft`)).
- **Verbatim D/T/S**: no document of the repository names this field's Darwin Core term. The file
  uses verbatimEventDate, Darwin Core's term for an event's date and time as written
  (`specimen.yaml:267-271` (`The brief's first line says the museum has not confirmed`)).
- **Identified by IRN**: "The museum's Darwin Core mapping resolves the identifier's Parties
  reference to the name it publishes as identifiedBy; its public archive maps no identifiedByID."
  (`specimen.yaml:289-291` (`The museum's Darwin Core mapping resolves`)).
- **Collection Code** is Darwin Core's collectionCode: a code the label writes, copied as written
  (`specimen.yaml:125-128` (`key: collection_code`)). It is not an EMu record number: of the 20
  fields, only Identified by IRN holds one
  (`specimen.yaml:287` (`The EMu Parties record number (IRN)`)). The owner's ruling below covers
  one printed heading.

### Values the system fills in

Code fills the values below. A value derived from other fields names its rule in its basis
(`ontology/__init__.py:141-142` (`field_research/derive.py fills the rule's fields by it`)). Each
bullet quotes the instruction the models receive under its rule. For the three derived values, that
instruction is not to fill the value themselves.

- **Country, Province/State and County** (`specimen.yaml:1008-1022` (`id: place_parents_derived`)).
  Upward derivation fills only open fields, such as a country from a settled province. A province
  derived from a county is the county's province-level parent, the first of the two or more its
  record names, never the country. The models are told: "Leave a larger place the label does not
  write empty: never take it from a smaller place's parents."
  (`specimen.yaml:1024-1025` (`Leave a larger place the label does not write empty`)).
- **The four elevation fields** (`specimen.yaml:1051-1063` (`id: elevation_conversion`)). A
  derived elevation is a stated one copied to the other end of its unit, or its exact conversion
  (1 ft = 0.3048 m) rounded to the hundredth. A derived elevation never replaces a stated one. No
  elevation is derived while an elevation field is neither settled nor open: one the readings
  disagree on goes to a person first. The models are told: "Never convert an elevation to the other
  unit: give it in the unit the label writes."
  (`specimen.yaml:1065-1066` (`Never convert an elevation to the other unit`)).
- **Elevation From (ft), inferred** (`specimen.yaml:926-940` (`id: elevation_unit_feet`)). An
  elevation whose text writes no unit is read as feet only when all three hold:
  - (a) at the elevation's own unit, at least one reader wrote the foot mark or "ft" right after
    its number, unquoted and with no other unit after it, and another reader wrote no unit; no
    reading writes another elevation; and the expert's options name no other number;
  - (b) the number, read as metres, is above the highest point of the specimen's country, and the
    country is cleared, not marked. The highest points come from the file's own table
    (`specimen.yaml:1296-1301` (`Each country's highest point and its elevation, from Wikidata`));
  - (c) the number, read as feet, is possible: 16000 with a mark is not, in the Philippines.

  When all three hold, Elevation From (ft) settles to that number, cleared, its reason
  "Basis: inferred, rule elevation_unit_feet"
  (`specimen.yaml:937` (`Basis: inferred, rule elevation_unit_feet`)), and derivation fills the
  other elevation fields. Otherwise the field is unresolved: magnitude alone never decides. The
  models are told: "Keep an elevation's foot mark (') or "ft" wherever it is written; a number's
  size alone never makes it feet."
  (`specimen.yaml:942-943` (`Keep an elevation's foot mark`)).
- **Date Visited To** (`specimen.yaml:1076-1079` (`id: end_date_from_one_date`)). A derived Date
  Visited To is the date of a settled Date Visited From, at its precision, and is never derived from
  a written range. The models are told: "Give Date Visited To only from an end date the label
  writes, never from a single collecting date."
  (`specimen.yaml:1087-1088` (`Give Date Visited To only from an end date the label writes`)).

For engineers: the field list, its order and its display names are pinned by
`tests/test_ontology.py::test_the_file_lists_the_profiles_20_fields_in_order_with_their_display_names`.
The derivation rules are the three with `derives` (`ontology/__init__.py:141-142`
(`field_research/derive.py fills the rule's fields by it`)), pinned by
`tests/test_ontology.py::test_the_file_holds_the_specs_rules_each_checked_as_stated`. The Philippine
case of the feet rule is
`tests/field_research/test_elevations_and_extent.py::test_6400_with_b_s_foot_mark_and_the_philippines_cleared_settles_6400_ft_cleared`.

## Label notations

A notation is a way labels write something: an abbreviation, a marker, a unit, a date form. For
each, the file lists the forms a label writes, every reading the notation allows, and the fields it
can belong to (`specimen.yaml:353-356` (`The label notations and every reading each allows`)).

### How a form is found in a unit

The file states how its forms are matched in a unit's text
(`specimen.yaml:46-58` (`forms are matched in a unit's text`)):

- Letter case does not matter, except in a word in angle brackets.
- A space in a form matches any white space, a line break, or no space at all.
- A form's final period is optional only where the table below says so.
- A form that begins or ends with a letter, a digit or a word in angle brackets matches only at a
  word's edge. So "c." is not found inside "McKinley"
  (`tests/test_ontology.py::test_a_form_matches_only_at_a_words_edge`).
- A word in angle brackets stands for what the label writes there: `<n>` a number; `<d>`, `<dd>`,
  `<d1>`, `<d2>`, `<mm>`, `<a>`, `<b>` a day's or a month's one or two digits; `<yy>` a two-digit
  year; `<yyyy>` a four-digit year; `<Roman month>` a Roman numeral I to XII in capitals;
  `<letter>` one letter
  (`specimen.yaml:52-56` (`A word in angle brackets stands for what the label writes there`);
  `ontology/__init__.py:53-66` (`PLACEHOLDERS`)).
- A match inside a longer match is dropped, so no part of a slide code is read as a date. A unit
  that holds an open question carries no field and no reading
  (`specimen.yaml:56-58` (`A match inside a longer match is dropped`);
  `ontology/__init__.py:302-311` (`kept = sorted(`);
  `tests/test_ontology.py::test_no_part_of_a_slide_code_is_a_date`).

### How a reading is used

The file's rule for every notation, in its own words
(`specimen.yaml:341-351` (`notation_rule:`)):

> Copy every literal exactly as the reading has it, character for character; a literal that is not
> in the reading is refused. Never complete, correct or translate a literal: readings of a notation
> are for calling the tools, never for the literal itself. Work through every reading a notation
> allows before a field is left for review, and let the tools and the specimen's other evidence
> decide between them. A field the label does not have stays empty.

In plain words: a reading helps the system look a value up, and it never changes what is copied.
"P.I." is looked up as the Philippines, and the text copied from the label stays "P.I.".

### The notations

The readings and notes are the file's words. "No field" means the notation fills none of the 20
fields.

| Notation | The label writes | Field | What it means |
|---|---|---|---|
| `philippine_islands_abbreviation` | `P.I.` | Country | Philippine Islands, the Philippines. |
| `philippine_islands` | `Philippine Islands` | Country | the Philippines. |
| `guatemala_abbreviation` | `Guat.` | Country | Guatemala. |
| `new_south_wales_abbreviation` | `N.S.W.` | Country, Province/State, County, City, Precise Location | New South Wales: a place abbreviation, looked up by its expansion. As for a place's name, the sources decide which level it is. |
| `province` | `Prov.` | Province/State | province, a word of the province's name, not the name. Look it up with the word written out ("Davao Province" for "Davao, Prov."). |
| `department` | `Dept.` | Province/State | department, a word of the province's name, not the name. |
| `county_word` | `Co.` | County | county, a word of the county's name, not the name. Look it up with the word written out ("`<County>` County" for "`<County>` Co."). |
| `mount` | `Mt.` | Precise Location | mount, part of the place's name. |
| `mts_abbreviation` | `Mts.` | Country, Province/State, County, City, Precise Location | a place abbreviation: when you know what it stands for, look up its expansion. As for a place's name, the sources decide which level it is. |
| `island` | `Is.` | Precise Location | island or islands. An island is neither a province nor a city, and no field of the profile holds an island's level: the precise location keeps it as written. |
| `near` | `nr.` | Precise Location | near. |
| `direction` | `E. slope`, `W. side` | Precise Location | a direction qualifying the place that follows. |
| `collected_by` | `leg.`, `coll.`, `Coll.` | Collectors | collected by, marking the collectors. |
| `determined_by` | `det.` | Identified by IRN | determined by, marking who identified the specimen. |
| `metres` | `<n> m` | Elevation From (m), Elevation To (m) | metres, the unit of an elevation; not metres when a capital "M" stands before a name or in a count of males and females. The unit decides the field. |
| `feet` | `<n> ft.`, `<n>'` | Elevation From (ft), Elevation To (ft) | feet, the unit of an elevation. The unit decides the field. |
| `elevation_heading` | `alt.`, `el.` | Elevation From (m), Elevation To (m), Elevation From (ft), Elevation To (ft) | the heading of an elevation. |
| `approximate` | `ca.`, `c.` | Elevation From (m), Elevation From (ft), Date Visited From | about: the value is approximate. |
| `roman_month` | `<d>.<Roman month>.<yyyy>`, `<Roman month>-<d>-<yy>`, `<yyyy>.<Roman month>.<d>` | Date Visited From, Date Visited To, Date Identified | the month, January to December, in any position of the date, when the profile allows Roman months; or the same, a 1 written for an I (1X: IX). |
| `month_name` | `Jan.`, `Feb.`, `Mar.`, `Apr.`, `Jun.`, `Jul.`, `Aug.`, `Sep.`, `Sept.`, `Oct.`, `Nov.`, `Dec.`, `ene.`, `janv.`, `Mai`, `Okt.`, `agosto` | Date Visited From, Date Visited To, Date Identified | the month. A month may be written by name in English, Spanish, French, German, Portuguese, Italian or Latin, abbreviated or not, with or without periods, and a day may carry an ordinal ("3rd", "1er"); the forms listed are examples. The final period is optional. |
| `numeric_date` | `<a>-<b>-<yy>`, `<a>.<b>.<yy>`, `<a>/<b>/<yy>` | Date Visited From, Date Visited To, Date Identified | month `<a>`, day `<b>`; or day `<a>`, month `<b>`. Settled only when a part over 12 fixes day against month; otherwise both readings stand until evidence decides. |
| `date_range` | `<d1>-<d2>.<Roman month>.<yyyy>`, `<Roman month>-<Roman month>.<yy>`, `<d1>.<Roman month>-<d2>.<Roman month>.<yyyy>` | Date Visited From, Date Visited To | a range: its first date is the start and its second the end. |
| `two_digit_year` | `'<yy>`, `-<yy>` | Date Visited From, Date Visited To, Date Identified | the year 19`<yy>`, under the profile's century rule. |
| `uncertain` | `?` | No field | the value before it is uncertain as written. |
| `slide_code` | `<Roman month>-<dd>-<yy>-<n>`, `<mm>-<dd>-<yy>-<n><letter>` | No field | a slide or preparation code: a month, a day, a two-digit year and a slide number joined by hyphens; never a date, nor is any part of it. No field takes a slide code. |
| `lewis_collection_heading` | `LEWIS COLLECTION` | Collection Code | the printed heading of the Lewis Collection's label templates; it is the Collection Code, copied as written. |
| `cnhm` | `CNHM.` | No field | Chicago Natural History Museum, the Field Museum's name from 1943 to 1966: the institution, never a collector, and no field of its own. Written on a locality line, it is part of the precise location as written. The final period is optional. |
| `species_number` | `sp. <n>` | Taxon | a morphocode, a species number: after a genus, a genus-level identification; with no genus on any label, it names no scientific taxon. |
| `host_marker` | `Host`, `ex.`, `on`, `from` | No field | before a name, the specimen's host (associatedTaxa), never its taxon. The final period is optional. |
| `female_sign` | `♀` | No field | female: the specimen's sex, which no field of the profile holds. |
| `male_sign` | `♂` | No field | male: the specimen's sex, which no field of the profile holds. |

### Where each notation comes from

The sources are listed as the file records them. A source `<path>:<lines>` is a file of this
repository at the commit that added the entry. A source `insects.py:<lines> at 7a09445a2` is the
Insects harness knowledge module, which version 1.0 moved into this file and deleted, as it stood
at commit 7a09445a2. A source
`src/specimen_digitization/field_research/prompts/common.txt:<lines> at d83f4d6f1` is the experts'
shared brief as it stood at commit d83f4d6f1, where it still held its label notations: WP 1.8 gave
that file the units path's text, and its notations are this file's
(`specimen.yaml:16-23` (`A source "<path>:<lines>" is a file of this repository`)).

| Notation | In the file | Sources as the file records them |
|---|---|---|
| `philippine_islands_abbreviation` | `specimen.yaml:358` (`id: philippine_islands_abbreviation`) | `insects.py:28 at 7a09445a2`; `insects.py:94 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:36 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/common.txt:27 at d83f4d6f1` |
| `philippine_islands` | `specimen.yaml:367` (`id: philippine_islands`) | `insects.py:95 at 7a09445a2` |
| `guatemala_abbreviation` | `specimen.yaml:373` (`id: guatemala_abbreviation`) | `insects.py:29 at 7a09445a2`; `insects.py:96 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:36 at d83f4d6f1` |
| `new_south_wales_abbreviation` | `specimen.yaml:381` (`id: new_south_wales_abbreviation`) | `src/specimen_digitization/field_research/prompts/common.txt:27 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/common.txt:36 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/county.txt:5` |
| `province` | `specimen.yaml:390` (`id: province`) | `insects.py:30-34 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:27 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/common.txt:37 at d83f4d6f1` |
| `department` | `specimen.yaml:399` (`id: department`) | `insects.py:35-39 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:37 at d83f4d6f1` |
| `county_word` | `specimen.yaml:406` (`id: county_word`) | `src/specimen_digitization/field_research/prompts/common.txt:36 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/county.txt:8`; `src/specimen_digitization/field_research/prompts/county.txt:12` |
| `mount` | `specimen.yaml:415` (`id: mount`) | `insects.py:40 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:38 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/city.txt:6` |
| `mts_abbreviation` | `specimen.yaml:423` (`id: mts_abbreviation`) | `src/specimen_digitization/field_research/prompts/common.txt:36 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/county.txt:5` |
| `island` | `specimen.yaml:434` (`id: island`) | `insects.py:41-43 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:38 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/province_state.txt:7`; `src/specimen_digitization/field_research/prompts/city.txt:6`; `docs/product-requirements/PRD.md:785-786`; `tests/fixtures/field_model_pilot_rows.json:17`; `tests/fixtures/field_model_pilot_rows.json:30` |
| `near` | `specimen.yaml:449` (`id: near`) | `insects.py:44 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:38 at d83f4d6f1` |
| `direction` | `specimen.yaml:456` (`id: direction`) | `insects.py:45-49 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:38 at d83f4d6f1` |
| `collected_by` | `specimen.yaml:463` (`id: collected_by`) | `insects.py:50-52 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:39 at d83f4d6f1` |
| `determined_by` | `specimen.yaml:470` (`id: determined_by`) | `insects.py:53-57 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:39 at d83f4d6f1` |
| `metres` | `specimen.yaml:482` (`id: metres`) | `insects.py:58-62 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:44 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/elevation_from_m.txt:8`; `src/specimen_digitization/field_research/written.py:451-462`; `src/specimen_digitization/field_research/written.py:465-494`; `src/specimen_digitization/field_research/written.py:523-528`; `src/specimen_digitization/field_research/written.py:986-994`; `docs/execution/units/PLAN.md:113` |
| `feet` | `specimen.yaml:496` (`id: feet`) | `insects.py:58-62 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:44 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/elevation_from_ft.txt:8` |
| `elevation_heading` | `specimen.yaml:505` (`id: elevation_heading`) | `insects.py:58-62 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:44 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/elevation_from_m.txt:9` |
| `approximate` | `specimen.yaml:513` (`id: approximate`) | `insects.py:63-67 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:44 at d83f4d6f1` |
| `roman_month` | `specimen.yaml:525` (`id: roman_month`) | `insects.py:68-72 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:40 at d83f4d6f1`; `tests/fixtures/field_model_pilot_rows.json:163-167`; `tests/fixtures/field_model_pilot_rows.json:193`; `src/specimen_digitization/field_research/checks.py:55-75` |
| `month_name` | `specimen.yaml:536` (`id: month_name`) | `insects.py:73-77 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:40 at d83f4d6f1` |
| `numeric_date` | `specimen.yaml:549` (`id: numeric_date`) | `insects.py:78-82 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:41 at d83f4d6f1` |
| `date_range` | `specimen.yaml:557` (`id: date_range`) | `src/specimen_digitization/field_research/prompts/common.txt:42 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/date_visited_from.txt:16`; `src/specimen_digitization/field_research/prompts/date_visited_to.txt:6` |
| `two_digit_year` | `specimen.yaml:565` (`id: two_digit_year`) | `insects.py:83-87 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:43 at d83f4d6f1` |
| `uncertain` | `specimen.yaml:572` (`id: uncertain`) | `insects.py:88 at 7a09445a2`; `src/specimen_digitization/field_research/prompts/common.txt:47 at d83f4d6f1` |
| `slide_code` | `specimen.yaml:579` (`id: slide_code`) | `src/specimen_digitization/field_research/prompts/common.txt:48 at d83f4d6f1`; `src/specimen_digitization/field_research/prompts/collection_code.txt:6`; `src/specimen_digitization/field_research/prompts/fmnh_ins_number.txt:6`; `src/specimen_digitization/field_research/prompts/collectors.txt:8`; `src/specimen_digitization/field_research/prompts/habitat.txt:4`; `src/specimen_digitization/field_research/prompts/collection_method.txt:4`; `tests/fixtures/field_model_pilot_rows.json:134` |
| `lewis_collection_heading` | `specimen.yaml:595` (`id: lewis_collection_heading`) | `docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:332` |
| `cnhm` | `specimen.yaml:608` (`id: cnhm`) | `tests/fixtures/field_model_pilot_rows.json:134`; `tests/fixtures/field_model_pilot_rows.json:57`; `tests/fixtures/field_model_pilot_rows.json:79`; `tests/fixtures/field_model_pilot_rows.json:115`; `https://en.wikipedia.org/wiki/Field_Museum_of_Natural_History` |
| `species_number` | `specimen.yaml:621` (`id: species_number`) | `src/specimen_digitization/field_research/prompts/taxon.txt:5`; `src/specimen_digitization/field_research/prompts/taxon.txt:8-9` |
| `host_marker` | `specimen.yaml:633` (`id: host_marker`) | `https://dwc.tdwg.org/terms/#dwc:associatedTaxa`; `https://dwc.tdwg.org/terms/#dwc:scientificName`; `src/specimen_digitization/field_research/prompts/taxon.txt:1`; `docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:318` |
| `female_sign` | `specimen.yaml:646` (`id: female_sign`) | `https://www.unicode.org/charts/PDF/U2600.pdf`; `https://dwc.tdwg.org/terms/#dwc:sex`; `src/specimen_digitization/application/domain.py:69-90`; `tests/fixtures/field_model_pilot_rows.json:75-87` |
| `male_sign` | `specimen.yaml:655` (`id: male_sign`) | `https://www.unicode.org/charts/PDF/U2600.pdf`; `https://dwc.tdwg.org/terms/#dwc:sex`; `src/specimen_digitization/application/domain.py:69-90`; `tests/fixtures/field_model_pilot_rows.json:75-87` |

For engineers: `tests/test_ontology.py::test_every_source_names_a_file_and_lines_it_has` skips a
web source. Every other source must name a line or a range of lines, the first no later than the
last. For a file of this repository the test checks that the file exists and has those lines. An
`insects.py ... at 7a09445a2` source, from the deleted module, is checked only for its prefix and for
lines within that module's 120 lines, and a `common.txt ... at d83f4d6f1` source only for its path
and for lines within the 48 lines that file had then
(`tests/test_ontology.py:441-458` (`for source in sources:`)). The experts' label
notations are pinned in the file by
`tests/test_ontology.py::test_the_label_notations_of_the_experts_brief_are_in_the_file`.

## Which field a unit goes to

The file's advice on where a unit belongs:

- **A unit that holds an open question carries no field and no reading**, whatever else it holds.
  This is the only part of the advice that overrides the rest
  (`ontology/__init__.py:309-311` (`questions = _unique`)).
- **A unit takes the fields of every notation it matches**
  (`ontology/__init__.py:312-315` (`notations = [entry`)).
- **A unit judged to be of a routing kind, such as a place's name, also takes that routing entry's
  fields, after the notations' fields.** A routing entry is a judgement of the unit that no notation
  makes
  (`ontology/__init__.py:288-289` (`names a routing entry, a judgement of the unit no notation`);
  `ontology/__init__.py:316-317` (`if route is not None:`)). The file advises judging a unit's kind
  where no notation names its fields
  (`specimen.yaml:306-308` (`The fields a kind of unit could belong to`)). "Mt. Apo" judged a
  place's name shows both: "Mt." gives Precise Location, and the routing entry adds the other place
  fields.

The fields are advice only: every expert receives every unit. The order of the fields is the
file's, not a likelihood (`specimen.yaml:306-308` (`The fields a kind of unit could belong to`)).

### The routing entries

| Routing entry | The unit | Fields | What it means | In the file |
|---|---|---|---|---|
| `place_name` | a place's name the label writes with no notation beside it ("`<Town>`", "`<Province>`", "`<Country>`", a mountain's name) | Country, Province/State, County, City, Precise Location | a place; the sources decide which level it is (a country, a province or state, a county or municipio, a city or town, or a place within them), never its name; a town and the second-level unit around it often share a name, and a mountain, an island, a river or an estate belongs to the precise location | `specimen.yaml:310` (`id: place_name`) |
| `person_name` | a person's name ("`<Initials>` `<Surname>`") | Collectors, Identified by IRN | a person; the marker beside the name says the role ("leg.", "coll.", "Coll.": a collector; "det.": the determiner), and capitalisation or position alone establishes no role | `specimen.yaml:327` (`id: person_name`) |

### Examples from the pilot labels

Most of these units come from the pilot labels. "Judged as" is the routing entry the unit is
given, where one applies. The fields are what the file gives each unit, and
`tests/test_ontology_curator_doc.py::test_each_example_units_fields_are_the_ones_the_file_gives_it`
checks every row against the file. The eleven pilot units the plan names are also pinned by
`tests/test_ontology.py::test_the_eleven_pilot_units_get_the_fields_and_meaning_the_file_gives_them`,
and three more by the tests named under the table.

| Unit | Judged as | Fields | Why |
|---|---|---|---|
| `CNHM.` | None | No field | The institution, never a collector (`cnhm`). |
| `P.I.` | None | Country | Philippine Islands, the Philippines (`philippine_islands_abbreviation`). |
| `Elev.6400'` | None | Elevation From (ft), Elevation To (ft) | The foot mark makes it feet (`feet`). |
| `Elev.6400` | None | No field | No unit is written, so no notation gives an elevation field. |
| `H. Hoogstraal leg.` | None | Collectors | "leg." marks the collectors (`collected_by`). |
| `Sp.30 ♀` | None | Taxon | "Sp.30" is a morphocode (`species_number`). "♀" is the specimen's sex, which no field holds (`female_sign`). |
| `6-Sept-1946` | None | Date Visited From, Date Visited To, Date Identified | "Sept" names the month (`month_name`). |
| `P-95-81-16` | None | No field | An open question: the unit carries no field and no reading (`p_code`). |
| `IV-29-68-4` | None | No field | A slide code, never a date, nor is any part of it (`slide_code`). |
| `Yepocapa` | a place's name (`place_name`) | Country, Province/State, County, City, Precise Location | A place: the sources decide which level it is. |
| `4800ft.` | None | Elevation From (ft), Elevation To (ft) | Feet (`feet`). |
| `Chimaltenago` | a place's name (`place_name`) | Country, Province/State, County, City, Precise Location | A place: the sources decide which level it is. |
| `LEWIS COLLECTION` | None | Collection Code | The owner's ruling below (`lewis_collection_heading`). |
| `Siphonaptera of Utah` | None | No field | Not ruled: no entry in the file. |
| `Mt. Apo` | a place's name (`place_name`) | Precise Location, Country, Province/State, County, City | "Mt." gives Precise Location (`mount`); the routing entry adds the other place fields. |

For engineers: `Elev.6400` is pinned by `tests/test_ontology.py::test_a_form_matches_only_at_a_words_edge`,
`LEWIS COLLECTION` by
`tests/test_ontology.py::test_a_unit_whose_text_is_the_printed_lewis_collection_heading_gets_the_collection_code`,
and `Siphonaptera of Utah` by `tests/test_ontology.py::test_no_other_printed_heading_is_ruled`. A
place's name with no routing entry gets nothing:
`tests/test_ontology.py::test_a_place_name_has_no_notation_and_takes_its_fields_from_routing_only`.

## The owner's ruling in the file

On 2026-11-13, in the coordinator's session, the owner was asked
'Should a printed "LEWIS COLLECTION" heading be stored as the Collection Code?'
and answered with the button "Yes, store it"
(`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:332` (`the owner answered with the button "Yes, store it"`)).

- **What the file does with it**: the notation `lewis_collection_heading` gives a unit whose text
  is the printed heading "LEWIS COLLECTION", on one line or across two, the Collection Code, copied
  as written (`specimen.yaml:595-600` (`id: lewis_collection_heading`);
  `tests/test_ontology.py::test_a_unit_whose_text_is_the_printed_lewis_collection_heading_gets_the_collection_code`).
  Its one source is the spec's dated line
  (`tests/test_ontology.py::test_the_lewis_notation_names_the_specs_dated_line_as_its_source_and_the_loader_needs_it`).
- **What it covers**: this heading only. No other printed heading is ruled
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:332` (`The answer covers this heading only`)).
- **Which runs it reaches**: the spec records that the file carries the ruling on the units path
  only (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:332` (`on the units path only`)). The experts now research every run on the units
  path (see "Units path" above), and every expert's instructions carry the ontology's text, its
  notations included
  (`src/specimen_digitization/field_research/prompts/__init__.py:65-67` (`from specimen_digitization.ontology import render`);
  `tests/test_ontology.py::test_the_first_pass_text_keeps_what_cuts_and_reads_a_unit_and_leaves_out_what_writes_a_value`).
  So the ruling reaches every run the experts research.
  "LEWIS", "COLLECTION", "LEWIS COLLECTIONS" and "Siphonaptera of Utah" get no field and no reading
  (`tests/test_ontology.py::test_no_other_printed_heading_is_ruled`).

The file also names two of the owner's decisions that are held. While D4 is held, no check uses a
taxon's regional occurrence (`specimen.yaml:1289` (`decision D4`)). While D5 is held, terrain takes
no part in the feet rule (`specimen.yaml:940` (`decision D5`)). Its header also
records the owner's message of 2026-11-14 that led version 2.0 to resolve the open meanings from
sources instead of putting them to him as questions. Read it there, in his exact words
(`specimen.yaml:34-38` (`Version 2.0 also resolves the meanings`);
`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:334` (`Siphonaptera of Utah`)).

## Open questions

These are not answered. A unit holding an open question carries no field and no reading.

The context and the status are the file's words.

| Question | The label writes | The question | Context | Status | In the file |
|---|---|---|---|---|---|
| `p_code` | `P-95-81-16` | What is "P-95-81-16", and does it fill a field? | One reader of label e98a924c-L2 writes it on a line of its own; over 12 recorded runs the first pass judged it uncertain in 7, reader A in 3 and neither in 2. The spec's worked example reads it as a code. | No source settles it (WP 2.1, 2026-11-14): it has neither form of a slide code, the catalogue number check takes five to nine digits only, and no reading marks it as a collection code; the pilot truth holds it in no field. Reported to the coordinator, not put to the owner. | `specimen.yaml:671-682` (`id: p_code`) |

- **"P-95-81-16"**: a unit that holds it carries no field and no reading
  (`tests/test_ontology.py::test_the_one_open_unit_is_the_files_only_question_and_carries_nothing_else`).
- **Other printed headings, such as "Siphonaptera of Utah"**: whether they are collection codes is
  not ruled, and the file has no entry for them
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:334` (`Siphonaptera of Utah`);
  `tests/test_ontology.py::test_no_other_printed_heading_is_ruled`).

**Resolved since version 1.0.** In version 1.0, "CNHM.", "Sp.30 ♀" and "P-95-81-16" carried no
field, waiting for the owner's reading (`docs/execution/units/PLAN.md:111` (`1.0 Ontology v1`)).
Version 2.0 resolved the first two from sources
(`specimen.yaml:601-607` (`Meanings version 1.0 left open`)):

- "CNHM." is the Chicago Natural History Museum, the institution, never a collector, with no field
  of its own. On a locality line it is part of the precise location as written
  (`specimen.yaml:608-613` (`id: cnhm`);
  `tests/test_ontology.py::test_cnhm_is_the_institution_and_on_a_locality_line_part_of_the_precise_location`).
- "Sp.30" is a morphocode, a species number, and its field is Taxon: after a genus it is a
  genus-level identification, and with no genus on any label it names no scientific taxon. "♀" is
  the specimen's sex, which none of the 20 fields holds (`specimen.yaml:621-624` (`id: species_number`);
  `specimen.yaml:646-649` (`id: female_sign`);
  `tests/test_ontology.py::test_the_resolved_meanings_name_their_sources_and_carry_their_fields`).

"P-95-81-16" stays open.

## The rules

The rules are the relations and checks between the things and the fields
(`specimen.yaml:696-701` (`The rules (version 2.0)`)). Each says how it is checked today: by
code, by a model, or not yet. "code" means its statement is something today's code guarantees,
and tests pin it. Today all 17 rules are checked by code
(`tests/test_ontology.py::test_the_file_holds_the_specs_rules_each_checked_as_stated`).

Each rule also carries an instruction, what a model does under it. A field's expert receives the
rules that name its field. The readers and the first pass receive the rules about reading a label.
The organiser receives every rule
(`specimen.yaml:703-709` (`WP 2.2 puts the rules into the models' instructions`);
`ontology/__init__.py:264-279` (`def render_instructions`);
`tests/test_ontology.py::test_each_model_receives_the_rules_that_concern_it_and_no_other`).

| Rule | Checked by | Fields | What it says | In the file |
|---|---|---|---|---|
| `one_collecting_event` | code | Country, Province/State, County, City, Precise Location, Date Visited From, Date Visited To | A specimen has one collecting event. When two of its labels write two different collecting dates, or two place names that no source confirms as one place (letter case, accents, punctuation and unit words such as "Dept." aside), an answer that settles the field on one label's text is refused. | `specimen.yaml:711-717` (`id: one_collecting_event`) |
| `place_within_settled_places` | code | Province/State, County, City | When an answer is applied, a candidate is checked against the settled country and province, and a city against a settled county only for a near spelling. The check stage also marks for a person a place below the country, settled on a source record that names its parents, whose record and the settled country's record name two different nations by an identity both carry: different ISO 3166-1 codes, or, on Getty TGN records, a chain that ends at another nation's record. With the country Georgia settled, a county Fulton in the US state Georgia is marked. Between a province, a county and a city the check marks nothing: a place is inside a settled province when the province's record is among its record's parents, and otherwise the check abstains. A person's value is never marked. | `specimen.yaml:730-745` (`id: place_within_settled_places`) |
| `place_chain` | code | Country, Province/State, County, City | The places form one chain, country > province or state > county > city. The check stage marks for a person a place whose source record and a place settled above it name two different nations, by the same test as the rule above. Below the country, a place is in the chain when the settled place's record is among its record's parents, and otherwise the check abstains: a settled Coles County, then an exact "Chicago", is not marked. A person's value is never marked. | `specimen.yaml:787-801` (`id: place_chain`) |
| `date_order` | code | Date Visited From, Date Visited To, Date Identified | The collecting date is on or before the determination date, and the same day is allowed. Dates written at different precisions compare on the parts both have ("1946" and "1946-09-06" agree). A settled determination dated before the settled collecting date is marked for a person, with both dates listed. | `specimen.yaml:835-842` (`id: date_order`) |
| `day_month_order` | code | Date Visited From, Date Visited To, Date Identified | A numeric date whose two orders, day-month and month-day, give two different dates is never settled on either reading by the date check. | `specimen.yaml:855-858` (`id: day_month_order`) |
| `code_is_no_date` | code | Date Visited From, Date Visited To, Date Identified | Codes are never dates nor any part of them: a slide code such as "IV-29-68-4" beside the collecting date "IV-23-48" is no date. The date check gives no date for a text that any reading writes inside a slide code. A date that punctuation separates from a code beside it ("IV-23-48;IV-29-68-4") is still a date. | `specimen.yaml:869-879` (`id: code_is_no_date`) |
| `label_type_routing` | code | None | A label's type (locality, determination, code) and a unit's fields name the experts a unit is for, and never keep a field's expert from a unit. Every expert's request carries every label's readings whole and every unit with its fields, so a determination label that writes a locality reaches the locality expert. | `specimen.yaml:906-912` (`id: label_type_routing`) |
| `elevation_unit_feet` | code | Elevation From (m), Elevation To (m), Elevation From (ft), Elevation To (ft) | An elevation whose text writes no unit is read as feet only when the three conditions under "Values the system fills in" hold. Otherwise the field is unresolved: magnitude alone never decides. Terrain takes no part while the owner's decision D5 is held. | `specimen.yaml:926-940` (`id: elevation_unit_feet`) |
| `elevation_needs_a_unit` | code | Elevation From (m), Elevation To (m), Elevation From (ft), Elevation To (ft) | An answer that settles an elevation field on a number that one of its readings writes with no unit anywhere in that reading is refused: a unit is never guessed from the magnitude, the place or a map. | `specimen.yaml:979-983` (`id: elevation_needs_a_unit`) |
| `elevation_unit_decides_field` | code | Elevation From (m), Elevation To (m), Elevation From (ft), Elevation To (ft) | An answer that settles an elevation field on a number that one of its readings writes in the other unit is refused. | `specimen.yaml:994-997` (`id: elevation_unit_decides_field`) |
| `place_parents_derived` | code | Country, Province/State, County | Upward derivation fills only open fields, as described under "Values the system fills in". A derived country is marked for a person when a place settled below it names another nation by an identity both carry, unless a person kept the country: then the place below it is marked instead. A derived province or county is never marked. | `specimen.yaml:1008-1022` (`id: place_parents_derived`) |
| `elevation_conversion` | code | Elevation From (m), Elevation To (m), Elevation From (ft), Elevation To (ft) | A derived elevation is a stated one copied to the other end of its unit, or its exact conversion (1 ft = 0.3048 m) rounded to the hundredth. A derived elevation never replaces a stated one. | `specimen.yaml:1051-1063` (`id: elevation_conversion`) |
| `end_date_from_one_date` | code | Date Visited To | A derived Date Visited To is the date of a settled Date Visited From, at its precision, and is never derived from a written range. | `specimen.yaml:1076-1085` (`id: end_date_from_one_date`) |
| `precise_location_extent` | code | Precise Location | The file gives the rule's meaning: Precise Location is the label's locality as written, every line of its locality text, with its line breaks, the higher places and an elevation written among those lines included. It is never cut to the first line, and a label whose locality names nothing finer than its town, or than its country, still has one (`specimen.yaml:1125-1130` (`The rule's meaning`)). Code marks for a person, as cut short, a precise location whose text writes no settled province or country and that, in every reading of its label, ends a line just before a line continuing the locality with a settled province or country that no other settled field's text holds. That next line may hold nothing else but other settled fields' texts, place unit words and punctuation. A precise location a person decided is never marked. So "E. slope Mt. McKinley" before the line "Davao Prov. near Mati" is not marked (`tests/field_research/test_elevations_and_extent.py:880` (`Davao Prov. near Mati`); `tests/field_research/test_elevations_and_extent.py::test_the_next_line_marks_only_as_the_locality_going_on`). Code never clears as not on the label a precise location that names nothing finer than its town or its country. One that holds an elevation settles only when its elevation text is the literal an elevation field settled from that label. | `specimen.yaml:1104-1116` (`id: precise_location_extent`) |
| `taxon_in_collection_scope` | code | Taxon | Field research settles a taxon only inside the collection's higher taxon, class Insecta, and only on GBIF's decision. A name whose every exact record lies outside Insecta ("Cynomys", "Citellus" and "Thomomys", genera of Mammalia) is never settled as the specimen's taxon. When another exact record of the name in Insecta has another authorship, as for "Epipsocus", there is no decision. A person reviewing the record may still choose any of GBIF's candidates. | `specimen.yaml:1184-1198` (`id: taxon_in_collection_scope`) |
| `host_is_no_taxon` | code | Taxon | A name a label writes after a host marker ("Host Thomomys", "Ex. Canis familiaris", "ex Peromyscus leucopus", "from nest of Formica rufa") is the host the specimen was taken from or a taxon associated with it, Darwin Core's associatedTaxa, and is not taken as the specimen's scientificName. A word that only ends in a marker ("Mex.", "Upon") is no marker, and a name before the marker ("Aus bus" in "Aus bus on Quercus") is no host. | `specimen.yaml:1221-1234` (`id: host_is_no_taxon`) |
| `parts_on_different_labels` | code | Taxon, Date Visited From, Date Visited To, Date Identified | A field's value is stored as one text from the labels until values stored as parts exist. When the parts of one field are on different labels (a name's genus on one and its species on another; a date's day and month on one and its year on another) and no one label holds them all, an answer that settles the field on one label's part does not settle it. The field is left ambiguous, with each label's part as an option, and is marked for review on each label that writes a part. | `specimen.yaml:1247-1268` (`id: parts_on_different_labels`) |

**Not a rule.** The file records one statement that is not a rule, and no check uses it: "A
taxon's regional occurrence is not a rule: that an authority records no occurrence of a taxon in a
region does not make it impossible there, and no check uses occurrence while the owner's decision
D4 is held." (`specimen.yaml:1285-1289` (`id: taxon_regional_occurrence`)).

For engineers: each rule checked by code names its tests in `tests/test_ontology.py`
(`CODE_RULE_TESTS`), one to one, and
`tests/test_ontology.py::test_every_rule_checked_by_code_names_its_tests_one_to_one_and_each_test_exists`
fails when a rule checked by code has none. The rules' own text, which no model receives, is
pinned by `tests/test_ontology.py::test_the_rules_rendered_text_is_pinned`.

## Reference tables in the file

- **Highest points**: each country's highest point and its elevation, from Wikidata, retrieved on
  2026-11-14, one row per country the query returns. Code reads it for the feet rule, and no
  model's text carries it
  (`specimen.yaml:1296-1305` (`Each country's highest point and its elevation, from Wikidata`)).
  The Philippines' row is Mount Apo, 2954 m
  (`specimen.yaml:1464` (`point_name: "Mount Apo"`);
  `tests/test_ontology.py::test_the_philippines_highest_point_is_mount_apo_at_2954_metres`).
  The table has 202 rows
  (`tests/test_ontology.py::test_the_highest_point_table_is_cited_once_with_its_query_and_has_one_row_per_country`).
- **The code's own notation tables**: the unit words of a place's name, the spellings of the
  elevation units, the words and signs that join a range, and the date notations. Each is pinned
  equal to the table the code reads
  (`specimen.yaml:1527-1606` (`The code's own notation tables`);
  `tests/test_ontology.py::test_the_codes_notation_tables_are_the_files`). The ontology's rendered
  text carries none of them (`tests/test_ontology.py::test_no_rendered_text_carries_the_code_tables`).
  The experts' brief builds two of its own lines in code: what joins a range, from the code's range
  words and signs, which the file's range table equals; and the elevation units, from a separate list
  of unit spellings as a label shows them (`SHOWN_UNITS`). The file says the brief renders these lines
  from the code's tables (`specimen.yaml:353-356` (`The label notations and every reading each allows`);
  `src/specimen_digitization/field_research/written.py:965-994` (`SHOWN_UNITS = {`);
  `src/specimen_digitization/field_research/prompts/__init__.py:60-63` (`range_line()`)).

## Keeping this page right

`tests/test_ontology_curator_doc.py` reads this page and the file. It fails when:

- a table that copies the file differs from it, in the file's order: the things; the fields (key,
  display name, Darwin Core term, what it holds); the notations (forms, fields, and the meaning
  cell built from the readings, the note and the optional final period); the notation sources; the
  routing entries (unit, fields, meaning); the questions (question, context, status); the rules
  (check and fields);
- the "Filled from other fields" column misses a derivation rule the file gives a field;
- an example unit's fields differ from what the file gives it;
- the text of a line or range of `specimen.yaml` that this page cites changes. The test keeps a
  fingerprint of each cited range and names the page lines to re-read. When the text has only moved,
  it says where it now sits;
- a cited file or line does not exist, a cited line no longer holds the text in brackets after it,
  or a cited test does not exist.

When the file changes, change this page with it, in the same pull request.
