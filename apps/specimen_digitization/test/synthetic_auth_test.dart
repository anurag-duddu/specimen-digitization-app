import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';
import 'widget_test.dart' show TestRepository;

final sessionResponse =
    jsonDecode(
          File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
        )['session']
        as Json;

class AccessRepository extends TestRepository {
  ApiFailure? accessFailure, dataFailure;
  bool empty = false;
  @override
  Future<List<CollectionScope>> scopes() async {
    if (accessFailure != null) throw accessFailure!;
    return empty ? [] : super.scopes();
  }

  @override
  Future<List<Specimen>> specimens(
    CollectionScope scope, {
    String query = '',
    String status = '',
  }) async {
    if (dataFailure != null) throw dataFailure!;
    return super.specimens(scope, query: query, status: status);
  }
}

void main() {
  testWidgets('synthetic setup failure preserves environment banner', (
    tester,
  ) async {
    await tester.pumpWidget(
      const SpecimenDigitizationApp(
        synthetic: true,
        setupMessage: 'Local synthetic setup failed.',
      ),
    );
    expect(find.textContaining('SYNTHETIC ENVIRONMENT'), findsOneWidget);
    expect(find.text('Local synthetic setup failed.'), findsOneWidget);
  });
  test(
    'pending validation and sign-out cannot produce a late authenticated session',
    () async {
      final response = Completer<http.Response>();
      final session = LocalFixtureSession(
        baseUrl: Uri.parse('http://localhost:8018'),
        client: MockClient((_) => response.future),
      );
      addTearDown(session.dispose);
      final changes = <bool>[];
      final subscription = session.changes.listen(changes.add);
      addTearDown(subscription.cancel);
      final attempt = session.signIn('test@example.test', 'test-only-token');
      expect(session.signedIn, false);
      expect(await session.token(), null);
      await session.signOut();
      response.complete(http.Response(jsonEncode(sessionResponse), 200));
      await attempt;
      await Future<void>.delayed(Duration.zero);
      expect(session.signedIn, false);
      expect(await session.token(), null);
      expect(changes, isNot(contains(true)));
    },
  );
  test(
    'offline, wrong environment and malformed responses never authenticate',
    () async {
      for (final state in ['offline', 'wrong-mode', 'malformed']) {
        final session = LocalFixtureSession(
          baseUrl: Uri.parse('http://localhost:8018'),
          client: MockClient((_) async {
            if (state == 'offline') {
              throw http.ClientException('Connection refused');
            }
            return http.Response(
              jsonEncode(
                state == 'wrong-mode'
                    ? {...sessionResponse, 'mode': 'production'}
                    : {'mode': 'synthetic'},
              ),
              200,
            );
          }),
        );
        await expectLater(
          session.signIn('test@example.test', 'test-only-token'),
          throwsA(
            isA<ApiFailure>().having(
              (e) => e.code,
              'code',
              state == 'offline' ? 'server_unavailable' : 'invalid_session',
            ),
          ),
        );
        expect(session.signedIn, false);
        expect(await session.token(), null);
        session.dispose();
      }
    },
  );
  testWidgets(
    'synthetic sign-in retains banner and distinguishes offline from rejected token',
    (tester) async {
      var offline = false;
      final session = LocalFixtureSession(
        baseUrl: Uri.parse('http://localhost:8018'),
        client: MockClient((_) async {
          if (offline) throw http.ClientException('Connection refused');
          return http.Response(
            '{"error":{"code":"unauthenticated","message":"Invalid synthetic bearer"}}',
            401,
          );
        }),
      );
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: TestRepository()),
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Email address'),
        'arbitrary@example.test',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Fixture token'),
        'wrong-token',
      );
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();
      expect(find.textContaining('rejected the fixture token'), findsOneWidget);
      expect(find.textContaining('SYNTHETIC ONLY.'), findsOneWidget);
      expect(find.text('Collection queue'), findsNothing);
      expect(session.signedIn, false);
      offline = true;
      await tester.ensureVisible(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();
      expect(find.textContaining('server is unavailable'), findsOneWidget);
      expect(find.textContaining('SYNTHETIC ONLY.'), findsOneWidget);
      expect(session.signedIn, false);
      await tester.pumpWidget(const SizedBox());
      session.dispose();
    },
  );
  testWidgets(
    'scope failures are distinct from verified no-role and preserve synthetic banner',
    (tester) async {
      final session = LocalFixtureSession(
        baseUrl: Uri.parse('http://localhost:8018'),
        client: MockClient(
          (_) async => http.Response(jsonEncode(sessionResponse), 200),
        ),
      );
      await session.signIn('test@example.test', 'test-only-token');
      final repo = AccessRepository()
        ..mode = 'production'
        ..accessFailure = const ApiFailure(
          'Connection interrupted',
          code: 'network',
        );
      await tester.pumpWidget(
        SpecimenDigitizationApp(session: session, repository: repo),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('SYNTHETIC ENVIRONMENT'), findsOneWidget);
      expect(find.textContaining('server is unavailable'), findsOneWidget);
      expect(
        find.textContaining('Your account has no assigned collection'),
        findsNothing,
      );
      repo.accessFailure = const ApiFailure(
        'Invalid synthetic bearer',
        status: 401,
      );
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('did not authorize this request'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Your account has no assigned collection'),
        findsNothing,
      );
      repo.accessFailure = null;
      repo.empty = true;
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Your account has no assigned collection'),
        findsOneWidget,
      );
      expect(find.textContaining('SYNTHETIC ENVIRONMENT'), findsOneWidget);
      repo.empty = false;
      await tester.tap(find.text('Check access again'));
      await tester.pumpAndSettle();
      expect(find.text('Collection queue'), findsOneWidget);
      expect(find.text('Intake'), findsOneWidget);
      repo.dataFailure = const ApiFailure(
        'Connection interrupted',
        code: 'network',
      );
      await tester.tap(find.byTooltip('Refresh collection'));
      await tester.pumpAndSettle();
      expect(find.textContaining('server is unavailable'), findsOneWidget);
      expect(
        find.textContaining('Your account has no assigned collection'),
        findsNothing,
      );
      expect(find.textContaining('SYNTHETIC ENVIRONMENT'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      session.dispose();
    },
  );
}
