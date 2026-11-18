"""The clearing rule (plan WP K1, PR #455) with the fields' second opinion (WP F1, PR #456), together.

Under the published profile only the catalogue number is mandatory (K1); the second opinion marks a settled
value it does not agree with (`marked:<field>:<label>:second_opinion_differs`) or did not check
(`..._not_checked`), and never judges the catalogue number (F1). Combined, a second opinion's mark is an
optional field's doubt: it is kept in `run.open_reasons` (the API's `open_reason_codes`), the field needs
attention, and the record clears on its catalogue number. What holds a record for another reason holds it with
the second opinion in any state.

The tests in test_second_opinion.py run on the profile with every field mandatory (test_step.field_mechanics_profile),
where every mark holds, as #456 alone does on main; these run on the published profile. Every record here is
built by the field research rig (test_step.build_rig) and taken through the workflow, with the second opinion's
step mounted as in production but for its model.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from test_second_opinion import Opinion, agreeing, full, step_paid
from test_skeletal_disposition import catalogue_number_lacking, readers_differ_on_the_collectors
from test_step import TODAY, Scripted, build_rig, decide, mounted, review_client

from specimen_digitization.application import active_graph
from specimen_digitization.application.api import summary
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import AuditEvent, Disposition, RunFinding
from specimen_digitization.application.review_summary import attention_fields, project_fields
from specimen_digitization.application.standing_holds import APPROVAL, HISTORY_RESTORED, person_acted
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
CATALOGUE = "fmnh_ins_number"
MEADOW = {"value": "Synthetic meadow", "evidence": "L1: meadow"}


def published():
    return published_registry().profiles[0]


def rig_on(folder, scenario=None, opinion=None, *, switched_off=False):
    """The rig's record on the published profile, with the second opinion's step mounted (its model answering
    as `opinion`), or switched off."""
    if scenario is None:
        rig, script = build_rig(folder, profile=published()), Scripted()
    else:
        text, other, candidates, script = scenario()
        rig = build_rig(folder, text, other, candidates=candidates, profile=published())
    mounted(rig, script)
    rig.workflow.second_opinion = None if switched_off else so.SecondOpinionStep(model_factory=opinion.factory)
    return rig


def to_end(rig):
    return rig.workflow.drain(rig.principal, rig.specimen.id)


def marks(codes, why=None):
    return sorted(code for code in codes if so.own(code) and (why is None or code.endswith(":" + why)))


def fields_of(codes):
    return {code.split(":")[1] for code in codes}


def settled_judged(run):
    """The fields the second opinion answers for on this run: settled, judged, no other rule's mark."""
    return {key for key in so.JUDGED if so._settled(run.fields.get(key))} - so._other_marks(run)


def resumed(rig):
    """A completed run reaching the handover again (Retry, Resume: the recheck), taken to its end."""
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    specimen.run.stage, specimen.run.disposition = "plan", None
    rig.repository.save(rig.principal, specimen, specimen.version, "resume", "resume")
    return to_end(rig)


# ---- 1. a second opinion's mark on an optional field is that field's doubt ----------------------------------

def test_the_second_opinion_never_judges_the_one_mandatory_field():
    assert published().mandatory_fields == (CATALOGUE,)
    assert CATALOGUE in so.EXCLUDED and not set(published().mandatory_fields) & set(so.JUDGED)


def test_every_second_opinion_mark_is_an_optional_fields_doubt(tmp_path):
    """step.split_reasons classifies both marks on every field the second opinion judges as an optional
    field's doubt; another rule's mark on the catalogue number still holds."""
    run = to_end(rig_on(tmp_path, opinion=Opinion(agreeing(tmp_path / "values")))).run
    label = run.regions[0].id
    codes = [field_step.marked_code(key, label, why) for key in so.JUDGED for why in (so.DIFFERS, so.NOT_CHECKED)]
    assert all(so.own(code) for code in codes)
    held, open_ = field_step.split_reasons(run, codes, mandatory=published().mandatory_fields)
    assert (held, open_) == ([], codes)
    catalogue = field_step.marked_code(CATALOGUE, label, "text_only")
    assert field_step.split_reasons(run, [catalogue, *codes], mandatory=published().mandatory_fields) == (
        [catalogue], codes)


def test_a_differing_and_an_unchecked_value_land_in_open_reasons_and_need_attention(tmp_path):
    """Both marks reach the record's open reasons, never its reasons, and the field needs attention on the
    server's view of the record (api.summary; the app reads `open_reason_codes` the same way:
    tests/fixtures/field_attention.json, second_opinion_test.dart)."""
    rig = rig_on(tmp_path, opinion=Opinion(agreeing(tmp_path / "values", habitat=MEADOW)))
    done = to_end(rig)
    run = done.run
    assert (run.stage, run.disposition, run.reasons) == ("finalized", Disposition.CLEARED, [])
    assert fields_of(marks(run.open_reasons, so.DIFFERS)) == {"habitat"}
    # A value changed after it was judged is not checked: refinalized, its mark is open as well.
    run.fields["county"].literal = run.fields["county"].normalized = run.fields["county"].parsed = "Changed"
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert fields_of(marks(run.open_reasons, so.NOT_CHECKED)) == {"county"}
    view = summary(done)
    assert view["reason_codes"] == [] and set(marks(run.open_reasons)) <= set(view["open_reason_codes"])
    fields = project_fields({key: value.model_dump(mode="json") for key, value in run.fields.items()})
    assert {"habitat", "county"} <= attention_fields(fields, view["open_reason_codes"])
    # The habitat's attention is its mark's alone (the changed county's evidence no longer supports it too).
    assert "habitat" not in attention_fields(fields, [code for code in view["open_reason_codes"] if not so.own(code)])


# ---- 2. the catalogue number settled: agreeing, differing on two, not obtained ------------------------------

def test_agreeing_everywhere_the_record_clears_with_no_open_reason(tmp_path):
    opinion = Opinion(agreeing(tmp_path / "values"))
    run = to_end(rig_on(tmp_path, opinion=opinion)).run
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.CLEARED, None)
    assert (run.reasons, run.open_reasons) == ([], [])
    assert run.second_opinion["status"] == so.OBTAINED and len(opinion.requests) == 1


def test_differing_on_two_optional_fields_the_record_clears_with_exactly_those_two_marks_open(tmp_path):
    rig = rig_on(tmp_path, opinion=Opinion(agreeing(tmp_path / "values", habitat=MEADOW,
        county={"value": None, "evidence": ""})))
    run = to_end(rig).run
    region = run.regions[0].id
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", Disposition.CLEARED, None, [])
    assert run.open_reasons == [f"marked:county:{region}:second_opinion_differs",
                                f"marked:habitat:{region}:second_opinion_differs"]


def not_obtained(case, tmp_path, monkeypatch):
    """The record of each way the second opinion is not obtained, or switched off."""
    from pydantic_ai.exceptions import ModelHTTPError

    folder = tmp_path / case
    if case == "switched-off":
        return to_end(rig_on(folder, switched_off=True)).run
    answers = {"402": Opinion(error=ModelHTTPError(402, "second-opinion", body="credit")),
               "503": Opinion(error=ModelHTTPError(503, "second-opinion", body="down")),
               "error": Opinion(error=RuntimeError("provider_request_failed")),
               "malformed": Opinion(raw="{not json"),
               "partial": Opinion({key: value for key, value in full().items() if key != "city"})}
    opinion = answers.get(case) or Opinion(full())
    rig = rig_on(folder, opinion=opinion)
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


CAUSES = {"switched-off": (so.SWITCHED_OFF, None), "402": (so.NOT_OBTAINED, "provider_error_402"),
          "503": (so.NOT_OBTAINED, "provider_error_503"), "error": (so.NOT_OBTAINED, "provider_error"),
          "malformed": (so.NOT_OBTAINED, "malformed"), "partial": (so.NOT_OBTAINED, "malformed"),
          "budget": (so.NOT_OBTAINED, "budget"), "unconfigured": (so.NOT_OBTAINED, "unconfigured"),
          "exception": (so.NOT_OBTAINED, "error"), "attempts-used": (so.NOT_OBTAINED, "attempts_used")}


@pytest.mark.parametrize("case", list(CAUSES))
def test_not_obtained_or_switched_off_the_record_clears_with_every_settled_value_not_checked(
        tmp_path, monkeypatch, case):
    """Each way #456 names the second opinion not obtained (a provider error, HTTP 402 included; a malformed or
    partial answer, asked twice; money; no price row; an exception; its attempts used), and switched off: the
    record clears, every settled value the second opinion answers for is open as "not checked", and the step's
    failure changes neither the stage nor the blocker research left."""
    run = not_obtained(case, tmp_path, monkeypatch)
    status, reason = CAUSES[case]
    assert run.second_opinion["status"] == status and run.second_opinion.get("reason") == reason
    assert (run.stage, run.blocker, run.disposition, run.reasons) == ("finalized", None, Disposition.CLEARED, [])
    assert fields_of(marks(run.open_reasons)) == fields_of(marks(run.open_reasons, so.NOT_CHECKED)) == (
        settled_judged(run)) and settled_judged(run)
    assert not marks(run.reasons)


def test_a_worker_deadline_in_the_request_ends_it_not_obtained_and_the_record_clears(tmp_path):
    """The outcome unknown (#456's lost-outcome path): found after the lease, held in full, finalized; the
    record clears with every value not checked."""
    from datetime import datetime

    from specimen_digitization.application.worker_deadline import WorkerDeadlineExceeded

    rig = rig_on(tmp_path, opinion=Opinion(error=WorkerDeadlineExceeded()))
    rig.workflow.step(rig.principal, rig.specimen.id)
    with pytest.raises(WorkerDeadlineExceeded):
        rig.workflow.step(rig.principal, rig.specimen.id)
    held = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert (held.stage, held.blocker, held.disposition) == (so.STEP, None, None)
    rig.clock.now = datetime.fromisoformat(held.lease_until) + timedelta(seconds=1)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["reason"] == "outcome_unknown"
    assert (run.stage, run.blocker, run.disposition, run.reasons) == ("finalized", None, Disposition.CLEARED, [])
    assert fields_of(marks(run.open_reasons, so.NOT_CHECKED)) == settled_judged(run)


# ---- 3. a record held for another reason stays held, the second opinion in any state ----------------------

OPINIONS = {
    "agrees": lambda folder: Opinion(agreeing(folder)),
    "differs": lambda folder: Opinion(agreeing(folder, habitat=MEADOW, county={"value": None, "evidence": ""})),
    "differs-on-the-catalogue-number": lambda folder: Opinion(agreeing(folder,
        fmnh_ins_number={"value": "999", "evidence": "L1: 999"})),
    "not-obtained": lambda folder: Opinion(error=RuntimeError("provider_request_failed")),
    "switched-off": None,
}


def opinion_rig(folder, state, scenario=None):
    make = OPINIONS[state]
    if make is None:
        return rig_on(folder, scenario, switched_off=True)
    return rig_on(folder, scenario, make(folder / "values"))


def coverage(run):
    run.coverage_confirmed = False


def given_up(run):
    run.findings.append(RunFinding(rule_id=field_step.GIVEN_UP, rule_version=field_step.GIVEN_UP_RULES,
        severity="warning", reason_code=f"{field_step.GIVEN_UP}:token_budget_exhausted"))


def wrong_format(run):
    value = run.fields[CATALOGUE]
    value.literal = value.parsed = value.normalized = "12AB"


HOLDS_AFTER = {  # a hold that arises on a finished record; refinalized (what the endpoint or step then runs)
    "coverage-unconfirmed": (coverage, "label_coverage_unconfirmed"),
    "research-given-up": (given_up, field_step.GIVEN_UP),
    "pending-approval": (person_acted, APPROVAL),
    "catalogue-number-of-the-wrong-format": (wrong_format, "identifier_format"),
}
HOLDS_FROM = {  # a record held from research on
    "catalogue-number-unsettled": (catalogue_number_lacking, f"mandatory_unresolved:{CATALOGUE}"),
    "catalogue-label-readers-differ": (readers_differ_on_the_collectors, "unresolved_transcription:"),
}


def held_by(run, code):
    return any(reason == code or (code.endswith(":") and reason.startswith(code)) for reason in run.reasons)


@pytest.mark.parametrize("state", list(OPINIONS))
@pytest.mark.parametrize("hold", [*HOLDS_FROM, *HOLDS_AFTER])
def test_a_record_held_for_another_reason_stays_held_whatever_the_second_opinion(tmp_path, state, hold):
    if hold in HOLDS_FROM:
        scenario, code = HOLDS_FROM[hold]
        run = to_end(opinion_rig(tmp_path, state, scenario)).run
    else:
        change, code = HOLDS_AFTER[hold]
        run = to_end(opinion_rig(tmp_path, state)).run
        change(run)
        field_step.refinalize(run, today=TODAY)
    assert run.stage == "finalized" and run.disposition == Disposition.REVIEW and held_by(run, code), run.reasons
    # No second-opinion mark holds the record; where it marks, the mark is open.
    assert not marks(run.reasons)
    assert not [code for code in marks(run.open_reasons) if code.startswith(f"marked:{CATALOGUE}:")]


# ---- 4. a person's decision: no mark on their field, their approval hold, approval clears ------------------

def test_a_persons_decision_carries_no_mark_holds_until_approval_and_buys_no_second_opinion(tmp_path):
    """#456: a field a person decided carries no second-opinion mark. #455: the person's decision holds the record
    for their approval (human_approval_required, from run.pending_review). Approved, it clears. Retry and
    Resume in between ask the second opinion nothing again for unchanged values."""
    opinion = Opinion(agreeing(tmp_path / "values", habitat=MEADOW))
    rig = rig_on(tmp_path, opinion=opinion)
    first = to_end(rig).run
    assert first.disposition == Disposition.CLEARED and fields_of(marks(first.open_reasons)) == {"habitat"}
    habitat = first.fields["habitat"]
    app_after = {"literal": habitat.literal, "parsed": habitat.parsed, "normalized": habitat.normalized,
                 "state": habitat.state.value, "reason": habitat.reason}
    client = review_client(rig)
    decided = decide(client, rig, "field-habitat", "field", target_id="habitat", after=app_after,
        evidence_ids=list(habitat.evidence_ids))
    assert decided.person_decided_fields == ["habitat"] and decided.pending_review == [APPROVAL]
    assert (decided.disposition, decided.reasons) == (Disposition.REVIEW, [APPROVAL])
    assert not [code for code in marks([*decided.reasons, *decided.open_reasons]) if ":habitat:" in code]
    again = resumed(rig).run
    assert (again.disposition, again.reasons) == (Disposition.REVIEW, [APPROVAL])
    assert len(opinion.requests) == 1 and len(step_paid(again)) == 1
    again = resumed(rig).run
    assert len(opinion.requests) == 1 and len(step_paid(again)) == 1
    approved = decide(client, rig, "approve", "approve")
    assert (approved.stage, approved.disposition, approved.reasons) == ("finalized", Disposition.CLEARED, [])
    assert approved.pending_review == [] and not marks(approved.open_reasons)
    assert len(opinion.requests) == 1


# ---- PR #456's head d016678b: an approval is the person's; finish is the whole refinalize -------------------

def test_an_approved_record_carries_no_mark_is_not_due_and_is_cleared_by_the_person(tmp_path):
    """#456: for a run a person approved the second opinion contributes no code and is not due. #455's approval
    handling agrees: the approval clears pending_review (clear_on_approval), the record is cleared by a person,
    no mark is left open, and a Retry or Resume afterwards asks nothing and keeps it so."""
    opinion = Opinion(agreeing(tmp_path / "values", habitat=MEADOW))
    rig = rig_on(tmp_path, opinion=opinion)
    assert fields_of(marks(to_end(rig).run.open_reasons)) == {"habitat"}
    client = review_client(rig)
    decide(client, rig, "approve", "approve")
    approved = rig.repository.get(rig.principal.scope, rig.specimen.id)
    run = approved.run
    assert run.human_approved and run.pending_review == [] and not so.due(run) and so.reasons(run) == []
    assert (run.disposition, run.reasons, marks(run.open_reasons)) == (Disposition.CLEARED, [], [])
    assert summary(approved)["cleared_by"] == "person"
    again = resumed(rig).run
    assert (again.disposition, again.reasons, marks(again.open_reasons)) == (Disposition.CLEARED, [], [])
    assert len(opinion.requests) == 1


def test_a_decision_while_the_record_waits_for_the_second_opinion_holds_it_for_approval(tmp_path):
    """#456: a person's decision at stage field_second_opinion sets the stage to finalized and goes through the
    whole refinalize. #455's hold, written where the decision enters (apply_decision), holds the record for the
    person's approval; the marks are split as research's finalize splits them; the decided field is unmarked."""
    rig = rig_on(tmp_path, opinion=Opinion(agreeing(tmp_path / "values", habitat=MEADOW)))
    waiting = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (waiting.stage, waiting.disposition) == (so.STEP, None)
    habitat = waiting.fields["habitat"]
    decided = decide(review_client(rig), rig, "field-habitat", "field", target_id="habitat",
        after={"literal": habitat.literal, "parsed": habitat.parsed, "normalized": habitat.normalized,
               "state": habitat.state.value, "reason": habitat.reason}, evidence_ids=list(habitat.evidence_ids))
    assert (decided.stage, decided.disposition, decided.reasons) == ("finalized", Disposition.REVIEW, [APPROVAL])
    assert decided.pending_review == [APPROVAL] and not marks(decided.reasons)
    assert fields_of(marks(decided.open_reasons)) == settled_judged(decided) - {"habitat"}
    assert not [code for code in decided.open_reasons if ":habitat:" in code and so.own(code)]


@pytest.mark.parametrize("state", ["agrees", "differs", "switched-off"])
def test_a_run_nobody_touched_clears_through_finish_as_through_researchs_finalize(tmp_path, state):
    """The step's finish is the whole refinalize: the record it finalizes is the one research's finalize gives
    on the same run with the step's stored result (finalize_fields, the split included)."""
    rig = opinion_rig(tmp_path, state)
    done = to_end(rig).run
    again = done.model_copy(deep=True)
    field_step.finalize_fields(again, None, (), today=TODAY)
    assert (done.stage, done.disposition) == ("finalized", Disposition.CLEARED)
    assert (again.stage, again.disposition, again.reasons, again.open_reasons) == (
        done.stage, done.disposition, done.reasons, done.open_reasons)
    assert not marks(done.reasons)


def test_a_run_classified_before_the_second_opinion_is_unconfigured_and_still_clears(tmp_path):
    """A run whose pinned profile has no price row for the second opinion (classified before #456): the step
    ends `unconfigured`, every settled value it answers for reads "not checked", and under #455 that holds
    nothing: the record clears."""
    from specimen_digitization.model_gateway import SECOND_OPINION_ROUTE

    opinion = Opinion(full())
    rig = rig_on(tmp_path, opinion=opinion)
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    stored.run.profile_snapshot["processing"]["price_list"]["models"].pop(SECOND_OPINION_ROUTE)
    stored.run.profile.execution.price_list["models"].pop(SECOND_OPINION_ROUTE, None)
    rig.repository.save(rig.principal, stored, stored.version, "old-profile", "old-profile")
    run = to_end(rig).run
    assert so.route_price(run) is None and not opinion.requests
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, "unconfigured")
    assert (run.stage, run.blocker, run.disposition, run.reasons) == ("finalized", None, Disposition.CLEARED, [])
    assert fields_of(marks(run.open_reasons, so.NOT_CHECKED)) == settled_judged(run) and settled_judged(run)


# ---- 5. a record stored before either change; a history restore ------------------------------------------

def test_a_record_stored_before_either_change_loads_and_keeps_its_hold(tmp_path):
    """Stored before #455 and #456: no pending_review, person_decided_fields, second_opinion or open_reasons;
    its reasons hold a person's pending approval and its audit names a person's habitat decision. It loads:
    the hold is adopted (#455), the decision is adopted (#456), and its refinalize holds it for that approval
    alone, the habitat unmarked and every other settled value open as not checked."""
    rig = rig_on(tmp_path, switched_off=True)
    done = to_end(rig)
    payload = done.model_dump(mode="json")
    for key in ("pending_review", "person_decided_fields", "second_opinion", "open_reasons"):
        payload["run"].pop(key, None)
    payload["run"]["reasons"] = [APPROVAL]
    payload["run"]["disposition"] = "needs_human_review"
    payload["audit"].append(AuditEvent(actor="reviewer-1", action="review_field", reason="Reviewed.",
        before={"run_id": done.run.id}, after={"field_key": "habitat", "state": "supported"}).model_dump(mode="json"))
    loaded = active_graph.unpack(payload, rig.blobs)
    run = loaded.run
    assert (run.pending_review, run.person_decided_fields, run.second_opinion) == ([APPROVAL], ["habitat"], None)
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [APPROVAL])
    assert fields_of(marks(run.open_reasons, so.NOT_CHECKED)) == settled_judged(run) - {"habitat"}
    # A legacy record with nothing to adopt loads exactly as stored.
    plain = done.model_dump(mode="json")
    assert active_graph.unpack(plain, rig.blobs).model_dump(mode="json") == plain


def test_a_history_restore_returns_a_self_consistent_state(tmp_path):
    """A restore to the revision before a person's decision returns that revision's own second opinion, decided
    list and open marks, held for review after the restore (#455); refinalized, it is the same; approved, it
    clears, and the approval is the person's: the second opinion contributes no code to an approved run (#456)."""
    from specimen_digitization.application.history_restore import restored_specimen

    rig = rig_on(tmp_path, opinion=Opinion(agreeing(tmp_path / "values", habitat=MEADOW)))
    revision = to_end(rig)
    region = revision.run.regions[0].id
    flagged = [f"marked:habitat:{region}:second_opinion_differs"]
    assert (revision.run.disposition, marks(revision.run.open_reasons)) == (Disposition.CLEARED, flagged)
    habitat = revision.run.fields["habitat"]
    client = review_client(rig)
    decide(client, rig, "field-habitat", "field", target_id="habitat",
        after=habitat.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(habitat.evidence_ids))
    base = rig.repository.get(rig.principal.scope, rig.specimen.id)
    source = rig.repository.version(rig.principal.scope, rig.specimen.id, revision.version)
    restored = restored_specimen(base, source)
    run = restored.run
    assert run.person_decided_fields == [] and run.second_opinion == revision.run.second_opinion
    assert (run.disposition, run.reasons, marks(run.open_reasons)) == (
        Disposition.REVIEW, [HISTORY_RESTORED], flagged)
    assert run.pending_review == [HISTORY_RESTORED]
    before = (run.disposition, list(run.reasons), list(run.open_reasons))
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons, run.open_reasons) == before
    saved = rig.repository.save(rig.principal, restored, base.version, "restore", "restore")
    loaded = rig.repository.get(rig.principal.scope, saved.id)
    assert (loaded.run.reasons, loaded.run.open_reasons, loaded.run.person_decided_fields) == (
        [HISTORY_RESTORED], before[2], [])
    approved = decide(client, rig, "approve", "approve")
    assert (approved.disposition, approved.reasons, marks(approved.open_reasons)) == (Disposition.CLEARED, [], [])


# ---- Codex round 8 on #456 (d016678b): an unconfirmed location reassessment survives the step --------------

@pytest.mark.parametrize("state", ["agrees", "differs", "not-obtained", "switched-off", "without-the-step"])
def test_an_unconfirmed_location_reassessment_holds_through_the_step_and_a_resume(tmp_path, monkeypatch, state):
    """Research leaves the city unproved by a location reassessment (FieldResearchStep._retained_reassessment,
    after its own finalize). The hold is durable (#455: run.pending_review, derived at every finalize), so the
    step's finish (the whole refinalize) and a Resume keep it, the second opinion obtained, not obtained or
    switched off; the record is held exactly as #455 alone holds it ("without-the-step": the second opinion
    contributes no mark and is never due), and a person's approval clears it."""
    from specimen_digitization.application.standing_holds import REASSESSMENT_UNCONFIRMED
    from specimen_digitization.field_research.step import FieldResearchStep

    hold = f"{REASSESSMENT_UNCONFIRMED}:city"
    original = FieldResearchStep._retained_reassessment

    def leaves_the_city(run, retained, *, replace=False):
        original(run, {*retained, "city"}, replace=replace)

    monkeypatch.setattr(FieldResearchStep, "_retained_reassessment", staticmethod(leaves_the_city))
    if state == "without-the-step":
        monkeypatch.setattr(so, "derived", lambda run, readings=(): [])
        rig = rig_on(tmp_path, switched_off=True)
    else:
        rig = opinion_rig(tmp_path, state)
    done = to_end(rig).run
    # The step ran and finished (its stored result), except where it is never due.
    assert done.stage == "finalized" and (done.second_opinion is None) == (state == "without-the-step")
    assert (done.disposition, done.reasons, done.pending_review) == (Disposition.REVIEW, [hold], [hold])
    monkeypatch.setattr(FieldResearchStep, "_retained_reassessment", staticmethod(original))
    again = resumed(rig).run
    assert (again.disposition, again.reasons, again.pending_review) == (Disposition.REVIEW, [hold], [hold])
    approved = decide(review_client(rig), rig, "approve", "approve")
    assert (approved.disposition, approved.reasons, approved.pending_review) == (Disposition.CLEARED, [], [])


@pytest.mark.parametrize("cleared_by", ["a-reassessment-that-settles-it", "a-persons-approval"])
def test_the_durable_reassessment_hold_wins_in_the_steps_finish(tmp_path, cleared_by):
    """#456 at d2ea7b28 kept research's `location_reassessment_unconfirmed:*` reasons across the step's finish.
    On the merged tree #455's durable state decides that hold: finish never duplicates it, and once the durable
    hold is cleared (a reassessment that settles the family, standing_holds.replace_reassessment, or a person's
    approval) a reason research left in the list is not carried back."""
    from specimen_digitization.application.standing_holds import (
        REASSESSMENT_UNCONFIRMED,
        clear_on_approval,
        note_pending,
        replace_reassessment,
    )

    hold = f"{REASSESSMENT_UNCONFIRMED}:city"
    run = to_end(opinion_rig(tmp_path, "agrees")).run
    note_pending(run, hold)
    run.reasons = [*run.reasons, hold]  # as _retained_reassessment leaves the list after research's finalize
    so.finish(run)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [hold])
    run.reasons = [*run.reasons, hold]  # a stale copy in the list, the durable hold then cleared
    if cleared_by == "a-persons-approval":
        run.human_approved = True
        clear_on_approval(run)
    else:
        replace_reassessment(run, [])
    so.finish(run)
    assert (run.disposition, run.reasons, run.pending_review) == (Disposition.CLEARED, [], [])


# ---- the combined pull request (coordinator, after #456's G51 rounds 1-2 and Codex round 9) -------------------
# #455's rule for `location_reassessment_unconfirmed:<field>`: recorded in run.pending_review by the reassessment
# that leaves the field unproved (_retained_reassessment), derived at every finalize on every path; it stays until
# a person approves the record (clear_on_approval) or a later reassessment of the family settles it
# (replace_reassessment). The second opinion's finish is the whole refinalize and carries nothing across.

def reassessment_hold(codes):
    return sorted(code for code in codes if code.startswith("location_reassessment_unconfirmed:"))


def _api(rig, action, monkeypatch):
    """A run action through the API (Retry, Resume, reassess_locations), as the app sends it; queueing saves the
    record pending for a worker, as production's lane.queue does (its collection registry is not this rig's)."""
    from test_step import ORG

    from specimen_digitization.application import api as app_api
    from specimen_digitization.application.domain import now

    def queue(specimen, registry, actor):
        specimen.run.stage, specimen.run.queued_at = "pending", now()

    monkeypatch.setattr(app_api, "queue", queue)
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = review_client(rig).post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": f"{action}-{current.version}"},
        json={"expected_revision": current.version, "action": action, "reason": "Run it again."})
    assert response.status_code == 200, response.text


def _queued_pending(rig):
    """What Resume saves on a record waiting at the step's stage in production: pending, no disposition, before
    a worker picks it up (Codex round 9 on #456)."""
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    held.run.stage, held.run.disposition = "pending", None
    rig.repository.save(rig.principal, held, held.version, "resume-queued", "resume-queued")


def _without_the_step(monkeypatch):
    """#455 alone: the second opinion contributes no mark and is never due."""
    monkeypatch.setattr(so, "derived", lambda run, readings=(): [])


@pytest.mark.parametrize("step", [True, False], ids=["with-the-step", "455-alone"])
def test_the_real_reassess_locations_action_with_the_gazetteer_down_then_the_step_keeps_the_hold(tmp_path,
        monkeypatch, step):
    """(b) G51 round 2's case: a record whose city research could not settle; the reviewer's real
    `reassess_locations` action; research again with every gazetteer down, so the family is retained unconfirmed;
    then the second opinion's step. The reassessment's durable hold is in the reasons and in pending_review after
    the step's finish, as #455 alone keeps it (the same record without the step)."""
    from test_second_opinion import Current, others
    from test_step import LABEL, answering

    from specimen_digitization.field_research.contracts import FieldAnswer

    unresolved = FieldAnswer(outcome="sources_cannot_resolve", literal=LABEL["city"], reading_names=["1A"],
        explanation="Could not settle it.")

    def through(folder, with_step):
        with pytest.MonkeyPatch.context() as patch:
            if not with_step:
                _without_the_step(patch)
            rig = build_rig(folder)
            mounted(rig, Scripted({"city": answering(unresolved)}))
            rig.workflow.second_opinion = None
            to_end(rig)
            _api(rig, "reassess_locations", patch)
            mounted(rig, Scripted({"city": answering(unresolved)}),
                tools_down=("tgn", "geolocate", "geonames", "wikidata", "gbif"))
            if with_step:
                rig.workflow.second_opinion = so.SecondOpinionStep(model_factory=Current(rig).factory)
            return to_end(rig).run

    run, alone = through(tmp_path / "run", step), through(tmp_path / "alone", False)
    held = reassessment_hold(run.reasons)
    assert run.stage == "finalized" and run.disposition == Disposition.REVIEW
    assert held and held == reassessment_hold(run.pending_review) == reassessment_hold(alone.reasons)
    assert others(run) == others(alone) and (run.second_opinion is not None) == step


@pytest.mark.parametrize("step", [True, False], ids=["with-the-step", "455-alone"])
def test_codex_r9_a_decision_on_city_after_a_resume_before_the_worker_is_455s_result(tmp_path, monkeypatch, step):
    """(c) Codex round 9 on #456: research leaves `location_reassessment_unconfirmed:city` and the record waits at
    the step; Resume saves it pending; before the worker runs, a person decides `city` keeping its value; then the
    worker. The result is #455's for that decision (the same sequence without the step): the person's approval
    hold added, the durable reassessment hold neither lost nor carried back stale."""
    from test_second_opinion import Current, others, reassessed_unconfirmed

    def sequence(folder, with_step):
        with pytest.MonkeyPatch.context() as patch:
            if not with_step:
                _without_the_step(patch)
            rig, research = reassessed_unconfirmed(folder, patch, (lambda rig: so.SecondOpinionStep(
                model_factory=Current(rig).factory)) if with_step else None)
            assert (research.run.stage == so.STEP) == with_step
            _queued_pending(rig)
            city = rig.repository.get(rig.principal.scope, rig.specimen.id).run.fields["city"]
            decide(review_client(rig), rig, "city", "field", target_id="city",
                after=city.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(city.evidence_ids))
            return research.run, to_end(rig).run

    research, final = sequence(tmp_path / "run", step)
    _, alone = sequence(tmp_path / "alone", False)
    assert reassessment_hold(research.reasons)
    assert final.stage == "finalized" and final.disposition == Disposition.REVIEW
    assert others(final) == others(alone) and APPROVAL in final.reasons
    assert reassessment_hold(final.reasons) == reassessment_hold(final.pending_review)
    assert final.pending_review == alone.pending_review


@pytest.mark.parametrize("action", ["resume", "retry"])
def test_resume_and_retry_of_a_waiting_record_recheck_then_the_step_with_the_hold_intact(tmp_path, monkeypatch,
        action):
    """(d) Resume and Retry of a record waiting at the step's stage, through the API: research's recheck runs as on
    main, then the step; one paid call at most for the step; the reassessment hold intact."""
    from test_second_opinion import Current, reassessed_unconfirmed

    rig, research = reassessed_unconfirmed(tmp_path, monkeypatch, lambda rig: so.SecondOpinionStep(
        model_factory=Current(rig).factory))
    assert research.run.stage == so.STEP
    held = reassessment_hold(research.run.reasons)
    _api(rig, action, monkeypatch)
    done = to_end(rig)
    final = done.run
    steps = [event.reason for event in done.audit if event.action == "workflow_step"]
    after = steps[len([e for e in research.audit if e.action == "workflow_step"]):]
    assert "field_research_recheck" in after and after[-1] == so.STEP
    assert final.stage == "finalized" and final.disposition == Disposition.REVIEW
    assert len(step_paid(final)) <= 1 and final.second_opinion
    assert held and reassessment_hold(final.reasons) == held == reassessment_hold(final.pending_review)


@pytest.mark.parametrize("action", ["resume", "retry"])
def test_a_main_written_approved_record_stays_cleared_on_resume_and_retry(tmp_path, monkeypatch, action):
    """(e) A record written and approved before the change (no second-opinion key, approved by a person, cleared):
    Resume or Retry through the API keeps it cleared by the person, and the step is never attempted."""
    opinion = Opinion(agreeing(tmp_path / "values", habitat=MEADOW))
    with pytest.MonkeyPatch.context() as patch:
        _without_the_step(patch)
        rig = rig_on(tmp_path, switched_off=True)
        to_end(rig)
        decide(review_client(rig), rig, "approve", "approve")
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    stored.run.second_opinion = None
    rig.repository.save(rig.principal, stored, stored.version, "as-main", "as-main")
    rig.workflow.second_opinion = so.SecondOpinionStep(model_factory=opinion.factory)
    _api(rig, action, monkeypatch)
    done = to_end(rig)
    run = done.run
    assert (run.stage, run.disposition, run.reasons, marks(run.open_reasons)) == (
        "finalized", Disposition.CLEARED, [], [])
    assert run.human_approved and summary(done)["cleared_by"] == "person"
    assert not opinion.requests and so.STEP not in run.attempts
