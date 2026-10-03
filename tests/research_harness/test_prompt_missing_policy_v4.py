"""The v4 role prompts: the missing-policy block (2026-10-03).

Each v4 file is its v3 file (#257: the reading citation and the human question evidence
blocks, test_prompt_reading_citation_v3.py) followed by one block. The block tells the role
that the committed research profile declares missing policy
"unstructured_label_event_unqualified" for some of its owned fields, to return
waiting_policy for such a field when no assembly and no source can ground it,
and to keep waiting_source for a source that failed or is unconfigured. The v3, v2 and v1
files stay on disk byte for byte (test_prompt_reading_citation_v3.py pins the v3 files,
test_geography_prompt_v2.py the v2 and v1 files and the v2 pin digests).
common-v1.txt is not touched: its digest is pinned there too.
"""
import hashlib
import re
from pathlib import Path

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.committed_pins import (
    UNQUALIFIED_LABEL_FIELDS, UNQUALIFIED_LABEL_POLICY, build_committed_pins, committed_research_profile,
)
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, FieldKey, SpecialistRole, digest
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROMPT_VERSION, MISSING_POLICY_PROMPT_VERSION, READING_CITATION_PROMPT_VERSION,
    RELATIONS_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
HEADER = "Missing policy (unstructured labels): the pinned profile declares missing_policy\n"
REASON = f'"missing_policy:{UNQUALIFIED_LABEL_POLICY}'
# The literal fields' roles: no source is connected for them, so there is no failure to report.
LITERAL_ROLES = (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
    SpecialistRole.COLLECTION)
# The roles whose v3 text has the producer block: a value they resolved from a lookup cites its reading.
CITING_ROLES = (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY)
# sha256 of each file's bytes: the v3 files as #257 added them (audit), the v4 files as added here.
FILE_SHA256 = {
    "specimen_taxonomy-v3.txt": "8c251604bd7e625e5f2ad88f723e233c749ec26b6d3f09a9ce0677d5b9f93963",  # pragma: allowlist secret
    "specimen_geography-v3.txt": "1f9c6a5762e1873228b829f0f334f547c29d97a59c51831c694fe8f4190f4795",  # pragma: allowlist secret
    "specimen_temporal-v3.txt": "dddedbcab47180c728f0538b2359c93972c8ec540a9ae9dfa6f4d79202a9b38f",  # pragma: allowlist secret
    "specimen_measurement-v3.txt": "9fcc4eb9d206b597cfbc0e203c6d57c2c4c8e578c403c939938baeee516b5480",  # pragma: allowlist secret
    "specimen_parties-v3.txt": "752b3c106e8942840eb0e6be7540d286f8ae6724d962c018e67fa0d0cde9011f",  # pragma: allowlist secret
    "specimen_collection-v3.txt": "40d6979ed0a375987fb696afb9b20dc4e25e026f1946ec594d4292affdcd6b18",  # pragma: allowlist secret
    "specimen_taxonomy-v4.txt": "a8ea99d6fdbfb448b0dca443ebf5f41c01a37e20f1955bb099ebf693e771d07c",  # pragma: allowlist secret
    "specimen_geography-v4.txt": "3ffd8e07565727681f38fd08cdde29236dbdc7b156a3ea31d756b5709f80e05f",  # pragma: allowlist secret
    "specimen_temporal-v4.txt": "92a1663ce8b4df46b6d916eef2c1a368e1bcd1ca537f54caea6ac4d62c950cf9",  # pragma: allowlist secret
    "specimen_measurement-v4.txt": "2dc272a7ac098339563b81565d529c00d039fcb9c589b911006f75a8bdede63d",  # pragma: allowlist secret
    "specimen_parties-v4.txt": "a2a53dbbce6e52503b174d15cfcff5df930accd7c43f10184feb65e4fa5b9893",  # pragma: allowlist secret
    "specimen_collection-v4.txt": "56a93e32a7bfb2360d99abcba202d80868e27e6eee1ab93c86e43e1fb2cd32c5",  # pragma: allowlist secret
}
# Each role's pin digest on its v4 file (the digest of common-v1.txt, the v4 file and the owned-fields line).
V4_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "132aa9819c78ae43364f1a1be9e7e45454f8bf4be6019e14ea97b81f78203564",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "5afe4f2009c2534c2146cb7b1f12bd317e59c2f3070ca8eba9db600b1cd4e5cf",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "1764838c2795e22120bf946b806bedc79c293132cbfe0ebb1658063f76d60886",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "cd304517f75902dd88235f28d4c9cfc5cfb1e34418c85d182671a4454c8e890d",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "262edc021fdab5d2d09d391bab3a7d3a396d95266906ba4094427ba2fa8f36c1",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "3f0d6bf0a0e238b8d06c46f9491683bc8c8fcd011b34a7a56721a3ba07338d50",  # pragma: allowlist secret
}
# The committed research profile's digest for the synthetic ids org / coll (a production job's differs
# with its real organization and collection ids; the digest covers them).
PROFILE_DIGEST_ORG_COLL = "a7693f02f04e99eb97d30efa85085df05ac9c9367bf64f4d1eaf8e0e74d7c97d"  # pragma: allowlist secret


def flat(text):
    return " ".join(text.split())


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


def block(role):
    v3 = (ROOT / f"{role.value}-v3.txt").read_bytes()
    v4 = (ROOT / f"{role.value}-v4.txt").read_bytes()
    assert v4.startswith(v3)
    return v4[len(v3):].decode("ascii")


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_role_resolves_to_its_v4_file_at_the_missing_policy_version(role):
    assert ROLE_PROMPTS[role] == (f"{role.value}-v4.txt", MISSING_POLICY_PROMPT_VERSION)
    assert MISSING_POLICY_PROMPT_VERSION == "specialists-missing-policy-v4-2026-10-03"
    assert MISSING_POLICY_PROMPT_VERSION not in {RELATIONS_PROMPT_VERSION, GEOGRAPHY_PROMPT_VERSION,
        READING_CITATION_PROMPT_VERSION}
    prompt = pin(role)
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    expected = (common + (ROOT / f"{role.value}-v4.txt").read_text(encoding="utf-8")
                + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
    assert prompt.version == MISSING_POLICY_PROMPT_VERSION
    assert prompt.text == expected and prompt.digest == hashlib.sha256(expected.encode()).hexdigest()
    assert prompt.digest == V4_ROLE_DIGESTS[role]
    # The v4 text begins with the audited v3 text, which begins with the v2 text.
    v2 = (ROOT / f"{role.value}-v2.txt").read_text(encoding="utf-8")
    v3 = (ROOT / f"{role.value}-v3.txt").read_text(encoding="utf-8")
    assert prompt.text.startswith(common + v3) and v3.startswith(v2)


@pytest.mark.parametrize(("name", "sha256"), tuple(FILE_SHA256.items()))
def test_the_v3_files_stay_byte_identical_and_the_v4_files_are_pinned(name, sha256):
    raw = (ROOT / name).read_bytes()
    raw.decode("ascii")  # read_text must not depend on the locale's encoding
    assert hashlib.sha256(raw).hexdigest() == sha256


def test_the_committed_pins_carry_the_v4_versions_and_digests_and_the_profile_digest():
    profile = published_registry().resolve("insects").profile
    pins = build_committed_pins(profile, organization_id="org", collection_id="coll")
    assert {role: (row["version"], row["digest"]) for role, row in pins["prompts"].items()} == {
        str(role): (MISSING_POLICY_PROMPT_VERSION, value) for role, value in V4_ROLE_DIGESTS.items()}
    assert digest(committed_research_profile("org", "coll")) == PROFILE_DIGEST_ORG_COLL
    assert {row["profile_digest"] for row in pins["prompts"].values()} == {PROFILE_DIGEST_ORG_COLL}
    # The digest covers the ids: another organization and collection pin another profile digest.
    other = build_committed_pins(profile, organization_id="other-org", collection_id="other-coll")
    assert {row["profile_digest"] for row in other["prompts"].values()} != {PROFILE_DIGEST_ORG_COLL}


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_the_block_follows_the_v3_text_and_names_the_policy_and_the_reason(role):
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


# ---- the v3 reading-citation text and this block do not contradict each other ---------------------
@pytest.mark.parametrize("role", CITING_ROLES)
def test_a_value_resolved_from_a_lookup_still_cites_its_reading_and_a_waiting_policy_value_cites_none(role):
    """#257's producer block tells the role to cite the one reading a lookup-resolved value came from;
    this block tells it to return waiting_policy when nothing grounds a declared field. Both are in the
    live text, and the block says which applies to which value."""
    live = flat(pin(role).text)
    assert "Where the request has no assembly for the field that your interpretation read" in live
    assert "source_observation_id = its observation_id" in live
    assert "a waiting_policy value cites no reading" in flat(block(role))
    assert ("still cites its reading, as the producer block" in flat(block(role)))
    # The producer block comes first; the missing-policy block is the last text before the owned fields.
    text = pin(role).text
    assert text.index("Producer and literal without an assembly") < text.index("Missing policy (unstructured labels)")
    assert text.endswith(block(role) + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_a_waiting_policy_value_asks_for_no_literal_no_evidence_and_no_question(role):
    """Nothing the v3 blocks say about literals, evidence or human questions applies to a waiting_policy
    value: it carries none, so the v3 rules for them (one-line literal, evidence only on the question)
    are not asked of it."""
    text = flat(block(role))
    assert "no literal, parsed, normalized or authority_id, no evidence ids, no question" in text
    assert "value.state unresolved" in text
