# Keep Drive selection inside intake

Written before implementation on 2026-10-22 UTC (2026-10-21 local).
Task `01a149fc-3649-75c1-a121-11c19de12cb8`; branch
`codex/intake-drive-inline`; baseline `473b48ea93258b9ea9c26b71f152c732087441e4`.

## Correction to the previous acceptance

The user correctly identified that a separate “Choose Drive photos” browser
window does not reproduce the chosen Air import interaction. PR #399 improved
our workspace and real transfer/recovery behavior but retained this pre-existing
popup. Successful transfer into a saved draft did not establish fidelity to the
reference. The prior acceptance should have checked the entire selection path.

The inspected [Air selection screen](https://mobbin.com/screens/93402b73-7eaf-446a-86e2-2c8c0f55ad5d)
keeps source navigation, account, file/folder browsing, selection and import in
one in-app dialog. It does not show our detached Google Picker window.
Google explicitly documents an inline modal and an embedded iframe:
<https://developers.google.com/workspace/drive/picker/guides/web-picker>.
The same guide recommends list mode for `drive.file`, where thumbnails may be
unavailable. Its permission distinction must not be hidden by promising a fully
custom all-Drive browser with a selected-file-only grant.

## Intended behavior

- Connected Drive file selection opens inside the current import workspace;
  no extra browser window or “return to the app” step.
- Actual sign-in/consent may use the provider's secure browser flow. After it
  completes, that window closes and selection resumes in the workspace.
- Use Google's real selected-file Picker with the existing `drive.file` grant.
  Render it inline and use its recommended list mode instead of unavailable
  thumbnail tiles. Existing authorized folder browsing stays in our branded
  browser; no automatic broader grant or provider-original mutation.
- Keep account/source context and a clear return/cancel action. Selection, cancel,
  session expiry, load failure and retry must settle in the workspace, retaining
  earlier selections. Source switching or closing must clean up browser content.
- Returned photos continue through existing verified selection, private review,
  explicit Submit and durable intake progress. No automatic submission.

## Implementation boundaries

1. Separate OAuth popup lifecycle from web Picker presentation. A connected
   account's Choose photos action must not instantiate a popup session. Preserve
   the native system-browser path and old installed-client endpoints.
2. Add a scoped embedded mode to the existing API-hosted Picker page. Bind its
   initiating origin to the authenticated allowed application origin. Permit
   framing only by exact configured app origins, on this page only. Keep OAuth
   pages and the application itself protected against framing. Keep provider
   access tokens within the existing API-origin Picker context; send only small
   lifecycle notifications to the app, never credentials or provider payloads.
3. Present that page inside the existing source pane, with responsive sizing and
   accessible title/loading/cancel/retry behavior. Validate notification origin,
   exact iframe window and current picker identity. Server status remains the
   authority for accepted selection. Do not silently fall back to a new window.
4. Adapt the Picker layout using Google's documented inline integration and
   verify it against the real connected account. If cross-origin iframe behavior
   requires a different documented approach, revise this plan before changing
   credential boundaries; do not disable security headers globally.

## Acceptance and release

- Focused backend tests: origin validation, legacy compatibility, frame policy,
  credential isolation, cancel/error/selection lifecycle and stale/replay guards.
- Focused widget and compiled-browser tests: no popup on connected selection,
  consent popup closes, inline frame lifecycle, wrong-origin/window/session
  rejection, cancel/retry/close/source switch, preserved prior selections.
- Responsive full-workspace evidence and actual signed-in Drive selection on the
  released build, confirming no second window and return to private review.
  Preserve demo originals and the two saved private draft photos; no scientific
  submission is needed for this correction.
- Repository verification, independent exact-head review, protected PR checks,
  merge and all three releases, public web/API SHA verification. No hand deploy,
  permission expansion or required-check bypass. Append actual outcome and any
  remaining native/provider limitations to SESSION_LEARNINGS.md.
