# Web (Flutter web, debug) evidence, desktop and tablet-landscape

Captured 2026-09-14 against the running Flutter web build at `http://localhost:3000`
(debug/DDC) with the synthetic API on port 8010, the same one-record fixture
(`synthetic-label.png`, collection "Insects") used in the other captures in this
folder. Sign-in used `reviewer@fieldmuseum.org` / fixture token
`4e479be9a7e26a8762361d7502f759ec7caae2153e9bd990`.

No PNGs could be saved from this tool chain (the browser tool returns screenshots
as images to the calling agent, not as files), so this written log is the
deliverable. Proportions below are measured off the actual screenshots (800px
wide for both viewports; 800x500 for 1440x900 = 55.6% scale, 800x600 for
1024x768 = 78.1% scale) and converted back to percentages of the viewport.

## Interaction method that actually worked

Standard `computer` clicks and `computer type` on this Flutter-web (CanvasKit)
build **do not register at all**, clicking a text field, a button, or the
"Sign in" control produces no focus ring, no validation, no navigation, and
`document.activeElement` stays `BODY`. Mouse-wheel `scroll` actions likewise do
nothing. This is because the app renders everything into a single `<canvas>`
inside a shadow-DOM `flt-glass-pane`; there is no real DOM for pointer events to
land on until Flutter's semantics (accessibility) tree is turned on.

The method that worked, in order:
1. Enable the semantics tree once per fresh page load by clicking the
   real, focusable `<flt-semantics-placeholder>` element via
   `javascript_tool` (`document.querySelector('flt-semantics-placeholder').click()`).
   This is the hidden "Enable accessibility" button Flutter always ships.
2. After that, `document.querySelector('flt-semantics-host')` contains real
   `<input>` elements (one per text field, in DOM order) and elements with
   `role="button"` / `role="checkbox"` (for ChoiceChips) that have working
   `aria-label` / `textContent`.
3. To type into a field: `javascript_tool` to call `.focus()` on the specific
   `<input>` inside the semantics host, then a normal `computer` `type` action
   (typing only works once real DOM focus is established this way, setting
   `.value` directly via `form_input`/JS is silently reverted by Flutter).
4. To click a button/card/chip: `javascript_tool` calling `.click()` directly
   on the matching `role="button"`/`role="checkbox"` element found by matching
   `textContent`/`aria-label` (plain `computer` clicks on the same visual
   coordinates still do nothing, even with semantics on, the semantics nodes
   themselves have `pointer-events: none` in their CSS and only respond to a
   real `click()` call or an OS-level accessibility action, not a synthesized
   mouse event at their screen coordinates).
5. To scroll: the scrollable region is a semantics node with
   `overflow-y: scroll` but `pointer-events: none`; setting its `.scrollTop`
   via JS and dispatching a `scroll` event moves Flutter's real scroll
   controller and the canvas repaints correctly.

One environment-specific note, not an app bug: jumping the emulated viewport
straight to 1024x768 left most of the canvas unpainted (black) below/right of a
~544x404 region. An intermediate resize (e.g. to 1000x700, then back to
1024x768) forced a repaint and fixed it. This looks like a CanvasKit backing
buffer not being reallocated on a single large emulated resize in this browser
tool, not something a real user's window resize would trigger.

---

## Desktop, 1440x900

### 1. Sign-in screen
Single centered card on an off-white background, no header/chrome at all (this
is the only screen with no app bar). The card spans roughly x=264 to 536 of the
800px-wide screenshot (34% of viewport width), horizontally centered. Vertical
content (microscope glyph, "Specimen Digitization" title, tagline, the
"Local synthetic fixture access" sub-heading, a 3-line synthetic-only warning,
two text fields, and the "Sign in" button) runs from about y=100 to y=380 of
500 (56% of viewport height), with slightly more empty space below the button
than above the logo. Fields and button share the same width as the card. The
"Fixture token" field has a trailing eye icon to reveal the value; no visible
affordance distinguishes it as a password field otherwise (no "•••" masking
character hint, no autofill icon).

### 2. Queue after sign-in
Persistent chrome starts immediately at the top: a slim app-title bar
(y=0 to 6% of viewport height) with a refresh icon and a "Sign out" icon at the
far right; a full-width yellow "SYNTHETIC ENVIRONMENT {EM} fixture results are
not real model processing or museum-approved records." banner directly below
it (another ~4% of height); then an "Authorized collection" dropdown row
("Insects") with "Local synthetic reviewer" printed at the far right of the
same row. A persistent icon-only left nav rail (Queue/Intake) occupies the
left ~5.5% of viewport width and runs the full height of the page, it does
not scroll with content. Below the chrome: "Collection queue" heading, a
one-line subtitle, a full-width search box, a row of 6 filter chips ("All
records" selected in green, the rest outlined), a "Filters (0)" pill button
beneath the chips, a "1 matching records loaded" caption, then the single
record card (light-green background, filename, a green check + "cleared"
status line, profile/timestamp line, "Risk: Unmeasured · Uncalibrated" line,
and a chevron at the far right edge indicating it's a full-width tappable
row). The record card and everything above it fit inside the 900px-tall
viewport with room to spare, no scrolling was needed to see the one fixture
record.

### 3. Workbench (record opened)
**Top:** Same header/banner/collection-dropdown chrome as the queue, plus a
"← Back to queue" text link. Below that: filename heading
("synthetic-label.png") and its UUID underneath, and a refresh icon at the far
right of that row. The body is a **two-column layout**: left column
(≈44% of content width) is "Source image" with rotate/zoom/fit-to-frame icon
buttons and a "Whole image" link, then the image itself (a screenshot of a
label transcript, with a small yellow-outlined region box near the top
overlaying a highlighted line of text), a "Label 1" chip, asset ID and SHA-256
text, and a "Correct label regions" link. Right column (≈52% of width) is
"Record status": status line ("cleared"), a profile/revision line, a
multi-line "Attempts: {...}" raw dictionary dump, two action-button rows
("Confirm label coverage" / "Record review approval", then "Correct
classification" / "Retry processing"), then a "Server image check" section
with pixel dimensions, brightness/contrast/detail-signal metrics, and a
collapsible "Image measurements and orientation" row. A second section,
"Classification and pinned profile," starts being cut off at the very bottom
edge of the viewport, confirming the page is taller than 900px and requires
scrolling.

**After scrolling once** (scrollTop ≈ 400 of a ≈3494 total, i.e. ~11% into
the page): the two columns scroll together as **one shared vertical scroll
container**, not two independently-scrolling panes. The left column's image
area is now mostly cropped to a blank/white sliver near the top of the
viewport (only a few remaining pixels of the image and none of its text
remain legible), while the right column has advanced to show "Classification
and pinned profile," "Classification provenance," "Pinned profile
dependencies and field rules," and "Recorded classification decision"
(collapsible rows). **The source image does NOT stay pinned/visible while
scrolling, it scrolls out of view with the rest of the page.**

**After scrolling twice** (scrollTop ≈ 900, ~26% into the page): the left
column is now completely blank (all of its content, image, label chip, asset
info, has scrolled past and the column is simply empty space for the rest of
the page's length, since it was much shorter than the right column). The
right column shows "Processing and recovery" (stage, steps, tokens, cost
metrics), a collapsible "Execution policy, usage and attempts" row, three run
buttons on one row plus a fourth ("Pause processing", "Resume processing",
"Cancel processing", then "Start new run" wrapped to its own row), and, right
at the bottom of the viewport, the three ChoiceChips: "Readings" (selected,
green fill with a check), "Fields & evidence", and "History". Because the left
column is empty for the remainder of the scroll, roughly half the viewport
width is wasted white space once you've scrolled past the image.

### 4. Fields & evidence / History chips
Clicking "Fields & evidence" (still scrolled to the chips' position) swaps the
content below the chip row to "Required fields & validation", a caption line,
then a list of labeled rows (fmnh ins number, collection code, country,
province/state, …), each showing "supported · <value>" and a chevron to
expand; the visible screenful shows 3 full rows before the "province state"
row is cut at the bottom edge. Clicking "History" instead shows "Current
decision history" / "Current review revision 21" and a numbered list of
workflow-step entries, each with an ISO timestamp and "synthetic-reviewer" as
actor, each row also chevron-expandable; 4 entries are visible before the
viewport bottom cuts the list. Both tabs replace the same content region in
place, the chip row itself does not move.

### 5. Filters dialog ("Filters (0)")
A centered modal dialog over a dimmed background, roughly x=228 to 572 (43% of
viewport width) and y=13 to 487 (nearly the full viewport height, 91%). Title
"Filter collection queue," a two-line explanatory caption ("All filters must
match. Risk filters exclude unmeasured records; risk does not establish
clearance."), then a vertical list of underlined text-input rows: Asset ID,
Run ID, Batch ID, Uploader ID, Processing stage, Profile ID, Profile version,
Issue code, Blocker, and "Created from (inclusive UTC)", 10 fields fit
without the dialog needing to scroll internally at this viewport height. A
bottom action row has "Cancel" and "Clear filters" as plain text links on the
left/center and a filled green "Apply filters" button on the right.

### 6. Intake screen (rail → "Intake")
Same persistent chrome (header, banner, collection dropdown, left rail, now
with "Intake" highlighted green). "Bring a specimen into focus" heading and a
one-line subtitle. A light-green card holds: an image-picker glyph, "Select
source photographs" heading, a "Sensitivity of new photographs" dropdown
("Sensitive" selected), two explanatory paragraphs (one about non-sensitive
classification, one about local previews/HEIC/TIFF handling and server-side
verification), a "Choose files" filled green button next to a "Take
photograph" button that renders visually disabled/greyed (camera capture is
noted as Android/iOS-app-only), a line of pre-submission guidance text, and a
checkbox "I checked framing and readability" right at the bottom edge. Below
that (confirmed by scrolling in the companion desktop capture already in this
folder) is an "Upload manifest · 0 items" section with placeholder text.

### 7. Browser back-button behavior (from the workbench)
The app never changes the URL for internal navigation, `location.href` stays
`http://localhost:3000/` whether you're on the sign-in screen, the queue, or a
specific record's workbench. Consequently, **pressing the browser's Back
control from the workbench does not return to the queue.** In a tab whose
history had a blank page before the app loaded, Back left the Flutter app
entirely and landed on that blank page (the app's canvas simply disappeared).
Pressing Forward again did not resume the app's in-memory state, it forced a
**full reload from scratch**, landing back on the **sign-in screen** (all
session/auth state was lost, not restored). In a tab that was opened directly
at the app URL (no prior blank page in its history), Back had no earlier entry
to go to and was a no-op, the workbench just stayed exactly as it was. In
neither case does Back ever produce the queue screen; that screen has no
history entry of its own to go back to. This matches an issue already flagged
in this folder's `README.md` (H3.1: system-back exits to launcher instead of
the queue, observed on Android).

### 8. Keyboard: Tab from the queue
Before any key press, `document.activeElement` is `flutter-view` itself (the
whole app root), nothing is pre-focused on page load. Pressing Tab once moved
accessibility focus to the "Refresh collection" icon button in the top-right
of the header bar. **No visible focus ring, outline, or any other visual
change appeared anywhere on screen** at that button's location, the only way
to know focus had moved was to query `document.activeElement` in the console.
For a sighted keyboard-only user, pressing Tab from the queue gives no visible
feedback about where keyboard focus went.

---

## Tablet landscape, 1024x768

### 1. Sign-in screen
Same single centered card, same relative proportions as desktop (card ≈41% of
viewport width, content block ≈64% of viewport height, centered with slightly
more bottom whitespace), the layout does not visibly change between these two
widths, it just re-centers. Text and control sizes are the same absolute
pixel size as desktop, so they read as proportionally larger on the smaller
canvas.

### 2. Queue after sign-in
Identical chrome arrangement to desktop (title bar, yellow synthetic-data
banner, collection dropdown + reviewer label, left icon rail with visible text
labels "Queue"/"Intake" under each icon). The search box, 6 filter chips,
"Filters (0)" button, and the one record card all fit on screen with no
scrolling required, same as desktop, the narrower width does not force any
wrapping in this simple list state (there's only one record).

### 3. Workbench (record opened), layout changes to single column
This is the most significant difference from desktop: **at 1024px the
two-column workbench layout collapses to a single stacked column.** Opening
the record shows only the "Source image" panel (viewer icons, the image
itself, "Label 1" chip, asset/SHA lines, "Correct label regions" link) filling
the full content width, "Record status" is not visible side-by-side at all;
it has been pushed below the fold.

**After scrolling once** (scrollTop ≈ 500 of ≈3968 total, ~13% into the page):
the tail end of the image panel ("Label 1" chip, asset info) is visible near
the top, immediately followed by the "Record status" card (status, profile,
attempts dictionary, the two action-button rows) starting directly beneath it
in the same single column, with "Server image check" beginning to show at the
very bottom edge.

**After scrolling twice** (scrollTop ≈ 1200, ~30% into the page): now showing
"Classification and pinned profile" and its sub-sections, then "Processing and
recovery" starting at the bottom edge. As on desktop, **the source image does
not stay pinned, it has scrolled completely out of view** and, because this
is a single column rather than two, there is no leftover blank space beside
later content (unlike desktop, where the empty left column persists after its
content ends).

Continuing to scroll to the chip row (scrollTop ≈ 1750, ~44% into the page)
shows one difference from desktop worth noting: the four run-action buttons
("Pause processing", "Resume processing", "Cancel processing", "Start new
run") all fit on a **single row** at 1024px width, whereas at 1440px width
three of the four wrapped together and the fourth ("Start new run") dropped to
its own row, i.e. the button row's wrap point is not simply "narrower viewport
wraps more"; the ordering of the wrap differs, likely due to how much other
chrome (like the wider two-column split) is competing for width at 1440px.

### 4. Fields & evidence / History chips
Same behavior and content as desktop, clicking "Fields & evidence" shows the
"Required fields & validation" list (fmnh ins number, collection code,
country, province state visible, one more chevron-expandable row cut at the
bottom); clicking "History" shows "Current decision history" / "Current
review revision 21" with 4 numbered workflow entries visible. No layout
differences from desktop other than the single-column context they sit in.

### 5. Filters dialog
Same "Filter collection queue" modal, but relatively larger against the
smaller viewport: the visible field list before the button row shows 8 fields
(Asset ID through Issue code) rather than desktop's 10 (Blocker and "Created
from" are not visible without scrolling the dialog itself, though the dialog
did not appear to need internal scrolling to reach the button row, Cancel /
Clear filters / Apply filters are all visible at the bottom in the same
screenshot). Otherwise identical structure and copy to desktop.

### 6. Intake screen
Same content and structure as desktop (heading, subtitle, sensitivity
dropdown, two explanatory paragraphs, "Choose files" / disabled "Take
photograph" buttons, guidance text, "I checked framing and readability"
checkbox visible at the very bottom edge). No reflow differences observed
versus desktop other than the same absolute-size-on-smaller-canvas effect seen
on the sign-in screen.

### 7. Browser back-button behavior
Tested from a tab that was opened directly at the app URL (no prior blank
page in its history): pressing Back had no previous history entry to go to,
so it was a **no-op**, the workbench stayed exactly as it was, still showing
the record, not the queue. This is consistent with the desktop finding: since
the app never pushes a distinct history entry for the queue vs. a record's
workbench, Back can never land on the queue specifically, it either does
nothing (no prior entry) or leaves the app for whatever the tab's actual
previous page was (as seen on desktop), but never reproduces in-app
navigation.

### 8. Keyboard: Tab from the queue
With focus explicitly reset to the `flutter-view` root before pressing Tab,
the first Tab stop landed in the **"Search specimens" text field** (not the
header's refresh icon, as it was on desktop), a text cursor appeared inside
the field and a floating tooltip/hint reading "Label specimen ID; use Filters
for other criteria" appeared overlapping the field's placeholder text. As on
desktop, **no visible focus ring or border-color change appeared on the field
itself**, the only indication focus had moved there was the blinking text
cursor and that tooltip text. (Note: an earlier, less-isolated attempt at this
same test, taken right after clicking "Back to queue" via script rather than
after explicitly resetting focus to the app root, produced a different first
Tab stop, on the "Intake" rail item; the DOM/tab order is evidently stateful
based on whatever element last held focus, not a fixed sequence starting from
the top of the page every time.)
