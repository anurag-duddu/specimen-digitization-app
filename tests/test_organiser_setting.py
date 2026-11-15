"""Work package 2.5 of docs/execution/units/PLAN.md: the organiser setting.

`harness.organiser_setting` reads SPECIMEN_UNITS_ORGANISER, `harness.organiser_pin` records it in
a units-path run's pinned dependencies, `harness.calls_organiser` gates parse's organiser call on
that record, and `harness.apply_units` writes the proposal from the run's reading units when the
call is left out."""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from specimen_digitization.application.domain import (
    Evidence,
    FieldValue,
    Observation,
    Profile,
    Region,
    Run,
    Transcript,
    ValueState,
)
from specimen_digitization.application.harness import (
    COMPETING,
    OFF,
    ON,
    ORGANISER,
    ORGANISER_SETTING,
    ExtractionCandidate,
    ExtractionOutput,
    apply_candidates,
    apply_units,
    calls_organiser,
    organiser_pin,
    organiser_setting,
)
from specimen_digitization.application.organiser import (
    SOURCE,
    reading_texts_of,
    stored_candidates,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.reading_units import (
    PERSON,
    ReadingUnit,
    ReadingUnits,
    UnitText,
    problems,
)
from specimen_digitization.application.storage import LocalBlobs

# Pilot slide 105526321 as the units-wp22-20261114 pair run read it: its barcode label, read the
# same by both readers, and the first lines of its locality label, read by handwriting-qwen (A)
# and handwriting-muse (B).
BARCODE = "FMNHINS\n4486784"
QWEN = "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner"
MUSE = "10-6-78-1a\nE.slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Wermer"
# The units the first pass cut there (units-wp22-20261114, results/r1/pair.jsonl), each reader's
# text and the unit's fields advice.
CUT = [
    ({"A": "10-6-78-la", "B": "10-6-78-1a"}, []),
    ({"A": "E. slope", "B": "E.slope"}, ["precise_location"]),
    ({"A": "Mt. McKinley", "B": "Mt. McKinley"}, ["precise_location"]),
    ({"A": "Davao Prov.", "B": "Davao Prov."}, ["province_state", "precise_location"]),
    ({"A": "Mindanao, P.I.", "B": "Mindanao, P.I."}, ["country", "province_state", "precise_location"]),
    ({"A": "F.G. Werner", "B": "F.G. Wermer"}, ["collectors"]),
]
FIELDS = ("fmnh_ins_number", "country", "province_state", "precise_location", "collectors",
    "elevation_from_ft", "elevation_from_m")


def region(order: int) -> Region:
    return Region(asset_id="asset-1", x=0, y=0, width=9, height=9, order=order, method="m", version="1")


def observation(label: Region, route: str, text: str) -> Observation:
    return Observation(region_id=label.id, route_id=route, model_id="model-" + route,
        provider="provider-" + route, prompt_version="p", input_sha256="0" * 64, literal_text=text,
        raw_ref="raw-" + route, raw_sha256="1" * 64)


def units(label: str, texts: dict[str, str], cut, keys: dict[str, str]) -> ReadingUnits:
    """`cut`'s units over `texts` (reader key -> its whole text); `keys` maps the cut's reader
    letters to the reader keys. Each unit's image is its first reader's text."""
    cursors = dict.fromkeys(texts, 0)
    built = []
    for number, (pieces, fields) in enumerate(cut, 1):
        spans = {}
        for letter, key in keys.items():
            piece = pieces.get(letter, "")
            start = texts[key].index(piece, cursors[key]) if piece else cursors[key]
            spans[key] = UnitText(text=piece, start=start, end=start + len(piece))
            cursors[key] = start + len(piece)
        image = next(piece for piece in pieces.values() if piece)
        built.append(ReadingUnit(id=f"{label}:{number}", label=label, lines=(1, 1), readers=spans,
            image=image, fields=fields))
    entry = ReadingUnits(label=label, units=built)
    assert problems(entry, texts) == []
    return entry


def pilot_run(*, person: str | None = None, person_units: bool = True, cut=CUT) -> Run:
    """A units-path run of the two labels: the barcode's readings identical (decided, as the
    workflow's identical_readings rule decides it), the locality label's differing. With
    `person`, a person decided the locality label's text: its units are cut over the person's
    text (keyed PERSON) when `person_units`, else over the two readings."""
    one, two = region(0), region(1)
    a1, b1 = observation(one, "handwriting-qwen", BARCODE), observation(one, "handwriting-muse", BARCODE)
    a2, b2 = observation(two, "handwriting-qwen", QWEN), observation(two, "handwriting-muse", MUSE)
    transcripts = [
        Transcript(region_id=one.id, text=BARCODE, observation_ids=[a1.id, b1.id], alternatives=[BARCODE],
            resolved=True, decision_kind="identical_readings", selected_observation_id=a1.id),
        Transcript(region_id=two.id, text=person, observation_ids=[a2.id, b2.id], alternatives=[QWEN, MUSE],
            resolved=person is not None, actor="synthetic-reviewer" if person else None,
            decision_kind="human" if person else "first_pass",
            selected_observation_id=a2.id if person else None),
    ]
    entries = [units(one.id, {a1.id: BARCODE, b1.id: BARCODE}, [({"A": BARCODE, "B": BARCODE},
        ["fmnh_ins_number"])], {"A": a1.id, "B": b1.id})]
    if person is not None and person_units:
        entries.append(units(two.id, {PERSON: person}, [(dict(pieces, B=pieces["A"]), fields)
            for pieces, fields in cut], {"A": PERSON}))
    else:
        entries.append(units(two.id, {a2.id: QWEN, b2.id: MUSE}, cut, {"A": a2.id, "B": b2.id}))
    return Run(profile=Profile(), first_pass_path="units", regions=[one, two], observations=[a1, b1, a2, b2],
        transcripts=transcripts, reading_units=entries, fields={key: FieldValue() for key in FIELDS})


def rows(run: Run, field: str) -> list[Evidence]:
    """The field's cited rows of the organiser's source, in the field's order."""
    by_id = {e.id: e for e in run.evidence}
    return [by_id[i] for i in run.fields[field].evidence_ids if i in by_id and by_id[i].source == SOURCE]


class _Blobs:
    """A blob store that keeps what it is given."""

    def __init__(self):
        self.stored: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        ref = hashlib.sha256(data).hexdigest()
        self.stored[ref] = data
        return ref

    def get(self, ref: str) -> bytes:
        return self.stored[ref]


def shape(row: Evidence) -> tuple:
    return (row.kind, row.asset_id, row.region_id, tuple(row.observation_ids), row.source, row.locator,
        row.excerpt, row.raw_ref, row.digest)


# ------------------------------------------------------------------------------ the setting


@pytest.mark.parametrize("environ,value", [({}, ON), ({ORGANISER_SETTING: ""}, ON),
    ({ORGANISER_SETTING: "on"}, ON), ({ORGANISER_SETTING: "off"}, OFF)])
def test_the_setting_calls_the_organiser_unless_it_says_off(environ, value):
    assert organiser_setting(environ) == value


@pytest.mark.parametrize("value", ["OFF", "false", "no", "secret-value"])
def test_a_mistyped_setting_raises_naming_the_setting_never_its_value(value):
    with pytest.raises(ValueError) as error:
        organiser_setting({ORGANISER_SETTING: value})
    assert ORGANISER_SETTING in str(error.value) and value not in str(error.value)


@pytest.mark.parametrize("path,setting,pinned", [
    ("old", None, {}), ("old", "on", {}), ("old", "off", {}), ("old", "secret-value", {}),
    ("units", None, {}), ("units", "on", {}), ("units", "off", {ORGANISER: OFF}),
])
def test_only_a_units_path_run_with_the_setting_off_pins_the_organiser_off(path, setting, pinned):
    run = Run(first_pass_path=path)
    environ = {} if setting is None else {ORGANISER_SETTING: setting}
    assert organiser_pin(run, environ) == pinned


def test_a_units_path_run_with_a_mistyped_setting_is_not_pinned():
    with pytest.raises(ValueError):
        organiser_pin(Run(first_pass_path="units"), {ORGANISER_SETTING: "secret-value"})


def test_production_pins_what_main_pins_unless_a_units_path_run_has_the_setting_off(tmp_path, monkeypatch):
    adapters = ProductionAdapters(LocalBlobs(tmp_path))

    def pins(path: str, setting: str | None) -> dict:
        if setting is None:
            monkeypatch.delenv(ORGANISER_SETTING, raising=False)
        else:
            monkeypatch.setenv(ORGANISER_SETTING, setting)
        return adapters.pin_dependencies(Run(profile=Profile(first_pass_route="first-pass-glm"),
            first_pass_path=path))

    for path in ("old", "units"):
        unset = pins(path, None)
        assert ORGANISER not in unset and pins(path, "on") == unset
    assert pins("old", "off") == pins("old", None)
    assert pins("units", "off") == {**pins("units", None), ORGANISER: OFF}


@pytest.mark.parametrize("path,dependencies,calls", [
    ("old", {}, True), ("old", {ORGANISER: OFF}, True), ("units", {}, True),
    ("units", {ORGANISER: OFF}, False), ("units", {ORGANISER: ON}, True), ("units", {ORGANISER: "Off"}, True),
])
def test_parse_calls_the_organiser_unless_a_units_path_run_is_pinned_off(path, dependencies, calls):
    assert calls_organiser(Run(first_pass_path=path, dependencies=dependencies)) is calls


# ------------------------------------------------------------------- the rows from the units


def test_each_unit_s_advised_fields_get_one_row_per_reading_at_the_unit_s_offsets(tmp_path):
    run = pilot_run()
    blobs = LocalBlobs(tmp_path)
    apply_units(run, "asset-1", blobs)
    a1, b1, a2, b2 = (o.id for o in run.observations)
    one, two = (r.id for r in run.regions)
    raw = json.dumps([e.model_dump(mode="json") for e in run.reading_units], ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()
    ref, sha = rows(run, "country")[0].raw_ref, hashlib.sha256(raw).hexdigest()
    assert blobs.get(ref) == raw

    def row(label, region_id, observation_id, start, end, text):
        return ("literal", "asset-1", region_id, (observation_id,), SOURCE,
            f"reading:{label}:{observation_id}#quote={start}-{end};literal={start}-{end}", text, ref, sha)

    assert [shape(r) for r in rows(run, "country")] == [
        row("2A", two, a2, 45, 59, "Mindanao, P.I."), row("2B", two, b2, 44, 58, "Mindanao, P.I.")]
    assert [shape(r) for r in rows(run, "collectors")] == [
        row("2A", two, a2, 60, 71, "F.G. Werner"), row("2B", two, b2, 59, 70, "F.G. Wermer")]
    # A decided label: its decided reading (1A) first, the other reader's reading (1B) beside it.
    assert [shape(r) for r in rows(run, "fmnh_ins_number")] == [
        row("1A", one, a1, 0, 15, BARCODE), row("1B", one, b1, 0, 15, BARCODE)]
    assert [shape(r) for r in rows(run, "precise_location")] == [
        row("2A", two, a2, 11, 19, "E. slope"), row("2A", two, a2, 20, 32, "Mt. McKinley"),
        row("2A", two, a2, 33, 44, "Davao Prov."), row("2A", two, a2, 45, 59, "Mindanao, P.I."),
        row("2B", two, b2, 11, 18, "E.slope"), row("2B", two, b2, 19, 31, "Mt. McKinley"),
        row("2B", two, b2, 32, 43, "Davao Prov."), row("2B", two, b2, 44, 58, "Mindanao, P.I.")]
    # No row for a unit the advice gives no field, and none for a field the advice never names.
    assert len(run.evidence) == 2 + 2 + 2 + 8 + 4
    assert rows(run, "elevation_from_ft") == []


def test_the_field_values_follow_apply_candidates_rule():
    run = pilot_run()
    apply_units(run, "asset-1", _Blobs())
    fields = run.fields
    # Both readers state one literal: supported with it.
    assert (fields["country"].state, fields["country"].literal, fields["country"].parsed) == (
        ValueState.SUPPORTED, "Mindanao, P.I.", "Mindanao, P.I.")
    assert fields["country"].reason == "Exact source-supported typed extraction"
    assert fields["fmnh_ins_number"].literal == BARCODE
    # Readers that differ, or two literals in one reading: ambiguous, none chosen.
    for key in ("collectors", "province_state", "precise_location"):
        assert (fields[key].state, fields[key].literal, fields[key].reason) == (
            ValueState.AMBIGUOUS, None, COMPETING)
    assert fields["elevation_from_ft"] == FieldValue()


def test_the_rows_and_values_are_those_apply_candidates_writes_for_the_same_candidates():
    """The organiser's candidate for each row, quoting the unit's text, through apply_candidates:
    the same rows (bar their ids and times) and the same values. The texts here occur once in
    their readings, so apply_candidates' first occurrence is the unit's own offsets."""
    run, twin = pilot_run(), pilot_run()
    twin.regions, twin.observations, twin.transcripts = run.regions, run.observations, run.transcripts
    blobs = _Blobs()
    apply_units(run, "asset-1", blobs)
    from specimen_digitization.application.organiser import parse_locator

    output = ExtractionOutput(candidates=[
        ExtractionCandidate(field_key=key, reading=parse_locator(r.locator).label, literal=r.excerpt,
            source_excerpt=r.excerpt)
        for key, value in run.fields.items() for r in rows(run, key)])
    ref = run.evidence[0].raw_ref
    apply_candidates(twin, "asset-1", output, ref, run.evidence[0].digest)

    assert sorted(shape(r) for r in twin.evidence) == sorted(shape(r) for r in run.evidence)
    for key in FIELDS:
        mine, theirs = run.fields[key], twin.fields[key]
        assert [shape(r) for r in rows(run, key)] == [shape(r) for r in rows(twin, key)]
        assert mine.model_dump(exclude={"evidence_ids"}) == theirs.model_dump(exclude={"evidence_ids"})


def test_stored_candidates_and_field_research_read_the_rows_as_the_organiser_s(tmp_path):
    from specimen_digitization.field_research.step import _candidates, run_readings

    run = pilot_run()
    apply_units(run, "asset-1", LocalBlobs(tmp_path))
    stored = [c for c in stored_candidates(run.fields, run.evidence, reading_texts_of(run))
        if c.field_key == "country"]
    a2, b2 = run.observations[2].id, run.observations[3].id
    assert [(c.label, c.observation_ids, c.quote_span, c.literal_span, c.literal, c.primary) for c in stored] == [
        ("2A", (a2,), (45, 59), (45, 59), "Mindanao, P.I.", True),
        ("2B", (b2,), (44, 58), (44, 58), "Mindanao, P.I.", False)]
    candidates = _candidates(run, run_readings(run))
    assert [(c.reading, c.quote, c.literal, c.evidence_id) for c in candidates["country"]] == [
        ("2A", "Mindanao, P.I.", "Mindanao, P.I.", rows(run, "country")[0].id),
        ("2B", "Mindanao, P.I.", "Mindanao, P.I.", rows(run, "country")[1].id)]


PERSON_TEXT = "E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner"
PERSON_CUT = [cut for cut in CUT if cut[0]["A"] != "10-6-78-la"]


def test_a_person_s_units_cite_the_label_s_decided_reading():
    run = pilot_run(person=PERSON_TEXT, cut=PERSON_CUT)
    apply_units(run, "asset-1", _Blobs())
    a2 = run.observations[2].id
    # The person's text is reading 2A (decided, cited to the reading it was anchored to); the
    # two machine readings, 2B and 2C, carry no units.
    assert [(r.locator, r.excerpt) for r in rows(run, "country")] == [
        (f"reading:2A:{a2}#quote=34-48;literal=34-48", "Mindanao, P.I.")]
    assert rows(run, "collectors")[0].locator == f"reading:2A:{a2}#quote=49-60;literal=49-60"
    assert run.fields["collectors"].literal == "F.G. Werner"


def test_a_reading_s_units_never_cite_a_decided_reading_with_another_text():
    """A decided reading anchored to an observation whose text it does not hold (a person's
    edit) is not that observation's reading: the units cut over the observation's text cite its
    raw reading only, even where the person's text holds the same characters there."""
    edited = QWEN.replace("Werner", "Wernor")
    run = pilot_run(person=edited, person_units=False)
    apply_units(run, "asset-1", _Blobs())
    a2, b2 = run.observations[2].id, run.observations[3].id
    assert edited[45:59] == "Mindanao, P.I."
    assert [r.locator for r in rows(run, "country")] == [
        f"reading:2B:{a2}#quote=45-59;literal=45-59", f"reading:2C:{b2}#quote=44-58;literal=44-58"]


def test_a_literal_the_written_rule_guard_refuses_gets_no_row():
    one = region(0)
    a, b = (observation(one, route, "Elev. 6400 m") for route in ("handwriting-qwen", "handwriting-muse"))
    entry = units(one.id, {a.id: a.literal_text, b.id: b.literal_text}, [
        ({"A": "Elev.", "B": "Elev."}, []),
        ({"A": "6400", "B": "6400"}, ["elevation_from_ft", "elevation_from_m"]),
        ({"A": "m", "B": "m"}, [])], {"A": a.id, "B": b.id})
    run = Run(profile=Profile(), first_pass_path="units", regions=[one], observations=[a, b], transcripts=[
        Transcript(region_id=one.id, observation_ids=[a.id, b.id], alternatives=[a.literal_text],
            resolved=False, decision_kind="first_pass")], reading_units=[entry],
        fields={key: FieldValue() for key in FIELDS})
    apply_units(run, "asset-1", _Blobs())
    # "6400" marked "m" is no Elevation From (ft) (extraction_guard, G41).
    assert rows(run, "elevation_from_ft") == [] and run.fields["elevation_from_ft"] == FieldValue()
    assert [r.excerpt for r in rows(run, "elevation_from_m")] == ["6400", "6400"]
    assert run.fields["elevation_from_m"].literal == "6400"


def test_a_blank_reader_a_field_the_run_lacks_and_a_span_off_its_reading_get_no_row():
    run = pilot_run()
    entry = run.reading_units[1]
    first, *rest = entry.units
    collectors = rest[-1]
    # Reader B wrote nothing at the collectors' unit; the advice names a field the run lacks; and
    # the first unit's span in reader A is moved off its text (no stored record holds this).
    b = next(key for key in collectors.readers if collectors.readers[key].text == "F.G. Wermer")
    blank = UnitText(text="", start=collectors.readers[b].start, end=collectors.readers[b].start)
    a = next(key for key in first.readers if key != b)
    moved = UnitText(text="Mindanao", start=0, end=8)
    run.reading_units[1] = ReadingUnits.model_construct(label=entry.label, units=[
        first.model_copy(update={"readers": {**first.readers, a: moved}, "fields": ["country"]}),
        *rest[:-1],
        collectors.model_copy(update={"readers": {**collectors.readers, b: blank},
            "fields": ["no_such_field", "collectors"]})])
    apply_units(run, "asset-1", _Blobs())
    assert "no_such_field" not in run.fields
    # Reader B states no collector, so the label has no single literal.
    assert [r.excerpt for r in rows(run, "collectors")] == ["F.G. Werner"]
    assert run.fields["collectors"].state == ValueState.AMBIGUOUS
    # Reader A's moved span gets no row; reader B's text at that unit does.
    assert [r.excerpt for r in rows(run, "country")] == ["Mindanao, P.I.", "10-6-78-1a", "Mindanao, P.I."]


def test_a_run_without_advised_units_stores_nothing():
    run = pilot_run(cut=[(pieces, []) for pieces, _ in CUT])
    run.reading_units = run.reading_units[1:]
    blobs = _Blobs()
    apply_units(run, "asset-1", blobs)
    assert run.evidence == [] and blobs.stored == {}
    assert all(value == FieldValue() for value in run.fields.values())


# ---------------------------------------------------------------------------- the workflow


def test_the_old_path_with_the_setting_off_stores_main_s_bytes(tmp_path, monkeypatch):
    from test_first_pass_units import MAIN_OLD_PATH_STORED, MAIN_OLD_PATH_WRITES, frozen_old_path_run, old_path_pins

    monkeypatch.setenv(ORGANISER_SETTING, "off")
    specimen = frozen_old_path_run(tmp_path, monkeypatch, switch=None)
    assert old_path_pins(specimen) == (MAIN_OLD_PATH_STORED, MAIN_OLD_PATH_WRITES)


# A units-path synthetic run frozen as test_first_pass_units.frozen_old_path_run freezes the old
# path's, with the organiser called: its stored record and projection writes on main 44aeb6863.
MAIN_UNITS_PATH_STORED = "sha256:de673a5acf4c1c2d9c315a83e9a67be176f9c379d7253eda180a2ce877ebc42f"
MAIN_UNITS_PATH_WRITES = "sha256:c85b4a2becf202f7e789e6233ab92f0b104a084b7d94e487693e01630eae350c"


def frozen_units_run(tmp_path, monkeypatch):
    """test_first_pass_units.frozen_old_path_run with the units switch on, the run created by
    test_first_pass_units.start_run, which keeps the intake run's path."""
    import test_first_pass_units as units_tests
    import test_first_pass_workflow

    monkeypatch.setattr(test_first_pass_workflow, "start", units_tests.start_run)
    return units_tests.frozen_old_path_run(tmp_path, monkeypatch, switch="on")


@pytest.mark.parametrize("setting", [None, "on"], ids=["unset", "on"])
def test_a_units_path_run_that_calls_the_organiser_stores_main_s_bytes(tmp_path, monkeypatch, setting):
    from test_first_pass_units import old_path_pins

    if setting is None:
        monkeypatch.delenv(ORGANISER_SETTING, raising=False)
    else:
        monkeypatch.setenv(ORGANISER_SETTING, setting)
    specimen = frozen_units_run(tmp_path, monkeypatch)
    assert specimen.run.first_pass_path == "units" and specimen.run.reading_units
    assert ORGANISER not in specimen.run.dependencies
    assert old_path_pins(specimen) == (MAIN_UNITS_PATH_STORED, MAIN_UNITS_PATH_WRITES)


def advised(run: Run) -> list[ReadingUnits]:
    """The run's units cut again at each line's first ": " (a keyed synthetic line), the value's
    unit advised for the line's key: the synthetic first pass gives no fields advice."""
    found = []
    for entry in run.reading_units:
        texts = {key: span.text for key, span in _whole(run, entry).items()}
        first = next(iter(texts))
        cut = []
        for line in texts[first].split("\n"):
            key, _, value = line.partition(": ")
            cut += [({"A": key + ":"}, []), ({"A": value}, [key] if key in run.fields else [])]
        letters = {chr(ord("A") + i): key for i, key in enumerate(texts)}
        cut = [({letter: pieces["A"] for letter in letters}, fields) for pieces, fields in cut]
        found.append(units(entry.label, texts, cut, letters))
    return found


def _whole(run: Run, entry: ReadingUnits) -> dict[str, UnitText]:
    texts = {o.id: o.literal_text for o in run.observations}
    return {key: UnitText(text=texts[key], start=0, end=len(texts[key])) for key in entry.units[0].readers}


class Extracting:
    """Synthetic adapters whose organiser call is recorded, and whose pins are the synthetic
    default with what organiser_pin adds."""

    def __init__(self, tmp_path):
        from specimen_digitization.application.api import SYNTHETIC_TEXT
        from specimen_digitization.application.workflow import SyntheticAdapters

        class Adapters(SyntheticAdapters):
            extractions: list[str] = []

            def extract(self, specimen):
                self.extractions.append(specimen.run.id)

            def pin_dependencies(self, run):
                return {"adapter": "SyntheticAdapters", "synthetic": run.profile.synthetic,
                    **organiser_pin(run, os.environ)}

        self.adapters = Adapters(LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT, SYNTHETIC_TEXT)
        self.adapters.extractions = []


def to_parse(tmp_path, monkeypatch, setting):
    from test_first_pass_units import start_run

    from specimen_digitization.application.reading_units import SETTING
    from specimen_digitization.application.storage import digest

    monkeypatch.setenv(SETTING, "on")
    if setting is None:
        monkeypatch.delenv(ORGANISER_SETTING, raising=False)
    else:
        monkeypatch.setenv(ORGANISER_SETTING, setting)
    adapters = Extracting(tmp_path).adapters
    workflow, principal, ident = start_run(tmp_path, adapters)
    for _ in range(40):
        specimen = workflow.repository.get(principal.scope, ident)
        if workflow.next_step(specimen.run) == "parse":
            break
        workflow.step(principal, ident)
    specimen.run.reading_units = advised(specimen.run)
    specimen = workflow.repository.save(principal, specimen, specimen.version, "advised", digest({"advised": 1}))
    return workflow, principal, specimen, adapters


def test_a_units_path_run_pinned_off_makes_no_organiser_call_and_writes_the_units_rows(tmp_path, monkeypatch):
    from specimen_digitization.application.integrity import verify_evidence

    workflow, principal, before, adapters = to_parse(tmp_path, monkeypatch, "off")
    assert before.run.dependencies[ORGANISER] == OFF
    after = workflow.step(principal, before.id)
    run = after.run

    assert "parse" in run.completed_steps and adapters.extractions == []
    # parse was no external step: no external call counted, no provider circuit admitted.
    assert run.usage.external_calls == before.run.usage.external_calls
    assert run.circuit == before.run.circuit
    country = rows(run, "country")
    assert [r.excerpt for r in country] == ["United States", "United States"]
    assert all(r.source == SOURCE and r.raw_ref and r.digest for r in country)
    assert run.fields["country"].literal == "United States"
    verify_evidence(after, workflow.blobs)
    drained = workflow.drain(principal, after.id)
    verify_evidence(drained, workflow.blobs)
    assert adapters.extractions == []


@pytest.mark.parametrize("setting", [None, "on"], ids=["unset", "on"])
def test_a_units_path_run_with_the_organiser_on_calls_it_and_writes_no_units_rows(tmp_path, monkeypatch, setting):
    workflow, principal, before, adapters = to_parse(tmp_path, monkeypatch, setting)
    assert ORGANISER not in before.run.dependencies
    after = workflow.step(principal, before.id)
    run = after.run

    assert "parse" in run.completed_steps and adapters.extractions == [run.id]
    assert run.usage.external_calls > before.run.usage.external_calls
    assert not [r for r in run.evidence if r.source == SOURCE]
