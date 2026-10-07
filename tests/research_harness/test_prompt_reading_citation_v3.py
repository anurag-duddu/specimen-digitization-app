"""The v3 prompts: the reading citation and the human question evidence rule (Lane P G3, 2026-10-03).

Every v3 file is its v2 file followed by one or two blocks, so the v2 text, the common text
and each role's owned-fields line are untouched; the v2 files stay on disk (their digests are
pinned in test_geography_prompt_v2.py). These tests pin the exact text and the committed pin
digests it moves. They fail only when the text changes: that the text works is shown by
test_unkeyed_label_reading_citation.py, which runs a specialist that reads its behaviour out
of this text through the production composer. Whether a real model follows it is not tested.

Taxonomy, geography, parties and collection get both blocks: they are the roles whose v2 text
says a lookup's producer comes from the assemblies a resolution names, which a real label (no
event, no assembly) cannot give. Temporal and measurement have no such sentence and no lookup
source; they get the question block only, since any role may ask a human question.
"""
import hashlib
import re
from pathlib import Path

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldResolution, HumanQuestion, SourceFragment, SpecialistRole,
)
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_HISTORY_PROMPT_VERSION, TAXONOMY_QUERY_PROMPT_VERSION, HANDOVER_PROMPT_VERSION, QUALIFIED_PROMPT_VERSION, READING_CITATION_PROMPT_VERSION,
    MEASUREMENT_EVIDENCE_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
PRODUCER_BLOCK = """Producer and literal without an assembly (publication): a value that cites a
lookup needs a producer, and a value.literal needs grounding. Where the request
has no assembly for the field that your interpretation read (on a label whose
lines carry no field key, assemblies are empty), leave assembly_ids empty and
event_id null, and on the value itself cite the one reading you interpreted,
copying from one entry of the request's fragments[]: source_observation_id = its
observation_id, verbatim_by_observation = {that observation_id: the label text
you read, copied character for character from its observation_text (line breaks
included; do not re-wrap, trim or normalise)}, settled_observation_ids = [that
observation_id], input_source = its input_source (decided_transcript or
raw_reading), source_region_id = its region_id. A changed character is refused
at publication, after your run, and stops the record's later publications. Cite
only that one reading, even when the other reader's reading is identical; do not
list the other reader. Take a decided_transcript entry when the text is in one,
else a raw_reading entry. value.literal is then only text inside one fragment's
literal of that reading (one line); for text written over several lines leave
literal null: verbatim_by_observation keeps the lines. Name assemblies or cite a
reading, not both; a lookup with neither has no producer and publication
refuses it.
"""
QUESTION_BLOCK = """Human question evidence (publication): give a human question's supporting evidence
only in question.evidence_ids. On a waiting_human resolution leave
FieldResolution.evidence_ids and value.evidence_ids empty: evidence cited there
passes validation, then blocks publication of the record.
"""
BLOCKS = {
    SpecialistRole.TAXONOMY: PRODUCER_BLOCK + QUESTION_BLOCK,
    SpecialistRole.GEOGRAPHY: PRODUCER_BLOCK + QUESTION_BLOCK,
    SpecialistRole.PARTIES: PRODUCER_BLOCK + QUESTION_BLOCK,
    SpecialistRole.COLLECTION: PRODUCER_BLOCK + QUESTION_BLOCK,
    SpecialistRole.TEMPORAL: QUESTION_BLOCK,
    SpecialistRole.MEASUREMENT: QUESTION_BLOCK,
}
# The v3 files' sha256 and the pin digests of common-v1.txt + the file + the owned-fields line
# (resolve_prompt). The v2 pin digests they replace are in test_geography_prompt_v2.py.
V3_FILES = {
    SpecialistRole.TAXONOMY: "8c251604bd7e625e5f2ad88f723e233c749ec26b6d3f09a9ce0677d5b9f93963",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "1f9c6a5762e1873228b829f0f334f547c29d97a59c51831c694fe8f4190f4795",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "dddedbcab47180c728f0538b2359c93972c8ec540a9ae9dfa6f4d79202a9b38f",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "9fcc4eb9d206b597cfbc0e203c6d57c2c4c8e578c403c939938baeee516b5480",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "752b3c106e8942840eb0e6be7540d286f8ae6724d962c018e67fa0d0cde9011f",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "40d6979ed0a375987fb696afb9b20dc4e25e026f1946ec594d4292affdcd6b18",  # pragma: allowlist secret
}
V3_PIN_DIGESTS = {
    SpecialistRole.TAXONOMY: "d70e05f68980495c4062b22d333732d8d0755341edab97c5d97e20be71b5e821",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "8d543fe32d4c700ee001a58ddd7904b56443b053e520f40a33ebb35738042b16",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "5c64fa5e00c2f2af515e4629eaeb9ad6994679b34dfe7fc007fa86ca0183241e",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "9b89f875c2976561b4b1605cd19d35fb230cd27f932a2f86b2eb5ddabf556976",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "1fe094ef0724f4a0ac82ebadb6d0ade04879b455ca2c65265afcfe5a6565a99c",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "c2545fe73a63a3fabaa16dbcfcd75dcee394b463ef1fcb12574fa9db3f533128",  # pragma: allowlist secret
}
# The old sentence, kept in the four roles: where assemblies exist a resolution still names them.
ASSEMBLY_RULE = (
    "Every resolution that cites a lookup names, as the common rules ask, its accepted/rejected "
    "assemblies (assembly_ids: the request's assemblies for that field that the interpretation read) "
    "and event (event_id); the lookup's producer comes from them, and publication refuses a lookup "
    "without one.")
GEOGRAPHY_ASSEMBLY_RULE = (
    "Every resolution that cites a GEOLocate lookup names, as the common rules ask, its accepted/rejected "
    "assemblies (assembly_ids: the request's assemblies for that field that the interpretation read) "
    "and event (event_id); the lookup's producer comes from them, and publication refuses a lookup "
    "without one.")
# The citation fields the producer block names; the composer test shows each is needed (input_source
# only when a decided transcript is cited, region id with it) and that nothing else is.
CITATION_FIELDS = {"source_observation_id", "verbatim_by_observation", "settled_observation_ids",
    "input_source", "source_region_id"}


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


def flat(text):
    return " ".join(text.split())


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_v3_file_is_its_v2_file_followed_by_the_blocks(role):
    v2 = (ROOT / f"{role.value}-v2.txt").read_bytes()
    v3 = (ROOT / f"{role.value}-v3.txt").read_bytes()
    v3.decode("ascii")
    assert v3 == v2 + BLOCKS[role].encode("ascii")
    assert hashlib.sha256(v3).hexdigest() == V3_FILES[role]


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_the_v3_pin_is_audited_from_the_file_and_the_live_pin_extends_it(role):
    # The live table moved on to the v4 files (the missing-policy block, test_prompt_missing_policy_v4.py) and then
    # to the v5 files (the hand-over block, test_prompt_handover_v5.py); the v3 pin digest is the audit record and
    # the live text begins with the v3 text.
    assert READING_CITATION_PROMPT_VERSION == "specialists-reading-citation-v3-2026-10-03"
    qualified = role in {SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.GEOGRAPHY}
    assert ROLE_PROMPTS[role] == (f"{role.value}-v{7 if role in {SpecialistRole.GEOGRAPHY, SpecialistRole.MEASUREMENT} else 6 if qualified or role == SpecialistRole.TAXONOMY else 5}.txt",
        GEOGRAPHY_HISTORY_PROMPT_VERSION if role == SpecialistRole.GEOGRAPHY else
        MEASUREMENT_EVIDENCE_PROMPT_VERSION if role == SpecialistRole.MEASUREMENT else
        TAXONOMY_QUERY_PROMPT_VERSION if role == SpecialistRole.TAXONOMY else
        QUALIFIED_PROMPT_VERSION if qualified else HANDOVER_PROMPT_VERSION)
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    v3 = (ROOT / f"{role.value}-v3.txt").read_text(encoding="utf-8")
    owned = "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n"
    assert hashlib.sha256((common + v3 + owned).encode()).hexdigest() == V3_PIN_DIGESTS[role]
    assert pin(role).text.startswith(common + v3)


@pytest.mark.parametrize("role", (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.PARTIES,
                                  SpecialistRole.COLLECTION))
def test_the_four_lookup_roles_still_name_assemblies_where_the_request_has_them(role):
    text = flat(pin(role).text)
    rule = GEOGRAPHY_ASSEMBLY_RULE if role == SpecialistRole.GEOGRAPHY else ASSEMBLY_RULE
    assert rule in text and flat(PRODUCER_BLOCK) in text
    # The reading is for a field with no assembly the interpretation read, and never beside assemblies.
    assert "Where the request has no assembly for the field that your interpretation read" in text
    assert "Name assemblies or cite a reading, not both" in text
    # The two rules a plausible model breaks (Lane P review of #257): both readers listed, and a changed copy.
    assert "Cite only that one reading, even when the other reader's reading is identical; do not list the other reader." in text
    assert "copied character for character from its observation_text (line breaks included; do not re-wrap, trim or normalise)" in text


@pytest.mark.parametrize("role", (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT))
def test_temporal_and_measurement_get_the_question_rule_only(role):
    text = flat(pin(role).text)
    assert flat(QUESTION_BLOCK) in text
    assert "Producer and literal without an assembly" not in text and "source_observation_id" not in text


def test_the_blocks_name_only_fields_the_contracts_have():
    values = set(FieldValue.model_fields)
    # The FieldValue fields the producer block names: the five citation fields and literal.
    assert {name for name in re.findall(r"[a-z_]+", PRODUCER_BLOCK) if name in values} == CITATION_FIELDS | {"literal"}
    # Every name_with_underscore in the blocks is a field of the value, the resolution or the request's fragments.
    known = values | set(FieldResolution.model_fields) | set(SourceFragment.model_fields) | {
        "decided_transcript", "raw_reading"}
    assert set(re.findall(r"[a-z]+(?:_[a-z]+)+", PRODUCER_BLOCK)) <= known
    assert {"assembly_ids", "event_id", "evidence_ids", "question"} <= set(FieldResolution.model_fields)
    assert "evidence_ids" in HumanQuestion.model_fields and "evidence_ids" in values
    assert set(re.findall(r"[a-z]+(?:_[a-z]+)+", QUESTION_BLOCK)) <= known | {"waiting_human"}


def test_the_common_text_is_unchanged():
    # common-v1.txt is byte-pinned in test_geography_prompt_v2.V1_FILES; the pins here start with it.
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    assert all(pin(role).text.startswith(common) for role in SpecialistRole)
