// The risk meter: never a bare number, never a zero for an absent one.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/risk_assessment.dart';
import 'package:specimen_digitization/src/widgets/risk_meter.dart';

import 'harness.dart';

const List<String> _components = <String>[
  'Reading disagreement, weight 0.4',
  'Coverage gap, weight 0.2',
];

void main() {
  group('the measured decision mirrors riskComposite', () {
    test('a blocked, unmeasured or incomplete assessment has no score', () {
      expect(RiskMeter.isMeasured(composite: 62, status: 'blocked'), isFalse);
      expect(
        RiskMeter.isMeasured(composite: 62, status: 'unmeasured'),
        isFalse,
      );
      expect(
        RiskMeter.isMeasured(composite: 62, measurementComplete: false),
        isFalse,
      );
      expect(RiskMeter.isMeasured(composite: null), isFalse);
      expect(RiskMeter.isMeasured(composite: 62), isTrue);
    });

    test('it agrees with riskComposite on the same inputs', () {
      final List<Map<String, dynamic>> cases = <Map<String, dynamic>>[
        <String, dynamic>{'composite': 62, 'status': 'complete'},
        <String, dynamic>{'composite': 62, 'status': 'blocked'},
        <String, dynamic>{'composite': 62, 'status': 'unmeasured'},
        <String, dynamic>{'composite': 62, 'measurement_complete': false},
        <String, dynamic>{'composite': null},
      ];
      for (final Map<String, dynamic> risk in cases) {
        final bool measured = RiskMeter.isMeasured(
          composite: risk['composite'] as num?,
          status: risk['status'] as String?,
          measurementComplete: risk['measurement_complete'] as bool? ?? true,
        );
        expect(
          riskComposite(risk) != 'Not measured',
          measured,
          reason: '$risk',
        );
      }
    });
  });

  test('the headline is stated out of one hundred, never as a percentage', () {
    expect(RiskMeter.headline(composite: 62), 'Risk 62 of 100');
    expect(RiskMeter.headline(composite: null), 'Not measured');
    expect(
      RiskMeter.headline(composite: 62, status: 'blocked'),
      'Not measured',
    );
  });

  testWidgets('a measured score shows the number and a bar', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SizedBox(
        width: 320,
        child: RiskMeter(composite: 62, components: _components),
      ),
    );
    // The tile states the word, the numeral and the unit as three parts of
    // one object, and the arc draws the same value (10 section 5).
    expect(find.text(RiskMeter.label), findsOneWidget);
    expect(find.text('62'), findsOneWidget);
    expect(find.text('OF ${RiskMeter.scale}'), findsOneWidget);
    expect(find.byType(UiArcIndicator), findsOneWidget);
    expect(find.text('Reading disagreement, weight 0.4'), findsOneWidget);
  });

  testWidgets('an unmeasured assessment shows no bar and no zero', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SizedBox(
        width: 320,
        child: RiskMeter(
          composite: null,
          components: const <String>[],
          status: 'unmeasured',
        ),
      ),
    );
    // "Not measured" twice: once as the tile's value and once as the arc's
    // own absence. Neither is a zero.
    expect(find.text(RiskMeter.absence), findsOneWidget);
    expect(find.text(UiArcIndicator.unmeasuredLabel), findsOneWidget);
    expect(find.text('0'), findsNothing);
  });

  testWidgets('an incomplete measurement is not measured either', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SizedBox(
        width: 320,
        child: RiskMeter(
          composite: 62,
          components: const <String>[],
          measurementComplete: false,
        ),
      ),
    );
    expect(find.text(RiskMeter.absence), findsOneWidget);
    expect(find.text(UiArcIndicator.unmeasuredLabel), findsOneWidget);
  });

  testWidgets('an uncalibrated score carries the chip and the caveat', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SizedBox(
        width: 400,
        child: RiskMeter(
          composite: 62,
          components: _components,
          calibrated: false,
        ),
      ),
    );
    expect(find.text('Not calibrated'), findsNWidgets(2));
    expect(find.text('Why'), findsOneWidget);
  });

  testWidgets('the compact variant drops the component list', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      SizedBox(
        width: 200,
        child: RiskMeter(composite: 62, components: _components, compact: true),
      ),
    );
    expect(find.text('Risk 62 of 100'), findsOneWidget);
    expect(find.text('Reading disagreement, weight 0.4'), findsNothing);
  });

  test('a score without its components is refused in debug', () {
    expect(
      () => RiskMeter(composite: 62, components: const <String>[]),
      throwsAssertionError,
    );
    expect(
      () => RiskMeter(composite: null, components: const <String>[]),
      returnsNormally,
    );
  });

  testWidgets('the score and its qualifier are spoken as one phrase', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      SizedBox(
        width: 400,
        child: RiskMeter(
          composite: 62,
          components: _components,
          calibrated: false,
        ),
      ),
    );
    expect(
      find.bySemanticsLabel(RegExp('Risk 62 of 100, not calibrated')),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        SizedBox(
          width: 400,
          child: RiskMeter(composite: 62, components: _components),
        ),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
