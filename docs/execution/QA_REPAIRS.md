# Frozen candidate API repairs

Base: 4c71e133acc9f99c2dae068f4199c806bde8ff5f.
Isolated branch: codex/upload-completion-repair.
Worktree: /tmp/specimen-upload-completion-repair.
No unfinished reliability-wave changes, cloud changes or deployment.

## QA-B01 and QA-B02

Commit 7a47b10 retains the completion request fingerprint (actor, key, upload and typed body) and original response in the upload document. The same fingerprint also binds the transactional ingestion receipt, including recovery between specimen creation and upload acceptance. Exact replay returns the original response even after background processing advances the specimen. Changed requests return 409. Legacy accepted uploads without a receipt fail closed rather than inventing an original response.

Image verification now fully decodes the pixel stream in addition to container verification. Decoder OSError, SyntaxError, EOFError and decompression-bomb failures become stable 422 input responses. Blob transport errors remain operational failures.

Validation: canonical scripts/ci/verify.sh passed, 64 Python passed / 2 opt-in SQL tests skipped, Flutter analyze, 16 Flutter tests and web release build passed. Two new actual TCP tests cover response stability after worker progress, changed body/key, 60-byte valid-header truncated PNG, repeated malformed requests and healthy subsequent requests on the same httpx client connection. No malformed input creates a specimen.

## QA-B03

Shared integrity verification runs before worker finalization and before review approval or capability deferral. It resolves the stored original and raw evidence bytes, checks SHA-256, original size/MIME/decoded dimensions, region ownership/geometry, observation region/input provenance, transcript associations, evidence ownership and raw lookup/evidence digests. Retained crop/mask references are resolved when present. Production-mode inputs are checked against the same RGB PNG crop computation used for inference; synthetic inputs retain their explicit original-byte convention.

Unavailable or corrupt evidence persists processing_blocked with evidence_integrity_failure and no scientific disposition. Restoring the original bytes permits a new versioned approval; only this integrity blocker is cleared. Earlier snapshots and blocked decision receipts remain unchanged. This is verification at the finalization boundary, not an ongoing storage monitor or a live production validation claim.

Validation: tests/test_evidence_integrity.py covers missing/corrupt source, observation and lookup storage through HTTP approval, restoration, immutable blocked receipt replay; substituted raw digest/reference, foreign asset ID and wrong input hash through stored-graph fault injection and HTTP approval; worker finalization; and non-synthetic crop hashing without an external model call. Existing ambiguous-authority fixture now retains its actual synthetic response bytes so its provenance meets the same gate.

Integration and QA should repeat the independent SQL/TCP reproduction on the assembled repair candidate. No paid inference, live authority validation or production release is claimed.
