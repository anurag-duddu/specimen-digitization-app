"""HTTP-level carry behavior with authoritative synthetic SQL Connect proof rows.

The named transport is a local fixture, not deployed/native SQL evidence.  The
repository, snapshot verifier, review-proof reader, API routes and workflow are
the real implementations.
"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import create_app, SYNTHETIC_COLLECTION, SYNTHETIC_ORG, SYNTHETIC_TEXT
from specimen_digitization.application.active_graph import unpack
from specimen_digitization.application.collection_profiles import insects_registry
from specimen_digitization.application.domain import (
    AuditEvent, Asset, Disposition, Evidence, FieldValue, MANDATORY, Principal,
    Profile, Run, Scope, Specimen,
)
from specimen_digitization.application.lane import run_status
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import SyntheticAdapters, Workflow
from test_application import PREFIX, image_bytes
from test_lane_trigger import RecordingDispatcher, registry as lane_registry
from test_projection_writer import Response
from test_review_projection_provenance import CanonicalSession


ACTORS = ("reviewer-a", "reviewer-b")
BASE_HEADERS = {"Authorization": "Bearer reviewer-a"}


def _synthetic_registry():
    registry = lane_registry()
    published_fixture = insects_registry(synthetic=True).profiles[0]
    profiles = tuple(
        profile.model_copy(update={
            "synthetic": True,
            "institutional_policy_approved": True,
            "semantics_confirmed": True,
            "language_handling": published_fixture.language_handling,
            "scoring_policy_ref": published_fixture.scoring_policy_ref,
            "segmentation_settings": published_fixture.segmentation_settings,
        })
        for profile in registry.profiles
    )
    return registry.model_copy(update={"profiles": profiles})


class CarryApiSession(CanonicalSession):
    """CanonicalSession plus only the named reads needed by ordinary HTTP routes."""

    def __init__(self, blobs):
        super().__init__()
        self.active = set(ACTORS)
        self.blobs = blobs
        self.scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        self.specimen_id = None

    def _latest(self):
        if not self.snapshots:
            return None
        return self.snapshots[max(self.snapshots)]

    def _specimen(self, row=None):
        row = row or self._latest()
        return unpack(row["snapshot"], self.blobs)

    def _search_row(self):
        specimen = self._specimen()
        return {
            "id": specimen.id,
            "revision": specimen.version,
            "status": run_status(specimen.run),
            "stage": specimen.run.stage,
            "disposition": specimen.run.disposition.value if specimen.run.disposition else None,
            "sensitive": specimen.asset.sensitive,
            "createdAt": specimen.created_at,
            "domainCreatedAt": specimen.created_at,
            "updatedAt": specimen.created_at,
            "assetId": specimen.asset.id,
            "batchId": specimen.batch_id,
            "filename": specimen.asset.filename,
            "uploader": specimen.asset.uploader,
            "activeRunId": specimen.run.id,
            "blocker": specimen.run.blocker,
            "profileId": specimen.run.profile.id,
            "profileVersion": specimen.run.profile.version,
            "reasonCodes": specimen.run.reasons,
            "risk": specimen.run.review_risk.get("composite"),
            "synthetic": specimen.run.profile.synthetic,
        }

    def post(self, url, json, timeout):
        operation, variables = json["operationName"], deepcopy(json["variables"])
        if operation == "GetSnapshot":
            self.calls.append((operation, variables))
            return Response({"data": {"specimenSnapshot": deepcopy(self.snapshots.get(variables["revision"]))}})
        if operation == "GetReprocessActionReceiptsV1":
            self.calls.append((operation, variables))
            if variables["organizationId"] != self.scope.organization_id or variables["collectionId"] != self.scope.collection_id:
                return Response({"data": {"requestReceipts": []}})
            rows = [{**deepcopy(row), "operation": saved_operation}
                for (actor, saved_operation, key), row in self.receipts.items()
                if actor == variables["actorUid"] and saved_operation.startswith("save:")
                and key == variables["idempotencyKey"] and row["revision"] == variables["resultingRevision"]]
            return Response({"data": {"requestReceipts": rows[:2]}})
        if operation == "SaveSpecimenV3" and max(self.snapshots, default=0) != variables.get("expectedRevision"):
            self.calls.append((operation, variables))
            return Response({"errors": [{"message": "stale revision", "extensions": {"code": "CONFLICT"}}]})
        if operation == "GetSpecimen":
            self.calls.append((operation, variables))
            current = self._latest()
            if current is None or variables["id"] != self.specimen_id:
                return Response({"data": {"specimen": None, "specimenSnapshots": []}})
            return Response({"data": {
                "specimen": {
                    "id": self.specimen_id,
                    "revision": current["revision"],
                    "sensitive": self._specimen(current).asset.sensitive,
                },
                "specimenSnapshots": [{"revision": current["revision"]}],
            }})
        if operation == "SearchSpecimens":
            self.calls.append((operation, variables))
            row = self._search_row()
            if variables.get("specimenId") not in (None, self.specimen_id):
                return Response({"data": {"items": []}})
            if variables.get("activeRunId") not in (None, row["activeRunId"]):
                return Response({"data": {"items": []}})
            return Response({"data": {"items": [row]}})
        if operation == "ListSnapshotHistory":
            self.calls.append((operation, variables))
            through = variables.get("throughRevision") or max(self.snapshots, default=0)
            rows = [
                {key: value for key, value in self.snapshots[revision].items()
                 if key in {"revision", "snapshot", "sha256", "contractVersion"}}
                for revision in sorted(self.snapshots)
                if variables["afterRevision"] < revision <= through
            ][: variables["limit"]]
            return Response({"data": {"specimenSnapshots": rows}})
        response = super().post(url, json, timeout)
        # requests.Response.json() decodes a fresh object graph per call; mirror
        # that boundary so application mutations cannot edit an immutable row.
        if operation == "GetReviewSaveProofV1":
            return Response(deepcopy(response.body), response.status_code)
        return response


class CarryApiCase:
    def __init__(self, path, *, repository_kind="named"):
        self.root = path
        self.blobs = LocalBlobs(path / "blobs")
        self.registry = _synthetic_registry()
        self.dispatcher = RecordingDispatcher()
        self.sensitive_access = {actor: True for actor in ACTORS}
        if repository_kind == "named":
            self.session = CarryApiSession(self.blobs)
            self.repository = SqlConnectRepository(session=self.session, graph_blobs=self.blobs)
        else:
            self.session = None
            self.repository = SQLiteRepository(path / "records.sqlite3")

        source = image_bytes()
        source_ref = self.blobs.put(source)
        profile_row = self.registry.profiles[0]
        profile = Profile(
            id=profile_row.id,
            version=profile_row.version,
            schema_version=profile_row.schema_version,
            policy_version=profile_row.clearance_policy,
            mandatory_fields=profile_row.mandatory_fields,
            routes=profile_row.model_routes,
            synthetic=True,
            institutional_policy_approved=True,
            semantics_confirmed=True,
        )
        evidence_bytes = b"Synthetic label is too incomplete to resolve this field."
        evidence_ref = self.blobs.put(evidence_bytes)
        evidence = Evidence(
            kind="label_region",
            asset_id=None,
            source="synthetic-review-fixture",
            locator="fixture:unresolved-label",
            excerpt=evidence_bytes.decode(),
            raw_ref=evidence_ref,
            digest=evidence_ref,
        )
        asset = Asset(
            sha256=source_ref,
            blob_ref=source_ref,
            media_type="image/png",
            size_bytes=len(source),
            width=120,
            height=80,
            filename="carry-fixture.png",
            uploader=ACTORS[0],
            sensitive=False,
        )
        evidence.asset_id = asset.id
        run = Run(profile=profile, stage="finalized", disposition=Disposition.REVIEW)
        run.profile_snapshot = profile_row.model_dump(mode="json")
        run.profile_registry_version = self.registry.version
        run.dependencies.update(
            profile_snapshot_sha256=digest(run.profile_snapshot),
            profile_registry_version=self.registry.version,
        )
        run.classification_selection = {
            "collection_id": SYNTHETIC_COLLECTION,
            "actor_id": ACTORS[0],
            "reason": "Explicit synthetic fixture selection",
        }
        run.fields = {
            key: FieldValue(state="unknown", reason="No supported source value", evidence_ids=[evidence.id])
            for key in MANDATORY
        }
        run.evidence.append(evidence)
        specimen = Specimen(
            scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
            asset=asset,
            run=run,
            audit=[AuditEvent(actor=ACTORS[0], action="ingest", reason="Synthetic API fixture")],
        )
        if self.session is not None:
            self.session.specimen_id = specimen.id
        principal = Principal(user_id=ACTORS[0], scope=specimen.scope, role="reviewer")
        token = actor_uid.set(ACTORS[0])
        try:
            self.current = self.repository.create(principal, specimen, "fixture-create", digest("fixture-create"))
        finally:
            actor_uid.reset(token)

        adapters = SyntheticAdapters(self.blobs, SYNTHETIC_TEXT)
        self.workflow = Workflow(
            self.repository,
            self.blobs,
            adapters,
            profile_registry=self.registry,
        )
        members = lambda actor: [{
            "organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION,
            "role": "reviewer",
            "can_view_sensitive": self.sensitive_access[actor],
        }] if actor in ACTORS else []
        app = create_app(
            mode="emulator",
            repository=self.repository,
            blobs=self.blobs,
            adapters=adapters,
            identity_verifier=lambda bearer, _app_check: bearer,
            memberships=members,
            profile_registry=self.registry,
            worker_dispatcher=self.dispatcher,
        )
        self.client = TestClient(app, raise_server_exceptions=False)

    @property
    def prefix(self):
        return PREFIX

    def headers(self, actor, key):
        return {"Authorization": f"Bearer {actor}", "Idempotency-Key": key}

    def workspace(self, actor=ACTORS[0]):
        return self.client.get(
            f"{self.prefix}/specimens/{self.current.id}/workspace",
            headers=self.headers(actor, "workspace-read"),
        )

    def save_unknown(self, field, reason, *, actor=ACTORS[0], evidence_id=None, revision=None, key=None):
        current = self.workspace(actor).json()
        evidence_id = evidence_id or current["evidence"][0]["evidence_id"]
        revision = current["revision"] if revision is None else revision
        active_run_id = current["active_run_id"]
        return self.client.post(
            f"{self.prefix}/specimens/{self.current.id}/decisions",
            headers=self.headers(actor, key or f"save-{field}-{revision}-{actor}"),
            json={
                "expected_revision": revision,
                "base_record_version_id": f"{active_run_id}:{revision}",
                "kind": "field",
                "target_id": field,
                "after": {"state": "unknown", "reason": reason},
                "evidence_ids": [evidence_id],
                "reason": reason,
            },
        )

    def reprocess(self, actor=ACTORS[0], *, revision=None, key="reprocess"):
        current = self.workspace(actor).json()
        revision = current["revision"] if revision is None else revision
        return self.client.post(
            f"{self.prefix}/runs/{current['active_run_id']}/actions",
            headers=self.headers(actor, key),
            json={"expected_revision": revision, "action": "reprocess", "reason": "Reprocess while retaining saved uncertainty"},
        )


@pytest.fixture
def case(tmp_path):
    value = CarryApiCase(tmp_path)
    yield value
    value.client.close()


def _assert_unknown(workspace, field, reason):
    value = workspace["fields"][field]
    assert value["value_state"] == "unknown"
    assert value["reason"] == reason


def test_http_saves_reprocess_and_history_keep_two_unknown_fields_through_parse(case):
    evidence_id = case.workspace().json()["evidence"][0]["evidence_id"]
    first = case.save_unknown("city", "No supported city appears on the label", evidence_id=evidence_id)
    assert first.status_code == 200, first.text
    city_event = next(event for event in first.json()["events"] if event["action"] == "review_field" and event["after"].get("field_key") == "city")
    second = case.save_unknown("elevation_from_m", "The label gives no elevation", evidence_id=evidence_id)
    assert second.status_code == 200, second.text
    elevation_event = next(event for event in second.json()["events"] if event["action"] == "review_field" and event["after"].get("field_key") == "elevation_from_m")

    response = case.reprocess(key="reprocess-two-fields")
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == second.json()["revision"] + 1
    assert case.dispatcher.calls == 1

    # Advance with only local deterministic adapters. This exercises pin,
    # classify and parse without a provider call or deployed worker.
    token = actor_uid.set(ACTORS[0])
    try:
        principal = Principal(user_id=ACTORS[0], scope=case.current.scope, role="reviewer")
        current = case.workflow.step(principal, case.current.id)
        for _ in range(30):
            if "parse" in current.run.completed_steps or current.run.stage in {"finalized", "processing_blocked"}:
                break
            current = case.workflow.step(principal, case.current.id)
        case.current = current
    finally:
        actor_uid.reset(token)
    workspace = case.workspace().json()
    _assert_unknown(workspace, "city", "No supported city appears on the label")
    _assert_unknown(workspace, "elevation_from_m", "The label gives no elevation")
    assert "parse" in workspace["run"]["completed_steps"]
    assert {event["id"] for event in workspace["decisions"]} >= {city_event["id"], elevation_event["id"]}
    history = case.client.get(
        f"{case.prefix}/specimens/{case.current.id}/history?after_revision=0",
        headers=case.headers(ACTORS[0], "history-read"),
    )
    assert history.status_code == 200, history.text
    revisions = {item["revision"] for item in history.json()["items"]}
    assert {1, first.json()["revision"], second.json()["revision"], response.json()["revision"]} <= revisions
    assert case.session.calls and any(op == "GetReviewSaveProofV1" for op, _ in case.session.calls)


def test_later_same_value_save_supersedes_only_its_field(case):
    evidence_id = case.workspace().json()["evidence"][0]["evidence_id"]
    first_city = case.save_unknown("city", "Original city review", evidence_id=evidence_id)
    assert first_city.status_code == 200, first_city.text
    elevation = case.save_unknown("elevation_from_m", "Elevation remains unknown", evidence_id=evidence_id)
    assert elevation.status_code == 200, elevation.text
    first_reprocess = case.reprocess(key="reprocess-first"); assert first_reprocess.status_code == 200, first_reprocess.text
    carried = case.workspace().json()
    city_origin_1 = next(event for event in carried["decisions"] if event["action"] == "review_field" and event["after"].get("field_key") == "city")
    elevation_origin = next(event for event in carried["decisions"] if event["action"] == "review_field" and event["after"].get("field_key") == "elevation_from_m")

    later = case.save_unknown("city", "Same uncertainty, reviewed again", actor=ACTORS[1])
    assert later.status_code == 200, later.text
    city_origin_2 = next(event for event in later.json()["decisions"] if event["action"] == "review_field" and event["after"].get("field_key") == "city" and event["actor"] == ACTORS[1])
    second_reprocess = case.reprocess(actor=ACTORS[1], key="reprocess-second")
    assert second_reprocess.status_code == 200, second_reprocess.text
    current = case.workspace(ACTORS[1]).json()
    _assert_unknown(current, "city", "Same uncertainty, reviewed again")
    _assert_unknown(current, "elevation_from_m", "Elevation remains unknown")
    city_events = [event for event in current["decisions"] if event["action"] == "review_field" and event["after"].get("field_key") == "city"]
    elevation_events = [event for event in current["decisions"] if event["action"] == "review_field" and event["after"].get("field_key") == "elevation_from_m"]
    assert city_events[-1]["id"] == city_origin_2["id"] != city_origin_1["id"]
    assert city_events[-1]["actor"] == ACTORS[1]
    assert elevation_events[-1]["id"] == elevation_origin["id"]


def test_stale_revision_and_invalid_authoritative_proof_hold_before_dispatch(case):
    saved = case.save_unknown("city", "Unresolved in a stale-write test")
    assert saved.status_code == 200, saved.text
    before = case.workspace().json()
    calls_before = case.dispatcher.calls
    stale = case.reprocess(revision=saved.json()["revision"] - 1, key="reprocess-stale")
    assert stale.status_code == 409, stale.text
    after_stale = case.workspace().json()
    assert (after_stale["active_run_id"], after_stale["revision"]) == (before["active_run_id"], before["revision"])
    assert case.dispatcher.calls == calls_before

    # Damage the retained server save-audit row, not the local snapshot/event.
    latest_save = next(row for row in reversed(case.session.audit) if row["revision"] == saved.json()["revision"])
    latest_save["actorUid"] = "unrelated-actor"
    invalid = case.reprocess(key="reprocess-proof-invalid")
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["message"] in {
        "review_decision_provenance_invalid",
        "preserved_human_field_provenance_unavailable",
    }
    after_invalid = case.workspace().json()
    assert (after_invalid["active_run_id"], after_invalid["revision"]) == (before["active_run_id"], before["revision"])
    assert case.dispatcher.calls == calls_before


def test_sqlite_event_alone_is_not_authoritative_carry_proof(tmp_path):
    case = CarryApiCase(tmp_path, repository_kind="sqlite")
    try:
        saved = case.save_unknown("city", "Local event has no named server save audit")
        assert saved.status_code == 200, saved.text
        before = case.workspace().json()
        calls_before = case.dispatcher.calls
        refused = case.reprocess(key="reprocess-sqlite-unproved")
        assert refused.status_code == 422, refused.text
        assert "preserved_human_field_provenance_unavailable" in refused.text
        after = case.workspace().json()
        assert (after["active_run_id"], after["revision"]) == (before["active_run_id"], before["revision"])
        assert case.dispatcher.calls == calls_before
    finally:
        case.client.close()
