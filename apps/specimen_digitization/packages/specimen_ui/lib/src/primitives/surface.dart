/// The solid pane (10 section 3, `Surface`).
///
/// Where glass is not warranted, a surface is `paper` or `matte` with a shape
/// token and an optional hairline. Repeated items are surfaces, never glass.
library;

import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';
import 'squircle.dart';

/// Which solid surface a pane sits on.
enum SurfaceRole {
  /// The window background.
  ground,

  /// List bodies, tables, fields, cards.
  paper,

  /// The letterbox behind a photograph.
  matte,
}

/// A solid pane at a shape token.
class Surface extends StatelessWidget {
  /// Paints [child] on [role].
  const Surface({
    super.key,
    required this.child,
    this.role = SurfaceRole.paper,
    this.radius,
    this.capsule = false,
    this.hairline = false,
    this.boundary = false,
    this.padding,
    this.clip = false,
  });

  /// What the pane contains.
  final Widget child;

  /// Which solid surface to paint.
  final SurfaceRole role;

  /// The corner radius. Defaults to `radius.tile`.
  final double? radius;

  /// True to draw the pane as a capsule.
  final bool capsule;

  /// True to draw a 1 dp hairline edge. Decorative separation.
  final bool hairline;

  /// True to draw a 1 dp boundary edge. An edge the reviewer must find.
  final bool boundary;

  /// Padding inside the pane.
  final EdgeInsetsGeometry? padding;

  /// True to clip [child] to the pane's shape. Costs a save layer, so it is
  /// off unless the content actually reaches the corners.
  final bool clip;

  /// The colour [role] resolves to.
  Color colorOf(UiThemeData ui) => switch (role) {
    SurfaceRole.ground => ui.color.ground,
    SurfaceRole.paper => ui.color.paper,
    SurfaceRole.matte => ui.color.matte,
  };

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double corner = radius ?? ui.shape.tile;
    final BorderSide side = boundary
        ? BorderSide(color: ui.color.boundary, width: ui.shape.stroke.boundary)
        : hairline
        ? BorderSide(color: ui.color.hairline, width: ui.shape.stroke.hairline)
        : BorderSide.none;
    final ShapeBorder shape = capsule
        ? StadiumBorder(side: side)
        : Squircle.border(corner, side: side);

    Widget content = child;
    if (padding != null) content = Padding(padding: padding!, child: content);
    if (clip && !capsule) {
      content = Squircle.clip(radius: corner, child: content);
    } else if (clip) {
      content = ClipPath(
        clipper: ShapeBorderClipper(shape: shape),
        child: content,
      );
    }

    return DecoratedBox(
      decoration: ShapeDecoration(shape: shape, color: colorOf(ui)),
      child: content,
    );
  }
}
