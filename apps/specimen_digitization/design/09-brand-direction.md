# 09. Brand direction: an instrument under frosted glass

Status: **agreed direction, not yet built.** Written 2026-09-16 after the
rebuild shipped and was judged to read as stock Material 3. This document
replaces section 2 (brand direction), section 3 (color), section 4
(typography), section 5.3 (shape) and section 6 (iconography) of
[03-design-system.md](03-design-system.md). Everything else in 03 stands:
the eight principles in section 1, spacing in 5.1, sizing in 5.2, touch
targets in 5.5, density in 5.6, the atomic inventory in 7, and the testing
approach in 8. The v1 tables stay in 03 as the record of what shipped.

The component library that renders this direction is specified in
[10-component-library.md](10-component-library.md). The build plan is in
[../../../docs/execution/FRONT_END_REFACTOR.md](../../../docs/execution/FRONT_END_REFACTOR.md).

## 0. Why the rebuild still looked like Google

The v1 foundation did the token work and kept every Material component. Three
things carried Google's identity through untouched:

1. **The fonts never shipped.** `bundledProductFonts` is `false`
   (`lib/src/theme/typography.dart:139`), there is no `assets/` directory and no
   `fonts:` entry in `pubspec.yaml`. Every screenshot in `screenshots/rebuild/`
   is Roboto on Android and would be SF Pro on iOS.
2. **Material Symbols.** 154 uses of `Symbols.`, 78 distinct glyphs, in 40
   files.
3. **Material anatomy.** `SegmentedButton`, the `NavigationBar` and
   `NavigationRail` pill indicators, tonal `FilledButton`, the notched
   floating-label `OutlineInputBorder`, `ExpansionTile`, the ink ripple. The
   component themes changed radii and removed tint and shadow; the anatomy,
   which is what a viewer recognises, stayed. 75 of 107 Dart files under
   `lib/` import `material.dart` directly.

Tokens change the paint. Components carry the identity. This direction
therefore comes with its own component library rather than another theme.

## 1. The reference, in words

A near-white ground. Large, soft fields of light in acid yellow, lavender,
rose and mint that bleed into the ground with heavy feathering, the way a
projector wash lands on a wall. Panes of frosted glass sit over those fields:
they blur what is behind them, lift it toward white, and catch a hairline of
light along their top edge. Corners are superellipses, not circles glued to
straight edges. Controls are capsules. The primary navigation floats as a row
of glass discs with the current one filled in ink. Numbers are very large and
very light; their units are small and quiet beside them. Labels are sentence
case and short. Data visualisations are made of dots and thin arcs with a
small triangular marker in the accent colour. Nothing is outlined in black;
structure comes from tone, blur and light.

The register: an instrument under frosted glass. A specimen drawer under a
glass lid is the same object. The photograph is the specimen; the chrome is
the glass.

## 2. Principles that decide arguments

These sit alongside the eight principles in 03 section 1 and win any argument
about appearance.

1. **Evidence is neutral; atmosphere is chrome.** The photograph pane and
   every label region sit on a neutral matte with no colour field within 24 dp
   of the matte's edge. Light fields live in the shell, the queue, intake,
   dashboards and empty states. A colour cast on a faded label is a data
   error, so this rule is not negotiable.
2. **Glass is a container, not a texture.** A `GlassSurface` is a pane the
   user reads as one thing: the navigation, a sheet, a tile group, a popover.
   Repeated items (rows, chips, cells) are never glass. At most four glass
   panes are on screen at once and at most one of them is modal.
3. **One accent, and it means "you".** Acid yellow marks the mark, the current
   position, the active marker on a gauge, the region under the pointer.
   It is never a button fill, never a status, never text.
4. **Big numbers, small words.** Hierarchy comes from size and weight in one
   family. Numerals go light as they go large. Units are small, tracked and
   upper case. Everything else is sentence case.
5. **Behaviour adapts, identity does not.** Scroll physics, back gestures,
   page transitions, safe areas, text selection, haptics and pickers follow
   the platform (05 section 5). Type, colour, shape, icons, motion signature
   and component anatomy are ours on every platform.

## 3. Colour

All values are `Color(0x...)` literals in exactly one file,
`packages/specimen_ui/lib/src/foundation/palette.dart`. Everything else reads
a role. Roles are named for what they do, never for a value.

### 3.1 Ground and ink

| Role | Light | Dark | Use |
|---|---|---|---|
| `ground` | `#F6F6F4` | `#0E0F11` | The window background. One unit of warmth, neutral enough that a photograph placed on it reads true. |
| `paper` | `#FFFFFF` | `#17181B` | Solid surface where glass is not warranted: list bodies, tables, fields. |
| `matte` | `#FFFFFF` | `#1E2024` | The letterbox behind a photograph. Lowest surface in light, highest in dark, so label paper reads as paper in both. |
| `ink` | `#111214` | `#F2F2EF` | Primary text, glyphs, the filled navigation disc, primary buttons. |
| `ink.secondary` | `#4B4F57` | `#B9BCC3` | Supporting text, labels above fields, timestamps. |
| `ink.tertiary` | `#646870` | `#9599A0` | Units, hints, placeholder text. Clears 4.5:1 on `paper` and on every glass level over every field. |
| `hairline` | `#E4E5E1` | `#25272B` | Decorative separation. 1 dp. Never a boundary. |
| `boundary` | `#82867B` | `#747A86` | Any edge a user must be able to find: field edges, unfilled checkboxes. 3:1 against `paper`. |
| `disabled.content` | `#62666E` | `#A6AAB1` | Text and glyphs of a disabled control. 4.5:1 on every surface; a disabled control in this product states a server reason and must stay readable (03 section 3.6). |
| `disabled.outline` | `#81858D` | `#757A82` | Edge of a disabled control. 3:1 floor. |
| `disabled.fill` | `ink` at 6% | `ink` at 8% | Behind a disabled control. |
| `scrim` | `#000000` at 32% | `#000000` at 56% | Behind modal glass. Lower than v1 because the pane itself already blurs. |

### 3.2 Light fields

A field is a radial gradient from a centre colour at a centre alpha to fully
transparent at its radius. Fields are painted once, behind everything, inside
a `RepaintBoundary`, by one widget (`FieldLayer`). Nothing else paints a
gradient.

| Field | Light centre | Light alpha | Dark centre | Dark alpha |
|---|---|---|---|---|
| `field.sun` | `#F2FF66` | 0.90 | `#B7C700` | 0.32 |
| `field.violet` | `#CDBBFF` | 0.85 | `#6E5AD1` | 0.40 |
| `field.rose` | `#FFB8D6` | 0.80 | `#C4568F` | 0.36 |
| `field.mint` | `#A9F2D8` | 0.85 | `#2FA07E` | 0.36 |
| `field.ember` | `#FFB466` | 0.85 | `#C87A2C` | 0.36 |

Geometry rules:

- Radius is 45 to 70 percent of the window's **longer** side. Alpha falls off
  on a Gaussian profile, `exp(-4 t squared)` normalised to one at the centre
  and zero at the radius, sampled into 32 gradient stops. A Gaussian holds
  near the centre, falls through the middle and thins out over a long tail,
  and it has no inflection, so no stop count puts a ring in it. Half the
  centre alpha is carried out to 41 percent of the radius, which is the number
  a window reads as the field's size.
- Fields are placed by **sky preset**, chosen per surface role, never per
  screen ad hoc:

| Preset | Fields | Where |
|---|---|---|
| `sky.home` | `sun` centred at (18%, 6%) r 55%; `violet` at (92%, 28%) r 60%; `rose` at (70%, 96%) r 50% | Sign-in, queue, intake, sources, help, empty states |
| `sky.work` | `violet` at (100%, 0%) r 45% at 60 percent of its alpha | Workbench, region editor, large-record fallback. Everything under the matte's 24 dp exclusion is clipped out. |
| `sky.none` | none | Sheets, dialogs, popovers, toasts. They blur what is beneath them instead. |

- **A field never encodes data.** A tile's spotlight field is fixed by its
  slot in a grid, not by the value it shows. The record-count tile is not
  redder when the count is higher. Status is carried by the status triples in
  3.5 and by icon and word, as before.
- In dark mode the same presets apply with the dark column. Dark is not an
  inversion: alphas drop by more than half so the fields read as light in a
  dark room rather than as coloured paint.

Centres and radii in the preset table are fractions of the window: x of its
width, y of its height, r of its longer side.

**Amendment, wave 1 (2026-09-16).** The rule above first bound the radius to
the window's **shorter** side and fell off on `Curves.easeOutQuad`. Rendered
at four real windows for the first time, that reads as three spots on a ground
rather than as light, which is the opposite of section 1. Measured on
`sky.home`, `field.sun`, at the radius where the field still carries half its
centre alpha:

| Window | Shorter side, `easeOutQuad` | Longer side, Gaussian |
|---|---|---|
| 390 by 844 | 63 dp: 16 percent of the width, 7 percent of the height | 191 dp: 49 percent of the width, 23 percent of the height |
| 768 by 1024 | 124 dp: 16 percent, 12 percent | 231 dp: 30 percent, 23 percent |
| 1180 by 820 | 132 dp: 11 percent, 16 percent | 267 dp: 23 percent, 33 percent |
| 1440 by 900 | 145 dp: 10 percent, 16 percent | 325 dp: 23 percent, 36 percent |

The share of the window carrying any field at all, measured as a pixel
differing from `ground` by more than one part in 85, moved from 47, 69, 67 and
62 percent to 99, 89, 93 and 95 percent at those four windows. Two things
were wrong and each fixed half of it. The shorter side is the wrong reference
for a tall window: on a phone it put the whole of `sky.home` in the top
quarter. And a quadratic falloff is a spot with a soft edge: it is down to a
quarter of its centre alpha at 29 percent of the radius, where the Gaussian is
still at 69 percent.

Every centre colour and every centre alpha in the table above is unchanged, so
the composite contrast measurements in 3.7 still hold: the gate composites
against a field's centre, which is the one point the geometry does not move.
The `matteExclusion` of 24 dp is unchanged. The stop count moved from 16 to 32
because a Gaussian has more curvature than a quadratic: at 16 stops the drawn
gradient sits up to 0.57 of one 8 bit level from the curve on the sun field,
and 32 holds it at 0.13.

### 3.3 Glass

The recipe for a `GlassSurface`, at three levels. Blur is `ImageFilter.blur`
with `TileMode.mirror`. The highlight is a 1 dp inner line along the top edge
only, drawn as a vertical gradient so it fades before the corners.

| Level | Blur sigma | Fill (light) | Fill (dark) | Highlight | Stroke | Shadow | Used by |
|---|---|---|---|---|---|---|---|
| `glass.flat` | 16 | `#FFFFFF` at 0.62 | `#1C1E22` at 0.55 | `#FFFFFF` at 0.85 light, 0.12 dark | `ink` at 6% light, `#FFFFFF` at 8% dark | none | In-flow panes: tile groups, the top bar, filter rows |
| `glass.floating` | 20 | 0.66 | 0.58 | same | same | `ink` at 10% light, `#000000` at 45% dark; blur 24; offset (0, 8) | Navigation, popovers, menus, toasts, the sticky action bar |
| `glass.modal` | 24 | 0.72 | 0.66 | same | same | `ink` at 14% light, `#000000` at 55% dark; blur 32; offset (0, 12), plus `scrim` | Sheets and dialogs |

Performance budget, enforced by a test that counts `BackdropFilter` nodes in
every golden window:

- At most 4 glass panes per window, at most 1 modal.
- No glass inside a scrolling list. The list's container may be glass; its
  rows are `paper` or transparent.
- Fields behind glass are static. Nothing animates under a blur except the
  content the user is scrolling.
- A `GlassQuality` setting (`full`, `reduced`, `off`) is read from the theme.
  `reduced` halves every sigma; `off` replaces the blur with a `paper` fill at
  0.92. The device run on the slowest supported Android tablet decides the
  default for that platform; the value is recorded in the verification report.

### 3.4 Accent

| Role | Both modes | Use |
|---|---|---|
| `accent` | `#E8FF47` | The mark. The current-position marker on a gauge or map. The active region marker over the photograph. The current page dot. |
| `on.accent` | `#111214` | Anything drawn on the accent. |

The accent is one hue at one value in both modes; it is luminous enough to
carry. It appears on at most three elements per window. It is not a button
fill, not a link colour, not a selected-row colour, not a status, not a focus
ring. Anything that means "affirmed", "attention" or "stop" uses the status
triples.

Amended in wave 1: the accent takes a 1 dp `ink` casing wherever it is the
only thing saying where a value is. The accent measures near 1 to 1 on
`paper`, so the gauge marker `UiArcIndicator` draws was invisible on the
surface it is drawn over most; section 3.6 already casings a region stroke
over a photograph for the same reason, and this is that rule applied to the
one other graphic that carries a value rather than a decoration.

### 3.5 Status and evidence hues

The v1 triples (`content`, `fill`, `onFill` for cleared, needs review,
deferred, processing, blocked, model, human, authority; the diff, region and
risk tokens) carry over **unchanged in value** in this step. They pass the
contrast test on the v2 surfaces because `paper` and light glass are both
lighter than the v1 surface ramp. A later polish pass may lift their
saturation toward the new register; the contrast test decides, not taste.

Two rules move from 03 unchanged and are restated because glass tempts people
to break them: status is never colour alone (icon plus word plus colour,
always), and herbarium green is the only thing allowed to look affirmative.
Green is no longer the primary colour of anything else.

### 3.6 Focus ring

`focus.ring` is `ink` in light and `#F2F2EF` in dark: 2 dp stroke, 2 dp gap in
the parent surface colour, drawn outside the component so it never reflows
layout, ring radius equal to the component radius plus 4. The v1 blue is
retired; a monochrome ring reads as part of this system and clears 3:1 against
every surface and every field. Over the photograph it keeps the 1 dp dark
outer and 1 dp light inner casing from 03 section 5.8.

### 3.7 What the contrast tests must now do

`test/theme/contrast_test.dart` and `test/accessibility/contrast_test.dart`
extend from the v1 token table to composited surfaces:

- Every text role on `ground`, `paper`, `matte`, and on each glass level
  composited over the lightest and darkest point of every field in both modes.
- `boundary`, `disabled.outline` and `focus.ring` at 3:1 on the same set.
- Status `content` colours on light glass over each field.

The composite is computed with `Color.alphaBlend`, which is what the engine
does for a flat fill; blur only averages neighbouring pixels and cannot push
contrast outside the range of the two extremes tested.

**Amendment, wave 0 (2026-09-16).** Running that test for the first time moved
three roles, in both modes. The values in 3.1 above are the corrected ones;
these were the values first written, and what they measured at their worst
composite:

| Role | First written | Measured | Floor | Now |
|---|---|---|---|---|
| `ink.tertiary` light | `#6B6F78` | 4.19:1 | 4.5:1 | `#646870` |
| `ink.tertiary` dark | `#878B93` | 3.88:1 | 4.5:1 | `#9599A0` |
| `boundary` light | `#C6C8C3` | 1.40:1 | 3:1 | `#82867B` |
| `boundary` dark | `#3B3E44` | 1.24:1 | 3:1 | `#747A86` |
| `disabled.outline` light | `#8E9299` | 2.60:1 | 3:1 | `#81858D` |
| `disabled.outline` dark | `#6A6E76` | 2.59:1 | 3:1 | `#757A82` |

Each moved along its own hue, holding hue and saturation and lowering or
raising only lightness, to the first value clearing its floor with a two
percent margin. `boundary` moved furthest, and the move is the point of the
role: at `#C6C8C3` it was a hairline by another name, and no value that light
can carry a 3:1 edge on white. `hairline` is unchanged and still measures
under 3:1 everywhere, which is what keeps the two roles distinct. Every other
pair in the table passed unchanged, including every status content colour on
light glass over every field.

## 4. Typography: Geist

### 4.1 The family and how it ships

| Role | Family | File | License |
|---|---|---|---|
| Everything proportional | Geist | `GeistVF.ttf` (variable, `wght` 100 to 900) | SIL OFL 1.1 |
| Literal, identifier, digest, code | Geist Mono | `GeistMonoVF.ttf` (variable, `wght` 100 to 900) | SIL OFL 1.1 |

The files on the design machine are version 1.200 (March 2024). They ship
inside the `specimen_ui` package under `assets/fonts/`, declared in that
package's `pubspec.yaml`, and referenced as `fontFamily: 'Geist', package:
'specimen_ui'`. The OFL text is taken from Vercel's `geist-font` release and
registered with `LicenseRegistry.addLicense` at startup. `google_fonts` is
removed from the app entirely; runtime fetching was what the v1 document
forbade and what shipped anyway.

Weight is set through `FontVariation('wght', n)` because the files are
variable, with `fontWeight` mirrored so the platform fallback face chooses
sensibly if the asset ever fails to load. A startup test asserts the two
families resolve to the bundled assets.

OpenType features verified in the bundled files: Sans carries `tnum`, `pnum`,
`frac`, `liga`, `dlig` and stylistic sets `ss01` to `ss09`; Mono carries
`liga`, `frac` and `ss01` to `ss09`. Rules:

- Every count, catalogue number, coordinate, duration and version number in
  Geist is set with `FontFeature.tabularFigures()` so a changed digit is
  visible by position.
- Geist Mono sets `FontFeature.disable('liga')` and
  `FontFeature.disable('calt')` in the literal roles; a ligature replaces two
  characters with one glyph, which is exactly wrong for verbatim evidence.
- Before JetBrains Mono is retired, a golden renders `0O 1lI 5S 2Z 8B` in Geist
  Mono at `mono.literal` and a reviewer confirms each pair is distinct. If the
  zero is not distinguished, the stylistic set that slashes or dots it is
  enabled in `mono.*` and pinned by that golden.

### 4.2 The scale

Sizes in logical pixels. Line height as a multiplier. Tracking in em.

| Role | Size | `wght` | Line | Tracking | Use |
|---|---|---|---|---|---|
| `display.hero` | 64 | 200 | 1.00 | -0.020 | One number per window: the count that matters, a distance, a total. Tabular. |
| `display.large` | 48 | 300 | 1.05 | -0.020 | Tile numerals. Tabular. |
| `display.medium` | 36 | 300 | 1.10 | -0.015 | Section numerals, the record count in the queue header. Tabular. |
| `headline` | 28 | 400 | 1.15 | -0.010 | Screen titles ("Queue", "GCT Balance" in the reference). |
| `title.large` | 22 | 500 | 1.20 | 0 | Pane titles, sheet titles. |
| `title` | 17 | 500 | 1.25 | 0 | Row titles, card titles, button labels at `lg`. |
| `body.large` | 17 | 400 | 1.45 | 0 | Reading text on wide windows. |
| `body` | 15 | 400 | 1.45 | 0 | Default text. |
| `body.small` | 13 | 400 | 1.40 | 0.005 | Secondary lines in rows, help text. |
| `label` | 13 | 500 | 1.20 | 0.020 | Field labels, chip text, button labels at `md`. Sentence case. |
| `label.small` | 11 | 500 | 1.20 | 0.030 | Badges, key caps, nav labels. |
| `unit` | 12 | 400 | 1.00 | 0.080 | Upper case unit beside a numeral: KM, SPM, MS. The only upper case in the product. `ink.tertiary`. |

Monospace roles keep their v1 sizes and rules (03 section 4.3) in Geist Mono:
`mono.literal` 15, `mono.literalDense` 13, `mono.identifier` 13, `mono.digest`
12, `mono.code` 13, all `wght` 400.

Weight rules: nothing below 14 px is lighter than 400. `wght` 200 appears only
at 48 px and above. Light weights never sit on `glass.flat` in dark mode below
36 px. Hero numerals may carry a text shadow of `ink` at 8 percent, blur 12,
in light mode only; no other text has a shadow or glow.

### 4.3 The Material bridge

`ThemeData.textTheme` still exists for the infrastructure widgets that read
it (text selection, the default `DefaultTextStyle`). It is derived from this
scale, never the other way round: `displayLarge` = `display.large`,
`displayMedium` = `display.medium`, `displaySmall` = `headline`,
`headlineLarge` = `headline`, `headlineMedium` = `title.large`,
`headlineSmall` = `title`, `titleLarge` = `title.large`, `titleMedium` =
`title`, `titleSmall` = `label`, `bodyLarge` = `body.large`, `bodyMedium` =
`body`, `bodySmall` = `body.small`, `labelLarge` = `label`, `labelMedium` =
`label`, `labelSmall` = `label.small`. Product code never reads
`Theme.of(context).textTheme`; it reads `context.ui.type.*`.

## 5. Shape: the superellipse

Corners use `RoundedSuperellipseBorder` and `ClipRSuperellipse`, which ship in
this SDK (Flutter 3.38.5, `painting/rounded_rectangle_border.dart` and
`widgets/basic.dart`). A superellipse corner has continuous curvature, so the
edge never visibly "starts to turn"; it is what makes the reference read as
soft rather than as rounded rectangles.

| Token | Radius | Applied to |
|---|---|---|
| `radius.capsule` | full height (`StadiumBorder`) | Buttons, toggles, chips, the navigation and its discs, search fields, badges |
| `radius.sheet` | 28 | Sheets, dialogs, large panes, the photograph matte |
| `radius.tile` | 20 | Data tiles, cards, tile groups, popovers, toasts |
| `radius.field` | 14 | Text fields, selects, textareas |
| `radius.inner` | 8 | Nested elements: thumbnails inside rows, key caps, swatches |
| `radius.none` | 0 | Diff spans, table cells, region overlays, the environment banner |

Rules:

- Optical nesting: an inner element's radius is its parent's radius minus the
  inset between them, floored at `radius.inner`. A tile at 20 with 12 dp
  padding gives its children 8.
- The photograph is never clipped by the matte's corner. It sits inset by at
  least 12 dp inside the matte, so no evidence pixel is hidden under a curve.
- A superellipse whose radius is at least half its height is drawn as a
  capsule; do not hand-tune between the two.
- Strokes: `hairline` 1 dp, `boundary` 1 dp, `emphasis` 2 dp (selected region,
  selected chip), `focus` 2 dp with a 2 dp gap, `bar` 3 dp (the leading bar of
  a selected row and of a diff addition).

## 6. Spacing and density

The 4 px grid and the `space1` to `space12` tokens from 03 section 5.1 are
unchanged. Density becomes two named tokens resolved from the input
modality, not the platform:

| Token | Row height | Control height | Gutter | Tile padding | Chosen when |
|---|---|---|---|---|---|
| `density.touch` | 56 | 48 | 20 | 20 | The last pointer event was a touch, or no pointer event has been seen on a window narrower than 840 |
| `density.pointer` | 44 | 40 visual, 48 hit box | 16 | 16 | The last pointer event was a mouse or trackpad |

A control's hit box is 48 dp in both densities; in `pointer` the extra 8 dp
is transparent slop around the 40 dp visual. Density never changes a hit box
(03 section 5.6). `Density.of(context)` is the only way to read it.

## 7. Iconography: Phosphor

`phosphor_flutter` 2.1.0 (MIT) replaces `material_symbols_icons`. Phosphor's
weights map onto the v1 rules directly.

| Weight | Use |
|---|---|
| `regular` | Every interface glyph by default: actions, navigation, chips, rows |
| `fill` | A settled disposition (cleared, deferred, needs review) and the current navigation destination. This is the v1 `fill01 = 1` rule, kept. |
| `light` | Decorative glyphs at 40 dp and above: empty states, the help screen |
| `thin`, `bold`, `duotone` | Not used. `bold` appears only inside the mark. |

Sizes: 16 (inline with `label.small`), 20 (inline with `body`), 24 (actions,
rows, navigation), 40 (empty states). Colour follows the text it sits with.

Every glyph enters the tree through `UiIcons`, the registry in
`packages/specimen_ui/lib/src/foundation/icons.dart`. A screen never names a
Phosphor glyph directly, so one meaning has one icon across the product
(03 section 6.2 rule, kept). The product meanings:

| Meaning | Phosphor glyph | Weight |
|---|---|---|
| Cleared | `checkCircle` | fill |
| Needs human review | `flag` | fill |
| Deferred | `pauseCircle` | fill |
| Processing | `spinnerGap` | regular, with the progress ring when determinate |
| Processing blocked | `prohibit` | regular |
| State unknown, Unknown (one registry key, `unknown`) | `question` | regular |
| Model reading | `cpu` | regular |
| Reviewer decision | `user` | regular |
| Authority match | `bookOpenText` | regular |
| Risk low, medium, high | `cellSignalLow`, `cellSignalMedium`, `cellSignalFull` | regular |
| Synthetic environment | `flask` | regular |
| Unreadable | `eyeSlash` | regular |
| Not present | `minus` | regular |
| Unmeasured | `circleDashed` | regular |
| Queue | `tray` | regular; fill when current |
| Intake | `plusSquare` | regular; fill when current |
| Sources | `folderOpen` | regular; fill when current |
| Help | `lifebuoy` | regular |
| Account | `userCircle` | regular |
| Reload | `arrowClockwise` | regular |
| Retry processing | `arrowCounterClockwise` | regular |
| Rotate the view | `arrowsClockwise` | regular |
| Sign out | `signOut` | regular |
| Filter | `funnel` | regular |
| Search | `magnifyingGlass` | regular |
| Correct label regions | `crop` | regular |
| Copy | `copy` | regular |
| Keyboard | `keyboard` | regular |
| Back | `arrowLeft` | regular |
| Close | `x` | regular |
| Expand, collapse | `caretDown`, `caretUp` | regular |
| Next, previous record | `caretRight`, `caretLeft` | regular |

The remaining glyphs of the 78 in use are mapped in the migration table kept
with the codemod (`docs/execution/FRONT_END_REFACTOR.md`, appendix A). Two
glyphs for one meaning is a defect; the registry test asserts every icon
value in `UiIcons` is unique.

## 8. Motion signature

The tokens and the reduced-motion policy in
[04-motion-and-microinteractions.md](04-motion-and-microinteractions.md) are
unchanged. This direction adds exactly three signature motions and one
prohibition.

| Motion | What moves | Duration and curve | Under reduced motion |
|---|---|---|---|
| Navigation glide | The ink disc slides from the previous destination to the current one behind the glyphs | `medium` (250 ms), emphasized | Disc appears at the new position, no slide |
| Capsule fill | A capsule toggle fills from its centre when selected; the check fades in after 40 percent | `short` (150 ms), standard | Fill and check appear together |
| Numeral tick | A hero or tile numeral cross-fades and slides 6 dp upward on change; digits are tabular so the width holds | `short` (150 ms), standard | Cross-fade only |

Prohibition: fields never move. The one exception is the sign-in screen,
where `sky.home` may drift by at most 4 percent of the window over 40
seconds; it is disabled under reduced motion and on battery saver. No
parallax, no blur that changes with scroll, no glass that animates its
opacity.

## 9. The mark and the app icon

The product's name is deferred; "Specimen Digitization" stays as the
descriptive name in the top bar on expanded windows and in store listings
until a naming pass.

The mark is **the pin**: the entomologist's pin seen from the side, a
vertical 2 dp `ink` stroke with a filled circular head, standing in a disc of
`accent`. It is the one object every insect specimen in the collection shares
and the verb the product performs on a record. It replaces the stock Flutter
launcher icon that ships today in `android/`, `ios/` and `web/icons/`.

Specification:

- Disc: `accent` `#E8FF47`. Pin: `ink` `#111214`, stroke 2 dp at 24 dp overall,
  head diameter 5 dp, pin height 16 dp, optically centred (the head sits 1 dp
  above geometric centre).
- App icon: a superellipse of `accent` with the pin at 44 percent of the icon
  height. Android adaptive icon foreground and background layers, iOS icon
  set, web favicon and maskable icons are generated from one SVG with
  `flutter_launcher_icons` 0.14.4. The splash, via `flutter_native_splash`
  2.4.8, is `ground` with the disc centred; no wordmark on the splash.
- Monochrome variant: `ink` pin on `paper`, for the environment banner and
  the help screen.
- The mark never rotates, never animates, never sits on a field.

## 10. Dark mode

Both modes ship from the same token table. In dark, `ground` is `#0E0F11`,
glass fills are dark and lifted by their highlight rather than by white, and
fields drop to a third of their alpha. Hero numerals lose their shadow.
Contrast tests run on both columns of every table above.

## 11. What we explicitly reject

This list replaces the v1 rejections in 03 section 2, which banned gradients
and glass outright. Those bans are lifted for the fields and panes defined
above and replaced with these sharper ones:

- **Saturated purple or violet as a brand colour, glows, glassmorphism as
  decoration.** The fields are pale and placed by preset; glass is a
  container with a budget. A gradient anywhere other than `FieldLayer` is a
  defect.
- **Glass on repeated items.** Rows, chips and cells are never blurred panes.
- **Glow or shadow on text** other than hero numerals in light mode.
- **Upper case** anywhere but the `unit` role.
- **Material anatomy**: the ink ripple, the notched floating label, the pill
  indicator inside a bar, tonal container buttons, `ExpansionTile` chevron
  rows, the M3 segmented button. If a Material component widget appears on a
  screen, the gate in 10 section 8 fails.
- **Apple assets**: SF Symbols and SF Pro are licensed for Apple platforms
  only and never ship in this cross-platform app.
- **Runtime font fetching.** Fonts are assets or they are not in the product.
- **Colour that encodes data anywhere but a status triple.** A field, a
  tile's tint or an accent marker never varies with a value.
- **Beige and brass, serif small caps, textured paper.** Still rejected, for
  the reasons in the v1 document.

## 12. Do and do not

| Do | Do not |
|---|---|
| Read every colour from `context.ui.color.*` or a status triple. | Write `Color(0x...)` outside `palette.dart`. |
| Paint fields only through `FieldLayer` with a sky preset. | Add a `LinearGradient` or `RadialGradient` to a widget. |
| Put glass around a pane the user reads as one object. | Put glass on a row, a chip or a cell, or exceed four panes per window. |
| Set weight with `FontVariation('wght', n)` from the type roles. | Pick a weight at a call site or set text below 14 px lighter than 400. |
| Use `unit` for a unit and nothing else in upper case. | Set a label, a button or a heading in upper case. |
| Draw corners with `RoundedSuperellipseBorder` at a shape token. | Use `BorderRadius.circular` with a literal. |
| Use the accent for position markers and the mark. | Fill a button, a selected row or a status with the accent. |
| Keep the matte neutral with 24 dp of field exclusion. | Let a field, a tint or glass touch the photograph. |
| Get a glyph from `UiIcons`. | Name a Phosphor glyph in a screen, or use two glyphs for one meaning. |
| Choose density from the input modality with `Density.of`. | Choose density from `Platform` or device type. |
| Keep icon plus word plus colour on every status. | Let glass or a field stand in for a status. |
| Use a hyphen, comma, colon or period. | Use an em dash or an en dash anywhere, including here. |

## Sources

- Reference boards supplied by the product owner, 2026-09-16: a running-app
  concept showing frosted panes over yellow, lavender, rose and mint fields,
  a floating disc navigation, thin large numerals with small units, and
  dot-matrix visualisations.
- Geist: <https://vercel.com/font>, files `GeistVF.ttf` and `GeistMonoVF.ttf`
  version 1.200, license SIL OFL 1.1 in the `geist-font` repository.
- Phosphor Icons: <https://phosphoricons.com>, `phosphor_flutter` 2.1.0, MIT.
- Flutter 3.38.5 SDK: `RoundedSuperellipseBorder`, `ClipRSuperellipse`,
  `RSuperellipse`, `BackdropFilter`, `FontVariation`.
- WCAG 2.2: SC 1.4.3 (contrast minimum), SC 1.4.11 (non-text contrast),
  SC 2.4.13 (focus appearance), SC 2.3.3 (animation from interactions).
- v1 record: [03-design-system.md](03-design-system.md) sections 2 to 6.
