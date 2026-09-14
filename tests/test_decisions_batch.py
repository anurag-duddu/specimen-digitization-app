"""The bulk decisions endpoint: one call, one reason, one outcome per decision.

Closes the wire half of pass criteria 7.2 and 7.3 in
`apps/specimen_digitization/design/08-verification-report.md`. 7.2 asked for
five corrections on one record in one round trip; 7.3 asked for an action the
server accepts across more than one record. Both are the same endpoint here,
because a batch entry addresses its own record: five entries naming one record
are 7.2, and five entries naming five records are 7.3.

What these tests hold is the part a reviewer depends on: the count on the
confirmation is the count the server acts on, and a batch that goes wrong says
exactly which records changed and which did not.
"""

import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    local_app,
)

TOKEN = "test-only-local-token"
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
BATCH = PREFIX + "/decisions:batch"
HEADERS = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "batch-request"}
REASON = "Reviewed together at the copy stand"


def image_bytes(shade: int):
    """A distinct image per specimen: identical bytes deduplicate on checksum."""
    output = io.BytesIO()
    Image.new("RGB", (120, 80), (shade, shade, shade)).save(output, format="PNG")
    return output.getvalue()


def client(root):
    return TestClient(local_app(root, TOKEN), raise_server_exceptions=False)


def processed(c, ordinal: int) -> dict:
    """One uploaded, processed record, as the workspace describes it.

    Every intake call carries its own key: the server reconciles on the key and
    a second, different payload under one key is a conflict, not a second
    record.
    """

    def intake_headers(step: str) -> dict:
        return dict(HEADERS, **{"Idempotency-Key": f"intake-{ordinal}-{step}"})

    batch = c.post(
        PREFIX + "/batches",
        headers=intake_headers("batch"),
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Synthetic"},
    )
    assert batch.status_code == 200, batch.text
    data = image_bytes(ordinal * 10)
    item = c.post(
        PREFIX + f"/batches/{batch.json()['batch_id']}/items",
        headers=intake_headers("item"),
        json={
            "client_item_id": f"item-{ordinal}",
            "filename": f"synthetic-{ordinal}.png",
            "media_type": "image/png",
            "size_bytes": len(data),
            "width": 120,
            "height": 80,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert item.status_code == 200, item.text
    upload = item.json()["upload_id"]
    content = c.put(
        PREFIX + f"/uploads/{upload}/content",
        headers=intake_headers("content"),
        content=data,
    )
    assert content.status_code == 200, content.text
    done = c.post(
        PREFIX + f"/uploads/{upload}/complete",
        headers=intake_headers("complete"),
        json={"expected_revision": content.json()["revision"]},
    )
    assert done.status_code == 200, done.text
    ident = done.json()["specimen_id"]
    work = c.post(
        PREFIX + f"/specimens/{ident}/process", headers=intake_headers("process")
    )
    assert work.status_code == 200, work.text
    return work.json()


def approval(record: dict) -> dict:
    return {
        "specimen_id": record["specimen_id"],
        "expected_revision": record["revision"],
        "base_record_version_id": record["record_version_id"],
        "kind": "approve",
    }


@pytest.fixture
def three(tmp_path):
    c = client(tmp_path)
    records = [processed(c, ordinal) for ordinal in range(1, 4)]
    yield c, records
    c.close()


def test_one_call_decides_many_records_and_reports_each(three):
    c, records = three
    response = c.post(
        BATCH,
        headers=HEADERS,
        json={"reason": REASON, "decisions": [approval(r) for r in records]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["requested"], body["applied"], body["refused"], body["skipped"]) == (
        3,
        3,
        0,
        0,
    )
    assert [row["specimen_id"] for row in body["results"]] == [
        r["specimen_id"] for r in records
    ]
    assert {row["outcome"] for row in body["results"]} == {"applied"}
    # Every row names the version the decision produced, so the client replaces
    # what it holds rather than guessing.
    for row, record in zip(body["results"], records):
        assert row["revision"] > record["revision"]
        assert row["disposition"] == "cleared"
    # And the records really moved, read back independently of the answer.
    for record in records:
        saved = c.get(
            PREFIX + f"/specimens/{record['specimen_id']}/workspace", headers=HEADERS
        ).json()
        assert saved["disposition"] == "cleared"


def test_every_decision_carries_its_own_reconciling_key(three):
    c, records = three
    request = {"reason": REASON, "decisions": [approval(r) for r in records]}
    first = c.post(BATCH, headers=HEADERS, json=request).json()
    keys = [row["idempotency_key"] for row in first["results"]]
    assert keys == ["batch-request-0", "batch-request-1", "batch-request-2"]
    assert len(set(keys)) == 3, "two decisions sharing a key reconcile as one"
    # The identical batch replayed changes nothing and answers the same
    # versions, because each decision reconciles on its own key.
    replay = c.post(BATCH, headers=HEADERS, json=request).json()
    assert [row["revision"] for row in replay["results"]] == [
        row["revision"] for row in first["results"]
    ]


def test_two_decisions_may_not_share_one_key(three):
    c, records = three
    decisions = [approval(records[0]), approval(records[1])]
    for entry in decisions:
        entry["idempotency_key"] = "same-key"
    response = c.post(
        BATCH, headers=HEADERS, json={"reason": REASON, "decisions": decisions}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_input"


def test_a_refused_record_never_hides_the_ones_that_changed(three):
    c, records = three
    stale = approval(records[1])
    # A record another reviewer moved under this one: the version the batch
    # names is no longer the version the server holds.
    stale["expected_revision"] = stale["expected_revision"] + 5
    stale["base_record_version_id"] = (
        stale["base_record_version_id"].rsplit(":", 1)[0]
        + f":{stale['expected_revision']}"
    )
    response = c.post(
        BATCH,
        headers=HEADERS,
        json={
            "reason": REASON,
            "decisions": [approval(records[0]), stale, approval(records[2])],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["applied"], body["refused"], body["skipped"]) == (2, 1, 0)
    outcomes = {row["specimen_id"]: row for row in body["results"]}
    assert outcomes[records[0]["specimen_id"]]["outcome"] == "applied"
    assert outcomes[records[2]["specimen_id"]]["outcome"] == "applied"
    refused = outcomes[records[1]["specimen_id"]]
    assert refused["outcome"] == "refused"
    # The same code the same decision would have been given on its own
    # endpoint, not a batch-shaped substitute.
    assert refused["error"]["code"] == "revision_or_idempotency_conflict"
    assert refused["error"]["status"] == 409
    # The refused record is untouched, and the other two are not.
    untouched = c.get(
        PREFIX + f"/specimens/{records[1]['specimen_id']}/workspace", headers=HEADERS
    ).json()
    assert untouched["revision"] == records[1]["revision"]
    assert untouched["disposition"] == "needs_human_review"


def test_an_unknown_record_is_one_row_not_one_error(three):
    c, records = three
    missing = dict(approval(records[0]), specimen_id="00000000-0000-4000-8000-00000000dead")
    response = c.post(
        BATCH,
        headers=HEADERS,
        json={"reason": REASON, "decisions": [approval(records[0]), missing]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["applied"], body["refused"]) == (1, 1)
    assert body["results"][1]["error"]["code"] == "not_found"


def test_several_corrections_on_one_record_are_one_round_trip(three):
    c, records = three
    record = records[0]
    # Criterion 7.2: several decisions, one record, one reason, one call. The
    # client names the version it was looking at once; the server threads the
    # rest, so a later correction is applied against what the earlier one
    # produced rather than against a version the client guessed.
    corrections = [
        {
            "specimen_id": record["specimen_id"],
            "expected_revision": record["revision"],
            "base_record_version_id": record["record_version_id"],
            "kind": "coverage",
            "after": {"confirmed": True},
        },
        dict(approval(record)),
    ]
    response = c.post(
        BATCH, headers=HEADERS, json={"reason": REASON, "decisions": corrections}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["applied"], body["refused"], body["skipped"]) == (2, 0, 0)
    revisions = [row["revision"] for row in body["results"]]
    assert revisions[1] > revisions[0] > record["revision"]
    saved = c.get(
        PREFIX + f"/specimens/{record['specimen_id']}/workspace", headers=HEADERS
    ).json()
    assert saved["revision"] == revisions[1]
    assert saved["run"]["coverage_confirmed"] is True
    assert saved["run"]["human_approved"] is True


def test_decisions_on_one_record_must_name_one_base_version(three):
    c, records = three
    record = records[0]
    first = approval(record)
    second = dict(first, expected_revision=record["revision"] + 1)
    response = c.post(
        BATCH, headers=HEADERS, json={"reason": REASON, "decisions": [first, second]}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_input"


def test_a_refusal_skips_that_record_and_no_other(three):
    c, records = three
    first, second = records[0], records[1]
    response = c.post(
        BATCH,
        headers=HEADERS,
        json={
            "reason": REASON,
            "decisions": [
                # An unsupported decision refuses, so the approval listed after
                # it for the same record is never attempted.
                dict(approval(first), kind="not_a_decision"),
                approval(first),
                approval(second),
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["outcome"] for row in body["results"]] == [
        "refused",
        "skipped",
        "applied",
    ]
    assert (body["applied"], body["refused"], body["skipped"]) == (1, 1, 1)
    assert body["results"][0]["error"]["code"] == "invalid_input"
    # Skipped means never sent. The record is exactly where it was.
    untouched = c.get(
        PREFIX + f"/specimens/{first['specimen_id']}/workspace", headers=HEADERS
    ).json()
    assert untouched["revision"] == first["revision"]


def test_a_reason_and_a_key_are_required(three):
    c, records = three
    decisions = [approval(records[0])]
    assert (
        c.post(
            BATCH, headers=HEADERS, json={"reason": "  ", "decisions": decisions}
        ).status_code
        == 422
    )
    assert (
        c.post(
            BATCH,
            headers={"Authorization": "Bearer " + TOKEN},
            json={"reason": REASON, "decisions": decisions},
        ).status_code
        == 422
    )
    # The reason is the batch's, and it reaches every decision's audit trail.
    assert (
        c.post(
            BATCH, headers=HEADERS, json={"reason": REASON, "decisions": decisions}
        ).status_code
        == 200
    )
    history = c.get(
        PREFIX + f"/specimens/{records[0]['specimen_id']}/workspace", headers=HEADERS
    ).json()
    assert REASON in {event["reason"] for event in history["decisions"]}


def test_the_batch_is_bounded(three):
    c, records = three
    assert (
        c.post(BATCH, headers=HEADERS, json={"reason": REASON, "decisions": []}).status_code
        == 422
    )
    oversized = [
        dict(approval(records[0]), idempotency_key=f"key-{index}")
        for index in range(101)
    ]
    assert (
        c.post(
            BATCH, headers=HEADERS, json={"reason": REASON, "decisions": oversized}
        ).status_code
        == 422
    )


def test_a_viewer_is_refused_row_by_row(tmp_path):
    """Authorization is checked per record, with the reason in the row."""
    from specimen_digitization.application.api import create_app
    from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
    from specimen_digitization.application.workflow import SyntheticAdapters
    from specimen_digitization.application.api import SYNTHETIC_TEXT

    c = client(tmp_path)
    record = processed(c, 1)
    c.close()
    blobs = LocalBlobs(tmp_path / "blobs")
    viewer = TestClient(
        create_app(
            mode="emulator",
            repository=SQLiteRepository(tmp_path / "state.sqlite3"),
            blobs=blobs,
            adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
            identity_verifier=lambda token, check: "viewer",
            memberships=lambda user: [
                {
                    "organization_id": SYNTHETIC_ORG,
                    "collection_id": SYNTHETIC_COLLECTION,
                    "role": "viewer",
                    "can_view_sensitive": True,
                }
            ],
        ),
        raise_server_exceptions=False,
    )
    response = viewer.post(
        BATCH, headers=HEADERS, json={"reason": REASON, "decisions": [approval(record)]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["applied"], body["refused"]) == (0, 1)
    assert body["results"][0]["error"]["code"] == "access_denied"
    assert body["results"][0]["error"]["status"] == 403
    viewer.close()
