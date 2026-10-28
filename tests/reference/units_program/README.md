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
slide's barcode label is a label region, so each of the 20 drawn slides holds one non-barcode label and its
barcode label. Looked at slide by slide (the table below; crops and `kinds.json` in the run folder's
`slides/drawn_labels/`), the non-barcode label is filled in by hand on 19 of the 20: 3 written by hand, 1 written by
hand with a printed collector line, 9 printed LEWIS COLLECTION templates and 6 printed Siphonaptera of Utah templates
filled in by hand; on 105526335 it is an unfilled LEWIS COLLECTION template (its only words, "LEWIS COLLECTION" and
"col", are printed). Behaviour across labels is therefore measured on the pilot slides only: the five with three
labels (105526324 to 105526328) hold two non-barcode labels each. Run locally on CPU with no paid call: on the six
pilot slides that the 2026-09-28 Docker lab segmented with the same checkpoint (transformers 5.14.0, torch 2.8.0,
amd64; here torch 2.13.0, transformers 5.15.1, arm64), the boxes are equal and the scores within 3e-6 (four of the
six differ at six decimals). The pilot slides count 2 (321, 322, 323, 329, 330) or 3 (324 to 328), 25 labels; with the
drawn 40, 65 labels in all. Every slide's coverage check is `confirmed`.

| Drawn, in order | Position | Catalogue number (QR) | Non-barcode label |
|---|---|---|---|
| 105526596 | 10 | FMNHINS 0004 486 509 | written by hand |
| 105526452 | 15 | FMNHINS 0004 486 653 | Siphonaptera of Utah template, filled in by hand |
| 105526348 | 17 | FMNHINS 0004 486 757 | LEWIS COLLECTION template, filled in by hand |
| 105526487 | 23 | FMNHINS 0004 486 618 | LEWIS COLLECTION template, filled in by hand |
| 105526371 | 24 | FMNHINS 0004 486 734 | LEWIS COLLECTION template, filled in by hand |
| 105526632 | 26 | FMNHINS 0004 486 473 | written by hand |
| 105526446 | 30 | FMNHINS 0004 486 659 | Siphonaptera of Utah template, filled in by hand |
| 105526617 | 35 | FMNHINS 0004 486 488 | written by hand |
| 105526448 | 36 | FMNHINS 0004 486 657 | Siphonaptera of Utah template, filled in by hand |
| 105526461 | 37 | FMNHINS 0004 486 644 | Siphonaptera of Utah template, filled in by hand |
| 105526647 | 48 | FMNHINS 0004 486 458 | LEWIS COLLECTION template, filled in by hand |
| 105526490 | 51 | FMNHINS 0004 486 615 | LEWIS COLLECTION template, filled in by hand |
| 105526468 | 53 | FMNHINS 0004 486 637 | LEWIS COLLECTION template, filled in by hand |
| 105526336 | 54 | not decoded | LEWIS COLLECTION template, filled in by hand |
| 105526369 | 65 | FMNHINS 0004 486 736 | LEWIS COLLECTION template, filled in by hand |
| 105526459 | 67 | FMNHINS 0004 486 646 | Siphonaptera of Utah template, filled in by hand |
| 105526359 | 71 | FMNHINS 0004 486 746 | LEWIS COLLECTION template, filled in by hand |
| 105526456 | 76 | FMNHINS 0004 486 649 | Siphonaptera of Utah template, filled in by hand |
| 105526335 | 84 | FMNHINS 0004 486 770 | LEWIS COLLECTION template, unfilled |
| 105526522 | 107 | FMNHINS 0004 486 583 | written by hand, printed collector line |

## Truth

- **Pilot slides: the fixture.** Its values are, in its own words, "hand-read from the images by go-live research
  session S8" and "a reading of the images, not a reader output" (`field_model_pilot_rows.json:2`), with the
  fixture author's interpretations where it says so (`:134`: CNHM read as the museum's old name, not a collector).
  The scorer reads its `expected` row; a scored field the row does not hold is absent (105526327's four elevation
  fields). The manifest records the fixture's digest and a test pins it.
- **Drawn slides: none.** No truth could be obtained for them. Each slide's catalogue number was decoded from its
  own QR code (zxing-cpp; no model, no pipeline output) and searched as an exact phrase in the museum's public
  collections route (`FMNH_PUBLIC_COLLECTIONS_API_BASE_URL`, `collections-search`, catalog Insects) at
  2026-10-28T01:33:35Z (UTC): no public-collections match for any of the 29 decoded catalogue numbers (the ten
  pilot slides included), while a published control number (FMNHINS 0005 238 368) was found. 105526336's code did
  not decode, so it was not searched. EMu API access is unavailable (`FMNH_EMU_API_*` are empty in `.env.example`
  and locally). The truth source for the 20 is none: they are measured for cleared / marked / left without a value
  counts only.
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
or a finding's code; today's code writes none, so today every settled field is cleared. A field that is not
settled (`unknown`, `unresolved`, `unreadable`, `ambiguous`) is left without a value whatever text it keeps (an
unresolved field may still hold a reader's literal); `not_present` and `not_applicable` settle as absent whatever text
they carry. Text is a string with a character other than whitespace, in the parsed value, the normalized value or
the literal: an empty or whitespace-only string, None and the field's `reason` are not text, so a `supported` field
without text is left without a value, and the compared value is the first of parsed, normalized and literal that has
text. (The rig's rule took any non-empty string; none of the baseline's 2,400 field states holds an empty or
whitespace-only string, and the regenerated `score_baseline.md` is byte-identical.) A record with no state is left
without a value, and a state outside `application/domain.py`'s seven, "" and "SUPPORTED" included, is refused.
Right values (criterion 1 (b)) are cleared right plus marked right.

Criterion 2: a field is cleared in a run when it is settled, with a value or as absent, and not marked. The fields
compared are those cleared in both runs, and a difference is any change between the two cleared results: a value
against absence, or two values whose compared values differ after `norm` (elevations as numbers). `norm` keeps ASCII
letters and digits and folds case, deleting every other character: "R.D.Mitchell" and "R.D.mitchell" are the same,
"Mexico" and "México" differ ("mexico" against "mxico"), and "México" and "Mèxico" are the same ("mxico" both). The plan's criterion 2 states this definition
and quotes this baseline's numbers. `score_baseline.md` labels each difference by the scorer's kind.

`test_units_reference_score.py` pins the rule on fixed records (right, wrong, left without a value, absent; a
marked value counted as marked, and as right when its value is right; each value state of `application/domain.py`
with five listed text shapes, scored against a truth and against absence: `supported` settles a value when it has
text, `not_present` and `not_applicable` settle as absent whatever text they carry, and the four unsettled states
(`unknown`, `unresolved`, `unreadable`, `ambiguous`) are left without a value whatever text they keep, a state the
scorer does not place failing the test; boundary records: an empty, None or whitespace-only literal, a whitespace
parsed value beside a literal, the default `reason` alone, a record with no state, and the refused states "",
"SUPPORTED", "Supported", " supported" and "invented"; a no-break space or a tab as the normalized value and the
word "text" as the parsed value, each beside a literal; text checked on every code point, the surrogates included,
against Python's `str.isspace`;
the compared value over all 64 combinations of parsed, normalized and literal, each None, "", "  " or text;
criterion 2 counting a cleared absence, giving each
difference its kind, "value_absent" or "two_values", and comparing ASCII letters and digits with case folded).
`test_units_reference_manifest.py` pins the whole manifest's canonical digest and the fixture's digest, both written `sha256:<hex>`, and recomputes the draw from the
sorted listing with the seed, so it fails when a digest, the seed or the truth file changes.

Usage: `python tests/reference/units_program/score.py <run>/r1/pair.jsonl <run>/r1/three.jsonl ... [--json OUT]`.

## The baseline

Run on 2026-10-28 from 08:06Z to about 10:10Z in `~/specimen-golive/runs/units-baseline-20261027/`: today's main
(7a09445a2, frozen as a `git archive` of its `src`), the pair arm (readers A and B) and the three-reader arm (A, B,
C), two repeats each, all 30 specimens, the first pass live in every repeat (on the 37 labels whose two readings
differ, 47 whose three do; 38, 38, 48 and 48 first-pass steps with retries), the organiser and field research
live, geography on. All 120 specimen runs finalized with no step error. In pair repeat 2 the first pass gave up
on two labels, 105526324-L2 and 105526329-L2 (finding `first_pass_given_up:<region>:model_malformed_response`,
production's own given-up path), so that run stores 35 first-pass decisions against 37 in repeat 1; the other three
runs gave none up. The full report, with every difference and the cost per run, is the run folder's
`score_baseline.md`.

The readers' texts are fixed in `readings.json`: three pilot labels whose crop is byte-identical to a 2026-10-25
crop keep that day's A, B and C readings; the other 62 labels were read live once per route on 2026-10-27/28.
Reader A (Qwen) failed on all four live calls for seven of them (six malformed answers, one provider failure); the
rig replays that failure through the workflow's own reader step, which retries within its three attempts and then
gives the reading up, as production does. Novita did not answer Qwen3-VL from about 01:10Z to 02:35Z on
2026-10-28; nothing was switched to another provider.

### Criterion 1, per run

Fields of the ten pilot specimens; n is the number of fields scored in the category. Today's code writes no
`marked:` code, so every settled value is cleared and the marked columns are 0.

| Run | Category | n | Cleared right | Cleared wrong (of which partial) | Marked right | Marked wrong | Left without a value |
|---|---|---|---|---|---|---|---|
| pair, repeat 1 | primary | 69 | 45 | 18 (7) | 0 | 0 | 6 |
| pair, repeat 1 | derived | 37 | 29 | 8 (0) | 0 | 0 | 0 |
| pair, repeat 1 | absent | 4 | 4 | 0 | 0 | 0 | 0 |
| pair, repeat 2 | primary | 69 | 44 | 14 (5) | 0 | 0 | 11 |
| pair, repeat 2 | derived | 37 | 26 | 11 (0) | 0 | 0 | 0 |
| pair, repeat 2 | absent | 4 | 4 | 0 | 0 | 0 | 0 |
| three, repeat 1 | primary | 69 | 43 | 15 (6) | 0 | 0 | 11 |
| three, repeat 1 | derived | 37 | 32 | 5 (0) | 0 | 0 | 0 |
| three, repeat 1 | absent | 4 | 4 | 0 | 0 | 0 | 0 |
| three, repeat 2 | primary | 69 | 43 | 16 (6) | 0 | 0 | 10 |
| three, repeat 2 | derived | 37 | 29 | 7 (0) | 0 | 0 | 1 |
| three, repeat 2 | absent | 4 | 4 | 0 | 0 | 0 | 0 |

Per arm, the mean over the two repeats and the range (the noise rule's terms):

| Arm | Category | Cleared wrong | Right | Left without a value |
|---|---|---|---|---|
| pair | primary (69) | 16 (14 to 18) | 44.5 (44 to 45) | 8.5 (6 to 11) |
| pair | derived (37) | 9.5 (8 to 11) | 27.5 (26 to 29) | 0 |
| pair | absent (4) | 0 | 4 | 0 |
| three | primary (69) | 15.5 (15 to 16) | 43 (43) | 10.5 (10 to 11) |
| three | derived (37) | 6 (5 to 7) | 30.5 (29 to 32) | 0.5 (0 to 1) |
| three | absent (4) | 0 | 4 | 0 |

Reported, not gated: marked values 0 in every run; specimens that reach a cleared disposition 1 of 30 (pair,
repeat 1) and 0 of 30 in the other three runs. The 20 drawn specimens, counted over their 20 fields each (400 per
run), cleared with a value / cleared as absent / left without a value: 130 / 187 / 83 and 135 / 191 / 74 (pair),
118 / 192 / 90 and 123 / 192 / 85 (three).

### Criterion 2

| Comparison | Fields cleared in both (with a value or absent) | Differences |
|---|---|---|
| pair repeat 1 against pair repeat 2 (the noise floor) | 472 | 30 |
| pair repeat 1 against three-reader repeat 1 | 459 | 30 |
| pair repeat 2 against three-reader repeat 2 | 464 | 23 |

The floor's 30, on 17 specimens: 23 a value against absence (verbatim D/T/S 8, habitat 4, collection code 4, the
three elevations derived on 105526324, and one each of city, collection method, collectors, precise location) and 7
two different values (105526322 collectors "H. Hoogstraal leg." / "H. Hoogstraal"; 105526323, 105526325 and
105526327 precise location, another reader's spelling or more or less of the locality block; 105526617 country
"Mexico" / "México"; 105526461 and 105526456 verbatim D/T/S, another line of the label). `score_baseline.md` lists
every difference, and for each pair-against-three one whether the first pass's image judgement at the label
differed.

### Cost

Estimate written into the run's ledger before any paid call: USD 7.592 by PLAN section 4's formula (field research
7.332, first pass 0.26), plus the organiser's parse calls 0.247 and the live reader calls at most 0.214: USD 8.053
at list in all. Limits: the plan's USD 8 at list per measurement by section 4's formula (7.592 before the run,
7.3535 after), and the WP 0 brief's USD 10 at list in all, the estimate included; the baseline's ledger phase
refused any step that could pass USD 7.90.
Actual at list as booked: the baseline USD 7.3535 (the 120 runs USD 7.3198; the rest is a first launch whose two
first specimens stopped at parse on a rig fault, USD 0.0036, and two holds that launch left open, USD 0.03; by
kind, field research 7.0823, parse 0.1464, first pass 0.0948 and the holds), the readers USD 0.4885 (unanswered calls booked at their worst case, USD 0.02 each), probes
USD 0.016: USD 7.858 in all. Field research at the price list's cached-input rate: USD 1.3703; Hugging Face's own
estimate: USD 0.9574.
