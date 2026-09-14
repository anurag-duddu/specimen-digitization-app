# 08. Verification report

Step 7 of the sequencing in [00-north-star.md](00-north-star.md): the heuristic
re-audit, the accessibility scripts, the size-class goldens and the gates, run by
someone who did not build the client.

Branch verified: `feat/motion-and-polish`, which is `main` plus the motion and
polish pull request (#43), the last of the six build steps. Toolchain Flutter
3.38.5, Dart 3.10.4. Every claim below is backed by a test name, a golden PNG, a
`file:line`, or a screenshot, and a claim with none of those is marked Partial
rather than Pass.

**Second pass, `fix/verification-defects`.** The findings below were worked
through on a branch off this one. Every row this document records as fixed
carries its new evidence in the same table, the remaining Partials keep their
reason, and the defect list at the end says what is still open and why. Where
the first pass got something wrong, including its own arithmetic, the correction
is stated rather than quietly applied.

## Executive summary

The rebuild now clears the bar in six of the eight dimensions, and the two it
does not clear are held by work no client change can do: a hardware screen
reader pass, and two server capabilities that do not exist.

Of the 58 pass criteria in the heuristics audit, **51 pass, 7 are partial and
none fail**. That is up from 36 pass, 14 partial and 8 fail.

**A correction to the first pass.** This document previously reported "56 pass
criteria, 36 pass, 15 partial and 5 fail". There are 58 criteria, and the
verdicts in the tables added up to 36, 14 and 8. The counts below are recounted
from the tables themselves.

The three findings that mattered are closed.

**V-1, the record screen laying out past its window.** The pinned source pane
was given a floor of 160 logical pixels, smaller than its own controls and
region list, so a pane drawn at the floor overflowed and the photograph was
what disappeared. The pane's own chrome is now measured rather than guessed and
taken out before the photograph's share is computed, the view controls collapse
into one menu where a row of them would not fit, and where the pane cannot be
pinned at all the whole record scrolls as one so the pixels are still on the
screen. Three further overflows the first pass had not separated out were found
and fixed in the same sweep: a placeholder column on a phone at 200 percent
text, an abstention row four pixels too wide, and the side by side panes at 200
percent text. 30 of the 97 goldens overflowed; none do. `knownWorkbenchOverflows`
is empty and the test fails on any overflow anywhere.

**V-2, `J` and `K` documented, bound and inert.** `WorkbenchScreen` now reads
the record's position out of the list the queue already holds and supplies
`onNext` and `onPrevious`. The queue does not wrap: at each end the control is
drawn, disabled, and carries the reason on its own semantics node, and the key
says that reason aloud rather than doing nothing. A deep link that opened a
record without passing through the queue asks for the list once, so the
neighbours exist.

**V-5, a deep link emptying the queue pane.** The list and the open record now
count their loads on separate generations, so neither cancels the other, and the
list pane shows placeholders until the server has answered rather than making a
claim about the collection.

Gates: `flutter analyze --fatal-infos` clean, `flutter test` 768 passing
and 7 skipped with no failures, string lint 0 violations, color-literal
backlog 0, `flutter build web --release` succeeds.

## What was run

| Gate | Result |
|---|---|
| `flutter analyze --fatal-infos` | No issues found |
| `flutter test` | 768 passed, 7 skipped, 0 failed |
| `python3 scripts/ci/check_ui_strings.py --baseline scripts/ci/ui_strings_baseline.txt` | 97 files scanned, 0 violations, 0 baselined, 0 warnings |
| `test/theme/no_color_literals_test.dart` | 0 literals outside `lib/src/theme/`, backlog empty |
| `flutter build web --release` | Built `build/web` |
| `bash scripts/ci/build_mobile.sh android` | Built `app-debug.apk` with the Android Studio JDK (first pass) |

The skips are the live-backend HTTP tests that need a running API, plus, off a
macOS host, the golden image comparisons. The three skipped assertions the first
pass added to record findings V-2, V-3 and V-4 are gone: each is now an
assertion that runs and passes, which is how those fixes are proven.

### Golden test platform

The PNGs in `test/golden/images/` are generated on macOS. A Linux CI runner
draws the same widget tree with the same deterministic test font and
antialiases it differently, which moves 1 to 4 percent of the pixels in about
half the files: a real difference in bytes and no difference at all in what the
golden is evidence of. Pull request #44 failed CI for exactly that reason, 49
files, every one a font-rendering diff.

The image comparison is therefore skipped off macOS, with the reason printed in
the skip (`goldenPlatformSkip` in `test/golden/golden_harness.dart`). Nothing
else is skipped. In particular the overflow assertions in
`size_classes_golden_test.dart`, which are what carries finding V-1, run on
every platform, as do the semantics fixtures and the keyboard walkthrough: they
are layout and semantics checks rather than pixel checks. A golden that is
skipped still built its screen and still ran every other assertion in its test.

### New in the first pass

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

### New in the second pass

- `test/screens/deep_link_queue_test.dart`: a deep link opened while the queue
  page is still out, held open by a completer rather than by a delay, so the
  assertion is about the state the reviewer actually sees mid-flight.
- `test/screens/queue_position_test.dart`: the queue's scroll offset across a
  record on a phone, the position line on the decision bar, the administrator
  contact read out of a collection document, and the help sheet's five sections.
- `test/saved_filters_test.dart`: the named filter sets, store and form.
- `test/app/error_persistence_test.dart`: a quiet poll that must not clear a
  banner, a banner that must be dismissible, and the conflict bound.
- `test/accessibility/greyscale_status_test.dart`: every status chip rendered,
  desaturated by the WCAG luminance coefficients and compared pair by pair.
- Three skipped assertions deleted, because each one now runs and passes:
  finding V-2 in the keyboard walkthrough, V-3 and V-4 in the semantics
  fixtures.

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
| 1.4 | An open specimen warns within 30 s of its revision changing, before a save | Pass | The warning is correct (`status_strip.dart:147-160`, `conflictVersion`) and the poll that raises it is the bound: `test/app/error_persistence_test.dart`, "the conflict warning cannot be later than the criterion allows", holds `queuePollInterval` at or under 30 s |
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
| 3.4 | Every saved decision offers Undo for 10 s, or says in its confirm dialog that it cannot be undone | Pass | The API exposes no reversal, so the statement is the path taken, and it is written once rather than at each call site so no sheet can ship without it: `ReasonForm.finality` (`lib/src/widgets/reason_sheet.dart`), rendered directly under the consequence in every sheet. `test/widgets/reason_sheet_test.dart`, "every sheet states that the decision cannot be undone" and "a server that offers a reversal names it instead"; `test/accessibility/fixtures/reason-sheet.txt` line 3 |
| 3.5 | Local edits inside a dialog, including delete, merge and reorder, are reversible without closing it | Pass | The region editor keeps a stack of twenty steps rather than one (`region_editor.dart`, `_undo`, `_undoDepth`), so a whole pass over one photograph is reversible; `test/region_editor_test.dart`, "delete is undoable inside the editor" and "merge is undoable and restores both regions" |
| 3.6 | An in-flight batch can be stopped, and stopping leaves no record unnamed | Pass | The Stop control and its "the file already sending finishes first" notice (`lib/src/screens/intake/manifest_panel.dart:124`, `163-175`); `test/intake_batch_test.dart` |

### 4. Consistency and standards

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 4.1 | One control type per job; tabs are `TabBar`, single-choice sets `SegmentedButton`, multi-select `FilterChip`, disclosures `ExpansionTile` | Pass | The types are used consistently, and the evidence switcher now announces as a tab list: `Semantics(role: SemanticsRole.tabBar)` around it and `SemanticsRole.tab` on each label (`lib/src/workbench.dart`). `test/accessibility/fixtures/workbench-readings.txt` lines 26-29 show `role=tabBar` with three `role=tab` children; `test/accessibility/semantics_fixtures_test.dart`, "the evidence switcher announces itself as a tab list". Stated plainly: the widget is still a `SegmentedButton` carrying tab roles rather than a Material `TabBar`, which is the alternative finding V-3 offered and which meets what section 4.2 step 6 asks a screen reader to say |
| 4.2 | Confirm buttons follow one naming pattern; one action is never named two ways | Pass | Every confirm is the verb phrase of the action, passed as `ReasonForm.action` from one place (`lib/src/screens/workbench/decision_bar.dart:69-72`); `test/accessibility/fixtures/reason-sheet.txt` |
| 4.3 | Errors appear in exactly three places by rule: field, action, screen | Pass | Field errors on the row (`fields_panel.dart:305-330`), action errors on the control (`decision_bar.dart:170-186`), screen errors in the banner (`lib/src/app/shell.dart:437`) |
| 4.4 | Every string comes from the bundle; no em-dash or en-dash | Pass | `check_ui_strings.py` 0 violations; grep for the two dashes in `lib/` returns nothing |
| 4.5 | Every status is icon plus text as well as colour, and passes a greyscale screenshot test | Pass | Icon plus text is real and verified (`status_chip.dart:1-6`, `test/widgets/status_chip_test.dart`). The greyscale screenshot test now exists: `test/accessibility/greyscale_status_test.dart` renders each status chip, desaturates it with the WCAG luminance coefficients and compares every pair, in both themes |
| 4.6 | Every target is at least 48 by 48; every icon-only control has a tooltip and a semantic label | Pass | `test/accessibility/guidelines_test.dart` and `test/accessibility/workbench_guidelines_test.dart` run the Android and iOS tap-target and labelled-target guidelines with an empty skip list; every icon-only control in the six semantics fixtures carries a tooltip |

### 5. Error prevention

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 5.1 | No hand-authored structured format where a picker is possible | Pass | Same evidence as 2.1 |
| 5.2 | A confirmation authorising work on more than one item states the exact count | Pass | "Save 5 pending changes" on both the control and the sheet; `test/widget_test.dart`, "five corrections save under one reason, in one action" |
| 5.3 | A record cannot be saved into a structurally impossible state | Pass | Supported demands content and linked evidence, and a coordinate outside the image is refused (`lib/src/workbench.dart:151-157`, `region_editor.dart`); `test/region_editor_test.dart`, `test/workflow_controls_test.dart` |
| 5.4 | Every measurement the client displays is a gate or carries an explicit override tick | Pass | The per-batch confirmation is the tick (`intake-confirm`); `test/intake_sensitivity_test.dart` |
| 5.5 | Every confirm dialog lists outstanding findings, blockers and superseded results | Pass | `ReasonForm.outstanding` (`reason_sheet.dart:30`); `test/accessibility/fixtures/reason-sheet.txt` shows the finding listed |
| 5.6 | Every button that can fail its own precondition says why; no silent no-op | Pass | The hint reaches the button's own node everywhere, and the last silent no-op is gone: `J` and `K` move along the queue, and at each end the control is drawn, disabled and carries the reason on its own node while the key announces it (`lib/src/screens/workbench/decision_bar.dart` `_Step`, `lib/src/workbench.dart` `_step`). `test/accessibility/keyboard_walkthrough_test.dart`, "J and K move to the next and the previous record"; `test/accessibility/fixtures/workbench-fields.txt`, the two disabled step controls with their hints |

### 6. Recognition rather than recall

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 6.1 | No correction without the source pixels visible on the same screen | Pass | The photograph is on the screen at every one of the four widths, in both themes, at both text scales, and there is no overflow stripe anywhere in the 97 goldens. On a phone at normal text it is pinned above the evidence and the record's own title scrolls with the evidence instead, so the pixels are what stays: `workbench-readings__compact-390x844__light__text1.0.png`. At 200 percent text the record scrolls as one and the photograph is at the top of that scroll rather than pinned, which is the honest trade at that type size: `workbench-fields__compact-390x844__light__text2.0.png` |
| 6.2 | Every identifier the user supplies is selectable from values on the record | Pass | The evidence picker offers only the record's own evidence (`lib/src/screens/workbench/evidence_picker.dart`); `test/pilot_evidence_test.dart` |
| 6.3 | One list of everything blocking clearance, each entry navigating to its control | Pass | "2 things block clearance" opens the list and each entry scrolls to its field (`lib/src/screens/workbench/blockers.dart`, `workbench.dart` `_goToBlocker`); `test/accessibility/fixtures/workbench-readings.txt` |
| 6.4 | Active filters are individually visible and individually removable without a dialog | Pass | `_ActiveFilterChips` (`queue_screen.dart:470-506`); `test/screens/queue_test.dart`, "an active filter is a chip, and removing the chip refilters" |
| 6.5 | The queue keeps its scroll position, shows the reviewer's position, and offers next and previous from inside a record | Pass | All three: the list carries a `PageStorageKey` so the offset survives being unmounted on a phone, the decision bar states "3 of 5", and next and previous are on the bar and on `J` and `K`. `test/screens/queue_position_test.dart`, "the queue keeps its scroll offset across a record" and "the decision bar states the reviewer position"; `test/accessibility/keyboard_walkthrough_test.dart`. The list pane no longer claims an empty collection on a deep link: `test/screens/deep_link_queue_test.dart` |
| 6.6 | Every row carries enough to choose between rows without opening any | Pass | Identifier, plain-language reason, status, risk and age, all in one spoken label: `test/accessibility/fixtures/queue.txt` line 14 |

### 7. Flexibility and efficiency of use

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 7.1 | Approve, confirm coverage, next, previous, switch tab, focus search, zoom and back are all on the keyboard, and `?` lists them | Pass | All eight, proven key by key in `test/accessibility/keyboard_walkthrough_test.dart`, including `J` and `K` against the routed application; `?` opens the list and the list is complete |
| 7.2 | Five fields corrected on one record save with one round trip and one reason | Partial | One reason and one user action, yes; one round trip, no. The wire takes one decision per call, so five corrections are five calls (`test/widget_test.dart:392-399` states this in the test itself) |
| 7.3 | The queue supports multi-select and the non-destructive bulk actions the server permits | Partial | Not built, and deliberately not built: the repository exposes no bulk action, so a selection model would select into nothing and a bulk control would be an affordance for a capability the server does not have. What the criterion can be held to today is the second half of its own wording, "the bulk actions the server permits", which is none: nothing in the queue implies a bulk action exists, there is no disabled bulk control and no multi-select checkbox. Stays Partial pending an API. The moment `SpecimenRepository` grows a batched review, this is a selection model over `QueueRow` and one confirmation stating the exact count, which criterion 5.2 already has a pattern for |
| 7.4 | Filter sets can be named, saved, reapplied in one action, and survive a restart | Pass | `lib/src/saved_filters.dart` keeps named sets per collection in `shared_preferences`; the filter form lists them at the top, applies one in a single tap, and deletes one from its own chip (`lib/src/search_filters.dart`, `_SavedSets`). `test/saved_filters_test.dart` covers all four, including the restart, which is read back through a second store object. Said out loud on the screen: the sets live on the device, because the collection API has nowhere to put one. `test/golden/images/filters__medium-768x1024__light.png` |
| 7.5 | Every specimen has a URL that opens it directly on web and by deep link on mobile | Pass | `test/app/routing_test.dart`, "a link to a record opens that record"; every golden in the workbench group is produced by a deep link |
| 7.6 | A reason can be chosen from configured codes or recent reasons without typing | Partial | Recent reasons are offered as chips (`reason_sheet.dart:30`, `workbench.dart` `_recentReasons`), and they are populated from this session only. Configured reason codes are not read from the profile |

### 8. Aesthetic and minimalist design

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 8.1 | No raw JSON in a default view; every dump behind a closed technical-detail disclosure, and every value also typed | Pass | `EvidenceDrawer` is closed by default and named "Technical detail" (`lib/src/widgets/evidence_drawer.dart`); it appears as a collapsed button in every workbench semantics fixture |
| 8.2 | No paragraph over 20 words in a default view; longer copy behind "Why?" | Pass | `CaveatText` splits label from explanation (`lib/src/widgets/caveat_text.dart`); `check_ui_strings.py` enforces the budgets |
| 8.3 | Every card has one job; the primary action is visible without scrolling at 1024x768 and 390x844 | Pass | The decision bar is pinned and visible at both, and the pane above it no longer overflows: `workbench-readings__medium-768x1024__light__text1.0.png` and `workbench-readings__compact-390x844__light__text1.0.png`; `test/workbench_layout_test.dart`, "the decision bar is pinned at every regime" |
| 8.4 | On a tablet in landscape the source image takes at least 40 percent of viewport height and expands to full width in one action | Pass | The 40 percent target is now measured against the photograph's own band rather than against a pane that included its controls, and the pane's chrome is taken out before the share is computed (`workbench_layout.dart`, `pinnedSourceHeight`, `sourceImageMinHeight`). The full-screen control is in every workbench fixture, and is the one control that stays when the pane is collapsed. `test/screens/workbench_scroll_test.dart`, "the photograph never takes the evidence pane below its floor" and "the photograph collapses and comes back on a phone" |
| 8.5 | Renders correctly in light and dark at 200 percent text with no clipping and no horizontal scrolling | Pass | Light and dark are correct in all 97 goldens, no golden scrolls horizontally, and none overflows: `knownWorkbenchOverflows` in `test/golden/size_classes_golden_test.dart` is empty and an overflow anywhere fails the suite. `test/screens/workbench_scroll_test.dart`, "the photograph survives 200 percent text on a phone, without an overflow" |
| 8.6 | All spacing, type sizes and semantic colours come from named tokens; no layout literal in a widget file | Pass | `test/theme/no_color_literals_test.dart` reports 0 literals outside `lib/src/theme/` with an empty backlog; `test/theme/theme_wiring_test.dart` |

### 9. Help users recognize, diagnose, and recover from errors

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 9.1 | Every error names what happened, the state the work is in, and the single next action | Pass | The stale-revision message names all three (`workspace.dart:292-295`), as does the dropped-correction notice (`status_strip.dart:206-218`). The one message that named an internal enum instead, "…is required hard", was fixed here |
| 9.2 | Every error surface carries the recovery action for that specific failure; no two classes share a generic action | Pass | Conflict offers Refresh, access failure tears the workspace down and offers a role recheck, intake failure offers per-file retry (`workspace.dart:114-124`, `manifest_panel.dart`) |
| 9.3 | Every error is attached to the object that failed | Pass | Field errors sit on the field row and are live regions (`test/accessibility/fixtures/workbench-fields.txt`, the `liveRegion` line under Collectors) |
| 9.4 | Every error is visible without scrolling from its control, in the error colour with an error icon, and announced | Pass | `Symbols.error` plus `colorScheme.error` plus `Semantics(liveRegion: true)` on the same row (`fields_panel.dart:300-330`) |
| 9.5 | No error is dismissed by a background process before the user acts; every persistent error is user-dismissible | Pass | A quiet poll no longer clears the banner; only a refresh the reviewer asked for does, and the banner carries its own Dismiss beside its recovery action (`workspace.dart` `refresh`, `lib/src/app/shell.dart` `_ErrorBanner`). `test/app/error_persistence_test.dart`, "a quiet poll does not take the banner away" and "the banner offers Dismiss beside its recovery action" |
| 9.6 | Configuration failures show a non-secret diagnostic line an administrator can act on | Pass | `lib/src/app/setup_screen.dart` and `lib/main.dart:76-82`; `test/production_startup_test.dart` |

### 10. Help and documentation

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 10.1 | A help control is at most two taps from every screen, listing shortcuts, a walkthrough, a glossary, a problem report and build information | Pass | One tap from every screen, and the sheet now carries all five: shortcuts, "A first review" in five steps (`reviewWalkthrough`), the glossary, "Report a problem" with the administrator contact and the mail subject, and "This build" with the environment, the account, the build stamp and the service mode (`lib/src/app/help_screen.dart`). `test/screens/queue_position_test.dart`, "help carries a walkthrough, the build and a way to report"; `test/golden/images/help__compact-390x844__light.png` |
| 10.2 | Every domain term has a one-sentence definition reachable from where it appears | Partial | The glossary is complete and `CaveatText` puts a "Why" beside the caveats, but a term in a row is not itself a link to its definition |
| 10.3 | Every instruction to contact an administrator names a person or a role and provides a working way to reach them, prefilled with the record context | Partial | `lib/src/administrator_contact.dart` reads a contact out of the collection document the scope already carries, under any of five published key spellings, and renders it as a named person or role with a mail address and a subject line carrying the collection and the record. It is on the help sheet and beside every in-collection message that used to say "ask your administrator" (`shell.dart`, `review_context.dart`, `operational_panel.dart`, `manifest_panel.dart`). `test/screens/queue_position_test.dart`, "the administrator contact" group. Partial for two honest reasons: the collection documents this client has seen publish no contact, so what ships today is "Your collection administrator is listed in the collection configuration for <collection>", which names a role and a place but not a person; and the sign-in and setup messages (`auth.dart`, `production_startup.dart`, `setup_screen.dart`, `main.dart`) are raised before any collection is resolved, so there is no configuration to read one from. Both close the moment a collection document carries a contact |
| 10.4 | A new reviewer completes a first review using only in-app guidance, verified with two people who have not seen the app | Partial | Not verifiable from a repository. The material a first-time reviewer would need is present except for the walkthrough named in 10.1 |
| 10.5 | Every screen that hands work to an asynchronous process says what happens next and how to reach the result | Pass | Intake says what happens after an upload and links to the queue (`manifest_panel.dart:137-162`); the retry dialog says the outcome may be unknown (`workbench.dart:1063-1069`) |

**Totals: 51 Pass, 7 Partial, 0 Fail, over 58 criteria.**

The seven that remain Partial: 1.2 (no test measures the 200 ms and the one
second), 7.2 (five corrections are five calls, because the wire takes one
decision per call), 7.3 (the server exposes no bulk action), 7.6 (configured
reason codes are not read from the profile), 10.2 (a term in a row is not
itself a link to its definition), 10.3 (no collection document publishes a
contact, and the sign-in messages are raised before a collection exists), and
10.4 (not verifiable from a repository). Four of the seven are held by the
server or by people rather than by client code.

## The bar, one row each

| Dimension | Standard | Met | Evidence |
|---|---|---|---|
| Usability | All ten heuristics pass with no finding above severity 1 | **Partial** | No criterion fails and no finding is at severity 1 or 0 any more: V-1, V-2 and V-5 are closed. Seven criteria remain partial, four of them held by the server or by people rather than by client code |
| Writing | Every string passes the checklist, no string over budget, zero em-dashes | **Yes** | `check_ui_strings.py` 0 violations over 97 files; no em-dash or en-dash anywhere in `lib/` or `test/` |
| Visual system | Zero literal colors, sizes or durations in widgets; light and dark both ship; every text pair meets AA | **Yes** | `no_color_literals_test.dart` 0 with an empty backlog; `theme/contrast_test.dart` and `accessibility/contrast_test.dart`; light and dark verified correct in all 97 goldens. `accessibility/greyscale_status_test.dart` now also holds the colour-blind case |
| Motion | Every animation is in the catalog with a reason and collapses under reduced motion | **Yes** | `test/motion/motion_tokens_test.dart`, `page_transitions_test.dart`, `reduced_motion_test.dart`; every animation site in `lib/` cites its catalog row in a comment |
| Adaptation | Every screen verified at compact, medium, expanded and large, both orientations, on iOS, Android and web | **Partial** | 97 goldens cover four widths in two themes, and every screen including the record is clean at all of them, at both text scales, with no overflow anywhere. Orientation is still covered only through the width that each orientation produces, and device coverage is still the pre-#43 screenshots in `design/screenshots/` |
| Accessibility | WCAG 2.2 AA; VoiceOver and TalkBack scripts complete unaided; keyboard-only review on web | **Partial** | The keyboard-only review passes end to end, `J` and `K` included (V-2). The evidence switcher announces as a tab list, so section 4.2 step 6 can pass (V-3). A first queue load announces that it is loading (V-4). What is left is the thing a repository cannot do: VoiceOver and TalkBack have still not been run on hardware |
| Honesty | No measurement renders as zero when missing; no score without components; no forbidden action appears enabled | **Yes** | `test/runtime_risk_test.dart`, `test/pilot_evidence_test.dart` and the wire tests all green; the fields fixture shows Unknown, Unreadable and Not present as first-class words, never blanks; the disabled-action audit in `semantics_fixtures_test.dart` finds no enabled control the server forbids, and the queue offers no bulk control for a bulk action the server does not have |
| Speed of review | One specimen to the next, including one correction with a reason, without leaving the keyboard on desktop | **Yes** | The correction and its reason were already fully keyboard-reachable. Moving to the next specimen now is too: `test/accessibility/keyboard_walkthrough_test.dart`, "J and K move to the next and the previous record", against the routed application |

## Remaining defects, ranked

Severity 0 is "a reviewer cannot do the job", 4 is "a reviewer would not notice".

Findings V-1 through V-6, V-10, V-11, V-12 and V-14 from the first pass are
closed and are recorded under "Fixed in the second pass" below. What follows is
what is still open.

### V-7, severity 2: the region editor gives the photograph little height on a phone

**Where.** `lib/src/region_editor.dart`, the body's column inside the compact
bottom sheet.

**What happens.** At 390x844 the image band is a thin strip between the region
chips above it and the coordinate field below it, which is not enough to drag a
corner handle on. The north star calls for a direct-manipulation editor on
touch; on a phone this is a coordinate form with a thumbnail.

**Evidence.** `test/golden/images/region-editor__compact-390x844__light.png`,
against `region-editor__large-1440x900__dark.png` where the same editor is
correct and the handles are usable.

**Exact fix.** On a compact window give the image an `AspectRatio` floor of the
asset's own ratio with a minimum height of roughly 240, and move the coordinate
field and the reason behind a disclosure so the photograph is the sheet's main
content rather than one row of it. Not done here: it is a redesign of the
sheet's compact form rather than a defect in the layout arithmetic, and it
belongs with a device pass on the editor.

### V-8, severity 2: disabled controls are drawn at 2.3:1

**Where.** The Material disabled state carried by the theme, seen on `Correct
label regions` and `Approve record` when the server forbids them, and now also
on the next and previous controls at the ends of the queue.

**What happens.** The reason a control is disabled is on the control's own
semantics node, so a screen reader hears it. A sighted reviewer reads it at a
contrast ratio of 2.38:1 and 2.25:1. WCAG 1.4.3 exempts inactive components, so
this is not an AA failure, but a reason nobody can read is not a reason.

**Exact fix.** Raise the disabled-state content color in
`lib/src/theme/component_themes.dart` from Material's 0.38 opacity to a token
that clears 4.5:1 against the surface, and add the pair to
`test/theme/contrast_test.dart` so it stays there. Not done here: it is a change
to every disabled control in the product at once, it moves most of the 97
goldens, and it is a design decision about how a disabled control should look
rather than a bug in a screen.

### V-9, severity 3: the collection switcher's floating label sits 1.5 px above the window

**Where.** `lib/src/app/shell.dart`, `_CollectionDropdown`.

**What happens.** An `AppBar` stretches an action to the 56 dp toolbar height.
A 48 dp outlined field, which is the minimum target size, draws its floating
label across its own top border, and the label's box then starts 1.5 px above
y 0. On a phone or a tablet the status-bar inset hides this; in a browser, where
the toolbar starts at y 0, it does not.

**Evidence.** `test/golden/images/queue__expanded-1180x820__light.png`, top
centre.

**Exact fix.** Stop using a floating-label form field as an app-bar action.
Replace the dense variant with a `MenuAnchor` showing the collection name and a
chevron, wrapped in `Semantics(label: 'Authorized collection')` and a `Tooltip`,
which fits the toolbar and keeps the 48 dp target. Not done here: it changes the
app bar on every screen and wants a device check on the switcher, which no
capture in this repository covers because no device capture was taken of an
account with more than one collection.

### V-13, severity 4: no multi-select and no bulk actions

Pass criterion 7.3. The repository exposes no bulk action, so this is a feature
waiting on an API rather than a defect: building a selection model now would
give a reviewer a way to select records and nothing to do with the selection,
and building a disabled bulk control would advertise a capability that does not
exist. Nothing in the queue implies one. The other two items the first pass
listed here, the greyscale check and named filter sets, are both built.

### V-15, severity 3: the environment banner takes most of a phone at 200 percent text

**Where.** `lib/src/widgets/environment_banner.dart`, seen through the shell.

**What happens.** At 390 wide and 200 percent text the synthetic-environment
banner wraps to eleven lines and occupies about half the window, which is why
`workbench-readings__compact-390x844__light__text2.0.png` shows the record
scrolled rather than the photograph pinned. Nothing is clipped and nothing
scrolls horizontally, so this is not a criterion failure; it is a banner that
does not adapt.

**Exact fix.** Shorten the banner to its first clause at compact widths and put
the rest behind the help sheet, or collapse it to a single line with a
disclosure. Found in this pass, so it is new here rather than carried over.
## Fixed in the first pass

Eight trivial defects, each one a hint, a label or a padding.

| Fix | Where | Why |
|---|---|---|
| The disabled reason now reaches the control's own semantics node | `lib/src/workbench.dart` `_reasoned`, `lib/src/screens/workbench/decision_bar.dart`, `lib/src/screens/workbench/source_pane.dart`, `lib/src/screens/workbench/readings_panel.dart` | A bare `Semantics(hint:)` around a disabled button leaves the hint on a parent node. Four controls announced "dimmed" and nothing else |
| The merged node states its own enabled flag | the same four sites | A merge boundary keeps its own flags, so a merged node that does not say it is disabled is read, and contrast-checked, as if it were live |
| "Step " with nothing after it is now "Step not recorded" | `lib/src/operational_panel.dart:54-62` | A record whose run reported no step rendered a sentence that stopped halfway |
| The validation severity `hard` is now "Blocks clearance" | `lib/src/vocabulary.dart:33-40` | A finding read "A supported collector is required hard", naming an internal enum outside a technical-detail disclosure |
| "1 need review" is now "1 needs review" | `lib/src/screens/queue/queue_screen.dart` | The count is inside a live region and the verb has to agree with it |
| The app-bar collection switcher gained vertical padding | `lib/src/app/shell.dart:163-180` | Its floating label was clipped by 5.5 px at medium and expanded widths; now 1.5 px, with V-9 for the rest |

## Fixed in the second pass

| Finding | Fix | Evidence |
|---|---|---|
| V-1 | The pinned pane is handed a band for its pixels rather than a height for the whole pane, and its own chrome is measured and taken out first (`workbench_layout.dart` `pinnedSourceHeight`, `sourceImageMinHeight`, `evidencePaneHardMinHeight`; `workbench.dart` `_stackedPlan`). The record's header scrolls with the evidence on a stacked layout so the photograph is what stays. Where the pane cannot be pinned, or the decision bar alone is taller than the pane, the whole record scrolls as one. Side by side, a pane scrolls above `layoutTextScrollThreshold`. The view controls collapse into one menu where a row of them would not fit | `knownWorkbenchOverflows` empty, 97 goldens clean; `test/screens/workbench_scroll_test.dart` |
| V-1, three more | A placeholder column that filled rather than scrolled (`workbench_screen.dart` `_Loading`), an abstention row four pixels too wide (`field_row.dart` `_Abstention`), and the side by side panes at 200 percent text | The same golden suite, which fails on an overflow anywhere |
| V-2 | `WorkbenchScreen` reads the record's position out of the loaded list and supplies `onNext`, `onPrevious`, their blocked reasons and the position label; `_step` announces the reason rather than doing nothing; a deep link asks for the list once | `test/accessibility/keyboard_walkthrough_test.dart`, two tests, previously skipped |
| V-3 | `SemanticsRole.tabBar` and `SemanticsRole.tab` on the evidence switcher | `test/accessibility/semantics_fixtures_test.dart`, previously skipped; `fixtures/workbench-*.txt` |
| V-4 | The invisible `LoadingAnnouncement` sends an announcement once from its state rather than hosting a live region with an empty rect | `test/widgets/skeleton_test.dart` and `test/accessibility/semantics_fixtures_test.dart`, previously skipped |
| V-5 | `_listGeneration` and `_recordGeneration`, a `recordLoading` flag of its own, and `QueuePane` gated on `listAnswered` | `test/screens/deep_link_queue_test.dart`, two tests, one of them holding the one-request budget |
| V-6 | `showAdaptiveForm` bounds the dialog's height as well as its width | `test/golden/images/filters__medium-768x1024__light.png` |
| V-10 | `autofocus` on the filter form's first field and on the region editor's region list | `lib/src/search_filters.dart`, `lib/src/region_editor.dart` |
| V-11 | `ReasonForm.finality`, stated once and rendered in every sheet | `test/widgets/reason_sheet_test.dart` |
| V-12 | `lib/src/administrator_contact.dart`, read from the collection document and rendered beside every in-collection message | `test/screens/queue_position_test.dart`. Criterion 10.3 stays Partial: see the row |
| V-14 | The help sheet is full width on a phone | `test/golden/images/help__compact-390x844__light.png` |
| 3.5 | The region editor keeps twenty undo steps rather than one | `test/region_editor_test.dart` |
| 4.5 | A real greyscale screenshot test | `test/accessibility/greyscale_status_test.dart` |
| 7.4 | Named filter sets, saved on the device | `test/saved_filters_test.dart` |
| 9.5 | A quiet poll no longer clears the banner, and the banner has its own Dismiss | `test/app/error_persistence_test.dart` |
| 10.1 | A five step walkthrough, a problem report and the build line in the help sheet | `test/screens/queue_position_test.dart` |

## What a first-time reviewer should look at

Four images, in this order. They take about two minutes and they carry what
changed.

1. **`apps/specimen_digitization/test/golden/images/workbench-readings__medium-768x1024__light__text1.0.png`**. The review screen working. The photograph on the left with its label visible, the two independent readings on the right, the segment selector, the blockers line, the decision bar pinned at the bottom. This is the bar the rest is measured against.

2. **`apps/specimen_digitization/test/golden/images/workbench-readings__compact-390x844__light__text1.0.png`**. The same screen on a phone. Where the first pass found a yellow and black stripe, the photograph is pinned above the evidence with its view controls and its region chips. Finding V-1, closed.

3. **`apps/specimen_digitization/test/golden/images/workbench-fields__medium-768x1024__light__text2.0.png`**. The record at 200 percent text. Nothing is clipped, nothing scrolls sideways, and the photograph is still the largest thing on the screen. Pass criterion 8.5.

4. **`apps/specimen_digitization/test/golden/images/workbench-history__large-1440x900__light__text1.0.png`**. The desktop layout, and the middle pane listing the record it holds rather than telling a reviewer that a collection with records has none. Finding V-5, closed. The decision bar at the foot carries the position and the two step controls, which is finding V-2 closed as well.

Then, for real type rather than the test font,
`design/screenshots/rebuild/android-03-workbench-top.png` and
`design/screenshots/rebuild/android-08-tablet-workbench.png`. Remember that
those predate the motion and polish pull request and the fixes above, and
should be retaken.
