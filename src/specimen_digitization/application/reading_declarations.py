"""Actual bounded declarations, independent of Unicode hints and clearance claims."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


OpaqueLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class DeclarationCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    language_candidates: tuple[OpaqueLabel, ...] = Field(
        default=(),
        max_length=8,
        description="Opaque declared language labels; empty when unknown. Not validated language codes.",
    )
    script_candidates: tuple[OpaqueLabel, ...] = Field(
        default=(),
        max_length=8,
        description="Opaque declared script labels; empty when unknown. Not Unicode-name hints.",
    )
    language_relation: Literal["unspecified", "cooccurring", "alternatives"] = (
        "unspecified"
    )

    @model_validator(mode="after")
    def relation_requires_candidates(self):
        if (
            self.language_relation != "unspecified"
            and len(set(self.language_candidates)) < 2
        ):
            raise ValueError(
                "Cooccurring or alternative languages require two distinct candidates"
            )
        if len(set(self.language_candidates)) != len(self.language_candidates) or len(
            set(self.script_candidates)
        ) != len(self.script_candidates):
            raise ValueError("Duplicate declaration candidates")
        return self


class LanguageHandling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["language-handling-v1"] = "language-handling-v1"
    unknown: Literal["unmeasured", "review"] = "unmeasured"
    mixed: Literal["unmeasured", "review"] = "review"
    conflicting: Literal["unmeasured", "review"] = "review"


def declaration_values(candidates, reference, method, producer, version, reason):
    from .reading_evidence import MetadataDeclaration

    return [
        MetadataDeclaration(
            kind=kind,
            value=value,
            method=method,
            producer=producer,
            version=version,
            evidence_ref=reference,
            locator=f"/candidates/{kind}_candidates/{index}",
            reason=reason,
        )
        for kind in ("language", "script")
        for index, value in enumerate(getattr(candidates, kind + "_candidates"))
    ]


def put_evidence(blobs, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return {"blob_ref": blobs.put(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def model_evidence(blobs, output, raw_ref, raw_sha256, model_id, prompt_version):
    candidates = DeclarationCandidates.model_validate(
        {
            key: getattr(output, key, default)
            for key, default in (
                ("language_candidates", ()),
                ("script_candidates", ()),
                ("language_relation", "unspecified"),
            )
        }
    )
    value = {
        "contract_version": "reading-declaration-v1",
        "method": "model_declared",
        "raw_ref": raw_ref,
        "raw_sha256": raw_sha256,
        "structured_output": output.model_dump(mode="json"),
        "candidates": candidates.model_dump(mode="json"),
        "producer": model_id,
        "version": prompt_version,
        "reason": "Actual structured model output; uncalibrated declaration",
    }
    metadata = put_evidence(blobs, value)
    return metadata


def checked_value(metadata, blobs):
    from .evidence_runtime import read_artifact

    return json.loads(read_artifact(metadata, blobs))


def effective_declarations(specimen, observation, blobs):
    result = []
    candidate_sources = []
    if observation.declaration_evidence:
        value = checked_value(observation.declaration_evidence, blobs)
        if (
            value["raw_ref"] != observation.raw_ref
            or value["raw_sha256"] != observation.raw_sha256
            or value["producer"] != observation.model_id
            or value["version"] != observation.prompt_version
            or value["structured_output"]["verbatim_text"] != observation.literal_text
            or value["method"] != "model_declared"
        ):
            raise ValueError("Model declaration provenance mismatch")
        candidates = DeclarationCandidates.model_validate(value["candidates"])
        for key in DeclarationCandidates.model_fields:
            if (
                value["structured_output"].get(
                    key, [] if key != "language_relation" else "unspecified"
                )
                != candidates.model_dump(mode="json")[key]
            ):
                raise ValueError("Declaration differs from actual structured output")
        result.extend(
            declaration_values(
                candidates,
                observation.declaration_evidence["blob_ref"],
                value["method"],
                value["producer"],
                value["version"],
                value["reason"],
            )
        )
        candidate_sources.append(candidates)
    human = [
        entry
        for entry in specimen.run.reading_declarations
        if entry["observation_id"] == observation.id
    ]
    if human:
        entry = human[-1]
        value = checked_value(entry, blobs)
        if (
            value["run_id"] != specimen.run.id
            or value["region_id"] != observation.region_id
            or value["observation_id"] != observation.id
            or value["raw_sha256"] != observation.raw_sha256
            or value["scope"] != specimen.scope.model_dump()
            or value["specimen_id"] != specimen.id
            or value["id"] != entry["id"]
            or value["method"] != "human_recorded"
        ):
            raise ValueError("Human declaration lineage mismatch")
        candidates = DeclarationCandidates.model_validate(value["candidates"])
        result.extend(
            declaration_values(
                candidates,
                entry["blob_ref"],
                "human_recorded",
                value["actor"],
                "human-reading-v1",
                value["reason"],
            )
        )
        candidate_sources.append(candidates)
    return tuple(result), candidate_sources


def record_human(specimen, observation, candidates, actor, reason, blobs):
    from .domain import now, uid

    previous = [
        entry
        for entry in specimen.run.reading_declarations
        if entry["observation_id"] == observation.id
    ]
    if len(previous) >= 32:
        raise ValueError("Human declaration history limit reached for this observation")
    value = {
        "contract_version": "reading-declaration-v1",
        "method": "human_recorded",
        "id": uid(),
        "scope": specimen.scope.model_dump(),
        "specimen_id": specimen.id,
        "run_id": specimen.run.id,
        "region_id": observation.region_id,
        "observation_id": observation.id,
        "raw_sha256": observation.raw_sha256,
        "actor": actor,
        "created_at": now(),
        "base_revision": specimen.version,
        "reason": reason,
        "candidates": candidates.model_dump(mode="json"),
        "supersedes": previous[-1]["id"] if previous else None,
    }
    specimen.run.reading_declarations.append(
        {
            **put_evidence(blobs, value),
            "id": value["id"],
            "observation_id": observation.id,
            "region_id": observation.region_id,
            "supersedes": value["supersedes"],
        }
    )


def label_handling(specimen, sources):
    policy = specimen.run.profile.language_handling
    labels = []
    for region in specimen.run.regions:
        groups = sources.get(region.id, [])
        languages = sorted(
            {value for group in groups for value in group.language_candidates}
        )
        scripts = sorted(
            {value for group in groups for value in group.script_candidates}
        )
        mixed = any(group.language_relation == "cooccurring" for group in groups)
        sets = {
            tuple(sorted(group.language_candidates))
            for group in groups
            if group.language_candidates
        }
        conflicting = len(sets) > 1 or any(
            group.language_relation == "alternatives"
            or (
                len(group.language_candidates) > 1
                and group.language_relation == "unspecified"
            )
            for group in groups
        )
        states = (
            (["unknown"] if not languages else [])
            + (["mixed"] if mixed else [])
            + (["conflicting"] if conflicting else [])
        )
        reasons = [
            "language_" + state + "_" + getattr(policy, state) for state in states
        ]
        labels.append(
            {
                "run_id": specimen.run.id,
                "region_id": region.id,
                "language_candidates": languages,
                "script_candidates": scripts,
                "mixed_declared": mixed,
                "conflicting_candidates": conflicting,
                "unmeasured": True,
                "policy_version": policy.version,
                "reasons": reasons,
                "review_required": any(
                    getattr(policy, state) == "review" for state in states
                ),
            }
        )
    return {
        "policy": policy.model_dump(),
        "labels": labels,
        "confidence": None,
        "vocabulary": "opaque_declared_labels",
    }
