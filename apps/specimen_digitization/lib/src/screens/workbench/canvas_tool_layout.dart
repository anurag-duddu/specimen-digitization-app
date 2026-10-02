import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Height of an intrinsic eight-point Wrap of menu triggers and icon buttons.
///
/// Null labels identify icon buttons. This reserves the photograph's remaining
/// budget; the toolbar itself keeps its natural layout and is never fixed-height.
double canvasToolsHeight(
  BuildContext context,
  double availableWidth,
  List<String?> labels,
) {
  final ui = context.ui;
  final width = math.max(1.0, availableWidth);
  var x = 0.0;
  var height = 0.0;
  var rowHeight = 0.0;
  for (final label in labels) {
    var controlWidth = UiDensity.hitBox;
    var controlHeight = UiDensity.hitBox;
    if (label != null) {
      final text = TextPainter(
        text: TextSpan(text: label, style: ui.type.label),
        textDirection: Directionality.of(context),
        textScaler: MediaQuery.textScalerOf(context),
        maxLines: 1,
      )..layout();
      controlWidth = math.max(
        controlWidth,
        2 * ui.space.s4 +
            UiIconSize.action.dimension +
            ui.space.s2 +
            text.width,
      );
      controlHeight = math.max(controlHeight, text.height);
      text.dispose();
    }
    controlWidth = math.min(controlWidth, width);
    if (x > 0 && x + ui.space.s2 + controlWidth > width) {
      height += rowHeight + ui.space.s2;
      rowHeight = 0;
      x = 0;
    }
    x += (x > 0 ? ui.space.s2 : 0) + controlWidth;
    rowHeight = math.max(rowHeight, controlHeight);
  }
  return height + rowHeight;
}
