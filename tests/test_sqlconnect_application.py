"""Opt-in real PostgreSQL/SQL Connect adapter test; never targets cloud endpoints."""

import os
import pytest
from specimen_digitization.application.domain import (
    Asset,
    Principal,
    Profile,
    Run,
    Scope,
    Specimen,
)
from specimen_digitization.application.production import (
    sql_emulator_host,
    SqlConnectRepository,
    actor_uid,
)
from specimen_digitization.application.storage import LocalBlobs, Conflict, digest
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters
from specimen_digitization.application.api import (
    SYNTHETIC_TEXT,
    SYNTHETIC_ORG,
    SYNTHETIC_COLLECTION,
)
from specimen_digitization.application.demo import fixture


@pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)
def test_real_sql_adapter_workflow_cas_and_reconstruction(tmp_path, monkeypatch):
    graph_blobs = LocalBlobs(tmp_path / "graphs")
    repo = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=graph_blobs
    )
    actor_uid.set("synthetic-reviewer")
    scope = Scope(
        organization_id=SYNTHETIC_ORG,
        collection_id=SYNTHETIC_COLLECTION,
    )
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    assert any(
        m["collection_id"] == scope.collection_id
        for m in repo.memberships(principal.user_id)
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = fixture()
    ref = blobs.put(raw)
    specimen = Specimen(
        scope=scope,
        asset=Asset(
            sha256=ref,
            blob_ref=ref,
            media_type="image/png",
            size_bytes=len(raw),
            width=1000,
            height=520,
            filename="explicit-synthetic.png",
            uploader=principal.user_id,
        ),
        run=Run(
            profile=Profile(
                synthetic=True,
                semantics_confirmed=True,
                institutional_policy_approved=True,
            )
        ),
    )
    specimen = repo.create(
        principal, specimen, "create:" + specimen.id, digest({"id": specimen.id})
    )
    result = Workflow(repo, blobs, SyntheticAdapters(blobs, SYNTHETIC_TEXT)).drain(
        principal, specimen.id
    )
    assert result.run.disposition.value == "needs_human_review"
    assert len(result.run.observations) == 2
    # Search uses the same current fields as the workspace, without loading
    # snapshots per row or exporting their values through the list response.
    from specimen_digitization.application.api import summary
    from specimen_digitization.application.search import SearchFilters
    from specimen_digitization.application.domain import now

    filters = SearchFilters(specimen_id=result.id)
    cutoff = now()
    assert result.asset.sensitive is True
    assert repo.search(scope, filters, cutoff) == []
    rows = repo.search(scope, filters, cutoff, include_sensitive=True)
    assert len(rows) == 1
    assert rows[0]["revision"] == result.version
    assert rows[0]["review_summary"] == summary(result)["review_summary"]
    assert rows[0]["review_summary"] is not None
    assert "fieldReviewStates" not in rows[0] and "fields" not in rows[0]
    old = result.version
    result.run.human_approved = True
    from specimen_digitization.application.policy import finalize

    finalize(result.run)
    result = repo.save(
        principal, result, old, "approve:" + result.id, digest({"approve": result.id})
    )
    assert result.run.disposition.value == "cleared"
    replay = repo.save(
        principal, result, old, "approve:" + result.id, digest({"approve": result.id})
    )
    assert replay == result
    with pytest.raises(Conflict):
        repo.save(
            principal, result, old, "stale:" + result.id, digest({"stale": result.id})
        )
    fresh = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=graph_blobs
    )
    assert fresh.get(scope, result.id) == result
    assert any(s.id == result.id for s in fresh.list(scope))

    # The mandatory engine contract covers the real storage boundary: fields
    # leave the compact snapshot, while both new and legacy graphs still count.
    from specimen_digitization.application import active_graph
    result.run.dependencies["queue_count_fixture"] = "x" * active_graph.GRAPH_THRESHOLD
    result = repo.save(principal, result, result.version, "packed:" + result.id, digest({"packed": result.id}))
    assert result.active_graph and result.active_graph["field_review"]["version"] == "field-review-v1"
    expected = summary(result)["review_summary"]
    with monkeypatch.context() as patch:
        patch.setattr(graph_blobs, "get_bounded_until", lambda *a: pytest.fail("New compact metadata needs no blob read"))
        assert repo.search(scope, filters, now(), include_sensitive=True, hydrate_review=True)[0]["review_summary"] == expected

    original_pack = active_graph.pack
    def legacy_pack(value, blobs):
        payload = original_pack(value, blobs)
        payload["active_graph"].pop("field_review")
        return payload
    with monkeypatch.context() as patch:
        patch.setattr(active_graph, "pack", legacy_pack)
        result = repo.save(principal, result, result.version, "legacy-packed:" + result.id, digest({"legacy-packed": result.id}))
    assert "field_review" not in result.active_graph
    assert repo.get(scope, result.id).run.fields == result.run.fields
    cutoff = now()
    assert repo.search(scope, filters, cutoff) == []
    assert repo.search(scope, filters, cutoff, include_sensitive=True)[0]["review_summary"] is None
    calls = []
    original_execute = repo.execute
    def execute(operation, variables, **kwargs):
        calls.append(operation)
        return original_execute(operation, variables, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(repo, "get", lambda *a: pytest.fail("No per-row workspace reads"))
        patch.setattr(repo, "execute", execute)
        rows = repo.search(scope, filters, cutoff, include_sensitive=True, hydrate_review=True)
    assert calls == ["SearchSpecimens"]
    assert rows[0]["revision"] == result.version
    assert rows[0]["review_summary"] == summary(result)["review_summary"] == expected
    assert not {"activeGraph", "active_graph", "fields", "snapshot", "fieldReviewStates"}.intersection(rows[0])
