# Protected release source successor, 2026-10-01

> Historical snapshot. The protected-release packet, initializer and
> `owner_grants.py` paths described below were retired and deleted on
> 2026-10-12. Current releases and owner setup are defined by
> `docs/DEPLOYMENT.md`, the three release workflows and
> `scripts/ops/owner_setup.sh`; do not follow this snapshot as a runbook.

This is an authored source closure for integration and independent review. No
tests, compiler, native connector, cloud mutation, deployment or paid call ran
in this author session. The root integrator remains the only candidate writer
and release owner.

The closure selects the finite data PR chain #112 → #115 → #147 → #148 →
#161 → #162 → #163 → #176 → #177 → #194 → #195, runtime workflow #101,
schema hardening #219, standing-grant report #119 and bounded setup-window
#123. The final data workflow supplies initialization, published creation
intent, owned disposal, migration, additive apply, backup/first restore,
hierarchy bootstrap and worker membership. Selecting #115 alone would retain
its deliberately unimplemented initialization path.

The combined GitHub gate waits for exact successful CI/CD on every plane.
Runtime additionally waits for the exact commit's successful data release and
binds its run and attempt into the record. Data jobs never wait for their own
workflow. Runtime waits at most 5,400 seconds; data at most 3,300. Later effects
re-admit the exact record and all observations before credentials/mutations.

The #219 source parser keeps its provenance, membership, transaction, markup,
directory, no-default and closed unique-swap protections. The final data
chain's SQL catalog adapter is added to that parser. The obsolete constant
`NAMED_RELAXATIONS` is replaced with the strict merged-contract reader.
`committed_source` now uses the same checked directory reader in initialization
and apply. The physical unique-swap hook reads the valid whole-table six-column
NOT-NULL unique before apply, and rereads it in the native session after backup
and first restore before executing the one committed old-index drop. It
verifies the old index is absent and the wider unique still exists. An unknown
readback, refusal, drop or acknowledgement blocks the release.

The newer main runtime deploy, settings policy, publication deadline, SQL
catalog, local Postgres runners, rollback/lost-acknowledgement controls and
application code are preserved. No branch tree, secret baseline, foreign
SESSION log or old policy document is restored wholesale. The three inherited
test-file changes retire assertions for obsolete envelope workflow steps;
their native claim, encryption and disposal controls remain, and the new data
workflow controls cover the current signed intent/encrypted artifact paths.
The legacy data template fixtures mentioned by this snapshot were never
consumed by the G11 workflows and have since been deleted with the retired
initializer and packet tooling.

Only the API readiness generation is pinned, from root's authenticated receipt
`integration/live-readiness-object-20261001.json` (SHA-256
`e137f2659f4011ffac63ce574394626b7121092423685229236a69383a70ea95`).
Root verified generation `1790562271708431`, 50 bytes, matching the committed
object digest. Worker drain arguments and SAM server settings remain pending:
the current main worker has no `--drain`, and its legacy launch policy and SAM
pilot expiry cannot be replaced by invented flags.

At the time of this snapshot, root still had to qualify the composed source and
fresh required CI and reconcile standing IAM/read permissions. The former
`owner_grants.py plan` and temporary setup window no longer exist; the active
least-privilege setup is the idempotent `scripts/ops/owner_setup.sh` described
by `docs/DEPLOYMENT.md`.
Initialization/bootstrap/first restore require their actual bounded owner
window and retained approved artifact. Bootstrap needs only the three named
`data-production` secrets documented in RELEASE 4.5, scoped to the deployment
step and removed from child environments; no retired release packet is needed.
First-created runtime resources may need owner invoker grants followed by one
qualified rerun. Secret-version readback, source registry/collection bindings,
actual worker/SAM CLI closure and currently missing live import/accounting
authority remain explicit gates. Root's App Check enable/read receipt is a
separate current fact; this successor neither re-enables nor registers it.

The historical suggested qualification used release packet, initializer,
owner-grant and template tests that have since been retired. Current
qualification is `scripts/ci/verify.sh` plus the protected workflow checks
documented in `docs/DEPLOYMENT.md`.
Root owns the sole SDK/native/full-test slot and any later protected release.
Static release or compiled SQL still cannot qualify the real ten specimens,
native authority or cumulative USD 30 headroom (G9, raised from USD 25 on 2026-10-17).

The retired read-only owner plan used the G9 USD 25 cumulative project billing
alert, covering infrastructure and models under the 2026-09-23 go-live amendment.
G30 retains a production model allowance (USD 28 since 2026-10-17, raised from
USD 5, then USD 15 on 2026-10-09 and USD 16 on 2026-10-16) and a separate USD 5
acceptance lab allowance. Historical lab calls do not debit a fabricated production
predecessor. G11 retires release cost ledgers and release reservations; G30's
atomic per-call reservations remain. The alert creates no spending authority,
headroom, import proof or increase to either model allowance.


Release v3 requires an independent old-index identity read on the same SQL connection before the single fixed drop. A present old name must be the public SourceAsset btree unique over precisely the original three ordered physical columns, valid/ready/live, expression/predicate/include-free, NOT NULL, and not constraint-backed. A wrong or unreadable catalog stops with no DROP or success certificate. An already absent old index skips DROP and still rechecks the new six-column unique. The generated old-index DDL artifact `dataconnect/sql/source-asset-old-index-qualified-ddl.sql` is intentionally absent until genuine source-specific generated DDL is recovered and reviewed; a present old index therefore remains HOLD. The scripted native transport controls carry a synthetic DDL fixture only, never admission authority or live physical proof. Native SQL qualification remains UNRUN.
