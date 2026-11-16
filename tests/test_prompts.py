from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from specimen_digitization import prompts
from specimen_digitization.prompts import (
    CollectionPromptInputs,
    PromptName,
    resolve_prompt,
)


class FakePromptVariable:
    @contextmanager
    def get(self, inputs, **kwargs):
        assert inputs.collection_profile_id == "insects-v1"
        assert kwargs["label"] == "candidate"
        yield SimpleNamespace(
            value="Resolved prompt text",
            label="candidate",
            version=7,
            reason="remote",
        )


def test_prompt_resolution_retains_served_version(monkeypatch) -> None:
    monkeypatch.setitem(
        prompts.PROMPT_VARIABLES,
        PromptName.LITERAL_TRANSCRIPTION,
        FakePromptVariable(),
    )
    inputs = CollectionPromptInputs(
        collection_profile_id="insects-v1",
        collection_name="Field Museum Insects",
        schema_version="literal-transcription-v1",
    )

    resolved = resolve_prompt(
        PromptName.LITERAL_TRANSCRIPTION,
        inputs,
        label="candidate",
    )

    assert resolved.text == "Resolved prompt text"
    assert resolved.requested_label == "candidate"
    assert resolved.served_label == "candidate"
    assert resolved.version == 7


def test_the_first_pass_prompt_works_with_biodiversity_data() -> None:
    """The owner, 2026-10-25: "The LLM system Prompt is to be working with
    biodiversity data and context should be around it". The first pass's code
    default (since WP 1.8 the units path's) says so and keeps the fluency rule."""
    text = " ".join(prompts._FIRST_PASS_UNITS_DEFAULT.split())
    for sentence in (
        "You work with biodiversity data.",
        "The image is one label of a natural-history specimen from {{collection_name}}: locality, elevation, "
        "collecting date, collector, taxon name, catalogue and slide codes, handwritten or typed.",
        "Never prefer a text because it reads more fluently:",
    ):
        assert sentence in text
