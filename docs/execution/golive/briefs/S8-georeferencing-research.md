# S8 brief: retrospective georeferencing research

Session title: **Research retrospective georeferencing for the harness**.
Recommended model Opus 5.5 at high effort; web research tools
(`WebSearch`, `WebFetch`) are needed.

## Why this exists

The owner, 2026-09-23: "for location parts in the harness a different approach
might be needed, spin this off as a new task". The owner supplied the research
charter below. Its output is a plan for the owner to review; it does not change
the production harness by itself. Until the owner accepts a plan, the harness
workstream (S4) keeps geography behind its typed tool interface with the Google
Maps tool of owner decision G10 as the initial, fully functional version (G6).

G34 (2026-09-24): the owner decided D15 for the Google tool and added: "clear
with place ID byt I want the harness for location retrospective
georeferencing fully implemented". So this workstream now also builds the
retrospective georeferencing tool behind S4's T3a geography interface, spec
first and test first as PLAN section 7 requires, in modules it owns, merged
by the steward. The D items stand as PLAN section 2.3 records: the owner
decided D1, D2, D3, D6, D7 and D9 on 2026-09-24 (G35 to G39, with G40 on the
harness's job and G41 on stated elevations); D11 (Copernicus GLO-30 tiles
read from the project's storage, credited) and D13 (the in-house point-radius
uncertainty engine) are coordinator rulings; D4 and D5 are on hold: D4's
occurrence check is off and sends nothing, and D5's checks record findings
only (coordinator rulings); D8, D10 and D12 wait for
their phase, except Getty TGN (G35). Each part of the build waits for any D
item that decides it.
You build the geographic derivations behind S4's interface (coordinator
ruling). Your modules: `src/specimen_digitization/application/georef_*.py`
and `georeferencing_tool.py`, their tests, `tests/fixtures/georeferencing/`
and `docs/execution/golive/GEO.md`.

## Build (G34 to G41)

Each task starts with its spec delta in `docs/execution/golive/GEO.md` and
failing tests, on its own branch, merged by the steward. PLAN section 4.8
governs every outside request.

1. Locality text: the parts of a locality, label notations and their readings
   (G29), slope and bearing phrases, elevation phrases kept as written, query
   variants from each reader's literal (G19, G20, G27), and the one-letter
   comparison on full names, never codes (G34).
2. Tier 1 gazetteers (G35): GeoNames, Wikidata, Getty TGN and NGA behind fakes
   and recorded fixtures, one source call per request, place text only,
   credited.
3. History: validity windows, successor chains, and historical and modern
   roles. The label-lag tolerance waits for D5.
4. Curated entries (G36): drafted with their sources and confirmed only
   through a pull request citing the owner-recorded confirmation, with a test
   that an unconfirmed entry never settles a field.
5. Tier 2 (G35): Google given the modernized name, or the literal, with the
   same reading's place fields, keeping only the place ID, the outcome and the
   fingerprint (G26).
6. Tier 3 and the geographic derivations (D13, D11, G37, G38, G41): the
   in-house point-radius engine; containment for county and city against
   geoBoundaries' open release (CC BY 4.0, credited); elevation from Copernicus
   GLO-30 where the label states none; a location derived from a settled county
   at county precision (G38); all as derivation results behind S4's interface,
   from open-source coordinates only.
7. The tool as `geography_lookup`, swapped in behind the same interface once
   both gates hold: the owner accepts your plan as G35 to G42 revise it (G12),
   and the acceptance lab shows it resolves the pilot slides at least as well
   as the Google module (coordinator ruling). The georeference stays in the
   tool result and the trace (G39).

## Grounding in this repository

Read before researching, so the plan fits the product that exists:

1. `docs/execution/golive/PLAN.md` (sections 1, 2 and 4.1 row 7) and the S4
   brief (`briefs/S4-first-pass-and-harness.md`), which defines the harness,
   its typed tools and outcomes, and the owner's rules: never invent values
   (`PRD.md` HAR-019); no data found for a mandatory field goes to the human
   queue; errors retry;
   "something that harness was able to resolve is cleared".
2. `docs/product-requirements/PRD.md` section 12.4 (487-567): the Insects field
   keys `country`, `province_state`, `county`, `city`, `precise_location`
   (verbatim, never replaced by a geocoder result), the four elevation fields
   (filled only with authority and evidence, G37 and G41), and the named geography sources; the typed lookup
   outcomes (HAR-008) and the failure table (676-688).
3. `docs/GBIF.md` 256-274 (its GADM use is superseded: GADM is not used,
   PLAN section 4.8) and
   `docs/execution/CONTRACTS.md` 210-270 (field value states; only `supported`
   satisfies a mandatory field).
4. `docs/product-requirements/COLLECTION_HIERARCHY.md`: the collections span
   Anthropology, Botany, Geology and Zoology, so the plan must say how profiles
   per collection and subcollection select geography behaviour.
5. `~/specimen-golive/research/06-product-spec-and-approvals.md` section 4 (the
   pilot field profile).
6. The pilot labels themselves (PLAN section 3): four localities on ten slides
   from two collecting events. Mindanao, Philippines, 1946 (CNHM; F.G. Werner,
   H. Hoogstraal): "E. slope Mt. McKinley, Davao Prov." at 6400 ft and at 3300
   ft, and "E. slope Mt. Apo, Davao Prov.", written "P.I." or "Philippine
   Islands". Yepocapa, Chimaltenango, Guatemala, 1948 (R.D. Mitchell), at 4800
   ft; the label misspells "Chimaltenago". Davao Province was later divided
   into several provinces and "P.I." is the pre-independence name, so the set
   tests historical resolution in two countries. Images:
   `gs://specimen-digitization.firebasestorage.app/microscopic-slides/subject_105526321.jpeg`
   to `...330.jpeg` (application default credentials work on this Mac). The
   acceptance lab (S7) produces transcripts of them; ask it for the ones it has.

## Deliverables

1. `docs/product-requirements/GEOREFERENCING.md`: the implementation plan in the
   charter's six sections, grounded in the repository (field keys, typed
   outcomes, the harness tool interface, the queue rule, profiles per
   collection). Cite sources for every external API claim, with the date you
   checked it. Mark every design choice the owner must confirm, and mark the
   document "Proposed, not accepted by the owner" at the top until the owner
   accepts it (G12). Tool outcomes are HAR-008's, as `LookupStatus` encodes
   them (`domain.py` 43-54); a missing credential is an operational block.
   From Google geocoding the pipeline keeps only the place ID, the outcome and a
   response fingerprint (G26).
2. Optional, only if it helps the owner judge the plan: a prototype under
   `scripts/research/georeferencing/` exercising the public endpoints read-only
   on the pilot labels' place names, with its results summarized in the plan.
   No production code, no secrets in the repository, no paid calls without the
   coordinator's go-ahead. GeoNames needs a free account username; if you need
   one, put that request in `~/specimen-golive/OWNER_ACTIONS.md`.
3. One docs pull request through the PR steward, following PLAN section 7.

## Research charter (supplied by the owner, verbatim)

# Role & Objective
You are an expert Geospatial Engineer and AI Solutions Architect specializing in Biodiversity Informatics, Semantics, and Automated Data Pipelines.

Your objective is to conduct exhaustive research and generate a comprehensive architecture plan for an autonomous "Retrospective Georeferencing and Location Validation Pipeline." This pipeline will ingest legacy, multi-disciplinary natural history collections data (spanning Anthropology, Geology, Zoology, and Botany) with location records that are 100+ years old, handle evolved/colonial toponyms, and output Darwin Core (DwC) compliant spatial data.

---

# Architectural Constraints & Logic
You must NOT build a pipeline that relies solely on modern commercial geocoders (e.g., standard Google Maps or Mapbox APIs), as they fail on historical boundaries, lack spatial uncertainty calculations, and cause false-positive hallucinations. Instead, design a Multi-Tiered Hybrid Routing Architecture:

1. Tier 1: Historical Resolution & Semantic Expansion (Wikidata SPARQL, GeoNames Historical/Alternate Dumps, Getty TGN).
2. Tier 2: Modern Coordinate Pinpointing (Using modernized strings verified in Tier 1 to query Google Maps API / Mapbox Geocoding API with strict Component Filtering).
3. Tier 3: Ecological Validation & Uncertainty Calculation (Cross-referencing GBIF/iDigBio distribution data and calculating Point-Radius uncertainty bounds using GEOLocate Web Services or standard minimum bounding circles).

---

# Tasks for the Agent

## Task 1: Comprehensive API & Dataset Deep Dive
Research the capabilities, authentication, and endpoint structures for the following services. Provide a concise technical assessment of how each will be utilized within the pipeline code:
- Wikidata SPARQL Endpoint (Specifically querying properties P625 coordinate location, P582 end time, and P1365 replaced by).
- GeoNames API & Historical Datasets (Filtering by PCLH and ADMDH feature codes).
- Getty TGN (Hierarchical spatial validation).
- GEOLocate Web Services API (Parsing verbatim descriptions into point-radius metadata).
- GBIF / iDigBio API (Validating coordinates against known species density distributions).
- Google Maps Platform / Mapbox APIs (Used strictly for modern precision mapping via component-restricted lookups).

## Task 2: Pipeline State Machine & Agent Flow Design
Outline the step-by-step logic gates for the autonomous pipeline. Explain how the pipeline handles:
- Ambiguous names (e.g., "Siberia" or "Jones Farm").
- Anachronism Filtering (Ensuring a resolved city wasn't founded *after* the specimen collection date).
- Confidence Scoring (How the pipeline calculates an algorithmic reliability metric for each record).
- Human-in-the-loop (HITL) fallback conditions (When a record should be flagged for museum curator review instead of auto-committing).

## Task 3: Data Schema & Target Integration Planning
Define how the pipeline maps outputs directly into the Darwin Core (DwC) standard and the extended Access to Biological Collection Data (ABCDG) format for geological data. Detail the exact target columns (e.g., verbatimLocality, locality, decimalLatitude, decimalLongitude, coordinateUncertaintyInMeters, geodeticDatum, georeferenceRemarks).

## Task 4: Concrete Code Blueprint
Provide a robust Python code framework illustrating the core orchestration. This blueprint must include:
- A pipeline class with async workers.
- The structured fallback/routing logic from Tier 1 to Tier 2.
- A functional example of a Wikidata SPARQL query payload that pulls historical names and coordinate windows based on a target year constraint.

---

# Expected Output Format
Deliver your response as an extensive, production-ready implementation plan broken into clean Markdown headers:
1. Executive Summary & Core Paradigm Shift
2. Comprehensive Technical Analysis of API Endpoints
3. Algorithmic Flowchart & State Machine Logic (using clear text or Mermaid notation)
4. Darwin Core & Data Integrity Schema Mapping
5. Python Code Blueprint & Orchestration Framework
6. Immediate Next Steps for Phase 1 Prototyping
