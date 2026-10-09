"""Whether the production drain mounts the research harness, and which one.

SPECIMEN_RESEARCH_HARNESS takes "off", "on" or "fields". Unset or empty is off:
the drain steps each run through the ordinary processing chain. "on" mounts the
six-specialist research harness at the plan handover; "fields" mounts field
research there instead (field_research/step.py; FIELD_RESEARCH.md). Any other
value raises, so a mistyped value never decides the chain silently.
"""
from __future__ import annotations

from collections.abc import Mapping

SETTING = "SPECIMEN_RESEARCH_HARNESS"
MODES = {"": "off", "off": "off", "on": "on", "fields": "fields"}
VALUES = {value: mode != "off" for value, mode in MODES.items()}


def research_harness_mode(environ: Mapping[str, str]) -> str:
    """"off", "on" or "fields"; errors name the setting, never its value."""
    value = environ.get(SETTING, "")
    if value not in MODES:
        raise ValueError(f"{SETTING} must be off, on or fields")
    return MODES[value]


def research_harness_enabled(environ: Mapping[str, str]) -> bool:
    """Whether a harness is mounted at the plan handover ("on" or "fields")."""
    return research_harness_mode(environ) != "off"
