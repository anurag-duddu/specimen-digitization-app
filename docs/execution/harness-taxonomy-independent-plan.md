# Independent taxonomy implementation plan

Date: 2026-10-07. Task: `/root/taxonomy`, independent six-specialist stream.
Worktree: `/Users/anuragduddu/.codex/worktrees/harness-taxonomy-independent/specimen-digitization-app`.
Branch: `codex/harness-taxonomy-independent`.
Baseline: remote main `7890de551c75fe3b06836c7fb224f85dd2a2423a`, verified with
`git ls-remote origin refs/heads/main` before managed worktree creation.

1. Reproduce the G20 one-confirmed-reader plus exact captured no-match gap on
   this baseline, without calling a provider.
2. Inspect and reuse completed taxonomy commit
   `8620c41eb2cab7e1b6038d3865713e0d527efed2` from the separate existing owner.
   Preserve that owner's worktree and branch. Review the source helpers,
   authority, assertion alignment, stop policy and acceptance closure.
3. Add focused independent regressions and repair any concrete defects found
   in support-source strategy, evidence-bound family/order context, genus-only
   handling, incomplete research and interrupted capture/replay.
4. Run domain offline checks in this worktree. Adopt the independent common
   package/capability base when provided by the integrator; use truthful final
   qualification pins after composition.
5. Append actual evidence and follow-ups to `docs/SESSION_LEARNINGS.md`, commit
   the reviewed source, and hand it to our independent integrator. Full
   verification, push, protected review/merge and CI/CD are integrator-owned.

Boundaries: GBIF decides; GNV/COL support. BugGuide is not admitted. A bare
`sp.30` supplies no genus. Preserve raw/organiser alternatives and human locks.
Unknown-send holds and exact source identity cannot be retried around. No paid
canary, direct data write, production mutation or Lane P dependency is included.

Dosu credit exhaustion is injected current context. The same monthly cap is
not retried, no credentials or billing change is made, and no knowledge receipt
exists in this task.

Shared hunks from the reusable commit: taxonomy-only assertion/reconciliation
in `evidence.py`, GBIF parameters/no-match candidates in `sources.py`, query
outage identity/stop feedback in `agents.py`, taxonomy prompt v7, and the
`accepted_output.py` validator closure. Root owns general capabilities,
recovery, dependencies and final combined qualification.

## Implemented and verified

- Baseline G20 regression failed before source reuse at the expected independent
  assertion settlement fence. Completed commit `8620c41eb` was reused as
  `4b3d6253d`; its original worktree stayed read-only.
- Independent regressions exposed six failures: capitalized explicit `Taxon:`
  keys could skip research/context and fail a valid raw producer, and a
  misfiled `taxon:` span inside a city line could falsely request taxonomy work.
  The repair uses one taxonomy-only scientific-name projection across the
  assertion validator, exact negative binding, query context and stop feedback.
  Raw literals, original observations and alternative readings stay unchanged.
- GBIF query lineage remains same-label, exact whole-line and unanimous. The
  API's family/order/checklist parameters were rechecked in official GBIF
  [taxonomy interpretation documentation](https://techdocs.gbif.org/en/data-processing/taxonomy-interpretation).
  This check supports the adapter contract; no live specimen query was run.
- Common upgrade `3288ec80` was adopted locally as `1f1ab2a3e`. Actual installed
  AI-slim/Evals/Graph 2.54.0 and Harness 0.54.0 were verified. 151 focused tests
  passed under that runtime, including taxonomy authority, exact input/proof
  reconciliation, context, stop feedback, interrupted capture and prompt pins.
- Before the small independent delta, 69 reused focused tests passed under the
  original 2.51.0/0.36.0 runtime, including automatic offline native publication
  without Save. That predecessor evidence is distinct from the new source and
  target-runtime native composition, which the integrator's combined verifier
  still must exercise.
- The local v4 validator closure is
  `67c3902b9b882a7b3df4f423dc1412019c47d738fbdfe84e2d8aff295072a7fc`.
  Root must recompute it after final composed shared-file edits while retaining
  the historical v1-v3 pairs and frozen prompt bytes.
