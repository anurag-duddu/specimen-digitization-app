// `UiArcIndicator` is where the north star's second principle meets a
// drawing: a gauge with no value renders the absence rather than a marker at
// zero. These tests hold that line, and the geometry either side of it.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('a measured gauge carries its value in semantics', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(
          value: 0.62,
          semanticsLabel: 'Risk',
          valueLabel: '62 of 100',
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('Risk'))
        .getSemanticsData();
    expect(data.label, 'Risk');
    expect(
      data.value,
      '62 of 100',
      reason:
          'a score is stated out of one hundred, never as a percentage '
          '(02 section 4.14)',
    );
    handle.dispose();
  });

  testWidgets('a gauge with no caller wording falls back to the percentage', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(value: 0.4, semanticsLabel: 'Coverage'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Coverage'))
          .getSemanticsData()
          .value,
      '40 percent',
    );
    handle.dispose();
  });

  testWidgets('no value draws the unmeasured glyph and the word, never a '
      'marker at zero', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(
          value: null,
          semanticsLabel: 'Risk',
          minLabel: '0',
          maxLabel: '100',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text(UiArcIndicator.unmeasuredLabel), findsOneWidget);
    expect(tester.widget<UiIcon>(find.byType(UiIcon)).spec, UiIcons.unmeasured);
    expect(find.text('0'), findsNothing);
    expect(
      find.text('100'),
      findsNothing,
      reason: 'a scale beside no value is a scale for nothing',
    );
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Risk'))
          .getSemanticsData()
          .value,
      UiArcIndicator.unmeasuredValue,
    );
    handle.dispose();
  });

  testWidgets('the word is not set in the one upper case role', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    final UiArcIndicatorStyle style = UiArcIndicatorStyle.resolve(ui);
    expect(style.label.fontSize, ui.type.unit.fontSize);
    expect(
      style.absence.fontSize,
      ui.type.label.fontSize,
      reason:
          '`unit` is the only upper case role in the product, and '
          '"Unmeasured" is a word rather than a unit (09 section 4.2)',
    );
  });

  testWidgets('the minimum and maximum are drawn where there is a value', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(
          value: 0.5,
          semanticsLabel: 'Risk',
          minLabel: '0',
          maxLabel: '100',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('0'), findsOneWidget);
    expect(find.text('100'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('0')).dx,
      lessThan(tester.getTopLeft(find.text('100')).dx),
    );
  });

  testWidgets('the two sweeps are 180 and 270 degrees', (
    WidgetTester tester,
  ) async {
    expect(UiArcSweep.half.sweep, closeTo(3.14159, 0.0001));
    expect(UiArcSweep.threeQuarter.sweep, closeTo(4.71239, 0.0001));
    for (final UiArcSweep sweep in UiArcSweep.values) {
      await tester.pumpWidget(
        uiHarness(
          child: UiArcIndicator(
            value: 0.5,
            semanticsLabel: 'Risk',
            sweep: sweep,
            size: 80,
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Size box = tester.getSize(find.byType(CustomPaint).first);
      expect(box.width, 80);
      expect(
        box.height,
        sweep == UiArcSweep.half ? lessThan(80) : 80,
        reason:
            'the half form carries no empty square under it, so a footer '
            'gauge does not push the tile taller than it needs to be',
      );
    }
  });

  testWidgets('the marker is the accent, cased so it can be seen at all', (
    WidgetTester tester,
  ) async {
    for (final Brightness mode in Brightness.values) {
      final UiThemeData ui = mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      final UiArcIndicatorStyle style = UiArcIndicatorStyle.resolve(ui);
      expect(style.marker, ui.color.accent);
      expect(style.track, ui.color.hairline);
      expect(style.stroke, ui.shape.stroke.hairline);
      expect(
        style.markerCasing,
        ui.color.ink,
        reason:
            'the accent measures near 1 to 1 on paper, so the one graphic '
            'carrying the value takes a casing the way a region stroke over '
            'a photograph does (09 section 3.6)',
      );
    }
  });

  testWidgets('the gauge repaints when the value moves and not otherwise', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(value: 0.2, semanticsLabel: 'Risk'),
      ),
    );
    await tester.pumpAndSettle();
    final CustomPainter first = tester
        .widget<CustomPaint>(find.byType(CustomPaint).first)
        .painter!;

    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(value: 0.2, semanticsLabel: 'Risk'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<CustomPaint>(find.byType(CustomPaint).first)
          .painter!
          .shouldRepaint(first),
      isFalse,
    );

    await tester.pumpWidget(
      uiHarness(
        child: const UiArcIndicator(value: 0.8, semanticsLabel: 'Risk'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<CustomPaint>(find.byType(CustomPaint).first)
          .painter!
          .shouldRepaint(first),
      isTrue,
    );
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    for (final double? value in <double?>[0.5, null]) {
      await tester.pumpWidget(
        uiHarness(
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: UiArcIndicator(
            value: value,
            semanticsLabel: 'Risk',
            minLabel: '0',
            maxLabel: '100',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('nothing about it animates, in either motion mode', (
    WidgetTester tester,
  ) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: const UiArcIndicator(value: 0.5, semanticsLabel: 'Risk'),
        ),
      );
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    }
  });
}
