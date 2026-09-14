/// Where a label region lands on screen, and the view that frames it
/// (screen blueprints, 6.2; motion catalog rows 34, 36, 37 and 39).
///
/// Pure geometry, kept out of the widget so it can be checked directly. Every
/// value here is derived from the asset's own pixel dimensions and the
/// region's recorded box; nothing is measured off the rendered image, and
/// nothing rewrites the recorded coordinates.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

/// The size an image of aspect [aspect] takes inside a box, letterboxed.
Size fitAspect(double aspect, double maxWidth, double maxHeight) =>
    maxWidth / maxHeight > aspect
    ? Size(maxHeight * aspect, maxHeight)
    : Size(maxWidth, maxWidth / aspect);

/// The box the photograph occupies inside a viewport of [viewport], after
/// [quarterTurns] of view rotation.
///
/// A quarter turn swaps the constraints the image is fitted into, which is
/// what keeps a rotated landscape photograph inside the pane instead of
/// overflowing it.
Rect sourceBoxIn(Size viewport, double width, double height, int quarterTurns) {
  final double aspect = height == 0 ? 1 : width / height;
  final bool turned = quarterTurns.isOdd;
  final Size inner = turned
      ? fitAspect(aspect, viewport.height, viewport.width)
      : fitAspect(aspect, viewport.width, viewport.height);
  final Size outer = turned ? Size(inner.height, inner.width) : inner;
  return Rect.fromLTWH(
    (viewport.width - outer.width) / 2,
    (viewport.height - outer.height) / 2,
    outer.width,
    outer.height,
  );
}

/// Maps a point in the photograph's own pixel space, normalized to 0 to 1,
/// through [quarterTurns] of clockwise view rotation.
Offset rotateUnit(Offset point, int quarterTurns) => switch (quarterTurns % 4) {
  1 => Offset(1 - point.dy, point.dx),
  2 => Offset(1 - point.dx, 1 - point.dy),
  3 => Offset(point.dy, 1 - point.dx),
  _ => point,
};

/// The region's box in the coordinate space of the zoomable child.
///
/// [bbox] is `[left, top, right, bottom]` in the asset's original pixels.
Rect regionRectIn(
  Size viewport,
  List<num> bbox,
  double width,
  double height,
  int quarterTurns,
) {
  final Rect box = sourceBoxIn(viewport, width, height, quarterTurns);
  final Offset a = rotateUnit(
    Offset(bbox[0] / width, bbox[1] / height),
    quarterTurns,
  );
  final Offset b = rotateUnit(
    Offset(bbox[2] / width, bbox[3] / height),
    quarterTurns,
  );
  return Rect.fromLTRB(
    box.left + math.min(a.dx, b.dx) * box.width,
    box.top + math.min(a.dy, b.dy) * box.height,
    box.left + math.max(a.dx, b.dx) * box.width,
    box.top + math.max(a.dy, b.dy) * box.height,
  );
}

/// The transform that frames [target] inside [viewport].
///
/// The scale is clamped to the viewer's own limits, so framing a one pixel
/// region does not ask for a magnification the viewer will refuse and then
/// silently disagree with.
Matrix4 frameRect(
  Size viewport,
  Rect target, {
  required double minScale,
  required double maxScale,
  double padding = 1.08,
}) {
  if (target.width <= 0 || target.height <= 0) return Matrix4.identity();
  final double raw = math.min(
    viewport.width / (target.width * padding),
    viewport.height / (target.height * padding),
  );
  final double scale = raw.clamp(minScale, maxScale);
  final Offset centre = target.center;
  return Matrix4.identity()
    ..translateByDouble(
      viewport.width / 2 - centre.dx * scale,
      viewport.height / 2 - centre.dy * scale,
      0,
      1,
    )
    ..scaleByDouble(scale, scale, 1, 1);
}

/// The transform that keeps the current view but changes its scale by
/// [factor] about the viewport's centre.
Matrix4 scaleAbout(
  Matrix4 current,
  Size viewport,
  double factor, {
  required double minScale,
  required double maxScale,
}) {
  final double now = current.getMaxScaleOnAxis();
  final double next = (now * factor).clamp(minScale, maxScale);
  if (next == now) return current;
  final double applied = next / now;
  final Offset centre = Offset(viewport.width / 2, viewport.height / 2);
  return Matrix4.identity()
    ..translateByDouble(centre.dx, centre.dy, 0, 1)
    ..scaleByDouble(applied, applied, 1, 1)
    ..translateByDouble(-centre.dx, -centre.dy, 0, 1)
    ..multiply(current);
}
