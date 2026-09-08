import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/connection_config.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  test('live configuration rejects unsafe URLs and emulator routing', () {
    for (final url in [
      '',
      'http://localhost:8080',
      'https://user@api.test',
      'https://api.test?token=x',
      'https://api.test/#fragment',
    ]) {
      expect(
        () => ConnectionConfig(
          apiUrl: url,
          siteKey: 'public-key',
        ).validate(web: true),
        throwsFormatException,
      );
    }
    expect(
      () => const ConnectionConfig(
        apiUrl: 'https://api.test',
        siteKey: '',
      ).validate(web: true),
      throwsFormatException,
    );
    expect(
      () => const ConnectionConfig(
        apiUrl: 'https://api.test',
        siteKey: 'public-key',
        authEmulatorHost: 'localhost',
      ).validate(web: true),
      throwsFormatException,
    );
    expect(
      const ConnectionConfig(
        apiUrl: 'https://api.test/v1',
        siteKey: 'public-key',
      ).validate(web: true).scheme,
      'https',
    );
    expect(
      const ConnectionConfig(
        apiUrl: 'http://localhost:8081',
        siteKey: '',
        synthetic: true,
      ).validate(web: true).host,
      'localhost',
    );
  });

  test(
    'live HTTP verifies UID, membership shape, mode and both headers before access',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      var response = <String, dynamic>{};
      var requests = 0;
      server.listen((r) async {
        requests++;
        expect(r.headers.value('Authorization'), 'Bearer local-auth-fixture');
        expect(r.headers.value('X-Firebase-AppCheck'), 'local-check-fixture');
        r.response.headers.contentType = ContentType.json;
        r.response.write(jsonEncode(response));
        await r.response.close();
      });
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
        token: () async => 'local-auth-fixture',
        appCheckToken: () async => 'local-check-fixture',
        expectedMode: 'production',
        expectedUserId: () => 'expected-user',
      );
      addTearDown(repo.close);
      final valid = {
        'user_id': 'expected-user',
        'mode': 'production',
        'memberships': [],
      };
      for (final invalid in [
        {...valid, 'user_id': 'other-user'},
        {...valid, 'memberships': null},
        {
          ...valid,
          'memberships': [
            {'organization_id': 'o', 'role': 'reviewer'},
          ],
        },
        {
          ...valid,
          'memberships': ['invalid'],
        },
        {...valid, 'mode': 'synthetic'},
      ]) {
        response = invalid;
        await expectLater(repo.scopes(), throwsA(isA<ApiFailure>()));
      }
      response = valid;
      expect(await repo.scopes(), isEmpty);
      expect(requests, 6);
    },
  );

  test(
    'missing or failed App Check never sends a protected HTTP request',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() => server.close(force: true));
      var requests = 0;
      server.listen((r) async {
        requests++;
        await r.response.close();
      });
      for (final provider in <Future<String?> Function()?>[
        null,
        () async => null,
        () async => '',
        () async => throw StateError('private detail'),
      ]) {
        final repo = ApiSpecimenRepository(
          baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
          token: () async => 'local-auth-fixture',
          appCheckToken: provider,
          expectedMode: 'production',
          expectedUserId: () => 'expected-user',
        );
        await expectLater(
          repo.scopes(),
          throwsA(
            isA<ApiFailure>()
                .having((e) => e.code, 'code', 'app_check_unavailable')
                .having(
                  (e) => e.message,
                  'safe message',
                  isNot(contains('private detail')),
                ),
          ),
        );
        repo.close();
      }
      expect(requests, 0);
    },
  );
}
