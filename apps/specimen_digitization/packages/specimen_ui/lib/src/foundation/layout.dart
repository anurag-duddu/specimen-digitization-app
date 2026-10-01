/// Layout measures derived from local constraints and the reader's text size.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

/// Shared layout measures on an eight-point structural grid.
///
/// Resolve inside a LayoutBuilder. Columns fit their actual content allocation,
/// so a narrow pane in a wide window behaves like a narrow pane.
@immutable
class UiLayoutMetrics {
  const UiLayoutMetrics._({
    required this.width,
    required this.gutter,
    required this.minColumnWidth,
    required this.readableMax,
  });

  /// Resolves without a BuildContext, including nonlinear text scaling.
  ///
  /// An unbounded parent receives one readable measure plus the maximum
  /// gutters. A bounded parent always wins over that fallback.
  factory UiLayoutMetrics.fromConstraints(
    BoxConstraints constraints, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    final double scale = math.max(1, textScaler.scale(16) / 16);
    final double readable = _ceilGrid(640 * scale);
    final double width = constraints.hasBoundedWidth
        ? constraints.maxWidth
        : math.max(
            constraints.minWidth.isFinite ? constraints.minWidth : 0,
            readable + 64,
          );
    final double desiredGutter = ((width * .025 / grid).round() * grid).clamp(
      16,
      32,
    );
    // Very small allocations still leave at least half their width for content.
    final double gutter = math.min(
      desiredGutter,
      (width / 4 / grid).floor() * grid,
    );
    return UiLayoutMetrics._(
      width: width,
      gutter: gutter,
      minColumnWidth: _ceilGrid(320 * scale),
      readableMax: readable,
    );
  }

  /// The structural spacing unit. Four points is reserved for optical gaps.
  static const double grid = 8;

  /// The width allocated by the parent.
  final double width;

  /// The horizontal inset on each side, normally 16 to 32 points.
  final double gutter;

  /// The preferred minimum width for a content column at this text scale.
  final double minColumnWidth;

  /// The longest useful reading measure, scaled with text rather than padding.
  final double readableMax;

  /// Space between related columns or control groups.
  double get gap => 16;

  /// Space between independent content sections.
  double get sectionGap => 24;

  /// Available content after the two outer gutters.
  double get contentWidth => math.max(0, width - 2 * gutter);

  /// A readable measure that never exceeds the available content.
  double get readableWidth => math.min(contentWidth, readableMax);

  /// The number of columns that fit, with one as the minimum.
  ///
  /// [minWidth] is an already-resolved intrinsic content requirement; omit it
  /// to use [minColumnWidth]. Narrower content wraps within the remaining width.
  int columns({double? minWidth, int maxColumns = 3}) {
    assert(maxColumns > 0);
    final double minimum = minWidth ?? minColumnWidth;
    assert(minimum > 0 && minimum.isFinite);
    return ((contentWidth + gap) / (minimum + gap)).floor().clamp(
      1,
      maxColumns,
    );
  }

  /// The equal share left for each of [count] columns after their gaps.
  double columnWidth(int count) {
    assert(count > 0);
    return math.max(0, (contentWidth - gap * (count - 1)) / count);
  }

  static double _ceilGrid(double value) => (value / grid).ceil() * grid;
}
