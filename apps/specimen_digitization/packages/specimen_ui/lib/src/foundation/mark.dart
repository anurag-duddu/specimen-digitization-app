/// The mark (09 section 9).
///
/// The pin: the entomologist's pin seen from the side, standing in a disc. It
/// is the one object every specimen in the collection shares and the verb the
/// product performs on a record.
///
/// This file draws the same geometry the brand rasters are rendered from:
/// `apps/specimen_digitization/assets/brand/pin.svg` is the vector source and
/// `tool/brand/render_mark.py` the raster generator. A change to one of the
/// five numbers below is a change to all three.
library;

import 'package:flutter/widgets.dart';

import 'theme.dart';

/// Which pair of roles the mark is drawn in.
enum UiMarkVariant {
  /// The pin in `on.accent` standing in a disc of `accent`. The mark.
  accent,

  /// The pin in `ink` standing in a disc of `paper`. The monochrome variant,
  /// for the environment banner and the help screen (09 section 9).
  mono;

  /// The disc's colour in [ui].
  Color disc(UiThemeData ui) =>
      this == UiMarkVariant.accent ? ui.color.accent : ui.color.paper;

  /// The pin's colour in [ui].
  Color pin(UiThemeData ui) =>
      this == UiMarkVariant.accent ? ui.color.onAccent : ui.color.ink;
}

/// The product's mark, drawn at [size].
///
/// Stated once at the 24 dp mark of 09 section 9 and scaled from there: the
/// disc fills the box, the pin is 16 dp tall with a 2 dp stroke and a 5 dp
/// head, and the whole pin is nudged 1 dp above the geometric centre so that a
/// head heavy shape does not read as sitting low.
///
/// The mark never rotates, never animates and never sits on a field
/// (09 section 9), so this widget holds no state and paints one frame. It is
/// an image to a screen reader, and [label] is what that image says; there is
/// no default, because the sentence a reviewer hears depends on where the mark
/// stands.
///
/// It is in the foundation rather than in a control family because it is the
/// brand itself: the launcher icons, the splash and this widget are three
/// renderings of one geometry, and nothing about it is a control.
class UiMark extends StatelessWidget {
  /// The mark: the pin in `on.accent`, standing in a disc of `accent`.
  const UiMark({required this.label, this.size = defaultSize, super.key})
    : variant = UiMarkVariant.accent,
      assert(size > 0, 'a mark with no size is not a mark');

  /// The monochrome variant: the pin in `ink`, standing in a disc of `paper`.
  const UiMark.mono({required this.label, this.size = defaultSize, super.key})
    : variant = UiMarkVariant.mono,
      assert(size > 0, 'a mark with no size is not a mark');

  /// The size 09 section 9 states the mark at, and the size it is drawn at
  /// unless a call site asks for another.
  static const double defaultSize = 24;

  /// What the mark says where it stands. Required, never guessed.
  final String label;

  /// The side of the square the mark is drawn in. The disc fills it.
  final double size;

  /// Which pair of roles the mark is drawn in.
  final UiMarkVariant variant;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Semantics(
      image: true,
      label: label,
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(
          painter: _PinPainter(disc: variant.disc(ui), pin: variant.pin(ui)),
        ),
      ),
    );
  }
}

/// The 24 dp box 09 section 9 states every other number against.
const double _markBox = 24;

/// The pin's total height, head included.
const double _pinHeight = 16;

/// The width of the pin's stroke.
const double _pinStroke = 2;

/// The diameter of the pin's head.
const double _headDiameter = 5;

/// How far above the geometric centre the pin sits.
const double _opticalRise = 1;

class _PinPainter extends CustomPainter {
  const _PinPainter({required this.disc, required this.pin});

  final Color disc;
  final Color pin;

  @override
  void paint(Canvas canvas, Size size) {
    final double side = size.shortestSide;
    if (side <= 0) return;
    final Offset centre = Offset(size.width / 2, size.height / 2);
    final double unit = side / _markBox;

    canvas.drawCircle(centre, side / 2, Paint()..color = disc);

    // The pin's box, then the three points on its axis that place the head,
    // the shaft and the tip. The shaft stops half a stroke short of the tip
    // because its round cap carries the last half.
    final double top = centre.dy - _opticalRise * unit - _pinHeight * unit / 2;
    final double headRadius = _headDiameter * unit / 2;
    final double headCentre = top + headRadius;
    final double tip = top + _pinHeight * unit;
    final double shaft = _pinStroke * unit;

    final Paint brush = Paint()..color = pin;
    canvas.drawCircle(Offset(centre.dx, headCentre), headRadius, brush);
    canvas.drawLine(
      Offset(centre.dx, headCentre),
      Offset(centre.dx, tip - shaft / 2),
      brush
        ..strokeWidth = shaft
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _PinPainter oldDelegate) =>
      oldDelegate.disc != disc || oldDelegate.pin != pin;
}
