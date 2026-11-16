# Closeout: reading units and the specimen ontology

This is the closing report of the program in [`PLAN.md`](PLAN.md). It records where the program
stopped, the end state on main of every row of the plan's section 5 (criterion 3,
`PLAN.md:77-78`), WP 1.8, the measurement budget, and what is carried. The owner's decisions that
closed the program are quoted in `PLAN.md` section 8.

Main is c431da22 (PR #446 merged) unless a line says otherwise. Paths are under
`src/specimen_digitization/` unless another root is given. "The log" is the program's own record,
`~/specimen-golive/units-program/carry_units_program.md`, and the run folders under
`~/specimen-golive/runs/`; both are off the repository.

## 1. Where the program stopped

- **Phase 1's gate (WP 1.5) was not met.** The re-test of 2026-11-13 met criterion 1 in the pair
  arm only and did not meet criterion 2 (`~/specimen-golive/runs/units-wp15c-20261113/score_units.md`;
  the log, lines 126-135). Phase 2 started on the owner's answer of 2026-11-14, typed in the
  coordinator's session 861fdd86: to "Start phase 2, or move its elevation rule into phase 1 first?"
  he answered "Start as planned" (the log, lines 138-140).
- **Phase 2's gate (WP 2.6) was not met**, and the phase stopped
  (`~/specimen-golive/runs/units-wp26-20261115/report.md:12-27`). `PLAN.md` row 2.6 records the
  result.
- **The owner closed the program on 2026-11-15** and switched the units path on in production the
  same day (`PLAN.md` section 8). Phase 3 (3.1 to 3.3) did not start.

## 2. Section 5, row by row

Each row of `PLAN.md` section 5, in its order, with its end state on main. "Removed" rows were
removed by WP 1.8 part B, commit d7363cb4 of PR #446, the last commit to touch each name under
`src/`.

| Row (`PLAN.md`) | End state on main | Where |
|---|---|---|
| `FirstPassOutput.selected_reader` (:205) | Removed | A search for `\bselected_reader\b` finds nothing under `src/` and `tests/` |
| `DifferenceVerdict`, `FirstPassOutput.verdicts`, `output_problems` (:206) | Removed; the units path's checks are `reading_units.problems` | `application/reading_units.py:191`; neither `DifferenceVerdict` nor `FirstPassOutput` is under `src/` |
| `FirstPassDecision`, `FirstPassDifference`, `Run.first_pass_decisions`, `UNRESOLVED_VERDICTS`, `OPEN_VERDICTS`, `is_material` (:207) | Kept, except `UNRESOLVED_VERDICTS`, which d7363cb4 removed although the row says kept; a units-path decision selects no reading and gives `uncertain` verdicts | `application/domain.py:176`, `:186`, `:513`; `application/projection.py:60`; `application/first_pass.py:247`; `application/integrity.py:133-134` |
| The first-pass transport (:208) | Extended: the child returns the units, and the parent validates `ReadingUnits` | `application/model_runtime.py:103`, `:292` |
| `g19_pick`, `supports` (:209) | Kept | `application/first_pass.py:254`, `:271` |
| The scheduling rule and the two-reading floor (:210) | Replaced: a label with two readings or more, some with text, gets the model's first pass; any other label with text gets units from the alignment at adjudicate; a label whose text a person wrote gets no call | `application/workflow.py:2354-2367`; PR #446's Left list names the one-reader case |
| The run's first-pass path (:211) | Kept on every run; every new run records units, and a reopened old-path run is moved to the units path | `application/domain.py:557-559`; `application/reading_units.py:27-30`; `application/workflow.py:312-320` |
| A person's transcript edit (:212) | Extended: the label's units come again from its current text source | `application/api.py:2205-2219` |
| `_DISAGREEMENT_ADJUDICATION_DEFAULT`, `prompt__transcription_disagreement_adjudication` (:213) | Removed; the Logfire prompt was deleted with the owner's variables key | Neither name is under `src/` or `tests/`; the log, line 525 |
| `SPECIMEN_FIRST_PASS_UNITS` (:214) | Turned on in production by PR #445, then removed by PR #446 | The name is not under `src/` or `tests/`; section 3 below |
| `FirstPassAdvice`, `Reading.first_pass`, the experts' `first_pass` key (:215) | Removed; `person_decided` stays | `field_research/experts.py:226`; `field_research/prompts/common.txt:8` |
| `BY_FIRST_PASS` (:216) | Removed; a person's text binds its label as `BY_PERSON` | `field_research/agreement.py:1311`; `tests/field_research/test_first_pass_advice.py::test_a_person_decided_transcript_binds_its_label_against_an_exact_source_match` |
| `BY_AGREEMENT`, `BY_SOURCE`, `BY_NEAR_SPELLING`, `BY_SAME_PLACE`, `BY_OTHER_LABEL`, `MIN_BACKING_READERS`, `_spelling` (:217) | Kept as the rule's backings; the row names a test since renamed (carried, section 5) | `field_research/agreement.py:1289`, `:1302-1307` |
| `confirmed_against_image`, `_confirms`, `_preferred_spelling`, `Label.preference` and its values, `_preference` (:218) | Removed | None of the names is under `src/` |
| `first_pass_followed`, `first_pass_overridden`, `first_pass_absent`, `first_pass_conflict`, `first_pass_code`, `_first_pass_preference`, `FIRST_PASS_RULES` (:219) | Removed from `src/`; under `tests/` one line keeps an old code, in a test that the move drops it | `tests/test_old_path_migration.py:422` |
| `first_pass_given_up`, `GIVEN_UP`, `give_up`, `given_up_regions` (:220) | Kept | `application/first_pass.py:64`, `:919` |
| `common.txt` rule 4 and its first-pass paragraph; the five tool-less briefs' first-pass sentences; `verbatim_dts.txt:1,3` (:221) | Rewritten: `common.txt` and the five briefs name no first pass. Left: `verbatim_dts.txt:1` and `:3` still say the museum has not confirmed what D/T/S holds; WP 1.7's prompt change is not on main (carried, section 5) | `field_research/prompts/common.txt`; `field_research/prompts/verbatim_dts.txt:1`, `:3`; the PRD's answer is `docs/product-requirements/PRD.md:1224` |
| `harness.apply_candidates` and the organiser call (:222) | Kept; WP 2.5 kept the organiser call (PR #443) | `application/harness.py:78`; `PLAN.md:222` |
| `FieldAnswer.literal`; `ACROSS_LINES` (:223) | Kept | `field_research/contracts.py:223`; `field_research/agreement.py:479` |
| `prompt__field_harness`, `PromptName.FIELD_HARNESS`, `_FIELD_HARNESS_DEFAULT` (:224) | Removed; the Logfire prompt was deleted with the owner's variables key | None of the names is under `src/` or `tests/`; the log, line 525 |
| `application/harness_knowledge/` (:225) | Moved into the ontology file at 1.0; the module is gone | A search for `harness_knowledge` finds nothing under `src/` and `tests/` |
| The code's notation tables (:226) | Kept, pinned equal to the ontology file | `tests/test_ontology.py::test_the_codes_notation_tables_are_the_files` |
| `exactUtf16Span` (:227) | Kept, with the code-point conversion before it | `apps/specimen_digitization/lib/src/reading_alignment.dart:12`, `:36`, `:53-56` |
| `research_harness/` and its switch (:228) | Kept, out of scope. The row says no phase touches it; PR #446 added `AppendTranscriptionVersionV3` beside V2 to its accepted operations | `research_harness/canonical_projection_v2.py:33` |
| `tests/fixtures/field_model_pilot_rows.json` (:229) | Kept; a digest test guards it | `tests/reference/units_program/test_units_reference_manifest.py:15` |

## 3. WP 1.8

**Part A, PR #445**, merged 2026-11-16 as be1d45167. It set the switch on in production
(`scripts/ci/runtime_settings.py` at be1d45167). Its release (the off-repo record
`~/specimen-golive/units-program/release_445.txt`): Data release run 43804096779, Runtime release
run 43804096899 (finished 04:32:01Z) and CI/CD run 43804096855 all succeeded, and the API's
`/version` gave be1d45167. The log records the units path on in production for every new run from
about 04:32Z (line 461). Before the release, and again at 04:46:13Z after it, a read-only query
counted 33 specimens, all finalized on the old path, none open (the log, lines 455 and 462). One
real specimen was checked: pilot 105526326, run 7b052445-a3a6-4b79-ab0b-04da234d572e, started with
the app's Start new run, finalized at 05:29:50Z as `needs_human_review`, its first-pass path units,
with 12 reading units over its 3 labels (the log, line 465).

**Part B, PR #446**, merged 2026-11-16 as c431da22 at head ec066674 (reviews: Codex
issuecomment-6922839579, G51 issuecomment-6922840149). It removed the old first pass, its prompt,
the switch and the field-harness prompt (section 2). Every new run records the units path; a run
the old first pass processed is moved to it when it is reopened, before a step is picked
(`application/workflow.py:320` `move_to_units`, called through `Workflow._move` at `:745`). The
move keeps a person's transcription decisions and carries a person's field decisions made after
the latest transcript decision (`application/workflow.py:320-336`, `:671-680`). Its tests are
`tests/test_old_path_migration.py` and `tests/test_old_path_migration_carry.py`. Its release (the
off-repo record `~/specimen-golive/units-program/release_446.txt`): the Data release (run
43911184657) and the Runtime release (run 43911184486) succeeded, and the API's `/version` gave
c431da22. The CI/CD run 43911184649 failed on its first attempt, so Hosting still gave be1d45167
when that record was written; the run was then started again. PR #446's "Left" list is carried in
section 5.

Row 1.8 put the switch-on "After the 1.5 gate". That gate was not met (section 1); the owner's
answer of 2026-11-15 replaced the condition (`PLAN.md` section 8).

## 4. The measurement budget

The cap is USD 55 at list (`PLAN.md` section 4). The log's running totals, at list:

| Spend | USD at list | Source (the log, or the run folder) |
|---|---|---|
| WP 0 baseline | 7.858 | line 15 |
| WP 1.5 | 8.348 | line 71 |
| Stability lane and its follow-up | 2.5637 and 0.5337 | lines 99, 108 |
| Running total after those | about 20.4 | line 109 |
| WP 1.5b (invalid: the model router answered 402 Payment Required; about 3.89 of it worst-case holds on calls that returned no usage) | 5.73 | lines 114-118 |
| WP 1.5c | 7.9336 | line 126 |
| Running total | about 34.0 | line 135 |
| WP 2.2 | 1.2125 | line 217 |
| WP 2.3c re-ask rig | 0.008312 | line 325 |
| WP 2.5 (PR #443) | 2.6557 | line 428 |
| Running total | about 37.9 | line 428 |
| WP 2.6 | 8.3098 | line 449; `~/specimen-golive/runs/units-wp26-20261115/report.md:68-75` |
| Running total | about 46.2 | line 449 |
| WP 1.8's check of one real specimen (production, booked; two failed segmentation attempts booked at their reservation) | 0.570111 | line 465 |
| Program total | about 46.8 of 55, at most | line 465 |

WP 2.6 ran above its row's USD 8 on the owner's answer of 2026-11-15, by the next-step box's
button in the coordinator's session: to "Run the final phase 2 test now for about USD 9, leaving
the one conflicting elevation for a person?" he answered "Yes, run it" (the log, line 446).

## 5. Carried

- **Getty TGN's non-preferred parents.** Below the country a place check abstains without the
  record's whole parent set, which today's reader does not give (`PLAN.md:127`, its follow-up;
  PR #436; `ontology/specimen.yaml:760-766`).
- **Open meanings.** "P-95-81-16" is the ontology's one open question (`ontology/specimen.yaml:671`).
  Other printed headings, such as "Siphonaptera of Utah", are not ruled
  (`docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:334`;
  `tests/test_ontology.py::test_no_other_printed_heading_is_ruled`).
- **Stale spec citations.** The spec cites `parents_refusal` at `agreement.py:2065-2089`
  (`FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md:243`, `:365`); it is at
  `field_research/agreement.py:2430`. It cites `NO_UNIT` at `agreement.py:302` and `:822-825`
  (`:256`); it is at `field_research/agreement.py:285` and `:812`. Its line 332 says the file
  carries the LEWIS ruling "on the units path only"; the experts now research every run on the
  units path (`field_research/step.py:211-213`), so that qualifier no longer separates any run.
- **WP 1.7's prompt change.** `field_research/prompts/verbatim_dts.txt:1` and `:3` still say the
  museum has not confirmed what D/T/S holds; `PLAN.md` row 1.7 replaces that sentence with the PRD's
  answer (`docs/product-requirements/PRD.md:1224`), pinned by a test.
- **SAM cold starts.** When the one-instance SAM service is still loading, a segmentation attempt
  fails and is booked at its reservation, 182321 micros with no usage (the log, line 464:
  2026-11-16 05:17-05:18Z, run 7b052445).
- **The research harness's native mode.** Its "on" mode can no longer publish a record whose
  label's readers differ (the log, line 491). Production runs it as `fields`
  (`scripts/ci/runtime_settings.py:142`).
- **PR #446's Left list** (its PR body):
  - any reopen of an old-path record drops its authority and taxonomy selections;
  - the move's history event shows as "Requested reprocessing", under the worker's uid;
  - a proof read that fails blocks the run until a person resumes it;
  - a Start new run carry followed by a transcript edit blocks the run, as it did before;
  - a moved run's run-level budgets were not measured;
  - `PLAN.md` row 217 names a test since renamed,
    `test_readers_that_agree_settle_on_the_spelling_of_the_reader_the_first_pass_preferred`.
- **Logfire.** The prompts `transcription-disagreement-adjudication` and `field-harness` (variables
  `prompt__transcription_disagreement_adjudication` and `prompt__field_harness`) were deleted on
  2026-11-16 with the owner's variables key, after a backup kept off the repository (the log,
  line 525; `~/specimen-golive/units-program/logfire_cleanup/`). The coordinator's record
  (`~/specimen-golive/units-program/brief_wp27_closeout.md`) gives 28 prompts remaining and
  `prompt__first_pass_units` not registered there, and the mirrors carry the text of main
  1ca922535; this closeout did not read Logfire. Production reads no variables (the log, line 525),
  so the Prompts page is not current. Registering every prompt there is a follow-up if the owner
  still wants it.
- **Phase 3** (3.1 people lookups, 3.2 the conventions table, 3.3 the steady-state run) did not
  start.
