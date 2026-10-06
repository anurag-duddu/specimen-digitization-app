"""Geography's historian prompt v2 and the per-role prompt table (owner G-geo-1..3, 2026-10-03).

Geography moves to its historian prompt. The other five roles move to v2 files
that are their v1 files followed by the G23 relation rule (Lane H, 2026-10-03;
tests/research_harness/test_prompt_relations_v2.py checks that text). The v1
files stay byte-identical on disk. The v1 role digests below were computed from
main 2f85b429 before any v2 was wired.

All six roles then move to v3 files, each its v2 file followed by the reading
citation and human question evidence blocks (Lane P G3, 2026-10-03;
tests/research_harness/test_prompt_reading_citation_v3.py checks that text), and to
v4 files, each its v3 file followed by the missing-policy block (Lane P F6;
tests/research_harness/test_prompt_missing_policy_v4.py), and to v5 files, each its v4
file followed by the hand-over block (Lane P W5; test_prompt_handover_v5.py). The v2, v3
and v4 files stay byte-identical on disk; the v2 file and role digests are pinned below as
the audit record, and the live pins are v5.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import FieldKey, ROLE_FIELDS, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROMPT_VERSION, GEOGRAPHY_HISTORY_PROMPT_VERSION, MISSING_POLICY_PROMPT_VERSION, PROMPT_VERSION,
    READING_CITATION_PROMPT_VERSION, RELATIONS_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)
from specimen_digitization.research_harness.sources import insects_registry

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
V1_FILES = {
    "common-v1.txt": "bafa2b52bc8088de23ef78d4403f98edf9f1c7ccd4aaa7d15d0caaed1f21c367",  # pragma: allowlist secret
    "specimen_geography-v1.txt": "6a7ccad2a8c2d28b13aa7196574f15f273e0ca62b0cd3917e2484ec22cf21a09",  # pragma: allowlist secret
    "specimen_taxonomy-v1.txt": "be7c4b194f55b9cd456f64294bc6b6d26dd30e41934e6ec62170417bc1addb42",  # pragma: allowlist secret
    "specimen_temporal-v1.txt": "a755e25fedd87ff7e959ed20f152de90bf81e74d0735dc7c4c384381a43f7744",  # pragma: allowlist secret
    "specimen_measurement-v1.txt": "8fea86f2905c36379f77600eea3d39ba78507196e2a38c4e8deba0325df68bff",  # pragma: allowlist secret
    "specimen_parties-v1.txt": "e50cd25a19d1b3be0ad06e9c09e7cbfb0900e70dce9d1b74d7c8ae01751ea642",  # pragma: allowlist secret
    "specimen_collection-v1.txt": "3c8fb750b35374bb1173b843ff5c4155febd6d880b9859d7a79904e28756c187",  # pragma: allowlist secret
}
GEOGRAPHY_V1_DIGEST = "9bba8680c505de86e5327a886d1982311627382a8772ab42c80b49b033268f68"  # pragma: allowlist secret
V1_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "a3105c9b4a41e5029366ccb871a7e002cbbc762e93f4d52e73f778bae75e5bd4",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "24a7e0108526928b609e2f6ec64878195d780c42f30c96c3b1bb0bf7e1dc9b9d",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "6b4ccc7eb831c5cf01e2c34d4b47de2ea6a9b8dcdcad35f65dd1e6e9e8027470",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "cc559ad8cfd7f36c037db683618fe597b2a79a2c60873c924d12d9cbce060993",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "46db0eeffb2c388ffe1f4c18c687a3174e14a603e645ad9e78c892047ebdd99e",  # pragma: allowlist secret
}
# The v2 files' own digests (the audit record; the live pins moved to v3).
V2_FILES = {
    "specimen_geography-v2.txt": "06609acdab2752826f718b292b73a19061d8014b900c646cc4fb5466253d0330",  # pragma: allowlist secret
    "specimen_taxonomy-v2.txt": "832626c5d7082d33a4f249bce2fca2746f959247653e523117d2cdfacb361092",  # pragma: allowlist secret
    "specimen_temporal-v2.txt": "ec316a45ca2a0b208e2dd842b89691c684639fb9ae1918a181f969f4418f0ac2",  # pragma: allowlist secret
    "specimen_measurement-v2.txt": "49b332414bb02784f9e584410db5777619e64b8866203901a36d48730b9a4647",  # pragma: allowlist secret
    "specimen_parties-v2.txt": "e5f7dae5716931eff095bd77a3e02561555e5a8c2f2645f3f1d93c720ddbbd33",  # pragma: allowlist secret
    "specimen_collection-v2.txt": "98b308f54dd5a287896ed321560ef857857f638713257fd69921980eb8612a2c",  # pragma: allowlist secret
}
GEOGRAPHY_V2_DIGEST = "359cbdb19403726e0a26da738758e06ad7f40e414aae15b89f7011155f71dcd4"  # pragma: allowlist secret
# The same five roles' pin digests on their v2 files, computed from those files below.
RELATION_DIGESTS = {
    SpecialistRole.TAXONOMY: "891d78856639fd1c1e8042e1f23177f5939f03966a8088b5af4bda35d4103bfd",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "1b41c74c2a4483ae6eb4bcc5a4a74e97a9d685dd7c09e8876530c1ac9b853937",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "58ac6830c6cde16d2d2a8747537f9721f687185d97bc5f832e9e141248244f52",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "b331cd9956fc6d464490eff47292ecefcd7b8d0fa8093605a188c69445bf6177",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "64b98ef934ea701b153545c361ba8183ebc8dfaed1fa6dc33081e9212c7a3d80",  # pragma: allowlist secret
}
# The GEOLocate query_text contract (lane G validator spec, revised 2026-10-03 with "place").
QUERY_KEYS = ("country", "state", "county", "locality", "place", "latitude", "longitude", "radius_km", "value")
REQUIRED_QUERY_KEYS = {"country", "locality", "place", "latitude", "longitude", "radius_km", "value"}
V2 = ROOT / "specimen_geography-v2.txt"
# The geography file the table resolves now; every v2 property below holds of it because it is the v2 file
# followed by the v3 blocks, the v4 block and the v5 block (test_prompt_reading_citation_v3.py,
# test_prompt_missing_policy_v4.py, test_prompt_handover_v5.py).
LIVE = ROOT / ROLE_PROMPTS[SpecialistRole.GEOGRAPHY][0]


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


@pytest.mark.parametrize(("name", "sha256"), tuple(V1_FILES.items()))
def test_v1_prompt_files_stay_byte_identical(name, sha256):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha256


@pytest.mark.parametrize(("name", "sha256"), tuple(V2_FILES.items()))
def test_v2_prompt_files_stay_byte_identical(name, sha256):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha256


def test_the_table_names_every_role_and_an_existing_file():
    assert set(ROLE_PROMPTS) == set(SpecialistRole)
    assert all((ROOT / name).is_file() for name, _ in ROLE_PROMPTS.values())
    assert ROLE_PROMPTS[SpecialistRole.GEOGRAPHY] == ("specimen_geography-v7.txt", GEOGRAPHY_HISTORY_PROMPT_VERSION)


def test_geography_v2_stays_the_audited_historian_prompt_with_its_owned_fields():
    expected = ((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n" + V2.read_text(encoding="utf-8")
                + "\nOwned fields: country, province_state, county, city, precise_location.\n")
    assert hashlib.sha256(expected.encode()).hexdigest() == GEOGRAPHY_V2_DIGEST != GEOGRAPHY_V1_DIGEST
    assert GEOGRAPHY_PROMPT_VERSION == "geography-historian-v2-2026-10-03"
    assert all(str(key) in expected for key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY])


def test_geography_resolves_to_its_v7_file_with_its_owned_fields():
    prompt = pin(SpecialistRole.GEOGRAPHY)
    expected = ((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n" + LIVE.read_text(encoding="utf-8")
                + "\nOwned fields: country, province_state, county, city, precise_location.\n")
    assert LIVE.name == "specimen_geography-v7.txt"
    assert prompt.text == expected
    assert prompt.version == GEOGRAPHY_HISTORY_PROMPT_VERSION == "geography-source-history-v7-2026-10-06"
    assert MISSING_POLICY_PROMPT_VERSION == "specialists-missing-policy-v4-2026-10-03" != prompt.version
    assert prompt.digest == hashlib.sha256(expected.encode()).hexdigest()
    assert prompt.digest not in {GEOGRAPHY_V1_DIGEST, GEOGRAPHY_V2_DIGEST}
    assert all(str(key) in prompt.text for key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY])
    # The v3 file (the reading citation) and the v4 file (the missing-policy block) are the audited bases the v5
    # file extends.
    v3 = (ROOT / "specimen_geography-v3.txt").read_text(encoding="utf-8")
    v4 = (ROOT / "specimen_geography-v4.txt").read_text(encoding="utf-8")
    assert LIVE.read_text(encoding="utf-8").startswith(v4) and v4.startswith(v3)
    assert READING_CITATION_PROMPT_VERSION != prompt.version


@pytest.mark.parametrize("role", tuple(RELATION_DIGESTS))
def test_the_other_five_roles_keep_their_audited_v2_files_the_v1_text_plus_the_relation_rule(role):
    common = (ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n"
    owned = "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n"
    v1 = (ROOT / f"{role.value}-v1.txt").read_text(encoding="utf-8")
    v2 = (ROOT / f"{role.value}-v2.txt").read_text(encoding="utf-8")
    assert v2.startswith(v1) and v2[len(v1):].startswith("Evidence relations (G23): ")
    assert hashlib.sha256((common + v2 + owned).encode()).hexdigest() == RELATION_DIGESTS[role]
    assert RELATIONS_PROMPT_VERSION == "specialists-relations-v2-2026-10-03"
    # The v1 files on disk still give the v1 pin digests.
    assert hashlib.sha256((common + v1 + owned).encode()).hexdigest() == V1_ROLE_DIGESTS[role] != RELATION_DIGESTS[role]
    assert PROMPT_VERSION == "specialists-v1-2026-09-29"
    # The live pin is the v2 text plus the v3 blocks, the v4 block and the v5 block.
    assert pin(role).text.startswith(common + v2) and pin(role).digest != RELATION_DIGESTS[role]


def test_v2_is_ascii_and_names_no_other_geocoder():
    for path in (V2, LIVE):
        path.read_bytes().decode("ascii")  # read_text must not depend on the locale's encoding
    for text in (V2.read_text(encoding="ascii"), LIVE.read_text(encoding="ascii"), pin(SpecialistRole.GEOGRAPHY).text):
        assert "google" not in text.lower()
        assert "geocodio" not in text.lower()


def test_v2_teaches_every_geolocate_query_key_and_a_valid_example():
    text = LIVE.read_text(encoding="utf-8")
    assert 'source_id "geolocate"' in text and "lookup_source" in text
    # The keys are taught in the query_text description, not merely elsewhere (value.state, ...).
    contract = text[text.index("query_text"):text.index("Example, field province_state")]
    for key in QUERY_KEYS:
        assert re.search(rf"(?<![\w.]){key}(?![\w.])", contract), key
    [line] = [item for item in text.splitlines() if item.startswith("{")]
    example = json.loads(line)
    assert REQUIRED_QUERY_KEYS <= set(example) <= set(QUERY_KEYS)
    assert len(line) <= 500 and 1 <= example["radius_km"] <= 100
    assert all(isinstance(item, str) and item == item.strip() and 0 < len(item) <= 200
               for key, item in example.items() if key not in {"latitude", "longitude", "radius_km"})
    for outcome in ("success", "ambiguous", "no_match"):
        assert f"- {outcome}:" in text


def test_v2_names_only_source_and_field_pairs_the_registry_admits():
    registry = insects_registry()
    text = LIVE.read_text(encoding="utf-8")
    geography = set(ROLE_FIELDS[SpecialistRole.GEOGRAPHY])
    assert set(registry.get("geolocate").fields) == geography
    ipt = {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION}
    assert set(registry.get("field_museum_ipt").fields) & geography == ipt
    assert "field_museum_ipt exact joins\nserve only country, province_state and precise_location" in text
    assert "google_maps" not in text and "invoke_utility" not in text


LOOKUP_PRODUCER_RULE = (
    "Every resolution that cites a lookup names, as the common rules ask, its accepted/rejected "
    "assemblies (assembly_ids: the request's assemblies for that field that the interpretation read) "
    "and event (event_id); the lookup's producer comes from them, and publication refuses a lookup "
    "without one.")


@pytest.mark.parametrize("role", (SpecialistRole.TAXONOMY, SpecialistRole.PARTIES, SpecialistRole.COLLECTION))
def test_lookup_citing_resolutions_name_the_assemblies_they_read(role):
    # Without assembly_ids and event_id a cited lookup has no producer
    # (lookup_evidence_producer_invalid), so these roles state it explicitly.
    text = " ".join(pin(role).text.split())
    assert LOOKUP_PRODUCER_RULE in text
