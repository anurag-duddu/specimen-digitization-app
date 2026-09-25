"""Field resolution from recorded tool outcomes (HARNESS.md section 9)."""

import hashlib
import json

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.application.domain import LookupStatus as S
from specimen_digitization.application.domain import ValueState as V
from specimen_digitization.application.field_resolution import (
    Called,
    Reading,
    Resolver,
    choose_reading,
    date_order_evidence,
)

# Region r1 of FMNH slide 105526330: the first pass picked Muse's reading.
MUSE = Reading(
    "r1", "o-muse", "decided_transcript", "Chimaltenago, GUAT.\nEpipsocus sp."
)
QWEN = Reading("r1", "o-qwen", "raw_reading", "Chimaltenango, GUAT.\nEpipocous sp.")
# The same region when the first pass picked none (G19).
RAW_MUSE = Reading("r1", "o-muse", "raw_reading", MUSE.text)
PLACE = {"o-muse": "Chimaltenago", "o-qwen": "Chimaltenango"}
TAXON = {"o-muse": "Epipsocus", "o-qwen": "Epipocous"}


def tool(**answers):
    """A fake tool: each literal answers with a preset Called; calls are kept."""
    made = []

    def call(literal, reading):
        made.append((literal, reading.observation_id))
        return answers[literal]

    call.made = made
    return call


def google(place_id="ChIJ-place", evidence="e-google", matched=None):
    """A Google success; `matched` is the literal it matched by name, if any."""
    return Called(
        S.SUCCESS,
        "geography_lookup",
        authority_id=place_id,
        normalized=matched,
        evidence={evidence: "supports"},
    )


def gbif(key="8MQRG", name="Epipsocus Hagen, 1866", **extra):
    return Called(
        S.SUCCESS,
        "taxonomy_verifier",
        authority_id=key,
        normalized=name,
        evidence={"e-gbif": "decides"},
        **extra,
    )


def failed(outcome, name="geography_lookup"):
    return Called(outcome, name)


def grounded(resolver, value):
    """(observation, excerpt) of each literal evidence item the value cites."""
    items = {e.id: e for e in resolver.evidence}
    return sorted(
        (items[i].observation_ids[0], items[i].excerpt)
        for i in value.evidence_ids
        if i in items
    )


def assert_one_relation_per_evidence(value):
    assert list(value.evidence_relations) == value.evidence_ids


def test_the_decided_literal_that_its_lookup_confirms_is_the_value():
    resolver, call = (
        Resolver([MUSE, QWEN], "asset-1"),
        tool(Chimaltenago=google(matched="Chimaltenago")),
    )

    value = resolver.settle("city", PLACE, call)

    assert (value.state, value.literal, value.authority_id) == (
        V.SUPPORTED,
        "Chimaltenago",
        "ChIJ-place",
    )
    assert (
        value.input_source,
        value.source_observation_id,
        value.source_region_id,
    ) == ("decided_transcript", "o-muse", "r1")
    assert (
        value.normalized == "Chimaltenago"
    )  # At most a reader's exactly matching literal (rule 1.6).
    assert value.evidence_relations["e-google"] == "supports"
    assert grounded(resolver, value) == [("o-muse", "Chimaltenago")]
    assert value.verbatim_by_observation == {}
    assert call.made == [("Chimaltenago", "o-muse")]  # The raw reading is not needed.
    assert resolver.findings == [] and resolver.blocker is None
    assert_one_relation_per_evidence(value)


def test_gbif_decides_and_its_accepted_name_is_the_normalized_value():
    resolver = Resolver([MUSE, QWEN], "asset-1")

    value = resolver.settle("taxon", TAXON, tool(Epipsocus=gbif()))

    assert (value.authority_id, value.normalized) == ("8MQRG", "Epipsocus Hagen, 1866")
    assert value.evidence_relations["e-gbif"] == "decides"


def test_a_raw_literal_settles_a_failed_decided_literal_and_the_verbatim_stays():
    resolver = Resolver([MUSE, QWEN], "asset-1")
    call = tool(
        Chimaltenago=failed(S.NO_MATCH), Chimaltenango=google(matched="Chimaltenango")
    )

    value = resolver.settle("city", PLACE, call)

    # G20 under G27: the decided literal stays the verbatim; the confirmed raw
    # reading is only the settled value's provenance (#88 section 4.3).
    assert (value.state, value.literal, value.authority_id) == (
        V.SUPPORTED,
        "Chimaltenago",
        "ChIJ-place",
    )
    assert (value.input_source, value.source_observation_id) == (
        "decided_transcript",
        "o-muse",
    )
    assert value.normalized == "Chimaltenango"
    assert grounded(resolver, value) == [("o-muse", "Chimaltenago")]
    assert call.made == [("Chimaltenago", "o-muse"), ("Chimaltenango", "o-qwen")]
    (finding,) = resolver.findings
    assert (finding.rule_id, finding.severity, finding.field_key) == (
        "spelling_disagreement",
        "warning",
        "city",
    )
    assert "e-google" in finding.evidence_ids
    assert_one_relation_per_evidence(value)


@pytest.mark.parametrize(
    "outcome, state", [(S.NO_MATCH, V.UNRESOLVED), (S.AMBIGUOUS, V.AMBIGUOUS)]
)
def test_when_both_literals_fail_the_decided_literal_goes_to_review(outcome, state):
    resolver = Resolver([MUSE, QWEN], "asset-1")
    call = tool(
        Epipsocus=failed(outcome, "taxonomy_verifier"),
        Epipocous=failed(S.NO_MATCH, "taxonomy_verifier"),
    )

    value = resolver.settle("taxon", TAXON, call)

    assert (value.state, value.literal, value.reason) == (
        state,
        "Epipsocus",
        f"lookup_{outcome.value}",
    )
    assert value.authority_id is None and value.normalized is None
    assert resolver.blocker is None and resolver.findings == []


def test_raw_readings_that_settle_to_different_values_are_a_conflict():
    third = Reading("r1", "o-third", "raw_reading", "Chimaltenanga, GUAT.")
    resolver = Resolver([MUSE, QWEN, third], "asset-1")
    call = tool(
        Chimaltenago=failed(S.NO_MATCH),
        Chimaltenango=google("p-1"),
        Chimaltenanga=google("p-2"),
    )

    value = resolver.settle("city", {**PLACE, "o-third": "Chimaltenanga"}, call)

    assert (value.state, value.reason, value.literal) == (
        V.AMBIGUOUS,
        "readings_conflict",
        "Chimaltenago",
    )
    assert value.authority_id is None


@pytest.mark.parametrize(
    "outcome", [S.RATE_LIMITED, S.TIMEOUT, S.PROVIDER, S.AUTHENTICATION, S.POLICY]
)
def test_an_operational_outcome_blocks_the_run_instead_of_deciding_the_field(outcome):
    resolver = Resolver([MUSE, QWEN], "asset-1")
    call = tool(Chimaltenago=failed(outcome))

    value = resolver.settle("city", PLACE, call)

    assert resolver.blocker == f"harness_geography_lookup_{outcome.value}"
    assert (value.state, value.authority_id) == (V.UNRESOLVED, None)
    assert call.made == [("Chimaltenago", "o-muse")]  # No fallback after a block.


def test_an_operational_outcome_in_the_fallback_also_blocks():
    resolver = Resolver([MUSE, QWEN], "asset-1")

    resolver.settle(
        "city",
        PLACE,
        tool(Chimaltenago=failed(S.NO_MATCH), Chimaltenango=failed(S.TIMEOUT)),
    )

    assert resolver.blocker == "harness_geography_lookup_timeout"


def test_with_no_decided_transcript_one_confirmed_reader_settles_and_each_reading_stays():
    resolver = Resolver([RAW_MUSE, QWEN], "asset-1")
    call = tool(
        Chimaltenago=failed(S.NO_MATCH), Chimaltenango=google(matched="Chimaltenango")
    )

    value = resolver.settle("city", PLACE, call)

    # G19 with G27 and G28: no single verbatim; the settled value is the place.
    assert (value.state, value.literal, value.authority_id) == (
        V.SUPPORTED,
        None,
        "ChIJ-place",
    )
    assert value.verbatim_by_observation == PLACE
    assert value.input_source_by_observation == dict.fromkeys(PLACE, "raw_reading")
    assert value.settled_observation_ids == ["o-qwen"]  # The confirmed reader.
    assert (
        value.input_source,
        value.source_region_id,
        value.source_observation_id,
    ) == (
        None,
        None,
        None,
    )
    assert value.normalized == "Chimaltenango"
    assert grounded(resolver, value) == sorted(PLACE.items())
    assert [f.rule_id for f in resolver.findings] == ["spelling_disagreement"]
    assert_one_relation_per_evidence(value)


def test_with_no_decided_transcript_gbif_names_the_settled_taxon():
    resolver = Resolver([RAW_MUSE, QWEN], "asset-1")

    value = resolver.settle(
        "taxon",
        TAXON,
        tool(Epipsocus=gbif(), Epipocous=failed(S.NO_MATCH, "taxonomy_verifier")),
    )

    assert (value.literal, value.normalized, value.settled_observation_ids) == (
        None,
        "Epipsocus Hagen, 1866",
        ["o-muse"],
    )
    assert value.verbatim_by_observation == TAXON


def test_readers_confirmed_on_the_same_value_clear_and_on_different_values_conflict():
    same = tool(Chimaltenago=google("p-1"), Chimaltenango=google("p-1"))
    different = tool(Chimaltenago=google("p-1"), Chimaltenango=google("p-2"))

    cleared = Resolver([RAW_MUSE, QWEN], "a").settle("city", PLACE, same)
    conflict = Resolver([RAW_MUSE, QWEN], "a").settle("city", PLACE, different)

    assert (cleared.state, cleared.authority_id) == (V.SUPPORTED, "p-1")
    assert (conflict.state, conflict.reason) == (V.AMBIGUOUS, "readings_conflict")
    assert (
        conflict.literal,
        conflict.source_observation_id,
        conflict.authority_id,
    ) == (None, None, None)
    assert conflict.verbatim_by_observation == PLACE


def test_with_no_decided_transcript_and_nothing_confirmed_the_readings_conflict():
    resolver = Resolver([RAW_MUSE, QWEN], "asset-1")

    value = resolver.settle(
        "city",
        PLACE,
        tool(Chimaltenago=failed(S.NO_MATCH), Chimaltenango=failed(S.AMBIGUOUS)),
    )

    assert (value.state, value.reason, value.literal) == (
        V.AMBIGUOUS,
        "readings_conflict",
        None,
    )
    assert value.settled_observation_ids == [] and value.source_region_id is None
    assert grounded(resolver, value) == sorted(PLACE.items())
    assert resolver.findings == []


def test_identical_raw_readings_are_looked_up_once_and_keep_their_literal():
    twin = Reading("r1", "o-twin", "raw_reading", RAW_MUSE.text)
    resolver, call = Resolver([RAW_MUSE, twin], "asset-1"), tool(Chimaltenago=google())

    value = resolver.settle(
        "city", {"o-muse": "Chimaltenago", "o-twin": "Chimaltenago"}, call
    )

    assert (value.state, value.literal, value.verbatim_by_observation) == (
        V.SUPPORTED,
        "Chimaltenago",
        {},
    )
    assert call.made == [("Chimaltenago", "o-muse")]


def test_a_field_no_reading_has_stays_unknown_and_calls_nothing():
    call = tool()

    assert (
        Resolver([MUSE, QWEN], "a").settle(
            "county", {"o-muse": None, "o-qwen": "Guatemala"}, call
        )
        == FieldValue()
    )
    assert (
        Resolver([RAW_MUSE, QWEN], "a").settle(
            "county", {"o-muse": None, "o-qwen": None}, call
        )
        == FieldValue()
    )
    assert call.made == []


def test_fields_no_tool_checks_are_transcribed_as_seen_and_conflicts_go_to_review():
    decided = Resolver([MUSE, QWEN], "a").transcribed(
        "collectors", {"o-muse": "GUAT.", "o-qwen": "GUAT."}
    )
    conflict = Resolver([RAW_MUSE, QWEN], "a").transcribed("collectors", PLACE)

    assert (decided.state, decided.literal, decided.input_source) == (
        V.SUPPORTED,
        "GUAT.",
        "decided_transcript",
    )
    assert (conflict.state, conflict.literal, conflict.verbatim_by_observation) == (
        V.AMBIGUOUS,
        None,
        PLACE,
    )


def test_tool_warnings_become_findings_with_their_evidence_and_never_reasons():
    resolver = Resolver([MUSE, QWEN], "asset-1")
    warned = gbif(warnings={"taxonomy_source_disagreement:col": ("e-col",)})

    value = resolver.settle("taxon", TAXON, tool(Epipsocus=warned))

    (finding,) = resolver.findings
    assert (finding.rule_id, finding.reason_code) == (
        "taxonomy_source_disagreement",
        "taxonomy_source_disagreement:col",
    )
    assert (finding.severity, finding.field_key, finding.evidence_ids) == (
        "warning",
        "taxon",
        ["e-col"],
    )
    assert value.reason == "settled_by:taxonomy_verifier"


def test_a_literal_that_is_not_in_its_reading_is_refused():
    with pytest.raises(ValueError, match="literal_not_in_source:o-muse"):
        Resolver([MUSE], "a").transcribed("habitat", {"o-muse": "Mossy forest"})


# A second label of the same slide (G32): its decided transcript spells the
# department as Google does.
LABEL_2 = Reading("r2", "o-muse-2", "decided_transcript", "Chimaltenango\nEpipsocus")


def test_two_labels_that_settle_the_same_place_clear_and_keep_both_spellings():
    resolver = Resolver([MUSE, QWEN, LABEL_2], "asset-1")
    call = tool(
        Chimaltenago=google("p-1", evidence="e-1"),
        Chimaltenango=google("p-1", evidence="e-2", matched="Chimaltenango"),
    )

    value = resolver.settle(
        "province_state", {**PLACE, "o-muse-2": "Chimaltenango"}, call
    )

    assert (value.state, value.authority_id, value.literal) == (
        V.SUPPORTED,
        "p-1",
        None,
    )
    assert value.verbatim_by_observation == {
        "o-muse": "Chimaltenago",
        "o-muse-2": "Chimaltenango",
    }
    assert value.input_source_by_observation == {
        "o-muse": "decided_transcript",
        "o-muse-2": "decided_transcript",
    }
    assert (
        value.source_region_id,
        value.source_observation_id,
        value.input_source,
    ) == (None, None, None)
    assert value.settled_observation_ids == ["o-muse", "o-muse-2"]
    assert value.normalized == "Chimaltenango"  # The label Google matched exactly.
    assert {"e-1", "e-2"} <= set(value.evidence_ids)
    assert_one_relation_per_evidence(value)
    assert [f.rule_id for f in resolver.findings] == ["spelling_disagreement"]


def test_two_labels_with_one_text_still_keep_each_labels_reading():
    other = Reading("r2", "o-muse-2", "decided_transcript", "Epipsocus")
    resolver = Resolver([MUSE, other], "asset-1")

    value = resolver.settle(
        "taxon",
        {"o-muse": "Epipsocus", "o-muse-2": "Epipsocus"},
        tool(Epipsocus=gbif()),
    )

    assert (value.state, value.literal, value.authority_id) == (
        V.SUPPORTED,
        None,
        "8MQRG",
    )
    both = {"o-muse": "Epipsocus", "o-muse-2": "Epipsocus"}
    assert value.verbatim_by_observation == both and resolver.findings == []
    assert value.settled_observation_ids == ["o-muse", "o-muse-2"]
    assert grounded(resolver, value) == [
        ("o-muse", "Epipsocus"),
        ("o-muse-2", "Epipsocus"),
    ]


@pytest.mark.parametrize(
    "second",
    [google("p-2", evidence="e-2"), failed(S.NO_MATCH)],
    ids=["another-place", "not-settled"],
)
def test_two_labels_that_do_not_settle_the_same_value_go_to_review(second):
    resolver = Resolver([MUSE, LABEL_2], "asset-1")
    call = tool(Chimaltenago=google("p-1", evidence="e-1"), Chimaltenango=second)

    value = resolver.settle(
        "province_state", {"o-muse": "Chimaltenago", "o-muse-2": "Chimaltenango"}, call
    )

    assert (value.state, value.reason, value.literal, value.authority_id) == (
        V.AMBIGUOUS,
        "labels_conflict",
        None,
        None,
    )
    assert value.verbatim_by_observation == {
        "o-muse": "Chimaltenago",
        "o-muse-2": "Chimaltenango",
    }
    assert grounded(resolver, value) == [
        ("o-muse", "Chimaltenago"),
        ("o-muse-2", "Chimaltenango"),
    ]
    assert "e-1" not in value.evidence_ids  # Only each label's reading, for review.
    assert value.settled_observation_ids == []


def test_a_field_no_tool_checks_needs_the_same_text_on_every_label():
    other = Reading("r2", "o-muse-2", "decided_transcript", "GUAT.\nF.G. Werner")
    resolver = Resolver([MUSE, other], "asset-1")

    same = resolver.transcribed(
        "country_text", {"o-muse": "GUAT.", "o-muse-2": "GUAT."}
    )
    different = resolver.transcribed(
        "collectors", {"o-muse": "Epipsocus sp.", "o-muse-2": "F.G. Werner"}
    )

    assert (same.state, same.literal, same.normalized) == (V.SUPPORTED, None, "GUAT.")
    assert same.verbatim_by_observation == {"o-muse": "GUAT.", "o-muse-2": "GUAT."}
    assert same.settled_observation_ids == ["o-muse", "o-muse-2"]
    assert (different.state, different.reason) == (V.AMBIGUOUS, "labels_conflict")
    assert different.settled_observation_ids == []


def test_a_label_without_the_field_does_not_count():
    resolver = Resolver([MUSE, LABEL_2], "asset-1")

    value = resolver.settle(
        "city",
        {"o-muse": "Chimaltenago", "o-muse-2": None},
        tool(Chimaltenago=google(matched="Chimaltenago")),
    )

    assert (value.state, value.literal, value.source_region_id) == (
        V.SUPPORTED,
        "Chimaltenago",
        "r1",
    )


def test_a_date_keeps_the_precision_and_rule_its_call_reports():
    parsed = Called(
        S.SUCCESS,
        "date_parser",
        parsed="1946-09",
        precision="month",
        century_rule="date-rules-v1:two_digit_year_century=1900",
    )
    resolver = Resolver(
        [Reading("r1", "o-muse", "decided_transcript", "Sept. '46")], "a"
    )

    value = resolver.settle(
        "date_collected", {"o-muse": "Sept. '46"}, tool(**{"Sept. '46": parsed})
    )

    assert (value.parsed, value.precision, value.century_rule) == (
        "1946-09",
        "month",
        "date-rules-v1:two_digit_year_century=1900",
    )
    assert value.normalized is None and value.authority_id is None
    assert resolver.findings == []


def date(*readings):
    """A date parser's `parsed`: (order, year, month, day) per reading."""
    keys = ("order", "year", "month", "day")
    return {
        "readings": [
            dict(zip(keys, r, strict=True)) | {"iso": f"{r[1]}-{r[2]:02d}-{r[3]:02d}"}
            for r in readings
        ]
    }


def test_a_date_order_comes_from_every_readings_unambiguous_dates():
    fixed = date(("day-month-year", 1948, 5, 13))  # 13-5-48
    same = date(("month-day-year", 1948, 5, 5))  # 5-5-48 fixes no order.
    open_ = date(("month-day-year", 1948, 4, 5), ("day-month-year", 1948, 5, 4))

    orders = date_order_evidence([fixed, same, open_, None])

    assert orders == {"day-month-year"}
    assert choose_reading(open_, orders)["iso"] == "1948-05-04"
    assert choose_reading(fixed, orders) is None  # Nothing to choose.


def test_dates_that_disagree_on_the_order_fix_none():
    # G33: a misread in one model's reading can block a choice, never make one.
    open_ = date(("month-day-year", 1948, 4, 5), ("day-month-year", 1948, 5, 4))
    orders = date_order_evidence(
        [date(("day-month-year", 1948, 5, 13)), date(("month-day-year", 1948, 5, 13))]
    )

    assert orders == {"day-month-year", "month-day-year"}
    assert choose_reading(open_, orders) is None
    assert choose_reading(open_, set()) is None


def test_a_label_settled_by_its_fallback_names_the_confirmed_raw_reading():
    # G32 with G20: label 1's decided "Chimaltenago" fails and its raw reading
    # settles the place; label 2 settles the same place directly.
    resolver = Resolver([MUSE, QWEN, LABEL_2], "asset-1")
    call = tool(
        Chimaltenago=failed(S.NO_MATCH),
        Chimaltenango=google("p-1", matched="Chimaltenango"),
    )

    value = resolver.settle(
        "province_state", {**PLACE, "o-muse-2": "Chimaltenango"}, call
    )

    assert (value.state, value.authority_id) == (V.SUPPORTED, "p-1")
    assert value.settled_observation_ids == ["o-qwen", "o-muse-2"]
    assert value.verbatim_by_observation == {
        "o-muse": "Chimaltenago",  # The decided verbatim stays (G27).
        "o-muse-2": "Chimaltenango",
    }


class Blobs:
    def __init__(self):
        self.puts = {}

    def put(self, data: bytes) -> str:
        ref = "blob/" + hashlib.sha256(data).hexdigest()[:8]
        self.puts[ref] = data
        return ref


def test_literal_evidence_stores_its_record_so_it_projects_like_any_evidence():
    blobs = Blobs()
    resolver = Resolver([MUSE], "asset-1", blobs=blobs)

    value = resolver.transcribed("country_text", {"o-muse": "GUAT."})

    (item,) = resolver.evidence
    assert item.id in value.evidence_ids and item.kind == "literal"
    record = blobs.puts[item.raw_ref]
    assert json.loads(record) == {
        "region_id": "r1",
        "observation_ids": ["o-muse"],
        "excerpt": "GUAT.",
    }
    assert item.digest == hashlib.sha256(record).hexdigest()
