import pytest

from specimen_digitization.application.review_risk import (
    Reading,
    RiskPolicy,
    RiskSignal,
    RiskWeight,
    compare_readings,
    review_risk,
)


def test_minority_numeral_span_line_and_script_uncertainty_are_retained():
    left = Reading(
        observation_id="a", region_id="r", text="Illinois\n1900", language="en"
    )
    right = Reading(
        observation_id="b", region_id="r", text="Illinois\n1908", language="en"
    )
    difference = compare_readings(left, right)
    span = difference.differences[0]
    assert left.text[slice(*span.left_span)] == "0"
    assert right.text[slice(*span.right_span)] == "8"
    assert span.contains_numeral and span.evidence_ids == ("a", "b")
    assert difference.differing_lines == (2,)
    assert set(difference.reasons) == {
        "literal_disagreement",
        "numeral_disagreement",
        "script_unconfirmed",
    }
    assert compare_readings(left, right) == difference


def test_risk_explains_inputs_and_cannot_override_validation_or_disposition():
    signals = (
        RiskSignal(code="hard_validation", count=1, evidence_ids=("validation-1",)),
        RiskSignal(
            code="numeral_disagreement", count=1, evidence_ids=("obs-a", "obs-b")
        ),
    )
    result = review_risk(signals)
    assert result.composite == 45 and result.components[0].contribution == 25
    assert result.calibrated is False and result.calibration_dataset_version is None
    assert "disposition" not in result.model_dump()
    zero = review_risk(
        signals, RiskPolicy(weights=(RiskWeight(code="hard_validation", weight=0),))
    )
    assert zero.composite == 0 and "hard_validation" in zero.reasons
    assert "unweighted_signal" in zero.reasons
    with pytest.raises(ValueError):
        review_risk((signals[0], signals[0]))


def risk_fixture():
    from specimen_digitization.application.review_risk import synthetic_risk_policies
    from specimen_digitization.application.reading_evidence import (
        MetadataDeclaration,
        ReadingEvidenceInput,
        align_readings,
        summarize_reading,
    )

    declarations = tuple(
        MetadataDeclaration(
            kind=kind,
            value=value,
            method="model_declared",
            producer="synthetic-model",
            version="1",
            evidence_ref="immutable:declaration",
            locator=kind,
            reason="Explicit synthetic fixture",
        )
        for kind, value in (("language", "en"), ("script", "Latn"))
    )
    readings = tuple(
        ReadingEvidenceInput(
            observation_id=identity,
            region_id="region-1",
            source_ref="immutable:" + identity,
            text=text,
            declarations=declarations,
        )
        for identity, text in (("left", "é😀1900"), ("right", "é😀1908"))
    )
    registry = synthetic_risk_policies()
    return (
        registry,
        readings,
        (align_readings(*readings),),
        tuple(summarize_reading(r) for r in readings),
    )


def test_two_published_synthetic_policies_produce_explainable_label_scores():
    from specimen_digitization.application.review_risk import label_review_risk

    registry, readings, alignments, metadata = risk_fixture()
    results = tuple(
        label_review_risk(
            "region-1",
            ("left", "right"),
            alignments,
            metadata,
            registry.resolve(entry.policy.reference, allow_synthetic=True),
        )
        for entry in registry.entries
    )
    assert [r.composite for r in results] == [40, 60]
    assert all(r.scope == "label" and r.status == "scored" for r in results)
    assert results[0].policy_reference != results[1].policy_reference
    assert results[0].input_sha256 != results[1].input_sha256
    assert [c.weight for c in results[0].components] == [20, 20]
    assert [c.weight for c in results[1].components] == [20, 40]
    for result in results:
        assert set(result.reasons) == {
            "unresolved_disagreement",
            "numeral_disagreement",
        }
        assert all(
            c.signal.evidence_ids == ("left", "right") for c in result.components
        )
        assert result.calibrated is False and result.clearance_authority is False
        assert "disposition" not in result.model_dump()


def test_missing_unknown_version_digest_draft_revoked_and_synthetic_policy_fail_closed():
    from specimen_digitization.application.review_risk import (
        RiskPolicyRegistry,
        RiskPolicyEntry,
        assess_risk,
    )

    registry, *_ = risk_fixture()
    reference = registry.entries[0].policy.reference
    failures = [
        registry.resolve(None),
        registry.resolve(reference),
        registry.resolve(
            reference.model_copy(update={"id": "missing"}), allow_synthetic=True
        ),
        registry.resolve(
            reference.model_copy(update={"version": "missing"}), allow_synthetic=True
        ),
        registry.resolve(
            reference.model_copy(update={"digest": "0" * 64}), allow_synthetic=True
        ),
    ]
    for status in ("draft", "revoked"):
        alternative = RiskPolicyRegistry(
            version="changed",
            entries=(
                RiskPolicyEntry(policy=registry.entries[0].policy, status=status),
            ),
        )
        failures.append(alternative.resolve(reference, allow_synthetic=True))
    for resolution in failures:
        assert resolution.status == "blocked" and resolution.policy is None
        result = assess_risk((), resolution, scope="specimen", target_id="specimen-1")
        assert result.status == "blocked" and result.composite is None
        assert resolution.reason in result.reasons


def test_pinned_policy_is_immutable_and_same_version_redefinition_rejected():
    from pydantic import ValidationError
    from specimen_digitization.application.review_risk import (
        RiskPolicyRegistry,
        RiskPolicyEntry,
        RiskPolicyResolution,
    )

    registry, *_ = risk_fixture()
    policy = registry.entries[0].policy
    reference = policy.reference
    with pytest.raises(ValidationError):
        policy.weights = ()
    changed = policy.model_copy(update={"weights": ()})
    with pytest.raises(ValidationError):
        RiskPolicyRegistry(
            version="bad", entries=(*registry.entries, RiskPolicyEntry(policy=changed))
        )
    redefined = RiskPolicyRegistry(
        version="2", entries=(RiskPolicyEntry(policy=changed, status="published"),)
    )
    assert (
        redefined.resolve(reference, allow_synthetic=True).reason
        == "risk_policy_digest_mismatch"
    )
    resolution = registry.resolve(reference, allow_synthetic=True)
    assert (
        RiskPolicyResolution.model_validate_json(resolution.model_dump_json())
        == resolution
    )
    with pytest.raises(ValidationError):
        RiskPolicyResolution(
            status="resolved",
            reference=reference,
            registry_version="1",
            reason="test",
            policy=changed,
        )


def test_label_missing_comparisons_metadata_and_quality_are_unmeasured_not_zero():
    from specimen_digitization.application.review_risk import label_review_risk

    registry, readings, alignments, metadata = risk_fixture()
    resolution = registry.resolve(
        registry.entries[0].policy.reference, allow_synthetic=True
    )
    missing_pair = label_review_risk(
        "region-1", ("left", "right", "third"), alignments, metadata, resolution
    )
    assert missing_pair.status == "unmeasured" and missing_pair.composite is None
    assert "reading_comparisons" in missing_pair.unmeasured
    partial = label_review_risk(
        "region-1",
        ("left", "right"),
        alignments,
        metadata[:1],
        resolution,
        unmeasured=("image_quality",),
    )
    assert partial.status == "unmeasured" and partial.composite is None
    assert set(partial.unmeasured) == {"language", "script", "image_quality"}
    assert len(partial.components) == 2
    absent = label_review_risk("region-1", (), (), (), resolution)
    assert absent.composite is None and "reading_comparisons" in absent.unmeasured


def test_unicode_long_blocked_label_never_reports_agreement_or_zero_risk():
    from specimen_digitization.application.review_risk import label_review_risk
    from specimen_digitization.application.reading_evidence import (
        align_readings,
        summarize_reading,
    )

    registry, readings, _, _ = risk_fixture()
    resolution = registry.resolve(
        registry.entries[0].policy.reference, allow_synthetic=True
    )
    long = tuple(r.model_copy(update={"text": "😀" * 100001}) for r in readings)
    blocked = align_readings(*long)
    result = label_review_risk(
        "region-1",
        ("left", "right"),
        (blocked,),
        tuple(summarize_reading(r) for r in long),
        resolution,
    )
    assert result.status == "blocked" and result.composite is None
    assert (
        "reading_codepoint_limit" in result.reasons
        and "reading_disagreement" in result.unmeasured
    )
    assert result.components[0].signal.code == "operational_block"


def test_field_specimen_assessments_keep_hard_reasons_even_with_zero_weights():
    from specimen_digitization.application.review_risk import (
        RiskPolicyRegistry,
        RiskPolicyEntry,
        assess_risk,
    )

    policy = RiskPolicy(
        id="synthetic-zero",
        version="1",
        synthetic=True,
        weights=(RiskWeight(code="hard_validation", weight=0),),
    )
    resolution = RiskPolicyRegistry(
        version="1", entries=(RiskPolicyEntry(policy=policy, status="published"),)
    ).resolve(policy.reference, allow_synthetic=True)
    signals = (
        RiskSignal(
            code="hard_validation",
            count=1,
            field_key="taxon",
            evidence_ids=("validation-1",),
        ),
    )
    for scope in ("field", "specimen"):
        result = assess_risk(signals, resolution, scope=scope, target_id="target-1")
        assert result.composite == 0 and "hard_validation" in result.reasons
        assert (
            result.clearance_authority is False
            and result.policy_reference == policy.reference
        )
    unknown = assess_risk(
        (RiskSignal(code="not_in_policy", count=1, evidence_ids=("e",)),),
        resolution,
        scope="field",
        target_id="taxon",
    )
    assert unknown.status == "unmeasured" and unknown.composite is None
    assert unknown.unmeasured == ("weight:not_in_policy",)


def test_label_rejects_wrong_regions_duplicate_pairs_and_metadata_versions():
    from specimen_digitization.application.review_risk import label_review_risk

    registry, readings, alignments, metadata = risk_fixture()
    resolution = registry.resolve(
        registry.entries[0].policy.reference, allow_synthetic=True
    )
    with pytest.raises(ValueError):
        label_review_risk(
            "other-region", ("left", "right"), alignments, metadata, resolution
        )
    with pytest.raises(ValueError):
        label_review_risk(
            "region-1", ("left", "right"), alignments * 2, metadata, resolution
        )
    with pytest.raises(ValueError):
        label_review_risk(
            "region-1", ("left", "left"), alignments, metadata, resolution
        )
    with pytest.raises(ValueError):
        label_review_risk(
            "region-1", ("left", "right"), alignments, metadata * 2, resolution
        )
