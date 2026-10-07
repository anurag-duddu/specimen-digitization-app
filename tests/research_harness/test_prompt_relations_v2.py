"""The G23 relation rule in the five non-geography v2 prompts (2026-10-03).

Each v2 file is its v1 file followed by the rule. Taxonomy, parties and
collection get the shared block and their role line. Temporal and measurement
get the option (b) text (coordinator ruling, until the owner decides on the
evidence helpers): the validator admits only the settlement's exact result for a
written date or an elevation, and the helpers set no relation, so those roles
copy the settlement's relations and add none.
"""

import hashlib
from pathlib import Path

import pytest

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, EventHypothesis, EventKind, FieldKey, ResearchScope, SourceFragment, SpecialistRequest,
    SpecialistRole,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, elevation_resolutions, settle_elevation, temporal_resolutions,
    validate_resolution,
)
from specimen_digitization.research_harness.prompts import (
    HANDOVER_PROMPT_VERSION, MEASUREMENT_EVIDENCE_PROMPT_VERSION, QUALIFIED_PROMPT_VERSION, RELATIONS_PROMPT_VERSION, ROLE_PROMPTS,
    TAXONOMY_QUERY_PROMPT_VERSION, TEMPORAL_CONTEXT_PROMPT_VERSION, resolve_prompt,
)
from specimen_digitization.research_harness.sources import insects_registry

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
FIVE = (SpecialistRole.TAXONOMY, SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT,
        SpecialistRole.PARTIES, SpecialistRole.COLLECTION)
SETTLED = (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT)
SHARED = """Evidence relations (G23): a supported value's value.evidence_relations maps each
id in value.evidence_ids, and no other id, to the role that evidence item
declares: the role field of the lookup_source result's evidence, or of the
request's evidence list. Label evidence an accepted literal assembly cites is
"supports". There is no default; an unresolved, ambiguous or unknown value needs
no relation.
"""
ROLE_LINES = {
    SpecialistRole.TAXONOMY: "On a resolved taxon, evidence_ids and value.evidence_ids are exactly the matching "
        "results' evidence ids; value.evidence_relations maps GBIF's deciding evidence to \"decides\" and each "
        "supporting source's to \"supports\".",
    SpecialistRole.PARTIES: "A collector resolved from an accepted literal assembly maps its evidence ids to "
        "\"supports\"; one from an exact public join maps that result's evidence to its declared role. The IRN "
        "exception carries no relation.",
    SpecialistRole.COLLECTION: "A catalog number, collection code, habitat or method resolved from an accepted "
        "literal assembly maps each of its evidence ids to \"supports\". verbatim_dts stays waiting_policy and "
        "carries none.",
}

# Lookup-citing resolutions name their assemblies and event, as Lane G's
# geography v2 says (#240), so the lookup has a producer.
LOOKUP_PRODUCER_RULE = (
    "Every resolution that cites a lookup names, as the common rules ask, its accepted/rejected "
    "assemblies (assembly_ids: the request's assemblies for that field that the interpretation read) "
    "and event (event_id); the lookup's producer comes from them, and publication refuses a lookup "
    "without one.")


def added(role):
    v1 = (ROOT / f"{role.value}-v1.txt").read_bytes()
    v2 = (ROOT / f"{role.value}-v2.txt").read_bytes()
    assert v2.startswith(v1)
    return v2[len(v1):].decode("ascii")


def flat(text):
    return " ".join(text.split())


@pytest.mark.parametrize("role", FIVE)
def test_each_v2_file_is_its_v1_text_followed_by_the_relation_rule_and_the_pin_extends_it(role):
    # The v2 files stay on disk as the audit record (their digests: test_geography_prompt_v2.py). The live
    # pins moved to the v3 files (test_prompt_reading_citation_v3.py), then to the v4 files, each the v3
    # file followed by the missing-policy block (test_prompt_missing_policy_v4.py), then to the v5 files,
    # each the v4 file followed by the hand-over block (test_prompt_handover_v5.py); all extend the v2 text.
    version = 9 if role == SpecialistRole.MEASUREMENT else 7 if role == SpecialistRole.TEMPORAL else 6 if role == SpecialistRole.TAXONOMY else 5
    assert ROLE_PROMPTS[role] == (f"{role.value}-v{version}.txt",
        MEASUREMENT_EVIDENCE_PROMPT_VERSION if role == SpecialistRole.MEASUREMENT else
        TEMPORAL_CONTEXT_PROMPT_VERSION if role == SpecialistRole.TEMPORAL else
        TAXONOMY_QUERY_PROMPT_VERSION if role == SpecialistRole.TAXONOMY else
        QUALIFIED_PROMPT_VERSION if role in SETTLED else HANDOVER_PROMPT_VERSION)
    assert RELATIONS_PROMPT_VERSION == "specialists-relations-v2-2026-10-03"
    (ROOT / f"{role.value}-v2.txt").read_bytes().decode("ascii")
    rule = added(role)
    assert rule.startswith("Evidence relations (G23): ") and "value.evidence_relations" in rule
    prompt = resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                            model_route="harness-deepseek", output_schema_digest=PIN)
    v2 = (ROOT / f"{role.value}-v2.txt").read_text(encoding="utf-8")
    if role == SpecialistRole.MEASUREMENT:
        assert (ROOT / "specimen_measurement-v7.txt").read_text().startswith(v2)
        assert "evidence relations" in prompt.text
        assert "without changing those objects or their provenance" in prompt.text
    elif role == SpecialistRole.TEMPORAL:
        assert rule.strip() in prompt.text
    else:
        assert prompt.text.startswith((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n" + v2)
    assert prompt.digest == hashlib.sha256(prompt.text.encode()).hexdigest()


@pytest.mark.parametrize("role", tuple(ROLE_LINES))
def test_taxonomy_parties_and_collection_get_the_shared_block_and_their_role_line(role):
    rule = added(role)
    assert rule.startswith(SHARED)
    assert flat(rule[len(SHARED):]) == ROLE_LINES[role] + " " + LOOKUP_PRODUCER_RULE


@pytest.mark.parametrize("role", SETTLED)
def test_temporal_and_measurement_copy_the_settlement_and_ask_for_no_relation(role):
    rule = flat(added(role))
    assert "exactly as the settlement gives it" in rule or "exactly as the G24/G29/G44 settlement gives it" in rule
    assert "add no relation the settlement does not give" in rule
    # No relation value is asked for on a settled value; label evidence is not
    # said to be "supports" (option (a) would add that with the helper change).
    assert '"supports"' not in rule and "Label evidence" not in rule


def test_temporal_still_maps_an_exact_joined_source_date_to_its_declared_role():
    assert "An exact-joined source date maps its result's evidence to the declared role." in flat(
        added(SpecialistRole.TEMPORAL))


SCOPE = ResearchScope(organization_id="org", collection_id="insects", specimen_id="synthetic", job_id="job",
                      generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)


def settled_request(role, field_key, text):
    fragment = SourceFragment(id="line", scope=SCOPE, asset_id="asset", asset_generation="1", asset_digest=PIN,
        label_id="label", region_id="label", observation_id="observation", reader="independent-reader",
        model_id="fake", prompt_digest=PIN, observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=0, end=len(text), literal=text,
        order=0)
    event = EventHypothesis(id="event", scope=SCOPE, kind=EventKind.COLLECTING, fragment_ids=(fragment.id,),
        evidence_ids=("role-evidence",), reason="Independently annotated synthetic event", status="accepted",
        validator_version="gold-v1")
    assembly = assemble_field(assembly_id="assembly", scope=SCOPE, field_key=field_key, fragments=(fragment,),
                              event=event)
    prompt = resolve_prompt(role, profile_digest=PIN, source_registry_digest=insects_registry().digest,
                            toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    return SpecialistRequest(scope=SCOPE, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt,
                             fragments=(fragment,), events=(event,), assemblies=(assembly,))


def test_settled_date_and_elevation_require_the_exact_helper_relations():
    """The settlement helpers now provide supports relations for native evidence.
    A model cannot omit them while claiming the same deterministic settlement."""
    dates = settled_request(SpecialistRole.TEMPORAL, FieldKey.DATE_VISITED_FROM, "2020-06-01")
    elevations = settled_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_M, "180 m")
    settled = [(dates, item) for item in temporal_resolutions(dates, event_id="event")] + [
        (elevations, item) for item in elevation_resolutions(settle_elevation(elevations, assembly_ids=("assembly",)))]
    assert {str(item.field_key) for _, item in settled} == {"date_visited_from", "date_visited_to",
        "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"}
    for request, item in settled:
        assert item.value.evidence_ids
        assert item.value.evidence_relations == dict.fromkeys(item.value.evidence_ids, "supports")
        assert validate_resolution(request, item) == item
        related = item.model_copy(update={"value": item.value.model_copy(update={"evidence_relations": {}})})
        with pytest.raises(EvidenceError, match="differs from (exact )?deterministic"):
            validate_resolution(request, related)
