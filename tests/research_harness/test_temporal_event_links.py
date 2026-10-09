"""Offline synthetic labels: explicit temporal context, never proximity inference."""
import asyncio
import json
import re

import pytest

from specimen_digitization.research_harness.contracts import EventKind, FieldKey, SpecialistRole, digest
from specimen_digitization.research_harness.evidence import EvidenceError, temporal_resolutions, validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry
from specimen_digitization.research_harness.temporal_context import TEMPORAL_LINK_RULE, qualify_temporal_links
from test_organiser_raw_reading_evidence import Label, build, request_for


def linked_case(*bodies, kind="Collecting", key="trip7", other_readers=None):
    labels, answers = [], []
    for index, body in enumerate(bodies, 1):
        text = f"{kind} event: {key}\n{body}"
        other = (other_readers or {}).get(index)
        labels.append(Label(text, other))
        for reader, reading in (("A", text), ("B", other or text)):
            for line in reading.splitlines():
                prefix, _, literal = line.partition(": ")
                if prefix not in {"Date", "Date from", "Date to", "Day and month", "Year", "Date order"}:
                    continue
                field = ("date_identified" if kind == "Determination" else
                         "date_visited_to" if prefix == "Date to" else "date_visited_from")
                answers.append((field, f"{index}{reader}", literal, line))
    built = build(labels, answers)
    return built, qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))


def linked_event(request):
    return next(item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE)


@pytest.mark.parametrize(("body", "canonical", "precision"), (
    ("Date: IX-14-46", "1946-09-14", "day"),
    ("Date: 3 sept. '46", "1946-09-03", "day"),
    ("Date: IX 1946", "1946-09", "month"),
    ("Date: 1946", "1946", "year"),
))
def test_event_link_preserves_historical_notation_and_written_precision(body, canonical, precision):
    built, request = linked_case(body)
    event = linked_event(request)
    written, copied = temporal_resolutions(request, event_id=event.id)
    assert written.value.normalized == copied.value.normalized == canonical
    assert written.value.precision == copied.value.precision == precision
    assert copied.derivation.rule_id == "G44"
    assert written.value.evidence_relations == copied.value.evidence_relations
    assert set(written.value.verbatim_by_observation.values()) <= {
        item.literal_text for item in built.specimen.run.observations}
    assert all(validate_resolution(request, item) == item for item in (written, copied))


def test_split_label_day_and_year_need_explicit_same_event_and_roles():
    built, request = linked_case("Day and month: IV-24", "Year: 1946")
    event = linked_event(request)
    assembly = next(item for item in request.assemblies if item.event_id == event.id)
    assert assembly.interpreted_text == "IV-24 1946"
    assert len(assembly.fragment_ids) == 2 and len(assembly.relation_ids) == 1
    written, copied = temporal_resolutions(request, event_id=event.id)
    assert written.value.literal is None
    assert written.value.normalized == copied.value.normalized == "1946-04-24"
    assert written.value.precision == "day"
    assert set(written.value.verbatim_by_observation.values()) == {
        "Collecting event: trip7\nDay and month: IV-24", "Collecting event: trip7\nYear: 1946"}
    broker = SourceBroker(SourceRegistry(()))
    parsed = asyncio.run(broker.invoke_utility(request, "parse_temporal", {
        "text": assembly.interpreted_text, "field_key": "date_visited_from"}))
    assert json.loads(parsed.candidate_json[0])["canonical"] == "1946-04-24"
    assert verify_local_utility_v2(request, parsed).text == "IV-24 1946"
    assert built.specimen.run.observations[0].literal_text.endswith("IV-24")


@pytest.mark.parametrize(("bodies", "other_readers"), (
    (("Day and month: IV-24",), None),
    (("Day and month: IV-24", "Year: 46"), None),
    (("Date: IV-24", "Year: 1946"), None),
    (("Date: 4-5-48",), None),
    (("Date: 1946-02-30",), None),
    (("Date: IX-14-46\nPrep. slide",), None),
    (("Day and month: IV-24", "Year: 1946"), {2: "Collecting event: another\nYear: 1946"}),
    (("Day and month: IV-24", "Year: 1946"), {2: "Collecting event: trip7\nYear: 1947"}),
    (("Date: IX-14-46", "Date: IX-15-46"), None),
))
def test_invalid_ambiguous_or_unverified_context_never_admits_an_event(bodies, other_readers):
    _, request = linked_case(*bodies, other_readers=other_readers)
    assert not [item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE]


@pytest.mark.parametrize(("order", "canonical"), (("DMY", "1948-05-04"), ("MDY", "1948-04-05")))
def test_numeric_order_requires_written_independent_event_context(order, canonical):
    _, request = linked_case(f"Date: 4-5-48\nDate order: {order}")
    written, _ = temporal_resolutions(request, event_id=linked_event(request).id)
    assert written.value.normalized == canonical
    assert written.value.literal == "4-5-48"


def test_determination_remains_a_separate_event_and_never_generates_collecting_endpoints():
    _, request = linked_case("Date: IX-14-46", kind="Determination")
    event = linked_event(request)
    assert event.kind == EventKind.DETERMINATION
    [written] = temporal_resolutions(request, event_id=event.id)
    assert written.field_key == FieldKey.DATE_IDENTIFIED
    assert not [item for item in request.assemblies if item.field_key != FieldKey.DATE_IDENTIFIED]


@pytest.mark.parametrize(("first", "last", "valid"), (
    ("IX-14-46", "IX-15-46", True),
    ("IX-15-46", "IX-14-46", False),
    ("1946", "1947-01", True),
    ("1946", "1946-09", False),
    ("1946-09", "1946-09-15", False),
    ("1946-09", "1946-09-30", True),
    ("1946-09-01", "1946-09", True),
))
def test_written_ranges_preserve_endpoints_and_require_order_at_written_precision(first, last, valid):
    _, request = linked_case(f"Date from: {first}", f"Date to: {last}")
    event = linked_event(request)
    if not valid:
        with pytest.raises(EvidenceError, match="reversed|precision"):
            temporal_resolutions(request, event_id=event.id)
        return
    written, end = temporal_resolutions(request, event_id=event.id)
    assert end.value_layer == "settled" and end.derivation is None and end.dependencies == ()
    assert end.value.literal == last
    assert validate_resolution(request, end) == end
    assert digest(written) != digest(end)


def test_unlinked_determination_year_cannot_complete_a_collecting_date():
    labels = (Label("Collecting event: trip7\nDay and month: IV-24"),
              Label("Determination event: trip7\nYear: 1946"))
    answers = [(field, name, literal, quote) for field, names, literal, quote in (
        ("date_visited_from", ("1A", "1B"), "IV-24", "Day and month: IV-24"),
        ("date_identified", ("2A", "2B"), "1946", "Year: 1946")) for name in names]
    built = build(labels, answers)
    request = qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))
    assert not [item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE]


@pytest.mark.parametrize(("bodies", "canonical"), (
    (("Date: 1946-09-14", "Year: 1946"), "1946-09-14"),
    (("Date: 5-5-48\nDate order: DMY",), "1948-05-05"),
    (("Date: 05-5-48\nDate order: DMY",), "1948-05-05"),
))
def test_complete_unambiguous_date_keeps_consistent_written_context(bodies, canonical):
    _, request = linked_case(*bodies)
    written, _ = temporal_resolutions(request, event_id=linked_event(request).id)
    assert written.value.normalized == canonical


@pytest.mark.parametrize("body", (
    "Date: 1946-09-14\nYear: 1947",
    "Date: 14-4-48\nDate order: MDY",
    "Date: 4-5-48\nDate order: guessed",
))
def test_conflicting_year_or_invalid_order_never_qualifies(body):
    _, request = linked_case(body)
    assert not [item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE]


@pytest.mark.parametrize("tamper", ("other_reader", "quote_offset", "excerpt", "unreadable"))
def test_cross_label_context_cannot_borrow_or_alter_reader_quote_evidence(tamper):
    built, _ = linked_case("Day and month: IV-24", "Year: 1946")
    original = request_for(built, SpecialistRole.TEMPORAL)
    candidate = next(item for item in original.organiser_candidates if item.literal == "1946")
    eid = candidate.evidence_ids[0]
    evidence = list(original.evidence)
    if tamper == "unreadable":
        original = original.model_copy(update={"fragments": tuple(item.model_copy(update={"unreadable": True})
            if item.observation_id == candidate.observation_id else item for item in original.fragments)})
    else:
        for index, row in enumerate(evidence):
            if row.id != eid:
                continue
            if tamper == "other_reader":
                other = next(item for item in original.organiser_candidates
                             if item.literal == "1946" and item.observation_id != candidate.observation_id)
                row = row.model_copy(update={"locator": row.locator.replace(candidate.observation_id, other.observation_id)})
            elif tamper == "quote_offset":
                row = row.model_copy(update={"locator": re.sub(r"#quote=(\d+)",
                    lambda match: "#quote=" + str(int(match[1]) + 1), row.locator)})
            else:
                row = row.model_copy(update={"excerpt": "Unrelated label states 1946"})
            evidence[index] = row
        original = original.model_copy(update={"evidence": tuple(evidence)})
    request = qualify_temporal_links(original)
    assert not [item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE]


@pytest.mark.parametrize("kind", ("Collecting", "Determination"))
def test_different_event_keys_cannot_select_a_specimens_date_by_model_choice(kind):
    field = "date_visited_from" if kind == "Collecting" else "date_identified"
    labels = (Label(f"{kind} event: trip7\nDate: IX-14-46"),
              Label(f"{kind} event: trip8\nDate: IX-15-46"))
    answers = [(field, f"{index}{reader}", literal, f"Date: {literal}")
        for index, literal in ((1, "IX-14-46"), (2, "IX-15-46")) for reader in ("A", "B")]
    built = build(labels, answers)
    request = qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))
    events = [item for item in request.events if item.validator_version == TEMPORAL_LINK_RULE]
    assert len(events) == 2  # Both raw event hypotheses remain visible.
    for event in events:
        with pytest.raises(EvidenceError, match="event selection"):
            temporal_resolutions(request, event_id=event.id)


def test_a_written_unlinked_to_does_not_trigger_g44_or_drop_valid_from():
    labels = (Label("Collecting event: trip7\nDate from: IX-14-46"),
              Label("date_visited_to: IX-15-46", decided="a"))
    answers = [("date_visited_from", f"1{reader}", "IX-14-46", "Date from: IX-14-46") for reader in ("A", "B")]
    built = build(labels, answers, keyed=True)
    request = qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))
    [written] = temporal_resolutions(request, event_id=linked_event(request).id)
    assert written.field_key == FieldKey.DATE_VISITED_FROM and written.value.normalized == "1946-09-14"
    assert validate_resolution(request, written) == written
    assert not written.dependencies and written.derivation is None


@pytest.mark.parametrize(("key", "literal"), (("trip8", "IX-15-46"), ("trip8", "IV-15"),
    ("trip7", "IV-15"), ("trip7", "1946-02-30")))
def test_printed_to_only_or_ambiguous_endpoint_is_not_replaced_with_a_from_copy(key, literal):
    labels = (Label("Collecting event: trip7\nDate from: IX-14-46"),
              Label(f"Collecting event: {key}\nDate to: {literal}"))
    answers = [(field, f"{index}{reader}", value, quote)
        for index, field, value, quote in ((1, "date_visited_from", "IX-14-46", "Date from: IX-14-46"),
            (2, "date_visited_to", literal, f"Date to: {literal}")) for reader in ("A", "B")]
    built = build(labels, answers)
    request = qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))
    from_assembly = next(item for item in request.assemblies if item.field_key == FieldKey.DATE_VISITED_FROM)
    [written] = temporal_resolutions(request, event_id=from_assembly.event_id)
    assert written.value.normalized == "1946-09-14" and written.field_key == FieldKey.DATE_VISITED_FROM
    assert validate_resolution(request, written) == written
    assert not written.derivation and not written.dependencies


@pytest.mark.parametrize("other", ("4-5-48", "1946-02-30", "IV-15"))
def test_an_unsettled_competing_event_cannot_be_ignored_to_select_a_clear_one(other):
    labels = (Label("Collecting event: trip7\nDate: IX-14-46"),
              Label(f"Collecting event: trip8\nDate: {other}"))
    answers = [("date_visited_from", f"{index}{reader}", literal, f"Date: {literal}")
        for index, literal in ((1, "IX-14-46"), (2, other)) for reader in ("A", "B")]
    built = build(labels, answers)
    request = qualify_temporal_links(request_for(built, SpecialistRole.TEMPORAL))
    assembly = next(item for item in request.assemblies if item.field_key == FieldKey.DATE_VISITED_FROM)
    with pytest.raises(EvidenceError, match="event selection"):
        temporal_resolutions(request, event_id=assembly.event_id)
