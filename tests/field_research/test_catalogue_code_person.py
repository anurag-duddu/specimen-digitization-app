"""The slide's QR code and a person's authority over the catalogue number, through the real routes.

Each test drives the workflow, the decision endpoint and the action route (Retry, Resume) on the
published profile, where the catalogue number is the one mandatory field: no stubbed
step.human_keys. The barcode label's readers write 0010007 and the code row says 0010001, so
with no person the code gives 0010001 (field_research/catalogue_code.py, rule 2).

What the code guarantees: the code's rule never acts on a field a person holds authority over
(second_opinion.authority, read from the run's durable state). It guarantees nothing about
research itself: main asks a field a person decided at the endpoint again on a Retry, and what
its expert then answers replaces the person's value (a person's 0010007 by an open field when
the expert names several numbers). That is main's behaviour, unchanged here, and the tests say
where it shows.

The sequences are those of the independent review of PR #458 at b5bdd290 (its probes ran them on
origin/main beside the head); each failed there, the code's 0010001 replacing the person's value.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from test_approval_and_research import queue_in_place, save_by_hand
from test_catalogue_code import CODE, FIRST, KEY, OTHER, PRINTED, barcode_label, catalogue, several
from test_step import ORG, Scripted, answering, build_rig, failing, mounted, review_client

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, Evidence, ValueState
from specimen_digitization.application.workflow import FIELD_RESEARCH
from specimen_digitization.field_research.contracts import FieldAnswer

HEADERS = {"Authorization": "Bearer reviewer"}
PERSONS = "0010007"
CANNOT = answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="The label does not say."))
# The readers' number settled by the expert; the habitat left open, so that Retry has a field to research.
DIFFERS = {KEY: catalogue(PERSONS, PERSONS), "habitat": CANNOT}
SEVERAL = {KEY: several(CODE, PERSONS), "habitat": CANNOT}


class Record:
    """One record on the published profile with a barcode label and its code row, and the routes a
    person and the workflow act through."""

    def __init__(self, tmp_path, monkeypatch, *texts, code=True):
        barcode_label(monkeypatch, *texts)
        self.rig = build_rig(tmp_path, FIRST, profile=published_registry().profiles[0])
        queue_in_place(monkeypatch)
        self.client = review_client(self.rig)
        self.count = 0
        self.code = None
        if code:
            def segment(run):
                self.code = Evidence(kind="derived", asset_id=self.rig.specimen.asset.id, region_id=run.regions[1].id,
                    source="barcode", locator="check:barcode_decode",
                    excerpt=f"{KEY}: {CODE} (QR code read by zxing-cpp 3.1.1, ladder rung whole)")
                run.evidence.append(self.code)

            save_by_hand(self.rig, segment, "segment-code")

    @property
    def run(self):
        return self.rig.repository.get(self.rig.principal.scope, self.rig.specimen.id).run

    def research(self, scripts):
        """Step the workflow to rest with these experts; the resolver, for the fields it was asked."""
        resolver = Scripted(scripts)
        mounted(self.rig, resolver)
        self.rig.clock.now += timedelta(hours=1)
        for _ in range(40):
            current = self.rig.workflow.step(self.rig.principal, self.rig.specimen.id)
            if current.run.stage == "retry_scheduled" and current.run.next_retry_at:
                self.rig.clock.now = datetime.fromisoformat(current.run.next_retry_at)
                continue
            if current.run.stage in {"finalized", "processing_blocked"}:
                return resolver
        raise AssertionError(current.run.stage)

    def post(self, path, body):
        current = self.rig.repository.get(self.rig.principal.scope, self.rig.specimen.id)
        self.count += 1
        response = self.client.post(path.format(org=ORG, specimen=current.id, run=current.run.id),
            headers={**HEADERS, "Idempotency-Key": f"k{self.count}"},
            json={"expected_revision": current.version, "reason": "Reviewed.", **body(current)})
        assert response.status_code == 200, response.text
        return self.run

    def decide(self, key, literal, *, cite):
        """A person's field decision at the decision endpoint: `literal`, supported, citing a reader's
        row of the barcode label ("reader"), the field's own rows as the app prefills them ("own"),
        or none."""
        def body(current):
            run = current.run
            rows = ([row.id for row in run.evidence if row.kind == "literal" and row.region_id == run.regions[1].id][:1]
                if cite == "reader" else list(run.fields[key].evidence_ids) if cite == "own" else [])
            return {"kind": "field", "base_record_version_id": f"{run.id}:{current.version}", "target_id": key,
                "after": {"literal": literal, "parsed": literal, "state": "supported", "reason": "A person read the label."},
                "evidence_ids": rows}

        return self.post("/v1/organizations/{org}/specimens/{specimen}/decisions", body)

    def approve(self):
        return self.post("/v1/organizations/{org}/specimens/{specimen}/decisions",
            lambda current: {"kind": "approve", "base_record_version_id": f"{current.run.id}:{current.version}"})

    def act(self, action):
        return self.post("/v1/organizations/{org}/runs/{run}/actions", lambda current: {"action": action})

    def cleared_by(self):
        detail = self.client.get(f"/v1/organizations/{ORG}/specimens/{self.rig.specimen.id}", headers=HEADERS)
        assert detail.status_code == 200, detail.text
        return detail.json()["cleared_by"]


def number(run):
    value = run.fields[KEY]
    return (value.state, value.normalized or value.parsed or value.literal)


def notes(run):
    return [finding.reason_code for finding in run.findings if finding.field_key == KEY and finding.rule_id == "barcode_decode"]


def the_persons(record):
    """The catalogue number is the person's 0010007: the code neither replaced it nor decides it."""
    run = record.run
    assert number(run) == (ValueState.SUPPORTED, PERSONS)
    assert record.code.id not in run.fields[KEY].evidence_relations
    assert KEY in run.person_decided_fields and "barcode_readers_differ:" + KEY not in notes(run)
    return run


def the_code_gave(record):
    run = record.run
    assert number(run) == (ValueState.SUPPORTED, CODE) and run.fields[KEY].evidence_ids == [record.code.id]
    return run


def test_a_person_saves_a_number_and_retries_before_approving(tmp_path, monkeypatch):
    """The code gives 0010001. A person saves 0010007 citing a reader's row; Retry researches the
    field again (main's task selection) and its expert settles the readers' 0010007; the code stands
    aside; the person approves and the record is cleared by a person with 0010007."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.research(DIFFERS)
    assert the_code_gave(record).disposition == Disposition.CLEARED
    record.decide(KEY, PERSONS, cite="reader")
    the_persons(record)
    assert FIELD_RESEARCH not in record.act("retry").completed_steps
    asked = record.research(DIFFERS)
    assert KEY in asked.calls
    the_persons(record)
    approved = record.approve()
    assert (approved.disposition, approved.human_approved, record.cleared_by()) == (Disposition.CLEARED, True, "person")
    the_persons(record)


def test_a_person_saves_a_number_approves_and_later_decides_another_field(tmp_path, monkeypatch):
    """The review's first sequence. A person saves 0010007 and approves (cleared by a person);
    Resume and Retry leave it; later the person decides the habitat and Retry researches the open
    fields again. At b5bdd290 that Retry gave the code's 0010001 and the next approval cleared the
    record by a person with the code's number. The person's 0010007 stands throughout."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.research(DIFFERS)
    the_code_gave(record)
    record.decide(KEY, PERSONS, cite="reader")
    approved = record.approve()
    assert (approved.disposition, record.cleared_by()) == (Disposition.CLEARED, "person")
    for action in ("resume", "retry"):
        record.act(action)
        record.research(DIFFERS)
        assert the_persons(record).human_approved is True
    record.decide("habitat", "Swamp", cite="none")
    record.act("retry")
    record.research(DIFFERS)
    the_persons(record)
    approved = record.approve()
    assert (approved.disposition, approved.human_approved, record.cleared_by()) == (Disposition.CLEARED, True, "person")
    the_persons(record)


def test_a_person_saves_a_number_before_any_research(tmp_path, monkeypatch):
    """The decision is saved before research runs: the first research asks the field's expert
    (main's task selection), which settles the readers' 0010007, and the code never gives its
    number; approved, the record is the person's."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.decide(KEY, PERSONS, cite="none")
    record.research(DIFFERS)
    the_persons(record)
    record.approve()
    record.act("resume")
    record.research(DIFFERS)
    assert the_persons(record).human_approved is True and record.cleared_by() == "person"


def test_a_record_main_wrote_with_the_barcode_differs_hold_is_decided_and_retried(tmp_path, monkeypatch):
    """A record as origin/main finalized it: the readers' 0010007 settled, marked barcode_differs
    and held (written here by research with the code's giving switched off and main's mark put
    on). A person saves 0010007; Retry on this code researches the field again; the code stands
    aside from the person's field."""
    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    def as_main(run, task, readings, *, decision=None):
        run.findings.append(field_step.RunFinding(rule_id=field_step.SETTLEMENT, rule_version=field_step.SETTLEMENT_RULES,
            severity="warning", field_key=KEY, evidence_ids=[],
            reason_code=field_step.marked_code(KEY, run.regions[1].id, catalogue_code.DIFFERS)))
        return True

    record = Record(tmp_path, monkeypatch, OTHER)
    with monkeypatch.context() as main:
        main.setattr(catalogue_code, "give", as_main)
        record.research(DIFFERS)
    held = record.run
    assert number(held) == (ValueState.SUPPORTED, PERSONS) and held.disposition == Disposition.REVIEW
    assert any(reason.endswith(":barcode_differs") for reason in held.reasons)
    record.decide(KEY, PERSONS, cite="reader")
    record.act("retry")
    asked = record.research(DIFFERS)
    assert KEY in asked.calls
    the_persons(record)
    assert record.approve().disposition == Disposition.CLEARED and record.cleared_by() == "person"
    the_persons(record)


def test_a_blocked_record_is_decided_and_retried(tmp_path, monkeypatch):
    """Another field's expert fails on every attempt and the run is blocked; a person saves
    0010007; Retry. Whatever research then does with the field, the code gives it no number. At
    b5bdd290 the code's 0010001 replaced the person's value."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.research({**DIFFERS, "country": failing("model_error")})
    assert record.run.stage == "processing_blocked"
    decided = record.decide(KEY, PERSONS, cite="reader")
    # A blocked run is not finalized by the decision, so the rule's earlier note waits for the
    # next research of the field; the value is the person's at once.
    assert number(decided) == (ValueState.SUPPORTED, PERSONS) and decided.person_decided_fields == [KEY]
    record.act("retry")
    asked = record.research(DIFFERS)
    # The run's attempts are used up: research is given up and asks no expert. Main's give-up leaves
    # the field unresolved with the person's literal; the code gives it no number.
    run = record.run
    value = run.fields[KEY]
    assert asked.calls == [] and (value.state, value.literal) == (ValueState.UNRESOLVED, PERSONS)
    assert record.code.id not in value.evidence_relations and notes(run) == []
    assert run.disposition == Disposition.REVIEW and record.cleared_by() is None


def test_a_correction_saved_on_the_apps_prefilled_evidence_is_not_cleared_with_the_codes_number(tmp_path, monkeypatch):
    """The app prefills a field decision with the field's own rows: here the code row, which does
    not hold the person's 0010007, so the correction stays held (evidence_does_not_support_value).
    At b5bdd290 a Retry then cleared the record by the system with the code's 0010001. The code
    stands aside; research settles the readers' 0010007, as on main."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.research(DIFFERS)
    the_code_gave(record)
    decided = record.decide(KEY, PERSONS, cite="own")
    assert f"evidence_does_not_support_value:{KEY}" in decided.reasons
    record.act("retry")
    record.research(DIFFERS)
    run = the_persons(record)
    assert run.disposition == Disposition.REVIEW and record.cleared_by() is None


def test_research_may_reopen_a_persons_number_and_the_code_still_gives_none(tmp_path, monkeypatch):
    """Main's behaviour, unchanged and not this rule's: the readers differ, the code gives 0010001,
    a person saves 0010007, and on Retry the field's expert names several numbers, so research
    leaves the field open in place of the person's value. The code's rule does not act on the
    person's field: it stays open and held, as on main. At b5bdd290 the code's 0010001 filled it
    and the next approval cleared the record by a person."""
    record = Record(tmp_path, monkeypatch, PRINTED, OTHER)
    record.research(SEVERAL)
    the_code_gave(record)
    record.decide(KEY, PERSONS, cite="reader")
    record.act("retry")
    record.research(SEVERAL)
    run = record.run
    assert run.fields[KEY].state == ValueState.AMBIGUOUS and number(run)[1] != CODE and notes(run) == []
    assert run.disposition == Disposition.REVIEW and f"mandatory_unresolved:{KEY}" in run.reasons
    approved = record.approve()
    assert approved.disposition == Disposition.REVIEW and record.cleared_by() is None


def test_the_rules_note_is_replaced_and_never_left_beside_another(tmp_path, monkeypatch):
    """The review's note. The code gives 0010001 over the readers' 0010007 and leaves one
    barcode_readers_differ note. A person then transcribes the barcode label, and research runs
    again: the rule now only notes that the code differs from the person's transcript
    (barcode_person_differs), and the earlier note is gone. At b5bdd290 both notes stood."""
    record = Record(tmp_path, monkeypatch, OTHER)
    record.research(DIFFERS)
    assert notes(the_code_gave(record)) == [f"barcode_readers_differ:{KEY}"]

    def transcript(current):
        run = current.run
        return {"kind": "transcription", "base_record_version_id": f"{run.id}:{current.version}",
            "target_id": run.regions[1].id, "after": {"text": OTHER, "state": "supported"}}

    record.post("/v1/organizations/{org}/specimens/{specimen}/decisions", transcript)
    record.research(DIFFERS)
    run = record.run
    assert number(run) == (ValueState.SUPPORTED, PERSONS)
    assert notes(run) == [f"barcode_person_differs:{KEY}"]


@pytest.mark.parametrize("times", [2, 3])
def test_a_number_given_again_in_one_run_keeps_one_note(tmp_path, monkeypatch, times):
    """The rule applied again to the same run (the field put back as research had settled it, as a
    history restore or a second attempt leaves it) replaces its note: one barcode_readers_differ,
    however often the code gives the number. At b5bdd290 each giving added one."""
    from test_catalogue_code import rig_with, with_code
    from test_step import settle as settle_run

    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research import step as field_step

    rig = rig_with(tmp_path, monkeypatch, OTHER)
    run = rig.specimen.run
    settle_run(rig, Scripted({KEY: catalogue(PERSONS, PERSONS)}))
    readers = run.fields[KEY].model_copy(deep=True)
    with_code(rig)
    for _ in range(times):
        run.fields[KEY] = readers.model_copy(deep=True)
        task = field_step.FieldTask(key=KEY, mandatory=True, current=run.fields[KEY], candidates=(), tools=())
        assert catalogue_code.settle(run, task, field_step.run_readings(run)) is True
    assert notes(run) == [f"barcode_readers_differ:{KEY}"]
    assert [f.reason_code for f in run.findings if f.rule_id == "field_settlement" and f.field_key == KEY] == [
        f"cleared:{KEY}:{run.regions[1].id}"]


# ---- catalogue_code.forget_stale, the one call in step.finalize_fields ---------------------------

NO_CODE_ROW = {
    "readers-agree": ((PRINTED,), catalogue(CODE, CODE)),
    "readers-differ": ((PRINTED, OTHER), several(CODE, PERSONS)),
    "another-number": ((OTHER,), catalogue(PERSONS, PERSONS)),
}


@pytest.mark.parametrize("scenario", NO_CODE_ROW)
def test_the_finalize_time_removal_changes_nothing_on_a_run_with_no_code_row(tmp_path, monkeypatch, scenario):
    """A run with no code row, researched and applied once, then finalized twice from the same
    state: with catalogue_code.forget_stale as finalize_fields calls it, and with it switched off.
    The two records are equal in every stored value (the whole run, dumped)."""
    import copy

    from test_catalogue_code import rig_with
    from test_step import TODAY, research

    from specimen_digitization.field_research import catalogue_code
    from specimen_digitization.field_research.step import apply_outcomes, finalize_fields

    texts, script = NO_CODE_ROW[scenario]
    rig = rig_with(tmp_path, monkeypatch, *texts)
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({KEY: script}))
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    assert notes(run) == []
    with_it, without_it = copy.deepcopy(run), copy.deepcopy(run)
    finalize_fields(with_it, None, outcomes, today=TODAY)
    monkeypatch.setattr(catalogue_code, "forget_stale", lambda run: None)
    finalize_fields(without_it, None, outcomes, today=TODAY)
    assert with_it.stage == "finalized" and with_it.model_dump(mode="json") == without_it.model_dump(mode="json")


def test_the_finalize_time_removal_takes_the_one_note_and_only_when_the_rule_no_longer_applies(tmp_path, monkeypatch):
    """catalogue_code.forget_stale itself. While the field is the number the code gave, the note
    stays and nothing changes. Once the field is another value (here a person's), exactly the
    barcode_readers_differ finding goes: every field and every other finding is as it was. A run
    whose code row is gone loses the note the same way."""
    from test_catalogue_code import rig_with, with_code
    from test_step import settle as settle_run

    from specimen_digitization.field_research import catalogue_code

    rig = rig_with(tmp_path, monkeypatch, OTHER)
    run = rig.specimen.run
    code = with_code(rig)
    settle_run(rig, Scripted({KEY: catalogue(PERSONS, PERSONS)}))
    assert number(run) == (ValueState.SUPPORTED, CODE) and notes(run) == [f"barcode_readers_differ:{KEY}"]

    def state():
        return ({key: value.model_dump(mode="json") for key, value in run.fields.items()},
            [finding.model_dump(mode="json") for finding in run.findings], list(run.reasons), list(run.open_reasons))

    before = state()
    catalogue_code.forget_stale(run)
    assert state() == before
    given = run.fields[KEY]
    run.fields[KEY] = given.model_copy(update={"literal": PERSONS, "parsed": PERSONS, "evidence_ids": [],
        "evidence_relations": {}, "layer": None, "reason": "A person read the label."})
    fields, found, reasons, opened = state()
    catalogue_code.forget_stale(run)
    assert notes(run) == []
    assert state() == (fields, [f for f in found if f["reason_code"] != f"barcode_readers_differ:{KEY}"], reasons, opened)
    # The same when the field is still the given value and the run no longer holds the code row.
    run.fields[KEY] = given
    run.findings.append(catalogue_code.RunFinding(rule_id=catalogue_code.RULE, rule_version=catalogue_code.RULE_VERSION,
        severity="info", field_key=KEY, reason_code=catalogue_code.READERS_DIFFER, evidence_ids=[code.id]))
    run.evidence[:] = [row for row in run.evidence if row.id != code.id]
    catalogue_code.forget_stale(run)
    assert notes(run) == []
