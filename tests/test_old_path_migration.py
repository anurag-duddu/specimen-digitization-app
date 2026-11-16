"""WP 1.8 part B of docs/execution/units/PLAN.md: a run the old first pass processed, reopened
after the old path's removal, is moved to the units path (workflow.move_to_units).

stored() builds such a run in the shape origin/main d83f4d6f1 stored one (the old first pass is
gone, so it cannot run here): the synthetic specimen, its readers differing at the taxon line,
drained through the synthetic API, then recorded as the old path recorded a run whose first pass
picked reader 1. Its path is the stored default `old` (no first_pass_path key); it has no reading
units; its first-pass decision selects reader 1, every verdict naming it; its transcript is
`first_pass`, reader 1's text, resolved, with reader 1 the decided transcript and reader 2 raw;
its fields are parsed from that text (Workflow.parse); and its pins hold the old first pass's
prompt and not the units prompt. The integrity check holds it to the old path's checks
(integrity.verify_evidence, first_pass.g19_pick). A run main stored so
(~/specimen-golive/units-program/wp18/old_path_completed_run.json, made there by
make_old_path_fixture.py) passed this module's first nine tests too, off the repository, where
its digests are not committed. The synthetic app drains a resumed run in-process
(api.schedule_local), as the worker does in production. The carries of a person's field
decisions, which need the server's save audits, are tested in test_old_path_migration_carry.py."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, create_app
from specimen_digitization.application.domain import Disposition, Profile, Run, Scope
from specimen_digitization.application.first_pass import alignment_units
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.production import pinned_prompt
from specimen_digitization.application.reading_units import OLD, PERSON, UNITS
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow, move_to_units
from specimen_digitization.prompts import PromptName

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
TOKEN = "test-only-local-token"
HEADERS = {"Authorization": "Bearer " + TOKEN}
# The synthetic app's one user (application/api.py, identity).
REVIEWER = "synthetic-reviewer"
# The second synthetic reader's taxon line, as the stored run's readers wrote it.
ALTERNATE = "taxon: different"


class Calls(SyntheticAdapters):
    """The synthetic adapters, recording each label the units first pass is called on."""

    def __init__(self, blobs):
        super().__init__(blobs, SYNTHETIC_TEXT, ALTERNATE)
        self.labels = []

    def first_pass_units(self, specimen, region, readings):
        self.labels.append(region.id)
        return super().first_pass_units(specimen, region, readings)


class TwoLabels(Calls):
    """Calls on a specimen of two labels: the image's top and bottom halves."""

    def segment(self, specimen):
        from specimen_digitization.application.domain import Region

        (whole,) = super().segment(specimen)
        half = whole.height // 2
        return [whole.model_copy(update={"height": half}),
            Region(asset_id=whole.asset_id, x=0, y=half, width=whole.width, height=whole.height - half,
                order=1, method=whole.method, version=whole.version)]


def app(repository, adapters):
    """The synthetic-mode app over the repository: a run a request resumes drains in-process."""
    return TestClient(create_app(mode="synthetic", repository=repository, blobs=adapters.blobs, adapters=adapters,
        token=TOKEN), raise_server_exceptions=False)


def to_old_path(specimen, blobs):
    """The specimen's finalized units-path run recorded as the old path recorded one whose first
    pass picked reader 1 on each label (module docstring), its fields parsed from those picks; a
    field a new run carries (human_field_carry) stays as the parse step keeps it."""
    from specimen_digitization.application.domain import ReaderHandoff
    from specimen_digitization.application.human_field_carry import KEY

    run = specimen.run
    assert (run.stage, run.first_pass_path) == ("finalized", UNITS)
    decisions = {d.region_id: d for d in run.first_pass_decisions}
    transcripts = {t.region_id: t for t in run.transcripts}
    run.first_pass_decisions, run.transcripts = [], []
    for region in run.regions:
        first, second = [o for o in run.observations if o.region_id == region.id]
        decision = decisions[region.id]
        picked = decision.model_copy(update={"selected_observation_id": first.id,
            "differences": [d.model_copy(update={"verdict": first.id}) for d in decision.differences]})
        run.first_pass_decisions.append(picked)
        run.transcripts.append(transcripts[region.id].model_copy(update={"decision_kind": "first_pass",
            "selected_observation_id": first.id, "text": first.literal_text, "resolved": True,
            "differences": picked.differences, "first_pass_call": picked.call,
            "handoffs": [ReaderHandoff(observation_id=first.id, role="decided_transcript",
                handed_text=first.literal_text),
                ReaderHandoff(observation_id=second.id, role="raw_reading", handed_text=second.literal_text)]}))
    run.reading_units = []
    prompts = run.dependencies.get("prompts")
    if isinstance(prompts, dict):
        prompts.pop(PromptName.FIRST_PASS_UNITS.value, None)
        prompts["transcription-disagreement-adjudication"] = {"text": "the old first pass's prompt"}
    run.first_pass_path = OLD
    carried = {key: run.fields[key] for key in run.dependencies.get(KEY, {})}
    Workflow.parse(run, specimen.asset.id, blobs)
    run.fields.update(carried)
    return specimen


def stored(tmp_path, adapters=SyntheticAdapters, change=None):
    """The repository and blobs under tmp_path holding one finalized run of the old path (module
    docstring), made with ``adapters`` (one label; TwoLabels for two) and then ``change``d, and
    its specimen's id."""
    from test_application import intake

    from specimen_digitization.application.storage import digest

    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    made = adapters(blobs) if adapters is not SyntheticAdapters else adapters(blobs, SYNTHETIC_TEXT, ALTERNATE)
    ident = intake(app(repository, made))["specimen_id"]
    specimen = to_old_path(repository.get(SCOPE, ident), blobs)
    if change is not None:
        change(specimen.run)
    principal = SimpleNamespace(user_id=REVIEWER, scope=SCOPE, role="reviewer")
    saved = repository.save(principal, specimen, specimen.version, "old-path", digest({"old_path": True}))
    verify_evidence(saved, blobs)
    return repository, blobs, ident


def workspace(http, ident):
    response = http.get(f"{PREFIX}/specimens/{ident}/workspace", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def the_stored_old_path_run(run):
    """The stored run as the old path recorded it: the old path, finalized, its first pass's pick."""
    assert run.first_pass_path == OLD and "first_pass_path" not in run.model_dump(mode="json")
    assert (run.stage, run.blocker) == ("finalized", None) and run.reading_units == []
    [decision] = run.first_pass_decisions
    assert decision.selected_observation_id == run.observations[0].id
    assert {d.verdict for d in decision.differences} == {run.observations[0].id}
    [transcript] = run.transcripts
    assert (transcript.decision_kind, transcript.selected_observation_id) == ("first_pass", run.observations[0].id)


def completed_on_the_units_path(specimen, blobs, labels):
    """The run completed on the units path: recorded so, its first pass called on its label before
    adjudicate and parse, its decision naming no reading with each difference uncertain, its
    transcript holding that decision's call and the label's units stored; integrity holds."""
    run = specimen.run
    (region,) = run.regions
    assert run.first_pass_path == UNITS and run.model_dump(mode="json")["first_pass_path"] == UNITS
    assert (run.stage, run.blocker) == ("finalized", None)
    assert labels == [region.id]
    steps = run.completed_steps
    assert steps.index(f"first_pass:{region.id}") < steps.index("adjudicate") < steps.index("parse")
    [decision] = run.first_pass_decisions
    assert decision.selected_observation_id is None and decision.differences
    assert {d.verdict for d in decision.differences} == {"uncertain"}
    [transcript] = run.transcripts
    assert transcript.first_pass_call == decision.call
    assert [entry.label for entry in run.reading_units] == [region.id]
    verify_evidence(specimen, blobs)
    return run, region, transcript


def test_an_edit_of_a_completed_old_path_run_completes_it_on_the_units_path(tmp_path):
    """The person's transcript edit resumes the run (application/api.py, kind transcription); the
    workflow moves it to the units path before its next step, the units first pass runs on the
    label, adjudicate applies the person's decision again, and the label's units are the
    person's text (first_pass.source_units)."""
    repository, blobs, ident = stored(tmp_path)
    the_stored_old_path_run(repository.get(SCOPE, ident).run)
    adapters = Calls(blobs)
    http = app(repository, adapters)
    before = workspace(http, ident)
    text = "taxon: as a person reads it"
    response = http.post(f"{PREFIX}/specimens/{ident}/decisions",
        headers={**HEADERS, "Idempotency-Key": "person-edit"},
        json={"expected_revision": before["revision"], "base_record_version_id": before["record_version_id"],
            "kind": "transcription", "target_id": before["regions"][0]["region_id"],
            "after": {"text": text, "state": "supported"}, "reason": "The person reads the label"})
    assert response.status_code == 200, response.text

    specimen = repository.get(SCOPE, ident)
    run, region, transcript = completed_on_the_units_path(specimen, blobs, adapters.labels)
    assert (transcript.actor, transcript.text, transcript.resolved) == (REVIEWER, text, True)
    assert run.reading_units == [alignment_units(region.id, [SimpleNamespace(id=PERSON, literal_text=text)])]
    assert run.disposition is not None


def test_a_restored_old_path_run_resumed_completes_on_the_units_path(tmp_path):
    """The history restore of the old-path revision runs nothing (application/history_restore.py):
    the restored run stays on the old path. Its resume runs the workflow, which moves it to the
    units path before its next step, and it completes there."""
    repository, blobs, ident = stored(tmp_path)
    adapters = Calls(blobs)
    http = app(repository, adapters)
    stored_revision = repository.get(SCOPE, ident).version
    before = workspace(http, ident)
    response = http.post(f"{PREFIX}/specimens/{ident}/history:restore",
        headers={**HEADERS, "Idempotency-Key": "restore"},
        json={"expected_revision": before["revision"], "base_record_version_id": before["record_version_id"],
            "source_revision": stored_revision, "reset_to_initial": False, "reason": "Restore the stored run"})
    assert response.status_code == 200, response.text
    restored = repository.get(SCOPE, ident)
    assert restored.version == stored_revision + 1 and adapters.labels == []
    the_stored_old_path_run(restored.run)
    assert restored.run.disposition == Disposition.REVIEW
    assert "history_restored_requires_review" in restored.run.reasons

    response = http.post(f"{PREFIX}/runs/{restored.run.id}/actions",
        headers={**HEADERS, "Idempotency-Key": "resume"},
        json={"action": "resume", "reason": "Process the restored run", "expected_revision": restored.version})
    assert response.status_code == 200, response.text

    run, _, transcript = completed_on_the_units_path(repository.get(SCOPE, ident), blobs, adapters.labels)
    assert transcript.actor is None and transcript.selected_observation_id is None


def test_a_completed_old_path_run_stepped_without_being_reopened_is_not_moved(tmp_path):
    """The workflow moves a run only when it is reopened: a finalized run's step returns it as it
    is (Workflow._step), on the old path."""
    repository, blobs, ident = stored(tmp_path)
    adapters = Calls(blobs)
    principal = SimpleNamespace(user_id=REVIEWER, scope=SCOPE, role="reviewer")
    before = repository.get(SCOPE, ident)
    after = Workflow(repository, blobs, adapters).step(principal, ident)
    assert after == before and adapters.labels == []
    the_stored_old_path_run(repository.get(SCOPE, ident).run)


def old_path_run(**changes):
    """A run of the old path at its finalize, its prompts pinned as main pinned an old-path run's:
    every prompt but the units one (production.pin_dependencies on d83f4d6f1)."""
    profile = Profile(id="zoology_insects_slides", schema_version="1.0.0")
    pins = {"routes": {}, "prompts": {name.value: {"name": name.value, "text": "pinned on main"}
        for name in (PromptName.LITERAL_TRANSCRIPTION, PromptName.STRUCTURED_EXTRACTION)},
        "policy": {"pinned": "on main"}}
    pins["prompts"]["transcription-disagreement-adjudication"] = {"text": "the old first pass's prompt"}
    run = Run(profile=profile, dependencies=pins, stage="finalize", human_approved=True,
        completed_steps=["pin_dependencies", "classify", "quality_check", "segment", "transcribe:r:a",
            "transcribe:r:b", "first_pass:r", "adjudicate", "parse", "plan", "lookup", "authority:0:parties",
            "field_research", "field_research_recheck", "resolve", "normalize", "validate", "finalize"])
    return run.model_copy(update=changes)


def test_the_move_pins_the_units_prompt_reschedules_from_the_first_pass_and_records_units():
    run = old_path_run()
    pins = json.loads(json.dumps(run.dependencies))

    assert move_to_units(run) is True

    # The units prompt joins the pins; every other pin stays as main pinned it.
    unit_prompt = PromptName.FIRST_PASS_UNITS.value
    assert run.dependencies["prompts"][unit_prompt] == pinned_prompt(run, PromptName.FIRST_PASS_UNITS)
    assert {key: value for key, value in run.dependencies["prompts"].items() if key != unit_prompt} == pins["prompts"]
    assert {key: value for key, value in run.dependencies.items() if key != "prompts"} == {
        key: value for key, value in pins.items() if key != "prompts"}
    # Every step from the first pass on runs again; the readings' steps stay.
    assert run.completed_steps == ["pin_dependencies", "classify", "quality_check", "segment", "transcribe:r:a",
        "transcribe:r:b"]
    assert Workflow.next_step(run) == "adjudicate"  # its region "r" is not on this bare run
    assert run.first_pass_decisions == [] and run.lookups == [] and run.human_approved is False
    assert run.first_pass_path == UNITS


def test_a_move_of_a_run_that_pins_no_prompts_pins_none():
    run = old_path_run(dependencies={"adapter": "SyntheticAdapters", "synthetic": True})
    assert move_to_units(run) is True
    assert run.dependencies == {"adapter": "SyntheticAdapters", "synthetic": True}


@pytest.mark.parametrize("changes", [{"first_pass_path": UNITS},
    {"dependencies": {"evidence_pilot": {"version": "evidence-pilot-v1"}}}], ids=["units-path", "evidence-pilot"])
def test_a_units_path_run_and_an_evidence_pilot_run_are_not_moved(changes):
    """The evidence pilot's lane runs no first pass (application/evidence_pilot.py next_step)."""
    run = old_path_run(**changes)
    before = run.model_copy(deep=True)
    assert move_to_units(run) is False
    assert run == before


def test_the_moved_runs_first_pass_reads_the_pinned_units_prompt(monkeypatch, tmp_path):
    """production's first pass (first_pass._prepared) reads the units prompt from the run's pins:
    after the move it is there, and the call sends it as the instructions."""
    from test_first_pass_units import ANSWER, ROUTE, direct_units

    run = old_path_run(profile=Profile(first_pass_route=ROUTE.route_id, id="zoology_insects_slides",
        schema_version="1.0.0"))
    run.dependencies["routes"] = {ROUTE.route_id: {"model_id": ROUTE.model_id, "provider": ROUTE.provider}}
    move_to_units(run)
    monkeypatch.setattr("test_first_pass_units.DEPENDENCIES", run.dependencies)
    calls = []
    decision, units, _ = direct_units(monkeypatch, tmp_path, calls, ANSWER)
    # The pinned text, as the agent's instructions carry it (stripped at its ends).
    pinned = run.dependencies["prompts"][PromptName.FIRST_PASS_UNITS.value]["text"]
    assert calls[0][0].instructions == pinned.strip() and len(pinned.strip()) > 1_000
    assert decision.selected_observation_id is None and units.units


def test_the_workflow_moves_a_reopened_run_before_it_picks_its_step(tmp_path, monkeypatch):
    """Workflow._step calls move_to_units before next_step: the first step a resumed old-path run
    takes is its first pass."""
    repository, blobs, ident = stored(tmp_path)
    specimen = repository.get(SCOPE, ident)
    specimen.run.stage = "finalize"  # what a resume of a finalized run sets (api.py, action "resume")
    principal = SimpleNamespace(user_id=REVIEWER, scope=SCOPE, role="reviewer")
    repository.save(principal, specimen, specimen.version, "reopen", "reopen")
    adapters = Calls(blobs)
    picked = []
    next_step = Workflow.next_step
    monkeypatch.setattr(workflow_module.Workflow, "next_step", staticmethod(
        lambda run: picked.append((run.first_pass_path, next_step(run))) or next_step(run)))
    Workflow(repository, blobs, adapters).step(principal, ident)
    (region,) = specimen.run.regions
    assert picked[0] == (UNITS, f"first_pass:{region.id}")
    assert adapters.labels == [region.id]


# ---- What the move keeps, carries and drops (fix round 1 of PR #446: Codex's and G51's
# reviews of dbaeace10). Each test failed on dbaeace10.

def decide(http, ident, kind, target, after, key, reason="The person reads the label"):
    current = workspace(http, ident)
    return http.post(f"{PREFIX}/specimens/{ident}/decisions", headers={**HEADERS, "Idempotency-Key": key},
        json={"expected_revision": current["revision"], "base_record_version_id": current["record_version_id"],
            "kind": kind, "target_id": target, "after": after, "reason": reason})


def act(http, repository, ident, action, key):
    specimen = repository.get(SCOPE, ident)
    return http.post(f"{PREFIX}/runs/{specimen.run.id}/actions", headers={**HEADERS, "Idempotency-Key": key},
        json={"action": action, "reason": "The person reopens the record", "expected_revision": specimen.version})


@pytest.mark.parametrize("route", ["decision", "resume", "retry"])
def test_a_field_decision_the_record_cannot_prove_blocks_the_move_and_keeps_the_value(tmp_path, route):
    """A person's field decision is carried across the move as reprocess carries it to a new run
    (human_field_carry), proved from the server's save audits. The synthetic app's local
    repository holds none (test_human_field_carry_api.test_sqlite_event_alone_is_not_authoritative_carry_proof),
    so the move blocks the run, unmoved, with the person's value kept: on every route that
    reopens the run. Codex's route: a taxon decision reopens the run at lookup (api.py, kind field)."""
    repository, blobs, ident = stored(tmp_path)
    adapters = Calls(blobs)
    http = app(repository, adapters)
    field = "taxon" if route == "decision" else "country"
    response = decide(http, ident, "field", field, {"state": "supported", "literal": "Person value",
        "parsed": "Person value", "reason": "Read by the person"}, "field-decision")
    assert response.status_code == 200, response.text
    if route != "decision":
        assert act(http, repository, ident, route, route).status_code == 200

    run = repository.get(SCOPE, ident).run
    assert run.fields[field].literal == "Person value"
    assert (run.stage, run.blocker) == ("processing_blocked", "preserved_human_field_provenance_unavailable")
    assert run.first_pass_path == OLD and adapters.labels == []


@pytest.mark.parametrize("step", ["first_pass", "parse"])
def test_a_step_whose_attempts_the_old_path_used_has_its_allowance_again_after_the_move(tmp_path, step):
    """The move gives each step it runs again a fresh allowance of max_attempts
    (workflow.attempts_used) and keeps run.attempts counting, so each attempt's cost-ledger key,
    step:attempt, is new. Before, a first pass or an extraction at the cap was given up unsent."""

    class Extracting(Calls):
        extracts = 0

        def extract(self, specimen):
            Extracting.extracts += 1
            return None

    def at_the_cap(run):
        run.attempts[key(run)] = run.profile.execution.max_attempts

    def key(run):
        return f"first_pass:{run.regions[0].id}" if step == "first_pass" else "parse"

    repository, blobs, ident = stored(tmp_path, change=at_the_cap)
    adapters = Extracting(blobs)
    http = app(repository, adapters)
    assert act(http, repository, ident, "resume", "resume").status_code == 200

    specimen = repository.get(SCOPE, ident)
    completed_on_the_units_path(specimen, blobs, adapters.labels)
    run, cap = specimen.run, specimen.run.profile.execution.max_attempts
    assert run.attempts[key(run)] == cap + 1
    assert run.dependencies["attempts_at_units_move"][key(run)] == cap
    assert Extracting.extracts == 1


def test_the_move_drops_the_removed_first_passs_findings(tmp_path):
    """The old first pass's findings (rule first_pass_preference) go with it; nothing on the units
    path replaces them, and the app shows a warning finding as a note on its field. Other
    findings stay."""
    from specimen_digitization.application.domain import RunFinding

    def findings(run):
        region = run.regions[0].id
        run.findings += [RunFinding(rule_id="first_pass_preference", rule_version="field-research-first-pass-advice-v1",
                severity="warning", field_key="country", reason_code=f"first_pass_conflict:country:{region}"),
            RunFinding(rule_id="kept_rule", rule_version="v1", severity="info", field_key="country",
                reason_code="kept_code")]

    repository, blobs, ident = stored(tmp_path, change=findings)
    adapters = Calls(blobs)
    http = app(repository, adapters)
    assert act(http, repository, ident, "resume", "resume").status_code == 200

    specimen = repository.get(SCOPE, ident)
    completed_on_the_units_path(specimen, blobs, adapters.labels)
    assert [f.rule_id for f in specimen.run.findings if f.rule_id in {"first_pass_preference", "kept_rule"}] == [
        "kept_rule"]
    assert all(f["rule_id"] != "first_pass_preference" for f in workspace(http, ident)["run"]["findings"])


class FailingFirstPass(Calls):
    def first_pass_units(self, specimen, region, readings):
        from specimen_digitization.application.domain import LookupStatus
        from specimen_digitization.application.workflow import AdapterFailure

        self.labels.append(region.id)
        raise AdapterFailure("provider_timeout", LookupStatus.TIMEOUT)


def test_every_state_the_move_saves_passes_the_integrity_check(tmp_path):
    """The move keeps a person's transcripts with their text, state, name and reason, and drops
    the old first pass's machine transcripts, which adjudicate makes again: the run it saves
    before adjudicate (here its first pass failed and waits to be retried) passes the integrity
    check, so a reviewer's approval then blocks nothing."""
    repository, blobs, ident = stored(tmp_path)
    adapters = FailingFirstPass(blobs)
    http = app(repository, adapters)
    region = repository.get(SCOPE, ident).run.regions[0].id
    text = "taxon: as a person reads it"
    assert decide(http, ident, "transcription", region, {"text": text, "state": "supported"}, "edit").status_code == 200

    specimen = repository.get(SCOPE, ident)
    run = specimen.run
    assert (run.first_pass_path, run.stage, adapters.labels) == (UNITS, "retry_scheduled", [region])
    verify_evidence(specimen, blobs)
    assert decide(http, ident, "approve", ident, {}, "approve").status_code == 200
    assert repository.get(SCOPE, ident).run.blocker != "evidence_integrity_failure"
    [transcript] = run.transcripts
    assert (transcript.actor, transcript.text, transcript.differences, transcript.first_pass_call) == (
        REVIEWER, text, [], None)


def test_a_persons_decision_on_one_of_two_labels_stays_on_that_label(tmp_path):
    """adjudicate applies each person's decision to its own label (keyed by region): the other
    label is the units first pass's, naming no reading."""
    repository, blobs, ident = stored(tmp_path, TwoLabels)
    adapters = TwoLabels(blobs)
    http = app(repository, adapters)
    first, second = repository.get(SCOPE, ident).run.regions
    text = "taxon: as a person reads it"
    assert decide(http, ident, "transcription", second.id, {"text": text, "state": "supported"},
        "edit").status_code == 200

    specimen = repository.get(SCOPE, ident)
    run = specimen.run
    assert (run.first_pass_path, run.stage, run.blocker) == (UNITS, "finalized", None)
    assert sorted(adapters.labels) == sorted([first.id, second.id])
    transcripts = {t.region_id: t for t in run.transcripts}
    assert (transcripts[second.id].actor, transcripts[second.id].text) == (REVIEWER, text)
    assert transcripts[first.id].actor is None and transcripts[first.id].selected_observation_id is None
    units = {entry.label: entry for entry in run.reading_units}
    assert units[second.id] == alignment_units(second.id, [SimpleNamespace(id=PERSON, literal_text=text)])
    assert PERSON not in units[first.id].units[0].readers
    verify_evidence(specimen, blobs)


def test_an_abstention_on_an_old_path_label_stays_after_the_move(tmp_path):
    """A person's abstention (a state, no text) is a transcription decision: adjudicate applies it
    again, and the label keeps its readings' units (first_pass.source_units)."""
    repository, blobs, ident = stored(tmp_path)
    adapters = Calls(blobs)
    http = app(repository, adapters)
    region = repository.get(SCOPE, ident).run.regions[0].id
    assert decide(http, ident, "transcription", region, {"text": None, "state": "unreadable"},
        "abstain").status_code == 200

    specimen = repository.get(SCOPE, ident)
    run, _, transcript = completed_on_the_units_path(specimen, blobs, adapters.labels)
    assert (transcript.actor, transcript.text, transcript.resolved, transcript.value_state) == (
        REVIEWER, None, False, "unreadable")
    assert PERSON not in run.reading_units[0].units[0].readers


def test_a_run_holding_research_selections_is_not_moved(tmp_path):
    """A person's research-candidate selection (human_review_field_locks) is not carried, and
    reprocess refuses to drop one (api.py, action reprocess): the move blocks the run unmoved,
    the selection kept. A transcript edit drops the selections first (api.py, kind
    transcription), and then the run moves."""
    locks = {"country": {"selection_id": "selection-1"}}
    repository, blobs, ident = stored(tmp_path, change=lambda run: run.dependencies.update(
        human_review_field_locks=locks))
    adapters = Calls(blobs)
    http = app(repository, adapters)
    assert act(http, repository, ident, "resume", "resume").status_code == 200

    run = repository.get(SCOPE, ident).run
    assert (run.stage, run.blocker) == ("processing_blocked", "preserved_human_field_provenance_unavailable")
    assert run.first_pass_path == OLD and run.dependencies["human_review_field_locks"] == locks
    assert adapters.labels == []
