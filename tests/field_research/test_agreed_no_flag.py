"""Work package F2 (docs/execution/autonomy/PLAN.md): an agreed value and an agreed blank carry no flag.

The two rules are the coordinator's rulings of 2026-11-19 on lane H1's measurement over the 100 truth slides,
under the owner's ruling of 2026-11-18 and his approved plan of 2026-11-17. They are derived at every finalize
from the second opinion's stored result and the run as it is now (second_opinion.unflagged, called by
step.finalize_fields), and they only shorten the optional fields' doubts (run.open_reasons):

- rule A: `label_unsettled:<field>` is not an open reason for a field settled with a value the second opinion
  agrees with, the three date fields excepted;
- rule B: `mandatory_unresolved:<field>` and `label_unsettled:<field>` are not open reasons for a blank field
  the current, obtained second opinion also leaves blank, Verbatim D/T/S excepted.

Every record here is the field research rig's (test_step.build_rig) on the published profile, taken through the
workflow with the second opinion's step mounted as in production but for its model. The rig's one label carries
the catalogue number, so its readers' difference would hold the record; the slide's QR code confirms the number
(`coded`), which leaves the label's doubt open and every field drawn from it `label_unsettled`, as on the live
slides. Each test compares the record with the same record finalized with the rules turned off (`off`): the
disposition, the holding reasons, the fields, the findings and the stored result are identical, and the open
reasons differ by exactly the codes the test names.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_second_opinion import Opinion
from test_skeletal_disposition import LACKS
from test_step import (
    SMITH_OR_SMYTH,
    SMYTH,
    TEXT,
    TODAY,
    Scripted,
    answering,
    build_rig,
    decide,
    every_field,
    field_mechanics_profile,
    mounted,
    resolved,
    review_client,
)

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, Evidence, RunFinding, ValueState
from specimen_digitization.application.review_summary import attention_fields, project_fields
from specimen_digitization.application.standing_holds import APPROVAL, HISTORY_RESTORED
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
CATALOGUE = "fmnh_ins_number"
# The step's clock, after the readings' (Observation.created_at is the wall clock; the rig's clock is fixed).
AHEAD = datetime(2031, 1, 1, tzinfo=timezone.utc)
# The fields the experts leave blank in the rule B record; the rule's own exception among them.
BLANKS = ("taxon", "habitat", "verbatim_dts", "collection_code", "date_identified", "collection_method", "country")
AGREED_BLANKS = frozenset(BLANKS) - {"verbatim_dts"}
MEADOW = {"value": "Synthetic meadow", "evidence": "L1: meadow"}
LABEL_UNSETTLED, UNRESOLVED = field_step.LABEL_UNSETTLED, "mandatory_unresolved"


def published():
    return published_registry().profiles[0]


def differing(blanks=()):
    """test_review_rules' Smith/Smyth label (the readers differ on the collectors), with `blanks` left blank."""
    return TEXT, SMYTH, every_field(*SMITH_OR_SMYTH), Scripted(
        {"collectors": answering(resolved("J. Smith", reading="1A"))} | {key: answering(LACKS) for key in blanks})


def coded(rig):
    """The slide's QR code, stored on the label as barcode.record stores it: it confirms the catalogue number."""
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    run = stored.run
    run.evidence.append(Evidence(kind="derived", asset_id=stored.asset.id, region_id=run.regions[0].id,
        source="barcode", locator="check:barcode_decode",
        excerpt=f"{CATALOGUE}: 0010001 (QR code read by zxing-cpp 3.1.1, ladder rung whole)"))
    rig.specimen = rig.repository.save(rig.principal, stored, stored.version, "code", "code")
    return rig


def rig_of(folder, blanks=(), *, opinion=None, profile=None):
    """The rig's record with the readers differing and the code confirming the number; `opinion` answers the
    second opinion's step (None: switched off)."""
    text, other, candidates, script = differing(blanks)
    rig = build_rig(folder, text, other, candidates=candidates, profile=profile or published())
    mounted(rig, script)
    rig.workflow.second_opinion = None if opinion is None else so.SecondOpinionStep(model_factory=opinion.factory)
    coded(rig)
    rig.clock.now = AHEAD
    return rig


def to_end(rig):
    return rig.workflow.drain(rig.principal, rig.specimen.id)


ANSWERS: dict = {}


def answer_of(blanks=(), **changes):
    """The second opinion's answer that agrees with every value the record settles and leaves blank what it
    leaves blank; `changes` replace entries."""
    if blanks not in ANSWERS:
        with tempfile.TemporaryDirectory() as folder:
            run = to_end(rig_of(Path(folder), blanks)).run
        values = {key: so.shown(value) for key, value in run.fields.items() if value.state == ValueState.SUPPORTED}
        ANSWERS[blanks] = {key: {"value": values.get(key), "evidence": "L1: synthetic" if values.get(key) else ""}
            for key in so.FIELDS}
    return {**ANSWERS[blanks], **changes}


def finalized(run, *, rules=True, stale=None):
    """A copy of the run finalized again (step.refinalize), with the two rules or without them; `stale`
    replaces its open reasons first, as an earlier finalize might have left them."""
    copy = run.model_copy(deep=True)
    if stale is not None:
        copy.open_reasons = list(stale)
    with pytest.MonkeyPatch.context() as patch:
        if not rules:
            patch.setattr(so, "unflagged", lambda run, reasons, **kwargs: list(reasons), raising=False)
        field_step.refinalize(copy, today=TODAY)
    return copy


def rest(run):
    """Everything of the record but its open reasons."""
    return (run.stage, run.disposition, run.blocker, list(run.reasons), run.pending_review, run.human_approved,
        {key: value.model_dump(mode="json") for key, value in run.fields.items()},
        [finding.model_dump(mode="json") for finding in run.findings], len(run.evidence), run.second_opinion)


def lifted(run):
    """The open reasons the rules remove from the record as it is: the record is the same with them and
    without (`rest`), and its open reasons are the others' in their order."""
    on, off = finalized(run), finalized(run, rules=False)
    assert rest(on) == rest(off)
    gone = set(off.open_reasons) - set(on.open_reasons)
    assert on.open_reasons == [code for code in off.open_reasons if code not in gone]
    return gone


def flagged(run):
    """The fields the server and the app flag (review_summary.attention_fields)."""
    fields = project_fields({key: value.model_dump(mode="json") for key, value in run.fields.items()})
    return attention_fields(fields, [*run.reasons, *run.open_reasons])


def codes(code, keys):
    return {f"{code}:{key}" for key in keys}


def values_of(run):
    """The fields rule A lifts on the rig's record: settled, judged, not a date."""
    return {key for key in so.JUDGED if so._settled(run.fields.get(key))} - so.DATES


def blank_codes(keys=AGREED_BLANKS):
    return codes(UNRESOLVED, keys) | codes(LABEL_UNSETTLED, keys)


def store_obtained(run, answer, at=AHEAD):
    """The stored result an obtained answer leaves (second_opinion.obtain's comparison, record)."""
    record = so.read_answer(answer)
    fields = {key: {"compared": so.shown(run.fields[key]), "value": record[key].value,
        "evidence": record[key].evidence, "verdict": so.AGREES_VERDICT if so.same(key, so.shown(run.fields[key]),
            record[key].value) else so.DIFFERS_VERDICT} for key in so.JUDGED if so._settled(run.fields.get(key))}
    labels = {str(number): region.id for number, region in enumerate(
        sorted(run.regions, key=lambda r: (r.order, r.id)), start=1)}
    so.record(run, so.Result(so.OBTAINED, fields=fields, answer=so.bounded_answer(record), labels=labels),
        attempt=1, at=at.isoformat())


# ---- rule A: an agreed value -------------------------------------------------------------------------------

def test_an_agreed_value_flagged_only_by_its_labels_doubt_carries_no_flag(tmp_path):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of()))).run
    label = run.regions[0].id
    values = values_of(run)
    assert (run.disposition, run.reasons, run.second_opinion["status"]) == (Disposition.CLEARED, [], so.OBTAINED)
    assert {"country", "habitat", "precise_location", "taxon", "elevation_from_m"} <= values
    assert lifted(run) == codes(LABEL_UNSETTLED, values)
    assert values <= flagged(finalized(run, rules=False)) and not values & flagged(run)
    # The label's own doubt, the catalogue number's code, the dates' and an open field's stay.
    assert {f"unresolved_transcription:{label}", f"{LABEL_UNSETTLED}:{CATALOGUE}",
        f"{LABEL_UNSETTLED}:collectors", f"{UNRESOLVED}:collectors"} <= set(run.open_reasons)
    assert codes(LABEL_UNSETTLED, so.DATES) <= set(run.open_reasons) and so.DATES <= flagged(run)


def test_an_agreed_value_another_rule_marks_keeps_its_mark_and_its_flag(tmp_path):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of()))).run
    mark = field_step.marked_code("habitat", run.regions[0].id, "text_only")
    run.findings.append(RunFinding(rule_id=field_step.SETTLEMENT, rule_version=field_step.SETTLEMENT_RULES,
        severity="warning", field_key="habitat", reason_code=mark))
    field_step.refinalize(run, today=TODAY)
    assert lifted(run) == codes(LABEL_UNSETTLED, values_of(run))
    assert mark in run.open_reasons and "habitat" in flagged(run) and "country" not in flagged(run)
    assert [finding.reason_code for finding in run.findings if finding.field_key == "habitat"][-1] == mark


def test_a_value_the_second_opinion_differs_on_keeps_every_flag(tmp_path):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=MEADOW)))).run
    differs = field_step.marked_code("habitat", run.regions[0].id, so.DIFFERS)
    assert lifted(run) == codes(LABEL_UNSETTLED, values_of(run) - {"habitat"})
    assert {differs, f"{LABEL_UNSETTLED}:habitat"} <= set(run.open_reasons) and "habitat" in flagged(run)


@pytest.mark.parametrize("case", ["no-verdict", "changed-since"])
def test_a_value_left_unjudged_brings_every_flag_back_until_it_is_judged(tmp_path, case):
    """The step is due again (second_opinion.due): neither rule applies to the record until it has run."""
    run = to_end(rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))).run
    assert lifted(run) == codes(LABEL_UNSETTLED, values_of(run)) | blank_codes()
    if case == "no-verdict":
        del run.second_opinion["fields"]["precise_location"]
    else:
        value = run.fields["precise_location"]
        value.literal = value.parsed = value.normalized = "Changed"
    field_step.refinalize(run, today=TODAY)
    assert so.due(run) and lifted(run) == set()
    assert field_step.marked_code("precise_location", run.regions[0].id, so.NOT_CHECKED) in run.open_reasons
    assert blank_codes() | codes(LABEL_UNSETTLED, values_of(run)) <= set(run.open_reasons)


def test_a_value_changed_under_another_rules_mark_keeps_its_own_flag_only(tmp_path):
    """Not due (the second opinion answers for no marked field), so the others stay lifted; the changed
    value's verdict is not for its current value."""
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of()))).run
    run.findings.append(RunFinding(rule_id=field_step.SETTLEMENT, rule_version=field_step.SETTLEMENT_RULES,
        severity="warning", field_key="habitat",
        reason_code=field_step.marked_code("habitat", run.regions[0].id, "text_only")))
    value = run.fields["habitat"]
    value.literal = value.parsed = value.normalized = "Changed"
    field_step.refinalize(run, today=TODAY)
    assert not so.due(run) and lifted(run) == codes(LABEL_UNSETTLED, values_of(run) - {"habitat"})
    assert f"{LABEL_UNSETTLED}:habitat" in run.open_reasons


# ---- rule B: an agreed blank -------------------------------------------------------------------------------

def test_a_blank_field_the_second_opinion_also_leaves_blank_carries_no_flag(tmp_path):
    run = to_end(rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))).run
    off = finalized(run, rules=False)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert all(run.fields[key].state == ValueState.NOT_PRESENT for key in BLANKS)
    assert blank_codes(BLANKS) <= set(off.open_reasons) and set(BLANKS) <= flagged(off)
    assert lifted(run) == blank_codes() | codes(LABEL_UNSETTLED, values_of(run))
    assert not flagged(run) & (AGREED_BLANKS - {"taxon"})
    # The taxon's own doubt is another code: it stays, and the taxon stays flagged.
    assert "taxonomy_unresolved" in run.open_reasons and "taxon" in flagged(run)
    # Verbatim D/T/S is the rule's exception; a field left open is not blank.
    assert blank_codes({"verbatim_dts"}) <= set(run.open_reasons) and "verbatim_dts" in flagged(run)
    assert run.fields["city"].state == ValueState.UNRESOLVED and f"{UNRESOLVED}:city" in run.open_reasons


@pytest.mark.parametrize("entry", [MEADOW, {"value": None, "evidence": "UNSURE: faint letters"}],
    ids=["a-value", "unsure"])
def test_a_blank_field_the_second_opinion_reads_a_value_or_is_unsure_on_keeps_its_flags(tmp_path, entry):
    """A blank where the second opinion reads a value is a missed-value signal (68 of 68 in lane H1's table)."""
    run = to_end(rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS, habitat=entry)))).run
    assert lifted(run) == blank_codes(AGREED_BLANKS - {"habitat"}) | codes(LABEL_UNSETTLED, values_of(run))
    assert blank_codes({"habitat"}) <= set(run.open_reasons) and "habitat" in flagged(run)


def a_persons_transcript(run):
    run.transcripts[0].actor = "reviewer@example.org"


def other_labels(run):
    run.second_opinion["labels"] = {"1": "a-label-the-run-no-longer-has"}


def no_labels_kept(run):
    del run.second_opinion["labels"]


def a_new_reading(run):
    first = run.observations[0]
    run.observations.append(first.model_copy(update={"id": "a-later-reading",
        "created_at": (AHEAD + timedelta(days=1)).isoformat()}))


def a_time_that_does_not_read(run):
    run.second_opinion["at"] = "replay"


def a_time_with_no_offset(run):
    run.second_opinion["at"] = "2031-01-01T00:00:00"


@pytest.mark.parametrize("change", [a_persons_transcript, other_labels, no_labels_kept, a_new_reading,
    a_time_that_does_not_read, a_time_with_no_offset], ids=lambda change: change.__name__)
def test_an_answer_that_is_not_current_lifts_no_blanks_flag(tmp_path, change):
    """second_opinion.answer_current: the labels it was asked on are the run's, no transcript is a person's,
    no reading is newer than the request; what it cannot establish is not current."""
    run = to_end(rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))).run
    assert so.answer_current(run) and blank_codes() <= lifted(run)
    change(run)
    field_step.refinalize(run, today=TODAY)
    assert not so.answer_current(run) and not lifted(run) & blank_codes()
    assert blank_codes() <= set(run.open_reasons) and AGREED_BLANKS <= flagged(run)


def test_a_step_that_ran_before_the_readings_clock_lifts_no_blanks_flag(tmp_path):
    """The rig's own clock is before the readings' wall-clock time: rule B decides nothing, rule A is as it is."""
    rig = rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))
    rig.clock.now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    run = to_end(rig).run
    assert not so.answer_current(run) and lifted(run) == codes(LABEL_UNSETTLED, values_of(run))


# ---- where neither rule applies ------------------------------------------------------------------------------

def not_obtained(case, folder, monkeypatch):
    from pydantic_ai.exceptions import ModelHTTPError

    opinions = {"402": Opinion(error=ModelHTTPError(402, "second-opinion", body="credit")),
        "error": Opinion(error=RuntimeError("provider_request_failed")), "malformed": Opinion(raw="{not json"),
        "switched-off": None}
    rig = rig_of(folder, BLANKS, opinion=opinions.get(case, Opinion(answer_of(BLANKS))))
    if case == "budget":
        monkeypatch.setattr(so, "CAP_MICROS", 5_000_000)
    elif case == "unconfigured":
        monkeypatch.setattr(so, "route_price", lambda run: None)
    elif case == "exception":
        monkeypatch.setattr(so, "obtain", lambda run, **kwargs: (_ for _ in ()).throw(ValueError("boom")))
    elif case == "attempts-used":
        pending = rig.workflow.step(rig.principal, rig.specimen.id)
        pending.run.attempts[so.STEP] = pending.run.profile.execution.max_attempts
        rig.repository.save(rig.principal, pending, pending.version, "attempts", "attempts")
    return to_end(rig).run


CAUSES = {"switched-off": so.SWITCHED_OFF, "402": so.NOT_OBTAINED, "error": so.NOT_OBTAINED,
    "malformed": so.NOT_OBTAINED, "budget": so.NOT_OBTAINED, "unconfigured": so.NOT_OBTAINED,
    "exception": so.NOT_OBTAINED, "attempts-used": so.NOT_OBTAINED}


@pytest.mark.parametrize("case", list(CAUSES))
def test_not_obtained_or_switched_off_no_flag_is_lifted_and_an_obtained_result_lifts_them(tmp_path, monkeypatch,
        case):
    run = not_obtained(case, tmp_path, monkeypatch)
    assert run.second_opinion["status"] == CAUSES[case] and run.disposition == Disposition.CLEARED
    assert lifted(run) == set() and blank_codes() <= set(run.open_reasons)
    # Derived from the stored result alone: the same record with an obtained, agreeing result.
    store_obtained(run, answer_of(BLANKS))
    field_step.refinalize(run, today=TODAY)
    assert lifted(run) == blank_codes() | codes(LABEL_UNSETTLED, values_of(run))


def test_an_open_intent_ends_first_and_no_flag_is_lifted(tmp_path):
    run = to_end(rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))).run
    assert lifted(run)
    so.record(run, so.Result(so.ASKING), attempt=2, at=AHEAD.isoformat())
    field_step.refinalize(run, today=TODAY)
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, "abandoned")
    assert lifted(run) == set() and blank_codes() <= set(run.open_reasons)


def test_a_run_on_the_profile_with_every_field_mandatory_is_unchanged_and_still_held(tmp_path):
    every = field_mechanics_profile()
    run = to_end(rig_of(tmp_path / "every", BLANKS, opinion=Opinion(answer_of(BLANKS)), profile=every)).run
    off = finalized(run, rules=False)
    assert run.second_opinion["status"] == so.OBTAINED and so.answer_current(run) and not so.due(run)
    assert run.disposition == Disposition.REVIEW and (run.reasons, run.open_reasons) == (off.reasons,
        off.open_reasons)
    assert {f"{UNRESOLVED}:{key}" for key in BLANKS} <= set(run.reasons)
    readings = field_step.run_readings(run)
    assert so.agreed(run, readings, mandatory=every.mandatory_fields) == (frozenset(), frozenset())
    doubts = sorted(blank_codes() | codes(LABEL_UNSETTLED, values_of(run)))
    assert so.unflagged(run, doubts, mandatory=every.mandatory_fields) == doubts
    # The same stored state under the published profile's mandatory set: the rules read the run's own profile.
    assert so.unflagged(run, doubts, mandatory=published().mandatory_fields) == []


def test_the_catalogue_number_is_never_affected(tmp_path):
    """Not judged, so never agreed: its codes stay with no mandatory set at all, and a record it holds is held."""
    run = to_end(rig_of(tmp_path / "settled", opinion=Opinion(answer_of()))).run
    own = [f"{LABEL_UNSETTLED}:{CATALOGUE}", f"{UNRESOLVED}:{CATALOGUE}", f"{UNRESOLVED}:identified_by_irn"]
    assert so.unflagged(run, own, mandatory=()) == own and f"{LABEL_UNSETTLED}:{CATALOGUE}" in run.open_reasons
    blank = dict.fromkeys(BLANKS)
    lacking = rig_of(tmp_path / "lacking", (*blank, CATALOGUE), opinion=Opinion(answer_of(BLANKS)))
    held = to_end(lacking).run
    assert held.disposition == Disposition.REVIEW and f"{UNRESOLVED}:{CATALOGUE}" in held.reasons
    assert finalized(held, rules=False).reasons == held.reasons


# ---- a person's field, an approved run; derived, never stale -------------------------------------------------

def fresh(run):
    """The record equals a fresh finalize of the same state, whatever open reasons an earlier one left."""
    stale = finalized(run, rules=False).open_reasons
    for earlier in ([], stale, list(reversed(stale))):
        again = finalized(run, stale=earlier)
        assert (again.disposition, again.reasons, again.open_reasons) == (run.disposition, run.reasons,
            run.open_reasons)
    return True


def resumed(rig):
    """A completed run reaching the handover again (Retry, Resume: the recheck), taken to its end."""
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    specimen.run.stage, specimen.run.disposition = "plan", None
    rig.repository.save(rig.principal, specimen, specimen.version, "resume", "resume")
    return to_end(rig).run


def confirm(client, rig, key, name):
    """A person confirms the field as it stands, through the decisions route."""
    value = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields[key]
    return decide(client, rig, name, "field", target_id=key,
        after=value.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(value.evidence_ids))


def test_retry_and_resume_give_the_same_reasons_and_ask_nothing_again(tmp_path):
    opinion = Opinion(answer_of(BLANKS))
    rig = rig_of(tmp_path, BLANKS, opinion=opinion)
    first = to_end(rig).run
    expected = blank_codes() | codes(LABEL_UNSETTLED, values_of(first))
    assert lifted(first) == expected and fresh(first)
    for _ in range(2):
        again = resumed(rig)
        assert (again.disposition, again.reasons, again.open_reasons) == (first.disposition, first.reasons,
            first.open_reasons)
        assert lifted(again) == expected and fresh(again) and len(opinion.requests) == 1


def test_a_persons_field_keeps_its_flag_and_an_approved_run_is_as_without_the_rules(tmp_path):
    """After the step: the person's field is the person's (second_opinion.authority), the record waits for
    their approval, the other fields stay lifted. Approved: the second opinion contributes nothing."""
    rig = rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))
    first = to_end(rig).run
    client = review_client(rig)
    decided = confirm(client, rig, "precise_location", "field-precise-location")
    assert decided.person_decided_fields == ["precise_location"]
    assert (decided.disposition, decided.reasons) == (Disposition.REVIEW, [APPROVAL])
    assert f"{LABEL_UNSETTLED}:precise_location" in decided.open_reasons and fresh(decided)
    assert lifted(decided) == blank_codes() | codes(LABEL_UNSETTLED, values_of(first) - {"precise_location"})
    again = resumed(rig)
    assert (again.reasons, again.open_reasons) == (decided.reasons, decided.open_reasons)
    approved = decide(client, rig, "approve", "approve")
    assert approved.human_approved and (approved.disposition, approved.reasons) == (Disposition.CLEARED, [])
    assert lifted(approved) == set() and fresh(approved)
    assert blank_codes() | codes(LABEL_UNSETTLED, values_of(first)) <= set(approved.open_reasons)


def test_a_field_a_person_decided_before_the_step_is_never_lifted(tmp_path):
    rig = rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))
    waiting = rig.workflow.step(rig.principal, rig.specimen.id)
    assert waiting.run.stage == so.STEP
    for key in ("precise_location", "habitat"):
        so.decided(waiting.run, key)
    rig.repository.save(rig.principal, waiting, waiting.version, "decided", "decided")
    run = to_end(rig).run
    assert run.second_opinion["status"] == so.OBTAINED and fresh(run)
    assert lifted(run) == blank_codes(AGREED_BLANKS - {"habitat"}) | codes(LABEL_UNSETTLED,
        values_of(run) - {"precise_location"})
    assert {f"{LABEL_UNSETTLED}:precise_location", *blank_codes({"habitat"})} <= set(run.open_reasons)


def test_a_decision_during_the_step_abandons_it_and_no_flag_is_lifted(tmp_path, monkeypatch):
    rig = rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))
    client = review_client(rig)
    rig.workflow.step(rig.principal, rig.specimen.id)
    real, seen = so.obtain, {}

    def decide_meanwhile(run, **kwargs):
        seen["decided"] = confirm(client, rig, "precise_location", "precise-location-meanwhile")
        return real(run, **kwargs)

    monkeypatch.setattr(so, "obtain", decide_meanwhile)
    rig.workflow.step(rig.principal, rig.specimen.id)
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert run == seen["decided"] and run.second_opinion["status"] == so.NOT_OBTAINED
    assert lifted(run) == set() and fresh(run) and blank_codes() <= set(run.open_reasons)
    # Derived from the stored result alone: once one is obtained, all but the person's field are lifted.
    store_obtained(run, answer_of(BLANKS))
    field_step.refinalize(run, today=TODAY)
    assert lifted(run) == blank_codes() | codes(LABEL_UNSETTLED, values_of(run) - {"precise_location"})


def test_a_history_restore_gives_the_restored_states_own_reasons(tmp_path):
    from specimen_digitization.application.history_restore import restored_specimen

    rig = rig_of(tmp_path, BLANKS, opinion=Opinion(answer_of(BLANKS)))
    revision = to_end(rig)
    confirm(review_client(rig), rig, "precise_location", "field-precise-location")
    base = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert f"{LABEL_UNSETTLED}:precise_location" in base.run.open_reasons
    restored = restored_specimen(base, rig.repository.version(rig.principal.scope, rig.specimen.id, revision.version))
    run = restored.run
    assert run.person_decided_fields == [] and run.second_opinion == revision.run.second_opinion
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [HISTORY_RESTORED])
    assert run.open_reasons == revision.run.open_reasons and fresh(run)
    assert lifted(run) == blank_codes() | codes(LABEL_UNSETTLED, values_of(run))
