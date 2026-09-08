# Actual language and script declarations

Branch `codex/backend-reliability`, additive to graph/blob/CORS checkpoint `5a62aae`.

The transcription output schema accepts bounded optional language/script candidates and an explicit language relation. Candidates are opaque labels, not claimed validated BCP/ISO identifiers. Each list has at most eight distinct labels of at most 100 characters. Empty means undeclared. `cooccurring` and `alternatives` require at least two distinct language candidates; unspecified multiple candidates are not treated as confirmed mixed-language evidence.

The production adapter retains the original provider response bytes unchanged. A separate immutable declaration artifact anchors actual structured output and candidates to that raw hash, model ID and prompt hash. Per-reading metadata uses actual declarations and keeps Unicode-name hints separate. Original observations are not rewritten by reviewers. No confidence is invented.

Review uses the existing authenticated/CAS/idempotent decisions endpoint with `kind=reading_metadata`, a current observation `target_id`, and `after` containing only candidates/relation. The server derives actor, timestamp, scope, specimen/run/region/observation lineage, raw hash, reason, and supersession link. Human history is append-only and bounded to 32 entries per observation. The latest human entry supersedes previous human entries for effective metadata; all model declarations remain visible. An empty human declaration does not erase model evidence. Resegmentation invalidates old observation targets while historical evidence remains retrievable.

Label aggregation is keyed by run and region, explicitly distinguishes cooccurring languages from conflicting candidate sets, and retains both states when appropriate. The versioned `language-handling-v1` profile rule defaults unknown to unmeasured and mixed/conflicting to review. It does not supply approved museum languages or auto-Deferred outcomes. Label policy and visible reasons are retained in `run.label_language_handling`; explicit human approval remains separate. Declared labels do not assert calibrated language confidence.

Human metadata changes recompute only reading metadata/alignment, label handling/risk and disposition; previously retained phase outputs and authority receipts stay byte-identical. Approval is invalidated. Source reads, model declarations and human artifacts are digest checked before approval. A changed artifact yields an operational evidence-integrity block.

The existing reading metadata endpoint now contains real model/human declarations. The new authorized revision-aware `/observations/{observation_id}/declarations` endpoint exposes full retained structured model provenance and human history. Current membership/sensitive access still governs historical retrieval.

## Verification

- Canonical checks passed 270 Python tests with 24 explicit SQL/codec skips, scanners, Flutter analysis/widget/web (`/tmp/specimen-declarations-canonical.log`).
- Eleven targeted actual HTTP/adversarial tests passed after selective invalidation was refined (`/tmp/specimen-declarations-selective.log`): mixed versus conflicting, unknown, bounds/provenance spoof rejection, human supersession, same-key replay, stale CAS, restart, unchanged original readings/raw bytes, old targets after actual resegmentation, historical provenance and tamper-blocked approval.
- Production adapter exercised with a real PydanticAI FunctionModel response carrying language/script candidates; retained structured candidates/model/prompt/raw hash checked (`/tmp/specimen-declaration-provider-output.log`). No live or paid model request occurred.
- Frozen additive `backend-declarations-wire-examples.json` captures complete actual synthetic mixed/conflicting/unknown workspaces and two human edits with metadata/provenance. Generator: `generate_declarations_fixture.py NEW_OUTPUT`, refuses existing outputs. Retained source state: `/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-declarations-wire-vnw_iv8b`. Existing fixtures were not regenerated.

Institutional policy approval, live provider validation and museum quality calibration remain external gates. Nothing was pushed or deployed.

## Final verification and advertised action

The final core canonical run passed again (`/tmp/specimen-declarations-final-canonical.log`) after selective invalidation and production structured-output tests. Flutter caught a missing advertised capability: reviewer/manager/admin summary/workspace actions now explicitly include `reading_metadata`; viewer/operator actions do not. Twelve declaration tests pass after this addition (`/tmp/specimen-declaration-actions-tests.log`). Separate `backend-declaration-actions-wire-examples.json` contains clearly labelled projections of actual HTTP summary/workspace fields. It supplements the frozen complete fixture; no frozen response bytes were changed.
