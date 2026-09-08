import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  const scope = CollectionScope(
    organizationId: 'o',
    collectionId: 'c',
    name: 'Fixture',
  );
  final workspace = <String, dynamic>{
    'specimen_id': 's',
    'revision': 1,
    'asset': {'id': 'a'},
    'available_actions': ['field'],
    'fields': {},
  };
  for (final denial in [401, 403, 0]) {
    test(
      'record200 then image denial $denial invalidates access and blocks further work until recheck',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() => server.close(force: true));
        final paths = <String>[];
        var checks = 0;
        var recover = false;
        server.listen((r) async {
          paths.add(r.uri.path);
          if (r.uri.path == '/v1/session') {
            r.response.write(
              jsonEncode({
                'user_id': 'u',
                'mode': 'production',
                'memberships': [],
              }),
            );
          } else if (r.uri.path.endsWith('/workspace')) {
            r.response.write(jsonEncode(workspace));
          } else {
            r.response.statusCode = denial;
          }
          await r.response.close();
        });
        final repo = ApiSpecimenRepository(
          baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
          token: () async => 'local-fixture',
          expectedMode: 'production',
          expectedUserId: () => 'u',
          appCheckToken: () async {
            checks++;
            if (!recover && denial == 0 && checks == 3) {
              throw StateError('attestation unavailable');
            }
            return 'local-check';
          },
        );
        addTearDown(repo.close);
        final failures = <ApiFailure>[];
        final subscription = repo.accessFailures.listen(failures.add);
        addTearDown(subscription.cancel);
        await repo.scopes();
        await expectLater(
          repo.specimen(scope, 's'),
          throwsA(
            isA<ApiFailure>().having(
              (e) => e.status,
              'status',
              denial == 0 ? 403 : denial,
            ),
          ),
        );
        expect(failures, hasLength(1));
        final count = paths.length;
        await expectLater(
          repo.request('POST', '/must-not-send', body: {}),
          throwsA(isA<ApiFailure>()),
        );
        expect(paths, hasLength(count));
        expect(
          paths.where((p) => p.endsWith('/content')),
          hasLength(denial == 0 ? 0 : 1),
        );
        recover = true;
        expect(await repo.scopes(), isEmpty);
      },
    );
  }

  for (final unavailable in [503, -1]) {
    test(
      'non-auth image failure $unavailable retains recoverable preview without invalidating access',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() => server.close(force: true));
        server.listen((r) async {
          if (r.uri.path.endsWith('/workspace')) {
            r.response.write(jsonEncode(workspace));
          } else {
            if (unavailable == -1) {
              (await r.response.detachSocket()).destroy();
              return;
            }
            r.response.statusCode = unavailable;
          }
          await r.response.close();
        });
        final repo = ApiSpecimenRepository(
          baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
          token: () async => 'local-fixture',
        );
        addTearDown(repo.close);
        final failures = <ApiFailure>[];
        final subscription = repo.accessFailures.listen(failures.add);
        addTearDown(subscription.cancel);
        final record = await repo.specimen(scope, 's');
        expect(record.assets.single['preview_error'], isNotNull);
        expect(failures, isEmpty);
      },
    );
  }
  for (final kind in [
    'history',
    'historical',
    'raw',
    'graph',
    'intake',
    'upload',
  ]) {
    for (final denial in [401, 403, 0]) {
      test(
        '$kind denial $denial signals even when caller catches and suppresses next request',
        () async {
          final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
          addTearDown(() => server.close(force: true));
          var count = 0;
          var checks = 0;
          server.listen((r) async {
            count++;
            if (r.uri.path == '/v1/session') {
              r.response.write(
                jsonEncode({
                  'user_id': 'u',
                  'mode': 'production',
                  'memberships': [],
                }),
              );
            } else if (kind == 'upload' && r.method == 'GET') {
              r.response.write(
                jsonEncode({'offset': 0, 'upload_id': 'u', 'revision': 1}),
              );
            } else {
              r.response.statusCode = denial;
            }
            await r.response.close();
          });
          final repo = ApiSpecimenRepository(
            baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
            token: () async => 'local-fixture',
            expectedMode: 'production',
            expectedUserId: () => 'u',
            appCheckToken: () async {
              checks++;
              if (denial == 0 && checks > (kind == 'upload' ? 2 : 1)) {
                throw StateError('attestation unavailable');
              }
              return 'local-check';
            },
          );
          addTearDown(repo.close);
          final failures = <ApiFailure>[];
          final subscription = repo.accessFailures.listen(failures.add);
          addTearDown(subscription.cancel);
          await repo.scopes();
          try {
            switch (kind) {
              case 'history':
                await repo.historyPage(scope, 's', throughRevision: 1);
              case 'historical':
                await repo.historicalSpecimen(scope, 's', 1);
              case 'raw':
                await repo.artifact(
                  scope,
                  Specimen(workspace),
                  ArtifactRequest(
                    ArtifactKind.observationRaw,
                    'a',
                    sha256: 'a' * 64,
                  ),
                );
              case 'graph':
                await repo.artifact(
                  scope,
                  Specimen({
                    ...workspace,
                    'artifact_receipt': {
                      'artifact_sha256': 'a' * 64,
                      'artifact_size_bytes': 1,
                    },
                  }),
                  ArtifactRequest(
                    ArtifactKind.activeGraph,
                    'a',
                    sha256: 'a' * 64,
                  ),
                );
              case 'upload':
                await repo.upload(
                  scope,
                  {'upload_id': 'u'},
                  IntakeFile(
                    name: 'fixture',
                    bytes: Uint8List(2 * 1024 * 1024),
                    mimeType: 'image/png',
                    sha256: 'a' * 64,
                    method: 'files',
                  ),
                  (_) {},
                );
              case 'intake':
                await repo.createIntake(
                  scope,
                  IntakeFile(
                    name: 'fixture',
                    bytes: Uint8List(1),
                    mimeType: 'image/png',
                    sha256: 'a' * 64,
                    method: 'files',
                  ),
                  'fixture',
                );
            }
            fail('Must deny');
          } on ApiFailure {
            /* A child panel may show a local error. */
          }
          expect(failures, hasLength(1));
          final before = count;
          await expectLater(
            repo.request('POST', '/next-item', body: {}),
            throwsA(isA<ApiFailure>()),
          );
          expect(count, before);
        },
      );
    }
  }
}
