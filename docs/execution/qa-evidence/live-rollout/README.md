# Live rollout evidence inventory

All committed data here is sanitized, authored synthetic evidence. The private
ten-specimen manifest, inventory, user identities and source images stay outside
Git. No cloud specimen was downloaded or inferred on by this QA task.

| Artifact | Candidate | Classification | Result |
|---|---|---|---|
| `baseline-local.md` | `a53f855e963b457c3ee2065f387609a193bb6f32` | Independently executed ASGI TestClient / SQLite / LocalBlobs / injected membership | 24 checks passed; zero cloud images or paid calls |
| `experiments.md` | Same baseline | QA harness development record | Preserves initial failed assertion and correction |
| `data-artifact-review.md` | Owner source not yet frozen | Independent consistency check of owner local synthetic artifact | 27-table/26,315-row and index/query evidence internally agrees; not reproduced by QA |

These artifacts are not live Firebase, App Check, SQL Connect, Storage rules,
SAM 3, real-provider or browser evidence. The product candidate SHA identifies
the unmodified baseline product; QA scripts were uncommitted additions during
execution and are delivered with this PR. Future runs must record both the
product candidate and QA harness revision/hash.

Full launch ledger and cases: `docs/execution/LIVE_QA.md`. Commands and report
contract: `scripts/qa/live/README.md`.
