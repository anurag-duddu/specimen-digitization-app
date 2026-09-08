"""Deterministic transcription evaluators and a synthetic Logfire experiment."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import logfire
from pydantic import BaseModel, ConfigDict, Field
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .observability import CaptureMode, configure_observability
from .transcription import LiteralTranscription


class TranscriptionEvalInput(BaseModel):
    """Synthetic candidate used to exercise the evaluation contract."""

    model_config = ConfigDict(frozen=True)

    candidate: LiteralTranscription


class TranscriptionEvalMetadata(BaseModel):
    """Non-content dimensions used to stratify an evaluation dataset."""

    model_config = ConfigDict(frozen=True)

    collection_profile_id: str = Field(min_length=1)
    difficulty_tags: list[str] = Field(default_factory=list)


TranscriptionEvaluatorContext = EvaluatorContext[
    TranscriptionEvalInput,
    LiteralTranscription,
    TranscriptionEvalMetadata,
]


def character_accuracy(actual: str, expected: str) -> float:
    """Return one minus case-sensitive Levenshtein distance, normalized to 0..1."""
    if not actual and not expected:
        return 1.0
    previous = list(range(len(expected) + 1))
    for actual_index, actual_character in enumerate(actual, start=1):
        current = [actual_index]
        for expected_index, expected_character in enumerate(expected, start=1):
            insertion = current[expected_index - 1] + 1
            deletion = previous[expected_index] + 1
            substitution = previous[expected_index - 1] + (
                actual_character != expected_character
            )
            current.append(min(insertion, deletion, substitution))
        previous = current
    distance = previous[-1]
    return max(0.0, 1.0 - distance / max(len(actual), len(expected)))


@dataclass
class VerbatimExact(
    Evaluator[TranscriptionEvalInput, LiteralTranscription, TranscriptionEvalMetadata]
):
    """Require exact text, including capitalization, punctuation, and line breaks."""

    def evaluate(self, ctx: TranscriptionEvaluatorContext) -> bool:
        return bool(
            ctx.expected_output
            and ctx.output.verbatim_text == ctx.expected_output.verbatim_text
        )


@dataclass
class CharacterAccuracy(
    Evaluator[TranscriptionEvalInput, LiteralTranscription, TranscriptionEvalMetadata]
):
    """Measure faithful transcription without case-folding or normalization."""

    def evaluate(self, ctx: TranscriptionEvaluatorContext) -> float:
        if ctx.expected_output is None:
            return 0.0
        return character_accuracy(
            ctx.output.verbatim_text,
            ctx.expected_output.verbatim_text,
        )


@dataclass
class LineStructureExact(
    Evaluator[TranscriptionEvalInput, LiteralTranscription, TranscriptionEvalMetadata]
):
    """Require the expected visual line structure."""

    def evaluate(self, ctx: TranscriptionEvaluatorContext) -> bool:
        return bool(
            ctx.expected_output and ctx.output.lines == ctx.expected_output.lines
        )


@dataclass
class UncertaintyExact(
    Evaluator[TranscriptionEvalInput, LiteralTranscription, TranscriptionEvalMetadata]
):
    """Require unreadable spans to remain explicit instead of being guessed."""

    def evaluate(self, ctx: TranscriptionEvaluatorContext) -> bool:
        return bool(
            ctx.expected_output
            and ctx.output.unreadable_spans == ctx.expected_output.unreadable_spans
        )


TRANSCRIPTION_EVALUATORS = (
    VerbatimExact(),
    CharacterAccuracy(),
    LineStructureExact(),
    UncertaintyExact(),
)


def build_transcription_dataset(
    *,
    name: str,
    cases: list[
        Case[
            TranscriptionEvalInput,
            LiteralTranscription,
            TranscriptionEvalMetadata,
        ]
    ],
) -> Dataset[TranscriptionEvalInput, LiteralTranscription, TranscriptionEvalMetadata]:
    """Build a versioned dataset with the standard deterministic evaluators."""
    return Dataset(
        name=name,
        cases=cases,
        evaluators=list(TRANSCRIPTION_EVALUATORS),
    )


def build_contract_smoke_dataset() -> Dataset[
    TranscriptionEvalInput,
    LiteralTranscription,
    TranscriptionEvalMetadata,
]:
    """Return synthetic cases that verify the evaluation-to-Logfire path."""
    exact = LiteralTranscription(
        verbatim_text="Chicago, Ill.\n12 Sept. 1948",
        lines=["Chicago, Ill.", "12 Sept. 1948"],
        unreadable_spans=[],
    )
    uncertain = LiteralTranscription(
        verbatim_text="Mt. [unreadable]\n3 Sept. 46",
        lines=["Mt. [unreadable]", "3 Sept. 46"],
        unreadable_spans=["[unreadable]"],
    )
    metadata = TranscriptionEvalMetadata(
        collection_profile_id="synthetic-insects-v1",
        difficulty_tags=["contract-smoke"],
    )
    return build_transcription_dataset(
        name="specimen-digitization/transcription-contract-smoke/v1",
        cases=[
            Case(
                name="exact-two-line-label",
                inputs=TranscriptionEvalInput(candidate=exact),
                expected_output=exact,
                metadata=metadata,
            ),
            Case(
                name="explicit-unreadable-span",
                inputs=TranscriptionEvalInput(candidate=uncertain),
                expected_output=uncertain,
                metadata=metadata,
            ),
        ],
    )


def _contract_task(inputs: TranscriptionEvalInput) -> LiteralTranscription:
    return inputs.candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one synthetic transcription contract experiment to Logfire."
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Run the experiment locally without exporting it to Logfire.",
    )
    args = parser.parse_args()

    configure_observability(
        send_to_logfire=False if args.no_send else None,
        capture_mode=CaptureMode.APPROVED_CONTENT,
    )
    try:
        report = build_contract_smoke_dataset().evaluate_sync(
            _contract_task,
            name="transcription-contract-smoke",
            progress=False,
            metadata={
                "dataset_version": "v1",
                "schema_version": "literal-transcription-v1",
                "data_classification": "synthetic",
            },
        )
        report.print(include_input=False, include_output=False)
    finally:
        logfire.force_flush()


if __name__ == "__main__":
    main()
