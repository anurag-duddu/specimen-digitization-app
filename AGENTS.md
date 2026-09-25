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
- Two branches appending to this file no longer conflict. `.gitattributes`
  marks it `merge=union`, so Git keeps both sides automatically. That works
  only while the rule above holds: never edit a region another session wrote,
  or union will keep both versions of it. Correction, 2026-09-23 (go-live
  program): the union driver runs only in local merges. GitHub's server-side
  merge (the merge button and `gh pr update-branch`) ignores it and reports a
  conflict, so bring a branch up to date with `git fetch origin && git merge
  origin/main` locally and push.
- A coordinating session may prune only after it has reconciled the entry with
  live Git/GitHub state and confirmed that no uncommitted or unmerged work will
  be lost.

This is a required repository ritual, not optional handoff prose.

Before changing CI, release configuration, Firebase Hosting, Google Cloud IAM,
GitHub environments, or production, read `docs/DEPLOYMENT.md` completely.

## Deployment rules

- Hosting production deployments MUST use `.github/workflows/ci-cd.yml` after
  a pull request is merged to `main`. Runtime and data production deployments
  MUST use only `.github/workflows/runtime-release.yml` and
  `.github/workflows/data-release.yml`, respectively. They run automatically,
  and only after a pull request is merged to `main` with the required checks
  passed and the PR steward's approval, and only when the approved contract in
  `docs/DEPLOYMENT.md` is met. Each plane uses a separate main-only
  environment and keyless identity, verifies all five successful checks on the
  exact merged commit, keeps immutable, attested provenance and verifies
  readiness. The data plane applies schema changes only through an automated
  additive-only gate. The Hosting identity remains isolated. For the go-live
  program, the PR steward's review replaces the former independent review. The
  authority is the owner's decision G11 of 2026-09-23 in
  `docs/execution/golive/PLAN.md` section 2.1;
  `docs/execution/RELEASE_AUTHORIZATION.md` keeps its list of what remains
  forbidden. Missing evidence fails closed.
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
