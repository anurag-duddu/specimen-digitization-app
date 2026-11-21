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
| S1 rule mechanics (this pull request) | Three things, after three review rounds. **C3, the strict duplicate**: a label whose every drawn field already has a review reason of its own (held or marked) is not also `unresolved_transcription`, as a person is sent to each of those fields anyway; a drawn field without one (a field cleared as not on the label, or waiting for its source, among them) keeps the label's reason, as does every label no field is drawn from (both as on main). **C4d**: an expert whose request its sources' answers made too long answers once more, without tools, on the run so far with each lookup result shortened to what an answer cites (the checks read the answers the expert received, untouched); a first request over the bound still fails as `input_too_large`. **Guard**: a record whose fields that describe the specimen (the catalogue number, the collection code and the determiner's IRN aside) are all settled with no value gets `no_specimen_value` and never finishes without a person; a field still open is held by its own reason instead. (Removed 2026-11-18 by K1, the owner's ruling of that date.) | `field_research/step.py` (`scientific_reasons`), `experts.py`, the app's `blockers.dart` (the reason's words) | Fail-first tests per change, with the cases that stay held; no existing test changed; a replay with the real code over the 120 stored specimen-runs: pilot values newly cleared wrong 0. Not in scope: any prompt, "P.I." storage, Verbatim D/T/S, the taxon (C2), the marks (C6), one-reader labels (C5), the app beyond the reason's words |
| C4a, a place name over a line break (not shipped) | A place value field's literal read over one line break ("Davao\nProv.," for "Davao Prov.,"). **Waits for the independent image check and the 100-slide truth set**, where a gain and an error rate can be measured; on stored data it was proven only up to the literal check (5 refused answers passed it). | `agreement.py` (`written_runs`, `across_lines`, `literal_basis`) | Codex's rounds 1 and 2 on #451: both readers write "leg. J. New" over "York", the organiser gives the collectors "J. New", and a city "New\nYork" (value "New York") must stay held, also where a unit wrongly names the city for the collector's surname, or one unit over the two lines names only the precise location (the first pass's unit fields are advice, not proof). |
| C4c, a place inside the country settled from another reading (not shipped) | A place below the country settling inside the record's country settled from another reading of its label, where its own reading spells the country otherwise (105526596's "Costa R.ica"). **Waits for the independent image check and the 100-slide truth set**; on stored data it was proven only by unit tests. | `step._misfit` | Codex's rounds 1 and 2 on #451, the cases any later attempt must hold: reader A "United States", reader B "France" over "Paris" (the country settled from A); "Iran" against "Iraq" and "P.R.C." against "D.R.C.", one letter apart but other nations; a country conflict found on the label only after the place was checked; a country marked on another label of the record. |
| C1 on the listed fields (waits) | The coordinator's rule change 1 ("blank as an answer") on the fields already on `contracts.NOT_ON_LABEL`: the field's own expert's `label_lacks_value` clearing it although the organiser offered text for it. **Waits for the larger truth set.** | `field_research/step.py` (`mark_not_on_label`, condition 5) | Coordinator's ruling of 2026-11-17 on PR #451: no existing safety pin is loosened. The tests that pin a wrong expert answer as held (the keyed lines "county: Cook" and Date Identified, "Lee" as a county, the city "Mt. Apo", the habitat "trap" and "trap, cloud forest") must stay held, so the organiser's text keeps refusing the absence whenever nothing the code already establishes explains why that text is not the field's value. Rule A's condition 5 already absents every text so explained, so a C1 that keeps every pin releases nothing on the stored runs. Measured on S1's first head (C1 as the expert's word plus readers that agree): 6, 4, 3 and 8 absences released (r1/pair, r2/pair, r1/three, r2/three), each judged true by reading the label except 105526487's habitat beside "PRAIRIE DOG", now known to be wrong (lane M0, 2026-11-17: a bare animal name on a label is the host and belongs in Habitat). |
| C4b, a precise location keeping its elevation (waits) | A precise location that keeps an elevation whose number its elevation field settled ("4800" beside "Yepocapa, 4800ft."). **Waits for the precise-location extent fix (V1)**: values first, then the hold. | `agreement.elevation_settled_inside`, `step._keeps_an_elevation`, the extent rule's statement | G51's round 1 on #451: on main this refusal is the only standing hold on an elevation-bearing locality, and with it lifted a cut locality clears with no mark. V1 must first pass these two, on 105526326's label (readers alike, country, province and the elevation "3300" settled): the answer "E. slope Mt. McKinley\nDavao, Prov. 3300'" (dropping "Mindanao, P.I.") and the answer "Davao, Prov. 3300'" alone are each held or marked, never cleared. A measurement gap V1 must close: the frozen scorer counts a precise location within its similarity bound (`score.py:98-100`, 0.85) as right, so a cut locality scores cleared right, and "0 newly cleared wrong" cannot see this class. Measured on S1's earlier heads: 105526326 and 105526329 cleared right (pair arm) and 105526326 marked right (three arm). |
| C3's undrawn-label half (dropped) | A label no field is drawn from held only while a field the organiser found text for on it is held. | | G51's round 1 on #451: unreachable on real organiser rows (a candidate exists only through a row its field cites, and that citation makes the label drawn; 0 of 12 undrawn open labels in the stored runs have organiser text); its only test simulated the lookup. The undrawn-label rule stays as on main. |
| C3's not-on-the-label release (dropped) | A drawn field cleared as not on the label, or waiting for a held source, no longer holding its label. | | G51's round 1 on #451: on one label whose readers differ ("Malaise trap" against "Malaise trep", left out or capitals; "Cook Co." against "Cock Co."; "Chicago" against "Chicaqo"), with the county, city or method cleared as not on the label against an organiser text, the label's reason was the one hold, and the head cleared the record (7 of 7; main held). The step cannot tell from its data whether a reader difference touches the text an absence was reached against, so the release is dropped and these cases are tests that stay held. |
| A1 who cleared a record (PR #450) | The coordinator's rule change 3, its first part: the specimen list, detail, workspace and decision responses carry additive `cleared_by` (`person`, `system` or null), derived on each read from the stored `run.human_approved`; the app shows "Approved by a person" (green) and "Cleared by system" (the model treatment), and a cleared record whose server does not say stays "Cleared", not green. A standing approval is withdrawn by a person's later decision on the record (a field, transcription, authority, taxonomy, metadata or research-candidate decision), whether or not it changes a value, as before this change; and by the value test, wherever a disposition is decided, when the values differ from those recorded at the approval. A system step that leaves the values as approved (a retry, resume, recovery, reconcile or reassessment, or research that writes the same values again) keeps it. `approve` records the digest (`run.approved_values_sha256`) and `lane.settle_approval` applies the value test; an approval with no digest (before this change) stands. Follow-up: tell the reviewer why the record still waits after approving, when the approval's own finalize derives a value and withdraws it. Not in scope: which records clear, the audit sample, showing a reviewer only the open fields, queue sorting or new tabs. | `application/lane.py`, `api.py`, `search.py`, `domain.py` (one optional key), `policy.py`, `field_research/step.py`, the research harness's two canonical materializations, the `SpecimenSearch` view and `SearchSpecimens` (one nullable last column), the app's `specimen_status.dart`, `models.dart`, the queue row, the record screen and the glossary, design 02, 03 and 09, CONTRACTS.md, DATA_SEARCH.md | Fail-first tests per change: the field on both list paths and the detail; an approval ended by each writer that changes a value (research after a retry, resume or reassessment, the drain's recovery, a derivation in the recheck, a person's edit) and kept by a retry, resume or reconcile that changes none, by research writing the identical value, and when it has no digest; widget tests for each chip; no golden changed. Residual risk stated in CONTRACTS.md: a stored non-boolean, which no writer produces, reads null on the list and the model's coercion on the detail (production, read-only, 2026-11-17: 33 of 33 snapshots hold a JSON boolean). |
| V2b the catalogue number from the slide's QR code | An engineering change (the owner has not ruled on the barcode). The segment step decodes the slide's QR code once (zxing-cpp 3.1.1, QR Code Model 2 only, exactly seven digits, one payload on every rung of a fixed ladder; never fails the step) and stores an accepted decode as one evidence row. Field research compares the code with `fmnh_ins_number`'s settled value, after the expert's answer, and changes no value layer. It confirms (no text_only mark) when all three hold: the value's literal writes the code whole (on its letters and numbers alone, no numeric character beside the seven digits); a reading of the code's label holds that literal at an occurrence with no number beside it; the value's parsed and normalized layers are supported without the code. A value whose literal does not write the code whole stays and is held (`marked:fmnh_ins_number:<label>:barcode_differs`, worded in the app). Otherwise, an open field or a person's transcript on any label included, nothing changes. An exception inside the comparison is logged and the field is put back. **Breaking a tie on the code is not shipped**: any later attempt must hold Codex's cases on #452 (a candidate clipped from a longer number, a Unicode or superscript digit beside the code, an invisible separator, a date joined across a line break, a spaced number that made research fail), and should compare the code with the first pass's reading units for the catalogue number (a whole unit's text), not search the raw text. | `application/barcode.py`, `workflow.py` (segment), `field_research/catalogue_code.py`, `step.apply_outcomes`, `pyproject.toml`, `uv.lock`, the app's `blockers.dart` and `settlement_codes.dart` (the new reason's words) | Lane V2's measurement (98 of 100 real slides decoded, all equal to the truth, none wrong; none wrong in 300,000 damaged synthetic codes); this wrapper decodes 97 of 100, all equal to the truth. Fail-first tests per rule; a run with no code row and every other field settle as before. Replay over wp26's 120 specimen-runs: catalogue numbers newly wrong 0, 104 values confirmed, the two wrong clearances of 105526487 now held, open fields left open, `marked:fmnh_ins_number` on 0 to 2 specimens a run (from 6 to 10). Not in scope: the expert's brief, any other field, any other review rule. Residual risk: a slide whose QR code holds seven digits that are not its catalogue number (another institution's code) would hold a correctly settled number (`barcode_differs`); and where the readers also wrote the code's digits as the number, it confirms that wrong number (removing a text_only or conflict mark). This is the stated residual risk; none of the 100 truth slides carries such a code. |
| V3 the slide's QR code settles the catalogue number | The coordinator's ruling of 2026-11-20 (not the owner's words), under the owner's ruling of 2026-11-18 quoted below this table, typed after the coordinator reported the barcode rules holding records for a person. The owner's words of 2026-10-26 bear on it too, as `docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md` section 1 records them at line 32, copied as typed: "Finally first pass never settles, it has to go to harness(QR is a straight pass, ignore that, I’m talking about specimens data)"; reading "a straight pass" as "the code's number is the catalogue number without the harness settling it" is the coordinator's reading, not his words. It changes V2b's comparison (the row above): where the run holds a stored decode whose payload is itself a well-formed catalogue number, the catalogue number is the code's number. Rule 1: no value settled (ambiguous, unresolved, not present, blank, or failing the identifier format): the code gives the number. Rule 2: a settled value whose literal does not write the code whole takes the code's number; the readers' number is kept in the reason and in an info finding (`barcode_readers_differ:fmnh_ins_number`, never a reason, never a hold); no `barcode_differs` mark is made (a record finalized before keeps its mark until a new run). Rule 3: a settled value that writes the code whole is confirmed, as in V2b. Rule 4, unchanged: a run with a transcript a person decided on any label, a run not on the units path, no stored decode. No part of the rule, the confirmation included, acts on a field a person holds authority over, read from the run's durable state through the function the second opinion uses (`second_opinion.authority`: a decision at the endpoint, a carried decision, a locked selection, a reassessment's protected field; every part of the rule enters through `catalogue_code._entry`); rules 1 and 2 run as the last act of `step.apply_outcomes`, after the check stage, so on the attempt that researches the number no other field's check and no re-ask sees a number the code gives (Codex round 1 on PR #458; a later research attempt of the same run does see it as a settled field: FIELD_RESEARCH.md, "Order"). The code gives whole values only: no number is read out of the readers' texts and no tie among readings is broken. A supplied value is supported, on the settled layer, its literal the code's digits, the code row its one citation and deciding it; nothing else is stored, so every later finalize reads the same record (`step.code_confirmed`). The app shows it with the basis of every catalogue number ("As written": the label carries the code); no app change. | `field_research/catalogue_code.py`; `step.py` (comments, and the guard's restore of an absent field) | Measured first: the released segment step stores a decode on 97 of the 100 truth slides, all 97 equal to the truth; no decode on 105526336, 105526446, 105526715 (unchanged: two clear on their readings, one stays held by `text_only`). Replay with the real code, before e83c36fd and after: base 83 to 94 records clear, r3 71 to 83; wrong catalogue numbers among cleared records 0 before and after; every record that moves goes to cleared with the truth's number (base: 8 by rule 1, 3 by rule 2). Nothing else moves on the 200 replayed runs: 0 other fields, 0 other findings, the second opinion's result identical; the reasons that differ are the catalogue number's own, plus two open reasons that hold nothing (`label_unsettled:fmnh_ins_number`, the code's label's `unresolved_transcription`). Values shown with no mark inside cleared records, as K1 scored them: base 429 right and 5 wrong to 505 and 6; r3 399 and 3 to 477 and 4 (the one more is 105526455's Province/State "Utah" for "Idaho", unchanged by this package, in a record that now clears). Tests: `tests/field_research/test_catalogue_code.py`, 115 cases, and `test_catalogue_code_person.py`, 17 cases, the person sequences through the real decision endpoint and Retry. A later research attempt of the same run reads a given number as a settled field, a stated residual by the coordinator's ruling (FIELD_RESEARCH.md); sixteen earlier cases changed expectation with the rule and are kept. Residual risk: a slide whose QR sticker belongs to another specimen now clears with the sticker's number; none in the 97. Details: `docs/execution/golive/FIELD_RESEARCH.md`, "The code gives the number (2026-11-20, lane V3)". |
| K1 skeletal records (this pull request) | The owner's ruling of 2026-11-18 (section 1, quoted there). **The profile**: `zoology_insects_slides` 1.0.0 makes `fmnh_ins_number` its only mandatory field; the nineteen others are optional, in the same order, then `identified_by_irn` (edited in place, as every earlier change to this profile was. A run keeps the clearance profile it was bound with through Retry and Resume (`lane.queue` renews only the execution limits; classify is not run again); only a new run binds the published profile: Reprocess (the app's "Start new run", `POST /runs/{run_id}/actions` with `reprocess`), whose classify step binds it (`test_lane_allowance.test_a_new_run_of_an_existing_specimen_binds_the_published_profile`); a regions decision's new run keeps the old profile). **The disposition**: every field a label writes is still checked and gets the same reasons as before (`policy.checked_fields`, `step.finalize_fields`); `step.split_reasons` then keeps an optional field's doubt in the new additive `run.open_reasons` and lets the record clear; the classification of every reason code is below. **Failures**: an optional field research could not finish (a failure or its expert's fallback) is that field's doubt, `research_incomplete:<field>` in `open_reasons`; research given up for the run as a whole holds (`field_research_given_up`); a label no field is drawn from holds nothing (the coordinator's rulings of 2026-11-18). **Removed**: S1's `no_specimen_value` guard (the coordinator added it on 2026-11-17; the owner's "Where there is no field related data on the lable, nothing to do, it will get cleared" removes it). The ordinary path (`policy.finalize`) splits the same way. No field's state, value, marks or findings change. **Codex round 1 (head cbb3b10d), fixed**: the QR code's confirmation is recomputed on the run as it is each time (`step.code_confirmed`: the decode's number against the current value, no mark, the decode row of this run's image and labels), never read from a relation; a person's pending approval and a location reassessment left unconfirmed survive every finalize until their own resolution (`step.pending_person_holds`; main had the same gap, closed there by other holds in practice); a field's attention in the app and the server's per-field counts read `open_reason_codes` as well as `reason_codes` (`blockers.fieldAttentionFor`, `review_summary`, the search projections' new last column `openReasonCodes`), while the record's disposition and blocker list read `reason_codes` alone. **Codex round 2 (head 74a77105), fixed**: standing holds are defined by construction (`application/standing_holds.py`): every reason a path outside the clearance rules writes (`human_approval_required`, `history_restored_requires_review`, `location_reassessment_unconfirmed:*`) is carried through every recomputation and kept beside a blocker until its own event, and `tests/test_standing_holds.py` scans the source for every writer of a run's reasons; the app takes record blocking from `reason_codes` alone (a transcription or finding blocks only when the server holds its code); one mapping of reason codes to fields, pinned for server and app by `tests/fixtures/field_attention.json`, with `label_unsettled:<field>` naming each field an open label doubt reaches. **Codex round 3 (head f9317b87), fixed by changing the principle**: a hold is never carried from one reasons list to the next; it is derived on every finalize from durable state on the run (`run.pending_review`, the give-up finding), so a blocker may replace the reasons freely. A run stored before the key adopts the holds its stored reasons name, once. | `application/profiles/published.json`, `field_research/step.py`, `application/policy.py`, `application/harness.py` (the extraction request lists the same fields as before), `application/domain.py` (one optional key), the app's `blockers.dart` (one reason's words added, one removed), PRD QUE-002 and 12.4, golive PLAN 2.1/G19/stage 8/4.2, FIELD_RESEARCH.md, CONTRACTS.md | Unit tests: each reason kind classified both ways; the published profile against the profile with every field mandatory, field for field, the same reasons split; a label with only the catalogue number clears; research given up for the run holds through refinalize; an optional field's failure stays open with its reason. The field-mechanics tests (`test_step.py`'s rig and the files built on it) run on the profile with every field mandatory (`test_step.field_mechanics_profile`), so every pinned case, the "expert wrong" ones included, keeps its field held or marked exactly as before. Replay over the 100 truth slides below. |
| F1 the fields' second opinion | An engineering change (the owner has not ruled on it or its model); its structure is the coordinator's ruling of 2026-11-18 after two review rounds. **Its own workflow step** `field_second_opinion`, after field research has completed for the run (its step or recheck finalized it: no retryable research failure pending) and before the record is finalized: the run waits at that stage with no disposition; the step is optional and obeys every guard a mandatory paid step obeys (attempts; steps, two external calls, reserved tokens and active time; a price row; the cost ceiling; room below the record's size limit), then reserves two requests' worst case (USD 0.12, a malformed answer is asked again once) on the monthly caps and the program's allowance inside one handler; an intent with status `asking`, a lease and an attempt but no blocker; a deadline that bounds the crop read, the request (as the experts' are) and the client's closing; ledgers settled only after the result's save; a bounded stored answer (20 values and texts, 300 characters each); every outcome of a sent call final for the values it asked (asked again only for a field never asked or changed since); when nothing of the step can be saved, the record is finalized as main would (except within a few bytes of the limit, where main's own next write blocks too). One request to Muse Spark Open 816B on Baseten (route `second-opinion-muse-spark`, priced in the published price list): the label crops, the readers' texts and the fields benchmark's instruction, never the pipeline's fields; the answer must satisfy the tool schema field by field (all 20 fields, each `{value, evidence}`), else it is asked again once, and a second malformed answer is "not obtained". **Its failure never blocks the run**: switched off, attempts used, a run limit, money, a provider error (HTTP 402 included), a timeout, a second malformed answer, a result over the record's size limit or any exception ends it "not obtained" and the record is finalized in the same save with research's stage and blocker; a person's decision while the intent is open abandons it at the endpoint, and anything else that finalizes the run abandons it first, held in full on the run and the ledgers; a lost outcome (worker deadline, crash, the save failing) is found after the lease, held in full and finalized. **One stored result** `Run.second_opinion` (optional, omitted while unset): the status, each judged field's compared value, the second opinion's value and text and the verdict, and the answer inline; no finding, mark, evidence row or field is written. **Marks derived at every finalize** (`step.finalize_fields`): `marked:<field>:<label>:second_opinion_differs` where the recorded verdict for the field's current value differs, `..._not_checked` where there is none; nothing where it agrees, for the catalogue number, the IRN, an open or blank field, a field another rule marks, or a field a person holds authority over (decided at the endpoint, `Run.person_decided_fields`; carried; locked; a person's transcript; reassessment-protected). Legacy decisions are adopted once at load from the review audit; a history restore returns the revision's own result and list. With K1 (the same pull request, #455, which includes #456) a mark on an optional field is that field's flag, not a hold: an agreed value is shown as settled; a differing or unchecked one is settled and flagged on its field; the record clears on its catalogue number, which the second opinion never judges, so on the published profile no second-opinion mark holds a record. A run is judged by its own pinned profile: on a run whose profile makes a field mandatory, any mark on that field holds the record, the second opinion's included; a new run (Reprocess, the app's "Start new run") takes the published skeletal profile, where only the catalogue number is mandatory and no second-opinion mark can hold. A record stored before this change keeps its old mandatory set on Resume or Retry: the second opinion ends `unconfigured`, its settled fields read "not checked", and those marks hold under the old profile; it clears by the new rule only on a new run, or by a person's approval. | `application/second_opinion_step.py`, `application/workflow.py` (the step's registration), `field_research/second_opinion.py`, `prompts/second_opinion.txt`, `step.py` (five lines in `finalize_fields`, before its `split_reasons`), `storage.work_available_at` and `lane_worker.waiting_until` (an open intent waits for its lease), `research_harness/workflow_bridge.py`, `active_graph.py` (adoption at load), `api.py` (decided), `domain.py` (two optional keys), `model_gateway.py`, `model_option.active_routes`, `profiles/published.json` (price row), the app's `blockers.dart` and `settlement_codes.dart` | The fields benchmark (2026-11-18, 67 slides answered by Muse Spark): on the cleared records the base pipeline's 355 unmarked values held 39 wrong, the 299 agreed 5; with the r3 readers 336 and 33, agreed 280 and 2. This code's replay of the same stored answers: base 273 still shown, 4 wrong (9 with the locality compared exactly), 60 differ (35 wrong), 22 not checked (four answers refused as malformed, all right); r3 265 shown, 2 wrong (6 exact), 58 differ (31 wrong), 13 not checked; 95 % upper bound of wrong among shown near 3 %. Residual risk: a misreading both readers share and the second opinion copies (two dates of two slides); padding of crops over 40:1 not measured; a legacy decision followed by a restore before it is adopted again (production holds none). |
| F2 an agreed value and an agreed blank carry no flag | The coordinator's two rulings of 2026-11-19 on lane H1's measurement (not the owner's words), under the owner's ruling of 2026-11-18 and rule changes 1 and 2 of section 1; display-level and reversible. Derived at every finalize from the second opinion's stored result and the run as it is now; nothing stored; only `run.open_reasons` is shortened. **Rule A**: `label_unsettled:<field>` is not an open reason for a field settled with a value whose recorded verdict for its current shown value is "agrees", the three date fields excepted; skipped on a run any label of which one reader read (an `independent_observations_missing:<label>` reason, holding or open). **Rule B**: `mandatory_unresolved:<field>` and `label_unsettled:<field>` are not open reasons for a blank (`not_present`) field, Verbatim D/T/S and Habitat excepted, that the obtained second opinion, current for the run (the same labels, no transcript a person bound, no reading newer than the request), also leaves blank. Neither applies to the catalogue number, a field the run's own pinned profile makes mandatory, a person's field, an approved run, or while the second opinion is not obtained or leaves a value unjudged. Marks, `research_incomplete`, `taxonomy_unresolved` and the labels' own codes stay, so a field another open reason still names stays flagged (a blank Taxon keeps `taxonomy_unresolved`): the rules remove the named codes, not every flag. See "F2" below. | `field_research/second_opinion.py` (`unflagged`, `agreed`, `answer_current`), one call in `field_research/step.py` `finalize_fields`; `tests/field_research/test_agreed_no_flag.py`; `tests/fixtures/field_attention.json` | Each test fails on e83c36fd. On the 100 truth slides replayed (200 stored runs, each finalized with and without the rules) no record differs in anything but its open reasons; on the 83 that clear, rule A removes 146 flags (0 on a wrong value) and rule B 125 (0 on a missed value); flagged fields per cleared record 11.16 to 7.89. |
| L1 a region too thin to hold a label is not counted as a label | The coordinator's ruling of 2026-11-21 (not the owner's words; an engineering fix of a label-finder artefact, not an owner sign-off of the coverage values, whose range of 1 to 3 is unchanged). In `label_coverage.check_coverage`, a label region whose shorter side is under `CoverageRule.min_region_short_side_fraction` (new, optional; 0.03 in the published profile) of the image's shorter side is left out of the region count; it is still stored, read and shown, and the geometry issues, the full-image cross-check and `merge_iou` are untouched. `run.coverage_check` records the fraction and the regions not counted. A rule without the value counts every region, so a stored run (which keeps the rule it pinned) checks as before. "Count only" means the region count: a run whose count is then in range has its coverage confirmed, with every consequence of a confirmed coverage, the not-on-the-label mark among them (the coordinator's ruling of 2026-11-21; below). | `application/label_coverage.py`, `application/collection_profiles.py`, `application/profiles/published.json`, `tests/test_lane_coverage.py` | Replay on the 100 truth slides (below): 94 to 98 records clear, 0 wrong catalogue numbers; 105527007 (one label drawn twice) stays held |
| L3 the same label boxed twice is counted once | The coordinator's ruling of 2026-11-21 on review round 1 of #461 (not the owner's words; an engineering fix of a label-finder artefact, provisional, not an owner sign-off of the coverage values). A new optional value of the coverage rule, `CoverageRule.nested_duplicate` (`min_containment`, `min_iou`, both required; 0.95 and 0.6 in the published profile): two label regions count as one label when at least 0.95 of the smaller box lies inside the larger and their IoU is at least 0.6, as the label finder's outer card and inner frame of one label do. `merge_iou` stays 0.9. Merges chain across both tests, after the thin regions are left out. Count only: both boxes stay in `run.regions` and are read, stored and shown; `run.coverage_check` adds `nested_duplicate` and `merged_regions` under a rule with the value. #461 first lowered `merge_iou` to 0.6; Codex's round 1 showed four separate diagonal labels whose boxes overlap at IoU 0.68 chaining into one label and confirming coverage, so IoU alone was dropped. A stored run keeps the rule it pinned; the consequences of a confirmed coverage are as in L1's row. | `application/collection_profiles.py`, `application/label_coverage.py`, `application/profiles/published.json`, `tests/test_lane_coverage.py`, `tests/field_research/test_duplicate_label_coverage.py` | Measured (`autonomy-program/L3/scripts/measure.py`, the 269 stored regions of the 100 truth slides): 24 overlapping pairs; two duplicates (outer card and inner frame of one Lewis label, the frame wholly inside: 105527007 IoU 0.7847, 105526361 IoU 0.7731), both meeting the rule; the other 22 are different labels (seen: L2 looked at six, the G51 review of #461 at all 22, each a barcode label's box touching a large label's box), at most 0.491 of the smaller box inside the other and IoU at most 0.0496, none meeting it. Replay (`L3/scripts/replay_l3.py`, the real `check_coverage` with each tree's published rule, then the real `finalize_fields` on the stored rows, origin/main 106cebd7 against this change): 98 to 99 records clear, 0 wrong catalogue numbers; 105527007 4 to 3 regions, now cleared; 105526361 3 to 2, cleared before and after; no other slide's coverage, count, disposition, reasons or shown field moves. On 105527007 every shown value that differs from the truth is flagged by an open reason naming its field: among them Date Visited From and To shown 1974-04-27 for the truth's 1976-04-27 (`label_unsettled:date_visited_from` and `label_unsettled:date_visited_to`); the two readers read that label's year as 1994 and 1974 on its outer box and 1970 and 1976 on its inner box. Residual risks: merges chain, so any number of separate narrow labels at an angle whose boxes nest link by link (each link: IoU 0.9 or more, or 0.95 inside at IoU 0.6 or more) would count as one, which can release a count hold (no such link between different labels among the 269 regions or in P1), and every box would still be read and shown; two duplicate examples only, both the same card-and-frame pattern; rolling back below this change needs a new run for runs pinned with the value. Details: DATA_CONTRACT.md 4.1 |
| H3 a blank field the second opinion gives a value for is flagged | The coordinator's rulings of 2026-11-21 on lane H2's measurement and on the paid habitat rerun (engineering fixes, not the owner's words). `second_opinion.filled`, at every finalize after the split and the derived holds: a judged field shown blank (not present, "not on the label" among them, not applicable, or supported with no text; an open field is already flagged by its state) for which the obtained, current second opinion gives a value gains the open reason `marked:<field>::second_opinion_differs` (a flag only: the value stays blank; never a mandatory field, a person's field, an approved run, a run off the units path or while the step is due, or a field already flagged). Measured and NOT shipped: a rule in `prompts/habitat.txt` that a host is the habitat (reverted; see "H3" below). The museum's published records hold hosts as associated taxa and never in Habitat (lane M0); the 20-field profile has no such field. | `field_research/second_opinion.py`, `field_research/step.py` (`finalize_fields`), `tests/field_research/test_blank_second_opinion_fills.py`, `tests/fixtures/field_attention.json`, the app's `test/second_opinion_test.dart` | Free replay on the 100 truth slides: 53 flags gained, all Habitat, 0 where the truth is blank, dispositions unchanged on 100 of 100; 5 Habitats the truth fills stay blank with no flag (the second opinion gave no value). The prompt rule's paid rerun on the 99 cleared records: wrong Habitats 6 to 19, so it does not ship |
| H4 a host the label writes is the Habitat value | The coordinator's rulings of 2026-11-21 (not the owner's words; the owner has not ruled on where a host belongs): the lane's, that the habitat expert answers a label's host as the Habitat, as written, by a change confined to its own instructions and the habitat field's acceptance code; and, on the second paid run, the one condition inside rule A. **The brief** (`prompts/habitat.txt`, five rules): a host is this field's value; the name after a host marker, or a non-insect animal's name with no marker, wherever it stands; copied whole, a written "Ex."/"Ex:"/"ex"/"On" kept, a "Host" heading left out, `value` empty; over consecutive lines where the label writes it so; a name the expert cannot place is not guessed. **Acceptance, habitat only**: a literal may run over consecutive lines as the precise location's does (`agreement.ACROSS_LINES`); one that starts with the heading "Host" is refused, never rewritten (`HOST_HEADING`). **Inside rule A (F2)**: an agreed Habitat keeps `label_unsettled:habitat` where a reader of a label it rests on writes another text for it (`second_opinion.READERS_MUST_WRITE`). Every other prompt text is byte-identical (33 of 34). Left in place: the ontology's `host_marker` entry ("[no field]", 21 prompts) and its comment that no field holds a host; the museum's published records hold hosts as associated taxa and never in Habitat (lane M0): a point for the owner, not a ruling of his. | `field_research/prompts/habitat.txt`, `field_research/agreement.py`, `experts.py`, `step.py`, `second_opinion.py`; `tests/field_research/test_host_is_the_habitat.py`, `test_agreed_habitat_readers.py`, `test_units_instructions.py` (the habitat pin) | Paid habitat-only rerun of a28cf3f5 on the 99 cleared records of the 100 truth slides (USD 0.2076 at list; the second opinion judged on the stored answers): right Habitats 10 to 49, wrong 6 (6 before), every wrong or partial one flagged, missing 76 to 37 (35 flagged), right blank 7 of 7; no record's disposition, `cleared_by`, holding reasons or other field differs. Free: the real finalize on the 100 stored runs equals origin/main on 100 of 100; the rule A condition adds 1 flag on run 3's answers and none on its 49 right Habitats. See "H4" below |

The owner's ruling of 2026-11-18, typed in session f9614090 (quoted exactly):

- "rather than holding for a person, I'd like you to figure out how to resolve these simpler things. I dont see a huge
  confluct there honestly. When we have multiple readers etc it is natural to see different values, we shouldnt be
  paralysed by it, our harness helps in clarifying anyway so the goal is to self resolve."
- "Where there is no field related data on the lable, nothing to do, it will get cleared. Not all fields are mandatory
  right. As long as the mandatory ones are filled it should be cleared. Lets make skeletal records mandatory (decide if
  not already decided), full set (remaining optional)"

The coordinator's decision for this build (the coordinator's words, not the owner's): "skeletal" was defined nowhere,
so the mandatory (skeletal) set is the catalogue number, `fmnh_ins_number`, the one thing every slide carries; every
other field is optional. The owner's list of 2026-09-24 (golive PLAN G42, "The mandatory fields in an entomological
database should be:" and twenty fields) stays the list of fields the record carries and the harness researches.

### K1: which reasons hold the record (`step.split_reasons`)

The classification is the coordinator's rulings of 2026-11-18 (the coordinator's words, not the owner's): an optional field the system failed to resolve is that field's doubt, it is the field that waits for a person, not the record; a label no field is drawn from holds nothing, except the label the catalogue number is drawn from; and only these hold: the catalogue number not settled, marked, failing its format, or drawn from a label whose reading is in doubt that the slide's QR code does not confirm; label coverage; missing provenance or evidence for the record as a whole; a run that did not finish; and a person's pending decision or approval.

| Reason code | Holds the record? |
|---|---|
| `label_coverage_unconfirmed` | holds |
| `mandatory_unresolved:fmnh_ins_number` (no settled catalogue number, its research failed included) | holds |
| `marked:fmnh_ins_number:<label>:<why>` (`text_only`, `conflict`, `parts_on_labels`, `barcode_differs`, a check-stage rule) | holds |
| `identifier_format` | holds |
| `unsupported_parsed`, `unsupported_normalized`, `unsupported_authority_id`, `evidence_missing`, `evidence_does_not_support_value`, `raw_reading_grounding_unproved`, `pixel_lineage_missing` on `fmnh_ins_number` | holds |
| `unresolved_transcription:<label>`, `independent_observations_missing:<label>`, a label's language rule `<reason>:<label>` | holds when the catalogue number is drawn from the label and the slide's QR code does not confirm it; otherwise (a label only optional fields are drawn from, a label no field is drawn from, a label whose first pass was given up) an optional field's doubt |
| `raw_provenance_missing:<label>` | holds when the catalogue number is drawn from the label (the code does not stand in for a missing raw reading); otherwise an optional field's doubt |
| the field codes above on an optional field (`mandatory_unresolved`, `unsupported_*`, `evidence_missing`, `evidence_does_not_support_value`, `raw_reading_grounding_unproved`, `pixel_lineage_missing`, `marked`) | an optional field's doubt |
| `research_incomplete:<optional field>` (new: a failure, a limit, a spent per-field or per-specimen meter, a request too large, an outage or deadline on the last attempt, or the expert's fallback) | an optional field's doubt; the field keeps its own reason (`FIELD_REASONS`) |
| `taxonomy_unresolved`, `identified_by_irn_identity_unproved` | an optional field's doubt |
| `elevation_invalid`, `elevation_range`, `elevation_units_conflict`, `date_precision_requires_review`, `date_order` | an optional field's doubt |
| `field_research_given_up` (new: research given up for the run as a whole) | holds; derived on every finalize from the give-up's finding on the run, which the next research attempt removes |
| `preserved_human_decision:<field>` | holds (recomputed from a person's decisions on every finalize) |
| `human_approval_required`, `history_restored_requires_review`, `location_reassessment_unconfirmed:<field>` | holds; derived on every finalize from `run.pending_review` (`application/standing_holds.py`), recorded when a person decides, a history is restored or a reassessment leaves a field unproved, and cleared by a person's approval (the reassessment's entries also by the reassessment that settles them) |
| `label_unsettled:<field>` (new: a field drawn from a label whose doubt is open, `step.label_attention`) | never holds: the field's attention only |
| an operational failure (`lookup_operational_failure`, `field_research_model_error`, `field_research_timeout` `:<field>`, the blocker) | holds: the run is blocked, as before |
| `evidence_integrity_failure` | never a reason: the step blocks, as before |
| ordinary path: `institutional_policy_unapproved`, `mandatory_semantics_unconfirmed`, `evidence_lineage_invalid:<row>`, its capability reason | holds |
| ordinary path: `taxonomy_lookup_missing` | an optional field's doubt |
| `no_specimen_value` | removed |
| any other code | holds (fail closed; no code produced today falls here) |

### K1's replay (free, real code, the 100 truth slides)

Each stored run (`~/specimen-golive/runs/units-wp26-20261115/`, four runs of 30; `~/specimen-golive/runs/autonomy-base70-20261118/`,
one run of 70: 69 finalized, 1 blocked) was loaded from a copy, bound to the published profile of the code under test
(this branch merged with main 9e79d35e, PR #452 included), and re-finalized (`finalize_fields` with each field's stored
failure and fallback). "With the code": PR #452's decode of the slide's QR code attached as its segment step would store
it (T0's image, byte-equal to the run's asset in all 189 finalized specimen-runs; decoded on 28 of the 30 wp26 slides
and 68 of the 69 finalized base70 slides) and its rule (`catalogue_code.settle`) run on the stored catalogue number, as
lane V2b's replay does. Before: 0 cleared in every run, as stored and as replayed on main d4c33d94. Scored against
`T0/truth_rows.json` (off-repo `~/specimen-golive/autonomy-program/K1/`: `score_r2_code.txt`, `score_r2_nocode.txt`,
`holds_r2_code.txt`, `wrong_values_r2_the100.txt`). The 100 are wp26 r1/pair and base70.

| run | cleared, no code | cleared, with the code | unmarked values in cleared records (wrong), with the code | marked (wrong) | wrong catalogue number cleared (no code / code) |
|---|---|---|---|---|---|
| wp26 r1/pair | 23 of 30 | 28 of 30 | 181 (5) | 20 (5) | 0 / 0 |
| wp26 r2/pair | 20 of 30 | 26 of 30 | 167 (3) | 20 (4) | 1 / 0 |
| wp26 r1/three | 20 of 30 | 28 of 30 | 178 (9) | 41 (8) | 1 / 0 |
| wp26 r2/three | 18 of 30 | 27 of 30 | 174 (11) | 36 (3) | 0 / 0 |
| base70 r1/pair | 46 of 70 | 55 of 70 | 365 (40) | 20 (3) | 2 / 0 |
| **the 100** | **69 of 100** | **83 of 100** | **546 (45)** | **40 (8)** | **2 / 0** |

Values are the app's (normalized first), every field the truth settles; a value where the truth has none counts
wrong. In the 83 cleared records of the 100: 45 of 546 unmarked values are wrong (8.2 %; about five of them are
conventions: "Aysen" shown for the label's "Aisen" three times, a determination date kept as written "VI.'41"
twice); 8 of 40 marked values are wrong; 75 fields are blank where the truth has a value (habitat 52, the host
name M0 ruled belongs there) and 198 are left open where the truth has one. The frozen scorer (parsed first, its 11
fields) on the 83: primary cleared right 320, cleared wrong 28 ("P.I." among them), marked right 29, marked wrong 1,
left without a value 94; derived 108 right, 9 wrong; absences 277 right, 3 wrong. 16 precise locations shown differ
from the truth at all, most a "Loc:" heading kept or a line cut; 8 of them pass the frozen scorer's 0.85
similarity. The code turns every wrong catalogue number that cleared without it (105526487 "4486518", 105526771
"448634", 105526356 "4486748") into a `barcode_differs` hold; no cleared record carries a wrong catalogue number.

What holds the other 17 of the 100 (with the code; a record counts once per kind): the catalogue number not settled
and so failing its format 8; label coverage unconfirmed 4; `barcode_differs` 3; `text_only` on the catalogue number
1 (no code decoded); the one blocked run (`external_outcome_unknown`) 1. Without the code, 31 are held, 18 of them
by `text_only` on the catalogue number.

### K1 with F1's second opinion (PR #455 with PR #456 merged in)

The two ship together. The second opinion's marks (`marked:<field>:<label>:second_opinion_differs`,
`..._not_checked`) pass through `step.split_reasons` like every other reason, at `finalize_fields`, which the step's
own finish and a person's decision at its stage both reach through `step.refinalize` (#456 at d016678b; an approved run
gets no second-opinion code, so a person's approval clears every flag with the holds). The second opinion never
judges the catalogue number, the published profile's one mandatory field, so on that profile none of its marks holds a
record: an agreed value is shown as
settled; a differing or unchecked value is settled and flagged on its field (`open_reasons`, the app's field
attention); the record clears on its catalogue number. Not obtained (a provider error, HTTP 402 included; a malformed
answer twice; money; no price row; an exception; its attempts used; an outcome lost) or switched off, every settled
value it answers for is flagged "not checked" and the record clears; the step's failure changes neither stage nor
blocker. A record held for another reason stays held whatever the second opinion says. A run is judged by its own pinned profile: on a run whose profile makes a field mandatory, any mark on that field holds the record, the second opinion's included; a new run (Reprocess, the app's "Start new run") takes the published skeletal profile, where only the catalogue number is mandatory and no second-opinion mark can hold. A record stored before this change keeps its old mandatory set on Resume or Retry: the second opinion ends `unconfigured`, its settled fields read "not checked", and those marks hold under the old profile; it clears by the new rule only on a new run, or by a person's approval. Proof:
`tests/field_research/test_second_opinion_skeletal.py`; `tests/fixtures/field_attention.json` and the app's
`second_opinion_test.dart` for the field's attention and words.

Replay (free, stored answers only: `~/specimen-golive/autonomy-program/K1/replay_k1c.py`, `score_k1c.py`,
`score_k1c.txt`). K1's replay with the QR code on, then the second opinion's real code fed the fields benchmark's stored
Muse Spark answer (95 of 100 slides answered; the other 5 count as not obtained), then `finalize_fields`. Product
view, inside the records that clear; "base" is wp26 r1/pair and base70 r1/pair (the 100 truth slides), "r3" the
stronger-reader run on the same 100.

| pipeline | records that clear | wrong catalogue numbers among them | shown as settled, no flag (wrong) | flagged: differs (wrong) | flagged: not checked (wrong) | another rule's mark (wrong) | open where the truth has a value |
|---|---|---|---|---|---|---|---|
| base | 83 of 100 | 0 | 434 (5) | 71 (38) | 41 (2) | 40 (8) | 198 |
| r3 | 71 of 100 | 0 | 402 (3) | 71 (38) | 31 (1) | 35 (11) | 126 |

The records that clear are the same with no stored answer at all (`replay_k1c_noanswers.json`): the second opinion
moves values between "shown" and "flagged", never a record between held and cleared. #455 alone cleared the same 83,
with 45 wrong among 546 unmarked values (8.2 %); with the second opinion 5 of the 434 shown with no flag are wrong
(1.2 %; 95 % upper bound 2.7 %; r3 3 of 402, 0.75 %, bound 2.2 %), each a value the second opinion read the same
wrong way (a collector's initial, "M. O." for "M. D."; the visit dates of two slides, month or year). What the stored
rows cannot prove: the step's own lifecycle in production (the answers are replayed, not requested); the five slides
without an answer (the provider refused a crop's aspect ratio in the benchmark; #456's padding of such crops is not
measured); anything outside these 100 slides.

### F2: an agreed value and an agreed blank carry no flag

Authority. The owner's ruling of 2026-11-18 and the plan he approved on 2026-11-17 are quoted in section 1 and under
"K1" above. The two rules are the coordinator's rulings of 2026-11-19 under them, on lane H1's measurement, and the
one-reader condition on rule A and Habitat as rule B's exception are his rulings of 2026-11-20 on the live confirmation
rows; they are not the owner's words. Rule A stands on rule change 2 ("Agreed and checked values clear."): the second opinion is the
independent check that looks at the label image, and the rule lifts a flag only for the field types the truth set
measured with no wrong value. Rule B goes beyond the condition the coordinator stated to the owner for rule change 1
("Blank becomes an answer when both readers read the whole label cleanly and the expert says the field is not there."):
it rests on the expert's "not present" and the second opinion's blank, not on the not-on-the-label check row. Both
change only which fields a cleared or held record flags; no record clears or holds differently and no value changes,
so either rule can be withdrawn by removing one call.

Why. Lane H1 measured, on the 83 records of the 100 truth slides that clear under K1 with F1 (base pipeline, stored
second-opinion answers), about 11 flagged fields per cleared record, and two groups of flags that guard nothing: a
settled value the second opinion agrees with, flagged only by `label_unsettled:<field>` (220 right, 2 wrong, both
dates of one slide; without the three date fields 157 right, 0 wrong); and a blank field the second opinion also leaves
blank, flagged by `mandatory_unresolved:<field>` alone or with `label_unsettled:<field>` (2 missed values, both
Verbatim D/T/S; without it 0 missed). The marks H1 found unsafe to lift stay as they are (`text_only`, `conflict`, the
date precision check, `second_opinion_differs`, `second_opinion_not_checked`).

Replay (free: `~/specimen-golive/autonomy-program/F2/scripts/replay_f2.py`, K1c's replay with the stored result's time
a real clock time, each stored run finalized twice, with the rules and with `unflagged` replaced by the identity;
`measure_f2.py` runs H1's own functions on both outputs).

| pipeline | records that clear, without and with | runs differing in anything but open reasons | rule A: flags removed (on a wrong value) | rule B: flags removed (on a missed value) | codes dropped on cleared records | flagged fields per cleared record |
|---|---|---|---|---|---|---|
| base | 83 and 83 of 100 | 0 of 100 | 146 (0) | 125 (0) | `label_unsettled` 206, `mandatory_unresolved` 135 | 11.16 to 7.89 (median 11 to 7) |
| r3 | 71 and 71 of 100 | 0 of 100 | 127 (0) | 73 (0) | `label_unsettled` 170, `mandatory_unresolved` 79 | 9.83 to 7.01 (median 10 to 6) |

The copy finalized without the rules equals K1c's stored replay on all 200 runs. Held records lose the same open codes
(base 48 and 49) and stay held for their own reasons.

The one-reader condition (the coordinator's ruling of 2026-11-20). The rules as first ruled reproduced H1's base
figures: rule A 157 flags (0 wrong); rule B 126 (0 missed), H1's 140 less 14 blank taxon fields (10 truly absent, 4 not
scored) that also carry `taxonomy_unresolved`, which H1's candidate dropped and this rule keeps; 11.16 to 7.75. The
live confirmation rows then showed what the replay did not hold: slide 105526455, Province/State "Utah" for Idaho,
drawn from a label one reader read, agreed by a second opinion that saw that one reader's text, flagged only by
`label_unsettled`; rule A would have lifted it (on the live rows of that hour, agreed values on one-reader labels: 2
right, 1 wrong; on labels both readers read: 45 right, 0 wrong). The ruling: an agreed value needs two independent
readings behind it, so rule A is skipped on a run that carries `independent_observations_missing` for any label. Its
cost on the base pipeline: 9 of the 83 cleared records carry the code and keep 11 of rule A's 157 flags, all on right
values; r3 holds no such record. Rule B does not take the condition (ruled the same day): a blank is no wrong value
shown as settled, the second opinion reads the crops itself, and the 63 blanks it agreed on those 9 records were all
truly absent.

Habitat as rule B's exception (the coordinator's ruling of 2026-11-20). A later live row, slide 105526418, has a bare
host name on its label ("CALLOSPERMOPHILUS") that the truth set puts in Habitat; field research left Habitat blank and
so did the second opinion, and rule B would have lifted the blank's only flag. A bare host name is a known miss of both
(lane H1: 48 blank Habitats where the truth has a host), so their agreement on a blank Habitat proves nothing until
hosts are filled, which is a separate follow-up. Its cost: 1 flag on the base pipeline (126 to 125) and 1 on r3.

What the replay cannot prove: the rules on a record a person has worked on (tests only); field types with few
cases (among the agreed values flagged only by their label's doubt: taxon 1, Verbatim D/T/S 1, county 2, habitat 3); a misreading both readers share, which the second opinion, given
both readers' texts, can agree with (3 such values are shown with no flag today and stay so).

### L1: a region too thin to hold a label is not counted as a label

Authority. The coordinator's ruling of 2026-11-21, an engineering fix of a label-finder artefact; not the owner's words
and not an owner sign-off. The coverage values themselves (1 to 3 regions, concept "text", 0.5 score, 50 % inside) are
provisional values from a coordinator ruling of 2026-09-23 (`status/coordinator.md` 23-24: "G15 check built with
provisional values (1-3 regions, "text", 0.5 score, 50% inside); S7 calibrates; OWNER SIGN-OFF on the final values
before production."); no owner sign-off of final values is recorded (DEC-7 is open). The new 0.03 is likewise
provisional.

Why. In the live run of b35e823e on the 100 truth slides, 5 records were held, every one by
`label_region_count_out_of_range` with 4 regions. The truth gives each of them three labels. On four the fourth region is
a strip 10 to 15 px tall along the image's top edge (score 0.50 to 0.61), read "[unreadable]" by both readers; on the
fifth (105527007) one label is drawn twice (IoU about 0.78, under `merge_iou` 0.9), which this rule does not touch.

Measurement (free, the stored regions; shorter side as a share of the image's shorter side):

| | share |
|---|---|
| the 7 strips of 269 regions (all at y = 0, all unreadable by both readers; three on 2-label slides that cleared) | 1.63 to 2.41 % |
| the smallest real label (the barcode label) | 14.33 % |
| fraction 0.02 / 0.03 / 0.05 / 0.10: regions not counted | 5 / 7 / 7 / 7, none read as text |

`P1/held_regions.json` holds 9 held production records, boxes only (no readings). Production slide scan 105526324
(48a71d53, 1798 x 615) has the same strip (1.6 %): not counted at 0.03, 4 to 3 regions. The other eight are camera-size
images (1920 x 1080 or 1080 x 1920) with no truth, and the rule was not tuned to them: at 0.03 one region of one of them
is not counted (2c6ef7b0, (0, 4, 28, 161), 2.6 %: 7 to 6 regions, still held; whether that box is a label cannot be judged
from boxes alone) and the other seven are unchanged; at 0.05 three of the seven would lose a region, at 0.10 six.

Replay (free: `~/specimen-golive/autonomy-program/L1/scripts/replay_l1.py`, each stored run copied, the real
`check_coverage` on its stored regions with the pinned rule and then the published one, then the real
`finalize_fields`). Before: coverage confirmed on 95, 94 clear, equal to the live rows. After: confirmed on 99, 98
clear, 0 wrong catalogue numbers. The four strip slides become confirmed and clear; 105527007 stays held; the three
cleared strip slides stay cleared (count 3 to 2); no other slide's outcome or count moves. On the four newly cleared
records every shown value that differs from the truth other than in spacing is flagged by a reason naming its field;
two values differ in line breaks or spacing only, unflagged. The replay does not re-run the readers, the first pass,
field research or the second opinion: it shows what the stored work becomes under the rule.

Count only, and what follows (the coordinator's ruling of 2026-11-21 on review round 1 of #460). "Count only" means the
region count. A run whose count is then in range has its coverage confirmed, and every consequence of a confirmed
coverage follows as on any confirmed run: the thin region is still read, and its text is still part of what the readers,
the organiser and the experts see; origin/main already behaves so for two labels and such a region. What reads the flag:
`application/policy.py:51` (the ordinary path's clearing gate), `field_research/step.py:3341` (`_whole_label_read`, which
opens the not-on-the-label mark at `step.py:4032`), `field_research/step.py:4378` (the units path's
`label_coverage_unconfirmed`), `research_harness/canonical_materialization.py:142` and
`research_harness/canonical_materialization_v2.py:202` (the harness producers' `label_coverage_unconfirmed`),
`application/human_field_carry.py:423` (`keep_regions`: "Start new run" on a record whose regions a person corrected
copies the old run's flag, a confirmation or a withdrawal, into the new run and skips segmentation; read from the code,
not tested, that flag is a person's, from `api.py:2729` or `api.py:2405`, so the thin-region rule does not reach it) and
`scripts/qa/live/human_review.py:229` (a QA script that refuses human-review evidence unless the saved flag is true: QA
acceptance, not a record's clearing). The list comes from `grep -rn "coverage_confirmed" src scripts
apps/specimen_digitization/lib` (tests left out); every other hit is the declaration (`domain.py:520`) or a write
(`label_coverage.py:133`, `api.py:2405`, `api.py:2729`, `workflow.py:1170`, `evidence_pilot.py:254`), and the search's
remaining hits are 4 fixture writes in test files under `scripts` (`scripts/lab/test_lab_checks.py:94`, `scripts/qa/live/test_human_review.py:104`, `:110` and `:234`), 17 in all; the Dart app has no hit (it sends a person's `coverage` decision). Worked case,
pinned by `tests/field_research/test_thin_region_coverage.py`: three labels and a thin region both readers read as clean
text, habitat's expert answering `label_lacks_value`; before, count 4, held, habitat's reason "No reading writes a
habitat."; after, count 3, cleared, "Not on the label: ..." with a `check:not_on_label` row. None of the seven measured
strips reaches it: each is `[unreadable]`, so `_whole_label_read` is false and the habitat is as before (the test's
mirror).

Rollback: code before this change cannot process a run this change pinned (the G51 review's probe, records written by
#460's head continued by b35e823e: Retry, Resume and a region correction end `processing_blocked` with
`evidence_integrity_failure`, one held record's detail returned 422, "Start new run" works on the probed record, which had no person's decisions). A new run is therefore the expected way
forward after rolling the server back below this change, for records whose runs were pinned with the value; it is not a
tested guarantee for every record.

Known gap, measured and not changed: on the 100 truth slides the full-image cross-check counted no detection (110
detections, highest score 0.2139, threshold 0.5), so on those slides the region count was the only part of the check that
held a record; the cross-check still holds a record when a detection at or over the threshold lies outside the labels.
A real label
thinner than 3 % of the image's shorter side would not be counted (none seen in 269 regions); it would still be read and
shown.

### H3: a blank field the second opinion gives a value for is flagged

Authority. The coordinator's rulings of 2026-11-21 (not the owner's words): on lane H2's diagnosis, engineering fixes of
the pipeline against the repository's own written requirement; on the paid habitat rerun, that the prompt change does
not ship. Lane M0's ruling H (`~/specimen-golive/autonomy-program/M0/meanings.txt`), settled from the repository's
sources (`habitat.txt:1`, "The habitat, host or substrate the label writes"; the ontology's rule that a host is never
the specimen's taxon; `taxon.txt`, a common name is not a taxon), puts a host in Habitat as written. The difference M0
recorded stands: the museum's published flea records hold hosts as associated taxa ("Ectoparasite Of"), and none of
the 104 Habitat values M0 read there is a host; the 20-field profile has no associated-taxa field. That is a point for
the owner, not a ruling of his.

Why (lane H2, `~/specimen-golive/autonomy-program/H2/notes.txt`, recounted with `h2_detail.py` and `blank_net.py`). Of
the 99 records the second confirmation run cleared (confirmation 3's six replacing theirs), the truth has a Habitat on
92: 16 were shown, 76 were blank, and every one of the 76 is a host. 58 of the 76 were blank with no flag, their reason
"Not on the label", though both readers read the host line. The habitat expert's instructions contradict themselves:
its brief and the ontology's field row say "habitat, host or substrate", while the ontology's `host_marker` notation
says a host has no field. Over all fields of the 99 records, 706 blanks carried no flag by lane H2's rule
(`H2/blank_net_check.py`: an open reason's code naming the field), 704 by the app's own mapping
(`H3/scripts/blank_counts.py`, `review_summary.attention_fields`: `date_precision_requires_review` flags two blank
identification dates); the stored second opinion gives a value on 53 of them, all Habitat, all real misses; nothing flagged them, because the second opinion's marks were for a
settled value only (PR #455) and `step.mark_not_on_label` had left the blank no flag to keep.

The flag, free replay (`~/specimen-golive/autonomy-program/H3/scripts/replay_h3.py`: each stored run of the 100 truth
slides copied, then `step.finalize_fields` with its stored second-opinion answer, once with origin/main's code and once
with this code; `compare_h3.py` against the truth):

| Measure (`H3/replay_h3.txt`) | origin/main | this code |
|---|---|---|
| Records that clear | 99 of 100 | 99 of 100 |
| Flags gained | | 53, all Habitat, all on cleared records |
| Of them, the truth has a value (second opinion's value right by `second_opinion.same`, wrong) | | 53 (46, 7) |
| Of them, the truth is blank | | 0 |
| Flagged fields per cleared record (the app's mapping, the IRN left out) | 7.55, median 7 | 8.08, median 8 |
| Records whose run differs in anything but its open reasons | | 0 of 100 |

The main-code replay equals the stored rows on 100 of 100. Residual: 5 cleared records whose truth has a Habitat keep
it blank with no flag, because the stored second opinion gave no value there (105526348, 105526356, 105526392,
105526468, 105527285). No existing test's expectation changed: the pin PR #455 wrote (`test_second_opinion.py`,
`test_a_field_another_rule_marks_and_an_open_or_blank_field_get_no_mark`) gives every field a blank answer, so it still
holds.

When the mark is current. The mark is derived at finalize, as every open reason is. Guaranteed: a save that follows a
finalize of the run as saved carries what a fresh finalize of that state gives (the G51 reviewer, round 2: of the 249 finalized states of his round-2 sequences, 247 equal a fresh finalize; the other two are the restore window's, below). Not
guaranteed: a save that does not follow a finalize keeps the open reasons of an earlier finalize, on origin/main and on
this branch alike and for every open reason, until the next finalize, which recomputes the mark from the record as it
then is and may give it or give none. The guarantee holds one way only: a save with no finalize can still equal a fresh
finalize (after Retry with no decision, or a restore to a revision no person approved: the G51 reviewer, round 3). The
worker ends some such windows when it reaches a finalize; a run it blocks first keeps the stored open reasons while it
is blocked, and some windows last until a person acts, which may be never.

Known examples, found in the reviews of this PR; the list is not claimed complete:

- a history restore (`history_restore.py:62`, `api.py:1573-1580`): the record is held for review, or blocked when the
  restored run had a blocker, and then stays blocked until the Retry or Resume after the repair (a decision does not end that window; an approval ends it only when the blocker was a lost blob's `evidence_integrity_failure`);
- a decision other than an approval or a capability deferral that arrives on a run whose stage is not `finalized`
  (`api.py:2423`; an approval reaches the finalize at any stage, where `step.refinalize` still returns early on a blocker other than a repaired `evidence_integrity_failure`, and a decision arriving at `field_second_opinion` is moved to
  `finalized` first, `api.py:2092`): after a transcript decision (stage `parse`); after Retry or Resume before any
  worker step (stage `pending`); on a paused or cancelled run, at rest, possibly indefinitely (the worker returns at
  `workflow.py:726`; a person resumes, retries or approves it, and reprocess is named here from the code only: it was
  not run); on a blocked run, until the Retry or Resume after the repair (`step.refinalize` returns early on a run with
  a blocker, `step.py:4846`);
- a field decision on the taxon or another looked-up field after a transcript decision removed field research from the
  completed steps (`api.py:2247`, then `api.py:2163` sets stage `lookup`), found by Codex in round 3; the saved revision
  keeps the mark beside the stored second opinion, and the worker's finalize removes it (tested);
- graph-limit recovery (`active_graph.py:237-264`, used by `save_recoverably`): when a save exceeds the record's graph or snapshot limit, the working copy is discarded, the prior snapshot is reloaded, its approval withdrawn, and it is saved `processing_blocked` with the limit as its blocker and no finalize, found by Codex in round 3; run by the G51 reviewer in round 4: an oversized decision returns 200, is discarded, the prior snapshot is saved blocked and its approval withdrawn; Retry ends it;
- a worker block the worker does not end by itself, for example `step_budget_exhausted` after a decision on a pending
  run (`workflow.py:921`, `workflow.py:978`; later steps return at `workflow.py:726`; automatic recovery does not take a
  completed-research recheck, `workflow.py:2141-2147`), found by Codex in round 3; run by the G51 reviewer in round 4: with the step allowance used up (set by a direct save standing in for repeated rechecks), Resume, a Habitat decision and a worker step left the run blocked with the mark on the person's field; Retry, Resume and an approval did not end it.

When a finalize ends a window it recomputes the mark. Tested here: after a restore to an approved revision, Resume gives
the mark, and approving again gives none (an approved run gets no mark) while the record clears by that person's
approval; after a transcript decision the worker's finalize removes it (the answer is no longer current); after a
decision on the marked field (on a paused or cancelled run, after Retry or Resume, while a blob is lost), the finalize
that follows gives no mark on that person's field, and the record then waits for that person's approval
(`standing_holds.person_acted`). The G51 reviewer's notes add (rounds 2 and 3): after a restore, a decision on another
field also gives the mark, and a decision on the field itself gives no mark and does not clear the record, which stays
`needs_human_review`, held by `history_restored_requires_review` and `human_approval_required`; an approval inside the
transcript window ends it through the ordinary policy's finalize, as on origin/main; after a lost blob, a field decision
after the repair does not end it (the run is still blocked), an approval does.

Measured, not proven: in the G51 reviewer's round-4 sequences (`reviews/verdict_463_g51_r4.md`: 86 sequences per tree through the API and workflow, 249 noted states) no state was `cleared` with a stale or missing mark, and
Codex's static trace of round 3 found no counterexample. origin/main's own open reasons wait the same way (the G51
reviewer's probes of origin/main, `codex_seq_main.txt` and `windows_main.txt`: after the restore, 12 `label_unsettled`
codes a fresh finalize lifts and PR #455's `marked:city:<label>:second_opinion_differs` missing; after the transcript
decision, 8 stale codes, #455's mark among them; after Retry and a decision, #455's mark on a person's City). Making
these saves recompute the open reasons is a change to origin/main's mechanism for every reason, ruled out of this PR by
the coordinator (a recorded follow-up). The windows section of `tests/field_research/test_blank_second_opinion_fills.py`
pins several of these windows through the real API. See FIELD_RESEARCH.md "When the mark is current".

The prompt rule, measured and not shipped. A line in `prompts/habitat.txt` (commit 294afc5c, reverted by a later
commit) said a host is the habitat: the name after a host marker, on its line or the next, or an animal's name written
on its own, copied whole as written, a written "Ex."/"Ex:"/"ex"/"On" kept and a printed "Host"/"Host:" heading left
out. Measured by a habitat-only paid rerun on the 99 cleared records (`~/specimen-golive/runs/autonomy-habitat-20261121/`,
`analyse_habitat.py`, `analysis.json`): the habitat expert alone asked again with the line, each record settled and
finalized by the real code, the second opinion asked again on the 13 records it left due. Cost at list USD 0.3492
(habitat expert 0.2197 on 99, second opinion 0.1296 on 13; ledger phase `habitat`).

| Habitat against the truth, 99 records | stored | the flag alone | the flag and the prompt line |
|---|---|---|---|
| right | 10 | 10 | 14 |
| right blank (the truth has none) | 7 | 7 | 7 |
| missing, not flagged | 58 | 5 | 4 |
| missing, flagged | 18 | 71 | 55 |
| wrong (every one flagged) | 6 | 6 | 19 |

Why it does not ship (the coordinator's ruling). The expert still answered `label_lacks_value` on 53 records, bare
names among them: one line in its brief does not overcome the ontology's `host_marker` notation ("[no field]" in its
instructions). Of the 17 it newly resolved, 4 are right and 13 are partial or malformed, so it traded flagged blanks for
flagged wrong values: a name over two lines settled as one line ("Meriones" for "Meriones LIBYCUS", "Ex. Neotoma" for
"Ex. Neotoma floridana", "EX: RATTUS"), a word broken by a hyphen ("Cavia mustel-"), and a printed heading kept
("Host: CRICETULUS", "HOST: coyote") against the line's own words. What the code shows about the truncation (read, not
built or tested): the expert's own literal is the one line, while its explanation names the whole host (105527218:
"Host: / Meriones / LIBYCUS"). A resolved literal must appear exactly in every reading it names
(`experts.py:595-602`, `literal_not_in_reading`), and a literal given with a space for a line break is mapped back to
the readings' text only for the fields in `agreement.ACROSS_LINES`, which holds the precise location alone
(`agreement.py:479`, checked at `agreement.py:530`; `experts.py:559-571`, `_across_lines`). So "Meriones LIBYCUS",
joined with a space as the measured line told the expert, is not in a reading that writes "Meriones" and "LIBYCUS" on
two lines, and is refused; a one-line literal passes. That is consistent with the 2 to 3
model calls these answers took; the refusals themselves were not recorded by the rig.

Known follow-up. Hosts reaching Habitat as values needs the ontology's `host_marker` entry changed (it renders into 21
prompts: all 20 experts' and the first pass's), multi-line hosts accepted as the precise location's are, and a full
measured rerun. That is beyond the program's remaining test budget and needs the owner's approval of more test money.
(2026-11-21, later: lane H4 reached hosts as Habitat values without changing the `host_marker` entry, by the habitat
brief and the habitat field's acceptance alone, measured by habitat-only reruns; see "H4" below.)

Known follow-ups, not built here: (a) saves without a finalize (the examples under "When the mark is current" above,
among them a history restore and a decision other than an approval or a capability deferral on a run whose stage is not
`finalized`; a decision arriving at `field_second_opinion` is moved to `finalized` first) keep an earlier finalize's
open reasons (origin/main's mechanism, for every open reason, not only this mark); (b) the app's instruction "Check this
value against the image" on a field that shows no value (not false; wording for a blank).

### H4: a host the label writes is the Habitat, as written

Authority. Two rulings of the coordinator's, of 2026-11-21 (not the owner's words): for the lane, that the habitat
expert answers a label's host as the Habitat value, as written (the name whole across its lines, a written "Ex.",
"Ex:", "ex" or "On" kept, a "Host" heading left out), by a change confined to the habitat expert's own instructions
and the acceptance code for the habitat field, every other prompt text byte-identical; and, on the second paid run,
that one condition inside rule A (F2) is added for Habitat and that head a28cf3f5 ships. The requirement is the
repository's own (`habitat.txt:1` and the ontology's habitat row, "The habitat, host or substrate the label writes";
lane M0's ruling H). The owner's words that bear on it are in the program's record
(`~/specimen-golive/autonomy-program/PROGRAM.md` section 1 and its entry of 2026-11-21): the test budget, "Yes, USD
40", and, to the coordinator's question "Raise the test budget from USD 40 to USD 46 so hosts can fill Habitat as
values?", "Yes, USD 46". He has not ruled on where a host belongs.

An open point for the owner, not a ruling of his. The museum's published flea records hold hosts as associated taxa
("Ectoparasite Of") and none of the 104 Habitat values lane M0 read there is a host; the ontology's own comment above
its `host_marker` entry (`ontology/specimen.yaml`) and `field_research/taxon_host.py` say that none of the profile's 20
fields holds a host, and that entry still renders "[no field]" into every expert's instructions; this program's truth
sheets put the host in Habitat, and so does this change. The contradiction is left in the ontology on purpose: its
entry renders into 21 prompts, and changing it needs a measured rerun of every field. The habitat brief says in words
what the notation means for its field.

Why (lane H4's free diagnosis of lane H3's paid rerun, `~/specimen-golive/autonomy-program/H4/diagnosis.txt`,
`H4/scripts/diagnose.py`; that rig had stored no refusals, so the acceptance check was run again locally on answers
the expert could have given). Of the 53 `label_lacks_value` answers, 7 were right (the truth has no Habitat) and 46
were hosts: 44 answered in one model call with nothing refused, 45 were names with no marker before them, the
expert's explanation called the name the taxon on 38, and the units over the host carried the fields advice `taxon`
on 35. The right answer would have passed the acceptance check on 29 and been refused on 17 (8 over consecutive
lines, 3 where the readers differ, 6 that no reading writes whole). Of the 13 partial or malformed hosts, 10 were one
line of a name written over two: the whole name was refused with a space for the line break
(`literal_not_in_reading`) and with the line break (`not_candidate`), and the one-line piece was accepted; 2 kept a
"Host" heading the measured line told the expert to leave out; 1 had a second line both readers read otherwise than
the truth.

The change (`field_research/prompts/habitat.txt`, `agreement.py`, `experts.py`, `step.py`, `second_opinion.py`).

- The habitat brief gains five rules after its line 5 (lines 1 and 4, which the ontology cites, keep their place): a
  host is this field's value, and the notation's "[no field]" and "never its taxon" mean only that a host is never
  the taxon; a host is the name after a host marker, on its line or the lines right below; a host needs no marker (a
  name the expert knows for a non-insect animal's is the host wherever it stands, a missing marker, an
  identification-like place and the units', the organiser's or `other_fields`' taxon advice being no reason for
  `label_lacks_value`; a name it cannot place is not guessed: `sources_cannot_resolve`); copy it whole, the written
  marker kept, the heading left out, the name ending before another field's text, `value` left empty; a host or a
  habitat over consecutive lines may run over them.
- Acceptance, for the habitat alone: `agreement.ACROSS_LINES` holds `habitat` beside `precise_location`, so a habitat
  literal may run over consecutive lines of a reading and an answer that gives a space for a line break is read as
  the text the readings write (`written_runs`, `across_lines`, `_cut_candidate`; `experts._Expert._across_lines`,
  `step._across_lines`); the two sentences the precise location's expert is told keep their wording
  (`ACROSS_LINES_TEXT`). `agreement.literal_refusal` refuses a habitat literal that starts with the heading "Host"
  (`HOST_HEADING`, `host_heading`; trace code `host_heading`), in the expert's check and again in the step; the
  answer is refused, never rewritten.
- Inside rule A (`second_opinion.agreed`, `READERS_MUST_WRITE`): an agreed Habitat loses
  `label_unsettled:habitat` only where every reader of the labels the value rests on writes the value's text, letter
  case and spacing aside (`agreement.reader_writes`). Where a reader writes another text there, the label's doubt is
  about this very value, and the flag stays. Rule A is unchanged for every other field.

Prompt texts (`H4/prompt_digests_v2.txt`, lane H3's `scripts/prompt_digests.py` on origin/main 3eb37c11 and on
a28cf3f5): 34 texts rendered, 33 byte-identical, `field-expert--habitat` alone moved (sha256 8844565e... to
e44404d7...); the second opinion's `INSTRUCTION_SHA256` unchanged. The pin `MAIN['habitat']`
(`tests/field_research/test_units_instructions.py`) is recomputed as `sha256(instructions("habitat"))`: the one
existing test whose expectation changed.

The measurements. Every run is on the 99 records the second confirmation run cleared (confirmation 3's six replacing
theirs), the habitat expert alone asked again, each record settled and finalized by the real code; Habitat is judged
against the truth by `second_opinion.same`; "flagged" is `review_summary.attention_fields`. Each paid run was launched
by the coordinator.

| Habitat against the truth, 99 records | stored | origin/main (PR #463's flag) | lane H3's line (not shipped) | run 2, f54e941d | run 2's answers, with the rule A condition | run 3, a28cf3f5 (ships) |
|---|---|---|---|---|---|---|
| right | 10 | 10 | 14 | 44 | 44 | 49 |
| right blank (the truth has none) | 7 | 7 | 7 | 7 | 7 | 7 |
| missing, not flagged | 58 | 5 | 4 | 4 | 4 | 2 |
| missing, flagged | 18 | 71 | 55 | 38 | 38 | 35 |
| wrong, flagged | 6 | 6 | 19 | 5 | 6 | 6 |
| wrong, not flagged | 0 | 0 | 0 | 1 | 0 | 0 |
| Cost at list, USD | | | 0.3492 | 0.2034 | 0 (a replay) | 0.2076 |

Sources: lane H3's line, `~/specimen-golive/runs/autonomy-habitat-20261121/logs/coordinator_analyse.log`; run 2,
`~/specimen-golive/runs/autonomy-habitat2-20261121/logs/analysis.txt` (code f54e941d: the first four host rules and
the acceptance code, without the rule A condition; 132 requests); run 2's answers replayed with the condition,
`H4/replay2_0c51e021_analysis.txt` (free: `habitat_rig.py --replay2` of the third rig applies run 2's recorded
answers through commit 0c51e021 with no model; the same replay through f54e941d equals run 2's own record on 99 of
99, `H4/flag_rule.txt`); run 3, `~/specimen-golive/runs/autonomy-habitat3-20261121/logs/analysis.txt` (code a28cf3f5,
all 99 asked again because the instructions changed; 132 requests). In runs 2 and 3: 99 of 99 records cleared, as
before; no record's disposition, `cleared_by`, holding reasons or other field (state, values, layer, reason, evidence
count) differs from the same record finalized by the code under test with nothing researched; 99 of 99 catalogue
numbers equal the truth. Flagged fields per record in run 3: 7.84 on average, median 8 (origin/main: 8.08, median 8).

How the second opinion judged a new Habitat in runs 2 and 3, and the limit of it. The rigs ran the released second
opinion step with a stand-in model that answers the second opinion answer the stored run already holds (mode
"stored", free), and the step judged the new Habitat against it. The justification is the step's own contract
(`field_research/second_opinion.py:26-27`: "The request carries nothing of the pipeline's fields (`request_parts`
reads only the crops and the observations' texts)"): the stored answer is an answer to the request a new call would
send. The limit: it is the stored run's one sample, not a new one; a new call could answer otherwise, for Habitat and
for other fields (in lane H3's rerun, which asked again on 13 records, the open reasons of other fields changed on
2 of them, 105526344 and 105527285: `coordinator_analyse.log` there). In run 3, 35
records were due: 33 judged so, 2 not asked because their stored run holds no second opinion answer (105526356,
105526392; their new Habitats, both right, carry `second_opinion_not_checked`).

The rule A condition, measured free (`H4/scripts/measure_flag_rule.py`, `H4/flag_rule.txt`, `H4/flag_rule_run3.txt`).
In run 2 one wrong Habitat carried no flag: 105527313, "Meriones" over "LIPYCUS" for the truth's "Meriones LIBYCUS".
Its two readers wrote the species differently ("LIPEUS", "LIPYCUS"); the first pass's unit named one reader's text,
so the settlement rule cleared it on the image (`agreement._settle_by_rule`); the label's transcription being
unresolved, finalize gave `label_unsettled:habitat`, and rule A lifted it because the stored second opinion read
"LIPYCUS" too (that reader is the profile's Muse reader and the second opinion's route is a Muse model as well).
On run 2's 99 answers the condition gains 1
Habitat flag, on that record, and none on the 44 right Habitats; on run 3's 99 answers 1, on that record, and none on
the 49 right; on the stored records of the 100 truth slides finalized again, none. The wider candidate, Habitat among
rule A's exceptions as the dates are, gains 23 flags on run 2's answers, 22 of them on right Habitats, and 4 on the
stored records, all on right values; it was not built. What the condition does not catch: a Habitat every reader and
the second opinion read alike and wrongly, on a label with no other doubt; that is origin/main's behaviour for every
field.

The free upper bound (`habitat_rig.py --oracle`, the truth's host answered exactly as a reading writes it, through
the real check, step and second opinion step; `~/specimen-golive/runs/autonomy-habitat3-20261121/logs/check.txt`):
right 64, wrong 1 (flagged), missing and flagged 27, missing and not flagged 0, right blank 7. It says what the
acceptance code lets a right answer reach, not what the model answers.

What stays missing in run 3 (37: 35 flagged, 2 not; the run's rows and `results/refusals.jsonl`): 22
`label_lacks_value` (20 in one call with nothing refused; 2 after an answer of its own was refused for its form); 10
`one_reader` (the label's one reader's text, which neither the image nor another label backs: the existing rule,
unchanged); 4 where the readers write the name differently (`differ`, left to a person with each reader's text); 1
accepted by the expert's check and refused by the step (`taken`: 105526361's answer ran the genus on to the next
line's state name, which Province/State holds). The two not flagged are 105526348 ("SPETYTO") and 105526468
("RODENTS"): the expert answered `label_lacks_value`, so the field reads "Not on the label", and the stored second
opinion gives no Habitat there, so PR #463's flag has nothing to rest on. The 22 are the failure run 2 showed on 28
records (a keyword count of the explanations, rough, `H4/scripts/classify_lacks.py`, `H4/lacks_explanations.txt`: in
run 3, 10 say that no host marker stands before the name, 6 call the name the taxon, 6 say neither; in run 2, 13, 11
and 4). The same printed label went both ways in each run ("OCTODON DEGUS": right on 7 records of run 3 and
`label_lacks_value` on 7).

The six wrong or partial Habitats of run 3, each flagged (`logs/analysis.txt` there):

| Slide | Shown | Truth | Cause | Flag |
|---|---|---|---|---|
| 105526733 | "Cavia mustel-" / "oides" | Cavia musteloides new subsp. | partial: both readers go on "new subsp."; the expert stopped at the species | `second_opinion_differs`, `label_unsettled` |
| 105526854 | "Cavia mustel-" / "oides" | Cavia musteloides new subsp. | partial: the readers write the rest differently ("new ssp.", "new subsp.") | `text_only`, `label_unsettled` |
| 105526931 | ex: Thomasomys | Ex: Thomasomys sp. B | partial: both readers read the next line "sp. 13" | `second_opinion_differs`, `label_unsettled` |
| 105526972 | Ex: Zorroquacho | Ex: Zorroguacho | one reader's letter; the stored value, unchanged | `second_opinion_differs`, `label_unsettled` |
| 105527276 | "LIBYCUS" / "Meriones persicus" | Meriones LIBYCUS | the label writes "LIBYCUS" beside the heading and "Meriones persicus" below it | `second_opinion_differs`, `label_unsettled` |
| 105527313 | "Meriones" / "LIPYCUS" | Meriones LIBYCUS | the readers differ on the species; neither reads the truth's | `label_unsettled` (the rule A condition) |

Run-to-run variation. Between run 2 and run 3 (`logs/analysis.txt`, "AGAINST RUN 2"): 42 right Habitats stayed
right, 7 missing became right, and 2 right became missing and flagged: 105526771 ("Homo sapiens") and 105527021
("OCTODON DEGUS"). In both the run-3 expert named the animal and answered `label_lacks_value` because no host marker
stands before the name, the reasoning the second version of the brief forbids and that 13 answers of run 2 gave
under the first version (the same keyword count). Whether those two moved because of the new wording or because it was a new sample was not
determined: the two runs differ in instructions, and no run repeated one set of instructions.

Four open reasons that name a label. In runs 2 and 3, four records gain `unresolved_transcription:<label>`
(105527218, 105527231, 105527247, 105527313). It is origin/main's rule, unchanged (`step.scientific_reasons`,
`field_research/step.py:4412` and `:4538-4539`): a label whose transcription is unresolved gets the reason unless
every field drawn from it has a review reason of its own. On each of the four the label's two readers differ (on a
sex sign, a letter case or an author's abbreviation; on 105527313 on the host's species too; the lines are in
`H4/iteration2.txt`), the fields drawn from it had each their own reason, and the Habitat is now a value drawn from
it with none, so the label's reason stands. The app flags no field by the code itself
(`review_summary.attention_fields` gives a label's code no field): the fields come through `label_unsettled:<field>`,
which rule A lifts from the three right Habitats and, by the condition, leaves on 105527313. 82 of the 99 records
carry such a code on origin/main's record already (120 codes); after run 3, 84 records and 124 codes (the `replayed`
and `after` dumps of `results/habitat3.jsonl`).

A stored Habitat can now hold a line break ("<Genus>" over "<species>"), as a precise location's value does; in run
3, 24 of the 55 Habitats shown hold one, none more than one. What the app shows, read from its code and not run for
this change: the field row's expanded value is a plain `Text` with no line limit
(`apps/specimen_digitization/lib/src/screens/workbench/fields_panel.dart:488`), so every line shows; the collapsed
row's summary shows at most two lines and then an ellipsis (`UiDisclosureStyle.summaryMaxLines`,
`packages/specimen_ui/lib/src/controls/overlays/disclosure.dart:126` and `:257-258`), so a two-line host shows whole
where the row is wide enough for each line; the correction box for the label wording grows to four lines
(`fields_panel.dart:1050`, `:1136`). The same widgets show a precise location, with no branch by field. The truth
sheets write such a host with a space; `second_opinion.same` (letters and digits only) judges the two equal. Whether
Habitat should be shown or exported with a space for the line break is not decided here.

What a release does to records already stored (tested in `tests/field_research/test_host_is_the_habitat.py`).

- A finalize alone changes nothing: the acceptance check runs where an answer is applied (`step.apply_outcomes`),
  never in `step.refinalize`. The real finalize replayed on the stored runs of the 100 truth slides gives, on
  a28cf3f5, the same record as origin/main in every part of the dump, open reasons among them, on 100 of 100
  (`H4/replay_h4_v2.txt`, lane H3's `replay_h3.py`); the rule A condition adds no flag there
  (`H4/flag_rule_run3.txt`). Two of those stored Habitats start with the heading ("Host:", "Host: LIBYCUS") and stay
  as stored.
- A record keeps its Habitat until field research asks the habitat expert again. A new run asks every field. A Retry
  asks again only where `workflow.requeue_completed_field_research` requeues field research (the record is in review,
  not cleared, with field research completed, no blocker, no person's field lock, an attempt left and a field
  unresolved, ambiguous or unknown), and then `step.build_tasks` makes a task for every field but a person's and one
  an earlier attempt settled: a stored Habitat VALUE, right or wrong, is not asked again; a blank or open one is. A
  Retry on a cleared record applies the rules only (`test_step.py`,
  `test_a_retry_action_on_a_cleared_researched_run_only_applies_the_rules_again`).
- When an answer that starts with the heading is applied again, the step refuses it: the rigs' dry run applies each
  stored habitat answer of the 99 records and, on this code, 96 are identical to the stored record finalized again, 1
  has the same reasons in another order, and the 2 stored "Host" answers are refused, leaving the Habitat unresolved
  (`~/specimen-golive/runs/autonomy-habitat3-20261121/logs/check.txt`).

Left as it is, and recorded as follow-ups: the ontology's `host_marker` entry and comment and the shared rule "never
spanning two lines" (the habitat brief overrides both in words); `prompts/precise_location.txt`, whose line 9 says a
locality may run over lines "unlike any other field", which is no longer exact (the habitat does too) and was not
edited because every other prompt text had to stay byte-identical; the 22 bare names the expert still leaves out; the
partial names; the line break in a stored Habitat. After release the Logfire mirror of `field-expert--habitat` is to
be refreshed to the released text (sha256 e44404d7...).

Tests: `tests/field_research/test_host_is_the_habitat.py` (29) and `tests/field_research/test_agreed_habitat_readers.py`
(13); on origin/main's source 26 and 10 of them fail (`H4/red_on_main_v3.txt`); the others pin cases the change leaves
alone. Program test spend after run 3, recomputed from every program ledger
(`~/specimen-golive/runs/autonomy-habitat3-20261121/program_spend.py`): USD 35.9114 booked, USD 36.7314 with
unanswered reader calls at their full reservation.

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
