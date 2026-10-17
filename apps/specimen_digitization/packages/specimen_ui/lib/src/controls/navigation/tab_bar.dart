/// The brand bottom tab bar (10 section 4.4, `UiTabBar`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import 'nav_destination.dart';
import 'nav_group.dart';

/// The resolved measurements of one tab bar (10 section 1.5).
///
/// Every number the bar draws with is named here, so the metric the owner
/// signed off on at normal text, the iPhone bar of 2026-10-16 (56 dp of
/// content), is a documented property of the component rather than literals
/// in a shell. The bar is the same on every platform: the only thing that
/// varies with the device is the system inset under it (05 section 5), and
/// that is read at build time, never here.
///
/// Amended 2026-10-17: the height that grows with the text is
/// `glyphBand + scaled labelAllowance + labelGap`. The first version left
/// [labelGap] out, so the 4 dp the cell pads under its label came out of the
/// glyph's air and at 200 percent text the glyph sat about 3 dp under the top
/// line. Normal text is unchanged at 56 dp, because the resting height
/// governs there; 200 percent is 68 dp.
@immutable
class UiTabBarStyle {
  /// Binds every token the bar draws with.
  const UiTabBarStyle({
    required this.ground,
    required this.hairline,
    required this.current,
    required this.rest,
    required this.label,
    required this.restingHeight,
    required this.glyphBand,
    required this.labelAllowance,
    required this.labelGap,
    required this.glyphSize,
    required this.crossFade,
    required this.curve,
  });

  /// The bar's ground. Solid `paper`: no glass, no tint, no elevation.
  final Color ground;

  /// The colour of the one physical pixel line along the top edge.
  ///
  /// `boundary` rather than `hairline`: 09 section 3.1 keeps `hairline` for
  /// decoration and gives `boundary` the edges a reviewer must be able to
  /// find, and the bar's top edge is where the content stops.
  final Color hairline;

  /// The glyph and the label of the current destination: `ink`.
  final Color current;

  /// The glyph and the label of every other destination: `ink.secondary`.
  final Color rest;

  /// The label role: `label.small`, sentence case, one line.
  final TextStyle label;

  /// The least the bar's content may be tall, before the safe inset:
  /// `space.tabBar`, 56 dp (03 section 5.2, `size.tabbar`).
  ///
  /// The HIG tab bar is 49 pt and grows with Dynamic Type; Material asks for a
  /// 48 dp target and WCAG 2.2 SC 2.5.8 asks for 24 CSS px. 56 is the first
  /// number on the 8 dp grid that holds a 24 dp glyph, a one line label and a
  /// 4 dp gap without crowding any of them, and it is the height the iPhone
  /// bar had when the owner called it "perfect".
  final double restingHeight;

  /// What the bar spends on the glyph before the label's own line: the 24 dp
  /// glyph plus one 8 dp step of air, 32 dp. The air is 4 dp above the glyph
  /// and 4 dp below it, and it holds at every text scale because the height
  /// formula adds it to the label rather than competing with it.
  final double glyphBand;

  /// What the label's line is allowed at scale 1.0: 16 dp, the line a
  /// `label.small` label sits in beside a 16 dp glyph (09 section 7).
  ///
  /// Scaled with the reviewer's text size, so at 200 percent the bar is
  /// `32 + 32 + 4 = 68` dp tall and the label never touches the glyph.
  final double labelAllowance;

  /// The air under the label and above the bar's inset: 4 dp, `space.s1`,
  /// which is also what the stock iOS bar leaves. It is part of the height
  /// that grows with the text, so the glyph keeps its own air (see
  /// [contentHeightOf]).
  final double labelGap;

  /// The glyph's square: 24 dp, the navigation size of 09 section 7.
  final double glyphSize;

  /// How long the fill and the colour take to cross-fade when the current
  /// destination changes, or zero under reduced motion (09 section 8).
  final Duration crossFade;

  /// The curve of that cross-fade.
  final Curve curve;

  /// The bar's content height at [textScaler], excluding the safe inset.
  ///
  /// `max(restingHeight, glyphBand + textScaler.scale(labelAllowance) +
  /// labelGap)`: it grows with the label rather than clipping it (10 section
  /// 2 clause 14), and the 4 dp the cell pads under the label is counted, so
  /// the glyph keeps the 8 dp of air [glyphBand] promises at every scale.
  /// That is 56 dp at normal text and 68 dp at 200 percent.
  double contentHeightOf(TextScaler textScaler) => math.max(
    restingHeight,
    glyphBand + textScaler.scale(labelAllowance) + labelGap,
  );

  /// The width of the top line for a window drawn at [devicePixelRatio]: one
  /// physical pixel, which is thinner than a logical one on every phone.
  static double hairlineWidthOf(double devicePixelRatio) =>
      1 / devicePixelRatio;

  /// The style for [ui].
  static UiTabBarStyle resolve(UiThemeData ui) => UiTabBarStyle(
    ground: ui.color.paper,
    hairline: ui.color.boundary,
    current: ui.color.ink,
    rest: ui.color.inkSecondary,
    label: ui.type.labelSmall,
    restingHeight: ui.space.tabBar,
    glyphBand: ui.space.iconAction + ui.space.s2,
    labelAllowance: ui.space.iconSmall,
    labelGap: ui.space.s1,
    glyphSize: UiIconSize.action.dimension,
    crossFade: ui.motion.navigationGlide,
    curve: MotionTokens.standardCurve,
  );
}

/// The one bottom tab bar, drawn the same on every platform.
///
/// A docked, full width bar flush to the bottom edge: a solid `paper` ground
/// with a one physical pixel `boundary` line along its top, and below its
/// content the system inset (the home indicator on an iPhone, the gesture or
/// three button bar on Android) with the same ground extending under it.
/// There is no pill, no indicator, no elevation, no tint and no glass.
///
/// Each of two to five destinations is an equal cell and the whole cell is
/// the hit target. A cell stacks the destination's glyph over its label,
/// which is always drawn: the glyph is `regular` and `ink.secondary`, and the
/// current destination is `fill` and `ink`, cross-fading over the navigation
/// motion token (09 section 8). Labels are `label.small`, sentence case, one
/// line, and the bar grows with the reviewer's text size.
///
/// Semantics: a tab list of tabs, one selected, each labelled with its
/// destination. `Left` and `Right` move focus between tabs, mirrored under
/// RTL; `Enter` and `Space` select; focus is ringed inside the cell so a ring
/// never leaves a bar that touches the screen's edges.
///
/// Why this exists, and why it is not a stock widget: 09 section 2 principle 5
/// says behaviour adapts and identity does not, and a bar that was
/// `CupertinoTabBar` on an iPhone and `NavigationBar` on a Pixel was two
/// products' identities in one app. The owner, in a Claude Code session on
/// 2026-10-17: "btw ios nav behaves perfectly but android has too much
/// padding/space"; "are you sure it is following desired guidelines given
/// flutter we are cross-platform and brand focsed less native focused but
/// still tream guidelines seriously not copy". The target is therefore the
/// iPhone's proportions, rebuilt as our own anatomy.
///
/// [UiPillNav] stays in the library for a window that wants a floating
/// capsule; compact phones use this bar (10 section 4.4).
class UiTabBar extends StatelessWidget {
  /// A bar over [destinations], with [currentIndex] filled.
  const UiTabBar({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
    this.iconKeyOf,
  });

  /// The destinations, in order. Two to five.
  final List<UiNavDestination> destinations;

  /// Which destination the reviewer is on.
  final int currentIndex;

  /// Goes to the destination at the given index.
  ///
  /// Called for the current destination too: what tapping where you already
  /// are does belongs to the screen, not to the navigation.
  final ValueChanged<int> onSelect;

  /// A key for the glyph of the destination at an index, or null for none.
  ///
  /// The shell uses it so a test and an integration selector can find the
  /// glyph, and measure it, without the bar knowing anything about either.
  final Key? Function(int index)? iconKeyOf;

  /// The fewest destinations a bar may hold.
  ///
  /// One destination is not a navigation, it is a title.
  static const int minDestinations = 2;

  /// The most destinations a bar may hold.
  ///
  /// Past five a cell on a 320 dp phone is narrower than its own label at
  /// default text size, and the window has earned a rail (05 section 2).
  static const int maxDestinations = 5;

  /// The bar's content height in this context, excluding the safe inset.
  static double contentHeightOf(BuildContext context) => UiTabBarStyle.resolve(
    context.ui,
  ).contentHeightOf(MediaQuery.textScalerOf(context));

  /// The bar's whole height in this context: its content plus the system
  /// inset under it, which is what the bar actually occupies.
  static double heightOf(BuildContext context) =>
      contentHeightOf(context) + MediaQuery.viewPaddingOf(context).bottom;

  @override
  Widget build(BuildContext context) {
    assert(
      destinations.length >= minDestinations &&
          destinations.length <= maxDestinations,
      'A tab bar holds $minDestinations to $maxDestinations destinations and '
      'was given ${destinations.length} (10 section 4.4). Wider windows get '
      'a rail or a sidebar instead of a longer bar.',
    );
    final UiThemeData ui = context.ui;
    final UiTabBarStyle style = UiTabBarStyle.resolve(ui);
    final int current = currentIndex.clamp(0, destinations.length - 1);
    final double content = style.contentHeightOf(
      MediaQuery.textScalerOf(context),
    );
    // `viewPadding`, not `padding`: a shell that has consumed the bottom
    // padding for the body above the bar has not made the home indicator go
    // away, and the bar is what sits over it (the stock iOS bar reads the
    // same property).
    final double inset = MediaQuery.viewPaddingOf(context).bottom;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: style.ground,
        border: Border(
          top: BorderSide(
            color: style.hairline,
            width: UiTabBarStyle.hairlineWidthOf(
              MediaQuery.devicePixelRatioOf(context),
            ),
          ),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.only(bottom: inset),
        child: SizedBox(
          width: double.infinity,
          height: content,
          child: NavGroup(
            length: destinations.length,
            axis: NavAxis.horizontal,
            builder: (BuildContext context, List<FocusNode> nodes) => Semantics(
              container: true,
              explicitChildNodes: true,
              role: SemanticsRole.tabBar,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  for (int i = 0; i < destinations.length; i++)
                    Expanded(
                      child: _TabCell(
                        destination: destinations[i],
                        style: style,
                        ui: ui,
                        current: i == current,
                        focusNode: nodes[i],
                        iconKey: iconKeyOf?.call(i),
                        onPressed: () => onSelect(i),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One destination: its glyph over its label, in a cell that is all hit box.
///
/// The layout is the stock iOS bar's, rebuilt: a column ending 4 dp above the
/// bar's inset, the glyph centred in whatever height the label leaves, the
/// label under it.
class _TabCell extends StatelessWidget {
  const _TabCell({
    required this.destination,
    required this.style,
    required this.ui,
    required this.current,
    required this.focusNode,
    required this.onPressed,
    this.iconKey,
  });

  final UiNavDestination destination;
  final UiTabBarStyle style;
  final UiThemeData ui;
  final bool current;
  final FocusNode focusNode;
  final VoidCallback onPressed;
  final Key? iconKey;

  @override
  Widget build(BuildContext context) {
    // The two weights of one glyph cross-fade rather than swap: the `regular`
    // form fades out and the `fill` form fades in over the navigation token,
    // each already in its own colour, so no frame draws a half-filled glyph
    // in a colour that is neither. Under reduced motion the token is zero and
    // the change is one frame.
    final Widget glyph = SizedBox.square(
      key: iconKey,
      dimension: style.glyphSize,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          AnimatedOpacity(
            opacity: current ? 0 : 1,
            duration: style.crossFade,
            curve: style.curve,
            child: UiIcon(
              destination.icon,
              size: UiIconSize.action,
              color: style.rest,
            ),
          ),
          AnimatedOpacity(
            opacity: current ? 1 : 0,
            duration: style.crossFade,
            curve: style.curve,
            child: UiIcon(
              destination.icon,
              size: UiIconSize.action,
              current: true,
              color: style.current,
            ),
          ),
        ],
      ),
    );

    return Pressable(
      semanticsLabel: destination.label,
      role: PressableRole.tab,
      selected: current,
      focusNode: focusNode,
      onPressed: onPressed,
      radius: ui.shape.inner,
      // The cell touches its neighbours and the screen's edges, so the ring
      // is drawn inside it; outside paint would be cut by the next cell.
      insetFocusRing: true,
      builder: (BuildContext context, Set<WidgetState> states) =>
          SizedBox.expand(
            child: Padding(
              padding: EdgeInsetsDirectional.only(bottom: style.labelGap),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.end,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Expanded(child: Center(child: glyph)),
                  AnimatedDefaultTextStyle(
                    style: style.label.copyWith(
                      color: current ? style.current : style.rest,
                    ),
                    duration: style.crossFade,
                    curve: style.curve,
                    child: UiLabel(
                      destination.label,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          ),
    );
  }
}
