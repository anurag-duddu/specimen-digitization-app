"""The v5 role prompts: the hand-over block (Lane P W5, 2026-10-04).

Each v5 file is its v4 file (#252: the missing-policy block) byte for byte followed by one block. The
taxonomy pins v7; geography pins v8, temporal pins v7 and measurement pins v9; parties and collection retain v5. The v5 block
tells a specialist what ``SpecialistRequest.organiser_candidates`` are (the ordinary extractor's stored values,
each located by trusted code or marked ungrounded), that a candidate is a proposal to verify against the raw
readings and never evidence, how a grounded candidate of the five literal fields resolves from its accepted
assembly, what to return for one the readings do not support, and that no assembly exists for the dates, the
elevations, taxon or the geography fields. The v1 to v4 files and common-v1.txt stay on disk byte for byte
(pinned in test_geography_prompt_v2.py, test_prompt_reading_citation_v3.py and test_prompt_missing_policy_v4.py).

The second half is the contradiction test: the v3 reading-citation block, the v4 missing-policy block and the v5
hand-over block are in one text, and each sentence of the v5 block that supersedes or limits an older one says so,
for every role that carries them. The statements are tied to the code they describe (the candidate statuses, the
fields that get an assembly), so the text cannot drift from it unnoticed.
"""
import hashlib
import re
from pathlib import Path

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.committed_pins import build_committed_pins
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, OrganiserCandidate, SpecialistRequest, SpecialistRole,
)
from specimen_digitization.research_harness.initial_requests import ASSEMBLY_FIELDS
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION, TAXONOMY_RECONCILIATION_PROMPT_VERSION, HANDOVER_PROMPT_VERSION, MISSING_POLICY_PROMPT_VERSION, QUALIFIED_PROMPT_VERSION,
    MEASUREMENT_EVIDENCE_PROMPT_VERSION, TEMPORAL_CONTEXT_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
HEADER = "Hand-over (organiser candidates): the request's organiser_candidates are the field\n"
# sha256 of each v5 file's bytes, and each role's pin digest on it (common-v1.txt, the v5 file, the owned-fields line).
V5_FILE_SHA256 = {
    "specimen_taxonomy-v5.txt": "45ae9af8ae5bdad7c2cc540379b7ca3922f6a4b13674cc8ece19e94efc98e19e",  # pragma: allowlist secret
    "specimen_geography-v5.txt": "b8e241d3523aca40b2830cbcce33f5ac49a1423227cb66caed33f68134ba121f",  # pragma: allowlist secret
    "specimen_temporal-v5.txt": "2f3e9a3d3951937fcdb4277191ef50e5f82caddeb72fb7e1f3e14cd6e3627d31",  # pragma: allowlist secret
    "specimen_measurement-v5.txt": "d62b27e9d0be31cbd52e2b03b1d0b2159c3ca903e206b7f9a1c8e5008b103648",  # pragma: allowlist secret
    "specimen_parties-v5.txt": "457488142949ff00d7434da71f3ea1813cf7287a0cd3727abdc3cd7ecf5f1baa",  # pragma: allowlist secret
    "specimen_collection-v5.txt": "ac669852e21819e365150ab43ff0aecd9d5952d2e72619ede8fee04f11563f01",  # pragma: allowlist secret
}
V5_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "476602d98b9b94d6e9e2876a973b970340ea8de125b66452989dad5b6874f5f3",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "47abfc0303ad550e1f1ca0fcda874c097e52ed7bec7eb9162c4b5b6f280a9d2f",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "bf1502f8c16cf5d01ac41f38221631d484b01cc128d02bc2991b75620294e3f6",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "e1f70e610c49112186eb5b3d3490797315f7941f7a64cc2a50fe79faa78ddf99",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "6395336fbc072a82e0b5ead1efc67ba11c9e6e04ded9756fc284ee1b50282e24",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "d8178716cb2f581fb33fc038c24b89c6f109ce6ae0be1b3c4c40b2883169c0b3",  # pragma: allowlist secret
}
V6_ROLE_DIGESTS = {
    SpecialistRole.GEOGRAPHY: "2627afa2841b834bc705daa57394eadd0d8d792807618655ca4b3569d880e13b",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "30744762b50a9ada2ea145bd24f8392b260696ccf94b6953a9b06bd71ead99cf",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "fe0cb50517fbfe284f4e2ce7493a5769e266349031d519c5a5a82d47b42b824d",  # pragma: allowlist secret
}
V7_ROLE_DIGESTS = {
    SpecialistRole.GEOGRAPHY: "71ab1cdee1cc836a3c3127d59d530fca03b4314091fbe7f7618fb6d01e073139",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "40a20bf9af6494c8a74a7df26cc56fd36fa36a3fe1b42d89c8675cdfbeed3307",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "e0b10dd8e01796863fba405022c6a4f2e4bb2818eff2af060ecfe0ce6478f50c",  # pragma: allowlist secret
}
GEOGRAPHY_V8_DIGEST = "30f5b580a78c53207d8f119f7b4afeaaed815c4b4ba79d8f426542f3adc09bba"  # pragma: allowlist secret
MEASUREMENT_V8_DIGEST = "06310d03a1419ac509d8c23b1c68340b8213ec008d67223dca1840309e64e7f7"  # pragma: allowlist secret
MEASUREMENT_V9_DIGEST = "65e3c30aeac9d55d165eb147bf36d88c208400238bb206d4361c1f348dc812e7"  # pragma: allowlist secret
TAXONOMY_V7_DIGEST = "ba33889e495c286e089b517366117c5167e788283d8a44eaae02ca14b3a6fc72"  # pragma: allowlist secret
# The roles that carry #257's producer block, and the ones whose own fields can get an assembly from the hand-over.
CITING_ROLES = (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.PARTIES, SpecialistRole.COLLECTION)
ASSEMBLY_ROLES = tuple(role for role in SpecialistRole if ASSEMBLY_FIELDS & set(ROLE_FIELDS[role]))
NO_ASSEMBLY_ROLES = tuple(role for role in SpecialistRole if role not in ASSEMBLY_ROLES)


def flat(text):
    return " ".join(text.split())


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


def appended_or_frozen_v5_text(role):
    # Coherent measurement v9 and temporal v7 replace the obsolete chain.
    # Keep auditing measurement's frozen v7 and temporal's frozen v5 here.
    if role == SpecialistRole.MEASUREMENT:
        return (ROOT / "specimen_measurement-v7.txt").read_text()
    if role == SpecialistRole.TEMPORAL:
        return ((ROOT / "common-v1.txt").read_text() + "\n"
            + (ROOT / f"{role.value}-v5.txt").read_text()
            + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
    return pin(role).text


def block(role):
    v4 = (ROOT / f"{role.value}-v4.txt").read_bytes()
    v5 = (ROOT / f"{role.value}-v5.txt").read_bytes()
    assert v5.startswith(v4)
    return v5[len(v4):].decode("ascii")


# ---------------------------------------------------------------------------- the table, the files, the pins
def test_table_pins_v5_taxonomy_v7_geography_v8_temporal_v7_and_measurement_v9():
    assert HANDOVER_PROMPT_VERSION == "specialists-handover-v5-2026-10-04"
    assert HANDOVER_PROMPT_VERSION != MISSING_POLICY_PROMPT_VERSION
    assert QUALIFIED_PROMPT_VERSION == "specialists-qualified-event-v6-2026-10-04"
    assert dict(ROLE_PROMPTS) == {role: (f"{role.value}-v{8 if role == SpecialistRole.GEOGRAPHY else 9 if role == SpecialistRole.MEASUREMENT else 7 if role in V7_ROLE_DIGESTS or role == SpecialistRole.TAXONOMY else 6 if role in V6_ROLE_DIGESTS else 5}.txt",
        GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION if role == SpecialistRole.GEOGRAPHY else
        MEASUREMENT_EVIDENCE_PROMPT_VERSION if role == SpecialistRole.MEASUREMENT else
        TEMPORAL_CONTEXT_PROMPT_VERSION if role == SpecialistRole.TEMPORAL else
        TAXONOMY_RECONCILIATION_PROMPT_VERSION if role == SpecialistRole.TAXONOMY else
        QUALIFIED_PROMPT_VERSION if role in V6_ROLE_DIGESTS else HANDOVER_PROMPT_VERSION)
        for role in SpecialistRole}


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_each_v5_file_remains_immutable_and_each_active_role_resolves_to_its_pinned_file(role):
    prompt = pin(role)
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    v5 = (ROOT / f"{role.value}-v5.txt").read_text(encoding="utf-8")
    suffix = "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n"
    historical = common + v5 + suffix
    assert hashlib.sha256(historical.encode()).hexdigest() == V5_ROLE_DIGESTS[role]
    name, version = ROLE_PROMPTS[role]
    active = (ROOT / name).read_text(encoding="utf-8")
    expected = common + active + suffix
    assert prompt.version == version and prompt.text == expected
    assert prompt.digest == hashlib.sha256(expected.encode()).hexdigest()
    assert prompt.digest == (GEOGRAPHY_V8_DIGEST if role == SpecialistRole.GEOGRAPHY else
        MEASUREMENT_V9_DIGEST if role == SpecialistRole.MEASUREMENT else
        TAXONOMY_V7_DIGEST if role == SpecialistRole.TAXONOMY else
        V7_ROLE_DIGESTS.get(role, V6_ROLE_DIGESTS.get(role, V5_ROLE_DIGESTS[role])))
    v4 = (ROOT / f"{role.value}-v4.txt").read_text(encoding="utf-8")
    assert v5.startswith(v4) and v5 != v4
    assert block(role).startswith(HEADER) and block(role).endswith("\n")
    # The pinned text still ends with the block and then the owned fields.
    if role == SpecialistRole.MEASUREMENT:
        assert (ROOT / "specimen_measurement-v7.txt").read_text().startswith(v5)
    elif role == SpecialistRole.TEMPORAL:
        assert "Complete collecting dates need no literal Collected: heading" in active
    elif role in V6_ROLE_DIGESTS or role == SpecialistRole.TAXONOMY:
        assert active.startswith(v5)
    else:
        assert prompt.text.endswith(block(role) + suffix)


@pytest.mark.parametrize(("name", "sha256"), tuple(V5_FILE_SHA256.items()))
def test_the_v5_files_are_ascii_and_pinned(name, sha256):
    raw = (ROOT / name).read_bytes()
    raw.decode("ascii")  # read_text must not depend on the locale's encoding
    assert hashlib.sha256(raw).hexdigest() == sha256


def test_the_committed_pins_carry_the_active_versions_and_digests():
    pins = build_committed_pins(published_registry().resolve("insects").profile, organization_id="org",
        collection_id="coll")
    assert {role: (row["version"], row["digest"]) for role, row in pins["prompts"].items()} == {
        str(role): (GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION, GEOGRAPHY_V8_DIGEST) if role == SpecialistRole.GEOGRAPHY else
            (MEASUREMENT_EVIDENCE_PROMPT_VERSION, MEASUREMENT_V9_DIGEST) if role == SpecialistRole.MEASUREMENT else
            (TEMPORAL_CONTEXT_PROMPT_VERSION, V7_ROLE_DIGESTS[role]) if role == SpecialistRole.TEMPORAL else
            (TAXONOMY_RECONCILIATION_PROMPT_VERSION, TAXONOMY_V7_DIGEST) if role == SpecialistRole.TAXONOMY else
            (QUALIFIED_PROMPT_VERSION, V6_ROLE_DIGESTS[role]) if role in V6_ROLE_DIGESTS else
            (HANDOVER_PROMPT_VERSION, V5_ROLE_DIGESTS[role]) for role in SpecialistRole}


# ---------------------------------------------------------------------------- what the block says
@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_every_block_opens_with_the_same_account_of_a_candidate(role):
    head = flat(block(role))
    for sentence in (
        'each with source "extractor", the literal it wrote, a status and a reason',
        "Trusted code computes the span and the status; the extractor supplies neither.",
        "A candidate is a proposal to verify, never evidence.",
        "The evidence is the raw readings in fragments[]",
        "and, for a grounded candidate, its accepted assembly.",
        "can misread a line, invent a value or assign a line to the wrong field.",
        "find its literal in the reading it names, read the lines around it and the other reader's reading, and "
        "reject it if the readings do not support it as the value of that field.",
        "it is a hint only, it names no span, assembly or evidence, and it is never a value.",
    ):
        assert sentence in head, (role, sentence)
    # The opening paragraph is one text for all six roles.
    first = block(SpecialistRole.TAXONOMY)
    assert block(role).startswith(first[:first.index("taxon: the candidate")])


def test_the_statuses_the_text_names_are_the_statuses_of_the_contract_and_its_fields():
    statuses = set(OrganiserCandidate.model_fields["status"].annotation.__args__)
    assert statuses == {"grounded", "located", "ungrounded"}
    text = flat(block(SpecialistRole.COLLECTION))
    for status in statuses:
        assert f"Status {status}:" in text
    # Every identifier the block uses for a candidate or its request is a field of the contract.
    names = {"organiser_candidates", "assembly_id", "event_id", "evidence_ids", "region_id", "observation_id",
        "source", "status", "reason", "literal", "start", "end"}
    assert {"organiser_candidates"} <= set(SpecialistRequest.model_fields)
    assert names - {"organiser_candidates"} <= set(OrganiserCandidate.model_fields)
    for role in SpecialistRole:
        used = set(re.findall(r"\b(assembly_id|event_id|region_id|observation_id|evidence_ids)\b", block(role)))
        assert used <= set(OrganiserCandidate.model_fields) | {"evidence_ids"}, role


@pytest.mark.parametrize("role", (SpecialistRole.PARTIES, SpecialistRole.COLLECTION))
def test_a_grounded_candidate_resolves_from_its_assembly_with_the_fields_publication_needs(role):
    text = flat(block(role))
    for sentence in (
        "A grounded candidate that the readings support resolves from its accepted assembly:",
        "work_state resolved, assembly_ids = [its assembly_id], event_id = its event_id,",
        "evidence_ids = the assembly's evidence_ids (on the resolution and on value.evidence_ids),",
        "value.state supported, value.literal = the assembly's interpreted_text copied exactly, value.parsed and "
        "value.normalized the same text,",
        'value.evidence_relations mapping each evidence id to "supports",',
        "value.verbatim_by_observation = {the candidate's observation_id: that reading's observation_text, copied "
        "character for character} and value.settled_observation_ids = [that observation_id].",
        "The publication grounds value.literal in that reading, so set both reading fields.",
    ):
        assert sentence in text, (role, sentence)


def test_the_shape_paragraph_is_one_text_in_parties_and_collection():
    def shape(role):
        text = block(role)
        start = text.index("A grounded candidate that the readings support resolves from its accepted assembly:")
        return text[start:text.index("fields.\n", start) + len("fields.\n")]
    assert shape(SpecialistRole.PARTIES) == shape(SpecialistRole.COLLECTION)


def test_the_collection_block_names_the_catalog_rule_and_the_ways_the_extractor_errs():
    text = flat(block(SpecialistRole.COLLECTION))
    assert ("For fmnh_ins_number value.parsed and value.normalized are instead the catalog digits by the rule above, "
            "and a candidate that rule refuses is not resolved; the other three keep the same text in all three.") in text
    assert ("The extractor can file the catalog prefix (FMNHINS), a catalog number, or a slide or preparation code under "
            "collection_code, and a locality or a specimen note under habitat or collection_method, and the validator "
            "refuses only the catalog prefix as a collection code and a code-shaped habitat or method") in text
    assert "resolve one only if the readings show that the line is what the field names." in text
    assert "A candidate for verbatim_dts is no assembly: verbatim_dts is unchanged" in text


def test_the_parties_block_says_the_validator_cannot_tell_a_collector_from_another_name():
    # identified_by_irn stays the v4 block's text ("identified_by_irn is unchanged: the declared exception.").
    assert "identified_by_irn is unchanged: the declared exception." in flat(pin(SpecialistRole.PARTIES).text)
    text = flat(block(SpecialistRole.PARTIES))
    assert "not a determiner, a preparer or another role, a place or a code" in text
    assert "checks only that the value has no digit and some letters, so whether the line is the collector is your check" in text


@pytest.mark.parametrize("role", (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT))
def test_dates_and_elevations_get_no_assembly_and_stay_waiting_policy(role):
    text = flat(block(role))
    assert f"the hand-over builds no assembly for {'a date' if role == SpecialistRole.TEMPORAL else 'an elevation'}" in text
    assert "which no tool you have returns" in text
    assert "the missing-policy rule above applies: return waiting_policy" in text
    assert "say in the reason which reading and line you read (copied character for character)" in text
    # Nothing here tells the model to resolve, cite an assembly it was not given, or call a utility.
    assert "work_state resolved" not in text and "assembly_ids = [" not in text and "invoke_utility" not in text


def test_taxonomy_and_geography_use_the_candidate_as_a_hint_and_the_lookup_decides():
    taxonomy, geography = flat(block(SpecialistRole.TAXONOMY)), flat(block(SpecialistRole.GEOGRAPHY))
    assert "the hand-over builds no assembly for it, because a taxon resolves from GBIF and not from a literal" in taxonomy
    assert ("confirm that the readings print the candidate before you send it, and never send a candidate they do "
            "not print. GBIF decides; a candidate is no evidence for or against a match.") in taxonomy
    assert "the hand-over builds no assembly for it, because these fields resolve from GEOLocate" in geography
    assert "and never query a place the readings do not print" in geography
    assert "The county and city rules above are unchanged, and a failed lookup is still waiting_source." in geography
    assert "The lookup decides; a candidate is no evidence for or against a result." in geography
    for text in (taxonomy, geography):
        assert ("If a candidate is rejected, ungrounded or cannot be verified, ignore it and work from what the "
                "readings print, by the rules above, naming in the reason the reading and the line (copied "
                "character for character) you read. Never send, propose or complete a value from outside the "
                "readings.") in text


@pytest.mark.parametrize("role", (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
                                  SpecialistRole.COLLECTION))
def test_a_literal_role_that_rejects_a_candidate_returns_the_unresolved_state_and_names_a_value_only_in_the_reason(role):
    text = flat(block(role))
    assert ("If a candidate is rejected, ungrounded or cannot be verified, it is not the value: return the field's "
            "own unresolved state as above. You may name a different value only from the raw readings: write it in "
            "the reason with the reading's observation_id and the line copied character for character. It cannot "
            "become the value without an accepted assembly, so the field stays unresolved and a person decides. "
            "Never invent a value and never complete one from outside the readings.") in text
    assert "waiting_source" not in text and "waiting_human" not in text


# ---------------------------------------------------------------------------- no contradiction among v3, v4 and v5
@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_the_legacy_v3_v4_v5_chain_keeps_its_order_in_retained_or_active_text(role):
    text = appended_or_frozen_v5_text(role)
    assert text.index("Human question evidence (publication):") < text.index("Missing policy (unstructured labels):")
    assert text.index("Missing policy (unstructured labels):") < text.index("Hand-over (organiser candidates):")
    assert text.count("Hand-over (organiser candidates):") == 1


@pytest.mark.parametrize("role", (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.PARTIES,
                                  SpecialistRole.COLLECTION))
def test_the_v4_claim_that_the_request_holds_no_accepted_assembly_is_superseded_where_it_is_no_longer_true(role):
    """v4 says: 'No rule yet qualifies an event or an assembly from unstructured label text, so the request can hold
    no accepted assembly for ...'. The hand-over makes that false for the fields in ASSEMBLY_FIELDS, so exactly the
    roles that own such a field replace the sentence for exactly those fields; the others keep it true."""
    live = flat(appended_or_frozen_v5_text(role))
    assert "can hold no accepted assembly" in live  # the v4 sentence is still in the text
    mine = {str(key) for key in ASSEMBLY_FIELDS & set(ROLE_FIELDS[role])}
    text = flat(block(role))
    if role in ASSEMBLY_ROLES:
        replaced = re.search(r"This replaces the sentence above that says the request can hold no accepted assembly "
                             r"for (.+?): for a grounded candidate it holds one\.", text)
        assert replaced, role
        assert set(re.findall(r"[a-z_]+", replaced[1])) - {"and"} == mine
    else:
        assert not mine and "This replaces the sentence above that says the request can hold no accepted assembly" not in text
        assert "builds no assembly" in text


def test_the_roles_that_get_an_assembly_are_parties_and_collection_and_the_fields_are_those_the_validator_resolves():
    assert set(ASSEMBLY_ROLES) == {SpecialistRole.PARTIES, SpecialistRole.COLLECTION}
    assert set(NO_ASSEMBLY_ROLES) == {SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.TEMPORAL,
        SpecialistRole.MEASUREMENT}
    assert ASSEMBLY_FIELDS == {FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE, FieldKey.HABITAT,
        FieldKey.COLLECTION_METHOD, FieldKey.COLLECTORS}


@pytest.mark.parametrize("role", CITING_ROLES)
def test_not_both_is_about_a_lookup_and_the_literal_from_an_assembly_is_the_stated_exception(role):
    """#257: 'Name assemblies or cite a reading, not both; a lookup with neither has no producer'. The two roles
    whose v5 block has a literal read from an assembly set verbatim_by_observation beside assembly_ids, and say that
    the 'not both' concerns the producer of a lookup; the two lookup roles resolve from a lookup and cite their
    reading as the producer block says, with no assembly."""
    live = flat(pin(role).text)
    assert "Name assemblies or cite a reading, not both" in live
    text = flat(block(role))
    if role in ASSEMBLY_ROLES:
        assert ('The producer block above is for a value without an assembly, and its "not both" is about the '
                "producer of a lookup; a literal read from an accepted assembly names the assembly and also these two "
                "reading fields.") in text
    else:
        assert "still cites its reading as the producer block above says" in text
        assert "assembly_ids = [" not in text and "verbatim_by_observation" not in text


@pytest.mark.parametrize("role", NO_ASSEMBLY_ROLES)
def test_no_v5_block_tells_a_role_without_an_assembly_to_cite_one_or_to_resolve_from_a_candidate(role):
    text = flat(block(role))
    assert "work_state resolved" not in text and "assembly_ids = [" not in text
    assert "value.literal" not in text and "value.verbatim_by_observation" not in text


def test_the_v4_rules_the_v5_text_leans_on_are_still_in_the_live_text():
    """N1/N4 query rules, the outage rule and the waiting_policy shape (#252 v4) are all still there, once."""
    taxonomy = flat(pin(SpecialistRole.TAXONOMY).text)
    for sentence in (
        "A lookup's query_text must be a scientific name the query builder can send",
        "A name in doubt is not sent either: return waiting_policy and make no lookup.",
        "A common name, or any text that is not a scientific name, is not a taxon the readings name",
        "If a lookup failed, timed out, was rate limited, or failed with an authentication or authorization error, "
        "return waiting_source as above",
    ):
        assert taxonomy.count(sentence) == 1, sentence
    geography = flat(pin(SpecialistRole.GEOGRAPHY).text)
    assert geography.count("If a GEOLocate lookup for the field failed or timed out") == 1
    assert geography.count("there is nothing to look up and you do not send such a query") == 1
    for role in SpecialistRole:
        shape = ("no literal, parsed, normalized, authority_id, evidence IDs or human question"
            if role == SpecialistRole.TEMPORAL else
            "no literal, parsed, normalized or authority_id, no evidence ids, no question")
        assert flat(pin(role).text).count(shape) == 1


@pytest.mark.parametrize("role", tuple(SpecialistRole))
def test_a_waiting_policy_value_still_asks_for_no_literal_and_the_block_adds_no_literal_to_it(role):
    """v4: a waiting_policy value has no literal, parsed, normalized, evidence ids or question. The v5 block asks for
    value.literal only on a resolved value (parties, collection) and tells the other roles to name a value in the
    reason; so no text asks a waiting_policy value to carry one."""
    text = flat(block(role))
    rejection = text[text.index("If a candidate is rejected"):]
    # value.literal is asked for only in the resolved-from-assembly paragraph (parties, collection), never on the
    # rejection path, and never in a role without an assembly.
    assert "value.literal" not in rejection
    assert ("value.literal" in text) == (role in ASSEMBLY_ROLES)
    if role in ASSEMBLY_ROLES:
        assert text.index("work_state resolved") < text.index("value.literal") < text.index("If a candidate is rejected")
    assert "value.state unresolved" not in text  # the shape of an unresolved value stays the v4 block's text alone
    assert "value.state unresolved" in flat(pin(role).text)
