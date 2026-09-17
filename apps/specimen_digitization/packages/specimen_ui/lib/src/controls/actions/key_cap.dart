/// The key cap (10 section 4.1, `UiKeyCap`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/label.dart';
import '../../primitives/squircle.dart';
import '../overlays/tooltip.dart';

/// The resolved paint of one key cap.
@immutable
class UiKeyCapStyle {
  /// Binds every token a key cap draws with.
  const UiKeyCapStyle({
    required this.background,
    required this.foreground,
    required this.side,
    required this.label,
    required this.radius,
    required this.padding,
    required this.minSize,
  });

  /// The cap's fill.
  final Color background;

  /// The key name's colour.
  final Color foreground;

  /// The cap's edge. A key cap is an edge a reviewer must be able to find, so
  /// it is `boundary` rather than `hairline`.
  final BorderSide side;

  /// The key name's type role: monospace, so `I` and `l` are distinct on a
  /// cap the width of one character.
  final TextStyle label;

  /// The cap's corner.
  final double radius;

  /// The padding inside the cap.
  final EdgeInsetsGeometry padding;

  /// The cap's height, and its minimum width, so a one-character cap is
  /// square rather than a sliver.
  ///
  /// Derived from the monospace role the cap is set in (11 section 2.2), so a
  /// cap grows with the reviewer's text size instead of clipping the key it
  /// names.
  final double minSize;

  /// The style in [ui], at [textScaler].
  static UiKeyCapStyle resolve(
    UiThemeData ui, {
    TextScaler textScaler = TextScaler.noScaling,
  }) => UiKeyCapStyle(
    background: ui.color.paper,
    foreground: ui.color.inkSecondary,
    side: BorderSide(color: ui.color.boundary, width: ui.shape.stroke.boundary),
    label: ui.type.mono.identifier,
    radius: ui.shape.inner,
    padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s2),
    minSize: UiType.heightAroundAt(
      ui.space.s6,
      ui.type.mono.identifier,
      textScaler,
    ),
  );
}

/// One key, drawn the way a keyboard draws it.
///
/// Carried from the v1 key cap pattern. A key cap is a picture of a key, not
/// a control: it is never pressed, so it has no states and no hit box of its
/// own. `UiPopoverMenu` puts one at the end of a row and the shortcut map is
/// a table of them.
class UiKeyCap extends StatelessWidget {
  /// A cap reading [label].
  const UiKeyCap({super.key, required this.label, this.semanticsLabel});

  /// What is printed on the key: `J`, `Esc`, `/`.
  final String label;

  /// What a screen reader reads instead, for a key whose printed form does
  /// not say itself aloud: "Slash" for `/` (02 section 4.16).
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiKeyCapStyle style = UiKeyCapStyle.resolve(
      ui,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final Widget cap = DecoratedBox(
      decoration: ShapeDecoration(
        shape: Squircle.border(style.radius, side: style.side),
        color: style.background,
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minWidth: style.minSize,
          minHeight: style.minSize,
        ),
        child: Padding(
          padding: style.padding,
          child: Center(
            widthFactor: 1,
            heightFactor: 1,
            // A cap is a picture of a key rather than a control, so nothing
            // beneath the tooltip competes for the tap and the primitive's
            // own slot carries rule 4 (11 section 3.3).
            child: UiLabel(
              label,
              style: style.label.copyWith(color: style.foreground),
              textAlign: TextAlign.center,
              tooltip: (BuildContext context, String message, Widget label) =>
                  UiTooltip(message: message, child: label),
            ),
          ),
        ),
      ),
    );
    if (semanticsLabel == null) return cap;
    return Semantics(label: semanticsLabel, excludeSemantics: true, child: cap);
  }
}
