# Optional finite-retention recovery backup

The protected data workflow may opt into `recovery.backup_retention`, containing
exactly `expires_at_unix` and `max_chargeable_bytes`. Absence preserves the existing
legacy backup contract. Presence requires a new backup (`backup_id: null`), a
reviewed expiry beyond both the packet and restore-clone deadlines but within 172
hours of packet issuance, and at most 10 GiB. No actual lifetime or operational admission is selected
by this document. The signed plan/independent release review binds both limits.

The new path uses the existing SQL Admin v1beta4 origin and
`POST projects/specimen-digitization/backups`. It supplies only the exact source
instance, existing cohort description, location and an absolute `expiryTime`.
`Backup.name` and `maxChargeableBytes` are output-only: neither is sent. Resource
names and the legacy backupRun ID must come from the one original operation and
successful native readback; no list-based adoption or second creation is allowed.

The method maps to existing `cloudsql.backupRuns.create`; new-resource get/list map
to existing backupRuns get/list permissions. The existing source backupRun is
cross-checked before its ID is passed to unchanged restoreBackup. No IAM grant,
new vault/plan, automatic-backup setting, backup deletion, or legacy-body TTL field
is introduced. Backup creation is still only within the admitted main-push data
workflow. The source settings and every preexisting backup remain unchanged.

A durable intent precedes the only POST. Native operation identity, target,
completion, source and cohort association, original backupRun mapping, exact
expiry and maximum chargeable-byte readback must qualify before clone creation or
restore. Unknown or over-limit outcomes retain evidence and stop without retry or
fallback. Finite-retention proof travels in the existing recovery receipt, bound
to the same restore backup ID and signed plan; missing proof blocks initialization.

`maxChargeableBytes` is a readback limit, not a server-side input cap. Admission must
reserve conservatively before creation using the observed source disk bound;
post-creation failure does not erase incurred liability. An expiry observation is
not evidence that billing stopped or that provider deletion completed at expiry.

The REST method and discovery schema explicitly support on-demand creation and
expiry inputs. The general standard-backup guide still says on-demand backups are
retained indefinitely. Therefore source compatibility is documented, while actual
provider enforcement remains Not confirmed until the protected native readback.
The exact operation/resource-mapping shapes are checked conservatively; unexpected
shapes stop with the original intent retained. No native behavior was tested during
authoring.

Primary references checked 2026-09-09:

- [CreateBackup](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1/Backups/CreateBackup)
- [Backup fields](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1/Backups)
- [Cloud SQL IAM method mapping](https://docs.cloud.google.com/sql/docs/postgres/iam-permissions?hl=en)
- [Legacy BackupRun fields](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/backupRuns)
- [Standard backup retention guide](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backup-options)

The retained SQL Admin v1beta4 discovery confirms `backups.createBackup` uses
`sql/v1beta4/{+parent}/backups`, returns `Operation`, and has `BackupContext.name`
plus `backupId`; `Backup.backupRun` is the output mapping used for IAM validation.
No production request, credential, backup ID, size observation or expiry was
fabricated for this design.
