"""What a publication failure may put in a log line (native_worker._described)."""
import pytest

from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.native_worker import _described

LONGEST = "a" + "_b" * 39 + "c"  # 80 characters


def test_the_longest_code_and_the_codes_the_publication_path_raises_are_logged():
    assert len(LONGEST) == 80
    for code in (LONGEST, "native_v2_commit_outcome_unknown", "canonical_capture_native_crop_unproved",
                 "lookup_evidence_producer_invalid", "native_v2_registration_rejected"):
        assert _described(PublicationUnavailable(code)) == ("PublicationUnavailable", "code=" + code)


@pytest.mark.parametrize("message", [
    "grassland",                    # a bare lowercase word is a value, not a code
    "19460914",                     # a bare digit run
    "a" + "_b" * 40,                # 81 characters: past the bound
    LONGEST + "_d",
    "a" * 200,
    "Native_code",                  # upper case
    "native_code\n",                # a trailing newline
    "native code",                  # two words
    "_native_code",                 # not a code's shape
    "native__code",
    "native_code_",
    "1native_code",
    "input_value='Synthetic teaching garden'",
    "naïve_code",
    "",
])
def test_a_message_that_is_not_a_snake_case_code_is_never_logged(message):
    cls, detail = _described(ValueError(message))
    assert cls == "ValueError" and detail.startswith("at=") and (not message or message not in detail)
