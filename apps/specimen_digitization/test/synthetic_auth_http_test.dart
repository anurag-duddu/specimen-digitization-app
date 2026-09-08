import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/models.dart';

final sessionResponse =
    jsonDecode(
          File('test/fixtures/backend-wire-examples.json').readAsStringSync(),
        )['session']
        as Json;

void main() {
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
