# Browse a data source, select specimens, run them

Status: **design, not implemented.** Written 2026-09-14 after the first real
specimens were processed end to end. Nothing here has been built.

## What this is, and what it is not

The user's ask: the collection's images should be *visible* in the app, and a
reviewer should be able to select all of them, one of them, or any subset, and
run processing on that selection.

This is **not** an extension of the pilot manifest, and the two must never be
merged. `application/pilot_manifest.py` defines `PilotManifest` with
`specimens: tuple[PilotSpecimen, ...] = Field(min_length=10, max_length=10)` and
`ordinal` bounded `ge=1, le=10`. That is deliberate. It is the frozen,
immutable, exactly-ten cohort that the protected release admits against, with
each specimen bound to a bucket object *generation*. The release contract says
the scope is exactly ten and that specimens may not be dropped to make cost or
acceptance pass.

So there are two separate things:

| | Pilot manifest | Source browse and run |
|---|---|---|
| Purpose | the gated production release | ongoing operational intake |
| Size | exactly 10, frozen | any subset of a registered source |
| Binding | object generation, pinned in the packet | object generation, at import time |
| Budget | the approved release ledger | a separate per-run allowance |
| Changes with use | never | continuously |

**Ship the ten first, unchanged.** Build this afterwards. Conflating them breaks
the release evidence chain, because the packet digest would no longer describe a
fixed set.

## What exists today

Verified against the current source, not assumed.

- **Intake is upload-only.** The whole path is `POST /batches` →
  `POST /batches/{id}/items` (declaring filename, media type, size, width,
  height, sha256) → `PUT /uploads/{id}/content` in chunks → `POST
  /uploads/{id}/complete`. `complete` verifies the declared metadata against the
  actual bytes and returns 422 on a mismatch. Every byte travels through the
  client.
- **There is no data-source concept.** Nothing in the API enumerates storage.
  The 1,000 objects under `microscopic-slides/` in
  `gs://specimen-digitization.firebasestorage.app` are invisible to the
  application.
- **There is no bulk action.** `POST /specimens/{id}/decisions` takes one
  decision for one specimen. This is already recorded as partial criterion 7.3
  in `design/08-verification-report.md` ("no bulk action exists on the API").
- **There is no multi-select in the client.** The queue renders single-select
  rows; no checkbox or selection model exists in `lib/src/screens/queue/`.
- **Paging already works.** `GET /specimens` takes `cursor` and `limit` with
  `SearchFilters`. The same cursor pattern should carry the source listing.
- **Deduplication already works.** The repository exposes `find_checksum`, and
  the schema holds a unique index `specimen_scope_checksum`.
- **Per-stage cost is already modelled.** `CollectionProfile.cost_micros` is a
  `dict[str, int]` of per-step costs and a run carries `reserved_cost_micros`
  and `actual_cost_micros`. Estimating the cost of N specimens before dispatch
  is therefore arithmetic over existing data, not new modelling.

## The gap

Three things are missing, in dependency order.

1. The application cannot **see** objects it has not already ingested.
2. The application cannot **ingest** an object without the bytes passing through
   a client upload.
3. The application cannot **act on many specimens at once**, with a cost
   ceiling, from one reviewer gesture.

## Design

### A. Source registry and inventory

A *source* is a collection-scoped, administrator-registered pointer at a storage
prefix. It is configuration, not a user-creatable resource: the deployment
contract is explicit that no runtime API creates collections or grants scope, and
the same reasoning applies here. A reviewer chooses *within* a registered source;
they never name a bucket.

    source_id, collection_id, bucket, prefix, media_types, registered_by, registered_at

Inventory is a server-side listing that records, per object: `object_name`,
`generation`, `size_bytes`, `content_type`, and a content digest. `SourceObject`
in `pilot_manifest.py` is already exactly this shape and should be reused rather
than re-invented.

Inventory must be **snapshotted, not listed live**, for three reasons: a bucket
listing of 1,000+ objects is slow to page interactively; `generation` must be
captured at a known moment so an import binds to the bytes that were seen; and
the reviewer's selection has to remain stable while they are choosing.

Each inventory row resolves an `imported` state through `find_checksum`, so the
listing can show what is already in the queue instead of offering duplicates.

### B. Server-side import from a source

    POST /v1/organizations/{org}/batches/{batch_id}/items:from-source

Body: the source id and a list of `{object_name, generation}` pairs.

The server reads each object, verifies the generation still matches, computes the
digest, and creates the specimen. **The integrity guarantee must not weaken.**
Today `complete` proves declared-equals-actual because a client declared first.
Here the server is the only reader, so the equivalent proof is the generation
binding: the import fails if the object changed between inventory and import.

Existing checksum uniqueness makes re-importing the same object a no-op that
returns the existing specimen, which is the correct behaviour for "select all"
run twice.

### C. Bulk run with a cost ceiling

    POST /v1/organizations/{org}/collections/{id}/runs:bulk

Two phases, and the first is not optional:

1. **Estimate.** Sum `profile.cost_micros` across the steps each selected
   specimen will execute. Return the count, the estimate, the remaining
   allowance, and what would be refused.
2. **Reserve and dispatch.** Reserve the estimate against the allowance before
   any external call. Refuse the whole request if it does not fit; never
   part-run a selection silently.

This is the step that can spend real money. At two reader calls per specimen,
"select all" over 1,000 slides is three orders of magnitude more inference than
the pilot. The endpoint must be incapable of exceeding its allowance, and the
allowance for ongoing operation is a **separate decision** from the release
ledger — see open questions.

The same endpoint shape closes partial criterion 7.3 for decisions.

### D. Sources screen (client)

A browse-and-select surface over the inventory:

- paged list or grid, cursor-based, over 1,000+ rows
- a thumbnail per object. **Note:** an un-imported object has no asset, so
  `GET /assets/{id}/content` does not apply. Either add a source thumbnail
  endpoint or render a placeholder. Do not send raw originals to the browser to
  make a grid.
- per-row state: available, already in queue, unsupported media type
- selection: one, many, and select-all-matching-the-current-filter, with the
  selection count always visible
- a confirmation step before running that names the count, the estimated cost
  and the remaining allowance

The confirmation step is a hard requirement, not a courtesy. A select-all gesture
that silently starts a thousand paid runs is the single most expensive mistake
this UI could allow.

### E. Bulk actions in the queue (client)

Multi-select in the queue with a bulk decision bar. This closes partial criteria
7.2 and 7.3 together and shares the selection model with D.

### F. Contracts and docs

Every endpoint above needs its shape recorded in `docs/execution/CONTRACTS.md`
before implementation, and the UI work needs a screen blueprint entry consistent
with `design/07-screen-blueprints.md`.

## Ordering

A and B are backend and can proceed together. C depends on B. D depends on A for
the listing and C for the estimate. E is independent of A-C and can start
immediately. F precedes the code it describes.

    A ──┬── B ── C ──┐
        │            ├── D
        └────────────┘
    E (independent)
    F (first)

## The cohort, and what the whole thing actually costs

**The pilot ten are the first ten objects in source order:**
`subject_105526321` through `subject_105526330`. Decided 2026-09-14. Nothing
beyond ten runs until the browse-and-run screen exists; everything after the
pilot is triggered from the UI, per specimen or per selection.

Cost was measured, not estimated, from five of those ten processed end to end
through both configured routes:

| | per specimen | ten | all 1,000 |
|---|---|---|---|
| Tokens (both readers) | 1,991 in + 1,034 out | | |
| Inference at a realistic rate | ~$0.0016 | ~$0.016 | ~$1.62 |
| Inference at a deliberately high rate | ~$0.0041 | ~$0.041 | ~$4.06 |
| SAM segmentation, if run | ~$0.0034 | ~$0.034 | ~$3.40 |

Processing the entire thousand is single-digit dollars, not the order of
magnitude an earlier draft of this document claimed. That draft multiplied the
**whole cloud release ceiling** (USD 12, which covers Cloud Run, storage, IAM,
the restore clone, network and telemetry) by the specimen count. Infrastructure
there is mostly fixed cost; inference is the only line that scales with slide
count, and it is the cheap one.

This changes the emphasis of workstream C but not its design. Estimate-then-
reserve is still right, because a UI that spends money should always say how
much before it does. It is no longer a gate on building the screen, and the
number it shows will be reassuring rather than alarming.

## Open questions for the owner

1. **Who may run a bulk job?** Today any reviewer can process one specimen. A
   thousand at once is a different authority, even at a few dollars. This
   probably needs a role check.
2. **Do bulk runs need segmentation?** It is the slowest stage by far, about 25
   seconds per image against 5 to 7 for a reading, and it is Cloud-Run-only. A
   cheaper "read the label region only" default for bulk, with full processing
   on request, may be the better shape.
3. **What happens to a partly finished bulk run?** Cancellation, resumption and
   per-specimen failure are all reviewer-visible states that need a decision
   before D is designed.
