# 10. Component library: `specimen_ui`

Status: **agreed architecture, not yet built.** Written 2026-09-16. This
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
  lib/src/primitives/
    pressable.dart  state_layer.dart  surface.dart  glass_surface.dart  field_layer.dart
    focus_ring.dart  squircle.dart  popover.dart  modal_routes.dart  field_core.dart
    announcer.dart  scrim.dart
  lib/src/controls/
    actions/   button.dart icon_button.dart capsule_toggle.dart chip.dart segmented.dart badge.dart key_cap.dart  actions.dart (family barrel)
    inputs/    field.dart text_area.dart search_field.dart select.dart switch.dart checkbox.dart radio.dart  inputs.dart
    overlays/  popover_menu.dart tooltip.dart toast.dart banner.dart disclosure.dart tabs.dart sheet.dart dialog.dart  overlays.dart
    navigation/ pill_nav.dart rail.dart sidebar.dart top_bar.dart scaffold.dart  navigation.dart
    data/      list_row.dart progress.dart skeleton.dart empty_state.dart data_tile.dart arc_indicator.dart avatar.dart hairline.dart  data.dart
  lib/src/gallery/             one page per family; UiGallery shell
  test/
    flutter_test_config.dart   loads the bundled fonts with FontLoader so goldens use Geist
    harness/control_contract.dart
    foundation/                contrast_composite_test, palette_only_literals_test, icons_unique_test, layering_test, fonts_test
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

1. **States.** Rest, hover, focus, pressed, selected, disabled, loading, error
   and read-only exist where they apply, are driven by one
   `WidgetStatesController`, and are visually distinct in the gallery.
2. **Hit box.** At least 48 by 48 dp in both densities. In `pointer` density
   the visual may be 40 dp; the 8 dp difference is transparent slop.
3. **Keyboard.** Focusable; `Space` and `Enter` activate; arrow keys move
   within composite controls (segmented, radio group, menu, tabs, pill nav);
   `Escape` dismisses an overlay and returns focus to its trigger; `Tab` never
   gets trapped except inside a modal, where it cycles.
4. **Focus ring.** Drawn per 09 section 3.6, only for keyboard focus
   (`FocusManager.highlightMode == traditional`), never on pointer press.
5. **Semantics.** A role (`button`, `toggle`, `checkbox`, `radio`, `tab`,
   `textField`, `link`, `header`, `image`, `liveRegion` as applicable), a
   label that stands alone, a value where there is one, `enabled`,
   `selected` or `checked` or `toggled` where applicable, and for a disabled
   control the reason on `hint` and on a tooltip (03 section 3.6).
6. **Press feedback.** The state layer, not a ripple: `ink` at 8 percent on
   hover and 12 percent on press in light, `paper` at 10 and 14 percent in
   dark, 60 ms in and 120 ms out. Capsules may add a 0.98 scale on touch.
7. **Text scaling.** Renders at 200 percent text scale with no overflow and
   no clipped glyph; heights grow, widths wrap. No fixed-height text box.
8. **Reduced motion.** Every transition collapses as 04 section 2.5 specifies.
9. **Direction.** Uses `EdgeInsetsDirectional` and `AlignmentDirectional`;
   directional glyphs flip under RTL.
10. **Density.** Reads `Density.of(context)`; never `Platform`.
11. **Tokens only.** No literal colour, size, radius or duration.
12. **Gallery.** Appears on its family page in every variant, state and size,
    in both modes and both densities.

## 3. Primitives (L2)

| Primitive | Built on | Responsibility | Notes |
|---|---|---|---|
| `Pressable` | `FocusableActionDetector`, `GestureDetector`, `WidgetStatesController`, `Semantics` | The one way anything becomes interactive: states, hit-box padding to 48, keyboard activation, focus ring, state layer, semantics role and label, disabled reason | Replaces `InkWell`, `InkResponse`, `Material`, `GestureDetector` at call sites. Exposes `builder(context, states)` so a control paints itself from states. |
| `StateLayer` | `AnimatedContainer` | The hover and press overlay per the contract | Used only inside `Pressable`. |
| `Surface` | `DecoratedBox`, `ClipRSuperellipse` | A solid `paper` or `matte` pane with a shape token and optional hairline | The non-glass container. |
| `GlassSurface` | `BackdropFilter`, `ClipRSuperellipse`, `DecoratedBox` | The 09 section 3.3 recipe at a level; honours `GlassQuality`; asserts in debug that it is not inside a scrolling list item | Counted by `glass_budget`. |
| `FieldLayer` | `CustomPaint`, `RepaintBoundary` | Paints a sky preset once behind a screen; clips the matte exclusion zone passed by the source pane | The only gradient painter in the product. |
| `FocusRing` | `CustomPaint` | The 2 dp ring, 2 dp gap, radius plus 4, outside bounds | Used by `Pressable` and `FieldCore`. |
| `Squircle` | `RoundedSuperellipseBorder`, `ClipRSuperellipse`, `StadiumBorder` | `Squircle.border(radius)`, `Squircle.clip(radius, child)`; switches to capsule when radius is at least half the height | Every corner in the product passes through here. |
| `Popover` | `OverlayPortal`, `TapRegion`, `FocusScope`, `Shortcuts` | Anchored overlay with placement (above, below, start, end, auto), outside-tap and `Escape` dismissal, focus return, `glass.floating` | Base of menus, selects, tooltips, date inputs. |
| `ModalRoutes` | `RawDialogRoute`, `showGeneralDialog`, `PopScope` | `showUiSheet` (bottom, drag handle, `glass.modal`) and `showUiDialog` (centred, max 560 wide); `showUiModal` picks by window class (compact gets the sheet, wider gets the dialog, per 05 section 3.7) | Focus trap, scrim, reduced-motion entrance. |
| `FieldCore` | `TextField(decoration: InputDecoration.collapsed)`, `FocusRing` | Text editing with no Material chrome; exposes controller, focus node, input formatters, `onSubmitted`, read-only, obscured | The one Material component import in the package. |
| `Announcer` | `SemanticsService.announce`, `Semantics(liveRegion:)` | Announce a status change once (06 section 3) | Used by toast, banner, progress. |
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

### 4.1 Actions family

**`UiButton`.** Capsule. Anatomy: optional leading glyph 20, label in
`type.label` (`type.title` at `lg`), optional trailing glyph. Variants:
`primary` (fill `ink`, text `paper`; in dark fill `paper`, text `ink`; this is
the reference's dark disc and the only high-contrast fill in the product),
`secondary` (glass.flat fill on `paper`, `boundary` stroke, `ink` text),
`ghost` (no fill, `ink` text, state layer only), `danger` (fill
`status.blocked.content`, text `paper`). `loading` swaps the leading glyph for
a 16 dp `UiProgress.ring` and keeps width. Semantics `button`. Retires
`FilledButton`, `OutlinedButton`, `TextButton`, `FilledButton.tonal`.

**`UiIconButton`.** 48 dp disc (40 in pointer), glyph 24, `ghost` or
`secondary` variant; requires `semanticsLabel`; tooltip on hover and long
press. Retires `IconButton`.

**`UiCapsuleToggle`.** The reference's `M W F S` control: a capsule per
option with the label at start and a 16 dp check disc at end that fills on
selection (09 section 8 capsule fill). Single or multiple selection.
Semantics `toggle` per option with `checked`. Arrow keys move, `Space`
toggles. Retires `FilterChip` in filter rows and `ChoiceChip`.

**`UiChip`.** Capsule at `sm`: optional glyph 16, label `type.label`,
optional trailing remove glyph. Variants `tag` (static, `paper` fill,
`hairline` stroke), `filter` (toggleable, fills `ink` at 8 percent when
selected, `emphasis` stroke), `input` (removable). Never glass. Retires
`Chip`, `InputChip`, `ActionChip`.

**`UiSegmented`.** One capsule track with 2 to 5 equal segments and an ink
thumb that glides (navigation glide motion). Semantics: `tab` per segment
with `selected`; arrows move, `Enter` selects. Retires `SegmentedButton`.

**`UiBadge`.** Count or dot at `label.small` on `ink` (or a status `content`
when it names a status), capsule. Retires `Badge`.

**`UiKeyCap`.** `mono.identifier` on `paper`, `radius.inner`, `boundary`
stroke. Carried from v1.

### 4.2 Inputs family

**`UiField`.** Label above in `type.label` `ink.secondary`; the field itself
is a `radius.field` superellipse of `paper` with a `boundary` stroke that
becomes `ink` 2 dp on focus and `status.blocked.content` on error; optional
leading glyph, trailing clear or action; help text or error text below in
`body.small` with the error glyph; optional counter. No floating label, no
notch. Semantics `textField` with label, value, hint, error announced once.
Retires `TextField` and `TextFormField` at call sites, `OutlineInputBorder`.

**`UiTextArea`.** `UiField` with `minLines`, `maxLines`, auto-grow.

**`UiSearchField`.** Capsule `UiField` with the search glyph, clear on content,
`Escape` clears then unfocuses, `Enter` submits.

**`UiSelect<T>`.** A `UiField`-shaped trigger showing the selected label and a
caret; opens a `Popover` list with type-to-filter when more than eight
options; single selection. Semantics `button` with `expanded`, list items
`selected`. Arrows move, `Enter` picks, `Escape` closes. Retires
`DropdownMenu`, `DropdownButton`.

**`UiSwitch`.** 44 by 26 capsule track (`boundary` stroke, `paper` fill; `ink`
fill when on) with a 22 dp thumb that glides; optional label at start; the
whole row is the hit box. Semantics `toggled`. Retires `Switch`,
`SwitchListTile`.

**`UiCheckbox`.** 20 dp `radius.inner` box, `boundary` stroke, fills `ink`
with a `paper` check when checked; indeterminate draws a bar. Label at end;
whole row hits. Semantics `checked`, mixed for indeterminate. Retires
`Checkbox`, `CheckboxListTile`.

**`UiRadio<T>`.** 20 dp disc on `RawRadio`; group semantics; arrows move
within the group. Retires `Radio`, `RadioListTile`.

### 4.3 Overlays family

**`UiPopoverMenu`.** `Popover` with `glass.floating`, `radius.tile`, items of
`UiListRow` at `sm` with glyph, label, optional shortcut `UiKeyCap`, optional
destructive tint; submenus not supported. Semantics `menu` and `menuItem`.
Retires `MenuAnchor`, `PopupMenuButton`.

**`UiTooltip`.** `Popover` on hover after 400 ms and on long press, `paper`
fill (not glass: tooltips are small and frequent), `body.small`, `radius.inner`.
Semantics `tooltip`; also the `disabledReason` carrier for `Pressable`.
Retires `Tooltip`.

**`UiToast`.** A `glass.floating` capsule stack anchored above the navigation
(compact) or bottom-start (wider): glyph, one line, optional single action,
auto-dismiss after 6 seconds unless it has an action; queued, one visible at a
time; announced via `Announcer`. Retires `SnackBar`, `ScaffoldMessenger`.

**`UiBanner`.** Full-width in-flow strip at `radius.none`: glyph, one line,
optional disclosure to a second line, optional dismiss. The environment banner
(`state.synthetic` fill and glyph) is an instance. Semantics `liveRegion`
once. Carried from v1 `EnvironmentBanner` and generalised.

**`UiDisclosure`.** A row (`title`, optional summary, caret) that reveals a
body with `AnimatedSize`; caret rotates 180 degrees; semantics `expanded`;
`Space` and `Enter` toggle. Body content is never glass. Retires
`ExpansionTile`.

**`UiTabs`.** A `UiSegmented` at `lg` bound to a `TabController`-free
`ValueNotifier<int>`, plus `UiTabView` that cross-fades panes (shared axis is
declined per 04 section 3.3 until routes need it). Retires `TabBar`.

**`UiSheet`, `UiDialog`.** The chrome for `ModalRoutes`: `glass.modal`,
`radius.sheet` (top corners for the sheet, all corners for the dialog), drag
handle on the sheet, title in `type.titleLarge`, body, action row with at
most one `primary` and one `secondary` or `ghost`. The reason sheet pattern
(03 section 7.3) is built on `UiSheet`. Retires `AlertDialog`, `showDialog`,
`showModalBottomSheet`, `BottomSheet`.

### 4.4 Navigation family

**`UiPillNav`.** The reference's floating row: a `glass.floating` capsule of
discs, one per destination (2 to 5), glyph 24 in `regular`, the current one an
`ink` disc with a `paper` glyph in `fill` weight; the disc glides between
destinations (09 section 8). Labels are not drawn; each disc carries its label
in semantics and shows it as a tooltip on hover and long press. Sits 16 dp
above the safe area; content scrolls under it with bottom padding equal to its
height plus 16. Semantics: `tab` per disc with `selected`. Arrows move,
`Enter` selects. Retires `NavigationBar`.

**`UiRail`.** For medium windows: a 72 dp column of the same discs, top-aligned
under the mark; extended form at expanded width shows `label.small` under each
disc. Retires `NavigationRail`.

**`UiSidebar`.** For large windows: 280 dp, `glass.flat`, the mark and product
name, destinations as `UiListRow` with the 3 dp leading bar on the current one,
the collection switcher as a `UiSelect`, account and help at the bottom.
Retires `Drawer` and the permanent drawer.

**`UiTopBar`.** 56 dp (48 pointer), transparent over the fields with a
`glass.flat` fill once content scrolls under it; slots: `leading` (back or the
mark), `title` (`type.title`), `actions` (`UiIconButton`s), optional `center`
(the collection switcher on wide windows). No elevation change, no colour
change on scroll beyond the glass fill. Retires `AppBar`.

**`UiScaffold`.** The page frame: paints `ground` and the sky preset via
`FieldLayer`, then `topBar`, `banner` slot, `body`, `actionBar` slot (sticky,
`glass.floating`, above the nav), `nav` slot (pill, rail or sidebar chosen by
the caller from window class); applies safe areas and keyboard insets; hosts
the toast layer. Retires `Scaffold`.

### 4.5 Data family

**`UiListRow`.** Height from density; slots `leading` (24 glyph, 40 thumbnail
or a `UiCheckbox`), `title` (`type.title` at `md`, `type.body` at `sm`),
`subtitle` (`body.small`, up to two lines), `trailing` (text, chip, caret).
Selectable variant fills `ink` at 6 percent with the 3 dp leading bar in `ink`;
long press enters selection where the caller allows. Never glass. Semantics
`button` or `checkbox` depending on the mode, one merged node. Retires
`ListTile`, `CheckboxListTile`.

**`UiProgress`.** `ring` (16, 24, 40; determinate arc in `ink`, track
`hairline`; indeterminate rotates unless reduced motion, then pulses opacity)
and `bar` (4 dp, `radius.capsule`). Determinate progress keeps its motion under
reduced motion because it is information (04 section 1.5). Semantics
`progressBar` with value. Retires `CircularProgressIndicator`,
`LinearProgressIndicator`.

**`UiSkeleton`.** `paper` at 0.6 blocks in the shape of the content they stand
for; a slow opacity pulse, none under reduced motion. Carried from v1; no
shimmer.

**`UiEmptyState`.** Glyph 40 `light`, `type.title`, one sentence `body`,
at most one `UiButton`. Sits on the sky, no glass. Carried from v1.

**`UiDataTile`.** The reference's numeral tile on `glass.flat`, `radius.tile`:
`label` at top-start in `type.label` `ink.secondary`, numeral in
`display.large` (or `display.hero` when the tile is the window's one hero)
with `type.unit` beside the baseline, optional footer line, optional child
slot for an `UiArcIndicator` or a dotted trace. Numeral tick on change. Never
encodes data in its tint (09 section 3.2). Semantics: one node reading label,
value and unit as a sentence.

**`UiArcIndicator`.** A 180 or 270 degree `hairline` arc with an `accent`
triangular marker at the value; optional min and max labels in `unit`. Used by
`RiskMeter` for the total beside its components; asserts on a missing value
and renders the unmeasured glyph instead of a marker (north star: unmeasured
stays unmeasured).

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

| Gate | Mechanism | Backlog |
|---|---|---|
| `no_color_literals` | `Color(0x` allowed only in `packages/specimen_ui/lib/src/foundation/palette.dart` | none from day one |
| `no_material_components` | Regex over `lib/**.dart` for the retired widget list in 1.3 followed by `(`, plus `showDialog(`, `showModalBottomSheet(`, `ScaffoldMessenger` | per-file counts, shrink-only, empty at the end |
| `no_material_imports` | `import 'package:flutter/material.dart'` under `lib/src/screens/`, `lib/src/widgets/`, `lib/src/app/` except `app_router.dart`; in the package, only `primitives/field_core.dart`, `foundation/theme.dart` and `controls/overlays/tooltip.dart` | per-file, shrink-only |
| `no_literal_geometry` | `BorderRadius.circular(<digits>)`, `Duration(milliseconds: <digits>)`, `EdgeInsets.all(<digits>)`, `SizedBox(height: <digits>)` in app widgets and screens | per-file, shrink-only; introduced in the polish wave |
| `glass_budget` | Counts `BackdropFilter` render objects in every golden window; at most 4, at most 1 inside a modal route | none |
| `layering` | Import direction inside the package (section 1.1) | none |
| `icons_unique` | Every `UiIcons` value distinct; no `Symbols.` or `Icons.` under `lib/` | `Symbols.` per-file backlog during the icon migration |
| `fonts_bundled` | Families resolve to assets; `google_fonts` absent from `pubspec.lock` | none |
| `contrast_composite` | 09 section 3.7 | none |
| `strings` | `scripts/ci/check_ui_strings.py` extended to `packages/specimen_ui/lib` | existing baseline mechanism |
| `no_dashes` | No em or en dash in any `.dart` string literal or `design/*.md` | none |

## 9. Definition of done for a component

A control merges when all of these are true:

1. Its entry in section 4 (or an amendment to it in the same change) matches
   what was built: anatomy, variants, sizes, states, semantics, keyboard.
2. Its style object exists with every token it uses; no literal anywhere.
3. `expectControlContract` passes.
4. Behaviour tests cover every variant and every state transition it owns.
5. It appears on its gallery page in every variant, size and state, and the
   family golden is regenerated in all four combinations.
6. Reduced motion, 200 percent text and RTL are exercised in its tests.
7. `flutter analyze --fatal-infos` is clean in the package and the app.
8. `CHANGELOG.md` has an entry.
9. The Material widget it retires is named in the entry, and its count in the
   `no_material_components` backlog has not grown.
10. The session closeout entry in `docs/SESSION_LEARNINGS.md` is appended.

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
