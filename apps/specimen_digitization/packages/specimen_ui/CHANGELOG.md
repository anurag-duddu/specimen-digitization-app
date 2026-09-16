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
- `StateLayer.colour` and `Pressable.stateLayerColour`, copied verbatim from
  the actions slot so the two branches carry identical content. The current tab
  of the strip fills with `ink`, and `ink` at 12 percent over an `ink` fill is
  the same colour, so it lifts toward `paper` instead.

### Gallery
- The overlays family page, registered as one line in `familyPages`. The shell
  now carries `foundationPages`, `familyPages` and `galleryPages`, and defaults
  to the third, so a family page reaches `/gallery` without moving the
  foundation goldens: those render the page list too, and
  `foundation_golden_test.dart` now pins `foundationPages` so they hold byte
  for byte as each slot registers.
- Eight goldens: the page in both modes at both densities, plus one window per
  mode with the sheet open and one with the dialog open. The page is captured
  at 1180 by 1000 rather than the usual 1180 by 820, because it is 922 logical
  pixels of content at touch density and a golden that stops at 820 reviews the
  banners and nothing else. The two modal goldens keep the standard window: a
  sheet and a dialog are judged against the window they are drawn over.

### inputs
Wave 1 slot C2, the inputs family (10 section 4.2).
- `UiField`: label above, a `radius.field` superellipse of `paper` whose
  `boundary` edge becomes `ink` at `stroke.emphasis` on focus and
  `status.blocked.content` on error, optional leading glyph, a trailing clear
  control with its own 48 dp hit box, help or error text below with the error
  glyph, and an optional counter. One semantics node reads the label, the
  value and the hint; the error goes through `Announcer` once. Retires
  `TextField`, `TextFormField`, `InputDecoration` and `OutlineInputBorder`.
- `UiTextArea`: the same field with `minLines`, `maxLines` and auto growth.
- `UiSearchField`: a capsule field with the search glyph leading, a clear
  control once there is something to clear, `Escape` to clear and then
  unfocus, and `Enter` to submit.
- `UiSelect<T>`: a field shaped trigger with the selected option and a caret,
  a `glass.floating` popover list at `radius.tile`, type to filter above eight
  options, `Down` and `Up` to move, `Enter` to pick and `Escape` to close and
  return focus. Semantics `button` with `expanded`, options `selected`.
  Retires `DropdownMenu`, `DropdownButton` and `MenuAnchor` used as a select.
- `UiSwitch`: a 44 by 26 capsule track with a 22 dp thumb that glides at
  `short` and jumps under reduced motion, the whole row as the hit box and
  `toggled` semantics. Retires `Switch` and `SwitchListTile`.
- `UiCheckbox`: a 20 dp `radius.inner` box that fills `ink` with a `paper`
  check, draws a bar when indeterminate and reads as mixed. Retires
  `Checkbox` and `CheckboxListTile`.
- `UiRadio<T>` and `UiRadioGroup<T>` on `RawRadio` and `RadioGroup`, so the
  exclusive group, the arrow keys and the group role come from the SDK.
  Retires `Radio` and `RadioListTile`.
- `UiInputStyle`, `UiFieldFrame` and `UiFieldBox` are the shared anatomy: a
  select and a field are one object with two behaviours. The style is named
  for the family rather than `UiFieldStyle`, which `foundation/fields.dart`
  already owns for the light fields of 09 section 3.2.
- A checked box and an on switch track lift toward `paper` under the pointer,
  because `ink` at 12 percent over an `ink` fill is the same colour. The row
  around them keeps the shared `ink` layer, so both halves of the control
  answer a hover.
- The gallery gains an inputs page, registered in the shell's `familyPages`
  list, and goldened in light and dark at both densities. The family golden is
  captured at 1180 by 1180 rather than the shell's 1180 by 820: seven controls
  in every state do not fit one window, and a golden that reviews the top of a
  page is not reviewing the three controls below the fold.
- `FieldCore` gains `excludeFromSemantics`, so a control that publishes one
  node for the whole field does not get a second one from the editor.

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
