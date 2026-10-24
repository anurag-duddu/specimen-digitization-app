/// Review-only pointers and dimension annotations for design documentation.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';

/// The gesture being explained by an annotation.
enum UiDesignPointerKind {
  /// A pointing cursor.
  arrow,

  /// A movable region.
  drag,

  /// A hand interaction.
  hand,
}

/// A labelled Phosphor pointer for design review, without a click action.
class UiDesignPointer extends StatelessWidget {
  /// Builds review content rather than an interactive product control.
  const UiDesignPointer({
    super.key,
    required this.label,
    this.kind = UiDesignPointerKind.arrow,
  });

  /// Name of the reviewer or the gesture being demonstrated.
  final String label;

  /// Gesture illustration.
  final UiDesignPointerKind kind;

  @override
  Widget build(BuildContext context) => Semantics(
    image: true,
    label: '${kind.name}: $label',
    child: ExcludeSemantics(
      child: Wrap(
        spacing: context.ui.space.s2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          UiIcon(switch (kind) {
            UiDesignPointerKind.arrow => UiIcons.designPointer,
            UiDesignPointerKind.drag => UiIcons.designDrag,
            UiDesignPointerKind.hand => UiIcons.designHand,
          }),
          Text(label, style: context.ui.type.labelSmall),
        ],
      ),
    ),
  );
}

/// Physical placement of a measurement label in a diagram.
enum UiMeasurementLabelPosition {
  /// Above a horizontal rule.
  top,

  /// Below a horizontal rule.
  bottom,

  /// Left of a vertical rule; diagram coordinates do not reverse in RTL.
  left,

  /// Right of a vertical rule.
  right,
}

/// A dimension line or a hatched spacing annotation.
class UiMeasurement extends StatelessWidget {
  /// The label states the actual measured value; no automatic measurement occurs.
  const UiMeasurement({
    super.key,
    required this.label,
    this.position = UiMeasurementLabelPosition.top,
    this.spacer = false,
    this.extent,
  });

  /// Caller-supplied measurement, including units.
  final String label;

  /// Physical diagram placement of the label.
  final UiMeasurementLabelPosition position;

  /// Shows a hatched spacing band instead of a dimension rule.
  final bool spacer;

  /// Optional visual length in logical pixels; defaults to the annotation token.
  final double? extent;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final vertical =
        position == UiMeasurementLabelPosition.left ||
        position == UiMeasurementLabelPosition.right;
    final text = Text(
      label,
      style: ui.type.mono.identifier,
      textAlign: TextAlign.center,
    );
    final line = SizedBox(
      width: vertical ? ui.space.s4 : extent ?? ui.space.annotationExtent,
      height: vertical ? extent ?? ui.space.annotationExtent : ui.space.s4,
      child: CustomPaint(
        painter: _DimensionPainter(
          color: ui.color.inkSecondary,
          vertical: vertical,
          spacer: spacer,
        ),
      ),
    );
    final before =
        position == UiMeasurementLabelPosition.top ||
        position == UiMeasurementLabelPosition.left;
    return Semantics(
      image: true,
      label: '${spacer ? 'Spacing' : 'Dimension'}: $label',
      child: ExcludeSemantics(
        child: vertical
            ? Row(
                mainAxisSize: MainAxisSize.min,
                textDirection: TextDirection.ltr,
                children: [
                  if (before) Flexible(child: text),
                  line,
                  if (!before) Flexible(child: text),
                ],
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [if (before) text, line, if (!before) text],
              ),
      ),
    );
  }
}

class _DimensionPainter extends CustomPainter {
  const _DimensionPainter({
    required this.color,
    required this.vertical,
    required this.spacer,
  });
  final Color color;
  final bool vertical, spacer;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1;
    if (spacer) {
      canvas.save();
      canvas.clipRect(Offset.zero & size);
      canvas.drawRect(
        Offset.zero & size,
        Paint()..color = color.withValues(alpha: .08),
      );
      for (var x = -size.height; x < size.width; x += 8) {
        canvas.drawLine(
          Offset(x, 0),
          Offset(x + size.height, size.height),
          paint,
        );
      }
      canvas.restore();
      return;
    }
    if (vertical) {
      canvas.drawLine(
        Offset(size.width / 2, 0),
        Offset(size.width / 2, size.height),
        paint,
      );
      canvas.drawLine(Offset.zero, Offset(size.width, 0), paint);
      canvas.drawLine(
        Offset(0, size.height),
        Offset(size.width, size.height),
        paint,
      );
    } else {
      canvas.drawLine(
        Offset(0, size.height / 2),
        Offset(size.width, size.height / 2),
        paint,
      );
      canvas.drawLine(Offset.zero, Offset(0, size.height), paint);
      canvas.drawLine(
        Offset(size.width, 0),
        Offset(size.width, size.height),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_DimensionPainter oldDelegate) =>
      color != oldDelegate.color ||
      vertical != oldDelegate.vertical ||
      spacer != oldDelegate.spacer;
}
