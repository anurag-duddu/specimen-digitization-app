from hashlib import sha256
import random
import tracemalloc

import pytest
from pydantic import ValidationError

from specimen_digitization.application.reading_evidence import (
    MetadataDeclaration,
    ReadingEvidenceInput,
    ReadingLimits,
    align_readings,
    reading_risk_evidence,
    summarize_reading,
)


def reading(text, observation="left", **kwargs):
    return ReadingEvidenceInput(
        observation_id=observation,
        region_id="region-1",
        source_ref="immutable:" + observation,
        text=text,
        **kwargs,
    )


def declaration(kind="language", value="en", **changes):
    values = dict(
        kind=kind,
        value=value,
        method="model_declared",
        producer="synthetic-model",
        version="fixture-1",
        evidence_ref="immutable:response",
        locator="output.language",
        reason="Explicit fixture declaration",
    )
    values.update(changes)
    return MetadataDeclaration(**values)


def assert_raw_spans(left, right, result):
    rebuilt = []
    cursor = 0
    for alternative in result.alternatives:
        for source, span in (
            (left.text, alternative.left),
            (right.text, alternative.right),
        ):
            assert source[span.start.codepoint : span.end.codepoint] == span.text
            assert (
                source.encode("utf-8")[
                    span.start.utf8_byte : span.end.utf8_byte
                ].decode("utf-8")
                == span.text
            )
            assert (
                source.encode("utf-16-le")[
                    2 * span.start.utf16_codeunit : 2 * span.end.utf16_codeunit
                ].decode("utf-16-le")
                == span.text
            )
        rebuilt.append(left.text[cursor : alternative.left.start.codepoint])
        rebuilt.append(alternative.right.text)
        cursor = alternative.left.end.codepoint
    rebuilt.append(left.text[cursor:])
    assert "".join(rebuilt) == right.text


def test_unknown_metadata_never_inferred_from_latin_letters():
    metadata = summarize_reading(reading("Illinois 1900"))
    assert metadata.language_state == metadata.script_state == "unknown"
    assert metadata.declarations == ()
    assert metadata.script_hints[0].unicode_name_prefix == "LATIN"
    assert "not_script_classification" in metadata.script_hints[0].method
    assert metadata.reference.text_sha256 == sha256(b"Illinois 1900").hexdigest()


def test_multiple_languages_scripts_and_reported_confidence_remain_claims():
    declarations = (
        declaration(),
        declaration(value="es", method="classifier_declared", reported_confidence=0.4),
        declaration("script", "Latn"),
        declaration("script", "Arab"),
    )
    value = reading("México العربية", declarations=declarations)
    metadata = summarize_reading(value)
    assert metadata.language_state == metadata.script_state == "multiple_candidates"
    assert metadata.declarations == declarations
    assert metadata.declarations[0].reported_confidence is None
    assert metadata.declarations[1].reported_confidence == 0.4
    assert {h.unicode_name_prefix for h in metadata.script_hints} == {"LATIN", "ARABIC"}
    with pytest.raises(ValidationError):
        declaration(value=None, reported_confidence=0.9)
    with pytest.raises(ValidationError):
        declarations[0].value = "fr"


@pytest.mark.parametrize(
    "a,b",
    [
        ("México ١٩٠٠", "México ١٩٠٨"),
        ("東京\n昆虫", "東京\n昆蟲"),
        ("Αθήνα Москва", "Αθήνα Мосκва"),
        ("😀a\r\nb", "😀a\r\nc"),
        ("e\u0301 1900", "é 1900"),
        ("A\u200d👩‍🔬Z", "A\u200d👩‍💻Z"),
        ("first\r\nsecond", "first\nsecond"),
        ("ab", "aXXb"),
        ("aXXb", "ab"),
        ("A\u2028B", "A\u2028C"),
        ("a b", "a  b"),
    ],
)
def test_unicode_line_span_and_raw_offset_reconstruction(a, b):
    left, right = reading(a), reading(b, "right")
    result = align_readings(left, right)
    assert result.status == "disagreement"
    assert_raw_spans(left, right, result)
    assert align_readings(left, right) == result


def test_astral_offsets_crlf_line_and_combining_normalization_are_explicit():
    result = align_readings(reading("😀a\r\nb"), reading("😀a\r\nc", "right"))
    position = result.alternatives[0].left.start
    assert (
        position.codepoint,
        position.utf8_byte,
        position.utf16_codeunit,
        position.line,
        position.column_codepoint,
    ) == (4, 7, 5, 2, 0)
    combining = align_readings(reading("e\u0301"), reading("é", "right"))
    assert (
        combining.status == "disagreement"
        and combining.left.text_sha256 != combining.right.text_sha256
    )


@pytest.mark.parametrize(
    "text,changes,reason",
    [
        ("same", {"source_truncated": True}, "source_truncated"),
        ("\ud800", {}, "invalid_unicode_scalar"),
        ("", {}, "empty_reading_not_agreement"),
    ],
)
def test_invalid_truncated_empty_identical_inputs_never_agree(text, changes, reason):
    result = align_readings(reading(text, **changes), reading(text, "right", **changes))
    assert result.status == "policy_blocked" and reason in result.reasons
    assert result.edit_distance is None and not result.alternatives


def test_long_reading_small_change_is_fully_aligned_without_copying_whole_text():
    left = reading("a" * 45000 + "1900" + "z" * 45000)
    right = reading("a" * 45000 + "1908" + "z" * 45000, "right")
    tracemalloc.start()
    result = align_readings(left, right)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert result.status == "disagreement" and result.alignment_cells == 4
    assert result.alternatives[0].left.start.codepoint == 45003
    assert sum(len(a.left.text) + len(a.right.text) for a in result.alternatives) == 2
    assert peak < ReadingLimits().max_working_bytes
    assert_raw_spans(left, right, result)


def test_explicit_input_cell_memory_and_output_bounds_never_silently_clip():
    cases = [
        (
            "x" * 11,
            "x" * 11,
            ReadingLimits(max_codepoints=10),
            "reading_codepoint_limit",
        ),
        ("😀" * 3, "😀" * 3, ReadingLimits(max_utf8_bytes=10), "reading_utf8_limit"),
        ("x" * 300, "y" * 300, ReadingLimits(), "alignment_cell_budget_exhausted"),
        (
            "abc",
            "xyz",
            ReadingLimits(max_working_bytes=1),
            "alignment_memory_budget_exhausted",
        ),
        (
            "abc",
            "xyz",
            ReadingLimits(max_alternative_codepoints=2),
            "alignment_output_budget_exhausted",
        ),
        (
            "1a2b3c",
            "1x2y3z",
            ReadingLimits(max_spans=1),
            "alignment_span_budget_exhausted",
        ),
    ]
    for a, b, limits, reason in cases:
        result = align_readings(reading(a), reading(b, "right"), limits)
        assert result.status == "policy_blocked" and reason in result.reasons
        assert not result.alternatives and result.edit_distance is None
        assert result.left.source_ref == "immutable:left"
        if reason.startswith("reading_"):
            assert result.left.text_sha256 is None and result.comparison_sha256 is None


def test_randomized_multiscript_alignment_reconstructs_original_readings():
    randomizer = random.Random(187)
    alphabet = "abc١中é\u0301😀\n\r"
    for _ in range(120):
        a = "".join(randomizer.choices(alphabet, k=randomizer.randrange(1, 30)))
        b = "".join(randomizer.choices(alphabet, k=randomizer.randrange(1, 30)))
        left, right = reading(a), reading(b, "right")
        result = align_readings(left, right)
        assert result.status in {"agreement", "disagreement"}
        assert_raw_spans(left, right, result)


def test_risk_missing_or_conflicting_metadata_and_blocked_alignment_are_unmeasured():
    a = reading("1900", declarations=(declaration(), declaration("script", "Latn")))
    b = reading(
        "1908",
        "right",
        declarations=(declaration(value="es"), declaration("script", "Latn")),
    )
    alignment = align_readings(a, b)
    evidence = reading_risk_evidence(
        alignment, (summarize_reading(a), summarize_reading(b))
    )
    assert {s.code for s in evidence.signals} == {
        "unresolved_disagreement",
        "numeral_disagreement",
    }
    assert evidence.unmeasured == ("language",)
    assert set(
        reading_risk_evidence(alignment, (summarize_reading(a),)).unmeasured
    ) == {"language", "script"}
    blocked = align_readings(a, b, ReadingLimits(max_working_bytes=1))
    assert "reading_disagreement" in reading_risk_evidence(blocked, ()).unmeasured
    with pytest.raises(ValueError):
        reading_risk_evidence(alignment, (summarize_reading(reading("other")),))


def test_typed_roundtrip_retains_source_digest_and_missing_metadata_is_not_complete():
    from specimen_digitization.application.reading_evidence import ReadingAlignment

    source_digest = sha256(b"synthetic original response").hexdigest()
    a = reading("é😀", source_sha256=source_digest)
    b = reading("é😀", "right")
    result = align_readings(a, b)
    assert result.status == "agreement"
    assert ReadingAlignment.model_validate_json(result.model_dump_json()) == result
    assert result.left.source_sha256 == source_digest
    risk = reading_risk_evidence(result, ())
    assert risk.signals == () and risk.unmeasured == ("language", "script")


def test_small_edit_distance_matches_independent_recursive_oracle():
    from functools import lru_cache
    from itertools import product

    @lru_cache(None)
    def distance(a, b):
        if not a or not b:
            return len(a) + len(b)
        return min(
            distance(a[1:], b) + 1,
            distance(a, b[1:]) + 1,
            distance(a[1:], b[1:]) + (a[0] != b[0]),
        )

    examples = ["".join(p) for size in range(1, 4) for p in product("a中", repeat=size)]
    for a in examples:
        for b in examples:
            result = align_readings(reading(a), reading(b, "right"))
            assert result.edit_distance == distance(a, b)
