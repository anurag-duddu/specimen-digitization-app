import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';
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
      tester.view.physicalSize = const Size(1200, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final repo = PagedRepository();
      final session = TestSession();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CollectionWorkspace(repository: repo, session: session),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(repo.requests.length, 1);
      expect(find.text('First page record'), findsOneWidget);
      await tester.tap(find.text('Load more records'));
      await tester.pump();
      expect(repo.requests.last['cursor'], 'opaque-A');
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
