"""The entire frozen cohort must fit before any local fixture reader is invoked."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import ExecutionPolicy, Region
from specimen_digitization.application.evidence_pilot import EvidencePilotWorkflow
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import (
    SQLiteRepository,
    LocalBlobs,
    digest,
    Conflict,
)
from specimen_digitization.application.worker import PilotWorker
from specimen_digitization.application.worker_launch import PilotAdmission
from specimen_digitization.application.workflow import OperationalBlock
from test_evidence_pilot import pilot, FixtureProvider
from test_stage_cost_reservations import cost_map
from test_application import image_bytes


def cohort(tmp_path, monkeypatch, *, regions=1, limit=1000, timeout=120):
    repo, principal, first, launch, original, _ = pilot(tmp_path, monkeypatch)
    launch.stage_cost_reservations = ExecutionPolicy(
        stage_cost_reservations=cost_map()
    ).stage_cost_reservations
    launch.per_specimen_cost_limit_micros = limit
    launch.total_cost_limit_micros = 10 * limit
    launch.per_specimen_call_limit = 1000
    launch.per_specimen_token_limit = 10000000
    blobs = LocalBlobs(tmp_path / "cohort-blobs")
    for index, binding in enumerate(launch.specimens):
        specimen = repo.get(launch.scope, binding.specimen_id)
        # Generated PNG fixture bytes only; no museum image or network input.
        raw = image_bytes() + f"\nlocal-fixture-{index}".encode()
        checksum = blobs.put(raw)
        specimen.asset.sha256 = binding.asset_sha256 = checksum
        specimen.asset.blob_ref = binding.blob_ref = checksum + ":123"
        specimen.asset.size_bytes = len(raw)
        specimen.run.profile.execution = ExecutionPolicy(
            stage_cost_reservations=cost_map(),
            approved_cost_limit_micros=limit,
            max_external_calls=1000,
            max_tokens=10000000,
            max_active_seconds=100000,
            external_timeout_seconds=timeout,
        )
        repo.save(
            principal, specimen, specimen.version, "cohort-fixture", digest(checksum)
        )
    get_blob = blobs.get
    blobs.get = lambda ref: get_blob(ref.split(":")[0])
    events = []
    clock = [datetime.now(timezone.utc)]

    def assemble(repository):
        admission = PilotAdmission(repository, launch, clock=lambda: clock[0])
        provider = FixtureProvider(blobs)
        original_read = provider.transcribe

        def read(specimen, region, route):
            events.append(("read", specimen.id, region.id, route))
            return original_read(specimen, region, route)

        provider.transcribe = read
        flow = EvidencePilotWorkflow(
            repository,
            blobs,
            admission,
            original.pilot_profile,
            production=provider,
            clock=lambda: clock[0],
        )

        def segment(specimen):
            events.append(("segment", specimen.id))
            retained = [
                Region(
                    asset_id=specimen.asset.id,
                    x=i,
                    y=0,
                    width=50,
                    height=50,
                    order=i,
                    method="sam3",
                    version="local-fixture",
                )
                for i in range(regions)
            ]
            raw = json.dumps([r.model_dump(mode="json") for r in retained]).encode()
            specimen.run.segmentation = {
                "blob_ref": blobs.put(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "input_sha256": specimen.asset.sha256,
                "validation": "valid",
                "model_id": "facebook/sam3",
                "model_revision": original.pilot_profile.segmentation_settings.model_revision,
                "request_sha256": digest(
                    {"specimen_id": specimen.id, "run_id": specimen.run.id}
                ),
                "settings": original.pilot_profile.segmentation_settings.model_dump(
                    mode="json"
                ),
            }
            return retained

        flow.adapters.segment = segment
        worker = PilotWorker(
            repository,
            flow,
            principal.user_id,
            lambda uid: [dict(principal.scope.model_dump(), role="reviewer")],
            admission,
        )
        return worker, flow

    worker, flow = assemble(repo)
    return SimpleNamespace(
        repo=repo,
        principal=principal,
        launch=launch,
        flow=flow,
        worker=worker,
        events=events,
        clock=clock,
        assemble=assemble,
    )


def segment_all(c):
    for binding in c.launch.specimens:
        for _ in range(3):
            c.flow.step(c.principal, binding.specimen_id)
        assert (
            "segment"
            in c.repo.get(c.launch.scope, binding.specimen_id).run.completed_steps
        )
    assert not any(event[0] == "read" for event in c.events)


def test_late_tenth_segmentation_prevents_every_reader(tmp_path, monkeypatch):
    from specimen_digitization.application.domain import LookupStatus

    c = cohort(tmp_path, monkeypatch, timeout=1)
    last = c.launch.specimens[-1].specimen_id
    segment = c.flow.adapters.segment

    def delayed(specimen):
        if specimen.id == last:
            raise AdapterFailure(
                "fixture_pending", LookupStatus.RATE_LIMITED, retry_after_seconds=60
            )
        return segment(specimen)

    c.flow.adapters.segment = delayed
    for _ in range(45):
        c.worker.tick()
    assert len([e for e in c.events if e[0] == "segment"]) == 9
    assert not any(e[0] == "read" for e in c.events)
    assert c.worker.result_summary()["status"] == "incomplete"


def test_complete_cohort_reservation_precedes_reader_and_survives_restart(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, regions=2, timeout=1)
    segment_all(c)
    before = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    first = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, first)
    ledger = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    reservation = ledger["reading_cohort"]
    assert reservation["state"] == "reserved"
    assert reservation["region_count"] == 20
    assert reservation["reading_count"] == 40
    assert reservation["reserved_cost_micros"] == 20 * (59 + 89) * 3
    assert (
        ledger["runs"] == before["runs"]
    ), "existing whole-run allocations must not be charged a second time"
    for _ in range(100):
        repo = SQLiteRepository(c.repo.path)
        worker, flow = c.assemble(repo)
        # Every restart may select the same first ID; completed reading work
        # remains in the same durable records and must never be replayed.
        for binding in c.launch.specimens:
            flow.step(c.principal, binding.specimen_id)
        if worker.result_summary()["status"] == "evidence_review_required":
            break
    reads = [event for event in c.events if event[0] == "read"]
    assert len(reads) == len(set(reads)) == 40
    assert (
        c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)[
            "reading_cohort"
        ]
        == reservation
    )


def test_insufficient_full_cost_retains_all_regions_and_stops_before_readers(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, limit=400, timeout=1)
    segment_all(c)
    with pytest.raises(OperationalBlock, match="cohort.*budget"):
        c.flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(e[0] == "read" for e in c.events)
    assert all(
        len(c.repo.get(c.launch.scope, b.specimen_id).run.regions) == 1
        for b in c.launch.specimens
    )
    ledger = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert ledger["reading_cohort"]["state"] == "blocked"
    assert sum(row["cost_micros"] for row in ledger["runs"].values()) == 4000
    assert c.worker.result_summary()["status"] == "incomplete"


@pytest.mark.parametrize("drift", ["region", "provenance", "generation", "route"])
def test_drift_after_reservation_blocks_direct_reader_and_restart(
    tmp_path, monkeypatch, drift
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    c.flow.admission.reserve_cohort_readings()
    last = c.repo.get(c.launch.scope, c.launch.specimens[-1].specimen_id)
    if drift == "region":
        last.run.regions[0].x += 1
    elif drift == "provenance":
        last.run.segmentation["request_sha256"] = "0" * 64
    elif drift == "generation":
        last.asset.blob_ref = last.asset.sha256 + ":124"
    else:
        last.run.profile.routes = ("handwriting-muse", "handwriting-qwen")
    c.repo.save(c.principal, last, last.version, "drift-fixture", digest(drift))
    worker, flow = c.assemble(SQLiteRepository(c.repo.path))
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    with pytest.raises(OperationalBlock):
        flow.adapters.transcribe(
            first, first.run.regions[0], first.run.profile.routes[0]
        )
    worker.tick()
    assert not any(event[0] == "read" for event in c.events)


def test_concurrent_cohort_admission_keeps_one_existing_allocation(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    initial = c.repo.document(
        c.launch.scope, "pilot_launch", c.flow.admission.ledger_id
    )
    barrier = threading.Barrier(2)
    original_write = PilotAdmission._write

    def racing_write(self, ledger, **updates):
        if "reading_cohort" in updates:
            barrier.wait(timeout=5)
        return original_write(self, ledger, **updates)

    monkeypatch.setattr(PilotAdmission, "_write", racing_write)

    def reserve(_):
        admission = PilotAdmission(SQLiteRepository(c.repo.path), c.launch)
        try:
            return admission.reserve_cohort_readings()
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(reserve, range(2)))
    ledger = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert ledger["revision"] == initial["revision"] + 1
    assert ledger["runs"] == initial["runs"]
    assert ledger["reading_cohort"]["reserved_cost_micros"] == 10 * 3 * (59 + 89)


def test_consumed_reader_liability_cannot_be_reset_before_restart(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    ident = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, ident)
    before = list(c.events)
    item = c.repo.get(c.launch.scope, ident)
    item.run.attempts = {
        key: value
        for key, value in item.run.attempts.items()
        if not key.startswith("transcribe:")
    }
    item.run.usage.reserved_cost_micros = 17
    c.repo.save(
        c.principal,
        item,
        item.version,
        "invalid-counter-reset",
        digest("counter-reset"),
    )
    _, restarted = c.assemble(SQLiteRepository(c.repo.path))
    with pytest.raises(OperationalBlock, match="cohort.*liability"):
        restarted.step(c.principal, ident)
    assert c.events == before


def test_known_reader_retry_uses_reserved_attempts_without_a_second_cohort_debit(
    tmp_path, monkeypatch
):
    from specimen_digitization.application.domain import LookupStatus

    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    provider = c.flow.adapters.production
    read = provider.transcribe
    attempts = []

    def retry(item, region, route):
        attempts.append(route)
        if len(attempts) == 1:
            raise AdapterFailure(
                "fixture_retry", LookupStatus.RATE_LIMITED, retry_after_seconds=1
            )
        return read(item, region, route)

    provider.transcribe = retry
    first = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, first)
    ledger = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    held = ledger["reading_cohort"]
    for _ in range(5):
        c.clock[0] += timedelta(seconds=60)
        c.flow.step(c.principal, first)
    after = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert after["reading_cohort"] == held and after["runs"] == ledger["runs"]
    assert sorted(after["reader_claims"][first].values()) == [1, 2]
    assert attempts == ["handwriting-qwen", "handwriting-qwen", "handwriting-muse"]


def test_unknown_reader_keeps_its_claim_and_blocks_restart(tmp_path, monkeypatch):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    calls = []

    def unknown(*args):
        calls.append(True)
        raise AdapterFailure("fixture_unknown", outcome_unknown=True)

    c.flow.adapters.production.transcribe = unknown
    ident = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, ident)
    retained = c.repo.document(
        c.launch.scope, "pilot_launch", c.flow.admission.ledger_id
    )
    assert list(retained["reader_claims"][ident].values()) == [1]
    worker, restarted = c.assemble(SQLiteRepository(c.repo.path))
    worker.tick()
    assert calls == [True] and not any(event[0] == "read" for event in c.events)
    after = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert after["reader_claims"] == retained["reader_claims"]
    assert after["reading_cohort"] == retained["reading_cohort"]


@pytest.mark.parametrize("missing", ["record", "segment", "regions", "provenance"])
def test_incomplete_retained_cohort_never_admits_a_reader(
    tmp_path, monkeypatch, missing
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    last = c.repo.get(c.launch.scope, c.launch.specimens[-1].specimen_id)
    if missing == "record":
        original_get = c.repo.get
        from specimen_digitization.application.storage import Missing

        def get(scope, ident):
            if ident == last.id:
                raise Missing(ident)
            return original_get(scope, ident)

        monkeypatch.setattr(c.repo, "get", get)
    else:
        if missing == "segment":
            last.run.completed_steps.remove("segment")
        elif missing == "regions":
            last.run.regions = []
        else:
            last.run.segmentation = {}
        c.repo.save(
            c.principal, last, last.version, "incomplete-fixture", digest(missing)
        )
    c.worker.tick()
    assert not any(event[0] == "read" for event in c.events)
    assert c.worker.result_summary()["status"] == "incomplete"


@pytest.mark.parametrize("boundary", ["reading_cohort", "reader_claims"])
def test_lost_reservation_response_never_calls_reader_or_releases_liability(
    tmp_path, monkeypatch, boundary
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    original = c.flow.admission._write

    def lost(ledger, **updates):
        original(ledger, **updates)
        if boundary in updates:
            raise ConnectionError("local fixture response lost after successful commit")

    monkeypatch.setattr(c.flow.admission, "_write", lost)
    c.worker.tick()
    assert not any(event[0] == "read" for event in c.events)
    held = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert held["reading_cohort"]["state"] == "reserved"
    if boundary == "reader_claims":
        assert sum(sum(values.values()) for values in held[boundary].values()) == 1
    worker, _ = c.assemble(SQLiteRepository(c.repo.path))
    for _ in range(10):
        worker.tick()
    after = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert after["reading_cohort"] == held["reading_cohort"]
    assert after["runs"] == held["runs"]
    assert not any(event[0] == "read" for event in c.events)
    assert worker.result_summary()["status"] == "incomplete"


def test_cohort_ledger_survives_real_protobuf_numeric_transport(tmp_path, monkeypatch):
    from google.protobuf import json_format
    from google.protobuf.struct_pb2 import Struct

    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    first = c.launch.specimens[0].specimen_id
    c.flow.step(c.principal, first)
    original = c.repo.document

    def transported(*args):
        result = json_format.MessageToDict(
            json_format.ParseDict(original(*args), Struct())
        )
        assert isinstance(result["revision"], float)
        return result

    monkeypatch.setattr(c.repo, "document", transported)
    for _ in range(3):
        c.flow.step(c.principal, first)
    held = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    assert list(held["reader_claims"][first].values()) == [1.0, 1.0]
    assert (
        c.repo.get(c.launch.scope, first).run.blocker
        == "pilot_evidence_review_required"
    )


def test_terminal_tenth_segmentation_stops_execution_incomplete(tmp_path, monkeypatch):
    from specimen_digitization.application.domain import LookupStatus

    c = cohort(tmp_path, monkeypatch, timeout=1)
    last = c.launch.specimens[-1].specimen_id
    original = c.flow.adapters.segment

    def failed(item):
        if item.id == last:
            raise AdapterFailure("fixture_segmentation_failed", LookupStatus.MALFORMED)
        return original(item)

    c.flow.adapters.segment = failed

    class Stop:
        waits = 0

        def is_set(self):
            return False

        def wait(self, interval):
            self.waits += 1
            assert self.waits < 60, "Terminal segmentation must stop this execution"

    c.worker.run(Stop(), interval_seconds=0.1)
    assert not any(event[0] == "read" for event in c.events)
    assert c.worker.result_summary()["status"] == "incomplete"
    assert len([event for event in c.events if event[0] == "segment"]) == 9


@pytest.mark.parametrize(
    "change", ["pins", "model", "region_asset", "segmentation_cost"]
)
def test_tenth_provenance_and_consumed_segmentation_checked_before_first_reader(
    tmp_path, monkeypatch, change
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    last = c.repo.get(c.launch.scope, c.launch.specimens[-1].specimen_id)
    if change == "pins":
        last.run.dependencies["prompts"] = {}
    elif change == "model":
        last.run.segmentation["model_revision"] = "unapproved"
    elif change == "region_asset":
        last.run.regions[0].asset_id = "unapproved"
    else:
        last.run.usage.reserved_cost_micros = 0
    c.repo.save(
        c.principal, last, last.version, "invalid-prior-fixture", digest(change)
    )
    with pytest.raises(OperationalBlock, match="pilot_cohort"):
        c.flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(event[0] == "read" for event in c.events)


@pytest.mark.parametrize(
    "budget,value",
    [
        ("max_external_calls", 12),
        ("max_tokens", 100000),
        ("max_steps", 7),
        ("max_active_seconds", 5),
    ],
)
def test_entire_reader_capacity_must_fit_before_first_reader(
    tmp_path, monkeypatch, budget, value
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    for binding in c.launch.specimens:
        item = c.repo.get(c.launch.scope, binding.specimen_id)
        setattr(item.run.profile.execution, budget, value)
        c.repo.save(
            c.principal,
            item,
            item.version,
            "bounded-capacity-fixture",
            digest([budget, value]),
        )
    segment_all(c)
    with pytest.raises(
        OperationalBlock, match="pilot_cohort_reading_capacity_insufficient"
    ):
        c.flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(event[0] == "read" for event in c.events)


def test_single_worker_segments_all_ten_then_reads_every_region_and_stops_for_review(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, regions=2, timeout=1)
    c.repo.due_page = lambda *args: pytest.fail("Frozen cohort never uses discovery")
    original = c.flow.adapters.production.transcribe

    def reader(item, region, route):
        assert len([event for event in c.events if event[0] == "segment"]) == 10
        ledger = c.repo.document(
            c.launch.scope, "pilot_launch", c.flow.admission.ledger_id
        )
        assert ledger["reading_cohort"]["reading_count"] == 40
        assert (
            ledger["reader_claims"][item.id]["transcribe:" + region.id + ":" + route]
            == 1
        )
        return original(item, region, route)

    c.flow.adapters.production.transcribe = reader

    class Stop:
        waits = 0

        def is_set(self):
            return False

        def wait(self, interval):
            self.waits += 1
            assert self.waits < 100

    c.worker.run(Stop(), interval_seconds=0.1)
    reads = [event for event in c.events if event[0] == "read"]
    assert len(reads) == len(set(reads)) == 40
    summary = c.worker.result_summary()
    assert summary["status"] == "evidence_review_required"
    assert set(summary["specimens"]) == {
        binding.specimen_id for binding in c.launch.specimens
    }
    assert summary["counts"] == {"review_required": 10}


def test_prior_reader_work_without_cohort_hold_cannot_be_adopted(tmp_path, monkeypatch):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    first = c.repo.get(c.launch.scope, c.launch.specimens[0].specimen_id)
    first.run.attempts[
        "transcribe:" + first.run.regions[0].id + ":handwriting-qwen"
    ] = 1
    first.run.usage.reserved_cost_micros += 59
    c.repo.save(
        c.principal,
        first,
        first.version,
        "unreconciled-reader-fixture",
        digest("legacy-reader"),
    )
    with pytest.raises(
        OperationalBlock, match="pilot_cohort_prior_reader_work_unreconciled"
    ):
        c.flow.step(c.principal, first.id)
    assert not any(event[0] == "read" for event in c.events)


def test_complete_reader_envelope_must_fit_remaining_launch_lifetime(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch)
    segment_all(c)
    c.clock[0] = c.launch.expires_at - timedelta(seconds=126)
    with pytest.raises(OperationalBlock, match="cohort.*time"):
        c.flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(event[0] == "read" for event in c.events)


def test_entire_serial_cohort_must_fit_existing_worker_maximum(tmp_path, monkeypatch):
    c = cohort(tmp_path, monkeypatch)
    segment_all(c)

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            pytest.fail("Infeasible whole work must stop immediately")

    c.worker.run(Stop(), max_seconds=1500)
    assert not any(event[0] == "read" for event in c.events)
    assert c.worker.result_summary()["status"] == "incomplete"


def test_restarted_execution_cannot_refresh_remaining_worker_time(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    c.flow.admission.bind_execution_window(max_seconds=400)
    held = c.flow.admission.reserve_cohort_readings()
    c.clock[0] += timedelta(seconds=399)
    worker, flow = c.assemble(SQLiteRepository(c.repo.path))
    with pytest.raises(OperationalBlock, match="cohort.*time"):
        flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(event[0] == "read" for event in c.events)
    ledger = c.repo.document(c.launch.scope, "pilot_launch", flow.admission.ledger_id)
    assert ledger["reading_cohort"] == held


def test_original_worker_window_cannot_be_recreated_after_effects(
    tmp_path, monkeypatch
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    ledger = c.flow.admission._ledger()
    del ledger["execution_window"]
    c.repo.put_document(
        c.launch.scope,
        "pilot_launch",
        c.flow.admission.ledger_id,
        {key: value for key, value in ledger.items() if key != "revision"},
        ledger["revision"],
    )
    _, flow = c.assemble(SQLiteRepository(c.repo.path))
    with pytest.raises(OperationalBlock, match="execution_time_unreconciled"):
        flow.step(c.principal, c.launch.specimens[0].specimen_id)
    assert not any(event[0] == "read" for event in c.events)


def test_monotonic_worker_time_is_checked_even_if_wall_clock_stalls(
    tmp_path, monkeypatch
):
    import specimen_digitization.application.worker as module

    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    elapsed = [0.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    original = c.worker.tick

    def tick(stop):
        elapsed[0] = 1200
        return original(stop)

    monkeypatch.setattr(c.worker, "tick", tick)

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            pytest.fail("Remaining worker envelope must stop immediately")

    c.worker.run(Stop(), max_seconds=1500)
    assert not any(event[0] == "read" for event in c.events)


@pytest.mark.parametrize(
    "malformed", [{}, False, 0, None, [], "", {"unexpected": 1500}]
)
def test_existing_invalid_execution_window_is_never_recreated(
    tmp_path, monkeypatch, malformed
):
    c = cohort(tmp_path, monkeypatch, timeout=1)
    segment_all(c)
    ledger = c.flow.admission._ledger()
    ledger["execution_window"] = malformed
    c.repo.put_document(
        c.launch.scope,
        "pilot_launch",
        c.flow.admission.ledger_id,
        {key: value for key, value in ledger.items() if key != "revision"},
        ledger["revision"],
    )
    c.clock[0] += timedelta(seconds=1490)
    before = c.repo.document(c.launch.scope, "pilot_launch", c.flow.admission.ledger_id)
    _, flow = c.assemble(SQLiteRepository(c.repo.path))
    with pytest.raises(OperationalBlock, match="execution_time"):
        flow.step(c.principal, c.launch.specimens[0].specimen_id)
    after = c.repo.document(c.launch.scope, "pilot_launch", flow.admission.ledger_id)
    assert after == before
    assert not any(event[0] == "read" for event in c.events)
