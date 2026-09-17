/// The floating pill navigation (10 section 4.4, `UiPillNav`).
library;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/glass.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/edge_fade.dart';
import '../../primitives/fit.dart';
import '../../primitives/glass_surface.dart';
import 'nav_destination.dart';
import 'nav_disc.dart';
import 'nav_group.dart';

/// The resolved measurements of one pill (10 section 1.5).
@immutable
class UiPillNavStyle {
  /// Binds every token the pill draws with.
  const UiPillNavStyle({
    required this.discExtent,
    required this.discVisual,
    required this.padding,
    required this.gap,
    required this.currentFill,
    required this.glide,
    required this.curve,
  });

  /// The square one destination occupies inside the capsule.
  ///
  /// The hit box in both densities, which is the floor density never moves
  /// (09 section 6).
  final double discExtent;

  /// The diameter of the `ink` disc under the current destination.
  ///
  /// The visual height of a control at this density: 48 at touch, 40 at
  /// pointer, with the difference showing as transparent slop between discs.
  final double discVisual;

  /// The padding between the discs and the capsule's edge.
  ///
  /// Also what keeps the focus ring inside the capsule's clip: the ring is
  /// drawn a gap plus a stroke outside the disc's own box.
  final double padding;

  /// The space between the capsule and the bottom safe area.
  final double gap;

  /// The fill of the current destination's disc.
  final Color currentFill;

  /// How long the disc takes to glide, or zero under reduced motion.
  final Duration glide;

  /// The curve the disc glides on.
  final Curve curve;

  /// The capsule's own height.
  double get height => discExtent + padding * 2;

  /// What a scaffold pads the body by: the capsule plus the space under it.
  double get inset => height + gap;

  /// The style for [ui].
  static UiPillNavStyle resolve(UiThemeData ui) => UiPillNavStyle(
    discExtent: UiDensity.hitBox,
    discVisual: ui.density.controlHeight,
    padding: ui.space.s2,
    gap: ui.space.s4,
    currentFill: ui.color.ink,
    glide: ui.motion.navigationGlide,
    curve: MotionTokens.emphasizedCurve,
  );
}

/// The reference's floating row: a `glass.floating` capsule of discs, one per
/// destination, with an `ink` disc gliding to the current one.
///
/// Two to five destinations. The glyph is 24 in `regular`, and the current
/// destination is an `ink` disc with a `paper` glyph in `fill` weight. Labels
/// are not drawn: each disc carries its label in semantics and as a tooltip.
/// The capsule sits [UiPillNavStyle.gap] above the bottom safe area and the
/// body scrolls under it, padded by [insetOf].
///
/// Semantics: a tab list of tabs, one selected. `Left` and `Right` move
/// between them, mirrored under RTL; `Enter` and `Space` select.
///
/// Retires `NavigationBar`.
class UiPillNav extends StatelessWidget {
  /// A pill over [destinations], with [currentIndex] filled.
  const UiPillNav({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
  });

  /// The destinations, in order. Two to five (10 section 4.4).
  final List<UiNavDestination> destinations;

  /// Which destination the reviewer is on.
  final int currentIndex;

  /// Goes to the destination at the given index.
  ///
  /// Called for the current destination too. Whether tapping where you
  /// already are does nothing, or scrolls the body to the top, belongs to the
  /// screen rather than to the navigation.
  final ValueChanged<int> onSelect;

  /// The fewest destinations a pill may hold.
  ///
  /// One destination is not a navigation, it is a title.
  static const int minDestinations = 2;

  /// The most destinations a pill may hold.
  ///
  /// Past five the discs stop being distinguishable at a glance and the
  /// window has earned a rail (05 section 2).
  static const int maxDestinations = 5;

  /// The capsule's height in this context's density.
  static double heightOf(BuildContext context) =>
      UiPillNavStyle.resolve(context.ui).height;

  /// The space between the capsule and the bottom safe area.
  static double gapOf(BuildContext context) =>
      UiPillNavStyle.resolve(context.ui).gap;

  /// What a scaffold pads the body by so its last row clears the capsule.
  ///
  /// The height plus the gap, which is 10 section 4.4's "its height plus 16".
  static double insetOf(BuildContext context) =>
      UiPillNavStyle.resolve(context.ui).inset;

  @override
  Widget build(BuildContext context) {
    assert(
      destinations.length >= minDestinations &&
          destinations.length <= maxDestinations,
      'A pill holds $minDestinations to $maxDestinations destinations and was '
      'given ${destinations.length} (10 section 4.4). Wider windows get a '
      'rail or a sidebar instead of a longer pill.',
    );
    final UiThemeData ui = context.ui;
    final UiPillNavStyle style = UiPillNavStyle.resolve(ui);
    final int current = currentIndex.clamp(0, destinations.length - 1);

    return GlassSurface(
      level: GlassLevel.floating,
      capsule: true,
      padding: EdgeInsetsDirectional.all(style.padding),
      child: FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth: style.discExtent * destinations.length,
            builder: (BuildContext context, bool _) =>
                _discs(ui, style, current),
          ),
          // 11 section 3.3's compact variant for a navigation row. Five 48 dp
          // discs need 240 dp and a phone in a narrow pane does not always
          // have it; a disc's hit box is 48 at every density and every text
          // scale (clause 2), so what gives is the capsule, which scrolls.
          FitVariant(
            intrinsicWidth: 0,
            builder: (BuildContext context, bool _) => EdgeFadedRow(
              index: current,
              length: destinations.length,
              fadeExtent: ui.space.s6,
              child: _discs(ui, style, current),
            ),
          ),
        ],
      ),
    );
  }

  /// The discs, the glide behind them, and the node a screen reader reads
  /// them as.
  Widget _discs(UiThemeData ui, UiPillNavStyle style, int current) => NavGroup(
    length: destinations.length,
    axis: NavAxis.horizontal,
    builder: (BuildContext context, List<FocusNode> nodes) => Semantics(
      container: true,
      explicitChildNodes: true,
      role: SemanticsRole.tabBar,
      child: SizedBox(
        height: style.discExtent,
        width: style.discExtent * destinations.length,
        child: Stack(
          children: <Widget>[
            // Signature motion 1 (09 section 8): the disc slides from the
            // previous destination to the current one behind the glyphs,
            // at `medium` on the emphasized curve. Under reduced motion
            // the duration token is zero and the disc appears in place.
            AnimatedPositionedDirectional(
              start: style.discExtent * current,
              top: 0,
              width: style.discExtent,
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
            Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (int i = 0; i < destinations.length; i++)
                  NavDisc(
                    destination: destinations[i],
                    current: i == current,
                    extent: style.discExtent,
                    focusNode: nodes[i],
                    onPressed: () => onSelect(i),
                  ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}
