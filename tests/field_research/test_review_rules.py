"""WP 2.R of docs/execution/units/PLAN.md: the two review rules checked against their requirements. The owner
typed on 2026-11-14: "4 shouldn't be flagged. It should be caught and handled. Goal isn't to throw everything
at the user it is to help by being in in autonomy as much as possible." and "Harness needs to work and do its
magic".

(i) unresolved_transcription keeps main's rule on both paths. WP 2.R tried dropping it on the units path for a
label whose readers' differences decide no field, then for one whose readers differ only in letter case or spacing,
and removed both (the coordinator's decision on #441's second review): the last form dropped 4 labels of the stored
runs, on drawn slides, finished no specimen, and each review round found an input where such a difference decides a
field. The inputs stay below as regressions, the reason kept on both paths.

(ii) mandatory_unresolved is not raised for a field settled absent as not on the label (owner decision A,
docs/execution/golive/FIELD_RESEARCH.md, "Fields the label does not state") only where its expert answered
label_lacks_value, or its answer falls under one of the place cases step.mark_not_on_label names (for a precise
location, `no_finer`: only an administrative marker beside the places settled, or `repeated`: only a settled place's
text; for a county or a city, `above`: only the text of a settled place above it), and the not-on-the-label check row
agrees (step.mark_not_on_label, step.not_on_label). WP 2.R
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
    resolved,
    settle,
)

from specimen_digitization.application.domain import Disposition, Observation, Region, ValueState
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.field_research import contracts, ontology_checks
from specimen_digitization.field_research import step as field_step

# 105526326's third label (wp15c): its readers differ only in letter case, as 19 of the 20 labels the first tried
# form dropped there do.
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


def transcription(run, region):
    return f"unresolved_transcription:{region}"


def noted(tmp_path, monkeypatch, *texts, refused=False):
    """test_step's label, which both readers read alike and every field's expert settles, and a second label
    its readers read as `texts`."""
    second_label_read(monkeypatch, *texts)
    rig = build_rig(tmp_path, candidates=every_field(), refused=refused)
    settle(rig, Scripted())
    return rig, rig.specimen.run


# ---- (i) unresolved_transcription: main's rule, the tried inputs as regressions -------------------

@pytest.mark.parametrize("texts", [
    (CASE_A, CASE_B),
    (NOTE_A, NOTE_B),
    ("IV-25\n1948", "IV-25\n1949"),
    ("IV-25\n1948\nMt. Apo", "IV-25\n1948\nMT. APO"),
], ids=["letter-case-or-spacing", "a-note-no-field-draws", "the-year-beside-IV-25", "Mt-Apo-MT-APO"])
def test_a_second_label_whose_readers_differ_keeps_the_reason(tmp_path, monkeypatch, first_pass_path, texts):
    """The inputs of WP 2.R's tried narrowings: readers that differ only in letter case or spacing ("Sp. 22" /
    "sp. 22"); on a note no field draws (105526329's "head 4 legs" / "head + legs"); on a year beside the date
    "IV-25" (Codex on #441's first review); and in the case of "Mt. Apo" / "MT. APO" below it, which
    date_lines reads as a unit after the year in one reading only (Codex on #441's second review). The label
    keeps unresolved_transcription on both paths, as on main."""
    rig, run = noted(tmp_path, monkeypatch, *texts)
    region = second_region(run)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def test_a_label_whose_readers_differ_on_a_fields_literal_keeps_the_reason(tmp_path, first_pass_path):
    """1A writes "J. Smith", 1B "J. Smyth"; the collectors' expert settles 1A's text, which the readers do not
    agree on. The label keeps unresolved_transcription on both paths, and the collectors their own reason
    (test_step's test_on_a_label_with_no_decided_transcript_the_way_out_is_a_transcription_decision)."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    run = rig.specimen.run
    settle(rig, Scripted({"collectors": answering(resolved("J. Smith", reading="1A"))}))
    region = run.regions[0].id
    assert (run.disposition, run.reasons) == (Disposition.REVIEW,
        [transcription(run, region), "mandatory_unresolved:collectors"])


def test_a_label_whose_first_pass_was_given_up_keeps_the_reason(tmp_path, monkeypatch, first_pass_path):
    """The letter-case labels above, with the first pass refused on every attempt and given up: the second
    label keeps unresolved_transcription on both paths (HARNESS.md, a given-up label goes to review however its
    fields settle)."""
    rig, run = noted(tmp_path, monkeypatch, CASE_A, CASE_B, refused=True)
    region = second_region(run)
    assert region in field_step.given_up_regions(run)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


def test_a_label_one_reader_read_keeps_the_reason(tmp_path, monkeypatch, first_pass_path):
    """The second label's other reader read nothing (wp15c's pair arm, where one reader returned nothing on
    seven labels): the label keeps unresolved_transcription on both paths."""
    rig, run = noted(tmp_path, monkeypatch, NOTE_A, "")
    region = second_region(run)
    assert [r.text for r in field_step.run_readings(run) if r.region_id == region] == [NOTE_A]
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


@pytest.mark.parametrize("texts", [("Malaise trap\nslide 2", "slide 2"), ("Malaise trap\nslide 2", "Malaise trep\nslide 2"),
    ("Malaise trap\nslide 2", "MALAISE TRAP\nslide 2")], ids=["a-line-one-reader-lacks", "trap-trep", "letter-case"])
def test_a_label_whose_readers_write_a_cleared_fields_text_keeps_the_reason(tmp_path, monkeypatch,
        first_pass_path, texts):
    """G51's input on #441's first review: the second label writes "Malaise trap", which one reader leaves
    out, misreads as "Malaise trep" or writes in capitals, and the collecting method clears as not on the
    label. Its label's reason is the only one that sends that field to a person: the label keeps
    unresolved_transcription on both paths."""
    second_label_read(monkeypatch, *texts)
    rig = build_rig(tmp_path, label_with(collection_method=None), candidates=every_field())
    run = rig.specimen.run
    settle(rig, Scripted({"collection_method": answering(LACKS)}))
    region = second_region(run)
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    evidence = {item.id: item for item in run.evidence}
    assert field_step.not_on_label("collection_method", run.fields["collection_method"], run, evidence, allowed)
    assert transcription(run, region) in run.reasons and run.disposition == Disposition.REVIEW


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
