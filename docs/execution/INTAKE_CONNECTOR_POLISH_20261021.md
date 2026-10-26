# Connector and intake polish — implementation plan

Written 2026-10-21 before implementation. Task: `01a149fc-3649-75c1-a121-11c19de12cb8`.
Branch: `codex/intake-connector-polish`; baseline: `c9040b83`.

## Outcome

A fast, coherent import workspace in the existing Specimen design system. Every
source returns to the same private photo review, followed by explicit **Submit**
and intake progress. Connection, browsing, checking and adding are distinct,
understandable states. This work includes the real waiting paths, account
recovery and partial failures, not only the initial Connect screen.

## Research and chosen direction

**Primary reference: Air's cloud asset import workspace.** Its use case is
closest to ours: choose a cloud source, connect an account, browse folders,
select a batch, and return to an image library. Retain that spatial structure
throughout the journey rather than borrowing a different layout for each source.

Inspected Mobbin references:

| Reference | Screens actually inspected | Decision |
| --- | --- | --- |
| [Air: Google Drive connection](https://mobbin.com/flows/b64a77e8-e8f2-41cb-be6b-0d02a35358a0) | In-context Connect, native provider consent, connected root browser | Primary connection structure: source navigation, one Connect action, account in header after connection. |
| [Air: folder import](https://mobbin.com/flows/f49a9de4-df97-4dd7-9e98-5711b7212313) | Entry menu, loading rows, populated folder browser, selected folder, completed import | Primary browsing structure: stable header, large file area, named breadcrumbs, fixed selection footer. Selected state inspected at full resolution: [screen](https://mobbin.com/screens/93402b73-7eaf-446a-86e2-2c8c0f55ad5d). |
| [Air: file upload](https://mobbin.com/flows/e647a567-8f3c-44bf-aaab-1d38f0ed7914) | Add menu, duplicate dialog, image library | Keep image-first return; preserve our existing duplicate protection instead of Air's version/duplicate choices. |
| [Claude: Google Drive attachment](https://mobbin.com/flows/16a618d7-b17b-4d38-b72d-3c95790cfbb1) | Compact source menu, attached file, fetch failure | Supports short connection setup and contextual recovery; single attachments are not the bulk layout. |
| [Claude: connector setup](https://mobbin.com/flows/97688333-b64c-4242-8a8b-852e3e50ce33) | Source menu, connector detail, returned menu with success | Connect once, then return to task. No repeated permissions explanation. |
| [ChatGPT: connector](https://mobbin.com/screens/793f39a7-9735-4c45-ae4e-a7f20229580f) | Compact GitHub connect sheet and native authorization | Native consent remains provider-owned. No custom OAuth imitation. |
| [Attio: integration](https://mobbin.com/flows/71af99f1-da65-40d7-9ded-20a2ebbcc6c0) | Catalog, detail, connected workspace | Useful secondary account-management pattern, not the main import workspace. |
| [Canva: Drive import](https://mobbin.com/flows/b3debed1-cb5a-434e-8d32-afca776d5aab) | Source icons, Connect in place, searchable asset browser | Supports staying in context; narrow editor sidebar is unsuitable for 500 photos. |
| [Dropbox: upload](https://mobbin.com/flows/1118c3b1-c64d-4ff5-a3ad-6f001192fa76) | Workspace, folder-location dialog, returned file list | Secondary reference for breadcrumbs and a stable footer. |
| [Dropbox iOS: adding content](https://mobbin.com/flows/0f9c59df-2862-42ba-94fb-91b1c61e64b7) | Entry, selected-photo tray/count with folder choice and Upload, returned list | Mobile adaptation: count and next action stay visible while content scrolls. |
| [Frame.io: adding assets](https://mobbin.com/flows/3bcf9fda-50fa-443e-8c7a-7d94be4e5064) | Empty workspace, Add menu, preparing thumbnails | Supports our image-first batch review and per-item preparation status. |

These are observed design references, not integration acceptance evidence.
Failure and permission designs below come from our product requirements and
current contracts; Mobbin does not establish their behavior.

## Current app comparison

Live read-only audit used the signed-in Gmail account and Intake E2E collection.
Drive shows a compact connected-account dialog and Choose photos. Dropbox shows
folders and a short checkbox list with repeated Preview buttons. Storage shows
the real no-registered-locations empty state. Links shows a small text field and
Review links. No photos were imported or submitted during this audit.

Source audit at the baseline:

- `intake_source_picker.dart`: one busy flag and generic Loading source across
  different operations; browsing height capped at 160–360 px; unnamed parent
  navigation; no select-all or filter. Picker selections are not selected in the
  app, so users must select the same photos again.
- `intake_selection.py`: five metadata checks per advance, driven by a
  three-second client poll. For 500 items this imposes about five minutes of
  cadence alone. This is a source-derived lower bound, not a live benchmark.
- `bulk_intake_controller.dart`: one admission POST per selected source photo,
  serial preparation before first local item becomes visible, duplicate summary
  polling and cached failed preview futures.
- `bulk_intake_screen.dart`: progress reloads all pages periodically even for
  terminal batches; Intake stays mounted when another workspace branch is shown.
- Registered storage relists its inventory to serve later pages. Recursive
  folder selection is synchronous. These paths need bounded behavior and honest
  counts; performance changes must preserve sensitivity and complete-list checks.

## Screen-by-screen implementation

Use existing Geist typography, monochrome actions, Phosphor icons, spacing,
focus rings, radii and status tokens from `specimen_ui`. Provider identity is
a small source label/icon; Air's blue brand and visual assets are not copied.

1. **Choose a source / disconnected:** a shared, bounded import workspace with
   source navigation (Drive, Dropbox, Storage, Links), title and close action.
   Desktop has a compact source rail; compact windows use a labeled source
   selector. Connect shows one short explanation and one action.
2. **Connecting / account choice:** keep the workspace geometry stable. Name the
   phase, preserve Cancel/close, show a connected account in the header.
   Multiple accounts require explicit choice; account management remains in the
   overflow. Preserve selections when reopening or reconnecting the same account.
3. **Drive Picker:** keep Google's actual Picker for `drive.file`. Returned
   eligible files are already selected. Show checking N of M and partial failures,
   then **Add N photos**. Optional folder authorization remains explicit.
4. **Dropbox / authorized Drive folders / storage:** named breadcrumbs, a clearly
   scoped filter for loaded files, a virtualized compact file list, failure details
   where needed, select visible eligible photos / clear, and a persistent selection
   footer. Folders are navigable; selecting a folder's photos and subfolders stays
   explicit. Keep 500 cap and incomplete listing warnings.
5. **Links:** one multiline entry with concise supported-link hint, provider
   account controls only when needed, then incremental checked results in the
   same file region. Explicit entered links yield selected eligible items; failed
   links remain visible and do not erase successes.
6. **Preview:** show an explicit requested preview without auto-downloading every
   original. Distinguish loading, unavailable and Retry. Keep bounded cache and
   decode limits; no 500 full-resolution thumbnails in memory.
7. **Adding / batch review:** keep Add separate from Submit. Show adding progress
   immediately; preserve acknowledged items on failure. Return to the image-first
   private batch grid. Local preparation publishes incremental progress and the
   first ready item instead of waiting for the last file.
8. **Submission / history:** retain fixed totals and per-photo states, meaningful
   waiting/retry labels, successful specimen links and cancellation semantics.
   Only the visible active view polls. Terminal and hidden views stop periodic
   reads; returning refreshes authoritatively. Transfers and server workers keep
   running independently of UI polling.
9. **Failure states:** inline, actionable problem with retained context and
   selection. Retry, reconnect, change account, file access or alternate source
   follow the confirmed error. Administrator help is a disclosure only after an
   actual institutional denial or a confirmed application-configuration failure.
   Never invent approval pending.

## Performance implementation and guardrails

- Preserve explicit Picker selection intent. Use bounded server verification
  work and durable checkpoints so useful progress is not limited by a
  five-files-per-three-second UI timer. Keep leases, CAS, account binding,
  backoff and lost-response reconciliation. Prefer the existing intake worker
  if it can safely own continuation; do not invent a second job system.
- Add a backwards-compatible bulk source-admission contract with bounded chunks
  (target 50, at most 10 admission calls for 500). Stable IDs and exact item
  reconciliation survive partial success/lost acknowledgements. Single-item
  endpoints remain compatible. Do not parallelize competing draft CAS writes.
- Consolidate progress reconciliation, guard overlapping refreshes, stop terminal
  and background reads, and load only needed pages. No optimistic scientific
  completion or fabricated percentage.
- Publish local preparation incrementally, invalidate failed preview futures on
  retry, and avoid serial account discovery where independent reads can safely
  run together.
- Measure provider/storage pagination and recursive selection before selecting
  any cache or cursor implementation. Retain explicit incomplete/over-limit
  failure rather than silently truncating. A change that needs new persistent
  schema or widened access must be reported separately, not hidden in UI work.
- Keep OAuth origins/state/PKCE and scopes, source-original immutability, source
  policy/sensitivity, collection/owner isolation, SSRF and decoding limits,
  idempotent Submit and worker budget protections unchanged.
- Enable bulk admission only on its explicit server capability flag. Explicit
  selection retry probes POST and falls back to legacy GET only on 404/405, so
  cached capabilities cannot strand work across runtime upgrades. Retain legacy
  idempotent single-item/status paths during independent client and runtime
  rollout. Recovery receipts survive uncertain replies and live drafts,
  then are pruned after authoritative submission/discard. Confirmed removed
  photos receive a fresh admission identity when explicitly selected again.

### Measured scope decision during implementation

Controlled SQLite/API measurements (no provider network) reduced 10/100/500
source admissions from 10/100/500 POSTs to 1/2/10; observed local elapsed times
were .037/.341/1.530 seconds before and .014/.102/.445 after. These are request
overhead evidence, not live-provider speed claims. A mocked storage inventory
showed five full listings/2,500 metadata visits for 500 items over five pages.
Changing that pagination safely requires a snapshot/cursor contract; resumable
recursive scans likewise need a separate durable scan contract. Both remain
unchanged in this release, with existing complete-list/cap checks preserved.

## Delivery order and ownership

A. Root: shared import workspace component and connector screen composition,
   source selection behavior, loading/error/preview states and responsive tests.
B. Connections lead: bounded backend verification/admission and focused contract
   tests; coordinate endpoint shapes before client changes.
C. Integration lead: controller admission/preparation/reconciliation and progress
   screen improvements with focused tests, after endpoint agreement.
D. Independent reviewer: exact final diff, failure contracts, layout evidence and
   release readiness. Root integrates fixes and runs repository verification.

Workstreams B/C may run in parallel with A only after this written plan exists.
They must coordinate shared contracts and avoid overlapping files.

## Acceptance and release

- Test Connect, account choice, loading, selected, empty, partial failure,
  reconnect, expired/revoked access, over-500, preview failure and retry.
- 10/100/500-item deterministic fixtures: selection retained without repeated
  clicks; bounded requests; exact counts; no lost acknowledged items or duplicate
  specimens. Record timings as controlled results, separately from real-provider
  timings.
- Verify zero periodic terminal/hidden-view requests over 60 seconds of test time,
  no overlapping refresh, and one authoritative refresh on resume.
- Phone/tablet/desktop layouts, 200% text, long names, keyboard/focus and
  accessible labels. Inspect rendered full-shell screen evidence in light/dark;
  component tests alone do not establish visual acceptance.
- Real Gmail Drive and Dropbox smoke after release: connect/status, browse,
  selection/preview and return-to-review in the designated E2E collection.
  Preserve the user's demo content. No unscoped Send/drain or paid scientific
  reprocessing for this polish. Any unavailable device/institutional acceptance
  remains explicitly Not confirmed.
- Run focused Python/Flutter tests, analysis, repository-required
  `scripts/ci/verify.sh`, independent review, then reviewed PR with all required
  checks. Release only through the existing protected main workflows and verify
  Hosting marker, API version and smoke results at the merged SHA.
- Append actual outcome/evidence/follow-ups to `docs/SESSION_LEARNINGS.md`
  before merge/handoff. No change to provider permissions or production
  configuration is planned.
