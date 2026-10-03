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

- Production changes happen only through three workflows, and only after a
  pull request is merged to `main` with the required checks passed: Hosting
  through `.github/workflows/ci-cd.yml`, data through
  `.github/workflows/data-release.yml`, and runtime through
  `.github/workflows/runtime-release.yml`. The data and runtime workflows also
  accept a manual run (`workflow_dispatch`) on `main` only; a manual run of the
  Hosting workflow runs the checks and does not deploy. The authority is the
  owner's standing decision G11 of 2026-09-23 in
  `docs/execution/golive/PLAN.md` section 2.1 (data and runtime releases
  deploy automatically on merge, like Hosting), and the owner's messages of
  2026-10-03 in the go-live coordinator session ("Take over, get this live";
  "Yes, get it done. You have my authorization..."), which supersede G11's
  "the PR steward approves" clause. `docs/DEPLOYMENT.md` quotes them and
  describes each workflow.
- The Hosting release deploys the tested web build. The data release
  initializes the database where something is missing, applies additive-only
  schema changes, publishes the schema and connector, creates the indexes in
  the committed index files, publishes the Storage rules and inserts the
  bootstrap rows; every step is idempotent. The runtime release builds the API
  image, pushes it, deploys it by digest and smoke-tests it; the deploy runs
  only after the data release succeeded on the same commit.
- No release ceremony. Do not add receipts, evidence digests, signed intents,
  time-limited access windows, approval packets or admission gates to a
  release. The owner never asked for them and repeated release attempts failed
  on them.
- The data release never drops, deletes or truncates. A destructive schema
  change stops the release and needs the owner.
- One-time owner setup is `scripts/ops/owner_setup.sh` (standing
  least-privilege grants and repository variables; it then starts and follows
  the releases). The owner runs it; an agent runs it only when the owner has
  authorized that run first-hand. Otherwise agents never run a `gcloud` or
  `firebase` command that changes production.
- Never run `firebase deploy`, a Hosting channel deploy, or a `gcloud ... deploy`
  command from a workstation or an agent shell.
- Never deploy SQL Connect schemas, database migrations, Storage rules,
  Functions, Cloud Run services, or model workers through the Hosting workflow.
- Do not add AWS deployment resources or AWS credentials unless the user makes
  a new, explicit architecture decision.
- Do not bypass, weaken, or disable required checks, branch protection, the
  main-only GitHub environments, pinned action SHAs, or the Workload Identity
  Federation conditions to make a release pass.
- Use `scripts/ci/verify.sh` before pushing. Use a pull request. Wait for every
  required check. After merge, wait for the three `main` workflows and verify
  the deployed commit through the public `deployment.json` marker, the API
  `/version` source SHA and the smoke results. A merge or a started workflow is
  not a release; the release is complete when those checks pass.
- Retired ceremony scripts are listed in `scripts/ci/RETIRED.md`. Do not extend
  them.

If a production release is blocked, report the exact failing step and fix
forward through a pull request. Do not substitute a hand deployment.
