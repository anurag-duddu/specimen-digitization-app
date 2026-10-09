"""SPECIMEN_RESEARCH_HARNESS: whether the production drain mounts the harness."""

import pytest

from specimen_digitization.research_harness.enablement import research_harness_enabled, research_harness_mode


def test_on_mounts_the_harness():
    assert research_harness_enabled({"SPECIMEN_RESEARCH_HARNESS": "on"}) is True
    assert research_harness_mode({"SPECIMEN_RESEARCH_HARNESS": "on"}) == "on"


def test_fields_mounts_field_research():
    assert research_harness_enabled({"SPECIMEN_RESEARCH_HARNESS": "fields"}) is True
    assert research_harness_mode({"SPECIMEN_RESEARCH_HARNESS": "fields"}) == "fields"


@pytest.mark.parametrize("environ", [{}, {"SPECIMEN_RESEARCH_HARNESS": ""},
                                     {"SPECIMEN_RESEARCH_HARNESS": "off"}])
def test_unset_empty_or_off_keeps_the_ordinary_chain(environ):
    assert research_harness_enabled(environ) is False
    assert research_harness_mode(environ) == "off"


@pytest.mark.parametrize("value", ["true", "false", "ON", "1", " on", "Fields", "field", "enabled-please"])
def test_any_other_value_fails_loudly_without_echoing_it(value):
    with pytest.raises(ValueError, match="^SPECIMEN_RESEARCH_HARNESS must be off, on or fields$"):
        research_harness_enabled({"SPECIMEN_RESEARCH_HARNESS": value})
