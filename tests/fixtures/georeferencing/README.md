# Georeferencing test fixtures

Recorded answers and rows from public gazetteers, each cut down to what the
tests read. They cover the pilot's places only. The only label text here is
pilot place names (G31).

| File | Source | Retrieved | License and credit |
|---|---|---|---|
| `wikidata_search.json` | Wikidata `wbsearchentities`, from S8's research probe | 2026-09-23 | CC0 1.0 |
| `wikidata_entities.json`, `wikidata_labels.json` | Wikidata `wbgetentities` for the pilot's places | 2026-09-24 | CC0 1.0 |
| `geonames_PH.txt`, `geonames_GT.txt` | 23 rows copied unchanged from the GeoNames Philippines and Guatemala dumps pinned in `georef_datasets.py` (`geonames/PH/2026-09-24`, `geonames/GT/2026-09-24`) | 2026-09-24 | GeoNames (https://www.geonames.org/), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) |
| `tgn_reconcile.json` | Getty's reconciliation service, type `/tgn`, for twelve pilot names, one name a request | 2026-09-24 | Contains information from the J. Paul Getty Trust, Getty Research Institute, Thesaurus of Geographic Names, which is made available under the ODC Attribution License (https://opendatacommons.org/licenses/by/1-0/) |
| `tgn_records.json`, `tgn_names.json` | Getty's SPARQL endpoint, `georef_tgn`'s two queries for the 24 records those names led to; the request carries TGN ids only | 2026-09-24 | as above |
