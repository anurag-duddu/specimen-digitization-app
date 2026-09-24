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
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'intake_harness.dart';

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
        theme: AppTheme.light(),
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

  Future<void> choose(WidgetTester tester) => chooseFiles(tester);

  Future<void> submit(WidgetTester tester) => submitBatch(tester);

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
      'Not sensitive intake rejects incompatible batch value $value',
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
        await selectSensitivity(tester, 'Not sensitive');
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

  testWidgets('explicit Not sensitive selection reaches batch and item', (
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
    expect(
      find.descendant(of: sensitivityControl, matching: find.text('Sensitive')),
      findsOneWidget,
    );
    await selectSensitivity(tester, 'Not sensitive');
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
    await selectSensitivity(tester, 'Not sensitive');
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
        if (sensitive) await selectSensitivity(tester, 'Not sensitive');
        await choose(tester);
        await submit(tester);
        expect(accepted, 1);
        expect(resumes, greaterThan(0));
      },
    );
  }

  group('a Sensitive upload is not processed (UI.md T3.1)', () {
    ApiSpecimenRepository unused() => repository(
      (request) async => fail('nothing is sent before an upload: $request'),
    );

    testWidgets('Sensitive stays preselected, both options in words', (
      tester,
    ) async {
      final repo = unused();
      addTearDown(repo.close);
      await mount(tester, repo, onComplete: () {});
      final UiSegmented<bool> control = tester.widget<UiSegmented<bool>>(
        sensitivityControl,
      );
      expect(control.value, isTrue);
      // Both drawn as words, not fallen to the icon-only rung: names long
      // enough to carry the consequence did not fit this column.
      for (final String option in <String>['Sensitive', 'Not sensitive']) {
        expect(
          find.descendant(of: sensitivityControl, matching: find.text(option)),
          findsOneWidget,
        );
      }
    });

    testWidgets('the consequence is said before anything is sent', (
      tester,
    ) async {
      final repo = unused();
      addTearDown(repo.close);
      await mount(tester, repo, onComplete: () {});
      expect(
        find.text(
          'Applies to photographs you add next. Sensitive photographs are not '
          'processed.',
        ),
        findsOneWidget,
      );
      // The way round a choice that cannot be undone sits with the caveat
      // that says it cannot, behind its "Why" (02 sections 1.8 and 4.15).
      final CaveatText permanence = tester.widget<CaveatText>(
        find.byWidgetPredicate(
          (Widget w) =>
              w is CaveatText &&
              w.label ==
                  'Sensitivity cannot be changed after an upload starts.',
        ),
      );
      expect(
        permanence.why,
        endsWith(
          'To have a sensitive photograph processed, upload it again as not '
          'sensitive.',
        ),
      );
      expect(find.textContaining('wait'), findsNothing);
    });
  });
}
