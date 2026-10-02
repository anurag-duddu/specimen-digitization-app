import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';

import 'workbench_harness.dart';
import 'ui_finders.dart';
import 'package:specimen_ui/specimen_ui.dart';

Json reading(
  String model,
  Object? region,
  String literal, {
  bool legacy = false,
}) => {
  'id': model,
  'model_id': model,
  'region_id': region,
  if (legacy) 'verbatim_text': literal else 'literal_text': literal,
};

Future<void> showReadings(WidgetTester tester, List<Json> observations) async {
  useWindow(tester, largeWindow);
  await tester.pumpWidget(
    workbenchHost(
      ReviewWorkbench(
        specimen: Specimen({
          'specimen_id': 'synthetic-region-comparison',
          'display_name': 'Synthetic local comparison',
          'revision': 1,
          'available_actions': <String>[],
          'regions': [
            for (final id
                in observations
                    .map((o) => o['region_id'])
                    .whereType<String>()
                    .where((id) => id.trim().isNotEmpty)
                    .toSet())
              {
                'region_id': id,
                'bbox': [0, 0, 10, 10],
              },
          ],
          'observations': observations,
        }),
        onChange: (_) async => fail('Viewing readings must not mutate data'),
        onRetry: (_) async => fail('Viewing readings must not run models'),
        onRefresh: () {},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> selectLabel(WidgetTester tester, int number) =>
    selectLabelOption(tester, 'Label $number');

Future<void> selectLabelOption(WidgetTester tester, String label) async {
  final Finder chooser = uiSelect('Label');
  if (chooser.evaluate().isEmpty) {
    await tester.scrollUntilVisible(
      chooser,
      240,
      scrollable: find
          .descendant(
            of: find.byKey(evidenceScrollKey),
            matching: find.byType(Scrollable),
          )
          .first,
      maxScrolls: 24,
    );
  }
  await tester.ensureVisible(chooser);
  await tester.pumpAndSettle();
  expect(chooser.hitTestable(), findsOneWidget);
  await tester.tap(chooser);
  await tester.pumpAndSettle();
  final Finder filter = find.byWidgetPredicate(
    (Widget widget) =>
        widget is FieldCore && widget.semanticsLabel == 'Filter the options',
  );
  if (filter.evaluate().isNotEmpty) {
    await tester.enterText(filter, label);
    await tester.pumpAndSettle();
  }
  final item = find.byWidgetPredicate(
    (w) => w is UiListRow && w.title == label,
  );
  await tester.ensureVisible(item);
  await tester.pumpAndSettle();
  expect(
    item.hitTestable(),
    findsOneWidget,
    reason: '$label must be reachable inside the menu',
  );
  await tester.tap(item);
  await tester.pumpAndSettle();
}

Finder get disagreementBadges => find.textContaining('Differs in');

Finder get matchingReadings => find.byWidgetPredicate(
  (widget) =>
      widget is DiffText &&
      widget.reference != null &&
      widget.text == widget.reference,
  description: 'literal reading matching its own regional reference',
);

void main() {
  testWidgets(
    'agreeing readers in different regions have no disagreement badges',
    (tester) async {
      await showReadings(tester, [
        reading('r1-a', 'r1', 'Chicago 1912'),
        reading('r1-b', 'r1', 'Chicago 1912'),
        reading('r2-a', 'r2', 'Museum 25'),
        reading('r2-b', 'r2', 'Museum 25'),
      ]);
      for (final label in [1, 2]) {
        await selectLabel(tester, label);
        expect(disagreementBadges, findsNothing);
        expect(matchingReadings, findsOneWidget);
      }
    },
  );

  testWidgets('interleaved readings compare only within their own region', (
    tester,
  ) async {
    await showReadings(tester, [
      reading('r1-a', 'r1', 'Chicago 1912'),
      reading('r2-a', 'r2', 'Museum 25'),
      reading('r1-b', 'r1', 'Chicago 1912'),
      reading('r2-b', 'r2', 'Museum 26'),
    ]);
    await selectLabel(tester, 1);
    expect(disagreementBadges, findsNothing);
    expect(matchingReadings, findsOneWidget);
    expect(find.text('Museum 25'), findsNothing);
    await selectLabel(tester, 2);
    expect(disagreementBadges, findsOneWidget);
    expect(matchingReadings, findsNothing);
    expect(find.text('Chicago 1912'), findsNothing);
  });

  testWidgets('a single reading in each region has no peer disagreement', (
    tester,
  ) async {
    await showReadings(tester, [
      reading('r1-a', 'r1', 'Chicago 1912'),
      reading('r2-a', 'r2', 'Museum 25'),
    ]);
    for (final label in [1, 2]) {
      await selectLabel(tester, label);
      expect(disagreementBadges, findsNothing);
      expect(matchingReadings, findsNothing);
    }
  });

  testWidgets(
    'unidentified readings never compare against another observation',
    (tester) async {
      await showReadings(tester, [
        reading('known', 'r1', 'Known label'),
        reading('missing-a', null, 'Unknown label A'),
        reading('missing-b', null, 'Unknown label B'),
        reading('empty', '', 'Unknown label C'),
        reading('whitespace', '  ', 'Unknown label D'),
        reading('invalid', 7, 'Unknown label E'),
      ]);
      await selectLabelOption(tester, 'All labels');
      await tester.tap(find.text('Unassigned model results'));
      await tester.pumpAndSettle();
      for (final suffix in ['A', 'B', 'C', 'D', 'E']) {
        expect(find.text('Unknown label $suffix'), findsOneWidget);
      }
      expect(disagreementBadges, findsNothing);
    },
  );

  testWidgets('legacy verbatim text is also used as the regional reference', (
    tester,
  ) async {
    await showReadings(tester, [
      reading('legacy-a', 'r1', 'Chicago 1912', legacy: true),
      reading('legacy-b', 'r1', 'Chicago 1912', legacy: true),
    ]);
    await selectLabel(tester, 1);
    expect(matchingReadings, findsOneWidget);
    expect(disagreementBadges, findsNothing);
  });

  testWidgets(
    'regional highlighting preserves Unicode and literal line breaks',
    (tester) async {
      const right = 'α🙂\nuncertain?';
      await showReadings(tester, [
        reading('r1-a', 'r1', 'Unrelated first label'),
        reading('r2-a', 'r2', 'α🙃\nuncertain?'),
        reading('r2-b', 'r2', right),
      ]);
      await selectLabel(tester, 2);
      expect(disagreementBadges, findsOneWidget);
      final rendered = tester
          .widgetList<Text>(find.byType(Text))
          .singleWhere((text) => text.textSpan?.toPlainText() == right);
      final characters = (rendered.textSpan! as TextSpan).children!
          .cast<TextSpan>();
      final highlighted = characters.where(
        (span) => span.style?.decoration == TextDecoration.underline,
      );
      expect(highlighted.map((span) => span.text).join(), '🙂');
      expect(rendered.textSpan!.toPlainText(), right);
    },
  );
}
