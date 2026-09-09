"""All frozen regions fit together without fictitious equal-size allocations."""

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import ExecutionPolicy, Region
from specimen_digitization.application.storage import SQLiteRepository, digest, Conflict
from specimen_digitization.application.worker_launch import PilotAdmission, PilotLaunch
from specimen_digitization.application.workflow import OperationalBlock
from test_cohort_reading_barrier import cohort, segment_all
from test_stage_cost_reservations import cost_map


def dynamic_cohort(tmp_path, monkeypatch, *, total=1798, attempts=1, reader_timeout=30):
    c = cohort(tmp_path, monkeypatch, timeout=120)
    c.launch.cohort_allocation_mode = "actual-regions-v1"
    c.launch.total_cost_limit_micros = total
    for binding in c.launch.specimens:
        item = c.repo.get(c.launch.scope, binding.specimen_id)
        item.run.profile.execution = ExecutionPolicy.model_validate(
            dict(
                item.run.profile.execution.model_dump(),
                max_attempts=attempts,
                reader_timeout_seconds=reader_timeout,
            )
        )
        c.repo.save(c.principal, item, item.version, "dynamic-policy", digest(attempts))
    PilotLaunch.model_validate(c.launch.model_dump())
    c.worker, c.flow = c.assemble(c.repo)
    original_segment = c.flow.adapters.segment
    last_id = c.launch.specimens[-1].specimen_id

    def segment(item):
        regions = original_segment(item)
        if item.id == last_id:
            regions.append(
                Region(
                    asset_id=item.asset.id,
                    x=1,
                    y=0,
                    width=50,
                    height=50,
                    order=1,
                    method="sam3",
                    version="local-fixture",
                )
            )
        return regions

    c.flow.adapters.segment = segment
    return c


def ledger(c):
    return c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)


@pytest.mark.parametrize("reader_timeout", [30, 45, 60])
def test_admitted_reader_schedule_finishes_near_launch_expiry(
    tmp_path, monkeypatch, reader_timeout
):
    c = dynamic_cohort(tmp_path, monkeypatch, reader_timeout=reader_timeout)
    segment = c.flow.adapters.segment
    reading_seconds = 15 + 22 * (reader_timeout + 1)
    c.launch.expires_at = c.clock[0] + timedelta(seconds=reading_seconds + 1)
    c.worker, c.flow = c.assemble(c.repo)
    c.flow.adapters.segment = segment
    segment_all(c)
    held = c.flow.admission.reserve_cohort_readings()
    assert held["reading_seconds"] == reading_seconds
    origin = c.clock[0]
    read = c.flow.adapters.production.transcribe

    def bounded_reader(*args):
        result = read(*args)
        c.clock[0] += timedelta(seconds=reader_timeout)
        return result

    c.flow.adapters.production.transcribe = bounded_reader
    for binding in c.launch.specimens:
        item = c.repo.get(c.launch.scope, binding.specimen_id)
        for _ in range(len(item.run.regions) * 2 + 1):
            c.flow.step(c.principal, binding.specimen_id)
            c.clock[0] += timedelta(seconds=1)
    assert (c.clock[0] - origin).total_seconds() == reading_seconds - 5
    assert c.worker.result_summary()["counts"] == {"review_required": 10}
    assert len([event for event in c.events if event[0] == "read"]) == 22
    # Completed snapshot rows retain the same nonzero safety margin.
    c.clock[0] = c.launch.expires_at - timedelta(seconds=5)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock, match="deadline"):
        c.flow.admission.admit(item)


@pytest.mark.parametrize("reader_timeout", [None, 30])
def test_short_reader_option_never_shortens_sam_admission(
    tmp_path, monkeypatch, reader_timeout
):
    c = dynamic_cohort(tmp_path, monkeypatch, reader_timeout=reader_timeout)
    c.launch.expires_at = c.clock[0] + timedelta(seconds=124)
    c.worker, c.flow = c.assemble(c.repo)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock, match="deadline"):
        c.flow.admission.admit(item)
    assert not c.events


def test_absent_reader_option_preserves_legacy_admission_tail(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch, reader_timeout=None)
    segment_all(c)
    c.clock[0] = c.launch.expires_at - timedelta(seconds=124)
    item = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock, match="deadline"):
        c.flow.admission.admit(item)
    assert not any(event[0] == "read" for event in c.events)


def test_dynamic_bootstrap_reserves_all_ten_sam_attempts_in_one_write(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    c.flow.admission.admit(first)
    held = ledger(c)
    assert held["revision"] == 1
    assert set(held["runs"]) == {b.specimen_id for b in c.launch.specimens}
    assert [r["cost_micros"] for r in held["runs"].values()] == [17] * 10
    assert not c.events


def test_uneven_eleven_regions_expand_one_cas_and_read_all_without_launch_change(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    original_digest = c.flow.admission.launch_digest
    segment_all(c)
    before = ledger(c)
    assert sum(r["cost_micros"] for r in before["runs"].values()) == 170
    held = c.flow.admission.reserve_cohort_readings()
    after = ledger(c)
    assert after["revision"] == before["revision"] + 1
    assert held["region_count"] == 11 and held["reading_count"] == 22
    assert held["reserved_cost_micros"] == 1628
    assert held["reading_seconds"] == 697
    assert sorted(r["cost_micros"] for r in after["runs"].values()) == [165] * 9 + [313]
    assert sum(r["cost_micros"] for r in after["runs"].values()) == 1798
    assert c.flow.admission.launch_digest == original_digest == after["launch_sha256"]
    for _ in range(6):
        worker, flow = c.assemble(SQLiteRepository(c.repo.path))
        for binding in c.launch.specimens:
            flow.step(c.principal, binding.specimen_id)
    reads = [x for x in c.events if x[0] == "read"]
    assert len(reads) == len(set(reads)) == 22
    assert worker.result_summary()["counts"] == {"review_required": 10}
    assert ledger(c)["runs"] == after["runs"]


def test_dynamic_short_budget_blocks_all_readers_without_partial_expansion(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch, total=1797)
    segment_all(c)
    before = ledger(c)
    with pytest.raises(OperationalBlock, match="cohort.*budget"):
        c.flow.admission.reserve_cohort_readings()
    after = ledger(c)
    assert after["runs"] == before["runs"]
    assert after["reading_cohort"]["state"] == "blocked"
    assert not any(e[0] == "read" for e in c.events)
    assert (
        sum(
            len(c.repo.get(c.launch.scope, b.specimen_id).run.regions)
            for b in c.launch.specimens
        )
        == 11
    )


def test_dynamic_bootstrap_checks_every_sam_allowance_before_first_effect(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch, total=170)
    last = c.repo.get(c.launch.scope, c.launch.specimens[-1].specimen_id)
    last.run.profile.execution.max_attempts = 2
    c.repo.save(c.principal, last, last.version, "larger-last-hold", digest("last"))
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock, match="budget"):
        c.flow.admission.admit(first)
    assert not c.events
    assert c.flow.admission._ledger()["runs"] == {}


def test_dynamic_unused_sam_attempt_allowances_are_never_released(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch, total=5394, attempts=3, reader_timeout=1)
    segment_all(c)
    before = ledger(c)
    assert sum(r["cost_micros"] for r in before["runs"].values()) == 510
    c.flow.admission.reserve_cohort_readings()
    assert sum(r["cost_micros"] for r in ledger(c)["runs"].values()) == 5394


@pytest.mark.parametrize(
    "change", ["smaller_hold", "larger_hold", "missing_hold", "policy"]
)
def test_dynamic_expanded_hold_or_policy_tamper_blocks_before_reader(
    tmp_path, monkeypatch, change
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.flow.admission.reserve_cohort_readings()
    state = ledger(c)
    ident = c.launch.specimens[0].specimen_id
    if change == "policy":
        item = c.repo.get(c.launch.scope, ident)
        item.run.profile.execution.reader_timeout_seconds = 20
        c.repo.save(c.principal, item, item.version, "policy-drift", digest(change))
    else:
        if change == "missing_hold":
            del state["runs"][ident]
        else:
            state["runs"][ident]["cost_micros"] += 1 if change == "larger_hold" else -1
        c.repo.put_document(
            c.launch.scope,
            "pilot_launch",
            c.flow.admission.ledger_id,
            {k: v for k, v in state.items() if k != "revision"},
            state["revision"],
        )
    _, restarted = c.assemble(SQLiteRepository(c.repo.path))
    with pytest.raises(OperationalBlock):
        restarted.step(c.principal, ident)
    assert not any(e[0] == "read" for e in c.events)


def test_dynamic_concurrent_expansion_commits_once(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    before = ledger(c)
    barrier = threading.Barrier(2)
    original = PilotAdmission._write

    def race(self, current, **updates):
        if "reading_cohort" in updates:
            barrier.wait(timeout=5)
        return original(self, current, **updates)

    monkeypatch.setattr(PilotAdmission, "_write", race)

    def reserve(_):
        try:
            return PilotAdmission(
                SQLiteRepository(c.repo.path), c.launch, clock=lambda: c.clock[0]
            ).reserve_cohort_readings()
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count("conflict") == 1
    after = ledger(c)
    assert after["revision"] == before["revision"] + 1
    assert sum(r["cost_micros"] for r in after["runs"].values()) == 1798
    assert not any(e[0] == "read" for e in c.events)


@pytest.mark.parametrize("mode_change", ["no_evidence", "no_map", "unknown"])
def test_dynamic_mode_requires_evidence_only_and_exact_stage_map(
    tmp_path, monkeypatch, mode_change
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    value = c.launch.model_dump()
    if mode_change == "no_evidence":
        value.update(evidence_only=False, evidence_profile_sha256=None)
    elif mode_change == "no_map":
        value["stage_cost_reservations"] = None
    else:
        value["cohort_allocation_mode"] = "unreviewed"
    with pytest.raises(ValidationError):
        PilotLaunch.model_validate(value)


@pytest.mark.parametrize("value", [0, -1, 121, float("inf"), float("nan"), True])
def test_invalid_reader_timeout_is_rejected(value):
    with pytest.raises(ValidationError):
        ExecutionPolicy(reader_timeout_seconds=value)


@pytest.mark.parametrize("timeout", [30, 45, 60])
def test_reader_timeout_is_step_specific_and_serialized(timeout):
    policy = ExecutionPolicy(reader_timeout_seconds=timeout)
    assert (
        policy.effect_timeout_for_step("transcribe:region:handwriting-qwen") == timeout
    )
    assert policy.effect_timeout_for_step("segment") == 120
    assert policy.effect_timeout_for_step("parse") == 120
    assert policy.model_dump(mode="json")["reader_timeout_seconds"] == timeout


def test_absent_optional_contracts_keep_legacy_payload_and_hash(tmp_path):
    from test_worker_launch import fixture

    _, _, _, launch = fixture(tmp_path)
    assert "cohort_allocation_mode" not in launch.model_dump(mode="json")
    assert "reader_timeout_seconds" not in ExecutionPolicy().model_dump(mode="json")
    assert ExecutionPolicy(reader_timeout_seconds=None).model_dump(
        mode="json"
    ) == ExecutionPolicy().model_dump(mode="json")
    assert PilotLaunch.model_validate(
        dict(launch.model_dump(), cohort_allocation_mode=None)
    ).model_dump(mode="json") == launch.model_dump(mode="json")


def test_default_policy_matches_pre_change_hash():
    # Literal pre-change serialization avoids confusing a golden hash with a credential.
    import json

    golden = (
        '{"version":"execution-safety-v1","max_steps":200,"max_external_calls":32,'
        '"max_tokens":160000,"max_active_seconds":3600.0,"external_timeout_seconds":120.0,'
        '"lease_seconds":180.0,"max_attempts":3,"approved_cost_limit_micros":null,'
        '"request_cost_reservation_micros":null}'
    )
    assert ExecutionPolicy().model_dump_json() == golden
    assert digest(ExecutionPolicy().model_dump(mode="json")) == digest(json.loads(golden))



@pytest.mark.parametrize("boundary", ["bootstrap", "expansion"])
def test_dynamic_lost_cas_response_retains_complete_holds_and_starts_no_reader(
    tmp_path, monkeypatch, boundary
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    if boundary == "expansion":
        segment_all(c)
    original = c.flow.admission._write
    raised = []

    def lose(current, **updates):
        original(current, **updates)
        matches = (
            "reading_cohort" in updates
            if boundary == "expansion"
            else "runs" in updates
        )
        if matches and not raised:
            raised.append(True)
            raise ConnectionError("Committed local CAS lost its response")

    monkeypatch.setattr(c.flow.admission, "_write", lose)
    c.worker.tick()
    before = ledger(c)
    assert len(before["runs"]) == 10
    assert sum(r["cost_micros"] for r in before["runs"].values()) == (
        1798 if boundary == "expansion" else 170
    )
    assert not any(e[0] == "read" for e in c.events)
    restarted, _ = c.assemble(SQLiteRepository(c.repo.path))
    restarted.tick()
    assert ledger(c)["runs"] == before["runs"]
    assert not any(e[0] == "read" for e in c.events)


def test_dynamic_unknown_reader_preserves_expanded_holds_and_never_replays(
    tmp_path, monkeypatch
):
    from specimen_digitization.application.reliability import AdapterFailure

    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    calls = []

    def unknown(*args):
        calls.append(True)
        raise AdapterFailure("fixture_unknown", outcome_unknown=True)

    c.flow.adapters.production.transcribe = unknown
    c.worker.tick()
    before = ledger(c)
    assert calls == [True]
    assert sum(r["cost_micros"] for r in before["runs"].values()) == 1798
    assert sum(sum(v.values()) for v in before["reader_claims"].values()) == 1
    restarted, _ = c.assemble(SQLiteRepository(c.repo.path))
    for _ in range(12):
        restarted.tick()
    assert ledger(c)["runs"] == before["runs"]
    assert ledger(c)["reader_claims"] == before["reader_claims"]
    assert not any(e[0] == "read" for e in c.events)


def test_dynamic_reservation_survives_struct_float_transport(tmp_path, monkeypatch):
    from google.protobuf import json_format
    from google.protobuf.struct_pb2 import Struct

    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.flow.admission.reserve_cohort_readings()
    original = c.repo.document

    def transported(*args):
        return json_format.MessageToDict(
            json_format.ParseDict(original(*args), Struct())
        )

    monkeypatch.setattr(c.repo, "document", transported)
    c.flow.admission.reserve_cohort_readings()
    c.flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert len([e for e in c.events if e[0] == "read"]) == 1
    assert sum(r["cost_micros"] for r in ledger(c)["runs"].values()) == 1798


@pytest.mark.parametrize("elapsed, accepted", [(803, True), (804, False)])
def test_dynamic_reader_budget_uses_remaining_original_window(
    tmp_path, monkeypatch, elapsed, accepted
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.clock[0] += timedelta(seconds=elapsed)
    if accepted:
        assert c.flow.admission.reserve_cohort_readings()["reading_seconds"] == 697
    else:
        with pytest.raises(OperationalBlock, match="cohort.*time"):
            c.flow.admission.reserve_cohort_readings()
        assert sum(r["cost_micros"] for r in ledger(c)["runs"].values()) == 170
    assert not any(e[0] == "read" for e in c.events)


def test_late_reader_result_keeps_resolved_timeout_and_unknown_cost(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    mono = [0]
    c.flow.monotonic = lambda: mono[0]
    read = c.flow.adapters.production.transcribe
    observed = []

    def late(item, region, route):
        observed.append(item.run.usage.reserved_active_seconds)
        mono[0] = 31
        return read(item, region, route)

    c.flow.adapters.production.transcribe = late
    first = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, first)
    result = c.repo.get(c.launch.scope, first)
    assert observed == [30]
    assert result.run.blocker == "external_outcome_unknown"
    assert result.run.usage.reserved_active_seconds == 30
    assert result.run.usage.reserved_cost_micros == 76
    assert not result.run.observations
    assert sum(r["cost_micros"] for r in ledger(c)["runs"].values()) == 1798


def test_sam_keeps_120_second_effect_budget_when_reader_is_30(tmp_path, monkeypatch):
    c = dynamic_cohort(tmp_path, monkeypatch)
    mono = [0]
    c.flow.monotonic = lambda: mono[0]
    segment = c.flow.adapters.segment
    held = []

    def sam(item):
        held.append(item.run.usage.reserved_active_seconds)
        mono[0] += 31
        return segment(item)

    c.flow.adapters.segment = sam
    first = c.launch.specimens[0].specimen_id
    for _ in range(3):
        c.flow.step(c.principal, first)
    result = c.repo.get(c.launch.scope, first)
    assert held == [120]
    assert "segment" in result.run.completed_steps and result.run.blocker is None
    assert result.run.usage.reserved_active_seconds == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("runs", []),
        ("runs", None),
        (
            "reading_cohort",
            {
                "state": "reserved",
                "identity": {},
                "identity_sha256": digest({}),
                "allocations": [],
            },
        ),
    ],
)
def test_dynamic_malformed_retained_phase_is_not_recreated(
    tmp_path, monkeypatch, field, value
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    c.flow.admission.admit(first)
    state = ledger(c)
    state[field] = value
    c.repo.put_document(
        c.launch.scope,
        "pilot_launch",
        c.flow.admission.ledger_id,
        {k: v for k, v in state.items() if k != "revision"},
        state["revision"],
    )
    before = ledger(c)
    with pytest.raises(OperationalBlock):
        c.flow.admission.admit(first)
    assert ledger(c) == before
    assert not c.events


def test_changed_other_baseline_row_blocks_before_current_specimen_sam(
    tmp_path, monkeypatch
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    c.flow.admission.admit(first)
    state = ledger(c)
    state["runs"][c.launch.specimens[-1].specimen_id]["cost_micros"] -= 1
    c.repo.put_document(
        c.launch.scope,
        "pilot_launch",
        c.flow.admission.ledger_id,
        {k: v for k, v in state.items() if k != "revision"},
        state["revision"],
    )
    with pytest.raises(OperationalBlock):
        for _ in range(3):
            c.flow.step(c.principal, first.id)
    assert not c.events


@pytest.mark.parametrize("tamper", ["other_hold", "other_formula", "baseline_hash"])
def test_complete_expanded_ledger_is_checked_during_each_admission(
    tmp_path, monkeypatch, tamper
):
    c = dynamic_cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.flow.admission.reserve_cohort_readings()
    state = ledger(c)
    last = c.launch.specimens[-1].specimen_id
    if tamper == "other_hold":
        state["runs"][last]["cost_micros"] -= 1
    elif tamper == "other_formula":
        state["reading_cohort"]["identity"]["specimens"][last]["reader_cost_micros"][
            "handwriting-qwen"
        ] -= 1
        state["reading_cohort"]["identity_sha256"] = digest(
            state["reading_cohort"]["identity"]
        )
        state["reading_cohort"]["allocations"][last]["reading_cost_micros"] -= 2
        state["runs"][last]["cost_micros"] -= 2
    else:
        state["allocation_baseline_sha256"] = "0" * 64
    c.repo.put_document(
        c.launch.scope,
        "pilot_launch",
        c.flow.admission.ledger_id,
        {k: v for k, v in state.items() if k != "revision"},
        state["revision"],
    )
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock):
        c.flow.admission.admit(first)
    assert not any(e[0] == "read" for e in c.events)
