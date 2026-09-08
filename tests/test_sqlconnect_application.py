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
from specimen_digitization.application.api import SYNTHETIC_TEXT
from specimen_digitization.application.demo import fixture


@pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)
def test_real_sql_adapter_workflow_cas_and_reconstruction(tmp_path):
    repo = SqlConnectRepository(
        project="demo-specimen-data", emulator_host=sql_emulator_host()
    )
    actor_uid.set("integration-reviewer")
    scope = Scope(
        organization_id="11111111-1111-4111-8111-111111111111",
        collection_id="22222222-2222-4222-8222-222222222222",
    )
    principal = Principal(user_id="integration-reviewer", scope=scope, role="reviewer")
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
        project="demo-specimen-data", emulator_host=sql_emulator_host()
    )
    assert fresh.get(scope, result.id) == result
    assert any(s.id == result.id for s in fresh.list(scope))
