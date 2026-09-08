import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'widget_test.dart' show TestRepository, TestSession;

class RevokedRepository extends TestRepository {
  bool revoked = false;
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    if (revoked) throw const ApiFailure('Access was revoked.', status: 403);
    return super.specimenPage(scope, filters: filters, cursor: cursor);
  }
}

void main() {
  testWidgets(
    'authorization denial removes collection and allows access recheck',
    (tester) async {
      final session = TestSession();
      final repo = RevokedRepository();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        MaterialApp(
          home: CollectionWorkspace(repository: repo, session: session),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Collection queue'), findsOneWidget);
      repo.revoked = true;
      await tester.tap(find.byTooltip('Refresh collection'));
      await tester.pumpAndSettle();
      expect(find.text('Collection queue'), findsNothing);
      expect(find.text('Authorized collection'), findsNothing);
      expect(
        find.textContaining('Collection access could not be verified'),
        findsOneWidget,
      );
      repo.revoked = false;
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();
      expect(find.text('Collection queue'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
