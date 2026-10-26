// GENERATED from assets/brand/specimen-mark.svg. Do not edit by hand.
// Regenerate with tool/brand/generate_flutter_mark.py, then dart format.
import 'dart:ui';

/// Canonical geometry traced from the owner's selected primary brand mark.
abstract final class MarkGeometry {
  /// Paints the same three interlocking ribbons without mirroring or a disc.
  static void paint(
    Canvas canvas,
    Size size, {
    required Color ink,
    required Color amber,
    required Color iris,
    required bool monochrome,
    required bool appIcon,
  }) {
    final scale = size.shortestSide / 512;
    canvas.save();
    canvas.translate(
      (size.width - size.shortestSide) / 2,
      (size.height - size.shortestSide) / 2,
    );
    canvas.scale(scale);
    canvas.translate(1, 42);
    final brush = Paint()..color = ink;
    canvas.drawPath(_upper, brush);
    if (!monochrome) {
      brush.shader = appIcon
          ? Gradient.linear(
              const Offset(145, 315),
              const Offset(390, 115),
              <Color>[
                iris,
                amber,
                Color.lerp(Color.lerp(amber, iris, 0.4), ink, 0.6)!,
                ink,
                amber,
              ],
              <double>[0, 0.28, 0.50, 0.72, 1],
            )
          : Gradient.linear(
              const Offset(145, 315),
              const Offset(300, 137),
              <Color>[
                iris,
                amber,
                Color.lerp(Color.lerp(amber, iris, 0.4), ink, 0.6)!,
                ink,
              ],
              <double>[0, 0.4, 0.72, 1],
            );
    }
    canvas.drawPath(_folded, brush);
    brush.shader = null;
    canvas.drawPath(_lower, brush);
    canvas.restore();
  }

  static final Path _upper = Path()
    ..fillType = PathFillType.evenOdd
    ..moveTo(60, 155)
    ..quadraticBezierTo(60, 139, 78, 130)
    ..lineTo(288, 43)
    ..quadraticBezierTo(303, 36, 316, 43)
    ..lineTo(335, 58)
    ..quadraticBezierTo(343, 65, 337, 72)
    ..lineTo(131, 161)
    ..quadraticBezierTo(102, 174, 102, 199)
    ..lineTo(102, 267)
    ..quadraticBezierTo(102, 284, 87, 275)
    ..lineTo(71, 265)
    ..quadraticBezierTo(60, 259, 60, 245)
    ..close();
  static final Path _folded = Path()
    ..fillType = PathFillType.evenOdd
    ..moveTo(132, 219)
    ..lineTo(132, 293)
    ..quadraticBezierTo(132, 309, 146, 318)
    ..lineTo(162, 326)
    ..quadraticBezierTo(174, 333, 174, 317)
    ..lineTo(174, 257)
    ..quadraticBezierTo(174, 232, 193, 222)
    ..lineTo(398, 128)
    ..quadraticBezierTo(412, 122, 401, 113)
    ..lineTo(386, 101)
    ..quadraticBezierTo(374, 91, 362, 97)
    ..lineTo(157, 187)
    ..quadraticBezierTo(132, 197, 132, 219)
    ..close();
  static final Path _lower = Path()
    ..fillType = PathFillType.evenOdd
    ..moveTo(205, 265)
    ..quadraticBezierTo(205, 247, 225, 237)
    ..lineTo(420, 150)
    ..quadraticBezierTo(439, 141, 450, 153)
    ..quadraticBezierTo(455, 159, 455, 171)
    ..lineTo(455, 272)
    ..quadraticBezierTo(455, 287, 440, 295)
    ..lineTo(259, 371)
    ..quadraticBezierTo(242, 380, 225, 372)
    ..lineTo(214, 366)
    ..quadraticBezierTo(205, 359, 205, 345)
    ..close()
    ..moveTo(277, 279)
    ..quadraticBezierTo(277, 271, 286, 267)
    ..lineTo(383, 223)
    ..quadraticBezierTo(391, 219, 391, 227)
    ..lineTo(391, 248)
    ..quadraticBezierTo(391, 256, 384, 260)
    ..lineTo(285, 304)
    ..quadraticBezierTo(277, 308, 277, 299)
    ..close();
}
