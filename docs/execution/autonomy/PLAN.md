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

## 2. The plan the coordinator put to the owner (his answer: "Yes, go ahead"; the items are the coordinator's words)

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
fields already on the not-on-the-label list (C1, C4a, C4b and C4c wait: section 4).

## 4. Work packages

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| S1 rule mechanics (this pull request) | Three things, after three review rounds. **C3, the strict duplicate**: a label whose every drawn field already has a review reason of its own (held or marked) is not also `unresolved_transcription`, as a person is sent to each of those fields anyway; a drawn field without one (a field cleared as not on the label, or waiting for its source, among them) keeps the label's reason, as does every label no field is drawn from (both as on main). **C4d**: an expert whose request its sources' answers made too long answers once more, without tools, on the run so far with each lookup result shortened to what an answer cites (the checks read the answers the expert received, untouched); a first request over the bound still fails as `input_too_large`. **Guard**: a record whose fields that describe the specimen (the catalogue number, the collection code and the determiner's IRN aside) are all settled with no value gets `no_specimen_value` and never finishes without a person; a field still open is held by its own reason instead. | `field_research/step.py` (`scientific_reasons`), `experts.py`, the app's `blockers.dart` (the reason's words) | Fail-first tests per change, with the cases that stay held; no existing test changed; a replay with the real code over the 120 stored specimen-runs: pilot values newly cleared wrong 0. Not in scope: any prompt, "P.I." storage, Verbatim D/T/S, the taxon (C2), the marks (C6), one-reader labels (C5), the app beyond the reason's words |
| C4a, a place name over a line break (not shipped) | A place value field's literal read over one line break ("Davao\nProv.," for "Davao Prov.,"). **Waits for the independent image check and the 100-slide truth set**, where a gain and an error rate can be measured; on stored data it was proven only up to the literal check (5 refused answers passed it). | `agreement.py` (`written_runs`, `across_lines`, `literal_basis`) | Codex's rounds 1 and 2 on #451: both readers write "leg. J. New" over "York", the organiser gives the collectors "J. New", and a city "New\nYork" (value "New York") must stay held, also where a unit wrongly names the city for the collector's surname, or one unit over the two lines names only the precise location (the first pass's unit fields are advice, not proof). |
| C4c, a place inside the country settled from another reading (not shipped) | A place below the country settling inside the record's country settled from another reading of its label, where its own reading spells the country otherwise (105526596's "Costa R.ica"). **Waits for the independent image check and the 100-slide truth set**; on stored data it was proven only by unit tests. | `step._misfit` | Codex's rounds 1 and 2 on #451, the cases any later attempt must hold: reader A "United States", reader B "France" over "Paris" (the country settled from A); "Iran" against "Iraq" and "P.R.C." against "D.R.C.", one letter apart but other nations; a country conflict found on the label only after the place was checked; a country marked on another label of the record. |
| C1 on the listed fields (waits) | The coordinator's rule change 1 ("blank as an answer") on the fields already on `contracts.NOT_ON_LABEL`: the field's own expert's `label_lacks_value` clearing it although the organiser offered text for it. **Waits for the larger truth set.** | `field_research/step.py` (`mark_not_on_label`, condition 5) | Coordinator's ruling of 2026-11-17 on PR #451: no existing safety pin is loosened. The tests that pin a wrong expert answer as held (the keyed lines "county: Cook" and Date Identified, "Lee" as a county, the city "Mt. Apo", the habitat "trap" and "trap, cloud forest") must stay held, so the organiser's text keeps refusing the absence whenever nothing the code already establishes explains why that text is not the field's value. Rule A's condition 5 already absents every text so explained, so a C1 that keeps every pin releases nothing on the stored runs. Measured on S1's first head (C1 as the expert's word plus readers that agree): 6, 4, 3 and 8 absences released (r1/pair, r2/pair, r1/three, r2/three), each judged true by reading the label except 105526487's habitat beside "PRAIRIE DOG", now known to be wrong (lane M0, 2026-11-17: a bare animal name on a label is the host and belongs in Habitat). |
| C4b, a precise location keeping its elevation (waits) | A precise location that keeps an elevation whose number its elevation field settled ("4800" beside "Yepocapa, 4800ft."). **Waits for the precise-location extent fix (V1)**: values first, then the hold. | `agreement.elevation_settled_inside`, `step._keeps_an_elevation`, the extent rule's statement | G51's round 1 on #451: on main this refusal is the only standing hold on an elevation-bearing locality, and with it lifted a cut locality clears with no mark. V1 must first pass these two, on 105526326's label (readers alike, country, province and the elevation "3300" settled): the answer "E. slope Mt. McKinley\nDavao, Prov. 3300'" (dropping "Mindanao, P.I.") and the answer "Davao, Prov. 3300'" alone are each held or marked, never cleared. A measurement gap V1 must close: the frozen scorer counts a precise location within its similarity bound (`score.py:98-100`, 0.85) as right, so a cut locality scores cleared right, and "0 newly cleared wrong" cannot see this class. Measured on S1's earlier heads: 105526326 and 105526329 cleared right (pair arm) and 105526326 marked right (three arm). |
| C3's undrawn-label half (dropped) | A label no field is drawn from held only while a field the organiser found text for on it is held. | | G51's round 1 on #451: unreachable on real organiser rows (a candidate exists only through a row its field cites, and that citation makes the label drawn; 0 of 12 undrawn open labels in the stored runs have organiser text); its only test simulated the lookup. The undrawn-label rule stays as on main. |
| C3's not-on-the-label release (dropped) | A drawn field cleared as not on the label, or waiting for a held source, no longer holding its label. | | G51's round 1 on #451: on one label whose readers differ ("Malaise trap" against "Malaise trep", left out or capitals; "Cook Co." against "Cock Co."; "Chicago" against "Chicaqo"), with the county, city or method cleared as not on the label against an organiser text, the label's reason was the one hold, and the head cleared the record (7 of 7; main held). The step cannot tell from its data whether a reader difference touches the text an absence was reached against, so the release is dropped and these cases are tests that stay held. |
| A1 who cleared a record (PR #450) | The coordinator's rule change 3, its first part: the specimen list, detail, workspace and decision responses carry additive `cleared_by` (`person`, `system` or null), derived on each read from the stored `run.human_approved`; the app shows "Approved by a person" (green) and "Cleared by system" (the model treatment), and a cleared record whose server does not say stays "Cleared", not green. A standing approval is withdrawn by a person's later decision on the record (a field, transcription, authority, taxonomy, metadata or research-candidate decision), whether or not it changes a value, as before this change; and by the value test, wherever a disposition is decided, when the values differ from those recorded at the approval. A system step that leaves the values as approved (a retry, resume, recovery, reconcile or reassessment, or research that writes the same values again) keeps it. `approve` records the digest (`run.approved_values_sha256`) and `lane.settle_approval` applies the value test; an approval with no digest (before this change) stands. Follow-up: tell the reviewer why the record still waits after approving, when the approval's own finalize derives a value and withdraws it. Not in scope: which records clear, the audit sample, showing a reviewer only the open fields, queue sorting or new tabs. | `application/lane.py`, `api.py`, `search.py`, `domain.py` (one optional key), `policy.py`, `field_research/step.py`, the research harness's two canonical materializations, the `SpecimenSearch` view and `SearchSpecimens` (one nullable last column), the app's `specimen_status.dart`, `models.dart`, the queue row, the record screen and the glossary, design 02, 03 and 09, CONTRACTS.md, DATA_SEARCH.md | Fail-first tests per change: the field on both list paths and the detail; an approval ended by each writer that changes a value (research after a retry, resume or reassessment, the drain's recovery, a derivation in the recheck, a person's edit) and kept by a retry, resume or reconcile that changes none, by research writing the identical value, and when it has no digest; widget tests for each chip; no golden changed. Residual risk stated in CONTRACTS.md: a stored non-boolean, which no writer produces, reads null on the list and the model's coercion on the detail (production, read-only, 2026-11-17: 33 of 33 snapshots hold a JSON boolean). |
| V2b the catalogue number from the slide's QR code | An engineering change (the owner has not ruled on the barcode). The segment step decodes the slide's QR code once (zxing-cpp 3.1.1, QR Code Model 2 only, exactly seven digits, one payload on every rung of a fixed ladder; never fails the step) and stores an accepted decode as one evidence row. Field research compares the code with `fmnh_ins_number`'s settled value, after the expert's answer, and changes no value layer. It confirms (no text_only mark) when all three hold: the value's literal writes the code whole (on its letters and numbers alone, no numeric character beside the seven digits); a reading of the code's label holds that literal at an occurrence with no number beside it; the value's parsed and normalized layers are supported without the code. A value whose literal does not write the code whole stays and is held (`marked:fmnh_ins_number:<label>:barcode_differs`, worded in the app). Otherwise, an open field or a person's transcript on any label included, nothing changes. An exception inside the comparison is logged and the field is put back. **Breaking a tie on the code is not shipped**: any later attempt must hold Codex's cases on #452 (a candidate clipped from a longer number, a Unicode or superscript digit beside the code, an invisible separator, a date joined across a line break, a spaced number that made research fail), and should compare the code with the first pass's reading units for the catalogue number (a whole unit's text), not search the raw text. | `application/barcode.py`, `workflow.py` (segment), `field_research/catalogue_code.py`, `step.apply_outcomes`, `pyproject.toml`, `uv.lock`, the app's `blockers.dart` and `settlement_codes.dart` (the new reason's words) | Lane V2's measurement (98 of 100 real slides decoded, all equal to the truth, none wrong; none wrong in 300,000 damaged synthetic codes); this wrapper decodes 97 of 100, all equal to the truth. Fail-first tests per rule; a run with no code row and every other field settle as before. Replay over wp26's 120 specimen-runs: catalogue numbers newly wrong 0, 104 values confirmed, the two wrong clearances of 105526487 now held, open fields left open, `marked:fmnh_ins_number` on 0 to 2 specimens a run (from 6 to 10). Not in scope: the expert's brief, any other field, any other review rule. Residual risk: a slide whose QR code holds seven digits that are not its catalogue number (another institution's code) would hold a correctly settled number (`barcode_differs`); and where the readers also wrote the code's digits as the number, it confirms that wrong number (removing a text_only or conflict mark). This is the stated residual risk; none of the 100 truth slides carries such a code. |
| F1 the fields' second opinion | An engineering change (the owner has not ruled on it or its model); its structure is the coordinator's ruling of 2026-11-18 after two review rounds. **Its own workflow step** `field_second_opinion`, after field research has completed for the run (its step or recheck finalized it: no retryable research failure pending) and before the record is finalized: the run waits at that stage with no disposition; the step has a paid step's lifecycle (a reservation of one request's cap, USD 0.06, checked against the run's ceiling, limits, monthly caps and the program's allowance; an intent with a lease and an attempt; a deadline; a settlement). One request to Muse Spark Open 816B on Baseten (route `second-opinion-muse-spark`, priced in the published price list): the label crops, the readers' texts and the fields benchmark's instruction, never the pipeline's fields; the answer must satisfy the tool schema field by field (all 20 fields, each `{value, evidence}`), else it is malformed. **Its failure never blocks the run**: switched off, attempts used, a run limit, money, a provider error (HTTP 402 included), a timeout, a malformed answer or any exception ends it "not obtained" and the record is finalized in the same save with research's stage and blocker; a lost outcome (worker deadline, crash, the save failing) is found after the lease, held in full and finalized. **One stored result** `Run.second_opinion` (optional, omitted while unset): the status, each judged field's compared value, the second opinion's value and text and the verdict, and the answer inline; no finding, mark, evidence row or field is written. **Marks derived at every finalize** (`step.finalize_fields`): `marked:<field>:<label>:second_opinion_differs` where the recorded verdict for the field's current value differs, `..._not_checked` where there is none; nothing where it agrees, for the catalogue number, the IRN, an open or blank field, a field another rule marks, or a field a person holds authority over (decided at the endpoint, `Run.person_decided_fields`; carried; locked; a person's transcript; reassessment-protected). Legacy decisions are adopted once at load from the review audit; a history restore returns the revision's own result and list. On main every mark holds the record, so a record that would clear on main is held until its second opinion is obtained and agrees. | `application/second_opinion_step.py`, `application/workflow.py` (the step's registration), `field_research/second_opinion.py`, `prompts/second_opinion.txt`, `step.py` (one line in `finalize_fields`), `research_harness/workflow_bridge.py`, `active_graph.py` (adoption at load), `api.py` (decided), `domain.py` (two optional keys), `model_gateway.py`, `model_option.active_routes`, `profiles/published.json` (price row), the app's `blockers.dart` and `settlement_codes.dart` | The fields benchmark (2026-11-18, 67 slides answered by Muse Spark): on the cleared records the base pipeline's 355 unmarked values held 39 wrong, the 299 agreed 5; with the r3 readers 336 and 33, agreed 280 and 2. This code's replay of the same stored answers: base 273 still shown, 4 wrong (9 with the locality compared exactly), 60 differ (35 wrong), 22 not checked (four answers refused as malformed, all right); r3 265 shown, 2 wrong (6 exact), 58 differ (31 wrong), 13 not checked; 95 % upper bound of wrong among shown near 3 %. Residual risk: a misreading both readers share and the second opinion copies (two dates of two slides); padding of crops over 40:1 not measured; a legacy decision followed by a restore before it is adopted again (production holds none). |

### S1's replay (free, real code, wp26's 120 specimen-runs)

Each stored Run was loaded and, on a copy, `mark_not_on_label` rerun on the captured outcomes (main's rule
A, unchanged) and `finalize_fields` called (C3, the guard). On main 49474f94 the same replay reproduces
every stored reason. Pilot cells by the frozen scorer (`tests/reference/units_program/score.py`).

| run | finished | reasons removed | reasons added | pilot cells moved |
|---|---|---|---|---|
| r1/pair | 0 of 30 | 3 unresolved_transcription | 1 no_specimen_value | 0 |
| r2/pair | 0 of 30 | 2 unresolved_transcription | 1 no_specimen_value | 0 |
| r1/three | 0 of 30 | 2 unresolved_transcription | 1 no_specimen_value | 0 |
| r2/three | 0 of 30 | 3 unresolved_transcription | 1 no_specimen_value | 0 |

Each label reason removed is on a label every field drawn from which keeps a reason of its own, so the
record still sends a person to each of them. 105526321's label (readers "Werner" against "Wermer" on
the collector) keeps its reason in every run. `no_specimen_value` falls on 105526335 in every run, whose
described fields are all settled absent (it was already held). 105526487's habitat stays held, as on
main.

C4d acts inside the expert, on messages the stored rows do not keep: it is proven by unit tests
alone (and by G51's runs of it on #451).
