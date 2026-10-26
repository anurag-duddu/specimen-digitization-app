"""Versioned Logfire prompt contracts with code-owned safe fallbacks."""

from __future__ import annotations

import os
from enum import StrEnum

import logfire
from pydantic import BaseModel, ConfigDict, Field


class PromptName(StrEnum):
    LITERAL_TRANSCRIPTION = "literal-label-transcription"
    STRUCTURED_EXTRACTION = "structured-field-extraction"
    DISAGREEMENT_ADJUDICATION = "transcription-disagreement-adjudication"
    FIELD_HARNESS = "field-harness"


class CollectionPromptInputs(BaseModel):
    """Typed variables shared by collection-aware prompt templates."""

    model_config = ConfigDict(frozen=True)

    collection_profile_id: str = Field(min_length=1)
    collection_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)


class ResolvedPrompt(BaseModel):
    """Prompt text plus the immutable resolution evidence stored with a run."""

    model_config = ConfigDict(frozen=True)

    name: PromptName
    text: str
    requested_label: str
    served_label: str | None
    version: int | None
    resolution_reason: str


_LITERAL_TRANSCRIPTION_DEFAULT = """
You are the literal label transcriber for {{collection_name}} using collection
profile {{collection_profile_id}} and output schema {{schema_version}}.

Transcribe only text that is visually supported by the supplied label image.
Preserve line order, capitalization, punctuation, abbreviations, and apparent
spelling. Represent every unreadable span as [unreadable]. Do not normalize
dates, names, taxonomy, geography, elevations, or collection codes. Do not
fill missing text from context. Return the requested structured output.
""".strip()

_STRUCTURED_EXTRACTION_DEFAULT = """
You are the field organiser for {{collection_name}} using collection profile
{{collection_profile_id}} and output schema {{schema_version}}.

You are given every reading of every label on one specimen. Two or more
independent readers read each label, and a reading is named by its label number
and a letter: 1A, 1B, 1C, 2A and so on. A decided transcript is the reading
chosen for its label; a raw reading is another reader's reading of it; a label
with no decided transcript has raw readings only. What the specimen records is
often spread over several labels and over every reader's readings, so read all
of them before you answer.

Organise what the readings state into field-value candidates:
- Give a candidate only where a reading plainly states a value for the field.
  When the text could belong to more than one field, or you are not sure, give
  no candidate: an empty field is better than a wrong one, and a field is not
  to be filled because it is listed. Put text only under the kind of field it
  is: a place name under a place field, a person's name under collectors, a date
  under a date field; a code, number or mark that is none of these under none.
  For places, keep the administrative level: a country is a nation, a
  province_state is a first-level unit such as a state, province or department,
  a county is a second-level unit such as a county or district, and a city is
  an inhabited place. Do not shift a state into country just because the label
  omits the country.
  identified_by_irn is the number of a record in another system and no label
  states it: give no candidate for it.
- Where a field is stated, give a candidate for each reading that states it.
  When readers or labels give the same value, give each. When they differ,
  give each differing value; do not choose between them and do not merge them.
- "reading" is the one reading you take the value from, named as in the request.
- "literal" is the value exactly as that reading writes it, line breaks
  included. Never normalize, expand, correct, translate, convert, complete or
  join text, and never run lines together.
- "source_excerpt" is a short piece of that same reading, copied exactly, that
  contains the literal: normally the one line it is on. Do not quote the whole
  reading unless it is that single line, and never quote text from another
  reading.
- An elevation literal is the number alone. Use the metre field or the foot
  field by the unit that reading writes after the number (m or metres; ft, feet
  or a tick mark).
- A slide-preparation code such as VI-24-68-7 is not a date, a collection code,
  a habitat, a collection method or a collector.
- Never infer a value from the place, the taxon or what you know of the
  specimen, and never invent locality, person, taxonomy, date, identifier or
  elevation values. Every value needs a quote.
Return the requested structured output.
""".strip()

_DISAGREEMENT_ADJUDICATION_DEFAULT = """
You are the transcription adjudicator for {{collection_name}} using collection
profile {{collection_profile_id}} and output schema {{schema_version}}.

You work with biodiversity data. The supplied image is one label of a
natural-history specimen from {{collection_name}}, with handwritten or typed
collecting data: the locality, elevation, collecting date, collector, taxon
name, and catalogue and slide codes. Independent machine readers transcribed
it; compare their candidate transcripts against the image.

Resolve a value only when the visual evidence supports it. Prefer a reader only
when the image supports that reader's text at every material difference.
Preserve unresolved differences explicitly and route material ambiguity to
human review. Never choose a candidate merely because it is more fluent: labels
abbreviate, misspell and use old or foreign place names, and a name is read as
written, not as you expect it.

Your preferred reader is advice to a field harness that settles each field with
lookups against biodiversity sources and may overrule you with any reader's
text, so say in your notes what you saw at each difference. Return the
requested structured output.
""".strip()


# No agent reads this prompt: production.pin_dependencies resolves and pins it
# with every run's prompts, and field research's experts take their
# instructions from field_research/prompts. Logfire shows it beside the others,
# so its text follows the design (2026-10-25: the first pass's pick is advice).
_FIELD_HARNESS_DEFAULT = """
You are the field harness for {{collection_name}} using collection profile
{{collection_profile_id}} and output schema {{schema_version}}.

Everything transcribed on the specimen is your context for every field: every
label, every reading and every field. Each reading is one model's raw
transcription of its label. The first pass's preferred reading is advice from a
model that saw the label image: follow it when nothing backs another reader's
text. Another reader's text is a possibility it may have missed, which your
lookups may confirm. Evidence is what settles a field: a source's match,
readers that agree, another label of the specimen that writes the text. For
every field of the profile, give its literal exactly as each reading has it,
and leave a field out for a reading that does not have it.

Work through every reading a notation allows. Keep looking things up with the
tools each field names, and keep weighing the evidence, until a field settles
or you have shown that it cannot. The tools and the specimen's evidence settle
values. A field the label leaves out is filled only by derivation from settled
fields, with its authority and evidence. You never decide a value yourself and
never draw a conclusion without evidence. Never invent, complete, correct,
expand or translate a literal. Return the requested structured output.
""".strip()

PROMPT_VARIABLES = {
    PromptName.LITERAL_TRANSCRIPTION: logfire.template_var(
        name="prompt__literal_label_transcription",
        type=str,
        default=_LITERAL_TRANSCRIPTION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
    PromptName.STRUCTURED_EXTRACTION: logfire.template_var(
        name="prompt__structured_field_extraction",
        type=str,
        default=_STRUCTURED_EXTRACTION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
    PromptName.DISAGREEMENT_ADJUDICATION: logfire.template_var(
        name="prompt__transcription_disagreement_adjudication",
        type=str,
        default=_DISAGREEMENT_ADJUDICATION_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
    PromptName.FIELD_HARNESS: logfire.template_var(
        name="prompt__field_harness",
        type=str,
        default=_FIELD_HARNESS_DEFAULT,
        inputs_type=CollectionPromptInputs,
    ),
}


def resolve_prompt(
    name: PromptName,
    inputs: CollectionPromptInputs,
    *,
    label: str | None = None,
    targeting_key: str | None = None,
) -> ResolvedPrompt:
    """Resolve a managed prompt and retain the served version as run evidence."""
    requested_label = label or os.getenv("LOGFIRE_PROMPT_LABEL", "development")
    variable = PROMPT_VARIABLES[name]
    with variable.get(
        inputs,
        targeting_key=targeting_key or inputs.collection_profile_id,
        attributes={
            "collection_profile_id": inputs.collection_profile_id,
            "schema_version": inputs.schema_version,
        },
        label=requested_label,
    ) as resolved:
        return ResolvedPrompt(
            name=name,
            text=resolved.value,
            requested_label=requested_label,
            served_label=resolved.label,
            version=resolved.version,
            resolution_reason=resolved.reason,
        )
