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
