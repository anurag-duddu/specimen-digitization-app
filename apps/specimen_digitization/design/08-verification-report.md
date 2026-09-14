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

**Third pass, `fix/verification-remainder`.** The four open defects V-7, V-8,
V-9 and V-15 are closed, and three of the seven Partial rows are now Pass.
The four rows that stay Partial stay Partial for a reason no client change can
retire, and each one names what would retire it: for 7.2, the exact endpoint
the API would have to publish; for 7.6's unused half, the exact key; for 10.3,
the two sources that are read and the fact that neither carries a value in
this repository; for 10.4, two people. One new defect was found while
measuring criterion 1.2 and fixed in the same pass, and two goldens were found
checked in stale. Both are recorded below rather than quietly corrected.

## Executive summary

The rebuild now clears the bar in six of the eight dimensions, and the two it
does not clear are held by work no client change can do: a hardware screen
reader pass, and two server capabilities that do not exist.

Of the 58 pass criteria in the heuristics audit, **54 pass, 4 are partial and
none fail**. That is up from 51, 7 and 0 at the end of the second pass, and
from 36, 14 and 8 at the end of the first.

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

The four findings the second pass left open are closed.

**V-7, the region editor giving the photograph a strip on a phone.** On a
compact window the photograph's band is floored at 240 logical pixels, and
everything that is not the photograph, the coordinate form, the region order
controls and the provenance lines, is behind one `ExpansionTile`. The editor
opens that disclosure itself when a coordinate inside it is the thing stopping
a save, so the pointer-free path WCAG 2.2 SC 2.5.7 asks for is one tap away
and never hidden behind an error nobody can see. The compact and medium
goldens also now pump the full screen route the app actually pushes below the
expanded breakpoint, rather than the dialog: the PNG this finding was written
against showed a container a phone never gets.

**V-8, disabled controls at 2.3:1.** The tokens existed and nothing passed
them to Material, so every disabled control in the product was drawn at
Material's 38 percent default, which measures 2.26:1 to 2.39:1 in light and
2.68:1 to 3.08:1 in dark against this product's own surfaces. `disabled.content`
is now `#5A625A` in light and `#A3ACA3` in dark, clearing 4.5:1 on all eight
surface roles in both modes and 3.5:1 or better over its own container, and a
new `disabled.outline` clears the 3:1 non-text floor. Six component themes take
the token layer and pass the pair on, so no call site can fall back to the
default. 93 of the 97 goldens moved.

**V-9, the collection switcher's floating label.** The app bar's switcher is a
`MenuAnchor` button rather than a form field: no floating label to clip, the
48 dp target the theme gives every button, and the whole control capped at 280
logical pixels including its padding. The drawer keeps the form field, where
there is room above the label for it.

**V-15, the environment banner at 200 percent text.** One line that truncates,
with the whole sentence on a tooltip and on the band's own semantics node, and
a disclosure that opens the rest to a second line. Two lines is the cap at
every text scale. At 390 wide and 200 percent text the band was about half the
window; it is now under a fifth of it, and the test measures that.

**Merged with pull request #42.** The approved review release landed on `main`
while this branch was open and touched the same three files: `workbench.dart`,
`workspace.dart` and the status strip. Its "reliable saves" work is kept whole
and this branch's work is layered on it rather than beside it. Two of its
rules now reach the batch path as well as the one at a time path, because a
batch cannot re-read the screen between its own calls: `reviewBatch` asks a
`stillApplies` predicate before each call, so a correction whose field moved
under the reviewer is never sent automatically against a newer revision, and
it refuses a result that is not a newer version of the same record. Its
idempotency rule is kept too: the batch prefix names the batch, and each call's
key is memoised on the record version it was sent against, so a call retried
after an uncertain answer carries the key it carried the first time. One of
this branch's own fixes, V-16, turned out to be the same defect #42 fixed more
thoroughly, so #42's version is what ships and this branch keeps only the test.

Gates: `flutter analyze --fatal-infos` clean, `flutter test` 863 passing
and 7 skipped with no failures, string lint 0 violations, color-literal
backlog 0, `flutter build web --release` succeeds.

## What was run

| Gate | Result |
|---|---|
| `flutter analyze --fatal-infos` | No issues found |
| `flutter test` | 863 passed, 7 skipped, 0 failed |
| `python3 scripts/ci/check_ui_strings.py --baseline scripts/ci/ui_strings_baseline.txt` | 100 files scanned, 0 violations, 0 baselined, 0 warnings |
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

### New in the third pass

- `test/screens/status_timing_test.dart`: the two timings criterion 1.2 states,
  measured on load more, on a save and on approve, against the routed
  application. The repository is gated on a `Completer` rather than on a delay,
  so `tester.pump(const Duration(milliseconds: 200))` advances the test clock
  by exactly the budget and the frame at 200 ms either has the progress
  affordance or the test fails.
- `test/review_batch_test.dart`: `reviewBatch`, call by call, plus the queue
  assertion that carries criterion 7.3.
- `test/reason_codes_test.dart`: the three reason sources, including the one
  that is empty against every fixture in this repository, stated as a test so
  the row cannot go stale.
- `test/widgets/term_text_test.dart`: the definition affordance and the five
  components it is applied in, plus the glossary's own shape.
- `test/app/app_bar_switcher_test.dart`: the switcher inside the toolbar at two
  size classes and four text scales.
- `test/screens/help_and_contact_test.dart`: the walkthrough against the
  controls it names, and the build-time administrator contact.
- After the merge with pull request #42, `test/review_batch_test.dart` also
  holds the two rules its "reliable saves" work added, applied to the batch
  path: a correction that no longer applies stops the batch, and a result that
  is not a newer version of the same record is refused.
- `test/region_editor_test.dart` and `test/widgets/environment_banner_test.dart`
  gained the V-7 and V-15 groups.

### Two goldens were checked in stale

`workbench-readings__medium-768x1024__{light,dark}__text2.0.png` failed on
`main` before this branch changed anything: the checked-in PNG had been
captured before the photograph finished decoding, so it showed the record with
an empty source pane. This is recorded rather than quietly corrected because it
means the second pass's claim of a fully green suite was, on this host, 766
passing and 2 failing. Pull request #42 found the same two and regenerated them
independently; the merge keeps this branch's pair, and regenerating the whole
suite after the merge changes no byte in either, which is the check that the
two renders agree.

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
| 1.2 | Server actions show progress on the control within 200 ms and a result within a second | Pass | Both timings are now measured, on the three actions the criterion is about: `test/screens/status_timing_test.dart`, "load more shows progress in 200 ms and rows within a second", "a save shows progress in 200 ms and a result within a second" and "approve shows progress in 200 ms and a result within a second". Each drives the routed application against a repository held open by a `Completer`, advances the test clock by exactly `const Duration(milliseconds: 200)` and asserts the control is reporting at that frame, then completes the gate, advances one second and asserts the result is on screen. No wall clock and no `pumpAndSettle` in either measurement, because a settle would wait however long the control took, which is the thing being measured |
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
| 7.2 | Five fields corrected on one record save with one round trip and one reason | Partial | One reason and one reviewer action, yes. One round trip, no, and not from the client: the wire takes one decision per call. What is new is `SpecimenRepository.reviewBatch` (`lib/src/models.dart`), which takes the whole set and one reason, sends them in order under a single idempotency key prefix (`<prefix>-0`, `<prefix>-1`, …), threads the record forward so each call carries the revision the one before it produced, and returns only the last result, so `WorkspaceController.mutateBatch` replaces the open record once instead of five times. A batch that stops part way throws `ReviewBatchFailure`, which carries the record as the server now has it and how many landed, so the reviewer is told what is still theirs to make rather than that the save failed. Merged with pull request #42, the batch path carries that work's two rules as well: `reviewBatch` asks a `stillApplies` predicate before each call, against the record the call before it produced, so a correction whose field moved under the reviewer is never sent automatically against a newer revision, and it refuses a result that is not a newer version of the same record. Each call's key is memoised on the version it was sent against, so a retry after an uncertain answer reuses its original key while the prefix still names the batch. `test/review_batch_test.dart`, nine tests, including "the workbench moves the screen once, on the last result", "a correction that no longer applies stops the batch" and "a result that is not a newer version is refused". **Stays Partial, and the API change that would close it:** `POST /collections/{id}/specimens/{specimen}/decisions:batch` taking `{expected_revision, reason, decisions: [{kind, target_id, after, evidence_ids}, …]}` and answering the record at the single revision all of them produced, with one `Idempotency-Key`. Nothing in the client blocks that; `reviewBatch` becomes a method on the interface and `ApiSpecimenRepository` overrides it with one call. It would also be strictly safer than what ships: one `expected_revision` for the whole set means the server, not the client, decides whether a later correction still applies |
| 7.3 | The queue supports multi-select and the non-destructive bulk actions the server permits | Partial | Not built, and deliberately not built: the repository exposes no bulk action over more than one record, so a selection model would select into nothing and a bulk control would be an affordance for a capability the server does not have. What the criterion can be held to today is the second half of its own wording, "the bulk actions the server permits", which is none, and that half is now a test rather than a claim: `test/review_batch_test.dart`, "no selection model, no select all, no bulk control", renders a six record queue and asserts there is no checkbox and no copy implying a bulk capability. Nothing was added here that would; `reviewBatch` is one record and several corrections, which is criterion 7.2. Stays Partial pending an API. The moment the server accepts a decision across records, this is a selection model over `QueueRow` and one confirmation stating the exact count, which criterion 5.2 already has a pattern for |
| 7.4 | Filter sets can be named, saved, reapplied in one action, and survive a restart | Pass | `lib/src/saved_filters.dart` keeps named sets per collection in `shared_preferences`; the filter form lists them at the top, applies one in a single tap, and deletes one from its own chip (`lib/src/search_filters.dart`, `_SavedSets`). `test/saved_filters_test.dart` covers all four, including the restart, which is read back through a second store object. Said out loud on the screen: the sets live on the device, because the collection API has nowhere to put one. `test/golden/images/filters__medium-768x1024__light.png` |
| 7.5 | Every specimen has a URL that opens it directly on web and by deep link on mobile | Pass | `test/app/routing_test.dart`, "a link to a record opens that record"; every golden in the workbench group is produced by a deep link |
| 7.6 | A reason can be chosen from configured codes or recent reasons without typing | Pass | Three groups of chips, each of which fills the field, and each named for where it came from (`lib/src/reason_codes.dart`, `ReasonForm`). **Recent reasons** now survive a restart and are kept per reviewer, not per device, so a shared imaging station does not offer one reviewer's reasons to the next: `RecentReasonStore`, `shared_preferences`, capped at ten. **The record's own reason codes**, the `reason_codes` the specimen payload publishes, are offered under their own heading in plain words, so "Human approval required" and "Mandatory unresolved: country" are one tap rather than a retype; a bare run identifier is dropped rather than offered as a reason nobody can read. **Configured codes** are read from the collection document and the profile snapshot under five key spellings, the collection winning over the profile. `test/reason_codes_test.dart`, seventeen tests, including "a chip fills the field, so no typing is needed" and "capped at ten". Said plainly: no collection document or profile this client has seen publishes a decision vocabulary, so the configured group is empty today and "no fixture in this repository publishes one" is a test that will fail the moment one does. The key this client asks the API to publish is `review_reasons` on the collection document, a list of strings or of `{code, label}` objects |

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
| 10.2 | Every domain term has a one-sentence definition reachable from where it appears | Pass | A term is now its own definition link. `lib/src/glossary.dart` carries one sentence per domain word, checked to be one sentence and dash free by test, and `TermText` draws the word with a dotted underline in the `outline` token, opens that sentence in a small sheet, and announces "Country, term, double tap for definition". Applied to the status word in `StatusChip`, the three layer names and the abstention word in `FieldRow`, the headline in `RiskMeter`, the region and the provider in `ReadingCard`, and Version, Run and Step in the status strip. The affordance is a link rather than a button, which is how WCAG 2.2 SC 2.5.8 treats an inline link and why a word inside a sentence does not have to carry a 48 dp box; everything it explains is also on the help sheet, one tap from every screen, where the entry is a full target. The help sheet's glossary is now those same sentences rather than the wire value each word came from, which is what it listed before. `test/widgets/term_text_test.dart`, fourteen tests; `test/accessibility/fixtures/workbench-fields.txt`. The field row states its own three layers explicitly, because a node with an action of its own is not merged into its parent and a row that relied on the merge would have stopped saying what it holds |
| 10.3 | Every instruction to contact an administrator names a person or a role and provides a working way to reach them, prefilled with the record context | Partial | Two sources now, not one. `lib/src/administrator_contact.dart` still reads the collection document under five key spellings, and where that carries nothing it falls back to a build-time `SPECIMEN_ADMIN_CONTACT` dart-define, which accepts `Alex Mwangi <alex@example.org>`, `Alex Mwangi, alex@example.org`, a bare address or a bare role. That closes the second of the two reasons this row was Partial for: sign-in, setup and email verification are raised before any collection is resolved, and all three now render `AdministratorContactLine` (`auth.dart`, `setup_screen.dart`, `email_verification.dart`), which reaches the build stamp when there is no scope. The line also carries the whole `mailto:` link, address and subject together, with the record identifier in the subject when a record is open, offered as selectable text rather than opened, because nothing in this app hands a URL to the platform without the reviewer choosing it. `test/screens/help_and_contact_test.dart`, "the build-time administrator contact" group, six tests; `test/screens/queue_position_test.dart`. **Stays Partial, and exactly why:** neither source carries a value at runtime in this repository. No collection document this client has seen publishes a contact, and no build configuration here passes the dart-define, so what still ships is "Your collection administrator is listed in the collection configuration for <collection>", which names a place and not a person. One `--dart-define=SPECIMEN_ADMIN_CONTACT='<name> <mail>'` in the deployment closes it with no further client change |
| 10.4 | A new reviewer completes a first review using only in-app guidance, verified with two people who have not seen the app | Partial | Not verifiable from a repository, and that is the whole of what is left: the criterion asks for two people who have not seen the app, and a test suite is not two people. The material is now complete. The second pass's note that the walkthrough named in 10.1 was missing was stale by the time it was written, because that pass shipped it; what this pass changed is that every step now names its control in the exact words on the control, in single quotes, and `walkthroughControls` lists those words once so the walkthrough and the screens cannot drift. The glossary beside it is one sentence per term rather than a wire mapping, and every term is also a link where it appears (10.2). `test/screens/help_and_contact_test.dart`, "names controls that exist, in the words the product uses", asserts each quoted control against `WorkbenchSegment.label`, `WorkbenchDecisionBar.approveLabel` and `coverageLabel`, so a control renamed without the walkthrough being renamed fails the suite |
| 10.5 | Every screen that hands work to an asynchronous process says what happens next and how to reach the result | Pass | Intake says what happens after an upload and links to the queue (`manifest_panel.dart:137-162`); the retry dialog says the outcome may be unknown (`workbench.dart:1063-1069`) |

**Totals: 54 Pass, 4 Partial, 0 Fail, over 58 criteria.**

The four that remain Partial, and what would retire each:

- **7.2**, five corrections are five calls, because the wire takes one decision
  per call. Retired by the batch endpoint named in the row.
- **7.3**, the server exposes no action across more than one record. Retired by
  an API that does.
- **10.3**, the client reads two sources for a contact and neither carries a
  value in this repository. Retired by a collection document that publishes one,
  or by one `--dart-define` at build time.
- **10.4**, two people who have not seen the app. Retired by two people.

All four are held by the server, by a deployment, or by people, rather than by
client code. That is the honest floor of what a repository can prove.

## The bar, one row each

| Dimension | Standard | Met | Evidence |
|---|---|---|---|
| Usability | All ten heuristics pass with no finding above severity 1 | **Partial** | No criterion fails and no finding is at severity 1 or 0 any more: V-1, V-2 and V-5 closed in the second pass, V-7, V-8, V-9 and V-15 in the third, which empties the open defect list of everything a client change can reach. Four criteria remain partial, and all four are held by the server, by a deployment or by people rather than by client code |
| Writing | Every string passes the checklist, no string over budget, zero em-dashes | **Yes** | `check_ui_strings.py` 0 violations over 97 files; no em-dash or en-dash anywhere in `lib/` or `test/` |
| Visual system | Zero literal colors, sizes or durations in widgets; light and dark both ship; every text pair meets AA | **Yes** | `no_color_literals_test.dart` 0 with an empty backlog; `theme/contrast_test.dart` and `accessibility/contrast_test.dart`; light and dark verified correct in all 97 goldens. `accessibility/greyscale_status_test.dart` holds the colour-blind case. The disabled state is no longer the exception: finding V-8 is closed, both disabled tokens are held to 3:1 on every surface in both modes and the content to 4.5:1, and the theme passes them to every button, chip and field so no call site can fall back to Material's 38 percent |
| Motion | Every animation is in the catalog with a reason and collapses under reduced motion | **Yes** | `test/motion/motion_tokens_test.dart`, `page_transitions_test.dart`, `reduced_motion_test.dart`; every animation site in `lib/` cites its catalog row in a comment |
| Adaptation | Every screen verified at compact, medium, expanded and large, both orientations, on iOS, Android and web | **Partial** | 97 goldens cover four widths in two themes, and every screen including the record is clean at all of them, at both text scales, with no overflow anywhere. Orientation is still covered only through the width that each orientation produces, and device coverage is still the pre-#43 screenshots in `design/screenshots/` |
| Accessibility | WCAG 2.2 AA; VoiceOver and TalkBack scripts complete unaided; keyboard-only review on web | **Partial** | The keyboard-only review passes end to end, `J` and `K` included (V-2). The evidence switcher announces as a tab list, so section 4.2 step 6 can pass (V-3). A first queue load announces that it is loading (V-4). What is left is the thing a repository cannot do: VoiceOver and TalkBack have still not been run on hardware |
| Honesty | No measurement renders as zero when missing; no score without components; no forbidden action appears enabled | **Yes** | `test/runtime_risk_test.dart`, `test/pilot_evidence_test.dart` and the wire tests all green; the fields fixture shows Unknown, Unreadable and Not present as first-class words, never blanks; the disabled-action audit in `semantics_fixtures_test.dart` finds no enabled control the server forbids, and the queue offers no bulk control for a bulk action the server does not have |
| Speed of review | One specimen to the next, including one correction with a reason, without leaving the keyboard on desktop | **Yes** | The correction and its reason were already fully keyboard-reachable. Moving to the next specimen now is too: `test/accessibility/keyboard_walkthrough_test.dart`, "J and K move to the next and the previous record", against the routed application |

## Remaining defects, ranked

Severity 0 is "a reviewer cannot do the job", 4 is "a reviewer would not notice".

Findings V-1 through V-6, V-10, V-11, V-12 and V-14 are closed and are
recorded under "Fixed in the second pass" below. V-7, V-8, V-9 and V-15 are
closed and are recorded under "Fixed in the third pass". **Nothing is open that
a client change can reach.** What follows is the one feature still waiting on
an API.

### V-13, severity 4: no multi-select and no bulk actions

Pass criterion 7.3. The repository exposes no action across more than one
record, so this is a feature waiting on an API rather than a defect: building a
selection model now would give a reviewer a way to select records and nothing
to do with the selection, and building a disabled bulk control would advertise
a capability that does not exist. Nothing in the queue implies one, and that is
now a test rather than a claim (`test/review_batch_test.dart`, "no selection
model, no select all, no bulk control").

### Nothing else is open

The four findings the second pass left open, V-7, V-8, V-9 and V-15, are closed
in this pass. One new defect was found while the timings for criterion 1.2 were
being measured, and it is closed in the same pass rather than carried:

**V-16, severity 3: a reviewer's own save reported as another reviewer's
version.** `_ReviewWorkbenchState._send` cleared its local-save flag when the
save's future completed. The host sets the new record and notifies during that
await, which schedules a build, and the await resumes in a microtask before
that build runs, so the flag was already false when `didUpdateWidget` saw the
new revision and the conflict banner fired on the reviewer's own decision. It
was invisible to every earlier test because none of them watched a save land
frame by frame; a `pumpAndSettle` runs the banner up and back down inside one
call.

Found independently in both passes. Pull request #42 fixed it more thoroughly,
by holding the flag across `WidgetsBinding.instance.endOfFrame` inside `_send`
and reading the repository's own acknowledgement rather than comparing widget
identity, so that is what ships; this branch's post-frame callback is gone and
its test stays. `test/screens/status_timing_test.dart` asserts no
`ConflictBanner` after a save and after an approve, and the batch path holds
the flag across the same frame for the same reason.

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

## Fixed in the third pass

| Finding | Fix | Evidence |
|---|---|---|
| V-7 | The compact editor floors the photograph's band at `RegionEditorBody.compactPreviewMinHeight` and puts the coordinate form, the region order controls and the provenance lines behind one `ExpansionTile`, which the editor opens itself when a coordinate inside it is what is blocking a save | `test/region_editor_test.dart`, "finding V-7, the editor on a phone", four tests; `test/golden/images/region-editor__compact-390x844__light.png`, now the full screen route the app actually pushes |
| V-8 | `ProductPalette.disabledContentLight/Dark` and `disabledOutlineLight/Dark`, wired through `specimenFilledButtonTheme`, `specimenOutlinedButtonTheme`, `specimenTextButtonTheme`, `specimenIconButtonTheme`, `specimenChipTheme` and `specimenInputTheme` | `test/theme/contrast_test.dart`, five disabled-state tests per mode, including that the content beats the Material default on every surface and still reads as quieter than `onSurfaceVariant`; design system section 3.6 carries the measured ratios; 93 of the 97 goldens moved |
| V-9 | `_CollectionSwitcher`, a `MenuAnchor` button with no floating label, capped at `AppShell.switcherMaxWidth` including its padding, carrying its own tap action on its semantics node | `test/app/app_bar_switcher_test.dart`, eleven tests: two size classes by four text scales inside the toolbar, plus the target size, the menu, and that no floating-label field is left in the app bar. `test/golden/images/queue__medium-768x1024__light.png` and `queue__expanded-1180x820__light.png` |
| V-15 | The band is one line that truncates, the whole sentence on a tooltip and on its semantics node, and a disclosure that opens it to two lines. `EnvironmentBanner.maxLines` is the cap | `test/widgets/environment_banner_test.dart`, "finding V-15, the band at 200 percent text on a phone", four tests; `test/golden/images/workbench-readings__compact-390x844__light__text2.0.png` |
| V-16 | Pull request #42's `_send`, which holds the local-save flag across `endOfFrame` and reads the repository's own acknowledgement, kept whole in the merge. The batch path holds the flag across the same frame | `test/screens/status_timing_test.dart` |
| 1.2 | Both timings measured on load more, save and approve | `test/screens/status_timing_test.dart` |
| 7.2 | `SpecimenRepository.reviewBatch` and `WorkspaceController.mutateBatch`: one reason, one key prefix naming the batch, a key per decision memoised on the version it was sent against, the record moved once, and pull request #42's still-applies and newer-version rules applied inside the batch. The row stays Partial and names the endpoint that would close it | `test/review_batch_test.dart` |
| 7.6 | `lib/src/reason_codes.dart`: configured codes, the record's own reason codes, and recent reasons kept across sessions per reviewer | `test/reason_codes_test.dart` |
| 10.2 | `lib/src/glossary.dart` and `TermText`, applied in five components | `test/widgets/term_text_test.dart` |
| 10.3 | The `SPECIMEN_ADMIN_CONTACT` build stamp, read wherever no collection document carries a contact, including on sign-in, setup and verification, with the whole `mailto:` link carrying the record. The row stays Partial because nothing sets it here | `test/screens/help_and_contact_test.dart` |
| 10.4 | Every walkthrough step names its control in the words on the control, and `walkthroughControls` keeps the two from drifting | `test/screens/help_and_contact_test.dart` |
| Two stale goldens | `workbench-readings__medium-768x1024__{light,dark}__text2.0.png` were checked in showing an empty source pane and failed on `main`. Regenerated | The suite, which is green on this host for the first time since |

## What a first-time reviewer should look at

Six images, in this order. They take about three minutes and they carry what
changed.

1. **`apps/specimen_digitization/test/golden/images/workbench-readings__medium-768x1024__light__text1.0.png`**. The review screen working. The photograph on the left with its label visible, the two independent readings on the right, the segment selector, the blockers line, the decision bar pinned at the bottom. This is the bar the rest is measured against.

2. **`apps/specimen_digitization/test/golden/images/workbench-readings__compact-390x844__light__text1.0.png`**. The same screen on a phone. Where the first pass found a yellow and black stripe, the photograph is pinned above the evidence with its view controls and its region chips. Finding V-1, closed.

3. **`apps/specimen_digitization/test/golden/images/workbench-fields__medium-768x1024__light__text2.0.png`**. The record at 200 percent text. Nothing is clipped, nothing scrolls sideways, and the photograph is still the largest thing on the screen. Pass criterion 8.5.

4. **`apps/specimen_digitization/test/golden/images/workbench-history__large-1440x900__light__text1.0.png`**. The desktop layout, and the middle pane listing the record it holds rather than telling a reviewer that a collection with records has none. Finding V-5, closed. The decision bar at the foot carries the position and the two step controls, which is finding V-2 closed as well.

5. **`apps/specimen_digitization/test/golden/images/region-editor__compact-390x844__light.png`**. The region editor on a phone, in the container a phone actually gets. The photograph is the sheet, with its overlays and its corner handles on it, and everything that is not the photograph is behind one disclosure. Finding V-7, closed. Compare it against `region-editor__large-1440x900__dark.png`, where the same editor is a dialog.

6. **`apps/specimen_digitization/test/golden/images/queue__expanded-1180x820__light.png`**. Top centre. The collection switcher is a menu button that fits the toolbar, rather than a form field whose floating label started above the window. Finding V-9, closed. The environment band above the list is also one line now rather than a paragraph, which is finding V-15.

Then, for real type rather than the test font,
`design/screenshots/rebuild/android-03-workbench-top.png` and
`design/screenshots/rebuild/android-08-tablet-workbench.png`. Remember that
those predate the motion and polish pull request and the fixes above, and
should be retaken.
