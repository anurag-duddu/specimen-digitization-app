/// The hover and press overlay (10 section 2 clause 6).
///
/// The state layer replaces the ink ripple, which 09 section 11 rejects: a
/// ripple animates outward from a touch point and says nothing a reviewer
/// needs, while a flat overlay says "this is under the pointer" and "this is
/// being pressed" at a glance.
library;

import 'package:flutter/widgets.dart';

import '../foundation/motion.dart';
import '../foundation/theme.dart';

/// Paints the state layer for a set of widget states.
///
/// Used only inside [Pressable]. A control paints its own fill and reads its
/// own states; this is the one overlay on top of both.
class StateLayer extends StatelessWidget {
  /// Draws the layer for [states] in [shape].
  const StateLayer({
    super.key,
    required this.states,
    required this.shape,
    this.child,
  });

  /// The control's current states.
  final Set<WidgetState> states;

  /// The control's outline, so the layer has the control's corners.
  final ShapeBorder shape;

  /// What the layer sits over, if anything.
  final Widget? child;

  /// The opacity [states] resolve to.
  static double opacityFor(Set<WidgetState> states, UiThemeData ui) {
    if (states.contains(WidgetState.disabled)) return 0;
    if (states.contains(WidgetState.pressed)) return ui.color.pressedOpacity;
    if (states.contains(WidgetState.hovered)) return ui.color.hoverOpacity;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double opacity = opacityFor(states, ui);
    // In rather than out: a press that has just started should show at once,
    // and a press that has ended should not snap away.
    final Duration duration = opacity > 0
        ? ui.motion.pressIn
        : ui.motion.pressOut;
    return AnimatedContainer(
      duration: duration,
      curve: MotionTokens.standardCurve,
      decoration: ShapeDecoration(
        shape: shape,
        color: ui.color.stateLayer(opacity),
      ),
      child: child,
    );
  }
}
