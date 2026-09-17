/// The glyph disc the pill and the rail are made of (10 section 4.4).
///
/// Internal to the navigation family: it is not exported from
/// `navigation.dart` and no screen names it. The pill and the rail draw the
/// same disc, and the only difference between them is whether the words sit
/// under the glyph.
///
/// The disc paints the glyph and nothing behind it. The `ink` disc that marks
/// the current destination belongs to the parent, because the parent is what
/// glides it from one destination to the next (09 section 8).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';
import 'nav_destination.dart';

/// One destination, drawn as a glyph in a square of [extent].
class NavDisc extends StatelessWidget {
  /// Draws [destination], filled when [current].
  const NavDisc({
    super.key,
    required this.destination,
    required this.current,
    required this.onPressed,
    required this.extent,
    this.focusNode,
    this.showLabel = false,
  });

  /// Which destination this is.
  final UiNavDestination destination;

  /// True for the destination the reviewer is on.
  final bool current;

  /// Goes to this destination.
  final VoidCallback onPressed;

  /// The square the glyph is centred in.
  ///
  /// The parent's gliding `ink` disc is centred in the same square, so this
  /// is what keeps the glyph on the disc rather than beside it.
  final double extent;

  /// The group's focus node for this destination.
  final FocusNode? focusNode;

  /// True to draw the destination's words under the glyph.
  ///
  /// The extended rail sets this. When it is false the words are still the
  /// control's semantics label and are drawn as a `UiTooltip` on hover and on
  /// long press, which is what makes an undrawn label reachable
  /// (10 section 4.4).
  final bool showLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;

    // The regular glyph is always painted. The fill glyph fades in over it as
    // the ink disc arrives, so the two forms swap while the disc travels
    // rather than popping when it lands. Painting the regular one underneath
    // costs nothing: by the time the fill form is opaque, the ink disc has
    // covered the ink glyph anyway. Colour and opacity may run alongside the
    // one authored move (04 section 5.2).
    final Widget glyph = SizedBox.square(
      dimension: extent,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          UiIcon(
            destination.icon,
            size: UiIconSize.action,
            color: ui.color.ink,
          ),
          AnimatedOpacity(
            opacity: current ? 1 : 0,
            duration: ui.motion.navigationGlide,
            curve: MotionTokens.standardCurve,
            child: UiIcon(
              destination.icon,
              size: UiIconSize.action,
              current: true,
              // `paper` on `ink` inverts with the mode, the way
              // `UiButton.primary` does, so the current disc reads as filled
              // in both columns of the token table.
              color: ui.color.paper,
            ),
          ),
        ],
      ),
    );

    Widget control = Pressable(
      semanticsLabel: destination.label,
      role: PressableRole.tab,
      selected: current,
      capsule: true,
      focusNode: focusNode,
      // The current destination sits on an `ink` disc, and `ink` at 12
      // percent over an `ink` fill is the same colour. Lifting toward `paper`
      // is what keeps hover and press visible on the one disc a reviewer
      // presses most. Every other disc sits on the sky and takes the default.
      stateLayerColour: current ? ui.color.paper : null,
      onPressed: onPressed,
      builder: (BuildContext context, Set<WidgetState> states) => showLabel
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                glyph,
                SizedBox(height: ui.space.s1),
                // One line, and normally not truncated either: the rail
                // measures the widest label at the live text scale and takes
                // its own width from it, so the words fit. `UiLabel` is what
                // makes that a promise of the system rather than of this one
                // call site (11 section 3.3, rule 1).
                UiLabel(
                  destination.label,
                  style: ui.type.labelSmall.copyWith(
                    color: current ? ui.color.ink : ui.color.inkSecondary,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            )
          : glyph,
    );

    if (!showLabel) {
      // A disc draws no words, so the label reaches a reviewer two ways at
      // once. `UiTooltip` draws it after a 400 ms hover and on a long press,
      // which is the pointer and touch answer; `Semantics(tooltip:)` carries
      // the same string to the platform, and `MergeSemantics` folds it into
      // the control's own node, so a screen reader reads one destination
      // rather than a tooltip and a tab.
      control = MergeSemantics(
        child: Semantics(
          tooltip: destination.label,
          child: UiTooltip(message: destination.label, child: control),
        ),
      );
    }
    return control;
  }
}
