"""Opt-in: a saved run reads back as its thread through GetRunThreadV1; never cloud.

Run against `scripts/data/serve-local.sh` with SPECIMEN_TEST_SQL_EMULATOR=true, like
tests/test_sqlconnect_projection.py. The thread from the real operation must equal the one
tests/thread_fixtures.py emulates from the writer's writes, which is where the canonical example
comes from.
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

import pytest

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, summary
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.production import (
    SqlConnectRepository,
    actor_uid,
    sql_emulator_host,
)
from specimen_digitization.application.projection import writes
from specimen_digitization.application.storage import LocalBlobs, Missing, digest
from specimen_digitization.application.thread import assemble, keys

from thread_fixtures import TRACE, rows, synthetic_run

pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)
ACTOR = "synthetic-reviewer"
TEMPLATE = "https://logfire.example.test/trace/{trace_id}"


def thread(specimen, data):
    return assemble(
        specimen,
        specimen.run,
        data,
        status=summary(specimen)["status"],
        trace_url_template=TEMPLATE,
    ).model_dump(mode="json")


def test_a_saved_run_reads_back_as_its_thread(tmp_path, caplog):
    token = actor_uid.set(ACTOR)
    try:
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        principal = Principal(user_id=ACTOR, scope=scope, role="reviewer")
        blobs = LocalBlobs(tmp_path / "blobs")
        repo = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host(), graph_blobs=blobs)

        def put(label, data):
            # The image is unique per run: a collection records each source checksum once.
            return blobs.put(data + os.urandom(16) if label == "a" else data)

        def recorded():
            s = synthetic_run(put=put, ident=lambda n: str(uuid4()), scope=scope)
            with caplog.at_level(logging.WARNING):
                saved = repo.create(principal, s, "ingest:" + s.id, digest({"create": s.id}))
            assert not [r for r in caplog.records if "Projection" in r.getMessage()], [r.getMessage() for r in caplog.records]
            return saved

        s, other = recorded(), recorded()
        data = repo.run_thread(scope, s.id, s.run.id, keys(s.run))
        real = thread(s, data)
        emulated = thread(s, rows(writes(s, repo.locate, repo._sized, ACTOR, True), s.id, s.run.id, keys(s.run)))
        assert real == emulated
        # The whole run came back, keyed by the domain's ids.
        left, right = s.run.regions
        assert [r["region_id"] for r in real["regions"]] == [left.id, right.id]
        assert [len(r["readings"]) for r in real["regions"]] == [2, 2]
        assert real["regions"][1]["first_pass"]["unresolved"] is True
        assert real["trace"] == {"trace_id": TRACE, "url": f"https://logfire.example.test/trace/{TRACE}"}
        assert real["tool_calls"][0]["started_at"] == "2026-09-23T12:04:00.000000Z"
        fields = {f["field_key"]: f for f in real["fields"]}
        assert fields["taxon"]["settled_observation_ids"] == [s.run.observations[2].id]
        assert fields["city"]["settled_observation_ids"] == [s.run.observations[0].id]
        assert [e["relation"] for e in fields["taxon"]["evidence"]] == ["decides", "contradicts"]
        assert real["decision"]["findings"][1]["evidence_ids"] == [s.run.lookups[3].id]
        assert real["coverage_check"]["evidence_id"] == s.run.evidence[0].id
        # Another specimen's run and an unknown run read as empty through this specimen.
        assert repo.run_thread(scope, s.id, other.run.id, keys(other.run))["runs"] == []
        assert repo.run_thread(scope, s.id, str(uuid4()), keys(s.run))["runs"] == []
        with pytest.raises(Missing):
            repo.run_thread(scope, str(uuid4()), s.run.id, keys(s.run))
    finally:
        actor_uid.reset(token)
