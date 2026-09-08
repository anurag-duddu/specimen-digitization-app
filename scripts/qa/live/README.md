# Independent live acceptance tools

These tools never deploy, provision, download cloud objects, call providers or
execute commands found in an evidence file. Run from the repository root. The
test fixtures are authored synthetic data, not the authorized pilot cohort.

```bash
uv run pytest -q scripts/qa/live/test_acceptance.py
uv run python scripts/qa/live/local_probe.py --output /tmp/qa-unique-local-result.json
```

`local_probe.py` uses a temporary private SQLite/LocalBlobs directory and ASGI
TestClient; it opens no listening ports. It tests interrupted upload, replay,
correction, settled workspace reconstruction, original digest, history and
membership denials. It does not run Firebase, a browser or a worker subprocess.
Choose a new output path for each execution; existing evidence is not overwritten.
Output is mode 0600. Failed probes retain completed checks, sanitized failure
type and their temporary state directory for inspection. Successful probes
remove their disposable state. Product source must be clean; candidate and
harness digest are captured before execution and rechecked after execution.

`acceptance.py` independently checks the data owner's `specimen-pilot/v1` ready
manifest and an evidence ledger. The actual manifest must be outside Git, owned
by the current user and mode 0600. The expected SHA-256 must come from the
coordinator's frozen authority, independently of the file being checked. The
same applies to the full candidate commit SHA. Do not compute a replacement
expected digest from changed input to make validation pass.

```bash
uv run python scripts/qa/live/acceptance.py "$PRIVATE_READY_MANIFEST" \
  --approved-manifest-sha256 "$COORDINATOR_MANIFEST_SHA256" \
  --candidate-sha "$FROZEN_COMBINED_SHA" > "$NEW_PRIVATE_LEDGER"

uv run python scripts/qa/live/acceptance.py "$PRIVATE_READY_MANIFEST" \
  --approved-manifest-sha256 "$COORDINATOR_MANIFEST_SHA256" \
  --candidate-sha "$FROZEN_COMBINED_SHA" \
  --report "$PRIVATE_LEDGER" --evidence-root "$PRIVATE_EVIDENCE_DIRECTORY"
```

The first command emits 35 `not_run` cases. Use a private output directory and
`umask 077` before creating the ledger. Never place signed URLs, tokens, private
source paths/content or user identities in committed evidence. Preserve raw
evidence privately; commit only reviewed sanitized summaries. Artifact paths
are relative to the evidence root, with SHA-256 over exact retained bytes.

The evaluator returns 0 when the evidence structure is ready for independent
review, 1 when cases or deployment provenance remain incomplete, and 2 for
invalid input. Every output explicitly keeps `release_accepted: false`.
Passing fixture/emulator/owner-report rows remain pending for live acceptance.
The gate checks file integrity and internal consistency; it cannot prove a
claim was observed, establish the first-ten selection, or approve institutional
semantics, representative quality, data handling or spending.

Each passing row needs an observer, UTC start/end, sanitized command, expected
and actual behavior, transport, zero exit code and retained artifact digest.
Keep each negative case's positive control and denials in that artifact. Full
cohort coverage is required for DATA-TEN, DATA-GENERATION, PROVIDER-ACTUAL and
BROWSER-E2E. The denominator remains ten even when records fail or need review.
All 20 PRD criteria and 15 live threat/operations cases must be retained.

Deployment provenance binds the Hosting, API, worker and SAM commit SHA to the
combined candidate. All three image digests use `sha256:` plus 64 lowercase hex
characters. SAM additionally requires `sam_model_id=facebook/sam3`, a full
40-character `sam_model_revision`, and 64-character `sam_checkpoint_sha256` and
`sam_config_sha256`. These pins supplement connector/rules revisions and
workflow/job URLs; they do not prove real serving or quality. A final merged candidate SHA differs from an
owner PR head: create a new ledger and rerun relevant checks; never relabel old
evidence. A reviewer must verify immutable image digest formats, actual URLs,
workflow conclusions and runtime/data state against the deployed environment.
