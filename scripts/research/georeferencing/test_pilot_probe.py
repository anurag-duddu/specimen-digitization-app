"""The research probe never reads GADM, not even as a measurement (PLAN 4.8)."""

from pathlib import Path

PROBE = Path(__file__).with_name("pilot_probe.py")


def test_the_probe_names_no_gadm_endpoint():
    # GBIF's reverse geocoder answers with GADM's layers, and its geocode/gadm
    # operations are GADM's own: PLAN 4.8 rules out both, even behind a flag.
    source = PROBE.read_text(encoding="utf-8")
    assert "geocode/reverse" not in source
    assert "geocode/gadm" not in source
    assert "GADM0" not in source
