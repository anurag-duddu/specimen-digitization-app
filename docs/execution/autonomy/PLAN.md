# Autonomy program: more records finish without a person, with no loss of trust

Started 2026-11-17. Coordinator: Claude Code session f9614090 (desktop app, repository root). The
program's off-repo state is `~/specimen-golive/autonomy-program/PROGRAM.md`; this file is its record
in the repository.

## 1. Authority

The owner typed these on 2026-11-17 in session f9614090. They are quoted exactly.

- "Why do I still see the same? cleared vs needs review? theres a weird tendency to keep everything in
  review. I don't understand it. If we are able to identify and settle them confidently, why do they
  need to go?"
- "bring up the level of autonomy of our app, we should be confident in our approach and build our
  harness, agents, VLMs and end to end pipeline in such a way that we dont overly miss out on autonomy
  but it is important to not make mistakes because people wont trust it. before you write a single line
  of code, tell me what you would do"
- To the coordinator's question "Go ahead with the plan, including the three rule changes?" he typed:
  "Yes, go ahead"

The three rule changes, in the words the coordinator put to him. His "Yes, go ahead" covers these and
nothing wider:

1. "Blank as an answer. The requirements say cleared needs 'a supported non-empty value for every
   profile-specific mandatory field'." Condition stated to him: "Blank becomes an answer when both
   readers read the whole label cleanly and the expert says the field is not there."
2. "Agreed and checked values clear. The requirements say 'never clear on agreement alone'." Condition
   stated to him: "Add an independent check that looks at the label image and tries to disprove the
   value. A field type clears on its own only after that check is measured accurate for it on the truth
   set; until then it stays marked."
3. "'Cleared by the system' in the app. The design says 'Green means a human affirmed it.'" Stated to
   him: "Add 'cleared by the system' next to 'approved by a person', show a reviewer only the one to
   three open fields on a held record, and sample a few machine-cleared records for audit so trust
   keeps being measured."

Also stated to him, and so binding on every work package: "Each step is measured on the truth set
before it ships, and a step that raises wrong cleared values does not ship."

The truth set, typed by the owner later on 2026-11-17 in the same session, to the coordinator's "who
confirms the 100 truth slides": "I think use another adverserial agent to go through he 100. I can step
in as needed."

**Not decided by the owner** (no work package may say he decided these): the trust bar (the
coordinator's proposal is at most 1 wrong value per 100 cleared); any budget. No paid model run is
approved for this program: work packages do free work only (stored runs, replays, code, tests), and
one that needs a paid run stops and reports its cost to the coordinator.

Earlier owner words that still bind:

- 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything
  at the user it is to help by being in in autonomy as much as possible." and "Harness needs to work
  and do its magic"
- 2026-10-09: "I think our harness is not about only being strict, its about the process of figuring it
  out given the data at hand."
- 2026-09-23 (G1): "When I say something that harness was able to resolve is cleared it is cleared"

The reading-units program's rule of order applies to every package: first make the values right, then
lift the hold that guards them.

## 2. The approved plan (the owner's view of it)

0. Yardstick: the truth set from 10 slides to about 100; two numbers on every change: the share of
   specimens finished without a person, and wrong values among the cleared ones.
1. Stop holding records for things that are not doubt: blank as an answer; a taxon label with only a
   species code stored as written and cleared; the duplicate "readers differ" hold removed; mechanical
   refusals fixed (line breaks, "too long to check", the country-first chain).
2. Agreed values clear once an independent image check is measured accurate for that field type.
3. The harness settles more of the truly open fields (a second reading for a one-reader label,
   one-character differences from the image, abbreviations such as "P.I." and "Ida.").
4. The app shows "cleared by the system" beside "approved by a person"; a reviewer sees only the open
   fields; an audit sample of machine-cleared records.
5. The 33 production records are run again after each step.

## 3. Evidence at the start: the free replay R0

R0 (off-repo, `~/specimen-golive/autonomy-program/R0/report.md`) replayed the last full test
(`~/specimen-golive/runs/units-wp26-20261115/`, frozen code d83f4d6f1, four runs of 30 specimens) and
measured what each candidate change frees and risks. Its replay is exact: 1,104 of 1,104 stored
reasons and 120 of 120 dispositions, on the frozen code and on main 49474f94.

Headline: no combination of changes that keeps every pilot value right finishes a specimen. The safe
stack frees 0 of 30 specimens in every run and moves 56 pilot cells to cleared right and 0 to cleared
wrong. Every specimen any change finishes carries a wrong or contested value ("P.I." stored as the
parsed country is 15 of the 20 cleared-wrong cells). After every change, what holds specimens is real
doubt. R0's "safe now" items are C3 (the duplicate label hold), C4 (mechanical refusals) and C1 on the
fields already on the not-on-the-label list.

## 4. Work packages

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| S1 rule mechanics (this pull request) | R0's safe items 1 to 3 and an empty-record guard. **C3**: a drawn field cleared as not on the label, or waiting for a held source, no longer makes its label `unresolved_transcription`; a label no field is drawn from, on which the organiser found text, holds only while one of those fields has a reason of its own (a label with no organiser text at all still holds, as WP 2.R left it). **C4a**: a place value field's literal may run over one line break ("Davao\nProv.," is "Davao Prov.,"). **C4b**: a precise location keeps an elevation whose number its elevation field settled ("4800" beside "Yepocapa, 4800ft."), by the extent rule precise_location_extent, whose statement now says so. **C4c**: a place below the country settles inside the country settled from another reading of its label, where its own reading spells the country otherwise. **C4d**: an expert whose request its sources' answers made too long answers once more on the run so far, each lookup result shortened to what an answer cites. **C1** (rule change 1, the listed fields only, `contracts.NOT_ON_LABEL` unchanged): a listed field whose own expert answered `label_lacks_value`, the whole label read, clears as not on the label though the organiser offered text for it, when every reader of its label writes that text alike and, for a county, the text writes no county unit word; the precise location keeps its extent rule. **Guard**: a record none of whose fields that describe the specimen holds a value (the catalogue number, the collection code and the determiner's IRN aside: R0's 105526335, labels "FMNHINS 4486770" and "LEWIS COLLECTION / col") gets `no_specimen_value` and never finishes without a person. | `field_research/step.py`, `agreement.py`, `experts.py`, `ontology/specimen.yaml`, the app's `blockers.dart` (the reason's words) | Fail-first tests per sub-change, with the cases that stay held; a replay with the real code over the 120 stored specimen-runs: pilot values newly cleared wrong 0. Not in scope: any prompt, "P.I." storage, Verbatim D/T/S, the taxon (C2), the marks (C6), one-reader labels (C5), the app beyond the reason's words |

### S1's replay (free, real code, wp26's 120 specimen-runs)

Each stored Run was loaded and, on a copy, the precise location's captured outcome reapplied where it
had been refused for its elevation (C4b), `mark_not_on_label` rerun on the captured outcomes (C1) and
`finalize_fields` called (C3, the guard). On main 49474f94 the same replay reproduces every stored
reason. Pilot cells by the frozen scorer (`tests/reference/units_program/score.py`).

| run | finished | reasons removed | reasons added | pilot newly cleared wrong | newly cleared right | left to marked |
|---|---|---|---|---|---|---|
| r1/pair | 0 of 30 | 8 mandatory_unresolved, 3 unresolved_transcription | 2 no_specimen_value | 0 | 2 | 0 |
| r2/pair | 0 of 30 | 5 mandatory_unresolved, 3 unresolved_transcription | 2 no_specimen_value | 0 | 1 | 0 |
| r1/three | 0 of 30 | 4 mandatory_unresolved | 1 marked, 1 no_specimen_value | 0 | 0 | 1 |
| r2/three | 0 of 30 | 10 mandatory_unresolved, 2 unresolved_transcription | 2 marked, 1 no_specimen_value | 0 | 0 | 1 |

The pilot cells that changed are all the precise location (C4b): 105526326 and 105526329 cleared right
on the pair arm (r1/pair both, r2/pair 105526329), 105526326 marked right (a conflict) on the three arm.
Cleared wrong stays 7, 5, 4 and 4, as R0's base. `no_specimen_value` falls on 105526335 in every run
and 105526461 on the pair arm, both already held. C1 releases 6, 4, 3 and 8 absences (collection
method, collection code, county, city, habitat), every one judged true by reading the label, except
105526487's habitat beside "PRAIRIE DOG" (r2/three), a host, whose convention is unruled.

Kept held by S1, narrower than R0's simulation:
- C4c settles a place only inside a country settled on the record. R0's wider form, any place a source
  confirmed, would lift the refusal of 105526359's city answer, "LOS ALAMOS Co." as the town Los Alamos,
  where the label writes no town, and of 105526459's city on the misread "AWellsville" (judged from the
  stored answers; not replayable); so 105526321 ("P.I."), 105526461
  (the heading "Siphonaptera of Utah"), 105526359 and 105526459 stay held.
- C3 keeps the reason of a label with no field drawn and no organiser text on it (R0's simulation kept
  these too; WP 2.R's inputs in `tests/field_research/test_review_rules.py`).
- C1 needs every reader of the organiser's text to write it alike, and a county's text to write no county
  unit word; the readers-differ and "Cook County" cases stay held.

C4a, C4c and C4d act inside the expert or on source answers the stored rows do not keep (the captured
outcomes carry no cited evidence ids, authority ids or options, and refused answers survive only as
text). C4a was replayed to the literal check only (5 refused answers now pass it); whether their place
then settles, and all of C4c and C4d, is unproven on stored data and is proven by unit tests alone.
