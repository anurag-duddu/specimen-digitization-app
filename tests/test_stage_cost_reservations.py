"""Real SQLite reservations and fixture effects; no prices or paid calls."""

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import ExecutionPolicy
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import SQLiteRepository, digest
from specimen_digitization.application.worker_launch import PilotAdmission, PilotLaunch
from specimen_digitization.application.workflow import OperationalBlock
from test_evidence_pilot import pilot, prepare_other_specimens


def cost_map():
    # Arbitrary fixture microdollars, deliberately not a provider price table.
    return {
        "version": "stage-cost-reservations-v1",
        "cost_micros": {
            "segment": 17,
            "transcribe:handwriting-qwen": 59,
            "transcribe:handwriting-muse": 89,
        },
    }


def mapped_pilot(tmp_path, monkeypatch, *, limit=1000):
    repo, principal, specimen, launch, workflow, calls = pilot(tmp_path, monkeypatch)
    launch = PilotLaunch.model_validate(
        dict(launch.model_dump(), stage_cost_reservations=cost_map())
    )
    for binding in launch.specimens:
        item = repo.get(principal.scope, binding.specimen_id)
        item.run.profile.execution = ExecutionPolicy.model_validate(
            dict(
                item.run.profile.execution.model_dump(),
                stage_cost_reservations=cost_map(),
                approved_cost_limit_micros=limit,
                request_cost_reservation_micros=999,  # Must never be the map fallback.
            )
        )
        repo.save(principal, item, item.version, "map-fixture", digest(cost_map()))
    specimen = repo.get(principal.scope, specimen.id)
    workflow.admission = PilotAdmission(repo, launch)
    return repo, principal, specimen, launch, workflow, calls


def run_to_block(workflow, principal, ident):
    for _ in range(12):
        result = workflow.step(principal, ident)
        if result.run.stage == "processing_blocked":
            return result
    pytest.fail("Fixture did not reach its retained review/budget boundary")


def test_exact_map_reserves_each_stage_before_effect_and_survives_restart(
    tmp_path, monkeypatch
):
    repo, principal, specimen, launch, workflow, _ = mapped_pilot(tmp_path, monkeypatch)
    prepare_other_specimens(principal, specimen.id, workflow)
    seen = []
    original_segment = workflow.adapters.segment
    original_read = workflow.adapters.transcribe

    def check(step, item):
        retained = repo.get(principal.scope, item.id)
        seen.append((step, retained.run.usage.reserved_cost_micros))
        assert retained.run.blocker == "external_outcome_unknown"

    def segment(item):
        check("segment", item)
        return original_segment(item)

    def read(item, region, route):
        check(route, item)
        return original_read(item, region, route)

    workflow.adapters.segment, workflow.adapters.transcribe = segment, read
    # Restart repository and admission after every durable step.
    for _ in range(10):
        result = workflow.step(principal, specimen.id)
        workflow.repository = SQLiteRepository(repo.path)
        workflow.admission = PilotAdmission(workflow.repository, launch)
        if result.run.stage == "processing_blocked":
            break
    assert seen == [
        ("segment", 17),
        ("handwriting-qwen", 76),
        ("handwriting-muse", 165),
    ]
    assert result.run.blocker == "pilot_evidence_review_required"
    assert result.run.usage.reserved_cost_micros == 165
    assert len(result.run.observations) == 2
    assert result.run.disposition is None


def test_entire_reading_cost_must_fit_before_first_effect(tmp_path, monkeypatch):
    repo, principal, specimen, launch, workflow, _ = mapped_pilot(
        tmp_path, monkeypatch, limit=200
    )
    prepare_other_specimens(principal, specimen.id, workflow)
    seen = []
    workflow.adapters.production.transcribe = lambda *args: seen.append(True)
    for _ in range(3):
        workflow.step(principal, specimen.id)
    with pytest.raises(
        OperationalBlock, match="pilot_cohort_reading_budget_insufficient"
    ):
        workflow.step(principal, specimen.id)
    result = repo.get(principal.scope, specimen.id)
    assert seen == []
    assert result.run.usage.reserved_cost_micros == 17
    assert not result.run.observations
    assert len(result.run.regions) == 1
    ledger = repo.document(
        principal.scope, "pilot_launch", workflow.admission.ledger_id
    )
    assert ledger["reading_cohort"]["state"] == "blocked"


def test_unknown_outcome_keeps_reservation_and_never_replays_after_restart(
    tmp_path, monkeypatch
):
    repo, principal, specimen, launch, workflow, _ = mapped_pilot(tmp_path, monkeypatch)
    prepare_other_specimens(principal, specimen.id, workflow)
    seen = []

    def unknown(*args):
        seen.append(True)
        raise AdapterFailure("fixture_unknown", outcome_unknown=True)

    workflow.adapters.production.transcribe = unknown
    result = run_to_block(workflow, principal, specimen.id)
    assert result.run.blocker == "external_outcome_unknown"
    assert result.run.usage.reserved_cost_micros == 76
    workflow.repository = SQLiteRepository(repo.path)
    workflow.admission = PilotAdmission(workflow.repository, launch)
    result = run_to_block(workflow, principal, specimen.id)
    assert seen == [True]
    assert result.run.usage.reserved_cost_micros == 76


@pytest.mark.parametrize("change", ["missing", "lower", "extra"])
def test_launch_and_run_map_must_match_exactly_before_any_effect(
    tmp_path, monkeypatch, change
):
    repo, principal, specimen, launch, workflow, calls = mapped_pilot(
        tmp_path, monkeypatch
    )
    value = cost_map()
    if change == "missing":
        value = None
    elif change == "lower":
        value["cost_micros"]["segment"] = 1
    else:
        value["cost_micros"]["parse"] = 1
    specimen = repo.get(principal.scope, specimen.id)
    specimen.run.profile.execution = ExecutionPolicy.model_validate(
        dict(specimen.run.profile.execution.model_dump(), stage_cost_reservations=value)
    )
    repo.save(principal, specimen, specimen.version, "changed-map", digest(value))
    with pytest.raises(OperationalBlock, match="stage_cost_reservations_mismatch"):
        workflow.step(principal, specimen.id)
    assert calls == []


def test_revised_launch_map_cannot_reset_the_existing_cohort_ledger(
    tmp_path, monkeypatch
):
    repo, principal, specimen, launch, workflow, _ = mapped_pilot(tmp_path, monkeypatch)
    workflow.admission.admit(repo.get(principal.scope, specimen.id))
    revised = cost_map()
    revised["cost_micros"]["segment"] = 1
    launch = PilotLaunch.model_validate(
        dict(launch.model_dump(), stage_cost_reservations=revised)
    )
    specimen = repo.get(principal.scope, specimen.id)
    specimen.run.profile.execution = ExecutionPolicy.model_validate(
        dict(
            specimen.run.profile.execution.model_dump(), stage_cost_reservations=revised
        )
    )
    with pytest.raises(
        OperationalBlock, match="launch_changed_requires_reconciliation"
    ):
        PilotAdmission(SQLiteRepository(repo.path), launch).admit(specimen)


@pytest.mark.parametrize("value", [0, -1, True, 1.2, 17.0, "17", None])
def test_map_values_are_strictly_positive_integer_microdollars(value):
    value_map = cost_map()
    value_map["cost_micros"]["segment"] = value
    with pytest.raises(ValidationError):
        ExecutionPolicy(stage_cost_reservations=value_map)


@pytest.mark.parametrize("change", ["version", "empty", "missing", "unknown"])
def test_map_enabled_pilot_requires_versioned_complete_exact_stage_set(
    tmp_path, monkeypatch, change
):
    _, _, _, launch, _, _ = pilot(tmp_path, monkeypatch)
    value = cost_map()
    if change == "version":
        value["version"] = "unreviewed"
    elif change == "empty":
        value["cost_micros"] = {}
    elif change == "missing":
        del value["cost_micros"]["transcribe:handwriting-muse"]
    else:
        value["cost_micros"]["unexpected"] = 1
    with pytest.raises(ValidationError):
        PilotLaunch.model_validate(
            dict(launch.model_dump(), stage_cost_reservations=value)
        )


def test_legacy_uniform_policy_and_launch_digest_do_not_gain_new_null_field(tmp_path):
    from test_worker_launch import fixture

    _, _, _, launch = fixture(tmp_path)
    assert "stage_cost_reservations" not in ExecutionPolicy().model_dump(mode="json")
    assert "stage_cost_reservations" not in launch.model_dump(mode="json")


def test_sql_snapshot_restores_exact_integer_costs_after_real_struct_transport(
    tmp_path, monkeypatch
):
    from google.protobuf import json_format
    from google.protobuf.struct_pb2 import Struct
    from specimen_digitization.application.production import SqlConnectRepository

    repo, principal, specimen, launch, workflow, _ = mapped_pilot(tmp_path, monkeypatch)
    specimen = repo.get(principal.scope, specimen.id)
    payload = specimen.model_dump(mode="json")
    transported = json_format.MessageToDict(json_format.ParseDict(payload, Struct()))
    assert (
        type(
            transported["run"]["profile"]["execution"]["stage_cost_reservations"][
                "cost_micros"
            ]["segment"]
        )
        is float
    )
    sql = SqlConnectRepository.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    restored = sql._snapshot({"snapshot": transported, "sha256": digest(payload)})
    assert (
        restored.run.profile.execution.stage_cost_reservations.cost_micros
        == cost_map()["cost_micros"]
    )
    assert all(
        type(value) is int
        for value in restored.run.profile.execution.stage_cost_reservations.cost_micros.values()
    )
    workflow.admission.admit(restored)
    assert digest(restored.run.profile.execution.model_dump(mode="json")) == digest(
        specimen.run.profile.execution.model_dump(mode="json")
    )


@pytest.mark.parametrize("value", [17.5, True, "17", float("inf"), 2**53])
def test_stored_cost_normalization_never_accepts_fractional_or_unsafe_values(value):
    value_map = cost_map()
    value_map["cost_micros"]["segment"] = value
    with pytest.raises(ValidationError):
        ExecutionPolicy.model_validate(
            {"stage_cost_reservations": value_map}, context={"persisted_snapshot": True}
        )
