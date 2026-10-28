# The units program's reference set

Work package 0 of [`docs/execution/units/PLAN.md`](../../../docs/execution/units/PLAN.md): the specimens every
measurement of the program runs on, their truth, the scorer, and the baseline of today's code. The run itself is
off-repo, under `~/specimen-golive/runs/units-baseline-20261027/` (its README lists every step and script).

## The 30 specimens

`manifest.json` names them, each a whole slide from
`gs://specimen-digitization.firebasestorage.app/microscopic-slides/` with its object generation, its image digest,
and its labels (id `<subject>-L<n>`, the region's box and id, the crop's digest).

- **The ten pilot slides**, subjects 105526321 to 105526330, the rows of
  `tests/fixtures/field_model_pilot_rows.json`.
- **Twenty drawn slides.** The 1,000 object names, sorted, shuffled with Python `random.Random(20261026)`; in that
  order, the first 20 that are not pilot slides and whose label count is 2. 107 positions were examined: 2 pilot
  slides skipped, 20 with two labels, 71 with three, 14 with four (`draw.examined`).

How labels are counted: by the app's own region step. `sam3_server.RunSegmenter` with `Sam3Engine`
(facebook/sam3 at the pinned revision; checkpoint digest
`sha256:9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8`) over the lab's `LocalObjects`, with the
published profile's `segmentation_settings` (prompt "label", label threshold 0.5); the count is
`label_coverage.check_coverage`'s `region_count` under the published coverage rule (regions merged at IoU 0.9). The
slide's barcode label is a label region, so a slide with one handwritten label and its barcode counts 2. Run
locally on CPU with no paid call: on the six pilot slides that the 2026-09-28 Docker lab segmented with the same
checkpoint (transformers 5.14.0, torch 2.8.0), every region box and score is the same. The pilot slides count 2
(321, 322, 323, 329, 330) or 3 (324 to 328), 25 labels; with the drawn 40, 65 labels in all. Every slide's coverage
check is `confirmed`.

| Drawn, in order | Position | Catalogue number (QR) |
|---|---|---|
| 105526596 | 10 | FMNHINS 0004 486 509 |
| 105526452 | 15 | FMNHINS 0004 486 653 |
| 105526348 | 17 | FMNHINS 0004 486 757 |
| 105526487 | 23 | FMNHINS 0004 486 618 |
| 105526371 | 24 | FMNHINS 0004 486 734 |
| 105526632 | 26 | FMNHINS 0004 486 473 |
| 105526446 | 30 | FMNHINS 0004 486 659 |
| 105526617 | 35 | FMNHINS 0004 486 488 |
| 105526448 | 36 | FMNHINS 0004 486 657 |
| 105526461 | 37 | FMNHINS 0004 486 644 |
| 105526647 | 48 | FMNHINS 0004 486 458 |
| 105526490 | 51 | FMNHINS 0004 486 615 |
| 105526468 | 53 | FMNHINS 0004 486 637 |
| 105526336 | 54 | not decoded |
| 105526369 | 65 | FMNHINS 0004 486 736 |
| 105526459 | 67 | FMNHINS 0004 486 646 |
| 105526359 | 71 | FMNHINS 0004 486 746 |
| 105526456 | 76 | FMNHINS 0004 486 649 |
| 105526335 | 84 | FMNHINS 0004 486 770 |
| 105526522 | 107 | FMNHINS 0004 486 583 |

## Truth

- **Pilot slides: the fixture.** Its values are, in its own words, "hand-read from the images by go-live research
  session S8" and "a reading of the images, not a reader output" (`field_model_pilot_rows.json:2`), with the
  fixture author's interpretations where it says so (`:134`: CNHM read as the museum's old name, not a collector).
  The scorer reads its `expected` row; a scored field the row does not hold is absent (105526327's four elevation
  fields). The manifest records the fixture's digest and a test pins it.
- **Drawn slides: none.** The museum's catalogue holds no record for them. Each slide's catalogue number was decoded
  from its own QR code (zxing-cpp; no model, no pipeline output) and searched as an exact phrase in the museum's
  public EMu-backed collections route (`FMNH_PUBLIC_COLLECTIONS_API_BASE_URL`, `collections-search`, catalog
  Insects) on 2026-10-27: no record for any of the 29 slides whose code decoded, the ten pilot slides included,
  while a published control number (FMNHINS 0005 238 368) was found. The EMu API needs credentials that are not
  provisioned (`FMNH_EMU_API_*` are empty in `.env.example` and locally). So the 20 are measured for cleared /
  marked / left without a value counts only.
- Fields without truth (collection code, county, city, habitat, collection method, verbatim D/T/S, taxon, date
  identified, identified-by IRN: the profile's 20 keys less the scorer's 11) are counts, never accuracy, on every
  specimen.

## The scorer

`score.py` moves the 2026-10-25 rig's strict rule (`free-harness-20261025/score.py` without `--lenient`) into the
repository, from one label to one whole specimen and to the plan's criterion 1. The value compared is the field's
parsed value, else its normalized value, else its literal; `value_ok` compares it with the truth field by field
(country and province by name sets, precise location by similarity 0.85 with "partial" counted wrong, elevations as
numbers, dates exactly, collectors and the catalogue number normalised).

| Truth | Settled with a value | Settled absent | Not settled |
|---|---|---|---|
| holds a value (primary, derived) | right or wrong, cleared or marked | wrong | left without a value |
| absent | wrong (wrongly settled) | right | left without a value |

A settled field is marked when the run carries the units path's code `marked:<field>:<label>:<why>` in its reasons
or a finding's code; today's code writes none, so today every settled field is cleared. Right values (criterion
1 (b)) are cleared right plus marked right. Criterion 2 counts the fields cleared with a value, unmarked, in both
of two runs, and those among them whose compared values differ after normalisation (letters and digits, lower case;
elevations as numbers). On the 2026-10-25 runs this definition gives 6 of 71 between the pair arm's repeats (the
plan's figure) and 2 of 58 between pair and three-reader repeat 1; the plan's 3 of 58 counts "R.D.Mitchell" against
"R.D.mitchell", a difference of letter case only.

`test_units_reference_score.py` pins the rule on fixed records (right, wrong, left without a value, absent; a
marked value counted as marked, and as right when its value is right); `test_units_reference_manifest.py` fails
when a digest, the seed or the truth file changes.

Usage: `python tests/reference/units_program/score.py <run>/r1/pair.jsonl <run>/r1/three.jsonl ... [--json OUT]`.

## The baseline

Not run yet. Its rig is ready in the run folder: today's main frozen as `main-7a09445a2/` (a `git archive` of
7a09445a2's `src`), `run_arm.py` (whole-slide specimens through the app's `Workflow`, the first pass live in every
repeat, the organiser and field research live), `full_run.sh` (both arms, two repeats, repeat 1 before repeat 2),
`analyse.py` (this scorer's report plus criterion 2's differences with the first pass at the label). The no-cost
preflight builds and saves all 30 specimens for both arms.

Estimate written into the run's ledger before any paid call: USD 7.592 by PLAN section 4's formula (field research
7.332, first pass 0.26), plus the organiser's parse calls 0.247 and the live reader calls (62 labels x 3 routes) at
most 0.214: USD 8.053 at list in all, under the USD 10 limit. The baseline's ledger phase stops a step that could
pass USD 7.90.

The readers' texts are fixed in `readings.json`: three pilot labels whose crop is byte-identical to a 2026-10-25
crop keep that day's A, B and C readings; the other 62 labels were read live once per route. Reader B (Muse) and
reader C (Nemotron) are read for all 62; reader A (Qwen on Novita) for 13, the other 49 wait. On 2026-10-28 Novita
did not answer Qwen3-VL from about 01:10Z to 02:35Z (text-only probes timed out at 60 s while the same model on
DeepInfra answered in 0.4 s), and from 05:05Z at the latest this workstation was asleep with dark wakes (`pmset -g
log`), which froze the in-process calls. The organiser is reader A's route (`harness.extract_with_agent` uses `run.profile.routes[0]`), so
the baseline needs Novita too.
