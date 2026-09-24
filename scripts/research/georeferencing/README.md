# Georeferencing research probe

`pilot_probe.py` asks public sources what they know about the four localities
on the ten pilot slides, so the owner can judge the plan in
[`docs/product-requirements/GEOREFERENCING.md`](../../../docs/product-requirements/GEOREFERENCING.md)
against real answers rather than examples. It is research code from session S8
(2026-09-23). Nothing imports it, and the harness's geography tool will follow
the plan, not this script.

The probe predates PLAN 4.8. It sent a year range and label locality strings to
GBIF's occurrence search, which the place tool never does: that check is off
while D4 is held, and every request the tool sends follows PLAN 4.8.

```bash
uv run python scripts/research/georeferencing/pilot_probe.py --out /tmp/geo-probe
```

What it does, per locality:

1. Parses the verbatim label text into feature, direction, administrative
   parts and country, expanding abbreviations from a fixed table.
2. Resolves the country literal ("P.I.", "Philippine Islands", "Guatemala")
   and every name through the Wikidata Action API, then enriches the
   candidates in one SPARQL query: validity window, successors (P1366),
   parents and point.
3. Matches names in the GeoNames per-country dump files (no account needed),
   exact first and fuzzy only when nothing matches exactly.
4. Collects the Field Museum's own published georeferences for records whose
   locality names the feature (GBIF occurrence search, facet then exact
   locality strings).
5. Checks each candidate point's containment through GBIF's reverse geocoder,
   which reads GADM (research only: the tool uses geoBoundaries and never GADM,
   PLAN 4.8), and
   its SRTM elevation (OpenTopoData) against the label elevation, and samples
   an elevation transect along a slope direction ("E. slope").

Rules it keeps: anonymous public endpoints only, no key, no paid call, a
descriptive User-Agent, at least 1.1 seconds between requests to the same host,
`Retry-After` honoured once, and nothing written outside `--out` (the raw
responses with their SHA-256, `report.json` and `summary.md`). A run makes
about 70 requests and takes two to three minutes.

The crosswalk entry mapping "Mount McKinley" to "Mount Talomo" is a hypothesis
for curator review, taken from the expedition narrative, not a fact.
