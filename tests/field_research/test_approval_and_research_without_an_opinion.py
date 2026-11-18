"""Main's approval tests (test_approval_and_research.py) run again with the second opinion's marks
derived (USES_SECOND_OPINION, tests/conftest.py) but no opinion obtained (the step switched off: every
settled value not checked). A person's approval is the person's (the G51 ruling): once approved, no
second-opinion code, exactly as main's own marks. Every assertion is main's, unchanged. Two of main's
tests are not collected here, because their premise is a record that clears with no person, which
cannot hold while no opinion is obtained: test_research_that_clears_a_run_no_person_touched_clears_it_as_the_system
and test_a_retry_whose_research_changes_a_value_ends_an_earlier_approval; both run with the step off
(test_approval_and_research.py) and with an agreeing opinion
(test_approval_and_research_with_second_opinion.py)."""

from __future__ import annotations

import test_approval_and_research as main_tests

USES_SECOND_OPINION = True
NEEDS_A_SYSTEM_CLEAR = {"test_research_that_clears_a_run_no_person_touched_clears_it_as_the_system",
                        "test_a_retry_whose_research_changes_a_value_ends_an_earlier_approval"}

globals().update({name: value for name, value in vars(main_tests).items()
    if not name.startswith("__") and name not in NEEDS_A_SYSTEM_CLEAR and name != "USES_SECOND_OPINION"})
