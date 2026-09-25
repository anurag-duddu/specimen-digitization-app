# Georeferencing test fixtures

Recorded answers and rows from public gazetteers, and units from public
boundary files, each cut down to what the tests read. They cover the pilot's
places and their neighbours only. The only label text here is pilot place names
(G31).

| File | Source | Retrieved | License and credit |
|---|---|---|---|
| `wikidata_search.json` | Wikidata `wbsearchentities`, from S8's research probe | 2026-09-23 | CC0 1.0 |
| `wikidata_entities.json`, `wikidata_labels.json` | Wikidata `wbgetentities` for the pilot's places | 2026-09-24 | CC0 1.0 |
| `geonames_PH.txt`, `geonames_GT.txt` | 23 rows copied unchanged from the GeoNames Philippines and Guatemala dumps pinned in `georef_datasets.py` (`geonames/PH/2026-09-24`, `geonames/GT/2026-09-24`) | 2026-09-24 | GeoNames (https://www.geonames.org/), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) |
| `tgn_reconcile.json` | Getty's reconciliation service, type `/tgn`, for twelve pilot names, one name a request | 2026-09-24 | Contains information from the J. Paul Getty Trust, Getty Research Institute, Thesaurus of Geographic Names, which is made available under the ODC Attribution License (https://opendatacommons.org/licenses/by/1-0/) |
| `tgn_records.json`, `tgn_names.json` | Getty's SPARQL endpoint, `georef_tgn`'s two queries for the 24 records those names led to; the request carries TGN ids only | 2026-09-24 | as above |
| `nga_search.json` | NGA GNS name searches (`georef_nga.search_params`) for twelve pilot names, one name a request | 2026-09-24 | NGA GEOnet Names Server; NGA's pages state no license and carry a disclaimer (#94, S33) |
| `nga_features.json`, `nga_units.json` | NGA GNS reads of the 51 features those searches found and of their first-order units; the requests carry GNS ids and codes only | 2026-09-24 | as above |
| `geoboundaries_PH_ADM3.geojson` | Davao City, copied unchanged from geoBoundaries' simplified Philippine municipalities pinned in `georef_datasets.py` (`geoboundaries/PH/ADM3/9469f09`) | 2026-09-24 | National Mapping and Resource Information Authority (NAMRIA), Philippines Statistics Authority (PSA), OCHA Philippines, via geoBoundaries (https://www.geoboundaries.org/), licensed under CC BY 3.0 IGO (https://creativecommons.org/licenses/by/3.0/igo/) |
| `cod_ab_GT_admin1.geojson`, `cod_ab_GT_admin2.geojson` | The department of Chimaltenango and the municipios of Yepocapa and Acatenango, copied unchanged from the admin1 and admin2 layers of the COD-AB file pinned in `georef_datasets.py` (`cod-ab/GT/2026-09-24`); the tests zip them as that file does | 2026-09-24 | Coordinadora Nacional Para La Reducción De Desastres (CONRED), via OCHA's Common Operational Datasets on HDX (https://data.humdata.org/dataset/cod-ab-gtm), licensed under CC BY 3.0 IGO (https://creativecommons.org/licenses/by/3.0/igo/) |
