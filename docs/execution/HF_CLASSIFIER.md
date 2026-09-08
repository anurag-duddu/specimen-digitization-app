# Hugging Face collection classifier

Implementation worktree: `/Users/anuragduddu/.codex/worktrees/36e1/specimen-digitization-app`.
Branch: `codex/hf-collection-classifier`.
Reviewed base: `6b4b654737d4d6bf7d26a749f431c15312c9a33b`.
Scope: this report, `src/specimen_digitization/application/hf_collection_classifier.py`,
and `tests/test_hf_collection_classifier.py` only. The commit containing this report
is the implementation handoff; its full SHA is sent to the coordinator separately.

## Contract and behavior

`HFCollectionClassifier(config=, gateway=, image_loader=, provenance_sink=, catalog=)`
implements synchronous `ClassifierAdapter.classify(ClassificationRequest)`.

- `HFClassifierConfig` freezes `route_id`, `expected_model_id`,
  `expected_provider`, `prompt_text`, `prompt_version`, `approved` (default false),
  `total_deadline_seconds`, `max_output_bytes`, `max_output_tokens`,
  `max_image_bytes`, and `max_image_pixels`.
- `gateway.route(route_id)` must identify that exact route, model, and concrete
  provider, with capability `collection_classifier`, text/image modalities and
  structured output enabled. `gateway.model_for(route_id)` supplies the actual
  Pydantic AI HuggingFaceModel. Existing handwriting routes do not automatically
  become approved classifier routes. Model identity and HF client provider are
  checked before loading the image; response identity is checked again.
- The trusted synchronous `image_loader(request)` returns
  `ApprovedClassificationImage(asset_id=, original_sha256=, png=)`. It must verify
  original-asset digest, tenant/collection authorization, approved provider data
  policy and canonical derivative lineage, with bounded retrieval and decoding.
  This module checks matching original identity, PNG structure, byte/pixel and
  single-frame limits, and records the separate canonical PNG digest. It cannot
  independently hash an original that the loader did not return.
- `catalog` is a copied mapping of allowed collection IDs to human-readable paths
  or names. Only request-allowlisted entries enter the prompt. Unknown or duplicate
  request IDs fail before dependencies are called. Catalog data remains server
  configuration; clients cannot provide an alternate catalog.
- Actual Pydantic AI Agent execution uses a bounded ranked-candidate schema,
  snake_case reason codes, one model request, zero executable tools and zero
  validation retries. Untrusted image instructions cannot expand collection IDs
  or tool authority. Unknown, duplicate, non-ranked and excess candidates fail
  closed; the adapter never sorts away a contract violation or adds a fallback.
- Scores remain uncalibrated. Every result has `calibration_version=None` and no
  synthetic fallback. A valid candidate response says `human_confirmation_required`;
  a valid empty candidate list says `no_candidates`. Selection/profile activation
  remains the backend's existing explicit human-confirmation flow.

## Raw evidence and telemetry

The synchronous `provenance_sink(envelope_bytes) -> nonempty_reference` writes
immutable, scope-restricted storage. Successful results require this reference.
Backend `classify_and_select` may hash the envelope at `raw_response_ref`.

The bounded JSON envelope records original request identity, canonical PNG digest,
exact constructed system/user prompts (including the supplied catalog), prompt and
adapter versions, concrete route/model/provider, output token setting, elapsed time,
structured output, status/reason, and the original Pydantic AI `ModelResponse` JSON
bytes encoded in base64 plus their SHA-256. Those response bytes contain usage,
timestamp, finish reason, response ID and provider metadata. Capture occurs before
Agent validation or mutation. Schema/identity/policy failures retain the response
when the configured byte/deadline budget permits. This is the **SDK ModelResponse**,
not byte-for-byte original HTTP wire data; `raw_format` explicitly names that format.

Over-limit responses and expired calls cannot retain a full response within their
budget and return an explicit block. Sink failures never return candidates as
completed. A sink that commits then loses its reply requires backend reconciliation;
a timeout cannot undo an already accepted remote model request or storage write.
The backend owns intent records, fencing, idempotence, retry/circuit and reconciliation.

No image bytes enter the envelope or logs. Agent instrumentation explicitly excludes
prompt/output content, binary images and request schema even if global instrumentation
is configured to capture content. Exceptions are reduced to fixed machine-readable
codes before Agent instrumentation observes them, never interpolated into results
or log strings. A captured-trace regression test checks success, schema errors,
HTTP errors and generic errors with global content capture enabled. Provenance contains potentially
sensitive model output and must remain private; it is not ordinary telemetry.

## Deadline and resource boundary

**Production must construct the gateway/loader/sink and execute this entire adapter
inside a trusted `bounded_effect.run_isolated` child factory.** Backend owner accepted
this responsibility directly. The module's remaining-budget checks and async model
cancellation are cooperative checks, not a hard whole-call bound: HF SDK discovery,
image verification and synchronous loader/sink code may block. No timeout thread is
used. Backend alone implements the factory and runtime wiring; none is enabled here.

Tests compose the adapter with the existing process boundary and deliberately block
loader, model and sink independently. Each child reaches the blocked operation, is
terminated and reaped at the overall deadline, returns no result and produces no late
effect. This proves the required composition locally; it does not prove the eventual
production factory until backend integration tests run.

The SDK materializes responses before this adapter checks serialized size. Therefore
`max_output_bytes` limits retained/output artifacts, not peak network allocation.
Backend's child memory/resource limit and bounded loader remain required. The provider
receives `max_tokens`, and reported output usage is checked; provider adherence and
actual billed cost need separately approved live validation.

## Verification and acceptance

Targeted local command: `uv run pytest -q tests/test_hf_collection_classifier.py`.
48 targeted tests cover the final adapter, including trace privacy regression cases.

Tests exercise the real Pydantic AI FunctionModel/Agent schema and binary content
path; the actual HuggingFaceModel/HuggingFaceProvider/gateway request mapping with
only the remote SDK completion replaced; raw byte equality and usage provenance;
allowlists, route capabilities, response model/provider binding; immutable config;
image identity/content/size/pixels; ranking, duplication, top-k and schema failures;
empty abstention; 401/403/429/500 redaction; output token/byte limits; model timeout,
late loader/sink, failed persistence; active-event-loop rejection; and three hard
process timeout/cleanup cases. No paid calls, cloud changes or museum images occur.

PRD coverage within this module: CLS-001/002/003/006 adapter portion; BYO-004/005/006
route policy; HAR-012/019 bounded abstention; section 14.4 provenance; section 15 typed
operational blocks; section 16.3 restricted telemetry. CLS-002 calibrated scores,
representative classification quality and section 19 end-to-end acceptance remain
**not confirmed**, pending approved evaluation data and human policy. This module
alone does not implement profile selection, correction invalidation or production.

An initial `scripts/ci/verify.sh` passed (315 Python tests, 24 skipped; Flutter
analysis, widget test and release web build passed). Final staged-file canonical
verification is recorded below after the final privacy regression fix. No push,
merge, provisioning, deployment or paid inference is authorized by this handoff.

## Integration finding

Installed Pydantic AI 2.40 `HuggingFaceProvider(hf_client=...)` still requires either
its `api_key` parameter or `HF_TOKEN` environment variable. Existing gateway passes
only `hf_client`; a Secret Manager token passed explicitly to the gateway can thus
fail if the environment variable is absent. Reported to backend owner for a scoped
shared-gateway fix: pass `api_key=self._token.get_secret_value()` to the provider.
The local HF mapping test supplies a harmless fixture environment value. This task
does not mutate the shared gateway or credentials.

Primary SDK references checked alongside the installed locked SDK source:
[Pydantic AI Hugging Face](https://pydantic.dev/docs/ai/models/huggingface/),
[testing](https://pydantic.dev/docs/ai/guides/testing/), and
[ModelResponse](https://pydantic.dev/docs/ai/api/pydantic-ai/messages/).

## Final local gate

Final staged-source `scripts/ci/verify.sh`: **passed**. Repository/secret checks
passed; Python **319 passed, 24 skipped, 7 warnings** in 66.44 seconds (includes all
48 classifier tests); Flutter dependency lock enforcement, analysis, widget test
and release web build passed. The 24 skips are existing environment-dependent
backend checks and do not establish live infrastructure behavior. The script
removed its temporary credential-free Firebase options file. `git diff --check`
passed; only the three owned files are staged. No deployment was performed.
