/// Multi-series analytical summaries with a complete textual equivalent.
library;

import 'dart:math' as math;
import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import 'chart.dart';

/// Visual encodings supported by [UiDataVisualization].
enum UiDataVisualizationKind {
  /// Adjacent columns comparing series within each category.
  groupedBars,

  /// Columns stacking positive and negative contributions separately.
  stackedBars,

  /// A continuous trace or separator.
  line,

  /// Measured traces with a translucent fill to the zero baseline.
  area,

  /// Proportional slices with no centre hole.
  pie,

  /// Proportional slices around a configurable centre hole.
  donut,

  /// Shared-scale radial comparisons across at least three categories.
  radar,

  /// Concentric completion rings against an explicit maximum.
  gauge,
}

/// Where the series key is placed. The end position stacks on narrow layouts.
enum UiChartLegend {
  /// No decorative separation or key.
  none,

  /// Above the plot.
  top,

  /// At the trailing edge when space allows, otherwise below the plot.
  end,

  /// Below the plot.
  bottom,
}

/// Plot sizing, independent of labels which always follow text scaling.
enum UiChartSize {
  /// The smallest compact plot.
  xxs,

  /// An extra-small compact plot.
  xs,

  /// A small plot.
  sm,

  /// The default medium plot.
  md,

  /// A large plot.
  lg,
}

/// One ordered series. Categories are identified by their labels.
@immutable
class UiChartSeries {
  /// Creates the component with explicit content and caller-owned state.
  const UiChartSeries({required this.label, required this.data});

  /// The visible accessible name supplied by the host.
  final String label;

  /// The ordered labelled observations for this series.
  final List<UiChartDatum> data;
}

/// Token-derived geometry shared by the plot and its key.
@immutable
class UiDataVisualizationStyle {
  /// Resolves plot geometry while reserving room for scaled axis labels.
  UiDataVisualizationStyle.resolve(
    UiThemeData ui,
    UiChartSize size,
    TextScaler scaler,
  ) : height = math.max(
        ui.space.targetMin *
            switch (size) {
              UiChartSize.xxs => 1.5,
              UiChartSize.xs => 2,
              UiChartSize.sm => 3,
              UiChartSize.md => 4,
              UiChartSize.lg => 6,
            },
        scaler.scale(ui.type.bodySmall.fontSize!) *
                (ui.type.bodySmall.height ?? 1) *
                3 +
            ui.space.s4 * 2,
      ),
      inset = ui.space.s4,
      gap = ui.space.s3,
      stroke = ui.shape.stroke.emphasis,
      radius = ui.space.s1,
      minimum = ui.space.readingMax,
      colors = [
        ui.brand.secondary.content,
        ui.color.inkSecondary,
        ui.color.ink,
        ui.brand.iris,
        ui.brand.amber,
        ui.color.inkTertiary,
      ],
      boundary = ui.color.boundary,
      label = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary);

  /// Plot height derived from the named size and scaled type.
  final double height;

  /// Inset keeping strokes and markers inside the plot.
  final double inset;

  /// Spacing between the plot, labels and key.
  final double gap;

  /// Stroke thickness for marks and boundaries.
  final double stroke;

  /// Radius of measured point markers.
  final double radius;

  /// Minimum allocation for a chart and trailing legend to share a row.
  final double minimum;

  /// The approved brand and neutral series colours, paired with exact text values.
  final List<Color> colors;

  /// The neutral plot boundary colour.
  final Color boundary;

  /// The visible accessible name supplied by the host.
  final TextStyle label;
}

/// A responsive chart with exact values that remain available without colour.
///
/// The host supplies ordered categories and formatting. Missing observations
/// break traces and never become zero. Cartesian charts include zero and retain
/// negative observations. Circular and radar encodings require nonnegative data;
/// invalid input is explained instead of silently discarding values. Pie/donut
/// use the first series; the API refuses multiple series for those encodings.
/// Gauge rings use each series' first observation and [maximum]. No interpolation
/// or smoothing invents unmeasured observations. Textual data is always shown.
/// Radar axes use numbered markers and a wrapping category key so long names
/// never collide with the plot or depend on fixed canvas label bounds.
class UiDataVisualization extends StatelessWidget {
  /// Creates the component with explicit content and caller-owned state.
  const UiDataVisualization({
    super.key,
    required this.label,
    required this.series,
    this.kind = UiDataVisualizationKind.line,
    this.legend = UiChartLegend.top,
    this.showAxes = true,
    this.maximum = 100,
    this.emptyLabel = 'No measurements',
    this.xAxisLabel,
    this.yAxisLabel,
    this.size = UiChartSize.md,
    this.holeRatio = .5,
  }) : assert(holeRatio >= 0 && holeRatio < 1);

  /// The visible accessible name supplied by the host.
  final String label;

  /// The ordered series, each retaining its own measured and missing observations.
  final List<UiChartSeries> series;

  /// The visual encoding applied to the observations.
  final UiDataVisualizationKind kind;

  /// The position of the series key.
  final UiChartLegend legend;

  /// Whether numeric ticks and category labels are displayed.
  final bool showAxes;

  /// The positive upper bound shared by gauge rings.
  final double maximum;

  /// The explanation displayed when no observations exist.
  final String emptyLabel;

  /// Axis descriptions, normally the category/time unit and measured unit.
  final String? xAxisLabel, yAxisLabel;

  /// Chart plot height class, keeping the value table unconstrained.
  final UiChartSize size;

  /// Inner radius relative to outer radius for donut charts.
  final double holeRatio;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiDataVisualizationStyle.resolve(
      ui,
      size,
      MediaQuery.textScalerOf(context),
    );
    final all = series.expand((s) => s.data).toList();
    final circular =
        kind == UiDataVisualizationKind.pie ||
        kind == UiDataVisualizationKind.donut;
    final radial =
        circular ||
        kind == UiDataVisualizationKind.radar ||
        kind == UiDataVisualizationKind.gauge;
    final invalid =
        series.any(
          (s) => s.data.map((d) => d.label).toSet().length != s.data.length,
        )
        ? 'Each series requires unique category labels.'
        : kind == UiDataVisualizationKind.radar &&
              all.map((d) => d.label).toSet().length < 3 &&
              all.isNotEmpty
        ? 'Radar charts require at least three distinct categories.'
        : circular && series.length > 1
        ? 'Pie and donut charts require one series.'
        : radial && all.any((v) => v.measured && v.value! < 0)
        ? 'This chart requires nonnegative measurements.'
        : kind == UiDataVisualizationKind.gauge &&
              (!maximum.isFinite ||
                  maximum <= 0 ||
                  series.any(
                    (s) =>
                        s.data.length > 1 ||
                        s.data.any((v) => v.measured && v.value! > maximum),
                  ))
        ? 'Gauge values must be between zero and the maximum, with one value per ring.'
        : null;
    final key = Wrap(
      spacing: style.gap,
      runSpacing: style.gap,
      children: [
        for (
          var i = 0;
          i <
              (circular && series.isNotEmpty
                  ? series.first.data.length
                  : series.length);
          i++
        )
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ExcludeSemantics(
                child: Container(
                  width: ui.space.s3,
                  height: ui.space.s3,
                  decoration: BoxDecoration(
                    color: style.colors[i % style.colors.length],
                    border: Border.all(
                      color: style.boundary,
                      width: style.stroke,
                    ),
                  ),
                ),
              ),
              SizedBox(width: ui.space.s2),
              Flexible(
                child: Text(
                  '${i + 1}. ${circular ? series.first.data[i].label : series[i].label}',
                  style: style.label,
                ),
              ),
            ],
          ),
      ],
    );
    final categories = all.map((d) => d.label).toSet().toList();
    final magnitude = all.fold<double>(
      1,
      (n, d) => d.measured ? math.max(n, d.value!.abs()) : n,
    );
    var low = 0.0, high = 0.0;
    for (final c in categories) {
      var positive = 0.0, negative = 0.0;
      for (final s in series) {
        for (final d in s.data.where((d) => d.label == c && d.measured)) {
          final v = d.value! / magnitude;
          if (kind == UiDataVisualizationKind.stackedBars) {
            if (v >= 0) {
              positive += v;
            } else {
              negative += v;
            }
          } else {
            low = math.min(low, v);
            high = math.max(high, v);
          }
        }
      }
      low = math.min(low, negative);
      high = math.max(high, positive);
    }
    String tick(double n) {
      final v = n * magnitude;
      if (!v.isFinite) {
        return n < 0 ? 'Below numeric range' : 'Above numeric range';
      }
      return v.abs() >= 1000000
          ? v.toStringAsExponential(1)
          : v == v.roundToDouble()
          ? v.toStringAsFixed(0)
          : v.toStringAsPrecision(3);
    }

    final plot = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showAxes && !radial && yAxisLabel != null)
          Text(yAxisLabel!, style: style.label),
        LayoutBuilder(
          builder: (context, constraints) {
            final axis = showAxes && !radial;
            final ticks = [tick(high), tick((low + high) / 2), tick(low)];
            final axisWidth = axis
                ? ticks.fold<double>(
                    0,
                    (width, text) => math.max(
                      width,
                      measureLabel(
                        context,
                        text,
                        style.label,
                      ).width.ceilToDouble(),
                    ),
                  )
                : 0.0;
            final categoryWidth =
                ui.space.targetMin * MediaQuery.textScalerOf(context).scale(1);
            final plotWidth = math.max(
              0.0,
              math.max(
                constraints.maxWidth - axisWidth,
                axis ? math.max(2, categories.length) * categoryWidth : 0.0,
              ),
            );
            // The axis and plot share a scrollable canvas. A long range label
            // must not consume the plot's whole allocation or overflow a card.
            return SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (axis)
                    SizedBox(
                      width: axisWidth,
                      height: style.height,
                      child: Padding(
                        padding: EdgeInsets.symmetric(vertical: style.inset),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            for (final value in ticks)
                              Text(value, style: style.label),
                          ],
                        ),
                      ),
                    ),
                  SizedBox(
                    width: plotWidth,
                    child: Column(
                      children: [
                        ExcludeSemantics(
                          child: SizedBox(
                            height: style.height,
                            width: double.infinity,
                            child: CustomPaint(
                              painter: _VisualizationPainter(
                                series: series,
                                kind: kind,
                                style: style,
                                showAxes: showAxes,
                                maximum: maximum,
                                holeRatio: holeRatio,
                                direction: Directionality.of(context),
                                textScaler: MediaQuery.textScalerOf(context),
                              ),
                            ),
                          ),
                        ),
                        if (axis)
                          Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: style.inset,
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                for (final c in categories)
                                  Expanded(
                                    child: Text(
                                      c,
                                      textAlign: TextAlign.center,
                                      style: style.label,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
        if (showAxes && !radial && xAxisLabel != null)
          Text(xAxisLabel!, textAlign: TextAlign.center, style: style.label),
        if (showAxes && kind == UiDataVisualizationKind.radar)
          Padding(
            padding: EdgeInsets.only(top: style.gap),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var index = 0; index < categories.length; index++)
                  Text(
                    '${index + 1}. ${categories[index]}',
                    style: style.label,
                  ),
              ],
            ),
          ),
      ],
    );
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Semantics(
            header: true,
            child: Text(
              label,
              style: ui.type.label.copyWith(color: ui.color.ink),
            ),
          ),
          SizedBox(height: style.gap),
          if (all.isEmpty)
            Text(emptyLabel, style: style.label)
          else ...[
            if (legend == UiChartLegend.top) key,
            if (invalid != null)
              Text(invalid, style: style.label)
            else if (!all.any((d) => d.measured))
              Text('Not measured', style: style.label)
            else
              LayoutBuilder(
                builder: (context, constraints) =>
                    legend == UiChartLegend.end &&
                        constraints.maxWidth >=
                            style.minimum *
                                MediaQuery.textScalerOf(context).scale(1)
                    ? Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(flex: 3, child: plot),
                          SizedBox(width: style.gap),
                          Expanded(child: key),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [plot, if (legend == UiChartLegend.end) key],
                      ),
              ),
            if (legend == UiChartLegend.bottom) key,
            for (final s in series) ...[
              SizedBox(height: style.gap),
              Text(s.label, style: ui.type.label.copyWith(color: ui.color.ink)),
              for (final d in s.data)
                Semantics(
                  container: true,
                  excludeSemantics: true,
                  label: '${s.label}, ${d.label}: ${d.description}',
                  child: Padding(
                    padding: EdgeInsets.only(top: ui.space.s1),
                    child: Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      spacing: style.gap,
                      children: [
                        Text(d.label, style: style.label),
                        Text(
                          d.description,
                          style: ui.type.mono.identifier.copyWith(
                            color: ui.color.ink,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ],
        ],
      ),
    );
  }
}

class _VisualizationPainter extends CustomPainter {
  const _VisualizationPainter({
    required this.series,
    required this.kind,
    required this.style,
    required this.showAxes,
    required this.maximum,
    required this.holeRatio,
    required this.direction,
    required this.textScaler,
  });

  /// The ordered series, each retaining its own measured and missing observations.
  final List<UiChartSeries> series;

  /// The visual encoding applied to the observations.
  final UiDataVisualizationKind kind;

  /// The visual treatment, independent of the content or controlled state.
  final UiDataVisualizationStyle style;

  /// Whether numeric ticks and category labels are displayed.
  final bool showAxes;

  /// The positive upper bound shared by gauge rings.
  final double maximum;

  /// The caller-supplied hole ratio.
  final double holeRatio;

  /// The caller-supplied direction.
  final TextDirection direction;
  final TextScaler textScaler;
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTRB(
      style.inset,
      style.inset,
      math.max(style.inset, size.width - style.inset),
      size.height - style.inset,
    );
    if (rect.isEmpty || series.isEmpty) return;
    final colors = style.colors;
    final outline = Paint()
      ..color = style.boundary
      ..style = PaintingStyle.stroke
      ..strokeWidth = style.stroke;
    final radial = [
      UiDataVisualizationKind.pie,
      UiDataVisualizationKind.donut,
      UiDataVisualizationKind.gauge,
      UiDataVisualizationKind.radar,
    ].contains(kind);
    if (radial) {
      final center = rect.center;
      final radius =
          math.min(rect.width, rect.height) /
          2 *
          (kind == UiDataVisualizationKind.radar && showAxes ? .65 : 1);
      if (kind == UiDataVisualizationKind.gauge) {
        final thickness = radius / (series.length * 2 + 1);
        for (var i = 0; i < series.length; i++) {
          final r = radius - thickness * (i * 2 + .5);
          final ring = Rect.fromCircle(center: center, radius: r);
          canvas.drawArc(
            ring,
            -math.pi / 2,
            math.pi * 2,
            false,
            Paint()
              ..color = style.boundary
              ..style = PaintingStyle.stroke
              ..strokeWidth = thickness,
          );
          if (series[i].data.isNotEmpty && series[i].data.first.measured) {
            canvas.drawArc(
              ring,
              -math.pi / 2,
              math.pi * 2 * series[i].data.first.value! / maximum,
              false,
              Paint()
                ..color = colors[i % colors.length]
                ..style = PaintingStyle.stroke
                ..strokeWidth = thickness,
            );
          }
        }
        return;
      }
      if (kind == UiDataVisualizationKind.pie ||
          kind == UiDataVisualizationKind.donut) {
        final data = series.first.data;
        final magnitude = data.fold<double>(
          1,
          (n, d) => d.measured ? math.max(n, d.value!) : n,
        );
        final sum = data.fold<double>(
          0,
          (n, d) => n + (d.measured ? d.value! / magnitude : 0),
        );
        if (sum == 0) {
          canvas.drawCircle(center, radius, outline);
          return;
        }
        var start = -math.pi / 2;
        for (var i = 0; i < data.length; i++) {
          if (!data[i].measured || data[i].value == 0) continue;
          final sweep = data[i].value! / magnitude / sum * math.pi * 2;
          final ring = Rect.fromCircle(
            center: center,
            radius: kind == UiDataVisualizationKind.donut
                ? radius * (1 + holeRatio) / 2
                : radius,
          );
          final paint = Paint()
            ..color = colors[i % colors.length]
            ..style = kind == UiDataVisualizationKind.donut
                ? PaintingStyle.stroke
                : PaintingStyle.fill
            ..strokeWidth = radius * (1 - holeRatio);
          canvas.drawArc(
            ring,
            start,
            sweep,
            kind == UiDataVisualizationKind.pie,
            paint,
          );
          if (kind == UiDataVisualizationKind.pie) {
            canvas.drawArc(ring, start, sweep, true, outline);
          }
          start += sweep;
        }
        return;
      }
      final categories = series
          .expand((s) => s.data)
          .map((d) => d.label)
          .toSet()
          .toList();
      if (categories.length < 3) return;
      final max = series
          .expand((s) => s.data)
          .fold<double>(1, (n, d) => d.measured ? math.max(n, d.value!) : n);
      Offset point(int i, double value) {
        final angle = i * math.pi * 2 / categories.length - math.pi / 2;
        return center +
            Offset(math.cos(angle), math.sin(angle)) * radius * value;
      }

      final occupiedLabels = <Rect>[];
      for (var i = 0; i < categories.length; i++) {
        canvas.drawLine(center, point(i, 1), outline);
        if (showAxes) {
          // Numbered markers reserve the plot for geometry. Full category text
          // is laid out by Flutter below it, where large text can wrap freely.
          final label = TextPainter(
            text: TextSpan(text: '${i + 1}', style: style.label),
            textDirection: direction,
            textScaler: textScaler,
            maxLines: 1,
          )..layout();
          final anchor = point(i, 1.25);
          final bounds = Rect.fromCenter(
            center: anchor,
            width: label.width,
            height: label.height,
          );
          final plotBounds = Offset.zero & size;
          // At extremely dense category counts a label may not fit. Preserve
          // its complete numbered key instead of clipping or overlapping it.
          if (plotBounds.contains(bounds.topLeft) &&
              plotBounds.contains(bounds.bottomRight) &&
              !occupiedLabels.any(
                (other) => other.overlaps(bounds.inflate(style.gap / 2)),
              )) {
            label.paint(canvas, bounds.topLeft);
            occupiedLabels.add(bounds);
          }
        }
      }
      for (var s = 0; s < series.length; s++) {
        final data = {for (final d in series[s].data) d.label: d};
        final complete = categories.every((c) => data[c]?.measured ?? false);
        final path = Path();
        var active = false;
        for (var i = 0; i < categories.length; i++) {
          final d = data[categories[i]];
          if (d == null || !d.measured) {
            active = false;
            continue;
          }
          final p = point(i, d.value! / max);
          if (active) {
            path.lineTo(p.dx, p.dy);
          } else {
            path.moveTo(p.dx, p.dy);
            active = true;
          }
          canvas.drawCircle(
            p,
            style.radius,
            Paint()..color = colors[s % colors.length],
          );
        }
        if (complete) path.close();
        canvas.drawPath(
          path,
          Paint()
            ..color = colors[s % colors.length]
            ..style = PaintingStyle.stroke
            ..strokeWidth = style.stroke,
        );
      }
      return;
    }
    final categories = series
        .expand((s) => s.data)
        .map((d) => d.label)
        .toSet()
        .toList();
    if (categories.isEmpty) return;
    final data = [
      for (final s in series) {for (final d in s.data) d.label: d},
    ];
    final magnitude = series
        .expand((s) => s.data)
        .fold<double>(
          1,
          (n, d) => d.measured ? math.max(n, d.value!.abs()) : n,
        );
    var low = 0.0, high = 0.0;
    for (final c in categories) {
      var positive = 0.0, negative = 0.0;
      for (final s in data) {
        final d = s[c];
        if (d == null || !d.measured) continue;
        final v = d.value! / magnitude;
        if (kind == UiDataVisualizationKind.stackedBars) {
          if (v >= 0) {
            positive += v;
          } else {
            negative += v;
          }
        } else {
          high = math.max(high, v);
          low = math.min(low, v);
        }
      }
      high = math.max(high, positive);
      low = math.min(low, negative);
    }
    final span = high == low ? 1 : high - low;
    double y(double value) => rect.bottom - (value - low) / span * rect.height;
    double x(double index) => direction == TextDirection.ltr
        ? rect.left + index * rect.width / categories.length
        : rect.right - index * rect.width / categories.length;
    final zero = y(0);
    canvas.drawLine(Offset(rect.left, zero), Offset(rect.right, zero), outline);
    if (showAxes) {
      for (var i = 1; i <= 3; i++) {
        final yy = rect.top + i * rect.height / 4;
        canvas.drawLine(
          Offset(rect.left, yy),
          Offset(rect.right, yy),
          Paint()
            ..color = style.boundary.withValues(alpha: .35)
            ..strokeWidth = style.stroke,
        );
      }
    }
    final positives = List<double>.filled(categories.length, 0),
        negatives = List<double>.filled(categories.length, 0);
    for (var s = 0; s < series.length; s++) {
      final paint = Paint()
        ..color = colors[s % colors.length]
        ..strokeWidth = style.stroke
        ..style = PaintingStyle.stroke;
      final path = Path();
      final fill = Path();
      var active = false;
      double lastX = 0;
      for (var i = 0; i < categories.length; i++) {
        final d = data[s][categories[i]];
        if (d == null || !d.measured) {
          if (active) {
            fill.lineTo(lastX, zero);
            fill.close();
          }
          active = false;
          continue;
        }
        final value = d.value! / magnitude;
        final px = x(i + .5), py = y(value);
        if (kind == UiDataVisualizationKind.groupedBars ||
            kind == UiDataVisualizationKind.stackedBars) {
          final stacked = kind == UiDataVisualizationKind.stackedBars;
          final width =
              rect.width /
              categories.length *
              .7 /
              (stacked ? 1 : series.length);
          final start = stacked
              ? (value >= 0 ? positives[i] : negatives[i])
              : 0.0;
          final end = start + value;
          if (value >= 0) {
            positives[i] = end;
          } else {
            negatives[i] = end;
          }
          final left = stacked
              ? px - width / 2
              : px - width * series.length / 2 + s * width;
          final bar = Rect.fromLTRB(
            left,
            math.min(y(start), y(end)),
            left + width,
            math.max(y(start), y(end)),
          );
          canvas.drawRect(bar, Paint()..color = colors[s % colors.length]);
          canvas.drawRect(bar, outline);
        } else {
          if (active) {
            path.lineTo(px, py);
            fill.lineTo(px, py);
          } else {
            path.moveTo(px, py);
            fill.moveTo(px, zero);
            fill.lineTo(px, py);
            active = true;
          }
          lastX = px;
          canvas.drawCircle(
            Offset(px, py),
            style.radius,
            Paint()..color = colors[s % colors.length],
          );
        }
      }
      if (active) {
        fill.lineTo(lastX, zero);
        fill.close();
      }
      if (kind == UiDataVisualizationKind.area) {
        canvas.drawPath(
          fill,
          Paint()..color = colors[s % colors.length].withValues(alpha: .15),
        );
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_VisualizationPainter oldDelegate) => true;
}
