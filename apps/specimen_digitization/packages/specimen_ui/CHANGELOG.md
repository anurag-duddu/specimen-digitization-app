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

### data

Wave 1 slot C5: the eight controls of 10 section 4.5.

- `UiListRow`. Height from the density, floored at the 48 dp hit box the
  control contract sets in both densities. Slots for a 24 glyph, a 40
  thumbnail or a checkbox the caller passes in, a title over a subtitle of up
  to two lines, and a trailing slot for text, a chip or a caret. The whole row
  is one `Pressable` and one merged semantics node whose role follows the
  mode: a row that opens a record is a `button`, a row in a selection is a
  `checkbox` carrying `checked`. Selected rows fill `ink` at 6 percent with
  the 3 dp leading bar, and the bar's gutter is reserved on every row so
  selecting one never shifts its content sideways. Never glass. Retires
  `ListTile` and `CheckboxListTile`.
- `UiProgress`. `ring` at 16, 24 and 40 and `bar` at 4 dp. Determinate draws
  an arc in `ink` on a `hairline` track and keeps its 200 ms linear catch up
  under reduced motion, because the motion is the number. Indeterminate turns,
  draws no track, and under reduced motion holds still and pulses its opacity
  instead. Two rules from 04 section 5.5 are enforced here rather than left to
  each call site: a reported value below the highest one seen is held at the
  highest, and the first value is painted where it is with no fill animation.
  Retires `CircularProgressIndicator` and `LinearProgressIndicator`.
- `UiSkeleton` in `row`, `tile` and `line`, each the shape and the height of
  the content it stands for, with a slow opacity pulse that stops under
  reduced motion and no shimmer at all. Outside the semantics tree.
- `UiEmptyState`. A 40 dp glyph, a title, one sentence and at most one
  `UiButton`, typed as a button so the rule is the signature. No glass.
- `UiDataTile`. `glass.flat` at `radius.tile`, the label in `type.label`, the
  numeral in `display.large` or `display.hero`, a unit on the numeral's
  baseline, an optional footer and an optional child slot. The numeral
  cross-fades and slides 6 dp upward on change, and cross-fades only under
  reduced motion. The tint never varies with the value. One semantics node
  reading label, value and unit as a sentence.
- `UiArcIndicator`. A 180 or 270 degree `hairline` arc with an `accent`
  triangular marker at the value and optional minimum and maximum labels. A
  null value draws the `unmeasured` glyph and the word, never a marker at
  zero.
- `UiAvatar` at 32 and 40, initials or an image, with the person's name as
  the whole of its semantics.
- `UiHairline`, horizontal and vertical, inset aware and directional. Retires
  `Divider` and `VerticalDivider`.
- The data gallery page, registered as one line in `familyPages`, with
  goldens in light and dark at both densities. They are captured at 1180 by
  1900 rather than at the shared 1180 by 820: eight controls do not fit one
  window, and the actions golden already reviews only the top of its page.
  The taller window belongs to this golden alone, so no other family's files
  move for it.

### Actions, for the data family

- The loading button's private `_LoadingArc` is now `UiProgress.ring` at
  16 dp, which is the replacement slot C1 marked it for. The four actions
  goldens do not move.

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
