# Screen blueprints

This document turns the audit, the writing guidelines, the design system, the
motion system, the responsive spec and the accessibility requirements into one
blueprint per screen. Each blueprint says what the screen is for, what is wrong
today with the evidence, how it is laid out at each window class, which
components it is built from, what its states are, and how a tester knows it is
done. Detailed layout math lives in
[05-responsive-and-platform-adaptation.md](05-responsive-and-platform-adaptation.md);
component anatomy lives in [03-design-system.md](03-design-system.md); every string
follows [02-ux-writing-guidelines.md](02-ux-writing-guidelines.md).

Evidence references point at `screenshots/` and at `file:line` in `lib/`.

## 1. Information architecture

### 1.1 Routes

The app has no router today (`main.dart:101-137`); screens are swapped by widget
state, so back gestures exit the app and no specimen is linkable. The redesign
adopts `go_router` with this route table. Every route is deep-linkable on web and
through app links on mobile.

| Route | Screen | Notes |
|---|---|---|
| `/sign-in` | Sign in | Redirect target when no session |
| `/verify` | Verify email | Redirect target when session is unverified |
| `/c/:collection/queue` | Queue | Query params carry filters: `?disposition=needs_review&risk_min=40` |
| `/c/:collection/queue/:specimen` | Workbench | On large windows renders beside the queue (list-detail); on smaller windows pushes over it |
| `/c/:collection/queue/:specimen/history/:revision` | Historical revision | Read only; opens in the history pane or as a pushed route |
| `/c/:collection/intake` | Intake | |
| `/c/:collection/intake/capture` | Camera capture | Full screen, phone and tablet only |
| `/c/:collection/queue/:specimen/regions` | Region editor | Full screen on compact and medium; dialog on expanded and above |
| `/help` | Help, shortcuts, glossary | Modal sheet over any route |

### 1.2 Navigation

Two destinations, Queue and Intake, as today. The collection switcher and the
account menu move out of their own full-width row (`workspace.dart:1057-1101`,
visible in `tablet-landscape-01-queue.png` as a 1500 dp dropdown) into the app
bar on medium and wider windows and into a sheet from the app bar title on
compact. Navigation component per window class follows section 2 of the
responsive spec: bottom bar, collapsed rail, extended rail, permanent drawer.

### 1.3 The environment banner

The synthetic banner (`workspace.dart:1040-1049`) is correct in intent and wrong
in weight: 44 dp of amber on every screen, in capitals, with an em-dash. It
becomes a 28 dp `EnvironmentBanner` strip under the app bar using the
`environment.synthetic` token, sentence case, with the copy from the writing
guidelines. It is never shown in production builds, so its cost is paid only by
developers and testers.

## 2. Sign in and verification

**Purpose.** Get a fieldmuseum.org staff member into their collection with a
magic link. Low frequency, low density.

**Today.** Three related screens use three different max widths (560, 440, 480)
and each carries a caveat paragraph above the fields
(`android-phone-01-signin.png`). The keyboard covers the primary button on a phone
(`android-phone-02-signin-filled.png`).

**Blueprint.** One centered column, max width 400, at every window class.
Wordmark, one-line purpose, email field, primary button, then a single secondary
line. The synthetic-mode caveat becomes the environment banner plus a two-line
note under the form, not a paragraph above it. The form scrolls with the
keyboard so the button stays reachable (`SingleChildScrollView` with
`MediaQuery.viewInsetsOf` padding). States: idle, sending, sent (with the resend
cooldown as a countdown chip), confirming link, error (inline, at the field, in
the error role). Motion: the sent state replaces the form with a fade-through,
the cooldown counts down without re-announcing every second.

## 3. Queue

**Purpose.** Let a reviewer pick the next specimen to work on and let a manager see
the shape of the backlog.

**Today.** On a phone the first record starts at the bottom edge of the first
screen because title, tagline, search, six chips, a filter button and a count
line come first (`android-phone-03-queue.png`). Each row concatenates four facts
into one string (`workspace.dart:870`). Disposition is carried by an icon color
and a lowercase word. The count says "1 matching records loaded", which is the
page size, not the total (audit H1.1). Active filters are invisible once the
dialog closes (H6.5).

**Blueprint.**

- **Header.** Title "Queue" and a live summary line: "38 records. 12 need review,
  3 blocked." The summary comes from the server counts when available; when the
  API returns only a page, the line says "38 loaded" and never implies a total.
- **Controls row.** A search field for specimen ID (labelled as exact match), a
  disposition `SegmentedButton` (All, Needs review, Cleared, Deferred, Blocked,
  Processing), and a Filters button showing the active count. Active filters
  render as removable `InputChip`s under the row so they are visible and
  individually removable without opening the sheet.
- **Rows.** `QueueRow`: leading thumbnail of the source image (48 dp, from the
  preview bytes the API already returns), title, one line of plain-language
  reason ("2 readings differ for Label 1", "Elevation range invalid"), a
  `StatusChip` for the disposition, a `RiskMeter` that shows "Not measured" when
  unmeasured, and a relative timestamp. Rows are keyed by specimen id so a
  background refresh never moves focus.
- **Empty and loading.** Skeleton rows on first load; the empty state names the
  absence ("No specimens yet" or "No records match these filters") and offers
  the one action that resolves it.
- **Refresh.** The 20 second poll stays but shows "Updated 12 s ago" in the header
  and never swaps the list while a row is focused or a sheet is open.
- **Multi-select.** A checkbox column at medium and wider; below that, a long
  press opens one. The window decides, not the platform, and the long press
  carries a named accessibility action so it is not a gesture only a sighted
  reviewer can find. The row body always opens the record and only the checkbox
  selects: a mode in which the same tap means two different things makes a row
  announce itself as a button that does not open anything.
  - **The bulk actions are the ones the server takes across records**, which
    today is approve and confirm label coverage, through
    `POST /decisions:batch`. A field correction or a transcription names a
    target inside one record and is not offered. Absent server support the
    affordance is hidden, not disabled.
  - **"Select all" means every record loaded, and the control says so.** The
    list API answers a page and a cursor, never a total, and the decisions
    endpoint takes named records at named versions, so a control claiming the
    whole filter would claim authority over records the client has never seen
    and could not state a count on the confirmation. The label is "Select all
    loaded", and once it has been taken, the bar says "More records match this
    filter. Load more to select them." whenever the server still has a page.
    The shared model (`lib/src/selection.dart`) has no way to express the other
    reading, which is how the rule is kept rather than remembered.
  - **The count is always visible**, in a bar pinned under the list rather than
    placed in it, and announced as a live region when it changes.
  - **A live selection holds the poll**, the same way a focused row and an open
    sheet already do: a count the reviewer is about to confirm must not change
    between being read and being confirmed.
  - **The confirmation names the exact count** before anything is written, in
    the title and on the primary button, through the same `ReasonSheet` as every
    other decision, so it also carries the finality sentence. This product has
    no true delete, so the count is the last honest moment.
  - **A partial result is a surface the reviewer dismisses, not one that times
    out.** It names every record that did not change, and it distinguishes
    refused from never attempted. A whole success is a snackbar.

**Layout.** Single pane through expanded; list-detail at 1200 dp and above with
a 360 dp list pane. Keyboard: `J`/`K` or arrows move selection, `Enter` opens,
`/` focuses search, `F` opens filters.

**Done when** pass criteria 1.1, 1.3, 4.5, 6.4, 6.5, 6.6 and 7.3 from the audit
hold, and the row passes the greyscale test.

## 4. Filters

**Today.** Thirteen free-text fields, including hand-typed RFC 3339 UTC instants
and API identifiers as labels (`search_filters.dart:3-17`, audit H2.1, H2.2).

**Blueprint.** A bottom sheet on compact, a 480 dp dialog otherwise. Fields are
grouped: Status (stage, blocker, issue code as pickers fed by the collection
configuration), Provenance (uploader, batch, profile as pickers), Dates (a date
range picker; the sheet converts to UTC instants internally), Risk (a range
slider 0 to 100 with a "Include not measured" switch that defaults on). Every
field has a plain label from the glossary. "Clear all" and "Apply" are the only
actions. Saved filter sets are a named list at the top of the sheet once the
server or local storage supports them.

## 5. Intake and capture

**Purpose.** Get photographs from a camera or a folder into the collection with
honest quality feedback and a manifest an operator can trust.

**Today.** Two paragraphs of 40 and 41 words come before the first button
(`android-phone-05-intake.png`). The manifest is below the fold at every width;
`intake.dart` has no layout branch. A single checkbox authorises an unlimited
batch (audit H5.3). Rejected files never appear in the manifest (H1.6). One string
field carries both progress and error text (H4.5). There is no way to remove a
file or stop a batch (H3.6, H3.7).

**Blueprint.**

- **Capture card.** Title "Add photographs". Two buttons: "Take photograph" (phone
  and tablet) and "Choose files". A sensitivity `SegmentedButton` (Sensitive,
  Not sensitive) with a one-line helper and a "Why" disclosure. The pre-upload
  checklist becomes a five-item list with a checkbox per batch, and the checkbox
  is reset whenever a file is added.
- **Manifest.** `UploadItem` rows: thumbnail, name, size and dimensions, a
  `StatusChip` (Ready, Checking, Uploading with a determinate ring, Accepted,
  Already in collection, Interrupted, Skipped with reason, Failed with reason),
  and a remove control while the item is not yet accepted. Local quality
  measurements render as three short labelled values with a "Not calibrated"
  chip; the server check is a button that reports its result in the same row.
  Batch progress sits in the manifest header: "8 of 12 accepted, 1 skipped".
  A "Stop" action cancels items that have not started; in-flight items finish.
- **Layout.** Single column on compact. Two columns at medium and above: capture
  card fixed at 420 dp on the left, manifest scrolling on the right, so the
  operator sees the manifest fill while pressing the same button.
- **Camera.** A full-screen capture route on phone and tablet with a level
  indicator, framing guides for the specimen and its labels, exposure and glare
  hints labelled as uncalibrated, tap to focus, a review step with retake, and a
  batch mode that returns to the viewfinder after each accept. Section 7 of the
  responsive spec lists what `image_picker` cannot provide and what the custom
  camera needs.

**Done when** pass criteria 1.5, 1.6, 3.6, 3.7, 4.5, 5.3 and 9.3 hold.

## 6. Workbench

**Purpose.** Let a reviewer compare source pixels against two independent
readings, decide, record a reason, and move on. This is the screen the north
star is about.

**Today.** The source image is a 380 dp box that scrolls away with the page;
after one scroll on a tablet the left pane is empty
(`tablet-landscape-03-workbench-scroll.png`, `desktop-01-workbench.png`). The
region overlay prints a UUID on a black box over the label it marks
(`android-phone-04-workbench-top.png`, `workbench.dart:548-560`). The Record
status card holds thirteen unrelated elements and dumps the attempts dictionary
as text (`android-phone-04-workbench-scroll2.png`). The two decision buttons sit
beside two occasional actions with equal weight. Readings, fields and history
are chips two screens below the image. Every correction is a modal that hides
the pixels (audit H6.2, severity 4). Raw JSON is the primary rendering for
issues, blockers, risk, disagreements, fields and audit events (H8.1).

### 6.1 Structure

Three regions at every window class: the **source pane**, the **evidence pane**
and the **decision bar**.

- **Source pane.** The image, its region overlays, the region chips, and the
  view controls. On compact and medium it is a collapsible header that stays
  pinned at a minimum height of 40 percent of the viewport while the evidence
  scrolls beneath it, with a control to expand it to full screen. On expanded and
  above it is a fixed pane that never scrolls with the evidence. Selecting a
  region chip animates the viewport to the region (emphasized easing, 350 ms,
  instant under reduced motion) and scrolls the readings to that region.
- **Evidence pane.** A `SegmentedButton` with Readings and Fields (History
  becomes a third segment below 1200 dp and a persistent side pane above). Above
  the segments sits a compact **status strip**: `StatusChip` for the disposition,
  run and version, stage, and a one-line **blockers summary** ("2 things block
  clearance") that expands to a list where each item navigates to the control
  that resolves it. Operational detail (attempts, usage, cost, lease) moves into
  a "Processing" disclosure that is closed by default and never shows a missing
  measurement as zero.
- **Decision bar.** "Confirm label coverage" and "Approve record" pinned at the
  bottom of the evidence pane (expanded and above) or above the navigation bar
  (compact and medium). Each button carries a tooltip and semantic hint with the
  reason when the server does not permit it. Next and previous specimen sit at
  the bar's edges on expanded windows and as swipe gestures on compact.

### 6.2 Source pane details

- `RegionOverlay` draws a 2 dp outline in the `region.overlay` token with a
  small numbered tab at the corner, outside the box, never a label over the
  pixels. The selected region uses `region.selected`. Overlays have a 44 dp
  minimum hit area independent of the box size and a focus ring at 3:1 against
  the photograph.
- Region chips read "Label 1", "Label 2"; the overlay's semantic label matches.
- Controls: rotate view, zoom in, zoom out, fit, full screen. The rotation is a
  view transform and the pane says so in a tooltip, not a paragraph.
- Asset checksum and coordinate basis live in a "Source details" disclosure.

### 6.3 Readings

- `ReadingCard` per model per region: model name, provider, a `DiffText` of the
  literal reading against the other reading with changed spans underlined and
  marked, and a summary sentence above ("Differs in 3 places"). The comparison is
  a minimal edit script over runes, so the sentence counts the places the two
  readings disagree rather than the positions at which their indices stop lining
  up. Cards sit side by side on medium and wider windows and stack on compact.
- Language and script declarations render as chips with a "Declare" action;
  the declaration history is a disclosure.
- "Resolve transcription" opens the reason sheet with both readings visible
  beside the field, not a modal that hides them.

### 6.4 Fields

- `FieldRow` per required field: name, required marker, `StatusChip` for the
  field state (Supported, Unknown, Unreadable, Not present, Not applicable,
  Ambiguous, Unresolved), and three labelled layers: As written, Read as,
  Standardized, plus an authority line when present. Validation findings attach
  to their field with the error role and an icon.
- **Inline correction.** Tapping a layer turns it into an editor in place; the
  source pane jumps to the region the field came from. The evidence field is a
  picker of the record's own evidence IDs, never free text. Corrections accumulate
  as pending changes (an amber "3 pending changes" chip in the status strip) and
  save together with one reason through the `ReasonSheet`. One server round trip
  per batch, one reason per batch, which is the behaviour the audit's pass
  criterion 7.2 requires.
- Authority candidates render as `AuthorityCandidateCard`s with name, identifier,
  relation and a "Use this match" action; the raw response is an `EvidenceDrawer`
  disclosure.
- Phase results render as a stepped list (Parse, Plan, Lookup, Resolve,
  Normalize, Validate, Finalize) with applicability and findings, each with a
  lazy "View evidence" that renders typed proposals.

### 6.5 History

- Decision history as a timeline: actor, action in plain words, reason, version,
  relative time, with "Open this version" for a read-only snapshot. The JSON of
  each event is an `EvidenceDrawer`.
- The revision browser lists version, date, actor and a one-line change summary,
  not a number and a hash.

### 6.6 Reason sheet

One `ReasonSheet` for every consequential action: shows the action, the object,
the consequence ("Run 3 is superseded. Run 3 stays in history."), the outstanding
findings the action does not resolve, a reason field with recent reasons as
chips, and a primary button named for the verb. It is a bottom sheet on compact
and a 480 dp dialog otherwise. It refuses to dismiss on scrim tap when text has
been entered and offers "Keep editing".

### 6.7 Conflict

When the record changes under the reviewer, a banner appears within one poll
interval, before any save is attempted: "Version 22 was saved by another
reviewer. Refresh and compare." A conflicting save opens a dialog with the same
copy and a primary "Refresh and compare" action. Pending local changes are kept
and re-applied against the new version where the field is unchanged.

### 6.8 Keyboard

`J`/`K` next and previous specimen, `1` to `9` select region, `R`/`F`/`H`
switch segment, `+`/`-`/`0` zoom, `A` approve (opens the reason sheet), `C`
confirm coverage, `?` shortcut list. All shortcuts appear in the help sheet and
are suppressed while a text field has focus.

**Done when** pass criteria 6.1, 6.2, 6.3, 7.1, 7.2, 8.1, 8.3, 8.4 hold, the
accessibility scripts in section 4.2 of the accessibility document complete, and
a timed review of five fields on one record takes one save.

## 7. Region editor

**Today.** A 680 dp dialog whose only resize control is four numeric fields; a
180 dp preview; delete and merge are instant and unrecoverable
(`region_editor.dart`, audit H3.4, H3.5, H5.6).

**Blueprint.** Full screen on compact and medium, a 640 dp dialog otherwise. The
preview fills the available width. Each region has four corner handles and a
drag body; the numeric fields remain below as the precise alternative and as
the pointer-free path WCAG 2.5.7 requires. Add, delete, reorder, rotate and
merge are in a toolbar; delete and merge are undoable inside the editor with a
snackbar "Undo". Saving with zero regions is blocked with a reason. The reason
field and the save button live in the sticky footer.

## 8. Operational recovery

**Today.** All four run actions render for a finalized run
(`android-phone-04-workbench-scroll4.png`); "Retry processing" appears enabled on
a cleared record; usage and cost lines print raw values and "0 micro-units".

**Blueprint.** A "Processing" disclosure in the status strip. Closed, it shows
one line: the stage and, if blocked, the blocker in plain words with the next
retry time. Open, it shows attempts as a list, usage as labelled values with
units, and only the run actions the server permits, each with a tooltip naming
why it is unavailable when it is. Reserved and actual cost render as currency
when the API returns a unit and as "Not recorded" otherwise; they never render
as zero when absent.

## 9. Large record fallback

Keep the behaviour (read-only, verified artifact, paged text) and restyle:
the explanation becomes "This record is too large for the normal view" with a
"Why" disclosure, the section picker becomes a `SegmentedButton` or dropdown
by width, and the text page keeps its real text semantics instead of one flat
label (accessibility finding 8).

## 10. Help, glossary and administrator contact

A help control in the app bar overflow on every screen opens a sheet with:
keyboard shortcuts, a glossary generated from the vocabulary table in the
writing guidelines, a three-step first-review walkthrough, build and
environment information, and an administrator contact that the collection
configuration supplies. Every "ask your administrator" string links here.

## 11. Errors and connectivity

Three error surfaces by rule: at the field (validation), at the action (a
snackbar or inline line beside the control that was pressed), and at the screen
(a banner for loss of access or connectivity). Each failure class has its own
recovery action. A server-unreachable banner names the last successful sync
and offers Retry; it does not clear itself while the failure persists.

## 12. Dark mode

Every blueprint above ships in light and dark from the token table. The
photograph stays as captured in both modes; the letterbox behind it uses
`surface-container-lowest` in light and `surface-container-highest` in dark so
label paper reads as paper, not as a glowing rectangle.

## 13. Order of work

Matches the sequencing in the north star: foundation and writing first, then the
shell and queue, then the workbench, then intake and capture, then motion and
polish, then verification. Each screen blueprint is independently mergeable
once the foundation is in.
