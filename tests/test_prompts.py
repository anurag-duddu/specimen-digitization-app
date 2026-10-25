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


def test_the_first_pass_prompt_works_with_biodiversity_data_and_gives_its_pick_as_advice() -> None:
    """The owner, 2026-10-25: "The LLM system Prompt is to be working with
    biodiversity data and context should be around it". The first pass's
    code default keeps G19's rule and the fluency rule, and says its pick is
    advice to a field harness that may overrule it."""
    text = " ".join(prompts._DISAGREEMENT_ADJUDICATION_DEFAULT.split())
    for sentence in (
        "You work with biodiversity data.",
        "The supplied image is one label of a natural-history specimen from {{collection_name}}, with "
        "handwritten or typed collecting data: the locality, elevation, collecting date, collector, taxon "
        "name, and catalogue and slide codes.",
        "Prefer a reader only when the image supports that reader's text at every material difference.",
        "Preserve unresolved differences explicitly and route material ambiguity to human review.",
        "Never choose a candidate merely because it is more fluent:",
        "Your preferred reader is advice to a field harness that settles each field with lookups against "
        "biodiversity sources and may overrule you with any reader's text, so say in your notes what you "
        "saw at each difference.",
    ):
        assert sentence in text


def test_the_field_harness_prompt_no_agent_reads_states_the_first_pass_as_advice() -> None:
    text = " ".join(prompts._FIELD_HARNESS_DEFAULT.split())
    assert "The first pass's preferred reading is advice from a model that saw the label image" in text
    assert "Another reader's text is a possibility" in text
    assert "decided transcript's lookups" not in text
