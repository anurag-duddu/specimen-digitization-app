import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';

final sessionResponse =
    jsonDecode(
          File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
        )['session']
        as Json;

/// A loopback API, as the lab serves a run (UI.md T5.1), whose session
/// reports [mode]. It answers the session and the organization's collections,
/// and only to [bearer].
Future<HttpServer> loopbackApi(String mode, {required String bearer}) async {
  final HttpServer server = await HttpServer.bind(
    InternetAddress.loopbackIPv4,
    0,
  );
  final Json membership =
      (sessionResponse['memberships'] as List).first as Json;
  server.listen((HttpRequest request) async {
    final String path = request.uri.path;
    if (request.headers.value(HttpHeaders.authorizationHeader) !=
        'Bearer $bearer') {
      request.response.statusCode = 401;
      request.response.write(
        jsonEncode(<String, dynamic>{
          'error': <String, dynamic>{
            'code': 'unauthenticated',
            'message': 'Bearer identity required',
          },
        }),
      );
    } else if (path == '/v1/session') {
      request.response.write(
        jsonEncode(<String, dynamic>{...sessionResponse, 'mode': mode}),
      );
    } else if (path ==
        '/v1/organizations/${membership['organization_id']}/collections') {
      request.response.write(
        jsonEncode(<String, dynamic>{
          'items': <Json>[
            <String, dynamic>{
              'collection_id': membership['collection_id'],
              'display_name': 'Insects',
            },
          ],
        }),
      );
    } else {
      request.response.statusCode = 404;
    }
    await request.response.close();
  });
  return server;
}

void main() {
  test(
    "the lab's emulator-mode server signs in over loopback (UI.md T5.1)",
    () async {
      final HttpServer server = await loopbackApi(
        'emulator',
        bearer: 'lab-test-token',
      );
      addTearDown(() => server.close(force: true));
      final LocalFixtureSession session = LocalFixtureSession(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
      );
      addTearDown(session.dispose);

      await session.signIn('arbitrary@example.test', 'lab-test-token');

      expect(session.signedIn, true);
      expect(await session.token(), 'lab-test-token');
    },
  );

  test('the local build takes a loopback server in either local mode, and '
      'never one in production (UI.md T5.1)', () async {
    for (final String mode in <String>['synthetic', 'emulator', 'production']) {
      final HttpServer server = await loopbackApi(
        mode,
        bearer: 'lab-test-token',
      );
      final ApiSpecimenRepository repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
        token: () async => 'lab-test-token',
        expectedModes: LocalFixtureSession.localModes,
      );
      try {
        if (mode == 'production') {
          await expectLater(
            repository.scopes(),
            throwsA(
              isA<ApiFailure>().having(
                (ApiFailure e) => e.code,
                'code',
                'mode_mismatch',
              ),
            ),
            reason: 'a local build never talks to a production server',
          );
        } else {
          final List<CollectionScope> scopes = await repository.scopes();
          expect(scopes, hasLength(1), reason: mode);
          expect(repository.mode, mode);
        }
      } finally {
        repository.close();
        await server.close(force: true);
      }
    }
  });

  test(
    'actual HTTP fixture sign-in rejects wrong bearer before publishing success',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final requests = <String>[];
      server.listen((request) async {
        requests.add(request.uri.path);
        expect(request.method, 'GET');
        if (request.headers.value(HttpHeaders.authorizationHeader) !=
            'Bearer accepted-fixture-test-token') {
          request.response.statusCode = 401;
          request.response.write(
            jsonEncode({
              'error': {
                'code': 'unauthenticated',
                'message': 'Invalid synthetic bearer',
              },
            }),
          );
        } else {
          request.response.write(jsonEncode(sessionResponse));
        }
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));
      final session = LocalFixtureSession(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
      );
      addTearDown(session.dispose);
      final changes = <bool>[];
      final subscription = session.changes.listen(changes.add);
      addTearDown(subscription.cancel);
      await expectLater(
        session.signIn('arbitrary@example.test', 'wrong-token'),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'unauthenticated'),
        ),
      );
      expect(session.signedIn, false);
      expect(await session.token(), null);
      expect(changes, isNot(contains(true)));
      await session.signIn(
        'arbitrary@example.test',
        'accepted-fixture-test-token',
      );
      await Future<void>.delayed(Duration.zero);
      expect(session.signedIn, true);
      expect(session.userId, sessionResponse['user_id']);
      expect(await session.token(), 'accepted-fixture-test-token');
      expect(changes, [true]);
      expect(requests, ['/v1/session', '/v1/session']);
    },
  );
}
