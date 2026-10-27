# The first pass's reading units and the specimen ontology

Status: the owner's design of 2026-10-26, written from his typed words of that day and revised on
2026-10-27 after the sixth reviews of pull request #418. The owner set the substance; the design
under his words is the engineer's. Nothing here is built. Every sentence about today names the
file and line that shows it in this branch's tree (paths under `src/specimen_digitization/` unless
another root is given; its `src/`, `tests/`, `scripts/` and `dataconnect/` are byte-identical to
main b2dcd50d6) or the recorded run under `~/specimen-golive/runs/`. Section 7 is the build order;
it is the same list as the plan's section 3 (`docs/execution/units/PLAN.md`). What a work package
builds and how is that package's choice, tested there; this document states the design and the
decisions.

## 1. The pipeline, in the owner's words

Each quotation is a contiguous part of one of his messages, copied as typed; his line breaks are
kept.

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

## 2. The design

- The readers (N) read every label. The first pass cuts each label's text into units at logical
  breaks, judges the image at each unit, and settles nothing.
- The field experts run in parallel as today, one per field, each with every unit, every raw
  reading, the organiser's candidates, its lookups and the ontology. One rule says what settles a
  field and whether the value is cleared or marked for a person (section 4).
- After every expert has answered, one check stage runs over the settled values: the place chain,
  the date order and the elevation unit. A failed check marks the field; an inference fills an open
  part, marked. Nothing else changes after the experts answer.
- The units path ships behind a switch, off by default. Each run records the path it started on
  and keeps it. The old path is deleted after the phase-1 gate and the production switch-on; a run
  reopened after that is moved to the units path (plan WP 1.8).
- A value made of parts on different labels is shown to a person now and stored once the record
  holds per-part values (section 4, "Parts on different labels").

## 3. The reading units

### Who cuts them, from what text

The first pass, for every label. Today it runs only for a label whose readers' texts differ
(`application/workflow.py:2068-2076`) and refuses fewer than two readings (`first_pass.py:404`).

The units always come from the label's current text source: a person's transcript when one is
present, else the machine readings. Any change of source regenerates them: a person's edit, a
second edit, or an abstention after an edit (which returns the label to its machine readings).
Today an edit updates the transcript and resumes the run at `parse` with no first pass
(`application/api.py:2176-2199`); an abstention carries null text (`:2168-2169`).

### What each unit holds

| Key | What it holds |
|---|---|
| `id` | `<label>:<n>`, n counting from 1 in reading order |
| `label`, `lines` | the label, and the first and last line the unit covers; a unit may cross a line ("E Slope Mt. / McKinley") |
| `readers` | for each reader, the text it wrote here and where: `{"A": {"text": "Elev.6400", "start": 68, "end": 77}, ...}` (reader A's text of the label below; B 68-78 with its mark, C 67-76); `start` and `end` are Python string indices into that reader's text (code points); a reader that wrote nothing here has `""` |
| `image` | what the first pass sees in the image at this unit: one reader's text, `uncertain`, or `not visible`. A judgement of the image, never a vote among readers: when the image is clear it names the text that matches it, even if one reader alone wrote it. Never a text no reader wrote |
| `means` | the first pass's own interpretation, which may be text no reader wrote: an expansion ("P.I." -> "Philippine Islands"), a normal form ("6-Sept-1946" -> 1946-09-06), a role ("leg." -> collected by; genus, species, author; day, month, year). May be empty. Never a literal |
| `role` | the part of a field's value this unit is, when it is one (genus, species, author; day, month, year); else empty |
| `fields` | the fields this unit could belong to, most likely first. Advice only: every expert receives every unit. May be empty |
| `note` | one short sentence when something matters (a mark only one reader saw) |

The app shows the units by converting the code-point offsets to UTF-16 (plan WP 1.6). No such
conversion exists today: `exactUtf16Span` takes UTF-16 offsets and slices
(`apps/specimen_digitization/lib/src/reading_alignment.dart:12-26`).

### What code checks on every answer

- Tiling: every character of every reading belongs to exactly one unit, in order; only whitespace
  lies between units.
- Range: a unit never ends inside a range. A range is a number or a date, a joiner (a hyphen, an en
  dash, "to", "bis", "au", "a"), then a number or a date of the same kind; a sign counts only before
  a digit at the start of a token; a letter-digit code ("1a2") and a line-end hyphen inside a word
  are not ranges. Today the range refusal applies to date and elevation fields only
  (`field_research/agreement.py:775-776`).
- An empty unit list is refused.
- An answer that fails is sent back once with the failed check named; one that fails twice is
  given up on, as today (`first_pass_given_up`, `first_pass.py:638-660`).

A given-up label, and a label with one reader, still gets units: from the alignment
(`reading_differences_among`), which today returns the differing spans only, drops a difference of
spacing alone and refuses one reading (`first_pass.py:196-213`, `:246-247`); plan WP 1.2 extends it
to return the agreed spans too (tokens at whitespace; each differing span one unit). Every such
unit's `image` is `uncertain`. A given-up label goes to review however its fields settle: today that
check sits inside the branch for an unresolved transcript (`field_research/step.py:3743-3751`), which
an agreed label never enters (`first_pass.py:671-673`); WP 1.3 moves it. A label with one reader is
not sent to review by this check, and a person's transcript (one reader) settles as the person's
text, as today (section 4, rule 2).

### One label, today and under this spec

Pilot label e98a924c-L2 (slide 105526322 of `tests/fixtures/field_model_pilot_rows.json`), three
readers (`~/specimen-golive/runs/three-readers-20261025/cases.json`):

- A: `CNHM. E Slope Mt. / McKinley, Davao Prov. / Mindanao, P.I. / 6-Sept-1946, Elev.6400 / H. Hoogstraal leg. / Shrubs, mostly forest / wings 4 head / Sp.30 ♀`
- B: the same with `Elev.6400'`, `Forest`, `Wings`, and an extra line `P-95-81-16`
- C: the same with `DavaoProv.`, `Mostly forst`, `Wings & head`, `♂`, no extra line

Over the 12 recorded three-reader runs (`fp_three_reps*.jsonl`) the first pass preferred no reader
in 9 and A in 3; at the foot mark it named A in 7, `uncertain` in 4, `neither` in 1; at the extra
line `uncertain` in 7, A in 3, `neither` in 2. In the 2026-10-25 harness runs
(`free-harness-20261025/results/`) the pair arm settled the elevation on readers agreeing on "6400"
with feet from B's mark, in both repeats; the three-reader arm settled it in neither.

Under this spec the first pass gives, among others:

| unit | readers | image | means | role | fields |
|---|---|---|---|---|---|
| CNHM. | A, B, C same | CNHM. | Chicago Natural History Museum, the Field Museum's name 1943-1966 | | none until the owner's reading (section 5) |
| E Slope Mt. McKinley (lines 1-2) | same | same | east slope of Mount McKinley | | precise_location |
| P.I. | same | same | Philippine Islands | | country |
| 6-Sept-1946 | same | same | 1946-09-06 | | date_visited_from |
| Elev.6400 / Elev.6400' | A "Elev.6400", B "Elev.6400'", C "Elev.6400" | "Elev.6400" or uncertain | elevation 6400, unit not certain from the image | | elevation_from_ft |
| H. Hoogstraal leg. | same | same | collected by H. Hoogstraal | | collectors |
| Sp.30 ♀ / ♂ | A, B "♀", C "♂" | ♀ | species number 30, female | | none until the owner's reading |
| P-95-81-16 | B only | uncertain | a code | | none until the owner's reading |

## 4. The harness

The experts stay as they are in shape: one per field, with lookups, all at once with one copy of
the other fields taken before any answers (`step.py:333-339`), outcomes applied after research
returns (`:4195-4210`). Two exceptions exist today and stay: `identified_by_irn` gets no model call
(`step.py:426-428`), and five fields have no lookup (collectors, collection code, habitat, collection
method, verbatim D/T/S: `field_research/contracts.py:47-51`). Each expert receives every unit, every
raw reading whole, the organiser's candidates as today (`experts.py:281-327`) and the ontology
rendered into its instructions.

### What settles a field: one rule

PRD v2 (`docs/product-requirements/PRD.md:667-670`): "A value is `unresolved` only when nothing
supports even an inference"; "On a conflict or a doubt, the harness fills in the best-supported
value and marks that part for a person"; and its risk row (`:1204`), "never clear on agreement
alone". The rule is written here once and the code follows it. For each field, on each label that
writes it:

1. The candidates are the texts the readers wrote at the unit, merged by today's `agreement_key`
   (letter case, spacing and Unicode form aside; `agreement.py:1200-1206`). Texts a source confirms
   as one authority (the same place, today `BY_SAME_PLACE`, `:1530-1533`) are one candidate. So are
   two texts of a place field that are one letter apart (`one_letter_apart`,
   `application/georef_locality.py:364-371`) when a source confirms one of them by its own name and
   rules out every other text of the field on that label, the other one included: a near spelling
   of a confirmed name (today `_preferred_spelling`, `:1346-1363`, reached only through `_by_source`,
   `:1518-1523`, which needs exactly one text confirmed and every other ruled out, `:1576-1582`).
   When a third reader's text is confirmed too (A "Chimaltenago", B "Chimaltenango", C "Escuintla",
   B and C both confirmed), nothing merges: B and C are two candidates with a SOURCE backing each,
   a conflict (rule 5). The merged candidate's literal is the text the image
   names, else the text the source confirmed exactly. Its value is the source's name. It has a
   SOURCE backing and, where the image names one of its texts, an IMAGE backing, so it is cleared
   (rule 4). Example, t1-329's province: the image names "Chimaltenago", TGN confirms
   "Chimaltenango": one candidate, literal "Chimaltenago", value "Chimaltenango", cleared (the test
   named in rule 5).
2. A transcript a person decided binds: that text settles, unmarked, and the rule ends (today
   `person_decided`, `:1406-1410`).
3. A candidate's backings are of three kinds. IMAGE: the first pass names its text at the unit.
   SOURCE: a source confirms it exactly, by its own name or expansion, and rules the others out
   (today `BY_SOURCE`, `:1223`); or it is a merged candidate of rule 1 (whose condition already
   rules every other text out); or it is a near spelling of
   a source's one candidate (today `BY_NEAR_SPELLING`, `:1576-1579`). A near spelling backs a text
   only when no reader's text is confirmed by its own name (`agreement.py:1563-1574`); with an
   exact match present, the merge of rule 1 applies instead. TEXT: two or more readers of this label
   wrote it; or another label of the specimen, on which two or more readers agree, writes it (today
   `BY_OTHER_LABEL`, `MIN_BACKING_READERS = 2`, `:1228`). This changes today's agreement:
   `BY_AGREEMENT` needs every reader of the label (`:1503-1508`, "Every reader writes it"), and
   another label backs a text only through `BY_AGREEMENT` (`:1536-1539`). Under the rule, A "P-95",
   B "P-95", C "P-93" gives "P-95" backed by readers agree (plan WP 1.3's test).
4. Exactly one candidate has a backing: it settles. It is CLEARED when it has an IMAGE or a SOURCE
   backing. With TEXT backings only, one or both, it settles MARKED. So the five tool-less fields
   clear when the image names the text, and settle marked on readers agreeing or on another label
   alone.
5. Two or more candidates have a backing: a conflict. When one of them has an IMAGE or a SOURCE
   backing, the field takes the best-backed candidate (SOURCE above IMAGE above TEXT; a tie broken
   by the number of readers that wrote it, then by reader order, A before B before C), MARKED, with
   the others listed. When none has (text against text), the field is `ambiguous` with the
   candidates as options, as today's `several_possibilities` (`step.py:1339-1342`). Today an
   exact source confirmation settles against an image-confirmed pick (`agreement.py:1515-1529`,
   `:1575-1582`), except that a pick one letter from the confirmed text stays the literal and the
   confirmed name is its value (rule 1; test
   `tests/field_research/test_first_pass_advice.py:614-645`); only the near-spelling and
   other-label branches refuse (`CONFLICT`, `agreement.py:1526`, `:1547`; `FIRST_PASS_CONFLICT`,
   `:1611-1618`). Under this rule a source against the image settles the source's text, marked,
   for texts that are not merged (different places). Merged texts are one candidate (rule 1).
6. No candidate has a backing: unresolved, with the candidates as options, unless the check stage
   infers a value (below).

The finding codes `first_pass_followed`, `first_pass_overridden`, `first_pass_absent` and
`first_pass_conflict` (`step.py:2385-2392`) are replaced by `cleared:<field>:<label>` and
`marked:<field>:<label>:<why>`. `first_pass_given_up` stays (section 3).

### Marked

Marked means: the field's value is set as today (state `supported`, with its literal and value,
`application/domain.py:262-266`) and the run carries a review finding `marked:<field>:<label>:<why>` whose detail lists the other
candidates. Today a finding never routes the record by itself (`RunFinding`,
`application/domain.py:320-322`); the disposition is review when the run has reasons
(`step.py:3927`). So WP 1.3 writes each `marked:` code into `run.reasons` too, and tests that the
disposition is `needs_human_review`. The `marked:` code joins the field-reason mapping of the review
summary (`application/review_summary.py:8-24`, applied at `:103-115`) and of the app's blockers
(`apps/specimen_digitization/lib/src/screens/workbench/blockers.dart:205-221`, applied at
`:387-398`), so a supported field with a marked finding is a field-targeted review item and counts
in field reviews (plan WP 1.3 and 1.6). Both take the whole text after the first colon as the field
today (`review_summary.py:106-109`; `blockers.dart:322`, `:388`), which for
`marked:habitat:L1:text_only` is `habitat:L1:text_only`, not a field. So each reads the field as the
first part after `marked:`. In this program a value's basis is written in its `reason`
("Basis: inferred, rule <id>"); a typed basis field waits for PRD v2's per-part model
(`PRD.md:614-622`).

### The check stage

After every expert has answered, one stage runs over the settled values, where today the place
order is applied and `derive.fill` runs (`step.py:2321-2357`):

- The place chain, country > province > county > city: a value outside the chain settled above it
  is marked. The apply-time refusal stays as today: `parents_refusal` (`agreement.py:2065-2089`)
  checks a candidate against the settled country and province, but a city against a settled county
  only for a near spelling: a settled Coles County, then an exact "Chicago" under Illinois, passes.
  The stage marks that, and the place chains that derivation fills (WP 2.3).
- The date order: a collecting date on or before the determination date, the same day allowed;
  partial dates compare on the parts both have ("1946" and "1946-09-06" agree; `domain.py:293`
  records precision). A date ambiguous between day and month is a conflict with both readings
  (today's `day_month_order_ambiguous` warning, `application/field_validators.py:137`).
- The elevation unit: a unit the cleared text does not write is inferred as feet only when (a) at
  least one reader wrote the foot mark or "ft" at this unit, (b) the number read as metres is above
  the cleared country's highest point (the Philippines: Mount Apo, 2,954 m; a table in the ontology
  file, from Wikidata, cited per row), and (c) the number read as feet is possible. The country must
  be cleared, not marked. Without (a) the field is unresolved: magnitude alone never decides, as
  today (`NO_UNIT`, `agreement.py:302`, `:822-825`). The rule takes effect after the owner's reading
  in plan WP 2.1. Terrain takes no part while D5 is held (`GEOREFERENCING.md:179`, the
  Measurements row: none while D5 is held).

A failed check marks the field. An inference fills an open part, marked, its `reason` naming the
rule. Upward derivation (a country from a settled province; `field_research/derive.py:43-49`,
`:66-74`) stays as today and fills only open fields. Nothing is revised after the experts answer
except by marking. Research is saved once, as today (`workflow.py:1151-1153`), and a retry reruns
the step as today; no deadline changes.

### Residual risks

Both exist today; the measurement reports wrongly cleared values and plan criterion 1 requires
them not to rise.

- The readers and the judge share one misreading: the label writes "P-95", two readers write
  "P-93", and the image judgement names "P-93". Cleared, wrong. Today the first pass's preferred
  reader's text settles its label when nothing backs another (`agreement.py:1219-1223`).
- A misread that is itself a real place: the readers write another real town, the image is
  uncertain, a gazetteer confirms the name and rejects the alternative. Cleared, wrong. Today
  `BY_SOURCE` (`agreement.py:1223`) does the same.
- The image judgement varies from run to run (the foot mark above: A in 7 of 12, `uncertain` in
  4, `neither` in 1). Plan criterion 2 measures its stability.

### Parts on different labels

The owner: "Bigger reason is data could be on two different labels but belong to the same field to
settle like taxa". Settling such a field needs a value stored as parts from different labels, each
with its own literal and basis. That storage is PRD v2's per-part model (`PRD.md:614-622`, the
four-group schema work), not this program. In this program: units carry a `role` (section 3); when
a field's parts are on different labels, the expert answers `several_possibilities` with the parts
named per label ("label 1 writes genus Aus; label 2 writes species bus"), marked for a person. The
owner sees it now; the assembled value is stored when per-part values exist. Today an answer holds
one literal (`contracts.py:229-232`) and only `precise_location` may cross lines (`ACROSS_LINES`,
`agreement.py:490`).

## 5. The conceptual model, as an ontology

The owner, 2026-10-26, three messages: "It’s not about location at all specimen level there is a
conceptual model that all models need to be aware of". "This is the ontological model that needs to
be baked in. So harness can connect the dots". "It may not exist the ontological conceptual model.
Needs to be built and baked in".

Darwin Core publishes a conceptual model of specimen data (dwc.tdwg.org/cm, version 2026-10-13):
the things, Event, Location, Material entity, Identification, Agent, Taxon, and the relationships
among them. It is the frame. The model of this collection's labels is one file in the repository,
readable by people and by code, rendered into every model's instructions: the readers, the first
pass, the organiser while it stays, and every expert. Rules code can check are checked by code.

| Thing | Examples on labels | Darwin Core |
|---|---|---|
| Specimen | the slide, its catalogue number, the institution that holds it | MaterialEntity; catalogNumber, institutionCode |
| Collecting event | one act of collecting: where, when, how, in what habitat | Event: eventDate, samplingProtocol, habitat; the collectors as recordedBy |
| Locality | the place of the event, in a chain country > province > county > city, with an elevation | dcterms:Location: locality, municipality, county, stateProvince, country, minimumElevationInMeters |
| Agent | a collector, an identifier | Agent; recordedBy, identifiedBy |
| Determination | a taxon name given to the specimen by a person on a date | Identification: identifiedBy, dateIdentified; the name as Taxon: scientificName |
| Taxon | the name, its rank, its accepted name | Taxon |
| Code | a slide or preparation code, a species number | ours: no Darwin Core term fits them |
| Label | a physical label; it carries attributes of the things above and has a type (locality, determination, code) | ours |

Version 1.0 (plan WP 1.0) holds no meaning the engineer invented: the things above; the profile's
20 fields with their Darwin Core names; the label notations moved from
`application/harness_knowledge/insects.py` (`NOTATIONS`, `:27-89`: "P.I.", "Prov.", "leg.", Roman
months, each with its readings and fields; test-only today, `tests/test_harness_knowledge.py` is
its only importer, and its docstring's claim that it is rendered into the harness's prompt,
`:7-9`, is not true today); and `fields` routing advice. The module is deleted at 1.0. What "CNHM."
is, where "Sp.30 ♀" goes and what "P-95-81-16" is are open questions for the owner's single reading
in WP 2.1; until then those units carry no field.

Version 2.0 (WP 2.1) adds the relations and the checks of section 4: one collecting event per
specimen (two labels with different localities or dates for it are a conflict); the place chain; the
date order; the elevation unit, with the highest-point table; codes are never dates nor any part of
them (t1-329 writes "IV-29-68-4" beside the collecting date "IV-23-48"); a label type routes units
to experts first and never excludes a field (every expert receives every unit); a taxon's regional
occurrence is not a rule (D4 is held, and absence from an authority is not impossibility,
`PRD.md:1207`). The owner and the collection's curators read the rules once, there.

Where the rules get their knowledge: the approved gazetteers for places (`contracts.py`,
`FIELD_TOOLS`); GBIF, Catalogue of Life and Global Names for taxon names; Wikidata for the
highest-point table; the institution's names and dates and the label conventions as a written table
in the file (phase 3). People: no approved source today (`docs/execution/golive/PLAN.md:782-794`
lists none); a people source is put to the owner with phase 1's measurement, never used before.

## 6. Today and the change

| Piece | Today | Under this spec |
|---|---|---|
| Scheduling | a first pass only for a label whose readers differ (`workflow.py:2068-2076`); refused below two readings (`first_pass.py:404`) | every label, from its current text source, one reading or more |
| First pass output | one preferred reader or none, a verdict per difference, notes (`FirstPassOutput`, `first_pass.py:290-301`) | the units, on the units path; with the switch off nothing changes; the pinned `FirstPassDecision` names no reading and its differences carry `uncertain` (today's path for an answer that never came, `first_pass.py:487-490`) |
| Transport | a child process returns `{"decision": ...}`; the parent validates `FirstPassDecision` (`application/model_runtime.py:90-99`, `:276-284`) | the child returns `{"decision": ..., "units": ...}`; the parent validates `ReadingUnits` and stores them on the run; `FirstPassDecision` untouched |
| The path a run takes | prompts, routes and configuration are pinned per run (`application/production.py:1418-1421`, `:1441-1449`); no first-pass path is | the run records its first-pass path when it starts; the experts follow the run's path, never the process switch |
| A person's edit | updates the transcript, resumes at `parse`, no first pass (`api.py:2176-2199`) | regenerates the label's units from its current text source |
| Organiser | proposes candidates quoted from whole readings, stored as evidence rows with offsets (`application/harness.py:123-166`) | kept; whether the production pipeline calls it is decided in plan WP 2.5 |
| What settles a field | readers agree (every reader); a source; a near spelling; one place; another label; the preferred reader's text; a person's text (`agreement.labels`, `:1366-1557`) | the rule of section 4: candidates, three kinds of backing, cleared or marked |
| The image guard | a near spelling or another label never overrides a text the first pass confirmed in the image; the conflict settles nothing (`confirmed_against_image`, `:1303`; `CONFLICT`, `:1526`, `:1547`) | the image is one backing; a conflict gives the best-backed value, marked, or `ambiguous` when none would clear |
| Checks and derivation | place parents checked at apply time (`parents_refusal`, `:2065-2089`); feet/metres, end date, parent places derived (`derive.py:66-91`) | the apply-time refusal stays; one check stage after the experts; a failed check marks; an inference fills an open part, marked; derivation as today |
| Review | several possibilities, or sources cannot resolve (`step.py:1339-1355`) | marked (a value with a review finding), `ambiguous` with options, or unresolved |

## 7. Build order

One list, in the spec's section 7 and the plan's section 3, one lane at a time. A gate is met or the
phase stops.

Phase 0: WP 0, the reference set, its truth, the scorer and the baseline.

Phase 1, the ontology's first version and the reading units: 1.0 ontology v1 (things, fields, the
label notations moved from `harness_knowledge`, `fields` advice; the module deleted) -> 1.1 unit
record, storage, Data Connect operation, projection field, API workspace route and app reader (data
release before runtime) -> 1.2 first pass v2 behind `SPECIMEN_FIRST_PASS_UNITS` (units for every
label, the tiling and range checks, the alignment's agreed spans, the new prompt variable, the
transport, the run's path pin, the ontology v1 in its prompt) -> 1.3 experts take units on the units
path (the settlement rule, marked, given-up labels, a person's edits, the ontology v1 in their
instructions) -> 1.4 organiser kept and measured -> 1.5 measurement (gate: criteria 1 and 2 met) ->
1.6 app shows the units -> 1.7 docs -> 1.8 switch on in production, then delete the old first pass,
its prompt variable, the switch and the unused field-harness prompt.

Phase 2, the ontology's second version: 2.1 relations and checks (the owner's and curators' one
reading) -> 2.2 the rules baked into every model's instructions, readers included -> 2.3 the check
stage (the place chain, the date order, the elevation unit, label types) -> 2.4 unit roles and the
per-label answer for parts on different labels -> 2.5 organiser decision -> 2.6 measurement (gate:
criteria 1 and 2 met) -> 2.7 docs.

Phase 3, people and conventions: 3.1 people lookups, only if the owner approves a source -> 3.2 the
conventions table -> 3.3 steady-state run (all three criteria met).

One lane runs at a time, in this order; a phase starts when the one before it has closed. Inside a
lane, two work packages that touch different files may run in parallel sessions in their own
worktrees (1.6 and 1.7; 2.1 and nothing else, since 2.2 to 2.5 read its file). The
`research_harness` package is out of this program's scope: it is kept as is, and a separate cleanup
program takes its inventory (the plan's section 5).
