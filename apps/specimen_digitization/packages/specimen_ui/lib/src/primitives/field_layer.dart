/// The light fields (09 section 3.2; 10 section 3, `FieldLayer`).
///
/// The only gradient painter in the product. It paints one sky preset once,
/// behind everything, inside a `RepaintBoundary`, and clips out the exclusion
/// the source pane asks for so no colour cast ever reaches a photograph.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../foundation/fields.dart';
import '../foundation/theme.dart';

/// Paints a sky preset behind a screen.
class FieldLayer extends StatelessWidget {
  /// Paints [preset] behind [child].
  const FieldLayer({
    super.key,
    required this.preset,
    this.child,
    this.exclusion,
  });

  /// Which preset to paint.
  final SkyPreset preset;

  /// The screen the fields sit behind.
  final Widget? child;

  /// A rectangle the fields are clipped out of, in this layer's coordinates.
  ///
  /// The photograph matte plus 24 dp. Principle 1 of 09 section 2: a colour
  /// cast on a faded label is a data error, so this is not negotiable.
  final Rect? exclusion;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<UiFieldPlacement> placements = ui.field.sky(preset);
    if (placements.isEmpty) {
      return ColoredBox(
        color: ui.color.ground,
        child: child ?? const SizedBox.expand(),
      );
    }
    return ColoredBox(
      color: ui.color.ground,
      child: Stack(
        fit: StackFit.passthrough,
        children: <Widget>[
          Positioned.fill(
            child: RepaintBoundary(
              child: CustomPaint(
                painter: FieldPainter(
                  fields: ui.field,
                  placements: placements,
                  exclusion: exclusion,
                ),
                isComplex: true,
                willChange: false,
              ),
            ),
          ),
          ?child,
        ],
      ),
    );
  }
}

/// Paints the placed fields of one preset.
///
/// Public so the gallery can draw a preset without a screen around it.
class FieldPainter extends CustomPainter {
  /// Paints [placements] from [fields].
  const FieldPainter({
    required this.fields,
    required this.placements,
    this.exclusion,
  });

  /// The colour table for the current mode.
  final UiFields fields;

  /// Where each field sits.
  final List<UiFieldPlacement> placements;

  /// The rectangle the fields are clipped out of.
  final Rect? exclusion;

  /// How many stops the alpha falloff is sampled into.
  ///
  /// The engine draws a straight line between stops, so the count decides how
  /// far the drawn gradient can sit from the curve it samples. Measured on the
  /// sun field, which has the widest channel span in the table: sixteen stops
  /// leave a worst case error of 0.57 of one 8 bit level, twenty four is the
  /// first count under half a level, and thirty two holds it at 0.13, which
  /// keeps the margin if a preset ever raises a centre alpha. Sixteen was
  /// enough for the quadratic falloff this replaced, whose curvature is
  /// lower.
  static const int stopCount = 32;

  /// How sharply the wash falls off, as the exponent of a Gaussian profile.
  ///
  /// The field is `exp(-falloff * t * t)`, normalised so it is one at the
  /// centre and zero at the radius. Four puts the half intensity point at 41
  /// percent of the radius and leaves a long, even tail, which is what "the
  /// way a projector wash lands on a wall" means in numbers (09 section 1).
  /// Higher is a spot with a soft edge; lower is a flat disc with a hard one.
  static const double falloff = 4;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect bounds = Offset.zero & size;
    canvas.save();
    final Rect? clip = exclusion;
    if (clip != null) {
      canvas.clipPath(
        Path.combine(
          PathOperation.difference,
          Path()..addRect(bounds),
          Path()..addRect(clip),
        ),
      );
    }
    // The longer side, not the shorter one. A field bound to the shorter
    // side of a 390 by 844 phone is a spot in a corner of a tall window; the
    // same fraction of the longer side is the wash 09 section 1 describes at
    // every window in the size class table.
    final double longer = size.longestSide;
    for (final UiFieldPlacement placement in placements) {
      final UiFieldStyle style = fields[placement.field];
      final Offset centre = Offset(
        size.width * placement.x,
        size.height * placement.y,
      );
      final double radius = longer * placement.radius;
      if (radius <= 0) continue;
      final double alpha = style.centreAlpha * placement.alphaScale;
      canvas.drawCircle(
        centre,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: _falloff(style.centre, alpha),
            stops: _stops,
          ).createShader(Rect.fromCircle(center: centre, radius: radius)),
      );
    }
    canvas.restore();
  }

  /// The colour at each stop: the centre colour, its alpha falling off on a
  /// Gaussian profile so the field has no visible edge and no visible
  /// inflection either.
  ///
  /// `Curves.easeOutQuad` was the first shape here and it measured as a spot:
  /// alpha is a quarter of the centre by 29 percent of the radius, so the
  /// window read as three dots on a ground rather than as light. A Gaussian
  /// holds near the centre, falls through the middle and thins out over a
  /// long tail, and it has no second derivative sign change, so no stop count
  /// ever puts a ring in it.
  static List<Color> _falloff(Color centre, double centreAlpha) => <Color>[
    for (int i = 0; i < stopCount; i++)
      centre.withValues(alpha: centreAlpha * profile(i / (stopCount - 1))),
  ];

  /// The share of its centre alpha the field carries at [t] of its radius.
  ///
  /// One at the centre, zero at the radius, monotonic between. Public so a
  /// test can assert the shape rather than the pixels it produces.
  static double profile(double t) {
    final double tail = math.exp(-falloff);
    return (math.exp(-falloff * t * t) - tail) / (1 - tail);
  }

  static final List<double> _stops = <double>[
    for (int i = 0; i < stopCount; i++) i / (stopCount - 1),
  ];

  @override
  bool shouldRepaint(FieldPainter oldDelegate) =>
      oldDelegate.fields != fields ||
      oldDelegate.placements != placements ||
      oldDelegate.exclusion != exclusion;
}
