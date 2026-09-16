/// The light fields (09 section 3.2; 10 section 3, `FieldLayer`).
///
/// The only gradient painter in the product. It paints one sky preset once,
/// behind everything, inside a `RepaintBoundary`, and clips out the exclusion
/// the source pane asks for so no colour cast ever reaches a photograph.
library;

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

  /// How many stops the ease-out alpha falloff is sampled into.
  ///
  /// A linear two-stop gradient leaves a visible ring where the falloff
  /// changes rate; sampling an ease-out curve removes it. Sixteen is the
  /// point past which the extra stops stop changing the rendered pixels at
  /// the radii 09 allows.
  static const int stopCount = 16;

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
    final double shorter = size.shortestSide;
    for (final UiFieldPlacement placement in placements) {
      final UiFieldStyle style = fields[placement.field];
      final Offset centre = Offset(
        size.width * placement.x,
        size.height * placement.y,
      );
      final double radius = shorter * placement.radius;
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

  /// The colour at each stop: the centre colour, its alpha falling off with an
  /// ease-out curve so the field has no visible edge.
  static List<Color> _falloff(Color centre, double centreAlpha) =>
      <Color>[
        for (int i = 0; i < stopCount; i++)
          centre.withValues(
            alpha: centreAlpha * (1 - Curves.easeOutQuad.transform(i / (stopCount - 1))),
          ),
      ];

  static final List<double> _stops = <double>[
    for (int i = 0; i < stopCount; i++) i / (stopCount - 1),
  ];

  @override
  bool shouldRepaint(FieldPainter oldDelegate) =>
      oldDelegate.fields != fields ||
      oldDelegate.placements != placements ||
      oldDelegate.exclusion != exclusion;
}
