# 11. Fit and scale

How the system sizes itself: what Flutter has where the web has `px` and
`rem`, who owns an edge, a width and a text style, and what a control does when
it is given less room than it needs. Written on 2026-09-16 after checkpoint 1
from three defects seen in the served gallery. It adds rules that 09 and 10
lacked and amends 09 section 3.6 and 10 sections 2, 4 and 8 where noted. Every
agent working on `specimen_ui` from wave F on reads it whole.

## 0. The three defects, read as one

| Seen in the gallery | Looked like | Layers actually at fault |
|---|---|---|
| A focused field drew three edges: a grey outline, a thick white ring, a thin white ring | `UiField` | The v1 Material `InputDecorationTheme` on the bridge `ThemeData` still painted its own enabled and focused borders beneath the "collapsed" decoration inside `FieldCore`; `FieldCore` painted its own focus ring; `UiFieldBox` thickened its outline on focus and painted a second ring around it; the ring was a circular rounded rectangle around a superellipse box, so the two never ran concentric at a corner |
| A segmented control in a 300 dp column broke every label into letters; a button read "Open a popove r" | `UiSegmented`, `UiButton` | Control labels could wrap (one `maxLines` across the 25 control files that draw text); `Expanded` segments shrank below their label; the gallery shell kept its 220 dp sidebar at phone width, so the content column got 130 dp; no control declares what it does with less width than it needs; family goldens render at one comfortable width |
| A dialog's text was underlined twice in yellow | `UiDialog` | `MaterialApp` installs a fallback text style through `WidgetsApp` (red monospace, double yellow underline) that `Material` normally replaces; the package never published a `DefaultTextStyle` of its own, so a route pushed on the root navigator inherited the fallback; the shell slot then patched `main.dart` and the queue slot patched each product modal, two fixes at L5 and L4 for an L1 responsibility; the test harness pumps controls where the fallback never appears |

The common cause is not a token and not a widget. Each layer was correct on
its own and nobody owned the seam between layers. Three ownership rules close
all three classes of defect: one text style source (section 5), one width
policy per control (section 3), one edge per control (section 4).

## 1. Units: what Flutter has where the web has `px` and `rem`

| Web | Flutter | This system |
|---|---|---|
| `px`. Device independent since CSS 2.1; scales with browser zoom | The logical pixel, written dp here. Device independent: one CSS px on the web, one point on iOS, 1/160 in on Android. Browser zoom changes `devicePixelRatio` and nothing in the app sees it | Every space, radius and stroke token is in dp. Nothing in the system is in device pixels |
| `rem`. The user's root font size | `MediaQuery.textScaler`: the platform text size setting (Dynamic Type on iOS, font scale on Android). `Text` applies it by itself. The web has no platform setting that reaches Flutter; the application supplies one | The type scale in 09 section 4.2 is the root. Anything that must grow with type derives from the scaled line height (section 2.2) |
| `em`. Relative to the local font | `TextStyle.fontSize` in scope | Inline glyphs and inline gaps derive from the adjacent role (section 2.2) |
| Media queries | `MediaQuery.sizeOf(context)` | `WindowClass` (section 3.1): read at the scaffold and by screens and patterns, never by a control |
| Container queries | `LayoutBuilder` constraints | A control's fit policy (section 3.3) reads the width it is given, never the window |
| `vw`, `vh` | Fractions of `MediaQuery.sizeOf` | Panes as fractions with dp minimums (05 section 2) |
| `clamp()` | `.clamp()` | Only on derived values. The type scale is never clamped per control |

What native platforms do, and what this system does: type scales with the
user's setting, spacing stays fixed and content reflows, and layout switches
between declared variants by window class. Nothing zooms as a whole. That is
HIG (Dynamic Type; layout guides) and M3 (font scale to 200 percent; window
size classes), and it is the rule here. "Everything in rem" is not the model.
"Type in rem, space in dp, arrangement by class, fit by constraints" is.

## 2. Text scale

### 2.1 One source

`MediaQuery.textScaler` is the only source of text scale. The application root
clamps it to 0.85 through 2.0 with `TextScaler.clamp`, because the control
contract promises 200 percent and promises nothing above it. On the web, where
the browser's preference does not reach Flutter, the root supplies the
reviewer's own setting from preferences once that product feature exists;
until then it is 1.0. No control reads or clamps the scaler itself. Tests pump
at 1.0, 1.3 and 2.0.

### 2.2 Geometry derives from type

A height that contains text is never a constant. `UiTypeScale.lineHeightOf`
returns a role's line box at the current scale; a control's height is
`max(density height, lineHeight + 2 * inset)`, where the inset is the value
that reproduces the density height at scale 1.0 (for `body` in a 40 dp pointer
control: (40 - 21.75) / 2). Hit boxes stay 48 dp at every scale. Inline glyphs
(`UiIconSize.inline`, 20 dp) scale with the scaler clamped to 1.5; standalone
glyphs do not scale. Space tokens do not scale. Field, button, segmented, chip,
list row, top bar and tab heights all follow this rule.

Every role carries `TextLeadingDistribution.even`, so the extra leading a
`height` multiplier adds is split equally above and below the glyphs and text
sits at the centre of its line box; Flutter's default distributes it in
proportion to ascent and descent, and Geist's asymmetry then floats text above
centre inside a box. That float is the visible cause of "the text sits high" in
fields. A `StrutStyle` built from the role locks the line box on a line that
mixes styles, such as a numeral beside its unit.

## 3. Space

### 3.1 Window classes

`WindowClass` moves from the application (`lib/src/layout/window_class.dart`)
into the package foundation (`foundation/window.dart`) unchanged: compact below
600, medium below 840, expanded below 1200, large below 1600, extra large from
1600. `WindowClass.of(context)` reads it. `Adaptive<T>` holds one value per
class and resolves to the nearest smaller class that is set:
`const Adaptive<int>(compact: 1, expanded: 3).of(context)` gives 1 on medium
and 3 on large. Scaffolds, screens and patterns choose arrangements with these
two. A control never reads either.

### 3.2 Density

Unchanged from 09 section 6. Density is the spacing modifier. It never changes
a hit box and never changes a type size.

### 3.3 Fit: the width policy of a control

A control has an intrinsic width: its widest label at the current text scale
plus its padding and glyphs. Given at least that, it lays out as the gallery
draws it. Given less, in order:

1. **A label never wraps.** Every `Text` that is a label inside a control is
   `maxLines: 1`, `softWrap: false`.
2. **A control never shrinks itself below its intrinsic width.** `Expanded`
   and `Flexible` inside a control never squeeze a label.
3. **Given less than its intrinsic width, the control switches to its declared
   compact variant** (table below). A control with several variants tries them
   in the order listed.
4. **When no variant fits, the label ends in an ellipsis**, the full label goes
   to the tooltip and to the semantics label, and the control keeps its height.
   Nothing is lost to the reader and nothing ever grows a second line.

Parents own arrangement. A row of buttons, chips or tiles wraps or stacks by
window class; it never asks a child to shrink. Content text (body copy, row
titles, help text, banner text) is not a label and wraps as content should.

| Control | Intrinsic width | Compact variants, in order | Last resort |
|---|---|---|---|
| `UiSegmented` | count times (widest label plus segment padding) plus insets | equal segments at the widest label; icon only segments with tooltips when every segment carries a glyph; a `UiSelect` with the same options, where the track carries a name to offer them under | ellipsis in each segment |
| `UiButton` | label plus glyph plus padding | none: a button keeps its width and the parent arranges | ellipsis; the tooltip carries the label |
| `UiChip` | label plus glyph plus padding | none | ellipsis |
| `UiTabs`, navigation rows | sum of labels | a scrolling row with edge fades | ellipsis |
| `UiTopBar` | leading plus title plus actions | title ellipsis; actions beyond two collapse into an overflow menu | title ellipsis |
| `UiDataTile` | numeral plus unit | the numeral steps down one display role at a time to `display.medium` | `FittedBox` on the numeral |
| `UiListRow` | title plus trailing | trailing drops its label and keeps its glyph; the title takes two lines (it is content) | title ellipsis |
| `UiDialog`, `UiSheet` actions | primary plus secondary | the actions stack, primary on top | ellipsis |
| `UiBanner`, `UiToast` | text plus action | the action moves under the text | the text wraps (it is content) |
| `UiField` | label, box, footer | none: the box stretches to the width given; label and footer wrap as content | none |

**Constraints, learned in wave G (2026-09-16).** `UiLabel` measures its own
overflow with a `LayoutBuilder`, so a control that carries a label cannot sit
under `IntrinsicWidth` or `IntrinsicHeight`; a pane that needs equal widths
uses a `Table`, a `Flex` with fixed flexes, or `Adaptive` widths. A trailing a
`UiListRow` cannot measure (a chip, a switch, a time) is bounded to the room
left once the title has its minimum, and ellipsises through its own label;
the declared "trailing under the title" variant for compact windows is open.
Gallery pages stack their specimen columns below 320 dp per column
(`GalleryColumns`), so the matrix pictures a control's fit policy at 360 dp
and never the page's squeeze.

### 3.4 Arrangement: `UiButtonRow`

The one arrangement every screen needs is a row of actions. `UiButtonRow`
(package, `controls/actions/`) takes a primary, an optional secondary and
optional tertiary actions, aligns them to the end with the primary last, and
becomes a column with the primary on top when the row does not fit in one line
or the window is compact. `UiDialog` and `UiSheet` use it for their actions;
patterns use it for form footers. No screen writes its own `Row` of buttons.

**Amendment, wave G (2026-09-16).** Two things the row found in the building.
The select rung above needs a name for the choice, so `UiSegmented` takes an
optional `label` and a track without one keeps its segments and ellipsises
them. That is the rung a tab strip has to skip anyway: `UiTabs` publishes
`SemanticsRole.tabBar` with `explicitChildNodes`, and a select beneath that
node is a child of a tab bar that is not a tab, which the SDK's own check
fails rather than degrades. And a stacked action sits on the column's centre
line at its own width rather than stretched to the column: a `UiButton` is the
reference's disc, and a capsule pulled to the full width of a phone stops
reading as one.

### 3.5 The gallery proves it

Every family page renders at the four window classes (compact 360, medium 700,
expanded 1000, large 1400 dp wide) and at text scales 1.0, 1.3 and 2.0, in both
modes: twenty four goldens per page. A new Fit page places each control of the
table above in 480, 360, 280 and 200 dp columns, at rest and focused. The
gallery shell itself gets a compact layout: below `medium` the page list is a
`UiSelect` above the content and the content takes the full width. The shell
is the first consumer of `Adaptive`.

## 4. One edge: the field, rebuilt inside out

From the inside out, each layer owns exactly one thing.

**`FieldCore` (L2) owns text.** It hosts editing through the Material
`TextField` infrastructure with `decoration: null`, so no `InputDecorator`
exists to paint a border, a hint or padding, whatever the bridge theme says.
The core draws the placeholder itself in the same `TextStyle` as the text
(`type.body`, `ink.tertiary`), on the same baseline, hidden the moment the
value is non empty. Caret: `ink`, `stroke.emphasis` wide, radius 1, the scaled
line height tall. Selection: `accent` at 35 percent (`ink` on it clears 4.5:1
in both modes; the composite contrast test gains the row). Strut from
`type.body`. The core paints no edge and no ring; `showFocusRing` goes. Typed
text, placeholder and caret become one object with one style.

**`UiFieldBox` (L3) owns the edge, and there is one.** Fill `paper`; edge
`boundary` at `stroke.boundary`; a superellipse at `radius.field`, or a stadium
for a capsule. The edge never changes width. Error turns the edge
`status.blocked.content`. Disabled uses `disabled.fill` and `disabled.outline`.
On focus the box shows the system focus ring of 09 section 3.6 and nothing
else. `FocusRing` paints the ring on the same shape as the edge, a superellipse
ring for a superellipse box and a stadium ring for a capsule, at the component
radius plus 4, so the two run concentric at every corner.

**Focus rule for fields** (amends 10 section 2 clause 4). A field shows the
ring for any focus, pointer or keyboard, because a focused field is being
edited and a caret alone does not say which of several fields that is. Every
other control shows the ring only for keyboard focus, as before.

**Metrics.** Box height `max(density.controlHeight, lineHeight + 2 * inset)`;
start padding `s4` (`s5` in a capsule); end padding `s1` before a trailing
action; leading glyph at `inline` size in `ink.secondary` with an `s2` gap;
trailing action in a 48 dp hit box that overlaps the slop. Multiline: top
aligned, vertical `s3`, grows to `maxLines`, then scrolls.

**`UiFieldFrame` owns words around the box.** Label in `type.label`
`ink.secondary`, flush with the box's outer edge, `s2` above the box; footer in
`type.body.small` `s2` below it, one line of help, or the error in
`status.blocked.content` announced once, with the counter at the end. This is
the only place a field's label and message live.

**The bridge theme.** `specimenInputTheme` stays on the `ThemeData` bridge
until the last Material `TextField` leaves the application in wave 3 (13
remain: `review_context.dart`, `reading_declarations.dart`,
`region_editor.dart`, the workbench readings and fields panels,
`reason_sheet.dart`). The package renders identically with or without it, and
the harness pumps fields both ways.

**Proof.** An inputs test focuses a field and counts painters in its subtree:
exactly one `ShapeDecoration` with a side and exactly one ring painter. The
inputs gallery page adds focused and typing states for each shape and size,
which the golden matrix then covers at three scales.

## 5. One text style source

`UiTheme` publishes a `DefaultTextStyle` (`type.body`, `ink`,
`decoration: none`) alongside its tokens, so every subtree under it, including
every route on the root navigator, reads the system's text style and never the
framework fallback. Modal frames, popovers, tooltips and toasts publish it again
from `context.ui`, so the package is correct inside any host, including a bare
`WidgetsApp` and the gallery. `main.dart`'s `_Text` and the wrapper in
`product_modal.dart` are removed once the package publishes it.

The `no_fallback_text_style` gate pumps every gallery page under a `WidgetsApp` carrying the same fallback style `MaterialApp` installs,
opens every overlay, walks every `RenderParagraph`, and fails on a style whose
`debugLabel` names the framework fallback or whose decoration is a double
underline.

## 6. Control contract additions (10 section 2)

13. **Labels never wrap.** Section 3.3, rule 1. The harness pumps the control at
    480, 360, 280 and 200 dp and fails on any label `Text` that lays out more
    than one line.
14. **Geometry derives from type.** Section 2.2. The harness pumps at 1.0, 1.3
    and 2.0 and fails on any overflow, any clipped glyph and any hit box under
    48 dp.
15. **Fit is declared.** Section 3.3, rules 2 to 4 and the table. A control that
    arranges more than one label names its variants in its style class and the
    Fit page shows each.

## 7. Work breakdown

Wave F (two slots in parallel, disjoint files), then wave G (three slots in
parallel, cut from the F merge), then wave 3 as planned in
`docs/execution/FRONT_END_REFACTOR.md`. Wave 3 waits for F and G because the
source pane, the workbench panels and intake are mostly fields and rows of
actions, and would otherwise be built on the anatomy this document retires.

| Slot | Branch | Owns | Delivers |
|---|---|---|---|
| F1 fields | `fe/fit-fields` | `primitives/field_core.dart`, `primitives/focus_ring.dart`, `controls/inputs/*`, the inputs gallery page and its goldens, the edge count test | Section 4 in full; superellipse and stadium rings; `UiSelect` on the same box |
| F2 foundation | `fe/fit-foundation` | `foundation/window.dart` (new), `foundation/type.dart` (line height, strut), `foundation/theme.dart` (the published `DefaultTextStyle`), `primitives/modal_routes.dart`, `primitives/popover.dart`, `primitives/fit.dart` (new: `FitBuilder`, label measurement), the tooltip and toast frames for text style only, `no_fallback_text_style`, the harness clauses 13 to 15 (added, enabled per family by wave G), the application root clamp and the `WindowClass` re-export | Sections 2, 3.1, 5 and the harness |
| G1 actions fit | `fe/fit-actions` | `controls/actions/*` (after F1), `UiButtonRow`, the actions gallery page | Table rows for segmented, button and chip |
| G2 surfaces fit | `fe/fit-surfaces` | `controls/overlays/*`, `controls/navigation/*`, `controls/data/*`, their gallery pages | Table rows for top bar, tabs, tile, row, dialog, sheet, banner and toast |
| G3 gallery matrix | `fe/fit-gallery` | `gallery/gallery_shell.dart`, the Fit page, the golden matrix test and its goldens directory | Section 3.5: the compact shell, the Fit page, twenty four goldens per family page |

The integrator merges F1 and F2, regenerates the family goldens, cuts G1 to G3
from that head, merges them, regenerates every golden and fixture once, runs
the gates, and then cuts wave 3. G3's matrix goldens are regenerated by the
integrator after G1 and G2 land, since they picture the controls those slots
change.
