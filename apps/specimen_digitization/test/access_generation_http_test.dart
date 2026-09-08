import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  for (final switchUser in [false, true]) {
    for (final lateStatus in [200, 403]) {
      test(
        'late $lateStatus cannot restore or revoke rechecked session (switch=$switchUser)',
        () async {
          var user = 'first';
          final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
          addTearDown(() => server.close(force: true));
          final oldRequest = Completer<HttpRequest>();
          server.listen((r) async {
            if (r.uri.path == '/old') {
              oldRequest.complete(r);
              return;
            }
            r.response.write(
              jsonEncode(
                r.uri.path == '/v1/session'
                    ? {'user_id': user, 'mode': 'production', 'memberships': []}
                    : {'current': true},
              ),
            );
            await r.response.close();
          });
          final repo = ApiSpecimenRepository(
            baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
            token: () async => 'local-fixture',
            appCheckToken: () async => 'local-check',
            expectedMode: 'production',
            expectedUserId: () => user,
          );
          addTearDown(repo.close);
          final failures = <ApiFailure>[];
          final subscription = repo.accessFailures.listen(failures.add);
          addTearDown(subscription.cancel);
          await repo.scopes();
          final old = repo.request('GET', '/old');
          final rejectedOld = expectLater(
            old,
            throwsA(
              isA<ApiFailure>().having((e) => e.code, 'code', 'access_changed'),
            ),
          );
          final held = await oldRequest.future;
          if (switchUser) user = 'second';
          await repo.scopes();
          held.response.statusCode = lateStatus;
          held.response.write('{}');
          await held.response.close();
          await rejectedOld;
          expect(failures, isEmpty);
          expect(await repo.request('GET', '/current'), {'current': true});
        },
      );
    }
  }
  test(
    'failed or partial recheck remains latched; only full verified recheck unlocks',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      var count = 0;
      var collectionsAvailable = false;
      var collectionShapeValid = false;
      final heldSession = Completer<HttpRequest>();
      var hold = false;
      server.listen((r) async {
        count++;
        if (hold && r.uri.path == '/v1/session') {
          heldSession.complete(r);
          return;
        }
        if (r.uri.path == '/v1/session') {
          r.response.write(
            jsonEncode({
              'user_id': 'u',
              'mode': 'production',
              'memberships': [
                {
                  'organization_id': 'o',
                  'collection_id': 'c',
                  'role': 'reviewer',
                },
              ],
            }),
          );
        } else if (r.uri.path.endsWith('/collections')) {
          r.response.statusCode = collectionsAvailable ? 200 : 503;
          r.response.write(
            jsonEncode({
              'items': collectionShapeValid
                  ? [
                      {'collection_id': 'c'},
                    ]
                  : [],
            }),
          );
        } else {
          r.response.statusCode = 403;
        }
        await r.response.close();
      });
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
        token: () async => 'local-fixture',
        appCheckToken: () async => 'local-check',
        expectedMode: 'production',
        expectedUserId: () => 'u',
      );
      addTearDown(repo.close);
      await expectLater(
        repo.request('GET', '/deny'),
        throwsA(isA<ApiFailure>()),
      );
      await expectLater(repo.scopes(), throwsA(isA<ApiFailure>()));
      final before = count;
      await expectLater(
        repo.request('GET', '/must-not-send'),
        throwsA(isA<ApiFailure>()),
      );
      expect(count, before);
      hold = true;
      final recheck = repo.scopes();
      final held = await heldSession.future;
      final during = count;
      await expectLater(
        repo.request('POST', '/must-not-send'),
        throwsA(isA<ApiFailure>()),
      );
      expect(count, during);
      held.response.write(
        jsonEncode({'user_id': 'u', 'mode': 'production', 'memberships': []}),
      );
      await held.response.close();
      expect(await recheck, isEmpty);
      hold = false;
      collectionsAvailable = true;
      await expectLater(repo.scopes(), throwsA(isA<ApiFailure>()));
      final afterIncomplete = count;
      await expectLater(
        repo.request('POST', '/must-not-send'),
        throwsA(isA<ApiFailure>()),
      );
      expect(count, afterIncomplete);
      collectionShapeValid = true;
      expect(await repo.scopes(), hasLength(1));
    },
  );
}
