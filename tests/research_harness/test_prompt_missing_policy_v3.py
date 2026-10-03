"""The v3 role prompts: the missing-policy block (2026-10-03).

Each v3 file is its v2 file followed by one block. The block tells the role that
the committed research profile declares missing policy
"unstructured_label_event_unqualified" for some of its owned fields, to return
waiting_policy for such a field when no assembly and no source can ground it,
and to keep waiting_source for a source that failed or is unconfigured. The v2
and v1 files stay on disk byte for byte (tests/research_harness/
test_geography_prompt_v2.py pins the v1 files and the v2 pin digests).
common-v1.txt is not touched: its digest is pinned there too.
"""
import hashlib
import re
from pathlib import Path

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.committed_pins import (
    UNQUALIFIED_LABEL_FIELDS, UNQUALIFIED_LABEL_POLICY, build_committed_pins,
)
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, FieldKey, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROMPT_VERSION, MISSING_POLICY_PROMPT_VERSION, RELATIONS_PROMPT_VERSION, ROLE_PROMPTS,
    resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
HEADER = "Missing policy (unstructured labels): the pinned profile declares missing_policy\n"
REASON = f'"missing_policy:{UNQUALIFIED_LABEL_POLICY}'
# The literal fields' roles: no source is connected for them, so there is no failure to report.
LITERAL_ROLES = (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
    SpecialistRole.COLLECTION)
# sha256 of each file's bytes: the v2 files as on main (unchanged), the v3 files as added.
FILE_SHA256 = {
    "specimen_taxonomy-v2.txt": "832626c5d7082d33a4f249bce2fca2746f959247653e523117d2cdfacb361092",  # pragma: allowlist secret
    "specimen_taxonomy-v3.txt": "5bde5b017b1f48827088bbaa8633d2444e97327329d7cb9a4db26a8eed398ff4",  # pragma: allowlist secret
    "specimen_geography-v2.txt": "06609acdab2752826f718b292b73a19061d8014b900c646cc4fb5466253d0330",  # pragma: allowlist secret
    "specimen_geography-v3.txt": "3de92fe3d10151e44e9ff0b9e0e8b8d5c2ea1fb75988fb62ae0f6afbc3a56bb0",  # pragma: allowlist secret
    "specimen_temporal-v2.txt": "ec316a45ca2a0b208e2dd842b89691c684639fb9ae1918a181f969f4418f0ac2",  # pragma: allowlist secret
    "specimen_temporal-v3.txt": "9ef5296e5abeb8b361bd3d2a0bc97dd3e86a7209f00c3303369cd7278029a4de",  # pragma: allowlist secret
    "specimen_measurement-v2.txt": "49b332414bb02784f9e584410db5777619e64b8866203901a36d48730b9a4647",  # pragma: allowlist secret
    "specimen_measurement-v3.txt": "2a771d6523102bbdb157725117ba4cd42fb72cbd643aa64b22eb894bab5c22ca",  # pragma: allowlist secret
    "specimen_parties-v2.txt": "e5f7dae5716931eff095bd77a3e02561555e5a8c2f2645f3f1d93c720ddbbd33",  # pragma: allowlist secret
    "specimen_parties-v3.txt": "5440516ee0a1e4c92e0716beb21d5f5bf92a529159b441de95c9254c6af0c3d4",  # pragma: allowlist secret
    "specimen_collection-v2.txt": "98b308f54dd5a287896ed321560ef857857f638713257fd69921980eb8612a2c",  # pragma: allowlist secret
    "specimen_collection-v3.txt": "4dbac271f6727a290edca74f755b1a9747fd195e5631c6cfecf4e21b3cb35d5c",  # pragma: allowlist secret
}
# Each role's pin digest on its v3 file (the digest of common-v1.txt, the v3 file and the owned-fields line).
V3_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "c9e829ef3fadecaf7fc1b2ded0b8dbeb7c810f8e5b290d2ced11ce88ab4b174f",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "3b0ce24954241b9093c7507cc978b7d055af7b0fd64003846b2eab327719b850",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "b83b5ba03709c5beb478c125f2dd9cc434accfdcfca7c4c41805ae79b39a7632",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "f1376cffa6d7a0051e091ef8b9eff6b14779a864300e30d6b03985342d4a650b",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "df3253d85f9b6d1829e8fa43845ddd42e9b9c99ef78f5ff6a3ab051425c2c316",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "c5b737716468b03081ab0c57c685ebec0dba26aaa35f111efe9807051dd4d87f",  # pragma: allowlist secret
}


def flat(text):
    return " ".join(text.split())


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


def block(role):
    v2 = (ROOT / f"{role.value}-v2.txt").read_bytes()
    v3 = (ROOT / f"{role.value}-v3.txt").read_bytes()
    assert v3.startswith(v2)
    return v3[len(v2):].decode("ascii")


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_role_resolves_to_its_v3_file_at_the_missing_policy_version(role):
    assert ROLE_PROMPTS[role] == (f"{role.value}-v3.txt", MISSING_POLICY_PROMPT_VERSION)
    assert MISSING_POLICY_PROMPT_VERSION == "specialists-missing-policy-v3-2026-10-03"
    assert MISSING_POLICY_PROMPT_VERSION not in {RELATIONS_PROMPT_VERSION, GEOGRAPHY_PROMPT_VERSION}
    prompt = pin(role)
    expected = ((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
                + (ROOT / f"{role.value}-v3.txt").read_text(encoding="utf-8")
                + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
    assert prompt.version == MISSING_POLICY_PROMPT_VERSION
    assert prompt.text == expected and prompt.digest == hashlib.sha256(expected.encode()).hexdigest()
    assert prompt.digest == V3_ROLE_DIGESTS[role]


@pytest.mark.parametrize(("name", "sha256"), tuple(FILE_SHA256.items()))
def test_the_v2_files_stay_byte_identical_and_the_v3_files_are_pinned(name, sha256):
    raw = (ROOT / name).read_bytes()
    raw.decode("ascii")  # read_text must not depend on the locale's encoding
    assert hashlib.sha256(raw).hexdigest() == sha256


def test_the_committed_pins_carry_the_v3_versions_and_digests():
    pins = build_committed_pins(published_registry().resolve("insects").profile,
        organization_id="org", collection_id="collection")
    assert {role: (row["version"], row["digest"]) for role, row in pins["prompts"].items()} == {
        str(role): (MISSING_POLICY_PROMPT_VERSION, digest) for role, digest in V3_ROLE_DIGESTS.items()}


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_the_block_follows_the_v2_text_and_names_the_policy_and_the_reason(role):
    text = block(role)
    assert text.startswith(HEADER) and text.endswith("\n")
    assert f'"{UNQUALIFIED_LABEL_POLICY}"' in text and REASON in flat(text)
    assert "waiting_policy" in text


def test_the_blocks_name_exactly_the_fields_the_committed_profile_declares():
    """The prompt and the profile cannot drift: each role's block names its declared owned fields and
    no other, and the roles together name all fifteen."""
    named = {}
    for role in SpecialistRole:
        listed = re.search(rf'"{UNQUALIFIED_LABEL_POLICY}" for (.+?)(?:, and no source|\.)', flat(block(role)))
        assert listed, role
        found = set(re.findall(r"[a-z_]+", listed[1])) - {"and"}
        assert found <= {str(key) for key in ROLE_FIELDS[role]}, (role, found)
        named[role] = {FieldKey(key) for key in found}
    assert set().union(*named.values()) == UNQUALIFIED_LABEL_FIELDS
    assert named[SpecialistRole.TAXONOMY] == {FieldKey.TAXON}
    assert named[SpecialistRole.GEOGRAPHY] == {FieldKey.COUNTY, FieldKey.CITY}


@pytest.mark.parametrize("role", LITERAL_ROLES)
def test_a_literal_role_never_returns_waiting_source_for_a_declared_field(role):
    text = flat(block(role))
    assert "no source is connected for" in text and "Never return waiting_source for" in text
    assert "no source that could fail" in text and "waiting_source blocks the record" in text
    assert "the common rule that a missing adapter is a source prerequisite" in text


@pytest.mark.parametrize("role", (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT))
def test_temporal_and_measurement_never_call_a_utility_on_text_that_is_not_an_assembly(role):
    # A utility call on label text raises research_utility_tool_failed and fails the whole role.
    text = flat(block(role))
    assert "Never call invoke_utility on text that is not an accepted assembly's interpreted_text" in text
    assert "fails the whole role" in text


@pytest.mark.parametrize(("role", "sentence"), (
    (SpecialistRole.TEMPORAL, "A field with an accepted assembly resolves as above."),
    (SpecialistRole.MEASUREMENT, "Elevations with an accepted assembly settle as above."),
    (SpecialistRole.PARTIES, "Collectors with an accepted assembly resolve as above."),
    (SpecialistRole.COLLECTION, "A field with an accepted assembly resolves as above."),
    (SpecialistRole.TAXONOMY, "A taxon with an accepted match resolves as above."),
))
def test_a_declared_field_that_can_be_grounded_still_resolves_as_before(role, sentence):
    assert sentence in flat(block(role))


def test_taxonomy_keeps_waiting_source_for_a_failed_lookup():
    text = flat(block(SpecialistRole.TAXONOMY))
    assert ("If a lookup failed, timed out, was rate limited or refused, or its source is not configured, "
            "return waiting_source as above") in text
    assert "that is operational and blocks the record." in text
    # The engine retries only operational_failed and retry_scheduled fields (engine.py), never a
    # waiting_source, so the prompt does not say it is retried.
    assert "retried" not in text


def test_geography_keeps_waiting_source_for_a_failed_lookup():
    text = flat(block(SpecialistRole.GEOGRAPHY))
    assert ("If a GEOLocate lookup for the field failed, timed out or was refused, abstain with "
            "waiting_source as above: that is operational and blocks the record") in text
    assert "This replaces the waiting_source instruction above for that case only" in text


def test_geography_leaves_country_state_and_precise_location_and_the_human_route_alone():
    text = flat(block(SpecialistRole.GEOGRAPHY))
    assert "country, province_state and precise_location are unchanged" in text
    assert "A no_match or ambiguous result still goes to a person as above" in text
    assert "GEOLocate confirms a county only inside the USA" in text


def test_taxonomy_never_proposes_a_taxon_the_readings_do_not_name():
    text = flat(block(SpecialistRole.TAXONOMY))
    assert "Never propose a taxon the readings do not name" in text
    assert "A taxon with an accepted match resolves as above" in text


def test_the_irn_and_verbatim_dts_texts_are_unchanged_in_the_roles_that_own_them():
    assert "identified_by_irn is unchanged: the declared exception." in flat(block(SpecialistRole.PARTIES))
    assert "verbatim_dts is unchanged: waiting_policy with its own reason." in flat(block(SpecialistRole.COLLECTION))
