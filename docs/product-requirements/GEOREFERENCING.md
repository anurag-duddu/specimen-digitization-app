# Retrospective georeferencing: a plan for the harness's geography tool

**Status:** Proposed, not accepted by the owner (G12). Until the owner accepts it, the harness keeps its Google Maps geography tool (G10).

**Last verified:** 2026-09-23

**Scope:** How the harness's geography tool turns historical locality text into country, province or state, county and city values and a point-radius georeference, with typed outcomes and provenance: first for the Insects pilot, then for the Botany, Zoology, Geology and Anthropology profiles. The plan changes no queue logic (G5) and no code by itself.

**Author:** session S8 (research), for the owner's review

The plan rests on the ten pilot slides (four distinct localities, read by S8), eleven research reports whose sources are listed at the end, S4's draft interface for the geography tool, and a read-only probe, `scripts/research/georeferencing/pilot_probe.py`, which made 72 anonymous requests to Wikidata, the GeoNames dumps, GBIF and OpenTopoData on 2026-09-23; all 72 succeeded. Repository references are `file:line` on `origin/main` at 709ae3c (unchanged at 7e3afb8). Owner decisions G1 to G18 are in `docs/execution/golive/PLAN.md` section 2.1; G19 to G26, taken on 2026-09-23, are recorded there by the coordinator's open pull request #87, and G27, the owner's ruling on D14 of the same day, by the coordinator. Each choice the owner must confirm is marked **(Owner decision Dn)** and listed under [Owner decisions](#owner-decisions).

## 1. Executive summary and the core paradigm shift

Today the geography tool (`application/geography.py`) sends one literal to GBIF's GADM search and marks every candidate `unresolved` when a visit date is present (97-99), so every dated record ends in review, and the planner asks it only for `province_state` (`evidence_runtime.py` 556-559). G10 names Google Maps as the initial tool. The pilot shows why looking up a string cannot resolve 1946 labels:

1. **No gazetteer knows the Davao "Mt. McKinley".** The expedition's narrative says the names Mount McKinley and Mount Washington "appear on no maps that we have seen"; they came from a US Army intelligence report [S1]. Wikidata's search for "Mount McKinley" returns seven hits, none in the Philippines, Denali first [S2]. GeoNames, NGA GNS, Getty TGN and GEOLocate hold no Philippine peak of that name, and OpenStreetMap has none within 15 km of Mount Apo [S3][S4][S5][S6][S7].
2. **Jurisdictions changed.** "Davao Prov." in 1946 is the province of 1914-1967 (Wikidata Q15095071), divided in 1967 into Davao del Norte, Davao del Sur and Davao Oriental [S8][S2]. GeoNames and GNS carry "Davao Province" only as an alternate name of modern Davao del Norte (GeoNames 1715347), so a name match maps the whole 1946 province onto one of its five modern pieces [S3][S4].
3. **The museum's published georeferences disagree.** For "Mt McKinley, E slope" GBIF holds two points 23.58 km apart (Latlong.net; MaNIS); the probe read SRTM elevations of 1,318 m and 1,733 m there, neither within 150 m of the labels' 6,400 ft (1,951 m) or 3,300 ft (1,006 m). The point for "Mt Apo, east slope, Todaya" lies 0.64 km south-west of the summit, at 2,599 m in SRTM, with a stated uncertainty of 5.16 m; the Todaya camp was at 2,800 ft [S1][S9].
4. **The commercial path cannot hold the result.** Google's terms limit caching of Geocoding API coordinates to 30 days and bar content derived from Google Maps Content, so a Google coordinate cannot be the stored or GBIF-published georeference [S10]. The owner has since narrowed this further (G26, 2026-09-23): from Google geocoding the pipeline keeps only the place ID, its own outcome and a response fingerprint, and drops Google's names, address parts and coordinates everywhere, traces included. GEOLocate returned no uncertainty for any Philippine or Guatemalan query and ignored its `state` parameter there [S6].

The plan keeps one geography tool behind the harness's typed seam, S4's `geography_lookup`. Inside it a deterministic state machine runs four tiers: institutional and expedition knowledge (tier 0), historical resolution (tier 1), modern jurisdiction and coordinates (tier 2), uncertainty and validation (tier 3). The tool returns one of the eleven `LookupStatus` outcomes per field key with its candidates, and the existing policy decides the queue (G5). Openly licensed sources supply the names, the modern units and the coordinate of record **(Owner decision D2)**; under G26 Google can at most confirm that a place exists, leaving only its place ID, outcome and fingerprint **(Owner decision D1)**. The first table below contrasts the two approaches; the second gives the plan's expected outcomes for the pilot (details in 3.6).

| | Geocode a string (today, G10) | Reconstruct, then measure (proposed) |
|---|---|---|
| Question | Where is this text on a modern map? | What did the collector mean on the collection date, and how sure are we? |
| Input | one literal | every location literal with provenance, the parsed collection date, collectors, the profile |
| Output | a pin chosen from a modern index | a point-radius georeference with sources, or an abstention with ranked candidates |
| Uncertainty | none; Google's viewport is a display hint [S11] | computed per the Georeferencing Best Practices [S12][S13] |
| Failure mode | a confident wrong anchor, such as Denali for "Mount McKinley" | a typed `no_match`, `ambiguous` or operational outcome |
| Storage | Google coordinates cached 30 days at most [S10] | CC0 and CC BY coordinates with attribution; the verbatim text is immutable (PRD 12.4) |

| Locality (slides) | Georeference outcome | Reason |
|---|---|---|
| E. slope Mt. McKinley, 6,400 ft and 3,300 ft, Sept. 1946 (105526321-326) | `ambiguous`: needs human review | no gazetteer match; an unconfirmed crosswalk hypothesis (Mount Talomo); the museum's points conflict |
| E. slope Mt. Apo, Nov. 1946 (105526327) | `ambiguous` from gazetteers; `success` once the itinerary is confirmed (D3) | two "Mount Apo" features in 1946 Davao Province; the itinerary excludes one |
| Yepocapa, Chimaltenago, 4,800 ft, Apr. 1948 (105526328-330) | `success` | one town; elevation supports it; "Chimaltenago" read as Chimaltenango, literal kept |

### 1.1 Fit with the repository and S4's interface

| Topic | Today on `main` | S4's draft `geography_lookup` (T3a, `application/harness_tools.py`, not merged) and this plan |
|---|---|---|
| Seam | `AuthorityTool.lookup(AuthorityQuery) -> AuthorityResult` (`evidence_harness.py` 343-346), specified as `LookupAdapter.execute(request, context) -> LookupResult` (`CONTRACTS.md` 258-264) | `GeographyQuery -> ToolResult`; the profile maps fields to tool ids (`CollectionProfile.field_tools`, S3) and sends country, province_state, county, city and precise_location to `geography_lookup`; an accepted plan replaces the implementation under that id and the harness does not change |
| Input | one literal, with the visit date as `historical_context` (`authority_registry.py` 37-43; `evidence_runtime.py` 584-586) | one call per record: `literals` (field key, the exact transcript substring, source observation and region) and `context` (four elevation literals, date literals with parsed partial dates, collectors, collection and profile ids) |
| Output | one `status` and `AuthorityCandidate` rows (`authority_registry.py` 111-138) | a call `outcome`, `field_outcomes`, `PlaceCandidate` and `GeoreferenceCandidate` lists, `checks` and `sub_calls` (section 5) |
| Planning, dates | `province_state` only (`evidence_runtime.py` 556-559); any date makes candidates `unresolved`, hence `ambiguous` (`geography.py` 97-99) | every geography field in one call; dates parsed by the harness only as written, and they clear at the precision written; a two-digit year reads as 19xx for Insects (owner decision G24, 2026-09-23); slide-preparation codes are never dates |
| Cost | `execute_one` refuses a non-zero cost reservation (`evidence_harness.py` 424-425) | open sources are free; Google needs a cost path only if D1 keeps it |
| Coordinates | no georeference type (`domain.py` 196-204) | `GeoreferenceCandidate`; the G10 Google tool leaves it empty and keeps only the place ID, the outcome and the response's SHA-256 (G26); before T3a merges, `AuthorityCandidate.context_json` |
| Registry, retries | `AuthorityRegistry(version="unconfigured")` (`production.py` 628-633); `retry_after`, `retry_delay` (`reliability.py` 25-47); `Workflow.schedule_retry` (`workflow.py` 555-560, 641-650) | each source registered per scope and classification; short waits inside the tool, a longer `Retry-After` back to the workflow |

## 2. Technical analysis of the sources

| Source | Tier and role | Access and limits | License or terms | Pilot result (2026-09-23) | Verdict |
|---|---|---|---|---|---|
| Crosswalk and expedition itineraries (new, FMNH) | T0: historical names to modern candidates; dated camps with elevations | versioned reference data curated by people, never model output | FMNH, from published sources | "Mount McKinley (Davao, 1946)" to Mount Talomo, a hypothesis of moderate confidence; McKinley 6,400-ft camp 1-12 Sept., base camp at 3,300 ft 9 Aug.-6 Oct. 1946; Apo camps of November 1946 at 2,800-9,000 ft [S1] | build **(Owner decision D3)** |
| GBIF occurrence search, FMNH records | T0: the museum's published georeferences for the same strings | anonymous; no published rate, HTTP 429 under load; `locality` and `recordedBy` match exact strings [S14] | per dataset: CC0, CC BY or CC BY-NC [S9] | McKinley: 2 clusters 23.58 km apart; Apo: 2 clusters 2.61 km apart; Yepocapa: 10 clusters up to 28.93 km apart | candidates only **(Owner decision D4)** |
| Wikidata Action API (`wbsearchentities`) | T1 discovery | anonymous with a descriptive User-Agent [S15]; 0.2-0.4 s a call, never throttled in 20+ calls | CC0 [S15] | "Mount McKinley": 7 hits, none in the Philippines; "Chimaltenago": none, though CirrusSearch `Chimaltenago~1` finds Chimaltenango [S15] | use |
| Wikidata Query Service (SPARQL) | T1 enrichment of known items: start (P571, P580), end (P576, P582), successors (P1366), parents (P131), point (P625) | anonymous; 60 s deadline; HTTP 429 with `Retry-After` [S16], 120 s after S8's second request; a label search took 14-42 s | CC0 | Q15095071 valid in 1946; Mount Apo Natural Park (Q1504280) founded 2004-02-03 | enrichment only |
| GeoNames dumps and web service | T1 bulk gazetteer, loaded locally | dumps anonymous, updated daily; web service needs a username, 1,000 credits an hour, 10,000 a day [S3] | CC BY 4.0 [S3] | "Davao Province" only on modern Davao del Norte; 118 of 141,421 PH alternate names flagged historic; "Chimaltenago" fuzzy-matches Chimaltenango | dumps as the system of record; web service deferred **(Owner decision D12)** |
| NGA GNS (ArcGIS REST) | T1 cross-check; a type per name (N approved, V variant) | anonymous; 3,000 records a request [S4] | freely available, citation requested [S4] | no McKinley peak; "Fort McKinley" as a variant only | cross-check |
| Getty TGN; World Historical Gazetteer | T1 hierarchy; corroboration | TGN SPARQL and reconciliation anonymous but degraded under scans, records now Linked Art JSON-LD, new gateway token-gated; WHG needs a token [S5] | TGN ODC-By 1.0 [S5]; WHG mixed by source | TGN historic flags and dates empty; Mount Apo filed under Cotabato; no Yepocapa; WHG refused anonymous calls | defer (D12) |
| PSGC (PSA) | T1 modern Philippine units | `psa.gov.ph` refuses scripts; community mirror stale since 2022-08-27 [S17] | no explicit license found | not used | publication files later |
| GADM through GBIF's reverse geocoder; geoBoundaries | T2 containment evidence (`GBIF.md` 254-274); polygons for radials | anonymous; limits undocumented [S14] | GADM non-commercial, no redistribution without permission; geoBoundaries CC BY 4.0 [S18] | the Apo summit area sits on a three-province boundary (North Cotabato at distance 0, Davao del Sur about 90 m away) | evidence only; geoBoundaries a Phase 1 candidate |
| Google Geocoding API | T2 existence check | key; 10,000 free Essentials calls a month, then USD 5.00 per 1,000; only `country` and `postal_code` components restrict [S11] | coordinates cached 30 days at most, `place_id` indefinitely, no content derived from Maps Content [S10]; G26 keeps only place ID, outcome and fingerprint | not called: no key yet, and paid calls are refused | existence check only (D1) |
| Mapbox Geocoding v6 | none | token; 1,000 requests a minute [S19] | no redistribution, even of paid permanent geocodes [S19] | not called | do not use |
| Nominatim, Overpass (OpenStreetMap); Mapcarta | T2 check that a feature exists | Nominatim 1 request a second, no bulk; the public Overpass server warns of overload [S7] | ODbL: a stored coordinate table may be a derivative database [S7] | Apo tagged `natural=volcano`, not `peak`; no "McKinley" within 15 km; two Overpass timeouts | corroboration only; Mapcarta is built from OpenStreetMap, Wikidata and GeoNames, so query those [S7] |
| Point-radius method | T3 uncertainty, computed in-house | not applicable | open guides [S12][S13][S20] | no service returned an uncertainty outside the USA | build **(Owner decision D13)** |
| GEOLocate | T3 candidate source, USA only | anonymous; no published limit; the community paces 3 s a request [S6] | no published web-service terms [S6] | `state` ignored outside the USA; uncertainty "Unavailable"; Apo tied with a Makati "Mount Apo" | not for non-US localities |
| SRTM through OpenTopoData; Copernicus GLO-30 | T3 elevation: research; production | OpenTopoData 1 request a second, 1,000 a day, 100 points a request; Copernicus tiles on anonymous S3 [S21] | per dataset; Copernicus free with attribution to DLR and Airbus [S21] | every pilot point; SRTM LE90 is 16 m [S21] | research only; Copernicus for production **(Owner decision D11)** |
| iDigBio, Bionomia | T3 corroboration; collector itineraries | anonymous [S22] | per record | FMNH Philippines 1946-47: 8,674 records, against 8,752 on GBIF | later |
| Macrostrat, PBDB, Mindat; Pleiades, PeriodO, Local Contexts | T3 Geology (formation, fossils, minerals); T1 and T3 Anthropology (ancient places, periods, governance) | Mindat and Local Contexts need keys; the others are anonymous [S23][S24][S25] | Macrostrat CC BY 4.0, PBDB unverified [S23]; Mindat CC BY-NC-SA 4.0 with beta limits [S24]; Pleiades CC BY 3.0, PeriodO public domain [S25] | Apo point: Cenozoic volcanic rocks; Mindat refused anonymous calls | per profile (3.7) **(Owner decision D10)** |

S4's Google rules in T3a and S8's refinements map Google's statuses onto the eleven outcomes [S11]. Because `administrative_area` and `locality` only bias a query, a 1946 "Davao Province" request can return `OK` anchored on a centroid, so an approximate location never counts as a point georeference.

| Outcome | Google | Outcome | Google | Outcome | Google |
|---|---|---|---|---|---|
| success | one result, no `partial_match` (S4); a type that fits the feature class (S8) | no_match | `ZERO_RESULTS` | rate_limited | `OVER_QUERY_LIMIT` |
| ambiguous | `partial_match` or several results (S4); a feature only at `APPROXIMATE` or `GEOMETRIC_CENTER` (S8) | empty_response | an empty or non-JSON 200 body | timeout | connection timeout |
| authentication_error | `REQUEST_DENIED` for a missing, bad or rejected key (S4) | authorization_error | `REQUEST_DENIED` for key restrictions; `OVER_DAILY_LIMIT` for billing | provider_error | `UNKNOWN_ERROR` |
| malformed_response | an unparseable body; S8 also files `INVALID_REQUEST` here as an adapter defect | policy_blocked | not a Google status: the registry or D1 | | |

Corrections to the charter:

1. P1365 is "replaces" and points to the predecessor; P1366 is "replaced by" and points to the successor. The charter has them reversed [S2].
2. GeoNames' historical codes exist (PCLH, ADMDH, ADM1H to ADM5H, PPLH) but are sparse: the 1914-1967 Davao Province has no historical record, although Maguindanao has one (ADM2H 1703701) [S3]. Getty TGN's historic flags and dates come back empty [S5].
3. GEOLocate cannot supply uncertainty outside the USA [S6], and Google's component filtering restricts only by country and postal code [S11]; the pipeline computes uncertainty itself (D13).
4. "ABCDG" is the Extension for Geosciences (EFG) built on ABCD 2.06, and neither is currently ratified (section 4) [S26][S27].

## 3. State machine and logic gates

### 3.1 States and gates

```mermaid
stateDiagram-v2
    [*] --> Intake
    Intake --> NoMatch: no locality literal
    Intake --> Parse: literals with evidence ids
    Parse --> Context: parts, expansions, reader variants
    Context --> Resolve: date, collectors, expedition, profile
    state Resolve {
        [*] --> Tier0
        Tier0 --> Tier1: crosswalk, itinerary, museum points
        Tier1 --> Hierarchy: names valid on the date
        Hierarchy --> Tier2: inside the label's historical units
        Tier2 --> Uncertainty: modern unit, storable coordinate
        Uncertainty --> Validation: point-radius per feature
        Validation --> [*]
    }
    Resolve --> Operational: rate limit, timeout, provider, auth, malformed, policy
    Operational --> Resolve: bounded retry, backoff, jitter
    Operational --> Blocked: retries spent or not retryable
    Resolve --> Decide: candidates, signals, review-priority score
    Decide --> Success: one feature passes every gate and the cut-off
    Decide --> Ambiguous: several features, hypothesis, conflict, low score
    Decide --> NoMatch: no candidate survives
    Decide --> EmptyResponse: every source returned an empty body
```

Any state that calls out can leave for the operational branch. Rate limits, timeouts and provider errors retry inside the tool while the wait is short; a longer `Retry-After` goes back to `Workflow.schedule_retry`. What remains is an operational block (QUE-005), never Deferred and never a review item.

| State | What it does | Hard gate | When the gate fails |
|---|---|---|---|
| Intake | receives every location literal with provenance, including locality text outside a field ("Mindanao") | at least one locality literal | `no_match`, reason `no_locality_literal` (105526324-328 if the right-hand label is not segmented) |
| Parse | a deterministic grammar and a versioned abbreviation table (Mt. to Mount, Prov. to Province, Mun. to Municipality, P.I. to Philippine Islands); direction-only offsets ("E. slope of X"); elevations with units | a unit is never guessed | that elevation's check is `not_assessable` (on 105526322 both readers dropped the foot mark: "Elev. 6400") |
| Context | collection date from the harness's parsed dates (G24: parsed as written, two-digit years as 19xx for Insects); collectors; expedition | the tool infers no date of its own (HAR-019); preparation codes such as 10-6-78-1a or IX-17-66-2 are never dates | with no parsed date the anachronism filter runs as undated; an itinerary match counts only under D3 |
| Tier 0 | crosswalk, itinerary, the museum's published points | only curator-confirmed entries resolve | an unconfirmed entry is a hypothesis: `ambiguous` at best |
| Tier 1 | Wikidata search and enrichment, the GeoNames dump, GNS; fuzzy matching bounded to edit distance 1-2 | country, feature class, anachronism filter (3.2) | candidate dropped; a fuzzy match is a recorded normalization and the literal stays |
| Hierarchy | tests each candidate against the label's historical path, as the union of its successor units | inside the label's units | candidate dropped (Iloilo's "Apo Mountain") |
| Tier 2 | modern units through successors and containment; the coordinate of record from storable sources; Google only as D1 allows | a storable source for the coordinate | `ambiguous`, reason `coordinate_not_storable` |
| Uncertainty | corrected center, geographic radial, direction-only sector, precision and datum (3.8) | one feature: unrelated same-name features are not georeferenced [S13] | `ambiguous` |
| Validation | checks typed `supports`, `conflicts` or `not_assessable`: containment, DEM elevation (feet become meters only inside the comparison, G22), itinerary, occurrences, profile checks (3.7) | no conflict beyond tolerance (D5) | `ambiguous`, with the conflict as reason |
| Decide | review-priority score (3.4); one outcome per field key into `field_outcomes` | at or above the cut-off (D5) | `ambiguous` |

### 3.2 Anachronism filter

- An interpretation is valid when its start is on or before the collection date and its end on or after it, with the start from P571 or P580 and the end from P576 or P582 [S2]. Validity has three states, valid, not valid and undated; undated interpretations stay, flagged and weighted lower, because P131 statements often carry no dates. A partial date is an interval, and an interpretation must be valid across all of it.
- A place founded after the collection date leaves the historical interpretation. The probe excluded Mount Apo Natural Park (Q1504280, inception 2004-02-03) for the 1946 Apo label, and Davao del Norte, a 1967 successor, cannot be the 1946 "Davao Prov." although GeoNames and GNS carry that alternate name.
- Label lag: printed names outlive their jurisdictions. "P.I." on labels of September 1946 uses the colonial name two months after independence on 4 July 1946, when the Commonwealth (Q146328) ended [S2]. Such a name is accepted with a `label_lag` flag when the gap is within the tolerance **(Owner decision D5)**; "Philippine Islands" is also an English alias of the modern Philippines (Q928), so `country` resolves to Q928 either way.
- The modern jurisdiction is present-day by definition: it is reached through successors (P1366) and point containment and is never filtered by founding date.

### 3.3 Ambiguous names

- "Siberia": the first page of Wikidata results holds ten or more senses, among them the region, albums, an opera, an asteroid and a Mexican settlement [S15]. Only evidence on the record separates them: the country literal, the label's hierarchy, a feature class that fits the phrase, validity on the date and the expedition. If more than one unrelated sense survives, the outcome is `ambiguous` with ranked candidates, and the most prominent sense never wins by default [S13]. The same holds for same-name features inside one unit, such as the two "Mount Apo" in 1946 Davao Province, 92.7 km apart.
- "Mount McKinley": without the country gate the first hit is Denali, a silent wrong answer. Feature class is a gate too: inside the Philippines the "Philippine Islands" search also returns a 1941-42 military campaign (Q696462) and a Wikimedia list article (Q2389438).
- "Jones Farm": a private name missing from gazetteers is `no_match` for the feature. The tool adds a coarse candidate, the smallest enclosing unit on the label with its corrected center and radial, labeled `coarse_admin`, that never clears automatically **(Owner decision D6)**. The rule follows the owner's decisions that dates clear at the precision written (G24) and a genus-only label is satisfied by a confirmed genus (G25): a georeference clears at the precision the label states, so a label that names only a province can clear with the province's radial, while a fallback to an enclosing unit because the named place was not found is coarser than written and goes to review.
- Reader variants: where the readers disagree on a toponym (handwriting-qwen "Chimaltenango", handwriting-muse "Chimaltenago" on 105526329-330), both forms become query variants and the adjudicated literal stays the field literal. The label reads "Chimaltenago" on all three slides; Qwen silently corrected it. Under G20 a lookup that confirms exactly one reader's literal settles a disagreement, and a gazetteer confirms Qwen's corrected spelling exactly, so G20 would record a spelling the label does not have. The owner decided this case (G27, 2026-09-23, D14): "raw transcript anyway will have exactly as written, for verbatim field it will be as written but final location will be exact actual as settled by harness. we are always capturing both so there isn't an issue if people want to change later". The lookup therefore confirms the place: the tool returns the settled place (Chimaltenango) as the field's final value, with both reader forms and their provenance, so the verbatim keeps the label's spelling ("Chimaltenago") and both are stored. The field can clear on the settled place; the reader disagreement is recorded as a check with the reason `spelling_disagreement` and does not send the field to review.

### 3.4 Confidence score

Hard gates come first; after them a transparent score ranks candidates and sets the success cut-off. Like the repository's other measures (`bounded-levenshtein-fraction-v1`; `review_risk.py`, "explainable uncalibrated triage"), it is labeled review priority and is uncalibrated: it can demote a would-be success to `ambiguous` but never promote a candidate past a gate. Calibration uses curator-verified georeferences (section 6); the thresholds are owner decisions (D5).

| Component | Values (proposed) | Weight (proposed) |
|---|---|---|
| Name match | exact 1.0; alias 0.9; historic alias or confirmed crosswalk 0.8; fuzzy at edit distance 1 0.6, at 2 0.4 | 0.25 |
| Temporal validity | valid 1.0; label lag 0.7; undated 0.6 | 0.15 |
| Hierarchy consistency | supports 1.0; not assessable 0.5 (a conflict is a hard gate) | 0.20 |
| Independent sources | two or more storable sources agreeing 1.0; one 0.5; copies of one source count once | 0.15 |
| Uncertainty radius | 1 minus the radius over the profile's maximum, not below 0 | 0.10 |
| Validation checks | the share of assessable checks that support | 0.15 |

### 3.5 Human-in-the-loop conditions

| Condition | Field outcome | Queue under the existing policy |
|---|---|---|
| no candidate in any tier | `no_match` | needs human review (QUE-003, G6) |
| every source returned an empty body | `empty_response` | needs human review |
| several unrelated features; only an unconfirmed tier-0 hypothesis; a conflicting check; a radius above the profile maximum; a score below the cut-off; a coordinate only from a non-storable source | `ambiguous`, with reasons | needs human review (conflicting evidence; missing or ambiguous field) |
| a named place not found, only a coarse administrative candidate (coarser than written) | `no_match` with the `coarse_admin` candidate | needs human review, never automatic (D6) |
| a sensitive locality under the profile | `policy_blocked`, reason `sensitive_locality` | review or operational block per profile (PRD section 15); today's code treats every `policy_blocked` as operational |
| a rate limit, timeout or provider error after retries; missing or bad credentials, such as no Google key yet; a malformed response | the matching operational outcome | operational block, never Deferred (QUE-005) |
| exactly one feature passes every gate and the cut-off | `success` | cleared only if every other gate passes (G1, QUE-002) |

Under G1 a value the harness resolves is cleared, which is why `success` is earned through hard gates rather than a score. PRD 12.4 leaves open whether a Google-only or Mapcarta-only match can support clearance; this plan answers no, pending D1. Under G26 a Google `success` leaves only a place ID behind: a reviewer cannot see which place matched, and Google has no historical units, so for a label that predates a jurisdiction change (a 1946 "Davao Prov.") its match is a modern candidate, never evidence of the historical jurisdiction.

### 3.6 Worked examples: the four pilot localities

**Mt. McKinley** (105526321-326). Tier 1 finds no Philippine "Mount McKinley" in Wikidata or the GeoNames dump. "Davao Prov." resolves to Q15095071, valid in 1946, with three successors; "P.I." resolves to Q928 with `label_lag`. Tier 0 offers the crosswalk hypothesis Mount Talomo (Wikidata Q31472786, GeoNames 1683778; 7.0364, 125.3125; GADM Philippines / Davao del Sur / Davao City) and matches the itinerary: 3 and 6 September fall within the 6,400-ft camp (1-12 September) and 14 September within the 3,300-ft base camp (9 August to 6 October) [S1]; G24 reads the two-digit years on 105526321 and 324-326 as 1946, so the match holds on day, month and year. On an SRTM transect due east from Talomo's summit (2,620 m) the ground falls to 1,915 m at 1.5 km, near the 6,400-ft level (1,951 m), and crosses the 3,300-ft level (1,006 m) between 8 and 8.5 km; it climbs again to 1,795 m at 4.5 km, so a one-dimensional distance rule would misplace camps. The museum's two points conflict with both label elevations and lie 7.2 km north and 16.4 km south-south-east of Talomo. Outcome for the georeference: `ambiguous`, reviewed with three candidates and the transect until a curator rules on the crosswalk (D3). `province_state` succeeds on its historical interpretation (Q15095071, valid in 1946) and `country` on Q928; the modern unit (Davao City or a Davao del Sur municipality) waits for the point and travels as an open modern candidate. The labels name no county or city and give one elevation in feet, so under today's mandatory fields these slides go to review whatever the georeference (D7, G8, G22).

**Mt. Apo** (105526327). Wikidata gives Mount Apo (Q455963; 6.9875, 125.2708; 2,954 m) and excludes Mount Apo Natural Park as founded in 2004. GeoNames gives 1730340 (SRTM 2,927 m), 6569865 near Malita (92.7 km away, SRTM 640 m, inside 1946 Davao Province [S1]) and 1730339 "Apo Mountain" in Iloilo, which the hierarchy gate drops. From gazetteers alone two unrelated features remain, so the outcome is `ambiguous` [S13]. The itinerary puts every camp of November 1946 on the main massif between 2,800 and 9,000 ft, and the four camps Hoogstraal calls east slope at 4,300-7,700 ft [S1]; a point at 640 m (about 2,100 ft) is below all of them. G24 reads the label's "'46" as 1946, so the match rests on collector, mountain, slope, month and year, and it counts once a curator has confirmed the itinerary (D3). Then one feature remains and the georeference is its east-slope sector (3.8): `success`, provided the sector's containment in the Davao successor units supports it (not yet computed); with no elevation on the label, that check is `not_assessable`. The museum's point for "east slope, Todaya" and "Baclayan" (0.64 km south-west of the summit, SRTM 2,599 m, stated uncertainty 5.16 m) falls outside the sector; it is shown as a candidate, and its disagreement travels in `checks` for a `warning` finding, which does not block clearance (D4).

**Yepocapa** (105526328-330). Tier 1 gives the municipality item Q1523937 (point 14.5, -90.95; parent Chimaltenango), the settlement Q25173824, and GeoNames' town 3587636 (PPLA2; 14.50195, -90.95396) and municipality 3587635 (ADM2; 14.46725, -90.97416). "Chimaltenago" has no Wikidata hit; the GeoNames fuzzy match returns the department of Chimaltenango (ADM1 3598571) and a municipality of that name (ADM2 3598570), and the label's order and Yepocapa's parent select the department: a normalization at edit distance 1, with the literal kept. Against 4,800 ft (1,463 m, converted inside the check only, G22), SRTM gives 1,427 m at Q1523937 (-36 m, supports), 1,396 m at the town (-67 m, supports) and 1,134 m at the municipality centroid (-329 m, conflicts), so the feature is the town, not the centroid. Q25173824 carries exactly GeoNames' coordinates, so S8 counts the two as one source; Q1523937 is a second point 0.48 km away. Five of the museum's ten published clusters carry only the town's name: three lie within 0.5 km of the GeoNames town point and support the label elevation, and two lie 6.1 km and 22.9 km away and conflict with it. G24 reads the two-digit years on 105526328-329 as 1948; no candidate carries a validity window, so the anachronism filter removes nothing. Outcome: `success`, with GeoNames 3587636 (CC BY 4.0) as the coordinate of record, the radius from the town's extent in Phase 1, `province_state` Chimaltenango, and the municipio and town of Yepocapa as `county` and `city` (D8).

### 3.7 Checks per collection profile

Profiles choose the checks. A record's profile comes from the collection it was uploaded or imported into, resolved down the collection tree (G14; `COLLECTION_HIERARCHY.md` 73-76), which S3 is building.

| Profile | Checks | Notes |
|---|---|---|
| Zoology, Botany | containment, DEM elevation, itinerary, GBIF records of the same collector within 30 days (supports), taxon plausibility (weak) | a stated uncertainty under 100 m on a historical text locality is a red flag |
| Geology | containment, stratigraphic plausibility (Macrostrat, PBDB), `GeologicalContext` terms | Mindat only after D10 |
| Anthropology | a sensitivity gate before any external call: ARPA, NHPA section 304, the 2024 NAGPRA rule (43 CFR 10.9), CARE, Local Contexts [S28][S25] | withholds or generalizes coordinates and routes to review (D10) |

### 3.8 Point-radius geometry

The corrected center is the center of the smallest circle enclosing the feature, and the geographic radial runs from it to the farthest boundary point [S13]. A direction-only offset extends the feature within a cone set by the heading's precision until a constraining boundary [S13]; a cardinal heading such as "E" carries plus or minus 45 degrees [S12]. S8 reads "E. slope of X" as the part of X's circle (radial R) inside that cone, a quarter circle bounded by X itself. Its smallest enclosing circle has the chord between the arc ends as diameter: center 0.707 R from X's center along the heading, radius 0.707 R. This is S8's derivation from the QRG 2.2.2 geometry, to be checked against the Calculator [S20]. Coordinate precision, an unknown datum (worst case 5,359 m) and measurement error then combine by the Calculator's method, not by addition [S12] (D13). No pilot locality has a measured feature boundary yet, so this plan states no radius in meters for any of them.

## 4. Darwin Core and data integrity mapping

Darwin Core, term list version 2026-05-26, is the normative output [S29]. The charter's "ABCDG" is the ABCD Extension for Geosciences (EFG), built on ABCD 2.06, which was ratified on 2005-09-16 [S26]; a 2022 TDWG paper reports that both still needed (re-)ratification under the Standards Documentation Specification, and no later confirmation was found [S27]. ABCD 3.0 is not ratified [S26]. ABCD 2.06 with EFG is therefore a secondary export for Geology.

### 4.1 Field mapping

| App value | Darwin Core terms | Treatment |
|---|---|---|
| label transcript, all lines | `verbatimLabel` (MaterialEntity, added 2023-08-21) [S29] | verbatim |
| `precise_location` | `verbatimLocality`; `locality` | verbatim and never replaced; `locality` is the interpretation and may equal it |
| `country`; `province_state`, `county`, `city` | `country`, `countryCode`; `stateProvince`, `county`, `municipality` | modern names; ISO 3166-1 alpha-2 (D8) |
| historical path, successor chain | `higherGeography`; `locationRemarks` | historical units as interpreted, such as "Philippine Islands \| Mindanao \| Davao Province (1914-1967)" (D8) |
| the four elevation fields | `verbatimElevation`; `minimumElevationInMeters`, `maximumElevationInMeters` | verbatim; nothing is derived, neither a conversion nor a filled-in endpoint (G22), so a label in feet fills only `verbatimElevation` and the meter terms come only from a label that states meters; the elevation check converts feet to meters inside its comparison and stores no field value |
| `GeoreferenceCandidate` | `decimalLatitude`, `decimalLongitude`, `geodeticDatum` (EPSG:4326), `coordinateUncertaintyInMeters`, `coordinatePrecision`, `pointRadiusSpatialFit`; for a sector, `footprintWKT`, `footprintSRS`, `footprintSpatialFit` | interpreted |
| process metadata | `georeferencedBy` (pipeline name and version, D8), `georeferencedDate` (ISO 8601), `georeferenceProtocol` (the Best Practices and an in-house protocol), `georeferenceSources` (each source with version and access date), `georeferenceRemarks`, `georeferenceVerificationStatus` | a new georeference starts as "requires verification" [S12] |
| sensitivity | `informationWithheld`, `dataGeneralizations` | as in 4.5 [S30] |

### 4.2 Historical and modern jurisdictions

Darwin Core prescribes no convention for historical against modern jurisdictions [S29]. S8 proposes **(Owner decision D8)**: `verbatimLocality` as written; `higherGeography` the historical path as interpreted; `stateProvince`, `county` and `municipality` the modern units; `locationRemarks` the successor chain, such as "Davao Province (1914-1967), divided by RA 4867 into Davao del Norte, Davao del Sur and Davao Oriental" [S8]. Two conventions need a curator. Davao City has been chartered apart from the province since 1936 and stayed outside the 1967 provinces [S8], while GADM files it under Davao del Sur [S14]. A Guatemalan municipio is the second-level unit, so S8 maps it to `county` and the town to `municipality`. Modern units come from coordinates only when the whole uncertainty circle lies inside one unit **(Owner decision D7)**.

### 4.3 Example: Yepocapa, slide 105526329

| Term | Value |
|---|---|
| verbatimLocality; locality; higherGeography | Yepocapa, 4800 ft. / Chimaltenago, / Guatemala; Yepocapa; Guatemala \| Chimaltenango \| Yepocapa |
| country; countryCode; stateProvince | Guatemala; GT; Chimaltenango |
| county; municipality | Yepocapa (municipio, GeoNames 3587635); Yepocapa (town, GeoNames 3587636) |
| verbatimElevation; minimumElevationInMeters, maximumElevationInMeters | 4800 ft.; not written (G22: no conversion) |
| decimalLatitude; decimalLongitude; geodeticDatum; coordinatePrecision | 14.50195; -90.95396; EPSG:4326; 0.00001 |
| coordinateUncertaintyInMeters; pointRadiusSpatialFit | computed in Phase 1 from the town's extent; not stated here |
| georeferencedBy; georeferencedDate; georeferenceProtocol | specimen-digitization `geography_lookup` geo-tiered-0 (automated); 2026-09-23; Georeferencing Best Practices v1.2.1 and Quick Reference Guide, with an FMNH protocol still to be written |
| georeferenceSources | GeoNames GT dump (CC BY 4.0); Wikidata Q1523937 (CC0); SRTM 30 m through OpenTopoData; GBIF reverse geocoder (GADM); all accessed 2026-09-23 |
| georeferenceRemarks; georeferenceVerificationStatus | Town point, not the municipality centroid (GeoNames 3587635, 329 m below the label elevation); "Chimaltenago" read as Chimaltenango (edit distance 1); requires verification |
| locationRemarks | Elevation stated in feet only; the DEM check compared 4,800 ft (1,463 m) with SRTM 1,396 m at the town. |

### 4.4 ABCD 2.06 and EFG

Verify each path against the ABCD 2.06 XSD before implementing [S26]; the nesting of `CoordinateMethod` and `AccuracyStatement` differed between fetches.

| Darwin Core | ABCD 2.06 path |
|---|---|
| locality, verbatimLocality | `Unit/Gathering/LocalityText` |
| country, countryCode; stateProvince, county | `Gathering/Country/Name`, `Gathering/Country/ISO3166Code`; `Gathering/NamedAreas/NamedArea/AreaName` with `AreaClass` |
| decimalLatitude, decimalLongitude | `Gathering/SiteCoordinateSets/SiteCoordinates/CoordinatesLatLong/LatitudeDecimal`, `LongitudeDecimal` |
| geodeticDatum; coordinateUncertaintyInMeters | `.../SpatialDatum`; `.../CoordinateErrorDistanceInMeters` |
| georeferenceProtocol; georeferenceSources | `.../CoordinateMethod`, `.../AccuracyStatement` (free text); no ABCD 2.06 equivalent found |
| minimum and maximum elevation | `Gathering/Altitude/MeasurementOrFactAtomised/LowerValue`, `UpperValue` |
| GeologicalContext (EFG) | `Unit/UnitStratigraphicDetermination/...`: `ChronostratigraphicAttributions`, `LithostratigraphicAttributions`, `BiostratigraphicAttributions` |

### 4.5 Sensitive localities

Chapman (2020) generalizes a copy for distribution, never the stored record, documents it in `dataGeneralizations` and `informationWithheld`, and sets grid categories from withholding or 1 degree down to 0.001 degree [S30]. That guide addresses sensitive species. For Anthropology the ceiling comes from law and governance: NAGPRA summaries give origin at county or State level only, ARPA and NHPA section 304 protect site locations, and CARE and Local Contexts give communities authority over their data [S28][S25]. Human remains, funerary or sacred objects and points on or near tribal land go to review before any coordinate is written (D10).

### 4.6 Integrity: licenses, storage and caching

Every evidence item carries a `storable` flag set from its license; only storable sources may feed the permanent georeference.

| Source | License or terms | Storable | Feeds the stored georeference |
|---|---|---|---|
| Wikidata | CC0 [S15] | yes | yes |
| GeoNames dumps; NGA GNS; Getty TGN | CC BY 4.0 [S3]; citation requested [S4]; ODC-By 1.0 [S5] | yes, attributed | yes (D2); TGN deferred |
| DEMs; Macrostrat | public domain or free with attribution [S21]; CC BY 4.0 [S23] | yes | as evidence only |
| GBIF occurrences (FMNH) | CC0, CC BY or CC BY-NC per dataset [S9] | as evidence | candidate only (D4) |
| GADM through GBIF | non-commercial, no redistribution [S18] | as evidence | no |
| OpenStreetMap services | ODbL [S7] | corroboration only | no |
| Google; Mapbox; GEOLocate; Mindat | coordinates 30 days, `place_id` indefinitely [S10]; no redistribution [S19]; no published terms [S6]; non-commercial with beta limits [S24] | no | no (D1, D10) |

Caching follows HAR-017 and `GBIF.md` 365-397: keyed by provider, operation, complete normalized request, source release (dump date or gazetteer version) and adapter version; success, empty, ambiguous and failure entries kept apart; retention set by profile and license, at most 30 days for Google; forced refresh supported. Each sub-call becomes one S5 ToolCall row (G23). On today's seam the results fit without a domain change in `AuthorityCandidate.context_json`, `FieldCandidate.normalizedValue` (typed `Any`) and `EvidenceItem.query` (`schema.gql` 180-211); optional georeference fields in a profile are a G8 matter **(Owner decision D9)**.

## 5. Python blueprint and orchestration

The code below is illustrative, not production code. The implementation registers under S4's `geography_lookup` id; inside it adapters run tier by tier, and the sub-adapters of one tier run concurrently while an HTTP gate admits each host through the repository's `provider_circuit.ProviderCircuit`, paces it, honors `Retry-After` through `retry_after` and `retry_delay` (`reliability.py` 25-47), maps each response to one of the eleven outcomes and records a sub-call for HAR-010 (query, source, retrieval time, response digest, raw reference, license; the tool version and matched identifiers travel on the result and its candidates). S4 owns `State`, `to_tool_result` and, until T3a merges, `to_authority_result` (built on `result_base`, so the lineage check at `evidence_harness.py` 451-456 holds). S8's additions to T3a, which S4 accepted on 2026-09-23, carry the plan's output:

| T3a element (S8's addition) | Why the plan needs it | Today's `AuthorityResult` |
|---|---|---|
| `LocalityLiteral.field_key` may be empty; the full verbatim locality also travels as one unassigned literal | locality text outside a field ("Mindanao", "Mun. Yepocapa") | one `literal` per query |
| `field_outcomes: dict[field_key, LookupStatus]`, which clearance reads | one outcome per field key | one `status` per call |
| `PlaceCandidate.role` (historical or modern), `valid_from`, `valid_to`, several per field key | HAR-014 separation and the anachronism filter | `relation` and `context_json` |
| `PlaceCandidate.source`; `GeoreferenceCandidate.sources` with license | provenance and the `storable` flag | `source_id`, `license` |
| `sub_calls`, one S5 ToolCall row each (G23) | HAR-010 for every request | one `raw_ref` and `response_sha256` |
| optional: ranked `georeferences`; `coordinate_precision`, `footprint_wkt`, `spatial_fit`, `remarks`, `verification_status`, `georeferenced_by`, `georeferenced_date`; `checks`; a taxon literal | the Darwin Core metadata of 4.1 and the checks of 3.1 | `context_json` |

The Wikidata payload below enriches the items that `wbsearchentities` found and ran live on 2026-09-23. A full-graph label and alias search took S8 14-42 s against the service's 60 s deadline [S16], so discovery goes through the Action API.

```sparql
SELECT ?item (SAMPLE(STR(?label)) AS ?name) (SAMPLE(?coord) AS ?point) (MIN(?from) AS ?validFrom)
       (MAX(?to) AS ?validTo) (GROUP_CONCAT(DISTINCT ?iso; separator=" ") AS ?countries)
       (GROUP_CONCAT(DISTINCT STR(?classLabel); separator="; ") AS ?classes)
       (GROUP_CONCAT(DISTINCT STR(?nextLabel); separator="; ") AS ?replacedBy)
       (GROUP_CONCAT(DISTINCT STR(?parentLabel); separator="; ") AS ?parents)
WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) IN ("en", "mul")) }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P571|wdt:P580 ?from }
  OPTIONAL { ?item wdt:P576|wdt:P582 ?to }
  OPTIONAL { ?item wdt:P17/wdt:P297 ?iso }
  OPTIONAL { ?item wdt:P31 ?class . ?class rdfs:label ?classLabel FILTER(LANG(?classLabel) = "en") }
  OPTIONAL { ?item wdt:P1366 ?next . ?next rdfs:label ?nextLabel FILTER(LANG(?nextLabel) IN ("en", "mul")) }
  OPTIONAL { ?item wdt:P131 ?parent . ?parent rdfs:label ?parentLabel FILTER(LANG(?parentLabel) IN ("en", "mul")) }
}
GROUP BY ?item
```

```python
"""Illustrative blueprint, not production code (S8, 2026-09-23). "S4:" marks a harness choice."""
import asyncio, hashlib, json, math, time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Protocol
import httpx
from pydantic import BaseModel
from specimen_digitization.application.domain import OPERATIONAL, LookupStatus
from specimen_digitization.application.reliability import retry_after, retry_delay

ENRICH = (Path(__file__).parent / "enrich.rq").read_text()  # the tested payload above
Signal = Literal["supports", "conflicts", "not_assessable"]
RETRYABLE = {LookupStatus.RATE_LIMITED, LookupStatus.TIMEOUT, LookupStatus.PROVIDER}
HTTP = {401: LookupStatus.AUTHENTICATION, 403: LookupStatus.AUTHORIZATION, 429: LookupStatus.RATE_LIMITED}

class SubCall(BaseModel):  # one ToolResult.sub_calls entry (HAR-010), recorded by the gate per request
    source: str
    query: dict
    outcome: LookupStatus
    retrieved_at: str
    response_sha256: str | None
    license: str  # decides whether a value may be stored (section 4.6)
    raw_ref: str | None = None  # blob written by S4's storage
class Candidate(BaseModel):  # becomes a PlaceCandidate, or feeds a GeoreferenceCandidate (HAR-004, HAR-014)
    source_id: str  # "wikidata:Q1523937", "geonames:3587636"
    feature_id: str  # candidates for the same place share this id
    role: Literal["historical", "modern"]  # T3a PlaceCandidate.role
    point: tuple[float, float] | None = None
    name_match: str = "exact"  # exact, alias, historic_alias, crosswalk, fuzzy1, fuzzy2
    validity: Literal["valid", "label_lag", "undated", "not valid"] = "undated"
    signals: dict[str, Signal] = {}  # ToolResult.checks: hierarchy, elevation, itinerary, occurrence
    storable: bool = False
    hypothesis: bool = False  # tier-0 entry that no curator has confirmed yet
    museum_published: bool = False  # FMNH's own published point: shown, never support (D4)
class SourceResult(BaseModel):  # one sub-adapter run
    status: LookupStatus
    candidates: list[Candidate] = []
    calls: list[SubCall] = []
    retry_after_seconds: int | None = None
class FieldOutcome(SourceResult):  # ToolResult.field_outcomes[field_key] with its candidates
    field_key: str  # country, province_state, county, city, georeference
    reasons: list[str] = []
class SourceAdapter(Protocol):  # typed outcomes only; a sub-adapter never raises
    async def run(self, state: "State", gate: "HttpGate") -> SourceResult: ...

class HttpGate:
    """Per-host circuit and pacing, Retry-After, bounded retries with jitter, typed outcomes, provenance."""
    def __init__(self, client: httpx.AsyncClient, circuit, keys: dict, pace_s: dict[str, float], attempts=3,
                 longest_wait_s=20.0):  # circuit: provider_circuit.ProviderCircuit; keys: a CircuitKey per host
        self.client, self.circuit, self.keys, self.pace = client, circuit, keys, pace_s
        self.attempts, self.longest, self.slots, self.locks = attempts, longest_wait_s, {}, {}

    async def get(self, source: str, license: str, url: str, params: dict) -> tuple[SubCall, bytes, int | None]:
        host, status, body, wait = httpx.URL(url).host, LookupStatus.PROVIDER, b"", None
        admission = self.circuit.admit(self.keys[host], probelease_seconds=60)
        if admission.status == "permitted":  # an open circuit stays provider_error for the workflow
            async with self.locks.setdefault(host, asyncio.Lock()):
                for attempt in range(1, self.attempts + 1):
                    await asyncio.sleep(max(0.0, self.slots.get(host, 0.0) - time.monotonic()))
                    self.slots[host] = time.monotonic() + self.pace.get(host, 1.1)
                    try:
                        response = await self.client.get(url, params=params)
                        status, body = classify(response), response.content
                        hint = retry_after(response.headers.get("Retry-After"))
                    except httpx.TimeoutException:
                        status, body, hint = LookupStatus.TIMEOUT, b"", None
                    wait = retry_delay(attempt, hint)  # jitter, never earlier than Retry-After
                    if status not in RETRYABLE or attempt == self.attempts or wait > self.longest:
                        break  # a longer wait goes back to the workflow's schedule_retry
                    await asyncio.sleep(wait)
            if status in OPERATIONAL:
                self.circuit.record_failure(admission.token, status.value, hint)
            else:
                self.circuit.record_success(admission.token)
        call = SubCall(source=source, query={"url": url, **params}, outcome=status, license=license,
                       retrieved_at=datetime.now(timezone.utc).isoformat(),
                       response_sha256=hashlib.sha256(body).hexdigest() if body else None)
        return call, body, math.ceil(wait) if wait and status in RETRYABLE else None

def classify(response: httpx.Response) -> LookupStatus:
    code, kind = response.status_code, response.headers.get("content-type", "")
    if code in HTTP or code >= 500:
        return HTTP.get(code, LookupStatus.PROVIDER)
    if code >= 400 or (response.content and "json" not in kind):
        return LookupStatus.MALFORMED  # adapter defect (PRD 15), or HTML from a degraded server
    return LookupStatus.SUCCESS if response.content else LookupStatus.EMPTY

def valid_on(valid_from: str | None, valid_to: str | None, day: date, lag_years: int) -> str:  # section 3.2
    if not valid_from and not valid_to:
        return "undated"
    if valid_from and date.fromisoformat(valid_from[:10]) > day:
        return "not valid"  # founded after the collection date
    if valid_to and date.fromisoformat(valid_to[:10]) < day:
        return "label_lag" if day.year - int(valid_to[:4]) <= lag_years else "not valid"
    return "valid"

class WikidataTier1:  # discovery through the Action API, then one SPARQL enrichment by QID
    api, sparql = "https://www.wikidata.org/w/api.php", "https://query.wikidata.org/sparql"

    async def run(self, state: "State", gate: HttpGate) -> SourceResult:
        search = {"action": "wbsearchentities", "search": state.name, "language": "en", "type": "item",
                  "limit": 7, "format": "json"}  # S4: CirrusSearch "name~1" when this finds nothing
        call, body, wait = await gate.get("wikidata", "CC0-1.0", self.api, search)
        calls, ok = [call], call.outcome == LookupStatus.SUCCESS
        ids = [hit["id"] for hit in json.loads(body).get("search", [])] if ok else []
        if ids:
            query = {"query": ENRICH % " ".join(f"wd:{i}" for i in ids), "format": "json"}
            call, body, wait = await gate.get("wikidata", "CC0-1.0", self.sparql, query)
            calls.append(call)
        if call.outcome != LookupStatus.SUCCESS:
            return SourceResult(status=call.outcome, calls=calls, retry_after_seconds=wait)
        candidates = []
        for row in json.loads(body).get("results", {}).get("bindings", []) if ids else []:
            value = {key: cell["value"] for key, cell in row.items()}
            if state.iso not in value.get("countries", "").split() or not state.accepts(value.get("classes", "")):
                continue  # hard gates: Denali for "Mount McKinley"; a 1941 campaign for "Philippine Islands"
            lon, lat = map(float, value["point"][6:-1].split()) if "point" in value else (None, None)
            qid = value["item"].rsplit("/", 1)[1]
            candidates.append(Candidate(
                source_id=f"wikidata:{qid}", feature_id=qid, role="historical", storable=True,
                point=None if lat is None else (lat, lon),
                validity=valid_on(value.get("validFrom"), value.get("validTo"), state.day, state.lag_years)))
        status = LookupStatus.SUCCESS if candidates else LookupStatus.NO_MATCH
        return SourceResult(status=status, candidates=candidates, calls=calls)

def sector_circle(radial_m: float, half_width_deg: float = 45.0) -> tuple[float, float]:
    """Center offset along the heading and radius of the smallest circle around the part of a
    feature within +/- half_width of a heading ("E. slope of X"; a cardinal heading is +/-45
    degrees, BP Table 4). S8's derivation from QRG 2.2.2; check it against the Calculator."""
    half = math.radians(half_width_deg)
    if half_width_deg >= 45:  # the chord between the arc ends is a diameter
        return radial_m * math.cos(half), radial_m * math.sin(half)  # 45 degrees: 0.707 R, 0.707 R
    return radial_m / (2 * math.cos(half)), radial_m / (2 * math.cos(half))  # apex on the circle

def decide(field_key: str, results: list[SourceResult], radius_m: float | None, policy) -> FieldOutcome:
    """One outcome per field key: operational first, then hard gates, then the score."""
    if blocked := [r for r in results if r.status in OPERATIONAL]:  # QUE-005: never Deferred
        return FieldOutcome(field_key=field_key, status=blocked[0].status, reasons=["operational"],
                            retry_after_seconds=blocked[0].retry_after_seconds)
    shown = [c for r in results for c in r.candidates]
    pool = [c for c in shown if not c.museum_published and c.validity != "not valid"
            and c.signals.get("hierarchy") != "conflicts"]
    if not pool:  # no data found: needs human review under the existing policy (G6, QUE-003)
        empty = bool(results) and all(r.status == LookupStatus.EMPTY for r in results)
        return FieldOutcome(field_key=field_key, candidates=shown,
                            status=LookupStatus.EMPTY if empty else LookupStatus.NO_MATCH)
    sources = {f: len({c.source_id.split(":")[0] for c in pool if c.feature_id == f and c.storable})
               for f in {c.feature_id for c in pool}}  # copies of one source count once
    score = lambda c: policy.review_priority(c, sources[c.feature_id], radius_m)  # section 3.4, uncalibrated
    ranked = sorted(pool, key=score, reverse=True)
    point, top = field_key == "georeference", ranked[0]
    reasons = [name for name, failed in (
        ("several_features", len(sources) > 1),  # QRG 2.4.3.2: do not georeference
        ("unconfirmed_hypothesis", any(c.hypothesis for c in pool)),
        ("signal_conflicts", any("conflicts" in c.signals.values() for c in pool)),
        ("coordinate_not_storable", point and not top.storable),
        ("radius_missing_or_too_large", point and (radius_m is None or radius_m > policy.max_radius_m)),
        ("below_cutoff", score(top) < policy.cutoff),  # the score can demote, never promote
    ) if failed]
    return FieldOutcome(field_key=field_key, candidates=ranked + [c for c in shown if c not in pool],
                        status=LookupStatus.AMBIGUOUS if reasons else LookupStatus.SUCCESS, reasons=reasons)

class GeoreferenceTool:  # S4's geography_lookup (T3a draft): GeographyQuery -> ToolResult
    tool, version = "geography_lookup", "geo-tiered-0"
    def __init__(self, tiers: list[list[SourceAdapter]], gate: HttpGate, policy):
        self.tiers, self.gate, self.policy = tiers, gate, policy

    def lookup(self, query):  # sync wrapper; an async agent awaits outcomes() instead
        state = State.from_query(query)  # GeographyQuery: literals with provenance, dates, collectors
        return to_tool_result(query, asyncio.run(self.outcomes(state)))  # or to_authority_result today

    async def outcomes(self, state: "State") -> dict[str, FieldOutcome]:
        for tier in self.tiers:  # tier 0, tier 1, hierarchy, tier 2, uncertainty, validation
            results = await asyncio.gather(*(adapter.run(state, self.gate) for adapter in tier))
            state.add(results)  # sub-adapters of one tier run concurrently; hosts stay paced
            if any(r.status in OPERATIONAL for r in results):
                break  # the gate has already spent the bounded retries
        return {key: decide(key, state.results_for(key), state.radius_for(key), self.policy)
                for key in ("country", "province_state", "county", "city", "georeference")}
```

Replayed against the probe's recorded responses, the code returns `no_match` for "Mount McKinley" in the Philippines, Q15095071 `valid` for "Davao Province" in 1946, Q1504280 `not valid`, and Q928 as the only "Philippine Islands" candidate after the class gate; it hands a 120 s `Retry-After` back to the workflow instead of sleeping, and an open circuit becomes `provider_error`.

## 6. Next steps for Phase 1 prototyping

| # | Step | Owner | Exit criterion |
|---|---|---|---|
| 1 | Decide D1 to D13 | owner | decisions recorded here |
| 2 | Confirm or reject the McKinley crosswalk entry and the 1946-47 expedition itinerary | Insects collection manager or curator (D3) | signed entries with sources |
| 3 | Merge T3a with S8's accepted additions; map the pilot's geography fields to `geography_lookup` | S4, S3 | contract tests pass |
| 4 | Build tier 0 and tier 1 adapters (crosswalk, itinerary, Wikidata, GeoNames dumps, GNS) with fakes and the probe's recorded responses as fixtures (HAR-018) | S4 | the fixtures reproduce the probe's results for the four localities |
| 5 | Build the point-radius module (corrected center, radial, sector, the Calculator's combination), then tiers 2 and 3 (containment, DEM check, `storable`, `decide`) | S4 (D13) | matches the Calculator's worked examples; a typed outcome for every row of 3.5 |
| 6 | Evaluate on the four pilot localities and a calibration set of FMNH records with curator-verified georeferences | S8 with a curator | precision and coverage per outcome; proposed thresholds for D5 |
| 7 | Run behind the G10 Google tool until the owner accepts | S4, owner | acceptance recorded (G12) |

Cost: the open sources cost USD 0, inside G9's USD 25. Google Geocoding is free for the first 10,000 Essentials calls a month and USD 5.00 per 1,000 after that [S11], and is used only if D1 keeps it.

Risks: Wikidata throttling (HTTP 429 with `Retry-After` after S8's second request from a shared address [S16]) is met by discovery through the Action API, a local cache and retries through the workflow; Getty's move to token-gated endpoints [S5] by deferral (D12); license obligations for GeoNames, NGA, Getty and the DEMs by attribution in `georeferenceSources` and dataset metadata (D2); sparse historical names by a tier-0 crosswalk curated by people; and the museum's repetition of one retrospective point across hundreds of records by treating those points as candidates only (D4).

Other workstreams: S4 merges T3a with the additions in section 5, registers the sources, adds a paid-call path only if D1 keeps Google, and builds the tool. S5 stores one ToolCall row per sub-call (G23) and, after D9, optional georeference fields. S3 maps the geography fields to `geography_lookup` in `field_tools`, selects checks per collection and implements profile inheritance (`COLLECTION_HIERARCHY.md` 73-76).

## Owner decisions

D1 to D13 are proposed, not accepted by the owner (G12); the owner rules on them in this document's pull request. D14 was decided by the owner on 2026-09-23 (G27), ahead of the rest, because S4 is building G20 now.

| # | Decision | Options | S8 recommendation | What it blocks |
|---|---|---|---|---|
| D1 | Google's role, given its terms and G26 (G10) | a) an existence check that keeps only place ID, outcome and fingerprint (G26), with open sources supplying names, units and coordinates; b) drop Google from the retrospective tool; c) negotiate enterprise terms; and whether a Google-only `success` may clear a field (PRD 12.4, open) | a, and a Google-only `success` does not by itself clear a field whose label predates a jurisdiction change | tier 2; use of the Maps key; the PRD 12.4 source table |
| D2 | Coordinate of record and attribution | open sources (Wikidata, GeoNames, NGA GNS) with attribution text in `georeferenceSources` and dataset metadata; or curator-entered coordinates only | open sources, with the GeoNames and NGA attribution texts | storing any coordinate; any export |
| D3 | Tier-0 curation | who owns the crosswalk and itineraries; McKinley as Mount Talomo, a neighboring peak, or unresolved; whether a confirmed itinerary match on collector, place and date counts as evidence | the Insects collection manager owns both; S8 drafts entries with sources; nothing unconfirmed resolves; confirmed matches count | the six McKinley slides and the Apo slide |
| D4 | The museum's published georeferences | a) support; b) candidates shown to reviewers, with disagreement reported as a warning; c) ignored | b: one retrospective point repeated on hundreds of records is circular | scoring and checks |
| D5 | Thresholds | maximum radius per profile; elevation tolerance; corroboration distance; label-lag tolerance; score cut-off | provisional: elevation 150 m (above the 60 m spread of four Yepocapa elevation figures); corroboration within the candidate's own radius; label lag 10 years; maximum radius and cut-off after step 6 | `decide` |
| D6 | Precision: clear at the precision written (the G24 and G25 principle applied to places) | a) a georeference clears at the precision the label states, and a fallback to an enclosing unit because a named place was not found ("Jones Farm") is a reviewer candidate only; b) coarse fallbacks may clear too | a | `decide` |
| D7 | Units derived from coordinates | derive county or city only when the whole uncertainty circle lies in one unit, or never; and whether a derived value satisfies a mandatory field (G8) | derive with containment evidence as a `lookup`; mandatory status is the owner's G8 call | county and city on the seven McKinley and Apo slides |
| D8 | Darwin Core conventions | historical path, modern units and successor chain as in 4.2; independent cities; municipio as `county`; `georeferencedBy` wording; "P.I." as country Philippines; "requires verification" by default | as proposed in 4.2 and 4.3 | any export |
| D9 | Optional georeference fields in the Insects profile (G8) | the tool result only; optional record fields for coordinates, datum, uncertainty, protocol, sources and status | the tool result in Phase 1, optional fields after it | S5 schema; S3 profile |
| D10 | Sensitivity and domain sources | generalization policy for Anthropology and sensitive Geology; holders of the Local Contexts and Mindat keys; the PBDB license; GEOLocate's terms from its maintainer | no Anthropology georeferencing before a policy exists; Mindat after license review; GEOLocate unused outside the USA | Anthropology and Geology profiles |
| D11 | Production elevation backend | Copernicus GLO-30 tiles read directly; Cloud SQL PostGIS raster [S31]; OpenTopoData (1,000 requests a day [S21]) | Copernicus tiles; OpenTopoData for research only | the elevation check at volume |
| D12 | Token-gated and account sources | Getty's new gateway; a WHG token; a GeoNames username (not needed with dumps) | defer all three | nothing in Phase 1 |
| D13 | Uncertainty engine | in-house point-radius per the Best Practices, porting the Calculator's combination code; GEOLocate | in-house | tier 3 |
| D14 | What a geography lookup confirms under G20 when readers disagree on a toponym's spelling | **Decided by the owner (G27):** "raw transcript anyway will have exactly as written, for verbatim field it will be as written but final location will be exact actual as settled by harness. we are always capturing both so there isn't an issue if people want to change later" | S8 had proposed the place only, with the spelling left to the first pass; under G27 the verbatim keeps the label's spelling and the field clears on the settled place, both stored (3.3) | nothing now |

## Sources

All sources were checked on 2026-09-23 unless marked.

- [S1] Hoogstraal, H. (1951). Philippine Zoological Expedition 1946-1947: Narrative and Itinerary. Fieldiana: Zoology 33(1): 1-86. https://www.biodiversitylibrary.org/part/12278 (BHL answered HTTP 403; read from https://archive.org/details/biostor-65904)
- [S2] Wikidata properties P1365, P1366, P571, P576, P580, P582, P625, P131 (https://www.wikidata.org/wiki/Property:P1366 and siblings) and items Q15095071, Q13792, Q13794, Q13806, Q146328, Q928, Q31472786, Q455963, Q1504280, Q1523937, Q25173824, Q696462, Q2389438, Q130018 (https://www.wikidata.org/wiki/Q15095071 and siblings), read through the Action API and WDQS
- [S3] GeoNames: web services and search, https://www.geonames.org/export/ws-overview.html and https://www.geonames.org/export/geonames-search.html; license, https://www.geonames.org/export/; dumps and readme, https://download.geonames.org/export/dump/; feature codes, https://www.geonames.org/export/codes.html; exceptions, https://www.geonames.org/export/webservice-exception.html
- [S4] NGA GEOnet Names Server: reference and citation terms, https://geonames.nga.mil/geonames/GNSHome/reference.html; ArcGIS REST layer, https://geonames.nga.mil/geon-ags/rest/services/RESEARCH/GIS_OUTPUT/MapServer
- [S5] Getty Vocabularies: SPARQL, http://vocab.getty.edu/sparql; reconciliation, https://services.getty.edu/vocab/reconcile/; token-gated gateway, https://data.getty.edu/vocab/sparql; data services and license, https://www.getty.edu/research-conservation/tools-databases/vocabularies/data-services/. World Historical Gazetteer API, https://docs.whgazetteer.org/content/technical/apis.html
- [S6] GEOLocate web services: JSON wrapper and SOAP v2 documentation, http://geo-locate.org/webservices/geolocatesvcv2/glcwrap.aspx; project site, http://www.geo-locate.org/
- [S7] OpenStreetMap: Nominatim usage policy, https://operations.osmfoundation.org/policies/nominatim/; ODbL Produced Work guideline, https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline; Overpass API, https://wiki.openstreetmap.org/wiki/Overpass_API. Mapcarta, About, https://mapcarta.com/About_Mapcarta
- [S8] Philippine statutes on Davao: Commonwealth Act No. 51 (1936); Republic Act No. 4867 (1967), https://lawphil.net/statutes/repacts/ra1967/ra_4867_1967.html; RA 8470 (1998); RA 10360 (2013), https://www.officialgazette.gov.ph/2013/01/14/republic-act-no-10360/; RA 11297 (2019), https://lawphil.net/statutes/repacts/ra2019/ra_11297_2019.html
- [S9] FMNH occurrence records on GBIF, queried by the probe (institutionCode=FMNH; Philippines 1945-1947, Guatemala 1947-1949), for example https://api.gbif.org/v1/occurrence/search?institutionCode=FMNH&country=PH&year=1945,1947&facet=locality; licenses per dataset
- [S10] Google Maps Platform Service Specific Terms (last modified 2026-06-10), sections 6.3.1, 6.3.2 and A.3, https://cloud.google.com/maps-platform/terms/maps-service-terms; Terms of Service, section 3.2.3, https://cloud.google.com/maps-platform/terms
- [S11] Google Geocoding API requests and responses (component filtering, statuses, partial_match, location_type), https://developers.google.com/maps/documentation/geocoding/requests-geocoding; pricing, https://developers.google.com/maps/billing-and-pricing/pricing
- [S12] Chapman, A.D. & Wieczorek, J.R. (2020). Georeferencing Best Practices, v1.2.1 (10 July 2025). GBIF Secretariat. https://doi.org/10.15468/doc-gg7h-s853
- [S13] Zermoglio, P.F., Chapman, A.D., Wieczorek, J.R., Luna, M.C. & Bloom, D.A. (2020). Georeferencing Quick Reference Guide. GBIF Secretariat. https://doi.org/10.35035/e09p-h128
- [S14] GBIF API reference: occurrence search and reverse geocoding. https://techdocs.gbif.org/en/openapi/
- [S15] Wikidata: Data access (Action API; CC0), https://www.wikidata.org/wiki/Wikidata:Data_access; WikibaseCirrusSearch help, https://www.mediawiki.org/wiki/Help:Extension:WikibaseCirrusSearch; Wikimedia Foundation User-Agent Policy, https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
- [S16] Wikidata Query Service User Manual (deadline, limits, HTTP 429 and Retry-After). https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual
- [S17] Philippine Statistics Authority, Philippine Standard Geographic Code, https://psa.gov.ph/classification/psgc (refuses scripted access); community mirror, https://psgc.gitlab.io/api/
- [S18] GADM license, https://gadm.org/license.html; geoBoundaries, https://github.com/wmgeolab/geoBoundaries
- [S19] Mapbox Product Terms (2026-07-21), section 2.7, https://www.mapbox.com/legal/product-terms; Geocoding v6, https://docs.mapbox.com/api/search/geocoding/
- [S20] Wieczorek, C. & Wieczorek, J. Georeferencing Calculator, http://georeferencing.org/georefcalculator/gc.html; Calculator Manual, https://doi.org/10.35035/gdwq-3v93
- [S21] Copernicus DEM on the Registry of Open Data on AWS and its product handbook, https://registry.opendata.aws/copernicus-dem/; OpenTopoData API, https://www.opentopodata.org/api/; review of global DEM accuracy, https://www.tandfonline.com/doi/full/10.1080/19475705.2021.1910575
- [S22] iDigBio search API, https://search.idigbio.org/v2/search/records; Bionomia API, https://api.bionomia.net
- [S23] Macrostrat API (license CC BY 4.0 stated in responses), https://macrostrat.org/api; Paleobiology Database data service, https://paleobiodb.org/data1.2/ (license unverified: sources conflict)
- [S24] Mindat licenses and API, https://www.mindat.org/licences.php (read from a cached copy; the page refused scripts)
- [S25] Pleiades, https://pleiades.stoa.org/downloads; PeriodO, https://perio.do/guide/; Local Contexts Hub API v2, https://localcontexts.org/support/api-guide/v2/; CARE Principles, https://gida-global.org/careprinciples
- [S26] ABCD standard (2.06 ratified 2005-09-16), https://www.tdwg.org/standards/abcd/; schema, http://rs.tdwg.org/abcd/2.06/ABCD_2.06.xsd; ABCD 3.0, https://abcd.tdwg.org/3.0/; Extension for Geosciences (EFG), https://github.com/tdwg/efg and https://www.tdwg.org/community/esp/efg/; BGBM wiki, ABCD 2 concepts, https://wiki.bgbm.org/bps/index.php/CommonABCD2Concepts
- [S27] Fichtmueller, D., Petersen, M., Glöckler, F. & Güntsch, A. (2022). State of the (Re-)Ratification of ABCD 2.06 and ABCD EFG under the SDS Guidelines. Biodiversity Information Science and Standards. https://biss.pensoft.net/article/93811/ (landing page only)
- [S28] Archaeological Resources Protection Act, 16 U.S.C. 470hh, https://www.law.cornell.edu/uscode/text/16/470hh; NHPA section 304 (54 U.S.C. 307103), ACHP guidance on sensitive information, https://www.achp.gov; NAGPRA regulations, 43 CFR 10.9 (effective 2024-01-12), https://www.ecfr.gov
- [S29] Darwin Core: list of terms (version 2026-05-26), https://dwc.tdwg.org/list/; quick reference, https://dwc.tdwg.org/terms/; changes, https://dwc.tdwg.org/list/changes.html
- [S30] Chapman, A.D. (2020). Current Best Practices for Generalizing Sensitive Species Occurrence Data, v1.0. GBIF Secretariat. https://doi.org/10.15468/doc-5jp4-5g10
- [S31] Cloud SQL for PostgreSQL extensions (postgis_raster). https://docs.cloud.google.com/sql/docs/postgres/extensions
