// The diff: a quantified summary, marked runs, and one spoken order.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';

import 'harness.dart';

void main() {
  group('compare', () {
    test('no reference means no comparison', () {
      final DiffOutcome outcome = DiffText.compare('Chicago 1912', null);
      expect(outcome.differingPositions, 0);
      expect(outcome.summary, isEmpty);
      expect(outcome.runs.single.kind, DiffRunKind.unchanged);
    });

    test('an identical reading differs nowhere', () {
      final DiffOutcome outcome = DiffText.compare('Chicago', 'Chicago');
      expect(outcome.identical, isTrue);
      expect(
        outcome.summary,
        'Matches the reference reading at every position',
      );
    });

    test('counts differing positions and groups them into runs', () {
      final DiffOutcome outcome = DiffText.compare(
        'Chicago 1913',
        'Chicago 1912',
      );
      expect(outcome.differingPositions, 1);
      expect(outcome.summary, 'Differs at 1 position');
      expect(outcome.runs, hasLength(2));
      expect(outcome.runs.first.kind, DiffRunKind.unchanged);
      expect(outcome.runs.last.kind, DiffRunKind.changed);
      expect(outcome.runs.last.text, '3');
    });

    test('three changed characters make one run, not three spans', () {
      final DiffOutcome outcome = DiffText.compare('Chixxxo', 'Chicago');
      expect(outcome.differingPositions, 3);
      expect(outcome.summary, 'Differs at 3 positions');
      expect(
        outcome.runs.where((DiffRun run) => run.kind == DiffRunKind.changed),
        hasLength(1),
      );
    });

    test('characters past the reference are added, not changed', () {
      final DiffOutcome outcome = DiffText.compare('Chicago IL', 'Chicago');
      final DiffRun last = outcome.runs.last;
      expect(last.kind, DiffRunKind.added);
      expect(last.text, ' IL');
      expect(last.marker, '+');
      expect(outcome.differingPositions, 3);
    });

    test('a reference longer than the literal still counts the difference', () {
      final DiffOutcome outcome = DiffText.compare('Chi', 'Chicago');
      expect(outcome.differingPositions, 4);
    });

    test('the summary is singular at one position', () {
      expect(DiffText.summaryFor(1), 'Differs at 1 position');
      expect(DiffText.summaryFor(2), 'Differs at 2 positions');
    });
  });

  testWidgets('the summary is rendered above the literal', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const DiffText(text: 'Chicago 1913', reference: 'Chicago 1912'),
    );
    expect(find.text('Differs at 1 position'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Differs at 1 position')).dy,
      lessThan(tester.getTopLeft(find.byType(SelectionArea)).dy),
    );
  });

  testWidgets('the block speaks the summary and then the full text', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const DiffText(text: 'Chixxxo', reference: 'Chicago'),
    );
    expect(
      find.bySemanticsLabel('Differs at 3 positions. Full text: Chixxxo'),
      findsOneWidget,
    );
    // The visible summary is not read a second time.
    expect(find.bySemanticsLabel('Differs at 3 positions'), findsNothing);
    handle.dispose();
  });

  testWidgets('a literal above the fallback is rendered plain', (
    WidgetTester tester,
  ) async {
    final String long = 'a' * (DiffText.plainFallbackRunes + 1);
    await pumpComponent(
      tester,
      SizedBox(
        width: 600,
        child: SingleChildScrollView(
          child: DiffText(text: long, reference: 'b$long'),
        ),
      ),
    );
    expect(
      find.textContaining('Too long to mark position by position'),
      findsOneWidget,
    );
    final Text body = tester.widget<Text>(
      find.descendant(
        of: find.byType(SelectionArea),
        matching: find.byType(Text),
      ),
    );
    expect(body.textSpan, isNull, reason: 'plain text, not a run of spans');
  });

  testWidgets('a literal below the fallback is rendered as runs', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const DiffText(text: 'Chixxxo', reference: 'Chicago'),
    );
    final Text body = tester.widget<Text>(
      find.descendant(
        of: find.byType(SelectionArea),
        matching: find.byType(Text),
      ),
    );
    expect(body.textSpan, isNotNull);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const DiffText(text: 'Chicago 1913', reference: 'Chicago 1912'),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });
}
