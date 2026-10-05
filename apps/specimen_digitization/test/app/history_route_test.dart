import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/app/session_notifier.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../widget_test.dart' show TestRepository, TestSession, fixture;

class RouteRepository extends TestRepository {
  final List<(String, String)> opened = [];
  int scopeReads = 0;
  Completer<List<CollectionScope>>? scopeGate;

  @override
  Future<List<CollectionScope>> scopes() async {
    scopeReads++;
    if (scopeGate != null) return scopeGate!.future;
    return super.scopes();
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    opened.add((scope.key, id));
    return fixture;
  }
}

class RestoringSession extends TestSession {
  RestoringSession() : super(signedIn: false);
  String _uid = '';

  @override
  String get userId => _uid;

  void restore([String uid = 'fixture-user']) {
    _uid = uid;
    signedIn = true;
    controller.add(true);
  }

  @override
  Future<void> signOut() async {
    _uid = '';
    await super.signOut();
  }
}

String locationOf(WidgetTester tester) => GoRouter.of(
  tester.element(find.byType(Navigator).first),
).routerDelegate.currentConfiguration.uri.toString();

Future<void> mount(
  WidgetTester tester,
  String platformLocation,
  TestSession session,
  RouteRepository repository,
) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(390, 844);
  tester.platformDispatcher.defaultRouteNameTestValue = platformLocation;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearDefaultRouteNameTestValue);
  addTearDown(session.controller.close);
  // No initialLocation override: this is the platform route read on reload.
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: repository),
  );
}

void main() {
  final encoded = AppRoutes.specimenOf(
    encodeCollectionKey('org/insects'),
    'fixture-001',
  );
  // Flutter 3.38.5 engine/window.dart routeInformationUpdated calls
  // Uri.decodeComponent before HashUrlStrategy writes browser history.
  final engineWritten = Uri.decodeComponent(encoded);

  for (final entry in {
    'legacy encoded link': encoded,
    'web history': engineWritten,
  }.entries) {
    testWidgets('${entry.key} reload opens the authorized exact record', (
      tester,
    ) async {
      final repository = RouteRepository();
      await mount(tester, entry.value, TestSession(), repository);
      await tester.pumpAndSettle();
      expect(find.byType(WorkbenchScreen), findsOneWidget);
      expect(locationOf(tester), encoded);
      expect(repository.opened, [('org/insects', 'fixture-001')]);
      await tester.pumpWidget(const SizedBox());
    });
  }

  for (final path in [encoded, engineWritten]) {
    testWidgets('cold identity restoration retains the record link: $path', (
      tester,
    ) async {
      final session = RestoringSession();
      final repository = RouteRepository();
      await mount(tester, path, session, repository);
      await tester.pumpAndSettle();
      expect(repository.scopeReads, 0);
      expect(repository.opened, isEmpty);
      session.restore();
      await tester.pumpAndSettle();
      expect(locationOf(tester), encoded);
      expect(repository.opened, [('org/insects', 'fixture-001')]);
      expect(find.byType(WorkbenchScreen), findsOneWidget);
      final router = GoRouter.of(tester.element(find.byType(Navigator).first));
      router.go(AppRoutes.queueOf(encodeCollectionKey('org/insects')));
      await tester.pumpAndSettle();
      router.go(AppRoutes.setup);
      await tester.pumpAndSettle();
      expect(
        locationOf(tester),
        AppRoutes.queueOf(encodeCollectionKey('org/insects')),
      );
      expect(repository.opened, [('org/insects', 'fixture-001')]);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'an initial signed-out emission does not erase the restored record link',
    (tester) async {
      final session = RestoringSession();
      final repository = RouteRepository();
      await mount(tester, engineWritten, session, repository);
      await tester.pumpAndSettle();
      session.controller.add(false);
      await tester.pumpAndSettle();
      expect(repository.opened, isEmpty);
      expect(repository.scopeReads, 0);
      session.restore();
      await tester.pumpAndSettle();
      expect(locationOf(tester), encoded);
      expect(repository.opened, [('org/insects', 'fixture-001')]);
      await tester.pumpWidget(const SizedBox());
    },
  );

  for (final restoredUser in ['different-user', 'fixture-user']) {
    testWidgets(
      'sign-out then restored account does not reopen the old record: $restoredUser',
      (tester) async {
        final session = RestoringSession()..restore();
        final repository = RouteRepository();
        await mount(tester, engineWritten, session, repository);
        await tester.pumpAndSettle();
        expect(repository.opened, [('org/insects', 'fixture-001')]);
        await session.signOut();
        await tester.pumpAndSettle();
        expect(session.userId, isEmpty);
        expect(locationOf(tester), AppRoutes.signIn);
        expect(find.byType(WorkbenchScreen), findsNothing);
        repository.scopeGate = Completer<List<CollectionScope>>();
        session.restore(restoredUser);
        await tester.pump();
        session.controller.add(
          true,
        ); // Overlapping auth and collection refresh.
        await tester.pump();
        expect(repository.opened, [('org/insects', 'fixture-001')]);
        repository.scopeGate!.complete(await TestRepository().scopes());
        await tester.pumpAndSettle();
        expect(
          locationOf(tester),
          AppRoutes.queueOf(encodeCollectionKey('org/insects')),
        );
        expect(repository.opened, [('org/insects', 'fixture-001')]);
        expect(find.byType(WorkbenchScreen), findsNothing);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  for (final signOut in [false, true]) {
    test(
      'an established account change or sign-out clears pending navigation: $signOut',
      () async {
        final session = RestoringSession()..restore();
        final notifier = AppSessionNotifier(session: session)
          ..pendingLocation = encoded;
        addTearDown(notifier.dispose);
        addTearDown(session.controller.close);
        if (signOut) {
          await session.signOut();
        } else {
          session.restore('different-user');
        }
        await Future<void>.delayed(Duration.zero);
        expect(notifier.pendingLocation, isNull);
      },
    );
  }

  test(
    'restoration preserves route data and leaves existing/global links intact',
    () {
      final restored = AppRoutes.restoreWebHistory(
        Uri.parse('$engineWritten?filter=needs%20review#reading'),
      )!;
      expect(restored.path, Uri.parse(encoded).path);
      expect(restored.queryParameters, {'filter': 'needs review'});
      expect(restored.fragment, 'reading');
      for (final path in [encoded, '/help', '/c/org%2Finsects/queue/queue']) {
        expect(AppRoutes.restoreWebHistory(Uri.parse(path)), isNull);
      }
      expect(
        AppRoutes.restoreWebHistory(
          Uri.parse('/c/org/insects/intake/sources/source-1'),
        )?.toString(),
        '/c/org%2Finsects/intake/sources/source-1',
      );
    },
  );

  for (final path in [
    '/c/org/plants/queue/private-record',
    '/c/org/insects/queue/fixture-001/extra',
    '/c/org/insects/help/fixture-001',
  ]) {
    testWidgets(
      'unavailable or malformed history cannot open a record: $path',
      (tester) async {
        final repository = RouteRepository();
        await mount(tester, path, TestSession(), repository);
        await tester.pumpAndSettle();
        expect(
          locationOf(tester),
          AppRoutes.queueOf(encodeCollectionKey('org/insects')),
        );
        expect(repository.opened, isEmpty);
        expect(find.byType(WorkbenchScreen), findsNothing);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
}
