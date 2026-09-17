/// The badge (10 section 4.1, `UiBadge`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/color.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/label.dart';
import '../overlays/tooltip.dart';

/// The resolved paint of one badge.
@immutable
class UiBadgeStyle {
  /// Binds every token a badge draws with.
  const UiBadgeStyle({
    required this.background,
    required this.foreground,
    required this.label,
    required this.padding,
    required this.minHeight,
    required this.dotSize,
  });

  /// The capsule's fill.
  final Color background;

  /// The count's colour.
  final Color foreground;

  /// The count's type role, with tabular figures.
  final TextStyle label;

  /// The padding inside the capsule.
  final EdgeInsetsGeometry padding;

  /// The capsule's height, which is also its minimum width, so a single
  /// digit reads as a disc.
  ///
  /// Derived from the count's own role rather than declared (11 section 2.2),
  /// so a reviewer reading at 200 percent gets a badge that grew rather than a
  /// digit with its head cut off.
  final double minHeight;

  /// The dot form's diameter.
  final double dotSize;

  /// The style in [ui], tinted by [status] where the badge names one, at
  /// [textScaler].
  static UiBadgeStyle resolve(
    UiThemeData ui, {
    UiStatusTriple? status,
    TextScaler textScaler = TextScaler.noScaling,
  }) => UiBadgeStyle(
    background: status?.content ?? ui.color.ink,
    // `paper` in both modes, the inversion the primary button makes: the
    // fill follows the mode, so its text has to be the other end of the
    // pair or the badge disappears in one of them.
    foreground: ui.color.paper,
    label: ui.type.labelSmall.copyWith(
      // 09 section 4.2: every count in Geist is set with tabular figures,
      // so a changed digit is visible by position rather than by width.
      fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
    ),
    padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s2),
    minHeight: UiType.heightAroundAt(
      ui.space.s5,
      ui.type.labelSmall,
      textScaler,
    ),
    dotSize: ui.space.s2,
  );
}

/// A count, or a dot where the number would say nothing.
///
/// Retires `Badge`.
///
/// A badge is never the only carrier of its meaning: it sits beside the
/// control or the row it counts, and a screen reader reads [semanticsLabel]
/// rather than a bare number.
class UiBadge extends StatelessWidget {
  /// A badge reading [count].
  const UiBadge(this.count, {super.key, this.status, this.semanticsLabel});

  /// A badge with no number: something is here, and the count is not the
  /// point.
  ///
  /// [semanticsLabel] is required because the dot has no visible text
  /// (10 section 11).
  const UiBadge.dot({
    super.key,
    required String this.semanticsLabel,
    this.status,
  }) : count = null;

  /// How many. Null for the dot form.
  final int? count;

  /// The status triple this badge names, where it names one.
  final UiStatusTriple? status;

  /// What a screen reader reads. A complete phrase: "4 records waiting",
  /// never "4" (02 section 4.16).
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiBadgeStyle style = UiBadgeStyle.resolve(
      ui,
      status: status,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final Widget body = count == null
        ? SizedBox.square(
            dimension: style.dotSize,
            child: DecoratedBox(
              decoration: ShapeDecoration(
                shape: const StadiumBorder(),
                color: style.background,
              ),
            ),
          )
        : DecoratedBox(
            decoration: ShapeDecoration(
              shape: const StadiumBorder(),
              color: style.background,
            ),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minWidth: style.minHeight,
                minHeight: style.minHeight,
              ),
              child: Padding(
                padding: style.padding,
                child: Center(
                  widthFactor: 1,
                  heightFactor: 1,
                  // A badge is not pressed, so nothing beneath the tooltip
                  // competes for the tap and the primitive's own slot is the
                  // whole of rule 4 here (11 section 3.3).
                  child: UiLabel(
                    '$count',
                    style: style.label.copyWith(color: style.foreground),
                    tooltip:
                        (BuildContext context, String message, Widget label) =>
                            UiTooltip(message: message, child: label),
                  ),
                ),
              ),
            ),
          );
    if (semanticsLabel == null) return body;
    return Semantics(
      label: semanticsLabel,
      excludeSemantics: true,
      child: body,
    );
  }
}
