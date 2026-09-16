/// The keyboard focus ring (09 section 3.6; 10 section 2 clause 4).
///
/// A 2 dp stroke with a 2 dp gap in the parent surface colour, drawn outside
/// the component so it never reflows layout, at the component's radius plus
/// four. Monochrome, because a blue ring belongs to a different system and a
/// monochrome one clears 3:1 against every surface and every field.
library;

import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';

/// Paints the focus ring around [child] when [visible].
///
/// The caller decides visibility, because only the caller knows whether the
/// focus came from the keyboard: the ring is drawn under
/// `FocusHighlightMode.traditional` and never on a pointer press.
class FocusRing extends StatelessWidget {
  /// Rings [child] when [visible].
  const FocusRing({
    super.key,
    required this.visible,
    required this.child,
    this.radius,
    this.capsule = false,
  });

  /// True when the ring should be painted.
  final bool visible;

  /// The component being ringed.
  final Widget child;

  /// The component's own corner radius. The ring is drawn at this plus the
  /// focus radius offset. Ignored when [capsule] is true.
  final double? radius;

  /// True when the component is a capsule, so the ring is one too.
  final bool capsule;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return CustomPaint(
      foregroundPainter: visible
          ? _FocusRingPainter(
              color: ui.color.focusRing,
              stroke: ui.shape.stroke.focus,
              gap: ui.shape.stroke.focusGap,
              radius: capsule
                  ? double.infinity
                  : (radius ?? ui.shape.inner) +
                        ui.shape.stroke.focusRadiusOffset,
            )
          : null,
      child: child,
    );
  }
}

class _FocusRingPainter extends CustomPainter {
  const _FocusRingPainter({
    required this.color,
    required this.stroke,
    required this.gap,
    required this.radius,
  });

  final Color color;
  final double stroke;
  final double gap;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    // Outside the component's box: the gap, then the stroke, so the ring never
    // covers a glyph and never changes the layout of what it rings.
    final Rect bounds = Rect.fromLTWH(
      0,
      0,
      size.width,
      size.height,
    ).inflate(gap + stroke / 2);
    final double corner = radius.isFinite
        ? radius
        : bounds.shortestSide / 2;
    canvas.drawRRect(
      RRect.fromRectAndRadius(bounds, Radius.circular(corner)),
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke,
    );
  }

  @override
  bool shouldRepaint(_FocusRingPainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.stroke != stroke ||
      oldDelegate.gap != gap ||
      oldDelegate.radius != radius;
}
