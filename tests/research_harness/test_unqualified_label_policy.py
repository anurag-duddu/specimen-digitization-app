"""The committed research profile declares missing policy for the fields no unstructured label can ground.

Fifteen fields (the twelve literals, county, city and taxon) carry the missing
policy "unstructured_label_event_unqualified", as verbatim_dts carries its own.
A specialist's waiting_policy on one of them is then the existing
needs_human_review path (reason mandatory_unresolved:{field}); a waiting_source
on it, a failed or unconfigured source, is still an operational block. Nothing
in evidence.py (the validator and its VALIDATOR_SOURCE_SHA256 pin), the
projector or the connector SQL names a field, so none of them changes.
"""
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.research_harness import committed_pins, evidence, initial_requests
from specimen_digitization.research_harness.accepted_output import VALIDATOR_SOURCE_SHA256
from specimen_digitization.research_harness.canonical_materialization_v2 import BLOCKED, TERMINAL, _policy_held
from specimen_digitization.research_harness.committed_pins import build_committed_pins
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldResolution, HumanQuestion, ResearchScope,
    SourceCoverageReceipt, SourceCoverageState, SpecialistRequest, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import insects_profile, validate_resolution
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import geolocate_interpretation
from specimen_digitization.research_harness.status import ResearchStatusV1
from specimen_digitization.application.domain import FieldValue, ValueState

from test_production_bridge import checkpoint, thread, waiting

ORG, COLLECTION = "org-synthetic", "collection-synthetic"
POLICY = "unstructured_label_event_unqualified"
LITERALS = {FieldKey(key) for key in ("date_visited_from", "date_visited_to", "date_identified",
    "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft", "collectors",
    "fmnh_ins_number", "collection_code", "habitat", "collection_method")}
LOOKUPS = {FieldKey.COUNTY, FieldKey.CITY, FieldKey.TAXON}
DECLARED = LITERALS | LOOKUPS
NOT_DECLARED = {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION,
    FieldKey.IDENTIFIED_BY_IRN}
EVIDENCE_PY_SHA256 = "217d3dd472e6eddcd02f2cf9cb2d6588bd59fb7c30788e96e8993dc1cc71ba0f"  # pragma: allowlist secret


def pins():
    profile = published_registry().resolve("insects").profile
    return build_committed_pins(profile, organization_id=ORG, collection_id=COLLECTION)


def pinned_profile():
    return CollectionProfile.model_validate(pins()["profile"])


def declared(profile):
    return {row.field_key: row.missing_policy for row in profile.fields if row.missing_policy}


def test_the_committed_profile_declares_the_fifteen_fields_and_verbatim_dts_keeps_its_own():
    assert declared(pinned_profile()) == {
        **dict.fromkeys(DECLARED, POLICY), FieldKey.VERBATIM_DTS: "verbatim_dts_definition_examples"}


def test_the_other_four_fields_declare_none_and_the_irn_keeps_its_exception():
    rows = {row.field_key: row for row in pinned_profile().fields}
    assert {key for key in NOT_DECLARED if rows[key].missing_policy} == set()
    assert rows[FieldKey.IDENTIFIED_BY_IRN].exception == evidence.emu_irn_exception()
    assert set(rows) == set(ALL_FIELDS) and all(row.mandatory is True for row in rows.values())
    # The twenty fields, the sources and the exception are insects_profile's; only the policy differs.
    default = {row.field_key: row for row in insects_profile(ORG, COLLECTION).fields}
    assert all(row.model_copy(update={"missing_policy": default[key].missing_policy}) == default[key]
               for key, row in rows.items())


def test_evidence_py_still_declares_verbatim_dts_alone_and_its_validator_pin_is_unchanged():
    default = insects_profile(ORG, COLLECTION)
    assert declared(default) == {FieldKey.VERBATIM_DTS: "verbatim_dts_definition_examples"}
    source = Path(evidence.__file__).read_bytes()
    assert hashlib.sha256(source).hexdigest() == VALIDATOR_SOURCE_SHA256 == EVIDENCE_PY_SHA256
    assert pins()["sources"]["acceptance_boundary"]["validator_source_sha256"] == EVIDENCE_PY_SHA256


def test_the_job_pins_carry_the_profile_and_every_prompt_pin_its_digest():
    built = pins()
    profile = committed_pins.committed_research_profile(ORG, COLLECTION)
    assert built["profile"] == profile.model_dump(mode="json")
    assert digest(profile) != digest(insects_profile(ORG, COLLECTION))
    assert {row["profile_digest"] for row in built["prompts"].values()} == {digest(profile)}
    assert built == pins()  # two builds are equal


def test_the_policy_name_is_the_reason_the_request_factory_gives_an_unqualified_event():
    assert committed_pins.UNQUALIFIED_LABEL_POLICY == POLICY
    assert f'"{POLICY}"' in inspect.getsource(initial_requests)
    assert committed_pins.UNQUALIFIED_LABEL_FIELDS == DECLARED
    assert set(committed_pins.UNQUALIFIED_LABEL_LITERAL_FIELDS) == LITERALS and len(
        committed_pins.UNQUALIFIED_LABEL_LITERAL_FIELDS) == 12


def test_no_source_can_ground_a_literal_but_county_city_and_taxon_each_have_one():
    """The twelve literals have no source this deployment offers, so a source cannot fail for them
    and waiting_policy is unambiguous. Each lookup field has a ready source, so the prompt keeps
    waiting_source for a lookup that failed."""
    registry = committed_pins._committed_registry()
    ready = {key: [policy.id for policy in registry.policies if policy.ready and key in policy.fields]
             for key in ALL_FIELDS}
    assert {key: ready[key] for key in LITERALS} == {key: [] for key in LITERALS}
    assert set(ready[FieldKey.TAXON]) == {"gbif", "global_names_verifier", "catalogue_of_life"}
    assert ready[FieldKey.COUNTY] == ready[FieldKey.CITY] == ["geolocate"]


def coverage(source, key, state, reason):
    return SourceCoverageReceipt(source_id=source, field_key=key, state=state, source_version="v",
        coverage_limit="x", reason=reason)


def question(source, key, reason):
    return HumanQuestion(field_key=key, question="q?", reason="scoped_absence",
        coverage=(coverage(source, key, SourceCoverageState.SEARCHED, reason),))


def test_taxon_and_a_county_outside_the_usa_have_no_route_to_a_human_question():
    """Why county and taxon are declared: a completed GBIF search with no match cannot become a human
    question, and GEOLocate confirms a county only inside the USA, so no receipt exists for one."""
    with pytest.raises(ValueError, match="exhausted"):
        question("gbif", FieldKey.TAXON, "no_match")
    outside = json.dumps({"country": "Philippines", "state": "Davao del Sur", "locality": "Mount McKinley",
        "place": "Mount McKinley", "latitude": 7.2, "longitude": 125.3, "radius_km": 30, "value": "Davao del Sur"})
    with pytest.raises(ValueError, match="county only inside the USA"):
        geolocate_interpretation(outside, FieldKey.COUNTY)


@pytest.mark.parametrize("key", sorted((FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION)))
def test_country_state_and_precise_location_keep_their_route_so_they_are_not_declared(key):
    """A GEOLocate no_match on them is a human question already, so they need no declaration."""
    assert question("geolocate", key, "no_match: nothing agreed").field_key == key
    assert key not in declared(pinned_profile())


def request_for(role):
    scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id="synthetic", job_id="job",
        generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    prompt = resolve_prompt(role, profile_digest="f" * 64, source_registry_digest="a" * 64,
        toolset_digest="b" * 64, model_route="harness-deepseek", output_schema_digest="c" * 64)
    return SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt)


@pytest.mark.parametrize("key", sorted(DECLARED))
def test_the_validator_accepts_waiting_policy_for_a_declared_field_as_it_is(key):
    """The prompt's instruction needs no evidence.py change."""
    role = next(role for role, keys in ROLE_FIELDS.items() if key in keys)
    request = request_for(role)
    policy = FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state=ValueState.UNRESOLVED), reason=f"missing_policy:{POLICY} nothing on the label")
    assert validate_resolution(request, policy, ()) == policy


@pytest.mark.parametrize("key", sorted(ALL_FIELDS, key=str))
def test_only_a_waiting_policy_on_a_declared_field_is_held_and_no_waiting_source_ever_is(key):
    profile = pinned_profile()
    mapping = {str(item): str(item) for item in ALL_FIELDS}
    held = _policy_held({str(key): str(WorkState.WAITING_POLICY)}, profile, mapping)
    assert bool(held) == (key in DECLARED or key == FieldKey.VERBATIM_DTS)
    for state in BLOCKED - {str(WorkState.WAITING_POLICY)}:
        assert _policy_held({str(key): state}, profile, mapping) == frozenset()
    assert not BLOCKED & TERMINAL


@pytest.mark.parametrize("key", sorted(DECLARED))
def test_the_run_status_waits_on_people_for_a_held_field_and_blocks_for_a_failed_source(key):
    declared_fields = frozenset(declared(pinned_profile()))
    assert key in declared_fields
    held = checkpoint(FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(), reason="missing_policy"))
    failed = waiting(key, WorkState.WAITING_SOURCE)

    def status(view):
        return ResearchStatusV1.from_thread(view, missing_policy_fields=declared_fields).status
    assert status(thread(held)) == "waiting_input"
    assert status(thread(failed)) == "blocked"
    # Without the profile's declaration the same waiting_policy is an operational block.
    assert ResearchStatusV1.from_thread(thread(held)).status == "blocked"
