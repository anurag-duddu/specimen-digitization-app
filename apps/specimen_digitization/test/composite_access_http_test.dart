import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  const scope = CollectionScope(
    organizationId: 'o',
    collectionId: 'c',
    name: 'Fixture',
  );
  for (final kind in ['preview', 'summary']) {
    for (final status in [-1, 403]) {
      test(
        'held $kind fallback $status cannot return stale specimen after recheck',
        () async {
          final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
          addTearDown(() => server.close(force: true));
          final pending = Completer<HttpRequest>();
          server.listen((r) async {
            if (r.uri.path == '/v1/session') {
              r.response.write(
                jsonEncode({
                  'user_id': 'u',
                  'mode': 'production',
                  'memberships': [],
                }),
              );
            } else if (r.uri.path.endsWith('/workspace')) {
              if (kind == 'summary') {
                r.response.statusCode = 413;
                r.response.write(
                  jsonEncode({
                    'error': {
                      'code': 'workspace_artifact_required',
                      'details': {'revision': 1, 'record_version_id': 'run:1'},
                    },
                  }),
                );
              } else {
                r.response.write(
                  jsonEncode({
                    'specimen_id': 's',
                    'revision': 1,
                    'asset': {'id': 'a'},
                    'available_actions': ['field'],
                    'fields': {},
                  }),
                );
              }
            } else {
              pending.complete(r);
              return;
            }
            await r.response.close();
          });
          final repo = ApiSpecimenRepository(
            baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
            token: () async => 'fixture',
            appCheckToken: () async => 'fixture-check',
            expectedMode: 'production',
            expectedUserId: () => 'u',
          );
          addTearDown(repo.close);
          final failures = <ApiFailure>[];
          final subscription = repo.accessFailures.listen(failures.add);
          addTearDown(subscription.cancel);
          await repo.scopes();
          final old = repo.specimen(scope, 's');
          final rejected = expectLater(
            old,
            throwsA(
              isA<ApiFailure>().having((e) => e.code, 'code', 'access_changed'),
            ),
          );
          final held = await pending.future;
          await repo.scopes();
          if (status == -1) {
            (await held.response.detachSocket()).destroy();
          } else {
            held.response.statusCode = status;
            await held.response.close();
          }
          await rejected;
          expect(failures, isEmpty);
          expect(await repo.scopes(), isEmpty);
        },
      );
    }
  }
  for (final status in [401, 403]) {
    test(
      'artifact summary $status never becomes a successful receipt',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() => server.close(force: true));
        server.listen((r) async {
          if (r.uri.path.endsWith('/workspace')) {
            r.response.statusCode = 413;
            r.response.write(
              jsonEncode({
                'error': {
                  'code': 'workspace_artifact_required',
                  'details': {'revision': 1, 'record_version_id': 'run:1'},
                },
              }),
            );
          } else {
            r.response.statusCode = status;
          }
          await r.response.close();
        });
        final repo = ApiSpecimenRepository(
          baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
          token: () async => 'fixture',
        );
        addTearDown(repo.close);
        final failures = <ApiFailure>[];
        final subscription = repo.accessFailures.listen(failures.add);
        addTearDown(subscription.cancel);
        await expectLater(
          repo.specimen(scope, 's'),
          throwsA(isA<ApiFailure>().having((e) => e.status, 'status', status)),
        );
        expect(failures, hasLength(1));
      },
    );
  }
}
