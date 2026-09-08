from __future__ import annotations

from types import SimpleNamespace

from specimen_digitization.evaluation import (
    CharacterAccuracy,
    LineStructureExact,
    UncertaintyExact,
    VerbatimExact,
    build_contract_smoke_dataset,
    character_accuracy,
)
from specimen_digitization.transcription import LiteralTranscription


def test_character_accuracy_is_case_and_punctuation_sensitive() -> None:
    assert character_accuracy("Davao Prov.", "Davao Prov.") == 1.0
    assert character_accuracy("Davao Prov", "Davao Prov.") < 1.0
    assert character_accuracy("", "") == 1.0


def test_transcription_evaluators_cover_text_lines_and_uncertainty() -> None:
    expected = LiteralTranscription(
        verbatim_text="Mt. [unreadable]\n3 Sept. 46",
        lines=["Mt. [unreadable]", "3 Sept. 46"],
        unreadable_spans=["[unreadable]"],
    )
    context = SimpleNamespace(expected_output=expected, output=expected)

    assert VerbatimExact().evaluate(context) is True
    assert CharacterAccuracy().evaluate(context) == 1.0
    assert LineStructureExact().evaluate(context) is True
    assert UncertaintyExact().evaluate(context) is True


def test_contract_dataset_executes_all_cases() -> None:
    dataset = build_contract_smoke_dataset()

    report = dataset.evaluate_sync(
        lambda inputs: inputs.candidate,
        progress=False,
    )

    assert len(report.cases) == 2
