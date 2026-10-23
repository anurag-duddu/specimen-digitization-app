/// Small, single-series charts with an always-visible textual equivalent.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';

/// One labelled observation; null means it has not been measured.
@immutable
class UiChartDatum {
  /// Creates a chart observation. Values must be finite when present.
  const UiChartDatum({
    required this.label,
    required this.value,
    this.displayValue,
  });

  /// Category or observation label in reading order.
  final String label;

  /// Measured value, or null for an unavailable measurement.
  final double? value;

  /// Optional formatted value, for example `1,200 specimens`.
  final String? displayValue;

  /// True when a finite observation exists.
  bool get measured => value != null && value!.isFinite;

  /// Exact readable value. Missing and invalid values never become zero.
  String get description => !measured
      ? 'Not measured'
      : displayValue ??
            (value == value!.roundToDouble()
                ? value!.toStringAsFixed(0)
                : value.toString());
}

/// The chart's visual encoding.
enum UiChartKind {
  /// Separate columns for discrete categories.
  bars,

  /// A connected trace for ordered observations; missing values break it.
  line,
}

/// Token-derived chart paint and geometry.
@immutable
class UiChartStyle {
  /// Resolves geometry and contrast from the current theme.
  UiChartStyle.resolve(UiThemeData ui)
    : height = ui.space.targetMin * 3,
      gap = ui.space.s2,
      inset = ui.space.s3,
      stroke = ui.shape.stroke.emphasis,
      dotRadius = ui.space.s1,
      barRadius = ui.shape.inner,
      series = ui.color.accent,
      baseline = ui.color.boundary,
      label = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      value = ui.type.mono.identifier.copyWith(color: ui.color.ink);

  /// Plot height. The textual values below grow with the reader's text.
  final double height;

  /// Gap between plot, rows and values.
  final double gap;

  /// Inset keeping strokes and points inside the plot.
  final double inset;

  /// Trace and baseline thickness.
  final double stroke;

  /// Radius of each measured point in a line chart.
  final double dotRadius;

  /// Maximum column corner radius.
  final double barRadius;

  /// Accessible secondary brand hue for this one series.
  final Color series;

  /// Neutral zero baseline.
  final Color baseline;

  /// Category typography.
  final TextStyle label;

  /// Exact-value typography.
  final TextStyle value;
}

/// A compact bar or line chart with visible labels and exact values.
///
/// The zero baseline is retained for positive and negative observations. A
/// missing observation has no mark and breaks a line instead of claiming zero.
/// Empty data is stated explicitly. This is a small-summary component rather
/// than a substitute for an analytical plotting library.
class UiChart extends StatelessWidget {
  /// Creates a single-series chart in the caller's observation order.
  const UiChart({
    super.key,
    required this.label,
    required this.data,
    this.kind = UiChartKind.bars,
    this.emptyLabel = 'No measurements',
  });

  /// What the series measures, including its unit where applicable.
  final String label;

  /// Ordered observations, normally a small handful of categories.
  final List<UiChartDatum> data;

  /// Bar or line encoding.
  final UiChartKind kind;

  /// Visible explanation when the observation list is empty.
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    final UiChartStyle style = UiChartStyle.resolve(context.ui);
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Semantics(
            header: true,
            child: Text(
              label,
              style: context.ui.type.label.copyWith(
                color: context.ui.color.ink,
              ),
            ),
          ),
          SizedBox(height: style.gap),
          if (data.isEmpty)
            Text(emptyLabel, style: style.label)
          else ...<Widget>[
            ExcludeSemantics(
              child: SizedBox(
                height: style.height,
                child: CustomPaint(
                  painter: _ChartPainter(
                    data: List<UiChartDatum>.of(data),
                    kind: kind,
                    style: style,
                    direction: Directionality.of(context),
                  ),
                ),
              ),
            ),
            SizedBox(height: style.gap),
            for (final UiChartDatum point in data)
              Padding(
                padding: EdgeInsets.only(bottom: style.gap),
                child: Semantics(
                  container: true,
                  excludeSemantics: true,
                  label: '${point.label}: ${point.description}',
                  child: Wrap(
                    alignment: WrapAlignment.spaceBetween,
                    spacing: style.gap,
                    runSpacing: style.gap,
                    children: <Widget>[
                      Text(point.label, style: style.label),
                      Text(point.description, style: style.value),
                    ],
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _ChartPainter extends CustomPainter {
  const _ChartPainter({
    required this.data,
    required this.kind,
    required this.style,
    required this.direction,
  });

  final List<UiChartDatum> data;
  final UiChartKind kind;
  final UiChartStyle style;
  final TextDirection direction;

  @override
  void paint(Canvas canvas, Size size) {
    final Rect plot = Rect.fromLTRB(
      style.inset,
      style.inset,
      math.max(style.inset, size.width - style.inset),
      size.height - style.inset,
    );
    if (plot.width <= 0 || plot.height <= 0) return;
    final List<double> measured = data
        .where((UiChartDatum d) => d.measured)
        .map((UiChartDatum d) => d.value!)
        .toList();
    // Normalize before finding the range, avoiding overflow for finite values
    // near double.maxFinite at opposite ends of the axis.
    final double magnitude = measured.fold<double>(
      1,
      (double n, double v) => math.max(n, v.abs()),
    );
    final double low = measured.fold<double>(
      0,
      (double n, double v) => math.min(n, v / magnitude),
    );
    final double high = measured.fold<double>(
      0,
      (double n, double v) => math.max(n, v / magnitude),
    );
    final double span = high == low ? 1 : high - low;
    double y(double value) =>
        plot.bottom - (value / magnitude - low) / span * plot.height;
    final double zero = y(0);
    canvas.drawLine(
      Offset(plot.left, zero),
      Offset(plot.right, zero),
      Paint()
        ..color = style.baseline
        ..strokeWidth = style.stroke,
    );
    final Paint ink = Paint()
      ..color = style.series
      ..strokeWidth = style.stroke
      ..strokeCap = StrokeCap.round;
    final double step = plot.width / data.length;
    double x(int index) {
      final double along = (index + .5) * step;
      return direction == TextDirection.rtl
          ? plot.right - along
          : plot.left + along;
    }

    Offset? previous;
    for (int i = 0; i < data.length; i++) {
      final UiChartDatum datum = data[i];
      if (!datum.measured) {
        previous = null;
        continue;
      }
      final Offset point = Offset(x(i), y(datum.value!));
      if (kind == UiChartKind.line) {
        if (previous != null) canvas.drawLine(previous, point, ink);
        canvas.drawCircle(point, style.dotRadius, ink);
        previous = point;
      } else if (datum.value != 0) {
        final double width = math.max(0, step - math.min(style.gap, step / 2));
        final Rect bar = Rect.fromLTRB(
          point.dx - width / 2,
          math.min(zero, point.dy),
          point.dx + width / 2,
          math.max(zero, point.dy),
        );
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            bar,
            Radius.circular(
              math.min(style.barRadius, math.min(bar.width, bar.height) / 2),
            ),
          ),
          ink,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_ChartPainter oldDelegate) => true;
}
