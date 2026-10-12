import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'ui_finders.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'widget_test.dart' show TestRepository, TestSession, fixture;

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

class ChildDeniedRepository extends TestRepository
    implements AccessFailureSource {
  final controller = StreamController<ApiFailure>.broadcast(sync: true);
  @override
  Stream<ApiFailure> get accessFailures => controller.stream;
}

class SynchronousScopesDeniedRepository extends TestRepository
    implements AccessFailureSource {
  final controller = StreamController<ApiFailure>.broadcast(sync: true);
  bool denyScopes = true;

  @override
  Stream<ApiFailure> get accessFailures => controller.stream;

  @override
  Future<List<CollectionScope>> scopes() async {
    if (!denyScopes) return super.scopes();
    const failure = ApiFailure(
      'Collection membership could not be read.',
      status: 403,
    );
    controller.add(failure);
    throw failure;
  }
}

class SynchronousRecordDeniedRepository extends ChildDeniedRepository {
  bool denyRecord = true;

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    if (!denyRecord) return super.specimen(scope, id);
    const failure = ApiFailure('Record access was denied.', status: 403);
    controller.add(failure);
    throw failure;
  }
}

void main() {
  testWidgets(
    'synchronous record denial clears busy state before access recheck',
    (tester) async {
      final session = TestSession();
      final repo = SynchronousRecordDeniedRepository();
      final workspace = WorkspaceController(repository: repo, session: session);
      addTearDown(session.controller.close);
      addTearDown(repo.controller.close);
      try {
        workspace.start();
        await tester.pumpAndSettle();

        await workspace.openSpecimen(fixture.id);
        expect(workspace.recordLoading, isFalse);
        expect(workspace.selected, isNull);
        expect(workspace.scope, isNull);

        repo.denyRecord = false;
        await workspace.checkAccess();
        expect(workspace.recordLoading, isFalse);
        expect(workspace.scope, isNotNull);
        await workspace.openSpecimen(fixture.id);
        expect(workspace.selected?.id, fixture.id);
        expect(workspace.recordLoading, isFalse);
      } finally {
        workspace.dispose();
      }
    },
  );

  testWidgets(
    'synchronous access denial while checking settles and can be retried',
    (tester) async {
      final session = TestSession();
      final repo = SynchronousScopesDeniedRepository();
      addTearDown(session.controller.close);
      addTearDown(repo.controller.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repo),
      );
      await tester.pumpAndSettle();

      expect(find.text('Checking collection access'), findsNothing);
      expect(
        find.text('Collection access could not be verified'),
        findsOneWidget,
      );
      expect(find.text('Check access again'), findsOneWidget);

      repo.denyScopes = false;
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();

      expect(find.byType(AppShell), findsOneWidget);
      expect(find.text('Checking collection access'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('child-local evidence denial still clears parent workspace', (
    tester,
  ) async {
    final session = TestSession();
    final repo = ChildDeniedRepository();
    addTearDown(session.controller.close);
    addTearDown(repo.controller.close);
    await tester.pumpWidget(
      SpecimenDigitizationApp(session: session, repository: repo),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AppShell), findsOneWidget);
    // Child panels may catch their own exception; this independent boundary
    // must still remove all collection context and editing surfaces.
    repo.controller.add(
      const ApiFailure('Evidence access denied.', status: 403),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AppShell), findsNothing);
    expect(
      find.textContaining('Collection access could not be verified'),
      findsOneWidget,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'authorization denial removes collection and allows access recheck',
    (tester) async {
      final session = TestSession();
      final repo = RevokedRepository();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repo),
      );
      await tester.pumpAndSettle();
      expect(find.byType(AppShell), findsOneWidget);
      repo.revoked = true;
      await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Refresh collection'));
      await tester.pumpAndSettle();
      expect(find.byType(AppShell), findsNothing);
      expect(
        find.textContaining('Collection access could not be verified'),
        findsOneWidget,
      );
      repo.revoked = false;
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();
      expect(find.byType(AppShell), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
