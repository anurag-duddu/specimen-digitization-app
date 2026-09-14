// The reason sheet: consequence first, reason required, typed text protected.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/reason_sheet.dart';

import 'harness.dart';

Widget _opener(void Function(String?) record) => Builder(
  builder: (BuildContext context) => TextButton(
    onPressed: () async => record(
      await showReasonSheet(
        context,
        title: 'Supersede the cleared decision?',
        action: 'Supersede the decision',
        consequence:
            'The record returns to the review queue and the current '
            'decision stops applying.',
        retained: 'The earlier decision and its reason stay in the history.',
        outstanding: <String>[
          'Locality is ambiguous',
          'Collector is unresolved',
        ],
        recentReasons: <String>['Wrong locality', 'Duplicate record'],
      ),
    ),
    child: const Text('Open'),
  ),
);

Future<void> _open(WidgetTester tester, void Function(String?) record) async {
  await pumpComponent(tester, _opener(record), size: const Size(1000, 800));
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('states the consequence, what is retained and what is left', (
    WidgetTester tester,
  ) async {
    await _open(tester, (String? _) {});
    expect(find.text('Supersede the cleared decision?'), findsOneWidget);
    expect(find.textContaining('returns to the review queue'), findsOneWidget);
    expect(find.textContaining('stay in the history'), findsOneWidget);
    expect(find.text('Still outstanding'), findsOneWidget);
    expect(find.text('Locality is ambiguous'), findsOneWidget);
    expect(find.text('Collector is unresolved'), findsOneWidget);
  });

  testWidgets('the primary button is disabled until a reason is typed', (
    WidgetTester tester,
  ) async {
    await _open(tester, (String? _) {});
    FilledButton primary() =>
        tester.widget<FilledButton>(find.byType(FilledButton));
    expect(primary().onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'Locality is wrong');
    await tester.pumpAndSettle();
    expect(primary().onPressed, isNotNull);
  });

  testWidgets('a recent reason fills the field', (WidgetTester tester) async {
    await _open(tester, (String? _) {});
    await tester.tap(find.widgetWithText(ActionChip, 'Wrong locality'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      'Wrong locality',
    );
  });

  testWidgets('the action returns the trimmed reason', (
    WidgetTester tester,
  ) async {
    String? result = 'not called';
    await _open(tester, (String? value) => result = value);
    await tester.enterText(find.byType(TextField), '  Wrong locality  ');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Supersede the decision'));
    await tester.pumpAndSettle();
    expect(result, 'Wrong locality');
  });

  testWidgets('Cancel returns nothing', (WidgetTester tester) async {
    String? result = 'not called';
    await _open(tester, (String? value) => result = value);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(result, isNull);
  });

  testWidgets('the scrim discards an empty form without asking', (
    WidgetTester tester,
  ) async {
    String? result = 'not called';
    await _open(tester, (String? value) => result = value);
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    expect(find.byType(ReasonForm), findsNothing);
    expect(result, isNull);
  });

  testWidgets('the scrim will not discard typed text, and offers to keep it', (
    WidgetTester tester,
  ) async {
    await _open(tester, (String? _) {});
    await tester.enterText(find.byType(TextField), 'Wrong locality');
    await tester.pumpAndSettle();

    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    expect(find.text('Discard this reason?'), findsOneWidget);

    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.byType(ReasonForm), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      'Wrong locality',
    );
  });

  testWidgets('discarding from that confirmation closes the sheet', (
    WidgetTester tester,
  ) async {
    String? result = 'not called';
    await _open(tester, (String? value) => result = value);
    await tester.enterText(find.byType(TextField), 'Wrong locality');
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard the reason'));
    await tester.pumpAndSettle();
    expect(find.byType(ReasonForm), findsNothing);
    expect(result, isNull);
  });

  testWidgets('a compact window gets the sheet form', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _opener((String? _) {}),
      size: const Size(420, 900),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsOneWidget);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        _opener((String? _) {}),
        size: const Size(1000, 800),
        theme: theme,
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      await expectAccessible(tester);
    }
  });
}
