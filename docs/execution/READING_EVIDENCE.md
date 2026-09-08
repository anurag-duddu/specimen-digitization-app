# Bounded reading evidence and metadata

Worktree `/Users/anuragduddu/.codex/worktrees/5178/specimen-digitization-app`;
branch `codex/reading-evidence-metadata`; clean base
`0da144de081cf7a28154ec2c1cd90fbea9834064`. The implementation commit is sent to
the coordinator and backend/Flutter owners after final gates. Scope is exactly
`application/reading_evidence.py`, `tests/test_reading_evidence.py` and this report.
Existing review_risk, domain, transcription, workflow, dependencies and other
worktrees remain untouched. This extension supersedes the old short-reading
comparison at the backend composition boundary; it does not wire shared modules.

## Typed contract

`ReadingEvidenceInput` contains observation/region IDs, immutable source_ref,
optional source_sha256, literal text, explicit source_truncated and bounded
MetadataDeclaration entries. The source SHA is the existing raw provider artifact
digest; text_sha256 is separately computed over exact UTF-8 text. They are not
interchangeable. The caller supplies declarations only when reported by a retained
provider/model/classifier response or recorded human action.

Each declaration has kind language/script, optional value, method, producer,
version, evidence_ref, locator, reason and optional reported_confidence. Missing
confidence stays null. Unknown value cannot carry confidence. Declared candidates
are not verified language/script classifications, even when one value exists.
Multiple values remain explicit alternatives; no automatic winner is selected.

`summarize_reading(input, limits=ReadingLimits()) -> ReadingMetadata` returns
reference/digest, available or policy_blocked status, explicit language/script
unknown/declared/multiple_candidates states, original declarations and reasons.
Unicode name-prefix diagnostics retain the runtime Unicode database version and
bounded counts. They are labelled as heuristics, not Unicode Script property
classification or language detection. Latin letters alone never identify English.
A blocked reading does not run the heuristic or disguise a partial count as full.

`align_readings(left, right, limits=ReadingLimits()) -> ReadingAlignment` compares
distinct observations of the same region. It returns agreement, disagreement or
policy_blocked, immutable input references, comparison digest, measured matrix
cells, working-memory reservation, edit distance only for completed analysis, and
bounded alternatives. Equal raw readings prove text equality, not correctness or
complete metadata. Empty, truncated or invalid-Unicode readings cannot agree.

Every alternative has operation replace/insert/delete and both source spans:

- `start/end.codepoint`: Python raw Unicode scalar indices, zero-based half-open.
- `start/end.utf8_byte`: offsets into exact UTF-8 text bytes, zero-based half-open.
- `start/end.utf16_codeunit`: Dart string offsets, zero-based half-open.
- `line`: one-based logical line; `column_codepoint`: zero-based raw codepoints.
- `text`: exact source slice. A zero-length insertion/deletion side is legitimate.

CRLF is one line break and both raw characters remain traceable. Other Python
splitlines-style Unicode line separators are recognised. Unicode normalization,
case folding and whitespace repair never occur. A decomposed combining sequence
and its precomposed equivalent remain different raw readings. Positions are scalar
boundaries, not grapheme-cluster boundaries: a combining mark can be a separate
span, and clients must not silently normalize or expand it in saved evidence.
Non-BMP characters have two UTF-16 code units. Invalid unpaired surrogate values
block rather than crash or manufacture a replacement character.

`reading_risk_evidence(alignment, metadata) -> ReadingRiskEvidence` produces
existing RiskSignal types for unresolved disagreements, numeral differences or
blocked analysis, plus explicit unmeasured dimensions. It requires metadata for
both exact observation versions before a language/script dimension can be treated
as declared consistently. Missing, conflicting or blocked metadata remains
unmeasured. Foreign/duplicate metadata is rejected. A blocked alignment never
becomes zero measured disagreement. No risk score or queue is assigned here;
backend and Flutter must display unmeasured alongside existing triage components.

## Bounds and algorithm

The input strings already exist in caller memory. This module bounds additional
analysis and does not claim an operating-system memory cap for an API process.
Defaults per reading are 100,000 codepoints and 400,000 UTF-8 bytes. Length is
checked before traversal and hashing uses 2,048-codepoint chunks. If a bound or
invalid scalar prevents a complete digest, text_sha256 and comparison_sha256 stay
null; source_ref, source_sha256 when supplied and full codepoint length remain.
No prefix digest is represented as the full text hash. Blocked results must not
be used as content-cache keys. The existing raw observation remains retrievable.

Alignment trims only an identical prefix/suffix by indices, then computes a
codepoint Levenshtein alignment over the remaining middle. It stores compact
one-byte directions and two uint32 rows, with deterministic tie-breaking.
Default work limits are 65,536 cells, a conservative 4 MiB working reservation,
256 spans and 20,000 total copied alternative codepoints. Reservation includes
buffer space, bounded edit objects/positions and copied alternatives; it is not
an RSS measurement. The module checks before allocating the matrix. Limits on
output are checked before slicing retained alternatives. Exhaustion returns a
specific policy_blocked reason, no partial result, and no edit-distance score.
No long reading or minority edit is silently dropped.

A 90,004-character fixture with one differing numeral completes with four matrix
cells, retains the exact offset and copies only two alternative characters.
Broadly different long inputs block on the cell bound, leaving raw references
available for an approved larger-budget run or manual review. No automatic
fallback to SequenceMatcher, truncation or coarse agreement is used.

## Validation and integration

Tests cover unknown declarations and absent confidence; model/classifier provenance;
multilingual and mixed-script hints; Arabic numerals, CJK, Greek/Cyrillic, astral
emoji and ZWJ sequences; combining/precomposed differences; CRLF and Unicode line
separators; exact UTF-8/UTF-16/codepoint reconstruction; insertions/deletions;
truncated/empty/invalid scalar failures; input/cell/memory/span/output limits;
long reading memory measurement; deterministic randomized multiscript reconstruction;
independent small recursive edit-distance oracle; typed serialization/digest
roundtrip; and unmeasured/foreign/conflicting risk metadata.

Verification passed on the staged implementation:

- `uv run pytest tests/test_reading_evidence.py -q`: 23 passed.
- `scripts/ci/verify.sh`: 118 Python tests passed, two existing emulator-only
  tests skipped; all repository/secret checks, Flutter analysis/widget test and
  release web build passed.
- Ruff undefined/unused-name checks and `git diff --check`: passed.

The test environment reports existing Starlette deprecation and unconfigured
Logfire warnings; this module introduces no network calls or telemetry. No live model,
private data, paid inference, provisioning, merge or deployment occurs. Source
metadata propagation and serialized workspace fields remain backend-owned;
Flutter consumes the serialized spans and authenticated evidence route, never
resolves a blob reference itself. Contracts were sent directly to both owners.

PRD component coverage: TRN-006/007/009/011/012 and SCR-002/003/004/006;
section 19 criteria 5/6/16 gain source-preserving metadata/disagreement components.
Representative script/language quality and application HTTP/SQL/UI integration
remain unverified here. This is a deterministic bounded evidence analysis tool,
not a language classifier, adjudicator, transcription model or clearance gate.

Primary interface references checked during this task:
[Python strings and line boundaries](https://docs.python.org/3/library/stdtypes.html#str.splitlines),
[Python Unicode database](https://docs.python.org/3/library/unicodedata.html),
and [Dart String UTF-16 representation](https://api.dart.dev/dart-core/String-class.html).
