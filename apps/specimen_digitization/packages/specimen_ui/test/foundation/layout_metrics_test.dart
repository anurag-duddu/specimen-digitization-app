import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

UiLayoutMetrics metrics(double width, {double scale = 1}) =>
    UiLayoutMetrics.fromConstraints(
      BoxConstraints(maxWidth: width),
      textScaler: TextScaler.linear(scale),
    );

void main() {
  test('local width resolves gutters without a viewport or context', () {
    expect(metrics(390).gutter, 16);
    expect(metrics(480).gutter, 16);
    expect(metrics(768).gutter, 16);
    expect(metrics(1280).gutter, 32);
    expect(metrics(390).contentWidth, 358);
    expect(metrics(1280).gap, 16);
    expect(metrics(1280).sectionGap, 24);
  });

  test('a column fits its minimum rather than a device breakpoint', () {
    final UiLayoutMetrics narrow = metrics(670);
    final UiLayoutMetrics wide = metrics(688);
    expect(narrow.columns(), 1);
    expect(wide.columns(), 2);
    expect(wide.columnWidth(2), 320);
    expect(metrics(1400).columns(maxColumns: 2), 2);
    expect(metrics(1400).columns(minWidth: 400), 3);
  });

  test('enlarged text stacks before a column becomes too narrow', () {
    expect(metrics(1024).columns(), 2);
    expect(metrics(1024, scale: 2).columns(), 1);
    expect(metrics(1024, scale: 2).minColumnWidth, 640);
    expect(metrics(1024, scale: 1.3).minColumnWidth % 8, 0);
    expect(metrics(1024, scale: 2).gutter, metrics(1024).gutter);
  });

  test(
    'reading measure stays bounded while narrow content uses its allocation',
    () {
      expect(metrics(2080).readableWidth, 640);
      expect(metrics(2080, scale: 2).readableWidth, 1280);
      expect(metrics(390).readableWidth, metrics(390).contentWidth);
      for (final double width in <double>[0, 16, 31, 48, 320, 390, 1280]) {
        final UiLayoutMetrics ui = metrics(width);
        expect(ui.gutter % 8, 0);
        expect(ui.contentWidth, inInclusiveRange(0, width));
        expect(ui.columnWidth(ui.columns()), greaterThanOrEqualTo(0));
      }
    },
  );

  test('unbounded constraints use a finite readable fallback', () {
    final UiLayoutMetrics ui = UiLayoutMetrics.fromConstraints(
      const BoxConstraints(),
    );
    expect(ui.width.isFinite, isTrue);
    expect(ui.readableWidth, 640);
    expect(ui.columns(maxColumns: 1), 1);
  });
}
