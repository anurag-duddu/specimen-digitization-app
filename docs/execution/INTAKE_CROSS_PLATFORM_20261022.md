# Cross-platform bulk photo intake

Written before implementation, October 22, 2026 (America/Chicago).
Task `01a149fc-3649-75c1-a121-11c19de12cb8`; branch
`codex/intake-cross-platform`; baseline main
`084b387f950cf2c255c04849f08998cb84d1096e`.

## Product contract

Deliver the same Add photos → review → explicit Submit → intake progress →
specimen workflow on the repository's shipped targets: iOS, Android, and web
(phone, tablet, desktop). Native Windows/macOS/Linux hosts are not present and
are not implied by responsive desktop-web support.

Preserve the 500-photo limit, one specimen per accepted photo, private durable
drafts, server-side provider credentials, collection isolation, sensitivity,
idempotent submission, and the separate specimen Queue. Preserve the existing
Gmail demo draft and provider originals during acceptance.

## Findings and chosen approach

1. Bulk file selection, replacement and submitted-item reselection omit the
   iOS uniform type identifiers required by file_selector_ios. Share one image
   filter across all entry points without widening backend format/size limits.
2. Native draft persistence ignores a false SharedPreferences write result.
   Admission also publishes a new item before confirming its recovery metadata.
   Require a successful persistence acknowledgement; on failure retain the
   capture for retry and roll back newly published local admission so retries
   cannot duplicate a photo. Exercise real file-backed restart behavior.
3. Native provider authorization launches an external browser and relies on
   app_links plus a ten-minute timeout. Investigate and implement a supported
   system authentication surface with completion, cancellation, expiry, and
   stale callback handling. Keep iOS 15 compatibility. Verify chosen platform
   library/native APIs before changing the adapter; keep secrets server-side.
4. Google explicitly prohibits its native Picker inside an embedded WebView.
   Preserve the supported `trigger_onepick` / `drive.file` path on native and
   inline SDK Picker on web. Use an automatically returning system auth sheet
   or browser tab where supported. Existing explicitly authorized folder browsing
   and Dropbox remain in the shared workspace. Do not silently request broader
   Drive scopes to mimic a custom selected-file browser.
5. Source polling currently treats a visible but inactive app as background,
   unlike the batch controller. Align lifecycle handling so visible web/native
   UI can reconcile while unfocused, and refresh on resume. Guard account,
   source, generation and route ownership throughout.

Google reference (reviewed today):
https://developers.google.com/workspace/drive/picker/guides/overview

### Native transport decision, before implementation

Use a small first-party Flutter method channel: ASWebAuthenticationSession on
iOS 15+, AndroidX Auth Tab with supported browser fallback on Android. Expose
completion, user dismissal, explicit cancellation and launch failure. Validate
the exact callback scheme/host/path and initiating state in Dart before sending
it to the authenticated server exchange. Close or expiry must settle the pending
future immediately and ignore late callbacks. Keep provider payloads out of logs.

The url_launcher in-app browser mode lacks a complete cancellation/result
contract; flutter_web_auth_2 5.x documents an iOS 17.4 floor. Neither justifies
breaking the existing iOS 15 target. Google requires native selection through
its OAuth-triggered Picker, so native file selection still uses a secure system
surface; it is not an embedded WebView or a silent broader Drive permission.

If the OS terminates the app during authorization, reconnect with a fresh proof;
do not pretend an in-memory proof survived. The saved draft must survive. Store
only scoped non-secret selection identifiers where needed for already-authorized
validation recovery, and never persist callback codes or OAuth proofs in prefs.

## Implementation order and ownership

- Integrator owns this plan, lifecycle reconciliation, cross-platform acceptance,
  independent review, repository verification and release coordination.
- Capture agent owns shared file filters, durable admission failure handling,
  permission error classification and focused recovery/capture tests.
- Connector agent owns native provider transport design/implementation and its
  focused cancellation/callback tests after the transport decision is recorded.
- Independent reviewer checks the integrated exact head before merge.

Use existing specimen_ui components and shared controllers. Avoid introducing
platform-specific copies of review/submission. A suspended or terminated client
cannot promise to transfer local bytes; show pending transfers honestly, restore
durable local files, and let accepted server work continue independently.

## Acceptance

- Meaningful regressions for iOS filter dispatch; failed/throwing metadata saves;
  retry without duplicate admission; 30 consecutive durable captures and restart;
  source inactive/background/resume; native callback identity/cancellation/expiry.
- Existing bulk 100/500, sensitivity, selection, draft, submission and progress
  contracts; relevant visual/widget/browser tests and native compilation.
- Inspect real current native builds on available physical iPhone and Android,
  preserving package identity and data. Test real provider return/cancel/retry,
  camera permission/capture/review, recovery, and submit/progress only in the
  dedicated test collection with a separate test batch. Never relabel emulator,
  fixture, compile or personal-account results as physical/institutional proof.
- Run scripts/ci/verify.sh before push; independent exact-head review and all
  required PR checks; merge and protected Hosting/Data/Runtime workflows only.
  Verify public web/API commit markers. Native installation and device acceptance
  are separate from web/backend deployment.
- Append actual results, blockers and unresolved device/provider dependencies to
  docs/SESSION_LEARNINGS.md. Do not claim cross-platform completion while a
  required target still fails or lacks live evidence.
