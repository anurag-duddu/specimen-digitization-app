"""Exact current graph counts, bounded compatibility I/O and transport fidelity."""

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct

from specimen_digitization.application.active_graph import (
    GRAPH_THRESHOLD, pack, read_graph, run_summary,
)
from specimen_digitization.application.domain import Asset, FieldValue, Run, Scope, Specimen
from specimen_digitization.application.graph_review_summary import GraphReviewCache
from specimen_digitization.application.search import SearchFilters, sql_item
from specimen_digitization.application.storage import Conflict, LocalBlobs, SQLiteRepository


SCOPE = Scope(organization_id="00000000-0000-4000-8000-000000000001",
              collection_id="00000000-0000-4000-8000-000000000002")
EXPECTED = {"review": 2, "missing": 1}


def specimen():
    return Specimen(scope=SCOPE, asset=Asset(sensitive=False, sha256="a" * 64,
        blob_ref="fixture", media_type="image/png", size_bytes=1, width=1, height=1,
        filename="fixture.png", uploader="reviewer"), run=Run(
            fields={"city": FieldValue(state="supported", literal="Chicago"),
                    "county": FieldValue(state="not_present"),
                    "taxon": FieldValue(state="ambiguous", literal="Apis")},
            reasons=["evidence_missing:city", "evidence_missing:city", "human_approval_required"],
            dependencies={"large_fixture": "x" * GRAPH_THRESHOLD}))


def row_for(payload):
    metadata = payload["active_graph"]
    row = {"id": payload["id"], "revision": payload["version"],
           "activeRunId": payload["run"]["id"], "reasonCodes": payload["run"]["reasons"],
           "activeGraph": metadata,
           "fieldReviewStates": metadata.get("field_review", {}).get("fields")}
    return sql_item(row, SCOPE)


def legacy(blobs):
    payload = pack(specimen(), blobs)
    payload["active_graph"].pop("field_review")
    return payload


def track(blobs, monkeypatch, *, delay=0):
    original = blobs.get_bounded_until
    state = {"calls": 0, "active": 0, "peak": 0}
    lock = threading.Lock()

    def read(*args):
        with lock:
            state["calls"] += 1
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        try:
            time.sleep(delay)
            return original(*args)
        finally:
            with lock:
                state["active"] -= 1
    monkeypatch.setattr(blobs, "get_bounded_until", read)
    return state


def test_new_and_legacy_graph_bytes_and_old_summary_contract_survive_struct(tmp_path):
    blobs = LocalBlobs(tmp_path)
    source = specimen()
    payload = pack(source, blobs)
    raw = blobs.get(payload["active_graph"]["blob_ref"])
    assert payload["run"] == run_summary(source.run.model_dump(mode="json"))
    assert payload["run"]["fields"] == {}
    transport = Struct()
    transport.update(payload)
    transported = MessageToDict(transport)
    assert type(transported["active_graph"]["size_bytes"]) is float
    assert type(transported["active_graph"]["revision"]) is float
    assert row_for(transported)["review_summary"] == EXPECTED
    assert read_graph(transported, blobs)[0] == raw
    transported["active_graph"].pop("field_review")
    assert read_graph(transported, blobs)[0] == raw
    assert row_for(transported)["review_summary"] is None
    cache = GraphReviewCache()
    row = row_for(transported)
    cache.hydrate([row], [transported["active_graph"]], blobs)
    assert row["review_summary"] == EXPECTED
    assert set(row).isdisjoint({"activeGraph", "active_graph", "fieldReviewStates", "fields", "snapshot"})
    assert "Chicago" not in json.dumps(row)


def test_compact_projection_is_bound_to_reasons_and_verified_graph(tmp_path):
    blobs = LocalBlobs(tmp_path)
    payload = pack(specimen(), blobs)
    payload["run"]["reasons"].append("evidence_missing:county")
    assert row_for(payload)["review_summary"] is None
    with pytest.raises(Conflict):
        read_graph(payload, blobs)
    payload = pack(specimen(), blobs)
    payload["active_graph"]["field_review"]["fields"]["city"]["has_value"] = False
    with pytest.raises(Conflict):
        read_graph(payload, blobs)


@pytest.mark.parametrize("fault", ["scope", "specimen", "revision", "run", "size-bool", "size-fraction", "size-limit", "reference", "digest"])
def test_legacy_identity_faults_do_not_read_or_return_counts(tmp_path, monkeypatch, fault):
    blobs = LocalBlobs(tmp_path)
    payload = legacy(blobs)
    row = row_for(payload)
    metadata = payload["active_graph"]
    if fault == "scope": metadata["scope"]["collection_id"] = "foreign"
    elif fault == "specimen": metadata["specimen_id"] = "foreign"
    elif fault == "revision": metadata["revision"] += 1
    elif fault == "run": metadata["run_id"] = "foreign"
    elif fault == "size-bool": metadata["size_bytes"] = True
    elif fault == "size-fraction": metadata["size_bytes"] += 0.5
    elif fault == "size-limit": metadata["size_bytes"] = 16 * 1024 * 1024 + 1
    elif fault == "reference": metadata["blob_ref"] = "b" * 64
    elif fault == "digest": metadata["run_sha256"] = "bad"
    monkeypatch.setattr(blobs, "get_bounded_until", lambda *a: pytest.fail("Invalid identity must not fetch"))
    GraphReviewCache().hydrate([row], [metadata], blobs)
    assert row["review_summary"] is None


@pytest.mark.parametrize("fault", ["bytes", "run-digest", "reasons", "missing"])
def test_legacy_content_faults_are_unknown_and_retryable(tmp_path, monkeypatch, fault):
    blobs = LocalBlobs(tmp_path)
    payload = legacy(blobs)
    metadata = payload["active_graph"]
    row = row_for(payload)
    saved = copy.deepcopy(metadata)
    ref = metadata["blob_ref"]
    raw = blobs.get(ref)
    if fault == "bytes": (tmp_path / ref).write_bytes(b"invalid")
    elif fault == "missing": (tmp_path / ref).unlink()
    elif fault == "run-digest": metadata["run_sha256"] = "b" * 64
    elif fault == "reasons": row["reason_codes"] = ["evidence_missing:county"]
    calls = track(blobs, monkeypatch)
    cache = GraphReviewCache()
    cache.hydrate([row], [metadata], blobs)
    assert row["review_summary"] is None
    (tmp_path / ref).write_bytes(raw)
    repaired = row_for({**payload, "active_graph": saved})
    cache.hydrate([repaired], [saved], blobs)
    assert repaired["review_summary"] == EXPECTED
    assert calls["calls"] == 2


def test_positive_cache_singleflight_and_row_identity(tmp_path, monkeypatch):
    blobs = LocalBlobs(tmp_path)
    payload = legacy(blobs)
    calls = track(blobs, monkeypatch, delay=0.02)
    cache = GraphReviewCache()
    rows = [row_for(payload) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda row: cache.hydrate([row], [payload["active_graph"]], blobs), rows))
    assert all(row["review_summary"] == EXPECTED for row in rows)
    assert calls["calls"] == 1
    assert calls["active"] == 0
    row = row_for(payload)
    cache.hydrate([row], [payload["active_graph"]], blobs)
    assert calls["calls"] == 1
    for name, value in [("revision", 100), ("collection_id", "foreign"), ("active_run_id", "foreign")]:
        row = row_for(payload)
        row[name] = value
        cache.hydrate([row], [payload["active_graph"]], blobs)
        assert row["review_summary"] is None
    assert calls["calls"] == 1


@pytest.mark.parametrize("limit", ["reads", "bytes", "deadline"])
def test_page_budgets_and_joined_concurrency(tmp_path, monkeypatch, limit):
    import specimen_digitization.application.graph_review_summary as module
    blobs = LocalBlobs(tmp_path)
    payloads = [legacy(blobs) for _ in range(5)]
    rows = [row_for(payload) for payload in payloads]
    if limit == "reads": monkeypatch.setattr(module, "PAGE_READS", 2)
    elif limit == "bytes": monkeypatch.setattr(module, "PAGE_BYTES", payloads[0]["active_graph"]["size_bytes"] * 2)
    else: monkeypatch.setattr(module, "PAGE_SECONDS", 0)
    calls = track(blobs, monkeypatch, delay=0.01)
    GraphReviewCache().hydrate(rows, [p["active_graph"] for p in payloads], blobs)
    assert calls["calls"] <= (0 if limit == "deadline" else 2)
    assert calls["peak"] <= 2 and calls["active"] == 0
    assert sum(row["review_summary"] is not None for row in rows) == calls["calls"]


def test_ordinary_26_record_page_and_lru_remain_bounded(tmp_path, monkeypatch):
    import specimen_digitization.application.graph_review_summary as module
    blobs = LocalBlobs(tmp_path)
    payloads = [legacy(blobs) for _ in range(26)]
    rows = [row_for(p) for p in payloads]
    calls = track(blobs, monkeypatch)
    monkeypatch.setattr(module, "CACHE_ENTRIES", 8)
    cache = GraphReviewCache()
    cache.hydrate(rows, [p["active_graph"] for p in payloads], blobs)
    assert all(row["review_summary"] == EXPECTED for row in rows)
    assert calls["calls"] == 26 and calls["peak"] <= 2 and calls["active"] == 0
    assert len(cache._values) == 8 and not cache._inflight


def test_different_pages_share_read_admission_and_join(tmp_path, monkeypatch):
    blobs = LocalBlobs(tmp_path)
    pages = [[legacy(blobs) for _ in range(3)] for _ in range(3)]
    calls = track(blobs, monkeypatch, delay=0.01)
    cache = GraphReviewCache()
    def page(payloads):
        rows = [row_for(p) for p in payloads]
        cache.hydrate(rows, [p["active_graph"] for p in payloads], blobs)
        assert all(row["review_summary"] == EXPECTED for row in rows)
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(page, pages))
    assert calls["calls"] == 9 and calls["peak"] == 2 and calls["active"] == 0
    assert not cache._inflight


def test_exhausted_read_admission_returns_unknown_without_starting_io(tmp_path, monkeypatch):
    import specimen_digitization.application.graph_review_summary as module
    blobs = LocalBlobs(tmp_path)
    payload = legacy(blobs)
    row = row_for(payload)
    cache = GraphReviewCache()
    monkeypatch.setattr(module, "PAGE_SECONDS", 0.02)
    monkeypatch.setattr(blobs, "get_bounded_until", lambda *a: pytest.fail("No admission means no I/O"))
    assert cache._slots.acquire(blocking=False)
    assert cache._slots.acquire(blocking=False)
    try:
        cache.hydrate([row], [payload["active_graph"]], blobs)
        assert row["review_summary"] is None
        assert not cache._inflight
    finally:
        cache._slots.release()
        cache._slots.release()


def test_failed_singleflight_does_not_repeat_within_page(tmp_path, monkeypatch):
    blobs = LocalBlobs(tmp_path)
    payload = legacy(blobs)
    calls = []
    def unavailable(*args):
        calls.append(args)
        time.sleep(0.01)
        raise OSError("temporary storage failure")
    monkeypatch.setattr(blobs, "get_bounded_until", unavailable)
    rows = [row_for(payload) for _ in range(5)]
    cache = GraphReviewCache()
    cache.hydrate(rows, [payload["active_graph"]] * 5, blobs)
    assert len(calls) == 1 and all(row["review_summary"] is None for row in rows)
    cache.hydrate([row_for(payload)], [payload["active_graph"]], blobs)
    assert len(calls) == 2 and not cache._inflight


def test_live_state_pattern_has_three_review_and_twelve_missing(tmp_path):
    """Controlled state-only analogue; it contains no production field content."""
    source = specimen()
    fields = {key: FieldValue(state="not_present") for key in source.run.profile.mandatory_fields}
    for key in ["fmnh_ins_number", "country", "province_state", "city", "precise_location",
                "date_visited_from", "date_visited_to"]:
        fields[key] = FieldValue(state="supported", literal="fixture")
    fields["taxon"] = FieldValue(state="unresolved", literal="fixture")
    fields["identified_by_irn"] = FieldValue(state="unknown")
    fields["verbatim_dts"] = FieldValue(state="unknown")
    source.run.fields = fields
    source.run.reasons = ["mandatory_unresolved:taxon", "mandatory_unresolved:verbatim_dts"]
    blobs = LocalBlobs(tmp_path)
    payload = pack(source, blobs)
    assert row_for(payload)["review_summary"] == {"review": 3, "missing": 12}
    payload["active_graph"].pop("field_review")
    row = row_for(payload)
    GraphReviewCache().hydrate([row], [payload["active_graph"]], blobs)
    assert row["review_summary"] == {"review": 3, "missing": 12}


@pytest.mark.parametrize("packed", ["new", "legacy"])
def test_sqlite_projection_and_opt_in_do_not_fetch_snapshots(tmp_path, monkeypatch, packed):
    repo = SQLiteRepository(tmp_path / "graph.db")
    payload = pack(specimen(), repo.graph_blobs)
    if packed == "legacy": payload["active_graph"].pop("field_review")
    with repo.connect() as db:
        db.execute("INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            (SCOPE.organization_id, SCOPE.collection_id, payload["id"], payload["version"], json.dumps(payload), "2026-01-01", "finalized"))
    monkeypatch.setattr(repo, "get", lambda *a: pytest.fail("No per-row SQL/snapshot read"))
    calls = track(repo.graph_blobs, monkeypatch)
    filters = SearchFilters(specimen_id=payload["id"])
    row = repo.search(SCOPE, filters, "2026-01-02")[0]
    assert row["review_summary"] == (EXPECTED if packed == "new" else None)
    assert calls["calls"] == 0
    row = repo.search(SCOPE, filters, "2026-01-02", hydrate_review=True)[0]
    assert row["review_summary"] == EXPECTED
    assert calls["calls"] == (1 if packed == "legacy" else 0)
    assert set(row).isdisjoint({"active_graph", "field_review_states", "fields", "snapshot"})


@pytest.mark.parametrize("fault", [None, "deadline", "overflow", "status"])
def test_gcs_queue_read_uses_bounded_single_reads_and_closes_response(monkeypatch, fault):
    import hashlib
    from types import SimpleNamespace
    from specimen_digitization.application.production import GcsBlobs
    import specimen_digitization.application.production as production

    clock = [0.0]
    monkeypatch.setattr(production.time, "monotonic", lambda: clock[0])
    content = b"verified graph"
    checksum = hashlib.sha256(content).hexdigest()
    chunks = iter([content, b""])
    state = {"closed": False}

    class Response:
        status_code = 503 if fault == "status" else 200
        headers = {}
        def __init__(self): self.raw = self
        def __enter__(self): return self
        def __exit__(self, *args): state["closed"] = True
        def read(self, *args, **kwargs): pytest.fail("read may fill across an unbounded trickle")
        def read1(self, count, *, decode_content):
            assert decode_content is False and count <= 65536
            if fault == "deadline": clock[0] += 9
            return next(chunks)

    def get(url, **kwargs):
        assert kwargs["params"] == {"alt": "media", "generation": "123"}
        assert kwargs["timeout"] == (1.0, 1.0)
        assert kwargs["max_allowed_time"] == 8.0
        assert kwargs["allow_redirects"] is False
        return Response()

    blobs = object.__new__(GcsBlobs)
    blobs.bucket = SimpleNamespace(name="scoped-test-bucket", client=SimpleNamespace(_http=SimpleNamespace(get=get)))
    if fault is None:
        assert blobs.get_bounded_until(checksum + ":123", len(content), 8.0) == content
    else:
        with pytest.raises(Exception):
            blobs.get_bounded_until(checksum + ":123", 1 if fault == "overflow" else len(content), 8.0)
    assert state["closed"]


@pytest.mark.parametrize("metadata", [1, True, "null", "invalid", {"field_review": {"fields": 1}}, {"field_review": {"fields": True}}])
def test_sqlite_malformed_graph_json_matches_sql_any_unknown(tmp_path, metadata):
    repo = SQLiteRepository(tmp_path / "malformed-graph.db")
    source = specimen()
    payload = source.model_dump(mode="json")
    payload["active_graph"] = metadata
    with repo.connect() as db:
        db.execute("INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            (SCOPE.organization_id, SCOPE.collection_id, source.id, source.version, json.dumps(payload), "2026-01-01", "finalized"))
    row = repo.search(SCOPE, SearchFilters(), "2026-01-02", hydrate_review=True)[0]
    assert row["review_summary"] is None
    wire = {"id": source.id, "revision": source.version, "activeRunId": source.run.id,
            "reasonCodes": source.run.reasons, "activeGraph": metadata,
            "fieldReviewStates": {"city": {"state": "supported", "has_value": True}}}
    assert sql_item(wire, SCOPE)["review_summary"] is None


def test_wide_graph_omits_optional_projection_without_dropping_fields(tmp_path):
    from specimen_digitization.application.active_graph import encoded, FIELD_REVIEW_LIMIT, field_review_projection
    from specimen_digitization.application.storage import check_snapshot
    blobs = LocalBlobs(tmp_path)
    source = specimen()
    source.run.fields = {f"field_{i}": FieldValue(state="supported", literal="fixture") for i in range(6000)}
    source.run.reasons = []
    assert len(encoded(field_review_projection(source.run.model_dump(mode="json")))) > FIELD_REVIEW_LIMIT
    payload = pack(source, blobs)
    assert "field_review" not in payload["active_graph"]
    check_snapshot(encoded(payload).decode())
    assert read_graph(payload, blobs)[1]["fields"] == source.run.model_dump(mode="json")["fields"]
    row = row_for(payload)
    GraphReviewCache().hydrate([row], [payload["active_graph"]], blobs)
    assert row["review_summary"] == {"review": 0, "missing": 0}


def test_optional_projection_does_not_break_near_limit_snapshot(tmp_path):
    from specimen_digitization.application.active_graph import encoded
    from specimen_digitization.application.domain import AuditEvent
    from specimen_digitization.application.storage import check_snapshot
    blobs = LocalBlobs(tmp_path)
    source = specimen()
    source.audit = [AuditEvent(actor="reviewer", action="fixture", reason="")]
    baseline = pack(source, blobs)
    baseline["active_graph"].pop("field_review")
    source.audit[0].reason = "x" * (256 * 1024 - len(encoded(baseline)) - 100)
    payload = pack(source, blobs)
    assert "field_review" not in payload["active_graph"]
    assert len(encoded(payload)) == 256 * 1024 - 100
    check_snapshot(encoded(payload).decode())
    assert read_graph(payload, blobs)[1] == source.run.model_dump(mode="json")
