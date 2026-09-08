"""Worker discovery fairness and persisted effect budgets under failure."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import (
    Asset,
    Principal,
    Profile,
    Run,
    Scope,
    Specimen,
    now,
)
from specimen_digitization.application.storage import (
    SQLiteRepository,
    LocalBlobs,
    digest,
)
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters
from specimen_digitization.application.worker import PollingWorker
from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from test_application import image_bytes


def setup(tmp_path, count=1):
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    data = image_bytes()
    ref = blobs.put(data)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="worker-fixture", role="reviewer", scope=scope)
    specimens = []
    for index in range(count):
        item = Specimen(
            id=str(UUID(int=index + 1)),
            scope=scope,
            asset=Asset(
                sha256=digest(index),
                blob_ref=ref,
                media_type="image/png",
                size_bytes=len(data),
                width=120,
                height=80,
                filename="synthetic.png",
                uploader=principal.user_id,
            ),
            run=Run(profile=Profile(synthetic=True)),
        )
        specimens.append(repo.create(principal, item, "create", digest(index)))
    return repo, blobs, principal, specimens


def test_worker_passes_ten_thousand_without_hydrating_discovery_and_restarts(tmp_path):
    repo, _, principal, _ = setup(tmp_path, 1)
    created = now()
    # Real SQL discovery metadata for a large queue; no fake repository page implementation.
    with repo.connect() as db:
        db.execute("DELETE FROM records")
        db.executemany(
            "INSERT INTO records(org,collection,id,revision,payload,checksum,work_available_at,created_at,state) VALUES(?,?,?,1,'{}',?,?,?,'ingested')",
            [
                (
                    principal.scope.organization_id,
                    principal.scope.collection_id,
                    str(UUID(int=i + 1)),
                    digest(i),
                    created,
                    created,
                )
                for i in range(10037)
            ],
        )
    visited = []
    workflow = SimpleNamespace(step=lambda p, ident: visited.append(ident))
    memberships = lambda user: [dict(principal.scope.model_dump(), role="reviewer")]
    worker = PollingWorker(
        repo,
        workflow,
        principal.user_id,
        memberships,
        page_size=100,
        steps_per_scope=100,
    )
    for i in range(101):
        if i == 50:
            worker = PollingWorker(
                SQLiteRepository(repo.path),
                workflow,
                principal.user_id,
                memberships,
                page_size=100,
                steps_per_scope=100,
            )
        worker.tick()
    assert len(visited) == len(set(visited)) == 10037
    assert set(visited) == {str(UUID(int=i + 1)) for i in range(10037)}


def test_poison_record_and_membership_failure_do_not_starve_healthy_work(tmp_path):
    repo, _, principal, specimens = setup(tmp_path, 3)
    clock = [datetime.now(timezone.utc) + timedelta(seconds=1)]
    calls = []

    def step(p, ident):
        calls.append(ident)
        if ident == specimens[0].id:
            raise OSError("poison storage")

    members = [False]

    def loader(user):
        if members[0]:
            raise OSError("membership outage")
        return [dict(principal.scope.model_dump(), role="reviewer")]

    worker = PollingWorker(
        repo,
        SimpleNamespace(step=step),
        principal.user_id,
        loader,
        page_size=3,
        steps_per_scope=3,
        clock=lambda: clock[0].isoformat(),
    )
    worker.tick()
    assert calls == [s.id for s in specimens]
    assert worker.health.record_errors == 1
    members[0] = True
    worker.tick()
    assert worker.health.membership_errors == 1
    members[0] = False
    worker.tick()
    assert len(calls) == 3  # Membership cooldown is honored.
    clock[0] += timedelta(seconds=3)
    worker.tick()
    assert len(calls) == 6


@pytest.mark.parametrize(
    "budget, blocker",
    [
        ("steps", "step_budget_exhausted"),
        ("external_calls", "external_call_budget_exhausted"),
        ("reserved_tokens", "token_budget_exhausted"),
        ("active_seconds", "active_time_budget_exhausted"),
    ],
)
def test_budget_exhaustion_persists_before_adapter_effect(tmp_path, budget, blocker):
    repo, blobs, principal, items = setup(tmp_path)
    s = items[0]
    s.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    policy = s.run.profile.execution
    setattr(
        s.run.usage,
        budget,
        {
            "steps": policy.max_steps,
            "external_calls": policy.max_external_calls,
            "reserved_tokens": policy.max_tokens + 1,
            "active_seconds": policy.max_active_seconds,
        }[budget],
    )
    s = repo.save(principal, s, s.version, "budget-fixture", digest(budget))

    class Forbidden(SyntheticAdapters):
        def segment(self, specimen):
            pytest.fail("Adapter called after exhausted budget")

    blocked = Workflow(repo, blobs, Forbidden(blobs, SYNTHETIC_TEXT)).step(
        principal, s.id
    )
    assert blocked.run.blocker == blocker
    assert blocked.run.disposition is None
    assert SQLiteRepository(repo.path).get(principal.scope, s.id).run.blocker == blocker


def test_unpriced_production_effect_is_not_treated_as_zero_cost(tmp_path):
    repo, blobs, principal, items = setup(tmp_path)
    s = items[0]
    s.run.profile.synthetic = False
    s.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    s = repo.save(principal, s, s.version, "cost-fixture", digest("cost"))

    class Forbidden(SyntheticAdapters):
        def segment(self, specimen):
            pytest.fail("Unapproved cost spent")

    blocked = Workflow(repo, blobs, Forbidden(blobs, SYNTHETIC_TEXT)).step(
        principal, s.id
    )
    assert blocked.run.blocker == "approved_cost_budget_unavailable"
    assert blocked.run.usage.external_calls == 0
    assert blocked.run.usage.actual_cost_micros is None


def test_active_lease_prevents_duplicate_effect_and_late_completion_loses_cas(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from specimen_digitization.application.storage import Conflict

    repo, blobs, principal, items = setup(tmp_path)
    s = items[0]
    s.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    s = repo.save(principal, s, s.version, "ready", digest("ready"))
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Gated(SyntheticAdapters):
        def segment(self, specimen):
            calls.append(specimen.id)
            entered.set()
            assert release.wait(5)
            return super().segment(specimen)

    workflow = Workflow(repo, blobs, Gated(blobs, SYNTHETIC_TEXT))
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(workflow.step, principal, s.id)
        assert entered.wait(5)
        leased = repo.get(principal.scope, s.id)
        assert leased.run.usage.external_calls == 1
        assert workflow.step(principal, s.id).version == leased.version
        cancelled = leased.model_copy(deep=True)
        cancelled.run.stage = "cancelled"
        repo.save(principal, cancelled, leased.version, "cancel", digest("cancel"))
        release.set()
        with pytest.raises(Conflict):
            pending.result()
    assert len(calls) == 1
    retained = repo.get(principal.scope, s.id)
    assert retained.run.stage == "cancelled"
    assert not retained.run.regions


def test_crash_after_intent_never_automatically_repeats_unknown_effect(tmp_path):
    repo, blobs, principal, items = setup(tmp_path)
    s = items[0]
    s.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    s = repo.save(principal, s, s.version, "ready", digest("ready"))

    class Crash(SyntheticAdapters):
        def segment(self, specimen):
            raise SystemExit("simulated process death after durable intent")

    workflow = Workflow(repo, blobs, Crash(blobs, SYNTHETIC_TEXT))
    with pytest.raises(SystemExit):
        workflow.step(principal, s.id)
    retained = repo.get(principal.scope, s.id)
    assert retained.run.usage.external_calls == 1
    clock = datetime.fromisoformat(retained.run.lease_until) + timedelta(seconds=1)

    class Forbidden(SyntheticAdapters):
        def segment(self, specimen):
            pytest.fail("Unknown external effect was automatically repeated")

    recovered = Workflow(
        SQLiteRepository(repo.path),
        blobs,
        Forbidden(blobs, SYNTHETIC_TEXT),
        clock=lambda: clock,
    )
    blocked = recovered.step(principal, s.id)
    assert blocked.run.blocker == "external_outcome_unknown"
    assert blocked.run.stage == "processing_blocked"
    assert blocked.run.usage.external_calls == 1


def test_external_deadline_discards_late_result_and_retains_reservation(tmp_path):
    repo, blobs, principal, items = setup(tmp_path)
    s = items[0]
    s.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    s = repo.save(principal, s, s.version, "ready", digest("ready"))
    timings = iter([0, s.run.profile.execution.external_timeout_seconds + 1])
    workflow = Workflow(
        repo,
        blobs,
        SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        monotonic=lambda: next(timings),
    )
    blocked = workflow.step(principal, s.id)
    assert blocked.run.blocker == "external_outcome_unknown"
    assert blocked.run.stage == "processing_blocked"
    assert not blocked.run.regions
    assert blocked.run.usage.reserved_active_seconds > 0


def test_http_recovery_actions_reject_active_external_lease(tmp_path):
    from test_application import client, intake, PREFIX, HEADERS

    with client(tmp_path) as http:
        row = intake(http)
        repo = SQLiteRepository(tmp_path / "state.sqlite3")
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        principal = Principal(
            user_id="synthetic-reviewer", scope=scope, role="reviewer"
        )
        specimen = repo.get(scope, row["specimen_id"])
        specimen.run.stage = "transcribe"
        specimen.run.disposition = None
        specimen.run.blocker = "external_outcome_unknown"
        specimen.run.lease_until = (
            datetime.now(timezone.utc) + timedelta(seconds=120)
        ).isoformat()
        specimen = repo.save(
            principal, specimen, specimen.version, "active-lease", digest("lease")
        )
        for action in ("retry", "resume", "reprocess"):
            response = http.post(
                PREFIX + f"/runs/{specimen.run.id}/actions",
                headers=HEADERS,
                json={
                    "action": action,
                    "reason": "Synthetic retry probe",
                    "expected_revision": specimen.version,
                },
            )
            assert response.status_code == 409, response.text
        assert repo.get(scope, specimen.id).version == specimen.version


@pytest.mark.skipif(
    __import__("os").getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires seeded SQL Connect/PostgreSQL",
)
def test_real_sql_worker_discovers_and_advances_retained_work(tmp_path):
    import hashlib
    import io
    from uuid import uuid4
    from PIL import Image, PngImagePlugin
    from specimen_digitization.application.production import (
        SqlConnectRepository,
        sql_emulator_host,
        actor_uid,
    )

    repo = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host()
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    principal = Principal(
        user_id="synthetic-reviewer",
        role="reviewer",
        scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
    )
    actor_uid.set(principal.user_id)
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("synthetic_worker_id", str(uuid4()))
    Image.new("RGB", (120, 80), "white").save(output, format="PNG", pnginfo=metadata)
    data = output.getvalue()
    item = Specimen(
        scope=principal.scope,
        asset=Asset(
            sha256=hashlib.sha256(data).hexdigest(),
            blob_ref=blobs.put(data),
            media_type="image/png",
            size_bytes=len(data),
            width=120,
            height=80,
            filename="synthetic-worker.png",
            uploader=principal.user_id,
        ),
        run=Run(profile=Profile(synthetic=True)),
    )
    item = repo.create(principal, item, "worker:" + item.id, digest(item.id))
    workflow = Workflow(repo, blobs, SyntheticAdapters(blobs, SYNTHETIC_TEXT))
    worker = PollingWorker(repo, workflow, principal.user_id, repo.memberships)
    for _ in range(40):
        worker.tick()
        if repo.get(principal.scope, item.id).run.stage == "finalized":
            break
    retained = repo.get(principal.scope, item.id)
    assert retained.run.stage == "finalized", retained.run.blocker
    assert worker.health.record_errors == worker.health.scope_errors == 0
    assert len(retained.run.observations) == 2
    assert retained.run.usage.external_calls == 4
