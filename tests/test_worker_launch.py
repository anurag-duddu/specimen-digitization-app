"""Pilot admission uses real retained state and zero external model calls."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
import threading

import pytest

from specimen_digitization.application.worker_launch import (
    PilotLaunch,
    PilotAdmission,
    read_launch,
    verify_source_manifest,
)
from specimen_digitization.application.worker import (
    PilotWorker,
    PollingWorker,
    production_launch,
)
from specimen_digitization.application.storage import SQLiteRepository
from specimen_digitization.application.workflow import OperationalBlock
from test_worker_recovery import setup


def fixture(tmp_path):
    repo, blobs, principal, specimens = setup(tmp_path, 11)
    for s in specimens:
        s.run.profile.synthetic = False
        s.asset.blob_ref = s.asset.sha256 + ":123"
        s.run.profile.execution.approved_cost_limit_micros = 1000
        s.run.profile.execution.request_cost_reservation_micros = 100
        repo.save(principal, s, s.version, "production-policy", s.asset.sha256)
    launch = PilotLaunch(
        source_manifest_sha256="a" * 64,
        authorization_reference="local-fixture-approval",
        scope=principal.scope,
        specimens=[
            dict(
                specimen_id=s.id, asset_sha256=s.asset.sha256, blob_ref=s.asset.blob_ref
            )
            for s in specimens[:10]
        ],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        total_cost_limit_micros=10000,
        per_specimen_cost_limit_micros=1000,
        per_specimen_call_limit=32,
        per_specimen_token_limit=160000,
        effect_timeout_seconds=120,
        hf_secret_resource="/".join(
            (
                "projects",
                "specimen-digitization",
                "secrets",
                "existing-hf",
                "versions",
                "1",
            )
        ),
    )
    return repo, principal, specimens, launch


def test_pilot_worker_never_discovers_eleventh_record_and_rechecks_revocation(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    calls = []
    members = [dict(principal.scope.model_dump(), role="reviewer")]
    repo.due_page = lambda *args: pytest.fail("Pilot may not enumerate collection")

    def step(p, ident):
        calls.append(ident)
        return repo.get(p.scope, ident)

    worker = PilotWorker(
        repo,
        SimpleNamespace(step=step),
        principal.user_id,
        lambda uid: members,
        PilotAdmission(repo, launch),
    )
    for _ in range(20):
        worker.tick()
    assert set(calls) == {s.id for s in specimens[:10]}
    assert len(calls) == 20
    members.clear()
    worker.tick()
    assert len(calls) == 20
    assert worker.health.blocked_scopes["pilot"] == "pilot_membership_required"


def test_pilot_reservations_survive_restart_and_refuse_changed_run_or_budget(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    admission = PilotAdmission(repo, launch)
    s = repo.get(principal.scope, specimens[0].id)
    admission.admit(s)
    restarted = PilotAdmission(SQLiteRepository(repo.path), launch)
    restarted.admit(s)
    ledger = repo.document(launch.scope, "pilot_launch", admission.ledger_id)
    assert len(ledger["runs"]) == 1
    assert ledger["revision"] == 1
    s.run.id = "new-run"
    with pytest.raises(OperationalBlock, match="run_changed"):
        restarted.admit(s)
    changed = launch.model_copy(update={"total_cost_limit_micros": 20000})
    with pytest.raises(OperationalBlock, match="launch_changed"):
        PilotAdmission(repo, changed).admit(s)


@pytest.mark.parametrize(
    "kind", ["unknown", "bytes", "generation", "synthetic", "budget", "deadline"]
)
def test_admission_rejects_before_any_effect(tmp_path, kind):
    repo, principal, specimens, launch = fixture(tmp_path)
    s = repo.get(principal.scope, specimens[0].id)
    if kind == "unknown":
        s.id = specimens[10].id
    if kind == "bytes":
        s.asset.sha256 = "b" * 64
    if kind == "generation":
        s.asset.blob_ref = s.asset.sha256 + ":124"
    if kind == "synthetic":
        s.run.profile.synthetic = True
    if kind == "budget":
        s.run.profile.execution.approved_cost_limit_micros = 1001
    if kind == "deadline":
        launch.expires_at = datetime.now(timezone.utc)
    with pytest.raises(OperationalBlock):
        PilotAdmission(repo, launch).admit(s)


def test_shutdown_stops_admission_within_tick(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    calls = []
    stop = threading.Event()
    stop.set()
    worker = PilotWorker(
        repo,
        SimpleNamespace(step=lambda *args: calls.append(args)),
        principal.user_id,
        lambda uid: pytest.fail("No discovery after stop"),
        PilotAdmission(repo, launch),
    )
    worker.tick(stop)
    assert not calls
    members = [dict(principal.scope.model_dump(), role="reviewer")]
    stop.clear()

    def step(*args):
        calls.append(args)
        stop.set()

    generic = PollingWorker(
        repo,
        SimpleNamespace(step=step),
        principal.user_id,
        lambda uid: members,
        page_size=10,
        steps_per_scope=10,
    )
    generic.tick(stop)
    assert len(calls) == 1


def test_manifest_and_configuration_fail_closed_before_credentials(
    tmp_path, monkeypatch
):
    repo, principal, specimens, launch = fixture(tmp_path)
    path = tmp_path / "launch.json"
    raw = launch.model_dump_json().encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    assert read_launch(path, hashlib.sha256(raw).hexdigest()) == launch
    with pytest.raises(OperationalBlock, match="digest_mismatch"):
        read_launch(path, "0" * 64)
    manifest = {
        "schema_version": "specimen-pilot/v1",
        "status": "ready",
        "project_id": "specimen-digitization",
        "authorization_reference": launch.authorization_reference,
        "selection": {
            "order": "explicit_source_order",
            "source_inventory_sha256": "c" * 64,
        },
        "specimens": [
            dict(
                ordinal=i,
                specimen_id=s.specimen_id,
                **launch.scope.model_dump(),
                source_objects=[
                    dict(
                        bucket="source",
                        object_name=str(i),
                        generation="1",
                        sha256=s.asset_sha256,
                        size_bytes=100,
                    )
                ],
                application_source=dict(
                    blob_ref=s.blob_ref,
                    sha256=s.asset_sha256,
                    size_bytes=100,
                    source_object_index=0,
                ),
            )
            for i, s in enumerate(launch.specimens, 1)
        ],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(manifest))
    source.chmod(0o600)
    launch.source_manifest_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    verify_source_manifest(source, launch)
    manifest["status"] = "metadata_frozen"
    source.write_text(json.dumps(manifest))
    source.chmod(0o600)
    launch.source_manifest_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(OperationalBlock, match="not_ready"):
        verify_source_manifest(source, launch)
    with pytest.raises(OperationalBlock, match="manifest_required"):
        production_launch(SimpleNamespace(launch_policy=None, source_manifest=None))


def test_dispatch_fence_survives_process_recreation_and_generic_retry(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    admission = PilotAdmission(repo, launch)
    specimen = repo.get(principal.scope, specimens[0].id)
    admission.begin_step(specimen)
    admission.admit(specimen)  # Same active dispatch may pass Workflow's second check.
    restarted = PilotAdmission(SQLiteRepository(repo.path), launch)
    with pytest.raises(OperationalBlock, match="dispatch_reconciliation"):
        restarted.begin_step(specimen)
    specimen.run.stage = "processing_blocked"
    specimen.run.blocker = "external_outcome_unknown"
    specimen = repo.save(principal, specimen, specimen.version, "unknown", "unknown")
    admission.note_outcome(specimen, completed_dispatch=True)
    specimen.run.blocker = None
    specimen.run.stage = "segment"  # API-equivalent generic retry must not erase fence.
    specimen = repo.save(principal, specimen, specimen.version, "retry", "retry")
    for guard in (admission, restarted):
        with pytest.raises(OperationalBlock, match="dispatch_reconciliation"):
            guard.begin_step(specimen)


def test_known_checkpoint_releases_fence_but_exception_never_does(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    admission = PilotAdmission(repo, launch)
    specimen = repo.get(principal.scope, specimens[0].id)
    admission.begin_step(specimen)
    specimen.run.completed_steps.append("pin_dependencies")
    specimen = repo.save(principal, specimen, specimen.version, "known", "known")
    admission.note_outcome(specimen, completed_dispatch=True)
    restarted = PilotAdmission(SQLiteRepository(repo.path), launch)
    restarted.begin_step(specimen)
    restarted.abandon_dispatch(specimen.id)
    with pytest.raises(OperationalBlock, match="dispatch_reconciliation"):
        restarted.begin_step(specimen)


def test_admission_failure_persists_only_for_matching_authorized_asset(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    launch.expires_at = datetime.now(timezone.utc)
    members = lambda uid: [dict(principal.scope.model_dump(), role="reviewer")]
    worker = PilotWorker(
        repo,
        SimpleNamespace(step=lambda *a: pytest.fail("No dispatch")),
        principal.user_id,
        members,
        PilotAdmission(repo, launch),
    )
    worker.tick()
    retained = repo.get(principal.scope, specimens[0].id)
    assert retained.run.stage == "processing_blocked"
    assert retained.run.blocker == "pilot_launch_deadline_reached"
    other = repo.get(principal.scope, specimens[1].id)
    other.asset.sha256 = "f" * 64
    other = repo.save(principal, other, other.version, "mismatch", "mismatch")
    worker.tick()
    assert repo.get(principal.scope, other.id).version == other.version


@pytest.mark.parametrize(
    "stage,blocker,state,status",
    [
        ("ingested", None, "pending", "incomplete"),
        (
            "processing_blocked",
            "external_outcome_unknown",
            "processing_blocked",
            "incomplete",
        ),
        (
            "processing_blocked",
            "pilot_evidence_review_required",
            "review_required",
            "evidence_review_required",
        ),
        ("finalized", None, "finalized", "completed"),
    ],
)
def test_summary_is_durable_and_never_counts_blocked_or_pending_as_complete(
    tmp_path, stage, blocker, state, status
):
    repo, principal, specimens, launch = fixture(tmp_path)
    for binding in launch.specimens:
        specimen = repo.get(principal.scope, binding.specimen_id)
        specimen.run.stage, specimen.run.blocker = stage, blocker
        repo.save(principal, specimen, specimen.version, "status", "status")
    admission = PilotAdmission(repo, launch)
    worker = PilotWorker(
        repo,
        SimpleNamespace(step=lambda *a: pytest.fail("Read-only summary")),
        principal.user_id,
        lambda uid: [dict(principal.scope.model_dump(), role="reviewer")],
        admission,
    )
    summary = worker.result_summary()
    assert summary["status"] == status
    assert summary["counts"] == {state: 10}
    stored = SQLiteRepository(repo.path).document(
        launch.scope, "pilot_launch", admission.ledger_id
    )
    assert stored["summary"] == summary


def test_evidence_mode_requires_explicit_profile_hash(tmp_path):
    _, _, _, launch = fixture(tmp_path)
    value = launch.model_dump(mode="json")
    value["evidence_only"] = True
    with pytest.raises(ValueError, match="pinned draft profile"):
        PilotLaunch.model_validate(value)
    value["evidence_profile_sha256"] = "d" * 64
    assert PilotLaunch.model_validate(value).evidence_only
    value["evidence_only"] = False
    with pytest.raises(ValueError, match="pinned draft profile"):
        PilotLaunch.model_validate(value)


def test_finalized_records_with_orphan_dispatch_are_not_complete(tmp_path):
    repo, principal, specimens, launch = fixture(tmp_path)
    admission = PilotAdmission(repo, launch)
    admission.begin_step(repo.get(principal.scope, specimens[0].id))
    admission.abandon_dispatch(specimens[0].id)
    for binding in launch.specimens:
        specimen = repo.get(principal.scope, binding.specimen_id)
        specimen.run.stage = "finalized"
        repo.save(principal, specimen, specimen.version, "finalized", "finalized")
    worker = PilotWorker(
        repo,
        SimpleNamespace(),
        principal.user_id,
        lambda uid: [dict(principal.scope.model_dump(), role="reviewer")],
        admission,
    )
    summary = worker.result_summary()
    assert summary["status"] == "incomplete"
    assert summary["unresolved_dispatches"] == 1


def test_sam_approval_gate_precedes_remote_work(monkeypatch):
    from specimen_digitization.application.production import ProductionAdapters

    monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE", raising=False)
    with pytest.raises(OperationalBlock, match="spending_approval"):
        ProductionAdapters.segment(SimpleNamespace(), SimpleNamespace())


def test_provider_5xx_is_unknown_not_retryable():
    from pydantic_ai.exceptions import ModelHTTPError
    from specimen_digitization.application.reliability import (
        run_agent_bounded,
        AdapterFailure,
    )

    class Agent:
        async def run(self, *args, **kwargs):
            raise ModelHTTPError(502, "model", {"error": "gateway"})

    with pytest.raises(AdapterFailure) as raised:
        run_agent_bounded(Agent(), "fixture", timeout_seconds=1, usage_limits=None)
    assert raised.value.outcome_unknown


def test_private_config_refuses_symlink_pipe_and_public_file(tmp_path):
    import os
    from specimen_digitization.application.private_config import read_private

    private = tmp_path / "private.json"
    private.write_bytes(b"{}")
    private.chmod(0o600)
    assert read_private(private) == b"{}"
    linked = tmp_path / "link.json"
    linked.symlink_to(private)
    with pytest.raises(OSError):
        read_private(linked)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(ValueError):
        read_private(fifo)
    private.chmod(0o644)
    with pytest.raises(ValueError):
        read_private(private)


def test_private_config_rejects_git_via_symlinked_ancestor(tmp_path):
    from specimen_digitization.application.private_config import read_private

    repo = tmp_path / "repository"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    (repo / ".git").write_text("gitdir: fixture")
    secret = nested / "config.json"
    secret.write_bytes(b"{}")
    secret.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(nested, target_is_directory=True)
    with pytest.raises(ValueError, match="outside Git"):
        read_private(alias / "config.json")
