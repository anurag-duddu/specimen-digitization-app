import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';

const scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'c',
  name: 'Synthetic collection',
  permissions: ['upload'],
);

void main() {
  final bytes = File('test/fixtures/synthetic-label.png').readAsBytesSync();
  final digest = sha256.convert(bytes).toString();

  ApiSpecimenRepository repository(
    Future<http.Response> Function(http.Request) handler,
  ) => ApiSpecimenRepository(
    baseUrl: Uri.parse('http://localhost:8016'),
    token: () async => 'synthetic-test-token',
    client: MockClient(handler),
  );

  Future<void> mount(
    WidgetTester tester,
    ApiSpecimenRepository repository, {
    required VoidCallback onComplete,
  }) async {
    await tester.binding.setSurfaceSize(const Size(1000, 2200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: IntakeScreen(
            repository: repository,
            scope: scope,
            userId: 'owner',
            onComplete: onComplete,
            pickImages: (_) async => [
              XFile.fromData(bytes, path: 'source.png', name: 'source.png'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> choose(WidgetTester tester) async {
    await tester.ensureVisible(find.text('Choose files'));
    await tester.runAsync(() async {
      await tester.tap(find.text('Choose files'));
      var finished = false;
      for (var attempt = 0; attempt < 200; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 25));
        await tester.pump();
        final button = find.ancestor(
          of: find.text('Choose files'),
          matching: find.byWidgetPredicate((w) => w is FilledButton),
        );
        if (tester.widget<FilledButton>(button).onPressed != null) {
          finished = true;
          break;
        }
      }
      expect(finished, isTrue);
    });
    await tester.pumpAndSettle();
  }

  Future<void> selectSensitivity(WidgetTester tester, String label) async {
    final selector = find.byKey(const ValueKey('intake-sensitivity'));
    expect(selector, findsOneWidget);
    await tester.ensureVisible(selector);
    await tester.tap(selector);
    await tester.pumpAndSettle();
    await tester.tap(find.text(label).last);
    await tester.pumpAndSettle();
  }

  Future<void> submit(WidgetTester tester) async {
    final quality = find.text('I checked framing and readability');
    await tester.ensureVisible(quality);
    await tester.tap(quality);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Upload / resume selected files'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Upload / resume selected files'));
    await tester.pumpAndSettle();
  }

  test(
    'legacy intake defaults to Sensitive in both creation requests',
    () async {
      final bodies = <Json>[];
      final repo = repository((request) async {
        bodies.add(jsonDecode(request.body) as Json);
        return http.Response(
          request.url.path.endsWith('/batches')
              ? '{"batch_id":"b"}'
              : '{"upload_id":"u"}',
          200,
        );
      });
      addTearDown(repo.close);
      await repo.createIntake(
        scope,
        IntakeFile(
          name: 'source.png',
          bytes: bytes,
          mimeType: 'image/png',
          sha256: digest,
          method: 'files',
        ),
        'sensitive-default',
      );
      expect(bodies, hasLength(2));
      expect(bodies.map((body) => body['sensitive']), [true, true]);
    },
  );

  test('a conflicting batch stops before creating its item', () async {
    var items = 0;
    final repo = repository((request) async {
      if (request.url.path.endsWith('/batches')) {
        return http.Response('{"batch_id":"b","sensitive":false}', 200);
      }
      items++;
      return http.Response('{"upload_id":"u"}', 200);
    });
    addTearDown(repo.close);
    await expectLater(
      repo.createIntake(
        scope,
        IntakeFile(
          name: 'source.png',
          bytes: bytes,
          mimeType: 'image/png',
          sha256: digest,
          method: 'files',
        ),
        'conflicting-batch',
      ),
      throwsA(
        isA<ApiFailure>().having(
          (error) => error.code,
          'code',
          'intake_sensitivity_mismatch',
        ),
      ),
    );
    expect(items, 0);
  });

  for (final value in <dynamic>[null, true, 'false']) {
    testWidgets(
      'Non-sensitive intake rejects incompatible batch value $value',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        var items = 0, accepted = 0;
        final repo = repository((request) async {
          if (request.url.path.endsWith('/batches')) {
            return http.Response(
              jsonEncode({'batch_id': 'b', 'sensitive': ?value}),
              200,
            );
          }
          items++;
          return http.Response(
            jsonEncode({
              'upload_id': 'u',
              'offset': bytes.length,
              'revision': 2,
            }),
            200,
          );
        });
        addTearDown(repo.close);
        await mount(tester, repo, onComplete: () => accepted++);
        await selectSensitivity(tester, 'Non-sensitive');
        await choose(tester);
        await submit(tester);
        expect(items, 0);
        expect(accepted, 0);
        expect(
          find.textContaining('original classification is unchanged'),
          findsOneWidget,
        );
      },
    );
  }

  testWidgets('explicit Non-sensitive selection reaches batch and item', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final bodies = <Json>[];
    var offset = 0, accepted = 0;
    final repo = repository((request) async {
      if (request.url.path.endsWith('/batches') ||
          request.url.path.endsWith('/items')) {
        final body = jsonDecode(request.body) as Json;
        bodies.add(body);
        return http.Response(
          jsonEncode({
            'batch_id': 'b',
            'upload_id': 'u',
            'sensitive': body['sensitive'],
            'state': 'uploading',
            'offset': 0,
          }),
          200,
        );
      }
      if (request.method == 'PUT') offset = bytes.length;
      return http.Response(
        jsonEncode({'upload_id': 'u', 'offset': offset, 'revision': 2}),
        200,
      );
    });
    addTearDown(repo.close);
    await mount(tester, repo, onComplete: () => accepted++);
    expect(find.text('Sensitive'), findsOneWidget);
    await selectSensitivity(tester, 'Non-sensitive');
    await choose(tester);
    await submit(tester);
    expect(bodies.map((body) => body['sensitive']), [false, false]);
    expect(accepted, 1);
    expect(offset, bytes.length);
  });

  testWidgets('changing the choice and reselecting never changes a retry', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final bodies = <Json>[];
    var items = 0, accepted = 0;
    final repo = repository((request) async {
      if (request.url.path.endsWith('/batches')) {
        bodies.add(jsonDecode(request.body) as Json);
        return http.Response('{"batch_id":"b","sensitive":false}', 200);
      }
      if (request.url.path.endsWith('/items')) {
        bodies.add(jsonDecode(request.body) as Json);
        items++;
        if (items == 1) {
          return http.Response(
            '{"error":{"code":"unavailable","message":"Try again"}}',
            503,
          );
        }
        return http.Response('{"upload_id":"u","sensitive":false}', 200);
      }
      return http.Response(
        jsonEncode({'upload_id': 'u', 'offset': bytes.length, 'revision': 2}),
        200,
      );
    });
    addTearDown(repo.close);
    await mount(tester, repo, onComplete: () => accepted++);
    await selectSensitivity(tester, 'Non-sensitive');
    await choose(tester);
    await submit(tester);
    expect(accepted, 0);
    await selectSensitivity(tester, 'Sensitive');
    await choose(tester);
    await submit(tester);
    expect(bodies.map((body) => body['sensitive']), [
      false,
      false,
      false,
      false,
    ]);
    expect(accepted, 1);
  });

  for (final sensitive in [true, false]) {
    testWidgets(
      'restored $sensitive upload resumes without changing its classification',
      (tester) async {
        SharedPreferences.setMockInitialValues({
          'upload-handles-v1:owner:org/c': jsonEncode([
            {'digest': digest, 'upload_id': 'existing'},
          ]),
        });
        var accepted = 0, resumes = 0;
        final repo = repository((request) async {
          expect(request.url.path, contains('/uploads/existing'));
          if (request.method == 'GET') {
            resumes++;
          } else {
            expect(request.url.path, endsWith('/complete'));
            expect(jsonDecode(request.body), {'expected_revision': 4});
          }
          return http.Response(
            jsonEncode({
              'upload_id': 'existing',
              'offset': bytes.length,
              'revision': 4,
              if (!sensitive) 'sensitive': false,
            }),
            200,
          );
        });
        addTearDown(repo.close);
        await mount(tester, repo, onComplete: () => accepted++);
        if (sensitive) await selectSensitivity(tester, 'Non-sensitive');
        await choose(tester);
        await submit(tester);
        expect(accepted, 1);
        expect(resumes, greaterThan(0));
      },
    );
  }
}
