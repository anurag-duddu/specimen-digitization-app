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
    assert registry.resolve("insects", "synthetic-v1").profile.digest == profile.digest
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
