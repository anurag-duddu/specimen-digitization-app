"""The organiser: the first agent reads every reading of every label and returns
candidates, several per field, each quoted from one named reading.

Owner, 2026-10-03: "maybe the LLM that looks at the raw transcript can organize
the data into field value pairs and share it with the harness along with the
transcript ... taxa can be on multiple else ... evidence is always necessary."

The labels below are abstract and synthetic, shaped like the ten recorded pilot
snapshots (a slide-code label, a locality label with a collector and a date, a
barcode label, and a label whose two readings the first pass could not decide).
No label text from a real specimen is kept here. Nothing here calls a model.
"""

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from specimen_digitization import prompts
from specimen_digitization.application import harness
from specimen_digitization.application.domain import (
    MANDATORY,
    Evidence,
    FieldValue,
    Transcript,
    ValueState,
)
from specimen_digitization.application.field_harness import labelled
from specimen_digitization.application.field_resolution import DECIDED, RAW, Reading
from specimen_digitization.application.harness import (
    ExtractionCandidate,
    ExtractionOutput,
    apply_candidates,
)
from specimen_digitization.application.organiser import (
    SOURCE,
    CandidateLocation,
    extraction_readings,
    format_locator,
    parse_locator,
    request_text,
    stored_candidates,
)

SLIDE = "AB-12-34-1\nsp 22\nlegs"
LOCALITY_A = "Mount Foo,\nNorthvale Prov.\nLandia\nJ. Q. Collector\nXI .46"
LOCALITY_B = "Mount Foo,\nNorthvalle Prov.\nLandia\nJ. Q. Collecter\nXI .46"
BARCODE = "FMNHINS\n1234567"
BACK_A = "Genus beta\nAB-12-34-2"
BACK_B = "Genus betta\nAB-12-34-2"
TAXON_TWO = "Genus alpha\nsp 22"


def region_readings(region, *readings):
    return [
        Reading(region, f"o-{region}-{i}", role, text)
        for i, (role, text) in enumerate(readings)
    ]


def make_run(*regions):
    """What `apply_candidates` reads: the fields, the evidence and the readings.
    Each argument is (region, [(role, text), ...])."""
    return SimpleNamespace(
        evidence=[],
        fields={key: FieldValue() for key in MANDATORY},
        readings=[r for region, rows in regions for r in region_readings(region, *rows)],
    )


def specimen_run():
    """Three labels as the pilot slides have them: two readers each, the first
    reading decided; the fourth label is undecided (two raw readings)."""
    return make_run(
        ("slide", [(DECIDED, SLIDE), (RAW, SLIDE)]),
        ("locality", [(DECIDED, LOCALITY_A), (RAW, LOCALITY_B)]),
        ("barcode", [(DECIDED, BARCODE), (RAW, BARCODE)]),
        ("back", [(RAW, BACK_A), (RAW, BACK_B)]),
    )


def candidate(field, reading, literal, quote=None):
    return ExtractionCandidate(
        field_key=field, reading=reading, literal=literal, source_excerpt=quote or literal
    )


def apply(run, *candidates, raw="raw"):
    apply_candidates(run, "asset", ExtractionOutput(candidates=list(candidates)), raw, "d")


def rows(run):
    return {e.id: e for e in run.evidence}


def texts(run):
    return {r.observation_id: r.text for r in run.readings}


def test_the_labels_are_named_as_the_stage_7_harness_names_them():
    names = labelled(specimen_run().readings)
    assert list(names) == ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"]
    assert names["4B"].text == BACK_B and names["2B"].role == RAW


# --- Several candidates per field, each quoting one reading -------------------


def test_a_taxon_on_two_labels_is_two_evidence_rows_and_one_value():
    run = specimen_run()
    run.readings = make_run(
        ("slide", [(DECIDED, SLIDE), (RAW, SLIDE)]),
        ("back", [(DECIDED, TAXON_TWO), (RAW, TAXON_TWO)]),
    ).readings
    apply(
        run,
        candidate("taxon", "1A", "sp 22", "sp 22"),
        candidate("taxon", "2A", "sp 22", "Genus alpha\nsp 22"),
    )
    field = run.fields["taxon"]
    assert field.state == ValueState.SUPPORTED and field.literal == "sp 22"
    assert len(run.evidence) == len(field.evidence_ids) == 2
    first, second = (rows(run)[i] for i in field.evidence_ids)
    assert (first.region_id, second.region_id) == ("slide", "back")
    assert parse_locator(first.locator).label == "1A"
    assert parse_locator(second.locator).label == "2A"
    # The narrow quote is the evidence, not the whole label.
    assert second.excerpt == "Genus alpha\nsp 22" and first.excerpt == "sp 22"


def test_a_taxon_that_differs_between_two_labels_stays_ambiguous_with_both_rows():
    run = make_run(
        ("slide", [(DECIDED, "Genus alpha"), (RAW, "Genus alpha")]),
        ("back", [(DECIDED, "Genus beta"), (RAW, "Genus beta")]),
    )
    apply(
        run,
        candidate("taxon", "1A", "Genus alpha"),
        candidate("taxon", "2A", "Genus beta"),
    )
    field = run.fields["taxon"]
    # G32: two labels that differ do not clear; the first literal stays the value.
    assert field.state == ValueState.AMBIGUOUS and field.literal == "Genus alpha"
    assert len(field.evidence_ids) == 2
    found = stored_candidates(run.fields, run.evidence, texts(run))
    assert [(c.label, c.literal, c.primary) for c in found] == [
        ("1A", "Genus alpha", True),
        ("2A", "Genus beta", False),
    ]


def test_two_readers_that_disagree_give_one_candidate_each_and_the_decided_is_the_value():
    run = specimen_run()
    # The model lists the other reader's variant first. The decided transcript is
    # still the label's verbatim (G19, G27): the first pass already judged this
    # difference, so the variant is evidence beside the value, not a rival to it.
    apply(
        run,
        candidate("collectors", "2B", "J. Q. Collecter", "J. Q. Collecter"),
        candidate("collectors", "2A", "J. Q. Collector", "J. Q. Collector"),
    )
    field = run.fields["collectors"]
    assert field.literal == "J. Q. Collector" and field.state == ValueState.SUPPORTED
    found = stored_candidates(run.fields, run.evidence, texts(run))
    assert [(c.label, c.literal, c.primary) for c in found] == [
        ("2A", "J. Q. Collector", True),
        ("2B", "J. Q. Collecter", False),
    ]
    assert {c.observation_id for c in found} == {"o-locality-0", "o-locality-1"}


def test_the_other_readers_candidate_alone_is_a_lead_not_a_value():
    # The decided reading has no value for the field (the reader dropped the line);
    # the other reader's reading does. A decided transcript is the verbatim, so the
    # field stays unknown, as it does today, but the lead is kept and cited.
    run = make_run(("one", [(DECIDED, "Mount Foo"), (RAW, "Mount Foo\nJ. Q. Collector")]))
    apply(run, candidate("collectors", "1B", "J. Q. Collector"))
    field = run.fields["collectors"]
    assert field.state == ValueState.UNKNOWN and field.literal is None
    assert field.reason == harness.LEAD and len(field.evidence_ids) == 1
    (lead,) = stored_candidates(run.fields, run.evidence, texts(run))
    assert (lead.label, lead.literal, lead.primary) == ("1B", "J. Q. Collector", False)


def test_a_decided_label_and_an_undecided_one_that_differ_are_ambiguous_decided_first():
    run = specimen_run()
    apply(
        run,
        candidate("taxon", "4A", "Genus beta"),  # the undecided label, listed first
        candidate("taxon", "1A", "sp 22"),
    )
    field = run.fields["taxon"]
    assert field.state == ValueState.AMBIGUOUS and field.literal == "sp 22"
    assert [parse_locator(rows(run)[i].locator).label for i in field.evidence_ids] == ["1A", "4A"]


def test_two_readers_that_agree_leave_the_field_supported_with_a_row_each():
    run = specimen_run()
    apply(
        run,
        candidate("fmnh_ins_number", "3A", "1234567", "FMNHINS\n1234567"),
        candidate("fmnh_ins_number", "3B", "1234567", "1234567"),
    )
    field = run.fields["fmnh_ins_number"]
    assert field.state == ValueState.SUPPORTED and field.literal == "1234567"
    assert len(field.evidence_ids) == 2
    assert [rows(run)[i].observation_ids for i in field.evidence_ids] == [
        ["o-barcode-0"],
        ["o-barcode-1"],
    ]


def test_a_label_with_no_decided_transcript_still_gives_candidates():
    run = specimen_run()
    apply(run, candidate("taxon", "4B", "Genus betta"))
    field = run.fields["taxon"]
    assert field.state == ValueState.SUPPORTED and field.literal == "Genus betta"
    (row,) = (rows(run)[i] for i in field.evidence_ids)
    assert row.region_id == "back" and row.observation_ids == ["o-back-1"]
    assert parse_locator(row.locator).label == "4B"


def test_the_two_readers_of_an_undecided_label_that_differ_stay_ambiguous():
    run = specimen_run()
    apply(
        run,
        candidate("taxon", "4A", "Genus beta"),
        candidate("taxon", "4B", "Genus betta"),
    )
    assert run.fields["taxon"].state == ValueState.AMBIGUOUS
    assert run.fields["taxon"].literal == "Genus beta"


def test_the_primary_is_the_first_decided_candidate_whatever_the_models_order():
    run = specimen_run()
    apply(
        run,
        candidate("collectors", "2B", "J. Q. Collecter"),
        candidate("collectors", "2A", "J. Q. Collector"),
        candidate("taxon", "4A", "Genus beta"),
    )
    assert run.fields["collectors"].literal == "J. Q. Collector"
    assert run.fields["collectors"].state == ValueState.SUPPORTED
    # With no decided candidate, the first candidate of an undecided label is the value.
    assert run.fields["taxon"].literal == "Genus beta"


@pytest.mark.parametrize("name", ["2a", " 2A ", "Reading 2A", "reading 2a"])
def test_a_reading_named_in_another_case_or_with_its_word_is_the_same_reading(name):
    run = specimen_run()
    apply(run, candidate("collectors", name, "J. Q. Collector"))
    assert run.fields["collectors"].literal == "J. Q. Collector"
    assert parse_locator(run.evidence[0].locator).label == "2A"


@pytest.mark.parametrize("name", ["2", "A", "2C", "label 2", "Reading", ""])
def test_a_name_that_is_no_reading_is_refused(name):
    run = specimen_run()
    apply(run, candidate("collectors", name or " ", "J. Q. Collector"))
    assert run.evidence == []


def test_a_repeat_of_the_same_span_is_one_row():
    run = specimen_run()
    apply(
        run,
        candidate("fmnh_ins_number", "3A", "1234567", "1234567"),
        candidate("fmnh_ins_number", "3A", "1234567", "FMNHINS\n1234567"),
    )
    assert len(run.evidence) == 1
    assert len(run.fields["fmnh_ins_number"].evidence_ids) == 1


# --- Evidence is always necessary: what trusted code refuses ------------------


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(("collectors", "2A", "J. Q. Collector", "J.Q. Collector"), id="altered quote"),
        pytest.param(("collectors", "2A", "J. Q. Collecter", "J. Q. Collecter"), id="the other reader's text, cited as this reading"),
        pytest.param(("collectors", "9A", "J. Q. Collector", "J. Q. Collector"), id="a reading nobody was given"),
        pytest.param(("collectors", "1A", "J. Q. Collector", "J. Q. Collector"), id="another label's reading"),
        pytest.param(("nonsense", "2A", "J. Q. Collector", "J. Q. Collector"), id="a field that is not the run's"),
        pytest.param(("date_visited_from", "2A", "1946-11", "XI .46"), id="normalised literal, not in its quote"),
        pytest.param(("country", "2A", "landia", "Landia"), id="literal changed in case"),
        pytest.param(("collectors", "2A", " ", "J. Q. Collector\n"), id="blank literal"),
        pytest.param(("collectors", "2A", "J. Q. Collector", " \n"), id="blank quote"),
    ],
)
def test_an_invented_or_altered_candidate_is_refused(bad):
    run = specimen_run()
    field, reading, literal, quote = bad
    apply(run, candidate(field, reading, literal, quote))
    assert run.evidence == []
    assert all(v == FieldValue() for v in run.fields.values())


def test_an_invented_candidate_does_not_disturb_the_valid_ones():
    run = specimen_run()
    apply(
        run,
        candidate("collectors", "2A", "J. Q. Collector"),
        candidate("collectors", "2A", "A. N. Other"),
        candidate("country", "2A", "Elsewhere", "Landia"),
    )
    assert run.fields["collectors"].state == ValueState.SUPPORTED
    assert run.fields["collectors"].literal == "J. Q. Collector"
    assert len(run.evidence) == 1
    assert run.fields["country"] == FieldValue()


def test_the_model_cannot_claim_an_offset_or_a_span():
    with pytest.raises(ValidationError):
        ExtractionCandidate(
            field_key="collectors",
            reading="2A",
            literal="J. Q. Collector",
            source_excerpt="J. Q. Collector",
            start=24,
            end=39,
        )
    with pytest.raises(ValidationError):  # nor the old region claim
        ExtractionCandidate(
            field_key="collectors",
            region_id="locality",
            reading="2A",
            literal="x",
            source_excerpt="x",
        )


def test_offsets_are_computed_from_the_verified_strings():
    run = specimen_run()
    quote = "Landia\nJ. Q. Collector"
    apply(run, candidate("collectors", "2A", "J. Q. Collector", quote))
    (row,) = run.evidence
    where = parse_locator(row.locator)
    text = LOCALITY_A
    assert (where.quote_start, where.quote_end) == (text.index(quote), text.index(quote) + len(quote))
    assert text[where.quote_start : where.quote_end] == row.excerpt == quote
    assert text[where.literal_start : where.literal_end] == "J. Q. Collector"
    assert where.quote_start <= where.literal_start < where.literal_end <= where.quote_end
    assert (where.label, where.observation_id) == ("2A", "o-locality-0")


def test_a_repeated_quote_or_literal_means_its_first_occurrence():
    run = make_run(("one", [(DECIDED, "4800 ft.\n4800 ft.\nx 4800"), (RAW, "y")]))
    apply(run, candidate("elevation_from_ft", "1A", "4800", "4800 ft."))
    (row,) = run.evidence
    where = parse_locator(row.locator)
    assert (where.quote_start, where.literal_start, where.literal_end) == (0, 0, 4)


def test_a_whole_reading_quote_is_kept_when_it_is_verbatim():
    # The old behaviour quoted whole transcripts. A verbatim whole-reading quote
    # is still evidence; only the prompt asks for narrow ones.
    run = specimen_run()
    apply(run, candidate("country", "2A", "Landia", LOCALITY_A))
    (row,) = run.evidence
    assert row.excerpt == LOCALITY_A
    where = parse_locator(row.locator)
    assert (where.quote_start, where.quote_end) == (0, len(LOCALITY_A))
    assert LOCALITY_A[where.literal_start : where.literal_end] == "Landia"


# --- The guard reads the cited reading ----------------------------------------


def test_the_guard_runs_on_the_text_of_the_cited_reading():
    # The decided reading writes metres, the raw reading a foot mark. The same
    # literal is a value of the metres field from the first and not from the second.
    run = make_run(("label", [(DECIDED, "Elev. 3300 m"), (RAW, "Elev. 3300'")]))
    apply(run, candidate("elevation_from_m", "1B", "3300", "Elev. 3300'"))
    assert run.evidence == [] and run.fields["elevation_from_m"] == FieldValue()
    apply(run, candidate("elevation_from_m", "1A", "3300", "Elev. 3300 m"))
    assert run.fields["elevation_from_m"].literal == "3300"
    assert len(run.evidence) == 1


def test_the_guard_does_not_read_a_reading_that_was_not_cited():
    # A foot mark in another reading of the label does not refuse a metres value the
    # cited reading writes in metres (a label with no decided transcript: both count).
    run = make_run(("label", [(RAW, "3300'"), (RAW, "3300 m")]))
    apply(run, candidate("elevation_from_m", "1B", "3300", "3300 m"))
    assert run.fields["elevation_from_m"].literal == "3300"


def test_a_refused_candidate_leaves_no_row_but_a_kept_one_survives_beside_it():
    run = make_run(("label", [(DECIDED, "AB-12-34-1\nSmith"), (RAW, "AB-12-34-1\nSmith")]))
    apply(
        run,
        candidate("collection_code", "1A", "AB-12-34-1", "AB-12-34-1"),  # G45
        candidate("collectors", "1A", "Smith"),
    )
    assert run.fields["collection_code"] == FieldValue()
    assert run.fields["collectors"].literal == "Smith"
    assert len(run.evidence) == 1


# --- A value already on the field from a keyed label line ---------------------


def keyed_run(value):
    run = make_run(("label", [(DECIDED, "country: Landia\nMount Foo"), (RAW, "country: Landia")]))
    row = Evidence(
        kind="literal",
        asset_id="asset",
        region_id="label",
        observation_ids=["o-label-0"],
        source="label",
        locator="region:label",
        excerpt="country: Landia",
    )
    run.evidence.append(row)
    run.fields["country"] = FieldValue(
        state=ValueState.SUPPORTED, literal=value, parsed=value, evidence_ids=[row.id]
    )
    return run, row


def test_a_candidate_that_agrees_with_a_keyed_line_adds_its_row_and_keeps_the_line():
    run, line = keyed_run("Landia")
    apply(run, candidate("country", "1A", "Landia", "country: Landia"))
    field = run.fields["country"]
    assert field.state == ValueState.SUPPORTED
    assert field.evidence_ids[0] == line.id and len(field.evidence_ids) == 2


def test_a_candidate_that_differs_from_a_keyed_line_makes_the_field_ambiguous():
    run, line = keyed_run("Elsewhere")
    apply(run, candidate("country", "1A", "Landia", "country: Landia"))
    field = run.fields["country"]
    assert field.state == ValueState.AMBIGUOUS and field.literal == "Elsewhere"
    assert len(field.evidence_ids) == 2


# --- What the organiser reads --------------------------------------------------


def observation(identifier, region, text):
    return SimpleNamespace(id=identifier, region_id=region, literal_text=text)


def transcript(region, text, selected, *ids, resolved=True):
    return Transcript(
        region_id=region,
        text=text,
        observation_ids=list(ids),
        alternatives=[],
        resolved=resolved,
        selected_observation_id=selected,
    )


def pilot_run():
    observations = [
        observation("a1", "r1", "Alpha\nBeta"),
        observation("a2", "r1", "Alpha\nBeta"),
        observation("b1", "r2", "Gamma"),
        observation("b2", "r2", "Gamma, x"),
        observation("c1", "r3", "Delta"),
        observation("c2", "r3", "  \n"),  # a reader that returned nothing
    ]
    transcripts = [
        transcript("r1", "Alpha\nBeta", "a1", "a1", "a2"),
        transcript("r2", None, None, "b1", "b2", resolved=False),
        transcript("r3", "Delta", "c1", "c1", "c2"),
    ]
    return SimpleNamespace(
        regions=[SimpleNamespace(id=r) for r in ("r1", "r2", "r3")],
        observations=observations,
        transcripts=transcripts,
    )


def test_every_reading_of_every_label_is_read_the_decided_one_first():
    readings = extraction_readings(pilot_run())
    assert [(r.region_id, r.observation_id, r.role) for r in readings] == [
        ("r1", "a1", DECIDED),
        ("r1", "a2", RAW),
        ("r2", "b1", RAW),  # no decided transcript: its readings are still read
        ("r2", "b2", RAW),
        ("r3", "c1", DECIDED),  # the empty reading is not
    ]
    assert list(labelled(readings)) == ["1A", "1B", "2A", "2B", "3A"]


def test_a_reviewer_edited_transcript_is_the_decided_reading():
    run = pilot_run()
    run.transcripts[0] = transcript("r1", "Alpha edited", "a1", "a1", "a2")
    readings = extraction_readings(run)[:3]
    assert [(r.observation_id, r.role, r.text) for r in readings] == [
        ("a1", DECIDED, "Alpha edited"),
        ("a1", RAW, "Alpha\nBeta"),
        ("a2", RAW, "Alpha\nBeta"),
    ]


def test_readings_a_child_was_handed_are_used_as_they_are():
    run = SimpleNamespace(readings=[Reading("r", "o", RAW, "x")], observations=[])
    assert extraction_readings(run) == [Reading("r", "o", RAW, "x")]


def test_the_request_names_every_reading_and_keeps_its_text_exactly():
    female = "\N{FEMALE SIGN} legs 'quoted' é"
    names = labelled(
        [
            Reading("r1", "a1", DECIDED, f"Alpha\n{female}"),
            Reading("r1", "a2", RAW, "Alpha"),
            Reading("r2", "b1", RAW, "Gamma"),
        ]
    )
    text = request_text(["taxon", "country"], names)
    assert text.splitlines()[0] == "Fields: taxon, country"
    assert f"Reading 1A (decided transcript):\nAlpha\n{female}\nEnd of reading 1A." in text
    assert "Reading 1B (raw reading):\nAlpha\nEnd of reading 1B." in text
    assert "Label 2 (no decided transcript)" in text and "Label 1 (no" not in text
    assert "Reading 2A (raw reading):\nGamma\nEnd of reading 2A." in text


# --- The locator is the stored shape W5 reads ----------------------------------


def test_a_locator_round_trips_and_other_locators_are_not_candidates():
    where = CandidateLocation("12B", "obs-1", 3, 20, 5, 9)
    assert format_locator(where) == "reading:12B:obs-1#quote=3-20;literal=5-9"
    assert parse_locator(format_locator(where)) == where
    for other in (None, "", "region:label", "candidate:123", "reading:1A:o#quote=1-2"):
        assert parse_locator(other) is None


def test_a_stored_candidate_is_never_guessed():
    run = specimen_run()
    apply(run, candidate("collectors", "2A", "J. Q. Collector", "Landia\nJ. Q. Collector"))
    assert len(stored_candidates(run.fields, run.evidence, texts(run))) == 1
    # Another text under the same observation (a stale or foreign snapshot): the
    # spans do not fit, so no candidate is read from the row.
    assert stored_candidates(run.fields, run.evidence, {"o-locality-0": "short"}) == []
    assert stored_candidates(run.fields, run.evidence, {}) == []
    # A row with an unrelated source is not a candidate row.
    run.evidence[0] = run.evidence[0].model_copy(update={"source": "label"})
    assert stored_candidates(run.fields, run.evidence, texts(run)) == []


def test_the_stored_shape_has_no_typed_field_the_projector_pin_would_hash():
    # domain.py is hashed into CANONICAL_PROJECTOR_SHA256: the organiser stores
    # its candidates in the fields Evidence and FieldValue already have.
    run = specimen_run()
    apply(run, candidate("collectors", "2A", "J. Q. Collector"))
    (row,) = run.evidence
    assert set(row.model_dump()) == set(Evidence.model_fields)
    assert row.source == SOURCE == "bounded_extraction_v1"
    assert row.kind == "literal" and row.raw_ref == "raw" and row.digest == "d"
    assert set(Evidence.model_fields) == {
        "id", "kind", "asset_id", "region_id", "observation_ids", "source",
        "locator", "excerpt", "raw_ref", "digest", "created_at",
    }


# --- The call: one text-only call per specimen, every reading in it -----------


def scripted_gateway(answer, seen):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    class Gateway:
        def model_for(self, route):
            def respond(messages, info):
                seen.append(messages)
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, answer)]
                )

            return FunctionModel(respond, model_name="synthetic-organiser")

    return Gateway()


def extraction_specimen(run):
    from specimen_digitization.application.domain import BudgetUsage, Profile
    from specimen_digitization.prompts import PromptName, ResolvedPrompt

    run.profile = Profile()
    run.usage = BudgetUsage()
    run.dependencies = {
        "prompts": {
            PromptName.STRUCTURED_EXTRACTION.value: ResolvedPrompt(
                name=PromptName.STRUCTURED_EXTRACTION,
                text="Organise fields.",
                requested_label="test",
                served_label=None,
                version=None,
                resolution_reason="code_default",
            ).model_dump(mode="json")
        }
    }
    return SimpleNamespace(run=run, asset=SimpleNamespace(id="asset"))


def user_text(seen):
    (messages,) = seen
    return "\n".join(
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt"
    )


def test_one_call_reads_both_readers_and_the_undecided_label_and_merges_across_labels(tmp_path):
    from specimen_digitization.application.storage import LocalBlobs

    run = make_run(
        ("slide", [(DECIDED, "Genus alpha\nAB-12-34-1"), (RAW, "Genus alpha\nAB-12-34-1")]),
        ("locality", [(DECIDED, LOCALITY_A), (RAW, LOCALITY_B)]),
        ("back", [(RAW, "sp 22 of Genus alpha"), (RAW, "sp 22 of Genus alpha")]),
    )
    seen = []
    answer = {
        "candidates": [
            {"field_key": "taxon", "reading": "1A", "literal": "Genus alpha", "source_excerpt": "Genus alpha"},
            {"field_key": "taxon", "reading": "3B", "literal": "Genus alpha", "source_excerpt": "sp 22 of Genus alpha"},
            {"field_key": "collectors", "reading": "2B", "literal": "J. Q. Collecter", "source_excerpt": "J. Q. Collecter"},
        ],
        "unresolved": ["habitat"],
    }
    blobs = LocalBlobs(tmp_path / "blobs")
    specimen = extraction_specimen(run)

    harness.extract_with_agent(scripted_gateway(answer, seen), blobs, specimen)

    sent = user_text(seen)
    for name, text in (("1A", "Genus alpha\nAB-12-34-1"), ("2A", LOCALITY_A), ("2B", LOCALITY_B), ("3A", "sp 22 of Genus alpha")):
        assert f"Reading {name} (" in sent and text in sent
    assert "Label 3 (no decided transcript)" in sent
    assert "source_transcripts" not in sent
    # The taxon spread over two labels: one value, a row for each label.
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.SUPPORTED and taxon.literal == "Genus alpha"
    assert [parse_locator(rows(run)[i].locator).label for i in taxon.evidence_ids] == ["1A", "3B"]
    # The other reader's reading of a decided label is a lead, not the value.
    assert run.fields["collectors"].literal is None
    assert [parse_locator(rows(run)[i].locator).label for i in run.fields["collectors"].evidence_ids] == ["2B"]
    # The model's whole answer is the one raw blob every row points at.
    raws = {e.raw_ref for e in run.evidence}
    assert len(raws) == 1 and b"habitat" in blobs.get(next(iter(raws)))
    assert run.usage.tokens > 0


def test_a_model_answer_in_the_old_shape_is_not_stored(tmp_path):
    # A model that still answers with region_id (no reading) fails the schema, is
    # retried once, and then the call is malformed (a known operational block).
    from specimen_digitization.application.reliability import AdapterFailure
    from specimen_digitization.application.storage import LocalBlobs

    run = specimen_run()
    answer = {
        "candidates": [
            {"field_key": "country", "region_id": "locality", "literal": "Landia", "source_excerpt": "Landia"}
        ],
        "unresolved": [],
    }
    with pytest.raises(AdapterFailure):
        harness.extract_with_agent(
            scripted_gateway(answer, []), LocalBlobs(tmp_path / "blobs"), extraction_specimen(run)
        )
    assert run.evidence == []


# --- The rows hold up in a real specimen graph ---------------------------------


def test_candidate_rows_pass_the_ordinary_integrity_policy_and_literal_checks(tmp_path):
    from fastapi.testclient import TestClient
    from test_application import TOKEN, intake

    from specimen_digitization.application.api import local_app
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.evidence_runtime import source_literals
    from specimen_digitization.application.integrity import verify_evidence
    from specimen_digitization.application.policy import evaluate
    from specimen_digitization.application.storage import LocalBlobs

    app = local_app(tmp_path, TOKEN)
    with TestClient(app) as http:
        row = intake(http)
    specimen = app.state.workflow.repository.get(
        Scope(organization_id=row["organization_id"], collection_id=row["collection_id"]),
        row["specimen_id"],
    )
    run = specimen.run
    readings = extraction_readings(run)
    assert [r.role for r in readings] == [DECIDED, RAW]  # two readers, the first decided
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = b"the organiser's whole answer"
    apply_candidates(
        run,
        specimen.asset.id,
        ExtractionOutput(
            candidates=[
                candidate("taxon", "1A", "Danaus plexippus", "taxon: Danaus plexippus"),
                candidate("taxon", "1B", "Danaus plexippus", "Danaus plexippus"),
                candidate("collectors", "1B", "Synthetic Collector"),
            ]
        ),
        blobs.put(raw),
        hashlib.sha256(raw).hexdigest(),
    )

    verify_evidence(specimen, blobs)  # lineage, digests and the raw blob all hold
    reasons = evaluate(run)
    assert not [r for r in reasons if r.startswith(("evidence_", "pixel_lineage", "unsupported_"))]
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.SUPPORTED and taxon.literal == "Danaus plexippus"
    # The ordinary authority plan still finds the taxon's source literal in the
    # decided transcript; a row quoted from a raw reading is not one.
    found = {s.field_key: s for s in source_literals(specimen, blobs)}
    assert found["taxon"].literal == "Danaus plexippus"
    texts_by_observation = {o.id: o.literal_text for o in run.observations}
    candidates = stored_candidates(run.fields, run.evidence, texts_by_observation)
    assert [(c.field_key, c.label, c.literal) for c in candidates if c.field_key == "taxon"] == [
        ("taxon", "1A", "Danaus plexippus"),
        ("taxon", "1B", "Danaus plexippus"),
    ]
    assert [c.label for c in candidates if c.field_key == "collectors"] == ["1B"]


# --- The prompt (pins its text only; real-model compliance is the replay's) ---


def test_the_default_prompt_asks_for_readings_quotes_and_several_candidates():
    text = prompts._STRUCTURED_EXTRACTION_DEFAULT
    for needle in (
        "every reading of every label",
        "decided transcript",
        "raw reading",
        '"reading"',
        '"literal"',
        '"source_excerpt"',
        "differ",
        "Never normalize",
        "Every value needs a quote",
    ):
        assert needle in text, needle
    assert "{{collection_name}}" in text and "{{schema_version}}" in text
    assert "source_transcripts" not in text


def test_an_answer_may_hold_a_candidate_per_reading_per_field():
    many = [
        {"field_key": "taxon", "reading": "1A", "literal": "x", "source_excerpt": "x"}
    ] * 200
    assert len(ExtractionOutput.model_validate({"candidates": many}).candidates) == 200
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate({"candidates": many + many[:1]})


def test_the_json_the_model_is_asked_for_has_no_offsets():
    schema = ExtractionCandidate.model_json_schema()
    assert set(schema["properties"]) == {"field_key", "reading", "literal", "source_excerpt"}
    assert schema["additionalProperties"] is False
    assert "offset" not in json.dumps(schema) and "start" not in json.dumps(schema)
