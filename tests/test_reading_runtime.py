"""Actual workspace/raw artifact behavior for multilingual and bounded comparisons."""

import pytest
from fastapi.testclient import TestClient
from test_application import intake, HEADERS, PREFIX, TOKEN
from specimen_digitization.application.api import create_app
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters


@pytest.mark.parametrize(
    "left,right,status",
    [
        ("😀a\r\nb", "😀a\r\nc", "disagreement"),
        ("a" * 9000, "b" * 9000, "policy_blocked"),
    ],
)
def test_reading_artifacts_preserve_utf16_and_long_uncertainty(
    tmp_path, left, right, status
):
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, left, right),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        alignment = http.get(
            path + "/disagreements/" + work["run"]["regions"][0]["id"], headers=HEADERS
        ).json()
        assert alignment["status"] == status, work["blocker"]
        assert work["observations"][0]["literal_text"] == left
        assert work["observations"][1]["literal_text"] == right
        assert set(work["run"]["review_risk"]["unmeasured"]) >= {"language", "script"}
        if status == "policy_blocked":
            assert "reading_disagreement" in work["run"]["review_risk"]["unmeasured"]
            assert (
                alignment["edit_distance"] is None and alignment["alternatives"] == []
            )
            assert work["run"]["disagreements"][0]["difference_count"] is None
        else:
            span = alignment["alternatives"][0]["left"]
            assert (
                span["start"]["utf16_codeunit"] == 5
                and span["end"]["utf16_codeunit"] == 6
            )
        metadata = http.get(
            path + "/observations/" + work["observations"][0]["id"] + "/metadata",
            headers=HEADERS,
        ).json()
        assert (
            metadata["reference"]["source_sha256"]
            == work["observations"][0]["raw_sha256"]
        )
        assert metadata["language_state"] == "unknown"


@pytest.mark.parametrize(
    "left,right", [("a" * 9000, "b" * 9000), ("same" * 26000, "same" * 26000)]
)
def test_legacy_adjudication_is_bounded_and_unknown_is_not_agreement(
    tmp_path, left, right
):
    import time

    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, left, right),
        token=TOKEN,
    )
    started = time.monotonic()
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace", headers=HEADERS
        ).json()
        transcript = work["run"]["transcripts"][0]
        assert transcript["disagreement_ratio"] is None
        assert transcript["alignment_status"] == "policy_blocked"
        assert transcript["alignment_reasons"] and not transcript["resolved"]
        assert transcript["text"] is None
        assert transcript["alternatives"] == list(dict.fromkeys([left, right]))
        assert work["disposition"] == "needs_human_review"
    assert time.monotonic() - started < 8
