# 12. Verification report v2

Step 7 of the sequencing in [00-north-star.md](00-north-star.md), taken again
against the rebuilt client: the eight dimensions of the bar, re-measured with
the instruments the first report used, plus the three the refactor added and
the first report had no way to take.

Branch verified: `fe/verification`, cut from `front-end-refactor` at `cbe78eb`,
which is every wave of `docs/execution/FRONT_END_REFACTOR.md` merged: waves 0,
1, 2, F, G, wave 3 and polish 2. Every screen is on `specimen_ui`. Toolchain
Flutter 3.38.5, Dart 3.10.4, on macOS 26.6.2, Apple silicon.

The first report is [08-verification-report.md](08-verification-report.md). It
measured the v1 client, whose interface was Material 3 with the product's
tokens on it. This one measures the owned component library that replaced it,
so the two are not two runs of one instrument: half the findings in 08 are
about widgets that no longer exist. Where a finding in 08 is still closed, this
report says which test holds it. Where a dimension could not be re-measured,
it says so and names what would take the measurement, rather than carrying 08's
verdict forward under a new date.

The honesty invariants of the north star bind this document about itself.
Unmeasured stays unmeasured. No score appears without its components. A number
that came from a simulator is labelled as coming from a simulator.

## Executive summary

**Six new defects, two of them severity 2, and the worst is on the first screen
every reviewer sees.** The environment band, the strip that says
"Not approved museum records", is painted over by the sky field on every entry
screen. Its own tokens measure 9.31:1 in light and 8.21:1 in dark; on the
sign in screen it renders at 3.31:1 to 5.91:1 in light and 4.23:1 to 4.40:1 in
dark, and six of those eight cells are under the WCAG 2.2 AA floor. The cause
is one line in a package primitive: `FieldPainter` clips to its own bounds only
when it has an exclusion rectangle, so a field whose circle reaches above the
layer paints over whatever the enclosing column drew first. See V2-1.

**The fit lens is clean.** Eleven screens at the four window classes and text
scales 1.0, 1.3 and 2.0 is 132 cells; none overflows, 123 hold their intended
arrangement and 9 are squeezed into a scroll they do not need at 1.0. That is
the refactor's headline result and it is the dimension 08 could not report,
because the size class goldens carry 1.0 and 2.0 only and nothing in this
repository pictured 1.3.

**Reduced motion is 10 of 14.** Ten of the fourteen transitions a reviewer
crosses collapse to instant under both signals. The four that do not are the
same two transitions counted twice: a route push below the large breakpoint and
a change of navigation destination. On the Android signal each still runs for
23 ms, which is Flutter's own five percent compression and is what 04 section
2.5 expects. On the iOS signal each runs for **451 ms**, the full Cupertino
slide, because nothing in the page transition path reads
`AccessibilityFeatures.reduceMotion`. The iPad is the primary review surface.
See V2-6.

**Glass measured on three surfaces, and the default does not move.** At the
budget maximum of four panes, one of them modal, over a ground that changes
every frame: on the web nothing measurable (0 of 699 frames over 16.7 ms at
full); on the iPad simulator 2.31 ms of raster at full against 0.52 ms with the
blur off, so four panes cost about 1.8 ms; on the Android emulator 15.77 ms at
full and 16.00 ms with the blur off, which is the emulator's own rasterizer and
not the blur. `GlassQuality.reduced` recovered nothing on any of the three.
`GlassQuality.full` stays the default on every platform, and the reason it
stays is written down rather than assumed.

**Device captures exist again, of the client that ships.** 43 captures under
[screenshots/refactor/](screenshots/refactor/), on an Android phone, an iPad
Pro 13 inch and a desktop browser, in both modes. The ones in
`screenshots/rebuild/` predate the motion and polish pull request and every
wave of the refactor, and should now be read as history.

Gates, all green on this tree: `flutter analyze --fatal-infos` clean in both
the application and the package, `flutter test` 1296 passed and 7 skipped in
the application and 684 passed in the package, the string lint 0 violations
over 202 files, and `flutter build web --release` builds.

## What was run

| Gate | Result |
|---|---|
| `flutter analyze --fatal-infos` (`packages/specimen_ui`) | No issues found |
| `flutter test` (`packages/specimen_ui`) | 684 passed, 0 failed |
| `flutter analyze --fatal-infos` (application) | No issues found |
| `flutter test` (application) | 1296 passed, 7 skipped, 0 failed |
| `uv run python scripts/ci/check_ui_strings.py --baseline scripts/ci/ui_strings_baseline.txt` | 202 files scanned, 0 violations, 0 baselined, 0 warnings |
| `flutter build web --release` | Built `build/web` |
| `flutter build ios --simulator --debug` | Built `build/ios/iphonesimulator/Runner.app` |
| `flutter build apk --profile` | Built `app-profile.apk`, 86.4 MB |

The 7 skips are the live backend HTTP tests that need a running API. The golden
image comparisons are skipped off macOS and were not skipped here: this host is
macOS, so every golden in `test/golden/images/` and every gallery golden was
compared byte for byte.

### The instruments

08 measured with the gates, 97 size class goldens, the semantics fixtures and
the keyboard walkthrough. All of those still run and all are green. This pass
keeps them and adds four files under `test/verification/`, which are the only
code this slot ships:

- **`fit_matrix_test.dart`.** Eleven screens at the four window classes and at
  1.0, 1.3 and 2.0, 132 cells. Per cell it records the navigation arrangement
  the shell chose, whether anything on screen had somewhere to scroll to, and
  whether anything laid out past the window. An overflow anywhere fails it, so
  it is a gate as well as the matrix below.
- **`reduced_motion_screens_test.dart`.** Seven transitions under each of the
  two signals 04 section 2.5 proves are not one signal. A transition that did
  not collapse is pumped a millisecond at a time until it settles, so the
  residual is a number rather than "still moving". `knownUncollapsedTransitions`
  holds the four that travel, in the shape of `knownWorkbenchOverflows`: an
  entry that starts collapsing fails the test too.
- **`dark_mode_windows_test.dart`.** Every screen at every window class in
  dark, with the WCAG AA text contrast guideline, the frosted pane count
  against the budget of 09 section 3.3, and the number of separate marks
  painted in the accent, counted off the pixels. Plus the environment band's
  own pair, in both modes, on an entry screen and inside the scaffold.
- **`verification_harness.dart`.** The measuring parts: the layout error
  collector, the arrangement probe, `measurePair` and `accentRegions`.

Two more files under `test/verification/` are run by hand rather than by
`flutter test`, because they are targets rather than tests:

- **`capture_app.dart`**, the capture target. It composes the shipped
  `SpecimenDigitizationApp` with the same fixture record the size class
  goldens are built from, so a device shows the queue and the record rather
  than the setup screen. The application's own `main()` needs Firebase and a
  production API, or a synthetic API on loopback, and neither is reachable
  from a simulator, an emulator or a browser tab without standing a server up
  outside this worktree. Nothing in the file is a screen, a widget or a token:
  every pixel a capture shows is the product's.
- **`glass_probe.dart`**, the glass measurement. It draws the budget at its
  maximum over a moving ground, cycles `GlassQuality` through its three values
  and reports the engine's own `FrameTiming` for each, on screen as well as in
  the log, so a screenshot of the device is the evidence.

### One instrument was found to be unreliable, and the finding is recorded

`textContrastGuideline` builds a histogram over a semantics node's whole
rectangle and takes the most frequent colour on each side of a luminance
threshold. It reported 17 failures in the dark sweep. Ten of them are the
instrument rather than the product, in two shapes:

- **A node whose rectangle is much wider than its glyphs.** The top bar's
  title node is the whole bar, because 11 section 3.3 gives the title an
  `Expanded`, so the histogram returns two shades of the sky behind it and
  reports 0.66:1 for a title that measures 11.22:1 against the bar. Four cells.
- **A ground that is a gradient.** The source pane's "Source photograph"
  disclosure header node is the full pane width over a near black matte, so
  both frequencies land on the matte and the guideline reports 1.06:1 for
  glyphs that measure 17.10:1. Six cells.

Each was adjudicated against the pixels with `measurePair`, which takes the
most common colour behind the words and the pixel furthest from it in
luminance. The ten are listed in `guidelineArtefacts` with the measured ratio;
the seven that the pixels agree with are listed in
`knownDarkContrastDefects` and are V2-1 and V2-2 below. Slot E4 recorded the
same class of artefact in a different shape (a control straddling a scroll
fold), and slot E3 recorded a third (a package surface measured through
Material's scrim). Three sightings of one weakness is worth one line in 06.

## The bar, one row each

| Dimension | Standard | Met | Evidence |
|---|---|---|---|
| Usability | All ten heuristics pass with no finding above severity 1 | **Not re-measured** | The 58 pass criteria of 01 were re-audited against the v1 client and are not re-audited here. Most of them are carried by tests that are still green (`keyboard_walkthrough_test.dart`, `semantics_fixtures_test.dart`, `review_batch_test.dart`, `status_timing_test.dart`, `help_and_contact_test.dart`, `reason_codes_test.dart`), so no criterion 08 closed is known to have reopened. What is new is six defects this pass found by looking, four of which a heuristic audit would have caught: V2-1 and V2-2 under heuristic 4, V2-3 under heuristic 8, V2-4 under heuristic 6. A criterion by criterion re-audit by someone who did not build the refactor is the work this row is waiting on |
| Writing | Every string passes the checklist, no string over budget, zero em-dashes | **Yes** | `check_ui_strings.py` 0 violations over 202 files; `test/theme/no_dashes_test.dart` green; no em dash or en dash anywhere in `lib/`, `test/` or the package |
| Visual system | Zero literal colors, sizes or durations in widgets; light and dark both ship; every text pair meets AA | **Partial** | The literal gates are clean: `no_color_literals_test.dart`, `no_literal_geometry_test.dart` with a shrink only backlog, `theme/contrast_test.dart` and `accessibility/contrast_test.dart`. Light and dark both ship and both are in all 121 screen goldens and all 288 matrix goldens. What is not clean is the pair that lands on a **field** rather than on one of the three opaque surfaces: every contrast table in 03 and 09 is taken over `ground`, `paper` and `matte`, and the sky composites on top of all three. V2-1 and V2-2 are both that gap, measured |
| Motion | Every animation is in the catalog with a reason and collapses under reduced motion | **Partial** | `test/motion/motion_tokens_test.dart`, `page_transitions_test.dart` and `reduced_motion_test.dart` are green, and every animation site in `lib/` still cites its catalog row. Measured on the routed application, 10 of 14 transitions collapse under both signals. The four that do not are V2-6: a route push and a destination change, 23 ms on the Android signal and 451 ms on the iOS signal |
| Adaptation | Every screen verified at compact, medium, expanded and large, both orientations, on iOS, Android and web | **Partial** | 132 measured cells over eleven screens, four window classes and three text scales, with no overflow anywhere, plus 121 screen goldens and 288 gallery matrix goldens. Device captures exist again: 43 of them, on an Android phone, an iPad Pro 13 inch and a desktop browser, in both modes. Two gaps keep this Partial: there is no Android tablet image on this machine, so the tablet class is the iPad rather than an Android tablet, and the simulator could not be rotated without a macOS accessibility grant, so **landscape is not captured on any device**. Orientation is still covered only through the width each orientation produces |
| Accessibility | WCAG 2.2 AA; VoiceOver and TalkBack scripts complete unaided; keyboard-only review on web | **Partial** | The keyboard only review passes end to end. The semantics fixtures are green and carry wave 3's four rewrites. What is left is what 08 left: VoiceOver and TalkBack have still not been run on hardware, and this pass did not run them either. Two contrast failures are open, V2-1 and V2-2 |
| Honesty | No measurement renders as zero when missing; no score without components; no forbidden action appears enabled | **Yes** | `runtime_risk_test.dart`, `pilot_evidence_test.dart` and the wire tests all green; the fields fixture shows Unknown, Unreadable and Not present as first class words; the disabled action audit in `semantics_fixtures_test.dart` finds no enabled control the server forbids. Visible in `screenshots/refactor/ipad-pro-13-portrait-record-fields-light.png` |
| Speed of review | One specimen to the next, including one correction with a reason, without leaving the keyboard on desktop | **Yes** | `test/accessibility/keyboard_walkthrough_test.dart` green, "J and K move to the next and the previous record" against the routed application. The decision bar carries the position and the two step controls at every window: `screenshots/refactor/ipad-pro-13-portrait-record-readings-light.png` |

Two dimensions moved since 08 and neither moved up. Visual system was Yes and
is Partial, because the refactor added a painted ground that no contrast table
covers. Motion was Yes and is Partial, because the refactor kept the platform
page transition and nothing in that path reads the iOS signal. Adaptation and
Accessibility stay Partial for the reasons 08 gave plus, for Adaptation, a new
one: this machine has no Android tablet.

## The fit matrix

Every screen at the four window classes and at text scales 1.0, 1.3 and 2.0,
in light. Source: `test/verification/fit_matrix_test.dart`, 132 cells, run on
2026-09-17. The verdict per cell is derived from three recorded facts: the
navigation arrangement the shell chose, whether anything had somewhere to
scroll to, and whether anything laid out past the window.

- **intended** means the cell drew the arrangement its window class declares
  and scrolled only where it scrolls at 1.0 as well.
- **squeezed** means the arrangement held but the type pushed the screen into a
  scroll it does not need at 1.0. This is the intended behaviour of 11 section
  2.2, recorded rather than assumed.
- **overflow** means content laid out past the window. There are none.

| Screen | compact 390x844 | medium 768x1024 | expanded 1180x820 | large 1440x900 |
|---|---|---|---|---|
| sign in | intended (no shell), squeezed at 1.3 and 2.0 | intended, squeezed at 2.0 | intended, squeezed at 1.3 and 2.0 | intended, squeezed at 2.0 |
| queue | intended (pill), squeezed at 2.0 | intended (rail) at all three | intended (rail extended) at all three | intended (sidebar), squeezed at 2.0 |
| filters | intended (pill, sheet) at all three | intended (rail, dialog) at all three | intended (rail extended, dialog) at all three | intended (sidebar, dialog) at all three |
| intake | intended (pill) at all three | intended (rail) at all three | intended (rail extended) at all three | intended (sidebar) at all three |
| sources | intended (pill), fits at all three | intended (rail), fits at all three | intended (rail extended), fits at all three | intended (sidebar), fits at all three |
| source | intended (pill) at all three | intended (rail), squeezed at 2.0 | intended (rail extended) at all three | intended (sidebar) at all three |
| record, readings | intended (pill) at all three | intended (rail) at all three | intended (rail extended) at all three | intended (sidebar) at all three |
| record, fields | intended (pill) at all three | intended (rail) at all three | intended (rail extended) at all three | intended (sidebar) at all three |
| record, history | intended (pill) at all three | intended (rail) at all three | intended (rail extended) at all three | intended (sidebar) at all three |
| region editor | intended (full screen route) at all three | intended (full screen route) at all three | intended (dialog) at all three | intended (dialog) at all three |
| help | intended (full screen route) at all three | intended at all three | intended at all three | intended at all three |

**123 intended, 9 squeezed, 0 overflow.** The nine are sign in at six cells,
queue at two and the source at one. Every one of them is a screen that fits at
1.0 and scrolls once the type grows, which is what 11 section 1 says a native
platform does: type scales, spacing stays fixed, content reflows. None of them
changes arrangement, clips a glyph or loses a hit box.

The two cells worth looking at by eye are **sign in at expanded 1180x820 at
1.3** and **sign in at large 1440x900 at 2.0**. The sign in screen is a single
centred column with no shell, so it has the least to give, and expanded is the
shortest of the four windows at 820 dp. It scrolls there at 1.3 while the
taller large window does not until 2.0.

### Where the matrix comes from, and what it does not cover

The gallery matrix (`packages/specimen_ui/test/gallery/goldens/matrix/`) is 288
PNGs: twelve family pages by four window classes by three text scales by two
modes, all comparing clean on this host. It pictures each control's own fit
policy. The screen size class goldens (`test/golden/images/`) are 121 PNGs:
eleven screens at four windows in two modes, with intake and the record's three
segments also at 200 percent text. They picture the screens.

Neither covers text scale 1.3 at the screen level, which is why the matrix
above is measured rather than read off a PNG. Adding 1.3 to the screen goldens
would add 121 more files and about 40 MB; measuring it costs 14 seconds and
fails the build on an overflow, which is what the goldens were being asked for.

`extraLarge`, from 1600 dp, is not a column of either matrix. Slot G3 recorded
that for the gallery and the same holds here.

## Motion and reduced motion

Source: `test/verification/reduced_motion_screens_test.dart`, run on
2026-09-17, on the routed application. Each transition is crossed, one frame is
pumped with no clock advance, and the tree is asked whether anything is still
travelling. A transition that is still travelling is then pumped a millisecond
at a time until it settles.

| Transition | Android signal (`disableAnimations`) | iOS signal (`reduceMotion`) |
|---|---|---|
| The queue at rest once it has loaded | collapsed | collapsed |
| Queue to record, push below large | **travels, residual 23 ms** | **travels, residual 451 ms** |
| Queue to record, cross fade at large | collapsed | collapsed |
| The record's evidence segment change | collapsed | collapsed |
| The filter surface entering | collapsed | collapsed |
| Help entering | collapsed | collapsed |
| A navigation destination change | **travels, residual 23 ms** | **travels, residual 451 ms** |

Ten of fourteen collapse. The four that do not are the same two transitions
under the two signals, and both are the platform page transition rather than
anything the product animates: `MaterialPage` at
`lib/src/app/app_router.dart:233` for a record below the large breakpoint, and
the default page for the `builder:` routes at `:218` and `:266`, which is what
a change of destination pushes.

**23 ms on Android is not a defect.** 04 section 2.5 records that Flutter runs
every default `AnimationController` at five percent of its duration when
`SemanticsBinding.instance.disableAnimations` is true, and five percent of the
450 ms `PredictiveBackPageTransitionsBuilder` is 22.5 ms. The measurement
agrees with the document to half a millisecond, which is the check.

**451 ms on iOS is V2-6.** iOS sets `reduceMotion` and never sets
`disableAnimations`, so Flutter compresses nothing, and
`specimenPageTransitions` at `lib/main.dart:277` names
`CupertinoPageTransitionsBuilder` with no reduced motion branch. On an iPad
with Reduce Motion on, opening a record from the queue below 1200 dp performs
the full horizontal slide. 04 section 2.5 states the rule and names iOS as the
platform where reading `MediaQuery` alone ships a spec that is broken for the
reviewers most likely to need it. That is exactly what happened, one layer
higher than the token layer it was written about.

Everything the product animates itself is correct, including the three
signature motions: the sky cross fades between presets at `motion.standard`,
which is zero under reduced motion, and the panel change is a cross fade in
place with no `SlideTransition` under the switcher, which the test asserts
directly.

## Dark mode at every window class

Source: `test/verification/dark_mode_windows_test.dart`, 58 tests, run on
2026-09-17. Ten screens at the four window classes in dark, plus the two token
level checks and the environment band in both modes.

### Glass over the darkest field

The worst ground `ink` is asked to sit on is a frosted pane over the matte.
Measured from the tokens rather than asserted:

| Pair | Composite | Ratio |
|---|---|---|
| `ink` on `glass.flat` over `matte`, dark | `#1d1f23` | **14.71:1** |
| `ink` on `glass.modal` over `matte`, dark, blurred | | 14.71:1 |
| `ink` on `glass.modal` over `matte`, dark, `GlassQuality.off` | | 15.67:1 |

Both clear 4.5:1 by a wide margin, and the opaque fallback a slow device gets
reads no worse than the blurred pane it replaces, which is the property that
makes `GlassQuality.off` safe to ship.

### The pane budget

09 section 3.3 allows four frosted panes per window and one modal. Measured on
every screen at every window class in dark:

| Screen | compact | medium | expanded | large |
|---|---|---|---|---|
| sign in | 0 | 0 | 0 | 0 |
| queue | 1 | 0 | 0 | 1 |
| filters | 2 (1 modal) | 1 (1 modal) | 1 (1 modal) | 2 (1 modal) |
| intake | 1 | 0 | 0 | 1 |
| sources | 1 | 0 | 0 | 1 |
| source | 1 | 0 | 0 | 1 |
| record, readings | 3 | 2 | 1 | 3 |
| record, fields | 3 | 2 | 1 | 3 |
| record, history | 3 | 2 | 1 | 3 |
| help | 1 | 1 | 1 | 1 |

The maximum anywhere is three, on the record at compact and at large. The
budget is not close to being spent, and no screen shows two modals.

### The accent, one use per screen

09 section 3.1 gives the accent one job: the current position, the active
marker, the mark. "One use per screen" is a rule about what a reviewer's eye
lands on, so it is counted off the pixels: a connected run of at least 16
pixels within 8 of `#E8FF47`, on the rendered frame.

Every screen with the shell reports **exactly one** accent mark at every window
class: the product mark that leads the rail and the sidebar. Sign in reports
one, which is the mark above the form. Filters and help report **zero**, which
is correct: a modal is open over the shell on filters, and help is a full
screen route with no mark. The navigation's current destination is drawn as an
ink disc rather than in the accent, which is 09 section 3.1's rule followed.

The rule holds on all 40 cells, which is the first time it has been counted
rather than asserted.

### Contrast

Seventeen of the forty cells failed `textContrastGuideline`. Ten are the
instrument, adjudicated above and listed in `guidelineArtefacts`. Seven are
real and are two defects:

- **sign in at all four window classes** is V2-1, the band under the sky.
- **queue at compact, medium and expanded** is V2-2, the freshness line over
  the sun field. The queue at large does not report it because at large the
  guideline hits the top bar artefact first and stops there, which is another
  reason the artefacts are worth retiring.

Everything else reads. The dark tokens are not an inversion of the light ones
and the photograph sits on a fixed dark matte in both modes, which is visible
in `screenshots/refactor/ipad-pro-13-portrait-record-readings-dark.png`: the
1912 label reads as paper rather than as a glowing rectangle.

## Glass: the measurement, and why the default does not move

`GlassQuality`'s own doc comment says the default per platform "is a
measurement, recorded in the verification report, not a preference". No
measurement had been taken. `GlassQuality` appears nowhere in
`docs/SESSION_LEARNINGS.md`, and `UiThemeData.light` and `.dark` both default
to `GlassQuality.full` on every platform. This is that measurement.

`test/verification/glass_probe.dart` draws the budget at its maximum, four
panes with one of them modal, over a `FieldLayer` that drifts every frame so no
pane's blur can be reused, and cycles the quality through its three values for
six seconds each, reporting the engine's own `FrameTiming`.

| Surface | Quality | Frames | Build median/worst ms | Raster median/worst ms | Frames over 16.7 ms |
|---|---|---|---|---|---|
| Web, Chromium 152, CanvasKit, 1180x820 at dpr 2, profile | full | 699 | 0.60 / 1.80 | 0.10 / 0.30 | 0 |
| | reduced | 715 | 0.50 / 0.90 | 0.00 / 0.50 | 0 |
| | off | 714 | 0.50 / 1.10 | 0.00 / 0.20 | 0 |
| iPad Pro 13 inch (M5) simulator, 1032x1376 at dpr 2, debug | full | 336 | 0.86 / 1.60 | 2.31 / 3.63 | 336 of 336 |
| | reduced | 344 | 0.69 / 1.09 | 2.37 / 3.21 | 344 of 344 |
| | off | 344 | 0.52 / 1.09 | 0.52 / 0.78 | 344 of 344 |
| Android emulator, Medium Phone API 36, 1080x2400 at 420 dpi, profile | full | 254 | 0.31 / 9.48 | 15.77 / 41.03 | 198 of 254 |
| | reduced | 330 | 0.32 / 4.12 | 15.70 / 44.18 | 261 of 330 |
| | off | 334 | 0.30 / 0.71 | 16.00 / 38.28 | 275 of 334 |

Read these three rows as three different things, because they are.

**The web is free.** Not one frame of 699 exceeded 16.7 ms at full quality, and
the raster phase is a tenth of a millisecond. CanvasKit hands the blur to the
GPU and the Dart side never waits for it, so `rasterDuration` here is
submission rather than work, but the frame count settles it: 699 frames in six
seconds is 116 per second, which is this display's own cadence sustained with
four frosted panes on screen.

**The iPad simulator is where the blur is visible, and it costs 1.8 ms.** The
raster phase is 2.31 ms at full and 0.52 ms with the blur off. The "frames over
16.7 ms" column counts `totalSpan`, which is vsync to raster finish and
therefore includes the wait for the display; the work is build plus raster,
which is 3.17 ms at full. This is a debug build on the Mac's own GPU, so it is
not an iPad's number. It is a number about the blur, and the blur is the part
that does not change between a simulator and the device it simulates in kind,
only in degree.

**The Android emulator cannot answer the question.** The raster phase is 15.77
ms at full and 16.00 ms with the blur off, which is to say the blur is not
what the emulator spends its frame on. The emulator's own rasterizer costs
about 16 ms whatever is drawn, so it cannot discriminate between the three
settings and must not be used to choose between them.

**`GlassQuality.reduced` recovered nothing anywhere it could be measured.**
2.37 ms against 2.31 ms on the iPad simulator, and 0.00 against 0.10 on the
web. Halving the sigma does not halve the cost, because the cost is the save
layer and the blur pass rather than the radius. That is worth knowing
independently of the default: `reduced` is not a useful middle setting on
either rasterizer measured, and a device that cannot afford `full` will need
`off`.

**Decision: `GlassQuality.full` stays the default on every platform.** No
surface measured showed a cost a lower setting would recover, and the one
middle setting available recovers nothing. `packages/specimen_ui/lib/src/foundation/glass.dart`
is unchanged except for a doc line pointing at this section, which is what its
own comment asked for.

**What would change the answer.** An iPad or an Android phone in hand, in a
profile build, running the probe. The three numbers above come from a browser,
a simulator and an emulator, and only the first of the three is the surface it
represents.

## Device captures

43 captures under [screenshots/refactor/](screenshots/refactor/), taken on
2026-09-17 against `cbe78eb` with `test/verification/capture_app.dart`. Every
one is the shipped client with the size class goldens' own fixture record
behind it.

| Surface | What it is | Window class | Screens | Modes |
|---|---|---|---|---|
| `android-phone-*` | Android emulator, Medium Phone API 36, 411 x 914 dp | compact | queue, record readings, intake, sign in, help | light and dark |
| `ipad-pro-13-portrait-*` | iOS simulator, iPad Pro 13 inch (M5), 1032 x 1376 dp | expanded | queue, record readings, record fields, record history, intake, sources, source, sign in, help | light and dark |
| `desktop-web-1180x820-*` | Google Chrome 153 headless, 1180 x 820 | expanded | queue, record readings, intake, sources, source, sign in, help | light and dark |

Plus `android-phone-queue-light-scrolled-to-end.png`, which is the evidence for
V2-3 rather than a capture of a screen.

**Three gaps, recorded rather than papered over.**

1. **There is no Android tablet image on this machine.** `flutter emulators`
   lists one emulator, `Medium_Phone_API_36`. The tablet class is therefore the
   iPad Pro 13 inch simulator, named as such in every filename. No capture in
   this folder is presented as an Android tablet.
2. **No capture is in landscape.** `xcrun simctl` has no rotate verb, and
   rotating the Simulator through its own Device menu needs a macOS
   accessibility grant this session cannot ask for. The iPad in portrait is
   1032 dp wide, which is `expanded`; in landscape it would be 1376 dp, which
   is `large`. So **the `large` window class has no device capture at all**,
   and the desktop browser row above is `expanded` too, because 1180 dp is
   `expanded`. The `large` class is covered by goldens and by the fit matrix
   and by nothing on a device.
3. **The iOS simulator refuses profile mode**, so the iPad captures are debug
   builds. Nothing a capture shows differs between debug and profile, but the
   frame timings in the glass section do, and they are labelled.

The Android sign in and help captures, and the iPad's, are from builds with
`--dart-define=CAPTURE_SIGNED_OUT=true` and
`--dart-define=CAPTURE_LOCATION=/help`, because the account menu did not open
to a synthetic tap on the simulator and a build is more honest than a tap that
may have missed.

## Web smoke

`flutter build web --release` builds. Served from a loopback static server and
walked through every route in the table, twice: once on the release build and
once on the profile build of the capture target, which is the one where the
collection routes resolve to a screen rather than to setup.

Routes walked: `/setup`, `/sign-in`, `/verify`, `/help`, `/gallery`,
`/c/org%2Finsects/queue`, `/c/org%2Finsects/queue/fixture-001`,
`/c/org%2Finsects/intake`, `/c/org%2Finsects/intake/sources`,
`/c/org%2Finsects/intake/sources/src-1`.

**Console errors: one, and it is the server rather than the application.**
`Failed to register a ServiceWorker ... An unknown error occurred when fetching
the script`, once per page load, on both builds. `flutter_service_worker.js`
answers 200 from both servers, so the registration failure is the browsing
context rather than a missing or broken asset. No Dart exception, no assertion,
no asset 404, no layout error on any route.

On the release build every collection route redirects to setup and the screen
says "Collection connection required", because a release build with the CI
Firebase placeholder has no session and no API. That is the redirect chain of
`app_router.dart` working, not a failure: the routes resolve, the redirect
fires, and the honest screen is what a reviewer sees.

`/gallery` is mounted only outside release builds, so it is absent from the
release build and present on the profile build. Both are correct.

## Defects, ranked

Severity 0 is "a reviewer cannot do the job", 4 is "a reviewer would not
notice". None of these is fixed here: this slot owns the report, not the code.
Each names the file and the line for the integrator.

### V2-1, severity 2: the sky field paints over the environment band

**What a reviewer sees.** On sign in, verify and setup, the strip that says
"Test environment. Not approved museum records." is washed by whichever field
of the sky sits behind it. In light at a large window the band's fill renders
`#F3FA74` instead of `#F7E3B4` and its text `#937F8E` instead of `#4A3400`. In
dark at compact the fill renders `#685E08` instead of `#4A3608`.

**Measured.** `test/verification/dark_mode_windows_test.dart`, "the band on
sign in at ...", which pins each number:

| Window | light | dark |
|---|---|---|
| compact 390x844 | 4.63:1 | 4.33:1 |
| medium 768x1024 | 5.91:1 | 4.40:1 |
| expanded 1180x820 | 3.64:1 | 4.34:1 |
| large 1440x900 | 3.31:1 | 4.23:1 |

The band's own tokens are `environmentOnFill` on `environmentFill`, which
measure **9.31:1 in light and 8.21:1 in dark**. Six of the eight cells are
below the WCAG 2.2 AA floor of 4.5:1 and the worst, light at large, is 3.31:1.
For scale: finding V-8 in 08, which was treated as a defect worth closing in
its own pass, was 2.26:1 to 2.39:1.

**The control.** The same band inside the scaffold, on the queue, measures
exactly 9.31:1 and 8.21:1 at all eight cells. The same test asserts that, so
the two halves cannot drift apart.

**Cause, in two places.**

1. `packages/specimen_ui/lib/src/primitives/field_layer.dart`, `FieldPainter.paint`.
   The canvas is clipped to `bounds` only inside `if (clip != null)`, which is
   only when an exclusion rectangle was passed. The `canvas.drawCircle` calls
   at the end of the method are otherwise unbounded, and the enclosing `Stack`
   pushes no clip layer because a `Positioned.fill` child produces no visual
   overflow for it to detect. A field whose circle reaches above the layer
   therefore paints over whatever the enclosing column drew first.
2. `lib/src/app/app_router.dart:439-461`, `_EnvironmentFrame`. It puts the band
   in a `Column` above the screen's own `UiScaffold`, so the band is what the
   unbounded painter reaches. Inside the scaffold the band is a sibling of the
   sky in the same `Stack` and paints after it, which is why the collection
   screens are correct.

**Suggested owner.** The package, for the clip: `FieldPainter.paint` should
clip to `bounds` whether or not it has an exclusion, and the fix is moving one
`clipRect` out of the `if`. The application, for the frame: passing the band
through `UiScaffold.banner` on the entry screens would also close it, and would
be the same anatomy the collection screens already use. Both are worth doing;
the first is the one that stops the class of defect rather than this instance.

**Evidence to look at.** `screenshots/refactor/android-phone-signin-light.png`
is the clearest. `desktop-web-1180x820-signin-light.png` and
`ipad-pro-13-portrait-signin-dark.png` show the same thing at the other two
classes.

### V2-2, severity 3: the queue's freshness line does not clear AA over the sky

**What a reviewer sees.** "Updated 14 s ago" under the queue's count line, in
grey over the yellow of the sun field.

**Measured.** `ink.tertiary` is `#9599A0`. It clears **6.70:1 over `ground`,
6.21:1 over `paper` and 5.70:1 over `matte`**, which is every surface 03 and 09
take a ratio over. Over the sun field at its centre, composited `#444A0C`, it
measures **3.29:1**. Where the line actually sits on the queue, read off the
dark golden, the glyphs are `#9599A0` against a local ground of `#3A3F0D`,
which is **3.87:1**, and 4.15:1 between the extremes of its rectangle. The
guideline reports 4.28, 4.04 and 4.05 at compact, medium and expanded in dark.

**Cause.** `lib/src/screens/queue/queue_screen.dart:769`,
`ui.type.bodySmall.copyWith(color: ui.color.inkTertiary)`. The line is correct
against every surface the token table covers; the sky is a fourth ground and
the table does not cover it.

**Suggested owner.** The application for the line, which wants `ink.secondary`
or its own surface. The design system for the rule: 09 section 3.2 should say
what a text pair is allowed to be over a field, and the contrast test should
take the composite. This is the general form of the same gap V2-1 exposes, and
closing the rule closes both classes rather than two instances.

### V2-3, severity 2: the last queue row sits under the floating navigation and cannot be scrolled clear

**What a reviewer sees.** On a phone, the disposition chips of the last record
in the queue are behind the floating pill navigation. Scrolling does not
uncover them: the list is already at its end.

**Measured.** Android emulator, 411 x 914 dp, six full swipes to the end of the
list. `screenshots/refactor/android-phone-queue-light-scrolled-to-end.png`:
"Needs review" on Pinned beetle 4 is cut in half and "Not calibrated" is partly
behind the capsule.

**Cause.** `lib/src/screens/queue/queue_screen.dart:416-424`. The list's
padding is `EdgeInsetsDirectional.symmetric(horizontal: gutter, vertical:
ui.space.s4)` and never reads `UiScaffold.of(context).bottomInset`. `UiScaffold`
floats its chrome over the body rather than reserving room in it, which slot E4
recorded and fixed for the record's decision bar:
`lib/src/screens/workbench/decision_bar.dart:137-141` reads `bottomInset` and
clears the pill. The queue's list did not get the same treatment.
`grep -rn bottomInset lib/` returns that one site.

**Not intake.** Intake's body does scroll clear of the pill; it needed more
swipes than the first attempt gave it. The defect is the queue list.

**Suggested owner.** The application, one line in the list's padding. The
package, for the general form: E4's closeout already asks for "a way for a
routed screen to fill `UiScaffold.actionBar`" and notes that "until then a
screen also has to pad itself by `bottomInset`". Two screens have now been
caught by that, one fixed and one not.

### V2-4, severity 3: the registered sources list states nothing about itself

**What a reviewer sees.** Tapping "Add from storage" lands on a screen with no
heading, no count and no way back other than the system gesture: one row under
the environment band. Every other screen in the product states its name.

**Measured.** `screenshots/refactor/ipad-pro-13-portrait-sources-light.png`
against `ipad-pro-13-portrait-source-light.png`, which is the screen one tap
further in and which does have a heading, a count and a listed date.

**Cause.** `lib/src/screens/sources/sources_screen.dart`, 154 lines, has titles
only on its two empty states (`:65`, `:91`) and on each row (`:142`). There is
no page header.

**Suggested owner.** The application. 07 section 13 gives sources a blueprint;
the heading is in it and the screen does not draw it.

### V2-5, severity 4: the application declares a second `FieldLayer`

`lib/src/widgets/field_row.dart:19` declares `enum FieldLayer`, the literal,
parsed and normalized layers of a field value. `package:specimen_ui` exports
`FieldLayer`, the widget that paints the sky. Any file that imports both must
alias one of them, which is how this was found: a probe importing
`widgets.dart` and `specimen_ui.dart` would not compile.

09 section 7 asks one word to mean one thing. This costs nothing today because
no file needs both, and it costs an import alias the first time one does.

**Suggested owner.** The application. `FieldValueLayer` says what the enum is
and frees the noun.

### V2-6, severity 3: a page transition does not collapse under reduced motion on iOS

**Measured.** 451 ms of residual travel, with a `SlideTransition` and a
`FadeTransition` part way, one frame after the reviewer crossed the transition,
under `AccessibilityFeatures.reduceMotion` on `TargetPlatform.iOS`. Two
transitions: opening a record from the queue below the large breakpoint, and
changing navigation destination. On the Android signal the same two run for
23 ms, which is Flutter's own five percent of 450 and is what 04 section 2.5
expects.

**Cause.** `lib/main.dart:277-286`, `specimenPageTransitions`, names
`CupertinoPageTransitionsBuilder` for iOS with no reduced motion branch, and
`lib/src/app/app_router.dart:233` uses `MaterialPage` for a record below large
while `:218` and `:266` use go_router's default page for the queue and intake
branches. `PageTransitionsTheme` has no access to the accessibility features,
and the one place in the product that does, `MotionTokens.prefersReducedMotion`,
is not consulted on this path.

The shape of the fix is already in the tree twice: `helpPage` in
`lib/src/app/help_screen.dart:76-98` and the large window record page in
`app_router.dart:236-260` both build a `CustomTransitionPage` whose duration is
`context.ui.motion.standard`, which is zero under reduced motion. Giving the
same treatment to the pages that currently take the platform default would
close it, at the cost of the iOS edge swipe, which slot E3 already recorded as
the price of leaving `MaterialPageRoute`.

**Suggested owner.** The application. 04 section 6.1 keeps the platform
transitions on purpose, so this is a change to that document as well as to the
code: either 04 gains a sentence saying the platform transition is the one
motion that keeps its travel under reduced motion, with the reason, or the
routes stop using it.

### Still open from the first report

08 left four pass criteria Partial, and nothing in this pass changes any of
them: 7.2 waits on one client path moving onto the batch endpoint, 7.6's unused
half waits on a key, 10.3 waits on a deployment setting `SPECIMEN_ADMIN_CONTACT`,
and 10.4 waits on two people. Its defect list is otherwise empty and this pass
found nothing that reopens an entry on it.

### Carried from the wave closeouts, not re-measured here

The wave F, G, 3 and polish 2 closeouts in `docs/SESSION_LEARNINGS.md` leave a
number of items open that this report does not adjudicate, because they are
package and document decisions rather than measurements. The four the integrator
is most likely to want beside this report:

- **`UiBannerStyle.maxLines` is 2 and three would fit.** Wave G measured that
  three lines clear finding V-15's height ceiling at 200 percent text on a
  phone, and left the call to the integrator because no document asks for
  three. Still open. Related to V2-1 only in that both are about this band.
- **Two gallery foundation pages overflow at a phone width** and are recorded
  as nobody's slot: `gallery/pages/shape_page.dart:68` by 3 dp at 360, and
  `gallery/pages/type_page.dart:64` above scale 1.0. They are in
  `overflowBacklog` and in `knownNarrowOverflows`.
- **The region editor's dialog is capped at 560 dp** and 05 section 3.6
  assigns it `DialogWidths.wide`, 640. The two disagree today.
- **`app_router.dart` still carries its bridge `Scaffold`**, marked
  `TODO(fe/wave-3)`. Slots E3, E4 and E5 each recorded that nothing they own
  needs it any more.

## What a first-time reviewer should look at

Six images, in this order. About four minutes, and they carry what changed and
what is wrong.

1. **`design/screenshots/refactor/android-phone-signin-light.png`.** The first
   screen a reviewer sees, on a phone. Read the band at the top: the sentence
   that says these are not approved museum records is the least legible text on
   the screen. That is V2-1, and it is the worst thing in this report.

2. **`design/screenshots/refactor/ipad-pro-13-portrait-record-readings-light.png`.**
   The review desk working, on the tablet class, with real type rather than the
   test font. The photograph on the left with its label regions, the two
   independent readings on the right with the character that differs underlined
   rather than coloured, the segment selector, the blockers line, the decision
   bar pinned at the foot with the position and the two step controls. This is
   the bar the rest is measured against.

3. **`design/screenshots/refactor/android-phone-queue-light-scrolled-to-end.png`.**
   The queue on a phone, scrolled as far as it goes. The last record's
   disposition is behind the navigation capsule and no amount of scrolling
   moves it. That is V2-3.

4. **`design/screenshots/refactor/ipad-pro-13-portrait-record-fields-dark.png`.**
   Dark mode on the record's fields, where the honesty invariants are visible:
   Unknown, Unreadable and Not present as first class words with their own
   glyph, and the photograph on a matte that keeps 1912 paper looking like
   paper.

5. **`test/golden/images/queue__large-1440x900__dark.png`.** The desktop
   layout at the one window class no device capture covers, in the test font.
   The sidebar, the list beside the empty detail pane, the collection switcher
   in the bar. Look at "Updated 0 s ago" under the count: that is V2-2.

6. **`packages/specimen_ui/test/gallery/goldens/matrix/fit_compact_2.0_light.png`.**
   The fit page at a phone width and 200 percent text, which is where wave G's
   work is visible: every control at 480, 360, 280 and 200 dp, each one in its
   declared compact variant rather than broken into letters. Compare it against
   the same file's description in the slot G3 closeout, written before G1 and
   G2 landed, to see what the fit rules bought.

## What is not measured

Stated plainly, because a verification report that does not say what it did not
do is not one.

- **The 58 pass criteria of the heuristics audit.** Not re-audited. This pass
  measured, it did not walk the flows criterion by criterion, and a re-audit by
  someone who did not build the refactor is what the Usability row is waiting on.
- **VoiceOver and TalkBack on hardware.** Not run, as in 08. The semantics
  fixtures say what the tree publishes; they do not say what a screen reader
  reads out.
- **Any landscape window on any device.** See the device captures section.
- **The `large` window class on a device.** Same reason.
- **An Android tablet.** No image on this machine.
- **Glass on real hardware.** A browser, a simulator and an emulator, none of
  which is a phone or a tablet.
- **The two entry screens other than sign in.** Verify and setup share
  `_EnvironmentFrame` with sign in, so V2-1 applies to them by construction,
  but neither is in the fit matrix or the capture set: both are behind a
  redirect that the fixture session does not reach.
- **Timed task walkthrough.** The Speed of review row is carried by the
  keyboard walkthrough test rather than by a stopwatch over a reviewer, which
  is what the north star's "How we check" column names.
