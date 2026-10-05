# Retrospective geography adapter, October 4, 2026

This adapter implements local historical candidates, conservative uncertainty,
administrative containment, and elevation derivation under G34–G39 and the
October 3 GEOLocate amendment. It does not write record coordinate fields,
approve proposals, or publish records. The source broker and worker are the
integration boundary.

`research_harness/georeferencing.py` exposes:

- `GeoreferencingAdapter(read_dataset)`. The callback accepts the canonical
  `georef_datasets.Dataset` and returns bytes from its `object_name` in the
  runtime's configured store. Every read checks the committed size and SHA-256.
  No implicit network download or alternate unpinned object is used.
- `history_query(request, query)` for source `georeference_history`. Its query
  JSON has `country` (`PH` or `GT`), `name`, and optionally `collected_on` (ISO
  year, month or day). Country dumps are searched locally. Results retain source
  IDs, dates when known, credit, and exact byte provenance. A GeoNames alias with
  no dates remains undated. Candidate success requires subsequent historian
  interpretation and GEOLocate validation before any field can settle.
- `derive_rest(country=..., validation=..., settled_inputs=...,
  requested_fields=..., verbatim_locality=..., label_has_elevation=...,
  tool_call_id=...)`. The worker supplies the trusted GEOLocate result and current
  persisted settled/reviewer values as `SettledLocationInput` records. Each input
  requires evidence, authority, and a revision. The adapter accepts no proposed
  model coordinate or uncertainty radius. It returns `DerivationResult`, whose
  proposals retain these input revisions, datasets, evidence, and tool call.
- `derivation_source_result(result, field_key)` represents a proposal in the
  existing source-result envelope. The caller still supplies its durable tool
  receipt. An unavailable DEM remains operational failure for that field.

The broker must register the local historical source and computed derivation
tool in the geography/measurement roles, enforce sensitive-data scope, and
retain their source results and receipts. The worker must read settled inputs
from the same specimen and generation, reject changed revisions, and pass only
a GEOLocate result trusted for that request. A model must never manufacture that
result or the settled inputs. The G38 API queues work under review rights; the
worker stores the returned proposal, and the existing reviewer decision route
edits and approves it. The adapter itself has no cloud or model client.

The current administrative field map uses Philippine provinces (ADM2) and
municipalities (ADM3), and Guatemalan departments (ADM1) and municipios (ADM2).
The Philippine ADM1 files are regions, not provinces. Neither dataset supplies
a separately reviewed county mapping, so an absent county remains explicit.
The map can be supplied by a reviewed collection profile; a municipality must
not be copied into county merely to fill both mandatory fields.

A qualified named administrative footprint determines a conservative enclosing
circle. Its simplification margin widens that circle. A second unit is proposed
only when its entire circle is uniquely contained, with that second file's own
margin to spare. A named point alone is insufficient to determine feature
extent. Historic Mt. McKinley in the Philippines remains unresolved until the
G36 entry is curator-confirmed, even beside a successful modern-name lookup.

DEM derivation runs only when the worker has established that the label states
no elevation (`label_has_elevation is False`). It includes every raster cell
touched by the uncertainty circle. Incomplete coverage or any no-data cell
refuses derivation. The four elevation fields retain the source minimum/maximum;
feet use the exact factor 0.3048. Label measurements and their verbatim are not
replaced. A circle larger than the bounded supported extent remains unresolved.

The canonical manifest recovers nine original September 24 dataset pins. On
October 4, the three original DEM tiles were fetched from their recorded public
URLs and matched those pins. The original six local gazetteer/boundary files
also matched their recorded sizes and digests. A tenth dataset, adjacent
Copernicus tile `N14_00_W092_00`, was fetched and pinned on October 4 because the
Yepocapa municipio's enclosing circle extends west of -91 degrees. This later
availability is recorded as such; it is not attributed to the earlier inventory.

Source objects must be provisioned through the normal runtime/data setup path.
Local files do not demonstrate object-store availability or worker access.
`scripts/research/georeferencing/verify_reference_data.py --dataset-root PATH`
is a reproducible offline check of actual file custody, all four boundary files,
gazetteer parsing, and a two-tile DEM circle. Its report explicitly does not claim
live specimen or publication acceptance.

The TGN, Wikidata, and NGA modules build and parse source requests without
sending them. Their fixture results prove offline parsing only. Source IDs for
follow-up queries must come from preceding source answers. Endpoint qualification,
the place-only disclosure filter, source pacing, and durable response capture
remain broker responsibilities; source operational failures are never absence.

The external historical orchestrator is
`historical_gazetteers.lookup(source_id, filtered_name, fetch)`. The caller's
qualified, durable fetch accepts an endpoint plus typed parameters and returns
HTTP status and bytes. At most three requests of at most 2 MB each run per
source. Follow-up IDs come only from the previous parsed source answer; missing
requested records remain ambiguous and unexpected IDs are refused. Ordered
`Exchange` entries retain query, status, body and digest. No partial or failed
source answer is silently treated as an exhausted gazetteer.

The validator result must confirm the most specific settled footprint anchor's
field and value. An ambiguous selection is not a successful validation: the
worker must obtain a genuine successful GEOLocate lookup. Upstream operational
failures retain their status. A valid DEM with no-data or incomplete geographic
coverage returns no-match; missing or corrupt pinned objects remain operational
failures. `DerivationResult.unresolved_statuses` preserves that distinction.
Even without a field proposal, the tool envelope retains a metadata-only
georeference candidate marked `settlement_allowed: false` with no field value.
