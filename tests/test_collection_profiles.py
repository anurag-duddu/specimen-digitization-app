import pytest
from pydantic import ValidationError

from specimen_digitization.application.collection_profiles import (
    CollectionNode,
    CollectionProfileRegistry,
    ProfileMapping,
    insects_registry,
)


def test_registry_frozen_versioned_and_roundtrips():
    registry = insects_registry(synthetic=True)
    profile = registry.profiles[0]
    with pytest.raises(ValidationError):
        profile.version = "changed"
    assert (
        CollectionProfileRegistry.model_validate_json(registry.model_dump_json())
        == registry
    )
    assert registry.resolve("insects", profile.version).profile.digest == profile.digest
    assert registry.resolve("insects", "old").reason == "profile_version_not_active"
    with pytest.raises(ValidationError):
        CollectionProfileRegistry(
            version="v1", nodes=registry.nodes, profiles=(profile, profile), mappings=()
        )


def test_unknown_missing_ambiguous_draft_revoked_fail_closed():
    registry = insects_registry(synthetic=True)
    assert registry.resolve("other").reason == "unknown_collection"
    assert insects_registry().resolve("insects").reason == "profile_draft"
    for mappings, expected in [
        ((), "missing_mapping"),
        (registry.mappings * 2, "ambiguous_mapping"),
    ]:
        changed = registry.model_copy(update={"mappings": mappings})
        assert changed.resolve("insects").reason == expected
    revoked = registry.profiles[0].model_copy(update={"state": "revoked"})
    assert (
        registry.model_copy(update={"profiles": (revoked,)}).resolve("insects").reason
        == "profile_revoked"
    )


def test_hierarchy_cycle_rejected_and_opaque_mapping():
    with pytest.raises(ValidationError):
        CollectionProfileRegistry(
            version="v1",
            nodes=(
                CollectionNode(id="a", parent_id="b", name="A"),
                CollectionNode(id="b", parent_id="a", name="B"),
            ),
            profiles=(),
            mappings=(),
        )
    registry = insects_registry(synthetic=True)
    opaque = "tenant-collection-opaque"
    profile = registry.profiles[0].model_copy(update={"collection_id": opaque})
    configured = CollectionProfileRegistry(
        version="v2",
        nodes=(CollectionNode(id=opaque, name="Synthetic collection"),),
        profiles=(profile,),
        mappings=(
            ProfileMapping(
                collection_id=opaque,
                profile_id=profile.id,
                profile_version=profile.version,
            ),
        ),
    )
    assert configured.resolve(opaque).profile == profile
    assert configured.resolve("insects").status == "review"


def test_optional_codec_families_representable_without_default_activation():
    from specimen_digitization.application.collection_profiles import CollectionProfile

    original = insects_registry().profiles[0]
    assert original.allowed_input_formats == ("JPEG", "PNG")
    definition = original.model_dump()
    definition["allowed_input_formats"] = ("JPEG", "PNG", "HEIC", "DNG")
    configured = CollectionProfile.model_validate(definition)
    assert configured.allowed_input_formats == ("JPEG", "PNG", "HEIC", "DNG")
    assert configured.state == "draft"
    assert not configured.institutional_policy_approved
    assert not configured.semantics_confirmed
    assert (
        CollectionProfile.model_validate_json(configured.model_dump_json())
        == configured
    )
    definition["allowed_input_formats"] = ("RAW",)
    with pytest.raises(ValidationError):
        CollectionProfile.model_validate(definition)


# Exact draft bytes captured from reviewed effb708 before additive runtime fields.
LEGACY_PROFILE_JSON = '{"id":"zoology_insects","version":"0.1.0-draft","collection_id":"insects","state":"draft","synthetic":false,"schema_version":"insects-v1","mandatory_fields":["fmnh_ins_number","collection_code","country","province_state","county","city","precise_location","elevation_from_m","elevation_to_m","elevation_from_ft","elevation_to_ft","habitat","collection_method","date_visited_from","date_visited_to","collectors","verbatim_dts","taxon","identified_by_irn","date_identified"],"optional_fields":[],"not_applicable_fields":[],"prompt_set":"fmnh_insects_transcription_v1","model_routes":["handwriting-qwen","handwriting-muse"],"segmentation_policy":"sam3-v1","tools":["taxonomy_verifier"],"data_sources":["gbif-col-xr"],"validators":["insects-rules-v1"],"scoring_policy":"insects-review-risk-v1","clearance_policy":"insects-clearance-v1","allowed_input_formats":["JPEG","PNG"],"classification_confirmation_required":true,"institutional_policy_approved":false,"semantics_confirmed":false}'


def test_legacy_profile_bytes_and_hash_survive_additive_schema():
    from hashlib import sha256
    from specimen_digitization.application.collection_profiles import (
        CollectionProfile,
        resolve_profile_rules,
    )

    profile = CollectionProfile.model_validate_json(LEGACY_PROFILE_JSON)
    assert profile.model_dump_json() == LEGACY_PROFILE_JSON
    assert profile.digest == sha256(LEGACY_PROFILE_JSON.encode()).hexdigest()
    assert profile.language_handling.unknown == "unmeasured"
    assert (
        profile.language_handling.mixed
        == profile.language_handling.conflicting
        == "review"
    )
    assert profile.scoring_policy_ref is profile.segmentation_settings is None
    with pytest.raises(ValueError, match="scoring_policy_reference_missing"):
        resolve_profile_rules(profile)


def test_two_synthetic_profiles_pin_different_runtime_rules():
    from hashlib import sha256
    from specimen_digitization.application.collection_profiles import (
        CollectionProfile,
        LanguageHandlingRule,
        PolicyReference,
        SegmentationSettings,
        resolve_profile_rules,
    )

    balanced = PolicyReference(
        id="synthetic-balanced",
        version="1",
        digest=sha256(b"synthetic balanced rule fixture").hexdigest(),
    )
    numeral = PolicyReference(
        id="synthetic-numeral",
        version="1",
        digest=sha256(b"synthetic numeral rule fixture").hexdigest(),
    )
    base = insects_registry(synthetic=True).profiles[0].model_dump()
    first = CollectionProfile.model_validate(
        {
            **base,
            "language_handling": LanguageHandlingRule(unknown="unmeasured"),
            "scoring_policy_ref": balanced,
            "segmentation_settings": SegmentationSettings(prompt="label"),
        }
    )
    second = CollectionProfile.model_validate(
        {
            **base,
            "id": "synthetic_second",
            "version": "synthetic-v2",
            "collection_id": "synthetic-other",
            "language_handling": LanguageHandlingRule(
                unknown="review", mixed="unmeasured"
            ),
            "scoring_policy_ref": numeral,
            "segmentation_settings": SegmentationSettings(prompt="specimen label"),
        }
    )
    registry = CollectionProfileRegistry(
        version="runtime-fixtures-v1",
        nodes=(
            CollectionNode(id="insects", name="Synthetic A"),
            CollectionNode(id="synthetic-other", name="Synthetic B"),
        ),
        profiles=(first, second),
        mappings=(
            ProfileMapping(
                collection_id="insects",
                profile_id=first.id,
                profile_version=first.version,
            ),
            ProfileMapping(
                collection_id="synthetic-other",
                profile_id=second.id,
                profile_version=second.version,
            ),
        ),
    )
    first_rules = resolve_profile_rules(
        registry.resolve("insects").profile, (balanced, numeral)
    )
    second_rules = resolve_profile_rules(
        registry.resolve("synthetic-other").profile, (balanced, numeral)
    )
    assert first_rules.language_handling.unknown == "unmeasured"
    assert second_rules.language_handling.unknown == "review"
    assert first_rules.scoring_policy_ref != second_rules.scoring_policy_ref
    assert (
        first_rules.segmentation_settings.prompt
        != second_rules.segmentation_settings.prompt
    )
    assert first_rules.profile_digest != second_rules.profile_digest
    for profile in (first, second):
        reloaded = CollectionProfile.model_validate_json(profile.model_dump_json())
        assert reloaded == profile and reloaded.digest == profile.digest
        assert (
            not profile.institutional_policy_approved
            and not profile.semantics_confirmed
        )
        with pytest.raises(ValidationError):
            profile.language_handling.unknown = "review"
        with pytest.raises(ValidationError):
            profile.segmentation_settings.prompt = "modified"


def test_runtime_rules_reject_unknown_versions_missing_and_mismatched_refs():
    from hashlib import sha256
    from specimen_digitization.application.collection_profiles import (
        CollectionProfile,
        PolicyReference,
        SegmentationSettings,
        resolve_profile_rules,
    )

    base = insects_registry(synthetic=True).profiles[0].model_dump()
    reference = PolicyReference(
        id="synthetic-rule", version="1", digest=sha256(b"fixture").hexdigest()
    )
    defined = {
        **base,
        "language_handling": {"version": "language-handling-v1"},
        "scoring_policy_ref": reference,
        "segmentation_settings": SegmentationSettings(prompt="label"),
    }
    for key, value in (
        ("language_handling", {"version": "unknown"}),
        ("segmentation_settings", {"version": "unknown", "prompt": "label"}),
        (
            "segmentation_settings",
            {"prompt": "label", "parameters": {"confidence": 0.9}},
        ),
        ("segmentation_settings", {"prompt": "label", "model_revision": "unreviewed"}),
    ):
        with pytest.raises(ValidationError):
            CollectionProfile.model_validate({**defined, key: value})
    profile = CollectionProfile.model_validate(defined)
    for candidates in (
        (),
        (reference.model_copy(update={"version": "2"}),),
        (reference.model_copy(update={"digest": sha256(b"different").hexdigest()}),),
        (reference, reference),
    ):
        with pytest.raises(ValueError, match="scoring_policy_reference_unresolved"):
            resolve_profile_rules(profile, candidates)
    missing = CollectionProfile.model_validate(
        {**defined, "segmentation_settings": None}
    )
    with pytest.raises(ValueError, match="segmentation_settings_missing"):
        resolve_profile_rules(missing, (reference,))


def test_synthetic_factory_has_explicit_versioned_runtime_rules():
    from specimen_digitization.application.collection_profiles import (
        SYNTHETIC_SCORING_POLICY,
        resolve_profile_rules,
    )

    profile = insects_registry(synthetic=True).profiles[0]
    assert profile.version == "synthetic-v2-runtime-rules"
    rules = resolve_profile_rules(profile, (SYNTHETIC_SCORING_POLICY,))
    assert rules.scoring_policy_ref.id == "synthetic-review-risk-balanced"
    assert rules.segmentation_settings.prompt == "label"
    assert rules.language_handling.mixed == "review"


def test_new_runtime_requires_explicit_language_pin():
    from specimen_digitization.application.collection_profiles import (
        CollectionProfile,
        SYNTHETIC_SCORING_POLICY,
        resolve_profile_rules,
    )

    definition = insects_registry(synthetic=True).profiles[0].model_dump()
    definition.pop("language_handling")
    profile = CollectionProfile.model_validate(definition)
    assert profile.language_handling.version == "language-handling-v1"
    with pytest.raises(ValueError, match="language_handling_rule_missing"):
        resolve_profile_rules(profile, (SYNTHETIC_SCORING_POLICY,))
