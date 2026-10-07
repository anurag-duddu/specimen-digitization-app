"""Exact role spans distinguish repeated date components without guessing."""

import pytest

from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole
from specimen_digitization.research_harness.evidence import temporal_resolutions, validate_resolution
from specimen_digitization.research_harness.temporal_context import TEMPORAL_LINK_RULE, qualify_temporal_links
from test_temporal_event_links import linked_case, linked_event


@pytest.mark.parametrize(("body", "canonical", "precision"), (
    ("Date: 1946-09-14\nYear: 1946", "1946-09-14", "day"),
    ("Date: IX 1946\nYear: 1946", "1946-09", "month"),
    ("Date: 1946\nYear: 1946", "1946", "year"),
    ("Date: 1946-09-14\nYear: 1946\n" + "Note: 1946\n" * 9, "1946-09-14", "day"),
))
def test_repeated_year_with_exact_independent_role_quotes_remains_publishable(body, canonical, precision):
    built, request = linked_case(body)
    event = linked_event(request)
    written, copied = temporal_resolutions(request, event_id=event.id)
    assert written.value.normalized == copied.value.normalized == canonical
    assert written.value.precision == copied.value.precision == precision
    assert all(validate_resolution(request, row) == row for row in (written, copied))
    assert copied.derivation.rule_id == "G44"
    assert {row.literal_text for row in built.specimen.run.observations} == {"Collecting event: trip7\n" + body}
    assembly = next(row for row in request.assemblies if row.event_id == event.id)
    spans = [row for row in request.fragments if row.id in assembly.fragment_ids]
    assert len(spans) == 2
    assert {row.observation_text[row.start:row.end] for row in spans} == {body.splitlines()[0][6:], "1946"}


def test_temporal_qualification_is_idempotent_for_restored_evidence_graph():
    _, request = linked_case("Day and month: IV-24", "Year: 1946")
    replayed = qualify_temporal_links(request)
    assert replayed == request
    assert len([row for row in replayed.events if row.validator_version == TEMPORAL_LINK_RULE]) == 1


def test_identical_written_range_endpoints_are_distinct_quoted_roles():
    _, request = linked_case("Date from: 1946-09-14\nDate to: 1946-09-14")
    written, end = temporal_resolutions(request, event_id=linked_event(request).id)
    assert written.field_key == FieldKey.DATE_VISITED_FROM
    assert end.field_key == FieldKey.DATE_VISITED_TO and end.value_layer == "settled"
    assert end.derivation is None and end.dependencies == ()
    assert written.assembly_ids != end.assembly_ids
    assert all(validate_resolution(request, row) == row for row in (written, end))


@pytest.mark.parametrize("tamper", ("quote_offset", "literal_offset", "other_observation", "missing_quote",
    "legacy_quote", "hint_label"))
def test_repeated_temporal_role_needs_its_exact_independent_native_quote(tamper):
    from specimen_digitization.research_harness.temporal_context import qualify_temporal_links
    from test_organiser_raw_reading_evidence import request_for
    import re

    built, _ = linked_case("Date: 1946-09-14\nYear: 1946")
    request = request_for(built, SpecialistRole.TEMPORAL)
    year = next(row for row in request.evidence if row.excerpt == "Year: 1946")
    rows = []
    for row in request.evidence:
        if row.id == year.id:
            if tamper == "missing_quote":
                continue
            if tamper == "quote_offset":
                row = row.model_copy(update={"locator": re.sub(r"#quote=(\d+)",
                    lambda match: "#quote=" + str(int(match[1]) + 1), row.locator)})
            elif tamper == "literal_offset":
                row = row.model_copy(update={"locator": re.sub(r";literal=(\d+)",
                    lambda match: ";literal=" + str(int(match[1]) - 1), row.locator)})
            elif tamper == "other_observation":
                row = row.model_copy(update={"locator": re.sub(r":([^:]+)#quote=", ":another-observation#quote=", row.locator)})
            elif tamper == "legacy_quote":
                row = row.model_copy(update={"source_version": "legacy-region/v1"})
        rows.append(row)
    request = request.model_copy(update={"evidence": tuple(rows)})
    if tamper == "hint_label":
        request = request.model_copy(update={"organiser_candidates": tuple(row.model_copy(update={"label": "9Z"})
            if row.status == "ungrounded" else row for row in request.organiser_candidates)})
    qualified = qualify_temporal_links(request)
    assert not [row for row in qualified.events if row.validator_version == TEMPORAL_LINK_RULE]


def test_temporal_replay_refuses_changed_existing_graph_identity():
    from specimen_digitization.research_harness.evidence import EvidenceError

    _, request = linked_case("Day and month: IV-24", "Year: 1946")
    request = request.model_copy(update={"events": tuple(row.model_copy(update={"reason": "changed reason"})
        if row.validator_version == TEMPORAL_LINK_RULE else row for row in request.events)})
    with pytest.raises(EvidenceError, match="identity differs"):
        qualify_temporal_links(request)


def test_exact_temporal_validator_history_decodes_and_crossed_pairs_fail():
    from uuid import uuid4
    from pydantic import ValidationError
    from specimen_digitization.research_harness.accepted_output import (
        AcceptedOutputProofV1, PRIOR_VALIDATOR_SOURCE_SHA256, TEMPORAL_LINK_VALIDATOR_SOURCE_SHA256,
        VALIDATOR_SOURCE_SHA256, VALIDATOR_VERSION, validation_boundary_pins,
    )
    from specimen_digitization.research_harness.contracts import digest
    from test_specialist_feedback import policy_output

    _, request = linked_case("Date: IX-14-46")
    proof = AcceptedOutputProofV1(original_request=request, native_run_id=str(uuid4()),
        conversation_id="offline-temporal-history", resolutions=policy_output(request).resolutions,
        source_results=(), effect_ids=(), model_settings_digest=digest("offline temporal history"),
        **validation_boundary_pins())
    for version, sha in (("validate_resolution/v3", PRIOR_VALIDATOR_SOURCE_SHA256),
        ("validate_resolution/v4", TEMPORAL_LINK_VALIDATOR_SOURCE_SHA256),
        (VALIDATOR_VERSION, VALIDATOR_SOURCE_SHA256)):
        decoded = AcceptedOutputProofV1.model_validate({**proof.model_dump(mode="json"),
            "validator_version": version, "validator_source_sha256": sha})
        assert decoded.validator_version == version
    with pytest.raises(ValidationError, match="pair_unqualified"):
        AcceptedOutputProofV1.model_validate({**proof.model_dump(mode="json"),
            "validator_version": "validate_resolution/v4", "validator_source_sha256": VALIDATOR_SOURCE_SHA256})
