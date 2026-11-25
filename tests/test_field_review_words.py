"""The server's side of the shared field-review-words contract (tests/fixtures/field_review_words.json).

The waiting-fields program, fix 1 (2026-11-24): the Identified by IRN, which no label carries and no approved
source looks up, is not counted for review while research leaves it unknown with no value and no reason names it.
The app's side is test/field_review_words_contract_test.dart; both read the same fixture: this side checks the
server's summary for each case, and the app's side checks that its drawn rows reading "Review needed" number the
summary's `review`, on the cases the fixture holds."""

import json
from pathlib import Path

import pytest

from specimen_digitization.application import review_summary as module
from specimen_digitization.application.review_summary import attention_fields, review_summary
from specimen_digitization.field_research.contracts import NO_APPROVED_AUTHORITY

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "field_review_words.json").read_text())
CASES = pytest.mark.parametrize("case", FIXTURE["cases"], ids=[case["name"] for case in FIXTURE["cases"]])


def test_the_fixture_names_the_servers_fields_with_no_approved_authority():
    assert FIXTURE["no_approved_authority"] == sorted(NO_APPROVED_AUTHORITY)


@CASES
def test_the_server_counts_the_summary_the_contract_names(case):
    assert review_summary(case["fields"], case["codes"]) == case["summary"]


@CASES
def test_the_server_names_the_fields_the_contract_names(case):
    fields, codes, status = case["fields"], case["codes"], case["status"]
    assert module.no_source_fields(fields, codes) == {key for key, word in status.items() if word == "no_source"}
    assert case["summary"]["review"] == sum(word == "review" for word in status.values())


@CASES
def test_the_flag_rule_itself_is_unchanged(case):
    """attention_fields, which the second opinion's flag check reads, still names the IRN: only the
    review count leaves it out."""
    fields, codes, status = case["fields"], case["codes"], case["status"]
    assert attention_fields(fields, codes) == {key for key, word in status.items()
                                               if word in {"review", "no_source"}}
