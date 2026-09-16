/// The scrim behind modal glass (10 section 3, `Scrim`).
///
/// Lower than v1 because the pane itself already blurs what is behind it
/// (09 section 3.1).
library;

import 'package:flutter/widgets.dart';

import '../foundation/motion.dart';
import '../foundation/theme.dart';

/// A tappable dim layer behind a modal surface.
class Scrim extends StatelessWidget {
  /// Dims the content behind a modal when [visible].
  const Scrim({
    super.key,
    this.visible = true,
    this.onDismiss,
    this.dismissLabel,
  });

  /// True while the modal is on screen.
  final bool visible;

  /// What a tap on the scrim does. Null makes the scrim inert, which is what
  /// a modal that must be answered wants.
  final VoidCallback? onDismiss;

  /// The label a screen reader reads for the dismiss gesture. Required
  /// wherever [onDismiss] is set, because a control with no visible text needs
  /// one (10 section 11).
  final String? dismissLabel;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget layer = AnimatedOpacity(
      opacity: visible ? 1 : 0,
      duration: ui.motion.standard,
      curve: MotionTokens.standardCurve,
      child: ColoredBox(color: ui.color.scrim, child: const SizedBox.expand()),
    );
    if (onDismiss == null) return IgnorePointer(child: layer);
    return Semantics(
      label: dismissLabel,
      button: true,
      onTap: onDismiss,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        excludeFromSemantics: true,
        onTap: onDismiss,
        child: layer,
      ),
    );
  }
}
