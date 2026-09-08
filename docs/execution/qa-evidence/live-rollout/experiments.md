# Preserved experiments

## Local correction reconstruction assertion

Candidate: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Command: `uv run python scripts/qa/live/local_probe.py --output docs/execution/qa-evidence/live-rollout/baseline-local.json`.
Initial exit: 1, `AssertionError: correction-app-recreation`.

The first probe compared the immediate correction response with a reopened
workspace. A transcription correction schedules downstream revalidation, so
the immediate response can precede a legitimate later revision. The corrected
probe reads the settled workspace through HTTP after background processing,
then recreates the app and compares that exact saved state. It also separately
checks retained original observations, replay idempotency and changed-payload
conflict. No direct database edit or product change was made.

Rerun exit: 0; 24 checks passed. See `baseline-local.md`. This is a correction
to a QA timing assumption, not a repaired product defect. Logfire emitted its
unconfigured warning; no telemetry was configured or sent by the probe.

## Canonical gate first attempt

`scripts/ci/verify.sh` exited 1 at detect-secrets because the generated JSON
quoted the public candidate commit and authored raster SHA-256 as high-entropy
strings. Gitleaks and the other repository checks passed. No credential was
present. The same observations are retained in a sanitized Markdown table with
the exact digests; the raw local JSON was moved to a private mode-0600 temporary
file. No scanner, baseline, allowlist or workflow was changed. Future raw
machine evidence belongs in the private evidence directory.

## Independent harness review

Bounded read-only QA-tool review found three P2 issues: failed checks exited
before saving evidence, independently duplicated manifest validation accepted
malformed names/extra fields rejected by runtime, and a dirty product could be
attributed to HEAD. All three were fixed before submission. The reviewer
independently reran all 45 QA tests, injected initial source-identity failure,
and verified exit 1, mode-0600 sanitized artifact, no executed probe checks,
no exception-text leak and `release_accepted: false`. No remaining actionable
findings in the reviewed fixes. Review occurred on this PR's precommit source;
the delivered harness source is pinned by the final PR commit.
