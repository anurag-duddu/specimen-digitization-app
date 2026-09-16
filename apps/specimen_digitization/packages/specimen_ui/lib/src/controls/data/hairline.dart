/// The rule between two things (10 section 4.5, `UiHairline`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';

/// A 1 dp rule in the `hairline` role, inset aware.
///
/// Retires `Divider` and `VerticalDivider`.
///
/// `hairline` is decorative separation and measures under 3:1 on every
/// surface, which is what keeps it distinct from `boundary`, the role for an
/// edge a reviewer has to be able to find (09 section 3.1). An edge that
/// carries meaning is a `boundary` stroke on a `Surface`, never one of these.
///
/// Drawn outside the semantics tree: a rule says nothing a screen reader can
/// act on, and the structure it suggests is carried by the rows on either
/// side of it.
class UiHairline extends StatelessWidget {
  /// A rule across the writing direction, between two stacked items.
  ///
  /// [indent] insets the start edge and [endIndent] the end edge, both
  /// directional, so a rule that clears a leading thumbnail clears it under
  /// right to left as well.
  const UiHairline({super.key, this.indent, this.endIndent})
    : axis = Axis.horizontal;

  /// A rule along the writing direction, between two items side by side.
  ///
  /// [indent] insets the top and [endIndent] the bottom.
  const UiHairline.vertical({super.key, this.indent, this.endIndent})
    : axis = Axis.vertical;

  /// Which way the rule runs.
  final Axis axis;

  /// The inset at the leading end of the rule.
  final double? indent;

  /// The inset at the trailing end of the rule.
  final double? endIndent;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double thickness = ui.shape.stroke.hairline;
    final double start = indent ?? ui.space.s0;
    final double end = endIndent ?? ui.space.s0;
    final bool horizontal = axis == Axis.horizontal;
    return ExcludeSemantics(
      child: Padding(
        padding: horizontal
            ? EdgeInsetsDirectional.only(start: start, end: end)
            : EdgeInsets.only(top: start, bottom: end),
        child: SizedBox(
          height: horizontal ? thickness : null,
          width: horizontal ? null : thickness,
          child: ColoredBox(
            color: ui.color.hairline,
            // A box with no child takes the smallest size its constraints
            // allow, so the rule has to ask for the whole of its other axis.
            // `LimitedBox` keeps that from throwing where the parent is
            // unbounded, which is what `Container` does for the same reason.
            child: const LimitedBox(
              maxWidth: 0,
              maxHeight: 0,
              child: SizedBox.expand(),
            ),
          ),
        ),
      ),
    );
  }
}
