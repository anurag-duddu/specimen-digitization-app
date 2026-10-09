"""An administrator reconciles an unknown outcome of a model reading by reading again.

A run blocked as `external_outcome_unknown` had no way out: retry, resume and
reprocess are refused for it, and pause and cancel leave the blocker in place.
The `reconcile` run action runs the blocked step once more, and only where that
writes no record twice: a model reading (`transcribe:`, `first_pass:`). A cancelled
run stays stopped, and a paused run stays paused.
"""

from datetime import datetime, timedelta, timezone

import pytest

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import (
    Asset,
    Observation,
    Principal,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
)
from specimen_digitization.application.first_pass import synthetic_decision
from specimen_digitization.application.lane import queue
from specimen_digitization.application.storage import (
    LocalBlobs,
    SQLiteRepository,
    digest,
    work_available_at,
)
from specimen_digitization.application.workflow import (
    SyntheticAdapters,
    Workflow,
)

from test_application import HEADERS, PREFIX, image_bytes
from test_lane_trigger import (
    STAGE_COSTS,
    USER,
    RecordingDispatcher,
    due_ids,
    lane_client,
    registry,
)

SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
UNKNOWN = "external_outcome_unknown"
DROPPED = "connection dropped before the provider answered"
ROUTES = Profile().routes


def operator():
    return Principal(user_id=USER, scope=SCOPE, role="operator")


class Readers(SyntheticAdapters):
    """The fixture's readers, one of whose calls drops its connection."""

    def __init__(self, blobs, *, drop=None):
        # Differing texts make the first pass a step of the run.
        super().__init__(blobs, SYNTHETIC_TEXT, alternate_text=SYNTHETIC_TEXT + "\nextra")
        self.drop, self.calls = drop, []

    def segment(self, specimen):
        self.calls.append("segment")
        if self.drop == "segment":
            raise RuntimeError(DROPPED)
        return super().segment(specimen)

    def transcribe(self, specimen, region, route):
        self.calls.append("transcribe:" + route)
        if self.drop == "transcribe:" + route:
            raise RuntimeError(DROPPED)
        return super().transcribe(specimen, region, route)

    def first_pass(self, specimen, region, readings):
        self.calls.append("first_pass")
        if self.drop == "first_pass":
            raise RuntimeError(DROPPED)
        return synthetic_decision(self.blobs, region, readings)


def blocked_run(root, drop, *, synthetic=False):
    """A run the worker blocked as unknown at the call named by `drop`.

    The workflow runs for real: the intent is saved, the call drops, and the
    lease is left to expire (the workflow's clock is an hour behind).
    """
    repo = SQLiteRepository(root / "state.sqlite3")
    blobs = LocalBlobs(root / "blobs")
    data = image_bytes()
    run = Run(profile=Profile(synthetic=synthetic))
    specimen = Specimen(
        scope=SCOPE,
        run=run,
        asset=Asset(
            sensitive=False,
            sha256=digest("reconcile"),
            blob_ref=blobs.put(data),
            media_type="image/png",
            size_bytes=len(data),
            width=120,
            height=80,
            filename="reconcile.png",
            uploader=USER,
        ),
    )
    queue(specimen, registry(), USER)
    run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    if drop != "segment":
        run.completed_steps.append("segment")
        run.regions = [
            Region(
                asset_id=specimen.asset.id,
                x=0,
                y=0,
                width=120,
                height=80,
                order=0,
                method="fixture",
                version="1",
            )
        ]
    repo.create(operator(), specimen, "create", digest("create"))
    adapters = Readers(blobs, drop=drop)
    workflow = Workflow(
        repo,
        blobs,
        adapters,
        clock=lambda: datetime.now(timezone.utc) - timedelta(hours=1),
    )
    for _ in range(6):
        current = workflow.step(operator(), specimen.id)
        if current.run.blocker == UNKNOWN:
            break
    assert current.run.blocker == UNKNOWN
    assert current.run.stage == "processing_blocked"
    return repo, blobs, current


def mutate(repo, specimen_id, change, label):
    """Save a stored run edited by `change`, for the states a fixture cannot reach."""
    specimen = repo.get(SCOPE, specimen_id)
    change(specimen.run)
    return repo.save(operator(), specimen, specimen.version, label, digest(label))


def reconcile(client, run, revision, *, reason="The reader dropped; read it again", key="reconcile-1"):
    return client.post(
        PREFIX + f"/runs/{run.id}/actions",
        headers=dict(HEADERS, **{"Idempotency-Key": key}),
        json={"action": "reconcile", "expected_revision": revision, "reason": reason},
    )


def actions_of(client, specimen_id):
    response = client.get(PREFIX + f"/specimens/{specimen_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["available_actions"]


def admin(root, dispatcher=None, role="admin"):
    return lane_client(root, dispatcher=dispatcher, role=role)


def reservation(run):
    usage = run.usage
    return (
        usage.steps,
        usage.external_calls,
        usage.reserved_tokens,
        usage.reserved_cost_micros,
        usage.reserved_active_seconds,
    )


def test_an_admin_reads_a_blocked_reading_again(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[1])
    step = f"transcribe:{blocked.run.regions[0].id}:{ROUTES[1]}"
    assert blocked.run.attempts[step] == 1
    # Two readings were reserved, the finished one and the unknown one.
    assert blocked.run.usage.reserved_cost_micros == 2 * STAGE_COSTS.for_step(step)
    dispatcher = RecordingDispatcher()
    c = admin(tmp_path, dispatcher)
    assert actions_of(c, blocked.id).count("reconcile") == 1

    response = reconcile(c, blocked.run, blocked.version)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["blocker"] is None
    assert "reconcile" not in response.json()["available_actions"]
    saved = repo.get(SCOPE, blocked.id)
    assert saved.version == blocked.version + 1
    assert saved.run.blocker is None
    assert saved.run.lease_until is None
    assert saved.run.stage == "pending"
    assert saved.run.completed_steps == blocked.run.completed_steps
    assert saved.run.observations == blocked.run.observations
    assert dispatcher.calls == 1
    # The run is due again, so the worker's drain picks it up.
    assert work_available_at(saved) is not None
    assert due_ids(tmp_path) == [blocked.id]


def test_the_unknown_spend_stays_and_the_second_reading_reserves_its_own(tmp_path):
    repo, blobs, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[1])
    step = f"transcribe:{blocked.run.regions[0].id}:{ROUTES[1]}"
    held = reservation(blocked.run)
    c = admin(tmp_path)
    assert reconcile(c, blocked.run, blocked.version).status_code == 200
    # Reconciling neither refunds nor releases the earlier reservation.
    waiting = repo.get(SCOPE, blocked.id).run
    assert reservation(waiting) == held
    assert waiting.attempts == blocked.run.attempts

    readers = Readers(blobs)
    drained = Workflow(repo, blobs, readers).step(operator(), blocked.id)

    assert readers.calls == ["transcribe:" + ROUTES[1]]
    read = [o.route_id for o in drained.run.observations]
    assert read == [ROUTES[0], ROUTES[1]]
    assert step in drained.run.completed_steps
    assert drained.run.blocker is None
    assert drained.run.attempts[step] == 2
    # The earlier reservation stays counted in full beside the new one.
    assert drained.run.usage.external_calls == held[1] + 2
    assert drained.run.usage.reserved_cost_micros == held[3] + STAGE_COSTS.for_step(step)
    assert drained.run.usage.steps == held[0] + 1


def test_an_admin_compares_a_blocked_pair_again(tmp_path):
    repo, blobs, blocked = blocked_run(tmp_path, "first_pass", synthetic=True)
    step = f"first_pass:{blocked.run.regions[0].id}"
    assert blocked.run.attempts[step] == 1
    c = admin(tmp_path)

    response = reconcile(c, blocked.run, blocked.version)

    assert response.status_code == 200, response.text
    saved = repo.get(SCOPE, blocked.id)
    assert (saved.run.blocker, saved.run.lease_until) == (None, None)
    readers = Readers(blobs)
    drained = Workflow(repo, blobs, readers).step(operator(), blocked.id)
    assert readers.calls == ["first_pass"]
    assert step in drained.run.completed_steps
    assert [d.region_id for d in drained.run.first_pass_decisions] == [
        blocked.run.regions[0].id
    ]


def test_the_audit_history_records_who_when_why_which_step_and_the_old_blocker(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    step = f"transcribe:{blocked.run.regions[0].id}:{ROUTES[0]}"
    c = admin(tmp_path)
    assert (
        reconcile(c, blocked.run, blocked.version, reason="Read the label again").status_code
        == 200
    )
    saved = repo.get(SCOPE, blocked.id)
    event = saved.audit[-1]
    assert saved.audit[:-1] == blocked.audit
    assert event.action == "reconcile"
    assert event.actor == USER
    assert event.reason == "Read the label again"
    assert event.created_at
    assert event.before["blocker"] == UNKNOWN
    assert event.before["step"] == step
    assert event.before["attempt"] == 1
    assert event.before["lease_until"] == blocked.run.lease_until
    assert event.after == {"blocker": None, "lease_until": None, "step": step}
    events = c.get(PREFIX + f"/runs/{saved.run.id}/events", headers=HEADERS).json()
    assert [e["action"] for e in events["items"]][-1] == "reconcile"
    assert events["blocker"] is None


def test_an_effectful_step_is_never_reconciled(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "segment")
    assert blocked.run.attempts == {"segment": 1}
    c = admin(tmp_path)
    assert "reconcile" not in actions_of(c, blocked.id)

    response = reconcile(c, blocked.run, blocked.version)

    assert response.status_code == 409, response.text
    assert "not a model reading" in response.json()["error"]["message"]
    after = repo.get(SCOPE, blocked.id)
    assert after.version == blocked.version
    assert after.run.blocker == UNKNOWN


def test_a_step_the_code_cannot_classify_is_refused(tmp_path, monkeypatch):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: "mystery:step"))
    c = admin(tmp_path)
    assert "reconcile" not in actions_of(c, blocked.id)

    response = reconcile(c, blocked.run, blocked.version)

    assert response.status_code == 409, response.text
    assert repo.get(SCOPE, blocked.id).version == blocked.version


def test_the_organiser_step_is_refused(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[1])
    regions = blocked.run.regions

    def to_the_organiser(run):
        run.completed_steps += [f"transcribe:{regions[0].id}:{ROUTES[1]}", "adjudicate"]
        run.attempts["parse"] = 1

    stuck = mutate(repo, blocked.id, to_the_organiser, "to-the-organiser")
    assert Workflow.next_step(stuck.run) == "parse"
    c = admin(tmp_path)
    assert "reconcile" not in actions_of(c, stuck.id)
    assert reconcile(c, stuck.run, stuck.version).status_code == 409
    assert repo.get(SCOPE, stuck.id).version == stuck.version


def test_a_reason_is_required(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    c = admin(tmp_path)

    for reason in ("", "   "):
        response = reconcile(c, blocked.run, blocked.version, reason=reason)
        assert response.status_code == 422, response.text
        assert "reason" in response.json()["error"]["message"].lower()
    assert repo.get(SCOPE, blocked.id).version == blocked.version


@pytest.mark.parametrize("role", ["viewer", "operator", "reviewer", "manager"])
def test_only_an_admin_may_reconcile(tmp_path, role):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    c = admin(tmp_path, role=role)
    assert "reconcile" not in actions_of(c, blocked.id)

    response = reconcile(c, blocked.run, blocked.version)

    assert response.status_code == 403, response.text
    assert repo.get(SCOPE, blocked.id).version == blocked.version
    assert repo.get(SCOPE, blocked.id).run.blocker == UNKNOWN


@pytest.mark.parametrize(
    "blocker", [None, "stage_failed_inspect_private_worker_logs", "cost_budget_exhausted"]
)
def test_only_an_unknown_outcome_is_reconciled(tmp_path, blocker):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])

    def other_blocker(run):
        run.blocker = blocker

    other = mutate(repo, blocked.id, other_blocker, "other-blocker")
    c = admin(tmp_path)
    assert "reconcile" not in actions_of(c, other.id)

    response = reconcile(c, other.run, other.version)

    assert response.status_code == 409, response.text
    assert "unknown external outcome" in response.json()["error"]["message"]
    assert repo.get(SCOPE, other.id).version == other.version


def test_a_second_reconcile_changes_nothing(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    c = admin(tmp_path, RecordingDispatcher())
    assert reconcile(c, blocked.run, blocked.version).status_code == 200
    once = repo.get(SCOPE, blocked.id)

    # A new request and a replay of the first are both refused, not repeated.
    for key in ("reconcile-2", "reconcile-1"):
        again = reconcile(c, once.run, once.version, key=key)
        assert again.status_code == 409, again.text
        assert "unknown external outcome" in again.json()["error"]["message"]

    twice = repo.get(SCOPE, blocked.id)
    assert twice.version == once.version
    assert [e.action for e in twice.audit].count("reconcile") == 1


def test_a_replay_after_the_step_blocks_again_returns_the_old_snapshot(tmp_path):
    repo, blobs, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    c = admin(tmp_path, RecordingDispatcher())
    first = reconcile(c, blocked.run, blocked.version)
    assert first.status_code == 200, first.text
    # The step is sent again, drops its connection again and its lease expires.
    again = Workflow(
        repo,
        blobs,
        Readers(blobs, drop="transcribe:" + ROUTES[0]),
        clock=lambda: datetime.now(timezone.utc) - timedelta(hours=1),
    ).step(operator(), blocked.id)
    assert again.run.blocker == UNKNOWN
    assert set(again.run.attempts.values()) == {2}
    assert again.version > blocked.version + 1

    # The same key and body now finds its receipt: the stored answer comes back
    # as a 200 for the old revision, and the record is not changed.
    replay = reconcile(c, blocked.run, blocked.version)

    assert replay.status_code == 200, replay.text
    assert replay.json()["revision"] == blocked.version + 1
    assert replay.json()["blocker"] is None
    stored = repo.get(SCOPE, blocked.id)
    assert stored.version == again.version
    assert stored.run.blocker == UNKNOWN
    assert [e.action for e in stored.audit].count("reconcile") == 1


def act(client, specimen_id, action, key):
    detail = client.get(PREFIX + f"/specimens/{specimen_id}", headers=HEADERS).json()
    return client.post(
        PREFIX + f"/runs/{detail['active_run_id']}/actions",
        headers=dict(HEADERS, **{"Idempotency-Key": key}),
        json={
            "action": action,
            "expected_revision": detail["revision"],
            "reason": "Stage test " + action,
        },
    )


def test_a_cancelled_run_stays_stopped(tmp_path):
    repo, blobs, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    dispatcher = RecordingDispatcher()
    c = admin(tmp_path, dispatcher)
    assert "reconcile" in actions_of(c, blocked.id)
    assert act(c, blocked.id, "cancel", "cancel-1").status_code == 200
    cancelled = repo.get(SCOPE, blocked.id)
    assert (cancelled.run.stage, cancelled.run.blocker) == ("cancelled", UNKNOWN)
    # A cancelled run is not offered the action, and it is refused if asked.
    assert "reconcile" not in actions_of(c, blocked.id)

    response = reconcile(c, cancelled.run, cancelled.version)

    assert response.status_code == 409, response.text
    assert "cancelled" in response.json()["error"]["message"]
    after = repo.get(SCOPE, blocked.id)
    assert after.version == cancelled.version
    assert (after.run.stage, after.run.blocker) == ("cancelled", UNKNOWN)
    # Cancel still stops paid work: nothing is queued and no reader is called.
    assert work_available_at(after) is None
    assert due_ids(tmp_path) == []
    readers = Readers(blobs)
    Workflow(repo, blobs, readers).step(operator(), blocked.id)
    assert readers.calls == []


def test_a_paused_run_stays_paused_until_a_person_resumes_it(tmp_path):
    repo, blobs, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    dispatcher = RecordingDispatcher()
    c = admin(tmp_path, dispatcher)
    assert act(c, blocked.id, "pause", "pause-1").status_code == 200
    paused = repo.get(SCOPE, blocked.id)
    assert (paused.run.stage, paused.run.blocker) == ("paused", UNKNOWN)
    assert "reconcile" in actions_of(c, blocked.id)
    started = dispatcher.calls

    response = reconcile(c, paused.run, paused.version)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paused"
    assert response.json()["blocker"] is None
    saved = repo.get(SCOPE, blocked.id)
    assert (saved.run.stage, saved.run.blocker, saved.run.lease_until) == (
        "paused",
        None,
        None,
    )
    event = saved.audit[-1]
    assert (event.action, event.before["stage"], event.before["blocker"]) == (
        "reconcile",
        "paused",
        UNKNOWN,
    )
    # Nothing is queued and no worker is started: it waits to be resumed.
    assert dispatcher.calls == started
    assert work_available_at(saved) is None
    assert due_ids(tmp_path) == []
    readers = Readers(blobs)
    Workflow(repo, blobs, readers).step(operator(), blocked.id)
    assert readers.calls == []

    resumed = act(c, blocked.id, "resume", "resume-1")

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "pending"
    assert dispatcher.calls == started + 1
    assert due_ids(tmp_path) == [blocked.id]
    Workflow(repo, blobs, readers).step(operator(), blocked.id)
    assert readers.calls == ["transcribe:" + ROUTES[0]]


def test_a_stale_revision_is_a_conflict(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])
    c = admin(tmp_path)

    response = reconcile(c, blocked.run, blocked.version + 1)

    assert response.status_code == 409, response.text
    assert repo.get(SCOPE, blocked.id).run.blocker == UNKNOWN


def test_a_live_lease_is_waited_out(tmp_path):
    repo, _, blocked = blocked_run(tmp_path, "transcribe:" + ROUTES[0])

    def leased(run):
        run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()

    live = mutate(repo, blocked.id, leased, "live-lease")
    c = admin(tmp_path)

    response = reconcile(c, live.run, live.version)

    assert response.status_code == 409, response.text
    assert "still leased" in response.json()["error"]["message"]
    assert repo.get(SCOPE, blocked.id).version == live.version


# The unit below the HTTP action: which blocked steps may be run again.


def stored_run(step, *, blocker=UNKNOWN, attempts=1, observations=()):
    run = Run(profile=Profile(synthetic=True), blocker=blocker)
    run.attempts = {step: attempts} if attempts else {}
    run.observations = list(observations)
    return run


@pytest.mark.parametrize("step", ["transcribe:r1:handwriting-muse", "first_pass:r1"])
def test_the_model_reading_steps_may_be_reconciled(monkeypatch, step):
    from specimen_digitization.application.workflow import reconcilable_step

    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: step))
    assert reconcilable_step(stored_run(step)) == step


@pytest.mark.parametrize(
    "step",
    [
        "pin_dependencies",
        "classify",
        "quality_check",
        "segment",
        "adjudicate",
        "parse",
        "plan",
        "lookup",
        "authority:0:taxonomy",
        "resolve",
        "normalize",
        "validate",
        "finalize",
        "field_research",
        "field_research_recheck",
        "mystery:step",
        "",
        "transcribe:",
        "transcribe:r1",
        "transcribe::handwriting-muse",
        "transcribe:r1:",
        "transcribe:r1:a:b",
        "first_pass:",
        "first_pass:r1:extra",
        "Transcribe:r1:handwriting-muse",
    ],
)
def test_every_other_step_is_refused_by_default(monkeypatch, step):
    from specimen_digitization.application.workflow import reconcilable_step

    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: step))
    assert reconcilable_step(stored_run(step or "x")) is None


@pytest.mark.parametrize(
    "stage, disposition, allowed",
    [
        ("processing_blocked", None, True),
        ("paused", None, True),
        ("pending", None, True),
        ("transcribe", None, True),
        ("cancelled", None, False),
        ("finalized", None, False),
        ("processing_blocked", "needs_human_review", False),
    ],
)
def test_a_cancelled_or_finished_run_is_not_reconciled(
    monkeypatch, stage, disposition, allowed
):
    from specimen_digitization.application.workflow import reconcilable_step

    step = "transcribe:r1:handwriting-muse"
    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: step))
    run = stored_run(step)
    run.stage, run.disposition = stage, disposition
    assert reconcilable_step(run) == (step if allowed else None)


def test_a_reconcilable_step_needs_the_unknown_blocker_and_an_attempt(monkeypatch):
    from specimen_digitization.application.workflow import reconcilable_step

    step = "transcribe:r1:handwriting-muse"
    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: step))
    assert reconcilable_step(stored_run(step, blocker=None)) is None
    assert reconcilable_step(stored_run(step, blocker="cost_budget_exhausted")) is None
    # The unknown outcome is not tied to a step that was never attempted.
    assert reconcilable_step(stored_run(step, attempts=0)) is None


def test_a_reading_the_run_already_holds_is_not_read_twice(monkeypatch):
    from specimen_digitization.application.workflow import reconcilable_step

    step = "transcribe:r1:handwriting-muse"
    monkeypatch.setattr(Workflow, "next_step", staticmethod(lambda run: step))
    held = Observation(
        region_id="r1",
        route_id="handwriting-muse",
        model_id="m",
        provider="p",
        prompt_version="v",
        input_sha256="0" * 64,
        literal_text="text",
        raw_ref="0" * 64,
        raw_sha256="0" * 64,
    )
    other = held.model_copy(update={"route_id": "handwriting-qwen"})
    assert reconcilable_step(stored_run(step, observations=[held])) is None
    assert reconcilable_step(stored_run(step, observations=[other])) == step
