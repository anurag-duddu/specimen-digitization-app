/// Non-destructive image crop selection in normalized image coordinates.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import 'slider.dart';

/// A crop preview and precise keyboard/touch controls.
///
/// [value] is a rectangle in the unit image plane, independent of UI direction.
/// The host supplies an image fitted to [aspectRatio], accepts proposed changes,
/// and applies or cancels the result. This widget never mutates the source image.
class UiCropEditor extends StatelessWidget {
  /// Requires a positive, normalized crop contained in the image bounds.
  UiCropEditor({
    super.key,
    required this.image,
    required this.value,
    this.onChanged,
    this.aspectRatio = 4 / 3,
    this.label = 'Crop image',
    this.disabledReason,
  }) : assert(aspectRatio > 0),
       assert(
         value.left >= 0 &&
             value.top >= 0 &&
             value.right <= 1 &&
             value.bottom <= 1,
       ),
       assert(value.width > 0 && value.height > 0);

  /// Host-owned image or preview, filling the supplied image aspect ratio.
  final Widget image;

  /// Controlled crop in normalized image coordinates.
  final Rect value;

  /// Proposed crop changes; null makes the selection read-only.
  final ValueChanged<Rect>? onChanged;

  /// Width divided by height of the source image.
  final double aspectRatio;

  /// Accessible preview name.
  final String label;

  /// Explanation when adjustments are unavailable.
  final String? disabledReason;
  void _move(double x, double y) => onChanged?.call(
    Rect.fromLTWH(
      (value.left + x).clamp(0, 1 - value.width),
      (value.top + y).clamp(0, 1 - value.height),
      value.width,
      value.height,
    ),
  );
  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (onChanged == null ||
        event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
    final dx = key == LogicalKeyboardKey.arrowRight
        ? .01
        : key == LogicalKeyboardKey.arrowLeft
        ? -.01
        : 0.0;
    final dy = key == LogicalKeyboardKey.arrowDown
        ? .01
        : key == LogicalKeyboardKey.arrowUp
        ? -.01
        : 0.0;
    if (dx == 0 && dy == 0) return KeyEventResult.ignored;
    if (HardwareKeyboard.instance.isShiftPressed) {
      onChanged!(
        Rect.fromLTWH(
          value.left,
          value.top,
          (value.width + dx).clamp(math.min(.01, value.width), 1 - value.left),
          (value.height + dy).clamp(math.min(.01, value.height), 1 - value.top),
        ),
      );
    } else {
      _move(dx, dy);
    }
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    String percent(double n) => '${(n * 100).round()}%';
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          label: label,
          value:
              'Left ${percent(value.left)}, top ${percent(value.top)}, width ${percent(value.width)}, height ${percent(value.height)}',
          hint:
              disabledReason ??
              'Arrow keys move the crop. Shift and arrow keys resize it. Sliders provide precise adjustment.',
          child: Focus(
            debugLabel: label,
            canRequestFocus: onChanged != null,
            onKeyEvent: _key,
            child: AspectRatio(
              aspectRatio: aspectRatio,
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final width = constraints.maxWidth,
                      height = constraints.maxHeight;
                  return ClipRect(
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        ExcludeSemantics(child: image),
                        // Physical coordinates belong to the image, including in RTL.
                        Positioned(
                          left: value.left * width,
                          top: value.top * height,
                          width: value.width * width,
                          height: value.height * height,
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onPanUpdate: onChanged == null
                                ? null
                                : (details) => _move(
                                    details.delta.dx / width,
                                    details.delta.dy / height,
                                  ),
                            child: Container(
                              decoration: BoxDecoration(
                                border: Border.all(
                                  color: ui.color.accent,
                                  width: ui.shape.stroke.emphasis,
                                ),
                              ),
                              child: CustomPaint(
                                painter: _CropGrid(ui.color.accent),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ),
        ),
        SizedBox(height: ui.space.s3),
        UiSlider(
          label: 'Crop left',
          value: value.left,
          min: 0,
          max: 1,
          valueLabel: percent,
          onChanged: onChanged == null ? null : (v) => _move(v - value.left, 0),
          disabledReason: disabledReason,
        ),
        UiSlider(
          label: 'Crop top',
          value: value.top,
          min: 0,
          max: 1,
          valueLabel: percent,
          onChanged: onChanged == null ? null : (v) => _move(0, v - value.top),
          disabledReason: disabledReason,
        ),
        UiSlider(
          label: 'Crop width',
          value: value.width,
          min: 0,
          max: 1,
          valueLabel: percent,
          onChanged: onChanged == null
              ? null
              : (v) => onChanged!(
                  Rect.fromLTWH(
                    value.left,
                    value.top,
                    v.clamp(math.min(.01, value.width), 1 - value.left),
                    value.height,
                  ),
                ),
          disabledReason: disabledReason,
        ),
        UiSlider(
          label: 'Crop height',
          value: value.height,
          min: 0,
          max: 1,
          valueLabel: percent,
          onChanged: onChanged == null
              ? null
              : (v) => onChanged!(
                  Rect.fromLTWH(
                    value.left,
                    value.top,
                    value.width,
                    v.clamp(math.min(.01, value.height), 1 - value.top),
                  ),
                ),
          disabledReason: disabledReason,
        ),
      ],
    );
  }
}

class _CropGrid extends CustomPainter {
  const _CropGrid(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withValues(alpha: .6)
      ..strokeWidth = 1;
    for (final fraction in [1 / 3, 2 / 3]) {
      canvas.drawLine(
        Offset(size.width * fraction, 0),
        Offset(size.width * fraction, size.height),
        paint,
      );
      canvas.drawLine(
        Offset(0, size.height * fraction),
        Offset(size.width, size.height * fraction),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_CropGrid oldDelegate) => oldDelegate.color != color;
}
