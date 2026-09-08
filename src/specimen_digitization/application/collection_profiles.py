"""Immutable profile snapshots and explicit mappings; authorization belongs to API."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from .domain import MANDATORY


class FrozenRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class CollectionNode(FrozenRecord):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    name: str = Field(min_length=1)


class LanguageHandlingRule(FrozenRecord):
    version: Literal["language-handling-v1"] = "language-handling-v1"
    unknown: Literal["unmeasured", "review"] = "unmeasured"
    mixed: Literal["unmeasured", "review"] = "review"
    conflicting: Literal["unmeasured", "review"] = "review"


class PolicyReference(FrozenRecord):
    id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Sam3Parameters(FrozenRecord):
    """The current HTTP contract supports no extra parameter knobs."""


class SegmentationSettings(FrozenRecord):
    version: Literal["sam3-settings-v1"] = "sam3-settings-v1"
    adapter_version: Literal["sam3-http-v1"] = "sam3-http-v1"
    model_id: Literal["facebook/sam3"] = "facebook/sam3"
    model_revision: Literal["3c879f39826c281e95690f02c7821c4de09afae7"] = (
        "3c879f39826c281e95690f02c7821c4de09afae7"  # pragma: allowlist secret
    )
    prompt: str = Field(min_length=1, max_length=1000)
    parameters: Sam3Parameters = Field(default_factory=Sam3Parameters)


class CollectionProfile(FrozenRecord):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    collection_id: str = Field(min_length=1)
    state: Literal[
        "draft", "testing", "approved", "active", "deprecated", "revoked"
    ] = "draft"
    synthetic: bool = False
    schema_version: str = Field(min_length=1)
    mandatory_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    not_applicable_fields: tuple[str, ...] = ()
    prompt_set: str = Field(min_length=1)
    model_routes: tuple[str, ...]
    segmentation_policy: str = Field(min_length=1)
    tools: tuple[str, ...]
    data_sources: tuple[str, ...]
    validators: tuple[str, ...]
    scoring_policy: str = Field(min_length=1)
    clearance_policy: str = Field(min_length=1)
    allowed_input_formats: tuple[Literal["JPEG", "PNG", "TIFF", "HEIC", "DNG"], ...] = (
        "JPEG",
        "PNG",
    )
    classification_confirmation_required: bool = True
    institutional_policy_approved: bool = False
    semantics_confirmed: bool = False

    language_handling: LanguageHandlingRule = Field(
        default_factory=LanguageHandlingRule
    )
    scoring_policy_ref: PolicyReference | None = None
    segmentation_settings: SegmentationSettings | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_serialization(self, handler):
        value = handler(self)
        # Historical definitions predate these fields. Do not change their bytes
        # or digest merely by loading them through the additive schema.
        for key in ("language_handling", "scoring_policy_ref", "segmentation_settings"):
            if key not in self.model_fields_set:
                value.pop(key, None)
        return value

    @property
    def digest(self) -> str:
        return sha256(self.model_dump_json().encode()).hexdigest()

    @model_validator(mode="after")
    def validate_fields(self):
        fields = (
            self.mandatory_fields + self.optional_fields + self.not_applicable_fields
        )
        if len(fields) != len(set(fields)) or any(not f.strip() for f in fields):
            raise ValueError("field groups must be nonblank and disjoint")
        if len(set(self.model_routes)) < 2:
            raise ValueError("two independent model routes required")
        return self


class ResolvedProfileRules(FrozenRecord):
    profile_id: str
    profile_version: str
    profile_digest: str
    language_handling: LanguageHandlingRule
    scoring_policy_ref: PolicyReference
    segmentation_settings: SegmentationSettings


def resolve_profile_rules(
    profile: CollectionProfile,
    supported_scoring_policies: tuple[PolicyReference, ...] = (),
) -> ResolvedProfileRules:
    """Runtime boundary, separate from legacy history loading and node selection.

    The caller supplies only references resolved by its approved policy registry;
    this module does not approve policy contents or silently instantiate scoring.
    """
    if profile.scoring_policy_ref is None:
        raise ValueError("scoring_policy_reference_missing")
    matches = [
        reference
        for reference in supported_scoring_policies
        if (reference.id, reference.version)
        == (profile.scoring_policy_ref.id, profile.scoring_policy_ref.version)
    ]
    if len(matches) != 1 or matches[0].digest != profile.scoring_policy_ref.digest:
        raise ValueError("scoring_policy_reference_unresolved")
    if "language_handling" not in profile.model_fields_set:
        raise ValueError("language_handling_rule_missing")
    if profile.segmentation_settings is None:
        raise ValueError("segmentation_settings_missing")
    # Revalidate nested objects as model_copy is not a validation boundary.
    language = LanguageHandlingRule.model_validate(
        profile.language_handling.model_dump()
    )
    segmentation = SegmentationSettings.model_validate(
        profile.segmentation_settings.model_dump()
    )
    return ResolvedProfileRules(
        profile_id=profile.id,
        profile_version=profile.version,
        profile_digest=profile.digest,
        language_handling=language,
        scoring_policy_ref=profile.scoring_policy_ref,
        segmentation_settings=segmentation,
    )


class ProfileMapping(FrozenRecord):
    collection_id: str
    profile_id: str
    profile_version: str


class ProfileResolution(FrozenRecord):
    status: Literal["selected", "review"]
    reason: str
    profile: CollectionProfile | None = None


class CollectionProfileRegistry(FrozenRecord):
    version: str = Field(min_length=1)
    nodes: tuple[CollectionNode, ...]
    profiles: tuple[CollectionProfile, ...]
    mappings: tuple[ProfileMapping, ...]

    @model_validator(mode="after")
    def validate_registry(self):
        nodes = {n.id: n for n in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("duplicate collection node")
        for node in self.nodes:
            seen = {node.id}
            parent = node.parent_id
            while parent is not None:
                if parent not in nodes or parent in seen:
                    raise ValueError("missing parent or cyclic hierarchy")
                seen.add(parent)
                parent = nodes[parent].parent_id
        keys = [(p.id, p.version) for p in self.profiles]
        if len(keys) != len(set(keys)):
            raise ValueError("published profile version cannot be replaced")
        if any(p.collection_id not in nodes for p in self.profiles):
            raise ValueError("profile collection missing")
        return self

    def resolve(
        self, collection_id: str, profile_version: str | None = None
    ) -> ProfileResolution:
        def review(reason):
            return ProfileResolution(status="review", reason=reason)

        if collection_id not in {n.id for n in self.nodes}:
            return review("unknown_collection")
        mappings = [m for m in self.mappings if m.collection_id == collection_id]
        if len(mappings) != 1:
            return review("missing_mapping" if not mappings else "ambiguous_mapping")
        mapping = mappings[0]
        if profile_version is not None and profile_version != mapping.profile_version:
            return review("profile_version_not_active")
        profiles = [
            p
            for p in self.profiles
            if (p.id, p.version) == (mapping.profile_id, mapping.profile_version)
        ]
        if not profiles or profiles[0].collection_id != collection_id:
            return review("missing_or_mismatched_profile")
        profile = profiles[0]
        if profile.state != "active":
            return review("profile_" + profile.state)
        return ProfileResolution(
            status="selected", reason="explicit_versioned_mapping", profile=profile
        )


# Reference generated by the evidence owner's synthetic_risk_policies() factory.
# No production scoring policy or calibration is implied.
SYNTHETIC_SCORING_POLICY = PolicyReference(
    id="synthetic-review-risk-balanced",
    version="1",
    digest="1e625be1a707fbba6cbda12e587d7442108c974dce69cb4120393fff26ef2138",  # pragma: allowlist secret
)


def insects_registry(*, synthetic: bool = False) -> CollectionProfileRegistry:
    """Draft institutional policy is never silently published by this factory."""
    runtime_rules = (
        {
            "language_handling": LanguageHandlingRule(),
            "scoring_policy_ref": SYNTHETIC_SCORING_POLICY,
            "segmentation_settings": SegmentationSettings(prompt="label"),
        }
        if synthetic
        else {}
    )
    profile = CollectionProfile(
        id="zoology_insects",
        version="synthetic-v2-runtime-rules" if synthetic else "0.1.0-draft",
        collection_id="insects",
        state="active" if synthetic else "draft",
        synthetic=synthetic,
        schema_version="insects-v1",
        mandatory_fields=MANDATORY,
        prompt_set="fmnh_insects_transcription_v1",
        model_routes=("handwriting-qwen", "handwriting-muse"),
        segmentation_policy="sam3-v1",
        tools=("taxonomy_verifier",),
        data_sources=("gbif-col-xr",),
        validators=("insects-rules-v1",),
        scoring_policy="insects-review-risk-v1",
        clearance_policy="insects-clearance-v1",
        **runtime_rules,
    )
    return CollectionProfileRegistry(
        version="insects-registry-v1",
        nodes=(CollectionNode(id="insects", name="Insects"),),
        profiles=(profile,),
        mappings=(
            ProfileMapping(
                collection_id="insects",
                profile_id=profile.id,
                profile_version=profile.version,
            ),
        ),
    )
