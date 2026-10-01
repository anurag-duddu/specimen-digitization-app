"""Mounted host tests use synthetic data and a real verified-identity dependency."""

import asyncio
from copy import deepcopy

import httpx
import pytest

from specimen_digitization.application.api import create_app
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.research_harness.canonical_binding import CanonicalBindingSnapshot
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.discovery import ScopedCanonicalReadStore

ORG = "11111111-1111-4111-8111-111111111111"
COLLECTION = "22222222-2222-4222-8222-222222222222"
SPECIMEN = "33333333-3333-4333-8333-333333333333"
RUN = "55555555-5555-4555-8555-555555555555"
CURRENT = f"/v1/organizations/{ORG}/collections/{COLLECTION}/specimens/{SPECIMEN}/research/current"


class NativeReadFixture:
    """An explicit test-only registration, not production binding authority."""

    def __init__(self):
        self.actors = []
        self.unavailable = False
        self.error = None
        self.pins = {"input_digest": "a" * 64, "profile": {"fixture": True}}
        self.canonical = {"organization_id": ORG, "collection_id": COLLECTION,
                          "specimen_id": SPECIMEN, "record_revision": 7,
                          "record_version_id": "44444444-4444-4444-8444-444444444444",
                          "canonical_run_id": RUN, "host_record_version_id": RUN + ":7",
                          "snapshot_sha256": "9" * 64, "sensitive": True}
        identity = {"organization_id": ORG, "collection_id": COLLECTION,
                    "specimen_id": SPECIMEN, "job_id": "test-opaque-job"}
        job = {"identity": identity, "generation": 2, "sensitive": True, "pins": self.pins,
               "record_revision": 7, "binding_digest": digest(self.pins), "paused": False,
               "history": [], "dependencies": {}, "trace_context": None,
               "fields": {str(k): {"locked": False, "revision": 0, "checkpoint": None,
                                    "reuse": None} for k in FieldKey}}
        self.state = {"state_revision": 3, "observed_at": "2026-10-01T00:00:00Z",
                      "job": deepcopy(job), "effects": {}, "outbox": {}, "halted": False,
                      "hold_reasons": ["legacy_live_import_not_confirmed"]}
        version_tuple = {key: self.canonical[key] for key in ("record_revision", "record_version_id",
            "canonical_run_id", "host_record_version_id", "snapshot_sha256")}
        self.row = {"binding_id": "66666666-6666-4666-8666-666666666666", "active": True,
                    "registration_revision": 1, "base_canonical": deepcopy(version_tuple),
                    "current_canonical": deepcopy(version_tuple), "job_id": identity["job_id"],
                    "job_key": digest(identity), "generation": 2,
                    "input_digest": self.pins["input_digest"], "profile_digest": digest(self.pins["profile"]),
                    "runtime_binding_digest": digest(self.pins), "program_key": "existing-program",
                    "policy_digest": "c" * 64, "source_sha256": "e" * 64,
                    "canonical_profile_digest": "f" * 64, "semantic_mapping_digest": "d" * 64,
                    "field_mapping": {str(k): str(k) for k in FieldKey},
                    "human_locks": {str(k): k == FieldKey.TAXON for k in FieldKey},
                    "publication_transition": None, "job": deepcopy(job), "read_bundle": self.state}

        self.row["semantic_mapping"] = {"field_mapping": deepcopy(self.row["field_mapping"]),
            "journal_budget_policy_digest": "b" * 64, "research_policy_origin": "fixture-owner-reviewed"}
        self.row["semantic_mapping_digest"] = digest(self.row["semantic_mapping"])
        self.row["journal_budget_policy_digest"] = "b" * 64
        self.row["journal_budget_policy_origin"] = "verified_owner_registration_not_SQL_recomputed"
        self.row["research_policy_origin"] = "fixture-owner-reviewed"
        self.state.pop("observed_at")
        self.state.update(server_time=100.0, job_key=self.row["job_key"], paused=False)

    def current_research_binding(self, scope, specimen_id):
        self.actors.append(actor_uid.get())
        if self.error:
            raise self.error
        return CanonicalBindingSnapshot.model_validate({
            "canonical": self.canonical, "active_registration_count": 0 if self.unavailable else 1,
            "registrations": [] if self.unavailable else [self.row],
            "snapshot": {"snapshot": {"fixture": "private"}, "sha256": self.canonical["snapshot_sha256"],
                "revision": self.canonical["record_revision"], "contractVersion": "fixture-source"},
            "projection": [],
        })

    def store(self, binding):
        return ScopedCanonicalReadStore(binding, verified_actor=actor_uid.get())


@pytest.fixture
def host(tmp_path):
    native = NativeReadFixture()
    membership_reads = []
    access = {"sensitive": True, "role": "viewer", "revoke_after_first": False}

    def verify(bearer, appcheck):
        if bearer not in {"actor-one", "actor-two"}:
            raise PermissionError("private verifier detail")
        return bearer

    def members(uid):
        membership_reads.append((uid, actor_uid.get()))
        return [{"organization_id": ORG, "collection_id": COLLECTION,
                 "role": access["role"], "can_view_sensitive": access["sensitive"]
                 and not (access["revoke_after_first"] and len(membership_reads) > 1)}]

    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator", repository=SQLiteRepository(tmp_path / "canonical.sqlite3"),
        blobs=blobs, adapters=SyntheticAdapters(blobs, "test-only reading"),
        identity_verifier=verify, memberships=members,
        research_binding_repository=native, research_store_factory=native.store,
    )
    return app, native, access, membership_reads


@pytest.mark.asyncio
async def test_real_host_mount_and_viewer_read_has_no_budget_job_or_lease_effect(host):
    app, native, _, memberships = host
    before = deepcopy(native.state)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(CURRENT, headers={"Authorization": "Bearer actor-one"})
    assert response.status_code == 200
    assert response.json()["scope"]["generation"] == 2
    assert response.json()["scope"]["input_digest"] == "a" * 64
    assert response.json()["canonical"]["record_version_id"] != response.json()["scope"]["job_id"]
    assert response.json()["capabilities"] == {"read": True, "retry": False, "review": False}
    assert "program_id" not in response.text
    assert "budget_policy" not in response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert native.state == before
    assert all(uid == context for uid, context in memberships)
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_concurrent_verified_actors_and_reset_after_requests(host):
    app, native, _, _ = host
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        replies = await asyncio.gather(*(client.get(CURRENT, headers={"Authorization": "Bearer " + uid})
                                        for uid in ("actor-one", "actor-two")))
    assert [r.status_code for r in replies] == [200, 200]
    assert set(native.actors) == {"actor-one", "actor-two"}
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_revoked_sensitive_membership_is_freshly_denied(host):
    app, native, access, _ = host
    access["revoke_after_first"] = True
    before = deepcopy(native.state)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        reply = await client.get(CURRENT, headers={"Authorization": "Bearer actor-one"})
    assert reply.status_code == 403
    assert reply.json() == {"detail": "research_access_denied"}
    assert native.state == before
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_uninstalled_mapping_and_raw_failure_are_private_unavailable(host):
    app, native, _, _ = host
    native.error = RuntimeError("private native failure or path must not escape")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        reply = await client.get(CURRENT, headers={"Authorization": "Bearer actor-one"})
    assert reply.status_code == 503
    assert reply.json() == {"detail": "research_service_unavailable"}
    assert "private native" not in reply.text
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_http_caller_cannot_supply_identity_program_or_capability(host):
    app, _, _, _ = host
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        missing = await client.get(CURRENT)
        injected = await client.get(CURRENT + "?program_id=reset", headers={"Authorization": "Bearer actor-one"})
    assert missing.status_code == 401
    assert injected.status_code == 422
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_viewer_cannot_admit_retry_and_queued_ack_is_not_a_publication(host):
    app, native, _, _ = host
    retry = CURRENT.removesuffix("/current") + "/jobs/test-opaque-job/generations/2/fields/taxon/retry"
    before = deepcopy(native.state)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        reply = await client.post(retry, headers={"Authorization": "Bearer actor-one"},
                                  json={"expected_checkpoint_revision": 1})
    assert reply.status_code == 403
    assert native.state == before
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_cancelled_host_request_resets_actor_without_rebinding_late_thread(host):
    import threading

    app, native, _, _ = host
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    observed = []
    original = native.current_research_binding

    def blocking(scope, specimen_id):
        uid = actor_uid.get()
        if uid == "actor-one":
            started.set()
            release.wait(timeout=2)
            observed.append(actor_uid.get())
            finished.set()
        return original(scope, specimen_id)

    native.current_research_binding = blocking
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        pending = asyncio.create_task(client.get(CURRENT, headers={"Authorization": "Bearer actor-one"}))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            reply = await client.get(CURRENT, headers={"Authorization": "Bearer actor-two"})
            assert reply.status_code == 200
            assert actor_uid.get() is None
        finally:
            release.set()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    assert await asyncio.to_thread(finished.wait, 2)
    assert observed == ["actor-one"]
    assert actor_uid.get() is None


@pytest.mark.asyncio
async def test_mounted_thread_uses_real_checkpoint_reader_and_native_locks(host):
    app, native, _, _ = host
    before = deepcopy(native.state)
    thread = CURRENT.removesuffix("/current") + "/jobs/test-opaque-job/generations/2/thread"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        reply = await client.get(thread, headers={"Authorization": "Bearer actor-one"})
    assert reply.status_code == 200
    value = reply.json()
    assert value["contract_version"] == "research-thread-v1"
    assert len(value["fields"]) == 20
    assert {field["field_key"] for field in value["fields"]} == {str(key) for key in FieldKey}
    taxon = next(field for field in value["fields"] if field["field_key"] == "taxon")
    assert taxon["work_state"] == "waiting_policy"
    assert taxon["checkpoint"] is None
    assert taxon["actions"] == []
    assert value["effects"] == []
    assert all(field["actions"] == [] for field in value["fields"])
    assert "program_key" not in reply.text and "budget_totals" not in reply.text
    assert native.state == before
    assert actor_uid.get() is None
