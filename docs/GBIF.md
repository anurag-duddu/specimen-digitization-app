# GBIF integration strategy

**Status:** Validated for the Insects pilot

**Last verified:** 2026-09-08 UTC

**Scope:** Read-only GBIF enrichment and validation for Specimen Digitization

## Decision

Use GBIF's direct APIs for the first implementation. GBIF should be the primary integration surface for taxonomic matching, optional occurrence corroboration, and selected institution, collection, dataset, vocabulary, and modern administrative-geography metadata.

Do not make the Google-hosted BigQuery table or Google Cloud Storage exports a P0 dependency. Reconsider them only for a measured batch workload that cannot be served efficiently by the GBIF occurrence Download API.

This is an **API-first, hybrid-ready** decision:

- P0 uses direct GBIF APIs with bounded retries, caching, typed outcomes, and captured provenance.
- P1 may use GBIF occurrence downloads for large or repeatable cohorts.
- BigQuery or dated GCS snapshots remain optional batch and replay sources.
- A cloud-dataset-only architecture is not acceptable because occurrence exports cannot replace taxonomic name matching, current record details, registry metadata, media metadata, or other GBIF services.

GBIF should be the primary source, not an unquestioned source of truth. The platform must preserve the original label text, expose conflicting evidence, and abstain when a match is insufficient.

## Repository fit

This decision supports the existing platform requirements to:

- keep literal, parsed, normalized, and externally resolved values separate;
- expose external providers through typed, allow-listed adapters;
- distinguish success, no match, ambiguity, throttling, timeout, authentication, provider, and schema failures;
- retain the exact query, provider, retrieval time, adapter version, identifiers, licensing metadata, and response digest;
- support checkpoints, replay, forced refresh, and human review; and
- prevent a lookup result from silently overwriting the specimen's source transcription.

See [PRD: structured extraction, enrichment, and reasoning harness](product-requirements/PRD.md#116-structured-extraction-enrichment-and-reasoning-harness) and [Harness options: Insects pilot spike](product-requirements/HARNESS_OPTIONS.md#insects-pilot-spike).

## Official documentation

- [GBIF API reference](https://techdocs.gbif.org/en/openapi/)
- [Species API](https://techdocs.gbif.org/en/openapi/v1/species)
- [Occurrence API](https://techdocs.gbif.org/en/openapi/v1/occurrence)
- [Registry API](https://techdocs.gbif.org/en/openapi/v1/registry-principal-methods)
- [Vocabulary API](https://techdocs.gbif.org/en/openapi/v1/vocabulary)
- [Occurrence image API](https://techdocs.gbif.org/en/openapi/images)
- [Taxonomy interpretation](https://techdocs.gbif.org/en/data-processing/taxonomy-interpretation)
- [Migration from the legacy GBIF Backbone to COL XR](https://data-blog.gbif.org/post/catalogue-of-life-taxonomic-backbone/)
- [GBIF citation guidelines](https://www.gbif.org/citation-guidelines)
- [GBIF terms](https://www.gbif.org/terms)

Only documented, non-experimental endpoints may contribute to a clearance decision. The application must not scrape `www.gbif.org` pages.

## API capability map

| API family | Platform use | Priority | Decision |
|---|---|---:|---|
| Species Match v2 | Resolve scientific names, accepted usage, synonymy, authorship, rank, classification, identifiers, and match diagnostics | P0 | Implement first |
| Species Match metadata | Pin the taxonomy index and software metadata used by a run | P0 | Capture with run provenance |
| Occurrence lookup/search | Corroborate a specimen that may already be published to GBIF | P0 or P1 | Add only if it improves reviewer decisions |
| Registry and GRSciColl | Resolve institutions, collections, publishing datasets, and organizations | P0 configuration | Bootstrap and human-confirm; do not call for every specimen |
| Occurrence Download | Produce large, asynchronous, citable occurrence extracts | P1 | Prefer before BigQuery for narrow cohorts |
| GADM geography | Validate modern country and first-level administrative geography | P1 | Use as supporting evidence only |
| Vocabularies and enumerations | Validate supported controlled values | P1 | Add only for fields required by the target schema |
| Maps | Display aggregate occurrence context | Later | Visualization only, not identification evidence |
| Occurrence images | Display cached low- or medium-resolution occurrence media | Later | Rights-sensitive; not source-image storage |
| Validator | Validate a dataset before publication to GBIF | Conditional | Use only if GBIF publication enters scope |
| Literature | Find works that cite GBIF datasets and downloads | Out of current scope | Not an identification-literature service |
| Registry mutation and crawl operations | Administer publishing infrastructure | Out of scope | Never expose to the pilot harness |

## P0: taxonomic name matching

### Required endpoints

```http
GET  https://api.gbif.org/v2/species/match
GET  https://api.gbif.org/v2/species/match/metadata
```

The GET operation matches one scientific name. The metadata operation reports the matching index, source dataset, build, and creation information.

GBIF's OpenAPI description also advertises a batch `POST /v2/species/match` operation. Live validation on 2026-09-08 returned HTTP `405 Method Not Allowed` with only `OPTIONS`, `HEAD`, and `GET` permitted. Do not make batch POST a production dependency until GBIF confirms deployment and a live capability probe succeeds. Implement bounded-concurrency GET requests for multi-name work in the meantime.

### Required taxonomy selection

Always send the Catalogue of Life Extended Release checklist key:

```text
7ddf754f-d193-4cc9-b351-99906754a03b
```

Example:

```http
GET /v2/species/match
    ?scientificName=Ctenocephalides%20felis
    &kingdom=Animalia
    &class=Insecta
    &checklistKey={COL_XR_CHECKLIST_KEY}
    &verbose=true
```

The legacy GBIF Backbone was last updated in 2023 and is retained for backward compatibility. GBIF's v1 name lookup, search, suggest, and usage operations do not provide the current COL XR workflow. Do not mix legacy integer taxon keys with current alphanumeric COL XR keys without an explicit, evidenced mapping.

As observed on 2026-09-07, the metadata endpoint identified the active index as `COL26.6 XR`, created on 2026-07-18. The alias is time-sensitive and must be read and recorded rather than hard-coded. The checklist key is the durable configuration value.

### Match inputs

Send all reliable context extracted from the label or collection profile:

- `scientificName`, including authorship when it is genuinely present;
- `taxonRank` when known;
- `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, and lower-rank parts when supported;
- `taxonID`, `scientificNameID`, or `taxonConceptID` when an external identifier is present;
- `verbose=true` when alternatives are needed for review; and
- the required `checklistKey`.

Do not invent higher classification merely to improve a match. Every contextual field must retain its own provenance.

### Match decision policy

GBIF confidence is evidence, not a clearance rule. The adapter must map provider responses into platform-level outcomes.

Live validation found `confidence=100` on both `NONE` and `HIGHERRANK` results. Confidence must never be evaluated without the match type, returned rank, and presence of a usage key.

| GBIF result | Platform treatment |
|---|---|
| Exact accepted match, non-empty usage key, expected rank, compatible classification, no material diagnostic conflict | Supported candidate; eligible for automatic selection only under an approved profile rule |
| Exact synonym | Preserve label name and synonym status; propose the accepted usage as a separate candidate |
| Fuzzy match | Candidate requiring review unless a separately validated typo policy applies |
| Multiple plausible alternatives or homonym conflict | `ambiguous`; retain ranked alternatives and require review |
| Higher-rank-only match, regardless of confidence | Partial support, never a species-level resolution |
| No match, regardless of confidence | `no_match`; preserve the attempted query and abstain |
| Provider or schema failure | Operational failure, not a biological no-match |

The platform must never replace the verbatim label taxon with the normalized result. It stores a linked candidate with evidence.

### Taxonomy evidence contract

At minimum, retain:

```yaml
provider: gbif
operation: species_match_v2
endpoint: /v2/species/match
verbatim_name: <label text>
query: <complete normalized request>
requested_rank: <requested or inferred target rank>
checklist_key: <COL_XR checklist key configured above>
taxonomy_alias: <value returned by metadata endpoint>
taxonomy_index_created: <value returned by metadata endpoint>
provider_build_sha: <value returned by metadata endpoint>
usage: <matched usage>
accepted_usage: <accepted usage when supplied>
classification: <ordered classification>
returned_rank: <rank of matched usage>
match_type: <provider diagnostic>
confidence: <provider diagnostic>
issues: <provider diagnostics>
alternatives: <provider alternatives when requested>
retrieved_at: <UTC timestamp>
adapter_version: <application adapter version>
raw_response_digest: <content digest>
raw_response_pointer: <immutable object-storage pointer>
```

The complete provider response belongs in immutable object storage when it is too large for the corresponding `lookupExecutions` record.

## Occurrence corroboration

### Useful endpoints

```http
GET https://api.gbif.org/v1/occurrence/{gbifId}
GET https://api.gbif.org/v1/occurrence/{datasetKey}/{occurrenceId}
GET https://api.gbif.org/v1/occurrence/search
GET https://api.gbif.org/v1/occurrence/{gbifId}/verbatim
```

Use occurrence data to answer narrowly framed questions:

- Has this specimen already been published to GBIF?
- Which GBIF record corresponds to this publisher identifier?
- Does the published record corroborate or disagree with the new transcription?
- What interpretation issues did GBIF attach to the published occurrence?

Prefer exact lookup by `gbifId`. Otherwise use the narrowest confirmed combination of:

- `institutionKey`;
- `collectionKey`;
- `datasetKey`;
- `catalogNumber` or `occurrenceId`; and
- `checklistKey` whenever taxonomic filters are present.

Do not use `institutionCode=FMNH` alone for record resolution. Institution and collection codes are not guaranteed to be globally unique, and a broad result set is not evidence of specimen identity.

Occurrence data is corroborating evidence, not the Field Museum master record. A difference between the label and GBIF may mean the new transcription is wrong, the GBIF interpretation is stale, or the publisher record needs correction. The adapter must report the disagreement without silently choosing a winner.

### Search limits and batch boundary

Occurrence search is paged, with a maximum page size of 300 and a deep-pagination boundary around the first 100,000 results. GBIF does not guarantee a fixed request rate. Rapid or numerous searches may receive HTTP `429` according to current server load.

If an occurrence-search job would run for more than approximately 15 minutes, GBIF recommends using the asynchronous Download API. Downloads are authenticated, citable, and better suited to thousands of taxa, datasets, locations, or other repeated filters.

```http
POST https://api.gbif.org/v1/occurrence/download/request
GET  https://api.gbif.org/v1/occurrence/download/{key}
GET  https://api.gbif.org/v1/occurrence/download/{key}/citation
```

The download request and its predicates must also specify the COL XR checklist when taxonomic filtering is used.

### Authenticated download validation — completed 2026-09-08

An authenticated, no-notification `SIMPLE_CSV` request selected the five validation specimens using one `GBIF_ID` `in` predicate and the explicit COL XR checklist key. GBIF accepted the request, reported five records while processing, and completed it in approximately 99 seconds.

- Download key: [`0006448-260903145123482`](https://api.gbif.org/v1/occurrence/download/0006448-260903145123482)
- DOI: [`10.15468/dl.887f5b`](https://doi.org/10.15468/dl.887f5b)
- Status: `SUCCEEDED`
- Records: 5
- Format: `SIMPLE_CSV`
- Checklist: explicit COL XR key configured above
- Archive: 1,496 bytes compressed; one 4,319-byte CSV with 50 columns
- Archive SHA-256 at validation time: `2101c56fee0d78b19c5f31b1cd8fecc5eff7cf9d0f6f8cdec5a3fd9a236d4803`
- Citation: `GBIF.org (8 September 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.887f5b`

The returned ID set exactly matched the requested five IDs. Every row matched its current individual Occurrence API response on GBIF ID, dataset key, catalog number, basis of record, institution and collection codes, COL XR taxon key, and `lastInterpreted` timestamp. The download's `CC0_1_0` values corresponded to the current API's CC0 legal-code URI. All provider interpretation issues remained present in the download and must be retained as evidence.

The metadata reports `eraseAfter=2027-03-08T03:00:25.504+00:00`. The DOI is the durable citation, but the hosted ZIP is not permanent binary storage. Any replay requirement must retain an approved immutable copy or, at minimum, the exact request, DOI, archive digest, extracted-row digest, and schema evidence.

## Registry and GRSciColl

### Useful read operations

```http
GET https://api.gbif.org/v1/grscicoll/institution/search
GET https://api.gbif.org/v1/grscicoll/institution/{key}
GET https://api.gbif.org/v1/grscicoll/collection/search
GET https://api.gbif.org/v1/grscicoll/collection/{key}
GET https://api.gbif.org/v1/dataset/search
GET https://api.gbif.org/v1/dataset/{key}
GET https://api.gbif.org/v1/organization/{key}
```

Use these operations during collection-profile setup to discover stable external UUIDs. A museum administrator or collection manager must confirm the mapping before it affects specimen resolution.

Observed on 2026-09-07:

- Field Museum of Natural History is active in GRSciColl with code `FMNH` and institution key `e71f36f1-e271-4720-a604-3c5a1418e7aa`.
- GRSciColl returned an active Insect, Arachnid and Myriapod Collection with code `ARTH`.

These are GBIF/GRSciColl identifiers. They do not confirm the collection code or target field Field Museum wants written to EMu. Store only human-confirmed identifiers in the active collection profile.

Registry calls should not run for every specimen. Resolve and approve the institution, collection, publishing organization, and relevant occurrence dataset keys during profile configuration, then cache the approved configuration with its verification date.

## Administrative geography

The Occurrence API includes GADM administrative-geography operations:

```http
GET https://api.gbif.org/v1/geocode/gadm/search
GET https://api.gbif.org/v1/geocode/gadm/{gid}
GET https://api.gbif.org/v1/geocode/gadm/{gid}/subdivisions
```

Use them as supporting evidence for modern country and province/state normalization and containment. For example, the current service resolves Illinois as `USA.14_1`, recognizes variants including `IL` and `Ill.`, and places it beneath the United States.

Do not use GADM to replace:

- verbatim locality text;
- historical place and jurisdiction interpretation;
- precise georeferencing;
- city or site resolution where the service has no suitable record; or
- human review of conflicting geographic evidence.

The platform must store verbatim locality, interpreted historical jurisdiction, modern administrative candidate, and any coordinates as separate linked values.

## Controlled vocabularies

The Vocabulary API currently exposes controlled concepts including:

- `BasisOfRecord`;
- `LifeStage`;
- `Sex`;
- `TypeStatus`;
- `OccurrenceStatus`;
- `PreservationType`;
- `EstablishmentMeans`;
- `Continent`; and
- `TaxonRank`.

Add a vocabulary mapping only when the target collection schema requires it. Do not coerce free-text `habitat` or `collection_method` into a GBIF term without an approved crosswalk. The label value remains verbatim even when a controlled candidate is added.

## Maps and occurrence images

The Maps API can support aggregate reviewer context, but a map tile is not evidence that a specimen identification or locality is correct. Maps are not required for P0.

The Occurrence Image API supplies cropped or resized occurrence images up to 1200 by 1200 pixels. GBIF asks scripted clients to use a single HTTP connection. Images may have more restrictive rights than occurrence data, may load slowly on first access, and may fail when the publisher source is unavailable. Use publisher-hosted originals for the highest resolution and preserve media-specific licensing.

Do not use GBIF occurrence images as a substitute for the platform's original specimen-label assets.

## Adapter boundaries

Implement separate typed clients rather than a general-purpose GBIF tool:

```text
GbifTaxonomyClient
  matchOne()
  matchManyWithBoundedGetConcurrency()
  getMatchMetadata()

GbifOccurrenceClient
  getByGbifId()
  getByPublisherId()
  searchCorroboratingRecords()
  requestDownload()

GbifRegistryClient
  resolveInstitution()
  resolveCollection()
  resolveDataset()
  getPublishingOrganization()

GbifGeographyClient
  searchAdministrativeRegion()
  getAdministrativeRegion()
```

Every client returns the platform's provider-neutral outcome model:

```text
success
no_match
ambiguous
empty_response
rate_limited
timeout
authentication_error
authorization_error
provider_error
malformed_response
policy_blocked
```

Provider-specific response fields remain available in evidence, but workflow logic must consume the provider-neutral contract.

## Authentication and configuration

Most GBIF read operations do not require authentication. Creating occurrence downloads and modifying resources require a GBIF account using HTTP Basic Authentication.

Production credentials belong in Secret Manager and must not be stored in the application database, source files, logs, or raw trace payloads.

The current `.env.example` uses one unversioned origin because the integration requires both v1 and v2 endpoints:

```text
GBIF_API_ORIGIN=https://api.gbif.org
GBIF_USERNAME=
GBIF_PASSWORD=
```

Each typed client owns its versioned path. `GBIF_USERNAME` and `GBIF_PASSWORD` remain blank unless asynchronous occurrence downloads are used. The local `.env` is gitignored; deployed credentials must come from Secret Manager.

The live download API accepted `sendNotification=false` with an empty `notificationAddresses` list. Production may still configure a monitored notification address, but it is not required for the polling-based adapter validated here.

Model-provider BYOK remains independent and provider-neutral. GBIF credentials configure a biodiversity-data provider, not a model provider. AWS is not in the current platform scope.

## Reliability, caching, and operational behavior

For all GBIF clients:

1. Send an identifying HTTP `User-Agent` containing an application URL or monitored contact email.
2. Set explicit connection and response timeouts.
3. Apply bounded exponential backoff with jitter to safe idempotent requests.
4. Honor provider retry instructions, including `Retry-After` when supplied.
5. Open a circuit after repeated systemic failures.
6. Checkpoint before and after external effects so replay does not duplicate them.
7. Cache by provider, operation, complete normalized request, checklist key, and relevant provider version.
8. Keep successful, empty, ambiguous, and failure cache entries distinguishable.
9. Use a profile-controlled retention policy and support forced refresh.
10. Treat an exhausted retry budget as an operational block, never a taxonomic no-match.

GBIF does not guarantee a particular request rate. Species matching, geocoding, and individual occurrence retrieval generally sustain rapid queries; search endpoints are more likely to be throttled. The platform must be correct under `429` rather than trying to discover or consume the maximum possible rate.

The 2026-09-08 validation sent serial Species Match requests with an 80 ms inter-request pause and an identifying User-Agent. All 144 requests succeeded, but that experiment validates only this modest traffic pattern; it does not establish a contractual or safe maximum rate.

## Validated cache boundary

Use Cloud SQL for PostgreSQL through Firebase SQL Connect as a curated application cache, not as a GBIF warehouse mirror. A local PostgreSQL 17 validation loaded 10,000 real GBIF rows in 3.09 seconds, occupied 4.68 MiB including indexes, returned warm indexed point lookups in approximately 0.01 to 0.04 ms, and replayed all 10,000 rows idempotently in 95.7 ms.

Those figures validate the schema and indexing approach only. They do not establish production SQL Connect or Cloud SQL network latency. Cache records must remain small and provenance-rich, keyed by provider, operation, complete normalized request, checklist key, and relevant provider release.

## Licensing, attribution, and provenance

GBIF occurrence records may be CC0, CC BY, or CC BY-NC. Preserve the license, dataset key, publishing organization, rights holder when present, retrieval date, and record identifier for each occurrence used. CC BY-NC data requires project-policy or legal review if commercial use is possible.

Media rights are separate from occurrence-record licensing. Store media identifiers and their stated rights independently.

For bulk occurrence use, prefer a GBIF Download DOI because it provides a citable, reproducible description of the retrieved cohort. For search-API use, capture the exact query and follow GBIF's search-result citation guidance. Never present uncited aggregated GBIF occurrence data as platform-owned data.

## Deferred Google Cloud datasets

The Google-hosted GBIF exports remain a possible later batch source:

- BigQuery exposes the mutable latest table at `bigquery-public-data.gbif.occurrences`.
- GCS exposes dated occurrence snapshots with Parquet shards and a `citation.txt` DOI.
- Both are expected to update monthly.

They should not serve interactive reviewer clicks. The current BigQuery table is unpartitioned and unclustered, so narrow filters can still scan hundreds of gigabytes. A 2026-09-07 read-only inspection also found the current table 214,437,350 rows, or 5.456 percent, smaller than the latest dated GCS snapshot. The source-snapshot relationship remains unexplained.

A capped validation query over preserved FMNH occurrences processed 321,201,227,881 bytes, billed 321,201,897,472 bytes (0.292131 TiB), and completed in 2.831 seconds. That is approximately USD 1.83 at on-demand list price after any free allowance is exhausted. The corresponding live Occurrence API cohort was 1,034 records, or 0.0513 percent, larger than BigQuery, confirming a small current-state lag even where cohort agreement is strong.

Authenticated GCS reads succeeded without Requester Pays, while anonymous object access returned `403`/`401` despite the published anonymous-access guidance. Bucket location and exact egress attribution remain unconfirmed. Do not depend on anonymous access, and validate location and billing before any full-snapshot transfer.

Do not use cloud-table `lastinterpreted` as a change-data-capture cursor. Validation observed a BigQuery value of `9999-12-31 23:59:59+00` where the current Occurrence API returned a normal 2026 interpretation timestamp. Use explicit snapshot date, DOI, retrieval time, and stable record identifiers instead.

Reconsider BigQuery or GCS only when all of these conditions hold:

- the measured job is genuinely batch-oriented;
- the GBIF Download API cannot meet the workflow efficiently;
- the BigQuery/GCS coverage discrepancy has been explained;
- source region, access method, billing, transfer, and retention behavior are confirmed;
- every query is dry-run first and guarded by `maximumBytesBilled`;
- the result is a small, versioned materialized subset rather than a full mirror; and
- snapshot date, DOI, query text or hash, schema, adapter version, license, and result digest are preserved.

No Google Marketplace subscription is required to query the public BigQuery table, but a caller-owned project is required. A billing-disabled BigQuery sandbox is the preferred environment for any no-cost investigation.

## Pilot implementation sequence

### Phase 1: Species Match validation — completed 2026-09-08

Use 25 to 50 adjudicated Insects fixtures covering:

- exact accepted names;
- exact synonyms;
- spelling errors;
- authorship variation;
- homonyms with and without higher classification;
- infraspecific names;
- higher-rank-only results;
- names absent from the active taxonomy; and
- identifier-based matching where an external identifier is available.

The validation exercised 36 cases against both the default backbone and explicit COL26.6 XR, with immediate repeats: 144 of 144 GET requests returned HTTP 200. It covered accepted names, exact synonyms, spelling variants, authorship variants, requested ranks, invalid names, uncontextualized homonyms, and higher-rank fallback. Thirteen CoL usages were independently consistent with their ChecklistBank records.

The live batch POST probe failed with HTTP 405 and is deferred. Implementation must capture match metadata, raw responses, typed outcomes, evidence, and replay artifacts for bounded-concurrency GET requests.

### Phase 2: expert acceptance policy

With collection experts, decide:

- which exact-result conditions may produce an automatically selected candidate;
- which synonym relationships are acceptable;
- how authorship conflicts affect clearance;
- whether fuzzy matches can ever clear automatically;
- which issues require review; and
- when an alternate source may be consulted.

Do not define thresholds solely from the provider confidence number.

### Phase 3: Field Museum registry bootstrap

Resolve candidate GRSciColl institution and collection UUIDs and relevant GBIF occurrence dataset keys. Have Field Museum confirm their meaning and mapping to the target EMu fields. Store the approved mapping in a versioned collection profile.

### Phase 4: occurrence corroboration and download validation

The five-record authenticated download and exact GBIF ID reconciliation are complete. A remaining product experiment should use known published and unpublished specimens to test confirmed composite identifiers and measure whether occurrence evidence changes reviewer decisions enough to justify P0 inclusion.

### Phase 5: GADM administrative validation

Test country and state/province normalization without replacing verbatim geography. Keep unresolved, historical, and precise locality work on its separately approved path.

### Phase 6: batch decision

If large cohort enrichment becomes necessary, test a filtered GBIF occurrence download first. Reopen BigQuery/GCS only if download performance, filtering, or analytical requirements are demonstrably insufficient.

## Spike success criteria

The GBIF spike succeeds when:

- every request uses the explicit COL XR checklist where relevant;
- the active taxonomy metadata is pinned in evidence;
- exact, synonym, fuzzy, ambiguous, higher-rank, and no-match fixtures remain distinguishable;
- no ambiguous or unsupported taxon is automatically cleared;
- verbatim label values are never overwritten;
- provider `429`, timeout, malformed response, and schema-change cases are reproduced in tests;
- retries are bounded, checkpointed, and idempotent;
- replay performs zero external calls and reproduces the same typed result and digest;
- GRSciColl and dataset identifiers used by the profile have human approval;
- occurrence disagreements are displayed as evidence rather than silently resolved;
- authenticated download requests preserve their predicate, checklist key, DOI, citation, archive digest, schema, and hosted-archive retention boundary;
- every external result is traceable to its query, provider version, retrieval time, identifiers, license, raw response, and adapter version; and
- direct API performance meets the agreed reviewer-workflow latency target under representative concurrency.

The completed read-only validation supports this design but does not by itself satisfy the implementation gates for forced provider failures, replay, production concurrency, or expert-approved automatic-selection policy.

## Open decisions

The following decisions require product or Field Museum input:

1. Whether GBIF occurrence corroboration is required for clearance, optional reviewer context, or outside the first release.
2. The approved Field Museum institution, collection, and occurrence dataset identifiers and their mapping to EMu.
3. The source-precedence rule when GBIF conflicts with another approved taxonomic authority or curator judgment.
4. The exact automatic-selection policy for exact, synonymous, fuzzy, higher-rank, and issue-bearing results.
5. Whether a direct ChecklistBank/Catalogue of Life adapter adds enough evidence beyond GBIF v2 Species Match to justify a second P0 taxonomy provider.
6. Whether Global Names Verifier materially improves name parsing or ambiguity detection on adjudicated Insects fixtures.
7. Which GBIF vocabularies correspond to approved target fields.
8. The caching and retention periods allowed for GBIF responses and occurrence media.
9. The project policy for CC BY-NC occurrence data and separately licensed media.

Until those decisions are made, the safe default is GBIF Species Match v2 against the explicitly pinned COL XR checklist, typed abstention, and human review for anything other than an approved exact-result pattern.
