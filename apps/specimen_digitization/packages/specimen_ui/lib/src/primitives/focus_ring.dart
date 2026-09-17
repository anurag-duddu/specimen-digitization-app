/// The focus ring (09 section 3.6 with its fit amendment; 10 section 2
/// clause 4; 11 section 4).
///
/// A 2 dp stroke with a 2 dp gap in the parent surface colour, drawn outside
/// the component so it never reflows layout, at the component's radius plus
/// four. Monochrome, because a blue ring belongs to a different system and a
/// monochrome one clears 3:1 against every surface and every field.
///
/// The ring takes the shape it rings. A circular rounded rectangle around a
/// superellipse is what made a focused field read as three edges: the two
/// curves run together on the straight part of a corner and apart at its
/// ends, so the eye reads a second outline rather than a ring. A superellipse
/// is ringed by a superellipse, a capsule by a stadium and a disc by a
/// circle, and every one of them runs concentric with the edge it rings.
library;

import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';

/// The shape a [FocusRing] follows.
///
/// An enum rather than a `bool`, because the system has three shapes and a
/// pair of booleans would let a caller ask for two of them at once.
enum FocusRingShape {
  /// A superellipse at the component's radius. Fields, tiles, sheets, and
  /// anything else `Squircle.border` draws.
  superellipse,

  /// A capsule. Buttons, chips, search fields, the navigation discs. The
  /// radius is the shorter side halved, so the ring matches `StadiumBorder`.
  stadium,

  /// A circle. The radio's disc, and any control drawn as one.
  circle,
}

/// Paints the focus ring around [child] when [visible].
///
/// The caller decides visibility, because only the caller knows what kind of
/// focus it has. Every control shows the ring under
/// `FocusHighlightMode.traditional` alone; a text editing field shows it for
/// any focus, pointer or keyboard, because a focused field is being edited
/// and a caret on its own does not say which of several fields that is
/// (09 section 3.6, fit amendment).
class FocusRing extends StatelessWidget {
  /// Rings [child] when [visible].
  const FocusRing({
    super.key,
    required this.visible,
    required this.child,
    this.radius,
    this.shape = FocusRingShape.superellipse,
  });

  /// True when the ring should be painted.
  final bool visible;

  /// The component being ringed.
  final Widget child;

  /// The component's own corner radius. The ring is drawn at this plus the
  /// focus radius offset. Read only for [FocusRingShape.superellipse]; the
  /// other two shapes take their curve from the box they are given.
  final double? radius;

  /// The shape the component is drawn in, which is the shape of its ring.
  final FocusRingShape shape;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return CustomPaint(
      foregroundPainter: visible
          ? _FocusRingPainter(
              color: ui.color.focusRing,
              stroke: ui.shape.stroke.focus,
              gap: ui.shape.stroke.focusGap,
              shape: shape,
              radius:
                  (radius ?? ui.shape.inner) +
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
    required this.shape,
    required this.radius,
  });

  final Color color;
  final double stroke;
  final double gap;
  final FocusRingShape shape;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    // Outside the component's box: the gap, then the stroke, so the ring never
    // covers a glyph and never changes the layout of what it rings.
    final Rect bounds = (Offset.zero & size).inflate(gap + stroke / 2);
    final Paint paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke;
    switch (shape) {
      case FocusRingShape.superellipse:
        canvas.drawRSuperellipse(
          RSuperellipse.fromRectAndRadius(bounds, Radius.circular(radius)),
          paint,
        );
      case FocusRingShape.stadium:
        // What `StadiumBorder` draws: a rounded rectangle whose radius is
        // half the shorter side. A superellipse here would part company with
        // the capsule it rings at the ends of the curve.
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            bounds,
            Radius.circular(bounds.shortestSide / 2),
          ),
          paint,
        );
      case FocusRingShape.circle:
        canvas.drawCircle(bounds.center, bounds.shortestSide / 2, paint);
    }
  }

  @override
  bool shouldRepaint(_FocusRingPainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.stroke != stroke ||
      oldDelegate.gap != gap ||
      oldDelegate.shape != shape ||
      oldDelegate.radius != radius;
}
