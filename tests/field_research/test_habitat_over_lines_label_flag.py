"""A Habitat settled over consecutive lines on a label whose transcription is unresolved carries
`label_unsettled:habitat` unless rule A lifts it (lane H4 of the autonomy program, fix round 3 of PR #464, 2026-11-21;
the coordinator's ruling R3', not the owner's words).

Why. For a label that is not in step.scientific_reasons' given-up branch (its first pass was not given up on, or a
person has transcribed it since with a resolved text) and whose transcription is unresolved, that function gives no
label's code (`unresolved_transcription:<label>`) where a field is drawn from the label and every drawn field whose
work is terminal is supported and is grounded in a raw reading or a derived value (its branches in full:
docs/execution/autonomy/PLAN.md, "H4", "The label's code"), and step.label_attention gave `label_unsettled:<field>` for a field drawn from a label one of whose
own codes is an open reason, and for no other. A Habitat this
lane settles over lines, the only field drawn from its label or drawn beside settled fields, therefore got no flag
where its two readers write it differently and the image backs one of them: the shape of truth slide 105527313, whose
flag came only from an unsettled Date Identified drawn from the same label. origin/main 3eb37c11 refuses that Habitat
and flags it. The run-the-code reviewer's round 3 ran it through the workflow (four shapes, no flag on 575367fe).

Now step.label_attention gives the Habitat's own code for such a value (step._over_lines, step._unread_labels), on a
run no person approved; no label's code and no other field's code is added. Rule A lifts it as before: the second
opinion agrees and every reading of the Habitat's labels holds its text (second_opinion.agreed).

Through the real workflow with the second opinion's step, its model scripted (the rig of test_agreed_no_flag). Label 1
is the rig's label, both readers alike; label 2 is the host's label. What origin/main 3eb37c11 and 575367fe give for
each shape was run on those trees: ~/specimen-golive/autonomy-program/H4/fix3_probe_label_*.txt. A habitat on ONE line
keeps origin/main's rule (a one-line value the image backs settles with no flag there too): pinned here as a limit.
So does a habitat that is a whole organiser candidate over two lines (no finding of a literal read from the
transcript, so no step._over_lines value): not pinned here; the run-the-code reviewer's round 4 ran it on both trees
(~/specimen-golive/autonomy-program/reviews/g51_probes/g51_464/r4/out/r4_label_cmp.txt, `candidate_two_lines`).
"""

from __future__ import annotations

import hashlib
import io

import pytest
import test_step
from PIL import Image
from test_agreed_no_flag import AHEAD, flagged, published, to_end
from test_second_opinion import Opinion
from test_step import COLLECTORS, TEXT, TODAY, Scripted, answering, build_rig, mounted

from specimen_digitization.application.domain import Observation, Region, ValueState
from specimen_digitization.application.workflow import store_reading_units
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
FLAG = "label_unsettled:habitat"
HOST = "Mus\nmusculus"
LABEL_2 = "Synthetic Museum\nHost:\nMus\nmusculus\nAlc. Skin Fresh x"
WITH_METHOD = "Synthetic Museum\nSynthetic net\nHost:\nMus\nmusculus\nAlc. Skin Fresh x"
NO_HABITAT = TEXT.replace("habitat: Synthetic grassland\n", "")
METHOD_LINE = "collection_method: Synthetic net\n"


def resolved(literal, *names):
    return answering(FieldAnswer(outcome="resolved", literal=literal, reading_names=list(names),
        explanation="As written."))


def several(*options):
    return answering(FieldAnswer(outcome="several_possibilities", options=list(options),
        explanation="The readers differ."))


def second_label(monkeypatch, first, other):
    """build_rig's specimen with a second label, which the two readers read as `first` and as `other`."""
    original = test_step.make_specimen

    def make(blobs, text=TEXT, second=None, *, profile=None):
        specimen = original(blobs, text, second) if profile is None else original(blobs, text, second, profile=profile)
        run = specimen.run
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
        region = Region(asset_id=specimen.asset.id, x=0, y=50, width=100, height=50, order=1,
            method="synthetic_fixture_region", version="1")
        crop_png = test_step.region_png(Image.open(io.BytesIO(output.getvalue())), region)
        region.crop_ref = blobs.put(crop_png)
        run.regions.append(region)
        crop = hashlib.sha256(crop_png).hexdigest()
        for route, written in zip(run.profile.routes, (first, other), strict=True):
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + written).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop,
                input_asset_id=specimen.asset.id, input_crop_ref=region.crop_ref, literal_text=written,
                raw_ref=blobs.put(raw), raw_sha256=hashlib.sha256(raw).hexdigest()))
            run.completed_steps.append(f"transcribe:{region.id}:{route}")
        return specimen

    monkeypatch.setattr(test_step, "make_specimen", make)


def finished_rig(tmp_path, monkeypatch, first, other, scripts, *, image=False, opinion=None):
    """The rig whose record went through the workflow to its end. `image`: the first pass's image names the first reader's text at
    each unit of label 2 where the readers differ (True), or only at those of the host's words ("host"). `opinion`:
    entries that replace the second opinion's answer, which otherwise agrees with every settled value."""
    second_label(monkeypatch, first, other)

    def build(folder, model):
        text = NO_HABITAT.replace(METHOD_LINE, "") if "collection_method" in scripts else NO_HABITAT
        rig = build_rig(folder, text, text, candidates=COLLECTORS, profile=published())
        mounted(rig, Scripted(dict(scripts)))
        rig.workflow.second_opinion = None if model is None else so.SecondOpinionStep(model_factory=model.factory)
        if image:
            stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
            run = stored.run
            label = run.regions[1].id
            reader = next(item.id for item in run.observations if item.region_id == label)
            store_reading_units(run, [entry.model_copy(update={"units": [
                unit.model_copy(update={"image": unit.readers[reader].text})
                if reader in unit.readers and len({span.text for span in unit.readers.values()}) > 1
                and unit.readers[reader].text and (image is True or "mus" in unit.readers[reader].text) else unit
                for unit in entry.units]}) if entry.label == label else entry for entry in run.reading_units])
            rig.specimen = rig.repository.save(rig.principal, stored, stored.version, "images", "images")
        rig.clock.now = AHEAD
        return rig

    plain = to_end(build(tmp_path / "unjudged", None)).run
    values = {key: so.shown(value) for key, value in plain.fields.items() if value.state == ValueState.SUPPORTED}
    answer = {key: {"value": values.get(key), "evidence": "L: synthetic" if values.get(key) else ""}
        for key in so.FIELDS}
    rig = build(tmp_path / "judged", Opinion({**answer, **(opinion or {})}))
    to_end(rig)
    return rig


def finished(tmp_path, monkeypatch, first, other, scripts, *, image=False, opinion=None):
    """finished_rig's stored run."""
    rig = finished_rig(tmp_path, monkeypatch, first, other, scripts, image=image, opinion=opinion)
    return rig.repository.get(rig.principal.scope, rig.specimen.id).run


def codes(run):
    """The record's open reasons with its labels' ids replaced by their place."""
    names = {region.id: f"<label {number}>" for number, region in enumerate(run.regions, start=1)}
    found = []
    for code in run.open_reasons:
        for region, name in names.items():
            code = code.replace(region, name)
        found.append(code)
    return found


MISREAD = LABEL_2.replace("musculus", "muscalus")
SHAPES = {
    # 105527313's shape: the readers differ on the host's second line, the image names the first reader's.
    "the-only-field-drawn": ((LABEL_2, MISREAD), {"habitat": several(HOST, "Mus\nmuscalus")}, True, [FLAG]),
    "a-resolved-answer-naming-one-reader": ((LABEL_2, MISREAD), {"habitat": resolved(HOST, "2A")}, True, [FLAG]),
    "beside-a-settled-field-of-the-label": ((WITH_METHOD, WITH_METHOD.replace("musculus", "muscalus")),
        {"habitat": several(HOST, "Mus\nmuscalus"), "collection_method": resolved("Synthetic net", "2A", "2B")},
        True, [FLAG]),
    "beside-an-unsettled-field-with-no-value": (
        (WITH_METHOD, WITH_METHOD.replace("musculus", "muscalus").replace("net", "met")),
        {"habitat": several(HOST, "Mus\nmuscalus"), "collection_method": several("Synthetic net", "Synthetic met")},
        "host", ["mandatory_unresolved:collection_method", FLAG]),
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_a_habitat_over_lines_whose_readers_differ_keeps_its_labels_flag(tmp_path, monkeypatch, shape):
    """The run-the-code reviewer's four shapes. The Habitat settles on the first reader's two lines (the image backs
    them), the second opinion agrees with it, and the second reader writes another text for it. 575367fe: no open
    reason names the Habitat and it carries no flag. origin/main: the Habitat is ambiguous or unresolved, and
    flagged. Now it keeps `label_unsettled:habitat` (rule A does not lift it: a reading of its label does not hold
    its text), and the record's other open reasons are 575367fe's: no label's code, no other field's code."""
    (first, other), scripts, image, expected = SHAPES[shape]
    run = finished(tmp_path, monkeypatch, first, other, scripts, image=image)
    habitat = run.fields["habitat"]
    assert (habitat.state, habitat.literal) == (ValueState.SUPPORTED, HOST)
    assert run.second_opinion["fields"]["habitat"]["verdict"] == so.AGREES_VERDICT
    assert so._a_reader_differs(run, "habitat", field_step.run_readings(run))
    assert codes(run) == expected and "habitat" in flagged(run) and run.reasons == []
    # Derived at each finalize from the run as it is: a second finalize gives the same.
    before = (list(run.reasons), list(run.open_reasons))
    field_step.refinalize(run, today=TODAY)
    assert (list(run.reasons), list(run.open_reasons)) == before


FROSH = LABEL_2.replace("Fresh", "Frosh")


def test_readers_who_write_the_habitat_alike_and_an_agreeing_second_opinion_leave_no_flag(tmp_path, monkeypatch):
    """Label 2's readers differ on another line only, so its transcription is unresolved; both write the host's two
    lines; the second opinion agrees. The flag is given and rule A lifts it: no open reason, as on 575367fe."""
    run = finished(tmp_path, monkeypatch, LABEL_2, FROSH, {"habitat": resolved(HOST, "2A", "2B")})
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, HOST)
    assert FLAG in field_step.label_attention(run, [])
    assert codes(run) == [] and "habitat" not in flagged(run)


def test_a_second_opinion_that_differs_leaves_the_flag_beside_its_mark(tmp_path, monkeypatch):
    """The same label; the second opinion gives another host. 575367fe: the mark alone. Now the label's flag too:
    rule A lifts nothing from a value the second opinion does not agree with."""
    run = finished(tmp_path, monkeypatch, LABEL_2, FROSH, {"habitat": resolved(HOST, "2A", "2B")},
        opinion={"habitat": {"value": "Rattus rattus", "evidence": "L2: another host"}})
    assert codes(run) == ["marked:habitat:<label 2>:second_opinion_differs", FLAG]


def test_a_label_both_readers_read_alike_gives_no_flag(tmp_path, monkeypatch):
    """Label 2's transcription is resolved: nothing is in doubt on the label, and no flag is given."""
    run = finished(tmp_path, monkeypatch, LABEL_2, LABEL_2, {"habitat": resolved(HOST, "2A", "2B")})
    assert run.fields["habitat"].literal == HOST and codes(run) == []
    assert field_step.label_attention(run, []) == []


def test_an_approved_run_and_a_habitat_decision_carried_into_the_run_get_no_flag_from_this_rule(tmp_path, monkeypatch):
    """On the record of the first shape: once a person approved the run, this rule adds nothing; and it adds nothing
    for a Habitat whose decision was CARRIED INTO the run by a reprocess (step.human_keys, one of the records
    step._over_lines tests through second_opinion.authority). The carried decision is injected at step.human_keys
    here, not made by a reprocess. A decision a person makes ON the run, through the decision endpoint: the next
    test."""
    (first, other), scripts, image, _ = SHAPES["the-only-field-drawn"]
    run = finished(tmp_path, monkeypatch, first, other, scripts, image=image)
    assert field_step.label_attention(run, []) == [FLAG]
    approved = run.model_copy(deep=True)
    approved.human_approved = True
    assert field_step.label_attention(approved, []) == []
    monkeypatch.setattr(field_step, "human_keys", lambda run: frozenset({"habitat"}))
    assert field_step.label_attention(run, []) == []


def test_a_habitat_a_person_decides_on_the_run_gets_no_flag_from_this_rule(tmp_path, monkeypatch):
    """Through the decision endpoint, nothing patched (the run-the-code reviewer's round 4 sequence, on the record of
    the first shape). A decision made on the run is recorded in Run.person_decided_fields, which
    second_opinion.authority(run) holds, and step._over_lines is false for a field a person holds authority over:
    research's Habitat carries the flag; a person confirms it unchanged and the flag is gone; a person changes it to
    the other reader's two lines and no flag is given; the person approves the record and none is given. The record
    waits for that approval from the first decision on (`human_approval_required`). The coordinator's ruling R4' of
    2026-11-21 on round 5 of #464's review (not the owner's words). In round 4 this test pinned the opposite, under
    ruling R4, which R4' replaces: the flag stayed until approval, because step._over_lines looked at step.human_keys
    only. Red on 61f3fdb8's source (the flag stays). On origin/main's source it cannot run as written: that source
    has no step._over_lines, which this test calls. ~/specimen-golive/autonomy-program/H4/red_fix5_*.txt."""
    (first, other), scripts, image, _ = SHAPES["the-only-field-drawn"]
    rig = finished_rig(tmp_path, monkeypatch, first, other, scripts, image=image)
    client = test_step.review_client(rig)

    def decided(name, **change):
        value = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields["habitat"]
        after = value.model_dump(mode="json", exclude={"evidence_ids"}) | change
        return test_step.decide(client, rig, name, "field", target_id="habitat", after=after,
            evidence_ids=list(value.evidence_ids))

    def over_lines(run):
        return field_step._over_lines(run, "habitat", run.fields["habitat"], field_step.human_keys(run))

    def state(run):
        habitat = run.fields["habitat"]
        return (habitat.state, habitat.literal, list(run.person_decided_fields), field_step.human_keys(run),
            over_lines(run), codes(run), list(run.reasons), run.human_approved)

    held = ["human_approval_required"]
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert state(run) == (ValueState.SUPPORTED, HOST, [], frozenset(), True, [FLAG], [], False)
    run = decided("confirm-1")
    assert state(run) == (ValueState.SUPPORTED, HOST, ["habitat"], frozenset(), False, [], held, False)
    assert "habitat" in so.authority(run) and field_step.label_attention(run, []) == []
    other_text = "Mus\nmuscalus"
    run = decided("change-1", literal=other_text, parsed=other_text, normalized=other_text)
    assert state(run) == (ValueState.SUPPORTED, other_text, ["habitat"], frozenset(), False,
        ["evidence_does_not_support_value:habitat"], held, False)
    run = test_step.decide(client, rig, "approve-1", "approve")
    assert state(run) == (ValueState.SUPPORTED, other_text, ["habitat"], frozenset(), False,
        ["evidence_does_not_support_value:habitat"], [], True)
    assert field_step.label_attention(run, []) == []


ONE_LINE = "Synthetic Museum\nHost: Mus musculus\nAlc. Skin Fresh x"


@pytest.mark.parametrize(("other", "answer", "image"), [
    (ONE_LINE.replace("Fresh", "Frosh"), resolved("Mus musculus", "2A", "2B"), False),
    (ONE_LINE.replace("musculus", "muscalus"), several("Mus musculus", "Mus muscalus"), True),
], ids=["readers-differ-elsewhere", "readers-differ-on-the-host"])
def test_limit_a_habitat_on_one_line_keeps_origin_mains_rule(tmp_path, monkeypatch, other, answer, image):
    """Stated as it is: a host on ONE line settles on origin/main 3eb37c11 too, and there as here it carries no
    flag when it is the only field drawn from its label, the image backs it and the second opinion agrees, even
    where the second reader writes it otherwise. The rule of this file is for the value this lane newly settles,
    text read over consecutive lines."""
    run = finished(tmp_path, monkeypatch, ONE_LINE, other, {"habitat": answer}, image=image)
    assert (run.fields["habitat"].state, run.fields["habitat"].literal) == (ValueState.SUPPORTED, "Mus musculus")
    assert codes(run) == [] and "habitat" not in flagged(run)
    assert field_step.label_attention(run, []) == []


# ---- the two conditions, each as the code has it --------------------------------------------------------------

def test_which_labels_count_as_unread(tmp_path, monkeypatch):
    """step._unread_labels, the label's condition of the rule, by step.scientific_reasons' two tests of a label:
    (a) its first pass was given up on (a `first_pass` give-up finding for it and no first-pass decision) and no
    person has transcribed it since (a transcript of the label with a person as its actor, resolved, with text);
    (b) else: it has no transcript, or a transcript of it is not resolved or has no text. The record of the first
    shape: label 1 is read alike (resolved), label 2's readers differ (not resolved)."""
    from specimen_digitization.application import first_pass
    from specimen_digitization.application.domain import RunFinding

    (first, other), scripts, image, _ = SHAPES["the-only-field-drawn"]
    run = finished(tmp_path, monkeypatch, first, other, scripts, image=image)
    label_1, label_2 = (region.id for region in run.regions)
    assert field_step._unread_labels(run) == {label_2}
    transcripts = {item.region_id: item for item in run.transcripts}
    assert transcripts[label_1].resolved and not transcripts[label_2].resolved

    def after(change):
        copy = run.model_copy(deep=True)
        change(copy, {item.region_id: item for item in copy.transcripts})
        return field_step._unread_labels(copy), field_step.label_attention(copy, [])

    def read(copy, by, text=LABEL_2):
        by[label_2].resolved, by[label_2].text = True, text

    # (b) resolved with text: the label is read, and the Habitat gets no flag from this rule.
    assert after(read) == (frozenset(), [])
    # (b) resolved with no text, not resolved though it has text, or no transcript at all: unread.
    assert after(lambda copy, by: read(copy, by, "")) == (frozenset({label_2}), [FLAG])
    assert after(lambda copy, by: (read(copy, by), setattr(by[label_2], "resolved", False))) == (
        frozenset({label_2}), [FLAG])
    assert after(lambda copy, by: copy.transcripts.remove(by[label_2])) == (frozenset({label_2}), [FLAG])

    # (a) given up: unread although its transcript is resolved, until a person's transcript of it stands.
    def given_up(copy, by, *, person=False):
        read(copy, by)
        copy.first_pass_decisions[:] = [item for item in copy.first_pass_decisions if item.region_id != label_2]
        copy.findings.append(RunFinding(rule_id=first_pass.GIVEN_UP, rule_version="test", severity="warning",
            reason_code=f"{first_pass.GIVEN_UP}:{label_2}"))
        if person:
            by[label_2].actor = "a-person"

    assert after(given_up) == (frozenset({label_2}), [FLAG])
    assert after(lambda copy, by: given_up(copy, by, person=True)) == (frozenset(), [])


def test_the_rule_needs_a_run_no_person_approved_and_a_value_research_settled_over_lines(tmp_path, monkeypatch):
    """`run.human_approved` true: nothing is added (an approval's own finalize decides what a person reviews). A
    value that is no step._over_lines value gets nothing either: a literal on one line, a habitat a person holds
    authority over by the run's record (second_opinion.authority; the two tests above), or one the run holds no transcript-literal finding for."""
    (first, other), scripts, image, _ = SHAPES["the-only-field-drawn"]
    run = finished(tmp_path, monkeypatch, first, other, scripts, image=image)
    assert not run.human_approved and field_step.label_attention(run, []) == [FLAG]

    def changed(change):
        copy = run.model_copy(deep=True)
        change(copy)
        return field_step.label_attention(copy, [])

    assert changed(lambda copy: setattr(copy, "human_approved", True)) == []
    assert changed(lambda copy: setattr(copy.fields["habitat"], "literal", "Mus musculus")) == []
    code = field_step.transcript_code("habitat")
    assert any(finding.reason_code == code for finding in run.findings)
    assert changed(lambda copy: copy.findings.__setitem__(slice(None),
        [finding for finding in copy.findings if finding.reason_code != code])) == []
