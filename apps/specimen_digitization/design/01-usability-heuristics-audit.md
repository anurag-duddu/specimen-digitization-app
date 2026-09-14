# Usability heuristics audit: Specimen Digitization Flutter client

## How to read this

This is a Nielsen Norman Group heuristic evaluation of every screen and dialog in
`apps/specimen_digitization/lib/`. The ten heuristics and their definitions come from
https://www.nngroup.com/articles/ten-usability-heuristics/. Severity uses Nielsen's 0 to 4
scale from https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/,
where 0 is "not a usability problem", 1 is cosmetic, 2 is minor, 3 is major and important to
fix, and 4 is a catastrophe that must be fixed before release. Severity combines frequency,
impact and persistence, so a small annoyance a reviewer hits forty times an hour is rated
higher than a large annoyance they hit once. Every finding names the screen, quotes the exact
string or names the widget, gives `file:line`, states the user consequence in one sentence,
and carries a Fix line an engineer can implement without asking a follow-up question. Nothing
here is inferred from screenshots; every claim is read off the source. Requirement IDs refer to
`docs/product-requirements/PRD.md`.

### Screen inventory

| # | Screen or dialog | Owning file | Primary role |
|---|---|---|---|
| 1 | Connection setup / setup blocked | `lib/main.dart:161-242` (`_ConnectionSetup`) | All users, before any collection access |
| 2 | Magic-link bootstrap spinner | `lib/src/magic_link_screen.dart:44-46` (`EmailLinkEntry`) | All users |
| 3 | Magic-link sign-in (send link, check email, confirm email) | `lib/src/magic_link_screen.dart:49-234` (`MagicLinkSignInScreen`) | All users |
| 4 | Fixture sign-in (email plus token or password) | `lib/src/auth.dart:126-299` (`_FixtureSignInScreen`) | Developer, synthetic environment only |
| 5 | Non-staff account block | `lib/src/email_verification.dart:40-64` | All users |
| 6 | Verify your account | `lib/src/email_verification.dart:72-132` (`EmailVerificationGate`) | All users |
| 7 | Workspace shell (app bar, environment banner, runtime blockers, collection dropdown, error banner, progress bar, rail or bar) | `lib/src/workspace.dart:557-707` | All users |
| 8 | No assigned collection / access unverified | `lib/src/workspace.dart:457-482` | All users |
| 9 | Collection queue | `lib/src/workspace.dart:308-447` (`_queue`) | Reviewer, manager |
| 10 | Filters dialog | `lib/src/search_filters.dart:19-107` (`SearchFilters`) | Reviewer, manager |
| 11 | Intake | `lib/src/intake.dart:429-656` (`IntakeScreen`) | Operator |
| 12 | Before-upload image check (per manifest row) | `lib/src/capture_quality.dart:97-159` (`CaptureQualityView`) | Operator |
| 13 | Review workbench shell and Record status card | `lib/src/workbench.dart:953-1199`, `992-1110` | Reviewer |
| 14 | Source image panel | `lib/src/workbench.dart:404-620` (`_source`) | Reviewer |
| 15 | Workbench tab 1, Readings | `lib/src/workbench.dart:622-867` (`_readings`) | Reviewer |
| 16 | Workbench tab 2, Fields and evidence | `lib/src/workbench.dart:869-951` (`_fields`) plus `lib/src/evidence_panel.dart:231-346` | Reviewer |
| 17 | Workbench tab 3, History | `lib/src/audit_history.dart:270-353` (`AuditHistoryPanel`) | Reviewer, manager |
| 18 | Review context cards (server image check, classification and pinned profile) | `lib/src/review_context.dart:31-164` (`ReviewContext`) | Reviewer |
| 19 | Processing and recovery panel | `lib/src/operational_panel.dart:77-181` (`OperationalPanel`) | Operator, manager |
| 20 | Review risk panel | `lib/src/risk_assessment.dart:15-71` (`ReviewRiskPanel`) | Reviewer, manager |
| 21 | Reading alignment view (span comparison) | `lib/src/reading_alignment.dart:23-114` | Reviewer |
| 22 | Declaration provenance view | `lib/src/reading_declarations.dart:69-159` (`ReadingDeclarationView`) | Reviewer |
| 23 | Edit dialog: field correction | `lib/src/workbench.dart:94-310` (`_edit`, `kind: 'field_correction'`) | Reviewer |
| 24 | Edit dialog: transcription adjudication | `lib/src/workbench.dart:94-310` (`_edit`, `kind: 'transcription_adjudication'`) | Reviewer |
| 25 | Edit dialog: segmentation correction by raw JSON | `lib/src/workbench.dart:179-198` (`_edit`, `kind: 'segmentation_correction'`) | Reviewer (should not exist) |
| 26 | Confirm dialog: label coverage and review approval | `lib/src/workbench.dart:334-381` (`_confirm`) | Reviewer |
| 27 | Retry from checkpoint dialog | `lib/src/workbench.dart:1056-1096` | Operator, reviewer with operate rights |
| 28 | Run action dialog (pause, resume, cancel, start new run) | `lib/src/operational_panel.dart:16-75` | Operator, manager |
| 29 | Region editor dialog | `lib/src/region_editor.dart:55-318` (`RegionEditor`) | Reviewer |
| 30 | Classification dialog | `lib/src/review_context.dart:166-284` (`ClassificationDialog`) | Reviewer |
| 31 | Authority candidate selection dialog | `lib/src/evidence_panel.dart:81-154` (`_select`) | Reviewer |
| 32 | Language and script declaration dialog | `lib/src/reading_declarations.dart:161-310` (`ReadingDeclarationDialog`) | Reviewer |
| 33 | Historical read-only record | `lib/src/audit_history.dart:175-268` (`_historicalRecord`) | Reviewer, manager |
| 34 | Large-record fallback | `lib/src/large_record.dart:74-171` plus `lib/src/workbench.dart:957-987` | Reviewer, manager |
| 35 | Evidence JSON disclosure (used on 12 surfaces) | `lib/src/review_context.dart:8-29` (`EvidenceDetails`) | Reviewer |

Findings below are numbered `H<heuristic>.<n>` and referenced by that number in the severity
summary.

---

## Heuristic 1: Visibility of system status

The interface tells the user what the system is doing now, what it just did, and what state
their work is in, without being asked.

### What works

- **Workspace shell.** `LinearProgressIndicator(semanticsLabel: 'Loading collection data')`
  covers both loading and mutating (`lib/src/workspace.dart:676-679`), so screen-reader users
  are told the app is busy rather than left in silence.
- **Intake manifest.** Each row's state string is wrapped in
  `Semantics(liveRegion: true, child: Text(e.state))` (`lib/src/intake.dart:563`), so a state
  change from `'Uploading'` to `'Accepted'` is announced without focus movement.
- **Intake upload.** `LinearProgressIndicator(value: e.progress, semanticsLabel: 'Upload progress')`
  (`lib/src/intake.dart:623-627`) is a determinate bar driven by a real byte callback
  (`lib/src/intake.dart:391-393`), not a fake spinner.
- **Every async button carries a busy label.** `'Sending link…'` and `'Signing in…'`
  (`lib/src/magic_link_screen.dart:195`), `'Checking…'` (`lib/src/email_verification.dart:109`),
  `'Loading more…'` (`lib/src/workspace.dart:444`), `'Checking on server…'`
  (`lib/src/intake.dart:591`), `'Loading evidence…'` (`lib/src/evidence_panel.dart:56`),
  `'Loading complete evidence…'` (`lib/src/large_record.dart:107`).
- **Environment honesty.** The non-production banner is unmissable and states the consequence:
  `'... ENVIRONMENT {EM} fixture results are not real model processing or museum-approved records.'`
  (`lib/src/workspace.dart:603-612`).
- **Lease visibility.** `'External work is leased until ${run['lease_until']}. Retry, resume and new-run requests must wait for the lease to end.'`
  (`lib/src/operational_panel.dart:124-127`) explains why buttons are dead instead of just
  disabling them.
- **History loading is announced.** `Semantics(liveRegion: true, child: Text('Loading historical revision $_requestedRevision…'))`
  (`lib/src/audit_history.dart:289-296`).

### What fails

**H1.1 Queue, `'${_items.length} matching records loaded'` (`lib/src/workspace.dart:382`). Severity 3.**
The count reports only what the client has loaded, never how many records match; a manager
looking at "25 matching records loaded" cannot tell whether the backlog is 25 or 4,000.
*Fix:* return `total` on `SpecimenPage` (`lib/src/models.dart:122-126`) and render
`'Showing 25 of 412 matching records'`; when the server cannot count, render
`'Showing 25. More records match.'`

**H1.2 Queue, silent 20 second poll (`lib/src/workspace.dart:60-70`). Severity 3.**
`_refresh(quiet: true)` replaces `_items` wholesale with no indication that the list changed or
when it last updated, so a reviewer can lose the row they were about to tap mid-reach.
*Fix:* store `DateTime _lastRefreshed`; render `'Updated 12 seconds ago'` in the results header;
when a quiet poll returns a different id set, do not swap the list. Show a
`MaterialBanner` reading `'3 records changed. Reload the queue.'` with a Reload action.

**H1.3 Workbench, mutation feedback is 4 pixels tall and 600 pixels away (`lib/src/workspace.dart:676`, `lib/src/workbench.dart:1025-1031`). Severity 3.**
Pressing `'Record review approval'` disables the button through `widget.busy` but shows no local
progress, so on a tablet the reviewer sees nothing happen and presses again.
*Fix:* replace the button child with a `Row` containing a 16 by 16
`CircularProgressIndicator(strokeWidth: 2)` and the text `'Recording…'` while the parent's
`busy` is true.

**H1.4 Workbench, no success confirmation for any mutation (`lib/src/workspace.dart:265-300`). Severity 3.**
`_mutate` replaces `_selected` and shows nothing; the only evidence a decision was saved is the
revision integer changing in a dense subtitle, so reviewers repeat actions or re-check history.
*Fix:* on success call
`ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Approval recorded. Revision $rev. Queue: $disposition.'), duration: Duration(seconds: 6)))`.

**H1.5 Intake, no batch-level progress (`lib/src/intake.dart:351-427`). Severity 3.**
`_send` iterates serially and only the current card animates, so an operator uploading 80 files
has no idea how far through the batch they are or whether they can leave.
*Fix:* add a header `LinearProgressIndicator(value: done / total)` plus
`'Uploading 12 of 80. 3 duplicates, 1 failed.'` computed from `_entries`.

**H1.6 Intake, rejected files never appear in the manifest (`lib/src/intake.dart:196-221`). Severity 3.**
An oversized, empty or unsupported file sets a single `_error` string and `continue`s, so
selecting 30 files with 4 bad ones shows one message naming only the last bad file. PRD 9.1.5
requires an itemized manifest with accepted, duplicate, invalid, uploading and failed items.
*Fix:* create a `ManifestEntry` for every rejected file with
`state: 'Rejected: file is larger than 25 MB'` and no `file`, so the manifest is complete.

**H1.7 Workbench, an open record never refreshes (`lib/src/workspace.dart:65`). Severity 3.**
The poll guard includes `_selected == null`, so the moment a reviewer opens a specimen the app
stops watching it; they discover the record moved only when a save is rejected as a conflict.
*Fix:* poll `repository.specimen(scope, id)` every 15 seconds while a specimen is open, compare
`revision`, and render an inline `Card` with `colorScheme.errorContainer`:
`'This record changed on the server (revision 8). Reload before saving.'` plus a Reload button.

**H1.8 Workbench, processing state is frozen (`lib/src/workbench.dart:993-998`). Severity 3.**
`s.status`, stage and attempts render whatever arrived with the record, so a specimen in
`running` shows the same stage indefinitely and the operator cannot tell if it is progressing.
*Fix:* the same open-record poll as H1.7 updates stage, attempts and `next_retry_at` in place.

**H1.9 Multiple screens, raw ISO timestamps (`lib/src/workbench.dart:1000`, `lib/src/operational_panel.dart:119`, `lib/src/operational_panel.dart:126`, `lib/src/evidence_panel.dart:163`). Severity 2.**
`'Next retry: ${s.data['run']['next_retry_at']}'` prints a machine instant, so the user has to
convert timezones mentally to know if a retry is soon.
*Fix:* add `intl` and format with `DateFormat.yMMMd().add_jm()` in the device locale plus a
relative phrase: `'Next retry in about 4 minutes (2:32 PM).'`

**H1.10 Queue, disposition is not visible without reading (`lib/src/workspace.dart:420-433`). Severity 3.**
Disposition reaches the eye only as a colour on one leading icon plus the first token of a
three-line subtitle string, so scanning a 40-row queue for "Needs human review" requires reading
every row.
*Fix:* render disposition as a `Chip` with an icon and the disposition name as the second
element of the tile title row.

---

## Heuristic 2: Match between the system and the real world

The interface uses the words, units and mental model of a museum curator and a digitization
operator, not the names the API happens to use.

### What works

- **Queue chips use the product's own queue names.** `'Needs human review'`, `'Cleared'`,
  `'Deferred'`, `'Processing blocked'`, `'Processing'` (`lib/src/workspace.dart:344-349`) match
  PRD 11.10 exactly, including the correct separation of operational blocks from Deferred
  (QUE-005).
- **Intake states the domain rule plainly.** `'One photograph per specimen. Originals remain unchanged; processing continues after you leave.'`
  (`lib/src/intake.dart:444`).
- **`labelOf` (`lib/src/models.dart:25`)** converts `needs_human_review` to spaced words so the
  raw enum never reaches the eye.
- **Absence is named, not zeroed.** `'Unmeasured'` for risk (`lib/src/workspace.dart:433`,
  `lib/src/risk_assessment.dart:5-13`), `'Not measured'` for usage
  (`lib/src/operational_panel.dart:90-91`), `'Not recorded'` as the default of `textOf`
  (`lib/src/models.dart:20-21`).

### What fails

**H2.1 Filters dialog, UTC ISO instants typed by hand (`lib/src/search_filters.dart:13-14`, `45`). Severity 4.**
The labels are `'Created from (inclusive UTC)'` and `'Created before (exclusive UTC)'`, and the
validator's help is `'Use UTC, for example 2026-09-08T00:00:00Z.'`; no reviewer types an RFC 3339
instant, so the single most useful triage filter (age) is unusable in practice.
*Fix:* replace both fields with one `showDateRangePicker` launcher labelled `'Created between'`,
display local dates, and convert to UTC in the request. Keep the raw fields only under an
`ExpansionTile` titled `'Advanced (identifiers and exact timestamps)'`.

**H2.2 Filters dialog, API field names as user labels (`lib/src/search_filters.dart:4-16`). Severity 3.**
`'Asset ID'`, `'Run ID'`, `'Batch ID'`, `'Uploader ID'`, `'Profile ID'`, `'Profile version'`,
`'Blocker'` are internal identifiers a reviewer never memorizes, so the dialog offers thirteen
fields and answers none of the questions in PRD REV-009 (collection, reason, risk, age, batch,
source, script, failed rule).
*Fix:* front the dialog with the REV-009 set: a reason-code multi-select, a risk `RangeSlider`
labelled `'Risk 0 to 100'`, the date range from H2.1, an uploader picker seeded from
`CollectionScope.configuration`, and a failed-rule picker. Move the seven ID fields into the
Advanced section.

**H2.3 Workbench, `'Profile ${s.profile} · Revision ${s.revision}'` (`lib/src/workbench.dart:994`). Severity 3.**
"Revision" is version-control vocabulary; an entomologist reads it as an edit they made rather
than as the record's version number, and the same token is reused for a fetchable historical
snapshot (`lib/src/audit_history.dart:323`).
*Fix:* use `'Version 7 of this record'` in the status header and `'Saved version 7'` in the
history list; keep `revision` in the technical detail expander.

**H2.4 Processing panel, `'Actual cost: ... micro-units'` (`lib/src/operational_panel.dart:139`). Severity 2.**
"Micro-units" is not a unit any manager can convert to a budget number.
*Fix:* format as currency with `NumberFormat.simpleCurrency`: `'Cost so far: $0.04 USD'`, and
keep `'Cost not measured'` for the null case, which the code already handles correctly.

**H2.5 Processing panel, `'External work is leased until ...'` (`lib/src/operational_panel.dart:126`). Severity 3.**
"Lease" is a distributed-systems term; the operator reads it as a licensing issue.
*Fix:* `'A processing job is running. Retry, resume and new runs are unavailable until it finishes (about 3 minutes).'`

**H2.6 Intake, `'Sensitivity of new photographs'` with values `'Sensitive'` and `'Non-sensitive'` (`lib/src/intake.dart:464-471`). Severity 3.**
The 44-word explanation below it (`lib/src/intake.dart:479`) defines "Non-sensitive" as
"suitable for ordinary collection access", which restates the label rather than naming a
consequence, so an operator guesses and the default (`_newSensitive = true`,
`lib/src/intake.dart:57`) silently restricts everything.
*Fix:* `SegmentedButton<bool>` with the two options named by effect:
`'Restricted: locality and collector hidden from general access'` and
`'Open: visible to all collection staff'`.

**H2.7 Readings tab, `'≠ Differs from the first reading for this region'` (`lib/src/workbench.dart:651`). Severity 2.**
A mathematics glyph carries the most important comparison in the product, and it renders as
tofu in fonts that lack it.
*Fix:* `Row(children: [Icon(Icons.compare_arrows), Text('Differs from Reading 1')])`.

**H2.8 Source panel, two names for one region (`lib/src/workbench.dart:553` versus `lib/src/workbench.dart:584`). Severity 2.**
The overlay badge prints the raw `region_id` while the chip below prints `'Label 1'` derived from
list position, so the reviewer cannot tell that the badge and the chip refer to the same label.
*Fix:* print `'Label 1'` on both, and put the `region_id` in a `Tooltip` on the badge.

**H2.9 Source panel, `'Asset: ...'` and `'SHA-256: ...'` on the primary review surface (`lib/src/workbench.dart:597-601`). Severity 2.**
Storage identifiers sit directly under the specimen photograph, competing with the evidence.
*Fix:* move both into an `ExpansionTile` titled `'File provenance'` and relabel the hash
`'File fingerprint (SHA-256)'`.

**H2.10 Intake, `'Bring a specimen into focus'` (`lib/src/intake.dart:439`). Severity 1.**
The page heading is a camera pun on a screen that is a batch upload manifest, which costs a
first-time operator a beat of orientation.
*Fix:* `'Upload specimen photographs'`.

**H2.11 Processing panel, a missing limit is interpolated into a fraction (`lib/src/operational_panel.dart:130`). Severity 2.**
When the policy is absent the string renders as `'Steps 4 / limit unavailable'`, which reads as
a limit named "limit unavailable".
*Fix:* branch the sentence: `'Steps used: 4 of 20.'` or `'Steps used: 4. No published limit.'`

---

## Heuristic 3: User control and freedom

Users can back out of anything they started, and mistakes are reversible.

### What works

- **Every dialog has a Cancel as its first action.** `lib/src/search_filters.dart:85`,
  `lib/src/workbench.dart:258`, `lib/src/workbench.dart:363`, `lib/src/workbench.dart:1079`,
  `lib/src/region_editor.dart:273`, `lib/src/review_context.dart:262`,
  `lib/src/evidence_panel.dart:130`, `lib/src/reading_declarations.dart:289`,
  `lib/src/operational_panel.dart:52`.
- **Sign-in has an exit.** `'Cancel sign-in'` when handling a link and `'Use a different email'`
  otherwise (`lib/src/magic_link_screen.dart:213-220`), both wired to
  `MagicLinkController.changeEmail` which clears the stored address and the pending link
  (`lib/src/magic_link.dart:274-282`).
- **The image viewer is fully resettable.** `'Whole image'` clears the crop
  (`lib/src/workbench.dart:446-449`) and `'Reset image view'` restores identity transform and
  zero rotation (`lib/src/workbench.dart:438-445`).
- **Historical records are explicitly exitable.** `'Close historical record'`
  (`lib/src/audit_history.dart:260-267`) and the panel's own promise that a snapshot
  `'cannot be edited or used as the current review revision'` (`lib/src/audit_history.dart:179`).
- **Filters have a distinct clear path.** `'Clear filters'` returns an empty map rather than
  cancelling (`lib/src/search_filters.dart:89-92`).

### What fails

**H3.1 Whole app, no routing and no working back gesture (`lib/main.dart:101-137`). Severity 4.**
`MaterialApp` sets `initialRoute: '/'` and `home:` with no `routes`, `onGenerateRoute` or router
package, and "back to queue" is a `TextButton` that mutates state
(`lib/src/workspace.dart:496-501`). On web the browser back button leaves the app; on Android the
system back gesture pops the whole app instead of the specimen.
*Fix:* adopt `go_router` with `/queue`, `/queue/:specimenId`, `/intake`, `/queue/:specimenId/history`.
This restores the platform back gesture, makes a specimen linkable, and removes the
`_page`/`_selected` state machine in `_CollectionWorkspaceState`.

**H3.2 All edit dialogs, scrim tap discards unsaved work (`lib/src/workbench.dart:116`, `lib/src/workbench.dart:326`, `lib/src/workbench.dart:337`, `lib/src/workbench.dart:606`, `lib/src/workbench.dart:1056`, `lib/src/region_editor.dart` via caller, `lib/src/evidence_panel.dart:88`, `lib/src/reading_declarations.dart:143`, `lib/src/operational_panel.dart:23`). Severity 3.**
Not one `showDialog` call passes `barrierDismissible: false`, so a stray tap outside a dialog
throws away a typed literal value, a list of evidence IDs and a three-sentence reason with no
warning.
*Fix:* pass `barrierDismissible: false` on every dialog that owns a text field, and wrap each
dialog body in `PopScope(canPop: false, onPopInvokedWithResult: ...)` that shows
`'Discard this correction?'` with `Keep editing` and `Discard` when any controller is non-empty.

**H3.3 Whole app, no undo for any saved decision (`lib/src/workspace.dart:265-300`). Severity 3.**
The server versions everything, but the client offers no path to reverse an approval, a
correction or a classification change; the reviewer's only recourse is to compose the inverse
decision by hand.
*Fix:* on a successful `_mutate`, show a SnackBar with a 10 second `SnackBarAction('Undo')` that
posts the inverse decision with `reason: 'Reverted an accidental save'` prefilled and editable.
Where the server marks an action irreversible, say so in the confirm dialog instead of offering
Undo.

**H3.4 Region editor, `'Delete region'` is instant and unrecoverable (`lib/src/region_editor.dart:194-204`). Severity 3.**
The handler removes the region and sets `_selected = 0`, so the reviewer loses both the region
and their place in a multi-label specimen, with no confirmation and no undo inside the dialog.
*Fix:* keep removals in a local `List<Json> _undoStack`; render
`'Label 3 removed. Undo'` as an inline `Row` above the reason field; move selection to the
neighbouring index rather than 0.

**H3.5 Region editor, `'Merge with next'` cannot be undone (`lib/src/region_editor.dart:223-242`). Severity 3.**
The union of two bounding boxes overwrites `selected['bbox']` and discards the removed region,
so a mis-click destroys a correct segmentation the reviewer must retype in four numeric fields.
*Fix:* the same `_undoStack`, plus a single `'Undo last change'` TextButton in the dialog content
enabled whenever the stack is non-empty.

**H3.6 Intake, a selected file cannot be removed (`lib/src/intake.dart:275-307`). Severity 3.**
`_entries` is only ever appended to or updated in place; an operator who picked the wrong
photograph out of a folder must leave the screen, which loses every other selection because
`IntakeScreen` is keyed on the scope (`lib/src/workspace.dart:485`).
*Fix:* add a trailing `IconButton(icon: Icon(Icons.close), tooltip: 'Remove from manifest')` on
each row, disabled when `e.state == 'Accepted'` or the row has a live `session`.

**H3.7 Intake, an upload batch cannot be stopped (`lib/src/intake.dart:351-427`). Severity 3.**
`_send` loops over every pending entry with no cancellation signal, and the only button is
disabled while `_busy`, so an operator who realises the whole batch is wrong must wait or kill
the app.
*Fix:* add `bool _cancelRequested`; render an `OutlinedButton('Stop after this file')` in place
of the disabled upload button while busy; `break` the loop when the flag is set and mark
remaining rows `'Paused. Press upload to resume.'`

**H3.8 Workspace shell, changing collection silently closes an open specimen (`lib/src/workspace.dart:643-654`). Severity 3.**
The dropdown's `onChanged` sets `_selected = null` and `_items = []` with no confirmation, so a
reviewer mid-correction loses the record they were reading.
*Fix:* when `_selected != null`, `showDialog` first:
`'Leave FMNH-INS-004312 and switch to Fishes?'` with `Stay` and `Switch collections`.

**H3.9 Queue, two independent filter systems with one clear button (`lib/src/workspace.dart:339-379`, `lib/src/search_filters.dart:89-92`). Severity 2.**
The chip row writes `_filter` and the dialog writes `_filters`; `'Clear filters'` empties only
the second, so a reviewer who clears filters still sees a filtered queue and cannot tell why.
*Fix:* merge into one `Map<String, String>` model; render one `'Clear all filters (3)'`
`ActionChip` in the results header that clears both.

**H3.10 Queue, `'Retry / refresh'` silently discards a paged queue (`lib/src/workspace.dart:669-674`). Severity 2.**
`_refresh` resets `_nextCursor` and `_seenCursors` (`lib/src/workspace.dart:143-144`), so
pressing the banner action after a `_loadMore` failure throws away eight already-loaded pages.
*Fix:* rename the action `'Reload queue from the start'`, and add a second action
`'Retry this page'` that re-issues `_loadMore` with the retained cursor.

---

## Heuristic 4: Consistency and standards

The same thing looks and behaves the same way everywhere, and the app follows Material 3 and
platform conventions.

### What works

- **Dialog button roles are consistent.** Confirm is always `FilledButton`, cancel is always
  `TextButton`, in all nine dialogs (for example `lib/src/workbench.dart:258-296` and
  `lib/src/region_editor.dart:273-314`).
- **Minimum touch target is enforced globally.** `FilledButton.styleFrom(minimumSize: Size(48, 48))`
  and the same for outlined buttons (`lib/main.dart:115-120`) meets the Material accessibility
  minimum and matters for gloved hands in a collection room.
- **Every icon-only control has a tooltip.** `lib/src/workspace.dart:567`,
  `lib/src/workspace.dart:580`, `lib/src/workbench.dart:426`, `431`, `440`, `1175`,
  `lib/src/auth.dart:249`.
- **One input decoration for the whole app.** `InputDecorationTheme(border: OutlineInputBorder())`
  (`lib/main.dart:112-114`).

### What fails

**H4.1 Workbench, `ChoiceChip` used as a tab bar (`lib/src/workbench.dart:1118-1130`). Severity 3.**
`['Readings', 'Fields & evidence', 'History']` are rendered as selection chips in a `Wrap`, so
they carry no `tab` semantic role, no arrow-key navigation, no selected-tab indicator and no
consistent position when the row wraps at narrow widths.
*Fix:* `DefaultTabController(length: 3)` with `TabBar` and `TabBarView`, which supplies the
role, keyboard traversal and indicator without custom code. Use `'Fields and evidence'` as the
label; the ampersand is the only one in the app.

**H4.2 Two chip systems named identically (`lib/src/workbench.dart:582` versus `lib/src/region_editor.dart:84`). Severity 2.**
Both render `ChoiceChip(label: Text('Label ${n}'))`, but one navigates a crop and the other
selects an edit target, so muscle memory from the viewer produces destructive edits in the
editor.
*Fix:* keep the chips as crop navigation in the viewer; in the editor use a vertical
`ReorderableListView` of regions with a crop thumbnail per row, which also solves the reordering
buttons in H4.5.

**H4.3 Confirm-button labels differ for the same class of action. Severity 2.**
`'Save and revalidate'` (`lib/src/workbench.dart:295`), `'Select and revalidate'`
(`lib/src/evidence_panel.dart:146`), `'Save region version'` (`lib/src/region_editor.dart:313`),
`'Select profile and rerun'` (`lib/src/review_context.dart:279`), `'Record review'`
(`lib/src/workbench.dart:373`), `'Save declaration'` (`lib/src/reading_declarations.dart:306`),
`'Request retry'` (`lib/src/workbench.dart:1092`). Seven verbs for one gesture forces the user to
read every button.
*Fix:* standardise on `'Save <object>'` (`Save correction`, `Save regions`, `Save declaration`,
`Save approval`) and move the consequence ("the server reruns affected checks") into a single
line directly above the action row.

**H4.4 Four unrelated error surfaces. Severity 3.**
`MaterialBanner` (`lib/src/workspace.dart:665-675`), inline live-region `Text`
(`lib/src/intake.dart:527-534`), plain unstyled `Text` (`lib/src/region_editor.dart:263-267`,
`lib/src/large_record.dart:111-115`, `lib/src/intake.dart:597`), and a single `SnackBar`
(`lib/src/workbench.dart:317-323`). The user cannot learn where errors appear.
*Fix:* one rule, applied everywhere. Screen-level blocking failure uses a persistent `Card` with
`colorScheme.errorContainer` and a recovery action; transient action failure uses a `SnackBar`
with `Retry`; field-level failure uses that field's `errorText`.

**H4.5 Intake, `ManifestEntry.state` carries both progress and errors (`lib/src/intake.dart:18`, `364`, `386`, `408`, `416-421`). Severity 3.**
The same string field holds `'Uploading'`, `'Accepted'`, `'Duplicate {EM} existing record retained'`
and a 40-word decoder-block paragraph, so the row's status line changes shape unpredictably and
cannot be styled or filtered.
*Fix:* split into `enum ManifestState { pending, checking, uploading, accepted, duplicate, rejected, interrupted }`
plus `String? problem`. Render the enum as a `Chip` and the problem as a separate error row.

**H4.6 Queue, disposition distinguished by colour alone for two of four states (`lib/src/workspace.dart:302-307`, `420-425`). Severity 3.**
Only `cleared` gets a different glyph (`Icons.verified_outlined`); `needs_human_review`,
`deferred` and everything else share `Icons.description_outlined` and differ only in colour.
PRD 16.4 requires non-color-only status.
*Fix:* give each disposition its own icon (`verified`, `rate_review`, `schedule`, `report`) and
add the disposition name as text in the chip from H1.10.

**H4.7 Whole app, no localization layer. Severity 2.**
Every user-facing string is a Dart literal; there is no `flutter_localizations`, no ARB file and
no `AppLocalizations`. The typographic apostrophe in `'We’ll send you a sign-in link.'`
(`lib/src/magic_link_screen.dart:162`) is the only one in the app, which is a symptom of the
absent copy discipline.
*Fix:* add `flutter_localizations` and `gen-l10n`, extract every literal to `lib/l10n/app_en.arb`,
and adopt one apostrophe convention in the ARB source.

**H4.8 Em-dashes and en-dashes in user-facing strings. Severity 1.**
`lib/main.dart:205` (`'SYNTHETIC ENVIRONMENT {EM} local fixture access only; not museum-approved records.'`),
`lib/src/workspace.dart:609`, `lib/src/email_verification.dart:109`
(`'I verified my email {EM} check again'`), `lib/src/intake.dart:379`
(`'Duplicate {EM} existing record retained'`), `lib/src/intake.dart:420`
(`'Interrupted {EM} retry to resume from the server checkpoint'`), and en-dashes in
`lib/src/search_filters.dart:15-16` (`'Minimum risk (0{EN}100)'`).
*Fix:* `'SYNTHETIC ENVIRONMENT. Local fixture access only. Not museum-approved records.'`,
`'I verified my email. Check again'`, `'Duplicate. Existing record retained.'`,
`'Interrupted. Retry to resume from the server checkpoint.'`, `'Minimum risk (0 to 100)'`.

**H4.9 Intake, a dropdown for a binary choice (`lib/src/intake.dart:460-476`). Severity 1.**
`DropdownButtonFormField<bool>` with exactly two items costs two taps where Material 3 offers a
one-tap control.
*Fix:* `SegmentedButton<bool>` with the consequence-named segments from H2.6.

**H4.10 App bar has no boundary (`lib/main.dart:121-124`). Severity 1.**
`AppBarTheme(backgroundColor: Color(0xfff4f6f3), surfaceTintColor: Colors.transparent)` is
identical to `scaffoldBackgroundColor` (`lib/main.dart:107`), so the bar dissolves into the page
and scrolled content slides under it invisibly.
*Fix:* remove the `surfaceTintColor` override so Material 3 applies its scroll-under tint, or add
`shape: Border(bottom: BorderSide(color: colorScheme.outlineVariant))`.

---

## Heuristic 5: Error prevention

The design removes the conditions that let a mistake happen, rather than reporting it after.

### What works

- **Every consequential decision requires a reason before it can commit,** satisfying PRD
  REV-005: `lib/src/workbench.dart:248-250`, `lib/src/region_editor.dart:285-287`,
  `lib/src/review_context.dart:252-254`, `lib/src/evidence_panel.dart:120-122`,
  `lib/src/reading_declarations.dart:279-281`, `lib/src/operational_panel.dart:44-46`.
- **The abstention rule is enforced at the form.** A `supported` state demands content
  (`lib/src/workbench.dart:186-188`) and linked evidence
  (`lib/src/workbench.dart:232-238`), while every absence state accepts an empty value and sends
  `'value': null` (`lib/src/workbench.dart:268`). This is PRD REV-010 implemented correctly.
- **Region geometry is checked before submit.** Positive area, non-negative origin and inside the
  original image (`lib/src/region_editor.dart:289-304`).
- **Actions the server has not permitted are disabled, not hidden and then rejected.**
  `_blocked` reads `available_actions` (`lib/src/workbench.dart:56-60`) and the operational panel
  renders only permitted actions (`lib/src/operational_panel.dart:162`).
- **A live lease blocks retry, resume and reprocess** (`lib/src/workbench.dart:61-70`,
  `lib/src/operational_panel.dart:164-171`), preventing a duplicated external model call.
- **Duplicate images are caught by content hash before upload** (`lib/src/intake.dart:206`,
  `275`).
- **Pagination detects its own corruption.** A repeated cursor or a duplicate id across pages
  raises a typed failure rather than silently showing the wrong list
  (`lib/src/workspace.dart:205-219`).
- **Unknown field states disable editing** rather than letting a stale client write a state it
  does not understand (`lib/src/workbench.dart:905-908`, `917-918`).
- **The sign-in link's shape is validated before it is trusted**, including host, path, port,
  fragment and single-valued parameters (`lib/src/magic_link.dart:170-181`).

### What fails

**H5.1 Edit dialog, hand-written JSON as a segmentation editor (`lib/src/workbench.dart:179-198`). Severity 4.**
When `kind == 'segmentation_correction'`, the value field is labelled
`'Regions JSON (original pixel coordinates)'` and its only validation is
`jsonDecode(s) is! List`, so any well-formed array of anything is accepted and posted as the
specimen's label geometry. A reviewer who reaches this path can destroy segmentation with a typo.
*Fix:* delete the `segmentation_correction` branch from `_edit` entirely. `RegionEditor`
(`lib/src/region_editor.dart`) is the only correct entry point and already produces the same
payload shape (`lib/src/region_editor.dart:305-311`).

**H5.2 Retry dialog, the confirm button silently does nothing on a blank reason (`lib/src/workbench.dart:1084-1090`). Severity 3.**
`if (controller.text.trim().isNotEmpty)` guards the pop with no `Form`, no validator and no
message, so the operator presses `'Request retry'`, the dialog does not move, and nothing
explains why.
*Fix:* wrap the field in a `Form` with the app's standard validator
`'A reason is required.'` and call `form.currentState!.validate()` in `onPressed`, matching
`lib/src/workbench.dart:368-372`.

**H5.3 Intake, one checkbox authorises an unlimited batch (`lib/src/intake.dart:515-522`, `637-647`). Severity 3.**
`'I checked framing and readability'` is a single screen-level gate; one tick releases 200
photographs the operator may not have looked at, which defeats the purpose of the confirmation.
*Fix:* move the checkbox into each manifest row next to that photograph's preview. Gate the
upload button on all pending rows being confirmed and label it
`'Confirm 12 remaining photographs'` until they are.

**H5.4 Intake, measured quality problems do not gate upload (`lib/src/capture_quality.dart:135-141`, `lib/src/intake.dart:637-647`). Severity 3.**
`CaptureQuality` computes clipping fractions and neighbour contrast and prints them, but the
upload button ignores them completely, so an operator uploads a black frame and learns hours
later that the record is blocked.
*Fix:* when `darkFraction > 0.2`, `brightFraction > 0.2` or `gradient` falls below a
profile-supplied threshold, set the row to `'Check this photograph before uploading'` and require
a per-row `CheckboxListTile('Upload anyway')` whose value is sent with the intake request.

**H5.5 Queue, an exact-match field presented as search (`lib/src/workspace.dart:320-337`). Severity 3.**
`prefixIcon: Icon(Icons.search)` with `labelText: 'Search specimens'` invites partial queries,
but the hint `'Exact specimen ID; use Filters for other criteria'` is the only warning and the
zero-result state (`lib/src/workspace.dart:396`) says only
`'No records match these filters'`.
*Fix:* relabel `'Specimen ID (exact match)'`; when a non-empty query returns nothing, render
`'No record has the ID "FMNH-12". This field matches the whole ID.'` with an
`OutlinedButton('Search other criteria')` that opens the Filters dialog.

**H5.6 Region editor, every region can be deleted and saved (`lib/src/region_editor.dart:194-204`, `289-304`). Severity 3.**
The validation loop never executes on an empty list, so a reviewer can save a specimen with zero
label regions and a reason attached, which is not a state any downstream stage can interpret.
*Fix:* in the save handler, before the loop:
`if (_regions.isEmpty) { setState(() => _error = 'Keep at least one label region. To record that a label is absent, use the "Not present" state on the field instead.'); return; }`

**H5.7 Region editor, cross-field coordinate errors are unattributed (`lib/src/region_editor.dart:29-33`, `171-184`). Severity 2.**
Any unparseable coordinate in any region produces one of two generic sentences with no
indication of which of up to four fields in which of N regions is wrong, so the reviewer hunts.
*Fix:* give each coordinate field its own `validator` returning
`'Enter a whole number of pixels.'`, add
`inputFormatters: [FilteringTextInputFormatter.digitsOnly]`, and make the summary line name the
region: `'Label 3 has an invalid Right x value.'`

**H5.8 Filters dialog, the cross-field risk rule depends on typing order (`lib/src/search_filters.dart:37-40`, `75`). Severity 2.**
`_validate` reads `_values['risk_min']`, which `onChanged` writes; if the user fills max before
min, the comparison runs against an empty string and the rule silently passes.
*Fix:* move the pair comparison into the Apply handler, or call
`_form.currentState!.validate()` from both risk fields' `onChanged`.

**H5.9 Confirm dialog, approval is requested without showing what is unresolved (`lib/src/workbench.dart:334-381`). Severity 3.**
`'This records your review. All evidence and validation gates still apply; the server determines clearance.'`
tells the reviewer the server decides, but not what the server is currently unhappy about, so
approvals are recorded blind against outstanding findings.
*Fix:* render `widget.specimen.findings` inside the dialog above the reason field:
`'2 unresolved validation findings: missing locality (error), ambiguous determiner (warning). Approving does not clear them.'`

**H5.10 Classification dialog, the destructive consequence is one line among nine (`lib/src/review_context.dart:243`). Severity 3.**
`'Saving starts a new run and invalidates profile-dependent results. Previous evidence and decisions remain retained.'`
is styled identically to the four informational lines above it, so the most expensive action in
the app reads as a footnote.
*Fix:* wrap that sentence in a `Container(decoration: BoxDecoration(color: colorScheme.errorContainer, borderRadius: BorderRadius.circular(8)), padding: EdgeInsets.all(12))`
placed immediately above the action row, and enumerate what will be superseded
(`'Discards: 4 field resolutions, 2 authority lookups.'`).

**H5.11 Workbench, stale-record conflict is only detected after the work is done (`lib/src/workspace.dart:292-295`). Severity 3.**
The conflict message is excellent, but it arrives after the reviewer has typed a literal value, a
list of evidence IDs and a reason, all of which are lost with the dialog.
*Fix:* combine with H1.7. Detect the newer revision by poll, disable the save buttons, and show
the warning before the reviewer invests the work. On an unavoidable conflict, reopen the dialog
with the typed values preserved so the reviewer only re-reads the evidence.

---

## Heuristic 6: Recognition rather than recall

Everything needed for a decision is visible at the moment of the decision.

### What works

- **The remembered address returns to the sign-in field** (`lib/src/magic_link_screen.dart:78`,
  `lib/src/magic_link.dart:146`), so a reviewer completing a link on a second device does not
  have to recall which address they used.
- **Upload handles survive a restart and reconcile by checksum**
  (`lib/src/intake.dart:92-132`), so the operator does not need to remember which of 80 files
  already uploaded.
- **Region chips let the reviewer jump between crops** without remembering coordinates
  (`lib/src/workbench.dart:577-594`).
- **The character-level diff underlines exactly what differs** between two readings
  (`lib/src/workbench.dart:663-676`), removing a manual string comparison; this is the strongest
  single piece of interaction design in the app and satisfies PRD REV-002.
- **`'Filters (N)'` shows that advanced filters are active** (`lib/src/workspace.dart:367`).

### What fails

**H6.1 Edit dialog, evidence IDs must be recalled and typed (`lib/src/workbench.dart:226-239`). Severity 4.**
`'Source / evidence IDs'` with helper `'Comma-separated IDs from this specimen'` is required
whenever the state is `supported`, but the IDs live on a different tab, inside `ExpansionTile`s,
inside JSON dumps. The reviewer must memorise a hash-like identifier, close the dialog, find it,
reopen the dialog and retype it, for every corrected field.
*Fix:* replace the text field with a `Wrap` of `FilterChip`s built from
`specimen.regions`, `specimen.observations` and `specimen.evidence`, labelled in human terms
(`'Label 2 reading (claude-sonnet)'`, `'GBIF lookup for country'`). Emit the selected ids as
`evidence_ids`. Keep a `'Enter an ID manually'` escape.

**H6.2 Edit dialog, the source pixels are not visible while correcting (`lib/src/workbench.dart:116-299`). Severity 4.**
The dialog renders only form controls; the specimen photograph, the region crop and the two model
readings are all behind the modal barrier, so the reviewer types a corrected transcription from
memory of what they saw a moment ago. This is the core review task and the interface actively
prevents source comparison, contradicting the PRD 9.3.2 workbench description.
*Fix:* stop using a dialog for correction. Render an inline editor in the right-hand column with
the region crop pinned at the top, the two independent readings below it, and the editable
literal, parsed, normalized and authority fields beneath. At widths under 1000 pixels use a
`showModalBottomSheet` with `isScrollControlled: true` that still shows the crop.

**H6.3 Workbench, nothing summarises what blocks clearance. Severity 4.**
The information is split across `findings` on tab 2 (`lib/src/workbench.dart:875-883`),
`reason_codes` on the status card (`lib/src/workbench.dart:1005-1011`), `issues` as raw JSON
(`lib/src/workbench.dart:1035`), phase `findings` inside evidence cards
(`lib/src/evidence_panel.dart:273-276`) and the blocker string
(`lib/src/operational_panel.dart:105`). The reviewer must assemble the to-do list themselves on
every record, which is the single largest time cost in the workflow.
*Fix:* a `'What blocks clearance'` `Card` pinned at the top of the content column, listing one
row per unmet gate with a severity icon, the plain-language rule name, and a
`TextButton('Go to')` that switches to the owning tab and calls
`Scrollable.ensureVisible` on the item. Render `'Nothing outstanding. Approval is available.'`
when the list is empty.

**H6.4 Filters dialog, thirteen empty text fields with no examples and no memory (`lib/src/search_filters.dart:69-78`). Severity 3.**
Nothing is prefilled, nothing autocompletes and nothing persists between sessions, so every
filtered search starts from recall.
*Fix:* `Autocomplete<String>` for reason code and blocker seeded from
`CollectionScope.configuration`; a picker for uploader; persist the last-used filter set per
scope in `SharedPreferences` and offer it as `'Reuse last filters'`.

**H6.5 Queue, active filters are invisible once the dialog closes (`lib/src/workspace.dart:367`). Severity 3.**
`'Filters (3)'` states that three filters are active but not which three, so a reviewer seeing an
unexpectedly short queue must reopen a thirteen-field dialog to find out why.
*Fix:* render each active filter as an `InputChip` with `onDeleted` under the search field:
`'Risk 60 to 100'`, `'Created after 1 Sep'`, `'Reason: ambiguous_determiner'`.

**H6.6 Edit dialog, the authority identifier is typed free-hand (`lib/src/workbench.dart:218-223`). Severity 3.**
`'Authority identifier (source-qualified)'` is a bare `TextFormField`, yet the valid identifiers
for that field key are already retained and rendered by `EvidencePanel`
(`lib/src/evidence_panel.dart:183`) on a different tab.
*Fix:* replace with a `DropdownMenu<String>` populated from the retained candidates for that
field key, with `'Enter an identifier not listed'` as the last item revealing the text field.

**H6.7 Queue, no position, no next, no previous, and scroll position is lost (`lib/src/workspace.dart:491-501`). Severity 3.**
Setting `_selected = null` rebuilds the queue `ListView` from the top, so a reviewer working down
a 40-record queue returns to row 1 after every specimen and must find their place by reading IDs.
*Fix:* keep the queue and the workbench in an `IndexedStack` so the queue's scroll offset
survives; add `'Previous specimen'` and `'Next specimen'` buttons in the workbench header plus
`'Specimen 14 of 38 in this filter'`.

**H6.8 Workbench, tabs carry no counts (`lib/src/workbench.dart:1121`). Severity 2.**
The reviewer cannot tell whether "Fields & evidence" holds two findings or forty without opening
it, so every record costs a speculative tab switch.
*Fix:* with the `TabBar` from H4.1, use `Tab(child: Row(children: [Text('Fields and evidence'), Badge(label: Text('7'))]))`.

**H6.9 Queue, four facts packed into one three-line string (`lib/src/workspace.dart:433`). Severity 3.**
Status, profile, timestamp and risk are concatenated with newlines and middots inside a single
`Text`, so nothing aligns down a column and the eye cannot compare risk across rows.
*Fix:* at widths of 800 pixels or more render a fixed-column layout (ID, disposition chip, top
reason, risk, age) using a `Row` of `Expanded` cells with a header row; below that width keep a
stacked card but give each fact its own line with a label.

**H6.10 History, the revision browser gives nothing to choose by (`lib/src/audit_history.dart:321-329`). Severity 3.**
Each row is `'Revision 4'` over `'Snapshot SHA-256 ...'`, so selecting the revision that
contains a particular decision is trial and error against a 16 MiB retrieval limit.
*Fix:* include timestamp, actor and the action that created the revision in the subtitle:
`'12 Sep 2026, 2:14 PM · a.duddu@fieldmuseum.org · field correction: locality'`.

---

## Heuristic 7: Flexibility and efficiency of use

Experts get accelerators. This is a tool used for hours a day, so the cost of the common path
dominates everything else.

### What works

- **The email field submits from the keyboard.** `onFieldSubmitted`
  (`lib/src/magic_link_screen.dart:178-180`, `lib/src/auth.dart:241-243`).
- **Autofill is wired.** `autofillHints: [AutofillHints.email]` inside an `AutofillGroup`
  (`lib/src/magic_link_screen.dart:136`, `170`).
- **Search is debounced at 350 ms** rather than firing per keystroke
  (`lib/src/workspace.dart:334-335`).
- **Expensive evidence is opt-in.** `LazyEvidence` (`lib/src/evidence_panel.dart:6-67`) defers
  every raw artifact fetch behind a button, so a reviewer who does not need raw responses does
  not pay for them.
- **Large records degrade rather than fail.** `LargeRecordEvidence` pages 12,000 characters at a
  time and avoids splitting surrogate pairs (`lib/src/large_record.dart:63-81`).

### What fails

**H7.1 Whole app, no keyboard shortcuts of any kind. Severity 4.**
There is no `Shortcuts`, `Actions`, `CallbackAction`, `FocusableActionDetector` or
`LogicalKeySet` anywhere in `lib/`. PRD REV-004 requires keyboard-efficient confirmation and
correction; a reviewer on a desktop browser must mouse to every control for every record.
*Fix:* wrap `ReviewWorkbench` in `Shortcuts` plus `Actions` with:
`Ctrl+Enter` record approval, `Ctrl+K` confirm coverage, `J` and `K` next and previous specimen,
`1`, `2`, `3` tab switch, `Escape` back to queue, `Ctrl+F` focus the queue search field,
`+`, `-`, `0` zoom in, out and reset on the source viewer. Ship a `?` shortcut opening a
shortcuts dialog.

**H7.2 Workbench, every correction is a modal round trip (`lib/src/workbench.dart:94-310`). Severity 4.**
Correcting one field costs: expand the field's `ExpansionTile`, press
`'Correct supported value'`, wait for the dialog, choose a state, type the value, type the parsed
value, type the normalized value, type the authority id, type the evidence ids, type a reason,
press save, wait for the server round trip, and repeat for the next field. A specimen with eight
corrected fields costs eight of these. This is the dominant cost of the product.
*Fix:* inline editing in the fields list (see H6.2), with one shared `'Reason for these corrections'`
field at the bottom of the record and a single `'Save 5 corrections'` action that posts them as
one versioned decision. Keep per-field reasons available for the cases policy requires them.

**H7.3 Queue, no bulk actions (`lib/src/workspace.dart:413-440`). Severity 3.**
Rows are `Card`s with `onTap` only; PRD REV-008 asks for bulk non-destructive actions, so a
manager clearing 30 obviously-fine records must open each one.
*Fix:* add a selection mode toggled from the results header, `CheckboxListTile` leading on each
row, and a bottom `BottomAppBar` offering only the actions every selected record's
`available_actions` permits, with the count in the button label.

**H7.4 Queue, no saved filters (`lib/src/workspace.dart:29`). Severity 3.**
`_filters` is transient state cleared on every rebuild of the workspace, so a reviewer who works
one named slice of the backlog rebuilds it from thirteen fields every morning. PRD REV-008 asks
for saved filters.
*Fix:* persist named filter sets in `SharedPreferences` keyed by `scope.key`; render them as
`ActionChip`s beside the `'Filters'` button with a `'Save current filters'` entry.

**H7.5 Whole app, no deep link to a specimen (`lib/main.dart:101-137`). Severity 3.**
There is no per-specimen route, so a reviewer cannot send a colleague a link to the record they
need a second opinion on, and cannot bookmark a record to return to.
*Fix:* the `go_router` change in H3.1 gives `/queue/:specimenId`, which on web puts the specimen
id in the address bar for free.

**H7.6 All confirm dialogs, the reason is retyped every time (`lib/src/workbench.dart:350-357`, `lib/src/operational_panel.dart:37-47`). Severity 3.**
A reviewer confirming label coverage on 40 clean specimens types the same sentence 40 times.
*Fix:* above the free-text field, offer a `DropdownMenu` of the collection's configured reason
codes plus the user's five most recent free-text reasons as `ActionChip`s that fill the field;
keep the field editable so a specific reason is always possible.

**H7.7 Whole app, no way to reduce the guidance text for an expert. Severity 2.**
The defensive paragraphs listed in H8.4 are unconditional, so an expert who has read them once
scrolls past 200 words on every record forever.
*Fix:* a `'Show full guidance'` `SwitchListTile` in the help menu, stored in `SharedPreferences`;
when off, collapse each long paragraph to its first sentence with a `TextButton('Why?')`.

**H7.8 Source viewer, no keyboard access to zoom or pan (`lib/src/workbench.dart:430-445`, `462-464`). Severity 2.**
`InteractiveViewer` responds to pointer and pinch only; the two zoom `IconButton`s are the sole
non-pointer path and there is no keyboard pan at all.
*Fix:* bind `+`, `-` and `0` to the same `TransformationController` mutations, bind the arrow
keys to a translation of 40 logical pixels, and give the viewer a `Focus` node with a visible
focus ring.

**H7.9 Queue, next page requires a button press (`lib/src/workspace.dart:441-445`). Severity 1.**
`'Load more records'` interrupts a scan every page.
*Fix:* keep the button as the accessible and screen-reader path, and additionally call
`_loadMore` from a `ScrollController` listener when the position passes 80 percent of
`maxScrollExtent`.

---

## Heuristic 8: Aesthetic and minimalist design

Every element on screen competes with every other element. What is not needed for the decision
at hand should not be in the primary view.

### What works

- **`LazyEvidence` keeps raw artifacts out of the default render**
  (`lib/src/evidence_panel.dart:46-66`).
- **`EvidenceDetails` collapses JSON behind a single disclosure**
  (`lib/src/review_context.dart:13-28`) rather than dumping it inline.
- **The queue's empty state is disciplined:** one icon, one heading, one sentence, one action
  (`lib/src/workspace.dart:386-412`), and the heading changes to match the cause
  (`'Your collection starts with a photograph'` versus `'No records match these filters'`).

### What fails

**H8.1 Workbench, raw JSON is the primary evidence surface. Severity 4.**
`_record` (`lib/src/workbench.dart:397-402`) prints indented JSON, and it is called for validation
issues (`lib/src/workbench.dart:1035`), the blocker (`1037`), review risk (`1039`), every
disagreement (`826`), every transcription (`847`), every field (`912`) and every audit event
(`lib/src/audit_history.dart:136`, `206`, `218`, `230`, `241`). A domain expert is asked to read
a serialisation format to do their job.
*Fix:* type every one of these. A validation finding is
`ListTile(leading: severityIcon, title: Text(message), subtitle: Text(ruleName), trailing: TextButton('Fix'))`.
A disagreement is the existing `ReadingAlignmentView`. An audit event is
`'12 Sep, 2:14 PM · a.duddu · Corrected locality · "Chicago, IL" to "Cook Co., Illinois, USA"'`.
Keep exactly one `'Technical detail'` expander per object, closed by default.

**H8.2 Workbench, the Record status card has no hierarchy (`lib/src/workbench.dart:992-1110`). Severity 4.**
In one card, in source order: status, profile and revision, stage and attempts, next retry, a
dead-letter sentence, a bullet list of reason codes, two decision buttons, a JSON dump of issues,
a JSON dump of the blocker, a JSON dump of risk, then two more buttons. The two decision buttons
that are the reviewer's actual goal are buried in the middle of a wall of run internals.
*Fix:* split into three. A compact status header (disposition chip, stage, version, age) directly
under the specimen title. The `'What blocks clearance'` card from H6.3. A decision action bar
pinned to the bottom of the content column holding `'Confirm label coverage'` and
`'Record review approval'`. Move stage, attempts, retry timing and the blocker into
`OperationalPanel`, which already owns them (`lib/src/operational_panel.dart:98-127`).

**H8.3 Workbench, two dense cards sit between the reviewer and the evidence (`lib/src/workbench.dart:1111-1130`). Severity 3.**
`ReviewContext` (server image check plus classification plus pinned profile) and
`OperationalPanel` both render before the tab row, so on a tablet the reviewer scrolls past 600
pixels of processing metadata to reach the readings.
*Fix:* add a fourth tab `'Processing'` holding `OperationalPanel` and the profile half of
`ReviewContext`, shown with a warning badge only when a blocker or an available run action
exists. Keep the server image check next to the source image, where it is about the image.

**H8.4 Multiple screens, defensive paragraphs in the primary flow. Severity 3.**
`lib/src/intake.dart:479` (44 words), `lib/src/intake.dart:483` (48 words),
`lib/src/intake.dart:513` (35 words), `lib/src/intake.dart:542` (26 words),
`lib/src/intake.dart:582` (39 words), `lib/src/capture_quality.dart:148` (52 words),
`lib/src/operational_panel.dart:112` (36 words), `lib/src/review_context.dart:155`,
`lib/src/workbench.dart:768`, `lib/src/reading_declarations.dart:221`. Every one is factually
correct and every one is read once and then skipped forever, which trains the user to skip the
line that matters.
*Fix:* one sentence of 15 words or fewer in the default view, plus a `TextButton('Why?')` opening
a `showModalBottomSheet` with the full text. For example
`lib/src/intake.dart:483` becomes `'HEIC, TIFF and DNG may not preview on this device. Upload still works.'`

**H8.5 Fields tab, a JSON blob per field (`lib/src/workbench.dart:912`). Severity 3.**
`_record(f)` runs inside every field's expanded `ExpansionTile`, so the Insects profile's field
set produces one JSON dump per field on one screen.
*Fix:* render Literal, Parsed, Normalized, Authority, State and Evidence as a two-column `Table`
with `TableRow`s, and keep one `'Technical detail'` expander per field.

**H8.6 Whole workbench, every disclosure is the same grey `ExpansionTile`. Severity 3.**
`lib/src/workbench.dart:742`, `834`, `892`, `941`; `lib/src/review_context.dart:13`;
`lib/src/risk_assessment.dart:49`; `lib/src/audit_history.dart:125`, `201`, `213`, `225`, `238`;
`lib/src/capture_quality.dart:108`. The result is an undifferentiated stack of chevrons in which
the primary content and the technical appendix look identical.
*Fix:* reserve `ExpansionTile` for genuinely optional technical detail. Render the primary layers
(literal, parsed, normalized, authority) as an always-visible two-column definition list, per PRD
REV-003 which asks for them as distinct layers, not as collapsed peers.

**H8.7 Whole app, no design tokens (`lib/main.dart:105-125`). Severity 2.**
`ThemeData` sets a seed colour, a scaffold colour, a border and a button minimum size. There is
no `TextTheme` override, so typography is Material defaults; padding literals of 8, 12, 16, 20,
24 and 32 appear ad hoc (`lib/src/workspace.dart:309`, `lib/src/workbench.dart:384`, `1155`,
`lib/src/intake.dart:436`, `lib/src/audit_history.dart:163`).
*Fix:* define `abstract final class Space { static const xs = 4.0, sm = 8.0, md = 12.0, lg = 16.0, xl = 24.0, xxl = 32.0; }`
and an explicit `TextTheme` for the six roles actually used, then replace every literal.

**H8.8 Whole app, colour carries almost no meaning. Severity 3.**
The only semantic colours are four disposition colours on a list icon
(`lib/src/workspace.dart:302-307`), an amber region border (`lib/src/workbench.dart:544`), the
amber diff highlight (`lib/src/workbench.dart:672`) and the environment banner
(`lib/src/workspace.dart:606`). Error text is rendered in the default body colour at
`lib/src/region_editor.dart:266`, `lib/src/intake.dart:597` and `lib/src/audit_history.dart:299`.
*Fix:* define semantic roles for `cleared`, `needsHumanReview`, `deferred` and
`processingBlocked` as a `ThemeExtension`, apply them to the status chip in H1.10, and use
`Theme.of(context).colorScheme.error` for every error string.

**H8.9 Whole app, no dark theme (`lib/main.dart:101-125`). Severity 3.**
`MaterialApp` supplies `theme:` only, with no `darkTheme` and no `themeMode`, so a reviewer
working a six-hour shift in a dim collection room stares at a `0xfff4f6f3` page. PRD 16.4 calls
for low visual fatigue and scalable text.
*Fix:* add
`darkTheme: ThemeData(useMaterial3: true, colorScheme: ColorScheme.fromSeed(seedColor: Color(0xff174f3b), brightness: Brightness.dark))`
and `themeMode: ThemeMode.system`, then remove the two hard-coded light colours at
`lib/main.dart:107` and `lib/main.dart:122` in favour of `colorScheme.surface`.

**H8.10 Source panel, the primary evidence is locked to 380 pixels (`lib/src/workbench.dart:452-453`). Severity 3.**
`Container(height: 380)` is fixed regardless of viewport, so on a tablet in landscape the
specimen photograph, which is the whole point of the workbench, occupies a fifth of the screen
while metadata fills the rest. PRD REV-001 makes the source image and its overlays a P0.
*Fix:* in the wide branch (`lib/src/workbench.dart:1181-1189`), make the outer layout a bounded
`Row` rather than a `SingleChildScrollView`, give the source pane `Expanded` height with
`ConstrainedBox(minHeight: 420)`, and scroll only the content column. Add a
`'Expand image'` toggle that gives the source the full width.

---

## Heuristic 9: Help users recognize, diagnose, and recover from errors

Errors are stated in plain language, name the actual problem, and offer the action that fixes it.

### What works

- **Messages name a cause and an action, without codes.**
  `'The local synthetic server is unavailable. Reconnect the demo server and refresh. Collection permissions could not be checked.'`
  (`lib/src/workspace.dart:131`); `'Page cursor repeated. Refresh the queue.'`
  (`lib/src/workspace.dart:210`);
  `'This sign-in link has expired or was already used. Request a new link.'`
  (`lib/src/magic_link.dart:295`).
- **Provider error codes are translated, never surfaced.** `authErrorMessage`
  (`lib/src/auth.dart:409-424`) and `emailLinkError` (`lib/src/magic_link.dart:292-308`) map every
  Firebase code to a sentence.
- **The conflict message is exemplary.**
  `'This record changed while you were reviewing. Your decision was not saved. Refresh evidence and compare the current version before trying again.'`
  (`lib/src/workspace.dart:293`) states what happened, what did not happen, and what to do.
- **Errors are announced to assistive technology.** `Semantics(liveRegion: true)` wraps the
  workspace banner (`lib/src/workspace.dart:667`), the intake error
  (`lib/src/intake.dart:528`), history errors (`lib/src/audit_history.dart:299`, `331`), lazy
  evidence errors (`lib/src/evidence_panel.dart:63`), setup errors (`lib/main.dart:227`) and
  sign-in messages (`lib/src/magic_link_screen.dart:186`,
  `lib/src/email_verification.dart:95`).
- **A failed lazy load relabels its own retry.** `'Retry ${widget.label.toLowerCase()}'`
  (`lib/src/evidence_panel.dart:59`).

### What fails

**H9.1 Workspace, one recovery action for every error class (`lib/src/workspace.dart:669-674`). Severity 3.**
`'Retry / refresh'` is offered for network failures, 401 and 403 denials, pagination corruption
and 5xx alike, and refreshing is the wrong action for a denial whose own message says
`'Sign out and sign in with the current fixture token'` (`lib/src/workspace.dart:127`).
*Fix:* carry the recovery on the failure. Add `List<BannerAction> actions` to the error state and
map: 401 or 403 to `'Sign in again'`; `network` or `timeout` to `'Retry'`; `pagination` to
`'Reload queue'`; 5xx to `'Retry'` plus `'Contact administrator'`.

**H9.2 Workspace, the error banner cannot be dismissed (`lib/src/workspace.dart:665-675`). Severity 2.**
`MaterialBanner` is rendered whenever `_error != null` with a single action and no close control,
so a `_loadMore` failure occupies the top of the screen indefinitely while the queue is perfectly
usable.
*Fix:* add `TextButton('Dismiss')` to `actions` that sets `_error = null`.

**H9.3 Workspace, an unread error can vanish on a background poll (`lib/src/workspace.dart:167`). Severity 2.**
A successful quiet `_refresh` sets `_error = null`, so an error raised at second 19 disappears at
second 20 before the user has read it.
*Fix:* clear `_error` only on an explicit user-initiated refresh, or timestamp it and keep it for
a minimum of 8 seconds.

**H9.4 Intake, errors are detached from the file that caused them (`lib/src/intake.dart:196-221`, `527-534`). Severity 3.**
`_error` is one screen-level string; the filename appears only inside the message text, and each
new rejection overwrites the previous one.
*Fix:* the per-file manifest rows from H1.6, each carrying its own `problem` string, rendered in
`colorScheme.error` next to that file's name.

**H9.5 Region editor, the error is invisible where it appears (`lib/src/region_editor.dart:263-267`). Severity 3.**
`Text(_visibleError!)` renders in the default body colour at the very bottom of a 680 pixel
scrollable dialog with no icon, no scroll-to and no field focus, so pressing Save appears to do
nothing.
*Fix:* render as
`Row(children: [Icon(Icons.error_outline, color: cs.error), Text(_visibleError!, style: TextStyle(color: cs.error))])`
and call `Scrollable.ensureVisible` on its key when it first becomes non-null.

**H9.6 Region editor, the message does not identify the offending value (`lib/src/region_editor.dart:29-33`). Severity 3.**
`'Coordinates must be whole pixel numbers.'` and
`'Correct invalid pixel coordinates before saving.'` cover any number of bad values in any number
of regions.
*Fix:* per-field `errorText` (see H5.7) plus a summary that names the region and the field, with
a `TextButton` that selects that region.

**H9.7 Startup, every failure collapses to one sentence (`lib/main.dart:70-74`, `lib/src/production_startup.dart:53-58`). Severity 3.**
A missing API URL, a failed App Check activation and an invalid HTTPS scheme all become either
`'Application setup could not be completed. Ask your administrator to check Firebase and the API configuration.'`
or `collectionPendingMessage` (`'Collection access is still being set up. Please try again later or contact your administrator.'`),
so an administrator receiving a screenshot cannot tell which of five configuration values is
wrong. Note that `ConnectionConfig.validate` already produces four precise, non-secret messages
(`lib/src/connection_config.dart:27-42`) which `initializeProduction` discards.
*Fix:* keep the friendly sentence, and add a second `SelectableText` line with the non-secret
diagnostic: `'Setup step: App Check activation.'` Propagate the `FormatException.message` from
`config.validate` instead of swallowing it at `lib/src/production_startup.dart:53`.

**H9.8 Intake, a cancelled file picker is reported as a failure (`lib/src/intake.dart:175-181`). Severity 2.**
The `catch (_)` covers everything and emits
`'Capture or file selection unavailable. Check device permissions or select files instead.'`,
which is wrong and alarming when the user simply dismissed the picker.
*Fix:* return silently when the picker yields an empty list without throwing; distinguish a
`PlatformException` with a permission code and give that case an
`'Open settings'` action.

**H9.9 Source image, error states offer no recovery (`lib/src/source_pixels.dart:25-27`, `31-40`, `lib/src/workbench.dart:456-460`). Severity 2.**
`'Source preview unavailable. Refresh to retry.'`, `'Source geometry is unavailable. Refresh evidence.'`,
`'Invalid source transform.'` and `'Preview unavailable. Refresh to renew source access.'` all
instruct the user to refresh, but the refresh control is an unlabelled icon 300 pixels above in
the workbench header (`lib/src/workbench.dart:1173`).
*Fix:* pass `onRefresh` into `SourcePixels` and render each error as an icon, the message and an
`OutlinedButton('Refresh evidence')` in place.

**H9.10 Large record, the error is styled but orphaned (`lib/src/large_record.dart:111-115`). Severity 2.**
The message uses `colorScheme.error` correctly, but the `'Load complete evidence'` button is
hidden by the same `if (_artifact == null)` branch only when loading succeeded, and there is no
explicit retry affordance labelled as such.
*Fix:* relabel the button `'Retry loading complete evidence'` when `_error != null`, matching the
pattern `LazyEvidence` already uses at `lib/src/evidence_panel.dart:59`.

**H9.11 Workbench, the only `SnackBar` in the app is used for a recoverable configuration error (`lib/src/workbench.dart:317-323`). Severity 2.**
`'Collection configuration is unavailable. Refresh collection access.'` is transient and
dismissible, yet it blocks the classification correction entirely and offers no refresh action.
*Fix:* add `SnackBarAction(label: 'Refresh', onPressed: widget.onRefresh)`.

---

## Heuristic 10: Help and documentation

The user can find out how to do their job without leaving the app or asking a colleague.

### What works

- **The first-run question is answered on the sign-in screen.**
  `'First time here? Your verified staff email creates your sign-in account. Collection access is managed separately by your collection administrator.'`
  (`lib/src/magic_link_screen.dart:222-224`) states both what happens automatically and who to ask.
- **The no-collection state is a complete instruction plus the action.**
  `'Your account has no assigned collection. Ask your administrator to grant a collection role, then check access again.'`
  with a `'Check access again'` button (`lib/src/workspace.dart:470-478`).
- **Help arrives at the moment it applies.** The value field's `helperText` changes with the
  evidence state: `'Preserve literal text; do not fill missing evidence.'` versus
  `'Absence is recorded as a state, not a fabricated value.'` (`lib/src/workbench.dart:182-184`).
- **The Filters dialog explains its own semantics.**
  `'All filters must match. Risk filters exclude unmeasured records; risk does not establish clearance.'`
  (`lib/src/search_filters.dart:67`).

### What fails

**H10.1 Whole app, there is no help entry point (`lib/src/workspace.dart:560-583`). Severity 3.**
The app bar has exactly two actions, Refresh and Sign out. There is no help menu, no about
screen, no build or environment display and no way to report a problem, so a stuck user has no
in-app path at all.
*Fix:* add a `PopupMenuButton` with `'Keyboard shortcuts'`, `'How a review works'`,
`'Glossary'`, `'Report a problem'` and `'About'` (build number, API environment, signed-in
address).

**H10.2 Whole app, domain terms are used with no definition. Severity 3.**
`'Deferred'` and `'Processing blocked'` (`lib/src/workspace.dart:347-348`), `'Uncalibrated'`
(`lib/src/workspace.dart:433`, `lib/src/risk_assessment.dart:30`), `'Adjudicated literal transcription'`
(`lib/src/workbench.dart:836`), `'Superseded human declaration'`
(`lib/src/reading_declarations.dart:112`), `'Authority'`, `'Profile'`, `'Revision'`. Each is a
precise term with a policy behind it and none of them can be looked up.
*Fix:* a `Glossary` map keyed by term; render each first occurrence on a screen as the term plus
a 16 pixel `Icons.info_outline` `IconButton` opening a `showModalBottomSheet` with the
definition and a link to the relevant PRD section. One glossary page in the help menu lists all
of them.

**H10.3 Multiple screens, `'contact your administrator'` with no way to do so. Severity 3.**
`lib/main.dart:73`, `lib/src/workspace.dart:617`, `lib/src/intake.dart:418`,
`lib/src/auth.dart:416`, `lib/src/production_startup.dart:6`, plus at least five messages in
`lib/src/api_repository.dart` (lines 204, 334, 453, 473, 767). The user is told to contact a
person who is never named and never reachable.
*Fix:* read the administrator name and address from `CollectionScope.configuration` and render a
single `'Contact your collection administrator'` button on every error surface that says it,
opening a prefilled mail composer with the specimen id, revision and error text.

**H10.4 Queue, the reviewer's core task is never explained (`lib/src/workspace.dart:316-318`). Severity 2.**
`'Review the evidence. Resolve uncertainty. Keep every decision traceable.'` is a motto, not
instruction; nothing tells a new reviewer what the three workbench tabs are for or what
"Confirm label coverage" commits them to.
*Fix:* a dismissible `'How a review works'` `Card` shown once per user, with four steps named
exactly as the UI names them: Compare readings, Correct fields, Confirm coverage, Record
approval. Keep it reachable from the help menu afterwards.

**H10.5 Intake, the quality checklist is a run-on sentence in the wrong place (`lib/src/intake.dart:513`). Severity 2.**
`'Before submitting: check sharp focus, readable smallest text, even exposure, no glare, and every label inside the frame.'`
is five separate checks compressed into one line, positioned above the file picker rather than
beside the photograph being judged.
*Fix:* render the five checks as a `Column` of `Icon` plus `Text` rows inside each manifest
card, next to that photograph's preview, and pair them with the per-row confirmation from H5.3.

**H10.6 Intake, nothing explains what happens next (`lib/src/intake.dart:444`). Severity 2.**
`'processing continues after you leave'` is the only statement about the pipeline; there is no
estimate, no count and no route to the results.
*Fix:* when the batch finishes, replace the upload button with
`'All 12 photographs accepted. They appear in the queue as processing finishes.'` and a
`FilledButton('Go to queue')` that sets the workspace page to 0.

**H10.7 Large-record fallback, the limitation is explained but the remedy is not (`lib/src/large_record.dart:95`). Severity 2.**
`'The standard workspace exceeds its response limit. Complete evidence is available as a read-only artifact. Field edits and approval are unavailable in this view.'`
tells the reviewer the record cannot be reviewed but not what to do about it.
*Fix:* add the actual next step, for example
`'To edit this record, ask a collection administrator to archive superseded run evidence.'`, with
the contact button from H10.3.

**H10.8 Whole app, keyboard behaviour will be undiscoverable once it exists. Severity 2.**
This is the documentation half of H7.1. Shortcuts that are not listed are shortcuts nobody uses.
*Fix:* ship the shortcuts dialog with the shortcuts, bound to `?` and listed in the help menu,
generated from the same `Map<ShortcutActivator, Intent>` so it cannot drift.

---

## Severity summary: all severity 3 and 4 findings, ranked

### Severity 4, catastrophes

| Rank | ID | Heuristic | Screen | Finding |
|---:|---|---|---|---|
| 1 | H6.2 | 6 Recognition | Edit dialog | Source pixels and model readings are hidden behind the modal while the reviewer types the corrected transcription |
| 2 | H8.1 | 8 Minimalist | Workbench, history | Raw JSON is the primary rendering for issues, blockers, risk, disagreements, fields and audit events |
| 3 | H7.2 | 7 Efficiency | Workbench | Every field correction is a full modal round trip; eight fields means eight modals |
| 4 | H6.3 | 6 Recognition | Workbench | Nothing summarises what blocks clearance; the reviewer assembles the list from five places per record |
| 5 | H6.1 | 6 Recognition | Edit dialog | Required evidence IDs must be memorised from another tab and typed by hand |
| 6 | H7.1 | 7 Efficiency | Whole app | No keyboard shortcuts at all, against PRD REV-004 |
| 7 | H8.2 | 8 Minimalist | Workbench Record status card | Thirteen unrelated elements in one card; the two decision buttons are buried mid-stack |
| 8 | H3.1 | 3 Control | Whole app | No routing; browser and system back gestures leave the app instead of returning to the queue |
| 9 | H5.1 | 5 Prevention | Edit dialog, segmentation | Label geometry is editable as free-text JSON validated only as "is a list" |
| 10 | H2.1 | 2 Real world | Filters dialog | Date filters require hand-typed UTC RFC 3339 instants |

### Severity 3, major

| ID | Heuristic | Screen | Finding |
|---|---|---|---|
| H1.1 | 1 Status | Queue | Loaded count is presented as a match count |
| H1.2 | 1 Status | Queue | Silent 20 second poll swaps the list with no notice or timestamp |
| H1.3 | 1 Status | Workbench | Mutation feedback is a 4 pixel bar far from the pressed button |
| H1.4 | 1 Status | Workbench | No success confirmation for any saved decision |
| H1.5 | 1 Status | Intake | No batch-level upload progress |
| H1.6 | 1 Status | Intake | Rejected files never appear in the manifest, against PRD 9.1.5 |
| H1.7 | 1 Status | Workbench | An open record is never refreshed; staleness surfaces only as a save conflict |
| H1.8 | 1 Status | Workbench | Stage and attempts are frozen for a running record |
| H1.10 | 1 Status | Queue | Disposition is not scannable without reading each row |
| H2.2 | 2 Real world | Filters dialog | API identifiers used as user-facing filter labels; PRD REV-009 criteria absent |
| H2.3 | 2 Real world | Workbench | "Revision" used for both record version and historical snapshot |
| H2.5 | 2 Real world | Processing panel | "Lease" exposed as user vocabulary |
| H2.6 | 2 Real world | Intake | Sensitivity options named by category, not by consequence |
| H3.2 | 3 Control | All dialogs | Scrim tap discards unsaved corrections with no warning |
| H3.3 | 3 Control | Whole app | No undo for any saved decision |
| H3.4 | 3 Control | Region editor | Delete region is instant, unconfirmed and unrecoverable |
| H3.5 | 3 Control | Region editor | Merge with next is unrecoverable inside the dialog |
| H3.6 | 3 Control | Intake | A selected file cannot be removed from the manifest |
| H3.7 | 3 Control | Intake | An upload batch cannot be stopped |
| H3.8 | 3 Control | Workspace shell | Switching collection silently closes an open specimen |
| H4.1 | 4 Consistency | Workbench | ChoiceChip used as a tab bar; no tab role, no keyboard traversal |
| H4.4 | 4 Consistency | Whole app | Four unrelated error surfaces |
| H4.5 | 4 Consistency | Intake | One string field carries both progress and error text |
| H4.6 | 4 Consistency | Queue | Two dispositions distinguished by colour alone, against PRD 16.4 |
| H5.2 | 5 Prevention | Retry dialog | Blank reason produces a silent no-op |
| H5.3 | 5 Prevention | Intake | One checkbox authorises an unlimited batch |
| H5.4 | 5 Prevention | Intake | Measured quality problems do not gate or flag the upload |
| H5.5 | 5 Prevention | Queue | Exact-match field presented as a general search |
| H5.6 | 5 Prevention | Region editor | All regions can be deleted and saved |
| H5.9 | 5 Prevention | Confirm dialog | Approval requested without showing the outstanding findings |
| H5.10 | 5 Prevention | Classification dialog | The destructive consequence is styled as a footnote |
| H5.11 | 5 Prevention | Workbench | Conflict is detected only after the full correction is typed |
| H6.4 | 6 Recognition | Filters dialog | Thirteen empty fields, no autocomplete, no memory |
| H6.5 | 6 Recognition | Queue | Active filters invisible once the dialog closes |
| H6.6 | 6 Recognition | Edit dialog | Authority identifier typed free-hand while candidates exist elsewhere |
| H6.7 | 6 Recognition | Queue and workbench | No position, no next or previous, queue scroll lost on return |
| H6.9 | 6 Recognition | Queue | Four facts concatenated into one unscannable string |
| H6.10 | 6 Recognition | History | Revision browser shows only a number and a hash |
| H7.3 | 7 Efficiency | Queue | No bulk actions, against PRD REV-008 |
| H7.4 | 7 Efficiency | Queue | No saved filters, against PRD REV-008 |
| H7.5 | 7 Efficiency | Whole app | No deep link to a specimen |
| H7.6 | 7 Efficiency | All confirm dialogs | The same reason is retyped for every record |
| H8.3 | 8 Minimalist | Workbench | Two dense metadata cards sit between the reviewer and the evidence |
| H8.4 | 8 Minimalist | Intake, workbench | Ten defensive paragraphs of 26 to 52 words in the primary flow |
| H8.5 | 8 Minimalist | Fields tab | One JSON blob per field |
| H8.6 | 8 Minimalist | Workbench | Twelve undifferentiated ExpansionTiles; primary layers look like appendices |
| H8.8 | 8 Minimalist | Whole app | Colour carries almost no meaning; error text is not error-coloured |
| H8.9 | 8 Minimalist | Whole app | No dark theme for a tool used for hours |
| H8.10 | 8 Minimalist | Source panel | The primary evidence is locked to 380 pixels at every viewport |
| H9.1 | 9 Errors | Workspace | One recovery action offered for every error class |
| H9.4 | 9 Errors | Intake | Errors detached from the file that caused them |
| H9.5 | 9 Errors | Region editor | The error is unstyled, unfocused and off-screen |
| H9.6 | 9 Errors | Region editor | The message does not identify the offending field or region |
| H9.7 | 9 Errors | Startup | Five distinct configuration failures collapse to one sentence, discarding precise messages the code already produces |
| H10.1 | 10 Help | Whole app | No help entry point of any kind |
| H10.2 | 10 Help | Whole app | Domain terms used with no definition or glossary |
| H10.3 | 10 Help | Nine surfaces | "Contact your administrator" with no name and no way to reach them |

Counts: 10 catastrophes (severity 4), 57 major (3), 28 minor (2), 5 cosmetic (1). Total 100
failures, recorded against 51 confirmed strengths listed in the "What works" sections above.

---

## Pass criteria

Each statement is checkable by a QA person against a build, without reading the source.

### 1. Visibility of system status

1. Every list that can be paginated states both the loaded count and the total match count, or
   explicitly says the total is unavailable.
2. Every action that reaches the server shows progress on or immediately beside the control that
   was pressed, within 200 ms, and shows a distinct success or failure result within one second
   of the response.
3. Every screen that auto-refreshes shows when it last refreshed and never replaces visible
   content without an explicit user action or a notice naming what changed.
4. An open specimen shows a warning within 30 seconds of its server revision changing, before the
   user attempts to save.
5. Every batch operation shows an aggregate count of done, remaining and failed items.
6. No timestamp is rendered in machine format; every date and time is in the device locale with a
   relative phrase where the value is within 24 hours.

### 2. Match between the system and the real world

1. No screen requires the user to type an identifier, a timestamp or a JSON structure that the
   system already knows; every such field is a picker, and any raw-entry alternative sits under a
   section explicitly labelled as advanced.
2. Every label and every button in the default view uses a word from the collection domain or
   from PRD section 8, and internal vocabulary (revision, lease, artifact, digest, micro-unit,
   CAS, dead letter) appears only inside technical-detail disclosures.
3. Every quantity is shown with a unit the user can act on: currency for cost, minutes for time,
   pixels for geometry, and a named scale with its range for risk.
4. Two elements that refer to the same object use the same name in every place they appear.
5. No user-facing string relies on a symbol as its only semantic carrier.

### 3. User control and freedom

1. The platform back gesture and the browser back button always return to the previous screen in
   the app, never exit it, on Android, iOS and web.
2. Every destructive or irreversible action shows its consequence, including what will be
   discarded or superseded, before the confirm button, and can be cancelled.
3. Every dialog containing unsaved text refuses to close on a scrim tap or a back gesture without
   asking, and offers Keep editing.
4. Every saved decision either offers Undo for at least ten seconds, or states in its confirm
   dialog that it cannot be undone.
5. Every local edit inside a dialog, including delete, merge and reorder, can be reversed without
   closing the dialog.
6. Any in-flight batch can be stopped, and stopping never leaves a record in an unnamed state.

### 4. Consistency and standards

1. One control type per job across the whole app: tabs are `TabBar`, single-choice sets are
   `SegmentedButton`, multi-select filters are `FilterChip`, disclosures are `ExpansionTile`, and
   no control type is used for a second purpose.
2. Confirm buttons across all dialogs follow one naming pattern, and the same action is never
   named two ways.
3. Errors appear in exactly three places by rule: field, action, screen. A tester can predict
   which one a given error will use.
4. Every user-facing string is sourced from the localization bundle, and no string contains an
   em-dash or an en-dash.
5. Every status is conveyed by icon plus text as well as colour, and passes a greyscale
   screenshot test.
6. Every interactive target measures at least 48 by 48 logical pixels, and every icon-only
   control has a tooltip and a semantic label.

### 5. Error prevention

1. No field accepts a hand-authored structured format (JSON, ISO instant, comma-separated ID
   list) where a picker is possible.
2. Every confirmation that authorises work on more than one item is scoped to a single item, or
   states the exact count it authorises.
3. A record cannot be saved into a structurally impossible state: zero label regions, a supported
   value with no evidence, or a coordinate outside the source image.
4. Every measurement the client already computes and displays is either enforced as a gate or
   attached to an explicit override the user must tick.
5. Every confirm dialog lists the outstanding validation findings, blockers and superseded
   results that the action does not resolve.
6. Every button that can fail its own precondition shows a message saying why; no button is ever
   a silent no-op.

### 6. Recognition rather than recall

1. No correction can be made without the corresponding source pixels being visible on the same
   screen at the same time.
2. Every identifier the user must supply is selectable from a list of the values that exist on
   the record being reviewed.
3. Every record shows one list of everything that currently blocks clearance, each entry
   navigating to the control that resolves it.
4. Active filters are individually visible and individually removable without opening a dialog.
5. The queue keeps its scroll position and shows the reviewer's position in it, with next and
   previous navigation from inside a record.
6. Every list row carries enough information to choose between rows without opening any of them.

### 7. Flexibility and efficiency of use

1. Approve, confirm coverage, next specimen, previous specimen, switch tab, focus search, zoom
   and back are all reachable from the keyboard, and the full list is displayed by pressing `?`.
2. A reviewer can correct five fields on one record and save them with one server round trip and
   one reason.
3. The queue supports multi-select and offers the non-destructive bulk actions the server
   permits for the whole selection.
4. Filter sets can be named, saved and reapplied in one action, and survive a restart.
5. Every specimen has a URL that opens that specimen directly on web and via a deep link on
   mobile.
6. A reason can be supplied from a list of configured reason codes or recent reasons without
   typing.

### 8. Aesthetic and minimalist design

1. No raw JSON appears in any default view. Every JSON dump sits behind a disclosure labelled as
   technical detail, closed by default, and every value it contains is also available in a typed
   rendering.
2. No paragraph in a default view exceeds 20 words; anything longer sits behind an explicit
   "Why?" control.
3. Every card on a screen has one job, and the primary action of a screen is visible without
   scrolling at 1024 by 768 and at 390 by 844.
4. On a tablet in landscape the source image occupies at least 40 percent of the viewport height,
   and can be expanded to the full width in one action.
5. The app renders correctly in light and dark, at system text scale 200 percent, with no
   clipping and no horizontal scrolling.
6. All spacing, type sizes and semantic colours come from named tokens; no layout literal appears
   in a widget file.

### 9. Help users recognize, diagnose, and recover from errors

1. Every error message names what happened, what state the user's work is now in, and the single
   next action.
2. Every error surface carries the recovery action appropriate to that specific failure, and no
   two failure classes share a generic action.
3. Every error is attached to the object that failed: the file, the field, the region or the
   record.
4. Every error is visible without scrolling from the control that triggered it, is rendered in
   the error colour with an error icon, and is announced to a screen reader.
5. No error can be dismissed by a background process before the user has acted on it, and every
   persistent error can be dismissed by the user.
6. Configuration failures show a non-secret diagnostic line an administrator can act on, in
   addition to the friendly sentence.

### 10. Help and documentation

1. A help control is reachable from every screen in at most two taps, and lists shortcuts, a task
   walkthrough, a glossary, a problem report and build information.
2. Every domain term in the interface has a one-sentence definition reachable from where the term
   appears.
3. Every instruction to contact an administrator names a person or a role and provides a working
   way to reach them, prefilled with the record context.
4. A new reviewer can complete a first review using only in-app guidance, verified by an
   unassisted first-use test with two people who have not seen the app.
5. Every screen that hands work to an asynchronous process says what happens next and how to get
   to the result.

---

## What the current code does unusually well and must survive the redesign

These are not niceties. They are the reasons this client is trustworthy, and a redesign that
loses them would be a regression even if it looked better.

**Honesty about unmeasured values.** The code never substitutes zero for absent. `riskComposite`
returns the string `'Unmeasured'` whenever the assessment is blocked, incomplete or has no
composite (`lib/src/risk_assessment.dart:5-13`); `textOf`'s default is `'Not recorded'`
(`lib/src/models.dart:20-21`); usage amounts render `'Not measured'`
(`lib/src/operational_panel.dart:90-91`); a failed local decode explicitly does not count as a
quality pass (`lib/src/intake.dart:263-265`, with the comment stating so); and
`'Unmeasured: ${e.preflight!['unmeasured'] ?? 'Not recorded'}'` surfaces the gap rather than
hiding it (`lib/src/intake.dart:609-611`). Any new visual language must have a first-class
"unmeasured" state that is visually distinct from both "good" and "bad", never an empty gauge and
never a zero.

**Uncalibrated is stated wherever a number is shown.** `'Review risk (uncalibrated)'`
(`lib/src/risk_assessment.dart:30`), `'Uncalibrated measurements. A valid image is not proof of readable labels or complete coverage.'`
(`lib/src/review_context.dart:66-68`), `'Scores are uncalibrated; they do not establish correctness.'`
(`lib/src/review_context.dart:110`), `'Reading agreement does not establish correctness.'`
(`lib/src/risk_assessment.dart:216`), `'Comparison limits prevented measurement. This is not agreement.'`
(`lib/src/risk_assessment.dart:213-215`). Shortening this copy is right; removing the claim is
not. Attach the caveat to the number itself, for example as a persistent superscript marker on
the risk chip that opens the definition.

**Server-permitted actions, never client-guessed ones.** `_blocked` tests
`available_actions` returned by the server (`lib/src/workbench.dart:56-60`), `_retryBlocked` adds
the lease and the operate permission (`lib/src/workbench.dart:61-70`), and `OperationalPanel`
renders only the run actions the server listed (`lib/src/operational_panel.dart:156-174`). The
UI never invents an affordance the backend will refuse. Keep this exact contract; the redesign
should add *why* a disabled action is disabled, not replace the mechanism.

**Idempotent mutations and honest uncertainty about them.** `_mutationKeys` retains the key for a
payload across retries so an identical retry reconciles on the server rather than duplicating a
decision (`lib/src/workspace.dart:263-274`), and the large-record view states
`'Action saved at revision N. Do not repeat it.'` when a mutation committed but the response was
lost (`lib/src/large_record.dart:89-93`). The `external_outcome_unknown` handling is the same
discipline applied to model calls:
`'The last external request may have executed. Its outcome is unknown. An authorized operator must reconcile that request before deliberately retrying; the client never repeats it automatically.'`
(`lib/src/operational_panel.dart:110-113`, echoed in the retry dialog at
`lib/src/workbench.dart:1063-1069`). Preserve the keys, the never-auto-retry rule and the
explicit statement that an outcome is unknown.

**Conflict handling that protects the record.** The stale-revision message names what happened,
what did not happen, and what to check (`lib/src/workspace.dart:292-295`); a 401 or 403 tears
down the editable workspace rather than leaving a stale one usable
(`lib/src/workspace.dart:114-124`); pagination detects a repeated cursor or a duplicate id and
refuses rather than showing a plausible wrong list (`lib/src/workspace.dart:205-219`); and
`AccessFailureSource` (`lib/src/models.dart:5-7`) ensures a denial inside a child panel reaches
the workspace. Keep all four. Improve only the timing (warn before the work, per H5.11) and the
recovery action (per H9.1).

**Live regions on every message that matters.** `Semantics(liveRegion: true)` wraps the workspace
error banner (`lib/src/workspace.dart:667`), intake errors and per-file states
(`lib/src/intake.dart:528`, `563`), history load progress and errors
(`lib/src/audit_history.dart:290`, `299`, `331`), lazy evidence errors
(`lib/src/evidence_panel.dart:63`), setup errors (`lib/main.dart:227`) and both sign-in screens
(`lib/src/magic_link_screen.dart:186`, `lib/src/email_verification.dart:95`, `52`). Combined with
`semanticsLabel` on both progress indicators (`lib/src/workspace.dart:678`,
`lib/src/intake.dart:626`), semantic labels on every source image
(`lib/src/workbench.dart:498`, `510`, `lib/src/region_editor.dart:108`,
`lib/src/capture_quality.dart:125`), `Semantics(label: 'Label region ...', button: true)` on the
overlays (`lib/src/workbench.dart:532-536`) and `Semantics(container: true)` grouping on the risk
and execution panels (`lib/src/risk_assessment.dart:82`, `141`, `204`), this is a more careful
accessibility baseline than most production Flutter apps have. Every new widget must carry the
same treatment, and the `TabBar` and inline-editor changes above should be verified with
TalkBack and VoiceOver before merge.

**Evidence is never fabricated to fill a form.** The `supported` state demands both content and
linked evidence, while `unknown`, `unreadable`, `ambiguous`, `not_present`, `not_applicable` and
`unresolved` are all first-class and send `'value': null`
(`lib/src/workbench.dart:151-157`, `186-188`, `232-238`, `268`). The declaration dialog says
`'Leave a list empty to record no declaration'` and
`'no language or script is inferred'` (`lib/src/reading_declarations.dart:221`). This is PRD
REV-010 and the product's central principle, implemented correctly at the form layer. The state
selector must remain as prominent as the value field in any inline editor that replaces the
dialog.

**Original bytes are never rewritten, and the coordinate basis is disclosed.** `SourcePixels`
inverts the derivative's display transform so overlays share original pixel coordinates rather
than modifying the image (`lib/src/source_pixels.dart:5-70`), `SourceBasisNotice` states the
basis and decoder for a decoded derivative (`lib/src/source_pixels.dart:73-98`), the legacy
notice disables region correction when orientation is unverified
(`lib/src/workbench.dart:418-421`, `603`), and `'View rotation does not alter the original.'`
(`lib/src/workbench.dart:617`) tells the reviewer that what they are doing is a view operation.
Keep all of it, including the refusal to allow region editing without a verified derivative.

**Exact spans are verified against the retained reading before display.** `exactUtf16Span`
refuses to slice across a surrogate pair and the alignment view replaces any span that does not
match the retained text with
`'Span does not match the retained reading. Refresh evidence.'`
(`lib/src/reading_alignment.dart:6-48`). The large-record pager applies the same care
(`lib/src/large_record.dart:63-72`). A redesign that renders diffs more attractively must keep
this verification, and must keep failing loudly rather than showing a plausible span.
