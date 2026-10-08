"""Synthetic ecological/measurement lines preserve their separate exact spans."""

import asyncio
import hashlib
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness.collection import collection_resolution
from specimen_digitization.research_harness.contracts import FieldKey, WorkState
from specimen_digitization.research_harness.evidence import validate_resolution

from test_collection_qualification import collection_request, retained, undecided


def current_graph(built):
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    built.graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope,
        collection_recovery=True, collection_original_reading=True)
    return built


@pytest.mark.parametrize("quantity", ("6400'", "6,400 ft", "100 m", "100 to 120 m"))
def test_ecological_prefix_keeps_its_quote_and_excludes_written_elevation(quantity):
    text = "Mossy forest " + quantity
    built = current_graph(undecided(retained(text, claimed_key="habitat", claimed_literal="Mossy forest")))
    request = collection_request(built)
    before = request.model_dump_json()
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.literal == result.value.parsed == result.value.normalized == "Mossy forest"
    assert set(result.value.verbatim_by_observation.values()) == {text}
    assert set(result.evidence_ids) <= {row.id for row in built.specimen.run.evidence}
    assert result.evidence_ids
    assembly = next(row for row in request.assemblies if row.id in result.assembly_ids)
    fragment = next(row for row in request.fragments if row.id in assembly.fragment_ids)
    assert fragment.observation_text[fragment.start:fragment.end] == "Mossy forest"
    assert request.model_dump_json() == before
    assert validate_resolution(request, result) == result


@pytest.mark.parametrize("suffix", (
    "6400", "6400''", "6400 ft extra", "6400 mt", "6,40 ft", "120 to 100 m",
    "unknown", "light trap", "6400' +/- 1 m", "6400'6401'",
))
def test_unsupported_remainder_does_not_disappear_from_collection_recovery(suffix):
    built = current_graph(undecided(retained("Mossy forest " + suffix)))
    result = collection_resolution(collection_request(built), FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert not result.evidence_ids and not result.assembly_ids
    assert result.value.parsed is None


@pytest.mark.parametrize("other", ("Wet forest 6400'", "6400'", ""))
def test_ecological_recovery_requires_the_other_retained_reader(other):
    built = current_graph(undecided(retained("Mossy forest 6400'", raw=other)))
    result = collection_resolution(collection_request(built), FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert not result.evidence_ids and not result.assembly_ids


def test_ecological_prefix_needs_native_quote_and_never_overrides_another_field_marker():
    for text, native in (("Mossy forest 6400'", False), ("Locality: Mossy forest 6400'", True)):
        result = collection_resolution(collection_request(current_graph(retained(text, native_quote=native))), FieldKey.HABITAT)
        assert result.work_state == WorkState.WAITING_POLICY
        assert not result.evidence_ids and not result.assembly_ids


@pytest.mark.parametrize("version", (
    "collection-qualified-evidence-v6-2026-10-07", "collection-original-reading-v7-2026-10-08",
))
def test_native_factory_keeps_collection_recovery_for_both_qualified_prompt_versions(version, monkeypatch):
    from specimen_digitization.application.domain import Principal
    from specimen_digitization.application.storage import digest as canonical_digest
    from specimen_digitization.research_harness.contracts import SpecialistRole, digest
    from specimen_digitization.research_harness.evidence import insects_profile
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    from specimen_digitization.research_harness.prompts import resolve_prompt
    from specimen_digitization.research_harness.sources import SourceRegistry
    from test_utility_original_reading_output import retained_text

    built = undecided(retained("Mossy forest 6400'"))
    original = built.specimen
    original.asset.sensitive = False
    profile = insects_profile(original.scope.organization_id, original.scope.collection_id)
    original.run.profile_snapshot = profile.model_dump(mode="json")
    registry = SourceRegistry(())
    scope = built.scope.model_copy(update={"profile_digest": digest(profile)})
    pins = {str(role): resolve_prompt(role, profile_digest=digest(profile),
        source_registry_digest=registry.digest, toolset_digest="a" * 64, model_route="harness-deepseek",
        output_schema_digest="b" * 64).model_dump(mode="json") for role in SpecialistRole}
    text = retained_text(SpecialistRole.COLLECTION, 6 if "v6" in version else 7)
    pins[str(SpecialistRole.COLLECTION)].update(version=version, text=text,
        digest=hashlib.sha256(text.encode()).hexdigest())
    snapshot = {"fixture": "offline original snapshot"}
    canonical = SimpleNamespace(specimen_id=original.id, sensitive=False)
    binding = SimpleNamespace(canonical=canonical, program_key="offline-program", source_sha256=original.asset.sha256,
        base_canonical=SimpleNamespace(record_revision=original.version, snapshot_sha256=canonical_digest(snapshot),
            canonical_run_id=original.run.id), canonical_profile_digest=canonical_digest(original.run.profile_snapshot),
        profile_digest=digest(profile), validate_job=lambda *args, **kwargs: None, research_scope=lambda: scope)
    job = {"pins": {"profile": profile.model_dump(mode="json"), "sources": {"registry_digest": registry.digest},
        "prompts": pins}, "fields": {str(key): {"revision": 0} for key in FieldKey}}
    repository = SimpleNamespace(graph_blobs=None, variables=lambda value: {},
        execute=lambda *args: {"specimenSnapshot": {"snapshot": snapshot, "sha256": canonical_digest(snapshot)}})
    monkeypatch.setattr("specimen_digitization.research_harness.initial_requests.unpack", lambda *args: original)

    async def access(*args):
        return None

    requests = asyncio.run(NativeGenerationRequestFactory(repository, verify_access=access, registry=registry)(
        Principal(user_id="offline-fixture", scope=original.scope, role="operator"), binding, job))
    result = collection_resolution(requests[SpecialistRole.COLLECTION], FieldKey.HABITAT)
    if "v6" in version:
        assert result.work_state == WorkState.WAITING_POLICY
        assert not [row for row in requests[SpecialistRole.COLLECTION].assemblies if row.field_key == FieldKey.HABITAT]
        assert not result.evidence_ids and not result.assembly_ids
    else:
        assert result.work_state == WorkState.RESOLVED
        assert result.value.literal == "Mossy forest"
        assert set(result.value.verbatim_by_observation.values()) == {"Mossy forest 6400'"}


@pytest.mark.parametrize("text", ("Mossy forest", "Mossy forest 6400'", "oak woodland 100 m"))
def test_retained_v7_acceptance_keeps_v6_ecology_policy_and_original_request(text, monkeypatch):
    from specimen_digitization.research_harness.accepted_output import AcceptedOutputProofV1, validation_boundary_pins
    from specimen_digitization.research_harness.contracts import SpecialistRole, SpecialistRequest, digest
    from specimen_digitization.research_harness.prompts import (
        COLLECTION_EVIDENCE_PROMPT_VERSION, COLLECTION_PROVENANCE_PROMPT_VERSION,
    )
    from test_utility_original_reading_output import retained_text

    literal = "oak woodland" if text.startswith("oak") else "Mossy forest"
    # Reconstruct the historical synthetic graph with its original event version.
    with monkeypatch.context() as patch:
        patch.setattr("specimen_digitization.research_harness.initial_requests.ORGANISER_RULE", "organiser-verbatim-span/v6")
        built = undecided(retained(text, claimed_key="habitat", claimed_literal=literal))
    request = collection_request(built)
    old_text = retained_text(SpecialistRole.COLLECTION, 6)
    request = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.HABITAT,), "field_revisions": {FieldKey.HABITAT: 0},
        "prompt": {**request.prompt.model_dump(mode="json"), "version": COLLECTION_EVIDENCE_PROMPT_VERSION,
            "text": old_text, "digest": hashlib.sha256(old_text.encode()).hexdigest()}})
    original = request.model_dump_json()
    old = collection_resolution(request, FieldKey.HABITAT)
    assert old.work_state == WorkState.WAITING_POLICY
    assert validate_resolution(request, old) == old
    proof = AcceptedOutputProofV1(original_request=request,
        native_run_id="00000000-0000-0000-0000-000000000001", conversation_id="offline-retained-ecology",
        resolutions=(old,), source_results=(), effect_ids=(), model_settings_digest=digest("synthetic settings"),
        validator_version="validate_resolution/v7",
        validator_source_sha256="c6d758fd18566a6941bdb3be07af4d5baaf5cd9d16111c1806409a3c179c9fc1",  # pragma: allowlist secret
        **validation_boundary_pins())
    retained_proof = proof.model_dump_json()
    assert AcceptedOutputProofV1.model_validate_json(retained_proof) == proof

    original_specimen = built.specimen.model_dump_json()
    fresh = collection_request(current_graph(built))
    new = SpecialistRequest.model_validate({**fresh.model_dump(mode="json"),
        "field_keys": (FieldKey.HABITAT,), "field_revisions": {FieldKey.HABITAT: 0}})
    assert new.prompt.version == COLLECTION_PROVENANCE_PROMPT_VERSION
    assert {row.observation_id: row.observation_text for row in new.fragments} == {
        row.observation_id: row.observation_text for row in request.fragments}
    assert built.specimen.model_dump_json() == original_specimen
    current = collection_resolution(new, FieldKey.HABITAT)
    assert current.work_state == WorkState.RESOLVED and current.value.literal == literal
    assert set(current.value.verbatim_by_observation.values()) == {text}
    assert validate_resolution(new, current) == current
    with pytest.raises(ValueError):
        AcceptedOutputProofV1.model_validate({**proof.model_dump(mode="json"),
            "resolutions": (current.model_dump(mode="json"),)})
    assert request.model_dump_json() == original
    assert proof.model_dump_json() == retained_proof
    assert AcceptedOutputProofV1.model_validate_json(retained_proof) == proof
