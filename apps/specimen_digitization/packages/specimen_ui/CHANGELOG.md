# Changelog

## Unreleased

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
- The gallery gains an inputs page, goldened in light and dark at both
  densities, and the shell gains a family page list beside the foundation one.
- `FieldCore` gains `excludeFromSemantics`, so a control that publishes one
  node for the whole field does not get a second one from the editor.

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
