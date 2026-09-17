import 'dart:convert';
import 'dart:io';
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
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';

import 'intake_harness.dart';

void main() {
  testWidgets(
    'blocked server codec keeps the original upload handle and explains configuration recovery',
    (tester) async {
      tester.view.physicalSize = const Size(900, 1800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      SharedPreferences.setMockInitialValues({});
      const scope = CollectionScope(
        organizationId: 'org',
        collectionId: 'c',
        name: 'Synthetic',
      );
      final bytes = File(
        'test/fixtures/synthetic-orientation6.heic',
      ).readAsBytesSync();
      var offset = 0, completions = 0, accepted = 0;
      final repository = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8016'),
        token: () async => 'test-only',
        client: MockClient((request) async {
          if (request.url.path.endsWith('/batches')) {
            return http.Response('{"batch_id":"b"}', 200);
          }
          if (request.url.path.endsWith('/items')) {
            final body = jsonDecode(request.body) as Json;
            expect(body.containsKey('width'), false);
            expect(body.containsKey('height'), false);
            return http.Response(
              '{"upload_id":"u","state":"uploading","offset":0,"revision":1}',
              200,
            );
          }
          if (request.url.path.endsWith('/complete')) {
            completions++;
            return http.Response(
              '{"error":{"code":"processing_blocked","message":"image_codec_codec_disabled"}}',
              503,
            );
          }
          if (request.method == 'PUT') {
            expect(request.bodyBytes, bytes);
            offset = bytes.length;
          }
          return http.Response(
            jsonEncode({
              'upload_id': 'u',
              'offset': offset,
              'revision': 2,
              'state': 'uploading',
            }),
            200,
          );
        }),
      );
      addTearDown(repository.close);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: IntakeScreen(
              repository: repository,
              scope: scope,
              userId: 'owner',
              onComplete: () => accepted++,
              pickImages: (_) async => [
                XFile.fromData(bytes, path: 'source.heic', name: 'source.heic'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await chooseFiles(tester);
      expect(offset, 0);
      expect(completions, 0);
      await submitBatch(tester);
      expect(offset, bytes.length);
      expect(completions, 1);
      expect(accepted, 0);
      expect(find.textContaining('Your upload is kept.'), findsOneWidget);
      final stored = (await SharedPreferences.getInstance()).getString(
        'upload-handles-v1:owner:org/c',
      )!;
      final handles = objects(jsonDecode(stored));
      expect(handles.single['upload_id'], 'u');
      expect(handles.single.keys, unorderedEquals(['digest', 'upload_id']));
      // Scoped to the row: the header counts accepted photographs under the
      // same word.
      expect(
        find.descendant(
          of: find.byType(IntakeManifestRow),
          matching: find.text('Accepted'),
        ),
        findsNothing,
      );
    },
  );
}
