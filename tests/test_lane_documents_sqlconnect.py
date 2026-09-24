"""Opt-in real connector check: the lane's worker writes its own documents
without sensitive access (docs/execution/golive/LANE.md, T2).

Start scripts/data/serve-local.sh on isolated ports, then set
SPECIMEN_TEST_SQL_EMULATOR=true and SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:PORT.
Metadata fixtures only; no images, blobs, models or cloud authentication.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import requests

from specimen_digitization.application.circuit_runtime import RepositoryCircuitStore
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_allowance import ProgramLedger
from specimen_digitization.application.lane_worker import CollectionFence
from specimen_digitization.application.production import (
    SqlConnectRepository,
    actor_uid,
    sql_emulator_host,
)
from specimen_digitization.application.provider_circuit import (
    CircuitKey,
    ProviderCircuit,
)
from specimen_digitization.application.storage import Conflict

pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)


def worker_scope(worker):
    """A fresh scope where the worker is an operator without sensitive access."""
    scope = Scope(organization_id=str(uuid4()), collection_id=str(uuid4()))
    result = requests.post(
        "http://"
        + sql_emulator_host()
        + "/v1/projects/demo-specimen-data/locations/us-east4/services/"
        "specimen-digitization-service:executeGraphql",
        headers={"Authorization": "Bearer owner"},
        json={
            "query": f"""mutation @transaction {{
              organization_insert(data:{{id:"{scope.organization_id}",name:"Lane worker fixture"}})
              collection_insert(data:{{organizationId:"{scope.organization_id}",id:"{scope.collection_id}",name:"Lane worker fixture"}})
              organizationMember_insert(data:{{organizationId:"{scope.organization_id}",uid:"{worker}",active:true}})
              collectionMember_insert(data:{{organizationId:"{scope.organization_id}",collectionId:"{scope.collection_id}",uid:"{worker}",active:true,role:"operator",canViewSensitive:false}})
            }}"""
        },
        timeout=10,
    ).json()
    assert not result.get("errors") and not result.get("code"), result
    return scope


@pytest.fixture
def worker():
    uid = "lane-worker-" + uuid4().hex[:12]
    token = actor_uid.set(uid)
    try:
        yield uid, worker_scope(uid), SqlConnectRepository(
            project="demo-specimen-data", emulator_host=sql_emulator_host()
        )
    finally:
        actor_uid.reset(token)


def test_a_document_not_marked_non_sensitive_is_refused_to_the_worker(worker):
    # The rule the lane's documents depend on: without sensitive access, every
    # worker_cursor write must say "sensitive": false.
    _, scope, repository = worker
    with pytest.raises(Conflict):
        repository.put_document(
            scope, "worker_cursor", str(uuid4()), {"circuit_state": {}}, 0
        )


def test_the_worker_creates_and_renews_its_collection_fence(worker):
    uid, scope, repository = worker
    moment = datetime.now(timezone.utc)
    fence = CollectionFence(repository, scope, uid, "exec-a", clock=lambda: moment)
    assert fence.acquire() == {"revision": 0, "holder": None}
    fence.hold(str(uuid4()), "run-a")
    fence.release()
    stored = fence.read()
    assert (stored["revision"], stored["holder"], stored["sensitive"]) == (3, None, False)
    # Another execution takes the released fence by compare-and-set.
    assert CollectionFence(
        repository, scope, uid, "exec-b", clock=lambda: moment
    ).acquire()["revision"] == 3


def test_the_worker_creates_and_saves_provider_circuit_state(worker):
    _, scope, repository = worker
    moment = datetime.now(timezone.utc)
    circuit = ProviderCircuit(RepositoryCircuitStore(repository, scope), lambda: moment)
    key = CircuitKey(
        organization_id=scope.organization_id,
        collection_id=scope.collection_id,
        provider="fixture",
        config_sha256="1" * 64,
    )
    admission = circuit.admit(key, 20)
    assert admission.status == "permitted"
    assert circuit.record_success(admission.token).status == "recorded"


def test_the_worker_creates_and_saves_the_program_ledger(worker):
    _, scope, repository = worker
    moment = datetime.now(timezone.utc)
    ledger = ProgramLedger(repository, scope, clock=lambda: moment)
    for micros, total in ((15_000, 15_000), (20_000, 35_000)):
        reservation = ledger.reserve(
            5_000_000, micros, specimen_id=str(uuid4()), run_id="run-a",
            step="segment", attempt=1,
        )
        assert reservation.issue is None
        assert reservation.position["reserved_total_micros"] == total
    stored = ledger.read()
    assert (stored["revision"], stored["reserved_total_micros"]) == (2, 35_000)
    assert stored["sensitive"] is False
    refused = ledger.reserve(
        40_000, 10_000, specimen_id=str(uuid4()), run_id="run-a", step="parse", attempt=1
    )
    assert refused.issue == "program_allowance_exhausted"
    # A completed call settles to its cost, giving back the rest (T2c).
    position = ledger.settle(
        5_000_000, 20_000, 1_234, specimen_id=str(uuid4()), run_id="run-a",
        step="transcribe:region-1:handwriting-qwen", attempt=1,
    )
    assert position["reserved_total_micros"] == 35_000 - 20_000 + 1_234
    assert ledger.read()["revision"] == 3
