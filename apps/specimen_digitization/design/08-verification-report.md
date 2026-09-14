# 08. Verification report

Step 7 of the sequencing in [00-north-star.md](00-north-star.md): the heuristic
re-audit, the accessibility scripts, the size-class goldens and the gates, run by
someone who did not build the client.

Branch verified: `feat/motion-and-polish`, which is `main` plus the motion and
polish pull request (#43), the last of the six build steps. Toolchain Flutter
3.38.5, Dart 3.10.4. Every claim below is backed by a test name, a golden PNG, a
`file:line`, or a screenshot, and a claim with none of those is marked Partial
rather than Pass.

## Executive summary

The rebuild is close to the bar and misses it in three places, all of them on the
record screen and all of them measurable.

Of the 56 pass criteria in the heuristics audit, **36 pass, 15 are partial and 5
fail**. Five of the eight dimensions of "The bar" are met: writing, visual system,
motion, honesty and, for the screens other than the record, adaptation. Usability,
accessibility and speed of review are not yet met.

The three findings that matter. First, the record screen lays out past the window
it was given on a phone at normal text size and at every width at 200 percent
text, and when it does the photograph is the thing that disappears: the screen
whose first principle is "evidence before interpretation" shows no evidence. It
is reproduced by 30 of the 97 goldens. Second, `J` and `K`, the two keys the north
star's speed-of-review row is written around, are bound, documented in the help
sheet, and wired to a callback the record screen never supplies, so they do
nothing. Third, opening a record by its URL on a desktop window cancels the queue
load that was in flight, and the list pane then states that the collection is
empty when it is not.

None of these is in the foundation. The token system, the writing pass, the
component library, the routes, the motion catalog and the honest-absence states
are all in place and all hold up under inspection: zero color literals outside
the theme, zero string-lint violations, zero em-dashes, light and dark correct in
all 97 goldens, and a semantics tree that names every control. Eight trivial
defects were fixed in this branch. The rest are listed below with the exact fix.

Gates: `flutter analyze --fatal-infos` clean, `flutter test` 739 passing and 10
skipped with no failures, string lint 0 violations, color-literal backlog 0,
`flutter build web --release` succeeds, `scripts/ci/build_mobile.sh android`
succeeds.

## What was run

| Gate | Result |
|---|---|
| `flutter analyze --fatal-infos` | No issues found |
| `flutter test` | 739 passed, 10 skipped, 0 failed |
| `python3 scripts/ci/check_ui_strings.py --baseline scripts/ci/ui_strings_baseline.txt` | 95 files scanned, 0 violations, 0 baselined, 0 warnings |
| `test/theme/no_color_literals_test.dart` | 0 literals outside `lib/src/theme/`, backlog empty |
| `flutter build web --release` | Built `build/web` |
| `bash scripts/ci/build_mobile.sh android` | Built `app-debug.apk` with the Android Studio JDK |

The 10 skips are seven live-backend HTTP tests that need a running API, and three
skipped assertions added by this verification that record findings V-2, V-3 and
V-4 below. Each skip carries the finding it belongs to in a comment, so the skip
list is the backlog and deleting an entry is how a fix gets proven.

### New in this branch

- `test/golden/golden_harness.dart` and `test/golden/size_classes_golden_test.dart`:
  97 goldens in `test/golden/images/`. Sign-in, queue, filters and the region
  editor at 390x844, 768x1024, 1180x820 and 1440x900 in light and dark; intake
  and the workbench's three segments at the same eight combinations at text scale
  1.0 and 2.0; the help sheet at compact. The record is built from
  `test/fixtures/backend-wire-examples.json` and the photograph is
  `test/fixtures/synthetic-label.png`, so a golden that moves because the wire
  moved is a real signal.
- `test/accessibility/semantics_fixtures_test.dart` and
  `test/accessibility/fixtures/*.txt`: a checked-in semantics dump for the queue,
  the three workbench segments, intake, filters, the region editor and the reason
  sheet, plus nine assertions about what a screen reader can tell.
- `test/accessibility/keyboard_walkthrough_test.dart`: the whole review, keyboard
  only.
- `design/screenshots/rebuild-smoke.md` and `design/screenshots/rebuild/`, copied
  in from the build worktree. **These document the state before PR #43** and are
  the only real-device evidence that exists. Read them as such: the environment
  banner in those captures still shouts in capitals and still carries an em-dash,
  both of which the current code has fixed
  (`lib/src/widgets/environment_banner.dart:31-34`). No device capture was taken
  of an account with more than one collection, so the app-bar collection switcher
  is unverified on hardware.

### How to read the goldens

`flutter test` renders text in the deterministic test font, so every glyph is a
solid box. That is deliberate and it is what makes these goldens a CI gate rather
than a machine-specific picture: the same bytes come out on any host. Boxes still
show layout, overflow, clipping, an empty pane, a missing element and the wrong
theme, which is everything this report claims from them. For legible copy, read
the device screenshots in `design/screenshots/` instead. Where the test font
inflates a result, this report says so.

## Pass criteria, one row each

Verdicts: **Pass** means demonstrated. **Partial** means the behaviour is present
but something the criterion asks for is not demonstrated. **Fail** means the
criterion is not met.

### 1. Visibility of system status

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1.1 | Paginated lists state loaded and total, or say the total is unavailable | Pass | The header says what is loaded and never implies a total: `lib/src/screens/queue/queue_screen.dart:398-408`; `test/accessibility/fixtures/queue.txt` line 4 |
| 1.2 | Server actions show progress on the control within 200 ms and a result within a second | Partial | `InFlightGlyph` swaps in place on the load-more control and the decision bar (`lib/src/widgets/in_flight_glyph.dart`, `queue_screen.dart:520-536`), and `_SavedCheck` shows the result (`status_strip.dart:503-520`). No test measures the 200 ms or the one second |
| 1.3 | Auto-refreshing screens say when they last refreshed and never replace content silently | Pass | "Updated N s ago" in the header (`queue_screen.dart:411-418`), and a poll that lands while a row has focus is held rather than applied (`lib/src/workspace.dart:399-407`) |
| 1.4 | An open specimen warns within 30 s of its revision changing, before a save | Partial | The warning exists and is correct (`status_strip.dart:147-160`, `conflictVersion`), but it is raised by the 20 s poll only; no test asserts the 30 s bound |
| 1.5 | Batch operations show done, remaining and failed | Pass | `batchProgressLine` in `lib/src/screens/intake/manifest_entry.dart:142-158` counts accepted, skipped, duplicate, failed and interrupted; `test/intake_batch_test.dart` |
| 1.6 | No machine timestamps; locale format with a relative phrase inside 24 hours | Pass | `relativeAge` and `absoluteTime` in `lib/src/widgets/queue_row.dart:23-55`, paired in the row's own label; `test/widgets/queue_row_test.dart` |

### 2. Match between the system and the real world

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 2.1 | No hand-typed identifiers, timestamps or JSON where a picker is possible | Pass | Dates use a range picker and profiles a dropdown (`lib/src/search_filters.dart:253-267`); the free-text filters are identifier searches the server has no list for |
| 2.2 | Domain words in the default view; internal vocabulary only inside technical detail | Pass | `lib/src/vocabulary.dart`; the one leak found in this audit, the raw severity `hard` printed beside a validation finding, was fixed here (`vocabulary.dart:33-40`). `test/vocabulary_test.dart` |
| 2.3 | Every quantity carries a unit the user can act on | Pass | Risk is a named 0 to 100 scale with its range spoken (`test/accessibility/fixtures/filters.txt`, "Risk range, 0 to 100"); geometry is in pixels (`region_editor.dart:517-530`) |
| 2.4 | Two elements naming the same object use the same name everywhere | Pass | One region is "Label 1" on the overlay, on the chip and in the reading card: `test/accessibility/semantics_fixtures_test.dart`, "a region overlay and its chip answer to the same name" |
| 2.5 | No string relies on a symbol as its only semantic carrier | Pass | Status is glyph plus word plus border (`lib/src/widgets/status_chip.dart:1-6`); the diff marks each run with a symbol and a word (`lib/src/widgets/diff_text.dart:170-215`). The one dangling string found, "Step " with nothing after it, was fixed here (`lib/src/operational_panel.dart:54-62`) |

### 3. User control and freedom

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 3.1 | Platform and browser back return to the previous screen on all three platforms | Pass | `test/app/routing_test.dart`, "opening a record changes the location, and back returns"; `test/accessibility/keyboard_walkthrough_test.dart` closes on browser back; `design/screenshots/rebuild/android-05-backkey-from-workbench.png` on a device |
| 3.2 | Destructive actions show their consequence before the confirm button and can be cancelled | Pass | `ReasonForm` states consequence, what is retained and what is still outstanding (`lib/src/widgets/reason_sheet.dart:17-42`); `test/widgets/reason_sheet_test.dart` |
| 3.3 | A dialog with unsaved text refuses a scrim tap or back without asking, and offers Keep editing | Pass | `showAdaptiveForm(dismissible: false)` plus the form's own `PopScope` (`lib/src/widgets/adaptive_form.dart:33-37`); `test/widgets/reason_sheet_test.dart` |
| 3.4 | Every saved decision offers Undo for 10 s, or says in its confirm dialog that it cannot be undone | **Fail** | Neither exists. There is no Undo affordance anywhere outside the region editor's local step (`lib/src/region_editor.dart:149-163`), and no reason sheet states that the decision is final. Grep for "cannot be undone" in `lib/` returns nothing |
| 3.5 | Local edits inside a dialog, including delete, merge and reorder, are reversible without closing it | Partial | The region editor keeps exactly one undo step (`region_editor.dart:122,149`), so the last change is reversible and the one before it is not |
| 3.6 | An in-flight batch can be stopped, and stopping leaves no record unnamed | Pass | The Stop control and its "the file already sending finishes first" notice (`lib/src/screens/intake/manifest_panel.dart:124`, `163-175`); `test/intake_batch_test.dart` |

### 4. Consistency and standards

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 4.1 | One control type per job; tabs are `TabBar`, single-choice sets `SegmentedButton`, multi-select `FilterChip`, disclosures `ExpansionTile` | Partial | The types are used consistently, but the Readings / Fields / History switcher is a `SegmentedButton` (`lib/src/workbench.dart:740`) where the accessibility document asks for a `TabBar` so it announces as a tab list. Finding V-3 |
| 4.2 | Confirm buttons follow one naming pattern; one action is never named two ways | Pass | Every confirm is the verb phrase of the action, passed as `ReasonForm.action` from one place (`lib/src/screens/workbench/decision_bar.dart:69-72`); `test/accessibility/fixtures/reason-sheet.txt` |
| 4.3 | Errors appear in exactly three places by rule: field, action, screen | Pass | Field errors on the row (`fields_panel.dart:305-330`), action errors on the control (`decision_bar.dart:170-186`), screen errors in the banner (`lib/src/app/shell.dart:437`) |
| 4.4 | Every string comes from the bundle; no em-dash or en-dash | Pass | `check_ui_strings.py` 0 violations; grep for the two dashes in `lib/` returns nothing |
| 4.5 | Every status is icon plus text as well as colour, and passes a greyscale screenshot test | Partial | Icon plus text is real and verified (`status_chip.dart:1-6`, `test/widgets/status_chip_test.dart`, and every status in `test/accessibility/fixtures/*.txt` is a word). There is no greyscale screenshot test |
| 4.6 | Every target is at least 48 by 48; every icon-only control has a tooltip and a semantic label | Pass | `test/accessibility/guidelines_test.dart` and `test/accessibility/workbench_guidelines_test.dart` run the Android and iOS tap-target and labelled-target guidelines with an empty skip list; every icon-only control in the six semantics fixtures carries a tooltip |

### 5. Error prevention

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 5.1 | No hand-authored structured format where a picker is possible | Pass | Same evidence as 2.1 |
| 5.2 | A confirmation authorising work on more than one item states the exact count | Pass | "Save 5 pending changes" on both the control and the sheet; `test/widget_test.dart`, "five corrections save under one reason, in one action" |
| 5.3 | A record cannot be saved into a structurally impossible state | Pass | Supported demands content and linked evidence, and a coordinate outside the image is refused (`lib/src/workbench.dart:151-157`, `region_editor.dart`); `test/region_editor_test.dart`, `test/workflow_controls_test.dart` |
| 5.4 | Every measurement the client displays is a gate or carries an explicit override tick | Pass | The per-batch confirmation is the tick (`intake-confirm`); `test/intake_sensitivity_test.dart` |
| 5.5 | Every confirm dialog lists outstanding findings, blockers and superseded results | Pass | `ReasonForm.outstanding` (`reason_sheet.dart:30`); `test/accessibility/fixtures/reason-sheet.txt` shows the finding listed |
| 5.6 | Every button that can fail its own precondition says why; no silent no-op | **Fail** | Almost everywhere this holds, and the hint now reaches the button's own node after the fix in this branch. `J` and `K` are the exception: bound, listed in the help sheet, and wired to a null callback, so they are exactly the silent no-op this forbids. Finding V-2 |

### 6. Recognition rather than recall

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 6.1 | No correction without the source pixels visible on the same screen | **Fail** | True at medium, expanded and large at normal text: `test/golden/images/workbench-fields__medium-768x1024__light__text1.0.png`. False on a phone and false at 200 percent text at every width, where the pinned source pane collapses and the photograph is replaced by an overflow stripe: `workbench-fields__compact-390x844__light__text1.0.png`. Finding V-1 |
| 6.2 | Every identifier the user supplies is selectable from values on the record | Pass | The evidence picker offers only the record's own evidence (`lib/src/screens/workbench/evidence_picker.dart`); `test/pilot_evidence_test.dart` |
| 6.3 | One list of everything blocking clearance, each entry navigating to its control | Pass | "2 things block clearance" opens the list and each entry scrolls to its field (`lib/src/screens/workbench/blockers.dart`, `workbench.dart` `_goToBlocker`); `test/accessibility/fixtures/workbench-readings.txt` |
| 6.4 | Active filters are individually visible and individually removable without a dialog | Pass | `_ActiveFilterChips` (`queue_screen.dart:470-506`); `test/screens/queue_test.dart`, "an active filter is a chip, and removing the chip refilters" |
| 6.5 | The queue keeps its scroll position, shows the reviewer's position, and offers next and previous from inside a record | **Fail** | Scroll position is kept (`workspace.dart` `holdList`/`releaseList`), but there is no position indicator, no next or previous control, and on a large window a deep link leaves the list pane claiming the collection is empty. Findings V-2 and V-5 |
| 6.6 | Every row carries enough to choose between rows without opening any | Pass | Identifier, plain-language reason, status, risk and age, all in one spoken label: `test/accessibility/fixtures/queue.txt` line 14 |

### 7. Flexibility and efficiency of use

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 7.1 | Approve, confirm coverage, next, previous, switch tab, focus search, zoom and back are all on the keyboard, and `?` lists them | Partial | Seven of the eight work, proven key by key in `test/accessibility/keyboard_walkthrough_test.dart`; `?` opens the list and the list is complete. Next and previous do not work. Finding V-2 |
| 7.2 | Five fields corrected on one record save with one round trip and one reason | Partial | One reason and one user action, yes; one round trip, no. The wire takes one decision per call, so five corrections are five calls (`test/widget_test.dart:392-399` states this in the test itself) |
| 7.3 | The queue supports multi-select and the non-destructive bulk actions the server permits | **Fail** | Not built. No selection model exists in `lib/src/screens/queue/` or `lib/src/workspace.dart` |
| 7.4 | Filter sets can be named, saved, reapplied in one action, and survive a restart | **Fail** | Not built. Grep for a saved-filter concept in `lib/` returns nothing |
| 7.5 | Every specimen has a URL that opens it directly on web and by deep link on mobile | Pass | `test/app/routing_test.dart`, "a link to a record opens that record"; every golden in the workbench group is produced by a deep link |
| 7.6 | A reason can be chosen from configured codes or recent reasons without typing | Partial | Recent reasons are offered as chips (`reason_sheet.dart:30`, `workbench.dart` `_recentReasons`), and they are populated from this session only. Configured reason codes are not read from the profile |

### 8. Aesthetic and minimalist design

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 8.1 | No raw JSON in a default view; every dump behind a closed technical-detail disclosure, and every value also typed | Pass | `EvidenceDrawer` is closed by default and named "Technical detail" (`lib/src/widgets/evidence_drawer.dart`); it appears as a collapsed button in every workbench semantics fixture |
| 8.2 | No paragraph over 20 words in a default view; longer copy behind "Why?" | Pass | `CaveatText` splits label from explanation (`lib/src/widgets/caveat_text.dart`); `check_ui_strings.py` enforces the budgets |
| 8.3 | Every card has one job; the primary action is visible without scrolling at 1024x768 and 390x844 | Partial | True at 1024x768 (`workbench-readings__medium-768x1024__light__text1.0.png` shows the decision bar pinned). At 390x844 the decision bar is pinned and visible, but the pane above it has overflowed, so what is on screen is not what the blueprint intends. Finding V-1 |
| 8.4 | On a tablet in landscape the source image takes at least 40 percent of viewport height and expands to full width in one action | Partial | The 40 percent target and the full-screen control are both implemented (`workbench_layout.dart:53,108`, the "Open the photograph full screen" tooltip in every workbench fixture). The floor beneath the target is set below the pane's own chrome height, so the target is not honoured when the chrome is tall. Finding V-1 |
| 8.5 | Renders correctly in light and dark at 200 percent text with no clipping and no horizontal scrolling | **Fail** | Light and dark are correct in all 97 goldens, and no golden scrolls horizontally. At 200 percent text the record screen clips at every one of the four widths in both themes, 24 goldens, plus 6 more at 100 percent on a phone. Finding V-1 |
| 8.6 | All spacing, type sizes and semantic colours come from named tokens; no layout literal in a widget file | Pass | `test/theme/no_color_literals_test.dart` reports 0 literals outside `lib/src/theme/` with an empty backlog; `test/theme/theme_wiring_test.dart` |

### 9. Help users recognize, diagnose, and recover from errors

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 9.1 | Every error names what happened, the state the work is in, and the single next action | Pass | The stale-revision message names all three (`workspace.dart:292-295`), as does the dropped-correction notice (`status_strip.dart:206-218`). The one message that named an internal enum instead, "…is required hard", was fixed here |
| 9.2 | Every error surface carries the recovery action for that specific failure; no two classes share a generic action | Pass | Conflict offers Refresh, access failure tears the workspace down and offers a role recheck, intake failure offers per-file retry (`workspace.dart:114-124`, `manifest_panel.dart`) |
| 9.3 | Every error is attached to the object that failed | Pass | Field errors sit on the field row and are live regions (`test/accessibility/fixtures/workbench-fields.txt`, the `liveRegion` line under Collectors) |
| 9.4 | Every error is visible without scrolling from its control, in the error colour with an error icon, and announced | Pass | `Symbols.error` plus `colorScheme.error` plus `Semantics(liveRegion: true)` on the same row (`fields_panel.dart:300-330`) |
| 9.5 | No error is dismissed by a background process before the user acts; every persistent error is user-dismissible | Partial | A poll that lands while a row has focus is held rather than applied, which protects the list. The workspace error banner is cleared by the next successful refresh (`workspace.dart:378-390`), which is a background process clearing an error the user may not have read |
| 9.6 | Configuration failures show a non-secret diagnostic line an administrator can act on | Pass | `lib/src/app/setup_screen.dart` and `lib/main.dart:76-82`; `test/production_startup_test.dart` |

### 10. Help and documentation

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 10.1 | A help control is at most two taps from every screen, listing shortcuts, a walkthrough, a glossary, a problem report and build information | Partial | One tap from every screen (the app-bar control, in all six semantics fixtures) and it carries the shortcuts and the glossary (`test/app/routing_test.dart`, `test/golden/images/help__compact-390x844__light.png`). No task walkthrough, no problem report, no build information |
| 10.2 | Every domain term has a one-sentence definition reachable from where it appears | Partial | The glossary is complete and `CaveatText` puts a "Why" beside the caveats, but a term in a row is not itself a link to its definition |
| 10.3 | Every instruction to contact an administrator names a person or a role and provides a working way to reach them, prefilled with the record context | **Fail** | Six messages say "ask your administrator" and none of them names a person, a role or a way to reach one (`lib/src/auth.dart:295,298,431,433,435`, `lib/main.dart:80`) |
| 10.4 | A new reviewer completes a first review using only in-app guidance, verified with two people who have not seen the app | Partial | Not verifiable from a repository. The material a first-time reviewer would need is present except for the walkthrough named in 10.1 |
| 10.5 | Every screen that hands work to an asynchronous process says what happens next and how to reach the result | Pass | Intake says what happens after an upload and links to the queue (`manifest_panel.dart:137-162`); the retry dialog says the outcome may be unknown (`workbench.dart:1063-1069`) |

**Totals: 36 Pass, 15 Partial, 5 Fail.**

## The bar, one row each

| Dimension | Standard | Met | Evidence |
|---|---|---|---|
| Usability | All ten heuristics pass with no finding above severity 1 | **No** | 5 criteria fail and 15 are partial; findings V-1, V-2 and V-5 are severity 1 |
| Writing | Every string passes the checklist, no string over budget, zero em-dashes | **Yes** | `check_ui_strings.py` 0 violations over 95 files; no em-dash or en-dash anywhere in `lib/` |
| Visual system | Zero literal colors, sizes or durations in widgets; light and dark both ship; every text pair meets AA | **Yes** | `no_color_literals_test.dart` 0 with an empty backlog; `theme/contrast_test.dart` and `accessibility/contrast_test.dart`; light and dark verified correct in all 97 goldens by a luminance check over every file |
| Motion | Every animation is in the catalog with a reason and collapses under reduced motion | **Yes** | `test/motion/motion_tokens_test.dart`, `page_transitions_test.dart`, `reduced_motion_test.dart`; every animation site in `lib/` cites its catalog row in a comment |
| Adaptation | Every screen verified at compact, medium, expanded and large, both orientations, on iOS, Android and web | **Partial** | 97 goldens cover four widths in two themes, and sign-in, queue, filters, intake and the region editor are clean at all of them. The record screen is not (V-1). Orientation is covered only through the width that each orientation produces. Device coverage is the pre-#43 screenshots in `design/screenshots/` |
| Accessibility | WCAG 2.2 AA; VoiceOver and TalkBack scripts complete unaided; keyboard-only review on web | **No** | Keyboard-only review passes end to end except `J` and `K` (V-2). The switcher does not announce as a tab list (V-3), so VoiceOver script step 6 cannot pass. A first queue load announces nothing (V-4). VoiceOver and TalkBack were not run on hardware in this verification |
| Honesty | No measurement renders as zero when missing; no score without components; no forbidden action appears enabled | **Yes** | `test/runtime_risk_test.dart`, `test/pilot_evidence_test.dart` and the wire tests all green; the fields fixture shows Unknown, Unreadable and Not present as first-class words, never blanks; the disabled-action audit in `semantics_fixtures_test.dart` finds no enabled control the server forbids |
| Speed of review | One specimen to the next, including one correction with a reason, without leaving the keyboard on desktop | **No** | The correction and its reason are fully keyboard-reachable and proven so. Moving to the next specimen is not. V-2 |

## Remaining defects, ranked

Severity 0 is "a reviewer cannot do the job", 4 is "a reviewer would not notice".

### V-1, severity 1: the record screen overflows and the photograph disappears

**Where.** `lib/src/screens/workbench/workbench_layout.dart:125`, `pinnedSourceMinHeight = 160`, used by `pinnedSourceHeight` at `workbench_layout.dart:104-120` and laid out at `lib/src/workbench.dart:1061-1076`.

**What happens.** The pinned source pane is given a floor of 160 logical pixels. Its own fixed rows, the title, the five view controls and the region chip strip, need about 248. When the record header and the decision bar leave the pane no more than its floor, it is drawn at 160, overflows by 88, and the photograph gets no height at all. At text scale 2.0 the same thing happens at every width, by 110 to 508 pixels.

**Evidence.** 30 of the 97 goldens, listed in `knownWorkbenchOverflows` in `test/golden/size_classes_golden_test.dart:51-67`. Start with `test/golden/images/workbench-readings__compact-390x844__light__text1.0.png`: the overflow stripe is at y 548 and there is no photograph above it. Compare `workbench-readings__medium-768x1024__light__text1.0.png`, where the same screen is correct.

**How much of this is the test font.** Some. The test font is wider than Roboto, so the environment banner and the record header wrap to more lines than they would on a device, and `design/screenshots/rebuild/android-03-workbench-top.png` shows the photograph present on a real phone at 411x914. The mechanism is not a font artifact: the floor is below the pane's own chrome height, so any tall chrome triggers it, and text scale 2.0 triggers it on every device. Pass criterion 8.5 requires 200 percent text to work.

**Exact fix.** Raise `pinnedSourceMinHeight` to the pane's measured chrome height plus a readable image band, by measuring the chrome the way `_stackedChrome` already measures the record chrome (`workbench.dart:97-101`) rather than hard-coding a number; and when even that does not fit, drop the pinned header entirely and leave the full-screen control as the way to the photograph, which is what the comment at `workbench_layout.dart:119-125` already says should happen but which the `return free - pinnedSourceMinHeight > 0 ? pinnedSourceMinHeight : 0` branch does not achieve because the 160 it returns is itself too small. Then delete the matching entries from `knownWorkbenchOverflows`; the test fails if an entry stops overflowing, so the list cannot rot.

### V-2, severity 1: `J` and `K` are documented, bound and inert

**Where.** `lib/src/screens/queue/workbench_screen.dart:96-150` constructs `ReviewWorkbench` without `onNext` or `onPrevious`. `lib/src/workbench.dart:962-973` invokes `widget.onNext?.call()`. `lib/src/screens/workbench/shortcuts.dart:88-89` lists both in the help sheet.

**What happens.** A reviewer reads "J, next specimen" in the shortcut list, presses J, and nothing happens. This is pass criterion 5.6's silent no-op, criterion 6.5's missing next and previous, criterion 7.1's incomplete keyboard map, and the north star's speed-of-review row.

**Evidence.** `test/accessibility/keyboard_walkthrough_test.dart`, "J and K move to the next and the previous record", skipped with this finding named.

**Exact fix.** In `_WorkbenchScreenState.build`, read the record's index from `controller.items` by `widget.specimenId`, and pass `onNext` and `onPrevious` that `context.go` to the neighbouring record's location, null at each end so the control and the binding disappear rather than doing nothing. This depends on V-5: the list has to be loaded for the neighbours to exist.

### V-3, severity 1: the evidence switcher does not announce as a tab list

**Where.** `lib/src/workbench.dart:740`, `SegmentedButton<WorkbenchSegment>`.

**What happens.** Material's `SegmentedButton` exposes `checked` and `inMutuallyExclusiveGroup`, which VoiceOver and TalkBack read as a radio button. Section 4.2 step 6 of the accessibility document requires "tab, 1 of 3, selected" and a rotor jump between tabs; pass criterion 4.1 requires tabs to be a `TabBar`.

**Evidence.** `test/accessibility/fixtures/workbench-readings.txt` lines 27-29 show `checked=isTrue … inMutuallyExclusiveGroup` and no role. `test/accessibility/semantics_fixtures_test.dart`, "the evidence switcher announces itself as a tab list", skipped with this finding named. The selected state itself is exposed correctly and is asserted unskipped by the test above it.

**Exact fix.** Either replace the switcher with a `TabBar` plus `TabBarView`, which also brings arrow-key movement between tabs for free and satisfies section 4.2 step 3, or wrap the existing control in `Semantics(role: SemanticsRole.tabBar)` and each `ButtonSegment.label` in `Semantics(role: SemanticsRole.tab)`. The `TabBar` is the one the criterion names.

### V-4, severity 2: a loading queue announces nothing

**Where.** `lib/src/widgets/skeleton.dart:112-124`. With `visible` false, the live region's child is `const SizedBox.shrink()`, its semantics node has an empty rect, and an empty rect is dropped from the tree. `lib/src/screens/queue/queue_screen.dart:298` uses exactly that default for the queue's first load.

**What happens.** A reviewer using a screen reader gets silence for the whole first load, which is the failure the widget's own doc comment says it exists to prevent.

**Evidence.** `test/accessibility/semantics_fixtures_test.dart`, "a silent wait still announces that the queue is loading", skipped with this finding named. The `visible: true` path is asserted unskipped and passes.

**Exact fix.** Replace the invisible branch with `SemanticsService.sendAnnouncement(message, Directionality.of(context))` fired once from `initState`, which is what a momentary event with no persistent text host is for, and keep the live region only for the visible branch. Do not give the node a one-pixel box; a node a screen reader can focus but nobody can see is worse than the announcement.

### V-5, severity 1: a deep link to a record empties the queue pane

**Where.** `lib/src/workspace.dart:381` (`refresh` takes `++_generation`), `:398` (`if (generation != _generation) return`), and `:526` (`openSpecimen` also takes `++_generation`).

**What happens.** One counter guards two independent loads. On a deep link the router mounts `WorkbenchScreen`, whose `didChangeDependencies` schedules `openSpecimen` as a microtask; that runs while `refresh`'s await is outstanding, bumps the generation, and `refresh` then discards the page it already fetched. `_updatedAt` is never set, `_items` stays empty, and `QueuePane` renders the empty state at `queue_screen.dart:272`, telling the reviewer "No specimens yet. Upload a photograph to create the first record" about a collection that has records.

**Evidence.** `test/golden/images/workbench-history__large-1440x900__light__text1.0.png`, the middle pane. Reproduced directly: at 1440x900, a deep link to the record yields 0 `QueueRow`s and 1 `EmptyState` saying "No specimens yet", while landing on `/queue` at the same width yields 1 row.

**Exact fix.** Give the list and the selected record separate counters, `_listGeneration` for `refresh` and `loadMore` and `_recordGeneration` for `openSpecimen`, so opening a record cannot cancel a list load. Then gate `QueuePane._empty` on `controller.updatedAt != null`, so a list that has never been answered renders `SkeletonRow`s and the loading announcement rather than a claim about the collection. Watch `test/app/request_budget_test.dart` while doing it: the fix must not turn one page request into two.

### V-6, severity 2: the filter dialog's risk switch is painted over the Apply button

**Where.** `lib/src/search_filters.dart:221`, the `Flexible(SingleChildScrollView(...))` inside a `Column(mainAxisSize: min)` that `showAdaptiveForm` puts in a `Dialog` with no height bound (`lib/src/widgets/adaptive_form.dart:76-89`).

**What happens.** At 768 logical pixels wide the scrolling body is given more height than what is left after the action row, so the last control in it, the "Include not measured" switch, is drawn on top of the primary action. Measured: the switch occupies (540, 904) to (600, 944) and Apply occupies (489.5, 936) to (608, 984); they overlap.

**Evidence.** `test/golden/images/filters__medium-768x1024__light.png`, bottom right.

**Exact fix.** Bound the dialog's height in `showAdaptiveForm` with `ConstrainedBox(maxHeight: MediaQuery.sizeOf(context).height * 0.9)` around the `ConstrainedBox` that already bounds the width, and change `Flexible` to `Expanded` in `SearchFilters.build` so the scroll view takes exactly what is left after the title and the actions.

### V-7, severity 2: the region editor gives the photograph almost no height on a phone

**Where.** `lib/src/region_editor.dart`, the body's column inside the compact bottom sheet.

**What happens.** At 390x844 the image band is about 35 logical pixels tall between the region chips above it and the coordinate field below it, which is not enough to drag a corner handle on. The north star calls for a direct-manipulation editor on touch; this is a coordinate form with a thumbnail.

**Evidence.** `test/golden/images/region-editor__compact-390x844__light.png`, against `region-editor__large-1440x900__dark.png` where the same editor is correct and the handles are usable.

**Exact fix.** On a compact window give the image an `AspectRatio` floor of the asset's own ratio with a minimum height of roughly 240, and move the coordinate field and the reason behind a disclosure so the photograph is the sheet's main content rather than one row of it.

### V-8, severity 2: disabled controls are drawn at 2.3:1

**Where.** The Material disabled state carried by the theme, seen on `Correct label regions` and `Approve record` when the server forbids them.

**What happens.** The reason a control is disabled is now correctly on the control's own semantics node, so a screen reader hears it. A sighted reviewer reads it at a contrast ratio of 2.38:1 and 2.25:1. WCAG 1.4.3 exempts inactive components, so this is not an AA failure, but a reason nobody can read is not a reason.

**Evidence.** Measured by `textContrastGuideline` during this verification once the hint was merged onto the button node.

**Exact fix.** Raise the disabled-state content color in `lib/src/theme/component_themes.dart` from Material's 0.38 opacity to a token that clears 4.5:1 against the surface, and add the pair to `test/theme/contrast_test.dart` so it stays there.

### V-9, severity 3: the collection switcher's floating label sits 1.5 px above the window

**Where.** `lib/src/app/shell.dart:163-180`.

**What happens.** An `AppBar` stretches an action to the 56 dp toolbar height. A 48 dp outlined field, which is the minimum target size, draws its floating label across its own top border, and the label's box then starts 1.5 px above y 0. On a phone or a tablet the status-bar inset hides this; in a browser, where the toolbar starts at y 0, it does not. The vertical padding added in this branch took it from 5.5 px to 1.5 px, which is inside Roboto's ascent padding, so the ink is visible; the box still overhangs.

**Evidence.** `test/golden/images/queue__expanded-1180x820__light.png`, top centre. Measured: the label's box top is at -1.5 and the field is 48 tall.

**Exact fix.** Stop using a floating-label form field as an app-bar action. Replace `_CollectionDropdown`'s dense variant with a `MenuAnchor` showing the collection name and a chevron, wrapped in `Semantics(label: 'Authorized collection')` and a `Tooltip`, which fits the toolbar and keeps the 48 dp target.

### V-10, severity 3: the region editor and the filter form take no initial focus

**Where.** `lib/src/region_editor.dart` and `lib/src/search_filters.dart` have no `autofocus`. Only `lib/src/widgets/reason_sheet.dart:180` sets one.

**What happens.** Section 4.2 step 5 of the accessibility document requires initial focus to land on a sensible first field rather than silently on Cancel, and the pre-PR checklist makes it a rule for every `showDialog`.

**Evidence.** Grep for `autofocus` across `lib/` returns one hit. The reason sheet's behaviour is asserted by `test/accessibility/semantics_fixtures_test.dart`, "a dialog takes focus and gives it back on close", which passes.

**Exact fix.** In the region editor, `autofocus` the region chip list rather than a coordinate field, so a touch reviewer does not get a keyboard on open. In the filter form, `autofocus` the first text field. Add the matching assertion to the semantics suite beside the reason sheet's.

### V-11, severity 3: no Undo and no statement that a decision is final

**Where.** Every reason sheet.

**What happens.** Pass criterion 3.4 asks for one of two things and gets neither.

**Exact fix.** The decisions here are server-side and versioned, so Undo is the wrong half of the choice: add one sentence to `ReasonForm` stating that the decision is recorded at the current version and is superseded rather than removed, and assert it in `test/widgets/reason_sheet_test.dart`.

### V-12, severity 3: "ask your administrator" names nobody

**Where.** `lib/src/auth.dart:295,298,431,433,435` and `lib/main.dart:80`.

**Exact fix.** Read a support contact from the collection configuration the scope already carries (`CollectionScope.configuration`), and render it as a named role with a mail link prefilled with the collection key and the record id. Where the configuration has none, say which role to ask for rather than "your administrator".

### V-13, severity 4: no greyscale check, no multi-select, no saved filter sets

Three criteria that are simply not built: 4.5's greyscale screenshot test, 7.3's
multi-select with bulk actions, and 7.4's named filter sets. The first is cheap
and worth doing now, because the goldens already exist: desaturate each status
golden and assert the chips are still distinguishable. The other two are features,
not defects, and belong in a plan rather than in a fix list.

### V-14, severity 4: the help screen is a card on a phone

`test/golden/images/help__compact-390x844__light.png` shows the help content in a
centred card with a scrim behind it at 390 wide, where a full-width screen would
give the glossary more measure. Cosmetic.

## Fixed in this branch

Eight trivial defects, each one a hint, a label or a padding.

| Fix | Where | Why |
|---|---|---|
| The disabled reason now reaches the control's own semantics node | `lib/src/workbench.dart` `_reasoned`, `lib/src/screens/workbench/decision_bar.dart:170`, `lib/src/screens/workbench/source_pane.dart:507`, `lib/src/screens/workbench/readings_panel.dart:352` | A bare `Semantics(hint:)` around a disabled button leaves the hint on a parent node. Four controls announced "dimmed" and nothing else |
| The merged node states its own enabled flag | the same four sites | A merge boundary keeps its own flags, so a merged node that does not say it is disabled is read, and contrast-checked, as if it were live |
| "Step " with nothing after it is now "Step not recorded" | `lib/src/operational_panel.dart:54-62` | A record whose run reported no step rendered a sentence that stopped halfway |
| The validation severity `hard` is now "Blocks clearance" | `lib/src/vocabulary.dart:33-40` | A finding read "A supported collector is required hard", naming an internal enum outside a technical-detail disclosure |
| "1 need review" is now "1 needs review" | `lib/src/screens/queue/queue_screen.dart:398-408` | The count is inside a live region and the verb has to agree with it |
| The app-bar collection switcher gained vertical padding | `lib/src/app/shell.dart:163-180` | Its floating label was clipped by 5.5 px at medium and expanded widths; now 1.5 px, with V-9 for the rest |

## What a first-time reviewer should look at

Four images, in this order. They take about two minutes and they carry the three
findings that matter.

1. **`apps/specimen_digitization/test/golden/images/workbench-readings__medium-768x1024__light__text1.0.png`**. The review screen working. The photograph on the left with its label visible, the two independent readings on the right, the segment selector, the blockers line, the decision bar pinned at the bottom. This is the bar the rest is measured against.

2. **`apps/specimen_digitization/test/golden/images/workbench-readings__compact-390x844__light__text1.0.png`**. The same screen on a phone. The yellow and black stripe about two thirds down is where the photograph should be. Finding V-1, and the reason criterion 6.1 fails.

3. **`apps/specimen_digitization/test/golden/images/workbench-history__large-1440x900__light__text1.0.png`**. The three-pane desktop layout, and the middle pane telling a reviewer that a collection with records has none. Finding V-5.

4. **`apps/specimen_digitization/test/golden/images/region-editor__large-1440x900__dark.png`**. The direct-manipulation region editor in dark mode, with the selected region's four corner handles on the photograph. This is the part of the rebuild that is furthest ahead of where the client started, and it is worth seeing before reading the defect list.

Then, for real type rather than the test font, `design/screenshots/rebuild/android-03-workbench-top.png` and `design/screenshots/rebuild/android-08-tablet-workbench.png`. Remember that those predate PR #43.
