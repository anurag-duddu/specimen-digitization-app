/// The navigation rail (10 section 4.4, `UiRail`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import 'nav_destination.dart';
import 'nav_disc.dart';
import 'nav_group.dart';

/// The resolved measurements of one rail (10 section 1.5).
///
/// The rail is the one control in the family whose width is measured rather
/// than fixed. Its collapsed form is a column of the pill's discs and is
/// always [minWidth]; its extended form draws the words under each glyph, and
/// a rail that kept 72 dp at 200 percent text would either clip them or wrap
/// a single word it cannot break. [resolve] measures the widest label at the
/// live text scale and widens the column to hold it, which is clause 7 of the
/// control contract applied to a vertical control: heights grow, widths grow
/// with them.
@immutable
class UiRailStyle {
  /// Binds every token the rail draws with.
  const UiRailStyle({
    required this.width,
    required this.discExtent,
    required this.discVisual,
    required this.itemExtent,
    required this.padding,
    required this.currentFill,
    required this.glide,
    required this.curve,
  });

  /// The column's width: [minWidth], or wider when a label needs it.
  final double width;

  /// The square one glyph is centred in, at the top of its destination.
  final double discExtent;

  /// The diameter of the `ink` disc under the current destination.
  final double discVisual;

  /// The height of one destination: [discExtent], plus the words when the
  /// rail is extended.
  final double itemExtent;

  /// The padding between a label and the column's edge.
  final double padding;

  /// The fill of the current destination's disc.
  final Color currentFill;

  /// How long the disc takes to glide, or zero under reduced motion.
  final Duration glide;

  /// The curve the disc glides on.
  final Curve curve;

  /// The 72 dp column of 10 section 4.4.
  ///
  /// Composed from the tokens rather than written as a number: a 48 dp hit
  /// box with 12 dp of gutter on each side. `space.rail` is the v1 rail at 80
  /// and still belongs to the screens that have not moved yet.
  static double minWidthOf(UiThemeData ui) => ui.space.targetMin + ui.space.s6;

  /// The style for [ui], measured for [destinations].
  ///
  /// [textScaler] and [textDirection] come from the context because the
  /// measurement has to be the one the labels will actually be laid out with.
  static UiRailStyle resolve(
    UiThemeData ui, {
    required bool extended,
    required List<UiNavDestination> destinations,
    required TextScaler textScaler,
    required TextDirection textDirection,
  }) {
    final double padding = ui.space.s2;
    final double minWidth = minWidthOf(ui);
    double widest = 0;
    double lineHeight = 0;
    if (extended) {
      final TextStyle label = ui.type.labelSmall;
      for (final UiNavDestination destination in destinations) {
        final TextPainter painter = TextPainter(
          text: TextSpan(text: destination.label, style: label),
          textDirection: textDirection,
          textScaler: textScaler,
          maxLines: 1,
        )..layout();
        widest = math.max(widest, painter.width);
        lineHeight = math.max(lineHeight, painter.height);
        painter.dispose();
      }
    }
    return UiRailStyle(
      width: extended ? math.max(minWidth, widest + padding * 2) : minWidth,
      discExtent: UiDensity.hitBox,
      discVisual: ui.density.controlHeight,
      itemExtent: UiDensity.hitBox + (extended ? ui.space.s1 + lineHeight : 0),
      padding: padding,
      currentFill: ui.color.ink,
      glide: ui.motion.navigationGlide,
      curve: MotionTokens.emphasizedCurve,
    );
  }
}

/// A column of the pill's discs for a medium window, top aligned under the
/// mark.
///
/// The collapsed form is glyphs only; [extended] draws each destination's
/// words under its glyph in `label.small`. The `ink` disc glides between
/// destinations exactly as it does in the pill (09 section 8).
///
/// The rail carries no glass. 10 section 4.4 gives the sidebar `glass.flat`
/// and gives the rail nothing, and a column of discs reads as the reference's
/// floating navigation without a pane around it. That also leaves the window's
/// four pane budget for the top bar, the action bar and whatever the body
/// holds (09 section 3.3).
///
/// Semantics: a tab list of tabs, one selected. `Up` and `Down` move between
/// them; `Enter` and `Space` select.
///
/// Retires `NavigationRail`.
class UiRail extends StatelessWidget {
  /// A rail over [destinations], with [currentIndex] filled.
  const UiRail({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
    this.leading,
    this.extended = false,
  });

  /// The destinations, in order.
  final List<UiNavDestination> destinations;

  /// Which destination the reviewer is on.
  final int currentIndex;

  /// Goes to the destination at the given index.
  final ValueChanged<int> onSelect;

  /// What sits above the destinations. The mark, on every screen that has
  /// one.
  final Widget? leading;

  /// True to draw each destination's words under its glyph.
  ///
  /// 05 section 2 gives the collapsed form to medium windows and the extended
  /// form to expanded ones. The rail does not decide that for itself: the
  /// window class does, and the shell reads it.
  final bool extended;

  /// The fewest destinations a rail may hold.
  ///
  /// The same floor as the pill: one destination is a title, not a
  /// navigation. There is no ceiling, because a column has room a capsule
  /// does not.
  static const int minDestinations = 2;

  @override
  Widget build(BuildContext context) {
    assert(
      destinations.length >= minDestinations,
      'A rail holds at least $minDestinations destinations and was given '
      '${destinations.length}. One destination is a title, not a navigation.',
    );
    final UiThemeData ui = context.ui;
    final UiRailStyle style = UiRailStyle.resolve(
      ui,
      extended: extended,
      destinations: destinations,
      textScaler: MediaQuery.textScalerOf(context),
      textDirection: Directionality.of(context),
    );
    final int current = currentIndex.clamp(0, destinations.length - 1);

    return SizedBox(
      width: style.width,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (leading != null)
            Padding(
              padding: EdgeInsetsDirectional.fromSTEB(
                0,
                ui.space.s4,
                0,
                ui.space.s6,
              ),
              child: leading,
            ),
          NavGroup(
            length: destinations.length,
            axis: NavAxis.vertical,
            builder: (BuildContext context, List<FocusNode> nodes) => Semantics(
              container: true,
              explicitChildNodes: true,
              role: SemanticsRole.tabBar,
              child: SizedBox(
                height: style.itemExtent * destinations.length,
                child: Stack(
                  children: <Widget>[
                    // Signature motion 1 (09 section 8), running down the
                    // column instead of along the capsule. Start and end are
                    // both pinned so the disc stays centred in the column at
                    // any width, in either direction.
                    AnimatedPositionedDirectional(
                      top: style.itemExtent * current,
                      start: 0,
                      end: 0,
                      height: style.discExtent,
                      duration: style.glide,
                      curve: style.curve,
                      child: Center(
                        child: SizedBox.square(
                          dimension: style.discVisual,
                          child: DecoratedBox(
                            decoration: ShapeDecoration(
                              shape: const StadiumBorder(),
                              color: style.currentFill,
                            ),
                          ),
                        ),
                      ),
                    ),
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        for (int i = 0; i < destinations.length; i++)
                          NavDisc(
                            destination: destinations[i],
                            current: i == current,
                            extent: style.discExtent,
                            showLabel: extended,
                            focusNode: nodes[i],
                            onPressed: () => onSelect(i),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
