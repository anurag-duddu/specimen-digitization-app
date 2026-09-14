import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'widget_test.dart' show TestRepository, TestSession;

class PagedRepository extends TestRepository {
  final requests = <Map<String, String>>[];
  final pending = Completer<SpecimenPage>();
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    requests.add({...filters, 'cursor': cursor ?? 'start'});
    if (cursor != null) return pending.future;
    if (filters['disposition'] == 'cleared') {
      return const SpecimenPage([
        Specimen({'specimen_id': 'new', 'filename': 'Filtered record'}),
      ]);
    }
    return const SpecimenPage([
      Specimen({'specimen_id': 'first', 'filename': 'First page record'}),
    ], nextCursor: 'opaque-A');
  }
}

void main() {
  testWidgets(
    'queue explicitly pages and discards pending old-filter results',
    (tester) async {
      // Expanded, so the queue is one pane: the list-detail split at 1200
      // would put these controls in a 360 dp column.
      tester.view.physicalSize = const Size(900, 1400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final repo = PagedRepository();
      final session = TestSession();
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repo),
      );
      await tester.pumpAndSettle();
      expect(repo.requests.length, 1);
      expect(find.text('First page record'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Load more records'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Load more records'));
      await tester.pump();
      expect(repo.requests.last['cursor'], 'opaque-A');
      await tester.scrollUntilVisible(
        find.text('Cleared'),
        -200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Cleared'));
      await tester.pumpAndSettle();
      expect(find.text('Filtered record'), findsOneWidget);
      repo.pending.complete(
        const SpecimenPage([
          Specimen({'specimen_id': 'old', 'filename': 'Stale page record'}),
        ]),
      );
      await tester.pumpAndSettle();
      expect(find.text('Stale page record'), findsNothing);
      expect(find.text('Filtered record'), findsOneWidget);
      expect(repo.requests.last['cursor'], 'start');
      await tester.pumpWidget(const SizedBox());
      await session.controller.close();
    },
  );
}
