# Repository instructions

These instructions apply to every branch, worktree, and Codex session in this
repository.

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
