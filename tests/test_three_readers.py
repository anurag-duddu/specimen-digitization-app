"""Three readers of each label (the NVIDIA option's reader C, Nemotron).

The reading pipeline works for two to eight readers (a profile names at most
eight, the label risk budget): every pair of a label's readings is compared, a label resolves only when every reading agrees, and
readings that differ go to the first pass, which sees every reading
(docs/product-requirements/NVIDIA_NEMOTRON_OPTION.md sections 1 and 2).
"""

import json

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import SYNTHETIC_TEXT, create_app
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.reliability import ReadingStopped
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from test_application import HEADERS, PREFIX, TOKEN, intake

THREE = ("handwriting-qwen", "handwriting-muse", "handwriting-nemotron")
DIFFERENT = SYNTHETIC_TEXT + "\ntaxon: different"


def three_reader_registry():
    registry = application_registry(True)
    return registry.model_copy(
        update={
            "profiles": tuple(
                profile.model_copy(update={"model_routes": THREE})
                for profile in registry.profiles
            )
        }
    )


class Readers(SyntheticAdapters):
    """Synthetic readers; a route in `stopped` gives up (ReadingStopped), so its
    label is left one reading short."""

    def __init__(self, blobs, alternates=None, stopped=()):
        super().__init__(blobs, SYNTHETIC_TEXT, alternates)
        self.stopped, self.first_passes = set(stopped), []

    def transcribe(self, specimen, region, route):
        if route in self.stopped:
            raise ReadingStopped("synthetic_reader_stopped")
        return super().transcribe(specimen, region, route)

    def first_pass(self, specimen, region, readings):
        self.first_passes.append([r.route_id for r in readings])
        return super().first_pass(specimen, region, readings)


def processed(tmp_path, adapters):
    """Intake through the synthetic API under the three-reader profile; the
    workspace and the label's comparison artifact."""
    blobs = adapters.blobs
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs,
        adapters=adapters,
        token=TOKEN,
        profile_registry=three_reader_registry(),
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        region = work["run"]["regions"][0]["id"]
        response = http.get(path + "/disagreements/" + region, headers=HEADERS)
        assert response.status_code == 200, response.text
        return work, response.json()


def by_route(work):
    return {o["route_id"]: o["id"] for o in work["observations"]}


def test_three_readers_that_agree_resolve_the_label_with_no_first_pass(tmp_path):
    adapters = Readers(LocalBlobs(tmp_path / "blobs"))

    work, artifact = processed(tmp_path, adapters)

    run = work["run"]
    # The whole synthetic pipeline runs, its evidence checks included.
    assert (run["stage"], run["blocker"]) == ("finalized", None)
    assert run["profile"]["routes"] == list(THREE)
    assert [o["route_id"] for o in work["observations"]] == list(THREE)
    assert adapters.first_passes == []
    (transcript,) = run["transcripts"]
    assert transcript["resolved"] and transcript["decision_kind"] == "identical_readings"
    assert transcript["text"] == SYNTHETIC_TEXT
    assert (transcript["alignment_status"], transcript["disagreement_ratio"]) == ("agreement", 0)
    ids = by_route(work)
    a, b, c = (ids[route] for route in THREE)
    # Every pair, in route order.
    assert [
        (p["left_observation_id"], p["right_observation_id"], p["status"])
        for p in transcript["comparisons"]
    ] == [(a, b, "agreement"), (a, c, "agreement"), (b, c, "agreement")]
    # The label's comparison artifact: the reported pair's fields, every pair beside.
    assert artifact["status"] == "agreement"
    assert [
        (p["left"]["observation_id"], p["right"]["observation_id"])
        for p in artifact["comparisons"]
    ] == [(a, b), (a, c), (b, c)]
    (summary,) = run["disagreements"]
    assert (summary["status"], summary["difference_count"]) == ("agreement", 0)
    assert set(run["reading_metadata"]) == {a, b, c}
    # The label's review risk compared all three pairs (review_risk.label_review_risk
    # marks reading_comparisons unmeasured when a pair is missing).
    (label,) = run["review_risk"]["labels"]
    assert "reading_comparisons" not in label["unmeasured"]


def test_one_reader_that_differs_sends_the_label_to_the_first_pass_with_every_reading(
    tmp_path,
):
    # Readers A and B agree; reader C reads the taxon line differently.
    adapters = Readers(LocalBlobs(tmp_path / "blobs"), (SYNTHETIC_TEXT, DIFFERENT))

    work, artifact = processed(tmp_path, adapters)

    run = work["run"]
    assert (run["stage"], run["blocker"]) == ("finalized", None)
    assert adapters.first_passes == [list(THREE)]
    (transcript,) = run["transcripts"]
    ids = by_route(work)
    a, b, c = (ids[route] for route in THREE)
    # The synthetic first pass picks no reading: no text, every reading handed on raw.
    assert transcript["decision_kind"] == "first_pass" and not transcript["resolved"]
    assert transcript["selected_observation_id"] is None
    assert [h["role"] for h in transcript["handoffs"]] == ["raw_reading"] * 3
    (difference,) = transcript["differences"]
    assert set(difference["spans"]) == {a, b, c}
    assert difference["spans"][a]["text"] == difference["spans"][b]["text"] == ""
    assert difference["spans"][c]["text"] == "taxon: different"
    # The least-agreeing pair speaks for the label: A with C, the first of the two
    # pairs that disagree as much.
    assert transcript["alignment_status"] == "disagreement"
    pairs = {
        (p["left_observation_id"], p["right_observation_id"]): p
        for p in transcript["comparisons"]
    }
    assert [p["status"] for p in pairs.values()] == ["agreement", "disagreement", "disagreement"]
    assert transcript["disagreement_ratio"] == pairs[(a, c)]["disagreement_ratio"] > 0
    assert (artifact["left"]["observation_id"], artifact["right"]["observation_id"]) == (a, c)
    assert artifact["status"] == "disagreement" and len(artifact["comparisons"]) == 3
    (summary,) = run["disagreements"]
    assert summary["status"] == "disagreement"
    assert summary["difference_count"] == len(artifact["alternatives"])


def test_a_label_left_with_two_of_three_readings_is_measured_on_that_pair(tmp_path):
    adapters = Readers(LocalBlobs(tmp_path / "blobs"), stopped={"handwriting-nemotron"})

    work, artifact = processed(tmp_path, adapters)

    run = work["run"]
    assert (run["stage"], run["blocker"]) == ("finalized", None)
    assert [o["route_id"] for o in work["observations"]] == list(THREE[:2])
    (transcript,) = run["transcripts"]
    # Two distinct readers still agree: the label resolves, as two readers' would.
    assert transcript["resolved"] and transcript["decision_kind"] == "identical_readings"
    assert transcript["alignment_status"] == "agreement"
    assert "comparisons" not in transcript
    assert "comparisons" not in artifact and artifact["status"] == "agreement"
    assert adapters.first_passes == []
    # Readings from two distinct routes and models: the label is still
    # independently read (policy.py, field_research/step.py).
    assert not [r for r in run["reasons"] if r.startswith("independent_observations_missing")]


def test_a_label_left_with_one_reading_is_unmeasured(tmp_path):
    adapters = Readers(
        LocalBlobs(tmp_path / "blobs"), stopped={"handwriting-muse", "handwriting-nemotron"}
    )
    blobs = adapters.blobs
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs,
        adapters=adapters,
        token=TOKEN,
        profile_registry=three_reader_registry(),
    )
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace", headers=HEADERS
        ).json()

    (transcript,) = work["run"]["transcripts"]
    assert not transcript["resolved"]
    assert (transcript["alignment_status"], transcript["alignment_reasons"]) == (
        "policy_blocked",
        ["independent_pair_incomplete"],
    )
    assert any(r.startswith("independent_observations_missing") for r in work["run"]["reasons"])


@pytest.mark.parametrize("alternate", [None, "taxon: different"], ids=["agree", "differ"])
def test_two_readers_keep_one_comparison_and_no_pair_list(tmp_path, alternate):
    # The published two-reader profile: the transcript and the artifact keep
    # their two-reader shape (no `comparisons`).
    blobs = LocalBlobs(tmp_path / "blobs")
    text = None if alternate is None else SYNTHETIC_TEXT + "\n" + alternate
    app = create_app(
        mode="synthetic",
        repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT, text),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        region = work["run"]["regions"][0]["id"]
        artifact = http.get(path + "/disagreements/" + region, headers=HEADERS).json()

    (transcript,) = work["run"]["transcripts"]
    assert len(transcript["observation_ids"]) == 2
    assert "comparisons" not in transcript and "comparisons" not in artifact
    first, second = (o["id"] for o in work["observations"])
    assert (artifact["left"]["observation_id"], artifact["right"]["observation_id"]) == (
        first,
        second,
    )
    assert json.dumps(artifact)  # The artifact is plain JSON.
