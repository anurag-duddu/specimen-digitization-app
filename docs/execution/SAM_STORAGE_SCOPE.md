# SAM application storage scope

The first native SAM execution must use the approved application object prefix
in `specimen-digitization.firebasestorage.app`. The PR21 source read the original
source locator and wrote claim/response objects under `sam3/`, which could not
work with the authorized `application/sha256/` get/create permissions.

SAM now reads the intake-verified application copy at
`application/sha256/<application_source.sha256>` and the exact generation in
`application_source.blob_ref`. The manifest already requires its digest and
size to match the original. The existing size/digest checks still precede the
model call, with no fallback to the original path. The response retains the
original source metadata as provenance.

Create-only claim and response receipts now use
`application/sha256/<manifest_sha256>/sam3/<specimen_id>/`. Mask objects remain
content addressed under `application/sha256/`. Region UUIDs, request binding,
model pins, checkpoint contract, deadlines, and unknown-outcome refusal are
unchanged. A restarted service returns the retained matching response or refuses
an uncertain/conflicting claim without another model call.

This is a correction for the first native execution. Before adopting it, the
coordinator must independently confirm there are no prior native SAM executions
or outstanding claims under the old namespace. This change neither migrates nor
deletes old claims. If any exist, stop for explicit reconciliation; do not use a
new prefix to repeat an unknown effect.

The correction creates no IAM grant and establishes no native readiness. SAM
still needs effective object get/create access within the application prefix,
the exact manifest secret, and worker-only invocation. The read-only GCS cache
mount has a separate unresolved least-privilege qualification: `only-dir`
restricts the mounted view, but does not itself prove an IAM prefix restriction
or that object-get alone permits directory traversal. Do not add broad bucket
listing or alter the mount implementation without reconciling that gate.

The saved PR21 image qualification belongs only to source
`aa7cdc0613fb4887ba5265a5aab29ac9df7eb4d8`, tree
`1cf2a2979b8f27a697c69a7701d84da814f289d9`. A merged successor containing this
correction requires independent source review, required exact-source checks,
fresh image qualification and a same-source data compatibility receipt before
publication. Preserve the previous image evidence; it cannot qualify changed
source. Unchanged data fingerprints permit the existing protected
`data-verify/v1` path after genuine schema readiness, without repeating the
already-issued catalog or native restore solely for this SAM correction.

The new storage fixture denies writes/reads outside the approved prefix and
denies original-source access. It uses different original/application generations,
checks original provenance, and verifies restart/idempotence behavior. It does
not use credentials, cloud storage, model weights or specimen bytes.
