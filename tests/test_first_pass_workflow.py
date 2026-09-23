"""The LLM first pass in the workflow (stage 6): docs/execution/golive/HARNESS.md section 4."""

from test_application import client, intake

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import Principal, Run, Scope
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow


class ChoosingAdapters(SyntheticAdapters):
    """Synthetic readers that disagree, and a first pass that picks a reading."""

    def __init__(self, blobs, pick):
        super().__init__(blobs, SYNTHETIC_TEXT, "taxon: different")
        self.pick, self.first_passes = pick, []

    def first_pass(self, specimen, region, readings):
        self.first_passes.append(region.id)
        decision = super().first_pass(specimen, region, readings)
        return decision.model_copy(
            update={"selected_observation_id": self.pick(readings)}
        )


def drain(tmp_path, adapters):
    row = intake(client(tmp_path))
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repo.get(scope, row["specimen_id"])
    specimen.run = Run(profile=specimen.run.profile)
    repo.save(principal, specimen, specimen.version, "new-run", digest({"new": True}))
    return Workflow(repo, adapters.blobs, adapters).drain(principal, specimen.id).run


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


def test_a_decision_naming_an_unknown_reading_blocks_the_run(tmp_path):
    adapters = ChoosingAdapters(LocalBlobs(tmp_path / "blobs"), lambda r: "unknown")

    run = drain(tmp_path, adapters)

    assert run.stage == "processing_blocked"
    assert run.blocker == "first_pass_contract_invalid"
    assert not run.first_pass_decisions and not run.transcripts


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
