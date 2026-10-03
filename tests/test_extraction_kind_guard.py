"""The extraction-time guard refuses values the owner's written rules call wrong.

`harness.apply_candidates` once checked only that the extractor's quoted literal
occurs in the decided transcript. Real records then showed an elevation read
from a foot mark in the metres field, a slide-preparation code in Collection
Code, and a slide code in Date Identified, each "Supported". The three rules under test are G41 with GEOREFERENCING.md:172 (a
unit is never guessed), G45 (a slide-preparation code in a field no lookup
checks) and GEOREFERENCING.md:173 (a preparation code is never a date).

Fixtures: the label text is the stored decided transcript of each pilot
specimen (positions 2, 3, 5 and 7), and the candidates are the (field, literal)
pairs of the extractor's stored answers for those labels, each quoting the whole
label as its excerpt, as the stored answers do; no ids are kept. Position 3's raw
answer is not kept locally, so its candidates are rebuilt from its stored
supported fields. Nothing here calls a model.

Four things the guard deliberately does not do are pinned below as they are
today: the FMNHINS prefix in Collection Code, a piece of a slide-preparation
code ("IX" from "IX-17-66-2") in Collection Code, the "Sp.#1" morphospecies
number in Habitat, and anything in `verbatim_dts`. They document an open owner
question (what Collection Code and Habitat may hold) or a coordinator hold, not
a wanted outcome: when the owner rules, flip those assertions in the same change
that adds the rule.
"""

from types import SimpleNamespace

import pytest

from specimen_digitization.application import harness
from specimen_digitization.application.domain import (
    MANDATORY,
    FieldValue,
    Run,
    Transcript,
    ValueState,
)
from specimen_digitization.application.harness import (
    ExtractionCandidate,
    ExtractionOutput,
)
from specimen_digitization.application.policy import evaluate
from specimen_digitization.application.storage import LocalBlobs

# The Insects profile's date rules (application/profiles/published.json).
DATE_RULES = {
    "version": "date-rules-v1",
    "two_digit_year_century": 1900,
    "roman_numeral_months": True,
}
FEMALE = "\N{FEMALE SIGN}"

# Decided transcripts of the pilot labels, as stored.
P2 = (
    "IX-17-66-2\nE. slope Mt. McKinley\n3300', Davao Prov.\nMindanao,\n"
    "Philippine Islands\nIX-14-46\nH. Hoogstraal\nCNHM"
)
P3_LEFT = "V-4-67-1\nsp 22\nlegs"
P3_LOCALITY = "E. slope Mt. Apo,\nDavao Prov.,\nMindanao, P.I.\nH. Hoogstraal\nXI .46"
P3_BARCODE = "FMNHINS\n4486778"
P5 = (
    "IV-29-68-2\nYepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-25\n"
    f"1948, R.D. Mitchell\n{FEMALE} legs Sp.#1"
)
P7 = (
    "IX-17-66-1\nE. Slope Mt.\nMcKimley, Davao\nProv., Mindanao,\n"
    "Philippine Islands\nH. Hoogstraal\nIX-14-46 3300'\nCNHM"
)


def make_run(labels):
    """The three attributes `apply_candidates` reads. The worker's extraction child
    builds the same shape (model_runtime._model_child): it has no profile snapshot,
    so the guard must not read one."""
    return SimpleNamespace(
        evidence=[],
        fields={key: FieldValue() for key in MANDATORY},
        transcripts=[
            Transcript(
                region_id=region,
                text=text,
                observation_ids=["o-" + region],
                alternatives=[],
                resolved=True,
            )
            for region, text in labels.items()
        ],
    )


def candidates(run, region, pairs):
    """The extractor quoted the whole label as its excerpt, as the stored answers do."""
    text = next(t.text for t in run.transcripts if t.region_id == region)
    return [
        ExtractionCandidate(
            field_key=key, region_id=region, literal=literal, source_excerpt=text
        )
        for key, literal in pairs
    ]


def apply(run, *per_region):
    output = ExtractionOutput(
        candidates=[
            c for region, pairs in per_region for c in candidates(run, region, pairs)
        ]
    )
    harness.apply_candidates(run, "asset", output, "raw")


def supported(run, key):
    return run.fields[key].state == ValueState.SUPPORTED


def test_position_7_foot_mark_is_not_stored():
    run = make_run({"label": P7})
    apply(
        run,
        (
            "label",
            [
                ("country", "Philippine Islands"),
                ("province_state", "Davao"),
                ("county", "Mindanao"),
                ("city", "McKimley"),
                ("precise_location", "E. Slope Mt."),
                ("collectors", "H. Hoogstraal"),
                ("elevation_from_m", "3300"),  # the label writes 3300' (feet)
            ],
        ),
    )
    assert not supported(run, "elevation_from_m")
    for key in ("country", "province_state", "collectors", "precise_location"):
        assert supported(run, key), key


def test_position_7_a_piece_of_a_slide_code_stays_in_collection_code():
    # Documents a gap, not a wanted outcome. The extractor cut "IX" from the
    # top-edge code IX-17-66-1 (or from the date IX-14-46). Refusing a piece of a
    # hyphen-joined token is not a written owner rule, so the guard leaves it
    # alone: what Collection Code may hold, pieces of a slide code included, is an
    # open owner question. If the owner rules, flip this assertion with the rule.
    run = make_run({"label": P7})
    apply(run, ("label", [("collection_code", "IX")]))
    assert supported(run, "collection_code")
    assert run.fields["collection_code"].literal == "IX"


def test_position_2_slide_code_and_foot_mark_are_not_stored():
    run = make_run({"label": P2})
    apply(
        run,
        (
            "label",
            [
                ("collection_code", "IX-17-66-2"),
                ("elevation_from_m", "3300"),  # the label writes 3300' (feet)
                ("verbatim_dts", "IX-17-66-2"),
                ("collectors", "H. Hoogstraal"),
            ],
        ),
    )
    assert not supported(run, "elevation_from_m")
    assert not supported(run, "collection_code")
    # verbatim_dts is a finding only under the coordinator's hold (PLAN.md:227).
    assert supported(run, "verbatim_dts")
    assert supported(run, "collectors")


def test_position_5_code_is_not_collection_code_and_matching_unit_stays():
    run = make_run({"label": P5})
    apply(
        run,
        (
            "label",
            [
                ("collection_code", "IV-29-68-2"),
                ("elevation_from_ft", "4800"),
                ("elevation_to_ft", "4800"),
                ("elevation_from_m", "1463"),  # not on the label: the substring check
                ("city", "Yepocapa"),
                ("collection_method", f"{FEMALE} legs"),
                ("collectors", "R.D. Mitchell"),
                ("habitat", "Sp.#1"),
            ],
        ),
    )
    assert not supported(run, "collection_code")
    assert not supported(run, "elevation_from_m")
    # Controls: "4800 ft." is feet, the field is feet.
    assert run.fields["elevation_from_ft"].literal == "4800"
    assert supported(run, "elevation_from_ft") and supported(run, "elevation_to_ft")
    for key in ("city", "collection_method", "collectors"):
        assert supported(run, key), key
    # Out of scope today: a morphospecies number such as "Sp.#1" in Habitat is an
    # open owner question (is it a Taxon or a Habitat value, or neither?). This
    # documents that the guard leaves it alone; it is not a wanted outcome.
    assert supported(run, "habitat")


def test_position_3_slide_code_is_never_a_date():
    run = make_run({"left": P3_LEFT, "locality": P3_LOCALITY, "barcode": P3_BARCODE})
    apply(
        run,
        ("left", [("date_identified", "V-4-67-1"), ("taxon", "sp 22")]),
        (
            "locality",
            [
                ("verbatim_dts", "XI .46"),
                ("province_state", "Davao Prov."),
                ("collectors", "H. Hoogstraal"),
                ("country", "P.I."),
            ],
        ),
        ("barcode", [("collection_code", "FMNHINS"), ("fmnh_ins_number", "4486778")]),
    )
    assert not supported(run, "date_identified")
    assert supported(run, "fmnh_ins_number")
    for key in ("verbatim_dts", "province_state", "collectors", "country"):
        assert supported(run, key), key
    # Out of scope today: the FMNHINS catalog prefix in Collection Code is an open
    # owner question (what Collection Code holds). Documents the gap, not a wish.
    assert supported(run, "collection_code")


def test_a_real_date_and_a_matching_elevation_on_the_same_label_are_stored():
    # Constructed from the stored position-2 transcript: IX-14-46 is a date.
    run = make_run({"label": P2})
    apply(
        run,
        (
            "label",
            [
                ("date_visited_from", "IX-14-46"),
                ("elevation_from_ft", "3300"),  # 3300' is feet, the field is feet
            ],
        ),
    )
    assert supported(run, "date_visited_from")
    assert supported(run, "elevation_from_ft")


def test_a_refused_value_is_not_stored_but_the_raw_answer_is_kept(tmp_path):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.prompts import PromptName, ResolvedPrompt

    run = Run()
    run.transcripts = [
        Transcript(
            region_id="label",
            text=P7,
            observation_ids=["o-label"],
            alternatives=[],
            resolved=True,
        )
    ]
    run.dependencies = {
        "prompts": {
            PromptName.STRUCTURED_EXTRACTION.value: ResolvedPrompt(
                name=PromptName.STRUCTURED_EXTRACTION,
                text="Extract fields.",
                requested_label="test",
                served_label=None,
                version=None,
                resolution_reason="code_default",
            ).model_dump(mode="json")
        }
    }
    answer = {
        "candidates": [
            {
                "field_key": key,
                "region_id": "label",
                "literal": literal,
                "source_excerpt": P7,
            }
            for key, literal in (
                ("country", "Philippine Islands"),
                ("elevation_from_m", "3300"),
            )
        ],
        "unresolved": [],
    }

    class Gateway:
        def model_for(self, route):
            def respond(messages, info):
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, answer)]
                )

            return FunctionModel(respond, model_name="synthetic-extractor")

    blobs = LocalBlobs(tmp_path / "blobs")
    specimen = SimpleNamespace(run=run, asset=SimpleNamespace(id="asset"))
    harness.extract_with_agent(Gateway(), blobs, specimen)

    assert supported(run, "country")
    assert not supported(run, "elevation_from_m")
    assert run.fields["elevation_from_m"].literal is None
    assert len(run.evidence) == 1  # only the accepted candidate has an evidence row
    # The existing review reason carries the record on (G45: "goes to review").
    assert "mandatory_unresolved:elevation_from_m" in evaluate(run)
    # The extractor's whole answer, refused candidate included, stays in the blob.
    stored = [p for p in blobs.root.iterdir() if not p.name.startswith(".")]
    assert len(stored) == 1
    raw = stored[0].read_bytes()
    assert b"elevation_from_m" in raw and b"3300" in raw


UNIT = "elevation_unit_conflict"
CODE = "slide_preparation_code"
NOT_A_DATE = "preparation_code_is_not_a_date"
PART = "part_of_hyphenated_token_is_not_a_date"

# (field, literal, label text, expected refusal or None)
CASES = {
    # --- Elevation unit (G41): the unit the label writes must be the field's.
    "feet tick in the metres field": ("elevation_from_m", "3300", P2, UNIT),
    "feet tick after a slide code": ("elevation_from_m", "3300", P7, UNIT),
    "feet tick, to metres": ("elevation_to_m", "3300", "3300'", UNIT),
    "curly feet tick": (
        "elevation_from_m",
        "3300",
        "3300\N{RIGHT SINGLE QUOTATION MARK}",
        UNIT,
    ),
    "prime feet tick": ("elevation_from_m", "3300", "3300\N{PRIME}", UNIT),
    "ft in the metres field": ("elevation_from_m", "3300", "Elev. 3300 ft", UNIT),
    "ft. in the metres field": ("elevation_from_m", "4800", "Yepocapa,4800 ft.", UNIT),
    "FT without a space": ("elevation_from_m", "3300", "3300FT", UNIT),
    "feet in the metres field": ("elevation_from_m", "3300", "3300 feet", UNIT),
    "foot in the metres field": ("elevation_from_m", "3300", "3300 foot", UNIT),
    "m in the feet field": ("elevation_from_ft", "1005", "Elev. 1005 m", UNIT),
    "m. in the feet field": ("elevation_to_ft", "1005", "1005 m.", UNIT),
    "metres in the feet field": ("elevation_from_ft", "1005", "1005 metres", UNIT),
    "meters in the feet field": ("elevation_from_ft", "1005", "1005 meters", UNIT),
    "m without a space": ("elevation_to_ft", "1005", "1005m", UNIT),
    # Controls: the written unit is the field's, or none is written.
    "ft. in the feet field": ("elevation_from_ft", "4800", P5, None),
    "ft. in the to-feet field": ("elevation_to_ft", "4800", P5, None),
    "feet tick in the feet field": ("elevation_from_ft", "3300", P2, None),
    "m in the metres field": ("elevation_from_m", "1005", "1005 m", None),
    "metres in the metres field": ("elevation_to_m", "1005", "1005 metres", None),
    "bare number, metres field": ("elevation_from_m", "6400", "Elev. 6400", None),
    "bare number, feet field": ("elevation_from_ft", "6400", "Elev. 6400", None),
    # --- Ranges: an end mark belongs to both endpoints.
    "range in feet, first end, metres field": (
        "elevation_from_m",
        "3300",
        "3300-3500 ft",
        UNIT,
    ),
    "range in feet, last end, metres field": (
        "elevation_to_m",
        "3500",
        "3300-3500 ft",
        UNIT,
    ),
    "range in feet, spaced dash": ("elevation_from_m", "3300", "3300 - 3500 ft.", UNIT),
    "range in feet, 'to'": ("elevation_from_m", "3300", "3300 to 3500 ft", UNIT),
    "range with a tick": ("elevation_from_m", "3300", "3300-3500'", UNIT),
    "range in feet, first end, feet field": (
        "elevation_from_ft",
        "3300",
        "3300-3500 ft",
        None,
    ),
    "range in feet, last end, feet field": (
        "elevation_to_ft",
        "3500",
        "3300-3500 ft",
        None,
    ),
    "range in metres, feet field": ("elevation_from_ft", "3300", "3300-3500 m", UNIT),
    "range in metres, metres field": ("elevation_from_m", "3300", "3300-3500 m", None),
    "range, each end its own unit, first": (
        "elevation_from_m",
        "3300",
        "3300 m - 10800 ft",
        None,
    ),
    "range, each end its own unit, last": (
        "elevation_to_m",
        "10800",
        "3300 m - 10800 ft",
        UNIT,
    ),
    "range with no unit": ("elevation_from_m", "3300", "3300-3500", None),
    # --- Boundaries: refuse only a whole number with a mark right after it; when
    # the number is part of another, the mark is not immediate or there are two
    # readings, do not refuse.
    "number inside a bigger one": ("elevation_from_m", "300", "Elev. 1300 ft", None),
    "number inside a thousands group": ("elevation_from_m", "300", "3,300 ft", None),
    "number before a decimal": ("elevation_from_m", "3300", "3300.5 ft", None),
    "the group's own spelling": ("elevation_from_m", "3,300", "3,300 ft", UNIT),
    "space before an apostrophe year": ("elevation_from_m", "3300", "3300 '46", None),
    "possessive, not a tick": ("elevation_from_m", "3300", "3300's", None),
    "word that only starts with m": (
        "elevation_from_ft",
        "4800",
        "4800 mountain",
        None,
    ),
    "mm is not metres": ("elevation_from_ft", "4800", "4800 mm", None),
    "unit on the next line": ("elevation_from_m", "3300", "3300\nft", None),
    "both units written for it": ("elevation_from_m", "3300", "3300 ft\n3300 m", None),
    # --- Slide-preparation codes (G45), in the four fields: a value that IS a code.
    "slide code, collection code": ("collection_code", "IX-17-66-2", P2, CODE),
    "slide code, other label": ("collection_code", "IV-29-68-2", P5, CODE),
    "a piece of a slide code is left alone": ("collection_code", "IX", P7, None),
    "a date-shaped piece of a code is left alone": (
        "habitat",
        "IV-29-68",
        "IV-29-68-2",
        None,
    ),
    "a code, then words": (
        "habitat",
        "VI-24-68-7 epipsocus",
        "VI-24-68-7 epipsocus",
        CODE,
    ),
    "numeric slide code": ("collection_code", "10-6-78-1a", "10-6-78-1a", CODE),
    "words, then a code are not read as a code": (
        "collectors",
        "H. Hoogstraal VI-24-68-7",
        "H. Hoogstraal VI-24-68-7",
        None,
    ),
    "a code written with dots is not read": (
        "collection_code",
        "IX.17.66.2",
        "IX.17.66.2",
        None,
    ),
    "a piece of a hyphenated name is left alone": (
        "collectors",
        "Smith",
        "J. Smith-Jones",
        None,
    ),
    "a piece of a hyphenated habitat is left alone": (
        "habitat",
        "alpine",
        "sub-alpine meadow",
        None,
    ),
    "a piece of a hyphenated method is left alone": (
        "collection_method",
        "trap",
        "light-trap",
        None,
    ),
    "a piece of a hyphenated prefix is left alone": (
        "collection_code",
        "FMNH",
        "FMNH-INS 4486778",
        None,
    ),
    "the owner's example, habitat": (
        "habitat",
        "VI-24-68-7",
        "VI-24-68-7\nepipsocus",
        CODE,
    ),
    "the owner's example, collectors": ("collectors", "VI-24-68-7", "VI-24-68-7", CODE),
    "slide code, collection method": ("collection_method", "IX-17-66-1", P7, CODE),
    "name, collectors": ("collectors", "H. Hoogstraal", P2, None),
    "institution mark, collection code": ("collection_code", "CNHM", P2, None),
    "locality words, habitat": ("habitat", "E. slope", P3_LOCALITY, None),
    "method, collection method": ("collection_method", f"{FEMALE} legs", P5, None),
    "slide code in a field with its own lookup": ("city", "IX-17-66-2", P2, None),
    # --- verbatim_dts is a finding only (PLAN.md:227): never refused.
    "verbatim_dts holds a slide code": ("verbatim_dts", "IX-17-66-2", P2, None),
    "verbatim_dts holds a piece of a code": ("verbatim_dts", "IX", P7, None),
    # --- Dates: a preparation code is never a date (GEOREFERENCING.md:173).
    "slide code, date identified": ("date_identified", "V-4-67-1", P3_LEFT, NOT_A_DATE),
    "slide code, date visited from": (
        "date_visited_from",
        "IX-17-66-2",
        P2,
        NOT_A_DATE,
    ),
    "slide code, date visited to": ("date_visited_to", "IV-29-68-2", P5, NOT_A_DATE),
    "date-shaped part of a code, date": (
        "date_visited_from",
        "IV-29-68",
        P5,
        NOT_A_DATE,
    ),
    "a hyphen-written day range is a slide code to the parser": (
        "date_visited_from",
        "IV-23-25-48",
        "IV-23-25-48",
        NOT_A_DATE,
    ),
    # The parser also reads no part of any other hyphen-joined token (HARNESS.md:648-650,
    # warning part_of_hyphenated_token): not a slide code, the parser's own rule. The
    # guard follows the parser, so these are refused; no stored value depends on them.
    "part of another joined token": (
        "date_visited_from",
        "1946",
        "6-Sept-1946",
        PART,
    ),
    "end of a hyphenated year range": (
        "date_visited_from",
        "1948",
        "1948-1950",
        PART,
    ),
    "tail of a written day range": (
        "date_visited_to",
        "12 Sept. 1946",
        "10-12 Sept. 1946",
        PART,
    ),
    "start of a written day range": (
        "date_visited_from",
        "10",
        "Sept. 10-12, 1946",
        PART,
    ),
    "the whole written day range is not refused": (
        "date_visited_from",
        "10-12 Sept. 1946",
        "10-12 Sept. 1946",
        None,
    ),
    "Roman month date": ("date_visited_from", "IX-14-46", P2, None),
    "Roman month and year, spaced": ("date_visited_from", "XI .46", P3_LOCALITY, None),
    "a whole joined date": ("date_visited_from", "6-Sept-1946", "6-Sept-1946", None),
    "month and year": ("date_identified", "Sept. 1946", "Det. Sept. 1946", None),
    "year only": ("date_visited_to", "1948", P5, None),
    # --- Out of scope today (open owner questions): left as they are.
    "catalog prefix, collection code": ("collection_code", "FMNHINS", P3_BARCODE, None),
    "morphospecies number, habitat": ("habitat", "Sp.#1", P5, None),
    "specimen number, taxon": ("taxon", "sp 22", P3_LEFT, None),
    "locality text, city": ("city", "Mt. Apo", P3_LOCALITY, None),
    "locality text, precise location": ("precise_location", "E. Slope Mt.", P7, None),
    # A literal that carries its own wrong unit is not this guard's: the policy's
    # Decimal reading and the derivations flag it downstream.
    "own unit in the literal, metres field": (
        "elevation_from_m",
        "3300 ft",
        "3300 ft",
        None,
    ),
}


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_the_pure_function_refuses_exactly_these_values(case):
    from specimen_digitization.application.extraction_guard import extraction_refusal

    field_key, literal, text, expected = CASES[case]
    assert extraction_refusal(field_key, literal, text) == expected


@pytest.mark.parametrize(
    "rules",
    [
        None,
        DATE_RULES,
        {**DATE_RULES, "roman_numeral_months": False},
        {**DATE_RULES, "two_digit_year_century": None},
    ],
    ids=["none", "insects", "no roman months", "no century"],
)
def test_the_date_refusal_does_not_depend_on_the_profile_date_rules(rules):
    """The guard passes no date rules (the extraction child has none), which is
    sound only while `date_parser` decides a slide code or a hyphen-joined part
    without them. If that changes, this test says so."""
    from specimen_digitization.application.domain import LookupStatus
    from specimen_digitization.application.field_validators import date_parser

    for literal, text in (
        ("V-4-67-1", P3_LEFT),
        ("IX-17-66-2", P2),
        ("IV-29-68", P5),
        ("1946", "6-Sept-1946"),
    ):
        result = date_parser(literal, source_text=text, date_rules=rules)
        assert result.outcome == LookupStatus.NO_MATCH
        assert result.warnings in (["slide_code"], ["part_of_hyphenated_token"])
