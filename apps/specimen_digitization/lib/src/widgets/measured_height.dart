/// Reports a child's laid out height to its owner.
///
/// Flutter's flex algorithm has no way to say "take what you need, and give
/// the rest back": a loose `Flexible` that uses less than its share leaves the
/// remainder stranded in its own slot. Where one child has a target height and
/// another must keep a usable minimum, the only honest answer is to measure
/// the fixed parts and do the arithmetic. This is the measurement.
///
/// The callback lands on the frame after layout, never during it, so it is
/// safe to call `setState` from.
library;

import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

/// Calls [onHeight] whenever [child]'s laid out height changes.
class MeasuredHeight extends SingleChildRenderObjectWidget {
  const MeasuredHeight({
    super.key,
    required this.onHeight,
    required super.child,
  });

  /// Receives the child's height, once per change.
  final ValueChanged<double> onHeight;

  @override
  RenderObject createRenderObject(BuildContext context) =>
      RenderMeasuredHeight(onHeight);

  @override
  void updateRenderObject(
    BuildContext context,
    covariant RenderMeasuredHeight renderObject,
  ) => renderObject.onHeight = onHeight;
}

/// The render object behind [MeasuredHeight].
class RenderMeasuredHeight extends RenderProxyBox {
  RenderMeasuredHeight(this.onHeight);

  /// Receives the child's height, once per change.
  ValueChanged<double> onHeight;

  double? _reported;

  @override
  void performLayout() {
    super.performLayout();
    final double height = size.height;
    if (_reported == height) return;
    _reported = height;
    // Reporting during layout would mutate the tree mid-layout, so the
    // measurement lands on the next frame.
    SchedulerBinding.instance.addPostFrameCallback((_) => onHeight(height));
  }
}
