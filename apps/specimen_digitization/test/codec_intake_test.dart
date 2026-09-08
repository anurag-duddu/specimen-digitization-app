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
import 'package:specimen_digitization/src/models.dart';

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
      await tester.runAsync(() async {
        await tester.tap(find.text('Choose files'));
        var finished = false;
        for (var attempt = 0; attempt < 200; attempt++) {
          await Future<void>.delayed(const Duration(milliseconds: 25));
          await tester.pump();
          final choose = find.ancestor(
            of: find.text('Choose files'),
            matching: find.byWidgetPredicate((w) => w is FilledButton),
          );
          if (tester.widget<FilledButton>(choose).onPressed != null) {
            finished = true;
            break;
          }
        }
        expect(
          finished,
          isTrue,
          reason: 'Native source inspection must finish before upload',
        );
      });
      await tester.pumpAndSettle();
      expect(offset, 0);
      expect(completions, 0);
      await tester.tap(find.text('I checked framing and readability'));
      await tester.pump();
      await tester.scrollUntilVisible(
        find.text('Upload / resume selected files'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Upload / resume selected files'));
      await tester.pumpAndSettle();
      expect(offset, bytes.length);
      expect(completions, 1);
      expect(accepted, 0);
      expect(
        find.textContaining('The uploaded original is retained.'),
        findsOneWidget,
      );
      final stored = (await SharedPreferences.getInstance()).getString(
        'upload-handles-v1:owner:org/c',
      )!;
      final handles = objects(jsonDecode(stored));
      expect(handles.single['upload_id'], 'u');
      expect(handles.single.keys, unorderedEquals(['digest', 'upload_id']));
      expect(find.text('Accepted'), findsNothing);
    },
  );
}
