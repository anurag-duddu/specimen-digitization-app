# Changelog

## Unreleased

### navigation

Wave 1 slot C4: the navigation family (10 section 4.4).

- `UiPillNav`, the reference's floating capsule. Two to five discs on
  `glass.floating`, the current one an `ink` disc with a `paper` glyph in
  `fill` weight, gliding between destinations at `medium` on the emphasized
  curve and appearing in place under reduced motion. It reports the height a
  scaffold pads the body by. Retires `NavigationBar`.
- `UiRail`, the same discs down a 72 dp column under a `leading` slot, with an
  extended form that draws each destination's words under its glyph. It
  measures the widest label at the live text scale and widens rather than
  clipping a word it cannot break. Retires `NavigationRail`.
- `UiSidebar`, a 280 dp `glass.flat` pane with `header` and `footer` slots and
  destinations as rows, the current one marked by the 3 dp leading bar, the
  `fill` glyph and `ink` rather than `ink.secondary`. The destinations scroll
  between the two slots when the pane is too short for them. Retires `Drawer`
  and the permanent drawer.
- `UiTopBar`, transparent over the fields and filled with `glass.flat` once
  the body has scrolled under it. It owns the top and side safe areas so its
  pane reaches the window's edges. Retires `AppBar`.
- `UiScaffold`, the page frame: `ground` and a sky preset through `FieldLayer`,
  then the `topBar`, `banner`, `body`, `actionBar`, `nav` and `overlays`
  slots, with safe areas and keyboard insets applied and the exact bottom
  inset its floating chrome occupies published through `UiScaffold.of`.
  Retires `Scaffold`.
- `UiNavDestination`, the one destination model all three navigations take.
- Semantics: a tab list per navigation, a tab per destination with `selected`,
  and the label on every disc as a tooltip because no words are drawn. Arrow
  keys move along the control's own axis and `Enter` selects.
- The gallery gains a navigation page, registered in `familyPages` rather
  than in `foundationPages` so the twenty four foundation goldens hold still
  as the families land. Its four goldens are captured at 1180 by 940 rather
  than the gallery's own 1180 by 820, because a family whose largest specimen
  is a page frame does not fit in one window's height and a truncated golden
  reviews only what fits.
- `Pressable.stateLayerColour`, taken verbatim from `fe/actions`, carries the
  current disc: `ink` at 12 percent over an `ink` disc is the same colour, so
  without it the one disc a reviewer presses most would show no press.

Foundation, changed for this family and committed on its own:

- The light field geometry was measured at 390 by 844, 768 by 1024, 1180 by
  820 and 1440 by 900 and did not read as the washes 09 section 1 describes.
  The radius is now a fraction of the window's longer side rather than its
  shorter one, and the alpha falls on a Gaussian rather than
  `Curves.easeOutQuad`. Every centre colour, every centre alpha and
  `UiFields.matteExclusion` are unchanged, so the composite contrast
  measurements still hold. 09 section 3.2 carries the new rule and the
  numbers, and all 24 foundation gallery goldens moved, because the gallery
  shell paints `sky.home` behind every page.

## 0.1.0

Wave 0 of the front-end refactor: the foundation and the primitives.

### Foundation

- Package skeleton with the five family barrels, so a wave 1 agent adding a
  control never edits the top barrel.
- Geist and Geist Mono bundled as package assets, with the SIL Open Font
  License 1.1 text registered through `LicenseRegistry`. `google_fonts` is out
  of the application entirely.
- `UiColor`, `UiFields`, `UiGlass`, `UiType`, `UiShape`, `UiSpace`,
  `UiDensity`, `MotionTokens` and `UiIcons`, with `palette.dart` as the only
  file in the product carrying a colour literal.
- `UiThemeData.light()` and `.dark()`, `UiTheme`, `context.ui`, and
  `toThemeData()` for the carrier `MaterialApp`.
- Six colour roles moved from the value printed in 09 because they failed the
  composite contrast rule in 09 section 3.7. The measurements are in
  `palette.dart` beside each value.

### Primitives

- `Pressable` and `StateLayer`, which retire `InkWell`, `InkResponse`,
  `Material` and a bare `GestureDetector` at every call site.
- `Surface`, `GlassSurface` and `Scrim`.
- `FieldLayer`, the only gradient painter in the product.
- `FocusRing` and `Squircle`.
- `Popover`, `ModalRoutes` (`showUiSheet`, `showUiDialog`, `showUiModal`),
  `FieldCore`, `Announcer` and the `Density` probe.

### Controls

- A minimal `UiButton` in `primary`, `secondary` and `ghost` at size `md`,
  marked experimental. Slot C1 completes the actions family per 10 section
  4.1.

### Gallery

- `UiGallery` with the six foundation pages, mounted at `/gallery` in the
  application outside release builds, and goldened in light and dark at both
  densities.
