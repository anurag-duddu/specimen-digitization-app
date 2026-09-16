# Changelog

## Unreleased

### actions

Wave 1 slot C1: the seven controls of 10 section 4.1.

- `UiButton` completed. Four variants (`primary`, `secondary`, `ghost`,
  `danger`), three sizes (`sm` 32, `md` by density, `lg` 56), a leading and a
  trailing glyph slot, and a `loading` state whose ring takes the leading
  slot so the width holds. `secondary` is the `glass.flat` tone composited
  onto `paper` rather than a blurred pane, because a button is a repeated
  item. Retires `FilledButton`, `FilledButton.tonal`, `OutlinedButton` and
  `TextButton`. The experimental marker is gone; the API is additive over
  wave 0, so no call site changed.
- `UiIconButton`. A 48 dp disc, 40 in pointer density, `ghost` or
  `secondary`, with a required `semanticsLabel` that doubles as the tooltip.
  Retires `IconButton`.
- `UiCapsuleToggle`. One capsule per option with a 16 dp check disc that
  fills from its centre on selection and a check that fades in after 40
  percent of the fill, which is signature motion 2. Single or multiple
  selection, arrows inside the group, `Space` to toggle. Retires `FilterChip`
  in filter rows and `ChoiceChip`.
- `UiChip` in `tag`, `filter` and `input`, with an optional status triple for
  the `StatusChip` pattern to re-base on, and a remove glyph that keeps its
  own 48 dp target inside a 32 dp capsule. Retires `Chip`, `InputChip` and
  `ActionChip`.
- `UiSegmented`. Two to five equal segments with an `ink` thumb that glides,
  which is signature motion 1; arrows move focus and `Enter` chooses, so
  arrowing past a segment does not switch the pane under the reviewer.
  Retires `SegmentedButton`.
- `UiBadge`, a count in tabular figures or a dot, optionally on a status
  content. Retires `Badge`.
- `UiKeyCap`, the monospace identifier role on `paper` at `radius.inner`.
- The actions gallery page, registered in the shell's family page list, with
  goldens in light and dark at both densities.

### Foundation, for the actions family

- `StateLayer` and `Pressable` take an optional state layer colour. The
  contract's `ink` is right over every light fill and invisible over an `ink`
  one, so a primary button had no visible hover or press at all. The opacity
  is unchanged; only which way the surface moves is now the control's to say.
- The gallery shell has a `familyPages` list beside `foundationPages`, and
  shows both. The foundation goldens draw the page list, so one shared list
  would move all twenty four of them every time a family landed.

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
