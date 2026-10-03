"""Whether the production drain mounts the research harness.

SPECIMEN_RESEARCH_HARNESS takes "on" or "off". Unset or empty is off: the drain
steps each run through the ordinary processing chain. Any other value raises,
so a mistyped value never decides the chain silently.
"""
from __future__ import annotations

from collections.abc import Mapping

SETTING = "SPECIMEN_RESEARCH_HARNESS"
VALUES = {"": False, "off": False, "on": True}


def research_harness_enabled(environ: Mapping[str, str]) -> bool:
    """The setting's value; errors name the setting, never its value."""
    value = environ.get(SETTING, "")
    if value not in VALUES:
        raise ValueError(f"{SETTING} must be on or off")
    return VALUES[value]
