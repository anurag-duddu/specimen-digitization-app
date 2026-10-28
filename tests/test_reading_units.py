"""Work package 1.1: the reading-unit record, stored with the run (docs/execution/units/PLAN.md).

FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 3 gives a unit's keys. Nothing makes units yet
(WP 1.2); these tests store and carry them through the repository (SQLite inline and through the
active graph, and SQL Connect's Struct transport), the workspace route and the normalized
projection, and show that a run without units keeps main's bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct
from pydantic import ValidationError

from specimen_digitization.application.active_graph import pack, run_summary
from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, create_app
from specimen_digitization.application.domain import (
    Asset,
    FieldValue,
    Observation,
    Principal,
    Region,
    Run,
    Scope,
    Specimen,
    ValueState,
)
from specimen_digitization.application.production import SqlConnectRepository
from specimen_digitization.application.projection import Blob, derived_id, writes
from specimen_digitization.application.reading_units import (
    ReadingUnit,
    ReadingUnits,
    UnitText,
)
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import SyntheticAdapters

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "tests/fixtures/general_api_contracts.json"
# The units of one label as the workspace route returns them; the app's reader test reads it.
WORKSPACE_FIXTURE = ROOT / "tests/fixtures/reading_units_workspace.json"
REGENERATE = "Regenerate tests/fixtures/reading_units_workspace.json from this test's workspace body"

# Pilot label e98a924c-L2's last lines as three readers wrote them (the design's section 3 example).
LABEL = "00000000-0000-4000-8000-0000000000e2"
READINGS = {
    "00000000-0000-4000-8000-00000000000a": "6-Sept-1946, Elev.6400\nSp.30 ♀",
    "00000000-0000-4000-8000-00000000000b": "6-Sept-1946, Elev.6400'\nSp.30 ♀",
    "00000000-0000-4000-8000-00000000000c": "6-Sept-1946, Elev.6400\nSp.30 ♂",
}
A, B, C = READINGS


def at(reading: str, piece: str) -> UnitText:
    """`piece` where it stands in `reading`, in Python string indices (code points)."""
    start = reading.index(piece)
    return UnitText(text=piece, start=start, end=start + len(piece))


def pilot_units(label: str = LABEL, readings: dict[str, str] = READINGS) -> ReadingUnits:
    a, b, c = readings
    return ReadingUnits(
        label=label,
        units=[
            ReadingUnit(
                id=f"{label}:1",
                label=label,
                lines=(1, 1),
                readers={key: at(text, "6-Sept-1946,") for key, text in readings.items()},
                image="6-Sept-1946,",
                means="1946-09-06",
                fields=["date_visited_from"],
            ),
            ReadingUnit(
                id=f"{label}:2",
                label=label,
                lines=(1, 1),
                readers={
                    a: at(readings[a], "Elev.6400"),
                    b: at(readings[b], "Elev.6400'"),
                    c: at(readings[c], "Elev.6400"),
                },
                image="uncertain",
                means="elevation 6400, unit not certain from the image",
                fields=["elevation_from_ft"],
                note="Only reader B saw a foot mark.",
            ),
            ReadingUnit(
                id=f"{label}:3",
                label=label,
                lines=(2, 2),
                readers={
                    a: at(readings[a], "Sp.30 ♀"),
                    b: at(readings[b], "Sp.30 ♀"),
                    c: at(readings[c], "Sp.30 ♂"),
                },
                image="Sp.30 ♀",
                means="species number 30, female",
            ),
        ],
    )


def unit(**changes) -> dict:
    """The first pilot unit as JSON, with `changes`."""
    return {**pilot_units().units[0].model_dump(mode="json"), **changes}


# ---------------------------------------------------------------------------- the record


def test_a_unit_holds_the_keys_of_the_design():
    stored = pilot_units().model_dump(mode="json")
    assert set(stored) == {"label", "units"}
    assert [set(u) for u in stored["units"]] == [
        {"id", "label", "lines", "readers", "image", "means", "role", "fields", "note"}
    ] * 3
    second = stored["units"][1]
    assert second["id"] == f"{LABEL}:2" and second["lines"] == [1, 1]
    assert second["readers"][B] == {"text": "Elev.6400'", "start": 13, "end": 23}
    assert second["readers"][A] == {"text": "Elev.6400", "start": 13, "end": 22}
    assert ReadingUnits.model_validate(stored) == pilot_units()


def test_offsets_are_code_points_into_the_readers_own_text():
    reading = "\U0001f98b Elev.6400"  # a butterfly: one code point, two UTF-16 code units
    span = at(reading, "Elev.6400")
    assert (span.start, span.end) == (2, 11)
    assert reading[span.start:span.end] == span.text
    assert len(reading.encode("utf-16-le")) // 2 == len(reading) + 1
    # A reader that wrote nothing here has an empty text at one point.
    assert UnitText(text="", start=7, end=7).text == ""


@pytest.mark.parametrize(
    "changes",
    [
        # The image names a text no reader wrote.
        {"image": "6 Sept 1946"},
        # The offsets do not span the text.
        {"readers": {A: {"text": "6-Sept-1946,", "start": 0, "end": 11}}},
        {"readers": {A: {"text": "", "start": 3, "end": 2}}},
        {"readers": {A: {"text": "x", "start": -1, "end": 0}}},
        {"readers": {}},
        {"readers": {"": {"text": "6-Sept-1946,", "start": 0, "end": 12}}},
        {"lines": [2, 1]},
        {"lines": [0, 1]},
        {"lines": [1]},
        {"role": "collector"},
        {"fields": ["country", "country"]},
        {"fields": [""]},
        {"label": ""},
        {"unknown": "key"},
    ],
)
def test_a_unit_refuses_what_the_design_rules_out(changes):
    with pytest.raises(ValidationError):
        ReadingUnit.model_validate(unit(**changes))


def test_the_image_may_name_any_readers_text_uncertain_or_not_visible():
    for image in ("Sp.30 ♀", "Sp.30 ♂", "uncertain", "not visible"):
        third = pilot_units().units[2].model_dump(mode="json")
        assert ReadingUnit.model_validate({**third, "image": image}).image == image


def test_a_labels_units_are_numbered_in_reading_order_and_name_the_same_readers():
    stored = pilot_units().model_dump(mode="json")
    first, second, third = stored["units"]
    for refused in (
        {**stored, "units": []},
        {**stored, "units": [second, first, third]},
        {**stored, "units": [first, {**second, "id": f"{LABEL}:3"}, third]},
        {**stored, "units": [first, {**second, "label": "another", "id": "another:2"}, third]},
        {**stored, "label": "another"},
        {**stored, "units": [first, {**second, "readers": {A: second["readers"][A]}}, third]},
    ):
        with pytest.raises(ValidationError):
            ReadingUnits.model_validate(refused)


def test_a_run_holds_one_entry_of_units_per_label():
    other = pilot_units("00000000-0000-4000-8000-0000000000e3")
    assert len(Run(reading_units=[pilot_units(), other]).reading_units) == 2
    with pytest.raises(ValidationError):
        Run(reading_units=[pilot_units(), pilot_units()])


# ---------------------------------------------------------------------------- old runs: main's bytes

# Pins computed on main e2faa1316 (before this change) from the stored run main's code wrote into
# general_api_contracts.json's workspace response, as the run of the specimen below. Each is
# written "sha256:<hex>", as tests/reference/units_program writes its digests.
MAIN_STORED_SHA256 = "sha256:4da6079f9b4a9a4d090e6c648f33e1bcfa53ef8a4c1180b331b33c110a733476"
MAIN_SNAPSHOT_DIGEST = "sha256:d9fa82359146af5cacaa126b90d2cfeb71883f7b64189ddc88a41dc57ab6a9c6"
MAIN_WRITES_DIGEST = "sha256:15d9f864a7fb5308f725de4ced70e730e16d0b7d5ed1e554792b0ec5a5ad87c3"


def hex_of(pin: str) -> str:
    """The hex digest of a "sha256:<hex>" pin."""
    algorithm, _, value = pin.partition(":")
    assert algorithm == "sha256" and len(value) == 64
    return value


def stored_from_main() -> tuple[dict, Specimen]:
    """A stored run main's code wrote (the contract corpus is unchanged by this change)."""
    corpus = json.loads(CONTRACTS.read_text())
    body = json.loads(corpus["responses"]["workspace"]["body_utf8"])
    specimen = Specimen(
        id=body["specimen_id"],
        scope=Scope(organization_id=body["organization_id"], collection_id=body["collection_id"]),
        asset=Asset.model_validate(body["asset"]),
        run=Run.model_validate(body["run"]),
        version=body["revision"],
        created_at=body["domain_created_at"],
    )
    return body["run"], specimen


def stored_bytes(specimen: Specimen) -> str:
    """The payload SQLiteRepository writes for `specimen` (storage.py, `_commit`)."""
    return json.dumps(pack(specimen.model_copy(deep=True), None), ensure_ascii=False, separators=(",", ":"))


def locate(ref: str) -> Blob:
    return Blob("bucket", "object/" + ref, "1")


def projected(specimen: Specimen) -> list:
    return [[w.operation, w.variables, w.key] for w in writes(specimen, locate, lambda ref: 1, "worker-uid")]


def test_a_run_without_units_stores_no_units_key():
    for run in (Run(), Run(reading_units=[])):
        stored = run.model_dump(mode="json")
        assert "reading_units" not in stored
        assert "reading_units" not in run_summary(stored)
        assert "reading_units" not in run.model_dump_json()


def test_a_stored_run_from_main_loads_unchanged_and_stores_main_bytes():
    raw, specimen = stored_from_main()
    assert "reading_units" not in raw and specimen.run.reading_units == []
    # The run re-dumps to main's exact JSON, key order included.
    assert json.dumps(specimen.run.model_dump(mode="json"), ensure_ascii=False) == json.dumps(
        raw, ensure_ascii=False
    )
    text = stored_bytes(specimen)
    assert hashlib.sha256(text.encode()).hexdigest() == hex_of(MAIN_STORED_SHA256)
    assert digest(json.loads(text)) == hex_of(MAIN_SNAPSHOT_DIGEST)
    # SQL Connect's snapshot: the Struct round trip reads back the same record and digest.
    payload = json.loads(text)
    transported = json_format.MessageToDict(json_format.ParseDict(payload, Struct()))
    sql = SqlConnectRepository.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    restored = sql._snapshot({"snapshot": transported, "sha256": hex_of(MAIN_SNAPSHOT_DIGEST)})
    assert restored == specimen
    # Struct leaves untyped maps' numbers as doubles; the snapshot digest reads them as SQL does.
    assert digest(json.loads(stored_bytes(restored))) == hex_of(MAIN_SNAPSHOT_DIGEST)


def test_a_stored_run_from_main_projects_as_main_did_without_units():
    _, specimen = stored_from_main()
    rows = projected(specimen)
    assert digest(rows) == hex_of(MAIN_WRITES_DIGEST)
    assert "AppendTranscriptionVersionV2" in {row[0] for row in rows}
    assert "AppendTranscriptionVersionV3" not in {row[0] for row in rows}
    assert not any("readingUnits" in row[1] for row in rows)


# ---------------------------------------------------------------------------- a run with units


def scope() -> Scope:
    return Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)


def with_units(units: list[ReadingUnits] | None = None) -> Specimen:
    region = Region(id=LABEL, asset_id="00000000-0000-4000-8000-0000000000f1", x=1, y=1,
                    width=10, height=10, order=0, method="fixture", version="fixture-v1")
    readings = [
        Observation(id=key, region_id=LABEL, route_id=f"reader-{key[-1]}", model_id="fixture",
                    provider="fixture", prompt_version="p" * 64, input_sha256="b" * 64,
                    literal_text=text, raw_ref="r" * 64, raw_sha256="r" * 64,
                    created_at="2026-10-27T00:00:00+00:00")
        for key, text in READINGS.items()
    ]
    return Specimen(
        id="00000000-0000-4000-8000-0000000000d1",
        scope=scope(),
        asset=Asset(id="00000000-0000-4000-8000-0000000000f1", sha256="a" * 64,
                    blob_ref="immutable-fixture", filename="fixture.png", media_type="image/png",
                    size_bytes=1, width=1, height=1, uploader="A",
                    created_at="2026-10-27T00:00:00+00:00"),
        run=Run(id="00000000-0000-4000-8000-0000000000c1", stage="finalized",
                created_at="2026-10-27T00:00:00+00:00", regions=[region], observations=readings,
                reading_units=[pilot_units()] if units is None else units),
        created_at="2026-10-27T00:00:00+00:00",
    )


def principal() -> Principal:
    return Principal(user_id="A", scope=scope(), role="reviewer")


def long_label(count: int) -> tuple[dict[str, str], ReadingUnits]:
    """A label of `count` words, one unit per word: a run past the active graph's threshold."""
    words = [f"w{n}" for n in range(count)]
    readings = {A: " ".join(words), B: " ".join(words)}
    units, start = [], 0
    for number, word in enumerate(words, 1):
        span = UnitText(text=word, start=start, end=start + len(word))
        units.append(ReadingUnit(id=f"{LABEL}:{number}", label=LABEL, lines=(1, 1),
                                 readers={A: span, B: span}, image=word, fields=["habitat"]))
        start += len(word) + 1
    return readings, ReadingUnits(label=LABEL, units=units)


def test_a_run_with_units_round_trips_through_the_repository(tmp_path):
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    # Stored inline.
    small = repository.create(principal(), with_units(), "create-small", digest({"small": 1}))
    assert small.active_graph is None
    assert repository.get(scope(), small.id) == small
    assert small.run.reading_units == [pilot_units()]
    with repository.connect() as db:
        (row,) = db.execute("SELECT payload FROM records WHERE id=?", (small.id,)).fetchone()
    assert row == stored_bytes(small)
    payload = json.loads(row)
    assert payload["run"]["reading_units"] == [pilot_units().model_dump(mode="json")]
    # Stored through the active graph: the compact row omits the units, the graph keeps them.
    _, units = long_label(1200)
    large = with_units([units])
    large.id = "00000000-0000-4000-8000-0000000000d2"
    large.asset.sha256 = "c" * 64
    large = repository.create(principal(), large, "create-large", digest({"large": 1}))
    assert large.active_graph is not None
    with repository.connect() as db:
        (row,) = db.execute("SELECT payload FROM records WHERE id=?", (large.id,)).fetchone()
    assert json.loads(row)["run"]["reading_units"] == []
    assert repository.get(scope(), large.id) == large
    assert large.run.reading_units == [units]
    # SQL Connect's snapshot: protobuf Struct carries every number as a double.
    transported = json_format.MessageToDict(json_format.ParseDict(payload, Struct()))
    first = transported["run"]["reading_units"][0]["units"][1]
    assert type(first["readers"][B]["end"]) is float and type(first["lines"][0]) is float
    sql = SqlConnectRepository.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    restored = sql._snapshot({"snapshot": transported, "sha256": digest(payload)})
    assert restored == small
    assert type(restored.run.reading_units[0].units[1].readers[B].end) is int
    assert restored.run.model_dump(mode="json")["reading_units"] == payload["run"]["reading_units"]
    assert digest(json.loads(stored_bytes(restored))) == digest(payload)


def app(repository) -> TestClient:
    blobs = LocalBlobs(Path(repository.path).parent / "blobs")
    return TestClient(
        create_app(
            mode="emulator", repository=repository, blobs=blobs, adapters=SyntheticAdapters(blobs, ""),
            identity_verifier=lambda bearer, appcheck: bearer,
            memberships=lambda user: [{"organization_id": SYNTHETIC_ORG, "collection_id": SYNTHETIC_COLLECTION,
                                       "role": "reviewer", "can_view_sensitive": True}],
        ),
        raise_server_exceptions=False,
    )


def workspace(http, specimen_id):
    response = http.get(f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{specimen_id}/workspace",
                        headers={"Authorization": "Bearer A"})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_workspace_route_returns_a_runs_units_and_omits_them_for_a_run_without(tmp_path):
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    specimen = repository.create(principal(), with_units(), "create", digest({"create": 1}))
    plain = with_units([])
    plain.id = "00000000-0000-4000-8000-0000000000d3"
    plain.asset.sha256 = "d" * 64
    repository.create(principal(), plain, "create-plain", digest({"plain": 1}))
    http = app(repository)
    body = workspace(http, specimen.id)
    assert body["run"]["reading_units"] == [pilot_units().model_dump(mode="json")]
    assert [ReadingUnits.model_validate(entry) for entry in body["run"]["reading_units"]] == [pilot_units()]
    shared = {
        "observations": [{"observation_id": o["observation_id"], "verbatim_text": o["verbatim_text"]}
                         for o in body["observations"]],
        "run": {"reading_units": body["run"]["reading_units"]},
    }
    assert json.loads(WORKSPACE_FIXTURE.read_text()) == shared, REGENERATE
    assert "reading_units" not in workspace(http, plain.id)["run"]


# ---------------------------------------------------------------------------- the normalized projection


def chicago_units(s: Specimen) -> ReadingUnits:
    """Units of the first-pass label of test_projection_decisions: "Chicago, Ill." against "Chicago, Il1."."""
    right, left = s.run.observations
    region = s.run.regions[0]
    readings = {left.id: left.literal_text, right.id: right.literal_text}
    return ReadingUnits(label=region.id, units=[
        ReadingUnit(id=f"{region.id}:1", label=region.id, lines=(1, 1), image="Chicago,",
                    readers={key: at(text, "Chicago,") for key, text in readings.items()},
                    means="Chicago", fields=["city"]),
        ReadingUnit(id=f"{region.id}:2", label=region.id, lines=(1, 1), image="Ill.",
                    readers={left.id: at(left.literal_text, "Ill."), right.id: at(right.literal_text, "Il1.")},
                    means="Illinois", fields=["province_state"]),
    ])


def test_a_labels_units_are_written_with_its_transcription_version():
    from test_projection_decisions import base, first_pass, rows

    s = first_pass(base())
    before = writes(s, locate, lambda ref: 1, "worker-uid")
    units = chicago_units(s)
    s.run.reading_units = [units]
    after = writes(s, locate, lambda ref: 1, "worker-uid")
    assert [w.operation for w in after] == [
        "AppendTranscriptionVersionV3" if w.operation == "AppendTranscriptionVersionV2" else w.operation
        for w in before
    ]
    (old,) = rows(before, "AppendTranscriptionVersionV2")
    (new,) = rows(after, "AppendTranscriptionVersionV3")
    assert ReadingUnits.model_validate(new["readingUnits"]) == units
    assert new["readingUnits"] == units.model_dump(mode="json")
    # The same decision with its units: a new version, every other value as V2 wrote it.
    assert new["id"] != old["id"]
    assert {k: v for k, v in new.items() if k not in ("id", "readingUnits")} == {
        k: v for k, v in old.items() if k != "id"
    }
    assert {h["transcriptionVersionId"] for h in rows(after, "AppendHarnessInputV1")} == {new["id"]}
    # Changed units are another version; the same units are the same one.
    assert rows(writes(s, locate, lambda ref: 1, "worker-uid"), "AppendTranscriptionVersionV3")[0]["id"] == new["id"]
    s.run.reading_units = [units.model_copy(update={"units": [units.units[0].model_copy(update={"means": "Chicago, Illinois"}), units.units[1]]})]
    assert rows(writes(s, locate, lambda ref: 1, "worker-uid"), "AppendTranscriptionVersionV3")[0]["id"] != new["id"]


def test_a_label_without_units_keeps_v2_beside_a_label_with_them():
    from test_projection_decisions import base, first_pass, rows

    s = first_pass(base())
    before = rows(writes(s, locate, lambda ref: 1, "worker-uid"), "AppendTranscriptionVersionV2")
    s.run.reading_units = [pilot_units("another-label")]
    after = writes(s, locate, lambda ref: 1, "worker-uid")
    assert rows(after, "AppendTranscriptionVersionV2") == before
    assert rows(after, "AppendTranscriptionVersionV3") == []


def test_a_candidate_from_a_label_with_units_changes_its_id_with_its_transcription():
    """Changed units are a new transcription version; a candidate settled on it is a new row too,
    so SQL never keeps candidate C pointing at the old version while the projector names the new one."""
    from test_projection_decisions import base, first_pass, rows

    s = first_pass(base())
    region = s.run.regions[0]
    s.run.fields = {"city": FieldValue(state=ValueState.SUPPORTED, literal="Chicago",
                                       input_source="decided_transcript", source_region_id=region.id)}
    s.run.reading_units = [chicago_units(s)]

    def saved() -> tuple[str, str]:
        result = writes(s, locate, lambda ref: 1, "worker-uid")
        (version,) = rows(result, "AppendTranscriptionVersionV3")
        (candidate,) = rows(result, "AppendFieldCandidateV2")
        assert candidate["sourceTranscriptionId"] == version["id"]
        return version["id"], candidate["id"]

    first = saved()
    # The same units again: both ids stay.
    assert saved() == first
    # Only one unit's meaning changes: a new version, and the candidate follows it.
    units = s.run.reading_units[0]
    s.run.reading_units = [units.model_copy(update={"units": [
        units.units[0].model_copy(update={"means": "Chicago, Illinois"}), units.units[1]]})]
    second = saved()
    assert second[0] != first[0]
    assert second[1] != first[1]
    # A label without units keeps main's candidate id: no transcription id in it.
    s.run.reading_units = []
    (candidate,) = rows(writes(s, locate, lambda ref: 1, "worker-uid"), "AppendFieldCandidateV2")
    assert candidate["id"] == derived_id(
        "candidate", s.run.id, "city", "-", digest(s.run.fields["city"].model_dump(mode="json"))
    )
