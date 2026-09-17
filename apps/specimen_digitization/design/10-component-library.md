# 10. Component library: `specimen_ui`

Status: **built, at `specimen_ui` 0.2.0.** Written 2026-09-16; section 4
reconciled with what the five family slots and the integration polish slot
shipped, in the same pass that released 0.2.0. Every paragraph marked
"Amended in wave 0" or "Amended in wave 1" is a change to this document made
by the work it describes, per section 10. This
document specifies the component library that renders
[09-brand-direction.md](09-brand-direction.md). It replaces section 7 (atomic
inventory) and section 8 (Flutter implementation plan) of
[03-design-system.md](03-design-system.md); the eight principles in 03 section
1 and the rules in 02, 04, 05 and 06 continue to apply to every component here.
The build plan, ownership map and waves are in
[../../../docs/execution/FRONT_END_REFACTOR.md](../../../docs/execution/FRONT_END_REFACTOR.md).

## 0. What makes a strong design system

A design system is strong when a stranger can add a screen that looks and
behaves as if the original team built it, and when the system tells them,
mechanically, the moment they drift. Twelve properties do that. Each one below
names the mechanism that enforces it in this repository, because a property
without a mechanism is a wish.

| # | Property | What it means here | Enforced by |
|---|---|---|---|
| 1 | Few decisions, made once | Colour, type, space, shape, motion, density, icons are tokens in one package; a widget never carries a literal | `no_color_literals`, `no_literal_geometry`, `icons_unique` tests (section 8) |
| 2 | Layers with hard boundaries | Foundation, primitives, controls, patterns, screens; each imports only the layer below | Package boundary plus the `layering` import test |
| 3 | Behaviour parity across inputs | Every control works by touch, mouse, keyboard, screen reader and under reduced motion | The control contract (section 2) run as a shared test on every control |
| 4 | Exhaustive, named states | Rest, hover, focus, pressed, selected, disabled, loading, error, read-only, defined per control and resolved in one place | `WidgetStatesController` plus one `XStyle.resolve(states)` per control; gallery renders every state |
| 5 | Composition over configuration | Slots (`leading`, `trailing`, `child`) and small enums, not boolean flags | Review rule in section 11; a control with more than two `bool` visual props is rejected |
| 6 | One vocabulary | The name in the spec is the name in code is the name in the gallery | Section 11 naming; the gallery page titles are generated from class names |
| 7 | Living documentation | A gallery renders every component in every state, both densities, both modes | `package:specimen_ui/gallery.dart`, mounted at `/gallery` in debug builds, goldened per family |
| 8 | Accessibility as a floor, measured | 48 dp targets, visible focus, 4.5:1 text on every composited surface, 200 percent text without clipping, semantics roles | `control_contract`, `contrast_composite`, the semantics fixtures already in `test/accessibility/` |
| 9 | A performance budget as a design rule | Glass costs a `saveLayer`; the system caps panes and forbids glass on repeated items | `glass_budget` test counts `BackdropFilter` per golden window |
| 10 | Adoption mechanics | A backlog that only shrinks, a codemod table for icons, one exemplar screen migrated before the rest | Backlog maps in the gate tests; appendix A of the build plan; the queue is the exemplar |
| 11 | Governance | A changelog, a definition of done, a deprecation path | Section 9 and 10 |
| 12 | Taste is encoded | The aesthetic is written down with specific rejections so six agents converge | 09 sections 1, 2, 11 and 12; the gallery golden is the taste review |

## 1. Architecture

### 1.1 Layers

| Layer | Lives in | May import | Look? | Product meaning? |
|---|---|---|---|---|
| L0 SDK primitives | `package:flutter/widgets.dart` | | none | none |
| L1 Foundation | `packages/specimen_ui/lib/src/foundation/` | L0 | tokens only | none |
| L2 Primitives | `packages/specimen_ui/lib/src/primitives/` | L0, L1 | geometry and state, no styling decisions of its own | none |
| L3 Controls | `packages/specimen_ui/lib/src/controls/` | L0 to L2 | yes | none: a `UiButton` does not know what a specimen is |
| L4 Patterns | `apps/specimen_digitization/lib/src/widgets/` | L0 to L3, `models.dart`, `vocabulary.dart` | composed from L3 | yes: `StatusChip`, `ReadingCard`, `RiskMeter` |
| L5 Screens | `apps/specimen_digitization/lib/src/screens/`, `lib/src/app/` | L0 to L4 | composed | yes |

The package cannot import the app because the path dependency points one way.
The app's screens import `package:specimen_ui/specimen_ui.dart` and the
patterns barrel `widgets/widgets.dart`, and nothing from `material.dart`; the
`layering` and `no_material_imports` tests in section 8 hold that line.

`★` The reason this works in Flutter and needs Radix in React: `widgets.dart`
already is the headless layer. `FocusableActionDetector` gives hover, focus and
keyboard activation; `WidgetStatesController` gives named states; `EditableText`
is a text input with no chrome; `OverlayPortal` and `RawMenuAnchor` position
overlays; `RawRadio` groups radios; `showGeneralDialog` and `RawDialogRoute`
run modals; `Semantics`, `Shortcuts` and `Actions` do accessibility and keys.
All of these are in the installed 3.38.5 SDK. `material.dart` is one component
library on top of that layer. This package is another.

### 1.2 Package layout

```
apps/specimen_digitization/packages/specimen_ui/
  pubspec.yaml                 name: specimen_ui; deps: flutter, phosphor_flutter; dev: flutter_test
  analysis_options.yaml        flutter_lints plus public_member_api_docs, prefer_const_constructors
  CHANGELOG.md
  LICENSES/OFL-Geist.txt
  assets/fonts/GeistVF.ttf, GeistMonoVF.ttf
  lib/specimen_ui.dart         barrel: exports foundation, primitives, controls
  lib/gallery.dart             barrel: exports UiGallery (debug only)
  lib/testing.dart             barrel: the glass pane counters, for test harnesses
  lib/src/foundation/
    palette.dart               the only file with Color(0x...) literals
    color.dart                 UiColor roles (light, dark), status triples carried from v1
    fields.dart                UiField definitions and sky presets
    glass.dart                 UiGlass levels, GlassQuality
    type.dart                  UiType roles, FontVariation helpers, TextTheme bridge
    shape.dart                 UiShape radii and strokes, superellipse helpers
    space.dart                 the 4 px grid (carried from v1)
    density.dart               UiDensity values; Density inherited widget and pointer probe
    motion.dart                MotionTokens (carried from v1) plus the three signature motions
    icons.dart                 UiIcons registry on Phosphor
    theme.dart                 UiTheme (InheritedWidget), UiThemeData.light()/dark(), toThemeData(), context.ui
    fonts.dart                 license registration, asset family names
    reduced_motion_platform*.dart  the platform probe MotionTokens reads, web and stub
  lib/src/primitives/
    pressable.dart  state_layer.dart  surface.dart  glass_surface.dart  field_layer.dart
    focus_ring.dart  squircle.dart  popover.dart  modal_routes.dart  field_core.dart
    announcer.dart  scrim.dart
  lib/src/controls/
    actions/   button.dart icon_button.dart capsule_toggle.dart chip.dart segmented.dart badge.dart key_cap.dart  actions.dart (family barrel)
    inputs/    field.dart text_area.dart search_field.dart select.dart switch.dart checkbox.dart radio.dart  inputs.dart
    overlays/  popover_menu.dart tooltip.dart toast.dart banner.dart disclosure.dart tabs.dart sheet.dart dialog.dart  overlays.dart
    navigation/ pill_nav.dart rail.dart sidebar.dart top_bar.dart scaffold.dart  navigation.dart
                nav_destination.dart, plus nav_disc.dart and nav_group.dart, unexported (section 4.4)
    data/      list_row.dart progress.dart skeleton.dart empty_state.dart data_tile.dart arc_indicator.dart avatar.dart hairline.dart  data.dart
  lib/src/gallery/             one page per family; UiGallery shell
  lib/src/testing/             the glass pane counters lib/testing.dart exports
  test/
    flutter_test_config.dart   loads the bundled fonts with FontLoader so goldens use Geist
    harness/control_contract.dart, harness_test.dart
    foundation/                contrast_composite_test, palette_only_literals_test, icons_unique_test, layering_test, fonts_test, motion_test, field_geometry_test, no_stand_ins_test
    primitives/, controls/     behaviour tests and control_contract runs
    gallery/                   one golden test per family; goldens/<family>-<mode>-<density>.png
```

Family barrels exist so that four agents can add controls in parallel without
touching the same file: each family owns its barrel; the top barrel lists the
five family barrels and is written once in the foundation step.

### 1.3 Material as infrastructure, and nothing else

| Kept | Where | Why |
|---|---|---|
| `MaterialApp.router` | `main.dart` | Localizations, `Overlay`, `Router`, `ScrollBehavior`, text selection defaults, `Theme` inheritance. It has no look of its own once every component widget is gone. |
| `ThemeData` | built by `UiThemeData.toThemeData()` | The carrier `MaterialApp` expects. Its `colorScheme` and `textTheme` are derived from `UiThemeData`, never edited directly. |
| `TextField` with `InputDecoration.collapsed` | `primitives/field_core.dart` only | Selection toolbar, magnifier, autofill, spell check, IME and the semantics of a text field are thousands of lines that `EditableText` alone does not give. The decoration is stripped; all chrome is ours. |
| `PageTransitionsTheme` | `main.dart` | Per-platform route transitions (05 section 5). |
| `Tooltip`'s semantics strings via `MaterialLocalizations` | `controls/overlays/tooltip.dart` | Localised "dismiss" and similar strings, not the widget. |

Everything else from `material.dart` is retired: `Scaffold`, `AppBar`,
`Card`, `ListTile`, `Chip` and its variants, `FilledButton`, `OutlinedButton`,
`TextButton`, `IconButton`, `NavigationBar`, `NavigationRail`, `Drawer`,
`ExpansionTile`, `SegmentedButton`, `Switch`, `Checkbox`, `Radio`,
`DropdownMenu`, `MenuAnchor`, `PopupMenuButton`, `SnackBar`,
`ScaffoldMessenger`, `AlertDialog`, `showDialog`, `showModalBottomSheet`,
`Tooltip`, `Divider`, `InkWell`, `Material`, `LinearProgressIndicator`,
`CircularProgressIndicator`, `Badge`, `TabBar`.

### 1.4 Theme access

```dart
final ui = context.ui;              // UiThemeData, an InheritedWidget lookup
ui.color.ink; ui.color.inkSecondary; ui.color.status.cleared.content;
ui.field.sun; ui.field.sky(SkyPreset.home);
ui.glass.floating;                  // UiGlassStyle(sigma, fill, highlight, stroke, shadow)
ui.type.displayHero; ui.type.unit; ui.type.mono.literal;
ui.shape.tile; ui.shape.capsule; ui.shape.stroke.focus;
ui.space.s4;                        // the 4 px grid, carried from v1
ui.density;                         // UiDensity.touch or .pointer, resolved by Density.of
ui.motion.short; ui.motion.emphasized;
ui.icons.cleared;                   // IconSpec(glyph, weight)
ui.quality;                         // GlassQuality
```

`UiTheme` wraps the app once in `main.dart`; `Theme.of(context)` continues to
work for the infrastructure widgets because `toThemeData()` feeds
`MaterialApp.theme` and `darkTheme`. Product code never reads `Theme.of`.

### 1.5 Style resolution

Every control has a style object holding every token it uses, a default
resolved from `UiThemeData`, and stateful members typed as
`WidgetStateProperty`. A call site passes a variant and a size; an override is
possible but is a code review event.

```dart
class UiButtonStyle {
  final WidgetStateProperty<Color> background, foreground, overlay;
  final WidgetStateProperty<BorderSide?> side;
  final OutlinedBorder shape;          // capsule
  final EdgeInsetsGeometry padding;    // from density
  final double minHeight;              // 48 touch, 40 pointer
  final TextStyle label;               // type.label or type.title for lg
  final Duration pressIn, pressOut;    // 60 ms, 120 ms
  static UiButtonStyle resolve(UiThemeData ui, UiButtonVariant v, UiSize s) { ... }
}
```

## 2. The control contract

Every interactive component in L3 satisfies all of the following. The shared
test `expectControlContract(tester, build)` in `test/harness/` asserts each
one; a control whose test file does not call it does not merge.

Amended in wave 1: "interactive" is the whole of the scope, and nine of the
thirty controls turned out not to be. `UiBadge`, `UiKeyCap`, `UiAvatar`,
`UiHairline`, `UiSkeleton`, `UiProgress`, `UiArcIndicator`, `UiDataTile` and
`UiEmptyState` have no role of their own, nothing to focus and no hit box, and
the first clause the contract asserts is a 48 dp target. They are tested for
what does apply instead: a label that stands alone, tabular figures where they
carry a number, growth rather than clipping at 200 percent text, right to
left, and no ticker in either motion mode. Where one of them contains a
control that is interactive, such as the `UiButton` an empty state may carry,
that control runs the contract in its own family.

The harness publishes `MediaQuery`, `Density` and `UiTheme` above the
application's navigator, the way `main.dart` wraps `MaterialApp.router`, so a
control that pushes a route is measured in the mode, the density and the
motion state the test asked for rather than in the light fallback.

1. **States.** Rest, hover, focus, pressed, selected, disabled, loading, error
   and read-only exist where they apply, are driven by one
   `WidgetStatesController`, and are visually distinct in the gallery.
2. **Hit box.** At least 48 by 48 dp in both densities. In `pointer` density
   the visual may be 40 dp; the 8 dp difference is transparent slop.
3. **Keyboard.** Focusable; `Space` and `Enter` activate; arrow keys move
   within composite controls (segmented, radio group, menu, tabs, pill nav)
   along the control's own axis; `Escape` dismisses an overlay and returns
   focus to its trigger; `Tab` never gets trapped except inside a modal, where
   it cycles.
   Amended in wave 1, twice. A vertical group answers `Up` and `Down` and
   leaves the cross axis alone: a rail that swallowed `Right` would trap a
   keyboard reviewer inside the navigation instead of letting them move into
   the content, and the orientation's own pair is the required one in the
   WAI-ARIA pattern. And a text editor is the one control the first half of
   this clause cannot be true of: while an editor holds focus,
   `DefaultTextEditingShortcuts` maps `Space` to
   `DoNothingAndStopPropagationTextIntent`, so nothing above the editor ever
   sees the key, and a control that consumed it would be a field nobody can
   type a space into. The contract therefore takes a `ControlActivation`.
   `keys` is the clause above; `textEditing` asserts the mirror image, that
   what took focus is an `EditableText` and that neither key was consumed
   above it. The mirror is the stronger assertion, because the defect it
   catches, an overlay or a screen swallowing the space bar, is a real one.
4. **Focus ring.** Drawn per 09 section 3.6, only for keyboard focus
   (`FocusManager.highlightMode == traditional`), never on pointer press.
   Amended in wave F by 09 section 3.6's fit amendment: a text editing field
   is the exception and shows the ring for any focus, pointer or keyboard,
   because a focused field is being edited and a caret alone does not say
   which of several fields holds it. The harness takes that from the
   `ControlActivation` a control already declares: `textEditing` asserts the
   mirror image here as it does for the activation keys, that an unfocused
   editor draws no ring and that a pointer tap draws one. The ring also takes
   the shape of what it rings rather than a circular rounded rectangle, so
   `FocusRing` carries a `FocusRingShape` of `superellipse`, `stadium` or
   `circle`.
5. **Semantics.** A role (`button`, `toggle`, `checkbox`, `radio`, `tab`,
   `textField`, `link`, `header`, `image`, `liveRegion` as applicable), a
   label that stands alone, a value where there is one, `enabled`,
   `selected` or `checked` or `toggled` where applicable, and for a disabled
   control the reason on `hint` and on a tooltip (03 section 3.6).
   Amended in wave 1: seven `SemanticsRole` values exist in Flutter 3.38.5 and
   cannot be used. `tooltip`, `progressBar`, `loadingSpinner`, `dragHandle`,
   `spinButton`, `comboBox` and `hotKey` map to `_unimplemented` in
   `_DebugSemanticsRoleChecks`, so the first frame that publishes one raises
   "Missing checks for role SemanticsRole.x" from the scheduler. Where a role
   is unusable, the property carrying the same meaning is used instead:
   `SemanticsProperties.tooltip` on the tooltip's own pane, and for a progress
   indicator a label that reads the value as a sentence. The roles that are
   safe today are `tab`, `tabBar`, `tabPanel`, `menu`, `menuBar`, `menuItem`,
   `menuItemCheckbox`, `menuItemRadio`, `dialog`, `alertDialog`, `alert`,
   `status`, `table`, `row`, `cell`, `columnHeader`, `radioGroup`, `list`,
   `listItem`, `form`, `complementary`, `contentInfo`, `main`, `navigation`,
   `region` and `none`. `tabBar` carries a second rule with it: every child
   node of a tab bar has to carry `tab`, so a label node or a focus node
   between the bar and its tabs fails the check rather than degrading. That is
   why `UiSegmented`'s own `Shortcuts` is built with `includeSemantics: false`.
6. **Press feedback.** The state layer, not a ripple: `ink` at 8 percent on
   hover and 12 percent on press in light, and `ink` at 10 and 14 percent in
   dark, 60 ms in and 120 ms out. Capsules may add a 0.98 scale on touch.
   Amended in wave 0: the dark row first said `paper`, which in dark is
   `#17181B`, darker than `ground`. Painting it over a dark surface hides the
   control instead of lifting it. `ink` is the light member of the pair in
   dark, so one token gives the effect the clause describes in both modes.
7. **Text scaling.** Renders at 200 percent text scale with no overflow and
   no clipped glyph; heights grow, widths wrap. No fixed-height text box.
8. **Reduced motion.** Every transition collapses as 04 section 2.5 specifies.
9. **Direction.** Uses `EdgeInsetsDirectional` and `AlignmentDirectional`;
   directional glyphs flip under RTL.
10. **Density.** Reads `Density.of(context)`; never `Platform`.
11. **Tokens only.** No literal colour, size, radius or duration.
12. **Gallery.** Appears on its family page in every variant, state and size,
    in both modes and both densities.

**Amendment, fit (2026-09-16).** Three clauses added by
`11-fit-and-scale.md` section 6; the harness gains a check for each.

13. **Labels never wrap.** Every label `Text` inside a control is one line
    (`maxLines: 1`, `softWrap: false`); the harness pumps the control at 480,
    360, 280 and 200 dp and fails on a label that lays out two lines.
14. **Geometry derives from type.** No height that holds text is a constant:
    it is `max(density height, scaled line height + 2 * inset)`; the harness
    pumps at text scales 1.0, 1.3 and 2.0 and fails on overflow, clipped
    glyphs or a hit box under 48 dp.
15. **Fit is declared.** A control that arranges more than one label names its
    compact variants in its style class, tries them in order when given less
    than its intrinsic width, and ends in an ellipsis with the full label in
    the tooltip and the semantics label only when none fits (11 section 3.3).

## 3. Primitives (L2)

| Primitive | Built on | Responsibility | Notes |
|---|---|---|---|
| `Pressable` | `FocusableActionDetector`, `GestureDetector`, `WidgetStatesController`, `Semantics` | The one way anything becomes interactive: states, hit-box padding to 48, keyboard activation, focus ring, state layer, semantics role and label, disabled reason | Replaces `InkWell`, `InkResponse`, `Material`, `GestureDetector` at call sites. Exposes `builder(context, states)` so a control paints itself from states. Amended in polish 2: it watches the pointer itself while it is disabled, because `FocusableActionDetector` reports a hover only while enabled, so the reason reaches a pointer that arrives rather than only a press; and `disabled` is exclusive of `hovered` and `pressed` in the set the builder is handed. |
| `StateLayer` | `AnimatedContainer` | The hover and press overlay per the contract | Used only inside `Pressable`. |
| `Surface` | `DecoratedBox`, `ClipRSuperellipse` | A solid `paper` or `matte` pane with a shape token and optional hairline | The non-glass container. |
| `GlassSurface` | `BackdropFilter`, `ClipRSuperellipse`, `DecoratedBox` | The 09 section 3.3 recipe at a level; honours `GlassQuality`; asserts in debug that it is not inside a scrolling list item | Counted by `glass_budget`. |
| `FieldLayer` | `CustomPaint`, `RepaintBoundary` | Paints a sky preset once behind a screen; clips the matte exclusion zone passed by the source pane | The only gradient painter in the product. |
| `FocusRing` | `CustomPaint` | The 2 dp ring, 2 dp gap, radius plus 4, outside bounds, on the shape it rings | Amended in wave F: it takes a `FocusRingShape` (`superellipse`, `stadium`, `circle`) and paints an `RSuperellipse`, an `RRect` at half the shorter side, or a circle, so ring and edge run concentric at every corner. Used by `Pressable`, `UiFieldBox` and `UiRadio`; `FieldCore` no longer draws one, because the edge and the ring belong to the same layer. `Pressable.focusRing` turns its own ring off for a control that rings its own edge. |
| `Squircle` | `RoundedSuperellipseBorder`, `ClipRSuperellipse`, `StadiumBorder` | `Squircle.border(radius)`, `Squircle.clip(radius, child)`; switches to capsule when radius is at least half the height | Every corner in the product passes through here. |
| `Popover` | `OverlayPortal`, `TapRegion`, `FocusScope`, `Shortcuts` | Anchored overlay with placement (above, below, start, end, auto), outside-tap and `Escape` dismissal, focus return, `glass.floating` | Base of menus, selects, tooltips, date inputs. |
| `ModalRoutes` | `RawDialogRoute`, `showGeneralDialog`, `PopScope` | `showUiSheet` (bottom, drag handle, `glass.modal`) and `showUiDialog` (centred, max 560 wide); `showUiModal` picks by window class (compact gets the sheet, wider gets the dialog, per 05 section 3.7) | Focus trap, scrim, reduced-motion entrance. |
| `FieldCore` | `TextField(decoration: null)` | Text only: the value, its own placeholder in the same style on the same baseline, the caret and the selection. Exposes controller, focus node, input formatters, `onSubmitted`, read-only, obscured | Amended in wave F: the decoration is absent rather than collapsed, so no `InputDecorator` exists for the bridge theme to paint through, and `showFocusRing` is gone. The one Material component import in the package. |
| `Announcer` | `SemanticsService.announce`, `Semantics(liveRegion:)` | Announce a status change once (06 section 3) | Used by toast, banner, progress. |
| `EdgeFadedRow` | `SingleChildScrollView`, `ShaderMask` | Added in wave G: a row at its own intrinsic width inside a column too narrow for it, scrolled, with the edge faded on the side there is more, and the chosen item scrolled into view | The compact variant 11 section 3.3 gives a tab strip and a navigation row. Used by `UiTabs` and `UiPillNav`, which would otherwise carry two copies of it. The fade extent comes in as a token, because a primitive makes no styling decision of its own. |
| `Scrim` | `AnimatedOpacity` | `scrim` token behind modal glass | |
| `Density` | `InheritedWidget`, `Listener` on the app root | Resolves `UiDensity` from the last `PointerDeviceKind` seen, defaulting from window width | `Density.of(context)`. |

```dart
Pressable(
  semanticsLabel: 'Approve record',
  onPressed: enabled ? approve : null,
  disabledReason: enabled ? null : 'Waiting for label coverage to be confirmed',
  shape: ui.shape.capsule,
  builder: (context, states) => AnimatedContainer(
    duration: ui.motion.pressIn,
    decoration: ShapeDecoration(shape: ui.shape.capsule, color: style.background.resolve(states)),
    child: child,
  ),
);
```

## 4. Controls (L3)

Each entry: anatomy; variants and sizes; state specifics beyond the contract;
semantics; keyboard; motion; the Material widget it retires. Sizes are `sm`
(32 visual, 48 hit), `md` (40 or 48 by density), `lg` (56).

Every paragraph marked "Amended in wave 1" records what the five family slots
and the integration polish slot built where it differs from the first draft,
per section 10: the entry and the control match, or the change that moved them
apart amends the entry in the same breath.

### 4.1 Actions family

**`UiButton`.** Capsule. Anatomy: optional leading glyph 20, label in
`type.label` (`type.title` at `lg`), optional trailing glyph. Variants:
`primary` (fill `ink`, text `paper` in both modes, so the disc inverts with
the mode: dark on a light ground, light on a dark one; this is the reference's
disc and the only high-contrast fill in the product. Amended in wave 0: the
first draft read "in dark fill `paper`, text `ink`", which keeps the disc dark
in dark mode, and `paper` on `ground` in dark measures 1.08:1. That is an
invisible control, which the 3:1 floor in 09 section 3.7 forbids),
`secondary` (glass.flat fill on `paper`, `boundary` stroke, `ink` text),
`ghost` (no fill, `ink` text, state layer only), `danger` (fill
`status.blocked.content`, text `paper`). `loading` swaps the leading glyph for
a 16 dp `UiProgress.ring` and keeps width. Semantics `button`. Retires
`FilledButton`, `OutlinedButton`, `TextButton`, `FilledButton.tonal`.

Amended in wave 1, four ways. A loading button refuses activation and keeps
its enabled paint: a reviewer must not be able to send one decision twice
(02 section 4.3), and draining the fill would read as the server having
withdrawn the action, which busy is not. "Keeps width" is the leading slot's
width, not the button's: the slot is a fixed 20 dp box in both states, so a
button that already had a leading glyph is exactly as wide, and one that did
not gains the slot at the same moment its label changes to the present
participle. The ring inside a button draws no track, because `hairline` is
chosen against `paper` and the ring is drawn in the button's own foreground;
the arc alone reads as a spinner. And `UiButtonStyle.overlay` is a plain
`Color` rather than the `WidgetStateProperty` section 1.5 sketches, because
what varies by state is the opacity, and the contract's two opacities live in
`StateLayer` where they are written once. `UiButton` also takes a
`statesController`, as `ButtonStyleButton` does and for the same reason: hover
and press cannot be drawn in a golden otherwise.

Amended in wave G, three ways. Its height is derived rather than declared
(11 section 2.2): `max(the size table's row, the scaled line box plus twice
the inset)`, so `sm`, `md` and `lg` are 32, the density row and 56 at scale
1.0 and grow from there. Its label is a `UiLabel`, so it is one line and ends
in an ellipsis with the whole word on a tooltip that wraps the control from
outside its `Pressable`, where a tap still reaches the button. And it
publishes `intrinsicWidth(context)`, the width it needs to draw its label
whole, because `UiButtonRow` chooses between a row and a column by measuring
its actions.

**`UiIconButton`.** 48 dp disc (40 in pointer), glyph 24, `ghost` or
`secondary` variant; requires `semanticsLabel`; tooltip on hover and long
press. Retires `IconButton`.

Amended in wave 1: the tooltip is a real `UiTooltip`, and a button the server
forbids draws its `disabledReason` there instead of its own name. The reason
travels by `Pressable.onDisabledReason` into `UiTooltip.reason`, which is the
carrier section 4.3 names. `FocusableActionDetector` reports no hover while it
is disabled, so a press and a long press are the two ways a reviewer asks for
it; the reason is on the semantics hint either way. There is no `primary`
disc: an `ink` filled disc is the current navigation destination (09 section
1), and a second meaning for one shape is the collision one vocabulary exists
to prevent.

**`UiCapsuleToggle`.** The reference's `M W F S` control: a capsule per
option with the label at start and a 16 dp check disc at end that fills on
selection (09 section 8 capsule fill). Single or multiple selection.
Semantics `toggle` per option with `checked`. Arrow keys move, `Space`
toggles. Retires `FilterChip` in filter rows and `ChoiceChip`.

Amended in wave 1: in single selection, choosing the chosen option again
clears it. Filter rows are the use, and a reviewer who can reach a filter has
to be able to reach no filter without a second control.

**`UiChip`.** Capsule at `sm`: optional glyph 16, label `type.label`,
optional trailing remove glyph. Variants `tag` (static, `paper` fill,
`hairline` stroke), `filter` (toggleable, fills `ink` at 8 percent when
selected, `emphasis` stroke), `input` (removable). Never glass. Retires
`Chip`, `InputChip`, `ActionChip`.

Amended in wave 1: a chip takes an optional status triple, filling with
`status.fill` and writing in `status.onFill`. Section 5 defines `StatusChip`
as "`UiChip.tag` with a status triple", so the slot has to exist for that
pattern to re-base on it. `UiChip.input` also paints its capsule as a
background in a stack rather than as a `Pressable`'s own surface, because
`Pressable` drops the semantics of its content and a removable chip has a
second target inside it; that is also what lets the remove glyph keep a 48 dp
box inside a 32 dp capsule.

Amended in wave G: a chip takes a `leading` widget in an `inline` box before
the label, mutually exclusive with `icon`. Section 5 defines `StatusChip` as a
tag with a status triple, and the one status it cannot draw that way is a
measured fraction, which is a ring rather than a glyph; the pattern drew its
own capsule around one because no slot existed. Its height derives from the
`label` role the same way a button's does, and its label is a `UiLabel`.

**`UiSegmented`.** One capsule track with 2 to 5 equal segments and an ink
thumb that glides (navigation glide motion). Semantics: `tab` per segment
with `selected`; arrows move, `Enter` selects. Retires `SegmentedButton`.

Amended in wave 1: the track is `paper` with a `hairline` stroke. The entry
named the thumb and the labels and not the track, and `hairline` is the
separating role, which is what a track is; it also matches `UiChip.tag`. The
segment sitting on the `ink` thumb lifts its state layer toward `paper`,
because `ink` at 12 percent over an `ink` fill is the same colour. The thumb
sits 4 dp inside the track, so the label row is padded by the same inset:
without it the thumb's centre and the segment's differ by the inset at both
ends, which is `inset * (1 - (2k+1)/n)` for segment `k` of `n` and is zero
only in the middle. The 2 to 5 range is asserted in `build` rather than in the
constructor, because a constructor assert that reads `length` cannot be
evaluated in a `const` expression and would make every `const UiSegmented`
a compile error. The control's `Shortcuts` is built with
`includeSemantics: false`, per the note on clause 5 of section 2.

Amended in wave G by 11 section 3.3, which gives this control the only fit
ladder in the family. `UiSegment` grows an optional `icon`; `UiSegmented`
grows an optional `label`, the name the select rung offers the options under.
The intrinsic width is the count times the widest label measured at the
current text scale plus a segment's padding, plus the track's insets, and
every segment is drawn at that one width so the thumb's step is even. Given
less: icon only segments with a tooltip each when every segment carries a
glyph, then a `UiSelect` over the same options when the track is named, then
the segments with their words cut short. Collapsing into the select changes
the form and not the value: nothing is reported and no selection moves. A
track with no name never collapses, which is what `UiTabs` needs, since a
select under its `tabBar` node would be a child of a tab bar that is not a
tab. The `IntrinsicWidth` that used to size the track is gone, because the
width is now declared.

**`UiBadge`.** Count or dot at `label.small` on `ink` (or a status `content`
when it names a status), capsule. Retires `Badge`.

**`UiKeyCap`.** `mono.identifier` on `paper`, `radius.inner`, `boundary`
stroke. Carried from v1.

Amended in wave 1: neither is interactive, so neither runs the control
contract. See the amendment to the preamble of section 2 for what they are
held to instead.

Amended in wave G: both derive their height from the role they draw, a badge
from `label.small` and a cap from `mono.identifier`, so each grows with the
reviewer's text size instead of clipping it (11 section 2.2). Both draw their
text as a `UiLabel`, and because neither is pressed, the tooltip that carries
an overflowing word is the label primitive's own slot rather than a wrapper
around the control.

**`UiButtonRow`.** Added in wave G by 11 section 3.4: a primary action, an
optional secondary and optional tertiary actions, ends aligned with the
primary last, becoming a column with the primary on top when the line does not
fit at the reviewer's text size or the window is compact. Keyboard order is
reading order in both arrangements, which is left to right in the line and top
to bottom in the column. Stacked actions sit on the column's centre line at
their own widths: a capsule pulled to a phone's full width stops reading as
the disc of 09 section 1. It is the one widget in the package that reads
`WindowClass`, because it is an arrangement rather than a control. `UiDialog`
and `UiSheet` adopt it for their actions and patterns use it for form footers,
so no screen writes its own `Row` of buttons.

### 4.2 Inputs family

**`UiField`.** Label above in `type.label` `ink.secondary`; the field itself
is a `radius.field` superellipse of `paper` with a `boundary` stroke that
becomes `ink` 2 dp on focus and `status.blocked.content` on error; optional
leading glyph, trailing clear or action; help text or error text below in
`body.small` with the error glyph; optional counter. No floating label, no
notch. Semantics `textField` with label, value, hint, error announced once.
Retires `TextField` and `TextFormField` at call sites, `OutlineInputBorder`.

Amended in wave 1, three ways, all of them about the anatomy being shared.
The style object is `UiInputStyle`, not `UiFieldStyle`: `foundation/fields.dart`
already owns that name for the light fields of 09 section 3.2, and the word
"field" means two unrelated things in this system. One `UiInputStyle` serves
four controls, against section 1.5's style per control, because 4.2 defines
`UiTextArea`, `UiSearchField` and the trigger of `UiSelect` as this control
with a change, and two style objects would be two places for the edge to
drift; `UiSelectStyle` holds that style plus the list's own tokens.
`UiFieldFrame` and `UiFieldBox` are public, against section 11's one public
class per file, because `UiSelect` lives in another file and has to draw the
same box; the alternative was sixty lines of duplicated chrome and a select
that drifts away from a field. The trailing clear control sits in a
`Positioned.directional` inside the hit area rather than in the row, because a
48 dp action does not fit inside a 40 dp pointer field but does fit inside the
slop the field already pads itself with. Six `bool` properties reach the
control, of which two are visual (`showLabel`, `obscureText`); the other four
are behaviour and keep the SDK's names, so section 11's cap of two is met.

**Amendment, fit (2026-09-16).** The field anatomy above is superseded by
`11-fit-and-scale.md` section 4: the core paints text only (no decorator, its
own placeholder, caret and selection), the box paints the one edge and never
thickens it, the focus ring is the whole focus treatment and is shown for any
focus, and the ring is painted on the box's own shape.

Built in wave F, slot F1, four ways beyond what that paragraph states.
`UiInputStyle.resolve` takes the current `TextScaler` and derives the box
height from it, so a field is the density height at scale 1.0 and the scaled
line box plus the same two insets above it (11 section 2.2); the trigger of
`UiSelect` resolves the same style and grows with it. `UiFieldBox` takes a
`semantics` wrapper that covers the box and never the trailing action: the
field passes a `MergeSemantics` around one `textField` node whose rect is the
48 dp box, which closes the defect wave 2 recorded, an editor publishing a
22 dp node inside the control so that every tap target guideline failed on a
field, while the clear control keeps the separate node and the separate 48 dp
box a second control needs. The editor's value, and its text editing actions,
come up into that node with the merge, so the field's own `Semantics` no
longer states a value of its own and nothing is announced twice. And the
selection colour is a token: `ink` on `accent` at 35 percent clears 4.5:1 on
every opaque surface in both modes, which the composite contrast gate now
holds as a row of its own.

**`UiTextArea`.** `UiField` with `minLines`, `maxLines`, auto-grow.

**`UiSearchField`.** Capsule `UiField` with the search glyph, clear on content,
`Escape` clears then unfocuses, `Enter` submits.

Amended in wave 1: "clears then unfocuses" is two keystrokes, not one. A
reviewer who has typed a query wants the query gone before they want the field
gone, and losing both to one keystroke costs a retype. The key is consumed
either way.

**`UiSelect<T>`.** A `UiField`-shaped trigger showing the selected label and a
caret; opens a `Popover` list with type-to-filter when more than eight
options; single selection. Semantics `button` with `expanded`, list items
`selected`. Arrows move, `Enter` picks, `Escape` closes. Retires
`DropdownMenu`, `DropdownButton`.

Amended in wave F: the trigger rings its own edge rather than the hit box.
Its `Pressable` passes `focusRing: false` and hands `WidgetState.focused`
through to the box, which draws the ring on the shape it painted. A ring
around the hit box sits 4 dp off the edge at the sides and 8 dp off it at the
top in pointer density, where the visual is 40 dp inside a 48 dp box. The
condition is unchanged: keyboard focus only, because a select is not being
edited.

Amended in wave 1: the list items are `UiListRow` at `sm` in its
selection-free mode, which is the row section 4.5 specifies and the same row a
menu uses. The option's glyph takes the row's leading slot, the label is the
title, the check sits in the trailing slot, and the selected row carries the
6 percent fill and the 3 dp bar of the selectable variant. The row is floored
at the 48 dp hit box, so the list's maximum height resolves from that floor
and still shows seven rows and part of an eighth. The popover itself carries
no semantics label: the trigger has just announced the label, the selected
option and `expanded`, and a pane repeating the label is a second thing to
listen past on the way to the options.

**`UiSwitch`.** 44 by 26 capsule track (`boundary` stroke, `paper` fill; `ink`
fill when on) with a 22 dp thumb that glides; optional label at start; the
whole row is the hit box. Semantics `toggled`. Retires `Switch`,
`SwitchListTile`.

Amended in wave 1: the thumb follows the track. It is `ink.secondary` when the
switch is off and `paper` when it is on, because a thumb that is `ink` in both
states reads as "on" while the switch is off. The track keeps the row's shared
`ink` state layer and the filled part carries a second `paper` one of its own:
a single layer colour makes one half of the control answer a hover and the
other half stop answering.

**`UiCheckbox`.** 20 dp `radius.inner` box, `boundary` stroke, fills `ink`
with a `paper` check when checked; indeterminate draws a bar. Label at end;
whole row hits. Semantics `checked`, mixed for indeterminate. Retires
`Checkbox`, `CheckboxListTile`.

Amended in wave 1: an indeterminate box moves to checked when it is pressed,
and never back to mixed. Mixed is a fact about a group, not a state a reviewer
can ask for, so `onChanged` is a `ValueChanged<bool>` rather than a
`ValueChanged<bool?>`.

**`UiRadio<T>`.** 20 dp disc on `RawRadio`; group semantics; arrows move
within the group. Retires `Radio`, `RadioListTile`.

Amended in wave F: the ring is a circle around the 20 dp disc, not a rounded
rectangle around the whole row. A row ring put a corner radius around a circle
and ran 20 dp of empty label into the bargain; the disc is what the option is,
and 09 section 3.6's fit amendment says the ring follows the shape.

Amended in wave 1: `UiRadioGroup<T>` ships with it, on the SDK's `RadioGroup`,
so the exclusive group, the arrow keys and the group role come from the SDK
rather than from us. `StateLayer` is used directly in `RawRadio`'s builder,
against its own "used only inside `Pressable`" note, because `RawRadio` owns
the focus node and the gestures and a second `Pressable` around it would put
two stops in the Tab order; clause 6 still wants the press feedback. Wrapping
an SDK control also means stating only what it does not: two `Semantics`
configurations that set the same flag cannot merge, so our node carried the
words and theirs carried the exclusive group until our `enabled` was dropped.

### 4.3 Overlays family

**`UiPopoverMenu`.** `Popover` with `glass.floating`, `radius.tile`, items of
`UiListRow` at `sm` with glyph, label, optional shortcut `UiKeyCap`, optional
destructive tint; submenus not supported. Semantics `menu` and `menuItem`.
Retires `MenuAnchor`, `PopupMenuButton`.

Amended in wave 1: the items are the menu's own row rather than a `UiListRow`.
The shortcut column and the destructive tint are menu specific, and a row
whose title can be tinted is a slot `UiListRow` does not have; giving it one
for a single caller is the configuration this system trades for composition.
The select's option list did move onto `UiListRow` (section 4.2), so the two
lists differ, and a later pass that gives the row a tone should close that.
`UiPopoverMenu.semanticsLabel` is optional: the pane's role announces it as a
menu and its items are visible text, so a label repeating the trigger's is
read twice. `UiMenuTrigger` ships with it, as the trigger a screen names.

**`UiTooltip`.** `Popover` on hover after 400 ms and on long press, `paper`
fill (not glass: tooltips are small and frequent), `body.small`, `radius.inner`.
Semantics `tooltip`; also the `disabledReason` carrier for `Pressable`.
Retires `Tooltip`.

Amended in wave 1: the semantics are the `tooltip` property on the pane, not
`SemanticsRole.tooltip`, which throws in this SDK (section 2 clause 5), and
not an annotation wrapped around the control either: `Pressable` publishes a
container node, so an annotation above it has no boundary to merge with and
its string lands on the page node instead. A control that draws no words
carries both, the drawn pane and a `Semantics(tooltip:)` folded into its own
node under a `MergeSemantics`, which is what every pill disc, rail disc and
icon button does. The `MergeSemantics` goes above the tooltip and never below
it: inside the tooltip's `OverlayPortal`, a merged node's subtree trips
`SemanticsOwner.sendSemanticsUpdate`'s own assertion,
`node.parent?._dirty != true`. `UiTooltip.reason` is the carrier form, built
around `Pressable.onDisabledReason`.

**`UiToast`.** A `glass.floating` capsule stack anchored above the navigation
(compact) or bottom-start (wider): glyph, one line, optional single action,
auto-dismiss after 6 seconds unless it has an action; queued, one visible at a
time; announced via `Announcer`. Retires `SnackBar`, `ScaffoldMessenger`.

Amended in wave 1: a toast with an action never expires at all. Six seconds
would take the action away as the reviewer reaches for it; `UiToasts.dismiss`
is the shell's way out. `UiToastHost` is the layer and `UiToasts.show` the
entry point, and `UiScaffold` installs a host around its body by default
(section 4.4), so a screen raises a toast with nothing at the call site.

Amended in wave G: the action moves under the message when the two do not fit
on one line, which is 11 section 3.3's row for this control. The message is
content and wraps; the action is a control with a hit box; neither is
squeezed.

**`UiBanner`.** Full-width in-flow strip at `radius.none`: glyph, one line,
optional disclosure to a second line, optional dismiss. The environment banner
(`state.synthetic` fill and glyph) is an instance. Semantics `liveRegion`
once. Carried from v1 `EnvironmentBanner` and generalised.

Amended in wave 1, four ways. There are seven tones rather than three
variants: `info`, the five statuses and `synthetic`, as one enum, because one
enum is what lets the fill, the text colour and the glyph be chosen together
in `resolve`. The `info` tone carries a `hairline` edge on its top and bottom,
because 09 has no informational triple and `paper` on a `paper` pane is a line
of text with no band at all; structure from tone is 09 section 3.1's own
answer. The band caps itself at two lines and truncates, carried from finding
V-15, where the environment band wrapped to eleven lines at 200 percent text
and took half the window; the whole sentence stays on the semantics node. And
the strip's minimum is `space.s6` rather than a control height, so a plain
band is 40 tall and a band with a control is 64; the 48 dp hit box is never
shrunk, the band around it is.

Amended in wave G, three ways. The band takes an action, `actionLabel` and
`onAction`, which 07 section 11 asks of every failure class and wave 2's shell
composed beside the strip for want of a slot; it moves under the words when
the two do not fit on one line. The sentence wraps rather than being cut at
one line: 11 section 3.3 calls it content, and the two line cap finding V-15
asks for is on the band, so closed the sentence may take both lines and open
it takes one while the detail takes the other. And the disclosure and the
dismiss stay on the first line in both arrangements, because they act on the
band rather than on what it reports.

**`UiDisclosure`.** A row (`title`, optional summary, caret) that reveals a
body with `AnimatedSize`; caret rotates 180 degrees; semantics `expanded`;
`Space` and `Enter` toggle. Body content is never glass. Retires
`ExpansionTile`.

Amended in wave G: the title is a `UiLabel` and the summary is content. A
summary is the row's second line, the same object a list row's subtitle is, so
it wraps to two lines before it is cut rather than ellipsising at 200 percent
text in a 360 dp pane.

**`UiTabs`.** A `UiSegmented` at `lg` bound to a `TabController`-free
`ValueNotifier<int>`, plus `UiTabView` that cross-fades panes (shared axis is
declined per 04 section 3.3 until routes need it). Retires `TabBar`.

Amended in wave 1: this is what shipped, and three things follow from it that
the entry did not say. A tab is a label and carries no glyph, because a
segment carries none and because three tabs have to fit side by side at 360.
A strip carries 2 to 5 tabs, which is the segmented control's own range. And
the keyboard is the segmented control's: arrows move focus, `Enter` chooses,
so arrowing past a tab does not swap the pane the reviewer is reading, and the
track clamps at its ends. A caller that needs anything else, glyph tabs or a
row that scrolls, passes it through the `strip` slot rather than growing this
control. `UiTabView` cross fades at `medium` rather than at 04 section 2.4's
`standard` for a panel content swap, on the brief's instruction as the later
document.

Amended in wave G: the strip now has the compact variant 11 section 3.3 gives
it, so a caller no longer has to pass a scrolling row through `strip`. Given
less than the width its labels need, `UiTabs` draws the same `UiSegmented` at
its intrinsic width inside a horizontal scroller whose edges fade on the side
there is something to scroll to, and the chosen tab is scrolled into view when
it changes. One track, one thumb, one keyboard pattern either way. The
`tabBar` role moved inside the scroller, because every child node of a tab bar
has to carry `tab` and a `Scrollable` publishes a node of its own.

**`UiSheet`, `UiDialog`.** The chrome for `ModalRoutes`: `glass.modal`,
`radius.sheet` (top corners for the sheet, all corners for the dialog), drag
handle on the sheet, title in `type.titleLarge`, body, action row with at
most one `primary` and one `secondary` or `ghost`. The reason sheet pattern
(03 section 7.3) is built on `UiSheet`. Retires `AlertDialog`, `showDialog`,
`showModalBottomSheet`, `BottomSheet`.

Amended in wave 1, three ways. The entry points are `UiSheet.show` and
`UiDialog.show`, not `showUiSheet` and `showUiDialog`: those two names belong
to the `ModalRoutes` primitive, which the top barrel exports, and a second
pair would be a collision. `UiDialog.showAdaptive` sits beside them, because
05 section 3.7 asks for one call that picks a sheet on a compact window and a
dialog above it, which the primitive `showUiModal` does for a bare pane and
nothing did for the chrome. `UiModalActions` is public and is not in this
entry, because the action row is identical in both modals and a private class
cannot cross two files in Dart, which section 11's one public class per file
requires. The sheet's drag handle closes it on a downward flick, and carries
no semantics of its own: dragging is never the only way out, because the scrim
and `Escape` both close a dismissible sheet, which is what SC 2.5.7 requires.

Amended in wave G, three ways. `UiModalActions` is the `UiButtonRow` of 11
section 3.4 under the name this family already had for it: it takes tertiary
actions as well, aligns them to the end with the primary last, and becomes a
column with the primary on top when the row does not fit one line or the
window is compact. The sheet bounds its body and scrolls it: its padded block
is `Flexible`, because a `Column` hands an inflexible child an unbounded main
axis and the `Flexible` inside it therefore had nothing to be flexible
against, which is how a filter sheet overflowed a phone by 1044 dp. And both
titles are `UiLabel`, one line with the whole of the title on the semantics
node, because a title that wraps to four lines pushes the body out of the
pane.

Amended in polish 2. `scrollBody` is on the dialog as well as the sheet, and
defaults to true on both, so a body written for `showAdaptive` never has to
know which of the two frames it landed in. A dialog is bounded by the window
it floats in, and two sentences are three lines at 200 percent text on a short
window, so the dialog needed the same thing the sheet has. The application's
filter form was carrying the difference as a height cap of its own.

### 4.4 Navigation family

**`UiPillNav`.** The reference's floating row: a `glass.floating` capsule of
discs, one per destination (2 to 5), glyph 24 in `regular`, the current one an
`ink` disc with a `paper` glyph in `fill` weight; the disc glides between
destinations (09 section 8). Labels are not drawn; each disc carries its label
in semantics and shows it as a tooltip on hover and long press. Sits 16 dp
above the safe area; content scrolls under it with bottom padding equal to its
height plus 16. Semantics: `tab` per disc with `selected`. Arrows move,
`Enter` selects. Retires `NavigationBar`.

Amended in wave 1: the pill is 64 dp tall, `space.s2` of padding around a
48 dp disc slot. Four is the least that keeps the focus ring inside the
capsule's own clip, and eight leaves the ring a clear 4 dp. The disc's glyph
cross fades its `fill` form in over the glide rather than swapping at the end:
swapping pops, and a glyph that turns `ink` the moment the disc leaves it is
wrong for the 250 ms the disc is still over it. Colour and opacity may run
alongside the one authored move (04 section 5.2). The undrawn label reaches a
pointer reviewer as a real `UiTooltip` and a screen reader as a
`Semantics(tooltip:)` folded into the disc's own node (section 4.3).

Amended in wave G: the pill has the compact variant 11 section 3.3 gives a
navigation row, because five 48 dp discs need 240 dp and a pill in a narrow
pane does not always have it. A disc's hit box is 48 at every density and
every text scale, so what gives is the capsule: it scrolls through
`EdgeFadedRow`, the edge fades on the side there is more, and the current
destination is scrolled into view when it changes. The pill overflowed by 56
dp at 200 dp before this, which the gallery matrix counted six times.

**`UiRail`.** For medium windows: a 72 dp column of the same discs, top-aligned
under the mark; extended form at expanded width shows `label.small` under each
disc. Retires `NavigationRail`.

Amended in wave 1, three ways. The rail carries no glass: this entry gives the
sidebar `glass.flat` and names nothing for the rail, so it is a transparent
column of discs over the sky, which also leaves the window's four pane budget
for the top bar, the action bar and the body. Its extended form widens past
72 dp when a label needs it, measured with a `TextPainter` at the live text
scale: a vertical column cannot wrap "Sources", so a fixed 72 either clips it
or overflows at 200 percent text, and measuring is the vertical reading of
clause 7's "heights grow, widths wrap". Its collapsed form is always 72, which
is composed as `space.targetMin + space.s6`, a 48 dp hit box with 12 dp of
gutter, rather than read from `space.rail`, which is the v1 rail at 80 and
still belongs to the screens that have not moved. Arrow keys move `Up` and
`Down` and leave the cross axis alone, per the amendment to clause 3.

**`UiSidebar`.** For large windows: 280 dp, `glass.flat`, the mark and product
name, destinations as `UiListRow` with the 3 dp leading bar on the current one,
the collection switcher as a `UiSelect`, account and help at the bottom.
Retires `Drawer` and the permanent drawer.

Amended in wave 1: the destinations are `UiListRow` in its `tab` mode, and the
current one is marked four ways rather than one. The row's own selectable
variant carries the 6 percent `ink` fill and the 3 dp leading bar of section
4.5; the glyph carries the other two, its `fill` weight and `ink` rather than
`ink.secondary`. The bar's gutter is reserved on every row whether or not the
bar is drawn, so a row becoming current never shifts its words sideways. The
pane publishes a tab list, which is why the row has a `tab` mode at all: every
child node of a `SemanticsRole.tabBar` has to be a tab. The destinations
scroll between the header and the footer, which this entry does not mention
and a 280 dp pane with five destinations at 200 percent text needs, because it
is then taller than the window the sidebar is meant for. The header and footer
are slots, which is what lets the shell put the collection switcher in one.

**`UiTopBar`.** 56 dp (48 pointer), transparent over the fields with a
`glass.flat` fill once content scrolls under it; slots: `leading` (back or the
mark), `title` (`type.title`), `actions` (`UiIconButton`s), optional `center`
(the collection switcher on wide windows). No elevation change, no colour
change on scroll beyond the glass fill. Retires `AppBar`.

Amended in wave 1, five ways. The bar spans the full width above the side
navigation rather than sitting beside it: this entry lists the slots in that
order, the brief says the navigation sits beside the body, and nothing settled
which wins, so the arrangement that also keeps the banner full width is the
one that ships. `title` is a `String`, not a `Widget?` slot as section 11
asks: a title is copy, and the bar sets `type.title` on it the way `UiButton`
sets `type.label` on its label. The glass fill appears at the threshold and
does not fade in, because 09 section 11 rejects glass that animates its
opacity. The bar owns the top and side safe areas, and the scaffold removes
that padding from everything below it, so the pane reaches the window's edges
while its content clears a notch. And `center` is centred in the space the
title and the actions leave, not in the window: centring it in the window lets
it sit on top of a long title, and a collection name is not worth covering a
page title with.

Amended in wave G, three ways. The bar has the fit of 11 section 3.3: the
title ellipsises first, and when a title cut to `space.labelMin` still leaves
no room the actions past the second collapse into an overflow `UiPopoverMenu`
carrying the same labels, glyphs and shortcuts, with a third arrangement that
puts every action in the menu for a column too narrow for two discs and a
trigger. That needs an action the bar can read, so `UiTopBarAction` is the
declared form of the slot; `actions` keeps its `List<Widget>` type and a bar
given plain widgets keeps them all drawn, because a bar cannot put into a menu
a control it cannot describe. The title is an `Expanded` rather than a
`Flexible` beside a `Spacer` where there is no `center`: a `Spacer` is a flex
child, so the title was capped at half the bar and ellipsised at 200 percent
text with the other half of the bar empty beside it. And the bar's height is
the line box of `type.title` floored at the density height rather than the
density height alone (11 section 2.2), which is 56 and 48 unchanged at scale
1.0.

**`UiScaffold`.** The page frame: paints `ground` and the sky preset via
`FieldLayer`, then `topBar`, `banner` slot, `body`, `actionBar` slot (sticky,
`glass.floating`, above the nav), `nav` slot (pill, rail or sidebar chosen by
the caller from window class); applies safe areas and keyboard insets; hosts
the toast layer. Retires `Scaffold`.

Amended in wave 1, four ways. "Hosts the toast layer" is now exact: with no
`overlays` of its own the frame wraps `body` in a `UiToastHost` and gives it
the published bottom inset, so `UiToasts.show` works from anywhere in any page
and a toast clears the chrome. The host has to wrap the body rather than sit
beside it in the stack, because `UiToastHost.maybeOf` walks upward. A caller
that passes its own `overlays` replaces the default and gets no toast layer.
The published inset includes the action bar and not only the pill this entry
names, because a body padded for the pill alone hides its last row under the
action bar; the frame measures what it floats rather than guessing, through a
`RenderProxyBox` and a post frame callback, which is the one frame of lag
`Scaffold` documents for `ScaffoldGeometry`. Overlays paint over the body and
under both the action bar and the navigation, which are one bottom column.
And `UiScaffold.of` returns `UiScaffoldGeometry.none` rather than throwing
when there is no frame above, the way `UiTheme` falls back, because a
component test that pumps one control on its own is the normal case for it.

Three files hold the navigation family's shared parts and are not in the
layout of section 1.2: `nav_destination.dart`, the one destination model all
three navigations take, and `nav_disc.dart` and `nav_group.dart`, the disc the
pill and the rail share and the roving focus all three need. The last two are
not exported from the family barrel.

### 4.5 Data family

**`UiListRow`.** Height from density; slots `leading` (24 glyph, 40 thumbnail
or a `UiCheckbox`), `title` (`type.title` at `md`, `type.body` at `sm`),
`subtitle` (`body.small`, up to two lines), `trailing` (text, chip, caret).
Selectable variant fills `ink` at 6 percent with the 3 dp leading bar in `ink`;
long press enters selection where the caller allows. Never glass. Semantics
`button` or `checkbox` depending on the mode, one merged node. Retires
`ListTile`, `CheckboxListTile`.

Amended in wave 1, four ways. The height is `density.rowHeight` floored at the
48 dp hit box: 09 section 6 gives the pointer row 44, clause 2 sets 48 in both
densities, and a full width row has nowhere to put the 4 dp of transparent
slop above and below without overlapping the rows it tiles against, so the
floor wins in `pointer` and the touch row is unchanged at 56. The row has no
corners of its own: this entry names no radius, the row tiles against its
neighbours and the pane around it owns the shape, so `radius.none` is the
token, which is also what makes the 3 dp bar a rectangle rather than a shape
that has to follow a curve. The leading slot is a fixed 40 dp box whenever
there is one, so a 24 glyph, a 40 thumbnail, an invisible child and a disabled
control all leave the title's edge in one place; a row with no leading child
has no slot and starts its text at the padding. And there is a third mode,
`tab`, beside `navigate` and `select`, because `UiSidebar`'s destinations are
rows inside a `SemanticsRole.tabBar`, whose every child node has to be a tab.

Amended in wave G: the row's fit is 11 section 3.3's row for it. The title and
the subtitle are content and take two lines each before they ellipsise; the
title was capped at one. The trailing drops its word and keeps its glyph when
the title would otherwise fall under `space.labelMin`, which needs a trailing
the row can read, so `UiRowTrailing` is the declared form of the slot.

Amended in polish 2, two ways. The row has a third variant, which is 11
section 3.3's "trailing under the title": the trailing takes a line of its
own, at the start of the column the title heads, when the line cannot hold
both. A `UiRowTrailing` reaches it after its word and its glyph rungs; a
trailing the row cannot read (a chip, a switch, a time) has no glyph rung and
goes there directly, at the point where the line would leave it less than the
hit box, which replaces the bound wave G's integration put on such a trailing.
And the row's tone follows its state, as every other control's does: the
title, the subtitle, a `UiRowTrailing`'s word and glyph, and the selected
row's bar all resolve `disabled.content` when the row is disabled. A row the
server will not open used to be drawn in exactly the ink of one that opens,
with only the absence of a hover saying otherwise, which is nothing at all on
a touch window. What the row does not tint is a slot the caller filled: a
leading glyph or a chip states its own colours and the row does not reach into
them.

**`UiProgress`.** `ring` (16, 24, 40; determinate arc in `ink`, track
`hairline`; indeterminate rotates unless reduced motion, then pulses opacity)
and `bar` (4 dp, `radius.capsule`). Determinate progress keeps its motion under
reduced motion because it is information (04 section 1.5). Semantics
`progressBar` with value. Retires `CircularProgressIndicator`,
`LinearProgressIndicator`.

Amended in wave 1, three ways. `SemanticsRole.progressBar` throws in this SDK
(section 2 clause 5), so the node carries a label that reads the value as a
sentence instead. An indeterminate indicator draws no track: a track is a
scale, and an indeterminate indicator has none to draw one against. And the
control enforces the two rules 04 section 5.5 states as product rules and
names an application call site for breaking: a reported value below the
highest one seen is held at the highest, and the first value is painted where
it is rather than filled up to. The cost is that a genuinely new attempt needs
a new `Key`, exactly as a retry gets its own row, which is documented on the
class.

**`UiSkeleton`.** `paper` at 0.6 blocks in the shape of the content they stand
for; a slow opacity pulse, none under reduced motion. Carried from v1; no
shimmer.

Amended in wave 1: the block is the state layer at the hover opacity, not
`paper` at 0.6. A loading list sits on a `paper` list body (09 section 3.3),
where `paper` on `paper` is nothing at all, and over `ground` in light it
measures about 1.02 to 1; the first data golden drew four placeholders nobody
could see. `ui.color.stateLayer(ui.color.hoverOpacity)` is the same "move the
surface toward its opposite" correction wave 0 made to the state layer itself,
and it is visible on `paper`, on `ground` and under a field in both modes. The
control is outside the semantics tree.

**`UiEmptyState`.** Glyph 40 `light`, `type.title`, one sentence `body`,
at most one `UiButton`. Sits on the sky, no glass. Carried from v1.

Amended in wave 1: the action slot is typed `UiButton?` rather than the
`Widget?` section 11 asks for, because "at most one `UiButton`" is a rule and
a type states a rule better than a comment does. This is the one slot in the
family narrow enough to be worth it.

**`UiDataTile`.** The reference's numeral tile on `glass.flat`, `radius.tile`:
`label` at top-start in `type.label` `ink.secondary`, numeral in
`display.large` (or `display.hero` when the tile is the window's one hero)
with `type.unit` beside the baseline, optional footer line, optional child
slot for an `UiArcIndicator` or a dotted trace. Numeral tick on change. Never
encodes data in its tint (09 section 3.2). Semantics: one node reading label,
value and unit as a sentence.

Amended in wave 1: the value is a `String` and is allowed to wrap. The tile
does not decide how a measurement is written, and "Not measured" at
`display.large` is wider than one tile line; clipping it leaves a tile reading
"Not", which is worse than one that is two lines tall (02 section 4.14). The
one node merges its child's, so a `child` carrying a value of its own states
it in the tile's `semanticsLabel`.

Amended in wave G: the value no longer wraps. 11 section 3.3 gives the tile a
third option the wave 1 amendment did not have, so "Not measured" arrives at a
size that fits rather than on a second line: the numeral steps down one
display role at a time to `display.medium`, and below that the numeral and its
unit are scaled together in a `FittedBox`. Together, because a `FittedBox`
reports its child's unscaled baseline to the row above it and a unit aligned
to a scaled numeral's baseline would float above the digits it belongs to. The
unit's own role never steps down: it is the one upper case role in the product
and a smaller one would read as a different unit.

**`UiArcIndicator`.** A 180 or 270 degree `hairline` arc with an `accent`
triangular marker at the value; optional min and max labels in `unit`. Used by
`RiskMeter` for the total beside its components; asserts on a missing value
and renders the unmeasured glyph instead of a marker (north star: unmeasured
stays unmeasured).

Amended in wave 1, four ways. A null value renders and does not assert: the
two cannot both happen, because an assertion in debug stops the frame, and
unmeasured is a first class state in this product rather than a programming
error. The marker carries a 1 dp `ink` casing around the accent, because the
accent measures near 1 to 1 on `paper` and a marker that is the only thing
saying where the value is has to be visible on the surfaces it is drawn over;
09 section 3.4 carries the rule. The word "Unmeasured" is set in `type.label`,
not in `unit`: it is not a unit, and `unit` is the one upper case role in the
product (09 section 4.2). And the minimum and maximum labels are dropped when
there is no value, because a scale beside no value is a scale for nothing.

**`UiAvatar`.** 32 or 40 dp disc with initials in `label` on `ink` at 8
percent, or an image. Semantics `image` with the person's name.

**`UiHairline`.** 1 dp `hairline`, inset-aware. Retires `Divider`.

## 5. Patterns (L4): how the existing product widgets re-base

| Pattern (app `lib/src/widgets/`) | Built from | Change |
|---|---|---|
| `StatusChip` | `UiChip.tag` with a status triple and `UiIcons` | Same API; colours and glyph from `context.ui.color.status` and `ui.icons` |
| `EvidenceSource`, `TermText`, `CaveatText`, `NotCalibratedChip` | `UiChip`, `UiTooltip`, type roles | Cosmetic |
| `DiffText` | own painter, type roles | Keeps its painter and marker rules; colours from tokens |
| `FieldRow` | `UiListRow`, `UiDisclosure`, `DiffText` | Layers (literal, parsed, normalised) become a `UiDisclosure` body |
| `ReadingCard`, `AuthorityCandidateCard` | `Surface` (paper, `radius.tile`), `UiButton.ghost` | Selected state uses the `emphasis` stroke, not glass |
| `RiskMeter` | `UiDataTile` with `UiArcIndicator` | Total beside components, unmeasured glyph when missing |
| `ReasonSheet` | `UiSheet`, `UiField`, `UiTextArea`, `UiButton` | Same contract: change, reason, confirm in one surface |
| `EvidenceDrawer` | `UiSheet` or `UiDialog` by window class, `mono.code` | Raw JSON stays behind "View raw" |
| `QueueRow`, `SourceObjectRow`, `UploadItem` | `UiListRow` | Selection mode via the row's selectable variant |
| `SelectionBar` | `glass.floating` capsule with `UiButton`s and a count | Anchored like the toast layer |
| `EnvironmentBanner` | `UiBanner` | Same copy, `flask` glyph |
| `Thumbnail`, `RegionOverlay`, `InFlightGlyph`, `MotionReveal`, `MeasuredHeight`, `Skeleton`, `EmptyState`, `KeyCap`, `AdaptiveForm` | tokens, `UiSkeleton`, `UiEmptyState`, `UiKeyCap`, `ModalRoutes` | `AdaptiveForm` delegates to `showUiModal` |

## 6. The gallery

`UiGallery` is a widget in the package (`lib/src/gallery/`) with one page per
family plus a foundation page (type specimen including `0O 1lI 5S 2Z 8B` in
Geist Mono, colour roles on every surface, fields and glass levels, shape
tokens, icons). Each control page renders every variant, size and state in a
grid, with light and dark and touch and pointer as page-level toggles. The app
mounts it at `/gallery` when `kReleaseMode` is false, so `flutter run -d
chrome` and a visit to `/gallery` is how the direction is reviewed by eye. The
package's golden tests render each page in all four combinations and check
them into `test/gallery/goldens/`. These goldens are the taste review: a
change to any control shows up as a diff on its family page before it shows
up on a screen.

Amended in wave 1: a family golden is captured at the height its page needs,
not at one shared window. The width is the gallery's 1180 everywhere; the
height is 820 for actions, 1180 for inputs, 1000 for overlays, 940 for
navigation and 1900 for data, measured against the page rather than guessed.
Actions moved to 2540 in wave G, measured the same way, when the page gained
the Fit block 11 section 3.5 asks for; see the amendment at the end of this
section.

Overlays, navigation and data moved again in wave G, measured the same way,
when each page gained the fit section 11 section 3.3 asks for: 1540 for
overlays, 1220 for navigation and 2280 for data. Data moved once more in
polish 2, to 2360, when the row gained the variant that puts its trailing
under the title and the 200 dp specimen grew by a line: the page measures 2343
and 2360 is the first height with nothing left to scroll. Two of those pages also state
a frosted pane count of their own, seven for overlays and eight for data,
because a sheet that shows one toast or one tile per column draws four of
them; a product window draws one toast and one row of tiles.
Inputs moved to 1600 in wave F, measured the same way, when the page gained
the box section 11 section 4 asks for: the box itself in each shape, at rest,
focused, and focused with a value under the caret. One control on a page can
hold focus and the rest cannot, so a page that only autofocused would review
one of the shapes it ships and leave the others unseen.
Eight controls in every variant, size and state do not fit 820, and a golden
that reviews the top of a page is not reviewing the controls below the fold.
Each family owns its own window, so taking a taller one moves no other
family's files. The actions page was the one still taller than its window;
wave G measured it at 1616 without the Fit block and 2492 with it, and took a
2540 window, so the family is now reviewed whole rather than down to its
fold.

Two goldens are not pages: `overlays-sheet-<mode>` and
`overlays-dialog-<mode>` capture the window with the modal open, at the
standard 1180 by 820, because a sheet and a dialog are judged against the
window they are drawn over rather than against the page behind them.

The shell draws its own page list in the sidebar, so registering a page would
move every other page's golden. It carries three lists instead:
`foundationPages`, `familyPages` and `galleryPages`, which is both. `/gallery`
shows `galleryPages`; `test/gallery/foundation_golden_test.dart` pins
`foundationPages`, so the twenty four foundation goldens hold byte for byte
however many families register.

A page with a spinner, a shimmer or a pulse on it wraps that specimen in a
`TickerMode(enabled: false)`: a repeating animation makes `pumpAndSettle` time
out, and every gallery golden calls it. A golden presses no key, so no focus
ring is drawn in one unless the test states
`FocusManager.instance.highlightStrategy = FocusHighlightStrategy.alwaysTraditional`.

**Amendment, fit (2026-09-16).** Every family page renders at the four window
classes and at text scales 1.0, 1.3 and 2.0 in both modes, twenty four goldens
per page, and a Fit page shows each fit declaring control in 480, 360, 280 and
200 dp columns. Below `medium` the gallery shell's page list becomes a
`UiSelect` above full width content (11 section 3.5).

## 7. Testing strategy

Package tests, run with `flutter test` from `packages/specimen_ui/`:

- `test/flutter_test_config.dart` loads Geist and Geist Mono from the package
  assets with `FontLoader`, so every golden renders in the product typeface.
  This also fixes the v1 defect where goldens rendered in the platform sans.
- One behaviour test per control plus a call to `expectControlContract`.
- One golden test per gallery page: light and dark, touch and pointer.
- Foundation tests: `contrast_composite` (09 section 3.7),
  `palette_only_literals`, `icons_unique`, `layering` (parses imports under
  `lib/src/` and asserts the L1 to L3 direction), `fonts` (both families
  resolve to the bundled assets and `GoogleFonts` does not exist in the
  dependency graph).

App tests, run from `apps/specimen_digitization/`:

- The existing suite stays green throughout. Screen goldens
  (`test/golden/images/`) and semantics fixtures
  (`test/accessibility/fixtures/`) are regenerated once per wave by the
  integrator, never by a component agent; the diff is reviewed as evidence,
  as the v1 rebuild did.
- Finders migrate from Material types (`find.byType(FilledButton)`) to roles
  and labels (`find.bySemanticsLabel`, `find.byWidgetPredicate((w) => w is
  UiButton)`), so a component change does not break a screen test that was
  really about behaviour.
- `test/theme/` keeps the gates below.

Goldens are generated on macOS as today. With fonts bundled, the platform
sans no longer leaks into them, so they are deterministic across machines
with the same Skia build.

## 8. Gates

All gates are tests, so they run wherever `flutter test` runs. Each gate with
a backlog carries a `Map<String, int>` of file to count that may only shrink,
the mechanism `test/theme/no_color_literals_test.dart` already uses.

Added after wave 1: `no_stand_ins`. Parallel family slots need each other's
controls before they exist, so a slot builds a private one and marks it
`TODO(fe/<family>)`. Six of those were built and all six are now the real
control. A stand-in that outlives its wave is a second implementation of a
control, which is what one vocabulary exists to prevent (section 0, property
6), so the marker is a gate rather than a convention.

| Gate | Mechanism | Backlog |
|---|---|---|
| `no_color_literals` | `Color(0x` allowed only in `packages/specimen_ui/lib/src/foundation/palette.dart` | none from day one |
| `no_material_components` | Regex over `lib/**.dart` for the retired widget list in 1.3 followed by `(`, plus `showDialog(`, `showModalBottomSheet(`, `ScaffoldMessenger` | per-file counts, shrink-only, empty at the end |
| `no_material_imports` | `import 'package:flutter/material.dart'` under `lib/src/screens/`, `lib/src/widgets/`, `lib/src/app/` except `app_router.dart`; in the package, only `primitives/field_core.dart`, `foundation/theme.dart` and `controls/overlays/tooltip.dart` | per-file, shrink-only |
| `no_literal_geometry` | Every static size, not the four patterns this row first named; two tests, `apps/specimen_digitization/test/theme/no_literal_geometry_test.dart` over the application's `lib/` and `packages/specimen_ui/test/gates/no_literal_geometry_test.dart` over the package's. Patterns and allowances in the amendment below | application: per-file, shrink-only; package: none, apart from the wave F handoff the integrator empties |
| `glass_budget` | Counts `BackdropFilter` render objects in every golden window; at most 4, at most 1 inside a modal route | none |
| `layering` | Import direction inside the package (section 1.1) | none |
| `icons_unique` | Every `UiIcons` value distinct; no `Symbols.` or `Icons.` under `lib/` | `Symbols.` per-file backlog during the icon migration |
| `fonts_bundled` | Families resolve to assets; `google_fonts` absent from `pubspec.lock` | none |
| `contrast_composite` | 09 section 3.7 | none |
| `strings` | `scripts/ci/check_ui_strings.py` extended to `packages/specimen_ui/lib` | existing baseline mechanism |
| `no_dashes` | No em or en dash in any `.dart` string literal or `design/*.md` | none |
| `no_stand_ins` | No `TODO(fe/` marker under the package's `lib/` | none |
| `no_fallback_text_style` | Every gallery page and every overlay pumped under `WidgetsApp`; no `RenderParagraph` carries the framework fallback style or a double underline (11 section 5) | none |
| `fit_matrix` | The golden matrix of 11 section 3.5: four window classes by three text scales by two modes per family page, plus the Fit page | none |

**Amendment, fit (2026-09-16, 11 sections 1 and 2.2).** `no_literal_geometry`
is now a census of every static size rather than four sample patterns, and it
runs as two tests so the design system can hold itself to zero while the
application burns a backlog down. It fires on a `BorderRadius` or `Radius`
constructor, on a digit radius given to `Squircle`, `RSuperellipse`,
`ClipRSuperellipse` or `RoundedSuperellipseBorder` or named `radius`,
`borderRadius` or `cornerRadius`, on `Duration`, on `EdgeInsets` and
`EdgeInsetsDirectional`, on `BoxConstraints`, on `Offset` and `Size`, and on a
number given to `width`, `height`, `minWidth`, `maxWidth`, `minHeight`,
`maxHeight`, `dimension`, `fontSize` or `letterSpacing`. Each file is read once
and its comments and its strings' contents are masked before matching, so prose
never counts and a finding's line number is the line in the file. The allowances
are values, paths or a named shape, never a comment on a line: the values 0, 1
and 2, which are the absence of a size, the hairline and the emphasis stroke;
`lib/src/foundation/*.dart` in the package, where a token is defined, and
`lib/src/gallery/**`, where a width is the subject rather than a decision;
`lib/src/models` in the application, where a number came off the network;
generated files; a number inside brackets, which is a list index; and the
`paint` method of a `CustomPainter`, where geometry is arithmetic on the size
the canvas was given. There is no per-line escape hatch, deliberately: a number
that genuinely must be written down becomes a token in the foundation. One
number is one finding wherever it was found, so two patterns that reach the same
digit do not count it twice, and fixing one call clears every finding it
carried. All ten of the application's `Duration` findings are elapsed time
rather than motion (seven request timeouts, a poll interval, a search debounce
and a cooldown), so the resolution there is one named constant in the file that
owns the policy rather than a motion token; the package's three are interaction
delays that 10 section 4.3 fixes and `foundation/motion.dart` says belong to
it.

## 9. Definition of done for a component

A control merges when all of these are true:

1. Its entry in section 4 (or an amendment to it in the same change) matches
   what was built: anatomy, variants, sizes, states, semantics, keyboard.
2. Its style object exists with every token it uses; no literal anywhere.
3. `expectControlContract` passes, with the `ControlActivation` the control
   needs, unless the control is not interactive, which section 2's preamble
   scopes out and names.
4. Behaviour tests cover every variant and every state transition it owns.
5. It appears on its gallery page in every variant, size and state, and the
   family golden is regenerated in all four combinations.
6. Reduced motion, 200 percent text and RTL are exercised in its tests.
7. `flutter analyze --fatal-infos` is clean in the package and the app.
8. `CHANGELOG.md` has an entry.
9. The Material widget it retires is named in the entry, and its count in the
   `no_material_components` backlog has not grown.
10. No `TODO(fe/` stand-in for another family's control is left under the
    package's `lib/`. A slot that has to build one because its sibling has not
    merged says so in its closeout, and the slot that merges the sibling swaps
    it; the `no_stand_ins` gate in section 8 is what makes that a rule rather
    than an intention.
11. The session closeout entry in `docs/SESSION_LEARNINGS.md` is appended.

## 10. Versioning and change control

The package is in-repo and versioned in its `pubspec.yaml`. Breaking API
changes bump the minor version and carry a `@Deprecated` shim for one wave
with the replacement named in the message. A change to a token value is a
design decision: it is proposed as an edit to 09 in the same pull request, and
the gallery golden diff is the evidence reviewed. A new component is proposed
as an entry in section 4 before it is built.

## 11. Naming

- Classes: `Ui` prefix for controls and primitives (`UiButton`, `UiField`,
  `Pressable` and `Surface` are the two exceptions because they are not
  controls). Styles: `UiButtonStyle`. Enums: `UiButtonVariant`, `UiSize`.
- Tokens: dotted in documents (`ink.secondary`), camelCase in code
  (`ui.color.inkSecondary`). Names are roles, never values.
- Props: slots as `Widget?` (`leading`, `trailing`, `child`); choices as
  enums; at most two `bool` visual props per control.
- Accessibility labels are required parameters wherever a control has no
  visible text (`UiIconButton`, `UiPillNav` destinations, `UiAvatar`).
- Files: one public class per file, snake_case matching the class.

## Sources

- Brad Frost, Atomic Design, chapter 2, for the layer vocabulary.
- Flutter 3.38.5 SDK sources for the primitives named in section 1.1.
- Radix Primitives and shadcn/ui, for the behaviour-first, owned-code model
  this package follows without depending on their Flutter ports (see the
  compatibility findings in the build plan).
- WAI-ARIA Authoring Practices for the keyboard patterns in sections 2 and 4.
- v1 record: [03-design-system.md](03-design-system.md) sections 7 and 8.
