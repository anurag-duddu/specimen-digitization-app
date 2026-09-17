# Changelog

## 0.3.0 (2026-09-17)

The fit and scale release. `design/11-fit-and-scale.md` read three defects seen
in the gallery as one cause: every layer was correct on its own and nobody
owned the seam between two of them. It closed all three with three ownership
rules, one text style source, one width policy per control and one edge per
control, and waves F and G carried those rules through the foundation, the
field, all five control families and the gallery. Polish 2 closed the package
defects the screen waves found while they were doing it.

What a caller gets: every control declares what it does with less width than
it needs, every height that holds text derives from the type scale rather than
from a constant, no route on the root navigator can inherit the framework's
fallback text style, and the gallery pictures all of it at four window classes
by three text scales by two modes.

Moving from 0.2.0: `FocusRing.capsule` is now `shape: FocusRingShape.stadium`,
`FieldCore.showFocusRing` is gone, and `UiModalActions` no longer takes a
`style`. Every `resolve` that draws text takes a `TextScaler` that defaults to
`TextScaler.noScaling`, so a call site that passes nothing behaves as it did.

### Composition
- `UiStickyBar` is new (`controls/navigation/sticky_bar.dart`, 13 section 3.5): a pinned sliver of one fixed extent for the row that scrolls up to the header and then sticks, drawn solid on `ground` and carrying the `header` marker; added by the integrator at the wave A merge so the record's segments and the queue's search row are the same bar.
- `UiCollapsingHeader` is new (`controls/navigation/collapsing_header.dart`, 13 section 3.1). A pinned `SliverPersistentHeader` between `maxFraction` and `minFraction` of the viewport height, defaulting to 0.55 and 0.40 (07 section 6.1), with a `content` slot and a `chrome` list of rows riding its lower edge. The last chrome row rides the edge and survives the collapse; the rows above it clip and fade as the band shrinks to one row at the minimum. The fractions are floored by the row the chrome must keep, so a short window at 200 percent text grows the header rather than clipping its controls. `glass.flat` paints behind the chrome only once the header is collapsed, at the threshold and without fading (09 section 11), which is the one frosted pane 13 section 2.2 allows a compact window. The collapse tracks the scroll under reduced motion, because a scroll position is not a transition. `primary: true` also marks it `PrimaryRegion`, so a screen never restates a height only the header can compute. It is not an interactive control and does not run the control contract, the way a skeleton and a data tile do not. **Polish 3:** a header built with `primary: true` is the region under review, which is content and not chrome: it publishes `PrimaryRegion` on its content's own box, at the extent it pins less the one chrome row that survives the collapse, and no `PinnedChrome` at all; a header built without `primary` keeps the `header` marker at the extent it pins. Reason: 13 section 2.3 lists a pinned header among the five regions and 13 section 4.1 pins this one at 40 percent of a phone while giving the whole of the chrome 28, so both screen slots wrapped the header in a `PinnedChrome(extent: 0)` to say what the pattern now says itself; and the marker moved onto the content's box because a marker around a sliver has no box for the fold gate to read, which is why the record put its own marker there. The chrome rows are not marked either: at 200 percent text on a phone the frame's own regions are already 201.75 of the 236.3 dp the budget allows and one row is 80, and the rows are inside the extent 13 section 2.5 measures already. This amends 13 section 2.3.
- `UiStatusStrip` is new (`controls/data/status_strip.dart`, 13 section 3.2). One line: a `disposition` slot, the `facts` joined into one `UiLabel` so the line ellipsises at its end rather than dropping a fact, and a `UiBlockers` summary that opens `UiBlockersSheet`, one row per blocker with the control that clears it. `UiBlocker` carries the label, an optional second line, and the action; a blocker with no action is a row with nothing to do and publishes no role. Fit: the summary keeps its words while the line holds them and drops to its glyph below that, with the words on the tooltip and the semantics label. The strip is 40 dp of its own and 48 with the summary on it, because a hit box is never shrunk. `onBlockers` overrides the sheet for a screen that presents the list somewhere of its own.
- `UiDecisionBar` is new (`controls/actions/decision_bar.dart`, 13 section 3.3). One row of `density.controlHeight` floored at the hit box, which is 64 once the scaffold's action bar pane has padded it: the primary, the secondary beside it or in the bar's own overflow menu when the line does not hold both, the count, and previous and next as edge buttons from `medium` up. The count is the `Expanded` child and ellipsises first, because the decision is what the reviewer came to make. The bar measures a button through `UiButtonStyle` rather than estimating it, so the variant it chooses is the one that fits. `UiDecisionSwipe` is the compact half: a fling across the evidence moves between records, against the reading direction in both scripts, and both moves reach a screen reader as named custom actions. `UiDecisionBar` reads `WindowClass`, which 11 section 3.1 allows a pattern and not a control.
- `UiBanner.strip` is new (13 section 3.5): one `label` line on the tint with the sentence, the administrator `contact` slot and the band's recovery behind a tap. `UiBannerForm` names the two forms and `UiBandForm` publishes the one a route asked for; a banner that states its own `form` ignores the ambient ask, because an explicit form is a decision and the ambient one is a default. 13 budgets the band at 32 dp; the strip opens a sheet, so it is a control, and the tint fills the 48 dp hit box this system never shrinks rather than floating inside it. `onTap` overrides the sheet.
- `UiScaffold` settles the compact window's one frosted pane (13 section 2.2; 09 section 3.3). Every pinned region used to draw its own: the top bar's fill once content scrolled under it, the action bar, the pill and a collapsed `UiCollapsingHeader`'s chrome, which is four panes on a phone where the budget is one, and two of them stacked is the "glass decision bar over a glass pill" 13 section 0 reads as a defect. The frame now spends the pane on the chrome it floats, the action bar where there is one and the navigation otherwise, and publishes `GlassQuality.off` to everything else inside itself, so a region that is no longer frosted is still the surface it was, drawn solid. Medium and above are unchanged. **This amends 13 section 3.1**, which gives the collapsed header's chrome that one pane: a record screen has an action bar as well, so the two clauses cannot both hold, and 2.2 is the one the gates measure.
- `UiScaffold` settles the medium window's two panes, and the top bar's at every class (13 section 2.2; polish 3). The record at medium drew three where the class allows two: the scrolled top bar, the frame's action bar and the collapsed header's chrome all blurred, because the wave A rule published `GlassQuality.off` at compact only. The rule now: the chrome the frame floats and the pane over the photograph, a collapsed header's chrome, are the two panes a medium window spends, and the frame's top bar is never a pane at any class. Its fill once content scrolls under it is the same `glass.flat` surface drawn solid, as it already was at compact, so a wider class spends its room on the panes over the work rather than on a bar the reviewer scrolls past. The shell's `_SolidBar`, which drew the compact bar's fill on `ground` while the gate still counted a solid pane, is now redundant with the frame's policy and can go.

- A Composition gallery page, registered in `galleryPages` beside the Fit page and belonging to no family because it draws four of them at once. It builds the record screen's compact composition from the patterns above with placeholder evidence, at rest and scrolled, and shows each pattern on its own beside it. Its own goldens are captured at 390, 768 and 1180 dp, each at the height the page measures in that window, because a composition is an arrangement and an arrangement is only evidence at more than one width; the matrix covers the same page at four classes by three scales by two modes. A specimen column publishes its own width as the window it is painted into, so a 240 dp specimen of a compact decision bar is a compact window whatever the reviewer's screen is.
- Three defects the pictures found and the patterns now carry. `UiCollapsingHeader` stretches its content across the header, which a `Column` does not do by default, so a photograph on its matte is the width of the window rather than the width of whatever it contains. `UiDecisionBar` measures a button through `UiButtonStyle` and declares the overflow arrangement's own intrinsic width, so at a width that holds neither arrangement the primary ellipsises rather than the row overflowing. `UiStatusStrip` bounds its disposition slot to the width the line leaves it, measured with a `LayoutBuilder`: a `Row` hands an inflexible child an unbounded main axis, so a chip at 200 percent text laid out at its intrinsic width and pushed the line over, and making it flexible gave it an even share whether it needed one or not. That is the answer `UiListRow` reached for a trailing it cannot measure, and it is the rule for any slot a control cannot read.

- `UiScaffold` gains the route driven behaviour of 13 section 3.4. `UiScaffoldSlots.of(context)` is the hook a routed screen publishes through, the same seam `UiScaffoldExclusion` already is and for the same reason: the shell builds one frame and the router swaps the body inside it. `setActionBar` fills the sticky pane, `setNavVisible` hides the navigation, and `setBandCompact` asks the frame's own banner slot for the one line form. Each wins over what the scaffold's caller passed, and each takes an `owner` so that `release(owner)` gives back only what that screen still holds: a router builds the screen arriving before it disposes the screen leaving, and a screen that cleared the slots outright on the way out would take the next screen's decision bar with it. `UiScaffold.navVisible` is the caller's own answer. A hidden navigation is `Offstage` rather than absent, so a pill keeps the destination it was on and still holds no viewport height. The frame marks its own top bar, banner, action bar and floating navigation with `PinnedChrome`, so a screen composed only from the patterns is measured without adding a marker of its own. The action bar's marker is on the pane, which is the decision bar plus the padding around it and so is the 64 dp of 13 section 4.1; `UiDecisionBar` carries no marker itself, because a marker inside a marker would be counted twice. No two markers nest.

- `UiScaffoldSlots.setTopBar` joins the three asks of 13 section 3.4, and for the reason the other three exist: the shell builds one frame and the router swaps the body inside it, so a screen that names itself cannot name itself at the frame's call site. A record's bar carries back, the specimen identifier and refresh, and none of the three is a fact the shell holds (13 section 4.1); the region editor's is back, its title and save. It takes an `owner` and is given back by `release(owner)` like every other slot, and the frame reads `_slots.topBar ?? widget.topBar`, so a shell that sets the bar by route and a screen that sets its own agree rather than fight. Without it the one way out of a record on a phone is the navigation pill, which 13 section 2.3 hides on that very screen.

- A null written to a `UiScaffoldSlots` slot by a caller that names itself gives the slot back only where that caller holds it; a null that names no one, which is what `release` writes, still clears it outright. The queue stays mounted under the record pushed over it and gives back the bulk bar it no longer needs on the route change, and that null used to arrive one frame after the record's decision bar and take it with it, which the chrome budget read as a screen well inside its budget. Found at the wave A merge of `fe/compose-record` and `fe/compose-shell`.
- `UiScaffoldSlots.setNavVisible(false)` hides the navigation the frame floats, the pill, and no longer a rail or a sidebar: 13 section 2.3 hides the pill inside a record because the way out is the bar's back, and a rail or a sidebar is a column beside the body that a desktop has no other navigation than. The caller's own `UiScaffold.navVisible` still governs both. The record asks at every window, and at 1440 by 900 the sidebar vanished inside a record; the shell's test caught it at the wave A merge.

- `primitives/composition_markers.dart` is new, and is the whole of what the composition gates read (13 section 5). `PinnedChrome` marks a region that holds viewport height and names which of the five jobs it does through `UiPinnedRegion` (`topBar`, `band`, `header`, `actionBar`, `navigation`); `PrimaryRegion` marks the one region a screen exists to show. Both build their child and nothing else, so a marker is one element and no render object, and the element still resolves to the child's box. `PinnedChrome.extentOf(element)` and `PrimaryRegion.minExtentOf(element)` are the one rule for reading a height off a marker: the extent it declares where there is one, the box under it otherwise, and a `FlutterError` naming the region when it has neither, which is a sliver that forgot to say what it pins. A rail and a sidebar are columns beside the body rather than chrome over it, so they hold no viewport height and are not marked.

### Foundation
- `foundation/window.dart` is new. `WindowClass` moves in from the application
  unchanged, same breakpoints and same members, and `Adaptive<T>` arrives with
  it: one optional value per class, resolving to the nearest smaller class
  that is set. The application file is a re-export, so no call site moved.
- Every type role carries `TextLeadingDistribution.even`. Flutter splits the
  leading a `height` multiplier adds in proportion to ascent and descent, and
  Geist's asymmetry then floats text above the centre of its line box, which
  is the visible cause of "the text sits high" in a field. Text drawn under a
  `Material` was already even, because Material's own 2021 typography sets it
  and `ThemeData` merges the product roles onto that; text this package draws
  was not. Every gallery golden moves.
- `UiType` gains the geometry of 11 section 2.2: `lineHeightOf`,
  `unscaledLineHeightOf`, `strutOf`, `insetFor` and `controlHeightFor`. A
  height that contains text is now derived rather than declared:
  `max(density height, scaled line height + 2 * inset)`, the inset being what
  reproduces the density height at scale 1.0.
  `controlHeightFor` takes a `UiDensity` rather than a `UiThemeData`, because
  the theme is composed of the type scale and a token file that imports the
  theme inverts that.
- `UiType.insetAround(restingHeight, style)`, `UiType.heightAround(...)` and
  `UiType.heightAroundAt(...)` in the foundation. Reason: wave F derived a
  height from a `UiDensity`, and the `sm` and `lg` rows of the size table, a
  badge and a key cap are heights that hold text without being the density
  row. `insetFor` and `controlHeightAt` are now the density shaped call of
  the same two functions, so there is one formula rather than five copies.
- Integration: `UiType.lineHeightAt` and `UiType.controlHeightAt` take an explicit `TextScaler`, and the context forms delegate to them, so `UiInputStyle.resolve`, which is handed a scaler, derives the field's height from the same source as every other control.
- `UiThemeData.defaultTextStyle` is the product's ambient text style,
  `type.body` in `ink` with `decoration: none`, and `UiTheme` publishes it as
  a `DefaultTextStyle` around its child. Every subtree under the tokens,
  including every route on the root navigator, now reads the system's style
  rather than the framework fallback that `MaterialApp` installs. `UiTheme`'s
  constructor is no longer `const`; its public surface is otherwise unchanged
  and it is still the inherited widget itself, so `context.ui` is one lookup.
- `UiSpace.labelMin` is new: `targetMin * 2`, the least width a one line label
  or title is worth drawing in before a control switches to its compact
  variant. Reason: 11 section 3.3 rule 3 needs a threshold and the grid had
  none. Below it an ellipsis leaves a word fragment rather than a word.
- `UiColor.selection` and `UiColor.selectionOpacity`: the accent at 35
  percent, behind the characters a reviewer has highlighted (11 section 4).
  `ink` on the composite clears 4.5:1 over every opaque surface in both modes,
  and the composite contrast gate gained the row.
- `UiStroke.caretRadius`: 1 dp, the caret's corner. Deliberately absent from
  `UiShape.strokes`, which is the map of widths the foundation gallery page
  walks.

### Primitives
- `Popover` fits the overlay it opens in (10 section 3; polish 3). A pane
  below or above its trigger hangs from the trigger's leading edge; where that
  would carry it past the overlay's trailing edge the anchor mirrors and the
  pane hangs from the trailing edge instead, and where neither edge holds it
  the pane is clamped inside the overlay's padding, the safe area plus
  `space.s4`, except that a pane may come as close to an edge as its own
  trigger does, so a select flush with the window keeps its list flush under
  it. Reason: slot A3 measured a record's account menu at 788 to 1036 of an
  800 dp window and had to move the menu off the bar, and `UiTopBar`'s
  overflow and `UiSelect` open through the same primitive. The vertical rule
  is unchanged. `start` and `end` now follow the reading direction, as their
  names say, and the fit is measured against the overlay the pane is drawn in
  rather than the media query's window, because the overlay is the only
  rectangle a pane can be drawn in: in the application the two are one, and a
  gallery frame with an `Overlay` of its own is measured against the frame.
- `primitives/label.dart` is new. `UiLabel` is the one line label of clause
  13: `maxLines: 1`, `softWrap: false`, an ellipsis, and the full text on the
  semantics label and in a tooltip only when the label actually overflows. The
  tooltip arrives as a slot rather than an import, because a drawn tooltip is
  a control and this is a primitive.
- `primitives/fit.dart` is new. `measureLabel` reports what one unbroken line
  needs at the current text scale, and `FitBuilder` draws the first declared
  variant that fits, or the last with a last resort flag.
- `primitives/edge_fade.dart` is new and exported. `EdgeFadedRow` is the
  compact variant 11 section 3.3 gives a tab strip and a navigation row: the
  row at its own intrinsic width inside a scroller, the edge faded on the side
  there is more, and the chosen item scrolled into view. Reason: `UiTabs` and
  `UiPillNav` both need it, a private class cannot cross two files in Dart,
  and two copies of one behaviour is what one vocabulary exists to prevent. It
  takes its fade extent as a token from the control, because a primitive makes
  no styling decision of its own.
- `ModalRoutes` and `Popover` publish the ambient text style around their
  panes from `context.ui`, so an overlay is correct in a host that resets the
  style below the tokens. `compactWindowMax` is `WindowClass.mediumMin` rather
  than a second copy of 600, and `isCompactWindow` reads the class.
- `FocusRing` takes a `FocusRingShape` (`superellipse`, `stadium`, `circle`)
  and the `capsule` flag is gone. Reason: a circular rounded rectangle around
  a superellipse meets the edge along a corner and parts from it at the ends,
  which the eye reads as a second outline. `capsule: true` becomes
  `shape: FocusRingShape.stadium`; the default is the superellipse every box
  in the product is drawn in. Call sites inside the package are updated.
- `FieldCore.showFocusRing` is gone, and the core draws no ring. Reason: the
  edge and the ring are one layer's job, and the core's ring was the second of
  the three edges a focused field drew.
- `FieldCore` builds its `TextField` with `decoration: null` rather than
  `InputDecoration.collapsed`. Reason: a collapsed decoration is still an
  `InputDecorator`, which reads the bridge `ThemeData`'s
  `InputDecorationTheme` and paints its enabled and focused borders under
  ours. There is now no decorator for it to paint through, and a test pumps
  every field both ways to hold that.
- `Pressable` takes `focusRing`, default true. Reason: a field shaped trigger
  draws a 40 dp edge inside a 48 dp hit box in pointer density, and the ring
  this primitive paints hugs the hit box. `UiSelect` passes false and rings
  its own edge, on the condition clause 4 already gives it.
- A disabled `Pressable` tells a pointer that arrives on it why it is
  disabled. `FocusableActionDetector` reports a hover only while it is enabled,
  which is right for the state layer and wrong for the reason, so the pointer
  is watched separately: `WidgetState.hovered` still means "hovered and able to
  respond", and `onDisabledReason` now fires on hover as well as on a tap and a
  long press. `UiIconButton`'s reason tooltip, which 10 section 4.1 says
  appears on hover, appeared only after the reviewer pressed a control that
  does nothing.
- A `Pressable` never hands its builder `hovered` and `disabled` at once. A
  control turned off under the pointer kept its hover until the detector
  cleared it a frame later, and a pair no style object has an answer for
  resolved by whichever of the two the resolver happened to test first. Both
  hover and press are cleared in the same pass that sets `disabled`.
- `FieldLayer` cross fades one sky into the next rather than cutting to it.
  `ui.motion.standard`, which is what the detail pane beside it cross fades at
  (04 section 4, row 17) and which the tokens return as zero under reduced
  motion, so the swap is instant there with no branch in the layer. The
  switcher does not animate its first child, so a screen opens with its own
  sky already painted. Reason: the application now paints `sky.work` on the
  record route and `sky.home` everywhere else, and a hard cut of the light
  behind the whole window reads as a flash.

### Actions
- `UiButtonRow` is new (`controls/actions/button_row.dart`, exported from the
  family barrel): a primary, an optional secondary and optional tertiary
  actions, ends aligned with the primary last, becoming a column with the
  primary on top when the line does not fit at the reviewer's text size or
  the window is compact. Reason: 11 section 3.4. It is the one widget in the
  package that reads `WindowClass`, because it is an arrangement rather than
  a control, and arrangement is what section 3.1 gives the window class to
  decide. Its actions are `UiButton`s rather than bare widgets, because it
  chooses between the two arrangements by measuring them.
- `UiButton.intrinsicWidth(context)`: the label at the current text scale
  plus the glyph slots and the padding, floored at the hit box. Reason:
  `UiButtonRow` decides on a measurement rather than a guess, and a pattern
  that arranges buttons itself needs the same number.
- `UiButtonStyle.resolve` takes a `TextScaler`, defaulting to
  `TextScaler.noScaling`, as `UiInputStyle.resolve` does and for the same
  reason (11 section 2.2). `UiButtonStyle.heightOf` takes the same argument
  as a named parameter, so an existing call site is unchanged at scale 1.0.
- `UiButtonStyle.restingHeightOf` and `UiButtonStyle.labelStyleOf` are new:
  the size table of 10 section 4 and the role a label is drawn in, published
  so that a control sized beside a button derives its own height from the
  same two values instead of restating them.
- `UiSegment.icon`, an optional `IconSpec`. Reason: the icon only rung of the
  ladder in 11 section 3.3 is available only when every segment carries one.
- `UiSegmented.label`, optional: what the track chooses. Reason: the select
  rung needs a name to offer the options under. A track without one keeps its
  segments at every width and ellipsises them, which is what a tab strip
  wants: `UiTabs` publishes `SemanticsRole.tabBar` with `explicitChildNodes`,
  and a select under that node is a child of a tab bar that is not a tab,
  which the SDK's own check fails rather than degrades.
- `UiSegmentedStyle.resolve` takes a `TextScaler` and the style gained
  `glyphSize`. `UiChipStyle.resolve` and `UiBadgeStyle.resolve` take one too,
  and `UiChipStyle` gained `leadingSize`; `UiKeyCapStyle.resolve` takes one.
  All default to `TextScaler.noScaling`.
- `UiChip.leading`, a `Widget?` drawn in an `inline` box before the label and
  mutually exclusive with `icon`. Reason: the slot 10 section 5 needs for
  `StatusChip`, whose measured form drew its own capsule around a determinate
  ring because no slot existed. The app's `_MeasuredChip` and its
  `TODO(fe/polish-2)` can be retired onto it.
- Every label in the family is a `UiLabel`: one line, an ellipsis, and the
  whole word on a tooltip and on the semantics label only when it actually
  overflows. Where the control is pressed, the tooltip wraps the control from
  outside its `Pressable`, so a tap reaches the control rather than the pane
  over it; where it is not (`UiBadge`, `UiKeyCap`), the label primitive's own
  tooltip slot carries it.
- `UiSegmented` declares the fit ladder of 11 section 3.3. Its intrinsic
  width is the count times the widest label measured at the current text
  scale plus a segment's padding, plus the track's insets, so every segment
  is equal at the widest label. Given less: icon only segments with a tooltip
  each when every segment carries a glyph, then a `UiSelect` over the same
  options with the same value and the same callback, then the segments with
  their words cut short. The `IntrinsicWidth` that used to size the track is
  gone; the width is declared rather than measured a second time by the
  framework, which is also what lets a label carry a `LayoutBuilder`.
- Collapsing a track into its select changes the form and not the value:
  nothing is reported, no selection moves, and what a screen reader meets is
  a control of a different kind under the same name carrying the same chosen
  option.
- `UiButton` and `UiChip` never shrink below their intrinsic width, and their
  heights derive from the roles they draw rather than from the density
  constant or from 32, so 200 percent text has room without a new number.
  `UiBadge` and `UiKeyCap` derive theirs the same way, from `label.small` and
  from `mono.identifier`.

### Inputs
- `UiInputStyle.resolve` takes a `TextScaler`. Reason: 11 section 2.2, a
  height that holds text is never a constant. Defaults to
  `TextScaler.noScaling`, so an existing call site keeps today's behaviour.
- `UiSelectStyle.resolve` takes the same `TextScaler`, for the same reason.
- `UiFieldBox` takes `semantics`, a wrapper around the box and never around
  the trailing action. Reason: a field merges its editor into one node whose
  rect is the 48 dp box, and the clear control has to stay outside that merge
  to keep its own words and its own target.
- The field's edge is `boundary` at `stroke.boundary` and never moves. Focus
  is the ring, drawn on the box's own shape, and a field shows it for any
  focus, pointer or keyboard (09 section 3.6, fit amendment).
- The box's height is `max(density.controlHeight, scaled line box + 2 * inset)`
  where the inset reproduces the density height at scale 1.0, so a field is
  unchanged at 1.0 and grows with the reviewer's text size above it.
- `FieldCore` draws the placeholder itself, in the text's own style and strut
  at `ink.tertiary`, on the line the value will take, excluded from semantics
  and transparent to the pointer. The caret is `ink`, `stroke.emphasis` wide,
  `caretRadius` at the ends and as tall as the scaled line box; the selection
  is `selection`, published through `DefaultSelectionStyle` so it holds inside
  a bare `WidgetsApp` as well as inside the application.
- Every role the core draws carries `TextLeadingDistribution.even`, so the
  text sits in the middle of its line box instead of floating above it. It is
  set locally until the foundation slot puts it on the type scale.
- `UiField` publishes one semantics node, whose rect is the 48 dp box and
  which carries the editor's flags, value and text editing actions. The
  labelled, Android and iOS tap target guidelines pass on a pumped field in
  both densities; before this they failed on the 22 dp node the editor
  published inside the control.
- `UiRadio` rings its 20 dp disc with a circle rather than the row with a
  rounded rectangle.

### Overlays
- `UiBanner` takes `actionLabel` and `onAction`. Reason: 07 section 11 asks
  every failure class to name its own recovery, and the band had a dismiss and
  a disclosure and nothing else. Wave 2's shell composed the action beside the
  strip and asked for this slot.
- `UiBannerStyle` gains `messageMin`, and the band's sentence now wraps to
  `UiBannerStyle.maxLines` when the detail is closed and to one line when it
  is open. Reason: 11 section 3.3 calls a band's text content, and the cap
  finding V-15 asks for is on the band rather than on the line. The band is
  still one line or two at every text scale. One application test moved with
  it, named in the closeout.
- `UiToastStyle` gains `messageMin`. Reason: the capsule's action moves under
  the message rather than either being squeezed, and the switch is measured
  against the width the message is left.
- `UiModalActions` takes `tertiary` and stacks with the primary on top when
  the row does not fit one line or the window is compact. Reason: this is
  `UiButtonRow` of 11 section 3.4 under the name the overlays family already
  had for it; slot G1 owns `controls/actions/` and lands the real class. Grep
  `fe/fit-actions` in `controls/overlays/sheet.dart` for the swap.
- `UiModalStyle.resolve` takes an optional `BuildContext` and the style gains
  `actionHeight`. Reason: 11 section 2.2, the action strip's height derives
  from the label role its buttons are set in. Without a context it reports the
  density height, which is that value at scale 1.0.
- `UiSheet` takes `scrollBody`, default true. Reason: the sheet now bounds its
  body and scrolls it; a caller whose body is already a scrollable passes
  false, because two scrollables in one column give the inner one an unbounded
  height again.
- `UiDisclosureStyle.summaryMaxLines` is 2 and the summary wraps. Reason: a
  disclosure's summary is the row's second line, the same object a list row's
  subtitle is, and is content rather than a label.
- The tooltip pane and the toast capsule publish the ambient text style the
  same way. No other change to either control.
- The sheet's padded block is `Flexible`, so the body is bounded by the window
  minus the chrome and scrolls inside it. A `Column` hands an inflexible child
  an unbounded main axis, which is why the inner `Flexible` had nothing to be
  flexible against and a filter sheet overflowed a phone by 1044 dp. The bound
  is the flex rather than arithmetic over the chrome, so it stays right
  whatever the safe area takes.
- `UiTabs` draws its track through `FitBuilder`: at its intrinsic width when
  that fits, and otherwise in a horizontal scroller whose edges fade on the
  side there is something to scroll to, with the chosen tab scrolled into
  view. The track inside is the same `UiSegmented` at the same size, so there
  is one thumb, one keyboard pattern and one set of tokens either way. The
  `tabBar` role sits inside the scroller rather than around it, because every
  child node of a tab bar has to carry `tab` and a `Scrollable`'s own node
  between the two would fail that check.
- Menu item labels and shortcuts, the menu trigger's label, the disclosure's
  title and the modal titles are `UiLabel`. Banner text, toast text, dialog
  and sheet bodies, the tooltip's sentence and the disclosure's summary stay
  wrapping `Text`: they are content.
- `UiModalActions` is a forwarder to `UiButtonRow`: the overlays keep their name for a row of actions and the actions family owns the arrangement. A modal without a primary leads with its way out. Its `style` parameter is gone; nothing outside the package passed it.
- `UiDisclosure`'s header keeps the 48 dp hit box of clause 2 in both
  densities. Reason: a header whose title fits one line was
  `density.rowHeight` tall, which is 44 in pointer, so every tap target
  guideline on a screen with a disclosure on it failed. The visual row keeps
  its density height and the difference is transparent slop inside the
  control's own box, so a column of disclosures still tiles without gaps.
- `UiDialog` takes `scrollBody`, defaulting to true, and `UiDialog.show` and
  `UiDialog.showAdaptive` forward it. Reason: `UiSheet` already had it, so a
  body written for `showAdaptive` had to know which of the two frames it landed
  in; and a dialog is bounded by the window it floats in, so a body that two
  sentences become three lines of at 200 percent text on a short window had
  nowhere to go. The application's filter form was carrying the difference as a
  height cap of its own.

### Navigation
- `UiTopBarAction` is new: a command with a glyph, a label, an optional
  shortcut and a callback, passed in `UiTopBar.actions`. Reason: the bar's
  compact variant is an overflow menu, and a menu needs a label, a glyph and a
  shortcut for every row it lists. A `Widget` carries none of those, so a bar
  given plain widgets keeps them all drawn. `actions` keeps its `List<Widget>`
  type, so no call site had to move; the application's own bar should adopt
  the class to gain the overflow (see the closeout).
- `UiTopBarStyle` gains `actionExtent`, `titleMin`, `heightIn`, `keptActions`
  and `overflowLabel`, and `height` is now the floor rather than the height.
  Reason: 11 section 2.2, a bar that holds one line of `type.title` derives
  its height from that line box; at scale 1.0 it is 56 or 48 exactly, as
  before.
- `UiTopBar` draws its title with an `Expanded` rather than a `Flexible`
  beside a `Spacer` when there is no `center`. Reason: a `Spacer` is a flex
  child, so the title was capped at half the bar and ellipsised at 200 percent
  text with the other half empty beside it. With a `center` the two still
  divide what the leading and the actions leave, which is 10 section 4.4's
  rule that the centre is centred in that space rather than in the window.
- `UiPillNav` scrolls when its discs do not fit, through `EdgeFadedRow`, with
  the current destination scrolled into view. Five discs need 240 dp and a
  disc's hit box never shrinks (clause 2), so at 200 dp the capsule overflowed
  by 56 dp; the gallery matrix counted that six times.
- The bar has three arrangements: every action drawn, the first two drawn with
  the rest in an overflow `UiPopoverMenu`, and every action in the menu for a
  column too narrow for two discs and a trigger. The menu carries the same
  labels, glyphs and shortcuts.
- `UiNavDestination` labels on a rail disc are `UiLabel`.
- `UiScaffoldExclusion` is new: a screen inside a scaffold asks for a
  rectangle to be kept clear with
  `UiScaffoldExclusion.of(context)?.publish(rect)`, and the frame clips its
  fields out of it. Reason: `UiScaffold.exclusion` is a constructor argument
  and the frame is built by the application's shell, which does not know where
  the photograph is, so the 24 dp clear band around a matte (09 section 2,
  principle 1) was unreachable from the pane that draws it. What the page asks
  for wins over what the caller passed, and `of` returns null outside a
  scaffold so a publisher is one call with no branch. Publishing is safe from
  a layout callback: a change reported while the frame is being built is
  announced after it.

### Data
- `UiRowTrailing` is new: the declared form of `UiListRow.trailing`, a glyph
  with a word beside it. Reason: the row's one compact variant is "trailing
  drops its label and keeps its glyph", which a row can only do to a trailing
  it can read. Anything else in the slot is drawn as given and the title
  wraps instead.
- `UiListRowStyle` gains `trailingLabel`, `trailingColor` and `titleMin`, and
  `UiListRow.contentMaxLines` is 2. Reason: 11 section 3.3 calls the row's
  title content and gives it two lines; the title used to be capped at one.
- `UiDataTileStyle.numeral` is now a getter over `numeralSteps`, the display
  roles the numeral steps down through. Reason: 11 section 3.3 has the tile
  step down one role at a time to `display.medium` and then scale. A caller
  reading `numeral` still gets the widest role.
- The tile's numeral never wraps. It steps down one display role at a time to
  `display.medium` and then scales the numeral and its unit together, because
  a `FittedBox` reports its child's unscaled baseline and a unit aligned to a
  scaled numeral's would float above the digits. The unit's role never
  changes. This amends the wave 1 reading of 02 section 4.14, which had no
  third option between clipping and a second line.
- The row's title and subtitle take two lines each and the trailing drops its
  word when the title would fall under `titleMin`.
- The avatar's initials and the arc indicator's absence and scale labels are
  `UiLabel`. The empty state's title and sentence stay content.
- `UiListRow` bounds a trailing it cannot measure (a chip, a switch, a time) to the room left once the title has its minimum, so no custom trailing can push the line over; a declared "trailing under the title" variant for compact windows is recorded for polish.
- `UiListRow`'s tone follows its state, as every other control's does.
  `UiListRowStyle.titleColor`, `subtitleColor` and `trailingColor` are
  `WidgetStateProperty<Color>`, and `bar` is one too; each resolves
  `disabled.content` for a row the server will not open. `title` and `subtitle`
  are now the type roles alone, with the colour resolved beside them, so there
  is one colour source per part rather than a resting colour baked into a role.
  Reason: a disabled row drew its title in full `ink` and its subtitle and
  trailing in `ink.secondary`, so the only thing saying the row was
  unavailable was the absence of a hover, which is nothing at all on a touch
  window.
- `UiRowTrailing` takes `color`, the colour the row resolved from its own
  states. Null keeps the resting colour out of the style, which is what a
  trailing built outside a row draws in.
- `UiListRow` gains the third variant 11 section 3.3 declares for it: the
  trailing moves under the title, on a line of its own at the start of the
  column, when the line cannot hold both. A `UiRowTrailing` reaches it after
  its word and its glyph rungs; a trailing the row cannot read (a chip, a
  switch, a time) has no glyph rung and goes there directly, at the point
  where the line would leave it less than `UiListRowStyle.trailingMin`, the hit
  box. It replaces the bound wave G's integration put on such a trailing, which
  at 200 dp was thirteen logical pixels of chip.
- `UiListRowStyle` gains `stackGap`, the space between the text and a trailing
  drawn under it, and `trailingMin`.
- A `UiListRow` with no `onPressed`, no `onLongPress` and no `disabledReason`
  publishes a plain node with the row's words, and no role, no focus and no
  state layer. Reason: it used to be a `Pressable` with nothing to do, so an
  upload row and a photograph that is not a record announced "disabled
  button", which promises a button a reviewer then cannot find, and the intake
  screens were wrapping such rows in `Semantics(excludeSemantics: true)` to
  silence it. A row the server forbids is the other case and keeps its
  `Pressable`: it is a control, it is off, and it owes the reviewer the
  reason.
- `UiDataTile` takes `surface`, a `UiDataTileSurface` of `glass` (the default,
  unchanged) or `paper`, which is the same shape and the same tokens on a
  solid pane with a hairline. Reason: `GlassSurface` asserts inside a sliver
  list item, because 09 section 3.3 forbids glass on repeated items, and three
  tiles in a list header spend the whole four pane glass budget on one row of
  chrome. A manifest's three counts are the product's own example and were a
  private `_CountTile` for want of this.

### Gallery
- The inputs gallery page gains the box in every shape at rest, focused and
  focused with a value, and the family golden is captured at 1180 by 1600.
- The actions gallery page gains the Fit block of 11 section 3.5: the
  segmented track named and glyphed, the same track unnamed, a button, an
  entered value chip and a `UiButtonRow`, each in a 480, 360, 280 and 200 dp
  column. The page's one focused specimen moved there, to the 200 dp button,
  because a page has one primary focus and the narrowest column is where a
  ring drawn outside a control would first meet something.
- The segmented section moved into the wider column of the page. The five
  segment track at `lg` needs 403 dp for its words and the narrow column is
  345, so the specimen was drawing its own last resort.
- The actions family golden is captured at 1180 by 2540, measured against a
  page that ends at 2492. It was 820 while the page ended at 1616, which
  10 section 6 already recorded as the one family taller than its window.
- The overlays gallery page states seven frosted panes rather than four, and
  the family golden window is 1180 by 1540. Both are the fit section: one
  toast capsule per column, four columns.
- The navigation gallery page's golden window is 1180 by 1220, measured
  against the page with its fit section.
- The data gallery page states eight frosted panes rather than four, and the
  family golden window is 1180 by 2280. The fit section spans the page rather
  than sitting in the measures column: a 480 dp specimen inside a 370 dp
  column is a specimen of 370 dp.
- `UiGallery` chooses its arrangement by window class, and is the first
  consumer of `Adaptive`. Below `medium` the page list is a `UiSelect` above
  the content and the content takes the whole window but its gutters; from
  `medium` up the 220 dp sidebar stays, pixel for pixel as before. Reason: a
  220 dp sidebar beside a 360 dp window leaves 130 dp for the page, which is
  the column the wrapping labels of 11 section 0 were first seen in. Keyboard
  navigation between pages works in both: the sidebar's rows are `Pressable`
  and the select answers `Enter`, `Down`, `Up` and `Escape`.
- The shell no longer publishes a `DefaultTextStyle` of its own. Reason:
  `UiTheme` publishes the product's ambient style (11 section 5), and a second
  publication of the same recipe is a second source for the one thing that
  document gives one source. Nothing moves: the styles were the same but for
  `decoration: none`, which the shell never set and never needed.
- `galleryPages` gains the Fit page, so `/gallery` carries twelve pages. It is
  listed beside `foundationPages` and `familyPages` rather than inside either,
  because it belongs to no family: it draws every family's controls. The
  foundation goldens still pin `foundationPages` and each family golden still
  renders its own page alone, so no existing gallery golden moves.
- The Fit page (`gallery/pages/fit_page.dart`) draws one section per row of the
  fit table in 11 section 3.3, in that order, each at 200, 280, 360 and 480 dp.
  Narrowest first: the four columns and their gutters come to 1380 dp, no
  window leaves a page that much, and the end worth losing is the wide one
  every family page already reviews. Each section states the compact variants
  the table gives that control, and draws it at rest above and focused below.
  A focused cell is the control under the `FocusRing` primitive on its own box,
  because one control on a page can hold primary focus and forty cannot; where
  the ring belongs to a member the control builds for itself, the section says
  where it lives rather than drawing a ring the product never draws. The page
  declares `maxGlassPanes: 13`, which is the top bar, the navigation row and
  the toast once per column plus the shell's own page list.
- `GalleryColumns` stacks a page's specimen columns below 320 dp per column, so the matrix pictures each control's own fit policy at 360 dp rather than the page's squeeze. `fitColumns` is one shared constant.
- Every "Needs human review" in the gallery is "Needs review", which is the
  chip label 02 section 4.13 specifies; the long form is the queue state's own
  name and stays in the token documentation, where it names which state a role
  and a glyph stand for.
- The data page's fit section notes the row's third variant at 200 dp, its
  tile section gains the paper surface, and the data family golden window is
  1180 by 2460 rather than 2280: the page needs 2458 with the taller 200 dp
  row and the new tile on it, and 2460 is the first height with nothing left
  to scroll. Measured, not guessed (10 section 6).
- The Fit page's `UiListRow` section names all three variants.

### Testing
- `expectControlContract` gains clauses 13, 14 and 15, each off by default so
  the families that shipped before 11 stay green: `labelsNeverWrap` (pumped at
  480, 360, 280 and 200 dp, with `wrappingContent` naming the strings that are
  content rather than labels), `geometryFromType` (pumped at 1.0, 1.3 and 2.0)
  and `fit`, a caller supplied `FitExpectation`. The harness also releases its
  semantics handle in a `finally`, so a contract that fails a clause reports
  that clause rather than a leaked handle.
- The harness no longer publishes a text style of its own. It used to, which
  is why nothing caught a route inheriting the framework fallback.
- `no_fallback_text_style` is new: every gallery page and every overlay those
  pages offer, pumped in a host that installs the fallback on purpose, with no
  paragraph allowed to carry its debug label or its double underline.
- Clauses 13, 14 and 15 are on in all fifteen contract tests of the three
  families, with the content strings named in `wrappingContent`. Two of them
  name a `UiButton` label there as well, because a button still wraps at 200
  dp and 11 section 3.3 gives it an ellipsis and a tooltip that slot G1 owns.
  Both entries carry the marker to delete.
- New behaviour tests: the bar's overflow at three widths and with opaque
  widgets; the strip scrolling, keeping every tab and revealing the chosen
  one; the band and the capsule moving their action under the words; the
  sheet's bounded scrolling body and a body that scrolls itself; the modal
  actions as a row, as a stack, and on a compact window; the tile's step down,
  its last resort and the hero chain.
- Clauses 13, 14 and 15 are on in every actions contract test.
Wave G of the front-end refactor, slot G3: section 3.5 of
`design/11-fit-and-scale.md`. The gallery shell gets a compact arrangement, a
Fit page shows every control of the fit table at four column widths, and the
golden matrix draws every page at four window classes by three text scales by
two modes.
- `test/gallery/matrix_golden_test.dart` is new, with 288 goldens under
  `test/gallery/goldens/matrix/`: every page of `galleryPages` at 360, 700,
  1000 and 1400 dp, at text scales 1.0, 1.3 and 2.0, in both modes, in pointer
  density with reduced motion on. Twenty four goldens per page, named
  `<page>_<class>_<scale>_<mode>.png`. Every window is a fixed 900 dp tall with
  the page scrolled to the top, because a height that held every specimen at
  scale 2.0 would be a hundred megabytes of binary nobody reviews, and because
  each page is already reviewed whole, at its own height, by its family golden.
  Each page is one test that captures its own twenty four, so the harness is
  paid for once: the whole matrix renders in about thirty seconds.
- The matrix carries `overflowBacklog`, a shrink-only record of what still
  overflows and where, by the file the report names. A control with no fit
  policy overflows in a 200 dp column, which is the defect the Fit page exists
  to picture, so the matrix records it rather than refusing to draw it. Five
  controls and two foundation pages are on the list; anything else, and
  anything that is not an overflow, fails.
- `test/gallery/gallery_shell_test.dart` is new: the arrangement at each side
  of the 600 dp boundary, the content taking the full width below it, the
  sidebar's start edge above it, and a page opened from the keyboard in both
  arrangements.
- The whole tree is formatted once with the pinned `dart format`, and the gate run checks formatting from here on.
- The package's goldens are compared on macOS only: `PlatformGatedGoldenComparator` in `test/flutter_test_config.dart` renders every golden on other platforms (so layout, overflow and semantics assertions still run) and sets the pixel comparison aside, and refuses `--update-goldens` off macOS, the rule the application's screen goldens already follow. Linux CI had failed all 336 of them by one to eleven percent of pixels.

## 0.2.0

2026-09-16. Wave 1 of the front-end refactor: the five control families of 10
section 4, the foundation and primitive changes each of them needed, and the
integration polish that swapped every cross-family stand-in for the real
control, fixed the test harness and reconciled 10 section 4 with what shipped.
Thirty controls, `flutter analyze --fatal-infos` clean, 519 package tests.

### Foundation
- `StateLayer` and `Pressable` take an optional state layer colour. The
  contract's `ink` is right over every light fill and invisible over an `ink`
  one, so a primary button had no visible hover or press at all. The opacity
  is unchanged; only which way the surface moves is now the control's to say.
  The actions slot and the inputs slot found it independently, and every
  family has at least one filled control that needs it.
- The light field geometry was measured at 390 by 844, 768 by 1024, 1180 by
  820 and 1440 by 900 and did not read as the washes 09 section 1 describes.
  The radius is now a fraction of the window's longer side rather than its
  shorter one, and the alpha falls on a Gaussian rather than
  `Curves.easeOutQuad`. Every centre colour, every centre alpha and
  `UiFields.matteExclusion` are unchanged, so the composite contrast
  measurements still hold. 09 section 3.2 carries the new rule and the
  numbers, and all 24 foundation gallery goldens moved, because the gallery
  shell paints `sky.home` behind every page.

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

### Actions
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
- The loading button's private `_LoadingArc` is now `UiProgress.ring` at
  16 dp, which is the replacement slot C1 marked it for. The four actions
  goldens do not move.

### Inputs
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

### Overlays
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

### Navigation
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

### Data
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

### Gallery
- The shell carries three page lists rather than one: `foundationPages`,
  `familyPages` and `galleryPages`, which is both, and it defaults to the
  third so a family page reaches `/gallery`. The foundation goldens draw the
  page list in their own sidebar, so one shared list would move all twenty
  four of them every time a family landed; `foundation_golden_test.dart` pins
  `foundationPages` instead, and those goldens hold byte for byte however many
  families register. The actions slot and the overlays slot reached the same
  three names independently, which is the signal that the shape was wrong
  rather than the use of it.
- Five family pages, each registered as one line in `familyPages`, each with
  four goldens in light and dark at both densities. A family golden is
  captured at the height its page needs rather than at one shared window, and
  10 section 6 carries the five heights.
- Two goldens that are not pages: the overlays window with the sheet open and
  with the dialog open, one per mode, at the standard 1180 by 820, because a
  sheet and a dialog are judged against the window they are drawn over rather
  than against the page behind them.

### Integration polish
- Every cross-family stand-in is now the real control, and the
  `no_stand_ins` gate keeps the next parallel wave from leaving one behind.
  `UiSelect`'s option rows and `UiSidebar`'s destinations are `UiListRow`;
  every pill disc, rail disc and icon button is wrapped in `UiTooltip`, with
  a disabled button drawing its reason through `UiTooltip.reason`; the
  default tab strip is a `UiSegmented` at `lg`; and `UiScaffold` installs a
  `UiToastHost` around its body, so `UiToasts.show` works from anywhere in
  any page with nothing at the call site.
- `UiListRow` gains a third mode, `tab`. A pane that publishes
  `SemanticsRole.tabBar` needs every child node to carry the tab role, which
  is what a sidebar's list of destinations is.
- `UiSegmented`'s `Shortcuts` is built with `includeSemantics: false`, so the
  control publishes no focusable node between itself and its segments.
- `UiToastHost`'s stack takes `StackFit.passthrough`, so a page under it is
  laid out against the constraints the host was handed.
- `UiTabs` no longer takes a `UiTabsStyle` or a per-tab glyph, and
  `UiTabsStyle` is gone with the private strip it styled. A segment is a
  label, a strip carries 2 to 5 tabs, and arrows move focus while `Enter`
  chooses. A caller that needs anything else passes it through the `strip`
  slot.
- `UiSelectStyle.optionLabel`, `UiSelectStyle.optionFill` and the four row
  members of `UiSidebarStyle` are deprecated and no longer read: the rows
  they painted are `UiListRow`, which resolves its own. They go in the next
  minor version.
- `uiHarness` publishes `MediaQuery`, `Density` and `UiTheme` above the
  application's navigator rather than inside `home`, so a route pushed in a
  package test renders in the mode, the density and the motion state the test
  asked for instead of the light fallback. The harness API is unchanged and
  no golden moved.
- The package carries a `.gitignore` for `test/gallery/failures/`, which
  `flutter test` writes on any golden mismatch.
- 10 sections 1.2, 2, 4, 6, 8 and 9 are reconciled with what shipped, and 09
  section 3.4 carries the accent's casing rule.

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
