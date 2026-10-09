# Elevation harness domain plan

Task: Elevation harness, 2026-10-07. Branch: `codex/harness-measurement`.
Worktree: `/Users/anuragduddu/.codex/worktrees/0934/specimen-digitization-app`.
Remote `main` verified at `7890de551c75fe3b06836c7fb224f85dd2a2423a`.

1. Reproduce the deterministic settlement gap: independent accepted assertions
   currently compare endpoints but can discard conflicting qualifiers or written
   uncertainty. Require exact scientific agreement while retaining every literal.
   Equivalent complete ft/m assertions may agree only through an accepted event;
   independent readers of one label must not be silently reinterpreted.
2. Verify ranges, signs, thousands/decimal notation, approximation, uncertainty,
   conflicting measurements, missing units and tampered output. Preserve G41's
   exact `1 ft = 0.3048 m`, native-source lineage and all four field endpoints.
3. Repair derived-only calculation against genuine existing checkpoint pins where
   current contracts permit it. Keep protected human Unknown intact. Missing pins
   remain a structured policy outcome, never an invented checkpoint or a question
   asking for a value already written.
4. Add a domain adapter for location-derived elevation eligibility/proposal use
   only if needed by existing approved contracts. DEM is presently reviewer-only:
   retain whole-coordinate-uncertainty coverage and captured dependencies, refuse
   replacement of a label elevation, and document the automatic-derivation policy
   prerequisite instead of changing that ruling.
5. Run focused offline parser, real scripted-agent/checkpoint, replay and composed
   fake-DataConnect publication tests. Confirm interrupted calculations can be
   retried/replayed without altering accepted evidence. Fixture, composed offline,
   source-provider and live-production evidence will be reported separately.

Shared browser/code/memory/recovery adapters belong to the geography lane. This
lane owns measurement helpers, policy, prompt hunks and tests; it does not change
the common writer, scheduler, journal, effect holds or production release path.
Memory needs: reviewed unit/qualifier procedures with versions and evidence,
never specimen facts or model-weight updates. Source dependency pins and related
label event grounding must be supplied by verified shared infrastructure.

Dosu CLI `0.66.1` reports an expired session; deployment inspection could not save
refreshed credentials within this lane. No knowledge tool is listed by the server.
The coordinator's reported monthly-credit exhaustion will not be retried.

Closeout: append actual changes, evidence and remaining prerequisites to
`docs/SESSION_LEARNINGS.md`; create a local reviewable commit if focused checks pass.
No push, merge, canonical suite, paid canary or production mutation in this lane.

## Implemented slice

- `evidence.py` now compares complete scientific assertions: exact converted
  endpoints, single/range meaning, approximation, converted written uncertainty,
  precision and datum. All supported approximation spellings express the same
  qualifier; every spelling is retained in the assertion metadata. Missing
  uncertainty remains distinct from explicit zero. ASCII `+/-` is accepted with
  the same unit and nonnegative-uncertainty checks as `±`.
- `measurement.py::pinned_elevation_resolutions` consumes an omitted native source
  only when its complete reconstructed settled-row digest matches one unambiguous
  immutable request dependency. It uses that pin's revision. Bare revisions,
  missing/stale pins and human outcomes cannot supply a source checkpoint.
- `sources.py::local_settlement_result` includes every elevation assembly of the
  accepted event even when the output request excludes its native source field.
  The replay verifier uses that same role-specific inventory. Other domains'
  assemblies remain available in the event graph without supplying elevation.
- Measurement-only utility feedback names scientific disagreement and preserves
  the structured unresolved path. The new immutable v10 prompt describes exact
  agreement, full utility provenance, derived-only repair and output subsets.
  Historical v6-v9 prompt bytes remain unchanged.
- Validator v4 pins the changed `evidence.py` bytes and retains/revalidates the
  previous v1-v3 proof pairs. Integration must recompute the final source SHA after
  composing any other lane's `evidence.py` changes; do not copy this lane's SHA
  over a different final file.

## Field outcomes and stop rules

The four owned fields are `elevation_from_m`, `elevation_to_m`,
`elevation_from_ft`, `elevation_to_ft`. A supported single value copies both
endpoints and derives converted quantities under G41; a range retains distinct
endpoints. A written 6,400 ft yields 6,400 ft and 1,950.72 m at both endpoints.
Exact equivalent statements on independently accepted same-event assemblies
retain both originals. No range, qualifier, unit or uncertainty is discarded to
manufacture agreement, and no numerical tolerance is introduced.

Unqualified/ambiguous evidence follows the profile's declared missing-policy
review outcome with an explicit reason and no invented value or conversational
question. A missing native source pin produces
`protected_native_dependency_unavailable:<source_field>` for the affected target.
The existing three product queues remain Cleared, Needs Human, Deferred;
operational failure/unknown-send rules were not changed into scientific absence
or a new queue. Pure local cancellation can replay the captured model response and
recompute deterministic arithmetic. Unknown external sends retain their holds.

## Remaining shared and policy prerequisites

1. The completion continuation now supplies measurement `request.dependencies`
   through the factory's service-owned accepted-checkpoint capture reader. It
   requires exact current native originals or proved generation reuse, original
   accepted-output closure, supported written settlement and matching runtime
   pins. Bare revisions, missing proof/readers, derived rows and preserved human
   outcomes cannot supply a source. The utility still requires its reconstructed
   source resolution to match that pin exactly, including after scope changes.
2. Its ordinary elevation grounding still requires one label region and identical
   reader-level written units/qualifiers. Exact-key lines now use the same
   retained-reader checks, including explicitly headed malformed readings and
   other labels' retained elevation claims. A target field key never asserts the
   written source unit: `elevation_from_m: 6,400 ft` retains feet as the native
   source and uses G41 for metres. Cross-label support requires an actual accepted
   event containing all assertion fragments with pinned semantic validation;
   complementary fragments additionally need accepted continuation relations.
   The ordinary snapshot provides no such join. Equal values, units or a model
   assertion never establish common-event membership, so that source hold stays.
3. DEM already has a domain adapter:
   `GeoreferencingAdapter.derive_rest` / `_elevations`, followed by
   `derivation_source_result`. It requires established label-elevation absence,
   verified location inputs with revisions, qualified pinned datasets, and
   complete coverage of the coordinate uncertainty circle. Captured proposals
   retain location dependencies, source/dataset IDs, extrema and computation
   evidence. They explicitly require human review and prohibit automatic
   settlement. G37 records the general missing-elevation derivation intent, but
   the registered path's concrete contract remains reviewer-triggered proposals:
   geography-v8, `derivation_worker._resolution`, `evidence.validate_resolution`
   and `source_capture_v2` all require human review and prohibit automatic
   settlement. An approved policy for a trusted autonomous producer must
   supersede that proposal-only contract, specify proved label absence and
   current settled location dependencies, and authorize how a fully covered
   pinned DEM range becomes all four derived field resolutions with dataset and
   computation lineage. Shared capture/admission must implement that same policy
   and retain every uncertainty-circle/no-data/source-failure hold. No automatic
   DEM flag or new source adapter was introduced in this continuation.
4. Shared browser/code/memory/recovery remain geography-owned. The pinned
   [harness v0.36.0 exports](https://raw.githubusercontent.com/pydantic/pydantic-ai-harness/v0.36.0/pydantic_ai_harness/__init__.py)
   were checked against the installed package (`pydantic-ai-slim` 2.51.0).
   Memory/Skills/Shell constructors are available; CodeMode import currently
   requires the uninstalled `pydantic-monty` optional dependency. No optional
   runtime, browser or model integration was installed or claimed in this lane.
   Measurement memory should contain reviewed, versioned unit/qualifier
   procedures and exact replay lessons, never specimen facts. Raw/adjudicated
   evidence must stay in the scoped immutable input/capture store.

Focused evidence and the final local commit are recorded in
`docs/SESSION_LEARNINGS.md`. Live source-provider, live native writes, authenticated
product acceptance and production release: **Not confirmed**.

## Isolated completion continuation

Task `01a11840-fd33-7fe3-babb-bd00b5506c4f`, source lane
`/root/elevation_completion_sol_ultra`, branch
`codex/lane-p-elevation-completion-20261007`, worktree
`/Users/anuragduddu/.codex/worktrees/lane-p-elevation-completion/specimen-digitization-app`.
Starts from the committed measurement slice `6c3a6bcf13f459f914cbb72fe6cb8f374b11a7b0`
with parent `main` `7890de551c75fe3b06836c7fb224f85dd2a2423a`; the original
measurement worktree is preserved. Root owns integration and production.

The service-owned reader recovers the immutable native accepted-output capture
using the existing store and blobs. The factory captures source pins only for
measurement; the engine keeps those pins when narrowing to pending/retried
targets and checks the loaded current checkpoint again before investigation.
No journal, scheduler, canonical writer, effect hold, budget or source-quote
contract changed. Interrupted pure arithmetic recovery and protected human
Unknown retain the existing behavior.

Keyed elevation admission now uses the distinct
`exact-elevation-field-key-line/v1` semantic validator. Every literal reading is
retained, including rejected/malformed claims. A keyed multi-label veto alone
was insufficient: the organiser could subsequently ground the other label when
the keyed assembly was refused. Both paths now include actual explicit elevation
lines in the region inventory, so neither can hide an omitted extractor claim.

The final `evidence.py` SHA remains
`b5af78b21598200ba6b603b95b7a81fa5f06f5161a95d6d3320120842854f98d`, matching
validator v4. Its bytes, v1-v3 proof pairs and historical prompt files were not
rewritten. Tests in this lane use the frozen baseline AI/Graph/Evals 2.51.0 and
Harness 0.36.0. The separate shared package-upgrade lane owns current-version
adoption and later combined qualification; this continuation makes no package
compatibility or deployed-source claim for that successor.

The public fake-DataConnect fixture previously wrote a genuine `180 to 181 m`
range alongside naked, rounded numbers under the three other elevation keys.
Those extra lines are unproved written assertions, and admission now holds them.
The test-owned fixture states only the genuine range, retains all twenty field
slots, and expects seventeen source rows to support nineteen published fields.
The removed derived numbers stay in a negative fixture; product admission was
not relaxed to pass that composed test.

Dosu 0.66.1 is installed. Root attempted the newly listed knowledge MCP route
once and received the monthly 4,000-credit pause, without a receipt ID; this lane
did not retry, change authentication/Library/billing, write knowledge or finalize
an empty session.
