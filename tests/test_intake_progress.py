"""Intake's summary reports saved milestones without changing a run."""

import pytest

from specimen_digitization.application.api import summary
from specimen_digitization.application.domain import Asset, Disposition, Region, Run, Scope, Specimen
from specimen_digitization.application.intake_progress import intake_progress


PREP = ["pin_dependencies", "classify", "quality_check", "segment"]


def run_with_readers():
    run = Run(completed_steps=PREP.copy())
    run.regions = [Region(id="label", asset_id="photo", x=0, y=0, width=1, height=1,
                          order=0, method="test", version="1")]
    return run


def test_reading_waits_for_every_route_and_region():
    run = run_with_readers()
    assert len(run.profile.routes) == 2
    run.completed_steps.append(f"transcribe:label:{run.profile.routes[0]}")
    assert intake_progress(run)["completed_stages"] == ["segment"]
    assert intake_progress(run)["next_step"] == "transcribe"
    run.completed_steps.append(f"transcribe:label:{run.profile.routes[1]}")
    assert intake_progress(run)["completed_stages"] == ["segment", "read"]
    assert intake_progress(run)["next_step"] == "adjudicate"


@pytest.mark.parametrize("state", ["retry_scheduled", "processing_blocked", "paused", "cancelled"])
def test_operational_state_does_not_erase_work_or_invent_it(state):
    run = Run(stage=state, completed_steps=PREP + ["adjudicate", "parse"],
              next_retry_at="2026-10-12T19:20:00+00:00")
    before = run.model_dump_json()
    progress = intake_progress(run)
    assert progress["next_step"] == "plan"
    assert progress["completed_stages"] == ["segment", "compare", "extract"]
    assert progress["next_retry_at"] == (run.next_retry_at if state == "retry_scheduled" else None)
    assert run.model_dump_json() == before


def test_pending_does_not_claim_work_and_early_disposition_does_not_complete_track():
    run = Run(stage="pending")
    assert intake_progress(run)["completed_stages"] == []
    run.disposition = Disposition.DEFERRED
    progress = intake_progress(run)
    assert progress["next_step"] is None
    assert progress["completed_stages"] == []


def test_no_regions_does_not_claim_reading_and_pilot_does_not_infer_ordinary_steps():
    run = Run(stage="transcribe", completed_steps=["quality_check", "segment"],
              dependencies={"evidence_pilot": {}})
    assert intake_progress(run)["completed_stages"] == ["segment"]
    assert intake_progress(run)["next_step"] == "transcribe"
    run.stage = "processing_blocked"
    assert intake_progress(run)["next_step"] is None


@pytest.mark.parametrize("marker", ["validate", "field_research"])
def test_both_research_paths_report_saved_completion(marker):
    run = Run(stage="finalized", completed_steps=[marker], disposition=Disposition.REVIEW)
    assert intake_progress(run)["completed_stages"] == ["research", "finalize"]


def specimen_for(run):
    return Specimen(scope=Scope(organization_id="org", collection_id="collection"), run=run,
        asset=Asset(sha256="a" * 64, blob_ref="photo", media_type="image/png", size_bytes=1,
                    width=1, height=1, filename="photo.png", uploader="operator"))


ALL_BEFORE_AUTHORITY = PREP + ["adjudicate", "parse", "plan", "lookup"]


@pytest.mark.parametrize("plan", [[{}], [{"tool": "gbif"}]])
@pytest.mark.parametrize("stage", ["paused", "cancelled", "finalized", "processing_blocked"])
def test_malformed_legacy_terminal_run_still_summarises(stage, plan):
    # Legacy runs can carry an authority plan the workflow cannot walk.
    run = Run(stage=stage, completed_steps=ALL_BEFORE_AUTHORITY.copy(), authority_plan=plan)
    specimen = specimen_for(run)
    before = specimen.model_dump_json()
    result = summary(specimen, "operator")
    assert result["stage"] == stage
    progress = result["intake_progress"]
    assert progress["next_step"] is None
    assert progress["completed_stages"][:3] == ["segment", "compare", "extract"]
    assert specimen.model_dump_json() == before


def test_summary_adds_bounded_projection_without_altering_actions_or_old_fields():
    run = run_with_readers()
    run.stage = "retry_scheduled"
    run.next_retry_at = "2026-10-12T19:20:00+00:00"
    specimen = Specimen(scope=Scope(organization_id="org", collection_id="collection"), run=run,
        asset=Asset(sha256="a" * 64, blob_ref="photo", media_type="image/png", size_bytes=1,
                    width=1, height=1, filename="photo.png", uploader="operator"))
    before = specimen.model_dump_json()
    result = summary(specimen, "operator")
    assert result["stage"] == result["status"] == "retry_scheduled"
    assert result["available_actions"] == ["retry", "resume", "pause", "cancel", "reprocess"]
    assert result["intake_progress"] == {
        "next_step": "transcribe", "completed_stages": ["segment"],
        "next_retry_at": run.next_retry_at,
    }
    assert specimen.model_dump_json() == before
