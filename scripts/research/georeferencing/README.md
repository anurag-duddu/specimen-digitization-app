# Georeferencing research probe

`pilot_probe.py` asks public sources what they know about the four localities
on the ten pilot slides, so the owner can judge the plan in
[`docs/product-requirements/GEOREFERENCING.md`](../../../docs/product-requirements/GEOREFERENCING.md)
against real answers rather than examples. It is research code from session S8
(2026-09-23). Nothing imports it, and the harness's geography tool will follow
the plan, not this script.

The probe predates PLAN 4.8. Its first runs sent GBIF's occurrence search the
museum code, the country and the label's year ±1, then the locality facet
values GBIF itself returned (never label text), and sent candidate points to
GBIF's GADM reverse geocoder. The place tool does neither: the occurrence check
is off while D4 is held, GADM is not used, not even as a measurement, and every
request it sends follows PLAN 4.8. The occurrence search now runs only with
`--held-steps`, so a default run sends no date and no occurrence query, and the
GADM step is gone from the probe.

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
4. With `--held-steps` only: collects the Field Museum's own published
   georeferences for records whose locality names the feature (GBIF occurrence
   search, facet then the facet values GBIF returned).
5. Compares each candidate point's SRTM elevation (OpenTopoData) with the label
   elevation, and samples an elevation transect along a slope direction
   ("E. slope").

Rules it keeps: anonymous public endpoints only, no key, no paid call, a
descriptive User-Agent, at least 1.1 seconds between requests to the same host,
`Retry-After` honoured once, and nothing written outside `--out` (the raw
responses with their SHA-256, `report.json` and `summary.md`). A default run
skips every GBIF request, and `--held-steps` adds only the occurrence search.
GBIF's occurrence records carry GADM's divisions in a `gadm` block, which the
probe removes before it keeps or stores a response, so the stored file and its
SHA-256 hold no GADM data (PLAN 4.8).

The crosswalk entry mapping "Mount McKinley" to "Mount Talomo" is a hypothesis
for curator review, taken from the expedition narrative, not a fact.
