"""The server's side of the shared field-attention contract (tests/fixtures/field_attention.json).

The app's side is its test field_attention_contract_test.dart (no Python test reads the app); both read the
same fixture, so the server's per-field counts and the app's field rows map reason codes to fields
the same way (plan WP K1, Codex round 2 on PR #455)."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application.review_summary import attention_fields, review_summary

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "field_attention.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[case["name"] for case in FIXTURE["cases"]])
def test_the_server_marks_the_fields_the_contract_names(case):
    codes = [*case.get("held_codes", []), *case["codes"]]
    assert sorted(attention_fields(case["fields"], codes)) == case["attention"]
    assert review_summary(case["fields"], codes)["review"] == len(case["attention"])
