# Specimen Digitization rebuild smoke test

Date: 2026-09-14
Branch: main (worktree frontend-design-dev-2580c8), head at time of test.
Environment: synthetic API at http://127.0.0.1:8010 (one fixture specimen, `synthetic-label.png`, cleared), Flutter web debug build at http://localhost:3000, Android debug build on `Medium_Phone_API_36` emulator (`emulator-5554`).
Sign-in: reviewer@fieldmuseum.org / fixture token, used on both platforms.

No source was edited. This report is a point-in-time record of what the running debug builds actually did under direct interaction.

## Method notes (read before the tables)

- **Web canvas is not directly clickable/scrollable by this harness.** Plain synthetic mouse clicks and mouse-wheel scrolls dispatched at real screen coordinates did not register anywhere on the Flutter canvas (confirmed by testing a known, working "Zoom in" button both via coordinate click, which failed, and via its semantics DOM node's `.click()`, which worked). All web interaction below therefore went through the accessibility (semantics) tree: click the hidden `flt-semantics-placeholder`, then either focus the real `<input>` and use the `type` action for text, or call `.click()` on `role="button"`/`role="radio"` semantics nodes. Scrolling used direct `scrollTop`/`scrollLeft` writes on the semantics scrollable `<div>`.
- **The Queue screen's semantics tree is essentially empty.** After sign-in, the only semantics nodes on the whole Queue screen were the two app-bar icon buttons ("Refresh collection", "Help and shortcuts"). The collection picker, search box, status filter chips, the Filters button, the nav rail (Queue/Intake/Sign out), and the specimen row itself have **no semantics nodes at all** — confirmed by walking every `flt-semantics` element and by role-counting (`button`, `radio`, `checkbox`, `group`, `img` — zero for any queue-sidebar control). Because of this, the prescribed "click the row via its semantics node" technique does not work on this screen: there is no node to click. The row also did not respond to a real, correctly-scaled mouse click or to a manually dispatched trusted `PointerEvent`/`MouseEvent` sequence at its exact canvas coordinates.
- **Workaround used to reach the record and to open Filters:** the app's own route builder (`AppRoutes.specimenOf`, `apps/specimen_digitization/lib/src/app/routes.dart`) was used to construct the workbench URL by hand (`/c/<org>%2F<collection>/queue/<specimenId>`), then `window.location.hash` was set and a `popstate` event dispatched. This is not something an end user or a screen-reader/keyboard user can do — it stands in for the broken row tap only so the rest of the smoke test could proceed. **The Filters sheet could not be opened at all**, for the same reason (its trigger lives in the same non-semantic, non-clickable sidebar) — it is reported as not testable, not as passing.
- Android touch input (`adb shell input tap/swipe`) is real, native touch — no harness caveat applies there. Coordinates were computed from the PNG's native pixel size, not the scaled preview.
- `flutter run` in debug/DDC mode is slower to paint than a release build; some "goes blank for ~1-2s then paints" findings below are likely worse than a profile/release build would show, and are flagged as such.

---

## Part A — Web

### Sign-in — 1440x900, 1024x768, 390x844

| Width | What is visible | Defect |
|---|---|---|
| 1440x900 | Centered "Specimen Digitization" card, "Test data access" notice with a "Why" disclosure, Email address + Fixture token fields (token has a show/hide eye icon), green "Sign in" button. Dark theme. | None. Console clean. |
| 1024x768 | Same layout, still centered, not stretched full-width. | None. |
| 390x844 | Same content, single column, no truncation. | None. |

Filling the form and submitting worked correctly at all three widths once routed through semantics (see Method notes) — sign-in itself is not blocked for a real user; the "clicks don't register" limitation is a property of this browser-automation harness, not the field/button widgets.

### Queue — 1440x900, 1024x768, 390x844

| Width | What is visible | Defect |
|---|---|---|
| 1440x900 | Left rail: collection picker "Insects", Queue/Intake nav, Sign out. Center: "Queue" header, search box, status chips, Filters button, one record row (`synthetic-label.png`, Cleared, Not measured, Not calibrated, 6h). Right: empty "No record open" pane (3-pane desktop layout). | **Critical — the entire Queue sidebar has no accessibility semantics and the record row is not operable by mouse click.** See Method notes. This blocks keyboard/screen-reader users entirely and blocks the one interaction (open a record) the screen exists for. |
| 1024x768 | Two-pane: nav rail + full-width Queue list (no third pane at this width). Top bar now shows "Authorized collection: Insects", refresh icon, "Test reviewer" account chip, help icon — a different app-bar arrangement than 1440's. All 6 status chips (All/Needs review/Cleared/Deferred/Blocked/Processing) fit on one row without scrolling. | Same semantics/click gap as above. |
| 390x844 | Bottom tab bar (Queue/Intake) replaces the side rail. Status chip row is a **horizontally-scrollable** strip cut off after "Cleared" with a partial "D" showing at the edge — confirmed via `scrollWidth`/`clientWidth` to be intentionally scrollable, not clipped content. No visible affordance (fade/arrow) hints that it scrolls. | Minor: no scroll affordance on the chip row (low confidence this is worth fixing, flagging for completeness). |

### Workbench — top, then scrolled — 1440x900, 1024x768, 390x844

Opened via the manual URL workaround (see Method notes), specimen `4e99dab8-9c35-56f0-8e29-fc12d38f1940`.

| Width | Top | Scrolled | Defect |
|---|---|---|---|
| 1440x900 | Header "synthetic-label.png" + id, copy/refresh/keyboard icons. "Source photograph" panel with the label image, zoom/rotate/fit controls, "Whole image"/"Label 1" chips, "Correct label regions" link. "Source details": Cleared, Version 21, "Nothing outstanding. Approval is available." Readings/Fields/History segmented control. Confirm label coverage / Approve record buttons. | Scrolling the evidence pane (`scrollTop`) kept the **source photograph pinned/visible** at the top while the reading text (`fmnh_ins_number: FMNH-INS 1001`, etc.) scrolled underneath — this is the intended split-pane behavior and it works. | Switching segments (Readings→Fields) made the source photograph go **solid black for roughly 1-2 seconds** before repainting with the image again. Reproducible on every segment switch. Likely worse than release build but still a visible flash a reviewer would notice. |
| 1024x768 | Below the "large" breakpoint the workbench becomes a **pushed, full-width screen** with an explicit "← Back to queue" link (not a 3rd pane). Same content as above otherwise. | Same pin-on-scroll behavior, works correctly. | "Back to queue" link (which does have proper semantics at this width) correctly returns to the Queue and changes the URL back to `.../queue`. Confirmed clean, no state leakage. |
| 390x844 | Same as 1024 but single column and tighter spacing. On first paint after navigating here, the photograph area was **blank/black for ~2 seconds**, same as the segment-switch flash above, then rendered correctly with the label text legible. | Confirmed the photograph stays visible while the label text below scrolls, same as desktop. | Same transient blank-image flash as above; more noticeable here because it's the first thing the user sees after tapping into a record. |

### Segments — Readings / Fields / History (via semantics `role="radio"`, since the segmented control itself has no visible text label reachable by simple text search — its accessible name is only exposed via `aria-label`, not text content)

- **Readings** (default): full label transcription, per-line reading detail, "Matches the reference reading at every position," language-policy panel, resolution/comparison detail. Renders correctly, matches what's on the photograph.
- **Fields**: ~20 identical field rows are rendered ("Field: supported", "Edit as written / Edit read as / Edit standardized" per row) with distinct visual field names and green "Supported" chips confirmed by screenshot (`fmnh_ins_number`, etc. are visible on screen). **However, every row's accessible group text is literally "Field: supported"** with the field name completely absent from the semantics tree — confirmed by pulling all matching semantics nodes; not one includes a field name, and no sibling node fills the gap. A screen-reader user hears "Field, supported" twenty times over with no way to tell which field is which.
- **History**: shows repeated "Technical detail" toggles. On web, **the semantics text dump for this segment is 16 consecutive "Technical detail" strings with nothing else** — no step number, no timestamp, no actor, no reason text — even though the visual/Android rendering of the same data (see Part B) clearly shows "1 · ingest", "synthetic-reviewer · 6h ago", "Reason: Verified immutable original" per row. The identifying text exists in the widget tree but is excluded from semantics; only the generic expand toggle is exposed.

### Filters — not testable

The Filters sheet/dialog could not be opened by any available method: its trigger button lives in the same non-semantic Queue sidebar (see Method notes), and plain coordinate clicks do not register on canvas in this harness. This is reported as **blocked**, not as passing.

### Intake — 1440x900, 1024x768, 390x844

| Width | What is visible | Defect |
|---|---|---|
| 1440x900 | Three columns: "Add photographs" (Choose files, sensitivity toggle, "Applies to photographs you add next", HEIC/TIFF/DNG caveat, pre-upload checklist), "Upload manifest" (No files selected yet). | None functional. Console clean. |
| 390x844 | Single column, same content, checklist fully visible after scroll, "Upload 0 photographs" button correctly disabled until a file + confirmation checkbox are set. | On the **first navigation to Intake from an open workbench record**, the canvas showed the **stale workbench screen for ~2-4 seconds** after the URL and the accessibility tree had already updated to Intake content — confirmed by reading the semantics tree mid-freeze (it already said "Choose files… Upload manifest…") while the screenshot still showed the old record. Self-corrected without interaction. This is a real, reproducible stale-frame/paint-lag defect, though likely exaggerated by the DDC debug build. |

Note: the web build only offers "Choose files" on Intake (no camera capture option, correctly — camera capture is device-only, confirmed by the on-screen caption "Camera capture runs in the Android and iOS apps").

### Help — broken for a signed-in user (Critical)

- Clicking the in-app **"Help and shortcuts" button** (top-right icon, which does have a working semantics node) does **nothing**: no dialog, no navigation, URL stays on `/queue`. Confirmed by clicking it live and checking `window.location.href` before/after — unchanged.
- Deep-linking directly to `/#/help` while signed in also does nothing useful: the router silently redirects to `/queue`.
- **Root cause, found in source** (`apps/specimen_digitization/lib/src/app/app_router.dart`, the `redirect()` closure): `AppRoutes.isEntryLocation()` only special-cases `/sign-in`, `/verify`, `/setup`. For any other location once a session+collection exist, the code calls `AppRoutes.collectionKeyIn(state.uri)`, which returns `null` for `/help` (its first path segment is `"help"`, not `"c"`), and `if (routeKey == null) return home;` sends the user straight back to the Queue. `/help` is a legitimate top-level `GoRoute` (declared right alongside `sign-in`/`verify`/`setup`) but was left out of the entry-location allowlist, so it can never be reached once signed in. This is a one-line-cause, high-confidence bug — not a guess from behavior alone.

### Browser Back from the workbench

- At 1024px ("pushed" layout), tapping the in-app "Back to queue" link works correctly and does change the URL back to `.../queue`.
- Testing the actual **browser Back button** from the workbench was compromised by the manual URL-injection workaround used to reach the workbench in the first place (see Method notes): it leaves extra, synthetic history entries, so the browser's native Back cycled through those instead of exercising a real user's forward/back stack. This could not be verified cleanly and is reported as **not conclusively testable**, not as passing or failing.

---

## Part B — Android (Medium_Phone_API_36, emulator-5554)

### Sign-in

| What is visible | Defect |
|---|---|
| Same content as web, light theme (system default), native Android text fields, standard IME. Typing and tapping worked immediately and reliably with real touch input — no workaround needed. | None. Cold start briefly shows the Flutter splash logo (~3s) before the sign-in form — normal. |

### Queue

| What is visible | Defect |
|---|---:|
| Top bar: "Insects" collection dropdown, refresh, sign-out, help icons. "Queue" header, search box, horizontally-scrollable status chips (All/Needs review/Cleared/Def…), Filters button, the one record row with Cleared/Not measured/Not calibrated/6h. Bottom tab bar Queue/Intake. Tapping the record row **works** and opens the workbench (unlike web). | None functional found. `adb logcat` filtered to the app's own PID shows no exceptions or overflow warnings anywhere in this session. |

### Workbench — top, then two scrolls (phone, portrait)

| Screen | What is visible | Defect |
|---|---|---|
| Top | "← Back to queue", "synthetic-label.png" + id, copy/refresh/keyboard icons, Source photograph with zoom controls and the label image rendered correctly and legibly, "Whole image"/"Label 1" chips, "Correct label regions" link, "Source details" (collapsed, chevron down), then a **sticky bottom action bar** ("Confirm label coverage" / "Approve record") that visibly overlaps/truncates the row directly above it (a green "Cleared…" chip is cut off, only its top sliver visible above the bar). | See below — this turns out to matter a lot, because scrolling does not work here. |
| "Scroll 1" (swipe attempted) | **No visual change at all.** | **Critical, reproducible defect: the Workbench screen does not scroll on an Android phone.** Tested with three different swipes — starting on the image, starting below the image on plain text, and a fast full-height fling — all produced zero movement. Ruled out as a general Android/touch problem by testing the same gesture on the **Intake** screen immediately after, which scrolled perfectly normally. `adb logcat` for the app's PID shows no `RenderFlex`/overflow error, so this reads as a captured/consumed gesture (most likely the `InteractiveViewer` around the source photograph, or a similar gesture arena, swallowing vertical drags for the whole page) rather than a broken layout. |
| "Scroll 2" / tapping "Source details" | Tapping the "Source details" header **did** work as a tap (it is a real tap target, unlike scrolling) and expanded to show "Source pixels: 1000 by 520 pixels" — but this new content's last line is immediately followed by, and partly hidden behind, the same sticky action bar, and it cannot be scrolled into full view. | Because scroll is broken, this content and the entire Readings/Fields/History segmented control (which sits further down the same column, confirmed present via the two-pane tablet layout — see below) are **unreachable on a phone**. This is ship-blocking: a reviewer cannot get to Fields, History, or read the full Source details on a real phone. |

### Readings / Fields segments (phone)

Not reachable — see the scrolling defect above. Both segments exist (confirmed via the tablet layout) but the segmented control itself is below the fold and the fold cannot be scrolled past on a phone.

### Intake (phone)

| What is visible | Defect |
|---|---|
| "Add photographs" panel: native **"Take photograph"** button (camera capture — present on Android, absent on web, as expected) plus "Choose files", Sensitive/Not sensitive toggle, HEIC/TIFF/DNG caveat, pre-upload checklist (Sharp focus, Smallest text readable, Even exposure, No glare, Every label inside the frame), "I checked framing and readability" checkbox, "Upload 0 photographs" (correctly disabled). Scrolling down reveals "Upload manifest" ("No files selected yet", "After a restart, select the same files again to resume") and "Nothing here yet." | None. This screen **scrolls correctly**, in contrast to the Workbench — confirms the scroll defect above is specific to the Workbench screen, not global. |

### System back gesture from the Workbench

`adb shell input keyevent 4` from the open record **correctly returned to the Queue** and the previously-opened row was highlighted green (a "just visited" affordance) — this is a nice touch and works correctly. (One earlier back-press from the Sign-in screen, before any record was opened, exited the app to the home screen outright — expected Android behavior for a root screen with no back stack, not a bug.)

### Tablet window (2360x1640 @ 320dpi)

| Screen | What is visible | Defect |
|---|---|---|
| Queue | Left nav rail (Queue/Intake) + full-width Queue list with the top app bar (collection dropdown, refresh, "Test reviewer" account, help). All 6 status chips fit on one row, no scrolling needed. Single pane (list only) — no third pane, since no record is open yet. | None. |
| Workbench | **Two-pane layout**: left = source photograph + zoom controls + "Source details"; right = status chips, Readings/Fields/History segmented control, and the reading/field/history content. This is a genuinely different (and better) layout than the phone's single column. | The same sticky "Confirm label coverage / Approve record" bar overlaps the bottom of the **right** (evidence) panel here too, cutting off the last visible line of content (confirmed on both Readings and History). Lower severity here because — unlike on the phone — the right panel **does scroll correctly** (confirmed: swiping inside it moved from History entry "1 · ingest" through entries "3", "4", "5", "6 · workflow step" cleanly), so the hidden line is only transiently covered, not permanently unreachable. |
| History tab | Switched correctly via tap (`Fields` tap failed to register with one coordinate attempt, `History` succeeded — see caveat below). Shows "Current decision history", "Current review version 21", numbered entries ("1 · ingest", "3/4/5/6 · workflow step") each with actor "synthetic-reviewer", a real timestamp ("6 h ago (13 Sep 2026, 21:38 CDT)"), a Reason string (e.g. "classify", "pin_dependencies", "quality_check"), and an expandable "Technical detail". This is the same data as the web History segment, but here every row **is** distinguishable — contrast with the web finding above where the accessible label drops all of this and repeats "Technical detail" alone. | One `Fields` tap attempt landed without effect (coordinate math was rechecked and looked correct; not chased further given `History` worked immediately after with the same method) — flagged as a possible intermittent hit-target issue on the segmented control at this density, not confirmed as a hard defect. |

---

## Defects to fix, ranked

1. **[Critical] Workbench does not scroll on an Android phone.** Readings/Fields/History and the rest of Source details are unreachable below the first screenful. Confirmed with three swipe variants; Intake scrolls fine on the same device in the same session, isolating this to the Workbench screen specifically (likely the source-photograph `InteractiveViewer` capturing the vertical drag for the whole page). Evidence: `apps/specimen_digitization/design/screenshots/rebuild/android-04-workbench-scroll1.png` is pixel-identical to `android-03-workbench-top.png` despite three scroll attempts between them; contrast with `android-06b-intake-scrolled.png`, which shows a successful scroll on the same device.

2. **[Critical] "Help and shortcuts" does nothing for a signed-in user, on web.** Clicking the button is a no-op; deep-linking to `/help` silently bounces to `/queue`. Root-caused in `apps/specimen_digitization/lib/src/app/app_router.dart`: the `redirect()` callback's entry-location allowlist (`AppRoutes.isEntryLocation`) omits `/help`, so `AppRoutes.collectionKeyIn(Uri.parse('/help'))` returns `null` and the generic `if (routeKey == null) return home;` fallback fires every time. One-line-diagnosable, not a guess.

3. **[Critical] The Queue screen (web) has no accessibility semantics for its sidebar, filters, search, or the specimen row, and the row cannot be opened by mouse click either.** Verified by enumerating every `flt-semantics` node on the screen (two nodes total: the two app-bar icons) and by testing both a real coordinate click and a manually dispatched trusted pointer-event sequence on the row, neither of which navigated to the record. The Filters sheet is unreachable for the same reason. This blocks keyboard and screen-reader users outright, and it is why this report had to fall back on hand-built deep links to reach the workbench at all.

4. **[High] Fields and History segments (web) drop the one piece of text that distinguishes each row from accessibility.** Fields: every row's group label is literally "Field: supported" with the field name never included (checked 8+ rows). History: the accessible text is 16 repeats of "Technical detail" with no step number, actor, timestamp, or reason — even though that text is present and correctly rendered visually (and correctly exposed on Android, per the tablet screenshots). A screen-reader user cannot tell rows apart in either segment.

5. **[Medium] Sticky bottom action bar ("Confirm label coverage" / "Approve record") overlaps scrollable content** in the Workbench, on both Android phone and tablet, and appears to do the same on web (a green status chip peeks out from behind it in the phone screenshots before any scrolling is attempted). On the phone this compounds defect #1 by permanently hiding content; on the tablet and (probably) web it's a cosmetic overlap since the content is still reachable by scrolling.

6. **[Medium] Repeated identical network requests.** The web client fired the same `GET /v1/organizations/.../specimens?collection_id=...&limit=50` request 7 times in a row with identical parameters shortly after sign-in (seen in the browser's network log). Not confirmed as a hard bug (could be intentional retry/poll behavior) but worth a look — it's excessive for a one-record fixture collection.

7. **[Low] Transient blank/black source-photograph flash**, roughly 1-2 seconds, on: (a) every Readings→Fields/History segment switch (web, 1440px, reproducible every time), and (b) first paint of the Workbench on mobile web (390px). Both self-correct without interaction. Likely worse in this DDC debug build than a release build would be, but a real user would still see a flash today.

8. **[Low] Stale-frame paint lag when navigating Workbench → Intake on mobile web.** The previous record's canvas stayed on screen for 2-4 seconds after the URL and semantics tree had already updated to Intake; self-corrected. Same debug-build caveat as #7.

9. **[Low / cosmetic] Status-filter chip row has no scroll affordance** at narrow widths (mobile web 390px, and implicitly Android phone) — it's a working horizontal scroll, but nothing hints that "Deferred/Blocked/Processing" exist past the visible "Cleared" chip.

## Not conclusively tested (call these out to the reviewer, don't read them as "passing")

- **Filters sheet** (web and, by extension, Android phone where the same overlap issue exists): trigger is inside the broken Queue sidebar; never opened.
- **Browser Back from an open record**: the manual URL-injection workaround used to open the record pollutes the history stack, so native Back could not be exercised as a real user would encounter it.
- **Fields segment on the Android tablet**: one tap attempt at (1732, 900) did not switch tabs; not re-tested with a second coordinate before time ran out. History switched correctly with the same method immediately after.

## Screenshots saved

All Android screenshots are in `apps/specimen_digitization/design/screenshots/rebuild/`:
`android-01-signin.png`, `android-02-queue.png`, `android-03-workbench-top.png`, `android-04-workbench-scroll1.png` (identical to -03, evidence of the scroll bug), `android-04b-workbench-sourcedetails-expanded.png`, `android-05-backkey-from-workbench.png`, `android-06-intake.png`, `android-06b-intake-scrolled.png`, `android-07-tablet-queue.png`, `android-08-tablet-workbench.png`, `android-08c-tablet-history.png`, `android-08d-tablet-history-scrolled.png`.

Web screenshots were not saved to disk (the browser tool used for Part A cannot write files); all web findings above are described from the images returned in-session, cross-checked against `get_page_text`/semantics-tree dumps and `read_console_messages` where noted.
