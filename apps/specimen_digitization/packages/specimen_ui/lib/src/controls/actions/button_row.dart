/// The one arrangement every screen needs (11 section 3.4, `UiButtonRow`).
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/window.dart';
import '../../primitives/fit.dart';
import 'button.dart';

/// A row of actions: primary last, ends aligned, stacking when it has to.
///
/// `UiDialog` and `UiSheet` use it for their actions and patterns use it for
/// form footers, so no screen writes its own `Row` of buttons and no two
/// screens disagree about which end the primary sits at.
///
/// The row becomes a column with the primary on top when it does not fit in
/// one line at the reviewer's text size, or when the window is compact. Both
/// arrangements read in the order they are drawn, so `Tab` follows the screen:
/// left to right in the row, which puts the primary last, and top to bottom in
/// the column, which puts it first. Nothing is reordered behind the reviewer's
/// back; the two orders are what a row and a column respectively read as.
///
/// The actions are [UiButton]s rather than bare widgets because this decides
/// between two arrangements by measuring them, and a button is the one thing
/// in the system that can say how wide it needs to be
/// ([UiButton.intrinsicWidth]). A screen with something else to put in a
/// footer composes it beside this rather than through it.
class UiButtonRow extends StatelessWidget {
  /// A row whose primary action is [primary].
  const UiButtonRow({
    super.key,
    required this.primary,
    this.secondary,
    this.tertiary = const <UiButton>[],
  });

  /// The action the screen exists to offer. Drawn last in a row and first in
  /// a column, and the only one a reviewer should have to find.
  final UiButton primary;

  /// The way out, or the second choice: "Cancel", "Save a draft".
  final UiButton? secondary;

  /// Anything else, in reading order, drawn before [secondary].
  final List<UiButton> tertiary;

  /// The actions in the order a row reads them, primary last.
  List<UiButton> get _rowOrder => <UiButton>[...tertiary, ?secondary, primary];

  /// The actions in the order a column reads them, primary first.
  List<UiButton> get _columnOrder => <UiButton>[
    primary,
    ?secondary,
    ...tertiary,
  ];

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double gap = ui.space.s2;
    final List<UiButton> row = _rowOrder;
    final List<double> widths = <double>[
      for (final UiButton action in row) action.intrinsicWidth(context),
    ];
    final double inOneLine =
        widths.fold<double>(0, (double sum, double w) => sum + w) +
        gap * (row.length - 1);
    final double widest = widths.fold<double>(0, math.max);
    // The one place in the package a widget reads the window class, and 11
    // section 3.4 is what puts it here: this is an arrangement rather than a
    // control, and arrangement is exactly what section 3.1 gives the window
    // class to decide. A compact window stacks whatever the arithmetic says,
    // because a phone sized window has a screen's worth of other things
    // beside a row of actions and the row is what gives way.
    final bool compact = WindowClass.of(context).isCompact;
    return FitBuilder(
      variants: <FitVariant>[
        if (!compact)
          FitVariant(
            intrinsicWidth: inOneLine,
            builder: (BuildContext context, bool _) => _line(row, gap),
          ),
        FitVariant(
          intrinsicWidth: widest,
          builder: (BuildContext context, bool _) => _stack(_columnOrder, gap),
        ),
      ],
    );
  }

  /// One line, ends aligned.
  ///
  /// `Align` rather than a row that fills the width, so the arrangement is
  /// still correct where nobody has bounded it: a flex that stretches to an
  /// unbounded width has nothing to align against.
  Widget _line(List<UiButton> actions, double gap) => Align(
    alignment: AlignmentDirectional.centerEnd,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int i = 0; i < actions.length; i++) ...<Widget>[
          if (i > 0) SizedBox(width: gap),
          actions[i],
        ],
      ],
    ),
  );

  /// A column, primary on top, each action on the column's centre line.
  ///
  /// Centred rather than stretched: a `UiButton` is the reference's disc
  /// (09 section 1), and a capsule pulled to the full width of a phone stops
  /// reading as one. Centred rather than ends aligned, which is what the line
  /// does: a column of actions has no line of type to run back to, and a
  /// stack pushed against one edge reads as something left over rather than
  /// as the choice the window came down to.
  Widget _stack(List<UiButton> actions, double gap) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.center,
    children: <Widget>[
      for (int i = 0; i < actions.length; i++) ...<Widget>[
        if (i > 0) SizedBox(height: gap),
        actions[i],
      ],
    ],
  );
}
