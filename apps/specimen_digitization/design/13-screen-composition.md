# 13. Screen composition

How a screen is put together from the controls, so that a phone shows the
work and not the chrome. Written on 2026-09-17 from the record screen on an
Android phone after wave 3: the controls were right and the screen was wrong.
It does for screens what 11 did for controls: names the causes, states the
rules, and turns each rule into a test. 05 section 3 and 07 already describe
the arrangements this document enforces; where they differ, this document
wins and says so.

## 0. The record screen on a phone, read as one defect

The capture at 390 by 844 dp showed, from the top: the collection switcher
bar, a two line environment band, a "Back to queue" row, a "Source photograph"
heading with its own collapse control, the photograph inside a matte inside a
pane with a floating tool capsule over its lower edge, a row of region
toggles, the specimen title with three commands, a "Correct label regions"
command, a "Source details" disclosure, a decision bar holding previous, a
count, next, and two stacked buttons, and the floating navigation pill. The
readings, which are the work, were below the fold.

| Seen | Cause | Rule that prevents it |
|---|---|---|
| A scroll inside a scroll | The stacked regime puts the source pane, which scrolls itself, inside a page `ListView` (`workbench.dart`, `_stacked`); intake and the import sheet nest the same way | One scroll per screen per axis (section 2.1) |
| Chrome takes about three quarters of the height | Top bar, band, back row, section heading, decision bar and pill are each laid out as if the window were tall; nobody adds them up | The chrome budget (section 2.3) |
| Things inside things | Photograph in a matte in a pane in a padded page in a scaffold; a glass decision bar over a glass pill; a heading over a disclosure over a pane | Surface depth (section 2.2) |
| No priority | The title repeats what the top bar should carry; "Back to queue" repeats what the bar's leading slot is for; the photograph's heading names what is self evident; the decision bar carries navigation it does not need on a phone | One job per region (section 2.4), and the per screen tables (section 4) |
| Conflicts inside elements | The tool capsule floats over the photograph's lower edge and the region toggles sit right under it; two collapse controls (heading and disclosure) three rows apart | The pinned header pattern (section 3.1) and one job per region |

07 section 6.1 already asked for a collapsible source header pinned at 40
percent of the viewport with the evidence scrolling beneath it, a status strip,
segments, and a decision bar above the navigation with previous and next as
swipes on compact. None of that was built, because nothing failed when it was
not. This document is what fails.

## 1. Units and axes, restated for screens

11 gave controls their units. A screen has two more:

- **The viewport.** Everything a screen pins (top bar, band, headers, bars,
  navigation) is measured as a fraction of `MediaQuery.sizeOf(context).height`
  at the window class in question. Content is what is left.
- **The scroll.** A screen has one vertical scroll position. Regions either
  scroll with it, pin above it, or collapse into it. Nothing scrolls on its own
  inside it.

## 2. The composition contract

Every routed screen satisfies these at every window class, in both modes, at
text scales 1.0, 1.3 and 2.0. Each clause is a test in
`test/composition/` (section 5).

### 2.1 One scroll per screen per axis
A screen is a `CustomScrollView` with slivers, or a single `ListView`. No
vertical scrollable sits inside another vertical scrollable. `shrinkWrap:
true` and `NeverScrollableScrollPhysics` do not appear under `lib/`, because
each exists only to nest a list. A horizontal strip (chips, region toggles, a
segmented track that scrolls) inside the vertical scroll is allowed and is the
only exception. A sheet or a dialog owns its own scroll, because it is its own
surface; the screen under the scrim does not count.

### 2.2 Surface depth
At compact, no surface sits inside another surface: a photograph sits on its
matte, and the matte sits on the page; a row sits on the page, not on a card
on the page. Glass at compact is the one pane the scaffold gives the pinned
region, and nothing else. **Amendment, wave A (2026-09-17).** The scaffold
spends that pane on the chrome it floats, the action bar or the navigation
where there is none, and publishes `GlassQuality.off` to every other region
inside itself, so a top bar that scrolls under, a collapsed header's chrome and
the band draw the same surface solid. Section 3.1's clause giving the pane to
the collapsed header's chrome is superseded by this one: both cannot hold on a
record screen, and 2.2 is what the gates measure. At medium and above depth is at most two, and glass
panes at most the budget 09 sets per class (compact 1, medium 2, expanded 3,
large 4), counted on the whole screen including the navigation.

### 2.3 The chrome budget
Pinned chrome at compact is at most 28 percent of the viewport height: top
bar, environment band, any pinned header at its collapsed height, the decision
bar, and the navigation pill, added together. At medium at most 24 percent,
at expanded and above at most 20 percent. Where a screen's pinned regions
exceed the budget, the screen has to give one of them up, not shrink them
below their density height. The rules that make the budget reachable:

- The environment band at compact is one line of `label` text on its tint,
  32 dp of tint inside a 48 dp hit box that is never shrunk, with the detail
  behind a tap (a sheet), never a two line paragraph with a chevron.
- The navigation pill hides on a screen that is inside a record (the record
  screen, the region editor), where the way out is the top bar's back. The
  scaffold owns this by route.
- The decision bar at compact is one row, `density.controlHeight` plus its
  padding: the primary action, the secondary action as a text button beside
  it or in the bar's overflow when both do not fit (11 section 3.3), and the
  specimen count as a label. Previous and next are swipes on compact and edge
  buttons from medium up (07 section 6.1).
- The top bar carries the screen's title and the back action; no screen draws
  a second title row or a "Back to ..." row under the bar.

### 2.4 One job per region
Each pinned or scrolling region has one job and says it once. The top bar
names the screen and offers the way out. A collapsing header shows the thing
under review. A status strip states the disposition and what blocks it. The
segments choose the evidence. The decision bar decides. Anything that repeats
another region's words (a heading over a photograph, a title under a top bar
that already carries it) is removed, not styled.

### 2.5 Above the fold
At compact, the screen's primary region (the photograph on the record screen,
the list on the queue, the form on intake, the sources list on sources) is
visible at its minimum height within the first viewport, with at least one
row of the region beneath it (the status strip and the first reading on the
record screen; the first two rows on the queue). The test measures it.

### 2.6 Rhythm
Gutters are `s4` at compact and `s6` from medium; the gap between regions is
`s6`; a region's own padding replaces, never adds to, the page's. A surface
carries its own padding and its content carries none. Nothing is padded
twice, which the depth rule makes checkable.

## 3. Patterns the package provides

### 3.1 `UiCollapsingHeader`
A `SliverPersistentHeader` for the thing under review. It takes a
`maxFraction` and `minFraction` of the viewport height (the record screen uses
0.55 and 0.40, from 07 section 6.1), the content, and a `chrome` slot for
controls that ride its lower edge (the view control capsule) and shrink to a
single row at the minimum. It is pinned; it never floats; it draws
`glass.flat` behind its chrome only when collapsed, so the budget's one pane at
compact is this one. Under reduced motion the collapse still tracks the
scroll, because it is a scroll position and not a transition.

### 3.2 `UiStatusStrip`
One line at the top of the evidence: the disposition chip, run and version,
and the blockers summary ("2 things block clearance") that opens a sheet
listing each with its control. It scrolls with the evidence.

### 3.3 `UiDecisionBar`
The decision bar of 2.3 as a pattern: primary, secondary, count, optional
previous and next from medium up, and the swipe handler for compact. It sits
in `UiScaffold.actionBar`, which a routed screen can now fill
(`UiScaffold.of(context).setActionBar` or the equivalent hook the package
lands), so the shell owns the bottom of the screen and the budget.

### 3.4 `UiScaffold` by route
`UiScaffold` reads the route: which screens hide the navigation pill, which
sky preset paints, whether the environment band is the one line form. The
shell already switches the sky by route; the pill and the band follow.

### 3.5 `UiStickyBar`
A pinned `SliverPersistentHeader` of one fixed extent for the region that
scrolls up to the header and then sticks under it: the record's segments, the
queue's search and filter row. It carries a `PinnedChrome` marker of the
`header` region, so the budget counts it while it is stuck, and it draws solid
under the scaffold's compact pane policy. Added by the integrator at the wave A
merge so both screen slots compose the same bar.

### 3.6 `UiBanner.strip`
The one line environment band: tint, glyph, one `label` line, tap for the
sheet with the full sentence and the administrator contact.

## 4. The screens at compact

Each table row is one region in scroll order; pinned regions say so. Where
this differs from 05 or 07 the difference is noted.

### 4.1 Record (workbench)
| Region | Pinned | Content | Height at 390 by 844 |
|---|---|---|---|
| Top bar | yes | Back, specimen id (`mono.identifier`), refresh; the collection switcher is not shown inside a record | 56 |
| Environment band | yes | One line strip when the environment is not production | 32 |
| Source header | collapsing, 0.55 to 0.40 | Photograph on its matte edge to edge, region overlays, the view control capsule riding the lower edge, the region toggle strip as the header's last row | 464 to 338 |
| Status strip | scrolls | Disposition, run and version, blockers summary | 40 |
| Segments | scrolls, then sticks under the header (`UiStickyBar`) | Readings, Fields, History | 48 |
| Evidence | scrolls | The chosen segment's content; commands that belong to the record (correct label regions, correct classification, retry) live in the top bar's overflow menu, not as rows | rest |
| Decision bar | yes | Primary, secondary or overflow, "1 of 4"; swipe for previous and next | 64 |
| Navigation pill | hidden | | 0 |

Pinned total 152 of 844, 18 percent. The photograph shows at 40 percent
minimum with the status strip and the first reading beneath it. 07 asked for
the segments in the evidence; they stick under the header here so the reader
never loses which evidence is showing, which 07 did not say and 05's wireframe
implies.

### 4.2 Queue
| Region | Pinned | Content |
|---|---|---|
| Top bar | yes | Collection switcher, refresh, account |
| Environment band | yes | One line strip |
| Header | scrolls | "Queue", the count as a numeral with its unit, the freshness line |
| Search and filters | scrolls, sticks | The search field with the filter control beside it; filters open a sheet |
| Rows | scrolls | The list |
| Navigation pill | yes | Queue, Intake, Sources |

### 4.3 Region editor
Full screen route (05 section 3.6): top bar (back, title, save), the
photograph band as a collapsing header floored at 0.40, the coordinate form
and provenance scrolling beneath, order controls as the top bar's overflow,
no pill.

### 4.4 Intake and capture
One scroll: the batch header, the capture card, the pre-upload checks, the
manifest, each a section with an `s6` gap; the upload action in the decision
bar slot; the pill visible.

### 4.5 Sources
One scroll: a heading (V2-4), the import action, the rows; the pill visible.

### 4.6 Sign in, help, setup
One scroll each; the band strip; no pill on sign in.

## 5. Gates

All under `apps/specimen_digitization/test/composition/`, run against every
routed screen at 390 by 844, 768 by 1024, 1180 by 820 and 1440 by 900 in both
modes and at 1.0, 1.3 and 2.0 text scale, from the same harness the size class
goldens use:

| Gate | What it measures | Allowance |
|---|---|---|
| `no_nested_scrollables` | Walks the element tree: a vertical `Scrollable` with a vertical `Scrollable` ancestor fails; `shrinkWrap: true` and `NeverScrollableScrollPhysics` under `lib/` fail as text | Horizontal strips; a sheet or dialog's own scroll |
| `surface_depth` | The deepest chain of `Surface` and `GlassSurface` ancestors on the screen, and the count of `GlassSurface` render objects | 1 at compact, 2 above; glass per class per 09 |
| `chrome_budget` | The sum of the pinned regions' heights over the viewport height, read from render boxes the screens mark with a `PinnedChrome` marker widget the package provides | 28, 24, 20 percent |
| `above_the_fold` | The primary region marked `PrimaryRegion` is laid out within the first viewport at its minimum height, with the next region's first row visible | per screen table |
| `one_job` | No two `Text` nodes in pinned regions carry the same string; no screen has a row whose only content is a back action | none |

The size class goldens pick up every change, and the fit matrix stays as it
is. Screen goldens and fixtures are regenerated once per wave by the
integrator, as before.

**The allowances, as built (2026-09-17, slot A4).** Every gate runs one test
per cell, and a cell is one screen at one window; both modes and all three text
scales are swept inside it and the worst reading is what the cell reports. Mode
and scale are deliberately not part of a cell's name: a composition defect is a
property of an arrangement, an arrangement is chosen by the window class, and a
screen that broke the contract in dark and not in light would be a finding
about the theme. `above_the_fold` runs at compact only, because the clause is
about a phone and a window with room to spare has no fold to be below. The
matrix is the eight routed locations, plus the import sheet and the region
editor, which are surfaces a screen opens over itself and compose in their own
right; `verify` is behind a redirect the fixture session does not reach, as the
fit matrix of 12 also recorded.

Three counting decisions the clauses do not settle on their own. A rail and a
sidebar are not chrome: they are laid out beside the body, so they spend width,
and the budget in section 2.3 is a share of the height. Depth is counted over
every `Surface` and `GlassSurface`, blurred or solid, because a pane a reader
sees inside another is nesting whatever it is filled with; the pane budget is
counted over the panes that blur, which is what `glass_budget` counts too.
**Amendment, wave A integration (2026-09-17).** The first form of this gate
counted every `GlassSurface` toward the class budget, on the reasoning that a
pane whose sigma the quality setting has turned off is still a pane a reader
sees. The wave A amendment to section 2.2 then made the solid form deliberate:
the scaffold publishes `GlassQuality.off` to every region it does not float, so
the top bar that scrolls under, the band and a collapsed header's chrome draw
solid by design, and counting them as panes left seven backlog lines no screen
slot could close. The budget is the count of save layers (09 section 3.3), a
solid fill is not one, and the gate reads `BackdropFilter` under a
`GlassSurface`, as `glass_budget` always has. And
every gate sweeps each screen's scroll views to their end before it reads the
tree, because a `ListView` builds only the rows its viewport holds: intake's
manifest is the third child of the page's list on a phone and is not in the
tree at all until the page is scrolled to it.

The backlogs the gates start with, each one a line a wave A slot deletes as it
fixes the screen, and each one checked in both directions so a line cannot
outlive what it allows:

| Gate | Cells | What they are |
|---|---|---|
| `no_nested_scrollables` | 7 | Intake at compact nests the manifest list in the page's list. The import sheet at all four windows, and the region editor at expanded and large, put a `SingleChildScrollView` inside the one `UiDialog` and `UiSheet` already wrap a body in. Two files under `lib/` still write `shrinkWrap` or `NeverScrollableScrollPhysics`, three occurrences. |
| `surface_depth` | 1 depth, 7 panes | The record at compact stacks two surfaces where compact allows one. On panes, six of the seven are one sentence: `UiTopBar` fills with `glass.flat` the moment the body scrolls under it and the pill is already a pane, so every compact screen that scrolls has two. The record at compact has four and at medium three. |
| `chrome_budget` | 4 | The record screen at all four windows: 54 percent of the viewport at compact against 28, 28 against 24 at medium, 32 against 20 at expanded, 29 against 20 at large. |
| `above_the_fold` | 3 | The record's photograph shows 168 dp of the 338 that 40 percent of a phone asks for. Intake's capture card is 1018 dp tall inside 844. The queue holds the fold at 1.0 and 1.3 and loses it at 2.0. |
| `one_job` | 3 | The "Back to queue" row on the record at compact, medium and expanded. No pinned region repeats another's words today, and that clause starts at zero. |

Two of those were found by the gates rather than predicted by section 0: the
region editor's nested scroll above the expanded floor, and the second glass
pane every compact screen gains on its first scroll, which `glass_budget` never
saw because it counts at rest.

The `PinnedChrome` and `PrimaryRegion` markers are read by name, and their
`extent` and `minExtent` through a dynamic call, so the gates measure a screen
that has moved to the markers and a screen that has not without waiting for
either. Where any marker is mounted, only markers are counted; where none is,
the gates measure the widgets that draw the five regions section 2.3 names. The
integrator replaces the three readers with an import once A1 is merged.

## 6. Work breakdown

Team A, composition. A1 first, then A2 to A4 in parallel from its merge.

| Slot | Branch | Owns | Delivers |
|---|---|---|---|
| A1 patterns | `fe/compose-package` | the package: `UiCollapsingHeader`, `UiStatusStrip`, `UiDecisionBar`, `UiBanner.strip`, `UiScaffold` by route (pill and band), the `PinnedChrome` and `PrimaryRegion` markers, the scaffold action bar hook; a Composition gallery page; contract tests | Section 3 |
| A2 record | `fe/compose-record` | `workbench.dart`, `screens/workbench/*`, `decision_bar.dart`, `source_pane.dart`, `region_editor.dart`, their tests | 4.1 and 4.3 |
| A3 shell and lists | `fe/compose-shell` | `app/shell.dart`, `app/app_router.dart`, `screens/queue/*`, `intake.dart`, `screens/intake/*`, `screens/sources/*`, `sources.dart`, sign in, help, setup, `widgets/environment_banner.dart`, their tests | 4.2, 4.4, 4.5, 4.6 and 2.3's shell rules |
| A4 gates | `fe/compose-gates` | `test/composition/*`, the per screen expectations table, a capture script that drives the Android emulator and the iPad simulator through every route at phone and tablet size for the checkpoint | Section 5 |

Team B, release readiness, runs beside team A; its slots touch no screen.
See `docs/execution/FRONT_END_REFACTOR.md` section 3I.
