# G38 review derivation API

This source contract queues proposal work and reads its retained output. It does
not perform a geocoder/model call or publish a derived value automatically.
The integrator must install the native worker, source broker, current binding
provisioning and operational scheduling callbacks before enabling the capability.

All routes share the existing authenticated prefix:
`/v1/organizations/{organization_id}/collections/{collection_id}/specimens/{specimen_id}/research/derivations`.

- `GET /capability` returns `research-derivation-capability/v1`: `available`,
  `blocked_reason`, `canonical_revision`, and `eligible_fields`. This read never
  writes a provenance artifact or schedules work.
- `POST` accepts `Idempotency-Key` and only `expected_record_revision`,
  `base_record_version_id` (the existing `run-id:revision` host ID), `reason`,
  and distinct `requested_fields`. No input values, source outcomes, coordinates,
  uncertainty, model settings or budget are accepted from the client.
- `GET /{request_id}` returns `research-derivation-result/v1`, with native
  `queued`, `running`, `completed` or `blocked` progress and retained proposals.
  A later canonical revision returns `stale: true` with no selectable proposals.

The POST requires current review rights, a non-sensitive record, proved current
human inputs, eligible unprotected targets and installed worker readiness plus
scheduling. `collect_settled_inputs` proves original human saves and copies their
bounded provenance into immutable application blobs. Ordinary manual place
edits use the genuine review decision as human authority; they do not assert a
provider validation. Retained ambiguous GEOLocate outcomes remain ambiguous.
The worker must obtain a genuine unique successful validation before computing
from it; it must never rewrite the original outcome.

One ordinary canonical save retains `run.dependencies.research_derivation_request`
as `DerivationCommand` and a `review_derive_rest` audit. Its immutable source
revision R and source snapshot digest are distinct from its queued revision
Q = R + 1. Original scientific stage, disposition, approval, values, verbatim,
readers and evidence remain unchanged. The command carries original review
identities, immutable provenance references, exact field digests, input revision
R, protected field keys and requested targets. The source snapshot and inputs
are revalidated by the worker at current Q.

`create_app` accepts trusted `research_derivation_ready(principal, specimen)`
and `schedule_derivation(principal, saved_specimen, command)` callbacks. Both
are required for availability. The optional `research_capture_blobs` reader is
required to expose or accept a computed spatial proposal. It reads exact
generation-pinned immutable computation captures only after current scope and
binding checks; missing capture access fails closed for derived choices. Readiness is the integrator's verified deployed
composition/configuration check. Scheduling must execute and read back the
native operational queue transaction bound to Q, run and scope; its return is
`DerivationScheduleReceipt` (`research-derivation-schedule/v1`, request ID,
queued revision, canonical run ID and `status: scheduled`). The API validates
that receipt before returning 202. A replay re-enters the ordinary save receipt
and scheduling callback to repair partial enqueue without another canonical
revision. A stale historical request must never be rescheduled against a newer
canonical revision. The optional dispatcher only wakes the already durable queue.

The worker intercepts this side work before ordinary paid processing or the
finalized guard. It provisions a fresh binding for Q, imports genuine human
locks and verifies `verify_settled_inputs(repository, current_specimen, blobs,
command.inputs)`. This helper permits unchanged inputs across a queue save;
the worker independently requires exact Q/run/source snapshot and command
identity. It must preserve current budget/effect admission controls.

Native job dependencies carry `derivation_request_id` and `derivation_result`:
`{request_id, status, checkpoint_ids, blocked_reason}`. Progress lives in the
journal, without a status-only canonical save. Every proposal checkpoint is
bound to the actual scope, current generation, field revision and completed
source effect. The computed source is `georeference_spatial`; its evidence
matches that coverage's source/version and retains the input revisions, dataset
IDs, rule, tool call and georeference trace. The tool call ID remains the
genuine GEOLocate validation receipt ID. Exact request ownership is independently
proved by the full typed command digest in the native computation capture and
its matching effect operation identity; matching input values alone is insufficient.
Both read and acceptance enforce the supported computation rule version.
Metadata-only or unresolved results
have no selectable value. A completed result may contain fewer proposals than
requested fields. The worker records honest operational/unresolved outcomes.

`ResearchDerivationService` reads only the command's requested current
checkpoints and validates each retained candidate through the existing source
resolver. No model-output proof is invented for a deterministic source effect.
Root's operational finish transaction removes due work only after the matching
native request has completed or blocked. It does not increment the scientific
canonical revision or make proposal checkpoints eligible for automatic native
publication.

Historical source rows marked `settlement_allowed: false` or
`validation_required: geolocate` remain visible research context without a
selection token; a manually supplied token cannot make them selectable. The
G38 `human_review_required: true` and `automatic_settlement_allowed: false`
markers still allow the explicit human choice after immutable capture proof.

A reviewer accepts selected proposals through the existing `research_candidate`
decision/batch CAS using the returned `selection_id`. Input changes must be
saved separately and followed by fresh computation. Acceptance preserves
`layer: derived`, the exact `derived_from` fields and full source/derivation
audit metadata while retaining original verbatim. It does not create record
coordinate fields. A saved choice then makes the prior proposal binding
historical and read-only as in the ordinary candidate review flow.

Local tests use real SQLite canonical receipts, retained effects/checkpoints,
blob bytes and proof validation. Native binding, connector audit and scheduling
transports are explicitly synthetic fixtures. These tests are source evidence;
production SQL scheduling, worker execution and authenticated save/reopen are
separate integrated acceptance requirements.
