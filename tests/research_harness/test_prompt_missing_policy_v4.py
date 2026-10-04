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

The live table moved on to the v5 files (each the v4 file followed by the hand-over block,
test_prompt_handover_v5.py), so the v4 files and their pin digests are the audit record here and
the live text begins with the v4 text.
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
    GEOGRAPHY_PROMPT_VERSION, HANDOVER_PROMPT_VERSION, MISSING_POLICY_PROMPT_VERSION,
    READING_CITATION_PROMPT_VERSION, RELATIONS_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
HEADER = "Missing policy (unstructured labels): the pinned profile declares missing_policy\n"
REASON = f'"missing_policy:{UNQUALIFIED_LABEL_POLICY}'
# The literal fields' roles: no source is connected for them, so there is no failure to report.
LITERAL_ROLES = (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
    SpecialistRole.COLLECTION)
# The roles whose v3 text (#257) carries the producer block: all four that have the v2 sentence about a lookup's
# producer. Only taxonomy and geography have a source a value can cite a lookup of.
CITING_ROLES = (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.PARTIES, SpecialistRole.COLLECTION)
LOOKUP_ROLES = (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY)
NO_LOOKUP_ROLES = (SpecialistRole.PARTIES, SpecialistRole.COLLECTION)
# sha256 of each file's bytes: the v3 files as #257 added them (audit), the v4 files as added here.
FILE_SHA256 = {
    "specimen_taxonomy-v3.txt": "8c251604bd7e625e5f2ad88f723e233c749ec26b6d3f09a9ce0677d5b9f93963",  # pragma: allowlist secret
    "specimen_geography-v3.txt": "1f9c6a5762e1873228b829f0f334f547c29d97a59c51831c694fe8f4190f4795",  # pragma: allowlist secret
    "specimen_temporal-v3.txt": "dddedbcab47180c728f0538b2359c93972c8ec540a9ae9dfa6f4d79202a9b38f",  # pragma: allowlist secret
    "specimen_measurement-v3.txt": "9fcc4eb9d206b597cfbc0e203c6d57c2c4c8e578c403c939938baeee516b5480",  # pragma: allowlist secret
    "specimen_parties-v3.txt": "752b3c106e8942840eb0e6be7540d286f8ae6724d962c018e67fa0d0cde9011f",  # pragma: allowlist secret
    "specimen_collection-v3.txt": "40d6979ed0a375987fb696afb9b20dc4e25e026f1946ec594d4292affdcd6b18",  # pragma: allowlist secret
    "specimen_taxonomy-v4.txt": "5f722a49eaf703dbb96fdca08d8b2d5b0dd29a4544dffb050a67ef73805caa27",  # pragma: allowlist secret
    "specimen_geography-v4.txt": "dc11acc47becdecedb7f329f65fdbbdd5d07abdd1833b38e5812a6568c2a00b4",  # pragma: allowlist secret
    "specimen_temporal-v4.txt": "92a1663ce8b4df46b6d916eef2c1a368e1bcd1ca537f54caea6ac4d62c950cf9",  # pragma: allowlist secret
    "specimen_measurement-v4.txt": "2dc272a7ac098339563b81565d529c00d039fcb9c589b911006f75a8bdede63d",  # pragma: allowlist secret
    "specimen_parties-v4.txt": "c8d20d3a8eaa81e7cd53ca9f7c9ee81ebd01ddc933067a3d6591e6b3b9fed4be",  # pragma: allowlist secret
    "specimen_collection-v4.txt": "04a82c819a2a9196621a18422259a302425cb73d5bbbec986e531828d6cbe20b",  # pragma: allowlist secret
}
# Each role's pin digest on its v4 file (the digest of common-v1.txt, the v4 file and the owned-fields line).
V4_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "4e6fc532dd512e91f0c6859ab32efd0d14a3bf65ce9843cf41e183a13b84a4c5",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "e9cef2c07f305e20010bee859d972c33f22c09b540b9288d76fec7fa7c182ebe",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "1764838c2795e22120bf946b806bedc79c293132cbfe0ebb1658063f76d60886",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "cd304517f75902dd88235f28d4c9cfc5cfb1e34418c85d182671a4454c8e890d",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "d465ddd68fa218068eeb2c6cca3419034fde5253675c96fd270b5e608867fc3a",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "cfe83bcbe4fcf821f46ada2977810b916f6dfd824b22738f3633d880bdff881d",  # pragma: allowlist secret
}
# The committed research profile's digest for the synthetic ids org / coll (a production job's differs
# with its real organization and collection ids; the digest covers them).
PROFILE_DIGEST_ORG_COLL = "a7693f02f04e99eb97d30efa85085df05ac9c9367bf64f4d1eaf8e0e74d7c97d"  # pragma: allowlist secret


def flat(text):
    return " ".join(text.split())


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


def v4_text(role):
    """The v4 pin text (common-v1.txt, the v4 file, the owned-fields line), as it was live."""
    return ((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
            + (ROOT / f"{role.value}-v4.txt").read_text(encoding="utf-8")
            + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")


def block(role):
    v3 = (ROOT / f"{role.value}-v3.txt").read_bytes()
    v4 = (ROOT / f"{role.value}-v4.txt").read_bytes()
    assert v4.startswith(v3)
    return v4[len(v3):].decode("ascii")


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_role_has_its_v4_file_at_the_missing_policy_version_and_the_live_table_moved_on(role):
    assert MISSING_POLICY_PROMPT_VERSION == "specialists-missing-policy-v4-2026-10-03"
    assert MISSING_POLICY_PROMPT_VERSION not in {RELATIONS_PROMPT_VERSION, GEOGRAPHY_PROMPT_VERSION,
        READING_CITATION_PROMPT_VERSION}
    # The live table is the v5 files (test_prompt_handover_v5.py); the v4 pin is audited from the file.
    assert ROLE_PROMPTS[role] == (f"{role.value}-v5.txt", HANDOVER_PROMPT_VERSION)
    text = v4_text(role)
    assert hashlib.sha256(text.encode()).hexdigest() == V4_ROLE_DIGESTS[role]
    # The v4 text begins with the audited v3 text, which begins with the v2 text; the live text begins with it.
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    v2 = (ROOT / f"{role.value}-v2.txt").read_text(encoding="utf-8")
    v3 = (ROOT / f"{role.value}-v3.txt").read_text(encoding="utf-8")
    assert text.startswith(common + v3) and v3.startswith(v2)
    v4 = (ROOT / f"{role.value}-v4.txt").read_text(encoding="utf-8")
    assert pin(role).text.startswith(common + v4)


@pytest.mark.parametrize(("name", "sha256"), tuple(FILE_SHA256.items()))
def test_the_v3_files_stay_byte_identical_and_the_v4_files_are_pinned(name, sha256):
    raw = (ROOT / name).read_bytes()
    raw.decode("ascii")  # read_text must not depend on the locale's encoding
    assert hashlib.sha256(raw).hexdigest() == sha256


def test_the_committed_research_profile_digest_is_the_v4_one_and_the_pins_carry_it():
    """The v5 prompts move no profile digest: every prompt pin still carries the missing-policy profile's digest
    (the pins' prompt versions and digests are pinned in test_prompt_handover_v5.py)."""
    profile = published_registry().resolve("insects").profile
    pins = build_committed_pins(profile, organization_id="org", collection_id="coll")
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


def test_taxonomy_keeps_waiting_source_for_a_failed_lookup_and_sets_a_policy_blocked_source_aside():
    text = flat(block(SpecialistRole.TAXONOMY))
    assert ("If a lookup failed, timed out, was rate limited, or failed with an authentication or authorization "
            "error, return waiting_source as above, even beside a no_match from another source: that is "
            "operational and blocks the record.") in text
    # The code treats policy_blocked as no outage (agents.SOURCE_OUTAGES): the text must say the same.
    assert ("A policy_blocked answer (an unqualified source such as BugGuide, or a refused query text) is not "
            "an outage: set that source aside.") in text
    assert "refused, or its source is not configured" not in text
    # The engine retries only operational_failed and retry_scheduled fields (engine.py), never a
    # waiting_source, so the prompt does not say it is retried.
    assert "retried" not in text


def test_the_taxonomy_rule_is_not_vacuously_true_when_no_lookup_was_made():
    """T2 of the review: 'every lookup you made completed without a match' holds when none was made. A
    named taxon is looked up first, and waiting_policy follows only a completed lookup with no accepted match."""
    text = flat(block(SpecialistRole.TAXONOMY))
    assert "When the readings name no taxon, return work_state waiting_policy for taxon." in text
    assert ("When they name one, look it up first (GBIF decides); return waiting_policy only after at least one "
            "lookup completed and none produced an accepted match (no_match, or a tie that no distinguishing "
            "evidence breaks).") in text
    assert "every taxonomy lookup you made" not in text
    # The v2 example asks which taxon was intended, a question that cannot be built (HumanQuestion needs
    # exhausted coverage; a GBIF search is SEARCHED), so the block replaces it.
    v2 = (ROOT / "specimen_taxonomy-v2.txt").read_text(encoding="utf-8")
    assert "ask which taxon was intended" in flat(v2)
    assert ("This replaces the example above that asks which taxon was intended: a completed search cannot be "
            "put to a person as a question (a human question needs exhausted coverage), so a tie is "
            "waiting_policy.") in text


def test_geography_keeps_waiting_source_for_a_failed_lookup_and_a_policy_blocked_place_defect_is_nothing_to_look_up():
    text = flat(block(SpecialistRole.GEOGRAPHY))
    assert ("If a GEOLocate lookup for the field failed or timed out (an HTTP error, a rate limit, a malformed "
            "answer), abstain with waiting_source as above: that is operational and blocks the record.") in text
    # For county outside the USA the lookup is refused (policy_blocked): that is the first rule's case.
    assert ('A policy_blocked answer naming a place-text defect (for county, a country outside the USA) is the '
            '"nothing to look up" case: waiting_policy.') in text
    assert "failed, timed out or was refused" not in text
    assert "This replaces the waiting_source instruction above for that case only" in text


def test_a_taxon_lookup_is_only_for_a_name_the_query_builder_can_send():
    """N1 of the second review: 'look it up first' sent GBIF a name the query builder rejects (all capitals, a
    lower-case start, 'cf.', a question mark): no request is sent and the record ends
    research_worker_custody_requires_reconciliation. The block names exactly the shapes the builder refuses."""
    text = flat(block(SpecialistRole.TAXONOMY))
    assert ("A lookup's query_text must be a scientific name the query builder can send: a capitalised genus, "
            "optionally followed by lower-case epithets and an author (Genus, Genus species); write a name that "
            "the label prints in capitals that way.") in text
    assert ("The builder sends nothing for a name that begins with a lower-case word or a qualifier such as cf., "
            "or that has a question mark on the genus, and a lookup it cannot send holds the record.") in text
    # N4 of the third review: a name in doubt (cf., aff., a question mark before or on the genus) is a shape the
    # builder refuses, and the text must say what to return for it, not only for common names.
    assert "A name in doubt is not sent either: return waiting_policy and make no lookup." in text
    assert text.index("holds the record. A name in doubt") < text.index("A common name, or any text")
    assert ("A common name, or any text that is not a scientific name, is not a taxon the readings name: "
            "return waiting_policy and make no lookup.") in text


# What lookup.scientific_name (the query builder behind GBIF's request) sends for each shape the text names.
SENDABLE = ("Camponotus", "Camponotus sp.", "Danaus plexippus", "Danaus plexippus Linnaeus",
    "Danaus plexippus (Linnaeus, 1758)", "Carabidae")
NOT_SENDABLE = ("CAMPONOTUS", "CAMPONOTUS SP.", "unknown beetle", "danaus plexippus", "cf. Danaus", "Danaus?",
    "cf. Danaus plexippus", "aff. Danaus plexippus", "nr. Danaus plexippus", "? Danaus plexippus")


@pytest.mark.parametrize("literal", SENDABLE)
def test_the_shapes_the_taxonomy_text_allows_are_sent(literal):
    from specimen_digitization.application.lookup import scientific_name
    name = scientific_name(literal)
    assert name is not None and name.genus and name.query[0].isupper()


@pytest.mark.parametrize("literal", NOT_SENDABLE)
def test_the_shapes_the_taxonomy_text_refuses_send_nothing(literal):
    """The builder returns no name, or a name with no genus, and sources.SourceBroker raises before any request
    (no captured response, so the record is held): the text must keep a model from sending them."""
    from specimen_digitization.application.lookup import scientific_name
    name = scientific_name(literal)
    assert name is None or not name.genus


def test_geography_does_not_send_a_query_for_nothing_to_look_up():
    """N2 of the second review: a refused (policy_blocked) result is receiptless, and a receiptless result in a
    role whose fields publish stops its publications (canonical_local_utility_unproved). The first rule keeps a
    model from sending the query at all."""
    text = flat(block(SpecialistRole.GEOGRAPHY))
    assert ("there is nothing to look up and you do not send such a query: return work_state waiting_policy "
            "for that field") in text


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
def test_the_v3_producer_block_and_the_v4_block_are_both_in_the_live_text_and_in_that_order(role):
    """#257's producer block is in all four lookup roles; the v4 block follows it and is the last text of the v4 pin
    (the live v5 text appends the hand-over block after it)."""
    live = flat(pin(role).text)
    assert "Where the request has no assembly for the field that your interpretation read" in live
    assert "source_observation_id = its observation_id" in live
    text = v4_text(role)
    assert text.index("Producer and literal without an assembly") < text.index("Missing policy (unstructured labels)")
    assert text.endswith(block(role) + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
    assert pin(role).text.index(block(role)) > pin(role).text.index("Producer and literal without an assembly")
    assert "a waiting_policy value cites no reading" in flat(block(role)) or role in NO_LOOKUP_ROLES


@pytest.mark.parametrize("role", LOOKUP_ROLES)
def test_a_value_resolved_from_a_lookup_still_cites_its_reading_and_a_waiting_policy_value_cites_none(role):
    """Taxonomy and geography can resolve a value from a lookup: it cites its reading as the producer block
    says, and a waiting_policy value cites none."""
    text = flat(block(role))
    assert "still cites its reading, as the producer block" in text
    assert "a waiting_policy value cites no reading" in text


@pytest.mark.parametrize("role", NO_LOOKUP_ROLES)
def test_parties_and_collection_are_told_the_producer_block_does_not_let_them_resolve_without_an_assembly(role):
    """T1 of the review: #257's block shows how to cite a reading for a value without an assembly (and says
    value.literal is then one line of that reading); the v4 block says never to resolve these fields from
    reading text without an assembly, and the validator agrees (a literal field needs assembly_ids,
    evidence.py). The block says which applies, so a model that follows the producer block does not resolve a
    field the validator would refuse (a refusal fails the whole role)."""
    text = flat(block(role))
    assert "Never resolve" in text
    assert ("The producer block above applies to a value that cites a lookup. None of these fields has a lookup, "
            "and a literal without an accepted assembly is refused, so it does not let you resolve them from a "
            "reading.") in text
    # Taxonomy's and geography's sentence about resolved lookup values is not in these two.
    assert "still cites its reading" not in text


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_a_waiting_policy_value_asks_for_no_literal_no_evidence_and_no_question(role):
    """Nothing the v3 blocks say about literals, evidence or human questions applies to a waiting_policy
    value: it carries none, so the v3 rules for them (one-line literal, evidence only on the question)
    are not asked of it."""
    text = flat(block(role))
    assert "no literal, parsed, normalized or authority_id, no evidence ids, no question" in text
    assert "value.state unresolved" in text
