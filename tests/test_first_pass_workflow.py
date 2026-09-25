"""The LLM first pass in the workflow (stage 6): docs/execution/golive/HARNESS.md section 4."""

import json
from types import SimpleNamespace

import pytest
from test_application import client, intake

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import (
    Principal,
    Run,
    Scope,
    StageCostReservations,
)
from specimen_digitization.application import model_runtime
from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.application.integrity import (
    EvidenceIntegrityError,
    verify_evidence,
)
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow


class ChoosingAdapters(SyntheticAdapters):
    """Synthetic readers that disagree, and a first pass that picks a reading the
    image supports at every difference (G19), or none."""

    def __init__(self, blobs, pick):
        super().__init__(blobs, SYNTHETIC_TEXT, "taxon: different")
        self.pick, self.first_passes = pick, []

    def first_pass(self, specimen, region, readings):
        self.first_passes.append(region.id)
        decision = super().first_pass(specimen, region, readings)
        chosen = self.pick(readings)
        if chosen is None:
            return decision
        return decision.model_copy(
            update={
                "selected_observation_id": chosen,
                "differences": [
                    d.model_copy(update={"verdict": chosen})
                    for d in decision.differences
                ],
            }
        )


def start(tmp_path, adapters):
    row = intake(client(tmp_path))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    return Workflow(repo, adapters.blobs, adapters), principal, specimen.id


def drain(tmp_path, adapters):
    workflow, principal, specimen_id = start(tmp_path, adapters)
    return workflow.drain(principal, specimen_id).run


def test_differing_readings_get_a_first_pass_before_adjudication(tmp_path):
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: r[1].id)

    run = drain(tmp_path, adapters)

    region, transcript = run.regions[0], run.transcripts[0]
    other, chosen = [o for o in run.observations if o.region_id == region.id]
    steps = run.completed_steps
    assert adapters.first_passes == [region.id]
    assert steps.index(f"first_pass:{region.id}") < steps.index("adjudicate")
    (decision,) = run.first_pass_decisions
    assert transcript.decision_kind == "first_pass"
    assert transcript.selected_observation_id == chosen.id
    assert transcript.text == chosen.literal_text and transcript.resolved
    assert transcript.first_pass_call == decision.call
    assert transcript.differences == decision.differences
    assert transcript.reason == decision.rationale
    assert transcript.alignment_status == "disagreement"
    assert [(h.observation_id, h.role, h.handed_text) for h in transcript.handoffs] == [
        (other.id, "raw_reading", other.literal_text),
        (chosen.id, "decided_transcript", chosen.literal_text),
    ]


def test_no_selection_hands_every_reading_to_the_harness_as_raw(tmp_path):
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: None)

    transcript = drain(tmp_path, adapters).transcripts[0]

    assert transcript.decision_kind == "first_pass"
    assert transcript.selected_observation_id is None and transcript.text is None
    assert not transcript.resolved
    assert [h.role for h in transcript.handoffs] == ["raw_reading", "raw_reading"]
    assert {(d.verdict, d.material) for d in transcript.differences} == {
        ("uncertain", True)
    }


class TamperingAdapters(ChoosingAdapters):
    """A first pass whose decision breaks its contract in one way."""

    def __init__(self, blobs, tamper):
        super().__init__(blobs, lambda r: None)
        self.tamper = tamper

    def first_pass(self, specimen, region, readings):
        decision = super().first_pass(specimen, region, readings)
        return self.tamper(decision, [o.id for o in readings])


def differences(decision, **update):
    return [d.model_copy(update=update) for d in decision.differences]


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d, ids: d.model_copy(update={"selected_observation_id": "unknown"}),
        lambda d, ids: d.model_copy(
            update={"differences": differences(d, verdict="unknown")}
        ),
        lambda d, ids: d.model_copy(update={"selected_observation_id": ids[1]}),
        lambda d, ids: d.model_copy(
            update={"differences": differences(d, material=False)}
        ),
        lambda d, ids: d.model_copy(update={"region_id": "region-2"}),
    ],
    ids=[
        "a pick naming no reading",
        "a verdict naming no reading",
        "a pick over an open material difference",
        "material flags the spans contradict",
        "another region",
    ],
)
def test_a_decision_breaking_its_contract_blocks_the_run(tmp_path, tamper):
    adapters = TamperingAdapters(LocalBlobs(tmp_path / "blobs"), tamper)

    run = drain(tmp_path, adapters)

    assert run.stage == "processing_blocked"
    assert run.blocker == "first_pass_contract_invalid"
    assert not run.first_pass_decisions and not run.transcripts


def test_a_first_pass_failing_before_it_returns_leaves_its_outcome_unknown(tmp_path):
    # Item 4 of the steward's review of #97: `first_pass:` is an external step, so
    # a failure before the call returns may follow an accepted, billable call.
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: None)

    def fail(specimen, region, readings):
        raise RuntimeError("connection reset after the request was sent")

    adapters.first_pass = fail

    run = drain(tmp_path, adapters)

    assert run.stage == "processing_blocked"
    assert run.blocker == "external_outcome_unknown"
    assert not run.first_pass_decisions


def test_a_billed_first_pass_reserves_before_its_call_which_is_no_reading(tmp_path):
    # Item 4 of the steward's review of #97: the step reserves its stage cost and
    # tokens and records its intent before the call, and the call's Observation is
    # the decision's, never one of the run's readings.
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: None)
    workflow, principal, specimen_id = start(tmp_path, adapters)
    repo = workflow.repository
    while not Workflow.next_step(repo.get(principal.scope, specimen_id).run).startswith(
        "first_pass:"
    ):
        workflow.step(principal, specimen_id)
    specimen = repo.get(principal.scope, specimen_id)
    profile = specimen.run.profile
    specimen.run.profile = profile.model_copy(
        update={
            "synthetic": False,
            "execution": profile.execution.model_copy(
                update={
                    "approved_cost_limit_micros": 10_000,
                    "stage_cost_reservations": StageCostReservations(
                        version="stage-cost-reservations-v1",
                        cost_micros={"first_pass": 900},
                    ),
                }
            ),
        }
    )
    repo.save(principal, specimen, specimen.version, "billed", digest({"billed": 1}))
    seen = []

    def first_pass(item, region, readings):
        retained = repo.get(principal.scope, item.id).run
        usage = retained.usage
        seen.append(
            (retained.blocker, usage.reserved_cost_micros, usage.reserved_tokens)
        )
        return synthetic_decision(adapters.blobs, region, readings)

    adapters.first_pass = first_pass

    run = workflow.step(principal, specimen_id).run

    assert seen == [("external_outcome_unknown", 900, 16000)]
    (decision,) = run.first_pass_decisions
    assert decision.call.id not in {o.id for o in run.observations}
    assert [o.route_id for o in run.observations] == list(run.profile.routes)


def test_identical_readings_skip_the_first_pass_and_are_recorded_as_before(tmp_path):
    adapters = SyntheticAdapters(LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT)

    run = drain(tmp_path, adapters)

    transcript = run.transcripts[0]
    first, second = [o for o in run.observations if o.region_id == transcript.region_id]
    assert not any(step.startswith("first_pass:") for step in run.completed_steps)
    assert not run.first_pass_decisions
    assert transcript.decision_kind == "identical_readings" and transcript.resolved
    assert transcript.selected_observation_id == first.id
    assert transcript.text == first.literal_text
    assert [(h.observation_id, h.role) for h in transcript.handoffs] == [
        (first.id, "decided_transcript"),
        (second.id, "raw_reading"),
    ]
    assert transcript.first_pass_call is None and transcript.reason is None


def forged_call(transcript, **update):
    call = transcript.first_pass_call.model_copy(update=update)
    return transcript.model_copy(update={"first_pass_call": call})


@pytest.mark.parametrize(
    "tamper",
    [
        lambda t: forged_call(t, raw_sha256="0" * 64),
        lambda t: forged_call(t, input_sha256="0" * 64),
        lambda t: forged_call(t, region_id="region-2"),
        lambda t: t.model_copy(update={"text": "forged"}),
        lambda t: t.model_copy(update={"selected_observation_id": "unknown"}),
    ],
    ids=[
        "the call's responses",
        "the call's input",
        "the call's region",
        "text other than the pick's literal",
        "a pick that is no reading",
    ],
)
def test_finalize_verifies_the_first_pass_call_and_its_pick(tmp_path, tamper):
    # The steward's review of #98: finalize checks the call and the pick before
    # the queue decision relies on them.
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: r[1].id)
    workflow, principal, specimen_id = start(tmp_path, adapters)
    specimen = workflow.drain(principal, specimen_id)
    verify_evidence(specimen, adapters.blobs)

    specimen.run.transcripts = [tamper(specimen.run.transcripts[0])]

    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(specimen, adapters.blobs)


def test_a_reviewer_changed_transcript_keeps_the_machine_pick_on_record(tmp_path):
    # A reviewer's transcription decision sets its own text and actor; the pick
    # the first pass made stays on the record as history.
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: r[1].id)
    workflow, principal, specimen_id = start(tmp_path, adapters)
    specimen = workflow.drain(principal, specimen_id)
    changed = specimen.run.transcripts[0].model_copy(
        update={"text": None, "resolved": False, "actor": "synthetic-reviewer"}
    )

    specimen.run.transcripts = [changed]

    verify_evidence(specimen, adapters.blobs)


def test_the_extraction_call_gets_no_raw_readings(monkeypatch, tmp_path):
    # Raw independent observations stay out of extraction context: a resolved
    # transcript goes without its handoffs, differences or first-pass call.
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: r[1].id)
    workflow, principal, specimen_id = start(tmp_path, adapters)
    specimen = workflow.drain(principal, specimen_id)
    fields = {k: v.model_dump(mode="json") for k, v in specimen.run.fields.items()}
    body = {"fields": fields, "evidence": [], "tokens": 0}
    result = SimpleNamespace(
        status="completed",
        cleanup_complete=True,
        value=json.dumps({"status": "completed", "value": body}).encode(),
    )
    sent = {}

    def isolated(function, payload, *args, **kwargs):
        sent.update(payload)
        return result

    monkeypatch.setattr(model_runtime, "run_isolated", isolated)

    model_runtime.invoke_model(
        SimpleNamespace(blobs=adapters.blobs, model_effect=None), specimen, "extract"
    )

    (transcript,) = sent["transcripts"]
    assert transcript["text"] == specimen.run.transcripts[0].text
    assert not {"handoffs", "differences", "first_pass_call"} & set(transcript)
