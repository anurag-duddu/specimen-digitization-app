# Program plan: reading units and the specimen ontology

Owner's mandate, 2026-10-26: "build it once and for all, properly test it and run it and get it
working. It's not about adding more and creating more dead code. It's about building it right in a
maintainable way replacing, upgrading, adding, removing where needed. [...] once you spec it out
we'll decide the models, what they work on, split it all up and execute. [...] Plan it well and
iterate and get to final steady state."

Spec: [`docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md`](../../product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md).

Revised 2026-10-26 after the Claude review of head 3021b7aa8 and the Codex adversarial review of
head 3ed1453b2 (pull request #418). Every finding of both is answered in the text of the spec or of
this plan, not in a reply.

## 1. The goal and the steady state

The pipeline becomes: readers (N) -> first pass (reading units, never settles) -> field experts
(settle from the units, the lookups and the ontology, in two rounds) -> review for what remains.
Measured on the reference set (WP 0), the steady state is reached when all four hold against the
baseline:

1. More fields settle right, no more settle wrong, fewer go to review. Counted per field with the
   strict rule of the 2026-10-25 scorer (`score.py`, copied into the repository by WP 0): for a
   field the label writes, right, wrong or review; for a field it does not write, cleared, review or
   wrongly settled; every count with its denominator. "No more settle wrong" holds per field, not in
   total: a wrong elevation is not paid for by a fixed code. The baseline on the 12 pilot labels is
   the 2026-10-25 pair arm (`~/specimen-golive/runs/free-harness-20261025/score_full.md`,
   full-r1/pair): primary fields 27 right, 9 wrong, 13 review; fields expected absent 33 cleared, 2
   review, 0 wrongly settled. The baseline on the 20 further specimens is WP 0's run of today's main.
2. Adding a reader never turns a right settlement into a wrong one, and settled-right falls only at
   units the image judges uncertain. Counted per unit, the three-reader arm against the pair arm,
   in every measurement.
3. Every settled value carries its basis (`label`, `derived`, `inferred`) and the app shows it: 0
   settled values without a basis on the reference set, and a widget test per basis.
4. Nothing dead remains: every row of section 5 is in its stated end state (removed, kept, or in
   the work package it is deferred to), and the closing report names each row.

A gate is met or the phase stops: the gap is analysed, the work package is reworked and the
measurement is repeated. Nothing proceeds on an explanation.

## 2. Phases and work packages

Each work package is one branch, one pull request, two reviews on its exact head: one independent
reviewer for the sign-off (G51, `AGENTS.md`: one independent reviewer per head, Claude or Codex)
and Codex gpt-6.1-sol as the adversarial reviewer in addition (the owner, 2026-10-26: "Use codex as
needed for adversarial reviews and checks"); merged and released on green per the owner's standing
instruction, then pruned. The strict-main delta check applies to every merge. Models and effort: the
standing table in `docs/execution/golive/PLAN.md` section 6 (the session table: Opus 5.5 with its
stated efforts for harness, data and client work) applies; this plan assigns none of its own,
because the owner decides them (his mandate above).

Cost baselines, from the 2026-10-25 ledgers: a first-pass call USD 0.000512 at list with two readers
and USD 0.000738 with three (`~/specimen-golive/runs/three-readers-20261025/ledger.jsonl`, 144 calls
per arm); field research USD 0.047 per specimen at list (`score_full.md`, full-r1/pair,
`fr_usd_list_mean`).

### Phase 0: the reference set

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| 0 Reference set and baseline | A frozen manifest: the 12 pilot labels (t1-321, 01b79931-L2, t1-322, e98a924c-L2, t1-323, cb903c0e-L2, t1-329, t1-330, 9cc24b07-L1, t1-324, t1-325, t1-328; truth: `tests/fixtures/field_model_pilot_rows.json`, S8's eyes-on table) and 20 further specimens from the 1,000 real slides, chosen before any new code runs, for having two or more labels, whose values a reviewer has accepted in production (truth: the accepted values, exported read-only); specimen ids, label ids and blob digests in the manifest. The scorer: the 2026-10-25 `score.py` strict rule, copied into the repository beside the manifest; one scorer for the whole program. The baseline for the 20 specimens: today's main, pair arm, two repeats, live first pass | `tests/reference/units_program/manifest.json` (new), `tests/reference/units_program/score.py` (new), `tests/reference/units_program/README.md` (new); the run under `~/specimen-golive/runs/units-baseline-<date>/` | The manifest names 12 labels and 20 specimens with digests; a test fails when a digest or the truth file changes; the baseline report gives every count of criterion 1 with its denominator, for both arms on the 12 labels (the 2026-10-25 scores) and the pair arm on the 20 specimens; cost at most USD 2.5 at list, costed before the run |

### Phase 1: the ontology's first version and the reading units

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| 1.0 Ontology v1 | The things, the profile's 20 fields with their Darwin Core names, the label types, the conventions the units need (`means` and `fields` depend on them), seeded from `harness_knowledge/insects.py`'s `Notation` table and `common.txt`'s label notations; a loader that validates the file and renders it to prompt text | `src/specimen_digitization/ontology/specimen.yaml` (new), `ontology/__init__.py` (new) | The loader refuses a field not among the profile's 20 keys, a label type naming no field, a convention with no source, and an unknown key (tests); the rendered text is pinned by a test; ten fixture units from the pilot labels (CNHM., P.I., Elev.6400', H. Hoogstraal leg., Sp.30 ♀, 6-Sept-1946, P-95-81-16, IV-29-68-4, Yepocapa, 4800ft., Chimaltenago) each get the fields and meaning the file gives them, pinned by a test; the independent reviewer checks every statement against the pilot labels and the existing briefs and lists the check in the review; a statement nothing backs is cut or marked `not yet` |
| 1.1 Unit record, storage, app reader | `ReadingUnit`/`ReadingUnits` models; a new list on the run with an empty default (additive, through the contract gates); a new projection field; the app's reader for it with its test; the wire contract documented | `application/reading_units.py` (new), `application/domain.py` (one additive field), `application/projection.py`, `docs/execution/golive/DATA_CONTRACT.md`, `apps/specimen_digitization/lib/src/models.dart` (or a new file) and its test | A run with units round-trips through the repository and the normalized projection (a test); a stored run from before this change (fixture) loads unchanged and projects without the field; the app parses a thread with the field and one without (Dart tests); `tests/research_harness/test_thread_embedded_schema.py` stays green; no existing model or enum changes, and the PR body lists the one additive field (golive/PLAN.md section 6's rule for `domain.py`) |
| 1.2 First pass v2 | Prompt and output schema produce the units for every label, agreed labels and person-decided labels (one reading) included; the ontology v1 baked into the prompt; the tiling check and the range check of spec section 2, the retry text naming the failed check; `selected_reader` (the reader every unit's `image` names, else null) and the per-difference verdicts derived by code from the units, so `FirstPassDecision`, `workflow.py`, `projection.py`, `step.py` and the first-pass tests keep working until WP 1.8; the scheduler change (a first pass for every label, `workflow.py`) as its own commit, costed | `application/first_pass.py`, `prompts.py` (`_DISAGREEMENT_ADJUDICATION_DEFAULT` replaced; the managed variable keeps its name), `application/workflow.py` (the scheduling rule), `integrity.py` | On the 12 labels, three readers, two repeats, live: every accepted answer tiles every reading (code-checked, 100%), with the refused-and-retried count reported; `image` names a text no reader wrote in 0 units (code-checked); the derived `selected_reader` and verdicts keep `tests/test_first_pass.py` and `tests/test_first_pass_null_text.py` green; unit-to-field precision and recall of `fields` against the organiser's candidates on the 12 labels, per field, reported; the share of units whose `image` is the same in both repeats, reported; cost per call at most 1.5 x USD 0.000738 with three readers and 1.5 x USD 0.000512 with two; the scheduler change adds one call per agreed label at that rate, reported per specimen |
| 1.3 Experts take units | The expert request carries every unit and every raw reading; `FirstPassAdvice` removed; the settlement order of spec section 3 in `agreement.labels`, with `BY_PERSON` and `BY_IMAGE` added and `BY_FIRST_PASS` removed; `confirmed_against_image` replaced by `image_names` and the `image_source_conflict` outcome; the finding codes `settled_<reason>`; `common.txt` rule 4 and the five tool-less briefs rewritten; the ontology v1 in the experts' instructions | `field_research/contracts.py`, `experts.py`, `agreement.py`, `step.py`, `prompts/common.txt`, the five briefs | Fail-first tests, one per reason in the order and one for `image_source_conflict`, each with its case: the person binds against an exact source match; a source confirms B and the image names A -> review with both; the image names C where A and B copy one wrong text -> C settles; the image is uncertain there -> review, never the copied text; a value with basis `inferred` that names no rule is refused. Kept green under the new names: `test_a_person_decided_transcript_binds_its_label_against_an_exact_source_match` (`BY_PERSON`), `test_with_no_pick_another_label_whose_readers_agree_settles_the_field` and `test_a_label_one_reader_read_backs_nothing` (`BY_OTHER_LABEL`), `test_readers_that_differ_only_in_case_or_spacing_agree_on_the_first_readers_spelling` (`BY_AGREEMENT`), `test_a_label_whose_first_pass_was_given_up_goes_to_review_however_its_fields_settle` (`first_pass_given_up`); `tests/field_research` green; a search for `FirstPassAdvice`, `BY_FIRST_PASS`, `confirmed_against_image` and `first_pass_followed|overridden|absent|conflict` finds nothing under `src/` |
| 1.4 Organiser | Kept: its call, its evidence rows with offsets (`harness.py`) and its candidates (`step.py`) stay; nothing is removed | none | Its candidates are the reference for 1.2's unit-to-field measure; its own precision and recall against the truth are reported beside the units' in 1.5 |
| 1.5 Measurement | The rig of 2026-10-25 (`~/specimen-golive/runs/free-harness-20261025/run_arm.py`) with a live first pass per repeat (no replayed rows), pair and three-reader arms, two repeats, the whole reference set, scored by WP 0's scorer against the baseline | `~/specimen-golive/runs/units-<date>/` (off-repo); `scripts/lab/` if reusable | Criteria 1 and 2 met, every count with its denominator; cost at most USD 7 at list, costed before the run; the report also gives the organiser's and the units' field precision and recall per field (for WP 2.5). Not met: the phase stops |
| 1.6 App | The readings panel shows the units per label (readers' texts, what the image names, the meaning, the fields) in place of the selected reading and its differences; a record without units (before 1.1) keeps today's view; the finding codes named in copy | `apps/specimen_digitization/lib/src/screens/workbench/readings_panel.dart`, `lib/src/reading_alignment.dart`, `lib/src/screens/workbench/blockers.dart`, goldens | Widget tests for five states: the image names a reader; `uncertain`; `not visible`; a person-decided label with one reader; a record without units. Size-class goldens at compact, medium and expanded (`design/05-responsive-and-platform-adaptation.md`, `WindowClass`); every string passes `design/02-ux-writing-guidelines.md`; every control has a semantic label and a 48 dp target (CLAUDE.md) |
| 1.7 Docs | `FIELD_RESEARCH.md`, `HARNESS.md`, `DATA_CONTRACT.md`, the closeout entry; the `verbatim_dts` brief's stale sentence ("The museum has not yet confirmed what D/T/S stands for") replaced by the PRD's answer of 2026-10-07 (`PRD.md` section 22, question 3: non-standard collecting-event date and time expressions), a one-line prompt change pinned by a test, and the docs that repeat it | docs; `field_research/prompts/verbatim_dts.txt` | Every sentence that says what the code does names its file and line or its test; the independent reviewer checks each and lists them in the review comment; a sentence that overreaches its code or test blocks the merge (the repository's standing rule) |
| 1.8 Remove the derived first-pass fields | `FirstPassOutput.selected_reader` and `DifferenceVerdict`/`verdicts` removed with 1.2's derivation; `prompt__field_harness` and its users removed; the tests and docs listed in section 5 updated | `application/first_pass.py`, `prompts.py`, `tests/test_first_pass.py`, `tests/test_first_pass_null_text.py`, `tests/test_model_transport_timeouts.py`, `tests/test_reported_usage_settles.py`, `tests/research_harness/test_people_independent_regressions.py`, `tests/test_prompts.py`, `tests/test_bounded_telemetry.py`, `docs/execution/golive/HARNESS.md`, `docs/OBSERVABILITY_AND_EVALUATION.md` | A search for `selected_reader`, `DifferenceVerdict`, `FIELD_HARNESS` and `prompt__field_harness` finds nothing under `src/` and `tests/`; a new `FirstPassDecision` names no reading and lists the alignment's differences with verdict `uncertain` (today's path for a capped first pass, `first_pass.py`), and the integrity check of records already written (`integrity.py`, `g19_pick`) stays green; CI green |

### Phase 2: the ontology's second version

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| 2.1 Relations and rules | The file gains the relations, the constraints and the derivation and inference rules of spec section 4, each with an id, a plain statement, how it is checked (code, model, or not yet), its sources and its Darwin Core term; the dependency order for round 2; the highest-point table (Wikidata, cited per row); drafted from the spec, the pilot labels, the existing briefs and `insects.py`. The owner and the collection's curators read the rules once, here (section 6) | `ontology/specimen.yaml` | The loader refuses a rule missing any part and a dependency cycle (tests); the rendered text is pinned; the rules marked `code` match 2.3's tests one to one (a test lists both sides); the reading by the owner and the curators is recorded in the PR body with its date, and a rule they correct is changed before merge |
| 2.2 Baked in | The rendered rules enter every model's instructions: readers, first pass, organiser, every expert; `insects.py`'s `Notation` table folded into the file (one source of notations) | `prompts.py`, `field_research/prompts/common.txt`, the reader prompts, `harness_knowledge/` | Prompt tests pin the rendered text in each prompt; on the 12 labels, field research at most 1.2 x USD 0.047 per specimen at list and the first pass within 1.2's bound; the readers' new outputs on the 12 labels compared with the recorded readings (`three-readers-20261025/cases.json`) and every difference listed in the PR body |
| 2.3 Code-checked rules, two rounds, basis | The place chain completed at every level and for exact candidates (`parents_refusal`); the elevation unit rule (a reader's mark, the country's highest point, the foot reading possible); date order with the same day allowed and partial dates compared on the parts both have; label types as routing that never excludes a field; the two rounds with the file's dependency order; the optional `basis` on each value part with the app reader in the same PR, old records unchanged, and a hold for runs in flight before the first inferred value is written (`PRD.md` rule 5: "The app reader ships first"); `derive.py` reads its rules from the file | `field_research/ontology_checks.py` (new), `derive.py`, `agreement.py`, `step.py`, `domain.py` (one additive optional field), `apps/.../models.dart` and its test | Fail-first tests per rule with named cases: settled Coles County, then an exact "Chicago" under Illinois -> refused; 6400 with B's mark, Philippines -> 6,400 ft `inferred`; 6400 with no mark -> review; 16000 with a mark -> review; a reader wrote "m" -> today's `UNIT_DIFFERS` path unchanged; collect 1946-09-06, determine 1946-09-06 -> allowed; determine before collect -> review with both; "1946" against "1946-09-06" -> agree; a determination label writing a locality -> the locality expert receives it; the province expert in round 2 receives the settled country; a cycle in the file fails the loader. Over the reference set's results, 0 derived or inferred values without a rule and its inputs. The app parses a value with and without `basis` (Dart test); an old record shows no basis (PRD: never shown as `inferred`) |
| 2.4 Units put together | Within one label: genus + species; day + month + year. Across labels: the place chain and the date only, where one label writes the whole and another a part of the same value. A taxon never across labels; conflicting labels go to review with both | `agreement.py`, `step.py` | Tests: genus and species on one label -> one taxon; genus on one label, species on another -> review with both; "6-Sept-1946" and "1946" on two labels -> 1946-09-06; "6 Sept" and "1946" on two labels -> review; two labels with different localities -> review with both. Measured in 2.6 on the 20 multi-label specimens: assembled values right, wrong, review, with the denominator |
| 2.5 Organiser decision | The rule: if 1.5's report shows the units' `fields` precision and recall each at or above the organiser's candidates' on every field, the organiser call is removed, its evidence rows replaced by rows written from the units (literal, label, offsets, as `harness.py` writes them today) so `Candidate.evidence_id` and `stored_candidates` still hold, and `apply_candidates` goes with its tests; otherwise the organiser stays and section 5's row is marked kept | `application/harness.py`, `application/production.py`, `application/organiser.py`, `extraction_guard.py`, `field_research/step.py`, the tests in section 5 | Either no call to `apply_candidates` remains, the rows written from units pass `tests/test_evidence_integrity.py`, and the closeout records the numbers that decided it; or the organiser is kept, the row says so, and the closeout records the numbers |
| 2.6 Measurement | The same rig on the whole reference set, the 20 multi-label specimens included | off-repo | Criteria 1 to 3 met; cost at most USD 7 at list, costed before the run. Not met: the phase stops |
| 2.7 Docs | The ontology documented for curators; closeout | docs | As 1.7 |

### Phase 3: people, conventions, retirement

| WP | Scope | Files | Acceptance |
|---|---|---|---|
| 3.1 People lookups | No people source is approved today, and a collector-name query is an owner exception (`golive/PLAN.md` 4.8, `GEOREFERENCING.md` D4). The ask (Wikidata persons first, Bionomia if needed) goes to the owner with phase 1's measurement; built only on his approval | `field_research/sources.py`, `contracts.py` (`FIELD_TOOLS["collectors"]`) | The owner's approval quoted in the PR body with its date; on the reference set the three pilot collectors (H. Hoogstraal, F.G. Werner, R.D. Mitchell) each matched, or reported not found with the query recorded; collectors settled-right at or above 2.6's count, settled-wrong 0 new; a run with no match at all fails (it proves nothing) |
| 3.2 Conventions table | Institution names and dates, slide-code formats, unit conventions, each with a source, in the ontology file; no second owner reading (section 6) | `ontology/specimen.yaml` | The loader refuses an entry with no source; a test checks "CNHM" -> 1943-1966 and the pilot slide-code formats ("IV-29-68-4", "10-6-78-1a") against the file |
| 3.3 Steady-state run | Reference set, two repeats, both arms; the report that closes the program | off-repo | All four criteria met; cost at most USD 7 at list; the report names every row of section 5 and its end state |
| 3.4 research_harness retirement | Move what the eleven users outside the package import (section 5) into `field_research/` or `application/`, then delete the six-specialist run path (`SPECIMEN_RESEARCH_HARNESS=on`) and its six Logfire mirrors. A separate pull request with its own review | `research_harness/`, the eleven users, `enablement.py`, `tests/research_harness/` | After the move the eleven users import nothing from `research_harness/`; `SPECIMEN_RESEARCH_HARNESS` takes `off` and `fields` only (`scripts/ci/runtime_settings.py` stays at `fields`); `research_harness/` and `tests/research_harness/` deleted or moved; the six mirrors removed where write access exists, else recorded as unused; CI green |

## 3. Order and gates

The same list as the spec's section 7, one lane at a time. A gate is met or the phase stops.

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

## 4. Measurement budget

Estimate first. One full measurement is 32 specimens x 2 arms x 2 repeats x about USD 0.05 of field
research (the 2026-10-25 mean, USD 0.047 at list), about USD 6.4, plus the live first pass at about
USD 0.001 per label per arm per repeat (about 60 labels: USD 0.24): about USD 7. Three full
measurements (1.5, 2.6, 3.3): about USD 21. WP 0's baseline on the 20 specimens (pair arm, two
repeats): about USD 2.5. Program cap: USD 25 at list across all runs. The coordinator records that
the owner said on 2026-10-26 that rerunning the specimens is within budget. Each run is costed at
list before it starts and reported after; a run that would pass the cap waits for the owner. The
2026-10-25 program used USD 2.93 of its USD 3.

## 5. Dispositions

Every symbol or module the design touches, with its users today (`file:line` on main b2dcd50d6),
the work package that migrates them, and its end state. "Deferred" always names the work package
that decides it; nothing is left open.

| Symbol or module | Users today (file:line) | Work package | End state |
|---|---|---|---|
| `FirstPassOutput.selected_reader` | `application/first_pass.py:291,303,321-322,493`; `workflow.py:999-1010` (through `FirstPassDecision.selected_observation_id`); `projection.py:454-461`; `tests/test_first_pass.py:112,119,128,160,166,224,369,384,466,524,539,1008`; `tests/test_first_pass_null_text.py:3-43`; `tests/test_model_transport_timeouts.py:30,66`; `tests/test_reported_usage_settles.py:5-145`; `tests/research_harness/test_people_independent_regressions.py:43`; `docs/execution/golive/HARNESS.md:480,485` | 1.2 derives it from the units; 1.8 removes it | Removed in 1.8, every test and doc listed updated |
| `DifferenceVerdict`, `FirstPassOutput.verdicts`, `output_problems` | `first_pass.py:282,297,316-335`; `tests/test_first_pass.py:27,107,110-200` | 1.2, 1.8 | `output_problems` rewritten to the tiling and range checks in 1.2; the verdicts derived in 1.2, removed in 1.8 |
| `FirstPassDecision`, `FirstPassDifference`, `Run.first_pass_decisions`, `UNRESOLVED_VERDICTS`, `OPEN_VERDICTS`, `is_material` | `domain.py:175,185,512`; `first_pass.py:35-36,44,329,396-558`; `workflow.py:18,398,966,999-1020`; `projection.py:60,428-461`; `integrity.py:125-127`; `active_graph.py:34`; `lane_costs.py:414`; `model_runtime.py:15,277` | none | Kept: the run's pinned record and the integrity check of records already written. From 1.8 a new decision names no reading and its differences carry verdict `uncertain` (today's path for a capped first pass) |
| `g19_pick`, `supports` | `first_pass.py:361,512`; `integrity.py:125,179`; `workflow.py:967,1010`; `tests/test_first_pass.py:803-992` | none | Kept (the integrity of written records) |
| The scheduling rule `len(texts) > 1` and the two-reading floor | `workflow.py:2075`; `first_pass.py:404` | 1.2 | Replaced: a first pass for every label with one reading or more; costed in 1.2 |
| `_DISAGREEMENT_ADJUDICATION_DEFAULT` | `prompts.py:101,168`; `tests/test_prompts.py:56`; `tests/test_bounded_telemetry.py:467`; `HARNESS.md:72` | 1.2 | Replaced by the units prompt under the same `PromptName`; the managed variable `prompt__transcription_disagreement_adjudication` keeps its name (renaming it needs Logfire write access the project does not hold) |
| `FirstPassAdvice`, `Reading.first_pass`, the experts' `first_pass` document key | `field_research/contracts.py:97,137`; `step.py:102,221,234,246,259`; `agreement.py:1265,1406`; `experts.py:311-320`; `tests/field_research/test_first_pass_advice.py:195-197,566-569` | 1.3 | Removed; the request carries the units instead. `person_decided` (`experts.py:324-326`, `common.txt:8`) stays as the one-reader form of a person's label |
| `BY_FIRST_PASS` | `agreement.py:1223,1401,1408,1556`; `test_first_pass_advice.py:248` | 1.3 | Split: its person-binding use becomes `BY_PERSON` (behaviour kept; the test rewritten to the name); its preferred-reader use is removed |
| `BY_AGREEMENT`, `BY_SOURCE`, `BY_NEAR_SPELLING`, `BY_SAME_PLACE`, `BY_OTHER_LABEL`, `MIN_BACKING_READERS`, `_spelling` | `agreement.py:1223-1228,1256,1377-1396,1508,1538-1549,1645`; `test_first_pass_advice.py:169,223,229`; `test_agreement.py:213,256` | 1.3 | Kept as reasons 2, 4, 5 and 6 of the order; `BY_AGREEMENT` is no longer the gate for the other reasons; `_spelling`'s "the preferred reader's spelling" becomes "the text the image names, else the first reader's" (`test_readers_that_agree_settle_on_the_spelling_of_the_reader_the_first_pass_preferred` rewritten so) |
| `confirmed_against_image`, `_confirms`, `_preferred_spelling`, `Label.preference` with `FOLLOWED`, `OVERRIDDEN`, `ABSENT`, `CONFLICT`, `_preference` | `agreement.py:110-115,1230,1295-1337,1353-1361,1419-1424,1522-1556,1611`; `contracts.py:109`; `step.py:2390-2455`; `FIELD_RESEARCH.md:892,898`; `HARNESS.md:52` | 1.3 | Replaced by `image_names` (the unit's `image`) and the `image_source_conflict` outcome; the near-spelling rule that keeps the label's spelling (`:1361`) re-expressed on units |
| `first_pass_followed`, `first_pass_overridden`, `first_pass_absent`, `first_pass_conflict`, `first_pass_code`, `_first_pass_preference`, `FIRST_PASS_RULES` | `step.py:2385-2460`; `test_first_pass_advice.py:19,153,166,183,278,302,309,327,350,377,396,620-644`; `FIELD_RESEARCH.md:898,1345`; `HARNESS.md:52` | 1.3 | Replaced by `settled_<reason>:<field>:<label>` and `image_source_conflict:<field>:<label>` |
| `first_pass_given_up`, `GIVEN_UP`, `give_up`, `given_up_regions` | `first_pass.py:67-68,638,654`; `workflow.py:991,2012`; `step.py:3735-3751`; `tests/test_first_pass_given_up.py`; `tests/test_first_pass_transient_recovery.py:159`; `tests/test_first_pass_stuck_recovery.py:220`; `tests/test_reconcile_unknown_outcome.py:776`; `tests/test_lane_routes.py:296`; `tests/test_extraction_recovery.py:31-798`; `tests/test_rate_limit_refusal.py:372,384`; `tests/field_research/test_step.py:1348-1370`; `tests/conftest.py:73`; `HARNESS.md:237,277` | none | Kept untouched: a failure marker, not a preference code |
| `common.txt` rule 4 and its `first_pass` paragraph (lines 9, 15, 22); the five tool-less briefs' first-pass sentences (`verbatim_dts.txt:5,7` and the other four) | the experts' instructions | 1.3; 1.7 for `verbatim_dts.txt:1,3` | Rewritten to the order of spec section 3; the stale D/T/S sentence replaced by the PRD's answer |
| `harness.apply_candidates` with its unanimity rule (`_label_value`, `_settle`) and the organiser call | `harness.py:78,197-255,329`; `organiser.py:22,35`; `extraction_guard.py:3`; `production.py` (`_extract_direct`); `step.py:275` (`stored_candidates`); `contracts.py:147` (`Candidate.evidence_id`); `tests/test_organiser.py:41-965`; `tests/test_application.py:506,531`; `tests/test_evidence_integrity.py:182,204`; `tests/test_extraction_kind_guard.py:75,118`; `tests/field_research/test_step.py:33,77,198`; `test_field_research_e2e.py:29,108,113`; `test_location_last_gaps.py:59,425`; `tests/research_harness/test_organiser_handover.py:665`; `test_organiser_handover_composer.py:16,109`; `test_organiser_raw_reading_composer.py:8-75`; `test_organiser_raw_reading_evidence.py:6-109`; `test_temporal_composer.py:21-60`; `test_measurement_keyed_admission.py:7,84`; `HARNESS.md:561,578` | 1.4 keeps; 1.5 measures; 2.5 decides | Deferred to 2.5, by the rule written there. Its unanimity rule shapes only its proposal, which is never evidence (`common.txt:6`), so it is not changed on its own |
| `prompt__field_harness`, `PromptName.FIELD_HARNESS`, `_FIELD_HARNESS_DEFAULT` | `prompts.py:16,129,171-175`; `production.py:1418` (pins every `PromptName`; nothing to change once the member is gone); `tests/test_prompts.py:73`; `tests/test_bounded_telemetry.py:468`; `docs/OBSERVABILITY_AND_EVALUATION.md:124`; the Logfire mirror | 1.8 | Removed with every user listed; the Logfire variable deleted where write access exists, else recorded as unused in the closeout |
| `research_harness/`, `SPECIMEN_RESEARCH_HARNESS=on`, the six-specialist Logfire mirrors | outside the package: `field_research/sources.py:64-67`; `field_research/checks.py:29-30`; `field_research/step.py:4051`; `application/native_drain.py:16-17`; `application/human_field_carry.py:17`; `application/production.py:240,256,275`; `application/projection.py:627`; `application/api.py:2405,3063-3119`; `application/cli.py:79-80`; `application/derivation_readiness.py:22`; `application/worker.py:710,959`. Also `research_harness/workflow_bridge.py:353` (`program_budget`: old research liabilities count against the headroom), `enablement.py`, `scripts/ci/runtime_settings.py:142` (`fields`), `tests/research_harness/` | 3.4 | Deferred to 3.4, a separate pull request: move what the eleven users import into `field_research/` or `application/`, then delete the six-specialist run path (`on`) and its mirrors. Not deleted in phases 1 and 2 |
| `_deciding`-era remnants | none in production (`FIELD_RESEARCH.md:829`: gone); a test helper `settle_deciding` at `tests/field_research/test_agreement.py:2133` | none | Dropped from the list: nothing to remove |
| `harness_knowledge/insects.py` `Notation` and `PLACE_ALIASES`, `harness_knowledge/__init__.py` `instructions_for` | the organiser's instructions | 1.0 seeds from it; 2.2 folds it in | Folded into the ontology file in 2.2: `instructions_for` renders the file's notations and the table is deleted |
| `tests/fixtures/field_model_pilot_rows.json` | the truth for the 12 labels (the 2026-10-25 `score.py`) | 0 | Kept; a digest test guards it |

## 6. What the owner does

The owner and the collection's curators read the ontology's rules once, when WP 2.1 drafts them
(they are statements about the collection), and confirm or correct them; that reading is recorded
in 2.1's pull request. No other reading is scheduled: 1.0's conventions are the code's existing
notations, and 3.2 adds sources to entries, not rules. The owner is asked two things only: a people
source (3.1), put to him with phase 1's measurement; and any run that would pass the budget cap
(section 4). Everything else is handled in the lanes and reported.
