"""Actual offline queue outcomes without inventing missing Insects semantics.

The six-role case uses real EffectModel/Harness/journal/admission/publication
with recorded sources and the in-memory native connector. Ordinary capability
review uses HTTP, retained unreadable observations, SQLite and immutable bytes.
These fixtures prove local contracts, not model behavior or live acceptance.
"""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

import production_e2e_support as support
import test_unkeyed_label_reading_citation as native_fixture
from test_application import HEADERS, PREFIX, TOKEN, intake
from test_unkeyed_label_reading_citation import build_rig, run_research
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, local_app
from specimen_digitization.application.domain import (
    Disposition, Lookup, LookupStatus, Principal, Scope,
)
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, FieldKey, FieldResolution, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution


@pytest.fixture(autouse=True)
def no_public_http(monkeypatch):
    """Refuse wire transport while retaining the ordinary ASGI test transport."""
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline queue cases perform no public HTTP")

    async def async_refuse(*args, **kwargs):
        raise AssertionError("the offline queue cases perform no public HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_refuse)


def test_all_six_grounded_domains_reach_review_only_for_missing_dts_semantics(tmp_path, monkeypatch):
    original_fixture = native_fixture.specimen_before_adjudication

    def complete_synthetic_coverage(blobs):
        specimen = original_fixture(blobs)
        [region] = specimen.run.regions
        # This constructed image has exactly one known synthetic label and the
        # region covers every pixel. Freeze its fixture coverage declaration
        # before native admission; the real whole-record science still runs.
        assert (region.x, region.y, region.width, region.height) == (
            0, 0, specimen.asset.width, specimen.asset.height)
        specimen.run.coverage_confirmed = True
        return specimen

    monkeypatch.setattr(native_fixture, "specimen_before_adjudication", complete_synthetic_coverage)
    rig, token = build_rig(tmp_path, monkeypatch, (support.LABEL_TEXT,))
    requests = []
    script = support.scripted_model_factory(rig.model_calls)

    def models(request, binding):
        requests.append(request)
        if FieldKey.VERBATIM_DTS in request.field_keys:
            # A supported, genuinely grounded proposal passes schema construction
            # but the actual admission validator still enforces owner semantics.
            proposal = support._literal(request, FieldKey.VERBATIM_DTS)
            assert isinstance(proposal, FieldResolution)
            with pytest.raises(EvidenceError, match="D/T/S semantics remain waiting-policy until definition supplied"):
                validate_resolution(request, proposal)
        return script(request, binding)

    try:
        parsed, result, hold, published = run_research(rig, models)
        _, state = support.research_state(rig.fake, rig.specimen_id)
        [job] = state["jobs"].values()
        receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
        final = receipts[-1]["causal_proof"]["progress_receipt"]
        assert {request.role for request in requests} == set(SpecialistRole)
        assert not script.errors and not script.fallbacks
        assert hold is None and not rig.fake.duplicates
        assert len(published) == len(set(published)) == 19
        assert set(published) == {str(key) for key in ALL_FIELDS} - {"verbatim_dts"}
        assert published[-1] == "identified_by_irn"
        assert result.version == parsed.version + 19
        assert result.run.stage == "finalized" and result.run.disposition == Disposition.REVIEW
        assert result.run.reasons == ["mandatory_unresolved:verbatim_dts"]
        assert (final["wire_status"], final["run_stage"], final["disposition"], final["exportable"]) == (
            "completed", "finalized", "needs_human_review", False)
        assert final["operational_reason_codes"] == []
        assert final["human_reason_codes"] == ["mandatory_unresolved:verbatim_dts"]
        assert len(final["canonical_field_work"]) == len(final["research_field_work"]) == 20
        assert final["research_field_work"] == {key: row["work_state"] for key, row in job["fields"].items()}
        assert job["fields"]["verbatim_dts"]["work_state"] == "waiting_policy"
        assert all(row["work_state"] in {"resolved", "nonblocking_exception"}
            for key, row in job["fields"].items() if key != "verbatim_dts")
        captures = [effect for effect in state["effects"].values()
            if effect["operation_key"].startswith("source_capture_v2:")]
        assert len(captures) == 7 and all(effect["status"] == "completed" for effect in captures)
        assert result.run.fields["taxon"].authority_id
        assert result.run.fields["date_visited_from"].normalized == result.run.fields["date_visited_to"].normalized
        assert result.run.fields["elevation_from_m"].normalized == "180.00"
        assert result.run.fields["elevation_to_m"].normalized == "181.00"
        reopened = rig.repository.get(rig.principal.scope, rig.specimen_id)
        assert reopened.version == result.version and reopened.run.fields == result.run.fields
        assert reopened.run.disposition == Disposition.REVIEW and reopened.run.reasons == result.run.reasons
    finally:
        actor_uid.reset(token)


class UnreadableAdapters(SyntheticAdapters):
    """Two completed independent synthetic routes retain their own unreadable bytes."""

    def transcribe(self, specimen, region, route):
        reading = super().transcribe(specimen, region, route)
        reading.unreadable_spans = ["entire label"]
        return reading


def unreadable_case(tmp_path):
    app = local_app(tmp_path, TOKEN)
    app.state.workflow.adapters = UnreadableAdapters(LocalBlobs(tmp_path / "blobs"), "[unreadable]")
    client = TestClient(app, raise_server_exceptions=False)
    row = intake(client)
    url = PREFIX + "/specimens/" + row["specimen_id"]
    workspace = client.get(url + "/workspace", headers=HEADERS)
    assert workspace.status_code == 200, workspace.text
    base = workspace.json()
    assert len(base["observations"]) == 2
    assert len([step for step in base["run"]["completed_steps"] if step.startswith("transcribe:")]) == 2
    assert len({item["model_id"] for item in base["observations"]}) == 2
    assert all(item["unreadable_spans"] and item["raw_ref"] and item["raw_sha256"]
        for item in base["observations"])
    return client, url, base


def defer_body(base, reason):
    return {"expected_revision": base["revision"], "base_record_version_id": base["record_version_id"],
        "kind": "capability_defer", "reason": "Synthetic source reviewed after both independent attempts",
        "after": {"capability_reason": reason, "retry_eligibility": "new_approved_script_model_or_better_source"}}


@pytest.mark.parametrize("reason", ["unsupported_script", "severe_source_damage"])
def test_legitimate_deferred_review_survives_http_reopen_queue_history_and_exact_replay(tmp_path, reason):
    client, url, base = unreadable_case(tmp_path)
    headers = {**HEADERS, "Idempotency-Key": "capability-review"}
    response = client.post(url + "/decisions", headers=headers, json=defer_body(base, reason))
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["revision"] == base["revision"] + 1
    assert (saved["status"], saved["stage"], saved["disposition"]) == ("completed", "finalized", "deferred")
    assert saved["blocker"] is None
    assert saved["run"]["capability_reason"] == reason and saved["run"]["retry_eligibility"]
    assert "capability_attempts_exhausted" in saved["run"]["completed_steps"]
    assert saved["observations"] == base["observations"]
    assert len(saved["decisions"]) == len(base["decisions"]) + 1
    assert saved["decisions"][-1]["action"] == "review_capability_defer"
    reopened = TestClient(local_app(tmp_path, TOKEN), raise_server_exceptions=False)
    current = reopened.get(url + "/workspace", headers=HEADERS)
    assert current.status_code == 200, current.text
    assert current.json()["revision"] == saved["revision"]
    assert current.json()["disposition"] == "deferred" and current.json()["observations"] == base["observations"]
    queued = reopened.get(PREFIX + "/specimens", headers=HEADERS,
        params={"collection_id": SYNTHETIC_COLLECTION, "state": "completed", "disposition": "deferred"})
    assert queued.status_code == 200, queued.text
    assert [item["specimen_id"] for item in queued.json()["items"]] == [base["specimen_id"]]
    prior = reopened.get(url + "/history/" + str(base["revision"]), headers=HEADERS)
    assert prior.status_code == 200, prior.text
    assert prior.json()["disposition"] != "deferred"
    replay = reopened.post(url + "/decisions", headers=headers, json=defer_body(base, reason))
    assert replay.status_code == 200, replay.text
    assert replay.json()["revision"] == saved["revision"]
    assert len(replay.json()["decisions"]) == len(saved["decisions"])


@pytest.mark.parametrize("reason", ["credential_error", "provider_timeout", "external_outcome_unknown", "source_unavailable"])
def test_operational_reason_cannot_be_saved_as_deferred(tmp_path, reason):
    client, url, base = unreadable_case(tmp_path)
    response = client.post(url + "/decisions", headers=HEADERS, json=defer_body(base, reason))
    assert response.status_code == 422, response.text
    assert "Documented capability reason" in response.json()["error"]["message"]
    current = client.get(url + "/workspace", headers=HEADERS).json()
    assert current["revision"] == base["revision"] and current["disposition"] != "deferred"
    assert current["decisions"] == base["decisions"]


@pytest.mark.parametrize("blocker", ["credential_error", "external_outcome_unknown", "provider_timeout"])
def test_qualified_unreadable_attempts_do_not_hide_a_current_operational_hold(tmp_path, blocker):
    client, url, base = unreadable_case(tmp_path)
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repository.get(scope, base["specimen_id"])
    specimen.run.stage = "processing_blocked"
    specimen.run.blocker = blocker
    specimen.run.disposition = None
    repository.save(principal, specimen, specimen.version, "synthetic-operational-hold", digest({"blocker": blocker}))
    held = client.get(url + "/workspace", headers=HEADERS).json()
    response = client.post(url + "/decisions", headers=HEADERS, json=defer_body(held, "unsupported_script"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["stage"], result["disposition"], result["blocker"]) == ("processing_blocked", None, blocker)
    assert result["observations"] == base["observations"]
    queued = client.get(PREFIX + "/specimens", headers=HEADERS,
        params={"collection_id": SYNTHETIC_COLLECTION, "disposition": "deferred"})
    assert queued.status_code == 200 and queued.json()["items"] == []


def test_unreadable_capability_review_does_not_replace_operational_lookup_with_deferred(tmp_path):
    client, url, base = unreadable_case(tmp_path)
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repository.get(scope, base["specimen_id"])
    raw = b'{"synthetic":true,"status":"rate_limited"}'
    blobs = LocalBlobs(tmp_path / "blobs")
    specimen.run.lookups.append(Lookup(provider="synthetic", adapter_version="1",
        query={"name": "source unavailable"}, status=LookupStatus.RATE_LIMITED,
        raw_ref=blobs.put(raw), digest=hashlib.sha256(raw).hexdigest()))
    repository.save(principal, specimen, specimen.version, "synthetic-lookup-hold", digest({"status": "rate_limited"}))
    held = client.get(url + "/workspace", headers=HEADERS).json()
    response = client.post(url + "/decisions", headers=HEADERS, json=defer_body(held, "severe_source_damage"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["stage"], result["disposition"]) == ("processing_blocked", None)
    assert result["blocker"] is None and "lookup_operational_failure" in result["reason_codes"]


def test_readable_source_cannot_be_saved_as_capability_deferred(tmp_path):
    client = TestClient(local_app(tmp_path, TOKEN), raise_server_exceptions=False)
    row = intake(client)
    url = PREFIX + "/specimens/" + row["specimen_id"]
    base = client.get(url + "/workspace", headers=HEADERS).json()
    assert len(base["observations"]) == 2 and not any(item["unreadable_spans"] for item in base["observations"])
    response = client.post(url + "/decisions", headers=HEADERS, json=defer_body(base, "unsupported_script"))
    assert response.status_code == 422, response.text
    assert "retained unreadable-source observations" in response.json()["error"]["message"]
    current = client.get(url + "/workspace", headers=HEADERS).json()
    assert current["revision"] == base["revision"] and current["disposition"] != "deferred"
    assert current["decisions"] == base["decisions"]


def test_incomplete_independent_attempts_cannot_be_saved_as_capability_deferred(tmp_path):
    client, url, base = unreadable_case(tmp_path)
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    specimen = repository.get(scope, base["specimen_id"])
    # Deliberately incomplete retained proof: the review fence must refuse
    # before any source-integrity/phase refresh or final disposition save.
    specimen.run.observations = specimen.run.observations[:1]
    repository.save(principal, specimen, specimen.version, "synthetic-incomplete-attempts", digest({"attempts": 1}))
    incomplete = client.get(url + "/workspace", headers=HEADERS).json()
    response = client.post(url + "/decisions", headers=HEADERS, json=defer_body(incomplete, "severe_source_damage"))
    assert response.status_code == 422, response.text
    assert "All independent attempts must finish" in response.json()["error"]["message"]
    current = client.get(url + "/workspace", headers=HEADERS).json()
    assert current["revision"] == incomplete["revision"] and current["disposition"] != "deferred"
    assert current["decisions"] == incomplete["decisions"]
