import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'workbench_harness.dart';

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

Finder get disagreementBadges => find.textContaining('Differs at');

Finder get matchingBadges =>
    find.textContaining('Matches the reference reading');

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
      expect(disagreementBadges, findsNothing);
      expect(matchingBadges, findsNWidgets(2));
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
    expect(disagreementBadges, findsOneWidget);
    expect(matchingBadges, findsOneWidget);
  });

  testWidgets('a single reading in each region has no peer disagreement', (
    tester,
  ) async {
    await showReadings(tester, [
      reading('r1-a', 'r1', 'Chicago 1912'),
      reading('r2-a', 'r2', 'Museum 25'),
    ]);
    expect(disagreementBadges, findsNothing);
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
