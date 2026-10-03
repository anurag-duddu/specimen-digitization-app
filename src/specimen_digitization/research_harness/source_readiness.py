"""Committed source readiness and capture retention for the research harness.

Data only, keyed by the source ids of ``sources.insects_registry()``. The pins
builder (committed_pins.py) keeps only the rows whose id the installed registry
has, so a source that leaves the registry drops out of the pins.

SOURCE_READINESS rows hold the four fields ``insects_registry`` accepts as
qualification overrides. For the three taxonomy APIs, ``qualification_receipt``
is a reference to the row in this file; no receipt exists. ``schema_digest`` is
``contracts.digest`` of the response keys the typed adapter reads, as listed for
the source in ``prompts/public-source-canaries-2026-09-29.json``. The releases
were read on 2026-10-02:
- gbif: the COL XR checklist the adapter queries (``COL_XR``), published
  2026-06-19 (https://api.gbif.org/v1/dataset/7ddf754f-d193-4cc9-b351-99906754a03b).
- global_names_verifier: https://verifier.globalnames.org/api/v1/version, v1.6.2.
- catalogue_of_life: https://api.checklistbank.org/dataset/3LR resolved to the
  release key 316321 (COL26.9, issued 2026-09-11), the key the canary recorded.
  The adapter puts this key in the request path, so it must stay an integer.
The geolocate row is ``sources.GEOLOCATE_QUALIFICATION`` itself, imported so the
two cannot drift: its receipt names the owner rulings G-geo-1..3 and the
2026-10-03 glcwrap.aspx probe, its schema digest is ``digest(GEOLOCATE_SCHEMA)``
and its release is ``GEOLOCATE_RELEASE``.

CAPTURE_POLICIES gives each source's retention as (kind, maximum_responses).
Only full_response lets a lookup run, and only for a ready source. The three
taxonomy adapters and the GEOLocate adapter make one GET per lookup
(sources.SourceBroker._execute). Browser sources, the unqualified museum
catalogue and Google Maps (paid, never full_response) are denied.
field_museum_ipt is absent: its joined lookup needs per-specimen joins that
committed data cannot give.
"""
from __future__ import annotations

from .sources import GEOLOCATE_QUALIFICATION

_ORIGIN = "repo:src/specimen_digitization/research_harness/source_readiness.py"

SOURCE_READINESS = {
    "gbif": {
        "qualification_state": "searched",
        "qualification_receipt": _ORIGIN + "#SOURCE_READINESS.gbif",
        # digest(["usage", "classification", "diagnostics", "synonym"])
        "schema_digest": "34c0c78b587eb9bcf299de961883223280e93ef4bf838f8336d2a49140aee208",  # pragma: allowlist secret (response schema digest)
        "source_release": "col-xr:7ddf754f-d193-4cc9-b351-99906754a03b@2026-06-19",
    },
    "global_names_verifier": {
        "qualification_state": "searched",
        "qualification_receipt": _ORIGIN + "#SOURCE_READINESS.global_names_verifier",
        # digest(["metadata", "names"])
        "schema_digest": "dac9e788d6f8aef5345db071cbe7ffb9c5fc0d4c45b9457264caf91f2094be25",  # pragma: allowlist secret (response schema digest)
        "source_release": "gnverifier-v1.6.2",
    },
    "catalogue_of_life": {
        "qualification_state": "searched",
        "qualification_receipt": _ORIGIN + "#SOURCE_READINESS.catalogue_of_life",
        # digest(["offset", "limit", "total", "result", "empty", "last"])
        "schema_digest": "bac8db5166c6ae1638b1459f154c7f8e967074fb33a04b8f772b167dc7107f69",  # pragma: allowlist secret (response schema digest)
        "source_release": "316321",
    },
    "geolocate": GEOLOCATE_QUALIFICATION,
}

CAPTURE_POLICIES = {
    "gbif": ("full_response", 1),
    "global_names_verifier": ("full_response", 1),
    "catalogue_of_life": ("full_response", 1),
    "geolocate": ("full_response", 1),
    "google_maps": ("denied", 1),
    "bugguide": ("denied", 1),
    "mapcarta": ("denied", 1),
    "field_museum_emudata": ("denied", 1),
}
