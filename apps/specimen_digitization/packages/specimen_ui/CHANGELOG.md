# Changelog

## Unreleased

### overlays

Wave 1 slot C3: the family a screen puts over, above or inside its content
without changing route. Retires `MenuAnchor`, `PopupMenuButton`, `showMenu`,
`Tooltip`, `SnackBar`, `ScaffoldMessenger`, `ExpansionTile`, `TabBar`,
`TabBarView`, `AlertDialog`, `showDialog`, `showModalBottomSheet` and
`BottomSheet`.

- `UiPopoverMenu` and `UiMenuTrigger`. A `glass.floating` pane at `radius.tile`
  with a glyph, a label, an optional shortcut in `mono.identifier` and an
  optional destructive tint. `Down` and `Up` move over the enabled items and
  wrap, `Enter` chooses, `Escape` closes and returns focus to the trigger.
  Semantics `menu` and `menuItem`. No submenus.
- `UiTooltip`, on hover after 400 ms and on long press. `paper` rather than
  glass, because tooltips are small and frequent and every frosted pane is a
  save layer. `UiTooltip.reason` is the carrier for a disabled control's reason
  through `Pressable.onDisabledReason`.
- `UiToast`, `UiToastHost` and `UiToasts.show`. A `glass.floating` capsule,
  queued one at a time, centred above the navigation on a compact window and in
  the bottom start corner on a wider one. It clears itself after six seconds
  unless it carries an action, and it announces itself once.
- `UiBanner`, a full width strip at `radius.none` in seven tones: `info`, the
  five statuses and `synthetic`. Optional second line behind a disclosure,
  optional dismiss, the message in a live region. The v1 `EnvironmentBanner`
  becomes one instance of it.
- `UiDisclosure`, a titled row that reveals a body with `AnimatedSize` and a
  caret that turns half a circle. Semantics `expanded`.
- `UiTabs` and `UiTabView`, bound to a `ValueNotifier<int>` rather than a
  `TabController`. Arrows move and select, mirrored under a right to left
  window; panes cross fade and never slide.
- `UiSheet`, `UiDialog` and the shared `UiModalActions` row. The chrome for
  `ModalRoutes`: `glass.modal`, `radius.sheet`, a drag handle on the sheet, the
  title in `title.large`, and at most one `primary` and one `secondary` or
  `ghost` action. `UiSheet.show`, `UiDialog.show` and `UiDialog.showAdaptive`
  are the wrappers that push the route and fill in the slots.

### Primitives

- `Popover` gained `surface` (`glass` or `paper`) and `interactive`, so a
  passive overlay neither takes focus nor swallows the click the reviewer was
  about to make on the control it describes.
- `Squircle` and `GlassSurface` gained `corners`, the one shape in the product
  that is not uniform, and `ModalRoutes` uses it: a sheet is round on top and
  square where it meets the window's edge (10 section 4.3).
- `ModalRoutes` dismisses on `Escape` and returns focus to whatever opened the
  modal, which clause 3 of the control contract requires and the route's own
  scope restoration does not do.

### Gallery

- The overlays family page, and `familyPages` in the gallery shell for the
  control families to register themselves in. Eight goldens: the page in both
  modes at both densities, plus one window per mode with the sheet open and one
  with the dialog open.

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
