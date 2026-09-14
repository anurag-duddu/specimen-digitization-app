# Completed-work reconciliation — 2026-09-13

User authorized completed-work integration and pruning, excluding active tasks. This document records the reviewed retirement plan; the private final receipt records actual outcomes.

## Preservation and integration

- Main baseline: `4c04a2a1de4ae273afab3e57fab1d411289c7183` (PR32). No open PRs at initial inventory.
- Completed planning documents and missing closeouts are included in this reconciliation. Existing closeout entries remain unchanged; recovered entries are linked in bounded appendices. One private administrator email is redacted in the public recovery copy; original private bytes remain retained.
- Dirty product files match current main, a reverse-applicable patch, or exact historical main blobs. Old initialization, acceptance, runtime and registry-login branch product files also match historical main blobs. Squashed bootstrap branches have matching Git patch IDs.
- The old single-photo experiment and superseded runtime setup drafts are retained privately/in their original directories. They are not new production entrypoints or current approval. Their executable functionality has been superseded by the reviewed application worker/SAM and protected release paths.
- A verified pre-prune Git bundle, original staged/working patches, file hashes and per-worktree snapshots are stored under the private `specimen-reconcile-20260913` rollout-state directory.
- Retiring a linked worktree preserves its entire directory, including ignored evidence, models and environments. Its `.git` pointer is preserved as `.git-retired-worktree-reference`; Git registration and reconciled branch names can then be pruned. No recursive deletion or evidence cleanup is authorized by this plan.

## Active exclusions

- `codex/bounded-release-input-transport` — active owner or declared dependency
- `codex/cohort-budget-admission` — active owner or declared dependency
- `codex/initialize-firebase-placeholder` — active owner or declared dependency
- `codex/reconcile-completed-work-20260913` — integration coordinator/main reference
- `codex/release-data-verification` — active owner or declared dependency
- `codex/review-region-comparison` — active owner or declared dependency
- `codex/worker-parent-deadline` — active owner or declared dependency
- `codex/worker-reading-scheduler` — active owner or declared dependency
- `main` — integration coordinator/main reference

## Inactive worktrees reviewed for retirement

| Branch | Preserved directory |
|---|---|
| `codex/auth-before-api` | `/private/tmp/specimen-auth-before-api-20260909` |
| `codex/bounded-recovery-backup` | `/private/tmp/specimen-bounded-recovery-backup-20260909` |
| `codex/clone-allowance-admission` | `/private/tmp/specimen-clone-allowance-admission-20260909` |
| `codex/first-collection-bootstrap` | `/private/tmp/specimen-first-collection-bootstrap-20260910` |
| `codex/hosting-marker-propagation` | `/private/tmp/specimen-hosting-marker-propagation-20260909` |
| `codex/live-human-review-release` | `/private/tmp/specimen-live-human-review-release-20260909` |
| `codex/magic-link-signin` | `/private/tmp/specimen-magic-link-signin-20260910` |
| `codex/pr21-local-image-qualification` | `/private/tmp/specimen-pr21-local-image-qualification-20260909` |
| `codex/pr21-publication-contract` | `/private/tmp/specimen-pr21-publication-contract-20260909` |
| `codex/pr23-local-image-qualification` | `/private/tmp/specimen-pr23-local-image-qualification-20260910` |
| `codex/release-controls-integration` | `/private/tmp/specimen-release-controls-integration-20260910` |
| `codex/runtime-registry-login` | `/private/tmp/specimen-runtime-registry-login-20260910` |
| `codex/runtime-setup-contract` | `/private/tmp/specimen-runtime-setup-contract-20260909` |
| `codex/live-data-platform` | `/Users/anuragduddu/.codex/worktrees/0cf0/specimen-digitization-app` |
| `codex/live-acceptance` | `/Users/anuragduddu/.codex/worktrees/73c3/specimen-digitization-app` |
| `codex/initialize-missing-database` | `/Users/anuragduddu/.codex/worktrees/7471/specimen-digitization-app` |
| `codex/release-acceptance` | `/Users/anuragduddu/.codex/worktrees/ac0d/specimen-digitization-app` |
| `detached` | `/Users/anuragduddu/.codex/worktrees/c835/specimen-digitization-app` |
| `codex/live-delivery` | `/Users/anuragduddu/.codex/worktrees/f88c/specimen-digitization-app` |
| `codex/live-integration` | `/Users/anuragduddu/.codex/worktrees/live-integration-20260908/specimen-digitization-app` |
| `codex/catalog-safe-diagnostics` | `/Users/anuragduddu/.codex/worktrees/specimen-catalog-diagnostics/specimen-digitization-app` |
| `codex/enterprise-appcheck-fix` | `/Users/anuragduddu/.codex/worktrees/specimen-enterprise-appcheck/specimen-digitization-app` |
| `codex/managed-cloudsql-catalog` | `/Users/anuragduddu/.codex/worktrees/specimen-managed-cloudsql-catalog/specimen-digitization-app` |
| `codex/pilot-cohort-reservations` | `/Users/anuragduddu/.codex/worktrees/specimen-pilot-cohort-reservations/specimen-digitization-app` |
| `codex/pilot-release-completion` | `/Users/anuragduddu/.codex/worktrees/specimen-pilot-release-completion/specimen-digitization-app` |
| `codex/real-model-integration` | `/Users/anuragduddu/code-projects/fieldmuseum/specimen-real-model-integration` |

Additional branches without worktrees are retired only after ancestry or complete product-file equivalence is verified. Full original commits remain recoverable from the private Git bundle.

## Release boundaries

Build/Hosting and runtime candidate CI are green at the baseline; protected data/runtime jobs fail at admission. Current authorized source/packet inputs are stale or absent, the original initialization window expired, and the active DATA task owns a pending combined budget/duration/IAM decision. This reconciliation does not repin private approval, open a new window, reset accounting or weaken those gates. Exactly ten specimens, every region and both readings remain required. Full live compare/correct/save/reopen acceptance is not yet complete.
