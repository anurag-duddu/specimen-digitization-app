# Repository instructions

These instructions apply to every branch, worktree, and Codex session in this
repository.

## Session closeout ritual

Every Codex session that changes, reviews, coordinates, or releases this
repository must use [`docs/SESSION_LEARNINGS.md`](docs/SESSION_LEARNINGS.md) as
the shared, append-only closeout log.

- Before a handoff, merge, archive, branch deletion, or worktree removal, append
  the session's outcome, durable evidence, reusable learnings, failed approaches,
  and unresolved follow-ups.
- Name the task ID, branch/worktree, relevant commits and pull requests, and the
  validation actually run. Use `Not confirmed` when evidence is unavailable.
- Do not rewrite or delete another session's entry. Correct an earlier entry by
  appending a dated correction that links back to it.
- A coordinating session may prune only after it has reconciled the entry with
  live Git/GitHub state and confirmed that no uncommitted or unmerged work will
  be lost.

This is a required repository ritual, not optional handoff prose.

Before changing CI, release configuration, Firebase Hosting, Google Cloud IAM,
GitHub environments, or production, read `docs/DEPLOYMENT.md` completely.

## Deployment rules

- Production deployments MUST be performed only by
  `.github/workflows/ci-cd.yml` after a pull request is merged to `main`.
- Never run `firebase deploy`, a Hosting channel deploy, or a `gcloud ... deploy`
  command from a workstation or an agent shell.
- Never deploy SQL Connect schemas, database migrations, Storage rules,
  Functions, Cloud Run services, or model workers through the Hosting workflow.
- Do not add AWS deployment resources or AWS credentials unless the user makes
  a new, explicit architecture decision.
- Do not bypass, weaken, or disable required checks, branch protection, the
  `production` GitHub environment, pinned action SHAs, or Workload Identity
  Federation conditions to make a release pass.
- Use `scripts/ci/verify.sh` before pushing. Use a pull request. Wait for every
  required check. After merge, wait for the `main` workflow and verify the
  deployed commit through the public `deployment.json` marker and smoke test.
- A release is not complete at commit, merge, workflow start, artifact upload,
  Firebase CLI success, or a generic HTTP 200. Record the commit SHA, pull
  request, green workflow run, successful deploy job, matching public
  deployment marker, and public application smoke result.

If a production release is blocked, stop and report the exact gate. Do not
substitute a hand deployment.
