"""SPECIMEN_RESEARCH_HARNESS: whether the production drain mounts the harness."""

import pytest

from specimen_digitization.research_harness.enablement import research_harness_enabled


def test_on_mounts_the_harness():
    assert research_harness_enabled({"SPECIMEN_RESEARCH_HARNESS": "on"}) is True


@pytest.mark.parametrize("environ", [{}, {"SPECIMEN_RESEARCH_HARNESS": ""},
                                     {"SPECIMEN_RESEARCH_HARNESS": "off"}])
def test_unset_empty_or_off_keeps_the_ordinary_chain(environ):
    assert research_harness_enabled(environ) is False


@pytest.mark.parametrize("value", ["true", "false", "ON", "1", " on", "enabled-please"])
def test_any_other_value_fails_loudly_without_echoing_it(value):
    with pytest.raises(ValueError, match="^SPECIMEN_RESEARCH_HARNESS must be on or off$"):
        research_harness_enabled({"SPECIMEN_RESEARCH_HARNESS": value})
