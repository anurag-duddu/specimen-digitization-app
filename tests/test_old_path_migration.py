"""WP 1.8 part B of docs/execution/units/PLAN.md: a run the old first pass processed, reopened
after the old path's removal, is moved to the units path (workflow.move_to_units).

stored() builds such a run in the shape origin/main d83f4d6f1 stored one (the old first pass is
gone, so it cannot run here): the synthetic specimen, its readers differing at the taxon line,
drained through the synthetic API, then recorded as the old path recorded a run whose first pass
picked reader 1. Its path is the stored default `old` (no first_pass_path key); it has no reading
units; its first-pass decision selects reader 1, every verdict naming it; its transcript is
`first_pass`, reader 1's text, resolved, with reader 1 the decided transcript and reader 2 raw;
and its pins hold the old first pass's prompt and not the units prompt. The integrity check
holds it to the old path's checks (integrity.verify_evidence, first_pass.g19_pick). A run main
stored so (~/specimen-golive/units-program/wp18/old_path_completed_run.json, made there by
make_old_path_fixture.py) passed this module's tests too, off the repository, where its digests
are not committed. The synthetic app drains a resumed run in-process (api.schedule_local), as
the worker does in production."""

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


def app(repository, adapters):
    """The synthetic-mode app over the repository: a run a request resumes drains in-process."""
    return TestClient(create_app(mode="synthetic", repository=repository, blobs=adapters.blobs, adapters=adapters,
        token=TOKEN), raise_server_exceptions=False)


def stored(tmp_path):
    """The repository and blobs under tmp_path holding one finalized run of the old path (module
    docstring), and its specimen's id."""
    from test_application import intake

    from specimen_digitization.application.domain import ReaderHandoff
    from specimen_digitization.application.storage import digest

    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    adapters = SyntheticAdapters(blobs, SYNTHETIC_TEXT, ALTERNATE)
    ident = intake(app(repository, adapters))["specimen_id"]
    specimen = repository.get(SCOPE, ident)
    run = specimen.run
    assert (run.stage, run.first_pass_path) == ("finalized", UNITS)
    (region,) = run.regions
    first, second = [o for o in run.observations if o.region_id == region.id]
    (decision,) = run.first_pass_decisions
    picked = decision.model_copy(update={"selected_observation_id": first.id,
        "differences": [d.model_copy(update={"verdict": first.id}) for d in decision.differences]})
    run.first_pass_decisions = [picked]
    (transcript,) = run.transcripts
    run.transcripts = [transcript.model_copy(update={"decision_kind": "first_pass",
        "selected_observation_id": first.id, "text": first.literal_text, "resolved": True,
        "differences": picked.differences, "first_pass_call": picked.call,
        "handoffs": [ReaderHandoff(observation_id=first.id, role="decided_transcript", handed_text=first.literal_text),
            ReaderHandoff(observation_id=second.id, role="raw_reading", handed_text=second.literal_text)]})]
    run.reading_units = []
    prompts = run.dependencies.get("prompts")
    if isinstance(prompts, dict):
        prompts.pop(PromptName.FIRST_PASS_UNITS.value, None)
        prompts["transcription-disagreement-adjudication"] = {"text": "the old first pass's prompt"}
    run.first_pass_path = OLD
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
