"""Geography's historian prompt v2 and the per-role prompt table (owner G-geo-1..3, 2026-10-03).

Only geography moves to a new prompt file and pin version. The digests below were
computed from main 2f85b429 before v2 was wired; the other five roles must keep them.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import FieldKey, ROLE_FIELDS, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROMPT_VERSION, PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
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
UNCHANGED_DIGESTS = {
    SpecialistRole.TAXONOMY: "a3105c9b4a41e5029366ccb871a7e002cbbc762e93f4d52e73f778bae75e5bd4",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "24a7e0108526928b609e2f6ec64878195d780c42f30c96c3b1bb0bf7e1dc9b9d",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "6b4ccc7eb831c5cf01e2c34d4b47de2ea6a9b8dcdcad35f65dd1e6e9e8027470",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "cc559ad8cfd7f36c037db683618fe597b2a79a2c60873c924d12d9cbce060993",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "46db0eeffb2c388ffe1f4c18c687a3174e14a603e645ad9e78c892047ebdd99e",  # pragma: allowlist secret
}
# The GEOLocate query_text contract (lane G validator spec, revised 2026-10-03 with "place").
QUERY_KEYS = ("country", "state", "county", "locality", "place", "latitude", "longitude", "radius_km", "value")
REQUIRED_QUERY_KEYS = {"country", "locality", "place", "latitude", "longitude", "radius_km", "value"}
V2 = ROOT / "specimen_geography-v2.txt"


def pin(role):
    return resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN, toolset_digest=PIN,
                          model_route="harness-deepseek", output_schema_digest=PIN)


@pytest.mark.parametrize(("name", "sha256"), tuple(V1_FILES.items()))
def test_v1_prompt_files_stay_byte_identical(name, sha256):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha256


def test_the_table_names_every_role_and_an_existing_file():
    assert set(ROLE_PROMPTS) == set(SpecialistRole)
    assert all((ROOT / name).is_file() for name, _ in ROLE_PROMPTS.values())
    assert ROLE_PROMPTS[SpecialistRole.GEOGRAPHY] == ("specimen_geography-v2.txt", GEOGRAPHY_PROMPT_VERSION)


def test_geography_resolves_to_the_v2_historian_prompt_with_its_owned_fields():
    prompt = pin(SpecialistRole.GEOGRAPHY)
    expected = ((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n" + V2.read_text(encoding="utf-8")
                + "\nOwned fields: country, province_state, county, city, precise_location.\n")
    assert prompt.text == expected
    assert prompt.version == GEOGRAPHY_PROMPT_VERSION == "geography-historian-v2-2026-10-03"
    assert prompt.digest == hashlib.sha256(expected.encode()).hexdigest() != GEOGRAPHY_V1_DIGEST
    assert all(str(key) in prompt.text for key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY])


@pytest.mark.parametrize("role", tuple(UNCHANGED_DIGESTS))
def test_the_other_five_roles_keep_their_text_digest_and_version(role):
    prompt = pin(role)
    assert prompt.digest == UNCHANGED_DIGESTS[role]
    assert prompt.version == PROMPT_VERSION == "specialists-v1-2026-09-29"
    assert prompt.text.startswith((ROOT / "common-v1.txt").read_text(encoding="utf-8") + "\n")
    assert (ROOT / f"{role.value}-v1.txt").read_text(encoding="utf-8") in prompt.text


def test_v2_is_ascii_and_names_no_other_geocoder():
    raw = V2.read_bytes()
    raw.decode("ascii")  # read_text must not depend on the locale's encoding
    for text in (raw.decode("ascii"), pin(SpecialistRole.GEOGRAPHY).text):
        assert "google" not in text.lower()
        assert "geocodio" not in text.lower()


def test_v2_teaches_every_geolocate_query_key_and_a_valid_example():
    text = V2.read_text(encoding="utf-8")
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
    text = V2.read_text(encoding="utf-8")
    geography = set(ROLE_FIELDS[SpecialistRole.GEOGRAPHY])
    assert set(registry.get("geolocate").fields) == geography
    ipt = {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION}
    assert set(registry.get("field_museum_ipt").fields) & geography == ipt
    assert "field_museum_ipt exact joins\nserve only country, province_state and precise_location" in text
    assert "google_maps" not in text and "invoke_utility" not in text
