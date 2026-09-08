# Evidence harness and authorities handoff

Worktree: `/Users/anuragduddu/.codex/worktrees/5178/specimen-digitization-app`.
Branch: `codex/evidence-authorities`. Base: `034d806c30b21e2b1d031ac6c84b6c80637088e8`.
Final implementation SHA is sent with the coordinator handoff after commit.
Scope is exclusively five new application modules, their five matching new test
modules, and this report. Existing workflow/domain/API/harness/policy/lookup,
dependencies, infrastructure and other worktrees are unchanged.

## Executable interfaces

- `authority_registry.AuthorityRegistry(version, sources)` holds immutable,
  explicitly approved source endpoints, source versions, operation allowlists,
  organization/collection pairs and permitted data classifications. No default
  source is approved. Endpoint credentials, query strings, fragments and HTTP
  are rejected. An approved endpoint is server configuration, never model input.
- `AuthorityQuery(organization_id, collection_id, data_classification, literal,
  evidence_ids, historical_context=None)` carries the retained literal lineage.
- `PartiesAdapter(registry, blobs, connection=None, token=None, client=None)` and
  `GeographyAdapter(registry, blobs, client=None)` expose `lookup(query)` returning
  immutable `AuthorityResult`, using the existing `LookupStatus` taxonomy.
- Results preserve literal text, input evidence IDs, exact non-secret query JSON
  and SHA-256, retrieval time, source/adapter versions, raw-body blob reference
  and SHA-256, candidate identities, support/unresolved relations, context and
  optional source-configured licensing metadata. No endpoint response headers,
  tokens or exception text enter evidence. Typed candidates also support explicit
  contradiction supplied by a source comparison.
- `run_phase(spec: HarnessSpec, inputs: PhaseInput) -> PhaseResult` has no I/O.
  The spec pins profile ID/version and each named phase/version. Results include
  applicability, candidates, lookup outcomes, findings, planned tools, budget
  usage and deterministic input/output digests. Callers retain the input evidence
  graph; the digest alone is not a replacement for retained inputs.
- `HarnessRunner(tools).execute_one(spec, call, query, usage, checkpoint,
  previous=None) -> ToolReceipt` executes exactly one registered/versioned tool.
  `checkpoint` must durably persist intent before the call and completion after
  it, using the backend's existing lease/CAS guard. A retained completed receipt
  replays without a call after digest validation. An intent returns
  `external_outcome_unknown`; retry requires an explicit outer-workflow action.
- `review_risk(signals, policy) -> ReviewRisk` returns weights, individual inputs,
  bounded contributions, reasons, algorithm/feature version, calibration-version
  metadata and input digest. It has no disposition or clearance operation.
  Calibration remains false: a named dataset alone does not prove calibration.

Backend task `01a07f47-f5cc-7c10-bc1f-571b086e9cd2` owns application assembly.
Collection profiles bind HarnessSpec by `(profile.id, profile.version)` and must
constrain phase tools to their published profile.tools. No dependency on the
unlanded collection module is introduced here.

## Phase behavior and policy boundary

Parse validates literal containment in the retained source excerpt and proposes
literal candidates. The existing extractor must still verify the excerpt against
the adjudicated transcript; a SourceLiteral is trusted application input, not an
unvalidated model tool argument. It includes asset, region and observation IDs.
Plan reports the phase's configured tool list without invoking it. Lookup and
normalize retain independent candidates and source lineage; missing captured
response provenance cannot produce a normalized proposal. Resolve preserves all
alternatives and reports unresolved or competing values. Validate/finalize check
mandatory evidence presence, alternatives and known semantics, returning findings.
Absent phases block; explicit non-applicability has a persisted reason.

These evidence validators supplement the existing policy. Core numeric/date,
coverage, independence, required-party identity selection and institutional
clearance checks must still execute. No phase sets a final queue, treats a score
as truth, expands Verbatim D/T/S, or converts absent elevation units. This module
is deterministic phase infrastructure; it does not claim an autonomous historical
reasoning agent or an additional model extraction implementation.

## Source implementations and verified interfaces

Parties uses the documented EMu Texpress search envelope (`hits`, `matches`,
record `id`, `version`, `data.NamFullName`). Field Museum's official implementation
uses POST with `X-HTTP-Method-Override: GET`; the adapter follows that read-only
search pattern with a JSON-encoded exact-name filter and minimal selected fields.
It requests only ID, record version and full name. Identifiers must match the
configured tenant and `eparties` module with positive IRN. The immutable identity
also includes source system, connection ID, environment and tenant. Catalogue IRNs
and a different tenant are schema failures. A unique name result remains ambiguous:
a real Parties record does not by itself prove it is the label's person. Backend
review must record corroboration/selection; this adapter never invents an IRN.

Official references checked in this task:

- [Field Museum search implementation](https://github.com/fieldmuseum/emurestapi-examples/blob/main/php/src/Texpress/Search.php)
- [Field Museum search example](https://github.com/fieldmuseum/emurestapi-examples/blob/main/php/tests/Unit/SearchTest.php)
- [Axiell Texpress search contract](https://help.emu.axiell.com/emurestapi/3.1.3/04-Resources-Texpress.html)
- [GBIF Occurrence/GADM API](https://techdocs.gbif.org/en/openapi/v1/occurrence)

Geography uses the fixed public GBIF GADM search endpoint. One read-only public
`Illinois` probe confirmed the results/endOfRecords envelope, modern region ID,
variants and higherRegions shape. This was public data, no paid inference or
private specimen query. An exact unique modern administrative name can support a
candidate. Multiple or incomplete results remain ambiguous. Historical context
forces ambiguity and is retained separately in candidate context alongside modern
parents; the adapter does not resolve historical jurisdiction, city/site precision
or coordinates. Mapcarta/Google automation is not enabled or silently substituted.
The source must explicitly approve GADM for the collection; repository guidance
allows modern supporting evidence, not institutional clearance by itself.

## Bounds and recovery

Each adapter performs one request, follows no redirects or response links, and
has a configured timeout at most 30 seconds and a streamed response-size cap at
most 1 MiB (default 256 KiB). Oversized content retains a bounded prefix digest
and explicit truncated-capture reason; it is never a successful complete response.
HTTP 401, 403, 429, provider failure, timeout, empty body, no match, ambiguity,
malformed response and missing policy/configuration remain distinguishable.
Retry-After seconds or HTTP dates are parsed and bounded to one day. Automatic
backoff, circuit breakers and retry scheduling are intentionally owned by the
existing durable worker; there is no second retry loop.

Harness calls reserve one tool count before execution and track elapsed usage.
Only explicitly known-free authority calls are supported; unknown or nonzero
cost estimates block, and no model tokens are consumed. Run counters come from
the outer persisted state. The elapsed budget is checked before new work; an
in-flight HTTP request uses its separately configured bounded timeout. Hard
process-level cancellation is not provided. Caller configuration must leave
call-timeout margin below the worker lease and enforce whole-run budgets.
Authority client transport injection is a test seam, not production approval.

## Verification and remaining integration gates

New tests exercise actual local TCP HTTP request/response bytes for both adapters,
including read-only POST method override, minimal selected fields, scope denial,
wrong tenant/module, candidate identity, missing credentials, modern/historical
ambiguity, no-match, empty, malformed, 401/403/429/5xx, redirect rejection and body
bounds. Timeout injection uses httpx MockTransport and is explicitly synthetic.
Harness tests cover intent/completion, input tampering, output digest tampering,
zero-call replay, unknown outcome, checkpoint failure before network, budget and
tool allowlists, evidence propagation, competing candidates, missing authority
capture, unknown semantics and phase applicability. Risk tests preserve exact
minority numeral spans, differing lines and script uncertainty; zero weights
cannot erase hard findings or create a clearance disposition.

Validation performed:

- `uv run pytest tests/test_authority_registry.py tests/test_parties.py tests/test_geography.py tests/test_evidence_harness.py tests/test_review_risk.py -q`: 41 scoped tests pass as part of the full suite.
- `scripts/ci/verify.sh`: 95 Python tests pass, two existing SQL-emulator-only tests skip; repository hooks and both secret scanners pass; Flutter analyze, widget test and release web build pass.
- `uvx ruff check` with undefined/unused-name checks on all ten new Python files and `git diff --check`: pass.

Resolve also emits typed cross-source comparisons with both values, source IDs and
evidence IDs. Exact equal normalized strings support one another; differing
strings are flagged as contradictory proposals needing review. This is not
semantic synonym inference or authority precedence. Unicode script observations
are name-prefix diagnostics, not a calibrated language/script classifier.
No live Parties connection, museum identity matching, approved Google/Mapcarta
API, representative quality calibration, paid model call, provisioning, merge or
deployment was performed. These are additive tested modules, not evidence that
the running application's new phases are integrated. Backend assembly and its
HTTP/SQL regression run remain required, along with the institution's actual
read-only authority access and field/source policy decisions.

PRD coverage is component-level HAR-001..008/010/012/014/018/019,
TRN-006/007, SCR-001..004/006 and REV-003. Section 19 criteria 7, 8, 10,
12 and 16 gain executable regression coverage here; this does not mark their
end-to-end application acceptance complete. HAR-009 retry/circuit integration,
policy queue decisions, SQL reconstruction and representative institutional
quality remain with their named owners and external approval gates.
