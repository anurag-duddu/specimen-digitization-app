"""WP 2.R of docs/execution/units/PLAN.md: the two review rules narrowed to their requirements. The owner
typed on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything
at the user it is to help by being in in autonomy as much as possible." and "Harness needs to work and do its
magic".

(i) unresolved_transcription, on the units path, is dropped only for a label whose readers differ in letter case
or spacing alone (step.readings_conflict): such readings do not conflict in G19's sense
(docs/execution/golive/PLAN.md:77: "a field still left with conflicting readings goes to needs human review").
Any other difference keeps it, whether or not a field seems to draw it, and so does a unit whose readers' texts
differ that no settled field's text holds while a field of the run clears as not on the label (the coordinator's
rulings on #441's first reviews); so do a label the first pass gave up on, one with one reader and one with no
units.

(ii) mandatory_unresolved is not raised for a field settled absent as not on the label (owner decision A,
docs/execution/golive/FIELD_RESEARCH.md, "Fields the label does not state") only where its expert answered
label_lacks_value and the not-on-the-label check row agrees (step.mark_not_on_label, step.not_on_label). WP 2.R
checked each field the list leaves out against its sources and adds none (contracts.NOT_ON_LABEL's comment), so
the rule is today's; its named cases are test_step's
test_the_listed_fields_a_label_does_not_state_clear_as_not_on_the_label (a field the label does not write,
cleared, no reason) and test_a_field_whose_line_the_label_writes_never_clears_as_not_on_the_label (a field whose
reading writes its text, answered label_lacks_value, keeps the reason); the fields left out are pinned below.

Every test runs on both first-pass paths (conftest.py). On the old path, live in production until WP 1.8, each
test asserts origin/main's result."""

from __future__ import annotations

import hashlib
import io

import pytest
import test_step as rig_module
from PIL import Image
from test_step import (
    LACKS,
    SMITH_OR_SMYTH,
    SMYTH,
    TEXT,
    Scripted,
    answering,
    build_rig,
    every_field,
    label_with,
    mounted,
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, Observation, Region, Run, ValueState
from specimen_digitization.application.first_pass import alignment_units
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import contracts, ontology_checks
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.agreement import _differs

# 105526326's third label (wp15c): its readers differ only in letter case, as 19 of the 20 labels the first form
# of this change dropped there do.
CASE_A, CASE_B = "Sp. 22\nhead 4 legs", "sp. 22\nhead  4 legs"
# 105526329's second label (wp15c r2/pair): its readers differ on a preparation note no field draws.
NOTE_A, NOTE_B = "head 4 legs", "head + legs"


def second_label_read(monkeypatch, *texts):
    """build_rig's specimen with a second label its readers read as `texts`, in route order; "" for a reader
    that read nothing, which extraction_readings leaves out (test_first_pass_advice's helper, which also takes
    make_specimen's `first_pass`, so that a first pass given up on runs on it too)."""
    original = rig_module.make_specimen

    def make(blobs, first=TEXT, other=None, *, first_pass=True):
        specimen = original(blobs, first, other, first_pass=first_pass)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for route, text in zip(run.profile.routes, texts, strict=True):
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=text,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        if len(set(texts)) > 1 and first_pass and rig_module.PATH == "old":
            # Its first pass picked no reading, as make_specimen's.
            run.completed_steps.append(f"first_pass:{region.id}")
        return specimen
    monkeypatch.setattr(rig_module, "make_specimen", make)


def second_region(run):
    return run.regions[1].id


def note_units(run):
    """The second label's units; None on the old path, which has none."""
    return next((item for item in run.reading_units if item.label == second_region(run)), None)


def differing(run):
    """The second label's units where its readers write different text, letter case and spacing aside."""
    return [[span.text for span in unit.readers.values()] for unit in note_units(run).units if _differs(unit)]


def transcription(run, region):
    return f"unresolved_transcription:{region}"


def noted(tmp_path, monkeypatch, *texts, refused=False):
    """test_step's label, which both readers read alike and every field's expert settles, and a second label
    its readers read as `texts`."""
    second_label_read(monkeypatch, *texts)
    rig = build_rig(tmp_path, candidates=every_field(), refused=refused)
    settle(rig, Scripted())
    return rig, rig.specimen.run


# ---- (i) unresolved_transcription --------------------------------------------------------------

def test_a_label_whose_readers_differ_only_in_letter_case_or_spacing_does_not_conflict(tmp_path, monkeypatch,
        first_pass_path):
    """Named case 1: the readers write "Sp. 22" and "sp. 22", "head 4 legs" and "head  4 legs", the same text
    letter case and spacing aside (agreement._differs). On the units path the readings do not conflict: no
    unresolved_transcription, and the record, whose every field settles, clears. On the old path the label still
    goes to a person, as on main."""
    rig, run = noted(tmp_path, monkeypatch, CASE_A, CASE_B)
    region = second_region(run)
    if first_pass_path == "units":
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
        assert differing(run) == [] and not field_step.readings_conflict(run, region)
    else:
        assert (run.disposition, run.reasons) == (Disposition.REVIEW, [transcription(run, region)])


def test_a_label_whose_readers_differ_on_a_span_no_field_draws_keeps_the_reason(tmp_path, monkeypatch,
        first_pass_path):
    """Named case 1 of the brief, kept by the coordinator's ruling on #441's first review: the readers differ
    on "4" against "+", which no field draws and no unit advises for a field. A real textual difference keeps
    unresolved_transcription on both paths, as on main."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, NOTE_B)
    region = second_region(run)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [transcription(run, region)])
    if first_pass_path == "units":
        assert differing(run) == [["4", "+"]]


def test_a_year_on_the_next_line_keeps_the_reason_though_the_literal_quotes_only_the_date(tmp_path,
        monkeypatch, first_pass_path):
    """Codex's input on #441's first review: the readers write "IV-25" over "1948" and over "1949". The
    collecting date's candidates quote "IV-25" only, but the year on the next line decides the date
    (written.year_on_next_line), so the date is left for a person, and the label keeps
    unresolved_transcription on both paths, as on main."""
    second_label_read(monkeypatch, "IV-25\n1948", "IV-25\n1949")
    rig = build_rig(tmp_path, label_with(date_visited_from=None), candidates=every_field(
        *(("date_visited_from", name, "IV-25", "IV-25") for name in ("2A", "2B"))))
    run = rig.specimen.run
    unsure = answering(LACKS.model_copy(update={"outcome": "several_possibilities", "options": ["IV-25"],
        "reading_names": ["2A", "2B"], "explanation": "The year on the next line differs: 1948 or 1949."}))
    settle(rig, Scripted({"date_visited_from": unsure}))
    region = second_region(run)
    assert run.fields["date_visited_from"].state != ValueState.SUPPORTED
    assert transcription(run, region) in run.reasons and "mandatory_unresolved:date_visited_from" in run.reasons
    if first_pass_path == "units":
        assert differing(run) == [["1948", "1949"]]


def test_a_label_whose_readers_differ_on_a_fields_literal_keeps_the_reason(tmp_path, first_pass_path):
    """Named case 2: 1A writes "J. Smith", 1B "J. Smyth"; the collectors' expert settles 1A's text, which the
    readers do not agree on. The label keeps unresolved_transcription on both paths, and the collectors their
    own reason (test_step's test_on_a_label_with_no_decided_transcript_the_way_out_is_a_transcription_decision)."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    run = rig.specimen.run
    settle(rig, Scripted({"collectors": answering(resolved("J. Smith", reading="1A"))}))
    region = run.regions[0].id
    assert (run.disposition, run.reasons) == (Disposition.REVIEW,
        [transcription(run, region), "mandatory_unresolved:collectors"])


def test_a_label_whose_first_pass_was_given_up_keeps_the_reason_though_its_readers_differ_only_in_case(
        tmp_path, monkeypatch, first_pass_path):
    """Named case 3: case 1's labels, with the first pass refused on every attempt and given up: the second
    label keeps unresolved_transcription on both paths (HARNESS.md, a given-up label goes to review however its
    fields settle)."""
    rig, run = noted(tmp_path, monkeypatch, CASE_A, CASE_B, refused=True)
    region = second_region(run)
    assert region in field_step.given_up_regions(run)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def test_a_label_one_reader_read_keeps_the_reason(tmp_path, monkeypatch, first_pass_path):
    """Named case 4: the second label's other reader read nothing (wp15c's pair arm, where one reader returned
    nothing on seven labels): one reading has no second reading to agree with, so the label keeps
    unresolved_transcription on both paths."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, "")
    region = second_region(run)
    assert [r.text for r in field_step.run_readings(run) if r.region_id == region] == [NOTE_A]
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def no_units(run):
    region = second_region(run)
    run.reading_units = [item for item in run.reading_units if item.label != region]


def one_route(run):
    for item in run.observations:
        if item.region_id == second_region(run):
            item.route_id = "one-route"


def one_model(run):
    for item in run.observations:
        if item.region_id == second_region(run):
            item.model_id = "one-model"


@pytest.mark.parametrize("change", [no_units, one_route, one_model], ids=["no-units", "one-route", "one-model"])
def test_a_label_with_no_units_or_one_reader_keeps_the_reason_though_its_readers_differ_only_in_case(tmp_path,
        monkeypatch, first_pass_path, change):
    """Case 1's run with one thing changed: the label has no units, or its readings come from one route or one
    model (independent_observations_missing's test). The reason stands again on both paths."""
    rig, run = noted(tmp_path, monkeypatch, CASE_A, CASE_B)
    region = second_region(run)
    change(run)
    field_step.refinalize(run)
    assert transcription(run, region) in run.reasons


def test_an_old_path_record_that_keeps_units_keeps_mains_reasons(tmp_path, monkeypatch, first_pass_path):
    """Codex's input on #441's first review: an old-path record whose stored run carries reading units, through
    the record's JSON round trip, keeps main's reasons: the narrowing is the units path's alone. On the units
    path the same record drops the reason (case 1)."""
    rig, run = noted(tmp_path, monkeypatch, CASE_A, CASE_B)
    region = second_region(run)
    if first_pass_path == "old":
        store_reading_units(run, [alignment_units(region, [o for o in run.observations if o.region_id == region])])
    run = Run.model_validate(run.model_dump(mode="json"))
    assert note_units(run) is not None
    field_step.refinalize(run)
    assert (transcription(run, region) in run.reasons) is (first_pass_path == "old")


def without_the_method(tmp_path, monkeypatch, *texts, candidates=(), scripts=None, also=()):
    """test_step's label without its collecting method line (and the lines of `also`), and a second label its
    readers read as `texts`; the method's expert finds none, so the method clears as not on the label (owner
    decision A)."""
    second_label_read(monkeypatch, *texts)
    rig = build_rig(tmp_path, label_with(**dict.fromkeys(("collection_method", *also))),
        candidates=every_field(*candidates))
    run = rig.specimen.run
    settle(rig, Scripted({"collection_method": answering(LACKS), **(scripts or {})}))
    return rig, run


@pytest.mark.parametrize("texts", [("Malaise trap\nslide 2", "slide 2"), ("Malaise trap\nslide 2", "Malaise trep\nslide 2"),
    ("Malaise trap\nslide 2", "MALAISE TRAP\nslide 2")], ids=["a-line-one-reader-lacks", "trap-trep", "letter-case"])
def test_a_label_whose_readers_write_a_cleared_fields_text_keeps_the_reason(tmp_path, monkeypatch,
        first_pass_path, texts):
    """G51's input on #441's first review: the second label writes "Malaise trap", which one reader leaves
    out, misreads as "Malaise trep" or writes in capitals, and the collecting method clears as not on the
    label. Its label's reason is the only one that would send that field to a person, so the label keeps
    unresolved_transcription on both paths: the first two as real differences, the third, which differs in
    letter case alone, as a unit that no settled field's text holds (the coordinator's ruling)."""
    rig, run = without_the_method(tmp_path, monkeypatch, *texts)
    region = second_region(run)
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    evidence = {item.id: item for item in run.evidence}
    assert field_step.not_on_label("collection_method", run.fields["collection_method"], run, evidence, allowed)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def test_a_case_difference_inside_a_settled_fields_text_drops_the_reason_beside_a_field_cleared_absent(
        tmp_path, monkeypatch, first_pass_path):
    """The collecting method clears as not on the label, and the second label's readers differ only in the
    letter case of "LEWIS" / "lewis", the collection code both readers' label rows hold, settled; the label's
    habitat, which both readers write alike, is left for a person. Every unit whose readers' texts differ lies
    inside the settled code on each reading, so on the units path the label loses unresolved_transcription and
    the habitat keeps its own reason; on the old path the label keeps it, as on main."""
    rig, run = coded(tmp_path, monkeypatch, "collection_code: LEWIS", "collection_code: lewis")
    region = second_region(run)
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    evidence = {item.id: item for item in run.evidence}
    assert field_step.not_on_label("collection_method", run.fields["collection_method"], run, evidence, allowed)
    assert run.fields["collection_code"].state == ValueState.SUPPORTED
    assert "mandatory_unresolved:habitat" in run.reasons
    assert (transcription(run, region) in run.reasons) is (first_pass_path == "old")
    if first_pass_path == "units":
        assert not field_step.readings_conflict(run, region, allowed)
        for alter in (no_rows, no_row_on_2b, row_text_not_the_literal, quote_not_the_reading, code_not_settled):
            changed = run.model_copy(deep=True)
            alter(changed)
            assert field_step.readings_conflict(changed, region, allowed), alter.__name__


def coded(tmp_path, monkeypatch, line_a, line_b):
    """without_the_method's run whose second label writes the collection code as `line_a` and `line_b` and a
    habitat both readers write alike: the code settles on 2A's "LEWIS", and the habitat is left unsure."""
    return without_the_method(tmp_path, monkeypatch, line_a + "\nhabitat: Grass", line_b + "\nhabitat: Grass",
        candidates=[("collection_code", "2A", "LEWIS", line_a), ("collection_code", "2B", "lewis", line_b),
            *(("habitat", name, "Grass", "habitat: Grass") for name in ("2A", "2B"))],
        also=("collection_code", "habitat"), scripts={
            "collection_code": answering(resolved("LEWIS", reading="2A")),
            "habitat": answering(LACKS.model_copy(update={"outcome": "sources_cannot_resolve", "literal": "Grass",
                "reading_names": ["2A", "2B"], "explanation": "Whether Grass is the habitat is unsure."}))})


def test_a_case_difference_that_runs_beyond_a_settled_fields_text_keeps_the_reason(tmp_path, monkeypatch,
        first_pass_path):
    """As the case above, but the unit whose readers' texts differ is "LEWIS," against "lewis,", which runs past
    the settled code "LEWIS": that unit is not wholly the code's text, so the label keeps
    unresolved_transcription on both paths."""
    rig, run = coded(tmp_path, monkeypatch, "collection_code: LEWIS, 1916", "collection_code: lewis, 1916")
    region = second_region(run)
    assert run.fields["collection_code"].state == ValueState.SUPPORTED
    assert transcription(run, region) in run.reasons
    if first_pass_path == "units":
        assert [texts for texts in (sorted(span.text for span in unit.readers.values())
            for unit in note_units(run).units) if len(set(texts)) > 1] == [["LEWIS,", "lewis,"]]


def code_rows(run):
    """The collection code's label rows on the second label, by reading name."""
    from specimen_digitization.application.organiser import parse_locator

    rows = {item.id: item for item in run.evidence}
    return {parse_locator(rows[i].locator).label: rows[i] for i in run.fields["collection_code"].evidence_ids
        if i in rows and parse_locator(rows[i].locator) is not None}


def no_rows(run):
    run.fields["collection_code"].evidence_ids.clear()


def no_row_on_2b(run):
    run.fields["collection_code"].evidence_ids.remove(code_rows(run)["2B"].id)


def row_text_not_the_literal(run):
    """2B's row places its literal over the whole line, which is not the settled code."""
    from specimen_digitization.application.organiser import format_locator, parse_locator

    row = code_rows(run)["2B"]
    found = parse_locator(row.locator)
    line = "collection_code: lewis"
    start = row.excerpt.index(line) + found.quote_start
    row.locator = format_locator(found.__class__(found.label, found.observation_id, found.quote_start,
        found.quote_end, start, start + len(line)))


def quote_not_the_reading(run):
    code_rows(run)["2B"].excerpt += "!"


def code_not_settled(run):
    run.fields["collection_code"].state = ValueState.UNRESOLVED


def test_a_field_held_on_a_label_whose_reason_is_dropped_keeps_its_own(tmp_path, monkeypatch, first_pass_path):
    """The second label's readers differ only in letter case, and its collection code, which only that label
    writes and both readers write alike, is answered as unsure: the label loses unresolved_transcription on the
    units path, but the field keeps its own reason, so the record still goes to a person for it."""
    second_label_read(monkeypatch, "collection_code: LEWIS\n" + CASE_A, "collection_code: LEWIS\n" + CASE_B)
    rig = build_rig(tmp_path, label_with(collection_code=None), candidates=every_field(
        *(("collection_code", name, "LEWIS", "collection_code: LEWIS") for name in ("2A", "2B"))))
    run = rig.specimen.run
    unsure = answering(LACKS.model_copy(update={"outcome": "sources_cannot_resolve", "literal": "LEWIS",
        "reading_names": ["2A", "2B"], "explanation": "Whether LEWIS is the code is unsure."}))
    settle(rig, Scripted({"collection_code": unsure}))
    region = second_region(run)
    assert run.fields["collection_code"].state != ValueState.SUPPORTED
    assert "mandatory_unresolved:collection_code" in run.reasons and run.disposition == Disposition.REVIEW
    assert (transcription(run, region) in run.reasons) is (first_pass_path == "old")


# ---- (ii) mandatory_unresolved on a field settled absent ------------------------------------------

# The fields contracts.NOT_ON_LABEL leaves out, each kept out by WP 2.R from its sources (contracts.py's
# comment): none clears as not on the label. identified_by_irn never routes (G16, G43); the taxon follows owner
# decision B as WP 2.T left it.
LEFT_OUT = ("fmnh_ins_number", "country", "province_state", "date_visited_from", "date_visited_to", "collectors",
    "verbatim_dts")


def test_the_not_on_label_list_is_unchanged_by_wp_2r():
    [key] = contracts.NOT_ON_LABEL
    listed = contracts.NOT_ON_LABEL[key]
    assert not listed & {*LEFT_OUT, "taxon", "identified_by_irn"}
    assert contracts.not_on_label_fields(*key) == listed


@pytest.mark.parametrize("key", LEFT_OUT)
def test_a_field_left_off_the_list_keeps_its_reason_when_the_label_does_not_write_it(tmp_path, key,
        first_pass_path):
    """Its line is off the label, the organiser gives no candidate for it and its expert answers
    label_lacks_value: on both paths no not-on-the-label row clears it. Each but Date Visited To is not present
    and keeps mandatory_unresolved; Date Visited To is derived from the settled Date Visited From (G44), so it
    has no reason of its own (and it waits while its source is held: the next test)."""
    # A country or a province is derived from a settled place below it (derive.fill): the label then writes
    # no place at all.
    places = ("country", "province_state", "county", "city") if key in ("country", "province_state") else (key,)
    text = TEXT.replace("\nleg. J. Smith", "") if key == "collectors" else label_with(**dict.fromkeys(places))
    rig = build_rig(tmp_path, text, candidates=[] if key == "collectors" else every_field())
    run = rig.specimen.run
    settle(rig, Scripted(dict.fromkeys(places, answering(LACKS))))
    value = run.fields[key]
    if key == "date_visited_to":
        # The step's derivation from the collecting date (G44) fills it: no reason of its own.
        assert value.layer == "derived" and f"mandatory_unresolved:{key}" not in run.reasons
        return
    assert value.state == ValueState.NOT_PRESENT
    rows = {item.id: item for item in run.evidence}
    assert not [i for i in value.evidence_ids if rows[i].locator == field_step.NOT_ON_LABEL_CHECK]
    assert f"mandatory_unresolved:{key}" in run.reasons and run.disposition == Disposition.REVIEW


def test_a_field_that_waits_for_its_source_is_never_settled_absent(tmp_path, first_pass_path):
    """Date Visited To follows Date Visited From (G44), which the readers write differently and which stays
    held. On the units path the To date waits (WP 2.3b, ontology_checks.waiting_fields): unknown, no
    not-on-the-label row and no reason of its own, its source's reason routing the record. On the old path it
    is not present with its own reason, as on main."""
    first, second = (label_with(date_visited_from=date) for date in ("2020-06-01", "2020-06-07"))
    rig = build_rig(tmp_path, first, second, candidates=every_field(
        ("date_visited_from", "1A", "2020-06-01", "date_visited_from: 2020-06-01"),
        ("date_visited_from", "1B", "2020-06-07", "date_visited_from: 2020-06-07")))
    run = rig.specimen.run
    several = answering(LACKS.model_copy(update={"outcome": "several_possibilities",
        "options": ["2020-06-01", "2020-06-07"], "reading_names": ["1A", "1B"],
        "explanation": "The readers write two dates."}))
    settle(rig, Scripted({"date_visited_from": several, "date_visited_to": answering(LACKS)}))
    to = run.fields["date_visited_to"]
    rows = {item.id: item for item in run.evidence}
    assert not [i for i in to.evidence_ids if rows[i].locator == field_step.NOT_ON_LABEL_CHECK]
    assert "mandatory_unresolved:date_visited_from" in run.reasons
    if first_pass_path == "units":
        assert "date_visited_to" in ontology_checks.waiting_fields(run)
        assert to.state == ValueState.UNKNOWN and "mandatory_unresolved:date_visited_to" not in run.reasons
    else:
        assert to.state == ValueState.NOT_PRESENT and "mandatory_unresolved:date_visited_to" in run.reasons
