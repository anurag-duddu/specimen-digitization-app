"""Lane H3 (docs/execution/autonomy/PLAN.md): a blank field for which the second opinion gives a value is flagged.

The coordinator's ruling of 2026-11-21 on lane H2's measurement over the 99 cleared records of the 100 truth
slides (an engineering fix, not the owner's words): a field research left without a value, for which the second
opinion's own answer gives one, gains an open reason naming it, `marked:<field>::second_opinion_differs`
(second_opinion.filled, called by step.finalize_fields on every finalize). Only a flag: the value stays blank, no
record is held, `cleared_by` and the disposition do not change. PR #455 had scoped the second opinion's marks to a
field settled with a value; PR #457 called such a blank "a missed-value signal" but kept only the flags it already
had, and a blank step.mark_not_on_label marks "Not on the label" has none.

The rig is test_step's (one label, two agreeing readers, the real workflow and its second opinion step, a scripted
field expert) with its coverage confirmed by the segment step's real check, so every label is read whole and the
habitat its expert finds lacking is marked "Not on the label" (step.mark_not_on_label), as on the 58 host labels H2
counted. Each test compares the record with the same record finalized with the rule turned off (`off`): everything
but the open reasons is identical, and the open reasons differ by exactly the code the test names.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import test_step as rig_module
from test_second_opinion import Opinion
from test_step import LABEL, TEXT, TODAY, Scripted, answering, build_rig, decide, field_mechanics_profile, mounted, \
    review_client

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, ValueState
from specimen_digitization.application.label_coverage import check_run
from specimen_digitization.application.lane import cleared_by
from specimen_digitization.application.review_summary import attention_fields, project_fields
from specimen_digitization.application.standing_holds import APPROVAL, HISTORY_RESTORED
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
# The step's clock, after the readings' (Observation.created_at is the wall clock; the rig's clock is fixed).
AHEAD = datetime(2031, 1, 1, tzinfo=timezone.utc)
NO_HABITAT = TEXT.replace(f"habitat: {LABEL['habitat']}\n", "")
LACKS = answering(FieldAnswer(outcome="label_lacks_value", explanation="No reading writes a habitat."))
HOST = {"value": "Ex. Cynomys", "evidence": "L1: Ex. Cynomys"}
MARK = "marked:habitat::second_opinion_differs"


def published():
    return published_registry().profiles[0]


@pytest.fixture
def whole(monkeypatch):
    """The rig's specimen with its segmentation evidence and coverage checked by the segment step's check
    (label_coverage.check_run, the published rule): one label, confirmed, so step._whole_label_read holds."""
    original = rig_module.make_specimen

    def make(blobs, text=TEXT, other=None, *, profile=None):
        specimen = original(blobs, text, other, profile=profile)
        run = specimen.run
        segmentation = {"cross_check": {"concept": "text", "detections": []}}
        raw = json.dumps(segmentation, sort_keys=True).encode()
        segmentation.update(input_sha256=specimen.asset.sha256, blob_ref=blobs.put(raw),
            sha256=hashlib.sha256(raw).hexdigest())
        run.segmentation = segmentation
        run.classification_selection = {"collection_id": "insects", "actor_id": "reviewer-1",
            "reason": "Intake selection"}
        run.coverage_confirmed = False
        check_run(specimen)
        return specimen

    monkeypatch.setattr(sys.modules[rig_module.__name__], "make_specimen", make)


def rig_of(folder, *, opinion=None, profile=None, lacking=("habitat",)):
    """The rig's record with no habitat written; the fields in `lacking` answered label_lacks_value; `opinion`
    answers the second opinion's step (None: switched off)."""
    rig = build_rig(folder, NO_HABITAT, profile=profile or published())
    mounted(rig, Scripted({key: LACKS for key in lacking}))
    rig.workflow.second_opinion = None if opinion is None else so.SecondOpinionStep(model_factory=opinion.factory)
    rig.clock.now = AHEAD
    return rig


def to_end(rig):
    return rig.workflow.drain(rig.principal, rig.specimen.id)


ANSWERS: dict = {}


def answer_of(lacking=("habitat",), **changes):
    """The second opinion's answer that agrees with every value the record settles and leaves blank what it
    leaves blank; `changes` replace entries."""
    if lacking not in ANSWERS:
        with tempfile.TemporaryDirectory() as folder:
            run = to_end(rig_of(Path(folder), lacking=lacking)).run
        values = {key: so.shown(value) for key, value in run.fields.items() if value.state == ValueState.SUPPORTED}
        ANSWERS[lacking] = {key: {"value": values.get(key), "evidence": "L1: synthetic" if values.get(key) else ""}
            for key in so.FIELDS}
    return {**ANSWERS[lacking], **changes}


def finalized(run, *, rule=True, stale=None):
    """A copy of the run finalized again (step.refinalize), with the rule or without it; `stale` replaces its
    open reasons first, as an earlier finalize might have left them."""
    copy = run.model_copy(deep=True)
    if stale is not None:
        copy.open_reasons = list(stale)
    with pytest.MonkeyPatch.context() as patch:
        if not rule:
            patch.setattr(so, "filled", lambda run, reasons, **kwargs: [], raising=False)
        field_step.refinalize(copy, today=TODAY)
    return copy


def rest(run):
    """Everything of the record but its open reasons."""
    return (run.stage, run.disposition, run.blocker, list(run.reasons), run.pending_review, run.human_approved,
        {key: value.model_dump(mode="json") for key, value in run.fields.items()},
        [finding.model_dump(mode="json") for finding in run.findings], len(run.evidence), run.second_opinion)


def added(run):
    """The open reasons the rule adds to the record as it is: the record is the same with it and without
    (`rest`), and its open reasons are the others' in their order, then the added ones."""
    on, off = finalized(run), finalized(run, rule=False)
    assert rest(on) == rest(off)
    new = [code for code in on.open_reasons if code not in off.open_reasons]
    assert on.open_reasons == [*off.open_reasons, *new]
    return new


def flagged(run):
    """The fields the server and the app flag (review_summary.attention_fields)."""
    fields = project_fields({key: value.model_dump(mode="json") for key, value in run.fields.items()})
    return attention_fields(fields, [*run.reasons, *run.open_reasons])


def fresh(run):
    """The record equals a fresh finalize of the same state, whatever open reasons an earlier one left."""
    stale = finalized(run, rule=False).open_reasons
    for earlier in ([], stale, [*stale, MARK, MARK], list(reversed([*stale, MARK]))):
        again = finalized(run, stale=earlier)
        assert (again.disposition, again.reasons, again.open_reasons) == (run.disposition, run.reasons,
            run.open_reasons)
    return True


def blank_not_on_label(run, key="habitat"):
    value = run.fields[key]
    return (value.state == ValueState.NOT_PRESENT and so.shown(value) is None
        and value.reason.startswith(field_step.NOT_ON_LABEL_REASON.split(":")[0] + ":"))


# ---- the rule --------------------------------------------------------------------------------------------

def test_a_blank_the_second_opinion_gives_a_value_for_is_flagged_and_nothing_else_changes(tmp_path, whole):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))).run
    off = finalized(run, rule=False)
    # Research's blank: "Not on the label", no flag without the rule (the 58 host labels' case).
    assert blank_not_on_label(run) and "habitat" not in flagged(off)
    assert (run.second_opinion["status"], so.answer_current(run), so.due(run)) == (so.OBTAINED, True, False)
    # The rule: one open reason naming the field, and the app flags it.
    assert added(run) == [MARK] and MARK in run.open_reasons and "habitat" in flagged(run)
    assert flagged(run) - flagged(off) == {"habitat"}
    # Only a flag: the value stays blank, nothing holds, the record is cleared by the system as before.
    assert (run.disposition, run.reasons) == (off.disposition, off.reasons) == (Disposition.CLEARED, [])
    assert cleared_by(run.disposition, run.human_approved) == cleared_by(off.disposition, off.human_approved)
    assert blank_not_on_label(run) and run.fields["habitat"] == off.fields["habitat"]
    # An optional field's doubt, read by split_reasons as the habitat's, never as a hold.
    assert field_step.split_reasons(run, [MARK], mandatory=published().mandatory_fields) == ([], [MARK])
    assert so.own(MARK) and fresh(run)


@pytest.mark.parametrize("entry", [{"value": None, "evidence": ""}, {"value": "  ", "evidence": "L1: "},
    {"value": None, "evidence": "UNSURE: faint letters"}], ids=["blank", "white-space", "unsure"])
def test_a_blank_the_second_opinion_gives_no_value_for_is_not_flagged(tmp_path, whole, entry):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=entry)))).run
    assert blank_not_on_label(run) and added(run) == [] and "habitat" not in flagged(run)


def test_a_field_already_flagged_is_not_flagged_twice(tmp_path, whole):
    """The taxon left blank keeps its own doubts (taxonomy_unresolved, mandatory_unresolved:taxon): no mark is
    added for it, though the second opinion gives it a value; the habitat, not flagged, gets its mark."""
    lacking = ("habitat", "taxon")
    answer = answer_of(lacking, habitat=HOST, taxon={"value": "Ctenophthalmus", "evidence": "L1: Ctenophthalmus"})
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer), lacking=lacking)).run
    assert run.fields["taxon"].state != ValueState.SUPPORTED and "taxon" in flagged(finalized(run, rule=False))
    assert added(run) == [MARK] and not [code for code in run.open_reasons if code.startswith("marked:taxon:")]


def test_a_value_the_second_opinion_differs_on_keeps_its_one_mark(tmp_path, whole):
    """A settled value is the derived marks' (second_opinion.derived): the rule adds nothing for it."""
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST, county={"value": "Lake", "evidence": ""}))))
    run = run.run
    county = [code for code in run.open_reasons if code.startswith("marked:county:")]
    assert county == [field_step.marked_code("county", run.regions[0].id, so.DIFFERS)] and added(run) == [MARK]


def test_a_field_the_profile_makes_mandatory_is_never_marked_by_the_rule(tmp_path, whole):
    """No hold: on the profile with every field mandatory the record is exactly as without the rule."""
    every = field_mechanics_profile()
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)), profile=every)).run
    off = finalized(run, rule=False)
    assert run.second_opinion["status"] == so.OBTAINED and not so.due(run)
    assert (run.disposition, run.reasons, run.open_reasons) == (off.disposition, off.reasons, off.open_reasons)
    assert MARK not in run.reasons + run.open_reasons
    assert so.filled(run, [], mandatory=every.mandatory_fields) == []
    # The same stored state under the published profile's mandatory set: the rule reads the run's own profile.
    assert so.filled(run, [], mandatory=published().mandatory_fields) == [MARK]


def test_the_catalogue_number_and_the_irn_are_never_marked_by_the_rule(tmp_path, whole):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(identified_by_irn={"value": "123", "evidence": ""})))).run
    assert run.fields["identified_by_irn"].state != ValueState.SUPPORTED and added(run) == []
    assert so.EXCLUDED == {"fmnh_ins_number", "identified_by_irn"}


# ---- where the rule gives nothing ----------------------------------------------------------------------------

def test_a_run_off_the_units_path_gets_no_mark(tmp_path, whole):
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))).run
    assert so.filled(run, []) == [MARK]
    run.first_pass_path = "old"
    assert so.filled(run, []) == []


def a_persons_transcript(run):
    run.transcripts[0].actor = "reviewer@example.org"


def other_labels(run):
    run.second_opinion["labels"] = {"1": "a-label-the-run-no-longer-has"}


def a_new_reading(run):
    first = run.observations[0]
    run.observations.append(first.model_copy(update={"id": "a-later-reading",
        "created_at": (AHEAD + timedelta(days=1)).isoformat()}))


def a_value_left_unjudged(run):
    del run.second_opinion["fields"]["precise_location"]


@pytest.mark.parametrize("change", [a_persons_transcript, other_labels, a_new_reading, a_value_left_unjudged],
    ids=lambda change: change.__name__)
def test_an_answer_not_current_or_a_step_due_gives_no_mark(tmp_path, whole, change):
    """second_opinion.answer_current (asked on the run's labels and readings as they are now) and due (a value
    the step answers for has no verdict for its current value: the step will run again)."""
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))).run
    assert added(run) == [MARK]
    change(run)
    field_step.refinalize(run, today=TODAY)
    assert not so.answer_current(run) or so.due(run)
    assert MARK not in run.open_reasons and added(run) == []


def test_switched_off_or_not_obtained_gives_no_mark_and_an_obtained_result_gives_it(tmp_path, whole):
    from test_agreed_no_flag import store_obtained

    for name, opinion in (("off", None), ("error", Opinion(error=RuntimeError("provider_request_failed")))):
        run = to_end(rig_of(tmp_path / name, opinion=opinion)).run
        assert run.second_opinion["status"] == (so.SWITCHED_OFF if opinion is None else so.NOT_OBTAINED)
        assert added(run) == [] and run.disposition == Disposition.CLEARED and fresh(run)
        # Derived from the stored result alone: the same record with an obtained answer that gives a value.
        store_obtained(run, answer_of(habitat=HOST), at=AHEAD)
        field_step.refinalize(run, today=TODAY)
        assert added(run) == [MARK] and run.disposition == Disposition.CLEARED


def test_a_not_obtained_result_after_an_obtained_one_gives_no_mark(tmp_path, whole):
    """record keeps an earlier answer beside a later not-obtained status; the rule reads only an obtained one."""
    run = to_end(rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))).run
    so.record(run, so.Result(so.NOT_OBTAINED, reason="provider_error"), attempt=2, at=AHEAD.isoformat())
    assert run.second_opinion["answer"]["habitat"] == HOST
    field_step.refinalize(run, today=TODAY)
    assert MARK not in run.open_reasons and added(run) == []


# ---- a person's field, an approval; derived, never stale -----------------------------------------------------

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


def test_retry_and_resume_give_the_same_reasons_and_ask_nothing_again(tmp_path, whole):
    opinion = Opinion(answer_of(habitat=HOST))
    rig = rig_of(tmp_path, opinion=opinion)
    first = to_end(rig).run
    assert added(first) == [MARK] and fresh(first)
    for _ in range(2):
        again = resumed(rig)
        assert (again.disposition, again.reasons, again.open_reasons) == (first.disposition, first.reasons,
            first.open_reasons)
        assert added(again) == [MARK] and fresh(again) and len(opinion.requests) == 1


def test_a_person_deciding_the_field_takes_its_mark_and_an_approval_takes_every_mark(tmp_path, whole):
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    to_end(rig)
    client = review_client(rig)
    other = confirm(client, rig, "precise_location", "field-precise-location")
    # A decision on another field: the record waits for approval, the habitat keeps its mark.
    assert (other.disposition, other.reasons) == (Disposition.REVIEW, [APPROVAL])
    assert added(other) == [MARK] and fresh(other)
    decided = confirm(client, rig, "habitat", "field-habitat")
    assert "habitat" in decided.person_decided_fields and "habitat" in so.authority(decided)
    assert MARK not in decided.open_reasons and added(decided) == [] and fresh(decided)
    approved = decide(client, rig, "approve", "approve")
    assert approved.human_approved and (approved.disposition, approved.reasons) == (Disposition.CLEARED, [])
    assert added(approved) == [] and fresh(approved)


def test_a_field_a_person_decided_before_the_step_is_never_marked(tmp_path, whole):
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    waiting = rig.workflow.step(rig.principal, rig.specimen.id)
    assert waiting.run.stage == so.STEP
    so.decided(waiting.run, "habitat")
    rig.repository.save(rig.principal, waiting, waiting.version, "decided", "decided")
    run = to_end(rig).run
    assert run.second_opinion["status"] == so.OBTAINED and MARK not in run.open_reasons and added(run) == []


def test_a_history_restore_gives_the_restored_states_own_reasons(tmp_path, whole):
    from specimen_digitization.application.history_restore import restored_specimen

    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    revision = to_end(rig)
    confirm(review_client(rig), rig, "habitat", "field-habitat")
    base = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert MARK not in base.run.open_reasons
    restored = restored_specimen(base, rig.repository.version(rig.principal.scope, rig.specimen.id, revision.version))
    run = restored.run
    assert run.person_decided_fields == [] and run.second_opinion == revision.run.second_opinion
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [HISTORY_RESTORED])
    assert run.open_reasons == revision.run.open_reasons and MARK in run.open_reasons and fresh(run)


# ---- the windows: saves with no finalize, origin/main's own mechanism ----------------------------------------
#
# The mark is derived at finalize, as every open reason is. The decisions endpoint finalizes only an approval, a
# capability deferral or a run whose stage is `finalized` when the decision arrives (api.py apply_decision);
# step.refinalize returns early on a blocked run; a history restore saves the restored snapshot's open reasons with no
# finalize (history_restore.restored_specimen). So after a restore, a transcript decision (stage `parse`), or a decision
# on a paused, cancelled or blocked run, the stored open reasons are an earlier finalize's until the next finalize,
# which recomputes them; on origin/main for every open reason alike. These tests pin each window through the real API
# and workflow; they do not change it (the coordinator's ruling of 2026-11-21). The windows here are examples found in
# the reviews of PR #463, not a complete list.

def queued(monkeypatch):
    """The API's queue as the worker's tests stand it in: the run is pending, and the rig's workflow takes it."""
    from datetime import datetime as clock

    from specimen_digitization.application import api as app_api

    def queue(specimen, registry, actor):
        specimen.run.stage, specimen.run.queued_at = "pending", clock.now(timezone.utc).isoformat()

    monkeypatch.setattr(app_api, "queue", queue)


def act(client, rig, action, key):
    """A run action (retry, resume) through the actions route."""
    from test_step import ORG

    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": key},
        json={"expected_revision": current.version, "action": action, "reason": "Again."})
    assert response.status_code == 200, response.text
    return to_end(rig).run


def restore(client, rig, revision, key):
    from test_step import ORG

    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/specimens/{current.id}/history:restore",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": key},
        json={"expected_revision": current.version, "base_record_version_id": f"{current.run.id}:{current.version}",
            "source_revision": revision, "reset_to_initial": False, "reason": "Back"})
    assert response.status_code == 200, response.text
    return rig.repository.get(rig.principal.scope, rig.specimen.id).run


def test_a_restore_to_an_approved_revision_saves_its_open_reasons_and_the_next_finalize_gives_the_mark(
        tmp_path, whole, monkeypatch):
    """The window is origin/main's mechanism: the restore copies the approved snapshot's open reasons (an approved run
    has no mark) and resets the approval, without a finalize; the record is held by history_restored_requires_review;
    the next finalize (Resume) gives the mark a fresh finalize gives."""
    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    assert MARK in to_end(rig).run.open_reasons
    client = review_client(rig)
    approved = decide(client, rig, "approve", "approve")
    assert approved.human_approved and MARK not in approved.open_reasons
    revision = rig.repository.get(rig.principal.scope, rig.specimen.id).version
    confirm(client, rig, "precise_location", "field-precise-location")
    run = restore(client, rig, revision, "restore")
    assert not run.human_approved and run.reasons == [HISTORY_RESTORED] and run.disposition == Disposition.REVIEW
    assert MARK not in run.open_reasons and MARK in finalized(run).open_reasons
    resumed_ = act(client, rig, "resume", "resume")
    assert MARK in resumed_.open_reasons and resumed_.reasons == [HISTORY_RESTORED] and fresh(resumed_)


def test_a_transcript_decision_keeps_the_mark_while_running_and_the_next_finalize_removes_it(
        tmp_path, whole, monkeypatch):
    """The window is origin/main's mechanism: a transcript decision through the endpoint sets the stage to parse and
    saves the earlier open reasons; the revision saved while the run is running still carries the mark; the worker's
    next finalize removes it (the answer is no longer current: a person's transcript), and Resume, Retry and the
    approval keep it gone."""
    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    first = to_end(rig).run
    assert MARK in first.open_reasons
    client = review_client(rig)
    running = decide(client, rig, "transcript", "transcription", target_id=first.regions[0].id,
        after={"text": NO_HABITAT, "state": "supported"})
    assert running.stage == "parse" and running.disposition is None and MARK in running.open_reasons
    mounted(rig, Scripted({"habitat": LACKS}))
    done = to_end(rig).run
    assert done.stage == "finalized" and not so.answer_current(done) and MARK not in done.open_reasons
    for action in ("resume", "retry"):
        again = act(client, rig, action, action)
        assert MARK not in again.open_reasons and fresh(again)
    approved = decide(client, rig, "approve", "approve")
    assert approved.human_approved and MARK not in approved.open_reasons


def test_a_decision_on_the_marked_field_while_a_blob_is_lost_keeps_the_mark_until_the_retry_after_repair(
        tmp_path, whole, monkeypatch):
    """The window is origin/main's mechanism: the decision's integrity check blocks the run (evidence_integrity_failure)
    and refinalize returns early on a blocked run, so the mark stays on the person's field; once the blob is back, the
    Retry's finalize takes it (the field is the person's)."""
    import shutil

    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    first = to_end(rig).run
    assert MARK in first.open_reasons
    client = review_client(rig)
    path = rig.blobs.root / first.observations[0].raw_ref
    hidden = tmp_path / "hidden-blob"
    shutil.move(path, hidden)
    blocked = confirm(client, rig, "habitat", "field-habitat")
    assert blocked.stage == "processing_blocked" and blocked.blocker == "evidence_integrity_failure"
    assert blocked.disposition is None
    assert "habitat" in blocked.person_decided_fields and MARK in blocked.open_reasons
    shutil.move(hidden, path)
    repaired = act(client, rig, "retry", "retry")
    assert repaired.stage == "finalized" and MARK not in repaired.open_reasons and fresh(repaired)


@pytest.mark.parametrize("action", ["pause", "cancel"])
def test_a_field_decision_on_a_paused_or_cancelled_run_keeps_the_mark_until_a_person_continues_the_run(
        tmp_path, whole, monkeypatch, action):
    """The window is origin/main's mechanism: the decisions endpoint finalizes only an approval or a run whose stage is
    finalized when the decision arrives, so a field decision on a paused or cancelled run saves the stored open reasons
    as they were (status paused or cancelled, disposition null); the worker does not advance such a run, so the
    window lasts until a person continues it. Resume (pause) or Retry (cancel) then finalizes, and the field is the
    person's: no mark."""
    from specimen_digitization.application.lane import run_status

    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    assert MARK in to_end(rig).run.open_reasons
    client = review_client(rig)
    stopped = act(client, rig, action, action)
    assert stopped.stage == ("paused" if action == "pause" else "cancelled") and stopped.disposition is None
    decided = confirm(client, rig, "habitat", "field-habitat")
    assert "habitat" in decided.person_decided_fields and MARK in decided.open_reasons
    assert decided.disposition is None and run_status(decided) == stopped.stage and decided.blocker is None
    # The worker leaves it as it is.
    assert MARK in to_end(rig).run.open_reasons
    continued = act(client, rig, "resume" if action == "pause" else "retry", "continue")
    assert continued.stage == "finalized" and MARK not in continued.open_reasons and fresh(continued)


def test_a_restore_to_an_approved_revision_then_approving_again_ends_the_window_with_no_mark(
        tmp_path, whole, monkeypatch):
    """The finalize after a restore recomputes the mark from the record as it then is: approving again finalizes an
    approved run, for which the second opinion derives nothing, so the stale window ends with no mark, as a fresh
    finalize gives."""
    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    assert MARK in to_end(rig).run.open_reasons
    client = review_client(rig)
    decide(client, rig, "approve", "approve")
    revision = rig.repository.get(rig.principal.scope, rig.specimen.id).version
    confirm(client, rig, "precise_location", "field-precise-location")
    restored = restore(client, rig, revision, "restore")
    assert restored.reasons == [HISTORY_RESTORED] and MARK not in restored.open_reasons
    again = decide(client, rig, "approve-again", "approve")
    assert again.human_approved and again.reasons == [] and MARK not in again.open_reasons
    assert again.open_reasons == finalized(again).open_reasons and fresh(again)


@pytest.mark.parametrize("action", ["retry", "resume"])
def test_a_field_decision_after_retry_or_resume_before_any_worker_step_keeps_the_mark_until_the_worker_finalizes(
        tmp_path, whole, monkeypatch, action):
    """The window is origin/main's mechanism: Retry or Resume on a completed record saves stage pending with no
    disposition; a field decision before any worker step is not finalized (the stage is not `finalized`), so the saved
    revision keeps the mark on the person's field; the worker's next finalize removes it (a person's field)."""
    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    assert MARK in to_end(rig).run.open_reasons
    client = review_client(rig)
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    from test_step import ORG

    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": action},
        json={"expected_revision": current.version, "action": action, "reason": "Again."})
    assert response.status_code == 200, response.text
    pending = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert pending.stage == "pending" and pending.disposition is None
    decided = confirm(client, rig, "habitat", "field-habitat")
    assert decided.stage == "pending" and decided.disposition is None
    assert "habitat" in decided.person_decided_fields and MARK in decided.open_reasons
    done = to_end(rig).run
    assert done.stage == "finalized" and MARK not in done.open_reasons and fresh(done)


def test_a_field_decision_after_a_transcript_decision_moves_the_run_to_lookup_and_keeps_the_mark_until_the_worker_finalizes(
        tmp_path, whole, monkeypatch):
    """The window is origin/main's mechanism: a transcript decision removes field research from the completed steps
    (api.py, the transcription branch), so a decision on the taxon that follows it sets the stage to `lookup` and is not
    finalized; the saved revision keeps the mark beside the stored second opinion. The worker's next finalize removes
    it (the answer is no longer current)."""
    queued(monkeypatch)
    rig = rig_of(tmp_path, opinion=Opinion(answer_of(habitat=HOST)))
    first = to_end(rig).run
    assert MARK in first.open_reasons
    client = review_client(rig)
    decide(client, rig, "transcript", "transcription", target_id=first.regions[0].id,
        after={"text": NO_HABITAT, "state": "supported"})
    taxon = confirm(client, rig, "taxon", "field-taxon")
    assert field_step.STEP not in taxon.completed_steps and taxon.stage == "lookup" and taxon.disposition is None
    assert taxon.second_opinion["status"] == so.OBTAINED and MARK in taxon.open_reasons
    mounted(rig, Scripted({"habitat": LACKS}))
    done = to_end(rig).run
    assert done.stage == "finalized" and MARK not in done.open_reasons
