"""Offline G38 HTTP checks with real saved choices, proofs, blobs and canonical CAS.

Native binding discovery is the candidate fixture's explicit source-only fake.
Native save audits are simulated in a separate SQLite table at actual save
time; ReviewProofReader and the derivation provenance collector remain real.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT, create_app, local_app,
)
from specimen_digitization.application.domain import FieldValue, Principal, Scope, ValueState
from specimen_digitization.application.storage import (
    LocalBlobs, ReviewProofReader, ReviewSnapshot, SQLiteRepository, digest,
)
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.research_harness.derivation_service import DEPENDENCY_KEY
from test_decisions_batch import HEADERS, TOKEN, processed
from test_research_candidate_decisions import (
    BoundDiscovery, RetainedResearch, choice, post, reopen, research_base,
)


class ProofRepository(SQLiteRepository):
    """Actual immutable local snapshots plus independently recorded fake native audits."""

    def __init__(self, path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS fixture_save_audits (id TEXT, org TEXT, collection TEXT, specimen TEXT, revision INTEGER, actor TEXT, UNIQUE(org,collection,specimen,revision))")

    def save(self, principal, specimen, expected_revision, key, request_digest):
        saved = super().save(principal, specimen, expected_revision, key, request_digest)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO fixture_save_audits VALUES (?,?,?,?,?,?)",
                (str(uuid4()), saved.scope.organization_id, saved.scope.collection_id,
                 saved.id, saved.version, principal.user_id))
        return saved

    def _review_proofs(self, scope, specimen):
        def snapshot(revision):
            with self.connect() as db:
                row = db.execute("SELECT payload,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision=?",
                    (scope.organization_id, scope.collection_id, specimen.id, revision)).fetchone()
            payload = json.loads(row[0])
            assert digest(payload) == row[1]
            return ReviewSnapshot(payload, row[1], self.version(scope, specimen.id, revision))

        def save_audits(base, result, event, prior, target):
            with self.connect() as db:
                rows = db.execute("SELECT id,actor FROM fixture_save_audits WHERE org=? AND collection=? AND specimen=? AND revision=? AND actor=?",
                    (scope.organization_id, scope.collection_id, specimen.id, result, event["actor"])).fetchall()
            return {"saveAudits": [{"id": row[0], "organizationId": scope.organization_id,
                "collectionId": scope.collection_id, "specimenId": specimen.id,
                "revision": result, "actorUid": row[1], "action": "checkpoint_or_review"}
                for row in rows]}

        return ReviewProofReader(specimen, snapshot, save_audits).prove(), None


@pytest.fixture
def derivation(tmp_path):
    with TestClient(local_app(tmp_path, TOKEN)) as intake:
        def public_post(url, **kwargs):
            if url.endswith(("/batches", "/items")):
                kwargs["json"] = {**kwargs["json"], "sensitive": False}
            return intake.post(url, **kwargs)
        record = processed(SimpleNamespace(post=public_post, put=intake.put), 1)
    repository = ProofRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repository.get(scope, record["specimen_id"])
    assert specimen.asset.sensitive is False
    for key in ("city", "elevation_from_m"):
        specimen.run.fields[key] = FieldValue(state=ValueState.UNRESOLVED)
    specimen = repository.save(principal, specimen, specimen.version,
        "unresolved-source-fixture", digest("unresolved-source-fixture"))
    blobs = LocalBlobs(tmp_path / "blobs")
    research = RetainedResearch(tmp_path, specimen)
    access = SimpleNamespace(role="reviewer", sensitive=True, member=True)
    app = create_app(mode="emulator", repository=repository, blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda *_: "synthetic-reviewer",
        memberships=lambda _: [{"organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION, "role": access.role,
            "can_view_sensitive": access.sensitive}] if access.member else [])
    discovery = BoundDiscovery(repository, specimen, research)
    app.state.research_discovery.current = discovery
    with TestClient(app, raise_server_exceptions=False) as http:
        fixture = SimpleNamespace(client=http, app=app, repository=repository, scope=scope,
            principal=principal, record=record, original=specimen, research=research,
            discovery=discovery, blobs=blobs, access=access, wakes=[], schedules=[])
        fixture.record = reopen(fixture)
        assert post(fixture, [choice(fixture)])["applied"] == 1
        fixture.selected = reopen(fixture)
        fixture.app.state.research_derivation.wake_worker = lambda: fixture.wakes.append("wake")

        def schedule(principal, saved, command):
            from specimen_digitization.research_harness.derivation_contracts import DerivationScheduleReceipt
            from specimen_digitization.research_harness.persistence import StaleWork

            assert principal.scope == saved.scope
            assert saved.version == command.queued_revision
            current = repository.get(principal.scope, saved.id)
            if (current.version != command.queued_revision
                    or current.run.id != command.canonical_run_id):
                raise StaleWork("derivation_schedule_current_revision_changed")
            fixture.schedules.append((principal.user_id, saved.version, command.id, saved.run.id))
            # Explicit synthetic operational receipt; no native SQL scheduling
            # or worker execution is claimed by this API test fixture.
            return DerivationScheduleReceipt(request_id=command.id,
                queued_revision=command.queued_revision, canonical_run_id=saved.run.id)

        fixture.app.state.research_derivation.schedule_derivation = schedule
        yield fixture


def url(fixture):
    return research_base(fixture) + "/derivations"


def enable(fixture):
    fixture.app.state.research_derivation.ready = lambda *_: True


def request(fixture, **changes):
    current = fixture.selected
    return {"expected_record_revision": current["revision"],
        "base_record_version_id": current["record_version_id"],
        "requested_fields": ["city", "elevation_from_m"],
        "reason": "Derive unresolved geography from the saved human choice", **changes}


def enqueue(fixture, body=None, key="derive-request"):
    return fixture.client.post(url(fixture),
        headers={**HEADERS, "Idempotency-Key": key}, json=body or request(fixture))


def capability(fixture):
    response = fixture.client.get(url(fixture) + "/capability", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def save_fixture(fixture, change, key):
    specimen = fixture.repository.get(fixture.scope, fixture.record["specimen_id"])
    change(specimen)
    return fixture.repository.save(fixture.principal, specimen, specimen.version, key, digest(key))


def test_capability_requires_explicit_ready_worker_and_reads_real_saved_input_proof(derivation):
    before = derivation.repository.get(derivation.scope, derivation.record["specimen_id"])
    assert capability(derivation)["blocked_reason"] == "derivation_worker_unavailable"
    enable(derivation)
    result = capability(derivation)
    assert result["available"] is True, result
    assert set(result["eligible_fields"]) == {"city", "elevation_from_m"}
    assert result["canonical_revision"] == before.version
    assert derivation.repository.get(derivation.scope, before.id) == before
    assert derivation.wakes == []


def test_queue_is_one_canonical_save_preserving_science_and_copying_verified_provenance(derivation):
    enable(derivation)
    before = derivation.selected
    response = enqueue(derivation)
    assert response.status_code == 202, response.text
    accepted = response.json()
    after = reopen(derivation)
    assert after["revision"] == before["revision"] + 1 == accepted["queued_revision"]
    assert after["stage"] == before["stage"] == "finalized"
    assert after["disposition"] == before["disposition"]
    for key in ("fields", "evidence", "observations", "transcripts"):
        assert after["run"][key] == before["run"][key]
    assert after["run"]["dependencies"]["human_review_field_locks"] == before["run"]["dependencies"]["human_review_field_locks"]
    command = after["run"]["dependencies"][DEPENDENCY_KEY]
    assert command["id"] == accepted["request_id"]
    assert command["human_locked_fields"] == ["country"]
    assert command["requested_fields"] == ["city", "elevation_from_m"]
    assert command["source_revision"] == before["revision"]
    [settled] = command["inputs"]
    assert settled["value"] == "Philippines"
    assert settled["selection_id"] == derivation.research.candidates["country"].selection_id
    provenance = json.loads(derivation.blobs.get(settled["provenance_blob_ref"]))
    assert provenance["source_selection"]["source_candidate"]["match_name"] == "MOUNT APO"
    assert provenance["source_selection"]["source_result"]["status"] == "ambiguous"
    assert provenance["review_decision"]["actor"] == "synthetic-reviewer"
    assert derivation.wakes == ["wake"]
    assert len(derivation.schedules) == 1
    assert derivation.research.store.budget(derivation.research.durable)["settled_micro_usd"] == 0


def test_queue_replay_uses_one_cas_and_preserves_a_later_canonical_revision(derivation):
    enable(derivation)
    first = enqueue(derivation)
    assert first.status_code == 202, first.text
    replay = enqueue(derivation)
    assert replay.status_code == 202 and replay.json() == first.json()
    assert reopen(derivation)["revision"] == first.json()["queued_revision"]
    wakes_before_later = list(derivation.wakes)
    later = save_fixture(derivation,
        lambda s: setattr(s.run.fields["habitat"], "reason", "Later reviewer metadata"), "later-canonical")
    again = enqueue(derivation)
    assert again.status_code == 409, again.text
    assert again.json() == {"detail": "research_state_changed"}
    saved = reopen(derivation)
    assert saved["revision"] == later.version
    assert saved["fields"]["habitat"]["reason"] == "Later reviewer metadata"
    assert len(derivation.schedules) == 2
    assert len(set(derivation.schedules)) == 1
    assert derivation.wakes == wakes_before_later


@pytest.mark.parametrize("changes,status", [
    ({"expected_record_revision": 1}, 409),
    ({"base_record_version_id": "wrong:1"}, 409),
    ({"latitude": 6.99, "longitude": 125.27}, 422),
    ({"requested_fields": ["country"]}, 409),
    ({"requested_fields": ["province_state"]}, 409),
    ({"requested_fields": ["taxon"]}, 422),
    ({"requested_fields": ["invented_field"]}, 422),
])
def test_rejects_stale_client_supplied_or_unavailable_targets_without_mutation(derivation, changes, status):
    enable(derivation)
    response = enqueue(derivation, request(derivation, **changes))
    assert response.status_code == status, response.text
    assert reopen(derivation)["revision"] == derivation.selected["revision"]
    assert derivation.wakes == []


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_enqueue_needs_current_reviewer_membership(derivation, role):
    enable(derivation)
    derivation.access.role = role
    assert capability(derivation)["blocked_reason"] == "derivation_review_required"
    response = enqueue(derivation)
    assert response.status_code == 403, response.text
    assert derivation.wakes == []


def test_sensitive_record_never_gets_derivation_capability_or_queue(derivation):
    enable(derivation)
    save_fixture(derivation, lambda s: setattr(s.asset, "sensitive", True), "sensitive-classification")
    assert capability(derivation)["blocked_reason"] == "derivation_sensitive_denied"
    assert enqueue(derivation).status_code == 403
    assert derivation.wakes == []


def test_missing_native_save_audit_fails_closed_despite_retained_canonical_review_event(derivation):
    enable(derivation)
    with derivation.repository.connect() as db:
        db.execute("DELETE FROM fixture_save_audits WHERE revision=?", (derivation.selected["revision"],))
    result = capability(derivation)
    assert result["available"] is False
    assert result["blocked_reason"] == "derivation_input_proof_unavailable"
    assert derivation.wakes == []


def test_queued_result_needs_no_fresh_binding_and_later_revision_is_stale_without_proposals(derivation):
    enable(derivation)
    accepted = enqueue(derivation)
    assert accepted.status_code == 202, accepted.text
    result_url = url(derivation) + "/" + accepted.json()["request_id"]
    response = derivation.client.get(result_url, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued" and response.json()["stale"] is False
    assert response.json()["proposals"] == []
    later = save_fixture(derivation, lambda s: setattr(s.run.fields["habitat"], "reason", "Later edit"), "result-stale")
    response = derivation.client.get(result_url, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["stale"] is True
    assert response.json()["canonical_revision"] == later.version
    assert response.json()["blocked_reason"] == "derivation_input_revision_changed"
    assert response.json()["proposals"] == []


@pytest.mark.parametrize("denial", ["membership", "sensitive"])
def test_result_rechecks_fresh_acl(derivation, denial):
    enable(derivation)
    accepted = enqueue(derivation)
    assert accepted.status_code == 202, accepted.text
    if denial == "membership":
        derivation.access.member = False
    else:
        save_fixture(derivation, lambda s: setattr(s.asset, "sensitive", True), "protect-result")
        derivation.access.sensitive = False
    response = derivation.client.get(url(derivation) + "/" + accepted.json()["request_id"], headers=HEADERS)
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "research_access_denied"}


@pytest.mark.parametrize("condition,reason", [
    ("busy", "derivation_record_busy"),
    ("blocked", "derivation_record_blocked"),
    ("no_supported_input", "derivation_settled_input_required"),
    ("no_remaining_target", "derivation_no_remaining_fields"),
])
def test_capability_requires_current_reviewable_state_supported_input_and_unresolved_target(derivation, condition, reason):
    enable(derivation)

    def change(specimen):
        if condition == "busy":
            specimen.run.stage = "parse"
        elif condition == "blocked":
            specimen.run.blocker = "offline_fixture_block"
        else:
            for key in ("city", "elevation_from_m"):
                specimen.run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal="Synthetic existing value")

    if condition == "no_supported_input":
        selected = derivation.selected
        response = derivation.client.post(
            f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{selected['specimen_id']}/decisions",
            headers={**HEADERS, "Idempotency-Key": "withdraw-supported-input"},
            json={"expected_revision": selected["revision"],
                "base_record_version_id": selected["record_version_id"],
                "kind": "field", "target_id": "country", "after": {"state": "unresolved"},
                "evidence_ids": [], "reason": "Reviewer withdraws the settled country"})
        assert response.status_code == 200, response.text
        current_revision = response.json()["revision"]
    else:
        current_revision = save_fixture(derivation, change, "capability-" + condition).version
    result = capability(derivation)
    assert result["available"] is False
    assert result["blocked_reason"] == reason
    assert result["canonical_revision"] == current_revision
    assert result["eligible_fields"] == []
    assert derivation.wakes == []


def test_a_genuine_human_unresolved_field_is_locked_against_derivation(derivation):
    enable(derivation)
    selected = derivation.selected
    response = derivation.client.post(
        f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{selected['specimen_id']}/decisions",
        headers={**HEADERS, "Idempotency-Key": "human-abstention"},
        json={"expected_revision": selected["revision"],
            "base_record_version_id": selected["record_version_id"],
            "kind": "field", "target_id": "city", "after": {"state": "unresolved"},
            "evidence_ids": [], "reason": "Reviewer cannot settle this city"})
    assert response.status_code == 200, response.text
    current = response.json()
    available = capability(derivation)
    assert available["available"] is True
    assert available["eligible_fields"] == ["elevation_from_m"]
    refused = enqueue(derivation, request(derivation,
        expected_record_revision=current["revision"],
        base_record_version_id=current["record_version_id"], requested_fields=["city"]))
    assert refused.status_code == 409, refused.text
    assert reopen(derivation)["revision"] == current["revision"]
    assert derivation.wakes == []


def test_readiness_alone_does_not_expose_derivation_without_scheduler(derivation):
    enable(derivation)
    derivation.app.state.research_derivation.schedule_derivation = None
    available = capability(derivation)
    assert available["available"] is False
    response = enqueue(derivation)
    assert response.status_code == 403, response.text
    assert reopen(derivation)["revision"] == derivation.selected["revision"]
    assert derivation.wakes == derivation.schedules == []


@pytest.mark.parametrize("failure", ["conflict", "transport"])
def test_schedule_failure_keeps_command_and_retry_repairs_without_second_canonical_revision(derivation, failure):
    from specimen_digitization.research_harness.persistence import StaleWork

    enable(derivation)
    scheduler = derivation.app.state.research_derivation.schedule_derivation
    attempts = []

    def first_failure(principal, saved, command):
        attempts.append((saved.version, command.id))
        if len(attempts) == 1:
            if failure == "conflict":
                raise StaleWork("derivation_schedule_not_confirmed")
            raise ConnectionError("Offline scheduling transport failed")
        return scheduler(principal, saved, command)

    derivation.app.state.research_derivation.schedule_derivation = first_failure
    response = enqueue(derivation)
    assert response.status_code == (409 if failure == "conflict" else 503), response.text
    retained = reopen(derivation)
    assert retained["revision"] == derivation.selected["revision"] + 1
    assert retained["stage"] == derivation.selected["stage"]
    assert retained["disposition"] == derivation.selected["disposition"]
    assert DEPENDENCY_KEY in retained["run"]["dependencies"]
    assert derivation.wakes == derivation.schedules == []
    repaired = enqueue(derivation)
    assert repaired.status_code == 202, repaired.text
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert reopen(derivation)["revision"] == retained["revision"]
    assert repaired.json()["queued_revision"] == retained["revision"]
    assert len(derivation.schedules) == 1 and derivation.wakes == ["wake"]
    assert len([event for event in reopen(derivation)["decisions"] if event["action"] == "review_derive_rest"]) == 1


@pytest.mark.parametrize("corruption", ["missing", "request", "revision", "run"])
def test_invalid_schedule_receipt_never_returns_accepted_or_wakes_worker(derivation, corruption):
    from specimen_digitization.research_harness.derivation_contracts import DerivationScheduleReceipt

    enable(derivation)

    def invalid_receipt(principal, saved, command):
        if corruption == "missing":
            return None
        receipt = DerivationScheduleReceipt(request_id=command.id,
            queued_revision=command.queued_revision, canonical_run_id=saved.run.id)
        return receipt.model_copy(update={
            "request": {"request_id": "f" * 64},
            "revision": {"queued_revision": command.queued_revision + 1},
            "run": {"canonical_run_id": str(uuid4())},
        }[corruption])

    derivation.app.state.research_derivation.schedule_derivation = invalid_receipt
    response = enqueue(derivation)
    assert response.status_code in {409, 503}, response.text
    saved = reopen(derivation)
    assert saved["revision"] == derivation.selected["revision"] + 1
    assert DEPENDENCY_KEY in saved["run"]["dependencies"]
    assert derivation.wakes == []


class UnreadCaptureStore:
    """No I/O implementation: any capture operation fails this plumbing test."""

    def __init__(self):
        self.calls = []

    def get(self, reference):
        self.calls.append(("get", reference))
        raise AssertionError("Ordinary or queued HTTP work must not read captures")

    def discover(self, locator):
        self.calls.append(("discover", locator))
        raise AssertionError("Ordinary or queued HTTP work must not discover captures")

    def put_at(self, locator, data):
        self.calls.append(("put_at", locator))
        raise AssertionError("Ordinary or queued HTTP work must not write captures")


@pytest.fixture
def capture_plumbing(derivation):
    captures = UnreadCaptureStore()
    assert derivation.app.state.research_derivation.capture_blobs is None
    app = create_app(mode="emulator", repository=derivation.repository, blobs=derivation.blobs,
        adapters=SyntheticAdapters(derivation.blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda *_: "synthetic-reviewer",
        memberships=lambda _: [{"organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION, "role": derivation.access.role,
            "can_view_sensitive": derivation.access.sensitive}] if derivation.access.member else [],
        research_capture_blobs=captures)
    app.state.research_derivation.schedule_derivation = derivation.app.state.research_derivation.schedule_derivation
    app.state.research_derivation.wake_worker = derivation.app.state.research_derivation.wake_worker
    # Keep the default discovery without a current binding. These tests make
    # no computed-proposal or exact-capture acceptance claim.
    with TestClient(app, raise_server_exceptions=False) as http:
        fixture = SimpleNamespace(**vars(derivation))
        fixture.app, fixture.client, fixture.captures = app, http, captures
        yield fixture


def test_optional_capture_store_plumbing_preserves_ordinary_session_and_review(capture_plumbing):
    fixture = capture_plumbing
    assert fixture.app.state.research_derivation.capture_blobs is fixture.captures
    session = fixture.client.get("/v1/session", headers=HEADERS)
    assert session.status_code == 200, session.text
    assert session.json()["user_id"] == "synthetic-reviewer"
    assert reopen(fixture)["fields"] == fixture.selected["fields"]
    response = fixture.client.post(
        f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{fixture.record['specimen_id']}/decisions",
        headers={**HEADERS, "Idempotency-Key": "ordinary-review-with-capture-store"},
        json={"expected_revision": fixture.selected["revision"],
            "base_record_version_id": fixture.selected["record_version_id"],
            "kind": "coverage", "after": {"confirmed": True},
            "reason": "Confirm existing label coverage"})
    assert response.status_code == 200, response.text
    saved = reopen(fixture)
    assert saved["revision"] == fixture.selected["revision"] + 1
    assert saved["fields"] == fixture.selected["fields"]
    assert saved["run"]["coverage_confirmed"] is True
    assert saved["decisions"][-1]["action"] == "review_coverage"
    assert fixture.captures.calls == []


def test_capture_store_plumbing_does_not_read_captures_for_capability_enqueue_or_queued_results(capture_plumbing):
    fixture = capture_plumbing
    enable(fixture)
    assert fixture.app.state.research_derivation.capture_blobs is fixture.captures
    assert capability(fixture)["available"] is True
    accepted = enqueue(fixture)
    assert accepted.status_code == 202, accepted.text
    assert capability(fixture)["blocked_reason"] == "derivation_record_busy"
    queued = fixture.client.get(url(fixture) + "/" + accepted.json()["request_id"], headers=HEADERS)
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    assert queued.json()["proposals"] == []
    replay = enqueue(fixture)
    assert replay.status_code == 202 and replay.json() == accepted.json()
    assert reopen(fixture)["revision"] == accepted.json()["queued_revision"]
    assert fixture.captures.calls == []


def test_blocked_command_never_resolves_old_native_results_or_reads_captures(capture_plumbing):
    fixture = capture_plumbing
    enable(fixture)
    accepted = enqueue(fixture)
    assert accepted.status_code == 202
    current = fixture.repository.get(fixture.scope, fixture.record["specimen_id"])
    blocked = current.model_copy(deep=True)
    blocked.run.dependencies[DEPENDENCY_KEY]["status"] = "blocked"
    blocked.run.dependencies[DEPENDENCY_KEY]["blocked_reason"] = "source_unavailable"
    service = fixture.app.state.research_derivation
    service.load_specimen = lambda *_: blocked
    calls = []

    async def forbidden_prior_result(*_):
        calls.append("native discovery")
        raise AssertionError("A blocked command must not resolve an older completed result")

    service.discovery = SimpleNamespace(bound_state=forbidden_prior_result)
    response = fixture.client.get(url(fixture) + "/" + accepted.json()["request_id"], headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"
    assert response.json()["blocked_reason"] == "source_unavailable"
    assert response.json()["proposals"] == []
    assert calls == fixture.captures.calls == []
    assert fixture.repository.get(fixture.scope, current.id) == current
